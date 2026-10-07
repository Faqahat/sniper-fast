//! WP-11 (PLAN WP-11, owner 2026-10-07): the experiment framework. Arms of an experiment run side by side in the same
//! live run, assigned per decision by hash, so a tip share or a size cap is compared against its control arm under the
//! same market instead of in back-to-back tests that market swings confound (FT-006, FT-007).
//!
//! - **Config** (`[experiments]`): `seed`, and one table per experiment with `enabled`, its arms, `weights` (empty: equal)
//!   and a scope (`scope_max_band`: bands 0 to it; `scope_kinds`: the evaluation kinds `commit`, `quiescent`, `timeout`,
//!   `fork`; `scope_venues`: a route through one of these venues; empty lists: all). Off unless a table is `enabled`; left
//!   out of the serialized config while off (a disabled table too), so a config without them hashes as before (meta.json
//!   `config.normalized_sha256`, exec_init `cfg_sha256`, engine_init): replays of older runs and the campaigns'
//!   frozen-config checks are unchanged.
//! - **The first arm listed is the control** (experiments.jsonl `control`; the toolkit compares every other arm with it).
//! - **The unit is the decision** (decisions.jsonl `decision`). Its arm in experiment E is
//!   `pick(xxh3_64_with_seed(E's name, 0xff, decision as u64 LE; seed), weights)`: a pure function of the seed, the
//!   experiment and the decision id, so a replay (same ids) assigns the same arms, and two experiments with the same seed
//!   assign independently (their names differ in the hash: a factorial design). The seed a run assigns with is the
//!   config's mixed with the segment's name (`Experiments::for_run`: decision ids restart each segment, so the segments
//!   of a campaign do not repeat one id-to-arm pattern); it is journaled with engine_init, so a replay assigns the run's.
//! - **Where each arm applies**:
//!   - `x4` (tip share): replaces `[tips] shares` for the route's band when the band is in scope (`scope_max_band`, by
//!     default 2: edges under 1,000,000 lamports with the default `[bands]`). `floor` and `cap` stay; the contested table is
//!     untouched; the BAM floor (`[send_policy.bam]`) still raises BAM-led bids on top. The engine's fee estimate and the
//!     executor's tip read the same arm (`tip::TipModel::tip_arm`), so a decision's net and the executor's stay one number.
//!   - `size` (size cap): caps the engine's size search (`price_route`: the ladder's rungs above the cap are left out and
//!     the locator's optimum is clamped to it) at the arm, and at the executor's cap below it (`[canary] size_sol`,
//!     `[live] max_size_sol`, the bankroll on the money view of the last journaled decision-point record, which a replay's
//!     offline executor holds too), so the decision priced is the trade sent. The executor still re-quotes at its own cap
//!     (the first decision of a segment, before any record; a money view that moved since): no trade is ever above it. Its
//!     scope is the evaluation kind only (a band depends on the size).
//!   - `margin` (on-chain margin floor, F23 / OD-5): replaces `[send_policy] margin_floor` (the min_profit's floor and
//!     the BAM bid's bar room).
//!   - `x2` (send delay): a tokio sleep on the send task before the fire, never on the engine thread; recorded on
//!     would-sends too (nothing is fired there). The SendGate is not read again after the sleep: a copy can leave up to
//!     20 ms after a pause or a stop (as one waiting in the rate queue can); the on-chain guard holds either way.
//!   - `x8` (block assignment, 10-minute blocks): needs WP-14's discovery connection, not built: `enabled = true` is
//!     refused. The block assignment ([`block_of`]) is here for it.
//! - **Records**: decisions.jsonl `experiments` holds every arm assigned to the decision (the randomization, scope
//!   aside: the balance check's unit); attempts.jsonl `experiments` holds the arms that applied to the attempt (in
//!   scope), and `tip.arm` the share when X4's arm replaced the band's; experiments.jsonl holds one `config` line per
//!   enabled experiment at the run's start (and `block_switch` lines for block experiments); the file is opened at its
//!   first line, so a run without experiments writes no such file.
use crate::venues::Venue;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

/// experiments.jsonl's schema (MEASUREMENT §4.45)
pub const SCHEMA: &str = "arbx.experiments/1.0";
/// the evaluation kinds (decisions.jsonl `kind`): every arbx decision is state-triggered
pub const KINDS: [&str; 4] = ["commit", "quiescent", "timeout", "fork"];
/// the band count (src/bands.rs: 0-4)
pub const N_BANDS: u8 = 5;
/// the most arms an experiment may have
pub const MAX_ARMS: usize = 8;
/// PLAN WP-11 (risk): a delay arm costs a little landing; it is bounded at 20 ms
pub const MAX_DELAY_MS: u32 = 20;

// ------------------------------------------------------------------------------------------------ config

