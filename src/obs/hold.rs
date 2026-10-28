//! OBSERVATORY module 2: the HOLD TAPE of every LIVE pre-send fill (the second-seller exit study: our biggest losses). LOG ONLY.
//! The live records come from the tailer (the run's own --dip-log: presend_live_fill / _exit / _sell_land / _close); the trades from
//! the observatory's book (arrival order, the executed feed's t_rx clock).
//!   * on a presend_live_fill: the token's trades from THE DUMP THAT FILLED US (as the engine's own attempt-landing record picks it:
//!     the sell with the biggest one-trade price drop >= 2% in the 2 slots before our fill, before it in chain order; none: from 2 s
//!     before the fill) until 3 s after our fill, each with: slot, idx, t, side, SOL, tokens, wallet short, flags (B = held >= 6%
//!     before or after the trade, C creator, I create-slot insider, S the create's signer, W watched, O ours) and the holding after it;
//!   * our exit: the decision (presend_live_exit: why, slot, t = the decision's time on the feed clock), every sell landing seen
//!     (slot, idx, t, SOL), the close (curve P&L). The pre-send sell's SEND time is not recorded by the engine (its sell loop prints
//!     SELL-TIMING only for reactive exits); the sell is built and written right at the decision (no RPC first), so decision ~ send;
//!   * derived: the first >= 1 SOL sell and the first sell by a >= 6% holder after our fill (not ours): ms after our fill was seen,
//!     whether it was seen before our sell decision and by how many ms; followers (distinct buyers, SOL) in the next 1 / 2 / 5 slots.
//!   * the record (hold_tape) is written once our fill + 3 s is in the tape and the position closed (or 20 s of feed time passed).
use super::book::{self, Book, Ctx, TapeTr, Tok, Tr, F_BIG, F_OURS};
use super::{LiveEv, M_HOLD};
use crate::tx::Pk;
use rustc_hash::FxHashSet;
use serde_json::{json, Value};

pub const AFTER_NS: u64 = 3_000_000_000;
const WAIT_NS: u64 = 20_000_000_000;
const MAX_OPEN: usize = 256;

struct Tape {
    mint: Pk, w: u64, fill_sig: String, fill_slot: u64, fill_idx: u64, t_fill: u64, rec: Value,
    trades: Vec<TapeTr>, dump: Option<usize>, exit: Option<Value>, exit_t: Option<u64>, sells: Vec<Value>, close: Option<Value>, done_close: bool,
    /// the fill trade's position in `trades` (once seen)
    fill_k: Option<usize>, started: std::time::Instant,
}

#[derive(Clone, Debug, Default)]
pub struct Stats { pub fills: u64, pub tapes: u64, pub no_fill_trade: u64, pub second_1sol: u64, pub second_big: u64, pub before_decision: u64, pub overflow: u64 }

#[derive(Default)]
pub struct Hold { open: Vec<Tape>, pub st: Stats, mints: FxHashSet<Pk> }

impl Hold {
    pub fn busy(&self, m: &Pk) -> bool { self.mints.contains(m) }
    pub fn mem_bytes(&self) -> usize { self.open.iter().map(|t| t.trades.capacity() * std::mem::size_of::<TapeTr>() + 1024).sum() }

    pub fn on_trade(&mut self, tok: &Tok, tr: &Tr, _ctx: &Ctx, _recs: &mut Vec<(usize, Value)>) {
        if !self.mints.contains(&tr.mint) { return; }
        for t in self.open.iter_mut().filter(|t| t.mint == tr.mint) {
            if tr.t <= t.t_fill + AFTER_NS + 1_000_000_000 && t.trades.len() < 5_000 { t.trades.push(tok.tape.back().cloned().expect("just taken")); }
        }
    }

