//! OBSERVATORY module 9: the FEED RACE (owner 10-29 02:50 PKT; the 24 h Astralane raw-shred trial). LOG ONLY.
//! Every arrival the dip engine ingests, from every feed (raw UDP shreds, ShredStream, deshred, the executed feed ...), is handed over
//! as (first 8 bytes of the signature, feed index, t_rx, slot) the moment the event loop takes it (one try_send, before its own work).
//! Per transaction, inside a 2 s window (bounded map, oldest dropped and counted): each feed's first arrival.
//!   race_tx: one compact record per tx delivered by >= 2 feeds that MATTERS to us (a buy that leaves its wallet >= 6% = a whale buy
//!     that can arm us; a sell inside a live pre-send window or of >= 6% of supply = a dump; a trade at vSOL >= 100 = a migration
//!     crossing), plus 1 in SAMPLE of the others: sig8, slot, idx, the first feed, every other feed's lag behind it (us), the tag.
//!   obs_summary "race" every 10 min (and race_summary records): per feed: txs delivered, wins (first), coverage (share of all txs
//!     seen by any feed), lead over the next feed (median / p90, us) when it won, lag behind the winner (median / p90) when it lost;
//!     the same over the tagged txs only. Leader-client split: not done (the leader lookup is not on this thread).
use super::M_RACE;
use rustc_hash::FxHashMap;
use serde_json::{json, Value};
use std::collections::VecDeque;

pub const WIN_NS: u64 = 2_000_000_000;
pub const SAMPLE: u64 = 20;
pub const NF: usize = 16;
const MAX_TX: usize = 400_000;
const KEEP: usize = 20_000;

#[derive(Clone, Copy)]
struct E { t: [u64; NF], slot: u64, idx: u32, tag: u8, first_t: u64 }

#[derive(Default, Clone)]
struct Fs { delivered: u64, wins: u64, lead: Vec<f32>, lag: Vec<f32>, t_delivered: u64, t_wins: u64, t_lead: Vec<f32>, t_lag: Vec<f32> }

pub const T_WHALE: u8 = 1;
pub const T_DUMP: u8 = 2;
pub const T_MIG: u8 = 4;

#[derive(Default)]
pub struct Race { names: Vec<String>, m: FxHashMap<u64, E>, q: VecDeque<(u64, u64)>, fs: Vec<Fs>, pub txs: u64, pub tagged: u64, pub multi: u64, pub records: u64, pub dropped: u64, n: u64 }

fn pct(v: &mut [f32], q: f64) -> Option<f64> { if v.is_empty() { return None; } v.sort_by(|a, b| a.partial_cmp(b).unwrap()); Some(v[((v.len() - 1) as f64 * q).round() as usize] as f64) }
fn push(v: &mut Vec<f32>, x: f32) { if v.len() < KEEP { v.push(x); } else { let k = (x.to_bits() as usize) % KEEP; v[k] = x; } }

impl Race {
    pub fn new(names: Vec<String>) -> Race { Race { fs: vec![Fs::default(); NF], names, ..Default::default() } }
    pub fn mem_bytes(&self) -> usize { self.m.len() * (std::mem::size_of::<E>() + 16) + self.q.len() * 16 + self.fs.len() * KEEP * 16 }
    fn name(&self, f: usize) -> String { self.names.get(f).cloned().unwrap_or_else(|| format!("feed{f}")) }

    pub fn on_arrival(&mut self, k8: u64, feed: u16, t: u64, slot: u64, now: u64, recs: &mut Vec<(usize, Value)>) {
        let f = (feed as usize).min(NF - 1);
        match self.m.get_mut(&k8) {
            Some(e) => { if e.t[f] == 0 { e.t[f] = t.max(1); } }
            None => {
                if self.m.len() >= MAX_TX { self.dropped += 1; } else {
                    let mut e = E { t: [0; NF], slot, idx: u32::MAX, tag: 0, first_t: t };
                    e.t[f] = t.max(1);
                    self.m.insert(k8, e); self.q.push_back((t, k8));
                }
            }
        }
        self.expire(now, false, recs);
    }
    /// the earliest arrival of a tx over all feeds (while it is in the window)
    pub fn earliest(&self, k8: u64) -> Option<u64> { self.m.get(&k8).and_then(|e| e.t.iter().filter(|t| **t > 0).min().copied()) }
    /// the executed feed's view of a tx (its block index, what it meant)
    pub fn tag(&mut self, k8: u64, idx: u64, tag: u8) { if let Some(e) = self.m.get_mut(&k8) { e.idx = idx as u32; e.tag |= tag; } }

