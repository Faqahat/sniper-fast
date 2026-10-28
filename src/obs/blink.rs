//! OBSERVATORY module 5: the BLINK causal launch-dump trigger (ported from /home/moiz/sniper-blink/src/blink.rs, parity-checked
//! and causal there; BLINK_PORT.md). NO model (BLINK failed on honest features): every trigger is logged with its 22 features so
//! we can measure how late we see sub-second launch dumps. LOG ONLY.
//! Books: one per token from its CreateEvent (the create slot included, no age / size gate). The token's clock, dev and seller
//! classes follow ev.py: s0 = the slot of the token's FIRST TRADE (not the create), dev = the first trader; a creation-slot bundler =
//! bought in slot s0; an early buyer = bought in the first 10 slots; counted from what was seen BEFORE the trade (causal). Curve
//! sanity (common.py build): the first trade starts from a pristine curve (|vsol before - 30 SOL| < 0.002 SOL), every trade sits on
//! the normal curve (|vsol x vtok / K0 - 1| < 0.5%), fee > 0, no mayhem; a token failing a check gets no triggers from then on.
//! TRIGGER: a sell within 28 slots of s0 whose one-trade drop (1 - (v / (v + sol))^2) is >= 3% by a dev / bundler / early buyer.
//! blink_trigger record: t_rx, slot, idx, j, sig, class, seller, age (ms since the create as seen, slots since s0), in_create_slot,
//! the 22 features (ev.py order: FEATURES), the slot's first-seen time on our feed and our seen lag within the slot (t_rx minus
//! it). Block time: not carried by the executed feed (only the slot); the recorder's bt joins offline.
use super::book::Tr;
use super::{Clock, M_BLINK};
use crate::tx::{b58, Pk};
use rustc_hash::FxHashMap;
use serde_json::{json, Value};
use std::collections::VecDeque;

pub const FEATURES: [&str; 22] = ["drop", "sellsol", "tpct", "cls", "frac", "sellerleft", "sellerprev", "age", "vsol", "ntr", "nbuyers", "buy5", "sell5",
    "nsells", "maxv", "devbuy", "nbund", "ne10", "devleft", "bundleft", "gap", "fee"];
pub const NF: usize = 22;
pub const SLOT_S: f64 = 0.212;
pub const SUP: f64 = 1e15;
pub const K0: f64 = 30e9 * 1.073e15;
pub const MAX_AGE_SLOTS: u64 = 28;
pub const E10_SLOTS: u64 = 10;
pub const W5_SLOTS: u64 = 24;
pub const MIN_DROP: f64 = 0.03;
const PRISTINE_VSOL: f64 = 30e9;
const PRISTINE_TOL: f64 = 2e6;
const NORMAL_TOL: f64 = 0.005;
const SWEEP_SLOTS: u64 = 400;
pub const CLS_DEV: u8 = 3;
pub const CLS_BUNDLER: u8 = 2;
pub const CLS_EARLY: u8 = 1;

/// one trade as BLINK reads it (fee_bps = protocol + creator)
#[derive(Clone, Debug)]
pub struct In { pub mint: Pk, pub s: u64, pub i: u32, pub j: i32, pub sig: [u8; 64], pub user: Pk, pub buy: bool, pub sol: u64, pub tok: u64, pub vsol: u64, pub vtok: u64, pub fee_bps: u64, pub t_rx: u64 }

#[derive(Default, Clone, Copy)]
struct U { held: i128, sells: u32, bought: bool, bund: bool, e10: bool }

pub struct Book {
    pub create_slot: u64, pub create_t_rx: u64, pub creator: Pk,
    pub s0: Option<u64>, cr: Pk, devbuy: u64,
    n: u64, last_slot: u64,
    users: FxHashMap<Pk, U>, nbuyers: u64, nsells: u64, nbund: u64, ne10: u64, bund_held: i128,
    win: VecDeque<(u64, bool, u64)>, buy5: u64, sell5: u64,
    maxv: f64,
    pub bad: Option<&'static str>,
}

