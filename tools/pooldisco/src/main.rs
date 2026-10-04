//! pooldisco: live discovery of tokens that trade in 2+ SOL pools (AMMs and launchpad bonding curves), the
//! cross-pool price gaps between them, and who (which arbitrage signers) closes those gaps.
//!
//! Inputs (all live):
//!   * Yellowstone gRPC transactions (processed, failed included) touching pump.fun, PumpSwap, LaunchLab, DBC,
//!     DAMM v2, DLMM, Raydium CPMM and AMM v4: vault balances (CP pools), new pools from swap instructions,
//!     arbitrage detection (a tx touching 2+ pools of one token whose signer ends with no net token change).
//!   * Yellowstone gRPC account updates for the state-priced venues, filtered by owner + discriminator:
//!     pump.fun BondingCurve, LaunchLab PoolState, DBC VirtualPool, DAMM v2 Pool, DLMM LbPair.
//!   * DexScreener (latest/dex/tokens) for the other pools of every active token, RPC getMultipleAccounts to
//!     bootstrap pool state, vaults and fee configs.
//! Outputs under --out: events.jsonl (arbs, gap open/close), candidates-latest.jsonl (ranked, rewritten every
//! minute), history.jsonl (top 30 per minute), candidates.csv (every venue) and candidates-tradeable.csv (arb-lab's
//! five venues only), status.log on stdout.
mod proto;
mod ws;

use anyhow::{bail, Context, Result};
use proto::*;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet, VecDeque};
use std::io::Write;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

type Pk = [u8; 32];
fn pk(s: &str) -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }
fn b58(k: &[u8]) -> String { bs58::encode(k).into_string() }
fn to_pk(b: &[u8]) -> Option<Pk> { b.try_into().ok() }
fn u16_at(d: &[u8], o: usize) -> Option<u16> { d.get(o..o + 2).map(|b| u16::from_le_bytes([b[0], b[1]])) }
fn u32_at(d: &[u8], o: usize) -> Option<u32> { d.get(o..o + 4).map(|b| u32::from_le_bytes(b.try_into().unwrap())) }
fn i32_at(d: &[u8], o: usize) -> Option<i32> { d.get(o..o + 4).map(|b| i32::from_le_bytes(b.try_into().unwrap())) }
fn u64_at(d: &[u8], o: usize) -> Option<u64> { d.get(o..o + 8).map(|b| u64::from_le_bytes(b.try_into().unwrap())) }
fn u128_at(d: &[u8], o: usize) -> Option<u128> { d.get(o..o + 16).map(|b| u128::from_le_bytes(b.try_into().unwrap())) }
fn pk_at(d: &[u8], o: usize) -> Option<Pk> { d.get(o..o + 32).map(|b| b.try_into().unwrap()) }
fn disc(name: &str) -> [u8; 8] { let h: [u8; 32] = Sha256::digest(name.as_bytes()).into(); h[..8].try_into().unwrap() }
fn unix() -> u64 { SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs() }

fn on_curve(b: &[u8; 32]) -> bool { curve25519_dalek::edwards::CompressedEdwardsY(*b).decompress().is_some() }
fn find_pda(seeds: &[&[u8]], program: &Pk) -> Pk {
    for bump in (0..=255u8).rev() {
        let mut h = Sha256::new();
        for s in seeds { h.update(s); }
        h.update([bump]);
        h.update(program);
        h.update(b"ProgramDerivedAddress");
        let out: [u8; 32] = h.finalize().into();
        if !on_curve(&out) { return out; }
    }
    [0u8; 32]
}

#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
enum V { PumpSwap, RayCpmm, RayAmmV4, Dlmm, DammV2, PumpCurve, LaunchLab, Dbc }
impl V {
    fn name(&self) -> &'static str {
        match self { V::PumpSwap => "PumpSwap", V::RayCpmm => "RayCPMM", V::RayAmmV4 => "RayAMMv4", V::Dlmm => "DLMM",
            V::DammV2 => "DAMMv2", V::PumpCurve => "PumpCurve", V::LaunchLab => "LaunchLab", V::Dbc => "DBC" }
    }
    fn tradeable(&self) -> bool { matches!(self, V::PumpSwap | V::RayCpmm | V::RayAmmV4 | V::Dlmm | V::DammV2) }
}

struct Ids {
    pumpfun: Pk, pumpswap: Pk, launchlab: Pk, dbc: Pk, dammv2: Pk, dlmm: Pk, cpmm: Pk, ammv4: Pk, wsol: Pk,
    token: Pk, token22: Pk, pfee: Pk,
    d_curve: [u8; 8], d_ll_pool: [u8; 8], d_dbc_pool: [u8; 8], d_dbc_cfg: [u8; 8], d_damm_pool: [u8; 8], d_lbpair: [u8; 8],
    aggregators: HashSet<Pk>,
}
impl Ids {
    fn new() -> Ids {
        Ids {
            pumpfun: pk("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"), pumpswap: pk("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"),
            launchlab: pk("LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj"), dbc: pk("dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN"),
            dammv2: pk("cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"), dlmm: pk("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"),
            cpmm: pk("CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"), ammv4: pk("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"),
            wsol: pk("So11111111111111111111111111111111111111112"), token: pk("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"),
            token22: pk("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"), pfee: pk("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"),
            d_curve: disc("account:BondingCurve"), d_ll_pool: disc("account:PoolState"), d_dbc_pool: disc("account:VirtualPool"),
            d_dbc_cfg: disc("account:PoolConfig"), d_damm_pool: disc("account:Pool"), d_lbpair: disc("account:LbPair"),
            aggregators: ["JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4", "6m2CDdhRgxpH4WjvdzxAYbGxwdGUz5MziiL5jek2kBma",
                "DF1ow4tspfHX9JwWJsAb9epbkA8hmpSEAtxXy1V27QBH", "proVF4pMXVaYqmy4NjniPLsJ9cKCuDAh4p6g1bbHn8d",
                "T1TANpTeScyeqVzzgNViGDNrkQ6qHz9KrSBS4aNXvGT", "routeUGWgWzqBWFcrCfv8tritsqukccJPu3q5GPP3xS"].iter().map(|s| pk(s)).collect(),
        }
    }
    fn venue_of_owner(&self, o: &Pk) -> Option<V> {
        if *o == self.pumpswap { Some(V::PumpSwap) } else if *o == self.cpmm { Some(V::RayCpmm) } else if *o == self.ammv4 { Some(V::RayAmmV4) }
        else if *o == self.dlmm { Some(V::Dlmm) } else if *o == self.dammv2 { Some(V::DammV2) } else if *o == self.pumpfun { Some(V::PumpCurve) }
        else if *o == self.launchlab { Some(V::LaunchLab) } else if *o == self.dbc { Some(V::Dbc) } else { None }
    }
}

#[derive(Clone, Default)]
struct PumpFeeCfg { flat: (u64, u64, u64), tiers: Vec<(u128, (u64, u64, u64))> }
fn decode_pump_fee_cfg(d: &[u8]) -> Option<PumpFeeCfg> {
    let mut o = 41;
    let fees = |o: &mut usize| -> Option<(u64, u64, u64)> { let f = (u64_at(d, *o)?, u64_at(d, *o + 8)?, u64_at(d, *o + 16)?); *o += 24; Some(f) };
    let flat = fees(&mut o)?;
    let n = u32_at(d, o)? as usize; o += 4;
    let mut tiers = vec![];
    for _ in 0..n.min(64) { let th = u128_at(d, o)?; o += 16; tiers.push((th, fees(&mut o)?)); }
    Some(PumpFeeCfg { flat, tiers })
}