/// `[experiments]`: the seed and one table per experiment (each off unless `enabled`)
#[derive(Debug, Clone, Default, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ExperimentsCfg {
    /// the assignment's seed (any u64; a campaign keeps one: segments' decision ids restart, their arms follow the ids)
    #[serde(default)]
    pub seed: u64,
    #[serde(default, skip_serializing_if = "X2Cfg::off")]
    pub x2: X2Cfg,
    #[serde(default, skip_serializing_if = "X4Cfg::off")]
    pub x4: X4Cfg,
    #[serde(default, skip_serializing_if = "SizeArmCfg::off")]
    pub size: SizeArmCfg,
    #[serde(default, skip_serializing_if = "MarginArmCfg::off")]
    pub margin: MarginArmCfg,
    #[serde(default, skip_serializing_if = "X8Cfg::off")]
    pub x8: X8Cfg,
}

/// `[experiments.x2]`: the send delay, ms (a tokio sleep on the send task before the fire)
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct X2Cfg {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default = "x2_arms")]
    pub arms_ms: Vec<u32>,
    #[serde(default)]
    pub weights: Vec<f64>,
    #[serde(default = "all_bands")]
    pub scope_max_band: u8,
    #[serde(default)]
    pub scope_kinds: Vec<String>,
    #[serde(default)]
    pub scope_venues: Vec<String>,
}
fn x2_arms() -> Vec<u32> { vec![0, 5, 10, 20] }
fn all_bands() -> u8 { N_BANDS - 1 }
impl Default for X2Cfg {
    fn default() -> Self { X2Cfg { enabled: false, arms_ms: x2_arms(), weights: vec![], scope_max_band: all_bands(), scope_kinds: vec![], scope_venues: vec![] } }
}
impl X2Cfg { pub fn off(&self) -> bool { !self.enabled } }

/// `[experiments.x4]`: the tip share of the edge, replacing `[tips] shares` in the bands up to `scope_max_band`
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct X4Cfg {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default = "x4_arms")]
    pub arms: Vec<f64>,
    #[serde(default)]
    pub weights: Vec<f64>,
    /// bands 0 to this one (default 2: edges under 1,000,000 lamports with the default `[bands]`)
    #[serde(default = "x4_max_band")]
    pub scope_max_band: u8,
    #[serde(default)]
    pub scope_kinds: Vec<String>,
    #[serde(default)]
    pub scope_venues: Vec<String>,
}
fn x4_arms() -> Vec<f64> { vec![0.7, 0.35] }
fn x4_max_band() -> u8 { 2 }
impl Default for X4Cfg {
    fn default() -> Self { X4Cfg { enabled: false, arms: x4_arms(), weights: vec![], scope_max_band: x4_max_band(), scope_kinds: vec![], scope_venues: vec![] } }
}
impl X4Cfg { pub fn off(&self) -> bool { !self.enabled } }

/// `[experiments.size]`: the size cap of the engine's size search, SOL
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct SizeArmCfg {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default = "size_arms")]
    pub arms_max_sol: Vec<f64>,
    #[serde(default)]
    pub weights: Vec<f64>,
    /// the evaluation kinds (a band or a venue depends on the size the cap picks: neither scopes this experiment)
    #[serde(default)]
    pub scope_kinds: Vec<String>,
}
fn size_arms() -> Vec<f64> { vec![0.05, 0.2] }
impl Default for SizeArmCfg { fn default() -> Self { SizeArmCfg { enabled: false, arms_max_sol: size_arms(), weights: vec![], scope_kinds: vec![] } } }
impl SizeArmCfg { pub fn off(&self) -> bool { !self.enabled } }

/// `[experiments.margin]`: the on-chain margin floor, lamports (`[send_policy] margin_floor`; F23, OD-5)
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct MarginArmCfg {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default = "margin_arms")]
    pub arms: Vec<u64>,
    #[serde(default)]
    pub weights: Vec<f64>,
    #[serde(default = "all_bands")]
    pub scope_max_band: u8,
    #[serde(default)]
    pub scope_kinds: Vec<String>,
    #[serde(default)]
    pub scope_venues: Vec<String>,
}
fn margin_arms() -> Vec<u64> { vec![1, 2_000] }
impl Default for MarginArmCfg {
    fn default() -> Self { MarginArmCfg { enabled: false, arms: margin_arms(), weights: vec![], scope_max_band: all_bands(), scope_kinds: vec![], scope_venues: vec![] } }
}
impl MarginArmCfg { pub fn off(&self) -> bool { !self.enabled } }

/// `[experiments.x8]`: blocks of `block_min` minutes with WP-14's discovery connection on or off (not built: refused on)
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct X8Cfg {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default = "x8_block")]
    pub block_min: u64,
}
fn x8_block() -> u64 { 10 }
impl Default for X8Cfg { fn default() -> Self { X8Cfg { enabled: false, block_min: x8_block() } } }
impl X8Cfg { pub fn off(&self) -> bool { !self.enabled } }

