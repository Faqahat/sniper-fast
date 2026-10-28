//! OBSERVATORY module 10: INSLOT paper (owner 10-29 03:00 PKT): would 8yYMhu's same-slot backrun work FOR US, anchored on OUR real seen
//! time of each sell (ops/strategies/rivals/8yYMhu/REPORT.md §3-4). LOG ONLY: `inslot` records (one per >= 1 SOL curve sell on a normal
//! token, same rate cap as module 7: <= 100 per minute) and the 10-min obs_summary "inslot".
//!   THE CLOCK (documented mapping): everything on OUR executed feed's arrival clock. Decision = t_rx of the sell + DECIDE_MS (3 ms, the
//!   live dip fire's decision time); landing L = decision + D, D in {15, 30, 45, 60, 90} ms. Our buy lands right before the first trade of
//!   the token seen after L (entry = the curve after every token trade seen by L). SAME-SLOT check (its Lighthouse slot <= dump slot):
//!   the landing is in the dump's slot iff our feed had not yet shown any tx of a later slot by L (the slot clock's first-seen time of
//!   slot s+1 > L); else "fail_slot". BAND check: the entry vSOL within [0.88, 1.04] x the post-dump vSOL, else "fail_band". A fail costs
//!   0.15 mSOL. With the feed race (module 9) on, the same is computed from the EARLIEST arrival of the sell over all feeds ("early_*":
//!   L = earliest + 3 ms + D on the same arrival clock: assumes the executed feed's delay is the same for every tx).
//!   SIZES 0.50 / 0.75 SOL (pump fee on top, our own impact; every later trade applied as it was). EXITS: the value at the end of entry
//!   slot + 3, + 6, + 9 and the 61-slot timeout (separate rows; its MAIN 3-or-6 split is not modelled). NET mSOL = SOL back after pump's
//!   fee - size - (0.5 buy priority + TIP_MSOL tip + 1.8 sell).
//!   PROFILE (its selection, §4): drop 8-25%, the seller sold >= 3% of supply, token age 5-150 slots, post-dump curve < 60 SOL, normal
//!   token (never mayhem); EU leaders not checked (no leader on this thread). took = 8yYMhu (on the watch list) bought it: its slot gap
//!   and block index.
use super::book::{self, Ctx, Pos, Tok, Tr};
use super::M_INSLOT;
use crate::tx::Pk;
use serde_json::{json, Value};

pub const DS: [u64; 5] = [15, 30, 45, 60, 90];
pub const SIZES: [f64; 2] = [0.5e9, 0.75e9];
pub const HOLDS: [u64; 4] = [3, 6, 9, 61];
pub const DECIDE_MS: u64 = 3;
pub const FAIL_MSOL: f64 = 0.15;
pub const TIP_MSOL: f64 = 1.0;
pub const COST_MSOL: f64 = 0.5 + TIP_MSOL + 1.8;
pub const RATE_PER_MIN: u32 = 100;
const MAX_OPEN: usize = 4096;
pub const RIVAL: &str = "8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3";

#[derive(Clone)]
struct Leg { l: u64, res: Option<&'static str>, pos: [Option<Pos>; 2], vals: [[Option<f64>; 4]; 2], entry_vsol: u64 }

struct Ev { mint: Pk, s: u64, i: u32, pos: (u64, u32, u32), t: u64, post_vsol: u64, last: (u64, u64, f64), next_t: Option<u64>, legs: Vec<Leg>, early: Option<u64>,
            profile: bool, took: Option<(u64, u32)>, rec: Value, dup: bool }

#[derive(Default, Clone)]
pub struct Agg { pub n: u64, pub fills: [u64; 10], pub fails: [u64; 10], pub pnl: [[[f64; 4]; 2]; 10] }

#[derive(Default)]
pub struct Inslot { open: Vec<Ev>, rival: Pk, minute: u64, in_minute: u32, pub records: u64, pub skipped: u64, pub agg: [Agg; 4] }

fn r4(x: f64) -> f64 { (x * 1e4).round() / 1e4 }

impl Inslot {
    pub fn new() -> Inslot { Inslot { rival: crate::tx::pk(RIVAL), ..Default::default() } }
    pub fn busy(&self, m: &Pk) -> bool { self.open.iter().any(|e| e.mint == *m) }
    pub fn mem_bytes(&self) -> usize { self.open.len() * 4096 }

