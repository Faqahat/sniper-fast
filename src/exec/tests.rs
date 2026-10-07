//! exec.rs's tests: PLAN WP-05's offline acceptance (bundle-only, the send checks, the in-flight lock, the network-call
//! counter, settlement), PLAN-ADDENDUM I-7 (a shadow run's would-sends) and the go-live gate's dry run (item 4)
use super::*;
use crate::control::GateMode;
use crate::feeds::PohGauge;
use crate::leaders::{LeaderBook, LeaderKind};
use crate::send::jito::{CachedToken, Jito, Outcome};
use crate::send::Path;
use crate::store_health::{HealthFlags, Shut};
use crate::venues::Venue;
use serde_json::json;
use std::sync::atomic::Ordering::Relaxed;
use std::sync::Mutex;

/// the route's token (no pool, vault or wallet key uses this byte)
const MINT: Pk = [251u8; 32];
/// a token the wallet holds no account for
const M2: Pk = [252u8; 32];
const S: u64 = 1_000_000_000;
/// the leaders of the test schedule: a Jito validator, a BAM one, another kind
const LJ: Pk = [231u8; 32];
const LB: Pk = [232u8; 32];
const LO: Pk = [233u8; 32];
/// the test blockhash: the ring's confirmed head, slot 100, height 90
const BH: [u8; 32] = [5u8; 32];

fn wallet_key() -> ed25519_dalek::SigningKey { ed25519_dalek::SigningKey::from_bytes(&[1u8; 32]) }
fn dry_key() -> ed25519_dalek::SigningKey { ed25519_dalek::SigningKey::from_bytes(&[77u8; 32]) }
fn unix_ms() -> i64 { (now_ns() / 1_000_000) as i64 }
fn tip_accounts() -> Vec<Pk> { send::known_tip_accounts(SendKind::JitoBundle).iter().map(|a| pk(a)).collect() }

/// the schedule, slots 96-119: 96-101 the Jito leader, 102-105 the BAM one, 106-109 the other kind, 110-119 Jito again
fn leader_of(slot: u64) -> Pk { match slot { 102..=105 => LB, 106..=109 => LO, _ => LJ } }
fn schedule() -> Vec<Pk> { (96..120).map(leader_of).collect() }
fn window_json() -> Value { json!({ "start": 96, "leaders": schedule().iter().map(b58).collect::<Vec<_>>() }) }

/// a config with one jito-bundle path (5 a second; WP-06: `[tips]`' defaults, 70% of the edge in every band, 1,000-100,000
/// lamports); `extra`: more TOML
fn test_cfg(dir: &std::path::Path, extra: &str) -> Config {
    let wallet = b58(&wallet_key().verifying_key().to_bytes());
    Config::parse(&format!("config_version = 2\nout_dir = \"{}\"\nwallet = \"{wallet}\"\n[pools]\nseed_csv = \"s.csv\"\n[rpc]\n[state]\nurl = \"http://localhost\"\n\
        [[send]]\nname = \"jito-bundle\"\nkind = \"jito-bundle\"\nurl = \"https://127.0.0.1:9\"\ntip_lamports = 1000\nmax_per_sec = 5\n{extra}",
        dir.display())).unwrap()
}

/// a recorder in `dir` (no monitor thread)
fn test_rec(dir: &std::path::Path) -> Rec {
    rec::start(rec::Opts { dir: dir.to_path_buf(), run: "test".into(), producer: "test".into(), cfg: Default::default(), feeds: vec![], monitor: false, echo: None }).unwrap()
}

fn test_dir(name: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("arbx-exec-{name}-{}-{}", std::process::id(), now_ns()));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn damm(n: u8, t0: Pk) -> PoolMeta {
    PoolMeta { venue: Venue::DammV2, pool: [n; 32], t0, t1: *WSOL, vault0: [n + 50; 32], vault1: [n + 100; 32],
        t0_prog: *crate::pda::TOKEN_PROGRAM, t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![], flag: false }
}

/// the test routes' size: 0.05 SOL, within every size cap the tests set (WP-07 review #12: the executor refuses a route
/// above its size cap, `size_cap`)
const SIZE: u64 = 50_000_000;

/// a round trip of `SIZE` through DAMM v2 pools `buy` and `sell` expecting `expected`, priced on state version `sv`
fn route(buy: u8, sell: PoolMeta, expected: u64, sv: u64) -> RouteIn {
    let size = SIZE;
    RouteIn { opp: buy as u64, trig: [3u8; 64], trig_feed: None, slot: 99, st: [100, 100, 200, 300, now_ns()], buy: damm(buy, MINT), sell,
        buy_data: vec![], sell_data: vec![], buy_source: "ours", sell_source: "ours", mint: MINT, size, mid: 1_000, back: size + expected, spent: size,
        gross_at_opp: expected as i64, net_at_opp: expected as i64, cu: 100_000,
        buy_live: vec![], sell_live: vec![], buy_end: None, sell_end: None, state_version: sv, route_age_ms: Some(1.5), decision: 40 + sv,
        trig_kind: "commit", t_first_shred: Some(90), t_commit: 150, t_priced: 400, parts_skew: Some((0, 1)),
        crowding: Crowding { signers_6h: Some(3), bucket: 0, src: "map_partial" }, accounts: vec![([buy; 32], 98, 7)],
        cu_src: "fallback".into(), cu_ata: (30_000, 5_000), mint_prog: *crate::pda::TOKEN_PROGRAM, mid_held: None, uva: None, buy_ext: None, sell_ext: None,
        sizes: vec![], arms: Default::default() }
}

/// what the in-memory block engine got: each bundle's transaction, and the send path's network calls when it got it
type Got = Arc<Mutex<Vec<(Vec<u8>, Option<u64>)>>>;

/// an in-memory block engine behind `j`: bundles land in the returned list, their ids b0, b1, ...
fn fake_engine(j: &Arc<Jito>) -> Got {
    let got: Got = Default::default();
    let g2 = got.clone();
    j.set_fake(Arc::new(move |txs: &[&[u8]]| {
        let net = crate::netcount::current().map(|c| c.load(Relaxed));
        let mut g = g2.lock().unwrap();
        g.push((txs[0].to_vec(), net));
        format!("b{}", g.len() - 1)
    }));
    got
}

/// a valid cached Jito token (an hour left)
fn fresh_token() -> CachedToken { CachedToken { value: "tok".into(), exp_ms: unix_ms() + 3_600_000, issued_ms: unix_ms() } }

/// a LeaderBook that knows the schedule and the three leaders' kinds
fn book() -> Arc<LeaderBook> {
    let b = LeaderBook::new(Rec::off());
    b.set_list("kobe", &json!({ "validators": [{ "identity_account": b58(&LJ), "running_jito": true }, { "identity_account": b58(&LB), "running_jito": true,
        "running_bam": true }, { "identity_account": b58(&LO), "running_jito": false }] }), now_ns()).unwrap();
    b.add_window(96, &schedule());
    b
}

/// the send view a decision reads: the ring's head at slot 100 (height 90) and the schedule
fn view() -> SendView {
    let mut v = SendView::default();
    v.on_head(&json!({ "hash": b58(&BH), "slot": 100, "height": 90, "src": "slotidx", "commitment": "confirmed", "t_ns": 1 }));
    v.on_window(&window_json());
    v
}

struct Rig {
    x: Exec,
    dir: std::path::PathBuf,
    rec: Rec,
    rx: crossbeam_channel::Receiver<Event>,
    got: Got,
    jito: Option<Arc<Jito>>,
    view: SendView,
    health: Arc<HealthFlags>,
    gauge: &'static PohGauge,
    book: Arc<LeaderBook>,
    /// events from the executor that were not settlements (the Jito sink's INPUT 5)
    buffered: Vec<Event>,
}
impl Drop for Rig { fn drop(&mut self) { self.rec.close(); let _ = std::fs::remove_dir_all(&self.dir); } }

/// An executor in `mode` on a made-up wallet, recording into its own directory. Live and canary send through a
/// jito-bundle path whose block engine is in memory (a valid cached token); shadow and dry runs hold no path (the dry run's
/// key is a throwaway one). The store is ready, the LeaderBook knows the schedule and the kinds, the ring's head is slot
/// 100, the `poh_trigger_pct` gauge is the rig's own. `extra`: more config
async fn rig(name: &str, mode: Mode, extra: &str) -> Rig { rig_full(name, mode, extra, None, [*WSOL, MINT].into_iter().collect()).await }

/// `rig` with PumpSwap's GlobalConfig and the tokens the wallet holds an account for
async fn rig_full(name: &str, mode: Mode, extra: &str, pump: Option<PumpGlobal>, held: HashSet<Pk>) -> Rig { rig_cfg(name, mode, extra, pump, held, vec![], &|_| {}).await }

/// `rig_full` with `[exec]` lookup tables and the config edited before the executor is assembled (WP-21: the venue switches)
async fn rig_cfg(name: &str, mode: Mode, extra: &str, pump: Option<PumpGlobal>, held: HashSet<Pk>, alts: Vec<(Pk, Vec<Pk>)>, edit: &dyn Fn(&mut Config)) -> Rig {
    let dir = test_dir(name);
    let rec = test_rec(&dir);
    let mut cfg = test_cfg(&dir, extra);
    edit(&mut cfg);
    let (tx, rx) = crossbeam_channel::unbounded();
    let (paths, jito, got) = if mode.sends() {
        let j = Jito::for_test(rec.clone());
        j.set_cached(Some(fresh_token()));
        let got = fake_engine(&j);
        (Some(Paths::for_test(vec![Path::test_bundle(j.clone(), Some(5), cfg.send_policy.queue_ms)], rec.clone())), Some(j), got)
    } else { (None, None, Got::default()) };
    let key = match mode { Mode::Live | Mode::Canary => Some(wallet_key()), Mode::DryRun => Some(dry_key()), Mode::Shadow => None };
    let mut x = Exec::assemble(&cfg, Rpc::race(vec![]), paths, rec.clone(), tx, vec![], alts, pump, held, mode, key).unwrap();
    let health = Arc::new(HealthFlags::default());
    health.set(Shut::Ready);
    x.set_health(health.clone());
    let book = book();
    x.set_leaders(book.clone());
    let gauge: &'static PohGauge = Box::leak(Box::new(PohGauge::new()));
    x.poh_gauge = gauge;
    Rig { x, dir, rec, rx, got, jito, view: view(), health, gauge, book, buffered: Vec::new() }
}

/// an executor that does nothing (to take a rig's own out for an engine)
fn idle_exec() -> Exec {
    Exec::assemble(&test_cfg(&std::env::temp_dir(), ""), Rpc::race(vec![]), None, Rec::off(), crossbeam_channel::unbounded().0, vec![], vec![], None,
        HashSet::default(), Mode::Shadow, None).unwrap()
}

impl Rig {
    /// the executor's turn at chain tip `tip` (target slot `tip + 1`), engine time `t`
    fn decide(&mut self, r: RouteIn, tip: u64, t: u64) -> Decided {
        let i = self.x.inputs(&self.view, tip, t);
        self.x.decide(r, &i, &self.view, &AltSource::none(), tip, t)
    }
    /// what came back from the executor's tasks so far, into `buffered`
    fn drain(&mut self) { while let Ok(ev) = self.rx.try_recv() { self.buffered.push(ev); } }
    /// the next settlement from the executor's tasks (other events are kept)
    async fn settled(&mut self) -> Settled {
        let t0 = std::time::Instant::now();
        loop {
            self.drain();
            if let Some(i) = self.buffered.iter().position(|e| matches!(e, Event::Settled(_))) {
                let Event::Settled(s) = self.buffered.remove(i) else { unreachable!() };
                return *s;
            }
            assert!(t0.elapsed() < std::time::Duration::from_secs(10), "no settlement");
            tokio::time::sleep(std::time::Duration::from_millis(2)).await;
        }
    }
    /// the INPUT 5 records the Jito sink sent so far (taken out)
    fn releases(&mut self) -> Vec<Value> {
        self.drain();
        let mut out = Vec::new();
        self.buffered.retain(|e| match e {
            Event::Input { kind: InputKind::InflightRelease, data } => { out.push((**data).clone()); false }
            _ => true,
        });
        out
    }
    fn lines(&self, stream: &str) -> Vec<Value> { self.rec.sync(); rec::read_jsonl(&self.dir, stream).unwrap_or_default() }
    fn n(&self, k: &str) -> u64 { self.x.counts.get(k).copied().unwrap_or(0) }
}

/// the inputs of a send that passes every check
fn ok_inputs() -> SendInputs {
    SendInputs { gate: GateMode::Live, gate_reason: "".into(), recorder_ok: true, shut: Shut::Ready, sender: None,
        blockhash: Some(BhSeen { slot: 100, age_slots: Some(3), src: "slotidx".into(), commitment: "confirmed" }), max_blockhash_age_slots: 20,
        leader: LeaderSeen { slot: 104, identity: Some(b58(&LJ)), kind: LeaderKind::Jito, kind_src: Some("kobe".into()) },
        skip_leader_kinds: vec![LeaderKind::Other, LeaderKind::Unknown], token: TokenSeen::Valid { age_s: 10 } }
}

// ------------------------------------------------------------------------------------------------ pure functions

/// PLAN WP-05 acceptance (`send_checks`, table-driven): a blockhash older than `max_blockhash_age_slots` (or none, or of
/// unknown age), a leader of a skipped kind (`other`, `unknown` by default; BAM allowed), an expired token and every other
/// input each refuse with their reason, in the plan's order (the gate first)
#[test]
fn send_checks_refuse_with_their_reasons_in_order() {
    assert_eq!(send_checks(&ok_inputs()), Ok(()));
    let with = |f: &dyn Fn(&mut SendInputs)| { let mut i = ok_inputs(); f(&mut i); send_checks(&i).err() };
    assert_eq!(with(&|i| i.blockhash.as_mut().unwrap().age_slots = Some(20)), None, "20 slots: the limit");
    assert_eq!(with(&|i| i.blockhash.as_mut().unwrap().age_slots = Some(21)).as_deref(), Some("blockhash_stale"));
    assert_eq!(with(&|i| i.blockhash.as_mut().unwrap().age_slots = None).as_deref(), Some("blockhash_stale"), "an age that cannot be told");
    assert_eq!(with(&|i| i.blockhash = None).as_deref(), Some("blockhash_stale"));
    assert_eq!(with(&|i| i.leader.kind = LeaderKind::Other).as_deref(), Some("leader_skip_kind"));
    assert_eq!(with(&|i| { i.leader.kind = LeaderKind::Unknown; i.leader.identity = None; }).as_deref(), Some("leader_unknown"));
    assert_eq!(with(&|i| i.leader.kind = LeaderKind::Bam), None, "BAM is not skipped by default");
    assert_eq!(with(&|i| { i.leader.kind = LeaderKind::Bam; i.skip_leader_kinds.push(LeaderKind::Bam); }).as_deref(), Some("leader_skip_kind"));
    assert_eq!(with(&|i| i.token = TokenSeen::Stale).as_deref(), Some("jito_auth_stale"), "only a valid cached token (F28)");
    assert_eq!(with(&|i| i.token = TokenSeen::NotUsed), None, "no bundle path, no token");
    assert_eq!(with(&|i| { i.gate = GateMode::Shadow; i.gate_reason = "control".into(); }).as_deref(), Some("gate_shadow:control"));
    assert_eq!(with(&|i| i.gate = GateMode::Stopped).as_deref(), Some("gate_stopped"));
    assert_eq!(with(&|i| i.recorder_ok = false).as_deref(), Some("recorder_unhealthy"));
    for (s, why) in [(Shut::Warmup, "warmup"), (Shut::StateUnavailable, "state_unavailable"), (Shut::Resync, "resync")] {
        assert_eq!(with(&|i| i.shut = s).as_deref(), Some(why));
    }
    assert_eq!(with(&|i| i.sender = Some("fee_cap")).as_deref(), Some("fee_cap"));
    // the order: every input bad, then fixed one at a time
    let mut all = ok_inputs();
    all.gate = GateMode::Shadow;
    all.gate_reason = "x".into();
    all.recorder_ok = false;
    all.shut = Shut::Warmup;
    all.sender = Some("fee_cap");
    all.blockhash = None;
    all.leader.kind = LeaderKind::Other;
    all.token = TokenSeen::Stale;
    let mut seen = Vec::new();
    while let Err(e) = send_checks(&all) {
        seen.push(e.split(':').next().unwrap().to_string());
        match seen.len() {
            1 => all.gate = GateMode::Live,
            2 => all.recorder_ok = true,
            3 => all.shut = Shut::Ready,
            4 => all.sender = None,
            5 => all.blockhash = ok_inputs().blockhash,
            6 => all.leader.kind = LeaderKind::Jito,
            _ => all.token = TokenSeen::NotUsed,
        }
    }
    assert_eq!(seen, ["gate_shadow", "recorder_unhealthy", "warmup", "fee_cap", "blockhash_stale", "leader_skip_kind", "jito_auth_stale"]);
    assert_eq!(SEND_CHECKS, ["gate", "recorder", "store_health", "sender", "blockhash", "leader", "jito_auth"]);
    let mut shadow = ok_inputs();
    shadow.gate = GateMode::Shadow;
    assert_eq!(input_checks(&shadow), Ok(()), "input_checks is send_checks without the gate");
}

/// PLAN WP-05 acceptance (the in-flight lock, table-driven): same state, a later slot of the same leader, a new state, a
/// new leader; an entry held `inflight_hold_slots` past its target slot, or until its attempt's final verdict
#[test]
fn the_inflight_lock() {
    let key = InflightKey { buy: [1; 32], sell: [2; 32], mint: MINT };
    let reverse = InflightKey { buy: [2; 32], sell: [1; 32], mint: MINT };
    let mut l = Inflight::new(2);
    assert_eq!(l.check(&key, 7, 101, Some(LJ)), Ok(("first", None)));
    l.insert(key, InflightEntry { sv: 7, target_slot: 101, leader: Some(LJ), attempt: 0, t: 0 });
    // (state version, target slot, leader) -> verdict
    let table: [(u64, u64, Pk, Result<&str, &str>); 6] = [
        (7, 101, LJ, Err("inflight_same_state")),
        (7, 102, LJ, Err("inflight_same_leader")),
        (8, 101, LJ, Ok("new_state")),
        (7, 102, LB, Ok("new_leader")),
        (8, 102, LB, Ok("new_state")),
        (7, 104, LJ, Ok("first")),
    ];
    for (sv, target, leader, want) in table {
        assert_eq!(l.check(&key, sv, target, Some(leader)).map(|x| x.0), want, "sv {sv} target {target}");
    }
    assert_eq!(l.check(&key, 8, 101, Some(LJ)).unwrap().1, Some((0, 7)), "the attempt and state it follows");
    assert_eq!(l.check(&reverse, 7, 101, Some(LJ)), Ok(("first", None)), "the reverse route is another key");
    // held while the chain is at target + 1, gone at target + 2
    l.expire(102);
    assert_eq!(l.len(), 1);
    l.expire(103);
    assert!(l.is_empty());
    // the final verdict releases it at once
    l.insert(key, InflightEntry { sv: 7, target_slot: 101, leader: Some(LJ), attempt: 5, t: 0 });
    assert!(!l.release(4) && l.len() == 1, "another attempt's verdict");
    assert!(l.release(5) && l.is_empty());
    assert_eq!(l.check(&key, 7, 101, Some(LJ)), Ok(("first", None)));
    // an unknown leader is the same unknown leader
    l.insert(key, InflightEntry { sv: 7, target_slot: 101, leader: None, attempt: 6, t: 0 });
    assert_eq!(l.check(&key, 7, 101, None), Err("inflight_same_state"));
    assert_eq!(l.check(&key, 7, 101, Some(LJ)), Ok(("new_leader", Some((6, 7)))));
}

/// PLAN WP-05 item 8: on-chain min_profit = tip + base fee + margin, margin = max(floor, share × net); the Stage-0
/// defaults (floor 1, share 0) keep today's floor (tip + base fee + 1). The bundle path's tip: its share of the edge within
/// its floor and cap, to its accounts in turn
#[test]
fn margins_and_tips() {
    assert_eq!(min_profit_onchain(31_500, 13_500, 1, 0.0), (36_501, 1), "today's floor");
    assert_eq!(min_profit_onchain(31_500, 200_000, 2_000, 0.02), (40_500, 4_000), "R §3.9's arm: 2% of the net");
    assert_eq!(min_profit_onchain(31_500, 50_000, 2_000, 0.02), (38_500, 2_000), "the floor");
    assert_eq!(min_profit_onchain(0, -5, 1, 0.5), (5_001, 1), "a negative net takes the floor");
    let c = test_cfg(&std::env::temp_dir(), "");
    let mut t = TipPolicy::from_path(&c.sends[0], crate::tip::TipModel::from_cfg(&c).unwrap());
    let (a, x) = t.tip(50_000).unwrap();
    let (b, _) = t.tip(50_000).unwrap();
    assert_eq!((x.lamports, x.band, x.share), (35_000, 1, 0.7));
    assert_eq!(t.tip(45_000).unwrap().1.lamports, 31_499, "the share is rounded down: never more than it");
    assert_ne!(a, b, "the accounts rotate");
    assert_eq!(t.tip(100).unwrap().1.lamports, 1_000, "the floor");
    assert_eq!(t.tip(10_000_000).unwrap().1.lamports, 100_000, "the cap");
    assert!(tip_accounts().contains(&a));
    // WP-06 item 8: the shares by band ([tips] shares), the same table as decisions and the queue
    let c = test_cfg(&std::env::temp_dir(), "[tips]\nshares = [0.5, 0.6, 0.7, 0.8, 0.9]\ncap = 10000000\n");
    let mut t = TipPolicy::from_path(&c.sends[0], crate::tip::TipModel::from_cfg(&c).unwrap());
    let got: Vec<(u64, u8)> = [10_000i64, 50_000, 500_000, 5_000_000, 20_000_000].iter().map(|e| { let x = t.tip(*e).unwrap().1; (x.lamports, x.band) }).collect();
    assert_eq!(got, vec![(5_000, 0), (30_000, 1), (350_000, 2), (4_000_000, 3), (10_000_000, 4)]);
}

/// data/crowded-pools.json: the 21 pools with 150 or more bots, with its source and date; bad entries are errors
#[test]
fn crowded_pools_file_loads() {
    let text = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/data/crowded-pools.json")).unwrap();
    let set = parse_crowded_pools(&text).unwrap();
    assert_eq!(set.len(), 21, "PATTERNS.md item 10: 21 pools with 150 or more bots");
    let v: Value = serde_json::from_str(&text).unwrap();
    assert!(v["source"].is_string() && v["date"].is_string());
    assert!(v["pools"].as_array().unwrap().iter().all(|p| p["bots"].as_u64().unwrap() >= 150));
    assert_eq!(parse_crowded_pools("[\"58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2\"]").unwrap().len(), 1, "a plain array");
    assert!(parse_crowded_pools("{\"pools\": [{\"pool\": \"not-a-key\"}]}").is_err());
    assert!(parse_crowded_pools("{\"pools\": [{\"bots\": 200}]}").is_err());
    assert!(parse_crowded_pools("{}").is_err());
    assert!(parse_crowded_pools("{\"pools\": []}").is_err(), "review N1: an empty list is a mistake, not a list");
    assert!(load_crowded_pools("/nonexistent/crowded-pools.json").is_err(), "a configured list must load");
}

/// The send view (journaled inputs only): the ring's head is the confirmed blockhash, a block meta the processed one; the
/// newest height; a blockhash expires 150 blocks after its own height (300 slots without heights); the schedule
#[test]
fn the_send_view() {
    let mut v = SendView::default();
    assert!(v.blockhash("confirmed").is_none());
    v.on_block_meta(103, [9; 32], Some(93), 5);
    assert!(v.blockhash("confirmed").is_none(), "a block meta is processed only");
    assert_eq!(v.blockhash("processed").map(|b| (b.slot, b.src.as_str())), Some((103, "blocks_meta")));
    v.on_head(&json!({ "hash": b58(&BH), "slot": 100, "height": 90, "src": "slotidx", "commitment": "confirmed", "t_ns": 1 }));
    assert_eq!(v.blockhash("confirmed").map(|b| (b.slot, b.hash)), Some((100, BH)));
    assert_eq!(v.blockhash("processed").map(|b| b.slot), Some(103), "the newer of the two");
    v.on_block_meta(101, [8; 32], Some(91), 6);
    assert_eq!(v.blockhash("processed").map(|b| b.slot), Some(103), "an older meta does not replace a newer one");
    assert_eq!(v.height, Some((103, 93)));
    assert_eq!(v.expired(100, Some(90), 0), Some(false));
    v.on_block_meta(400, [1; 32], Some(241), 7);
    assert_eq!(v.expired(100, Some(90), 0), Some(true), "height 241 > 90 + 150");
    assert_eq!(v.expired(100, None, 399), Some(false));
    assert_eq!(v.expired(100, None, 401), Some(true), "no height: slot + 300");
    assert_eq!(SendView::default().expired(100, None, 0), None, "nothing known");
    v.on_window(&json!({ "start": 500, "leaders": [b58(&LJ), b58(&LB)] }));
    assert_eq!((v.leader(500), v.leader(501), v.leader(502)), (Some(LJ), Some(LB), None));
}

// ------------------------------------------------------------------------------------------------ the executor's start

/// What each mode refuses at its start, before any RPC call: a live or canary executor needs the trading key (the
/// config's wallet), bundle-only send paths and its bundle path; a dry run refuses send paths and the trading key; a
/// shadow one holds no key; a configured crowded list that does not load stops every start (review F8 c)
#[tokio::test]
async fn exec_new_refuses_what_its_mode_forbids() {
    let dir = test_dir("new");
    let cfg = test_cfg(&dir, "");
    let (tx, _rx) = crossbeam_channel::unbounded();
    let j = Jito::for_test(Rec::off());
    let paths = Paths::for_test(vec![Path::test_bundle(j, Some(5), 10)], Rec::off());
    let err = |cfg: &Config, paths: Option<Arc<Paths>>, mode: Mode, key: Option<ed25519_dalek::SigningKey>| {
        let (cfg, tx) = (cfg.clone(), tx.clone());
        async move { format!("{:#}", Exec::new(&cfg, &Rpc::race(vec![]), paths, Rec::off(), tx, vec![], mode, key, vec![]).await.err().expect("refused")) }
    };
    assert!(err(&cfg, Some(paths.clone()), Mode::Live, None).await.contains("needs the trading key"));
    assert!(err(&cfg, Some(paths.clone()), Mode::Live, Some(dry_key())).await.contains("not the config's wallet"));
    assert!(err(&cfg, None, Mode::Canary, Some(wallet_key())).await.contains("needs its send paths"));
    let helius = "[[send]]\nname = \"helius\"\nkind = \"helius\"\nurl = \"https://fra-sender.helius-rpc.com/fast\"\ntip_lamports = 5000\n";
    let mixed = test_cfg(&dir, helius);
    assert!(err(&mixed, Some(paths.clone()), Mode::Live, Some(wallet_key())).await.contains("bundle-only"));
    assert!(err(&cfg, Some(paths.clone()), Mode::DryRun, Some(dry_key())).await.contains("a dry run builds no send path"));
    assert!(err(&cfg, None, Mode::DryRun, Some(wallet_key())).await.contains("must not be the trading wallet"));
    assert!(err(&cfg, None, Mode::Shadow, Some(dry_key())).await.contains("holds no key"));
    let crowded = test_cfg(&dir, "[send_policy]\ncrowded_pools_file = \"/nonexistent/crowded-pools.json\"\n");
    for mode in [Mode::Shadow, Mode::DryRun] {
        let key = (mode == Mode::DryRun).then(dry_key);
        assert!(err(&crowded, None, mode, key).await.contains("crowded_pools_file"), "{mode:?}");
    }
    let _ = std::fs::remove_dir_all(&dir);
}

// ------------------------------------------------------------------------------------------------ live

/// PLAN WP-05 acceptance: a live decision yields exactly one bundle copy, built on the ring's recent blockhash (no durable
/// nonce), its tip last to a Jito tip account, its route instruction carrying the size and the on-chain min_profit (tip +
/// base fee + 1) as signed (review WP-05 #12); the network-call counter is 0 when the send reaches the (in-memory) block
/// engine, while a token refresh's calls run in the background (F28). The attempt line (v2) carries the blockhash with
/// its age and source, the band, the crowding, the LeaderBook's snapshot of the target slot, the in-flight key, the state
/// version and the queue; copies.jsonl has the copy; `leader_known_pct` counts it (the `poh_trigger_pct` gauge is the
/// engine's, after the decision: `a_shadow_run_records_would_sends`)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_live_decision_sends_one_bundle_copy_with_no_network_call() {
    let mut r = rig("live-one", Mode::Live, "").await;
    crate::leaders::note_be_rtt(12.5);
    let t0 = crate::netcount::total();
    // a "token refresh" in the background while the send runs: its calls are not the send path's
    let bg = tokio::spawn(async { for _ in 0..50 { crate::netcount::note(); tokio::time::sleep(std::time::Duration::from_millis(1)).await; } });
    let d = r.decide(route(1, damm(2, MINT), 55_000, 7), 100, now_ns());
    assert_eq!((d.verdict, d.reason.as_str(), d.attempt, d.sent, d.would_send), ("send", "sent", Some(0), Some(true), false), "{d:?}");
    assert_eq!((d.rank, d.crowding.map(|c| c.bucket), d.ev), (Some(0), Some(0), Some(15_000)), "net: 55,000 - the 35,000 tip - the base fee");
    let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
    bg.await.unwrap();
    assert_eq!((attempt, fired.copies.len()), (0, 1), "exactly one bundle copy");
    let c = &fired.copies[0];
    assert!(c.ok && c.t_sent > 0 && c.bundle.as_deref() == Some("b0") && c.drop.is_none(), "{c:?}");
    let got = r.got.lock().unwrap().clone();
    assert_eq!(got.len(), 1, "one bundle reached the block engine");
    assert_eq!(got[0].1, Some(0), "no network call between the decision and the block engine (F28)");
    assert_eq!(r.x.net_calls(), 0);
    assert!(crate::netcount::total() >= t0 + 50, "the background calls were counted, outside the send path");
    // the transaction: one signature (the wallet's), the ring's blockhash, no AdvanceNonce, the tip last to a Jito account
    let raw = &got[0].0;
    let (tx, used) = crate::tx::parse_wire(raw).unwrap();
    assert_eq!((used, tx.num_signers, tx.keys[0]), (raw.len(), 1, r.x.payer));
    assert!(!tx.ixs.iter().any(|ix| tx.keys[ix.program as usize] == [0u8; 32] && ix.data.first() == Some(&4)), "no durable nonce");
    let tip = Some((tx.keys[tx.ixs.last().unwrap().accounts[1] as usize], 35_000));
    let checks = verify_bundle(raw, &live_want(&r.x, tip, 40_001));
    for c in &checks { assert_eq!(c["ok"], json!(true), "{c}"); }
    // the route instruction as signed: the size and min_profit = the 35,000 tip + the base fee + 1
    let all = tx.resolve(|t| r.x.alt_lists.get(t).cloned()).unwrap();
    let seen = route_of(&tx, &all, &r.x.program).unwrap();
    assert_eq!((seen.amount_in, seen.min_profit, seen.authority, seen.legs.len()), (SIZE, 40_001, r.x.payer, 2));
    assert_eq!((seen.legs[0].program, seen.legs[1].program), (Venue::DammV2.program(), Venue::DammV2.program()));
    assert_eq!(send::tip_paid(&tx, &tip_accounts()), 35_000, "70% of the 50,000 edge");
    r.x.on_settled(Settled::Fired { attempt, fired }, now_ns(), &|_| None);
    let a = r.lines("attempts");
    assert_eq!(a.len(), 1);
    let l = &a[0];
    assert_eq!((l["kind"].as_str(), l["sent"].as_bool(), l["copies"].as_array().map(|c| c.len())), (Some("live"), Some(true), Some(1)));
    assert_eq!((l["blockhash"]["hash"].as_str(), l["blockhash"]["slot"].as_u64(), l["blockhash"]["age_slots"].as_u64(), l["blockhash"]["src"].as_str(),
        l["blockhash"]["commitment"].as_str()), (Some(b58(&BH).as_str()), Some(100), Some(0), Some("slotidx"), Some("confirmed")));
    assert_eq!((l["leader"]["slot"].as_u64(), l["leader"]["leader"].as_str(), l["leader"]["kind"].as_str(), l["leader"]["kind_src"].as_str()),
        (Some(101), Some(b58(&LJ).as_str()), Some("jito"), Some("kobe")), "the LeaderBook's snapshot of the target slot");
    assert!(l["leader"]["be_rtt_ms"].as_f64().is_some(), "the block engine's keep-alive RTT");
    assert_eq!((l["band"].as_u64(), l["sv"].as_str(), l["inflight"]["why_allowed"].as_str(), l["inflight"]["key"][0].as_str()),
        (Some(1), Some("0000000000000007"), Some("first"), Some(b58(&[1u8; 32]).as_str())));
    assert_eq!((l["queue"]["rank"].as_u64(), l["queue"]["ev"].as_i64()), (Some(0), Some(15_000)));
    assert_eq!((l["tip"]["lamports"].as_u64(), l["min_profit_onchain"].as_u64(), l["margin"].as_u64()), (Some(35_000), Some(40_001), Some(1)),
        "min_profit = tip + base fee + max(margin_floor 1, 0 x net)");
    assert_eq!((l["crowding"]["src"].as_str(), l["crowding"]["bucket"].as_u64()), (Some("map_partial"), Some(0)));
    assert_eq!((l["tx"]["sig"].as_str(), l["route_in"]["accounts"][0]["wv"].as_u64()), (c_sig(&got[0].0).as_deref(), Some(7)));
    assert!(l["stages"]["t_signed"].as_u64().is_some() && l["stages"]["t_enqueued"].as_u64().is_some());
    assert_eq!(l["checks"].as_array().map(|c| c.len()), Some(SEND_CHECKS.len() + 10));
    let cp = r.lines("copies");
    assert_eq!((cp.len(), cp[0]["blockhash_slot"].as_u64(), cp[0]["queue_wait_us"].as_u64(), cp[0]["drop"].is_null()), (1, Some(100), Some(0), true));
    assert_eq!(r.gauge.status(&[], now_ns())["attempts_total"].as_u64(), Some(0), "the executor no longer reads the PoH index before the fire (review #8)");
    assert_eq!(r.x.leader_known_pct(), json!(100.0));
    assert_eq!(r.x.leader_known_pct(), Value::Null, "none since");
    assert_eq!((r.n("live_sent"), r.x.open_attempts()), (1, vec![0]));
}

fn c_sig(raw: &[u8]) -> Option<String> { send::first_signature(raw) }

/// what a live rig's bundle on the test route (pools [1; 32] and [2; 32], `SIZE`, DAMM v2 legs, signed by the wallet)
/// must be, with its tip and on-chain min_profit: the decision's route CU (100,000) and ATA allowances (30,000, 5,000),
/// `[builder]`'s defaults (`auto` loaded-data limit, held-set additions off), the route's sizes (none in the store)
fn live_want(x: &Exec, tip: Option<(Pk, u64)>, min_profit: u64) -> VerifyWant {
    VerifyWant { payer: x.payer, signer: x.payer, blockhash: BH, tip, tips: tip_accounts(), program: x.program, pools: [[1; 32], [2; 32]], cu_route: 100_000,
        cu_ata: (30_000, 5_000), alts: x.alt_lists.clone(), amount_in: SIZE, min_profit, margin_floor: 1,
        quote: build::ata_of(&x.payer, &WSOL, &crate::pda::TOKEN_PROGRAM), mid: build::ata_of(&x.payer, &MINT, &crate::pda::TOKEN_PROGRAM),
        leg_programs: [Venue::DammV2.program(), Venue::DammV2.program()], ata: None, held_ok: false, held_rent: build::HELD_RENT_BOUND, loaded_limit: Some(None),
        sizes: vec![], guard: None, payer_tokens: x.payer_tokens.clone() }
}

