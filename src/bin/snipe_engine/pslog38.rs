// =====================================================================================================================
// dip38 ANTI-BAIT LOG (owner "build dip38" 11-05; /home/it/sniper-data/antibait/REPORT.txt §7). LOG-ONLY: nothing of it ever arms,
// skips, withholds, sizes or exits anything; with its flags off nothing of it runs (no record, no field, no task, no file). The one live
// part of dip38 is the blocklist's launcher match (psblock.rs, --presend-live-blocklist-launcher, default on with the blocklist).
//   a) LAUNCHER: every create's tx fee payer (signer[0]) per mint (dtrzJPj7 pays the create, the pump "creator" field is a fresh wallet
//      on 527 of its 912 tokens): launcher, its holding now (launcher_pct), what it sold / bought on the curve since the create
//      (launcher_sold_pct / launcher_bought_pct), payer_ne_creator; on every presend_live_insider record
//   b) FUNDING RESOLVER (psfund.rs, its own low-priority thread, a bounded queue): on FIRST SIGHT of a window's whale / re-arm dumper or a >= 3%
//      holder of an armed token (at the arm, a new >= 3% buyer while armed, at each logged send, at the fill) the wallet is queued once;
//      its chain comes back as a presend_live_fund record and is kept (wallet -> chain) for the run (and in --presend-live-fund-state)
//   c) INSIDER (log): a >= 3% holder or the window's whale / dumper (never the launcher itself) has the token's launcher or creator in
//      its chain (any hop; hubs included). FAMILY (log): such a wallet's chain holds a blocklisted wallet. FAMILY LEDGER (log): per
//      launcher, the realized P&L of its INSIDER fills over 24 h (FL_WIN_NS); would-block = INSIDER and the launcher's sum <= -0.20 SOL
//      (FL_LOSS) with no fill >= +0.05 (FL_WIN); learned at realize (INSIDER at the fill, or with the chains known at the realize);
//      --presend-live-family-state FILE keeps it across runs
//   d) SHAPE LEDGER (log; --presend-live-shape-log on): els = the exact sizes (0.001% of supply) of the non-whale holders >= 3% held
//      BEFORE the current slot (this slot's own trades taken out); would-block = an el with fills summing <= -0.10 SOL (SH_LOSS) and no
//      fill >= +0.05 (SH_WIN) within 6 h (SH_WIN_NS); learned at realize from the fill's els; --presend-live-shape-state FILE
//   e) RECORDS: presend_live_insider / presend_live_shape with stage "arm" (every presend_live_arm), "send" (the first registered
//      attempt of each window slot: the sender's decision moment), "fill" (our fill: the holders at our landing, before our buy) and
//      "realize" (the P&L and what was learned); presend_live_fund (one per resolved wallet), presend_live_fund_state (a reload);
//      a terminal line on an arm / fill flag; the status line's "DIP38 LOG" part; run_end "dip38_log"
// HOT PATH: per trade one hash lookup (the launcher's own trades) + the shape's per-slot delta (shape on) + a holding check on armed
// mints (insider on); never an RPC, never a wait: the queue is try_send (full = dropped, counted, asked again at the next sight).
// =====================================================================================================================
use super::*;
use super::psfund::{Chains, FSt, FundOut};
use std::hash::Hash;

/// the holder threshold of every dip38 rule (% of supply), raw (3% of 1e15)
pub const AB_PCT: f64 = 3.0;
pub const AB_MIN: i64 = 30_000_000_000_000;
/// FAMILY LEDGER: 24 h, <= -0.20 SOL, no win >= 0.05 SOL
pub const FL_WIN_NS: u64 = 24 * 3_600 * 1_000_000_000;
pub const FL_LOSS: i64 = 200_000_000;
pub const FL_WIN: i64 = 50_000_000;
/// SHAPE LEDGER: 6 h, <= -0.10 SOL, no win >= 0.05 SOL
pub const SH_WIN_NS: u64 = 6 * 3_600 * 1_000_000_000;
pub const SH_LOSS: i64 = 100_000_000;
pub const SH_WIN: i64 = 50_000_000;
/// a fill's state waits this long for its realize
const FILL_KEEP: Duration = Duration::from_secs(7_200);
/// resolve lags kept for the median
const LAG_KEEP: usize = 4096;

pub fn pct(b: i64) -> f64 { b as f64 / pl::SUPPLY * 100.0 }
fn r3(x: f64) -> f64 { (x * 1000.0).round() / 1000.0 }
/// a holding's exact size in 0.001% of supply (the SHAPE element)
pub fn el_of(b: i64) -> u32 { (b.max(0) as f64 / pl::SUPPLY * 100_000.0).round() as u32 }
pub fn el_f(e: u32) -> f64 { e as f64 / 1000.0 }

/// a rolling P&L ledger: key -> its positions (t ns, P&L lamports) of the last `win_ns`
#[derive(Clone, Debug)]
pub struct Led<K: Hash + Eq> { pub m: FxHashMap<K, VecDeque<(u64, i64)>>, pub win_ns: u64 }

