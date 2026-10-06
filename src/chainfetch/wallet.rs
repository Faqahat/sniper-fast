//! Our wallet's every landed transaction (PLAN WP-03b item 1; MEASUREMENT §4.15). A signature of ours comes from any
//! of four sources (`found_by`):
//! - (a) `account_update`: the `txn` of a wallet or wallet-token-account update on the state stream (every landed
//!   transaction we pay for writes the wallet, failed ones too: the fee is charged);
//! - (b) `ours`: our attempts' signatures, once fired (`chainfetch::note_fired`);
//! - (c) `jito_processed`: Jito `processed` results (`chainfetch::note_jito_processed`; the send side is WP-05's);
//! - (d) `sigs_for_address`: `getSignaturesForAddress(wallet)` over the last hour, every `sigs_every_s` (hourly). FT-000
//!   (S1-12): only the rows of the last hour are taken (the first page used to bring the wallet's whole history: 748
//!   transactions back to five days before, 749 Shyft calls at every segment start), and a segment lists only what is
//!   newer than the previous segment's cursor (`until`): the newest signature it recorded with nothing older still
//!   pending ([`Wallet::cursor`], `wallet-cursor.json` in its run directory, `[chainfetch] wallet_cursor`).
//!
//! (a) and (d) show the signature landed: it is fetched at once. Most of (b) never lands (Jito drops a losing bundle),
//! so a signature known only from (b) or (c) is watched instead: batched `getSignatureStatuses` (up to 256 a call, one
//! call every 2 s while any is watched), and fetched only once a status shows it landed or (a) / (d) names it. A watched
//! signature with no status 90 s after it was found, or (WP-05) once the chain is 16 slots past its attempt's target
//! slot, never landed (`unlanded`, counted). The rate is a call every 2 s
//! while attempts are in flight plus one fetch per landed transaction, against the 22 fetches per attempt of fetching
//! every signature blind (review WP-03b #2).
//!
//! Each landed signature is fetched once with a bounded `getTransaction` (2 s deadline; at most 4 in flight), retried
//! after 1 s, 5 s and 30 s (then every 30 s) while nothing is found, and given up 10 minutes after it was found
//! (txfetch.jsonl `not_found`); a later (a) makes a waiting retry due at once (review WP-03b #20). The result goes to
//! wallet.jsonl and to the engine (INPUT `wallet_tx`). A signature found by (d) but never by (a), once a minute has
//! passed (the update may lag), is an events.jsonl `wallet_update_missing`: it tests the assumption that failed landings
//! write the wallet account; (b)-(d) cover the case where it does not hold.
use super::txjson::RpcTx;
use crate::feeds::grpc::{PbInnerIx, PbIx};
use crate::tx::Pk;
use serde_json::{json, Map, Value};
use std::collections::{BTreeSet, HashMap, VecDeque};

/// `found_by` bits (exec.jsonl / wallet.jsonl `found_by`, in this order)
pub const F_ACCOUNT: u8 = 1;
pub const F_SHRED: u8 = 2;
pub const F_STREAM: u8 = 4;
pub const F_OURS: u8 = 8;
pub const F_JITO: u8 = 16;
pub const F_SIGS: u8 = 32;
pub const F_SAMPLE: u8 = 64;
/// WP-07: the executor's status check found the signature landed before its record came (`chainfetch::note_landed`:
/// the record settles the executor's provisional money), or the ledger's reconciliation found it in the window
pub const F_EXEC: u8 = 128;
/// the sources that show a signature landed: a wallet-account write (a), getSignaturesForAddress (d), the executor's
/// status check or the reconciliation's search (WP-07)
pub const LANDED_BITS: u8 = F_ACCOUNT | F_SIGS | F_EXEC;

pub fn found_by(bits: u8) -> Vec<&'static str> {
    [(F_ACCOUNT, "account_update"), (F_SHRED, "shred"), (F_STREAM, "tx_stream"), (F_OURS, "ours"), (F_JITO, "jito_processed"), (F_SIGS, "sigs_for_address"),
        (F_SAMPLE, "block_sample"), (F_EXEC, "executor_status")].iter().filter(|(b, _)| bits & b != 0).map(|(_, n)| *n).collect()
}