/// Fail closed (WP-04 review #8; PLAN WP-05 item 2): an executor is not ready until an engine installs its health; a
/// non-Jito leader, a stale or missing blockhash, a slot outside the schedule, an expiring token and a closed recorder
/// each refuse, before anything is built or sent
#[tokio::test]
async fn the_executor_fails_closed() {
    let mut r = rig("closed", Mode::Live, "").await;
    let t = now_ns();
    r.x.set_health(Arc::new(HealthFlags::default()));
    let d = r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t);
    assert_eq!((d.reason.as_str(), d.attempt), ("warmup", None), "not ready by default");
    r.x.set_health(r.health.clone());
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 2), 105, t + 1).reason, "leader_skip_kind", "slot 106: the other kind");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 3), 200, t + 2).reason, "blockhash_stale", "100 slots old");
    let mut empty = SendView::default();
    std::mem::swap(&mut empty, &mut r.view);
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 4), 100, t + 3).reason, "blockhash_stale", "no blockhash at all");
    std::mem::swap(&mut empty, &mut r.view);
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 5), 120, t + 4).reason, "leader_unknown", "slot 121: outside the schedule");
    // the journaled schedule names the leader; a LeaderBook that names another for the slot makes it unknown
    r.view.on_window(&json!({ "start": 101, "leaders": [b58(&LB)] }));
    let i = r.x.inputs(&r.view, 100, t + 5);
    assert_eq!((i.leader.identity.clone(), i.leader.kind, i.leader.kind_src.as_deref()), (Some(b58(&LB)), LeaderKind::Unknown, Some("schedule_mismatch")));
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 6), 100, t + 5).reason, "leader_unknown");
    r.view.on_window(&json!({ "start": 101, "leaders": [b58(&LJ)] }));
    let j = r.jito.clone().unwrap();
    j.set_cached(Some(CachedToken { value: "t".into(), exp_ms: unix_ms() + 2_000, issued_ms: unix_ms() - 600_000 }));
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 6), 100, now_ns()).reason, "jito_auth_stale", "2 s left: the send path would not use it");
    j.set_cached(None);
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 100, now_ns()).reason, "jito_auth_stale", "none");
    j.set_cached(Some(fresh_token()));
    r.rec.close();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 8), 100, now_ns()).reason, "recorder_unhealthy", "a closed recorder");
    r.x.rec = Rec::off();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 9), 100, now_ns()).reason, "recorder_unhealthy", "no recorder");
    assert!(r.got.lock().unwrap().is_empty(), "nothing was sent");
    assert_eq!((r.n("reject_warmup"), r.n("reject_blockhash_stale"), r.n("reject_jito_auth_stale"), r.n("reject_leader_unknown"), r.n("reject_leader_skip_kind")),
        (1, 2, 2, 2, 1));
    assert_eq!(r.x.next_attempt, 0, "no attempt");
}

/// The route checks in a live run: the in-flight lock (the same state, a later slot of the same leader, a new state, a new
/// leader), the ≥1M class's bucket (a token every 2 s), the crowded skip (`crowded_skip`, from
/// `crowded_skip_min_expected_lamports`) and the crowded rank, the decision's bar, an implausible gap, a token not held
/// (WP-06: created and closed, not refused), token cooling after 25 attempts' would-fails in a row (a second would-fail
/// of one bundle does not count again: review #16)
#[tokio::test]
async fn the_route_checks() {
    let mut r = rig("route", Mode::Live, "[send_policy]\ncrowded_skip_min_expected_lamports = 100000\n").await;
    let t = now_ns();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 100, t).reason, "sent");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 100, t + 1).reason, "inflight_same_state");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 100, t + 2).reason, "inflight_same_state");
    // tip 101: target 102, the BAM leader: a new leader; tip 102: target 103, the same BAM leader, a later slot
    let d = r.decide(route(1, damm(2, MINT), 50_000, 7), 101, t + 3);
    assert_eq!(d.reason, "sent", "a new leader");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 102, t + 4).reason, "inflight_same_leader");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 8), 102, t + 5).reason, "sent", "a new state");
    let a = r.lines("attempts");
    assert_eq!(a.iter().map(|l| (l["inflight"]["why_allowed"].as_str().unwrap().to_string(), l["inflight"]["prev_attempt"].as_u64())).collect::<Vec<_>>(),
        vec![("first".into(), None), ("new_leader".into(), Some(0)), ("new_state".into(), Some(1))]);
    // the big class: 0.5/s, burst 1
    let big = 1_100_000;
    assert_eq!(r.decide(route(3, damm(4, MINT), big, 1), 100, t).reason, "sent");
    assert_eq!(r.decide(route(3, damm(4, MINT), big, 2), 100, t + S).reason, "band_throttle");
    assert_eq!(r.decide(route(3, damm(4, MINT), big, 3), 100, t + 2 * S + 1).reason, "sent", "a token every 2 s");
    // crowded: bucket 2 from 100k expected is not sent; below it, it goes ranked behind its band's others
    let mut c = route(5, damm(6, MINT), 150_000, 1);
    c.crowding = Crowding { signers_6h: None, bucket: 2, src: "static_list" };
    assert_eq!(r.decide(c.clone(), 100, t).reason, "crowded_skip");
    let mut c2 = route(5, damm(6, MINT), 60_000, 2);
    c2.crowding = c.crowding;
    let d = r.decide(c2, 100, t);
    assert_eq!((d.reason.as_str(), d.rank), ("sent", Some(1)));
    // the decision's bar: tip + base fee + [live] margin_lamports (6,999 pays a 1,399 tip: the bar is 7,399)
    assert_eq!(r.decide(route(7, damm(8, MINT), 6_999, 1), 100, t).reason, "expected_below_min_profit");
    assert_eq!(r.decide(route(7, damm(8, MINT), 0, 2), 100, t).reason, "expected_below_min_profit");
    assert_eq!(r.decide(route(7, damm(8, MINT), 2_000_000_000, 3), 100, t).reason, "implausible_gap");
    // WP-06: a token the wallet holds no account for is no longer refused (`rent_cap` and `max_new_token_accounts` are
    // gone): its account is created and closed in the same transaction (rent_neutral_create_and_close has the bytes)
    let mut m2 = route(7, damm(8, M2), 50_000, 4);
    m2.mint = M2;
    m2.buy = damm(7, M2);
    assert_eq!(r.decide(m2, 100, t).reason, "sent");
    let l = r.lines("attempts").last().unwrap().clone();
    assert_eq!((l["tx"]["creates_ata"].as_bool(), l["tx"]["closes_ata"].as_bool(), l["tx"]["held_addition"].as_bool()), (Some(true), Some(true), Some(false)));
    assert_eq!((r.n("reject_inflight_same_state"), r.n("reject_inflight_same_leader"), r.n("reject_band_throttle"), r.n("reject_crowded_skip"), r.n("rank_crowded")),
        (2, 1, 1, 1, 1));
    // token cooling: would-fails of 25 attempts in a row (the block engine's results) pause the token 60 s; one bundle's
    // repeated would-fails count once
    for k in 0..24u8 { assert_eq!(r.decide(route(40 + 2 * k, damm(41 + 2 * k, MINT), 50_000, 1), 100, t).reason, "sent"); }
    let open: Vec<u64> = r.x.open_attempts().into_iter().filter(|a| *a != 6).collect();
    assert_eq!(open.len(), 30, "the M2 attempt (6) aside");
    let wf = |a: u64| json!({ "attempt": a, "outcome": "would-fail", "release": false, "sig": null });
    for k in 0..24 { r.x.on_release(&wf(open[k]), t + k as u64); }
    for _ in 0..5 { r.x.on_release(&wf(open[0]), t + 30); }
    assert_eq!((r.decide(route(9, damm(10, MINT), 50_000, 1), 100, t + 30).reason.as_str(), r.n("cool_repeat")), ("sent", 5), "24 attempts: not yet");
    r.x.on_release(&wf(open[24]), t + 31);
    assert_eq!(r.decide(route(11, damm(12, MINT), 50_000, 1), 100, t + 32).reason, "token_cooling");
    assert_eq!(r.decide(route(11, damm(12, MINT), 50_000, 2), 100, t + 61 * S).reason, "sent", "60 s later");
    assert_eq!(r.n("verdict_would_fail"), 30, "every result is counted as a verdict");
    // the run stops: every attempt still open gets its `unsettled` final line (stop.json lists them)
    let open = r.x.open_attempts();
    assert_eq!(open.len(), 33);
    assert_eq!(r.x.settle_at_stop(), open);
    let o = r.lines("outcomes");
    assert_eq!((o.len(), o.iter().all(|l| l["final"] == "unsettled" && l["final_src"] == "stop")), (33, true));
    assert!(r.x.open_attempts().is_empty() && r.x.inflight.is_empty());
    assert_eq!(r.n("unsettled"), 33);
}

/// PLAN WP-05 item 1: a canary run is a live run under `[canary]`'s caps: trades of at most `size_sol` (never above 0.2
/// SOL, nor `[live] max_size_sol`), `count` attempts at least `every_ms` apart, then the sender stops (`canary_count`);
/// its failed-fee cap is `max_spend_lamports`
#[tokio::test]
async fn a_canary_is_a_capped_live_run() {
    let mut r = rig("canary", Mode::Canary, "[canary]\nenabled = true\ncount = 2\nevery_ms = 1000\nsize_sol = 0.05\nmax_spend_lamports = 20000\n").await;
    assert_eq!((r.x.size_cap(), r.x.cap_failed_fees), (50_000_000, 20_000));
    let t = now_ns();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t).reason, "sent");
    assert_eq!(r.decide(route(3, damm(4, MINT), 50_000, 1), 100, t + 1).reason, "canary_wait");
    assert_eq!(r.decide(route(3, damm(4, MINT), 50_000, 2), 100, t + S + 1).reason, "sent", "every_ms later");
    assert_eq!(r.decide(route(5, damm(6, MINT), 50_000, 1), 100, t + 3 * S).reason, "canary_count");
    assert_eq!(r.x.status()["stopped"].as_str(), Some("canary count reached"));
    assert_eq!(r.decide(route(7, damm(8, MINT), 50_000, 1), 100, t + 4 * S).reason, "sender_stopped", "for good");
    let a = r.lines("attempts");
    assert_eq!(a.iter().map(|l| (l["kind"].as_str().unwrap().to_string(), l["sent"].as_bool().unwrap())).collect::<Vec<_>>(),
        vec![("canary".to_string(), true), ("canary".to_string(), true)]);
    assert_eq!((r.n("canary_sent"), r.n("reject_canary_wait"), r.n("reject_canary_count"), r.n("reject_sender_stopped")), (2, 1, 1, 1));
}

/// PLAN WP-01's control test on the WP-05 executor: `pause-sending` through the control socket closes the gate. The
/// decision's reason is `gate_shadow:control`; one that passes every other check is a would-send (decisions `would_send`,
/// attempts `sent = false`, nothing reaches the block engine), one another check refuses says which (`reason_ungated`).
/// `resume-sending` sends again; a stop closes the gate for good
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_pause_records_would_sends_and_sends_nothing() {
    use crate::control::{self, StopInfo, StopReason};
    let mut r = rig("ctl", Mode::Live, "").await;
    let sess = control::Session::new();
    sess.set_dir(r.dir.clone());
    r.x.set_gate(sess.gate.clone());
    let _srv = control::serve(sess.clone(), &r.dir).unwrap();
    let rep = control::send_command(&r.dir, "pause-sending", "moiz", "WP-05 control test").unwrap();
    assert_eq!((rep["accepted"].as_bool(), rep["send_gate"]["mode"].as_str()), (Some(true), Some("shadow")));
    let t = now_ns();
    let d = r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t);
    assert_eq!((d.verdict, d.reason.as_str(), d.would_send, d.sent, d.attempt, d.reason_ungated.clone()), ("reject", "gate_shadow:control", true, Some(false), Some(0), None));
    let d2 = r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t + 1);
    assert_eq!((d2.reason.as_str(), d2.would_send, d2.attempt, d2.reason_ungated.as_deref()), ("gate_shadow:control", false, None, Some("inflight_same_state")));
    assert!(control::send_command(&r.dir, "resume-sending", "moiz", "done").unwrap()["accepted"].as_bool().unwrap());
    assert_eq!(r.decide(route(3, damm(4, MINT), 50_000, 1), 100, t + 2).reason, "sent");
    sess.stopper.request(StopInfo::new(StopReason::Signal, "SIGINT"));
    assert_eq!(r.decide(route(5, damm(6, MINT), 50_000, 1), 100, t + 3).reason, "gate_stopped");
    let _ = r.settled().await;
    tokio::time::sleep(std::time::Duration::from_millis(20)).await;
    assert_eq!(r.got.lock().unwrap().len(), 1, "only the resumed decision reached the block engine");
    assert_eq!((r.n("reject_gate_shadow"), r.n("reject_gate_stopped"), r.n("would_send"), r.n("live_sent")), (2, 1, 2, 1));
    // review #16: what else refused a gated decision is `ungated_<reason>`: the `reject_*` counters sum to the refusals
    assert_eq!((r.n("ungated_inflight_same_state"), r.n("reject_inflight_same_state")), (1, 0));
    let rejects: u64 = r.x.counts.iter().filter(|(k, _)| k.starts_with("reject_")).map(|(_, v)| *v).sum();
    assert_eq!(rejects, r.x.status()["decisions"].as_u64().unwrap() - r.n("live_sent"), "one reject_* per refused decision");
    let a = r.lines("attempts");
    assert_eq!(a.iter().map(|l| (l["attempt"].as_u64().unwrap(), l["sent"].as_bool().unwrap())).collect::<Vec<_>>(), vec![(0, false), (1, true), (2, false)]);
    assert_eq!((a[0]["not_sent"].as_str(), a[2]["not_sent"].as_str(), a[0]["tx"]["sig"].as_str()), (Some("gate_shadow:control"), Some("gate_stopped"), None),
        "a would-send of a sending mode is not signed");
}

// ------------------------------------------------------------------------------------------------ settlement

/// PLAN WP-05 acceptance (settlement, stream-based): every block-engine result of our bundle reaches the engine as INPUT
/// 5 (a landing releases the in-flight entry); the wallet stream's record of our signature makes the attempt final
/// (`landed_ok`, its fee, CU and the route program's events, with the results in order); an expiry check that finds a
/// landing makes it landed (`statuses`), one that finds nothing `not_landed_expired`, and a landing seen later writes an
/// amend line; cross-checks are kept. Review WP-05 #3: a landing the expiry check found first counts the base fee and an
/// unknown round trip until its wallet record amends it (an amend line with its fee, CU and events; its round trip
/// counted then, its landing and tip once). A send the queue dropped is final at once and gives back its in-flight entry
/// and its big-band token
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn settlement_from_the_chain() {
    let mut r = rig("settle", Mode::Live, "").await;
    let t = now_ns();
    let mut sigs = Vec::new();
    for k in 0..3u8 {
        assert_eq!(r.decide(route(10 + 2 * k, damm(11 + 2 * k, MINT), 50_000, 1), 100, t).reason, "sent");
        let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
        assert_eq!(attempt, k as u64);
        sigs.push(fired.copies[0].sig.clone().unwrap());
        r.x.on_settled(Settled::Fired { attempt, fired }, now_ns(), &|_| None);
    }
    // the block engine's results of attempt 0's bundle (b0): accepted, then processed
    let j = r.jito.clone().unwrap();
    let res = |outcome: &'static str| Outcome { bundle: "b0".into(), outcome, slot: Some(101), index: (outcome == "processed").then_some(4), bid: None, detail: None,
        validator: Some(b58(&LJ)) };
    j.on_result_at(res("accepted"), t + 1);
    j.on_result_at(res("processed"), t + 2);
    let rel = r.releases();
    assert_eq!(rel.iter().map(|d| (d["attempt"].as_u64(), d["outcome"].as_str(), d["release"].as_bool(), d["seq"].as_u64())).collect::<Vec<_>>(),
        vec![(Some(0), Some("accepted"), Some(false), Some(0)), (Some(0), Some("processed"), Some(true), Some(1))]);
    let keys = r.x.inflight.len();
    for d in &rel { r.x.on_release(d, t + 3); }
    assert_eq!((r.x.inflight.len(), r.n("inflight_released")), (keys - 1, 1), "the landing released the entry");
    // attempt 0 lands (the wallet stream), with the route program's events
    let events = |back: u64| json!([{ "kind": "leg", "leg": 0 }, { "kind": "out", "leg": 0, "amount": 77 }, { "kind": "out", "leg": 1, "amount": back }]);
    r.x.on_wallet_tx(&json!({ "sig": sigs[0], "attempt": 0, "slot": 101, "idx": 12, "ok": true, "err": null, "fee": 5_000, "cu_consumed": 87_000,
        "prog_events": events(SIZE + 49_000) }), now_ns(), &|_| None);
    // a cross-check of attempt 1 (+2 s): nothing yet
    r.x.on_settled(Settled::Statuses { why: "check", at: vec![(1, "+2s")], result: Ok(vec![None]), t_ns: t }, t, &|_| None);
    // the expiry check: attempt 1 landed (the wallet stream missed it), attempt 2 did not
    let hit = SigStatus { slot: 102, err: None, confirmation: Some("confirmed".into()) };
    r.x.on_settled(Settled::Statuses { why: "expiry", at: vec![(1, "expiry"), (2, "expiry")], result: Ok(vec![Some(hit), None]), t_ns: t }, t, &|_| None);
    assert!(r.x.open_attempts().is_empty());
    // attempt 1 is a win whose fee and round trip only its wallet record has: the base fee is counted, the round trip is
    // unknown (the money says it is partial), the tip is counted once
    let money = |r: &Rig| { let (_, m) = r.x.status_v2(&mut ExecPrev::default()); m };
    let m = money(&r);
    assert_eq!((m["round_trip_total_lamports"].as_i64(), m["round_trip_unknown_total"].as_u64(), m["tips_paid_total_lamports"].as_u64(), m["fees_landed_total_lamports"].as_u64()),
        (Some(49_000), Some(1), Some(2 * 31_499), Some(10_000)));
    // attempt 2 landed after all (seen later): an amend line; its failed fee counts against the cap
    r.x.on_wallet_tx(&json!({ "sig": sigs[2], "attempt": 2, "slot": 140, "idx": 3, "ok": false, "err": { "InstructionError": [2, { "Custom": 1314390018u64 }] },
        "fee": 5_000 }), now_ns(), &|_| None);
    // attempt 1's wallet record comes after its final: it amends the fee, CU and events, and its round trip is counted
    r.x.on_wallet_tx(&json!({ "sig": sigs[1], "attempt": 1, "slot": 102, "idx": 7, "ok": true, "err": null, "fee": 5_000, "cu_consumed": 91_000,
        "prog_events": events(SIZE + 21_000) }), now_ns(), &|_| None);
    // a second copy of a wallet record changes nothing
    r.x.on_wallet_tx(&json!({ "sig": sigs[1], "attempt": 1, "slot": 102, "idx": 7, "ok": true, "err": null, "fee": 5_000, "cu_consumed": 91_000,
        "prog_events": events(SIZE + 21_000) }), now_ns(), &|_| None);
    let o = r.lines("outcomes");
    let by = |a: u64| o.iter().filter(|l| l["attempt"].as_u64() == Some(a)).cloned().collect::<Vec<_>>();
    let o0 = &by(0)[0];
    assert_eq!((o0["final"].as_str(), o0["final_src"].as_str(), o0["landed"]["slot"].as_u64(), o0["fee_lamports"].as_u64(), o0["cu_consumed"].as_u64()),
        (Some("landed_ok"), Some("wallet"), Some(101), Some(5_000), Some(87_000)));
    assert_eq!((o0["delivered"].clone(), o0["round_trip_on_chain"].as_i64(), o0["landed"]["leader_kind"].as_str()), (json!([77, SIZE + 49_000]), Some(49_000), Some("jito")));
    assert_eq!(o0["verdicts"].as_array().map(|v| v.iter().map(|x| x["outcome"].as_str().unwrap().to_string()).collect::<Vec<_>>()),
        Some(vec!["accepted".to_string(), "processed".into()]), "every result, in order");
    assert_eq!((o0["processed"]["index"].as_u64(), o0["accepted"]["validator"].as_str(), o0["bundle"].as_str()), (Some(4), Some(b58(&LJ).as_str()), Some("b0")));
    let o1 = by(1);
    assert_eq!(o1.len(), 2, "the final line and the wallet record's amend");
    assert_eq!((o1[0]["final"].as_str(), o1[0]["final_src"].as_str(), o1[0]["landed"]["slot"].as_u64(), o1[0]["fee_lamports"].is_null()),
        (Some("landed_ok"), Some("statuses"), Some(102), true));
    assert_eq!(o1[0]["statuses_checks"].as_array().map(|a| a.iter().map(|c| c["at"].as_str().unwrap().to_string()).collect::<Vec<_>>()),
        Some(vec!["+2s".to_string(), "expiry".into()]));
    assert_eq!((o1[1]["amend"].as_bool(), o1[1]["amends"].as_str(), o1[1]["final_src"].as_str(), o1[1]["fee_lamports"].as_u64(), o1[1]["cu_consumed"].as_u64(),
        o1[1]["round_trip_on_chain"].as_i64()), (Some(true), Some("statuses"), Some("wallet"), Some(5_000), Some(91_000), Some(21_000)));
    let o2 = by(2);
    assert_eq!(o2.len(), 2);
    assert_eq!((o2[0]["final"].as_str(), o2[0]["final_src"].as_str(), o2[0]["amend"].as_bool()), (Some("not_landed_expired"), Some("expiry"), Some(false)));
    assert_eq!((o2[1]["final"].as_str(), o2[1]["amend"].as_bool(), o2[1]["amends"].as_str(), o2[1]["final_src"].as_str(), o2[1]["fee_lamports"].as_u64()),
        (Some("landed_fail"), Some(true), Some("not_landed"), Some("wallet"), Some(5_000)), "the amend line");
    assert_eq!((r.n("landed_ok"), r.n("not_landed_expired"), r.n("expiry_status_hit"), r.n("amended")), (2, 1, 1, 2));
    let (exec, m) = r.x.status_v2(&mut ExecPrev::default());
    assert_eq!((exec["landed_total"].as_u64(), exec["ok_total"].as_u64(), exec["sent_total"].as_u64(), m["failed_fees_total_lamports"].as_u64(), m["src"].as_str()),
        (Some(3), Some(2), Some(3), Some(5_000), Some("bot")), "each landing once");
    assert_eq!((m["round_trip_total_lamports"].as_i64(), m["round_trip_unknown_total"].as_u64(), m["tips_paid_total_lamports"].as_u64(), m["fees_landed_total_lamports"].as_u64()),
        (Some(49_000 + 21_000), Some(0), Some(2 * 31_499), Some(15_000)), "both winners' round trips and tips; every landed fee");
    // a send the rate queue dropped: final at once; its in-flight entry and its big-band token come back
    let big = 1_100_000;
    assert_eq!(r.decide(route(30, damm(31, MINT), big, 1), 100, t).reason, "sent");
    let Settled::Fired { attempt, fired: mut f } = r.settled().await else { panic!("a fire result") };
    assert_eq!(r.decide(route(30, damm(31, MINT), big, 1), 100, t + 1).reason, "inflight_same_state", "held while it is open");
    f.copies[0].t_sent = 0;
    f.copies[0].ok = false;
    f.copies[0].drop = Some("rate_queue_timeout");
    r.x.on_settled(Settled::Fired { attempt, fired: f }, now_ns(), &|_| None);
    let last = r.lines("outcomes").last().cloned().unwrap();
    assert_eq!((last["attempt"].as_u64(), last["final"].as_str(), last["final_src"].as_str(), last["error"].as_str()),
        (Some(attempt), Some("not_landed_refused"), Some("send"), Some("rate_queue_timeout")));
    assert_eq!(r.n("drop_rate_queue_timeout"), 1);
    assert_eq!(r.decide(route(30, damm(31, MINT), big, 1), 100, t + 2).reason, "sent", "the entry and the token came back");
}

/// Review WP-05 #3: a failed landing the expiry check found first counts against the failed-fee cap at once (the base
/// fee, what the bundle paid), and its wallet record replaces it by the fee recorded, without counting the landing twice
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_failed_landing_found_by_the_expiry_check_counts_against_the_cap() {
    let mut r = rig("settle-fail", Mode::Live, "[live]\nmax_failed_fees_lamports = 9000\n").await;
    let t = now_ns();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t).reason, "sent");
    let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
    let sig = fired.copies[0].sig.clone().unwrap();
    r.x.on_settled(Settled::Fired { attempt, fired }, t, &|_| None);
    let fail = SigStatus { slot: 102, err: Some(json!({ "InstructionError": [2, { "Custom": 1314390018u64 }] })), confirmation: Some("confirmed".into()) };
    r.x.on_settled(Settled::Statuses { why: "expiry", at: vec![(attempt, "expiry")], result: Ok(vec![Some(fail)]), t_ns: t }, t, &|_| None);
    let (_, m) = r.x.status_v2(&mut ExecPrev::default());
    assert_eq!((m["failed_fees_total_lamports"].as_u64(), m["fees_landed_total_lamports"].as_u64(), m["tips_paid_total_lamports"].as_u64()), (Some(5_000), Some(5_000), Some(0)));
    // 5,000 spent + 5,000 for the next send is over the 9,000 cap: the sender stops
    assert_eq!(r.decide(route(3, damm(4, MINT), 50_000, 1), 100, t + 1).reason, "fee_cap");
    assert_eq!(r.x.status()["stopped"].as_str(), Some("failed-fee cap reached"));
    // the wallet record then says 6,000 (the fee it really paid): it replaces the 5,000, the landing counts once
    r.x.on_wallet_tx(&json!({ "sig": sig, "attempt": attempt, "slot": 102, "idx": 1, "ok": false, "err": { "InstructionError": [2, { "Custom": 1314390018u64 }] },
        "fee": 6_000 }), now_ns(), &|_| None);
    let (exec, m) = r.x.status_v2(&mut ExecPrev::default());
    assert_eq!((m["failed_fees_total_lamports"].as_u64(), m["fees_landed_total_lamports"].as_u64(), exec["landed_total"].as_u64(), exec["ok_total"].as_u64()),
        (Some(6_000), Some(6_000), Some(1), Some(0)));
    let o = r.lines("outcomes");
    assert_eq!(o.iter().map(|l| (l["final_src"].as_str().unwrap().to_string(), l["amend"].as_bool().unwrap())).collect::<Vec<_>>(),
        vec![("statuses".to_string(), false), ("wallet".to_string(), true)]);
    assert_eq!(o[1]["failed_fees_total_lamports"].as_u64(), Some(6_000));
}

/// The executor's timers: the cross-checks fall due at +2 s, +10 s and +60 s (one batched getSignatureStatuses each);
/// once the chain passes the blockhash's validity (height + 150) the attempt is checked once more (with
/// `searchTransactionHistory`, F43) and the answer makes it final. With no RPC to ask, the check fails and the attempt is
/// `not_landed_expired`, the failure noted
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn expiry_and_cross_checks_from_the_timers() {
    let mut r = rig("expiry", Mode::Live, "").await;
    let t = now_ns();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t).reason, "sent");
    let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
    let t_sent = fired.copies[0].t_sent;
    r.x.on_settled(Settled::Fired { attempt, fired }, now_ns(), &|_| None);
    r.x.tick(t_sent + S, &r.view, 101);
    assert_eq!((r.n("status_check"), r.n("expiry_check")), (0, 0), "nothing due yet");
    r.x.tick(t_sent + 2 * S, &r.view, 102);
    assert_eq!(r.n("status_check"), 1, "the +2 s check");
    let Settled::Statuses { why, at, result, .. } = r.settled().await else { panic!("a statuses answer") };
    assert_eq!((why, at.clone(), result.is_err()), ("check", vec![(attempt, "+2s")], true), "no provider to ask");
    r.x.on_settled(Settled::Statuses { why, at, result, t_ns: t }, t, &|_| None);
    // the chain passes height 90 + 150
    r.view.on_block_meta(400, [1; 32], Some(241), t);
    r.x.tick(t_sent + 3 * S, &r.view, 400);
    assert_eq!(r.n("expiry_check"), 1);
    r.x.tick(t_sent + 4 * S, &r.view, 401);
    assert_eq!(r.n("expiry_check"), 1, "once");
    let s = r.settled().await;
    assert!(matches!(&s, Settled::Statuses { why: "expiry", .. }));
    r.x.on_settled(s, now_ns(), &|_| None);
    let o = r.lines("outcomes");
    assert_eq!((o.len(), o[0]["final"].as_str(), o[0]["final_src"].as_str()), (1, Some("not_landed_expired"), Some("expiry")));
    assert!(o[0]["error"].as_str().is_some_and(|e| e.contains("expiry check failed")), "{}", o[0]);
    assert_eq!(o[0]["statuses_checks"].as_array().map(|a| a.len()), Some(2));
    assert_eq!((o[0]["blockhash"]["valid_until_height"].as_u64(), o[0]["target_slot"].as_u64()), (Some(240), Some(101)));
    assert!(r.x.open_attempts().is_empty() && r.x.inflight.is_empty());
}

// ------------------------------------------------------------------------------------------------ with an engine

/// two AMM v4 pools on MINT / WSOL (1,000 and 1,010 SOL), in an offline engine
fn amm_engine() -> (crate::engine::Engine, PoolMeta, PoolMeta) {
    use crate::config::StrategyCfg;
    let amm = |n: u8| PoolMeta { venue: Venue::RayAmmV4, pool: [n; 32], t0: MINT, t1: *WSOL, vault0: [n + 10; 32], vault1: [n + 20; 32],
        t0_prog: *crate::pda::TOKEN_PROGRAM, t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![], flag: false };
    let pool_data: Arc<[u8]> = { let mut p = vec![0u8; 752]; p[0..8].copy_from_slice(&1u64.to_le_bytes()); p[176..184].copy_from_slice(&25u64.to_le_bytes());
        p[184..192].copy_from_slice(&10_000u64.to_le_bytes()); p.into() };
    let (a, b) = (amm(1), amm(2));
    let mut reg = crate::pools::Registry { pools: vec![a.clone(), b.clone()], by_pool: Default::default(), pairs: Default::default(), seeds: Default::default(), ours: Default::default() };
    reg.by_pool.insert(a.pool, 0);
    reg.by_pool.insert(b.pool, 1);
    reg.pairs.insert(crate::pools::pair_key(&MINT, &WSOL), vec![0, 1]);
    let mut store = crate::store::Store::default();
    for (m, sol) in [(&a, 1_000u64), (&b, 1_010)] {
        store.update(m.pool, pool_data.clone(), 10, 1, None);
        store.update(m.vault0, amm_vault(1_000_000_000_000_000), 10, 1, None);
        store.update(m.vault1, amm_vault(sol * 1_000_000_000), 10, 1, None);
    }
    (crate::engine::Engine::new_offline(Arc::new(reg), store, StrategyCfg { state_triggers: true, ..StrategyCfg::default() }), a, b)
}

fn amm_vault(amount: u64) -> Arc<[u8]> { let mut v = vec![0u8; 165]; v[64..72].copy_from_slice(&amount.to_le_bytes()); v.into() }

/// the stream delivers at `slot` and Tier A is complete (the warm-up gate opens, WP-04); the ring's head (slot 99) and
/// the schedule arrive as journaled inputs
fn amm_start(e: &mut crate::engine::Engine, t: &mut u64) {
    let mut status = |_: &str| {};
    e.step(Event::Slot { slot: 100, status: 0, t: *t, parent: Some(99), dead_error: None, bank_id: None }, *t, &mut status);
    e.step(Event::Input { kind: InputKind::BlockhashHead, data: Arc::new(json!({ "hash": b58(&BH), "slot": 99, "height": 89, "src": "slotidx",
        "commitment": "confirmed", "t_ns": *t })) }, *t, &mut status);
    e.step(Event::Input { kind: InputKind::LeaderWindow, data: Arc::new(window_json()) }, *t, &mut status);
    *t += 6_000_000;
    e.timers(*t, &mut status);
}

/// one transaction moving pool `m` to `sol` SOL at slot 100; its group resolves by quiescence at the timers 4 ms later
fn amm_move(e: &mut crate::engine::Engine, m: &PoolMeta, n: u8, sol: u64, t: &mut u64) {
    let mut status = |_: &str| {};
    let txn = [n + 50; 64];
    for (k, data) in [(m.vault1, amm_vault(sol * 1_000_000_000)), (m.vault0, amm_vault(1_000_000_000_000_000 - n as u64))] {
        *t += 1_000;
        e.step(Event::Account { slot: 100, pubkey: k, owner: [3; 32], lamports: 1, data, t: *t, txn: Some(txn), write_version: *t, is_startup: false,
            src: 0, aseq: 0, bank_id: None }, *t, &mut status);
    }
    *t += 4_000_000;
    e.timers(*t, &mut status);
}

/// the journal's decision-point records (INPUT 3 `gate`, `src` "decision") of what the send checks read (WP-09 part 2's
/// `sent` records, a send's signature, apart: `sent_records`)
fn decision_records(dir: &std::path::Path) -> Vec<(usize, Value)> {
    use crate::rec::journal::{self, JBody};
    journal::read_dir(dir).unwrap().iter().enumerate().filter_map(|(i, r)| match &r.body {
        JBody::Input { kind: 3, data } if data["src"] == "decision" && data.get("sent").is_none() => Some((i, data.clone())),
        _ => None,
    }).collect()
}

/// ---- WP-09 part 2. The journal's `sent` records (a live or canary send's attempt and signature, right after its decision)
fn sent_records(dir: &std::path::Path) -> Vec<(usize, Value)> {
    use crate::rec::journal::{self, JBody};
    journal::read_dir(dir).unwrap().iter().enumerate().filter_map(|(i, r)| match &r.body {
        JBody::Input { kind: 3, data } if data["src"] == "decision" && data.get("sent").is_some() => Some((i, data.clone())),
        _ => None,
    }).collect()
}

