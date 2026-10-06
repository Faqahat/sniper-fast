//! Replay of a recorded run, and one route re-priced at one recorded state version (PLAN WP-09 items 1-3; MEASUREMENT
//! §4.13 "Replay", §4.29, §4.50).
//!
//! - **`arbx replay --run <dir>`** rebuilds the run's engine as `arbx run` built it and feeds it the run's inputs, in
//!   order, at their journaled times: the registry the run traded (`pools.json`, and beside it `registry-run.json`: the
//!   pairs in the registry's own order and the state stream's watch list with its accounts' roles; both written by
//!   `arbx run` from WP-09 on), the frozen config (`config.toml`, or `--config`), the boot snapshot (the journal's boot
//!   section and its accounts.bin records: `journal::replay_engine`), then every journal record through
//!   `journal::replay` (the WP-03 / WP-04 replay on the replay clock). What a decision read of the SendGate is the run's
//!   own journaled record (INPUT 3 `src` "decision"), staged ahead of the input whose handling made the decision and
//!   applied at its opportunity (review WP-09 #3); the 100 ms watch samples are status only. The replay records into a
//!   new directory of its own (`--out`; default `./replay-<run>-<unix s>-<pid>`, never inside the run) as a run does
//!   (decisions.jsonl, commits.jsonl, attempts.jsonl, ...; its own journal is switched off: it would not be
//!   replayable), and writes `replay.json`.
//! - **The executor** (the WP-05 merge; review WP-09 "For the WP-05 merge"). A run with an executor journals its
//!   exec_init record (INPUT 12 in the boot section: the lookup tables, PumpSwap's GlobalConfig, the held tokens, the
//!   mode, the size cap, the would-send rate, the tip policy, the crowding map's static list; `exec::ExecInit`). The
//!   replay builds an offline executor from it (`Exec::offline`: no RPC, no send path, no key; it spawns nothing) and
//!   the crowding map; its send checks read the run's decision-point records (the gate's mode and reason, the leader's
//!   kind, the Jito token, the recorder; `Exec::stage_seen`), and the run's settlements (INPUT 9) and the other
//!   executor inputs reach it as they reached the run's. Nothing is sent. Shadow and dry-run executors are replayed, and
//!   (WP-09 part 2) live and canary ones: a decision the run sent is replayed as sent, with the run's signature (the
//!   decision-point `sent` record the run journals right after the send), its fire's result, the block engine's verdicts,
//!   the statuses and the wallet's record from the journal; the record's failed-fee cap and equity guard apply. Not
//!   replayed: an executor recorded before this (no exec_init), or of an exec_init version this build does not rebuild.
//!   A send replayed without its `sent` record (a live or canary recording made before part 2) makes the replay not
//!   whole (`sent_records_missing`).
//! - **Whole.** `ok` (exit 0) needs a whole replay: no journal gap, no account record the journal names missing from
//!   accounts.bin, no accounts.bin gap, every journaled store verdict reproduced, no record dropped by the run's or the
//!   replay's recorder, no executor whose verdicts were not replayed, and every decision-point record the offline
//!   executor read was its own (review WP-09 #2, #4).
//! - **Streaming.** journal.bin and accounts.bin are read one rotation file at a time, and an account record is held
//!   only until the journal names it; the compare reads decisions, commits and attempts a zstd frame at a time, one line
//!   per side at a time (review WP-09 #7).
//! - **`--compare`** diffs the replay's decisions.jsonl and commits.jsonl against the run's into `replay-diff.json`
//!   (field by field; `stages.t_priced` / `stages.t_decided` aside: they are the run's real clock reads), and checks
//!   the run's state and decision digests (events.jsonl `engine_digests`, written by `Engine::finish`; the state digest
//!   folds the executor's state) when the replay ran to the end. With the executor replayed every field is compared,
//!   the executor's verdicts and fields (`sent`, `would_send`, `reason_ungated`, `ev`, `rank`, `crowding`, `attempt`,
//!   `band`) among them, and so are attempts.jsonl's lines (`attempt_projection`: the real clock's stage times, the
//!   LeaderBook's snapshot and a dry run's signature aside). For a recording whose executor was not replayed, its
//!   verdict where the offline engine stands in (`no_executor` / `gate_*`) and its own fields are counted, not
//!   compared, and keep `ok` false. Journal gaps are listed and the decisions inside them are not compared.
//! - **What-if** (`--set key=value`, `--reprice-sizes`): the replay on another `[strategy]` / `[state]` setting, and the
//!   best route of every opportunity re-priced at other sizes at the state its decision priced (X3), in the same pass.
//! - **`arbx quote`** replays up to one state version (an accounts.bin `aseq`, a `slot:write_version`, a transaction's
//!   post-state, or `pre:<txn>`) and prices one route there as a decision prices it (`Engine::quote_route`). `--batch`
//!   answers many in one pass (the toolkit's R4 and R8).
//!
//! Recordings made before WP-03 have no journal and cannot be replayed; recordings made before WP-04 are refused by
//! `journal::replay_engine`; recordings without pools.json and registry-run.json (made before WP-09) are refused. A
//! replay reproduces a run of the same build: replay.json `build` compares the run's (meta.json) with this binary's,
//! and a different one is warned about.
use crate::config::{Config, StrategyCfg};
use crate::engine::{self, Engine, EngineInit};
use crate::feeds::InputKind;
use crate::pools::{pair_key, Registry};
use crate::rec::accounts::{self, AcctRec, AcctRecord, RoleOf, Roles, NO_POOL};
use crate::rec::journal::{self, JBody, JRec};
use crate::rec::{self, Rec};
use crate::tx::{b58, Pk};
use crate::venues::{PoolMeta, Venue};
use anyhow::{bail, Context, Result};
use rustc_hash::{FxHashMap as HashMap, FxHashSet as HashSet};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;

/// pools.json (MEASUREMENT §4.29: a list, no header) and registry-run.json beside it
pub const POOLS_FILE: &str = "pools.json";
pub const REGISTRY_RUN_FILE: &str = "registry-run.json";
pub const REGISTRY_RUN_SCHEMA: &str = "arbx.registry-run/1.0";
/// replay.json, replay-diff.json, reprice.jsonl, `arbx quote` (MEASUREMENT §4.50)
pub const REPLAY_SCHEMA: &str = "arbx.replay/1.0";
pub const DIFF_SCHEMA: &str = "arbx.replay-diff/1.0";
pub const REPRICE_SCHEMA: &str = "arbx.reprice/1.0";
pub const QUOTE_SCHEMA: &str = "arbx.quote/1.0";
/// diff entries written to replay-diff.json at most (all are counted)
const MAX_DIFFS: usize = 2_000;
/// the replay's own recorder is not let run more than this share of a queue ahead (it would drop records)
const BACKPRESSURE_EVERY: u64 = 2_048;
/// how long the replay waits for its recorder's writers to drain a queue before it gives up (a writer that died)
const BACKPRESSURE_GIVE_UP: std::time::Duration = std::time::Duration::from_secs(60);

// ------------------------------------------------------------------ pools.json, registry-run.json

/// The venue's name as the seed lists and pools.json write it (`Venue::parse` reads it back)
pub fn venue_name(v: Venue) -> &'static str {
    match v { Venue::PumpSwap => "PumpSwap", Venue::RayCpmm => "RayCPMM", Venue::RayAmmV4 => "RayAMMv4", Venue::Dlmm => "DLMM", Venue::DammV2 => "DAMMv2" }
}

fn pk_of(v: &Value) -> Result<Pk> {
    let s = v.as_str().context("a public key is not a string")?;
    bs58::decode(s).into_vec().ok().and_then(|b| Pk::try_from(b).ok()).with_context(|| format!("{s}: not a 32-byte base58 key"))
}

/// pools.json (MEASUREMENT §4.29): the registry the segment traded, a list of every pool in registry index order with
/// its index (`idx`, accounts.bin `pool_index`): `[{idx, venue, pool, t0, t1, vault0, vault1, t0_prog, t1_prog, extra,
/// flag, source, tier, pair_key}]`. The analysis toolkit reads it (blockctx attribution, route accounts)
pub fn pools_json(reg: &Registry) -> Value {
    let in_pairs: HashMap<usize, (Pk, Pk)> = reg.pairs.iter().flat_map(|(k, v)| v.iter().map(move |i| (*i, *k))).collect();
    Value::Array(reg.pools.iter().enumerate().map(|(i, m)| json!({
        "idx": i, "venue": venue_name(m.venue), "pool": b58(&m.pool), "t0": b58(&m.t0), "t1": b58(&m.t1), "vault0": b58(&m.vault0), "vault1": b58(&m.vault1),
        "t0_prog": b58(&m.t0_prog), "t1_prog": b58(&m.t1_prog), "extra": m.extra.iter().map(b58).collect::<Vec<_>>(), "flag": m.flag,
        "source": match (reg.seeds.contains(&m.pool), reg.ours.contains(&m.pool)) { (true, true) => "both", (true, false) => "seed", (false, true) => "ours", _ => "none" },
        "tier": in_pairs.contains_key(&i).then_some("A"),
        "pair_key": in_pairs.get(&i).map(|k| format!("{}/{}", b58(&k.0), b58(&k.1))) })).collect())
}

/// registry-run.json (MEASUREMENT §4.29): what a replay needs beside pools.json. The pairs in the registry's own order
/// with each pair's pool order (the order an evaluation prices a pool's routes in), and the state stream's base watch
/// list in order with each account's role (the re-read after a connection reads it in chunks of this order; a replay
/// must ask for the same chunks to accept the run's journaled answers). `pools_sha256` binds it to the pools.json it
/// was written with
pub fn registry_run_json(reg: &Registry, watch: &[Pk], roles: &Roles, pools_sha256: &str) -> Value {
    let pairs: Vec<Value> = reg.pairs.iter().map(|(k, v)| json!({ "key": [b58(&k.0), b58(&k.1)], "pools": v })).collect();
    let watch: Vec<Value> = watch.iter().map(|k| {
        let r = roles.get(k);
        json!({ "pk": b58(k), "role": r.map(|r| accounts::role::name(r.role)), "role_id": r.map(|r| r.role),
            "pool_index": r.and_then(|r| (r.pool_index != NO_POOL).then_some(r.pool_index)) })
    }).collect();
    json!({ "schema": REGISTRY_RUN_SCHEMA, "written_ns": crate::feeds::clock::now_ns(), "producer": crate::provenance::build_short(), "pools_file": POOLS_FILE,
        "pools_sha256": pools_sha256, "n_pools": reg.pools.len(), "n_pairs": reg.pairs.len(), "pairs": pairs, "watch": watch })
}

/// Write `<dir>/pools.json` and `<dir>/registry-run.json` (`arbx run`, right after the boot; the scenario tests).
/// Returns pools.json's sha256 (meta.json `pools.file_sha256`)
pub fn write_pools_json(dir: &Path, reg: &Registry, watch: &[Pk], roles: &Roles) -> Result<String> {
    let bytes = serde_json::to_vec(&pools_json(reg))?;
    let sha = crate::provenance::sha256_hex(&bytes);
    let p = dir.join(POOLS_FILE);
    crate::control::write_atomic(&p, &bytes).with_context(|| format!("writing {}", p.display()))?;
    let p = dir.join(REGISTRY_RUN_FILE);
    crate::control::write_atomic(&p, serde_json::to_string(&registry_run_json(reg, watch, roles, &sha))?.as_bytes()).with_context(|| format!("writing {}", p.display()))?;
    Ok(sha)
}

/// meta.json `pools` (MEASUREMENT §4.2) with the files `write_pools_json` wrote: `file`, `file_sha256`, `registry_run_file`
pub fn meta_pools(mut pools: Value, pools_sha256: &str) -> Value {
    pools["file"] = json!(POOLS_FILE);
    pools["file_sha256"] = json!(pools_sha256);
    pools["registry_run_file"] = json!(REGISTRY_RUN_FILE);
    pools
}

/// A run's registry and watch list, read back from pools.json and registry-run.json
pub struct Pools {
    pub reg: Registry,
    /// the state stream's base watch list, in order, with each account's role
    pub watch: Vec<(Pk, RoleOf)>,
    pub pools_sha256: String,
}

/// Read pools.json (`path`) and the registry-run.json beside it, refusing a pair that does not belong together
pub fn read_pools_json(path: &Path) -> Result<Pools> {
    let bytes = std::fs::read(path).with_context(|| format!("reading {}", path.display()))?;
    let v: Value = serde_json::from_slice(&bytes).with_context(|| format!("{}: not JSON", path.display()))?;
    let list = v.as_array().with_context(|| format!("{}: not a list of pools (MEASUREMENT §4.29)", path.display()))?;
    let mut reg = Registry { pools: vec![], by_pool: Default::default(), pairs: Default::default(), seeds: Default::default(), ours: Default::default() };
    for (n, p) in list.iter().enumerate() {
        anyhow::ensure!(p["idx"].as_u64() == Some(n as u64), "{}: pool {n} has idx {}", path.display(), p["idx"]);
        let venue = p["venue"].as_str().and_then(Venue::parse).with_context(|| format!("{}: pool {n}: venue {}", path.display(), p["venue"]))?;
        let m = PoolMeta { venue, pool: pk_of(&p["pool"])?, t0: pk_of(&p["t0"])?, t1: pk_of(&p["t1"])?, vault0: pk_of(&p["vault0"])?, vault1: pk_of(&p["vault1"])?,
            t0_prog: pk_of(&p["t0_prog"])?, t1_prog: pk_of(&p["t1_prog"])?, extra: p["extra"].as_array().into_iter().flatten().map(pk_of).collect::<Result<_>>()?,
            flag: p["flag"].as_bool().unwrap_or(false) };
        match p["source"].as_str() { Some("both") => { reg.seeds.insert(m.pool); reg.ours.insert(m.pool); } Some("seed") => { reg.seeds.insert(m.pool); }
            Some("ours") => { reg.ours.insert(m.pool); } _ => {} }
        reg.by_pool.insert(m.pool, n);
        reg.pools.push(m);
    }
    let pools_sha256 = crate::provenance::sha256_hex(&bytes);
    let rp = path.with_file_name(REGISTRY_RUN_FILE);
    if !rp.is_file() {
        bail!("{}: no {REGISTRY_RUN_FILE} beside it (the pairs and the watch list a replay needs; written by `arbx run` from WP-09 on, MEASUREMENT §4.29)",
            path.display());
    }
    let r: Value = serde_json::from_slice(&std::fs::read(&rp).with_context(|| format!("reading {}", rp.display()))?)
        .with_context(|| format!("{}: not JSON", rp.display()))?;
    let schema = r["schema"].as_str().unwrap_or("");
    if !schema.starts_with("arbx.registry-run/1.") { bail!("{}: schema {schema:?} is not {REGISTRY_RUN_SCHEMA}", rp.display()); }
    anyhow::ensure!(r["pools_sha256"].as_str() == Some(pools_sha256.as_str()), "{} was not written with this {} (its pools_sha256 is {}, the file's {pools_sha256})",
        rp.display(), path.display(), r["pools_sha256"]);
    for p in r["pairs"].as_array().with_context(|| format!("{}: no `pairs`", rp.display()))? {
        let k = p["key"].as_array().context("registry-run.json: a pair without `key`")?;
        anyhow::ensure!(k.len() == 2, "registry-run.json: a pair key of {} keys", k.len());
        let key = pair_key(&pk_of(&k[0])?, &pk_of(&k[1])?);
        let idx: Vec<usize> = p["pools"].as_array().into_iter().flatten().filter_map(|x| x.as_u64()).map(|x| x as usize).collect();
        anyhow::ensure!(idx.iter().all(|i| *i < reg.pools.len()), "registry-run.json: a pair names a pool past the registry");
        reg.pairs.insert(key, idx);
    }
    let mut watch = Vec::new();
    for w in r["watch"].as_array().with_context(|| format!("{}: no `watch`", rp.display()))? {
        let role = RoleOf { role: w["role_id"].as_u64().unwrap_or(accounts::role::OTHER as u64) as u8,
            pool_index: w["pool_index"].as_u64().map_or(NO_POOL, |x| x as u32) };
        watch.push((pk_of(&w["pk"])?, role));
    }
    Ok(Pools { reg, watch, pools_sha256 })
}

// ------------------------------------------------------------------ a run's inputs

