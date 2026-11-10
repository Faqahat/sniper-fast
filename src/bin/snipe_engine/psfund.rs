// =====================================================================================================================
// dip38 FUNDING RESOLVER (LOG-ONLY; owner "build dip38" 11-05; /home/it/sniper-data/antibait/REPORT.txt §4 and §7b; the Python
// reference /home/it/sniper-studies/sniper-antibait/resolve.py + rpc.py). Behind --presend-live-insider-log on: off = nothing of it exists (no
// thread, no client, no file). NEVER on the hot path: its own thread "ps-fund" (nice 19, its own single-thread runtime) fed through a
// BOUNDED queue (FUND_QUEUE; try_send: full = the wallet is dropped and counted, asked again at its next sight); the decision / send
// path never waits for it.
//   * a wallet -> its first FUND_FIRST_K successful txs (its history start must be reached within FUND_PAGES pages of 1,000
//     signatures, else "deep": a busy wallet public RPC cannot trace) -> every incoming SOL transfer >= 0.05 SOL in them (system
//     transfer / transferWithSeed to it, createAccount(WithSeed) of it; outer and inner instructions) -> each funder walked: its kind
//     (first page: <= 5 txs = "oneshot" pass-through, >= 1,000 txs inside 2 days = "hub", else "normal"); a pass-through's own first
//     funder is followed (its first FUND_PASS_K txs) up to FUND_HOPS hops. EVERY address walked is kept in the chain with its kind and
//     hop (hubs too: the walk stops there, the address stays: the token's own launcher often looks like a hub, REPORT §4a)
//   * the chain: {st ok | deep | fail, n = signatures read, t = unix s, chain = [[address, kind, hop], ...] in walk order}
//   * rate: every RPC call waits for its slot (--presend-live-fund-rps N per second, default FUND_RPS); a 429 / timeout is retried
//     with a doubling backoff (FUND_TRIES in all); the client is its own endpoint "fund" (its own bucket, never the exit path's)
//   * state: --presend-live-fund-state FILE = {"v": 1, "saved": unix s, "w": {wallet: {st, n, t, chain}}} (ok / deep only), read at the
//     start, written by the task every FUND_SAVE when it learned something (FILE.tmp + rename) and by the run's end; re-read when
//     another writer changed it (mtime checked every FUND_CHECK; new / newer entries are merged and sent to the event loop). Seed:
//     ops/strategies/presend/antibait/fund_seed.py (the study's resolve_*.json)
// =====================================================================================================================
use super::*;
use std::future::Future;

