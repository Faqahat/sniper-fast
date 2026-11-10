// =====================================================================================================================
// dip43 BUILDER B: the send path and the exits (BUILD_DIP43.md B1..B5; specs: misses/REPORT.md P2 / P3 / P5, F6 / F7; exit/REPORT.md
// EXIT-1 / EXIT-2; integrator/REPORT.md section 5 b1, b2, b4, b5, b6). EVERY ITEM IS OFF BY DEFAULT: with none of its flags the engine
// sends, prices, routes, exits and sells exactly as dip42 (each hook below returns dip42's answer when its flag is absent).
//   B1 --presend-live-reroute on|off (off)          a try the lane's own cap refuses (rate_path / rate_path_config) goes to the NEXT lane
//                                                   of its leader class with capacity (in route order); a global-cap refusal is never
//                                                   re-routed. presend_attempt gets "path_orig" (the lane it was planned on) when moved
//      --presend-live-single-token on|off (off)     an async lane's try is charged ONE rate token (the sender's fast_budget) instead of
//                                                   two (+ Path::send's budget.acquire): Path::send_prepaid
//      --presend-live-skip-clients LIST (none)      no pre-send try is signed for a slot whose leader runs one of these clients (gossip
//                                                   clientId, e.g. Rakurai): counted "skip_client" in not_sent
//      the global cap itself: --presend-live-max-per-sec (engine range 1..200 already; the run script's own limit: see docs/dip43_flags.md)
//   B2 --presend-live-fee-tier N:CU_PRICE[:CLIENTS] (off)  every Nth try (1-based) a window signs in one slot is signed at CU_PRICE uL
//                                                   (never lower than its own price) when the slot's leader runs a listed client (default
//                                                   the fee A/B's AgaveBam,HarmonicAgave,HarmonicFiredancer,Firedancer,Agave). Works on top
//                                                   of the fee A/B (an arm B try can be tiered too). presend_attempt gets "tier"
//   B3 --presend-live-exit-lots FRAC:SLOTS (off)    timer (time-limit, time-ms) and take-profit exits sell floor(tokens x FRAC) now (lot 1)
//                                                   and the rest SLOTS slot(s) later (lot 2; or 400 x SLOTS + 600 ms on the wall clock, a
//                                                   stalled slot clock); a stop-loss value seen while lot 2 waits sells lot 2 at once; stop
//                                                   exits stay whole. Lot 1's sell loop stops at a confirmed balance <= lot 2's tokens (never
//                                                   sells the rest); lot 2's loop sells until 0. Realized sums every sell of both lots
//      --presend-live-exit-lots-ab on|off (off)     on: position id parity (even pid = lots, odd = whole); off: every eligible exit in lots
//      --presend-live-exit-lots-kinds LIST (t2)     the position kinds in the lots exit: t2, rearm, wide, qf2 (or all)
//      --presend-live-lot2-cu-price-micro N (500000)  lot 2's CU price (a lot 2 fired by a stop: the run's sell price)
//      control file key "exit_lots": off|ab|live    (--presend-live-ledger-control; needs --presend-live-exit-lots; else ignored)
//   B4 --presend-live-timer-sell-cu-price-micro N (off)  timer exit sells (time-limit, time-ms) at N uL; TP / SL / wall / orphan unchanged
//      --presend-live-timer-sell-ab on|off (off)    on: the position id's SECOND bit ((pid >> 1) & 1 == 0 = cheap), so it never lines up
//                                                   with the lots A/B's parity; off: every timer sell cheap
//   B5 --presend-live-start-ms N (off = --presend-live-ms, 50)  a T2 window's first try N ms after its trigger (0 = at once); the window's
//                                                   end slot is NOT moved (dip42's end)
// Records: presend_attempt "path_orig" / "tier"; presend_live_exit "lot", "lots", "timer_sell", "tokens_all", "lot2_tokens",
// "lot2_due_slot"; a second presend_live_exit (why lot2 / lot2-stop / lot2-wall, "lot": 2) when lot 2 goes; presend_live_lot_sold (lot 1's
// sell loop answer); presend_live_sell_land "lot"; presend_live_ledger_mode "exit_lots"; run_end presend_live.b43. docs/dip43_records.md
// =====================================================================================================================
use super::*;

/// the position kinds the lots exit can take
pub const LOT_KINDS: [&str; 4] = ["t2", "rearm", "wide", "qf2"];
/// lot 2's default CU price (EXIT-1: 65,000 lamports at 120k CU instead of 605,000)
pub const LOT2_PRICE: u64 = 500_000;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LotsMode { Off, Ab, Live }
impl LotsMode {
    pub fn s(self) -> &'static str { match self { LotsMode::Off => "off", LotsMode::Ab => "ab", LotsMode::Live => "live" } }
    pub fn parse(x: &str) -> Option<LotsMode> { match x { "off" => Some(LotsMode::Off), "ab" => Some(LotsMode::Ab), "live" => Some(LotsMode::Live), _ => None } }
}

