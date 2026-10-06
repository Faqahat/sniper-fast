//! Scenario tests (PLAN WP-09 item 4): every catalogued kind of loss, S1-S8 with S1b, S1b', S4b and S8b, reproduced on
//! real account layouts and replayed.
//!
//! - **Inputs.** `testdata/scenarios/accounts.json`: the real accounts of seven mainnet pools (USDC/SOL on PumpSwap,
//!   Raydium CPMM, Raydium AMM v4, Meteora DLMM and DAMM v2; the bolt trade's PumpSwap and DLMM pools on 9dSMwFfP/SOL)
//!   with every account arbx follows for them, read once from public RPC by `tools/capture-fixtures.py --scenarios`
//!   (`capture.json` says what and why). A scenario boots a registry from these bytes through the real `pools::boot`
//!   (served by a local mock RPC), then mutates copies synthetically with the venues' own maths (a swap's vault, bin and
//!   price changes).
//! - **A scenario is a run.** [`Rig`] drives an offline engine as `arbx run` does: the boot snapshot recorded in
//!   accounts.bin and journaled (t 0), the engine_init record, the registry and the state stream's watch list and roles
//!   (`pools.json`, `registry-run.json`),
//!   the frozen config (`deploy/arbx-stage0.toml`, written as the run's `config.toml`), every update recorded in
//!   accounts.bin before the engine handles it, every input and timer journaled. Each scenario asserts its expected
//!   result (PLAN WP-09's table), then replays its run directory with `replay::replay(.., compare)`: the replay must be
//!   whole and give the run's state digest, decision digest (also as the run recorded them: events.jsonl
//!   `engine_digests`) and identical decisions and commit groups.
//! - **Expected values** that depend on venue maths (sizes, gross, net, CU, crossings, which route is best, and
//!   `below_min_profit` against `best`) live apart from the inputs, in `testdata/scenarios/expected/<scenario>.json`, one
//!   projection per scenario (pools by fixture name). WP-16 changes the maths: regenerate them with
//!   `ARBX_BLESS=1 cargo test --release --lib scenarios` and review the diff. The structural expectations (what is never
//!   priced, which reasons, which counters) are asserted in the code and do not change with the maths.
mod digest_points;
mod exec_replay;
mod harness;
mod s1_torn_reads;
mod s2_failed_sells;
mod s3_failed_arb;
mod s4_skew;
mod s5_bolt;
mod s6_lookup_tables;
mod s7_warmup;
mod s8_forks;
mod s9_inflight;
mod s10_rent;
mod s11_bands;
mod synth;

use crate::config::Config;
use crate::engine::{self, Engine, EngineInit, EngineKnobs};
use crate::feeds::{src as asrc, Arrival, Event, InputKind, RawTx};
use crate::pools::{self, Registry, CLOCK_SYSVAR, PUMP_FEE_CONFIG};
use crate::rec::accounts::{self, AcctRec, AcctUpdate, RoleOf, Roles};
use crate::rec::journal::Journal;
use crate::rec::{self, Rec};
use crate::store::{Acct, Store};
use crate::tx::{b58, Ix, Pk, Tx};
use crate::venues::legacy::{cp, dammv2};
use crate::venues::{dlmm, PoolMeta, Venue};
use rustc_hash::FxHashMap as HashMap;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::sync::{Arc, OnceLock};

pub(crate) const MS: u64 = 1_000_000;
pub(crate) const US: u64 = 1_000;
/// the scenarios' first engine time (2026-10-04)
pub(crate) const T0: u64 = 1_791_000_000_000_000_000;
pub(crate) const SOL: u64 = 1_000_000_000;

// ------------------------------------------------------------------ fixtures

/// One captured account
pub(crate) struct Fix { pub key: Pk, pub what: String, pub owner: Pk, pub lamports: u64, pub data: Vec<u8> }

pub(crate) struct Fixtures {
    pub accounts: Vec<Fix>,
    by_key: HashMap<Pk, usize>,
    /// (pair, name, venue, pool)
    pub pools: Vec<(String, String, Venue, Pk)>,
    /// the context slot every account was read at
    pub slot: u64,
}

fn pk(s: &str) -> Pk { crate::tx::pk(s) }

/// testdata/scenarios/accounts.json, read once, every account's sha256 checked
pub(crate) fn fixtures() -> &'static Fixtures {
    static F: OnceLock<Fixtures> = OnceLock::new();
    F.get_or_init(|| {
        use base64::Engine as _;
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/scenarios/accounts.json");
        let v: Value = serde_json::from_slice(&std::fs::read(&path).expect("testdata/scenarios/accounts.json")).expect("accounts.json is JSON");
        assert_eq!(v["schema"], "arbx.fixture.scenario-accounts/1");
        let mut f = Fixtures { accounts: vec![], by_key: HashMap::default(), pools: vec![], slot: 0 };
        for a in v["accounts"].as_array().unwrap() {
            let data = base64::engine::general_purpose::STANDARD.decode(a["data"].as_str().unwrap()).unwrap();
            assert_eq!(crate::provenance::sha256_hex(&data), a["sha256"].as_str().unwrap(), "{}: the fixture's bytes changed", a["what"]);
            f.slot = f.slot.max(a["slot"].as_u64().unwrap());
            f.by_key.insert(pk(a["pubkey"].as_str().unwrap()), f.accounts.len());
            f.accounts.push(Fix { key: pk(a["pubkey"].as_str().unwrap()), what: a["what"].as_str().unwrap().into(), owner: pk(a["owner"].as_str().unwrap()),
                lamports: a["lamports"].as_u64().unwrap(), data });
        }
        for p in v["pools"].as_array().unwrap() {
            f.pools.push((p["pair"].as_str().unwrap().into(), p["name"].as_str().unwrap().into(), Venue::parse(p["venue"].as_str().unwrap()).unwrap(),
                pk(p["pool"].as_str().unwrap())));
        }
        let g = pump_global_config(f.slot);
        f.by_key.insert(g.key, f.accounts.len());
        f.accounts.push(g);
        f
    })
}

