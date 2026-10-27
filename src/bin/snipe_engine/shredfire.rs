// =====================================================================================================================
// SHRED FIRE (--dip-shred-fire shadow|live; engine dip14; owner OK 10-25 ~08:45 PKT "yes do the fixes";
// ops/dip/speed/fixes/FIXES.md). The dip engine decided on the EXECUTED feed: it waited behind the dump's first shred sighting
// FRA 2.2 ms median (p90 7.8), AMS 0.7, Firedancer leaders 6.8. Here every shred-feed tx (deshred / entries) that sells a
// followed token is priced on the token's book with pump's exact integer sell and decided with the same IMIT1 / M2 rule, for
// EVERY tx index the dump can have (src/dip_shred.rs: the index is the one input a shred feed lacks):
//   * a pick for every index  -> live: FIRE now (same checks, guard, route, records as the executed path; the executed feed
//     then confirms it and never fires a second buy); shadow: a would-fire record
//   * a no-pick for every index -> a sure skip (the executed path still decides as today: a safety net)
//   * it depends on the index, another unconfirmed tx on the token is ahead, the tx cannot be priced, the token's book is
//     unknown -> the executed path decides as today (`why` in the records)
// --dip-shred-index exact (default): the index range is [after the token's newest trade of the slot, end of slot] -> no
// decision can differ through the index. window: [the executed feed's highest index in the slot - margin, + window]
// (--dip-shred-margin 40, --dip-shred-window 100): more shred fires, an estimate (the parity records say whether the true index
// fell in the window). min_out (the +5% guard) keeps a failed / reordered / mispriced dump to a cheap 6042 fail.
// Records (--dip-log): shred_dump (each decision), shred_fire (each shred buy, + the usual fire record with "via": "shred"),
// shred_parity (when the executed feed confirms or fails the dump: inputs equal, decision equal, the true index, ms saved),
// shred_unseen (a decided dump the executed feed never delivered). Counts in the 60 s status line and run_end.
// =====================================================================================================================
use super::*;
use arbx::dip_shred::{self as ds, Mode, Touch, Tracker};
use rustc_hash::FxHashMap;

/// every --dip-shred-* flag (a stray one without --dip-shred-fire is refused)
const FLAGS: [&str; 4] = ["--dip-shred-index", "--dip-shred-window", "--dip-shred-margin", "--dip-shred-seller-check"];

#[derive(Clone, Debug)]
pub struct Cfg {
    pub mode: Mode,
    /// Some((margin, window)): the window index policy; None: exact
    pub window: Option<(u32, u32)>,
    /// --dip-shred-seller-check on (default): a sell bigger than the seller's tokens per the book waits for the executed feed
    pub seller_check: bool,
}

impl Cfg {
    pub fn from_args(live: bool, probe: bool) -> Result<Option<Cfg>> { Cfg::from_argv(&std::env::args().collect::<Vec<_>>(), live, probe) }

    /// the flags on a given command line (unit-tested); readers named as the engine's own so check_flags types them
    pub fn from_argv(argv: &[String], live: bool, probe: bool) -> Result<Option<Cfg>> {
        let has = |f: &str| argv.iter().skip(1).any(|x| x == f);
        let arg = |f: &str| argv.iter().position(|x| x == f).and_then(|i| argv.get(i + 1)).cloned();
        let arg_u64 = |f: &str, d: u64| arg(f).and_then(|s| s.parse::<u64>().ok()).unwrap_or(d);
        let Some(m) = arg("--dip-shred-fire") else {
            if let Some(f) = FLAGS.iter().find(|f| has(f)) { bail!("{f} needs --dip-shred-fire shadow|live"); }
            return Ok(None);
        };
        let mode = Mode::parse(&m).map_err(|e| anyhow::anyhow!(e))?;
        if mode == Mode::Live && !live { bail!("--dip-shred-fire live fires real buys: it needs --live (shadow logs only)"); }
        if probe { bail!("--dip-shred-fire with --dip-probe: the landing probe is its own experiment (run them separately)"); }
        let window = match arg("--dip-shred-index").as_deref() {
            None | Some("exact") => {
                if has("--dip-shred-window") || has("--dip-shred-margin") { bail!("--dip-shred-window / --dip-shred-margin need --dip-shred-index window"); }
                None
            }
            Some("window") => {
                let (mg, w) = (arg_u64("--dip-shred-margin", 40), arg_u64("--dip-shred-window", 100));
                if mg > 400 { bail!("--dip-shred-margin must be 0..400 txs"); }
                if !(1..=2000).contains(&w) { bail!("--dip-shred-window must be 1..2000 txs"); }
                Some((mg as u32, w as u32))
            }
            Some(x) => bail!("--dip-shred-index {x}: exact | window"),
        };
        let seller_check = match arg("--dip-shred-seller-check").as_deref() { None | Some("on") => true, Some("off") => false, Some(x) => bail!("--dip-shred-seller-check {x}: on | off") };
        Ok(Some(Cfg { mode, window, seller_check }))
    }

    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"mode": self.mode.as_str(), "index": if self.window.is_some() { "window" } else { "exact" },
            "margin": self.window.map(|w| w.0), "window": self.window.map(|w| w.1), "seller_check": self.seller_check, "i_max": ds::I_MAX, "pend_max_ms": ds::PEND_MAX_NS / 1_000_000})
    }
}

/// one dump decided on shreds, waiting for the executed feed
pub struct SDump {
    pub mint: Pk,
    pub sig58: String,
    pub slot: u64,
    /// first sighting (feed clock) and its feed; when the decision was taken (now_ns)
    pub t_shred: u64,
    pub feed: u16,
    pub t_dec: u64,
    /// the priced trade (i = i_lo)
    pub tr: T,
    pub fees: (u32, u32),
    pub i_lo: u32,
    pub i_hi: u32,
    /// the executed feed's highest index in the slot at the sighting
    pub progress: Option<u32>,
    /// the decision for every index (exact policy) and the window policy's
    pub pick: Option<bool>,
    pub w_pick: Option<bool>,
    pub w_range: Option<(u32, u32)>,
    pub pick_lo: bool,
    pub imit: (f64, f64),
    pub m2: Option<(f64, f64)>,
    pub env: Option<bool>,
    /// what was done: fired / would_fire / nopick / depends / skip:<why>
    pub what: String,
    pub fired: Option<(u64, String)>,
    pub min_out: Option<u64>,
    /// the seller holds fewer tokens than it sells per the book (the sell may fail: it got tokens by transfer, or holds none)
    pub seller_short: bool,
}