    /// a trade (after the book took it); `early` = the earliest arrival of this tx over all feeds (module 9)
    pub fn on_trade(&mut self, tok: &Tok, tr: &Tr, ctx: &Ctx, early: Option<u64>) {
        let cur = tok.tape.back().expect("the book just took this trade");
        let rival = self.rival;
        for e in self.open.iter_mut().filter(|e| e.mint == tr.mint) {
            if cur.pos() <= e.pos { continue; }
            if tr.buy && tr.user == rival && e.took.is_none() && tr.s <= e.s + 2 { e.took = Some((tr.s - e.s, tr.i)); }
            // pending legs whose landing time passed: entry = the state before this trade
            for lg in e.legs.iter_mut() {
                if lg.res.is_none() && tr.t > lg.l { resolve(lg, e.last, e.post_vsol, e.next_t); }
                for p in lg.pos.iter_mut().flatten() { p.feed(cur); }
            }
            e.last = (tr.vsol, tr.vtok, tr.fr());
        }
        if !tr.buy && tr.sol >= 1_000_000_000 && ctx.normal {
            let minute = tr.t / 60_000_000_000;
            if minute != self.minute { self.minute = minute; self.in_minute = 0; }
            if self.in_minute >= RATE_PER_MIN || self.open.len() >= MAX_OPEN { self.skipped += 1; return; }
            self.in_minute += 1;
            let drop = 1.0 - tr.p() / tr.p_pre();
            let age = tr.s.saturating_sub(tok.s0);
            let profile = (0.08..=0.25).contains(&drop) && tr.tok >= 30_000_000_000_000 && (5..=150).contains(&age) && tr.vsol < 60_000_000_000;
            let mut legs: Vec<Leg> = DS.iter().map(|d| Leg { l: tr.t + (DECIDE_MS + d) * 1_000_000, res: None, pos: [None, None], vals: [[None; 4]; 2], entry_vsol: 0 }).collect();
            if let Some(et) = early.filter(|et| *et < tr.t) { legs.extend(DS.iter().map(|d| Leg { l: et + (DECIDE_MS + d) * 1_000_000, res: None, pos: [None, None], vals: [[None; 4]; 2], entry_vsol: 0 })); }
            // dip24.1 (10-29 live check): a >= 1 SOL sell while an earlier one of the same token (<= 3 slots before) is still open is the SAME
            // dump cluster: recorded with dup_of_slot, left out of the summary (it double-counted one opportunity)
            let dup_of = self.open.iter().filter(|e| e.mint == tr.mint && e.s + 3 >= tr.s).map(|e| e.s).min();
            let rec = json!({"ev": "inslot", "dup_of_slot": dup_of, "mint": book::b58(&tr.mint), "t": tr.t, "slot": tr.s, "idx": tr.i, "j": tr.j, "sol": tr.sol, "tok": tr.tok, "drop_pct": r4(drop * 100.0),
                "seller": book::short(&tr.user), "age_slots": age, "vsol": tr.vsol, "profile": profile, "early_t": early, "sig": bs58::encode(&tr.sig).into_string(), "rival": RIVAL});
            self.open.push(Ev { mint: tr.mint, s: tr.s, i: tr.i, pos: cur.pos(), t: tr.t, post_vsol: tr.vsol, last: (tr.vsol, tr.vtok, tr.fr()), next_t: None, legs, early, profile, took: None, rec, dup: dup_of.is_some() });
        }
    }

    /// the slot clock reached `slot` at `t`: same-slot verdicts, the values due, finished records
    pub fn on_slot(&mut self, slot: u64, t: u64, recs: &mut Vec<(usize, Value)>, all: bool) {
        let mut i = 0;
        while i < self.open.len() {
            let e = &mut self.open[i];
            if slot > e.s && e.next_t.is_none() { e.next_t = Some(t); }
            for lg in e.legs.iter_mut() {
                if lg.res.is_none() && (e.next_t.is_some() || all) { resolve(lg, e.last, e.post_vsol, e.next_t); }
                for (si, p) in lg.pos.iter().enumerate() {
                    let Some(p) = p else { continue };
                    for (k, h) in HOLDS.iter().enumerate() { if lg.vals[si][k].is_none() && (slot > e.s + h || all) { lg.vals[si][k] = Some(p.val()); } }
                }
            }
            let done = all || slot > e.s + HOLDS[3];
            if !done { i += 1; continue; }
            let e = self.open.swap_remove(i);
            self.write(e, recs);
        }
    }

