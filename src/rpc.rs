//! Minimal JSON-RPC client (off the hot path): account snapshots at boot, lookup tables, slot/blockhash, signature
//! statuses and transaction simulation.
//!
//! WP-02 (runtime split): `Rpc::bind` ties a client to the background runtime: every call is spawned there, whichever
//! runtime awaits it, and replies over `runtime::LARGE_REPLY` bytes are parsed in `spawn_blocking`. The HTTP work
//! checks it is not on an `arbx-hot` thread (`runtime::check_not_hot`).
//!
//! WP-03b (PLAN WP-03b item 5; PLAN-ADDENDUM I-1, F29):
//! - **Roles.** Every client has a [`Role`] (`boot`, `exec`, `backfill`, `wallet`, `slotidx`, `blockhash`, ...): stats
//!   aggregate per (role, provider) in one [`Registry`] (resources.jsonl `rpc`, status.jsonl `chainfetch.by_role`),
//!   instead of the fresh, invisible `Stats` every `only` client had.
//! - **Token buckets per provider** ([`Limiter`]), shared by every role and client of the process: a provider's
//!   `max_rps` (Haan answered 429 at about 5 requests/s) is never exceeded by the bot as a whole. Roles have one of four
//!   priorities ([`Role::priority`]): critical (boot, snapshot, exec, settle) may take the bucket's last token, normal
//!   (engine, leaders, provenance, wallet) keeps a quarter of the burst for them, index (slot index, coverage sample,
//!   blockhash poll) and bulk (backfill, warm-up, tools) keep half. Callers that must wait queue in the bucket by
//!   priority, then first come first served: a waiting caller is never overtaken by a later or lower one, so the slot
//!   index is served before the backfill on a provider they share (review WP-03b #1). A 429 cools the provider down
//!   (backoff, bucket drained, no tokens accrue while it cools).
//! - **Errors are classified** ([`ErrClass`]): rate_limited, timeout, body (a reply cut or garbled while it was read:
//!   cmp2's Shyft HTTP/2 "error decoding response body"), http, transport, rpc (a JSON-RPC error answer), no_result.
//! - **`call_bounded`** (deadline, retries): tries the providers in order, moving on at once after a retryable failure,
//!   with backoff between rounds; used by every chain-fetch component (and later by settlement). A JSON-RPC error that
//!   states a chain fact (a skipped slot, an unsupported transaction version) ends the call at once; any other error
//!   answer may be the provider's own (a plan without the method, its own parameter limit, a node behind), so the
//!   call asks the providers that have not answered yet and fails only when every one has.
//! - **The boot policy** ([`Phase::Boot`]): while the run boots (pools, the account snapshot, the route-program check,
//!   `Exec::new`), every call of every client made from the run's root client is a bounded call that retries with
//!   backoff across the providers for `[chainfetch] boot_retry_s`; only a sustained failure, or the same kind of refusal
//!   from every provider, aborts the boot (stop.json reason `error`, detail `... sustained RPC failure ...`; events.jsonl
//!   `rpc_boot_failed`). Background tasks started during the boot take their own phase (`with_own_phase`).
//! - **Accounting** (resources.jsonl `rpc`): `calls` are HTTP requests sent; a refusal for want of a token sends none and
//!   is counted only as `rate_budget`; `throttled` counts the requests that waited for their token.
//! - **Pre-resolved DNS and warm connections**: the client resolves each provider's host once ([`CachedDns`], refreshed
//!   in the background), so a reconnect never waits on a DNS lookup (35 ms of Haan's 53 ms cold connect); HTTP/2 and TCP
//!   keep-alives, and a cheap call to any provider idle for 20 s (`start_warm`), keep the connections warm.
use crate::tx::{b58, Pk};
use anyhow::{Context, Result};
use base64::Engine as _;
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap, VecDeque};
use std::net::SocketAddr;
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicU8, Ordering::Relaxed};
use std::sync::{Arc, LazyLock, Mutex, OnceLock, RwLock};
use std::time::Duration;
use tokio::time::Instant;

/// One RPC provider. `bearer` is sent as `Authorization: Bearer <value>` (Haan); keys in the URL need nothing.
#[derive(Debug, Clone)]
pub struct Endpoint { pub name: String, pub url: String, pub bearer: Option<String> }

/// Per-provider results: every call goes to every provider at once, the first good answer is used, and every
/// provider's own latency is still recorded (so each call measures all of them).
#[derive(Default)]
pub struct Stats {
    /// (provider, method) -> latencies (µs) of successful answers
    pub lat: std::collections::BTreeMap<(String, String), Vec<u64>>,
    pub wins: std::collections::BTreeMap<String, u64>,
    pub errors: std::collections::BTreeMap<String, u64>,
    /// (provider, reason) -> count; reasons have URLs cut to their host so no key is ever logged
    pub why: std::collections::BTreeMap<(String, String), u64>,
    pub calls: u64,
}

/// An error message with every URL reduced to scheme://host (provider keys live in paths and query strings).
pub fn scrub(msg: &str) -> String {
    let mut out = String::with_capacity(msg.len());
    let mut rest = msg;
    while let Some(i) = rest.find("http") {
        out.push_str(&rest[..i]);
        let url = &rest[i..];
        let end = url.find(|c: char| c.is_whitespace() || c == ')' || c == '"' || c == '\'').unwrap_or(url.len());
        let u = &url[..end];
        let host_end = u.find("://").map(|p| p + 3).and_then(|p| u[p..].find(|c| c == '/' || c == '?').map(|q| p + q)).unwrap_or(u.len());
        out.push_str(&u[..host_end]);
        rest = &url[end..];
    }
    out.push_str(rest);
    // anything still looking like a key parameter
    for k in ["api-key=", "api_key=", "apikey=", "token="] {
        while let Some(i) = out.find(k) { let j = out[i..].find(|c: char| c == '&' || c.is_whitespace()).map_or(out.len(), |x| i + x); out.replace_range(i + k.len()..j, "…"); break; }
    }
    out
}

// ------------------------------------------------------------------ roles, phases, bounds, failures

/// Who makes a call: the stats key (with the provider) and the token bucket's priority. FT-000 (S1-1, S1-3): the
/// engine's lookup-table fetches have their own role (`alt`), and the state stream's re-read after a (re)connection runs
/// as `snapshot` (critical: it queued behind the lookup-table fetches and took 51.4 s at boot). WP-07's ledger (its
/// balance snapshots and its reconciliation's window searches) is `ledger` (integration: WP-07 had used the then unused
/// `snapshot`, which the FT-000 fixes gave to the re-read; one role each keeps their counts apart in `rpc_budget`)
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Role { Boot, Snapshot, Exec, Settle, Engine, Alt, Leaders, Provenance, Wallet, Blockhash, Backfill, Slotidx, Sample, Warm, Other, Ledger }

impl Role {
    pub const ALL: [Role; 16] = [Role::Boot, Role::Snapshot, Role::Exec, Role::Settle, Role::Engine, Role::Alt, Role::Leaders, Role::Provenance, Role::Wallet,
        Role::Blockhash, Role::Backfill, Role::Slotidx, Role::Sample, Role::Warm, Role::Other, Role::Ledger];
    /// the roles of the chain-fetch service, the ones a `[[chainfetch.provider]]` names
    pub const FETCH: [Role; 5] = [Role::Wallet, Role::Blockhash, Role::Backfill, Role::Slotidx, Role::Sample];
    pub fn as_str(self) -> &'static str {
        match self { Role::Boot => "boot", Role::Snapshot => "snapshot", Role::Exec => "exec", Role::Settle => "settle", Role::Engine => "engine",
            Role::Alt => "alt", Role::Leaders => "leaders", Role::Provenance => "provenance", Role::Wallet => "wallet", Role::Blockhash => "blockhash",
            Role::Backfill => "backfill", Role::Slotidx => "slotidx", Role::Sample => "sample", Role::Warm => "warm", Role::Other => "other",
            Role::Ledger => "ledger" }
    }
    pub fn parse(s: &str) -> Option<Role> { Role::ALL.into_iter().find(|r| r.as_str() == s) }
    /// The bucket priority: 0 critical (may take the bucket's last token), 1 normal (keeps a quarter of the burst), 2 index
    /// and 3 bulk (keep half). Waiting callers are served by priority, then in order: the slot index, the coverage sample
    /// and the blockhash poll (2) go before the backfill (3) on a provider they share. FT-000 (S1-1): a role with a
    /// reserved share of a bucket ([`Limiter::set_reserve`], `[chainfetch] reserve`) is served ahead of that order while
    /// its share holds a token, so a busy normal role can no longer starve the slot index or the backfill
    pub fn priority(self) -> u8 {
        match self {
            // the ledger's money view gates every live send (stale: nothing is sent): critical, and a few calls an hour
            Role::Boot | Role::Snapshot | Role::Exec | Role::Settle | Role::Ledger => 0,
            Role::Engine | Role::Alt | Role::Leaders | Role::Provenance | Role::Wallet => 1,
            Role::Slotidx | Role::Sample | Role::Blockhash => 2,
            Role::Backfill | Role::Warm | Role::Other => 3,
        }
    }
    /// How long a plain `call` (not bounded) waits for its token: an executor call (a simulation, a gate check) is worth
    /// nothing late, so it fails over or fails within a second; the others wait up to 10 s (the engine's re-snapshot
    /// after a reconnect is a burst of requests)
    pub fn token_wait(self) -> Duration { if self == Role::Exec { Duration::from_secs(1) } else { Duration::from_secs(10) } }
}

/// JSON-RPC error codes that state a fact of the chain, the same on every provider: the slot was skipped (-32007,
/// -32009), the transaction version is not supported at the version asked (-32015). Any other error answer may be the
/// provider's own
pub fn code_is_chain_fact(code: Option<i64>) -> bool { matches!(code, Some(-32007 | -32009 | -32015)) }

/// How `call` behaves: `Run` (each call as configured: race or failover, one round), or `Boot` (PLAN-ADDENDUM I-1:
/// every call retries with backoff across the providers until `boot_retry` runs out). Shared by every client made from
/// the same root (`only`, `with_role`), so `Exec::new`'s calls follow it too
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Phase { Run = 0, Boot = 1 }

/// The limits of a bounded call
#[derive(Clone, Copy, Debug)]
pub struct Bounds {
    /// give up after this long (token waits and backoff included)
    pub deadline: Duration,
    /// attempts after the first (each attempt is one request to one provider)
    pub retries: u32,
    /// one request's timeout (cut to what is left of the deadline)
    pub attempt_timeout: Duration,
    /// the wait after every provider failed once, doubling up to `backoff_max`
    pub backoff_first: Duration,
    pub backoff_max: Duration,
}

impl Bounds {
    /// a chain fetch: `deadline` in all, `retries` more attempts (the next provider at once, then a short backoff)
    pub fn fetch(deadline: Duration, retries: u32) -> Bounds {
        Bounds { deadline, retries, attempt_timeout: deadline, backoff_first: Duration::from_millis(100), backoff_max: Duration::from_secs(1) }
    }
    /// the boot policy (I-1): retry across the providers with backoff for `budget`; a request gets 5 s
    pub fn boot(budget: Duration) -> Bounds {
        Bounds { deadline: budget, retries: u32::MAX, attempt_timeout: Duration::from_secs(5), backoff_first: Duration::from_millis(250), backoff_max: Duration::from_secs(8) }
    }
}

/// A successful bounded call
#[derive(Clone, Debug)]
pub struct Fetched { pub value: Value, pub provider: String, pub latency_ms: f64, pub bytes: usize, pub attempts: u32 }

/// What went wrong with a request
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum ErrClass {
    /// HTTP 429, or a JSON-RPC rate-limit error
    RateLimited,
    /// no complete answer within the request's timeout
    Timeout,
    /// the reply was cut or garbled while it was read, or is not JSON (cmp2: Shyft's HTTP/2 "error decoding response body")
    Body,
    /// another HTTP status without a JSON-RPC answer
    Http,
    /// the connection failed (connect, TLS, reset before a reply)
    Transport,
    /// a JSON-RPC error answer (the provider answered: skipped slot, invalid params, node behind, ...)
    Rpc,
    /// a reply with neither a result nor an error (a gateway's own message)
    NoResult,
    /// no token of the provider's bucket before the deadline
    Budget,
    /// the client has no provider
    NoProvider,
    /// the run is stopping
    Stopped,
}

