//! WP-22: the automatic pool refresh (PLAN-ADDENDUM "WP-22: Automatic pool refresh"; FT-008).
//!
//! `arbx pools refresh` builds the next seed list (`venue,pool,source`) from the current one, the previous segments'
//! records and the public trending lists, and writes it with a JSON report (what was added, dropped and kept, with
//! reasons, sources, timings and each source's fetch status) and an inputs file (everything the plan read: the list, the
//! records' counts, the candidates, every account fetched), so the same inputs give the same list (`--inputs`).
//!
//! - **Sources.** Our records (each segment directory's triggers, decisions, opportunities and rivals per listed pool;
//!   the exec records of rival arbitrage, `arb_like`, for pools we do not list: the pool account of every swap on our
//!   venues, top-level or inner, read at the decoders' positions); GeckoTerminal's `trending_pools` (5m, 1h, 6h) and
//!   `new_pools`; DexScreener's `token-pairs` for each candidate token (its full pool set). Never GMGN.
//! - **Rules.** Our five venues only; quote WSOL (or USDC when `[pool_refresh] quotes` names it). Every pool added is
//!   verified on chain (getMultipleAccounts through the configured non-Haan RPC): the account exists, its owner is the
//!   venue's program, it decodes with the engine's own decoder (`pools::meta_of`, the boot's), its mints are the ones the
//!   source named, its quote vault (a token account of the quote mint) holds at least the minimum, and its mints pass
//!   the boot's Token-2022 refusals (`pools::apply_mints`). A token enters only with 2+ verified pools of one quote on
//!   our venues, counting pools already listed (the list and the registry). Listed pools whose account is gone (or
//!   reassigned, or no longer decodes) are dropped (`dead:*`), and so are listed pools idle in `idle_segments`
//!   consecutive segments they were listed in (`idle`). Priority: active listed pools, then new pools from our records,
//!   then new pools from the trending lists, then idle listed pools; the list is capped at `cap` (a token whose group a
//!   cut would break loses its additions).
//! - **Fail-safe.** A verification that cannot complete (an RPC failure, the deadline) writes the previous list
//!   unchanged, with `status` `kept_previous` and the reason. A source that fails only adds nothing (its status says why).
//! - **Never Haan.** No gRPC stream at all; the RPC is `[pool_refresh] rpc` (config-checked: never Haan's) at most
//!   `rpc_max_rps` requests a second in this process.
use crate::config::{Config, PoolRefreshCfg};
use crate::pools::{self, pair_key};
use crate::replay::venue_name;
use crate::rpc::Account;
use crate::tx::{b58, Pk};
use crate::venues::{token_amount, PoolMeta, Venue, WSOL};
use anyhow::{bail, Context, Result};
use base64::Engine as _;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::LazyLock;
use std::time::{Duration, Instant};

pub const SCHEMA: &str = "arbx.pool-refresh/1.0";
pub const INPUTS_SCHEMA: &str = "arbx.pool-refresh-inputs/1.0";
/// the `source` column of a pool WP-22 added: `wp22:<records|gt|ds>:<segment>`
pub const TAG: &str = "wp22";
pub static USDC: LazyLock<Pk> = LazyLock::new(|| crate::tx::pk("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"));
pub static USDT: LazyLock<Pk> = LazyLock::new(|| crate::tx::pk("Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"));
/// candidates from our records verified per refresh, at most this many times `max_adds` (the most active first)
const RECORD_CANDS_PER_ADD: usize = 5;
/// rejected candidates listed in the report (the counts are complete)
const REPORT_REJECTED_MAX: usize = 300;
/// more listed pools than this (or than a twentieth of the list) that one verification answer calls dead although the
/// last segment's boot found them alive (or the last segment saw them active) means the RPC, or a decoder after a program
/// upgrade, is suspect: the previous list stays. Below it they are kept anyway (review #2): the next boot re-checks them
/// on its own provider, and the refresh after it drops the ones that boot dropped
const DEAD_MAX_MIN: usize = 25;
/// a segment counts toward an idle streak only when its triggers cover at least this share of a segment's minutes
/// (review #3a: a short, crashed or degraded segment says little about its pools)
pub const IDLE_COVER_SHARE: f64 = 0.8;
/// the shrink guard (review #3b): one refresh drops at most max(IDLE_DROP_MIN, a tenth of the list) idle pools, the
/// longest idle first, and never so many that the list falls below SHRINK_FLOOR of its rows; the rest stay (idle, last
/// in priority) for a later refresh
pub const IDLE_DROP_MIN: usize = 25;
pub const SHRINK_FLOOR: f64 = 0.8;
/// the venues a refresh may add pools on: the five the engine trades at FT-008 (review #10: a venue added to `Venue`
/// later, such as WP-21A's CLMM and Whirlpool, is never added by a refresh until it is named here)
pub const ADD_VENUES: [Venue; 5] = [Venue::PumpSwap, Venue::RayCpmm, Venue::RayAmmV4, Venue::Dlmm, Venue::DammV2];

pub fn pk_opt(s: &str) -> Option<Pk> { bs58::decode(s.trim()).into_vec().ok().and_then(|v| Pk::try_from(v).ok()) }

// ------------------------------------------------------------------ the list

/// One seed row
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Row { pub venue: Venue, pub pool: Pk, pub source: String }

/// A seed list's rows (`venue` and `pool` columns required, `source` kept when there is one; other columns ignored),
/// the first of a repeated pool kept; and the lines that could not be read
pub fn parse_list(text: &str) -> Result<(Vec<Row>, usize)> {
    let mut lines = text.lines();
    let header: Vec<&str> = lines.next().context("empty seed list")?.split(',').map(str::trim).collect();
    let col = |n: &str| header.iter().position(|h| *h == n);
    let (cv, cp) = (col("venue").context("seed list: no venue column")?, col("pool").context("seed list: no pool column")?);
    let cs = col("source");
    let (mut rows, mut bad, mut seen) = (Vec::new(), 0usize, HashSet::new());
    for l in lines.filter(|l| !l.trim().is_empty()) {
        let f: Vec<&str> = l.split(',').collect();
        let (Some(v), Some(p)) = (f.get(cv).and_then(|s| Venue::parse(s.trim())), f.get(cp).and_then(|s| pk_opt(s))) else { bad += 1; continue };
        if !seen.insert(p) { continue; }
        rows.push(Row { venue: v, pool: p, source: cs.and_then(|i| f.get(i)).map(|s| s.trim().to_string()).unwrap_or_default() });
    }
    Ok((rows, bad))
}

/// The list as written: `venue,pool,source`, one row a line, in order
pub fn list_csv(rows: &[Row]) -> String {
    let mut s = String::from("venue,pool,source\n");
    for r in rows {
        s.push_str(venue_name(r.venue));
        s.push(',');
        s.push_str(&b58(&r.pool));
        s.push(',');
        s.push_str(&r.source.replace([',', '\n', '\r'], ";"));
        s.push('\n');
    }
    s
}

/// A list file checked for a segment to boot on (the campaign): it parses, has at least one row, and hashes as given
pub fn check_list(path: &Path, sha256: Option<&str>) -> Result<(usize, String)> {
    let b = std::fs::read(path).with_context(|| format!("reading {}", path.display()))?;
    let h = crate::provenance::sha256_hex(&b);
    if let Some(want) = sha256 { if want != h { bail!("{}: sha256 {h} is not the report's {want}", path.display()); } }
    let (rows, _) = parse_list(std::str::from_utf8(&b).context("not UTF-8")?)?;
    if rows.is_empty() { bail!("{}: no rows", path.display()); }
    Ok((rows.len(), h))
}

// ------------------------------------------------------------------ records

/// One pool's activity in one segment
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Counts { pub triggers: u64, pub decisions: u64, pub opps: u64, pub rivals: u64 }
impl Counts {
    pub fn total(&self) -> u64 { self.triggers + self.decisions + self.opps + self.rivals }
}

/// A pool we did not list, in rival arbitrage on our venues (exec records `arb_like`, landed)
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Seen { pub venue: String, pub txs: u64 }

/// One segment's records, as the refresh read them
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct SegAct {
    pub name: String,
    pub started_ns: u64,
    /// its stop.json exists (a segment still running is read as far as it got)
    pub complete: bool,
    /// every stream read without error, the essential ones (triggers, rivals) present, and at least one trigger recorded:
    /// only such a segment counts toward a pool's idle streak
    pub ok: bool,
    /// the pools it listed (its pools.json); None: unknown (no idle streak counts across it)
    pub listed: Option<BTreeSet<String>>,
    /// listed pools with any activity
    pub pools: BTreeMap<String, Counts>,
    /// pools it did not list, in landed rival arbitrage (exec records)
    pub unlisted: BTreeMap<String, Seen>,
    /// per stream: files, lines, bytes, an error
    pub streams: BTreeMap<String, Value>,
    /// the minutes (UTC wall-clock minutes) in which it recorded at least one trigger: how much of the segment its records
    /// cover (review #3a)
    #[serde(default)]
    pub covered_min: u32,
    /// the minutes it was started for (meta.json `run.argv` `--minutes`)
    #[serde(default)]
    pub planned_min: Option<f64>,
    /// the minutes from its start (meta.json `run.started_ns`, else its first trigger) to its last trigger
    #[serde(default)]
    pub span_min: f64,
    /// the minutes from its start to when the refresh read it (a running segment is read before its end)
    #[serde(default)]
    pub elapsed_min: f64,
}

fn find(h: &[u8], n: &[u8]) -> Option<usize> {
    if n.is_empty() || h.len() < n.len() { return None; }
    let first = n[0];
    let mut i = 0;
    while i + n.len() <= h.len() {
        match h[i..=h.len() - n.len()].iter().position(|b| *b == first) {
            None => return None,
            Some(j) => {
                let k = i + j;
                if &h[k..k + n.len()] == n { return Some(k); }
                i = k + 1;
            }
        }
    }
    None
}

/// the string value right after `key` (which ends with the opening quote)
fn str_after<'a>(line: &'a [u8], key: &[u8]) -> Option<&'a str> {
    let s = find(line, key)? + key.len();
    let e = line[s..].iter().position(|b| *b == b'"')?;
    std::str::from_utf8(&line[s..s + e]).ok()
}

/// the unsigned number right after `key` (which ends with `:`)
fn num_after(line: &[u8], key: &[u8]) -> Option<u64> {
    let s = find(line, key)? + key.len();
    let e = line[s..].iter().position(|b| !b.is_ascii_digit()).unwrap_or(line.len() - s);
    std::str::from_utf8(&line[s..s + e]).ok()?.parse().ok()
}

