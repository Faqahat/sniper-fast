//! The bundle tip policy (PLAN WP-06 item 8; review F22). One band table ([`crate::bands::Bands`]) is read by the
//! decisions, the send queue and the tips. Over the expected **edge** (expected gross − the base fee, before the tip):
//!
//! **tip = clamp(⌊share(band, contested) × edge⌋, floor, cap)**
//!
//! - `[tips] shares` are Stage 0's 0.7 in every band (the status quo: WP-06 changes the mechanism, not the behaviour;
//!   X4 changes the numbers); `contested_shares` apply when the Stage 2A Selector calls a gap contested (always false
//!   until then).
//! - The tip sets the bundle's on-chain min_profit (tip + base fee + margin, PLAN WP-05 item 8) and the engine's fee
//!   estimate (`fee`: base fee + the tip of the gross's edge; a bundle pays CU price 0, PLAN WP-06 item 5), so a
//!   decision's net and the executor's are the same number.
//! - It replaces `send::Path::tip`'s share logic for bundles: the jito-bundle path keeps only its floor
//!   (`tip_lamports`, Jito's minimum) and its accounts; `[tips]` holds the rest.
//! - WP-11's X4 arm (a share per arm, `[experiments.x4]`) hooks in at [`TipModel::tip_arm`]: in the bands up to its
//!   `max_band` the arm's share replaces the band's (`shares`; the contested table is left alone), `floor` and `cap`
//!   stay, and the engine's fee estimate (`fee_arm`) reads the same arm, so a decision's net and the executor's stay one
//!   number. Without an arm both are the functions they were.
use crate::bands::{Bands, BASE_FEE};
use crate::experiments::ShareArm;
use serde::{Deserialize, Serialize};

/// the bands a share table covers (src/bands.rs: 0-4)
pub const N_BANDS: usize = 5;

/// The tip policy as a run configures it (`[tips]`, `[bands]`)
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct TipModel {
    pub bands: Bands,
    pub shares: [f64; N_BANDS],
    pub contested_shares: [f64; N_BANDS],
    pub floor: u64,
    pub cap: u64,
}

/// One tip: its lamports, the band of the edge it was cut from, the share used, and (WP-11) the X4 arm's share when it
/// replaced the band's (attempts.jsonl `tip.arm`)
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Tip { pub lamports: u64, pub band: u8, pub share: f64, pub arm: Option<f64> }

impl Default for TipModel {
    /// Stage 0's: 0.7 of the edge in every band, 1,000 to 100,000 lamports (the jito-bundle path's values before WP-06)
    fn default() -> Self {
        TipModel { bands: Bands::default(), shares: [0.7; N_BANDS], contested_shares: [0.16, 0.47, 0.54, 0.64, 0.64], floor: 1_000, cap: 100_000 }
    }
}

impl TipModel {
    /// from `[tips]` and `[bands]` (checked by `Config::parse`)
    pub fn from_cfg(c: &crate::config::Config) -> Result<TipModel, String> {
        let t = &c.tips;
        let arr = |v: &[f64], k: &str| -> Result<[f64; N_BANDS], String> {
            let a: [f64; N_BANDS] = v.try_into().map_err(|_| format!("[tips] {k}: one share per band ({N_BANDS}), not {}", v.len()))?;
            if a.iter().any(|s| !s.is_finite() || !(0.0..=1.0).contains(s)) { return Err(format!("[tips] {k}: shares of the edge, 0..1")); }
            Ok(a)
        };
        let m = TipModel { bands: Bands::new(&c.bands.edges)?, shares: arr(&t.shares, "shares")?, contested_shares: arr(&t.contested_shares, "contested_shares")?,
            floor: t.floor, cap: t.cap };
        m.check()?;
        Ok(m)
    }