/// a ledger's view of one key at a time: positions, their sum, the best one (i64::MIN: none)
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct LView { pub n: u32, pub sum: i64, pub best: i64 }
impl Default for LView { fn default() -> LView { LView { n: 0, sum: 0, best: i64::MIN } } }
impl LView {
    /// >= 1 position, sum <= -loss, none >= +win
    pub fn blocks(&self, loss: i64, win: i64) -> bool { self.n >= 1 && self.sum <= -loss && self.best < win }
    pub fn json(&self, would: bool) -> serde_json::Value {
        serde_json::json!({"n": self.n, "sum": self.sum as f64 / 1e9, "best": (self.n > 0).then(|| self.best as f64 / 1e9), "would": would})
    }
}

impl<K: Hash + Eq + Copy> Led<K> {
    pub fn new(win_ns: u64) -> Led<K> { Led { m: FxHashMap::default(), win_ns } }
    pub fn add(&mut self, k: K, t: u64, pnl: i64) {
        let w = self.win_ns;
        let q = self.m.entry(k).or_default();
        q.push_back((t, pnl));
        while q.front().is_some_and(|x| x.0 + w < t) { q.pop_front(); }
    }
    /// the positions of `k` within the window ending at `now` (none later than `now`)
    pub fn view(&self, k: &K, now: u64) -> LView {
        let mut v = LView::default();
        for (t, p) in self.m.get(k).into_iter().flatten() {
            if *t + self.win_ns < now || *t > now { continue; }
            v.n += 1; v.sum += p; v.best = v.best.max(*p);
        }
        v
    }
    /// the newest position's time (0: none): the saves prune to it (the feed's clock, whatever the wall clock says)
    pub fn newest(&self) -> u64 { self.m.values().filter_map(|q| q.back().map(|x| x.0)).max().unwrap_or(0) }
    pub fn prune(&mut self, now: u64) {
        let w = self.win_ns;
        self.m.retain(|_, q| { while q.front().is_some_and(|x| x.0 + w < now) { q.pop_front(); } !q.is_empty() });
    }
}

/// a ledger key in the state file
pub trait LKey: Sized { fn ks(&self) -> String; fn kp(s: &str) -> Option<Self>; }
impl LKey for Pk {
    fn ks(&self) -> String { b58(self) }
    fn kp(s: &str) -> Option<Pk> { bs58::decode(s).into_vec().ok().and_then(|v| v.try_into().ok()) }
}
impl LKey for u32 {
    fn ks(&self) -> String { format!("{}.{:03}", self / 1000, self % 1000) }
    fn kp(s: &str) -> Option<u32> { s.parse::<f64>().ok().filter(|x| x.is_finite() && *x >= 0.0).map(|x| (x * 1000.0).round() as u32) }
}

/// {"v": 1, "kind": KIND, "win_h": H, "l": {key: [[t ns, lamports], ...]}} (PATH.tmp + rename) -> keys written
pub fn led_save<K: LKey + Hash + Eq + Copy>(l: &Led<K>, path: &str, kind: &str) -> Result<usize> {
    let m: serde_json::Map<String, serde_json::Value> = l.m.iter().filter(|(_, q)| !q.is_empty())
        .map(|(k, q)| (k.ks(), q.iter().map(|(t, p)| serde_json::json!([t, p])).collect::<Vec<_>>().into())).collect();
    let n = m.len();
    let tmp = format!("{path}.tmp");
    std::fs::write(&tmp, serde_json::json!({"v": 1, "kind": kind, "win_h": l.win_ns / 3_600_000_000_000, "l": m}).to_string()).with_context(|| format!("write {tmp}"))?;
    std::fs::rename(&tmp, path).with_context(|| format!("rename {tmp}"))?;
    Ok(n)
}
pub fn led_parse<K: LKey + Hash + Eq + Copy>(b: &[u8], win_ns: u64) -> Result<Led<K>> {
    let v: serde_json::Value = serde_json::from_slice(b).context("parse")?;
    let mut l = Led::new(win_ns);
    for (k, q) in v["l"].as_object().context("no \"l\" object")? {
        let Some(key) = K::kp(k) else { bail!("bad key {k}") };
        for x in q.as_array().context("not a list")? {
            let (Some(t), Some(p)) = (x[0].as_u64(), x[1].as_i64()) else { bail!("{k}: not [t, lamports]") };
            l.m.entry(key).or_default().push_back((t, p));
        }
    }
    Ok(l)
}
pub fn led_load<K: LKey + Hash + Eq + Copy>(path: &str, win_ns: u64) -> Result<Led<K>> {
    led_parse(&std::fs::read(path).with_context(|| format!("read {path}"))?, win_ns).with_context(|| path.to_string())
}

/// a token's launch: the create tx's fee payer, the pump creator field, the create slot, the payer's curve trades since (raw tokens)
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct LRec { pub payer: Pk, pub creator: Pk, pub slot: u64, pub bought: i64, pub sold: i64 }

/// a wallet the rules look at: its role (whale / dumper / holder) and holding (% of supply) then
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Cand { pub w: Pk, pub role: &'static str, pub pct: f64 }

/// a rule's hit: the wallet, the address in its chain (the launcher / creator / a listed wallet), its hop, the walk ("W<-F<-L")
#[derive(Clone, Debug, PartialEq)]
pub struct Hit { pub c: Cand, pub link: Pk, pub via: &'static str, pub hops: u8, pub summ: String }
impl Hit {
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"wallet": b58(&self.c.w), "role": self.c.role, "pct": r3(self.c.pct), "via": self.via, "link": b58(&self.link), "hops": self.hops, "chain": self.summ})
    }
}

