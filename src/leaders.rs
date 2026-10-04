//! The basic LeaderBook (PLAN WP-03 item 10; MEASUREMENT §4.27): who leads each slot and what kind of leader it is.
//!
//! - **Schedule:** `getSlotLeaders` in 400-slot windows from the current slot, refreshed every 100 slots, on the
//!   background runtime. Each newly learned slot is a leaders.jsonl line; each window also reaches the engine as an
//!   `Event::Input` (`leader_window`), so the journal holds what the send checks will read (WP-05).
//! - **Kind** (`jito`, `bam`, `other`, `unknown`) from three named sources, each recorded with its time (F39):
//!   1. the Jito validators API (`[leaders] validator_lists`, default `https://kobe.mainnet.jito.network/api/v1/validators`:
//!      `{"validators": [{"identity_account", "running_jito", "running_bam", ...}]}`, checked against the 2026-10-03
//!      snapshot `arb-lab/runs-long/kobe.json`: 648 validators, 383 running BAM). Its `running_bam` is the public BAM
//!      list; a validator absent from it runs neither;
//!   2. validator identities seen in our own bundle results (`Accepted` / `Processed` `validator_identity`): they take
//!      Jito bundles. They fill in leaders no list names, and outrank a list that says `other` (the list is older);
//!   3. the dated static fallback `data/validators-meta.json` (built from that snapshot), used while no API list was
//!      fetched (Cherry's address is refused by the API: arb-lab's leaders.py fetched it elsewhere).
//! - `leader(slot)`, `kind(slot)` and `snapshot(slot)` (the struct WP-05 copies into attempts and WP-08 fills further:
//!   region, RTT and client stay null here). send/tpu.rs keeps its own `Book` until WP-08 switches it over.
use crate::config::LeadersCfg;
use crate::feeds::clock::now_ns;
use crate::rec::{Rec, Record, LEADERS};
use crate::tx::{b58, Pk};
use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, RwLock};

/// slots per `getSlotLeaders` window, and how often (in slots) a new window is fetched
pub const WINDOW: u64 = 400;
pub const REFRESH_SLOTS: u64 = 100;
/// schedule entries kept below the current slot
const KEEP_BEHIND: u64 = 2_000;

#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum LeaderKind { Jito, Bam, Other, Unknown }

impl LeaderKind {
    pub fn as_str(self) -> &'static str { match self { LeaderKind::Jito => "jito", LeaderKind::Bam => "bam", LeaderKind::Other => "other", LeaderKind::Unknown => "unknown" } }
}

/// One validator list: where it came from, when it was fetched, and the date it describes (the static file's own date)
struct KindList { src: String, fetched_ns: u64, dated_ns: u64, map: HashMap<Pk, LeaderKind>, is_static: bool }

#[derive(Default)]
struct Inner {
    sched: BTreeMap<u64, Pk>,
    /// the newest API list first, then the static fallback
    lists: Vec<KindList>,
    /// identity -> when our bundle results last named it
    bundle_seen: HashMap<Pk, u64>,
    /// the start of the last window fetched
    last_window: Option<u64>,
}

/// What WP-05 copies into an attempt (`attempts.leader`), MEASUREMENT §4.27's fields
#[derive(Clone, Debug, PartialEq, serde::Serialize)]
pub struct LeaderSnap {
    pub slot: u64,
    pub leader: Option<String>,
    pub kind: LeaderKind,
    pub kind_src: Option<String>,
    pub kind_age_s: Option<u64>,
    pub region: Option<String>,
    pub rtt_ms: Option<f64>,
    pub rtt_age_s: Option<u64>,
    pub rtt_src: Option<String>,
    pub client: Option<String>,
}

pub struct LeaderBook { inner: RwLock<Inner>, rec: Rec }

impl LeaderBook {
    pub fn new(rec: Rec) -> Arc<LeaderBook> { Arc::new(LeaderBook { inner: RwLock::new(Inner::default()), rec }) }