/// a wallet signature's fetch is given up this long after it was found
pub const GIVE_UP_NS: u64 = 600_000_000_000;
/// how long a signature found by `sigs_for_address` waits for its account update before it is `wallet_update_missing`
pub const MISSING_GRACE_NS: u64 = 60_000_000_000;
/// a signature known only from our attempt (b) or Jito (c) is watched this long for a status (a bundle that did not
/// land within it never will: Jito forwards it to the leaders of a few slots)
pub const WATCH_NS: u64 = 90_000_000_000;
/// WP-05: an attempt's signatures are watched until the chain is this many slots past the attempt's target slot (four
/// leader windows: a bundle lands in its leader's slots or not at all; a later landing still comes by (a), and the
/// executor checks once more when the blockhash expires), within the 90 s above
pub const WATCH_SLOTS_AFTER_TARGET: u64 = 16;
/// at most this many signatures in one getSignatureStatuses call (the RPC's limit is 256)
pub const STATUS_BATCH: usize = 256;
/// signatures are remembered this long (a later source of one already fetched only adds to its `found_by`)
const KEEP_NS: u64 = 7_200_000_000_000;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum State {
    /// known only from (b) / (c): its status is polled
    Watch,
    Due,
    InFlight,
    Done,
    GaveUp,
    /// watched for `WATCH_NS` with no status: it never landed
    Unlanded,
}

#[derive(Clone, Debug)]
pub struct WSig {
    pub found_by: u8,
    /// monotonic ns when first found
    pub first: u64,
    pub slot: Option<u64>,
    pub attempt: Option<u64>,
    pub tries: u32,
    pub state: State,
    /// when its fetch is due (its entry in the due set)
    due_at: Option<u64>,
    /// monotonic ns when it was known to have landed (the wallet coverage's start)
    pub landed: Option<u64>,
    /// monotonic ns of its wallet.jsonl record
    pub recorded: Option<u64>,
    /// the block index its record was written with (None: an `idx_update` follows from the slot index)
    pub idx: Option<u64>,
    /// its record also went to exec.jsonl (the idx update goes there too)
    pub in_exec: bool,
    /// WP-05: watched no longer once the chain passes this slot (an attempt's target slot + `WATCH_SLOTS_AFTER_TARGET`)
    pub watch_until_slot: Option<u64>,
}

pub struct Wallet {
    pub wallet: Pk,
    pub wsol: Pk,
    pub route: Pk,
    sigs: HashMap<[u8; 64], WSig>,
    order: VecDeque<(u64, [u8; 64])>,
    due: BTreeSet<(u64, [u8; 64])>,
    /// the watched signatures, oldest first (entries of signatures no longer watched are skipped)
    watch: VecDeque<(u64, [u8; 64])>,
    /// the state stream's first slot: (d)'s signatures before it cannot have had an update in this run
    pub stream_first_slot: Option<u64>,
    /// FT-000 (S1-12): the previous segment's cursor: (d) lists only signatures newer than it (`until`)
    pub until: Option<String>,
    missing_checks: VecDeque<(u64, [u8; 64])>,
    pub fetched_total: u64,
    pub gave_up_total: u64,
    pub missing_total: u64,
    /// watched signatures that never showed a status (of them, those that passed their target slot: WP-05), and those
    /// whose status showed they landed
    pub unlanded_total: u64,
    pub unlanded_by_slot_total: u64,
    pub landed_by_status_total: u64,
    /// FT-000 (S1-12): (d)'s rows older than its hour, not taken
    pub older_rows_total: u64,
    /// coverage (`wallet_with_tx_pct`): landed signatures whose minute has passed, and those recorded within it
    cov_q: VecDeque<(u64, [u8; 64])>,
    pub cov_n_total: u64,
    pub cov_with_total: u64,
}