impl ExperimentsCfg {
    /// every experiment off: nothing is assigned, recorded or serialized
    pub fn off(&self) -> bool { !(self.x2.enabled || self.x4.enabled || self.size.enabled || self.margin.enabled || self.x8.enabled) }

    /// What `Config::parse` refuses (only the enabled tables are checked: a disabled one changes nothing). The size arms
    /// are checked against the ladder (`[strategy] sizes_sol`) and the executor's static caps: an arm above `[live]
    /// max_size_sol` (or `[canary] size_sol` with the canary enabled) or the ladder's top rung would trade at that cap, so
    /// two arms would not differ
    pub fn check(&self, c: &crate::config::Config) -> Result<(), String> {
        let e = |t: &str, m: String| Err(format!("[experiments.{t}] {m}"));
        if self.x2.enabled {
            let x = &self.x2;
            arms_check("x2", &x.arms_ms, &x.weights)?;
            if let Some(a) = x.arms_ms.iter().find(|a| **a > MAX_DELAY_MS) { return e("x2", format!("arms_ms: {a} ms is above {MAX_DELAY_MS} ms (PLAN WP-11: a delay arm is bounded)")); }
            Scope::parse("x2", x.scope_max_band, &x.scope_kinds, &x.scope_venues)?;
        }
        if self.x4.enabled {
            let x = &self.x4;
            arms_check("x4", &x.arms, &x.weights)?;
            if x.arms.iter().any(|s| !s.is_finite() || !(0.0..=1.0).contains(s)) { return e("x4", format!("arms {:?}: shares of the edge, 0..1", x.arms)); }
            Scope::parse("x4", x.scope_max_band, &x.scope_kinds, &x.scope_venues)?;
        }
        if self.size.enabled {
            let x = &self.size;
            arms_check("size", &x.arms_max_sol, &x.weights)?;
            if x.arms_max_sol.iter().any(|s| !s.is_finite() || *s <= 0.0) { return e("size", format!("arms_max_sol {:?}: sizes in SOL, > 0", x.arms_max_sol)); }
            let rungs = &c.strategy.sizes_sol;
            let (lo, top) = (rungs.iter().copied().fold(f64::INFINITY, f64::min), rungs.iter().copied().fold(0.0, f64::max));
            for &a in &x.arms_max_sol {
                if a < lo { return e("size", format!("arm {a} SOL is below the ladder's smallest rung {lo} ([strategy] sizes_sol): it would price nothing")); }
                if a > top { return e("size", format!("arm {a} SOL is above the ladder's top rung {top} ([strategy] sizes_sol): it would trade at {top}")); }
                if a > c.live.max_size_sol { return e("size", format!("arm {a} SOL is above [live] max_size_sol {}: it would trade at that cap", c.live.max_size_sol)); }
                if c.canary.enabled && a > c.canary.size_sol { return e("size", format!("arm {a} SOL is above [canary] size_sol {}: it would trade at that cap", c.canary.size_sol)); }
            }
            Scope::parse("size", all_bands(), &x.scope_kinds, &[])?;
        }
        if self.margin.enabled {
            let x = &self.margin;
            arms_check("margin", &x.arms, &x.weights)?;
            if x.arms.contains(&0) { return e("margin", "arms: a margin floor >= 1 (a landed bundle must clear tip + fee + at least 1 lamport)".into()); }
            Scope::parse("margin", x.scope_max_band, &x.scope_kinds, &x.scope_venues)?;
        }
        if self.x8.enabled { return e("x8", "enabled = true is refused: X8 switches WP-14's discovery connection, which is not built".into()); }
        Ok(())
    }

    /// The compiled experiments a run applies (None: all off). Call after `check`
    pub fn compile(&self) -> Option<Experiments> {
        if self.off() { return None; }
        let scope = |b: u8, k: &[String], v: &[String], name: &str| Scope::parse(name, b, k, v).expect("checked by Config::parse");
        let w = |w: &[f64], n: usize| if w.is_empty() { vec![1.0; n] } else { w.to_vec() };
        let x = Experiments {
            seed: self.seed,
            config_seed: None,
            run: None,
            x2: self.x2.enabled.then(|| Exp { arms: self.x2.arms_ms.clone(), weights: w(&self.x2.weights, self.x2.arms_ms.len()),
                scope: scope(self.x2.scope_max_band, &self.x2.scope_kinds, &self.x2.scope_venues, "x2") }),
            x4: self.x4.enabled.then(|| Exp { arms: self.x4.arms.clone(), weights: w(&self.x4.weights, self.x4.arms.len()),
                scope: scope(self.x4.scope_max_band, &self.x4.scope_kinds, &self.x4.scope_venues, "x4") }),
            size: self.size.enabled.then(|| Exp { arms: self.size.arms_max_sol.clone(), weights: w(&self.size.weights, self.size.arms_max_sol.len()),
                scope: scope(all_bands(), &self.size.scope_kinds, &[], "size") }),
            margin: self.margin.enabled.then(|| Exp { arms: self.margin.arms.clone(), weights: w(&self.margin.weights, self.margin.arms.len()),
                scope: scope(self.margin.scope_max_band, &self.margin.scope_kinds, &self.margin.scope_venues, "margin") }),
        };
        (!x.is_empty()).then_some(x)
    }