    /// What `[tips]` and `[bands]` must be (a model from a config or a replay's `--set tips.<field>`): shares of the edge in
    /// 0..1, 1 <= floor <= cap, four increasing positive band edges
    pub fn check(&self) -> Result<(), String> {
        for (k, a) in [("shares", &self.shares), ("contested_shares", &self.contested_shares)] {
            if a.iter().any(|s| !s.is_finite() || !(0.0..=1.0).contains(s)) { return Err(format!("[tips] {k}: shares of the edge, 0..1")); }
        }
        if self.floor == 0 || self.cap < self.floor { return Err(format!("[tips] floor {} / cap {}: 1 <= floor <= cap", self.floor, self.cap)); }
        Bands::new(&self.bands.edges).map(|_| ())
    }

    /// The tip for an expected edge (gross − base fee): the share of its band (the contested one when `contested`) of
    /// the edge, rounded down (never more than it), within `floor` and `cap`. A negative edge tips the floor
    pub fn tip(&self, edge: i64, contested: bool) -> Tip { self.tip_arm(edge, contested, None) }

    /// [`TipModel::tip`] under WP-11's X4 arm (`[experiments.x4]`): in bands 0..=`arm.max_band` the arm's share replaces
    /// the band's (`shares`; a contested gap keeps the contested table), rounded down and within the same `floor` and
    /// `cap`. Without an arm, or out of its bands, the tip is `tip`'s to the lamport
    pub fn tip_arm(&self, edge: i64, contested: bool, arm: Option<ShareArm>) -> Tip {
        let band = self.bands.of_edge(edge);
        let arm = arm.filter(|a| !contested && band <= a.max_band).map(|a| a.share);
        let share = arm.unwrap_or_else(|| if contested { self.contested_shares } else { self.shares }[band as usize]);
        let lamports = ((edge.max(0) as f64 * share) as u64).clamp(self.floor, self.cap.max(self.floor));
        Tip { lamports, band, share, arm }
    }

    /// The engine's fee estimate for an expected gross (PLAN WP-06 item 5): the base fee plus the tip of its edge. A
    /// bundle pays CU price 0, so the CU it asks costs nothing
    pub fn fee(&self, gross: i64) -> u64 { self.fee_arm(gross, None) }

    /// [`TipModel::fee`] under WP-11's X4 arm: the base fee plus the tip `tip_arm` cuts from the gross's edge
    pub fn fee_arm(&self, gross: i64, arm: Option<ShareArm>) -> u64 { BASE_FEE + self.tip_arm(gross.saturating_sub(BASE_FEE as i64), false, arm).lamports }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The clamp table: the share of the edge rounded down, the floor below, the cap above; the Stage-0 shares are
    /// today's (0.7 in every band), so the tips are the WP-05 path's to the lamport
    #[test]
    fn tip_clamp_table() {
        let m = TipModel::default();
        for (edge, want, band) in [(-5_000i64, 1_000u64, 0u8), (0, 1_000, 0), (1_428, 1_000, 0), (1_430, 1_000, 0), (1_500, 1_050, 0), (19_999, 13_999, 0), (20_000, 14_000, 1),
            (45_000, 31_499, 1), (50_000, 35_000, 1), (142_857, 99_999, 2), (142_858, 100_000, 2), (10_000_000, 100_000, 4), (i64::MAX, 100_000, 4)] {
            let t = m.tip(edge, false);
            assert_eq!((t.lamports, t.band, t.share), (want, band, 0.7), "edge {edge}");
        }
        // the WP-05 TipPolicy rule this replaces: ((edge.max(0) as f64 * 0.7) as u64).clamp(1_000, 100_000)
        for edge in (0..3_000_000i64).step_by(7_919) {
            assert_eq!(m.tip(edge, false).lamports, ((edge.max(0) as f64 * 0.7) as u64).clamp(1_000, 100_000), "{edge}");
        }
    }

