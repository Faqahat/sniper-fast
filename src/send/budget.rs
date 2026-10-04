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