    fn r(&self) -> std::sync::RwLockReadGuard<'_, Inner> { self.inner.read().unwrap_or_else(|e| e.into_inner()) }
    fn w(&self) -> std::sync::RwLockWriteGuard<'_, Inner> { self.inner.write().unwrap_or_else(|e| e.into_inner()) }

    pub fn leader(&self, slot: u64) -> Option<Pk> { self.r().sched.get(&slot).copied() }

    /// a validator's kind, the source that says so and that source's age (s) at `now`
    fn kind_of(inner: &Inner, id: &Pk, now: u64) -> (LeaderKind, Option<String>, Option<u64>) {
        let seen = inner.bundle_seen.get(id).copied();
        let age = |t: u64| Some(now.saturating_sub(t) / 1_000_000_000);
        // the newest list that is not the static fallback, else the static one
        let list = inner.lists.iter().find(|l| !l.is_static).or_else(|| inner.lists.iter().find(|l| l.is_static));
        match (list, seen) {
            (Some(l), seen) => match l.map.get(id).copied().unwrap_or(LeaderKind::Other) {
                LeaderKind::Other if seen.is_some() => (LeaderKind::Jito, Some("bundle_result".into()), seen.and_then(age)),
                k => (k, Some(l.src.clone()), age(l.dated_ns)),
            },
            (None, Some(t)) => (LeaderKind::Jito, Some("bundle_result".into()), age(t)),
            (None, None) => (LeaderKind::Unknown, None, None),
        }
    }

    pub fn kind(&self, slot: u64) -> LeaderKind {
        let g = self.r();
        match g.sched.get(&slot) { Some(id) => LeaderBook::kind_of(&g, id, now_ns()).0, None => LeaderKind::Unknown }
    }

    /// the slot's leader and kind, as an attempt records it
    pub fn snapshot(&self, slot: u64) -> LeaderSnap {
        let g = self.r();
        let leader = g.sched.get(&slot).copied();
        let (kind, kind_src, kind_age_s) = match &leader { Some(id) => LeaderBook::kind_of(&g, id, now_ns()), None => (LeaderKind::Unknown, None, None) };
        LeaderSnap { slot, leader: leader.map(|k| b58(&k)), kind, kind_src, kind_age_s, region: None, rtt_ms: None, rtt_age_s: None, rtt_src: None, client: None }
    }

    /// A validator identity named by one of our bundle results (`Accepted` / `Processed`)
    pub fn note_bundle_validator(&self, identity: &str) {
        let Ok(k) = bs58::decode(identity.trim()).into_vec() else { return };
        let Ok(k) = Pk::try_from(k) else { return };
        self.w().bundle_seen.insert(k, now_ns());
    }

    /// A Jito validators API answer (`{"validators": [{"identity_account", "running_jito", "running_bam"}]}`) from `src`.
    /// Returns how many validators it names
    pub fn set_list(&self, src: &str, v: &Value, t: u64) -> Result<usize> {
        let list = parse_list(v)?;
        let n = list.len();
        let mut g = self.w();
        g.lists.retain(|l| l.is_static || l.src != src);
        g.lists.insert(0, KindList { src: src.into(), fetched_ns: t, dated_ns: t, map: list, is_static: false });
        Ok(n)
    }

