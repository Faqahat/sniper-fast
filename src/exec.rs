//! The executor (PLAN WP-05): from the engine's decisions to one-transaction Jito bundles. Bundle-only, fail-closed, no
//! network call between the decision and the fire.
//!
//! **Send checks** ([`send_checks`]: one pure function over [`SendInputs`], called by the executor at every decision and
//! by replay, WP-09): the SendGate in live; a healthy recorder; the store's health (WP-04: warm-up, state availability,
//! the re-read); the sender's own caps; a blockhash from the WP-03b ring (journaled `blockhash_head` inputs, the state
//! stream's block metas) no older than `max_blockhash_age_slots`; the target slot's leader (the slot after the current
//! processed one) from the LeaderBook, whose kind is not in `skip_leader_kinds`; a valid cached Jito auth token (the
//! send path never refreshes it, F28). The first that fails is the decision's reason.
//!
//! **Route checks**, in order: an expected profit, a plausible gap, token cooling, the rent cap, the in-flight lock
//! keyed by (buy pool, sell pool, mint) (a new attempt only on a new state version or a new leader; `inflight_same_state`
//! for the same slot, `inflight_same_leader` for a later slot of the same leader), the ≥1M class's token bucket
//! (`band_throttle`), the crowded skip (`crowded_skip`), the on-chain min_profit (tip + base fee + margin, margin =
//! max(`margin_floor`, `margin_share` × expected net): a landed bundle cannot lose) against the expected profit, and the
//! build (one bundle copy: CU limit, the ATA create when needed, the route, the tip last; on a recent blockhash, never a
//! durable nonce).
//!
//! **Modes** ([`Mode`]): `live` and `canary` (live under `[canary]`'s caps, at most 0.2 SOL) sign with the trading key
//! and fire through the jito-bundle path's rate queue (bands, crowding, EV; send/budget.rs). `shadow` (PLAN-ADDENDUM
//! I-7) runs every check up to the signature: a decision that passes all of them but the SendGate is a would-send, built
//! and recorded with `sent = false`. `dry_run` (go-live gate item 4) also signs it, with a throwaway key made in memory
//! (never the trading key; the payer stays the wallet, so accounts, sizes and tips are the live ones and the signature
//! cannot pass on chain), records it in full (transaction, size, tip, accounts, the checks it passed) and never sends: a
//! dry-run executor holds no send path and no Jito client, so nothing in it can transmit; it may simulate (read-only).
//! The dry run's checks ([`verify_bundle`]) read the signed bytes: the route instruction's amount_in and min_profit
//! against the decision's, its accounts, the tip's amount, account and payer, and that the signed min_profit covers the
//! signed tip, the base fee and the margin floor (what makes a landed bundle unable to lose; review WP-05 #12). Shadow
//! and dry runs hold no Jito client, so the token check is not modelled in them (`TokenSeen::NotUsed`, review #18): a
//! period of `jito_auth_stale` shows only in a sending run.
//!
//! **Settlement** (item 9), stream-based: a landing is the wallet stream's record of our signature (INPUT `wallet_tx`);
//! an attempt that never landed is final when its blockhash expires (150 blocks), after one bounded
//! `getSignatureStatuses` with `searchTransactionHistory` (F43); `getSignatureStatuses` also runs at +2 s, +10 s and
//! +60 s, batched, 500 ms each; a landing found after the final writes an `amend` line, and so does the wallet record of
//! a landing the expiry check found first (its fee, CU and events: review WP-05 #3). A copy that left without an answer
//! (a timeout, a transport error) may still land: it stays open until it lands or its blockhash expires (review #7);
//! only a copy that never left, or one the block engine refused, is final at once. Every block-engine result of our
//! bundles is kept in order (send/jito.rs) and reaches the engine as INPUT `inflight_release`: only a landing
//! (`processed`, `finalized`) releases the attempt's in-flight entry early (PLAN WP-07's final: a landing or the
//! blockhash's expiry; a would-fail keeps it for its hold, review #2), and an attempt's first would-fail counts once
//! toward its token's cooling. Building and signing run on the engine thread (microseconds); the send and every RPC call
//! run on the runtimes.
use crate::bands;
use crate::build::{self, Alt, PumpGlobal};
use crate::config::{Config, SendKind, SendPath};
use crate::control::{GateMode, SendGate};
use crate::feeds::{clock::now_ns, Event, InputKind};
use crate::lat::Series;
use crate::leaders::{LeaderBook, LeaderKind};
use crate::rec::{self, Rec};
use crate::rpc::{Bounds, Rpc, SigStatus};
use crate::send::{self, jito, Copy, Fired, Paths, Prio, TokenBucket};
use crate::store_health::{HealthFlags, Shut};
use crate::tx::{b58, pk, Pk};
use crate::venues::{PoolMeta, WSOL};
use anyhow::{Context, Result};
use crossbeam_channel::Sender;
use rustc_hash::{FxHashMap as HashMap, FxHashSet as HashSet};
use serde_json::{json, Value};
use std::collections::{BTreeMap, VecDeque};
use std::sync::atomic::AtomicU64;
use std::sync::Arc;
use std::time::Duration;

/// CU for creating the mid token account when the wallet has none (arbed's cu-budget allowance)
const ATA_CREATE_CU: u64 = 30_000;
const BASE_FEE: u64 = bands::BASE_FEE;
/// a blockhash is valid for this many blocks after its own (an attempt is open until the chain passes it)
pub const BLOCKHASH_VALID_BLOCKS: u64 = 150;
/// without a block height an attempt expires this many slots after its blockhash's slot (150 blocks, skipped slots
/// included with margin) ...
const EXPIRY_SLOTS: u64 = 300;
/// ... and without any slot this long after it was signed
const EXPIRY_NS: u64 = 120_000_000_000;
/// the cross-checks after the send (F43): one batched `getSignatureStatuses` each, 500 ms
const CHECKS: [(u64, &str); 3] = [(2_000_000_000, "+2s"), (10_000_000_000, "+10s"), (60_000_000_000, "+60s")];
/// signatures per getSignatureStatuses call (the RPC's limit is 256)
const STATUS_BATCH: usize = 256;
/// finalised attempts remembered for amends and verdicts that come late
const FINALS_KEEP: usize = 20_000;
/// token cooling: this many would-fails in a row pause a token 60 s, doubling per pause up to 5 min
const COOL_AFTER: u32 = 25;

/// What the executor is armed as (attempts.jsonl `kind`)
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    /// real bundles (`--live`, mode = "live")
    Live,
    /// real bundles under `[canary]`'s caps (`--canary`)
    Canary,
    /// no key: every check up to the signature, would-sends recorded with `sent = false` (I-7)
    Shadow,
    /// a throwaway key: would-sends built, signed, recorded in full, never sent (go-live gate item 4)
    DryRun,
}

impl Mode {
    pub fn as_str(self) -> &'static str { match self { Mode::Live => "live", Mode::Canary => "canary", Mode::Shadow => "shadow", Mode::DryRun => "dry_run" } }
    /// the modes that send
    pub fn sends(self) -> bool { matches!(self, Mode::Live | Mode::Canary) }
}

/// A route's crowding (PLAN WP-05 item 5, F6): distinct arbitrage-like signers that landed on either pool over the
/// window, its bucket (0 < 20, 1 20-150, 2 ≥ 150 by default) and where the bucket came from (`map`: the activity map
/// holds the whole window; `static_list`: WP-00's list stands in until it does; `map_partial`: no list, the map so far)
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, serde::Serialize)]
pub struct Crowding { pub signers_6h: Option<u32>, pub bucket: u8, pub src: &'static str }

impl Crowding {
    /// the send queue's crowding rank: the top bucket queues behind the others of its band
    pub fn rank(&self) -> u8 { (self.bucket >= 2) as u8 }
}

/// Everything a build needs about one round trip, owned (the engine fills it at the size the step wants)
#[derive(Clone)]
pub struct RouteIn {
    pub opp: u64,
    pub trig: [u8; 64],
    pub trig_feed: Option<String>,
    pub slot: u64,
    /// engine stage times: rx, decoded, engine, resolved, decided
    pub st: [u64; 5],
    pub buy: PoolMeta,
    pub sell: PoolMeta,
    pub buy_data: Vec<u8>,
    pub sell_data: Vec<u8>,
    pub buy_source: &'static str,
    pub sell_source: &'static str,
    pub mint: Pk,
    pub size: u64,
    /// our prediction at `size`: what the buy leg delivers, what the sell leg returns
    pub mid: u64,
    pub back: u64,
    /// what the buy leg debits at `size` (PLAN-ADDENDUM WP-16: arbx-sizing's exact quote; PumpSwap's
    /// `buy_exact_quote_in` debits min(size, eff0 + fees(eff0)), now and then a lamport below `size`): the guard's quote
    /// delta is `back` minus it, as the decision's `gross`
    pub spent: u64,
    pub gross_at_opp: i64,
    pub net_at_opp: i64,
    pub cu: u64,
    pub buy_live: Vec<i64>,
    pub sell_live: Vec<i64>,
    pub buy_end: Option<i32>,
    pub sell_end: Option<i32>,
    /// WP-04 item 10: the state version the decision priced (xxh3 over the route accounts' (pubkey, slot,
    /// write_version)), the time since the route's last write, and the decision (decisions.jsonl `decision`)
    pub state_version: u64,
    pub route_age_ms: Option<f64>,
    pub decision: u64,
    /// WP-05: the evaluation's kind (`commit`, `quiescent`, `timeout`, `fork`) and stage times (attempts `trigger`,
    /// `stages`), the consistency-set skew of each pool
    pub trig_kind: &'static str,
    pub t_first_shred: Option<u64>,
    pub t_commit: u64,
    pub t_priced: u64,
    pub parts_skew: Option<(u64, u64)>,
    /// the route's crowding (F6)
    pub crowding: Crowding,
    /// the route's accounts with the (slot, write_version) the decision priced (attempts `route_in.accounts`, X6)
    pub accounts: Vec<(Pk, u64, u64)>,
}

impl RouteIn {
    /// the expected profit at `size` (gross, before the tip and the fee): the guard's quote delta, the sell leg's output
    /// minus the buy leg's debit, as the decision's `gross` (WP-16 merge: one profit for the decision and the executor)
    pub fn expected(&self) -> i64 { self.back as i64 - self.spent as i64 }
}

// ------------------------------------------------------------------------------------------------ the send view

/// One blockhash as the executor would build on it
#[derive(Clone, Debug, PartialEq)]
pub struct Bh { pub hash: [u8; 32], pub slot: u64, pub height: Option<u64>, pub src: String, pub commitment: &'static str, pub t_ns: u64 }

/// What the send checks read of the chain, from journaled engine inputs only (so a replay sees the same): the WP-03b
/// ring's confirmed head (INPUT 1 `blockhash_head`), the state stream's block metas (processed), the newest block
/// height, and the leader schedule (INPUT 2 `leader_window`). Owned by the engine
#[derive(Default, Debug)]
pub struct SendView {
    pub head: Option<Bh>,
    pub meta: Option<Bh>,
    /// the newest block height seen, with its slot
    pub height: Option<(u64, u64)>,
    sched: BTreeMap<u64, Pk>,
}

/// slots of the schedule kept (a window is 400; the next one comes every 100)
const SCHED_KEEP: usize = 4_000;

impl SendView {
    /// INPUT 1 `blockhash_head`: `{hash, slot, height, src, commitment, t_ns}`
    pub fn on_head(&mut self, d: &Value) {
        let Some(hash) = d["hash"].as_str().and_then(|h| bs58::decode(h).into_vec().ok()).and_then(|v| <[u8; 32]>::try_from(v).ok()) else { return };
        let Some(slot) = d["slot"].as_u64() else { return };
        let height = d["height"].as_u64();
        let commitment = if d["commitment"].as_str() == Some("processed") { "processed" } else { "confirmed" };
        self.head = Some(Bh { hash, slot, height, src: d["src"].as_str().unwrap_or("ring").to_string(), commitment, t_ns: d["t_ns"].as_u64().unwrap_or(0) });
        if let Some(h) = height { self.note_height(slot, h); }
    }

    /// a block meta of the state stream (processed)
    pub fn on_block_meta(&mut self, slot: u64, hash: [u8; 32], height: Option<u64>, t: u64) {
        if self.meta.as_ref().is_some_and(|m| m.slot >= slot) { return; }
        self.meta = Some(Bh { hash, slot, height, src: "blocks_meta".into(), commitment: "processed", t_ns: t });
        if let Some(h) = height { self.note_height(slot, h); }
    }

    fn note_height(&mut self, slot: u64, h: u64) { if self.height.is_none_or(|x| h > x.1) { self.height = Some((slot, h)); } }

    /// INPUT 2 `leader_window`: `{start, leaders: [pk]}`
    pub fn on_window(&mut self, d: &Value) {
        let Some(start) = d["start"].as_u64() else { return };
        for (i, l) in d["leaders"].as_array().into_iter().flatten().enumerate() {
            if let Some(k) = l.as_str().and_then(|s| bs58::decode(s).into_vec().ok()).and_then(|v| Pk::try_from(v).ok()) { self.sched.insert(start + i as u64, k); }
        }
        while self.sched.len() > SCHED_KEEP { let k = *self.sched.keys().next().unwrap(); self.sched.remove(&k); }
    }

    /// the schedule's leader of `slot`
    pub fn leader(&self, slot: u64) -> Option<Pk> { self.sched.get(&slot).copied() }

    /// The blockhash a bundle would use: `confirmed` the ring's head; `processed` the newer of the head and the newest
    /// block meta
    pub fn blockhash(&self, commitment: &str) -> Option<&Bh> {
        match (commitment, &self.head, &self.meta) {
            ("processed", Some(h), Some(m)) => Some(if m.slot > h.slot { m } else { h }),
            ("processed", h, m) => h.as_ref().or(m.as_ref()),
            (_, h, _) => h.as_ref(),
        }
    }

    /// whether the chain has passed `bh`'s validity: its height + 150 when both heights are known, else its slot + 300
    /// against `tip_slot`
    pub fn expired(&self, bh_slot: u64, bh_height: Option<u64>, tip_slot: u64) -> Option<bool> {
        match (bh_height, self.height) {
            (Some(h), Some((_, now))) => Some(now > h + BLOCKHASH_VALID_BLOCKS),
            _ if tip_slot > 0 && bh_slot > 0 => Some(tip_slot > bh_slot + EXPIRY_SLOTS),
            _ => None,
        }
    }
}

// ------------------------------------------------------------------------------------------------ the send checks

/// The blockhash a check saw
#[derive(Clone, Debug, PartialEq)]
pub struct BhSeen { pub slot: u64, pub age_slots: Option<u64>, pub src: String, pub commitment: &'static str }

/// The target slot's leader a check saw (the LeaderBook's snapshot, the schedule's identity)
#[derive(Clone, Debug, PartialEq)]
pub struct LeaderSeen { pub slot: u64, pub identity: Option<String>, pub kind: LeaderKind, pub kind_src: Option<String> }

/// The Jito token a check saw: a valid cached one, none valid, or none needed (no bundle path: shadow, dry run)
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum TokenSeen { Valid { age_s: u64 }, Stale, NotUsed }

/// Everything `send_checks` reads: one value per input, taken at the decision (the engine journals the ones that come
/// from outside its inputs: the gate, the leader's kind, the token, the recorder)
#[derive(Clone, Debug)]
pub struct SendInputs {
    pub gate: GateMode,
    pub gate_reason: String,
    pub recorder_ok: bool,
    pub shut: Shut,
    /// the sender's own state: None ready, else why not (`fee_cap`, `sender_stopped`, `canary_wait`, `canary_count`)
    pub sender: Option<&'static str>,
    pub blockhash: Option<BhSeen>,
    pub max_blockhash_age_slots: u64,
    pub leader: LeaderSeen,
    pub skip_leader_kinds: Vec<LeaderKind>,
    pub token: TokenSeen,
}

/// the checks `send_checks` runs, in order (attempts `checks`)
pub const SEND_CHECKS: [&str; 7] = ["gate", "recorder", "store_health", "sender", "blockhash", "leader", "jito_auth"];

/// The SendGate's check: live, or `gate_shadow:<reason>` / `gate_stopped`
pub fn gate_check(i: &SendInputs) -> Result<(), String> {
    match i.gate {
        GateMode::Live => Ok(()),
        GateMode::Stopped => Err("gate_stopped".into()),
        GateMode::Shadow => Err(format!("gate_shadow:{}", i.gate_reason)),
    }
}

/// Every check but the gate's, in order: the recorder (`recorder_unhealthy`), the store's health (`warmup`,
/// `state_unavailable`, `resync`), the sender's caps, the blockhash (`blockhash_stale`: none, its age unknown, or older
/// than `max_blockhash_age_slots`), the leader (`leader_unknown`, `leader_skip_kind`), the token (`jito_auth_stale`)
pub fn input_checks(i: &SendInputs) -> Result<(), String> {
    if !i.recorder_ok { return Err("recorder_unhealthy".into()); }
    if i.shut != Shut::Ready { return Err(i.shut.as_str().into()); }
    if let Some(s) = i.sender { return Err(s.into()); }
    match &i.blockhash {
        Some(b) if b.age_slots.is_some_and(|a| a <= i.max_blockhash_age_slots) => {}
        _ => return Err("blockhash_stale".into()),
    }
    if i.skip_leader_kinds.contains(&i.leader.kind) {
        return Err(if i.leader.kind == LeaderKind::Unknown { "leader_unknown" } else { "leader_skip_kind" }.into());
    }
    if i.token == TokenSeen::Stale { return Err("jito_auth_stale".into()); }
    Ok(())
}

/// PLAN WP-05 item 2: the send checks, one pure function (the executor's decision and WP-09's replay): the first that
/// fails is the reason
pub fn send_checks(i: &SendInputs) -> Result<(), String> { gate_check(i)?; input_checks(i) }

// ------------------------------------------------------------------------------------------------ the in-flight lock

/// The in-flight key (PLAN WP-05 item 4): the route's two pools and its mint
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct InflightKey { pub buy: Pk, pub sell: Pk, pub mint: Pk }

impl InflightKey {
    pub fn json(&self) -> Value { json!([b58(&self.buy), b58(&self.sell), b58(&self.mint)]) }
}

/// An attempt in flight on a key: the state version it priced, its target slot and leader, the attempt, when
#[derive(Clone, Debug, PartialEq)]
pub struct InflightEntry { pub sv: u64, pub target_slot: u64, pub leader: Option<Pk>, pub attempt: u64, pub t: u64 }

/// The in-flight lock (replaces the 400 ms pair lock): a new attempt on a key goes only on a new state version or to a
/// new leader. An entry holds `hold_slots` past its target slot, or until its attempt is released early: a landing (the
/// block engine's `processed`, the wallet's record), or a copy that never left or was refused (review WP-05 #2: a
/// would-fail, a lost auction or a drop does not release it)
#[derive(Debug)]
pub struct Inflight { map: HashMap<InflightKey, InflightEntry>, pub hold_slots: u64 }

impl Inflight {
    pub fn new(hold_slots: u64) -> Inflight { Inflight { map: HashMap::default(), hold_slots: hold_slots.max(1) } }