    /// `arbx check`'s line
    pub fn describe(&self, c: &crate::config::Config) -> String {
        let Some(x) = self.compile() else { return "experiments (WP-11): off (no arm is assigned: decisions and attempts record `experiments` empty)".into() };
        let wts = |w: &[f64]| w.iter().map(|v| format!("{v}")).collect::<Vec<_>>().join(":");
        let mut parts = Vec::new();
        if let Some(e) = &x.x4 {
            parts.push(format!("x4 tip share arms {:?} (control {}; weights {}) replace [tips] shares {:?} in bands 0-{} ({}), floor {} and cap {} kept{}{}", e.arms, e.arms[0], wts(&e.weights),
                c.tips.shares, e.scope.max_band, band_range(&c.bands.edges, e.scope.max_band), c.tips.floor, c.tips.cap,
                if c.send_policy.bam.enabled { ", the BAM floor raises BAM-led bids on top" } else { "" }, e.scope.describe_rest()));
        }
        if let Some(e) = &x.size {
            let canary = if c.canary.enabled { format!("[canary] size_sol {}, ", c.canary.size_sol) } else { String::new() };
            parts.push(format!("size cap arms {:?} SOL (control {}; weights {}) on the engine's size search (rungs {:?} up to the arm), never above {canary}[live] max_size_sol {}{}{}",
                e.arms, e.arms[0], wts(&e.weights), c.strategy.sizes_sol, c.live.max_size_sol,
                if c.live.bankroll_share > 0.0 { format!(" or the bankroll ({:.0}% of the liquid SOL - {} SOL, at most the WSOL)", c.live.bankroll_share * 100.0, c.live.bankroll_reserve_sol) } else { String::new() },
                e.scope.describe_rest()));
        }
        if let Some(e) = &x.margin {
            parts.push(format!("margin floor arms {:?} lamports (control {}; weights {}) replace [send_policy] margin_floor {} in bands 0-{}{}", e.arms, e.arms[0], wts(&e.weights),
                c.send_policy.margin_floor, e.scope.max_band, e.scope.describe_rest()));
        }
        if let Some(e) = &x.x2 {
            parts.push(format!("x2 send delay arms {:?} ms (control {}; weights {}) slept on the send task before the fire (never the engine thread), bands 0-{}{}", e.arms, e.arms[0], wts(&e.weights),
                e.scope.max_band, e.scope.describe_rest()));
        }
        let cells: usize = [x.x2.as_ref().map(|e| e.arms.len()), x.x4.as_ref().map(|e| e.arms.len()), x.size.as_ref().map(|e| e.arms.len()),
            x.margin.as_ref().map(|e| e.arms.len())].into_iter().flatten().product();
        format!("experiments (WP-11): seed {} (mixed with each segment's name); {}; each decision's arm is xxh3(seed, experiment, decision id): replayable, the experiments independent ({} cells)",
            x.seed, parts.join("; "), cells)
    }
}

/// the band edges' range of bands 0..=max as text ("edge < 1000000")
fn band_range(edges: &[i64], max: u8) -> String {
    if max as usize >= edges.len() { "every edge".into() } else { format!("edge < {}", edges[max as usize]) }
}

/// an experiment's arms and weights: 2 to `MAX_ARMS` distinct arms, weights empty (equal) or one positive weight per arm
fn arms_check<T: PartialEq + std::fmt::Debug>(name: &str, arms: &[T], weights: &[f64]) -> Result<(), String> {
    if !(2..=MAX_ARMS).contains(&arms.len()) { return Err(format!("[experiments.{name}] {} arms: 2 to {MAX_ARMS} (an experiment compares arms)", arms.len())); }
    for (i, a) in arms.iter().enumerate() {
        if arms[..i].contains(a) { return Err(format!("[experiments.{name}] arm {a:?} twice: the records could not tell the arms apart")); }
    }
    if !weights.is_empty() && weights.len() != arms.len() { return Err(format!("[experiments.{name}] weights: one per arm ({}), not {}", arms.len(), weights.len())); }
    if weights.iter().any(|w| !w.is_finite() || *w <= 0.0) { return Err(format!("[experiments.{name}] weights {weights:?}: each > 0")); }
    if weights.iter().any(|w| *w > 1e9) { return Err(format!("[experiments.{name}] weights {weights:?}: each at most 1e9 (relative weights)")); }
    Ok(())
}

// ------------------------------------------------------------------------------------------------ scope