/// One SOL-paired pool. Prices are lamports per raw token unit; depth is the CP-equivalent SOL reserve (lamports).
struct Pool {
    venue: V, mint: Pk,
    vault_sol: Option<Pk>, vault_tok: Option<Pk>, r_sol: Option<f64>, r_tok: Option<f64>,
    owed_sol: f64, owed_tok: f64, virt_sol: f64, virt_tok: f64,
    price: f64, depth: f64, fee: f64, live: bool, state_ok: bool,
    // venue extras
    fee_cfg: Option<Pk>, canonical: bool, creator_fee: bool, ammv4_fee: f64,
    last_slot: u64, txs: u64, updates: u64,
}
impl Pool {
    fn new(venue: V, mint: Pk) -> Pool {
        Pool { venue, mint, vault_sol: None, vault_tok: None, r_sol: None, r_tok: None, owed_sol: 0.0, owed_tok: 0.0, virt_sol: 0.0, virt_tok: 0.0,
            price: 0.0, depth: 0.0, fee: 0.0, live: false, state_ok: false, fee_cfg: None, canonical: false, creator_fee: false, ammv4_fee: 0.0025,
            last_slot: 0, txs: 0, updates: 0 }
    }
}

#[derive(Default)]
struct GapOpen { slot: u64, t: Option<Instant>, g_max: f64, est_max: f64, pair: (Pk, Pk), confirmed: bool }

#[derive(Default)]
struct MintStat {
    pools: Vec<Pk>, first: Option<Instant>, txs: u64, swaps_by_pool: HashMap<Pk, u64>,
    arb_ok: u64, arb_fail: u64, arb_profit: i64, signers_ok: HashMap<Pk, u64>, signers_fail: HashMap<Pk, u64>, progs: HashMap<Pk, u64>,
    profit_by_signer: HashMap<Pk, i64>,
    gap: Option<GapOpen>, gap_opens: u64, gap_slots: u64, gap_secs: f64, gap_est_sum: f64, gap_g_max: f64,
    closes_arb: u64, closes_other: u64, closers: HashMap<Pk, u64>, dex_looked: bool, unconfirmed: u64, arb_slots: VecDeque<(u64, Pk)>,
}

enum Msg {
    Tx(u64, TxInfo),
    Acct(u64, Pk, Pk, Vec<u8>, Option<Vec<u8>>),
    Fetched(Vec<(Pk, Option<(Pk, Vec<u8>)>)>),
    Dex(Vec<(String, String)>),
}

struct BotTags { m: HashMap<Pk, (u32, String)> }

struct St {
    ids: Ids, out: String, t0: Instant, slot: u64,
    pools: HashMap<Pk, Pool>, vault_of: HashMap<Pk, Pk>, mints: HashMap<Pk, MintStat>, curve_mint: HashMap<Pk, Pk>,
    pending_curve: HashMap<Pk, (u64, Vec<u8>)>, mint_seen: HashMap<Pk, u32>, requested: HashSet<Pk>,
    dbc_cfg: HashMap<Pk, Vec<u8>>, cpmm_cfg: HashMap<Pk, f64>, waiting_cfg: HashMap<Pk, Vec<(Pk, u64, Vec<u8>)>>,
    pump_fee: Option<PumpFeeCfg>, pump_fee_key: Pk,
    fetch_tx: tokio::sync::mpsc::UnboundedSender<Pk>, dex_tx: tokio::sync::mpsc::UnboundedSender<Pk>,
    recent: HashMap<u128, (Pk, bool)>, recent_q: VecDeque<u128>, pending_close: Vec<(Pk, u64, u64)>, polling: bool, ctr: std::sync::Arc<ws::Counters>,
    events: std::io::BufWriter<std::fs::File>, bots: BotTags,
    n_tx: u64, n_tx_fail: u64, n_acct: u64, n_arb: u64, n_gap: u64, n_fetch: u64, n_dex: u64, n_drop: u64,
}

const OPEN_G: f64 = 0.0005; // 5 bp net of both pools' fees
const OPEN_EST: f64 = 100_000.0; // 0.0001 SOL estimated optimal profit
const CLOSE_G: f64 = 0.0002;
const MIN_DEPTH: f64 = 300_000_000.0; // 0.3 SOL CP-equivalent SOL reserve
const MAX_G: f64 = 0.30;

fn sig_key(s: &[u8]) -> u128 { u128::from_le_bytes(s.get(..16).map(|b| b.try_into().unwrap()).unwrap_or([0; 16])) }

impl St {
    fn event(&mut self, v: Value) { let _ = writeln!(self.events, "{}", v); }

    fn see_mint(&mut self, mint: &Pk) {
        if *mint == self.ids.wsol { return; }
        let c = { let c = self.mint_seen.entry(*mint).or_insert(0); *c += 1; *c };
        if c == 1 {
            // the pump.fun curve address of every token we see, so curve account updates can be attributed
            let curve = find_pda(&[b"bonding-curve", mint], &self.ids.pumpfun);
            self.curve_mint.insert(curve, *mint);
            if let Some((slot, data)) = self.pending_curve.remove(&curve) { self.state_update(slot, curve, self.ids.pumpfun, &data, None); }
        }
        if c == 3 { let _ = self.dex_tx.send(*mint); }
    }

    fn fetch(&mut self, k: Pk) { if self.requested.insert(k) { self.n_fetch += 1; let _ = self.fetch_tx.send(k); } }

    fn register(&mut self, pool: Pk, p: Pool) -> bool {
        let mint = p.mint;
        if let Some(v) = p.vault_sol { self.vault_of.insert(v, pool); }
        if let Some(v) = p.vault_tok { self.vault_of.insert(v, pool); }
        let is_new = !self.pools.contains_key(&pool);
        self.pools.insert(pool, p);
        if is_new {
            let st = self.mints.entry(mint).or_default();
            if st.first.is_none() { st.first = Some(Instant::now()); }
            st.pools.push(pool);
            let n = st.pools.len();
            let looked = st.dex_looked;
            // a token with a second pool: find its curves too (PDAs) and every other pool (DexScreener)
            if n == 2 || (n == 1 && self.pools[&pool].venue != V::PumpCurve) {
                let curve = find_pda(&[b"bonding-curve", &mint], &self.ids.pumpfun);
                self.curve_mint.insert(curve, mint);
                self.fetch(curve);
                let ll = find_pda(&[b"pool", &mint, &self.ids.wsol], &self.ids.launchlab);
                self.fetch(ll);
                if !looked { self.mints.get_mut(&mint).unwrap().dex_looked = true; let _ = self.dex_tx.send(mint); }
            }
        }
        is_new
    }

