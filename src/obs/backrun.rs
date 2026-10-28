//! OBSERVATORY module 7: the BACKRUN census (owner 10-29 02:00 PKT; the same-slot backrunner 8yYMhuYo… class: fixed 0.75 SOL,
//! buys right behind >= 1 SOL sells, holds median 9 slots, middle half 6-31). LOG ONLY: the strategy's opportunity universe live,
//! who wins each sell (block-index gap), what each hold pays, and when OUR engine saw the sell (t = our t_rx).
//!   For every curve SELL >= 1 SOL on a normal token (seen from its create, not mayhem, standard curve): one backrun_sell record with
//!   the sell (t, slot, idx, j, SOL, one-trade drop %, seller short, token age, vSOL, signature), every BUY on the token after it in
//!   the same slot and the next 2 slots (wallet short, slot gap, block index, idx gap within the sell's slot, SOL, watched, ms after
//!   the sell on our clock; at most 20 listed, all counted), and the value path of a 0.75 SOL position (pump fee in, our own impact,
//!   every later trade applied as it was): "v_br" = bought on the curve right after the FIRST backrunner (we are second), "v_sell" =
//!   bought right after the sell (we are the first backrunner); value = SOL back after pump's fee / 0.75 at the end of entry slot +1,
//!   +2, +5, +9, +31 (sold into the curve with impact). Bounded: at most RATE_PER_MIN sells per minute of feed time (the rest counted),
//!   at most 16 open per token. With module 8 (--obs-select): "armable" = the seller's candidate classes / our live rule, and each buyer's
//!   "pro" = an auto-detected backrunner (select.rs).
use super::book::{self, Ctx, Pos, TapeTr, Tok, Tr};
use super::M_BACKRUN;
use crate::tx::Pk;
use rustc_hash::{FxHashMap, FxHashSet};
use serde_json::{json, Value};

pub const MIN_SELL: u64 = 1_000_000_000;
pub const SIZE: f64 = 750_000_000.0;
pub const HOLDS: [u64; 5] = [1, 2, 5, 9, 31];
pub const BUY_SLOTS: u64 = 2;
pub const MAX_BUYS: usize = 20;
pub const RATE_PER_MIN: u32 = 100;
const PER_TOKEN: usize = 16;

struct Ev {
    label: Value,
    mint: Pk, sell: TapeTr, drop: f64, age: (Option<u64>, Option<f64>),
    buys: Vec<Value>, n_buys: u32, buy_sol: u64,
    first: Option<(TapeTr, u64)>, pos_br: Option<Pos>, br_slot: u64, pos_sell: Option<Pos>,
    v_br: [Option<f64>; 5], v_sell: [Option<f64>; 5],
}

#[derive(Clone, Debug, Default)]
pub struct Stats { pub sells: u64, pub records: u64, pub rate_skipped: u64, pub token_skipped: u64, pub with_br: u64, pub same_slot_br: u64, pub watched_first: u64 }

#[derive(Default)]
pub struct Backrun { open: Vec<Ev>, per_tok: FxHashMap<Pk, u32>, minute: u64, in_minute: u32, pub st: Stats }

fn r4(x: f64) -> f64 { (x * 1e4).round() / 1e4 }

impl Backrun {
    pub fn busy(&self, m: &Pk) -> bool { self.per_tok.contains_key(m) }
    pub fn mem_bytes(&self) -> usize { self.open.len() * 2048 }

    pub fn on_trade(&mut self, tok: &Tok, tr: &Tr, ctx: &Ctx, watch: &FxHashSet<Pk>, sel: Option<&super::select::Select>, recs: &mut Vec<(usize, Value)>) {
        let _ = recs;
        let cur = tok.tape.back().expect("the book just took this trade");
        if self.per_tok.contains_key(&tr.mint) {
            for e in self.open.iter_mut().filter(|e| e.mint == tr.mint) {
                if cur.pos() <= e.sell.pos() { continue; }
                // the buys after the sell in its slot and the next 2
                if tr.buy && tr.s <= e.sell.s + BUY_SLOTS {
                    e.n_buys += 1; e.buy_sol += tr.sol;
                    if e.buys.len() < MAX_BUYS {
                        e.buys.push(json!({"w": book::short(&tr.user), "ds": tr.s - e.sell.s, "idx": tr.i, "di": if tr.s == e.sell.s { Some(tr.i as i64 - e.sell.i as i64) } else { None },
                            "sol": tr.sol, "wt": watch.contains(&tr.user), "pro": sel.map(|x| x.is_pro(&tr.user, tr.t)), "ms": (tr.t as i64 - e.sell.t as i64) as f64 / 1e6}));
                    }
                    if e.first.is_none() {
                        e.first = Some((cur.clone(), tr.t));
                        e.br_slot = tr.s;
                        e.pos_br = Pos::open(tr.vsol, tr.vtok, SIZE, tr.fr(), false);
                        if let Some(p) = e.pos_sell.as_mut() { p.feed(cur); }
                        continue;
                    }
                }
                if let Some(p) = e.pos_sell.as_mut() { p.feed(cur); }
                if let Some(p) = e.pos_br.as_mut() { p.feed(cur); }
            }
        }
        if !tr.buy && tr.sol >= MIN_SELL && ctx.normal {
            self.st.sells += 1;
            let minute = tr.t / 60_000_000_000;
            if minute != self.minute { self.minute = minute; self.in_minute = 0; }
            if self.in_minute >= RATE_PER_MIN { self.st.rate_skipped += 1; return; }
            let n = self.per_tok.entry(tr.mint).or_insert(0);
            if *n as usize >= PER_TOKEN { self.st.token_skipped += 1; return; }
            *n += 1;
            self.in_minute += 1;
            let drop = 1.0 - tr.p() / tr.p_pre();
            self.open.push(Ev { label: sel.map(|x| x.label(&tr.mint, &tr.user)).unwrap_or(Value::Null), mint: tr.mint, sell: cur.clone(), drop, age: (tok.age_slots(tr.s), tok.age_ms(tr.t)), buys: Vec::new(), n_buys: 0, buy_sol: 0, first: None,
                pos_br: None, br_slot: 0, pos_sell: Pos::open(tr.vsol, tr.vtok, SIZE, tr.fr(), false), v_br: [None; 5], v_sell: [None; 5] });
        }
    }

