//! A path's rate budget (arbed's `rateWindow` and `createBundleBudget`): at most `per_sec` sends in any rolling second.
//! With the budget full a send waits up to `max_wait` (`[send_policy] queue_ms` for the bundle path) for a slot, and
//! freed slots go to the waiting sends best first (PLAN WP-05 item 5): the band rank first (every band under 1M before
//! the ≥1M class), then the crowding rank (a pool in the ≥150-signer bucket behind the others of its band), then the
//! higher EV, then the earlier send. A send still waiting at `max_wait` is dropped: `crowded_pool` when a less crowded
//! send of its band took a slot while it waited, else `rate_queue_timeout`. While 4 or more sends wait, the lowest EV
//! among them is λ, the shadow price of a send slot (the Stage-2 Selector's input). `max_wait` zero refuses at once.
use std::collections::VecDeque;
use std::sync::atomic::{AtomicI64, Ordering::Relaxed};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::sync::oneshot;
use tokio::time::Instant;

/// Which send goes first when the budget is short: `band` (0: bands 0-2, 1: the ≥1M class; src/bands.rs), then `crowd`
/// (1: a pool of the route is in the ≥150-signer bucket), then the higher `ev` (expected net, lamports)
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Prio { pub band: u8, pub crowd: u8, pub ev: i64 }

impl Prio {
    /// ranked behind its band's others because a pool of the route is crowded (its rate drops are counted apart)
    pub fn crowded(&self) -> bool { self.crowd > 0 }
    /// one sortable queue rank (decisions.jsonl `rank`): 0 small, 1 small crowded, 2 big, 3 big crowded
    pub fn rank(&self) -> u8 { self.band.min(1) * 2 + self.crowd.min(1) }
    /// the queue order: lower is served first
    fn key(&self) -> (u8, u8, std::cmp::Reverse<i64>) { (self.band, self.crowd, std::cmp::Reverse(self.ev)) }
}

/// A token bucket: `rate` tokens a second, holding at most `burst`; it starts full. The ≥1M class's throttle
/// (`[send_policy] big_band_max_per_sec`, burst 1). Integer arithmetic (a token is 10^12 units, the rate is kept to 0.001
/// token/s: a rate under 0.0005/s is 0), so the refill is exact. Single-threaded (the engine thread owns it); times are ns.
#[derive(Clone, Debug)]
pub struct TokenBucket { per_ns: u128, cap: u128, units: u128, last_ns: Option<u64> }

const TOKEN: u128 = 1_000_000_000_000;

impl TokenBucket {
    pub fn new(rate_per_sec: f64, burst: u32) -> TokenBucket {
        // units per ns = rate * 10^12 / 10^9
        let per_ns = if rate_per_sec.is_finite() && rate_per_sec > 0.0 { (rate_per_sec * 1_000.0).round() as u128 } else { 0 };
        let cap = burst as u128 * TOKEN;
        // rate 0 = never: no token at the start either
        TokenBucket { per_ns, cap, units: if per_ns > 0 { cap } else { 0 }, last_ns: None }
    }

    /// the units held at `now_ns` (a clock that goes backwards refills nothing)
    fn units_at(&self, now_ns: u64) -> u128 {
        match self.last_ns {
            Some(last) => self.units.saturating_add((now_ns.saturating_sub(last) as u128).saturating_mul(self.per_ns)).min(self.cap),
            None => self.units,
        }
    }

    /// would `try_take(now_ns)` succeed? (takes nothing: WP-00 review F5, the token is used only once the attempt goes)
    pub fn peek(&self, now_ns: u64) -> bool { self.units_at(now_ns) >= TOKEN }

    /// take one token at `now_ns` if there is one
    pub fn try_take(&mut self, now_ns: u64) -> bool {
        self.units = self.units_at(now_ns);
        if self.last_ns.map_or(true, |l| now_ns > l) { self.last_ns = Some(now_ns); }
        if self.units >= TOKEN { self.units -= TOKEN; true } else { false }
    }

    /// give back a token taken by a send that never left (WP-00 review F5's residual: a bundle dropped from the rate
    /// queue); never above the burst
    pub fn refund(&mut self, now_ns: u64) {
        self.units = self.units_at(now_ns).saturating_add(TOKEN).min(self.cap);
        if self.last_ns.map_or(true, |l| now_ns > l) { self.last_ns = Some(now_ns); }
    }
}

/// Why a send got no slot
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Drop {
    /// waited `max_wait` (or `max_wait` is 0 and the budget was full)
    Timeout,
    /// waited `max_wait` while a less crowded send of its band took a slot
    Crowded,
}