/// ---- WP-16 merge. PumpSwap's GlobalConfig, a part of every PumpSwap pool since WP-16 (arbx-sizing reads its disable
/// flags and creator-fee switch; the state stream follows it): accounts.json, captured before WP-16, does not hold it.
/// Its real bytes come from two of WP-16's own captures (testdata/venue-parity, read from mainnet by the venue
/// harness), one before and one after the scenarios' capture slot: identical, so the account did not change in between
fn pump_global_config(slot: u64) -> Fix {
    use base64::Engine as _;
    const SHA256: &str = "a698009a419d0b8c56ff257626d15cba305c4989a602fa86e65ca252b2c200f4";
    let key = *crate::pools::PUMP_GLOBAL_CONFIG;
    let read = |file: &str| -> (u64, Pk, u64, Vec<u8>) {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/venue-parity/pools").join(file);
        let v: Value = serde_json::from_slice(&std::fs::read(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()))).unwrap();
        let a = v["accounts"].as_array().unwrap().iter().find(|a| pk(a["pubkey"].as_str().unwrap()) == key).expect("the GlobalConfig in the capture");
        let lamports: u64 = a["lamports"].as_str().map_or_else(|| a["lamports"].as_u64(), |x| x.parse().ok()).unwrap();
        (v["slot"].as_u64().unwrap(), pk(a["owner"].as_str().unwrap()), lamports, base64::engine::general_purpose::STANDARD.decode(a["data"].as_str().unwrap()).unwrap())
    };
    let before = read("PumpSwap-CyJwKnLiiY4fmiwqMCSWFSHxo7T9Ubshgs2uRAuJCrk5.json");
    let after = read("PumpSwap-9qKxzRejsV6Bp2zkefXWCbGvg61c3hHei7ShXJ4FythA.json");
    assert!(before.0 < slot && slot < after.0, "the two captures ({}, {}) bracket the scenarios' slot {slot}", before.0, after.0);
    assert_eq!(before, (before.0, after.1, after.2, after.3.clone()), "the GlobalConfig is the same before and after the scenarios' capture");
    assert_eq!(crate::provenance::sha256_hex(&after.3), SHA256, "the GlobalConfig's bytes changed");
    Fix { key, what: "pump_global_config".into(), owner: after.1, lamports: after.2, data: after.3 }
}

impl Fixtures {
    pub fn get(&self, k: &Pk) -> Option<&Fix> { self.by_key.get(k).map(|i| &self.accounts[*i]) }
    /// a pool by its capture name ("usdc.pump")
    pub fn pool(&self, name: &str) -> (Venue, Pk) {
        let (pair, n) = name.split_once('.').unwrap();
        self.pools.iter().find(|p| p.0 == pair && p.1 == n).map(|p| (p.2, p.3)).unwrap_or_else(|| panic!("no fixture pool {name}"))
    }
    /// a fixture account's readable name ("usdc.pump" for a pool, "usdc.pump.vault0", "mint", ...)
    pub fn name_of(&self, k: &Pk) -> Option<String> { self.get(k).map(|a| a.what.strip_suffix(".pool").unwrap_or(&a.what).to_string()) }
}

/// A registry of the named fixture pools, booted by the real `pools::boot` from the fixture bytes (a local mock RPC
/// serves them): the metadata a run derives from chain (vaults, mints, token programs, extras, flags)
pub(crate) fn boot_registry(names: &[&str]) -> Registry {
    let f = fixtures();
    let mock = crate::rpc::mock::MockRpc::start();
    {
        let mut m = mock.accounts.lock().unwrap();
        for a in &f.accounts { m.insert(a.key, (a.data.clone(), a.owner, a.lamports)); }
    }
    mock.slot.store(f.slot, std::sync::atomic::Ordering::Relaxed);
    let rpc = crate::rpc::Rpc::race(vec![crate::rpc::Endpoint { name: "mock".into(), url: mock.url.clone(), bearer: None }]);
    let cands: Vec<(Venue, Pk)> = names.iter().map(|n| f.pool(n)).collect();
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let (reg, drops) = rt.block_on(pools::boot(&rpc, &cands, Default::default(), cands.iter().map(|c| c.1).collect())).expect("pools::boot on the fixtures");
    assert_eq!(reg.pools.len(), names.len(), "every fixture pool booted: {}; dropped {}", reg.summary(), pools::drops_json(&drops));
    reg
}

// ------------------------------------------------------------------ account bytes (synthetic mutations)

pub(crate) fn put_u64(d: &mut [u8], o: usize, x: u64) { d[o..o + 8].copy_from_slice(&x.to_le_bytes()); }
pub(crate) fn get_u64(d: &[u8], o: usize) -> u64 { u64::from_le_bytes(d[o..o + 8].try_into().unwrap()) }
/// an SPL / Token-2022 token account's amount
pub(crate) fn token_amount(d: &[u8]) -> u64 { get_u64(d, 64) }
pub(crate) fn with_amount(d: &[u8], amount: u64) -> Vec<u8> { let mut v = d.to_vec(); put_u64(&mut v, 64, amount); v }
/// the Clock sysvar at `slot` (slot @0, unix_timestamp @32)
pub(crate) fn clock_at(d: &[u8], slot: u64, unix: i64) -> Vec<u8> { let mut v = d.to_vec(); put_u64(&mut v, 0, slot); v[32..40].copy_from_slice(&unix.to_le_bytes()); v }

// ------------------------------------------------------------------ the run

/// One scenario's run: an offline engine driven as `arbx run` drives it, recording into its own directory
pub(crate) struct Rig {
    pub name: &'static str,
    pub dir: PathBuf,
    pub rec: Rec,
    pub ar: Arc<AcctRec>,
    pub e: Engine,
    pub reg: Arc<Registry>,
    pub cfg: Config,
    /// the chain as it is now: every followed account's bytes (the fixtures, then each write)
    pub chain: HashMap<Pk, Vec<u8>>,
    /// the boot's slot (the fixtures' context slot unless the scenario chose another)
    pub s0: u64,
    /// the Clock's unix time at `s0`
    pub unix0: i64,
    wv: u64,
    /// readable names of the scenario's transactions (for the expected projections)
    pub sig_names: HashMap<[u8; 64], String>,
    /// ---- WP-09 (the executor replay): the run's SendGate (its executor reads it; `Setup::exec`) and LeaderBook
    pub gate: Arc<crate::control::SendGate>,
    pub book: Arc<crate::leaders::LeaderBook>,
    /// keep the run directory (`ARBX_KEEP_SCENARIOS`), or it was handed to the scenario's `Done`
    keep: bool,
    handed_over: bool,
}

/// ---- WP-09 (review WP-09 "For the WP-05 merge" item 9). A real executor in the run (WP-05: every `arbx run` builds
/// one), as `arbx run` builds it: `Exec::assemble` on the boot's lookup tables, PumpSwap GlobalConfig and held tokens
/// (the GlobalConfig decoded from the fixture's account, as the boot decodes it; the fixtures hold no lookup table: one
/// of every account the fixture pools' legs name, as Stage 0's `[exec] alts` hold the venues' common accounts), the run's SendGate, a LeaderBook that knows the
/// test leaders' kinds, the engine's health, the crowding map with WP-00's static list; its exec_init record journaled
/// after engine_init. No RPC endpoint, no send path, no key (a dry run's throwaway key aside)
pub(crate) struct ExecSetup<'a> {
    pub mode: crate::exec::Mode,
    /// the wallet holds an account for every token of the registry (else WSOL only: WP-06 creates the mid token's account
    /// and closes it in the same transaction, rent-neutral)
    pub hold_tokens: bool,
    /// WP-06: the wallet's PumpSwap user volume accumulator exists (the boot read; else PumpSwap buys are `uva_missing`)
    pub uva: bool,
    /// WP-00's crowded-pools list, by fixture pool name
    pub crowded: &'a [&'a str],
    /// the SendGate starts shadow for the whole segment (`mode_shadow`, as `arbx run` without `--live` starts), else live
    /// (a test moves it)
    pub sticky_shadow: bool,
}

