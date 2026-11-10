// =====================================================================================================================
// dip42 Q1: the "quiet token + fresh-wallet big buy" reactive trigger as a SHADOW LOG (owner 11-06: LOG ONLY, built LOCAL, default OFF).
// Q1 is a LEAD of the w2num3 study, NOT proven (/home/it/sniper-studies/sniper-w2num3: ex9.py "Q1 quiet & fresh-wallet buy (freq<=2)" on build.py's
// candidates; sim TEST days +7.65 SOL/day at 0.5 SOL with a 9-slot timer exit, +5.24 with 4 slots, followers -20% +3.2; FIT days +2.9;
// possibly bait). Nothing is sent: the log is the forward test.
//
// THE RULE (every number is the study's; the flags' defaults):
//  the token: seen from its create by this feed, not a mayhem launch (build.py: launched, non-mayhem tokens)
//  a candidate = one executed BUY of it with                                             [build.py `isbig = b and sol >= 5e8`]
//    SOL in >= --q1-min-sol (0.5)
//    token age (slot - create slot) in --q1-age-slots LO:HI (3:80, both ends in)         [ex9.py `C.age.between(3,80)`]
//    curve token reserve after it in (0, 1073e12]                                        [build.py `(vtok > 0) & (vtok <= 1073e12)`]
//    the buyer not a 2NUM family wallet (build.py `u in FAM: continue`), not us
//  QUIET, counted WITH the trigger's own trade and nothing after it (build.py updates its state with the row, then reads it):
//    regbots  = 0: no wallet of the bot list (--q1-bots: the registry, dip39's list format) traded the token (buy or sell) in slots
//               (s - --q1-bot-slots, s] (100)                                            [`w100 = x[0] > s - 100`, `len(u100 & REG)`]
//    dipbuyers = 0: no wallet (ours included) BOUGHT the token within 2 slots after a SELL >= 0.3 SOL of it (the sell seen first), that buy
//               in slots [s - --q1-dip-slots, s] (200)                                   [`dipb`, `bigsells`, pruned `< s - 200`]
//  FRESH: the buyer's DISTINCT tokens first traded in a slot BEFORE s is <= --q1-fresh-max (2)        [`trig_freq = wfreq(u, s)`, ex9 `<= 2`]
//    counted as the study's tape did: only trades of launched, non-mayhem tokens at age <= 400 slots; the token itself counts when the
//    wallet traded it in an earlier slot. The book: per wallet its first Q1_K (8) tokens with their first slots (bounded), a wallet idle
//    for --q1-fresh-hours (48) forgotten; --q1-fresh-state FILE preloads it (ops/prod/q1_fresh_seed.py builds it from the collector tape)
//    and it is saved back every ~1500 slots and at the end. WARM-UP: while the history covers < 24 h (no state file, or one older than
//    24 h at the first trade) every wallet looks fresh: the records say "warm": true and "cover_h".
//  ONE trigger per token per --q1-gap-slots (30: the owner's spec; the study's dedup was 10): a later candidate < 30 slots after the last
//    trigger of the token is dropped.
//  There is NO curve / market-cap bound in the study's rule beyond the age band.
//
// RECORDS (only with --q1-log on):
//  q1_config  at the start; q1_bots on a list reload
//  q1_trigger {id, mint, sig, slot, idx, j, t, buyer, sol, tok, pct (% of supply), age, vsol / vtok / p (the curve AFTER the buy), p_pre,
//              bots, dipb, prior (the buyer's earlier distinct tokens), warm, cover_h, size (the paper size)}
//  q1_outcome {id, mint, slot (the trigger's), h: 1 | 4 | 9, end_slot, vsol / vtok / p (the curve at the END of slot + h = after the token's
//              last trade seen in slots <= slot + h), ret (p / the trigger's p - 1), buy_sol / sell_sol / net_sol (every later trade of the
//              token up to there, lamports), n_buys / n_sells, fam / us (a family wallet / our wallet traded it since the trigger), warm}
//    written when the feed's slot passes slot + h (so the slot is complete). h = 4 and 9 also carry
//    "paper": {size, tok, out, net (lamports)}: a --q1-size-sol (0.5) buy landing right after the trigger (pump's curve at the trigger's
//    reserves), sold at the end of slot + h on the curve WITH our buy still in it (vSOL + size, the same product), 1.25% fee each side and
//    1.5 mSOL fixed. PAPER: no landing delay, no band, no followers -20%.
// HOW: the main loop only hands each executed trade / create to a channel; the whole rule, the wallet book, the state file and the records
// run on their own thread (the tests run it inline). Nothing is read back by the probe: no decision, no send, no other record changes.
// A missing / bad bot list: NOTHING is written (a warning; the file is re-read on change every ~30 s).
// Off (no --q1-log on): nothing of it runs; every record and decision dip41's.
// =====================================================================================================================
use super::*;
use std::sync::atomic::AtomicI64;

