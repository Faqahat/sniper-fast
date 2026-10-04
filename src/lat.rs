//! Latency series for status.jsonl `latency` (MEASUREMENT A.8).
//!
//! WP-00 (review F7): arb-lab kept every sample (up to 200,000 per series) and sorted the whole vector three times per
//! series on every status tick, on the engine thread: 4.2 ms every 10 s at 200k samples, more with WP-00's
//! state-path series. A `Series` keeps a uniform reservoir of at most `RESERVOIR` samples of the whole run
//! (Vitter's algorithm R) and counts every sample in `n`, so a tick sorts at most 8,192 values per series.

use serde_json::{json, Value};

/// samples kept per series for the percentiles (p99 then rests on about 82 samples)
pub const RESERVOIR: usize = 8_192;

pub struct Series {
    pub name: &'static str,
    /// every sample since the start
    n: u64,
    /// a uniform sample of them (any order: replacement picks a random slot)
    buf: Vec<u64>,
    rng: u64,
}

impl Series {
    pub fn new(name: &'static str) -> Series {
        // a fixed, per-name seed: runs are reproducible and series do not move in lockstep
        let seed = name.bytes().fold(0x9E37_79B9_7F4A_7C15u64, |h, b| (h ^ b as u64).wrapping_mul(0x0100_0000_01B3)) | 1;
        Series { name, n: 0, buf: Vec::new(), rng: seed }
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
        if self.buf.len() < RESERVOIR { self.buf.push(v); return; }
        let j = self.next() % self.n;
        if (j as usize) < RESERVOIR { self.buf[j as usize] = v; }
    }

    #[cfg(test)]
    pub fn n(&self) -> u64 { self.n }

    /// the `q` quantile (0..=1) of the kept samples, ns; 0 when empty. Sorts the reservoir in place (its order is free)
    #[cfg(test)]
    pub fn pct(&mut self, q: f64) -> u64 {
        if self.buf.is_empty() { return 0; }
        self.buf.sort_unstable();
        self.buf[((self.buf.len() - 1) as f64 * q).round() as usize]
    }

    /// the status.jsonl entry: `{n, p50_us, p90_us, p99_us}` (one sort for the three)
    pub fn summary(&mut self) -> Value {
        let (p50, p90, p99) = if self.buf.is_empty() { (0, 0, 0) } else {
            self.buf.sort_unstable();
            let at = |q: f64| self.buf[((self.buf.len() - 1) as f64 * q).round() as usize];
            (at(0.5), at(0.9), at(0.99))
        };
        json!({ "n": self.n, "p50_us": p50 / 1000, "p90_us": p90 / 1000, "p99_us": p99 / 1000 })
    }

    #[cfg(test)]
    pub fn kept(&self) -> &[u64] { &self.buf }
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
        assert_eq!(s.summary(), json!({ "n": 5, "p50_us": 3, "p90_us": 5, "p99_us": 5 }));
        assert_eq!(Series::new("e").summary(), json!({ "n": 0, "p50_us": 0, "p90_us": 0, "p99_us": 0 }));
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