    /// entries whose hold ended by `slot` (target slot + hold ≤ slot) go
    pub fn expire(&mut self, slot: u64) { let h = self.hold_slots; self.map.retain(|_, e| e.target_slot + h > slot); }

    /// May a new attempt on `key` go, priced on `sv`, aimed at `target_slot` and its `leader`? Ok: why (`first`,
    /// `new_state`, `new_leader`) and the entry it replaces (attempt, state version); Err: `inflight_same_state` (the same
    /// state to the same leader at the same slot) or `inflight_same_leader` (the same state, a later slot of the same
    /// leader; from Stage 1 the verifier may allow it, `new_slot_verified`)
    pub fn check(&self, key: &InflightKey, sv: u64, target_slot: u64, leader: Option<Pk>) -> Result<(&'static str, Option<(u64, u64)>), &'static str> {
        let Some(e) = self.map.get(key).filter(|e| e.target_slot + self.hold_slots > target_slot.saturating_sub(1)) else { return Ok(("first", None)) };
        let prev = Some((e.attempt, e.sv));
        if e.sv != sv { return Ok(("new_state", prev)); }
        if e.leader != leader { return Ok(("new_leader", prev)); }
        if target_slot > e.target_slot { Err("inflight_same_leader") } else { Err("inflight_same_state") }
    }

    pub fn insert(&mut self, key: InflightKey, e: InflightEntry) { self.map.insert(key, e); }

    /// the attempt landed, or cannot (it never left, it was refused, it expired): its entry goes (if it is still that
    /// attempt's). True when one went
    pub fn release(&mut self, attempt: u64) -> bool {
        let before = self.map.len();
        self.map.retain(|_, e| e.attempt != attempt);
        self.map.len() < before
    }

    pub fn len(&self) -> usize { self.map.len() }
    pub fn is_empty(&self) -> bool { self.map.is_empty() }
}

// ------------------------------------------------------------------------------------------------ tips

/// The bundle path's tip (`[[send]]` jito-bundle: `tip_share` of the edge within `tip_lamports`..`tip_max_lamports`, to
/// its accounts in rotation), the same with or without a built path (shadow and dry runs tip as live ones would)
#[derive(Clone, Debug, PartialEq)]
pub struct TipPolicy { pub accounts: Vec<Pk>, pub floor: u64, pub share: Option<f64>, pub max: u64, cursor: usize, pub path: String }

impl TipPolicy {
    pub fn from_path(c: &SendPath) -> TipPolicy {
        let known = send::known_tip_accounts(c.kind);
        let names: Vec<&str> = if c.tip_accounts.is_empty() { known.to_vec() } else { c.tip_accounts.iter().map(String::as_str).collect() };
        TipPolicy { accounts: names.iter().map(|a| pk(a)).collect(), floor: c.tip_lamports, share: c.tip_share, max: c.tip_max_lamports.unwrap_or(u64::MAX), cursor: 0,
            path: c.name.clone() }
    }
    /// the tip for an expected edge (gross − base fee), and its account
    pub fn tip(&mut self, edge: i64) -> Option<(Pk, u64)> {
        if self.accounts.is_empty() || self.floor == 0 { return None; }
        let lamports = match self.share { Some(s) => ((edge.max(0) as f64 * s) as u64).clamp(self.floor, self.max.max(self.floor)), None => self.floor };
        let a = self.accounts[self.cursor % self.accounts.len()];
        self.cursor += 1;
        Some((a, lamports))
    }
}

/// The on-chain min_profit of a bundle (PLAN WP-05 item 8): tip + base fee + priority (0) + margin, margin =
/// max(`floor`, `share` × expected net). Rent is never part of it. Returns (min_profit, margin)
pub fn min_profit_onchain(tip: u64, expected_net: i64, floor: u64, share: f64) -> (u64, u64) {
    let margin = floor.max((expected_net.max(0) as f64 * share) as u64);
    (tip + BASE_FEE + margin, margin)
}

// ------------------------------------------------------------------------------------------------ settlement

/// What comes back to the engine from the executor's tasks (journaled as INPUT 9 `settled`)
pub enum Settled {
    /// the send task's result for one attempt (its copy sent, refused, or never left)
    Fired { attempt: u64, fired: Fired },
    /// one batched getSignatureStatuses: `why` `check` (the +2/+10/+60 s cross-checks) or `expiry` (the one check
    /// before an attempt not landed is final; with `searchTransactionHistory`), one entry per (attempt, label)
    Statuses { why: &'static str, at: Vec<(u64, &'static str)>, result: std::result::Result<Vec<Option<SigStatus>>, String>, t_ns: u64 },
    /// a dry run's read-only simulation of a would-send bundle (sims are recorded with the attempt's id)
    DrySim { attempt: u64, line: Value },
}

impl Settled {
    /// the journal's INPUT 9 body
    pub fn json(&self) -> Value {
        match self {
            Settled::Fired { attempt, fired } => json!({ "what": "fired", "attempt": attempt, "fired": serde_json::to_value(fired).unwrap_or(Value::Null) }),
            Settled::Statuses { why, at, result, t_ns } => json!({ "what": "statuses", "why": why, "at": at.iter().map(|(a, l)| json!([a, l])).collect::<Vec<_>>(),
                "result": match result { Ok(v) => serde_json::to_value(v).unwrap_or(Value::Null), Err(e) => json!({ "error": e }) }, "t_ns": t_ns }),
            Settled::DrySim { attempt, line } => json!({ "what": "dry_sim", "attempt": attempt, "line": line }),
        }
    }

    /// ---- WP-09 (review WP-09 "For the WP-05 merge" item 4). The journal's INPUT 9 body read back, in `json`'s
    /// `{what: fired | statuses | dry_sim}` forms: a replay hands it to its executor as the run's engine handed the event.
    /// None: not one of them (an older form, or a label this build does not write)
    pub fn from_json(v: &Value) -> Option<Settled> {
        match v["what"].as_str()? {
            "fired" => Some(Settled::Fired { attempt: v["attempt"].as_u64()?, fired: Fired::from_json(&v["fired"])? }),
            "statuses" => {
                let why = match v["why"].as_str()? { "check" => "check", "expiry" => "expiry", _ => return None };
                let at = v["at"].as_array()?.iter().map(|x| Some((x[0].as_u64()?, status_label(x[1].as_str()?)?))).collect::<Option<Vec<_>>>()?;
                let result = match &v["result"] {
                    Value::Array(a) => Ok(a.iter().map(|s| if s.is_null() { Some(None) } else { SigStatus::from_json(s).map(Some) }).collect::<Option<Vec<_>>>()?),
                    r => Err(r["error"].as_str()?.to_string()),
                };
                Some(Settled::Statuses { why, at, result, t_ns: v["t_ns"].as_u64()? })
            }
            "dry_sim" => Some(Settled::DrySim { attempt: v["attempt"].as_u64()?, line: v["line"].clone() }),
            _ => None,
        }
    }
}

/// a statuses entry's label (`CHECKS`', or the expiry check's) as the static string the executor writes
fn status_label(s: &str) -> Option<&'static str> { CHECKS.iter().map(|c| c.1).chain(["expiry"]).find(|l| *l == s) }

/// An attempt sent (live, canary) and not final yet
struct Open {
    attempt: u64,
    decision: u64,
    opp: u64,
    sig: [u8; 64],
    sig58: String,
    mint: Pk,
    size: u64,
    mid: u64,
    back: u64,
    trig: [u8; 64],
    trig_slot: u64,
    expected: i64,
    tip: u64,
    min_profit: u64,
    creates_ata: bool,
    worst: u64,
    bh_slot: u64,
    bh_height: Option<u64>,
    target_slot: u64,
    leader: Option<(String, LeaderKind)>,
    /// the decision's engine time (journaled): the expiry without a slot counts from it (WP-09: never the real clock)
    t_engine: u64,
    t_signed: u64,
    t_sent: Option<u64>,
    bundle: Option<String>,
    path: String,
    fired: bool,
    took_big: bool,
    /// cross-checks still to run (time, label) and their results
    checks_due: Vec<(u64, &'static str)>,
    checks: Vec<Value>,
    /// a cross-check saw it land (evidence; the wallet record or the expiry check decides)
    status_hit: Option<SigStatus>,
    expiry_asked: bool,
    /// the copy left without an answer (a timeout, a transport error): why, for its final line (review WP-05 #7)
    send_error: Option<String>,
    /// one of its would-fails counted toward its token's cooling already (one per attempt: review #2, #16)
    cooled: bool,
}

/// What is remembered of a final attempt (amends, late verdicts): whether it landed and how (`src`: `statuses` when the
/// expiry check found the landing, whose fee and events only the wallet record brings), what its landing adds to the
/// money so far (`counted`), whether the wallet record came, whether a would-fail of it counted toward cooling
#[derive(Clone)]
struct Final { sig58: String, mint: Pk, landed: bool, ok: bool, tip: u64, size: u64, creates_ata: bool, src: &'static str, counted: Counted, wallet_seen: bool,
    cooled: bool }

/// the dry run's key and options
struct Dry { key: ed25519_dalek::SigningKey, simulate: bool, sim_recent: VecDeque<u64>, sim_per_sec: usize }

/// the canary's caps on top of the live ones
#[derive(Clone, Copy)]
struct CanaryCaps { count: u32, every_ns: u64 }

pub struct Exec {
    mode: Mode,
    payer: Pk,
    program: Pk,
    alts: Vec<Alt>,
    alt_lists: HashMap<Pk, Arc<Vec<Pk>>>,
    pump: Option<PumpGlobal>,
    held: HashSet<Pk>,
    /// the executor's RPC (role exec: the diagnostic simulations) and the settlement's (role settle): run-time calls are
    /// bounded calls, never the 3 s failover or the 429 loop (item 2)
    rpc: Rpc,
    settle: Rpc,
    rt: tokio::runtime::Handle,
    back: Sender<Event>,
    /// live and canary only: the send paths and the bundle path's index; a shadow or dry-run executor has none
    paths: Option<Arc<Paths>>,
    bundle_path: Option<usize>,
    jito: Option<Arc<jito::Jito>>,
    /// live and canary: the trading key
    key: Option<ed25519_dalek::SigningKey>,
    dry: Option<Dry>,
    pol: crate::config::SendPolicyCfg,
    skip_kinds: Vec<LeaderKind>,
    tips: Option<TipPolicy>,
    /// the bundle path's rate (a would-send's rate model) and its rolling window
    path_rate: usize,
    would_recent: VecDeque<u64>,
    max_size: u64,
    cap_failed_fees: u64,
    margin_lamports: u64,
    max_new_atas: u32,
    canary: Option<CanaryCaps>,
    sim_rate: Option<usize>,
    sim_recent: VecDeque<u64>,
    sim_size_max: u64,
    cu_price: u64,
    /// sims.jsonl ([sim] enabled), attempts.jsonl, outcomes.jsonl and the diagnostic `log` events, through the recorder
    rec: Rec,
    sims_on: bool,
    pub counts: HashMap<&'static str, u64>,
    /// stage latencies of the send (status.jsonl `latency`, A.8): `decided_to_signed`, `signed_to_fired` (handed to the
    /// runtime: the cost of the spawn), `signed_to_sent` (the copy's send task running, from its fire result)
    pub lat: Vec<Series>,
    gate: Arc<SendGate>,
    gate_seen: Option<GateMode>,
    /// WP-04 item 8 / I-4: the engine's store health. Fail closed: not ready until an engine installs its flags
    health: Arc<HealthFlags>,
    refused: Option<String>,
    leaders: Option<Arc<LeaderBook>>,
    next_attempt: u64,
    inflight: Inflight,
    big: TokenBucket,
    /// per token: (would-fails in a row, paused until (ns), pauses so far)
    mint_cool: HashMap<Pk, (u32, u64, u32)>,
    open: BTreeMap<u64, Open>,
    by_sig: HashMap<[u8; 64], u64>,
    finals: HashMap<u64, Final>,
    finals_order: VecDeque<u64>,
    feeds: Vec<String>,
    seen: HashMap<[u8; 64], (u64, u16, Vec<(u16, u64)>)>,
    /// the send path's network-call scope (F28): every call made between a decision and its fire counts here
    net: Arc<AtomicU64>,
    /// the `poh_trigger_pct` gauge every attempt is noted in (the process's, which the status line reads; tests give
    /// their own)
    poh_gauge: &'static crate::feeds::PohGauge,
    // totals
    decisions: u64,
    refusals: u64,
    would_sends: u64,
    sent: u32,
    last_sent_ns: u64,
    landed: u32,
    wins: u32,
    spent: u64,
    reserved: u64,
    fees: u64,
    tips_paid: u64,
    /// the on-chain round trips of the winning landings (the last leg's output − the size, from the route program's
    /// events): with `tips_paid` and `fees`, the bot's own net until WP-07's ledger
    round_trip: i64,
    /// winning landings whose round trip is not in `round_trip` (yet): found by the expiry check before their wallet
    /// record, or without the route program's events (truncated logs). While it is not 0 the money is partial (review #3)
    round_trip_unknown: u32,
    /// attempts handed to the fire whose copy never left (the queue dropped it, no valid token, ...): not sends for the
    /// canary's count (review #16)
    never_left: u32,
    new_atas: u32,
    stopped: Option<&'static str>,
    leader_seen: (u64, u64),
    leader_prev: (u64, u64),
    // ---- WP-09: a replay's offline executor (`Exec::offline`)
    /// its send checks read what the run's decisions read from outside the journal (`journaled`: the run's
    /// decision-point records), never its own gate, LeaderBook, token or recorder; it spawns nothing (no RPC call, no
    /// send, no key)
    offline: bool,
    /// `cfg_sha256` of the config it was assembled from (exec_init)
    cfg_sha256: String,
    /// the run's last decision-point record at or before the opportunity being decided, and whether it is this
    /// opportunity's own
    journaled: Option<Seen>,
    journaled_fresh: bool,
    /// records that are not this replay's: one staged at another opportunity than its own, one this build cannot read,
    /// or one whose target slot or leader identity is not the replay's (the replay diverged)
    pub seen_mismatch: u64,
    /// decisions made before any record (fail closed: the gate read as stopped)
    pub seen_missing: u64,
    /// tests: the route instruction is built with these (amount_in, min_profit) instead of the decision's (a builder
    /// regression the dry run's checks must catch: review #12)
    #[cfg(test)]
    fault_route: Option<(u64, u64)>,
}

/// `Exec::lat` series, in order
const LAT_DECIDED_TO_SIGNED: usize = 0;
const LAT_SIGNED_TO_FIRED: usize = 1;
const LAT_SIGNED_TO_SENT: usize = 2;
fn exec_lat() -> Vec<Series> { ["decided_to_signed", "signed_to_fired", "signed_to_sent"].into_iter().map(Series::new).collect() }

fn sol(x: f64) -> u64 { (x * 1e9) as u64 }
fn hex_code(c: u32) -> String { format!("0x{c:x}") }
fn sig64(s: &str) -> Option<[u8; 64]> { bs58::decode(s).into_vec().ok()?.try_into().ok() }
fn kind_of(s: &str) -> Option<LeaderKind> { match s { "jito" => Some(LeaderKind::Jito), "bam" => Some(LeaderKind::Bam), "other" => Some(LeaderKind::Other), "unknown" => Some(LeaderKind::Unknown), _ => None } }

/// What the engine records for a decision the executor saw (decisions.jsonl `verdict`, `reason`, `attempt`, `sent`,
/// `would_send`, `reason_ungated`, `crowding`, `ev`, `rank`, `band`). `reason` follows `send_checks`' order (a closed
/// gate first); with the gate closed, `reason_ungated` is the first other check that would have refused the decision
/// (null: it is a would-send: every other check passed and its bundle was built, PLAN-ADDENDUM I-7). `band` is the
/// executor's (at the size it would trade: the queue's and the tip's band; review WP-05 #9), once it reached the route
/// checks
#[derive(Clone, Debug, PartialEq)]
pub struct Decided {
    pub verdict: &'static str,
    pub reason: String,
    pub attempt: Option<u64>,
    pub sent: Option<bool>,
    pub would_send: bool,
    pub reason_ungated: Option<String>,
    pub crowding: Option<Crowding>,
    pub ev: Option<i64>,
    pub rank: Option<u8>,
    pub band: Option<u8>,
}

impl Decided {
    pub fn reject(reason: impl Into<String>) -> Decided {
        Decided { verdict: "reject", reason: reason.into(), attempt: None, sent: None, would_send: false, reason_ungated: None, crowding: None, ev: None, rank: None,
            band: None }
    }
}

/// The crowded-pool list (data/crowded-pools.json): `{"pools": [{"pool": "<base58>", ...}, ...]}`, or a plain array of
/// base58 strings. Every entry must be an account key: a typo must not silently un-rank a pool.
pub fn parse_crowded_pools(text: &str) -> Result<HashSet<Pk>> {
    let v: Value = serde_json::from_str(text).context("not JSON")?;
    let list = match &v {
        Value::Array(a) => a,
        Value::Object(o) => o.get("pools").and_then(|p| p.as_array()).context("no \"pools\" array")?,
        _ => anyhow::bail!("neither a JSON object with \"pools\" nor an array"),
    };
    let mut out = HashSet::default();
    for e in list {
        let s = match e {
            Value::String(s) => s.as_str(),
            Value::Object(o) => o.get("pool").and_then(|p| p.as_str()).with_context(|| format!("entry {e} has no \"pool\""))?,
            _ => anyhow::bail!("entry {e} is not a pool"),
        };
        let k: Pk = bs58::decode(s).into_vec().ok().and_then(|b| b.try_into().ok()).with_context(|| format!("{s} is not a base58 account key"))?;
        out.insert(k);
    }
    // review N1: an empty list ranks and skips nothing; that is "no file", not a list
    anyhow::ensure!(!out.is_empty(), "no pool listed (leave [send_policy] crowded_pools_file empty for none)");
    Ok(out)
}

pub fn load_crowded_pools(path: &str) -> Result<HashSet<Pk>> {
    let text = std::fs::read_to_string(path).with_context(|| format!("[send_policy] crowded_pools_file {path}"))?;
    parse_crowded_pools(&text).with_context(|| format!("[send_policy] crowded_pools_file {path}"))
}

/// a throwaway signing key for the dry run, made in memory from the OS's randomness (never written anywhere)
pub fn ephemeral_key() -> Result<ed25519_dalek::SigningKey> {
    use std::io::Read;
    let mut seed = [0u8; 32];
    std::fs::File::open("/dev/urandom").context("/dev/urandom")?.read_exact(&mut seed)?;
    let k = ed25519_dalek::SigningKey::from_bytes(&seed);
    seed.fill(0);
    Ok(k)
}

/// One built bundle transaction
struct Built { msg: build::Message, cu_limit: u64, creates_ata: bool }

impl Exec {
    /// Everything off the hot path: lookup tables, PumpSwap's GlobalConfig, the wallet's token accounts. `mode`: what to
    /// arm; `key`: the trading key (live, canary: the config's wallet, unlocked by the caller), the dry run's throwaway key,
    /// or none (shadow). `paths`: the send paths (live and canary only; a dry run refuses them: nothing in it may send)
    #[allow(clippy::too_many_arguments)]
    pub async fn new(cfg: &Config, rpc_all: &Rpc, paths: Option<Arc<Paths>>, rec: Rec, back: Sender<Event>, feeds: Vec<String>,
        mode: Mode, key: Option<ed25519_dalek::SigningKey>, mints: Vec<(Pk, Pk)>) -> Result<(Exec, Vec<String>)> {
        let mut notes = Vec::new();
        let payer = pk(&cfg.wallet);
        // a configured crowded list must load, first, before any RPC call (fail closed: a missing file would silently put
        // the crowded pools back in front)
        let crowded = if cfg.send_policy.crowded_pools_file.is_empty() { None } else { Some(load_crowded_pools(&cfg.send_policy.crowded_pools_file)?) };
        if let Some(c) = &crowded { notes.push(format!("crowded pools: {} from {} (bucket 2 until the activity map holds {} h)", c.len(), cfg.send_policy.crowded_pools_file, cfg.send_policy.crowding_window_h)); }
        match mode {
            Mode::Live | Mode::Canary => {
                let k = key.as_ref().context("a live or canary executor needs the trading key")?;
                anyhow::ensure!(k.verifying_key().to_bytes() == payer, "the trading key is not the config's wallet {}", cfg.wallet);
                crate::config::bundle_only(&cfg.sends).context("PLAN WP-05: live sends are bundle-only")?;
                let p = paths.as_ref().context("a live or canary executor needs its send paths")?;
                anyhow::ensure!(p.bundle_path().is_some(), "no jito-bundle send path was built (see the send path notes)");
            }
            Mode::DryRun => {
                anyhow::ensure!(paths.is_none(), "a dry run builds no send path: nothing in it may transmit");
                let k = key.as_ref().context("a dry run needs its throwaway key")?;
                anyhow::ensure!(k.verifying_key().to_bytes() != payer, "the dry run's key must not be the trading wallet's");
            }
            Mode::Shadow => anyhow::ensure!(key.is_none(), "a shadow executor holds no key"),
        }
        let rpc = rpc_all.only(&cfg.exec.rpc);
        let rpc = if rpc.is_empty() {
            anyhow::ensure!(mode == Mode::Shadow, "[exec] rpc names {:?}: none of them is a configured, available [rpc] endpoint", cfg.exec.rpc);
            notes.push(format!("[exec] rpc {:?} unavailable: the shadow executor reads through the run's providers", cfg.exec.rpc));
            rpc_all.with_role(crate::rpc::Role::Exec)
        } else { rpc };
        let alt_keys: Vec<Pk> = cfg.exec.alts.iter().map(|a| pk(a)).collect();
        let (_, accts) = rpc.accounts(&alt_keys).await.context("lookup tables")?;
        let mut alts = Vec::new();
        for (k, a) in alt_keys.iter().zip(accts) {
            match a.and_then(|a| crate::tx::parse_alt(&a.data)) { Some(addrs) => alts.push((*k, addrs)), None => notes.push(format!("lookup table {} not found, skipped", b58(k))) }
        }
        let (_, g) = rpc.accounts(&[*build::PUMP_GLOBAL_CONFIG]).await.context("PumpSwap GlobalConfig")?;
        let pump = g.into_iter().next().flatten().and_then(|a| build::decode_pump_global(&a.data));
        if pump.is_none() { notes.push("PumpSwap GlobalConfig unreadable: PumpSwap legs will not build".into()); }
        // which of the pools' tokens the wallet already holds an account for: their associated token accounts, read
        // in batches (getTokenAccountsByOwner needs an index most providers refuse; this works everywhere)
        let mut cands: Vec<(Pk, Pk)> = mints.clone();
        cands.push((*WSOL, *crate::pda::TOKEN_PROGRAM));
        cands.sort(); cands.dedup();
        let atas: Vec<Pk> = cands.iter().map(|(m, p)| build::ata_of(&payer, m, p)).collect();
        let (_, accts) = rpc.accounts(&atas).await.context("wallet token accounts")?;
        let held: HashSet<Pk> = cands.iter().zip(accts).filter(|(_, a)| a.is_some()).map(|((m, _), _)| *m).collect();
        if !held.contains(&*WSOL) {
            anyhow::ensure!(!mode.sends(), "wallet {} has no WSOL account: every route starts from it", cfg.wallet);
            notes.push(format!("wallet {} has no WSOL account: a live run would refuse to start", cfg.wallet));
        }
        let x = Exec::assemble(cfg, rpc, paths, rec, back, feeds, alts, pump, held, mode, key)?;
        notes.push(match mode {
            Mode::Live => format!("LIVE TRADING armed: bundle-only, at most {} SOL a trade, stop after {} lamports of failed fees", cfg.live.max_size_sol, cfg.live.max_failed_fees_lamports),
            Mode::Canary => format!("CANARY armed: live bundles of at most {} SOL, {} attempts, {} ms apart, stop after {} lamports of failed fees", cfg.canary.size_sol,
                cfg.canary.count, cfg.canary.every_ms, cfg.canary.max_spend_lamports),
            Mode::Shadow => "shadow: every send check up to the signature; would-sends recorded with sent = false (PLAN-ADDENDUM I-7)".into(),
            Mode::DryRun => format!("DRY RUN: would-sends built and signed by the throwaway key {} (payer {}), recorded in full, never sent{}",
                x.dry.as_ref().map(|d| b58(&d.key.verifying_key().to_bytes())).unwrap_or_default(), cfg.wallet, if cfg.dry_run.simulate { "; simulated read-only" } else { "" }),
        });
        Ok((x, notes))
    }