/// What a replay starts from, besides the streams
pub struct Inputs {
    pub dir: PathBuf,
    pub cfg: Config,
    pub config_path: PathBuf,
    pub reg: Arc<Registry>,
    pub watch: Vec<(Pk, RoleOf)>,
    pub pools_path: PathBuf,
    pub pools_sha256: String,
    /// meta.json (the SendGate at the start, the run's build), when the run wrote one
    pub meta: Option<Value>,
}

/// Read a run directory's registry, config and meta, refusing a recording that cannot be replayed (with why)
pub fn inputs(dir: &Path, config: Option<&Path>, pools: Option<&Path>) -> Result<Inputs> {
    anyhow::ensure!(dir.is_dir(), "{}: not a directory", dir.display());
    if rec::stream_files(dir, "journal").is_empty() {
        bail!("{}: no journal.bin: recordings made before WP-03 cannot be replayed (the engine's inputs were not journaled; MEASUREMENT §4.13)", dir.display());
    }
    if rec::stream_files(dir, "accounts").is_empty() { bail!("{}: no accounts.bin: the journal names account updates the recording does not hold", dir.display()); }
    let pools_path = pools.map(Path::to_path_buf).unwrap_or_else(|| dir.join(POOLS_FILE));
    if !pools_path.is_file() {
        bail!("{}: no pools.json, the registry the run traded (written by `arbx run` from WP-09 on; MEASUREMENT §4.29): this recording cannot be replayed \
            without it (give one with --pools, with its registry-run.json beside it)", dir.display());
    }
    let p = read_pools_json(&pools_path)?;
    let config_path = config.map(Path::to_path_buf).unwrap_or_else(|| dir.join("config.toml"));
    let cfg = Config::load(&config_path).with_context(|| format!("the run's config {} (a replay needs the run's own build and config)", config_path.display()))?;
    let meta = std::fs::read(dir.join("meta.json")).ok().and_then(|b| serde_json::from_slice(&b).ok());
    Ok(Inputs { dir: dir.to_path_buf(), cfg, config_path, reg: Arc::new(p.reg), watch: p.watch, pools_path, pools_sha256: p.pools_sha256, meta })
}

/// The run's build (meta.json `build`) against this binary's: the same source is the same commit and the same
/// uncommitted changes (`dirty_sha256`); `same_binary` compares the binaries' sha256 (review WP-09 #12)
pub fn build_check(meta: Option<&Value>) -> Value {
    let me = crate::provenance::build_json();
    let key = |b: &Value| (b["git_commit"].clone(), b["git_dirty"].clone(), b["dirty_sha256"].clone());
    match meta.map(|m| &m["build"]).filter(|b| b.is_object()) {
        None => json!({ "run": null, "replay": me, "same_source": null, "same_binary": null }),
        Some(b) => json!({ "run": b, "replay": me, "same_source": key(b) == key(&me),
            "same_binary": b["binary_sha256"].is_string() && b["binary_sha256"] == me["binary_sha256"] }),
    }
}

/// accounts.bin records by `aseq`, read one rotation file at a time as the journal names them. Each file is in `aseq`
/// order (the aseq is taken and the record queued under one lock), so a record not found once a file past it was read is
/// not in the recording (a gap)
pub struct AcctSource {
    files: Vec<PathBuf>,
    next: usize,
    buf: HashMap<u64, AcctRecord>,
    /// the highest aseq read so far
    max_read: Option<u64>,
    /// GAP records: (first lost aseq, how many)
    pub gaps: Vec<(u64, u64)>,
    pub records: u64,
}

impl AcctSource {
    pub fn open(dir: &Path) -> AcctSource {
        AcctSource { files: rec::stream_files(dir, "accounts"), next: 0, buf: HashMap::default(), max_read: None, gaps: Vec::new(), records: 0 }
    }
    fn load_next(&mut self) -> Result<bool> {
        let Some(p) = self.files.get(self.next).cloned() else { return Ok(false) };
        self.next += 1;
        let bytes = if p.extension().is_some_and(|e| e == "zst") { rec::decode_zst(&p)?.0 } else { std::fs::read(&p)? };
        let parsed = accounts::parse(&bytes).with_context(|| format!("{}", p.display()))?;
        self.gaps.extend(parsed.gaps);
        for r in parsed.records {
            self.records += 1;
            self.max_read = Some(self.max_read.map_or(r.aseq, |m| m.max(r.aseq)));
            self.buf.insert(r.aseq, r);
        }
        Ok(true)
    }
    /// The record `aseq` (removed from the source: each is applied once), or None when the recording does not hold it:
    /// the files are read on only while their records are older than `aseq` (the stream is in `aseq` order across its
    /// rotation files), so a lost record never makes the rest of a recording load at once
    pub fn take(&mut self, aseq: u64) -> Result<Option<AcctRecord>> {
        loop {
            if let Some(r) = self.buf.remove(&aseq) { return Ok(Some(r)); }
            if self.max_read.is_some_and(|m| m >= aseq) { return Ok(None); }
            if !self.load_next()? { return Ok(None); }
        }
    }
    /// every file read to its end (the accounts.bin GAP records of the whole recording)
    fn read_all(&mut self) -> Result<()> {
        while self.load_next()? { self.buf.clear(); }
        Ok(())
    }
}

/// journal.bin records, one rotation file at a time
struct JFiles { files: Vec<PathBuf>, next: usize, cur: std::vec::IntoIter<JRec>, pending: Option<JRec> }

impl JFiles {
    fn open(dir: &Path) -> JFiles { JFiles { files: rec::stream_files(dir, "journal"), next: 0, cur: Vec::new().into_iter(), pending: None } }
    fn next(&mut self) -> Result<Option<JRec>> {
        if let Some(r) = self.pending.take() { return Ok(Some(r)); }
        loop {
            if let Some(r) = self.cur.next() { return Ok(Some(r)); }
            let Some(p) = self.files.get(self.next).cloned() else { return Ok(None) };
            self.next += 1;
            let bytes = if p.extension().is_some_and(|e| e == "zst") { rec::decode_zst(&p)?.0 } else { std::fs::read(&p)? };
            self.cur = journal::parse(&bytes).with_context(|| format!("{}", p.display()))?.1.into_iter();
        }
    }
    fn push_back(&mut self, r: JRec) { self.pending = Some(r); }
}

/// the leading records written before the engine's first input (journal.rs `boot_rec`: t_engine 0, or a GAP among them)
fn is_boot(r: &JRec) -> bool { r.t_engine == 0 || matches!(r.body, JBody::Gap { .. }) }

// ------------------------------------------------------------------ overrides (what-if)

/// One `--set key=value`: `strategy.<field>` (the `[strategy]` section), `state.<knob>` / `alts.<knob>` /
/// `accuracy.ring_versions` / `accuracy.queue` (the engine's knobs, `engine::EngineKnobs`), `min_tip`, or WP-06's
/// `tips.<field>` / `cu.min_samples` (the run's engine_init `builder`)
#[derive(Clone, Debug)]
pub struct Set { pub key: String, pub value: String }

impl std::str::FromStr for Set {
    type Err = anyhow::Error;
    fn from_str(s: &str) -> Result<Set> {
        let (k, v) = s.split_once('=').with_context(|| format!("--set {s}: expected key=value"))?;
        Ok(Set { key: k.trim().to_string(), value: v.trim().to_string() })
    }
}

fn json_value(s: &str) -> Value { serde_json::from_str(s).unwrap_or_else(|_| Value::String(s.to_string())) }

/// set `path` (dot-separated) in `v`, refusing a key it does not have
fn set_path(v: &mut Value, path: &[&str], x: Value, whole: &str) -> Result<()> {
    let (last, head) = path.split_last().context("empty key")?;
    let mut cur = v;
    for p in head { cur = cur.get_mut(*p).with_context(|| format!("--set {whole}: no `{p}`"))?; }
    let o = cur.as_object_mut().with_context(|| format!("--set {whole}: not a section"))?;
    anyhow::ensure!(o.contains_key(*last), "--set {whole}: no such key");
    o.insert(last.to_string(), x);
    Ok(())
}

/// Apply the overrides to the strategy and the run's engine_init (its knobs, min_tip). The strategy hash in the
/// returned init is the new strategy's: the what-if engine starts from it
pub fn apply_sets(cfg: &mut StrategyCfg, init: &mut EngineInit, sets: &[Set]) -> Result<()> {
    if sets.is_empty() { return Ok(()); }
    let mut s = serde_json::to_value(&*cfg)?;
    let mut k = serde_json::to_value(init.knobs.clone().unwrap_or_default())?;
    for x in sets {
        let parts: Vec<&str> = x.key.split('.').collect();
        let val = json_value(&x.value);
        match parts.as_slice() {
            ["strategy", rest @ ..] => set_path(&mut s, rest, val, &x.key)?,
            ["state", rest @ ..] | ["knobs", rest @ ..] => set_path(&mut k, rest, val, &x.key)?,
            ["alts", rest @ ..] => { let mut p = vec!["alts"]; p.extend_from_slice(rest); set_path(&mut k, &p, val, &x.key)?; }
            ["accuracy", "ring_versions"] => set_path(&mut k, &["ring_versions"], val, &x.key)?,
            ["accuracy", "queue"] => set_path(&mut k, &["accuracy_queue"], val, &x.key)?,
            // the tip every net is computed with: a pre-WP-06 journal's min_tip; with WP-06's model, its floor too
            ["min_tip"] => {
                init.min_tip = val.as_u64().with_context(|| format!("--set {}: not a number", x.key))?;
                if let Some(b) = init.builder.as_mut() {
                    b.tips.floor = init.min_tip;
                    b.tips.cap = b.tips.cap.max(init.min_tip);
                    b.tips.check().map_err(|e| anyhow::anyhow!("--set {}: {e}", x.key))?;
                }
            }
            // WP-06: the run's tip model (`tips.floor`, `tips.cap`, `tips.shares`, `tips.contested_shares`) and CU model
            // (`cu.min_samples`)
            ["tips", rest @ ..] | ["cu", rest @ ..] => {
                let b = init.builder.as_mut().with_context(|| format!("--set {}: the run's journal has no WP-06 builder model", x.key))?;
                let mut m = serde_json::to_value(&*b)?;
                let mut p = vec![if parts[0] == "tips" { "tips" } else { "cu" }];
                p.extend_from_slice(rest);
                set_path(&mut m, &p, val, &x.key)?;
                *b = serde_json::from_value(m).with_context(|| format!("--set {}: the builder model does not load", x.key))?;
                b.tips.check().map_err(|e| anyhow::anyhow!("--set {}: {e}", x.key))?;
                anyhow::ensure!(b.cu.min_samples >= 1, "--set {}: cu.min_samples >= 1", x.key);
            }
            _ => bail!("--set {}: unknown key (strategy.<field>, state.<knob>, alts.<knob>, accuracy.ring_versions, accuracy.queue, min_tip, tips.<field>, cu.min_samples)", x.key),
        }
    }
    *cfg = serde_json::from_value(s).context("--set: the [strategy] does not load")?;
    init.knobs = Some(serde_json::from_value(k).context("--set: the knobs do not load")?);
    init.strategy_sha256 = engine::strategy_sha256(cfg);
    Ok(())
}

// ------------------------------------------------------------------ the replay engine

/// The roles `arbx run` gives the accounts it follows: the watch list's, and the DLMM bin arrays the boot store follows
fn roles_of(watch: &[(Pk, RoleOf)], reg: &Registry, store: &crate::store::Store) -> Arc<Roles> {
    let roles = Roles::new(watch.iter().copied());
    roles.add(store.dlmm_arrays.iter().flat_map(|(p, l)| {
        let pi = reg.by_pool.get(p).map_or(NO_POOL, |i| *i as u32);
        l.iter().map(move |(_, k)| (*k, RoleOf { role: accounts::role::DLMM_BIN_ARRAY, pool_index: pi }))
    }).collect::<Vec<_>>());
    Arc::new(roles)
}

/// a journal gap: the lost `seq` range and the engine times around it
#[derive(Clone, Debug, PartialEq)]
pub struct GapAt { pub first_lost_seq: u64, pub n_lost: u64, pub t_before: u64, pub t_after: Option<u64> }

/// The journal's boot section and its account records, read (and checked) before a replay writes anything; the
/// journal and accounts.bin positioned after it
struct Boot {
    jf: JFiles,
    acc: AcctSource,
    records: Vec<JRec>,
    accts: HashMap<u64, AcctRecord>,
    missing: u64,
    gaps: Vec<GapAt>,
    /// the run's engine_init (the overrides not applied)
    init: EngineInit,
    /// the run's executor (review WP-09 "For the WP-05 merge"): none, one to replay from its exec_init record, or one that
    /// is not replayed
    exec: RunExec,
}

/// A run's executor as a replay sees it
#[derive(Clone, Debug)]
pub enum RunExec {
    /// the run had none (engine_init `executor` false)
    None,
    /// replayed: an offline executor made from the run's exec_init record
    Replayed(crate::exec::ExecInit),
    /// not replayed, and why: no exec_init record (a recording made before the executor replay), or one of an earlier
    /// version (before WP-06's builder). WP-09 part 2: a live or canary executor is replayed (`Exec::offline`)
    NotReplayed(String),
}

impl RunExec {
    fn json(&self) -> Value {
        match self {
            RunExec::None => json!({ "run": false, "replayed": false, "mode": null, "why_not": null }),
            RunExec::Replayed(i) => json!({ "run": true, "replayed": true, "mode": i.mode, "why_not": null, "cfg_sha256": i.cfg_sha256 }),
            RunExec::NotReplayed(why) => json!({ "run": true, "replayed": false, "mode": null, "why_not": why }),
        }
    }
}

/// The run's executor from its boot section: replayed when it has an exec_init record (WP-09 part 2: of any mode; a
/// live or canary executor's sends with the run's signatures, its `sent` records), whose config sections the replay's
/// config gives (else refused: the replay would not be the run's)
fn run_exec(inp: &Inputs, init: &EngineInit, records: &[JRec]) -> Result<RunExec> {
    if !init.executor { return Ok(RunExec::None); }
    let Some(v) = journal::exec_init(records) else {
        return Ok(RunExec::NotReplayed("the run had an executor (engine_init executor true) and its journal has no exec_init record: a recording made before the \
            executor replay (WP-09 with WP-05), whose executor verdicts and fields cannot be rebuilt".into()));
    };
    // WP-06: an exec_init record of an earlier version was written by a build whose bundles (their layout, CU, tips) this
    // one does not make: not replayed, with why (the engine's own decisions still are)
    if v["version"].as_u64() != Some(crate::exec::EXEC_INIT_VERSION as u64) {
        return Ok(RunExec::NotReplayed(format!("an exec_init record of version {} (this build writes {}): recorded before WP-06's builder (rent-neutral \
            create+close, measured CU, tips by band), whose bundles this build does not rebuild", v["version"], crate::exec::EXEC_INIT_VERSION)));
    }
    let ei = crate::exec::ExecInit::from_json(v).context("the journal's exec_init record (INPUT 12) does not read")?;
    // ---- WP-09 part 2: a live or canary executor is replayed too (its sends with the run's signatures, from its `sent`
    // records; what came back to the run, from the journal); a send without its record makes the replay not whole
    let mine = crate::exec::cfg_sha256(&inp.cfg);
    anyhow::ensure!(ei.cfg_sha256 == mine, "the config's executor sections (sha256 {}) are not the run's ({}): give the run's frozen config", &mine[..16],
        &ei.cfg_sha256[..16.min(ei.cfg_sha256.len())]);
    Ok(RunExec::Replayed(ei))
}