    /// state-priced venues (account stream or RPC bootstrap)
    fn state_update(&mut self, slot: u64, key: Pk, owner: Pk, d: &[u8], txn: Option<&[u8]>) {
        let ids = &self.ids;
        if d.len() < 8 { return; }
        let dd: [u8; 8] = d[..8].try_into().unwrap();
        let wsol = ids.wsol;
        let (venue, mint, price, depth, fee, live) = if owner == ids.pumpfun && dd == ids.d_curve {
            let Some(mint) = self.curve_mint.get(&key).copied() else {
                if self.pending_curve.len() < 200_000 { self.pending_curve.insert(key, (slot, d.to_vec())); }
                return;
            };
            let (vt, vq) = (u64_at(d, 8).unwrap_or(0) as f64, u64_at(d, 16).unwrap_or(0) as f64);
            let complete = d.get(48).copied().unwrap_or(1) != 0;
            if d.len() >= 115 { if let Some(q) = pk_at(d, 83) { if q != [0u8; 32] && q != wsol { return; } } }
            let creator = pk_at(d, 49).map_or(false, |c| c != [0u8; 32]);
            if vt <= 0.0 { return; }
            (V::PumpCurve, mint, vq / vt, vq, if creator { 0.0125 } else { 0.0095 }, !complete)
        } else if owner == ids.launchlab && dd == ids.d_ll_pool {
            let (Some(base), Some(quote)) = (pk_at(d, 205), pk_at(d, 237)) else { return };
            if quote != wsol { return; }
            let (va, vb, ra, rb) = (u64_at(d, 37).unwrap_or(0) as f64, u64_at(d, 45).unwrap_or(0) as f64, u64_at(d, 53).unwrap_or(0) as f64, u64_at(d, 61).unwrap_or(0) as f64);
            if va - ra <= 0.0 { return; }
            (V::LaunchLab, base, (vb + rb) / (va - ra), vb + rb, 0.0125, d.get(17).copied() == Some(0))
        } else if owner == ids.dbc && dd == ids.d_dbc_pool {
            let (Some(cfg), Some(base)) = (pk_at(d, 72), pk_at(d, 136)) else { return };
            let Some(c) = self.dbc_cfg.get(&cfg) else {
                self.waiting_cfg.entry(cfg).or_default().push((key, slot, d.to_vec()));
                self.fetch(cfg);
                return;
            };
            if pk_at(c, 8) != Some(wsol) { return; }
            let sp = u128_at(d, 280).unwrap_or(0) as f64;
            let spr = sp / 18446744073709551616.0;
            let price = spr * spr;
            // active segment liquidity
            let mut liq = 0.0;
            for i in 0..20 {
                let (s, l) = (u128_at(c, 408 + 32 * i).unwrap_or(0), u128_at(c, 424 + 32 * i).unwrap_or(0));
                if s == 0 { break; }
                if (s as f64) >= sp { liq = l as f64; break; }
            }
            let depth = liq * sp / 3.402823669209385e38;
            // base fee: cliff with the time scheduler (modes 0 linear, 1 exponential); anything else = cliff
            let (cliff, second, third, first, mode) = (u64_at(c, 104).unwrap_or(0) as f64, u64_at(c, 112).unwrap_or(0), u64_at(c, 120).unwrap_or(0) as f64,
                u16_at(c, 128).unwrap_or(0) as u64, c.get(130).copied().unwrap_or(0));
            let act_type = c.get(234).copied().unwrap_or(0);
            let act = u64_at(d, 296).unwrap_or(0);
            let now = if act_type == 0 { slot } else { unix() };
            let num = if second > 0 && (mode == 0 || mode == 1) {
                let period = if now < act { first } else { ((now - act) / second).min(first) } as f64;
                if mode == 0 { (cliff - third * period).max(0.0) } else { cliff * (1.0 - third / 1e4).powf(period) }
            } else { cliff };
            let migrated = d.get(305).copied().unwrap_or(0) != 0;
            (V::Dbc, base, price, depth, (num / 1e9).min(0.99), !migrated)
        } else if owner == ids.dammv2 && dd == ids.d_damm_pool && d.len() >= 700 {
            let (Some(a), Some(b)) = (pk_at(d, 168), pk_at(d, 200)) else { return };
            if a != wsol && b != wsol { return; }
            let sp = u128_at(d, 456).unwrap_or(0) as f64;
            let l = u128_at(d, 360).unwrap_or(0) as f64;
            if sp <= 0.0 { return; }
            let spr = sp / 18446744073709551616.0;
            let p_ba = spr * spr; // token b per token a (raw)
            let (mint, price, depth) = if b == wsol { (a, p_ba, l * sp / 3.402823669209385e38) } else { (b, 1.0 / p_ba, l / sp) };
            let cliff = u64_at(d, 8).unwrap_or(0) as f64;
            let mode = d[16];
            let nper = u16_at(d, 22).unwrap_or(0) as f64;
            let red = u64_at(d, 32).unwrap_or(0) as f64;
            let act = u64_at(d, 472).unwrap_or(0);
            let now = if d[480] == 0 { slot } else { unix() };
            let num = match mode {
                0 | 1 => {
                    let freq = u64_at(d, 24).unwrap_or(0);
                    if freq == 0 { cliff } else {
                        let period = if now < act { nper } else { (((now - act) / freq) as f64).min(nper) };
                        if mode == 0 { (cliff - red * period).max(0.0) } else { cliff * (1.0 - red / 1e4).powf(period) }
                    }
                }
                3 | 4 => {
                    let init = u128_at(d, 152).unwrap_or(0) as f64;
                    let step = u32_at(d, 24).unwrap_or(0) as f64;
                    let exp = u32_at(d, 28).unwrap_or(0) as u64;
                    let period = if now > act + exp || now < act { nper } else if sp <= init || step == 0.0 { 0.0 } else { ((sp - init) * 1e4 / init / step).floor().min(nper) };
                    if mode == 3 { (cliff - red * period).max(0.0) } else { cliff * (1.0 - red / 1e4).powf(period) }
                }
                _ => cliff,
            };
            (V::DammV2, mint, price, depth, (num / 1e9).min(0.99), d[481] == 0)
        } else if owner == ids.dlmm && dd == ids.d_lbpair && d.len() >= 216 {
            let (Some(x), Some(y)) = (pk_at(d, 88), pk_at(d, 120)) else { return };
            if x != wsol && y != wsol { return; }
            let active = i32_at(d, 76).unwrap_or(0) as f64;
            let bs = u16_at(d, 80).unwrap_or(0) as f64;
            let p_yx = (1.0 + bs / 1e4).powf(active);
            let base_factor = u16_at(d, 8).unwrap_or(0) as f64;
            let power = d[34] as i32;
            let fee = base_factor * bs * 10.0 * 10f64.powi(power) / 1e9;
            let (mint, price, vsol) = if y == wsol { (x, p_yx, pk_at(d, 184)) } else { (y, 1.0 / p_yx, pk_at(d, 152)) };
            // depth: 20% of the SOL reserve (rough: liquidity is spread over bins; DLMM estimates are coarse)
            let mut depth = 0.0;
            if let Some(p) = self.pools.get(&key) { if let Some(r) = p.r_sol { depth = 0.2 * r; } }
            if !self.pools.contains_key(&key) {
                let mut p = Pool::new(V::Dlmm, mint);
                p.vault_sol = vsol;
                self.register(key, p);
                if let Some(v) = vsol { self.fetch(v); }
            }
            (V::Dlmm, mint, price, depth, fee.min(0.99), true)
        } else { return };
        if !price.is_finite() || price <= 0.0 { return; }
        if !self.pools.contains_key(&key) { self.register(key, Pool::new(venue, mint)); }
        let p = self.pools.get_mut(&key).unwrap();
        p.price = price; p.fee = fee; p.live = live; p.state_ok = true; p.last_slot = slot; p.updates += 1;
        if venue != V::Dlmm { p.depth = depth; } else if depth > 0.0 { p.depth = depth; }
        self.n_acct += 1;
        let closer = txn.map(sig_key);
        self.gap_check(&mint, slot, closer, None, None);
    }

    /// CP pools priced from vault balances
    fn reprice_vault_pool(&mut self, key: &Pk) {
        let pump_fee = self.pump_fee.clone();
        let cpmm_cfg = &self.cpmm_cfg;
        let Some(p) = self.pools.get_mut(key) else { return };
        let (Some(rs), Some(rt)) = (p.r_sol, p.r_tok) else { return };
        let s = rs - p.owed_sol + p.virt_sol;
        let t = rt - p.owed_tok + p.virt_tok;
        if s <= 0.0 || t <= 0.0 { return; }
        p.price = s / t; p.depth = s; p.state_ok = true; p.live = true;
        p.fee = match p.venue {
            V::RayAmmV4 => p.ammv4_fee,
            V::RayCpmm => p.fee_cfg.and_then(|c| cpmm_cfg.get(&c).copied()).unwrap_or(0.0025),
            V::PumpSwap => {
                let f = match &pump_fee {
                    Some(cfg) if p.canonical && !cfg.tiers.is_empty() => {
                        // market cap in lamports with a 1e15 raw supply (pump.fun's 1B x 6 decimals)
                        let mc = (s / t * 1e15) as u128;
                        let mut f = cfg.tiers[0].1;
                        for i in (1..cfg.tiers.len()).rev() { if mc >= cfg.tiers[i].0 { f = cfg.tiers[i].1; break; } }
                        f
                    }
                    Some(cfg) => cfg.flat,
                    None => (20, 5, 5),
                };
                (f.0 + f.1 + if p.creator_fee { f.2 } else { 0 }) as f64 / 1e4
            }
            _ => p.fee,
        };
    }

