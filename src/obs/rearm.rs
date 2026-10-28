//! OBSERVATORY module 1: the pre-send RE-ARM shadow (owner's rule R0; ops/strategies/presend/REARM2.md, the replay rearm2/ and
//! haqq_dissect/rearm/rsim.py). LOG ONLY: what the re-arm would have armed, tried and filled on this run's own feed.
//! Everything below is on the executed feed's arrival clock (t = t_rx, unix ns) and slot clock (the observatory's `Clock`: the
//! first arrival of a slot moves it), in ARRIVAL order, as the live engine sees the chain.
//!   CANDIDATE: a single curve SELL of >= 6% of supply (tok >= 6e13) on a normal token (seen from its create, not mayhem, standard
//!     curve) whose age is <= 30 s (slots since the create x 0.212 s, the study's clock: <= 141 slots) and whose post-sell curve is
//!     < 100 SOL. Every such sell also STOPS an armed re-arm window of its token (30 ms later: "the next whale dump").
//!   HOLDERS CHECK at the end of slot dump+2 (= when the clock first reaches a slot >= dump+3, before that tx's trades): every wallet
//!     still holding >= 6%. None: no window ("no_holder"). A live pre-send window armed on the token then: "blocked_live_armed".
//!   WINDOW (R0): armed at that moment (t_arm, arm slot), last slot = dump + 3 + 20 (rsim's "dump + 3 + G", inclusive); it ends at
//!     the first arrival of slot > last slot ("expired"), or 30 ms after the next >= 6% sell of the token ("whale_dump"), or 30 ms
//!     after the trade after which no wallet holds >= 6% ("no_holder"), or QUIET stop 6:2 (at the first slot >= arm slot + 6, fewer
//!     than 2 trades by anyone but us since the arm: "quiet"), or a live T2 window armed on the token ("superseded": applied when
//!     the window is evaluated, from the tailed live records). R2 = the same window with last slot dump + 3 + 10 (its own end).
//!   R5: the QUIET arm signals of the remaining holders at the arm: (a) slots since the token's previous trade, (b) cohort wallets
//!     holding it, (c) follower bots that traded it, (d) per holder its dump history's mean followers (wh_fol, wh_dumps; the
//!     observatory's own 24 h DumpBook, preloaded from --presend-live-quiet-book). r5_skip = all four hold for the LARGEST holder
//!     (rearm2/ev.py's choice: qsig of hold[0]).
//!   TRIES: k per slot (the live pace: --presend-live-k, the engine's slot length SLOT_US) from t_arm to the end; each would-be try in
//!     unix second S is REFUSED when the live attempts sent in S (tailed presend_attempt records) plus the re-arm's own tries already
//!     placed in S reach the cap (--presend-live-max-per-sec, the shared helius-ps budget). Counted per window; tries refused within
//!     100 ms before a paper fill are flagged on the fill.
//!   PAPER FILL per row a / b / c (= the shadow's queue rows, +0 / +5 / +10 ms): the first trade x in [t_arm, end) whose post price is
//!     <= (1 - drop) x the reference (the post price of the last trade at least 50 ms before x on the arrival clock; none: the first
//!     tape trade's pre price); our order lands at x.t + D behind every trade seen by then (m = the last of them) and fills iff the
//!     price after m is still <= that limit, the curve after m is < 100 SOL ("untradeable" otherwise) and x.t + D < end ("late");
//!     else the search goes on after x. One paper position per token per row: a row whose last paper position on the token is not
//!     sold + 300 ms by t_arm is "blocked".
//!   EXITS per fill, sizes 0.40 / 0.65 / 1.0 SOL, our buy on the curve after m (fee on top, our own impact), every later trade of the
//!     token applied on that curve; two variants: "naive" (every later trade as it was) and "slip" (a later buy whose min-out our buy
//!     breaks is dropped: the study's slack table). A sell decided at time T executes on the curve after every trade seen before T
//!     (zero sell latency; the 3 s tape is in the record for any other assumption). Policies: t200 / t300 (T = our fill seen + 200 /
//!     300 ms; "fill seen" = its landing time x.t + D), s2 (the first trade of slot >= entry slot + 2), tp10 / tp20 (the first of:
//!     value >= 1.10 / 1.20 right after a trade, value <= 0.80, s2), live (TP 20% / SL 20% / t200 / s2, the first). Values are gross
//!     mSOL: SOL back after pump's fee minus the size (no tx costs). The 0.88x min-out of the live attempt is checked per size
//!     (min_ok: the tokens at m >= the min-out a try signed on the reference state would ask).
//!   SECOND SELLER per fill: the first sell after m within the entry slot + 2 by a wallet holding >= 6% (before or after it) or of
//!     >= 1 SOL: when (ms after our fill was seen), whether before our would-be 200 ms sell. FOLLOWERS: distinct buyers (not us) and
//!     their SOL after m in the next 1 / 2 / 5 slots.
//!   RECORDS: rearm_cand (every candidate at its holders check), rearm_window (every window, at its evaluation: holders, signals,
//!     end, tries, rows, fills with exits), rearm_tape (windows with a fill: every trade of the token from the dump to the last fill
//!     + 3 s). The 10-min obs_summary carries the totals (fills by row, paper P&L by size / exit).
use super::book::{self, Book, Ctx, Pos, TapeTr, Tok, Tr, BIG, F_BIG, F_OURS};
use super::{Cfg, Clock, Live, LiveEv, M_REARM};
use crate::tx::Pk;
use rustc_hash::{FxHashMap, FxHashSet};
use serde_json::{json, Value};
use std::collections::VecDeque;
use std::time::Instant;