/// PLAN-ADDENDUM I-7: a shadow run with an engine runs every send check up to the signature. A decision that passes them
/// all but the SendGate is a would-send, recorded with `sent = false` in decisions.jsonl (with its attempt) and in
/// attempts.jsonl (built, unsigned); one another check refuses says which (`reason_ungated`). What each decision saw from
/// outside (the gate, the leader's kind, the token, the recorder) is journaled at the decision when it changes (WP-08
/// review #18): the leader's kind reaches replay. Review WP-05 #9: decisions.jsonl `band` is the attempt's (the
/// executor's, at the size it would trade), the engine's at its priced size is `band_at_opp`; #8: the engine notes each
/// attempt in the `poh_trigger_pct` gauge after the decision
#[tokio::test]
async fn a_shadow_run_records_would_sends() {
    let mut r = rig("shadow-engine", Mode::Shadow, "[send_policy]\nbig_band_max_per_sec = 1000\n").await;
    let gate = SendGate::new();
    let _ = gate.shadow("mode_shadow", "no --live or --canary: nothing is sent", true);
    let (mut e, a, b) = amm_engine();
    e.set_rec(r.rec.clone());
    let mut x = std::mem::replace(&mut r.x, idle_exec());
    x.set_gate(gate);
    x.set_health(e.health_flags());
    e.exec = Some(x);
    let mut t = now_ns();
    amm_start(&mut e, &mut t);
    amm_move(&mut e, &a, 0, 1_030, &mut t);
    amm_move(&mut e, &b, 1, 1_060, &mut t);
    // the third one while the target slot's leader is of another kind (a new window, journaled; the LeaderBook agrees)
    let mut status = |_: &str| {};
    e.step(Event::Input { kind: InputKind::LeaderWindow, data: Arc::new(json!({ "start": 101, "leaders": [b58(&LO)] })) }, t, &mut status);
    r.book.add_window(101, &[LO]);
    amm_move(&mut e, &a, 2, 1_090, &mut t);
    r.rec.sync();
    let d: Vec<Value> = rec::read_jsonl(&r.dir, "decisions").unwrap().into_iter().filter(|l| l["opp"].is_u64()).collect();
    assert_eq!(d.len(), 3, "{d:?}");
    for l in &d[..2] {
        assert_eq!((l["verdict"].as_str(), l["reason"].as_str(), l["would_send"].as_bool(), l["sent"].as_bool()),
            (Some("reject"), Some("gate_shadow:mode_shadow"), Some(true), Some(false)), "{l}");
        assert!(l["attempt"].is_u64() && l["reason_ungated"].is_null() && l["ev"].is_i64() && l["crowding"]["src"].as_str() == Some("map_partial"), "{l}");
    }
    assert_eq!((d[2]["would_send"].as_bool(), d[2]["reason_ungated"].as_str(), d[2]["attempt"].is_null(), d[2]["sent"].is_null()),
        (Some(false), Some("leader_skip_kind"), true, true), "{}", d[2]);
    let att = rec::read_jsonl(&r.dir, "attempts").unwrap();
    assert_eq!(att.len(), 2);
    for (k, l) in att.iter().enumerate() {
        assert_eq!((l["kind"].as_str(), l["sent"].as_bool(), l["not_sent"].as_str(), l["tx"]["sig"].is_null()), (Some("shadow"), Some(false), Some("gate_shadow:mode_shadow"), true));
        assert_eq!((l["attempt"].as_u64(), l["decision"].clone(), l["blockhash"]["slot"].as_u64(), l["blockhash"]["age_slots"].as_u64(), l["leader"]["kind"].as_str()),
            (Some(k as u64), d[k]["decision"].clone(), Some(99), Some(1), Some("jito")));
        assert!(l["tx"]["bytes"].as_u64().unwrap() <= build::MAX_TX_BYTES as u64 && l["dry_run"].is_null(), "built, not signed");
        assert!(l["tip"]["lamports"].as_u64().unwrap() >= 1_000 && l["min_profit_onchain"].as_u64().unwrap() > l["tip"]["lamports"].as_u64().unwrap());
        assert_eq!((d[k]["band"].as_u64(), d[k]["band_at_opp"].is_u64()), (l["band"].as_u64(), true), "the band the attempt was queued and tipped by");
        assert_eq!(l["band"].as_u64(), Some(crate::bands::of_gross(l["expected"]["gross"].as_i64().unwrap()) as u64));
    }
    assert_eq!(r.gauge.status(&[], now_ns())["attempts_total"].as_u64(), Some(2), "the engine noted both attempts' triggers");
    let x = e.exec.as_ref().unwrap();
    assert_eq!((x.counts.get("would_send").copied(), x.counts.get("reject_gate_shadow").copied(), x.net_calls()), (Some(2), Some(3), 0));
    r.rec.close();
    let seen: Vec<(String, String, bool)> = decision_records(&r.dir).into_iter()
        .map(|(_, d)| (d["mode"].as_str().unwrap().to_string(), d["leader"]["kind"].as_str().unwrap().to_string(), d["jito_token_ok"].as_bool().unwrap())).collect();
    assert_eq!(seen, vec![("shadow".into(), "jito".into(), true), ("shadow".into(), "other".into(), true)], "one record per change");
}

/// review WP-03 #3, on the WP-05 executor: the SendGate mode each send check saw is journaled on the engine thread at the
/// decision (INPUT gate, `src` "decision", with the opportunity) whenever it differs from the last one journaled; the
/// live gate still decides (a pause closes the very next check; the first decision was sent)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_gate_each_send_check_saw_is_journaled() {
    use crate::rec::journal::{self, JBody};
    let mut r = rig("gatej", Mode::Live, "[send_policy]\nbig_band_max_per_sec = 1000\n").await;
    let gate = SendGate::new();
    let (mut e, a, b) = amm_engine();
    e.set_rec(r.rec.clone());
    let mut x = std::mem::replace(&mut r.x, idle_exec());
    x.set_gate(gate.clone());
    x.set_health(e.health_flags());
    e.exec = Some(x);
    let mut t = now_ns();
    amm_start(&mut e, &mut t);
    amm_move(&mut e, &a, 0, 1_030, &mut t);
    gate.shadow("control", "pause-sending by test", false).unwrap();
    amm_move(&mut e, &b, 1, 1_060, &mut t);
    amm_move(&mut e, &a, 2, 1_090, &mut t);
    let x = e.exec.as_ref().unwrap();
    assert_eq!((x.counts.get("reject_gate_shadow").copied(), x.gate_seen()), (Some(2), Some(GateMode::Shadow)), "the live gate decided the last two");
    assert_eq!(x.counts.get("live_sent").copied(), Some(1), "the first was sent");
    let _ = r.settled().await;
    assert_eq!(r.got.lock().unwrap().len(), 1);
    r.rec.close();
    let recs = decision_records(&r.dir);
    assert_eq!(recs.iter().map(|(_, d)| (d["mode"].as_str().unwrap().to_string(), d["opp"].as_u64().unwrap())).collect::<Vec<_>>(),
        vec![("live".to_string(), 0), ("shadow".to_string(), 1)], "one record per change, at the decision that saw it");
    let (i, d) = &recs[1];
    assert_eq!((d["reason"].as_str(), d["leader"]["kind"].as_str(), d["jito_token_ok"].as_bool(), d["recorder_ok"].as_bool()),
        (Some("control"), Some("jito"), Some(true), Some(true)));
    let j = journal::read_dir(&r.dir).unwrap();
    assert!(matches!(j[i - 1].body, JBody::Timer { .. }) && j[i - 1].t_engine == j[*i].t_engine, "{:?}", j[i - 1]);
    // WP-09 part 2: the send journaled its attempt's signature right after its decision (a replay sends with it): the
    // signature the block engine got, at the decision's engine time, after the record of what its checks read
    let sent = sent_records(&r.dir);
    assert_eq!(sent.len(), 1, "{sent:?}");
    let (k, s) = &sent[0];
    let got = crate::send::first_signature(&r.got.lock().unwrap()[0].0).unwrap();
    assert_eq!((s["opp"].as_u64(), s["sent"]["attempt"].as_u64(), s["sent"]["sig"].as_str()), (Some(0), Some(0), Some(got.as_str())));
    assert!(*k > recs[0].0 && j[*k].t_engine == j[recs[0].0].t_engine, "right after the decision's own record");
}

// ------------------------------------------------------------------------------------------------ the dry run

/// Go-live gate item 4: a dry run builds and signs at least 100 would-send bundles and sends none. Each is recorded in
/// full (the signed transaction, its size, tip and accounts, the checks it passed); its signature is the throwaway key's
/// (it verifies with that key and not with the payer's: it could not land even if it left). Transmitting is impossible: a
/// dry-run executor refuses send paths at its start (`exec_new_refuses_what_its_mode_forbids`), drops any it is handed,
/// holds no Jito client and no trading key; the in-memory block engine behind the paths it was handed receives nothing;
/// the send path makes no network call. The would-sends follow the bundle path's rate (5 a second)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_dry_run_signs_and_never_sends() {
    let mut r = rig("dry", Mode::DryRun, "").await;
    // send paths to a block engine in memory, handed to a dry-run executor anyway
    let j = Jito::for_test(Rec::off());
    j.set_cached(Some(fresh_token()));
    let got = fake_engine(&j);
    let paths = Paths::for_test(vec![Path::test_bundle(j.clone(), Some(5), 10)], Rec::off());
    let (tx, rx) = crossbeam_channel::unbounded();
    let held: HashSet<Pk> = [*WSOL, MINT].into_iter().collect();
    let mut x = Exec::assemble(&test_cfg(&r.dir, ""), Rpc::race(vec![]), Some(paths), r.rec.clone(), tx, vec![], vec![], None, held, Mode::DryRun, Some(dry_key())).unwrap();
    assert!(x.paths.is_none() && x.bundle_path.is_none() && x.jito.is_none() && x.key.is_none(), "no path, no block engine, no trading key");
    assert_eq!(x.dry_signer(), Some(dry_key().verifying_key().to_bytes()));
    x.set_health(r.health.clone());
    x.set_leaders(r.book.clone());
    x.poh_gauge = r.gauge;
    r.x = x;
    assert!(r.x.gate.allows(), "the gate is open: still nothing may leave");
    let payer = wallet_key().verifying_key().to_bytes();
    let signer = dry_key().verifying_key();
    let tips = tip_accounts();
    let mut t = now_ns();
    for k in 0..120u64 {
        let n = (k % 50) as u8 * 2 + 1;
        let d = r.decide(route(n, damm(n + 1, MINT), 50_000 + k * 1_000, k), 100, t);
        assert_eq!((d.would_send, d.sent, d.reason.as_str(), d.attempt), (true, Some(false), "would_send", Some(k)), "{k}: {d:?}");
        t += S / 4;
    }
    tokio::time::sleep(std::time::Duration::from_millis(50)).await;
    assert!(got.lock().unwrap().is_empty(), "nothing reached the block engine");
    assert_eq!(r.x.net_calls(), 0, "no network call");
    assert!(rx.try_iter().all(|e| !matches!(e, Event::Settled(_))), "nothing was fired");
    let a = r.lines("attempts");
    assert_eq!(a.len(), 120);
    for l in &a {
        assert_eq!((l["kind"].as_str(), l["sent"].as_bool(), l["not_sent"].as_str()), (Some("dry_run"), Some(false), Some("dry_run")));
        let dr = &l["dry_run"];
        assert_eq!((dr["checks_ok"].as_bool(), dr["signer"].as_str(), dr["simulated"].as_bool()), (Some(true), Some(b58(&signer.to_bytes()).as_str()), Some(false)), "{dr}");
        let raw = { use base64::Engine as _; base64::engine::general_purpose::STANDARD.decode(dr["tx_b64"].as_str().unwrap()).unwrap() };
        assert_eq!((Some(raw.len() as u64), dr["bytes"].as_u64()), (l["tx"]["bytes"].as_u64(), Some(raw.len() as u64)), "the size as built");
        assert!(raw.len() <= build::MAX_TX_BYTES);
        let names: Vec<&str> = dr["checks"].as_array().unwrap().iter().map(|c| c["check"].as_str().unwrap()).collect();
        assert_eq!(names, ["parses", "one_signature", "signature_verifies", "payer_is_wallet", "size", "accounts_resolve", "locks", "blockhash", "cu_limit", "no_cu_price",
            "tip_last", "tip_to_jito", "tip_check", "route_program", "pools_named", "route_data", "route_amount_in", "route_min_profit", "min_profit_covers_tip",
            "route_accounts", "route_payer_accounts", "ix_order", "loaded_data_limit", "ata_create", "ata_close", "rent_returns", "held_addition", "route_guard"]);
        // the route as signed: the decision's size and on-chain min_profit (review #12)
        let route = dr["checks"].as_array().unwrap().iter().find(|c| c["check"] == "route_min_profit").unwrap();
        assert_eq!((route["detail"]["signed"].as_u64(), l["min_profit_onchain"].as_u64()), (route["detail"]["want"].as_u64(), route["detail"]["want"].as_u64()));
        // the tip as recorded is what the transaction pays to a Jito tip account, last
        let (tx, _) = crate::tx::parse_wire(&raw).unwrap();
        assert_eq!(send::tip_paid(&tx, &tips), l["tip"]["lamports"].as_u64().unwrap());
        assert_eq!((tx.keys[0], tx.num_signers), (payer, 1), "the payer is the wallet, the only signer");
        let accts = dr["accounts"].as_array().unwrap();
        assert_eq!((accts[0]["key"].as_str(), accts[0]["signer"].as_bool(), accts[0]["writable"].as_bool()), (Some(b58(&payer).as_str()), Some(true), Some(true)));
        assert_eq!(accts.iter().filter(|x| x["signer"] == json!(true)).count(), 1);
        // the signature is the throwaway key's, never the payer's: it cannot pass on chain
        use ed25519_dalek::Verifier;
        let sig = ed25519_dalek::Signature::from_bytes(raw[1..65].try_into().unwrap());
        assert!(signer.verify(&raw[65..], &sig).is_ok());
        assert!(ed25519_dalek::VerifyingKey::from_bytes(&payer).unwrap().verify(&raw[65..], &sig).is_err());
        assert_eq!(l["tx"]["sig"].as_str(), c_sig(&raw).as_deref());
    }
    assert_eq!((r.n("dry_run_ok"), r.n("dry_run_check_failed"), r.n("would_send")), (120, 0, 120));
    // the bundle path's rate: of 7 would-sends in one instant, 5 go and 2 are refused by the rate model (`would_rate`, not
    // the queue's own `rate_queue_timeout`: review #10)
    t += 2 * S;
    let reasons: Vec<String> = (0..7u64).map(|k| r.decide(route(101, damm(102, MINT), 50_000, 1_000 + k), 100, t).reason).collect();
    assert_eq!(reasons.iter().filter(|x| *x == "would_send").count(), 5, "{reasons:?}");
    assert_eq!(reasons.iter().filter(|x| *x == "would_rate").count(), 2, "{reasons:?}");
    let mut c = route(105, damm(106, MINT), 50_000, 2_000);
    c.crowding = Crowding { signers_6h: None, bucket: 2, src: "static_list" };
    assert_eq!(r.decide(c, 100, t).reason, "would_rate_crowded", "a crowded route over the modelled rate");
    // a signed would-send whose bytes were tampered with fails its checks
    let raw = { use base64::Engine as _; base64::engine::general_purpose::STANDARD.decode(a[0]["dry_run"]["tx_b64"].as_str().unwrap()).unwrap() };
    let mut bad = raw.clone();
    let (ptx, _) = crate::tx::parse_wire(&raw).unwrap();
    bad[65 + 4 + 1 + 32 * ptx.keys.len()] ^= 1;
    let tip0 = (pk(a[0]["tip"]["account"].as_str().unwrap()), a[0]["tip"]["lamports"].as_u64().unwrap());
    let want = VerifyWant { signer: signer.to_bytes(), ..live_want(&r.x, Some(tip0), a[0]["min_profit_onchain"].as_u64().unwrap()) };
    assert!(verify_bundle(&raw, &want).iter().all(|c| c["ok"] == json!(true)));
    let failed: Vec<String> = verify_bundle(&bad, &want).iter().filter(|c| c["ok"] != json!(true)).map(|c| c["check"].as_str().unwrap().to_string()).collect();
    assert_eq!(failed, ["signature_verifies", "blockhash"], "one bit of the blockhash");
}

/// The dry run from its start (`Exec::new`, through a local mock RPC): it reads accounts (the lookup tables, PumpSwap's
/// GlobalConfig, the wallet's token accounts) and, with `[dry_run] simulate`, simulates its signed would-sends read-only
/// (`simulateTransaction`, sigVerify off: the throwaway key is not the payer; the blockhash kept, so its age is checked),
/// at most `max_sim_per_sec` a second. It calls no method that sends. Each simulation is written to sims.jsonl with its
/// attempt; none is on the send path (its network-call counter stays 0)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_dry_run_reads_and_simulates_only() {
    let m = crate::rpc::mock::MockRpc::start();
    m.slot.store(500, Relaxed);
    let payer = wallet_key().verifying_key().to_bytes();
    // initialized token accounts (state 1 at 108: WP-06 reads a held account as one that exists)
    let acct = { let mut d = [0u8; 165]; d[108] = 1; d };
    for mint in [*WSOL, MINT] { m.set(build::ata_of(&payer, &mint, &crate::pda::TOKEN_PROGRAM), &acct); }
    let dir = test_dir("dry-sim");
    let rec = test_rec(&dir);
    let cfg = test_cfg(&dir, "[exec]\nrpc = [\"mock\"]\n[dry_run]\nsimulate = true\nmax_sim_per_sec = 2\n");
    let rpc = Rpc::race(vec![crate::rpc::Endpoint { name: "mock".into(), url: m.url.clone(), bearer: None }]);
    let (tx, rx) = crossbeam_channel::unbounded();
    let (x, notes) = Exec::new(&cfg, &rpc, None, rec.clone(), tx, vec![], Mode::DryRun, Some(dry_key()), vec![(MINT, *crate::pda::TOKEN_PROGRAM)]).await.unwrap();
    assert!(notes.iter().any(|n| n.starts_with("DRY RUN") && n.contains("simulated read-only")), "{notes:?}");
    // WP-06: the wallet's PumpSwap user volume accumulator was read with its token accounts (the mock has none)
    assert!(notes.iter().any(|n| n.contains("no PumpSwap user volume accumulator") && n.contains("uva_missing")), "{notes:?}");
    assert_eq!(x.uva, Some(false));
    let mut held = vec![b58(&WSOL), b58(&MINT)];
    held.sort();
    assert_eq!(x.held_mints(), held);
    let mut r = Rig { x, dir, rec, rx, got: Got::default(), jito: None, view: view(), health: Arc::new(HealthFlags::default()), gauge: Box::leak(Box::new(PohGauge::new())),
        book: book(), buffered: Vec::new() };
    r.health.set(Shut::Ready);
    r.x.set_health(r.health.clone());
    r.x.set_leaders(r.book.clone());
    r.x.poh_gauge = r.gauge;
    let t = now_ns();
    for k in 0..3u8 { assert_eq!(r.decide(route(1 + 2 * k, damm(2 + 2 * k, MINT), 50_000, 1), 100, t).reason, "would_send"); }
    let mut sims = Vec::new();
    for _ in 0..2 {
        let Settled::DrySim { attempt, line } = r.settled().await else { panic!("a dry run's simulation") };
        sims.push(attempt);
        r.x.on_settled(Settled::DrySim { attempt, line }, now_ns(), &|_| None);
    }
    sims.sort();
    assert_eq!(sims, vec![0, 1], "at most 2 a second");
    let a = r.lines("attempts");
    assert_eq!(a.iter().map(|l| l["dry_run"]["simulated"].as_bool().unwrap()).collect::<Vec<_>>(), vec![true, true, false]);
    let s = r.lines("sims");
    assert_eq!(s.len(), 2);
    assert!(s.iter().all(|l| l["src"] == "dry_run" && l["sim_slot"] == 500 && l["sim_error"].is_null() && l["attempt"].is_u64()), "{s:?}");
    // the RPC calls: account reads at the start, then two read-only simulations of the signed would-sends
    let reqs = m.reqs.lock().unwrap().clone();
    let methods: Vec<&str> = reqs.iter().map(|q| q["method"].as_str().unwrap()).collect();
    assert!(methods.iter().all(|x| *x == "getMultipleAccounts" || *x == "simulateTransaction"), "{methods:?}");
    let sim_reqs: Vec<&Value> = reqs.iter().filter(|q| q["method"] == "simulateTransaction").collect();
    assert_eq!(sim_reqs.len(), 2);
    for q in &sim_reqs {
        assert_eq!((q["params"][1]["sigVerify"].as_bool(), q["params"][1]["replaceRecentBlockhash"].as_bool()), (Some(false), Some(false)));
        assert!(a.iter().any(|l| l["dry_run"]["tx_b64"] == q["params"][0]), "the would-send as recorded");
        let raw = { use base64::Engine as _; base64::engine::general_purpose::STANDARD.decode(q["params"][0].as_str().unwrap()).unwrap() };
        assert_eq!(crate::tx::parse_wire(&raw).unwrap().0.keys[0], payer);
    }
    assert_eq!(r.x.net_calls(), 0, "the simulations run after the decision, off the send path");
}

// ------------------------------------------------------------------------------------------------ review WP-05 fixes

/// A live executor like the rig's whose in-memory block engine answers with `engine` (it may refuse, or not answer)
fn with_engine(r: &mut Rig, engine: Arc<crate::send::jito::FakeEngine>) -> Arc<Jito> {
    let j = Jito::for_test(r.rec.clone());
    j.set_cached(Some(fresh_token()));
    j.set_fake_result(engine);
    let cfg = test_cfg(&r.dir, "");
    let paths = Paths::for_test(vec![Path::test_bundle(j.clone(), Some(5), cfg.send_policy.queue_ms)], r.rec.clone());
    let (tx, rx) = crossbeam_channel::unbounded();
    let held: HashSet<Pk> = [*WSOL, MINT].into_iter().collect();
    let mut x = Exec::assemble(&cfg, Rpc::race(vec![]), Some(paths), r.rec.clone(), tx, vec![], vec![], None, held, Mode::Live, Some(wallet_key())).unwrap();
    x.set_health(r.health.clone());
    x.set_leaders(r.book.clone());
    x.poh_gauge = r.gauge;
    r.x = x;
    r.rx = rx;
    r.jito = Some(j.clone());
    j
}

/// Review WP-05 #2: final means a landing or the blockhash's expiry (PLAN WP-07). A block-engine result that is not a
/// landing (would-fail, lost auction, dropped, rejected), through the Jito client's sink as the engine gets it, keeps
/// the in-flight entry: the same state version goes neither to the same leader at the same slot nor at its later slot
/// until the hold ends; a landing (`processed`) releases it. One bundle's several would-fails count once toward its
/// token's cooling
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_would_fail_keeps_the_lock() {
    let mut r = rig("wf-lock", Mode::Live, "").await;
    let t = now_ns();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 100, t).reason, "sent");
    let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
    r.x.on_settled(Settled::Fired { attempt, fired }, t, &|_| None);
    let j = r.jito.clone().unwrap();
    let res = |outcome: &'static str, detail: Option<&str>| Outcome { bundle: "b0".into(), outcome, slot: Some(101), index: None, bid: None, detail: detail.map(String::from),
        validator: None };
    for (o, d) in [("accepted", None), ("would-fail", Some("custom program error: 0x4e580002")), ("would-fail", Some("custom program error: 0x4e580002")),
        ("lost-auction", None), ("dropped", None), ("rejected", Some("boom"))] {
        j.on_result_at(res(o, d), t + 1);
    }
    let rel = r.releases();
    assert_eq!(rel.len(), 6);
    assert!(rel.iter().all(|d| d["release"] == json!(false)), "{rel:?}");
    for d in &rel { r.x.on_release(d, t + 2); }
    assert_eq!((r.x.inflight.len(), r.n("inflight_released")), (1, 0), "nothing released the entry");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 100, t + 3).reason, "inflight_same_state", "the same state, leader and slot");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 101, t + 4).reason, "sent", "the next slot's leader is another (BAM): allowed, as planned");
    let Settled::Fired { attempt: a1, fired } = r.settled().await else { panic!("a fire result") };
    r.x.on_settled(Settled::Fired { attempt: a1, fired }, t, &|_| None);
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 102, t + 5).reason, "inflight_same_leader");
    assert_eq!((r.x.mint_cool.get(&MINT).map(|c| c.0), r.n("cool_repeat"), r.n("verdict_would_fail")), (Some(1), 1, 2), "one would-fail for the attempt");
    // the hold ends 2 slots past the target slot: the same state may go again
    r.x.tick(t + 6, &r.view, 104);
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 104, t + 7).reason, "sent", "the hold passed");
    // a landing releases its entry at once
    let Settled::Fired { attempt: a2, fired } = r.settled().await else { panic!("a fire result") };
    assert_eq!((a1, a2), (1, 2));
    r.x.on_settled(Settled::Fired { attempt: a2, fired }, t, &|_| None);
    let b = r.x.open.get(&a2).and_then(|o| o.bundle.clone()).unwrap();
    j.on_result_at(Outcome { bundle: b, outcome: "processed", slot: Some(103), index: Some(1), bid: None, detail: None, validator: None }, t + 8);
    let rel = r.releases();
    assert_eq!(rel.iter().map(|d| (d["outcome"].as_str(), d["release"].as_bool())).collect::<Vec<_>>(), vec![(Some("processed"), Some(true))]);
    let before = r.x.inflight.len();
    r.x.on_release(&rel[0], t + 9);
    assert_eq!((r.x.inflight.len(), r.n("inflight_released")), (before - 1, 1));
}

/// Review WP-05 #7: a copy that left but got no answer (a timeout, a transport error) may still land. It stays open (its
/// in-flight entry and its fee reservation kept), is cross-checked and settled by its landing or its blockhash's expiry,
/// with the send error on its final line. A copy the block engine refused (it answered) cannot land: final at once,
/// its entry and reservation given back
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_send_without_an_answer_stays_open() {
    let mut r = rig("no-answer", Mode::Live, "").await;
    let calls = Arc::new(AtomicU64::new(0));
    let c2 = calls.clone();
    let _j = with_engine(&mut r, Arc::new(move |_txs: &[&[u8]]| match c2.fetch_add(1, Relaxed) {
        0 | 1 => Err(crate::send::jito::BundleError::Other(anyhow::anyhow!("/searcher.SearcherService/SendBundle: Unavailable transport error"))),
        _ => Err(crate::send::jito::BundleError::Refused(anyhow::anyhow!("/searcher.SearcherService/SendBundle: ResourceExhausted rate limited"))),
    }));
    let t = now_ns();
    let mut sigs = Vec::new();
    for k in 0..2u8 {
        assert_eq!(r.decide(route(1 + 2 * k, damm(2 + 2 * k, MINT), 50_000, 1), 100, t).reason, "sent");
        let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
        let c = &fired.copies[0];
        assert!(!c.ok && c.t_sent > 0 && c.t_ack == 0 && c.drop.is_none(), "it left, no answer: {c:?}");
        sigs.push(c.sig.clone().unwrap());
        r.x.on_settled(Settled::Fired { attempt, fired }, t, &|_| None);
    }
    assert_eq!((r.x.open_attempts(), r.x.reserved, r.n("send_unanswered"), r.n("not_landed_refused")), (vec![0, 1], 2 * 5_000, 2, 0), "open, reserved");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t + 1).reason, "inflight_same_state", "its entry holds");
    // attempt 0 had arrived after all: the wallet stream records it
    r.x.on_wallet_tx(&json!({ "sig": sigs[0], "attempt": 0, "slot": 101, "idx": 2, "ok": true, "err": null, "fee": 5_000, "cu_consumed": 80_000,
        "prog_events": [{ "kind": "out", "leg": 0, "amount": 9 }, { "kind": "out", "leg": 1, "amount": SIZE + 20_000 }] }), now_ns(), &|_| None);
    // attempt 1 did not: its blockhash expires, the expiry check finds nothing
    r.x.on_settled(Settled::Statuses { why: "expiry", at: vec![(1, "expiry")], result: Ok(vec![None]), t_ns: t }, t, &|_| None);
    let o = r.lines("outcomes");
    assert_eq!((o[0]["final"].as_str(), o[0]["final_src"].as_str(), o[0]["round_trip_on_chain"].as_i64()), (Some("landed_ok"), Some("wallet"), Some(20_000)));
    assert_eq!((o[1]["final"].as_str(), o[1]["final_src"].as_str()), (Some("not_landed_expired"), Some("expiry")));
    assert!(o[1]["error"].as_str().is_some_and(|e| e.starts_with("send:") && e.contains("Unavailable")), "{}", o[1]);
    assert_eq!(r.x.reserved, 0);
    // a refusal (the block engine answered): final at once, the entry and the reservation back
    assert_eq!(r.decide(route(5, damm(6, MINT), 50_000, 1), 100, t + 2).reason, "sent");
    let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
    let c = &fired.copies[0];
    assert!(!c.ok && c.t_sent > 0 && c.t_ack > 0 && c.drop.is_none(), "answered: {c:?}");
    r.x.on_settled(Settled::Fired { attempt, fired }, t, &|_| None);
    let last = r.lines("outcomes").last().cloned().unwrap();
    assert_eq!((last["final"].as_str(), last["final_src"].as_str()), (Some("not_landed_refused"), Some("send")));
    assert!(last["error"].as_str().is_some_and(|e| e.contains("ResourceExhausted")), "{last}");
    assert_eq!((r.x.reserved, r.n("send_refused"), r.x.never_left), (0, 1, 0));
    assert_eq!(r.decide(route(5, damm(6, MINT), 50_000, 1), 100, t + 3).reason, "sent", "the entry came back");
}

/// Review WP-05 #12 (go-live gate item 4): the dry run decodes the route instruction from the signed bytes. A builder
/// that signs a min_profit other than the decision's (here 1: a landed bundle could lose its tip and fee) or another
/// amount_in fails the dry run's checks, while every other check passes; the attempt records which
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_dry_run_catches_a_wrong_min_profit() {
    let mut r = rig("dry-mp", Mode::DryRun, "").await;
    let t = now_ns();
    let failed = |l: &Value| l["dry_run"]["checks"].as_array().unwrap().iter().filter(|c| c["ok"] != json!(true)).map(|c| c["check"].as_str().unwrap().to_string()).collect::<Vec<_>>();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t).reason, "would_send");
    let good = r.lines("attempts")[0].clone();
    assert_eq!((good["dry_run"]["checks_ok"].as_bool(), failed(&good)), (Some(true), Vec::<String>::new()));
    let mp = good["min_profit_onchain"].as_u64().unwrap();
    assert_eq!(mp, 31_499 + 5_000 + 1, "the tip (70% of the 45,000 edge) + the base fee + the margin floor");
    // the builder signs min_profit 1
    r.x.fault_route = Some((SIZE, 1));
    assert_eq!(r.decide(route(3, damm(4, MINT), 50_000, 1), 100, t + S).reason, "would_send");
    let bad = r.lines("attempts")[1].clone();
    assert_eq!((bad["min_profit_onchain"].as_u64(), bad["dry_run"]["checks_ok"].as_bool()), (Some(mp), Some(false)), "the decision's value is recorded, the signed one is not it");
    assert_eq!(failed(&bad), ["route_min_profit", "min_profit_covers_tip"]);
    let c = bad["dry_run"]["checks"].as_array().unwrap().iter().find(|c| c["check"] == "route_min_profit").unwrap().clone();
    assert_eq!((c["detail"]["signed"].as_u64(), c["detail"]["want"].as_u64()), (Some(1), Some(mp)));
    // the builder signs another amount
    r.x.fault_route = Some((999_999_999, mp));
    assert_eq!(r.decide(route(5, damm(6, MINT), 50_000, 1), 100, t + 2 * S).reason, "would_send");
    assert_eq!(failed(&r.lines("attempts")[2]), ["route_amount_in"]);
    assert_eq!((r.n("dry_run_ok"), r.n("dry_run_check_failed")), (1, 2));
    // a signed min_profit that is the decision's but does not cover the tip, the fee and the margin is caught too
    let raw = { use base64::Engine as _; base64::engine::general_purpose::STANDARD.decode(good["dry_run"]["tx_b64"].as_str().unwrap()).unwrap() };
    let tip0 = (pk(good["tip"]["account"].as_str().unwrap()), good["tip"]["lamports"].as_u64().unwrap());
    let want = VerifyWant { signer: dry_key().verifying_key().to_bytes(), margin_floor: 2, ..live_want(&r.x, Some(tip0), mp) };
    let names: Vec<String> = verify_bundle(&raw, &want).iter().filter(|c| c["ok"] != json!(true)).map(|c| c["check"].as_str().unwrap().to_string()).collect();
    assert_eq!(names, ["min_profit_covers_tip"]);
    // the same bytes with min_profit set to 1 and signed again (a valid signature over a wrong value): caught
    let mut bad = raw.clone();
    let (tx, _) = crate::tx::parse_wire(&raw).unwrap();
    let ix = tx.ixs.iter().find(|ix| tx.keys[ix.program as usize] == r.x.program).unwrap();
    let at = raw.windows(ix.data.len()).position(|w| w == &ix.data[..]).unwrap();
    bad[at + 10..at + 18].copy_from_slice(&1u64.to_le_bytes());
    use ed25519_dalek::Signer;
    let sig = dry_key().sign(&bad[65..]).to_bytes();
    bad[1..65].copy_from_slice(&sig);
    let want = VerifyWant { signer: dry_key().verifying_key().to_bytes(), ..live_want(&r.x, Some(tip0), mp) };
    let names: Vec<String> = verify_bundle(&bad, &want).iter().filter(|c| c["ok"] != json!(true)).map(|c| c["check"].as_str().unwrap().to_string()).collect();
    assert_eq!(names, ["route_min_profit", "min_profit_covers_tip"], "the signature verifies; the signed value is wrong");
}

/// Review WP-05 #16: a canary attempt whose copy never left (the rate queue dropped it) is not one of the canary's
/// `count` attempts
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_dropped_canary_send_is_not_counted() {
    let mut r = rig("canary-drop", Mode::Canary, "[canary]\nenabled = true\ncount = 2\nevery_ms = 1000\nsize_sol = 0.05\nmax_spend_lamports = 20000\n").await;
    let t = now_ns();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t).reason, "sent");
    let Settled::Fired { attempt, fired: mut f } = r.settled().await else { panic!("a fire result") };
    f.copies[0].t_sent = 0;
    f.copies[0].ok = false;
    f.copies[0].drop = Some("rate_queue_timeout");
    r.x.on_settled(Settled::Fired { attempt, fired: f }, t, &|_| None);
    assert_eq!(r.decide(route(3, damm(4, MINT), 50_000, 1), 100, t + S + 1).reason, "sent");
    assert_eq!(r.decide(route(5, damm(6, MINT), 50_000, 1), 100, t + 2 * S + 2).reason, "sent", "the dropped one did not count");
    assert_eq!(r.decide(route(7, damm(8, MINT), 50_000, 1), 100, t + 3 * S + 3).reason, "canary_count");
    assert_eq!((r.x.never_left, r.n("drop_rate_queue_timeout"), r.n("canary_sent")), (1, 1, 3));
}

/// Review WP-05 #15, #10, #16: the round trip is the last leg's output (any number of legs); the reasons and their
/// counters: `crowded_skip` (not sent by policy), the queue's drops `crowded_pool` / `rate_queue_timeout` (`drop_*`), the
/// would-send rate model's `would_rate` / `would_rate_crowded`, `ungated_*` behind a closed gate
#[test]
fn round_trips_reasons_and_counters() {
    let ev = |v: Value| last_leg_out(&v);
    assert_eq!(ev(json!([{ "kind": "out", "leg": 0, "amount": 5 }, { "kind": "out", "leg": 1, "amount": 9 }])), Some(9));
    assert_eq!(ev(json!([{ "kind": "out", "leg": 0, "amount": 5 }, { "kind": "out", "leg": 1, "amount": 7 }, { "kind": "out", "leg": 2, "amount": 11 }])), Some(11), "three legs");
    assert_eq!(ev(json!([{ "kind": "out", "leg": 2, "amount": 11 }, { "kind": "out", "leg": 0, "amount": 5 }])), Some(11), "by leg, not order");
    assert_eq!(ev(json!([{ "kind": "out", "amount": 3 }, { "kind": "out", "amount": 4 }])), Some(4), "without leg numbers: the last");
    assert_eq!((ev(json!([{ "kind": "leg", "leg": 0 }])), ev(Value::Null)), (None, None));
    for (r, c, u) in [("crowded_skip", "reject_crowded_skip", "ungated_crowded_skip"), ("would_rate", "reject_would_rate", "ungated_would_rate"),
        ("would_rate_crowded", "reject_would_rate_crowded", "ungated_would_rate_crowded"), ("gate_shadow:control", "reject_gate_shadow", "ungated_gate_shadow"),
        ("build_error:buy leg: x", "reject_build_error", "ungated_build_error"), ("nonsense", "reject_other", "ungated_other")] {
        assert_eq!((reject_counter(r), ungated_counter(r)), (c, u), "{r}");
    }
    assert_eq!((drop_counter("crowded_pool"), drop_counter("rate_queue_timeout"), drop_counter("bad_tx"), drop_counter("x")),
        ("drop_crowded_pool", "drop_rate_queue_timeout", "drop_bad_tx", "drop_other"));
    assert_eq!(reject_counter("crowded_pool"), "reject_other", "the queue's drop is no decision's reason");
}

