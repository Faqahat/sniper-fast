//! Measured CU limits (PLAN WP-06 item 4; review F36). The transaction's CU limit was a static per-venue table (5 runs
//! ran out of CU; the median ask was 206k against 140k used). Now it is built per leg, from samples of every venue's
//! own consumption, not only from our transactions (only wins land, which would starve the table):
//!
//! - **The table** (`data/cu-table.json`, schema `arbx.cu-table/1.0`) is what the toolkit's `cu-table` command writes
//!   (tools/arbx-report/arbx_report/reports/cu_table.py): per leg, keyed `<venue>|<bins bucket>` (DLMM by the bins with
//!   liquidity the leg crosses: `0`, `1-2`, `3-5`, `6+`; other venues `na`), the sample count, p50 and p99 of the venue
//!   program's `consumed X of Y` at the swap's invoke depth; our route program's overhead (outer consumption minus its
//!   legs); the ATA create, the ATA close and the tip transfer. It carries its own provenance (`built_ns`,
//!   `source_runs`, `source`).
//! - **Our route's limit** = (overhead p99 + Σ leg p99 + tip) × 1.10, plus the ATA create and close (× 1.10) when the
//!   transaction makes them, rounded up to 1,000 and never above 1.4M.
//! - **Fallback:** a route whose overhead or either leg has fewer than `cu_min_samples` samples (30) uses today's formula
//!   (`Venue::leg_cu` + 29,000) × 1.10, and the ATA create and close the constants below (a table without them too).
//!
//! The model ([`CuModel`]: the table as read and `cu_min_samples`) is journaled with the engine_init record, so a
//! replay asks the run's CU without reading the file.
use crate::venues::Venue;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub const SCHEMA: &str = "arbx.cu-table/1.0";
/// the most CU a transaction may ask
pub const MAX_CU: u64 = 1_400_000;
/// the fallback formula's allowance for our route program, the tip transfer and the compute-budget instructions
/// (arbed's cu-budget; engine.rs before WP-06)
pub const FALLBACK_OVERHEAD: u64 = 29_000;
/// the fallback's ATA create (idempotent) and close: arbed's create allowance; a close well above what SPL Token's
/// (and p-token's) CloseAccount consumes
pub const FALLBACK_ATA_CREATE: u64 = 30_000;
pub const FALLBACK_ATA_CLOSE: u64 = 5_000;
/// the margin on every limit
pub const MARGIN: f64 = 1.10;
/// the default `cu_min_samples`
pub const MIN_SAMPLES: u64 = 30;

/// one cell's samples (the toolkit's quantiles may be fractional)
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct LegStat { pub n: u64, pub p50: Option<f64>, pub p99: Option<f64> }

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Overhead { pub n: u64, pub p99: Option<f64>, #[serde(default)] pub program: Vec<String> }

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Extras {
    /// p99 of the ATA program's create and of the token program's close (0: not sampled), and the tip transfer
    #[serde(default)]
    pub ata_create: f64,
    #[serde(default)]
    pub ata_close: f64,
    #[serde(default)]
    pub tip: f64,
}

/// `data/cu-table.json` as the toolkit writes it (cells are informational: the route's limit is computed from the legs)
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct CuTable {
    pub schema: String,
    #[serde(default)]
    pub built_ns: Option<u64>,
    #[serde(default)]
    pub source_runs: Vec<String>,
    /// provenance of a table not built from recordings (the venue harness's measurements on the real binaries)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,
    pub legs: BTreeMap<String, LegStat>,
    pub overhead: Overhead,
    pub extras: Extras,
}

impl CuTable {
    pub fn parse(text: &str) -> Result<CuTable, String> {
        let t: CuTable = serde_json::from_str(text).map_err(|e| format!("not a cu table: {e}"))?;
        if t.schema != SCHEMA { return Err(format!("schema {:?}, this build reads {SCHEMA}", t.schema)); }
        Ok(t)
    }
    pub fn load(path: &str) -> Result<CuTable, String> {
        CuTable::parse(&std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?).map_err(|e| format!("{path}: {e}"))
    }
}

/// The toolkit's bins bucket of a DLMM leg: the bins with liquidity it crosses
pub fn bins_bucket(crossed: u32) -> &'static str {
    match crossed { 0 => "0", 1..=2 => "1-2", 3..=5 => "3-5", _ => "6+" }
}

