//! PRE-SEND LIVE (`snipe_engine --dip --presend-shadow --presend-live`; owner GO 10-25 ~07:05 PKT "ok lets do the real test"):
//! the PURE parts of the small, capped live probe of the study's pre-sent conditional buy (trigger T2 "whale buy",
//! ops/strategies/presend/REPORT.md). Its job is to MEASURE where cheap pre-sent attempts really land relative to a dump.
//! The engine wiring (sender thread, fills, exits, records, caps) is src/bin/snipe_engine/pslive.rs; flags, records and the
//! evaluator: ops/strategies/presend/LIVE.md.
//!   * `Detector`: the shadow's T2 trigger rules (src/presend.rs: first >= 3% crossing, holding >= whale_pct at THAT buy, not the
//!     creator, not a create-slot insider, curve < 100 SOL; the study's non-standard-curve filter; mayhem / no-history tokens not
//!     followed) decided on the live feed IN ARRIVAL ORDER (the shadow sorts each slot 2 slots late). It also reports a whale's
//!     first sell after its trigger (the window's end).
//!   * `limit_min_out`: an attempt's min tokens out = the buy at the curve state whose price is (1 - drop) x the latest price, on
//!     the same constant product, capped at the 100 SOL curve: pump's own slippage check (6042) fills it only at or below that
//!     price.
//!   * `Pace`: k attempts per slot, evenly spaced (a late tick does not burst).
//!   * `attempt_ixs`: one attempt = compute budget, the Lighthouse slot deadline, a NON-idempotent Token-2022 ATA create (the
//!     double-fill guard: a second success fails because the account exists; our sells close it), the idempotent WSOL ATA create
//!     (as the engine's buy), the pump buy, one tip transfer (reverted with a failed attempt: paid only on a fill).
use crate::build::{self, Ix};
use crate::pda;
use crate::snipe::Launch;
use crate::snipe_build;
use crate::tx::Pk;
use rustc_hash::FxHashMap;

/// the replay's slot length on the block-position clock (ms), as the shadow
pub const SMS: f64 = crate::presend::SMS;
/// pump.fun supply in raw units
pub const SUPPLY: f64 = crate::presend::SUPPLY;
/// a wallet becomes "big" at 3% of supply (the first crossing only)
const HX: i64 = 30_000_000_000_000;
/// no trigger and no fill at curve >= 100 SOL (lamports)
pub const UNTRADE_V: u64 = 100_000_000_000;
/// pump's slippage error of buy_exact_quote_in_v3 (min tokens out not met)
pub const ERR_SLIPPAGE: u32 = 6042;
/// fast-path write tags of attempts carry this bit (the fast-acks thread hands them to the probe instead of printing them)
pub const PS_TAG: u64 = 1 << 62;

/// one executed curve trade as the live feed delivers it (arrival order)
#[derive(Clone, Debug)]
pub struct Trade {
    pub mint: Pk, pub s: u64, pub i: u32, pub j: i32, pub sig: [u8; 64], pub user: Pk, pub buy: bool, pub sol: u64, pub tok: u64, pub vsol: u64, pub vtok: u64,
    pub fbps: u64, pub cbps: u64, pub t_rx: u64,
}

impl Trade {
    /// the post-trade curve price (lamports per raw token)
    pub fn p(&self) -> f64 { self.vsol as f64 / (self.vtok as f64).max(1.0) }
    /// the pre-trade price
    pub fn p_pre(&self) -> f64 {
        let (v, t) = if self.buy { (self.vsol.saturating_sub(self.sol), self.vtok.saturating_add(self.tok)) } else { (self.vsol.saturating_add(self.sol), self.vtok.saturating_sub(self.tok)) };
        v as f64 / (t as f64).max(1.0)
    }
    /// pump's fee rate of this trade: protocol + creator bps, 95 / 30 when the event does not carry them (the shadow's and the
    /// study's `fee_rate`; MEASURED 10-25 in simulation: an event without fee fields made the guard formula's (fbps + cbps).max(1)
    /// give 0.0001 and the limit ~1.2% too low)
    pub fn fr(&self) -> f64 { crate::presend::fee_rate(self.fbps, self.cbps) }
    /// the block-position clock of this trade (ms; `dip_model::arrival`)
    pub fn a(&self) -> f64 { crate::dip_model::arrival(self.s, self.i) }
    /// chain position
    pub fn pos(&self) -> (u64, u32, i32) { (self.s, self.i, self.j) }
}

/// what the detector saw on one trade
#[derive(Clone, Debug, PartialEq)]
pub enum Det {
    /// a T2 trigger (the shadow's `presend_arm`): `pct` = the holding at this buy (float32-rounded, as the study); `age_slots` 0 =
    /// in the create slot (the create's signer buying in its own create tx: the study code counts it; it lost on R1-R4)
    Trigger { whale: Pk, pct: f64, bal: i64, age_slots: u64 },
    /// a wallet's first >= 3% crossing that left it below whale_pct (it never triggers later)
    Below,
    /// the first sell, after its trigger, of a wallet that triggered on this token (its window ends 30 ms later)
    WhaleSell { whale: Pk },
    /// the token is no longer followed (the study's non-standard curves: one of its first 50 trades at curve < 25 / > 200 SOL)
    Gone,
}