/// Read the boot section and refuse what cannot be replayed before anything is written (review WP-09 #9): no
/// engine_init, a `[strategy]` that is not the run's, an override the engine does not have, an executor config that is
/// not the run's. `with_exec`: rebuild the run's executor (a replay; a quote reads the store only, and needs none)
fn open_boot(inp: &Inputs, sets: &[Set], with_exec: bool) -> Result<Boot> {
    let mut jf = JFiles::open(&inp.dir);
    let mut acc = AcctSource::open(&inp.dir);
    let mut records = Vec::new();
    while let Some(r) = jf.next()? {
        if !is_boot(&r) { jf.push_back(r); break; }
        records.push(r);
    }
    let init = journal::engine_init(&records).context("the journal has no engine_init record (INPUT 10) this build reads: it was not written by `Engine::run` of WP-03 or later, or its record does not read (a WP-06 builder model of another schema)")?;
    let run_hash = engine::strategy_sha256(&inp.cfg.strategy);
    anyhow::ensure!(init.strategy_sha256 == run_hash, "the config's [strategy] (sha256 {}) is not the run's ({}): give the run's frozen config", &run_hash[..16],
        &init.strategy_sha256[..16.min(init.strategy_sha256.len())]);
    apply_sets(&mut inp.cfg.strategy.clone(), &mut init.clone(), sets)?;
    let exec = if with_exec { run_exec(inp, &init, &records)? } else { RunExec::None };
    let (mut accts, mut missing, mut gaps) = (HashMap::default(), 0, Vec::new());
    for r in &records {
        match r.body {
            JBody::Account { aseq, .. } => match acc.take(aseq)? { Some(a) => { accts.insert(aseq, a); } None => missing += 1 },
            JBody::Gap { first_lost_seq, n_lost } => gaps.push(GapAt { first_lost_seq, n_lost, t_before: 0, t_after: None }),
            _ => {}
        }
    }
    Ok(Boot { jf, acc, records, accts, missing, gaps, init, exec })
}

/// Build the replay's engine from the boot section: the boot store, the run's engine_init (or the what-if overrides on
/// it), the preloaded lookup tables, the watch list and roles, the SendGate as meta.json recorded it at the start (the
/// status lines show it; each decision's gate is the run's journaled record), and the run's executor when it is replayed
/// (an offline one from its exec_init record, on the engine's health, with the crowding map it ranked routes by).
/// `rec`: where it records
fn build_engine(inp: &Inputs, boot: &Boot, sets: &[Set], rec: &Rec) -> Result<(Engine, EngineInit)> {
    let (mut e, init) = if sets.is_empty() {
        journal::replay_engine(inp.reg.clone(), inp.cfg.strategy.clone(), &boot.records, &boot.accts)?
    } else {
        // the what-if path: `replay_engine`'s steps, on the overridden strategy and knobs
        let mut init = boot.init.clone();
        let mut cfg = inp.cfg.strategy.clone();
        apply_sets(&mut cfg, &mut init, sets)?;
        let mut e = Engine::new_offline(inp.reg.clone(), journal::boot_store(&boot.records, &boot.accts, &inp.reg), cfg);
        e.apply_init(&init)?;
        for (t, v) in journal::boot_alts(&boot.records) { e.preload_alt(t, v, None, false); }
        (e, init)
    };
    e.set_rec(rec.clone());
    let roles = roles_of(&inp.watch, &inp.reg, &e.store);
    e.set_acct_rec(AcctRec::new(rec.clone(), roles));
    e.set_base_watch(inp.watch.iter().map(|w| w.0).collect());
    e.gate = inp.meta.as_ref().map(|m| &m["send_gate"]).filter(|g| g.is_object()).and_then(journal::gate_of);
    // ---- WP-09 (review WP-09 "For the WP-05 merge" items 1, 2)
    if let RunExec::Replayed(ei) = &boot.exec {
        e.set_crowding(crate::crowding::Activity::new(ei.crowding_window_h, ei.crowding_buckets, ei.crowded.iter().copied().collect()));
        let mut x = crate::exec::Exec::offline(&inp.cfg, ei, rec.clone())?;
        x.set_health(e.health_flags());
        // review WP-06 #8: a what-if tip model (`tips.*`, `min_tip`) is the executor's too, not only the engine's fee
        if !sets.is_empty() { if let Some(b) = &init.builder { x.set_tip_model(b.tips.clone()); } }
        e.exec = Some(x);
    }
    Ok((e, init))
}

// ------------------------------------------------------------------ the driver

/// What one pass over the journal did
#[derive(Clone, Debug, Default)]
pub struct Drive {
    pub records: u64,
    pub boot_records: u64,
    pub events: u64,
    pub timers: u64,
    pub missing_accounts: u64,
    pub verdict_mismatches: u64,
    /// FT-000 (S1-4): the run's lookup-table evictions (ALT `found` 4 records) and those the replay did not reproduce;
    /// `alts_overridden`: a what-if changed `[alts]` (its evictions differ by design)
    pub alt_evictions: u64,
    pub alt_evict_mismatches: u64,
    pub alts_overridden: bool,
    pub skipped: u64,
    /// INPUT 9 settlements fed back (to the executor)
    pub settled: u64,
    /// decision-point gate records (INPUT 3 `src` "decision"), and those staged for the replay's decisions
    pub gate_observed: u64,
    pub gate_staged: u64,
    pub gaps: Vec<GapAt>,
    /// accounts.bin GAP records: (first lost aseq, how many)
    pub accounts_gaps: Vec<(u64, u64)>,
    /// engine times of the ACCOUNT inputs whose record accounts.bin does not hold (skipped: the store then differs)
    pub missing_at: Vec<u64>,
    /// our own landed transactions the journal names (INPUT 9 `settled` with a landing): (engine time, signature). The
    /// run's engine does not evaluate its own transactions' commit groups (`Engine::on_resolution` asks its executor); an
    /// offline engine has no executor, so a replay of a run that landed transactions evaluates them and differs from the
    /// first one on (until the WP-05 merge gives the replay the executor). INPUT 7 `wallet_tx` is not one: any wallet
    /// transaction (a top-up) has it (review WP-09 #13)
    pub own_landings: Vec<(u64, String)>,
    pub t_first: Option<u64>,
    pub t_last: u64,
    /// the replay stopped before this record (a `--to-slot` or a quote's version): (seq, t_engine)
    pub stopped_at: Option<(u64, u64)>,
    /// the replay's recorder did not drain within `BACKPRESSURE_GIVE_UP` (a writer gone): records may be lost
    pub backpressure_gave_up: bool,
    pub wall_ns: u64,
    /// ---- FT-001: the run's digest points the replay reached, with the replay's digests there (`DigestPlan`); `finished`:
    /// `Engine::finish` ran at the run's `run_end` point (as the run's did: before its stop sequence)
    pub points: Vec<DigestAt>,
    pub finished: bool,
}

/// ---- FT-001. Where a replay digests: at the run's digest-point records (INPUT 14, `Engine::digest_point`: the end of
/// its loop, `run_end`, and of its stop sequence, `stop_end`), doing there what the run did there (`finish` at
/// `run_end`, the executor's `settle_at_stop` at `stop_end`). A recording made before them (FT-001 p1, build 11e25d1) has
/// only events.jsonl's `engine_digests`, taken by `finish` once the run had handled its last record at `t_engine`: the
/// replay digests (and finishes) right after its own last record at or before that time (`legacy`), the run's stop
/// sequence having journaled only later records (its drain reads the clock after `finish`). `on` false: no digest point
/// (`arbx quote`)
#[derive(Clone, Debug, Default)]
pub(crate) struct DigestPlan { pub on: bool, pub legacy: Option<(u64, Value)> }

/// ---- FT-001. Whether `r` is past the digest point of a recording made before INPUT 14: a record after the engine
/// time its `finish` recorded (`t_engine`; the stop sequence's records are later: it reads the clock after `finish`)
pub(crate) fn past_digest_point(r: &JRec, t_engine: u64) -> bool { r.t_engine > t_engine }

/// ---- FT-001. A digest point a replay reached: which (`run_end`, `stop_end`), how it was found (`marker`: the run's
/// INPUT 14 record, at journal `seq`; `inferred_t_engine`: a recording made before the record, at its engine_digests'
/// `t_engine`), the run's digests there, the replay's (for `run_end` before and after `finish`, as the run's) and the
/// replay's counters there
#[derive(Clone, Debug)]
pub struct DigestAt {
    pub point: String,
    pub how: &'static str,
    pub seq: Option<u64>,
    pub t_engine: u64,
    pub run: Value,
    pub before: Option<engine::Digests>,
    pub replay: engine::Digests,
    pub counts: Value,
}

/// ---- FT-001. The replay at the run's digest point: what the run did there, then the replay's digests (`run_end`:
/// `finish`, before and after its bookkeeping; `stop_end`: the executor's `settle_at_stop`, then the digests)
fn at_digest_point(e: &mut Engine, d: &mut Drive, run: Value, how: &'static str, seq: Option<u64>, t_engine: u64) {
    let point = run["point"].as_str().unwrap_or(engine::DIGEST_RUN_END).to_string();
    let (before, replay) = if point == engine::DIGEST_STOP_END {
        if let Some(x) = e.exec.as_mut() { x.settle_at_stop(); }
        (None, e.digest_point(engine::DIGEST_STOP_END, None))
    } else if d.finished {
        // a second run_end (not written by `arbx run`): the state as it is
        (None, e.digests())
    } else {
        d.finished = true;
        let (b, a) = e.finish();
        (Some(b), a)
    };
    d.points.push(DigestAt { point, how, seq, t_engine, run, before, replay, counts: e.counts_json() });
}

/// What a pass does around each record (a quote's version, the repricing, `--to-slot`)
trait Hook {
    /// before `r` is handled; false: stop before it
    fn before(&mut self, _e: &mut Engine, _r: &JRec, _aseq: Option<u64>) -> Result<bool> { Ok(true) }
    /// after `r` was handled; false: stop
    fn after(&mut self, _e: &mut Engine, _r: &JRec, _aseq: Option<u64>) -> Result<bool> { Ok(true) }
}

/// One pass: the boot section builds the engine, then every record is handed to `journal::replay` in order (one at a
/// time with the decision-point gate records the run wrote while handling it, which `journal::replay` stages ahead of
/// it; the hooks act between records); `rec` is the replay's recorder (or off). FT-001: at the run's digest points
/// (`plan`) the replay digests and does what the run did there (`at_digest_point`)
fn drive(inp: &Inputs, boot: Boot, sets: &[Set], rec: &Rec, hook: &mut dyn Hook, plan: &DigestPlan) -> Result<(Engine, EngineInit, Drive)> {
    let t0 = std::time::Instant::now();
    let mut d = Drive { boot_records: boot.records.len() as u64, missing_accounts: boot.missing, gaps: boot.gaps.clone(),
        alts_overridden: sets.iter().any(|x| x.key.starts_with("alts.") || x.key.starts_with("knobs.alts.")), ..Default::default() };
    let (mut e, init) = build_engine(inp, &boot, sets, rec)?;
    let Boot { mut jf, mut acc, .. } = boot;
    let none: HashMap<u64, AcctRecord> = HashMap::default();
    let mut one: HashMap<u64, AcctRecord> = HashMap::default();
    let caps = rec.recorder().map(|r| (r.cfg.queue_core, r.cfg.queue_chain, r.cfg.queue_bulk, r.cfg.queue_journal));
    // a recording made before the digest-point records: the run's digest point is right before its first record after
    // the time the run digested at (reached once, unless a record of the run's says where it is)
    let mut legacy = plan.legacy.clone().filter(|_| plan.on);
    while let Some(r) = jf.next()? {
        d.records += 1;
        if let JBody::Gap { first_lost_seq, n_lost } = r.body {
            d.gaps.push(GapAt { first_lost_seq, n_lost, t_before: d.t_last, t_after: None });
            continue;
        }
        if let Some(g) = d.gaps.last_mut() { if g.t_after.is_none() { g.t_after = Some(r.t_engine); } }
        // ---- FT-001: the run's digest point
        if let Some(v) = journal::digest_point(&r) {
            legacy = None;
            if plan.on { at_digest_point(&mut e, &mut d, v.clone(), "marker", Some(r.seq), r.t_engine); }
            continue;
        }
        if let Some((t, v)) = legacy.take_if(|(t, _)| past_digest_point(&r, *t)) { at_digest_point(&mut e, &mut d, v, "inferred_t_engine", None, t); }
        let aseq = match r.body { JBody::Account { aseq, .. } => Some(aseq), _ => None };
        if !hook.before(&mut e, &r, aseq)? { d.stopped_at = Some((r.seq, r.t_engine)); break; }
        d.t_first.get_or_insert(r.t_engine);
        d.t_last = d.t_last.max(r.t_engine);
        // the decision-point gate records the run wrote while handling `r` follow it (TICK records may sit between)
        let mut group = vec![r];
        while let Some(n) = jf.next()? {
            if journal::is_gate_decision(&n) || matches!(n.body, JBody::Tick) { d.records += 1; group.push(n); } else { jf.push_back(n); break; }
        }
        let r = &group[0];
        if let JBody::Input { kind, data } = &r.body {
            // (a failed landing writes no pool account: only successful ones open commit groups)
            if *kind == InputKind::Settled as u8 && data["error"].is_null() {
                if let Some(sig) = data["landed"]["sig"].as_str() { d.own_landings.push((r.t_engine, sig.to_string())); }
            }
        }
        let st = match aseq {
            Some(a) => match acc.take(a)? {
                Some(rec_a) => { one.clear(); one.insert(a, rec_a); journal::replay(&mut e, &group, &one)? }
                None => {
                    d.missing_accounts += 1;
                    d.missing_at.push(r.t_engine);
                    // the input is skipped; the gate records after it are still the run's
                    journal::replay(&mut e, &group[1..], &none)?
                }
            },
            None => journal::replay(&mut e, &group, &none)?,
        };
        d.events += st.events;
        d.timers += st.timers;
        d.missing_accounts += st.missing_accounts;
        d.verdict_mismatches += st.verdict_mismatches;
        d.alt_evictions += st.alt_evictions;
        d.alt_evict_mismatches += st.alt_evict_mismatches;
        d.skipped += st.skipped;
        d.settled += st.settled;
        d.gate_observed += st.gate_observed;
        d.gate_staged += st.gate_staged;
        // an offline engine keeps the fetches it would have sent; a replay has the run's answers in the journal
        if d.records % 4_096 < group.len() as u64 { e.offline_fetches.clear(); e.offline_reads.clear(); }
        if !hook.after(&mut e, r, aseq)? { d.stopped_at = Some((r.seq, r.t_engine)); break; }
        if let (Some((qc, qch, qb, qj)), Some(rr)) = (caps, rec.recorder()) {
            if d.records % BACKPRESSURE_EVERY < group.len() as u64 && !d.backpressure_gave_up {
                // the replay runs far faster than a run: let the writers catch up rather than drop a record
                let full = |rr: &rec::Recorder| rr.depth(rec::DECISIONS) * 4 > qc || rr.depth(rec::TRIGGERS) * 4 > qch || rr.depth(rec::RIVALS) * 4 > qb
                    || rr.depth(rec::JOURNAL) * 4 > qj;
                let since = std::time::Instant::now();
                while full(rr) {
                    if since.elapsed() > BACKPRESSURE_GIVE_UP { d.backpressure_gave_up = true; break; }
                    std::thread::sleep(std::time::Duration::from_micros(500));
                }
            }
        }
    }
    // (a recording whose last record is the one the run digested after: its digest point is the end)
    if d.stopped_at.is_none() { if let Some((t, v)) = legacy.take() { at_digest_point(&mut e, &mut d, v, "inferred_t_engine", None, t); } }
    if d.stopped_at.is_none() { acc.read_all()?; }
    d.accounts_gaps = acc.gaps.clone();
    d.wall_ns = t0.elapsed().as_nanos() as u64;
    Ok((e, init, d))
}

// ------------------------------------------------------------------ arbx replay

/// `--reprice-sizes`: fractions of the decision's size, and `opt` (the best size up to the ladder's top rung)
#[derive(Clone, Debug, PartialEq)]
pub enum Reprice { Frac(f64), Opt }

impl std::str::FromStr for Reprice {
    type Err = anyhow::Error;
    fn from_str(s: &str) -> Result<Reprice> {
        let s = s.trim();
        if s == "opt" { return Ok(Reprice::Opt); }
        let f: f64 = s.parse().with_context(|| format!("--reprice-sizes {s}: a fraction or `opt`"))?;
        anyhow::ensure!(f > 0.0 && f <= 1.0, "--reprice-sizes {s}: a fraction in (0, 1]");
        Ok(Reprice::Frac(f))
    }
}

/// `arbx replay` options
#[derive(Clone, Debug, Default)]
pub struct Opts {
    pub from_slot: Option<u64>,
    pub to_slot: Option<u64>,
    pub config: Option<PathBuf>,
    pub pools: Option<PathBuf>,
    /// a new directory (refused if it exists); default `./replay-<run>-<unix s>-<pid>` (`default_out`)
    pub out: Option<PathBuf>,
    pub compare: bool,
    pub sets: Vec<Set>,
    pub reprice: Vec<Reprice>,
}