/// the age gate: 30 s on the study's 0.212 s slot clock
pub const MAX_AGE_SLOTS: u64 = 141;
/// R0: arm at dump + 3, last slot dump + 3 + 20; R2: + 10
pub const WAIT: u64 = 3;
pub const G0: u64 = 20;
pub const G2: u64 = 10;
/// the stop's 30 ms (the live whale-sell stop)
pub const STOP_MS: u64 = 30;
/// QUIET stop 6:2
pub const QN: u64 = 6;
pub const QM: u32 = 2;
/// rows a / b / c (ms after the crossing trade)
pub const ROWS: [(&str, u64); 3] = [("a", 0), ("b", 5), ("c", 10)];
/// the trailing reference
pub const REF_NS: u64 = 50_000_000;
/// a paper position blocks its token's row until its sell + 300 ms
pub const MARGIN_NS: u64 = 300_000_000;
/// paper sizes (SOL)
pub const SIZES: [f64; 3] = [0.40, 0.65, 1.0];
pub const POLICIES: [&str; 6] = ["t200", "t300", "s2", "tp10", "tp20", "live"];
/// the tape after a fill
pub const FOLLOW_NS: u64 = 3_000_000_000;
/// a window is evaluated this long (feed time) after its end (the tailer's live records must be in)
pub const SETTLE_NS: u64 = 1_000_000_000;
/// a window's own tape starts this long before its dump (the 50 ms reference of its first trades)
const PRE_NS: u64 = 1_000_000_000;
/// windows / candidates in flight at most (a flood is counted, not followed)
const MAX_OPEN: usize = 2_000;
const UNTRADE: u64 = 100_000_000_000;

#[derive(Clone, Debug)]
struct Dump { tr: TapeTr, p_pre: f64, seller: Pk, left: i64, age_slots: u64, age_ms: Option<f64> }

impl Dump {
    fn json(&self) -> Value {
        json!({"sig": bs58::encode(&self.tr.sig).into_string(), "slot": self.tr.s, "idx": self.tr.i, "j": self.tr.j, "t": self.tr.t, "seller": book::b58(&self.seller),
               "sol": self.tr.sol, "tok": self.tr.tok, "pct": self.tr.tok as f64 / book::SUPPLY * 100.0, "seller_left_pct": self.left.max(0) as f64 / book::SUPPLY * 100.0,
               "p_pre": self.p_pre, "p": self.tr.p(), "drop_pct": (1.0 - self.tr.p() / self.p_pre.max(1e-30)) * 100.0, "vsol": self.tr.vsol, "vtok": self.tr.vtok,
               "age_slots": self.age_slots, "age_ms": self.age_ms})
    }
}

struct Cand { mint: Pk, dump: Dump, wait_slot: u64 }

#[derive(Clone, Debug, Default)]
struct Fill {
    row: usize, x: usize, m: usize, a_land: u64, lim: f64, refp: f64, s_in: u64,
}

