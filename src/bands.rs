//! The one band table (PLAN WP-05 item 5, WP-06 item 8; review F22): decisions (`decisions.band`), the send queue
//! (`Prio`: the ≥1M class is throttled and queues behind every smaller band) and, from WP-06, the tips all read the
//! same bands. A band is over the expected **edge** = expected gross − the base fee (before the tip):
//!
//! | band | edge |
//! |---|---|
//! | 0 | < 20,000 |
//! | 1 | 20,000 – 100,000 |
//! | 2 | 100,000 – 1,000,000 |
//! | 3 | 1,000,000 – 10,000,000 |
//! | 4 | ≥ 10,000,000 |
//!
//! Bands 3 and 4 form the big class (`[send_policy] big_band_max_per_sec`). The edges are `[bands] edges` (WP-06): the
//! engine and the executor each hold the run's [`Bands`] (journaled with the engine_init and exec_init records, so a
//! replay bands as the run did); the free functions below read the default table (`EDGES`).

/// the base fee of a one-signature transaction (lamports)
pub const BASE_FEE: u64 = 5_000;

/// the band edges over the expected edge (lamports): band k is `[EDGES[k-1], EDGES[k])`
pub const EDGES: [i64; 4] = [20_000, 100_000, 1_000_000, 10_000_000];

/// the first band of the big class (≥ 1M lamports of edge)
pub const BIG_FROM: u8 = 3;

/// the band of an expected edge (gross − base fee)
pub fn of_edge(edge: i64) -> u8 { EDGES.iter().take_while(|e| edge >= **e).count() as u8 }

/// the band of an expected gross (the base fee is taken off first)
pub fn of_gross(gross: i64) -> u8 { of_edge(gross.saturating_sub(BASE_FEE as i64)) }

/// bands 3 and 4: the ≥1M class, throttled and queued behind every smaller band
pub fn is_big(band: u8) -> bool { band >= BIG_FROM }

/// the send queue's band rank: 0 for bands 0-2, 1 for the big class
pub fn rank(band: u8) -> u8 { is_big(band) as u8 }

/// The band table as a run configures it (`[bands] edges`: four increasing positive edges over the expected edge). The
/// default is the table above
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct Bands { pub edges: [i64; 4] }

impl Default for Bands { fn default() -> Self { Bands { edges: EDGES } } }

impl Bands {
    /// from `[bands] edges`: exactly four, increasing, positive
    pub fn new(edges: &[i64]) -> Result<Bands, String> {
        let e: [i64; 4] = edges.try_into().map_err(|_| format!("[bands] edges: four edges, not {}", edges.len()))?;
        if e[0] <= 0 || e.windows(2).any(|w| w[0] >= w[1]) { return Err(format!("[bands] edges {e:?}: four increasing positive edges")); }
        Ok(Bands { edges: e })
    }
    /// the band of an expected edge (gross − base fee)
    pub fn of_edge(&self, edge: i64) -> u8 { self.edges.iter().take_while(|e| edge >= **e).count() as u8 }
    /// the band of an expected gross (the base fee is taken off first)
    pub fn of_gross(&self, gross: i64) -> u8 { self.of_edge(gross.saturating_sub(BASE_FEE as i64)) }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// the table's edges, on the edge (gross − base fee): the engine's decisions used the same numbers since WP-04
    #[test]
    fn bands_over_the_expected_edge() {
        for (edge, band) in [(-5_000, 0), (0, 0), (19_999, 0), (20_000, 1), (99_999, 1), (100_000, 2), (999_999, 2), (1_000_000, 3), (9_999_999, 3), (10_000_000, 4), (i64::MAX, 4)] {
            assert_eq!(of_edge(edge), band, "{edge}");
        }
        assert_eq!((of_gross(25_000), of_gross(24_999), of_gross(1_005_000), of_gross(1_004_999)), (1, 0, 3, 2), "the base fee comes off first");
        assert_eq!((rank(2), rank(3), rank(4), is_big(2)), (0, 1, 1, false));
        assert_eq!(of_gross(i64::MIN), 0, "no overflow");
    }

    /// WP-06: `[bands] edges` configures the same table; the default is the constants'; bad tables are refused
    #[test]
    fn configured_bands() {
        let d = Bands::default();
        for edge in [-5_000, 0, 19_999, 20_000, 99_999, 100_000, 1_000_000, 10_000_000, i64::MAX] { assert_eq!(d.of_edge(edge), of_edge(edge)); }
        let b = Bands::new(&[1_000, 2_000, 3_000, 4_000]).unwrap();
        assert_eq!((b.of_edge(999), b.of_edge(1_000), b.of_edge(3_999), b.of_edge(4_000), b.of_gross(6_000)), (0, 1, 3, 4, 1));
        for bad in [&[1, 2, 3][..], &[0, 1, 2, 3], &[5, 4, 6, 7], &[1, 2, 2, 3]] { assert!(Bands::new(bad).is_err(), "{bad:?}"); }
    }
}