/// a wallet on a token: its balance, its trades (dip20 QUIET: who traded before a trigger), its trigger states
#[derive(Clone, Copy, Debug, Default)]
struct Wal { bal: i64, n: u32, became: bool, ins: bool, trig: bool, sold: bool }

/// `last_tr` (dip20 QUIET): the newest slot of the token's trades (0: none yet; `last_slot` starts at the create slot)
struct DTok { s0: u64, creator: Pk, signer: Pk, n: u32, out: bool, wal: FxHashMap<Pk, Wal>, last_slot: u64, last_tr: u64 }

#[derive(Clone, Debug, Default)]
pub struct DetStats { pub creates: u64, pub mayhem: u64, pub trades: u64, pub no_hist: u64, pub excluded: u64, pub triggers: u64, pub below: u64, pub whale_sells: u64, pub retired: u64 }

/// the live T2 detector (the shadow's trigger rules, arrival order)
pub struct Detector {
    pub whale_pct: f64,
    toks: FxHashMap<Pk, DTok>,
    pub st: DetStats,
    last_retire: u64,
    /// a token with no trade for this many slots is forgotten (the shadow's 6 h)
    pub idle_slots: u64,
    /// dip20 QUIET: the token's newest trade slot BEFORE the trade `trade` took last (0: none; a followed token only): the trigger's
    /// "since_last" (apply_filter.quiet_signals: the previous trade of any wallet)
    pub prev_tr: u64,
}

impl Detector {
    pub fn new(whale_pct: f64) -> Detector {
        let mut toks = FxHashMap::default(); toks.reserve(1 << 13);
        Detector { whale_pct, toks, st: DetStats::default(), last_retire: 0, idle_slots: 6 * 3600 * 1000 / 212, prev_tr: 0 }
    }
    pub fn tokens(&self) -> usize { self.toks.len() }
    /// followed (seen from its create, not mayhem, not excluded)
    pub fn followed(&self, mint: &Pk) -> bool { self.toks.get(mint).is_some_and(|t| !t.out) }
    /// the token's create slot
    pub fn create_slot(&self, mint: &Pk) -> Option<u64> { self.toks.get(mint).map(|t| t.s0) }

    /// a pump create (its executed tx): the token is followed from here (mayhem launches are not)
    pub fn create(&mut self, mint: Pk, slot: u64, creator: Pk, signer: Pk, mayhem: bool) {
        if self.toks.contains_key(&mint) { return; }
        self.st.creates += 1;
        if mayhem { self.st.mayhem += 1; return; }
        self.toks.insert(mint, DTok { s0: slot, creator, signer, n: 0, out: false, wal: FxHashMap::default(), last_slot: slot, last_tr: 0 });
    }

    /// one executed trade, in ARRIVAL order; what it means for the probe goes to `out`
    pub fn trade(&mut self, t: &Trade, out: &mut Vec<Det>) {
        let Some(tk) = self.toks.get_mut(&t.mint) else { self.st.no_hist += 1; return };
        if tk.out { return; }
        self.st.trades += 1;
        // the study's non-standard curves (p1_build: any of the first 50 trades at curve < 25 / > 200 SOL, or no virtual tokens)
        if tk.n < 50 && (t.vsol < 25_000_000_000 || t.vsol > 200_000_000_000 || t.vtok == 0) {
            tk.out = true; tk.wal = FxHashMap::default(); self.st.excluded += 1;
            out.push(Det::Gone);
            return;
        }
        tk.n += 1;
        tk.last_slot = tk.last_slot.max(t.s);
        self.prev_tr = tk.last_tr;
        tk.last_tr = tk.last_tr.max(t.s);
        let (s0, creator, signer) = (tk.s0, tk.creator, tk.signer);
        let w = tk.wal.entry(t.user).or_default();
        w.n += 1;
        if t.buy { w.bal += t.tok as i64; } else { w.bal -= t.tok as i64; }
        if t.buy && t.s == s0 && t.user != creator && t.user != signer { w.ins = true; }
        // a triggered whale's first sell after its trigger
        if !t.buy && w.trig && !w.sold { w.sold = true; self.st.whale_sells += 1; out.push(Det::WhaleSell { whale: t.user }); }
        // the trigger (the shadow's ps4 T2 + ps6 filter): the balance AFTER this buy
        if t.buy && t.vsol < UNTRADE_V && !w.became {
            let ht = if t.user == creator { 1 } else if w.ins { 2 } else if w.bal >= HX { 3 } else { 0 };
            if ht != 0 { w.became = true; }
            if ht == 3 {
                let pct = (w.bal as f64 / SUPPLY * 100.0) as f32 as f64;
                if pct >= self.whale_pct {
                    w.trig = true;
                    self.st.triggers += 1;
                    out.push(Det::Trigger { whale: t.user, pct, bal: w.bal, age_slots: t.s.saturating_sub(s0) });
                } else { self.st.below += 1; out.push(Det::Below); }
            }
        }
    }

