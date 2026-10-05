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
//! Bands 3 and 4 form the big class (`[send_policy] big_band_max_per_sec`). The edges are WP-06's `[bands] edges`
//! default; until WP-06 brings the key they are this table's constants.

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
}