struct Win {
    id: u64, mint: Pk, dump: Dump, holders: Vec<(Pk, i64, u64, u8, f64, u32)>, quiet: Value, r5_skip: bool,
    arm_slot: u64, t_arm: u64, en_slot: u64, en_slot2: u64,
    /// the end (t, why, clock slot then) and R2's end
    end: Option<(u64, &'static str, u64)>, end2: Option<(u64, &'static str)>,
    /// trades by anyone but us since the arm (QUIET stop), its decision (Some(stop?))
    others: u32, qdec: Option<bool>,
    /// the token's trades from PRE_NS before the dump on (arrival order)
    tape: Vec<TapeTr>, tape_cut: bool,
    /// rows: blocked at the arm
    blocked: [bool; 3],
    /// evaluation: phase 1 done (rows searched), the fills, the hit reason per row
    fills: Vec<Fill>, hits: [Option<&'static str>; 3], evaluated: bool, superseded: Option<u64>,
    tries: (u32, u32, u32), refused_t: Vec<u64>, slot_ns: u64,
    /// wall clock at the end (the feed-stall fallback)
    ended_at: Option<Instant>,
}

#[derive(Clone, Debug, Default)]
pub struct Stats {
    pub cands: u64, pub no_holder: u64, pub blocked_live: u64, pub windows: u64, pub evaluated: u64, pub fills: [u64; 3], pub blocked_rows: [u64; 3], pub late: [u64; 3],
    pub untradeable: [u64; 3], pub tries: u64, pub refused: u64, pub ends: FxHashMap<&'static str, u64>, pub r5_skip: u64, pub r2_fills: [u64; 3], pub flood: u64, pub tape_cut: u64,
    /// paper P&L (row c, slip model): per size x policy the sum (mSOL) and count / wins; the same for the naive variant
    pub pnl: [[f64; 6]; 3], pub pnl_naive: [[f64; 6]; 3], pub wins: [[u64; 6]; 3], pub n_pnl: u64,
    /// row a / b / c fills with the live policy at 0.65 SOL (mSOL)
    pub pnl_rows_live065: [f64; 3],
    pub second_seller: u64, pub second_before_200: u64,
}

pub struct Rearm {
    k: u64, drop: f64, cap: u64, user: Pk, coh: FxHashSet<Pk>, fb: FxHashSet<Pk>, fol: f64,
    cands: Vec<Cand>, wins: Vec<Win>, done: Vec<Win>,
    /// the re-arm's own would-be tries per unix second (the shared budget)
    re_sec: FxHashMap<u64, u32>, re_q: VecDeque<u64>,
    /// per token: each row's paper position free again at (feed time)
    free: FxHashMap<Pk, [u64; 3]>,
    /// mints with a candidate / window in flight (the book keeps them)
    busy: FxHashMap<Pk, u32>,
    wid: u64,
    pub st: Stats,
    live_arms: Vec<(Pk, u64)>,
}

impl Rearm {
    pub fn new(cfg: &Cfg) -> Rearm {
        Rearm { k: if cfg.k == 0 { 8 } else { cfg.k }, drop: if cfg.drop > 0.0 { cfg.drop } else { 0.12 }, cap: if cfg.rate_cap == 0 { 40 } else { cfg.rate_cap }, user: cfg.user,
            coh: cfg.cohort.clone(), fb: cfg.fbots.clone(), fol: if cfg.quiet_fol > 0.0 { cfg.quiet_fol } else { 2.24 }, cands: Vec::new(), wins: Vec::new(), done: Vec::new(),
            re_sec: FxHashMap::default(), re_q: VecDeque::new(), free: FxHashMap::default(), busy: FxHashMap::default(), wid: 0, st: Stats::default(), live_arms: Vec::new() }
    }
    pub fn busy(&self, m: &Pk) -> bool { self.busy.contains_key(m) }
    fn hold(&mut self, m: Pk) { *self.busy.entry(m).or_insert(0) += 1; }
    fn release(&mut self, m: &Pk) { if let Some(n) = self.busy.get_mut(m) { *n -= 1; if *n == 0 { self.busy.remove(m); } } }
    pub fn mem_bytes(&self) -> usize {
        self.wins.iter().chain(self.done.iter()).map(|w| w.tape.capacity() * std::mem::size_of::<TapeTr>() + 512).sum::<usize>() + self.cands.len() * 256 + self.free.len() * 64
            + self.re_sec.len() * 24
    }

    /// one trade (after the book took it)
    pub fn on_trade(&mut self, tok: &Tok, tr: &Tr, ctx: &Ctx, _clock: &Clock, recs: &mut Vec<(usize, Value)>) {
        let _ = recs;
        // the token's windows: their tapes, stops, the QUIET count
        for w in self.wins.iter_mut().chain(self.done.iter_mut()) {
            if w.mint != tr.mint { continue; }
            if w.tape.len() < 20_000 { w.tape.push(tok.tape.back().cloned().expect("the book just took this trade")); } else { w.tape_cut = true; }
            if w.end.is_some() { continue; }
            if tr.user != self.user { w.others += 1; }
            if !tr.buy && tr.tok as i64 >= BIG { w.end = Some((tr.t + STOP_MS * 1_000_000, "whale_dump", tr.s)); }
            else if ctx.nbig_after == 0 { w.end = Some((tr.t + STOP_MS * 1_000_000, "no_holder", tr.s)); }
            if w.end.is_some() && w.end2.is_none() { w.end2 = Some((w.end.unwrap().0, w.end.unwrap().1)); }
        }
        // a candidate dump
        if !tr.buy && tr.tok as i64 >= BIG && ctx.normal && tr.vsol < UNTRADE {
            let age = tr.s.saturating_sub(tok.s0);
            if age <= MAX_AGE_SLOTS {
                if self.cands.len() + self.wins.len() >= MAX_OPEN { self.st.flood += 1; return; }
                self.st.cands += 1;
                let d = Dump { tr: tok.tape.back().cloned().expect("just taken"), p_pre: tr.p_pre(), seller: tr.user, left: ctx.bal_after, age_slots: age, age_ms: tok.age_ms(tr.t) };
                self.cands.push(Cand { mint: tr.mint, dump: d, wait_slot: tr.s + WAIT });
                self.hold(tr.mint);
            }
        }
    }