/// One experiment's scope: bands 0..=`max_band`, the evaluation kinds (a bit per [`KINDS`]) and the venues (a bit per
/// `Venue::ALL`; a route is in when one of its legs trades on one)
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Scope { pub max_band: u8, pub kinds: u8, pub venues: u16 }

const ALL_KINDS: u8 = (1 << KINDS.len()) - 1;
const ALL_VENUES: u16 = (1 << Venue::ALL.len()) - 1;

impl Scope {
    /// every band, kind and venue
    pub const ALL: Scope = Scope { max_band: N_BANDS - 1, kinds: ALL_KINDS, venues: ALL_VENUES };

    /// from a table's `scope_max_band`, `scope_kinds` and `scope_venues` (the seed lists' venue names: PumpSwap, RayCPMM,
    /// RayAMMv4, DLMM, DAMMv2, RayCLMM, Whirlpool)
    pub fn parse(name: &str, max_band: u8, kinds: &[String], venues: &[String]) -> Result<Scope, String> {
        if max_band >= N_BANDS { return Err(format!("[experiments.{name}] scope_max_band {max_band}: a band 0..{}", N_BANDS - 1)); }
        let mut k = 0u8;
        for s in kinds {
            let Some(i) = KINDS.iter().position(|x| x == s) else { return Err(format!("[experiments.{name}] scope_kinds: {s:?} is not one of {KINDS:?}")) };
            k |= 1 << i;
        }
        let mut v = 0u16;
        for s in venues {
            let Some(x) = Venue::parse(s) else { return Err(format!("[experiments.{name}] scope_venues: {s:?} is not a venue (PumpSwap, RayCPMM, RayAMMv4, DLMM, DAMMv2, RayCLMM, Whirlpool)")) };
            v |= 1 << venue_bit(x);
        }
        Ok(Scope { max_band, kinds: if kinds.is_empty() { ALL_KINDS } else { k }, venues: if venues.is_empty() { ALL_VENUES } else { v } })
    }
    /// the evaluation kind is in scope
    pub fn kind_ok(&self, kind: &str) -> bool { KINDS.iter().position(|k| *k == kind).is_some_and(|i| self.kinds & (1 << i) != 0) }
    /// one of the route's legs trades on a venue in scope
    pub fn venue_ok(&self, buy: Venue, sell: Venue) -> bool { self.venues & (1 << venue_bit(buy) | 1 << venue_bit(sell)) != 0 }
    /// the route is in scope, its band aside
    pub fn route_ok(&self, kind: &str, buy: Venue, sell: Venue) -> bool { self.kind_ok(kind) && self.venue_ok(buy, sell) }
    /// the band is in scope
    pub fn band_ok(&self, band: u8) -> bool { band <= self.max_band }
    /// the route at this band is in scope
    pub fn covers(&self, band: u8, kind: &str, buy: Venue, sell: Venue) -> bool { self.band_ok(band) && self.route_ok(kind, buy, sell) }
    /// experiments.jsonl's `scope`
    pub fn json(&self) -> Value {
        let kinds: Vec<&str> = KINDS.iter().enumerate().filter(|(i, _)| self.kinds & (1 << i) != 0).map(|x| *x.1).collect();
        let venues: Vec<&str> = Venue::ALL.iter().filter(|v| self.venues & (1 << venue_bit(**v)) != 0).map(|v| crate::replay::venue_name(*v)).collect();
        json!({ "max_band": self.max_band, "kinds": kinds, "venues": venues })
    }
    /// the kind and venue limits, if any, for `arbx check`
    fn describe_rest(&self) -> String {
        let j = self.json();
        let mut s = String::new();
        if self.kinds != ALL_KINDS { s.push_str(&format!(", kinds {}", j["kinds"])); }
        if self.venues != ALL_VENUES { s.push_str(&format!(", venues {}", j["venues"])); }
        s
    }
}

fn venue_bit(v: Venue) -> u32 { Venue::ALL.iter().position(|x| *x == v).unwrap_or(0) as u32 }

// ------------------------------------------------------------------------------------------------ assignment

/// The hash an arm is drawn from: xxh3-64 of the experiment's name, a 0xff separator and the unit (the decision id,
/// little-endian), seeded with the run's seed
pub fn unit_hash(seed: u64, experiment: &str, unit: u64) -> u64 {
    let mut b = [0u8; 48];
    let n = experiment.len().min(39);
    b[..n].copy_from_slice(&experiment.as_bytes()[..n]);
    b[n] = 0xff;
    b[n + 1..n + 9].copy_from_slice(&unit.to_le_bytes());
    xxhash_rust::xxh3::xxh3_64_with_seed(&b[..n + 9], seed)
}

