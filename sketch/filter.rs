//! SKETCH ONLY — launch filter: decides which pump `create_v2` launches to snipe, and how big.
//! Not wired. Design + calibration: sketch/launch-filter.md. Pairs with launch.rs (entry) / exit.rs.
//!
//! Runs at SLOT 0 on a `Launch` from `detect_launch`, O(1), NO RPC. Three tiers:
//!   A  synchronous intrinsic  — everything is already in the create_v2 tx we just decoded
//!   B  creator reputation     — O(1) lookup in an in-memory table fed by past exit outcomes
//!   C  global risk controls   — exposure / rate / cooldown / drawdown kill-switch
//! A launch must pass A and C and not be DENY in B; the combined score then SIZES the position.

use crate::tx::Pk;
use crate::snipe::launch::Launch;   // sketch module
use rustc_hash::FxHashMap;

// ---- tunable config. Defaults are STARTING POINTS; calibrate on the shadow harness (md §4). ----
#[derive(Clone)]
pub struct FilterConfig {
    // Tier A — intrinsic
    pub dev_buy_min_sol: f64,     // reject near-zero dev conviction
    pub dev_buy_max_sol: f64,     // reject whales (we'd buy the top; cf. the $148 whale exception, run48e)
    pub max_creator_fee_bps: u64, // reject dev-extractive launches (high per-trade creator fee)
    pub allow_mayhem: bool,       // mayhem-mode launches: risk flag
    pub require_uri: bool,        // require non-empty metadata uri (socials present)
    // Tier C — global
    pub max_concurrent: usize,    // open positions at once (bankroll / exposure cap)
    pub creator_cooldown_slots: u64, // don't re-snipe the same creator within this window
    pub max_launches_per_100slots: u32, // global rate cap (don't chase every launch)
    pub daily_loss_kill_sol: f64, // halt sniping if realized PnL today <= -this
    // sizing
    pub base_size_sol: f64,       // nominal position; scaled by the score
    pub max_size_sol: f64,
}
impl Default for FilterConfig {
    fn default() -> Self {
        Self { dev_buy_min_sol: 0.5, dev_buy_max_sol: 5.0, max_creator_fee_bps: 100,
               allow_mayhem: false, require_uri: false,
               max_concurrent: 3, creator_cooldown_slots: 150, max_launches_per_100slots: 8,
               daily_loss_kill_sol: 10.0, base_size_sol: 2.0, max_size_sol: 5.0 }
    }
}

// Tier A inputs we read straight off the create_v2 tx (add these to `Launch` when wiring).
pub struct Intrinsic {
    pub dev_buy_sol: f64,     // bundled dev buy (same tx, slot 0)
    pub creator_fee_bps: u64,
    pub is_mayhem: bool,
    pub has_uri: bool,
}

// Tier B — creator reputation, updated after every exit (close the loop).
#[derive(Default, Clone, Copy)]
pub struct CreatorStat { pub launches: u32, pub sniped: u32, pub rugs: u32, pub ewma_pnl: f64, pub last_slot: u64 }
#[derive(PartialEq)]
pub enum Rep { Deny, Neutral, Allow }

#[derive(Default)]
pub struct Reputation { m: FxHashMap<Pk, CreatorStat> }
impl Reputation {
    pub fn rep(&self, creator: &Pk) -> (Rep, CreatorStat) {
        let s = self.m.get(creator).copied().unwrap_or_default();
        let rug_rate = if s.sniped > 0 { s.rugs as f64 / s.sniped as f64 } else { 0.0 };
        let r = if s.sniped >= 3 && (rug_rate > 0.6 || s.ewma_pnl < -0.3) { Rep::Deny }
                else if s.sniped >= 3 && s.ewma_pnl > 0.3 { Rep::Allow }
                else { Rep::Neutral };
        (r, s)
    }
    /// called from the exit outcome: pnl in SOL, was_rug = hit stop-loss / unsellable
    pub fn record(&mut self, creator: Pk, pnl: f64, was_rug: bool, slot: u64) {
        let e = self.m.entry(creator).or_default();
        e.sniped += 1; if was_rug { e.rugs += 1; }
        e.ewma_pnl = 0.7 * e.ewma_pnl + 0.3 * pnl; e.last_slot = slot;
    }
    pub fn seen_launch(&mut self, creator: Pk) { self.m.entry(creator).or_default().launches += 1; }
}

// Tier C — live risk state.
#[derive(Default)]
pub struct RiskState {
    pub open_positions: usize,
    pub realized_today_sol: f64,
    recent_launch_slots: std::collections::VecDeque<u64>,
    last_snipe_by_creator: FxHashMap<Pk, u64>,
}

pub struct SnipeDecision { pub size_sol: f64, pub reason: &'static str }

pub struct Filter { pub cfg: FilterConfig, pub rep: Reputation, pub risk: RiskState }

impl Filter {
    /// Slot-0 gate. Returns Some(decision) to snipe, None to skip. No RPC, no allocation on the hot path.
    pub fn evaluate(&mut self, l: &Launch, x: &Intrinsic, slot: u64) -> Option<SnipeDecision> {
        let c = &self.cfg;
        // Tier C — kill-switch & exposure first (cheapest rejects)
        if self.risk.realized_today_sol <= -c.daily_loss_kill_sol { return None; }
        if self.risk.open_positions >= c.max_concurrent { return None; }
        while let Some(&s) = self.risk.recent_launch_slots.front() {
            if slot.saturating_sub(s) > 100 { self.risk.recent_launch_slots.pop_front(); } else { break; }
        }
        if self.risk.recent_launch_slots.len() as u32 >= c.max_launches_per_100slots { return None; }
        if let Some(&last) = self.risk.last_snipe_by_creator.get(&l.creator) {
            if slot.saturating_sub(last) < c.creator_cooldown_slots { return None; }
        }
        // Tier A — intrinsic gates
        if x.dev_buy_sol < c.dev_buy_min_sol || x.dev_buy_sol > c.dev_buy_max_sol { return None; }
        if x.creator_fee_bps > c.max_creator_fee_bps { return None; }
        if x.is_mayhem && !c.allow_mayhem { return None; }
        if c.require_uri && !x.has_uri { return None; }
        // Tier B — reputation
        let (rep, stat) = self.rep.rep(&l.creator);
        if rep == Rep::Deny { return None; }

        // ---- score -> size. Keep it monotone and bounded. ----
        let mut score = 1.0_f64;
        // dev buy sweet spot: peak mid-band, taper to the edges
        let mid = 0.5 * (c.dev_buy_min_sol + c.dev_buy_max_sol);
        score *= 1.0 - ((x.dev_buy_sol - mid).abs() / (c.dev_buy_max_sol - mid).max(1e-6)) * 0.5;
        if rep == Rep::Allow { score *= 1.3; }
        if stat.ewma_pnl > 0.0 { score *= 1.0 + stat.ewma_pnl.min(1.0) * 0.2; }
        if x.is_mayhem { score *= 0.7; }
        let size = (c.base_size_sol * score).clamp(0.0, c.max_size_sol);
        if size < 0.1 { return None; }

        // commit side-effects (caller must also call rep.record on exit + open/close positions)
        self.risk.recent_launch_slots.push_back(slot);
        self.risk.last_snipe_by_creator.insert(l.creator, slot);
        Some(SnipeDecision { size_sol: size, reason: "pass" })
    }
}

// CALIBRATION NOTE: the thresholds above are starting points, NOT fitted — 12 observed snipes is too few
// to fit. The shadow harness (md §4) replays a large recorded create_v2 stream with known outcomes and
// grid-searches these params for expectancy, which is how we set them before any live run.