/// the counters (status line, run_end)
#[derive(Default)]
pub struct Stats {
    pub classified: u64, pub sells: u64, pub candidates: u64, pub decided: u64,
    pub why: FxHashMap<&'static str, u64>,
    pub pick: u64, pub nopick: u64, pub depends: u64, pub fired: u64, pub would_fire: u64,
    pub parity: u64, pub dec_equal: u64, pub dec_differ: u64, pub in_equal: u64, pub in_differ: u64, pub idx_in_range: u64, pub idx_out: u64,
    pub w_idx_in: u64, pub w_idx_out: u64, pub dump_failed: u64, pub unseen: u64, pub exec_only: u64,
    pub saved_us: Vec<f32>, pub eval_us: Vec<f32>,
}

pub struct ShredFire {
    pub cfg: Cfg,
    pub tr: Tracker,
    /// decided dumps by sig8 (the tx's first sell of the token that is a dump)
    pub dumps: FxHashMap<u64, SDump>,
    /// classified big-sell candidates that were not decided, by sig8: why (for the executed path's dumps: coverage)
    pub undecided: FxHashMap<u64, (&'static str, u64)>,
    pub st: Stats,
    last_prune: u64,
    /// tokens whose shred-priced dump differed from the executed trade (a book the shred path cannot trust): the executed path
    /// decides them for the rest of the run (`shred_fallback` record)
    pub fallback: rustc_hash::FxHashSet<Pk>,
}

fn push_cap(v: &mut Vec<f32>, x: f64) { if v.len() < 8192 { v.push(x as f32); } else { let i = (x.to_bits() as usize) % v.len(); v[i] = x as f32; } }
fn pctl(v: &[f32], q: f64) -> f64 {
    let mut w = v.to_vec();
    w.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    w.get(((w.len().max(1) - 1) as f64 * q).round() as usize).map(|&x| x as f64).unwrap_or(0.0)
}

impl ShredFire {
    pub fn new(cfg: Cfg) -> ShredFire {
        ShredFire { cfg, tr: Tracker::default(), dumps: FxHashMap::default(), undecided: FxHashMap::default(), st: Stats::default(), last_prune: 0, fallback: Default::default() }
    }