    /// dip20 QUIET, called right after the trigger trade went in: over the wallets that traded the token BEFORE the trigger (the
    /// whale's own trigger buy taken out of its trade count and balance), (cohort wallets holding it, follower bots that traded it)
    /// = apply_filter.quiet_signals' coh_hold / fb_n. None: the token is not followed
    pub fn holders(&self, mint: &Pk, whale: &Pk, trig_tok: u64, coh: &rustc_hash::FxHashSet<Pk>, fb: &rustc_hash::FxHashSet<Pk>) -> Option<(u32, u32)> {
        let tk = self.toks.get(mint).filter(|t| !t.out)?;
        let (mut coh_hold, mut fb_n) = (0u32, 0u32);
        for (k, w) in &tk.wal {
            let (n, bal) = if k == whale { (w.n.saturating_sub(1), w.bal - trig_tok as i64) } else { (w.n, w.bal) };
            if n == 0 { continue; }
            if bal > 0 && coh.contains(k) { coh_hold += 1; }
            if fb.contains(k) { fb_n += 1; }
        }
        Some((coh_hold, fb_n))
    }

    /// forget tokens idle for `idle_slots` (call with the feed's slot; works every 2048 slots)
    pub fn retire(&mut self, slot: u64, keep: impl Fn(&Pk) -> bool) {
        if slot < self.last_retire + 2048 { return; }
        self.last_retire = slot;
        let idle = self.idle_slots;
        let n0 = self.toks.len();
        self.toks.retain(|m, t| keep(m) || t.last_slot + idle >= slot);
        self.st.retired += (n0 - self.toks.len()) as u64;
    }
}

/// An attempt's limit: the buy of `spend` lamports (pump's fee rate `fr` on top: spend / (1 + fr) reaches the curve, the engine's
/// guard math) at the curve state whose price is (1 - drop) x the price of (vsol, vtok), on the same constant product V x T,
/// and never at a curve of 100 SOL or more (the shadow's "untradeable"). The on-chain min-out check (6042) then fills the
/// attempt iff the curve's price when it executes is at or below that limit. -> (min tokens out, limit price, the limit
/// state's virtual SOL); None: no fill possible (the limit state is at >= 100 SOL... never: it is capped; an empty curve / a
/// spend too small to buy one token).
pub fn limit_min_out(vsol: u64, vtok: u64, spend: u64, fr: f64, drop: f64) -> Option<(u64, f64, u64)> {
    // drop < 0 (a limit ABOVE the latest price) is for the simulation checks only; the engine takes 0 < drop <= 0.5
    if vsol == 0 || vtok == 0 || spend == 0 || !(drop > -1.0 && drop < 1.0) || !(fr >= 0.0 && fr < 1.0) { return None; }
    let (v, t) = (vsol as f64, vtok as f64);
    let k = v * t;
    // the limit state: price x (1 - drop) on the same curve (V x T = k): V_L = V sqrt(1 - drop), T_L = T / sqrt(1 - drop)
    let vl = (v * (1.0 - drop).sqrt()).min(UNTRADE_V as f64 - 1.0);
    let tl = k / vl;
    let x = spend as f64 / (1.0 + fr);
    let q = (tl * x / (vl + x)).floor();
    if !(q >= 1.0) { return None; }
    Some((q as u64, vl / tl, vl as u64))
}

/// the tokens a buy of `spend` (fee rate `fr` on top) gets at the curve state (vsol, vtok) (pump's constant product, floored)
pub fn buy_out(vsol: u64, vtok: u64, spend: u64, fr: f64) -> u64 {
    let x = (spend as f64 / (1.0 + fr)) as u128;
    if vsol == 0 { return 0; }
    (vtok as u128 * x / (vsol as u128 + x)) as u64
}

/// k attempts per slot, evenly spaced on the monotonic clock: due at `next`, then every `iv` ns; a tick later than one interval
/// restarts the pace from now (no burst to catch up)
#[derive(Clone, Copy, Debug)]
pub struct Pace { pub next: u64, pub iv: u64 }
impl Pace {
    /// `k` attempts per slot of `slot_ns`, the first one at `start`
    pub fn new(start: u64, k: u64, slot_ns: u64) -> Pace { Pace { next: start, iv: (slot_ns / k.clamp(1, 1000)).max(1) } }
    /// due at `now`? (then the next one is scheduled)
    pub fn due(&mut self, now: u64) -> bool {
        if now < self.next { return false; }
        self.next = if now - self.next >= self.iv { now + self.iv } else { self.next + self.iv };
        true
    }
}

/// the associated token account program's NON-idempotent Create (instruction 0): fails when the account already exists
pub fn create_ata_ix(payer: Pk, owner: Pk, mint: Pk, token_prog: Pk) -> Ix {
    let mut ix = build::create_ata_idempotent_ix(payer, owner, mint, token_prog);
    ix.data = vec![0];
    ix
}

/// the instruction indices of an attempt: (slot deadline, Token-2022 ATA create, pump buy, tip)
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct Roles { pub guard: Option<u8>, pub ata: Option<u8>, pub buy: Option<u8>, pub tip: Option<u8> }