/// Probe (ignored; `cargo test --release --lib -- --ignored probe_ --nocapture --test-threads=1`): the engine thread's cost
/// of one decision that is built (a shadow would-send), signed and checked (a dry run) or signed and fired (live), and of
/// `inputs()` (review WP-05 #8: the leader read before the fire)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
#[ignore]
async fn probe_decide_costs() {
    for mode in [Mode::Shadow, Mode::DryRun, Mode::Live] {
        let mut r = rig(&format!("probe-{}", mode.as_str()), mode, "").await;
        if mode == Mode::Shadow { let g = SendGate::new(); let _ = g.shadow("mode_shadow", "probe", true); r.x.set_gate(g); }
        let mut t = now_ns();
        let mut v = Vec::new();
        let mut vi = Vec::new();
        for k in 0..400u64 {
            let n = (k % 100) as u8 * 2 + 1;
            let rt = route(n, damm(n + 1, MINT), 50_000 + k, k);
            let ti = std::time::Instant::now();
            let i = r.x.inputs(&r.view, 100, t);
            vi.push(ti.elapsed().as_nanos() as u64);
            let t0 = std::time::Instant::now();
            let d = r.x.decide(rt, &i, &r.view, &AltSource::none(), 100, t);
            v.push(t0.elapsed().as_nanos() as u64);
            assert!(d.attempt.is_some(), "{d:?}");
            t += S; // past the rate window
        }
        v.sort();
        vi.sort();
        println!("PROBE decide {}: p50 {:.1} us, p90 {:.1} us, p99 {:.1} us, max {:.1} us", mode.as_str(), v[200] as f64 / 1e3, v[360] as f64 / 1e3, v[396] as f64 / 1e3, v[399] as f64 / 1e3);
        println!("PROBE inputs {}: p50 {:.2} us, p90 {:.2} us, p99 {:.2} us (a 3-validator LeaderBook)", mode.as_str(), vi[200] as f64 / 1e3, vi[360] as f64 / 1e3, vi[396] as f64 / 1e3);
        if mode == Mode::Live {
            let (a, b) = (r.x.lat[0].pct(0.5), r.x.lat[0].pct(0.9));
            let (c, d) = (r.x.lat[1].pct(0.5), r.x.lat[1].pct(0.9));
            println!("PROBE live decided_to_signed p50 {:.1} us p90 {:.1} us; signed_to_fired p50 {:.1} us p90 {:.1} us", a as f64 / 1e3, b as f64 / 1e3, c as f64 / 1e3, d as f64 / 1e3);
        }
    }
}

// ------------------------------------------------------------------------------------------------ WP-09: the replay's forms

/// Review WP-09 "For the WP-05 merge" item 4: INPUT 9 `settled` reads back in each of WP-05's `{what: …}` forms (a fire
/// result with its copies, a drop code among them; a statuses answer, landed, not found and failed; a dry run's
/// simulation) as the same settlement: written again, the same body
#[test]
fn settlements_read_back_from_the_journal() {
    let copy = |drop: Option<&'static str>| send::Sent { attempt: 3, path: "jito-bundle".into(), sig: Some("5ig".into()), tip_account: Some(b58(&[9; 32])), tip_lamports: 1_000,
        t_sent: 11, t_ack: 12, ms: 1.5, ok: drop.is_none(), status: Some(200), reply: None, bundle: Some("b0".into()), blockhash_slot: Some(99), queue_wait_us: Some(40),
        drop, lambda: Some(4), endpoint: Some("fra.example".into()), leader_kind: Some("bam") };
    let all = vec![
        Settled::Fired { attempt: 3, fired: Fired { id: 3, t_ns: 10, copies: vec![copy(None), copy(Some("rate_queue_timeout")), copy(Some("crowded_pool"))] } },
        Settled::Statuses { why: "expiry", at: vec![(1, "expiry"), (2, "expiry")], result: Ok(vec![Some(SigStatus { slot: 102, err: None, confirmation: Some("confirmed".into()) }), None]),
            t_ns: 20 },
        Settled::Statuses { why: "check", at: vec![(4, "+2s"), (5, "+10s"), (6, "+60s")], result: Err("timeout".into()), t_ns: 30 },
        Settled::Statuses { why: "check", at: vec![(4, "+2s")], result: Ok(vec![Some(SigStatus { slot: 7, err: Some(json!({ "InstructionError": [2, { "Custom": 6001 }] })),
            confirmation: None })]), t_ns: 31 },
        Settled::DrySim { attempt: 8, line: json!({ "attempt": 8, "src": "dry_run", "sim_ms": 2.5, "err": null }) },
    ];
    for s in &all {
        let j = s.json();
        let back = Settled::from_json(&j).unwrap_or_else(|| panic!("reads back: {j}"));
        assert_eq!(back.json(), j);
    }
    assert!(Settled::from_json(&json!({ "error": null, "landed": { "sig": "x" } })).is_none(), "the pre-WP-05 form is not a settlement");
    assert!(Settled::from_json(&json!({ "what": "statuses", "why": "other", "at": [], "result": [], "t_ns": 1 })).is_none());
    assert_eq!(send::drop_code("something new"), "other");
}

/// Review WP-09 "For the WP-05 merge" item 2: the exec_init record reads back as what the executor started with (its
/// lookup tables in order, PumpSwap's GlobalConfig, the held tokens, the size cap, the would-send rate, the tip policy,
/// the crowding map's static list); its size cap is the smaller of the cap and a bankroll's
#[tokio::test]
async fn exec_init_reads_back() {
    let dir = test_dir("exec-init");
    let cfg = test_cfg(&dir, "");
    let held: HashSet<Pk> = [*WSOL, MINT, M2].into_iter().collect();
    let pump = PumpGlobal { disable_flags: 8, protocol: vec![[1; 32], [2; 32]], reserved: vec![[3; 32]], buyback: vec![[4; 32]] };
    let x = Exec::assemble(&cfg, Rpc::race(vec![]), None, Rec::off(), crossbeam_channel::unbounded().0, vec![], vec![([7; 32], vec![[8; 32], [9; 32]]), ([6; 32], vec![[5; 32]])],
        Some(pump.clone()), held, Mode::Shadow, None).unwrap();
    let mut i = x.init();
    (i.crowding_window_h, i.crowding_buckets, i.crowded) = (6, [20, 150], vec![[11; 32], [12; 32]]);
    assert_eq!((i.alts[0].0, i.alts[1].0, i.pump.clone(), i.held.len(), i.max_size, i.would_send_per_sec), ([7; 32], [6; 32], Some(pump), 3, sol(cfg.live.max_size_sol), 5));
    assert_eq!(i.tips.as_ref().map(|p| (p.model.floor, p.model.shares, p.model.cap)), Some((1_000, [0.7; 5], 100_000)));
    assert_eq!((i.uva, i.version), (None, EXEC_INIT_VERSION));
    let mut j = i.json();
    j["version"] = Value::Null;
    assert!(ExecInit::from_json(&j).is_none(), "a record written before WP-06's builder is not read as one");
    assert_eq!(i.cfg_sha256, cfg_sha256(&cfg));
    let back = ExecInit::from_json(&i.json()).unwrap();
    assert_eq!(back, i);
    // (merge of WP-06 with integ/stage0) no static bankroll cap: the bankroll is WP-07's, on each decision-point record's
    // money view; a record claiming one is not read as this build's (it would not replay as it ran)
    assert!(i.json().get("bankroll_cap_lamports").is_none());
    let mut j = i.json();
    j["bankroll_cap_lamports"] = json!(7);
    assert!(ExecInit::from_json(&j).is_none(), "a static bankroll cap is refused");
    j["bankroll_cap_lamports"] = Value::Null;
    assert_eq!(ExecInit::from_json(&j).unwrap(), i, "WP-06's null one reads");
    let _ = std::fs::remove_dir_all(&dir);
}

/// exec_init's `cfg_sha256`: the config the executor decides with. The supervisor's `--budget-left` (a lower failed-fee
/// cap for the segment; only a sending executor reads it) does not change it; the send policy does
#[test]
fn the_executor_config_hash() {
    let dir = std::env::temp_dir();
    let base = cfg_sha256(&test_cfg(&dir, ""));
    let mut c = test_cfg(&dir, "");
    c.live.max_failed_fees_lamports = 1;
    assert_eq!(cfg_sha256(&c), base);
    assert_ne!(cfg_sha256(&test_cfg(&dir, "[send_policy]\ninflight_hold_slots = 3\n")), base);
    // WP-06: the builder, the tips and the bands are the executor's too
    for extra in ["[builder]\nheld_max = 3\n", "[builder]\ncreate_close = false\n", "[tips]\ncap = 200000\n", "[bands]\nedges = [1, 2, 3, 4]\n"] { assert_ne!(cfg_sha256(&test_cfg(&dir, extra)), base, "{extra}"); }
    // FT-006: the BAM bid policy is the executor's when on; off, it hashes as a config without it (replays of older runs)
    assert_ne!(cfg_sha256(&test_cfg(&dir, "[send_policy.bam]\nenabled = true\n")), base);
    assert_eq!(cfg_sha256(&test_cfg(&dir, "[send_policy.bam]\nenabled = false\nmin_tip_per_cu = 0.07\n")), base);
    c.strategy.cu_price_micro += 1;
    assert_ne!(cfg_sha256(&c), base);
}

/// Review WP-09 "For the WP-05 merge" items 1, 3: an offline executor (a replay's) reads the gate, the leader's kind, the
/// token and the recorder from the run's decision-point records, the last one at or before the opportunity, and nothing
/// of its own; the leader's identity is the journaled schedule's. A record of another opportunity, or one naming another
/// target slot or leader, is counted (`seen_mismatch`); a decision before any record reads the gate stopped
#[test]
fn an_offline_executor_reads_the_runs_records() {
    let cfg = test_cfg(&std::env::temp_dir(), "");
    let init = ExecInit { mode: Mode::Shadow, alts: vec![], pump: None, held: vec![*WSOL, MINT], max_size: 1_000, max_size_src: "live".into(),
        would_send_per_sec: 3, tips: None, crowding_window_h: 6, crowding_buckets: [20, 150], crowded: vec![], cfg_sha256: cfg_sha256(&cfg), uva: Some(true),
        version: EXEC_INIT_VERSION, money_guard: false, cap_failed_fees: None };
    let mut x = Exec::offline(&cfg, &init, Rec::off()).unwrap();
    assert!(x.is_offline() && x.paths.is_none() && x.key.is_none() && x.jito.is_none());
    assert_eq!((x.size_cap(), x.path_rate), (1_000, 3));
    // WP-09 part 2: a live executor is replayed too, offline as well: no key, no send path, no Jito client; the run's
    // failed-fee cap and equity guard from its record
    let live = Exec::offline(&cfg, &ExecInit { mode: Mode::Live, money_guard: true, cap_failed_fees: Some(77_000), ..init.clone() }, Rec::off()).unwrap();
    assert!(live.is_offline() && live.paths.is_none() && live.key.is_none() && live.jito.is_none() && live.mode.sends());
    assert_eq!((live.cap_failed_fees, live.money_guard), (77_000, true));
    let view = view();
    // before any record: fail closed
    let i = x.inputs(&view, 100, 1);
    assert_eq!((i.gate, i.recorder_ok, x.seen_missing), (GateMode::Stopped, false, 1));
    // the run's record of opportunity 4, at opportunity 4: its gate, kind and recorder; the schedule's identity (slot 101: LJ)
    let rec4 = json!({ "mode": "shadow", "reason": "paused", "src": "decision", "opp": 4, "leader": { "slot": 101, "identity": b58(&LJ), "kind": "bam", "kind_src": "kobe" },
        "jito_token_ok": true, "recorder_ok": true });
    x.stage_seen(4, 4, &rec4);
    let i = x.inputs(&view, 100, 2);
    assert_eq!((i.gate, i.gate_reason.as_str(), i.leader.kind, i.leader.identity.clone(), i.recorder_ok, i.token), (GateMode::Shadow, "paused", LeaderKind::Bam, Some(b58(&LJ)),
        true, TokenSeen::NotUsed));
    assert_eq!(x.seen_mismatch, 0);
    // the last record holds at the next opportunities
    assert_eq!(x.inputs(&view, 104, 3).leader.kind, LeaderKind::Bam);
    // a record naming another target slot than the replay's, a record staged at another opportunity, one it cannot read
    x.stage_seen(5, 5, &json!({ "mode": "live", "reason": null, "src": "decision", "opp": 5, "leader": { "slot": 999, "identity": b58(&LJ), "kind": "jito" },
        "jito_token_ok": true, "recorder_ok": true }));
    let _ = x.inputs(&view, 100, 4);
    x.stage_seen(6, 7, &rec4);
    x.stage_seen(8, 8, &json!({ "mode": null, "src": "decision", "opp": 8, "executor": false }));
    assert_eq!(x.seen_mismatch, 3);
}

// ------------------------------------------------------------------------------------------------ WP-06: the builder

/// a route through M2, a token the wallet holds no account for (DAMM v2 legs)
fn route_m2(buy: u8, sell: u8, expected: u64, sv: u64) -> RouteIn {
    let mut r = route(buy, damm(sell, M2), expected, sv);
    r.mint = M2;
    r.buy = damm(buy, M2);
    r
}

/// the dry-run attempt lines' signed transactions
fn signed(l: &Value) -> Vec<u8> { use base64::Engine as _; base64::engine::general_purpose::STANDARD.decode(l["dry_run"]["tx_b64"].as_str().unwrap()).unwrap() }

/// the checks of `raw` that fail against `want`
fn failing(raw: &[u8], want: &VerifyWant) -> Vec<String> {
    verify_bundle(raw, want).iter().filter(|c| c["ok"] != json!(true)).map(|c| c["check"].as_str().unwrap().to_string()).collect()
}

/// The ledger of one bundle transaction, instruction by instruction, on the payer's native lamports (what WP-07's ledger
/// books from the chain, read here from the signed bytes): the base fee, every System transfer from the payer (the tip),
/// the rent an ATA create takes (`rent`: the account's rent-exempt minimum) and what a CloseAccount of an account this
/// transaction created gives back (every lamport of it: its rent, it holds nothing else). Returns (native delta, rent
/// locked, rent reclaimed)
fn payer_ledger(tx: &crate::tx::Tx, payer: &Pk, rent: u64) -> (i64, u64, u64) {
    let mut native = -(BASE_FEE as i64);
    let (mut locked, mut reclaimed) = (0u64, 0u64);
    let mut created: HashMap<Pk, u64> = HashMap::default();
    for ix in &tx.ixs {
        let p = tx.keys[ix.program as usize];
        let key = |k: usize| tx.keys[ix.accounts[k] as usize];
        if p == *crate::pda::ATA_PROGRAM && ix.data == [1] && key(0) == *payer {
            native -= rent as i64;
            locked += rent;
            created.insert(key(1), rent);
        } else if (p == *crate::pda::TOKEN_PROGRAM || p == *crate::pda::TOKEN_2022) && ix.data == [9] && key(1) == *payer {
            let back = created.remove(&key(0)).expect("a close of an account this transaction did not create");
            native += back as i64;
            reclaimed += back;
        } else if p == [0u8; 32] && ix.data.len() == 12 && ix.data[..4] == [2, 0, 0, 0] && key(0) == *payer {
            native -= u64::from_le_bytes(ix.data[4..12].try_into().unwrap()) as i64;
        }
    }
    (native, locked, reclaimed)
}

/// PLAN WP-06 items 1-2, the go-live gate's rent-neutral create+close: a route through a token the wallet holds no account
/// for creates the payer's ATA before the route and closes it to the payer after it, in the same transaction, in the
/// plan's order (CU limit, loaded-data limit, create, route, close, tip); its CU limit adds the create and the close. The
/// ledger of the signed bytes: the native lamports move by the fee and the tip only (rent locked = rent reclaimed: 1,488,440
/// for an SPL account at mainnet's rent, 1,513,840 for a Token-2022 one); the dry run's checks pass on the new layout. A held
/// token's route creates and closes nothing. The executor's attempt lines say which (`creates_ata`, `closes_ata`)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn rent_neutral_create_and_close() {
    let mut r = rig("rent-neutral", Mode::DryRun, "").await;
    let t = now_ns();
    let payer = r.x.payer;
    assert_eq!(r.decide(route_m2(1, 2, 50_000, 1), 100, t).reason, "would_send");
    assert_eq!(r.decide(route(3, damm(4, MINT), 50_000, 1), 100, t + S).reason, "would_send");
    let a = r.lines("attempts");
    let (cc, held) = (&a[0], &a[1]);
    for l in [cc, held] { assert_eq!(l["dry_run"]["checks_ok"].as_bool(), Some(true), "{}", l["dry_run"]["checks"]); }
    assert_eq!((cc["tx"]["creates_ata"].as_bool(), cc["tx"]["closes_ata"].as_bool(), cc["tx"]["held_addition"].as_bool(), cc["tx"]["cu_limit"].as_u64()),
        (Some(true), Some(true), Some(false), Some(100_000 + 30_000 + 5_000)), "the create and the close are in the CU limit");
    assert_eq!((held["tx"]["creates_ata"].as_bool(), held["tx"]["closes_ata"].as_bool(), held["tx"]["cu_limit"].as_u64()), (Some(false), Some(false), Some(100_000)));
    assert_eq!(cc["tx"]["mid_account"].as_str(), Some(b58(&build::ata_of(&payer, &M2, &crate::pda::TOKEN_PROGRAM)).as_str()));
    let (tx, _) = crate::tx::parse_wire(&signed(cc)).unwrap();
    let progs: Vec<Pk> = tx.ixs.iter().map(|ix| tx.keys[ix.program as usize]).collect();
    assert_eq!(progs, vec![crate::tx::COMPUTE_BUDGET, crate::tx::COMPUTE_BUDGET, *crate::pda::ATA_PROGRAM, r.x.program, *crate::pda::TOKEN_PROGRAM, [0u8; 32]]);
    let tip = cc["tip"]["lamports"].as_u64().unwrap();
    for rent in [1_488_440u64, 1_513_840] {
        let (native, locked, reclaimed) = payer_ledger(&tx, &payer, rent);
        assert_eq!((native, locked, reclaimed), (-(BASE_FEE as i64) - tip as i64, rent, rent), "rent-neutral: the fee and the tip only");
    }
    let (tx, _) = crate::tx::parse_wire(&signed(held)).unwrap();
    assert_eq!(tx.ixs.len(), 4, "CU limit, loaded-data limit, route, tip");
    assert_eq!(payer_ledger(&tx, &payer, 1_488_440), (-(BASE_FEE as i64) - held["tip"]["lamports"].as_i64().unwrap(), 0, 0));
    for (name, ok) in [("ix_order", true), ("ata_create", true), ("ata_close", true), ("rent_returns", true)] {
        let c = cc["dry_run"]["checks"].as_array().unwrap().iter().find(|c| c["check"] == name).unwrap().clone();
        assert_eq!(c["ok"].as_bool(), Some(ok), "{c}");
    }
    let rr = cc["dry_run"]["checks"].as_array().unwrap().iter().find(|c| c["check"] == "rent_returns").unwrap()["detail"].clone();
    assert_eq!((rr["created"].clone(), rr["closed"].clone()), (json!([b58(&build::ata_of(&payer, &M2, &crate::pda::TOKEN_PROGRAM))]), rr["created"].clone()));
}

/// PLAN WP-06 + go-live gate item 4: the dry run's checks on the new layout catch every way the rent could stay locked or
/// the order break, from the signed bytes alone (review WP-06 #2: what the transaction creates, keeps and closes is read
/// from it, never taken from the build): no close (`ix_order`, `ata_close`, `rent_returns`, `held_addition`, and
/// `min_profit_covers_tip`: the kept account's rent is not covered; `cu_limit`: the close's allowance is in the limit
/// without the close); a close to another account (the rent leaves: the same, the order aside); the close before the
/// route (`ix_order`, `rent_returns`); a close of a held token's account the transaction did not create (`cu_limit`,
/// `ix_order`, `ata_close`, `rent_returns`); another token's account created (`ata_create`, `ata_close`; `rent_returns`
/// holds: it is closed); a kept account, held-set additions off (the default) or on but the close fitting; a wrong
/// loaded-data limit; a missing guard trailer. min_profit still covers the tip + the base fee + the margin floor: the
/// create's rent comes back in the transaction, so it is not paid out
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn verify_bundle_on_the_new_layout() {
    let mut r = rig("verify-wp06", Mode::DryRun, "").await;
    let t = now_ns();
    assert_eq!(r.decide(route_m2(1, 2, 50_000, 1), 100, t).reason, "would_send");
    let l = r.lines("attempts")[0].clone();
    let (mp, tip0) = (l["min_profit_onchain"].as_u64().unwrap(), (pk(l["tip"]["account"].as_str().unwrap()), l["tip"]["lamports"].as_u64().unwrap()));
    let x = &r.x;
    let payer = x.payer;
    let dk = dry_key();
    let ata = build::AtaOps { mint: M2, token_program: *crate::pda::TOKEN_PROGRAM, close: true };
    let limit = l["tx"]["loaded_data_limit"].as_u64().unwrap() as u32;
    // the executor's own want re-derives the `auto` limit from the message; these hand-laid variants keep it fixed, so
    // each one fails for what it changes
    let auto = VerifyWant { signer: dk.verifying_key().to_bytes(), mid: build::ata_of(&payer, &M2, &crate::pda::TOKEN_PROGRAM), ata: Some((M2, *crate::pda::TOKEN_PROGRAM)),
        ..live_want(x, Some(tip0), mp) };
    assert_eq!(failing(&signed(&l), &auto), Vec::<String>::new(), "the executor's own bytes");
    let want = VerifyWant { loaded_limit: Some(Some(limit)), ..want_clone(&auto) };
    assert_eq!(failing(&signed(&l), &want), Vec::<String>::new());
    // the same route, its instructions laid out by hand
    let rt = route_m2(1, 2, 50_000, 1);
    let leg = |m: &PoolMeta, tin: Pk, tout: Pk| build::leg(&build::LegIn { m, pool: &[], tin, tout, amount_in: rt.size, payer, pump: None, dlmm_live: &[], dlmm_end: None,
        dlmm_ext: None }).unwrap();
    let quote = build::ata_of(&payer, &WSOL, &crate::pda::TOKEN_PROGRAM);
    let route_ix = build::route_ix(x.program, payer, quote, rt.size, mp, &[leg(&rt.buy, *WSOL, M2), leg(&rt.sell, M2, *WSOL)], None).unwrap();
    let sign = |ixs: Vec<build::Ix>| { let m = build::compile_v0(payer, &ixs, BH, &[], &[tip0.0]).unwrap(); build::sign(&m, &dk) };
    // the CU limit each plan asks: the route's 100,000 plus the create's 30,000 and the close's 5,000 when it makes them
    let plan = |a: Option<build::AtaOps>| build::Plan { payer, cu_price: 0, extra_tips: vec![], cu_limit: 100_000 + a.map_or(0, |a| 30_000 + if a.close { 5_000 } else { 0 }), loaded_data_limit: Some(limit),
        ata: a, tip: Some(tip0) };
    let good = build::bundle_ixs(&plan(Some(ata)), route_ix.clone());
    assert_eq!(failing(&sign(good.clone()), &want), Vec::<String>::new());
    // no close: the rent stays locked (and the limit still asks the close's CU)
    let mut v = good.clone();
    v.remove(4);
    assert_eq!(failing(&sign(v), &want), ["cu_limit", "min_profit_covers_tip", "ix_order", "ata_close", "rent_returns", "held_addition"]);
    // the close sends the rent elsewhere
    let mut v = good.clone();
    v[4] = build::close_account_ix(want.mid, [250; 32], payer, *crate::pda::TOKEN_PROGRAM);
    assert_eq!(failing(&sign(v), &want), ["min_profit_covers_tip", "ata_close", "rent_returns", "held_addition"]);
    // the close before the route (it would fail on chain, or close an account the route then needs)
    let mut v = good.clone();
    v.swap(3, 4);
    assert_eq!(failing(&sign(v), &want), ["ix_order", "rent_returns"]);
    // a held token: the transaction must create and close nothing; a close of its account (not created here) is caught
    let held_want = VerifyWant { ata: None, ..want_clone(&want) };
    let mut v = build::bundle_ixs(&plan(None), route_ix.clone());
    v.insert(3, build::close_account_ix(want.mid, payer, payer, *crate::pda::TOKEN_PROGRAM));
    assert_eq!(failing(&sign(v), &held_want), ["cu_limit", "ix_order", "ata_close", "rent_returns"]);
    // another token's account created (and closed): not the route's mid account
    let other = build::AtaOps { mint: [249; 32], ..ata };
    assert_eq!(failing(&sign(build::bundle_ixs(&plan(Some(other)), route_ix.clone())), &want), ["ata_create", "ata_close"]);
    // an account created and kept: with held-set additions off (the default) it is caught whatever else holds; with them
    // configured and allowed (`held_ok`) it is caught still, as this bundle carries its close easily (only an addition
    // the size budget needed passes: the_size_budget_ladder)
    let kept = build::bundle_ixs(&plan(Some(build::AtaOps { close: false, ..ata })), route_ix.clone());
    let kept_fails = ["min_profit_covers_tip", "ix_order", "ata_close", "rent_returns", "held_addition"];
    assert_eq!(failing(&sign(kept.clone()), &want), kept_fails);
    let on = VerifyWant { held_ok: true, ..want_clone(&want) };
    assert_eq!(failing(&sign(kept.clone()), &on), kept_fails);
    let c = verify_bundle(&sign(kept), &on).into_iter().find(|c| c["check"] == "held_addition").unwrap();
    assert!(c["detail"]["with_close"]["bytes"].as_u64().unwrap() <= build::MAX_TX_BYTES as u64, "{c}");
    // a wrong loaded-data limit; the guard trailer missing when one is wanted
    let mut p2 = plan(Some(ata));
    p2.loaded_data_limit = Some(limit - 32 * 1024);
    assert_eq!(failing(&sign(build::bundle_ixs(&p2, route_ix.clone())), &want), ["loaded_data_limit"]);
    assert_eq!(failing(&sign(build::bundle_ixs(&p2, route_ix.clone())), &auto), ["loaded_data_limit"], "auto: re-derived from the message");
    assert_eq!(failing(&sign(good.clone()), &VerifyWant { guard: Some(0), ..want_clone(&want) }), ["route_guard"]);
    // a leg that spends from the payer's USDC account (review WP-06 #7): min_profit does not watch it
    let usdc = build::ata_of(&payer, &PERMANENT_MINTS[1], &crate::pda::TOKEN_PROGRAM);
    let mut b1 = leg(&rt.buy, *WSOL, M2);
    b1.accounts[2].key = usdc;
    let bad_route = build::route_ix(x.program, payer, quote, rt.size, mp, &[b1, leg(&rt.sell, M2, *WSOL)], None).unwrap();
    let bad = sign(build::bundle_ixs(&plan(Some(ata)), bad_route));
    assert_eq!(failing(&bad, &want), ["route_payer_accounts"]);
    assert!(failing(&bad, &VerifyWant { payer_tokens: vec![], ..want_clone(&want) }).is_empty(), "only that check sees it");
    // min_profit covers the tip, the fee and the margin floor; the rent is not paid out (it comes back)
    let c = verify_bundle(&sign(good), &want).into_iter().find(|c| c["check"] == "min_profit_covers_tip").unwrap();
    assert_eq!((c["ok"].as_bool(), c["detail"]["signed_paid_out"].as_u64(), c["detail"]["kept_rent"].as_u64()), (Some(true), Some(tip0.1), Some(0)));
}

fn want_clone(w: &VerifyWant) -> VerifyWant {
    VerifyWant { payer: w.payer, signer: w.signer, blockhash: w.blockhash, tip: w.tip, tips: w.tips.clone(), program: w.program, pools: w.pools, cu_route: w.cu_route,
        cu_ata: w.cu_ata, alts: w.alts.clone(), amount_in: w.amount_in, min_profit: w.min_profit, margin_floor: w.margin_floor, quote: w.quote, mid: w.mid,
        leg_programs: w.leg_programs, ata: w.ata, held_ok: w.held_ok, held_rent: w.held_rent, loaded_limit: w.loaded_limit, sizes: w.sizes.clone(), guard: w.guard,
        payer_tokens: w.payer_tokens.clone() }
}

/// PLAN WP-06 item 2: a PumpSwap buy names the wallet's user volume accumulator and creates it when it is missing
/// (1,346,200 lamports, never recovered, outside the route's profit check): refused `uva_missing` while it is absent or
/// unknown (fail closed), unless `[builder] allow_uva_create`; the store's view (the route's `uva`) overrides the boot
/// read. A PumpSwap sell does not name it
#[tokio::test]
async fn uva_missing_refuses_pumpswap_buys() {
    let mut r = rig("uva", Mode::Live, "").await;
    let t = now_ns();
    let pump_buy = |n: u8, uva: Option<bool>| { let mut x = route(n, damm(n + 1, MINT), 50_000, 1); x.buy.venue = Venue::PumpSwap; x.uva = uva; x };
    assert_eq!(r.decide(pump_buy(1, None), 100, t).reason, "uva_missing", "unknown: the boot read none");
    r.x.set_uva(Some(false));
    assert_eq!(r.decide(pump_buy(3, None), 100, t).reason, "uva_missing");
    assert_eq!(r.decide(pump_buy(5, Some(false)), 100, t).reason, "uva_missing", "the store says it is not there");
    // present: past the check (this test's pool has no PumpSwap bytes to build a leg from: the build refuses next)
    assert!(r.decide(pump_buy(7, Some(true)), 100, t).reason.starts_with("build_error:buy leg"), "the store says it is there");
    r.x.set_uva(Some(true));
    assert!(r.decide(pump_buy(9, None), 100, t).reason.starts_with("build_error:buy leg"), "the boot read it");
    assert_eq!(r.decide(pump_buy(11, Some(false)), 100, t).reason, "uva_missing", "the store's view wins");
    // a sell on PumpSwap is not a buy
    let mut sell = route(13, damm(14, MINT), 50_000, 1);
    sell.sell.venue = Venue::PumpSwap;
    sell.uva = Some(false);
    assert_ne!(r.decide(sell, 100, t).reason, "uva_missing");
    // review WP-06 #13: a buy is a PumpSwap leg its quote token (t1) goes into, on either leg: a sell leg on a pool whose
    // quote is the route's token buys it
    let mut sell_buys = route(17, damm(18, MINT), 50_000, 1);
    (sell_buys.sell.venue, sell_buys.sell.t0, sell_buys.sell.t1, sell_buys.uva) = (Venue::PumpSwap, *WSOL, MINT, Some(false));
    assert_eq!(r.decide(sell_buys, 100, t).reason, "uva_missing");
    r.x.builder.allow_uva_create = true;
    assert!(r.decide(pump_buy(15, Some(false)), 100, t).reason.starts_with("build_error:buy leg"), "the owner allowed the creation");
    assert_eq!(r.n("reject_uva_missing"), 5);
}

/// PLAN WP-06 item 2: whether the wallet holds the mid token's account is the store's view when the engine follows it
/// (the route's `mid_held`), else the boot read's: a token the boot read held but the store shows closed is created and
/// closed again; a token the boot read missed but the store holds is neither
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_held_view_comes_from_the_store() {
    let mut r = rig("held-view", Mode::DryRun, "").await;
    let t = now_ns();
    let mut gone = route(1, damm(2, MINT), 50_000, 1);
    gone.mid_held = Some(false);
    let mut there = route_m2(3, 4, 50_000, 1);
    there.mid_held = Some(true);
    for (k, x) in [gone, there].into_iter().enumerate() { assert_eq!(r.decide(x, 100, t + k as u64 * S).reason, "would_send"); }
    let a = r.lines("attempts");
    assert_eq!(a.iter().map(|l| (l["tx"]["creates_ata"].as_bool().unwrap(), l["tx"]["closes_ata"].as_bool().unwrap(), l["dry_run"]["checks_ok"].as_bool().unwrap()))
        .collect::<Vec<_>>(), vec![(true, true, true), (false, false, true)]);
}

/// PLAN WP-06 items 4 and 9: the CU limit is the route's (the engine's CU model: `RouteIn::cu`) plus the ATA create and
/// close it makes (`cu_ata`), and the attempt says where it came from; with `[builder] payer_guard` the route carries
/// nexus-v2's 8-byte trailer (`max_payer_lamport_drop`, `payer_guard_max_drop`) and the dry run's `route_guard` checks it;
/// the tip is the band's share of the edge (attempts `tip.share`, `tip.band`)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn cu_limit_guard_and_tip_band_in_the_bundle() {
    let mut r = rig("cu-guard", Mode::DryRun, "[builder]\npayer_guard = true\npayer_guard_max_drop = 7\n[tips]\nshares = [0.5, 0.6, 0.7, 0.8, 0.9]\ncap = 10000000\n").await;
    let t = now_ns();
    let mut x = route_m2(1, 2, 2_005_000, 1);
    (x.cu, x.cu_src, x.cu_ata) = (211_000, "table:DammV2|na+DammV2|na".into(), (23_100, 3_300));
    assert_eq!(r.decide(x, 100, t).reason, "would_send");
    let l = r.lines("attempts")[0].clone();
    assert_eq!(l["dry_run"]["checks_ok"].as_bool(), Some(true), "{}", l["dry_run"]["checks"]);
    assert_eq!((l["tx"]["cu_limit"].as_u64(), l["tx"]["cu_src"].as_str(), l["tx"]["guard_max_drop"].as_u64()), (Some(211_000 + 23_100 + 3_300),
        Some("table:DammV2|na+DammV2|na"), Some(7)));
    // the edge 2,000,000 is band 3 (1M-10M): 0.8 of it
    assert_eq!((l["band"].as_u64(), l["tip"]["band"].as_u64(), l["tip"]["share"].as_f64(), l["tip"]["lamports"].as_u64()), (Some(3), Some(3), Some(0.8), Some(1_600_000)));
    let raw = signed(&l);
    let (tx, _) = crate::tx::parse_wire(&raw).unwrap();
    let all = tx.resolve(|_| None).unwrap();
    let seen = route_of(&tx, &all, &r.x.program).unwrap();
    assert_eq!((seen.guard, seen.min_profit), (Some(7), l["min_profit_onchain"].as_u64().unwrap()));
    let g = l["dry_run"]["checks"].as_array().unwrap().iter().find(|c| c["check"] == "route_guard").unwrap().clone();
    assert_eq!((g["ok"].as_bool(), g["detail"]["signed"].as_u64()), (Some(true), Some(7)));
}

/// The merge of WP-06 with integ/stage0: WP-07's rent cap (`[supervisor] rent_cap_sol`) limits held-set additions only.
/// A create+close in one transaction locks no rent, so a route through a token the wallet holds no account for is built
/// with its create and close and sent whatever the recoverable rent (kept as WP-07 wrote it, the cap would have made the
/// canary held-only: `rent_cap` on every such route). A held-set addition (configured: `[builder] held_max` > 0) is
/// allowed only while the money view's recoverable rent plus the rent it may lock (`build::HELD_RENT_BOUND`) stays
/// within the cap: refused, the bundle is `oversized` and the build says why; the dry run's `held_ok` is the same rule.
/// Without a money view (no balance snapshot yet: a live run sends nothing then, `equity_unknown`) the cap is not known
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_rent_cap_limits_held_additions_only() {
    let mut r = rig("rent-cap-cc", Mode::Live, "[supervisor]\nrent_cap_sol = 0.001\n").await;
    r.x.set_money(money(1_000_000_000, 900_000_000, 4_078_560));
    let d = r.decide(route_m2(1, 2, 50_000, 1), 100, now_ns());
    assert_eq!(d.reason, "sent", "{d:?}");
    let l = r.lines("attempts")[0].clone();
    assert_eq!((l["tx"]["creates_ata"].as_bool(), l["tx"]["closes_ata"].as_bool(), l["tx"]["held_addition"].as_bool()), (Some(true), Some(true), Some(false)),
        "rent-neutral: created and closed");
    assert!(!r.x.held_growth_ok(), "held-set additions are off by default");
    assert_eq!(r.n("reject_rent_cap"), 0);
    // held-set additions configured (an explicit opt-in): the cap binds the size budget's held_ata rung
    let mut r = rig_full("rent-cap-held", Mode::Live, "[builder]\nheld_max = 5\n[supervisor]\nrent_cap_sol = 0.006\n[send_policy]\nbig_band_max_per_sec = 1000\n",
        Some(pump_global()), [*WSOL].into_iter().collect()).await;
    let ta = [0xab; 32];
    let (a, ea) = held_route(&mut r.x, M2, 21, 22, ta);
    let tables: HashMap<Pk, Vec<Option<Pk>>> = [(ta, ea)].into_iter().collect();
    let by_pool: HashMap<Pk, Vec<Pk>> = [(a.buy.pool, vec![ta])].into_iter().collect();
    let alts = AltSource { tables: &tables, by_pool: &by_pool };
    let tip = Some((tip_accounts()[0], 35_000));
    assert!(r.x.held_growth_ok(), "no money view yet: the cap is not known");
    // 4,078,560 recoverable + 2,282,880 is over the 6,000,000 cap: no held addition, the bundle does not fit
    r.x.set_money(money(1_000_000_000, 900_000_000, 4_078_560));
    assert!(!r.x.held_growth_ok());
    let e = r.x.build(&a, 40_001, BH, tip, &alts, 0).err().unwrap();
    assert!(e.starts_with("oversized(") && e.contains(&format!("held_ata: recoverable rent 4078560 + {} over the rent cap 6000000", build::HELD_RENT_BOUND)), "{e}");
    let t = now_ns();
    let i = r.x.inputs(&r.view, 100, t);
    assert_eq!(r.x.decide(a.clone(), &i, &r.view, &alts, 100, t).reason, "oversized");
    // 2,039,280 + 2,282,880 is within it: the held addition is built and sent, its route asking the rent on chain
    r.x.set_money(money(1_000_000_000, 900_000_000, 2_039_280));
    assert!(r.x.held_growth_ok());
    let mut a2 = a.clone();
    a2.state_version = 2;
    let i = r.x.inputs(&r.view, 100, t + S);
    assert_eq!(r.x.decide(a2, &i, &r.view, &alts, 100, t + S).reason, "sent");
    let l = r.lines("attempts").last().unwrap().clone();
    assert_eq!((l["tx"]["alt_fallback"].as_str(), l["tx"]["held_addition"].as_bool(), l["tx"]["held_rent_lamports"].as_u64()),
        (Some("held_ata"), Some(true), Some(build::HELD_RENT_BOUND)));
    assert_eq!((r.n("reject_oversized"), r.n("reject_rent_cap")), (1, 0), "a refused addition is `oversized`; `rent_cap` produces nothing");
}

