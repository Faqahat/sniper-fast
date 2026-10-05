//! Network calls, counted where they start (PLAN WP-05 item 2, review F28): no RPC call and no other network call may
//! sit between a decision and its fire. Every `Rpc` call (`call`, `call_bounded`: counted in the caller's context,
//! before the call is spawned onto the background runtime) and every Jito unary call except `SendBundle` (an auth
//! challenge, a token refresh, getTipAccounts) calls [`note`].
//!
//! The send path runs inside a **scope**: the engine thread's send checks, build and signing on the thread
//! ([`on_thread`]), the fire task and every copy task it starts on the hot runtime ([`in_task`]). A call made inside a
//! scope also counts in that scope's counter, so a test can prove a send reached its path with the counter at 0, while a
//! token refresh in the background (outside any scope) counts only in the process total.
use std::cell::RefCell;
use std::future::Future;
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
use std::sync::Arc;

static TOTAL: AtomicU64 = AtomicU64::new(0);

thread_local! { static THREAD: RefCell<Option<Arc<AtomicU64>>> = const { RefCell::new(None) }; }
tokio::task_local! { static TASK: Arc<AtomicU64>; }

/// one network call (an RPC request, a Jito unary call other than SendBundle), in the caller's context
#[inline]
pub fn note() {
    TOTAL.fetch_add(1, Relaxed);
    THREAD.with(|s| if let Some(c) = &*s.borrow() { c.fetch_add(1, Relaxed); });
    let _ = TASK.try_with(|c| c.fetch_add(1, Relaxed));
}

/// every network call of the process so far
pub fn total() -> u64 { TOTAL.load(Relaxed) }

/// the scope this task or thread runs in, if any (a task the send path spawns takes it along)
pub fn current() -> Option<Arc<AtomicU64>> { TASK.try_with(|c| c.clone()).ok().or_else(|| THREAD.with(|s| s.borrow().clone())) }

/// run `f` on this thread with its network calls also counted in `c`
pub fn on_thread<R>(c: &Arc<AtomicU64>, f: impl FnOnce() -> R) -> R {
    let prev = THREAD.with(|s| s.borrow_mut().replace(c.clone()));
    struct Restore(Option<Arc<AtomicU64>>);
    impl Drop for Restore { fn drop(&mut self) { let p = self.0.take(); THREAD.with(|s| *s.borrow_mut() = p); } }
    let _r = Restore(prev);
    f()
}

/// `f` with its network calls (in this task) also counted in `c`; None: no scope
pub async fn in_task<F: Future>(c: Option<Arc<AtomicU64>>, f: F) -> F::Output {
    match c { Some(c) => TASK.scope(c, f).await, None => f.await }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// a call inside a scope counts there and in the total; outside it, only in the total; a task spawned inside a scope
    /// does not inherit it unless it is handed over (`current` + `in_task`)
    #[tokio::test]
    async fn scopes_count_their_own_calls() {
        let c = Arc::new(AtomicU64::new(0));
        let t0 = total();
        note();
        on_thread(&c, || { note(); note(); });
        assert_eq!(c.load(Relaxed), 2);
        in_task(Some(c.clone()), async { note(); }).await;
        assert_eq!(c.load(Relaxed), 3);
        let inner = in_task(Some(c.clone()), async {
            let scope = current();
            tokio::spawn(async move { in_task(scope, async { note() }).await }).await.unwrap();
            tokio::spawn(async { note() }).await.unwrap();
        });
        inner.await;
        assert_eq!(c.load(Relaxed), 4, "the handed-over task counts, the plain one does not");
        assert!(total() >= t0 + 6);
        assert!(current().is_none(), "the thread scope ended with on_thread");
    }

    /// PLAN WP-05 acceptance (F28): every `Rpc` call counts where it starts, in its caller's scope: `call` (the boot
    /// policy or the failover), `call_bounded` and what is built on it (`statuses_bounded`). No provider here: each call
    /// fails at once, and still counts
    #[tokio::test]
    async fn every_rpc_call_counts() {
        let c = Arc::new(AtomicU64::new(0));
        let rpc = crate::rpc::Rpc::race(vec![]);
        let b = || crate::rpc::Bounds::fetch(std::time::Duration::from_millis(100), 0);
        in_task(Some(c.clone()), async {
            assert!(rpc.call("getSlot", serde_json::json!([])).await.is_err());
            assert!(rpc.call_bounded("getSlot", serde_json::json!([]), b()).await.is_err());
            assert!(rpc.statuses_bounded(&[[0u8; 64]], true, b()).await.is_err());
            assert!(rpc.accounts(&[[1u8; 32]]).await.is_err());
        }).await;
        assert_eq!(c.load(Relaxed), 4);
    }
}