impl Wallet {
    pub fn new(wallet: Pk, wsol: Pk, route: Pk) -> Wallet {
        Wallet { wallet, wsol, route, sigs: HashMap::new(), order: VecDeque::new(), due: BTreeSet::new(), watch: VecDeque::new(), stream_first_slot: None, until: None,
            missing_checks: VecDeque::new(), fetched_total: 0, gave_up_total: 0, missing_total: 0, unlanded_total: 0, unlanded_by_slot_total: 0, landed_by_status_total: 0,
            older_rows_total: 0,
            cov_q: VecDeque::new(), cov_n_total: 0, cov_with_total: 0 }
    }

    pub fn get(&self, sig: &[u8; 64]) -> Option<&WSig> { self.sigs.get(sig) }
    pub fn get_mut(&mut self, sig: &[u8; 64]) -> Option<&mut WSig> { self.sigs.get_mut(sig) }
    /// signatures to fetch or being fetched
    pub fn pending_now(&self) -> usize { self.sigs.values().filter(|s| matches!(s.state, State::Due | State::InFlight)).count() }
    /// signatures watched for a status
    pub fn watching(&self) -> usize { self.watch.iter().filter(|(_, sig)| self.sigs.get(sig).is_some_and(|s| s.state == State::Watch)).count() }
    /// how many signatures the wallet remembers
    pub fn len(&self) -> usize { self.sigs.len() }
    pub fn is_empty(&self) -> bool { self.sigs.is_empty() }

    /// `sig`'s fetch is due at `at` (any earlier schedule replaced)
    fn schedule(&mut self, sig: [u8; 64], at: u64) {
        let Some(s) = self.sigs.get_mut(&sig) else { return };
        if let Some(old) = s.due_at.take() { self.due.remove(&(old, sig)); }
        s.state = State::Due;
        s.due_at = Some(at);
        self.due.insert((at, sig));
    }

    /// `sig` is known to have landed: it enters the wallet coverage
    fn landed(&mut self, sig: [u8; 64], now: u64) {
        let Some(s) = self.sigs.get_mut(&sig) else { return };
        if s.landed.is_none() { s.landed = Some(now); self.cov_q.push_back((now, sig)); }
    }

    /// A source named `sig` (`bit`: F_*). True when it is new. A landing source (a, d) makes its fetch due at once (a
    /// watched one too; an (a) also cuts a retry's wait short); (b) and (c) only watch it
    pub fn found(&mut self, sig: [u8; 64], bit: u8, slot: Option<u64>, attempt: Option<u64>, now: u64) -> bool {
        let lands = bit & LANDED_BITS != 0;
        if let Some(s) = self.sigs.get_mut(&sig) {
            s.found_by |= bit;
            if s.slot.is_none() { s.slot = slot; }
            if s.attempt.is_none() { s.attempt = attempt; }
            let (state, due_at) = (s.state, s.due_at);
            if lands {
                match state {
                    State::Watch | State::Unlanded => { self.landed(sig, now); self.schedule(sig, now); }
                    State::Due if bit == F_ACCOUNT && due_at.is_some_and(|t| t > now) => self.schedule(sig, now),
                    // WP-07: the executor saw it landed: one more fetch of a signature given up (its record settles the
                    // executor's provisional money)
                    State::GaveUp if bit == F_EXEC => self.schedule(sig, now),
                    _ => {}
                }
            }
            return false;
        }
        self.sigs.insert(sig, WSig { found_by: bit, first: now, slot, attempt, tries: 0, state: State::Watch, due_at: None, landed: None, recorded: None, idx: None,
            in_exec: false, watch_until_slot: None });
        self.order.push_back((now, sig));
        if lands { self.landed(sig, now); self.schedule(sig, now); } else { self.watch.push_back((now, sig)); }
        if bit == F_SIGS { self.missing_checks.push_back((now + MISSING_GRACE_NS, sig)); }
        true
    }

