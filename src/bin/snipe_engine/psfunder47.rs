// =====================================================================================================================
// dip47 FUNDER-CLUSTER LOG (LOG ONLY: never blocks, withholds or changes a decision; --presend-live-funder-log on, default off).
// Why: r83 H2d2DtyD: 17 wallets held 44% at our send, each funded 0-2 slots before its own buy in a tx paid by BufYjmzE; FAM (create-slot
// buyers + transfer recipients) read 18.9%. Definition (the fix8283 study's lastfund2.py / features.py, reproduced by the offline test):
//   a holder's FUNDER = the fee payer (first signer) of the transaction right before its FIRST buy of the mint
//   (getSignaturesForAddress(wallet, before = that buy's signature) -> its newest entry -> getTransaction), when the payer is another
//   wallet and the holder's SOL balance rose by >= 0.05 SOL in it. "just funded" = that tx <= 3 slots before the buy.
//   CLUSTER = the holders >= 0.5% of supply (ours out) sharing one funder; its share = their holdings summed.
// How: the main loop notes every wallet's first buy signature per followed token and, when a holder reaches >= 0.5%, pushes ONE lookup
// to a bounded queue (QUEUE_MAX; full: the OLDEST is dropped, counted). WORKERS threads "ps-funder" (nice 19, their own runtimes), paced
// together to --presend-live-funder-rps (15; max 40), do the 2 RPC calls and send the result back; the main loop keeps a bounded cache
// per wallet (CACHE_MAX, oldest out). The main loop never waits: an arm / fill reports what is resolved by then (resolved / pending).
// RPC: --presend-live-funder-rpc URL (`${VAR}` expanded) or the FAM log's (--presend-live-fam-rpc / rpc_url). The URL is never printed
// or recorded (errors go through rpc::scrub).
// Records: "presend_live_funder" {w, mint, kind, at (arm | fill), slot, n, pct, resolved, pending, c1 {funder, n_wallets, pct}, c2,
// just_funded_pct, lag_ms {mean, max}}; presend_live_fill gets "funder" {pct, n, resolved}; one line per window at its arm.
// =====================================================================================================================
use super::*;

pub const MIN_FRAC: f64 = 0.005;
pub const FUND_MIN: i64 = 50_000_000;
pub const JUST_SLOTS: u64 = 3;
pub const QUEUE_MAX: usize = 4096;
pub const CACHE_MAX: usize = 50_000;
pub const FIRST_MAX: usize = 300_000;
pub const WORKERS: usize = 4;
const TIMEOUT: Duration = Duration::from_secs(8);

/// a blocking RPC call (the worker's client; the tests' fixture)
pub type Src<'a> = dyn Fn(&str, serde_json::Value) -> std::result::Result<serde_json::Value, String> + 'a;

#[derive(Clone, Debug)]
pub struct Job { pub w: Pk, pub mint: Pk, pub sig: [u8; 64], pub slot: u64, pub t0: Instant }

/// a wallet's lookup: its first buy (mint, slot), the tx before it (slot; 0 = none: a fresh wallet), its funder, the SOL it got
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Res { pub mint: Pk, pub buy_slot: u64, pub prev_slot: u64, pub funder: Option<Pk>, pub lamports: i64, pub lag_ms: f32, pub ok: bool }