/// What `replay` did
pub struct Report {
    pub out: PathBuf,
    /// replay.json
    pub summary: Value,
    /// replay-diff.json (with `--compare`)
    pub diff: Option<Value>,
    /// the replay was whole (`not_whole` empty) and, with `--compare`, found no difference
    pub ok: bool,
    pub digest: u64,
    pub decision_digest: u64,
}

/// The default `--out`: a new directory in the current directory, named after the run, the time and this process.
/// Never inside the run (its recording stays as the run wrote it) and never beside it (a campaign directory holds only
/// segments: the supervisor and the toolkit list it)
pub fn default_out(run: &Path) -> PathBuf {
    let name = run.file_name().map(|s| s.to_string_lossy().into_owned()).unwrap_or_else(|| "run".into());
    PathBuf::from(format!("replay-{name}-{}-{}", crate::feeds::clock::real_ns() / 1_000_000_000, std::process::id()))
}

/// Create the replay's directory, exclusively: two replays never share one (review WP-09 #9)
fn claim_out(out: &Path) -> Result<()> {
    if let Some(p) = out.parent().filter(|p| !p.as_os_str().is_empty()) { std::fs::create_dir_all(p).with_context(|| format!("creating {}", p.display()))?; }
    match std::fs::create_dir(out) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => bail!("{}: already exists: a replay writes into a new directory (choose another --out)", out.display()),
        Err(e) => Err(e).with_context(|| format!("creating {}", out.display())),
    }
}

/// `--to-slot`: stop once the chain tip passes it; `--reprice-sizes` in the same pass
struct MainHook<'a> { to_slot: Option<u64>, reprice: Option<RepriceHook<'a>> }
impl Hook for MainHook<'_> {
    fn before(&mut self, e: &mut Engine, _r: &JRec, _a: Option<u64>) -> Result<bool> { Ok(self.to_slot.map_or(true, |m| e.tip_slot() <= m)) }
    fn after(&mut self, e: &mut Engine, r: &JRec, a: Option<u64>) -> Result<bool> {
        if let Some(h) = self.reprice.as_mut() { h.after(e, r, a)?; }
        Ok(true)
    }
}

/// The run's losses that make a replay not whole (review WP-09 #2): journal gaps, account records the journal names
/// that accounts.bin lacks, accounts.bin gaps, store verdicts not reproduced, records the run's recorder dropped
/// (manifest.json: journal, accounts, decisions, commits), the replay's own recorder drops, an executor not replayed
fn not_whole(run: &Path, d: &Drive, replay_dropped: u64, exec: &RunExec, uses: RecordUse, what_if: bool) -> Vec<Value> {
    let mut v = Vec::new();
    if !d.gaps.is_empty() {
        v.push(json!({ "why": "journal_gap", "n": d.gaps.len(), "records_lost": d.gaps.iter().map(|g| g.n_lost).sum::<u64>(),
            "detail": "journal records lost (GAP records): the decisions inside are not compared and the store may differ after" }));
    }
    if d.missing_accounts > 0 {
        v.push(json!({ "why": "accounts_missing", "n": d.missing_accounts, "detail": "account records the journal names are not in accounts.bin: their inputs were skipped" }));
    }
    if !d.accounts_gaps.is_empty() {
        v.push(json!({ "why": "accounts_gap", "n": d.accounts_gaps.len(), "records_lost": d.accounts_gaps.iter().map(|g| g.1).sum::<u64>(),
            "detail": "accounts.bin records lost (GAP records)" }));
    }
    if d.verdict_mismatches > 0 {
        v.push(json!({ "why": "verdict_mismatch", "n": d.verdict_mismatches, "detail": "ACCOUNT records whose journaled store verdict the replayed store does not give: the replayed store diverged" }));
    }
    if d.alt_evict_mismatches > 0 && !d.alts_overridden {
        v.push(json!({ "why": "alt_evict_mismatch", "n": d.alt_evict_mismatches, "detail": "lookup-table evictions (ALT found 4) the replay did not reproduce: its cache diverged" }));
    }
    let manifest: Option<Value> = std::fs::read(run.join("manifest.json")).ok().and_then(|b| serde_json::from_slice(&b).ok());
    for s in manifest.as_ref().and_then(|m| m["streams"].as_array()).into_iter().flatten() {
        let name = s["name"].as_str().unwrap_or("");
        if !matches!(name, "journal" | "accounts" | "decisions" | "commits") { continue; }
        let lost: u64 = ["dropped_total", "suppressed_total", "io_lost_total", "encode_errors_total"].iter().filter_map(|k| s[*k].as_u64()).sum();
        if lost > 0 { v.push(json!({ "why": "run_recorder_loss", "stream": name, "n": lost, "detail": "the run's recorder lost records of this stream (manifest.json)" })); }
    }
    for q in ["core", "accounts", "journal"] {
        let lost = manifest.as_ref().and_then(|m| m["queues"][q]["lost_at_close"].as_u64()).unwrap_or(0);
        if lost > 0 { v.push(json!({ "why": "run_recorder_loss", "queue": q, "n": lost, "detail": "records still queued when the run's recorder closed (manifest.json)" })); }
    }
    if replay_dropped > 0 || d.backpressure_gave_up {
        v.push(json!({ "why": "replay_recorder_loss", "n": replay_dropped, "detail": "the replay's own recorder dropped records (its decisions and commits are incomplete)" }));
    }
    // ---- WP-09 (review WP-09 "For the WP-05 merge" items 6, 9): an executor recorded before the executor replay (no
    // exec_init) or a sending one is not replayed; a replayed one must have read the run's records as its own
    if let RunExec::NotReplayed(why) = exec { v.push(json!({ "why": "executor_not_replayed", "n": 1, "detail": why })); }
    // (a what-if decides other opportunities than the run by design: its use of the run's records is reported, not a loss)
    if what_if { return v; }
    if uses.mismatch > 0 {
        v.push(json!({ "why": "decision_records_mismatch", "n": uses.mismatch, "detail": "decision-point records (INPUT 3 `src` \"decision\") the replay's executor read \
            that were not its own: staged at another opportunity, unreadable, or naming another target slot or leader than the replay's (the replay diverged)" }));
    }
    if uses.missing > 0 {
        v.push(json!({ "why": "decision_records_missing", "n": uses.missing, "detail": "executor decisions the replay made before any decision-point record (they read the \
            gate as stopped: fail closed)" }));
    }
    if uses.unused > 0 {
        v.push(json!({ "why": "decision_records_unused", "n": uses.unused, "detail": "decision-point records no decision of the replay read: the run decided \
            opportunities the replay did not (the replay diverged)" }));
    }
    if uses.sent_missing > 0 {
        v.push(json!({ "why": "sent_records_missing", "n": uses.sent_missing, "detail": "sends the replay's executor made without the run's `sent` record (the \
            attempt's signature): a live or canary recording made before WP-09 part 2, or a replay that diverged" }));
    }
    v
}

/// ---- WP-09. What a replay made of the run's decision-point records: records its executor read that were not its own
/// (`Exec::seen_mismatch`), executor decisions before any record (`seen_missing`), records left unread by a replay that
/// ran to the end; WP-09 part 2: sends replayed without the run's `sent` record (`Exec::sent_missing`)
#[derive(Clone, Copy, Debug, Default)]
struct RecordUse { mismatch: u64, missing: u64, unused: u64, sent_missing: u64 }

/// The run's digests as `Engine::finish` and `Engine::digest_point` recorded them (events.jsonl `engine_digests`; review
/// WP-09 #6), in order
fn run_digests(run: &Path) -> Vec<Value> {
    rec::read_jsonl(run, "events").unwrap_or_default().into_iter().filter(|e| e["kind"] == "engine_digests").map(|e| e["detail"].clone()).collect()
}

/// ---- FT-001. Where the replay digests (`DigestPlan`): at the run's digest-point records; for a recording made before
/// them (no `point` in its engine_digests), after its last record at or before the `t_engine` its `finish` recorded
pub(crate) fn digest_plan(run_events: &[Value]) -> DigestPlan {
    let legacy = if run_events.iter().any(|v| v.get("point").is_some()) { None }
        else { run_events.last().and_then(|v| v["t_engine"].as_u64().map(|t| (t, v.clone()))) };
    DigestPlan { on: true, legacy }
}

/// ---- FT-001. The counters of a digest point that differ, run vs replay: `{counter: [run, replay]}` (engine's and
/// executor's; null: a record written before FT-001 has none)
fn counts_differ(run: &Value, replay: &Value) -> Value {
    if !run["counts"].is_object() { return Value::Null; }
    let mut out = serde_json::Map::new();
    for (side, prefix) in [("engine", ""), ("exec", "exec.")] {
        let (a, b) = (run["counts"][side].as_object(), replay[side].as_object());
        let keys: std::collections::BTreeSet<&String> = a.into_iter().flat_map(|m| m.keys()).chain(b.into_iter().flat_map(|m| m.keys())).collect();
        for k in keys {
            let (x, y) = (a.and_then(|m| m.get(k)).cloned().unwrap_or(json!(0)), b.and_then(|m| m.get(k)).cloned().unwrap_or(json!(0)));
            if x != y { out.insert(format!("{prefix}{k}"), json!([x, y])); }
        }
    }
    Value::Object(out)
}

/// The digests check (review WP-09 #6; FT-001): at each of the run's digest points the replay reached, the run's state
/// and decision digests (for `run_end` before and after `finish`) against the replay's taken at the same point of the
/// journal, with the parts and counters that differ. Not checked (never a difference): a what-if, a replay that stopped
/// before the point, a run that recorded no digests, a recording whose digest point is unknown (made before the
/// digest-point records, with no `t_engine` to place it by). `end`: the replay's digests at the end of the journal
fn digests_check(run_events: &[Value], d: &Drive, end: &engine::Digests, sets: &[Set]) -> Value {
    let hex = |x: u64| format!("{x:016x}");
    let same_as = |rec: &Value, mine: &engine::Digests| rec["digest"].as_str() == Some(hex(mine.state).as_str())
        && rec["decision_digest"].as_str() == Some(hex(mine.decision).as_str());
    let points: Vec<Value> = d.points.iter().map(|p| {
        let rb = &p.run["before_finish"];
        let before_same = p.before.as_ref().filter(|_| rb.is_object()).map(|b| same_as(rb, b));
        let same = same_as(&p.run, &p.replay) && before_same != Some(false);
        let mut replay = p.replay.json();
        if let Some(b) = &p.before { replay["before_finish"] = b.json(); }
        let mut run = p.run.clone();
        if let Some(o) = run.as_object_mut() { o.remove("counts"); }
        json!({ "point": p.point, "how": p.how, "seq": p.seq, "t_engine": p.t_engine, "same": same, "before_finish_same": before_same,
            "parts_differ": p.replay.parts_differ(&p.run), "before_finish_parts_differ": p.before.as_ref().and_then(|b| b.parts_differ(rb)),
            "counts_differ": counts_differ(&p.run, &p.counts), "run": run, "replay": replay })
    }).collect();
    let why_not = if !sets.is_empty() { Some("what-if (--set)") }
        else if !points.is_empty() { None }
        else if d.stopped_at.is_some() { Some("the replay stopped early (--to-slot), before the run's digest point") }
        else if run_events.is_empty() { Some("not recorded (a run before WP-09, or one that ended before Engine::finish): the digest point is unknown") }
        else { Some("the digest point is unknown: the run's digest-point record is not in its journal (a recording made before FT-001's record whose \
            engine_digests has no t_engine, or the record was lost)") };
    let same = why_not.is_none().then(|| points.iter().all(|p| p["same"] == json!(true)));
    // review WP-09 #6's fields: the run's `run_end` digests and the replay's there (else the replay's at the end)
    let run_end = points.iter().find(|p| p["point"] == engine::DIGEST_RUN_END);
    json!({ "checked": same.is_some(), "same": same, "not_checked": why_not,
        "point": run_end.map(|p| p["how"].clone()), "points": points,
        "run": run_end.map(|p| p["run"].clone()).or_else(|| run_events.last().cloned()),
        "replay": run_end.map_or_else(|| end.json(), |p| p["replay"].clone()),
        "replay_end": end.json() })
}

/// Replay a run directory (see the module doc). Writes into `o.out`: the replay's own streams, `replay.json`, and with
/// `--compare` `replay-diff.json`, with `--reprice-sizes` `reprice.jsonl`
pub fn replay(run: &Path, o: &Opts) -> Result<Report> {
    let inp = inputs(run, o.config.as_deref(), o.pools.as_deref())?;
    // everything that can be refused is, before anything is written (review WP-09 #9)
    let boot = open_boot(&inp, &o.sets, true)?;
    let want = if o.reprice.is_empty() { None } else { Some(opportunities(run, &Window { from_slot: o.from_slot, to_slot: o.to_slot, t_cut: None })?) };
    let build = build_check(inp.meta.as_ref());
    if build["same_source"] == json!(false) {
        rec::err_line(&format!("arbx replay: WARNING: {} was recorded by another build ({} dirty {}) than this one ({} dirty {}): differences may be the build's",
            run.display(), build["run"]["git_commit"], build["run"]["git_dirty"], build["replay"]["git_commit"], build["replay"]["git_dirty"]));
    }
    let out = o.out.clone().unwrap_or_else(|| default_out(run));
    claim_out(&out)?;
    let rec = rec::start(rec::Opts { dir: out.clone(), run: format!("replay:{}", run.file_name().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default()),
        producer: crate::provenance::build_short(), cfg: Default::default(), feeds: vec![], monitor: false, echo: Some(Box::new(std::io::sink())) })?;
    // the replay's own journal would not be replayable (it has no boot snapshot): not written (review WP-09 #9)
    if let Some(r) = rec.recorder() { r.switch_off(|s| s.name == "journal"); }
    let mut cfg = inp.cfg.strategy.clone();
    apply_sets(&mut cfg, &mut boot.init.clone(), &o.sets)?;
    let cap = (cfg.sizes_sol.iter().cloned().fold(0.0, f64::max) * 1e9) as u64;
    let n_want = want.as_ref().map_or(0, |w| w.len());
    let fee_rule = if boot.init.builder.is_some() { "tips_by_band" } else { "legacy" };
    let mut hook = MainHook { to_slot: o.to_slot, reprice: want.map(|w| RepriceHook { want: w, sizes: &o.reprice, cfg, cap, seen: 0, out: Vec::new(), fee_rule }) };
    let run_exec = boot.exec.clone();
    // FT-001: the run's digest points (its INPUT 14 records; a recording made before them, its engine_digests' time)
    let run_events = run_digests(run);
    let res = drive(&inp, boot, &o.sets, &rec, &mut hook, &digest_plan(&run_events));
    let (mut e, init, d) = match res { Ok(x) => x, Err(err) => { rec.close(); return Err(err); } };
    let uses = RecordUse { mismatch: e.exec.as_ref().map_or(0, |x| x.seen_mismatch), missing: e.exec.as_ref().map_or(0, |x| x.seen_missing),
        unused: if d.stopped_at.is_none() { e.gate_seen.script.len() as u64 } else { 0 }, sent_missing: e.exec.as_ref().map_or(0, |x| x.sent_missing) };
    // `finish` ran at the run's `run_end` point (where the run's did, before its stop sequence); else here, at the end
    if !d.finished { e.finish(); }
    let end = e.digests();
    let (digest, decision_digest) = (end.state, end.decision);
    rec.close();
    let rec_stats = rec.stats();
    let dropped: u64 = rec_stats.as_ref().map_or(0, |s| s.dropped.iter().map(|x| x.1).sum::<u64>() + s.io_lost.iter().map(|x| x.1).sum::<u64>());
    let span_ns = d.t_first.map_or(0, |t| d.t_last.saturating_sub(t));
    let window = Window { from_slot: o.from_slot, to_slot: o.to_slot, t_cut: d.stopped_at.map(|s| s.1) };
    let losses = not_whole(run, &d, dropped, &run_exec, uses, !o.sets.is_empty());
    let whole = losses.is_empty();
    let digests = digests_check(&run_events, &d, &end, &o.sets);
    let mut diff = if o.compare { Some(compare(run, &out, &window, &d, &run_exec, !o.sets.is_empty(), &digests)?) } else { None };
    let differences_ok = diff.as_ref().map_or(true, |x| x["summary"]["differences_ok"] == json!(true));
    let ok = whole && differences_ok;
    if let Some(x) = diff.as_mut() {
        x["whole"] = json!(whole);
        x["not_whole"] = json!(losses);
        x["summary"]["whole"] = json!(whole);
        x["summary"]["ok"] = json!(ok);
        x["ok"] = json!(ok);
    }
    let reprice = match hook.reprice { Some(h) => Some(write_reprice(&inp, h, n_want, &o.reprice, &out, init.min_tip)?), None => None };
    let summary = json!({
        "schema": REPLAY_SCHEMA, "run": run.display().to_string(), "out": out.display().to_string(), "producer": crate::provenance::build_short(),
        "build": build, "config": inp.config_path.display().to_string(), "pools_file": inp.pools_path.display().to_string(), "pools_sha256": inp.pools_sha256,
        "pools": inp.reg.pools.len(), "pairs": inp.reg.pairs.len(),
        "engine_init": { "min_tip": init.min_tip, "executor": init.executor, "strategy_sha256": init.strategy_sha256, "knobs": init.knobs },
        "executor_replayed": !matches!(run_exec, RunExec::NotReplayed(_)),
        "executor": { "run": init.executor, "replayed": matches!(run_exec, RunExec::Replayed(_)), "exec_init": run_exec.json(), "records_staged": d.gate_staged,
            "records_mismatch": uses.mismatch, "records_missing": uses.missing, "records_unused": uses.unused, "settled_fed": d.settled,
            "sent_missing": uses.sent_missing },
        "overrides": o.sets.iter().map(|s| format!("{}={}", s.key, s.value)).collect::<Vec<_>>(),
        "window": { "from_slot": o.from_slot, "to_slot": o.to_slot, "stopped_at_seq": d.stopped_at.map(|s| s.0), "stopped_at_t_ns": d.stopped_at.map(|s| s.1) },
        "journal": { "boot_records": d.boot_records, "records": d.records, "events": d.events, "timers": d.timers, "skipped_inputs": d.skipped,
            "gate_observed": d.gate_observed, "gate_staged": d.gate_staged, "alt_evictions": d.alt_evictions, "alt_evict_mismatches": d.alt_evict_mismatches,
            "t_first_ns": d.t_first, "t_last_ns": d.t_last, "span_ms": span_ns as f64 / 1e6,
            "gaps": d.gaps.iter().map(|g| json!({ "first_lost_seq": g.first_lost_seq, "n_lost": g.n_lost, "t_before": g.t_before, "t_after": g.t_after })).collect::<Vec<_>>() },
        "accounts": { "missing": d.missing_accounts, "verdict_mismatches": d.verdict_mismatches,
            "gaps": d.accounts_gaps.iter().map(|g| json!({ "first_lost_aseq": g.0, "n_lost": g.1 })).collect::<Vec<_>>() },
        "wall_ms": d.wall_ns as f64 / 1e6, "speed_x": if d.wall_ns > 0 { span_ns as f64 / d.wall_ns as f64 } else { 0.0 },
        "digest": format!("{digest:016x}"), "decision_digest": format!("{decision_digest:016x}"), "digests": digests,
        "recorder_dropped": dropped, "whole": whole, "not_whole": losses,
        "compare": diff.as_ref().map(|x| x["summary"].clone()), "reprice": reprice,
        "ok": ok,
    });
    std::fs::write(out.join("replay.json"), serde_json::to_string_pretty(&summary)?)?;
    if let Some(x) = &diff { std::fs::write(out.join("replay-diff.json"), serde_json::to_string_pretty(x)?)?; }
    Ok(Report { out, summary, diff, ok, digest, decision_digest })
}