impl ErrClass {
    pub fn as_str(self) -> &'static str {
        match self { ErrClass::RateLimited => "rate_limited", ErrClass::Timeout => "timeout", ErrClass::Body => "body", ErrClass::Http => "http",
            ErrClass::Transport => "transport", ErrClass::Rpc => "rpc", ErrClass::NoResult => "no_result", ErrClass::Budget => "rate_budget",
            ErrClass::NoProvider => "no_provider", ErrClass::Stopped => "stopped" }
    }
}

/// A failed request (or bounded call): its class, the provider, the HTTP status and JSON-RPC code when there were any,
/// and a message with every URL scrubbed
#[derive(Clone, Debug)]
pub struct RpcFailure { pub class: ErrClass, pub provider: Option<String>, pub status: Option<u16>, pub code: Option<i64>, pub msg: String, pub retryable: bool, pub attempts: u32 }

impl RpcFailure {
    pub fn new(class: ErrClass, provider: Option<&str>, msg: String) -> RpcFailure {
        let retryable = !matches!(class, ErrClass::Rpc | ErrClass::NoProvider | ErrClass::Stopped);
        RpcFailure { class, provider: provider.map(String::from), status: None, code: None, msg: scrub(&msg), retryable, attempts: 1 }
    }
}

impl std::fmt::Display for RpcFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { f.write_str(&self.msg) }
}
impl std::error::Error for RpcFailure {}

/// JSON-RPC error codes that are answers, not provider trouble: asking the same provider again at once would not help.
/// Two kinds: chain facts ([`code_is_chain_fact`]: a skipped slot, an unsupported version) end a bounded call at once;
/// the others may be the provider's own (a block it does not have yet, its node behind, its own parameter limit, a
/// method its plan lacks), so a bounded call asks the providers that have not answered before it fails
pub fn code_is_answer(code: Option<i64>) -> bool {
    matches!(code, Some(-32600 | -32601 | -32602 | -32004 | -32007 | -32009 | -32014 | -32015 | -32001 | -32016))
}

// ------------------------------------------------------------------ token buckets

/// A provider's token bucket (requests/s, with a burst), shared by every role of the process. A caller takes a token
/// when the bucket holds its lane's threshold and nobody is waiting ahead of it. The lanes, in the order callers are
/// served:
/// 1. **critical** (boot, snapshot, exec, settle): may take the bucket's last token;
/// 2. **reserved** (FT-000 S1-1): a role with a reserved share of the bucket ([`Limiter::set_reserve`]) whose share holds
///    a token. Each share is a second bucket of entitlement (the share's rate, a burst of `max(1, rate)`), not of
///    capacity: every grant still takes a token of the provider's bucket, so the provider's rate is never exceeded, and
///    an idle role's unused share is simply taken by the others. A reserved caller keeps a quarter of the burst for the
///    critical ones, as a normal one does (it never takes the token a boot or exec call needs next);
/// 3. **priority**: everyone else (and a reserved role whose share is spent), by priority, then in order of arrival;
///    normal roles keep a quarter of the burst for the critical ones, index and bulk roles half.
///
/// The first in line takes the next token its lane allows, and nobody behind it can take one before it (review WP-03b
/// #1: the backfill's many waiters overtook the slot index's few). In FT-000 the engine's lookup-table fetches (normal)
/// held both providers' buckets: the slot index (index) and the backfill (bulk) never got a token while one waited; a
/// reserved share gives each of them its rate whatever waits ahead in the priority order. A 429 drains the bucket and
/// cools the provider down (250 ms, doubling with every 429 in a row, at most 8 s); no tokens accrue while it cools.
/// `rate` 0: no limit (the cool-down still applies)
pub struct Limiter { pub rate: f64, pub burst: f64, st: Mutex<LimState>, wake: tokio::sync::Notify }
struct LimState {
    tokens: f64,
    last: Instant,
    cool_until: Option<Instant>,
    streak: u32,
    /// the waiting callers: (priority, arrival) -> their role (None: a caller without one, never in the reserved lane)
    queue: BTreeMap<(u8, u64), Option<Role>>,
    seq: u64,
    /// the reserved shares (FT-000), and their entitlement
    res: Vec<Share>,
}

/// A role's reserved share of a bucket: `rate` requests/s of entitlement, up to `burst`
#[derive(Clone, Copy, Debug)]
struct Share { role: Role, rate: f64, burst: f64, ent: f64 }

/// How a token was granted
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Lane { Critical, Reserved, Priority }

/// The most of a bucket's rate its reserved shares may add up to: the slot index needs one getBlock per confirmed slot,
/// 3.7/s in FT-000, 92.5% of Shyft's 4/s (its share is 0.95 in the deploy configs). Critical callers never wait for a
/// share (their lane comes first), and the others keep at least 5% of the rate
pub const MAX_RESERVE: f64 = 0.95;

impl LimState {
    fn share(&self, r: Option<Role>) -> Option<&Share> { r.and_then(|r| self.res.iter().find(|x| x.role == r)) }
    fn entitled(&self, r: Option<Role>) -> bool { self.share(r).is_some_and(|x| x.ent >= 1.0) }
    /// the lane a caller is in now
    fn lane(&self, prio: u8, r: Option<Role>) -> Lane {
        if prio == 0 { Lane::Critical } else if self.entitled(r) { Lane::Reserved } else { Lane::Priority }
    }
    /// a caller's place in the serving order now: its lane, then arrival (critical, reserved) or priority and arrival
    fn order(&self, key: (u8, u64), r: Option<Role>) -> (u8, u8, u64) {
        match self.lane(key.0, r) { Lane::Critical => (0, 0, key.1), Lane::Reserved => (1, 0, key.1), Lane::Priority => (2, key.0, key.1) }
    }
    /// the waiting callers served before `key` (None: a newcomer of priority `prio` and role `r`, behind everyone of its
    /// lane already waiting)
    fn ahead(&self, prio: u8, r: Option<Role>, key: Option<(u8, u64)>) -> usize {
        let me = match key { Some(k) => self.order(k, r), None => { let o = self.order((prio, u64::MAX), r); (o.0, o.1, u64::MAX) } };
        self.queue.iter().filter(|(k, rr)| Some(**k) != key && self.order(**k, **rr) < me).count()
    }
}

/// A caller's place in a bucket's queue; leaving it (served, timed out, or dropped) wakes the callers behind it
struct Place<'a> { lim: &'a Limiter, key: (u8, u64), held: bool }
impl Place<'_> {
    fn leave(&mut self) {
        if !self.held { return; }
        self.held = false;
        self.lim.st.lock().unwrap_or_else(|e| e.into_inner()).queue.remove(&self.key);
        self.lim.wake.notify_waiters();
    }
}
impl Drop for Place<'_> { fn drop(&mut self) { self.leave(); } }