/// the strings of the array right after `key` (which ends with `[`)
fn strs_after<'a>(line: &'a [u8], key: &[u8]) -> Vec<&'a str> {
    let Some(s) = find(line, key).map(|i| i + key.len()) else { return vec![] };
    let Some(e) = line[s..].iter().position(|b| *b == b']') else { return vec![] };
    line[s..s + e].split(|b| *b == b',').filter_map(|x| std::str::from_utf8(x).ok()).map(|x| x.trim().trim_matches('"')).filter(|x| !x.is_empty()).collect()
}

/// What one stream's reading did
#[derive(Default)]
struct StreamStat { files: usize, lines: u64, bytes: u64, error: Option<String>, stopped: bool }
impl StreamStat {
    fn json(&self) -> Value { json!({ "files": self.files, "lines": self.lines, "bytes": self.bytes, "error": self.error, "deadline_stop": self.stopped }) }
}

/// Every line of a stream's files (`rec::stream_files`: rotation order), plain or zstd frames, one frame in memory at a
/// time; a trailing incomplete frame (a write in progress) is left out. Stops at `deadline`
fn each_line(dir: &Path, name: &str, deadline: Instant, f: &mut dyn FnMut(&[u8])) -> StreamStat {
    fn feed(buf: &[u8], carry: &mut Vec<u8>, st: &mut StreamStat, f: &mut dyn FnMut(&[u8])) {
        st.bytes += buf.len() as u64;
        let mut start = 0;
        for (i, b) in buf.iter().enumerate() {
            if *b == b'\n' {
                if carry.is_empty() { if i > start { f(&buf[start..i]); st.lines += 1; } }
                else { carry.extend_from_slice(&buf[start..i]); f(carry); st.lines += 1; carry.clear(); }
                start = i + 1;
            }
        }
        carry.extend_from_slice(&buf[start..]);
    }
    let mut st = StreamStat::default();
    for p in crate::rec::stream_files(dir, name) {
        if Instant::now() >= deadline { st.stopped = true; break; }
        st.files += 1;
        let data = match std::fs::read(&p) { Ok(d) => d, Err(e) => { st.error = Some(format!("{}: {e}", p.display())); continue } };
        let mut carry = Vec::new();
        if p.extension().is_some_and(|e| e == "zst") {
            let mut pos = 0;
            while pos < data.len() {
                if Instant::now() >= deadline { st.stopped = true; break; }
                let rest = &data[pos..];
                let Ok(n) = zstd::zstd_safe::find_frame_compressed_size(rest) else { break };
                if n == 0 || n > rest.len() { break; }
                let size = zstd::zstd_safe::get_frame_content_size(&rest[..n]).ok().flatten().unwrap_or(64 << 20) as usize;
                match zstd::bulk::decompress(&rest[..n], size) {
                    Ok(b) => feed(&b, &mut carry, &mut st, f),
                    Err(e) => { st.error = Some(format!("{}: a zstd frame: {e}", p.display())); break }
                }
                pos += n;
            }
        } else { feed(&data, &mut carry, &mut st, f); }
        if !carry.is_empty() { f(&carry); st.lines += 1; }
    }
    st
}

#[derive(Deserialize)]
struct IxLite<'a> { p: usize, #[serde(default)] a: Vec<usize>, #[serde(borrow, default)] d: &'a str }
#[derive(Deserialize)]
struct InnerLite<'a> { #[serde(borrow, default)] list: Vec<IxLite<'a>> }
#[derive(Deserialize)]
struct ExecLite<'a> {
    #[serde(default)] ok: bool,
    #[serde(borrow, default)] keys: Vec<&'a str>,
    #[serde(borrow, default)] ixs: Vec<IxLite<'a>>,
    #[serde(borrow, default)] inner: Option<Vec<InnerLite<'a>>>,
}

fn hex8(s: &str) -> [u8; 8] { let v: Vec<u8> = (0..8).map(|i| u8::from_str_radix(&s[2 * i..2 * i + 2], 16).unwrap()).collect(); v.try_into().unwrap() }
static PUMP_SWAPS: LazyLock<[[u8; 8]; 3]> = LazyLock::new(|| [hex8("33e685a4017f83ad"), hex8("c62e1552b4d9e870"), hex8("66063d1201daebea")]);
static CPMM_SWAPS: LazyLock<[[u8; 8]; 2]> = LazyLock::new(|| [hex8("8fbe5adac41e33de"), hex8("37d96256a34ab4ad")]);
static DLMM_SWAPS: LazyLock<[[u8; 8]; 6]> = LazyLock::new(|| [hex8("414b3f4ceb5b5b88"), hex8("f8c69e91e17587c8"), hex8("38ade6d0ade49ccd"), hex8("4a62c0d6b1334b33"),
    hex8("2bd7f784893cf351"), hex8("fa49652126cf4bb8")]);
static DAMM_SWAPS: LazyLock<[[u8; 8]; 2]> = LazyLock::new(|| [hex8("f8c69e91e17587c8"), hex8("414b3f4ceb5b5b88")]);

/// The pool account of a swap instruction on one of our venues, at the position the engine's decoders read it
/// (`venues::cp::decode_pending`, `venues::dlmm::decode_pending`, `engine::damm_pending`): PumpSwap buy / sell /
/// buy_exact_quote_in account 0, CPMM swap_base_input / output account 3, AMM v4 swap (tags 9, 11, 16, 17) account 1,
/// DLMM's swaps account 0, DAMM v2 swap / swap2 account 1; any other venue: None. `data`: the instruction data's first
/// bytes
pub fn swap_pool_index(venue: Venue, data: &[u8], n_acc: usize) -> Option<usize> {
    let d8: Option<[u8; 8]> = data.get(..8).map(|b| b.try_into().unwrap());
    let (ok, i, min) = match venue {
        Venue::PumpSwap => (d8.is_some_and(|d| PUMP_SWAPS.contains(&d)), 0, 4),
        Venue::RayCpmm => (d8.is_some_and(|d| CPMM_SWAPS.contains(&d)), 3, 8),
        Venue::RayAmmV4 => (data.first().is_some_and(|t| [9u8, 11, 16, 17].contains(t)) && data.len() >= 17, 1, 8),
        Venue::Dlmm => (d8.is_some_and(|d| DLMM_SWAPS.contains(&d)), 0, 11),
        Venue::DammV2 => (d8.is_some_and(|d| DAMM_SWAPS.contains(&d)), 1, 9),
        // venues added later (WP-21A's CLMM and Whirlpool): their swaps are not read for candidates yet (PLAN-ADDENDUM
        // WP-22 "later"); unreachable until they exist
        #[allow(unreachable_patterns)]
        _ => return None,
    };
    (ok && n_acc >= min).then_some(i)
}

/// the first bytes of a base64 instruction's data (enough for a discriminator and AMM v4's length check)
fn data_head(d: &str) -> Vec<u8> {
    let cut = if d.len() > 24 { &d[..24] } else { d };
    base64::engine::general_purpose::STANDARD.decode(cut).unwrap_or_default()
}

/// The pools of our venues a landed rival arbitrage swapped in (one exec line), with their venues
fn exec_pools(line: &[u8]) -> Vec<(Venue, String)> {
    let Ok(x) = serde_json::from_slice::<ExecLite>(line) else { return vec![] };
    if !x.ok { return vec![]; }
    let progs: Vec<Option<Venue>> = x.keys.iter().map(|k| pk_opt(k).and_then(|p| Venue::of_program(&p))).collect();
    let mut out: Vec<(Venue, String)> = Vec::new();
    let inner = x.inner.iter().flatten().flat_map(|l| l.list.iter());
    for ix in x.ixs.iter().chain(inner) {
        let Some(Some(v)) = progs.get(ix.p) else { continue };
        let Some(i) = swap_pool_index(*v, &data_head(ix.d), ix.a.len()) else { continue };
        let Some(k) = ix.a.get(i).and_then(|&j| x.keys.get(j)) else { continue };
        if !out.iter().any(|(_, p)| p == k) { out.push((*v, k.to_string())); }
    }
    out
}