    /// The dated static fallback (`data/validators-meta.json`: `{"date": "YYYY-MM-DD", "source", "validators": {identity:
    /// {"jito": bool, "bam": bool}}}`). Returns how many validators it names
    pub fn load_static(&self, path: &std::path::Path) -> Result<usize> {
        let v: Value = serde_json::from_str(&std::fs::read_to_string(path).with_context(|| format!("reading {}", path.display()))?)?;
        let date = v["date"].as_str().context("validators-meta.json: no date")?;
        let dated_ns = date_ns(date).with_context(|| format!("validators-meta.json: bad date {date}"))?;
        let mut map = HashMap::new();
        for (k, x) in v["validators"].as_object().context("validators-meta.json: no validators")? {
            let Ok(b) = bs58::decode(k).into_vec() else { continue };
            let Ok(id) = Pk::try_from(b) else { continue };
            map.insert(id, if x["bam"].as_bool() == Some(true) { LeaderKind::Bam } else if x["jito"].as_bool() == Some(true) { LeaderKind::Jito } else { LeaderKind::Other });
        }
        let n = map.len();
        let mut g = self.w();
        g.lists.retain(|l| !l.is_static);
        g.lists.push(KindList { src: format!("static:{}@{date}", path.file_name().map(|f| f.to_string_lossy().into_owned()).unwrap_or_default()), fetched_ns: now_ns(),
            dated_ns, map, is_static: true });
        Ok(n)
    }

    /// A window of the schedule from `start`: the slots not known before are written to leaders.jsonl (with each one's
    /// kind as known now). Returns the slots that were new
    pub fn add_window(&self, start: u64, leaders: &[Pk]) -> usize {
        let t = now_ns();
        let mut lines = Vec::new();
        {
            let mut g = self.w();
            g.last_window = Some(start);
            for (i, id) in leaders.iter().enumerate() {
                let slot = start + i as u64;
                if g.sched.insert(slot, *id).is_none() { lines.push((slot, *id)); }
            }
            let floor = start.saturating_sub(KEEP_BEHIND);
            g.sched = g.sched.split_off(&floor);
            if self.rec.is_on() {
                let rows: Vec<Value> = lines.iter().map(|(slot, id)| {
                    let (kind, src, age) = LeaderBook::kind_of(&g, id, t);
                    json!({ "slot": slot, "leader": b58(id), "kind": kind.as_str(), "kind_src": src, "kind_age_s": age, "region": null, "rtt_ms": null,
                        "rtt_age_s": null, "rtt_src": null, "client": null, "t_ns": t })
                }).collect();
                if !rows.is_empty() {
                    let n = rows.len() as u32;
                    self.rec.emit(LEADERS, Record::enc_lines(n, move |o| {
                        for (k, r) in rows.iter().enumerate() { if k > 0 { o.push(b'\n'); } let _ = serde_json::to_writer(&mut *o, r); }
                    }));
                }
            }
        }
        lines.len()
    }

    /// Whether a new window is due at `slot` (none yet, or `REFRESH_SLOTS` past the last one)
    pub fn due(&self, slot: u64) -> bool { self.r().last_window.map_or(true, |w| slot >= w + REFRESH_SLOTS || slot < w) }

    /// Fetch the window from `start` (`getSlotLeaders(start, 400)`) and add it; returns its leaders
    pub async fn refresh_window(&self, rpc: &crate::rpc::Rpc, start: u64) -> Result<Vec<Pk>> {
        let v = rpc.call("getSlotLeaders", json!([start, WINDOW])).await?;
        let list: Vec<Pk> = v.as_array().context("getSlotLeaders: not a list")?.iter()
            .map(|x| x.as_str().and_then(|s| bs58::decode(s).into_vec().ok()).and_then(|b| Pk::try_from(b).ok()).context("getSlotLeaders: a bad identity"))
            .collect::<Result<_>>()?;
        if list.is_empty() { bail!("getSlotLeaders({start}): empty"); }
        self.add_window(start, &list);
        Ok(list)
    }

    /// the sources and their sizes (run.log, events)
    pub fn sources(&self) -> Vec<(String, usize, u64)> { self.r().lists.iter().map(|l| (l.src.clone(), l.map.len(), l.fetched_ns)).collect() }
}

/// The run's LeaderBook, for the sources that have no handle on it (the Jito result stream)
static BOOK: std::sync::OnceLock<Arc<LeaderBook>> = std::sync::OnceLock::new();

/// make `book` the run's LeaderBook (`arbx run`, once)
pub fn install(book: Arc<LeaderBook>) { let _ = BOOK.set(book); }