    fn why(&mut self, w: &'static str) { *self.st.why.entry(w).or_default() += 1; }

    /// an executed-feed arrival (ok or failed): no longer pending; the slot's progress; a decided dump that FAILED gets its
    /// parity record now (an ok one gets it from the trade loop: `exec_dump`)
    pub fn on_exec_arrival(&mut self, a: &arbx::feeds::Arrival, log: &DipLog) {
        let k = ds::sig8(&a.tx.sig);
        self.tr.confirmed(k, a.slot, a.exec.as_ref().map(|x| x.index), a.t_rx);
        if a.executed == Some(false) {
            if let Some(d) = self.dumps.remove(&k) {
                self.st.dump_failed += 1;
                log.w(serde_json::json!({"ev": "shred_parity", "mint": b58(&d.mint), "sig": d.sig58, "result": "dump_failed", "what": d.what, "slot": a.slot,
                    "t_shred": d.t_shred, "t_exec": a.t_rx, "pick_shred": d.pick, "seller_short": d.seller_short, "pred": {"sol": d.tr.sol, "tok": d.tr.tok},
                    "fired": d.fired.as_ref().map(|f| f.1.clone())}));
            }
        }
    }

    /// prune: pending txs that never executed; decided dumps the executed feed never delivered (shred_unseen)
    pub fn tick(&mut self, now: u64, log: &DipLog) {
        if now.saturating_sub(self.last_prune) < 500_000_000 { return; }
        self.last_prune = now;
        self.tr.prune(now);
        let old: Vec<u64> = self.dumps.iter().filter(|(_, d)| now.saturating_sub(d.t_shred) > 3_000_000_000).map(|(k, _)| *k).collect();
        for k in old {
            if let Some(d) = self.dumps.remove(&k) {
                self.st.unseen += 1;
                log.w(serde_json::json!({"ev": "shred_unseen", "mint": b58(&d.mint), "sig": d.sig58, "slot": d.slot, "what": d.what, "t_shred": d.t_shred,
                    "fired": d.fired.as_ref().map(|f| f.1.clone())}));
            }
        }
        self.undecided.retain(|_, v| now.saturating_sub(v.1) < 10_000_000_000);
    }

    /// the executed path's decision on a dump trade of `mint` (`tr` as executed, `x_index` its tx index, `pick` its decision): the
    /// parity record of a shred-decided dump (removed); a dump the shred path did not decide is counted by why. -> it was bought
    /// on its shred sighting (the executed path must not buy it again)
    #[allow(clippy::too_many_arguments)]
    pub fn exec_dump(&mut self, sig: &[u8; 64], mint: &Pk, tr: &T, x_index: u64, pick: bool, t_exec_rx: u64, log: &DipLog) -> bool {
        let k = ds::sig8(sig);
        let mine = self.dumps.get(&k).is_some_and(|d| d.mint == *mint && d.tr.tok == tr.tok);
        if !mine {
            if self.dumps.get(&k).is_some_and(|d| d.mint == *mint) { return false; }      // another trade of the same tx and token
            self.st.exec_only += 1;
            let why = self.undecided.get(&k).map(|v| v.0).unwrap_or("not_seen_on_shreds");
            *self.st.why.entry(match why { "not_seen_on_shreds" => "exec_only:not_seen", "pending_ahead" => "exec_only:pending_ahead",
                "no_history" => "exec_only:no_history", "unpriceable" => "exec_only:unpriceable", "multi_sell" => "exec_only:multi_sell",
                "no_dump_event" => "exec_only:no_dump_event", "slip_fail_gross" | "slip_fail_net" => "exec_only:slip_fail", "seller_short" => "exec_only:seller_short",
                "token_fallback" => "exec_only:token_fallback",
                _ => "exec_only:other" }).or_default() += 1;
            log.w(serde_json::json!({"ev": "shred_parity", "mint": b58(mint), "sig": tr.sig, "result": "exec_only", "why": why, "pick_exec": pick, "slot": tr.s, "idx": x_index,
                "t_exec": t_exec_rx, "t_shred": self.undecided.get(&k).map(|v| v.1)}));
            return false;
        }
        let d = self.dumps.remove(&k).unwrap();
        let now = arbx::feeds::clock::now_ns();
        let inputs_equal = (d.tr.sol, d.tr.tok, d.tr.vsol, d.tr.vtok, &d.tr.user) == (tr.sol, tr.tok, tr.vsol, tr.vtok, &tr.user);
        let fees_equal = d.fees == (tr.fbps, tr.cbps);
        let i = x_index as u32;
        let in_range = i >= d.i_lo && i <= d.i_hi;
        let in_w = d.w_range.map(|(a, b)| i >= a && i <= b);
        self.st.parity += 1;
        if inputs_equal { self.st.in_equal += 1; } else { self.st.in_differ += 1; }
        if in_range { self.st.idx_in_range += 1; } else { self.st.idx_out += 1; }
        match in_w { Some(true) => self.st.w_idx_in += 1, Some(false) => self.st.w_idx_out += 1, None => {} }
        // the shred side's decision: what it acted on (the window policy's when configured and decisive, else the exact one)
        let shred_pick = if self.cfg.window.is_some() { d.w_pick.or(d.pick) } else { d.pick };
        let dec_equal = shred_pick.map(|p| p == pick);
        match dec_equal { Some(true) => self.st.dec_equal += 1, Some(false) => self.st.dec_differ += 1, None => {} }
        let saved_ms = (t_exec_rx as i64 - d.t_shred as i64) as f64 / 1e6;
        if d.fired.is_some() { push_cap(&mut self.st.saved_us, saved_ms * 1e3); }
        // a mismatch: this token's book cannot be trusted on shreds: the executed path decides it from now on
        if !inputs_equal && self.fallback.insert(d.mint) {
            *self.st.why.entry("token_fallback").or_default() += 1;
            log.w(serde_json::json!({"ev": "shred_fallback", "mint": b58(&d.mint), "sig": d.sig58, "slot": tr.s, "why": "inputs_differ",
                "pred": {"sol": d.tr.sol, "vsol": d.tr.vsol, "vtok": d.tr.vtok}, "exec": {"sol": tr.sol, "vsol": tr.vsol, "vtok": tr.vtok}}));
        }
        log.w(serde_json::json!({"ev": "shred_parity", "mint": b58(&d.mint), "sig": d.sig58, "result": "executed", "what": d.what, "slot": tr.s, "idx": x_index,
            "i_lo": d.i_lo, "i_hi": d.i_hi, "idx_in_range": in_range, "w_range": d.w_range, "idx_in_window": in_w, "progress": d.progress,
            "inputs_equal": inputs_equal, "fees_equal": fees_equal, "pred": {"sol": d.tr.sol, "tok": d.tr.tok, "vsol": d.tr.vsol, "vtok": d.tr.vtok, "user": d.tr.user, "fees": d.fees},
            "exec": {"sol": tr.sol, "tok": tr.tok, "vsol": tr.vsol, "vtok": tr.vtok, "user": tr.user, "fees": (tr.fbps, tr.cbps)},
            "pick_shred": d.pick, "pick_window": d.w_pick, "pick_exec": pick, "decision_equal": dec_equal, "seller_short": d.seller_short,
            "t_shred": d.t_shred, "t_shred_decided": d.t_dec, "t_exec": t_exec_rx, "t_exec_decided": now,
            "ms_shred_to_exec_rx": saved_ms, "ms_decisions": (now as i64 - d.t_dec as i64) as f64 / 1e6, "fired": d.fired.as_ref().map(|f| f.1.clone())}));
        d.fired.is_some()
    }

    /// the executed feed's tx is done: a shred-decided dump of it that the executed path found no dump event for
    pub fn exec_tx_done(&mut self, sig: &[u8; 64], t_exec_rx: u64, log: &DipLog) {
        let k = ds::sig8(sig);
        if let Some(d) = self.dumps.remove(&k) {
            *self.st.why.entry("no_exec_dump").or_default() += 1;
            log.w(serde_json::json!({"ev": "shred_parity", "mint": b58(&d.mint), "sig": d.sig58, "result": "no_exec_dump", "what": d.what, "slot": d.slot,
                "t_shred": d.t_shred, "t_exec": t_exec_rx, "pred": {"sol": d.tr.sol, "tok": d.tr.tok, "vsol": d.tr.vsol, "vtok": d.tr.vtok}, "fired": d.fired.as_ref().map(|f| f.1.clone())}));
        }
    }

    /// status line
    pub fn line(&self) -> String {
        let (pt, ps) = self.tr.sizes();
        let mut why: Vec<_> = self.st.why.iter().filter(|(_, v)| **v > 0).collect(); why.sort();
        format!(" | SHRED {}: sells {} candidates {} decided {} (pick {} nopick {} depends {}) fired {} would {} | parity {} (decision equal {} differ {}; inputs equal {} differ {}; idx in range {} out {}{}) failed {} unseen {} exec-only {} | pending {pt} tok / {ps} tx (stale {}) | eval {:.0} / {:.0} us p50 / p99 | saved {:.2} ms p50 | why {:?}",
            self.cfg.mode.as_str(), self.st.sells, self.st.candidates, self.st.decided, self.st.pick, self.st.nopick, self.st.depends, self.st.fired, self.st.would_fire,
            self.st.parity, self.st.dec_equal, self.st.dec_differ, self.st.in_equal, self.st.in_differ, self.st.idx_in_range, self.st.idx_out,
            if self.cfg.window.is_some() { format!("; window in {} out {}", self.st.w_idx_in, self.st.w_idx_out) } else { String::new() },
            self.st.dump_failed, self.st.unseen, self.st.exec_only, self.tr.stale, pctl(&self.st.eval_us, 0.5), pctl(&self.st.eval_us, 0.99), pctl(&self.st.saved_us, 0.5) / 1e3, why)
    }

    pub fn json(&self) -> serde_json::Value {
        let s = &self.st;
        serde_json::json!({"cfg": self.cfg.json(), "classified": s.classified, "sells": s.sells, "candidates": s.candidates, "decided": s.decided, "pick": s.pick, "nopick": s.nopick,
            "depends": s.depends, "fired": s.fired, "would_fire": s.would_fire, "parity": s.parity, "decision_equal": s.dec_equal, "decision_differ": s.dec_differ,
            "inputs_equal": s.in_equal, "inputs_differ": s.in_differ, "idx_in_range": s.idx_in_range, "idx_out": s.idx_out, "window_in": s.w_idx_in, "window_out": s.w_idx_out,
            "dump_failed": s.dump_failed, "unseen": s.unseen, "exec_only": s.exec_only, "stale_pending": self.tr.stale, "why": s.why.iter().map(|(k, v)| (k.to_string(), *v)).collect::<HashMap<_, _>>(),
            "eval_us_p50": pctl(&s.eval_us, 0.5), "eval_us_p99": pctl(&s.eval_us, 0.99), "saved_ms_p50": pctl(&s.saved_us, 0.5) / 1e3, "saved_ms_p90": pctl(&s.saved_us, 0.9) / 1e3})
    }
}

/// what the shred decision needs from the run (dipmode's locals)
pub struct Gates<'a> {
    pub model: &'a Imit, pub cohort: &'a HashSet<String>, pub targets: &'a HashSet<String>, pub max_age_s: f64, pub thr: f64, pub thr_dev: f64,
    pub m2: Option<&'a arbx::dip_model::Bundle>, pub m2_gate: bool, pub m2_min: f64, pub m2_extra: bool,
}

/// a robust shred pick, for the executed path's checks + fire (dipmode)
pub struct Pick { pub mint: Pk, pub tr: T, pub d: arbx::dip_imit::Dump, pub dev: bool, pub fees: (u32, u32), pub sig8: u64, pub t_dec: u64, pub eval_us: f64 }

impl ShredFire {
    /// a shred-feed arrival: classify it once per signature, track it as pending on the tokens it can move, and decide its
    /// dump (if any). -> the robust picks to fire (live) / log (shadow); every decision is in self.dumps for the parity
    #[allow(clippy::too_many_arguments)]
    pub fn on_shred(&mut self, a: &arbx::feeds::Arrival, toks: &mut HashMap<Pk, Tok>, m2toks: &mut HashMap<Pk, arbx::dip_model::Tok>, g: &Gates) -> (Vec<Pick>, bool) {
        let mut out = Vec::new();
        let mut decided = false;
        // a raw shred / entries copy with unresolved lookup tables is not classified: a deshred copy (resolved) follows
        if ds::unresolved(&a.tx) { return (out, false); }
        let k = ds::sig8(&a.tx.sig);
        if !self.tr.first_sighting(k, a.t_rx) { return (out, false); }
        let cls = ds::classify(&a.tx, &|m| toks.contains_key(m));
        if cls.is_empty() { return (out, false); }
        self.st.classified += 1;
        let moving: Vec<Pk> = cls.iter().filter(|(_, t)| t.trades()).map(|(m, _)| *m).collect();
        let sig58 = bs58::encode(&a.tx.sig).into_string();
        for (mint, touch) in cls {
            let Touch::Sells(sells) = touch else { continue };
            if sells.is_empty() { continue; }
            self.st.sells += 1;
            let Some(tk) = toks.get_mut(&mint) else { continue };
            if self.fallback.contains(&mint) { self.undecided.insert(k, ("token_fallback", a.t_rx)); self.why("skip_token_fallback"); continue; }
            let Some(last) = tk.book.tr.last() else { self.undecided.insert(k, ("no_history", a.t_rx)); self.why("no_history"); continue };
            // a dump candidate: the tx's first sell of the token, priced on the book, >= 1 SOL (the IMIT1 dump and M2 extra rules
            // both need it); later sells of a multi-sell tx wait for the executed feed (their pre-state includes this one)
            let fees = ds::fee_guess(&tk.book);
            let progress = self.tr.progress(a.slot);
            let (lo, hi) = ds::index_range(tk.book.last_key(), a.slot, None, 0);
            let Some(priced) = ds::price_sells((last.vsol, last.vtok), &sells, a.slot, lo, &sig58, fees) else { self.undecided.insert(k, ("unpriceable", a.t_rx)); self.why("unpriceable"); continue };
            if priced[0].sol < arbx::dip::MIN_SELL { continue; }
            self.st.candidates += 1;
            let skip = |sf: &mut ShredFire, w: &'static str| { sf.undecided.insert(k, (w, a.t_rx)); sf.why(w); };
            if self.tr.pending_ahead(&mint, k) > 0 { skip(self, "pending_ahead"); continue; }
            if let Some(w) = priced.iter().zip(sells.iter()).find_map(|(p, s)| ds::slip_fail(p.sol, s.min_sol, fees)) { skip(self, if w == "min_sol_gross" { "slip_fail_gross" } else { "slip_fail_net" }); continue; }
            // the seller holds fewer tokens than it sells per the book: if it holds none the sell fails on chain; it may also have got them
            // by transfer (MEASURED on the 10-24 recording: 3.1% of the executed dumps, 12% of IMIT1's picks, 4% of the M2 gate's).
            // Decided and recorded either way; with --dip-shred-seller-check on (default) such a pick waits for the executed feed
            let short = ds::seller_net(&tk.book, &priced[0].user) < sells[0].tokens as i128;
            let t0 = Instant::now();
            let gate = ds::Gate { model: g.model, cohort: g.cohort, targets: g.targets, max_age_s: g.max_age_s, thr: if tk.dev { g.thr_dev } else { g.thr }, dev: tk.dev,
                                  m2: g.m2, m2_gate: g.m2_gate, m2_min: g.m2_min, m2_extra: g.m2_extra };
            let mint58 = b58(&mint);
            let ev = ds::eval(&mut tk.book, m2toks.get_mut(&mint), &priced[0], hi, &gate, &mint58);
            let Some(ev) = ev else { skip(self, if sells.len() > 1 { "multi_sell" } else { "no_dump_event" }); continue };
            // the window policy (estimate): [progress - margin, progress + window], never below the exact lower bound
            let (w_pick, w_range) = match (self.cfg.window, progress) {
                (Some((mg, w)), Some(p)) => {
                    let (wl, wh) = ds::index_range(tk.book.last_key(), a.slot, Some((p, mg)), w);
                    let t2 = T { i: wl, ..priced[0].clone() };
                    (ds::eval(&mut tk.book, m2toks.get_mut(&mint), &t2, wh, &gate, &mint58).and_then(|e| e.pick), Some((wl, wh)))
                }
                _ => (None, None),
            };
            let eval_us = t0.elapsed().as_secs_f64() * 1e6;
            push_cap(&mut self.st.eval_us, eval_us);
            self.st.decided += 1;
            let decision = if self.cfg.window.is_some() { w_pick.or(ev.pick) } else { ev.pick };
            let held_back = short && self.cfg.seller_check && decision == Some(true);
            let what = match decision { Some(true) => { self.st.pick += 1; if held_back { self.why("seller_short"); "skip:seller_short" } else { "pick" } }
                                        Some(false) => { self.st.nopick += 1; "nopick" } None => { self.st.depends += 1; "depends" } };
            let t_dec = arbx::feeds::clock::now_ns();
            self.dumps.insert(k, SDump { mint, sig58: sig58.clone(), slot: a.slot, t_shred: a.t_rx, feed: a.feed, t_dec, tr: priced[0].clone(), fees, i_lo: ev.i_lo, i_hi: ev.i_hi,
                progress, pick: ev.pick, w_pick, w_range, pick_lo: ev.pick_lo, imit: ev.imit, m2: ev.m2.as_ref().and_then(|m| m.bounds), env: ev.env, what: what.to_string(),
                fired: None, min_out: None, seller_short: short });
            if decision == Some(true) && !held_back { out.push(Pick { mint, tr: priced[0].clone(), d: ev.d.clone(), dev: tk.dev, fees, sig8: k, t_dec, eval_us }); }
            decided = true;
            break;                                         // one decision per tx (the dumps map is keyed by the tx)
        }
        // every token this tx can move: pending until the executed feed confirms it (after the decisions: a tx is never ahead of itself)
        self.tr.add_pending(k, a.t_rx, a.slot, &moving);
        (out, decided)
    }