    /// The executor from what `new` fetched (or a test made up): no network here. Needs a tokio runtime.
    #[allow(clippy::too_many_arguments)]
    pub fn assemble(cfg: &Config, rpc: Rpc, paths: Option<Arc<Paths>>, rec: Rec, back: Sender<Event>, feeds: Vec<String>,
        alts: Vec<(Pk, Vec<Pk>)>, pump: Option<PumpGlobal>, held: HashSet<Pk>, mode: Mode, key: Option<ed25519_dalek::SigningKey>) -> Result<Exec> {
        let payer = pk(&cfg.wallet);
        let paths = if mode.sends() { paths } else { None };
        let bundle_path = paths.as_ref().and_then(|p| p.bundle_path());
        let jito = bundle_path.and_then(|i| paths.as_ref().and_then(|p| p.list[i].jito.clone()));
        let bundle_cfg = cfg.sends.iter().find(|s| s.enabled && s.kind == SendKind::JitoBundle).or_else(|| cfg.sends.iter().find(|s| s.kind == SendKind::JitoBundle));
        let (dry, key) = match mode {
            Mode::DryRun => (Some(Dry { key: key.context("a dry run needs its key")?, simulate: cfg.dry_run.simulate, sim_recent: VecDeque::new(),
                sim_per_sec: cfg.dry_run.max_sim_per_sec as usize }), None),
            Mode::Shadow => (None, None),
            _ => (None, key),
        };
        let skip_kinds: Vec<LeaderKind> = cfg.send_policy.skip_leader_kinds.iter().filter_map(|k| kind_of(k)).collect();
        let canary = (mode == Mode::Canary).then_some(CanaryCaps { count: cfg.canary.count, every_ns: cfg.canary.every_ms * 1_000_000 });
        let max_size = match mode { Mode::Canary => sol(cfg.canary.size_sol.min(cfg.live.max_size_sol)), _ => sol(cfg.live.max_size_sol) };
        let alt_lists: HashMap<Pk, Arc<Vec<Pk>>> = alts.iter().map(|(k, a)| (*k, Arc::new(a.clone()))).collect();
        let settle = rpc.with_role(crate::rpc::Role::Settle);
        let x = Exec { mode, payer, program: pk(&cfg.exec.program), alts: alts.iter().map(|(k, a)| Alt::new(*k, a)).collect(), alt_lists, pump, held, rpc, settle,
            rt: tokio::runtime::Handle::current(), back, paths, bundle_path, jito, key, dry, pol: cfg.send_policy.clone(), skip_kinds,
            tips: bundle_cfg.map(TipPolicy::from_path), path_rate: bundle_cfg.and_then(|c| c.max_per_sec).unwrap_or(5) as usize, would_recent: VecDeque::new(),
            max_size, cap_failed_fees: if mode == Mode::Canary { cfg.canary.max_spend_lamports } else { cfg.live.max_failed_fees_lamports },
            margin_lamports: cfg.live.margin_lamports, max_new_atas: cfg.live.max_new_token_accounts, canary,
            sim_rate: cfg.sim.enabled.then_some(cfg.sim.max_per_sec as usize), sim_recent: VecDeque::new(), sim_size_max: sol(cfg.exec.max_size_sol),
            cu_price: cfg.strategy.cu_price_micro, rec, sims_on: cfg.sim.enabled, counts: HashMap::default(), lat: exec_lat(), gate: SendGate::new(), gate_seen: None,
            health: Arc::new(HealthFlags::default()), refused: None, leaders: None, next_attempt: 0, inflight: Inflight::new(cfg.send_policy.inflight_hold_slots),
            big: TokenBucket::new(cfg.send_policy.big_band_max_per_sec, 1), mint_cool: HashMap::default(), open: BTreeMap::new(), by_sig: HashMap::default(),
            finals: HashMap::default(), finals_order: VecDeque::new(), feeds, seen: HashMap::default(), net: Arc::new(AtomicU64::new(0)), poh_gauge: &crate::feeds::POH_GAUGE,
            decisions: 0, refusals: 0, would_sends: 0, sent: 0, last_sent_ns: 0, landed: 0, wins: 0, spent: 0, reserved: 0, fees: 0, tips_paid: 0, round_trip: 0,
            round_trip_unknown: 0, never_left: 0, new_atas: 0, stopped: None, leader_seen: (0, 0), leader_prev: (0, 0), offline: false, cfg_sha256: cfg_sha256(cfg), journaled: None,
            journaled_fresh: false, seen_mismatch: 0, seen_missing: 0, #[cfg(test)] fault_route: None };
        x.install_sink();
        Ok(x)
    }

    /// every result of our bundles reaches the engine as INPUT 5 `inflight_release` (journaled), through the Jito client's
    /// sink; `release` is true for a landing only (`Outcome::is_final`: review WP-05 #2)
    fn install_sink(&self) {
        let Some(j) = &self.jito else { return };
        let back = self.back.clone();
        j.set_sink(Box::new(move |n: jito::ResultNote| {
            let o = &n.outcome;
            let _ = back.send(Event::Input { kind: InputKind::InflightRelease, data: Arc::new(json!({ "src": "jito", "sig": n.sig, "bundle": n.bundle, "attempt": n.attempt,
                "outcome": o.outcome, "slot": o.slot, "index": o.index, "validator": o.validator, "seq": n.seq, "t_ns": n.t_ns, "release": o.is_final(),
                "code": if o.outcome == "would-fail" { jito::error_code(o.detail.as_deref()) } else { None } })) });
        }));
    }

    pub fn mode(&self) -> Mode { self.mode }

    /// WP-01: follow the run's SendGate (a new Exec has its own, always live)
    pub fn set_gate(&mut self, gate: Arc<SendGate>) { self.gate = gate; }

    /// the SendGate mode the last decision read (None: it returned before reading it); the engine journals it
    pub fn gate_seen(&self) -> Option<GateMode> { self.gate_seen }

    /// WP-04: follow the engine's store health. Until an engine installs its flags the executor is not ready (fail
    /// closed: WP-04 review #8)
    pub fn set_health(&mut self, h: Arc<HealthFlags>) { self.health = h; }

    /// the run's LeaderBook (the target slot's leader, its kind, places and RTTs: attempts' `leader`)
    pub fn set_leaders(&mut self, b: Arc<LeaderBook>) { self.leaders = Some(b); }

    /// why the last decision was refused (decisions.jsonl `reason`), None when it was sent
    pub fn refusal(&self) -> Option<String> { self.refused.clone() }

    /// the SendGate as it is now (`SendGate::json`)
    pub fn gate_json(&self) -> Value { self.gate.json() }

    /// the send path's network calls so far (F28: a decision-to-fire must make none)
    pub fn net_calls(&self) -> u64 { self.net.load(std::sync::atomic::Ordering::Relaxed) }

    /// the dry run's signer (its public key), if this is a dry run
    pub fn dry_signer(&self) -> Option<Pk> { self.dry.as_ref().map(|d| d.key.verifying_key().to_bytes()) }

    /// the attempts still open (sent, not final): stop.json `in_flight_at_stop` / `unsettled`
    pub fn open_attempts(&self) -> Vec<u64> { self.open.keys().copied().collect() }

    /// the tokens the wallet held an account for at boot (meta.json `wallet.held_mints_at_boot`), sorted
    pub fn held_mints(&self) -> Vec<String> {
        let mut v: Vec<String> = self.held.iter().map(b58).collect();
        v.sort();
        v
    }

    fn count(&mut self, k: &'static str) { *self.counts.entry(k).or_default() += 1; }

    /// the size to simulate this decision at, if a simulation slot is free (at most max_per_sec), at the engine's time `t`
    /// (WP-09 review item 5: never the real clock; the window decides which decisions are simulated, folded into the
    /// decision digest)
    pub fn wants_sim(&mut self, size: u64, t: u64) -> Option<u64> {
        let per = self.sim_rate?;
        while self.sim_recent.front().is_some_and(|x| t.saturating_sub(*x) >= 1_000_000_000) { self.sim_recent.pop_front(); }
        if self.sim_recent.len() >= per { self.count("sim_skipped_rate"); return None; }
        self.sim_recent.push_back(t);
        Some(size.min(self.sim_size_max))
    }

    /// the largest size a decision may trade (live: `[live] max_size_sol`; canary: its size; shadow and dry runs model
    /// live)
    pub fn size_cap(&self) -> u64 { self.max_size }

    /// the sender's own state for the send checks (None: ready)
    fn sender_state(&mut self, t: u64) -> Option<&'static str> {
        if !self.mode.sends() { return None; }
        if self.stopped.is_some() { return Some("sender_stopped"); }
        if self.spent + self.reserved + BASE_FEE > self.cap_failed_fees {
            if self.open.is_empty() { self.stopped = Some(if self.mode == Mode::Canary { "spend cap reached" } else { "failed-fee cap reached" }); }
            return Some("fee_cap");
        }
        if let Some(c) = self.canary {
            // the attempts that left (or may have): one the queue dropped is no canary (review WP-05 #16)
            if self.sent.saturating_sub(self.never_left) >= c.count { self.stopped = Some("canary count reached"); return Some("canary_count"); }
            if self.sent > 0 && t < self.last_sent_ns + c.every_ns { return Some("canary_wait"); }
        }
        None
    }

    /// What the send checks see now: the gate, the recorder, the store's health, the sender, the blockhash of `view` aged
    /// against `tip_slot`, the leader of `tip_slot + 1`, the token. `now_ns` is the engine's time. An offline executor
    /// (a replay) reads the gate, the leader's kind, the token and the recorder from the run's journaled record instead
    /// (`journaled`); the store's health, the sender, the blockhash and the leader's identity are the engine's own
    pub fn inputs(&mut self, view: &SendView, tip_slot: u64, now_ns: u64) -> SendInputs {
        let target = tip_slot + 1;
        let bh = view.blockhash(&self.pol.blockhash_commitment).map(|b| BhSeen { slot: b.slot, age_slots: (tip_slot > 0).then(|| tip_slot.saturating_sub(b.slot)),
            src: b.src.clone(), commitment: b.commitment });
        let (gate, gate_reason, recorder_ok, leader, token) = if self.offline { self.journaled_inputs(view, target) } else {
            let token = match (&self.jito, self.mode.sends()) {
                (_, false) => TokenSeen::NotUsed,
                (None, true) => TokenSeen::Stale,
                (Some(j), true) => match j.token_state((now_ns / 1_000_000) as i64) { jito::TokenState::Valid { age_s, .. } => TokenSeen::Valid { age_s }, jito::TokenState::Stale => TokenSeen::Stale },
            };
            (self.gate.mode(), self.gate.reason(), self.rec.core_ok(), self.leader_seen(view, target), token)
        };
        self.gate_seen = Some(gate);
        SendInputs { gate, gate_reason, recorder_ok, shut: self.health.shut(), sender: self.sender_state(now_ns), blockhash: bh,
            max_blockhash_age_slots: self.pol.max_blockhash_age_slots, leader, skip_leader_kinds: self.skip_kinds.clone(), token }
    }

    /// ---- WP-09 (review WP-09 "For the WP-05 merge" item 3). An offline executor's gate, recorder, leader and token: the
    /// run's last decision-point record (`stage_seen`), the leader's identity from the journaled schedule. A record staged
    /// for this very opportunity must name the same target slot and identity (else `seen_mismatch`). Before any record,
    /// fail closed: the gate stopped, the recorder not ok (`seen_missing`)
    fn journaled_inputs(&mut self, view: &SendView, target: u64) -> (GateMode, String, bool, LeaderSeen, TokenSeen) {
        let identity = view.leader(target).map(|k| b58(&k));
        let fresh = std::mem::take(&mut self.journaled_fresh);
        let Some(s) = &self.journaled else {
            self.seen_missing += 1;
            return (GateMode::Stopped, "replay_no_record".into(), false, LeaderSeen { slot: target, identity, kind: LeaderKind::Unknown, kind_src: Some("replay_no_record".into()) },
                TokenSeen::Stale);
        };
        if fresh && (s.leader_slot != Some(target) || s.identity != identity) { self.seen_mismatch += 1; }
        let token = if !s.token_ok { TokenSeen::Stale } else if self.mode.sends() { TokenSeen::Valid { age_s: 0 } } else { TokenSeen::NotUsed };
        (s.gate, s.gate_reason.clone(), s.recorder_ok, LeaderSeen { slot: target, identity, kind: s.kind, kind_src: s.kind_src.clone() }, token)
    }

    /// ---- WP-09. A replay hands an offline executor the run's decision-point record of opportunity `opp` (INPUT 3 `src`
    /// "decision", staged ahead by `journal::replay`) when it decides opportunity `at` (`opp` ≤ `at`; the last one holds
    /// until the next). A record of another opportunity than the one being decided, or one this build cannot read, means
    /// the replay is not the run's (`seen_mismatch`)
    pub fn stage_seen(&mut self, opp: u64, at: u64, d: &Value) {
        match Seen::from_json(d) {
            Some(s) => {
                if opp != at { self.seen_mismatch += 1; }
                self.journaled = Some(s);
                self.journaled_fresh = opp == at;
            }
            None => self.seen_mismatch += 1,
        }
    }

    /// The target slot's leader: its identity from the journaled schedule only (INPUT 2: a replay sees the same; none
    /// there is `unknown`, `no_schedule`), its kind from the LeaderBook (journaled with the decision when it changes,
    /// INPUT 3); a book that names another leader for the slot makes it `unknown` (`schedule_mismatch`). Before the fire
    /// only the book's light read (`kind_at`); the attempt line takes the full snapshot after it (review WP-05 #8)
    fn leader_seen(&self, view: &SendView, target: u64) -> LeaderSeen {
        let unknown = |identity: Option<String>, why: &str| LeaderSeen { slot: target, identity, kind: LeaderKind::Unknown, kind_src: Some(why.to_string()) };
        let Some(id) = view.leader(target) else { return unknown(None, crate::leaders::NO_SCHEDULE) };
        let identity = Some(b58(&id));
        let Some(b) = &self.leaders else { return unknown(identity, crate::leaders::NO_SOURCE) };
        let (book_leader, kind, kind_src) = b.kind_at(target);
        if book_leader.is_some_and(|l| l != id) { return unknown(identity, "schedule_mismatch"); }
        LeaderSeen { slot: target, identity, kind, kind_src }
    }

    /// an attempt's trigger has (or not) a PoH position: the `poh_trigger_pct` gauge. The engine looks it up after the
    /// decision (the PoH index is shared with the feed threads: not before the fire; review WP-05 #8)
    pub fn note_poh(&self, has: bool) { self.poh_gauge.note_attempt(has); }

    /// The executor's turn for one decision (route `r`, re-quoted by the engine at the size cap): the send checks, the
    /// route checks, then a send (live, canary) or a would-send (shadow, dry run, or a closed gate) recorded with
    /// `sent = false`. `slot` is the engine's processed slot (in-flight expiry), `t` its time
    pub fn decide(&mut self, r: RouteIn, i: &SendInputs, view: &SendView, slot: u64, t: u64) -> Decided {
        self.decisions += 1;
        let net = self.net.clone();
        let gate = gate_check(i);
        // a closed gate is counted for every decision it held back (MEASUREMENT A.5: `reject_gate_shadow`, `_stopped`);
        // what else refused such a decision is `ungated_<reason>`, so the `reject_*` counters sum to the refusals
        // (review WP-05 #16)
        if let Err(g) = &gate { self.count(reject_counter(g)); }
        let mut d = crate::netcount::on_thread(&net, || self.decide_inner(r, i, view, slot, t, gate.is_err()));
        if d.attempt.is_none() { let k = if gate.is_err() { ungated_counter(&d.reason) } else { reject_counter(&d.reason) }; self.count(k); }
        if let Err(g) = gate {
            // send_checks' order: the gate's reason first; what would have refused it otherwise beside it
            d.reason_ungated = if d.would_send { None } else { Some(d.reason.clone()) };
            d.reason = g;
        }
        if d.sent != Some(true) { self.refusals += 1; self.refused = Some(d.reason.clone()); } else { self.refused = None; }
        d
    }

    /// everything but the gate (`gated`: the gate is closed, a send would be a would-send)
    fn decide_inner(&mut self, r: RouteIn, i: &SendInputs, view: &SendView, slot: u64, t: u64, gated: bool) -> Decided {
        if let Err(why) = input_checks(i) { return Decided::reject(why); }
        let expected = r.expected();
        let band = bands::of_gross(expected);
        let crowding = r.crowding;
        let mut d = Decided { crowding: Some(crowding), band: Some(band), ..Decided::reject("") };
        let fail = |mut d: Decided, why: &str| { d.reason = why.to_string(); d };
        // the route's checks
        if expected <= 0 { return fail(d, "expected_below_min_profit"); }
        // a gap worth more than the trade is a broken quote, not an opportunity (seen: 9.9e12 lamports)
        if expected > r.size as i64 { return fail(d, "implausible_gap"); }
        if self.mint_cool.get(&r.mint).is_some_and(|c| t < c.1) { return fail(d, "token_cooling"); }
        let creates_ata = !self.held.contains(&r.mint);
        if creates_ata && self.new_atas >= self.max_new_atas { return fail(d, "rent_cap"); }
        self.inflight.expire(slot);
        let key = InflightKey { buy: r.buy.pool, sell: r.sell.pool, mint: r.mint };
        let leader_pk = i.leader.identity.as_deref().and_then(|s| bs58::decode(s).into_vec().ok()).and_then(|v| Pk::try_from(v).ok());
        let target = i.leader.slot;
        let (why_allowed, prev) = match self.inflight.check(&key, r.state_version, target, leader_pk) { Ok(x) => x, Err(why) => return fail(d, why) };
        let big = bands::is_big(band);
        if big && !self.big.peek(t) { return fail(d, "band_throttle"); }
        // a bucket-2 route expecting this much is not sent at all (OD-3's alternative); `crowded_pool` is the queue's drop
        if crowding.bucket >= 2 && self.pol.crowded_skip_min_expected_lamports > 0 && expected >= self.pol.crowded_skip_min_expected_lamports as i64 {
            return fail(d, "crowded_skip");
        }
        // the tip, the on-chain min_profit (item 8) and the decision's own bar (today's: tip + fee + [live] margin)
        let tip = self.tips.as_mut().and_then(|p| p.tip(expected - BASE_FEE as i64));
        let tip_l = tip.map_or(0, |x| x.1);
        let net = expected - tip_l as i64 - BASE_FEE as i64;
        let (min_profit, margin) = min_profit_onchain(tip_l, net, self.pol.margin_floor, self.pol.margin_share);
        let prio = Prio { band: bands::rank(band), crowd: crowding.rank(), ev: net };
        d.ev = Some(net);
        d.rank = Some(prio.rank());
        if expected < (min_profit.max(tip_l + BASE_FEE + self.margin_lamports)) as i64 { return fail(d, "expected_below_min_profit"); }
        // a would-send (shadow, dry run, a closed gate) models the bundle path's rate: at most its max_per_sec a second
        // (`would_rate`; `would_rate_crowded` for a crowded route: a model, not the queue's drop, review WP-05 #10)
        let would = !self.mode.sends() || gated;
        if would {
            while self.would_recent.front().is_some_and(|x| t.saturating_sub(*x) >= 1_000_000_000) { self.would_recent.pop_front(); }
            if self.would_recent.len() >= self.path_rate { return fail(d, if crowding.rank() > 0 { "would_rate_crowded" } else { "would_rate" }); }
        }
        let Some(bh) = view.blockhash(&self.pol.blockhash_commitment).cloned() else { return fail(d, "blockhash_stale") };
        let t_built0 = now_ns();
        let built = match self.build(&r, min_profit, bh.hash, tip) {
            Ok(b) => b,
            Err(e) => return fail(d, &if e.starts_with("oversized") { "oversized".to_string() } else { format!("build_error:{e}") }),
        };
        let t_built = now_ns();
        // a sending mode's path (always there: `Exec::new` refuses a live or canary executor without its bundle path)
        let send_path = if would { None } else {
            match (self.paths.clone(), self.bundle_path) { (Some(p), Some(bp)) => Some((p, bp)), _ => return fail(d, "sender_stopped") }
        };
        // the attempt: from here on nothing refuses it
        let attempt = self.next_attempt;
        self.next_attempt += 1;
        let took_big = big && self.big.try_take(t);
        self.inflight.insert(key, InflightEntry { sv: r.state_version, target_slot: target, leader: leader_pk, attempt, t });
        self.leader_seen.0 += 1;
        if i.leader.kind != LeaderKind::Unknown && i.leader.identity.is_some() { self.leader_seen.1 += 1; }
        d.attempt = Some(attempt);
        // live / canary: sign and fire first (nothing but the signature sits between the decision and the fire), record after
        let fired = send_path.map(|(paths, bp)| {
            let raw = Arc::new(build::sign(&built.msg, self.key.as_ref().expect("a sending mode holds its key")));
            let t_signed = now_ns();
            let fire = paths.fire(attempt, vec![Copy { path: bp, raw: raw.clone(), tip, blockhash_slot: Some(bh.slot) }], prio);
            (paths, bp, raw, fire, t_signed, now_ns())
        });
        let snap = self.leaders.as_ref().map(|b| serde_json::to_value(b.snapshot(target)).unwrap_or(Value::Null))
            .unwrap_or_else(|| json!({ "slot": target, "leader": i.leader.identity, "kind": i.leader.kind, "kind_src": i.leader.kind_src, "be_rtt_ms": crate::leaders::be_rtt(now_ns()) }));
        let age = i.blockhash.as_ref().and_then(|b| b.age_slots);
        let mut line = AttemptLine { attempt, r: &r, mode: self.mode, expected, band, crowding, tip, tip_policy: self.tips.as_ref(), min_profit, margin, built: &built, bh: &bh,
            bh_age: age, leader: snap, key, prev, why_allowed, prio, lambda: self.paths.as_ref().and_then(|p| p.queue_now().1), t_built0, t_built, payer: self.payer,
            program: self.program }.json();
        let Some((paths, bp, raw, fire, t_signed, t_fired)) = fired else {
            // a would-send (shadow, dry run, a closed gate): recorded with sent = false
            self.would_recent.push_back(t);
            self.would_sends += 1;
            d.reason = "would_send".into();
            d.sent = Some(false);
            d.would_send = true;
            line["sent"] = json!(false);
            line["not_sent"] = json!(if gated { gate_check(i).err().unwrap_or_default() } else { self.mode.as_str().to_string() });
            if let Some(dk) = self.dry.as_ref().map(|d| d.key.clone()) {
                // the dry run signs (the throwaway key) and checks the signed transaction as the send path would
                let raw = build::sign(&built.msg, &dk);
                let t_signed = now_ns();
                let want = self.want(&r, dk.verifying_key().to_bytes(), bh.hash, tip, min_profit, built.cu_limit);
                let checks = verify_bundle(&raw, &want);
                let ok = checks.iter().all(|c| c["ok"] == json!(true));
                line["tx"]["sig"] = json!(send::first_signature(&raw));
                line["copies"][0]["sig"] = line["tx"]["sig"].clone();
                line["stages"]["t_signed"] = json!(t_signed);
                line["dry_run"] = json!({ "signer": b58(&dk.verifying_key().to_bytes()), "tx_b64": base64_of(&raw), "bytes": raw.len(), "checks": checks, "checks_ok": ok,
                    "accounts": accounts_of(&raw, &self.alt_lists) });
                self.count(if ok { "dry_run_ok" } else { "dry_run_check_failed" });
                // the simulation's rate window on the engine's time (WP-09 review item 5: never the real clock)
                let sim = self.dry.as_mut().is_some_and(|dry| {
                    while dry.sim_recent.front().is_some_and(|x| t.saturating_sub(*x) >= 1_000_000_000) { dry.sim_recent.pop_front(); }
                    let go = dry.simulate && dry.sim_recent.len() < dry.sim_per_sec;
                    if go { dry.sim_recent.push_back(t); }
                    go
                });
                line["dry_run"]["simulated"] = json!(sim);
                if sim { self.spawn_dry_sim(attempt, raw); }
            }
            self.rec.json(rec::ATTEMPTS, line);
            self.count("would_send");
            return d;
        };
        let sig58 = send::first_signature(&raw).unwrap_or_default();
        let sig = sig64(&sig58).unwrap_or([0; 64]);
        let pools = [r.buy.pool, r.sell.pool];
        let back = self.back.clone();
        self.rt.spawn(async move {
            let fired = match fire.await { Ok(f) => f, Err(e) => Fired { id: attempt, t_ns: 0, copies: vec![send::Sent { attempt, path: "?".into(), sig: Some(sig58_of(&sig)),
                tip_account: None, tip_lamports: 0, t_sent: 0, t_ack: 0, ms: 0.0, ok: false, status: None, reply: Some(format!("send task failed: {e}")), bundle: None,
                blockhash_slot: None, queue_wait_us: None, drop: Some("send_task"), lambda: None }] } };
            // WP-03b tap, after the firing: the copy that left (the wallet's source (b), watched until a few slots past its
            // target slot) and the route's pools (backfill priority 0)
            crate::chainfetch::note_fired(attempt, &fired.copies, &pools, Some(target));
            let _ = back.send(Event::Settled(Box::new(Settled::Fired { attempt, fired })));
        });
        line["sent"] = json!(true);
        line["tx"]["sig"] = json!(sig58);
        line["copies"][0]["sig"] = json!(sig58);
        line["stages"]["t_signed"] = json!(t_signed);
        line["stages"]["t_enqueued"] = json!(t_fired);
        self.rec.json(rec::ATTEMPTS, line);
        self.lat[LAT_DECIDED_TO_SIGNED].push(t_signed.saturating_sub(r.st[4]));
        self.lat[LAT_SIGNED_TO_FIRED].push(t_fired.saturating_sub(t_signed));
        self.sent += 1;
        self.last_sent_ns = t;
        self.reserved += BASE_FEE;
        self.count(if self.mode == Mode::Canary { "canary_sent" } else { "live_sent" });
        if crowding.rank() > 0 { self.count("rank_crowded"); }
        self.by_sig.insert(sig, attempt);
        self.open.insert(attempt, Open { attempt, decision: r.decision, opp: r.opp, sig, sig58: sig58.clone(), mint: r.mint, size: r.size, mid: r.mid, back: r.back,
            trig: r.trig, trig_slot: r.slot, expected, tip: tip_l, min_profit, creates_ata: built.creates_ata, worst: BASE_FEE, bh_slot: bh.slot, bh_height: bh.height,
            target_slot: target, leader: i.leader.identity.clone().map(|id| (id, i.leader.kind)), t_engine: t, t_signed, t_sent: None, bundle: None,
            path: paths.list[bp].name.clone(), fired: false, took_big, checks_due: Vec::new(), checks: Vec::new(), status_hit: None, expiry_asked: false,
            send_error: None, cooled: false });
        d.verdict = "send";
        d.reason = "sent".into();
        d.sent = Some(true);
        d
    }

    /// What the signed bundle of route `r` must be (the dry run's checks): from the decision's own values, never from the
    /// built message, so a builder that encodes the wrong amount or min_profit is caught (review WP-05 #12)
    fn want(&self, r: &RouteIn, signer: Pk, blockhash: [u8; 32], tip: Option<(Pk, u64)>, min_profit: u64, cu_limit: u64) -> VerifyWant<'_> {
        let mint_prog = if r.mint == r.buy.t0 { r.buy.t0_prog } else { r.buy.t1_prog };
        VerifyWant { payer: self.payer, signer, blockhash, tip, tips: self.tips.as_ref().map(|p| p.accounts.clone()).unwrap_or_default(), program: self.program,
            pools: [r.buy.pool, r.sell.pool], cu_limit, alts: &self.alt_lists, amount_in: r.size, min_profit, margin_floor: self.pol.margin_floor,
            quote: build::ata_of(&self.payer, &WSOL, &crate::pda::TOKEN_PROGRAM), mid: build::ata_of(&self.payer, &r.mint, &mint_prog),
            leg_programs: [r.buy.venue.program(), r.sell.venue.program()] }
    }

