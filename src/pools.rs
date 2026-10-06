//! Pool registry: the seed pools (the markets whose swaps we react to) plus every registry pool on the same token
//! pairs, completed and verified from chain at boot. Metadata always comes from the pool account itself, never from
//! the files, so a stale or mis-oriented row can't produce a wrong quote.
use crate::config::PoolsCfg;
use crate::pda;
use crate::rec::accounts::{role, RoleOf, NO_POOL};
use crate::rpc::Rpc;
use crate::tx::{b58, pk, Pk};
use crate::venues::{dlmm, pk_at, PoolMeta, Venue, WSOL};
use arbx_sizing::venue::dammv2;
use anyhow::{Context, Result};
use rustc_hash::{FxHashMap as HashMap, FxHashSet as HashSet};
use std::sync::LazyLock;

pub static PUMP_FEE_CONFIG: LazyLock<Pk> = LazyLock::new(|| pk("5PHirr8joyTMp9JMm6nW7hNDVyEYdkzDqazxPD7RaTjx"));
/// PumpSwap's GlobalConfig: its disable flags and configurable-creator-fee switch are part of every PumpSwap quote
/// (arbx-sizing `pumpswap::parse`, PLAN-ADDENDUM WP-16), so the state stream follows it
pub static PUMP_GLOBAL_CONFIG: LazyLock<Pk> = LazyLock::new(|| arbx_sizing::layout::PUMP_GLOBAL_CONFIG);
pub static PUMP_FUN: LazyLock<Pk> = LazyLock::new(|| pk("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"));
/// the Clock sysvar (chain time; WP-03 item 2)
pub static CLOCK_SYSVAR: LazyLock<Pk> = LazyLock::new(|| pk("SysvarC1ock11111111111111111111111111111111"));
/// DLMM bin arrays kept live around the active one (each side)
pub const DLMM_ARRAY_SPAN: i64 = 3;

pub struct Registry {
    pub pools: Vec<PoolMeta>,
    pub by_pool: HashMap<Pk, usize>,
    /// unordered mint pair -> pools on it (only pairs with WSOL and at least two pools)
    pub pairs: HashMap<(Pk, Pk), Vec<usize>>,
    /// pools that came from the seed list (MriyaNN8's markets)
    pub seeds: HashSet<Pk>,
    /// pools from our own registry
    pub ours: HashSet<Pk>,
}

pub fn pair_key(a: &Pk, b: &Pk) -> (Pk, Pk) { if a <= b { (*a, *b) } else { (*b, *a) } }

/// The pool's Token-2022 mints its quote scans for a transfer fee or hook (arbx-sizing refuses both: `sz_transfer_fee`,
/// `sz_transfer_hook`), beyond the accounts it already follows (a PumpSwap pool's base mint is `extra[0]`). SPL Token
/// mints can carry neither, so they are not followed
pub fn t22_mints(m: &PoolMeta) -> Vec<Pk> {
    let mut v = Vec::new();
    for (mint, prog) in [(m.t0, m.t0_prog), (m.t1, m.t1_prog)] {
        if prog == *pda::TOKEN_2022 && !m.extra.contains(&mint) && !v.contains(&mint) { v.push(mint); }
    }
    v
}