#[derive(Clone, Debug, PartialEq)]
pub struct LotsCfg { pub frac: f64, pub slots: u64, pub kinds: Vec<&'static str>, pub mode: LotsMode, pub lot2_price: u64 }

#[derive(Clone, Debug, PartialEq)]
pub struct TierCfg { pub n: u32, pub cu_price: u64, pub clients: Vec<String> }

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TimerSellCfg { pub cu_price: u64, pub ab: bool }

/// Builder B's parameters. Default = every item off = dip42
#[derive(Clone, Debug, PartialEq, Default)]
pub struct B43Cfg {
    pub reroute: bool,
    pub single_token: bool,
    pub skip_clients: Vec<String>,
    pub tier: Option<TierCfg>,
    /// B5: the T2 window's start (ms after the trigger); None = --presend-live-ms (dip42)
    pub start_ms: Option<f64>,
    pub lots: Option<LotsCfg>,
    pub timer_sell: Option<TimerSellCfg>,
}

/// a comma-separated client list (known gossip clientIds or Unknown(N)), no duplicates, not empty
fn clients_parse(flag: &str, s: &str) -> Result<Vec<String>> {
    let mut v: Vec<String> = Vec::new();
    for c in s.split(',').map(str::trim) {
        let unk = c.strip_prefix("Unknown(").and_then(|x| x.strip_suffix(')')).is_some_and(|n| !n.is_empty() && n.bytes().all(|b| b.is_ascii_digit()));
        if c.is_empty() || !(psfeeab::KNOWN_CLIENTS.contains(&c) || unk) {
            bail!("{flag}: '{c}' is not a leader client the engine knows ({} or Unknown(N))", psfeeab::KNOWN_CLIENTS.join(", "));
        }
        if v.iter().any(|x| x == c) { bail!("{flag}: '{c}' twice"); }
        v.push(c.to_string());
    }
    Ok(v)
}

/// Builder B's flags without --presend-live: refused (as every --presend-live-* flag)
pub fn needs_presend_live(argv: &[String]) -> Result<()> {
    let has = |f: &str| argv.iter().skip(1).any(|x| x == f);
    if !has("--presend-live") { if let Some(f) = B43FLAGS.iter().find(|f| has(f)) { bail!("{f} needs --presend-live"); } }
    Ok(())
}

impl B43Cfg {
    /// the flags (each validated here; a value without its parent flag refused)
    pub fn from_argv(argv: &[String]) -> Result<B43Cfg> {
        let has = |f: &str| argv.iter().skip(1).any(|x| x == f);
        let arg = |f: &str| argv.iter().position(|x| x == f).and_then(|i| argv.get(i + 1)).cloned();
        let onoff = |f: &str| -> Result<bool> { match arg(f).as_deref() { None => Ok(false), Some("on") => Ok(true), Some("off") => Ok(false), Some(x) => bail!("{f} {x}: on | off") } };
        let num = |f: &str, lo: u64, hi: u64| -> Result<Option<u64>> {
            match arg(f) {
                None if has(f) => bail!("{f} needs a value"),
                None => Ok(None),
                Some(x) => match x.parse::<u64>() { Ok(n) if (lo..=hi).contains(&n) => Ok(Some(n)), _ => bail!("{f} {x}: must be {lo}..{hi}") },
            }
        };
        let mut c = B43Cfg { reroute: onoff("--presend-live-reroute")?, single_token: onoff("--presend-live-single-token")?, ..Default::default() };
        if let Some(s) = arg("--presend-live-skip-clients") { c.skip_clients = clients_parse("--presend-live-skip-clients", &s)?; }
        else if has("--presend-live-skip-clients") { bail!("--presend-live-skip-clients needs a value (e.g. Rakurai)"); }
        if let Some(s) = arg("--presend-live-fee-tier") {
            let bad = || anyhow::anyhow!("--presend-live-fee-tier N:CU_PRICE[:CLIENTS] (N 1..20 = every Nth try of a window-slot, CU_PRICE 1..1000000 uL, CLIENTS comma-separated), e.g. 4:150000; got '{s}'");
            let v: Vec<&str> = s.splitn(3, ':').collect();
            if v.len() < 2 { return Err(bad()); }
            let n: u32 = v[0].parse().map_err(|_| bad())?;
            let p: u64 = v[1].parse().map_err(|_| bad())?;
            if !(1..=20).contains(&n) || !(1..=1_000_000).contains(&p) { return Err(bad()); }
            let clients = match v.get(2) { Some(x) => clients_parse("--presend-live-fee-tier", x)?, None => psfeeab::AB_CLIENTS.split(',').map(String::from).collect() };
            c.tier = Some(TierCfg { n, cu_price: p, clients });
        } else if has("--presend-live-fee-tier") { bail!("--presend-live-fee-tier needs a value (e.g. 4:150000)"); }
        c.start_ms = num("--presend-live-start-ms", 0, 500)?.map(|x| x as f64);
        match arg("--presend-live-exit-lots") {
            Some(s) => {
                let bad = || anyhow::anyhow!("--presend-live-exit-lots FRAC:SLOTS (FRAC in (0, 1) = lot 1's share, SLOTS 1..4 = lot 2's delay), e.g. 0.5:1; got '{s}'");
                let (f, k) = s.split_once(':').ok_or_else(bad)?;
                let frac: f64 = f.parse().map_err(|_| bad())?;
                let slots: u64 = k.parse().map_err(|_| bad())?;
                if !(frac > 0.0 && frac < 1.0) || !(1..=4).contains(&slots) { return Err(bad()); }
                let kinds = match arg("--presend-live-exit-lots-kinds") {
                    None => vec!["t2"],
                    Some(x) if x == "all" => LOT_KINDS.to_vec(),
                    Some(x) => {
                        let mut v: Vec<&'static str> = Vec::new();
                        for k in x.split(',').map(str::trim) {
                            let Some(kk) = LOT_KINDS.iter().find(|y| **y == k) else { bail!("--presend-live-exit-lots-kinds: '{k}' (t2, rearm, wide, qf2 or all)") };
                            if !v.contains(kk) { v.push(kk); }
                        }
                        v
                    }
                };
                let mode = if onoff("--presend-live-exit-lots-ab")? { LotsMode::Ab } else { LotsMode::Live };
                let lot2_price = num("--presend-live-lot2-cu-price-micro", 1, 50_000_000)?.unwrap_or(LOT2_PRICE);
                c.lots = Some(LotsCfg { frac, slots, kinds, mode, lot2_price });
            }
            None => {
                if has("--presend-live-exit-lots") { bail!("--presend-live-exit-lots needs a value (e.g. 0.5:1)"); }
                for f in ["--presend-live-exit-lots-ab", "--presend-live-exit-lots-kinds", "--presend-live-lot2-cu-price-micro"] {
                    if has(f) { bail!("{f} needs --presend-live-exit-lots FRAC:SLOTS"); }
                }
            }
        }
        match num("--presend-live-timer-sell-cu-price-micro", 1, 50_000_000)? {
            Some(p) => c.timer_sell = Some(TimerSellCfg { cu_price: p, ab: onoff("--presend-live-timer-sell-ab")? }),
            None => if has("--presend-live-timer-sell-ab") { bail!("--presend-live-timer-sell-ab needs --presend-live-timer-sell-cu-price-micro N"); },
        }
        Ok(c)
    }