impl Drop {
    /// the decision reason (MEASUREMENT A.1, send slot)
    pub fn reason(self) -> &'static str { match self { Drop::Timeout => "rate_queue_timeout", Drop::Crowded => "crowded_pool" } }
}

/// A slot was granted after waiting this long
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Granted { pub waited: Duration }

struct Waiter { prio: Prio, seq: u64, done: oneshot::Sender<()>, overtaken: bool, deadline: Instant }

/// a waiter whose `acquire` is gone (its task was dropped before its own timeout ran) is removed this long after its
/// deadline
const ABANDONED: Duration = Duration::from_secs(1);

#[derive(Default)]
struct State { recent: VecDeque<Instant>, waiting: Vec<Waiter>, seq: u64, pumping: bool }

pub struct Budget { per_sec: usize, max_wait: Duration, st: Arc<Mutex<State>>, lambda: Arc<AtomicI64> }

const WINDOW: Duration = Duration::from_secs(1);
/// λ is defined while at least this many sends wait
pub const LAMBDA_MIN_WAITING: usize = 4;
const NO_LAMBDA: i64 = i64::MIN;

fn take(s: &mut State, per_sec: usize, now: Instant) -> bool {
    while s.recent.front().is_some_and(|t| now.duration_since(*t) >= WINDOW) { s.recent.pop_front(); }
    if s.recent.len() >= per_sec { return false; }
    s.recent.push_back(now);
    true
}

/// λ: the lowest EV among the waiting sends when at least `LAMBDA_MIN_WAITING` wait
fn lambda_of(s: &State) -> i64 {
    let open: Vec<i64> = s.waiting.iter().filter(|w| !w.done.is_closed()).map(|w| w.prio.ev).collect();
    if open.len() < LAMBDA_MIN_WAITING { return NO_LAMBDA; }
    open.into_iter().min().unwrap_or(NO_LAMBDA)
}

/// a waiter still waiting: its `acquire` has not timed out (one that has removes it and reports its drop; review WP-05 #11)
fn open_waiters(s: &State) -> bool { s.waiting.iter().any(|w| !w.done.is_closed()) }

/// waiters whose `acquire` is gone (its task was dropped before its own timeout ran) go a second past their deadline
fn forget_abandoned(s: &mut State, now: Instant) { s.waiting.retain(|w| !(w.done.is_closed() && now >= w.deadline + ABANDONED)); }

impl Budget {
    pub fn new(per_sec: u32, max_wait: Duration) -> Budget {
        Budget { per_sec: per_sec.max(1) as usize, max_wait, st: Default::default(), lambda: Arc::new(AtomicI64::new(NO_LAMBDA)) }
    }

    pub fn per_sec(&self) -> usize { self.per_sec }
    pub fn max_wait(&self) -> Duration { self.max_wait }

    /// a slot now if one is free and nobody waits (keep-alive calls use this: they never take a trade's room)
    pub fn try_now(&self) -> bool {
        let mut s = self.st.lock().unwrap();
        let now = Instant::now();
        forget_abandoned(&mut s, now);
        !open_waiters(&s) && take(&mut s, self.per_sec, now)
    }

    /// sends waiting for a slot now (status `exec.queue_now`)
    pub fn waiting(&self) -> usize { self.st.lock().unwrap().waiting.iter().filter(|w| !w.done.is_closed()).count() }

    /// λ now: the lowest EV of the waiting sends while at least 4 wait (status `exec.lambda_now`)
    pub fn lambda(&self) -> Option<i64> { Some(self.lambda.load(Relaxed)).filter(|l| *l != NO_LAMBDA) }

    /// a slot now, or within `max_wait` (best first); Err: dropped, and why
    pub async fn acquire(&self, prio: Prio) -> Result<Granted, Drop> {
        let t0 = Instant::now();
        let (rx, seq) = {
            let mut s = self.st.lock().unwrap();
            forget_abandoned(&mut s, t0);
            if !open_waiters(&s) && take(&mut s, self.per_sec, t0) { return Ok(Granted { waited: Duration::ZERO }); }
            if self.max_wait.is_zero() { return Err(Drop::Timeout); }
            let (tx, rx) = oneshot::channel();
            s.seq += 1;
            let seq = s.seq;
            s.waiting.push(Waiter { prio, seq, done: tx, overtaken: false, deadline: t0 + self.max_wait });
            self.lambda.store(lambda_of(&s), Relaxed);
            if !s.pumping { s.pumping = true; tokio::spawn(pump(self.st.clone(), self.per_sec, self.lambda.clone())); }
            (rx, seq)
        };
        match tokio::time::timeout(self.max_wait, rx).await {
            Ok(Ok(())) => Ok(Granted { waited: t0.elapsed() }),
            _ => {
                // still queued: give up (the pump leaves a waiter whose receiver is gone for this to remove and report);
                // already removed: the pump took a slot for it as the wait ran out (it removes only the waiters it
                // grants: review WP-05 #11)
                let mut s = self.st.lock().unwrap();
                match s.waiting.iter().position(|w| w.seq == seq) {
                    Some(i) => {
                        let w = s.waiting.remove(i);
                        self.lambda.store(lambda_of(&s), Relaxed);
                        Err(if w.overtaken { Drop::Crowded } else { Drop::Timeout })
                    }
                    None => Ok(Granted { waited: t0.elapsed() }),
                }
            }
        }
    }
}

