//! The alert hook point (PLAN WP-07, for WP-20's Telegram alerts). Every stop and every alert-worthy money event of the
//! ledger, the in-process supervisor and the campaign supervisor is written to its `events.jsonl` with a clear kind
//! (MEASUREMENT A.6) and handed to [`notify`] as a [`Notice`]. Until a hook is installed `notify` does nothing: arbx
//! does not depend on WP-20. WP-20's merge installs its sink with [`set_hook`] (once, at start: `alerts::notice_hook`,
//! in `arbx run` and in `arbx campaign`'s own process); its hook must never block (a bounded channel with `try_send`:
//! `notify` is called on the engine thread and the campaign's loop).
use serde::Serialize;
use serde_json::Value;
use std::sync::{Arc, RwLock};

/// How much a notice matters (WP-20 maps it to its own levels and `min_level`)
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Level { Info, Warn, Error, Critical }

/// One alert: the events.jsonl `kind` it was written with, the subsystem, a line of text for a human, the detail
#[derive(Clone, Debug, Serialize)]
pub struct Notice {
    pub t_ns: u64,
    pub level: Level,
    /// the events.jsonl kind (MEASUREMENT A.6), also WP-20's dedup key with `subject`
    pub kind: &'static str,
    /// `ledger`, `supervisor`, `campaign`
    pub subsystem: &'static str,
    /// what it is about (a segment, a mint, a rule), for the dedup key
    pub subject: String,
    pub text: String,
    pub detail: Value,
}

type Hook = Arc<dyn Fn(&Notice) + Send + Sync>;

static HOOK: RwLock<Option<Hook>> = RwLock::new(None);

/// Install the process's alert sink (WP-20's `alerts`). It replaces any earlier one; it must never block
pub fn set_hook(f: impl Fn(&Notice) + Send + Sync + 'static) { *HOOK.write().unwrap_or_else(|e| e.into_inner()) = Some(Arc::new(f)); }

/// Remove the sink (tests)
pub fn clear_hook() { *HOOK.write().unwrap_or_else(|e| e.into_inner()) = None; }

/// tests that install the process's hook hold this lock while it is theirs (one hook per process; tests run in
/// parallel: integration, the alerts' wiring tests beside WP-07's own)
#[cfg(test)]
pub fn hook_test_lock() -> std::sync::MutexGuard<'static, ()> {
    static L: std::sync::Mutex<()> = std::sync::Mutex::new(());
    L.lock().unwrap_or_else(|e| e.into_inner())
}

#[cfg(test)]
thread_local! {
    /// tests: the notices of this thread, captured instead of going to the process's hook (tests run in parallel)
    static CAPTURE: std::cell::RefCell<Option<Vec<Notice>>> = const { std::cell::RefCell::new(None) };
}

/// tests: capture this thread's notices while `f` runs
#[cfg(test)]
pub fn capture<R>(f: impl FnOnce() -> R) -> (R, Vec<Notice>) {
    CAPTURE.with(|c| *c.borrow_mut() = Some(Vec::new()));
    let r = f();
    let got = CAPTURE.with(|c| c.borrow_mut().take()).unwrap_or_default();
    (r, got)
}

/// notices a hook panicked on (the panic is caught: review WP-07 #13)
pub static HOOK_PANICS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

thread_local! {
    /// this thread is running the alert hook now (`control::install_panic_hook` then logs a panic instead of failing the
    /// run with it: the hook's panic is caught here)
    static IN_HOOK: std::cell::Cell<bool> = const { std::cell::Cell::new(false) };
}

/// whether this thread is running the alert hook (a panic there is the hook's, caught, not the run's)
pub fn in_hook() -> bool { IN_HOOK.with(|f| f.get()) }

/// Hand a notice to the installed sink (nothing without one). Callers have already written its events.jsonl line and
/// acted (a stop is requested before its notice). A hook that panics is caught and counted (`HOOK_PANICS`): it never
/// unwinds into the engine or the campaign's loop
pub fn notify(n: Notice) {
    #[cfg(test)]
    {
        let taken = CAPTURE.with(|c| match c.borrow_mut().as_mut() { Some(v) => { v.push(n.clone()); true } None => false });
        if taken { return; }
    }
    let h = HOOK.read().unwrap_or_else(|e| e.into_inner()).clone();
    if let Some(h) = h {
        IN_HOOK.with(|f| f.set(true));
        let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| h(&n)));
        IN_HOOK.with(|f| f.set(false));
        if r.is_err() { HOOK_PANICS.fetch_add(1, std::sync::atomic::Ordering::Relaxed); }
    }
}

/// A notice now
pub fn now(level: Level, kind: &'static str, subsystem: &'static str, subject: impl Into<String>, text: impl Into<String>, detail: Value) -> Notice {
    Notice { t_ns: crate::feeds::clock::now_ns(), level, kind, subsystem, subject: subject.into(), text: text.into(), detail }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// without a hook nothing happens; an installed hook sees every notice; tests capture their own thread's
    #[test]
    fn the_hook_point() {
        notify(now(Level::Info, "x", "ledger", "s", "no hook", Value::Null));
        let (_, got) = capture(|| notify(now(Level::Critical, "equity_floor", "supervisor", "p1", "floor", serde_json::json!({ "floor": 1 }))));
        assert_eq!(got.len(), 1);
        assert_eq!((got[0].level, got[0].kind, got[0].subject.as_str()), (Level::Critical, "equity_floor", "p1"));
        assert!(Level::Critical > Level::Warn && Level::Warn > Level::Info);
        assert_eq!(serde_json::to_value(Level::Error).unwrap(), "error");
    }
}