impl Default for ExecSetup<'_> {
    fn default() -> Self { ExecSetup { mode: crate::exec::Mode::Shadow, hold_tokens: true, uva: true, crowded: &[], sticky_shadow: true } }
}

/// the test leaders: two Jito validators and one of another kind (the LeaderBook's list, `Rig::new`)
pub(crate) const LEADER_JITO: Pk = [0xa7; 32];
pub(crate) const LEADER_JITO2: Pk = [0xa9; 32];
pub(crate) const LEADER_OTHER: Pk = [0xa8; 32];

/// A lookup table holding every account the registry pools' legs name (both directions, every followed DLMM bin array;
/// the payer aside), as the boot reads one of `[exec] alts`
fn fixture_alt(reg: &Registry, chain: &HashMap<Pk, Vec<u8>>, store: &Store, payer: Pk, pump: &crate::build::PumpGlobal) -> (Pk, Vec<Pk>) {
    let mut keys: Vec<Pk> = Vec::new();
    let mut add = |k: Pk| if k != payer && !keys.contains(&k) { keys.push(k); };
    for m in &reg.pools {
        let mint = if m.t0 == *crate::venues::WSOL { m.t1 } else { m.t0 };
        let arrays: Vec<(i64, Pk)> = store.dlmm_arrays.get(&m.pool).cloned().unwrap_or_default();
        for a in &arrays { add(a.1); }
        let live: Vec<i64> = arrays.iter().map(|a| a.0).collect();
        for (tin, tout) in [(*crate::venues::WSOL, mint), (mint, *crate::venues::WSOL)] {
            let leg = crate::build::leg(&crate::build::LegIn { m, pool: &chain[&m.pool], tin, tout, amount_in: SOL, payer, pump: Some(pump), dlmm_live: &live, dlmm_end: None, dlmm_ext: None });
            if let Ok(l) = leg { add(l.out); for a in &l.accounts { add(a.key); } }
        }
    }
    keys.truncate(256);
    ([0xa1; 32], keys)
}

/// What a scenario changes in the Stage-0 config (exact text replacements of deploy/arbx-stage0.toml) and in the boot
pub(crate) struct Setup<'a> {
    pub pools: &'a [&'a str],
    pub config: &'a [(&'a str, &'a str)],
    /// the boot's slot (default: the fixtures')
    pub s0: Option<u64>,
    /// accounts left out of the boot snapshot (S7: a vault the node does not have)
    pub omit: &'a [Pk],
    /// the recorder's rotation (`[record] rotate_mb`; default: the config's)
    pub rotate_mb: Option<f64>,
    /// engine_init says the run had an executor (the engine itself has none: its decisions are `no_executor`)
    pub executor: bool,
    /// ---- WP-09: a real executor in the run (`ExecSetup`)
    pub exec: Option<ExecSetup<'a>>,
    /// ---- WP-06: the state stream follows the wallet (`[state] watch_wallet`, as `arbx run`): its account, its token
    /// accounts and its PumpSwap user volume accumulator, with the ones named here in the boot snapshot
    pub wallet: Option<WalletSetup<'a>>,
}

/// The wallet as the boot snapshot reads it (WP-06): the tokens it holds an account for (by fixture pool name: that pool's
/// non-SOL token; WSOL always), whether its PumpSwap user volume accumulator exists
#[derive(Clone, Copy)]
pub(crate) struct WalletSetup<'a> { pub holds: &'a [&'a str], pub uva: bool, pub lamports: u64 }

/// an initialized SPL token account of `mint` owned by `owner` holding `amount` (WP-06 reads it as held)
pub(crate) fn token_account(mint: &Pk, owner: &Pk, amount: u64) -> Vec<u8> {
    let mut d = vec![0u8; 165];
    d[..32].copy_from_slice(mint);
    d[32..64].copy_from_slice(owner);
    d[64..72].copy_from_slice(&amount.to_le_bytes());
    d[108] = 1;
    d
}

impl Default for Setup<'_> {
    fn default() -> Self { Setup { pools: &[], config: &[], s0: None, omit: &[], rotate_mb: None, executor: false, exec: None, wallet: None } }
}

pub(crate) fn nop() -> impl FnMut(&str) { |_: &str| {} }

/// the Stage-0 config with its `/root/arbx/...` data paths read from this checkout (the CU table)
pub(crate) fn scenario_paths(cfg: &Config) -> Config {
    let mut c = cfg.clone();
    if let Some(rel) = c.builder.cu_table.strip_prefix("/root/arbx/") { c.builder.cu_table = Path::new(env!("CARGO_MANIFEST_DIR")).join(rel).display().to_string(); }
    c
}