/// hand freed slots to the waiting sends, best first, until nobody waits
async fn pump(st: Arc<Mutex<State>>, per_sec: usize, lambda: Arc<AtomicI64>) {
    loop {
        let next = {
            let mut s = st.lock().unwrap();
            let next = grant(&mut s, per_sec, Instant::now());
            lambda.store(lambda_of(&s), Relaxed);
            match next { Some(n) => n, None => { s.pumping = false; return; } }
        };
        tokio::time::sleep_until(next).await;
    }
}

/// One round of the pump at `now`: free slots go to the waiting sends, best first. A crowded waiter passed over for a
/// less crowded one of its band is marked (its drop, if it comes, is `crowded_pool`). A waiter whose receiver is gone
/// (its `acquire` timed out and is about to remove it and report the drop) is skipped, never granted nor removed, so an
/// `acquire` that finds its waiter gone was granted (review WP-05 #11); one abandoned past its deadline (its task was
/// dropped) is removed. Returns when to run again (None: no send waits, the pump stops)
fn grant(s: &mut State, per_sec: usize, now: Instant) -> Option<Instant> {
    forget_abandoned(s, now);
    s.waiting.sort_by(|a, b| a.prio.key().cmp(&b.prio.key()).then(a.seq.cmp(&b.seq)));
    let mut i = 0;
    while i < s.waiting.len() {
        if s.waiting[i].done.is_closed() { i += 1; continue; }
        if !take(s, per_sec, now) { break; }
        let w = s.waiting.remove(i);
        if w.prio.crowd == 0 {
            for o in s.waiting.iter_mut().filter(|o| o.prio.band == w.prio.band && o.prio.crowd > 0) { o.overtaken = true; }
        }
        let _ = w.done.send(());
    }
    // a send still waiting waits for the window to free a slot
    open_waiters(s).then(|| s.recent.front().map_or(now, |t| *t + WINDOW))
}

#[cfg(test)]
mod tests {
    use super::*;

    const S: u64 = 1_000_000_000;

    /// WP-00 acceptance: the big-band bucket allows 0.5 a second with a burst of 1
    #[test]
    fn token_bucket_rate_and_burst_one() {
        let t0 = 1_000 * S;
        let mut b = TokenBucket::new(0.5, 1);
        assert!(b.try_take(t0), "starts full: the first big trade goes");
        assert!(!b.try_take(t0), "burst 1: a second one at once is refused");
        assert!(!b.try_take(t0 + S), "1 s later only half a token has come back");
        assert!(!b.try_take(t0 + 2 * S - 1), "still short of a token just before 2 s");
        assert!(b.try_take(t0 + 2 * S), "a token every 2 s");
        assert!(!b.try_take(t0 + 2 * S + S / 2));
        // a long quiet spell never stores more than the burst
        assert!(b.try_take(t0 + 100 * S));
        assert!(!b.try_take(t0 + 100 * S), "burst 1 after 98 s idle");
        // over 60 s of constant demand: 30 tokens at 0.5/s
        let mut b = TokenBucket::new(0.5, 1);
        let mut n = 0;
        let mut t = t0;
        while t < t0 + 60 * S { if b.try_take(t) { n += 1; } t += S / 100; }
        assert_eq!(n, 30, "0.5/s over 60 s, the first from the full bucket");
        // a clock going backwards neither refills nor panics
        let mut b = TokenBucket::new(0.5, 1);
        assert!(b.try_take(t0));
        assert!(!b.try_take(t0 - S));
        assert!(!b.try_take(t0 + S));
        assert!(b.try_take(t0 + 2 * S));
    }