    fn on_fetched(&mut self, items: Vec<(Pk, Option<(Pk, Vec<u8>)>)>) {
        for (key, v) in items {
            let Some((owner, d)) = v else { continue };
            if owner == self.ids.token || owner == self.ids.token22 {
                if let (Some(pool), Some(amt)) = (self.vault_of.get(&key).copied(), u64_at(&d, 64)) {
                    if let Some(p) = self.pools.get_mut(&pool) {
                        if p.vault_sol == Some(key) { p.r_sol = Some(amt as f64); if p.venue == V::Dlmm { p.depth = 0.2 * amt as f64; } }
                        if p.vault_tok == Some(key) { p.r_tok = Some(amt as f64); }
                    }
                    // both vaults of a CP pool come in the same batch; check once, on the token vault (DLMM: its SOL vault)
                    let last = self.pools.get(&pool).map_or(false, |p| p.vault_tok == Some(key) || p.venue == V::Dlmm);
                    if last {
                        if self.pools.get(&pool).map_or(false, |p| p.venue != V::Dlmm) { self.reprice_vault_pool(&pool); }
                        if let Some(mint) = self.pools.get(&pool).map(|p| p.mint) { let slot = self.slot; self.gap_check(&mint, slot, None, None, Some(pool)); }
                    }
                }
                continue;
            }
            if key == self.pump_fee_key { self.pump_fee = decode_pump_fee_cfg(&d); continue; }
            if owner == self.ids.dbc && d.len() >= 8 && d[..8] == self.ids.d_dbc_cfg {
                self.dbc_cfg.insert(key, d.clone());
                if let Some(w) = self.waiting_cfg.remove(&key) { for (pool, slot, pd) in w { self.state_update(slot, pool, self.ids.dbc, &pd, None); } }
                continue;
            }
            if owner == self.ids.cpmm && d.len() >= 20 && d.len() < 300 {
                // amm_config: trade_fee_rate @12 (/1e6)
                if let Some(r) = u64_at(&d, 12) { self.cpmm_cfg.insert(key, r as f64 / 1e6); }
                continue;
            }
            let Some(venue) = self.ids.venue_of_owner(&owner) else { continue };
            let wsol = self.ids.wsol;
            match venue {
                V::PumpSwap | V::RayCpmm | V::RayAmmV4 => {
                    let (t0, t1, v0, v1) = match venue {
                        V::RayAmmV4 if d.len() >= 752 => (pk_at(&d, 400), pk_at(&d, 432), pk_at(&d, 336), pk_at(&d, 368)),
                        V::RayCpmm if d.len() >= 413 => (pk_at(&d, 168), pk_at(&d, 200), pk_at(&d, 72), pk_at(&d, 104)),
                        V::PumpSwap if d.len() >= 203 => (pk_at(&d, 43), pk_at(&d, 75), pk_at(&d, 139), pk_at(&d, 171)),
                        _ => continue,
                    };
                    let (Some(t0), Some(t1), Some(v0), Some(v1)) = (t0, t1, v0, v1) else { continue };
                    if t0 != wsol && t1 != wsol { continue; }
                    let sol0 = t0 == wsol;
                    let mint = if sol0 { t1 } else { t0 };
                    let mut p = Pool::new(venue, mint);
                    p.vault_sol = Some(if sol0 { v0 } else { v1 });
                    p.vault_tok = Some(if sol0 { v1 } else { v0 });
                    match venue {
                        V::RayAmmV4 => {
                            let (num, den) = (u64_at(&d, 176).unwrap_or(25) as f64, u64_at(&d, 184).unwrap_or(10000) as f64);
                            if den > 0.0 { p.ammv4_fee = num / den; }
                            let (pnl0, pnl1) = (u64_at(&d, 192).unwrap_or(0) as f64, u64_at(&d, 200).unwrap_or(0) as f64);
                            if sol0 { p.owed_sol = pnl0; p.owed_tok = pnl1; } else { p.owed_sol = pnl1; p.owed_tok = pnl0; }
                        }
                        V::RayCpmm => {
                            let o0 = [341, 357, 397].iter().map(|&o| u64_at(&d, o).unwrap_or(0) as f64).sum::<f64>();
                            let o1 = [349, 365, 405].iter().map(|&o| u64_at(&d, o).unwrap_or(0) as f64).sum::<f64>();
                            if sol0 { p.owed_sol = o0; p.owed_tok = o1; } else { p.owed_sol = o1; p.owed_tok = o0; }
                            p.fee_cfg = pk_at(&d, 8);
                            if let Some(c) = p.fee_cfg { if !self.cpmm_cfg.contains_key(&c) { self.fetch(c); } }
                        }
                        V::PumpSwap => {
                            let base = t0;
                            p.canonical = pk_at(&d, 11) == Some(find_pda(&[b"pool-authority", &base], &self.ids.pumpfun));
                            p.creator_fee = pk_at(&d, 211).map_or(false, |k| k != [0u8; 32]);
                            if d.len() >= 253 { let virt = u64_at(&d, 245).unwrap_or(0) as f64; if t1 == wsol { p.virt_sol = virt; } else { p.virt_tok = virt; } }
                        }
                        _ => {}
                    }
                    let (vs, vt) = (p.vault_sol.unwrap(), p.vault_tok.unwrap());
                    self.register(key, p);
                    self.fetch(vs); self.fetch(vt);
                }
                _ => { let slot = self.slot; self.state_update(slot, key, owner, &d, None); }
            }
        }
    }