    pub fn on_live(&mut self, e: &LiveEv, book: &Book, recs: &mut Vec<(usize, Value)>) {
        let _ = recs;
        match e {
            LiveEv::Fill { w, mint, sig, slot, idx, t, rec, .. } => {
                self.st.fills += 1;
                if self.open.len() >= MAX_OPEN { self.st.overflow += 1; return; }
                // the trades already seen (the fill record comes after the fill trade): from 5 s before the fill
                let trades: Vec<TapeTr> = book.get(mint).map(|tk| tk.tape.iter().filter(|x| x.t + 5_000_000_000 >= *t).cloned().collect()).unwrap_or_default();
                self.mints.insert(*mint);
                self.open.push(Tape { mint: *mint, w: *w, fill_sig: sig.clone(), fill_slot: *slot, fill_idx: *idx, t_fill: *t, rec: rec.clone(), trades, dump: None, exit: None,
                    exit_t: None, sells: Vec::new(), close: None, done_close: false, fill_k: None, started: std::time::Instant::now() });
            }
            LiveEv::Exit { mint, why, slot, t, value, round } => {
                if let Some(tp) = self.open.iter_mut().rev().find(|x| x.mint == *mint && x.exit.is_none()) {
                    tp.exit = Some(json!({"why": why, "slot": slot, "t": t, "value": value, "round": round, "ms_after_fill": (*t as i64 - tp.t_fill as i64) as f64 / 1e6}));
                    tp.exit_t = Some(*t);
                }
            }
            LiveEv::SellLand { mint, sig, slot, idx, t, sol } => {
                if let Some(tp) = self.open.iter_mut().rev().find(|x| x.mint == *mint) {
                    tp.sells.push(json!({"sig": sig, "slot": slot, "idx": idx, "t": t, "sol": sol, "ms_after_fill": (*t as i64 - tp.t_fill as i64) as f64 / 1e6,
                        "ms_after_decision": tp.exit_t.map(|d| (*t as i64 - d as i64) as f64 / 1e6)}));
                }
            }
            LiveEv::Close { mint, rec } => {
                if let Some(tp) = self.open.iter_mut().rev().find(|x| x.mint == *mint && !x.done_close) {
                    tp.close = Some(json!({"curve_pnl": rec["curve_pnl"], "exit_why": rec["exit_why"], "result": rec["result"], "rounds": rec["rounds"], "held_s": rec["held_s"],
                        "sell_lands": rec["sell_lands"]}));
                    tp.done_close = true;
                }
            }
            _ => {}
        }
    }

    pub fn tick(&mut self, now: u64, force: bool, book: &Book, recs: &mut Vec<(usize, Value)>) {
        let _ = book;
        let mut i = 0;
        while i < self.open.len() {
            let t = &self.open[i];
            let full = now >= t.t_fill + AFTER_NS + 500_000_000;
            let stale = now >= t.t_fill + WAIT_NS || t.started.elapsed().as_secs() >= 60;
            if force || (full && t.done_close) || stale {
                let t = self.open.swap_remove(i);
                let m = t.mint;
                self.write(t, recs);
                if !self.open.iter().any(|x| x.mint == m) { self.mints.remove(&m); }
                continue;
            }
            i += 1;
        }
    }

    pub fn finish(&mut self, book: &Book, recs: &mut Vec<(usize, Value)>) { self.tick(u64::MAX, true, book, recs); }