    /// review F5: peeking takes nothing, and agrees with the next take; WP-00 F5's residual: a refund gives the token
    /// back (never above the burst)
    #[test]
    fn token_bucket_peek_takes_nothing_and_refunds() {
        let t0 = 1_000 * S;
        let mut b = TokenBucket::new(0.5, 1);
        for _ in 0..3 { assert!(b.peek(t0)); }
        assert!(b.try_take(t0));
        assert!(!b.peek(t0) && !b.peek(t0 + S));
        assert!(b.peek(t0 + 2 * S));
        assert!(b.peek(t0 + 2 * S), "still there: a peek is not a take");
        assert!(b.try_take(t0 + 2 * S));
        assert!(!b.peek(t0 + 2 * S));
        b.refund(t0 + 2 * S);
        assert!(b.peek(t0 + 2 * S), "the dropped send's token is back");
        b.refund(t0 + 2 * S);
        assert!(b.try_take(t0 + 2 * S) && !b.try_take(t0 + 2 * S), "a refund never stores more than the burst");
    }

    #[test]
    fn token_bucket_rate_zero_never_allows() {
        let mut b = TokenBucket::new(0.0, 1);
        assert!(!b.try_take(S));
        assert!(!b.try_take(1_000 * S));
    }

    #[tokio::test(start_paused = true)]
    async fn at_most_n_in_a_rolling_second() {
        let b = Budget::new(2, Duration::ZERO);
        assert!(b.acquire(Prio::default()).await.is_ok());
        assert!(b.try_now());
        assert_eq!(b.acquire(Prio::default()).await, Err(Drop::Timeout), "third in the same second is refused");
        tokio::time::advance(Duration::from_millis(1_001)).await;
        assert!(b.acquire(Prio::default()).await.is_ok());
    }