/// (venue, pool) candidates from the seed CSV and the registry
pub fn candidates(cfg: &PoolsCfg) -> Result<(Vec<(Venue, Pk)>, HashSet<Pk>, HashSet<Pk>)> {
    let text = std::fs::read_to_string(&cfg.seed_csv).with_context(|| format!("reading {}", cfg.seed_csv))?;
    let mut lines = text.lines();
    let header: Vec<&str> = lines.next().context("empty seed csv")?.split(',').collect();
    let col = |name: &str| header.iter().position(|h| h.trim() == name);
    let (cv, cp) = (col("venue").context("seed csv: no venue column")?, col("pool").context("seed csv: no pool column")?);
    let (ca, cb) = (col("mint_a"), col("mint_b"));
    let mut out = Vec::new();
    let mut seeds = HashSet::default();
    let mut ours = HashSet::default();
    let mut seed_pairs = HashSet::default();
    for l in lines {
        let f: Vec<&str> = l.split(',').collect();
        let (Some(v), Some(p)) = (f.get(cv).and_then(|s| Venue::parse(s.trim())), f.get(cp)) else { continue };
        let Ok(key) = bs58::decode(p.trim()).into_vec() else { continue };
        let Ok(key): Result<Pk, _> = key.try_into() else { continue };
        out.push((v, key));
        seeds.insert(key);
        if let (Some(a), Some(b)) = (ca.and_then(|i| f.get(i)), cb.and_then(|i| f.get(i))) {
            if let (Ok(a), Ok(b)) = (bs58::decode(a.trim()).into_vec(), bs58::decode(b.trim()).into_vec()) {
                if let (Ok(a), Ok(b)) = (Pk::try_from(a), Pk::try_from(b)) { seed_pairs.insert(pair_key(&a, &b)); }
            }
        }
    }
    if let Some(reg) = &cfg.registry_json {
        let rows: Vec<serde_json::Value> = serde_json::from_str(&std::fs::read_to_string(reg).with_context(|| format!("reading {reg}"))?)?;
        for r in rows {
            let (Some(v), Some(p), Some(t0), Some(t1)) = (r["venue"].as_str().and_then(Venue::parse), r["pool"].as_str(), r["t0"].as_str(), r["t1"].as_str()) else { continue };
            let (p, t0, t1) = (pk(p), pk(t0), pk(t1));
            if cfg.registry_all || seed_pairs.contains(&pair_key(&t0, &t1)) {
                ours.insert(p);
                if !seeds.contains(&p) { out.push((v, p)); }
            }
        }
    }
    Ok((out, seeds, ours))
}