/// One segment directory's records: the listed pools' activity and, with `exec`, the unlisted pools of landed rival
/// arbitrage
pub fn read_segment(dir: &Path, exec: bool, deadline: Instant) -> SegAct {
    let meta: Value = std::fs::read(dir.join("meta.json")).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or(Value::Null);
    let name = meta["run"]["segment"].as_str().map(String::from).unwrap_or_else(|| dir.file_name().map(|f| f.to_string_lossy().into_owned()).unwrap_or_default());
    let started_ns = meta["run"]["started_ns"].as_u64().unwrap_or(0);
    let listed: Option<BTreeSet<String>> = std::fs::read(dir.join(crate::replay::POOLS_FILE)).ok().and_then(|b| serde_json::from_slice::<Value>(&b).ok())
        .and_then(|v| v.as_array().map(|a| a.iter().filter_map(|p| p["pool"].as_str().map(String::from)).collect()));
    let planned_min = meta["run"]["argv"].as_array().and_then(|a| a.iter().position(|x| x == "--minutes").and_then(|i| a.get(i + 1)))
        .and_then(|m| m.as_str()).and_then(|m| m.parse::<f64>().ok());
    let mut s = SegAct { name, started_ns, complete: dir.join("stop.json").is_file(), ok: true, listed, planned_min, ..Default::default() };
    let mut counts: HashMap<String, Counts> = HashMap::new();
    let mut minutes: HashSet<u64> = HashSet::new();
    let read_ns = crate::feeds::clock::now_ns();
    let (mut first_rx, mut last_rx) = (u64::MAX, 0u64);
    {
        let mut bump = |p: &str, f: fn(&mut Counts)| { if !p.is_empty() { f(counts.entry(p.to_string()).or_default()); } };
        // a segment that recorded no trigger at all (its state stream was down, or it ended in its boot) says nothing about
        // its pools' activity: not ok, so it never counts toward an idle streak; the minutes its triggers cover (their
        // receive time, `st.rx`) say how much of it does (review #3a)
        let mut trig = 0u64;
        let st = each_line(dir, "triggers", deadline, &mut |l| {
            if let Some(p) = str_after(l, b"\"pool\":\"") {
                trig += 1;
                bump(p, |c| c.triggers += 1);
                if let Some(t) = find(l, b"\"st\":{").and_then(|i| num_after(&l[i..], b"\"rx\":")) {
                    minutes.insert(t / 60_000_000_000);
                    first_rx = first_rx.min(t);
                    last_rx = last_rx.max(t);
                }
            }
        });
        if st.files == 0 || trig == 0 { s.ok = false; }
        s.streams.insert("triggers".into(), st.json());
        if st.error.is_some() || st.stopped { s.ok = false; }
        let st = each_line(dir, "opportunities", deadline, &mut |l| {
            for k in [&b"\"buy_pool\":\""[..], &b"\"sell_pool\":\""[..]] { if let Some(p) = str_after(l, k) { bump(p, |c| c.opps += 1); } }
        });
        if st.error.is_some() || st.stopped { s.ok = false; }
        s.streams.insert("opportunities".into(), st.json());
        let st = each_line(dir, "decisions", deadline, &mut |l| {
            if let Some(t) = find(l, b"\"trigger\":{") { if let Some(p) = str_after(&l[t..], b"\"pool\":\"") { bump(p, |c| c.decisions += 1); } }
        });
        if st.error.is_some() || st.stopped { s.ok = false; }
        s.streams.insert("decisions".into(), st.json());
        let st = each_line(dir, "rivals", deadline, &mut |l| { for p in strs_after(l, b"\"pools\":[") { bump(p, |c| c.rivals += 1); } });
        if st.files == 0 || st.error.is_some() || st.stopped { s.ok = false; }
        s.streams.insert("rivals".into(), st.json());
    }
    s.pools = counts.into_iter().filter(|(_, c)| c.total() > 0).collect();
    s.covered_min = minutes.len() as u32;
    if last_rx > 0 {
        let from = if started_ns > 0 && started_ns <= first_rx { started_ns } else { first_rx };
        s.span_min = (last_rx - from) as f64 / 60e9;
    }
    s.elapsed_min = if started_ns > 0 { read_ns.saturating_sub(started_ns) as f64 / 60e9 } else { s.span_min };
    if exec {
        let listed = s.listed.clone().unwrap_or_default();
        let mut seen: HashMap<String, Seen> = HashMap::new();
        let mut bad = 0u64;
        let st = each_line(dir, "exec", deadline, &mut |l| {
            // the landed rival arbitrage only (exec.jsonl `arb_like`, WP-08)
            if find(l, b"\"arb_like\":{\"is\":true").is_none() { return; }
            let ps = exec_pools(l);
            if ps.is_empty() { bad += (find(l, b"\"ok\":true").is_some() && serde_json::from_slice::<ExecLite>(l).is_err()) as u64; }
            for (v, p) in ps {
                if listed.contains(&p) { continue; }
                let e = seen.entry(p).or_insert_with(|| Seen { venue: venue_name(v).into(), txs: 0 });
                e.txs += 1;
            }
        });
        let mut j = st.json();
        j["unparsed"] = json!(bad);
        if st.error.is_some() { s.ok = false; }
        s.streams.insert("exec".into(), j);
        s.unlisted = seen.into_iter().collect();
    }
    s
}

/// The segment directories under `paths` (a segment directory itself, or a campaign directory: its `<name>-p<i>`
/// segments), oldest first (meta.json `run.started_ns`, then the name)
pub fn segment_dirs(paths: &[PathBuf]) -> Vec<PathBuf> {
    let mut out: Vec<(u64, String, PathBuf)> = Vec::new();
    let mut add = |d: &Path| {
        let meta: Value = std::fs::read(d.join("meta.json")).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or(Value::Null);
        let n = d.file_name().map(|f| f.to_string_lossy().into_owned()).unwrap_or_default();
        out.push((meta["run"]["started_ns"].as_u64().unwrap_or(0), n, d.to_path_buf()));
    };
    for p in paths {
        if p.join("meta.json").is_file() { add(p); continue; }
        let mut subs: Vec<PathBuf> = std::fs::read_dir(p).into_iter().flatten().flatten().map(|e| e.path()).filter(|d| d.is_dir() && d.join("meta.json").is_file()).collect();
        subs.sort();
        for d in subs { add(&d); }
    }
    out.sort();
    out.dedup_by(|a, b| a.2 == b.2);
    out.into_iter().map(|x| x.2).collect()
}

// ------------------------------------------------------------------ candidates from the trending lists

/// Where a candidate came from, in priority order
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Src { Records, Gt, Ds }
impl Src {
    pub fn tag(self) -> &'static str { match self { Src::Records => "records", Src::Gt => "gt", Src::Ds => "ds" } }
}

/// A pool to verify: its venue as the source names it (the chain's owner decides), the mints the source names (none
/// from our records), a score (USD volume over the last hour for the trending lists, rival transactions for our records)
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Cand {
    pub pool: String,
    pub venue: String,
    pub src: Src,
    pub base: Option<String>,
    pub quote: Option<String>,
    pub score: f64,
    pub symbol: Option<String>,
    /// the list or token it came from
    pub via: String,
}

/// GeckoTerminal's dex id as our venue (a hint: the account's owner decides)
pub fn gt_venue(dex: &str) -> Option<Venue> {
    match dex {
        "pumpswap" => Some(Venue::PumpSwap),
        "meteora" => Some(Venue::Dlmm),
        "meteora-damm-v2" => Some(Venue::DammV2),
        "raydium" => Some(Venue::RayAmmV4),
        "raydium-cp" | "raydium-cpmm" | "raydium-cp-swap" => Some(Venue::RayCpmm),
        _ => None,
    }
}

/// DexScreener's dex id and labels as our venue (a hint: the account's owner decides)
pub fn ds_venue(dex: &str, labels: &[String]) -> Option<Venue> {
    let has = |l: &str| labels.iter().any(|x| x.eq_ignore_ascii_case(l));
    match dex {
        "pumpswap" => Some(Venue::PumpSwap),
        "meteora" if has("DLMM") => Some(Venue::Dlmm),
        "meteora" if has("DYN2") => Some(Venue::DammV2),
        "raydium" if has("CPMM") => Some(Venue::RayCpmm),
        "raydium" if labels.is_empty() || has("AMM") || has("AMMv4") => Some(Venue::RayAmmV4),
        _ => None,
    }
}

fn num(v: &Value) -> Option<f64> { v.as_f64().or_else(|| v.as_str().and_then(|s| s.parse().ok())) }
fn strip_sol(id: &str) -> &str { id.strip_prefix("solana_").unwrap_or(id) }

/// A GeckoTerminal pools list (`trending_pools`, `new_pools`): our venues' pools as candidates, and every base token
/// (WSOL, USDC, USDT left out) for DexScreener
pub fn parse_gt(body: &str, via: &str) -> Result<(Vec<Cand>, Vec<(String, Option<String>)>)> {
    let v: Value = serde_json::from_str(body).context("GeckoTerminal: not JSON")?;
    let items = v["data"].as_array().context("GeckoTerminal: no data list")?;
    let hubs = [b58(&WSOL), b58(&USDC), b58(&USDT)];
    let (mut cands, mut tokens) = (Vec::new(), Vec::new());
    for it in items {
        let a = &it["attributes"];
        let Some(pool) = a["address"].as_str() else { continue };
        let r = &it["relationships"];
        let (base, quote) = (r["base_token"]["data"]["id"].as_str().map(strip_sol), r["quote_token"]["data"]["id"].as_str().map(strip_sol));
        let symbol = a["name"].as_str().and_then(|n| n.split(" / ").next()).map(|s| s.trim().to_string());
        for t in [base, quote].into_iter().flatten() {
            if !hubs.iter().any(|h| h.as_str() == t) && !tokens.iter().any(|(x, _): &(String, Option<String>)| x.as_str() == t) {
                tokens.push((t.to_string(), if Some(t) == base { symbol.clone() } else { None }));
            }
        }
        let Some(venue) = r["dex"]["data"]["id"].as_str().and_then(gt_venue) else { continue };
        // GeckoTerminal's reserve is both sides: half of it on the quote side, against the minimum (the chain decides)
        cands.push(Cand { pool: pool.to_string(), venue: venue_name(venue).into(), src: Src::Gt, base: base.map(String::from), quote: quote.map(String::from),
            score: num(&a["volume_usd"]["h1"]).unwrap_or(0.0), symbol, via: via.to_string() });
    }
    Ok((cands, tokens))
}

/// A DexScreener token-pairs answer: the token's pools on our venues with a quote we take and, where it says, at least
/// half the minimum liquidity on the quote side (the chain decides)
pub fn parse_ds(body: &str, via: &str, quotes: &[Pk], min_quote_units: &dyn Fn(&Pk) -> f64) -> Result<Vec<Cand>> {
    let v: Value = serde_json::from_str(body).context("DexScreener: not JSON")?;
    let items = v.as_array().or_else(|| v["pairs"].as_array()).context("DexScreener: no pair list")?;
    let mut out = Vec::new();
    for p in items {
        if p["chainId"].as_str().is_some_and(|c| c != "solana") { continue; }
        let Some(pool) = p["pairAddress"].as_str() else { continue };
        let labels: Vec<String> = p["labels"].as_array().map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect()).unwrap_or_default();
        let Some(venue) = p["dexId"].as_str().and_then(|d| ds_venue(d, &labels)) else { continue };
        let (base, quote) = (p["baseToken"]["address"].as_str(), p["quoteToken"]["address"].as_str());
        let (Some(bk), Some(qk)) = (base.and_then(pk_opt), quote.and_then(pk_opt)) else { continue };
        // the quote side: whichever of the two is a quote we take (DexScreener may name them the other way round)
        let (q, qunits) = if quotes.contains(&qk) { (qk, num(&p["liquidity"]["quote"])) } else if quotes.contains(&bk) { (bk, num(&p["liquidity"]["base"])) } else { continue };
        if qunits.is_some_and(|u| u < min_quote_units(&q) * 0.5) { continue; }
        let sym = if q == qk { p["baseToken"]["symbol"].as_str() } else { p["quoteToken"]["symbol"].as_str() };
        out.push(Cand { pool: pool.to_string(), venue: venue_name(venue).into(), src: Src::Ds, base: base.map(String::from), quote: quote.map(String::from),
            score: num(&p["volume"]["h1"]).unwrap_or(0.0), symbol: sym.map(String::from), via: via.to_string() });
    }
    Ok(out)
}

/// Candidates merged by pool: the best source kept (records, then GeckoTerminal, then DexScreener), its mints the
/// first named, the highest score; sorted by pool
pub fn merge(cands: Vec<Cand>) -> Vec<Cand> {
    let mut m: BTreeMap<String, Cand> = BTreeMap::new();
    for c in cands {
        match m.get_mut(&c.pool) {
            None => { m.insert(c.pool.clone(), c); }
            Some(x) => {
                let score = x.score.max(c.score);
                if c.src < x.src { let (b, q, s) = (x.base.clone(), x.quote.clone(), x.symbol.clone()); *x = c; if x.base.is_none() { x.base = b; x.quote = q; } if x.symbol.is_none() { x.symbol = s; } }
                else { if x.base.is_none() { x.base = c.base; x.quote = c.quote; } if x.symbol.is_none() { x.symbol = c.symbol; } }
                x.score = score;
            }
        }
    }
    m.into_values().collect()
}

