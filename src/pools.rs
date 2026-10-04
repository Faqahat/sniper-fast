//! Pool registry: the seed pools (the markets whose swaps we react to) plus every registry pool on the same token
//! pairs, completed and verified from chain at boot. Metadata always comes from the pool account itself, never from
//! the files, so a stale or mis-oriented row can't produce a wrong quote.
use crate::config::PoolsCfg;
use crate::pda;
use crate::rec::accounts::{role, RoleOf, NO_POOL};
use crate::rpc::Rpc;
use crate::tx::{b58, pk, Pk};
use crate::venues::{dlmm, pk_at, PoolMeta, Venue, WSOL};
use anyhow::{Context, Result};
use rustc_hash::{FxHashMap as HashMap, FxHashSet as HashSet};
use std::sync::LazyLock;

pub static PUMP_FEE_CONFIG: LazyLock<Pk> = LazyLock::new(|| pk("5PHirr8joyTMp9JMm6nW7hNDVyEYdkzDqazxPD7RaTjx"));
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

/// Read every candidate pool from chain and build its metadata.
pub async fn boot(rpc: &Rpc, cands: &[(Venue, Pk)], seeds: HashSet<Pk>, ours: HashSet<Pk>) -> Result<Registry> {
    let keys: Vec<Pk> = cands.iter().map(|c| c.1).collect();
    let (_, accts) = rpc.accounts(&keys).await?;
    let mut metas = Vec::new();
    for ((venue, pool), a) in cands.iter().zip(accts) {
        let Some(a) = a else { continue };
        if a.owner != venue.program() { continue; }
        let d = &a.data;
        let m = match venue {
            Venue::RayAmmV4 if d.len() >= 752 => (pk_at(d, 400), pk_at(d, 432), pk_at(d, 336), pk_at(d, 368), vec![], false),
            Venue::RayCpmm if d.len() >= 413 => (pk_at(d, 168), pk_at(d, 200), pk_at(d, 72), pk_at(d, 104), vec![pk_at(d, 8).unwrap()], false),
            Venue::PumpSwap if d.len() >= 253 => {
                let base = pk_at(d, 43).unwrap();
                let canonical = pk_at(d, 11) == Some(pda::find_program_address(&[b"pool-authority", &base], &PUMP_FUN).0);
                (Some(base), pk_at(d, 75), pk_at(d, 139), pk_at(d, 171), vec![base], canonical)
            }
            // DAMM v2: mints and vaults straight from the pool (t0 = token a, t1 = token b: the program's own order)
            Venue::DammV2 => match crate::venues::dammv2::decode(d) {
                Some(p) => (Some(p.token_a_mint), Some(p.token_b_mint), Some(p.token_a_vault), Some(p.token_b_vault), vec![], false),
                None => continue,
            },
            Venue::Dlmm if d.len() >= 904 => {
                let ext = pda::find_program_address(&[b"bitmap", pool], &venue.program()).0;
                (pk_at(d, 88), pk_at(d, 120), pk_at(d, 152), pk_at(d, 184), vec![ext], false)
            }
            _ => continue,
        };
        let (Some(t0), Some(t1), Some(v0), Some(v1)) = (m.0, m.1, m.2, m.3) else { continue };
        metas.push(PoolMeta { venue: *venue, pool: *pool, t0, t1, vault0: v0, vault1: v1, t0_prog: *pda::TOKEN_PROGRAM, t1_prog: *pda::TOKEN_PROGRAM, extra: m.4, flag: m.5 });
    }
    // token programs from the mints' owners
    let mints: Vec<Pk> = metas.iter().flat_map(|m| [m.t0, m.t1]).collect::<HashSet<_>>().into_iter().collect();
    let (_, macc) = rpc.accounts(&mints).await?;
    let mut nofee: HashSet<Pk> = HashSet::default();
    let owner: HashMap<Pk, Pk> = mints.iter().zip(macc).filter_map(|(k, a)| a.map(|a| {
        if !has_transfer_fee(&a.data) { nofee.insert(*k); }
        (*k, a.owner)
    })).collect();
    for m in &mut metas {
        if let Some(o) = owner.get(&m.t0) { m.t0_prog = *o; }
        if let Some(o) = owner.get(&m.t1) { m.t1_prog = *o; }
        // DAMM v2: `flag` = neither mint charges a Token-2022 transfer fee (the quote refuses pools where it may)
        if m.venue == Venue::DammV2 { m.flag = nofee.contains(&m.t0) && nofee.contains(&m.t1); }
    }
    // a token that takes a transfer fee ("tax token", Token-2022) shrinks every leg by it; none of our quotes model it,
    // so its pools only make fake gaps (2026-10-03: exactly -100 / -300 bps per leg on such pools). Drop them.
    let before = metas.len();
    metas.retain(|m| nofee.contains(&m.t0) && nofee.contains(&m.t1));
    if metas.len() < before { eprintln!("pools: dropped {} pools whose token charges a transfer fee", before - metas.len()); }
    // DLMM: does the bitmap extension exist? (kept in extra[0] only if it does)
    let exts: Vec<Pk> = metas.iter().filter(|m| m.venue == Venue::Dlmm).map(|m| m.extra[0]).collect();
    let (_, eacc) = rpc.accounts(&exts).await?;
    let exists: HashSet<Pk> = exts.iter().zip(eacc).filter(|(_, a)| a.is_some()).map(|(k, _)| *k).collect();
    for m in metas.iter_mut().filter(|m| m.venue == Venue::Dlmm) { m.flag = exists.contains(&m.extra[0]); }
    // index by pair; keep pairs with WSOL and 2+ pools
    let mut pairs: HashMap<(Pk, Pk), Vec<usize>> = HashMap::default();
    for (i, m) in metas.iter().enumerate() { pairs.entry(pair_key(&m.t0, &m.t1)).or_default().push(i); }
    pairs.retain(|k, v| (k.0 == *WSOL || k.1 == *WSOL) && v.len() >= 2);
    let by_pool = metas.iter().enumerate().map(|(i, m)| (m.pool, i)).collect();
    Ok(Registry { pools: metas, by_pool, pairs, seeds, ours })
}

