//! SKETCH ONLY — exit / TP ladder state machine for a pump.fun snipe. Not wired into the build.
//! Design + measured basis: sketch/exit-ladder.md. Pairs with sketch/launch.rs (entry).
//!
//! Driven by the launch's `bonding_curve` account updates (added to the watched set after the snipe —
//! same account-follow path the arb engine uses). Each update yields a price multiple `r` and a slot age;
//! the machine emits `SellOrder`s (fraction of the ORIGINAL position + a min-SOL slippage floor) which the
//! caller turns into a pump `sell` ix and submits on the existing send path.

use crate::tx::Pk;

// ---- params (defaults grounded in the sniper's measured ladders; all tunable) ----
#[derive(Clone, Copy)]
pub struct ExitParams {
    pub derisk_frac: f64,     // 0.40 — first tranche of original position (fired ASAP)
    pub ride_r: f64,          // 1.60 — climb here & rising -> ride mode
    pub ladder_r_floor: f64,  // 1.00 — trailing ladder only while r >= this
    pub ladder_frac: f64,     // 0.30 — fraction of REMAINING per ladder step
    pub ladder_step_slots: u64, // 4
    pub trail_drop: f64,      // 0.15 — ride mode: r off peak by this -> dump remainder
    pub stop_r: f64,          // 0.85 — dump 100% now
    pub age_cap_slots: u64,   // 50  — hard dump (~20s)
    pub slippage: f64,        // 0.10 — min_sol_output = expected * (1 - slippage)
}
impl Default for ExitParams {
    fn default() -> Self {
        Self { derisk_frac: 0.40, ride_r: 1.60, ladder_r_floor: 1.00, ladder_frac: 0.30,
               ladder_step_slots: 4, trail_drop: 0.15, stop_r: 0.85, age_cap_slots: 50, slippage: 0.10 }
    }
}

#[derive(Clone, Copy, PartialEq, Debug)]
enum Phase { Derisk, Ladder, Ride, Done }

pub struct Exit {
    p: ExitParams,
    mint: Pk,
    buy_slot: u64,
    avg_buy_px: f64,       // SOL per token paid at entry
    pos_tokens: f64,       // ORIGINAL bought amount
    remaining: f64,        // tokens still held
    phase: Phase,
    peak_r: f64,
    last_sell_slot: u64,
}

/// What the caller executes: sell `tokens` of `mint`, requiring at least `min_sol_output` back.
pub struct SellOrder { pub mint: Pk, pub tokens: f64, pub min_sol_output: f64, pub reason: &'static str }

impl Exit {
    pub fn new(p: ExitParams, mint: Pk, buy_slot: u64, avg_buy_px: f64, pos_tokens: f64) -> Self {
        Self { p, mint, buy_slot, avg_buy_px, pos_tokens, remaining: pos_tokens,
               phase: Phase::Derisk, peak_r: 1.0, last_sell_slot: buy_slot }
    }

    #[inline]
    fn order(&mut self, frac_of_remaining: f64, cur_px: f64, slot: u64, reason: &'static str) -> SellOrder {
        let tokens = (self.remaining * frac_of_remaining).min(self.remaining);
        self.remaining -= tokens;
        self.last_sell_slot = slot;
        if self.remaining <= self.pos_tokens * 1e-6 { self.phase = Phase::Done; }
        SellOrder { mint: self.mint, tokens,
                    min_sol_output: tokens * cur_px * (1.0 - self.p.slippage), reason }
    }

    /// Call on every bonding_curve update. `cur_px` = virtual_quote_reserves / virtual_token_reserves,
    /// parsed from the BondingCurve account (IDL-confirmed offsets, after the 8-byte disc):
    ///   +8 virtual_token_reserves u64, +16 virtual_quote_reserves u64 (quote = SOL for SOL curves),
    ///   +24 real_token, +32 real_quote, +40 total_supply, +48 complete bool, +49 creator pubkey, ...
    /// `sellable` = curve still live (not migrating / drained). Returns at most one order per update.
    pub fn on_update(&mut self, cur_px: f64, slot: u64, sellable: bool) -> Option<SellOrder> {
        if self.phase == Phase::Done || self.remaining <= 0.0 { return None; }
        let r = cur_px / self.avg_buy_px;
        let age = slot.saturating_sub(self.buy_slot);
        if r > self.peak_r { self.peak_r = r; }

        // hard stops first — dump everything
        if !sellable || r <= self.p.stop_r || age >= self.p.age_cap_slots {
            let why = if !sellable { "rug/unsellable" } else if age >= self.p.age_cap_slots { "age-cap" } else { "stop-loss" };
            return Some(self.order(1.0, cur_px, slot, why));
        }

        match self.phase {
            Phase::Derisk => {
                // fire the big first tranche as soon as we can (ideally slot 0/1)
                let frac_of_remaining = self.p.derisk_frac; // remaining == original here
                self.phase = Phase::Ladder;
                Some(self.order(frac_of_remaining, cur_px, slot, "derisk"))
            }
            Phase::Ride => {
                // sold up high; exit the rest when it rolls over off the peak
                if r <= self.peak_r * (1.0 - self.p.trail_drop) {
                    Some(self.order(1.0, cur_px, slot, "ride-trail-stop"))
                } else { None }
            }
            Phase::Ladder => {
                if r >= self.p.ride_r {
                    self.phase = Phase::Ride; // let it run
                    None
                } else if r < self.p.ladder_r_floor {
                    Some(self.order(1.0, cur_px, slot, "fade-exit"))
                } else if slot.saturating_sub(self.last_sell_slot) >= self.p.ladder_step_slots {
                    Some(self.order(self.p.ladder_frac, cur_px, slot, "ladder"))
                } else { None }
            }
            Phase::Done => None,
        }
    }
}

// ---- pump `sell` ix (disc 33e685a4017f83ad; args amount u64, min_sol_output u64) ----
// 14 accounts = the buy set MINUS the two volume accumulators. IDL order:
//   0 global  1 fee_recipient(W)  2 mint  3 bonding_curve(W)  4 assoc_bonding_curve(W)
//   5 associated_user(W)  6 user(W,S)  7 system_program  8 creator_vault(W)  9 token_program
//   10 event_authority  11 program  12 fee_config  13 fee_program
// All already derived for the buy (sketch/launch.rs::BuyAccounts) — reuse them, drop global_/user_vol.
pub const SELL_DISC: [u8; 8] = [0x33, 0xe6, 0x85, 0xa4, 0x01, 0x7f, 0x83, 0xad];

// WHERE THIS HOOKS IN (no edits made):
// - after snipe_fire (launch.rs): construct Exit, and add `bonding_curve` to the feeds watched set so the
//   engine starts getting its account updates.
// - engine: on a watched bonding_curve update, parse cur_px from the account bytes, call Exit::on_update,
//   and for any SellOrder build the pump `sell` ix (accounts above) and submit via the existing send path.
// - same-slot de-risk: pre-build the first sell on a 2nd durable-nonce lane; first cut fires it at slot+1.