/// Review WP-06 #2 (the review's mutant M1, in the dry run itself): a builder that keeps the account it creates (no close)
/// fails the dry run's own checks, read from the signed bytes: the order, the close, the rent's return, the held-set
/// addition (none is configured; or one is, but this bundle carries its close easily) and min_profit (the kept rent is
/// not covered); the attempt says which. Nothing comes from the build: its own record of the kept account changes none
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_dry_run_catches_a_kept_account() {
    for extra in ["", "[builder]\nheld_max = 40\n"] {
        let mut r = rig("dry-kept", Mode::DryRun, extra).await;
        let t = now_ns();
        r.x.fault_keep = true;
        assert_eq!(r.decide(route_m2(1, 2, 50_000, 1), 100, t).reason, "would_send");
        let l = r.lines("attempts")[0].clone();
        assert_eq!((l["tx"]["creates_ata"].as_bool(), l["tx"]["closes_ata"].as_bool(), l["tx"]["held_addition"].as_bool()), (Some(true), Some(false), Some(true)));
        let failed: Vec<&str> = l["dry_run"]["checks"].as_array().unwrap().iter().filter(|c| c["ok"] != json!(true)).map(|c| c["check"].as_str().unwrap()).collect();
        assert_eq!(failed, ["min_profit_covers_tip", "ix_order", "ata_close", "rent_returns", "held_addition"], "{extra:?}");
        assert_eq!((l["dry_run"]["checks_ok"].as_bool(), r.n("dry_run_check_failed"), r.n("dry_run_ok"), r.n("held_addition")), (Some(false), 1, 0, 1));
        let c = l["dry_run"]["checks"].as_array().unwrap().iter().find(|c| c["check"] == "held_addition").unwrap().clone();
        assert_eq!((c["detail"]["held_ok"].as_bool(), c["detail"]["rent"].as_u64()), (Some(!extra.is_empty()), Some(build::HELD_RENT_BOUND)), "{c}");
    }
}

/// Review WP-06 #2: the dry run re-derives the CU limit and the loaded-data limit from the signed message's own
/// instructions and accounts, on the decision's route CU, ATA allowances and account sizes, never the build's numbers: a
/// builder that asks another CU limit (here without the create's allowance) or another loaded-data limit fails `cu_limit`
/// / `loaded_data_limit` although its own record agrees with its bytes; the sizes the decision holds move the limit
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_dry_run_rederives_the_cu_and_loaded_data_limits() {
    let mut r = rig("dry-limits", Mode::DryRun, "").await;
    let t = now_ns();
    let failed = |l: &Value| -> Vec<String> { l["dry_run"]["checks"].as_array().unwrap().iter().filter(|c| c["ok"] != json!(true)).map(|c| c["check"].as_str().unwrap().to_string()).collect() };
    let detail = |l: &Value, k: &str| l["dry_run"]["checks"].as_array().unwrap().iter().find(|c| c["check"] == k).unwrap()["detail"].clone();
    assert_eq!(r.decide(route_m2(1, 2, 50_000, 1), 100, t).reason, "would_send");
    let good = r.lines("attempts")[0].clone();
    assert_eq!(failed(&good), Vec::<String>::new());
    let cu = detail(&good, "cu_limit");
    assert_eq!((cu["want"].as_u64(), cu["route"].as_u64(), cu["creates"].as_u64(), cu["closes"].as_u64()), (Some(135_000), Some(100_000), Some(1), Some(1)));
    let ld = detail(&good, "loaded_data_limit");
    let limit = good["tx"]["loaded_data_limit"].as_u64().unwrap();
    assert_eq!((ld["signed"].as_u64(), ld["want"].as_u64()), (Some(limit), Some(build::loaded_data_padded(ld["need"].as_u64().unwrap()) as u64)));
    // the CU limit without the create's 30,000
    r.x.fault_cu = Some(100_000 + 5_000);
    assert_eq!(r.decide(route_m2(3, 4, 50_000, 1), 100, t + S).reason, "would_send");
    let l = r.lines("attempts")[1].clone();
    assert_eq!((l["tx"]["cu_limit"].as_u64(), failed(&l)), (Some(105_000), vec!["cu_limit".to_string()]), "the build's own number agrees with its bytes");
    r.x.fault_cu = None;
    // 1 MiB less loaded data
    r.x.fault_loaded = Some(limit as u32 - (1 << 20));
    assert_eq!(r.decide(route_m2(5, 6, 50_000, 1), 100, t + 2 * S).reason, "would_send");
    let l = r.lines("attempts")[2].clone();
    assert_eq!((l["tx"]["loaded_data_limit"].as_u64(), failed(&l)), (Some(limit - (1 << 20)), vec!["loaded_data_limit".to_string()]));
    r.x.fault_loaded = None;
    // a pool the store sizes at 10 MB: both the build and the dry run's derivation count it
    let mut big = route_m2(7, 8, 50_000, 1);
    big.sizes = vec![([7; 32], 10_000_000)];
    assert_eq!(r.decide(big, 100, t + 3 * S).reason, "would_send");
    let l = r.lines("attempts")[3].clone();
    assert_eq!(failed(&l), Vec::<String>::new());
    assert!(l["tx"]["loaded_data_limit"].as_u64().unwrap() > limit + 10_000_000, "{}", l["tx"]["loaded_data_limit"]);
    assert_eq!((r.n("dry_run_ok"), r.n("dry_run_check_failed")), (2, 2));
}

/// Review WP-06 #3 (the review's mutant M4 survived every test): the size cap holds end to end. The engine re-quotes every
/// route at the executor's cap (`Engine::after_opportunity`: `Exec::size_cap`: the canary's `size_sol`, else `[live]
/// max_size_sol`, under WP-07's bankroll on the ledger's money view: the one bankroll source since the merge with
/// integ/stage0) before the executor decides, so no attempt trades above it whatever size the engine priced: a canary's
/// bundles (decoded from what the block engine received), a shadow run's would-sends, and a shadow run whose bankroll
/// (85% of 0.1 SOL liquid − 0.03 SOL) caps below `max_size_sol`. The executor's own refusal (`size_cap`, WP-07 review #12)
/// stays behind it: the engine's re-quote leaves it nothing to refuse here (`reject_size_cap` 0), and it refuses a
/// route sized past the cap (wp07_bankroll_rent_cap_and_canary_count)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_engine_caps_the_size() {
    let canary = "[canary]\nenabled = true\ncount = 10\nevery_ms = 1\nsize_sol = 0.05\nmax_spend_lamports = 20000\n";
    let bankroll = "[live]\nmax_size_sol = 0.2\nbankroll_share = 0.85\nbankroll_reserve_sol = 0.03\n";
    for (mode, extra, cap, view) in [(Mode::Canary, canary, 50_000_000u64, None), (Mode::Shadow, "[live]\nmax_size_sol = 0.03\n", 30_000_000, None),
        (Mode::Shadow, bankroll, 55_000_000, Some(money(100_000_000, 90_000_000, 0)))] {
        let mut r = rig("size-cap", mode, &format!("[send_policy]\nbig_band_max_per_sec = 1000\n{extra}")).await;
        let gate = SendGate::new();
        if mode == Mode::Shadow { let _ = gate.shadow("mode_shadow", "no --live or --canary: nothing is sent", true); }
        let (mut e, a, b) = amm_engine();
        e.set_rec(r.rec.clone());
        let mut x = std::mem::replace(&mut r.x, idle_exec());
        // the money view as the ledger hands it over (this engine has no ledger: it stays)
        if let Some(m) = view { x.set_money(m); }
        assert_eq!(x.size_cap(), cap);
        x.set_gate(gate);
        x.set_health(e.health_flags());
        let program = x.program;
        e.exec = Some(x);
        let mut t = now_ns();
        amm_start(&mut e, &mut t);
        amm_move(&mut e, &a, 0, 1_030, &mut t);
        amm_move(&mut e, &b, 1, 1_060, &mut t);
        r.rec.sync();
        let d: Vec<Value> = rec::read_jsonl(&r.dir, "decisions").unwrap().into_iter().filter(|l| l["opp"].is_u64()).collect();
        let priced: Vec<u64> = d.iter().filter_map(|l| l["routes"][l["best"].as_u64()? as usize]["size"].as_u64()).collect();
        assert!(!priced.is_empty() && priced.iter().all(|s| *s > cap), "{mode:?}: the engine priced above the cap: {priced:?}");
        let att = rec::read_jsonl(&r.dir, "attempts").unwrap();
        assert!(!att.is_empty(), "{mode:?}: {d:?}");
        for l in &att { assert!(l["size_lamports"].as_u64().unwrap() <= cap, "{mode:?}: {}", l["size_lamports"]); }
        assert!(att.iter().any(|l| l["size_lamports"].as_u64() == Some(cap)), "{mode:?}: the cap binds");
        assert_eq!(e.exec.as_ref().unwrap().counts.get("reject_size_cap"), None, "{mode:?}: the engine re-quoted at the cap");
        if mode.sends() {
            let _ = r.settled().await;
            let got = r.got.lock().unwrap().clone();
            assert!(!got.is_empty());
            for (raw, _) in &got {
                let (tx, _) = crate::tx::parse_wire(raw).unwrap();
                assert!(route_of(&tx, &tx.resolve(|_| None).unwrap(), &program).unwrap().amount_in <= cap, "the signed amount_in");
            }
        }
    }
}

/// a rich worst-case route (3M expected: it covers min_profit and a held account's rent) through `mint`, on pools
/// `buy`/`sell`, and the learned table (key `table`, indexed by its buy pool) with the fewest of its accounts that makes
/// the held-ATA fallback the one that fits (held-set additions configured)
fn held_route(x: &mut Exec, mint: Pk, buy: u8, sell: u8, table: Pk) -> (RouteIn, Vec<Option<Pk>>) {
    let mut w = worst_route();
    (w.mint, w.buy.t0, w.sell.t0, w.buy.extra, w.buy.pool, w.sell.pool, w.back) = (mint, mint, mint, vec![mint], [buy; 32], [sell; 32], w.size + 3_000_000);
    let tip = Some((tip_accounts()[0], 35_000));
    let route = build::route_ix(x.program, x.payer, build::ata_of(&x.payer, &WSOL, &crate::pda::TOKEN_PROGRAM), w.size, 40_001, &[leg_of(x, &w, true), leg_of(x, &w, false)], None).unwrap();
    let full = x.compile(&w, &route, Some(build::AtaOps { mint, token_program: *crate::pda::TOKEN_PROGRAM, close: true }), tip, BH, &[], None, 0).unwrap().msg.loadable.clone();
    let entries = |n: usize| -> Vec<Option<Pk>> { full[..n].iter().map(|k| Some(*k)).chain([Some(*crate::pda::TOKEN_PROGRAM)]).collect() };
    let by_pool: HashMap<Pk, Vec<Pk>> = [(w.buy.pool, vec![table])].into_iter().collect();
    let keep = x.builder.held_max;
    x.builder.held_max = 40;
    let n = (0..full.len()).find(|n| {
        let t: HashMap<Pk, Vec<Option<Pk>>> = [(table, entries(*n))].into_iter().collect();
        x.build(&w, 40_001, BH, tip, &AltSource { tables: &t, by_pool: &by_pool }, 0).is_ok_and(|b| b.alt_fallback == "held_ata")
    }).expect("a table size where only the held-ATA fallback fits");
    x.builder.held_max = keep;
    (w, entries(n))
}

/// Review WP-06 #5 (the review's mutant M5 survived): `held_max` counts every held-set addition, the landed ones and the
/// ones in flight. With `held_max = 1` (configured), a live held addition in flight stops another token's (`oversized`:
/// "1 tokens held of held_max 1"); once it lands its token is in the held set (`new_token_accounts_total` 1) and the limit
/// still binds; a higher `held_max` lets the next one go
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn held_additions_count_in_flight_and_landed() {
    let mut r = rig_full("held-count", Mode::Live, "[builder]\nheld_max = 1\n[send_policy]\nbig_band_max_per_sec = 1000\n", Some(pump_global()), [*WSOL].into_iter().collect()).await;
    let m3: Pk = [247; 32];
    let (ta, tb) = ([0xab; 32], [0xac; 32]);
    let (a, ea) = held_route(&mut r.x, M2, 21, 22, ta);
    let (b, eb) = held_route(&mut r.x, m3, 41, 42, tb);
    let tables: HashMap<Pk, Vec<Option<Pk>>> = [(ta, ea), (tb, eb)].into_iter().collect();
    let by_pool: HashMap<Pk, Vec<Pk>> = [(a.buy.pool, vec![ta]), (b.buy.pool, vec![tb])].into_iter().collect();
    let alts = AltSource { tables: &tables, by_pool: &by_pool };
    let t = now_ns();
    let decide = |r: &mut Rig, w: &RouteIn, sv: u64, t: u64| { let mut w = w.clone(); w.state_version = sv; let i = r.x.inputs(&r.view, 100, t); r.x.decide(w, &i, &r.view, &alts, 100, t) };
    assert_eq!(decide(&mut r, &a, 1, t).reason, "sent");
    let la = r.lines("attempts")[0].clone();
    assert_eq!((la["tx"]["alt_fallback"].as_str(), la["tx"]["held_addition"].as_bool()), (Some("held_ata"), Some(true)));
    assert_eq!(r.x.held_count(), 1, "in flight");
    // another token while the first is in flight: the held set is full
    assert_eq!(decide(&mut r, &b, 1, t + S).reason, "oversized");
    assert!(r.x.build(&b, 40_001, BH, Some((tip_accounts()[0], 35_000)), &alts, 0).err().unwrap().contains("held_ata: 1 tokens held of held_max 1"));
    // the first lands: its token joins the held set; the limit still binds
    let sig = la["tx"]["sig"].as_str().unwrap().to_string();
    r.x.on_wallet_tx(&json!({ "sig": sig, "ok": true, "slot": 101, "fee": 5_000 }), t + 2 * S, &|_| None);
    assert!(r.x.open_attempts().is_empty() && r.x.held.contains(&M2));
    assert_eq!((r.x.held_count(), r.x.new_atas), (1, 1));
    assert_eq!(decide(&mut r, &b, 2, t + 3 * S).reason, "oversized", "landed: counted");
    // room for one more
    r.x.builder.held_max = 2;
    assert_eq!(decide(&mut r, &b, 3, t + 4 * S).reason, "sent");
    assert_eq!((r.x.held_count(), r.n("reject_oversized")), (2, 2));
}

/// Review WP-06 #9: `[builder] create_close = false` (the held-only control arm) trades only tokens the wallet holds an
/// account for: a route through any other is refused (`mid_not_held`) before anything is built; a held token's route goes
#[tokio::test]
async fn create_close_off_trades_held_tokens_only() {
    let mut r = rig("held-only", Mode::Live, "[builder]\ncreate_close = false\n").await;
    let t = now_ns();
    assert_eq!(r.decide(route_m2(1, 2, 50_000, 1), 100, t).reason, "mid_not_held");
    let mut there = route_m2(3, 4, 50_000, 1);
    there.mid_held = Some(true);
    assert_eq!(r.decide(there, 100, t + 1).reason, "sent", "the store holds it");
    assert_eq!(r.decide(route(5, damm(6, MINT), 50_000, 1), 100, t + 2).reason, "sent", "the boot read held it");
    let a = r.lines("attempts");
    assert!(a.iter().all(|l| l["tx"]["creates_ata"] == json!(false)), "nothing created");
    assert_eq!(r.n("reject_mid_not_held"), 1);
}

/// PumpSwap's GlobalConfig as the rig's PumpSwap legs read it
fn pump_global() -> PumpGlobal { PumpGlobal { disable_flags: 0, protocol: vec![[30; 32], [31; 32], [32; 32]], reserved: vec![[33; 32]], buyback: vec![[34; 32], [35; 32]] } }

/// the worst-case 2-leg route of PLAN WP-06's size acceptance: a PumpSwap buy (pool v2: 25 accounts) and a DLMM sell
/// naming 5 bin arrays, through M2 (not held: create and close)
fn worst_route() -> RouteIn {
    let mut r = route_m2(1, 2, 50_000, 1);
    r.buy = PoolMeta { venue: Venue::PumpSwap, pool: [21; 32], t0: M2, t1: *WSOL, vault0: [23; 32], vault1: [24; 32], t0_prog: *crate::pda::TOKEN_PROGRAM,
        t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![M2], flag: false };
    r.sell = PoolMeta { venue: Venue::Dlmm, pool: [22; 32], t0: M2, t1: *WSOL, vault0: [25; 32], vault1: [26; 32], t0_prog: *crate::pda::TOKEN_PROGRAM,
        t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![[27; 32]], flag: false };
    let mut pool = vec![0u8; 300];
    pool[211..243].copy_from_slice(&[40; 32]);
    r.buy_data = pool;
    let mut pair = vec![0u8; 904];
    pair[76..80].copy_from_slice(&150i32.to_le_bytes());   // array 2; selling X walks down
    pair[552..584].copy_from_slice(&[13; 32]);
    r.sell_data = pair;
    (r.sell_live, r.sell_end, r.sell_ext, r.uva) = (vec![-2, -1, 0, 1, 2], Some(-120), Some([27; 32]), Some(true));
    r
}

/// PLAN WP-06 item 7, the size budget, on the worst-case route: over 1,232 bytes with the `[exec]` tables alone; a table
/// the engine learned that names the route's pools is added (`alt_index`) and the bundle fits, every check passing on
/// the signed bytes (the table resolves); with fewer accounts in the index, where create+close does not fit and keeping
/// the new account would: `oversized` by default (review WP-06 #1: held-set additions are off, `held_max = 0`); with
/// held-set additions configured (an explicit opt-in), still `oversized` unless the expected profit covers min_profit and
/// the rent the account would lock, or once the held set is full; else `held_ata`, its route asking min_profit +
/// `HELD_RENT_BOUND` on chain, and the dry run passes it (the close does not fit: a justified addition); else `oversized`
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_size_budget_ladder() {
    let mut r = rig_full("size", Mode::DryRun, "", Some(pump_global()), [*WSOL].into_iter().collect()).await;
    let t = now_ns();
    let w = worst_route();
    let tip = Some((tip_accounts()[0], 35_000));
    assert_eq!(r.x.builder.held_max, 0, "held-set additions are off by default");
    // nothing to add: oversized (keeping the account saves the close, not 200 bytes)
    let e = r.x.build(&w, 40_001, BH, tip, &AltSource::none(), 0).err().unwrap();
    assert!(e.starts_with("oversized("), "{e}");
    assert_eq!(build_reason(&e), "oversized");
    // a learned table naming the PumpSwap pool and every account the message could load
    let full = { let m = r.x.compile(&w, &build::route_ix(r.x.program, r.x.payer, build::ata_of(&r.x.payer, &WSOL, &crate::pda::TOKEN_PROGRAM), w.size, 40_001,
        &[leg_of(&r.x, &w, true), leg_of(&r.x, &w, false)], None).unwrap(), Some(build::AtaOps { mint: M2, token_program: *crate::pda::TOKEN_PROGRAM, close: true }), tip, BH, &[], None, 0).unwrap();
        m.msg.loadable.clone() };
    assert!(full.len() > 20, "{}", full.len());
    // (a learned table holds the token program too: loadable once no CloseAccount invokes it)
    let table = [0xab; 32];
    let entries = |n: usize| -> Vec<Option<Pk>> { full[..n].iter().map(|k| Some(*k)).chain([Some(*crate::pda::TOKEN_PROGRAM)]).collect() };
    let tables: HashMap<Pk, Vec<Option<Pk>>> = [(table, entries(full.len()))].into_iter().collect();
    let by_pool: HashMap<Pk, Vec<Pk>> = [(w.buy.pool, vec![table])].into_iter().collect();
    let alts = AltSource { tables: &tables, by_pool: &by_pool };
    let b = r.x.build(&w, 40_001, BH, tip, &alts, 0).unwrap();
    assert_eq!((b.alt_fallback, b.index_tables.clone(), b.creates_ata(), b.closes_ata()), ("alt_index", vec![table], true, true));
    assert!(b.fits() && build::tx_bytes(&b.msg) <= build::MAX_TX_BYTES);
    // the executor's own decision with that table: a would-send whose signed bytes pass every check (the table resolves)
    let i = r.x.inputs(&r.view, 100, t);
    let d = r.x.decide(w.clone(), &i, &r.view, &alts, 100, t);
    assert_eq!(d.reason, "would_send", "{d:?}");
    let l = r.lines("attempts")[0].clone();
    assert_eq!((l["tx"]["alt_fallback"].as_str(), l["tx"]["alt_index_tables"][0].as_str(), l["dry_run"]["checks_ok"].as_bool()), (Some("alt_index"), Some(b58(&table).as_str()),
        Some(true)), "{}", l["dry_run"]["checks"]);
    assert!(l["tx"]["bytes"].as_u64().unwrap() <= 1_232);
    // a route whose expected profit (3M) covers min_profit and the rent a kept account locks; the 50,000 one does not
    let mut rich = worst_route();
    (rich.back, rich.state_version) = (rich.size + 3_000_000, 2);
    // fewer accounts in the index: a table size where create+close does not fit and keeping the account would (held-set
    // additions configured)
    let n = (0..full.len()).find(|n| {
        let part: HashMap<Pk, Vec<Option<Pk>>> = [(table, entries(*n))].into_iter().collect();
        r.x.builder.held_max = 40;
        let ok = r.x.build(&rich, 40_001, BH, tip, &AltSource { tables: &part, by_pool: &by_pool }, 0).is_ok_and(|b| b.alt_fallback == "held_ata");
        r.x.builder.held_max = 0;
        ok
    }).expect("some table size makes the held-ATA fallback the one that fits");
    let part: HashMap<Pk, Vec<Option<Pk>>> = [(table, entries(n))].into_iter().collect();
    let alts = AltSource { tables: &part, by_pool: &by_pool };
    // the default: no held-set addition, the bundle is refused
    let e = r.x.build(&rich, 40_001, BH, tip, &alts, 0).err().unwrap();
    assert!(e.starts_with("oversized(") && !e.contains("held_ata"), "{e}");
    // configured: the poor route cannot pay the rent; the rich one keeps the account and its route asks the rent too
    r.x.builder.held_max = 40;
    let e = r.x.build(&w, 40_001, BH, tip, &alts, 0).err().unwrap();
    assert!(e.starts_with("oversized(") && e.contains("held_ata: expected 50000 below min_profit + the rent kept"), "{e}");
    let b = r.x.build(&rich, 40_001, BH, tip, &alts, 0).unwrap();
    assert_eq!((b.alt_fallback, b.creates_ata(), b.closes_ata(), b.held_addition(), b.min_profit, b.held_rent),
        ("held_ata", true, false, true, 40_001 + build::HELD_RENT_BOUND, build::HELD_RENT_BOUND));
    let raw = build::sign(&b.msg, &wallet_key());
    let (tx, _) = crate::tx::parse_wire(&raw).unwrap();
    let list = |t: &Pk| alts.list(t);
    assert_eq!(route_of(&tx, &tx.resolve(list).unwrap(), &r.x.program).unwrap().min_profit, 40_001 + build::HELD_RENT_BOUND, "on chain");
    // the held set full (held_max tokens held beyond WSOL, USDC, USDT): oversized
    r.x.builder.held_max = 1;
    r.x.held.insert([248; 32]);
    let e = r.x.build(&rich, 40_001, BH, tip, &alts, 0).err().unwrap();
    assert!(e.contains("held_ata: 1 tokens held of held_max 1"), "{e}");
    r.x.held.remove(&[248; 32]);
    // the executor's own dry-run decision: a held-set addition its checks pass from the signed bytes (configured and
    // allowed, the close does not fit, the rent in min_profit)
    r.x.builder.held_max = 40;
    let i = r.x.inputs(&r.view, 100, t + S);
    let d = r.x.decide(rich.clone(), &i, &r.view, &alts, 100, t + S);
    assert_eq!(d.reason, "would_send", "{d:?}");
    let l = r.lines("attempts")[1].clone();
    assert_eq!((l["tx"]["alt_fallback"].as_str(), l["tx"]["held_addition"].as_bool(), l["tx"]["held_rent_lamports"].as_u64(), l["dry_run"]["checks_ok"].as_bool()),
        (Some("held_ata"), Some(true), Some(build::HELD_RENT_BOUND), Some(true)), "{}", l["dry_run"]["checks"]);
    assert_eq!(l["min_profit_onchain"].as_u64(), Some(100_000 + 5_000 + 1 + build::HELD_RENT_BOUND), "the tip (capped), the fee, the margin floor and the rent");
    assert_eq!((r.n("held_addition"), r.n("dry_run_ok")), (1, 2), "counted");
    let c = l["dry_run"]["checks"].as_array().unwrap().iter().find(|c| c["check"] == "held_addition").unwrap().clone();
    assert!(c["detail"]["with_close"]["bytes"].as_u64().unwrap() > build::MAX_TX_BYTES as u64, "{c}");
    // max_alts = 0: no table from the index
    r.x.builder.max_alts = 0;
    assert!(r.x.build(&w, 40_001, BH, tip, &alts, 0).err().unwrap().starts_with("oversized"));
}

/// one leg of `worst_route` as the executor builds it
fn leg_of(x: &Exec, r: &RouteIn, buy: bool) -> build::Leg {
    let (m, data, tin, tout, live, end, ext) = if buy { (&r.buy, &r.buy_data, *WSOL, r.mint, &r.buy_live, r.buy_end, r.buy_ext) }
        else { (&r.sell, &r.sell_data, r.mint, *WSOL, &r.sell_live, r.sell_end, r.sell_ext) };
    build::leg(&build::LegIn { m, pool: data, tin, tout, amount_in: r.size, payer: x.payer, pump: x.pump.as_ref(), dlmm_live: live, dlmm_end: end, dlmm_ext: ext }).unwrap()
}

// ------------------------------------------------------------------------------------------------ WP-06: LiteSVM vectors

/// a venue-parity fixture (testdata/venue-parity/pools: the venue harness's snapshots): every account (owner, data) and
/// its Clock (slot, unix time)
struct ParityFx { pool: Pk, venue: Venue, slot: u64, unix: i64, accts: Vec<(Pk, Pk, Vec<u8>)> }

fn parity_fx(file: &str) -> ParityFx {
    use base64::Engine as _;
    let path = format!("{}/testdata/venue-parity/pools/{file}", env!("CARGO_MANIFEST_DIR"));
    let v: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    let accts = v["accounts"].as_array().unwrap().iter().map(|a| (pk(a["pubkey"].as_str().unwrap()), pk(a["owner"].as_str().unwrap()),
        base64::engine::general_purpose::STANDARD.decode(a["data"].as_str().unwrap()).unwrap())).collect();
    ParityFx { pool: pk(v["pool"].as_str().unwrap()), venue: Venue::parse(v["venue"].as_str().unwrap()).unwrap(), slot: v["clock"]["slot"].as_u64().unwrap(),
        unix: v["clock"]["unix_timestamp"].as_i64().unwrap(), accts }
}

impl ParityFx {
    fn data(&self, k: &Pk) -> Option<&Vec<u8>> { self.accts.iter().find(|a| a.0 == *k).map(|a| &a.2) }
    /// the engine's metadata (`pools::meta_of`, the token programs from the mints' owners)
    fn meta(&self) -> PoolMeta {
        let mut m = crate::pools::meta_of(self.venue, &self.pool, self.data(&self.pool).unwrap()).unwrap();
        let prog = |k: &Pk| self.accts.iter().find(|a| a.0 == *k).map_or(*crate::pda::TOKEN_PROGRAM, |a| a.1);
        (m.t0_prog, m.t1_prog) = (prog(&m.t0), prog(&m.t1));
        m
    }
}

/// One bundle of the vectors: its route (which pool buys), GLL3's quote vault scaled by `num`/1000, the wallet holding the
/// mid token's account or not, the on-chain min_profit (`profit_fail`: above anything the route can make)
struct Case { name: &'static str, num: u64, gll3_buys: bool, held: bool, profit_fail: bool }

/// PLAN WP-06 / go-live gate (rent-neutral create+close) on the real programs: the bundles arbx's builder makes for the
/// recorded HOTBOT route (PumpSwap GLL3 ↔ DLMM 6D4E; HOTBOT is a Token-2022 mint), written to
/// testdata/builder/bundle-vectors.json for program/venue-harness `tests/arbx_bundle.rs`, which executes them in LiteSVM
/// on the dumped mainnet programs (PumpSwap, its fee program, DLMM, SPL Token, Token-2022, the ATA program) and the
/// deployed nexus-v2 ELF. Each vector is the executor's own build (`Exec::build`: the CU limit, the loaded-data limit,
/// the create, the route, the close, the tip), signed by the test wallet; the quote is arbx-sizing's on the same
/// snapshot (the gap opened as program/venue-harness `tests/route.rs` does). The file must be what this builder makes:
/// `ARBX_BLESS=1` rewrites it
#[tokio::test]
async fn bundle_vectors_for_the_venue_harness() {
    use crate::quote::{self as q, Use};
    let (g, d) = (parity_fx("PumpSwap-GLL3CzybpSCLZdoACf8QUM5YrKVwyA65kQ2RcTsJxxzV.json"), parity_fx("DLMM-6D4EWF22HfQamimKhX47tqiu9DVCkcxDMrmhnSvewKAo.json"));
    let (gm, dm) = (g.meta(), d.meta());
    let mint = gm.t0;
    assert_eq!((dm.t0, gm.t1, dm.t1), (mint, *WSOL, *WSOL), "HOTBOT/SOL on both");
    let mint_prog = gm.t0_prog;
    assert_eq!(mint_prog, *crate::pda::TOKEN_2022, "HOTBOT is a Token-2022 mint: its account and its close are Token-2022's");
    let cfg = test_cfg(&std::env::temp_dir(), "");
    let payer = wallet_key().verifying_key().to_bytes();
    let pump = build::decode_pump_global(g.data(&crate::pools::PUMP_GLOBAL_CONFIG).unwrap()).unwrap();
    let arrays: Vec<(i64, Pk)> = { let mut v: Vec<(i64, Pk)> = d.accts.iter().filter(|a| a.1 == Venue::Dlmm.program() && a.2.len() == 10_136)
        .map(|a| (i64::from_le_bytes(a.2[8..16].try_into().unwrap()), a.0)).collect(); v.sort(); v };
    let tip_acct = tip_accounts()[0];
    let cases = [Case { name: "pump_buy_dlmm_sell_create_close", num: 880, gll3_buys: true, held: false, profit_fail: false },
        Case { name: "pump_buy_dlmm_sell_held", num: 880, gll3_buys: true, held: true, profit_fail: false },
        Case { name: "pump_buy_dlmm_sell_create_close_profit_fail", num: 880, gll3_buys: true, held: false, profit_fail: true },
        Case { name: "dlmm_buy_pump_sell_create_close", num: 1_120, gll3_buys: false, held: false, profit_fail: false }];
    let mk = |alts: Vec<(Pk, Vec<Pk>)>| Exec::assemble(&cfg, Rpc::race(vec![]), None, Rec::off(), crossbeam_channel::unbounded().0, vec![], alts, Some(pump.clone()),
        [*WSOL].into_iter().collect(), Mode::Shadow, None).unwrap();
    let ours = [build::ata_of(&payer, &WSOL, &crate::pda::TOKEN_PROGRAM), build::ata_of(&payer, &mint, &mint_prog), build::pump_uva(&payer)];
    // each case's route, quoted by arbx-sizing on the snapshot with GLL3's quote vault scaled (the gap)
    let mut routes: Vec<(RouteIn, u64, u64, u64)> = Vec::new();
    for c in &cases {
        let q0 = u64::from_le_bytes(g.data(&gm.vault1).unwrap()[64..72].try_into().unwrap());
        let scaled = q0 / 1_000 * c.num;
        let mut accts: HashMap<Pk, crate::store::Acct> = HashMap::default();
        for fx in [&g, &d] {
            for (k, _, data) in &fx.accts {
                let mut data = data.clone();
                if *k == gm.vault1 { data[64..72].copy_from_slice(&scaled.to_le_bytes()); }
                accts.insert(*k, crate::store::Acct::rpc(Arc::from(data), fx.slot, 0, 0, crate::feeds::src::RPC_BOOT));
            }
        }
        let get = |k: &Pk| accts.get(k);
        let usable = |_: i64| true;
        let src = q::Src { get: &get, arrays: &arrays, usable: &usable, clock: q::clock(d.slot, d.unix) };
        let u = Use::Route { dlmm_budget: q::DLMM_BUDGET_ALONE };
        let (bm, sm) = if c.gll3_buys { (&gm, &dm) } else { (&dm, &gm) };
        let (lb, ls) = (q::leg(bm, bm.t0 == *WSOL, &src, u).unwrap(), q::leg(sm, sm.t0 == mint, &src, u).unwrap());
        let ladder: Vec<u64> = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0].iter().map(|s| (s * 1e9) as u64).collect();
        let t = q::best(&lb, &ls, &ladder, 1_000_000, 1_000_000_000).unwrap();
        assert!(t.profit() > 100_000, "{}: the gap pays: {}", c.name, t.profit());
        let (wb, ws) = (lb.walk(t.x).unwrap(), ls.walk(t.mid).unwrap());
        let (cu, cu_src) = crate::cu_table::CuModel::default().route(bm.venue, wb.crossed, sm.venue, ws.crossed);
        let mut r = route_m2(1, 2, 0, 1);
        (r.buy, r.sell, r.mint, r.mint_prog) = (bm.clone(), sm.clone(), mint, mint_prog);
        (r.buy_data, r.sell_data) = (accts[&bm.pool].data.to_vec(), accts[&sm.pool].data.to_vec());
        (r.size, r.mid, r.back, r.spent, r.buy_end, r.sell_end) = (t.x, wb.out, ws.out, wb.spent, wb.end, ws.end);
        let live: Vec<i64> = arrays.iter().map(|a| a.0).collect();
        (r.buy_live, r.sell_live) = if c.gll3_buys { (vec![], live) } else { (live, vec![]) };
        (r.cu, r.cu_src, r.cu_ata, r.mid_held, r.uva) = (cu, cu_src.as_str(), crate::cu_table::CuModel::default().ata_ops(), Some(c.held), Some(true));
        r.sizes = accts.iter().map(|(k, a)| (*k, a.data.len() as u32)).collect();
        r.sizes.sort();
        let expected = r.expected();
        // the tip and min_profit as the executor sets them (70% of the edge, the base fee, the margin floor 1)
        let tip_l = crate::tip::TipModel::default().tip(expected - 5_000, false).lamports;
        let min_profit = if c.profit_fail { expected as u64 + 1_000_000 } else { tip_l + 5_000 + 1 };
        routes.push((r, tip_l, min_profit, scaled));
    }
    // the [exec] lookup table: every account the bundles could load from one (the payer's own accounts and its volume
    // accumulator left out: a shared table holds none of ours), both directions
    let mut keys: Vec<Pk> = Vec::new();
    let x0 = mk(vec![]);
    for (r, _, min_profit, _) in &routes {
        let route = build::route_ix(x0.program, payer, ours[0], r.size, *min_profit, &[leg_of(&x0, r, true), leg_of(&x0, r, false)], None).unwrap();
        let plan = Some(build::AtaOps { mint, token_program: mint_prog, close: true });
        for k in x0.compile(r, &route, plan, Some((tip_acct, 1)), BH, &[], None, 0).unwrap().msg.loadable { if !ours.contains(&k) && !keys.contains(&k) { keys.push(k); } }
    }
    let table = ([0xa1u8; 32], keys);
    let x = mk(vec![table.clone()]);
    let mut cases_out = Vec::new();
    for (c, (r, tip_l, min_profit, scaled)) in cases.iter().zip(&routes) {
        let (bm, sm) = (&r.buy, &r.sell);
        let b = x.build(r, *min_profit, BH, Some((tip_acct, *tip_l)), &AltSource::none(), 0).unwrap_or_else(|e| panic!("{}: {e}", c.name));
        assert!(b.fits() && b.alt_fallback == "none", "{}: {} bytes", c.name, build::tx_bytes(&b.msg));
        assert_eq!((b.creates_ata(), b.closes_ata()), (!c.held, !c.held), "{}", c.name);
        let raw = build::sign(&b.msg, &wallet_key());
        // the dry run's checks pass on the signed bytes (the table resolves), every value re-derived from them
        let mut want = x.want(r, payer, BH, Some((tip_acct, *tip_l)), *min_profit, x.pol.margin_floor, &raw, &AltSource::none());
        want.signer = payer;
        assert_eq!(failing(&raw, &want), Vec::<String>::new(), "{}", c.name);
        // the signed instructions recompile to the same message on the tables it names (what `with_close` builds on)
        let (tx, _) = crate::tx::parse_wire(&raw).unwrap();
        let all = tx.resolve(|t| want.alts.get(t).cloned()).unwrap();
        let tables: Vec<Alt> = tx.lookups.iter().map(|l| Alt::new(l.table, &want.alts[&l.table])).collect();
        let again = build::compile_v0(payer, &signed_ixs(&tx, &all).unwrap(), BH, &tables.iter().collect::<Vec<_>>(), &[tip_acct]).unwrap();
        assert_eq!(again.bytes, b.msg.bytes, "{}", c.name);
        cases_out.push(json!({ "name": c.name, "gll3_quote_vault_scale": [c.num, 1_000], "gll3_quote_vault": b58(&gm.vault1), "gll3_quote_vault_amount": scaled,
            "buy_pool": b58(&bm.pool), "sell_pool": b58(&sm.pool), "mint": b58(&mint), "token_program": b58(&mint_prog),
            "mid_account": b58(&build::ata_of(&payer, &mint, &mint_prog)), "held": c.held, "size": r.size, "spent": r.spent, "back": r.back, "expected_profit": r.expected(),
            "min_profit": min_profit, "tip": [b58(&tip_acct), tip_l], "cu_limit": b.cu_limit, "cu_src": b.cu_src, "cu_route": r.cu, "cu_ata": [r.cu_ata.0, r.cu_ata.1],
            "loaded_data_limit": b.loaded_data_limit,
            "expect": if c.profit_fail { "profit_fail" } else { "ok" }, "bytes": raw.len(), "tx_b64": base64_of(&raw) }));
    }
    let (tk, ta) = table;
    let doc = json!({ "schema": "arbx.bundle-vectors/1", "about": "arbx's own bundles (src/exec/tests.rs bundle_vectors_for_the_venue_harness), executed by \
        program/venue-harness tests/arbx_bundle.rs on the dumped mainnet programs and the deployed nexus-v2 ELF (PLAN WP-06)",
        "payer": b58(&payer), "payer_seed_byte": 1, "program": b58(&pk(&cfg.exec.program)), "blockhash": b58(&BH), "clock_from": "DLMM-6D4E",
        "fixtures": ["PumpSwap-GLL3CzybpSCLZdoACf8QUM5YrKVwyA65kQ2RcTsJxxzV.json", "DLMM-6D4EWF22HfQamimKhX47tqiu9DVCkcxDMrmhnSvewKAo.json"],
        "alt": { "table": b58(&tk), "addrs": ta.iter().map(b58).collect::<Vec<_>>() }, "cases": cases_out });
    let path = format!("{}/testdata/builder/bundle-vectors.json", env!("CARGO_MANIFEST_DIR"));
    let text = serde_json::to_string_pretty(&doc).unwrap() + "\n";
    if std::env::var_os("ARBX_BLESS").is_some() {
        std::fs::create_dir_all(std::path::Path::new(&path).parent().unwrap()).unwrap();
        std::fs::write(&path, &text).unwrap();
    }
    let have = std::fs::read_to_string(&path).unwrap_or_default();
    assert!(have == text, "{path} is not what this builder makes: ARBX_BLESS=1 cargo test --release --lib bundle_vectors (then run program/venue-harness tests/arbx_bundle.rs)");
}