/// A Token-2022 mint with a TransferFeeConfig extension (type 1) whose older or newer fee is non-zero. Mint base 82
/// bytes, padding to 165, account type at 165, then TLV (u16 type, u16 length, value). SPL mints never charge one.
fn has_transfer_fee(d: &[u8]) -> bool {
    if d.len() <= 166 { return false; }
    let mut o = 166;
    while o + 4 <= d.len() {
        let (t, l) = (u16::from_le_bytes([d[o], d[o + 1]]), u16::from_le_bytes([d[o + 2], d[o + 3]]) as usize);
        if t == 0 { return false; }
        if t == 1 {
            // authorities 32 + 32, withheld u64, older {epoch u64, max u64, bps u16}, newer {epoch u64, max u64, bps u16}
            let v = &d[o + 4..(o + 4 + l).min(d.len())];
            let bps = |at: usize| v.get(at..at + 2).map_or(1, |b| u16::from_le_bytes([b[0], b[1]]));
            return bps(72 + 16) != 0 || bps(72 + 18 + 16) != 0;
        }
        o += 4 + l;
    }
    false
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
            if m.venue == Venue::PumpSwap { add(*PUMP_FEE_CONFIG, &mut s); }
        }
        s
    }
    /// Every account `static_accounts` follows, with its role (accounts.bin DICT, exec.jsonl `watched`; WP-03): pools,
    /// vaults, PumpSwap base mints, CPMM configs, the PumpSwap fee config
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
            if m.venue == Venue::PumpSwap { out.push((*PUMP_FEE_CONFIG, RoleOf { role: role::PUMP_FEE_CONFIG, pool_index: NO_POOL })); }
        }
        out
    }

    /// The extra accounts the state stream follows (WP-03 item 2), with their roles: the Clock sysvar (chain time), every
    /// DLMM pool's bitmap-extension PDA whether or not it exists (an update arrives if one is created), the programdata
    /// accounts of `programs` (upgrade detection), and the wallet with its token accounts (its WSOL account and its
    /// associated account for every registry mint: every landed transaction we pay for writes the wallet)
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