// ------------------------------------------------------------------ --compare

/// The decisions a compare looks at: trigger slots in [from, to], and no later than where the replay stopped
#[derive(Clone, Debug, Default)]
pub struct Window { pub from_slot: Option<u64>, pub to_slot: Option<u64>, pub t_cut: Option<u64> }

impl Window {
    fn holds(&self, d: &Value) -> bool {
        let slot = d["trigger"]["slot"].as_u64().unwrap_or(0);
        let t = d["t_ns"].as_u64().unwrap_or(0);
        self.from_slot.map_or(true, |f| slot >= f) && self.to_slot.map_or(true, |m| slot <= m) && self.t_cut.map_or(true, |c| t < c)
    }
}

/// MEASUREMENT A.1: the stage of a decision reason
pub fn reason_stage(r: &str) -> &'static str {
    let r = r.split(':').next().unwrap_or(r);
    match r {
        "pending_commit" | "route_not_quiet" | "parts_skewed" | "store_lagging" | "account_missing" | "clock_stale" | "warmup" | "fork_pending"
        | "state_unavailable" | "resync" => "state",
        "best" | "not_best" | "priced" | "broken_quote" | "implausible_gap" | "below_min_profit" | "dlmm_cap" | "no_route" => "pricing",
        x if x.starts_with("unquotable") => "pricing",
        "inflight_same_state" | "inflight_same_leader" | "band_throttle" | "rate_queue_timeout" | "crowded_pool" => "send_slot",
        // WP-05's names for the queue's outcomes (MEASUREMENT A.1 as WP-05 writes them)
        "crowded_skip" | "would_rate" | "would_rate_crowded" => "send_slot",
        "blockhash_stale" | "leader_unknown" | "leader_skip_kind" | "program_hash_mismatch" | "jito_auth_stale" => "inputs",
        "uva_missing" | "dlmm_ext_needed" | "oversized" | "build_error" | "expected_below_min_profit" => "build",
        "sent" | "send" => "sent",
        _ => "policy",
    }
}

/// the offline engine's stand-in for an executor's verdict: it has none (`no_executor`, or the SendGate's `gate_*`)
fn stand_in(r: &str) -> bool { r == "no_executor" || r.starts_with("gate_") }

/// Whether a reason difference is an executor's verdict this replay cannot give (review WP-09 #4): the run had an
/// executor, its decision got past the engine's own state and pricing stages, and the replay (no executor) gave its
/// stand-in. Any state- or pricing-stage reason on either side is compared: a replay that says `warmup` where the run
/// sent differs. Counted as `executor_verdicts_not_replayed`; the replay is then not whole (`executor_not_replayed`)
pub fn executor_not_replayed(run: &str, replay: &str, executor: bool) -> bool {
    executor && !matches!(reason_stage(run), "state" | "pricing") && stand_in(replay)
}

/// a decision line's fields only an executor fills (WP-05's `sent`, `would_send`, `reason_ungated` among them): not
/// compared for a run with an executor until the offline executor replays them (counted)
const EXECUTOR_FIELDS: [&str; 7] = ["attempt", "ev", "rank", "crowding", "sent", "would_send", "reason_ungated"];
/// the fields of a decision line that are the run's real clock reads (`stages`: the rest of it is journaled times)
const NOT_COMPARED: [&str; 2] = ["stages.t_priced", "stages.t_decided"];

/// One file of a JSON-lines stream, a line at a time: a zstd file is decompressed one frame at a time (a trailing
/// incomplete frame, a write in progress, is left out), so a compare never holds a whole file (review WP-09 #7)
struct FileLines { data: Vec<u8>, pos: usize, zst: bool, buf: Vec<u8>, bpos: usize }

impl FileLines {
    fn open(p: &Path) -> Result<FileLines> {
        let data = std::fs::read(p).with_context(|| format!("reading {}", p.display()))?;
        let zst = p.extension().is_some_and(|e| e == "zst");
        Ok(if zst { FileLines { data, pos: 0, zst, buf: Vec::new(), bpos: 0 } } else { FileLines { data: Vec::new(), pos: 0, zst, buf: data, bpos: 0 } })
    }
    /// the next frame's bytes appended to `buf` (what was read of it dropped first); false at the end
    fn fill(&mut self) -> Result<bool> {
        if !self.zst { return Ok(false); }
        self.buf.drain(..self.bpos);
        self.bpos = 0;
        let rest = &self.data[self.pos..];
        let Ok(n) = zstd::zstd_safe::find_frame_compressed_size(rest) else { return Ok(false) };
        if rest.is_empty() || n == 0 || n > rest.len() { return Ok(false); }
        let size = zstd::zstd_safe::get_frame_content_size(&rest[..n]).ok().flatten().unwrap_or(64 << 20) as usize;
        self.buf.extend(zstd::bulk::decompress(&rest[..n], size).context("a zstd frame")?);
        self.pos += n;
        Ok(true)
    }
    fn next_line(&mut self) -> Result<Option<Vec<u8>>> {
        loop {
            if let Some(i) = self.buf[self.bpos..].iter().position(|b| *b == b'\n') {
                let l = self.buf[self.bpos..self.bpos + i].to_vec();
                self.bpos += i + 1;
                return Ok(Some(l));
            }
            if !self.fill()? {
                if self.bpos < self.buf.len() { let l = self.buf[self.bpos..].to_vec(); self.bpos = self.buf.len(); return Ok(Some(l)); }
                return Ok(None);
            }
        }
    }
}

/// A stream's records one at a time across its rotation files (each file's header line skipped)
struct Lines { files: Vec<PathBuf>, next: usize, cur: Option<(FileLines, PathBuf, u64)> }
impl Lines {
    fn open(dir: &Path, name: &str) -> Lines { Lines { files: rec::stream_files(dir, name), next: 0, cur: None } }
    fn next(&mut self) -> Result<Option<Value>> {
        loop {
            if let Some((f, p, n)) = self.cur.as_mut() {
                match f.next_line()? {
                    Some(l) if l.iter().all(|b| b.is_ascii_whitespace()) => continue,
                    Some(l) => {
                        let v: Value = serde_json::from_slice(&l).with_context(|| format!("{}: line {n}", p.display()))?;
                        *n += 1;
                        if *n == 1 && v["schema"].as_str().is_some_and(|s| s.starts_with("arbx.")) && v.get("file_seq").is_some() { continue; }
                        return Ok(Some(v));
                    }
                    None => self.cur = None,
                }
            }
            let Some(p) = self.files.get(self.next).cloned() else { return Ok(None) };
            self.next += 1;
            self.cur = Some((FileLines::open(&p)?, p, 0));
        }
    }
}

/// decisions.jsonl's main lines (with `routes`) by id, in id order; the follow-up flags apart
struct DecisionLines { lines: Lines, pub flags: std::collections::BTreeSet<(u64, String)>, peeked: Option<Value> }
impl DecisionLines {
    fn open(dir: &Path) -> DecisionLines { DecisionLines { lines: Lines::open(dir, "decisions"), flags: Default::default(), peeked: None } }
    fn next(&mut self) -> Result<Option<Value>> {
        if let Some(v) = self.peeked.take() { return Ok(Some(v)); }
        while let Some(v) = self.lines.next()? {
            if v.get("routes").is_some() { return Ok(Some(v)); }
            let id = v["decision"].as_u64().unwrap_or(u64::MAX);
            for f in ["torn_suspect", "fork_priced"] { if v[f] == json!(true) { self.flags.insert((id, f.to_string())); } }
        }
        Ok(None)
    }
    fn peek_id(&mut self) -> Result<Option<u64>> {
        if self.peeked.is_none() { self.peeked = self.next()?; }
        Ok(self.peeked.as_ref().and_then(|v| v["decision"].as_u64()))
    }
}

/// increasing ids kept as ranges (the decisions compared: a few runs of consecutive ids, whatever their number)
#[derive(Default, Debug)]
struct IdRanges(Vec<(u64, u64)>);
impl IdRanges {
    fn push(&mut self, id: u64) {
        match self.0.last_mut() {
            Some(r) if id == r.1 + 1 => r.1 = id,
            Some(r) if id >= r.0 && id <= r.1 => {}
            _ => { self.0.push((id, id)); self.0.sort_unstable(); }
        }
    }
    fn contains(&self, id: u64) -> bool { self.0.iter().any(|r| r.0 <= id && id <= r.1) }
}

struct DiffAcc { entries: Vec<Value>, n: u64, by_field: BTreeMap<String, u64>, by_class: BTreeMap<&'static str, u64>, first_own: Option<u64>, after_own: u64 }
impl DiffAcc {
    fn new(first_own: Option<u64>) -> DiffAcc { DiffAcc { entries: Vec::new(), n: 0, by_field: BTreeMap::new(), by_class: BTreeMap::new(), first_own, after_own: 0 } }
    fn push(&mut self, id: u64, t: u64, field: String, run: &Value, replay: &Value, class: &'static str, after_gap: bool) {
        self.n += 1;
        *self.by_field.entry(field.split(['[', '.']).next().unwrap_or(&field).to_string()).or_default() += 1;
        *self.by_class.entry(class).or_default() += 1;
        let after_own = self.first_own.is_some_and(|f| t >= f);
        if after_own { self.after_own += 1; }
        if self.entries.len() < MAX_DIFFS {
            self.entries.push(json!({ "decision": id, "t_ns": t, "field": field, "run": run, "replay": replay, "class": class, "after_gap": after_gap,
                "after_own_landing": after_own }));
        }
    }
}

/// the class of a differing field (MEASUREMENT A.1 stages; `pricing` for numbers a venue's maths makes). Two reasons of
/// different stages are the earlier stage's difference (a route priced `below_min_profit` in one and an opportunity in
/// the other differ in pricing, whatever the policy then said)
fn field_class(field: &str, run: &Value, replay: &Value) -> &'static str {
    let rank = |s: &str| match s { "state" => 0, "pricing" => 1, _ => 2 };
    match field {
        f if f.ends_with(".reason") || f == "reason" => [run, replay].iter().filter_map(|v| v.as_str().map(reason_stage)).min_by_key(|s| rank(s)).unwrap_or("policy"),
        f if f.ends_with(".size") || f.ends_with(".gross") || f.ends_with(".net") || f.ends_with(".cu") || f.ends_with(".crossed") || f == "best" || f == "band" => "pricing",
        f if f.starts_with("stages.") => "state",
        "sv" | "route_age_ms" | "parts_skew_slots" | "w_src" | "trigger" | "kind" | "t_ns" => "state",
        _ => "other",
    }
}

/// the differing (sub)fields of two values: objects and arrays field by field (`routes[3].net`, `stages.t_commit`),
/// anything else whole
fn diff_fields(prefix: &str, a: &Value, b: &Value, out: &mut Vec<(String, Value, Value)>) {
    if a == b { return; }
    match (a, b) {
        (Value::Object(x), Value::Object(y)) => {
            let keys: std::collections::BTreeSet<&String> = x.keys().chain(y.keys()).collect();
            for k in keys {
                let (u, v) = (x.get(k).unwrap_or(&Value::Null), y.get(k).unwrap_or(&Value::Null));
                let name = if prefix.is_empty() { k.clone() } else { format!("{prefix}.{k}") };
                if prefix.is_empty() && (k == "routes" || k == "stages") { diff_fields(&name, u, v, out); } else if u != v { out.push((name, u.clone(), v.clone())); }
            }
        }
        (Value::Array(x), Value::Array(y)) => {
            for n in 0..x.len().max(y.len()) {
                let (u, v) = (x.get(n).unwrap_or(&Value::Null), y.get(n).unwrap_or(&Value::Null));
                if u == v { continue; }
                match (u, v) {
                    (Value::Object(p), Value::Object(q)) => {
                        let fields: std::collections::BTreeSet<&String> = p.keys().chain(q.keys()).collect();
                        for f in fields {
                            let (s, t) = (p.get(f).unwrap_or(&Value::Null), q.get(f).unwrap_or(&Value::Null));
                            if s != t { out.push((format!("{prefix}[{n}].{f}"), s.clone(), t.clone())); }
                        }
                    }
                    _ => out.push((format!("{prefix}[{n}]"), u.clone(), v.clone())),
                }
            }
        }
        _ => out.push((prefix.to_string(), a.clone(), b.clone())),
    }
}

