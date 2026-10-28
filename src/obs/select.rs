//! OBSERVATORY module 8: the SELECTION census (owner 10-29 02:45 PKT: "monitoring that can later help us WIDEN OUR SELECTION").
//! LOG ONLY. Normal tokens only (seen from the create, not mayhem, standard curve).
//!   (a) select_cand: every buy that takes a wallet from < 3% to >= 3% of supply (a crossing; a wallet can cross again after selling
//!       below), with its CLASS: creator / insider (create-slot buyer) / first_buy (its first trade on the token) / repeat (it crossed
//!       before) / laddered (a later buy crossing); whether OUR live rule (presend_live Detector: the wallet's first >= 3% crossing,
//!       holding >= whale_pct (6%) at that buy, not the creator, not a create-slot insider, curve < 100 SOL) arms it and if not why;
//!       token age, vSOL, the QUIET signals (since_last, coh_hold, fb_n, wh_fol, wh_dumps), the token's trades / distinct buyers of the
//!       last 60 s and 120 s; and the outcome over the next 50 slots: the holder's first sell (slot gap, % of its holding sold, one-trade
//!       drop %), the rebound after it (max post price over its next 1..15 slots / the post-dump price), followers (distinct buyers and
//!       SOL after the dump in its slot and the next 2), and the paper value of our standard pre-send fill if that dump dropped the
//!       price >= 12% (0.65 SOL bought right after it, sold before the first trade seen >= 200 ms later; gross mSOL, no costs), flagged
//!       inside a 10 / 20 / 30-slot window from the crossing. Written 50 slots after the crossing (or 15 slots after its dump).
//!   (b) labels for every >= 1 SOL curve sell (on the backrun_sell record): the seller's candidate classes on the token and whether
//!       our live rule armed it ("armable"); each buyer after it flagged "pro" when it is an AUTO-DETECTED backrunner: a wallet that
//!       bought after >= 1 SOL sells (same slot / next 2) >= 50 times in the last 6 h (hourly buckets; at most MAX_PROS wallets kept).
//!   (c) the 10-min obs_summary: per class: candidates, live-armable, dumps within 10 / 20 / 30 slots, paper fills and P&L (mSOL).
use super::book::{self, Ctx, Pos, Tok, Tr};
use super::M_SELECT;
use crate::tx::Pk;
use rustc_hash::{FxHashMap, FxHashSet};
use serde_json::{json, Value};
use std::collections::VecDeque;

pub const X3: i64 = 30_000_000_000_000;
pub const HORIZON: u64 = 50;
pub const REBOUND: u64 = 15;
pub const CLASSES: [&str; 5] = ["creator", "insider", "first_buy", "laddered", "repeat"];
const MAX_OPEN: usize = 5_000;
const MAX_PROS: usize = 200_000;
pub const PRO_MIN: u32 = 50;

#[derive(Default)]
struct STok { ring: VecDeque<(u64, Pk, bool)>, crossed: FxHashMap<Pk, (u8, bool)>, last_big_sell: Option<(u64, u32, u32, Pk)>, counted: Vec<Pk>, last_t: u64 }

struct Cand {
    mint: Pk, w: Pk, s: u64, t: u64, class: u8, live: bool, why: &'static str, rec: Value,
    dump: Option<(u64, u64, f64, f64, f64)>, // slot, t, pct sold, drop, post price
    rebound: f64, fol: FxHashSet<Pk>, fol_sol: u64, paper: Option<Pos>, paper_out: Option<f64>, t_exit: u64,
}

#[derive(Clone, Debug, Default)]
pub struct Agg { pub n: u64, pub live: u64, pub d10: u64, pub d20: u64, pub d30: u64, pub fills: u64, pub pnl: f64 }

#[derive(Default)]
pub struct Stats { pub cands: u64, pub written: u64, pub flood: u64, pub per_class: [Agg; 5], pub pros: u64 }