    /// run `prios` (name, prio) against a 1/s budget whose slot of this second is taken, each waiting `wait`; returns the
    /// order they were served and each one's result
    async fn race(wait: Duration, prios: Vec<(&'static str, Prio)>) -> (Vec<&'static str>, Vec<(&'static str, Result<Granted, Drop>)>) {
        let b = Arc::new(Budget::new(1, wait));
        assert!(b.acquire(Prio::default()).await.is_ok());
        let order = Arc::new(Mutex::new(Vec::new()));
        let mut hs = Vec::new();
        for (name, prio) in prios {
            let (b, order) = (b.clone(), order.clone());
            hs.push(tokio::spawn(async move { let r = b.acquire(prio).await; if r.is_ok() { order.lock().unwrap().push(name); } (name, r) }));
            tokio::task::yield_now().await;
        }
        let mut res = Vec::new();
        for h in hs { res.push(h.await.unwrap()); }
        let o = order.lock().unwrap().clone();
        (o, res)
    }

    /// PLAN WP-05 acceptance (queue order, under tokio's paused clock): every band under 1M before the ≥1M class, within
    /// a band the crowded pools behind the others, then the higher EV; one slot a second
    #[tokio::test(start_paused = true)]
    async fn the_queue_orders_by_band_then_crowding_then_ev() {
        let p = |band: u8, crowd: u8, ev: i64| Prio { band, crowd, ev };
        let (order, _) = race(Duration::from_millis(5_500), vec![("big", p(1, 0, 9_000_000)), ("crowded-small", p(0, 1, 900_000)), ("small-low", p(0, 0, 10)),
            ("small-high", p(0, 0, 50_000)), ("big-crowded", p(1, 1, 50_000_000))]).await;
        assert_eq!(order, vec!["small-high", "small-low", "crowded-small", "big", "big-crowded"]);
        assert_eq!((p(0, 0, 1).rank(), p(0, 1, 1).rank(), p(1, 0, 1).rank(), p(1, 1, 1).rank()), (0, 1, 2, 3));
    }

    /// `queue_ms` (WP-00 review: brought back with a test at the configured queue): a send that waits past it is dropped,
    /// `crowded_pool` when a less crowded send of its band took the slot it waited for, else `rate_queue_timeout`
    #[tokio::test(start_paused = true)]
    async fn queue_drops_say_why() {
        let p = |band: u8, crowd: u8, ev: i64| Prio { band, crowd, ev };
        // one slot a second, 10 ms of patience: nobody gets a slot within 10 ms of a full window
        let (order, res) = race(Duration::from_millis(10), vec![("crowded", p(0, 1, 5)), ("plain", p(0, 0, 1))]).await;
        assert!(order.is_empty());
        assert_eq!(res, vec![("crowded", Err(Drop::Timeout)), ("plain", Err(Drop::Timeout))], "no slot came: nobody overtook anybody");
        // 1.5 s of patience: the plain send takes the slot at 1 s; the crowded one, passed over, is dropped at 1.5 s
        let (order, res) = race(Duration::from_millis(1_500), vec![("crowded", p(0, 1, 500)), ("plain", p(0, 0, 1)), ("big-crowded", p(1, 1, 7))]).await;
        assert_eq!(order, vec!["plain"]);
        assert_eq!(res[0], ("crowded", Err(Drop::Crowded)), "its crowding rank put it behind");
        assert_eq!(res[2], ("big-crowded", Err(Drop::Timeout)), "another band: the plain send did not overtake it");
        assert_eq!(Drop::Crowded.reason(), "crowded_pool");
        assert_eq!(Drop::Timeout.reason(), "rate_queue_timeout");
    }

    /// review WP-05 #11: a waiter whose `acquire` timed out (its receiver dropped) before it locks the queue is neither
    /// granted nor removed by the pump: the slot goes to the next waiter, and that `acquire` finds its waiter and reports
    /// the drop (it used to be removed, and its `acquire` then reported a slot it never got). One abandoned (its task
    /// dropped) is removed a second past its deadline
    #[test]
    fn a_timed_out_waiter_is_left_for_its_acquire() {
        let t0 = Instant::now();
        let mut s = State::default();
        s.recent.push_back(t0);
        let (late_tx, late_rx) = oneshot::channel();
        let (next_tx, mut next_rx) = oneshot::channel();
        s.waiting.push(Waiter { prio: Prio { band: 0, crowd: 0, ev: 9 }, seq: 1, done: late_tx, overtaken: false, deadline: t0 + Duration::from_millis(10) });
        s.waiting.push(Waiter { prio: Prio { band: 0, crowd: 0, ev: 1 }, seq: 2, done: next_tx, overtaken: false, deadline: t0 + Duration::from_millis(10) });
        drop(late_rx);   // its acquire's timeout ran: the receiver is gone, it has not locked the queue yet
        assert_eq!(grant(&mut s, 1, t0 + Duration::from_millis(500)), Some(t0 + WINDOW), "the window is full");
        assert_eq!(s.waiting.len(), 2);
        assert_eq!(lambda_of(&s), NO_LAMBDA);
        assert_eq!(grant(&mut s, 1, t0 + WINDOW), None, "the slot went to the next waiter; no send waits: the pump stops");
        assert!(next_rx.try_recv().is_ok());
        assert_eq!(s.waiting.iter().map(|w| w.seq).collect::<Vec<_>>(), vec![1], "the timed-out waiter is left for its acquire to report");
        assert_eq!(s.recent.len(), 1, "one slot taken, for the waiter that got it");
        assert!(!open_waiters(&s), "it does not hold the next send back");
        forget_abandoned(&mut s, t0 + Duration::from_millis(10) + ABANDONED);
        assert!(s.waiting.is_empty(), "abandoned (its acquire never came back): removed");
        // through the budget: a waiter left behind by a dropped task neither blocks a free slot nor counts as waiting
        let b = Budget::new(1, Duration::from_millis(10));
        let (tx, rx) = oneshot::channel();
        drop(rx);
        b.st.lock().unwrap().waiting.push(Waiter { prio: Prio::default(), seq: 9, done: tx, overtaken: false, deadline: t0 });
        assert_eq!(b.waiting(), 0);
        assert!(b.try_now(), "a free slot is taken at once");
    }

    /// λ: the lowest EV among the waiting sends, only while 4 or more wait (PLAN WP-05 item 5)
    #[tokio::test(start_paused = true)]
    async fn lambda_is_the_lowest_waiting_ev_from_four() {
        let b = Arc::new(Budget::new(1, Duration::from_secs(5)));
        assert!(b.acquire(Prio::default()).await.is_ok());
        assert_eq!((b.waiting(), b.lambda()), (0, None));
        let mut hs = Vec::new();
        for ev in [700i64, 300, 900] {
            let b = b.clone();
            hs.push(tokio::spawn(async move { b.acquire(Prio { band: 0, crowd: 0, ev }).await }));
            tokio::task::yield_now().await;
        }
        assert_eq!((b.waiting(), b.lambda()), (3, None), "three wait: no lambda");
        let b2 = b.clone();
        hs.push(tokio::spawn(async move { b2.acquire(Prio { band: 1, crowd: 0, ev: 5_000 }).await }));
        tokio::task::yield_now().await;
        assert_eq!((b.waiting(), b.lambda()), (4, Some(300)));
        for h in hs { let _ = h.await; }
        assert_eq!(b.lambda(), None, "nobody waits");
    }
}