    /// the slot clock moved to `slot` at `t` (before that tx's trades): holders checks, window starts / ends, the QUIET stops
    #[allow(clippy::too_many_arguments)]
    pub fn on_slot(&mut self, _prev: u64, slot: u64, t: u64, book: &Book, clock: &Clock, qb: Option<&crate::presend_quiet::DumpBook>, cfg: &Cfg, live: &Live, recs: &mut Vec<(usize, Value)>) {
        let _ = (clock, cfg);
        // windows: QUIET 6:2, R2 end, expiry
        for w in self.wins.iter_mut() {
            if w.end.is_none() && w.qdec.is_none() && slot >= w.arm_slot + QN {
                let stop = w.others < QM;
                w.qdec = Some(stop);
                if stop { w.end = Some((t, "quiet", slot)); }
            }
            if w.end2.is_none() && slot > w.en_slot2 { w.end2 = Some((t, if w.end.is_some() { w.end.unwrap().1 } else { "expired" })); }
            if w.end.is_none() && slot > w.en_slot { w.end = Some((t, "expired", slot)); }
            if w.end.is_some() && w.end2.is_none() { w.end2 = Some((w.end.unwrap().0, w.end.unwrap().1)); }
        }
        let mut i = 0;
        while i < self.wins.len() {
            if self.wins[i].end.is_some() {
                let mut w = self.wins.swap_remove(i);
                w.ended_at = Some(Instant::now());
                *self.st.ends.entry(w.end.unwrap().1).or_default() += 1;
                self.done.push(w);
            } else { i += 1; }
        }
        // candidates due: the holders at the end of slot dump + 2
        let due: Vec<Cand> = { let (a, b): (Vec<Cand>, Vec<Cand>) = std::mem::take(&mut self.cands).into_iter().partition(|c| slot >= c.wait_slot); self.cands = b; a };
        for c in due {
            let Some(tok) = book.get(&c.mint) else { self.release(&c.mint); continue };
            let holders = tok.holders();
            let mut rec = json!({"ev": "rearm_cand", "mint": book::b58(&c.mint), "dump": c.dump.json(), "check_slot": slot, "t_check": t, "holders": holders.len()});
            if holders.is_empty() {
                self.st.no_holder += 1;
                rec["verdict"] = "no_holder".into();
                recs.push((M_REARM, rec));
                self.release(&c.mint);
                continue;
            }
            // QUIET signals at the arm (a, b, c token-level; d per holder)
            let since_last = slot.saturating_sub(tok.last_s);
            let coh_hold = tok.wal.iter().filter(|(k, w)| w.bal > 0 && self.coh.contains(*k)).count() as u32;
            let fb_n = tok.wal.keys().filter(|k| self.fb.contains(*k)).count() as u32;
            let hs: Vec<(Pk, i64, u64, u8, f64, u32)> = holders.iter().map(|(k, b, fb, r)| {
                let (f, n) = qb.map(|q| q.whale(k, slot, t)).unwrap_or((-1.0, 0));
                (*k, *b, *fb, *r, f, n)
            }).collect();
            let top_fol = hs[0].4;
            let all4 = since_last >= 1 && coh_hold == 0 && fb_n < crate::presend_quiet::FB_MAX && top_fol < self.fol;
            let quiet = json!({"since_last": since_last, "coh_hold": coh_hold, "fb_n": fb_n, "wh_fol_top": top_fol, "fol": self.fol, "all4": all4,
                "q": [since_last >= 1, coh_hold == 0, fb_n < crate::presend_quiet::FB_MAX, top_fol < self.fol]});
            let live_armed = live.armed_now(&c.mint);
            if live_armed {
                self.st.blocked_live += 1;
                rec["verdict"] = "blocked_live_armed".into(); rec["quiet"] = quiet;
                recs.push((M_REARM, rec));
                self.release(&c.mint);
                continue;
            }
            self.wid += 1;
            self.st.windows += 1;
            if all4 { self.st.r5_skip += 1; }
            rec["verdict"] = "window".into(); rec["w"] = self.wid.into();
            recs.push((M_REARM, rec));
            let fr = self.free.get(&c.mint).copied().unwrap_or([0; 3]);
            let blocked = [fr[0] > t, fr[1] > t, fr[2] > t];
            for (r, b) in blocked.iter().enumerate() { if *b { self.st.blocked_rows[r] += 1; } }
            let d0 = c.dump.tr.s;
            let lo = c.dump.tr.t.saturating_sub(PRE_NS);
            let tape: Vec<TapeTr> = tok.tape.iter().filter(|x| x.t >= lo).cloned().collect();
            let cut = tok.tape.front().is_some_and(|x| x.t > lo && tok.tape.len() >= book::TAPE_MAX);
            self.wins.push(Win { id: self.wid, mint: c.mint, dump: c.dump, holders: hs, quiet, r5_skip: all4, arm_slot: slot, t_arm: t, en_slot: d0 + WAIT + G0,
                en_slot2: d0 + WAIT + G2, end: None, end2: None, others: 0, qdec: None, tape, tape_cut: cut, blocked, fills: Vec::new(),
                hits: [None; 3], evaluated: false, superseded: None, tries: (0, 0, 0), refused_t: Vec::new(), slot_ns: 0, ended_at: None });
            // (the candidate's hold on the mint passes to the window)
        }
    }

    /// a tailed live record (live T2 arms take a token over)
    pub fn on_live(&mut self, e: &LiveEv) {
        if let LiveEv::Arm { mint, t, .. } = e { self.live_arms.push((*mint, *t)); if self.live_arms.len() > 4096 { self.live_arms.drain(..2048); } }
    }