/// INSIDER / FAMILY over the candidates: cov = [ok, deep, fail, pending, not asked]
#[derive(Clone, Debug, Default, PartialEq)]
pub struct V38 { pub n: usize, pub cov: [u32; 5], pub ins: Option<Hit>, pub fam: Option<Hit> }
impl V38 {
    pub fn cov_json(&self) -> serde_json::Value {
        serde_json::json!({"ok": self.cov[0], "deep": self.cov[1], "fail": self.cov[2], "pending": self.cov[3], "none": self.cov[4]})
    }
}

/// the rules (pure): INSIDER = a candidate but the launcher has the launcher or the creator anywhere in its chain; FAMILY = a candidate's
/// chain holds a listed wallet. The first hit of each in candidate order (whale / dumper first, then holders largest first)
pub fn judge(cands: &[Cand], launcher: Option<&Pk>, creator: Option<&Pk>, chains: &Chains, pending: &FxHashSet<Pk>, listed: Option<&FxHashMap<Pk, String>>) -> V38 {
    let mut v = V38 { n: cands.len(), ..Default::default() };
    for c in cands {
        let ch = chains.get(&c.w);
        match ch.map(|x| x.st) {
            Some(FSt::Ok) => v.cov[0] += 1,
            Some(FSt::Deep) => v.cov[1] += 1,
            Some(FSt::Fail) => v.cov[2] += 1,
            None => v.cov[if pending.contains(&c.w) { 3 } else { 4 }] += 1,
        }
        let Some(ch) = ch.filter(|x| x.st == FSt::Ok) else { continue };
        if v.ins.is_none() && launcher != Some(&c.w) {
            for (k, via) in [(launcher, "launcher"), (creator, "creator")] {
                let Some(k) = k.filter(|k| **k != c.w) else { continue };
                if let Some(i) = ch.find(k) {
                    v.ins = Some(Hit { c: *c, link: *k, via, hops: ch.links[i].hops, summ: ch.summary(&c.w, i) });
                    break;
                }
            }
        }
        if v.fam.is_none() {
            if let Some(l) = listed {
                if let Some(i) = ch.links.iter().position(|x| l.contains_key(&x.a)) {
                    v.fam = Some(Hit { c: *c, link: ch.links[i].a, via: "blocklist", hops: ch.links[i].hops, summ: ch.summary(&c.w, i) });
                }
            }
        }
    }
    v
}

/// a window the log follows
#[derive(Clone, Debug)]
pub struct W38 { pub mint: Pk, pub who: Pk, pub rearm: bool, pub last_send: u64, pub sends: u32 }

/// a fill's view, kept for its realize
#[derive(Clone, Debug)]
pub struct F38 { pub mint: Pk, pub rearm: bool, pub cands: Vec<Cand>, pub launcher: Option<Pk>, pub creator: Option<Pk>, pub ins: Option<Hit>, pub els: Vec<u32>, pub at: Instant }

/// what one stage's evaluation found (the fill keeps it)
#[derive(Default)]
struct Em { cands: Vec<Cand>, launcher: Option<Pk>, creator: Option<Pk>, ins: Option<Hit>, els: Vec<u32> }

/// counters bumped by the realized tasks
#[derive(Default, Debug)]
pub struct Lrn { pub fl: AtomicU64, pub sh: AtomicU64, pub rz: AtomicU64 }

/// a position's dip38 part for its realized task: the ledgers learn its P&L, the realize records are written
#[derive(Clone, Debug)]
pub struct Rz38 {
    pub w: u64, pub pid: u64, pub mint: Pk, pub rearm: bool, pub launcher: Option<Pk>, pub ins_fill: bool, pub late: Option<Hit>, pub cov_late: [u32; 5],
    pub els: Vec<u32>, pub ins_on: bool, pub shape_on: bool, pub fl: Arc<Mutex<Led<Pk>>>, pub sl: Arc<Mutex<Led<u32>>>, pub lrn: Arc<Lrn>,
}
impl Rz38 {
    /// the P&L into the ledgers (the family ledger: an INSIDER fill, at the fill or with the chains known now; the shape ledger: every el of
    /// the fill) -> the realize records
    pub fn learn(&self, pnl: i64, now: u64) -> Vec<serde_json::Value> {
        let mut out = Vec::new();
        let kind = if self.rearm { "rearm" } else { "T2" };
        self.lrn.rz.fetch_add(1, Ordering::Relaxed);
        if self.ins_on {
            let ins = self.ins_fill || self.late.is_some();
            let learn = ins && self.launcher.is_some();
            let after = self.launcher.map(|l| {
                let mut g = self.fl.lock().unwrap();
                if learn { g.add(l, now, pnl); }
                g.view(&l, now)
            });
            if learn { self.lrn.fl.fetch_add(1, Ordering::Relaxed); }
            let v = V38 { cov: self.cov_late, ..Default::default() };
            out.push(serde_json::json!({"ev": "presend_live_insider", "stage": "realize", "w": self.w, "pid": self.pid, "mint": b58(&self.mint), "kind": kind, "t": now,
                "pnl": pnl, "launcher": self.launcher.map(|l| b58(&l)), "insider_fill": self.ins_fill, "insider_late": self.late.is_some(),
                "late": self.late.as_ref().map(|h| h.json()), "cov_late": v.cov_json(), "learned": learn,
                "fl_after": after.map(|a| a.json(a.blocks(FL_LOSS, FL_WIN)))}));
        }
        if self.shape_on {
            let mut els = self.els.clone();
            els.sort_unstable(); els.dedup();
            if !els.is_empty() {
                let mut g = self.sl.lock().unwrap();
                for e in &els { g.add(*e, now, pnl); }
                self.lrn.sh.fetch_add(1, Ordering::Relaxed);
            }
            out.push(serde_json::json!({"ev": "presend_live_shape", "stage": "realize", "w": self.w, "pid": self.pid, "mint": b58(&self.mint), "kind": kind, "t": now,
                "pnl": pnl, "els": els.iter().map(|e| el_f(*e)).collect::<Vec<_>>(), "learned": !els.is_empty()}));
        }
        out
    }
}

