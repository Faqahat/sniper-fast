//! A path's rate budget (arbed's `rateWindow` and `createBundleBudget`): at most `per_sec` sends in any rolling second.
//! With the budget full a send waits up to `max_wait` for a slot, and freed slots go to the waiting sends best first
//! (lower `Prio::rank`, then higher expected profit). `max_wait` zero refuses at once: a queued trade would be stale.
use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::time::Instant;
use tokio::sync::oneshot;

/// Which send goes first when the budget is short: the lower rank first (0 = the seed pools), then the higher profit.
#[derive(Clone, Copy, Debug, Default)]
pub struct Prio { pub rank: u8, pub net: i64 }

/// `Prio::rank` values: a seed (Mriya-sourced) pool on the route, any other route, and (WP-00, F6) a route touching a
/// pool with 150 or more arbitrage bots, which queues behind both
pub const RANK_SEED: u8 = 0;
pub const RANK_OTHER: u8 = 1;
pub const RANK_CROWDED: u8 = 2;

impl Prio {
    /// ranked last because a pool of the route is on the crowded list (its rate drops are counted apart)
    pub fn crowded(&self) -> bool { self.rank >= RANK_CROWDED }
}

/// A token bucket: `rate` tokens a second, holding at most `burst`; it starts full. WP-00's big-band throttle (live
/// trades expecting 1M or more: 0.5/s, burst 1). Integer arithmetic (a token is 10^12 units, the rate is kept to
/// 0.001 token/s: a rate under 0.0005/s is 0), so the refill is exact. Single-threaded (the engine thread owns it); times are ns.
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
}

struct Waiter { prio: Prio, seq: u64, done: oneshot::Sender<()> }

#[derive(Default)]
struct State { recent: VecDeque<Instant>, waiting: Vec<Waiter>, seq: u64, pumping: bool }

pub struct Budget { per_sec: usize, max_wait: Duration, st: Arc<Mutex<State>> }

const WINDOW: Duration = Duration::from_secs(1);

fn take(s: &mut State, per_sec: usize, now: Instant) -> bool {
    while s.recent.front().is_some_and(|t| now.duration_since(*t) >= WINDOW) { s.recent.pop_front(); }
    if s.recent.len() >= per_sec { return false; }
    s.recent.push_back(now);
    true
}

impl Budget {
    pub fn new(per_sec: u32, max_wait: Duration) -> Budget {
        Budget { per_sec: per_sec.max(1) as usize, max_wait, st: Default::default() }
    }

    pub fn per_sec(&self) -> usize { self.per_sec }

    /// a slot now if one is free and nobody waits (keep-alive calls use this: they never take a trade's room)
    pub fn try_now(&self) -> bool {
        let mut s = self.st.lock().unwrap();
        s.waiting.is_empty() && take(&mut s, self.per_sec, Instant::now())
    }

    /// a slot now, or within `max_wait` (best first); false = over the limit, do not send
    pub async fn acquire(&self, prio: Prio) -> bool {
        let (rx, seq) = {
            let mut s = self.st.lock().unwrap();
            if s.waiting.is_empty() && take(&mut s, self.per_sec, Instant::now()) { return true; }
            if self.max_wait.is_zero() { return false; }
            let (tx, rx) = oneshot::channel();
            s.seq += 1;
            let seq = s.seq;
            s.waiting.push(Waiter { prio, seq, done: tx });
            if !s.pumping { s.pumping = true; tokio::spawn(pump(self.st.clone(), self.per_sec)); }
            (rx, seq)
        };
        match tokio::time::timeout(self.max_wait, rx).await {
            Ok(Ok(())) => true,
            _ => {
                // still queued: give up; already removed: the pump granted it as the wait ran out
                let mut s = self.st.lock().unwrap();
                match s.waiting.iter().position(|w| w.seq == seq) { Some(i) => { s.waiting.remove(i); false } None => true }
            }
        }
    }
}

/// hand freed slots to the waiting sends, best first, until nobody waits
async fn pump(st: Arc<Mutex<State>>, per_sec: usize) {
    loop {
        let next = {
            let mut s = st.lock().unwrap();
            s.waiting.retain(|w| !w.done.is_closed());
            s.waiting.sort_by(|a, b| a.prio.rank.cmp(&b.prio.rank).then(b.prio.net.cmp(&a.prio.net)).then(a.seq.cmp(&b.seq)));
            while !s.waiting.is_empty() && take(&mut s, per_sec, Instant::now()) {
                let w = s.waiting.remove(0);
                let _ = w.done.send(());
            }
            if s.waiting.is_empty() { s.pumping = false; return; }
            match s.recent.front() { Some(t) => *t + WINDOW, None => Instant::now() }
        };
        tokio::time::sleep_until(next).await;
    }
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

    /// review F5: peeking takes nothing, and agrees with the next take
    #[test]
    fn token_bucket_peek_takes_nothing() {
        let t0 = 1_000 * S;
        let mut b = TokenBucket::new(0.5, 1);
        for _ in 0..3 { assert!(b.peek(t0)); }
        assert!(b.try_take(t0));
        assert!(!b.peek(t0) && !b.peek(t0 + S));
        assert!(b.peek(t0 + 2 * S));
        assert!(b.peek(t0 + 2 * S), "still there: a peek is not a take");
        assert!(b.try_take(t0 + 2 * S));
        assert!(!b.peek(t0 + 2 * S));
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
        assert!(b.acquire(Prio::default()).await);
        assert!(b.try_now());
        assert!(!b.acquire(Prio::default()).await, "third in the same second is refused");
        tokio::time::advance(Duration::from_millis(1_001)).await;
        assert!(b.acquire(Prio::default()).await);
    }

    #[tokio::test(start_paused = true)]
    async fn waiting_sends_are_served_best_first() {
        let b = Arc::new(Budget::new(1, Duration::from_millis(1_500)));
        assert!(b.acquire(Prio::default()).await);
        let order = Arc::new(Mutex::new(Vec::new()));
        let mut hs = Vec::new();
        for (name, prio) in [("ours-small", Prio { rank: 1, net: 10 }), ("seed", Prio { rank: 0, net: 1 }), ("ours-big", Prio { rank: 1, net: 99 })] {
            let (b, order) = (b.clone(), order.clone());
            hs.push(tokio::spawn(async move { if b.acquire(prio).await { order.lock().unwrap().push(name); } }));
            tokio::task::yield_now().await;
        }
        for h in hs { h.await.unwrap(); }
        // one slot a second, 1.5 s of patience: the best waiter gets the slot at 1 s, the next one is refused at 1.5 s
        assert_eq!(*order.lock().unwrap(), vec!["seed"]);
        assert!(!b.try_now(), "the granted slot is still in the window");
    }
}