impl Rig {
    /// Boot a scenario as `arbx run` boots a segment (see the module doc)
    pub fn new(name: &'static str, s: Setup) -> Rig {
        let f = fixtures();
        let reg = boot_registry(s.pools);
        let src = std::fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join("deploy/arbx-stage0.toml")).unwrap();
        let mut text = src.clone();
        for (a, b) in s.config { assert_eq!(text.matches(a).count(), 1, "config replacement {a:?}"); text = text.replacen(a, b, 1); }
        let cfg = Config::parse(&text).expect("the scenario's config");
        let dir = std::env::temp_dir().join(format!("arbx-scenario-{name}-{}-{}", std::process::id(), crate::feeds::clock::real_ns()));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("config.toml"), &text).unwrap();
        let rcfg = crate::config::RecordCfg { rotate_mb: s.rotate_mb.unwrap_or(crate::config::RecordCfg::default().rotate_mb), ..Default::default() };
        let rec = rec::start(rec::Opts { dir: dir.clone(), run: name.into(), producer: "scenario".into(), cfg: rcfg, feeds: vec!["shred".into(), "tx".into()],
            monitor: false, echo: Some(Box::new(std::io::sink())) }).unwrap();
        // the state stream's base watch list and roles, as `arbx run` builds them (the Clock; no programdata; the wallet
        // when the setup follows it, WP-06)
        let payer = crate::tx::pk(&cfg.wallet);
        let extra = reg.extra_watch(true, &[], s.wallet.as_ref().map(|_| &payer));
        let mut role_list = reg.watch_roles();
        role_list.extend(extra.iter().copied());
        let roles = Arc::new(Roles::new(role_list));
        let ar = AcctRec::new(rec.clone(), roles.clone());
        let mut base = reg.static_accounts();
        for (k, _) in &extra { if !base.contains(k) { base.push(*k); } }
        let s0 = s.s0.unwrap_or(f.slot);
        let mut chain: HashMap<Pk, Vec<u8>> = f.accounts.iter().map(|a| (a.key, a.data.clone())).collect();
        let unix0 = i64::from_le_bytes(chain[&*CLOCK_SYSVAR][32..40].try_into().unwrap());
        chain.insert(*CLOCK_SYSVAR, clock_at(&chain[&*CLOCK_SYSVAR], s0, unix0));
        // ---- WP-06: the wallet's accounts the boot snapshot reads (a system account: no data; its WSOL account; the token
        // accounts it holds; its PumpSwap user volume accumulator)
        let mut wallet_lamports: HashMap<Pk, u64> = HashMap::default();
        if let Some(w) = &s.wallet {
            chain.insert(payer, vec![]);
            wallet_lamports.insert(payer, w.lamports);
            let wsol = crate::build::ata_of(&payer, &crate::venues::WSOL, &crate::pda::TOKEN_PROGRAM);
            chain.insert(wsol, token_account(&crate::venues::WSOL, &payer, 5 * SOL));
            for n in w.holds {
                let m = reg.pools[reg.by_pool[&f.pool(n).1]].clone();
                let (mint, prog) = if m.t0 == *crate::venues::WSOL { (m.t1, m.t1_prog) } else { (m.t0, m.t0_prog) };
                chain.insert(crate::build::ata_of(&payer, &mint, &prog), token_account(&mint, &payer, 0));
            }
            if w.uva { chain.insert(crate::build::pump_uva(&payer), vec![7u8; 64]); }
        }
        // the boot snapshot: accounts.bin (src rpc_boot) and the journal's ACCOUNT records with t_engine 0
        let j = Journal::new(rec.clone());
        let mut store = Store::default();
        let boot_one = |store: &mut Store, k: Pk, chain: &HashMap<Pk, Vec<u8>>| {
            if s.omit.contains(&k) { return; }
            let Some(d) = chain.get(&k) else { return };
            let (fx, slot) = (f.get(&k), s0);
            let data: Arc<[u8]> = d.clone().into();
            let lamports = fx.map_or_else(|| wallet_lamports.get(&k).copied().unwrap_or(1), |x| x.lamports);
            let aseq = ar.record(&AcctUpdate { pubkey: k, slot, write_version: 0, t_recv: T0 - 1_000 * MS, src: asrc::RPC_BOOT, is_startup: false, txn: None,
                lamports, owner: fx.map_or([0; 32], |x| x.owner), data: &data, bank_id: None });
            j.account(0, aseq, store.is_stale(&k, slot, asrc::RPC_BOOT, 0, aseq));
            store.apply(k, Acct::rpc(data, slot, T0 - 1_000 * MS, aseq, asrc::RPC_BOOT).with_lamports(lamports));
        };
        ar.mark(accounts::MARK_BOOT_BEGIN, &[]);
        for k in &base { boot_one(&mut store, *k, &chain); }
        engine::initial_dlmm_arrays(&reg, &mut store);
        let arrays: Vec<(Pk, u32)> = store.dlmm_arrays.iter().flat_map(|(p, l)| { let pi = reg.by_pool[p] as u32; l.iter().map(move |(_, k)| (*k, pi)) }).collect();
        roles.add(arrays.iter().map(|(k, pi)| (*k, RoleOf { role: accounts::role::DLMM_BIN_ARRAY, pool_index: *pi })).collect::<Vec<_>>());
        let mut arrays = arrays;
        arrays.sort();
        for (k, _) in &arrays { boot_one(&mut store, *k, &chain); }
        ar.mark(accounts::MARK_BOOT_END, &[]);
        let reg = Arc::new(reg);
        crate::replay::write_pools_json(&dir, &reg, &base, &roles).unwrap();
        // the engine as `arbx run` builds it: the strategy, the knobs, the cheapest enabled send path's tip; its
        // engine_init record journaled before the first input
        let mut e = Engine::new_offline(reg.clone(), store, cfg.strategy.clone());
        e.set_rec(rec.clone());
        e.set_acct_rec(ar.clone());
        e.set_base_watch(base);
        let min_tip = cfg.sends.iter().filter(|s| s.enabled).map(|s| s.tip_lamports).min().unwrap_or(0);
        e.apply_init(&EngineInit { min_tip, strategy_sha256: engine::strategy_sha256(&cfg.strategy), executor: s.executor, signer_stats_file: String::new(),
            signer_stats_sha256: None, signer_stats: Default::default(), knobs: Some(EngineKnobs::from_cfg(&cfg)),
            // WP-06: the fee and CU model as `arbx run` builds it (the config's [tips], [bands] and CU table: the repo's copy)
            builder: Some(engine::BuilderModel::from_cfg(&scenario_paths(&cfg)).expect("the builder model")) }).unwrap();
        // ---- WP-09: the run's executor (`ExecSetup`), its gate and LeaderBook
        let gate = crate::control::SendGate::new();
        let book = crate::leaders::LeaderBook::new(Rec::off());
        book.set_list("kobe", &json!({ "validators": [{ "identity_account": b58(&LEADER_JITO), "running_jito": true }, { "identity_account": b58(&LEADER_JITO2),
            "running_jito": true }, { "identity_account": b58(&LEADER_OTHER), "running_jito": false }] }), T0).unwrap();
        if let Some(x) = &s.exec {
            if x.sticky_shadow { let _ = gate.shadow("mode_shadow", "no --live or --canary: nothing is sent", true); }
            let payer = crate::tx::pk(&cfg.wallet);
            let pump = crate::build::decode_pump_global(&chain[&*crate::pools::PUMP_GLOBAL_CONFIG]).expect("the fixture's GlobalConfig decodes");
            let alt = fixture_alt(&reg, &chain, &e.store, payer, &pump);
            let mut held: rustc_hash::FxHashSet<Pk> = [*crate::venues::WSOL].into_iter().collect();
            if x.hold_tokens { for m in &reg.pools { held.insert(m.t0); held.insert(m.t1); } }
            let key = (x.mode == crate::exec::Mode::DryRun).then(|| crate::exec::ephemeral_key().unwrap());
            let rt = crate::exec::offline_runtime();
            let _in = rt.enter();
            let mut ex = crate::exec::Exec::assemble(&cfg, crate::rpc::Rpc::race(vec![]), None, rec.clone(), crossbeam_channel::unbounded().0,
                vec!["shred".into(), "tx".into()], vec![alt], Some(pump), held, x.mode, key).expect("the run's executor");
            ex.set_gate(gate.clone());
            ex.set_leaders(book.clone());
            ex.set_health(e.health_flags());
            ex.set_uva(Some(x.uva));
            let b = &cfg.send_policy.crowding_buckets;
            e.set_crowding(crate::crowding::Activity::new(cfg.send_policy.crowding_window_h, [b[0], b[1]], x.crowded.iter().map(|n| f.pool(n).1).collect()));
            e.exec = Some(ex);
            e.gate = Some(gate.clone());
        }
        // (`Setup::executor`: the record says so, as a run with an executor writes it; this engine has none)
        let mut init = e.init().json();
        init["executor"] = json!(s.executor || e.exec.is_some());
        e.journal().input(0, InputKind::EngineInit, Arc::new(init));
        e.journal_exec_init();
        Rig { name, dir, rec, ar, e, reg, cfg, chain, s0, unix0, wv: 1_000, sig_names: HashMap::default(), gate, book,
            keep: std::env::var_os("ARBX_KEEP_SCENARIOS").is_some(), handed_over: false }
    }

    /// ---- WP-09. INPUT 1 `blockhash_head`: the WP-03b ring's confirmed head at `slot` (what the send checks age and a
    /// bundle is built on), as the chain-fetch service hands it to the engine
    pub fn blockhash(&mut self, slot: u64, t: u64) {
        let h = crate::provenance::sha256_hex(format!("scenario-blockhash:{slot}").as_bytes());
        let mut hash = [0u8; 32];
        for (i, b) in h.as_bytes().chunks(2).take(32).enumerate() { hash[i] = u8::from_str_radix(std::str::from_utf8(b).unwrap(), 16).unwrap(); }
        self.input(InputKind::BlockhashHead, json!({ "hash": b58(&hash), "slot": slot, "height": slot.saturating_sub(1_000_000), "src": "slotidx",
            "commitment": "confirmed", "t_ns": t }), t);
    }

    /// ---- WP-09. The leader schedule from `start` (INPUT 2 `leader_window`, as the LeaderBook's refresher hands it to the
    /// engine; the book holds the same slots)
    pub fn leaders(&mut self, start: u64, leaders: &[Pk], t: u64) {
        self.book.add_window(start, leaders);
        self.input(InputKind::LeaderWindow, json!({ "start": start, "leaders": leaders.iter().map(b58).collect::<Vec<_>>() }), t);
    }

    /// ---- WP-09. The decisions' opportunities (main lines with an `opp`)
    pub fn opportunities(&self) -> Vec<Value> { self.evaluations().into_iter().filter(|d| d["opp"].is_u64()).collect() }

    /// ---- WP-09. attempts.jsonl so far
    pub fn attempts(&self) -> Vec<Value> { self.rec.sync(); rec::read_jsonl(&self.dir, "attempts").unwrap_or_default() }

    pub fn meta(&self, name: &str) -> PoolMeta { let (_, p) = fixtures().pool(name); self.reg.pools[self.reg.by_pool[&p]].clone() }
    pub fn data(&self, k: &Pk) -> Vec<u8> { self.chain.get(k).cloned().unwrap_or_else(|| panic!("no chain account {}", b58(k))) }

    /// A state-stream update received at `t` (recorded in accounts.bin first, then handed to the engine 10 µs later)
    pub fn write(&mut self, key: Pk, data: Vec<u8>, slot: u64, txn: Option<[u8; 64]>, t: u64) -> u64 {
        self.wv += 1;
        let d: Arc<[u8]> = data.clone().into();
        let fx = fixtures().get(&key);
        let (lamports, owner) = (fx.map_or(1, |x| x.lamports), fx.map_or([0; 32], |x| x.owner));
        let aseq = self.ar.record(&AcctUpdate { pubkey: key, slot, write_version: self.wv, t_recv: t, src: asrc::GRPC, is_startup: false, txn, lamports, owner, data: &d,
            bank_id: None });
        self.chain.insert(key, data);
        self.e.step(Event::Account { slot, pubkey: key, owner, lamports, data: d, t, txn, write_version: self.wv, is_startup: false, src: asrc::GRPC, aseq,
            bank_id: None }, t + 10 * US, &mut nop());
        aseq
    }
    /// a slot status from the state stream (0 processed, 1 confirmed, 2 finalized, 6 dead)
    pub fn slot(&mut self, slot: u64, status: i32, parent: Option<u64>, t: u64) {
        self.e.step(Event::Slot { slot, status, t, parent, dead_error: None, bank_id: None }, t + 10 * US, &mut nop());
    }
    /// the Clock sysvar written at `slot` (400 ms a slot from `s0`)
    pub fn clock(&mut self, slot: u64, t: u64) {
        let unix = self.unix0 + (slot.saturating_sub(self.s0) * 400 / 1_000) as i64;
        let d = clock_at(&self.data(&CLOCK_SYSVAR), slot, unix);
        self.write(*CLOCK_SYSVAR, d, slot, None, t);
    }
    /// a new processed slot with its Clock
    pub fn tick(&mut self, slot: u64, t: u64) { self.slot(slot, 0, Some(slot - 1), t); self.clock(slot, t + 50 * US); }
    /// the timers, everything allowed (an idle wake-up of `Engine::run`)
    pub fn timers(&mut self, t: u64) { self.e.timers_at(t, engine::TIMER_ALL, &mut nop()); }
    pub fn tx(&mut self, a: Arrival) { let t = a.t_rx; self.e.step(Event::Tx(a), t + 10 * US, &mut nop()); }
    pub fn input(&mut self, kind: InputKind, data: Value, t: u64) { self.e.step(Event::Input { kind, data: Arc::new(data) }, t, &mut nop()); }

    /// The stream delivers (slot s0+1 and its Clock) and housekeeping finds Tier A complete: the warm-up gate opens
    pub fn make_ready(&mut self, t: u64) {
        let s = self.s0 + 1;
        self.tick(s, t);
        self.timers(t + 6 * MS);
        assert_eq!(self.e.shut(), crate::store_health::Shut::Ready, "{}: ready after Tier A is complete and the stream delivers", self.name);
    }

    /// a transaction signature with a readable name (the expected projections name it; the same label gives the same
    /// signature in every scenario, so a twin run can be compared line by line)
    pub fn sig(&mut self, label: &str) -> [u8; 64] {
        let h = crate::provenance::sha256_hex(format!("scenario:{label}").as_bytes());
        let mut s = [0u8; 64];
        for (i, b) in h.as_bytes().chunks(2).take(32).enumerate() { s[i] = u8::from_str_radix(std::str::from_utf8(b).unwrap(), 16).unwrap(); s[i + 32] = s[i] ^ 0x5a; }
        self.sig_names.insert(s, label.to_string());
        s
    }

    pub fn decisions(&self) -> Vec<Value> { self.rec.sync(); rec::read_jsonl(&self.dir, "decisions").unwrap_or_default() }
    /// replay this run's directory with the compare into `<dir>/<out>`
    pub fn replay_compare(&self, out: &str) -> crate::replay::Report {
        crate::replay::replay(&self.dir, &crate::replay::Opts { compare: true, out: Some(self.dir.join(out)), ..Default::default() })
            .unwrap_or_else(|e| panic!("{}: the replay refused its run: {e:#}", self.name))
    }
    pub fn commits(&self) -> Vec<Value> { self.rec.sync(); rec::read_jsonl(&self.dir, "commits").unwrap_or_default() }
    /// the decisions' main lines (follow-up lines left out)
    pub fn evaluations(&self) -> Vec<Value> { self.decisions().into_iter().filter(|d| d.get("routes").is_some()).collect() }

    /// End the run (as `Engine::run` ends: `finish`), close the recorder, then replay the run directory with the compare
    /// and check the replay gives the run's digests and identical decisions and commit groups. Returns the run's
    /// decisions and commits (read before the replay)
    pub fn finish_and_replay(mut self) -> Done {
        self.e.finish();
        let (digest, decision_digest) = (self.e.digest(), self.e.decision_digest());
        self.rec.close();
        let (decisions, commits) = (rec::read_jsonl(&self.dir, "decisions").unwrap_or_default(), rec::read_jsonl(&self.dir, "commits").unwrap_or_default());
        let r = self.replay_compare("replay");
        let diff = r.diff.clone().unwrap();
        assert!(r.ok, "{}: the replay differs from the run: {} {}", self.name, r.summary["not_whole"], serde_json::to_string_pretty(&diff).unwrap());
        assert_eq!((r.digest, r.decision_digest), (digest, decision_digest), "{}: run vs replay digests", self.name);
        let s = &diff["summary"];
        assert_eq!((s["missing_in_replay"].as_u64(), s["extra_in_replay"].as_u64(), s["differ"].as_u64()), (Some(0), Some(0), Some(0)), "{}", self.name);
        assert_eq!(s["compared"].as_u64(), Some(decisions.iter().filter(|d| d.get("routes").is_some()).count() as u64), "{}: every decision compared", self.name);
        assert_eq!(r.summary["accounts"]["missing"], json!(0));
        // review WP-09 #6: the run recorded its digests (Engine::finish) and the replay, run to the end, reproduced them
        assert_eq!((r.summary["digests"]["checked"].as_bool(), r.summary["digests"]["same"].as_bool()), (Some(true), Some(true)), "{}: {}", self.name,
            r.summary["digests"]);
        assert_eq!(r.summary["whole"], json!(true), "{}", self.name);
        // ---- WP-09: a run with an executor replays it (exec_init), attempt for attempt
        if self.e.exec.is_some() {
            assert_eq!((r.summary["executor"]["replayed"].as_bool(), s["executor_replayed"].as_bool()), (Some(true), Some(true)), "{}: {}", self.name, r.summary["executor"]);
            assert_eq!((s["attempts_differ"].as_u64(), s["attempts_missing_in_replay"].as_u64(), s["attempts_extra_in_replay"].as_u64()), (Some(0), Some(0), Some(0)), "{}", self.name);
            assert_eq!(s["attempts_compared"], s["attempts_run"], "{}: every attempt compared", self.name);
            // ---- WP-16 merge: the executor's expected profit is its decision's gross, the guard's quote delta (the sell
            // output minus the buy leg's debit), at the same size
            let best: HashMap<u64, &Value> = decisions.iter().filter(|d| d["opp"].is_u64())
                .map(|d| (d["decision"].as_u64().unwrap(), &d["routes"][d["best"].as_u64().unwrap() as usize])).collect();
            for a in rec::read_jsonl(&self.dir, "attempts").unwrap_or_default() {
                let x = &a["expected"];
                assert_eq!(x["gross"].as_i64(), Some(x["back"].as_i64().unwrap() - x["spent"].as_i64().unwrap()), "{}: {a}", self.name);
                assert!(x["spent"].as_u64().unwrap() <= a["size_lamports"].as_u64().unwrap(), "{}: {a}", self.name);
                let b = best[&a["decision"].as_u64().unwrap()];
                if b["size"] == a["size_lamports"] { assert_eq!(x["gross"], b["gross"], "{}: attempt {} vs its decision's route {b}", self.name, a["attempt"]); }
            }
        }
        self.handed_over = true;
        Done { name: self.name, dir: self.dir.clone(), decisions, commits, sig_names: std::mem::take(&mut self.sig_names), replay: r.summary, keep: self.keep }
    }
}