impl Limiter {
    pub fn new(rate: f64, burst: f64) -> Limiter {
        let burst = if rate > 0.0 { burst.max(1.0) } else { 0.0 };
        Limiter { rate: rate.max(0.0), burst, wake: tokio::sync::Notify::new(),
            st: Mutex::new(LimState { tokens: burst, last: Instant::now(), cool_until: None, streak: 0, queue: Default::default(), seq: 0, res: Vec::new() }) }
    }
    pub fn unlimited() -> Limiter { Limiter::new(0.0, 0.0) }
    /// FT-000 (S1-1): reserve `rate` requests/s of this bucket for `role` (0 removes it). The shares of one bucket never
    /// add up to more than [`MAX_RESERVE`] of its rate (`[chainfetch] reserve` is checked so; a larger sum is scaled down
    /// here)
    pub fn set_reserve(&self, role: Role, rate: f64) {
        let mut s = self.st.lock().unwrap_or_else(|e| e.into_inner());
        s.res.retain(|x| x.role != role);
        if self.rate > 0.0 && rate > 0.0 && rate.is_finite() {
            let burst = rate.max(1.0);
            s.res.push(Share { role, rate, burst, ent: burst });
        }
        let sum: f64 = s.res.iter().map(|x| x.rate).sum();
        if sum > MAX_RESERVE * self.rate { let k = MAX_RESERVE * self.rate / sum; for x in s.res.iter_mut() { x.rate *= k; } }
        s.res.sort_by_key(|x| x.role);
    }
    /// the rate reserved for `role` (0: none)
    pub fn reserved(&self, role: Role) -> f64 { self.st.lock().unwrap_or_else(|e| e.into_inner()).share(Some(role)).map_or(0.0, |x| x.rate) }
    /// every reserved share: (role, requests/s)
    pub fn reserves(&self) -> Vec<(Role, f64)> { self.st.lock().unwrap_or_else(|e| e.into_inner()).res.iter().map(|x| (x.role, x.rate)).collect() }
    /// the tokens a caller needs in the bucket: 1 for critical callers; plus a reserve of a quarter of the burst for
    /// reserved and normal ones, half for index and bulk ones in the priority lane; never more than the burst
    fn threshold(&self, lane: Lane, prio: u8) -> f64 {
        let t = match (lane, prio) { (Lane::Critical, _) | (_, 0) => 1.0, (Lane::Reserved, _) | (_, 1) => 1.0 + 0.25 * self.burst, _ => 1.0 + 0.5 * self.burst };
        t.min(self.burst.max(1.0))
    }
    /// tokens accrue at `rate` up to the burst, never during a cool-down (review WP-03b #19: a bucket that refilled while
    /// it cooled sent a whole burst the moment the cool-down ended); the shares' entitlement accrues at their rates
    fn refill(&self, s: &mut LimState, now: Instant) {
        let dt_all = now.saturating_duration_since(s.last).as_secs_f64();
        for x in s.res.iter_mut() { x.ent = (x.ent + dt_all * x.rate).min(x.burst); }
        if let Some(c) = s.cool_until {
            if now < c { s.last = now; return; }
            s.cool_until = None;
            if s.last < c { s.last = c; }
        }
        if self.rate > 0.0 {
            let dt = now.saturating_duration_since(s.last).as_secs_f64();
            s.tokens = (s.tokens + dt * self.rate).min(self.burst);
        }
        if now > s.last { s.last = now; }
    }
    /// a token now if the caller is first in line and the bucket holds its lane's threshold; else an estimate of the wait
    /// (the cool-down, or the tokens it and the callers ahead of it need; for a caller with a spent share, also when its
    /// share holds a token again)
    fn grant(&self, s: &mut LimState, prio: u8, r: Option<Role>, ahead: usize, now: Instant) -> std::result::Result<Lane, Duration> {
        if let Some(c) = s.cool_until { if now < c { return Err(c - now); } }
        let lane = s.lane(prio, r);
        if self.rate <= 0.0 { return Ok(lane); }
        let th = self.threshold(lane, prio);
        if ahead == 0 && s.tokens >= th {
            s.tokens -= 1.0;
            if lane == Lane::Reserved { if let Some(x) = s.res.iter_mut().find(|x| Some(x.role) == r) { x.ent -= 1.0; } }
            return Ok(lane);
        }
        let need = (th + ahead as f64 - s.tokens).max(0.0);
        let mut w = need / self.rate;
        if lane == Lane::Priority {
            // a spent share: it may be served sooner, in the reserved lane, once its share holds a token again
            let th_res = self.threshold(Lane::Reserved, prio);
            if let Some(x) = s.share(r) { w = w.min(((1.0 - x.ent) / x.rate).max((th_res - s.tokens).max(0.0) / self.rate)); }
        }
        Err(Duration::from_secs_f64(w).max(Duration::from_millis(1)))
    }
    /// Take a token now if the cool-down, the bucket and the queue allow it (a newcomer goes behind every queued caller of
    /// its priority or a higher one); else how long until they may
    pub fn try_take(&self, prio: u8, now: Instant) -> std::result::Result<(), Duration> { self.try_take_as(prio, None, now).map(|_| ()) }
    /// `try_take` for a caller of `role` (its reserved share, if any, applies)
    pub fn try_take_role(&self, role: Role, now: Instant) -> std::result::Result<Lane, Duration> { self.try_take_as(role.priority(), Some(role), now) }
    fn try_take_as(&self, prio: u8, r: Option<Role>, now: Instant) -> std::result::Result<Lane, Duration> {
        let mut s = self.st.lock().unwrap_or_else(|e| e.into_inner());
        self.refill(&mut s, now);
        let ahead = s.ahead(prio, r, None);
        self.grant(&mut s, prio, r, ahead, now)
    }
    /// How long a newcomer of priority `prio` would wait now (zero: a token is there for it), without taking one
    pub fn wait_hint(&self, prio: u8, now: Instant) -> Duration { self.wait_hint_as(prio, None, now) }
    /// `wait_hint` for a caller of `role`
    pub fn wait_hint_role(&self, role: Role, now: Instant) -> Duration { self.wait_hint_as(role.priority(), Some(role), now) }
    fn wait_hint_as(&self, prio: u8, r: Option<Role>, now: Instant) -> Duration {
        let mut s = self.st.lock().unwrap_or_else(|e| e.into_inner());
        self.refill(&mut s, now);
        if let Some(c) = s.cool_until { if now < c { return c - now; } }
        if self.rate <= 0.0 { return Duration::ZERO; }
        let (th, ahead) = (self.threshold(s.lane(prio, r), prio), s.ahead(prio, r, None));
        if ahead == 0 && s.tokens >= th { Duration::ZERO } else { Duration::from_secs_f64((th + ahead as f64 - s.tokens).max(0.0) / self.rate) }
    }
    /// the callers waiting in the queue now
    pub fn queued(&self) -> usize { self.st.lock().unwrap_or_else(|e| e.into_inner()).queue.len() }
    /// Wait for a token (at most until `until`; a wait that cannot end in time fails at once): Ok(how long it waited:
    /// zero when the token was there), Err when `until` comes first
    pub async fn take(&self, prio: u8, until: Option<Instant>) -> std::result::Result<Duration, ()> { self.take_as(prio, None, until).await.map(|x| x.0) }
    /// `take` for a caller of `role`: Ok(the wait, the lane that granted it)
    pub async fn take_role(&self, role: Role, until: Option<Instant>) -> std::result::Result<(Duration, Lane), ()> { self.take_as(role.priority(), Some(role), until).await }
    async fn take_as(&self, prio: u8, r: Option<Role>, until: Option<Instant>) -> std::result::Result<(Duration, Lane), ()> {
        let start = Instant::now();
        let key = {
            let mut s = self.st.lock().unwrap_or_else(|e| e.into_inner());
            self.refill(&mut s, start);
            let ahead = s.ahead(prio, r, None);
            match self.grant(&mut s, prio, r, ahead, start) {
                Ok(lane) => return Ok((Duration::ZERO, lane)),
                Err(w) if until.is_some_and(|u| start + w > u) && s.share(r).is_none() => return Err(()),
                Err(_) => { s.seq += 1; let k = (prio, s.seq); s.queue.insert(k, r); k }
            }
        };
        let mut place = Place { lim: self, key, held: true };
        loop {
            let woken = self.wake.notified();
            tokio::pin!(woken);
            woken.as_mut().enable();
            let now = Instant::now();
            let got = {
                let mut s = self.st.lock().unwrap_or_else(|e| e.into_inner());
                self.refill(&mut s, now);
                let ahead = s.ahead(prio, r, Some(key));
                let g = self.grant(&mut s, prio, r, ahead, now);
                if g.is_ok() { s.queue.remove(&key); }
                g
            };
            match got {
                Ok(lane) => {
                    place.held = false;
                    self.wake.notify_waiters();
                    return Ok(((now - start).max(Duration::from_nanos(1)), lane));
                }
                Err(w) => {
                    if until.is_some_and(|u| now >= u) { place.leave(); return Err(()); }
                    // a wait that cannot end in time fails at once (a caller with a share may be served sooner than the
                    // estimate: it waits until its deadline)
                    let w = match until { Some(u) if now + w > u => { if self.st.lock().unwrap_or_else(|e| e.into_inner()).share(r).is_none() { place.leave(); return Err(()); } u - now } _ => w };
                    tokio::select! { _ = &mut woken => {}, _ = tokio::time::sleep(w) => {} }
                }
            }
        }
    }
    /// a 429: drain the bucket and cool the provider down
    pub fn on_rate_limited(&self, now: Instant) {
        let mut s = self.st.lock().unwrap_or_else(|e| e.into_inner());
        self.refill(&mut s, now);
        s.streak = (s.streak + 1).min(16);
        let cd = Duration::from_millis(250 << (s.streak.min(6) - 1)).min(Duration::from_secs(8));
        s.cool_until = Some(now + cd);
        s.tokens = s.tokens.min(0.0);
    }
    pub fn on_ok(&self) { self.st.lock().unwrap_or_else(|e| e.into_inner()).streak = 0; }
    /// how long the cool-down still runs
    pub fn cooling(&self, now: Instant) -> Duration {
        self.st.lock().unwrap_or_else(|e| e.into_inner()).cool_until.map_or(Duration::ZERO, |c| c.saturating_duration_since(now))
    }
}

// ------------------------------------------------------------------ the per-(role, provider) registry

/// One (role, provider)'s counters since the start. `calls` are HTTP requests sent (`ok` + `errors`); `budget` counts
/// the calls refused for want of a token, which sent nothing (review WP-03b #8)
#[derive(Clone, Copy, Default, Debug, PartialEq, Eq)]
pub struct Totals {
    pub calls: u64, pub ok: u64, pub errors: u64, pub rate_limited: u64, pub timeouts: u64, pub body: u64, pub http: u64, pub transport: u64,
    pub rpc: u64, pub no_result: u64, pub budget: u64,
    /// requests that waited for their token (a token granted at once is no wait: review WP-03b #7), and how long in all (µs)
    pub throttled: u64, pub throttle_wait_us: u64,
    /// FT-000: tokens granted through the role's reserved share of the bucket (`Lane::Reserved`)
    pub reserved: u64,
}

impl Totals {
    fn minus(&self, p: &Totals) -> Totals {
        Totals { calls: self.calls - p.calls, ok: self.ok - p.ok, errors: self.errors - p.errors, rate_limited: self.rate_limited - p.rate_limited,
            timeouts: self.timeouts - p.timeouts, body: self.body - p.body, http: self.http - p.http, transport: self.transport - p.transport, rpc: self.rpc - p.rpc,
            no_result: self.no_result - p.no_result, budget: self.budget - p.budget, throttled: self.throttled - p.throttled,
            throttle_wait_us: self.throttle_wait_us - p.throttle_wait_us, reserved: self.reserved - p.reserved }
    }
}

/// latencies kept per key for the interval percentiles (the newest; at most this many or this old)
const LAT_KEEP: usize = 8_192;
const LAT_KEEP_NS: u64 = 120_000_000_000;

#[derive(Default)]
struct KeyStats { t: Totals, lat: VecDeque<(u64, u32)>, sent: Decay }

fn r3(x: f64) -> f64 { (x * 1_000.0).round() / 1_000.0 }

/// the time constant of the request rates the registry keeps per (role, provider) (`used_rps`)
const RATE_TAU_S: f64 = 10.0;

/// An exponentially decaying count of events: its value over `RATE_TAU_S` is the recent rate (a steady stream of r/s
/// converges to r)
#[derive(Default, Clone, Copy, Debug)]
struct Decay { c: f64, t: Option<Instant> }
impl Decay {
    fn at(&self, now: Instant) -> f64 { self.t.map_or(0.0, |t| self.c * (-now.saturating_duration_since(t).as_secs_f64() / RATE_TAU_S).exp()) }
    fn add(&mut self, now: Instant) { self.c = self.at(now) + 1.0; self.t = Some(now); }
    fn rate(&self, now: Instant) -> f64 { self.at(now) / RATE_TAU_S }
}

/// Every client's calls, per (role, provider), and every provider's token bucket: one per process
/// ([`Registry::global`]; tests make their own). The consumers (resources.jsonl, status.jsonl) each take their own
/// deltas
#[derive(Default)]
pub struct Registry {
    stats: Mutex<BTreeMap<(Role, String), KeyStats>>,
    limits: Mutex<HashMap<String, Arc<Limiter>>>,
    /// the bucket of a provider without its own limit: (rate, burst); None: unlimited
    default_limit: Mutex<Option<(f64, f64)>>,
    /// per consumer: when it last took its deltas, and the totals then
    prev: Mutex<HashMap<&'static str, (u64, BTreeMap<(Role, String), Totals>)>>,
    last_used: Mutex<HashMap<String, Instant>>,
    /// events.jsonl for the boot policy (`rpc_boot_retry`, `rpc_boot_failed`)
    sink: OnceLock<crate::rec::Rec>,
    /// FT-000: when each `budget_json` consumer last took its deltas (the runtime's clock: a paused clock in tests)
    budget_t: Mutex<HashMap<&'static str, Instant>>,
    last_boot_event: AtomicU64,
    boot_events_suppressed: AtomicU64,
}

static GLOBAL: LazyLock<Arc<Registry>> = LazyLock::new(|| Arc::new(Registry::default()));

impl Registry {
    /// the process's registry (every client's default)
    pub fn global() -> Arc<Registry> { GLOBAL.clone() }

    /// Provider `name`'s bucket: `rate` requests/s with `burst` (None: `max(1, rate)`); `rate` 0: no limit
    pub fn set_limit(&self, name: &str, rate: f64, burst: Option<f64>) {
        let b = burst.unwrap_or(rate.max(1.0));
        self.limits.lock().unwrap().insert(name.to_string(), Arc::new(if rate > 0.0 { Limiter::new(rate, b) } else { Limiter::unlimited() }));
    }
    /// the bucket of every provider without its own (`rate` 0: none)
    pub fn set_default_limit(&self, rate: f64) { *self.default_limit.lock().unwrap() = (rate > 0.0).then_some((rate, rate.max(1.0))); }

    /// provider `name`'s bucket (made from the default the first time)
    pub fn limiter(&self, name: &str) -> Arc<Limiter> {
        let mut m = self.limits.lock().unwrap();
        if let Some(l) = m.get(name) { return l.clone(); }
        let l = Arc::new(match *self.default_limit.lock().unwrap() { Some((r, b)) => Limiter::new(r, b), None => Limiter::unlimited() });
        m.insert(name.to_string(), l.clone());
        l
    }

    /// (rate, burst) per provider with a bucket (meta.json)
    pub fn limits_json(&self) -> Value {
        let m = self.limits.lock().unwrap();
        let mut v: Vec<(&String, &Arc<Limiter>)> = m.iter().collect();
        v.sort_by(|a, b| a.0.cmp(b.0));
        Value::Object(v.into_iter().map(|(k, l)| {
            let mut x = json!({ "max_rps": (l.rate > 0.0).then_some(l.rate), "burst": (l.rate > 0.0).then_some(l.burst) });
            // FT-000: the reserved shares, requests/s by role (absent: none)
            let res = l.reserves();
            if !res.is_empty() { x["reserve"] = Value::Object(res.into_iter().map(|(r, rate)| (r.as_str().to_string(), json!(r3(rate)))).collect()); }
            (k.clone(), x)
        }).collect())
    }

    /// the boot policy's events go to `rec` (events.jsonl)
    pub fn set_sink(&self, rec: crate::rec::Rec) { let _ = self.sink.set(rec); }

