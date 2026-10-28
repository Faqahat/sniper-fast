//! OBSERVATORY module 4: MIGRATION (near-graduation; the migpaper test: ops/strategies/e2x1_dissect/migpaper/ needs our REAL seen
//! times instead of a modelled 66 ms). LOG ONLY. Normal tokens only (seen from the create, not mayhem, standard curve).
//!   mig_v100: the first trade whose post curve takes vSOL >= 100 SOL (the pre-send arm point of the migpaper ARM-gate row);
//!   mig_v105: the first trade with vSOL >= 105 SOL that does NOT complete the curve (the migpaper trigger; a sell there is flagged:
//!     the study does not enter it); each with t, slot, idx, vSOL, side, SOL, token age, and the trailing 1 / 5 / 10 s flow (net buy
//!     SOL = buys - sells, distinct buyers, trades) on the arrival clock;
//!   mig_complete: the trade that completed the curve (vtok = 279.9e12 after a buy: every CompleteEvent of the recording has it),
//!     as seen (t), and ms after the v105 crossing;
//!   mig_follow: 10 s after each v100 / v105 trigger: the forward 1 / 5 / 10 s flow, the max vSOL reached, completed or not;
//!   mig_migrate: the migration tx (an executed tx with no pump trade that names PumpSwap and one of the completed mints) as seen:
//!     slot, t, signature, ms after the completion; mig_pool_tx: later executed txs naming PumpSwap and the migrated mint (only the ones
//!     the feed carries: the executed feed subscribes to the pump program, so pool trades that do not touch pump are NOT seen; the
//!     PumpSwap events are not decoded: signature and t only).
use super::book::{self, Book, Ctx, Tok, Tr};
use super::{RawIn, M_MIGR};
use crate::tx::Pk;
use rustc_hash::FxHashMap;
use serde_json::{json, Value};

const V100: u64 = 100_000_000_000;
const V105: u64 = 105_000_000_000;
const FOLLOW_NS: u64 = 10_000_000_000;
const KEEP_NS: u64 = 3_600_000_000_000;
const POOL_TX_MAX: u32 = 5;

#[derive(Default, Clone, Copy)]
struct St { v100: Option<u64>, v105: Option<u64>, complete: Option<u64>, migrated: Option<u64>, pool_txs: u32 }

#[derive(Clone, Debug, Default)]
pub struct Stats { pub v100: u64, pub v105: u64, pub v105_sell: u64, pub completes: u64, pub migrations: u64, pub migrations_unmatched: u64, pub pool_txs: u64, pub records: u64, pub raw: u64 }

