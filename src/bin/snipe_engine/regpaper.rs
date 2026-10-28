// ===================================================================================================================
// dip24 REGULAR MODE (owner 10-29 02:05 PKT): --dip-regular live|paper|off (default live = dip23's behaviour, old commands unchanged).
//   off:   no regular (IMIT1 / M2) pick is ever sent or paper-traded; dumps are logged as before (research inputs); a pick that would
//          have been made is logged as pick_skip "regular_off". The shred-fire path never buys either.
//   paper: picks are decided EXACTLY as live (IMIT1 tier + the M2 gate with its --dip-m2-min, guard, dev list, spacing, near-leader
//          and client filters, one position per token, --max-inflight, the pre-send blocks, the pauses, the balance check) but NEVER
//          sent: a PAPER position instead (this file), tracked on the live trade stream:
//            entry  = the curve after every trade of the token seen before pick t_rx + --dip-regular-paper-ms (60), i.e. our buy lands
//                     right before the first trade of the token at or after that time; the guard (min tokens = the post-dump quote /
//                     --dip-guard, as live) is checked there: too few tokens = a no-fill (the reverted buy's fee is counted);
//            size   = the pick's spend (dev-list tokens: --dip-dev-spend-lamports), pump's fee on top, our own impact on the curve;
//            exit   = the run's rules: take-profit / stop-loss on every later trade (the live formula, on the paper curve with our
//                     tokens), the time limit at land slot + --dip-hold-slots (the live "slot + 1 >= land + hold"); the sell lands the
//                     same paper delay after the decision, on the curve after every trade seen before it;
//            P&L    = gross (SOL back after pump's fee - spend) and net = gross - 0.5 mSOL (buy priority) - 0.6 mSOL (sell) - the route's
//                     tips (the pick's paths' configured tips; one tip with the nonce fan-out); a no-fill costs 0.5 mSOL.
//          Paper positions are their OWN book: they never touch the live positions (`open`), the pre-send probe (which still sees no
//          reactive position) or any send budget. Records regular_paper_pick / _fill / _exit; the status line "REGULAR PAPER: ...".
//   live:  as today.
// ===================================================================================================================
use super::*;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Regular { Live, Paper, Off }

impl Regular {
    pub fn parse(s: Option<&str>) -> Result<Regular> {
        match s { None | Some("live") => Ok(Regular::Live), Some("paper") => Ok(Regular::Paper), Some("off") => Ok(Regular::Off), Some(x) => bail!("--dip-regular {x}: live | paper | off") }
    }
    pub fn as_str(self) -> &'static str { match self { Regular::Live => "live", Regular::Paper => "paper", Regular::Off => "off" } }
}

/// costs of a paper round trip (lamports): the buy's priority, the sell, a reverted buy
pub const BUY_PRIO: i64 = 500_000;
pub const SELL_COST: i64 = 600_000;
pub const NOFILL_COST: i64 = 500_000;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum St { Pending, Open, Selling, Done }

struct PPos {
    mint: Pk, dump_sig: String, t_pick: u64, land_at: u64, spend: u64, min_out: u64, tips: u64, dev: bool,
    st: St,
    /// the token's curve before the next trade (pending: the real curve; open: the paper curve with our tokens in it)
    v: f64, t: f64, fr: f64,
    q: f64, land: (u64, u64, u64),
    exit: Option<(&'static str, u64, u64, f64)>, sell_at: u64,
}

#[derive(Default)]
pub struct Paper {
    pub ms: u64, pos: HashMap<Pk, PPos>,
    pub picks: u64, pub fills: u64, pub nofill: u64, pub exits: u64, pub wins: u64, pub gross: i64, pub net: i64,
}

fn rd(x: f64) -> f64 { (x * 1e6).round() / 1e6 }

impl Paper {
    pub fn new(ms: u64) -> Paper { Paper { ms, ..Default::default() } }
    /// positions pending or open (the one-position rules count these in paper mode)
    pub fn open_count(&self) -> usize { self.pos.values().filter(|p| p.st != St::Done).count() }
    pub fn has(&self, m: &Pk) -> bool { self.pos.get(m).is_some_and(|p| p.st != St::Done) }