    /// one request's outcome: Ok(latency µs) or its class; `waited`: its token wait. A `rate_budget` refusal sent no
    /// request: it counts only as `budget`
    pub fn record(&self, role: Role, provider: &str, r: std::result::Result<u32, ErrClass>, waited: Duration) {
        let t = crate::feeds::clock::now_ns();
        let mut m = self.stats.lock().unwrap();
        let k = m.entry((role, provider.to_string())).or_default();
        if r == Err(ErrClass::Budget) { k.t.budget += 1; return; }
        k.sent.add(Instant::now());
        let x = &mut k.t;
        x.calls += 1;
        if !waited.is_zero() { x.throttled += 1; x.throttle_wait_us += waited.as_micros() as u64; }
        match r {
            Ok(us) => {
                x.ok += 1;
                k.lat.push_back((t, us));
                while k.lat.len() > LAT_KEEP || k.lat.front().is_some_and(|f| t.saturating_sub(f.0) > LAT_KEEP_NS) { k.lat.pop_front(); }
            }
            Err(c) => {
                x.errors += 1;
                match c {
                    ErrClass::RateLimited => x.rate_limited += 1, ErrClass::Timeout => x.timeouts += 1, ErrClass::Body => x.body += 1, ErrClass::Http => x.http += 1,
                    ErrClass::Transport => x.transport += 1, ErrClass::Rpc => x.rpc += 1, ErrClass::NoResult => x.no_result += 1, ErrClass::Budget => x.budget += 1,
                    ErrClass::NoProvider | ErrClass::Stopped => {}
                }
            }
        }
        drop(m);
        self.last_used.lock().unwrap().insert(provider.to_string(), Instant::now());
    }

    /// how long provider `name` has not been called (None: never)
    pub fn idle_for(&self, name: &str) -> Option<Duration> { self.last_used.lock().unwrap().get(name).map(|t| t.elapsed()) }

    /// the requests/s every role but `except` sent to provider `name` lately (a 10 s decaying average)
    pub fn used_rps(&self, name: &str, except: Role) -> f64 {
        let now = Instant::now();
        self.stats.lock().unwrap().iter().filter(|((r, p), _)| *r != except && p == name).map(|(_, k)| k.sent.rate(now)).sum()
    }

    /// What is left of provider `name`'s budget for `role` after every other role's recent requests: its rate minus what
    /// they used, and never less than the role's reserved share (FT-000: the backfill paced itself to 0.03/s while the
    /// lookup-table fetches used everything); 0 while it cools down after a 429; None: the provider has no limit. The
    /// backfill sizes itself to the sum over its providers (review WP-03b #1b, #10)
    pub fn spare_rps(&self, name: &str, role: Role) -> Option<f64> {
        let l = self.limiter(name);
        if l.rate <= 0.0 { return None; }
        if !l.cooling(Instant::now()).is_zero() { return Some(0.0); }
        Some((l.rate - self.used_rps(name, role)).max(0.0).max(l.reserved(role)))
    }

    /// FT-000 (S1-1): reserve `rate` requests/s of provider `name`'s bucket for `role` (after `set_limit`; a provider
    /// without a limit has nothing to reserve)
    pub fn set_reserve(&self, name: &str, role: Role, rate: f64) { self.limiter(name).set_reserve(role, rate); }

    /// a token granted through `role`'s reserved share (counted as `reserved`)
    pub fn record_lane(&self, role: Role, provider: &str, lane: Lane) {
        if lane != Lane::Reserved { return; }
        self.stats.lock().unwrap().entry((role, provider.to_string())).or_default().t.reserved += 1;
    }

    /// every (role, provider)'s totals since the start
    pub fn totals(&self) -> BTreeMap<(Role, String), Totals> { self.stats.lock().unwrap().iter().map(|(k, v)| (k.clone(), v.t)).collect() }
    pub fn total(&self, role: Role, provider: &str) -> Totals { self.stats.lock().unwrap().get(&(role, provider.to_string())).map(|k| k.t).unwrap_or_default() }

    /// The deltas since `consumer`'s previous call (and, with `pct`, the p50/p90/p99 ms of its latencies since then)
    fn take(&self, consumer: &'static str, pct: bool) -> Vec<((Role, String), Totals, Option<[f64; 3]>)> {
        let now = crate::feeds::clock::now_ns();
        let m = self.stats.lock().unwrap();
        let mut prev = self.prev.lock().unwrap();
        let (since, p) = prev.entry(consumer).or_insert((0, BTreeMap::new()));
        let mut out = Vec::new();
        for (k, s) in m.iter() {
            let d = s.t.minus(p.get(k).unwrap_or(&Totals::default()));
            if d == Totals::default() { continue; }
            let mut v: Vec<u32> = if pct { s.lat.iter().filter(|x| x.0 > *since).map(|x| x.1).collect() } else { Vec::new() };
            let pct = (!v.is_empty()).then(|| {
                v.sort_unstable();
                let q = |f: f64| (v[((v.len() - 1) as f64 * f).round() as usize] as f64 / 10.0).round() / 100.0;
                [q(0.5), q(0.9), q(0.99)]
            });
            out.push((k.clone(), d, pct));
        }
        *p = m.iter().map(|(k, v)| (k.clone(), v.t)).collect();
        *since = now;
        out
    }

    /// FT-000 (S1-1): status.jsonl `rpc_budget` (MEASUREMENT §4.8): each provider's budget and what each role used of it
    /// since `consumer`'s previous call: `{interval_s, providers: {<name>: {max_rps, calls_delta, rps, used_pct,
    /// queued_now, cooling_ms_now, roles: {<role>: {calls_delta, rps, share_pct, reserved_rps, reserved_delta,
    /// throttled_delta, wait_ms_delta, rate_budget_delta}}}}, roles: {<role>: {calls_delta, rps, share_pct}}}`. `rps` is
    /// requests sent per second of the interval; `share_pct` the share of the provider's `max_rps` (of the summed
    /// `max_rps` of the limited providers in `roles`); a role with a reserved share is listed even when it sent nothing
    pub fn budget_json(&self, consumer: &'static str) -> Value {
        let d = self.take(consumer, false);
        let now = Instant::now();
        let secs = self.budget_t.lock().unwrap().insert(consumer, now).map_or(0.0, |t| now.saturating_duration_since(t).as_secs_f64());
        let rate = |n: u64| if secs > 0.0 { Some(r3(n as f64 / secs)) } else { None };
        let limits: Vec<(String, Arc<Limiter>)> = { let m = self.limits.lock().unwrap(); let mut v: Vec<_> = m.iter().map(|(k, l)| (k.clone(), l.clone())).collect(); v.sort_by(|a, b| a.0.cmp(&b.0)); v };
        let mut providers = serde_json::Map::new();
        let mut by_role: BTreeMap<Role, u64> = BTreeMap::new();
        let mut cap_sum = 0.0;
        for (name, l) in &limits {
            let rows: Vec<&((Role, String), Totals, Option<[f64; 3]>)> = d.iter().filter(|x| &x.0 .1 == name).collect();
            let reserves = l.reserves();
            if rows.is_empty() && reserves.is_empty() && l.rate <= 0.0 { continue; }
            let max = (l.rate > 0.0).then_some(l.rate);
            if let Some(m) = max { cap_sum += m; }
            let calls: u64 = rows.iter().map(|x| x.1.calls).sum();
            let mut roles = serde_json::Map::new();
            let mut names: Vec<Role> = rows.iter().map(|x| x.0 .0).chain(reserves.iter().map(|x| x.0)).collect();
            names.sort();
            names.dedup();
            for r in names {
                let t = rows.iter().find(|x| x.0 .0 == r).map(|x| x.1).unwrap_or_default();
                *by_role.entry(r).or_default() += t.calls;
                let res = reserves.iter().find(|x| x.0 == r).map(|x| r3(x.1));
                roles.insert(r.as_str().to_string(), json!({ "calls_delta": t.calls, "rps": rate(t.calls),
                    "share_pct": max.and_then(|m| rate(t.calls).map(|x| r3(x * 100.0 / m))), "reserved_rps": res, "reserved_delta": t.reserved,
                    "throttled_delta": t.throttled, "wait_ms_delta": r3(t.throttle_wait_us as f64 / 1e3), "rate_budget_delta": t.budget }));
            }
            providers.insert(name.clone(), json!({ "max_rps": max, "calls_delta": calls, "rps": rate(calls),
                "used_pct": max.and_then(|m| rate(calls).map(|x| r3(x * 100.0 / m))), "queued_now": l.queued(),
                "cooling_ms_now": l.cooling(now).as_millis() as u64, "roles": roles }));
        }
        // roles of providers without a bucket entry (no limit) still count in `roles`
        for ((r, p), t, _) in &d { if !limits.iter().any(|(n, _)| n == p) { *by_role.entry(*r).or_default() += t.calls; } }
        let roles: serde_json::Map<String, Value> = by_role.into_iter().map(|(r, n)| (r.as_str().to_string(), json!({ "calls_delta": n, "rps": rate(n),
            "share_pct": (cap_sum > 0.0).then(|| rate(n).map(|x| r3(x * 100.0 / cap_sum))).flatten() }))).collect();
        json!({ "interval_s": (secs > 0.0).then(|| r3(secs)), "providers": providers, "roles": roles })
    }

    /// resources.jsonl `rpc` (MEASUREMENT §4.10): `{"<role>/<provider>": {calls_delta, ok_delta, errors_delta,
    /// rate_limited_delta, timeouts_delta, body_errors_delta, http_errors_delta, transport_errors_delta, rpc_errors_delta,
    /// no_result_delta, rate_budget_delta, throttled_delta, throttle_wait_ms_delta, p50_ms, p90_ms, p99_ms}}` for the
    /// keys with calls since the previous line
    pub fn resources_json(&self) -> Value {
        Value::Object(self.take("resources", true).into_iter().map(|((role, prov), d, p)| (format!("{}/{prov}", role.as_str()), json!({
            "calls_delta": d.calls, "ok_delta": d.ok, "errors_delta": d.errors, "rate_limited_delta": d.rate_limited, "timeouts_delta": d.timeouts,
            "body_errors_delta": d.body, "http_errors_delta": d.http, "transport_errors_delta": d.transport, "rpc_errors_delta": d.rpc,
            "no_result_delta": d.no_result, "rate_budget_delta": d.budget, "throttled_delta": d.throttled,
            "throttle_wait_ms_delta": (d.throttle_wait_us as f64 / 10.0).round() / 100.0, "reserved_delta": d.reserved,
            "p50_ms": p.map(|x| x[0]), "p90_ms": p.map(|x| x[1]), "p99_ms": p.map(|x| x[2]) }))).collect())
    }

    /// status.jsonl `chainfetch.by_role` (MEASUREMENT §4.8): `{role: {calls_delta, errors_delta, rate_limited_delta,
    /// rate_budget_delta}}` since `consumer`'s previous call, summed over the providers (no percentiles: the status line
    /// runs on the engine thread, review WP-03b #23)
    pub fn by_role_json(&self, consumer: &'static str) -> Value {
        let mut by: BTreeMap<&'static str, (u64, u64, u64, u64)> = BTreeMap::new();
        for ((role, _), d, _) in self.take(consumer, false) {
            let e = by.entry(role.as_str()).or_default();
            e.0 += d.calls; e.1 += d.errors; e.2 += d.rate_limited; e.3 += d.budget;
        }
        Value::Object(by.into_iter().map(|(k, (c, e, r, b))| (k.to_string(), json!({ "calls_delta": c, "errors_delta": e, "rate_limited_delta": r,
            "rate_budget_delta": b }))).collect())
    }

    /// run.log at the end: one line per (role, provider) with its totals and the latency of its last answers
    pub fn summary_lines(&self) -> Vec<String> {
        self.stats.lock().unwrap().iter().map(|((role, prov), k)| {
            let t = &k.t;
            let mut v: Vec<u32> = k.lat.iter().map(|x| x.1).collect();
            v.sort_unstable();
            let p = |q: f64| if v.is_empty() { "-".to_string() } else { format!("{:.1}", v[((v.len() - 1) as f64 * q).round() as usize] as f64 / 1e3) };
            format!("{}/{prov}: {} calls, {} ok, {} rate_limited, {} timeout, {} body, {} http, {} transport, {} rpc, {} rate_budget, {} throttled; p50/p99 {}/{} ms",
                role.as_str(), t.calls, t.ok, t.rate_limited, t.timeouts, t.body, t.http, t.transport, t.rpc, t.budget, t.throttled, p(0.5), p(0.99))
        }).collect()
    }

