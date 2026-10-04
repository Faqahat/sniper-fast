//! The LeaderBook (PLAN WP-03 item 10, WP-08 item 1; MEASUREMENT §4.27, §4.28): who leads each slot, what kind of
//! leader it is, where it is, how far its TPU endpoint is from us, and what client it runs.
//!
//! - **Schedule:** `getSlotLeaders` in 400-slot windows from the current slot, refreshed every 100 slots, on the
//!   background runtime. Each newly learned slot is a leaders.jsonl line (`event` `learned`); each window also reaches
//!   the engine as an `Event::Input` (`leader_window`), so the journal holds what the send checks will read (WP-05).
//! - **Kind** (`jito`, `bam`, `other`, `unknown`), each source recorded with its time (F39):
//!   1. the Jito validators API (`[leaders] validator_lists`, default `https://kobe.mainnet.jito.network/api/v1/validators`:
//!      `{"validators": [{"identity_account", "running_jito", "running_bam", ...}]}`, checked against the 2026-10-03
//!      snapshot `arb-lab/runs-long/kobe.json`: 648 validators, 383 running BAM). Its `running_bam` is the public BAM
//!      list; a validator absent from it runs neither;
//!   2. validator identities seen in our own bundle results (`Accepted` / `Processed` `validator_identity`): they take
//!      Jito bundles. They fill in leaders no list names, and outrank a list that says `other` (the list is older);
//!   3. the dated static fallback `data/validators-meta.json` (built from that snapshot), used while no API list was
//!      fetched (Cherry's address is refused by the API: arb-lab's leaders.py fetched it elsewhere);
//!   4. (WP-08) the client a validator announces in gossip (`getClusterNodes` `clientId`), for a validator no list names
//!      and no bundle result showed: `JitoLabs` is `jito`, `AgaveBam` / `FireBAM` are `bam`, plain `Agave` is `other`
//!      (`kind_src` `gossip_client`); other clients (Firedancer, Harmonic, Rakurai, ...) say nothing about Jito.
//!
//!   An `unknown` kind says why (review WP-08 #6): `kind_src` `no_schedule` (the slot is outside the schedule the book
//!   holds) or `no_source` (a known leader that no source names). A refresh that changes the kind of a slot already
//!   written is a leaders.jsonl line again (`event` `kind_update`), written by the refresher for the slots from the
//!   current one on (the WP-03 hand-off).
//! - **Validator metadata** (WP-08): `getClusterNodes` (gossip IP, TPU-QUIC address, version, client; every 10 minutes)
//!   and `getVoteAccounts` (vote account, stake; every `refresh_min`); a failed fetch is tried again after 30 s, then
//!   60 s, ... up to its period (review WP-08 #8). Places come from the offline table `[leaders] geo_table`
//!   (`data/ip-geo.csv`, DB-IP City Lite ranges): `city` is `<country>-<city>`, `region` the metro it belongs to
//!   ([`METROS`]: Tokyo, New York, Frankfurt, Northern Virginia, ... gather their suburbs; review WP-08 #9), else the
//!   city. A validator's `region` / `city` are its gossip IP's; `tpu_region` is its announced TPU-QUIC endpoint's, which
//!   for BAM and Harmonic validators is a shared ingress node, often in another city or country (review WP-08 #3:
//!   `tpu_shared_by` counts the nodes announcing the same endpoint). validators.jsonl, one line per validator, every 10
//!   minutes (review WP-08 #7: segments are 20 minutes, the RTTs are measured after the first one).
//! - **RTT** (F40): [`probe_loop`] makes a QUIC handshake (no data sent; ALPN `solana-tpu`, as send/tpu.rs) to the
//!   TPU-QUIC endpoints of the leaders of the next 64 slots, at most `rtt_per_sec` a second, each endpoint again after 5
//!   minutes (a failed one after 1 minute). It is kept **per endpoint** (review WP-08 #3): one handshake measures every
//!   validator behind a shared BAM or Harmonic ingress node. It is labelled **host -> leader TPU-QUIC RTT** (`rtt_src`
//!   `quic_handshake`): host to the endpoint the leader announces, not the bundle's path, which runs block engine ->
//!   leader. A leader whose endpoint has no fresh measurement (some validators rate-limit handshakes) falls back to the
//!   median fresh RTT of the endpoints in its endpoint's region (`tpu_region`; its gossip region when it announces no
//!   endpoint) (`rtt_src` `region_bucket`). An RTT older than 10 minutes is not used. The block engine's keep-alive RTT
//!   is published by the send path ([`note_be_rtt`], WP-05) and carried as `be_rtt_ms`.
//! - `leader(slot)`, `kind(slot)` and `snapshot(slot)` (the struct WP-05 copies into attempts: the leader, its kind,
//!   places, endpoint, RTT, client, `be_rtt_ms` and the next distinct leader). send/tpu.rs uses this book for its
//!   targets ([`LeaderBook::next_leaders`]): its own `Book` is gone.
//! - **Locks** (review WP-08 #10): readers on hot paths (the state stream's block metas, TPU sends, attempts' snapshots)
//!   take the read lock for a few lookups. The long jobs (leaders.jsonl lines, validators.jsonl) copy what they need
//!   under the read lock and build their JSON after releasing it; the prober takes the write lock only to mark the
//!   endpoint it picked.
use crate::config::LeadersCfg;
use crate::feeds::clock::now_ns;
use crate::rec::{Rec, Record, LEADERS, VALIDATORS};
use crate::tx::{b58, Pk};
use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap};
use std::net::{IpAddr, SocketAddr};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, RwLock};
use std::time::Duration;

/// slots per `getSlotLeaders` window, and how often (in slots) a new window is fetched
pub const WINDOW: u64 = 400;
pub const REFRESH_SLOTS: u64 = 100;
/// schedule entries kept below the current slot
const KEEP_BEHIND: u64 = 2_000;
const S: u64 = 1_000_000_000;
/// an endpoint's RTT is measured again after this long (field acceptance: an RTT from the previous 10 minutes)
pub const RTT_REFRESH_NS: u64 = 300 * S;
/// an endpoint whose handshake failed is tried again after this long
pub const RTT_RETRY_NS: u64 = 60 * S;
/// an RTT (an endpoint's own or a region's) older than this is not used
pub const RTT_MAX_AGE_NS: u64 = 600 * S;
/// a handshake not complete by then has failed
pub const RTT_TIMEOUT: Duration = Duration::from_millis(1_500);
/// the prober measures the endpoints of the leaders of the next this many slots
pub const RTT_LOOKAHEAD: u64 = 64;
/// getClusterNodes is fetched again after this long (a validator's TPU address moves when it restarts)
pub const NODES_REFRESH_NS: u64 = 600 * S;
/// validators.jsonl is written this often (review WP-08 #7: at least one snapshot with RTTs in a 20-minute segment)
pub const VALIDATORS_EVERY_NS: u64 = 600 * S;
/// a failed refresh is tried again after this long, doubled on each further failure up to its own period
pub const RETRY_FIRST_NS: u64 = 30 * S;
/// the block engine's keep-alive RTT is carried while it is younger than this
pub const BE_RTT_MAX_AGE_NS: u64 = 300 * S;

#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum LeaderKind { Jito, Bam, Other, Unknown }

impl LeaderKind {
    pub fn as_str(self) -> &'static str { match self { LeaderKind::Jito => "jito", LeaderKind::Bam => "bam", LeaderKind::Other => "other", LeaderKind::Unknown => "unknown" } }
    /// what a gossip `clientId` says about the Jito block engine: JitoLabs runs it, the BAM clients run BAM, plain Agave
    /// runs neither; other clients are not evidence either way
    pub fn from_client(client: &str) -> Option<LeaderKind> {
        match client { "JitoLabs" => Some(LeaderKind::Jito), "AgaveBam" | "FireBAM" => Some(LeaderKind::Bam), "Agave" => Some(LeaderKind::Other), _ => None }
    }
}

/// `kind_src` of an `unknown` kind: the slot is outside the schedule the book holds (a window that failed to load)
pub const NO_SCHEDULE: &str = "no_schedule";
/// `kind_src` of an `unknown` kind: a leader no source names (no list, no bundle result, no telling gossip client)
pub const NO_SOURCE: &str = "no_source";

/// One validator list: where it came from, when it was fetched, and the date it describes (the static file's own date)
struct KindList { src: String, fetched_ns: u64, dated_ns: u64, map: HashMap<Pk, LeaderKind>, is_static: bool }

/// A cluster node as `getClusterNodes` describes it
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Node {
    pub gossip: Option<IpAddr>,
    pub tpu_quic: Option<SocketAddr>,
    pub version: Option<String>,
    /// `clientId` when the node sends it, else the family its version implies (`client_src` says which)
    pub client: Option<String>,
    pub client_src: Option<&'static str>,
}

/// A validator's vote account (`getVoteAccounts`)
#[derive(Clone, Debug, PartialEq)]
pub struct Vote { pub vote: Pk, pub stake: u64, pub delinquent: bool }

/// One TPU-QUIC endpoint's handshake RTT bookkeeping
#[derive(Clone, Debug, Default)]
struct Rtt { ms: Option<f64>, t_ok: u64, last_try: u64, last_failed: bool, ok: u64, failed: u64, err: Option<String> }

impl Rtt {
    fn fresh(&self, now: u64) -> bool { self.ms.is_some() && now.saturating_sub(self.t_ok) <= RTT_MAX_AGE_NS }
    fn due(&self, now: u64) -> bool { now.saturating_sub(self.last_try) >= if self.last_failed { RTT_RETRY_NS } else { RTT_REFRESH_NS } }
}

/// A schedule slot and the kind last written for it to leaders.jsonl
#[derive(Clone, Debug)]
struct SlotEntry { leader: Pk, kind: LeaderKind, kind_src: Option<String> }

/// Metros (review WP-08 #9): the table's cities (`<country>-<city>`, as [`city_name`] makes them) that one region
/// gathers, so a metro's suburbs and data-centre towns share one region (and one RTT bucket). Every name is checked
/// against the shipped table (`the_geo_table`); a city not listed is its own region
pub const METROS: &[(&str, &[&str])] = &[
    ("JP-Tokyo", &["JP-Chiyoda_City", "JP-Koto-ku", "JP-Minato", "JP-Shibuya_City", "JP-Shinagawa", "JP-Inzai"]),
    ("US-New_York", &["US-New_York", "US-Newark", "US-Piscataway", "US-Secaucus", "US-Englewood_Cliffs", "US-Staten_Island"]),
    ("DE-Frankfurt", &["DE-Frankfurt_am_Main", "DE-Offenbach", "DE-Hattersheim_am_Main", "DE-Limburg_an_der_Lahn", "DE-Gräfenhausen", "DE-Rüsselsheim_am_Main"]),
    ("US-Ashburn", &["US-Ashburn", "US-Sterling", "US-Reston", "US-Warrenton", "US-Washington_D.C.", "US-The_Wharf"]),
    ("US-Chicago", &["US-Chicago", "US-Elk_Grove_Village", "US-Lombard"]),
    ("US-San_Jose", &["US-San_Jose", "US-Santa_Clara", "US-San_Mateo", "US-Berkeley"]),
    ("US-Dallas", &["US-Dallas", "US-Richardson"]),
    ("US-Salt_Lake_City", &["US-Salt_Lake_City", "US-Draper", "US-Herriman"]),
    ("US-Denver", &["US-Denver", "US-Boulder", "US-Greenwood_Village", "US-Westminster"]),
    ("US-Atlanta", &["US-Atlanta", "US-Norcross"]),
    ("US-Portland", &["US-Portland", "US-Hillsboro"]),
    ("US-Seattle", &["US-Seattle", "US-Kent"]),
    ("US-Miami", &["US-Miami", "US-Boca_Raton"]),
    ("NL-Amsterdam", &["NL-Amsterdam", "NL-Haarlem", "NL-Purmerend", "NL-Wormerveer"]),
    ("GB-London", &["GB-London", "GB-Slough", "GB-Maidenhead", "GB-Erith", "GB-Westminster"]),
    ("IE-Dublin", &["IE-Dublin", "IE-Saggart", "IE-Walkinstown"]),
    ("HK-Hong_Kong", &["HK-Hong_Kong", "HK-Quarry_Bay", "HK-Chai_Wan", "HK-Lau_Fau_Shan", "HK-Kowloon_Bay", "HK-Tsuen_Wan", "HK-Wan_Chai"]),
    ("FR-Paris", &["FR-Aubervilliers", "FR-Puteaux"]),
    ("FR-Roubaix", &["FR-Roubaix", "FR-Wattrelos"]),
    ("DE-Munich", &["DE-Munich", "DE-Ismaning", "DE-Ottobrunn"]),
    ("CH-Zurich", &["CH-Zurich", "CH-Wallisellen", "CH-Winterthur"]),
    ("KR-Seoul", &["KR-Seoul", "KR-Yongsan-dong"]),
    ("CA-Vancouver", &["CA-Vancouver", "CA-Surrey"]),
    ("CA-Toronto", &["CA-Toronto", "CA-Mississauga"]),
    ("SG-Singapore", &["SG-Singapore", "SG-MacPherson"]),
    ("FI-Helsinki", &["FI-Helsinki", "FI-Tuusula"]),
    ("RU-Moscow", &["RU-Moscow", "RU-Belyaninovo", "RU-Ramenskoye"]),
];