/// a wallet's first Q1_K tokens are kept (the fresh bound must be < Q1_K - 1)
pub const Q1_K: usize = 8;
/// the wallet history counts trades at token age <= this (build.py's tape: `d.s - cs <= 400`)
pub const Q1_FREQ_AGE: u64 = 400;
/// a candidate's curve token reserve after it (build.py)
pub const Q1_VTOK_MAX: u64 = 1_073_000_000_000_000;
/// a dip buy: a buy within Q1_DIP_AFTER slots after a sell >= Q1_DIP_SELL lamports
pub const Q1_DIP_SELL: u64 = 300_000_000;
pub const Q1_DIP_AFTER: u64 = 2;
/// the outcomes' horizons (slots after the trigger's slot)
pub const Q1_H: [u64; 3] = [1, 4, 9];
/// the paper trade's costs: pump's fee per side (bps), the fixed cost per trip (lamports)
pub const Q1_FEE_BPS: u64 = 125;
pub const Q1_FIXED: u64 = 1_500_000;
/// the warm-up: the history covers less than this (ns); a state file older than this at the feed's first trade is not used
pub const Q1_WARM_NS: u64 = 24 * 3600 * 1_000_000_000;
pub const Q1_STATE_GAP_NS: u64 = 24 * 3600 * 1_000_000_000;
/// the state is saved / the books pruned every this many slots; the bot list's mtime check
const Q1_SAVE_SLOTS: u64 = 1500;
const Q1_PRUNE_SLOTS: u64 = 50;
const Q1_CHECK: Duration = Duration::from_secs(30);
/// open triggers kept at most (a guard: ~9 slots of triggers is a handful)
const Q1_OPEN_CAP: usize = 4096;

/// the flags' values
#[derive(Clone, Debug, PartialEq)]
pub struct Q1Cfg {
    pub min_sol: u64, pub age: (u64, u64), pub bot_slots: u64, pub dip_slots: u64, pub fresh_max: u32, pub gap: u64, pub size: u64,
    /// --q1-fresh-hours (ns)
    pub fresh_ns: u64,
    pub bots: String, pub state: Option<String>,
    /// the 2NUM family (the fam2 wallets)
    pub fam: Vec<Pk>,
}
impl Q1Cfg {
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"min_sol": self.min_sol as f64 / 1e9, "age": [self.age.0, self.age.1], "bot_slots": self.bot_slots, "dip_slots": self.dip_slots,
            "dip_sell_sol": Q1_DIP_SELL as f64 / 1e9, "dip_after": Q1_DIP_AFTER, "fresh_max": self.fresh_max, "gap_slots": self.gap, "size": self.size,
            "fresh_hours": self.fresh_ns as f64 / 3.6e12, "freq_age": Q1_FREQ_AGE, "k": Q1_K, "bots": self.bots, "state": self.state, "horizons": Q1_H,
            "fee_bps": Q1_FEE_BPS, "fixed": Q1_FIXED, "fam": self.fam.iter().map(b58).collect::<Vec<_>>()})
    }
    /// the warm-up's length (ns)
    pub fn warm_ns(&self) -> u64 { Q1_WARM_NS.min(self.fresh_ns) }
}

/// --q1-age-slots LO:HI (0 <= LO <= HI <= 400)
pub fn age_parse(s: &str) -> Result<(u64, u64)> {
    let bad = || anyhow::anyhow!("--q1-age-slots LO:HI (token age in slots, 0 <= LO <= HI <= {Q1_FREQ_AGE}), e.g. 3:80; got '{s}'");
    let (a, b) = s.split_once(':').ok_or_else(bad)?;
    let (a, b): (u64, u64) = (a.trim().parse().map_err(|_| bad())?, b.trim().parse().map_err(|_| bad())?);
    if a > b || b > Q1_FREQ_AGE { return Err(bad()); }
    Ok((a, b))
}

/// --q1-bots: dip39's list formats (a plain array of base58 wallets, or the bot registry's {"wallets": [{"wallet": ..} | {"w": ..} | ".."]})
/// -> (the wallets, entries skipped). An entry that is not a 32-byte base58 key is SKIPPED, as the study's registry read did (build.py:
/// `B58RE.match`; the registry carries a few numeric ids), where dip39's gate refuses the file. `user` never counts (not in the study's
/// registry either). Refused: not JSON, no array, no wallet at all
pub fn bots_parse(b: &[u8], user: &Pk) -> Result<(FxHashSet<Pk>, usize)> {
    let j: serde_json::Value = serde_json::from_slice(b).context("parse")?;
    let arr = match &j {
        serde_json::Value::Array(a) => a,
        serde_json::Value::Object(o) => o.get("wallets").and_then(|w| w.as_array()).context("no \"wallets\" array")?,
        _ => bail!("not an array or an object with \"wallets\""),
    };
    let (mut set, mut skipped) = (FxHashSet::default(), 0usize);
    for v in arr {
        match v.as_str().or_else(|| v["wallet"].as_str()).or_else(|| v["w"].as_str()).and_then(|s| bs58::decode(s).into_vec().ok()).and_then(|x| <[u8; 32]>::try_from(x).ok()) {
            Some(pk) => { if pk != *user { set.insert(pk); } }
            None => skipped += 1,
        }
    }
    if set.is_empty() { bail!("no wallet in the list"); }
    Ok((set, skipped))
}

/// a mint's id in a wallet's history: its first 4 bytes (little-endian)
#[inline]
pub fn mint_id(m: &Pk) -> u32 { u32::from_le_bytes([m[0], m[1], m[2], m[3]]) }

/// one wallet's history: its last trade (unix s), its first tokens (id, the slot of its first trade of it), oldest first
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct WF { pub last: u32, pub n: u8, pub m: [u32; Q1_K], pub s: [u64; Q1_K] }
impl WF {
    /// the distinct tokens first traded in a slot before `slot` (capped at Q1_K)
    #[inline]
    pub fn prior(&self, slot: u64) -> u32 { self.s[..self.n as usize].iter().filter(|&&x| x < slot).count() as u32 }
}