    fn on_tx(&mut self, slot: u64, info: TxInfo) {
        self.slot = self.slot.max(slot);
        let (Some(t), Some(meta)) = (info.transaction.as_ref(), info.meta.as_ref()) else { return };
        let Some(m) = t.message.as_ref() else { return };
        let mut keys: Vec<Pk> = Vec::with_capacity(m.account_keys.len() + meta.loaded_writable_addresses.len() + meta.loaded_readonly_addresses.len());
        for k in m.account_keys.iter().chain(meta.loaded_writable_addresses.iter()).chain(meta.loaded_readonly_addresses.iter()) {
            match to_pk(k) { Some(k) => keys.push(k), None => return }
        }
        if keys.is_empty() { return; }
        let ok = meta.err.is_none();
        self.n_tx += 1;
        if !ok { self.n_tx_fail += 1; }
        let signer = keys[0];
        let sk = sig_key(&info.signature);
        // pool discovery from swap instructions of the vault-priced venues (top level and inner)
        let (pswap, cpmm, ammv4) = (self.ids.pumpswap, self.ids.cpmm, self.ids.ammv4);
        let mut cand: Vec<Pk> = vec![];
        {
            let mut look = |ix: &PbIx| {
                let Some(prog) = keys.get(ix.program_id_index as usize) else { return };
                let acc = |i: usize| ix.accounts.get(i).and_then(|&a| keys.get(a as usize)).copied();
                let d = &ix.data;
                if *prog == pswap && d.len() >= 8 && ix.accounts.len() >= 9 {
                    if let Some(p) = acc(0) { cand.push(p); }
                } else if *prog == cpmm && d.len() >= 8 && ix.accounts.len() >= 13 {
                    if let Some(p) = acc(3) { cand.push(p); }
                } else if *prog == ammv4 && !d.is_empty() && matches!(d[0], 9 | 11 | 16 | 17) && ix.accounts.len() >= 8 {
                    if let Some(p) = acc(1) { cand.push(p); }
                }
            };
            for ix in &m.instructions { look(ix); }
            for inn in &meta.inner_instructions { for ix in &inn.instructions { look(ix); } }
        }
        for p in cand { if !self.pools.contains_key(&p) && !self.requested.contains(&p) { self.fetch(p); } }

        // token balances: mints seen, vault reserves
        let mut touched_vault_pools: Vec<Pk> = vec![];
        for tb in &meta.post_token_balances {
            let Some(acct) = keys.get(tb.account_index as usize) else { continue };
            if ok {
                if let Some(pool) = self.vault_of.get(acct).copied() {
                    let amt: f64 = tb.ui_token_amount.as_ref().and_then(|u| u.amount.parse::<u64>().ok()).unwrap_or(0) as f64;
                    if let Some(p) = self.pools.get_mut(&pool) {
                        if p.vault_sol == Some(*acct) { p.r_sol = Some(amt); if p.venue == V::Dlmm { p.depth = 0.2 * amt; } }
                        if p.vault_tok == Some(*acct) { p.r_tok = Some(amt); }
                        p.last_slot = slot;
                        if p.venue != V::Dlmm && !touched_vault_pools.contains(&pool) { touched_vault_pools.push(pool); }
                    }
                }
            }
        }
        let mut mints_here: Vec<Pk> = vec![];
        for tb in meta.post_token_balances.iter().chain(meta.pre_token_balances.iter()) {
            if let Ok(v) = bs58::decode(&tb.mint).into_vec() { if let Ok(mk) = <Pk>::try_from(v.as_slice()) { if !mints_here.contains(&mk) { mints_here.push(mk); } } }
        }
        for mk in &mints_here { self.see_mint(mk); }

        // pools touched, grouped by token
        let mut by_mint: HashMap<Pk, Vec<Pk>> = HashMap::new();
        for k in &keys {
            if let Some(p) = self.pools.get(k) { let v = by_mint.entry(p.mint).or_default(); if !v.contains(k) { v.push(*k); } }
        }
        let mut is_arb_tx = false;
        if !by_mint.is_empty() {
            let top_progs: Vec<Pk> = m.instructions.iter().filter_map(|ix| keys.get(ix.program_id_index as usize).copied()).collect();
            let agg = top_progs.iter().any(|p| self.ids.aggregators.contains(p));
            let signer_s = b58(&signer);
            let wsol_s = b58(&self.ids.wsol);
            let sol_delta = meta.post_balances.first().copied().unwrap_or(0) as i64 - meta.pre_balances.first().copied().unwrap_or(0) as i64;
            let tok_delta = |mint_s: &str| -> i128 {
                let mut d = 0i128;
                for (sgn, list) in [(-1i128, &meta.pre_token_balances), (1, &meta.post_token_balances)] {
                    for b in list.iter().filter(|b| b.owner == signer_s && b.mint == mint_s) {
                        d += sgn * b.ui_token_amount.as_ref().and_then(|u| u.amount.parse::<i128>().ok()).unwrap_or(0);
                    }
                }
                d
            };
            let wsol_delta = tok_delta(&wsol_s) as i64;
            let main_prog = top_progs.iter().copied().find(|p| *p != pk("ComputeBudget111111111111111111111111111111") && *p != [0u8; 32]).unwrap_or([0u8; 32]);
            for (mint, pls) in &by_mint {
                for p in pls { if let Some(pp) = self.pools.get_mut(p) { pp.txs += 1; } }
                let multi = pls.len() >= 2;
                let st = self.mints.entry(*mint).or_default();
                st.txs += 1;
                for p in pls { *st.swaps_by_pool.entry(*p).or_default() += 1; }
                if !multi { continue; }
                let arb = if ok { tok_delta(&b58(mint)) == 0 && !agg } else { !agg };
                if !arb { continue; }
                is_arb_tx = true;
                let profit = sol_delta + wsol_delta;
                st.arb_slots.push_back((slot, signer)); while st.arb_slots.len() > 64 { st.arb_slots.pop_front(); }
                if ok {
                    st.arb_ok += 1; st.arb_profit += profit; *st.signers_ok.entry(signer).or_default() += 1;
                    *st.profit_by_signer.entry(signer).or_default() += profit;
                } else { st.arb_fail += 1; *st.signers_fail.entry(signer).or_default() += 1; }
                *st.progs.entry(main_prog).or_default() += 1;
                self.n_arb += 1;
                let tag = self.bots.m.get(&signer).map(|t| t.1.clone());
                let ev = json!({"ev": "arb", "slot": slot, "sig": b58(&info.signature), "ok": ok, "signer": signer_s, "tag": tag, "prog": b58(&main_prog),
                    "mint": b58(mint), "pools": pls.iter().map(|p| format!("{}:{}", self.pools[p].venue.name(), b58(p))).collect::<Vec<_>>(),
                    "profit": if ok { Some(profit) } else { None }, "fee": meta.fee, "t": unix()});
                self.event(ev);
            }
            // remember who did what (gap-closure attribution)
            self.recent.insert(sk, (signer, is_arb_tx));
            self.recent_q.push_back(sk);
            while self.recent_q.len() > 400_000 { if let Some(o) = self.recent_q.pop_front() { self.recent.remove(&o); } }
        }
        for pool in touched_vault_pools {
            self.reprice_vault_pool(&pool);
            if let Some(mint) = self.pools.get(&pool).map(|p| p.mint) { self.gap_check(&mint, slot, Some(sk), Some((signer, is_arb_tx)), None); }
        }
    }

    /// best net gap among a token's live pools; open/close gap episodes
    fn gap_check(&mut self, mint: &Pk, slot: u64, _closer: Option<u128>, closer_known: Option<(Pk, bool)>, polled: Option<Pk>) {
        let Some(st) = self.mints.get(mint) else { return };
        if st.pools.len() < 2 { return; }
        let live: Vec<(&Pk, &Pool)> = st.pools.iter().filter_map(|k| self.pools.get(k).map(|p| (k, p)))
            .filter(|(_, p)| p.live && p.state_ok && p.price > 0.0 && p.depth >= MIN_DEPTH).collect();
        if live.len() < 2 { return; }
        let mut best = (f64::MIN, 0.0, ([0u8; 32], [0u8; 32]));
        for i in 0..live.len() {
            for j in 0..live.len() {
                if i == j { continue; }
                let (a, b) = (live[i].1, live[j].1); // buy on a (cheap), sell on b
                if a.price >= b.price { continue; }
                let g = b.price / a.price * (1.0 - a.fee) * (1.0 - b.fee) - 1.0;
                // gaps over 30% are almost always dead/broken pools or transfer-fee tokens: kept out of scoring
                if g > MAX_G { continue; }
                let est = if g > 0.0 { let x = 1.0 / (1.0 / a.depth + 1.0 / b.depth); (x * g * g / 4.0).min(0.1 * a.depth.min(b.depth)) } else { 0.0 };
                if g > best.0 { best = (g, est, (*live[i].0, *live[j].0)); }
            }
        }
        let (g, est, pair) = best;
        let now = Instant::now();
        let polled_venue = |k: &Pk| self.polling && self.pools.get(k).map_or(false, |p| matches!(p.venue, V::PumpSwap | V::RayCpmm | V::RayAmmV4));
        let pair_polled = polled_venue(&pair.0) || polled_venue(&pair.1);
        let by_poll_of = |pr: &(Pk, Pk)| polled.map_or(false, |k| k == pr.0 || k == pr.1);
        let mut ev: Option<Value> = None;
        let st = self.mints.get_mut(mint).unwrap();
        match st.gap.as_mut() {
            None => {
                if g > OPEN_G && est >= OPEN_EST {
                    // with polled vault reserves, a gap only counts once a fresh poll of its CP pool still shows it
                    let confirmed = !pair_polled || by_poll_of(&pair);
                    st.gap = Some(GapOpen { slot, t: Some(now), g_max: g, est_max: est, pair, confirmed });
                    if confirmed { st.gap_opens += 1; self.n_gap += 1; }
                }
            }
            Some(o) => {
                if !o.confirmed && by_poll_of(&o.pair) && g > OPEN_G { o.confirmed = true; st.gap_opens += 1; self.n_gap += 1; }
                if g > o.g_max { o.g_max = g; }
                if est > o.est_max { o.est_max = est; o.pair = pair; }
                if g < CLOSE_G {
                    let o = st.gap.take().unwrap();
                    let secs = o.t.map_or(0.0, |t| now.duration_since(t).as_secs_f64());
                    if !o.confirmed { st.unconfirmed += 1; return; }
                    st.gap_slots += slot.saturating_sub(o.slot); st.gap_secs += secs; st.gap_est_sum += o.est_max;
                    if o.g_max > st.gap_g_max { st.gap_g_max = o.g_max; }
                    match closer_known {
                        Some((s, true)) => { st.closes_arb += 1; *st.closers.entry(s).or_default() += 1; }
                        _ => self.pending_close.push((*mint, o.slot, slot)),
                    }
                    ev = Some(json!({"ev": "gap", "mint": b58(mint), "open_slot": o.slot, "close_slot": slot, "secs": (secs * 1000.0).round() / 1000.0,
                        "g_bp": (o.g_max * 1e4).round(), "est_sol": o.est_max / 1e9,
                        "buy": format!("{}:{}", self.pools.get(&o.pair.0).map_or("?", |p| p.venue.name()), b58(&o.pair.0)),
                        "sell": format!("{}:{}", self.pools.get(&o.pair.1).map_or("?", |p| p.venue.name()), b58(&o.pair.1)),
                        "closer": closer_known.map(|(s, a)| json!([b58(&s), a]))}));
                }
            }
        }
        if let Some(e) = ev { self.event(e); }
    }