    /// a boot-policy event (events.jsonl): `rpc_boot_failed` always, `rpc_boot_retry` at most once a second (the others
    /// counted in the next one's `suppressed`)
    fn boot_event(&self, kind: &'static str, mut detail: Value) {
        let Some(rec) = self.sink.get() else { return };
        if kind == "rpc_boot_retry" {
            let now = crate::feeds::clock::now_ns();
            let last = self.last_boot_event.load(Relaxed);
            if now.saturating_sub(last) < 1_000_000_000 || self.last_boot_event.compare_exchange(last, now, Relaxed, Relaxed).is_err() {
                self.boot_events_suppressed.fetch_add(1, Relaxed);
                return;
            }
            detail["suppressed"] = json!(self.boot_events_suppressed.swap(0, Relaxed));
        }
        rec.event(kind, "rpc", None, detail);
    }
}

// ------------------------------------------------------------------ DNS

/// Each provider host resolved once and served from the cache (so a reconnect never waits on a DNS lookup: Haan's cold
/// connect was 35 ms of DNS in 53 ms); `refresh` re-resolves in the background, keeping the old addresses on a failure
#[derive(Clone, Default)]
pub struct CachedDns(Arc<DnsInner>);
#[derive(Default)]
struct DnsInner { map: RwLock<HashMap<String, Vec<SocketAddr>>>, lookups: AtomicU64, hits: AtomicU64 }

impl CachedDns {
    async fn lookup(&self, host: &str) -> std::io::Result<Vec<SocketAddr>> {
        self.0.lookups.fetch_add(1, Relaxed);
        Ok(tokio::net::lookup_host((host, 0u16)).await?.collect())
    }
    /// resolve `host` now and cache it; how many addresses
    pub async fn prime(&self, host: &str) -> std::io::Result<usize> {
        let a = self.lookup(host).await?;
        let n = a.len();
        if n > 0 { self.0.map.write().unwrap().insert(host.to_string(), a); }
        Ok(n)
    }
    /// re-resolve every cached host (a failure keeps the old addresses)
    pub async fn refresh(&self) {
        let hosts: Vec<String> = self.0.map.read().unwrap().keys().cloned().collect();
        for h in hosts { if let Ok(a) = self.lookup(&h).await { if !a.is_empty() { self.0.map.write().unwrap().insert(h, a); } } }
    }
    pub fn cached(&self, host: &str) -> Option<Vec<SocketAddr>> { self.0.map.read().unwrap().get(host).cloned() }
    /// fresh lookups done, and connections served from the cache
    pub fn lookups(&self) -> u64 { self.0.lookups.load(Relaxed) }
    pub fn hits(&self) -> u64 { self.0.hits.load(Relaxed) }
}

impl reqwest::dns::Resolve for CachedDns {
    fn resolve(&self, name: reqwest::dns::Name) -> reqwest::dns::Resolving {
        let (me, host) = (self.clone(), name.as_str().to_string());
        Box::pin(async move {
            if let Some(a) = me.cached(&host) {
                me.0.hits.fetch_add(1, Relaxed);
                return Ok(Box::new(a.into_iter()) as reqwest::dns::Addrs);
            }
            let a = me.lookup(&host).await.map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
            if !a.is_empty() { me.0.map.write().unwrap().insert(host, a.clone()); }
            Ok(Box::new(a.into_iter()) as reqwest::dns::Addrs)
        })
    }
}

/// the host of a URL (DNS)
pub fn url_host(url: &str) -> Option<String> { reqwest::Url::parse(url).ok()?.host_str().map(String::from) }

// ------------------------------------------------------------------ the client

#[derive(Clone)]
pub struct Rpc { eps: std::sync::Arc<Vec<Endpoint>>, http: reqwest::Client, pub stats: std::sync::Arc<std::sync::Mutex<Stats>>,
    /// try the providers in order, the next only if one fails (a race sends every call to all of them: every call costs
    /// rate limit everywhere, and 15% of calls then failed on all of them)
    failover: bool,
    /// the runtime every call runs on (`bind`; `arbx run`: rt_bg). None: the caller's
    rt: Option<tokio::runtime::Handle>,
    /// WP-03b: who calls (stats key, bucket priority), where the stats go, and the boot policy (shared by every client
    /// made from this one)
    role: Role,
    reg: Arc<Registry>,
    phase: Arc<AtomicU8>,
    boot_budget_ms: Arc<AtomicU64>,
    stop: Arc<OnceLock<Arc<AtomicBool>>>,
    dns: CachedDns }

#[derive(Debug, Clone)]
pub struct Account { pub owner: Pk, pub lamports: u64, pub data: Vec<u8> }

/// the boot policy's default budget ([chainfetch] boot_retry_s)
pub const BOOT_RETRY_DEFAULT: Duration = Duration::from_secs(90);

impl Rpc {
    pub fn new(url: String) -> Rpc { Rpc::race(vec![Endpoint { name: "rpc".into(), url, bearer: None }]) }

    pub fn race(eps: Vec<Endpoint>) -> Rpc {
        let dns = CachedDns::default();
        let http = reqwest::Client::builder().tcp_nodelay(true).pool_idle_timeout(std::time::Duration::from_secs(90))
            .pool_max_idle_per_host(8).timeout(std::time::Duration::from_secs(20))
            // WP-03b: warm connections (HTTP/2 pings and TCP keep-alives cost no request budget) and no DNS on a reconnect
            .connect_timeout(Duration::from_secs(5)).tcp_keepalive(Duration::from_secs(30))
            .http2_keep_alive_interval(Duration::from_secs(15)).http2_keep_alive_timeout(Duration::from_secs(5)).http2_keep_alive_while_idle(true)
            .dns_resolver(Arc::new(dns.clone()))
            .build().expect("http client");
        Rpc { eps: std::sync::Arc::new(eps), http, stats: Default::default(), failover: false, rt: None, role: Role::Other, reg: Registry::global(),
            phase: Arc::new(AtomicU8::new(Phase::Run as u8)), boot_budget_ms: Arc::new(AtomicU64::new(BOOT_RETRY_DEFAULT.as_millis() as u64)),
            stop: Arc::new(OnceLock::new()), dns }
    }
    pub fn with_failover(mut self, on: bool) -> Rpc { self.failover = on; self }

    /// Run every call of this client (and of the clients `only` makes from it) on `rt` (the background runtime)
    pub fn bind(mut self, rt: tokio::runtime::Handle) -> Rpc { self.rt = Some(rt); self }
    pub fn is_bound(&self) -> bool { self.rt.is_some() }

    pub fn names(&self) -> Vec<String> { self.eps.iter().map(|e| e.name.clone()).collect() }
    pub fn endpoints(&self) -> &[Endpoint] { &self.eps }

    /// a client on only the named providers (one provider, not the race, for simulations and settlement), in the order
    /// named (the failover order). Its role is `exec` (the executor's client); `only_role` names another
    pub fn only(&self, names: &[String]) -> Rpc { self.only_role(Role::Exec, names) }

    /// a client on only the named providers, for `role` (stats, bucket priority); phase, stop and registry shared
    pub fn only_role(&self, role: Role, names: &[String]) -> Rpc {
        let mut x = self.clone();
        x.eps = std::sync::Arc::new(names.iter().filter_map(|n| self.eps.iter().find(|e| &e.name == n).cloned()).collect());
        x.stats = Default::default();
        x.role = role;
        x
    }
    /// the same providers for another role (phase, stop, registry and the run.log `Stats` shared)
    pub fn with_role(&self, role: Role) -> Rpc { let mut x = self.clone(); x.role = role; x }
    /// the same client with a phase of its own, set to `p` and changed by nobody else: a background task started during
    /// the boot (the LeaderBook) calls as configured, not under the boot policy (review WP-03b #14)
    pub fn with_own_phase(&self, p: Phase) -> Rpc { let mut x = self.clone(); x.phase = Arc::new(AtomicU8::new(p as u8)); x }
    pub fn role(&self) -> Role { self.role }
    pub fn is_empty(&self) -> bool { self.eps.is_empty() }

    /// stats and buckets in `reg` instead of the process's (tests)
    pub fn with_registry(mut self, reg: Arc<Registry>) -> Rpc { self.reg = reg; self }
    pub fn registry(&self) -> &Arc<Registry> { &self.reg }
    pub fn dns(&self) -> &CachedDns { &self.dns }

    /// the boot policy on or off, for this client and every client made from it (I-1)
    pub fn set_phase(&self, p: Phase) { self.phase.store(p as u8, Relaxed); }
    pub fn phase(&self) -> Phase { if self.phase.load(Relaxed) == Phase::Boot as u8 { Phase::Boot } else { Phase::Run } }
    /// how long a boot-time call retries before the boot gives up
    pub fn set_boot_budget(&self, d: Duration) { self.boot_budget_ms.store(d.as_millis().max(1) as u64, Relaxed); }
    pub fn boot_budget(&self) -> Duration { Duration::from_millis(self.boot_budget_ms.load(Relaxed)) }
    /// a boot-policy call stops retrying once `flag` is set (a stop during the boot: its retries run for the boot budget,
    /// 90 s). FT-001 p1: the flag is the run's stop flag, set when the stop is requested, before the stop sequence; every
    /// bounded call failed at once from then on ("no attempt before the deadline", no provider asked), so the ledger's stop
    /// snapshot, its window search and the executor's expiry checks never ran. Any other call is bounded by its own
    /// deadline and goes on: the stop sequence's calls are what it waits for
    pub fn set_stop(&self, flag: Arc<AtomicBool>) { let _ = self.stop.set(flag); }
    fn stopping(&self) -> bool { self.stop.get().is_some_and(|f| f.load(Relaxed)) }

    /// One request to one provider, no retry: the provider's token first (waiting at most until `until`), then the
    /// request within `timeout`; the outcome is classified and counted in the registry (role, provider)
    async fn attempt(&self, ep: &Endpoint, body: &Value, method: &str, timeout: Duration, until: Option<Instant>) -> std::result::Result<(Value, usize, Duration), RpcFailure> {
        crate::runtime::check_not_hot("an RPC call");
        let lim = self.reg.limiter(&ep.name);
        let waited = match lim.take_role(self.role, until).await {
            Ok((w, lane)) => { self.reg.record_lane(self.role, &ep.name, lane); w }
            Err(()) => {
                self.reg.record(self.role, &ep.name, Err(ErrClass::Budget), Duration::ZERO);
                return Err(RpcFailure::new(ErrClass::Budget, Some(&ep.name), format!("{} {method}: no token of its {:.1}/s budget in time", ep.name, lim.rate)));
            }
        };
        let t0 = Instant::now();
        let r = match tokio::time::timeout(timeout, http_once(&self.http, ep, body, method)).await {
            Ok(r) => r,
            Err(_) => Err(RpcFailure::new(ErrClass::Timeout, Some(&ep.name), format!("{} {method}: no answer in {:.1} s", ep.name, timeout.as_secs_f64()))),
        };
        let lat = t0.elapsed();
        match &r {
            Ok(_) => lim.on_ok(),
            Err(f) if f.class == ErrClass::RateLimited => lim.on_rate_limited(Instant::now()),
            Err(_) => {}
        }
        self.reg.record(self.role, &ep.name, r.as_ref().map(|_| lat.as_micros().min(u32::MAX as u128) as u32).map_err(|f| f.class), waited);
        r.map(|(v, n)| (v, n, lat))
    }

    /// One JSON-RPC call raced across every provider (or in failover order); returns the first successful result. A
    /// bound client runs it on its runtime (`bind`). During the boot ([`Phase::Boot`]) it is a bounded call that
    /// retries across the providers with backoff for the boot budget (PLAN-ADDENDUM I-1)
    pub async fn call(&self, method: &str, params: Value) -> Result<Value> {
        // WP-05 (F28): counted where it starts, in the caller's context (a send-path scope sees it)
        crate::netcount::note();
        if self.phase() == Phase::Boot {
            let b = Bounds::boot(self.boot_budget());
            return match self.bounded(method, params, b, true).await {
                Ok(f) => Ok(f.value),
                Err(e) => Err(anyhow::Error::new(e)),
            };
        }
        match &self.rt {
            Some(h) => {
                let mut me = self.clone();
                me.rt = None;
                let m = method.to_string();
                h.spawn(async move { me.call_here(&m, params).await }).await.map_err(|e| anyhow::anyhow!("rpc {method}: task failed: {e}"))?
            }
            None => self.call_here(method, params).await,
        }
    }