    /// One bundle transaction (PLAN WP-05 item 1; WP-06 brings its final order, rent neutrality and the size budget):
    /// the CU limit, the mid token's ATA create when the wallet holds none, the route with its on-chain `min_profit`, the
    /// tip last (a top-level System transfer: Jito ignores a tip account named through a table). On `blockhash` (item 3:
    /// a recent blockhash, never a durable nonce). No CU price: a bundle pays its tip only
    fn build(&self, r: &RouteIn, min_profit: u64, blockhash: [u8; 32], tip: Option<(Pk, u64)>) -> Result<Built, String> {
        let leg = |m: &PoolMeta, data: &[u8], tin: Pk, tout: Pk, live: &[i64], end: Option<i32>| build::leg(&build::LegIn {
            m, pool: data, tin, tout, amount_in: r.size, payer: self.payer, pump: self.pump.as_ref(), dlmm_live: live, dlmm_end: end });
        let l1 = leg(&r.buy, &r.buy_data, *WSOL, r.mint, &r.buy_live, r.buy_end).map_err(|e| format!("buy leg: {e}"))?;
        let l2 = leg(&r.sell, &r.sell_data, r.mint, *WSOL, &r.sell_live, r.sell_end).map_err(|e| format!("sell leg: {e}"))?;
        let quote = build::ata_of(&self.payer, &WSOL, &crate::pda::TOKEN_PROGRAM);
        let (amount_in, min_profit) = (r.size, min_profit);
        #[cfg(test)]
        let (amount_in, min_profit) = self.fault_route.unwrap_or((amount_in, min_profit));
        let v2 = build::route_ix(self.program, self.payer, quote, amount_in, min_profit, &[l1, l2])?;
        let creates_ata = !self.held.contains(&r.mint);
        let cu_limit = r.cu + if creates_ata { ATA_CREATE_CU } else { 0 };
        let mut ixs = vec![build::cu_limit_ix(cu_limit as u32)];
        if creates_ata {
            let prog = if r.mint == r.buy.t0 { r.buy.t0_prog } else { r.buy.t1_prog };
            ixs.push(build::create_ata_idempotent_ix(self.payer, self.payer, r.mint, prog));
        }
        ixs.push(v2);
        let mut keep = Vec::new();
        if let Some((to, lamports)) = tip { ixs.push(build::transfer_ix(self.payer, to, lamports)); keep.push(to); }
        let alts: Vec<&Alt> = self.alts.iter().collect();
        let msg = build::compile_v0(self.payer, &ixs, blockhash, &alts, &keep)?;
        let bytes = build::tx_bytes(&msg);
        if bytes > build::MAX_TX_BYTES || msg.locks > build::MAX_LOCKS { return Err(format!("oversized({bytes} bytes, {} locks)", msg.locks)); }
        Ok(Built { msg, cu_limit, creates_ata })
    }