/// the counters of the status line / run_end (index: arm, send, fill)
#[derive(Default, Debug)]
pub struct St38 {
    pub arms: u64, pub sends: u64, pub fills: u64, pub ins: [u64; 3], pub fam: [u64; 3], pub flw: [u64; 3], pub shw: [u64; 3],
    pub asked: u64, pub dropped: u64, pub ok: u64, pub deep: u64, pub fail: u64, pub loaded: u64, pub lags: Vec<f64>,
}

/// the probe's dip38 state (empty and idle with the flags off)
pub struct L38 {
    pub launch: FxHashMap<Pk, LRec>,
    pub chains: Chains,
    pub pending: FxHashSet<Pk>,
    /// the resolver's queue (a run); `q` the tests' queue instead
    pub tx: Option<tokio::sync::mpsc::Sender<Pk>>,
    pub q: Option<Vec<Pk>>,
    pub fsh: Arc<psfund::FundShared>,
    pub wins: FxHashMap<u64, W38>,
    pub fills: FxHashMap<u64, F38>,
    /// SHAPE: per mint, its newest slot's per-wallet token deltas (that slot's trades so far)
    pub sd: FxHashMap<Pk, (u64, Vec<(Pk, i64)>)>,
    sd_swept: u64, l_swept: u64,
    pub fl: Arc<Mutex<Led<Pk>>>,
    pub sl: Arc<Mutex<Led<u32>>>,
    pub saved: u64,
    pub st: St38,
    pub lrn: Arc<Lrn>,
}

impl Default for L38 {
    fn default() -> L38 {
        L38 { launch: FxHashMap::default(), chains: FxHashMap::default(), pending: FxHashSet::default(), tx: None, q: None, fsh: Arc::default(), wins: FxHashMap::default(),
            fills: FxHashMap::default(), sd: FxHashMap::default(), sd_swept: 0, l_swept: 0, fl: Arc::new(Mutex::new(Led::new(FL_WIN_NS))), sl: Arc::new(Mutex::new(Led::new(SH_WIN_NS))),
            saved: 0, st: St38::default(), lrn: Arc::default() }
    }
}

impl L38 {
    /// the state at the start: the chains / ledgers preloaded (a missing file: empty + a note; a bad one refuses the start); with `mtx`
    /// (a run) the resolver task is started on the current runtime, without it (the tests) wallets queue in `q`
    pub fn new(cfg: &Cfg, mtx: Option<tokio::sync::mpsc::UnboundedSender<Msg>>) -> Result<L38> {
        let mut l = L38::default();
        if !cfg.insider_log && !cfg.shape_log { return Ok(l); }
        let note = |what: &str, p: &Option<String>, n: Result<usize>| -> Result<String> {
            Ok(match (p, n) {
                (None, _) => format!("{what}: no state file (empty, not saved)"),
                (Some(p), Ok(n)) => format!("{what}: {n} preloaded from {p}"),
                (Some(p), Err(_)) if !std::path::Path::new(p).exists() => format!("{what}: NOTE {p} does not exist: starts EMPTY (saved there every ~10 min and at the run's end)"),
                (Some(p), Err(e)) => bail!("{what} {p}: {e:#}"),
            })
        };
        let mut msg = Vec::new();
        if cfg.insider_log {
            let r = match &cfg.fund_state { Some(p) => psfund::fund_load(p).map(|m| { let n = m.len(); l.chains = m; n }), None => Ok(0) };
            msg.push(note("funding chains", &cfg.fund_state, r)?);
            let r = match &cfg.family_state { Some(p) => led_load::<Pk>(p, FL_WIN_NS).map(|m| { let n = m.m.len(); *l.fl.lock().unwrap() = m; n }), None => Ok(0) };
            msg.push(note("family ledger", &cfg.family_state, r)?);
            match mtx {
                Some(mtx) => {
                    let url = match &cfg.fund_rpc {
                        Some(u) => config::expand(u).with_context(|| "--presend-live-fund-rpc names an env var that is empty / missing")?,
                        None => psfund::FUND_RPC.to_string(),
                    };
                    let (tx, rx) = tokio::sync::mpsc::channel::<Pk>(psfund::FUND_QUEUE);
                    let send: Box<dyn Fn(FundOut) + Send + Sync> = Box::new(move |o| { let _ = mtx.send(Msg::Ps(PsMsg::Fund(Box::new(o)))); });
                    psfund::spawn(url, cfg.fund_rps, cfg.fund_state.clone(), l.chains.clone(), rx, send, l.fsh.clone())?;
                    l.tx = Some(tx);
                }
                None => l.q = Some(Vec::new()),
            }
        }
        if cfg.shape_log {
            let r = match &cfg.shape_state { Some(p) => led_load::<u32>(p, SH_WIN_NS).map(|m| { let n = m.m.len(); *l.sl.lock().unwrap() = m; n }), None => Ok(0) };
            msg.push(note("shape ledger", &cfg.shape_state, r)?);
        }
        eprintln!("DIP PRESEND LIVE DIP38 ANTI-BAIT LOG (LOG ONLY): {}", msg.join(" | "));
        Ok(l)
    }
}