    /// a pick decided exactly as live: a paper position (nothing is sent)
    #[allow(clippy::too_many_arguments)]
    pub fn pick(&mut self, mint: Pk, dump_sig: &str, slot: u64, idx: u64, t_rx: u64, vsol: u64, vtok: u64, fr: f64, spend: u64, min_out: u64, tips: u64, dev: bool, score: f64,
                route: &str, log: &DipLog) {
        self.picks += 1;
        let land_at = t_rx + self.ms * 1_000_000;
        log.w(serde_json::json!({"ev": "regular_paper_pick", "mint": b58(&mint), "dump_sig": dump_sig, "slot": slot, "idx": idx, "t": t_rx, "score": score, "spend": spend, "min_out": min_out,
            "tips": tips, "route": route, "dev": dev, "paper_ms": self.ms, "land_at": land_at, "vsol": vsol, "vtok": vtok}));
        self.pos.insert(mint, PPos { mint, dump_sig: dump_sig.to_string(), t_pick: t_rx, land_at, spend, min_out, tips, dev, st: St::Pending, v: vsol as f64, t: vtok as f64, fr, q: 0.0,
            land: (0, 0, 0), exit: None, sell_at: 0 });
    }

    /// one trade of a token (call for every trade; cheap when the token has no paper position). `tp` / `sl` / `hold`: the run's exit
    #[allow(clippy::too_many_arguments)]
    pub fn on_trade(&mut self, e: &arbx::dip::TradeEvent, slot: u64, idx: u64, t_rx: u64, tp: f64, sl: f64, log: &DipLog) {
        let Some(p) = self.pos.get_mut(&e.mint) else { return };
        if p.st == St::Done { return; }
        let fr_e = (e.fbps + e.cbps).max(1) as f64 / 1e4;
        if p.st == St::Pending {
            if t_rx < p.land_at { p.v = e.vsol as f64; p.t = e.vtok as f64; p.fr = fr_e; return; }
            // our buy lands before this trade
            Self::fill(p, slot, idx, t_rx, log, &mut self.fills, &mut self.nofill, &mut self.net);
            if p.st == St::Done { return; }
        }
        // the trade on the paper curve (after our buy)
        if p.st == St::Selling && t_rx >= p.sell_at { Self::sell(p, log, &mut self.exits, &mut self.wins, &mut self.gross, &mut self.net); return; }
        if e.buy { let sol = e.sol as f64; let dt = (p.t * sol / (p.v + sol)).floor(); p.v += sol; p.t -= dt; }
        else { let tk = e.tok as f64; let so = (p.v * tk / (p.t + tk)).floor(); p.v -= so; p.t += tk; }
        p.fr = fr_e;
        if p.st == St::Open {
            // the live TP / SL formula (TXC per tx), on the paper curve with our tokens
            let so = (p.v * p.q / (p.t + p.q)).floor() * (1.0 - fr_e) / 1e9;
            let val = (so - TXC) / (p.spend as f64 / 1e9 + TXC);
            let why = if val >= 1.0 + tp { Some("take-profit") } else if val <= 1.0 - sl { Some("stop-loss") } else { None };
            if let Some(w) = why { p.exit = Some((w, slot, t_rx, val)); p.sell_at = t_rx + self.ms * 1_000_000; p.st = St::Selling; }
        }
    }

    fn fill(p: &mut PPos, slot: u64, idx: u64, t_rx: u64, log: &DipLog, fills: &mut u64, nofill: &mut u64, net: &mut i64) {
        let x = (p.spend as f64 / (1.0 + p.fr)).floor();
        let q = (p.t * x / (p.v + x)).floor();
        let ok = q >= p.min_out as f64 && p.v < 100e9;
        let rec = serde_json::json!({"ev": "regular_paper_fill", "mint": b58(&p.mint), "filled": ok, "why": if ok { "filled" } else if p.v >= 100e9 { "curve_100" } else { "guard" },
            "before": {"slot": slot, "idx": idx, "t": t_rx}, "ms_after_pick": (t_rx as i64 - p.t_pick as i64) as f64 / 1e6, "tokens": q, "min_out": p.min_out,
            "vsol": p.v, "vtok": p.t, "spend": p.spend, "dev": p.dev});
        log.w(rec);
        if !ok { *nofill += 1; *net -= NOFILL_COST; p.st = St::Done; return; }
        *fills += 1;
        p.q = q; p.v += x; p.t -= q; p.land = (slot, idx, t_rx); p.st = St::Open;
    }