// ------------------------------------------------------------------------------------------------ WP-21: CLMM vectors

/// How a CLMM vector opens its price gap on the snapshots: a token vault's amount scaled by num/1000 (PumpSwap's quote
/// vault, AMM v4's coin vault), or an Orca pool's price moved by k ticks (as program/venue-harness `tests/clmm_route.rs`
/// `moved_whirlpool`: the sqrt price in the middle of tick (tick + k), the current tick set to it). Each case tries its
/// candidates in order and keeps the first whose best route pays 0.0001 SOL (deterministic: the same on every run)
#[derive(Clone, Copy, Debug)]
enum Gap { Vault { pool: &'static str, side: u8, nums: &'static [u64] }, WhirlTicks { pool: &'static str, ks: &'static [i32] } }

/// One CLMM bundle: the buy and sell pools (fixture prefixes), the gap, the wallet holding the mid token's account or not,
/// min_profit above what the route makes (`profit_fail`)
struct ClmmCase { name: &'static str, buy: &'static str, sell: &'static str, gap: Gap, held: bool, profit_fail: bool }

/// the byte patches of a gap candidate: (key, offset, bytes)
fn gap_patches(g: Gap, i: usize) -> Option<Vec<(Pk, usize, Vec<u8>)>> {
    use crate::quote::clmm_tests::any_fx;
    match g {
        Gap::Vault { pool, side, nums } => {
            let num = *nums.get(i)?;
            let fx = any_fx(pool);
            let m = crate::quote::clmm_tests::meta(fx);
            let v = if side == 0 { m.vault0 } else { m.vault1 };
            let amount = u64::from_le_bytes(fx.accts[&v].1[64..72].try_into().unwrap());
            Some(vec![(v, 64, (amount / 1_000 * num).to_le_bytes().to_vec())])
        }
        Gap::WhirlTicks { pool, ks } => {
            let k = *ks.get(i)?;
            let fx = any_fx(pool);
            let d = &fx.accts[&fx.pool].1;
            let t = i32::from_le_bytes(d[81..85].try_into().unwrap()) + k;
            let sp = (1.0001f64.powf((t as f64 + 0.5) / 2.0) * 18_446_744_073_709_551_616.0) as u128;
            Some(vec![(fx.pool, 65, sp.to_le_bytes().to_vec()), (fx.pool, 81, t.to_le_bytes().to_vec())])
        }
    }
}

/// One CLMM route of the vectors, built: the route as the executor takes it, the tip and min_profit the executor sets, the
/// gap's patches, the fixtures, the later snapshot (its Clock), the legs' steps
struct ClmmBuilt { r: RouteIn, tip: u64, min_profit: u64, patches: Vec<(Pk, usize, Vec<u8>)>, files: [String; 2], clock_from: String, steps: [u32; 2], gap: String }

/// the vectors' cases (`clmm_bundle_vectors_for_the_venue_harness`)
fn clmm_cases() -> Vec<ClmmCase> {
    const UP: &[u64] = &[1_000, 1_020, 1_050, 1_100, 1_250, 1_500, 2_000, 3_000, 5_000];
    const DOWN: &[u64] = &[1_000, 980, 950, 900, 800, 650, 500, 330, 200];
    const KUP: &[i32] = &[60, 120, 250, 500];
    const KDOWN: &[i32] = &[-60, -120, -250, -500];
    vec![
        ClmmCase { name: "whirl_buy_pump_sell_create_close", buy: "FAqh", sell: "9qKx", gap: Gap::Vault { pool: "9qKx", side: 1, nums: UP }, held: false, profit_fail: false },
        ClmmCase { name: "pump_buy_whirl_sell_create_close", buy: "9qKx", sell: "FAqh", gap: Gap::Vault { pool: "9qKx", side: 1, nums: DOWN }, held: false, profit_fail: false },
        ClmmCase { name: "whirl_buy_rayclmm_sell_create_close", buy: "4uny", sell: "DCAL", gap: Gap::WhirlTicks { pool: "4uny", ks: KUP }, held: false, profit_fail: false },
        ClmmCase { name: "rayclmm_buy_whirl_sell_held", buy: "DCAL", sell: "4uny", gap: Gap::WhirlTicks { pool: "4uny", ks: KDOWN }, held: true, profit_fail: false },
        ClmmCase { name: "rayclmm_buy_ammv4_sell_create_close", buy: "3ucN", sell: "58oQ", gap: Gap::Vault { pool: "58oQ", side: 0, nums: UP }, held: false, profit_fail: false },
        ClmmCase { name: "whirl_buy_pump_sell_profit_fail", buy: "FAqh", sell: "9qKx", gap: Gap::Vault { pool: "9qKx", side: 1, nums: UP }, held: false, profit_fail: true },
    ]
}

/// PumpSwap's GlobalConfig of the vectors (PumpSwap 9qKx's snapshot)
fn clmm_pump() -> PumpGlobal {
    let fx = crate::quote::clmm_tests::any_fx("9qKx");
    build::decode_pump_global(&fx.accts[&*crate::pools::PUMP_GLOBAL_CONFIG].1).unwrap()
}

/// Case `c` quoted by arbx-sizing on its patched snapshots: the first gap candidate whose best route pays 0.0001 SOL, the
/// route built as the engine's `route_in` fills it (the tick arrays the engine names, the bitmap extension when it exists)
fn clmm_built(c: &ClmmCase) -> ClmmBuilt {
    use crate::quote::clmm_tests::{any_fx, meta};
    use crate::quote::{self as q, Use};
    let (fb, fs) = (any_fx(c.buy), any_fx(c.sell));
    let (bm, sm) = (meta(fb), meta(fs));
    let mint = if bm.t0 == *WSOL { bm.t1 } else { bm.t0 };
    assert!([sm.t0, sm.t1].contains(&mint) && [sm.t0, sm.t1].contains(&WSOL), "{}: one pair", c.name);
    let mint_prog = if bm.t0 == mint { bm.t0_prog } else { bm.t1_prog };
    // the later snapshot's Clock (Orca refuses one before its stamps)
    let later = if fb.unix >= fs.unix { fb } else { fs };
    let u = Use::Route { dlmm_budget: if bm.venue.walks() && sm.venue.walks() { q::DLMM_BUDGET_SHARED } else { q::DLMM_BUDGET_ALONE } };
    let mut found: Option<ClmmBuilt> = None;
    for i in 0.. {
        let Some(patches) = gap_patches(c.gap, i) else { break };
        // the store as the engine would hold it: both snapshots (the sell's last), patched, the accounts that do not exist empty
        let mut accts: HashMap<Pk, crate::store::Acct> = HashMap::default();
        for fx in [fb, fs] {
            for (k, (_, d)) in &fx.accts {
                let mut d = d.clone();
                for (pk_, o, b) in &patches { if pk_ == k { d[*o..*o + b.len()].copy_from_slice(b); } }
                accts.insert(*k, crate::store::Acct::rpc(Arc::from(d), fx.slot, 0, 0, crate::feeds::src::RPC_BOOT));
            }
            for k in &fx.absent { accts.entry(*k).or_insert_with(|| crate::store::Acct::rpc(Arc::from(&[][..]), fx.slot, 0, 0, crate::feeds::src::RPC_BOOT)); }
        }
        let get = |k: &Pk| accts.get(k);
        let getv = |k: &Pk| accts.get(k).map(|a| a.data.to_vec());
        // the arrays the engine follows (`pools::clmm_arrays`, as `initial_dlmm_arrays` sets them at boot)
        let follow = |m: &PoolMeta| if m.venue.is_clmm() { crate::pools::clmm_arrays(m, &getv, &[]) } else { vec![] };
        let (ab, as_) = (follow(&bm), follow(&sm));
        let all = |_: i64| true;
        let (srcb, srcs) = (q::Src { get: &get, arrays: &ab, usable: &all, clock: q::clock(later.slot, later.unix) },
            q::Src { get: &get, arrays: &as_, usable: &all, clock: q::clock(later.slot, later.unix) });
        let (zb, zs) = (bm.t0 == *WSOL, sm.t0 == mint);
        let (lb, ls) = (q::leg(&bm, zb, &srcb, u).unwrap_or_else(|w| panic!("{}: buy leg {w:?}", c.name)), q::leg(&sm, zs, &srcs, u).unwrap_or_else(|w| panic!("{}: sell leg {w:?}", c.name)));
        let ladder: Vec<u64> = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0].iter().map(|s| (s * 1e9) as u64).collect();
        let Ok(t) = q::best(&lb, &ls, &ladder, 1_000_000, 2_000_000_000) else { continue };
        if t.profit() < 100_000 { continue; }
        let (wb, ws) = (lb.walk(t.x).unwrap(), ls.walk(t.mid).unwrap());
        let names = |m: &PoolMeta, l: &q::Leg, x: u64, z: bool| -> Vec<i64> {
            match m.venue {
                Venue::RayClmm => l.clmm_arrays(x).unwrap().unwrap().into_iter().map(i64::from).collect(),
                Venue::Whirlpool => crate::venues::clmm::whirl_leg_starts(&accts[&m.pool].data, z).unwrap().into_iter().map(i64::from).collect(),
                _ => vec![],
            }
        };
        let (nb, ns) = (names(&bm, &lb, t.x, zb), names(&sm, &ls, t.mid, zs));
        let (cu, cu_src) = crate::cu_table::CuModel::default().route(bm.venue, wb.crossed, sm.venue, ws.crossed);
        let mut r = route_m2(1, 2, 0, 1);
        (r.buy, r.sell, r.mint, r.mint_prog) = (bm.clone(), sm.clone(), mint, mint_prog);
        (r.buy_data, r.sell_data) = (accts[&bm.pool].data.to_vec(), accts[&sm.pool].data.to_vec());
        (r.size, r.mid, r.back, r.spent, r.buy_end, r.sell_end) = (t.x, wb.out, ws.out, wb.spent, wb.end, ws.end);
        (r.buy_live, r.sell_live) = (nb, ns);
        let ext = |m: &PoolMeta| (m.venue == Venue::RayClmm).then(|| m.clmm_ext().copied()).flatten().filter(|e| accts.get(e).is_some_and(|a| !a.data.is_empty()));
        (r.buy_ext, r.sell_ext) = (ext(&bm), ext(&sm));
        (r.cu, r.cu_src, r.cu_ata, r.mid_held, r.uva) = (cu, cu_src.as_str(), crate::cu_table::CuModel::default().ata_ops(), Some(c.held), Some(true));
        r.sizes = accts.iter().map(|(k, a)| (*k, a.data.len() as u32)).collect();
        r.sizes.sort();
        let expected = r.expected();
        assert_eq!(expected, t.profit(), "{}: the route's expected profit is the trip's", c.name);
        let tip_l = crate::tip::TipModel::default().tip(expected - 5_000, false).lamports;
        let min_profit = if c.profit_fail { expected as u64 + 1_000_000 } else { tip_l + 5_000 + 1 };
        found = Some(ClmmBuilt { r, tip: tip_l, min_profit, patches, files: [fb.file.clone(), fs.file.clone()], clock_from: later.file.clone(), steps: [wb.crossed, ws.crossed],
            gap: format!("{:?} candidate {i}", c.gap) });
        break;
    }
    found.unwrap_or_else(|| panic!("{}: no gap candidate pays", c.name))
}

/// The lookup table the vectors' bundles load their accounts from: every account `x0`'s compile of each route names (both
/// legs, the create and close, the tip), the payer's own accounts left out (a shared table holds none of ours)
fn clmm_alt(x0: &Exec, built: &[ClmmBuilt], payer: Pk, tip_acct: Pk) -> Vec<Pk> {
    let mut keys: Vec<Pk> = Vec::new();
    for b in built {
        let r = &b.r;
        let ours = [build::ata_of(&payer, &WSOL, &crate::pda::TOKEN_PROGRAM), build::ata_of(&payer, &r.mint, &r.mint_prog), build::pump_uva(&payer)];
        let route = build::route_ix(x0.program, payer, ours[0], r.size, b.min_profit, &[leg_of(x0, r, true), leg_of(x0, r, false)], None).unwrap();
        let plan = Some(build::AtaOps { mint: r.mint, token_program: r.mint_prog, close: true });
        for k in x0.compile(r, &route, plan, Some((tip_acct, 1)), BH, &[], None, 0).unwrap().msg.loadable { if !ours.contains(&k) && !keys.contains(&k) { keys.push(k); } }
    }
    keys
}

/// PLAN-ADDENDUM WP-21 point 6 (the on-chain route program): routes through Raydium CLMM and Orca Whirlpool legs as the
/// engine builds them (`Exec::build`: the CU limit, the loaded-data limit, the create, nexus-v2's route with the
/// `swap_v2` legs `build::leg` lays out, the close, the tip), written to testdata/builder/bundle-vectors-clmm.json for
/// program/venue-harness `tests/arbx_bundle_clmm.rs`, which runs them in LiteSVM on the dumped mainnet programs (Orca
/// Whirlpool, Raydium CLMM, PumpSwap and its fee program, Raydium AMM v4, SPL Token, the ATA program) and the deployed
/// nexus-v2 ELF. The pairs come from the venue-parity fixtures (testdata/venue-parity: the pools sharing a mint):
/// Whirlpool FAqh ↔ PumpSwap 9qKx (2zMM/SOL) both ways, Raydium CLMM DCAL ↔ Whirlpool 4uny (J6pQ/SOL, the pair of
/// tests/clmm_route.rs) both ways, Raydium CLMM 3ucN → Raydium AMM v4 58oQ (USDC/SOL), and one whose min_profit the
/// route cannot reach. The quotes are arbx-sizing's on the same patched snapshots, the Clock the later snapshot's; the
/// tick arrays the legs name are the engine's (Raydium: `Leg::clmm_arrays` over the arrays the engine follows,
/// `pools::clmm_arrays`; Orca: `venues::clmm::whirl_leg_starts`). `ARBX_BLESS=1` rewrites the file
#[tokio::test]
async fn clmm_bundle_vectors_for_the_venue_harness() {
    let cases = clmm_cases();
    let built: Vec<ClmmBuilt> = cases.iter().map(clmm_built).collect();
    let cfg = test_cfg(&std::env::temp_dir(), "");
    let payer = wallet_key().verifying_key().to_bytes();
    let pump = clmm_pump();
    let tip_acct = tip_accounts()[0];
    let mk = |alts: Vec<(Pk, Vec<Pk>)>| Exec::assemble(&cfg, Rpc::race(vec![]), None, Rec::off(), crossbeam_channel::unbounded().0, vec![], alts, Some(pump.clone()),
        [*WSOL].into_iter().collect(), Mode::Shadow, None).unwrap();
    // the [exec] lookup table: every account the bundles load from one (the payer's own accounts left out)
    let x0 = mk(vec![]);
    let keys = clmm_alt(&x0, &built, payer, tip_acct);
    assert!(keys.len() <= 256, "{} keys for one table", keys.len());
    let table = ([0xa2u8; 32], keys);
    let x = mk(vec![table.clone()]);
    let mut cases_out = Vec::new();
    for (c, b) in cases.iter().zip(&built) {
        let r = &b.r;
        let bx = x.build(r, b.min_profit, BH, Some((tip_acct, b.tip)), &AltSource::none(), 0).unwrap_or_else(|e| panic!("{}: {e}", c.name));
        assert!(bx.fits() && bx.alt_fallback == "none", "{}: {} bytes", c.name, build::tx_bytes(&bx.msg));
        assert_eq!((bx.creates_ata(), bx.closes_ata()), (!c.held, !c.held), "{}", c.name);
        let raw = build::sign(&bx.msg, &wallet_key());
        let mut want = x.want(r, payer, BH, Some((tip_acct, b.tip)), b.min_profit, x.pol.margin_floor, &raw, &AltSource::none());
        want.signer = payer;
        assert_eq!(failing(&raw, &want), Vec::<String>::new(), "{}", c.name);
        let (tx, _) = crate::tx::parse_wire(&raw).unwrap();
        let all = tx.resolve(|t| want.alts.get(t).cloned()).unwrap();
        let tables: Vec<Alt> = tx.lookups.iter().map(|l| Alt::new(l.table, &want.alts[&l.table])).collect();
        let again = build::compile_v0(payer, &signed_ixs(&tx, &all).unwrap(), BH, &tables.iter().collect::<Vec<_>>(), &[tip_acct]).unwrap();
        assert_eq!(again.bytes, bx.msg.bytes, "{}", c.name);
        // the route instruction's legs as nexus-v2 parses them: each venue's swap_v2, its account count, the amount at offset 8
        let (bl, sl) = (leg_of(&x, r, true), leg_of(&x, r, false));
        let leg_json = |m: &PoolMeta, l: &build::Leg, names: &[i64], steps: u32| json!({ "venue": crate::replay::venue_name(m.venue), "pool": b58(&m.pool),
            "program": b58(&l.program), "n_accounts": l.accounts.len(), "data_len": l.data.len(), "amount_offset": l.amount_offset, "tick_arrays": names,
            "steps": steps, "cu_allowed": m.venue.leg_cu(steps) });
        cases_out.push(json!({ "name": c.name, "gap": b.gap, "patches": b.patches.iter().map(|(k, o, d)| json!([b58(k), o, d.iter().map(|x| format!("{x:02x}")).collect::<String>()])).collect::<Vec<_>>(),
            "fixtures": b.files, "clock_from": b.clock_from, "buy_pool": b58(&r.buy.pool), "sell_pool": b58(&r.sell.pool), "mint": b58(&r.mint), "token_program": b58(&r.mint_prog),
            "mid_account": b58(&build::ata_of(&payer, &r.mint, &r.mint_prog)), "held": c.held, "size": r.size, "mid": r.mid, "spent": r.spent, "back": r.back,
            "expected_profit": r.expected(), "min_profit": b.min_profit, "tip": [b58(&tip_acct), b.tip], "cu_limit": bx.cu_limit, "cu_src": bx.cu_src, "cu_route": r.cu,
            "cu_ata": [r.cu_ata.0, r.cu_ata.1], "loaded_data_limit": bx.loaded_data_limit, "legs": [leg_json(&r.buy, &bl, &r.buy_live, b.steps[0]), leg_json(&r.sell, &sl, &r.sell_live, b.steps[1])],
            "expect": if c.profit_fail { "profit_fail" } else { "ok" }, "bytes": raw.len(), "tx_b64": base64_of(&raw) }));
    }
    let (tk, ta) = table;
    let doc = json!({ "schema": "arbx.bundle-vectors/1", "about": "arbx's own bundles through Raydium CLMM and Orca Whirlpool legs (src/exec/tests.rs \
        clmm_bundle_vectors_for_the_venue_harness), executed by program/venue-harness tests/arbx_bundle_clmm.rs on the dumped mainnet programs and the \
        deployed nexus-v2 ELF (PLAN-ADDENDUM WP-21 point 6)", "payer": b58(&payer), "payer_seed_byte": 1, "program": b58(&pk(&cfg.exec.program)), "blockhash": b58(&BH),
        "alt": { "table": b58(&tk), "addrs": ta.iter().map(b58).collect::<Vec<_>>() }, "cases": cases_out });
    let path = format!("{}/testdata/builder/bundle-vectors-clmm.json", env!("CARGO_MANIFEST_DIR"));
    let text = serde_json::to_string_pretty(&doc).unwrap() + "\n";
    if std::env::var_os("ARBX_BLESS").is_some() { std::fs::write(&path, &text).unwrap(); }
    let have = std::fs::read_to_string(&path).unwrap_or_default();
    assert!(have == text, "{path} is not what this builder makes: ARBX_BLESS=1 cargo test --release --lib clmm_bundle_vectors (then run program/venue-harness tests/arbx_bundle_clmm.rs)");
}

/// a round trip through venues `bv` (buy) and `sv` (sell): `route`'s DAMM v2 one with its venues changed (enough for a
/// check that refuses it before anything is built)
fn venue_route(bv: Venue, sv: Venue, n: u8) -> RouteIn {
    let mut r = route(n, damm(n + 1, MINT), 50_000, n as u64);
    (r.buy.venue, r.sell.venue) = (bv, sv);
    r
}

/// a canary that sends: no attempt cap, 1 ms between attempts, 0.2 SOL
const CANARY_OK: &str = "[canary]\nenabled = true\ncount = 0\nevery_ms = 1\nsize_sol = 0.2\n";

/// PLAN-ADDENDUM WP-21 (review F4, F3): the guard that keeps money off the CLMM venues. In a mode that sends (live,
/// canary), a route with a Raydium CLMM or Orca Whirlpool leg (the buy, the sell or both, beside an older venue or not)
/// through a venue switched to "quote" or "off" is refused `venue_quote_only` before anything is built: no attempt, no
/// in-flight entry, nothing fired; the older venues' routes still send. With the gate closed the refusal is the gated
/// decision's `reason_ungated`, never a would-send, while an older venue's route is a would-send. A venue switched to
/// "send" is not refused here (`a_send_venue_builds_its_clmm_route_and_a_dry_run_signs_it`)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_quote_only_guard_refuses_clmm_routes_before_anything_is_built() {
    let legs = [(Venue::RayClmm, Venue::DammV2), (Venue::DammV2, Venue::Whirlpool), (Venue::RayClmm, Venue::Whirlpool), (Venue::Whirlpool, Venue::RayClmm)];
    let ms = 10_000_000u64;
    for mode in [Mode::Live, Mode::Canary] {
        for (ray, whirl) in [("quote", "quote"), ("off", "off"), ("quote", "send"), ("send", "off")] {
            let extra = if mode == Mode::Canary { CANARY_OK } else { "" };
            let mut r = rig_cfg(&format!("qo-{}-{ray}-{whirl}", mode.as_str()), mode, extra, None, [*WSOL, MINT].into_iter().collect(), vec![],
                &|c: &mut Config| { c.pools.rayclmm = ray.into(); c.pools.whirlpool = whirl.into(); }).await;
            let t = now_ns();
            let mut n = 0u64;
            for (k, (bv, sv)) in legs.into_iter().enumerate() {
                let held_back = [bv, sv].iter().any(|v| (*v == Venue::RayClmm && ray != "send") || (*v == Venue::Whirlpool && whirl != "send"));
                if !held_back { continue; }
                n += 1;
                let d = r.decide(venue_route(bv, sv, 10 + 2 * k as u8), 100, t + n * ms);
                assert_eq!((d.verdict, d.reason.as_str(), d.attempt, d.sent, d.would_send, d.reason_ungated.as_deref()), ("reject", "venue_quote_only", None, None, false, None),
                    "{mode:?} {ray}/{whirl} {bv:?} -> {sv:?}: {d:?}");
            }
            assert!(n >= 3, "{n}");
            // nothing was built, held in flight or fired
            assert_eq!(r.x.inflight.len(), 0, "no in-flight entry");
            assert_eq!((r.lines("attempts").len(), r.got.lock().unwrap().len()), (0, 0), "no attempt, nothing reached the block engine");
            r.drain();
            assert!(r.buffered.is_empty(), "nothing fired");
            assert_eq!(r.n("reject_venue_quote_only"), n);
            // the older venues still send
            let d = r.decide(route(60, damm(61, MINT), 50_000, 1), 100, t + 10 * ms);
            assert_eq!((d.reason.as_str(), d.attempt), ("sent", Some(0)), "{mode:?}: {d:?}");
            let _ = r.settled().await;
            // the gate closed: the check still applies (the gated decision's reason_ungated, never a would-send); an older
            // venue's route is a would-send
            let gate = SendGate::new();
            gate.shadow("control", "pause-sending by test", false).unwrap();
            r.x.set_gate(gate);
            let (bv, sv) = if ray != "send" { (Venue::RayClmm, Venue::DammV2) } else { (Venue::DammV2, Venue::Whirlpool) };
            let d = r.decide(venue_route(bv, sv, 70), 100, t + 20 * ms);
            assert_eq!((d.reason.as_str(), d.would_send, d.attempt, d.reason_ungated.as_deref()), ("gate_shadow:control", false, None, Some("venue_quote_only")), "{d:?}");
            let d = r.decide(route(80, damm(81, MINT), 50_000, 2), 100, t + 30 * ms);
            assert_eq!((d.reason.as_str(), d.would_send, d.attempt.is_some(), d.reason_ungated.as_deref()), ("gate_shadow:control", true, true, None), "{d:?}");
        }
    }
}

/// PLAN-ADDENDUM WP-21 (review F4): with both venues switched to "send" a live run builds and sends routes with CLMM
/// legs (the vectors' Whirlpool -> PumpSwap and Raydium CLMM -> Whirlpool, on the venue-parity snapshots): one bundle each
/// reaches the block engine, its route instruction naming the venues' swap_v2 legs in order at the route's size; a dry
/// run with them left at "quote" builds and signs the same routes (its throwaway key), never refused `venue_quote_only`
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_send_venue_builds_its_clmm_route_and_a_dry_run_signs_it() {
    let cases = clmm_cases();
    let built: Vec<ClmmBuilt> = [&cases[0], &cases[3]].into_iter().map(clmm_built).collect();
    let pump = clmm_pump();
    let payer = wallet_key().verifying_key().to_bytes();
    let x0 = Exec::assemble(&test_cfg(&std::env::temp_dir(), ""), Rpc::race(vec![]), None, Rec::off(), crossbeam_channel::unbounded().0, vec![], vec![],
        Some(pump.clone()), [*WSOL].into_iter().collect(), Mode::Shadow, None).unwrap();
    let alt = ([0xa3u8; 32], clmm_alt(&x0, &built, payer, tip_accounts()[0]));
    let ms = 10_000_000u64;
    for mode in [Mode::Live, Mode::DryRun] {
        let (ray, whirl) = if mode == Mode::Live { ("send", "send") } else { ("quote", "quote") };
        let mut r = rig_cfg(&format!("clmm-build-{}", mode.as_str()), mode, "[live]\nmax_size_sol = 2.0\n", Some(pump.clone()), [*WSOL].into_iter().collect(),
            vec![alt.clone()], &|c: &mut Config| { c.pools.rayclmm = ray.into(); c.pools.whirlpool = whirl.into(); }).await;
        let t = now_ns();
        for (k, b) in built.iter().enumerate() {
            let d = r.decide(b.r.clone(), 100, t + k as u64 * ms);
            let raw = match mode {
                Mode::Live => {
                    assert_eq!((d.reason.as_str(), d.attempt, d.sent), ("sent", Some(k as u64), Some(true)), "{k}: {d:?}");
                    let Settled::Fired { fired, .. } = r.settled().await else { panic!("a fire result") };
                    assert!(fired.copies[0].ok, "{:?}", fired.copies[0]);
                    r.got.lock().unwrap()[k].0.clone()
                }
                _ => {
                    assert_eq!((d.reason.as_str(), d.would_send, d.attempt), ("would_send", true, Some(k as u64)), "{k}: {d:?}");
                    signed(&r.lines("attempts")[k])
                }
            };
            let (tx, _) = crate::tx::parse_wire(&raw).unwrap();
            let all = tx.resolve(|t| r.x.alt_lists.get(t).cloned()).unwrap();
            let seen = route_of(&tx, &all, &r.x.program).unwrap();
            assert_eq!((seen.amount_in, seen.legs[0].program, seen.legs[1].program), (b.r.size, b.r.buy.venue.program(), b.r.sell.venue.program()), "{k}");
            // the payer is the wallet; a dry run signs with its throwaway key, a live run with the wallet's
            assert_eq!(tx.keys[0], payer);
        }
        assert_eq!(r.n("reject_venue_quote_only"), 0);
    }
}

/// PLAN-ADDENDUM WP-21 (review F11): do CLMM routes fit a transaction with the lookup tables a run has? The vectors' five
/// routes built (the executor's own build: create, route, close, tip) with no table, with the default `[exec] alts` as
/// they are on chain (testdata/builder/exec-alts-20261006.json: the 10 of `v2_alts`' 12 tables that exist; they hold
/// both CLMM programs, the token programs, Memo and nexus-v2, and 28 of the 242 WP-21 pools), and with those plus one
/// table of the route's own accounts (the vectors' table)
#[tokio::test]
async fn clmm_routes_and_the_lookup_tables() {
    let v: Value = serde_json::from_str(&std::fs::read_to_string(format!("{}/testdata/builder/exec-alts-20261006.json", env!("CARGO_MANIFEST_DIR"))).unwrap()).unwrap();
    let mut default: Vec<(Pk, Vec<Pk>)> = v["tables"].as_object().unwrap().iter().map(|(t, a)| (pk(t), a.as_array().unwrap().iter().map(|x| pk(x.as_str().unwrap())).collect())).collect();
    default.sort();
    let cases = clmm_cases();
    let built: Vec<ClmmBuilt> = cases.iter().filter(|c| !c.profit_fail).map(clmm_built).collect();
    let payer = wallet_key().verifying_key().to_bytes();
    let tip_acct = tip_accounts()[0];
    let cfg = test_cfg(&std::env::temp_dir(), "");
    let mk = |alts: Vec<(Pk, Vec<Pk>)>| Exec::assemble(&cfg, Rpc::race(vec![]), None, Rec::off(), crossbeam_channel::unbounded().0, vec![], alts, Some(clmm_pump()),
        [*WSOL].into_iter().collect(), Mode::Shadow, None).unwrap();
    let own = ([0xa4u8; 32], clmm_alt(&mk(vec![]), &built, payer, tip_acct));
    let mut with_own = default.clone();
    with_own.push(own);
    let mut rows = Vec::new();
    for (label, tables) in [("none", vec![]), ("default", default.clone()), ("default+own", with_own)] {
        let x = mk(tables);
        for (c, b) in cases.iter().filter(|c| !c.profit_fail).zip(&built) {
            let r = x.build(&b.r, b.min_profit, BH, Some((tip_acct, b.tip)), &AltSource::none(), 0);
            // an oversized build says its size: "oversized(N bytes, M locks...)"
            let (fits, bytes) = match &r {
                Ok(bx) => (bx.fits(), build::tx_bytes(&bx.msg)),
                Err(e) if e.starts_with("oversized(") => (false, e["oversized(".len()..].split(' ').next().and_then(|n| n.parse().ok()).unwrap_or(0)),
                Err(e) => panic!("{}: {e}", c.name),
            };
            rows.push((label, c.name, fits, bytes));
        }
    }
    for r in &rows { eprintln!("lookup tables {:<12} {:<40} fits {:<5} {} bytes", r.0, r.1, r.2, r.3); }
    let fits = |label: &str| rows.iter().filter(|r| r.0 == label && r.2).count();
    assert_eq!(fits("default+own"), built.len(), "with a table of their own accounts every route fits");
    // without any table the two PumpSwap <-> Whirlpool routes are oversized (1,382 and 1,448 bytes) and Whirlpool <->
    // Raydium CLMM fits by one byte (1,231); the default tables hold the venues' programs and common accounts: all fit
    assert_eq!((fits("none"), fits("default")), (3, built.len()), "{rows:?}");
}