    /// any Builder B item on (the run_start JSON / status / run_end parts are written only then)
    pub fn any_on(&self) -> bool { *self != B43Cfg::default() }

    /// B1: no pre-send try for a slot of this leader client (empty list: never)
    #[inline]
    pub fn skip_client(&self, client: &str) -> bool { !self.skip_clients.is_empty() && self.skip_clients.iter().any(|c| c == client) }

    /// run_start's presend_live.b43
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"reroute": self.reroute, "single_token": self.single_token, "skip_clients": self.skip_clients,
            "fee_tier": self.tier.as_ref().map(|t| serde_json::json!({"n": t.n, "cu_price": t.cu_price, "clients": t.clients})),
            "start_ms": self.start_ms, "exit_lots": self.lots.as_ref().map(|l| serde_json::json!({"frac": l.frac, "slots": l.slots, "kinds": l.kinds, "mode": l.mode.s(), "lot2_cu_price": l.lot2_price})),
            "timer_sell": self.timer_sell.map(|t| serde_json::json!({"cu_price": t.cu_price, "ab": t.ab}))})
    }

    /// the start banner: one line per item (printed also when off, so a dry run shows every setting)
    pub fn desc_lines(&self, max_per_sec: u64, path_max_per_sec: u64, live_ms: f64) -> Vec<String> {
        let oo = |b: bool| if b { "ON" } else { "off" };
        vec![
            format!("DIP43-B B1 CAP + ROUTES: global cap {max_per_sec}/s, per lane entry {path_max_per_sec}/s | re-route a lane-refused try {} | one rate token per async try {} | pre-send skip clients {}",
                oo(self.reroute), oo(self.single_token), if self.skip_clients.is_empty() { "none".to_string() } else { self.skip_clients.join(",") }),
            format!("DIP43-B B2 FEE TIER: {}", match &self.tier { None => "off".to_string(),
                Some(t) => format!("ON: every {}th try of a window-slot at CU price {} uL (never lower than its own) on leaders {}", t.n, t.cu_price, t.clients.join(",")) }),
            format!("DIP43-B B3 TWO-LOT EXIT: {}", match &self.lots { None => "off".to_string(),
                Some(l) => format!("{} ({}): timer / take-profit exits of kinds {} sell {:.0}% now, the rest {} slot(s) later (wall {} ms) at {} uL; a stop while lot 2 waits sells it at once; stops whole | control key exit_lots",
                    l.mode.s().to_uppercase(), if l.mode == LotsMode::Ab { "even position id = lots, odd = whole" } else { "every eligible exit" }, l.kinds.join(","), l.frac * 100.0, l.slots,
                    lot2_wall_ms(l.slots), l.lot2_price) }),
            format!("DIP43-B B4 CHEAP TIMER SELLS: {}", match &self.timer_sell { None => "off".to_string(),
                Some(t) => format!("ON: time-limit / time-ms sells at {} uL{} (TP / SL / wall / orphan sells unchanged)", t.cu_price, if t.ab { " on positions with (pid >> 1) even (A/B; others the run's price)" } else { " on every position" }) }),
            format!("DIP43-B B5 WINDOW START: {}", match self.start_ms { None => format!("off: +{live_ms} ms after the trigger (--presend-live-ms)"),
                Some(s) => format!("ON: +{s} ms after the trigger (end slot unchanged)") }),
        ]
    }
}