    /// A bounded call (WP-03b item 5): the providers in order, the next at once after a retryable failure (a provider
    /// cooling down after a 429, or whose bucket is empty, is passed over while another is ready), a backoff once every
    /// provider failed, until `b.retries` more attempts or `b.deadline`. A JSON-RPC error answer that states a chain fact
    /// (`code_is_chain_fact`: a skipped slot, an unsupported version) returns at once; any other error answer is taken as
    /// the provider's own: that provider is asked no more in this call and the others are, and the call fails with it only
    /// when every provider has answered so (review WP-03b #4). During the boot, every failed attempt is an events.jsonl
    /// `rpc_boot_retry`, and the final failure `rpc_boot_failed`. A bound client runs it on its runtime
    pub async fn call_bounded(&self, method: &str, params: Value, b: Bounds) -> std::result::Result<Fetched, RpcFailure> {
        crate::netcount::note();
        self.bounded(method, params, b, false).await
    }

    /// `call_bounded`; `boot`: a boot-policy call (`call` during [`Phase::Boot`]): its retries and its failure are
    /// events, and its failure reads "sustained RPC failure"
    async fn bounded(&self, method: &str, params: Value, b: Bounds, boot: bool) -> std::result::Result<Fetched, RpcFailure> {
        match &self.rt {
            Some(h) => {
                let mut me = self.clone();
                me.rt = None;
                let m = method.to_string();
                match h.spawn(async move { me.bounded_here(&m, params, b, boot).await }).await {
                    Ok(r) => r,
                    Err(e) => Err(RpcFailure::new(ErrClass::Stopped, None, format!("rpc {method}: task failed: {e}"))),
                }
            }
            None => self.bounded_here(method, params, b, boot).await,
        }
    }