    /// WP-05: watch `sig` (one of our attempts') only until the chain passes `slot`
    pub fn watch_until(&mut self, sig: &[u8; 64], slot: u64) {
        if let Some(s) = self.sigs.get_mut(sig) { s.watch_until_slot = Some(s.watch_until_slot.map_or(slot, |x| x.max(slot))); }
    }

    /// at most `max` signatures to fetch now
    pub fn take_due(&mut self, now: u64, max: usize) -> Vec<[u8; 64]> {
        let mut out = Vec::new();
        while out.len() < max {
            let Some(&(t, sig)) = self.due.iter().next() else { break };
            if t > now { break; }
            self.due.remove(&(t, sig));
            if let Some(s) = self.sigs.get_mut(&sig) {
                if s.state == State::Due && s.due_at == Some(t) { s.state = State::InFlight; s.due_at = None; out.push(sig); }
            }
        }
        out
    }

    /// The fetch of `sig` ended: `Some(idx)` recorded (with its block index, if known), or nothing found / failed. False
    /// when it was given up (10 minutes after it was found)
    pub fn done(&mut self, sig: &[u8; 64], recorded: Option<Option<u64>>, in_exec: bool, now: u64) -> bool {
        let Some(s) = self.sigs.get_mut(sig) else { return true };
        match recorded {
            Some(idx) => { s.state = State::Done; s.recorded = Some(now); s.idx = idx; s.in_exec = in_exec; self.fetched_total += 1; true }
            None if now.saturating_sub(s.first) >= GIVE_UP_NS => { s.state = State::GaveUp; self.gave_up_total += 1; false }
            None => {
                let wait = match s.tries { 0 => 1_000_000_000, 1 => 5_000_000_000, _ => 30_000_000_000 };
                s.tries += 1;
                self.schedule(*sig, now + wait);
                true
            }
        }
    }

    /// FT-000 (S1-12): this segment's cursor for the next one: (slot, signature) of the newest transaction it recorded
    /// with no landed signature of an older or equal slot still waiting for its fetch (one still pending when the segment
    /// stops is newer than the cursor, so the next segment lists and fetches it). None: nothing recorded yet
    pub fn cursor(&self) -> Option<(u64, [u8; 64])> {
        let pending = self.sigs.values().filter(|s| matches!(s.state, State::Due | State::InFlight)).filter_map(|s| s.slot).min();
        self.sigs.iter().filter(|(_, s)| s.state == State::Done && s.recorded.is_some()).filter_map(|(k, s)| s.slot.map(|sl| (sl, *k)))
            .filter(|(sl, _)| pending.is_none_or(|p| *sl < p)).max()
    }

    /// The fetch of `sig` was refused for want of a token (nothing was sent): due again shortly, its tries unchanged
    pub fn refused(&mut self, sig: &[u8; 64], now: u64) { if self.sigs.contains_key(sig) { self.schedule(*sig, now + 250_000_000); } }

    /// up to `max` watched signatures for a getSignatureStatuses call, the oldest first
    pub fn watch_batch(&self, max: usize) -> Vec<[u8; 64]> {
        self.watch.iter().filter(|(_, sig)| self.sigs.get(sig).is_some_and(|s| s.state == State::Watch)).take(max).map(|x| x.1).collect()
    }

    /// A getSignatureStatuses answer (`value`: one entry per signature of `sigs`, null when unknown): a watched signature
    /// with a status landed (failed ones too: the fee was charged), and its fetch is due now. Returns how many landed
    pub fn on_statuses(&mut self, sigs: &[[u8; 64]], value: &Value, now: u64) -> usize {
        let Some(list) = value.as_array() else { return 0 };
        let mut n = 0;
        for (sig, v) in sigs.iter().zip(list) {
            if v.is_null() { continue; }
            let Some(s) = self.sigs.get_mut(sig) else { continue };
            if s.state != State::Watch { continue; }
            if s.slot.is_none() { s.slot = v["slot"].as_u64(); }
            self.landed(*sig, now);
            self.schedule(*sig, now);
            self.landed_by_status_total += 1;
            n += 1;
        }
        n
    }