    /// a dry run's read-only simulation (sigVerify off: the throwaway key is not the payer; the blockhash checked): its
    /// answer comes back to the engine (INPUT 9) and is written to sims.jsonl with the attempt's id. Never a send. An
    /// offline executor (a replay) calls nothing: the run's answers are in its journal
    fn spawn_dry_sim(&self, attempt: u64, raw: Vec<u8>) {
        if self.offline { return; }
        let (rpc, back) = (self.rpc.clone(), self.back.clone());
        self.rt.spawn(async move {
            let t = std::time::Instant::now();
            let mut line = json!({ "attempt": attempt, "src": "dry_run", "t_ns": now_ns() });
            match rpc.simulate_bounded(&raw, false, false, Bounds::fetch(Duration::from_secs(2), 1)).await {
                Ok(s) => {
                    let code = s.err.as_ref().and_then(build::custom_code);
                    line["sim_ms"] = json!(t.elapsed().as_secs_f64() * 1e3);
                    line["sim_slot"] = json!(s.slot);
                    line["err"] = json!(s.err);
                    line["code"] = json!(code.map(hex_code));
                    line["meaning"] = json!(crate::proglog::meaning(code, &s.err));
                    line["encoding_ok"] = json!(s.err.is_none() || code == Some(build::ERR_PROFIT));
                    line["units"] = json!(s.units);
                    line["delivered"] = json!(crate::proglog::delivered_from_logs(&s.logs).iter().map(|d| d.1).collect::<Vec<_>>());
                    if s.err.is_some() && code != Some(build::ERR_PROFIT) { line["logs_tail"] = json!(s.logs.iter().rev().take(8).rev().collect::<Vec<_>>()); }
                }
                Err(e) => line["sim_error"] = json!(e.msg),
            }
            let _ = back.send(Event::Settled(Box::new(Settled::DrySim { attempt, line })));
        });
    }

    fn route_json(r: &RouteIn) -> Value {
        json!({ "opp": r.opp, "trigger": bs58::encode(r.trig).into_string(), "trigger_feed": r.trig_feed, "slot": r.slot,
            "buy_pool": b58(&r.buy.pool), "buy_venue": r.buy.venue, "buy_source": r.buy_source,
            "sell_pool": b58(&r.sell.pool), "sell_venue": r.sell.venue, "sell_source": r.sell_source, "mint": b58(&r.mint),
            "size_lamports": r.size, "predicted_mid": r.mid, "predicted_back": r.back, "predicted_spent": r.spent, "predicted_profit": r.expected(),
            "gross_at_opp": r.gross_at_opp, "net_at_opp": r.net_at_opp,
            // WP-04 item 10: the decision and the state version it priced
            "decision": r.decision, "sv": format!("{:016x}", r.state_version), "route_age_ms": r.route_age_ms })
    }

    /// STEP 2 (diagnostic, `[sim] enabled`): build this decision's transaction (no tip, a zero blockhash replaced by the
    /// RPC) and simulate it, unsigned; the answer goes to sims.jsonl. A bounded call on the background runtime
    pub fn simulate(&mut self, r: RouteIn) {
        let t0 = now_ns();
        let min_profit = (BASE_FEE + self.cu_price * r.cu / 1_000_000).max(1);
        let built = self.build(&r, min_profit, [0u8; 32], None);
        let t_built = now_ns();
        let mut line = Self::route_json(&r);
        line["t_ns"] = json!(t0);
        line["build_us"] = json!((t_built - t0) / 1_000);
        if !self.sims_on { return; }
        let rec = self.rec.clone();
        let b = match built {
            Ok(b) => b,
            Err(e) => { self.count("sim_build_failed"); line["build_error"] = json!(e); rec.json(rec::SIMS, line); return; }
        };
        self.count("sim_sent");
        line["bytes"] = json!(build::tx_bytes(&b.msg));
        line["locks"] = json!(b.msg.locks);
        line["cu_limit"] = json!(b.cu_limit);
        line["creates_ata"] = json!(b.creates_ata);
        line["min_profit"] = json!(min_profit);
        // an offline executor (a replay) calls nothing (the diagnostic answer is not a journaled input: not replayed)
        if self.offline { return; }
        let raw = build::unsigned(&b.msg);
        let rpc = self.rpc.clone();
        self.rt.spawn(async move {
            let t = std::time::Instant::now();
            match rpc.simulate_bounded(&raw, false, true, Bounds::fetch(Duration::from_secs(2), 1)).await {
                Ok(s) => {
                    let code = s.err.as_ref().and_then(build::custom_code);
                    let delivered = crate::proglog::delivered_from_logs(&s.logs);
                    line["sim_ms"] = json!(t.elapsed().as_secs_f64() * 1e3);
                    line["sim_slot"] = json!(s.slot);
                    line["err"] = json!(s.err);
                    line["code"] = json!(code.map(hex_code));
                    line["meaning"] = json!(crate::proglog::meaning(code, &s.err));
                    line["encoding_ok"] = json!(s.err.is_none() || code == Some(build::ERR_PROFIT));
                    line["units"] = json!(s.units);
                    line["delivered"] = json!(delivered.iter().map(|d| d.1).collect::<Vec<_>>());
                    if s.err.is_some() && code != Some(build::ERR_PROFIT) { line["logs_tail"] = json!(s.logs.iter().rev().take(8).rev().collect::<Vec<_>>()); }
                }
                Err(e) => { line["sim_error"] = json!(e.msg); }
            }
            rec.json(rec::SIMS, line);
        });
    }

    // -------------------------------------------------------------------------------------------- settlement

    /// one of our own copies (a pool move by our own trade is not a trigger)
    pub fn is_ours(&self, sig: &[u8; 64]) -> bool { self.by_sig.contains_key(sig) }

    /// a feed delivered a transaction: note it if it is one of our open copies
    pub fn on_arrival(&mut self, sig: &[u8; 64], feed: u16, t: u64) {
        if !self.by_sig.contains_key(sig) { return; }
        let e = self.seen.entry(*sig).or_insert((t, feed, Vec::new()));
        if t < e.0 { e.0 = t; e.1 = feed; }
        if !e.2.iter().any(|x| x.0 == feed) { e.2.push((feed, t)); }
    }

    /// A result of the executor's tasks (journaled INPUT 9) at engine time `t`: a fire result, a statuses answer, a dry
    /// run's simulation
    pub fn on_settled(&mut self, s: Settled, t: u64, poh: &dyn Fn(&[u8; 64]) -> Option<crate::feeds::entries::Poh>) {
        match s {
            Settled::Fired { attempt, fired } => self.on_fired(attempt, fired, t, poh),
            Settled::Statuses { why, at, result, t_ns } => self.on_statuses(why, at, result, t_ns, poh),
            Settled::DrySim { line, .. } => { self.rec.json(rec::SIMS, line); }
        }
    }

    /// The send task's result. Accepted (a bundle id): open until it lands or its blockhash expires. Left without an
    /// answer (a timeout, a transport error after it may have gone out): it may land, so it stays open the same way, its
    /// in-flight entry and fee reservation kept (review WP-05 #7). Never left (a `drop` code: the queue, the token, its
    /// check) or refused by the block engine's answer: nothing can land, the attempt is final now and gives back its
    /// in-flight entry, its reservation and its big-band token (refunded at the engine's time `t`, review #13)
    fn on_fired(&mut self, attempt: u64, fired: Fired, t: u64, poh: &dyn Fn(&[u8; 64]) -> Option<crate::feeds::entries::Poh>) {
        let Some(o) = self.open.get_mut(&attempt) else { return };
        let c = fired.copies.first();
        let left = c.is_some_and(|c| c.t_sent > 0 && c.drop.is_none());
        if let Some(c) = c.filter(|c| c.t_sent > 0) { self.lat[LAT_SIGNED_TO_SENT].push(c.t_sent.saturating_sub(o.t_signed)); }
        o.fired = true;
        if let Some(c) = c.filter(|c| left && (c.ok || c.t_ack == 0)) {
            o.t_sent = Some(c.t_sent);
            o.bundle = c.bundle.clone();
            o.checks_due = CHECKS.iter().map(|(dt, l)| (c.t_sent + dt, *l)).collect();
            if !c.ok {
                o.send_error = Some(format!("send: {}", c.reply.as_deref().unwrap_or("no answer")));
                *self.counts.entry("send_unanswered").or_default() += 1;
            }
            return;
        }
        let why = c.and_then(|c| c.drop).map(String::from).or_else(|| c.and_then(|c| c.reply.clone())).unwrap_or_else(|| "no copy".into());
        if left { self.count("send_refused"); } else {
            self.never_left += 1;
            if let Some(code) = c.and_then(|c| c.drop) { self.count(drop_counter(code)); }
        }
        let o = self.open.remove(&attempt).unwrap();
        if o.took_big { self.big.refund(t); }
        self.finalize(o, "not_landed_refused", "send", None, Some(why), false, poh);
    }

    /// INPUT 7 `wallet_tx` (WP-03b): one of our wallet's transactions. One of our attempts' signatures landed: final
    /// (`landed_ok` / `landed_fail`, from the wallet), or an amend line when it was final already: a landing after a
    /// final that said not landed, or the wallet record of a landing the expiry check found first, which brings its fee,
    /// CU and the route program's events (review WP-05 #3). `t`: the engine's time (the record's journaled one: WP-09
    /// review item 5, never the real clock)
    pub fn on_wallet_tx(&mut self, d: &Value, t: u64, poh: &dyn Fn(&[u8; 64]) -> Option<crate::feeds::entries::Poh>) {
        let Some(sig) = d["sig"].as_str().and_then(sig64) else { return };
        let attempt = self.by_sig.get(&sig).copied().or_else(|| d["attempt"].as_u64().filter(|a| self.open.contains_key(a) || self.finals.contains_key(a)));
        let Some(attempt) = attempt else { return };
        let ok = d["ok"].as_bool().unwrap_or(false);
        let landed = Landed { slot: d["slot"].as_u64(), idx: d["idx"].as_u64(), ok, err: d.get("err").cloned().filter(|e| !e.is_null()), fee: d["fee"].as_u64(),
            cu: d["cu_consumed"].as_u64(), prog_events: d.get("prog_events").cloned().unwrap_or(Value::Null), t_wallet: t };
        if let Some(o) = self.open.remove(&attempt) {
            let fin = if ok { "landed_ok" } else { "landed_fail" };
            self.finalize(o, fin, "wallet", Some(landed), None, false, poh);
        } else if self.finals.get(&attempt).is_some_and(|f| !f.wallet_seen) {
            self.amend(attempt, landed, "wallet");
        }
    }

    /// INPUT 5 `inflight_release` (a block-engine result of one of our bundles, from the Jito client's sink). Only a
    /// landing (`release`: `processed`, `finalized`) releases the attempt's in-flight entry early: a would-fail, a lost
    /// auction or a drop keeps it for its hold, so the same state does not go again to the same leader (review WP-05 #2).
    /// Token cooling: an accepted or landed bundle clears its token's run of would-fails; an attempt's first would-fail
    /// adds one to it (a bundle may get several results: they count once)
    pub fn on_release(&mut self, d: &Value, t: u64) {
        let attempt = d["attempt"].as_u64().or_else(|| d["sig"].as_str().and_then(sig64).and_then(|s| self.by_sig.get(&s).copied()));
        let Some(attempt) = attempt else { return };
        let outcome = d["outcome"].as_str().unwrap_or("");
        *self.counts.entry(match outcome { "accepted" => "verdict_accepted", "processed" => "verdict_processed", "finalized" => "verdict_finalized",
            "would-fail" => "verdict_would_fail", "lost-auction" => "verdict_lost_auction", "dropped" => "verdict_dropped", _ => "verdict_rejected" }).or_default() += 1;
        if d["release"].as_bool() == Some(true) && self.inflight.release(attempt) { self.count("inflight_released"); }
        let would_fail = outcome == "would-fail";
        let first = |c: &mut bool| { let f = !*c; *c = true; f };
        let (mint, counts) = if let Some(o) = self.open.get_mut(&attempt) { (o.mint, would_fail && first(&mut o.cooled)) }
            else if let Some(f) = self.finals.get_mut(&attempt) { (f.mint, would_fail && first(&mut f.cooled)) }
            else { return };
        if would_fail && !counts { self.count("cool_repeat"); return; }
        let e = self.mint_cool.entry(mint).or_insert((0, 0, 0));
        match outcome {
            "accepted" | "processed" | "finalized" => *e = (0, 0, 0),
            "would-fail" => {
                e.0 += 1;
                if e.0 >= COOL_AFTER {
                    let secs = (60u64 << e.2.min(3)).min(300);
                    e.1 = t + secs * 1_000_000_000; e.0 = 0; e.2 += 1;
                    let n = e.2;
                    self.rec.log("send", format!("cool: token {} paused {secs} s after {COOL_AFTER} would-fails in a row (pause {n})", b58(&mint)));
                }
            }
            _ => {}
        }
    }

