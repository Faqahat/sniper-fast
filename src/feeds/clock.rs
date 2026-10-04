//! One clock for every source: CLOCK_REALTIME in nanoseconds. Kernel UDP receive timestamps (SO_TIMESTAMPNS) are
//! CLOCK_REALTIME too, so raw-shred and gRPC arrivals are directly comparable on the same machine.
//!
//! **Replay mode** (PLAN WP-04 item 11): a replay sets a virtual time on its own thread (`set_virtual`), and `now_ns` on
//! that thread returns it, so the stage timestamps the engine, store, commit and fork code take while handling a
//! journaled input are that input's `t_engine_ns`: the replay is deterministic to the last field. One global flag says
//! whether any thread is replaying; while it is off (always, in a run) `now_ns` costs one relaxed load more than the
//! system call. Other threads (feeds, writers, other tests) keep the real clock.
use std::cell::Cell;
use std::sync::atomic::{AtomicUsize, Ordering};

/// threads that have a virtual time set
static REPLAYING: AtomicUsize = AtomicUsize::new(0);

thread_local! {
    static VIRTUAL: Cell<Option<u64>> = const { Cell::new(None) };
}

#[inline]
pub fn now_ns() -> u64 {
    if REPLAYING.load(Ordering::Relaxed) != 0 {
        if let Some(t) = VIRTUAL.with(|v| v.get()) { return t; }
    }
    real_ns()
}

/// the real clock, whatever the thread's replay mode
#[inline]
pub fn real_ns() -> u64 {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    // SAFETY: valid pointer to a timespec on the stack
    unsafe { libc::clock_gettime(libc::CLOCK_REALTIME, &mut ts) };
    ts.tv_sec as u64 * 1_000_000_000 + ts.tv_nsec as u64
}

/// Set (Some) or clear (None) this thread's virtual time
pub fn set_virtual(t: Option<u64>) {
    VIRTUAL.with(|v| {
        let was = v.replace(t);
        match (was.is_some(), t.is_some()) {
            (false, true) => { REPLAYING.fetch_add(1, Ordering::Relaxed); }
            (true, false) => { REPLAYING.fetch_sub(1, Ordering::Relaxed); }
            _ => {}
        }
    });
}

/// this thread's virtual time, if it is replaying
pub fn virtual_time() -> Option<u64> { VIRTUAL.with(|v| v.get()) }

/// Replay mode for the current scope: the virtual time is cleared when the guard drops (also on a panic)
pub struct Virtual;
impl Virtual {
    pub fn start(t: u64) -> Virtual { set_virtual(Some(t)); Virtual }
    pub fn at(&self, t: u64) { set_virtual(Some(t)); }
}
impl Drop for Virtual { fn drop(&mut self) { set_virtual(None); } }

#[cfg(test)]
mod tests {
    use super::*;

    /// WP-04 item 11: the replay clock is per thread; other threads keep the real one
    #[test]
    fn the_virtual_clock_is_per_thread() {
        let real = now_ns();
        {
            let v = Virtual::start(42);
            assert_eq!(now_ns(), 42);
            v.at(43);
            assert_eq!(now_ns(), 43);
            let other = std::thread::spawn(now_ns).join().unwrap();
            assert!(other >= real, "another thread reads the real clock");
        }
        assert!(now_ns() >= real && virtual_time().is_none(), "cleared when the guard drops");
    }
}