impl Drop for Rig {
    fn drop(&mut self) {
        self.rec.close();
        if !self.keep && !self.handed_over { let _ = std::fs::remove_dir_all(&self.dir); }
    }
}

/// A finished scenario: its run's records and its replay's summary
pub(crate) struct Done {
    pub name: &'static str,
    pub dir: PathBuf,
    pub decisions: Vec<Value>,
    pub commits: Vec<Value>,
    pub sig_names: HashMap<[u8; 64], String>,
    pub replay: Value,
    keep: bool,
}

impl Drop for Done {
    fn drop(&mut self) { if !self.keep { let _ = std::fs::remove_dir_all(&self.dir); } }
}

impl Done {
    pub fn evaluations(&self) -> Vec<&Value> { self.decisions.iter().filter(|d| d.get("routes").is_some()).collect() }

    /// The scenario's expected projection (testdata/scenarios/expected/<name>.json): the decisions with their routes'
    /// prices and reasons and the commit groups, pools and transactions by name. `ARBX_BLESS=1` writes it
    pub fn check_expected(&self) {
        let f = fixtures();
        let names: HashMap<String, String> = f.accounts.iter().map(|a| (b58(&a.key), f.name_of(&a.key).unwrap())).collect();
        let sigs: HashMap<String, String> = self.sig_names.iter().map(|(k, v)| (bs58::encode(k).into_string(), v.clone())).collect();
        let name = |v: &Value| -> Value { v.as_str().map_or(Value::Null, |s| json!(names.get(s).or(sigs.get(s)).cloned().unwrap_or_else(|| s.to_string()))) };
        let decisions: Vec<Value> = self.decisions.iter().map(|d| {
            if d.get("routes").is_none() {
                return json!({ "decision": d["decision"], "torn_suspect": d.get("torn_suspect"), "fork_priced": d.get("fork_priced"), "txn": name(&d["txn"]) });
            }
            json!({ "decision": d["decision"], "kind": d["kind"], "trigger": { "txn": name(&d["trigger"]["txn"]), "slot": d["trigger"]["slot"], "pool": name(&d["trigger"]["pool"]) },
                "w_src": d["w_src"], "verdict": d["verdict"], "reason": d["reason"], "best": d["best"], "band": d["band"], "parts_skew_slots": d["parts_skew_slots"],
                "routes": d["routes"].as_array().unwrap().iter().map(|r| json!({ "buy": name(&r["buy"]), "sell": name(&r["sell"]), "reason": r["reason"],
                    "size": r["size"], "gross": r["gross"], "net": r["net"], "cu": r["cu"], "crossed": r["crossed"] })).collect::<Vec<_>>() })
        }).collect();
        let commits: Vec<Value> = self.commits.iter().map(|c| json!({ "group": c["group"], "txn": name(&c["txn"]), "slot": c["slot"], "w_src": c["w_src"],
            "outcome": c["outcome"], "resolved_by": c["resolved_by"], "late": c.get("late"), "members": c["w_seen"].as_array().map(|v| v.len()),
            "pools": c["pools"].as_array().map(|v| v.iter().map(name).collect::<Vec<_>>()), "evaluated": c["evaluated"] })).collect();
        let got = json!({ "scenario": self.name, "_doc": "WP-09 scenario projection (src/scenarios/mod.rs `Done::check_expected`): pricing-dependent values. Regenerate with ARBX_BLESS=1 cargo test --release --lib scenarios, after review",
            "decisions": decisions, "commits": commits });
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/scenarios/expected").join(format!("{}.json", self.name));
        if std::env::var_os("ARBX_BLESS").is_some() {
            std::fs::create_dir_all(path.parent().unwrap()).unwrap();
            std::fs::write(&path, serde_json::to_string_pretty(&got).unwrap() + "\n").unwrap();
            return;
        }
        let want: Value = serde_json::from_slice(&std::fs::read(&path).unwrap_or_else(|_| panic!("{}: no expected file {} (ARBX_BLESS=1 writes it)", self.name, path.display())))
            .unwrap();
        if want != got {
            let (w, g) = (serde_json::to_string_pretty(&want).unwrap(), serde_json::to_string_pretty(&got).unwrap());
            let first = w.lines().zip(g.lines()).position(|(a, b)| a != b).unwrap_or(w.lines().count().min(g.lines().count()));
            let ctx = |s: &str| s.lines().skip(first.saturating_sub(3)).take(8).collect::<Vec<_>>().join("\n");
            panic!("{}: differs from {} at line {first}:\n--- expected\n{}\n--- got\n{}\n(if the venue maths changed on purpose: ARBX_BLESS=1 cargo test --release --lib scenarios, then review the diff)",
                self.name, path.display(), ctx(&w), ctx(&g));
        }
    }
}