    /// The executor's timers (the engine's housekeeping, journaled): in-flight expiry, the cross-checks due (one batched
    /// getSignatureStatuses, 500 ms) and the attempts whose blockhash expired (one batched getSignatureStatuses with
    /// `searchTransactionHistory`, F43), each on the background runtime; the answers come back as INPUT 9. Without a slot
    /// an attempt expires `EXPIRY_NS` after its decision's engine time. An offline executor (a replay) keeps the same
    /// books and calls nothing: the run's answers are in its journal
    pub fn tick(&mut self, t: u64, view: &SendView, tip_slot: u64) {
        self.inflight.expire(tip_slot);
        let mut checks: Vec<(u64, &'static str, [u8; 64])> = Vec::new();
        let mut expiry: Vec<(u64, &'static str, [u8; 64])> = Vec::new();
        for o in self.open.values_mut() {
            if !o.fired { continue; }
            let expired = view.expired(o.bh_slot, o.bh_height, tip_slot).unwrap_or(t.saturating_sub(o.t_engine) >= EXPIRY_NS);
            if expired && !o.expiry_asked { o.expiry_asked = true; expiry.push((o.attempt, "expiry", o.sig)); continue; }
            while let Some(&(due, label)) = o.checks_due.first() {
                if due > t { break; }
                o.checks_due.remove(0);
                checks.push((o.attempt, label, o.sig));
            }
        }
        for (why, list, search, ms) in [("check", checks, false, 500u64), ("expiry", expiry, true, 2_000)] {
            for chunk in list.chunks(STATUS_BATCH) {
                let at: Vec<(u64, &'static str)> = chunk.iter().map(|x| (x.0, x.1)).collect();
                let sigs: Vec<[u8; 64]> = chunk.iter().map(|x| x.2).collect();
                let (rpc, back) = (self.settle.clone(), self.back.clone());
                self.count(if why == "check" { "status_check" } else { "expiry_check" });
                if self.offline { continue; }
                self.rt.spawn(async move {
                    let b = Bounds { deadline: Duration::from_millis(ms), retries: if search { 1 } else { 0 }, attempt_timeout: Duration::from_millis(ms),
                        backoff_first: Duration::from_millis(100), backoff_max: Duration::from_millis(500) };
                    let result = rpc.statuses_bounded(&sigs, search, b).await.map_err(|e| e.msg);
                    let _ = back.send(Event::Settled(Box::new(Settled::Statuses { why, at, result, t_ns: now_ns() })));
                });
            }
        }
    }

    fn on_statuses(&mut self, why: &'static str, at: Vec<(u64, &'static str)>, result: std::result::Result<Vec<Option<SigStatus>>, String>, t_ns: u64,
        poh: &dyn Fn(&[u8; 64]) -> Option<crate::feeds::entries::Poh>) {
        for (k, (attempt, label)) in at.into_iter().enumerate() {
            let hit = match &result { Ok(v) => Ok(v.get(k).cloned().flatten()), Err(e) => Err(e.clone()) };
            let res = match &hit { Ok(Some(s)) => json!({ "slot": s.slot, "ok": s.err.is_none(), "err": s.err, "confirmation": s.confirmation }), Ok(None) => Value::Null,
                Err(e) => json!({ "error": e }) };
            if why == "check" {
                if let Some(o) = self.open.get_mut(&attempt) {
                    o.checks.push(json!({ "t_ns": t_ns, "at": label, "result": res }));
                    if let Ok(Some(s)) = &hit { o.status_hit = Some(s.clone()); }
                } else if let (true, Ok(Some(s))) = (self.finals.get(&attempt).is_some_and(|f| !f.landed), &hit) {
                    // a late cross-check found a landing after the final: amend
                    self.amend(attempt, Landed::of_status(s), "statuses");
                }
                continue;
            }
            // the expiry check: a landing the wallet path missed, else not landed
            let Some(mut o) = self.open.remove(&attempt) else { continue };
            o.checks.push(json!({ "t_ns": t_ns, "at": "expiry", "result": res }));
            match hit {
                Ok(Some(s)) => { self.count("expiry_status_hit"); let fin = if s.err.is_none() { "landed_ok" } else { "landed_fail" }; self.finalize(o, fin, "statuses", Some(Landed::of_status(&s)), None, false, poh); }
                Ok(None) => { self.count("expired"); self.finalize(o, "not_landed_expired", "expiry", None, None, false, poh); }
                // the check failed: what a cross-check saw decides, else not landed (the wallet stream may amend it)
                Err(e) => match o.status_hit.clone() {
                    Some(s) => { let fin = if s.err.is_none() { "landed_ok" } else { "landed_fail" }; self.finalize(o, fin, "statuses", Some(Landed::of_status(&s)), Some(format!("expiry check failed: {e}")), false, poh); }
                    None => { self.count("expired"); self.finalize(o, "not_landed_expired", "expiry", None, Some(format!("expiry check failed: {e}")), false, poh); }
                },
            }
        }
    }

    /// The final outcomes.jsonl line (v2) of an attempt, its in-flight entry released, its money counted (the bot's
    /// counters until WP-07's ledger). A landing the expiry check found has no fee or events yet: its fee is counted as
    /// the base fee (exactly what a one-signature bundle at CU price 0 pays) and its round trip as unknown, until its
    /// wallet record amends them (review WP-05 #3)
    #[allow(clippy::too_many_arguments)]
    fn finalize(&mut self, o: Open, fin: &'static str, src: &'static str, landed: Option<Landed>, error: Option<String>, amend: bool,
        poh: &dyn Fn(&[u8; 64]) -> Option<crate::feeds::entries::Poh>) {
        self.inflight.release(o.attempt);
        self.reserved = self.reserved.saturating_sub(o.worst);
        self.by_sig.remove(&o.sig);
        let seen = self.seen.remove(&o.sig);
        let error = error.or_else(|| o.send_error.clone());
        let counted = landed.as_ref().map(|l| Counted::of(l, o.tip, o.size, o.creates_ata)).unwrap_or_default();
        self.add(counted, o.mint);
        let line = self.outcome_line(&o, fin, src, landed.as_ref(), error, amend, seen.as_ref(), poh);
        self.rec.json(rec::OUTCOMES, line);
        self.count(match fin { "landed_ok" => "landed_ok", "landed_fail" => "landed_fail", "not_landed_expired" => "not_landed_expired", "unsettled" => "unsettled",
            _ => "not_landed_refused" });
        self.finals.insert(o.attempt, Final { sig58: o.sig58.clone(), mint: o.mint, landed: landed.is_some(), ok: landed.as_ref().is_some_and(|l| l.ok), tip: o.tip,
            size: o.size, creates_ata: o.creates_ata, src, counted, wallet_seen: src == "wallet", cooled: o.cooled });
        self.finals_order.push_back(o.attempt);
        while self.finals_order.len() > FINALS_KEEP { if let Some(a) = self.finals_order.pop_front() { self.finals.remove(&a); } }
    }

    /// The run is stopping: every attempt still open gets its final line now, `unsettled` (`final_src` `stop`; A.2), and
    /// stop.json lists them (`unsettled`). Returns them
    pub fn settle_at_stop(&mut self) -> Vec<u64> {
        let open: Vec<u64> = self.open.keys().copied().collect();
        for a in &open { if let Some(o) = self.open.remove(a) { self.finalize(o, "unsettled", "stop", None, None, false, &|_| None); } }
        open
    }

    /// A later record of a final attempt (MEASUREMENT §4.40 `amend`): a landing found after a final that said not landed
    /// (a late cross-check, the wallet stream), or the wallet record of a landing the expiry check found first. The
    /// money then counts what this record says instead of what was counted (the landing once; the fee, the failed fee
    /// and the round trip as the record gives them: review WP-05 #3)
    fn amend(&mut self, attempt: u64, l: Landed, src: &'static str) {
        let Some(f) = self.finals.get(&attempt).cloned() else { return };
        self.count("amended");
        let fin = if l.ok { "landed_ok" } else { "landed_fail" };
        let counted = Counted::of(&l, f.tip, f.size, f.creates_ata);
        self.sub(f.counted);
        self.add(counted, f.mint);
        if let Some(x) = self.finals.get_mut(&attempt) {
            x.landed = true;
            x.ok = l.ok;
            x.src = src;
            x.counted = counted;
            x.wallet_seen |= src == "wallet";
        }
        let delivered = delivered_of(&l.prog_events);
        self.rec.json(rec::OUTCOMES, json!({ "attempt": attempt, "t_ns": now_ns(), "sig": f.sig58, "final": fin, "final_t_ns": now_ns(), "final_src": src, "amend": true,
            "amends": if f.landed { f.src } else { "not_landed" }, "landed": l.json(None), "ok": l.ok, "err": l.err, "fee_lamports": l.fee, "cu_consumed": l.cu,
            "prog_events": l.prog_events, "delivered": delivered, "round_trip_on_chain": last_leg_out(&l.prog_events).map(|b| b as i64 - f.size as i64),
            "failed_fees_total_lamports": self.spent }));
    }

    /// a landing's money into the counters (and its new token account into the held set)
    fn add(&mut self, c: Counted, mint: Pk) {
        self.landed += c.landed;
        self.wins += c.win;
        self.tips_paid += c.tip;
        self.fees += c.fee;
        self.spent += c.failed_fee;
        self.round_trip += c.round_trip;
        self.round_trip_unknown += c.rt_unknown;
        if c.atas > 0 { self.new_atas += c.atas; self.held.insert(mint); }
    }

    /// what `add` counted for a landing, taken back (a later record replaces it)
    fn sub(&mut self, c: Counted) {
        self.landed -= c.landed;
        self.wins -= c.win;
        self.tips_paid -= c.tip;
        self.fees -= c.fee;
        self.spent -= c.failed_fee;
        self.round_trip -= c.round_trip;
        self.round_trip_unknown -= c.rt_unknown;
        self.new_atas -= c.atas;
    }

    #[allow(clippy::too_many_arguments)]
    fn outcome_line(&self, o: &Open, fin: &str, src: &str, landed: Option<&Landed>, error: Option<String>, amend: bool, seen: Option<&(u64, u16, Vec<(u16, u64)>)>,
        poh: &dyn Fn(&[u8; 64]) -> Option<crate::feeds::entries::Poh>) -> Value {
        let verdicts: Vec<(u64, jito::Outcome)> = self.jito.as_ref().map(|j| j.verdicts(&o.sig58)).unwrap_or_default();
        let vj: Vec<Value> = verdicts.iter().map(|(t, v)| json!({ "t_ns": t, "outcome": v.outcome, "slot": v.slot, "validator": v.validator, "index": v.index, "bid": v.bid,
            "code": if v.outcome == "would-fail" { jito::error_code(v.detail.as_deref()) } else { None }, "detail": v.detail })).collect();
        let first_ms = o.t_sent.zip(verdicts.first()).map(|(s, (t, _))| (*t as f64 - s as f64) / 1e6);
        let accepted = verdicts.iter().find(|(_, v)| v.outcome == "accepted").map(|(t, v)| json!({ "t_ns": t, "slot": v.slot, "validator": v.validator }));
        let processed = verdicts.iter().find(|(_, v)| v.outcome == "processed").map(|(_, v)| json!({ "slot": v.slot, "index": v.index, "validator": v.validator }));
        let feed = |f: u16| self.feeds.get(f as usize).cloned().unwrap_or_default();
        let tp = poh(&o.trig);
        let op = landed.and_then(|_| poh(&o.sig));
        let code = landed.and_then(|l| l.err.as_ref()).and_then(build::custom_code);
        let delivered: Vec<u64> = landed.map(|l| delivered_of(&l.prog_events)).unwrap_or_default();
        let mut v = json!({
            "attempt": o.attempt, "decision": o.decision, "opp": o.opp, "t_ns": now_ns(), "kind": self.mode, "sig": o.sig58, "bundle": o.bundle, "path": o.path,
            "final": fin, "final_t_ns": now_ns(), "final_src": src, "amend": amend, "error": error,
            "verdicts": vj, "first_verdict_ms": first_ms, "accepted": accepted, "processed": processed,
            "landed": landed.map(|l| l.json(o.leader.as_ref())),
            "slots_after_trigger": landed.and_then(|l| l.slot).map(|s| s as i64 - o.trig_slot as i64),
        });
        v["poh"] = json!({ "trigger": tp.map(|p| json!({ "slot": p.slot, "ms": p.ms(), "ticks": p.ticks })), "ours": op.map(|p| json!({ "slot": p.slot, "ms": p.ms(), "ticks": p.ticks })),
            "ours_ms_after_trigger": op.zip(tp).and_then(|(a, b)| a.ms_after(&b)) });
        v["ms_after_trigger_src"] = if op.is_some() && tp.is_some() { json!("poh") } else { Value::Null };
        v["seen"] = json!(seen.map(|x| json!({ "first_ns": x.0, "first_feed": feed(x.1), "by": x.2.iter().map(|(f, t)| (feed(*f), json!(t))).collect::<serde_json::Map<_, _>>() })));
        v["send_to_seen_ms"] = json!(seen.zip(o.t_sent).map(|(x, s)| (x.0 as f64 - s as f64) / 1e6));
        v["ok"] = json!(landed.map(|l| l.ok));
        v["err"] = json!(landed.and_then(|l| l.err.clone()));
        v["code"] = json!(code.map(hex_code));
        v["meaning"] = json!(landed.map(|l| crate::proglog::meaning(code, &l.err)));
        v["fee_lamports"] = json!(landed.and_then(|l| l.fee));
        v["cu_consumed"] = json!(landed.and_then(|l| l.cu));
        v["prog_events"] = json!(landed.map(|l| l.prog_events.clone()));
        v["delivered"] = json!(delivered);
        v["predicted"] = json!([o.mid, o.back]);
        // the two round trips on one basis, the last leg's output minus the size (the route program's events carry what
        // each leg delivered, not what the buy leg debited); `expected` is the guard's quote delta (minus the debit)
        v["round_trip_on_chain"] = json!(landed.and_then(|l| last_leg_out(&l.prog_events)).map(|b| b as i64 - o.size as i64));
        v["round_trip_predicted"] = json!(o.back as i64 - o.size as i64);
        v["expected"] = json!(o.expected);
        v["tip_lamports"] = json!(o.tip);
        v["min_profit_onchain"] = json!(o.min_profit);
        v["blockhash"] = json!({ "slot": o.bh_slot, "height": o.bh_height, "valid_until_height": o.bh_height.map(|h| h + BLOCKHASH_VALID_BLOCKS) });
        v["target_slot"] = json!(o.target_slot);
        v["ledger"] = Value::Null;
        v["closer"] = Value::Null;
        v["statuses_checks"] = json!(o.checks);
        // status.jsonl v2 counter semantics (MEASUREMENT §2.2): the running total after this attempt
        v["failed_fees_total_lamports"] = json!(self.spent);
        v
    }

    /// for run.log: counters, spend so far against the cap
    pub fn status(&self) -> Value {
        json!({ "mode": self.mode, "counts": self.counts, "decisions": self.decisions, "would_send": self.would_sends, "sent": self.sent, "landed": self.landed, "wins": self.wins,
            "in_flight": self.open.len(), "failed_fees_total_lamports": self.spent, "cap_lamports": self.cap_failed_fees, "stopped": self.stopped })
    }

    /// the share of attempts (would-sends included) whose target leader was known, since the last call (status
    /// `coverage.leader_known_pct`; null without an attempt)
    pub fn leader_known_pct(&mut self) -> Value {
        let (n, k) = (self.leader_seen.0 - self.leader_prev.0, self.leader_seen.1 - self.leader_prev.1);
        self.leader_prev = self.leader_seen;
        if n == 0 { Value::Null } else { json!(((k as f64 * 100.0 / n as f64) * 100.0).round() / 100.0) }
    }

    /// status.jsonl `health.jito_token_age_s_now` (null: no bundle path)
    pub fn token_age_s(&self) -> Option<u64> {
        match self.jito.as_ref()?.token_state((now_ns() / 1_000_000) as i64) { jito::TokenState::Valid { age_s, .. } => Some(age_s), jito::TokenState::Stale => None }
    }

    /// the blockhash commitment the send checks use
    pub fn blockhash_commitment(&self) -> &str { &self.pol.blockhash_commitment }

    /// status.jsonl v2 (MEASUREMENT §4.8, §2.2): the `exec` section and the `money` section, deltas against `prev`.
    /// `money` holds the bot's own counters until WP-07's ledger (`src: "bot"`; zeros for a shadow or dry run, which
    /// send nothing)
    pub fn status_v2(&self, prev: &mut ExecPrev) -> (Value, Value) {
        let mut counts_delta = serde_json::Map::new();
        for (k, v) in &self.counts {
            let d = v - prev.counts.get(k).copied().unwrap_or(0);
            if d > 0 { counts_delta.insert(k.to_string(), json!(d)); }
        }
        prev.counts = self.counts.clone();
        // every block-engine result so far, by outcome (the jito path's result stream)
        let mut verdicts: std::collections::BTreeMap<&'static str, u64> = Default::default();
        if let Some(j) = &self.jito { for (k, v) in j.counts.lock().unwrap().iter() { *verdicts.entry(k).or_default() += v; } }
        let verdicts_delta: serde_json::Map<String, Value> = verdicts.iter().filter_map(|(k, v)| {
            let d = v - prev.verdicts.get(k).copied().unwrap_or(0);
            (d > 0).then(|| (k.to_string(), json!(d)))
        }).collect();
        prev.verdicts = verdicts;
        let over_rate = self.paths.as_ref().map(|p| {
            let (mut all, mut crowded) = (0u64, 0u64);
            for x in &p.list { let st = x.stats.lock().unwrap(); all += st.limited; crowded += st.limited_crowded; }
            json!({ "crowded": crowded, "other": all.saturating_sub(crowded) })
        });
        let (queue, lambda) = self.paths.as_ref().map(|p| p.queue_now()).map_or((None, None), |(q, l)| (Some(q), l));
        let exec = json!({ "kind": self.mode, "stopped": self.stopped, "counts_total": self.counts, "counts_delta": counts_delta, "verdicts_delta": verdicts_delta,
            "over_rate_total": over_rate, "decisions_total": self.decisions, "decisions_delta": self.decisions - prev.decisions, "refused_total": self.refusals,
            "would_send_total": self.would_sends, "would_send_delta": self.would_sends - prev.would_sends,
            "attempts_total": self.next_attempt, "attempts_delta": self.next_attempt - prev.attempts, "sent_total": self.sent, "sent_delta": self.sent as u64 - prev.sent,
            "landed_total": self.landed, "landed_delta": self.landed as u64 - prev.landed, "ok_total": self.wins, "in_flight_now": self.open.len(),
            "inflight_keys_now": self.inflight.len(), "queue_now": queue, "lambda_now": lambda, "net_calls_send_path_total": self.net_calls() });
        let money = json!({ "src": "bot", "failed_fees_total_lamports": self.spent, "failed_fees_delta_lamports": self.spent - prev.spent.min(self.spent),
            "failed_fees_cap_now_lamports": self.cap_failed_fees, "fees_landed_total_lamports": self.fees, "tips_paid_total_lamports": self.tips_paid,
            "round_trip_total_lamports": self.round_trip, "round_trip_unknown_total": self.round_trip_unknown,
            "new_token_accounts_total": self.new_atas });
        prev.decisions = self.decisions;
        prev.would_sends = self.would_sends;
        prev.attempts = self.next_attempt;
        prev.sent = self.sent as u64;
        prev.landed = self.landed as u64;
        prev.spent = self.spent;
        (exec, money)
    }

    pub fn payer(&self) -> Pk { self.payer }

    // -------------------------------------------------------------------------------------------- replay (WP-09)

    /// ---- WP-09. A replay's executor (review WP-09 "For the WP-05 merge" item 1): `assemble` on the run's exec_init
    /// record (its lookup tables, PumpSwap GlobalConfig and held tokens), with no RPC endpoint, no send path and no key,
    /// and the record's size cap, would-send rate and tip policy. A dry run's would-sends are signed by a new throwaway
    /// key: only their signatures differ from the run's. It reads the run's journaled decision inputs (`stage_seen`) and
    /// spawns nothing. A live or canary executor is not replayed (its sends cannot be): refused
    pub fn offline(cfg: &Config, init: &ExecInit, rec: Rec) -> Result<Exec> {
        anyhow::ensure!(!init.mode.sends(), "a {} executor is not replayed (its sends cannot be): only shadow and dry-run executors are", init.mode.as_str());
        let key = if init.mode == Mode::DryRun { Some(ephemeral_key()?) } else { None };
        let rt = offline_runtime();
        let _in = rt.enter();
        let mut x = Exec::assemble(cfg, Rpc::race(vec![]), None, rec, crossbeam_channel::unbounded().0, vec![], init.alts.clone(), init.pump.clone(),
            init.held.iter().copied().collect(), init.mode, key)?;
        x.offline = true;
        x.max_size = init.size_cap();
        x.path_rate = init.would_send_per_sec;
        x.tips = init.tips.clone();
        Ok(x)
    }

    /// whether this is a replay's offline executor
    pub fn is_offline(&self) -> bool { self.offline }

    /// What this executor started with: its part of the exec_init record (the engine adds the crowding map's,
    /// `Engine::exec_init`). Taken before its first decision (the tip rotation's cursor is then 0)
    pub fn init(&self) -> ExecInit {
        let mut held: Vec<Pk> = self.held.iter().copied().collect();
        held.sort();
        ExecInit { mode: self.mode, alts: self.alts.iter().map(|a| (a.key, self.alt_lists.get(&a.key).map(|l| l.to_vec()).unwrap_or_default())).collect(),
            pump: self.pump.clone(), held, max_size: self.max_size, max_size_src: if self.mode == Mode::Canary { "canary" } else { "live" }.into(), bankroll_cap: None,
            would_send_per_sec: self.path_rate, tips: self.tips.clone(), crowding_window_h: 0, crowding_buckets: [0, 0], crowded: vec![], cfg_sha256: self.cfg_sha256.clone() }
    }

    /// ---- WP-09 (review WP-09 "For the WP-05 merge" item 7). A digest of the executor's decision state, folded into
    /// `Engine::digest`: its totals and counters, the in-flight map, the ≥1M class's bucket, token cooling, the would-send
    /// and simulation windows, the open and final attempts, its copies' arrivals, the held tokens, the tip rotation, what
    /// the last decision read of the gate. Left out: stage times and latency series (real clock reads), the network-call
    /// scope, the recorder, the LeaderBook, a replay's own bookkeeping (`seen_*`)
    pub fn digest(&self, x: &mut xxhash_rust::xxh3::Xxh3) {
        fn u(x: &mut xxhash_rust::xxh3::Xxh3, v: u64) { x.update(&v.to_le_bytes()); }
        x.update(self.mode.as_str().as_bytes());
        for v in [self.decisions, self.refusals, self.would_sends, self.sent as u64, self.last_sent_ns, self.landed as u64, self.wins as u64, self.spent, self.reserved,
            self.fees, self.tips_paid, self.round_trip as u64, self.round_trip_unknown as u64, self.never_left as u64, self.new_atas as u64, self.next_attempt,
            self.leader_seen.0, self.leader_seen.1] { u(x, v); }
        x.update(self.stopped.unwrap_or("-").as_bytes());
        x.update(self.refused.as_deref().unwrap_or("-").as_bytes());
        x.update(&[self.gate_seen.map_or(9, |g| g as u8)]);
        let mut counts: Vec<(&&str, &u64)> = self.counts.iter().collect();
        counts.sort();
        for (k, v) in counts { x.update(k.as_bytes()); u(x, *v); }
        let mut inflight: Vec<(&InflightKey, &InflightEntry)> = self.inflight.map.iter().collect();
        inflight.sort_by_key(|e| (e.0.buy, e.0.sell, e.0.mint));
        u(x, inflight.len() as u64);
        for (k, e) in inflight {
            x.update(&k.buy); x.update(&k.sell); x.update(&k.mint);
            for v in [e.sv, e.target_slot, e.attempt, e.t] { u(x, v); }
            x.update(&e.leader.unwrap_or([0; 32]));
        }
        let (units, last) = self.big.state();
        x.update(&units.to_le_bytes());
        u(x, last.unwrap_or(u64::MAX));
        let mut cool: Vec<(&Pk, &(u32, u64, u32))> = self.mint_cool.iter().collect();
        cool.sort();
        for (k, c) in cool { x.update(k); for v in [c.0 as u64, c.1, c.2 as u64] { u(x, v); } }
        for w in [&self.would_recent, &self.sim_recent] { u(x, w.len() as u64); for t in w { u(x, *t); } }
        if let Some(d) = &self.dry { u(x, d.sim_recent.len() as u64); for t in &d.sim_recent { u(x, *t); } }
        u(x, self.open.len() as u64);
        for (a, o) in &self.open {
            u(x, *a);
            x.update(&o.sig);
            x.update(&o.mint);
            for v in [o.decision, o.opp, o.size, o.expected as u64, o.tip, o.min_profit, o.worst, o.bh_slot, o.bh_height.unwrap_or(u64::MAX), o.target_slot, o.t_engine,
                o.t_sent.unwrap_or(u64::MAX), o.checks.len() as u64, o.status_hit.as_ref().map_or(u64::MAX, |s| s.slot)] { u(x, v); }
            x.update(&[o.creates_ata as u8, o.fired as u8, o.took_big as u8, o.expiry_asked as u8, o.cooled as u8]);
            x.update(o.bundle.as_deref().unwrap_or("-").as_bytes());
            x.update(o.send_error.as_deref().unwrap_or("-").as_bytes());
            for (t, l) in &o.checks_due { u(x, *t); x.update(l.as_bytes()); }
        }
        let mut finals: Vec<(&u64, &Final)> = self.finals.iter().collect();
        finals.sort_by_key(|f| *f.0);
        u(x, finals.len() as u64);
        for (a, f) in finals {
            u(x, *a);
            x.update(f.sig58.as_bytes());
            x.update(&f.mint);
            x.update(f.src.as_bytes());
            x.update(&[f.landed as u8, f.ok as u8, f.creates_ata as u8, f.wallet_seen as u8, f.cooled as u8]);
            let c = &f.counted;
            for v in [f.tip, f.size, c.landed as u64, c.win as u64, c.tip, c.fee, c.failed_fee, c.round_trip as u64, c.rt_unknown as u64, c.atas as u64] { u(x, v); }
        }
        let mut by_sig: Vec<(&[u8; 64], &u64)> = self.by_sig.iter().collect();
        by_sig.sort();
        for (s, a) in by_sig { x.update(s); u(x, *a); }
        let mut seen: Vec<(&[u8; 64], &(u64, u16, Vec<(u16, u64)>))> = self.seen.iter().collect();
        seen.sort_by_key(|s| *s.0);
        for (s, (t, f, by)) in seen { x.update(s); u(x, *t); u(x, *f as u64); for (f, t) in by { u(x, *f as u64); u(x, *t); } }
        let mut held: Vec<&Pk> = self.held.iter().collect();
        held.sort();
        u(x, held.len() as u64);
        for k in held { x.update(k); }
        u(x, self.tips.as_ref().map_or(u64::MAX, |p| p.cursor as u64));
    }
}

/// ---- WP-09 (review WP-09 "For the WP-05 merge" items 1, 2). What an executor starts with that the run's frozen
/// config does not hold, journaled once with the boot records as INPUT 12 `exec_init` (`t_engine_ns` 0; MEASUREMENT
/// §4.13) by `Engine::journal_exec_init`: the mode; the `[exec] alts` lookup tables as the boot read them; PumpSwap's
/// GlobalConfig as the boot decoded it; the tokens the wallet held an account for; the size cap (`[live]`'s or the
/// canary's) and a bankroll-derived cap (none before WP-06 / WP-07); the would-send rate (the bundle path's); the
/// bundle path's tip policy; the crowding map's window, buckets and WP-00's static list (the crowded-pools file's
/// contents, as read at the start); the sha256 of the config sections the executor decides with. A replay builds its
/// offline executor and the crowding map from it, and reads no file outside the run
#[derive(Clone, Debug, PartialEq)]
pub struct ExecInit {
    pub mode: Mode,
    pub alts: Vec<(Pk, Vec<Pk>)>,
    pub pump: Option<PumpGlobal>,
    pub held: Vec<Pk>,
    pub max_size: u64,
    pub max_size_src: String,
    pub bankroll_cap: Option<u64>,
    pub would_send_per_sec: usize,
    pub tips: Option<TipPolicy>,
    pub crowding_window_h: u64,
    pub crowding_buckets: [u32; 2],
    pub crowded: Vec<Pk>,
    /// `cfg_sha256(cfg)` of the run's config
    pub cfg_sha256: String,
}

fn pk58(s: &str) -> Option<Pk> { bs58::decode(s).into_vec().ok()?.try_into().ok() }

impl ExecInit {
    /// the journal's INPUT 12 body
    pub fn json(&self) -> Value {
        let keys = |v: &[Pk]| v.iter().map(b58).collect::<Vec<_>>();
        json!({ "mode": self.mode, "alts": self.alts.iter().map(|(k, a)| json!({ "table": b58(k), "addrs": keys(a) })).collect::<Vec<_>>(),
            "pump": self.pump.as_ref().map(|g| json!({ "disable_flags": g.disable_flags, "protocol": keys(&g.protocol), "reserved": keys(&g.reserved), "buyback": keys(&g.buyback) })),
            "held_mints": keys(&self.held), "max_size_lamports": self.max_size, "max_size_src": self.max_size_src, "bankroll_cap_lamports": self.bankroll_cap,
            "would_send_per_sec": self.would_send_per_sec,
            "tips": self.tips.as_ref().map(|p| json!({ "path": p.path, "accounts": keys(&p.accounts), "floor": p.floor, "share": p.share, "max": p.max })),
            "crowding": { "window_h": self.crowding_window_h, "buckets": self.crowding_buckets, "static_list": keys(&self.crowded) },
            "cfg_sha256": self.cfg_sha256 })
    }

    /// read back (None: not an exec_init body this build reads)
    pub fn from_json(v: &Value) -> Option<ExecInit> {
        let keys = |v: &Value| -> Option<Vec<Pk>> { v.as_array()?.iter().map(|k| k.as_str().and_then(pk58)).collect() };
        let mode = match v["mode"].as_str()? { "live" => Mode::Live, "canary" => Mode::Canary, "shadow" => Mode::Shadow, "dry_run" => Mode::DryRun, _ => return None };
        let alts = v["alts"].as_array()?.iter().map(|a| Some((pk58(a["table"].as_str()?)?, keys(&a["addrs"])?))).collect::<Option<Vec<_>>>()?;
        let pump = match &v["pump"] {
            Value::Null => None,
            g => Some(PumpGlobal { disable_flags: u8::try_from(g["disable_flags"].as_u64()?).ok()?, protocol: keys(&g["protocol"])?, reserved: keys(&g["reserved"])?,
                buyback: keys(&g["buyback"])? }),
        };
        let tips = match &v["tips"] {
            Value::Null => None,
            p => Some(TipPolicy { accounts: keys(&p["accounts"])?, floor: p["floor"].as_u64()?, share: p["share"].as_f64(), max: p["max"].as_u64()?, cursor: 0,
                path: p["path"].as_str()?.to_string() }),
        };
        let c = &v["crowding"];
        let b = c["buckets"].as_array()?;
        Some(ExecInit { mode, alts, pump, held: keys(&v["held_mints"])?, max_size: v["max_size_lamports"].as_u64()?, max_size_src: v["max_size_src"].as_str().unwrap_or("").into(),
            bankroll_cap: v["bankroll_cap_lamports"].as_u64(), would_send_per_sec: usize::try_from(v["would_send_per_sec"].as_u64()?).ok()?, tips,
            crowding_window_h: c["window_h"].as_u64()?, crowding_buckets: [u32::try_from(b.first()?.as_u64()?).ok()?, u32::try_from(b.get(1)?.as_u64()?).ok()?],
            crowded: keys(&c["static_list"])?, cfg_sha256: v["cfg_sha256"].as_str()?.to_string() })
    }

    /// the largest size a decision trades: the size cap, under a bankroll-derived one when there is one
    pub fn size_cap(&self) -> u64 { self.bankroll_cap.map_or(self.max_size, |b| b.min(self.max_size)) }
}

/// ---- WP-09 (review WP-09 "For the WP-05 merge" item 3). What a run's executor decision read from outside the journal,
/// as the engine journaled it at the decision (INPUT 3 `src` "decision", written whenever it differs from the last
/// one: the SendGate's mode or reason, the target slot's leader kind, the Jito token, the recorder), read back by a
/// replay's offline executor. The record also names the decision's target slot and leader identity, which the replay
/// computes itself from the journaled schedule (a difference is a divergence)
#[derive(Clone, Debug, PartialEq)]
pub struct Seen {
    pub opp: u64,
    pub gate: GateMode,
    pub gate_reason: String,
    pub leader_slot: Option<u64>,
    pub identity: Option<String>,
    pub kind: LeaderKind,
    pub kind_src: Option<String>,
    pub token_ok: bool,
    pub recorder_ok: bool,
}

impl Seen {
    /// a record as `Engine::after_opportunity` writes it; None for one without the executor's fields (a decision without
    /// an executor writes `executor: false` records)
    pub fn from_json(d: &Value) -> Option<Seen> {
        let gate = match d["mode"].as_str()? { "live" => GateMode::Live, "shadow" => GateMode::Shadow, "stopped" => GateMode::Stopped, _ => return None };
        let l = &d["leader"];
        Some(Seen { opp: d["opp"].as_u64()?, gate, gate_reason: d["reason"].as_str().unwrap_or("").to_string(), leader_slot: l["slot"].as_u64(),
            identity: l["identity"].as_str().map(String::from), kind: kind_of(l["kind"].as_str()?)?, kind_src: l["kind_src"].as_str().map(String::from),
            token_ok: d["jito_token_ok"].as_bool()?, recorder_ok: d["recorder_ok"].as_bool()? })
    }
}

/// the runtime an offline executor is assembled on: never driven (an offline executor spawns nothing) and never dropped
pub fn offline_runtime() -> tokio::runtime::Handle {
    static RT: std::sync::OnceLock<tokio::runtime::Runtime> = std::sync::OnceLock::new();
    RT.get_or_init(|| tokio::runtime::Builder::new_current_thread().build().expect("a current-thread runtime")).handle().clone()
}

/// sha256 of the config the executor decides with (exec_init `cfg_sha256`): `[exec]`, `[[send]]`, `[send_policy]`,
/// `[live]` without its failed-fee cap (the supervisor's `--budget-left` lowers it for a segment, and only a sending
/// executor reads it), `[canary]`, `[sim]`, `[dry_run]`, the wallet and `[strategy] cu_price_micro`. A replay's config must
/// give the run's
pub fn cfg_sha256(cfg: &Config) -> String {
    let mut live = serde_json::to_value(&cfg.live).unwrap_or(Value::Null);
    if let Some(o) = live.as_object_mut() { o.remove("max_failed_fees_lamports"); }
    let v = json!({ "wallet": cfg.wallet, "exec": cfg.exec, "sends": cfg.sends, "send_policy": cfg.send_policy, "live": live, "canary": cfg.canary, "sim": cfg.sim,
        "dry_run": cfg.dry_run, "cu_price_micro": cfg.strategy.cu_price_micro });
    crate::provenance::sha256_hex(&serde_json::to_vec(&v).unwrap_or_default())
}

fn sig58_of(s: &[u8; 64]) -> String { bs58::encode(s).into_string() }
/// the lookup tables a built message loads accounts from (attempts `tx.alts`)
fn lookups_of(msg: &build::Message) -> Vec<String> {
    crate::tx::parse_wire(&build::unsigned(msg)).map(|(tx, _)| tx.lookups.iter().map(|l| b58(&l.table)).collect()).unwrap_or_default()
}
/// what each leg delivered, in order: the `out` events of the route program's logs (`proglog::events`, as the wallet
/// stream's record carries them)
fn delivered_of(prog_events: &Value) -> Vec<u64> {
    prog_events.as_array().into_iter().flatten().filter(|e| e["kind"] == "out").filter_map(|e| e["amount"].as_u64()).collect()
}

/// what the route's last leg delivered (the quote back): the `out` event of the highest leg (the last one without leg
/// numbers), whatever the number of legs (review WP-05 #15)
fn last_leg_out(prog_events: &Value) -> Option<u64> {
    let outs = prog_events.as_array().into_iter().flatten().filter(|e| e["kind"] == "out").filter_map(|e| Some((e["leg"].as_u64(), e["amount"].as_u64()?)));
    outs.fold(None, |best: Option<(Option<u64>, u64)>, (leg, amount)| match best { Some((b, _)) if leg < b => best, _ => Some((leg, amount)) }).map(|x| x.1)
}
fn base64_of(b: &[u8]) -> String { use base64::Engine as _; base64::engine::general_purpose::STANDARD.encode(b) }

/// The executor's refusal reasons (MEASUREMENT A.1) and their counters (A.7): `reject_<reason>` when the reason refused
/// the decision, `ungated_<reason>` when a closed SendGate refused it first (counted `reject_gate_*`), so the `reject_*`
/// counters sum to the refusals (review WP-05 #16). The text before a `:` is the reason (`gate_shadow:<why>`,
/// `build_error:<detail>`)
macro_rules! reasons {
    ($($r:literal),* $(,)?) => {
        /// the counter of a refusal reason (`reject_<reason>`; `reject_other` for an unknown one)
        pub fn reject_counter(reason: &str) -> &'static str {
            match reason.split(':').next().unwrap_or("") { $($r => concat!("reject_", $r),)* _ => "reject_other" }
        }
        /// the counter of what refused a decision the closed gate refused first (`ungated_<reason>`)
        pub fn ungated_counter(reason: &str) -> &'static str {
            match reason.split(':').next().unwrap_or("") { $($r => concat!("ungated_", $r),)* _ => "ungated_other" }
        }
    };
}

reasons!("gate_shadow", "gate_stopped", "recorder_unhealthy", "warmup", "state_unavailable", "resync", "fee_cap", "sender_stopped", "canary_wait", "canary_count",
    "blockhash_stale", "leader_unknown", "leader_skip_kind", "jito_auth_stale", "expected_below_min_profit", "implausible_gap", "token_cooling", "rent_cap",
    "inflight_same_state", "inflight_same_leader", "band_throttle", "crowded_skip", "would_rate", "would_rate_crowded", "oversized", "build_error");

/// the counter of a copy that never left (copies.jsonl `drop`, MEASUREMENT §4.38): `drop_<code>`. Such an attempt was
/// handed to the fire, so it is not a refused decision (review WP-05 #16)
pub fn drop_counter(code: &str) -> &'static str {
    match code {
        "rate_queue_timeout" => "drop_rate_queue_timeout", "crowded_pool" => "drop_crowded_pool", "bad_tx" => "drop_bad_tx",
        "jito_auth_stale" => "drop_jito_auth_stale", "send_task" => "drop_send_task", _ => "drop_other",
    }
}

/// a landing as the settlement knows it
#[derive(Clone, Debug)]
struct Landed { slot: Option<u64>, idx: Option<u64>, ok: bool, err: Option<Value>, fee: Option<u64>, cu: Option<u64>, prog_events: Value, t_wallet: u64 }

/// What one landing adds to the bot's money counters: the landing, a win and its tip, its fee (and as a failed fee
/// when it failed), a win's round trip when the route program's events give it (else it is unknown), the token account
/// it created
#[derive(Clone, Copy, Debug, Default, PartialEq)]
struct Counted { landed: u32, win: u32, tip: u64, fee: u64, failed_fee: u64, round_trip: i64, rt_unknown: u32, atas: u32 }

impl Counted {
    /// a landing of a bundle tipping `tip` for `size` (a record without a fee: the base fee, what our one-signature
    /// bundles at CU price 0 pay)
    fn of(l: &Landed, tip: u64, size: u64, creates_ata: bool) -> Counted {
        let fee = l.fee.unwrap_or(BASE_FEE);
        let rt = if l.ok { last_leg_out(&l.prog_events).map(|b| b as i64 - size as i64) } else { None };
        Counted { landed: 1, win: l.ok as u32, tip: if l.ok { tip } else { 0 }, fee, failed_fee: if l.ok { 0 } else { fee }, round_trip: rt.unwrap_or(0),
            rt_unknown: (l.ok && rt.is_none()) as u32, atas: (l.ok && creates_ata) as u32 }
    }
}

impl Landed {
    fn of_status(s: &SigStatus) -> Landed { Landed { slot: Some(s.slot), idx: None, ok: s.err.is_none(), err: s.err.clone(), fee: None, cu: None, prog_events: Value::Null, t_wallet: 0 } }
    fn json(&self, leader: Option<&(String, LeaderKind)>) -> Value {
        json!({ "slot": self.slot, "idx": self.idx, "t_wallet_ns": (self.t_wallet > 0).then_some(self.t_wallet), "leader": leader.map(|l| l.0.clone()), "leader_kind": leader.map(|l| l.1) })
    }
}

/// What `status_v2`'s deltas are against (the previous status line)
#[derive(Default)]
pub struct ExecPrev { counts: HashMap<&'static str, u64>, verdicts: std::collections::BTreeMap<&'static str, u64>, decisions: u64, would_sends: u64, attempts: u64, sent: u64, landed: u64, spent: u64 }

/// attempts.jsonl v2 (MEASUREMENT §4.37), the parts every mode writes
struct AttemptLine<'a> {
    attempt: u64,
    r: &'a RouteIn,
    mode: Mode,
    expected: i64,
    band: u8,
    crowding: Crowding,
    tip: Option<(Pk, u64)>,
    tip_policy: Option<&'a TipPolicy>,
    min_profit: u64,
    margin: u64,
    built: &'a Built,
    bh: &'a Bh,
    bh_age: Option<u64>,
    leader: Value,
    key: InflightKey,
    prev: Option<(u64, u64)>,
    why_allowed: &'static str,
    prio: Prio,
    lambda: Option<i64>,
    t_built0: u64,
    t_built: u64,
    payer: Pk,
    program: Pk,
}

impl AttemptLine<'_> {
    fn json(&self) -> Value {
        let r = self.r;
        let tip_l = self.tip.map_or(0, |t| t.1);
        let mut checks: Vec<&str> = SEND_CHECKS.to_vec();
        checks.extend(["expected", "gap", "cooling", "rent", "inflight", "band", "crowding", "min_profit", "rate", "build"]);
        json!({
            "attempt": self.attempt, "decision": r.decision, "opp": r.opp, "t_ns": self.t_built, "kind": self.mode,
            "trigger": { "txn": bs58::encode(r.trig).into_string(), "slot": r.slot, "kind": r.trig_kind, "t_first_shred": r.t_first_shred, "feed": r.trig_feed },
            "route": { "buy_pool": b58(&r.buy.pool), "buy_venue": r.buy.venue, "buy_source": r.buy_source, "sell_pool": b58(&r.sell.pool), "sell_venue": r.sell.venue,
                "sell_source": r.sell_source, "mint": b58(&r.mint), "mint_prog": b58(if r.mint == r.buy.t0 { &r.buy.t0_prog } else { &r.buy.t1_prog }), "hub": b58(&WSOL) },
            "size_lamports": r.size,
            "expected": { "mid": r.mid, "back": r.back, "spent": r.spent, "gross": self.expected, "fee": BASE_FEE, "tip": tip_l, "net": self.expected - tip_l as i64 - BASE_FEE as i64 },
            "band": self.band, "sv": format!("{:016x}", r.state_version), "route_age_ms": r.route_age_ms,
            "parts_skew_slots": r.parts_skew.map(|(b, s)| json!({ "buy": b, "sell": s })),
            "min_profit_onchain": self.min_profit, "margin": self.margin,
            "tip": { "lamports": tip_l, "account": self.tip.map(|t| b58(&t.0)), "sender": self.tip_policy.map(|p| p.path.clone()), "share": self.tip_policy.and_then(|p| p.share),
                "band": self.band, "arm": null, "policy": "share_of_edge" },
            "tx": { "sig": null, "bytes": build::tx_bytes(&self.built.msg), "locks": self.built.msg.locks, "alts": lookups_of(&self.built.msg), "alt_fallback": "none", "cu_limit": self.built.cu_limit,
                "cu_src": "fallback", "cu_price_micro": 0, "loaded_data_limit": null, "creates_ata": self.built.creates_ata, "closes_ata": false, "guard_max_drop": null,
                "payer": b58(&self.payer), "program": { "id": b58(&self.program), "kind": "nexus-v2", "layout": "v2" } },
            "blockhash": { "hash": b58(&self.bh.hash), "slot": self.bh.slot, "height": self.bh.height, "age_slots": self.bh_age, "commitment": self.bh.commitment, "src": self.bh.src },
            "leader": self.leader,
            "crowding": self.crowding,
            "inflight": { "key": self.key.json(), "prev_attempt": self.prev.map(|p| p.0), "prev_sv": self.prev.map(|p| format!("{:016x}", p.1)), "why_allowed": self.why_allowed },
            "queue": { "rank": self.prio.rank(), "band_rank": self.prio.band, "crowd_rank": self.prio.crowd, "ev": self.prio.ev, "wait_us": null, "lambda": self.lambda },
            "experiments": {},
            "checks": checks,
            "stages": { "t_first_shred": r.t_first_shred, "t_update_recv": r.st[0], "t_commit": r.t_commit, "t_engine": r.st[2], "t_priced": r.t_priced, "t_decided": r.st[4],
                "t_built": self.t_built, "t_build_start": self.t_built0, "t_signed": null, "t_enqueued": null, "t_dequeued": null, "t_sent": null, "t_ack": null },
            "copies": [{ "path": self.tip_policy.map(|p| p.path.clone()), "sig": null, "bytes": build::tx_bytes(&self.built.msg), "tip": tip_l, "min_profit": self.min_profit }],
            "route_in": { "accounts": r.accounts.iter().map(|(k, slot, wv)| json!({ "acct": b58(k), "slot": slot, "wv": wv })).collect::<Vec<_>>(),
                "dlmm_arrays": { "buy": r.buy_live, "sell": r.sell_live }, "buy_end": r.buy_end, "sell_end": r.sell_end },
            "net_at_opp": r.net_at_opp, "gross_at_opp": r.gross_at_opp,
        })
    }
}

/// What a signed bundle transaction must be (the dry run's checks), from the decision's own values
pub struct VerifyWant<'a> {
    pub payer: Pk,
    /// the key that signed it (the dry run's throwaway key)
    pub signer: Pk,
    pub blockhash: [u8; 32],
    pub tip: Option<(Pk, u64)>,
    pub tips: Vec<Pk>,
    pub program: Pk,
    pub pools: [Pk; 2],
    pub cu_limit: u64,
    pub alts: &'a HashMap<Pk, Arc<Vec<Pk>>>,
    /// the route instruction's amount_in (the attempt's `size_lamports`) and min_profit (its `min_profit_onchain`)
    pub amount_in: u64,
    pub min_profit: u64,
    /// `[send_policy] margin_floor`: the signed min_profit covers the signed tip + the base fee + at least this
    pub margin_floor: u64,
    /// the route's accounts: the quote account (the payer's WSOL account, where the last leg delivers), the mid token's
    /// account (where the first leg delivers), and each leg's venue program
    pub quote: Pk,
    pub mid: Pk,
    pub leg_programs: [Pk; 2],
}