/// A candidate pool `boot` did not keep, and why (WP-16 review F8: meta.json `pools.dropped`, events.jsonl
/// `pools_dropped`): `missing` (no account), `owner` (not the venue's program), `layout` (an account the venue's quote
/// does not read: a length or discriminator arbx-sizing does not accept), `transfer_fee`, `transfer_hook`,
/// `mint_layout` (a mint arbx-sizing refuses: a nonzero Token-2022 transfer fee, a transfer hook with a program set, an
/// extension list it cannot read; `mint` names it)
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize)]
pub struct Dropped { pub venue: Venue, pub pool: String, pub why: &'static str, pub mint: Option<String> }

/// The drops as a boot record: `{total, counts: {why: n}, pools: [{venue, pool, why, mint}]}`
pub fn drops_json(d: &[Dropped]) -> serde_json::Value {
    let mut counts = std::collections::BTreeMap::<&str, usize>::new();
    for x in d { *counts.entry(x.why).or_default() += 1; }
    serde_json::json!({ "total": d.len(), "counts": counts, "pools": d })
}

/// The candidates' metadata from their accounts (None: not found), and the ones that are not kept
pub fn pool_metas(cands: &[(Venue, Pk)], accts: &[Option<crate::rpc::Account>]) -> (Vec<PoolMeta>, Vec<Dropped>) {
    let (mut metas, mut drops) = (Vec::new(), Vec::new());
    for ((venue, pool), a) in cands.iter().zip(accts) {
        let why = match a {
            None => "missing",
            Some(a) if a.owner != venue.program() => "owner",
            Some(a) => match meta_of(*venue, pool, &a.data) { Some(m) => { metas.push(m); continue } None => "layout" },
        };
        drops.push(Dropped { venue: *venue, pool: b58(pool), why, mint: None });
    }
    (metas, drops)
}

/// The token programs from the mints' owners (`mints` and their accounts, None: not found), DAMM v2's `flag`, and the
/// pools whose mint arbx-sizing refuses dropped (returned)
pub fn apply_mints(metas: &mut Vec<PoolMeta>, mints: &[Pk], macc: &[Option<crate::rpc::Account>]) -> Vec<Dropped> {
    let mut refused: HashMap<Pk, &'static str> = HashMap::default();
    let owner: HashMap<Pk, Pk> = mints.iter().zip(macc).filter_map(|(k, a)| a.as_ref().map(|a| {
        if let Some(why) = mint_refused(&a.data) { refused.insert(*k, why); }
        (*k, a.owner)
    })).collect();
    for m in metas.iter_mut() {
        if let Some(o) = owner.get(&m.t0) { m.t0_prog = *o; }
        if let Some(o) = owner.get(&m.t1) { m.t1_prog = *o; }
        // DAMM v2: `flag` = neither mint charges a Token-2022 transfer fee (kept for the tools; the quote scans the mints)
        if m.venue == Venue::DammV2 { m.flag = !refused.contains_key(&m.t0) && !refused.contains_key(&m.t1); }
    }
    // a token that takes a transfer fee ("tax token", Token-2022) shrinks every leg by it, and one with a transfer hook
    // needs accounts our legs do not pass: arbx-sizing refuses both (`sz_transfer_fee`, `sz_transfer_hook`), so their
    // pools could only make fake gaps (2026-10-03: exactly -100 / -300 bps per leg on fee pools). Drop them here; a
    // mint that turns its fee or hook on later is refused at quote time (the engine follows Token-2022 mints).
    let mut drops = Vec::new();
    metas.retain(|m| {
        let Some((mint, why)) = [m.t0, m.t1].into_iter().find_map(|k| refused.get(&k).map(|w| (k, *w))) else { return true };
        let why = if why == "layout" { "mint_layout" } else { why };
        drops.push(Dropped { venue: m.venue, pool: b58(&m.pool), why, mint: Some(b58(&mint)) });
        false
    });
    drops
}

/// Read every candidate pool from chain and build its metadata; the candidates not kept, with why (`Dropped`)
pub async fn boot(rpc: &Rpc, cands: &[(Venue, Pk)], seeds: HashSet<Pk>, ours: HashSet<Pk>) -> Result<(Registry, Vec<Dropped>)> {
    let keys: Vec<Pk> = cands.iter().map(|c| c.1).collect();
    let (_, accts) = rpc.accounts(&keys).await?;
    let (mut metas, mut drops) = pool_metas(cands, &accts);
    let mints: Vec<Pk> = metas.iter().flat_map(|m| [m.t0, m.t1]).collect::<HashSet<_>>().into_iter().collect();
    let (_, macc) = rpc.accounts(&mints).await?;
    drops.extend(apply_mints(&mut metas, &mints, &macc));
    if !drops.is_empty() { eprintln!("pools: dropped {} candidates {} (meta.json pools.dropped)", drops.len(), drops_json(&drops)["counts"]); }
    // DLMM: the bitmap extension's PDA is `extra[0]`, followed on the state stream whether or not it exists (`extra_watch`);
    // the builder reads it from the store per send (PLAN WP-06 item 6: the boot-time check is gone, `flag` stays false)
    // index by pair; keep pairs with WSOL and 2+ pools
    let mut pairs: HashMap<(Pk, Pk), Vec<usize>> = HashMap::default();
    for (i, m) in metas.iter().enumerate() { pairs.entry(pair_key(&m.t0, &m.t1)).or_default().push(i); }
    pairs.retain(|k, v| (k.0 == *WSOL || k.1 == *WSOL) && v.len() >= 2);
    let by_pool = metas.iter().enumerate().map(|(i, m)| (m.pool, i)).collect();
    Ok((Registry { pools: metas, by_pool, pairs, seeds, ours }, drops))
}

/// A pool's metadata from its own account bytes (the token programs default to SPL Token: `boot` sets them from the
/// mints' owners; DLMM's `flag` is unused since WP-06: the builder reads the bitmap extension, `extra[0]`, from the store
/// per send). None: not a pool of this venue the engine reads
pub fn meta_of(venue: Venue, pool: &Pk, d: &[u8]) -> Option<PoolMeta> {
    let m = match venue {
        Venue::RayAmmV4 if d.len() >= 752 => (pk_at(d, 400), pk_at(d, 432), pk_at(d, 336), pk_at(d, 368), vec![], false),
        Venue::RayCpmm if d.len() >= 413 => (pk_at(d, 168), pk_at(d, 200), pk_at(d, 72), pk_at(d, 104), vec![pk_at(d, 8)?], false),
        // every length the program (and arbx-sizing) reads: from the original layout up (a pool written before a trailing
        // field existed is shorter; WP-16 review F1)
        Venue::PumpSwap if d.len() >= arbx_sizing::venue::pumpswap::POOL_MIN_LEN => {
            let base = pk_at(d, 43)?;
            let canonical = pk_at(d, 11) == Some(pda::find_program_address(&[b"pool-authority", &base], &PUMP_FUN).0);
            (Some(base), pk_at(d, 75), pk_at(d, 139), pk_at(d, 171), vec![base], canonical)
        }
        // DAMM v2: mints and vaults straight from the pool (t0 = token a, t1 = token b: the program's own order); a pool of
        // another length or discriminator is not one arbx-sizing prices
        Venue::DammV2 => {
            let k = dammv2::decode(d).and_then(|_| dammv2::keys(d))?;
            (Some(*k.token_a_mint), Some(*k.token_b_mint), Some(*k.token_a_vault), Some(*k.token_b_vault), vec![], false)
        }
        Venue::Dlmm if d.len() >= 904 => {
            let ext = pda::find_program_address(&[b"bitmap", pool], &venue.program()).0;
            (pk_at(d, 88), pk_at(d, 120), pk_at(d, 152), pk_at(d, 184), vec![ext], false)
        }
        _ => return None,
    };
    let (Some(t0), Some(t1), Some(v0), Some(v1)) = (m.0, m.1, m.2, m.3) else { return None };
    Some(PoolMeta { venue, pool: *pool, t0, t1, vault0: v0, vault1: v1, t0_prog: *pda::TOKEN_PROGRAM, t1_prog: *pda::TOKEN_PROGRAM, extra: m.4, flag: m.5 })
}

/// Why arbx-sizing refuses a mint (DESIGN.md §2.0, `token::scan_extensions`): a Token-2022 TransferFeeConfig whose
/// older or newer fee is nonzero (`transfer_fee`), a TransferHook with a program set (`transfer_hook`), or an extension
/// list it cannot read (`layout`). SPL mints (82 bytes) have none
pub fn mint_refused(d: &[u8]) -> Option<&'static str> {
    if d.len() <= 82 { return None; }
    match arbx_sizing::token::scan_extensions(d) {
        Ok(()) => None,
        Err(arbx_sizing::Abort::TransferFee) => Some("transfer_fee"),
        Err(arbx_sizing::Abort::TransferHook) => Some("transfer_hook"),
        Err(_) => Some("layout"),
    }
}