// ---------------------------------------------------------------------------------------------------------------------
// B1 routes
// ---------------------------------------------------------------------------------------------------------------------

/// tries moved to another lane / refused on every lane of the class (status, run_end)
pub static REROUTED: AtomicU64 = AtomicU64::new(0);
pub static REROUTE_FAILED: AtomicU64 = AtomicU64::new(0);

/// B1: the lane of a due try (pure apart from `take`: unit-tested). `take(j)` = the rate check of lane j (take_rate: a refused check takes
/// no token). Re-route OFF: exactly `take(ri0)` (dip42). ON: a lane refusal ("rate_path" / "rate_path_config") tries the class's next lanes
/// in route order; a global-cap refusal ends the search (no lane has room). -> (the lane used, moved)
pub fn pick_route(n: usize, ri0: usize, reroute: bool, mut take: impl FnMut(usize) -> std::result::Result<(), &'static str>) -> std::result::Result<(usize, bool), &'static str> {
    let why = match take(ri0) { Ok(()) => return Ok((ri0, false)), Err(w) => w };
    if !reroute || why == "rate_global" || n < 2 { return Err(why); }
    for k in 1..n {
        let j = (ri0 + k) % n;
        match take(j) {
            Ok(()) => { REROUTED.fetch_add(1, Ordering::Relaxed); return Ok((j, true)); }
            Err("rate_global") => break,
            Err(_) => {}
        }
    }
    REROUTE_FAILED.fetch_add(1, Ordering::Relaxed);
    Err(why)
}

/// B1 --presend-live-single-token on: `send_one` whose async send does not take a second rate token (the sender's fast_budget took it)
pub(super) fn send_one_prepaid(r: &RouteP, raw: &[u8], tag: u64, handle: &tokio::runtime::Handle, body: &mut Vec<u8>, req: &mut Vec<u8>) -> &'static str {
    if let Some((conn, json)) = &r.fast {
        if *json { arbx::fast::json_send_body(raw, body); conn.frame(&body[..], req); } else { conn.frame(raw, req); }
        if conn.write_req(req, tag).is_ok() { return "written"; }
    }
    let (p, raw) = (r.path.clone(), raw.to_vec());
    handle.spawn(async move {
        let t = Instant::now();
        let res = p.send_prepaid(&raw, None).await;
        pl::note_ack(tag, match &res { Ok(rep) => rep.status.or(Some(200)), Err(e) => e.status }, t.elapsed().as_secs_f64() * 1e3);
    });
    if r.fast.is_some() { "conn_down_async" } else { "async" }
}

// ---------------------------------------------------------------------------------------------------------------------
// B2 fee tier
// ---------------------------------------------------------------------------------------------------------------------

/// tier tries [base on a tier client, tiered] (status, run_end)
pub static TIER_TRIES: [AtomicU64; 2] = [AtomicU64::new(0), AtomicU64::new(0)];

/// the sender's per window-slot try counter (only with the tier on)
#[derive(Default)]
pub struct TierCtr { m: FxHashMap<u64, (u64, u32)> }
impl TierCtr {
    /// this try's 1-based number among the window's tries signed in `slot`
    pub fn next(&mut self, w: u64, slot: u64) -> u32 {
        if self.m.len() > 4096 { self.m.retain(|_, v| v.0 + 64 >= slot); }
        let e = self.m.entry(w).or_insert((slot, 0));
        if e.0 != slot { *e = (slot, 0); }
        e.1 += 1;
        e.1
    }
}

/// one try's tier view (the presend_attempt record's "tier")
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TierTag { pub i: u32, pub n: u32, pub on: bool, pub client_ok: bool, pub cu_price: u64 }
impl TierTag {
    pub fn json(&self) -> serde_json::Value { serde_json::json!({"i": self.i, "n": self.n, "on": self.on, "client": self.client_ok, "cu_price": self.cu_price}) }
}

/// B2 (pure: unit-tested): the try's CU price with the tier. `i` = its 1-based number in its window-slot; the tier applies on every Nth
/// try on a listed client, never lowers the price. Tier off: (price, None) = dip42
pub fn tier_price(cfg: &B43Cfg, i: u32, client: &str, price: u64) -> (u64, Option<TierTag>) {
    let Some(t) = &cfg.tier else { return (price, None) };
    let client_ok = t.clients.iter().any(|c| c == client);
    let on = client_ok && i % t.n == 0 && t.cu_price > price;
    let p = if on { t.cu_price } else { price };
    (p, Some(TierTag { i, n: t.n, on, client_ok, cu_price: p }))
}

/// B2 the sender's step (tier on only): the price, the fee A/B's view of it (its failed-try fee follows the signed price) and the tag
pub fn tier_apply(cfg: &B43Cfg, ctr: &mut TierCtr, w: u64, slot: u64, client: &str, price: u64, sig_fa: Option<psfeeab::AttFee>)
    -> (u64, Option<psfeeab::AttFee>, Option<TierTag>) {
    if cfg.tier.is_none() { return (price, sig_fa, None); }
    let i = ctr.next(w, slot);
    let (p, tag) = tier_price(cfg, i, client, price);
    let mut fa = sig_fa;
    if let Some(f) = fa.as_mut() { f.cu_price = p; }
    if let Some(t) = tag.filter(|t| t.client_ok) { TIER_TRIES[t.on as usize].fetch_add(1, Ordering::Relaxed); }
    (p, fa, tag)
}