#[derive(Default)]
pub struct Migr { toks: FxHashMap<Pk, St>, follow: Vec<(Pk, u64, &'static str, u64, u64)>, pub st: Stats }

/// the flow in [lo, hi) of a token's tape: (net buy SOL, distinct buyers, trades)
fn flow(tok: &Tok, lo: u64, hi: u64) -> Value {
    let (mut net, mut n) = (0i64, 0u32);
    let mut b: rustc_hash::FxHashSet<Pk> = Default::default();
    for x in tok.tape.iter().filter(|x| x.t >= lo && x.t < hi) { n += 1; if x.buy { net += x.sol as i64; b.insert(x.user); } else { net -= x.sol as i64; } }
    json!({"net_sol": net as f64 / 1e9, "buyers": b.len(), "trades": n})
}

impl Migr {
    pub fn busy(&self, m: &Pk) -> bool { self.follow.iter().any(|f| f.0 == *m) }
    pub fn mem_bytes(&self) -> usize { self.toks.len() * 96 + self.follow.len() * 64 }

    pub fn on_trade(&mut self, tok: &Tok, tr: &Tr, ctx: &Ctx, recs: &mut Vec<(usize, Value)>) {
        if !ctx.normal || tr.vsol < V100 && !ctx.completes { return; }
        let st = self.toks.entry(tr.mint).or_default();
        let base = |ev: &str| json!({"ev": ev, "mint": book::b58(&tr.mint), "t": tr.t, "slot": tr.s, "idx": tr.i, "j": tr.j, "vsol": tr.vsol as f64 / 1e9, "buy": tr.buy, "sol": tr.sol,
            "w": book::short(&tr.user), "age_slots": tok.age_slots(tr.s), "age_ms": tok.age_ms(tr.t), "sig": bs58::encode(&tr.sig).into_string()});
        let trail = |r: &mut Value| { for (k, w) in [("f1", 1u64), ("f5", 5), ("f10", 10)] { r[k] = flow(tok, tr.t.saturating_sub(w * 1_000_000_000), tr.t); } };
        if st.v100.is_none() && tr.vsol >= V100 {
            st.v100 = Some(tr.t);
            let mut r = base("mig_v100"); trail(&mut r);
            recs.push((M_MIGR, r)); self.st.v100 += 1; self.st.records += 1;
            self.follow.push((tr.mint, tr.t, "v100", tr.s, tr.vsol));
        }
        if st.v105.is_none() && tr.vsol >= V105 && !ctx.completes {
            st.v105 = Some(tr.t);
            let mut r = base("mig_v105"); trail(&mut r);
            r["v100_ms_before"] = json!(st.v100.map(|a| (tr.t as i64 - a as i64) as f64 / 1e6));
            if !tr.buy { self.st.v105_sell += 1; r["note"] = "the crossing trade is a sell (the study does not enter)".into(); }
            recs.push((M_MIGR, r)); self.st.v105 += 1; self.st.records += 1;
            self.follow.push((tr.mint, tr.t, "v105", tr.s, tr.vsol));
        }
        if ctx.completes && st.complete.is_none() {
            st.complete = Some(tr.t);
            let mut r = base("mig_complete");
            r["ms_after_v105"] = json!(st.v105.map(|a| (tr.t as i64 - a as i64) as f64 / 1e6));
            r["ms_after_v100"] = json!(st.v100.map(|a| (tr.t as i64 - a as i64) as f64 / 1e6));
            trail(&mut r);
            recs.push((M_MIGR, r)); self.st.completes += 1; self.st.records += 1;
        }
    }

    /// an executed tx naming PumpSwap without a pump trade: a migration (it names a completed mint not yet migrated) or a pool tx
    pub fn on_raw(&mut self, r: &RawIn, book: &Book, recs: &mut Vec<(usize, Value)>) {
        self.st.raw += 1;
        let mut hit = false;
        for k in &r.keys {
            let Some(st) = self.toks.get_mut(k) else { continue };
            let Some(tc) = st.complete else { continue };
            hit = true;
            if st.migrated.is_none() {
                st.migrated = Some(r.t_rx);
                self.st.migrations += 1; self.st.records += 1;
                let age = book.get(k).map(|tk| (tk.age_slots(r.slot), tk.age_ms(r.t_rx)));
                recs.push((M_MIGR, json!({"ev": "mig_migrate", "mint": book::b58(k), "t": r.t_rx, "slot": r.slot, "sig": bs58::encode(&r.sig).into_string(),
                    "ms_after_complete": (r.t_rx as i64 - tc as i64) as f64 / 1e6, "payer": book::short(&r.payer), "age": age.map(|a| json!({"slots": a.0, "ms": a.1}))})));
            } else if st.pool_txs < POOL_TX_MAX {
                st.pool_txs += 1;
                self.st.pool_txs += 1; self.st.records += 1;
                recs.push((M_MIGR, json!({"ev": "mig_pool_tx", "mint": book::b58(k), "t": r.t_rx, "slot": r.slot, "sig": bs58::encode(&r.sig).into_string(), "n": st.pool_txs,
                    "ms_after_migrate": (r.t_rx as i64 - st.migrated.unwrap() as i64) as f64 / 1e6, "payer": book::short(&r.payer)})));
            }
            break;
        }
        if !hit { self.st.migrations_unmatched += 1; }
    }

    pub fn tick(&mut self, now: u64, book: &Book, recs: &mut Vec<(usize, Value)>) {
        let mut i = 0;
        while i < self.follow.len() {
            let (m, t0, kind, s0, v0) = self.follow[i];
            if now < t0 + FOLLOW_NS + 500_000_000 { i += 1; continue; }
            self.follow.swap_remove(i);
            let Some(tok) = book.get(&m) else { continue };
            let mx = tok.tape.iter().filter(|x| x.t >= t0 && x.t <= t0 + FOLLOW_NS).map(|x| x.vsol).max().unwrap_or(0);
            let st = self.toks.get(&m).copied().unwrap_or_default();
            let mut r = json!({"ev": "mig_follow", "kind": kind, "mint": book::b58(&m), "t0": t0, "slot0": s0, "vsol0": v0 as f64 / 1e9, "max_vsol_10s": mx as f64 / 1e9,
                "completed_ms": st.complete.map(|c| (c as i64 - t0 as i64) as f64 / 1e6), "tape_from": tok.tape.front().map(|x| x.t)});
            for (k, w) in [("g1", 1u64), ("g5", 5), ("g10", 10)] { r[k] = flow(tok, t0 + 1, t0 + w * 1_000_000_000); }
            recs.push((M_MIGR, r)); self.st.records += 1;
        }
        if self.toks.len() > 50_000 {
            self.toks.retain(|_, s| [s.v100, s.v105, s.complete, s.migrated].iter().flatten().any(|&t| t + KEEP_NS > now));
        }
    }

    pub fn status(&self) -> Value {
        let s = &self.st;
        json!({"v100": s.v100, "v105": s.v105, "v105_sell": s.v105_sell, "completes": s.completes, "migrations": s.migrations, "pool_txs": s.pool_txs,
               "raw_txs": s.raw, "raw_unmatched": s.migrations_unmatched, "records": s.records, "following": self.follow.len()})
    }
}