impl Registry {
    /// accounts the state stream must follow (DLMM bin arrays are added by the engine around the active bin)
    pub fn static_accounts(&self) -> Vec<Pk> {
        let mut s: Vec<Pk> = Vec::new();
        let mut seen = HashSet::default();
        let mut add = |k: Pk, s: &mut Vec<Pk>| if seen.insert(k) { s.push(k) };
        for &i in self.pairs.values().flatten() {
            let m = &self.pools[i];
            add(m.pool, &mut s);
            // DLMM and DAMM v2 price off the pool account alone (DLMM adds its bin arrays through the engine)
            if !matches!(m.venue, Venue::Dlmm | Venue::DammV2) { add(m.vault0, &mut s); add(m.vault1, &mut s); for e in &m.extra { add(*e, &mut s); } }
            if m.venue == Venue::PumpSwap { add(*PUMP_FEE_CONFIG, &mut s); add(*PUMP_GLOBAL_CONFIG, &mut s); }
            for k in t22_mints(m) { add(k, &mut s); }
        }
        s
    }
    /// Every account `static_accounts` follows, with its role (accounts.bin DICT, exec.jsonl `watched`; WP-03): pools,
    /// vaults, PumpSwap base mints, CPMM configs, the PumpSwap fee config and GlobalConfig, Token-2022 mints (WP-16)
    pub fn watch_roles(&self) -> Vec<(Pk, RoleOf)> {
        let mut out = Vec::new();
        let r = |role: u8, i: usize| RoleOf { role, pool_index: i as u32 };
        for &i in self.pairs.values().flatten() {
            let m = &self.pools[i];
            out.push((m.pool, r(role::POOL, i)));
            if !matches!(m.venue, Venue::Dlmm | Venue::DammV2) {
                out.push((m.vault0, r(role::VAULT, i)));
                out.push((m.vault1, r(role::VAULT, i)));
                for e in &m.extra { out.push((*e, r(if m.venue == Venue::PumpSwap { role::MINT } else { role::EXTRA }, i))); }
            }
            if m.venue == Venue::PumpSwap {
                out.push((*PUMP_FEE_CONFIG, RoleOf { role: role::PUMP_FEE_CONFIG, pool_index: NO_POOL }));
                out.push((*PUMP_GLOBAL_CONFIG, RoleOf { role: role::PUMP_GLOBAL_CONFIG, pool_index: NO_POOL }));
            }
            for k in t22_mints(m) { out.push((k, r(role::MINT, i))); }
        }
        out
    }