    /// A `getSignaturesForAddress` page (`result`: [{signature, slot, err, blockTime, ...}], newest first): the new
    /// signatures, the cursor for the next page (`before`), and whether that page is needed (the page is full and its
    /// oldest entry is newer than `since_unix`). FT-000 (S1-12): a row older than `since_unix` is not taken (an hour's
    /// window; a row without a block time is)
    pub fn sigs_page(&mut self, page: &Value, since_unix: i64, now: u64) -> (Vec<[u8; 64]>, Option<String>, bool) {
        let rows = page.as_array().map(|a| a.as_slice()).unwrap_or(&[]);
        let mut new = Vec::new();
        for r in rows {
            if r["blockTime"].as_i64().is_some_and(|t| t < since_unix) { self.older_rows_total += 1; continue; }
            let Some(sig) = r["signature"].as_str().and_then(|s| bs58::decode(s).into_vec().ok()).and_then(|v| <[u8; 64]>::try_from(v).ok()) else { continue };
            if self.found(sig, F_SIGS, r["slot"].as_u64(), None, now) { new.push(sig); }
        }
        let last = rows.last();
        let more = rows.len() >= 1_000 && last.and_then(|r| r["blockTime"].as_i64()).is_some_and(|t| t > since_unix);
        (new, last.and_then(|r| r["signature"].as_str()).map(String::from), more)
    }

    /// Signatures found by `sigs_for_address` that their minute later still have no account update: (sig, slot).
    /// Those before the state stream's first slot are not counted (no update could have reached this run)
    pub fn missing_due(&mut self, now: u64) -> Vec<([u8; 64], Option<u64>, u8)> {
        let mut out = Vec::new();
        while let Some(&(t, sig)) = self.missing_checks.front() {
            if t > now { break; }
            self.missing_checks.pop_front();
            let Some(s) = self.sigs.get(&sig) else { continue };
            let in_run = match (s.slot, self.stream_first_slot) { (Some(a), Some(b)) => a >= b, _ => false };
            if s.found_by & F_ACCOUNT == 0 && in_run { self.missing_total += 1; out.push((sig, s.slot, s.found_by)); }
        }
        out
    }

    /// Once a second, `tip_slot` the chain's newest slot (0: unknown): watched signatures without a status for
    /// `WATCH_NS`, or whose attempt's target slot the chain has passed by `WATCH_SLOTS_AFTER_TARGET` (WP-05), never
    /// landed; coverage (landed signatures whose minute has passed, recorded within it or not); old signatures forgotten
    pub fn evaluate(&mut self, now: u64, tip_slot: u64) {
        let mut keep = VecDeque::with_capacity(self.watch.len());
        while let Some((t, sig)) = self.watch.pop_front() {
            let Some(s) = self.sigs.get_mut(&sig).filter(|s| s.state == State::Watch) else { continue };
            let by_slot = tip_slot > 0 && s.watch_until_slot.is_some_and(|u| tip_slot > u);
            if by_slot || now.saturating_sub(t) >= WATCH_NS {
                s.state = State::Unlanded;
                self.unlanded_total += 1;
                if by_slot { self.unlanded_by_slot_total += 1; }
            } else { keep.push_back((t, sig)); }
        }
        self.watch = keep;
        while let Some(&(t, sig)) = self.cov_q.front() {
            if now.saturating_sub(t) < 60_000_000_000 { break; }
            self.cov_q.pop_front();
            self.cov_n_total += 1;
            if self.sigs.get(&sig).and_then(|s| s.recorded).is_some_and(|r| r.saturating_sub(t) <= 60_000_000_000) { self.cov_with_total += 1; }
        }
        while let Some(&(t, sig)) = self.order.front() {
            if now.saturating_sub(t) < KEEP_NS { break; }
            self.order.pop_front();
            match self.sigs.get(&sig) {
                // still being fetched or watched (never past 10 minutes, in practice): looked at again later
                Some(s) if matches!(s.state, State::Due | State::InFlight | State::Watch) => self.order.push_back((now, sig)),
                Some(s) if now.saturating_sub(s.first) >= KEEP_NS => { self.sigs.remove(&sig); }
                _ => {}
            }
        }
    }
}