/// A validator identity named by one of our bundle results (send/jito.rs), to the run's LeaderBook if there is one
pub fn note_bundle_validator(identity: &str) { if let Some(b) = BOOK.get() { b.note_bundle_validator(identity); } }

/// `{"validators": [{identity_account, running_jito, running_bam}]}` as kinds
fn parse_list(v: &Value) -> Result<HashMap<Pk, LeaderKind>> {
    let mut map = HashMap::new();
    for x in v["validators"].as_array().context("no `validators` list")? {
        let Some(id) = x["identity_account"].as_str() else { continue };
        let Ok(b) = bs58::decode(id).into_vec() else { continue };
        let Ok(id) = Pk::try_from(b) else { continue };
        let k = if x["running_bam"].as_bool() == Some(true) { LeaderKind::Bam } else if x["running_jito"].as_bool() == Some(true) { LeaderKind::Jito } else { LeaderKind::Other };
        map.insert(id, k);
    }
    if map.is_empty() { bail!("no validator in the list"); }
    Ok(map)
}

/// "YYYY-MM-DD" as ns since the epoch (midnight UTC)
fn date_ns(d: &str) -> Option<u64> {
    let p: Vec<i64> = d.split('-').map(|x| x.parse().ok()).collect::<Option<_>>()?;
    let [y, m, day] = p[..] else { return None };
    if !(1..=12).contains(&m) || !(1..=31).contains(&day) { return None; }
    // days from civil (Howard Hinnant)
    let y = if m <= 2 { y - 1 } else { y };
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let mp = (m + 9) % 12;
    let doy = (153 * mp + 2) / 5 + day - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    let days = era * 146_097 + doe - 719_468;
    u64::try_from(days).ok().map(|d| d * 86_400 * 1_000_000_000)
}

/// The engine input for a window (`Event::Input` leader_window; the journal's INPUT record)
pub fn window_input(start: u64, leaders: &[Pk]) -> Value { json!({ "start": start, "leaders": leaders.iter().map(b58).collect::<Vec<_>>() }) }