/// The nexus-v2 route instruction as a signed transaction carries it (data `[2, n, amount_in u64, min_profit u64, per
/// leg {n_accounts, amount_offset, data_len u16}, leg data]`; accounts: authority, quote, then per leg its output account,
/// its program and its own accounts: build.rs `route_ix`)
#[derive(Debug, PartialEq)]
pub struct RouteSeen { pub amount_in: u64, pub min_profit: u64, pub authority: Pk, pub quote: Pk, pub legs: Vec<LegSeen> }

/// one leg of a [`RouteSeen`]: where it delivers, its program, its accounts
#[derive(Debug, PartialEq)]
pub struct LegSeen { pub out: Pk, pub program: Pk, pub accounts: Vec<Pk> }

/// the route instruction of `program` in a parsed transaction whose full account list is `all` (None: none, more than
/// one, or one that does not decode)
pub fn route_of(tx: &crate::tx::Tx, all: &[Pk], program: &Pk) -> Option<RouteSeen> {
    let mut ixs = tx.ixs.iter().filter(|ix| tx.keys.get(ix.program as usize) == Some(program));
    let ix = ixs.next()?;
    if ixs.next().is_some() { return None; }
    let d = &ix.data;
    let u64_at = |i: usize| d.get(i..i + 8).map(|b| u64::from_le_bytes(b.try_into().unwrap()));
    if d.first() != Some(&2) { return None; }
    let n = *d.get(1)? as usize;
    let (amount_in, min_profit) = (u64_at(2)?, u64_at(10)?);
    let key = |k: usize| ix.accounts.get(k).and_then(|&i| all.get(i as usize)).copied();
    let (authority, quote) = (key(0)?, key(1)?);
    let (mut at, mut data_len) = (2usize, 0usize);
    let mut legs = Vec::with_capacity(n);
    for l in 0..n {
        let desc = d.get(18 + 4 * l..22 + 4 * l)?;
        // bits 6-7 of the account count are the NATIVE flags (build.rs refuses them on the v2 layout)
        if desc[0] & 0xC0 != 0 { return None; }
        let na = desc[0] as usize;
        data_len += u16::from_le_bytes([desc[2], desc[3]]) as usize;
        let accounts: Vec<Pk> = (at + 2..at + 2 + na).map(key).collect::<Option<_>>()?;
        legs.push(LegSeen { out: key(at)?, program: key(at + 1)?, accounts });
        at += 2 + na;
    }
    if d.len() != 18 + 4 * n + data_len || ix.accounts.len() != at { return None; }
    Some(RouteSeen { amount_in, min_profit, authority, quote, legs })
}