#[derive(Default)]
pub struct Select { toks: FxHashMap<Pk, STok>, cands: Vec<Cand>, pros: FxHashMap<Pk, ([u16; 6], u64)>, pub st: Stats, coh: FxHashSet<Pk>, fb: FxHashSet<Pk>, fol: f64, whale_pct: f64, last_sweep: u64 }

fn cls_of(c: u8) -> &'static str { CLASSES[c as usize] }

impl Select {
    pub fn new(cfg: &super::Cfg) -> Select { Select { coh: cfg.cohort.clone(), fb: cfg.fbots.clone(), fol: if cfg.quiet_fol > 0.0 { cfg.quiet_fol } else { 2.24 }, whale_pct: 6.0, ..Default::default() } }
    pub fn busy(&self, m: &Pk) -> bool { self.cands.iter().any(|c| c.mint == *m) }
    pub fn mem_bytes(&self) -> usize { self.toks.values().map(|t| 256 + t.ring.len() * 48 + t.crossed.len() * 48).sum::<usize>() + self.cands.len() * 1024 + self.pros.len() * 64 }

    /// the rolling 6 h count of a wallet's buys after >= 1 SOL sells
    fn pro_count(&self, w: &Pk, hour: u64) -> u32 {
        self.pros.get(w).map(|(b, h)| if hour >= h + 6 { 0 } else { b.iter().map(|x| *x as u32).sum() }).unwrap_or(0)
    }
    pub fn is_pro(&self, w: &Pk, t: u64) -> bool { self.pro_count(w, t / 3_600_000_000_000) >= PRO_MIN }
    /// (b): the seller's classes on the token and whether our live rule armed it
    pub fn label(&self, mint: &Pk, seller: &Pk) -> Value {
        match self.toks.get(mint).and_then(|t| t.crossed.get(seller)) {
            Some((m, live)) => json!({"classes": (0..5).filter(|k| m & (1 << k) != 0).map(|k| CLASSES[k]).collect::<Vec<_>>(), "live": live}),
            None => json!({"classes": [], "live": false}),
        }
    }