/// wallet.jsonl's own fields (MEASUREMENT §4.15)
#[derive(Clone, Debug, PartialEq)]
pub struct Fields { pub wallet_kind: &'static str, pub wallet_sol: Option<i64>, pub wallet_tok: Map<String, Value>, pub created: Vec<Value>, pub closed: Vec<Value> }

const SYSTEM: Pk = [0u8; 32];

/// every instruction, top-level then inner: (program, account keys, data)
pub(crate) fn all_ixs<'a>(x: &'a RpcTx) -> Vec<(Pk, Vec<Pk>, &'a [u8])> {
    let msg = x.tx.message.as_ref();
    let k = |i: u32| x.keys.get(i as usize).copied();
    let mut out = Vec::new();
    let top: Vec<&PbIx> = msg.map(|m| m.instructions.iter().collect()).unwrap_or_default();
    for ix in top { if let Some(p) = k(ix.program_id_index) { out.push((p, ix.accounts.iter().filter_map(|a| k(*a as u32)).collect(), &ix.data[..])); } }
    for g in x.meta.as_ref().map(|m| m.inner_instructions.as_slice()).unwrap_or(&[]) {
        let list: Vec<&PbInnerIx> = g.instructions.iter().collect();
        for ix in list { if let Some(p) = k(ix.program_id_index) { out.push((p, ix.accounts.iter().filter_map(|a| k(*a as u32)).collect(), &ix.data[..])); } }
    }
    out
}

fn u32_at(d: &[u8], i: usize) -> Option<u32> { d.get(i..i + 4).map(|b| u32::from_le_bytes(b.try_into().unwrap())) }
fn u64_at(d: &[u8], i: usize) -> Option<u64> { d.get(i..i + 8).map(|b| u64::from_le_bytes(b.try_into().unwrap())) }