/// a leg's key in the table (`<venue>|<bucket>`, the toolkit's)
pub fn leg_key(v: Venue, crossed: u32) -> String {
    let name = serde_json::to_value(v).ok().and_then(|x| x.as_str().map(String::from)).unwrap_or_default();
    if v == Venue::Dlmm { format!("{name}|{}", bins_bucket(crossed)) } else { format!("{name}|na") }
}

/// Today's formula (engine.rs before WP-06): (29,000 + both legs' `leg_cu`) × 1.10, rounded up to 1,000
pub fn fallback(bv: Venue, c1: u32, sv: Venue, c2: u32) -> u64 {
    (((FALLBACK_OVERHEAD + bv.leg_cu(c1) + sv.leg_cu(c2)) as f64 * MARGIN / 1000.0).ceil() * 1000.0) as u64
}

fn round_up(x: f64) -> u64 { ((x / 1000.0).ceil() * 1000.0) as u64 }

/// ⌈v⌉ × 1.10, rounded up, in integers (21,000 × 1.10 is 23,100, not the float's 23,101)
fn with_margin(v: f64) -> u64 { (v.ceil() as u64 * 11).div_ceil(10) }

/// Where a CU limit came from (attempts.jsonl `tx.cu_src`, decisions' routes): the table's cell (its legs' keys) or the
/// fallback formula
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum CuSrc { Table(String), Fallback }

impl CuSrc {
    pub fn as_str(&self) -> String { match self { CuSrc::Table(k) => format!("table:{k}"), CuSrc::Fallback => "fallback".into() } }
}

/// The table as a run uses it (None: none configured, every route the fallback) and `cu_min_samples`
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct CuModel { pub table: Option<CuTable>, pub min_samples: u64 }

impl Default for CuModel { fn default() -> Self { CuModel { table: None, min_samples: MIN_SAMPLES } } }

impl CuModel {
    /// The CU a route asks before any ATA create or close: from the table when its overhead and both legs have at least
    /// `min_samples` samples, else the fallback formula. `c1`, `c2`: the bins with liquidity each DLMM leg crosses
    pub fn route(&self, bv: Venue, c1: u32, sv: Venue, c2: u32) -> (u64, CuSrc) {
        let ok = |s: Option<&LegStat>| s.filter(|s| s.n >= self.min_samples).and_then(|s| s.p99);
        if let Some(t) = &self.table {
            let (k1, k2) = (leg_key(bv, c1), leg_key(sv, c2));
            let ov = (t.overhead.n >= self.min_samples).then_some(t.overhead.p99).flatten();
            if let (Some(ov), Some(p1), Some(p2)) = (ov, ok(t.legs.get(&k1)), ok(t.legs.get(&k2))) {
                return (round_up(with_margin(ov + p1 + p2 + t.extras.tip) as f64).min(MAX_CU), CuSrc::Table(format!("{k1}+{k2}")));
            }
        }
        (fallback(bv, c1, sv, c2).min(MAX_CU), CuSrc::Fallback)
    }

    /// What an ATA create and an ATA close add to the limit: the table's p99 × 1.10 when it sampled them, else the
    /// fallback constants
    pub fn ata_ops(&self) -> (u64, u64) {
        let x = |v: Option<f64>, fb: u64| v.filter(|v| *v > 0.0).map_or(fb, with_margin);
        let e = self.table.as_ref().map(|t| &t.extras);
        (x(e.map(|e| e.ata_create), FALLBACK_ATA_CREATE), x(e.map(|e| e.ata_close), FALLBACK_ATA_CLOSE))
    }

