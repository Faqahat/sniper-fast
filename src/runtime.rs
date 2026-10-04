//! The runtime split (PLAN WP-02 item 1; review F9). arb-lab ran the state stream, the feeds, the Jito sends and every
//! RPC fetch on one 2-worker runtime, so a slow RPC reply (or the parse of a large one) could delay the state stream or
//! a send.
//!
//! - **`rt_hot`** ([`HOT`], 2 workers): stream I/O and sends only: the state stream, the gRPC feeds, the Jito send and
//!   result streams, the send paths and their keep-alives.
//! - **`rt_bg`** ([`BG`], `[runtime] bg_threads` workers, niced +5): every RPC call. `Rpc::bind` puts a client's calls on
//!   it (they are spawned there whichever runtime awaits them), and replies over [`LARGE_REPLY`] bytes are parsed in
//!   `spawn_blocking` on its blocking pool.
//!
//! [`check_not_hot`] guards the RPC path: an RPC future polled on an `arbx-hot` thread is counted
//! ([`hot_violations`]) and fails a debug assertion.
use anyhow::{Context, Result};
use std::sync::atomic::{AtomicI64, AtomicU64, Ordering};
use std::time::Duration;

/// thread name of the hot runtime's workers
pub const HOT: &str = "arbx-hot";
/// thread name of the background runtime's workers and blocking threads
pub const BG: &str = "arbx-bg";
/// the hot runtime's workers (arb-lab's `worker_threads(2)`)
pub const HOT_THREADS: usize = 2;
/// the background runtime's niceness, added to the process's
pub const BG_NICE: i32 = 5;
/// RPC replies larger than this are parsed in `spawn_blocking` (never on a runtime worker)
pub const LARGE_REPLY: usize = 256 * 1024;

static HOT_VIOLATIONS: AtomicU64 = AtomicU64::new(0);
/// large-reply parses running now (resources.jsonl `runtimes.bg.blocking_now`), and done so far
pub static BLOCKING_NOW: AtomicI64 = AtomicI64::new(0);
pub static LARGE_PARSES: AtomicU64 = AtomicU64::new(0);

/// The two runtimes of `arbx run`
pub struct Runtimes { pub hot: tokio::runtime::Runtime, pub bg: tokio::runtime::Runtime }

impl Runtimes {
    pub fn new(bg_threads: usize) -> Result<Runtimes> {
        Ok(Runtimes { hot: hot_runtime(HOT_THREADS)?, bg: bg_runtime(bg_threads)? })
    }

    /// stop both (the hot one first: its tasks may still be waiting on background RPC)
    pub fn shutdown(self, timeout: Duration) {
        self.hot.shutdown_timeout(timeout);
        self.bg.shutdown_timeout(timeout);
    }
}

pub fn hot_runtime(threads: usize) -> Result<tokio::runtime::Runtime> {
    tokio::runtime::Builder::new_multi_thread().worker_threads(threads.max(1)).thread_name(HOT).enable_all().build().context("the hot runtime")
}

pub fn bg_runtime(threads: usize) -> Result<tokio::runtime::Runtime> {
    tokio::runtime::Builder::new_multi_thread().worker_threads(threads.max(1)).thread_name(BG).on_thread_start(|| nice_this_thread(BG_NICE))
        .enable_all().build().context("the background runtime")
}

/// Lower this thread's priority by `delta` (Linux: `setpriority` on a thread id affects that thread only). Raising the
/// niceness needs no privilege; a failure leaves the thread as it was
pub fn nice_this_thread(delta: i32) {
    // SAFETY: plain syscalls on this thread's own id
    unsafe {
        let tid = libc::syscall(libc::SYS_gettid) as libc::id_t;
        *libc::__errno_location() = 0;
        let cur = libc::getpriority(libc::PRIO_PROCESS, tid);
        if cur == -1 && *libc::__errno_location() != 0 { return; }
        let _ = libc::setpriority(libc::PRIO_PROCESS, tid, (cur + delta).min(19));
    }
}

/// this thread's niceness (tests)
pub fn this_thread_nice() -> i32 {
    // SAFETY: as above
    unsafe { libc::getpriority(libc::PRIO_PROCESS, libc::syscall(libc::SYS_gettid) as libc::id_t) }
}

/// this thread's kernel id
pub fn gettid() -> i32 {
    // SAFETY: no arguments
    unsafe { libc::syscall(libc::SYS_gettid) as i32 }
}

pub fn on_hot_thread() -> bool { std::thread::current().name() == Some(HOT) }

/// The RPC path calls this where it does its work: on an `arbx-hot` thread it counts a violation and fails a debug
/// assertion (an RPC client that was not bound to `rt_bg`)
#[inline]
pub fn check_not_hot(what: &str) {
    if on_hot_thread() {
        HOT_VIOLATIONS.fetch_add(1, Ordering::Relaxed);
        debug_assert!(false, "{what} polled on an {HOT} thread: bind the client to rt_bg (Rpc::bind)");
    }
}

/// RPC futures polled on an `arbx-hot` thread so far
pub fn hot_violations() -> u64 { HOT_VIOLATIONS.load(Ordering::Relaxed) }

/// busy time of a runtime's workers so far, ms (resources.jsonl `runtimes.*.busy_ms_delta`)
pub fn busy_ms(h: &tokio::runtime::Handle) -> u64 {
    let m = h.metrics();
    (0..m.num_workers()).map(|w| m.worker_total_busy_duration(w).as_millis() as u64).sum()
}

/// tasks alive on a runtime now
pub fn tasks_now(h: &tokio::runtime::Handle) -> usize { h.metrics().num_alive_tasks() }

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn workers_are_named_and_the_background_is_niced() {
        let rts = Runtimes::new(2).unwrap();
        let hot = rts.hot.block_on(async { tokio::spawn(async { (std::thread::current().name().map(String::from), this_thread_nice()) }).await.unwrap() });
        let bg = rts.bg.block_on(async { tokio::spawn(async { (std::thread::current().name().map(String::from), this_thread_nice()) }).await.unwrap() });
        assert_eq!(hot.0.as_deref(), Some(HOT));
        assert_eq!(bg.0.as_deref(), Some(BG));
        // +5 relative to the process (capped at 19 when the tests themselves run niced)
        assert_eq!(bg.1, (hot.1 + BG_NICE).min(19), "hot {} bg {}", hot.1, bg.1);
        let blocking = rts.bg.block_on(async { tokio::task::spawn_blocking(|| (std::thread::current().name().map(String::from), this_thread_nice())).await.unwrap() });
        assert_eq!(blocking, (Some(BG.to_string()), bg.1), "the blocking pool is background too");
        assert!(busy_ms(rts.bg.handle()) < 60_000);
        rts.shutdown(Duration::from_secs(1));
    }

    /// release builds count the violation (debug builds also fail the assertion: see the next test)
    #[cfg(not(debug_assertions))]
    #[test]
    fn rpc_work_on_a_hot_thread_is_counted() {
        let before = hot_violations();
        check_not_hot("test");
        assert_eq!(hot_violations(), before, "the test thread is not hot");
        let rt = hot_runtime(1).unwrap();
        rt.block_on(async { tokio::spawn(async { check_not_hot("test rpc") }).await.unwrap() });
        assert!(hot_violations() > before);
    }

    #[cfg(debug_assertions)]
    #[test]
    fn rpc_work_on_a_hot_thread_fails_the_debug_assertion() {
        let rt = hot_runtime(1).unwrap();
        let r = rt.block_on(async { tokio::spawn(async { check_not_hot("test rpc") }).await });
        assert!(r.is_err(), "the assertion panicked the task");
    }
}