/// the queue between the event loop and the task (a full queue drops the wallet: asked again at its next sight)
pub const FUND_QUEUE: usize = 512;
/// the wallet's first txs read for its incoming SOL (the study: the 2nd / 3rd transfer often carries the link, REPORT §4a)
pub const FUND_FIRST_K: usize = 4;
/// a pass-through funder's first txs read for its own funder
pub const FUND_PASS_K: usize = 3;
/// a pass-through ("oneshot") wallet has at most this many txs ever
pub const FUND_ONESHOT: usize = 5;
/// pass-through hops followed at most
pub const FUND_HOPS: u8 = 3;
/// an incoming transfer smaller than this is not a funding (lamports; 0.05 SOL)
pub const FUND_MIN: u64 = 50_000_000;
/// the wallet's history read at most (pages of 1,000 signatures); its start not reached = "deep"
pub const FUND_PAGES: usize = 2;
/// a "hub": a full first page (1,000 txs) spanning less than this (s)
pub const HUB_SPAN_S: i64 = 2 * 86_400;
/// RPC calls per second (default)
pub const FUND_RPS: f64 = 3.0;
/// the public endpoint (default)
pub const FUND_RPC: &str = "https://api.mainnet-beta.solana.com";
/// one call's budget, its tries
pub const FUND_TIMEOUT: Duration = Duration::from_secs(20);
pub const FUND_TRIES: u32 = 5;
/// a failed wallet is asked again after this long (s); a deep one after FUND_DEEP_RETRY_S
pub const FUND_RETRY_S: u64 = 1_800;
pub const FUND_DEEP_RETRY_S: u64 = 86_400;
/// the task's state save period (when it learned something) and its reload check
pub const FUND_SAVE: Duration = Duration::from_secs(60);
pub const FUND_CHECK: Duration = Duration::from_secs(10);
/// the funder-kind cache's size cap (cleared beyond)
const KIND_MAX: usize = 200_000;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind { Hub, Oneshot, Normal }
impl Kind {
    pub fn s(self) -> &'static str { match self { Kind::Hub => "hub", Kind::Oneshot => "oneshot", Kind::Normal => "normal" } }
    pub fn parse(s: &str) -> Option<Kind> { match s { "hub" => Some(Kind::Hub), "oneshot" => Some(Kind::Oneshot), "normal" => Some(Kind::Normal), _ => None } }
    /// a first page of signatures (newest first): <= 5 = oneshot, a full page spanning < 2 days = hub, else normal (resolve.py kind())
    pub fn of(page: &[SigI]) -> Kind {
        if page.len() <= FUND_ONESHOT { return Kind::Oneshot; }
        let span = match (page.first().and_then(|s| s.bt), page.last().and_then(|s| s.bt)) { (Some(a), Some(b)) if page.len() > 1 => Some(a - b), _ => None };
        if page.len() >= 1000 && span.is_some_and(|s| s < HUB_SPAN_S) { Kind::Hub } else { Kind::Normal }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FSt { Ok, Deep, Fail }
impl FSt {
    pub fn s(self) -> &'static str { match self { FSt::Ok => "ok", FSt::Deep => "deep", FSt::Fail => "fail" } }
}

/// one address of a funding walk: its kind and its hop (0 = a direct funder of the wallet)
#[derive(Clone, Debug, PartialEq)]
pub struct Link { pub a: Pk, pub kind: Kind, pub hops: u8 }

/// a wallet's funding chain
#[derive(Clone, Debug, PartialEq)]
pub struct Chain { pub st: FSt, pub n: u32, pub t: u64, pub links: Vec<Link>, pub err: Option<String> }

fn short(k: &Pk) -> String { b58(k).chars().take(8).collect() }

impl Chain {
    /// the first link that is `k` (None: not in the chain)
    pub fn find(&self, k: &Pk) -> Option<usize> { self.links.iter().position(|l| l.a == *k) }
    /// the walk that reached link `i`: its hop-0 funder .. i
    pub fn walk(&self, i: usize) -> &[Link] {
        let mut s = i.min(self.links.len().saturating_sub(1));
        while s > 0 && self.links[s].hops > 0 { s -= 1; }
        &self.links[s..=i]
    }
    /// "WALLET8<-FUNDER8<-...<-LINK8" (prefixes)
    pub fn summary(&self, w: &Pk, i: usize) -> String {
        let mut s = short(w);
        for l in self.walk(i) { s.push_str("<-"); s.push_str(&short(&l.a)); }
        s
    }
    pub fn json(&self) -> serde_json::Value {
        let mut j = serde_json::json!({"st": self.st.s(), "n": self.n, "t": self.t,
            "chain": self.links.iter().map(|l| serde_json::json!([b58(&l.a), l.kind.s(), l.hops])).collect::<Vec<_>>()});
        if let Some(e) = &self.err { j["err"] = e.clone().into(); }
        j
    }
    /// a state-file entry (also the study's resolve_*.json shape after fund_seed.py); None: unreadable
    pub fn from_json(v: &serde_json::Value) -> Option<Chain> {
        let st = match v["st"].as_str()? { "ok" => FSt::Ok, "deep" => FSt::Deep, "fail" => FSt::Fail, _ => return None };
        let mut links = Vec::new();
        for l in v["chain"].as_array().map(|a| a.as_slice()).unwrap_or(&[]) {
            let a: Pk = bs58::decode(l[0].as_str()?).into_vec().ok()?.try_into().ok()?;
            links.push(Link { a, kind: Kind::parse(l[1].as_str()?)?, hops: l[2].as_u64()?.min(255) as u8 });
        }
        Some(Chain { st, n: v["n"].as_u64().unwrap_or(0) as u32, t: v["t"].as_u64().unwrap_or(0), links, err: v["err"].as_str().map(String::from) })
    }
    /// asked again now (`now` unix s): a failure after FUND_RETRY_S, a deep one after FUND_DEEP_RETRY_S, an ok one never
    pub fn stale(&self, now: u64) -> bool {
        match self.st { FSt::Ok => false, FSt::Fail => now >= self.t + FUND_RETRY_S, FSt::Deep => now >= self.t + FUND_DEEP_RETRY_S }
    }
}

/// one signature of getSignaturesForAddress (newest first)
#[derive(Clone, Debug, PartialEq)]
pub struct SigI { pub sig: String, pub slot: u64, pub bt: Option<i64>, pub ok: bool }

pub fn sigs_parse(v: &serde_json::Value) -> std::result::Result<Vec<SigI>, String> {
    let a = v.as_array().ok_or("getSignaturesForAddress: not a list")?;
    a.iter().map(|s| Ok(SigI { sig: s["signature"].as_str().ok_or("no signature")?.to_string(), slot: s["slot"].as_u64().unwrap_or(0), bt: s["blockTime"].as_i64(),
        ok: s["err"].is_null() })).collect()
}

/// the incoming SOL transfers to `addr` in a jsonParsed getTransaction result: (source, lamports), outer then inner instructions (rpc.py sol_in)
pub fn sol_in(tx: &serde_json::Value, addr: &str) -> Vec<(Pk, u64)> {
    let mut out = Vec::new();
    if tx.is_null() { return out; }
    let mut ixs: Vec<&serde_json::Value> = tx["transaction"]["message"]["instructions"].as_array().map(|a| a.iter().collect()).unwrap_or_default();
    for g in tx["meta"]["innerInstructions"].as_array().map(|a| a.as_slice()).unwrap_or(&[]) {
        if let Some(a) = g["instructions"].as_array() { ixs.extend(a.iter()); }
    }
    for ix in ixs {
        let p = &ix["parsed"];
        if !p.is_object() { continue; }
        let info = &p["info"];
        let src = info["source"].as_str().and_then(|s| bs58::decode(s).into_vec().ok()).and_then(|v| <Pk>::try_from(v).ok());
        match p["type"].as_str() {
            Some("transfer" | "transferWithSeed") if info["destination"].as_str() == Some(addr) => {
                if let (Some(s), Some(l)) = (src, info["lamports"].as_u64()) { out.push((s, l)); }
            }
            Some("createAccount" | "createAccountWithSeed") if info["newAccount"].as_str() == Some(addr) => {
                if let Some(s) = src { out.push((s, info["lamports"].as_u64().unwrap_or(0))); }
            }
            _ => {}
        }
    }
    out
}

/// where the resolver reads the chain (the RPC; a test's tape)
pub trait FundSrc: Send + Sync {
    /// one page of getSignaturesForAddress (1,000 at most, newest first), before `before`
    fn sigs(&self, a: &Pk, before: Option<String>) -> impl Future<Output = std::result::Result<Vec<SigI>, String>> + Send;
    /// a jsonParsed getTransaction result (null: not found)
    fn tx(&self, sig: &str) -> impl Future<Output = std::result::Result<serde_json::Value, String>> + Send;
}

/// the walk (resolve.py resolve()) with the funder kinds cached across wallets
pub struct Resolver<S: FundSrc> { pub src: S, kinds: FxHashMap<Pk, Kind>, ones: FxHashMap<Pk, Vec<SigI>>, pub calls: u64 }

impl<S: FundSrc> Resolver<S> {
    pub fn new(src: S) -> Resolver<S> { Resolver { src, kinds: FxHashMap::default(), ones: FxHashMap::default(), calls: 0 } }

    /// up to `pages` pages of `a`'s signatures; true: its history start was reached
    async fn hist(&mut self, a: &Pk, pages: usize) -> std::result::Result<(Vec<SigI>, bool), String> {
        let (mut out, mut before) = (Vec::new(), None);
        for _ in 0..pages {
            self.calls += 1;
            let p = self.src.sigs(a, before.clone()).await?;
            let n = p.len();
            before = p.last().map(|s| s.sig.clone());
            out.extend(p);
            if n < 1000 { return Ok((out, true)); }
        }
        Ok((out, false))
    }

    /// a funder's kind (its first page; cached)
    async fn kind(&mut self, a: &Pk) -> std::result::Result<Kind, String> {
        if let Some(k) = self.kinds.get(a) { return Ok(*k); }
        let (p, _) = self.hist(a, 1).await?;
        let k = Kind::of(&p);
        if self.kinds.len() >= KIND_MAX { self.kinds.clear(); self.ones.clear(); }
        self.kinds.insert(*a, k);
        if k == Kind::Oneshot { self.ones.insert(*a, p); }
        Ok(k)
    }

    /// the incoming SOL of `a`'s oldest `k` successful txs of `h` (newest first)
    async fn first_in(&mut self, a: &Pk, h: &[SigI], k: usize) -> std::result::Result<Vec<(Pk, u64)>, String> {
        let me = b58(a);
        let mut out = Vec::new();
        for s in h.iter().rev().filter(|s| s.ok).take(k) {
            self.calls += 1;
            let t = self.src.tx(&s.sig).await?;
            out.extend(sol_in(&t, &me).into_iter().filter(|x| x.0 != *a));
        }
        Ok(out)
    }

    /// the wallet's chain at unix second `now` (an RPC failure = st "fail" with its error)
    pub async fn resolve(&mut self, w: &Pk, now: u64) -> Chain {
        match self.walk(w).await {
            Ok((st, n, links)) => Chain { st, n, t: now, links, err: None },
            Err(e) => Chain { st: FSt::Fail, n: 0, t: now, links: Vec::new(), err: Some(e.chars().take(200).collect()) },
        }
    }

    async fn walk(&mut self, w: &Pk) -> std::result::Result<(FSt, u32, Vec<Link>), String> {
        let (h, done) = self.hist(w, FUND_PAGES).await?;
        if !done { return Ok((FSt::Deep, h.len() as u32, Vec::new())); }
        let f = self.first_in(w, &h, FUND_FIRST_K).await?;
        let mut links = Vec::new();
        for (src, lam) in f {
            if lam < FUND_MIN { continue; }
            let (mut cur, mut hops) = (src, 0u8);
            loop {
                let k = self.kind(&cur).await?;
                links.push(Link { a: cur, kind: k, hops });
                if k != Kind::Oneshot || hops >= FUND_HOPS { break; }
                let page = match self.ones.get(&cur) { Some(p) => p.clone(), None => self.hist(&cur, 1).await?.0 };
                let ff: Vec<(Pk, u64)> = self.first_in(&cur, &page, FUND_PASS_K).await?.into_iter().filter(|x| x.1 >= FUND_MIN).collect();
                let Some(nx) = ff.first() else { break };
                if nx.0 == *w || nx.0 == cur { break; }
                cur = nx.0;
                hops += 1;
            }
        }
        Ok((FSt::Ok, h.len() as u32, links))
    }
}

/// the real source: the "fund" RPC endpoint, paced to `gap` between calls (all of the task's calls), 429 / timeouts retried
pub struct RpcSrc { rpc: rpc::Rpc, gap: Duration, next: std::sync::Mutex<Instant>, pub sh: Arc<FundShared> }

impl RpcSrc {
    pub fn new(url: String, rps: f64, sh: Arc<FundShared>) -> RpcSrc {
        RpcSrc { rpc: rpc::Rpc::race(vec![rpc::Endpoint { name: "fund".into(), url, bearer: None }]), gap: Duration::from_secs_f64(1.0 / rps.max(0.01)),
            next: std::sync::Mutex::new(Instant::now()), sh }
    }
    async fn pace(&self) {
        let wait = {
            let mut n = self.next.lock().unwrap();
            let now = Instant::now();
            let at = (*n).max(now);
            *n = at + self.gap;
            at - now
        };
        if !wait.is_zero() { tokio::time::sleep(wait).await; }
    }
    async fn call(&self, m: &str, p: serde_json::Value) -> std::result::Result<serde_json::Value, String> {
        let mut back = Duration::from_secs(2);
        for i in 0..FUND_TRIES {
            self.pace().await;
            self.sh.calls.fetch_add(1, Ordering::Relaxed);
            match self.rpc.call_bounded(m, p.clone(), rpc::Bounds::fetch(FUND_TIMEOUT, 0)).await {
                Ok(f) => return Ok(f.value),
                Err(e) if i + 1 < FUND_TRIES && matches!(e.class, rpc::ErrClass::RateLimited | rpc::ErrClass::Timeout | rpc::ErrClass::Http | rpc::ErrClass::Transport | rpc::ErrClass::Body | rpc::ErrClass::Budget | rpc::ErrClass::NoResult) => {
                    if e.class == rpc::ErrClass::RateLimited { self.sh.r429.fetch_add(1, Ordering::Relaxed); }
                    tokio::time::sleep(back).await;
                    back = (back * 2).min(Duration::from_secs(30));
                }
                Err(e) => return Err(format!("{m}: {}", rpc::scrub(&e.msg))),
            }
        }
        Err(format!("{m}: retries spent"))
    }
}

impl FundSrc for RpcSrc {
    fn sigs(&self, a: &Pk, before: Option<String>) -> impl Future<Output = std::result::Result<Vec<SigI>, String>> + Send {
        let mut o = serde_json::json!({"limit": 1000, "commitment": "confirmed"});
        if let Some(b) = before { o["before"] = b.into(); }
        let p = serde_json::json!([b58(a), o]);
        async move { sigs_parse(&self.call("getSignaturesForAddress", p).await?) }
    }
    fn tx(&self, sig: &str) -> impl Future<Output = std::result::Result<serde_json::Value, String>> + Send {
        let p = serde_json::json!([sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}]);
        async move { self.call("getTransaction", p).await }
    }
}

/// the task's counters (the event loop's status line reads them)
#[derive(Default)]
pub struct FundShared {
    pub calls: AtomicU64, pub r429: AtomicU64, pub resolved: AtomicU64, pub busy: AtomicBool, pub stop: AtomicBool,
    pub saves: AtomicU64, pub save_errs: AtomicU64, pub reloads: AtomicU64, pub reload_errs: AtomicU64, pub last_ms: AtomicU64,
}

/// what the task sends back to the event loop
#[derive(Debug)]
pub enum FundOut {
    /// a wallet resolved: its chain, the ms it took, the RPC calls it made
    Done(Pk, Arc<Chain>, f64, u64),
    /// another writer changed the state file: its new / newer entries
    Loaded(Vec<(Pk, Arc<Chain>)>, String),
}

pub type Chains = FxHashMap<Pk, Arc<Chain>>;

/// the state file -> its chains (ok / deep / fail entries as written)
pub fn fund_parse(b: &[u8]) -> Result<Chains> {
    let v: serde_json::Value = serde_json::from_slice(b).context("parse")?;
    let mut m = FxHashMap::default();
    for (w, c) in v["w"].as_object().context("no \"w\" object")? {
        let Some(k) = bs58::decode(w).into_vec().ok().and_then(|x| <Pk>::try_from(x).ok()) else { bail!("bad wallet {w}") };
        let Some(c) = Chain::from_json(c) else { bail!("{w}: not a chain entry") };
        m.insert(k, Arc::new(c));
    }
    Ok(m)
}
pub fn fund_load(path: &str) -> Result<Chains> { fund_parse(&std::fs::read(path).with_context(|| format!("read {path}"))?).with_context(|| path.to_string()) }
/// written as PATH.tmp<tag> then renamed (ok / deep only: failures are asked again); -> entries written
pub fn fund_save(m: &Chains, path: &str, tag: &str) -> Result<usize> {
    let w: serde_json::Map<String, serde_json::Value> = m.iter().filter(|(_, c)| c.st != FSt::Fail).map(|(k, c)| (b58(k), c.json())).collect();
    let n = w.len();
    let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    let tmp = format!("{path}.tmp{tag}");
    std::fs::write(&tmp, serde_json::json!({"v": 1, "saved": now, "w": w}).to_string()).with_context(|| format!("write {tmp}"))?;
    std::fs::rename(&tmp, path).with_context(|| format!("rename {tmp}"))?;
    Ok(n)
}
fn mtime(p: &str) -> Option<std::time::SystemTime> { std::fs::metadata(p).and_then(|m| m.modified()).ok() }
pub fn unix_s() -> u64 { std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0) }