impl PsLive {
    /// dip38: the launchers are recorded (the insider log, or the blocklist's launcher match)
    pub(super) fn l38_launch_on(&self) -> bool { self.cfg.insider_log || self.cfg.shape_log || self.cfg.blocklist_launcher }
    pub(super) fn l38_on(&self) -> bool { self.cfg.insider_log || self.cfg.shape_log }

    /// on_exec: the tx's creates; `payer` = its fee payer (signer[0]; the create event's user when the tx has no keys)
    pub(super) fn l38_creates(&mut self, creates: &[arbx::dip::CreateEvent], payer: Option<Pk>, slot: u64) {
        for c in creates {
            self.l38.launch.entry(c.mint).or_insert(LRec { payer: payer.unwrap_or(c.user), creator: c.creator, slot, bought: 0, sold: 0 });
        }
    }

    /// on_exec: one trade AFTER the detector took it: the launcher's curve trades, the shape's per-slot deltas, a new >= 3% buyer of an
    /// armed token queued for its chain
    pub(super) fn l38_trade(&mut self, t: &pl::Trade) {
        if let Some(l) = self.l38.launch.get_mut(&t.mint) {
            if l.payer == t.user { if t.buy { l.bought += t.tok as i64; } else { l.sold += t.tok as i64; } }
        }
        if self.cfg.shape_log {
            let e = self.l38.sd.entry(t.mint).or_insert((t.s, Vec::new()));
            if t.s > e.0 { e.0 = t.s; e.1.clear(); }
            if t.s == e.0 {
                let d = if t.buy { t.tok as i64 } else { -(t.tok as i64) };
                match e.1.iter_mut().find(|x| x.0 == t.user) { Some(x) => x.1 += d, None => e.1.push((t.user, d)) }
            }
        }
        if self.cfg.insider_log && t.buy && t.user != self.user && self.armed.contains_key(&t.mint) && self.det.bal(&t.mint, &t.user) >= AB_MIN { self.l38_ask(t.user); }
    }

    /// queue a wallet for its chain (once: known, pending or a fresh failure are not asked again)
    pub(super) fn l38_ask(&mut self, w: Pk) {
        if w == self.user || self.l38.pending.contains(&w) { return; }
        if self.l38.chains.get(&w).is_some_and(|c| !c.stale(psfund::unix_s())) { return; }
        if let Some(q) = self.l38.q.as_mut() { q.push(w); self.l38.pending.insert(w); self.l38.st.asked += 1; return; }
        let Some(tx) = self.l38.tx.as_ref() else { return };
        match tx.try_send(w) {
            Ok(()) => { self.l38.pending.insert(w); self.l38.st.asked += 1; }
            Err(_) => self.l38.st.dropped += 1,
        }
    }

    /// the window's candidates now: its whale / dumper (any holding), then the other holders >= 3% (largest first; ours never)
    fn l38_cands(&self, mint: &Pk, who: &Pk, rearm: bool) -> Vec<Cand> {
        let mut v = vec![Cand { w: *who, role: if rearm { "dumper" } else { "whale" }, pct: pct(self.det.bal(mint, who)) }];
        for (w, b) in self.det.holders_at_least(mint, AB_MIN, &self.user).unwrap_or_default() {
            if w != *who { v.push(Cand { w, role: "holder", pct: pct(b) }); }
        }
        v
    }

    /// the token's launcher (create-tx payer) and creator (the launch record's, else the detector's)
    fn l38_lc(&self, mint: &Pk) -> (Option<Pk>, Option<Pk>) {
        let l = self.l38.launch.get(mint);
        (l.map(|x| x.payer), l.map(|x| x.creator).or_else(|| self.det.creator_bal(mint).map(|c| c.0)))
    }

    /// SHAPE: the exact sizes of the holders >= 3% (the whale / dumper and we out) held BEFORE `slot` (its own trades taken out)
    pub(super) fn l38_els(&self, mint: &Pk, slot: u64, not: &Pk) -> Vec<u32> {
        let cur: &[(Pk, i64)] = self.l38.sd.get(mint).filter(|e| e.0 == slot).map(|e| e.1.as_slice()).unwrap_or(&[]);
        let before = |w: &Pk, now: i64| now - cur.iter().find(|x| x.0 == *w).map_or(0, |x| x.1);
        let mut seen: Vec<Pk> = Vec::new();
        let mut out = Vec::new();
        // the holders >= 3% now, and this slot's sellers (>= 3% before their sale)
        let now_list = self.det.holders_at_least(mint, AB_MIN, &self.user).unwrap_or_default();
        for (w, b) in now_list.into_iter().chain(cur.iter().filter(|x| x.1 < 0).map(|x| (x.0, self.det.bal(mint, &x.0)))) {
            if w == *not || w == self.user || seen.contains(&w) { continue; }
            seen.push(w);
            let b0 = before(&w, b);
            if b0 >= AB_MIN { out.push(el_of(b0)); }
        }
        out
    }