/// One pre-sent attempt's instructions, in order: SetComputeUnitLimit, SetComputeUnitPrice, `guard` (the Lighthouse slot
/// deadline: first, so a stale attempt fails before anything else), the NON-idempotent Token-2022 ATA create of `user` for the
/// mint (the double-fill guard), the idempotent WSOL ATA create (as the engine's buy), the pump buy (spend, min tokens out),
/// one tip transfer last (`tip`: account, lamports; reverted with a failed attempt).
#[allow(clippy::too_many_arguments)]
pub fn attempt_ixs(user: Pk, l: &Launch, spend: u64, min_out: u64, cu_limit: u32, cu_price: u64, guard: Ix, tip: Option<(Pk, u64)>) -> (Vec<Ix>, Roles) {
    let mut v = Vec::with_capacity(7);
    v.push(build::cu_limit_ix(cu_limit));
    v.push(build::cu_price_ix(cu_price));
    let mut r = Roles { guard: Some(v.len() as u8), ..Default::default() };
    v.push(guard);
    r.ata = Some(v.len() as u8);
    v.push(create_ata_ix(user, user, l.mint, *pda::TOKEN_2022));
    v.push(build::create_ata_idempotent_ix(user, user, *snipe_build::WSOL, *pda::TOKEN_PROGRAM));
    r.buy = Some(v.len() as u8);
    v.push(snipe_build::buy_ix(user, l, spend, min_out, true));
    if let Some((to, lamports)) = tip { r.tip = Some(v.len() as u8); v.push(build::transfer_ix(user, to, lamports)); }
    (v, r)
}

/// An attempt's on-chain result from its transaction error (`rec::tx_error` text: "ix{N}:custom:0x{code}", "ix{N}:ie{k}",
/// "tx{k}", "" = success): "ok", "6042" (the price was above the limit), "deadline" (failed at the slot guard: landed after its
/// deadline), "ata_exists" (failed at the ATA create: we already hold the token, the double-fill guard), "buy_<code>" (another
/// error at the pump buy), "other" (anything else)
pub fn classify(err: &str, r: &Roles) -> String {
    if err.is_empty() { return "ok".into(); }
    let Some(rest) = err.strip_prefix("ix") else { return "other".into() };
    let n: Option<u8> = rest.split(':').next().and_then(|x| x.parse().ok());
    let code = rest.split(":custom:0x").nth(1).and_then(|h| u32::from_str_radix(h, 16).ok());
    if n.is_some() && n == r.guard { return "deadline".into(); }
    if n.is_some() && n == r.ata { return "ata_exists".into(); }
    if n.is_some() && n == r.buy {
        return match code { Some(ERR_SLIPPAGE) => "6042".into(), Some(c) => format!("buy_{c}"), None => format!("buy_{}", rest.split(':').nth(1).unwrap_or("?")) };
    }
    "other".into()
}

/// The send acks of attempts (the fast path's HTTP answers, the async sends' results), by write tag: (HTTP status or 0 = no
/// answer / refused before sending, ms from the write to the answer). Filled from the fast-acks thread and the async send tasks,
/// read when an attempt is resolved; bounded (the oldest go past ACKS_MAX).
type AckMap = (FxHashMap<u64, (u16, f32)>, std::collections::VecDeque<u64>);
static ACKS: std::sync::LazyLock<std::sync::Mutex<AckMap>> = std::sync::LazyLock::new(Default::default);
const ACKS_MAX: usize = 50_000;
/// per HTTP status: how many attempt acks (the status line); 0 = no answer / not sent
static ACK_COUNTS: std::sync::LazyLock<std::sync::Mutex<std::collections::BTreeMap<u16, u64>>> = std::sync::LazyLock::new(Default::default);

/// an attempt's send ack (`tag` with PS_TAG)
pub fn note_ack(tag: u64, status: Option<u16>, ms: f64) {
    let s = status.unwrap_or(0);
    *ACK_COUNTS.lock().unwrap_or_else(|e| e.into_inner()).entry(s).or_default() += 1;
    let mut g = ACKS.lock().unwrap_or_else(|e| e.into_inner());
    let (m, o) = &mut *g;
    if m.insert(tag, (s, ms as f32)).is_none() { o.push_back(tag); }
    while o.len() > ACKS_MAX { if let Some(k) = o.pop_front() { m.remove(&k); } }
}
/// the ack of the attempt written with `tag` (None: no answer yet)
pub fn ack_of(tag: u64) -> Option<(u16, f32)> { ACKS.lock().unwrap_or_else(|e| e.into_inner()).0.get(&tag).copied() }
/// acks per HTTP status so far
pub fn ack_counts() -> std::collections::BTreeMap<u16, u64> { ACK_COUNTS.lock().unwrap_or_else(|e| e.into_inner()).clone() }