    fn write(&mut self, e: Ev, recs: &mut Vec<(usize, Value)>) {
        self.records += 1;
        let mut r = e.rec;
        let groups: [usize; 4] = [0, if e.profile { 1 } else { 0 }, if e.took.is_some() { 2 } else { 0 }, if e.profile && e.took.is_some() { 3 } else { 0 }];
        let mut legs = serde_json::Map::new();
        for (k, lg) in e.legs.iter().enumerate() {
            let label = if k < DS.len() { format!("{}", DS[k]) } else { format!("early_{}", DS[k - DS.len()]) };
            let res = lg.res.unwrap_or("unresolved");
            let mut j = json!({"res": res, "entry_vsol": lg.entry_vsol});
            if res == "fill" {
                j["v"] = json!({"0.50": lg.vals[0].iter().map(|v| v.map(r4)).collect::<Vec<_>>(), "0.75": lg.vals[1].iter().map(|v| v.map(r4)).collect::<Vec<_>>()});
            }
            legs.insert(label, j);
            for (gi, g) in groups.iter().enumerate() {
                if e.dup || (gi > 0 && *g == 0) { continue; }
                let a = &mut self.agg[*g];
                if k == 0 { a.n += 1; }
                if res == "fill" {
                    a.fills[k] += 1;
                    for si in 0..2 { for h in 0..4 { if let Some(v) = lg.vals[si][h] { a.pnl[k][si][h] += (v - 1.0) * SIZES[si] / 1e6 - COST_MSOL; } } }
                } else if res.starts_with("fail") {
                    a.fails[k] += 1;
                    for si in 0..2 { for h in 0..4 { a.pnl[k][si][h] -= FAIL_MSOL; } }
                }
            }
        }
        r["legs"] = Value::Object(legs);
        r["took"] = e.took.map(|(ds, idx)| json!({"ds": ds, "idx": idx, "di": if ds == 0 { Some(idx as i64 - e.i as i64) } else { None }})).unwrap_or(Value::Null);
        r["holds"] = json!(HOLDS);
        recs.push((M_INSLOT, r));
    }

    pub fn status(&self) -> Value { json!({"records": self.records, "open": self.open.len(), "skipped": self.skipped}) }
    pub fn summary(&self) -> Value {
        let names = ["all", "profile", "rival_took", "profile_and_took"];
        json!(names.iter().enumerate().map(|(g, n)| {
            let a = &self.agg[g];
            let legs: serde_json::Map<String, Value> = (0..10).filter(|k| a.fills[*k] + a.fails[*k] > 0).map(|k| {
                let label = if k < DS.len() { format!("{}", DS[k]) } else { format!("early_{}", DS[k - DS.len()]) };
                (label, json!({"fills": a.fills[k], "fails": a.fails[k], "fill_rate": a.fills[k] as f64 / a.n.max(1) as f64,
                    "net_msol": {"0.50": a.pnl[k][0].iter().map(|x| (x * 10.0).round() / 10.0).collect::<Vec<_>>(), "0.75": a.pnl[k][1].iter().map(|x| (x * 10.0).round() / 10.0).collect::<Vec<_>>()}}))
            }).collect();
            (n.to_string(), json!({"n": a.n, "holds": HOLDS, "by_d": legs}))
        }).collect::<serde_json::Map<String, Value>>())
    }
}


/// a leg's landing decided: out of the dump's slot (the next slot was seen by L), out of the vSOL band, or a fill on `last`
fn resolve(lg: &mut Leg, last: (u64, u64, f64), post: u64, next_t: Option<u64>) {
    if next_t.is_some_and(|nt| nt <= lg.l) { lg.res = Some("fail_slot"); return; }
    let (v, t, fr) = last;
    lg.entry_vsol = v;
    let ratio = v as f64 / post.max(1) as f64;
    if !(0.88..=1.04).contains(&ratio) { lg.res = Some("fail_band"); return; }
    lg.pos = [Pos::open(v, t, SIZES[0], fr, false), Pos::open(v, t, SIZES[1], fr, false)];
    lg.res = Some(if lg.pos[0].is_some() { "fill" } else { "fail_band" });
}