    pub fn expire(&mut self, now: u64, all: bool, recs: &mut Vec<(usize, Value)>) {
        while let Some(&(t0, k8)) = self.q.front() {
            if !all && t0 + WIN_NS > now { break; }
            self.q.pop_front();
            let Some(e) = self.m.remove(&k8) else { continue };
            self.txs += 1;
            let mut fe: Vec<(usize, u64)> = e.t.iter().enumerate().filter(|(_, t)| **t > 0).map(|(f, t)| (f, *t)).collect();
            fe.sort_by_key(|x| x.1);
            let tagged = e.tag != 0;
            if tagged { self.tagged += 1; }
            for (k, (f, t)) in fe.iter().enumerate() {
                let s = &mut self.fs[*f];
                s.delivered += 1; if tagged { s.t_delivered += 1; }
                if k == 0 {
                    s.wins += 1; if tagged { s.t_wins += 1; }
                    if let Some((_, t2)) = fe.get(1) { let l = (t2 - t) as f32 / 1e3; push(&mut s.lead, l); if tagged { push(&mut s.t_lead, l); } }
                } else { let l = (t - fe[0].1) as f32 / 1e3; push(&mut s.lag, l); if tagged { push(&mut s.t_lag, l); } }
            }
            if fe.len() >= 2 {
                self.multi += 1;
                self.n += 1;
                if tagged || self.n % SAMPLE == 0 {
                    self.records += 1;
                    let lags: serde_json::Map<String, Value> = fe.iter().skip(1).map(|(f, t)| (self.name(*f), json!(((t - fe[0].1) as f64 / 1e3).round()))).collect();
                    recs.push((M_RACE, json!({"ev": "race_tx", "sig8": format!("{k8:016x}"), "slot": e.slot, "idx": if e.idx == u32::MAX { Value::Null } else { e.idx.into() },
                        "t": e.first_t, "first": self.name(fe[0].0), "lag_us": lags, "tag": e.tag, "sampled": !tagged})));
                }
            }
        }
    }

    pub fn summary(&mut self) -> Value {
        let total = self.txs.max(1) as f64;
        let mut per = serde_json::Map::new();
        for f in 0..NF {
            let name = self.name(f);
            let s = &mut self.fs[f];
            if s.delivered == 0 { continue; }
            per.insert(name, json!({"delivered": s.delivered, "coverage": s.delivered as f64 / total, "wins": s.wins, "win_share": s.wins as f64 / total,
                "lead_us_p50": pct(&mut s.lead, 0.5), "lead_us_p90": pct(&mut s.lead, 0.9), "lag_us_p50": pct(&mut s.lag, 0.5), "lag_us_p90": pct(&mut s.lag, 0.9),
                "tagged": {"delivered": s.t_delivered, "wins": s.t_wins, "lead_us_p50": pct(&mut s.t_lead, 0.5), "lead_us_p90": pct(&mut s.t_lead, 0.9),
                    "lag_us_p50": pct(&mut s.t_lag, 0.5), "lag_us_p90": pct(&mut s.t_lag, 0.9)}}));
        }
        json!({"txs": self.txs, "multi_feed": self.multi, "tagged": self.tagged, "records": self.records, "open": self.m.len(), "dropped_full": self.dropped, "per_feed": per})
    }
    pub fn status(&self) -> Value { json!({"txs": self.txs, "multi_feed": self.multi, "tagged": self.tagged, "records": self.records, "open": self.m.len(), "dropped_full": self.dropped}) }
}