    pub fn on_trade(&mut self, tok: &Tok, tr: &Tr, ctx: &Ctx, qb: Option<&crate::presend_quiet::DumpBook>, recs: &mut Vec<(usize, Value)>) {
        if !ctx.normal { return; }
        let hour = tr.t / 3_600_000_000_000;
        // the pros: a buy after a >= 1 SOL sell of the token (same slot / next 2), once per sell and wallet
        let st = self.toks.entry(tr.mint).or_default();
        st.last_t = tr.t;
        let lo = tr.t.saturating_sub(120_000_000_000);
        while st.ring.front().is_some_and(|x| x.0 < lo) { st.ring.pop_front(); }
        if tr.buy {
            if let Some((ss, _, _, seller)) = st.last_big_sell {
                if tr.s <= ss + 2 && tr.user != seller && !st.counted.contains(&tr.user) && st.counted.len() < 64 {
                    st.counted.push(tr.user);
                    if self.pros.len() < MAX_PROS || self.pros.contains_key(&tr.user) {
                        let e = self.pros.entry(tr.user).or_insert(([0; 6], hour));
                        if hour > e.1 { let k = (hour - e.1).min(6) as usize; e.0.rotate_left(k); for x in e.0.iter_mut().rev().take(k) { *x = 0; } e.1 = hour; }
                        e.0[5] = e.0[5].saturating_add(1);
                        if e.0.iter().map(|x| *x as u32).sum::<u32>() == PRO_MIN { self.st.pros += 1; }
                    }
                }
            }
        } else if tr.sol >= 1_000_000_000 { st.last_big_sell = Some((tr.s, tr.i, tr.j, tr.user)); st.counted.clear(); }
        // the token's open candidates: the holder's dump, the rebound, the followers, the paper fill
        let cur = tok.tape.back().expect("the book just took this trade");
        for c in self.cands.iter_mut().filter(|c| c.mint == tr.mint) {
            match c.dump {
                None => {
                    if !tr.buy && tr.user == c.w && tr.s <= c.s + HORIZON {
                        let pct = tr.tok as f64 / (ctx.bal_before.max(1) as f64);
                        let drop = 1.0 - tr.p() / tr.p_pre();
                        c.dump = Some((tr.s, tr.t, pct, drop, tr.p()));
                        if drop >= 0.12 { c.paper = Pos::open(tr.vsol, tr.vtok, 0.65e9, tr.fr(), false); }
                    }
                }
                Some((ds, dt, _, _, pp)) => {
                    if tr.s <= ds + REBOUND { c.rebound = c.rebound.max(tr.p() / pp); }
                    if tr.buy && tr.s <= ds + 2 { c.fol.insert(tr.user); c.fol_sol += tr.sol; }
                    if let Some(p) = c.paper.as_mut() {
                        if c.paper_out.is_none() {
                            if tr.t >= dt + 200_000_000 { c.paper_out = Some((p.pnl() / 1e6 * 100.0).round() / 100.0); c.t_exit = tr.t; } else { p.feed(cur); }
                        }
                    }
                }
            }
        }
        // (a) a 3% crossing
        if tr.buy && ctx.bal_before < X3 && ctx.bal_after >= X3 && tok.hist {
            let st = self.toks.entry(tr.mint).or_default();
            let prev = st.crossed.get(&tr.user).copied();
            let w = tok.wal.get(&tr.user).copied().unwrap_or_default();
            let class: u8 = if ctx.fl & book::F_CREATOR != 0 { 0 } else if w.ins { 1 } else if prev.is_some() { 4 } else if w.n == 1 { 2 } else { 3 };
            let pct = ctx.bal_after as f64 / book::SUPPLY * 100.0;
            let first = prev.is_none();
            let why: &'static str = if !first { "not_first_crossing" } else if class == 0 { "creator" } else if class == 1 { "insider" }
                else if tr.vsol >= 100_000_000_000 { "curve_100" } else if (pct as f32 as f64) < self.whale_pct { "below_6pct_at_crossing" } else { "" };
            let live = why.is_empty();
            let e = st.crossed.entry(tr.user).or_insert((0, false));
            e.0 |= 1 << class; e.1 |= live;
            if self.cands.len() >= MAX_OPEN { self.st.flood += 1; } else {
                self.st.cands += 1;
                let (n60, b60, n120, b120) = {
                    let lo60 = tr.t.saturating_sub(60_000_000_000);
                    let (mut n60, mut n120) = (0u32, 0u32); let (mut b60, mut b120): (FxHashSet<Pk>, FxHashSet<Pk>) = Default::default();
                    for (t, u, b) in &st.ring { n120 += 1; if *b { b120.insert(*u); } if *t >= lo60 { n60 += 1; if *b { b60.insert(*u); } } }
                    (n60, b60.len(), n120, b120.len())
                };
                let since_last = if ctx.prev_s == 0 { 9999 } else { tr.s.saturating_sub(ctx.prev_s) };
                let coh = tok.wal.iter().filter(|(k, w)| w.bal > 0 && **k != tr.user && self.coh.contains(*k)).count();
                let fbn = tok.wal.keys().filter(|k| **k != tr.user && self.fb.contains(*k)).count();
                let (wf, wd) = qb.map(|q| q.whale(&tr.user, tr.s, tr.t)).unwrap_or((-1.0, 0));
                let rec = json!({"mint": book::b58(&tr.mint), "w": book::short(&tr.user), "slot": tr.s, "idx": tr.i, "t": tr.t, "pct_after": pct, "buy_sol": tr.sol,
                    "class": cls_of(class), "live_arms": live, "why_not": if live { Value::Null } else { why.into() }, "age_slots": tok.age_slots(tr.s), "age_ms": tok.age_ms(tr.t),
                    "vsol": tr.vsol, "quiet": {"since_last": since_last, "coh_hold": coh, "fb_n": fbn, "wh_fol": wf, "wh_dumps": wd,
                        "all4": since_last >= 1 && coh == 0 && fbn < 2 && wf < self.fol}, "n60": n60, "b60": b60, "n120": n120, "b120": b120});
                self.cands.push(Cand { mint: tr.mint, w: tr.user, s: tr.s, t: tr.t, class, live, why, rec, dump: None, rebound: 0.0, fol: Default::default(), fol_sol: 0, paper: None,
                    paper_out: None, t_exit: 0 });
            }
        }
        let st = self.toks.entry(tr.mint).or_default();
        st.ring.push_back((tr.t, tr.user, tr.buy));
        if st.ring.len() > 4096 { st.ring.pop_front(); }
        let _ = recs;
    }