    /// The extra accounts the state stream follows (WP-03 item 2), with their roles: the Clock sysvar (chain time), every
    /// DLMM pool's bitmap-extension PDA whether or not it exists (an update arrives if one is created; the builder passes
    /// it when the store holds it, WP-06), the programdata accounts of `programs` (upgrade detection), and the wallet with
    /// its token accounts (its WSOL account and its associated account for every registry mint: every landed transaction
    /// we pay for writes the wallet; WP-06: whether the wallet holds a mint's account is the store's) and, with a PumpSwap
    /// pool, its PumpSwap user volume accumulator (WP-06 item 2: followed, so its creation is seen)
    pub fn extra_watch(&self, clock: bool, programs: &[Pk], wallet: Option<&Pk>) -> Vec<(Pk, RoleOf)> {
        let mut out = Vec::new();
        let none = |role: u8| RoleOf { role, pool_index: NO_POOL };
        if clock { out.push((*CLOCK_SYSVAR, none(role::CLOCK_SYSVAR))); }
        for &i in self.pairs.values().flatten() {
            let m = &self.pools[i];
            if m.venue == Venue::Dlmm { if let Some(ext) = m.extra.first() { out.push((*ext, RoleOf { role: role::DLMM_BITMAP_EXT, pool_index: i as u32 })); } }
        }
        let loader = pk(crate::provenance::UPGRADEABLE_LOADER);
        for p in programs { out.push((pda::find_program_address(&[p], &loader).0, none(role::PROGRAMDATA))); }
        if let Some(w) = wallet {
            out.push((*w, none(role::WALLET)));
            let mut mints: Vec<(Pk, Pk)> = vec![(*WSOL, *pda::TOKEN_PROGRAM)];
            for &i in self.pairs.values().flatten() { let m = &self.pools[i]; mints.push((m.t0, m.t0_prog)); mints.push((m.t1, m.t1_prog)); }
            mints.sort();
            mints.dedup();
            for (mint, prog) in mints { out.push((pda::ata(w, &mint, &prog), none(role::WALLET_TOKEN_ACCOUNT))); }
            if self.pairs.values().flatten().any(|&i| self.pools[i].venue == Venue::PumpSwap) { out.push((crate::build::pump_uva(w), none(role::WALLET_PUMP_UVA))); }
        }
        let mut seen = HashSet::default();
        out.retain(|(k, _)| seen.insert(*k));
        out
    }

    /// `[[state.tx_stream]]` `@watched_writable`: every watched pool and its vaults
    pub fn watched_writable(&self) -> Vec<String> {
        let mut seen = HashSet::default();
        let mut out = Vec::new();
        for &i in self.pairs.values().flatten() {
            let m = &self.pools[i];
            for k in [m.pool, m.vault0, m.vault1] { if seen.insert(k) { out.push(b58(&k)); } }
        }
        out
    }

    pub fn source(&self, p: &Pk) -> &'static str {
        match (self.seeds.contains(p), self.ours.contains(p)) { (true, true) => "both", (true, false) => "mriya", (false, true) => "ours", _ => "?" }
    }
    pub fn summary(&self) -> String {
        let n_pairs = self.pairs.len();
        let n_pools: usize = self.pairs.values().map(|v| v.len()).sum();
        let mut by_venue: HashMap<Venue, usize> = HashMap::default();
        for &i in self.pairs.values().flatten() { *by_venue.entry(self.pools[i].venue).or_default() += 1; }
        let (m, o) = (self.pairs.values().flatten().filter(|&&i| self.seeds.contains(&self.pools[i].pool)).count(),
            self.pairs.values().flatten().filter(|&&i| self.ours.contains(&self.pools[i].pool)).count());
        format!("{n_pairs} SOL pairs with 2+ pools, {n_pools} pools ({by_venue:?}); MriyaNN8's {m}, ours {o}")
    }
}