    /// evaluate the windows whose end is settled; write the ones whose fills' tapes are complete
    pub fn tick(&mut self, now: u64, force: bool, book: &Book, live: &Live, cfg: &Cfg, recs: &mut Vec<(usize, Value)>) {
        let _ = (book, cfg);
        let slot_ns = crate::feeds::entries::SLOT_US.load(std::sync::atomic::Ordering::Relaxed) * 1_000;
        let mut i = 0;
        while i < self.done.len() {
            let w = &self.done[i];
            let (t_end, _, _) = w.end.unwrap();
            let stalled = w.ended_at.is_some_and(|a| a.elapsed().as_secs() >= 10);
            if !(now >= t_end + SETTLE_NS || force || stalled) { i += 1; continue; }
            if !self.done[i].evaluated {
                let mut w = self.done.swap_remove(i);
                self.evaluate(&mut w, live, slot_ns);
                self.done.push(w);
                continue;
            }
            // phase 2: every fill's tape complete (the last landing + 3 s seen), or forced / stalled
            let last = w.fills.iter().map(|f| f.a_land).max().unwrap_or(0);
            if w.fills.is_empty() || now >= last + FOLLOW_NS + SETTLE_NS / 2 || force || stalled {
                let w = self.done.swap_remove(i);
                self.write(w, now, live, recs);
                continue;
            }
            i += 1;
        }
        // the per-second budget map: keep 30 min
        while self.re_q.front().is_some_and(|&s| s + 1800 < now / 1_000_000_000) { let s = self.re_q.pop_front().unwrap(); self.re_sec.remove(&s); }
        if self.free.len() > 20_000 { let n = now; self.free.retain(|_, f| f.iter().any(|&x| x > n)); }
    }

    /// phase 1: superseded, tries vs the budget, the rows' fills
    fn evaluate(&mut self, w: &mut Win, live: &Live, slot_ns: u64) {
        w.evaluated = true;
        self.st.evaluated += 1;
        let (mut t_end, mut why, s_end) = w.end.unwrap();
        // a live T2 window armed on the token during the window takes it over
        if let Some(&(_, ta)) = self.live_arms.iter().find(|(m, ta)| *m == w.mint && *ta >= w.t_arm && *ta < t_end) {
            w.superseded = Some(ta); t_end = ta; why = "superseded";
            w.end = Some((t_end, why, s_end));
            *self.st.ends.entry("superseded").or_default() += 1;
        }
        if w.end2.is_some_and(|e| e.0 > t_end) { w.end2 = Some((t_end, why)); }
        // tries (k per slot from the arm) vs the shared per-second budget
        w.slot_ns = slot_ns.max(1);
        let step = (w.slot_ns / self.k.max(1)).max(1);
        let (mut n, mut ok, mut refused) = (0u32, 0u32, 0u32);
        let mut tt = w.t_arm;
        while tt < t_end && n < 10_000 {
            n += 1;
            let s = tt / 1_000_000_000;
            let used = self.re_sec.get(&s).copied().unwrap_or(0);
            if (live.sent_in(s) + used) as u64 >= self.cap { refused += 1; w.refused_t.push(tt); }
            else { ok += 1; let c = self.re_sec.entry(s).or_insert(0); if *c == 0 { self.re_q.push_back(s); } *c += 1; }
            tt += step;
        }
        w.tries = (n, ok, refused);
        self.st.tries += n as u64; self.st.refused += refused as u64;
        // the rows
        let lim_of = |w: &Win, k: usize| -> f64 {
            let tx = w.tape[k].t;
            let r = w.tape[..k].iter().rposition(|y| y.t + REF_NS <= tx);
            match r { Some(r) => w.tape[r].p(), None => { let f = &w.tape[0]; pre_p(f) } }
        };
        for (r, &(_, dms)) in ROWS.iter().enumerate() {
            if w.blocked[r] { w.hits[r] = Some("blocked"); continue; }
            let mut k = w.tape.iter().position(|x| x.t >= w.t_arm).unwrap_or(w.tape.len());
            while k < w.tape.len() {
                let x = &w.tape[k];
                if x.t >= t_end { break; }
                let refp = lim_of(w, k);
                let lim = refp * (1.0 - self.drop);
                if !(x.p() <= lim) { k += 1; continue; }
                let a_land = x.t + dms * 1_000_000;
                if a_land >= t_end { w.hits[r] = Some("late"); self.st.late[r] += 1; break; }
                let mut m = k;
                while m + 1 < w.tape.len() && w.tape[m + 1].t <= a_land { m += 1; }
                let pm = w.tape[m].p();
                if !(pm <= lim) { k += 1; continue; }
                if w.tape[m].vsol >= UNTRADE { w.hits[r] = Some("untradeable"); self.st.untradeable[r] += 1; break; }
                w.fills.push(Fill { row: r, x: k, m, a_land, lim, refp, s_in: w.tape[m].s });
                self.st.fills[r] += 1;
                break;
            }
        }
    }