    /// the clock: finished candidates written; idle tokens forgotten
    pub fn on_slot(&mut self, slot: u64, now: u64, recs: &mut Vec<(usize, Value)>, all: bool) {
        let mut i = 0;
        while i < self.cands.len() {
            let c = &self.cands[i];
            let due = all || match c.dump { Some((ds, ..)) => slot > ds + REBOUND && (c.paper.is_none() || c.paper_out.is_some() || slot > ds + REBOUND + 5), None => slot > c.s + HORIZON };
            if !due { i += 1; continue; }
            let mut c = self.cands.swap_remove(i);
            let a = &mut self.st.per_class[c.class as usize];
            a.n += 1; if c.live { a.live += 1; }
            let gap = c.dump.map(|d| d.0 - c.s);
            if let Some(g) = gap { if g <= 10 { a.d10 += 1; } if g <= 20 { a.d20 += 1; } if g <= 30 { a.d30 += 1; } }
            if c.paper.is_some() && c.paper_out.is_none() { c.paper_out = c.paper.as_ref().map(|p| (p.pnl() / 1e6 * 100.0).round() / 100.0); }
            if let Some(v) = c.paper_out { a.fills += 1; a.pnl += v; }
            let mut r = std::mem::take(&mut c.rec);
            r["ev"] = "select_cand".into();
            r["outcome"] = match c.dump {
                None => json!({"dump": null}),
                Some((ds, dt, pct, drop, _)) => json!({"dump": {"slot_gap": ds - c.s, "ms": (dt as i64 - c.t as i64) as f64 / 1e6, "pct_sold": (pct * 1e4).round() / 1e4,
                    "drop_pct": (drop * 1e4).round() / 100.0}, "rebound_15": (c.rebound * 1e4).round() / 1e4, "followers": [c.fol.len(), c.fol_sol],
                    "paper_065_msol": c.paper_out, "in_window": [gap.is_some_and(|g| g <= 10), gap.is_some_and(|g| g <= 20), gap.is_some_and(|g| g <= 30)]}),
            };
            self.st.written += 1;
            recs.push((M_SELECT, r));
        }
        if now > self.last_sweep + 30_000_000_000 {
            self.last_sweep = now;
            let busy: FxHashSet<Pk> = self.cands.iter().map(|c| c.mint).collect();
            self.toks.retain(|m, t| busy.contains(m) || now.saturating_sub(t.last_t) < 1_800_000_000_000);
            let hour = now / 3_600_000_000_000;
            if self.pros.len() > MAX_PROS / 2 { self.pros.retain(|_, (b, h)| hour < *h + 6 && b.iter().map(|x| *x as u32).sum::<u32>() >= 3); }
        }
    }

    pub fn status(&self) -> Value { json!({"cands": self.st.cands, "written": self.st.written, "open": self.cands.len(), "flood": self.st.flood, "pros_detected": self.st.pros, "tokens": self.toks.len()}) }
    pub fn summary(&self) -> Value {
        let mut v = self.status();
        v["per_class"] = json!(CLASSES.iter().enumerate().map(|(k, n)| { let a = &self.st.per_class[k];
            (n.to_string(), json!({"n": a.n, "live_arms": a.live, "dump_10": a.d10, "dump_20": a.d20, "dump_30": a.d30, "paper_fills": a.fills, "paper_msol": (a.pnl * 100.0).round() / 100.0})) })
            .collect::<serde_json::Map<String, Value>>());
        v
    }
}