    /// a closed gap counts as closed by an arbitrage if an arbitrage tx on that token landed in [open, close+2]
    fn resolve_closes(&mut self) {
        let pend = std::mem::take(&mut self.pending_close);
        for (mint, open, close) in pend {
            if self.slot < close + 25 { self.pending_close.push((mint, open, close)); continue; }
            let st = self.mints.get_mut(&mint).unwrap();
            match st.arb_slots.iter().rev().find(|(s, _)| *s >= open && *s <= close + 2) {
                Some((_, sg)) => { let sg = *sg; st.closes_arb += 1; *st.closers.entry(sg).or_default() += 1; }
                None => st.closes_other += 1,
            }
        }
    }

    /// rpc mode: refresh the vault reserves of every CP pool (and DLMM SOL reserve) of tokens with 2+ pools
    fn poll_vaults(&mut self) {
        let mut ks = vec![];
        for st in self.mints.values() {
            if st.pools.len() < 2 { continue; }
            for k in &st.pools {
                let Some(p) = self.pools.get(k) else { continue };
                if let Some(v) = p.vault_sol { ks.push(v); }
                if let Some(v) = p.vault_tok { ks.push(v); }
            }
        }
        for k in ks { let _ = self.fetch_tx.send(k); }
    }

    fn report(&mut self, final_: bool) -> Result<()> {
        self.resolve_closes();
        let _ = self.events.flush();
        let hours = (self.t0.elapsed().as_secs_f64() / 3600.0).max(1.0 / 60.0);
        let mut rows: Vec<(f64, Value, Vec<(V, Pk)>)> = vec![];
        for (mint, st) in &self.mints {
            if st.pools.len() < 2 { continue; }
            let pools: Vec<&Pool> = st.pools.iter().filter_map(|k| self.pools.get(k)).collect();
            let live_n = pools.iter().filter(|p| p.live && p.state_ok).count();
            if live_n < 2 && st.arb_ok + st.arb_fail == 0 { continue; }
            let mut open_est = 0.0;
            if let Some(o) = &st.gap { open_est = o.est_max; }
            let gap_sol = (st.gap_est_sum + open_est) / 1e9;
            let arb_sol = st.arb_profit.max(0) as f64 / 1e9;
            let opp_h = gap_sol.max(arb_sol) / hours;
            let mut comp: HashSet<Pk> = st.signers_ok.keys().copied().collect();
            comp.extend(st.signers_fail.keys().copied());
            let n_comp = comp.len();
            let score = opp_h / (1.0 + n_comp as f64);
            let mut signers: Vec<(Pk, u64, u64, i64)> = comp.iter().map(|s| (*s, *st.signers_ok.get(s).unwrap_or(&0), *st.signers_fail.get(s).unwrap_or(&0), *st.profit_by_signer.get(s).unwrap_or(&0))).collect();
            signers.sort_by(|a, b| (b.1 + b.2).cmp(&(a.1 + a.2)));
            let tagged = |s: &Pk| self.bots.m.get(s).map(|t| t.1.clone()).unwrap_or_default();
            let mriya = comp.iter().any(|s| self.bots.m.get(s).map_or(false, |t| t.1 == "mriya"));
            let top20 = comp.iter().any(|s| self.bots.m.get(s).map_or(false, |t| t.0 <= 20));
            let tradeable_live = pools.iter().filter(|p| p.venue.tradeable() && p.live && p.state_ok).count();
            let mut progs: Vec<(&Pk, &u64)> = st.progs.iter().collect();
            progs.sort_by(|a, b| b.1.cmp(a.1));
            let pv: Vec<Value> = st.pools.iter().filter_map(|k| self.pools.get(k).map(|p| json!({"venue": p.venue.name(), "pool": b58(k), "live": p.live && p.state_ok,
                "fee_bp": (p.fee * 1e5).round() / 10.0, "depth_sol": (p.depth / 1e7).round() / 100.0, "price": p.price, "txs": st.swaps_by_pool.get(k).copied().unwrap_or(0)}))).collect();
            let closers_v: Vec<Value> = { let mut c: Vec<(&Pk, &u64)> = st.closers.iter().collect(); c.sort_by(|a, b| b.1.cmp(a.1)); c.iter().take(3).map(|(s, n)| json!([b58(*s), n, tagged(s)])).collect() };
            let v = json!({"mint": b58(mint), "score": (score * 1e4).round() / 1e4, "opp_sol_h": (opp_h * 1e4).round() / 1e4,
                "gap_opens": st.gap_opens, "gap_open_now": st.gap.is_some(), "gap_est_sol": (gap_sol * 1e4).round() / 1e4, "gap_max_bp": (st.gap_g_max.max(st.gap.as_ref().map_or(0.0, |o| o.g_max)) * 1e4).round(),
                "gap_secs": st.gap_secs.round(), "gap_unconfirmed": st.unconfirmed, "closes_by_arb": st.closes_arb,
                "closers": closers_v, "closes_other": st.closes_other,
                "arb_ok": st.arb_ok, "arb_fail": st.arb_fail, "arb_profit_sol": (st.arb_profit as f64 / 1e9 * 1e4).round() / 1e4,
                "competitors": n_comp, "mriya": mriya, "top20": top20,
                "signers": signers.iter().take(6).map(|(s, o, f, p)| json!({"s": b58(s), "ok": o, "fail": f, "profit_sol": (*p as f64 / 1e9 * 1e4).round() / 1e4, "tag": tagged(s)})).collect::<Vec<_>>(),
                "progs": progs.iter().take(4).map(|(p, n)| json!([b58(*p), n])).collect::<Vec<_>>(),
                "txs": st.txs, "pools": pv, "tradeable_live_pools": tradeable_live,
                "age_min": st.first.map_or(0.0, |t| (t.elapsed().as_secs_f64() / 60.0).round())});
            let vk: Vec<(V, Pk)> = st.pools.iter().filter_map(|k| self.pools.get(k).map(|p| (p.venue, *k))).collect();
            rows.push((score, v, vk));
        }
        rows.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
        let dir = &self.out;
        let mut f = std::io::BufWriter::new(std::fs::File::create(format!("{dir}/candidates-latest.jsonl.tmp"))?);
        for r in &rows { writeln!(f, "{}", r.1)?; }
        drop(f);
        std::fs::rename(format!("{dir}/candidates-latest.jsonl.tmp"), format!("{dir}/candidates-latest.jsonl"))?;
        let mut h = std::fs::OpenOptions::new().create(true).append(true).open(format!("{dir}/history.jsonl"))?;
        writeln!(h, "{}", json!({"t": unix(), "final": final_, "minutes": (self.t0.elapsed().as_secs_f64() / 60.0).round(), "top": rows.iter().take(30).map(|r| r.1.clone()).collect::<Vec<_>>()}))?;
        // seed CSVs: candidates with real opportunity (gap episodes or observed arbs)
        let mut all = String::from("venue,pool,source,mint,score,opp_sol_h,competitors,mriya,top20\n");
        let mut trad = all.clone();
        for (score, v, vk) in rows.iter() {
            if *score <= 0.0 { continue; }
            let src = format!("pooldisco,{},{},{},{},{},{}", v["mint"].as_str().unwrap_or(""), v["score"], v["opp_sol_h"], v["competitors"], v["mriya"], v["top20"]);
            let ntrad = vk.iter().filter(|(ve, _)| ve.tradeable()).count();
            for (ve, k) in vk {
                all.push_str(&format!("{},{},{}\n", ve.name(), b58(k), src));
                if ve.tradeable() && ntrad >= 2 { trad.push_str(&format!("{},{},{}\n", ve.name(), b58(k), src)); }
            }
        }
        std::fs::write(format!("{dir}/candidates.csv"), all)?;
        std::fs::write(format!("{dir}/candidates-tradeable.csv"), trad)?;
        let multi = self.mints.values().filter(|s| s.pools.len() >= 2).count();
        use std::sync::atomic::Ordering::Relaxed;
        let c = &self.ctr;
        println!("{} ws_acct={} logs={} arblike_ok={} arblike_fail={} fetched_ok={} fetched_fail={}", unix(), c.ws_acct.load(Relaxed), c.logs.load(Relaxed),
            c.arb_like_ok.load(Relaxed), c.arb_like_fail.load(Relaxed), c.fetched_ok.load(Relaxed), c.fetched_fail.load(Relaxed));
        let _ = writeln!(std::fs::OpenOptions::new().create(true).append(true).open(format!("{dir}/counters.jsonl"))?, "{}", json!({"t": unix(),
            "ws_acct": c.ws_acct.load(Relaxed), "logs": c.logs.load(Relaxed), "arblike_ok": c.arb_like_ok.load(Relaxed), "arblike_fail": c.arb_like_fail.load(Relaxed),
            "fetched_ok": c.fetched_ok.load(Relaxed), "fetched_fail": c.fetched_fail.load(Relaxed), "tx": self.n_tx, "arbs": self.n_arb, "pools": self.pools.len()}));
        println!("{} min={:.1} slot={} tx={} fail={} acct={} pools={} multi_mints={} arbs={} gap_opens={} fetch={} dex={} drop={} ranked={}",
            unix(), self.t0.elapsed().as_secs_f64() / 60.0, self.slot, self.n_tx, self.n_tx_fail, self.n_acct, self.pools.len(), multi, self.n_arb,
            self.n_gap, self.n_fetch, self.n_dex, self.n_drop, rows.len());
        Ok(())
    }
}