    /// phase 2: exits, second seller, followers; the records; the token's rows busy until each paper sell + 300 ms
    fn write(&mut self, w: Win, now: u64, live: &Live, recs: &mut Vec<(usize, Value)>) {
        let _ = now;
        let (t_end, why, s_end) = w.end.unwrap();
        let mut rows = serde_json::Map::new();
        let mut any_fill = false;
        for (r, &(name, _)) in ROWS.iter().enumerate() {
            let Some(f) = w.fills.iter().find(|f| f.row == r) else {
                rows.insert(name.into(), json!({"blocked": w.blocked[r], "fill": null, "hit": w.hits[r]}));
                continue;
            };
            any_fill = true;
            let x = &w.tape[f.x]; let m = &w.tape[f.m];
            let in_r2 = w.end2.is_some_and(|e| f.a_land < e.0) && f.s_in <= w.en_slot2;
            if in_r2 { self.st.r2_fills[r] += 1; }
            let refused_near = w.refused_t.iter().filter(|&&tt| tt + 100_000_000 >= x.t && tt <= f.a_land).count();
            // exits per size, both variants
            let after: Vec<&TapeTr> = w.tape[f.m + 1..].iter().filter(|y| y.t <= f.a_land + FOLLOW_NS + 2_000_000_000).collect();
            let mut px = serde_json::Map::new(); let mut pxn = serde_json::Map::new(); let mut whys = serde_json::Map::new(); let mut min_ok = Vec::new();
            let mut free_at = f.a_land + 200_000_000;
            for (si, &size) in SIZES.iter().enumerate() {
                let fr = m.fr as f64;
                // the live attempt's min-out (a try signed on the reference state): the tokens our buy gets after m must reach it
                let need = min_out_at_limit(f.refp, m, size, fr, self.drop);
                let got = book::buy_tokens(m.vsol as f64, m.vtok as f64, size * 1e9, fr).0;
                min_ok.push(got >= need);
                let (vals, ws, xt) = exits(m, &after, size * 1e9, fr, f.a_land, f.s_in, true);
                let (valsn, _, _) = exits(m, &after, size * 1e9, fr, f.a_land, f.s_in, false);
                if si == 1 { free_at = xt[5]; }
                let key = format!("{size:.2}");
                px.insert(key.clone(), json!(POLICIES.iter().zip(vals.iter()).map(|(p, v)| (p.to_string(), json!(round2(*v)))).collect::<serde_json::Map<String, Value>>()));
                pxn.insert(key.clone(), json!(POLICIES.iter().zip(valsn.iter()).map(|(p, v)| (p.to_string(), json!(round2(*v)))).collect::<serde_json::Map<String, Value>>()));
                whys.insert(key, json!(POLICIES.iter().zip(ws.iter()).map(|(p, v)| (p.to_string(), json!(v))).collect::<serde_json::Map<String, Value>>()));
                if r == 2 {
                    for (pi, v) in vals.iter().enumerate() { self.st.pnl[si][pi] += v; if *v > 0.0 { self.st.wins[si][pi] += 1; } }
                    for (pi, v) in valsn.iter().enumerate() { self.st.pnl_naive[si][pi] += v; }
                    if si == 0 { self.st.n_pnl += 1; }
                }
                if si == 1 { self.st.pnl_rows_live065[r] += vals[5]; }
            }
            let e = self.free.entry(w.mint).or_insert([0; 3]);
            e[r] = e[r].max(free_at + MARGIN_NS);
            // second seller, followers
            let s_in = f.s_in;
            let second = after.iter().find(|y| !y.buy && y.fl & F_OURS == 0 && y.s <= s_in + 2 && (y.fl & F_BIG != 0 || y.sol >= 1_000_000_000));
            let sj = second.map(|y| {
                let ms = (y.t as i64 - f.a_land as i64) as f64 / 1e6;
                json!({"t_ms": ms, "slot": y.s, "idx": y.i, "w": book::short(&y.user), "sol": y.sol, "tok": y.tok, "big": y.fl & F_BIG != 0, "before_200ms": ms < 200.0})
            });
            if r == 2 { if let Some(y) = second { self.st.second_seller += 1; if (y.t as i64 - f.a_land as i64) < 200_000_000 { self.st.second_before_200 += 1; } } }
            let fol = |k: u64| -> Value {
                let mut b: FxHashSet<Pk> = FxHashSet::default(); let mut sol = 0u64;
                for y in after.iter().filter(|y| y.buy && y.fl & F_OURS == 0 && y.s <= s_in + k) { b.insert(y.user); sol += y.sol; }
                json!([b.len(), sol])
            };
            rows.insert(name.into(), json!({"blocked": false, "hit": "fill", "fill": {
                "x": {"slot": x.s, "idx": x.i, "j": x.j, "t": x.t, "p": x.p(), "w": book::short(&x.user), "buy": x.buy, "sol": x.sol, "drop_pct": (1.0 - x.p() / f.refp) * 100.0},
                "ref": f.refp, "lim": f.lim, "m": {"slot": m.s, "idx": m.i, "j": m.j, "t": m.t, "p": m.p(), "vsol": m.vsol, "vtok": m.vtok}, "n_ahead": f.m - f.x,
                "a_land": f.a_land, "s_in": f.s_in, "ms_after_arm": (f.a_land as i64 - w.t_arm as i64) as f64 / 1e6, "slots_after_dump": f.s_in.saturating_sub(w.dump.tr.s),
                "r2": in_r2, "refused_near": refused_near, "live_pos_open": live.pos_open_at(f.a_land), "min_ok": min_ok,
                "px": px, "px_naive": pxn, "why": whys, "second": sj, "followers": {"s1": fol(1), "s2": fol(2), "s5": fol(5)}}}));
        }
        let mut rec = json!({"ev": "rearm_window", "w": w.id, "mint": book::b58(&w.mint), "dump": w.dump.json(),
            "holders": w.holders.iter().map(|(k, b, fb, role, f, n)| json!({"w": book::b58(k), "pct": *b as f64 / book::SUPPLY * 100.0, "first_buy": fb, "role": book::flags_str(*role),
                "wh_fol": f, "wh_dumps": n})).collect::<Vec<_>>(),
            "quiet": w.quiet, "r5_skip": w.r5_skip, "arm": {"slot": w.arm_slot, "t": w.t_arm}, "en_slot": w.en_slot, "en_slot_r2": w.en_slot2,
            "end": {"t": t_end, "why": why, "slot": s_end, "ms_after_arm": (t_end as i64 - w.t_arm as i64) as f64 / 1e6}, "end_r2": w.end2.map(|e| json!({"t": e.0, "why": e.1})),
            "superseded_live_t": w.superseded, "others": w.others, "quiet_stop": w.qdec, "tries": {"n": w.tries.0, "ok": w.tries.1, "refused": w.tries.2, "k": self.k, "cap": self.cap,
            "slot_ms": w.slot_ns as f64 / 1e6}, "n_tape": w.tape.len(), "tape_cut": w.tape_cut,
            "min_ratio": min_ratio(&w, t_end, self.drop), "rows": Value::Object(rows)});
        if w.tape_cut { self.st.tape_cut += 1; rec["tape_cut"] = true.into(); }
        recs.push((M_REARM, rec));
        if any_fill {
            let last = w.fills.iter().map(|f| f.a_land).max().unwrap_or(t_end) + FOLLOW_NS;
            let lo = w.dump.tr.t;
            let tape: Vec<Value> = w.tape.iter().filter(|y| y.t >= lo && y.t <= last).map(|y| y.json()).collect();
            recs.push((M_REARM, json!({"ev": "rearm_tape", "w": w.id, "mint": book::b58(&w.mint), "from_t": lo, "to_t": last, "n": tape.len(), "trades": tape})));
        }
        self.release(&w.mint);
    }