/// start the resolver on its OWN thread ("ps-fund", the lowest CPU priority, its own single-thread runtime: never a worker of the engine's
/// runtimes): wallets from `rx`, answers through `send`, the state file kept (when given). Its end: `sh.stop` or the queue closed
pub fn spawn(url: String, rps: f64, state: Option<String>, seed: Chains, rx: tokio::sync::mpsc::Receiver<Pk>, send: Box<dyn Fn(FundOut) + Send + Sync>, sh: Arc<FundShared>) -> Result<()> {
    std::thread::Builder::new().name("ps-fund".into()).spawn(move || {
        unsafe {
            let tid = libc::syscall(libc::SYS_gettid);
            libc::setpriority(libc::PRIO_PROCESS, tid as libc::id_t, 19);
        }
        let rt = match tokio::runtime::Builder::new_current_thread().enable_all().build() {
            Ok(rt) => rt,
            Err(e) => { eprintln!("DIP PRESEND LIVE FUND RESOLVER: no runtime ({e}): not started"); return; }
        };
        rt.block_on(worker(url, rps, state, seed, rx, send, sh));
    }).context("ps-fund thread")?;
    Ok(())
}

async fn worker(url: String, rps: f64, state: Option<String>, seed: Chains, mut rx: tokio::sync::mpsc::Receiver<Pk>, send: Box<dyn Fn(FundOut) + Send + Sync>, sh: Arc<FundShared>) {
    let mut res = Resolver::new(RpcSrc::new(url, rps, sh.clone()));
    let mut cache = seed;
    let (mut dirty, mut last_save, mut last_chk) = (false, Instant::now(), Instant::now());
    let mut known = state.as_deref().and_then(mtime);
    loop {
        if sh.stop.load(Ordering::SeqCst) { break; }
        match tokio::time::timeout(FUND_CHECK, rx.recv()).await {
            Ok(Some(w)) => {
                if sh.stop.load(Ordering::SeqCst) { break; }
                sh.busy.store(true, Ordering::SeqCst);
                let (t0, c0) = (Instant::now(), res.calls);
                let c = Arc::new(res.resolve(&w, unix_s()).await);
                let ms = t0.elapsed().as_secs_f64() * 1e3;
                sh.last_ms.store(ms as u64, Ordering::Relaxed);
                sh.resolved.fetch_add(1, Ordering::Relaxed);
                if c.st != FSt::Fail { dirty = true; }
                cache.insert(w, c.clone());
                sh.busy.store(false, Ordering::SeqCst);
                send(FundOut::Done(w, c, ms, res.calls - c0));
            }
            Ok(None) => break,
            Err(_) => {}
        }
        let Some(p) = state.as_deref() else { continue };
        // its own thread: the file work blocks nobody
        if dirty && last_save.elapsed() >= FUND_SAVE && !sh.stop.load(Ordering::SeqCst) {
            match fund_save(&cache, p, "w") {
                Ok(_) => { sh.saves.fetch_add(1, Ordering::Relaxed); known = mtime(p); dirty = false; }
                Err(_) => { sh.save_errs.fetch_add(1, Ordering::Relaxed); }
            }
            last_save = Instant::now();
        }
        if last_chk.elapsed() >= FUND_CHECK {
            last_chk = Instant::now();
            let mt = mtime(p);
            if mt.is_some() && mt != known {
                known = mt;
                match fund_load(p) {
                    Ok(m) => {
                        let mut new = Vec::new();
                        for (k, c) in m {
                            if cache.get(&k).is_none_or(|o| c.t > o.t || (o.st == FSt::Fail && c.st != FSt::Fail)) { cache.insert(k, c.clone()); new.push((k, c)); }
                        }
                        sh.reloads.fetch_add(1, Ordering::Relaxed);
                        send(FundOut::Loaded(new, p.to_string()));
                    }
                    Err(e) => { sh.reload_errs.fetch_add(1, Ordering::Relaxed); send(FundOut::Loaded(Vec::new(), format!("{p}: NOT reloaded: {e:#}"))); }
                }
            }
        }
    }
}