/// The signed bundle transaction's checks (go-live gate item 4: its size, tip and accounts checked), each
/// `{check, ok, detail}`, read from the signed bytes: one signed v0 transaction with nothing after it; its signature
/// verifies with the signer's key; the payer is the wallet; size and locks within the limits; the blockhash is the one
/// chosen; the CU limit; the tip last, a top-level System transfer of the tip from the payer to a Jito tip account
/// (`Path::check`'s rule too); the route program; both pools among its accounts; and the route instruction itself
/// (review WP-05 #12): it decodes (`route_data`), its amount_in and min_profit are the decision's (`route_amount_in`,
/// `route_min_profit`), the signed min_profit covers the signed tip + the base fee + the margin floor
/// (`min_profit_covers_tip`: a landed bundle cannot lose), and its accounts are the payer, the quote account and per leg
/// its output account, its venue's program and its pool (`route_accounts`)
pub fn verify_bundle(raw: &[u8], w: &VerifyWant) -> Vec<Value> {
    let mut out = Vec::new();
    let mut put = |check: &str, ok: bool, detail: Value| out.push(json!({ "check": check, "ok": ok, "detail": detail }));
    let parsed = crate::tx::parse_wire(raw);
    let Some((tx, used)) = parsed else { put("parses", false, json!("not a transaction")); return out };
    put("parses", used == raw.len(), json!({ "bytes": raw.len(), "used": used }));
    put("one_signature", tx.num_signers == 1, json!(tx.num_signers));
    // the message is what follows the signature (one signature: 1 + 64 bytes)
    let sig_ok = raw.len() > 65 && {
        use ed25519_dalek::Verifier;
        let sig = ed25519_dalek::Signature::from_bytes(raw[1..65].try_into().unwrap());
        ed25519_dalek::VerifyingKey::from_bytes(&w.signer).is_ok_and(|vk| vk.verify(&raw[65..], &sig).is_ok())
    };
    put("signature_verifies", sig_ok, json!(b58(&w.signer)));
    put("payer_is_wallet", tx.keys.first() == Some(&w.payer), json!(tx.keys.first().map(b58)));
    put("size", raw.len() <= build::MAX_TX_BYTES, json!({ "bytes": raw.len(), "max": build::MAX_TX_BYTES }));
    let all = tx.resolve(|t| w.alts.get(t).cloned());
    let locks = all.as_ref().map_or(0, |a| a.len());
    put("accounts_resolve", all.is_some(), json!({ "static": tx.keys.len(), "loaded": locks.saturating_sub(tx.keys.len()), "lookups": tx.lookups.len() }));
    put("locks", locks <= build::MAX_LOCKS, json!({ "accounts": locks, "max": build::MAX_LOCKS }));
    let bh_ok = raw.len() >= 65 + 4 + 32 * tx.keys.len() + 32 && {
        // the message: header (4 incl. the version byte), compact key count (1 byte below 128 keys), the keys, the blockhash
        let at = 65 + 4 + 1 + 32 * tx.keys.len();
        raw.get(at..at + 32) == Some(&w.blockhash[..])
    };
    put("blockhash", bh_ok, json!(b58(&w.blockhash)));
    put("cu_limit", tx.cu_limit == Some(w.cu_limit as u32), json!({ "tx": tx.cu_limit, "want": w.cu_limit }));
    put("no_cu_price", tx.cu_price_micro.unwrap_or(0) == 0, json!(tx.cu_price_micro));
    // the tip as signed: the last instruction, a System transfer (2) from the payer
    let signed_tip = tx.ixs.last().filter(|ix| tx.keys.get(ix.program as usize) == Some(&[0u8; 32]) && ix.data.len() == 12 && ix.data[..4] == [2, 0, 0, 0])
        .and_then(|ix| Some((*tx.keys.get(*ix.accounts.first()? as usize)?, *tx.keys.get(*ix.accounts.get(1)? as usize)?, u64::from_le_bytes(ix.data[4..12].try_into().unwrap()))));
    let last_is_tip = signed_tip.is_some_and(|(from, to, lamports)| from == w.payer && w.tip == Some((to, lamports)));
    let tip_ok = w.tip.is_none() || last_is_tip;
    // (what was signed is spelled out only when it is not what was wanted: the dry run's decisions stay cheap)
    put("tip_last", tip_ok, json!({ "account": w.tip.map(|t| b58(&t.0)), "lamports": w.tip.map(|t| t.1),
        "signed": if tip_ok { Value::Null } else { json!(signed_tip.map(|(f, t, l)| json!({ "from": b58(&f), "to": b58(&t), "lamports": l }))) } }));
    let paid = send::tip_paid(&tx, &w.tips);
    put("tip_to_jito", w.tip.map_or(true, |t| paid == t.1 && w.tips.contains(&t.0)), json!({ "paid": paid }));
    put("tip_check", send::verify_copy(raw, SendKind::JitoBundle, &w.tips, "jito-bundle").is_ok(), Value::Null);
    let route = tx.ixs.iter().any(|ix| tx.keys.get(ix.program as usize) == Some(&w.program));
    put("route_program", route, json!(b58(&w.program)));
    let has = |p: &Pk| all.as_ref().is_some_and(|a| a.contains(p));
    put("pools_named", has(&w.pools[0]) && has(&w.pools[1]), json!([b58(&w.pools[0]), b58(&w.pools[1])]));
    // the route instruction, decoded from the signed bytes (review WP-05 #12)
    let seen = all.as_ref().and_then(|a| route_of(&tx, a, &w.program));
    put("route_data", seen.as_ref().is_some_and(|r| r.legs.len() == 2), json!(seen.as_ref().map(|r| json!({ "legs": r.legs.len() }))));
    let r = seen.as_ref();
    put("route_amount_in", r.is_some_and(|r| r.amount_in == w.amount_in), json!({ "signed": r.map(|r| r.amount_in), "want": w.amount_in }));
    put("route_min_profit", r.is_some_and(|r| r.min_profit == w.min_profit), json!({ "signed": r.map(|r| r.min_profit), "want": w.min_profit }));
    // a landed bundle cannot lose: what the program demands back covers everything the transaction pays out (every
    // System transfer from the payer: the tip) plus the base fee and the margin floor
    let paid_out: u64 = tx.ixs.iter().filter(|ix| tx.keys.get(ix.program as usize) == Some(&[0u8; 32]) && ix.data.len() == 12 && ix.data[..4] == [2, 0, 0, 0])
        .filter(|ix| ix.accounts.first().and_then(|&i| tx.keys.get(i as usize)) == Some(&w.payer))
        .map(|ix| u64::from_le_bytes(ix.data[4..12].try_into().unwrap())).sum();
    let floor = paid_out.saturating_add(BASE_FEE).saturating_add(w.margin_floor);
    put("min_profit_covers_tip", r.is_some_and(|r| r.min_profit >= floor), json!({ "signed_min_profit": r.map(|r| r.min_profit), "signed_paid_out": paid_out,
        "base_fee": BASE_FEE, "margin_floor": w.margin_floor }));
    let legs_ok = r.is_some_and(|r| r.authority == w.payer && r.quote == w.quote && r.legs.len() == 2
        && r.legs[0].out == w.mid && r.legs[1].out == w.quote
        && r.legs.iter().zip(&w.leg_programs).all(|(l, p)| l.program == *p)
        && r.legs.iter().zip(&w.pools).all(|(l, p)| l.accounts.contains(p)));
    put("route_accounts", legs_ok, if legs_ok { json!({ "legs": 2 }) } else { json!(r.map(|r| json!({ "authority": b58(&r.authority), "quote": b58(&r.quote),
        "legs": r.legs.iter().map(|l| json!({ "out": b58(&l.out), "program": b58(&l.program), "accounts": l.accounts.len() })).collect::<Vec<_>>() }))) });
    out
}

/// a signed transaction's accounts, in order, with how each is named (static or through a lookup table) and whether it
/// signs or is written (the dry run's record)
pub fn accounts_of(raw: &[u8], alts: &HashMap<Pk, Arc<Vec<Pk>>>) -> Value {
    let Some((tx, _)) = crate::tx::parse_wire(raw) else { return Value::Null };
    let Some(all) = tx.resolve(|t| alts.get(t).cloned()) else { return Value::Null };
    let n = tx.keys.len();
    let sig = tx.num_signers as usize;
    json!(all.iter().enumerate().map(|(i, k)| json!({ "key": b58(k), "signer": i < sig, "writable": tx.is_writable(i), "via": if i < n { json!("static") } else {
        // which table it was loaded from
        json!(tx.lookups.iter().find(|l| alts.get(&l.table).is_some_and(|a| l.writable.iter().chain(&l.readonly).any(|&j| a.get(j as usize) == Some(k)))).map(|l| b58(&l.table)))
    } })).collect::<Vec<_>>())
}

#[cfg(test)]
mod tests;