/// the arm a hash draws by the weights: the hash's top 53 bits as a uniform draw over the weights' sum
pub fn pick(h: u64, weights: &[f64]) -> usize {
    let total: f64 = weights.iter().sum();
    let u = (h >> 11) as f64 * (total / 9_007_199_254_740_992.0);
    let mut acc = 0.0;
    for (i, w) in weights.iter().enumerate() {
        acc += w;
        if u < acc { return i; }
    }
    weights.len().saturating_sub(1)
}

/// the arm (its index) experiment `experiment` assigns unit `unit` (a decision id) under `seed`
pub fn assign(seed: u64, experiment: &str, unit: u64, weights: &[f64]) -> usize { pick(unit_hash(seed, experiment, unit), weights) }

/// A block experiment's block at engine time `t_ns` (X8: `block_min`-minute blocks, each a whole block on one arm): its
/// index, its arm, and its bounds (ns)
pub fn block_of(seed: u64, experiment: &str, t_ns: u64, block_ns: u64, weights: &[f64]) -> (u64, usize, u64, u64) {
    let id = t_ns / block_ns.max(1);
    (id, assign(seed, experiment, id, weights), id * block_ns, (id + 1) * block_ns)
}

/// experiments.jsonl's `block_switch` line (a block experiment's arm changed at `t_ns`)
pub fn block_switch_json(t_ns: u64, experiment: &str, seed: u64, block: (u64, usize, u64, u64), arm: Value) -> Value {
    json!({ "t_ns": t_ns, "experiment": experiment, "event": "block_switch", "seed": seed, "block": { "id": block.0, "arm_index": block.1, "arm": arm,
        "from_ns": block.2, "to_ns": block.3 } })
}

/// One compiled experiment: its arms, weights (one per arm, positive) and scope
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Exp<T> { pub arms: Vec<T>, pub weights: Vec<f64>, pub scope: Scope }

impl<T: Copy> Exp<T> {
    fn arm(&self, seed: u64, name: &str, unit: u64) -> Arm<T> {
        let i = assign(seed, name, unit, &self.weights);
        Arm { idx: i as u8, value: self.arms[i], scope: self.scope }
    }
    /// one positive weight per arm (at most 1e9), 1 to `MAX_ARMS` arms, every arm within `ok` (what `ExperimentsCfg::compile`
    /// makes; a record read back must be)
    fn valid(&self, ok: impl Fn(&T) -> bool) -> bool {
        (1..=MAX_ARMS).contains(&self.arms.len()) && self.weights.len() == self.arms.len() && self.weights.iter().all(|w| w.is_finite() && *w > 0.0 && *w <= 1e9)
            && self.scope.max_band < N_BANDS && self.arms.iter().all(ok)
    }
}

/// The experiments a run applies: journaled with engine_init (a replay assigns as the run did) and written to meta.json
/// `experiments`
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct Experiments {
    /// the seed the arms are drawn with: the config's, mixed with the segment's name by `for_run`
    pub seed: u64,
    /// `for_run`: the config's seed and the segment the seed was mixed with (None: not mixed, e.g. a test)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub config_seed: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub run: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub x2: Option<Exp<u32>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub x4: Option<Exp<f64>>,
    /// the arms in SOL (as configured: the records' labels); a cap of `(sol × 1e9).round()` lamports
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub size: Option<Exp<f64>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub margin: Option<Exp<u64>>,
}

/// the records' key of each experiment (decisions / attempts `experiments`), and its experiments.jsonl name
pub const KEYS: [(&str, &str); 4] = [("x2", "x2_delay_ms"), ("x4", "x4_share"), ("size", "size_max_sol"), ("margin", "margin")];

impl Experiments {
    /// nothing enabled
    pub fn is_empty(&self) -> bool { self.x2.is_none() && self.x4.is_none() && self.size.is_none() && self.margin.is_none() }

    /// The experiments as segment `run` assigns them (`arbx run`): the seed becomes xxh3-64 of the segment's name seeded
    /// with the config's seed, so each segment of a campaign draws its own id-to-arm pattern (decision ids restart each
    /// segment); the config's seed and the name stay recorded (engine_init, meta.json, experiments.jsonl)
    pub fn for_run(mut self, run: &str) -> Experiments {
        let base = self.config_seed.unwrap_or(self.seed);
        self.seed = xxhash_rust::xxh3::xxh3_64_with_seed(run.as_bytes(), base);
        self.config_seed = Some(base);
        self.run = Some(run.to_string());
        self
    }

    /// every experiment's arms and weights are whole and within `ExperimentsCfg::check`'s bounds (an engine_init record
    /// read back: else the record is not read)
    pub fn valid(&self) -> bool {
        self.x2.as_ref().is_none_or(|e| e.valid(|d| *d <= MAX_DELAY_MS)) && self.x4.as_ref().is_none_or(|e| e.valid(|s| s.is_finite() && (0.0..=1.0).contains(s)))
            && self.size.as_ref().is_none_or(|e| e.valid(|s| s.is_finite() && *s > 0.0)) && self.margin.as_ref().is_none_or(|e| e.valid(|f| *f >= 1))
    }