/// B2: a tiered try's failed fee by signature (the main loop's fallback fee when the failed-tx side channel has none and the fee A/B is
/// off). Bounded FIFO; empty (and never locked) with the tier off
static TIER_FEES: Mutex<(Option<FxHashMap<[u8; 64], u64>>, VecDeque<[u8; 64]>)> = Mutex::new((None, VecDeque::new()));
static TIER_ON: AtomicBool = AtomicBool::new(false);
const TIER_FEES_MAX: usize = 8192;
pub fn tier_fee_note(sig: &[u8; 64], fee: u64) {
    TIER_ON.store(true, Ordering::Relaxed);
    let mut g = TIER_FEES.lock().unwrap_or_else(|e| e.into_inner());
    let (m, q) = &mut *g;
    let m = m.get_or_insert_with(FxHashMap::default);
    if q.len() >= TIER_FEES_MAX { if let Some(o) = q.pop_front() { m.remove(&o); } }
    m.insert(*sig, fee);
    q.push_back(*sig);
}
pub fn tier_fail_fee(sig: &[u8; 64]) -> Option<u64> {
    if !TIER_ON.load(Ordering::Relaxed) { return None; }
    TIER_FEES.lock().unwrap_or_else(|e| e.into_inner()).0.as_ref().and_then(|m| m.get(sig).copied())
}

// ---------------------------------------------------------------------------------------------------------------------
// B3 / B4 exits
// ---------------------------------------------------------------------------------------------------------------------

/// lot 2's wall-clock backstop (a stalled slot clock): 400 ms a slot + 600
pub fn lot2_wall_ms(slots: u64) -> u64 { slots * 400 + 600 }
/// the exits a lots exit takes (pure)
pub fn lots_reason(why: &str) -> bool { matches!(why, "time-limit" | "time-ms" | "take-profit") }
/// the exits a cheap timer sell takes (pure)
pub fn timer_reason(why: &str) -> bool { matches!(why, "time-limit" | "time-ms") }
/// the lots arm of a position (pure): Some(true) lots, Some(false) the A/B's whole arm, None off
pub fn lots_arm(mode: LotsMode, pid: u64) -> Option<bool> { match mode { LotsMode::Off => None, LotsMode::Live => Some(true), LotsMode::Ab => Some(pid % 2 == 0) } }
/// the cheap timer-sell arm of a position (pure): ab = the id's second bit even
pub fn cheap_arm(t: &TimerSellCfg, pid: u64) -> bool { !t.ab || (pid >> 1) & 1 == 0 }
/// (lot 1, lot 2) tokens of `t` (pure): lot 1 = floor(t x frac); None when either lot would be empty (then the exit stays whole)
pub fn lots_split(t: u64, frac: f64) -> Option<(u64, u64)> {
    let a = (t as f64 * frac).floor() as u64;
    (a > 0 && a < t).then_some((a, t - a))
}

/// one two-lot exit under way
pub(super) struct LotSt {
    pub pid: u64,
    /// lot 1's tokens, every token of the round at the decision
    pub a: u64, pub t: u64,
    pub why: &'static str, pub dec_slot: u64, pub due_slot: u64, pub dec_at: Instant, pub wall_ms: u64,
    /// lot 1's sell round; lot 2's once fired
    pub r1: u32, pub r2: Option<u32>,
    /// lot 1's loop still running; its answer (sold_at) once back; lot 2's answer kept while lot 1's runs
    pub l1_pending: bool, pub l1_sold: Option<Option<u64>>, pub l2_out: Option<SellOut>,
    /// lot 1's landing seen on the feed (the sell-land records' "lot")
    pub l1_seen: bool,
    pub lot2_price: u64,
}

/// the counters
#[derive(Default, Debug, Clone, Copy)]
pub struct B43N { pub lots: u64, pub whole_arm: u64, pub whole_small: u64, pub lot2_timer: u64, pub lot2_wall: u64, pub lot2_stop: u64, pub l1_unconfirmed: u64,
    pub cheap: u64, pub base_timer: u64, pub ctl_changes: u64, pub ctl_errors: u64 }

/// Builder B's state in the probe (empty with its flags off)
#[derive(Default)]
pub(super) struct B43St {
    pub lots: FxHashMap<Pk, LotSt>,
    /// the lots exit's mode now (None: the start flag's)
    pub mode: Option<LotsMode>,
    /// the control file's (path, mtime, last check) for "exit_lots" (only with --presend-live-exit-lots)
    pub ctl: Option<(String, Option<std::time::SystemTime>, Instant)>,
    pub n: B43N,
}

/// the control file's "exit_lots": Some(mode) / None (absent)
pub fn ctl_parse_lots(b: &[u8]) -> std::result::Result<Option<LotsMode>, String> {
    let v: serde_json::Value = serde_json::from_slice(b).map_err(|e| format!("bad JSON: {e}"))?;
    match v.get("exit_lots") {
        None | Some(serde_json::Value::Null) => Ok(None),
        Some(x) => x.as_str().and_then(LotsMode::parse).map(Some).ok_or_else(|| format!("exit_lots: '{x}' (off | ab | live)")),
    }
}