    fn write(&mut self, mut t: Tape, recs: &mut Vec<(usize, Value)>) {
        self.st.tapes += 1;
        t.trades.sort_by_key(|x| x.pos());
        t.trades.dedup_by_key(|x| x.pos());
        // our fill in the tape (its signature)
        let fill_k = t.trades.iter().position(|x| bs58::encode(&x.sig).into_string() == t.fill_sig && x.fl & F_OURS != 0)
            .or_else(|| t.trades.iter().position(|x| x.s == t.fill_slot && x.i as u64 == t.fill_idx));
        t.fill_k = fill_k;
        if fill_k.is_none() { self.st.no_fill_trade += 1; }
        let fpos = fill_k.map(|k| t.trades[k].pos()).unwrap_or((t.fill_slot, t.fill_idx as u32, 0));
        // the dump that filled us: the biggest one-trade drop (>= 2%) among the sells in the 2 slots before our fill, before it
        let dump = t.trades.iter().enumerate().filter(|(_, x)| !x.buy && x.pos() < fpos && x.s + 2 >= t.fill_slot)
            .map(|(k, x)| (k, 1.0 - x.p() / pre_p(x))).filter(|(_, d)| *d >= 0.02).max_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));
        t.dump = dump.map(|d| d.0);
        let from_k = t.dump.unwrap_or_else(|| t.trades.iter().position(|x| x.t + 2_000_000_000 >= t.t_fill).unwrap_or(0));
        let to_t = t.t_fill + AFTER_NS;
        let tape: Vec<Value> = t.trades.iter().enumerate().filter(|(k, x)| *k >= from_k && x.t <= to_t).map(|(_, x)| x.json()).collect();
        // second sellers after our fill
        let after: Vec<&TapeTr> = t.trades.iter().filter(|x| x.pos() > fpos && x.t <= to_t + 5_000_000_000 && x.fl & F_OURS == 0).collect();
        let dec = t.exit_t;
        let sj = |x: Option<&&TapeTr>| -> Value {
            match x {
                None => Value::Null,
                Some(x) => json!({"slot": x.s, "idx": x.i, "t": x.t, "w": book::short(&x.user), "sol": x.sol, "tok": x.tok, "big": x.fl & F_BIG != 0,
                    "ms_after_fill": (x.t as i64 - t.t_fill as i64) as f64 / 1e6, "seen_before_decision": dec.map(|d| x.t < d),
                    "ms_before_decision": dec.map(|d| (d as i64 - x.t as i64) as f64 / 1e6)}),
            }
        };
        let s1 = after.iter().find(|x| !x.buy && x.sol >= 1_000_000_000);
        let sb = after.iter().find(|x| !x.buy && x.fl & F_BIG != 0);
        if s1.is_some() { self.st.second_1sol += 1; }
        if sb.is_some() { self.st.second_big += 1; }
        if [s1, sb].iter().flatten().any(|x| dec.is_some_and(|d| x.t < d)) { self.st.before_decision += 1; }
        let fol = |k: u64| -> Value {
            let mut b: FxHashSet<Pk> = FxHashSet::default(); let mut sol = 0u64;
            for x in after.iter().filter(|x| x.buy && x.s <= t.fill_slot + k) { b.insert(x.user); sol += x.sol; }
            json!([b.len(), sol])
        };
        recs.push((M_HOLD, json!({"ev": "hold_tape", "w": t.w, "mint": book::b58(&t.mint), "fill": {"sig": t.fill_sig, "slot": t.fill_slot, "idx": t.fill_idx, "t": t.t_fill,
            "tokens": t.rec["tokens"], "sol_in": t.rec["sol_in"], "path": t.rec["path"], "client": t.rec["client"], "p_sign": t.rec["p_sign"], "lim": t.rec["lim"],
            "slots_after_trigger": t.rec["slots_after_trigger"], "ms_send_to_rx": t.rec["ms_send_to_rx"], "in_tape": fill_k.is_some()},
            "dump": t.dump.map(|k| { let x = &t.trades[k]; let mut j = x.json(); j["drop_pct"] = json!((1.0 - x.p() / pre_p(x)) * 100.0); j["ms_before_fill"] = json!((t.t_fill as i64 - x.t as i64) as f64 / 1e6); j }),
            "exit": t.exit, "send_t": null, "send_note": "the pre-send sell's send time is not recorded by the engine; it is written at the decision (no RPC first)",
            "sells": t.sells, "close": t.close, "first_1sol_sell": sj(s1), "first_big_sell": sj(sb), "followers": {"s1": fol(1), "s2": fol(2), "s5": fol(5)},
            "n": tape.len(), "trades": tape})));
    }

    pub fn status(&self) -> Value {
        let s = &self.st;
        json!({"fills": s.fills, "tapes": s.tapes, "open": self.open.len(), "no_fill_trade": s.no_fill_trade, "second_1sol": s.second_1sol, "second_big": s.second_big,
               "seen_before_decision": s.before_decision, "overflow": s.overflow})
    }
    pub fn summary(&self) -> Value { self.status() }
}

fn pre_p(t: &TapeTr) -> f64 {
    let (v, k) = if t.buy { (t.vsol.saturating_sub(t.sol), t.vtok.saturating_add(t.tok)) } else { (t.vsol.saturating_add(t.sol), t.vtok.saturating_sub(t.tok)) };
    v as f64 / (k as f64).max(1.0)
}