    /// the slot clock reached `slot` (every trade of the slots before it is in): the values due; the finished records
    pub fn on_slot(&mut self, slot: u64, recs: &mut Vec<(usize, Value)>) {
        for e in self.open.iter_mut() {
            for (k, h) in HOLDS.iter().enumerate() {
                if e.v_sell[k].is_none() && slot > e.sell.s + h { e.v_sell[k] = Some(e.pos_sell.as_ref().map(|p| r4(p.val())).unwrap_or(f64::NAN)); }
                if e.first.is_some() && e.v_br[k].is_none() && slot > e.br_slot + h { e.v_br[k] = Some(e.pos_br.as_ref().map(|p| r4(p.val())).unwrap_or(f64::NAN)); }
            }
        }
        self.flush(slot, false, recs);
    }

    fn flush(&mut self, slot: u64, all: bool, recs: &mut Vec<(usize, Value)>) {
        let mut i = 0;
        while i < self.open.len() {
            let e = &self.open[i];
            let br_done = slot > e.sell.s + BUY_SLOTS && (e.first.is_none() || e.v_br[4].is_some());
            if !(all || (e.v_sell[4].is_some() && br_done)) { i += 1; continue; }
            let e = self.open.swap_remove(i);
            if let Some(n) = self.per_tok.get_mut(&e.mint) { *n -= 1; if *n == 0 { self.per_tok.remove(&e.mint); } }
            self.st.records += 1;
            if let Some((f, _)) = &e.first { self.st.with_br += 1; if f.s == e.sell.s { self.st.same_slot_br += 1; } if f.fl & book::F_WATCHED != 0 { self.st.watched_first += 1; } }
            let s = &e.sell;
            let fj = e.first.as_ref().map(|(f, t)| json!({"w": book::short(&f.user), "ds": f.s - s.s, "idx": f.i, "di": if f.s == s.s { Some(f.i as i64 - s.i as i64) } else { None },
                "sol": f.sol, "ms": (*t as i64 - s.t as i64) as f64 / 1e6, "wt": f.fl & book::F_WATCHED != 0}));
            let vals = |v: &[Option<f64>; 5]| json!(v.iter().map(|x| x.filter(|y| y.is_finite())).collect::<Vec<_>>());
            recs.push((M_BACKRUN, json!({"ev": "backrun_sell", "mint": book::b58(&e.mint), "t": s.t, "slot": s.s, "idx": s.i, "j": s.j, "sol": s.sol, "tok": s.tok,
                "drop_pct": r4(e.drop * 100.0), "seller": book::short(&s.user), "seller_fl": book::flags_str(s.fl), "age_slots": e.age.0, "age_ms": e.age.1, "vsol": s.vsol,
                "sig": bs58::encode(&s.sig).into_string(), "n_buys": e.n_buys, "buy_sol": e.buy_sol, "buys": e.buys, "first": fj, "holds": HOLDS, "size": SIZE / 1e9,
                "v_br": vals(&e.v_br), "v_sell": vals(&e.v_sell), "armable": e.label, "partial": all && e.v_sell[4].is_none()})));
        }
    }

    pub fn tick(&mut self, _now: u64, force: bool, recs: &mut Vec<(usize, Value)>) { if force { self.flush(u64::MAX, true, recs); } }

    pub fn status(&self) -> Value {
        let s = &self.st;
        json!({"sells": s.sells, "records": s.records, "open": self.open.len(), "rate_skipped": s.rate_skipped, "token_skipped": s.token_skipped, "with_backrunner": s.with_br,
               "same_slot_backrunner": s.same_slot_br, "watched_first": s.watched_first})
    }
    pub fn summary(&self) -> Value { self.status() }
}