// ------------------------------------------------------------------------------------------------ WP-07

fn money(liquid: u64, wsol: u64, rent: u64) -> crate::ledger::MoneyView {
    crate::ledger::MoneyView { equity_known: true, stale: false, liquid: Some(liquid), wsol: Some(wsol), native: Some(liquid - wsol), rent_recoverable: Some(rent) }
}

/// WP-07, the WP-05 hand-off (provisional money): a landing the expiry check found first asks the chain-fetch service
/// for its record (`note_landed`) and is counted provisionally (the base fee, an unknown round trip); its record settles
/// it (the fee and round trip from the chain, the ledger's line in the amend), and the ledger's view of the executor
/// (`landings`) follows. A refused bundle keeps its final for the reconciliation. And a run with a ledger sends nothing
/// before the start equity is known (`equity_unknown`)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn wp07_provisional_money_is_settled_by_its_record() {
    let mut r = rig("wp07-prov", Mode::Live, "").await;
    let t = now_ns();
    r.x.require_equity(true);
    assert_eq!(r.decide(route(10, damm(11, MINT), 50_000, 1), 100, t).reason, "equity_unknown", "no balance snapshot yet");
    assert_eq!(r.n("reject_equity_unknown"), 1);
    // review WP-07 #3: a stale money view sends nothing either
    r.x.set_money(crate::ledger::MoneyView { stale: true, ..money(414_500_000, 191_500_000, 4_078_560) });
    assert_eq!(r.decide(route(10, damm(11, MINT), 50_000, 1), 100, t).reason, "equity_stale");
    assert_eq!(r.n("reject_equity_stale"), 1);
    r.x.set_money(money(414_500_000, 191_500_000, 4_078_560));
    assert_eq!(r.decide(route(10, damm(11, MINT), 50_000, 1), 100, t).reason, "sent");
    let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
    let sig = fired.copies[0].sig.clone().unwrap();
    r.x.on_settled(Settled::Fired { attempt, fired }, now_ns(), &|_| None);
    // the expiry check finds it landed before its wallet record: provisional, and its record is asked for
    let (shared, notes) = crate::chainfetch::Shared::new(crate::rpc::Registry::global());
    let hit = SigStatus { slot: 102, err: None, confirmation: Some("confirmed".into()) };
    crate::chainfetch::with_test_service(shared, || r.x.on_settled(Settled::Statuses { why: "expiry", at: vec![(attempt, "expiry")], result: Ok(vec![Some(hit)]), t_ns: t }, t, &|_| None));
    match notes.try_recv() {
        Ok(crate::chainfetch::Note::Landed { sig: s, slot, attempt: a, .. }) => assert_eq!((bs58::encode(s).into_string(), slot, a), (sig.clone(), Some(102), Some(attempt))),
        other => panic!("the record is asked for: {:?}", other.map(|_| ())),
    }
    let l = r.x.landings();
    assert_eq!((l[0].landed, l[0].wallet_seen, l[0].src, l[0].fee, l[0].rt_unknown, l[0].fin), (true, false, "statuses", 5_000, true, "landed_ok"));
    assert!(l[0].provisional());
    // its record settles it: the fee and round trip as the chain says, the ledger's line in the amend
    let events = json!([{ "kind": "out", "leg": 0, "amount": 77 }, { "kind": "out", "leg": 1, "amount": SIZE + 49_000 }]);
    assert_eq!(r.x.round_trip_of(Some(attempt), &sig, &events), Some(49_000), "the ledger's check of a win");
    r.x.on_wallet_tx(&json!({ "sig": sig, "attempt": attempt, "slot": 102, "idx": 7, "ok": true, "err": null, "fee": 6_000, "cu_consumed": 90_000, "prog_events": events,
        "ledger_line": { "trade_net": 11_501, "fee": 6_000, "tip": 31_499 } }), now_ns(), &|_| None);
    let l = r.x.landings();
    assert_eq!((l[0].wallet_seen, l[0].src, l[0].fee, l[0].tip, l[0].round_trip, l[0].rt_unknown), (true, "wallet", 6_000, 31_499, 49_000, false));
    let o = r.lines("outcomes");
    assert_eq!((o[1]["amend"].as_bool(), o[1]["amends"].as_str(), o[1]["ledger"]["trade_net"].as_i64()), (Some(true), Some("statuses"), Some(11_501)));
    assert!(o[0]["ledger"].is_null(), "no record yet at the final line");
    // a failed landing found first by the expiry check: its base fee is provisional failed fees until its record
    assert_eq!(r.decide(route(12, damm(13, MINT), 50_000, 1), 100, t + 1).reason, "sent");
    let Settled::Fired { attempt: a2, fired } = r.settled().await else { panic!("a fire result") };
    r.x.on_settled(Settled::Fired { attempt: a2, fired }, now_ns(), &|_| None);
    let fail = SigStatus { slot: 103, err: Some(json!({ "InstructionError": [2, { "Custom": 1314390018u64 }] })), confirmation: Some("confirmed".into()) };
    r.x.on_settled(Settled::Statuses { why: "expiry", at: vec![(a2, "expiry")], result: Ok(vec![Some(fail)]), t_ns: t }, t, &|_| None);
    assert_eq!(r.x.provisional_failed_fees(), 5_000);
    // a refused bundle: its final stays `not_landed_refused` (the reconciliation confirms it never lands)
    assert_eq!(r.decide(route(14, damm(15, MINT), 50_000, 1), 100, t + 2).reason, "sent");
    let Settled::Fired { attempt: a3, fired: mut f } = r.settled().await else { panic!("a fire result") };
    f.copies[0].ok = false;
    f.copies[0].t_ack = 1;
    f.copies[0].reply = Some("refused: invalid argument".into());
    r.x.on_settled(Settled::Fired { attempt: a3, fired: f }, now_ns(), &|_| None);
    let l = r.x.landings();
    assert_eq!(l.iter().find(|x| x.attempt == a3).map(|x| (x.fin, x.landed)), Some(("not_landed_refused", false)));
}

/// WP-07 (go-live gate): the bankroll caps a trade at `bankroll_share` x the liquid SOL + WSOL − the reserve and at the
/// WSOL, within the size cap; nothing while the ledger has no balances. The rent cap never refuses a create+close (merge
/// of WP-06: it binds held-set additions only). A canary `count` of 0 is no attempt cap
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn wp07_bankroll_rent_cap_and_canary_count() {
    let mut r = rig("wp07-bank", Mode::Live, "[live]\nmax_size_sol = 0.2\nbankroll_share = 0.85\nbankroll_reserve_sol = 0.03\n[supervisor]\nrent_cap_sol = 0.006\n").await;
    assert_eq!((r.x.size_cap(), r.x.bankroll_cap()), (200_000_000, None), "no balances yet: the configured cap (a run with a ledger refuses equity_unknown)");
    r.x.set_money(money(414_500_000, 191_500_000, 0));
    assert_eq!(r.x.size_cap(), 191_500_000, "frz on 2026-10-05: its WSOL (the bankroll allows 0.32 SOL, the canary cap 0.2)");
    r.x.set_money(money(100_000_000, 90_000_000, 0));
    assert_eq!((r.x.size_cap(), r.x.bankroll_cap()), (55_000_000, Some(55_000_000)), "85% of 0.1 SOL − 0.03");
    // review WP-07 #12: the executor itself refuses a route sized above its cap, whoever sized it
    let mut big = route(40, damm(41, MINT), 50_000, 1);
    (big.size, big.back, big.spent) = (60_000_000, 60_050_000, 60_000_000);
    assert_eq!(r.decide(big, 100, now_ns()).reason, "size_cap", "a route above the bankroll's 55M");
    assert_eq!(r.n("reject_size_cap"), 1);
    r.x.set_money(money(30_000_000, 30_000_000, 0));
    assert_eq!(r.x.size_cap(), 0, "the reserve takes it all: the engine refuses bankroll_empty");
    r.x.set_money(money(1_000_000_000, 0, 0));
    assert_eq!(r.x.size_cap(), 0, "no WSOL to spend");
    r.x.set_money(money(1_000_000_000, 900_000_000, 0));
    assert_eq!(r.x.size_cap(), 200_000_000, "the size cap");
    // the rent cap (merge of WP-06 with integ/stage0): a route through a token the wallet holds no account for creates it
    // and closes it in the same transaction, which locks no rent: sent whatever the recoverable rent (the cap binds
    // held-set additions only: the_rent_cap_limits_held_additions_only)
    let mut rt = route(20, damm(21, M2), 50_000, 1);
    rt.buy = damm(20, M2);
    rt.mint = M2;
    r.x.set_money(money(1_000_000_000, 900_000_000, 4_078_560));
    assert_eq!(r.decide(rt, 100, now_ns()).reason, "sent", "4.08M recoverable, a new account's rent would pass 6M: create+close is not capped");
    let l = r.lines("attempts").last().unwrap().clone();
    assert_eq!((l["tx"]["creates_ata"].as_bool(), l["tx"]["closes_ata"].as_bool(), r.n("reject_rent_cap")), (Some(true), Some(true), 0));
    // a canary with count = 0 is not capped by count
    let mut c = rig("wp07-canary", Mode::Canary, "[canary]\nenabled = true\ncount = 0\nevery_ms = 1\nsize_sol = 0.2\n").await;
    let t = now_ns();
    for k in 0..3u64 {
        let n = 30 + 2 * k as u8;
        assert_eq!(c.decide(route(n, damm(n + 1, MINT), 50_000, k), 100, t + k * 10_000_000).reason, "sent", "{k}");
    }
}

/// PLAN WP-07 acceptance ("drain logic under a virtual clock"): at a stop the engine keeps handling what settles the
/// open attempts (their wallet records, the block engine's results, the expiry checks) and leaves out what would price
/// (account updates), until none is open or the drain's time is up on the clock it is given
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn wp07_the_stop_drain_on_a_virtual_clock() {
    let mut r = rig("wp07-drain", Mode::Live, "[send_policy]\nbig_band_max_per_sec = 1000\n").await;
    let (mut e, a, _b) = amm_engine();
    e.set_rec(r.rec.clone());
    let mut x = std::mem::replace(&mut r.x, idle_exec());
    x.set_gate(SendGate::new());
    x.set_health(e.health_flags());
    e.exec = Some(x);
    let mut t = now_ns();
    amm_start(&mut e, &mut t);
    amm_move(&mut e, &a, 0, 1_030, &mut t);
    let sent = e.exec.as_ref().unwrap().landings();
    assert_eq!((sent.len(), sent[0].fin), (1, "open"), "one attempt in flight at the stop");
    // the virtual clock: 5 s pass at every reading
    let vt = std::cell::Cell::new(t);
    let clock = || { vt.set(vt.get() + 5 * S); vt.get() };
    let open_none = |e: &crate::engine::Engine| e.exec.as_ref().is_none_or(|x| x.open_attempts().is_empty());
    let mut status = |_: &str| {};
    let (tx, rx) = crossbeam_channel::unbounded::<Event>();
    // nothing comes: the drain gives up when its 60 s are up on the virtual clock (a few real milliseconds)
    let t_real = std::time::Instant::now();
    assert!(!e.drain_on(&rx, vt.get() + 60 * S, &open_none, &mut status, &clock));
    assert!(vt.get() >= t + 60 * S && t_real.elapsed() < std::time::Duration::from_secs(5), "{:?}", t_real.elapsed());
    assert_eq!(e.exec.as_ref().unwrap().open_attempts().len(), 1);
    // an account update (left out: nothing is priced) and then the attempt's wallet record: it settles, the drain ends
    let before = e.store.get(&a.vault1).map(|x| x.data.to_vec());
    tx.send(Event::Account { slot: 101, pubkey: a.vault1, owner: [3; 32], lamports: 1, data: amm_vault(2_000 * 1_000_000_000), t: vt.get(), txn: Some([77; 64]),
        write_version: vt.get(), is_startup: false, src: 0, aseq: 0, bank_id: None }).unwrap();
    tx.send(Event::Input { kind: InputKind::WalletTx, data: Arc::new(json!({ "sig": sent[0].sig, "slot": 101, "idx": 3, "ok": true, "err": null, "fee": 5_000,
        "attempt": sent[0].attempt, "found_by": ["account_update"], "prog_events": null })) }).unwrap();
    assert!(e.drain_on(&rx, vt.get() + 60 * S, &open_none, &mut status, &clock));
    assert_eq!(e.store.get(&a.vault1).map(|x| x.data.to_vec()), before, "the account update was left out");
    let o = r.lines("outcomes");
    assert_eq!((o.len(), o[0]["final"].as_str(), o[0]["final_src"].as_str()), (1, Some("landed_ok"), Some("wallet")), "{o:?}");
    assert!(e.exec.as_mut().unwrap().settle_at_stop().is_empty(), "nothing left unsettled");
}

/// Review WP-07 #6, in the order the real system produces: a bundle the block engine refused (final `not_landed_refused`)
/// whose wallet record comes all the same, to the ledger first and then to the executor (`Engine::step`'s order). The
/// executor keeps its first final (`refused`), says so in the amend line (`refused_then_landed`, `first_final`) and hands
/// it over once (`take_refused_landed`); the reconciliation flags it. Through the engine, such a record puts the gate in
/// shadow at once (`reconcile_miss`) with a Critical notice
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn wp07_a_refused_bundle_that_lands_is_flagged() {
    let mut r = rig("wp07-refused", Mode::Live, "").await;
    let t = now_ns();
    r.x.set_money(money(414_500_000, 191_500_000, 4_078_560));
    assert_eq!(r.decide(route(14, damm(15, MINT), 50_000, 14), 100, t).reason, "sent");
    let Settled::Fired { attempt: a3, fired: mut f } = r.settled().await else { panic!("a fire result") };
    let sig = f.copies[0].sig.clone().unwrap();
    f.copies[0].ok = false;
    f.copies[0].t_ack = 1;
    f.copies[0].reply = Some("refused: invalid argument".into());
    r.x.on_settled(Settled::Fired { attempt: a3, fired: f }, now_ns(), &|_| None);
    assert_eq!(r.x.landings().iter().find(|x| x.attempt == a3).map(|x| (x.fin, x.refused)), Some(("not_landed_refused", true)));
    // it lands anyway: its record to the ledger, then to the executor
    let mut ledger = crate::ledger::Ledger::new(Default::default(), Default::default(), r.x.payer(), Rec::off(), "rv");
    let raw = crate::ledger::Raw { kind: "route".into(), ok: true, payer: true, wallet_sol: -36_499, wsol: 49_000, fee: 5_000, tip: 31_499, ..Default::default() };
    let events = json!([{ "kind": "out", "leg": 0, "amount": 77 }, { "kind": "out", "leg": 1, "amount": SIZE + 49_000 }]);
    let d = json!({ "sig": sig, "slot": 120, "idx": 3, "ok": true, "err": null, "fee": 5_000, "attempt": a3, "prog_events": events, "ledger": raw.json() });
    ledger.on_wallet_tx(&d, now_ns(), &crate::ledger::no_prices, None);
    r.x.on_wallet_tx(&d, now_ns(), &|_| None);
    assert_eq!(r.x.take_refused_landed().len(), 1);
    assert!(r.x.take_refused_landed().is_empty(), "handed over once");
    assert_eq!(r.x.landings().iter().find(|x| x.attempt == a3).map(|x| (x.fin, x.refused, x.landed)), Some(("landed_ok", true, true)), "the first final is kept");
    let (line, ok) = crate::ledger::exec_recon(&ledger.entries, &r.x.landings(), &Default::default(), 10_000);
    assert!(!ok && line["refused_landed"][0]["sig"] == json!(sig), "a refused bundle that landed is flagged: {line}");
    let o = r.lines("outcomes");
    let amend = o.iter().find(|l| l["amend"] == json!(true)).unwrap();
    assert_eq!((amend["refused_then_landed"].as_bool(), amend["first_final"].as_str()), (Some(true), Some("not_landed_refused")));
    assert_eq!(r.n("refused_then_landed"), 1);
    // through the engine: another refused bundle whose record comes as INPUT 7 puts the gate in shadow at once
    assert_eq!(r.decide(route(20, damm(21, MINT), 50_000, 20), 100, t + 1).reason, "sent");
    let Settled::Fired { attempt: a4, fired: mut f } = r.settled().await else { panic!("a fire result") };
    let sig4 = f.copies[0].sig.clone().unwrap();
    f.copies[0].ok = false;
    f.copies[0].t_ack = 1;
    f.copies[0].reply = Some("refused".into());
    r.x.on_settled(Settled::Fired { attempt: a4, fired: f }, now_ns(), &|_| None);
    let (mut e, _a, _b) = amm_engine();
    e.set_rec(r.rec.clone());
    let sess = crate::control::Session::new();
    let mut x = std::mem::replace(&mut r.x, idle_exec());
    x.set_gate(sess.gate.clone());
    let payer = x.payer();
    e.exec = Some(x);
    let mut l = crate::ledger::Ledger::new(Default::default(), Default::default(), payer, r.rec.clone(), "rv-engine");
    l.bind(sess.gate.clone(), sess.stopper.clone());
    e.ledger = Some(l);
    let d4 = json!({ "sig": sig4, "slot": 130, "idx": 1, "ok": false, "err": { "InstructionError": [2, { "Custom": 6001 }] }, "fee": 5_000, "attempt": a4,
        "ledger": crate::ledger::Raw { kind: "route".into(), ok: false, payer: true, wallet_sol: -5_000, fee: 5_000, ..Default::default() }.json() });
    let mut status = |_: &str| {};
    let (_, notes) = crate::notify::capture(|| e.step(Event::Input { kind: InputKind::WalletTx, data: Arc::new(d4) }, now_ns(), &mut status));
    assert_eq!((sess.gate.reason().as_str(), sess.gate.sticky()), ("reconcile_miss", true), "at once, for the rest of the segment");
    assert!(notes.iter().any(|n| n.kind == "recon_miss" && n.level == crate::notify::Level::Critical), "{notes:?}");
}

/// Review WP-07 #2 (mutant M1), through the run loop (`Engine::run`, as `arbx run` drives it): a live executor with a
/// ledger (`Ledger::for_run`, as `run()` assembles it, the config's 5,000,000 allotment) sends nothing before the first
/// balance snapshot (`equity_unknown`: the floor cannot be armed yet); after it, a route is sent; a wallet record whose
/// loss passes the floor puts the gate in shadow, asks the run to stop (`equity_floor`, exit 20) and ends the loop
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn wp07_the_run_loop_arms_the_equity_stops() {
    let extra = "[send_policy]\nbig_band_max_per_sec = 1000\n[supervisor]\ntest_budget_lamports = 5000000\n";
    let mut r = rig("wp07-arm", Mode::Live, extra).await;
    let sess = crate::control::Session::new();
    let (mut e, a, b) = amm_engine();
    e.set_rec(r.rec.clone());
    let payer = r.x.payer();
    let mut x = std::mem::replace(&mut r.x, idle_exec());
    x.set_gate(sess.gate.clone());
    e.exec = Some(x);
    e.gate = Some(sess.gate.clone());
    let cfg = test_cfg(&r.dir, extra);
    e.ledger = Some(crate::ledger::Ledger::for_run(&cfg, payer, r.rec.clone(), "wp07-arm", true, sess.gate.clone(), sess.stopper.clone(), Default::default(), None, None));
    let (tx, rx) = crossbeam_channel::unbounded::<Event>();
    let (done_tx, done_rx) = crossbeam_channel::bounded::<()>(1);
    let feeder = std::thread::spawn(move || {
        let pause = || std::thread::sleep(std::time::Duration::from_millis(40));
        let t = now_ns();
        tx.send(Event::Slot { slot: 100, status: 0, t, parent: Some(99), dead_error: None, bank_id: None }).unwrap();
        tx.send(Event::Input { kind: InputKind::BlockhashHead, data: Arc::new(json!({ "hash": b58(&BH), "slot": 99, "height": 89, "src": "slotidx",
            "commitment": "confirmed", "t_ns": t })) }).unwrap();
        tx.send(Event::Input { kind: InputKind::LeaderWindow, data: Arc::new(window_json()) }).unwrap();
        pause();
        let mv = |m: &PoolMeta, n: u8, sol: u64| {
            for (k, data) in [(m.vault1, amm_vault(sol * 1_000_000_000)), (m.vault0, amm_vault(1_000_000_000_000_000 - n as u64))] {
                let t = now_ns();
                tx.send(Event::Account { slot: 100, pubkey: k, owner: [3; 32], lamports: 1, data, t, txn: Some([n + 50; 64]), write_version: t, is_startup: false,
                    src: 0, aseq: 0, bank_id: None }).unwrap();
            }
        };
        // a decision before any balance snapshot, then the start snapshot, then a decision with it
        mv(&a, 0, 1_030);
        pause();
        tx.send(Event::Input { kind: InputKind::Snapshot, data: Arc::new(crate::ledger::test_snapshot_answer(&payer, 90, 300_000_000, 200_000_000, 0, "start")) }).unwrap();
        pause();
        mv(&b, 1, 1_060);
        pause();
        // a route landing of ours that lost 6,000,000: past the floor (start less 5,000,000)
        let raw = crate::ledger::Raw { kind: "route".into(), ok: false, payer: true, wallet_sol: -6_000_000, fee: 6_000_000, ..Default::default() };
        tx.send(Event::Input { kind: InputKind::WalletTx, data: Arc::new(json!({ "sig": bs58::encode([9u8; 64]).into_string(), "slot": 101, "idx": 1, "ok": false,
            "err": { "InstructionError": [2, { "Custom": 6001 }] }, "fee": 6_000_000, "attempt": null, "ledger": raw.json() })) }).unwrap();
        let _ = done_rx.recv_timeout(std::time::Duration::from_secs(10));
    });
    let stop = sess.stopper.flag();
    let end = e.run(&rx, &stop, now_ns() + 8_000_000_000, |_| {});
    let _ = done_tx.send(());
    feeder.join().unwrap();
    assert_eq!(end, crate::engine::RunEnd::Stopped, "the floor stopped the loop");
    assert_eq!(sess.stopper.info().map(|i| (i.reason, i.reason.exit_code())), Some((crate::control::StopReason::EquityFloor, 20)));
    assert_eq!(sess.gate.mode(), GateMode::Stopped);
    let d: Vec<Value> = r.lines("decisions").into_iter().filter(|l| l["opp"].is_u64()).collect();
    assert_eq!(d.iter().map(|l| l["reason"].as_str().unwrap_or("").to_string()).collect::<Vec<_>>(), ["equity_unknown", "sent"], "{d:?}");
    assert_eq!(r.got.lock().unwrap().len(), 1, "one bundle left, after the snapshot");
}

// ------------------------------------------------------------------------------------------------ integration (integ/stage0)

/// one live send of the route `n` (its pools of its own) to the fake block engine, settled as fired: (attempt, signature)
async fn integ_send(r: &mut Rig, n: u8, t: u64) -> (u64, String) {
    assert_eq!(r.decide(route(n, damm(n + 1, MINT), 50_000, n as u64), 100, t).reason, "sent");
    let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
    let sig = fired.copies[0].sig.clone().unwrap();
    r.x.on_settled(Settled::Fired { attempt, fired }, now_ns(), &|_| None);
    (attempt, sig)
}

/// a wallet record of our attempt (INPUT 7 as the executor gets it: the route program's events, the ledger's line)
fn integ_record(sig: &str, attempt: u64, slot: u64, ok: bool, fee: u64, events: &Value, ledger_line: Value) -> Value {
    json!({ "sig": sig, "attempt": attempt, "slot": slot, "idx": 7, "ok": ok, "err": if ok { Value::Null } else { json!({ "InstructionError": [2, { "Custom": 6001 }] }) },
        "fee": fee, "cu_consumed": 90_000, "prog_events": events, "ledger_line": ledger_line })
}

/// Integration (WP-05 x WP-07 x WP-20: the settlement hook of docs/reviews/WP-20-exec-hooks.patch, wired at the merge). A
/// landing of ours is told from chain data, through the process's alert functions (captured here). Its wallet record
/// brings the route program's events (the round trip: the last leg's output − the size) and the ledger's line of the same
/// transaction (its fee, its tip, the rent it left locked): the alert says "succeeded" and the net = round trip − tip −
/// fee − rent, a gain only above 0 and never "profitable". One that created an account pays the ledger's exact rent in
/// its net (not the estimate) and reads as a loss; one the expiry check found first is told without its net, then again
/// when its record brings it; a failed landing is told with its fee and the program's error; the failed-fee cap is the
/// budget floor, told once
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn integ_landings_are_told_with_their_chain_net() {
    let mut r = rig("integ-alerts", Mode::Live, "[live]\nmax_failed_fees_lamports = 12000\n").await;
    let t = now_ns();
    let mut all: Vec<crate::alerts::Alert> = Vec::new();
    let events = json!([{ "kind": "out", "leg": 0, "amount": 77 }, { "kind": "out", "leg": 1, "amount": SIZE + 49_000 }]);
    let line = |rent: u64| json!({ "trade_gross": 49_000, "tip": 31_499, "fee": 6_000, "rent_nonrecoverable": 0, "rent_locked": rent, "rent_reclaimed": 0,
        "trade_net": 11_501, "equity_delta": 11_501, "liquid_delta": 11_501 - rent as i64 });
    let fail_line = json!({ "trade_gross": 0, "tip": 0, "fee": 5_000, "rent_nonrecoverable": 0, "rent_locked": 0, "rent_reclaimed": 0, "trade_net": -5_000,
        "equity_delta": -5_000, "liquid_delta": -5_000 });
    // a win, settled by its wallet record (the ledger's line beside the route program's events)
    let (a1, s1) = integ_send(&mut r, 10, t).await;
    let (_, got) = crate::alerts::capture(|| r.x.on_wallet_tx(&integ_record(&s1, a1, 102, true, 6_000, &events, line(0)), now_ns(), &|_| None));
    assert_eq!(got.len(), 1, "{got:?}");
    assert_eq!((got[0].kind, got[0].level, got[0].icon, got[0].key.as_str()), ("win", crate::alerts::Level::Info, "💰", format!("win:{s1}").as_str()));
    assert_eq!(got[0].title, "succeeded · net +0.000011501 SOL", "49,000 − 31,499 − 6,000, every part from the chain");
    assert!(got[0].body.contains("DammV2&gt;DammV2") && got[0].body.contains("size 0.0500 · gross +0.000049 · tip 0.000031499 · fee 0.000006"), "{}", got[0].body);
    assert!(got[0].body.contains("slot 102"), "{}", got[0].body);
    all.extend(got);
    // a win whose transaction created a token account: the ledger's rent (2,039,280) is in the net, which is below 0
    let (a2, s2) = integ_send(&mut r, 12, t + 1).await;
    let (_, got) = crate::alerts::capture(|| r.x.on_wallet_tx(&integ_record(&s2, a2, 103, true, 6_000, &events, line(2_039_280)), now_ns(), &|_| None));
    assert_eq!((got.len(), got[0].level), (1, crate::alerts::Level::Warning));
    assert_eq!(got[0].title, "succeeded but lost: net -0.002027779 SOL after fee, tip, rent", "11,501 − 2,039,280");
    assert!(got[0].body.contains("rent 0.00203928"), "{}", got[0].body);
    all.extend(got);
    // found by the expiry check first: told without its net; its record brings the net, and it is told again
    let (a3, s3) = integ_send(&mut r, 14, t + 2).await;
    let hit = SigStatus { slot: 104, err: None, confirmation: Some("confirmed".into()) };
    let (_, got) = crate::alerts::capture(|| r.x.on_settled(Settled::Statuses { why: "expiry", at: vec![(a3, "expiry")], result: Ok(vec![Some(hit)]), t_ns: t }, t, &|_| None));
    assert_eq!(got.iter().map(|a| a.title.as_str()).collect::<Vec<_>>(), ["succeeded · net not known yet"]);
    all.extend(got);
    let (_, got) = crate::alerts::capture(|| r.x.on_wallet_tx(&integ_record(&s3, a3, 104, true, 6_000, &events, line(0)), now_ns(), &|_| None));
    assert_eq!(got.iter().map(|a| a.title.as_str()).collect::<Vec<_>>(), ["succeeded · net +0.000011501 SOL"], "the amend tells the net");
    all.extend(got);
    // a failed landing: its fee lost and the program's error
    let (a4, s4) = integ_send(&mut r, 16, t + 3).await;
    let (_, got) = crate::alerts::capture(|| r.x.on_wallet_tx(&integ_record(&s4, a4, 105, false, 5_000, &Value::Null, fail_line.clone()), now_ns(), &|_| None));
    assert_eq!((got.len(), got[0].kind, got[0].level), (1, "failed_landing", crate::alerts::Level::Error));
    assert_eq!(got[0].title, "failed landing · fee 0.000005 SOL lost");
    assert!(got[0].body.contains("custom 0x1771"), "{}", got[0].body);
    all.extend(got);
    // the failed-fee cap (12,000): 5,000 spent, and the next send's 5,000 fit; after a second failure there is no room:
    // the budget floor, told once (the sender stays stopped)
    let (a5, s5) = integ_send(&mut r, 18, t + 4).await;
    let (_, got) = crate::alerts::capture(|| r.x.on_wallet_tx(&integ_record(&s5, a5, 106, false, 5_000, &Value::Null, fail_line.clone()), now_ns(), &|_| None));
    all.extend(got);
    let (d, got) = crate::alerts::capture(|| r.decide(route(20, damm(21, MINT), 50_000, 20), 100, t + 5));
    assert_eq!(d.reason, "fee_cap");
    assert_eq!(got.iter().map(|a| (a.kind, a.level)).collect::<Vec<_>>(), [("budget_floor", crate::alerts::Level::Critical)]);
    assert_eq!(got[0].title, "BUDGET FLOOR (failed_fee_cap): sending stops");
    all.extend(got);
    let (d, got) = crate::alerts::capture(|| r.decide(route(22, damm(23, MINT), 50_000, 22), 100, t + 6));
    assert!(d.reason == "sender_stopped" && got.is_empty(), "once: {} {got:?}", d.reason);
    // Stage-1 plan review F12: no alert ever calls a landing "profitable"
    assert_eq!(all.len(), 7);
    assert!(all.iter().all(|a| !a.title.contains("profitable") && !a.body.contains("profitable")), "{all:?}");
}

/// Integration (WP-20's daily summary x WP-07's money x the merged engine's status line): the win ratio is wins ÷ bundles
/// sent, with both numbers and the ledger's net after fees, tips and rent. The real engine settles two live sends from
/// their wallet records (the ledger first, as `Engine::step` does: a win of 11,501 net, a failed landing of 5,000) and
/// writes its status line (status 2.2: the executor's `exec`, the ledger's `money`, `rpc_budget`, `alerts`); the daily
/// totals read that line: 1 win / 2 sent, net +6,501 from the ledger
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn integ_the_daily_ratio_reads_the_merged_status_line() {
    let mut r = rig("integ-daily", Mode::Live, "").await;
    let t = now_ns();
    let (a1, s1) = integ_send(&mut r, 10, t).await;
    let (a2, s2) = integ_send(&mut r, 12, t + 1).await;
    let (mut e, _a, _b) = amm_engine();
    e.set_rec(r.rec.clone());
    let mut x = std::mem::replace(&mut r.x, idle_exec());
    x.set_gate(SendGate::new());
    let payer = x.payer();
    e.exec = Some(x);
    e.ledger = Some(crate::ledger::Ledger::new(Default::default(), Default::default(), payer, Rec::off(), "integ-daily"));
    let mut status = |_: &str| {};
    let step = |e: &mut crate::engine::Engine, kind: InputKind, d: Value, status: &mut dyn FnMut(&str)| e.step(Event::Input { kind, data: Arc::new(d) }, now_ns(), status);
    // the start: a balance snapshot (INPUT 13) below the landings' slots
    step(&mut e, InputKind::Snapshot, crate::ledger::test_snapshot_answer(&payer, 90, 222_956_693, 191_524_924, 0, "start"), &mut status);
    let events = json!([{ "kind": "out", "leg": 0, "amount": 77 }, { "kind": "out", "leg": 1, "amount": SIZE + 49_000 }]);
    let win = crate::ledger::Raw { kind: "route".into(), ok: true, payer: true, wallet_sol: -37_499, wsol: 49_000, fee: 6_000, tip: 31_499, ..Default::default() };
    let lost = crate::ledger::Raw { kind: "route".into(), ok: false, payer: true, wallet_sol: -5_000, fee: 5_000, ..Default::default() };
    let rec_of = |sig: &str, a: u64, slot: u64, ok: bool, fee: u64, ev: Value, raw: &crate::ledger::Raw| json!({ "sig": sig, "attempt": a, "slot": slot, "idx": 3, "ok": ok,
        "err": if ok { Value::Null } else { json!({ "InstructionError": [2, { "Custom": 6001 }] }) }, "fee": fee, "prog_events": ev, "ledger": raw.json() });
    let ((), got) = crate::alerts::capture(|| crate::notify::capture(|| {
        step(&mut e, InputKind::WalletTx, rec_of(&s1, a1, 102, true, 6_000, events.clone(), &win), &mut status);
        step(&mut e, InputKind::WalletTx, rec_of(&s2, a2, 103, false, 5_000, Value::Null, &lost), &mut status);
    }).0);
    assert_eq!(got.iter().map(|a| a.kind).collect::<Vec<_>>(), ["win", "failed_landing"], "{got:?}");
    assert_eq!(got[0].title, "succeeded · net +0.000011501 SOL", "the fee and tip of the ledger's line the engine added to the record");
    e.write_final_status(0, "deadline");
    r.rec.sync();
    let line = crate::alerts::summary::last_status(&r.dir.join("status.jsonl")).expect("the engine's status line");
    assert_eq!(line["exec"]["sent_total"].as_u64(), Some(2));
    assert_eq!(line["money"]["src"].as_str(), Some("ledger"));
    assert!(line.get("rpc_budget").is_some() && line.get("alerts").is_some(), "status 2.2: FT-000's rpc_budget and WP-20's alerts beside WP-07's money");
    let s = crate::alerts::summary::Snapshot::of(&line);
    assert_eq!((s.sends, s.wins, s.net_lamports, s.net_src), (Some(2), Some(1), Some(11_501 - 5_000), Some("ledger")), "{line}");
    // the day's totals over a runs directory holding that segment, and the daily summary's line
    let runs = test_dir("integ-daily-runs");
    let seg = runs.join("integ-p1");
    std::fs::create_dir_all(&seg).unwrap();
    std::fs::copy(r.dir.join("status.jsonl"), seg.join("status.jsonl")).unwrap();
    let day = now_ns() / crate::alerts::summary::DAY_NS * crate::alerts::summary::DAY_NS;
    let tot = crate::alerts::summary::day_totals(&runs, day);
    assert_eq!((tot.sends, tot.wins, tot.net_lamports, tot.net_src), (2, 1, 6_501, Some("ledger")));
    let a = crate::alerts::daily_alert(&tot);
    assert!(a.body.contains("win ratio 50.0% (1 win / 2 sent) · net +0.000006501 SOL (ledger)"), "{}", a.body);
    let _ = std::fs::remove_dir_all(&runs);
}

// ------------------------------------------------------------------------------------------------ after the merge