/// the wallets' distinct-token book (the study's `WF` / `wfreq`)
#[derive(Debug, Default)]
pub struct Fresh { pub w: FxHashMap<Pk, WF> }
impl Fresh {
    /// the wallet's earlier distinct tokens at `slot`
    #[cfg(test)]
    pub fn prior(&self, user: &Pk, slot: u64) -> u32 { self.w.get(user).map_or(0, |x| x.prior(slot)) }
    /// one trade of a young launched token: the wallet's earlier distinct tokens (this trade's token counts only from the next slot on)
    pub fn note(&mut self, user: Pk, mint: &Pk, slot: u64, t_s: u32) -> u32 {
        let id = mint_id(mint);
        let e = self.w.entry(user).or_insert(WF { last: t_s, n: 0, m: [0; Q1_K], s: [0; Q1_K] });
        if t_s > e.last { e.last = t_s; }
        let n = e.n as usize;
        if !e.m[..n].contains(&id) && n < Q1_K { e.m[n] = id; e.s[n] = slot; e.n += 1; }
        e.prior(slot)
    }
    /// wallets with no trade since `lo` (unix s) forgotten
    pub fn prune(&mut self, lo: u32) -> usize { let n = self.w.len(); self.w.retain(|_, x| x.last >= lo); n - self.w.len() }
    /// the state (FORMAT: the header of ops/prod/q1_fresh_seed.py)
    pub fn state_json(&self, t: u64, slot: u64, from: u64) -> serde_json::Value {
        let w: serde_json::Map<String, serde_json::Value> = self.w.iter().map(|(k, x)| {
            let mut v: Vec<u64> = Vec::with_capacity(1 + 2 * x.n as usize);
            v.push(x.last as u64);
            for i in 0..x.n as usize { v.push(x.m[i] as u64); v.push(x.s[i]); }
            (b58(k), v.into())
        }).collect();
        serde_json::json!({"v": 1, "kind": "q1_fresh", "t": t, "slot": slot, "from": from, "k": Q1_K, "age_max": Q1_FREQ_AGE, "w": w})
    }
    /// a saved state -> (its clock, its history's start, the wallets); wallets idle > `idle_ns` before its clock dropped
    pub fn state_parse(b: &[u8], idle_ns: u64) -> Result<(u64, u64, FxHashMap<Pk, WF>)> {
        let j: serde_json::Value = serde_json::from_slice(b).context("parse")?;
        if j["v"].as_u64() != Some(1) || j["kind"] != "q1_fresh" { bail!("not a v1 q1_fresh state"); }
        let (Some(t), Some(from)) = (j["t"].as_u64(), j["from"].as_u64()) else { bail!("no \"t\" / \"from\"") };
        let lo = (t.saturating_sub(idle_ns) / 1_000_000_000) as u32;
        let mut m: FxHashMap<Pk, WF> = FxHashMap::default();
        for (w, v) in j["w"].as_object().context("no \"w\" object")? {
            let Some(pk) = bs58::decode(w).into_vec().ok().and_then(|x| <[u8; 32]>::try_from(x).ok()) else { bail!("bad wallet {w}") };
            let a: Vec<u64> = v.as_array().with_context(|| format!("{w}: not an array"))?.iter().map(|x| x.as_u64()).collect::<Option<Vec<u64>>>().with_context(|| format!("{w}: bad entry"))?;
            if a.is_empty() || a.len() % 2 != 1 { bail!("{w}: want [last, m, s, ...]"); }
            if (a[0] as u32) < lo { continue; }
            let mut x = WF { last: a[0] as u32, n: 0, m: [0; Q1_K], s: [0; Q1_K] };
            for p in a[1..].chunks(2).take(Q1_K) { let n = x.n as usize; x.m[n] = p[0] as u32; x.s[n] = p[1]; x.n += 1; }
            m.insert(pk, x);
        }
        Ok((t, from, m))
    }
}

/// the paper trade: `size` lamports into the curve right after the trigger (reserves `v0` = vSOL, vTok after it), sold at reserves `cur`
/// with our buy still in the curve (vSOL + size, the same product) -> (tokens, SOL out before the fee, net lamports after 1.25% per side
/// and the fixed cost). None: an empty curve
pub fn paper(v0: (u64, u64), cur: (u64, u64), size: u64) -> Option<(u64, u64, i64)> {
    if v0.0 == 0 || v0.1 == 0 || cur.0 == 0 || cur.1 == 0 || size == 0 { return None; }
    let tok = (size as u128 * v0.1 as u128 / (v0.0 as u128 + size as u128)) as u64;
    if tok == 0 { return None; }
    let vs = cur.0 as u128 + size as u128;
    let vt = (cur.0 as u128 * cur.1 as u128).div_ceil(vs);
    let out = (tok as u128 * vs / (vt + tok as u128)) as u64;
    let fee = |x: u64| (x as u128 * Q1_FEE_BPS as u128).div_ceil(10_000) as u64;
    let net = out as i64 - fee(out) as i64 - size as i64 - fee(size) as i64 - Q1_FIXED as i64;
    Some((tok, out, net))
}