    /// The transaction's limit: the route's plus the ATA operations it makes, at most 1.4M
    pub fn limit(&self, route: u64, create: bool, close: bool) -> u64 {
        let (c, x) = self.ata_ops();
        (route + if create { c } else { 0 } + if close { x } else { 0 }).min(MAX_CU)
    }

    /// The model from `[builder] cu_table` ("" = none: the fallback) and `cu_min_samples`
    pub fn from_cfg(b: &crate::config::BuilderCfg) -> Result<CuModel, String> {
        let table = if b.cu_table.is_empty() { None } else { Some(CuTable::load(&b.cu_table)?) };
        Ok(CuModel { table, min_samples: b.cu_min_samples })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn stat(n: u64, p99: f64) -> LegStat { LegStat { n, p50: Some(p99 * 0.8), p99: Some(p99) } }

    fn table() -> CuTable {
        let mut legs = BTreeMap::new();
        legs.insert("PumpSwap|na".into(), stat(300, 106_134.0));
        legs.insert("Dlmm|1-2".into(), stat(40, 61_000.5));
        legs.insert("Dlmm|6+".into(), stat(12, 180_000.0));
        legs.insert("RayCpmm|na".into(), stat(84, 29_168.0));
        CuTable { schema: SCHEMA.into(), built_ns: Some(1), source_runs: vec!["seg".into()], source: None, legs,
            overhead: Overhead { n: 31, p99: Some(20_000.0), program: vec![] }, extras: Extras { ata_create: 21_000.0, ata_close: 3_000.0, tip: 150.0 } }
    }

    /// A cell whose overhead and legs are sampled enough comes from the table ((ov + legs + tip) × 1.10, rounded up to
    /// 1,000); a leg (or overhead) under `cu_min_samples` falls back to today's formula; the ATA operations come from the
    /// table's extras when sampled, else the constants; the limit never passes 1.4M
    #[test]
    fn lookup_and_fallback() {
        let m = CuModel { table: Some(table()), min_samples: 30 };
        let (l, src) = m.route(Venue::PumpSwap, 0, Venue::Dlmm, 2);
        assert_eq!(src, CuSrc::Table("PumpSwap|na+Dlmm|1-2".into()));
        assert_eq!(l, 207_000, "(20,000 + 106,134 + 61,000.5 + 150) x 1.10 = 206,013 rounded up to 1,000");
        assert_eq!(src.as_str(), "table:PumpSwap|na+Dlmm|1-2");
        // DLMM 6+ has 12 samples: the fallback
        assert_eq!(m.route(Venue::PumpSwap, 0, Venue::Dlmm, 9), (fallback(Venue::PumpSwap, 0, Venue::Dlmm, 9), CuSrc::Fallback));
        // a venue the table has no cell for
        assert_eq!(m.route(Venue::DammV2, 0, Venue::RayCpmm, 0).1, CuSrc::Fallback);
        // overhead under the floor: every route falls back
        let mut t = table();
        t.overhead.n = 29;
        assert_eq!(CuModel { table: Some(t.clone()), min_samples: 30 }.route(Venue::PumpSwap, 0, Venue::Dlmm, 2).1, CuSrc::Fallback);
        assert_eq!(CuModel { table: Some(t), min_samples: 29 }.route(Venue::PumpSwap, 0, Venue::Dlmm, 2).1, CuSrc::Table("PumpSwap|na+Dlmm|1-2".into()));
        // the ATA operations
        assert_eq!(m.ata_ops(), (23_100, 3_300));
        assert_eq!(m.limit(206_000, true, true), 206_000 + 23_100 + 3_300);
        assert_eq!(m.limit(206_000, true, false), 206_000 + 23_100);
        assert_eq!(CuModel::default().ata_ops(), (FALLBACK_ATA_CREATE, FALLBACK_ATA_CLOSE));
        let mut t = table();
        t.extras.ata_close = 0.0;
        assert_eq!(CuModel { table: Some(t), min_samples: 30 }.ata_ops(), (23_100, FALLBACK_ATA_CLOSE), "a close never sampled");
        assert_eq!(m.limit(1_390_000, true, true), MAX_CU);
        // no table: today's formula, bit for bit (engine.rs before WP-06)
        for (bv, c1, sv, c2) in [(Venue::PumpSwap, 0, Venue::Dlmm, 3), (Venue::Dlmm, 7, Venue::RayCpmm, 0), (Venue::DammV2, 0, Venue::RayAmmV4, 0)] {
            let want = (((29_000 + bv.leg_cu(c1) + sv.leg_cu(c2)) as f64 * 1.10 / 1000.0).ceil() * 1000.0) as u64;
            assert_eq!(CuModel::default().route(bv, c1, sv, c2), (want, CuSrc::Fallback));
        }
    }

    /// The toolkit's keys: venue names as the engine serializes them, DLMM by bins-crossed bucket
    #[test]
    fn keys_are_the_toolkits() {
        assert_eq!((leg_key(Venue::PumpSwap, 9), leg_key(Venue::RayCpmm, 0), leg_key(Venue::RayAmmV4, 0), leg_key(Venue::DammV2, 0)),
            ("PumpSwap|na".into(), "RayCpmm|na".into(), "RayAmmV4|na".into(), "DammV2|na".into()));
        assert_eq!([0, 1, 2, 3, 5, 6, 200].map(|c| leg_key(Venue::Dlmm, c)), ["Dlmm|0", "Dlmm|1-2", "Dlmm|1-2", "Dlmm|3-5", "Dlmm|3-5", "Dlmm|6+", "Dlmm|6+"].map(String::from));
    }

    /// the toolkit's file reads back (its golden synthetic segment's table, testdata copy of tools/arbx-report's golden
    /// report section), fractional quantiles included; another schema is refused
    #[test]
    fn reads_the_toolkits_table() {
        let text = r#"{"built_ns": 1791100006000000000, "cells": {"PumpSwap|Dlmm|1-2|false": {"leg_samples": [8, 1], "limit": null, "src": "fallback"}},
            "extras": {"ata_close": 0, "ata_create": 0, "tip": 150}, "legs": {"Dlmm|1-2": {"n": 1, "p50": 60000, "p99": 60000},
            "Dlmm|unk": {"n": 4, "p50": 61250, "p99": 61497.5}, "PumpSwap|na": {"n": 8, "p50": 41014, "p99": 41014}},
            "overhead": {"n": 2, "p99": 20000, "program": ["4PXLvTZcjUkUcht5oEy9LghFNm8nwLd89K3ohyUPEfMa"]}, "schema": "arbx.cu-table/1.0", "source_runs": ["synth-p1"]}"#;
        let t = CuTable::parse(text).unwrap();
        assert_eq!((t.legs.len(), t.legs["Dlmm|unk"].p99, t.overhead.n, t.extras.tip), (3, Some(61497.5), 2, 150.0));
        // 8 PumpSwap samples, 2 of the overhead: the fallback at 30
        assert_eq!(CuModel { table: Some(t.clone()), min_samples: 30 }.route(Venue::PumpSwap, 0, Venue::Dlmm, 1).1, CuSrc::Fallback);
        assert_eq!(CuModel { table: Some(t), min_samples: 1 }.route(Venue::PumpSwap, 0, Venue::Dlmm, 1).0, 134_000, "121,164 x 1.10 = 133,281");
        assert!(CuTable::parse(&text.replace("arbx.cu-table/1.0", "arbx.cu-table/2.0")).is_err());
        // the model round-trips through its journal form
        let m = CuModel { table: Some(table()), min_samples: 30 };
        assert_eq!(serde_json::from_value::<CuModel>(serde_json::to_value(&m).unwrap()).unwrap(), m);
    }

    /// The shipped table (data/cu-table.json) loads, says where it came from, and asks at least the measured venue CU
    #[test]
    fn the_shipped_table() {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/data/cu-table.json");
        let t = CuTable::load(path).unwrap();
        assert!(t.source.is_some() || !t.source_runs.is_empty(), "provenance");
        for (k, s) in &t.legs { assert!(s.n > 0 && s.p99.is_some_and(|p| p > 0.0), "{k}"); }
    }
}