/// The two lanes name the same accounts (merge fixes, after WP-06 met integ/stage0): WP-06's permanent mints are WSOL and
/// the USDC and USDT that WP-07's ledger snapshots (`[ledger] extra_mints`, the default and the frz canary's), so the dry
/// run's `route_payer_accounts` watches the payer's real USDC and USDT accounts (WP-06 had a mistyped USDT key); and the
/// builder's PumpSwap user volume accumulator (`build::pump_uva`, `uva_missing`) is the one the ledger reads as
/// non-recoverable (`ledger::accumulator_of`)
#[tokio::test]
async fn the_permanent_mints_are_the_ledgers() {
    let mints = |c: &Config| -> Vec<Pk> { c.ledger.extra_mints.iter().map(|m| pk(m)).collect() };
    let frz = Config::load(&std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("deploy/arbx-canary-frz.toml")).unwrap();
    let cfg = test_cfg(&std::env::temp_dir(), "");
    assert_eq!(PERMANENT_MINTS[0], *WSOL);
    assert_eq!(PERMANENT_MINTS[1..].to_vec(), mints(&cfg), "the ledger's default extra_mints");
    assert_eq!(PERMANENT_MINTS[1..].to_vec(), mints(&frz), "the frz canary's");
    assert_eq!(b58(&PERMANENT_MINTS[2]), "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", "USDT");
    let x = idle_exec();
    assert_eq!(x.payer_tokens, PERMANENT_MINTS[1..].iter().map(|m| build::ata_of(&x.payer, m, &crate::pda::TOKEN_PROGRAM)).collect::<Vec<_>>());
    let frz_wallet = pk(&frz.wallet);
    assert_eq!(build::pump_uva(&frz_wallet), crate::ledger::accumulator_of(&frz_wallet));
}

// ------------------------------------------------------------------------------------------------ FT-006: BAM

fn bam_on(min_tip_per_cu: f64, below_floor: &str) -> crate::config::BamPolicyCfg {
    crate::config::BamPolicyCfg { enabled: true, min_tip_per_cu, max_share: 0.9, below_floor: below_floor.into() }
}

/// FT-006 (`bam_bid`, the routing of a bid by leader kind): the band's tip is raised toward `min_tip_per_cu` × the CU
/// limit; never above `max_share` of the edge, the `[tips]` cap or the decision's bar room; never below the band's tip
#[test]
fn bam_bid_raises_toward_the_floor_within_its_bounds() {
    let p = bam_on(0.05, "send");
    let bid = |band: u64, edge: i64, cu: u64, cap: u64, bar: i64| bam_bid(&p, band, edge, cu, cap, bar);
    // 100,000 CU: the floor is 5,000 lamports
    let b = bid(7_000, 10_000, 100_000, 100_000, 9_000);
    assert_eq!((b.lamports, b.floor, b.reached()), (7_000, 5_000, true), "the band's tip is over the floor: unchanged");
    let b = bid(4_200, 6_000, 100_000, 100_000, 5_000);
    assert_eq!((b.lamports, b.room, b.reached()), (5_000, 5_000, true), "raised to the floor (0.9 x 6,000 = 5,400 room; the bar allows 5,000)");
    let b = bid(3_500, 5_000, 100_000, 100_000, 10_000);
    assert_eq!((b.lamports, b.room, b.reached()), (4_500, 4_500, false), "out of reach: 0.9 of the edge");
    assert_eq!(bid(3_500, 5_000, 100_000, 100_000, 4_000).lamports, 4_000, "the decision's bar first");
    assert_eq!(bid(4_200, 6_000, 100_000, 4_800, 5_000).lamports, 4_800, "the [tips] cap");
    assert_eq!(bid(6_000, 6_000, 100_000, 100_000, 4_000).lamports, 6_000, "never below the band's tip");
    assert_eq!(bid(1_000, -5, 100_000, 100_000, -5).lamports, 1_000, "no edge, no raise");
    assert_eq!(bid(4_200, 6_000, 101_001, 100_000, 6_000).floor, 5_051, "rounded up");
    assert_eq!(bam_bid(&bam_on(0.0, "send"), 4_200, 6_000, 100_000, 100_000, 6_000).lamports, 4_200, "a floor of 0: the band's tip");
}

/// FT-006: a BAM-led target slot's bundle bids its floor through the in-memory block engine (the signed tip, the signed
/// min_profit over it, the decision's net), records the bid (attempts `tip.policy` `bam_floor`, `tip.bam`) and the copy's
/// endpoint and leader kind (attempts `copies[0]`, copies.jsonl 1.3); a Jito-led slot's bundle keeps the band's tip
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_bam_led_slot_bids_its_floor() {
    let mut r = rig("bam-floor", Mode::Live, "[send_policy.bam]\nenabled = true\nmin_tip_per_cu = 0.05\nmax_share = 0.9\n").await;
    // 12,000 expected, edge 7,000: the band's tip 4,900; the CU limit 100,000 (the wallet holds MINT: no ATA) -> floor 5,000
    let d = r.decide(route(1, damm(2, MINT), 12_000, 7), 101, now_ns());
    assert_eq!((d.reason.as_str(), d.sent, d.ev), ("sent", Some(true), Some(2_000)), "net: 12,000 - the 5,000 bid - the base fee: {d:?}");
    let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
    let raw = r.got.lock().unwrap()[0].0.clone();
    let (tx, _) = crate::tx::parse_wire(&raw).unwrap();
    assert_eq!(send::tip_paid(&tx, &tip_accounts()), 5_000, "the floor, 0.05 x 100,000 CU, reached the block engine");
    let all = tx.resolve(|t| r.x.alt_lists.get(t).cloned()).unwrap();
    assert_eq!(route_of(&tx, &all, &r.x.program).unwrap().min_profit, 10_001, "the signed min_profit covers the raised tip + the base fee + 1");
    let tip = Some((tx.keys[tx.ixs.last().unwrap().accounts[1] as usize], 5_000));
    for c in verify_bundle(&raw, &live_want(&r.x, tip, 10_001)) { assert_eq!(c["ok"], json!(true), "{c}"); }
    assert_eq!((fired.copies[0].leader_kind, fired.copies[0].endpoint.as_deref()), (Some("bam"), Some("127.0.0.1")));
    r.x.on_settled(Settled::Fired { attempt, fired }, now_ns(), &|_| None);
    // a Jito-led slot (target 98): the band's tip, nothing raised
    let d = r.decide(route(3, damm(4, MINT), 12_000, 8), 97, now_ns());
    assert_eq!((d.reason.as_str(), d.ev), ("sent", Some(2_100)), "{d:?}");
    let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
    let (tx, _) = crate::tx::parse_wire(&r.got.lock().unwrap()[1].0).unwrap();
    assert_eq!(send::tip_paid(&tx, &tip_accounts()), 4_900, "70% of the 7,000 edge");
    r.x.on_settled(Settled::Fired { attempt, fired }, now_ns(), &|_| None);
    let a = r.lines("attempts");
    assert_eq!(a.len(), 2);
    let (b, j) = (&a[0], &a[1]);
    assert_eq!((b["leader"]["kind"].as_str(), b["tip"]["lamports"].as_u64(), b["tip"]["policy"].as_str(), b["tip"]["share"].as_f64()),
        (Some("bam"), Some(5_000), Some("bam_floor"), Some(0.7)), "the band's share stays recorded");
    assert_eq!((b["tip"]["bam"]["band_tip"].as_u64(), b["tip"]["bam"]["floor"].as_u64(), b["tip"]["bam"]["cu_limit"].as_u64(), b["tip"]["bam"]["room"].as_u64(),
        b["tip"]["bam"]["reached"].as_bool(), b["tip"]["bam"]["raised"].as_bool()), (Some(4_900), Some(5_000), Some(100_000), Some(6_000), Some(true), Some(true)),
        "room: the decision's bar (12,000 - 5,000 - the 1,000 [live] margin) under 0.9 x 7,000");
    assert_eq!((b["tx"]["cu_limit"].as_u64(), b["min_profit_onchain"].as_u64()), (Some(100_000), Some(10_001)), "the floor's CU limit is the build's");
    assert_eq!((b["copies"][0]["leader_kind"].as_str(), b["copies"][0]["endpoint"].as_str()), (Some("bam"), Some("127.0.0.1")));
    assert_eq!((j["leader"]["kind"].as_str(), j["tip"]["lamports"].as_u64(), j["tip"]["policy"].as_str(), j["tip"]["bam"].is_null(), j["copies"][0]["leader_kind"].as_str()),
        (Some("jito"), Some(4_900), Some("share_of_edge"), true, Some("jito")));
    let cp = r.lines("copies");
    assert_eq!(cp.iter().map(|c| (c["leader_kind"].as_str(), c["endpoint"].as_str(), c["tip_lamports"].as_u64())).collect::<Vec<_>>(),
        vec![(Some("bam"), Some("127.0.0.1"), Some(5_000)), (Some("jito"), Some("127.0.0.1"), Some(4_900))]);
}

/// FT-006: a floor out of reach bids what the edge allows (`below_floor = "send"`, up to the decision's bar), or is not
/// sent to the BAM-led slot (`"skip"`: `bam_bid_below_floor`, nothing reaches the block engine); with the policy off a
/// BAM-led slot bids the band's tip, as before
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_bam_floor_out_of_reach_sends_or_skips() {
    // 9,000 expected, edge 4,000: the band's tip 2,800, the floor 5,000; the bar allows 9,000 - 5,000 - 1,000 = 3,000
    let mut r = rig("bam-skip", Mode::Live, "[send_policy.bam]\nenabled = true\nbelow_floor = \"skip\"\n").await;
    let d = r.decide(route(1, damm(2, MINT), 9_000, 7), 101, now_ns());
    assert_eq!((d.verdict, d.reason.as_str(), d.attempt, d.sent), ("reject", "bam_bid_below_floor", None, None), "{d:?}");
    assert_eq!(r.n("reject_bam_bid_below_floor"), 1);
    assert!(r.got.lock().unwrap().is_empty() && r.lines("attempts").is_empty(), "nothing sent, nothing built");
    let d = r.decide(route(3, damm(4, MINT), 9_000, 7), 97, now_ns());
    assert_eq!(d.reason, "sent", "a Jito-led slot is not skipped: {d:?}");
    let mut s = rig("bam-send", Mode::Live, "[send_policy.bam]\nenabled = true\n").await;
    let d = s.decide(route(1, damm(2, MINT), 9_000, 7), 101, now_ns());
    assert_eq!((d.reason.as_str(), d.ev), ("sent", Some(1_000)), "the bar's room, 3,000: {d:?}");
    let _ = s.settled().await;
    let (tx, _) = crate::tx::parse_wire(&s.got.lock().unwrap()[0].0).unwrap();
    assert_eq!(send::tip_paid(&tx, &tip_accounts()), 3_000);
    let a = s.lines("attempts");
    assert_eq!((a[0]["tip"]["bam"]["reached"].as_bool(), a[0]["tip"]["policy"].as_str()), (Some(false), Some("bam_floor")));
    let mut o = rig("bam-off", Mode::Live, "").await;
    let d = o.decide(route(1, damm(2, MINT), 9_000, 7), 101, now_ns());
    assert_eq!((d.reason.as_str(), d.ev), ("sent", Some(1_200)), "off: the band's 2,800: {d:?}");
    let _ = o.settled().await;
    let a = o.lines("attempts");
    assert_eq!((a[0]["leader"]["kind"].as_str(), a[0]["tip"]["lamports"].as_u64(), a[0]["tip"]["bam"].is_null()), (Some("bam"), Some(2_800), true));
}

/// FT-006: the dry run bids for a BAM-led slot as a live run would, and its checks of the signed bytes pass (the signed
/// min_profit covers the raised tip, the base fee and the margin floor)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_dry_run_bids_for_a_bam_slot_as_live() {
    let mut r = rig("bam-dry", Mode::DryRun, "[send_policy.bam]\nenabled = true\n").await;
    let d = r.decide(route(1, damm(2, MINT), 12_000, 7), 101, now_ns());
    assert!(d.would_send, "{d:?}");
    let a = r.lines("attempts");
    assert_eq!((a[0]["tip"]["lamports"].as_u64(), a[0]["dry_run"]["checks_ok"].as_bool(), a[0]["copies"][0]["leader_kind"].as_str(), a[0]["copies"][0]["endpoint"].as_str()),
        (Some(5_000), Some(true), Some("bam"), Some("127.0.0.1")), "the configured block engine, where a send would go: {}", a[0]["dry_run"]["checks"]);
}

// ------------------------------------------------------------------------------------------------ WP-11: the arms

fn x4_arm(share: f64, max_band: u8) -> Option<crate::experiments::Arm<f64>> {
    Some(crate::experiments::Arm { idx: 0, value: share, scope: crate::experiments::Scope { max_band, ..crate::experiments::Scope::ALL } })
}
fn margin_arm(floor: u64) -> Option<crate::experiments::Arm<u64>> { Some(crate::experiments::Arm { idx: 0, value: floor, scope: crate::experiments::Scope::ALL }) }
fn with_arms(mut r: RouteIn, arms: crate::experiments::Arms) -> RouteIn { r.arms = arms; r }

/// WP-11 (property): X4's share and the margin arm's floor applied exactly where intended and never past a bound, over
/// 800 random decisions (edges in every band and on both sides of the floor and the cap, shares 0 to 1, scopes ending at
/// every band, margin floors 1 to 50,000, BAM-led and Jito-led slots with `[send_policy.bam]` on). In the arm's bands the
/// tip is the arm's share of the edge within `[tips]`' floor and cap (`tip.arm` the share, `experiments.x4_share`
/// recorded); out of them it is the band's tip to the lamport (nothing recorded). The BAM floor raises a BAM-led bid on
/// top of the arm's band tip within its room. Every would-send clears the decision's bar (tip + base fee + max(the
/// floor, `[live] margin_lamports`)), its on-chain min_profit is tip + base fee + the floor and never above the expected
/// profit; every other decision is refused `expected_below_min_profit`
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn x4_and_margin_arms_stay_within_every_bound() {
    use crate::experiments::{Arms, ShareArm};
    let mut r = rig("x4-prop", Mode::Shadow, "[send_policy]\nbig_band_max_per_sec = 1000\n[send_policy.bam]\nenabled = true\n").await;
    let mut rng = 0x2545_f491_4f6c_dd1du64;
    let mut next = move || { rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17; rng };
    let model = crate::tip::TipModel::default();
    let mut cases = Vec::new();
    let mut t = now_ns();
    for case in 0..800u64 {
        let expected = match next() % 4 { 0 => 1_000 + next() % 19_000, 1 => 20_000 + next() % 80_000, 2 => 100_000 + next() % 900_000, _ => 1_000_000 + next() % 2_000_000 };
        let share = [0.0, 0.05, 0.1, 0.2, 0.35, 0.7, 1.0][(next() % 7) as usize];
        let max_band = (next() % 5) as u8;
        let mf = [None, Some(1u64), Some(2_000), Some(50_000)][(next() % 4) as usize];
        let bam = next() % 2 == 0;
        let arms = Arms { x4: x4_arm(share, max_band), margin: mf.and_then(margin_arm), ..Default::default() };
        t += 1_000_000_000;
        let d = r.decide(with_arms(route(1, damm(2, MINT), expected, case + 1), arms), if bam { 101 } else { 97 }, t);
        cases.push((d, expected, share, max_band, mf, bam));
    }
    let lines = r.lines("attempts");
    let by_attempt: HashMap<u64, &Value> = lines.iter().map(|a| (a["attempt"].as_u64().unwrap(), a)).collect();
    let p = r.x.pol.bam.clone();
    let (mut sent, mut refused, mut in_scope, mut raised) = (0, 0, 0, 0);
    for (d, expected, share, max_band, mf, bam) in &cases {
        let edge = *expected as i64 - 5_000;
        let band = crate::bands::of_edge(edge);
        let on = band <= *max_band;
        let band_tip = model.tip_arm(edge, false, Some(ShareArm { share: *share, max_band: *max_band })).lamports;
        let plain = model.tip(edge, false).lamports;
        if on { assert_eq!(band_tip, ((edge as f64 * share) as u64).clamp(1_000, 100_000), "the arm's share in its bands: {edge} {share}"); }
        else { assert_eq!(band_tip, plain, "out of the arm's bands: the band's tip to the lamport ({edge}, band {band}, scope 0-{max_band})"); }
        let floor = mf.unwrap_or(1);
        let bar = floor.max(1_000);
        let tip = if *bam { bam_bid(&p, band_tip, edge, 100_000, 100_000, edge - bar as i64).lamports } else { band_tip };
        if (*expected as i64) < (tip + 5_000 + bar) as i64 {
            assert_eq!((d.reason.as_str(), d.would_send), ("expected_below_min_profit", false), "{expected} tip {tip} bar {bar}: {d:?}");
            refused += 1;
            continue;
        }
        assert!(d.would_send, "{expected} {share} {max_band} {mf:?} {bam}: {d:?}");
        sent += 1;
        in_scope += on as u32;
        let a = by_attempt[&d.attempt.unwrap()];
        // the decision's net and the attempt's: the expected profit less this tip and the base fee, over the bar
        assert_eq!(d.ev, Some(*expected as i64 - tip as i64 - 5_000));
        assert!(d.ev.unwrap() >= bar as i64);
        assert_eq!((a["tip"]["lamports"].as_u64(), a["tip"]["arm"].as_f64()), (Some(tip), on.then_some(*share)), "{a}");
        assert_eq!(a["experiments"].get("x4_share").and_then(|v| v.as_f64()), on.then_some(*share));
        assert_eq!(a["experiments"].get("margin").and_then(|v| v.as_u64()), *mf);
        assert!((1_000..=100_000).contains(&tip), "the floor and the cap: {tip}");
        let mp = a["min_profit_onchain"].as_u64().unwrap();
        assert_eq!((mp, a["margin"].as_u64()), (tip + 5_000 + floor, Some(floor)), "{a}");
        assert!(mp <= *expected, "a landed bundle cannot lose: min_profit {mp} over {expected}");
        if *bam {
            assert_eq!(a["tip"]["bam"]["band_tip"].as_u64(), Some(band_tip), "the BAM floor raises the arm's band tip");
            assert!(tip >= band_tip && tip <= band_tip.max(((edge as f64 * p.max_share) as u64).min(100_000)), "within the BAM room: {tip} {band_tip} {edge}");
            raised += (tip > band_tip) as u32;
        } else {
            assert!(a["tip"]["bam"].is_null());
        }
    }
    eprintln!("x4 property: {sent} would-sends ({in_scope} in the arm's bands, {raised} raised by the BAM floor), {refused} refused");
    assert!(sent >= 200 && refused >= 50 && in_scope >= 100 && raised >= 20 && in_scope < sent, "every path taken: {sent} {refused} {in_scope} {raised}");
}

/// WP-11: the BAM floor per X4 arm. On a BAM-led slot each arm's band tip is raised toward the floor (0.05 x 100,000 CU =
/// 5,000) within its room, and a band tip already over the floor is kept; on a Jito-led slot each arm bids its own share.
/// The signed tip reaches the block engine
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_bam_floor_raises_each_arms_bid() {
    use crate::experiments::Arms;
    // 12,000 expected (edge 7,000): arm 0.1 -> 700, the [tips] floor 1,000; arm 0.35 -> 2,450. 105,000 expected (edge 100,000):
    // 10,000 and 35,000, both over the BAM floor. One rig per edge (the test path's 5 sends a second)
    let cases = [(0.1, 12_000u64, 101u64, 5_000u64, "bam_floor"), (0.35, 12_000, 101, 5_000, "bam_floor"), (0.1, 12_000, 97, 1_000, "share_of_edge"),
        (0.35, 12_000, 97, 2_450, "share_of_edge"), (0.1, 105_000, 101, 10_000, "share_of_edge"), (0.35, 105_000, 101, 35_000, "share_of_edge"),
        (0.1, 105_000, 97, 10_000, "share_of_edge"), (0.35, 105_000, 97, 35_000, "share_of_edge")];
    for (j, part) in cases.chunks(4).enumerate() {
    let mut r = rig(if j == 0 { "x4-bam-a" } else { "x4-bam-b" }, Mode::Live, "[send_policy.bam]\nenabled = true\nmin_tip_per_cu = 0.05\nmax_share = 0.9\n").await;
    for (k, (share, expected, tip_slot, want, policy)) in part.iter().enumerate() {
        let arms = Arms { x4: x4_arm(*share, 2), ..Default::default() };
        let d = r.decide(with_arms(route(1, damm(2, MINT), *expected, 10 + k as u64), arms), *tip_slot, now_ns());
        assert_eq!((d.reason.as_str(), d.ev), ("sent", Some(*expected as i64 - *want as i64 - 5_000)), "case {k}: {d:?}");
        let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
        let (tx, _) = crate::tx::parse_wire(&r.got.lock().unwrap()[k].0).unwrap();
        assert_eq!(send::tip_paid(&tx, &tip_accounts()), *want, "case {k}: the signed tip");
        r.x.on_settled(Settled::Fired { attempt, fired }, now_ns(), &|_| None);
        let a = &r.lines("attempts")[k];
        assert_eq!((a["tip"]["lamports"].as_u64(), a["tip"]["arm"].as_f64(), a["tip"]["policy"].as_str()), (Some(*want), Some(*share), Some(*policy)), "case {k}: {a}");
        assert_eq!(a["leader"]["kind"].as_str(), Some(if *tip_slot == 101 { "bam" } else { "jito" }));
    }
    }
}

/// WP-11 (X2): the delay arm sleeps on the send task, never on the engine thread: `decide` returns at once and the copy
/// leaves the arm's 20 ms after the fire was handed over (attempts `experiments.x2_delay_ms`); out of its scope (a band
/// above `max_band`) nothing is delayed or recorded; a would-send records its arm (nothing is fired)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn x2_delays_the_copy_on_the_send_task() {
    use crate::experiments::{Arm, Arms, Scope};
    let mut r = rig("x2-delay", Mode::Live, "").await;
    let arms = |max_band: u8| Arms { x2: Some(Arm { idx: 1, value: 20, scope: Scope { max_band, ..Scope::ALL } }), ..Default::default() };
    let t0 = std::time::Instant::now();
    let d = r.decide(with_arms(route(1, damm(2, MINT), 12_000, 7), arms(4)), 97, now_ns());
    let took = t0.elapsed();
    assert_eq!(d.reason, "sent", "{d:?}");
    assert!(took < std::time::Duration::from_millis(20), "the engine thread does not wait for the delay: {took:?}");
    let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
    r.x.on_settled(Settled::Fired { attempt, fired: fired.clone() }, now_ns(), &|_| None);
    let a = &r.lines("attempts")[0];
    let handed = a["stages"]["t_enqueued"].as_u64().unwrap();
    assert!(fired.copies[0].t_sent >= handed + 20_000_000, "the copy left {} ms after the fire", (fired.copies[0].t_sent - handed) as f64 / 1e6);
    assert_eq!(a["experiments"], json!({ "x2_delay_ms": 20 }));
    // a scope of band 0 only: an edge of 30,000 (band 1) is out of it, sent at once, nothing recorded
    let d = r.decide(with_arms(route(1, damm(2, MINT), 35_000, 8), arms(0)), 97, now_ns());
    assert_eq!(d.reason, "sent");
    let _ = r.settled().await;
    assert_eq!(r.lines("attempts")[1]["experiments"], json!({}), "out of scope: no arm applied");
    let mut s = rig("x2-would", Mode::Shadow, "").await;
    let d = s.decide(with_arms(route(1, damm(2, MINT), 12_000, 7), arms(4)), 97, now_ns());
    assert!(d.would_send);
    assert_eq!(s.lines("attempts")[0]["experiments"], json!({ "x2_delay_ms": 20 }), "a would-send records its arm");
}

/// WP-11 (the size arm): the cap applies where the engine picks the size. Under each arm the engine's size search stops
/// at the arm, and at the executor's cap below it (the canary's 0.05 SOL, the bankroll's 0.055 SOL) on the money view of
/// the last journaled decision-point record: every priced route within it, the decision's size that cap (the profit rises
/// with the size here), and the attempt trades the decision's size. The first decision, before any record, prices at
/// the arm and the executor re-quotes at its cap (as without the arm): no attempt ever exceeds the executor's caps
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_engine_prices_under_each_size_arm() {
    use crate::experiments::{Exp, Experiments, Scope};
    let canary = "[canary]\nenabled = true\ncount = 100\nevery_ms = 1\nsize_sol = 0.05\nmax_spend_lamports = 20000\n";
    let bankroll = "[live]\nmax_size_sol = 0.2\nbankroll_share = 0.85\nbankroll_reserve_sol = 0.03\n";
    for (mode, extra, exec_cap, view) in [(Mode::Canary, canary, 50_000_000u64, None), (Mode::Shadow, bankroll, 55_000_000, Some(money(100_000_000, 90_000_000, 0)))] {
        let mut r = rig("size-arm", mode, &format!("[send_policy]\nbig_band_max_per_sec = 1000\n{extra}")).await;
        let gate = SendGate::new();
        if mode == Mode::Shadow { let _ = gate.shadow("mode_shadow", "no --live or --canary: nothing is sent", true); }
        let (mut e, a, b) = amm_engine();
        e.set_rec(r.rec.clone());
        // arms 0.02 (a rung) and 0.1 (over the executor's cap); the ladder's default 0.02 - 1 SOL
        e.set_experiments(Some(Experiments { seed: 11, size: Some(Exp { arms: vec![0.02, 0.1], weights: vec![1.0, 1.0], scope: Scope::ALL }), ..Default::default() }));
        let mut x = std::mem::replace(&mut r.x, idle_exec());
        if let Some(m) = view { x.set_money(m); }
        assert_eq!(x.size_cap(), exec_cap);
        x.set_gate(gate);
        x.set_health(e.health_flags());
        e.exec = Some(x);
        let mut t = now_ns();
        amm_start(&mut e, &mut t);
        // a second apart (a would-send's rate model: 5 a second)
        for k in 0..12u8 { t += 1_000_000_000; amm_move(&mut e, if k % 2 == 0 { &a } else { &b }, k, 1_030 + 30 * k as u64, &mut t); }
        r.rec.sync();
        let d: Vec<Value> = rec::read_jsonl(&r.dir, "decisions").unwrap().into_iter().filter(|l| l["opp"].is_u64()).collect();
        let att = rec::read_jsonl(&r.dir, "attempts").unwrap();
        let by_dec: HashMap<u64, &Value> = d.iter().map(|l| (l["decision"].as_u64().unwrap(), l)).collect();
        let mut arms_seen = std::collections::BTreeSet::new();
        let first = d[0]["decision"].as_u64().unwrap();
        for l in &d {
            let arm = crate::experiments::sol_lamports(l["experiments"]["size_max_sol"].as_f64().unwrap());
            let cap = if l["decision"].as_u64() == Some(first) { arm } else { arm.min(exec_cap) };
            for rt in l["routes"].as_array().unwrap() { if let Some(sz) = rt["size"].as_u64() { assert!(sz <= cap, "{mode:?}: priced {sz} past its cap {cap}"); } }
            assert_eq!(l["routes"][l["best"].as_u64().unwrap() as usize]["size"].as_u64(), Some(cap), "{mode:?}: the profit rises with the size: the cap binds");
        }
        assert!(!att.is_empty(), "{mode:?}");
        for x in &att {
            let l = by_dec[&x["decision"].as_u64().unwrap()];
            let priced = l["routes"][l["best"].as_u64().unwrap() as usize]["size"].as_u64().unwrap();
            let size = x["size_lamports"].as_u64().unwrap();
            assert_eq!(size, priced.min(exec_cap), "{mode:?}: the decision's size, at most the executor's cap");
            if l["decision"].as_u64() != Some(first) { assert_eq!(size, priced, "{mode:?}: the decision priced is the trade sent"); }
            assert!(size <= exec_cap);
            assert_eq!(x["experiments"]["size_max_sol"], l["experiments"]["size_max_sol"]);
            arms_seen.insert(l["experiments"]["size_max_sol"].to_string());
        }
        assert_eq!(arms_seen.len(), 2, "{mode:?}: both arms sent: {arms_seen:?}");
        assert_eq!(e.exec.as_ref().unwrap().counts.get("reject_size_cap"), None, "{mode:?}: the engine re-quoted at the executor's cap");
    }
}

/// WP-11 (review #14): the executor refuses a route sized past its decision's size arm (`size_arm`, counted
/// `reject_size_arm`: the engine's search stops at the arm, so only a route sized elsewhere reaches the check); at the arm,
/// or with the route's evaluation kind out of the arm's scope, it is sent
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_executor_refuses_a_size_past_its_arm() {
    use crate::experiments::{Arm, Arms, Scope};
    let mut r = rig("size-arm-exec", Mode::Live, "").await;
    let arm = |sol: f64, kinds: u8| Arms { size: Some(Arm { idx: 0, value: sol, scope: Scope { kinds, ..Scope::ALL } }), ..Default::default() };
    // the test routes trade 0.05 SOL (`SIZE`); an arm of 0.01 SOL
    let d = r.decide(with_arms(route(1, damm(2, MINT), 12_000, 7), arm(0.01, Scope::ALL.kinds)), 97, now_ns());
    assert_eq!((d.verdict, d.reason.as_str(), d.attempt), ("reject", "size_arm", None), "{d:?}");
    assert_eq!(r.n("reject_size_arm"), 1);
    assert!(r.got.lock().unwrap().is_empty() && r.lines("attempts").is_empty(), "nothing built, nothing sent");
    // at the arm (0.05 SOL): sent
    let d = r.decide(with_arms(route(1, damm(2, MINT), 12_000, 8), arm(0.05, Scope::ALL.kinds)), 97, now_ns());
    assert_eq!(d.reason, "sent", "{d:?}");
    let _ = r.settled().await;
    // an arm scoped to quiescent evaluations only: this commit-triggered route is not the arm's
    let d = r.decide(with_arms(route(1, damm(2, MINT), 12_000, 9), arm(0.01, 0b0010)), 97, now_ns());
    assert_eq!(d.reason, "sent", "out of the arm's scope: {d:?}");
    let _ = r.settled().await;
    assert_eq!(r.lines("attempts")[0]["experiments_assigned"], json!({ "size_max_sol": 0.05 }), "the assigned arm recorded (review #10)");
}

// ------------------------------------------------------------------------------------------------ arbx-fast: Helius big gaps

/// arbx-fast `[send_policy.helius_big]`: a decision expecting at least the threshold goes to Helius Sender with 70% of its
/// edge (after base and priority fee) as the tip, the compute-unit price Helius requires, and an on-chain min_profit that
/// covers tip + priority fee + base fee + margin; a smaller one stays a Jito bundle with the band's tip
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_big_gap_goes_to_helius_with_seventy_percent() {
    let extra = "[[send]]\nname = \"helius\"\nkind = \"helius\"\nurl = \"https://127.0.0.1:9/fast\"\ntip_lamports = 1000000\nmax_per_sec = 5\n\
        [send_policy.helius_big]\nenabled = true\nmin_expected_lamports = 1500000\ntip_share = 0.7\npriority_fee_lamports = 10000\nmax_per_sec = 2\n";
    let mut r = rig("helius-big", Mode::Shadow, extra).await;
    let d = r.decide(route(1, damm(2, MINT), 2_000_000, 7), 97, now_ns());
    assert!(d.would_send, "{d:?}");
    // CU limit 100,000 (the wallet holds MINT): 100,000 micro-lamports a CU = the 10,000-lamport priority fee; edge
    // 2,000,000 - 5,000 - 10,000
    let prio = 10_000u64;
    let tip = (1_985_000f64 * 0.7) as u64;
    let a = r.lines("attempts");
    assert_eq!((a[0]["helius_big"]["tip"].as_u64(), a[0]["helius_big"]["prio_fee"].as_u64(), a[0]["helius_big"]["cu_price_micro"].as_u64()),
        (Some(tip), Some(prio), Some(100_000)), "{}", a[0]);
    assert_eq!(a[0]["min_profit_onchain"].as_u64(), Some(tip + prio + BASE_FEE + 1), "tip + priority + base fee + the margin floor");
    assert_eq!(d.ev, Some(2_000_000 - tip as i64 - BASE_FEE as i64 - prio as i64));
    // under the threshold: a Jito bundle, no Helius fields
    let d = r.decide(route(3, damm(4, MINT), 1_000_000, 8), 97, now_ns());
    assert!(d.would_send, "{d:?}");
    let a = r.lines("attempts");
    assert!(a[1]["helius_big"].is_null(), "{}", a[1]);
    // the Helius window: at most max_per_sec (2) a second
    let t = now_ns();
    let _ = r.decide(route(5, damm(6, MINT), 2_000_000, 9), 97, t);
    let d = r.decide(route(7, damm(8, MINT), 2_000_000, 10), 97, t);
    assert_eq!(d.reason, "helius_rate", "{d:?}");
}

/// arbx-fast `also = ["bolt"]`: the same transaction carries Bolt's minimum tip too, out of the 70%; Helius gets the rest
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_big_gap_pays_helius_and_bolt_out_of_seventy_percent() {
    let extra = "[[send]]\nname = \"helius\"\nkind = \"helius\"\nurl = \"https://127.0.0.1:9/fast\"\ntip_lamports = 1000000\nmax_per_sec = 5\n\
        [[send]]\nname = \"bolt\"\nkind = \"bolt\"\nurl = \"https://127.0.0.1:9/bolt\"\ntoken_env = \"ARBX_TEST_BOLT\"\ntip_lamports = 1000000\nmax_per_sec = 5\n\
        [send_policy.helius_big]\nenabled = true\nmin_expected_lamports = 3000000\ntip_share = 0.7\npriority_fee_lamports = 10000\nmax_per_sec = 2\nalso = [\"bolt\"]\n";
    let mut r = rig("helius-bolt", Mode::Shadow, extra).await;
    let d = r.decide(route(1, damm(2, MINT), 5_000_000, 7), 97, now_ns());
    assert!(d.would_send, "{d:?}");
    let total = (4_985_000f64 * 0.7) as u64;
    let a = r.lines("attempts");
    let h = &a[0]["helius_big"];
    assert_eq!((h["tip"].as_u64(), h["also"][0]["path"].as_str(), h["also"][0]["tip"].as_u64(), h["tips_total"].as_u64()),
        (Some(total - 1_000_000), Some("bolt"), Some(1_000_000), Some(total)), "{h}");
    assert_eq!(a[0]["min_profit_onchain"].as_u64(), Some(total + 10_000 + BASE_FEE + 1));
    // at the threshold, 3,000,000: 70% of the 2,985,000 edge (2,089,500) still covers both 1,000,000 minimums
    let d = r.decide(route(3, damm(4, MINT), 3_000_000, 8), 97, now_ns());
    assert!(d.would_send, "{d:?}");
    let a = r.lines("attempts");
    assert_eq!((a[1]["helius_big"]["tip"].as_u64(), a[1]["helius_big"]["tips_total"].as_u64()), (Some((2_985_000f64 * 0.7) as u64 - 1_000_000), Some((2_985_000f64 * 0.7) as u64)), "{}", a[1]["helius_big"]);
}

/// arbx-fast: a big gap whose share cannot cover Bolt's minimum too goes to Helius alone (no `also` tip, no Bolt copy)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_smaller_big_gap_goes_to_helius_alone() {
    let extra = "[[send]]\nname = \"helius\"\nkind = \"helius\"\nurl = \"https://127.0.0.1:9/fast\"\ntip_lamports = 1000000\nmax_per_sec = 5\n\
        [[send]]\nname = \"bolt\"\nkind = \"bolt\"\nurl = \"https://127.0.0.1:9/bolt\"\ntoken_env = \"ARBX_TEST_BOLT\"\ntip_lamports = 1000000\nmax_per_sec = 5\n\
        [send_policy.helius_big]\nenabled = true\nmin_expected_lamports = 1700000\ntip_share = 0.6\npriority_fee_lamports = 10000\nmax_per_sec = 2\nalso = [\"bolt\"]\n";
    let mut r = rig("helius-alone", Mode::Shadow, extra).await;
    let d = r.decide(route(1, damm(2, MINT), 2_500_000, 7), 97, now_ns());
    assert!(d.would_send, "{d:?}");
    let a = r.lines("attempts");
    let h = &a[0]["helius_big"];
    assert_eq!((h["tip"].as_u64(), h["also"].as_array().map(|v| v.len()), h["tips_total"].as_u64()),
        (Some((2_485_000f64 * 0.6) as u64), Some(0), Some((2_485_000f64 * 0.6) as u64)), "60% of 2,485,000 = 1,491,000: under 2,000,000, Helius alone: {h}");
}