    fn sell(p: &mut PPos, log: &DipLog, exits: &mut u64, wins: &mut u64, gross: &mut i64, net: &mut i64) {
        let out = ((p.v * p.q / (p.t + p.q)).floor() * (1.0 - p.fr)).floor();
        let g = out as i64 - p.spend as i64;
        let n = g - BUY_PRIO - SELL_COST - p.tips as i64;
        *exits += 1; *gross += g; *net += n; if n > 0 { *wins += 1; }
        let (why, slot, t_dec, val) = p.exit.unwrap_or(("?", 0, 0, f64::NAN));
        log.w(serde_json::json!({"ev": "regular_paper_exit", "mint": b58(&p.mint), "dump_sig": p.dump_sig, "why": why, "slot_decision": slot, "t_decision": t_dec,
            "value_at_decision": if val.is_nan() { serde_json::Value::Null } else { serde_json::json!(rd(val)) }, "t_sell": p.sell_at, "slots_held": slot as i64 - p.land.0 as i64,
            "ms_held": (p.sell_at as i64 - p.land.2 as i64) as f64 / 1e6, "sol_out": out, "gross": g, "net": n, "costs": {"buy_prio": BUY_PRIO, "sell": SELL_COST, "tips": p.tips},
            "spend": p.spend, "tokens": p.q, "dev": p.dev}));
        p.st = St::Done;
    }

    /// the clock: time exits (land slot + hold, the live rule), a sell due with no trade after it, a fill due with no trade after it;
    /// done positions are forgotten. `now` = the feed's latest arrival time
    pub fn tick(&mut self, slot_now: u64, now: u64, hold: u64, log: &DipLog) {
        for p in self.pos.values_mut() {
            match p.st {
                St::Pending if now >= p.land_at + 1_000_000_000 => { Self::fill(p, slot_now, u64::MAX, now, log, &mut self.fills, &mut self.nofill, &mut self.net); }
                St::Open if slot_now + 1 >= p.land.0 + hold => { p.exit = Some(("time-limit", slot_now, now, f64::NAN)); p.sell_at = now + self.ms * 1_000_000; p.st = St::Selling; }
                St::Selling if now >= p.sell_at + 1_000_000_000 => { Self::sell(p, log, &mut self.exits, &mut self.wins, &mut self.gross, &mut self.net); }
                _ => {}
            }
        }
        if self.pos.len() > 64 { self.pos.retain(|_, p| p.st != St::Done); }
    }

    /// the run's end: open positions sold at their last state
    pub fn finish(&mut self, log: &DipLog) {
        for p in self.pos.values_mut() {
            match p.st {
                St::Open | St::Selling => { if p.exit.is_none() { p.exit = Some(("run_end", 0, 0, f64::NAN)); } Self::sell(p, log, &mut self.exits, &mut self.wins, &mut self.gross, &mut self.net); }
                _ => {}
            }
        }
    }

    pub fn line(&self) -> String {
        format!(" | REGULAR PAPER: picks {}, fills {} (no-fill {}), exits {}, paper P&L {:+.4} SOL gross / {:+.4} net, open {}", self.picks, self.fills, self.nofill, self.exits,
            self.gross as f64 / 1e9, self.net as f64 / 1e9, self.open_count())
    }
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"paper_ms": self.ms, "picks": self.picks, "fills": self.fills, "nofill": self.nofill, "exits": self.exits, "wins": self.wins, "gross": self.gross, "net": self.net})
    }
}