    /// one stage's records (both logs as on) for window `id`; `t` = the stage's time (unix ns)
    fn l38_emit(&mut self, stage: &'static str, id: u64, slot: u64, t: u64) -> Em {
        let mut em = Em::default();
        let Some(w) = self.l38.wins.get(&id).cloned() else { return em };
        let si = match stage { "arm" => 0, "send" => 1, _ => 2 };
        let kind = if w.rearm { "rearm" } else { "T2" };
        if self.cfg.insider_log {
            let cands = self.l38_cands(&w.mint, &w.who, w.rearm);
            for c in &cands { self.l38_ask(c.w); }
            let (l, c) = self.l38_lc(&w.mint);
            let v = judge(&cands, l.as_ref(), c.as_ref(), &self.l38.chains, &self.l38.pending, self.bl.as_ref().map(|b| &b.set));
            let flv = l.map(|l| self.l38.fl.lock().unwrap().view(&l, t));
            let flw = v.ins.is_some() && flv.is_some_and(|x| x.blocks(FL_LOSS, FL_WIN));
            if v.ins.is_some() { self.l38.st.ins[si] += 1; }
            if v.fam.is_some() { self.l38.st.fam[si] += 1; }
            if flw { self.l38.st.flw[si] += 1; }
            let lr = self.l38.launch.get(&w.mint).copied();
            let mut r = serde_json::json!({"ev": "presend_live_insider", "stage": stage, "w": id, "mint": b58(&w.mint), "kind": kind, "slot": slot, "t": t,
                "launcher": l.map(|x| b58(&x)), "creator": c.map(|x| b58(&x)), "payer_ne_creator": lr.map(|x| x.payer != x.creator),
                "launcher_pct": l.map(|x| r3(pct(self.det.bal(&w.mint, &x)))), "launcher_sold_pct": lr.map(|x| r3(pct(x.sold))), "launcher_bought_pct": lr.map(|x| r3(pct(x.bought))),
                "cands": v.n, "cov": v.cov_json(), "insider": v.ins.is_some(), "ins": v.ins.as_ref().map(|h| h.json()), "family": v.fam.is_some(),
                "fam": v.fam.as_ref().map(|h| h.json()), "fl": flv.map(|x| x.json(x.blocks(FL_LOSS, FL_WIN))), "would": flw});
            if stage == "send" { r["n"] = w.sends.into(); }
            self.rec(r);
            if stage != "send" && (v.ins.is_some() || v.fam.is_some()) {
                self.line(format!("  PRESEND LIVE INSIDER (log) {stage} w{id} {}{}{}{}", b58(&w.mint),
                    v.ins.as_ref().map(|h| format!(" | INSIDER {} {} {:.1}% funded by the {} ({} hop(s): {})", h.c.role, &b58(&h.c.w)[..8], h.c.pct, h.via, h.hops, h.summ)).unwrap_or_default(),
                    v.fam.as_ref().map(|h| format!(" | FAMILY {} {} {:.1}% chain has listed {} ({})", h.c.role, &b58(&h.c.w)[..8], h.c.pct, &b58(&h.link)[..8], h.summ)).unwrap_or_default(),
                    flv.filter(|_| v.ins.is_some()).map(|x| format!(" | family ledger {} fills {:+.3} SOL -> {}", x.n, x.sum as f64 / 1e9, if flw { "WOULD BLOCK" } else { "pass" })).unwrap_or_default()));
            }
            em = Em { cands, launcher: l, creator: c, ins: v.ins, els: Vec::new() };
        }
        if self.cfg.shape_log {
            let els = self.l38_els(&w.mint, slot, &w.who);
            let hit = {
                let g = self.l38.sl.lock().unwrap();
                els.iter().map(|e| (*e, g.view(e, t))).find(|(_, v)| v.blocks(SH_LOSS, SH_WIN))
            };
            if hit.is_some() { self.l38.st.shw[si] += 1; }
            let mut r = serde_json::json!({"ev": "presend_live_shape", "stage": stage, "w": id, "mint": b58(&w.mint), "kind": kind, "slot": slot, "t": t,
                "els": els.iter().map(|e| el_f(*e)).collect::<Vec<_>>(), "hit": hit.map(|(e, v)| { let mut j = v.json(true); j["el"] = el_f(e).into(); j }), "would": hit.is_some()});
            if stage == "send" { r["n"] = w.sends.into(); }
            self.rec(r);
            if stage != "send" {
                if let Some((e, v)) = hit {
                    self.line(format!("  PRESEND LIVE SHAPE (log) {stage} w{id} {} | holder size {:.3}% had {} fills {:+.3} SOL in 6 h, no win -> WOULD BLOCK", b58(&w.mint), el_f(e), v.n, v.sum as f64 / 1e9));
                }
            }
            em.els = els;
        }
        em
    }