impl PsLive {
    /// the lots exit's mode now
    pub(super) fn b43_mode(&self) -> LotsMode { self.b43.mode.unwrap_or_else(|| self.cfg.b43.lots.as_ref().map_or(LotsMode::Off, |l| l.mode)) }

    /// a position's kind for the lots exit
    fn b43_kind(&self, p: &PPos) -> &'static str {
        if p.rearm { "rearm" } else if let Some((k, _)) = self.wd_win(p.w) { k.key() } else { "t2" }
    }

    /// B3 / B4 at an exit decision (exit(): the position's exit is set). false = not ours: the caller runs dip42's sell_round. true = this
    /// exit's sell is started here (lot 1 of a lots exit, or a whole sell at the cheap timer price); `r` = its presend_live_exit record
    pub(super) fn b43_exit(&mut self, mint: &Pk, why: &'static str, slot: u64, r: &mut serde_json::Value) -> bool {
        if self.cfg.b43.lots.is_none() && self.cfg.b43.timer_sell.is_none() { return false; }
        let Some(p) = self.pos.get(mint) else { return false };
        let (pid, round) = (p.pid, p.round);
        // B4: the cheap timer price (this position's arm)
        let cheap = match &self.cfg.b43.timer_sell {
            Some(ts) if timer_reason(why) => {
                let on = cheap_arm(ts, pid);
                r["timer_sell"] = serde_json::json!({"arm": if on { "cheap" } else { "base" }, "cu_price": on.then_some(ts.cu_price), "ab": ts.ab});
                if on { self.b43.n.cheap += 1; Some(ts.cu_price) } else { self.b43.n.base_timer += 1; None }
            }
            _ => None,
        };
        // B3: lots (the mode now, the reason, the kind, the arm, two non-empty lots of exactly known tokens)
        let mode = self.b43_mode();
        let kind = self.b43_kind(p);
        let mut plan: Option<(u64, u64, u64)> = None;
        if let Some(l) = self.cfg.b43.lots.as_ref().filter(|l| lots_reason(why) && l.kinds.contains(&kind)) {
            if let Some(arm) = lots_arm(mode, pid) {
                let (t, exact) = p.buys.iter().filter(|b| b.round == 0).fold((0u64, true), |a, b| (a.0 + b.tokens, a.1 && !b.sig.is_empty()));
                r["lots"] = serde_json::json!({"arm": if arm { "lots" } else { "whole" }, "mode": mode.s(), "frac": l.frac, "slots": l.slots, "kind": kind});
                if !arm { self.b43.n.whole_arm += 1; }
                else {
                    match lots_split(t, l.frac) {
                        Some((a, rest)) if exact => plan = Some((a, rest, t)),
                        _ => { r["lots"]["whole_why"] = (if exact { "too_few_tokens" } else { "estimated_tokens" }).into(); self.b43.n.whole_small += 1; }
                    }
                }
            }
        }
        let Some((a, rest, t)) = plan else {
            if cheap.is_none() { return false; }
            self.sell_round_x(mint, Some(SellX { keep: 0, cu_price: cheap, lot: 0 }));
            return true;
        };
        let l = self.cfg.b43.lots.as_ref().expect("plan needs lots");
        let (slots, lot2_price) = (l.slots, l.lot2_price);
        r["lot"] = 1.into(); r["tokens"] = a.into(); r["tokens_all"] = t.into(); r["lot2_tokens"] = rest.into(); r["lot2_due_slot"] = (slot + slots).into();
        self.b43.n.lots += 1;
        self.b43.lots.insert(*mint, LotSt { pid, a, t, why, dec_slot: slot, due_slot: slot + slots, dec_at: Instant::now(), wall_ms: lot2_wall_ms(slots), r1: round + 1, r2: None,
            l1_pending: true, l1_sold: None, l2_out: None, l1_seen: false, lot2_price });
        self.sell_round_x(mint, Some(SellX { keep: rest, cu_price: cheap, lot: 1 }));
        true
    }

    /// B3: lot 2 now: every token not in lot 1 (lot 2's own and any buy no round covered yet), sold until 0. `price` None = the run's
    /// sell price (a stop); `why` lot2 / lot2-wall / lot2-stop
    fn b43_fire_lot2(&mut self, mint: &Pk, why: &'static str, price: Option<u64>, slot: u64, val: f64) {
        let Some(l) = self.b43.lots.get_mut(mint) else { return };
        if l.r2.is_some() { return; }
        let Some(p) = self.pos.get_mut(mint).filter(|p| p.pid == l.pid) else { self.b43.lots.remove(mint); return };
        p.round += 1;
        let r2 = p.round;
        let (mut toks, mut land) = (0u64, 0u64);
        // lot 1's buys move to lot 2's round: its "sold" (a confirmed 0) covers every token, so the position's accounting closes on it
        for b in p.buys.iter_mut().filter(|b| b.round == 0 || b.round == l.r1) { b.round = r2; toks += b.tokens; land = land.max(b.slot); }
        let tokens2 = toks.saturating_sub(l.a);
        p.selling = true;
        l.r2 = Some(r2);
        match why { "lot2-stop" => self.b43.n.lot2_stop += 1, "lot2-wall" => self.b43.n.lot2_wall += 1, _ => self.b43.n.lot2_timer += 1 }
        let mut r = serde_json::json!({"ev": "presend_live_exit", "w": p.w, "mint": b58(mint), "why": why, "slot": slot, "value": if val.is_nan() { serde_json::Value::Null } else { serde_json::json!(val) },
            "t": arbx::feeds::clock::now_ns(), "slots_held": slot as i64 - p.land.0 as i64, "pid": p.pid, "round": r2, "tokens": tokens2, "lot": 2, "lot1_slot": l.dec_slot,
            "lot1_why": l.why, "ms_after_lot1": l.dec_at.elapsed().as_secs_f64() * 1e3, "cu_price": price, "lot1_done": !l.l1_pending});
        if p.rearm { r["kind"] = "rearm".into(); }
        let c = Cmd::Sell { mint: *mint, pid: p.pid, round: r2, launch: p.launch.clone(), derived: p.derived, known: (tokens2 > 0).then_some(tokens2), guess: tokens2, land_slot: land,
            read_first: false, keep_ata: true, x43: Some(SellX { keep: 0, cu_price: price, lot: 2 }) };
        let line = format!("  PRESEND LIVE EXIT {} {why} (lot 2: {tokens2} tokens, {:.0} ms after lot 1){}", b58(mint), l.dec_at.elapsed().as_secs_f64() * 1e3, if p.rearm { " [rearm]" } else { "" });
        self.exec(c);
        self.rec(r);
        self.line(line);
    }

    /// B3 the clock (tick): lot 2 of every lots exit whose slot (or wall backstop) came; the control file's "exit_lots"
    pub(super) fn b43_tick(&mut self, slot_now: u64) {
        self.b43_ctl_check(false);
        if self.b43.lots.is_empty() { return; }
        let due: Vec<(Pk, &'static str)> = self.b43.lots.iter().filter(|(_, l)| l.r2.is_none())
            .filter_map(|(m, l)| if slot_now >= l.due_slot { Some((*m, "lot2")) } else if l.dec_at.elapsed() >= Duration::from_millis(l.wall_ms) { Some((*m, "lot2-wall")) } else { None }).collect();
        for (m, why) in due {
            let price = self.b43.lots.get(&m).map(|l| l.lot2_price);
            self.b43_fire_lot2(&m, why, price, slot_now, f64::NAN);
        }
    }

    /// B3: an outside trade of a mint whose lot 2 waits: a stop-loss value of lot 2's tokens sells it at once (the run's sell price)
    pub(super) fn b43_lot2_stop(&mut self, mint: &Pk, vsol: u64, vtok: u64, fr: f64, slot: u64) {
        let Some(l) = self.b43.lots.get(mint).filter(|l| l.r2.is_none()) else { return };
        let Some(p) = self.pos.get(mint).filter(|p| p.pid == l.pid) else { return };
        if self.cfg.sl <= 0.0 { return; }
        let rest = l.t - l.a;
        let v = pl::value(vsol, vtok, rest, fr, ((p.spend as u128 * rest as u128) / l.t.max(1) as u128) as u64);
        if v <= 1.0 - self.cfg.sl { self.b43_fire_lot2(mint, "lot2-stop", None, slot, v); }
    }

    /// B3: a sell round's answer (on_sold, first). None = taken here (lot 1's answer; lot 2's while lot 1's loop still runs); Some = the
    /// answer dip42's on_sold handles (not a lots position; lot 2's final answer, with lot 1's sells already in the position)
    pub(super) fn b43_sold(&mut self, mint: Pk, pid: u64, round: u32, out: SellOut) -> Option<(u32, SellOut)> {
        let Some(l) = self.b43.lots.get_mut(&mint).filter(|l| l.pid == pid) else { return Some((round, out)) };
        if round == l.r1 && l.l1_pending {
            l.l1_pending = false;
            l.l1_sold = Some(out.sold_at);
            if out.sold_at.is_none() { self.b43.n.l1_unconfirmed += 1; }
            let fin = l.l2_out.take().and_then(|o| l.r2.map(|r2| (r2, o)));
            let r = serde_json::json!({"ev": "presend_live_lot_sold", "mint": b58(&mint), "pid": pid, "round": round, "lot": 1, "sold_at": out.sold_at, "sell_sigs": out.sigs,
                "attempts": out.attempts, "lot2_fired": l.r2.is_some(), "lot2_done": fin.is_some()});
            // realized sums every sell of both lots: lot 1's go into the position now
            if let Some(p) = self.pos.get_mut(&mint) { p.sells.extend(out.sigs.iter().cloned()); }
            self.rec(r);
            if fin.is_some() { self.b43.lots.remove(&mint); }
            return fin;
        }
        if Some(round) == l.r2 {
            if l.l1_pending { l.l2_out = Some(out); return None; }
            self.b43.lots.remove(&mint);
        }
        Some((round, out))
    }

    /// B3: the lot of one of our sell landings on the feed (the sell_land record's "lot"; None: not a lots position)
    pub(super) fn b43_land_lot(&mut self, mint: &Pk, tok: u64) -> Option<u8> {
        let l = self.b43.lots.get_mut(mint)?;
        if l.r2.is_none() || (!l.l1_seen && tok == l.a) { l.l1_seen = true; Some(1) } else { Some(2) }
    }

    /// the control file's "exit_lots" (every ~10 s from tick; `force`: now). Needs --presend-live-exit-lots and --presend-live-ledger-control
    pub(super) fn b43_ctl_check(&mut self, force: bool) {
        if self.cfg.b43.lots.is_none() { return; }
        if self.b43.ctl.is_none() {
            let Some(p) = self.cfg.ledger_ctl.clone() else { return };
            self.b43.ctl = Some((p, None, Instant::now()));
            return self.b43_ctl_check(true);
        }
        let Some((path, mt0, at)) = self.b43.ctl.clone() else { return };
        if !force && at.elapsed() < Duration::from_secs(10) { return; }
        let mt = std::fs::metadata(&path).and_then(|m| m.modified()).ok();
        if let Some(c) = self.b43.ctl.as_mut() { c.2 = Instant::now(); }
        if !force && mt == mt0 { return; }
        if let Some(c) = self.b43.ctl.as_mut() { c.1 = mt; }
        let old = self.b43_mode();
        match std::fs::read(&path).map_err(|e| e.to_string()).and_then(|b| ctl_parse_lots(&b)) {
            Ok(None) => {}
            Ok(Some(m)) if m == old => {}
            Ok(Some(m)) => {
                self.b43.mode = Some(m);
                self.b43.n.ctl_changes += 1;
                self.rec(serde_json::json!({"ev": "presend_live_ledger_mode", "ok": true, "exit_lots": m.s(), "was": {"exit_lots": old.s()}, "path": path, "t": arbx::feeds::clock::now_ns()}));
                self.line(format!("  PRESEND LIVE LEDGER MODES: exit_lots {} -> {} ({path})", old.s(), m.s()));
            }
            Err(e) => {
                self.b43.n.ctl_errors += 1;
                self.rec(serde_json::json!({"ev": "presend_live_ledger_mode", "ok": false, "err": e, "path": path, "exit_lots": old.s(), "t": arbx::feeds::clock::now_ns()}));
                self.line(format!("  PRESEND LIVE LEDGER control file {path}: exit_lots NOT read ({e}): stays {}", old.s()));
            }
        }
    }

    /// the start: the control file's first read (the lots mode), the start record (only with an item on)
    pub(super) fn b43_start(&mut self) {
        self.b43_ctl_check(true);
        if self.cfg.b43.any_on() {
            let mut j = self.cfg.b43.json();
            j["ev"] = "presend_live_b43_start".into();
            j["exit_lots_mode"] = self.b43_mode().s().into();
            self.rec(j);
        }
    }

    /// the status part ("" with every item off)
    pub(super) fn b43_status(&self) -> String {
        let c = &self.cfg.b43;
        if !c.any_on() { return String::new(); }
        let mut v: Vec<String> = Vec::new();
        if c.reroute { v.push(format!("rerouted {} (no lane {})", REROUTED.load(Ordering::Relaxed), REROUTE_FAILED.load(Ordering::Relaxed))); }
        if c.tier.is_some() { v.push(format!("tier tries {} / base {}", TIER_TRIES[1].load(Ordering::Relaxed), TIER_TRIES[0].load(Ordering::Relaxed))); }
        if c.lots.is_some() {
            let n = &self.b43.n;
            v.push(format!("lots {} ({}): exits {} whole-arm {} small {} | lot 2 timer {} wall {} stop {} | lot 1 unconfirmed {}", self.b43_mode().s(), self.b43.lots.len(), n.lots, n.whole_arm,
                n.whole_small, n.lot2_timer, n.lot2_wall, n.lot2_stop, n.l1_unconfirmed));
        }
        if c.timer_sell.is_some() { v.push(format!("timer sells cheap {} base {}", self.b43.n.cheap, self.b43.n.base_timer)); }
        if v.is_empty() { String::new() } else { format!(" | DIP43-B {}", v.join(" | ")) }
    }

    /// run_end's presend_live.b43 (None with every item off)
    pub(super) fn b43_finish(&self) -> Option<serde_json::Value> {
        if !self.cfg.b43.any_on() { return None; }
        let n = &self.b43.n;
        Some(serde_json::json!({"cfg": self.cfg.b43.json(), "rerouted": REROUTED.load(Ordering::Relaxed), "reroute_failed": REROUTE_FAILED.load(Ordering::Relaxed),
            "tier_tries": TIER_TRIES[1].load(Ordering::Relaxed), "tier_base_tries": TIER_TRIES[0].load(Ordering::Relaxed),
            "lots": {"mode": self.b43_mode().s(), "exits": n.lots, "whole_arm": n.whole_arm, "whole_small": n.whole_small, "lot2_timer": n.lot2_timer, "lot2_wall": n.lot2_wall,
                "lot2_stop": n.lot2_stop, "lot1_unconfirmed": n.l1_unconfirmed, "pending": self.b43.lots.len(), "ctl_changes": n.ctl_changes, "ctl_errors": n.ctl_errors},
            "timer_sell": {"cheap": n.cheap, "base": n.base_timer}}))
    }
}