// ---------------- network tasks

async fn channel(url: &str) -> Result<tonic::transport::Channel> {
    use tonic::transport::{ClientTlsConfig, Endpoint};
    let mut ep = Endpoint::from_shared(url.to_string())?.tcp_nodelay(true).http2_keep_alive_interval(Duration::from_secs(10))
        .keep_alive_timeout(Duration::from_secs(20)).keep_alive_while_idle(true)
        .initial_stream_window_size(Some(16 * 1024 * 1024)).initial_connection_window_size(Some(32 * 1024 * 1024)).connect_timeout(Duration::from_secs(10));
    if url.starts_with("https://") { ep = ep.tls_config(ClientTlsConfig::new().with_webpki_roots())?; }
    Ok(ep.connect().await.with_context(|| "grpc connect")?)
}

async fn grpc_once(url: &str, token: &str, ids: &Ids, sink: &crossbeam_channel::Sender<Msg>, drops: &std::sync::atomic::AtomicU64, txsel: &str, accsel: &str) -> Result<()> {
    use tonic::codec::ProstCodec;
    let mut grpc = tonic::client::Grpc::new(channel(url).await?).max_decoding_message_size(256 * 1024 * 1024);
    grpc.ready().await.context("not ready")?;
    let named = [("pumpfun", ids.pumpfun), ("pumpswap", ids.pumpswap), ("launchlab", ids.launchlab), ("dbc", ids.dbc), ("dammv2", ids.dammv2), ("dlmm", ids.dlmm), ("cpmm", ids.cpmm), ("ammv4", ids.ammv4)];
    let progs: Vec<String> = named.iter().filter(|(n, _)| txsel == "all" || txsel.split(',').any(|x| x == *n)).map(|(_, p)| b58(p)).collect();
    let mk_acc = |owner: &Pk, d: [u8; 8]| FilterAccounts { account: vec![], owner: vec![b58(owner)],
        filters: vec![AccFilter { filter: Some(AccF::Memcmp(Memcmp { offset: 0, data: Some(MemData::Bytes(d.to_vec())) })) }] };
    let mut accounts: HashMap<String, FilterAccounts> = HashMap::from([
        ("curve".to_string(), mk_acc(&ids.pumpfun, ids.d_curve)), ("ll".to_string(), mk_acc(&ids.launchlab, ids.d_ll_pool)),
        ("dbc".to_string(), mk_acc(&ids.dbc, ids.d_dbc_pool)), ("damm".to_string(), mk_acc(&ids.dammv2, ids.d_damm_pool)),
        ("dlmm".to_string(), mk_acc(&ids.dlmm, ids.d_lbpair)),
    ]);
    accounts.retain(|k, _| accsel == "all" || accsel.split(',').any(|x| x == k));
    let transactions = if progs.is_empty() { HashMap::new() } else {
        HashMap::from([("v".to_string(), FilterTx { vote: Some(false), failed: None, account_include: progs, ..Default::default() })]) };
    let first = SubscribeRequest { accounts, transactions, commitment: Some(0), ..Default::default() };
    let (out_tx, out_rx) = tokio::sync::mpsc::channel::<SubscribeRequest>(4);
    out_tx.send(first).await.ok();
    let pinger = tokio::spawn(async move {
        loop { tokio::time::sleep(Duration::from_secs(10)).await; if out_tx.send(SubscribeRequest { ping: Some(Ping { id: 1 }), ..Default::default() }).await.is_err() { break; } }
    });
    let mut req = tonic::Request::new(tokio_stream::wrappers::ReceiverStream::new(out_rx));
    req.metadata_mut().insert("x-token", token.parse().context("token header")?);
    let codec: ProstCodec<SubscribeRequest, SubscribeUpdate> = ProstCodec::default();
    let res = async {
        let mut st = grpc.streaming(req, http::uri::PathAndQuery::from_static("/geyser.Geyser/Subscribe"), codec).await?.into_inner();
        while let Some(m) = st.message().await? {
            let msg = if let Some(u) = m.transaction {
                match u.transaction { Some(info) if !info.is_vote => Msg::Tx(u.slot, info), _ => continue }
            } else if let Some(a) = m.account {
                let Some(i) = a.account else { continue };
                let (Some(k), Some(o)) = (to_pk(&i.pubkey), to_pk(&i.owner)) else { continue };
                Msg::Acct(a.slot, k, o, i.data, i.txn_signature)
            } else { continue };
            if sink.try_send(msg).is_err() { drops.fetch_add(1, std::sync::atomic::Ordering::Relaxed); }
        }
        bail!("stream ended")
    }.await;
    pinger.abort();
    res
}

async fn fetcher(rpc: String, mut rx: tokio::sync::mpsc::UnboundedReceiver<Pk>, sink: crossbeam_channel::Sender<Msg>) {
    let cl = reqwest::Client::builder().timeout(Duration::from_secs(20)).build().unwrap();
    use base64::Engine;
    loop {
        let Some(first) = rx.recv().await else { return };
        let mut batch = vec![first];
        while batch.len() < 100 { match rx.try_recv() { Ok(k) => batch.push(k), Err(_) => break } }
        let body = json!({"jsonrpc": "2.0", "id": 1, "method": "getMultipleAccounts",
            "params": [batch.iter().map(|k| b58(k)).collect::<Vec<_>>(), {"encoding": "base64", "commitment": "processed"}]});
        let mut out = vec![];
        for attempt in 0..3 {
            let r = async { cl.post(&rpc).json(&body).send().await?.json::<Value>().await }.await;
            match r {
                Ok(v) if v["result"]["value"].is_array() => {
                    for (k, a) in batch.iter().zip(v["result"]["value"].as_array().unwrap()) {
                        if a.is_null() { out.push((*k, None)); continue; }
                        let owner = a["owner"].as_str().and_then(|s| bs58::decode(s).into_vec().ok()).and_then(|v| to_pk(&v));
                        let data = a["data"][0].as_str().and_then(|s| base64::engine::general_purpose::STANDARD.decode(s).ok());
                        out.push((*k, owner.zip(data)));
                    }
                    break;
                }
                _ => { tokio::time::sleep(Duration::from_millis(500 * (attempt + 1))).await; }
            }
        }
        if !out.is_empty() { let _ = sink.send(Msg::Fetched(out)); }
        tokio::time::sleep(Duration::from_millis(120)).await;
    }
}