// ------------------------------------------------------------------ transactions

/// A transaction as a shred feed delivers it (unexecuted: its write set W(T) is a hint): `writable` accounts, then
/// read-only `ro`, with `ixs` over (writable ++ ro) indices; its wire bytes are what the journal keeps
pub(crate) fn shred_tx(sig: [u8; 64], signer: Pk, writable: &[Pk], ro: &[Pk], ixs: Vec<Ix>, slot: u64, t: u64) -> Arrival {
    let mut keys = vec![signer];
    keys.extend(writable.iter().copied());
    keys.extend(ro.iter().copied());
    let tx = Tx { sig, num_signers: 1, num_ro_signed: 0, num_ro_unsigned: ro.len() as u8, keys, ixs, ..Default::default() };
    let w = crate::tx::to_wire(&tx).expect("encodable");
    let (tx, _) = crate::tx::parse_wire(&w).expect("decodable");
    Arrival { feed: 0, slot, t_rx: t, t_decoded: t, executed: None, tx, poh: None, raw: RawTx::Wire(w.into()) }
}

/// the same transaction from the executed stream (`ok`: it succeeded), later
pub(crate) fn executed_copy(a: &Arrival, ok: bool, t: u64) -> Arrival {
    Arrival { feed: 1, slot: a.slot, t_rx: t, t_decoded: t, executed: Some(ok), tx: a.tx.clone(), poh: None, raw: a.raw.clone() }
}