impl Book {
    pub fn new(create_slot: u64, create_t_rx: u64, creator: Pk) -> Book {
        Book { create_slot, create_t_rx, creator, s0: None, cr: [0; 32], devbuy: 0, n: 0, last_slot: 0, users: FxHashMap::default(), nbuyers: 0, nsells: 0,
               nbund: 0, ne10: 0, bund_held: 0, win: VecDeque::new(), buy5: 0, sell5: 0, maxv: f64::MIN, bad: None }
    }
    #[inline]
    pub fn class(&self, user: &Pk) -> u8 {
        if self.s0.is_some() && *user == self.cr { return CLS_DEV; }
        match self.users.get(user) { Some(u) if u.bund => CLS_BUNDLER, Some(u) if u.e10 => CLS_EARLY, _ => 0 }
    }
    fn sane(&mut self, t: &In) -> bool {
        if self.bad.is_some() { return false; }
        if self.s0.is_none() {
            let pre = if t.buy { t.vsol as f64 - t.sol as f64 } else { t.vsol as f64 + t.sol as f64 };
            if (pre - PRISTINE_VSOL).abs() >= PRISTINE_TOL { self.bad = Some("not_pristine"); return false; }
        }
        if (t.vsol as f64 * t.vtok as f64 / K0 - 1.0).abs() >= NORMAL_TOL { self.bad = Some("abnormal_curve"); return false; }
        if t.fee_bps == 0 { self.bad = Some("fee0"); return false; }
        true
    }
    #[inline]
    fn prune_win(&mut self, s: u64) {
        let lo = s.saturating_sub(W5_SLOTS);
        while let Some(&(ws, b, sol)) = self.win.front() {
            if ws >= lo { break; }
            if b { self.buy5 -= sol; } else { self.sell5 -= sol; }
            self.win.pop_front();
        }
    }
    /// ev.py's 22 features of a sell `t` on this book's state BEFORE it -> (features, class, drop)
    pub fn features(&mut self, t: &In) -> ([f64; NF], u8, f64) {
        let s0 = self.s0.unwrap_or(t.s);
        let v = t.vsol as f64; let sol = t.sol as f64; let tok = t.tok as f64;
        let r = v / (v + sol); let dr = 1.0 - r * r;
        let cls = self.class(&t.user);
        let u = self.users.get(&t.user).copied().unwrap_or_default();
        let held = u.held as f64;
        self.prune_win(t.s);
        let crh = if t.user == self.cr { held } else { self.users.get(&self.cr).map(|x| x.held as f64).unwrap_or(0.0) };
        let bh = (self.bund_held - if u.bund { u.held } else { 0 }) as f64;
        let sellerleft = (held - tok).max(0.0) / SUP;
        let maxv = self.maxv.max(v);
        let x: [f64; NF] = [
            dr, sol / 1e9, tok / SUP, cls as f64, tok / held.max(1.0), sellerleft, u.sells as f64,
            t.s.saturating_sub(s0) as f64 * SLOT_S, v / 1e9, self.n as f64, self.nbuyers as f64, self.buy5 as f64 / 1e9, self.sell5 as f64 / 1e9,
            self.nsells as f64, maxv / 1e9, self.devbuy as f64 / 1e9, self.nbund as f64, self.ne10 as f64,
            if t.user != self.cr { crh.max(0.0) / SUP } else { sellerleft }, bh / SUP,
            if self.n > 0 { t.s.saturating_sub(self.last_slot) as f64 * SLOT_S } else { 9.0 }, t.fee_bps as f64,
        ];
        (x, cls, dr)
    }
    /// apply a trade (after any trigger evaluation on it)
    pub fn apply(&mut self, t: &In) {
        if self.s0.is_none() { self.s0 = Some(t.s); self.cr = t.user; self.devbuy = if t.buy { t.sol } else { 0 }; }
        let s0 = self.s0.unwrap();
        let u = self.users.entry(t.user).or_default();
        if t.buy {
            if !u.bought { u.bought = true; self.nbuyers += 1; }
            u.held += t.tok as i128;
            let mut newly = false;
            if t.s == s0 && !u.bund { u.bund = true; self.nbund += 1; newly = true; }
            if t.s.saturating_sub(s0) < E10_SLOTS && !u.e10 { u.e10 = true; self.ne10 += 1; }
            if newly { self.bund_held += u.held; } else if u.bund { self.bund_held += t.tok as i128; }
        } else {
            u.held -= t.tok as i128; u.sells += 1; self.nsells += 1;
            if u.bund { self.bund_held -= t.tok as i128; }
        }
        self.win.push_back((t.s, t.buy, t.sol));
        if t.buy { self.buy5 += t.sol; } else { self.sell5 += t.sol; }
        self.maxv = self.maxv.max(t.vsol as f64);
        self.n += 1; self.last_slot = t.s;
    }
}