    /// a presend_live_arm (T2 / re-arm): the window followed, its stage "arm"
    pub(super) fn l38_arm(&mut self, id: u64, mint: Pk, who: Pk, rearm: bool, slot: u64, t: u64) {
        if !self.l38_on() { return; }
        self.l38.wins.insert(id, W38 { mint, who, rearm, last_send: 0, sends: 0 });
        self.l38.st.arms += 1;
        self.l38_emit("arm", id, slot, t);
    }

    /// drain_atts: an attempt registered; the first of each window slot is the window's stage "send"
    pub(super) fn l38_send(&mut self, id: u64, slot: u64) {
        let Some(w) = self.l38.wins.get_mut(&id) else { return };
        if w.last_send == slot { return; }
        w.last_send = slot;
        w.sends += 1;
        self.l38.st.sends += 1;
        self.l38_emit("send", id, slot, arbx::feeds::clock::now_ns());
    }

    /// our fill (before the detector took our buy): stage "fill", kept for the realize (a window's first fill)
    pub(super) fn l38_fill(&mut self, id: u64, mint: Pk, slot: u64, t: u64) {
        if !self.l38_on() { return; }
        if !self.l38.wins.contains_key(&id) {
            let Some(w) = self.wins.get(&id) else { return };
            let rearm = self.rearm_w(id);
            self.l38.wins.insert(id, W38 { mint, who: w.whale, rearm, last_send: 0, sends: 0 });
        }
        if self.l38.fills.contains_key(&id) { return; }
        self.l38.st.fills += 1;
        let em = self.l38_emit("fill", id, slot, t);
        let rearm = self.l38.wins.get(&id).is_some_and(|w| w.rearm);
        self.l38.fills.insert(id, F38 { mint, rearm, cands: em.cands, launcher: em.launcher, creator: em.creator, ins: em.ins, els: em.els, at: Instant::now() });
    }

    /// realized(): the fill's view (INSIDER judged again with the chains known now) for the realized task (None: off / no fill seen)
    pub(super) fn l38_realize(&mut self, w: u64, pid: u64, rearm: bool) -> Option<Box<Rz38>> {
        if !self.l38_on() { return None; }
        let f = self.l38.fills.remove(&w)?;
        let late = if self.cfg.insider_log {
            judge(&f.cands, f.launcher.as_ref(), f.creator.as_ref(), &self.l38.chains, &self.l38.pending, self.bl.as_ref().map(|b| &b.set))
        } else { V38::default() };
        Some(Box::new(Rz38 { w, pid, mint: f.mint, rearm: rearm || f.rearm, launcher: f.launcher, ins_fill: f.ins.is_some(), late: late.ins, cov_late: late.cov, els: f.els,
            ins_on: self.cfg.insider_log, shape_on: self.cfg.shape_log, fl: self.l38.fl.clone(), sl: self.l38.sl.clone(), lrn: self.l38.lrn.clone() }))
    }

    /// the resolver's answers
    pub(super) fn l38_fund(&mut self, o: FundOut) {
        match o {
            FundOut::Done(w, c, ms, calls) => {
                self.l38.pending.remove(&w);
                match c.st { FSt::Ok => self.l38.st.ok += 1, FSt::Deep => self.l38.st.deep += 1, FSt::Fail => self.l38.st.fail += 1 }
                if self.l38.st.lags.len() < LAG_KEEP { self.l38.st.lags.push(ms); }
                let mut r = c.json();
                r["ev"] = "presend_live_fund".into();
                r["wallet"] = b58(&w).into();
                r["ms"] = ((ms * 10.0).round() / 10.0).into();
                r["calls"] = calls.into();
                self.rec(r);
                self.l38.chains.insert(w, c);
            }
            FundOut::Loaded(v, info) => {
                let n = v.len();
                for (k, c) in v { self.l38.chains.insert(k, c); }
                self.l38.st.loaded += n as u64;
                let ok = !info.contains("NOT reloaded");
                self.rec(serde_json::json!({"ev": "presend_live_fund_state", "ok": ok, "new": n, "info": info, "cached": self.l38.chains.len()}));
                self.line(format!("  PRESEND LIVE FUND STATE {}: {n} new / newer chains ({})", if ok { "reloaded" } else { "NOT reloaded" }, info));
            }
        }
    }