/// index of `k` in a transaction's (writable ++ ro) list (+1 for the signer)
pub(crate) fn ix_of(k: &Pk, signer: &Pk, writable: &[Pk], ro: &[Pk]) -> u8 {
    if k == signer { return 0; }
    (writable.iter().chain(ro).position(|x| x == k).unwrap_or_else(|| panic!("{} not in the transaction", b58(k))) + 1) as u8
}

/// A PumpSwap `sell` of `amount` base tokens on pool `m` by `user` (instruction data: discriminator, amount,
/// min_quote_out; accounts [pool, user, global, base_mint, quote_mint, ...]: what `cp::decode_pending` reads)
pub(crate) fn pump_sell(m: &PoolMeta, user: &Pk, amount: u64, min_out: u64, writable: &[Pk], ro: &[Pk]) -> Ix {
    let mut data = vec![0x33, 0xe6, 0x85, 0xa4, 0x01, 0x7f, 0x83, 0xad];
    data.extend(amount.to_le_bytes());
    data.extend(min_out.to_le_bytes());
    let accts = [m.pool, *user, [0x91; 32], m.t0, m.t1, m.vault0, m.vault1];
    Ix { program: ix_of(&*crate::venues::PUMPSWAP, user, writable, ro), accounts: accts.iter().map(|k| ix_of(k, user, writable, ro)).collect(), data }
}

/// A Raydium AMM v4 `swap_base_in` (v2, tag 16) of `amount` on pool `m` by `user` (zfo: token0 in)
pub(crate) fn ammv4_swap(m: &PoolMeta, user: &Pk, amount: u64, zfo: bool, writable: &[Pk], ro: &[Pk]) -> Ix {
    let (tin, tout) = if zfo { (m.t0, m.t1) } else { (m.t1, m.t0) };
    let (uin, uout) = (crate::pda::ata(user, &tin, &m.t0_prog), crate::pda::ata(user, &tout, &m.t1_prog));
    let mut data = vec![16u8];
    data.extend(amount.to_le_bytes());
    data.extend(0u64.to_le_bytes());
    // [0] token program [1] amm [2] authority [3] vault0 [4] vault1 [5] user in [6] user out [7] user
    let accts = [*crate::pda::TOKEN_PROGRAM, m.pool, [0x92; 32], m.vault0, m.vault1, uin, uout, *user];
    Ix { program: ix_of(&*crate::venues::RAYAMMV4, user, writable, ro), accounts: accts.iter().map(|k| ix_of(k, user, writable, ro)).collect(), data }
}

// ------------------------------------------------------------------ swaps on the chain's bytes (the venues' own maths)

/// A swap of `amount_in` on pool `m` at the chain's current bytes: the accounts it writes, with their new bytes (the
/// venue's own post-trade model: CP effective reserves, the DLMM bins walked, the DAMM v2 price) and the output. The
/// model is the engine's maths before WP-16 (`venues::legacy`, kept for tests): the scenarios' third-party trades, and
/// so their inputs, are byte for byte what they were before the merge; the engine prices them with arbx-sizing
pub(crate) fn swap(chain: &HashMap<Pk, Vec<u8>>, m: &PoolMeta, zfo: bool, amount_in: u64, slot: u64, unix: i64) -> (Vec<(Pk, Vec<u8>)>, u64) {
    try_swap(chain, m, zfo, amount_in, slot, unix).unwrap_or_else(|| panic!("{}: a swap of {amount_in} (zfo {zfo}) does not quote", nm(&m.pool)))
}