    /// What every enabled experiment assigns decision `id`
    pub fn assign(&self, id: u64) -> Arms {
        Arms { x2: self.x2.as_ref().map(|e| e.arm(self.seed, "x2", id)), x4: self.x4.as_ref().map(|e| e.arm(self.seed, "x4", id)),
            size: self.size.as_ref().map(|e| e.arm(self.seed, "size", id)), margin: self.margin.as_ref().map(|e| e.arm(self.seed, "margin", id)) }
    }

    /// experiments.jsonl's `config` lines (one per enabled experiment) at engine time `t_ns`
    pub fn config_lines(&self, t_ns: u64) -> Vec<Value> {
        let line = |name: &str, key: &str, arms: Value, weights: &[f64], scope: &Scope, unit: &str| json!({ "t_ns": t_ns, "experiment": name, "event": "config",
            "key": key, "control": arms[0].clone(), "arms": arms, "weights": weights, "seed": self.seed, "config_seed": self.config_seed, "run": self.run,
            "scope": scope.json(), "unit": "decision", "arm_unit": unit,
            "assignment": "xxh3_64_with_seed(name ++ 0xff ++ decision_le, seed): the top 53 bits over the weights; the first arm is the control" });
        let mut v = Vec::new();
        if let Some(e) = &self.x2 { v.push(line("x2", "x2_delay_ms", json!(e.arms), &e.weights, &e.scope, "ms")); }
        if let Some(e) = &self.x4 { v.push(line("x4", "x4_share", json!(e.arms), &e.weights, &e.scope, "share of the edge")); }
        if let Some(e) = &self.size { v.push(line("size", "size_max_sol", json!(e.arms), &e.weights, &e.scope, "SOL")); }
        if let Some(e) = &self.margin { v.push(line("margin", "margin", json!(e.arms), &e.weights, &e.scope, "lamports")); }
        v
    }
}

/// One assigned arm: its index, its value and its experiment's scope
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Arm<T> { pub idx: u8, pub value: T, pub scope: Scope }

/// X4's arm as the tip model applies it: the share replaces the band's in bands 0..=`max_band` (`tip::TipModel::tip_arm`)
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ShareArm { pub share: f64, pub max_band: u8 }

/// What the enabled experiments assigned one decision (`Experiments::assign`): carried by the engine's opportunity and
/// the executor's `RouteIn`. Default: none (experiments off, a probe)
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Arms {
    pub x2: Option<Arm<u32>>,
    pub x4: Option<Arm<f64>>,
    pub size: Option<Arm<f64>>,
    pub margin: Option<Arm<u64>>,
}

impl Arms {
    /// no experiment assigned anything
    pub fn is_empty(&self) -> bool { self.x2.is_none() && self.x4.is_none() && self.size.is_none() && self.margin.is_none() }

    /// decisions.jsonl `experiments`: every arm assigned (the randomization; scope aside). Empty when off
    pub fn assigned_json(&self) -> serde_json::Map<String, Value> {
        let mut m = serde_json::Map::new();
        if let Some(a) = &self.x2 { m.insert("x2_delay_ms".into(), json!(a.value)); }
        if let Some(a) = &self.x4 { m.insert("x4_share".into(), json!(a.value)); }
        if let Some(a) = &self.size { m.insert("size_max_sol".into(), json!(a.value)); }
        if let Some(a) = &self.margin { m.insert("margin".into(), json!(a.value)); }
        m
    }

    /// the decision digest's bytes (folded only when some experiment is on)
    pub fn digest_bytes(&self) -> [u8; 8] {
        let i = |x: Option<u8>| x.map_or(0xff, |v| v);
        [i(self.x2.map(|a| a.idx)), i(self.x4.map(|a| a.idx)), i(self.size.map(|a| a.idx)), i(self.margin.map(|a| a.idx)), 0, 0, 0, 0]
    }

    /// X4's arm for a route of evaluation kind `kind` through `buy` and `sell` (the band is the tip model's to check: the
    /// share applies in bands 0..=`max_band`)
    pub fn share_arm(&self, kind: &str, buy: Venue, sell: Venue) -> Option<ShareArm> {
        self.x4.filter(|a| a.scope.route_ok(kind, buy, sell)).map(|a| ShareArm { share: a.value, max_band: a.scope.max_band })
    }

    /// the size arm's cap (lamports) for an evaluation of kind `kind`
    pub fn size_cap(&self, kind: &str) -> Option<u64> { self.size.filter(|a| a.scope.kind_ok(kind)).map(|a| sol_lamports(a.value)) }

    /// the margin arm's floor for a route at `band`
    pub fn margin_floor(&self, band: u8, kind: &str, buy: Venue, sell: Venue) -> Option<u64> {
        self.margin.filter(|a| a.scope.covers(band, kind, buy, sell)).map(|a| a.value)
    }