    /// tick: housekeeping and the ledgers' saves (every ~10 min, off the event loop)
    pub(super) fn l38_tick(&mut self, slot_now: u64) {
        if !self.l38_launch_on() { return; }
        if slot_now >= self.l38.l_swept + 2048 {
            self.l38.l_swept = slot_now;
            let (det, armed, pos) = (&self.det, &self.armed, &self.pos);
            self.l38.launch.retain(|m, _| det.create_slot(m).is_some() || armed.contains_key(m) || pos.contains_key(m));
        }
        if !self.l38_on() { return; }
        if slot_now >= self.l38.sd_swept + 4 {
            self.l38.sd_swept = slot_now;
            self.l38.sd.retain(|_, e| e.0 + 8 >= slot_now);
            let wins = &self.wins;
            self.l38.wins.retain(|id, _| wins.contains_key(id));
            self.l38.fills.retain(|_, f| f.at.elapsed() < FILL_KEEP);
        }
        if slot_now >= self.l38.saved + CR_SAVE_SLOTS {
            if self.l38.saved > 0 {
                if let Some(p) = self.cfg.family_state.clone() {
                    let m = { let mut g = self.l38.fl.lock().unwrap(); let n = g.newest(); g.prune(n); g.clone() };
                    std::thread::spawn(move || { if let Err(e) = led_save(&m, &p, "family") { eprintln!("DIP PRESEND LIVE FAMILY LEDGER: NOT saved to {p}: {e:#}"); } });
                }
                if let Some(p) = self.cfg.shape_state.clone() {
                    let m = { let mut g = self.l38.sl.lock().unwrap(); let n = g.newest(); g.prune(n); g.clone() };
                    std::thread::spawn(move || { if let Err(e) = led_save(&m, &p, "shape") { eprintln!("DIP PRESEND LIVE SHAPE LEDGER: NOT saved to {p}: {e:#}"); } });
                }
            }
            self.l38.saved = slot_now;
        }
    }

    /// the status part ("" with the logs off)
    pub(super) fn l38_status(&self) -> String {
        if !self.l38_on() { return String::new(); }
        let s = &self.l38.st;
        let a = |x: &[u64; 3]| format!("{}/{}/{}", x[0], x[1], x[2]);
        let mut o = String::from(" | DIP38 LOG arm/send/fill:");
        if self.cfg.insider_log {
            let f = &self.l38.fsh;
            o += &format!(" insider {} family {} family-ledger would {} | fund cached {} (ok {} deep {} fail {} this run), pending {}, asked {}, dropped {}, rpc calls {} (429 {}), last {} ms{} | launchers {}",
                a(&s.ins), a(&s.fam), a(&s.flw), self.l38.chains.len(), s.ok, s.deep, s.fail, self.l38.pending.len(), s.asked, s.dropped, f.calls.load(Ordering::Relaxed),
                f.r429.load(Ordering::Relaxed), f.last_ms.load(Ordering::Relaxed), if f.busy.load(Ordering::Relaxed) { " (busy)" } else { "" }, self.l38.launch.len());
        }
        if self.cfg.shape_log { o += &format!(" | shape would {}", a(&s.shw)); }
        o
    }

    /// the run's end: the resolver stopped, the chains and the ledgers saved; run_end "dip38_log" (None with the logs off)
    pub(super) fn l38_finish(&mut self) -> Option<serde_json::Value> {
        if !self.l38_on() { return None; }
        self.l38.fsh.stop.store(true, Ordering::SeqCst);
        self.l38.tx = None;
        let mut saved = serde_json::json!({});
        if let Some(p) = self.cfg.fund_state.clone() {
            match psfund::fund_save(&self.l38.chains, &p, "m") {
                Ok(n) => { self.line(format!("  PRESEND LIVE FUND STATE: {n} chains saved to {p}")); saved["fund"] = n.into(); }
                Err(e) => self.line(format!("  PRESEND LIVE FUND STATE: NOT saved to {p}: {e:#}")),
            }
        }
        for (p, kind) in [(self.cfg.family_state.clone(), "family"), (self.cfg.shape_state.clone(), "shape")] {
            let Some(p) = p else { continue };
            let r = if kind == "family" { let mut g = self.l38.fl.lock().unwrap(); let n = g.newest(); g.prune(n); led_save(&g, &p, kind) }
                else { let mut g = self.l38.sl.lock().unwrap(); let n = g.newest(); g.prune(n); led_save(&g, &p, kind) };
            match r {
                Ok(n) => { self.line(format!("  PRESEND LIVE {} LEDGER: {n} keys saved to {p}", kind.to_uppercase())); saved[kind] = n.into(); }
                Err(e) => self.line(format!("  PRESEND LIVE {} LEDGER: NOT saved to {p}: {e:#}", kind.to_uppercase())),
            }
        }
        let s = &self.l38.st;
        let mut v = s.lags.clone();
        v.sort_by(|a, b| a.total_cmp(b));
        let f = &self.l38.fsh;
        Some(serde_json::json!({"insider_log": self.cfg.insider_log, "shape_log": self.cfg.shape_log, "arms": s.arms, "sends": s.sends, "fills": s.fills,
            "insider": s.ins, "family": s.fam, "family_would": s.flw, "shape_would": s.shw, "asked": s.asked, "dropped": s.dropped, "resolved": {"ok": s.ok, "deep": s.deep, "fail": s.fail},
            "loaded": s.loaded, "cached": self.l38.chains.len(), "pending": self.l38.pending.len(), "rpc_calls": f.calls.load(Ordering::Relaxed), "rpc_429": f.r429.load(Ordering::Relaxed),
            "resolve_ms_p50": (!v.is_empty()).then(|| v[v.len() / 2]), "learned": {"family": self.l38.lrn.fl.load(Ordering::Relaxed), "shape": self.l38.lrn.sh.load(Ordering::Relaxed),
            "realized": self.l38.lrn.rz.load(Ordering::Relaxed)}, "family_keys": self.l38.fl.lock().unwrap().m.len(), "shape_keys": self.l38.sl.lock().unwrap().m.len(), "saved": saved}))
    }
}