/// Compare the replay's decisions.jsonl and commits.jsonl with the run's, and the digests (see the module doc). The
/// summary's `differences_ok`: no field, flag, commit or digest difference (the caller's `ok` also needs a whole replay)
fn compare(run: &Path, out: &Path, w: &Window, d: &Drive, exec: &RunExec, what_if: bool, digests: &Value) -> Result<Value> {
    // ---- WP-09 (review WP-09 "For the WP-05 merge" item 6): a replayed executor's verdicts and fields are compared like
    // every other field; only a recording whose executor was not replayed keeps the exemptions (and is never ok)
    let (exec_run, exec_replayed) = (!matches!(exec, RunExec::None), matches!(exec, RunExec::Replayed(_)));
    // the intervals a journal gap left without inputs, and each account input skipped for want of its record: decisions
    // inside are not compared; differences after the first are marked `after_gap` (the store may differ from then on)
    // (a gap among the boot records skips nothing: every difference is then `after_gap`)
    let mut gaps: Vec<(u64, u64)> = d.gaps.iter().filter(|g| g.t_before > 0).map(|g| (g.t_before, g.t_after.unwrap_or(u64::MAX))).collect();
    gaps.extend(d.missing_at.iter().map(|t| (*t, *t)));
    let first_gap = gaps.iter().map(|g| g.0).chain(d.gaps.iter().filter(|g| g.t_before == 0).map(|_| 1)).min();
    let in_gap = |t: u64| gaps.iter().any(|(a, b)| t >= *a && t <= *b);
    let first_own = d.own_landings.iter().map(|x| x.0).min();
    let (mut a, mut b) = (DecisionLines::open(run), DecisionLines::open(out));
    let mut acc = DiffAcc::new(first_own);
    // the decisions compared (in the window, outside gaps, in both): their follow-up flags are compared too
    let mut compared_ids = IdRanges::default();
    let (mut n_run, mut n_replay, mut compared, mut identical, mut missing, mut extra, mut skipped_gap, mut outside) = (0u64, 0u64, 0u64, 0u64, 0u64, 0u64, 0u64, 0u64);
    let (mut exec_verdicts, mut exec_fields) = (0u64, 0u64);
    loop {
        let (ia, ib) = (a.peek_id()?, b.peek_id()?);
        let (x, y) = match (ia, ib) {
            (None, None) => break,
            (Some(i), Some(j)) if i == j => (a.next()?, b.next()?),
            (Some(i), Some(j)) if i < j => (a.next()?, None),
            (Some(_), None) => (a.next()?, None),
            _ => (None, b.next()?),
        };
        let (has_x, has_y) = (x.is_some(), y.is_some());
        if has_x { n_run += 1; }
        if has_y { n_replay += 1; }
        let any = x.as_ref().or(y.as_ref()).context("a decision line")?;
        let (id, t) = (any["decision"].as_u64().unwrap_or(0), any["t_ns"].as_u64().unwrap_or(0));
        if !w.holds(any) { outside += 1; continue; }
        if in_gap(t) { skipped_gap += 1; continue; }
        let after_gap = first_gap.is_some_and(|g| t >= g);
        let (Some(mut x), Some(mut y)) = (x, y) else {
            if has_x { missing += 1; acc.push(id, t, "decision".into(), &json!("present"), &Value::Null, "missing_in_replay", after_gap); }
            else { extra += 1; acc.push(id, t, "decision".into(), &Value::Null, &json!("present"), "extra_in_replay", after_gap); }
            continue;
        };
        compared += 1;
        compared_ids.push(id);
        for v in [&mut x, &mut y] {
            if let Some(s) = v.get_mut("stages").and_then(|s| s.as_object_mut()) { for f in NOT_COMPARED { s.remove(f.trim_start_matches("stages.")); } }
        }
        if exec_run && !exec_replayed {
            // an executor's own fields: not compared when the executor is not replayed (counted)
            if EXECUTOR_FIELDS.iter().any(|f| !x[*f].is_null() && x[*f] != y[*f]) { exec_fields += 1; }
            for f in EXECUTOR_FIELDS { x.as_object_mut().map(|o| o.remove(f)); y.as_object_mut().map(|o| o.remove(f)); }
            let (rr, rp) = (x["reason"].as_str().unwrap_or("").to_string(), y["reason"].as_str().unwrap_or("").to_string());
            if rr != rp && executor_not_replayed(&rr, &rp, true) {
                exec_verdicts += 1;
                for f in ["verdict", "reason"] { x.as_object_mut().map(|o| o.remove(f)); y.as_object_mut().map(|o| o.remove(f)); }
            }
        }
        if x == y { identical += 1; continue; }
        let mut fields = Vec::new();
        diff_fields("", &x, &y, &mut fields);
        for (name, u, v) in fields { let c = field_class(&name, &u, &v); acc.push(id, t, name, &u, &v, c, after_gap); }
    }
    // the follow-up flags (torn_suspect, fork_priced) of the decisions compared. A flag only the run has, of a replay
    // that stopped early (`--to-slot`), may have come after the stop: not counted then
    let (fa, fb) = (a.flags, b.flags);
    let flags_differ: Vec<Value> = fa.symmetric_difference(&fb).filter(|(i, f)| compared_ids.contains(*i) && !(w.t_cut.is_some() && !fb.contains(&(*i, f.clone()))))
        .map(|(i, f)| json!({ "decision": i, "flag": f, "run": fa.contains(&(*i, f.clone())), "replay": fb.contains(&(*i, f.clone())) })).collect();
    // commits.jsonl: the same lines in the same order (every field is a journaled time or a recorded value)
    let (mut ca, mut cb) = (Lines::open(run, "commits"), Lines::open(out, "commits"));
    let (mut n_ca, mut n_cb, mut c_differ, mut first_commit_diff) = (0u64, 0u64, 0u64, Value::Null);
    loop {
        let (x, y) = (ca.next()?, cb.next()?);
        if x.is_none() && y.is_none() { break; }
        if x.is_some() { n_ca += 1; }
        if y.is_some() { n_cb += 1; }
        let any = x.as_ref().or(y.as_ref()).context("a commit line")?;
        let t = any["t_resolved"].as_u64().or(any["t"].as_u64()).unwrap_or(0);
        if w.t_cut.is_some_and(|c| t >= c) || in_gap(t) { continue; }
        if x != y {
            c_differ += 1;
            if first_commit_diff.is_null() { first_commit_diff = json!({ "line": n_ca.max(n_cb) - 1, "run": x, "replay": y }); }
        }
    }
    // ---- WP-09: a replayed executor's attempts.jsonl, attempt by attempt (those of the decisions compared)
    let att = if exec_replayed { Some(compare_attempts(run, out, &compared_ids)?) } else { None };
    let att_ok = att.as_ref().map_or(true, |a| a.differ == 0 && a.missing == 0 && a.extra == 0);
    let flags_n = flags_differ.len() as u64;
    let digests_ok = digests["same"] != json!(false);
    let differences_ok = acc.n == 0 && flags_n == 0 && c_differ == 0 && digests_ok && att_ok;
    let summary = json!({
        "what_if": what_if, "executor": exec_run, "executor_replayed": exec_replayed,
        "attempts_run": att.as_ref().map(|a| a.n_run), "attempts_replay": att.as_ref().map(|a| a.n_replay), "attempts_compared": att.as_ref().map(|a| a.compared),
        "attempts_identical": att.as_ref().map(|a| a.compared - a.differ), "attempts_differ": att.as_ref().map(|a| a.differ),
        "attempts_missing_in_replay": att.as_ref().map(|a| a.missing), "attempts_extra_in_replay": att.as_ref().map(|a| a.extra),
        "attempts_by_field": att.as_ref().map(|a| a.by_field.clone()),
        "decisions_run": n_run, "decisions_replay": n_replay, "outside_window": outside, "compared": compared, "identical": identical,
        "differ": compared - identical, "missing_in_replay": missing, "extra_in_replay": extra, "skipped_gap": skipped_gap,
        "executor_verdicts_not_replayed": exec_verdicts, "executor_fields_not_replayed": exec_fields, "field_diffs": acc.n, "by_field": acc.by_field, "by_class": acc.by_class,
        "own_landings": d.own_landings.len(), "first_own_landing_t_ns": first_own, "diffs_after_own_landing": acc.after_own,
        "flags_differ": flags_n, "commits_run": n_ca, "commits_replay": n_cb, "commits_differ": c_differ,
        "digests_checked": digests["checked"], "digests_same": digests["same"], "differences_ok": differences_ok,
    });
    let not_replayed = if exec_run && !exec_replayed {
        json!({ "executor_fields": EXECUTOR_FIELDS, "executor_verdicts": "a run whose executor is not replayed (no exec_init record, or one of an earlier version): \
            its verdict where the replay (no executor) gives no_executor / gate_* and the run's reason is past the state and pricing stages" })
    } else { Value::Null };
    Ok(json!({ "schema": DIFF_SCHEMA, "run": run.display().to_string(), "replay": out.display().to_string(), "t_ns": crate::feeds::clock::now_ns(),
        "not_replayed": not_replayed, "attempts_not_compared": if exec_replayed { json!(ATTEMPT_NOT_COMPARED) } else { Value::Null },
        "attempt_diffs": att.as_ref().map(|a| a.entries.clone()),
        "not_compared": NOT_COMPARED, "window": { "from_slot": w.from_slot, "to_slot": w.to_slot, "t_cut": w.t_cut },
        "gaps": d.gaps.iter().map(|g| json!({ "first_lost_seq": g.first_lost_seq, "n_lost": g.n_lost, "t_before": g.t_before, "t_after": g.t_after })).collect::<Vec<_>>(),
        "digests": digests, "summary": summary, "diffs": acc.entries, "diffs_truncated": acc.n.saturating_sub(MAX_DIFFS as u64), "flags": flags_differ,
        "first_commit_diff": first_commit_diff }))
}

/// ---- WP-09 (review WP-09 "For the WP-05 merge" item 6). The fields of an attempts.jsonl line (MEASUREMENT §4.37) a
/// replay does not reproduce, left out of the compare: the real clock (`t_ns`; the stage times of the build, the
/// signature and the send; the decision's own clock reads `t_priced` and `t_decided`), the LeaderBook's snapshot
/// (`leader`: places and RTTs read live, not journaled; the kind the send checks read is in the decision-point record),
/// and a dry run's signature and signer (a new throwaway key each run: `tx.sig`, `copies[].sig`, `dry_run.signer`,
/// `dry_run.tx_b64`, the signature check's detail). Everything else is compared: the route, sizes, the expected
/// profit, the tip and its account, min_profit, the built transaction's size, locks, lookup tables and CU, the
/// blockhash, the crowding, the in-flight key and why it was allowed, the queue rank, the route's account versions, a
/// dry run's checks and accounts. WP-09 part 2 (a live or canary executor replayed): the send queue's λ estimate
/// (`queue.lambda`, the bundle path's queue as it was: PLAN WP-09 takes λ from the recording)
pub const ATTEMPT_NOT_COMPARED: [&str; 17] = ["t_ns", "leader", "stages.t_priced", "stages.t_decided", "stages.t_built", "stages.t_build_start", "stages.t_signed",
    "stages.t_enqueued", "stages.t_dequeued", "stages.t_sent", "stages.t_ack", "tx.sig", "copies[].sig", "dry_run.signer", "dry_run.tx_b64",
    "dry_run.checks[signature_verifies].detail", "queue.lambda"];

/// an attempts.jsonl line without `ATTEMPT_NOT_COMPARED`
pub fn attempt_projection(mut v: Value) -> Value {
    if let Some(o) = v.as_object_mut() { o.remove("t_ns"); o.remove("leader"); }
    if let Some(q) = v.get_mut("queue").and_then(|q| q.as_object_mut()) { q.remove("lambda"); }
    if let Some(s) = v.get_mut("stages").and_then(|s| s.as_object_mut()) {
        for k in ["t_priced", "t_decided", "t_built", "t_build_start", "t_signed", "t_enqueued", "t_dequeued", "t_sent", "t_ack"] { s.remove(k); }
    }
    if let Some(t) = v.get_mut("tx").and_then(|t| t.as_object_mut()) { t.remove("sig"); }
    for c in v.get_mut("copies").and_then(|c| c.as_array_mut()).into_iter().flatten() { if let Some(o) = c.as_object_mut() { o.remove("sig"); } }
    if let Some(d) = v.get_mut("dry_run").and_then(|d| d.as_object_mut()) {
        d.remove("signer");
        d.remove("tx_b64");
        for c in d.get_mut("checks").and_then(|c| c.as_array_mut()).into_iter().flatten() {
            if c["check"] == "signature_verifies" { if let Some(o) = c.as_object_mut() { o.remove("detail"); } }
        }
    }
    v
}

/// What the attempts compare found
struct AttemptsCmp { n_run: u64, n_replay: u64, compared: u64, differ: u64, missing: u64, extra: u64, by_field: BTreeMap<String, u64>, entries: Vec<Value> }

/// attempts.jsonl of the run and of the replay, joined by attempt id (both in id order), each on `attempt_projection`:
/// the attempts of the decisions compared (`compared`); an attempt one side has and the other not is missing or extra
fn compare_attempts(run: &Path, out: &Path, compared: &IdRanges) -> Result<AttemptsCmp> {
    let (mut a, mut b) = (Lines::open(run, "attempts"), Lines::open(out, "attempts"));
    let mut c = AttemptsCmp { n_run: 0, n_replay: 0, compared: 0, differ: 0, missing: 0, extra: 0, by_field: BTreeMap::new(), entries: Vec::new() };
    let id = |v: &Option<Value>| v.as_ref().map(|v| v["attempt"].as_u64().unwrap_or(u64::MAX));
    let (mut pa, mut pb) = (a.next()?, b.next()?);
    loop {
        let (x, y) = match (id(&pa), id(&pb)) {
            (None, None) => break,
            (Some(i), Some(j)) if i == j => { let r = (pa.take(), pb.take()); pa = a.next()?; pb = b.next()?; r }
            (Some(i), Some(j)) if i < j => { let r = (pa.take(), None); pa = a.next()?; r }
            (Some(_), None) => { let r = (pa.take(), None); pa = a.next()?; r }
            _ => { let r = (None, pb.take()); pb = b.next()?; r }
        };
        let (has_x, has_y) = (x.is_some(), y.is_some());
        if has_x { c.n_run += 1; }
        if has_y { c.n_replay += 1; }
        let any = x.as_ref().or(y.as_ref()).context("an attempt line")?;
        let (att, dec) = (any["attempt"].as_u64().unwrap_or(u64::MAX), any["decision"].as_u64().unwrap_or(u64::MAX));
        if !compared.contains(dec) { continue; }
        let (Some(x), Some(y)) = (x, y) else {
            if has_x { c.missing += 1; } else { c.extra += 1; }
            if c.entries.len() < MAX_DIFFS {
                c.entries.push(json!({ "attempt": att, "decision": dec, "field": "attempt", "run": if has_x { json!("present") } else { Value::Null },
                    "replay": if has_y { json!("present") } else { Value::Null } }));
            }
            continue;
        };
        c.compared += 1;
        let (x, y) = (attempt_projection(x), attempt_projection(y));
        if x == y { continue; }
        c.differ += 1;
        let mut fields = Vec::new();
        diff_fields("", &x, &y, &mut fields);
        for (name, u, v) in fields {
            *c.by_field.entry(name.split(['[', '.']).next().unwrap_or(&name).to_string()).or_default() += 1;
            if c.entries.len() < MAX_DIFFS { c.entries.push(json!({ "attempt": att, "decision": dec, "field": name, "run": u, "replay": v })); }
        }
    }
    Ok(c)
}

// ------------------------------------------------------------------ pricing a route on the engine's store

/// The engine's own price of route (buy, sell, mint) at `size` on its store as it is, as a decision prices it
/// (`Engine::quote_route`): what the buy leg delivers and debits (`spent`), what the sell leg returns, the gross (the
/// guard's quote delta, `back` − `spent`), the CU it asks (WP-06: the run's CU model), and the net with the engine's fee
/// rule (WP-06: base fee + the tip of the gross's edge by band, the run's engine_init `builder`; a journal written before
/// WP-06: base fee + `cu_price_micro` × CU + the run's `min_tip`)
pub fn price(e: &Engine, buy: &Pk, sell: &Pk, mint: &Pk, size: u64) -> Result<Value, String> {
    quote_json(e.quote_route(buy, sell, mint, size))
}

fn quote_json(q: Result<crate::engine::RouteQuote, &'static str>) -> Result<Value, String> {
    match q {
        Ok(q) => Ok(json!({ "size": q.size, "mid": q.mid, "back": q.back, "spent": q.spent, "gross": q.gross, "fee": q.fee, "net": q.net, "cu": q.cu,
            "crossed": [q.crossed.0, q.crossed.1], "buy_end": q.buy_end, "sell_end": q.sell_end })),
        Err(why) => Err(format!("unquotable on this state ({why}: a part missing or left out, or a venue refused the size)")),
    }
}