// ------------------------------------------------------------------ the plan

/// A registry pool on one of our venues (registry.json), for the group count
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RegPool { pub venue: String, pub pool: String, pub t0: String, pub t1: String }

/// The registry's pools on our venues (registry.json rows: venue, pool, t0, t1)
pub fn read_registry(path: &str) -> Result<Vec<RegPool>> {
    let rows: Vec<Value> = serde_json::from_str(&std::fs::read_to_string(path).with_context(|| format!("reading {path}"))?)?;
    Ok(rows.iter().filter_map(|r| {
        let v = r["venue"].as_str().and_then(Venue::parse)?;
        Some(RegPool { venue: venue_name(v).into(), pool: r["pool"].as_str()?.into(), t0: r["t0"].as_str()?.into(), t1: r["t1"].as_str()?.into() })
    }).collect())
}

/// The registry pools the group rule may count: the boot loads registry.json's pools only with `[pools] registry_all`
/// (or on seed pairs named by mint columns, which the lists the refresh writes do not have), so without it none count
/// (review #9); and only on the venues the boot reads from the registry, as `pools::candidates` (PLAN-ADDENDUM WP-21
/// review R2-2: never Raydium CLMM or Orca Whirlpool rows, whose pools come from the seed list only, nor a venue switched
/// off)
pub fn registry_for(cfg: &Config) -> Vec<RegPool> {
    match (&cfg.pools.registry_json, cfg.pools.registry_all) {
        (Some(r), true) => read_registry(r).unwrap_or_default().into_iter()
            .filter(|p| Venue::parse(&p.venue).is_some_and(|v| !v.is_clmm() && cfg.pools.venue_on(v))).collect(),
        _ => vec![],
    }
}

/// An account as saved in the inputs file (base64 data)
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SavedAcct { pub owner: String, pub lamports: u64, pub data: String }
impl SavedAcct {
    pub fn of(a: &Account) -> SavedAcct { SavedAcct { owner: b58(&a.owner), lamports: a.lamports, data: base64::engine::general_purpose::STANDARD.encode(&a.data) } }
    pub fn account(&self) -> Option<Account> {
        Some(Account { owner: pk_opt(&self.owner)?, lamports: self.lamports, data: base64::engine::general_purpose::STANDARD.decode(&self.data).ok()? })
    }
}

/// Everything the plan reads (the inputs file): the same inputs give the same list
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct Inputs {
    pub current: Vec<(String, String, String)>,
    pub registry: Vec<RegPool>,
    pub segments: Vec<SegAct>,
    pub cands: Vec<Cand>,
    /// every account fetched (null: none on chain)
    pub accounts: BTreeMap<String, Option<SavedAcct>>,
    /// the campaign's segment length (`--segment-min`); None: each segment's own `--minutes` (review #3a)
    #[serde(default)]
    pub segment_min: Option<f64>,
    /// review #7: the policy the plan ran with, the segment the list is for, why the fetch failed (the plan then keeps
    /// the previous list), and the current list's sha256: a replay uses them and refuses another policy or list
    #[serde(default)]
    pub policy: Option<PoolRefreshCfg>,
    #[serde(default)]
    pub segment: Option<String>,
    #[serde(default)]
    pub failure: Option<String>,
    #[serde(default)]
    pub current_sha256: Option<String>,
}

impl Inputs {
    pub fn rows(&self) -> Vec<Row> {
        self.current.iter().filter_map(|(v, p, s)| Some(Row { venue: Venue::parse(v)?, pool: pk_opt(p)?, source: s.clone() })).collect()
    }
    pub fn set_rows(&mut self, rows: &[Row]) { self.current = rows.iter().map(|r| (venue_name(r.venue).to_string(), b58(&r.pool), r.source.clone())).collect(); }
}

/// What the plan decided
#[derive(Debug)]
pub struct Outcome { pub rows: Vec<Row>, pub report: Value }

#[derive(Clone, Debug)]
struct Verified { c: Cand, m: PoolMeta, token: Pk, quote: Pk, liq: u64 }