/// The wallet's view of one transaction: its kind, its lamport and token changes, the accounts it created (funded by
/// the wallet: it pays) and closed. Kinds, in this order: `route` (a top-level instruction of the route program), `nonce`
/// (a System nonce instruction other than AdvanceNonce: initialize, withdraw, authorize, upgrade), `wrap` (SyncNative on
/// the wallet's WSOL account), `unwrap` (CloseAccount of it), `close` (CloseAccount of another of its token accounts),
/// `ata_create` (an associated-token-account create for the wallet), `transfer_in` (another payer, and the wallet's
/// lamports rose), `transfer_out` (a System transfer from the wallet), `other`
pub fn fields(x: &RpcTx, wallet: &Pk, wsol: &Pk, route: &Pk) -> Fields {
    let meta = x.meta.as_ref();
    let wi = x.keys.iter().position(|k| k == wallet);
    let bal = |v: Option<&Vec<u64>>, i: usize| v.and_then(|b| b.get(i)).copied();
    let wallet_sol = wi.and_then(|i| Some(bal(meta.map(|m| &m.post_balances), i)? as i64 - bal(meta.map(|m| &m.pre_balances), i)? as i64));
    let payer_is_wallet = x.keys.first() == Some(wallet);
    // token changes of the wallet's own token accounts, by mint (an account absent on one side counts as 0)
    let w58 = bs58::encode(wallet).into_string();
    let mut tok: std::collections::BTreeMap<String, i128> = Default::default();
    if let Some(m) = meta {
        for (side, list) in [(-1i128, &m.pre_token_balances), (1, &m.post_token_balances)] {
            for b in list.iter().filter(|b| b.owner == w58) {
                *tok.entry(b.mint.clone()).or_default() += side * b.ui_token_amount.as_ref().and_then(|u| u.amount.parse::<i128>().ok()).unwrap_or(0);
            }
        }
    }
    let wallet_tok: Map<String, Value> = tok.into_iter().filter(|(_, v)| *v != 0).map(|(k, v)| (k, json!(v.to_string()))).collect();
    let ixs = all_ixs(x);
    let top_n = x.tx.message.as_ref().map_or(0, |m| m.instructions.len());
    let (top, _) = ixs.split_at(top_n.min(ixs.len()));
    let tokp = |p: &Pk| *p == *crate::pda::TOKEN_PROGRAM || *p == *crate::pda::TOKEN_2022;
    let sys_tag = |d: &[u8]| u32_at(d, 0);
    let kind = if top.iter().any(|(p, _, _)| p == route) { "route" }
        else if ixs.iter().any(|(p, _, d)| *p == SYSTEM && matches!(sys_tag(d), Some(5 | 6 | 7 | 12))) { "nonce" }
        else if top.iter().any(|(p, a, d)| tokp(p) && d.first() == Some(&17) && a.first() == Some(wsol)) { "wrap" }
        else if top.iter().any(|(p, a, d)| tokp(p) && d.first() == Some(&9) && a.first() == Some(wsol)) { "unwrap" }
        else if top.iter().any(|(p, a, d)| tokp(p) && d.first() == Some(&9) && a.get(2) == Some(wallet)) { "close" }
        else if top.iter().any(|(p, a, d)| *p == *crate::pda::ATA_PROGRAM && d.first().is_none_or(|t| *t <= 1) && a.get(2) == Some(wallet)) { "ata_create" }
        else if !payer_is_wallet && wallet_sol.is_some_and(|s| s > 0) { "transfer_in" }
        else if payer_is_wallet && top.iter().any(|(p, a, d)| *p == SYSTEM && sys_tag(d) == Some(2) && a.first() == Some(wallet) && a.get(1).is_some_and(|t| t != wallet)) { "transfer_out" }
        else { "other" };
    // accounts created (pre 0, post > 0) and closed (pre > 0, post 0) in a transaction the wallet pays for: lamports, the
    // owner and space a System CreateAccount (or WithSeed) gave them, where a closing CloseAccount sent the lamports
    let (mut created, mut closed) = (Vec::new(), Vec::new());
    if let (Some(m), true) = (meta, payer_is_wallet) {
        let create_of = |k: &Pk| -> (Option<String>, Option<u64>) {
            for (p, a, d) in &ixs {
                if *p != SYSTEM { continue; }
                match sys_tag(d) {
                    Some(0) if a.get(1) == Some(k) => return (d.get(20..52).map(|o| bs58::encode(o).into_string()), u64_at(d, 12)),
                    Some(3) if a.get(1) == Some(k) => {
                        // u32 3 | base (32) | seed (u64 length + bytes) | lamports u64 | space u64 | owner (32)
                        let n = u64_at(d, 36).unwrap_or(0) as usize;
                        let at = 44 + n;
                        return (d.get(at + 16..at + 48).map(|o| bs58::encode(o).into_string()), u64_at(d, at + 8));
                    }
                    _ => {}
                }
            }
            (None, None)
        };
        for (i, k) in x.keys.iter().enumerate() {
            if k == wallet { continue; }
            let (pre, post) = (m.pre_balances.get(i).copied().unwrap_or(0), m.post_balances.get(i).copied().unwrap_or(0));
            if pre == 0 && post > 0 {
                let (owner, space) = create_of(k);
                created.push(json!({ "acct": bs58::encode(k).into_string(), "lamports": post, "owner": owner, "space": space }));
            } else if pre > 0 && post == 0 {
                let to = ixs.iter().find(|(p, a, d)| tokp(p) && d.first() == Some(&9) && a.first() == Some(k)).and_then(|(_, a, _)| a.get(1)).map(|t| bs58::encode(t).into_string());
                closed.push(json!({ "acct": bs58::encode(k).into_string(), "lamports": pre, "to": to }));
            }
        }
    }
    Fields { wallet_kind: kind, wallet_sol, wallet_tok, created, closed }
}