/// the size a decision would pick over (0, cap], priced: the engine's own search (`Engine::quote_route_best`: the
/// strategy's ladder, then arbx-sizing's locator where a rung makes money, as `price_route`; WP-16)
fn price_opt(e: &Engine, buy: &Pk, sell: &Pk, mint: &Pk, cap: u64) -> Value {
    quote_json(e.quote_route_best(buy, sell, mint, cap)).unwrap_or_else(|err| json!({ "error": err }))
}

// ------------------------------------------------------------------ --reprice-sizes (X3)

/// The run's opportunity decisions (a best route at or above `min_profit`): id -> (buy, sell, mint, size, net, gross, slot, t)
fn opportunities(run: &Path, w: &Window) -> Result<BTreeMap<u64, Value>> {
    let mut d = DecisionLines::open(run);
    let mut out = BTreeMap::new();
    while let Some(v) = d.next()? {
        if v["opp"].is_null() || !w.holds(&v) { continue; }
        let Some(b) = v["best"].as_u64() else { continue };
        let r = &v["routes"][b as usize];
        out.insert(v["decision"].as_u64().unwrap_or(0), json!({ "buy": r["buy"], "sell": r["sell"], "mint": r["mint"], "size": r["size"], "net": r["net"],
            "gross": r["gross"], "cu": r["cu"], "slot": v["trigger"]["slot"], "t_ns": v["t_ns"], "verdict": v["verdict"], "reason": v["reason"] }));
    }
    Ok(out)
}

/// The repricing, in the replay's own pass (`Engine::quote_route` changes nothing the replay records): after each
/// record, the run's opportunities that record decided, at the fractions of their size and at the optimum
struct RepriceHook<'a> { want: BTreeMap<u64, Value>, sizes: &'a [Reprice], cfg: StrategyCfg, cap: u64, seen: u64, out: Vec<Value>,
    /// WP-06: the fee rule the prices used (`tips_by_band`: the run's builder model; `legacy`: a pre-WP-06 journal's)
    fee_rule: &'static str }
impl Hook for RepriceHook<'_> {
    fn after(&mut self, e: &mut Engine, _r: &JRec, _a: Option<u64>) -> Result<bool> {
        let now = e.counter("evaluation");
        // the decisions this record made: ids [seen, now) (an evaluation is one decision, numbered from 0)
        let ids: Vec<u64> = self.want.range(self.seen..now).map(|(k, _)| *k).collect();
        self.seen = now;
        for id in ids {
            let d = self.want.remove(&id).unwrap();
            let (Ok(buy), Ok(sell), Ok(mint)) = (pk_of(&d["buy"]), pk_of(&d["sell"]), pk_of(&d["mint"])) else { continue };
            let size = d["size"].as_u64().unwrap_or(0);
            // the decision's own size again: the check that the repricing reads the state the decision priced
            let check = price(e, &buy, &sell, &mint, size);
            let same = check.as_ref().ok().map(|v| v["gross"] == d["gross"]);
            let at: Vec<Value> = self.sizes.iter().filter_map(|s| match s { Reprice::Frac(f) => Some(*f), Reprice::Opt => None }).map(|f| {
                let x = ((size as f64) * f) as u64;
                match price(e, &buy, &sell, &mint, x) { Ok(mut v) => { v["f"] = json!(f); v } Err(err) => json!({ "f": f, "size": x, "error": err }) }
            }).collect();
            let opt = self.sizes.contains(&Reprice::Opt).then(|| price_opt(e, &buy, &sell, &mint, self.cap));
            self.out.push(json!({ "decision": id, "t_ns": d["t_ns"], "slot": d["slot"], "buy": d["buy"], "sell": d["sell"], "mint": d["mint"], "size": size,
                "run": { "gross": d["gross"], "net": d["net"], "cu": d["cu"], "verdict": d["verdict"], "reason": d["reason"] },
                "requote": check.unwrap_or_else(|err| json!({ "error": err })), "requote_same_gross": same, "at": at, "opt": opt }));
        }
        Ok(true)
    }
}

/// reprice.jsonl: the header, then one line per opportunity repriced; its summary for replay.json
fn write_reprice(inp: &Inputs, h: RepriceHook, n_want: usize, sizes: &[Reprice], out: &Path, min_tip: u64) -> Result<Value> {
    let mut text = String::new();
    text.push_str(&json!({ "schema": REPRICE_SCHEMA, "run": inp.dir.display().to_string(), "sizes": sizes.iter().map(|s| match s { Reprice::Frac(f) => json!(f), Reprice::Opt => json!("opt") }).collect::<Vec<_>>(),
        "min_tip": min_tip, "cu_price_micro": h.cfg.cu_price_micro, "cap_lamports": h.cap, "fee_rule": h.fee_rule }).to_string());
    text.push('\n');
    for l in &h.out { text.push_str(&l.to_string()); text.push('\n'); }
    std::fs::write(out.join("reprice.jsonl"), text)?;
    let profitable = |f: &dyn Fn(&Value) -> Option<i64>| h.out.iter().filter(|l| f(l).is_some_and(|n| n > 0)).count();
    let mut by: BTreeMap<String, usize> = BTreeMap::new();
    for s in sizes {
        match s {
            Reprice::Frac(f) => { by.insert(format!("{f}"), profitable(&|l: &Value| l["at"].as_array()?.iter().find(|x| x["f"].as_f64() == Some(*f))?["net"].as_i64())); }
            Reprice::Opt => { by.insert("opt".into(), profitable(&|l: &Value| l["opt"]["net"].as_i64())); }
        }
    }
    let same = h.out.iter().filter(|l| l["requote_same_gross"] == json!(true)).count();
    Ok(json!({ "file": "reprice.jsonl", "opportunities": n_want, "repriced": h.out.len(), "requote_same_gross": same, "profitable": by }))
}

// ------------------------------------------------------------------ arbx quote

/// A recorded state version (`arbx quote --version`)
#[derive(Clone, Debug, PartialEq)]
pub enum Version {
    /// after the accounts.bin record `aseq` was handled
    Aseq(u64),
    /// after the update with this slot and write version was handled
    SlotWv(u64, u64),
    /// after every update stamped with the transaction was handled (its post-state)
    Txn([u8; 64]),
    /// before the first update stamped with the transaction (its pre-state)
    PreTxn([u8; 64]),
}

impl std::str::FromStr for Version {
    type Err = anyhow::Error;
    fn from_str(s: &str) -> Result<Version> {
        let s = s.trim();
        let sig = |x: &str| -> Result<[u8; 64]> { bs58::decode(x).into_vec().ok().and_then(|b| <[u8; 64]>::try_from(b).ok()).with_context(|| format!("{x}: not a signature")) };
        if let Some(t) = s.strip_prefix("pre:") { return Ok(Version::PreTxn(sig(t)?)); }
        if let Some(a) = s.strip_prefix("aseq:") { return Ok(Version::Aseq(a.parse()?)); }
        if let Some((a, b)) = s.split_once(':') { return Ok(Version::SlotWv(a.parse().context("slot")?, b.parse().context("write_version")?)); }
        if s.bytes().all(|b| b.is_ascii_digit()) { return Ok(Version::Aseq(s.parse()?)); }
        Ok(Version::Txn(sig(s)?))
    }
}

/// One `arbx quote` question
#[derive(Clone, Debug)]
pub struct QuoteReq { pub id: Value, pub buy: Pk, pub sell: Pk, pub mint: Pk, pub version: Version, pub size: u64, pub asked: String }

impl QuoteReq {
    /// `--route buy,sell,mint --version V --size N`
    pub fn parse(route: &str, version: &str, size: u64, id: Value) -> Result<QuoteReq> {
        let p: Vec<&str> = route.split(',').map(str::trim).collect();
        anyhow::ensure!(p.len() == 3, "--route {route}: buy,sell,mint");
        let k = |s: &str| pk_of(&json!(s));
        Ok(QuoteReq { id, buy: k(p[0])?, sell: k(p[1])?, mint: k(p[2])?, version: version.parse()?, size, asked: version.to_string() })
    }
    /// a `--batch` line: {"id", "route": "buy,sell,mint", "version", "size"}
    pub fn from_json(v: &Value) -> Result<QuoteReq> {
        let version = match &v["version"] { Value::String(s) => s.clone(), Value::Number(n) => n.to_string(), x => bail!("version {x}: a string or an aseq") };
        QuoteReq::parse(v["route"].as_str().context("no route")?, &version, v["size"].as_u64().context("no size")?, v["id"].clone())
    }
}

/// Quote questions waiting for their version (review WP-09 #8: maps from each record to its questions, so a batch is
/// one pass whatever its size): answered on the boot state, after every one of their accounts.bin records was handled,
/// or right before the first of them
struct QuoteHook {
    reqs: Vec<QuoteReq>,
    answers: Vec<Option<Value>>,
    open: usize,
    booted: bool,
    at_boot: Vec<usize>,
    /// question -> records still to come; record -> the questions answered after it
    after_left: Vec<usize>,
    after_of: HashMap<u64, Vec<usize>>,
    /// record -> the questions answered right before it
    before_of: HashMap<u64, Vec<usize>>,
}

impl QuoteHook {
    fn answer(&mut self, e: &Engine, k: usize, r: Option<&JRec>) {
        if self.answers[k].is_some() { return; }
        let q = &self.reqs[k];
        let mut v = match price(e, &q.buy, &q.sell, &q.mint, q.size) {
            Ok(mut v) => { v["ok"] = json!(true); v }
            Err(err) => json!({ "ok": false, "error": err, "size": q.size }),
        };
        // the versions the price read: each pool's parts and followed bin arrays as the store holds them, and whether a
        // decision would have left one out now (pending: a commit group writes it; contested: its slot; unverified: not
        // read again since the state stream's last connection)
        let state: Vec<Value> = [q.buy, q.sell].iter().filter_map(|p| e.reg.by_pool.get(p).map(|i| e.reg.pools[*i].clone())).flat_map(|m| {
            let mut ks = crate::store::consistency_set(&m);
            ks.extend(crate::store::other_parts(&m));
            if let Some(l) = e.store.dlmm_arrays.get(&m.pool) { ks.extend(l.iter().map(|x| x.1)); }
            ks
        }).filter_map(|k| e.store.get(&k).map(|a| {
            let (pending, contested, unverified) = e.part_flags(&k);
            json!({ "acct": b58(&k), "slot": a.slot, "wv": a.write_version, "aseq": a.aseq, "txn": a.txn.map(|t| bs58::encode(t).into_string()),
                "pending": pending, "contested": contested, "unverified": unverified })
        })).collect();
        v["schema"] = json!(QUOTE_SCHEMA);
        v["id"] = q.id.clone();
        v["route"] = json!({ "buy": b58(&q.buy), "sell": b58(&q.sell), "mint": b58(&q.mint) });
        v["version"] = json!({ "asked": q.asked, "at_seq": r.map(|r| r.seq), "at_t_engine": r.map(|r| r.t_engine), "tip_slot": e.tip_slot() });
        v["state"] = json!(state);
        self.answers[k] = Some(v);
        self.open -= 1;
    }
    /// the questions on the boot state, once, before the first input
    fn boot(&mut self, e: &Engine) {
        if self.booted { return; }
        self.booted = true;
        for k in std::mem::take(&mut self.at_boot) { self.answer(e, k, None); }
    }
}

impl Hook for QuoteHook {
    fn before(&mut self, e: &mut Engine, r: &JRec, aseq: Option<u64>) -> Result<bool> {
        self.boot(e);
        if let Some(qs) = aseq.and_then(|a| self.before_of.remove(&a)) { for k in qs { self.answer(e, k, Some(r)); } }
        Ok(self.open > 0)
    }
    fn after(&mut self, e: &mut Engine, r: &JRec, aseq: Option<u64>) -> Result<bool> {
        if let Some(qs) = aseq.and_then(|a| self.after_of.remove(&a)) {
            for k in qs {
                self.after_left[k] = self.after_left[k].saturating_sub(1);
                if self.after_left[k] == 0 { self.answer(e, k, Some(r)); }
            }
        }
        Ok(self.open > 0)
    }
}

/// Answer quote questions on a run, in the order asked, with one replay pass up to the last version asked. A version is
/// an accounts.bin record: the state right after the journal handed it to the engine (`aseq`, `slot:write_version`), the
/// state after every update stamped with a transaction (`<txn>`), or right before the first of them (`pre:<txn>`)
pub fn quote(run: &Path, config: Option<&Path>, pools: Option<&Path>, reqs: Vec<QuoteReq>) -> Result<Vec<Value>> {
    let inp = inputs(run, config, pools)?;
    let boot = open_boot(&inp, &[], false)?;
    let boot_aseqs: HashSet<u64> = boot.records.iter().filter_map(|r| match r.body { JBody::Account { aseq, .. } => Some(aseq), _ => None }).collect();
    // the versions asked, looked up in one pass over accounts.bin
    let mut by_aseq: HashMap<u64, bool> = HashMap::default();
    let mut by_swv: HashMap<(u64, u64), Vec<u64>> = HashMap::default();
    let mut by_txn: HashMap<[u8; 64], Vec<u64>> = HashMap::default();
    for q in &reqs {
        match &q.version {
            Version::Aseq(a) => { by_aseq.insert(*a, false); }
            Version::SlotWv(s, w) => { by_swv.insert((*s, *w), Vec::new()); }
            Version::Txn(t) | Version::PreTxn(t) => { by_txn.insert(*t, Vec::new()); }
        }
    }
    for p in rec::stream_files(run, "accounts") {
        let bytes = if p.extension().is_some_and(|e| e == "zst") { rec::decode_zst(&p)?.0 } else { std::fs::read(&p)? };
        for r in accounts::parse(&bytes).with_context(|| format!("{}", p.display()))?.records {
            if let Some(f) = by_aseq.get_mut(&r.aseq) { *f = true; }
            if let Some(v) = by_swv.get_mut(&(r.slot, r.write_version)) { v.push(r.aseq); }
            if let Some(v) = r.txn.as_ref().and_then(|t| by_txn.get_mut(t)) { v.push(r.aseq); }
        }
    }
    let mut h = QuoteHook { answers: vec![None; reqs.len()], open: 0, booted: false, at_boot: Vec::new(), after_left: vec![0; reqs.len()], after_of: HashMap::default(),
        before_of: HashMap::default(), reqs: Vec::new() };
    for (k, q) in reqs.iter().enumerate() {
        let found: Result<Vec<u64>, String> = match &q.version {
            Version::Aseq(a) => if by_aseq.get(a) == Some(&true) { Ok(vec![*a]) } else { Err(format!("aseq {a} is not in accounts.bin")) },
            Version::SlotWv(s, w) => match by_swv.get(&(*s, *w)).map(|v| v.len()) {
                Some(1) => Ok(by_swv[&(*s, *w)].clone()),
                Some(n) if n > 1 => Err(format!("{n} updates at slot {s} with write version {w}: name one by its aseq")),
                _ => Err(format!("no account update at slot {s} with write version {w}")),
            },
            Version::Txn(t) | Version::PreTxn(t) => match by_txn.get(t).filter(|v| !v.is_empty()) {
                Some(v) => { let mut v = v.clone(); v.sort_unstable(); v.dedup(); Ok(v) }
                None => Err(format!("no account update stamped with {}", bs58::encode(t).into_string())),
            },
        };
        match found {
            Ok(s) => {
                h.open += 1;
                match q.version {
                    Version::PreTxn(_) if s.iter().any(|a| boot_aseqs.contains(a)) => h.at_boot.push(k),
                    Version::PreTxn(_) => for a in s { h.before_of.entry(a).or_default().push(k); },
                    _ if s.iter().all(|a| boot_aseqs.contains(a)) => h.at_boot.push(k),
                    _ => {
                        let left: Vec<u64> = s.into_iter().filter(|a| !boot_aseqs.contains(a)).collect();
                        h.after_left[k] = left.len();
                        for a in left { h.after_of.entry(a).or_default().push(k); }
                    }
                }
            }
            Err(err) => h.answers[k] = Some(json!({ "schema": QUOTE_SCHEMA, "id": q.id, "ok": false, "error": err, "version": { "asked": q.asked } })),
        }
    }
    h.reqs = reqs;
    if h.open > 0 {
        let (e, _, _) = drive(&inp, boot, &[], &Rec::off(), &mut h, &DigestPlan::default())?;
        // a journal with no input after its boot section: the boot state answers
        h.boot(&e);
    }
    Ok(h.answers.into_iter().zip(&h.reqs).map(|(a, q)| a.unwrap_or_else(|| json!({ "schema": QUOTE_SCHEMA, "id": q.id, "ok": false,
        "error": "the version is not in the journal (lost in a gap, or after the run stopped)", "version": { "asked": q.asked } }))).collect())
}

