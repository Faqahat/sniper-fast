//! Latency series for status.jsonl `latency` (MEASUREMENT §4.8, A.8).
//!
//! WP-00 (review F7): arb-lab kept every sample (up to 200,000 per series) and sorted the whole vector three times per
//! series on every status tick, on the engine thread: 4.2 ms every 10 s at 200k samples, more with WP-00's
//! state-path series. A `Series` keeps a uniform reservoir of at most `RESERVOIR` samples of the whole run
//! (Vitter's algorithm R) and counts every sample in `n`, so a tick sorts at most 8,192 values per series.
//!
//! WP-02 (status.jsonl v2, §2.2): percentiles name their window. A second reservoir holds the samples since the last
//! status line (`window: "interval"`, `take_interval`); the run-wide one is `window: "run"` (`run_pct`).

use serde_json::{json, Value};

/// samples kept per series for the percentiles (p99 then rests on about 82 samples)
pub const RESERVOIR: usize = 8_192;

pub struct Series {
    pub name: &'static str,
    /// every sample since the start
    n: u64,
    /// a uniform sample of them (any order: replacement picks a random slot)
    buf: Vec<u64>,
    /// the samples since the last `take_interval`, and a uniform sample of them
    iv_n: u64,
    iv: Vec<u64>,
    rng: u64,
}

impl Series {
    pub fn new(name: &'static str) -> Series {
        // a fixed, per-name seed: runs are reproducible and series do not move in lockstep
        let seed = name.bytes().fold(0x9E37_79B9_7F4A_7C15u64, |h, b| (h ^ b as u64).wrapping_mul(0x0100_0000_01B3)) | 1;
        Series { name, n: 0, buf: Vec::new(), iv_n: 0, iv: Vec::new(), rng: seed }
    }

    /// xorshift64*: cheap, good enough to pick reservoir slots
    fn next(&mut self) -> u64 {
        let mut x = self.rng;
        x ^= x >> 12; x ^= x << 25; x ^= x >> 27;
        self.rng = x;
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }

    pub fn push(&mut self, v: u64) {
        self.n += 1;
        if self.buf.len() < RESERVOIR { self.buf.push(v); } else {
            let j = self.next() % self.n;
            if (j as usize) < RESERVOIR { self.buf[j as usize] = v; }
        }
        self.iv_n += 1;
        if self.iv.len() < RESERVOIR { self.iv.push(v); } else {
            let j = self.next() % self.iv_n;
            if (j as usize) < RESERVOIR { self.iv[j as usize] = v; }
        }
    }

    pub fn n(&self) -> u64 { self.n }

    /// the `q` quantile (0..=1) of the kept samples, ns; 0 when empty. Sorts the reservoir in place (its order is free)
    pub fn pct(&mut self, q: f64) -> u64 {
        if self.buf.is_empty() { return 0; }
        self.buf.sort_unstable();
        self.buf[((self.buf.len() - 1) as f64 * q).round() as usize]
    }

    /// (p50, p90, p99) of a sample, sorted in place; None when empty
    fn three(v: &mut [u64]) -> Option<(u64, u64, u64)> {
        if v.is_empty() { return None; }
        v.sort_unstable();
        let at = |q: f64| v[((v.len() - 1) as f64 * q).round() as usize];
        Some((at(0.5), at(0.9), at(0.99)))
    }

    /// `{window: "run", n, p50, p90, p99}` over the whole run, in units of `div` ns (1e3: whole µs); null percentiles
    /// when empty
    pub fn run_pct(&mut self, div: f64) -> Value {
        let n = self.n;
        pct_json("run", n, Self::three(&mut self.buf), div)
    }

    /// `{window: "interval", n, p50, p90, p99}` over the samples since the last call (in units of `div` ns), then
    /// starts the next interval
    pub fn take_interval(&mut self, div: f64) -> Value {
        let v = pct_json("interval", self.iv_n, Self::three(&mut self.iv), div);
        self.iv.clear();
        self.iv_n = 0;
        v
    }

    #[cfg(test)]
    pub fn kept(&self) -> &[u64] { &self.buf }
}

fn pct_json(window: &str, n: u64, p: Option<(u64, u64, u64)>, div: f64) -> Value {
    let f = |x: u64| -> Value { if div == 1e3 { json!(x / 1000) } else { json!(x as f64 / div) } };
    match p {
        Some((a, b, c)) => json!({ "window": window, "n": n, "p50": f(a), "p90": f(b), "p99": f(c) }),
        None => json!({ "window": window, "n": n, "p50": null, "p90": null, "p99": null }),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn small_series_are_exact() {
        let mut s = Series::new("x");
        for v in [5_000u64, 1_000, 3_000, 2_000, 4_000] { s.push(v); }
        assert_eq!(s.n(), 5);
        assert_eq!(s.pct(0.5), 3_000);
        assert_eq!(s.run_pct(1e3), json!({ "window": "run", "n": 5, "p50": 3, "p90": 5, "p99": 5 }));
        assert_eq!(Series::new("e").run_pct(1e3), json!({ "window": "run", "n": 0, "p50": null, "p90": null, "p99": null }));
    }

    /// WP-02: the interval window holds the samples since the last line only; the run window keeps them all
    #[test]
    fn interval_window_restarts_each_line() {
        let mut s = Series::new("y");
        for v in [1_000u64, 2_000, 3_000] { s.push(v); }
        assert_eq!(s.take_interval(1e3), json!({ "window": "interval", "n": 3, "p50": 2, "p90": 3, "p99": 3 }));
        assert_eq!(s.take_interval(1e3)["n"], json!(0), "nothing since");
        s.push(9_000_000);
        assert_eq!(s.take_interval(1e6), json!({ "window": "interval", "n": 1, "p50": 9.0, "p90": 9.0, "p99": 9.0 }), "ms");
        assert_eq!(s.run_pct(1e3)["n"], json!(4));
    }

    /// a long series keeps at most RESERVOIR samples, counts them all, and its percentiles stay close to the truth
    #[test]
    fn reservoir_is_bounded_and_unbiased() {
        let mut s = Series::new("state_recv_to_decided");
        let total = 300_000u64;
        // a uniform ramp 0..total (shuffled by a stride so the order says nothing): true p50 = total/2, p99 = 0.99 total
        for k in 0..total { s.push((k * 7_919) % total); }
        assert_eq!(s.n(), total);
        assert_eq!(s.kept().len(), RESERVOIR);
        for (q, tol) in [(0.5, 0.02), (0.9, 0.015), (0.99, 0.005)] {
            let got = s.pct(q) as f64 / total as f64;
            assert!((got - q).abs() < tol, "q {q}: {got}");
        }
        // late samples still get in (the reservoir follows the whole run, not its start)
        let mut s = Series::new("late");
        for _ in 0..100_000 { s.push(1); }
        for _ in 0..100_000 { s.push(1_000_000); }
        let late = s.kept().iter().filter(|&&v| v == 1_000_000).count() as f64 / RESERVOIR as f64;
        assert!((late - 0.5).abs() < 0.05, "{late}");
    }
}