/// [`swap`], or None when the venue refuses it (no liquidity, a bin array not held, a size past the reserves)
pub(crate) fn try_swap(chain: &HashMap<Pk, Vec<u8>>, m: &PoolMeta, zfo: bool, amount_in: u64, slot: u64, unix: i64) -> Option<(Vec<(Pk, Vec<u8>)>, u64)> {
    Some(match m.venue {
        Venue::Dlmm => {
            let pair = chain[&m.pool].clone();
            let active = i32::from_le_bytes(pair[76..80].try_into().unwrap());
            let c = dlmm::array_index(active);
            let keys: Vec<(i64, Pk)> = (c - pools::DLMM_ARRAY_SPAN..=c + pools::DLMM_ARRAY_SPAN).map(|i| (i, dlmm::bin_array_pda(&m.pool, i))).collect();
            let held: HashMap<i64, &[u8]> = keys.iter().filter_map(|(i, k)| chain.get(k).map(|d| (*i, &d[..]))).collect();
            let q = crate::venues::legacy::dlmm::quote(&crate::venues::legacy::dlmm::View { pair: &pair, arrays: &held, over: None }, zfo, amount_in, unix, true).ok()?;
            let mut arrays: HashMap<i64, Vec<u8>> = HashMap::default();
            for (bin, x, y) in &q.changed {
                let i = dlmm::array_index(*bin);
                let a = arrays.entry(i).or_insert_with(|| held[&i].to_vec());
                let o = 56 + (*bin as i64 - i * dlmm::BINS_PER_ARRAY as i64) as usize * 144;
                put_u64(a, o, *x);
                put_u64(a, o + 8, *y);
            }
            let mut p = pair;
            p[76..80].copy_from_slice(&q.end_active.to_le_bytes());
            let (va, v_ref, idx_ref, ts) = q.vol;
            p[40..44].copy_from_slice(&(va as u32).to_le_bytes());
            p[44..48].copy_from_slice(&(v_ref as u32).to_le_bytes());
            p[48..52].copy_from_slice(&idx_ref.to_le_bytes());
            p[56..64].copy_from_slice(&ts.to_le_bytes());
            let mut out = vec![(m.pool, p)];
            let mut ix: Vec<i64> = arrays.keys().copied().collect();
            ix.sort();
            for i in ix { out.push((keys.iter().find(|k| k.0 == i).unwrap().1, arrays.remove(&i).unwrap())); }
            (out, q.out)
        }
        Venue::DammV2 => {
            let d = chain[&m.pool].clone();
            let mut p = dammv2::decode(&d)?;
            if m.flag { p.transfer_fee_known_zero = true; }
            let (out, np) = dammv2::swap_exact_in(&p, zfo, amount_in, slot, unix).ok()?;
            // dammv2.rs `off`: sqrt_price @456, token_a_amount @680, token_b_amount @688
            let mut n = d;
            n[456..472].copy_from_slice(&np.sqrt_price.to_le_bytes());
            put_u64(&mut n, 680, np.token_a_amount);
            put_u64(&mut n, 688, np.token_b_amount);
            (vec![(m.pool, n)], out)
        }
        _ => {
            let pump = chain.get(&*PUMP_FEE_CONFIG).and_then(|d| cp::decode_pump_fee_cfg(d)).map(Arc::new);
            let extra: Vec<&[u8]> = m.extra.iter().map(|k| &chain[k][..]).collect();
            let a = cp::Accounts { pool: &chain[&m.pool], vault0: &chain[&m.vault0], vault1: &chain[&m.vault1], extra };
            let s = cp::snapshot(m, &a, slot, unix, pump.as_ref()).ok()?;
            let q = cp::quote(&s, zfo, amount_in)?;
            let (v0, v1) = (token_amount(&chain[&m.vault0]), token_amount(&chain[&m.vault1]));
            let n0 = (v0 as i128 + q.r0 as i128 - s.r0 as i128) as u64;
            let n1 = (v1 as i128 + q.r1 as i128 - s.r1 as i128) as u64;
            (vec![(m.vault0, with_amount(&chain[&m.vault0], n0)), (m.vault1, with_amount(&chain[&m.vault1], n1))], q.out)
        }
    })
}

/// whether a pool's token 0 is WSOL (a swap with SOL in is then `zero_for_one`)
pub(crate) fn sol_is_t0(m: &PoolMeta) -> bool { m.t0 == *crate::venues::WSOL }

/// the readable name of an account in the fixtures, else base58
pub(crate) fn nm(k: &Pk) -> String { fixtures().name_of(k).unwrap_or_else(|| b58(k)) }

/// every route's reason of a decision line
pub(crate) fn reasons(d: &Value) -> Vec<String> { d["routes"].as_array().unwrap().iter().map(|r| r["reason"].as_str().unwrap().to_string()).collect() }

/// the decision's routes touching pool `p` (by base58)
pub(crate) fn routes_through<'a>(d: &'a Value, p: &Pk) -> Vec<&'a Value> {
    let s = b58(p);
    d["routes"].as_array().unwrap().iter().filter(|r| r["buy"] == json!(s) || r["sell"] == json!(s)).collect()
}

/// The fixtures themselves: every pool boots, and the real layouts quote (the scenarios' starting state)
#[test]
fn the_fixture_pools_boot_and_quote() {
    let f = fixtures();
    let names = ["usdc.pump", "usdc.cpmm", "usdc.ammv4", "usdc.dlmm", "usdc.damm"];
    let reg = boot_registry(&names);
    assert_eq!(reg.pairs.len(), 1, "one USDC/SOL pair: {}", reg.summary());
    let mut r = Rig::new("fixtures", Setup { pools: &names, ..Default::default() });
    r.make_ready(T0);
    for n in names {
        let m = r.meta(n);
        let (v, _) = f.pool(n);
        assert_eq!(m.venue, v);
    }
    // WP-16: each pool quotes in both directions on the engine's own path (arbx-sizing's legs, as a decision parses them):
    // every ordered pair of the five, at 0.01 SOL
    let usdc = { let m = r.meta(names[0]); if m.t0 == *crate::venues::WSOL { m.t1 } else { m.t0 } };
    for b in names {
        for s in names.iter().filter(|s| **s != b) {
            let q = r.e.quote_route(&r.meta(b).pool, &r.meta(s).pool, &usdc, SOL / 100).unwrap_or_else(|e| panic!("{b} -> {s}: {e}"));
            assert!(q.mid > 0 && q.back > 0 && q.spent > 0 && q.spent <= SOL / 100, "{b} -> {s}: {}", q.gross);
        }
    }
    let bolt = boot_registry(&["bolt.pump", "bolt.dlmm"]);
    assert!(bolt.pools.iter().any(|m| m.venue == Venue::PumpSwap && m.t0_prog == pk("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")), "the bolt token is Token-2022");
    // WP-06: the bitmap extension is read from the store per send (the boot check is gone): the fixtures hold the USDC
    // pair's and not the bolt pair's, and the engine's store as the boot snapshot left it says the same
    let ext_of = |reg: &Registry| reg.pools.iter().find(|m| m.venue == Venue::Dlmm).map(|m| m.extra[0]).unwrap();
    assert!(f.get(&ext_of(&bolt)).is_none(), "the bolt DLMM pair has no bitmap extension");
    assert!(f.get(&ext_of(&reg)).is_some(), "the USDC DLMM pair has one");
    assert!(r.e.store.get(&ext_of(&reg)).is_some_and(|a| !a.data.is_empty()), "followed and held by the store");
    assert!(reg.pools.iter().chain(&bolt.pools).all(|m| m.venue != Venue::Dlmm || !m.flag), "no boot-time flag");
}