// ------------------------------------------------------------------ command line (main.rs arms)

/// `arbx replay`: prints replay.json's summary; the exit code is 0 (a whole replay and, with `--compare`, no
/// difference), 1 (not whole, or differences), 2 refused (main.rs)
pub fn cli_replay(run: &Path, o: &Opts) -> Result<i32> {
    let r = replay(run, o)?;
    let s = &r.summary;
    println!("replay of {} -> {}", run.display(), r.out.display());
    println!("  journal: {} records ({} boot), {} events, {} timers over {:.1} s of engine time; replayed in {:.1} s ({:.1}x real time)",
        s["journal"]["records"], s["journal"]["boot_records"], s["journal"]["events"], s["journal"]["timers"], s["journal"]["span_ms"].as_f64().unwrap_or(0.0) / 1e3,
        s["wall_ms"].as_f64().unwrap_or(0.0) / 1e3, s["speed_x"].as_f64().unwrap_or(0.0));
    println!("  accounts missing {}, verdict mismatches {}, journal gaps {}, replay recorder drops {}", s["accounts"]["missing"], s["accounts"]["verdict_mismatches"],
        s["journal"]["gaps"].as_array().map_or(0, |g| g.len()), s["recorder_dropped"]);
    if s["build"]["same_source"] == json!(false) { println!("  WARNING: the run was recorded by another build (replay.json `build`)"); }
    let x = &s["executor"];
    if x["run"] == json!(true) {
        println!("  executor: {}", if x["replayed"] == json!(true) {
            format!("{} replayed offline from exec_init; {} decision-point records staged ({} not its own, {} unread), {} settlements fed", x["exec_init"]["mode"].as_str().unwrap_or("?"),
                x["records_staged"], x["records_mismatch"], x["records_unused"], x["settled_fed"])
        } else { format!("NOT replayed: {}", x["exec_init"]["why_not"].as_str().unwrap_or("?")) });
    }
    for w in s["not_whole"].as_array().into_iter().flatten() { println!("  NOT WHOLE: {} ({}): {}", w["why"].as_str().unwrap_or("?"), w["n"], w["detail"].as_str().unwrap_or("")); }
    if let Some(c) = s["compare"].as_object() {
        println!("  compare: {} decisions in the window, {} identical, {} differ ({} field differences), {} missing, {} extra, {} in gaps, {} executor verdicts not replayed; commits {} vs {}, {} differ; digests {} -> replay-diff.json",
            c["compared"], c["identical"], c["differ"], c["field_diffs"], c["missing_in_replay"], c["extra_in_replay"], c["skipped_gap"], c["executor_verdicts_not_replayed"],
            c["commits_run"], c["commits_replay"], c["commits_differ"],
            match (c["digests_checked"].as_bool(), c["digests_same"].as_bool()) { (Some(true), Some(true)) => "same", (Some(true), _) => "DIFFER", _ => "not checked" });
    }
    if let Some(c) = s["compare"].as_object().filter(|c| c["executor_replayed"] == json!(true)) {
        println!("  attempts: {} vs {}, {} compared, {} differ, {} missing, {} extra", c["attempts_run"], c["attempts_replay"], c["attempts_compared"], c["attempts_differ"],
            c["attempts_missing_in_replay"], c["attempts_extra_in_replay"]);
    }
    // FT-001: the state digests at the run's digest points (where it took them), with the parts that differ
    let dg = &s["digests"];
    let at = |p: &Value| format!("{} ({}{})", p["point"].as_str().unwrap_or("?"), p["how"].as_str().unwrap_or("?"), p["seq"].as_u64().map_or(String::new(), |q| format!(" at seq {q}")));
    let points = dg["points"].as_array().cloned().unwrap_or_default();
    match (dg["checked"].as_bool(), dg["same"].as_bool()) {
        (Some(true), Some(true)) => println!("  digests: the run's state and decision digests at {}", points.iter().map(at).collect::<Vec<_>>().join(", ")),
        (Some(true), _) => for p in points.iter().filter(|p| p["same"] != json!(true)) {
            println!("  digests DIFFER at {}: parts {} (before finish: {}), counters {}", at(p), p["parts_differ"], p["before_finish_parts_differ"], p["counts_differ"]);
        },
        _ => println!("  digests not checked: {}", dg["not_checked"].as_str().unwrap_or("?")),
    }
    if !s["reprice"].is_null() { println!("  reprice: {}", s["reprice"]); }
    println!("  {}", if r.ok { "OK" } else if s["whole"] == json!(false) { "NOT OK: the replay is not whole (see `not_whole` in replay.json)" } else { "DIFFERENCES (see replay-diff.json)" });
    Ok(if r.ok { 0 } else { 1 })
}

/// `arbx quote`: one question (`--route --version --size`), or `--batch <file>` (JSON lines in, JSON lines out, in order)
pub fn cli_quote(run: &Path, config: Option<&Path>, pools: Option<&Path>, route: Option<&str>, version: Option<&str>, size: Option<u64>, batch: Option<&Path>) -> Result<i32> {
    let reqs = match batch {
        Some(b) => {
            let text = std::fs::read_to_string(b).with_context(|| format!("reading {}", b.display()))?;
            text.lines().filter(|l| !l.trim().is_empty()).enumerate().map(|(i, l)| {
                let v: Value = serde_json::from_str(l).with_context(|| format!("{}: line {}", b.display(), i + 1))?;
                QuoteReq::from_json(&v).with_context(|| format!("{}: line {}", b.display(), i + 1))
            }).collect::<Result<Vec<_>>>()?
        }
        None => vec![QuoteReq::parse(route.context("--route buy,sell,mint (or --batch)")?, version.context("--version")?, size.context("--size")?, Value::Null)?],
    };
    let single = batch.is_none();
    let ans = quote(run, config, pools, reqs)?;
    let all_ok = ans.iter().all(|a| a["ok"] == json!(true));
    if single { println!("{}", serde_json::to_string_pretty(&ans[0])?); } else { for a in &ans { println!("{a}"); } }
    Ok(if all_ok { 0 } else { 1 })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// `--version` forms: an aseq (plain or `aseq:`), `slot:write_version`, a transaction, `pre:<txn>`
    #[test]
    fn versions_parse() {
        let sig = bs58::encode([7u8; 64]).into_string();
        assert_eq!("42".parse::<Version>().unwrap(), Version::Aseq(42));
        assert_eq!("aseq:42".parse::<Version>().unwrap(), Version::Aseq(42));
        assert_eq!("453000000:17".parse::<Version>().unwrap(), Version::SlotWv(453_000_000, 17));
        assert_eq!(sig.parse::<Version>().unwrap(), Version::Txn([7; 64]));
        assert_eq!(format!("pre:{sig}").parse::<Version>().unwrap(), Version::PreTxn([7; 64]));
        assert!("pre:nope".parse::<Version>().is_err() && "1:x".parse::<Version>().is_err() && "zz".parse::<Version>().is_err());
        let q = QuoteReq::from_json(&json!({ "id": 3, "route": format!("{},{},{}", b58(&[1; 32]), b58(&[2; 32]), b58(&[3; 32])), "version": 9, "size": 100 })).unwrap();
        assert_eq!((q.version, q.size, q.buy, q.id), (Version::Aseq(9), 100, [1; 32], json!(3)));
        assert!(QuoteReq::parse("a,b", "1", 1, Value::Null).is_err());
    }

    /// `--set`: the strategy, the knobs (state, alts, accuracy), min_tip; unknown keys refused; the init's strategy hash
    /// follows the new strategy
    #[test]
    fn overrides_apply_to_the_strategy_and_the_knobs() {
        let mut cfg = StrategyCfg::default();
        let mut init = EngineInit { min_tip: 1_000, strategy_sha256: engine::strategy_sha256(&cfg), knobs: Some(engine::EngineKnobs::default()), ..Default::default() };
        let sets: Vec<Set> = ["strategy.min_profit_lamports=5", "strategy.sizes_sol=[0.1,1.0]", "state.quiescence_ms=7", "alts.give_up_s=60", "accuracy.ring_versions=4",
            "accuracy.queue=9", "min_tip=2000"].iter().map(|s| s.parse().unwrap()).collect();
        apply_sets(&mut cfg, &mut init, &sets).unwrap();
        let k = init.knobs.clone().unwrap();
        assert_eq!((cfg.min_profit_lamports, cfg.sizes_sol.clone(), k.quiescence_ms, k.alts.give_up_s, k.ring_versions, k.accuracy_queue, init.min_tip),
            (5, vec![0.1, 1.0], 7, 60, 4, 9, 2_000));
        assert_eq!(init.strategy_sha256, engine::strategy_sha256(&cfg));
        for bad in ["strategy.nope=1", "state.nope=1", "x=1", "strategy.min_profit_lamports=\"a\""] {
            assert!(apply_sets(&mut cfg.clone(), &mut init.clone(), &[bad.parse().unwrap()]).is_err(), "{bad}");
        }
        assert!("novalue".parse::<Set>().is_err());
        // WP-06: the builder model (tips by band, CU) as engine_init journals it; a journal without one refuses its keys
        assert!(apply_sets(&mut cfg.clone(), &mut init.clone(), &["tips.floor=5000".parse().unwrap()]).is_err(), "no builder model in a pre-WP-06 journal");
        init.builder = Some(engine::BuilderModel { tips: crate::tip::TipModel::default(), cu: crate::cu_table::CuModel::default() });
        let sets: Vec<Set> = ["tips.shares=[0.5,0.5,0.6,0.6,0.6]", "tips.cap=200000", "tips.bands.edges=[10000,100000,1000000,10000000]", "cu.min_samples=10", "min_tip=3000"]
            .iter().map(|s| s.parse().unwrap()).collect();
        apply_sets(&mut cfg, &mut init, &sets).unwrap();
        let b = init.builder.clone().unwrap();
        assert_eq!((b.tips.shares, b.tips.cap, b.tips.floor, b.tips.bands.edges, b.cu.min_samples), ([0.5, 0.5, 0.6, 0.6, 0.6], 200_000, 3_000, [10_000, 100_000, 1_000_000, 10_000_000], 10));
        for bad in ["tips.floor=0", "tips.shares=[2,0,0,0,0]", "tips.shares=[0.5]", "tips.bands.edges=[3,2,1,0]", "tips.nope=1", "cu.min_samples=0", "min_tip=0", "cu.nope=1"] {
            assert!(apply_sets(&mut cfg.clone(), &mut init.clone(), &[bad.parse().unwrap()]).is_err(), "{bad}");
        }
    }

    /// decision reasons by stage (MEASUREMENT A.1), and what a compare does not compare: an executor's verdict only
    /// where the replay gave its stand-in and the run's decision got past the engine's own stages (review WP-09 #4)
    #[test]
    fn reason_stages_and_the_executor_rule() {
        for (r, s) in [("pending_commit", "state"), ("parts_skewed", "state"), ("warmup", "state"), ("unquotable_dlmm_array", "pricing"), ("below_min_profit", "pricing"),
            ("best", "pricing"), ("gate_shadow:mode_shadow", "policy"), ("no_executor", "policy"), ("rate_queue_timeout", "send_slot"), ("blockhash_stale", "inputs"),
            ("build_error:unquotable", "build"), ("sent", "sent"), ("inflight_same_state", "send_slot"), ("band_throttle", "send_slot")] {
            assert_eq!(reason_stage(r), s, "{r}");
        }
        // a run without an executor: everything is compared
        for (run, rep) in [("no_executor", "gate_shadow:paused"), ("rate_queue_timeout", "no_executor"), ("inflight_same_state", "no_executor")] {
            assert!(!executor_not_replayed(run, rep, false), "{run} / {rep}");
        }
        // a run with an executor: its verdict against the replay's stand-in is not replayed (counted, never OK) ...
        for run in ["sent", "not_sent", "fee_cap", "gate_shadow:mode_shadow", "inflight_same_state", "band_throttle", "blockhash_stale", "rate_queue_timeout"] {
            assert!(executor_not_replayed(run, "no_executor", true) && executor_not_replayed(run, "gate_shadow:paused", true), "{run}");
        }
        // ... but a replay whose state or pricing stage differs is a difference, whatever the run's executor said
        for (run, rep) in [("sent", "warmup"), ("sent", "resync"), ("not_sent", "state_unavailable"), ("sent", "below_min_profit"), ("warmup", "no_executor"),
            ("below_min_profit", "no_executor")] {
            assert!(!executor_not_replayed(run, rep, true), "{run} / {rep}");
        }
        assert_eq!(field_class("reason", &json!("no_executor"), &json!("below_min_profit")), "pricing");
        assert_eq!(field_class("routes[1].net", &json!(1), &json!(2)), "pricing");
        assert_eq!(field_class("stages.t_commit", &json!(1), &json!(2)), "state");
    }

    /// the SendGate a journaled gate state describes
    #[test]
    fn gate_states_rebuild() {
        let g = journal::gate_of(&json!({ "mode": "shadow", "reason": "mode_shadow", "detail": null, "sticky": true })).unwrap();
        assert_eq!((g.allows(), g.reason(), g.sticky()), (false, "mode_shadow".to_string(), true));
        assert!(journal::gate_of(&json!({ "mode": "live" })).unwrap().allows());
        assert_eq!(journal::gate_of(&json!({ "mode": "stopped", "reason": "deadline" })).unwrap().mode(), crate::control::GateMode::Stopped);
        assert!(journal::gate_of(&json!({ "mode": null, "src": "decision" })).is_none(), "a run without a gate");
    }

    /// the compare's line reader: a zstd file a frame at a time, a line split across two frames, the header skipped, a
    /// trailing incomplete frame left out (review WP-09 #7)
    #[test]
    fn lines_stream_across_frames() {
        let d = std::env::temp_dir().join(format!("arbx-lines-{}-{}", std::process::id(), crate::feeds::clock::real_ns()));
        std::fs::create_dir_all(&d).unwrap();
        let header = json!({ "schema": "arbx.decisions/1.0", "file_seq": 0 }).to_string();
        let mut z = zstd::bulk::compress(format!("{header}\n{{\"a\":1}}\n{{\"a\":").as_bytes(), 1).unwrap();
        z.extend(zstd::bulk::compress(b"2}\n{\"a\":3}\n", 1).unwrap());
        let mut tail = zstd::bulk::compress(b"{\"a\":4}\n", 1).unwrap();
        tail.truncate(tail.len() - 3);
        z.extend(tail);
        std::fs::write(d.join("decisions.000.jsonl.zst"), &z).unwrap();
        std::fs::write(d.join("decisions.001.jsonl"), format!("{header}\n{{\"a\":5}}\n\n{{\"a\":6}}")).unwrap();
        let mut l = Lines::open(&d, "decisions");
        let mut got = Vec::new();
        while let Some(v) = l.next().unwrap() { got.push(v["a"].as_u64().unwrap()); }
        assert_eq!(got, vec![1, 2, 3, 5, 6]);
        let _ = std::fs::remove_dir_all(&d);
        let mut r = IdRanges::default();
        for i in [3, 4, 5, 9, 10, 20] { r.push(i); }
        assert!(r.contains(4) && r.contains(10) && r.contains(20) && !r.contains(6) && !r.contains(2) && !r.contains(21), "{r:?}");
    }

    /// the differing fields of two decision lines: routes and stages field by field, the rest whole
    #[test]
    fn diff_fields_names_the_fields() {
        let a = json!({ "reason": "best", "routes": [{ "net": 1, "cu": 2 }, { "net": 5 }], "stages": { "t_commit": 1, "t_engine": 2 }, "sv": { "h": "x" } });
        let b = json!({ "reason": "best", "routes": [{ "net": 1, "cu": 3 }], "stages": { "t_commit": 1, "t_engine": 3 }, "sv": { "h": "y" } });
        let mut out = Vec::new();
        diff_fields("", &a, &b, &mut out);
        let names: Vec<&str> = out.iter().map(|x| x.0.as_str()).collect();
        assert_eq!(names, vec!["routes[0].cu", "routes[1]", "stages.t_engine", "sv"]);
    }
}