    async fn bounded_here(&self, method: &str, params: Value, b: Bounds, boot: bool) -> std::result::Result<Fetched, RpcFailure> {
        let n = self.eps.len();
        if n == 0 { return Err(RpcFailure::new(ErrClass::NoProvider, None, format!("rpc {method}: no providers"))); }
        let body = json!({ "jsonrpc": "2.0", "id": 1, "method": method, "params": params });
        let start = Instant::now();
        let deadline = start + b.deadline;
        let (mut attempts, mut next) = (0u32, 0usize);
        // the providers asked in this round (each once per round; then the backoff), and those that answered with an
        // error of their own (asked no more in this call)
        let mut tried = vec![false; n];
        let mut answered = vec![false; n];
        let mut backoff = b.backoff_first;
        let mut last: Option<RpcFailure> = None;
        let mut hist: BTreeMap<(String, &'static str), u32> = BTreeMap::new();
        loop {
            let now = Instant::now();
            let all_answered = answered.iter().all(|a| *a);
            // FT-001 p1: only a boot-policy call ends on the run's stop (`set_stop`); the stop sequence's calls go on
            let stopping = boot && self.stopping();
            let out_of = if stopping { Some("the run is stopping") } else if all_answered { Some("every provider refused the request") }
                else if attempts > b.retries { Some("retries spent") } else if now >= deadline { Some("deadline") } else { None };
            if let Some(why) = out_of {
                let mut f = last.unwrap_or_else(|| if stopping { RpcFailure::new(ErrClass::Stopped, None, format!("rpc {method}: not asked: the run is stopping")) }
                    else { RpcFailure::new(ErrClass::Budget, None, format!("rpc {method}: no attempt before the deadline")) });
                if stopping { f.class = ErrClass::Stopped; f.retryable = false; }
                f.attempts = attempts;
                let summary: Vec<String> = hist.iter().map(|((p, c), k)| format!("{p} {c} x{k}")).collect();
                if attempts > 1 {
                    f.msg = format!("{method}: {}: no provider answered in {:.1} s ({attempts} attempts: {}; {why}); last: {}",
                        if boot { "sustained RPC failure" } else { "RPC failure" }, start.elapsed().as_secs_f64(), summary.join(", "), f.msg);
                }
                if boot {
                    self.reg.boot_event("rpc_boot_failed", json!({ "method": method, "role": self.role.as_str(), "attempts": attempts, "secs": start.elapsed().as_secs_f64(),
                        "by_provider_class": summary, "last": f.msg }));
                }
                return Err(f);
            }
            // of the providers not asked in this round (nor refused), the next in order that is ready now (not cooling down
            // after a 429, a token in its bucket for this role); none ready: the one ready soonest
            let k = (0..n).map(|i| (next + i) % n).filter(|&i| !tried[i] && !answered[i])
                .min_by_key(|&i| (self.reg.limiter(&self.eps[i].name).wait_hint_role(self.role, now), (i + n - next % n) % n)).unwrap_or(next % n);
            tried[k] = true;
            let ep = &self.eps[k];
            attempts += 1;
            let timeout = b.attempt_timeout.min(deadline.saturating_duration_since(now)).max(Duration::from_millis(1));
            match self.attempt(ep, &body, method, timeout, Some(deadline)).await {
                Ok((value, bytes, lat)) => return Ok(Fetched { value, provider: ep.name.clone(), latency_ms: lat.as_secs_f64() * 1e3, bytes, attempts }),
                Err(mut f) => {
                    *hist.entry((ep.name.clone(), f.class.as_str())).or_default() += 1;
                    f.attempts = attempts;
                    match f.class {
                        ErrClass::Stopped | ErrClass::NoProvider => return Err(f),
                        // a chain fact, the same everywhere: the caller's answer
                        ErrClass::Rpc if code_is_chain_fact(f.code) => return Err(f),
                        // another error answer: this provider's own (its plan, its limits, its node); the others are asked
                        _ if !f.retryable => answered[k] = true,
                        _ => {}
                    }
                    if boot {
                        self.reg.boot_event("rpc_boot_retry", json!({ "method": method, "role": self.role.as_str(), "provider": ep.name, "class": f.class.as_str(),
                            "code": f.code, "attempt": attempts, "elapsed_ms": start.elapsed().as_millis() as u64, "error": f.msg }));
                    }
                    last = Some(f);
                    next = k + 1;
                    if (0..n).all(|i| tried[i] || answered[i]) && !answered.iter().all(|a| *a) {
                        tried.iter_mut().for_each(|t| *t = false);
                        let left = deadline.saturating_duration_since(Instant::now());
                        if !left.is_zero() {
                            // jitter: up to a quarter of the backoff, from the clock's low bits (no RNG needed)
                            let j = Duration::from_micros((crate::feeds::clock::now_ns() / 1_000) % (backoff.as_micros() as u64 / 4 + 1));
                            tokio::time::sleep((backoff + j).min(left)).await;
                            backoff = (backoff * 2).min(b.backoff_max);
                        }
                    }
                }
            }
        }
    }

    async fn call_here(&self, method: &str, params: Value) -> Result<Value> {
        let body = std::sync::Arc::new(json!({ "jsonrpc": "2.0", "id": 1, "method": method, "params": params }));
        if self.failover {
            self.stats.lock().unwrap().calls += 1;
            let mut last = None;
            for (k, ep) in self.eps.iter().enumerate() {
                // a provider gets 3 s for its answer (its token wait is our own pacing and does not count); only the last
                // one retries a 429, with backoff, within its 3 s
                let is_last = k + 1 == self.eps.len();
                // WP-03b: a provider whose bucket (or 429 cool-down) would make the call wait is passed over while a later
                // one is ready (the shared budgets spread the load instead of queueing behind the first provider)
                if !is_last {
                    let now = Instant::now();
                    let ready = |e: &Endpoint| self.reg.limiter(&e.name).wait_hint_role(self.role, now).is_zero();
                    if !ready(ep) && self.eps[k + 1..].iter().any(ready) { continue; }
                }
                let t0 = Instant::now();
                let mut wait = Duration::from_millis(300);
                let r = loop {
                    let left = Duration::from_secs(3).saturating_sub(t0.elapsed()).max(Duration::from_millis(1));
                    match self.attempt(ep, &body, method, left, Some(Instant::now() + self.role.token_wait())).await {
                        Err(f) if f.class == ErrClass::RateLimited && is_last && t0.elapsed() + wait < Duration::from_secs(3) => {
                            tokio::time::sleep(wait).await;
                            wait = (wait * 2).min(Duration::from_secs(5));
                        }
                        r => break r,
                    }
                };
                let mut s = self.stats.lock().unwrap();
                match r {
                    Ok((v, _, lat)) => { s.lat.entry((ep.name.clone(), method.to_string())).or_default().push(lat.as_micros() as u64); *s.wins.entry(ep.name.clone()).or_default() += 1; return Ok(v); }
                    Err(e) => {
                        *s.errors.entry(ep.name.clone()).or_default() += 1;
                        let mut why = scrub(&e.msg); why.truncate(200);
                        *s.why.entry((ep.name.clone(), why)).or_default() += 1;
                        last = Some(e);
                    }
                }
            }
            return Err(last.map(anyhow::Error::new).unwrap_or_else(|| anyhow::anyhow!("rpc {method}: no providers")));
        }
        let (tx, mut rx) = tokio::sync::mpsc::channel::<(String, std::result::Result<Value, RpcFailure>)>(self.eps.len().max(1));
        let solo = self.eps.len() == 1;
        for ep in self.eps.iter().cloned() {
            let (me, body, tx, m) = (self.clone(), body.clone(), tx.clone(), method.to_string());
            tokio::spawn(async move {
                // a lone provider retries a 429 (up to 8 attempts, backoff 300 ms doubling to 5 s), as before
                let mut wait = Duration::from_millis(300);
                let mut n = 0;
                let r = loop {
                    n += 1;
                    match me.attempt(&ep, &body, &m, Duration::from_secs(20), Some(Instant::now() + me.role.token_wait())).await {
                        Err(f) if f.class == ErrClass::RateLimited && solo && n < 8 => { tokio::time::sleep(wait).await; wait = (wait * 2).min(Duration::from_secs(5)); }
                        r => break r,
                    }
                };
                {
                    let mut s = me.stats.lock().unwrap();
                    match &r {
                        Ok((_, _, lat)) => s.lat.entry((ep.name.clone(), m.clone())).or_default().push(lat.as_micros() as u64),
                        Err(e) => {
                            *s.errors.entry(ep.name.clone()).or_default() += 1;
                            let mut why = scrub(&e.msg);
                            why.truncate(200);
                            *s.why.entry((ep.name.clone(), why)).or_default() += 1;
                        }
                    }
                }
                let _ = tx.send((ep.name, r.map(|x| x.0))).await;
            });
        }
        drop(tx);
        self.stats.lock().unwrap().calls += 1;
        let mut last = None;
        while let Some((name, r)) = rx.recv().await {
            match r {
                Ok(v) => { *self.stats.lock().unwrap().wins.entry(name).or_default() += 1; return Ok(v); }
                Err(e) => last = Some(e),
            }
        }
        Err(last.map(anyhow::Error::new).unwrap_or_else(|| anyhow::anyhow!("rpc {method}: no providers")))
    }

    /// Resolve every provider's host (cached for the run) and open its connection with one `getSlot` (role `boot`);
    /// returns one run.log line per provider
    pub async fn prewarm(&self) -> Vec<String> {
        let me = self.with_role(Role::Boot);
        let mut notes = Vec::new();
        let body = json!({ "jsonrpc": "2.0", "id": 1, "method": "getSlot", "params": [{ "commitment": "processed" }] });
        for ep in self.eps.iter() {
            let t0 = Instant::now();
            let dns = match url_host(&ep.url) {
                Some(h) if h.parse::<std::net::IpAddr>().is_err() => match self.dns.prime(&h).await {
                    Ok(n) => format!("DNS {n} addresses in {:.1} ms", t0.elapsed().as_secs_f64() * 1e3),
                    Err(e) => format!("DNS failed ({e}): resolved per connection"),
                },
                _ => "no DNS (an address)".to_string(),
            };
            let t1 = Instant::now();
            crate::netcount::note();
            let first = match me.attempt(ep, &body, "getSlot", Duration::from_secs(5), Some(Instant::now() + Duration::from_secs(5))).await {
                Ok(_) => format!("first call {:.1} ms", t1.elapsed().as_secs_f64() * 1e3),
                Err(f) => format!("first call failed ({}: {})", f.class.as_str(), f.msg),
            };
            notes.push(format!("rpc {}: {dns}, {first}", ep.name));
        }
        notes
    }

    /// Keep the connections warm (on `rt`, until `stop`): every `every` (the run: 5 s), a `getSlot` (role `warm`, only
    /// with a token to spare) to any provider idle for `idle`, and the DNS cache re-resolved every 5 minutes
    pub fn start_warm(&self, rt: &tokio::runtime::Handle, stop: Arc<AtomicBool>, idle: Duration, every: Duration) -> tokio::task::JoinHandle<()> {
        let me = self.with_role(Role::Warm).with_own_phase(Phase::Run);
        rt.spawn(async move {
            let body = json!({ "jsonrpc": "2.0", "id": 1, "method": "getSlot", "params": [{ "commitment": "processed" }] });
            let mut last_dns = Instant::now();
            while !stop.load(Relaxed) {
                tokio::time::sleep(every).await;
                for ep in me.eps.iter() {
                    // only an idle provider, and only with a token to spare (a busy one is warm anyway)
                    let spare = me.reg.limiter(&ep.name).wait_hint(Role::Warm.priority(), Instant::now()).is_zero();
                    if spare && me.reg.idle_for(&ep.name).is_none_or(|d| d >= idle) {
                        crate::netcount::note();
                        let _ = me.attempt(ep, &body, "getSlot", Duration::from_secs(3), Some(Instant::now())).await;
                    }
                }
                if last_dns.elapsed() >= Duration::from_secs(300) { me.dns.refresh().await; last_dns = Instant::now(); }
            }
        })
    }

    /// the most common failure reasons per provider
    pub fn reasons(&self, per: usize) -> Vec<String> {
        let s = self.stats.lock().unwrap();
        let mut v: Vec<(&(String, String), &u64)> = s.why.iter().collect();
        v.sort_by(|a, b| a.0 .0.cmp(&b.0 .0).then(b.1.cmp(a.1)));
        let mut out = Vec::new();
        let mut last = String::new();
        let mut n = 0;
        for ((ep, why), c) in v {
            if *ep != last { last = ep.clone(); n = 0; }
            n += 1;
            if n <= per { out.push(format!("{ep}: {c} x {why}")); }
        }
        out
    }

    /// one line per provider: wins, errors, p50/p90 latency per method
    pub fn summary(&self) -> Vec<String> {
        let mut s = self.stats.lock().unwrap();
        let calls = s.calls.max(1);
        let names: Vec<String> = self.eps.iter().map(|e| e.name.clone()).collect();
        let mut out = Vec::new();
        for n in names {
            let wins = s.wins.get(&n).copied().unwrap_or(0);
            let errs = s.errors.get(&n).copied().unwrap_or(0);
            let mut parts = Vec::new();
            for ((ep, m), v) in s.lat.iter_mut() {
                if *ep != n || v.is_empty() { continue; }
                v.sort_unstable();
                let p = |q: f64| v[((v.len() - 1) as f64 * q).round() as usize] as f64 / 1000.0;
                parts.push(format!("{m} {:.1}/{:.1} ms ({})", p(0.5), p(0.9), v.len()));
            }
            out.push(format!("{n}: first {wins}/{calls} ({:.0}%), errors {errs}; {}", wins as f64 * 100.0 / calls as f64, parts.join(", ")));
        }
        out
    }

    /// getMultipleAccounts in batches of 100, processed commitment; returns (slot, accounts in order)
    pub async fn accounts(&self, keys: &[Pk]) -> Result<(u64, Vec<Option<Account>>)> {
        let mut out = Vec::with_capacity(keys.len());
        let mut slot = 0;
        for chunk in keys.chunks(100) {
            let ks: Vec<String> = chunk.iter().map(b58).collect();
            let r = self.call("getMultipleAccounts", json!([ks, { "encoding": "base64", "commitment": "processed" }])).await?;
            slot = slot.max(r["context"]["slot"].as_u64().unwrap_or(0));
            for v in r["value"].as_array().context("getMultipleAccounts: no value")? {
                out.push(parse_account(v));
            }
            // pace bulk fetches (public endpoints allow a few requests per second)
            if keys.len() > 100 { tokio::time::sleep(std::time::Duration::from_millis(120)).await; }
        }
        Ok((slot, out))
    }

    /// getMultipleAccounts of at most 100 keys, only bytes `[offset, offset + length)` of each (`dataSlice`): headers
    /// of large accounts (a programdata account's 45 bytes instead of megabytes); returns (slot, accounts in order)
    pub async fn accounts_slice(&self, keys: &[Pk], offset: usize, length: usize) -> Result<(u64, Vec<Option<Account>>)> {
        anyhow::ensure!(keys.len() <= 100, "accounts_slice takes at most 100 keys");
        let ks: Vec<String> = keys.iter().map(b58).collect();
        let r = self.call("getMultipleAccounts", json!([ks, { "encoding": "base64", "commitment": "processed", "dataSlice": { "offset": offset, "length": length } }])).await?;
        let slot = r["context"]["slot"].as_u64().unwrap_or(0);
        let out = r["value"].as_array().context("getMultipleAccounts: no value")?.iter().map(parse_account).collect();
        Ok((slot, out))
    }

    pub async fn slot(&self) -> Result<u64> { Ok(self.call("getSlot", json!([{ "commitment": "processed" }])).await?.as_u64().unwrap_or(0)) }

    pub async fn latest_blockhash(&self) -> Result<([u8; 32], u64)> {
        let r = self.call("getLatestBlockhash", json!([{ "commitment": "confirmed" }])).await?;
        let h = bs58::decode(r["value"]["blockhash"].as_str().context("no blockhash")?).into_vec()?;
        Ok((h.try_into().map_err(|_| anyhow::anyhow!("bad blockhash"))?, r["value"]["lastValidBlockHeight"].as_u64().unwrap_or(0)))
    }

    /// simulateTransaction (no signature check, replace blockhash); returns (err, units consumed, logs)
    pub async fn simulate(&self, tx: &[u8]) -> Result<(Option<Value>, Option<u64>, Vec<String>)> {
        let b64 = base64::engine::general_purpose::STANDARD.encode(tx);
        let r = self.call("simulateTransaction", json!([b64, { "encoding": "base64", "sigVerify": false, "replaceRecentBlockhash": true, "commitment": "processed" }])).await?;
        let v = &r["value"];
        let logs = v["logs"].as_array().map(|a| a.iter().filter_map(|l| l.as_str().map(String::from)).collect()).unwrap_or_default();
        Ok((if v["err"].is_null() { None } else { Some(v["err"].clone()) }, v["unitsConsumed"].as_u64(), logs))
    }

    /// simulateTransaction with everything the step-2 record needs: the slot simulated at, the error, units, logs
    pub async fn simulate_full(&self, tx: &[u8]) -> Result<Sim> {
        let b64 = base64::engine::general_purpose::STANDARD.encode(tx);
        let r = self.call("simulateTransaction", json!([b64, { "encoding": "base64", "sigVerify": false, "replaceRecentBlockhash": true, "commitment": "processed" }])).await?;
        let v = &r["value"];
        Ok(Sim { slot: r["context"]["slot"].as_u64().unwrap_or(0), err: if v["err"].is_null() { None } else { Some(v["err"].clone()) },
            units: v["unitsConsumed"].as_u64(),
            logs: v["logs"].as_array().map(|a| a.iter().filter_map(|l| l.as_str().map(String::from)).collect()).unwrap_or_default() })
    }

    /// getTransaction (confirmed, v0 allowed); None while the node doesn't have it
    pub async fn transaction(&self, sig: &str) -> Result<Option<Value>> {
        let r = self.call("getTransaction", json!([sig, { "encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed" }])).await?;
        Ok(if r.is_null() { None } else { Some(r) })
    }

    /// mints `owner` holds a token account for (SPL Token and Token-2022)
    pub async fn token_mints(&self, owner: &Pk) -> Result<std::collections::HashSet<Pk>> {
        let mut out = std::collections::HashSet::new();
        for prog in [*crate::pda::TOKEN_PROGRAM, *crate::pda::TOKEN_2022] {
            let r = self.call("getTokenAccountsByOwner", json!([b58(owner), { "programId": b58(&prog) }, { "encoding": "base64", "dataSlice": { "offset": 0, "length": 32 } }])).await?;
            for a in r["value"].as_array().into_iter().flatten() {
                if let Some(d) = a["account"]["data"][0].as_str().and_then(|d| base64::engine::general_purpose::STANDARD.decode(d).ok()) {
                    if let Ok(m) = Pk::try_from(d.as_slice()) { out.insert(m); }
                }
            }
        }
        Ok(out)
    }

    /// getSignatureStatuses as one bounded call (PLAN WP-05 item 2: the executor's run-time calls use `call_bounded`, never
    /// the 3 s failover or the 429 loop): per signature, None when the node does not know it. `search_history`: look past
    /// the recent status cache (the one check before an attempt is final, F43)
    pub async fn statuses_bounded(&self, sigs: &[[u8; 64]], search_history: bool, b: Bounds) -> std::result::Result<Vec<Option<SigStatus>>, RpcFailure> {
        let ss: Vec<String> = sigs.iter().map(|s| bs58::encode(s).into_string()).collect();
        let f = self.call_bounded("getSignatureStatuses", json!([ss, { "searchTransactionHistory": search_history }]), b).await?;
        let list = f.value["value"].as_array().cloned().unwrap_or_default();
        Ok((0..sigs.len()).map(|i| list.get(i).filter(|v| !v.is_null()).map(|v| SigStatus { slot: v["slot"].as_u64().unwrap_or(0),
            err: if v["err"].is_null() { None } else { Some(v["err"].clone()) }, confirmation: v["confirmationStatus"].as_str().map(String::from) })).collect())
    }

    /// simulateTransaction as one bounded call (read-only: nothing is broadcast). `sig_verify` false lets a transaction
    /// signed by another key than its payer simulate; `replace_blockhash` false checks the blockhash too
    pub async fn simulate_bounded(&self, tx: &[u8], sig_verify: bool, replace_blockhash: bool, b: Bounds) -> std::result::Result<Sim, RpcFailure> {
        let b64 = base64::engine::general_purpose::STANDARD.encode(tx);
        let f = self.call_bounded("simulateTransaction", json!([b64, { "encoding": "base64", "sigVerify": sig_verify, "replaceRecentBlockhash": replace_blockhash,
            "commitment": "processed" }]), b).await?;
        let (r, v) = (&f.value, &f.value["value"]);
        Ok(Sim { slot: r["context"]["slot"].as_u64().unwrap_or(0), err: if v["err"].is_null() { None } else { Some(v["err"].clone()) },
            units: v["unitsConsumed"].as_u64(),
            logs: v["logs"].as_array().map(|a| a.iter().filter_map(|l| l.as_str().map(String::from)).collect()).unwrap_or_default() })
    }

    /// getSignatureStatuses: (slot, ok) per signature, None if unknown
    pub async fn statuses(&self, sigs: &[[u8; 64]]) -> Result<Vec<Option<(u64, bool)>>> {
        let ss: Vec<String> = sigs.iter().map(|s| bs58::encode(s).into_string()).collect();
        let r = self.call("getSignatureStatuses", json!([ss, { "searchTransactionHistory": false }])).await?;
        Ok(r["value"].as_array().map(|a| a.iter().map(|v| if v.is_null() { None } else {
            Some((v["slot"].as_u64().unwrap_or(0), v["err"].is_null())) }).collect()).unwrap_or_default())
    }
}

/// One HTTP request and its classified outcome: the `result` (moved out of the reply, not copied) and the reply's size
async fn http_once(http: &reqwest::Client, ep: &Endpoint, body: &Value, method: &str) -> std::result::Result<(Value, usize), RpcFailure> {
    let name = ep.name.as_str();
    let mut req = http.post(&ep.url).json(body);
    if let Some(b) = &ep.bearer { req = req.header("authorization", format!("Bearer {b}")); }
    let resp = req.send().await.map_err(|e| {
        // the request never got an answer: a timeout, or a failed connection (connect, TLS, a reset before the reply)
        let class = if e.is_timeout() { ErrClass::Timeout } else if e.is_body() || e.is_decode() { ErrClass::Body } else { ErrClass::Transport };
        RpcFailure::new(class, Some(name), format!("{name} {method}: {e:#}"))
    })?;
    let status = resp.status().as_u16();
    if status == 429 {
        let mut f = RpcFailure::new(ErrClass::RateLimited, Some(name), format!("{name} {method}: rate limited (HTTP 429)"));
        f.status = Some(429);
        return Err(f);
    }
    let bytes = resp.bytes().await.map_err(|e| {
        let mut f = RpcFailure::new(if e.is_timeout() { ErrClass::Timeout } else { ErrClass::Body }, Some(name), format!("{name} {method}: reading reply: {e:#}"));
        f.status = Some(status);
        f
    })?;
    let n = bytes.len();
    let v: Value = match parse_reply(bytes.clone()).await {
        Ok(v) => v,
        Err(_) => {
            let text = String::from_utf8_lossy(&bytes);
            let snippet: String = text.chars().take(120).map(|c| if c.is_control() { ' ' } else { c }).collect();
            let class = if (200..300).contains(&status) { ErrClass::Body } else { ErrClass::Http };
            let mut f = RpcFailure::new(class, Some(name), format!("{name} {method}: HTTP {status} with a non-JSON reply ({n} bytes): {:?}", snippet.trim()));
            f.status = Some(status);
            return Err(f);
        }
    };
    if let Some(e) = v.get("error").filter(|e| !e.is_null()) {
        let code = e["code"].as_i64();
        let text = e["message"].as_str().map(String::from).unwrap_or_else(|| e.to_string());
        let low = text.to_ascii_lowercase();
        let limited = matches!(code, Some(429 | -32429)) || low.contains("rate limit") || low.contains("too many requests");
        let mut f = RpcFailure::new(if limited { ErrClass::RateLimited } else { ErrClass::Rpc }, Some(name), format!("{name} {method}: {e}"));
        f.status = Some(status);
        f.code = code;
        // an RPC error with an answer's code is not asked of the same provider again (`bounded` asks the others unless it is
        // a chain fact); a provider's trouble (internal errors, a node behind) and an error without a code (a gateway's
        // own message) are retried (review WP-03b #4)
        f.retryable = limited || code.is_none() || !code_is_answer(code);
        return Err(f);
    }
    if !(200..300).contains(&status) {
        let mut f = RpcFailure::new(ErrClass::Http, Some(name), format!("{name} {method}: HTTP {status}"));
        f.status = Some(status);
        return Err(f);
    }
    // a reply with neither a result nor an error (a gateway's own message) is not an answer: it must not win the race
    match v {
        Value::Object(mut m) if m.contains_key("result") => Ok((m.remove("result").unwrap_or(Value::Null), n)),
        other => Err(RpcFailure::new(ErrClass::NoResult, Some(name), format!("{name} {method}: no result in reply: {}", other.to_string().chars().take(120).collect::<String>()))),
    }
}

/// A reply's JSON: parsed in place when small, in `spawn_blocking` when over `runtime::LARGE_REPLY` bytes (a getBlock
/// or a big getMultipleAccounts: tens of ms of parsing that must not hold a runtime worker)
pub async fn parse_reply<B: AsRef<[u8]> + Send + 'static>(bytes: B) -> serde_json::Result<Value> {
    if bytes.as_ref().len() <= crate::runtime::LARGE_REPLY || tokio::runtime::Handle::try_current().is_err() { return serde_json::from_slice(bytes.as_ref()); }
    crate::runtime::BLOCKING_NOW.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    crate::runtime::LARGE_PARSES.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let r = tokio::task::spawn_blocking(move || { crate::runtime::check_not_hot("a large RPC reply's parse"); serde_json::from_slice(bytes.as_ref()) }).await;
    crate::runtime::BLOCKING_NOW.fetch_sub(1, std::sync::atomic::Ordering::Relaxed);
    match r { Ok(v) => v, Err(e) => Err(serde::de::Error::custom(format!("parse task: {e}"))) }
}