/// the newest entry of getSignaturesForAddress's answer: (signature, slot). None: no earlier tx
pub fn parse_prev(sigs: &serde_json::Value) -> std::result::Result<Option<(String, u64)>, String> {
    let a = sigs.as_array().ok_or("signatures: not a list")?;
    Ok(a.first().and_then(|x| Some((x["signature"].as_str()?.to_string(), x["slot"].as_u64().unwrap_or(0)))))
}
/// a jsonParsed transaction: (fee payer = first signer, the wallet's SOL change in lamports)
pub fn parse_tx(tx: &serde_json::Value, w: &str) -> std::result::Result<(Option<Pk>, i64), String> {
    let ks = tx["transaction"]["message"]["accountKeys"].as_array().ok_or("transaction: no account keys")?;
    let key = |k: &serde_json::Value| -> Option<String> { k["pubkey"].as_str().or_else(|| k.as_str()).map(str::to_string) };
    let payer = ks.iter().find(|k| k["signer"].as_bool().unwrap_or(false)).or(ks.first()).and_then(key)
        .and_then(|s| bs58::decode(s).into_vec().ok()).and_then(|v| <[u8; 32]>::try_from(v).ok());
    let d = ks.iter().position(|k| key(k).as_deref() == Some(w)).map_or(0, |i| {
        tx["meta"]["postBalances"][i].as_i64().unwrap_or(0) - tx["meta"]["preBalances"][i].as_i64().unwrap_or(0)
    });
    Ok((payer, d))
}
/// the two calls of one lookup
pub fn lookup(src: &Src, j: &Job) -> std::result::Result<Res, String> {
    let w = b58(&j.w);
    let sigs = src("getSignaturesForAddress", serde_json::json!([w, {"before": bs58::encode(&j.sig).into_string(), "limit": 8, "commitment": "confirmed"}]))?;
    let base = Res { mint: j.mint, buy_slot: j.slot, prev_slot: 0, funder: None, lamports: 0, lag_ms: 0.0, ok: true };
    let Some((psig, pslot)) = parse_prev(&sigs)? else { return Ok(base) };
    let tx = src("getTransaction", serde_json::json!([psig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}]))?;
    if tx.is_null() { return Err("getTransaction: null".into()); }
    let (payer, d) = parse_tx(&tx, &w)?;
    let funder = payer.filter(|p| *p != j.w && d >= FUND_MIN);
    Ok(Res { prev_slot: pslot, funder, lamports: d, ..base })
}

/// one cluster: (funder, wallets, % of supply)
pub type Cl = (Pk, u32, f64);
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Summary { pub n: u32, pub pct: f64, pub resolved: u32, pub pending: u32, pub c1: Option<Cl>, pub c2: Option<Cl>, pub just_pct: f64, pub lag_mean: f64, pub lag_max: f64 }

/// the clusters of `holders` ((wallet, raw balance), all >= 0.5%) from the lookups known for this mint
pub fn summarize(mint: &Pk, holders: &[(Pk, i64)], get: impl Fn(&Pk) -> Option<Res>) -> Summary {
    let pc = |b: i64| b as f64 / pl::SUPPLY * 100.0;
    let mut s = Summary { n: holders.len() as u32, pct: holders.iter().map(|h| pc(h.1)).sum(), ..Default::default() };
    let mut by: Vec<Cl> = Vec::new();
    let mut lags = 0.0f64;
    for (w, b) in holders {
        let Some(r) = get(w).filter(|r| r.ok && r.mint == *mint) else { s.pending += 1; continue };
        s.resolved += 1;
        lags += r.lag_ms as f64; s.lag_max = s.lag_max.max(r.lag_ms as f64);
        let Some(f) = r.funder else { continue };
        if r.buy_slot.saturating_sub(r.prev_slot) <= JUST_SLOTS { s.just_pct += pc(*b); }
        match by.iter_mut().find(|c| c.0 == f) { Some(c) => { c.1 += 1; c.2 += pc(*b); } None => by.push((f, 1, pc(*b))) }
    }
    if s.resolved > 0 { s.lag_mean = lags / s.resolved as f64; }
    by.sort_by(|a, b| b.2.partial_cmp(&a.2).unwrap_or(std::cmp::Ordering::Equal).then(a.0.cmp(&b.0)));
    s.c1 = by.first().copied();
    s.c2 = by.get(1).copied();
    s
}
fn r3(x: f64) -> f64 { (x * 1e3).round() / 1e3 }
impl Summary {
    fn cl(c: &Option<Cl>) -> serde_json::Value { c.map_or(serde_json::Value::Null, |(f, n, p)| serde_json::json!({"funder": b58(&f), "n_wallets": n, "pct": r3(p)})) }
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"n": self.n, "pct": r3(self.pct), "resolved": self.resolved, "pending": self.pending, "c1": Self::cl(&self.c1), "c2": Self::cl(&self.c2),
            "just_funded_pct": r3(self.just_pct), "lag_ms": {"mean": self.lag_mean.round(), "max": self.lag_max.round()}})
    }
}

#[derive(Default)]
pub struct FuSh { pub q: Mutex<VecDeque<Job>>, pub stop: AtomicBool, pub calls: AtomicU64, pub errs: AtomicU64, pub drops: AtomicU64, pub done: AtomicU64, next: Mutex<Option<Instant>> }