/// Run the LeaderBook's refreshes on `rt` (the background runtime) until `stop`: a new schedule window every 100 slots
/// (the current slot is the engine's, `send::tpu::SLOT`, or `getSlot` until it has one), handed to the engine as an
/// input; the validator lists every `refresh_min` minutes (a failure keeps the older list or the static fallback, and
/// is an events.jsonl `leaders_list_stale`)
pub fn start(book: Arc<LeaderBook>, rpc: crate::rpc::Rpc, cfg: LeadersCfg, rt: &tokio::runtime::Handle, stop: Arc<AtomicBool>,
    back: crossbeam_channel::Sender<crate::feeds::Event>, rec: Rec) {
    rt.spawn(async move {
        let http = reqwest::Client::builder().timeout(std::time::Duration::from_secs(20)).build().ok();
        let mut next_lists = 0u64;
        let mut fails = 0u32;
        while !stop.load(Ordering::Relaxed) {
            let now = now_ns();
            if now >= next_lists {
                next_lists = now + cfg.refresh_min.max(1) * 60_000_000_000;
                for url in &cfg.validator_lists {
                    let host = crate::provenance::host_of(url);
                    let got = match &http {
                        Some(h) => match h.get(url).send().await {
                            Ok(r) if r.status().is_success() => r.json::<Value>().await.map_err(anyhow::Error::from).and_then(|v| book.set_list(&host, &v, now_ns())),
                            Ok(r) => Err(anyhow::anyhow!("HTTP {}", r.status().as_u16())),
                            Err(e) => Err(anyhow::anyhow!(crate::rpc::scrub(&e.to_string()))),
                        },
                        None => Err(anyhow::anyhow!("no HTTP client")),
                    };
                    match got {
                        Ok(n) => rec.event("leaders_refresh", "leaders", None, json!({ "src": host, "validators": n })),
                        Err(e) => rec.event("leaders_list_stale", "leaders", None, json!({ "src": host, "error": format!("{e:#}"),
                            "using": book.sources().first().map(|s| s.0.clone()) })),
                    }
                }
            }
            let mut slot = crate::send::tpu::SLOT.load(Ordering::Relaxed);
            if slot == 0 { slot = rpc.slot().await.unwrap_or(0); }
            if slot > 0 && book.due(slot) {
                match book.refresh_window(&rpc, slot).await {
                    Ok(list) => { fails = 0; let _ = back.send(crate::feeds::Event::Input { kind: crate::feeds::InputKind::LeaderWindow, data: Arc::new(window_input(slot, &list)) }); }
                    Err(e) => {
                        fails += 1;
                        if fails == 1 || fails % 30 == 0 { rec.event("leaders_list_stale", "leaders", None, json!({ "src": "getSlotLeaders", "error": format!("{e:#}"), "fails": fails })); }
                    }
                }
            }
            tokio::time::sleep(std::time::Duration::from_secs(2)).await;
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    /// A fake JSON-RPC server: every request's (method, params) goes to `answer`, whose value is the `result`
    pub async fn fake_rpc(answer: impl Fn(&str, &Value) -> Value + Send + Sync + 'static) -> String {
        let l = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = l.local_addr().unwrap();
        let answer = Arc::new(answer);
        tokio::spawn(async move {
            loop {
                let Ok((mut s, _)) = l.accept().await else { return };
                let answer = answer.clone();
                tokio::spawn(async move {
                    let mut buf = Vec::new();
                    let mut chunk = [0u8; 8192];
                    loop {
                        let Ok(n) = s.read(&mut chunk).await else { return };
                        if n == 0 { return; }
                        buf.extend_from_slice(&chunk[..n]);
                        let Some(end) = buf.windows(4).position(|w| w == b"\r\n\r\n") else { continue };
                        let head = String::from_utf8_lossy(&buf[..end]).to_ascii_lowercase();
                        let len: usize = head.lines().find_map(|l| l.strip_prefix("content-length:").map(|v| v.trim().parse().unwrap())).unwrap_or(0);
                        if buf.len() < end + 4 + len { continue; }
                        let req: Value = serde_json::from_slice(&buf[end + 4..end + 4 + len]).unwrap();
                        let body = json!({ "jsonrpc": "2.0", "id": req["id"], "result": answer(req["method"].as_str().unwrap_or(""), &req["params"]) }).to_string();
                        let resp = format!("HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{body}", body.len());
                        let _ = s.write_all(resp.as_bytes()).await;
                        return;
                    }
                });
            }
        });
        format!("http://{addr}")
    }

    fn id(n: u8) -> Pk { [n; 32] }

    /// PLAN WP-03 acceptance: the window refresh and the kind lookup against a fake RPC. Windows are 400 slots from the
    /// current slot, the next is due 100 slots later and adds only the new slots (leaders.jsonl lines); the kind comes
    /// from the API list (bam / jito / absent = other), then our bundle results, then the static fallback
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn window_refresh_and_kind_lookup_with_a_fake_rpc() {
        // leader of slot s: validator (s / 4) % 3 + 1 (four slots each)
        let calls = Arc::new(std::sync::Mutex::new(Vec::new()));
        let c2 = calls.clone();
        let url = fake_rpc(move |m, p| {
            c2.lock().unwrap().push((m.to_string(), p.clone()));
            let (start, n) = (p[0].as_u64().unwrap(), p[1].as_u64().unwrap());
            json!((start..start + n).map(|s| b58(&id(((s / 4) % 3 + 1) as u8))).collect::<Vec<_>>())
        }).await;
        let rpc = crate::rpc::Rpc::new(url);
        let dir = std::env::temp_dir().join(format!("arbx-leaders-{}-{}", std::process::id(), now_ns()));
        let rec = crate::rec::start(crate::rec::Opts { dir: dir.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![], monitor: false,
            echo: Some(Box::new(std::io::sink())) }).unwrap();
        let book = LeaderBook::new(rec.clone());
        assert!(book.due(1_000));
        let w = book.refresh_window(&rpc, 1_000).await.unwrap();
        assert_eq!(w.len(), 400);
        assert_eq!(calls.lock().unwrap()[0], ("getSlotLeaders".to_string(), json!([1_000, 400])));
        assert_eq!((book.leader(1_000), book.leader(1_004), book.leader(1_399), book.leader(1_400)), (Some(id(2)), Some(id(3)), Some(id(2)), None));
        assert!(!book.due(1_099) && book.due(1_100), "a new window every 100 slots");
        book.refresh_window(&rpc, 1_100).await.unwrap();
        assert_eq!(book.leader(1_499), Some(id(3)));
        // no list yet: unknown; then the static fallback; then the API list overrides it; bundle results fill the rest
        assert_eq!(book.kind(1_000), LeaderKind::Unknown);
        let st = dir.join("validators-meta.json");
        std::fs::write(&st, json!({ "date": "2026-10-03", "source": "test", "validators": { b58(&id(1)): { "jito": true, "bam": false }, b58(&id(2)): { "jito": true, "bam": true } } }).to_string()).unwrap();
        assert_eq!(book.load_static(&st).unwrap(), 2);
        assert_eq!((book.kind(1_008), book.kind(1_000), book.kind(1_004)), (LeaderKind::Jito, LeaderKind::Bam, LeaderKind::Other));
        let s = book.snapshot(1_000);
        assert_eq!((s.kind_src.as_deref(), s.leader.clone()), (Some("static:validators-meta.json@2026-10-03"), Some(b58(&id(2)))));
        assert!(s.kind_age_s.unwrap() > 0, "the static list's age counts from its date");
        let api = json!({ "validators": [{ "identity_account": b58(&id(1)), "running_jito": true, "running_bam": true },
            { "identity_account": b58(&id(2)), "running_jito": true, "running_bam": false }] });
        assert_eq!(book.set_list("kobe.mainnet.jito.network", &api, now_ns()).unwrap(), 2);
        assert_eq!((book.kind(1_008), book.kind(1_000), book.kind(1_004)), (LeaderKind::Bam, LeaderKind::Jito, LeaderKind::Other));
        assert_eq!(book.snapshot(1_000).kind_src.as_deref(), Some("kobe.mainnet.jito.network"));
        book.note_bundle_validator(&b58(&id(3)));
        let s = book.snapshot(1_004);
        assert_eq!((s.kind, s.kind_src.as_deref()), (LeaderKind::Jito, Some("bundle_result")));
        assert_eq!(book.snapshot(5).kind, LeaderKind::Unknown, "a slot outside the schedule");
        // leaders.jsonl: one line per newly learned slot (400 + 100), kinds as known then
        rec.close();
        let lines = crate::rec::read_jsonl(&dir, "leaders").unwrap();
        assert_eq!(lines.len(), 500);
        assert_eq!((lines[0]["slot"].as_u64(), lines[0]["leader"].as_str(), lines[0]["kind"].as_str()), (Some(1_000), Some(b58(&id(2)).as_str()), Some("unknown")));
        assert!(lines[0].get("rtt_ms").is_some_and(|v| v.is_null()) && lines[0]["t_ns"].as_u64().is_some());
        assert_eq!(lines[499]["slot"].as_u64(), Some(1_499));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn dates_and_the_shipped_fallback() {
        assert_eq!(date_ns("1970-01-02"), Some(86_400_000_000_000));
        assert_eq!(date_ns("2026-10-03"), Some(1_790_985_600 * 1_000_000_000));
        assert!(date_ns("2026-13-01").is_none());
        let book = LeaderBook::new(Rec::off());
        let n = book.load_static(&std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("data/validators-meta.json")).unwrap();
        assert!(n > 500, "the shipped fallback names the Jito validators: {n}");
    }
}