/// one simulateTransaction answer
#[derive(Debug, Clone)]
pub struct Sim { pub slot: u64, pub err: Option<Value>, pub units: Option<u64>, pub logs: Vec<String> }

/// one signature's status (`getSignatureStatuses`): the slot it landed in, its error (None: it succeeded) and the
/// commitment reached
#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct SigStatus { pub slot: u64, pub err: Option<Value>, pub confirmation: Option<String> }

impl SigStatus {
    /// ---- WP-09: read back as `Serialize` wrote it (journal INPUT 9 `settled` `statuses`: a replay hands it to its executor)
    pub fn from_json(v: &Value) -> Option<SigStatus> {
        Some(SigStatus { slot: v["slot"].as_u64()?, err: v.get("err").cloned().filter(|e| !e.is_null()), confirmation: v["confirmation"].as_str().map(String::from) })
    }
}

fn parse_account(v: &Value) -> Option<Account> {
    if v.is_null() { return None; }
    let data = base64::engine::general_purpose::STANDARD.decode(v["data"][0].as_str()?).ok()?;
    let owner: Pk = bs58::decode(v["owner"].as_str()?).into_vec().ok()?.try_into().ok()?;
    Some(Account { owner, lamports: v["lamports"].as_u64().unwrap_or(0), data })
}

/// Test support (review WP-04 #1): a JSON-RPC server on 127.0.0.1 that answers getMultipleAccounts from `accounts` at
/// `slot` (one HTTP/1.1 request per connection), so a run-level test reads accounts through the real client. While
/// `fail_next` is above 0 a call is answered HTTP 500 (and the counter goes down); a call naming an account of
/// `fail_keys` is answered HTTP 500 once (the account leaves the set)
#[cfg(test)]
pub(crate) mod mock {
    use super::*;
    use std::io::{Read, Write};
    use std::sync::atomic::{AtomicBool, AtomicU64, Ordering::Relaxed};
    use std::sync::{Arc, Mutex};

    pub struct MockRpc {
        pub url: String,
        /// account -> (data, owner, lamports)
        pub accounts: Arc<Mutex<std::collections::HashMap<Pk, (Vec<u8>, Pk, u64)>>>,
        pub slot: Arc<AtomicU64>,
        pub fail_next: Arc<AtomicU64>,
        pub fail_keys: Arc<Mutex<std::collections::HashSet<Pk>>>,
        pub calls: Arc<AtomicU64>,
        /// every request, in order (`{"method", "params", ...}`)
        pub reqs: Arc<Mutex<Vec<Value>>>,
        stop: Arc<AtomicBool>,
        addr: std::net::SocketAddr,
    }

    impl MockRpc {
        pub fn start() -> MockRpc {
            let l = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
            let addr = l.local_addr().unwrap();
            let m = MockRpc { url: format!("http://{addr}"), accounts: Default::default(), slot: Arc::new(AtomicU64::new(0)), fail_next: Default::default(),
                fail_keys: Default::default(), calls: Default::default(), reqs: Default::default(), stop: Default::default(), addr };
            let (accounts, slot, fail, fail_keys, calls, stop) = (m.accounts.clone(), m.slot.clone(), m.fail_next.clone(), m.fail_keys.clone(), m.calls.clone(), m.stop.clone());
            let reqs = m.reqs.clone();
            std::thread::spawn(move || {
                for c in l.incoming() {
                    if stop.load(Relaxed) { break; }
                    let Ok(mut c) = c else { continue };
                    let _ = c.set_read_timeout(Some(std::time::Duration::from_secs(5)));
                    let mut buf = Vec::new();
                    let mut b = [0u8; 4096];
                    // the headers, then Content-Length bytes of body
                    let body = loop {
                        let Ok(n) = c.read(&mut b) else { break None };
                        if n == 0 { break None; }
                        buf.extend_from_slice(&b[..n]);
                        let Some(h) = buf.windows(4).position(|w| w == b"\r\n\r\n") else { continue };
                        let head = String::from_utf8_lossy(&buf[..h]).to_ascii_lowercase();
                        let len: usize = head.lines().find_map(|l| l.strip_prefix("content-length:").map(|v| v.trim().parse().unwrap_or(0))).unwrap_or(0);
                        if buf.len() >= h + 4 + len { break Some(buf[h + 4..h + 4 + len].to_vec()); }
                    };
                    let Some(body) = body else { continue };
                    calls.fetch_add(1, Relaxed);
                    let req: Value = serde_json::from_slice(&body).unwrap_or(Value::Null);
                    reqs.lock().unwrap().push(req.clone());
                    let named: Vec<Pk> = req["params"][0].as_array().into_iter().flatten().filter_map(|k| k.as_str())
                        .filter_map(|s| bs58::decode(s).into_vec().ok()?.try_into().ok()).collect();
                    let key_fail = { let mut f = fail_keys.lock().unwrap(); let hit = named.iter().find(|k| f.contains(*k)).copied(); if let Some(k) = hit { f.remove(&k); } hit.is_some() };
                    let (status, reply) = if key_fail || fail.load(Relaxed) > 0 {
                        if !key_fail { fail.fetch_sub(1, Relaxed); }
                        ("500 Internal Server Error", "upstream error".to_string())
                    } else {
                        let accts = accounts.lock().unwrap();
                        let value: Vec<Value> = req["params"][0].as_array().into_iter().flatten().map(|k| {
                            let key: Option<Pk> = k.as_str().and_then(|s| bs58::decode(s).into_vec().ok()).and_then(|v| v.try_into().ok());
                            match key.and_then(|k| accts.get(&k)) {
                                Some((data, owner, lamports)) => json!({ "data": [base64::engine::general_purpose::STANDARD.encode(data), "base64"], "owner": b58(owner),
                                    "lamports": lamports, "executable": false, "rentEpoch": 0 }),
                                None => Value::Null,
                            }
                        }).collect();
                        ("200 OK", json!({ "jsonrpc": "2.0", "id": req["id"], "result": { "context": { "slot": slot.load(Relaxed) }, "value": value } }).to_string())
                    };
                    let _ = write!(c, "HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{reply}", reply.len());
                    let _ = c.flush();
                }
            });
            m
        }
        pub fn set(&self, k: Pk, data: &[u8]) { self.accounts.lock().unwrap().insert(k, (data.to_vec(), [3; 32], 1)); }
    }

    impl Drop for MockRpc {
        fn drop(&mut self) { self.stop.store(true, Relaxed); let _ = std::net::TcpStream::connect(self.addr); }
    }

    /// the mock through the real client: accounts, the context slot, a failing call
    #[tokio::test(flavor = "multi_thread", worker_threads = 1)]
    async fn the_mock_answers_get_multiple_accounts() {
        let m = MockRpc::start();
        m.set([1; 32], &[9, 8, 7]);
        m.slot.store(77, Relaxed);
        let rpc = Rpc::race(vec![Endpoint { name: "mock".into(), url: m.url.clone(), bearer: None }]);
        let (slot, v) = rpc.accounts(&[[1; 32], [2; 32]]).await.unwrap();
        assert_eq!((slot, v[0].as_ref().map(|a| a.data.clone()), v[1].is_none()), (77, Some(vec![9, 8, 7]), true));
        m.fail_next.store(1, Relaxed);
        assert!(rpc.accounts(&[[1; 32]]).await.is_err());
        assert!(rpc.accounts(&[[1; 32]]).await.is_ok());
        m.fail_keys.lock().unwrap().insert([2; 32]);
        assert!(rpc.accounts(&[[1; 32]]).await.is_ok(), "a call not naming it");
        assert!(rpc.accounts(&[[1; 32], [2; 32]]).await.is_err());
        assert!(rpc.accounts(&[[2; 32]]).await.is_ok(), "once");
        assert_eq!(m.calls.load(Relaxed), 6);
    }
}

#[cfg(test)]
pub(crate) mod tests;