    /// the run's end: open windows end "run_end" and are written with what is known
    pub fn finish(&mut self, now: u64, book: &Book, live: &Live, cfg: &Cfg, recs: &mut Vec<(usize, Value)>) {
        for mut w in std::mem::take(&mut self.wins) { w.end = Some((now.max(w.t_arm), "run_end", 0)); if w.end2.is_none() { w.end2 = Some((now, "run_end")); } self.done.push(w); }
        self.tick(now, true, book, live, cfg, recs);
        self.tick(now, true, book, live, cfg, recs);
        for c in std::mem::take(&mut self.cands) {
            recs.push((M_REARM, json!({"ev": "rearm_cand", "mint": book::b58(&c.mint), "dump": c.dump.json(), "verdict": "run_end"})));
        }
    }

    pub fn status(&self) -> Value {
        let s = &self.st;
        json!({"cands": s.cands, "no_holder": s.no_holder, "blocked_live": s.blocked_live, "windows": s.windows, "evaluated": s.evaluated, "open": self.wins.len(), "pending": self.done.len(),
               "fills": s.fills, "blocked_rows": s.blocked_rows, "late": s.late, "untradeable": s.untradeable, "tries": s.tries, "refused": s.refused, "ends": s.ends,
               "r5_skip": s.r5_skip, "r2_fills": s.r2_fills, "flood": s.flood, "tape_cut": s.tape_cut})
    }
    pub fn summary(&self) -> Value {
        let s = &self.st;
        let tab = |a: &[[f64; 6]; 3]| -> Value { json!(SIZES.iter().enumerate().map(|(si, z)| (format!("{z:.2}"), json!(POLICIES.iter().enumerate().map(|(pi, p)| (p.to_string(), json!(round2(a[si][pi])))).collect::<serde_json::Map<String, Value>>()))).collect::<serde_json::Map<String, Value>>()) };
        let mut v = self.status();
        v["paper_row_c_msol"] = tab(&s.pnl); v["paper_row_c_naive_msol"] = tab(&s.pnl_naive);
        v["paper_row_c_wins"] = json!(SIZES.iter().enumerate().map(|(si, z)| (format!("{z:.2}"), json!(POLICIES.iter().enumerate().map(|(pi, p)| (p.to_string(), json!(s.wins[si][pi]))).collect::<serde_json::Map<String, Value>>()))).collect::<serde_json::Map<String, Value>>());
        v["paper_fills_row_c"] = s.n_pnl.into();
        v["live_policy_065_by_row_msol"] = json!([round2(s.pnl_rows_live065[0]), round2(s.pnl_rows_live065[1]), round2(s.pnl_rows_live065[2])]);
        v["second_seller_row_c"] = json!({"fills_hit": s.second_seller, "before_200ms": s.second_before_200});
        v
    }
}

fn round2(x: f64) -> f64 { (x * 100.0).round() / 100.0 }

fn pre_p(t: &TapeTr) -> f64 {
    let (v, k) = if t.buy { (t.vsol.saturating_sub(t.sol), t.vtok.saturating_add(t.tok)) } else { (t.vsol.saturating_add(t.sol), t.vtok.saturating_sub(t.tok)) };
    v as f64 / (k as f64).max(1.0)
}

/// the lowest post price / the 50 ms reference reached in the window (how close it came to a fill when it had none)
fn min_ratio(w: &Win, t_end: u64, _drop: f64) -> Option<f64> {
    let mut best: Option<f64> = None;
    for (k, x) in w.tape.iter().enumerate() {
        if x.t < w.t_arm || x.t >= t_end { continue; }
        let r = w.tape[..k].iter().rposition(|y| y.t + REF_NS <= x.t).map(|r| w.tape[r].p()).unwrap_or_else(|| pre_p(&w.tape[0]));
        let q = x.p() / r;
        best = Some(best.map_or(q, |b: f64| b.min(q)));
    }
    best.map(|b| (b * 1e4).round() / 1e4)
}

/// the tokens a try signed on the reference state would ask for (presend_live::limit_min_out on the curve whose price is the
/// reference: the limit state's buy), an approximation of the live min-out (the live try signs on its own latest state)
fn min_out_at_limit(refp: f64, m: &TapeTr, size: f64, fr: f64, drop: f64) -> f64 {
    // the curve through m with price refp: V T = k (m's product), V / T = refp
    let k = m.vsol as f64 * m.vtok as f64;
    let v = (k * refp).sqrt(); let t = k / v.max(1.0);
    match crate::presend_live::limit_min_out(v as u64, t as u64, (size * 1e9) as u64, fr, drop) { Some((q, _, _)) => q as f64, None => f64::INFINITY }
}

/// the paper exits of a position bought right after `m` (the trades `after` follow in order): per policy the gross mSOL, the
/// reason, the sell time (ns). Policies: t200, t300, s2, tp10, tp20, live
fn exits(m: &TapeTr, after: &[&TapeTr], size: f64, fr: f64, seen: u64, s_in: u64, slip: bool) -> ([f64; 6], [&'static str; 6], [u64; 6]) {
    let Some(p0) = Pos::open(m.vsol, m.vtok, size, fr, slip) else { return ([0.0; 6], ["untradeable"; 6], [seen; 6]) };
    let mut out = [f64::NAN; 6]; let mut why = [""; 6]; let mut xt = [0u64; 6];
    let mut p = p0;
    let pnl = |p: &Pos| (p.pnl() / 1e6 * 100.0).round() / 100.0;
    let (t200, t300) = (seen + 200_000_000, seen + 300_000_000);
    // state before each trade: decide the time exits on the first trade at / after their time; the value exits after each trade
    for y in after.iter() {
        let before = pnl(&p);
        // time-based exits: execute on the state before this trade (it is the first one seen at / after the decision time)
        if out[0].is_nan() && y.t >= t200 { out[0] = before; why[0] = "time"; xt[0] = y.t; }
        if out[1].is_nan() && y.t >= t300 { out[1] = before; why[1] = "time"; xt[1] = y.t; }
        if out[2].is_nan() && y.s >= s_in + 2 { out[2] = before; why[2] = "slot"; xt[2] = y.t; }
        for k in [3usize, 4] { if out[k].is_nan() && y.s >= s_in + 2 { out[k] = before; why[k] = "slot"; xt[k] = y.t; } }
        if out[5].is_nan() && (y.t >= t200 || y.s >= s_in + 2) { out[5] = before; why[5] = if y.t >= t200 { "time" } else { "slot" }; xt[5] = y.t; }
        // every real trade goes in (ours too: the curve is the chain's); the records count ours in the tape
        p.feed(y);
        let v = p.val();
        let now = pnl(&p);
        for (k, tp) in [(3usize, 1.10), (4, 1.20), (5, 1.20)] {
            if out[k].is_nan() { if v >= tp { out[k] = now; why[k] = "tp"; xt[k] = y.t; } else if v <= 0.80 { out[k] = now; why[k] = "sl"; xt[k] = y.t; } }
        }
        if out.iter().all(|x| !x.is_nan()) { break; }
    }
    // no trade after the decision time in the tape: the last state
    let last = pnl(&p);
    for k in 0..6 { if out[k].is_nan() { out[k] = last; why[k] = "tape_end"; xt[k] = after.last().map(|y| y.t).unwrap_or(seen); } }
    (out, why, xt)
}

#[cfg(test)]
pub(crate) fn exits_for_test(m: &TapeTr, after: &[&TapeTr], size: f64, fr: f64, seen: u64, s_in: u64, slip: bool) -> ([f64; 6], [&'static str; 6], [u64; 6]) { exits(m, after, size, fr, seen, s_in, slip) }