pub struct Funder {
    pub sh: Arc<FuSh>,
    rx: crossbeam_channel::Receiver<(Pk, Res)>,
    tx: crossbeam_channel::Sender<(Pk, Res)>,
    /// (mint, wallet) -> its first buy (signature, slot)
    first: FxHashMap<(Pk, Pk), ([u8; 64], u64)>,
    /// wallet -> the mint its lookup was asked for
    asked: FxHashMap<Pk, Pk>,
    pub cache: FxHashMap<Pk, Res>,
    cache_q: VecDeque<Pk>,
    lined: FxHashSet<u64>,
    pub queued: u64, pub events: u64,
}

/// one job: paced, looked up, sent back (a failed lookup: counted, the wallet may be asked again)
pub fn work(sh: &FuSh, src: &Src, gap: Duration, tx: &crossbeam_channel::Sender<(Pk, Res)>) -> bool {
    let Some(j) = sh.q.lock().unwrap().pop_front() else { return false };
    let counted = |m: &str, p: serde_json::Value| {
        let wait = { let mut n = sh.next.lock().unwrap(); let now = Instant::now(); let at = n.map_or(now, |x| x.max(now)); *n = Some(at + gap); at - now };
        if !wait.is_zero() { std::thread::sleep(wait); }
        sh.calls.fetch_add(1, Ordering::Relaxed);
        src(m, p)
    };
    let r = match lookup(&counted, &j) {
        Ok(r) => { sh.done.fetch_add(1, Ordering::Relaxed); Res { lag_ms: j.t0.elapsed().as_secs_f32() * 1e3, ..r } }
        Err(_) => { sh.errs.fetch_add(1, Ordering::Relaxed); Res { mint: j.mint, buy_slot: j.slot, prev_slot: 0, funder: None, lamports: 0, lag_ms: 0.0, ok: false } }
    };
    let _ = tx.send((j.w, r));
    true
}

impl Funder {
    /// no worker (the tests pump the queue themselves)
    pub fn idle() -> Funder {
        let (tx, rx) = crossbeam_channel::unbounded();
        Funder { sh: Arc::new(FuSh::default()), rx, tx, first: FxHashMap::default(), asked: FxHashMap::default(), cache: FxHashMap::default(), cache_q: VecDeque::new(),
            lined: FxHashSet::default(), queued: 0, events: 0 }
    }
    /// the workers on `url` (never printed)
    pub fn start(url: String, rps: u32) -> Funder {
        let f = Funder::idle();
        let gap = Duration::from_secs_f64(1.0 / rps.clamp(1, 40) as f64);
        for i in 0..WORKERS {
            let (sh, tx, url) = (f.sh.clone(), f.tx.clone(), url.clone());
            let _ = std::thread::Builder::new().name(format!("ps-funder-{i}")).spawn(move || {
                unsafe { let tid = libc::syscall(libc::SYS_gettid); libc::setpriority(libc::PRIO_PROCESS, tid as libc::id_t, 19); }
                let Ok(rt) = tokio::runtime::Builder::new_current_thread().enable_all().build() else { return };
                let client = rpc::Rpc::race(vec![rpc::Endpoint { name: "funder".into(), url, bearer: None }]);
                let src = move |m: &str, p: serde_json::Value| rt.block_on(client.call_bounded(m, p, rpc::Bounds::fetch(TIMEOUT, 1))).map(|f| f.value).map_err(|e| rpc::scrub(&e.msg));
                while !sh.stop.load(Ordering::Relaxed) {
                    if !work(&sh, &src, gap, &tx) { std::thread::sleep(Duration::from_millis(5)); }
                }
            });
        }
        f
    }
    /// the tests: every queued job through `src` now
    pub fn pump(&mut self, src: &Src) { while work(&self.sh, src, Duration::ZERO, &self.tx) {} }
    fn drain(&mut self) {
        while let Ok((w, r)) = self.rx.try_recv() {
            if !r.ok { self.asked.remove(&w); continue; }
            if self.cache.insert(w, r).is_none() { self.cache_q.push_back(w); }
            while self.cache_q.len() > CACHE_MAX { if let Some(o) = self.cache_q.pop_front() { self.cache.remove(&o); self.asked.remove(&o); } }
        }
    }
    /// a buy of a followed token (`bal`: the buyer's balance after it): its first buy noted; at >= 0.5% one lookup queued
    pub fn buy(&mut self, mint: Pk, w: Pk, sig: [u8; 64], slot: u64, bal: i64) {
        if self.first.len() >= FIRST_MAX { let lo = slot.saturating_sub(20_000); self.first.retain(|_, v| v.1 >= lo); }
        let (fs, fslot) = *self.first.entry((mint, w)).or_insert((sig, slot));
        if (bal as f64) < MIN_FRAC * pl::SUPPLY || self.asked.get(&w) == Some(&mint) { return; }
        self.asked.insert(w, mint);
        if self.asked.len() > 2 * CACHE_MAX { self.asked.clear(); }
        let mut q = self.sh.q.lock().unwrap();
        if q.len() >= QUEUE_MAX { q.pop_front(); self.sh.drops.fetch_add(1, Ordering::Relaxed); }
        q.push_back(Job { w, mint, sig: fs, slot: fslot, t0: Instant::now() });
        self.queued += 1;
    }
    pub fn status(&self) -> String {
        format!(" | FUNDER LOG queued {} done {} errs {} drops {} calls {} cache {}", self.queued, self.sh.done.load(Ordering::Relaxed), self.sh.errs.load(Ordering::Relaxed),
            self.sh.drops.load(Ordering::Relaxed), self.sh.calls.load(Ordering::Relaxed), self.cache.len())
    }
}
impl Drop for Funder { fn drop(&mut self) { self.sh.stop.store(true, Ordering::Relaxed); } }