#[derive(Default, Debug, Clone)]
pub struct Stats { pub creates: u64, pub mayhem: u64, pub trades: u64, pub triggers: u64, pub by_cls: [u64; 4], pub bad: u64, pub in_create_slot: u64, pub under_1s: u64,
                   pub lag_sum_ms: f64, pub lag_n: u64 }

#[derive(Default)]
pub struct Blink { books: FxHashMap<Pk, Book>, pub st: Stats, last_sweep: u64 }

impl Blink {
    pub fn books(&self) -> usize { self.books.len() }
    pub fn mem_bytes(&self) -> usize { self.books.values().map(|b| 512 + b.users.capacity() * 80 + b.win.capacity() * 24).sum() }
    pub fn create(&mut self, mint: Pk, slot: u64, creator: Pk, mayhem: bool, t_rx: u64) {
        self.st.creates += 1;
        if mayhem { self.st.mayhem += 1; return; }
        self.books.entry(mint).or_insert_with(|| Book::new(slot, t_rx, creator));
    }
    /// one trade (before the shared book takes it; BLINK has its own)
    pub fn push(&mut self, tr: &Tr, clock: &Clock, recs: &mut Vec<(usize, Value)>) {
        let Some(b) = self.books.get_mut(&tr.mint) else { return };
        self.st.trades += 1;
        let t = In { mint: tr.mint, s: tr.s, i: tr.i, j: tr.j as i32, sig: tr.sig, user: tr.user, buy: tr.buy, sol: tr.sol, tok: tr.tok, vsol: tr.vsol, vtok: tr.vtok,
                     fee_bps: tr.fbps as u64 + tr.cbps as u64, t_rx: tr.t };
        if let Some(s0) = b.s0 { if t.s.saturating_sub(s0) > MAX_AGE_SLOTS { self.books.remove(&tr.mint); return; } }
        if !b.sane(&t) { self.st.bad += 1; b.apply(&t); return; }
        if !t.buy && b.s0.is_some() {
            let (x, cls, dr) = b.features(&t);
            if dr >= MIN_DROP && cls != 0 {
                let s0 = b.s0.unwrap();
                self.st.triggers += 1; self.st.by_cls[cls as usize] += 1;
                let in_create = t.s == b.create_slot;
                if in_create { self.st.in_create_slot += 1; }
                let age_ms = if b.create_t_rx > 0 && t.t_rx >= b.create_t_rx { Some((t.t_rx - b.create_t_rx) as f64 / 1e6) } else { None };
                if t.s.saturating_sub(s0) as f64 * SLOT_S < 1.0 { self.st.under_1s += 1; }
                let first = clock.reached(t.s).filter(|_| clock.cur >= t.s);
                let lag = first.map(|f| (t.t_rx as i64 - f as i64) as f64 / 1e6);
                if let Some(l) = lag { self.st.lag_sum_ms += l; self.st.lag_n += 1; }
                recs.push((M_BLINK, json!({"ev": "blink_trigger", "mint": b58(&t.mint), "slot": t.s, "idx": t.i, "j": t.j, "sig": bs58::encode(&t.sig).into_string(), "t_rx": t.t_rx,
                    "cls": cls, "seller": b58(&t.user), "age_ms": age_ms, "age_slots": t.s.saturating_sub(s0), "age_slots_create": t.s.saturating_sub(b.create_slot),
                    "in_create_slot": in_create, "create_slot": b.create_slot, "s0": s0, "drop": dr, "sell_sol": t.sol, "vsol": t.vsol, "vtok": t.vtok,
                    "features": x.to_vec(), "slot_first_t": first, "seen_lag_in_slot_ms": lag, "block_time": null})));
            }
        }
        b.apply(&t);
    }
    pub fn advance(&mut self, slot_now: u64) {
        if slot_now == 0 || slot_now < self.last_sweep + 16 { return; }
        self.last_sweep = slot_now;
        self.books.retain(|_, b| match b.s0 { Some(s0) => slot_now <= s0 + MAX_AGE_SLOTS, None => slot_now <= b.create_slot + SWEEP_SLOTS });
    }
    pub fn status(&self) -> Value {
        let s = &self.st;
        json!({"books": self.books.len(), "creates": s.creates, "mayhem": s.mayhem, "trades": s.trades, "triggers": s.triggers, "by_cls_dev_bund_early": [s.by_cls[3], s.by_cls[2], s.by_cls[1]],
               "in_create_slot": s.in_create_slot, "under_1s": s.under_1s, "bad": s.bad, "seen_lag_in_slot_ms_mean": if s.lag_n > 0 { Some(s.lag_sum_ms / s.lag_n as f64) } else { None }})
    }
}