    /// the shred_dump record of a decided dump (written after any send)
    pub fn dump_rec(&self, k: u64, feed_names: &[String]) -> Option<serde_json::Value> {
        let d = self.dumps.get(&k)?;
        Some(serde_json::json!({"ev": "shred_dump", "mint": b58(&d.mint), "sig": d.sig58, "slot": d.slot, "t_shred": d.t_shred,
            "feed": feed_names.get(d.feed as usize).cloned().unwrap_or_else(|| d.feed.to_string()), "t_decided": d.t_dec, "ms_decide": (d.t_dec as i64 - d.t_shred as i64) as f64 / 1e6,
            "sol": d.tr.sol, "tok": d.tr.tok, "vsol": d.tr.vsol, "vtok": d.tr.vtok, "user": d.tr.user, "fees": d.fees, "i_lo": d.i_lo, "i_hi": d.i_hi, "progress": d.progress,
            "pick": d.pick, "pick_lo": d.pick_lo, "pick_window": d.w_pick, "w_range": d.w_range, "imit_lo": d.imit.0, "imit_hi": d.imit.1, "m2_lo": d.m2.map(|m| m.0),
            "m2_hi": d.m2.map(|m| m.1), "env": d.env, "what": d.what, "min_out": d.min_out, "seller_short": d.seller_short, "fired": d.fired.as_ref().map(|f| f.1.clone())}))
    }