    /// WP-11 (X4, property over 200,000 random edges, shares and scopes): `tip_arm` is `tip` without an arm, out of the
    /// arm's bands and for a contested gap; in them it is the arm's share of the edge rounded down within the same floor
    /// and cap (`arm` the share), never more than the edge (the floor aside); the fee estimate reads the same tip
    #[test]
    fn x4_arm_property() {
        let m = TipModel { shares: [0.2, 0.2, 0.2, 0.6, 0.7], ..TipModel::default() };
        let mut rng = 0x9e37_79b9_7f4a_7c15u64;
        let mut in_band = 0;
        for _ in 0..200_000 {
            rng ^= rng << 13;
            rng ^= rng >> 7;
            rng ^= rng << 17;
            let edge = (rng % 40_000_000) as i64 - 1_000_000;
            let share = ((rng >> 40) % 1_001) as f64 / 1_000.0;
            let max_band = ((rng >> 20) % 5) as u8;
            let arm = ShareArm { share, max_band };
            let (a, p) = (m.tip_arm(edge, false, Some(arm)), m.tip(edge, false));
            assert_eq!(m.tip_arm(edge, false, None), p, "no arm: today's tip");
            assert!(a.lamports >= m.floor && a.lamports <= m.cap, "{edge} {share}: {a:?}");
            if p.band <= max_band {
                in_band += 1;
                assert_eq!((a.share, a.arm, a.band), (share, Some(share), p.band));
                assert_eq!(a.lamports, ((edge.max(0) as f64 * share) as u64).clamp(m.floor, m.cap));
                assert!(a.lamports <= (edge.max(0) as u64).max(m.floor), "never more than the edge (the floor aside)");
            } else {
                assert_eq!(a, p, "out of the arm's bands: the band's tip");
            }
            assert_eq!(m.tip_arm(edge, true, Some(arm)), m.tip(edge, true), "a contested gap keeps its table");
            assert_eq!(m.fee_arm(edge + 5_000, Some(arm)), 5_000 + a.lamports, "the engine's fee estimate reads the same tip");
        }
        assert!(in_band > 50_000 && in_band < 190_000, "{in_band}");
    }

    /// Shares by band: each band its own share; contested gaps their own table; the fee estimate is base + tip
    #[test]
    fn tips_by_band() {
        let m = TipModel { shares: [0.1, 0.2, 0.3, 0.4, 0.5], contested_shares: [0.5, 0.6, 0.7, 0.8, 0.9], floor: 10, cap: 10_000_000, ..TipModel::default() };
        let cases = [(10_000i64, 0u8, 1_000u64, 5_000u64), (50_000, 1, 10_000, 30_000), (500_000, 2, 150_000, 350_000), (5_000_000, 3, 2_000_000, 4_000_000),
            (20_000_000, 4, 10_000_000, 10_000_000)];
        for (edge, band, plain, contested) in cases {
            let (p, c) = (m.tip(edge, false), m.tip(edge, true));
            assert_eq!((p.band, p.lamports, c.band, c.lamports), (band, plain, band, contested), "edge {edge}");
        }
        assert_eq!(m.fee(15_000), 5_000 + 1_000, "the gross's edge is 10,000: band 0, 10%");
        assert_eq!(TipModel::default().fee(55_000), 5_000 + 35_000);
        assert_eq!(TipModel::default().fee(i64::MIN), 5_000 + 1_000, "no overflow");
        // the checks a config and a replay's --set pass through
        assert!(TipModel::default().check().is_ok());
        for bad in [TipModel { floor: 0, ..TipModel::default() }, TipModel { cap: 999, ..TipModel::default() }, TipModel { shares: [0.7, 0.7, 1.5, 0.7, 0.7], ..TipModel::default() },
            TipModel { contested_shares: [f64::NAN; 5], ..TipModel::default() }, TipModel { bands: Bands { edges: [20_000, 10_000, 1_000_000, 10_000_000] }, ..TipModel::default() }] {
            assert!(bad.check().is_err(), "{bad:?}");
        }
    }
}