impl PsLive {
    /// the funder log's start (None with the flag off / no RPC: said once, never the URL)
    pub(super) fn fu47_open(cfg: &Cfg) -> Option<Funder> {
        if !cfg.funder_log { return None; }
        let url = match cfg.funder_rpc.as_ref().or(cfg.fam_rpc.as_ref()) {
            Some(u) => config::expand(u),
            None => PRIMARY_URL.get().cloned(),
        };
        let src = if cfg.funder_rpc.is_some() { "--presend-live-funder-rpc" } else if cfg.fam_rpc.is_some() { "--presend-live-fam-rpc" } else { "rpc_url" };
        match url {
            Some(u) => {
                eprintln!("DIP47 FUNDER-CLUSTER LOG (LOG ONLY): holders >= 0.5% -> the fee payer of the tx before their first buy (2 RPC calls each, {} per second, RPC {src}), \
                    {WORKERS} background workers, queue {QUEUE_MAX}, cache {CACHE_MAX}", cfg.funder_rps);
                Some(Funder::start(u, cfg.funder_rps))
            }
            None => { eprintln!("DIP47 FUNDER-CLUSTER LOG: no RPC ({src} empty / missing): OFF"); None }
        }
    }
    /// a trade the detector took (main loop; nothing with the log off)
    pub(super) fn fu47_trade(&mut self, t: &pl::Trade) {
        if !t.buy || t.user == self.user || self.fu47.is_none() { return; }
        let bal = self.det.bal(&t.mint, &t.user);
        if let Some(f) = self.fu47.as_mut() { f.buy(t.mint, t.user, t.sig, t.s, bal); }
    }
    /// an arm / a fill of window `w`: the record (and at the arm the window's line) -> the fill record's compact object
    pub(super) fn fu47_event(&mut self, w: u64, mint: &Pk, at: &str, slot: u64) -> Option<serde_json::Value> {
        self.fu47.as_ref()?;
        let holders = self.det.holders_at_least(mint, (MIN_FRAC * pl::SUPPLY) as i64, &self.user).unwrap_or_default();
        let kind = self.g47_kind(w);
        let f = self.fu47.as_mut()?;
        f.drain();
        f.events += 1;
        let s = summarize(mint, &holders, |k| f.cache.get(k).copied());
        let line = at == "arm" && f.lined.insert(w);
        if f.lined.len() > 8192 { f.lined.clear(); }
        let mut r = s.json();
        r["ev"] = "presend_live_funder".into(); r["w"] = w.into(); r["mint"] = b58(mint).into(); r["kind"] = kind.into(); r["at"] = at.into(); r["slot"] = slot.into();
        r["t"] = arbx::feeds::clock::now_ns().into();
        self.rec(r);
        let (cp, cn, cf) = s.c1.map_or((0.0, 0, "none".to_string()), |c| (c.2, c.1, b58(&c.0).chars().take(8).collect::<String>() + "…"));
        if line { self.line(format!("  PRESEND LIVE FUNDER (log) w{w} {}: cluster {:.1}% ({} wallets, funder {}) resolved {}/{}", b58(mint), cp, cn, cf, s.resolved, s.n)); }
        Some(serde_json::json!({"pct": r3(cp), "n": cn, "resolved": s.resolved}))
    }
}