    /// set what a pick became (fired / would_fire / skip:<why>) and its buy
    pub fn set_what(&mut self, k: u64, what: String, fired: Option<(u64, String)>, min_out: Option<u64>) {
        if let Some(d) = self.dumps.get_mut(&k) {
            if fired.is_some() { self.st.fired += 1; } else if what == "would_fire" { self.st.would_fire += 1; }
            d.what = what; d.fired = fired; d.min_out = min_out;
        }
    }
}

/// the dip14 leader-client flags: --dip-skip-clients LIST (C1), --dip-probe-clients LIST, --dip-probe-tipless on|off (D3)
pub struct ClientFlags { pub skip_clients: Option<Vec<String>>, pub probe_clients: Option<Vec<String>>, pub probe_tipless: bool }

/// the flags on a command line, refused when malformed or without what they need (unit-tested): the probe filters need
/// --dip-probe N; the tipless twin needs --dip-probe-paths (one path per probe)
pub fn client_flags(argv: &[String], probe_n: u64, probe_paths: bool) -> Result<ClientFlags> {
    let arg = |f: &str| argv.iter().position(|x| x == f).and_then(|i| argv.get(i + 1)).cloned();
    let has = |f: &str| argv.iter().skip(1).any(|x| x == f);
    let skip_clients = match arg("--dip-skip-clients") { Some(s) => Some(parse_client_list("--dip-skip-clients", &s)?), None => None };
    let probe_clients = match arg("--dip-probe-clients") { Some(s) => Some(parse_client_list("--dip-probe-clients", &s)?), None => None };
    let probe_tipless = match arg("--dip-probe-tipless").as_deref() { None | Some("off") => false, Some("on") => true, Some(x) => bail!("--dip-probe-tipless {x}: on | off") };
    if probe_n == 0 && (probe_clients.is_some() || has("--dip-probe-tipless")) { bail!("--dip-probe-clients / --dip-probe-tipless need --dip-probe N"); }
    if probe_tipless && !probe_paths { bail!("--dip-probe-tipless on needs --dip-probe-paths (one path per probe: the twin goes through the same one)"); }
    Ok(ClientFlags { skip_clients, probe_clients, probe_tipless })
}

/// C1 (--dip-skip-clients LIST): the leader client names / classes never fired on (e.g. Rakurai: 7 of 8 spilled); a name
/// matches the leader book's clientId (any case) or its class (lat::class: bam, harmonic, jito, fd, agave, other)
pub fn parse_client_list(flag: &str, s: &str) -> Result<Vec<String>> {
    let v: Vec<String> = s.split(',').map(|x| x.trim().to_ascii_lowercase()).filter(|x| !x.is_empty()).collect();
    if v.is_empty() { bail!("{flag}: an empty list"); }
    for x in &v { if !x.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_') { bail!("{flag}: '{x}' is not a client name or class"); } }
    Ok(v)
}

/// the leader client `client` (clientId) matches the list (by name or by class)
pub fn client_in(list: &[String], client: &str) -> bool {
    let c = client.to_ascii_lowercase();
    let k = lat::class(client);
    list.iter().any(|x| *x == c || x == k)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn v(a: &[&str]) -> Vec<String> { a.iter().map(|s| s.to_string()).collect() }

    fn pk32(s: &str) -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }

    /// a shred-feed arrival of a tx that sells `tokens` of `mint` from `seller` (pump sell layout 0: mint at account 2, seller at 6)
    fn sell_arrival(mint: Pk, seller: Pk, tokens: u64, min_sol: u64, slot: u64, sig: [u8; 64], t: u64) -> arbx::feeds::Arrival {
        let mut data = arbx::dip::SELL_LAYOUTS[0].0.to_vec();
        data.extend(tokens.to_le_bytes()); data.extend(min_sol.to_le_bytes());
        let tx = arbx::tx::Tx { sig, keys: vec![seller, *arbx::snipe::PUMP, mint], ixs: vec![arbx::tx::Ix { program: 1, accounts: vec![0, 0, 2, 0, 0, 0, 0], data }], ..Default::default() };
        arbx::feeds::Arrival { feed: 0, slot, t_rx: t, t_decoded: t, executed: None, tx, poh: None, raw: arbx::feeds::RawTx::None, exec: None }
    }
    /// a shred-feed arrival of a pump BUY of `mint` (unpriceable: it makes the token's book pending)
    fn buy_arrival(mint: Pk, slot: u64, sig: [u8; 64], t: u64) -> arbx::feeds::Arrival {
        let mut data = vec![0x66u8, 0x06, 0x3d, 0x12, 0x01, 0xda, 0xeb, 0xea]; data.extend([0u8; 16]);
        let tx = arbx::tx::Tx { sig, keys: vec![[3; 32], *arbx::snipe::PUMP, mint], ixs: vec![arbx::tx::Ix { program: 1, accounts: vec![0, 0, 2], data }], ..Default::default() };
        arbx::feeds::Arrival { feed: 1, slot, t_rx: t, t_decoded: t, executed: None, tx, poh: None, raw: arbx::feeds::RawTx::None, exec: None }
    }
    fn exec_arrival(slot: u64, sig: [u8; 64], ok: bool, t: u64) -> arbx::feeds::Arrival {
        let tx = arbx::tx::Tx { sig, ..Default::default() };
        arbx::feeds::Arrival { feed: 2, slot, t_rx: t, t_decoded: t, executed: Some(ok), tx, poh: None, raw: arbx::feeds::RawTx::None, exec: None }
    }

    /// The engine's shred path on the M2 parity tapes (IMIT1 + M2 gate as run 15): every big sell is first seen as a shred tx
    /// (on_shred: classify, price, decide), then executed (the books updated as dipmode does, the executed decision, exec_dump):
    /// every robust shred decision equals the executed one, every shred-priced input equals the executed trade; a second
    /// feed's copy is no new sighting; a failed dump gets a dump_failed record; a decided dump the executed feed finds no dump in
    /// gets no_exec_dump; an unconfirmed buy on the token ahead of a dump makes it wait (pending_ahead); a fired dump returns
    /// true from exec_dump (the executed path does not buy it again)
    #[test]
    fn shred_wiring_on_parity_tapes() {
        let root = env!("CARGO_MANIFEST_DIR");
        let Some(par) = std::fs::read_to_string(format!("{root}/testdata/dip_m2_parity.json")).ok().and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok()) else { return; };
        let Ok(b) = arbx::dip_model::Bundle::load(&format!("{root}/testdata/dip_m2_bundle.json")) else { return; };
        let Ok(model) = Imit::load(&format!("{root}/ops/overnight/sel/IMIT1.json")) else { return; };
        let cohort: HashSet<String> = serde_json::from_str::<Vec<String>>(&std::fs::read_to_string(format!("{root}/ops/overnight/sel/cohort_train.json")).unwrap()).unwrap().into_iter().collect();
        let targets: HashSet<String> = arbx::dip_imit::TARGETS.iter().map(|s| s.to_string()).collect();
        let thr = model.thresholds["top4"];
        let g = Gates { model: &model, cohort: &cohort, targets: &targets, max_age_s: 1800.0, thr, thr_dev: thr, m2: Some(&b), m2_gate: true, m2_min: b.thr_default, m2_extra: true };
        let dir = std::env::temp_dir().join(format!("shred_wiring_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let lp = dir.join("dip.jsonl");
        let log = DipLog::open(Some(lp.to_string_lossy().to_string())).unwrap();
        let mut sf = ShredFire::new(Cfg { mode: Mode::Shadow, window: None, seller_check: false });
        let mut toks: HashMap<Pk, Tok> = HashMap::new();
        let mut m2toks: HashMap<Pk, arbx::dip_model::Tok> = HashMap::new();
        let none = |_s: u64| -> Option<u64> { None };
        let (mut n_big, mut n_dec, mut n_pick, mut n_exec_pick, mut t) = (0u64, 0u64, 0u64, 0u64, 1_000_000_000u64);
        let (mut sigs_seen, mut n_wait) = (0u64, 0u64);
        let mut gapped: HashSet<String> = HashSet::new();
        for (ti, tk) in par["tokens"].as_array().unwrap().iter().enumerate() {
            let mint = pk32(tk["mint"].as_str().unwrap());
            let la = &tk["launch"];
            let li = arbx::dip_imit::LaunchInfo { slot: la["slot"].as_u64().unwrap(), idx: la["idx"].as_u64().map(|v| v as u32), creator: la["creator"].as_str().map(|s| s.to_string()),
                signer: la["user"].as_str().map(|s| s.to_string()), sig: la["sig"].as_str().unwrap_or("").to_string(), mayhem: false };
            toks.insert(mint, Tok { book: arbx::dip_imit::TokenBook::new(li), launch: None, t_created: Instant::now(), last_pick_slot: None, dev: false, keys: None });
            m2toks.insert(mint, arbx::dip_model::Tok::new(la["slot"].as_u64().unwrap()));
            let mut prev_tx: Option<(u64, u64)> = None;
            for (n, r) in tk["trades"].as_array().unwrap().iter().enumerate() {
                t += 1_000_000;
                let (s, i, j) = (r[0].as_u64().unwrap(), r[1].as_u64().unwrap(), r[2].as_i64().unwrap() as i32);
                let user = pk32(r[4].as_str().unwrap());
                let (buy, sol, tok, vsol, vtok) = (r[5].as_bool().unwrap(), r[6].as_u64().unwrap(), r[7].as_u64().unwrap(), r[8].as_u64().unwrap(), r[9].as_u64().unwrap());
                let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&((ti as u64) << 32 | n as u64).to_be_bytes()); sig[8] = 1;
                let first_in_tx = prev_tx != Some((s, i));
                prev_tx = Some((s, i));
                // the shred sighting of a big sell (the tx's first trade of the token)
                if !buy && sol >= arbx::dip::MIN_SELL && first_in_tx {
                    n_big += 1;
                    // every 7th dump: an unconfirmed buy on the token is ahead of it (it must wait, then the buy confirms)
                    let ahead = n_big % 7 == 0;
                    let mut bsig = sig; bsig[0] ^= 0x80;                // another tx (its own sig8)
                    // the book is exact when its newest post-state is this trade's pre-state (the tapes have a few gaps)
                    if let Some(l) = toks[&mint].book.tr.last() { if (l.vsol, l.vtok) != (vsol + sol, vtok - tok) { gapped.insert(bs58::encode(&sig).into_string()); } }
                    if ahead { let (p, d) = sf.on_shred(&buy_arrival(mint, s, bsig, t - 500_000), &mut toks, &mut m2toks, &g); assert!(p.is_empty() && !d); }
                    let a = sell_arrival(mint, user, tok, 0, s, sig, t);
                    let (picks, decided) = sf.on_shred(&a, &mut toks, &mut m2toks, &g);
                    sigs_seen += 1;
                    if ahead {
                        assert!(!decided, "a dump behind an unconfirmed tx on its token waits");
                        // (not a candidate at all when the tape's book has a gap before it: the shred price is then below 1 SOL)
                        // (checked after no_history: a tape can start with a big sell)
                        match sf.undecided.get(&arbx::dip_shred::sig8(&sig)).map(|x| x.0) {
                            Some("pending_ahead") => n_wait += 1,
                            Some(w) => assert!(w == "no_history" || w == "unpriceable", "waited for {w}"),
                            None => {}
                        }
                    }
                    if decided { n_dec += 1; }
                    n_pick += picks.len() as u64;
                    // a second feed's copy: nothing
                    let mut a2 = sell_arrival(mint, user, tok, 0, s, sig, t + 300); a2.feed = 1;
                    let (p2, d2) = sf.on_shred(&a2, &mut toks, &mut m2toks, &g);
                    assert!(p2.is_empty() && !d2, "a duplicate sighting decides nothing");
                    if ahead { sf.on_exec_arrival(&exec_arrival(s, bsig, true, t + 100), &log); }
                }
                // the executed trade, as dipmode feeds it
                let tr = arbx::dip_imit::T { s, i: i as u32, j, sig: bs58::encode(&sig).into_string(), user: bs58::encode(&user).into_string(), buy, sol, tok, vsol, vtok,
                    fbps: r[10].as_u64().unwrap_or(95) as u32, cbps: r[11].as_u64().unwrap_or(30) as u32, syn: false };
                let ea = exec_arrival(s, sig, true, t + 2_000_000);
                sf.on_exec_arrival(&ea, &log);
                let tkk = toks.get_mut(&mint).unwrap();
                let dump_k = tkk.book.push(tr.clone(), &targets, 1800.0, &none);
                let extra_k = if dump_k.is_none() && !buy && sol >= arbx::dip::MIN_SELL { tkk.book.later_in_slot((s, i as u32, j), 1800.0) } else { None };
                let t2 = arbx::dip_model::Tr { s, i: i as u32, j, buy, sol, tok, vsol, vtok, user };
                let mt = m2toks.get_mut(&mint).unwrap();
                mt.push(&t2, &b.sets);
                if let Some(k) = dump_k.or(extra_k) {
                    let d = tkk.book.dump("m", k, &model, &cohort, &none);
                    let m2s = if d.env_ok { mt.features().ok().map(|x| b.model.score(&x)) } else { None };
                    let pick = arbx::dip_shred::pick_rule(d.env_ok, d.launch_ok, d.score, thr, dump_k.is_none(), true, m2s, b.thr_default);
                    n_exec_pick += pick as u64;
                    let fired = sf.exec_dump(&sig, &mint, &tkk.book.tr[k], i, pick, ea.t_rx, &log);
                    assert!(!fired, "shadow fires nothing");
                }
                sf.exec_tx_done(&sig, ea.t_rx, &log);
            }
        }
        // a failed dump: a fresh token (create + dev buy, a buy, then a 1.5 SOL sell 20 slots later = an IMIT1 dump event), the sell
        // decided on shreds, then the executed feed reports its tx FAILED: a dump_failed record, and it is no longer waiting
        let fm: Pk = [0xF1; 32];
        let li = arbx::dip_imit::LaunchInfo { slot: 9_000_000, idx: Some(5), creator: Some(bs58::encode([0xC1u8; 32]).into_string()), signer: Some(bs58::encode([0xC1u8; 32]).into_string()),
            sig: "CREATE".into(), mayhem: false };
        let mut fb = arbx::dip_imit::TokenBook::new(li);
        let (mut v, mut k) = (30_000_000_000u64, 1_073_000_000_000_000u64);
        for (n, (s0, i0, sig0, sol)) in [(9_000_000u64, 5u32, "CREATE", 1_000_000_000u64), (9_000_010, 3, "BUY2", 2_000_000_000)].into_iter().enumerate() {
            let tok = (k as u128 * sol as u128 / (v as u128 + sol as u128)) as u64;
            v += sol; k -= tok;
            let _ = fb.push(arbx::dip_imit::T { s: s0, i: i0, j: 0, sig: sig0.into(), user: bs58::encode([0xC1u8 + n as u8; 32]).into_string(), buy: true, sol, tok, vsol: v, vtok: k,
                fbps: 95, cbps: 30, syn: false }, &targets, 1800.0, &none);
        }
        toks.insert(fm, Tok { book: fb, launch: None, t_created: Instant::now(), last_pick_slot: None, dev: false, keys: None });
        let mut fsig = [9u8; 64]; fsig[0] = 0xEE;
        let held_tok = arbx::dip_shred::seller_net(&toks[&fm].book, &bs58::encode([0xC2u8; 32]).into_string()) as u64;
        let (_, d_f) = sf.on_shred(&sell_arrival(fm, [0xC2; 32], held_tok, 0, 9_000_020, fsig, t + 50), &mut toks, &mut m2toks, &g);
        assert!(d_f, "the fresh token's sell is decided on shreds");
        let failed_before = sf.st.dump_failed;
        sf.on_exec_arrival(&exec_arrival(9_000_020, fsig, false, t + 60), &log);
        assert_eq!(sf.st.dump_failed, failed_before + 1);
        assert!(!sf.dumps.contains_key(&arbx::dip_shred::sig8(&fsig)));
        let (m0, tk0) = toks.iter().find(|(m, _)| **m != fm).map(|(m, t)| (*m, t.book.tr.last().unwrap().clone())).unwrap();
        // a fired dump: exec_dump returns true (no second buy)
        let mut gsig = [8u8; 64]; gsig[0] = 0xDD;
        let fake = arbx::dip_imit::T { s: tk0.s + 20, i: 5, j: 0, sig: bs58::encode(&gsig).into_string(), user: tk0.user.clone(), buy: false, sol: 2_000_000_000, tok: 7, vsol: 1, vtok: 1, fbps: 95, cbps: 30, syn: false };
        sf.dumps.insert(arbx::dip_shred::sig8(&gsig), SDump { mint: m0, sig58: fake.sig.clone(), slot: fake.s, t_shred: 1, feed: 0, t_dec: 2, tr: fake.clone(), fees: (95, 30), i_lo: 0,
            i_hi: arbx::dip_shred::I_MAX, progress: None, pick: Some(true), w_pick: None, w_range: None, pick_lo: true, imit: (1.0, 1.0), m2: None, env: Some(true), what: "fired".into(),
            fired: Some((3, "buy".into())), min_out: Some(1), seller_short: false });
        assert!(sf.exec_dump(&gsig, &m0, &fake, 5, true, 4, &log), "a dump bought on shreds is not bought again");
        drop(log);
        let recs: Vec<serde_json::Value> = std::fs::read_to_string(&lp).unwrap().lines().map(|l| serde_json::from_str(l).unwrap()).collect();
        let par_recs: Vec<&serde_json::Value> = recs.iter().filter(|r| r["ev"] == "shred_parity" && r["result"] == "executed").collect();
        let differ = par_recs.iter().filter(|r| r["decision_equal"] == serde_json::json!(false)).count();
        let in_differ = par_recs.iter().filter(|r| r["inputs_equal"] == serde_json::json!(false) && !gapped.contains(r["sig"].as_str().unwrap())).count();
        let in_differ_gap = par_recs.iter().filter(|r| r["inputs_equal"] == serde_json::json!(false)).count() - in_differ;
        let fake58 = bs58::encode(&gsig).into_string();
        let picks_equal = par_recs.iter().filter(|r| r["decision_equal"] == serde_json::json!(true) && r["pick_exec"] == serde_json::json!(true) && r["sig"] != fake58.as_str()).count();
        eprintln!("shred wiring: {sigs_seen} big sells seen on shreds ({n_wait} waited behind an unconfirmed buy), {n_dec} decided ({n_pick} robust picks; executed picks {n_exec_pick}), parity records {} (inputs differ {in_differ} + {in_differ_gap} behind a tape gap, decision differs {differ}, picks equal {picks_equal}) | {}",
            par_recs.len(), sf.line());
        assert_eq!(differ, 0, "a robust shred decision differs from the executed one");
        assert_eq!(in_differ, 0, "a shred-priced trade differs from the executed one (exact book)");
        assert!(n_dec > 200 && n_pick > 0 && picks_equal as u64 == n_pick, "every robust pick is an executed pick");
        assert!(n_wait > 20, "pending_ahead exercised");
        assert!(recs.iter().any(|r| r["result"] == "dump_failed"));
        // a mismatch (here: behind a tape gap) puts its token on the executed path for the rest of the run
        let fb: Vec<&serde_json::Value> = recs.iter().filter(|r| r["ev"] == "shred_fallback").collect();
        assert_eq!(fb.len(), in_differ_gap, "one fallback per token with a mismatch");
        for r in &fb { assert!(sf.fallback.contains(&pk32(r["mint"].as_str().unwrap()))); }
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn shred_flags_and_refusals() {
        let base = ["snipe_engine", "--dip"];
        let with = |x: &[&str]| { let mut a = v(&base); a.extend(x.iter().map(|s| s.to_string())); a };
        assert!(Cfg::from_argv(&with(&[]), true, false).unwrap().is_none());
        assert!(Cfg::from_argv(&with(&["--dip-shred-index", "window"]), true, false).is_err(), "a stray flag without --dip-shred-fire");
        let c = Cfg::from_argv(&with(&["--dip-shred-fire", "shadow"]), false, false).unwrap().unwrap();
        assert_eq!((c.mode, c.window, c.seller_check), (Mode::Shadow, None, true));
        assert!(!Cfg::from_argv(&with(&["--dip-shred-fire", "shadow", "--dip-shred-seller-check", "off"]), true, false).unwrap().unwrap().seller_check);
        assert!(Cfg::from_argv(&with(&["--dip-shred-fire", "shadow", "--dip-shred-seller-check", "maybe"]), true, false).is_err());
        assert!(Cfg::from_argv(&with(&["--dip-shred-seller-check", "off"]), true, false).is_err(), "a stray flag");
        assert!(Cfg::from_argv(&with(&["--dip-shred-fire", "live"]), false, false).is_err(), "live without --live");
        assert!(Cfg::from_argv(&with(&["--dip-shred-fire", "live"]), true, false).unwrap().unwrap().mode == Mode::Live);
        assert!(Cfg::from_argv(&with(&["--dip-shred-fire", "fast"]), true, false).is_err());
        assert!(Cfg::from_argv(&with(&["--dip-shred-fire", "shadow"]), true, true).is_err(), "with the landing probe");
        let w = Cfg::from_argv(&with(&["--dip-shred-fire", "shadow", "--dip-shred-index", "window", "--dip-shred-window", "60"]), true, false).unwrap().unwrap();
        assert_eq!(w.window, Some((40, 60)));
        assert!(Cfg::from_argv(&with(&["--dip-shred-fire", "shadow", "--dip-shred-window", "60"]), true, false).is_err(), "window size with the exact policy");
        assert!(Cfg::from_argv(&with(&["--dip-shred-fire", "shadow", "--dip-shred-index", "window", "--dip-shred-window", "0"]), true, false).is_err());
        assert!(Cfg::from_argv(&with(&["--dip-shred-fire", "shadow", "--dip-shred-index", "window", "--dip-shred-margin", "401"]), true, false).is_err());
        assert!(Cfg::from_argv(&with(&["--dip-shred-fire", "shadow", "--dip-shred-index", "guess"]), true, false).is_err());
        // the engine's start-up check knows every flag and types the numbers (a wrong spelling is built at run time: a "--..."
        // literal here would itself become a known flag)
        assert!(check_flags(&with(&["--dip-shred-fire", "shadow", "--dip-shred-index", "window", "--dip-shred-window", "60", "--dip-shred-margin", "30"])).is_ok());
        assert!(check_flags(&with(&["--dip-shred-fire", "shadow", "--dip-shred-index", "window", "--dip-shred-window", "x"])).is_err());
        let wrong = ["-", "-dip-shred-fir"].concat();
        assert!(check_flags(&with(&[&wrong, "shadow"])).is_err());
        // C1
        assert!(check_flags(&with(&["--dip-skip-clients", "Rakurai"])).is_ok());
        let l = parse_client_list("--dip-skip-clients", "Rakurai, fd").unwrap();
        assert!(client_in(&l, "Rakurai") && client_in(&l, "Firedancer") && client_in(&l, "Frankendancer") && !client_in(&l, "JitoLabs") && !client_in(&l, "AgaveBam"));
        assert!(parse_client_list("--dip-skip-clients", " , ").is_err());
        assert!(parse_client_list("--dip-skip-clients", "rak urai").is_err());
        let j = parse_client_list("--dip-probe-clients", "jito").unwrap();
        assert!(client_in(&j, "JitoLabs") && !client_in(&j, "HarmonicAgave") && !client_in(&j, "AgaveBam"));
        let h = parse_client_list("--dip-probe-clients", "harmonic,HarmonicFiredancer").unwrap();
        assert!(client_in(&h, "HarmonicAgave") && client_in(&h, "HarmonicFiredancer") && !client_in(&h, "JitoLabs"));
        // the client / probe flags and their refusals
        let cf = client_flags(&with(&["--dip-skip-clients", "Rakurai"]), 0, false).unwrap();
        assert_eq!((cf.skip_clients, cf.probe_clients, cf.probe_tipless), (Some(vec!["rakurai".to_string()]), None, false));
        assert!(client_flags(&with(&["--dip-probe-clients", "jito"]), 0, false).is_err(), "probe filter without --dip-probe");
        assert!(client_flags(&with(&["--dip-probe-tipless", "on"]), 20, false).is_err(), "tipless twin without one path per probe");
        assert!(client_flags(&with(&["--dip-probe-tipless", "yes"]), 20, true).is_err());
        assert!(client_flags(&with(&["--dip-skip-clients", ""]), 0, false).is_err());
        let ok = client_flags(&with(&["--dip-probe-clients", "jito", "--dip-probe-tipless", "on"]), 20, true).unwrap();
        assert_eq!((ok.probe_clients, ok.probe_tipless), (Some(vec!["jito".to_string()]), true));
        assert!(check_flags(&with(&["--dip-probe", "20", "--dip-probe-clients", "jito", "--dip-probe-tipless", "on", "--dip-defer", "--dip-clock2", "--dip-feed-lag", "--dip-busy-poll"])).is_ok());
    }
}