/// bin arrays to follow for a DLMM pool around `active`
pub fn dlmm_arrays(pool: &Pk, active: i32) -> Vec<(i64, Pk)> {
    let c = dlmm::array_index(active);
    (c - DLMM_ARRAY_SPAN..=c + DLMM_ARRAY_SPAN).map(|i| (i, dlmm::bin_array_pda(pool, i))).collect()
}

pub fn show(k: &Pk) -> String { let s = b58(k); format!("{}…", &s[..8]) }

#[cfg(test)]
mod tests {
    use super::*;
    use crate::rpc::Account;

    /// WP-16 review F8: the candidates `boot` does not keep are named with why: a missing account, another owner, a
    /// layout no venue reads (a PumpSwap pool below the program's 211 bytes), a mint arbx-sizing refuses (a Token-2022
    /// transfer fee, a transfer hook with a program set); the others are kept, a mint's owner setting the token program
    #[test]
    fn boot_names_every_candidate_it_drops() {
        let pump = |len: usize, base: u8| { let mut d = vec![0u8; len]; d[43..75].fill(base); d[75..107].copy_from_slice(&*WSOL); d[139..171].fill(base + 1); d[171..203].fill(base + 2); d };
        let acct = |owner: Pk, data: Vec<u8>| Some(Account { owner, lamports: 1, data });
        let p = |n: u8| [n; 32];
        let cands = vec![(Venue::PumpSwap, p(1)), (Venue::PumpSwap, p(2)), (Venue::PumpSwap, p(3)), (Venue::PumpSwap, p(4)), (Venue::PumpSwap, p(5)), (Venue::PumpSwap, p(6))];
        let pump_prog = Venue::PumpSwap.program();
        let accts = vec![acct(pump_prog, pump(301, 10)), None, acct([9; 32], pump(301, 20)), acct(pump_prog, pump(210, 30)), acct(pump_prog, pump(211, 40)),
            acct(pump_prog, pump(300, 50))];
        let (mut metas, drops) = pool_metas(&cands, &accts);
        assert_eq!(metas.iter().map(|m| m.pool[0]).collect::<Vec<_>>(), vec![1, 5, 6], "301, 211 and 300 bytes are read");
        assert_eq!(drops.iter().map(|d| (d.pool.clone(), d.why)).collect::<Vec<_>>(),
            vec![(b58(&p(2)), "missing"), (b58(&p(3)), "owner"), (b58(&p(4)), "layout")]);
        // the mints: pool 5's base charges a transfer fee, pool 6's has a transfer hook; pool 1's is clean Token-2022
        let t22 = |ext: Option<(u16, Vec<u8>)>| { let mut d = vec![0u8; 166]; d[165] = 1; if let Some((t, v)) = ext { d.extend(t.to_le_bytes()); d.extend((v.len() as u16).to_le_bytes()); d.extend(v); } d };
        let mut fee = vec![0u8; 108];
        fee[88..90].copy_from_slice(&300u16.to_le_bytes());
        let mut hook = vec![0u8; 64];
        hook[32..64].fill(7);
        let mints = vec![[10; 32], [40; 32], [50; 32], *WSOL];
        let macc = vec![acct(*pda::TOKEN_2022, t22(None)), acct(*pda::TOKEN_2022, t22(Some((1, fee)))), acct(*pda::TOKEN_2022, t22(Some((14, hook)))),
            acct(*pda::TOKEN_PROGRAM, vec![0u8; 82])];
        let drops = apply_mints(&mut metas, &mints, &macc);
        assert_eq!(metas.iter().map(|m| (m.pool[0], m.t0_prog == *pda::TOKEN_2022)).collect::<Vec<_>>(), vec![(1, true)]);
        assert_eq!(drops.iter().map(|d| (d.pool.clone(), d.why, d.mint.clone())).collect::<Vec<_>>(),
            vec![(b58(&p(5)), "transfer_fee", Some(b58(&[40; 32]))), (b58(&p(6)), "transfer_hook", Some(b58(&[50; 32])))]);
        let j = drops_json(&drops);
        assert_eq!((j["total"].as_u64(), j["counts"]["transfer_fee"].as_u64(), j["pools"][1]["why"].as_str()), (Some(2), Some(1), Some("transfer_hook")));
    }
}