/// the region (metro) of a `<country>-<city>` name
pub fn metro_of(city: &str) -> Option<&'static str> { METROS.iter().find(|(_, cs)| cs.contains(&city)).map(|(m, _)| *m) }

/// Where an address is: its city (`<country>-<city>`) and its region (the metro the city belongs to, else the city)
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Place { pub city: Arc<str>, pub region: Arc<str> }

/// The offline IP -> location table (`data/ip-geo.csv`: `ip_start,ip_end,country,stateprov,city`, IPv4, `#` comments)
pub struct Geo { ranges: Vec<(u32, u32, Place)>, pub src: String }

impl Geo {
    /// The table in `text` (`src` names it in validators.jsonl)
    pub fn parse(text: &str, src: &str) -> Result<Geo> {
        let mut ranges = Vec::new();
        let mut places: HashMap<String, Place> = HashMap::new();
        for (n, line) in text.lines().enumerate() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') || line.starts_with("ip_start") { continue; }
            let f = split_csv(line);
            if f.len() < 5 { bail!("{src}:{}: {} columns, want ip_start,ip_end,country,stateprov,city", n + 1, f.len()); }
            let (Ok(a), Ok(b)) = (f[0].parse::<std::net::Ipv4Addr>(), f[1].parse::<std::net::Ipv4Addr>()) else { bail!("{src}:{}: not an IPv4 range", n + 1) };
            let city = city_name(&f[2], &f[4]);
            let place = places.entry(city.clone()).or_insert_with(|| {
                let region: Arc<str> = Arc::from(metro_of(&city).unwrap_or(&city));
                Place { city: Arc::from(city.as_str()), region }
            }).clone();
            ranges.push((u32::from(a), u32::from(b), place));
        }
        ranges.sort_by_key(|r| r.0);
        if ranges.windows(2).any(|w| w[1].0 <= w[0].1) { bail!("{src}: overlapping ranges"); }
        Ok(Geo { ranges, src: src.to_string() })
    }
    pub fn load(path: &std::path::Path) -> Result<Geo> {
        let text = std::fs::read_to_string(path).with_context(|| format!("reading {}", path.display()))?;
        Geo::parse(&text, &path.file_name().map(|f| f.to_string_lossy().into_owned()).unwrap_or_default())
    }
    /// where an address is (IPv4 only)
    pub fn place(&self, ip: IpAddr) -> Option<&Place> {
        let IpAddr::V4(v4) = ip else { return None };
        let x = u32::from(v4);
        let i = self.ranges.partition_point(|r| r.0 <= x).checked_sub(1)?;
        let r = &self.ranges[i];
        (x <= r.1).then_some(&r.2)
    }
    /// the region of an address (the metro, else the city)
    pub fn region(&self, ip: IpAddr) -> Option<Arc<str>> { self.place(ip).map(|p| p.region.clone()) }
    pub fn len(&self) -> usize { self.ranges.len() }
    pub fn is_empty(&self) -> bool { self.ranges.is_empty() }
    /// the distinct regions and cities of the table
    pub fn counts(&self) -> (usize, usize) {
        let r: std::collections::HashSet<&str> = self.ranges.iter().map(|x| &*x.2.region).collect();
        let c: std::collections::HashSet<&str> = self.ranges.iter().map(|x| &*x.2.city).collect();
        (r.len(), c.len())
    }
}

/// `DE` + `Frankfurt am Main (Innenstadt I)` -> `DE-Frankfurt_am_Main`: the country and the city without its district
pub fn city_name(country: &str, city: &str) -> String {
    let city = city.split(" (").next().unwrap_or("").trim();
    if city.is_empty() { country.to_string() } else { format!("{country}-{}", city.replace(' ', "_")) }
}

/// one CSV line's fields (double quotes, `""` inside quotes)
fn split_csv(line: &str) -> Vec<String> {
    let (mut out, mut cur, mut q) = (Vec::new(), String::new(), false);
    let mut it = line.chars().peekable();
    while let Some(c) = it.next() {
        match (c, q) {
            ('"', true) if it.peek() == Some(&'"') => { cur.push('"'); it.next(); }
            ('"', _) => q = !q,
            (',', false) => out.push(std::mem::take(&mut cur)),
            _ => cur.push(c),
        }
    }
    out.push(cur);
    out
}

/// the client family a version string implies when the node sends no `clientId`: Frankendancer 0.x, Firedancer 26+,
/// else Agave (or one of its forks)
pub fn client_from_version(v: &str) -> Option<&'static str> {
    let major: u64 = v.split('.').next()?.parse().ok()?;
    Some(match major { 0 => "Frankendancer", 26..=99 => "Firedancer", _ => "Agave" })
}

#[derive(Default)]
struct Inner {
    sched: BTreeMap<u64, SlotEntry>,
    /// the newest API list first, then the static fallback
    lists: Vec<KindList>,
    /// identity -> when our bundle results last named it
    bundle_seen: HashMap<Pk, u64>,
    /// the start of the last window the refresher fetched
    last_window: Option<u64>,
    nodes: HashMap<Pk, Node>,
    nodes_ns: u64,
    /// TPU-QUIC endpoint -> how many nodes announce it (BAM and Harmonic ingress nodes serve many validators)
    shared: HashMap<SocketAddr, u32>,
    /// identity -> its vote account
    votes: HashMap<Pk, Vote>,
    votes_ns: u64,
    /// handshake RTTs by TPU-QUIC endpoint (one measurement for every validator behind it)
    rtt: HashMap<SocketAddr, Rtt>,
    /// every measured endpoint by its own region: (ms, when) (the `region_bucket` fallback: kept up to date by each
    /// measurement, rebuilt when the geo table changes, so a snapshot only filters its region's few samples)
    buckets: HashMap<Arc<str>, HashMap<SocketAddr, (f64, u64)>>,
    geo: Option<Arc<Geo>>,
    /// a kind source changed since the last kind-update pass
    kinds_dirty: bool,
}

impl Inner {
    fn place(&self, ip: Option<IpAddr>) -> Option<&Place> { self.geo.as_deref()?.place(ip?) }
    fn rebuild_buckets(&mut self) {
        let mut b: HashMap<Arc<str>, HashMap<SocketAddr, (f64, u64)>> = HashMap::new();
        for (a, r) in &self.rtt {
            let (Some(ms), Some(p)) = (r.ms, self.place(Some(a.ip()))) else { continue };
            b.entry(p.region.clone()).or_default().insert(*a, (ms, r.t_ok));
        }
        self.buckets = b;
    }
    /// the median fresh RTT of a region's endpoints at `now` and the newest sample's time
    fn region_median(&self, region: &str, now: u64) -> Option<(f64, u64)> {
        let mut v: Vec<(f64, u64)> = self.buckets.get(region)?.values().filter(|x| now.saturating_sub(x.1) <= RTT_MAX_AGE_NS).copied().collect();
        if v.is_empty() { return None; }
        let newest = v.iter().map(|x| x.1).max().unwrap_or(now);
        v.sort_by(|a, b| a.0.total_cmp(&b.0));
        let n = v.len();
        Some((if n % 2 == 1 { v[n / 2].0 } else { (v[n / 2 - 1].0 + v[n / 2].0) / 2.0 }, newest))
    }
}

/// The region medians one job needs, each computed once (validators.jsonl asks for the same regions many times)
#[derive(Default)]
struct Medians(HashMap<Arc<str>, Option<(f64, u64)>>);

impl Medians {
    fn get(&mut self, inner: &Inner, region: &Arc<str>, now: u64) -> Option<(f64, u64)> {
        *self.0.entry(region.clone()).or_insert_with(|| inner.region_median(region, now))
    }
}