/// one executed trade as the rule needs it
#[derive(Clone, Debug)]
pub struct Q1Trade { pub mint: Pk, pub user: Pk, pub buy: bool, pub sol: u64, pub tok: u64, pub vsol: u64, pub vtok: u64, pub slot: u64, pub idx: u32, pub j: i32, pub sig: [u8; 64], pub t: u64 }

/// a followed token: its create slot, the newest big sell's slot (0: none), the listed bots' newest trade slots, the dip buyers' newest
/// dip-buy slots, its last trigger's slot (0: none)
#[derive(Debug, Default)]
struct QTok { cs: u64, last_sell: u64, bots: Vec<(Pk, u64)>, dips: Vec<(Pk, u64)>, last_trig: u64 }

fn upsert(v: &mut Vec<(Pk, u64)>, w: Pk, slot: u64) {
    match v.iter_mut().find(|e| e.0 == w) { Some(e) => e.1 = e.1.max(slot), None => v.push((w, slot)) }
}

/// a trigger whose outcomes are still due
#[derive(Clone, Debug)]
struct Open { id: u64, mint: Pk, slot: u64, v0: (u64, u64), cur: (u64, u64), buys: u64, sells: u64, nb: u32, ns: u32, fam: bool, us: bool, next: usize, warm: bool }

/// the counters the status line reads (the rule runs on its own thread)
#[derive(Debug, Default)]
pub struct Q1Stats {
    pub cands: AtomicU64, pub not_quiet: AtomicU64, pub not_fresh: AtomicU64, pub dedup: AtomicU64, pub no_list: AtomicU64, pub triggers: AtomicU64, pub warm_triggers: AtomicU64,
    pub outcomes: AtomicU64,
    /// paper at +4 / +9: wins, losses, net lamports
    pub pw: [AtomicU64; 2], pub pl: [AtomicU64; 2], pub pnet: [AtomicI64; 2],
    pub wallets: AtomicU64, pub toks: AtomicU64, pub bots: AtomicU64, pub warm: AtomicBool, pub listed: AtomicBool,
}

/// the rule (pure but for the bot list / state files): fed in feed order, its records pushed to `out`
#[derive(Debug)]
pub struct Q1 {
    pub cfg: Q1Cfg,
    user: Pk,
    fam: FxHashSet<Pk>,
    /// the bot list (None: no good list yet -> nothing written)
    pub bots: Option<FxHashSet<Pk>>,
    mtime: Option<std::time::SystemTime>,
    checked: Instant,
    pub bots_err: Option<String>, pub bots_skipped: usize,
    toks: FxHashMap<Pk, QTok>,
    pub fresh: Fresh,
    open: Vec<Open>,
    next_id: u64,
    /// the feed's clock (ns) and slot; the history's start (the state's when used)
    pub now_t: u64, pub now_slot: u64, pub cover_from: Option<u64>,
    /// a preloaded state waiting for the first trade: (its clock, its start, the wallets)
    pending: Option<(u64, u64, FxHashMap<Pk, WF>)>,
    pub state_used: Option<bool>, pub state_err: Option<String>, pub state_n: usize,
    pruned: u64, saved: u64, warm_logged: bool, forgot: u64, late: u64,
    pub st: Arc<Q1Stats>,
}

impl Q1 {
    /// the start: the bot list read (a failure is kept: nothing written until a good list), the state preloaded (used at the first trade)
    pub fn open(cfg: Q1Cfg, user: Pk) -> Q1 {
        let fam = cfg.fam.iter().copied().collect();
        let mut q = Q1 { cfg, user, fam, bots: None, mtime: None, checked: Instant::now(), bots_err: None, bots_skipped: 0, toks: FxHashMap::default(), fresh: Fresh::default(), open: Vec::new(), next_id: 0,
            now_t: 0, now_slot: 0, cover_from: None, pending: None, state_used: None, state_err: None, state_n: 0, pruned: 0, saved: 0, warm_logged: false, forgot: 0, late: 0,
            st: Arc::new(Q1Stats::default()) };
        q.mtime = std::fs::metadata(&q.cfg.bots).and_then(|m| m.modified()).ok();
        match std::fs::read(&q.cfg.bots).map_err(|e| anyhow::anyhow!("read: {e}")).and_then(|x| bots_parse(&x, &user)) {
            Ok((s, skipped)) => { q.st.bots.store(s.len() as u64, Ordering::Relaxed); q.st.listed.store(true, Ordering::Relaxed); q.bots = Some(s); q.bots_skipped = skipped; }
            Err(e) => q.bots_err = Some(format!("{e:#}")),
        }
        if let Some(p) = q.cfg.state.clone() {
            match std::fs::read(&p) {
                Ok(x) => match Fresh::state_parse(&x, q.cfg.fresh_ns) { Ok(s) => { q.state_n = s.2.len(); q.pending = Some(s); } Err(e) => q.state_err = Some(format!("{e:#}")) },
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
                Err(e) => q.state_err = Some(format!("{e}")),
            }
        }
        q.st.warm.store(true, Ordering::Relaxed);
        q
    }
    /// the start's record
    pub fn config_rec(&self) -> serde_json::Value {
        let mut r = self.cfg.json();
        r["ev"] = "q1_config".into();
        r["mode"] = "log".into();
        r["bots_n"] = self.bots.as_ref().map(|b| b.len()).into();
        r["bots_err"] = self.bots_err.clone().into();
        r["bots_skipped"] = self.bots_skipped.into();
        r["state_wallets"] = self.state_n.into();
        r["state_err"] = self.state_err.clone().into();
        r["warmup"] = format!("\"warm\": true while the wallet history covers < {} h (a state file <= 24 h old at the first trade counts)", self.cfg.warm_ns() as f64 / 3.6e12).into();
        r["t"] = arbx::feeds::clock::now_ns().into();
        r
    }
    /// a pump create: a non-mayhem token is followed from here
    pub fn create(&mut self, mint: Pk, slot: u64, mayhem: bool) {
        if mayhem || self.toks.contains_key(&mint) { return; }
        self.toks.insert(mint, QTok { cs: slot, ..Default::default() });
    }
    fn first_trade(&mut self, t: u64) {
        self.cover_from = Some(t);
        if let Some((saved, from, w)) = self.pending.take() {
            // the state's clock is block time (whole seconds): a minute of slack; never one older than 24 h
            let ok = saved <= t.saturating_add(60_000_000_000) && t.saturating_sub(saved) <= Q1_STATE_GAP_NS;
            if ok { self.cover_from = Some(from.min(t)); self.fresh.w = w; }
            self.state_used = Some(ok);
        }
    }
    /// the history covers less than the warm-up
    pub fn warm(&self) -> bool { self.cover_from.is_none_or(|c| self.now_t < c.saturating_add(self.cfg.warm_ns())) }
    pub fn cover_h(&self) -> f64 { self.cover_from.map_or(0.0, |c| self.now_t.saturating_sub(c) as f64 / 3.6e12) }
    #[cfg(test)]
    pub fn open_n(&self) -> usize { self.open.len() }