/// A listed pool the plan keeps (for now): its row and index in the list, its metadata (None: one verification answer
/// called it dead, `rpc`, but the last boot found it alive or the last segment saw it active), its activity, its idle streak
#[derive(Clone, Debug)]
struct Listed { i: usize, row: Row, meta: Option<PoolMeta>, total: u64, streak: u32, rpc: Option<&'static str> }

/// the minutes a segment is measured against: the campaign's segment length, else its own `--minutes`
fn seg_minutes(inp: &Inputs, s: &SegAct) -> Option<f64> { inp.segment_min.or(s.planned_min).filter(|m| *m > 0.0) }

/// whether a segment counts toward an idle streak (review #3a): its records whole; its triggers spanning
/// IDLE_COVER_SHARE of its minutes (a complete segment's: the campaign's segment length or its own `--minutes`; a
/// running one's: those elapsed when the refresh read it, at least half a segment) with a trigger in IDLE_COVER_SHARE of
/// the minutes of that span (a stream that died, or stalled for a while, leaves gaps)
fn counts_for_idle(inp: &Inputs, s: &SegAct) -> bool {
    let Some(m) = seg_minutes(inp, s) else { return false };
    let need = if s.complete { m } else if s.elapsed_min >= 0.5 * m { s.elapsed_min.min(m) } else { return false };
    s.ok && s.span_min >= IDLE_COVER_SHARE * need && s.covered_min as f64 >= IDLE_COVER_SHARE * s.span_min
}

/// the order of a new pool among the new ones: our records first, then the trending lists; the higher score; the pool
fn add_key(c: &Cand) -> (Src, i64, String) { (c.src, -(c.score.max(0.0).min(9e15) as i64), c.pool.clone()) }

/// The plan: the next list from the inputs (pure: the same inputs give the same list). Err: the inputs are incomplete
/// (an account the plan needs was not fetched): the caller keeps the previous list
pub fn plan(p: &PoolRefreshCfg, inp: &Inputs, segment: &str) -> std::result::Result<Outcome, String> {
    let quotes: Vec<Pk> = p.quotes.iter().map(|q| if q == "USDC" { *USDC } else { *WSOL }).collect();
    let accts: HashMap<Pk, Option<Account>> = inp.accounts.iter().filter_map(|(k, a)| Some((pk_opt(k)?, a.as_ref().and_then(|a| a.account())))).collect();
    let get = |k: &Pk| -> std::result::Result<Option<&Account>, String> { accts.get(k).map(|a| a.as_ref()).ok_or_else(|| format!("account {} was not fetched", b58(k))) };
    let current = inp.rows();
    let segs = &inp.segments;
    // what the last boot saw (the most recent segment with a pools.json: the running one, booted on its own provider) and
    // what the most recent segment saw active: a pool either vouches for is never dropped on one verification answer
    let booted: Option<&BTreeSet<String>> = segs.iter().rev().find_map(|s| s.listed.as_ref());
    let last_active = |key: &str| segs.last().is_some_and(|s| s.pools.get(key).is_some_and(|c| c.total() > 0));
    // 1. the listed pools: alive, active or idle
    let mut drops: Vec<Value> = Vec::new();
    let mut listed: Vec<Listed> = Vec::new();
    let mut idle: Vec<Listed> = Vec::new();
    let mut unconfirmed = 0usize;
    for (i, r) in current.iter().enumerate() {
        let a = get(&r.pool)?;
        let meta = match a {
            None => Err("dead:missing"),
            Some(a) if a.owner != r.venue.program() => Err("dead:owner"),
            Some(a) => pools::meta_of(r.venue, &r.pool, &a.data).ok_or("dead:layout"),
        };
        let key = b58(&r.pool);
        let total: u64 = segs.iter().filter_map(|s| s.pools.get(&key)).map(|c| c.total()).sum();
        let m = match meta {
            Ok(m) => m,
            // review #2: alive at the last boot, or active since: kept; the next boot re-checks it and drops it if it is
            // gone, and the refresh after that drops it (it is then in no boot's pools.json)
            Err(why) if booted.is_some_and(|b| b.contains(&key)) || last_active(&key) => {
                unconfirmed += 1;
                listed.push(Listed { i, row: r.clone(), meta: None, total, streak: 0, rpc: Some(why) });
                continue;
            }
            Err(why) => { drops.push(json!({ "venue": venue_name(r.venue), "pool": key, "why": why, "source": r.source })); continue }
        };
        let mut streak = 0u32;
        for s in segs.iter().rev() {
            let listed_here = s.listed.as_ref().is_some_and(|l| l.contains(&key));
            if !counts_for_idle(inp, s) || !listed_here || s.pools.get(&key).is_some_and(|c| c.total() > 0) { break; }
            streak += 1;
        }
        let x = Listed { i, row: r.clone(), meta: Some(m), total, streak, rpc: None };
        if p.idle_segments > 0 && streak >= p.idle_segments { idle.push(x); } else { listed.push(x); }
    }
    // the suspect-RPC guard: the listed pools one answer calls dead against the last boot or the last segment's activity
    // (without any boot record, every dead one)
    let suspect = unconfirmed + if booted.is_none() { drops.len() } else { 0 };
    let max_dead = DEAD_MAX_MIN.max(current.len() / 20);
    if suspect > max_dead {
        return Err(format!("{suspect} of the {} listed pools came back dead (more than {max_dead} in one refresh{}): the RPC or a decoder is suspect", current.len(),
            if booted.is_some() { ", all alive at the last segment's boot or active in it" } else { "" }));
    }
    // the shrink guard (review #3b): at most max(IDLE_DROP_MIN, a tenth of the list) idle pools go, the longest idle
    // first, and never below SHRINK_FLOOR of the list's rows; the others stay, idle, last in priority
    let n = current.len();
    let idle_bound = IDLE_DROP_MIN.max(n / 10);
    let floor_rows = (n as f64 * SHRINK_FLOOR).ceil() as usize;
    let idle_room = idle_bound.min(n.saturating_sub(drops.len()).saturating_sub(floor_rows));
    idle.sort_by(|a, b| b.streak.cmp(&a.streak).then(a.total.cmp(&b.total)).then(a.i.cmp(&b.i)));
    let idle_candidates = idle.len();
    let held = idle.split_off(idle_room.min(idle.len()));
    for x in &idle {
        drops.push(json!({ "venue": venue_name(x.row.venue), "pool": b58(&x.row.pool), "why": "idle", "idle_segments": x.streak, "source": x.row.source }));
    }
    let idle_held = held.len();
    listed.extend(held);
    listed.sort_by_key(|x| x.i);
    let shrink = json!({ "idle_candidates": idle_candidates, "idle_dropped": idle.len(), "idle_held": idle_held, "idle_bound": idle_bound, "floor_rows": floor_rows,
        "applied": idle_held > 0 });
    let listed_set: HashSet<Pk> = current.iter().map(|r| r.pool).collect();
    // the pools on a pair: listed (alive) and the registry's (alive on chain, fetched with the candidates)
    let mut on_pair: HashMap<(Pk, Pk), BTreeSet<Pk>> = HashMap::new();
    for x in &listed { if let Some(m) = &x.meta { on_pair.entry(pair_key(&m.t0, &m.t1)).or_default().insert(x.row.pool); } }
    let reg_pools: HashSet<Pk> = inp.registry.iter().filter_map(|r| pk_opt(&r.pool)).collect();
    let mut reg_alive: HashMap<(Pk, Pk), BTreeSet<Pk>> = HashMap::new();
    for r in &inp.registry {
        let (Some(v), Some(pool), Some(t0), Some(t1)) = (Venue::parse(&r.venue), pk_opt(&r.pool), pk_opt(&r.t0), pk_opt(&r.t1)) else { continue };
        // (WP-21 review R2-2: the boot never loads the registry's CLMM rows: an inputs file saved before `registry_for`
        // left them out does not count them either)
        if v.is_clmm() || listed_set.contains(&pool) { continue; }
        // alive: fetched, the venue's, decodes, the pair the registry names (not fetched: not counted, the safe side)
        let alive = accts.get(&pool).and_then(|a| a.as_ref()).is_some_and(|a| a.owner == v.program()
            && pools::meta_of(v, &pool, &a.data).is_some_and(|m| pair_key(&m.t0, &m.t1) == pair_key(&t0, &t1)));
        if alive { reg_alive.entry(pair_key(&t0, &t1)).or_default().insert(pool); }
    }
    // 2. the candidates, verified
    let mut rejected: Vec<(Cand, String)> = Vec::new();
    let mut ok: Vec<Verified> = Vec::new();
    for c in &inp.cands {
        let Some(pool) = pk_opt(&c.pool) else { rejected.push((c.clone(), "address".into())); continue };
        if listed_set.contains(&pool) { continue; }
        if reg_pools.contains(&pool) { rejected.push((c.clone(), "in_registry".into())); continue; }
        let res: std::result::Result<Verified, String> = 'v: {
            let Some(a) = get(&pool)? else { break 'v Err("missing".into()) };
            let Some(venue) = Venue::of_program(&a.owner).filter(|v| ADD_VENUES.contains(v)) else { break 'v Err("venue".into()) };
            let Some(m) = pools::meta_of(venue, &pool, &a.data) else { break 'v Err("layout".into()) };
            if let (Some(b), Some(q)) = (c.base.as_deref().and_then(pk_opt), c.quote.as_deref().and_then(pk_opt)) {
                if pair_key(&b, &q) != pair_key(&m.t0, &m.t1) { break 'v Err("mints".into()); }
            }
            let Some(quote) = quotes.iter().copied().find(|q| m.t0 == *q || m.t1 == *q) else { break 'v Err("quote".into()) };
            let token = if m.t0 == quote { m.t1 } else { m.t0 };
            if token == quote { break 'v Err("quote".into()); }
            let qv = if m.t0 == quote { m.vault0 } else { m.vault1 };
            let liq = match get(&qv)? { Some(v) if v.data.len() >= 72 && v.data[..32] == quote[..] => token_amount(&v.data).unwrap_or(0), _ => break 'v Err("vault".into()) };
            let min = if quote == *WSOL { (p.min_liquidity_sol * 1e9) as u64 } else { (p.min_liquidity_usdc * 1e6) as u64 };
            if liq < min { break 'v Err("liquidity".into()); }
            let (ma, mb) = (get(&m.t0)?.cloned(), get(&m.t1)?.cloned());
            if ma.is_none() || mb.is_none() { break 'v Err("mint_missing".into()); }
            let mints = [m.t0, m.t1];
            let mut v = vec![m];
            let d = pools::apply_mints(&mut v, &mints, &[ma, mb]);
            if let Some(d) = d.first() { break 'v Err(d.why.into()); }
            Ok(Verified { c: c.clone(), m: v.remove(0), token, quote, liq })
        };
        match res { Ok(v) => ok.push(v), Err(why) => rejected.push((c.clone(), why)) }
    }
    // 3. the group rule: a token enters with 2+ verified pools of one quote on our venues, the listed ones counted
    let have = |k: &(Pk, Pk)| on_pair.get(k).map_or(0, |s| s.len()) + reg_alive.get(k).map_or(0, |s| s.len());
    let mut by_pair: BTreeMap<(Pk, Pk), Vec<Verified>> = BTreeMap::new();
    for v in ok { by_pair.entry(pair_key(&v.token, &v.quote)).or_default().push(v); }
    let mut units: Vec<Vec<Verified>> = Vec::new();
    for (k, mut vs) in by_pair {
        vs.sort_by(|a, b| add_key(&a.c).cmp(&add_key(&b.c)));
        let h = have(&k);
        if h + vs.len() < 2 { for v in vs { rejected.push((v.c, "group".into())); } continue; }
        let mut it = vs.into_iter();
        if h == 0 { units.push(vec![it.next().unwrap(), it.next().unwrap()]); }
        for v in it { units.push(vec![v]); }
    }
    units.sort_by(|a, b| add_key(&a[0].c).cmp(&add_key(&b[0].c)));
    let mut adds: Vec<Verified> = Vec::new();
    for u in units {
        if adds.len() + u.len() <= p.max_adds { adds.extend(u); } else { for v in u { rejected.push((v.c, "max_adds".into())); } }
    }
    // 4. the cap: active listed pools (most active first), new pools, idle listed pools; a token whose group the cut breaks
    // loses its additions (and the room goes back to the idle pools)
    let final_set = loop {
        let mut order: Vec<(u8, i64, String, Pk)> = Vec::new();
        for x in &listed { if x.total > 0 { order.push((0, -(x.total as i64), format!("{:08}", x.i), x.row.pool)); } }
        for (n, v) in adds.iter().enumerate() { order.push((1, 0, format!("{n:08}"), v.m.pool)); }
        for x in &listed { if x.total == 0 { order.push((2, 0, format!("{:08}", x.i), x.row.pool)); } }
        order.sort();
        let kept: HashSet<Pk> = order.iter().take(p.cap).map(|x| x.3).collect();
        let broken: BTreeSet<(Pk, Pk)> = adds.iter().map(|v| pair_key(&v.token, &v.quote)).filter(|k| {
            let n = on_pair.get(k).map_or(0, |s| s.iter().filter(|x| kept.contains(*x)).count()) + reg_alive.get(k).map_or(0, |s| s.len())
                + adds.iter().filter(|v| pair_key(&v.token, &v.quote) == *k && kept.contains(&v.m.pool)).count();
            n < 2
        }).collect();
        if broken.is_empty() { break kept; }
        let (keep, cut): (Vec<Verified>, Vec<Verified>) = adds.into_iter().partition(|v| !broken.contains(&pair_key(&v.token, &v.quote)));
        for v in cut { rejected.push((v.c, "cap_group".into())); }
        adds = keep;
    };
    let mut rows: Vec<Row> = Vec::new();
    let mut kept_j: Vec<Value> = Vec::new();
    let (mut n_active, mut n_idle, mut n_unconfirmed) = (0usize, 0usize, 0usize);
    let in_listed: HashMap<Pk, &Listed> = listed.iter().map(|x| (x.row.pool, x)).collect();
    for r in &current {
        let Some(x) = in_listed.get(&r.pool) else { continue };
        if final_set.contains(&r.pool) {
            rows.push(r.clone());
            let why = if x.rpc.is_some() { n_unconfirmed += 1; "unconfirmed_dead" } else if x.total > 0 { n_active += 1; "active" } else { n_idle += 1; "idle" };
            kept_j.push(json!({ "pool": b58(&r.pool), "why": why, "activity": x.total, "idle_segments": x.streak, "rpc": x.rpc }));
        } else {
            drops.push(json!({ "venue": venue_name(r.venue), "pool": b58(&r.pool), "why": "cap", "activity": x.total, "source": r.source }));
        }
    }
    let mut added_j: Vec<Value> = Vec::new();
    let mut by_token: BTreeMap<Pk, (Option<String>, usize, f64)> = BTreeMap::new();
    let mut adds_by_src: BTreeMap<&str, usize> = BTreeMap::new();
    for v in &adds {
        if !final_set.contains(&v.m.pool) { rejected.push((v.c.clone(), "cap".into())); continue; }
        let source = format!("{TAG}:{}:{segment}", v.c.src.tag());
        rows.push(Row { venue: v.m.venue, pool: v.m.pool, source: source.clone() });
        *adds_by_src.entry(v.c.src.tag()).or_default() += 1;
        let t = by_token.entry(v.token).or_insert((None, 0, 0.0));
        if t.0.is_none() { t.0 = v.c.symbol.clone(); }
        t.1 += 1;
        t.2 += v.c.score;
        added_j.push(json!({ "venue": venue_name(v.m.venue), "pool": b58(&v.m.pool), "token": b58(&v.token), "quote": b58(&v.quote), "source": source,
            "src": v.c.src.tag(), "via": v.c.via, "score": v.c.score, "symbol": v.c.symbol, "quote_liquidity": v.liq }));
    }
    let mut top: Vec<(Pk, (Option<String>, usize, f64))> = by_token.into_iter().collect();
    top.sort_by(|a, b| b.1.1.cmp(&a.1.1).then(b.1.2.partial_cmp(&a.1.2).unwrap_or(std::cmp::Ordering::Equal)).then(a.0.cmp(&b.0)));
    let mut dropped_by: BTreeMap<String, usize> = BTreeMap::new();
    for d in &drops { *dropped_by.entry(d["why"].as_str().unwrap_or("?").to_string()).or_default() += 1; }
    let mut rejected_by: BTreeMap<String, usize> = BTreeMap::new();
    for (_, w) in &rejected { *rejected_by.entry(w.clone()).or_default() += 1; }
    let mut cands_by: BTreeMap<&str, usize> = BTreeMap::new();
    for c in &inp.cands { *cands_by.entry(c.src.tag()).or_default() += 1; }
    rejected.sort_by(|a, b| a.0.pool.cmp(&b.0.pool));
    let report = json!({
        "counts": { "current": current.len(), "rows": rows.len(), "kept": n_active + n_idle + n_unconfirmed, "kept_active": n_active, "kept_idle": n_idle,
            "kept_unconfirmed": n_unconfirmed, "idle_held": idle_held, "added": added_j.len(),
            "added_by_source": adds_by_src, "dropped": drops.len(), "dropped_by": dropped_by, "candidates": inp.cands.len(), "candidates_by_source": cands_by,
            "rejected_by": rejected_by },
        "added": added_j,
        "dropped": drops,
        "top_tokens": top.iter().take(10).map(|(k, (s, n, sc))| json!({ "token": b58(k), "symbol": s, "pools": n, "score": sc })).collect::<Vec<_>>(),
        "rejected": rejected.iter().take(REPORT_REJECTED_MAX).map(|(c, w)| json!({ "pool": c.pool, "venue": c.venue, "src": c.src.tag(), "via": c.via, "why": w })).collect::<Vec<_>>(),
        "kept": kept_j,
        "shrink_guard": shrink,
        "segments_counted_for_idle": segs.iter().map(|s| json!({ "segment": s.name, "counts": counts_for_idle(inp, s), "complete": s.complete,
            "covered_min": s.covered_min, "span_min": (s.span_min * 10.0).round() / 10.0, "elapsed_min": (s.elapsed_min * 10.0).round() / 10.0,
            "minutes": seg_minutes(inp, s) })).collect::<Vec<_>>(),
    });
    Ok(Outcome { rows, report })
}

// ------------------------------------------------------------------ fetching

/// HTTP GETs (the real one: reqwest; tests: recorded answers)
pub trait Web { fn get(&mut self, url: &str) -> std::result::Result<String, String>; }
/// getMultipleAccounts (the real one: the configured RPC; tests: recorded accounts)
pub trait Chain { fn accounts(&mut self, keys: &[Pk]) -> std::result::Result<Vec<Option<Account>>, String>; fn name(&self) -> String; }

/// The real web: one client, a timeout per request, each host paced at its own rate
pub struct HttpWeb { rt: tokio::runtime::Runtime, http: reqwest::Client, gap: Vec<(String, Duration)>, last: HashMap<String, Instant> }
impl HttpWeb {
    pub fn new(cfg: &PoolRefreshCfg) -> Result<HttpWeb> {
        let rt = tokio::runtime::Builder::new_current_thread().enable_all().build()?;
        let http = reqwest::Client::builder().timeout(Duration::from_secs(cfg.http_timeout_s)).user_agent(concat!("arbx/", env!("CARGO_PKG_VERSION"))).build()?;
        let host = |u: &str| crate::rpc::url_host(u).unwrap_or_default();
        let gap = vec![(host(&cfg.geckoterminal_url), Duration::from_secs_f64(60.0 / cfg.geckoterminal_per_min.max(1) as f64)),
            (host(&cfg.dexscreener_url), Duration::from_secs_f64(60.0 / cfg.dexscreener_per_min.max(1) as f64))];
        Ok(HttpWeb { rt, http, gap, last: HashMap::new() })
    }
}
impl Web for HttpWeb {
    fn get(&mut self, url: &str) -> std::result::Result<String, String> {
        let host = crate::rpc::url_host(url).unwrap_or_default();
        if let (Some(g), Some(t)) = (self.gap.iter().find(|x| x.0 == host).map(|x| x.1), self.last.get(&host)) {
            let wait = g.saturating_sub(t.elapsed());
            if !wait.is_zero() { std::thread::sleep(wait); }
        }
        self.last.insert(host, Instant::now());
        let http = self.http.clone();
        let u = url.to_string();
        self.rt.block_on(async move {
            let r = http.get(&u).header("Accept", "application/json").send().await.map_err(|e| crate::rpc::scrub(&format!("{e}")))?;
            let st = r.status();
            let body = r.text().await.map_err(|e| format!("{e}"))?;
            if !st.is_success() { return Err(format!("HTTP {}", st.as_u16())); }
            Ok(body)
        })
    }
}

/// Recorded web answers in a directory (tests, `--web-dir`): GeckoTerminal's lists as `gt-trending_5m.json`,
/// `gt-trending_1h.json`, `gt-trending_6h.json`, `gt-new.json`; DexScreener's token pairs as `ds-<mint>.json`. A URL
/// with no file is a failed request
pub struct DirWeb { pub dir: PathBuf, pub asked: Vec<String> }
impl DirWeb {
    pub fn file_of(url: &str) -> Option<String> {
        if let Some(i) = url.find("/token-pairs/v1/solana/") { return Some(format!("ds-{}.json", &url[i + 23..])); }
        if url.contains("/new_pools") { return Some("gt-new.json".into()); }
        url.find("trending_pools?duration=").map(|i| format!("gt-trending_{}.json", &url[i + 24..]))
    }
}
impl Web for DirWeb {
    fn get(&mut self, url: &str) -> std::result::Result<String, String> {
        self.asked.push(url.to_string());
        let f = DirWeb::file_of(url).ok_or_else(|| format!("no recorded answer for {url}"))?;
        std::fs::read_to_string(self.dir.join(&f)).map_err(|e| format!("{f}: {e}"))
    }
}

/// The real chain: the configured providers (failover in order), this process's budget
pub struct RpcChain { rt: tokio::runtime::Runtime, rpc: crate::rpc::Rpc, names: Vec<String> }
impl RpcChain {
    /// `[pool_refresh] rpc`'s endpoints (named `[[rpc.endpoint]]`s, whether or not the segments use them; never Haan's:
    /// the config check refuses it), each at most `rpc_max_rps`
    pub fn new(cfg: &Config) -> Result<RpcChain> {
        let pr = &cfg.pool_refresh;
        let mut eps = Vec::new();
        let mut skipped = Vec::new();
        for n in &pr.rpc {
            let Some(e) = cfg.rpc.endpoints.iter().find(|e| &e.name == n) else { bail!("[pool_refresh] rpc {n:?}: no such [[rpc.endpoint]]") };
            let mut one = cfg.rpc.clone();
            one.url_env = None;
            one.endpoints = vec![crate::config::RpcEndpointCfg { enabled: true, ..e.clone() }];
            let (got, sk) = one.endpoints();
            // review #8: the resolved URL's host, compared without case (a url_env names it only at run time)
            if got.iter().any(|x| is_haan_url(&x.url)) { bail!("[pool_refresh] rpc {n:?}: never Haan"); }
            eps.extend(got);
            skipped.extend(sk);
        }
        if eps.is_empty() { bail!("[pool_refresh] rpc {:?}: no endpoint is usable here (environment missing: {skipped:?})", pr.rpc); }
        let reg = crate::rpc::Registry::global();
        for e in &eps { reg.set_limit(&e.name, pr.rpc_max_rps, Some(1.0)); }
        let names = eps.iter().map(|e| format!("{} ({})", e.name, crate::provenance::host_of(&e.url))).collect();
        let rt = tokio::runtime::Builder::new_current_thread().enable_all().build()?;
        Ok(RpcChain { rt, rpc: crate::rpc::Rpc::race(eps).with_failover(true), names })
    }
}
impl Chain for RpcChain {
    /// one getMultipleAccounts (at most 100 keys), tried 3 times (1.5 s, then 3 s apart: a public endpoint's 429 passes)
    fn accounts(&mut self, keys: &[Pk]) -> std::result::Result<Vec<Option<Account>>, String> {
        let mut last = String::new();
        for attempt in 0..3u64 {
            if attempt > 0 { std::thread::sleep(Duration::from_millis(1_500 * attempt)); }
            let rpc = self.rpc.clone();
            match self.rt.block_on(async move { rpc.accounts(keys).await }) {
                Ok((_, v)) => return Ok(v),
                Err(e) => last = crate::rpc::scrub(&format!("{e:#}")),
            }
        }
        Err(format!("{last} (3 attempts)"))
    }
    fn name(&self) -> String { self.names.join(", ") }
}

/// whether a URL's host is Haan's (any case)
pub fn is_haan_url(url: &str) -> bool {
    crate::rpc::url_host(url).unwrap_or_else(|| url.to_string()).to_ascii_lowercase().contains("haandigital")
}

/// Review #8: what a refresh's environment becomes, from the .env's `pairs`, the `names` its verification endpoints read
/// and the `inherited` variable names: (the variables to set: only those named, never a HAAN one; the inherited ones to
/// remove: every HAAN one)
pub fn env_plan(pairs: Vec<(String, String)>, names: &[String], inherited: Vec<String>) -> (Vec<(String, String)>, Vec<String>) {
    let haan = |k: &str| k.to_ascii_uppercase().contains("HAAN");
    (pairs.into_iter().filter(|(k, _)| names.contains(k) && !haan(k)).collect(), inherited.into_iter().filter(|k| haan(k)).collect())
}

/// Review #8: the environment of a refresh holds only what its verification endpoints name: every inherited HAAN
/// variable is removed, and only `names` are read from the .env `file` (a missing file is fine when nothing is needed).
/// The names loaded, and a warning
pub fn load_env_names(file: &Path, names: &[String]) -> (Vec<String>, Option<String>) {
    let inherited: Vec<String> = std::env::vars_os().map(|(k, _)| k.to_string_lossy().into_owned()).collect();
    let (pairs, warn) = match dotenvy::from_path_iter(file) {
        Ok(it) => (it.flatten().collect::<Vec<_>>(), None),
        Err(e) if !names.is_empty() => (vec![], Some(format!("WARNING: {}: {e}: the verification RPC's variables {names:?} were not loaded", file.display()))),
        Err(_) => (vec![], None),
    };
    let (set, remove) = env_plan(pairs, names, inherited);
    for k in remove { std::env::remove_var(k); }
    let loaded = set.iter().map(|(k, _)| k.clone()).collect();
    for (k, v) in set { std::env::set_var(k, v); }
    (loaded, warn)
}

/// Review #12: below the running segment, for the CPU (nice 10) and for the disk (I/O class idle). Called first: the
/// threads made later inherit both. What it did, for the report
pub fn lower_priority() -> Value {
    let nice = unsafe { libc::nice(10) };
    // ioprio_set(IOPRIO_WHO_PROCESS, 0: this thread, IOPRIO_PRIO_VALUE(IOPRIO_CLASS_IDLE = 3, 0))
    let io = unsafe { libc::syscall(libc::SYS_ioprio_set, 1, 0, 3 << 13) };
    json!({ "nice": nice, "io_class": if io == 0 { "idle".to_string() } else { format!("unchanged: {}", std::io::Error::last_os_error()) } })
}

/// what one source's fetch did
#[derive(Default)]
struct SrcStat { requests: u64, ok: u64, failed: u64, items: u64, ms: f64, errors: Vec<String> }
impl SrcStat {
    fn json(&self, on: bool) -> Value {
        json!({ "enabled": on, "requests": self.requests, "ok": self.ok, "failed": self.failed, "items": self.items, "ms": (self.ms * 10.0).round() / 10.0,
            "status": if !on { "off" } else if self.requests == 0 { "none" } else if self.failed == 0 { "ok" } else if self.ok == 0 { "failed" } else { "partial" },
            "errors": self.errors.iter().take(10).collect::<Vec<_>>() })
    }
    fn err(&mut self, what: &str, e: String) { self.failed += 1; if self.errors.len() < 50 { self.errors.push(format!("{what}: {e}")); } }
}

// ------------------------------------------------------------------ the refresh

/// `arbx pools refresh`'s options
#[derive(Clone, Debug, Default)]
pub struct Opts {
    /// the current list (default: the config's `[pools] seed_csv`)
    pub current: Option<PathBuf>,
    /// segment or campaign directories to read records from
    pub runs: Vec<PathBuf>,
    pub out: PathBuf,
    /// default: `<out>` with `.report.json`
    pub report: Option<PathBuf>,
    /// the segment the new list is for (the `source` tag of what it adds)
    pub segment: String,
    /// replay a refresh from its inputs file (no records read, nothing fetched)
    pub inputs: Option<PathBuf>,
    /// stop fetching and keep the previous list past this long (default: `[pool_refresh] timeout_s` less 15 s)
    pub deadline_s: Option<u64>,
    /// answer the web from recorded files (`DirWeb`) instead of the network (fixtures; the chain is still the RPC)
    pub web_dir: Option<PathBuf>,
    /// the campaign's segment length in minutes: a segment counts toward an idle streak when its triggers cover 80% of it
    /// (default: each segment's own `--minutes`)
    pub segment_min: Option<f64>,
    /// what lowering the process's priority did (`main`), for the report
    pub process: Option<Value>,
}

/// An inputs file (`{schema, inputs}`, as the refresh writes it, or the bare inputs)
pub fn load_inputs(f: &Path) -> Result<Inputs> {
    let v: Value = serde_json::from_slice(&std::fs::read(f).with_context(|| format!("reading {}", f.display()))?).with_context(|| format!("{}: not JSON", f.display()))?;
    let body = if v["schema"].as_str() == Some(INPUTS_SCHEMA) { v["inputs"].clone() } else { v };
    serde_json::from_value(body).with_context(|| format!("{}: not a pool refresh inputs file", f.display()))
}

/// `<out>.report.json` and `<out>.inputs.json` beside the list
pub fn report_path(o: &Opts) -> PathBuf { o.report.clone().unwrap_or_else(|| PathBuf::from(format!("{}.report.json", o.out.display()))) }
pub fn inputs_path(report: &Path) -> PathBuf {
    let s = report.display().to_string();
    PathBuf::from(match s.strip_suffix(".report.json").or_else(|| s.strip_suffix(".json")) { Some(b) => format!("{b}.inputs.json"), None => format!("{s}.inputs.json") })
}

/// The refresh: records, candidates, verification, plan; writes the list, the report and the inputs file (atomically:
/// the list first, then the report naming its sha256). A verification that cannot complete writes the previous list
/// unchanged (`status` `kept_previous`). Returns the report
pub fn refresh(cfg: &Config, o: &Opts, web: &mut dyn Web, chain: &mut dyn Chain) -> Result<Value> {
    let t0 = crate::feeds::clock::now_ns();
    let start = Instant::now();
    let p = &cfg.pool_refresh;
    // review #7: a replay plans with what the refresh had: its policy (a config with another one is refused), its
    // segment, its fetch failure, and the same current list (checked by its sha256)
    let loaded: Option<Inputs> = match &o.inputs { Some(f) => Some(load_inputs(f)?), None => None };
    if let Some(pol) = loaded.as_ref().and_then(|i| i.policy.as_ref()) {
        let (mut a, mut b) = (pol.clone(), p.clone());
        a.enabled = true;
        b.enabled = true;
        if a != b { bail!("the inputs file was planned with another [pool_refresh] policy than this config's: replay it with the config the refresh ran with"); }
    }
    let deadline = start + Duration::from_secs(o.deadline_s.unwrap_or(p.timeout_s.saturating_sub(15).max(15)));
    let current_path = o.current.clone().unwrap_or_else(|| PathBuf::from(&cfg.pools.seed_csv));
    let current_raw = std::fs::read(&current_path).with_context(|| format!("reading the current list {}", current_path.display()))?;
    let current_sha = crate::provenance::sha256_hex(&current_raw);
    if let Some(want) = loaded.as_ref().and_then(|i| i.current_sha256.as_ref()) {
        if *want != current_sha { bail!("{} (sha256 {current_sha}) is not the current list the refresh read (sha256 {want}): pass that one with --current", current_path.display()); }
    }
    let (rows, unreadable) = parse_list(std::str::from_utf8(&current_raw).context("the current list is not UTF-8")?)?;
    let report_p = report_path(o);
    let inputs_p = inputs_path(&report_p);
    // the output directories first: the inputs file is written before the list (a pre-flight writes into a new one)
    for f in [&o.out, &report_p, &inputs_p] {
        if let Some(d) = f.parent().filter(|d| !d.as_os_str().is_empty()) { std::fs::create_dir_all(d).with_context(|| format!("creating {}", d.display()))?; }
    }
    let mut phases = serde_json::Map::new();
    let mut sources = serde_json::Map::new();
    let quotes: Vec<Pk> = p.quotes.iter().map(|q| if q == "USDC" { *USDC } else { *WSOL }).collect();
    let mut rpc_j = json!({ "endpoints": chain.name(), "max_rps": p.rpc_max_rps, "calls": 0, "accounts": 0, "ms": 0.0 });
    let (inp, failure): (Inputs, Option<String>) = if let (Some(f), Some(inp)) = (&o.inputs, loaded) {
        sources.insert("inputs_file".into(), json!(f.display().to_string()));
        let failure = inp.failure.clone();
        (inp, failure)
    } else {
        let mut inp = Inputs::default();
        inp.set_rows(&rows);
        inp.registry = registry_for(cfg);
        // records
        let t = Instant::now();
        let dirs = segment_dirs(&o.runs);
        let n = dirs.len();
        if p.records || p.idle_segments > 0 {
            for (i, d) in dirs.iter().enumerate() { inp.segments.push(read_segment(d, p.records && i + (p.exec_segments as usize) >= n, deadline)); }
        }
        phases.insert("records_ms".into(), json!(t.elapsed().as_millis() as u64));
        let listed_now: HashSet<String> = inp.current.iter().map(|x| x.1.clone()).chain(inp.registry.iter().map(|r| r.pool.clone())).collect();
        let mut cands: Vec<Cand> = Vec::new();
        if p.records {
            let mut seen: BTreeMap<String, (String, u64)> = BTreeMap::new();
            for s in inp.segments.iter().rev().take(p.exec_segments as usize) {
                for (pool, x) in &s.unlisted { if !listed_now.contains(pool) { let e = seen.entry(pool.clone()).or_insert((x.venue.clone(), 0)); e.1 += x.txs; } }
            }
            let mut v: Vec<(String, String, u64)> = seen.into_iter().map(|(k, (v, n))| (k, v, n)).collect();
            v.sort_by(|a, b| b.2.cmp(&a.2).then(a.0.cmp(&b.0)));
            let n_seen = v.len();
            for (pool, venue, n) in v.into_iter().take(p.max_adds.max(1) * RECORD_CANDS_PER_ADD) {
                cands.push(Cand { pool, venue, src: Src::Records, base: None, quote: None, score: n as f64, symbol: None, via: "exec:arb_like".into() });
            }
            sources.insert("records".into(), json!({ "enabled": true, "segments": inp.segments.len(), "unlisted_pools_seen": n_seen, "candidates": cands.len(),
                "status": if inp.segments.is_empty() { "none" } else if inp.segments.iter().all(|s| s.ok) { "ok" } else { "partial" } }));
        } else { sources.insert("records".into(), json!({ "enabled": false, "status": "off" })); }
        // GeckoTerminal
        let t = Instant::now();
        let mut gt = SrcStat::default();
        let mut tokens: Vec<(String, Option<String>)> = Vec::new();
        if p.geckoterminal {
            let base = p.geckoterminal_url.trim_end_matches('/');
            let lists = [("trending_5m", format!("{base}/networks/solana/trending_pools?duration=5m")), ("trending_1h", format!("{base}/networks/solana/trending_pools?duration=1h")),
                ("trending_6h", format!("{base}/networks/solana/trending_pools?duration=6h")), ("new", format!("{base}/networks/solana/new_pools"))];
            for (via, url) in lists {
                if Instant::now() >= deadline { gt.err(via, "deadline".into()); continue; }
                gt.requests += 1;
                match web.get(&url).and_then(|b| parse_gt(&b, &format!("gt:{via}")).map_err(|e| format!("{e:#}"))) {
                    Ok((c, tk)) => { gt.ok += 1; gt.items += c.len() as u64; cands.extend(c); for x in tk { if !tokens.iter().any(|y| y.0 == x.0) { tokens.push(x); } } }
                    Err(e) => gt.err(via, e),
                }
            }
        }
        gt.ms = t.elapsed().as_secs_f64() * 1e3;
        sources.insert("geckoterminal".into(), gt.json(p.geckoterminal));
        // DexScreener: every candidate token's pools
        let t = Instant::now();
        let mut ds = SrcStat::default();
        if p.dexscreener {
            let base = p.dexscreener_url.trim_end_matches('/');
            let min_units = |q: &Pk| if *q == *WSOL { p.min_liquidity_sol } else { p.min_liquidity_usdc };
            for (tok, _) in tokens.iter().take(p.max_tokens) {
                if Instant::now() >= deadline { ds.err("tokens", "deadline".into()); break; }
                ds.requests += 1;
                match web.get(&format!("{base}/token-pairs/v1/solana/{tok}")).and_then(|b| parse_ds(&b, &format!("ds:{tok}"), &quotes, &min_units).map_err(|e| format!("{e:#}"))) {
                    Ok(c) => { ds.ok += 1; ds.items += c.len() as u64; cands.extend(c); }
                    Err(e) => ds.err(tok, e),
                }
            }
        }
        ds.ms = t.elapsed().as_secs_f64() * 1e3;
        let mut dsj = ds.json(p.dexscreener);
        dsj["tokens"] = json!(tokens.len().min(p.max_tokens));
        dsj["tokens_seen"] = json!(tokens.len());
        sources.insert("dexscreener".into(), dsj);
        inp.cands = merge(cands);
        // the chain: round 1 the listed pools and the candidates, round 2 the decodable candidates' vaults and mints and
        // the registry's pools on their pairs
        let t = Instant::now();
        let mut failure = None;
        let mut fetch = |keys: Vec<Pk>, inp: &mut Inputs, rpc_j: &mut Value| -> std::result::Result<(), String> {
            let keys: Vec<Pk> = keys.into_iter().filter(|k| !inp.accounts.contains_key(&b58(k))).collect::<BTreeSet<_>>().into_iter().collect();
            for chunk in keys.chunks(100) {
                if Instant::now() >= deadline { return Err("the deadline passed before the verification completed".into()); }
                let got = chain.accounts(chunk)?;
                if got.len() != chunk.len() { return Err(format!("getMultipleAccounts answered {} accounts for {}", got.len(), chunk.len())); }
                rpc_j["calls"] = json!(rpc_j["calls"].as_u64().unwrap_or(0) + 1);
                rpc_j["accounts"] = json!(rpc_j["accounts"].as_u64().unwrap_or(0) + chunk.len() as u64);
                for (k, a) in chunk.iter().zip(got) { inp.accounts.insert(b58(k), a.as_ref().map(SavedAcct::of)); }
            }
            Ok(())
        };
        let r1: Vec<Pk> = rows.iter().map(|r| r.pool).chain(inp.cands.iter().filter_map(|c| pk_opt(&c.pool))).collect();
        if let Err(e) = fetch(r1, &mut inp, &mut rpc_j) { failure = Some(e); }
        if failure.is_none() {
            let mut r2: Vec<Pk> = Vec::new();
            let mut pairs: HashSet<(Pk, Pk)> = HashSet::new();
            for c in &inp.cands {
                let Some(pool) = pk_opt(&c.pool) else { continue };
                let Some(Some(a)) = inp.accounts.get(&c.pool).map(|a| a.as_ref().and_then(|a| a.account())) else { continue };
                let Some(m) = Venue::of_program(&a.owner).filter(|v| ADD_VENUES.contains(v)).and_then(|v| pools::meta_of(v, &pool, &a.data)) else { continue };
                r2.extend([m.vault0, m.vault1, m.t0, m.t1]);
                pairs.insert(pair_key(&m.t0, &m.t1));
            }
            for r in &inp.registry {
                if let (Some(pool), Some(t0), Some(t1)) = (pk_opt(&r.pool), pk_opt(&r.t0), pk_opt(&r.t1)) { if pairs.contains(&pair_key(&t0, &t1)) { r2.push(pool); } }
            }
            if let Err(e) = fetch(r2, &mut inp, &mut rpc_j) { failure = Some(e); }
        }
        rpc_j["ms"] = json!((t.elapsed().as_secs_f64() * 1e4).round() / 10.0);
        phases.insert("verify_ms".into(), json!(t.elapsed().as_millis() as u64));
        // only the registry pools the plan may count are kept in the inputs (the file stays small)
        let fetched: HashSet<String> = inp.accounts.keys().cloned().collect();
        inp.registry.retain(|r| fetched.contains(&r.pool));
        inp.segment_min = o.segment_min;
        inp.policy = Some(p.clone());
        inp.segment = Some(o.segment.clone());
        inp.failure = failure.clone();
        inp.current_sha256 = Some(current_sha.clone());
        (inp, failure)
    };
    // the inputs file (`--inputs` replays it): one that cannot be written is recorded, never fatal (the list does not need it)
    let inputs_error = serde_json::to_vec(&json!({ "schema": INPUTS_SCHEMA, "inputs": &inp })).map_err(anyhow::Error::from)
        .and_then(|b| crate::control::write_atomic(&inputs_p, &b)).err().map(|e| format!("{e:#}"));
    // the plan, or the previous list
    let t = Instant::now();
    let segment = inp.segment.clone().unwrap_or_else(|| o.segment.clone());
    let planned = match &failure { Some(e) => Err(e.clone()), None => plan(p, &inp, &segment) };
    phases.insert("plan_ms".into(), json!(t.elapsed().as_millis() as u64));
    let (status, reason, body, detail) = match planned {
        Ok(out) => ("ok", Value::Null, list_csv(&out.rows).into_bytes(), out.report),
        Err(e) => ("kept_previous", json!(e), current_raw.clone(), json!({ "counts": { "current": rows.len(), "rows": rows.len(), "kept": rows.len(), "added": 0, "dropped": 0 } })),
    };
    crate::control::write_atomic(&o.out, &body)?;
    let out_sha = crate::provenance::sha256_hex(&body);
    let t1 = crate::feeds::clock::now_ns();
    let mut report = json!({ "schema": SCHEMA, "segment": segment, "status": status, "reason": reason, "t_start_ns": t0, "t_end_ns": t1,
        "duration_ms": start.elapsed().as_millis() as u64, "phases": phases, "policy": p,
        "current": { "path": current_path.display().to_string(), "sha256": current_sha, "rows": rows.len(), "unreadable_rows": unreadable },
        "out": { "path": o.out.display().to_string(), "sha256": out_sha, "rows": parse_list(std::str::from_utf8(&body).unwrap_or("")).map(|x| x.0.len()).unwrap_or(0) },
        "sources": sources, "rpc": rpc_j,
        "records": inp.segments.iter().map(|s| json!({ "segment": s.name, "complete": s.complete, "ok": s.ok, "listed": s.listed.as_ref().map(|l| l.len()),
            "active_pools": s.pools.len(), "unlisted_pools": s.unlisted.len(), "streams": s.streams })).collect::<Vec<_>>(),
        "inputs_file": inputs_p.display().to_string(), "inputs_sha256": std::fs::read(&inputs_p).ok().map(|b| crate::provenance::sha256_hex(&b)),
        "inputs_error": inputs_error, "process": o.process, "segment_min": inp.segment_min });
    if let (Some(r), Some(d)) = (report.as_object_mut(), detail.as_object()) { for (k, v) in d { r.insert(k.clone(), v.clone()); } }
    crate::control::write_atomic(&report_p, format!("{}\n", serde_json::to_string_pretty(&report)?).as_bytes())?;
    Ok(report)
}

/// The report in one line (the CLI, the campaign's log and its Telegram notice)
pub fn summary_line(r: &Value) -> String {
    let c = &r["counts"];
    let tops: Vec<String> = r["top_tokens"].as_array().map(|a| a.iter().take(5).map(|t| {
        let name = t["symbol"].as_str().map(String::from).unwrap_or_else(|| t["token"].as_str().map(|s| format!("{}…", &s[..s.len().min(6)])).unwrap_or_default());
        format!("{name} ({})", t["pools"].as_u64().unwrap_or(0))
    }).collect()).unwrap_or_default();
    let secs = r["duration_ms"].as_u64().unwrap_or(0) as f64 / 1e3;
    match r["status"].as_str() {
        Some("ok") => {
            let n = |k: &str| c[k].as_u64().unwrap_or(0);
            format!("+{} added, -{} dropped, {} kept ({} active, {} idle{}) -> {} pools in {secs:.0} s{}{}", n("added"), n("dropped"), n("kept"), n("kept_active"), n("kept_idle"),
                if n("kept_unconfirmed") > 0 { format!(", {} the RPC called dead but the last boot found alive", n("kept_unconfirmed")) } else { String::new() }, n("rows"),
                if tops.is_empty() { String::new() } else { format!("; new: {}", tops.join(", ")) },
                if n("idle_held") > 0 { format!("; {} idle pools held by the shrink guard", n("idle_held")) } else { String::new() })
        }
        _ => format!("kept the previous list ({} pools) after {secs:.0} s: {}", c["rows"], r["reason"].as_str().unwrap_or("?")),
    }
}

/// `arbx pools refresh`: the refresh with the real web and chain (or the inputs file); prints the summary
pub fn main(cfg: &Config, o: &Opts) -> Result<Value> {
    if !cfg.pool_refresh.enabled { eprintln!("note: [pool_refresh] enabled = false in this config: the refresh runs with its policy anyway"); }
    cfg.pool_refresh.check(&cfg.rpc).map_err(|e| anyhow::anyhow!(e))?;
    // politeness to the running segment: a lower CPU and I/O priority (the records are read on one core)
    let mut o = o.clone();
    o.process = Some(lower_priority());
    let o = &o;
    struct NoWeb;
    impl Web for NoWeb { fn get(&mut self, _: &str) -> std::result::Result<String, String> { Err("offline (--inputs)".into()) } }
    struct NoChain;
    impl Chain for NoChain {
        fn accounts(&mut self, _: &[Pk]) -> std::result::Result<Vec<Option<Account>>, String> { Err("offline (--inputs)".into()) }
        fn name(&self) -> String { "none (--inputs)".into() }
    }
    let r = if o.inputs.is_some() { refresh(cfg, o, &mut NoWeb, &mut NoChain)? } else {
        let mut web: Box<dyn Web> = match &o.web_dir { Some(d) => Box::new(DirWeb { dir: d.clone(), asked: vec![] }), None => Box::new(HttpWeb::new(&cfg.pool_refresh)?) };
        let web = web.as_mut();
        match RpcChain::new(cfg) {
            Ok(mut chain) => refresh(cfg, o, web, &mut chain)?,
            // no usable verification RPC: nothing can be verified, the previous list stays (recorded)
            Err(e) => {
                struct Down(String);
                impl Chain for Down {
                    fn accounts(&mut self, _: &[Pk]) -> std::result::Result<Vec<Option<Account>>, String> { Err(self.0.clone()) }
                    fn name(&self) -> String { "unavailable".into() }
                }
                refresh(cfg, o, web, &mut Down(format!("{e:#}")))?
            }
        }
    };
    println!("pool refresh for {}: {}", o.segment, summary_line(&r));
    println!("list {} (sha256 {}), report {}", r["out"]["path"].as_str().unwrap_or("?"), r["out"]["sha256"].as_str().unwrap_or("?"), report_path(o).display());
    Ok(r)
}

#[cfg(test)]
mod tests;