async fn dexscreener(mut rx: tokio::sync::mpsc::UnboundedReceiver<Pk>, sink: crossbeam_channel::Sender<Msg>) {
    let cl = reqwest::Client::builder().timeout(Duration::from_secs(15)).build().unwrap();
    let mut q: VecDeque<Pk> = VecDeque::new();
    loop {
        tokio::time::sleep(Duration::from_millis(1100)).await;
        while let Ok(k) = rx.try_recv() { if q.len() < 20_000 { q.push_back(k); } }
        if q.is_empty() { continue; }
        let batch: Vec<String> = (0..10).filter_map(|_| q.pop_front()).map(|k| b58(&k)).collect();
        let url = format!("https://api.dexscreener.com/latest/dex/tokens/{}", batch.join(","));
        let Ok(r) = cl.get(&url).send().await else { continue };
        let Ok(v) = r.json::<Value>().await else { continue };
        let mut out = vec![];
        for p in v["pairs"].as_array().cloned().unwrap_or_default() {
            if p["chainId"] != "solana" { continue; }
            let (b, qa) = (p["baseToken"]["address"].as_str().unwrap_or(""), p["quoteToken"]["address"].as_str().unwrap_or(""));
            let sol = "So11111111111111111111111111111111111111112";
            if b != sol && qa != sol { continue; }
            let mint = if b == sol { qa } else { b };
            out.push((mint.to_string(), p["pairAddress"].as_str().unwrap_or("").to_string()));
        }
        if !out.is_empty() { let _ = sink.send(Msg::Dex(out)); }
    }
}

fn env_file(path: &str) -> HashMap<String, String> {
    std::fs::read_to_string(path).unwrap_or_default().lines().filter(|l| !l.trim_start().starts_with('#'))
        .filter_map(|l| l.split_once('=').map(|(a, b)| (a.trim().to_string(), b.trim().trim_matches('"').to_string()))).collect()
}

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let arg = |name: &str, def: &str| -> String { args.iter().position(|a| a == name).and_then(|i| args.get(i + 1)).cloned().unwrap_or(def.to_string()) };
    let out = arg("--out", "/root/arbx/runs/discovery");
    let minutes: f64 = arg("--minutes", "45").parse()?;
    let envp = arg("--env", "/root/arbx/deploy/.env");
    let bots_path = arg("--bots", "");
    let grpc_url = arg("--grpc", "https://grpc.haandigital.eu:443");
    std::fs::create_dir_all(&out)?;
    let env = env_file(&envp);
    let token = env.get("HAAN_X_TOKEN").cloned().context("HAAN_X_TOKEN missing")?;
    let rpc = env.get("RMR_RPC_URL").cloned().context("RMR_RPC_URL missing")?;
    // bot tags: {signer: [rank_by_wins, tag]}
    let mut bots = BotTags { m: HashMap::new() };
    if !bots_path.is_empty() {
        let v: Value = serde_json::from_str(&std::fs::read_to_string(&bots_path)?)?;
        for (s, t) in v.as_object().cloned().unwrap_or_default() {
            if let Ok(k) = bs58::decode(&s).into_vec() { if let Ok(k) = Pk::try_from(k.as_slice()) {
                bots.m.insert(k, (t[0].as_u64().unwrap_or(999) as u32, t[1].as_str().unwrap_or("").to_string()));
            } }
        }
    }
    let mode = arg("--mode", "rpc");
    let ctr = std::sync::Arc::new(ws::Counters::default());
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build()?;
    let (tx, rx) = crossbeam_channel::bounded::<Msg>(300_000);
    let (fetch_tx, fetch_rx) = tokio::sync::mpsc::unbounded_channel::<Pk>();
    let (dex_tx, dex_rx) = tokio::sync::mpsc::unbounded_channel::<Pk>();
    let drops = std::sync::Arc::new(std::sync::atomic::AtomicU64::new(0));
    {
        let (tx2, d2, url, tok) = (tx.clone(), drops.clone(), grpc_url.clone(), token.clone());
        let (txsel, accsel) = (arg("--tx", "all"), arg("--acc", "all"));
        if mode == "grpc" { rt.spawn(async move {
            let ids = Ids::new();
            loop {
                if let Err(e) = grpc_once(&url, &tok, &ids, &tx2, &d2, &txsel, &accsel).await { eprintln!("{} grpc: {e:#}", unix()); }
                tokio::time::sleep(Duration::from_secs(2)).await;
            }
        }); } else {
            let ids = Ids::new();
            let wsu = rpc.replacen("https://", "wss://", 1);
            let subs = vec![(ids.pumpfun, ids.d_curve), (ids.launchlab, ids.d_ll_pool), (ids.dbc, ids.d_dbc_pool), (ids.dammv2, ids.d_damm_pool), (ids.dlmm, ids.d_lbpair)];
            rt.spawn(ws::programs(wsu.clone(), subs, tx.clone(), ctr.clone()));
            let venues: HashSet<String> = [ids.pumpfun, ids.pumpswap, ids.launchlab, ids.dbc, ids.dammv2, ids.dlmm, ids.cpmm, ids.ammv4].iter().map(|p| b58(p)).collect();
            let aggs: HashSet<String> = ids.aggregators.iter().map(|p| b58(p)).collect();
            let (stx, srx) = tokio::sync::mpsc::unbounded_channel();
            let lp = vec![ids.pumpswap, ids.dlmm, ids.dammv2, ids.cpmm, ids.ammv4, ids.launchlab, ids.dbc];
            rt.spawn(ws::logs(wsu, lp, venues, aggs, stx, ctr.clone()));
            rt.spawn(ws::gettx(rpc.clone(), srx, arg("--gettx-per-sec", "12").parse().unwrap_or(12), tx.clone(), ctr.clone()));
        }
        rt.spawn(fetcher(rpc, fetch_rx, tx.clone()));
        rt.spawn(dexscreener(dex_rx, tx.clone()));
    }
    let ids = Ids::new();
    let pump_fee_key = find_pda(&[b"fee_config", &ids.pumpswap], &ids.pfee);
    let events = std::io::BufWriter::new(std::fs::OpenOptions::new().create(true).append(true).open(format!("{out}/events.jsonl"))?);
    let mut st = St { ids, out: out.clone(), t0: Instant::now(), slot: 0, pools: HashMap::new(), vault_of: HashMap::new(), mints: HashMap::new(),
        curve_mint: HashMap::new(), pending_curve: HashMap::new(), mint_seen: HashMap::new(), requested: HashSet::new(), dbc_cfg: HashMap::new(),
        cpmm_cfg: HashMap::new(), waiting_cfg: HashMap::new(), pump_fee: None, pump_fee_key, fetch_tx, dex_tx, recent: HashMap::new(),
        recent_q: VecDeque::new(), pending_close: vec![], polling: mode != "grpc", ctr: ctr.clone(), events, bots, n_tx: 0, n_tx_fail: 0, n_acct: 0, n_arb: 0, n_gap: 0, n_fetch: 0, n_dex: 0, n_drop: 0 };
    st.fetch(pump_fee_key);
    let deadline = Instant::now() + Duration::from_secs_f64(minutes * 60.0);
    let mut next_report = Instant::now() + Duration::from_secs(60);
    let mut next_poll = Instant::now() + Duration::from_secs(5);
    loop {
        match rx.recv_timeout(Duration::from_millis(200)) {
            Ok(Msg::Tx(slot, info)) => st.on_tx(slot, info),
            Ok(Msg::Acct(slot, k, o, d, txn)) => { st.slot = st.slot.max(slot); st.state_update(slot, k, o, &d, txn.as_deref()); }
            Ok(Msg::Fetched(v)) => st.on_fetched(v),
            Ok(Msg::Dex(v)) => {
                for (_mint, pair) in v {
                    st.n_dex += 1;
                    if let Ok(k) = bs58::decode(&pair).into_vec() { if let Ok(k) = Pk::try_from(k.as_slice()) { if !st.pools.contains_key(&k) { st.fetch(k); } } }
                }
            }
            Err(_) => {}
        }
        if st.polling && Instant::now() >= next_poll { st.poll_vaults(); next_poll = Instant::now() + Duration::from_secs(3); }
        if Instant::now() >= next_report {
            st.n_drop = drops.load(std::sync::atomic::Ordering::Relaxed);
            if let Err(e) = st.report(false) { eprintln!("report: {e:#}"); }
            next_report = Instant::now() + Duration::from_secs(60);
            if Instant::now() >= deadline { st.report(true)?; break; }
        }
    }
    let _ = std::io::stdout().flush();
    std::process::exit(0);
}