    /// one executed-feed trade (feed order) -> its records (a trigger; the outcomes the feed's slot just passed)
    pub fn trade(&mut self, e: &Q1Trade, out: &mut Vec<serde_json::Value>) {
        if e.t > self.now_t { self.now_t = e.t; }
        if self.cover_from.is_none() { self.first_trade(e.t); }
        if e.slot > self.now_slot {
            self.now_slot = e.slot;
            // the slots before this one are complete: the outcomes due
            self.flush(out);
            self.prune();
        }
        // the open triggers of this token follow it (an out-of-order trade of an older slot is left out: its horizons may be written)
        if !self.open.is_empty() {
            if e.slot == self.now_slot {
                let (fam, us) = (self.fam.contains(&e.user), e.user == self.user);
                for o in self.open.iter_mut().filter(|o| o.mint == e.mint && e.slot <= o.slot + Q1_H[Q1_H.len() - 1]) {
                    o.cur = (e.vsol, e.vtok);
                    if e.buy { o.buys += e.sol; o.nb += 1; } else { o.sells += e.sol; o.ns += 1; }
                    o.fam |= fam; o.us |= us;
                }
            } else { self.late += 1; }
        }
        let Some(tk) = self.toks.get_mut(&e.mint) else { return };
        if e.slot < tk.cs { return; }
        let age = e.slot - tk.cs;
        if age > Q1_FREQ_AGE { return; }
        // the wallet's history (the study's tape: every trade of a launched non-mayhem token at age <= 400)
        let prior = self.fresh.note(e.user, &e.mint, e.slot, (e.t / 1_000_000_000) as u32);
        // the token's rows (build.py: rows with a curve reserve in (0, 1073e12]); past the age band nothing of it is read again
        if e.vtok == 0 || e.vtok > Q1_VTOK_MAX || age > self.cfg.age.1 { return; }
        // the row into the token's state FIRST (the trigger's own trade counts)
        if e.buy {
            if tk.last_sell > 0 && e.slot >= tk.last_sell && e.slot - tk.last_sell <= Q1_DIP_AFTER { upsert(&mut tk.dips, e.user, e.slot); }
        } else if e.sol >= Q1_DIP_SELL { tk.last_sell = tk.last_sell.max(e.slot); }
        if self.bots.as_ref().is_some_and(|b| b.contains(&e.user)) { upsert(&mut tk.bots, e.user, e.slot); }
        // the candidate
        if !e.buy || e.sol < self.cfg.min_sol || age < self.cfg.age.0 || e.user == self.user || self.fam.contains(&e.user) { return; }
        let st = &self.st;
        st.cands.fetch_add(1, Ordering::Relaxed);
        if self.bots.is_none() { st.no_list.fetch_add(1, Ordering::Relaxed); return; }
        let nb = tk.bots.iter().filter(|x| x.1 + self.cfg.bot_slots > e.slot).count();
        let nd = tk.dips.iter().filter(|x| x.1 + self.cfg.dip_slots >= e.slot).count();
        if nb > 0 || nd > 0 { st.not_quiet.fetch_add(1, Ordering::Relaxed); return; }
        if prior > self.cfg.fresh_max { st.not_fresh.fetch_add(1, Ordering::Relaxed); return; }
        if tk.last_trig > 0 && e.slot.saturating_sub(tk.last_trig) < self.cfg.gap { st.dedup.fetch_add(1, Ordering::Relaxed); return; }
        tk.last_trig = e.slot;
        let warm = self.warm();
        st.triggers.fetch_add(1, Ordering::Relaxed);
        if warm { st.warm_triggers.fetch_add(1, Ordering::Relaxed); }
        self.next_id += 1;
        let id = self.next_id;
        let p = e.vsol as f64 / (e.vtok as f64).max(1.0);
        let p_pre = e.vsol.saturating_sub(e.sol) as f64 / (e.vtok.saturating_add(e.tok) as f64).max(1.0);
        out.push(serde_json::json!({"ev": "q1_trigger", "id": id, "mint": b58(&e.mint), "sig": bs58::encode(&e.sig).into_string(), "slot": e.slot, "idx": e.idx, "j": e.j, "t": e.t,
            "buyer": b58(&e.user), "sol": e.sol, "tok": e.tok, "pct": e.tok as f64 / pl::SUPPLY * 100.0, "age": age, "vsol": e.vsol, "vtok": e.vtok, "p": p, "p_pre": p_pre,
            "bots": nb, "dipb": nd, "prior": prior, "warm": warm, "cover_h": self.cover_h(), "size": self.cfg.size}));
        if self.open.len() < Q1_OPEN_CAP {
            self.open.push(Open { id, mint: e.mint, slot: e.slot, v0: (e.vsol, e.vtok), cur: (e.vsol, e.vtok), buys: 0, sells: 0, nb: 0, ns: 0, fam: false, us: false, next: 0, warm });
        }
    }
    /// the outcomes whose slot the feed has passed
    fn flush(&mut self, out: &mut Vec<serde_json::Value>) {
        if self.open.is_empty() { return; }
        let now = self.now_slot;
        for o in self.open.iter_mut() {
            while o.next < Q1_H.len() && now > o.slot + Q1_H[o.next] {
                let h = Q1_H[o.next];
                o.next += 1;
                let (p0, p) = (o.v0.0 as f64 / (o.v0.1 as f64).max(1.0), o.cur.0 as f64 / (o.cur.1 as f64).max(1.0));
                let mut r = serde_json::json!({"ev": "q1_outcome", "id": o.id, "mint": b58(&o.mint), "slot": o.slot, "h": h, "end_slot": o.slot + h, "vsol": o.cur.0, "vtok": o.cur.1,
                    "p": p, "ret": if p0 > 0.0 { p / p0 - 1.0 } else { 0.0 }, "buy_sol": o.buys, "sell_sol": o.sells, "net_sol": o.buys as i64 - o.sells as i64, "n_buys": o.nb,
                    "n_sells": o.ns, "fam": o.fam, "us": o.us, "warm": o.warm, "t": self.now_t});
                self.st.outcomes.fetch_add(1, Ordering::Relaxed);
                if h >= 4 {
                    if let Some((tok, sol, net)) = paper(o.v0, o.cur, self.cfg.size) {
                        r["paper"] = serde_json::json!({"label": "paper", "size": self.cfg.size, "tok": tok, "out": sol, "net": net});
                        let k = if h == 4 { 0 } else { 1 };
                        if net > 0 { self.st.pw[k].fetch_add(1, Ordering::Relaxed); } else { self.st.pl[k].fetch_add(1, Ordering::Relaxed); }
                        self.st.pnet[k].fetch_add(net, Ordering::Relaxed);
                    }
                }
                out.push(r);
            }
        }
        self.open.retain(|o| o.next < Q1_H.len());
    }
    /// tokens past the history's age forgotten; idle wallets forgotten (every ~1500 slots)
    fn prune(&mut self) {
        let now = self.now_slot;
        if now < self.pruned + Q1_PRUNE_SLOTS { return; }
        let wallets = now >= (self.pruned / Q1_SAVE_SLOTS + 1) * Q1_SAVE_SLOTS || self.pruned == 0;
        self.pruned = now;
        let hi = self.cfg.age.1;
        self.toks.retain(|_, t| now.saturating_sub(t.cs) <= Q1_FREQ_AGE);
        for t in self.toks.values_mut() { if now.saturating_sub(t.cs) > hi && (!t.bots.is_empty() || !t.dips.is_empty()) { t.bots = Vec::new(); t.dips = Vec::new(); } }
        if wallets {
            let lo = (self.now_t.saturating_sub(self.cfg.fresh_ns) / 1_000_000_000) as u32;
            self.forgot += self.fresh.prune(lo) as u64;
        }
        self.st.wallets.store(self.fresh.w.len() as u64, Ordering::Relaxed);
        self.st.toks.store(self.toks.len() as u64, Ordering::Relaxed);
        self.st.warm.store(self.warm(), Ordering::Relaxed);
    }
    /// the wall-clock work (the thread's idle step; a test calls it): the bot list's reload, the warm-up's end, the state every ~1500 slots
    pub fn house(&mut self, force: bool, out: &mut Vec<serde_json::Value>, lines: &mut Vec<String>) {
        if force || self.checked.elapsed() >= Q1_CHECK {
            self.checked = Instant::now();
            let mt = std::fs::metadata(&self.cfg.bots).and_then(|m| m.modified()).ok();
            if force || mt != self.mtime {
                self.mtime = mt;
                match std::fs::read(&self.cfg.bots).map_err(|e| anyhow::anyhow!("read: {e}")).and_then(|b| bots_parse(&b, &self.user)) {
                    Ok((s, skipped)) => {
                        self.bots_skipped = skipped;
                        let was = self.bots.as_ref().map(|b| b.len());
                        for t in self.toks.values_mut() { t.bots.retain(|e| s.contains(&e.0)); }
                        self.st.bots.store(s.len() as u64, Ordering::Relaxed); self.st.listed.store(true, Ordering::Relaxed);
                        out.push(serde_json::json!({"ev": "q1_bots", "ok": true, "path": self.cfg.bots, "n": s.len(), "was": was, "t": arbx::feeds::clock::now_ns()}));
                        lines.push(format!("  Q1 LOG bot list reloaded: {} wallets from {}", s.len(), self.cfg.bots));
                        self.bots = Some(s); self.bots_err = None;
                    }
                    Err(e) => {
                        out.push(serde_json::json!({"ev": "q1_bots", "ok": false, "path": self.cfg.bots, "err": format!("{e:#}"), "n": self.bots.as_ref().map(|b| b.len()),
                            "t": arbx::feeds::clock::now_ns()}));
                        lines.push(format!("  Q1 LOG bot list NOT reloaded ({e:#}): {}", if self.bots.is_some() { "the last good list stays" } else { "NO list: nothing is written" }));
                    }
                }
            }
        }
        if !self.warm_logged && self.cover_from.is_some() && !self.warm() {
            self.warm_logged = true;
            lines.push(format!("  Q1 LOG: the wallet history covers {:.1} h ({} wallets): its records are no longer \"warm\"", self.cover_h(), self.fresh.w.len()));
        }
        if self.cfg.state.is_some() && self.now_slot >= self.saved + Q1_SAVE_SLOTS {
            if self.saved > 0 { if let Err(e) = self.save() { lines.push(format!("  Q1 LOG: the wallet history was NOT saved: {e}")); } }
            self.saved = self.now_slot;
        }
    }
    /// the wallet history to its state file (atomic: FILE.new + rename) -> wallets
    pub fn save(&self) -> std::result::Result<usize, String> {
        let Some(p) = self.cfg.state.as_ref() else { return Ok(0) };
        let Some(from) = self.cover_from else { return Ok(0) };
        let tmp = format!("{p}.new");
        std::fs::write(&tmp, self.fresh.state_json(self.now_t, self.now_slot, from).to_string()).map_err(|e| format!("write {tmp}: {e}"))?;
        std::fs::rename(&tmp, p).map_err(|e| format!("rename {tmp}: {e}"))?;
        Ok(self.fresh.w.len())
    }
    /// run_end's part (the state saved)
    pub fn finish(&mut self, lines: &mut Vec<String>) -> serde_json::Value {
        if self.cfg.state.is_some() {
            match self.save() { Ok(n) => lines.push(format!("  Q1 LOG: wallet history of {n} wallets saved to {}", self.cfg.state.as_deref().unwrap_or(""))),
                                Err(e) => lines.push(format!("  Q1 LOG: the wallet history was NOT saved: {e}")) }
        }
        let s = &self.st;
        let l = |a: &AtomicU64| a.load(Ordering::Relaxed);
        let pp = |k: usize| serde_json::json!({"w": l(&s.pw[k]), "l": l(&s.pl[k]), "net": s.pnet[k].load(Ordering::Relaxed)});
        serde_json::json!({"mode": "log", "cands": l(&s.cands), "not_quiet": l(&s.not_quiet), "not_fresh": l(&s.not_fresh), "dedup": l(&s.dedup), "no_list": l(&s.no_list),
            "triggers": l(&s.triggers), "warm_triggers": l(&s.warm_triggers), "outcomes": l(&s.outcomes), "open_at_end": self.open.len(), "paper4": pp(0), "paper9": pp(1),
            "size": self.cfg.size, "wallets": self.fresh.w.len(), "forgot": self.forgot, "tokens": self.toks.len(), "bots": self.bots.as_ref().map(|b| b.len()),
            "state": self.cfg.state, "state_used": self.state_used, "state_err": self.state_err, "cover_h": self.cover_h(), "warm": self.warm(), "late": self.late})
    }
}