/// the value of `tokens` held at curve (vsol, vtok) as a fraction of the spend (pump's fee on the sell side; the shadow's path
/// value: SOL out x (1 - fee) / size, gross)
pub fn value(vsol: u64, vtok: u64, tokens: u64, fr: f64, spend: u64) -> f64 {
    crate::dip::sell_sol_out(vsol, vtok, tokens) as f64 * (1.0 - fr) / spend.max(1) as f64
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::presend::{In, Params, Shadow};
    use serde_json::Value;
    use std::collections::{BTreeMap, HashMap, HashSet};

    fn pk(s: &str) -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }
    fn sig64(s: &str) -> [u8; 64] { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }

    /// pump's buy on the curve as the chain does it (integer constant product), for the limit tests
    fn chain_buy(v: u64, t: u64, x_net: u64) -> (u64, u64, u64) {
        let q = (t as u128 * x_net as u128 / (v as u128 + x_net as u128)) as u64;
        (q, v + x_net, t - q)
    }
    fn chain_sell(v: u64, t: u64, q: u64) -> (u64, u64) { let o = (v as u128 * q as u128 / (t as u128 + q as u128)) as u64; (v - o, t + q) }

    /// the limit math: an attempt signed at a curve state fills (its min-out is met) exactly when the curve it meets is at or below
    /// (1 - drop) x the signing price, on any curve state reached by sells (a dump) or buys; never at >= 100 SOL
    #[test]
    fn limit_min_out_fills_iff_price_at_or_below_limit() {
        let spend = 550_000_000u64; let fr = 0.0125;
        let x_net = (spend as f64 / (1.0 + fr)) as u64;
        for &(v0, t0) in &[(30_000_000_000u64, 1_073_000_000_000_000u64), (45_000_000_000, 715_333_333_333_333), (80_000_000_000, 402_375_000_000_000)] {
            for &drop in &[0.05, 0.12, 0.20] {
                let (mo, lim, vl) = limit_min_out(v0, t0, spend, fr, drop).unwrap();
                let p0 = v0 as f64 / t0 as f64;
                assert!(((lim / p0) - (1.0 - drop)).abs() < 1e-9, "the limit is (1 - drop) x the signing price");
                assert!(vl < UNTRADE_V);
                // walk the curve down by sells and up by buys: the fill decision vs the spot price before our buy
                let mut cases = 0;
                for step in 0..400u64 {
                    // sells of up to 15% of the virtual tokens: price drops of up to ~24%
                    let q = (t0 as f64 * step as f64 / 400.0 * 0.15) as u64;
                    let (v, t) = chain_sell(v0, t0, q);
                    let p = v as f64 / t as f64;
                    let (got, _, _) = chain_buy(v, t, x_net);
                    let fills = got >= mo;
                    let want = p <= lim;
                    // within 1e-6 of the limit the integer rounding may go either way
                    if (p / lim - 1.0).abs() > 1e-6 { assert_eq!(fills, want, "v0 {v0} drop {drop}: p/p0 {:.6} lim/p0 {:.6}", p / p0, lim / p0); cases += 1; }
                }
                assert!(cases > 300);
                // a buy-only path (price up): never fills
                let (_, v1, t1) = chain_buy(v0, t0, 2_000_000_000);
                assert!(chain_buy(v1, t1, x_net).0 < mo);
                // the signing state itself: no fill (the price is above the limit)
                assert!(chain_buy(v0, t0, x_net).0 < mo);
            }
        }
        // near 100 SOL: the limit is capped at the 100 SOL curve
        let (v, t) = (115_000_000_000u64, 279_913_043_478_260u64);
        let (mo, _, vl) = limit_min_out(v, t, spend, fr, 0.05).unwrap();
        assert!(vl < UNTRADE_V);
        let k = v as f64 * t as f64;
        let t100 = (k / 100e9) as u64;
        assert!(chain_buy(100_000_000_000, t100, x_net).0 < mo, "no fill at a curve of 100 SOL");
        let t99 = (k / 99e9) as u64;
        assert!(chain_buy(99_000_000_000, t99, x_net).0 >= mo, "a fill below it");
        assert!(limit_min_out(0, 1, 1, 0.0, 0.1).is_none());
        assert!(limit_min_out(1, 1, 1, 0.0, 1.0).is_none());
        // buy_out = the engine's guard quote
        assert_eq!(buy_out(30_000_000_000, 1_073_000_000_000_000, spend, fr), chain_buy(30_000_000_000, 1_073_000_000_000_000, x_net).0);
    }

    #[test]
    fn pace_k_per_slot_evenly_no_burst() {
        let slot = 212_000_000u64;
        let mut p = Pace::new(1_000, 4, slot);
        assert_eq!(p.iv, 53_000_000);
        let mut fired = Vec::new();
        let mut now = 0u64;
        while now < 1_000 + 10 * slot { if p.due(now) { fired.push(now); } now += 1_000_000; }
        // 4 per slot over 10 slots, 53 ms apart
        assert!((40..=41).contains(&fired.len()), "{}", fired.len());
        for w in fired.windows(2) { assert!((52_000_000..=54_000_000).contains(&(w[1] - w[0])), "{:?}", w); }
        // a stall of 1 s: one attempt, then the pace again (no burst of ~19)
        let t = now + 1_000_000_000;
        assert!(p.due(t));
        assert!(!p.due(t + 1_000_000));
        assert!(p.due(t + 53_000_000));
        // k bounds
        assert_eq!(Pace::new(0, 20, slot).iv, 10_600_000);
        assert_eq!(Pace::new(0, 0, slot).iv, slot);
    }

    /// instruction equality (build::Ix has no PartialEq)
    fn same(a: &Ix, b: &Ix) -> bool { a.program == b.program && a.data == b.data && a.accounts == b.accounts }

    fn launch() -> Launch { snipe_build::launch_from_target(pk("7oeUduY1zhUwQ3YdSP9CGDYF8nYzfRdhgqtc6wAbpump"), pk("3tNPvytXB9yTZLgh5RGdjrXVxHp89vGeCiwx9juqgp7q")) }

    /// the attempt layout: CU limit, CU price, deadline, NON-idempotent T22 ATA create, WSOL ATA (idempotent), buy (spend, min out),
    /// one tip last; the roles are the indices; the error classification by index
    #[test]
    fn attempt_layout_and_classify() {
        let user = pk("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE");
        let l = launch();
        let guard = Ix { program: pk("L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95"), accounts: vec![], data: vec![15, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 5] };
        let tip = pk("4ACfpUFoaSD9bfPdeu6DBt89gB6ENTeHBXCAi87NhDEE");
        let (ixs, r) = attempt_ixs(user, &l, 200_000_000, 123_456, 70_000, 1_000, guard.clone(), Some((tip, 200_000)));
        assert_eq!(ixs.len(), 7);
        assert_eq!(r, Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) });
        assert_eq!((ixs[0].data[0], u32::from_le_bytes(ixs[0].data[1..5].try_into().unwrap())), (2, 70_000));
        assert_eq!((ixs[1].data[0], u64::from_le_bytes(ixs[1].data[1..9].try_into().unwrap())), (3, 1_000));
        assert!(same(&ixs[2], &guard));
        // the double-fill guard: Create (0), not CreateIdempotent (1), of OUR Token-2022 ATA for this mint
        assert_eq!(ixs[3].program, *pda::ATA_PROGRAM);
        assert_eq!(ixs[3].data, vec![0]);
        assert_eq!(ixs[3].accounts[1].key, snipe_build::assoc_user(&user, &l.mint));
        assert_eq!(ixs[3].accounts[5].key, *pda::TOKEN_2022);
        assert!(ixs[3].accounts[0].signer && ixs[3].accounts[1].writable);
        assert_eq!((ixs[4].program, ixs[4].data.clone()), (*pda::ATA_PROGRAM, vec![1]));
        assert_eq!(ixs[4].accounts[1].key, snipe_build::assoc_quote(&user));
        assert_eq!(ixs[5].data[..8], snipe_build::BUY_EXACT_QUOTE_IN_V3_DISC);
        assert_eq!(u64::from_le_bytes(ixs[5].data[8..16].try_into().unwrap()), 200_000_000);
        assert_eq!(u64::from_le_bytes(ixs[5].data[16..24].try_into().unwrap()), 123_456);
        assert!(same(&ixs[6], &build::transfer_ix(user, tip, 200_000)));
        // compiles into one packet with a Helius tip account and a CU price: the Sender's own check accepts it
        let msg = build::compile_v0(user, &ixs, [7u8; 32], &[], &[]).unwrap();
        let raw = build::sign(&msg, &ed25519_dalek::SigningKey::from_bytes(&[3u8; 32]));
        assert!(raw.len() <= 1232, "{} bytes", raw.len());
        // no tip (a tipless path): 6 instructions
        let (ixs2, r2) = attempt_ixs(user, &l, 1, 1, 70_000, 1_000, guard, None);
        assert_eq!((ixs2.len(), r2.tip), (6, None));
        // classification by the failing instruction's index
        assert_eq!(classify("", &r), "ok");
        assert_eq!(classify("ix5:custom:0x179a", &r), "6042");
        assert_eq!(classify("ix5:custom:0x1774", &r), "buy_6004");
        assert_eq!(classify("ix2:custom:0x1771", &r), "deadline");
        assert_eq!(classify("ix3:ie37", &r), "ata_exists");
        assert_eq!(classify("ix3:custom:0x0", &r), "ata_exists");
        assert_eq!(classify("ix6:custom:0x1", &r), "other");
        assert_eq!(classify("tx4", &r), "other");
        assert_eq!(classify("?", &r), "other");
    }

    /// a hand-made token: creator / insider / below-5% / whale; the whale's first sell; the non-standard-curve exclusion; mayhem
    /// and history-less tokens are not followed
    #[test]
    fn detector_synthetic() {
        let mint = [7u8; 32]; let cre = [1u8; 32]; let sgn = [2u8; 32];
        let mut d = Detector::new(5.0);
        d.create(mint, 100, cre, sgn, false);
        let (mut v, mut t): (u64, u64) = (30_000_000_000, 1_073_000_000_000_000);
        let mut n = 0u32;
        let mut tr = |s: u64, user: u8, buy: bool, amount: u64, d: &mut Detector| -> Vec<Det> {
            let (sol, tok) = if buy { let tok = (t as u128 * amount as u128 / (v + amount) as u128) as u64; v += amount; t -= tok; (amount, tok) }
                             else { let sol = (v as u128 * amount as u128 / (t + amount) as u128) as u64; v -= sol; t += amount; (sol, amount) };
            n += 1;
            let mut sig = [0u8; 64]; sig[..4].copy_from_slice(&n.to_be_bytes());
            let mut out = Vec::new();
            d.trade(&Trade { mint, s, i: n, j: 0, sig, user: [user; 32], buy, sol, tok, vsol: v, vtok: t, fbps: 95, cbps: 30, t_rx: 0 }, &mut out);
            out
        };
        assert!(tr(100, 1, true, 3_000_000_000, &mut d).is_empty(), "the creator's dev buy: ht 1, never a trigger");
        assert!(tr(100, 3, true, 2_000_000_000, &mut d).is_empty(), "a create-slot insider");
        assert_eq!(tr(103, 4, true, 1_400_000_000, &mut d), vec![Det::Below], "3..5% on its first big buy");
        assert!(tr(104, 4, true, 1_000_000_000, &mut d).is_empty(), "a below-5% wallet never triggers later");
        let o = tr(106, 5, true, 3_000_000_000, &mut d);
        assert!(matches!(o.as_slice(), [Det::Trigger { whale, pct, age_slots: 6, .. }] if *whale == [5u8; 32] && *pct >= 5.0), "{o:?}");
        assert!(tr(107, 5, true, 100_000_000, &mut d).is_empty(), "a whale triggers once");
        assert!(tr(108, 6, false, 1_000_000_000_000, &mut d).is_empty(), "another wallet's sell");
        assert_eq!(tr(109, 5, false, 10_000_000_000_000, &mut d), vec![Det::WhaleSell { whale: [5u8; 32] }]);
        assert!(tr(110, 5, false, 10_000_000_000_000, &mut d).is_empty(), "only its first sell");
        assert_eq!(d.st.triggers, 1);
        // an unknown mint, a mayhem launch: not followed
        let mut out = Vec::new();
        d.trade(&Trade { mint: [8; 32], s: 1, i: 0, j: 0, sig: [0; 64], user: [5; 32], buy: true, sol: 9_000_000_000, tok: 90_000_000_000_000, vsol: 40_000_000_000, vtok: 800_000_000_000_000,
                         fbps: 95, cbps: 30, t_rx: 0 }, &mut out);
        assert!(out.is_empty() && d.st.no_hist == 1);
        d.create([9; 32], 5, cre, cre, true);
        assert!(!d.followed(&[9; 32]));
        // the non-standard curve filter
        d.create([10; 32], 5, cre, cre, false);
        let mut out = Vec::new();
        d.trade(&Trade { mint: [10; 32], s: 5, i: 0, j: 0, sig: [0; 64], user: [1; 32], buy: true, sol: 1, tok: 1, vsol: 20_000_000_000, vtok: 1_000_000_000_000_000, fbps: 0, cbps: 0, t_rx: 0 }, &mut out);
        assert_eq!(out, vec![Det::Gone]);
        assert!(!d.followed(&[10; 32]));
    }

    /// the feed's failed-transaction side channel (src/feeds/mod.rs own_fail_*): only the watched payer's, its bincode error as
    /// `rec::tx_error` text, taken once, bounded; the attempt acks by tag
    #[test]
    fn own_fail_side_channel_and_acks() {
        let payer = [0xEEu8; 32];
        crate::feeds::own_fail_watch(payer);
        let watched = crate::feeds::OWN_FAIL_PAYER.get().copied().unwrap();
        // InstructionError(5, Custom(6042)) in bincode
        let err = [8u8, 0, 0, 0, 5, 25, 0, 0, 0, 0x9a, 0x17, 0, 0];
        let (s1, s2) = ([0xA1u8; 64], [0xA2u8; 64]);
        crate::feeds::own_fail_note(&s1, Some(&[0x11u8; 32][..]), 10, 3, 5_070, &err);
        assert_eq!(crate::feeds::own_fail_take(&s1), None, "another payer: not recorded");
        crate::feeds::own_fail_note(&s2, Some(&watched[..]), 11, 7, 5_070, &err);
        let got = crate::feeds::own_fail_take(&s2).unwrap();
        assert_eq!((got.slot, got.index, got.fee, got.err.as_str()), (11, 7, 5_070, "ix5:custom:0x179a"));
        assert_eq!(classify(&got.err, &Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) }), "6042");
        assert_eq!(crate::feeds::own_fail_take(&s2), None, "taken once");
        // acks
        note_ack(PS_TAG | 77, Some(200), 1.5);
        note_ack(PS_TAG | 78, None, 0.0);
        assert_eq!(ack_of(PS_TAG | 77), Some((200, 1.5)));
        assert_eq!(ack_of(PS_TAG | 78), Some((0, 0.0)));
        assert_eq!(ack_of(PS_TAG | 79), None);
        assert!(ack_counts().get(&200).copied().unwrap_or(0) >= 1);
    }

    /// a parity token's trades, in chain order
    fn tok_trades(tk: &Value) -> (Pk, u64, Pk, Pk, Vec<Trade>) {
        let mint = pk(tk["mint"].as_str().unwrap());
        let la = &tk["launch"];
        let users: Vec<Pk> = tk["users"].as_array().unwrap().iter().map(|u| pk(u.as_str().unwrap())).collect();
        let signer = pk(la["user"].as_str().unwrap());
        let creator = la["creator"].as_str().map(pk).unwrap_or(signer);
        let v = tk["trades"].as_array().unwrap().iter().map(|r| Trade { mint, s: r[0].as_u64().unwrap(), i: r[1].as_u64().unwrap() as u32, j: r[2].as_i64().unwrap() as i32,
            sig: sig64(r[3].as_str().unwrap()), user: users[r[4].as_u64().unwrap() as usize], buy: r[5].as_u64().unwrap() == 1, sol: r[6].as_u64().unwrap(),
            tok: r[7].as_u64().unwrap(), vsol: r[8].as_u64().unwrap(), vtok: r[9].as_u64().unwrap(), fbps: r[10].as_u64().unwrap_or(0), cbps: r[11].as_u64().unwrap_or(0), t_rx: 0 }).collect();
        (mint, la["slot"].as_u64().unwrap(), creator, signer, v)
    }

    /// PARITY with the shadow (and so with the study): on the 312 parity tokens, fed in chain order, the live detector's triggers
    /// are exactly the shadow's presend_arm records (trigger trade, holding %), its below-5% count equals the shadow's; fed with
    /// every slot's trades REVERSED (a worst-case arrival order), the differences are counted (a wallet's two buys swapped in
    /// one slot can move its first crossing)
    #[test]
    fn detector_parity_with_shadow() {
        let root = env!("CARGO_MANIFEST_DIR");
        let Ok(text) = std::fs::read_to_string(format!("{root}/testdata/presend_parity.json")) else { eprintln!("presend_parity.json missing: skipped"); return };
        let par: Value = serde_json::from_str(&text).unwrap();
        let (mut n_tok, mut n_trig, mut n_rev_diff) = (0usize, 0usize, 0usize);
        for tk in par["tokens"].as_array().unwrap() {
            let (mint, s0, cre, sgn, v) = tok_trades(tk);
            // the shadow's triggers
            let mut sh = Shadow::new(Params::default());
            sh.create(mint, s0, cre, sgn, false, 0);
            for t in &v {
                sh.push(In { mint, s: t.s, i: t.i, j: t.j, sig: t.sig, user: t.user, buy: t.buy, sol: t.sol, tok: t.tok, vsol: t.vsol, vtok: t.vtok, fbps: t.fbps, cbps: t.cbps, t_rx: 0, flags: 0 });
                sh.advance(t.s);
            }
            sh.complete();
            let want: Vec<(u64, u64, i64, f64)> = sh.drain().into_iter().filter(|e| e.rec["ev"] == "presend_arm")
                .map(|e| (e.rec["slot"].as_u64().unwrap(), e.rec["idx"].as_u64().unwrap(), e.rec["j"].as_i64().unwrap(), e.rec["pct"].as_f64().unwrap())).collect();
            // the live detector, chain order
            let run = |order: &[Trade]| -> (Vec<(u64, u64, i64, f64)>, u64) {
                let mut d = Detector::new(5.0);
                d.create(mint, s0, cre, sgn, false);
                let mut got = Vec::new();
                for t in order {
                    let mut out = Vec::new();
                    d.trade(t, &mut out);
                    for e in out { if let Det::Trigger { pct, .. } = e { got.push((t.s, t.i as u64, t.j as i64, pct)); } }
                }
                (got, d.st.below)
            };
            let (got, below) = run(&v);
            assert_eq!(got, want, "token {}", tk["mint"]);
            assert_eq!(below, sh.st.below_pct, "below-5% count {}", tk["mint"]);
            // worst-case arrival order: every slot reversed
            let mut by: BTreeMap<u64, Vec<Trade>> = BTreeMap::new();
            for t in &v { by.entry(t.s).or_default().push(t.clone()); }
            let rev: Vec<Trade> = by.into_values().flat_map(|mut x| { x.reverse(); x }).collect();
            let (got2, _) = run(&rev);
            let a: HashSet<(u64, u64, i64)> = got.iter().map(|x| (x.0, x.1, x.2)).collect();
            let b: HashSet<(u64, u64, i64)> = got2.iter().map(|x| (x.0, x.1, x.2)).collect();
            n_rev_diff += a.symmetric_difference(&b).count();
            n_tok += 1; n_trig += got.len();
        }
        eprintln!("presend live detector parity: {n_tok} tokens, {n_trig} triggers identical to the shadow's (chain order); every slot reversed: {n_rev_diff} trigger differences");
        assert!(n_tok > 300 && n_trig > 400);
        // reversing whole slots is far worse than the feed's real reordering; still a small share
        assert!(n_rev_diff * 20 < n_trig, "{n_rev_diff} of {n_trig}");
        let _ = HashMap::<u8, u8>::new();
    }
}