/// A leader's kind, the source that says so and that source's age (s)
type KindOf = (LeaderKind, Option<String>, Option<u64>);
/// An RTT (ms), its age (s) and its source (`quic_handshake`, `region_bucket`)
type RttOf = (Option<f64>, Option<u64>, Option<&'static str>);

/// What the book says about a validator at a moment: copied out under the read lock, turned into JSON after it
#[derive(Clone, Debug, Default)]
struct Facts {
    region: Option<Arc<str>>,
    city: Option<Arc<str>>,
    tpu: Option<SocketAddr>,
    tpu_region: Option<Arc<str>>,
    shared: Option<u32>,
    rtt: (Option<f64>, Option<u64>, Option<&'static str>),
    client: Option<String>,
}

impl Facts {
    /// the fields leaders.jsonl, validators.jsonl and the snapshot share
    fn put(&self, m: &mut serde_json::Map<String, Value>) {
        let s = |x: &Option<Arc<str>>| x.as_deref().map_or(Value::Null, |v| Value::String(v.to_string()));
        m.insert("region".into(), s(&self.region));
        m.insert("city".into(), s(&self.city));
        m.insert("tpu_quic".into(), self.tpu.map_or(Value::Null, |a| Value::String(a.to_string())));
        m.insert("tpu_region".into(), s(&self.tpu_region));
        m.insert("tpu_shared_by".into(), json!(self.shared));
        m.insert("rtt_ms".into(), json!(self.rtt.0));
        m.insert("rtt_age_s".into(), json!(self.rtt.1));
        m.insert("rtt_src".into(), json!(self.rtt.2));
        m.insert("client".into(), json!(self.client));
    }
}

/// The next distinct leader after a slot's (`attempts.leader.next`)
#[derive(Clone, Debug, PartialEq, serde::Serialize)]
pub struct NextLeader { pub slot: u64, pub identity: String, pub kind: LeaderKind }

/// What WP-05 copies into an attempt (`attempts.leader`), MEASUREMENT §4.27's fields
#[derive(Clone, Debug, PartialEq, serde::Serialize)]
pub struct LeaderSnap {
    pub slot: u64,
    pub leader: Option<String>,
    pub kind: LeaderKind,
    /// the kind's source; for `unknown`, why: `no_schedule`, `no_source`
    pub kind_src: Option<String>,
    pub kind_age_s: Option<u64>,
    /// the leader's gossip IP: its region (metro, else city) and city
    pub region: Option<String>,
    pub city: Option<String>,
    /// the TPU-QUIC endpoint it announces, that endpoint's region, and how many nodes announce it (a shared BAM or
    /// Harmonic ingress node when more than one)
    pub tpu_quic: Option<String>,
    pub tpu_region: Option<String>,
    pub tpu_shared_by: Option<u32>,
    /// host -> its TPU-QUIC endpoint (`quic_handshake`), else the median of its endpoint region's (`region_bucket`)
    pub rtt_ms: Option<f64>,
    pub rtt_age_s: Option<u64>,
    pub rtt_src: Option<String>,
    pub client: Option<String>,
    /// the block engine's latest keep-alive RTT ([`note_be_rtt`])
    pub be_rtt_ms: Option<f64>,
    pub next: Option<NextLeader>,
}

/// RTT counts (events.jsonl `leaders_refresh` with each validator snapshot): handshakes, the endpoints and regions with
/// a fresh RTT, and the validators (with a vote account) whose RTT is their endpoint's own, a region bucket, or none
#[derive(Clone, Debug, Default, PartialEq, serde::Serialize)]
pub struct RttStats {
    pub probes_ok: u64,
    pub probes_failed: u64,
    pub endpoints_fresh: usize,
    pub regions_fresh: usize,
    pub validators: usize,
    pub validators_rtt_own: usize,
    pub validators_rtt_bucket: usize,
}

pub struct LeaderBook { inner: RwLock<Inner>, rec: Rec }

impl LeaderBook {
    pub fn new(rec: Rec) -> Arc<LeaderBook> { Arc::new(LeaderBook { inner: RwLock::new(Inner::default()), rec }) }

    fn r(&self) -> std::sync::RwLockReadGuard<'_, Inner> { self.inner.read().unwrap_or_else(|e| e.into_inner()) }
    fn w(&self) -> std::sync::RwLockWriteGuard<'_, Inner> { self.inner.write().unwrap_or_else(|e| e.into_inner()) }

    pub fn leader(&self, slot: u64) -> Option<Pk> { self.r().sched.get(&slot).map(|e| e.leader) }

    /// a validator's kind, the source that says so and that source's age (s) at `now`
    fn kind_of(inner: &Inner, id: &Pk, now: u64) -> KindOf {
        let seen = inner.bundle_seen.get(id).copied();
        let age = |t: u64| Some(now.saturating_sub(t) / S);
        let gossip = || inner.nodes.get(id).filter(|n| n.client_src == Some("clientId")).and_then(|n| n.client.as_deref()).and_then(LeaderKind::from_client);
        // the newest list that is not the static fallback, else the static one
        let list = inner.lists.iter().find(|l| !l.is_static).or_else(|| inner.lists.iter().find(|l| l.is_static));
        match (list, seen) {
            (Some(l), seen) => match l.map.get(id).copied() {
                Some(LeaderKind::Other) | None if seen.is_some() => (LeaderKind::Jito, Some("bundle_result".into()), seen.and_then(age)),
                // absent from the list: the client it announces, when that says Jito or BAM (a list that names it wins)
                None => match gossip() {
                    Some(k @ (LeaderKind::Jito | LeaderKind::Bam)) => (k, Some("gossip_client".into()), age(inner.nodes_ns)),
                    _ => (LeaderKind::Other, Some(l.src.clone()), age(l.dated_ns)),
                },
                Some(k) => (k, Some(l.src.clone()), age(l.dated_ns)),
            },
            (None, Some(t)) => (LeaderKind::Jito, Some("bundle_result".into()), age(t)),
            (None, None) => match gossip() {
                Some(k) => (k, Some("gossip_client".into()), age(inner.nodes_ns)),
                None => (LeaderKind::Unknown, Some(NO_SOURCE.into()), None),
            },
        }
    }

    /// an identity's RTT at `now`: its endpoint's own handshake RTT while fresh, else the median fresh RTT of the
    /// endpoints in its endpoint's region (its gossip region without an endpoint), with the sample's age (the newest of
    /// the region's) and the source
    fn rtt_of(inner: &Inner, node: Option<&Node>, now: u64, med: &mut Medians) -> RttOf {
        let tpu = node.and_then(|n| n.tpu_quic);
        if let Some(r) = tpu.and_then(|a| inner.rtt.get(&a)).filter(|r| r.fresh(now)) { return (r.ms, Some(now.saturating_sub(r.t_ok) / S), Some("quic_handshake")); }
        let region = match tpu { Some(a) => inner.place(Some(a.ip())), None => inner.place(node.and_then(|n| n.gossip)) }.map(|p| p.region.clone());
        match region.and_then(|r| med.get(inner, &r, now)) {
            Some((ms, t)) => (Some(ms), Some(now.saturating_sub(t) / S), Some("region_bucket")),
            None => (None, None, None),
        }
    }

    /// what the book says of `id` at `now` (under the read lock: plain copies, no JSON)
    fn facts(inner: &Inner, id: &Pk, now: u64, med: &mut Medians) -> Facts {
        let node = inner.nodes.get(id);
        let gossip = inner.place(node.and_then(|n| n.gossip));
        let tpu = node.and_then(|n| n.tpu_quic);
        Facts { region: gossip.map(|p| p.region.clone()), city: gossip.map(|p| p.city.clone()), tpu,
            tpu_region: inner.place(tpu.map(|a| a.ip())).map(|p| p.region.clone()), shared: tpu.and_then(|a| inner.shared.get(&a).copied()),
            rtt: LeaderBook::rtt_of(inner, node, now, med), client: node.and_then(|n| n.client.clone()) }
    }

    pub fn kind(&self, slot: u64) -> LeaderKind {
        let g = self.r();
        match g.sched.get(&slot) { Some(e) => LeaderBook::kind_of(&g, &e.leader, now_ns()).0, None => LeaderKind::Unknown }
    }

    /// the slot's leader, kind, places, endpoint, RTT, client, the block engine's RTT and the next distinct leader, as an
    /// attempt records it
    pub fn snapshot(&self, slot: u64) -> LeaderSnap { self.snapshot_at(slot, now_ns()) }

    pub fn snapshot_at(&self, slot: u64, now: u64) -> LeaderSnap {
        let g = self.r();
        let leader = g.sched.get(&slot).map(|e| e.leader);
        let (kind, kind_src, kind_age_s) = match &leader { Some(id) => LeaderBook::kind_of(&g, id, now), None => (LeaderKind::Unknown, Some(NO_SCHEDULE.into()), None) };
        let f = leader.map(|id| LeaderBook::facts(&g, &id, now, &mut Medians::default())).unwrap_or_default();
        let next = leader.and_then(|id| g.sched.range(slot + 1..).find(|(_, e)| e.leader != id)
            .map(|(s, e)| NextLeader { slot: *s, identity: b58(&e.leader), kind: LeaderBook::kind_of(&g, &e.leader, now).0 }));
        drop(g);
        let s = |x: Option<Arc<str>>| x.map(|v| v.to_string());
        LeaderSnap { slot, leader: leader.map(|k| b58(&k)), kind, kind_src, kind_age_s, region: s(f.region), city: s(f.city), tpu_quic: f.tpu.map(|a| a.to_string()),
            tpu_region: s(f.tpu_region), tpu_shared_by: f.shared, rtt_ms: f.rtt.0, rtt_age_s: f.rtt.1, rtt_src: f.rtt.2.map(String::from), client: f.client,
            be_rtt_ms: be_rtt(now), next }
    }

    /// A validator identity named by one of our bundle results (`Accepted` / `Processed`)
    pub fn note_bundle_validator(&self, identity: &str) {
        let Ok(k) = bs58::decode(identity.trim()).into_vec() else { return };
        let Ok(k) = Pk::try_from(k) else { return };
        let mut g = self.w();
        if g.bundle_seen.insert(k, now_ns()).is_none() { g.kinds_dirty = true; }
    }

    /// A Jito validators API answer (`{"validators": [{"identity_account", "running_jito", "running_bam"}]}`) from `src`.
    /// Returns how many validators it names
    pub fn set_list(&self, src: &str, v: &Value, t: u64) -> Result<usize> {
        let list = parse_list(v)?;
        let n = list.len();
        let mut g = self.w();
        g.lists.retain(|l| l.is_static || l.src != src);
        g.lists.insert(0, KindList { src: src.into(), fetched_ns: t, dated_ns: t, map: list, is_static: false });
        g.kinds_dirty = true;
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
        g.kinds_dirty = true;
        Ok(n)
    }

    /// The offline geo table (`[leaders] geo_table`)
    pub fn set_geo(&self, geo: Geo) { let mut g = self.w(); g.geo = Some(Arc::new(geo)); g.rebuild_buckets(); }

    /// The cluster's nodes (`getClusterNodes`, [`parse_cluster_nodes`]) as of `t`. Returns how many
    pub fn set_nodes(&self, nodes: Vec<(Pk, Node)>, t: u64) -> usize {
        let n = nodes.len();
        let mut shared: HashMap<SocketAddr, u32> = HashMap::new();
        for (_, x) in &nodes { if let Some(a) = x.tpu_quic { *shared.entry(a).or_default() += 1; } }
        let map: HashMap<Pk, Node> = nodes.into_iter().collect();
        let mut g = self.w();
        g.nodes = map;
        g.shared = shared;
        g.nodes_ns = t;
        g.kinds_dirty = true;
        n
    }

    /// The vote accounts by identity (`getVoteAccounts`, [`parse_vote_accounts`]) as of `t`. Returns how many
    pub fn set_votes(&self, votes: Vec<(Pk, Vote)>, t: u64) -> usize {
        let n = votes.len();
        let map: HashMap<Pk, Vote> = votes.into_iter().collect();
        let mut g = self.w();
        g.votes = map;
        g.votes_ns = t;
        n
    }

    /// how old the node table is at `now` (None: never fetched)
    pub fn nodes_age(&self, now: u64) -> Option<u64> { let g = self.r(); (g.nodes_ns > 0).then(|| now.saturating_sub(g.nodes_ns)) }

    /// whether vote accounts are known
    pub fn has_votes(&self) -> bool { !self.r().votes.is_empty() }

    /// one leaders.jsonl line
    fn line(slot: u64, id: &Pk, t: u64, event: &str, kind: &KindOf, f: &Facts) -> Value {
        let mut m = serde_json::Map::new();
        m.insert("slot".into(), json!(slot));
        m.insert("leader".into(), json!(b58(id)));
        m.insert("kind".into(), json!(kind.0.as_str()));
        m.insert("kind_src".into(), json!(kind.1));
        m.insert("kind_age_s".into(), json!(kind.2));
        f.put(&mut m);
        m.insert("t_ns".into(), json!(t));
        m.insert("event".into(), json!(event));
        Value::Object(m)
    }

    fn emit_lines(&self, rows: Vec<Value>, stream: crate::rec::S) {
        if rows.is_empty() || !self.rec.is_on() { return; }
        let n = rows.len() as u32;
        self.rec.emit(stream, Record::enc_lines(n, move |o| {
            for (k, r) in rows.iter().enumerate() { if k > 0 { o.push(b'\n'); } let _ = serde_json::to_writer(&mut *o, r); }
        }));
    }

    /// A window of the schedule from `start` (the refresher's: the next window is due `REFRESH_SLOTS` later): the slots
    /// not known before are written to leaders.jsonl (with each one's kind as known now). Returns the slots that were new
    pub fn add_window(&self, start: u64, leaders: &[Pk]) -> usize { self.add_slots(start, leaders, true) }

    /// The same for a window fetched by another user of the book (send/tpu.rs): it does not move the refresher's window
    pub fn fill_window(&self, start: u64, leaders: &[Pk]) -> usize { self.add_slots(start, leaders, false) }

    fn add_slots(&self, start: u64, leaders: &[Pk], refresher: bool) -> usize {
        let t = now_ns();
        let new = {
            let mut g = self.w();
            if refresher { g.last_window = Some(start); }
            let mut new = Vec::new();
            for (i, id) in leaders.iter().enumerate() {
                let slot = start + i as u64;
                if g.sched.get(&slot).is_some_and(|e| e.leader == *id) { continue; }
                let k = LeaderBook::kind_of(&g, id, t);
                g.sched.insert(slot, SlotEntry { leader: *id, kind: k.0, kind_src: k.1.clone() });
                new.push((slot, *id, k));
            }
            let floor = start.saturating_sub(KEEP_BEHIND);
            g.sched = g.sched.split_off(&floor);
            new
        };
        self.write_lines(&new, t, "learned");
        new.len()
    }

    /// leaders.jsonl lines for `(slot, leader, kind)` rows: each leader's facts are copied under the read lock (once per
    /// leader), the lines are made after it is released
    fn write_lines(&self, rows: &[(u64, Pk, KindOf)], t: u64, event: &str) {
        if rows.is_empty() || !self.rec.is_on() { return; }
        let facts: HashMap<Pk, Facts> = {
            let g = self.r();
            let mut med = Medians::default();
            let mut m = HashMap::new();
            for (_, id, _) in rows { if !m.contains_key(id) { m.insert(*id, LeaderBook::facts(&g, id, t, &mut med)); } }
            m
        };
        let lines: Vec<Value> = rows.iter().map(|(slot, id, k)| LeaderBook::line(*slot, id, t, event, k, &facts[id])).collect();
        self.emit_lines(lines, LEADERS);
    }

    /// whether a kind source changed since the last [`LeaderBook::kind_updates`]
    pub fn kinds_dirty(&self) -> bool { self.r().kinds_dirty }

    /// The kind-update pass (MEASUREMENT §4.27 "plus kind updates"): every scheduled slot from `from` on whose kind (or
    /// its source) is not what leaders.jsonl last said is written again, `event` `kind_update`. Returns how many
    pub fn kind_updates(&self, from: u64) -> usize {
        let t = now_ns();
        // cleared first: a source that changes during the pass marks the book again for the next one
        self.w().kinds_dirty = false;
        // compared under the read lock, applied under a short write lock
        let changed: Vec<(u64, Pk, KindOf)> = {
            let g = self.r();
            g.sched.range(from..).filter_map(|(slot, e)| {
                let k = LeaderBook::kind_of(&g, &e.leader, t);
                (k.0 != e.kind || k.1 != e.kind_src).then_some((*slot, e.leader, k))
            }).collect()
        };
        if changed.is_empty() { return 0; }
        {
            let mut g = self.w();
            for (slot, id, k) in &changed { if let Some(e) = g.sched.get_mut(slot).filter(|e| e.leader == *id) { e.kind = k.0; e.kind_src = k.1.clone(); } }
        }
        self.write_lines(&changed, t, "kind_update");
        changed.len()
    }

    /// Whether a new window is due at `slot` (none yet, or `REFRESH_SLOTS` past the last one)
    pub fn due(&self, slot: u64) -> bool { self.r().last_window.map_or(true, |w| slot >= w + REFRESH_SLOTS || slot < w) }

    /// Fetch the window from `start` (`getSlotLeaders(start, 400)`) and add it; returns its leaders
    pub async fn refresh_window(&self, rpc: &crate::rpc::Rpc, start: u64) -> Result<Vec<Pk>> {
        let v = rpc.call("getSlotLeaders", json!([start, WINDOW])).await?;
        let list = parse_slot_leaders(&v).with_context(|| format!("getSlotLeaders({start})"))?;
        self.add_window(start, &list);
        Ok(list)
    }

    /// Fetch `getClusterNodes` and keep it; returns how many nodes
    pub async fn refresh_nodes(&self, rpc: &crate::rpc::Rpc) -> Result<usize> {
        let v = rpc.call("getClusterNodes", json!([])).await?;
        Ok(self.set_nodes(parse_cluster_nodes(&v)?, now_ns()))
    }

    /// Fetch `getVoteAccounts` and keep it; returns how many validators
    pub async fn refresh_votes(&self, rpc: &crate::rpc::Rpc) -> Result<usize> {
        let v = rpc.call("getVoteAccounts", json!([{ "commitment": "confirmed" }])).await?;
        Ok(self.set_votes(parse_vote_accounts(&v)?, now_ns()))
    }

    /// The distinct leaders from `slot` on, with their TPU-QUIC addresses, at most `n` (send/tpu.rs's targets): a leader
    /// without an address is left out, and so is a leader already listed
    pub fn next_leaders(&self, slot: u64, n: usize) -> Vec<(Pk, SocketAddr)> {
        let g = self.r();
        let mut out: Vec<(Pk, SocketAddr)> = Vec::new();
        let mut seen: Vec<Pk> = Vec::new();
        for (_, e) in g.sched.range(slot..) {
            if out.len() >= n { break; }
            if seen.contains(&e.leader) { continue; }
            seen.push(e.leader);
            if let Some(a) = g.nodes.get(&e.leader).and_then(|x| x.tpu_quic) { out.push((e.leader, a)); }
        }
        out
    }

    /// The next endpoint to measure at `slot`: among the TPU-QUIC endpoints of the leaders of the next `RTT_LOOKAHEAD`
    /// slots, the first never tried, or measured more than `RTT_REFRESH_NS` ago, or failed more than `RTT_RETRY_NS` ago.
    /// Found under the read lock; the write lock only marks the one picked as tried at `now`
    pub fn rtt_target(&self, slot: u64, now: u64) -> Option<SocketAddr> {
        let pick = {
            let g = self.r();
            let mut seen: Vec<SocketAddr> = Vec::new();
            let mut pick = None;
            for (_, e) in g.sched.range(slot..slot + RTT_LOOKAHEAD) {
                let Some(addr) = g.nodes.get(&e.leader).and_then(|n| n.tpu_quic) else { continue };
                if seen.contains(&addr) { continue; }
                seen.push(addr);
                if g.rtt.get(&addr).map_or(true, |r| r.due(now)) { pick = Some(addr); break; }
            }
            pick
        }?;
        let mut g = self.w();
        let r = g.rtt.entry(pick).or_default();
        // one prober runs; checked again all the same
        if r.last_try != 0 && !r.due(now) { return None; }
        r.last_try = now;
        Some(pick)
    }

    /// A handshake's result for the endpoint `addr` at `t`: its RTT (ms), or why it failed
    pub fn note_rtt(&self, addr: SocketAddr, r: std::result::Result<f64, String>, t: u64) {
        let mut g = self.w();
        let e = g.rtt.entry(addr).or_default();
        e.last_try = t;
        let ok = r.as_ref().ok().copied();
        match r {
            Ok(ms) => { e.ms = Some(ms); e.t_ok = t; e.ok += 1; e.last_failed = false; e.err = None; }
            Err(why) => { e.failed += 1; e.last_failed = true; e.err = Some(why); }
        }
        if let (Some(ms), Some(region)) = (ok, g.place(Some(addr.ip())).map(|p| p.region.clone())) { g.buckets.entry(region).or_default().insert(addr, (ms, t)); }
    }

    pub fn rtt_stats(&self, now: u64) -> RttStats {
        let g = self.r();
        let fresh: Vec<&SocketAddr> = g.rtt.iter().filter(|(_, r)| r.fresh(now)).map(|(a, _)| a).collect();
        let regions: std::collections::HashSet<Arc<str>> = fresh.iter().filter_map(|a| g.place(Some(a.ip())).map(|p| p.region.clone())).collect();
        let mut med = Medians::default();
        let (mut own, mut bucket) = (0, 0);
        for id in g.votes.keys() {
            match LeaderBook::rtt_of(&g, g.nodes.get(id), now, &mut med).2 { Some("quic_handshake") => own += 1, Some(_) => bucket += 1, None => {} }
        }
        RttStats { probes_ok: g.rtt.values().map(|r| r.ok).sum(), probes_failed: g.rtt.values().map(|r| r.failed).sum(), endpoints_fresh: fresh.len(),
            regions_fresh: regions.len(), validators: g.votes.len(), validators_rtt_own: own, validators_rtt_bucket: bucket }
    }

    /// validators.jsonl (MEASUREMENT §4.28): one line per validator with a vote account, at `now`. What the lines need
    /// is copied under the read lock; the JSON is made after it is released. Returns how many
    pub fn write_validators(&self, now: u64) -> usize {
        type Row = (Pk, Vote, Option<Node>, KindOf, Facts);
        let (src, rows): (String, Vec<Row>) = {
            let g = self.r();
            let list_src = g.lists.iter().find(|l| !l.is_static).or_else(|| g.lists.iter().find(|l| l.is_static)).map(|l| l.src.clone());
            let src = ["getClusterNodes", "getVoteAccounts"].iter().map(|s| s.to_string()).chain(list_src).chain(g.geo.as_ref().map(|x| format!("geo:{}", x.src)))
                .collect::<Vec<_>>().join("+");
            let mut med = Medians::default();
            let mut ids: Vec<&Pk> = g.votes.keys().collect();
            ids.sort();
            let rows = ids.into_iter().map(|id| (*id, g.votes[id].clone(), g.nodes.get(id).cloned(), LeaderBook::kind_of(&g, id, now), LeaderBook::facts(&g, id, now, &mut med))).collect();
            (src, rows)
        };
        let lines: Vec<Value> = rows.into_iter().map(|(id, v, node, (kind, kind_src, _), f)| {
            let known = kind != LeaderKind::Unknown;
            let mut m = serde_json::Map::new();
            for (k, x) in [("t_ns", json!(now)), ("identity", json!(b58(&id))), ("vote", json!(b58(&v.vote))), ("stake_lamports", json!(v.stake)), ("delinquent", json!(v.delinquent)),
                ("gossip_ip", json!(node.as_ref().and_then(|n| n.gossip).map(|a| a.to_string()))), ("version", json!(node.as_ref().and_then(|n| n.version.clone()))),
                ("client_src", json!(node.as_ref().and_then(|n| n.client_src))), ("jito", json!(known.then_some(matches!(kind, LeaderKind::Jito | LeaderKind::Bam)))),
                ("bam", json!(known.then_some(kind == LeaderKind::Bam))), ("kind", json!(kind.as_str())), ("kind_src", json!(kind_src))] { m.insert(k.into(), x); }
            f.put(&mut m);
            m.insert("src".into(), json!(src));
            Value::Object(m)
        }).collect();
        let n = lines.len();
        self.emit_lines(lines, VALIDATORS);
        n
    }

    /// the sources and their sizes (run.log, events)
    pub fn sources(&self) -> Vec<(String, usize, u64)> { self.r().lists.iter().map(|l| (l.src.clone(), l.map.len(), l.fetched_ns)).collect() }
}

/// The run's LeaderBook, for the sources that have no handle on it (the Jito result stream, send/tpu.rs)
static BOOK: std::sync::OnceLock<Arc<LeaderBook>> = std::sync::OnceLock::new();

/// make `book` the run's LeaderBook (`arbx run`, once)
pub fn install(book: Arc<LeaderBook>) { let _ = BOOK.set(book); }

/// the run's LeaderBook, when `arbx run` installed one
pub fn installed() -> Option<Arc<LeaderBook>> { BOOK.get().cloned() }

/// A validator identity named by one of our bundle results (send/jito.rs), to the run's LeaderBook if there is one
pub fn note_bundle_validator(identity: &str) { if let Some(b) = BOOK.get() { b.note_bundle_validator(identity); } }

/// the block engine's latest keep-alive RTT (f64 bits) and when it was measured
static BE_RTT_MS: AtomicU64 = AtomicU64::new(0);
static BE_RTT_NS: AtomicU64 = AtomicU64::new(0);

/// The block engine's keep-alive round trip (ms), published by the send path (send/mod.rs keep-alives of the
/// jito-bundle path: WP-05 makes this call); attempts carry it as `leader.be_rtt_ms`
pub fn note_be_rtt(ms: f64) {
    if !ms.is_finite() || ms < 0.0 { return; }
    BE_RTT_MS.store(ms.to_bits(), Ordering::Relaxed);
    BE_RTT_NS.store(now_ns(), Ordering::Relaxed);
}

/// the block engine's RTT at `now`, while it is younger than `BE_RTT_MAX_AGE_NS`
pub fn be_rtt(now: u64) -> Option<f64> {
    let t = BE_RTT_NS.load(Ordering::Relaxed);
    (t > 0 && now.saturating_sub(t) <= BE_RTT_MAX_AGE_NS).then(|| f64::from_bits(BE_RTT_MS.load(Ordering::Relaxed)))
}

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

fn pk_of(s: &str) -> Option<Pk> { bs58::decode(s).into_vec().ok().and_then(|b| Pk::try_from(b).ok()) }

/// `getSlotLeaders`' answer: a list of identities
pub fn parse_slot_leaders(v: &Value) -> Result<Vec<Pk>> {
    let list: Vec<Pk> = v.as_array().context("not a list")?.iter().map(|x| x.as_str().and_then(pk_of).context("a bad identity")).collect::<Result<_>>()?;
    if list.is_empty() { bail!("empty"); }
    Ok(list)
}

/// `getClusterNodes`' answer: per identity, the gossip IP, the TPU-QUIC address (`tpuQuic`, else `tpu` + 6), the
/// version and the client (`clientId`, else the family the version implies)
pub fn parse_cluster_nodes(v: &Value) -> Result<Vec<(Pk, Node)>> {
    let addr = |x: &Value| x.as_str().and_then(|a| a.parse::<SocketAddr>().ok());
    let mut out = Vec::new();
    for n in v.as_array().context("getClusterNodes: not a list")? {
        let Some(id) = n["pubkey"].as_str().and_then(pk_of) else { continue };
        let tpu_quic = addr(&n["tpuQuic"]).or_else(|| addr(&n["tpu"]).map(|mut a| { a.set_port(a.port().wrapping_add(6)); a }));
        let version = n["version"].as_str().map(String::from);
        let (client, client_src) = match n["clientId"].as_str().filter(|c| !c.is_empty()) {
            Some(c) => (Some(c.to_string()), Some("clientId")),
            None => match version.as_deref().and_then(client_from_version) { Some(c) => (Some(c.to_string()), Some("version")), None => (None, None) },
        };
        out.push((id, Node { gossip: addr(&n["gossip"]).map(|a| a.ip()), tpu_quic, version, client, client_src }));
    }
    if out.is_empty() { bail!("getClusterNodes: no node"); }
    Ok(out)
}

/// `getVoteAccounts`' answer (`current` and `delinquent`) by identity
pub fn parse_vote_accounts(v: &Value) -> Result<Vec<(Pk, Vote)>> {
    let mut out = Vec::new();
    for (list, delinquent) in [("current", false), ("delinquent", true)] {
        for x in v[list].as_array().into_iter().flatten() {
            let (Some(id), Some(vote)) = (x["nodePubkey"].as_str().and_then(pk_of), x["votePubkey"].as_str().and_then(pk_of)) else { continue };
            out.push((id, Vote { vote, stake: x["activatedStake"].as_u64().unwrap_or(0), delinquent }));
        }
    }
    if out.is_empty() { bail!("getVoteAccounts: no vote account"); }
    Ok(out)
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

/// When a refresh is due next: its period after a success; after the `fails`-th failure in a row 30 s, 60 s, 120 s, ...
/// up to the period (review WP-08 #8: a failure at boot must not leave the book without nodes for 10 minutes)
#[derive(Clone, Copy, Debug, Default, PartialEq)]
struct Due { next: u64, fails: u32 }

impl Due {
    fn ok(&mut self, now: u64, period: u64) { self.fails = 0; self.next = now + period; }
    fn failed(&mut self, now: u64, period: u64) {
        self.fails += 1;
        self.next = now + RETRY_FIRST_NS.saturating_mul(1u64 << (self.fails - 1).min(20)).min(period);
    }
}

/// an error for events.jsonl: its chain, with every URL cut to its host and key parameters masked (review WP-08 #4:
/// a provider's URL can carry its API key)
fn scrubbed(e: &anyhow::Error) -> String { crate::rpc::scrub(&format!("{e:#}")) }

/// The LeaderBook's refreshes, one [`Refresher::tick`] at a time (the run loop of [`start`]; tests drive it directly):
/// the validator lists every `refresh_min` (a failure keeps the older list or the fallback: `leaders_list_stale`), the
/// cluster's nodes every 10 minutes and its vote accounts every `refresh_min` (a failure of either is retried after 30 s,
/// doubling), a schedule window every 100 slots (handed to the engine as an input), the kind-update pass, and
/// validators.jsonl every 10 minutes with the RTT counts
pub struct Refresher {
    book: Arc<LeaderBook>,
    rpc: crate::rpc::Rpc,
    cfg: LeadersCfg,
    http: Option<reqwest::Client>,
    back: crossbeam_channel::Sender<crate::feeds::Event>,
    rec: Rec,
    /// the current slot (the engine's, `send::tpu::SLOT`; 0: ask `getSlot`)
    slot: Box<dyn Fn() -> u64 + Send + Sync>,
    /// per validator list (`cfg.validator_lists` order)
    lists: Vec<Due>,
    nodes: Due,
    votes: Due,
    next_validators: u64,
    fails: u32,
}

impl Refresher {
    pub fn new(book: Arc<LeaderBook>, rpc: crate::rpc::Rpc, cfg: LeadersCfg, back: crossbeam_channel::Sender<crate::feeds::Event>, rec: Rec,
        slot: Box<dyn Fn() -> u64 + Send + Sync>) -> Refresher {
        let http = reqwest::Client::builder().timeout(Duration::from_secs(20)).build().ok();
        let lists = vec![Due::default(); cfg.validator_lists.len()];
        Refresher { book, rpc, cfg, http, back, rec, slot, lists, nodes: Due::default(), votes: Due::default(), next_validators: 0, fails: 0 }
    }

    pub async fn tick(&mut self, now: u64) {
        let every = self.cfg.refresh_min.max(1) * 60 * S;
        for (i, url) in self.cfg.validator_lists.clone().iter().enumerate() {
            if now < self.lists[i].next { continue; }
            let host = crate::provenance::host_of(url);
            let got = match &self.http {
                Some(h) => match h.get(url).send().await {
                    Ok(r) if r.status().is_success() => r.json::<Value>().await.map_err(anyhow::Error::from).and_then(|v| self.book.set_list(&host, &v, now_ns())),
                    Ok(r) => Err(anyhow::anyhow!("HTTP {}", r.status().as_u16())),
                    Err(e) => Err(anyhow::anyhow!("{}", e.without_url())),
                },
                None => Err(anyhow::anyhow!("no HTTP client")),
            };
            match got {
                Ok(n) => { self.lists[i].ok(now, every); self.rec.event("leaders_refresh", "leaders", None, json!({ "src": host, "validators": n })); }
                Err(e) => {
                    self.lists[i].failed(now, every);
                    self.rec.event("leaders_list_stale", "leaders", None, json!({ "src": host, "error": scrubbed(&e), "fails": self.lists[i].fails,
                        "retry_s": (self.lists[i].next - now) / S, "using": self.book.sources().first().map(|s| s.0.clone()) }));
                }
            }
        }
        if now >= self.nodes.next {
            match self.book.refresh_nodes(&self.rpc).await {
                Ok(n) => { self.nodes.ok(now, NODES_REFRESH_NS); self.rec.event("leaders_refresh", "leaders", None, json!({ "src": "getClusterNodes", "nodes": n })); }
                Err(e) => {
                    self.nodes.failed(now, NODES_REFRESH_NS);
                    self.rec.event("leaders_list_stale", "leaders", None, json!({ "src": "getClusterNodes", "error": scrubbed(&e), "fails": self.nodes.fails,
                        "retry_s": (self.nodes.next - now) / S, "age_s": self.book.nodes_age(now).map(|a| a / S) }));
                }
            }
        }
        if now >= self.votes.next {
            match self.book.refresh_votes(&self.rpc).await {
                Ok(n) => { self.votes.ok(now, every); self.rec.event("leaders_refresh", "leaders", None, json!({ "src": "getVoteAccounts", "validators": n })); }
                Err(e) => {
                    self.votes.failed(now, every);
                    self.rec.event("leaders_list_stale", "leaders", None, json!({ "src": "getVoteAccounts", "error": scrubbed(&e), "fails": self.votes.fails,
                        "retry_s": (self.votes.next - now) / S }));
                }
            }
        }
        let mut slot = (self.slot)();
        if slot == 0 { slot = self.rpc.slot().await.unwrap_or(0); }
        if slot > 0 && self.book.due(slot) {
            match self.book.refresh_window(&self.rpc, slot).await {
                Ok(list) => { self.fails = 0; let _ = self.back.send(crate::feeds::Event::Input { kind: crate::feeds::InputKind::LeaderWindow, data: Arc::new(window_input(slot, &list)) }); }
                Err(e) => {
                    self.fails += 1;
                    if self.fails == 1 || self.fails % 30 == 0 { self.rec.event("leaders_list_stale", "leaders", None, json!({ "src": "getSlotLeaders", "error": scrubbed(&e), "fails": self.fails })); }
                }
            }
        }
        if slot > 0 && self.book.kinds_dirty() { self.book.kind_updates(slot); }
        if now >= self.next_validators && self.book.has_votes() {
            self.next_validators = now + VALIDATORS_EVERY_NS;
            let n = self.book.write_validators(now);
            self.rec.event("leaders_refresh", "leaders", None, json!({ "src": "validators.jsonl", "validators": n, "rtt": self.book.rtt_stats(now) }));
        }
    }
}

/// Run the LeaderBook's refreshes on `rt` (the background runtime) until `stop` ([`Refresher`], every 2 s), and, with
/// `[leaders] rtt_probe`, the RTT prober ([`probe_loop`])
pub fn start(book: Arc<LeaderBook>, rpc: crate::rpc::Rpc, cfg: LeadersCfg, rt: &tokio::runtime::Handle, stop: Arc<AtomicBool>,
    back: crossbeam_channel::Sender<crate::feeds::Event>, rec: Rec) {
    let slot = || crate::send::tpu::SLOT.load(Ordering::Relaxed);
    if cfg.rtt_probe {
        let (book, stop, rec, per_sec) = (book.clone(), stop.clone(), rec.clone(), cfg.rtt_per_sec);
        rt.spawn(async move {
            match crate::send::tpu::quic_client() {
                Ok(ep) => probe_loop(book, ep, per_sec, stop, Box::new(slot)).await,
                Err(e) => rec.event("leaders_list_stale", "leaders", None, json!({ "src": "rtt_probe", "error": format!("no QUIC client: {e:#}") })),
            }
        });
    }
    rt.spawn(async move {
        let mut r = Refresher::new(book, rpc, cfg, back, rec, Box::new(slot));
        while !stop.load(Ordering::Relaxed) {
            r.tick(now_ns()).await;
            tokio::time::sleep(Duration::from_secs(2)).await;
        }
    });
}

/// One QUIC handshake to `addr` on `ep` (no stream opened, no data sent; the connection is closed at once): its
/// duration in ms, or why it failed (refused, `RTT_TIMEOUT`)
pub async fn probe(ep: &quinn::Endpoint, addr: SocketAddr) -> std::result::Result<f64, String> {
    let t0 = std::time::Instant::now();
    let connecting = ep.connect(addr, "connect").map_err(|e| format!("{e}"))?;
    match tokio::time::timeout(RTT_TIMEOUT, connecting).await {
        Ok(Ok(c)) => { let ms = t0.elapsed().as_secs_f64() * 1e3; c.close(0u32.into(), b"rtt"); Ok(ms) }
        Ok(Err(e)) => Err(format!("{e}")),
        Err(_) => Err("timed out".into()),
    }
}

/// The RTT prober: every `1 / per_sec` s, one handshake to the next endpoint due ([`LeaderBook::rtt_target`]) until
/// `stop`
pub async fn probe_loop(book: Arc<LeaderBook>, ep: quinn::Endpoint, per_sec: f64, stop: Arc<AtomicBool>, slot: Box<dyn Fn() -> u64 + Send + Sync>) {
    let gap = Duration::from_secs_f64(1.0 / per_sec.clamp(0.01, 50.0));
    while !stop.load(Ordering::Relaxed) {
        let t = std::time::Instant::now();
        let s = slot();
        if s > 0 {
            if let Some(addr) = book.rtt_target(s, now_ns()) {
                let r = probe(&ep, addr).await;
                book.note_rtt(addr, r, now_ns());
            }
        }
        tokio::time::sleep(gap.saturating_sub(t.elapsed())).await;
    }
    ep.close(0u32.into(), b"stop");
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

    fn recorder(name: &str) -> (std::path::PathBuf, Rec) {
        let dir = std::env::temp_dir().join(format!("arbx-leaders-{name}-{}-{}", std::process::id(), now_ns()));
        let rec = crate::rec::start(crate::rec::Opts { dir: dir.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![], monitor: false,
            echo: Some(Box::new(std::io::sink())) }).unwrap();
        (dir, rec)
    }

    /// PLAN WP-03 acceptance: the window refresh and the kind lookup against a fake RPC. Windows are 400 slots from the
    /// current slot, the next is due 100 slots later and adds only the new slots (leaders.jsonl lines); the kind comes
    /// from the API list (bam / jito / absent = other), then our bundle results, then the static fallback; an unknown
    /// kind says why (review WP-08 #6: `no_source`, `no_schedule`)
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
        let (dir, rec) = recorder("window");
        let book = LeaderBook::new(rec.clone());
        assert!(book.due(1_000));
        let w = book.refresh_window(&rpc, 1_000).await.unwrap();
        assert_eq!(w.len(), 400);
        assert_eq!(calls.lock().unwrap()[0], ("getSlotLeaders".to_string(), json!([1_000, 400])));
        assert_eq!((book.leader(1_000), book.leader(1_004), book.leader(1_399), book.leader(1_400)), (Some(id(2)), Some(id(3)), Some(id(2)), None));
        assert!(!book.due(1_099) && book.due(1_100), "a new window every 100 slots");
        book.refresh_window(&rpc, 1_100).await.unwrap();
        assert_eq!(book.leader(1_499), Some(id(3)));
        // no list yet: unknown, and why; then the static fallback; then the API list overrides it; bundle results fill the rest
        assert_eq!(book.kind(1_000), LeaderKind::Unknown);
        assert_eq!(book.snapshot(1_000).kind_src.as_deref(), Some(NO_SOURCE), "a known leader no source names");
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
        let out = book.snapshot(5);
        assert_eq!((out.kind, out.kind_src.as_deref(), out.leader), (LeaderKind::Unknown, Some(NO_SCHEDULE), None), "a slot outside the schedule");
        // leaders.jsonl: one line per newly learned slot (400 + 100), kinds as known then
        rec.close();
        let lines = crate::rec::read_jsonl(&dir, "leaders").unwrap();
        assert_eq!(lines.len(), 500);
        assert_eq!((lines[0]["slot"].as_u64(), lines[0]["leader"].as_str(), lines[0]["kind"].as_str(), lines[0]["kind_src"].as_str()),
            (Some(1_000), Some(b58(&id(2)).as_str()), Some("unknown"), Some(NO_SOURCE)));
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

    // ------------------------------------------------------------------------------------------------ WP-08

    /// A fake HTTP server for GET requests: every request gets the current (status, body) of `state`
    async fn fake_http(state: Arc<std::sync::Mutex<(u16, String)>>) -> String {
        let l = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = l.local_addr().unwrap();
        tokio::spawn(async move {
            loop {
                let Ok((mut s, _)) = l.accept().await else { return };
                let state = state.clone();
                tokio::spawn(async move {
                    let mut buf = Vec::new();
                    let mut chunk = [0u8; 4096];
                    while !buf.windows(4).any(|w| w == b"\r\n\r\n") {
                        let Ok(n) = s.read(&mut chunk).await else { return };
                        if n == 0 { return; }
                        buf.extend_from_slice(&chunk[..n]);
                    }
                    let (status, body) = state.lock().unwrap().clone();
                    let resp = format!("HTTP/1.1 {status} X\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{body}", body.len());
                    let _ = s.write_all(resp.as_bytes()).await;
                });
            }
        });
        format!("http://{addr}/api/v1/validators")
    }

    fn node_json(id: Pk, ip: &str, tpu_port: u16, client: Option<&str>, version: &str) -> Value {
        json!({ "pubkey": b58(&id), "gossip": format!("{ip}:8001"), "tpuQuic": format!("{ip}:{tpu_port}"), "tpu": null, "version": version, "clientId": client })
    }
    fn list_json(entries: &[(Pk, bool, bool)]) -> String {
        json!({ "validators": entries.iter().map(|(id, jito, bam)| json!({ "identity_account": b58(id), "running_jito": jito, "running_bam": bam })).collect::<Vec<_>>() }).to_string()
    }
    fn shipped_geo() -> Geo { Geo::load(&std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("data/ip-geo.csv")).unwrap() }

    /// The WP-03 hand-off: the `leaders::start` loop ([`Refresher::tick`]) with a fake RPC and a fake validators API.
    /// The first tick fetches the list, the cluster's nodes and vote accounts, the window from the current slot (handed
    /// to the engine as an input) and writes validators.jsonl; a later list that changes a validator's kind makes the
    /// kind-update pass write its slots again (`kind_update`); a failed list fetch is `leaders_list_stale` and keeps the
    /// older list; the next window is due 100 slots later; a validator no list names takes its gossip client's kind
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn the_refresher_loop() {
        // leaders: slot s -> validator (s / 4 + 2) % 4 + 1 (5,000 is 1's); 1 is on the list as jito, 2 absent (gossip
        // client JitoLabs), 3 absent (plain Agave), 4 absent (Firedancer)
        let url_rpc = fake_rpc(move |m, p| match m {
            // the window from 5,200 fails (a null answer)
            "getSlotLeaders" if p[0] == json!(5_200) => Value::Null,
            "getSlotLeaders" => { let (start, n) = (p[0].as_u64().unwrap(), p[1].as_u64().unwrap()); json!((start..start + n).map(|s| b58(&id(((s / 4 + 2) % 4 + 1) as u8))).collect::<Vec<_>>()) }
            "getClusterNodes" => json!([node_json(id(1), "3.66.0.1", 8009, Some("JitoLabs"), "4.3.0"), node_json(id(2), "3.66.0.2", 8009, Some("JitoLabs"), "4.3.0"),
                node_json(id(3), "5.39.216.7", 8009, Some("Agave"), "4.2.2"), node_json(id(4), "9.9.9.9", 8009, None, "26.9.5")]),
            "getVoteAccounts" => json!({ "current": [{ "votePubkey": b58(&id(11)), "nodePubkey": b58(&id(1)), "activatedStake": 5_000_000u64 },
                { "votePubkey": b58(&id(12)), "nodePubkey": b58(&id(2)), "activatedStake": 7_000_000u64 }],
                "delinquent": [{ "votePubkey": b58(&id(13)), "nodePubkey": b58(&id(3)), "activatedStake": 1u64 }] }),
            "getSlot" => json!(0),
            _ => Value::Null,
        }).await;
        let list = Arc::new(std::sync::Mutex::new((200u16, list_json(&[(id(1), true, false)]))));
        let url_list = fake_http(list.clone()).await;
        let host = crate::provenance::host_of(&url_list);
        let (dir, rec) = recorder("loop");
        let book = LeaderBook::new(rec.clone());
        book.set_geo(shipped_geo());
        let cfg = LeadersCfg { validator_lists: vec![url_list.clone()], refresh_min: 60, ..Default::default() };
        let (tx, rx) = crossbeam_channel::unbounded();
        let slot = Arc::new(AtomicU64::new(5_000));
        let s2 = slot.clone();
        let mut r = Refresher::new(book.clone(), crate::rpc::Rpc::new(url_rpc), cfg, tx, rec.clone(), Box::new(move || s2.load(Ordering::Relaxed)));
        let t0 = now_ns();
        r.tick(t0).await;
        let inputs: Vec<crate::feeds::Event> = rx.try_iter().collect();
        assert!(matches!(&inputs[..], [crate::feeds::Event::Input { kind: crate::feeds::InputKind::LeaderWindow, data }] if data["start"] == json!(5_000)), "the window reached the engine");
        assert_eq!((book.kind(5_000), book.kind(5_004), book.kind(5_008), book.kind(5_012)), (LeaderKind::Jito, LeaderKind::Jito, LeaderKind::Other, LeaderKind::Other));
        let s = book.snapshot(5_004);
        assert_eq!((s.kind_src.as_deref(), s.client.as_deref(), s.region.as_deref(), s.city.as_deref()), (Some("gossip_client"), Some("JitoLabs"), Some("DE-Frankfurt"),
            Some("DE-Frankfurt_am_Main")), "absent from the list: the gossip client says Jito");
        assert_eq!((s.tpu_quic.as_deref(), s.tpu_region.as_deref(), s.tpu_shared_by), (Some("3.66.0.2:8009"), Some("DE-Frankfurt"), Some(1)));
        assert_eq!(book.snapshot(5_008).kind_src.as_deref(), Some(host.as_str()), "plain Agave: the list's `other`");
        assert_eq!((book.snapshot(5_012).client.as_deref(), book.snapshot(5_012).kind_src.as_deref()), (Some("Firedancer"), Some(host.as_str())),
            "a client that says nothing about Jito, from the version");
        assert_eq!(book.snapshot(5_000).next.map(|n| (n.slot, n.identity)), Some((5_004, b58(&id(2)))));
        // the same tick an hour of slots later: nothing but the window is due (100 slots on); 99 slots on, nothing
        slot.store(5_099, Ordering::Relaxed);
        r.tick(t0 + S).await;
        assert_eq!(rx.try_iter().count(), 0, "not due at +99");
        slot.store(5_100, Ordering::Relaxed);
        r.tick(t0 + 2 * S).await;
        assert_eq!(rx.try_iter().count(), 1, "due at +100");
        // a new list puts validator 3 in BAM: the kind-update pass rewrites its slots from the current one on
        *list.lock().unwrap() = (200, list_json(&[(id(1), true, false), (id(3), true, true)]));
        r.tick(t0 + 61 * 60 * S).await;
        assert_eq!(book.kind(5_104), LeaderKind::Bam);
        // the list fails: stale, the older list stays
        *list.lock().unwrap() = (500, "{}".into());
        r.tick(t0 + 122 * 60 * S).await;
        assert_eq!(book.kind(5_104), LeaderKind::Bam, "a failed fetch keeps the older list");
        // a window that cannot be fetched: `leaders_list_stale` (getSlotLeaders), still due, nothing handed to the engine
        slot.store(5_200, Ordering::Relaxed);
        r.tick(t0 + 122 * 60 * S + S).await;
        assert!(book.due(5_200) && rx.try_iter().count() == 0);
        rec.close();
        let lines = crate::rec::read_jsonl(&dir, "leaders").unwrap();
        let learned = lines.iter().filter(|l| l["event"] == "learned").count();
        let updates: Vec<&Value> = lines.iter().filter(|l| l["event"] == "kind_update").collect();
        assert_eq!(learned, 500, "400 + 100 slots learned");
        // validator 3 leads 4 slots in every 16: those from 5,100 on in the two windows (5,100..5,500): 100 slots
        assert_eq!(updates.len(), 100, "{:?}", updates.first());
        assert!(updates.iter().all(|l| l["leader"] == json!(b58(&id(3))) && l["kind"] == "bam" && l["slot"].as_u64().unwrap() >= 5_100));
        let first = lines.iter().find(|l| l["slot"] == json!(5_004)).unwrap();
        assert_eq!((first["region"].as_str(), first["city"].as_str(), first["client"].as_str(), first["kind_src"].as_str(), first["tpu_quic"].as_str()),
            (Some("DE-Frankfurt"), Some("DE-Frankfurt_am_Main"), Some("JitoLabs"), Some("gossip_client"), Some("3.66.0.2:8009")));
        let ev = crate::rec::read_jsonl(&dir, "events").unwrap();
        let srcs: Vec<(String, String)> = ev.iter().filter(|e| e["kind"].as_str().is_some_and(|k| k.starts_with("leaders_")))
            .map(|e| (e["kind"].as_str().unwrap().to_string(), e["detail"]["src"].as_str().unwrap_or("").to_string())).collect();
        for want in [("leaders_refresh", host.as_str()), ("leaders_refresh", "getClusterNodes"), ("leaders_refresh", "getVoteAccounts"), ("leaders_refresh", "validators.jsonl"),
            ("leaders_list_stale", host.as_str()), ("leaders_list_stale", "getSlotLeaders")] {
            assert!(srcs.contains(&(want.0.to_string(), want.1.to_string())), "{want:?} in {srcs:?}");
        }
        let stale = ev.iter().find(|e| e["kind"] == "leaders_list_stale").unwrap();
        assert_eq!((stale["detail"]["using"].as_str(), stale["detail"]["fails"].as_u64(), stale["detail"]["retry_s"].as_u64()), (Some(host.as_str()), Some(1), Some(30)),
            "a failed list is tried again after 30 s");
        let snap = ev.iter().find(|e| e["kind"] == "leaders_refresh" && e["detail"]["src"] == "validators.jsonl").unwrap();
        assert_eq!(snap["detail"]["rtt"]["validators"].as_u64(), Some(3), "the RTT counts: {snap}");
        // validators.jsonl: one line per vote account (the delinquent one too), with the node's and the kind's fields,
        // every 10 minutes (here: the first tick, an hour and two hours later)
        let vl = crate::rec::read_jsonl(&dir, "validators").unwrap();
        assert_eq!(vl.len(), 9, "three snapshots of three validators");
        let v1 = vl.iter().find(|l| l["identity"] == json!(b58(&id(1)))).unwrap();
        assert_eq!((v1["vote"].as_str(), v1["stake_lamports"].as_u64(), v1["tpu_quic"].as_str(), v1["client"].as_str(), v1["jito"].as_bool(), v1["bam"].as_bool()),
            (Some(b58(&id(11)).as_str()), Some(5_000_000), Some("3.66.0.1:8009"), Some("JitoLabs"), Some(true), Some(false)));
        assert_eq!((v1["region"].as_str(), v1["city"].as_str(), v1["tpu_region"].as_str(), v1["tpu_shared_by"].as_u64(), v1["gossip_ip"].as_str()),
            (Some("DE-Frankfurt"), Some("DE-Frankfurt_am_Main"), Some("DE-Frankfurt"), Some(1), Some("3.66.0.1")));
        assert_eq!(v1["src"].as_str(), Some(format!("getClusterNodes+getVoteAccounts+{host}+geo:ip-geo.csv").as_str()));
        assert!(vl.iter().any(|l| l["identity"] == json!(b58(&id(3))) && l["delinquent"] == json!(true)));
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// Review WP-08 #8 and #4: a failed getClusterNodes or getVoteAccounts is tried again after 30 s, then 60 s, ...
    /// (not after its 10- or 60-minute period), and only a success sets the long period again; validators.jsonl comes
    /// as soon as the vote accounts do. An RPC error that names the provider's URL reaches events.jsonl with the URL cut
    /// to its host and the key masked
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn failed_refreshes_are_tried_again_soon_and_errors_are_scrubbed() {
        let calls = Arc::new(std::sync::Mutex::new(HashMap::<String, u32>::new()));
        let c2 = calls.clone();
        let url = fake_rpc(move |m, _| {
            let n = { let mut c = c2.lock().unwrap(); let n = c.entry(m.to_string()).or_default(); *n += 1; *n };
            match m {
                // the nodes fail twice, the vote accounts once (a null answer does not parse)
                "getClusterNodes" if n <= 2 => Value::Null,
                "getClusterNodes" => json!([node_json(id(1), "3.66.0.1", 8009, Some("JitoLabs"), "4.3.0")]),
                "getVoteAccounts" if n <= 1 => Value::Null,
                "getVoteAccounts" => json!({ "current": [{ "votePubkey": b58(&id(11)), "nodePubkey": b58(&id(1)), "activatedStake": 5u64 }] }),
                _ => Value::Null,
            }
        }).await;
        let (dir, rec) = recorder("retry");
        let book = LeaderBook::new(rec.clone());
        let cfg = LeadersCfg { validator_lists: vec![], refresh_min: 60, ..Default::default() };
        let (tx, _rx) = crossbeam_channel::unbounded();
        let mut r = Refresher::new(book.clone(), crate::rpc::Rpc::new(url), cfg.clone(), tx.clone(), rec.clone(), Box::new(|| 0));
        let t0 = now_ns();
        let n = |m: &str| calls.lock().unwrap().get(m).copied().unwrap_or(0);
        r.tick(t0).await;
        assert_eq!((n("getClusterNodes"), n("getVoteAccounts"), book.nodes_age(t0), book.has_votes()), (1, 1, None, false));
        r.tick(t0 + 29 * S).await;
        assert_eq!((n("getClusterNodes"), n("getVoteAccounts")), (1, 1), "not before 30 s");
        r.tick(t0 + 30 * S).await;
        assert_eq!((n("getClusterNodes"), n("getVoteAccounts"), book.has_votes()), (2, 2, true), "both again at 30 s; the votes came");
        r.tick(t0 + 89 * S).await;
        assert_eq!(n("getClusterNodes"), 2, "the second failure waits 60 s");
        r.tick(t0 + 90 * S).await;
        assert_eq!((n("getClusterNodes"), book.nodes_age(t0 + 90 * S).is_some()), (3, true));
        r.tick(t0 + 90 * S + NODES_REFRESH_NS - S).await;
        assert_eq!((n("getClusterNodes"), n("getVoteAccounts")), (3, 2), "a success sets the long periods again");
        r.tick(t0 + 90 * S + NODES_REFRESH_NS).await;
        assert_eq!((n("getClusterNodes"), n("getVoteAccounts")), (4, 2), "the nodes 10 minutes after their success");
        // an RPC whose URL carries a key, and that refuses: the events name its host, never the key
        let closed = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = closed.local_addr().unwrap().port();
        drop(closed);
        let mut bad = Refresher::new(LeaderBook::new(rec.clone()), crate::rpc::Rpc::new(format!("http://127.0.0.1:{port}/rpc?api-key=SECRET123")), cfg, tx, rec.clone(),
            Box::new(|| 7));
        bad.tick(t0).await;
        rec.close();
        let ev = crate::rec::read_jsonl(&dir, "events").unwrap();
        let stale: Vec<&Value> = ev.iter().filter(|e| e["kind"] == "leaders_list_stale").collect();
        let first = stale.iter().find(|e| e["detail"]["src"] == "getClusterNodes").unwrap();
        assert_eq!((first["detail"]["fails"].as_u64(), first["detail"]["retry_s"].as_u64()), (Some(1), Some(30)));
        let second = stale.iter().filter(|e| e["detail"]["src"] == "getClusterNodes").nth(1).unwrap();
        assert_eq!((second["detail"]["fails"].as_u64(), second["detail"]["retry_s"].as_u64()), (Some(2), Some(60)));
        let refused: Vec<String> = stale.iter().map(|e| e["detail"]["error"].as_str().unwrap_or("").to_string()).filter(|e| e.contains(&format!("127.0.0.1:{port}"))).collect();
        assert!(refused.len() >= 3, "getClusterNodes, getVoteAccounts and getSlotLeaders failed against the closed port: {stale:?}");
        assert!(stale.iter().all(|e| !e.to_string().contains("SECRET123")), "no key in events.jsonl: {stale:?}");
        let vl = crate::rec::read_jsonl(&dir, "validators").unwrap();
        let ts: Vec<u64> = vl.iter().map(|l| l["t_ns"].as_u64().unwrap()).collect();
        assert_eq!(ts, vec![t0 + 30 * S, t0 + 90 * S + NODES_REFRESH_NS - S], "validators.jsonl as soon as the vote accounts came, then 10 minutes on");
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// `start` itself (the WP-03 hand-off): it runs the refresher on the given runtime until `stop` (the window reaches
    /// the engine's channel; the current slot from `send::tpu::SLOT`, else `getSlot`), and stops when asked
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn start_runs_the_refresher_until_stop() {
        let url = fake_rpc(|m, p| match m {
            "getSlot" => json!(7_000),
            "getSlotLeaders" => json!((0..p[1].as_u64().unwrap()).map(|_| b58(&id(1))).collect::<Vec<_>>()),
            "getClusterNodes" => json!([node_json(id(1), "127.0.0.1", 9, Some("JitoLabs"), "4.3.0")]),
            "getVoteAccounts" => json!({ "current": [{ "votePubkey": b58(&id(9)), "nodePubkey": b58(&id(1)), "activatedStake": 1u64 }] }),
            _ => Value::Null,
        }).await;
        let book = LeaderBook::new(Rec::off());
        let (tx, rx) = crossbeam_channel::unbounded();
        let stop = Arc::new(AtomicBool::new(false));
        // no prober here (the RTT test drives it): the shared current slot may be another test's
        let cfg = LeadersCfg { validator_lists: vec![], rtt_probe: false, ..Default::default() };
        start(book.clone(), crate::rpc::Rpc::new(url), cfg, &tokio::runtime::Handle::current(), stop.clone(), tx, Rec::off());
        let deadline = std::time::Instant::now() + Duration::from_secs(10);
        let ev = loop {
            if let Ok(e) = rx.try_recv() { break Some(e); }
            if std::time::Instant::now() > deadline { break None; }
            tokio::time::sleep(Duration::from_millis(20)).await;
        };
        assert!(matches!(ev, Some(crate::feeds::Event::Input { kind: crate::feeds::InputKind::LeaderWindow, .. })), "a window reached the engine");
        assert!(book.nodes_age(now_ns()).is_some(), "the node table was fetched");
        stop.store(true, Ordering::Relaxed);
        tokio::time::sleep(Duration::from_millis(2_300)).await;
        let n = rx.try_iter().count();
        tokio::time::sleep(Duration::from_millis(2_300)).await;
        assert_eq!(rx.try_iter().count() + n, n, "stopped: nothing more after the stop");
    }

    /// a QUIC server like a leader's TPU (ALPN solana-tpu, any client): counts handshakes and the streams opened
    fn fake_tpu() -> (SocketAddr, Arc<AtomicU64>, Arc<AtomicU64>) {
        let provider = Arc::new(rustls::crypto::ring::default_provider());
        let key = rcgen::KeyPair::generate_for(&rcgen::PKCS_ECDSA_P256_SHA256).unwrap();
        let cert = rcgen::CertificateParams::new(vec!["solana".to_string()]).unwrap().self_signed(&key).unwrap();
        let mut tls = rustls::ServerConfig::builder_with_provider(provider).with_protocol_versions(&[&rustls::version::TLS13]).unwrap()
            .with_no_client_auth().with_single_cert(vec![cert.der().clone()], rustls::pki_types::PrivateKeyDer::Pkcs8(key.serialize_der().into())).unwrap();
        tls.alpn_protocols = vec![b"solana-tpu".to_vec()];
        let sc = quinn::ServerConfig::with_crypto(Arc::new(quinn::crypto::rustls::QuicServerConfig::try_from(tls).unwrap()));
        let ep = quinn::Endpoint::server(sc, "127.0.0.1:0".parse().unwrap()).unwrap();
        let addr = ep.local_addr().unwrap();
        let (hs, streams) = (Arc::new(AtomicU64::new(0)), Arc::new(AtomicU64::new(0)));
        let (h2, s2) = (hs.clone(), streams.clone());
        tokio::spawn(async move {
            while let Some(inc) = ep.accept().await {
                let (h3, s3) = (h2.clone(), s2.clone());
                tokio::spawn(async move {
                    let Ok(c) = inc.await else { return };
                    h3.fetch_add(1, Ordering::Relaxed);
                    tokio::select! { r = c.accept_uni() => if r.is_ok() { s3.fetch_add(1, Ordering::Relaxed); }, r = c.accept_bi() => if r.is_ok() { s3.fetch_add(1, Ordering::Relaxed); } }
                });
            }
        });
        (addr, hs, streams)
    }

    /// PLAN WP-08 acceptance: RTT bookkeeping with a fake QUIC endpoint, per endpoint (review WP-08 #3). The endpoints of
    /// the next leaders are measured one at a time (a handshake, no stream, no data); two validators announcing one
    /// endpoint (a shared ingress node) are measured once and both carry its RTT; an endpoint that does not answer fails
    /// after the timeout and its validators take the median RTT of their endpoint's region (`region_bucket`), never of
    /// their gossip region: a validator placed in one region whose endpoint is in another takes the endpoint's region,
    /// and one whose endpoint's region has no sample has no RTT although its gossip region has one; a validator without
    /// an endpoint takes its gossip region's; an endpoint measured is due again after 5 minutes, a failed one after 1;
    /// an RTT older than 10 minutes is dropped; the prober loop measures by itself
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn rtt_bookkeeping_with_a_fake_quic_endpoint() {
        let (addr, handshakes, streams) = fake_tpu();
        // a UDP port that never answers
        let silent = std::net::UdpSocket::bind("127.0.0.1:0").unwrap();
        let silent_addr = silent.local_addr().unwrap();
        let book = LeaderBook::new(Rec::off());
        book.set_geo(Geo::parse("ip_start,ip_end,country,stateprov,city\n10.0.0.0,10.255.255.255,XX,There,Elsewhere\n127.0.0.0,127.255.255.255,ZZ,Loop,\"Loopback (Lo 1)\"\n", "test.csv").unwrap());
        let node = |tpu: Option<SocketAddr>, ip: &str| Node { gossip: Some(ip.parse().unwrap()), tpu_quic: tpu, version: Some("4.3.0".into()), client: Some("Agave".into()), client_src: Some("clientId") };
        let far: SocketAddr = "10.0.0.9:8009".parse().unwrap();
        // 1 and 4 share the answering endpoint; 2 does not answer; 3 has no endpoint; 5 is placed elsewhere with the
        // silent loopback endpoint; 6 is placed on the loopback with an endpoint elsewhere (never measured)
        book.set_nodes(vec![(id(1), node(Some(addr), "127.0.0.1")), (id(2), node(Some(silent_addr), "127.0.0.2")), (id(3), node(None, "127.0.0.3")),
            (id(4), node(Some(addr), "127.0.0.4")), (id(5), node(Some(silent_addr), "10.0.0.5")), (id(6), node(Some(far), "127.0.0.6"))], now_ns());
        book.set_votes((1..=6).map(|n| (id(n), Vote { vote: id(100 + n), stake: 1, delinquent: false })).collect(), now_ns());
        book.add_window(100, &[1u8, 1, 1, 1, 4, 4, 4, 4, 2, 2, 2, 2, 3, 3, 3, 3, 5, 5, 5, 5, 6, 6, 6, 6].map(id));
        let ep = crate::send::tpu::quic_client().unwrap();
        let t = now_ns();
        let a = book.rtt_target(100, t).unwrap();
        assert_eq!(a, addr, "the first leader's endpoint");
        let r = probe(&ep, a).await;
        let ms = *r.as_ref().expect("the handshake completes");
        assert!(ms > 0.0 && ms < 1_000.0, "{ms}");
        book.note_rtt(a, r, t);
        let b = book.rtt_target(100, t).unwrap();
        assert_eq!(b, silent_addr, "4 shares 1's endpoint, measured already: 2's is next");
        let r = probe(&ep, b).await;
        assert_eq!(r, Err("timed out".to_string()));
        book.note_rtt(b, r, t);
        let c = book.rtt_target(100, t).unwrap();
        assert_eq!(c, far, "3 has no endpoint, 5 shares 2's: 6's is next");
        book.note_rtt(c, Err("refused".into()), t);
        assert_eq!(book.rtt_target(100, t + S), None, "every endpoint tried within the minute");
        assert_eq!(book.rtt_target(100, t + 61 * S), Some(silent_addr), "a failed one is tried again after a minute");
        assert_eq!(book.rtt_target(100, t + 301 * S), Some(addr), "a measured one after five");
        let snap = |slot: u64| { let s = book.snapshot_at(slot, t + 10 * S); (s.rtt_ms, s.rtt_src, s.region, s.tpu_region, s.tpu_shared_by) };
        let (own, bucket) = (Some("quic_handshake".to_string()), Some("region_bucket".to_string()));
        let (zz, xx) = (Some("ZZ-Loopback".to_string()), Some("XX-Elsewhere".to_string()));
        assert_eq!(snap(100), (Some(ms), own.clone(), zz.clone(), zz.clone(), Some(2)));
        assert_eq!(snap(104), (Some(ms), own, zz.clone(), zz.clone(), Some(2)), "a shared endpoint's RTT is every validator's behind it");
        assert_eq!(snap(108), (Some(ms), bucket.clone(), zz.clone(), zz.clone(), Some(2)), "its endpoint failed: the endpoint region's median");
        assert_eq!(snap(112), (Some(ms), bucket.clone(), zz.clone(), None, None), "no endpoint: its gossip region's");
        assert_eq!(snap(116), (Some(ms), bucket, xx.clone(), zz.clone(), Some(2)), "placed elsewhere, its endpoint on the loopback: the loopback's");
        assert_eq!(snap(120), (None, None, zz, xx, Some(1)), "its endpoint's region has no sample: none, though its gossip region has one");
        assert_eq!(book.snapshot_at(100, t + 10 * S).rtt_age_s, Some(10));
        assert_eq!(book.snapshot_at(100, t + 601 * S).rtt_ms, None, "older than 10 minutes");
        assert_eq!(book.rtt_stats(t + 10 * S), RttStats { probes_ok: 1, probes_failed: 2, endpoints_fresh: 1, regions_fresh: 1, validators: 6, validators_rtt_own: 2,
            validators_rtt_bucket: 3 });
        // the prober loop on its own: a fresh book, two validators behind one endpoint, 20 handshakes a second at most,
        // stopped once it measured: one handshake for both
        let book2 = LeaderBook::new(Rec::off());
        book2.set_nodes(vec![(id(1), node(Some(addr), "127.0.0.1")), (id(4), node(Some(addr), "127.0.0.4"))], now_ns());
        book2.add_window(100, &[id(1), id(1), id(4), id(4)]);
        let stop = Arc::new(AtomicBool::new(false));
        let h = tokio::spawn(probe_loop(book2.clone(), crate::send::tpu::quic_client().unwrap(), 20.0, stop.clone(), Box::new(|| 100)));
        let deadline = std::time::Instant::now() + Duration::from_secs(5);
        while book2.rtt_stats(now_ns()).probes_ok == 0 && std::time::Instant::now() < deadline { tokio::time::sleep(Duration::from_millis(20)).await; }
        tokio::time::sleep(Duration::from_millis(300)).await;
        stop.store(true, Ordering::Relaxed);
        h.await.unwrap();
        let st = book2.rtt_stats(now_ns());
        assert_eq!((st.probes_ok, st.probes_failed, st.endpoints_fresh), (1, 0, 1), "one endpoint, measured once (not due again for 5 minutes)");
        assert_eq!((book2.snapshot(100).rtt_src.as_deref(), book2.snapshot(102).rtt_src.as_deref()), (Some("quic_handshake"), Some("quic_handshake")));
        tokio::time::sleep(Duration::from_millis(100)).await;
        assert_eq!((handshakes.load(Ordering::Relaxed), streams.load(Ordering::Relaxed)), (2, 0), "two handshakes, no stream: no data sent");
        drop(silent);
    }

    /// Review WP-08 #11: the TPU path's targets (`next_leaders`): the distinct leaders from the current slot on, leaders
    /// without a TPU-QUIC address left out, at most `n`; a window filled by the TPU path (`fill_window`) adds its slots to
    /// the schedule (and leaders.jsonl) without moving the refresher's window
    #[test]
    fn next_leaders_and_fill_window() {
        let (dir, rec) = recorder("tpu");
        let book = LeaderBook::new(rec.clone());
        let a = |p: u16| -> SocketAddr { format!("10.0.0.1:{p}").parse().unwrap() };
        let node = |tpu: Option<SocketAddr>| Node { tpu_quic: tpu, ..Default::default() };
        book.set_nodes(vec![(id(1), node(Some(a(1)))), (id(2), node(Some(a(2)))), (id(3), node(None)), (id(4), node(Some(a(4))))], now_ns());
        assert!(book.next_leaders(0, 4).is_empty(), "no schedule");
        // slots 50..: 1 1 2 2 3 3 1 1 4 4
        assert_eq!(book.fill_window(50, &[1u8, 1, 2, 2, 3, 3, 1, 1, 4, 4].map(id)), 10);
        assert!(book.due(50) && book.due(10_000), "the refresher's window did not move");
        assert_eq!(book.next_leaders(50, 10), vec![(id(1), a(1)), (id(2), a(2)), (id(4), a(4))], "distinct, 3 has no address");
        assert_eq!(book.next_leaders(50, 2), vec![(id(1), a(1)), (id(2), a(2))], "at most n");
        assert_eq!(book.next_leaders(54, 10), vec![(id(1), a(1)), (id(4), a(4))], "from the slot on");
        assert_eq!(book.next_leaders(59, 10), vec![(id(4), a(4))]);
        assert!(book.next_leaders(60, 10).is_empty() && book.next_leaders(50, 0).is_empty());
        // the same window again adds nothing; the refresher's own window does move it
        assert_eq!(book.fill_window(50, &[1u8, 1, 2, 2, 3, 3, 1, 1, 4, 4].map(id)), 0);
        book.add_window(60, &[id(2)]);
        assert!(!book.due(60) && book.due(160));
        rec.close();
        let lines = crate::rec::read_jsonl(&dir, "leaders").unwrap();
        assert_eq!(lines.len(), 11, "the TPU path's slots are learned too");
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// The offline geo table: quoted fields, comments, the city (country, city without its district) and the region
    /// (its metro, else the city), longest match by range, IPv6 has none; the shipped data/ip-geo.csv loads and places
    /// a Frankfurt validator; every metro city is in the shipped table, in one metro only (review WP-08 #9)
    #[test]
    fn the_geo_table() {
        let g = Geo::parse("# c\nip_start,ip_end,country,stateprov,city\n10.0.0.0,10.0.0.255,DE,Hesse,\"Frankfurt am Main (Innenstadt I)\"\n10.0.1.0,10.0.1.255,US,\"New York\",\"New York\"\n10.0.2.0,10.0.2.255,ZZ,,\n10.0.4.0,10.0.4.255,DE,Hesse,Offenbach\n", "t").unwrap();
        assert_eq!(g.len(), 4);
        let r = |ip: &str| g.place(ip.parse().unwrap()).map(|x| (x.region.to_string(), x.city.to_string()));
        let p = |a: &str, b: &str| Some((a.to_string(), b.to_string()));
        assert_eq!((r("10.0.0.7"), r("10.0.1.255"), r("10.0.2.1"), r("10.0.4.1")),
            (p("DE-Frankfurt", "DE-Frankfurt_am_Main"), p("US-New_York", "US-New_York"), p("ZZ", "ZZ"), p("DE-Frankfurt", "DE-Offenbach")));
        assert_eq!((r("10.0.3.1"), r("9.255.255.255"), r("::1")), (None, None, None));
        assert_eq!(g.counts(), (3, 4), "Frankfurt and Offenbach are one region");
        assert!(Geo::parse("ip_start,ip_end,country,stateprov,city\n10.0.0.0,10.0.0.255,DE,a,b\n10.0.0.9,10.0.1.255,DE,a,b\n", "t").is_err(), "overlap");
        assert_eq!(split_csv("a,\"b, \"\"c\"\"\",d"), vec!["a", "b, \"c\"", "d"]);
        let shipped = shipped_geo();
        assert!(shipped.len() > 800, "{}", shipped.len());
        let f = shipped.place("3.66.0.1".parse().unwrap()).unwrap();
        assert_eq!((&*f.region, &*f.city), ("DE-Frankfurt", "DE-Frankfurt_am_Main"));
        let cities: std::collections::HashSet<String> = shipped.ranges.iter().map(|x| x.2.city.to_string()).collect();
        let mut seen = std::collections::HashSet::new();
        for (m, cs) in METROS {
            assert!(cs.len() >= 2, "{m}");
            for c in *cs { assert!(cities.contains(*c), "{m}: {c} is not a city of the shipped table"); assert!(seen.insert(*c), "{c} in two metros"); }
        }
        // the 2026-10-04 table: 195 cities in 132 regions
        assert_eq!(shipped.counts(), (132, 195));
    }

    /// getClusterNodes / getVoteAccounts: the client from `clientId`, else from the version; the TPU-QUIC address, else
    /// TPU + 6; delinquent vote accounts kept
    #[test]
    fn cluster_nodes_and_vote_accounts() {
        let v = json!([{ "pubkey": b58(&id(1)), "gossip": "1.2.3.4:8001", "tpuQuic": "1.2.3.4:8009", "version": "4.3.0", "clientId": "AgaveBam" },
            { "pubkey": b58(&id(2)), "gossip": "1.2.3.5:8001", "tpuQuic": null, "tpu": "1.2.3.5:8003", "version": "0.1106.40201", "clientId": null },
            { "pubkey": b58(&id(3)), "gossip": null, "version": null }, { "pubkey": "bad" }]);
        let n: HashMap<Pk, Node> = parse_cluster_nodes(&v).unwrap().into_iter().collect();
        assert_eq!(n.len(), 3);
        assert_eq!(n[&id(1)], Node { gossip: Some("1.2.3.4".parse().unwrap()), tpu_quic: Some("1.2.3.4:8009".parse().unwrap()), version: Some("4.3.0".into()),
            client: Some("AgaveBam".into()), client_src: Some("clientId") });
        assert_eq!((n[&id(2)].tpu_quic, n[&id(2)].client.as_deref(), n[&id(2)].client_src), (Some("1.2.3.5:8009".parse().unwrap()), Some("Frankendancer"), Some("version")));
        assert_eq!((n[&id(3)].gossip, n[&id(3)].client.clone()), (None, None));
        assert_eq!((client_from_version("26.9.5"), client_from_version("4.2.2"), client_from_version("x")), (Some("Firedancer"), Some("Agave"), None));
        let votes = parse_vote_accounts(&json!({ "current": [{ "nodePubkey": b58(&id(1)), "votePubkey": b58(&id(9)), "activatedStake": 42u64 }],
            "delinquent": [{ "nodePubkey": b58(&id(2)), "votePubkey": b58(&id(8)), "activatedStake": 0u64 }] })).unwrap();
        assert_eq!(votes, vec![(id(1), Vote { vote: id(9), stake: 42, delinquent: false }), (id(2), Vote { vote: id(8), stake: 0, delinquent: true })]);
        assert!(parse_cluster_nodes(&json!([])).is_err() && parse_vote_accounts(&json!({})).is_err());
    }

    /// Real answers (testdata/leaders/cluster-sample.json: getClusterNodes and getVoteAccounts from the public endpoint,
    /// 2026-10-04, one validator per gossip client): every client parses with its `clientId`, every gossip address has
    /// a region in the shipped geo table, the vote accounts (a delinquent one too) parse, the gossip client gives the
    /// kinds it can, and validators.jsonl writes one line per vote account. The HarmonicAgave validator CAo1dCGY is
    /// placed in Michigan by its gossip IP but announces a London TPU endpoint (review WP-08 #3: `region` and
    /// `tpu_region` differ); the JitoLabs one Fd7btgyS sits in Limburg an der Lahn with a Frankfurt endpoint, one metro
    #[test]
    fn real_cluster_answers() {
        let f: Value = serde_json::from_str(&std::fs::read_to_string(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/leaders/cluster-sample.json")).unwrap()).unwrap();
        let nodes = parse_cluster_nodes(&f["getClusterNodes"]).unwrap();
        assert_eq!(nodes.len(), 12);
        let clients: Vec<&str> = nodes.iter().filter_map(|(_, n)| n.client.as_deref()).collect();
        for c in ["Agave", "JitoLabs", "AgaveBam", "Firedancer", "Frankendancer", "HarmonicAgave", "FireBAM", "Rakurai", "HarmonicFiredancer", "Raiku", "Unknown(38813)"] {
            assert!(clients.contains(&c), "{c} in {clients:?}");
        }
        assert!(nodes.iter().all(|(_, n)| n.client_src == Some("clientId")));
        assert_eq!(nodes.iter().filter(|(_, n)| n.tpu_quic.is_none()).count(), 1, "one node announces no TPU-QUIC address");
        let geo = shipped_geo();
        for (id, n) in &nodes { assert!(geo.place(n.gossip.unwrap()).is_some(), "{} {:?}", b58(id), n.gossip); }
        let votes = parse_vote_accounts(&f["getVoteAccounts"]).unwrap();
        assert_eq!((votes.len(), votes.iter().filter(|v| v.1.delinquent).count()), (11, 1));
        let (dir, rec) = recorder("real");
        let book = LeaderBook::new(rec.clone());
        book.set_geo(geo);
        book.set_nodes(nodes.clone(), now_ns());
        book.set_votes(votes, now_ns());
        assert_eq!(book.write_validators(now_ns()), 11);
        rec.close();
        let vl = crate::rec::read_jsonl(&dir, "validators").unwrap();
        let kind = |c: &str| vl.iter().find(|l| l["client"] == json!(c)).map(|l| (l["kind"].as_str().unwrap().to_string(), l["kind_src"].as_str().map(String::from)));
        assert_eq!(kind("JitoLabs"), Some(("jito".into(), Some("gossip_client".into()))));
        assert_eq!((kind("AgaveBam").unwrap().0, kind("FireBAM").unwrap().0), ("bam".to_string(), "bam".to_string()));
        assert_eq!(kind("Rakurai"), Some(("unknown".to_string(), Some(NO_SOURCE.to_string()))), "no source names it, and the line says so");
        assert!(vl.iter().all(|l| l["region"].is_string() || l["gossip_ip"].is_null()), "every validator in the cluster sample has a region");
        let by = |p: &str| vl.iter().find(|l| l["identity"].as_str().is_some_and(|i| i.starts_with(p))).unwrap();
        let h = by("CAo1dCGY");
        assert_eq!((h["region"].as_str(), h["city"].as_str(), h["tpu_quic"].as_str(), h["tpu_region"].as_str()), (Some("US-Delta_Mills"), Some("US-Delta_Mills"),
            Some("64.130.46.242:9007"), Some("GB-London")));
        let j = by("Fd7btgyS");
        assert_eq!((j["region"].as_str(), j["city"].as_str(), j["tpu_region"].as_str(), j["tpu_shared_by"].as_u64()), (Some("DE-Frankfurt"), Some("DE-Limburg_an_der_Lahn"),
            Some("DE-Frankfurt"), Some(1)));
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// The gossip client is a kind source only for a validator no list names: JitoLabs -> jito, AgaveBam / FireBAM -> bam,
    /// plain Agave -> other; a list's verdict and our bundle results outrank it; without any list it still names them
    #[test]
    fn kinds_from_gossip_clients() {
        let book = LeaderBook::new(Rec::off());
        let node = |c: &str| Node { client: Some(c.into()), client_src: Some("clientId"), ..Default::default() };
        book.set_nodes(vec![(id(1), node("JitoLabs")), (id(2), node("FireBAM")), (id(3), node("Agave")), (id(4), node("HarmonicAgave")), (id(5), node("JitoLabs"))], now_ns());
        book.add_window(10, &[id(1), id(2), id(3), id(4), id(5), id(6)]);
        let k = |s: u64| { let x = book.snapshot(s); (x.kind, x.kind_src) };
        // no list: gossip names 1-3; HarmonicAgave and an unknown node stay unknown (no source names them)
        assert_eq!((k(10), k(11), k(12)), ((LeaderKind::Jito, Some("gossip_client".into())), (LeaderKind::Bam, Some("gossip_client".into())), (LeaderKind::Other, Some("gossip_client".into()))));
        assert_eq!((k(13), k(15)), ((LeaderKind::Unknown, Some(NO_SOURCE.into())), (LeaderKind::Unknown, Some(NO_SOURCE.into()))));
        // a list naming 5 as running neither wins over its JitoLabs client; absent 1 keeps its gossip kind
        book.set_list("kobe", &json!({ "validators": [{ "identity_account": b58(&id(5)), "running_jito": false, "running_bam": false }] }), now_ns()).unwrap();
        assert_eq!((k(14), k(10).0, k(12)), ((LeaderKind::Other, Some("kobe".into())), LeaderKind::Jito, (LeaderKind::Other, Some("kobe".into()))));
        // a version-derived client is no evidence
        book.set_nodes(vec![(id(1), Node { client: Some("Agave".into()), client_src: Some("version"), ..Default::default() })], now_ns());
        assert_eq!(k(10), (LeaderKind::Other, Some("kobe".into())));
        // the kind-update pass: every slot's kind (or source) changed since it was learned; a second pass finds none
        assert!(book.kinds_dirty());
        assert_eq!(book.kind_updates(0), 6);
        assert!(!book.kinds_dirty());
        assert_eq!(book.kind_updates(0), 0);
    }

    /// The snapshot carries the block engine's keep-alive RTT while it is fresh
    #[test]
    fn the_block_engine_rtt() {
        let book = LeaderBook::new(Rec::off());
        book.add_window(1, &[id(1)]);
        note_be_rtt(f64::NAN);
        note_be_rtt(12.5);
        let t = now_ns();
        assert_eq!(book.snapshot_at(1, t).be_rtt_ms, Some(12.5));
        assert_eq!(book.snapshot_at(1, t + BE_RTT_MAX_AGE_NS + S).be_rtt_ms, None, "stale");
    }
}