    /// the delay arm (ms) for a route at `band`
    pub fn delay_ms(&self, band: u8, kind: &str, buy: Venue, sell: Venue) -> Option<u32> {
        self.x2.filter(|a| a.scope.covers(band, kind, buy, sell)).map(|a| a.value)
    }

    /// attempts.jsonl `experiments`: the arms that applied to an attempt at `band` (X4's when it replaced the band's share:
    /// `x4_applied`)
    pub fn applied_json(&self, band: u8, kind: &str, buy: Venue, sell: Venue, x4_applied: Option<f64>) -> Value {
        let mut m = serde_json::Map::new();
        if let Some(d) = self.delay_ms(band, kind, buy, sell) { m.insert("x2_delay_ms".into(), json!(d)); }
        if let Some(s) = x4_applied { m.insert("x4_share".into(), json!(s)); }
        if let Some(a) = self.size.filter(|a| a.scope.kind_ok(kind)) { m.insert("size_max_sol".into(), json!(a.value)); }
        if let Some(f) = self.margin_floor(band, kind, buy, sell) { m.insert("margin".into(), json!(f)); }
        Value::Object(m)
    }
}

/// WP-11: what one arm's decisions did (status.jsonl `experiments`): every decision assigned the arm, those that became
/// an opportunity (a best route over `min_profit`), were sent, were would-sends, and the executor's refusals of the rest
/// by reason (the part before a `:`)
#[derive(Clone, Debug, Default, PartialEq)]
pub struct ArmCounts { pub decisions: u64, pub opportunities: u64, pub sent: u64, pub would_send: u64, pub refused: std::collections::BTreeMap<String, u64> }

/// WP-11: the per-arm counters of a run, by experiment (x2, x4, size, margin) and arm index; status.jsonl `experiments`
#[derive(Clone, Debug, Default)]
pub struct ArmStats { by: Vec<((u8, u8), ArmCounts)> }

impl ArmStats {
    fn slot(&mut self, k: (u8, u8)) -> &mut ArmCounts {
        let i = match self.by.iter().position(|x| x.0 == k) { Some(i) => i, None => { self.by.push((k, ArmCounts::default())); self.by.len() - 1 } };
        &mut self.by[i].1
    }
    /// one decision of arms `a`: an opportunity or not, sent, a would-send, or refused for `reason`
    pub fn note(&mut self, a: &Arms, opportunity: bool, sent: bool, would_send: bool, reason: &str) {
        let ids = [a.x2.map(|x| x.idx), a.x4.map(|x| x.idx), a.size.map(|x| x.idx), a.margin.map(|x| x.idx)];
        for (e, idx) in ids.into_iter().enumerate() {
            let Some(i) = idx else { continue };
            let c = self.slot((e as u8, i));
            c.decisions += 1;
            if !opportunity { continue; }
            c.opportunities += 1;
            if sent { c.sent += 1; } else if would_send { c.would_send += 1; } else {
                let r = reason.split(':').next().unwrap_or("");
                match c.refused.get_mut(r) { Some(n) => *n += 1, None => { c.refused.insert(r.to_string(), 1); } }
            }
        }
    }
    /// status.jsonl `experiments`: `{key: {arm: {decisions, opportunities, sent, would_send, refused: {reason: n}}}}`, the
    /// run's totals; None before the first decision
    pub fn json(&self, x: &Experiments) -> Option<Value> {
        if self.by.is_empty() { return None; }
        let label = |e: u8, i: u8| -> Option<String> {
            let i = i as usize;
            match e { 0 => x.x2.as_ref().and_then(|v| v.arms.get(i)).map(|a| json!(a).to_string()), 1 => x.x4.as_ref().and_then(|v| v.arms.get(i)).map(|a| json!(a).to_string()),
                2 => x.size.as_ref().and_then(|v| v.arms.get(i)).map(|a| json!(a).to_string()), _ => x.margin.as_ref().and_then(|v| v.arms.get(i)).map(|a| json!(a).to_string()) }
        };
        let mut out = serde_json::Map::new();
        let mut by = self.by.clone();
        by.sort_by_key(|x| x.0);
        for ((e, i), c) in by {
            let Some(l) = label(e, i) else { continue };
            let key = KEYS[e as usize].1;
            let m = out.entry(key.to_string()).or_insert_with(|| json!({}));
            m[l] = json!({ "decisions": c.decisions, "opportunities": c.opportunities, "sent": c.sent, "would_send": c.would_send, "refused": c.refused });
        }
        Some(Value::Object(out))
    }
}

/// SOL to lamports as the ladder (`Engine::ladder`) and the executor's caps convert them: truncated (0.05 SOL is
/// 50,000,000 lamports), so an arm equal to a rung or a cap is that rung or cap to the lamport
pub fn sol_lamports(sol: f64) -> u64 { (sol * 1e9) as u64 }

#[cfg(test)]
mod tests;