/// what the main loop hands over
pub enum Q1Msg { Create(Pk, u64, bool), Trade(Box<Q1Trade>), Finish(crossbeam_channel::Sender<serde_json::Value>) }

/// the main loop's handle: the rule inline (the tests) or on its own thread (a run)
pub struct Q1Tap {
    tx: Option<crossbeam_channel::Sender<Q1Msg>>,
    inline: Option<Box<Q1>>,
    out: crossbeam_channel::Sender<Out>,
    thread: Option<std::thread::JoinHandle<()>>,
    pub st: Arc<Q1Stats>,
    pub cfg: Q1Cfg,
}

fn emit(out: &crossbeam_channel::Sender<Out>, recs: &mut Vec<serde_json::Value>, lines: &mut Vec<String>) {
    for l in lines.drain(..) { let _ = out.send(Out::Line(l)); }
    for r in recs.drain(..) { let _ = out.send(Out::Rec(r)); }
}

impl Q1Tap {
    /// the start: the lists read, the start's line and record; `inline`: no thread (every message handled at once)
    pub fn start(cfg: Q1Cfg, user: Pk, out: &crossbeam_channel::Sender<Out>, inline: bool) -> Q1Tap {
        let mut q = Q1::open(cfg.clone(), user);
        let st = q.st.clone();
        eprintln!("DIP Q1 SHADOW (dip42, LOG ONLY: nothing sent): a BUY >= {} SOL at token age {}..{} slots by a wallet with <= {} earlier tokens, on a QUIET token (0 listed bots in {} slots, \
            0 dip buyers in {} slots), one per token per {} slots -> q1_trigger + q1_outcome at +1 / +4 / +9 slots (paper {} SOL) | bots {} | wallet history {}",
            cfg.min_sol as f64 / 1e9, cfg.age.0, cfg.age.1, cfg.fresh_max, cfg.bot_slots, cfg.dip_slots, cfg.gap, cfg.size as f64 / 1e9,
            match (&q.bots, &q.bots_err) { (Some(b), _) => format!("{}: {} wallets (re-read on change)", cfg.bots, b.len()),
                (None, e) => format!("{} NOT LOADED ({}): NOTHING is written until a good list is read", cfg.bots, e.clone().unwrap_or_default()) },
            match (&cfg.state, &q.state_err, q.state_n) { (None, _, _) => "no state file: WARM-UP (every wallet looks fresh at first; records \"warm\": true for 24 h)".to_string(),
                (Some(p), Some(e), _) => format!("{p} NOT read ({e}): WARM-UP"), (Some(p), None, 0) => format!("{p} (not there yet / empty: WARM-UP; saved every ~1500 slots)"),
                (Some(p), None, n) => format!("{p}: {n} wallets preloaded (used when <= 24 h old at the first trade)") });
        let _ = out.send(Out::Rec(q.config_rec()));
        if inline { return Q1Tap { tx: None, inline: Some(Box::new(q)), out: out.clone(), thread: None, st, cfg }; }
        let (tx, rx) = crossbeam_channel::unbounded::<Q1Msg>();
        let o = out.clone();
        let thread = std::thread::Builder::new().name("q1-log".into()).spawn(move || {
            let (mut recs, mut lines) = (Vec::new(), Vec::new());
            loop {
                match rx.recv_timeout(Duration::from_secs(1)) {
                    Ok(Q1Msg::Trade(t)) => q.trade(&t, &mut recs),
                    Ok(Q1Msg::Create(m, s, may)) => q.create(m, s, may),
                    Ok(Q1Msg::Finish(r)) => { let j = q.finish(&mut lines); emit(&o, &mut recs, &mut lines); let _ = r.send(j); return; }
                    Err(crossbeam_channel::RecvTimeoutError::Timeout) => {}
                    Err(crossbeam_channel::RecvTimeoutError::Disconnected) => return,
                }
                q.house(false, &mut recs, &mut lines);
                if !recs.is_empty() || !lines.is_empty() { emit(&o, &mut recs, &mut lines); }
            }
        }).ok();
        Q1Tap { tx: Some(tx), inline: None, out: out.clone(), thread, st, cfg }
    }
    #[inline]
    pub fn create(&mut self, mint: Pk, slot: u64, mayhem: bool) {
        if let Some(q) = self.inline.as_mut() { q.create(mint, slot, mayhem); return; }
        if let Some(tx) = &self.tx { let _ = tx.send(Q1Msg::Create(mint, slot, mayhem)); }
    }
    #[inline]
    pub fn trade(&mut self, t: Q1Trade) {
        if let Some(q) = self.inline.as_mut() {
            let (mut recs, mut lines) = (Vec::new(), Vec::new());
            q.trade(&t, &mut recs);
            q.house(false, &mut recs, &mut lines);
            emit(&self.out, &mut recs, &mut lines);
            return;
        }
        if let Some(tx) = &self.tx { let _ = tx.send(Q1Msg::Trade(Box::new(t))); }
    }
    /// the inline rule (the tests)
    #[cfg(test)]
    pub fn inner(&mut self) -> &mut Q1 { self.inline.as_mut().expect("inline") }
    /// the status line's part
    pub fn status(&self) -> String {
        let s = &self.st;
        let l = |a: &AtomicU64| a.load(Ordering::Relaxed);
        let pp = |k: usize| format!("{}W/{}L {:+.3} SOL", l(&s.pw[k]), l(&s.pl[k]), s.pnet[k].load(Ordering::Relaxed) as f64 / 1e9);
        format!(" | Q1 LOG{}{}: triggers {} ({} in warm-up) of {} big buys (not quiet {}, not fresh {}, repeat {}) | paper {} SOL +4 {}, +9 {} | wallets {}, bots {}",
            if s.listed.load(Ordering::Relaxed) { "" } else { " NO BOT LIST (nothing written)" }, if s.warm.load(Ordering::Relaxed) { " WARM-UP" } else { "" },
            l(&s.triggers), l(&s.warm_triggers), l(&s.cands), l(&s.not_quiet), l(&s.not_fresh), l(&s.dedup), self.cfg.size as f64 / 1e9, pp(0), pp(1), l(&s.wallets), l(&s.bots))
    }
    /// run_end's part: the thread saves the state and answers (waited for at most 20 s)
    pub fn finish(&mut self) -> Option<serde_json::Value> {
        if let Some(q) = self.inline.as_mut() {
            let (mut recs, mut lines) = (Vec::new(), Vec::new());
            let j = q.finish(&mut lines);
            emit(&self.out, &mut recs, &mut lines);
            return Some(j);
        }
        let tx = self.tx.take()?;
        let (rtx, rrx) = crossbeam_channel::bounded(1);
        let _ = tx.send(Q1Msg::Finish(rtx));
        let j = rrx.recv_timeout(Duration::from_secs(20)).ok();
        if j.is_some() { if let Some(t) = self.thread.take() { let _ = t.join(); } }
        Some(j.unwrap_or_else(|| serde_json::json!({"mode": "log", "err": "the q1 thread did not answer in 20 s"})))
    }
}
