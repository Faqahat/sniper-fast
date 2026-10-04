//! Run provenance (PLAN WP-01 item 4; MEASUREMENT §4.2 meta.json v2): which binary, config and on-chain programs a run
//! used, on which host, with which clock. Everything here runs once per segment, off the hot path: at boot (the route
//! program, before anything can send) or in the background after the feeds start (the venue programs, review F1/M8).
//!
//! - **Build**: the values `buildinfo.rs` stamped at compile time, plus the sha256 and size of `/proc/self/exe` (the file
//!   that is really running, whatever was moved over its path since).
//! - **Config**: the file's sha256, the sha256 of `Config::normalized_json` (ignores comments and formatting), the frozen
//!   copy in the run directory, and whether it matches the campaign's frozen config.
//! - **Programs**: the ELF hash of the route program and of every venue program. The venue programs are fetched in the
//!   background and, within a campaign, once: later segments read each programdata header (45 bytes, `dataSlice`) and
//!   reuse the campaign's cached hashes while the last deploy slot is unchanged. A programdata account is a 45-byte
//!   header (u32 state 3, u64 last deploy slot, `Option<Pubkey>` upgrade authority, padded to 45 bytes), the ELF, then
//!   zero padding up to the allocated length (review F21). The ELF's end is the largest of the section header table's end
//!   and every section's and program header's file range; sha256 and md5 cover bytes `[45, 45 + elf_len)`.
//! - **Clock**: the kernel's NTP state (adjtimex) and `chronyc tracking` when chrony runs.
use crate::config::{sorted, Config, FeedKind};
use crate::pools::Registry;
use crate::rpc::Rpc;
use crate::tx::{b58, pk, Pk};
use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use std::path::Path;

pub const META_SCHEMA: &str = "arbx.meta/2.0";
pub const PROVENANCE_SCHEMA: &str = "arbx.provenance/1.0";

pub fn hex(b: &[u8]) -> String { b.iter().map(|x| format!("{x:02x}")).collect() }

pub fn sha256_hex(b: &[u8]) -> String { use sha2::Digest; hex(&sha2::Sha256::digest(b)) }

pub fn md5_hex(b: &[u8]) -> String { use md5::Digest; hex(&md5::Md5::digest(b)) }

/// sha256 (hex) and size of a file, read in 1 MiB pieces
pub fn file_sha256(path: &Path) -> Result<(String, u64)> {
    use sha2::Digest;
    use std::io::Read;
    let mut f = std::fs::File::open(path).with_context(|| format!("opening {}", path.display()))?;
    let mut h = sha2::Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    let mut n = 0u64;
    loop {
        let k = f.read(&mut buf)?;
        if k == 0 { break; }
        h.update(&buf[..k]);
        n += k as u64;
    }
    Ok((hex(&h.finalize()), n))
}

// ------------------------------------------------------------------ build

/// meta.json `build` (MEASUREMENT §4.2): the compile-time stamp of buildinfo.rs and the running file's hash (computed
/// once per process)
pub fn build_json() -> Value {
    static BUILD: std::sync::OnceLock<Value> = std::sync::OnceLock::new();
    BUILD.get_or_init(build_json_now).clone()
}

fn build_json_now() -> Value {
    let dirty = match env!("ARBX_GIT_DIRTY") { "true" => json!(true), "false" => json!(false), _ => Value::Null };
    let features: Vec<&str> = env!("ARBX_TARGET_FEATURES").split(',').filter(|s| !s.is_empty()).collect();
    let (bin_sha, bin_size) = match file_sha256(Path::new("/proc/self/exe")) { Ok((h, n)) => (json!(h), json!(n)), Err(_) => (Value::Null, Value::Null) };
    json!({
        "version": env!("CARGO_PKG_VERSION"),
        "git_commit": env!("ARBX_GIT_COMMIT"), "git_dirty": dirty,
        "dirty_sha256": Some(env!("ARBX_DIRTY_SHA256")).filter(|s| !s.is_empty()),
        "rustc": env!("ARBX_RUSTC"), "profile": env!("ARBX_PROFILE"), "target_features": features,
        "build_ts": env!("ARBX_BUILD_TS").parse::<u64>().ok(),
        "binary_path": std::fs::read_link("/proc/self/exe").ok().map(|p| p.display().to_string()),
        "binary_sha256": bin_sha, "binary_size": bin_size,
    })
}

/// "<commit8>[+dirty]": one short line for run.log and `arbx --version`-like output
pub fn build_short() -> String {
    let c = env!("ARBX_GIT_COMMIT");
    format!("{}{}", &c[..c.len().min(8)], if env!("ARBX_GIT_DIRTY") == "true" { "+dirty" } else { "" })
}

// ------------------------------------------------------------------ config

/// meta.json `config` (MEASUREMENT §4.2). `cfg` is the config as loaded from the file, before any command-line override
/// (review F2: `normalized_sha256` is then the same in every segment of a campaign and equals `arbx provenance`'s; what
/// the command line changed is in meta.json `overrides`, and `effective_mode` is set by the caller). `frozen_copy`: the
/// name of the copy in the run directory. With a campaign directory, its `campaign.json` names the campaign's frozen
/// config, and `matches_campaign` says whether this file is it
pub fn config_json(path: &Path, raw: &[u8], cfg: &Config, frozen_copy: Option<&str>, campaign_dir: Option<&Path>) -> Value {
    let file_sha = sha256_hex(raw);
    let campaign_sha = campaign_dir.and_then(|d| std::fs::read_to_string(d.join("campaign.json")).ok())
        .and_then(|t| serde_json::from_str::<Value>(&t).ok()).and_then(|v| v["config"]["sha256"].as_str().map(str::to_string));
    json!({
        "path": std::fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf()).display().to_string(),
        "file_sha256": file_sha, "normalized_sha256": cfg.normalized_sha256(), "config_version": cfg.config_version,
        "mode": cfg.mode, "effective_mode": cfg.mode, "frozen_copy": frozen_copy,
        "campaign_config_sha256": campaign_sha, "matches_campaign": campaign_sha.as_ref().map(|c| *c == file_sha),
    })
}

/// a config section as JSON, keys sorted, every URL cut to scheme://host (keys may live in URLs)
pub fn section<T: serde::Serialize>(x: &T) -> Value { scrub_urls(sorted(serde_json::to_value(x).unwrap_or(Value::Null))) }

fn scrub_urls(v: Value) -> Value {
    match v {
        Value::String(s) if s.contains("://") => Value::String(crate::rpc::scrub(&s)),
        Value::Object(m) => Value::Object(m.into_iter().map(|(k, v)| (k, scrub_urls(v))).collect()),
        Value::Array(a) => Value::Array(a.into_iter().map(scrub_urls).collect()),
        x => x,
    }
}

// ------------------------------------------------------------------ hosts

/// the host (and port) of a URL, never its path or query (where provider keys live): `https://a.b:443/x?k=1` -> `a.b:443`
pub fn host_of(url: &str) -> String {
    let rest = url.split_once("://").map_or(url, |x| x.1);
    let host = rest.split(['/', '?', '#']).next().unwrap_or("");
    // user:password@host
    host.rsplit_once('@').map_or(host, |x| x.1).to_string()
}

pub fn hostname() -> String {
    std::fs::read_to_string("/proc/sys/kernel/hostname").map(|s| s.trim().to_string()).unwrap_or_default()
}

/// meta.json `feeds`: `id` is the index among the enabled feeds (the id every stream uses); hosts only
pub fn feeds_json(cfg: &Config) -> Value {
    let mut id = 0u16;
    Value::Array(cfg.feeds.iter().map(|f| {
        let fid = f.enabled.then(|| { id += 1; id - 1 });
        let host = match f.kind {
            FeedKind::Udp => f.bind.clone().unwrap_or_default(),
            FeedKind::Multicast => format!("{}:{}@{}", f.group.as_deref().unwrap_or(""), f.port.unwrap_or(0), f.interface.as_deref().unwrap_or("")),
            _ => f.url.as_deref().map(host_of).unwrap_or_default(),
        };
        json!({ "id": fid, "name": f.name, "kind": f.kind, "enabled": f.enabled, "host": host })
    }).collect())
}

/// meta.json `send_paths`: the enabled paths; `id` is the path's index in the running send paths (null when it could
/// not be built)
pub fn send_paths_json(cfg: &Config, built: &[String]) -> Value {
    Value::Array(cfg.sends.iter().filter(|s| s.enabled).map(|s| {
        let n = if s.tip_accounts.is_empty() { crate::send::known_tip_accounts(s.kind).len() } else { s.tip_accounts.len() };
        json!({ "id": built.iter().position(|b| *b == s.name), "name": s.name, "kind": s.kind, "host": host_of(&s.url),
            "max_per_sec": s.max_per_sec, "tip_accounts_n": n })
    }).collect())
}

/// meta.json `rpc`: every configured provider, host only; `available`: its environment is complete. Roles: every
/// available provider serves `boot` (the race); the `[exec]` ones also `exec`; WP-03b: the chain-fetch roles
/// `[[chainfetch.provider]]` gives it, and `max_rps`, its token bucket for the whole process (null: no limit)
pub fn rpc_json(cfg: &Config) -> Value {
    let (eps, _) = cfg.rpc.endpoints();
    let available: Vec<String> = eps.iter().map(|e| e.name.clone()).collect();
    let cf = &cfg.chainfetch;
    let fetch_roles = |name: &str| -> Vec<&'static str> {
        crate::rpc::Role::FETCH.iter().filter(|r| cf.providers_for(r.as_str(), &available).iter().any(|n| n == name)).map(|r| r.as_str()).collect()
    };
    let max_rps = |name: &str| { let r = cf.limit_of(name).0; (r > 0.0).then_some(r) };
    let mut out = Vec::new();
    if let Some(e) = eps.iter().find(|e| e.name == "default") {
        let mut roles = vec!["boot"];
        roles.extend(fetch_roles("default"));
        out.push(json!({ "name": "default", "host": host_of(&e.url), "available": true, "roles": roles, "max_rps": max_rps("default") }));
    }
    for e in &cfg.rpc.endpoints {
        let live = eps.iter().find(|x| x.name == e.name);
        let host = live.map(|x| host_of(&x.url)).or_else(|| e.url.as_deref().map(host_of));
        let mut roles = Vec::new();
        if e.enabled { roles.push("boot"); if cfg.exec.rpc.contains(&e.name) { roles.push("exec"); } }
        if live.is_some() { roles.extend(fetch_roles(&e.name)); }
        out.push(json!({ "name": e.name, "host": host, "enabled": e.enabled, "available": live.is_some(), "roles": roles, "max_rps": max_rps(&e.name) }));
    }
    Value::Array(out)
}

/// meta.json `inputs` (review N8): the other files the run reads at start, which the config names but does not hash:
/// `{<key>: {path, sha256, size} | {path, error}}` for `[live] crowded_pools_file`, `[pools] templates_json` and
/// `[strategy] signer_stats_file` (read at start, rewritten at stop). Unset ones are left out
pub fn inputs_json(cfg: &Config) -> Value {
    let mut m = serde_json::Map::new();
    for (k, p) in [("crowded_pools_file", Some(cfg.live.crowded_pools_file.as_str())), ("templates_json", cfg.pools.templates_json.as_deref()),
        ("signer_stats_file", Some(cfg.strategy.signer_stats_file.as_str()))] {
        let Some(p) = p.filter(|p| !p.is_empty()) else { continue };
        m.insert(k.into(), match file_sha256(Path::new(p)) {
            Ok((h, n)) => json!({ "path": p, "sha256": h, "size": n }),
            Err(e) => json!({ "path": p, "sha256": null, "error": format!("{e:#}") }),
        });
    }
    Value::Object(m)
}

/// meta.json `pools`
pub fn pools_json(reg: &Registry, cfg: &Config) -> Value {
    let mut by_venue = std::collections::BTreeMap::<String, usize>::new();
    for &i in reg.pairs.values().flatten() { *by_venue.entry(format!("{:?}", reg.pools[i].venue)).or_default() += 1; }
    let sha = |p: Option<&str>| p.and_then(|p| file_sha256(Path::new(p)).ok()).map(|x| x.0);
    json!({ "summary": reg.summary(), "n_pools": reg.pairs.values().map(|v| v.len()).sum::<usize>(), "n_pairs": reg.pairs.len(),
        "by_venue": by_venue, "seed_csv_sha256": sha(Some(&cfg.pools.seed_csv)), "registry_sha256": sha(cfg.pools.registry_json.as_deref()),
        "file": null })
}

// ------------------------------------------------------------------ programs

pub const UPGRADEABLE_LOADER: &str = "BPFLoaderUpgradeab1e11111111111111111111111";
pub const LOADER_V2: &str = "BPFLoader2111111111111111111111111111111111";
/// u32 state (3) + u64 last deploy slot + `Option<Pubkey>` (1 + 32)
pub const PROGRAMDATA_HEADER: usize = 45;

fn u64_at(b: &[u8], o: usize) -> Result<u64> {
    Ok(u64::from_le_bytes(b.get(o..o + 8).with_context(|| format!("truncated at {o}"))?.try_into().unwrap()))
}

/// The length of the ELF image at the start of `elf` (which may be followed by padding): the largest of the ELF
/// header, the program and section header tables' ends, and every program header's and section's file range
/// (`SHT_NOBITS` sections hold no file bytes)
pub fn elf_len(elf: &[u8]) -> Result<usize> {
    if elf.len() < 64 || elf[..4] != *b"\x7fELF" { bail!("not an ELF image"); }
    if elf[4] != 2 || elf[5] != 1 { bail!("not a 64-bit little-endian ELF"); }
    let u16_at = |o: usize| u16::from_le_bytes([elf[o], elf[o + 1]]) as u64;
    let u32_at = |o: u64| -> Result<u32> { let o = o as usize; Ok(u32::from_le_bytes(elf.get(o..o + 4).context("truncated")?.try_into().unwrap())) };
    let (phoff, shoff) = (u64_at(elf, 0x20)?, u64_at(elf, 0x28)?);
    let (ehsize, phentsize, phnum, shentsize, shnum) = (u16_at(0x34), u16_at(0x36), u16_at(0x38), u16_at(0x3a), u16_at(0x3c));
    let add = |a: u64, b: u64| a.checked_add(b).context("ELF offsets overflow");
    let mut end = ehsize.max(64);
    if phnum > 0 {
        if phentsize < 0x38 { bail!("program header entries of {phentsize} bytes"); }
        end = end.max(add(phoff, phnum * phentsize)?);
        for i in 0..phnum {
            let o = (phoff + i * phentsize) as usize;
            end = end.max(add(u64_at(elf, o + 0x08)?, u64_at(elf, o + 0x20)?)?);
        }
    }
    if shnum > 0 {
        if shentsize < 0x40 { bail!("section header entries of {shentsize} bytes"); }
        end = end.max(add(shoff, shnum * shentsize)?);
        for i in 0..shnum {
            let o = shoff + i * shentsize;
            if u32_at(o + 4)? == 8 { continue; } // SHT_NOBITS
            end = end.max(add(u64_at(elf, (o + 0x18) as usize)?, u64_at(elf, (o + 0x20) as usize)?)?);
        }
    }
    if end > elf.len() as u64 { bail!("the ELF ends at {end}, past the {} bytes there are", elf.len()); }
    Ok(end as usize)
}

/// An ELF image's hashes. `trailing_nonzero`: non-zero bytes after its end (0 for a well-formed programdata account;
/// anything else means the end was computed short)
#[derive(Debug, Clone)]
pub struct ElfHash { pub elf_len: usize, pub sha256: String, pub md5: String, pub trailing_nonzero: usize }

pub fn hash_elf(bytes: &[u8]) -> Result<ElfHash> {
    let n = elf_len(bytes)?;
    Ok(ElfHash { elf_len: n, sha256: sha256_hex(&bytes[..n]), md5: md5_hex(&bytes[..n]), trailing_nonzero: bytes[n..].iter().filter(|b| **b != 0).count() })
}

#[derive(Debug, Clone)]
pub struct ProgramData { pub last_deploy_slot: u64, pub upgrade_authority: Option<Pk>, pub elf: ElfHash }

/// A programdata account of the upgradeable loader: its header, then the ELF's hashes without the zero padding
pub fn parse_programdata(data: &[u8]) -> Result<ProgramData> {
    if data.len() < PROGRAMDATA_HEADER { bail!("programdata of {} bytes: shorter than its header", data.len()); }
    let h = parse_programdata_header(data)?;
    Ok(ProgramData { last_deploy_slot: h.last_deploy_slot, upgrade_authority: h.upgrade_authority, elf: hash_elf(&data[PROGRAMDATA_HEADER..])? })
}

/// The programdata address an upgradeable program account points to (state 2)
pub fn programdata_address(program_data: &[u8]) -> Result<Pk> {
    if program_data.len() < 36 || u32::from_le_bytes(program_data[..4].try_into().unwrap()) != 2 { bail!("not an upgradeable program account"); }
    Ok(program_data[4..36].try_into().unwrap())
}

/// A program to hash at boot
#[derive(Debug, Clone)]
pub struct ProgramSpec { pub role: &'static str, pub id: Pk, pub name: String, pub expected_sha256: String, pub expected_md5: String }

/// The route program (`[exec] program`, with the expected hashes) and every venue program
pub fn program_specs(cfg: &Config) -> Vec<ProgramSpec> {
    let mut v = vec![route_spec(cfg)];
    v.extend(venue_specs());
    v
}

/// The route program: checked at boot, before anything can send
pub fn route_spec(cfg: &Config) -> ProgramSpec {
    ProgramSpec { role: "route", id: pk(&cfg.exec.program), name: "route".into(),
        expected_sha256: cfg.exec.expected_program_sha256.clone(), expected_md5: cfg.exec.expected_program_md5.clone() }
}

/// The venue programs: recorded, not checked (fetched in the background, `fetch_programs_cached`)
pub fn venue_specs() -> Vec<ProgramSpec> {
    use crate::venues::Venue;
    [Venue::PumpSwap, Venue::RayCpmm, Venue::RayAmmV4, Venue::Dlmm, Venue::DammV2].into_iter()
        .map(|x| ProgramSpec { role: "venue", id: x.program(), name: format!("{x:?}"), expected_sha256: String::new(), expected_md5: String::new() }).collect()
}

/// A program's entry before its hashes are in (meta.json is written before the background fetch ends): every hash
/// field null, `pending: true`. A segment that stops first keeps it so
pub fn pending_entry(spec: &ProgramSpec) -> Value {
    let mut v = program_entry(spec, Err(anyhow::anyhow!("pending")));
    v["error"] = Value::Null;
    v["ok"] = Value::Null;
    v["pending"] = json!(true);
    v
}

/// A program's meta.json `programs` entry from what the chain returned: the program account (owner, data) and, for
/// the upgradeable loader, its programdata account's data
pub fn program_entry(spec: &ProgramSpec, fetched: Result<(Pk, Vec<u8>, Option<(Pk, Vec<u8>)>)>) -> Value {
    let expect = |e: &str| Some(e.to_string()).filter(|e| !e.is_empty());
    let mut v = json!({ "role": spec.role, "id": b58(&spec.id), "name": spec.name, "programdata": null, "last_deploy_slot": null,
        "upgrade_authority": null, "elf_len": null, "elf_sha256": null, "elf_md5": null, "trailing_nonzero": null,
        "expected_sha256": expect(&spec.expected_sha256), "expected_md5": expect(&spec.expected_md5), "ok": null, "error": null });
    let res = fetched.and_then(|(owner, data, pd)| -> Result<(Option<Pk>, Option<ProgramData>, ElfHash)> {
        if owner == pk(UPGRADEABLE_LOADER) {
            let (addr, pdata) = pd.context("programdata not fetched")?;
            let p = parse_programdata(&pdata)?;
            let h = p.elf.clone();
            Ok((Some(addr), Some(p), h))
        } else if owner == pk(LOADER_V2) {
            Ok((None, None, hash_elf(&data)?))
        } else {
            bail!("owner {} is not a loader this procedure knows", b58(&owner))
        }
    });
    match res {
        Ok((addr, p, h)) => {
            v["programdata"] = json!(addr.map(|a| b58(&a)));
            if let Some(p) = p { v["last_deploy_slot"] = json!(p.last_deploy_slot); v["upgrade_authority"] = json!(p.upgrade_authority.map(|a| b58(&a))); }
            v["elf_len"] = json!(h.elf_len); v["elf_sha256"] = json!(h.sha256); v["elf_md5"] = json!(h.md5); v["trailing_nonzero"] = json!(h.trailing_nonzero);
            if !spec.expected_sha256.is_empty() || !spec.expected_md5.is_empty() {
                v["ok"] = json!((spec.expected_sha256.is_empty() || spec.expected_sha256 == h.sha256) && (spec.expected_md5.is_empty() || spec.expected_md5 == h.md5));
            }
        }
        Err(e) => {
            v["error"] = json!(crate::rpc::scrub(&format!("{e:#}")));
            // an expected hash that cannot be checked is not met (fail closed)
            if !spec.expected_sha256.is_empty() || !spec.expected_md5.is_empty() { v["ok"] = json!(false); }
        }
    }
    v
}

/// Fetch and hash every program: one RPC call per account (programdata accounts run to megabytes), 3 tries each.
/// Failures are recorded in the entry, never fatal.
pub async fn fetch_programs(rpc: &Rpc, specs: &[ProgramSpec]) -> Vec<Value> {
    async fn one(rpc: &Rpc, k: Pk) -> Result<(Pk, Vec<u8>)> {
        let mut last = None;
        for i in 0..3 {
            if i > 0 { tokio::time::sleep(std::time::Duration::from_millis(500)).await; }
            match rpc.accounts(&[k]).await {
                Ok((_, mut v)) => match v.pop().flatten() { Some(a) => return Ok((a.owner, a.data)), None => bail!("account {} not found", b58(&k)) },
                Err(e) => last = Some(e),
            }
        }
        Err(last.unwrap())
    }
    let mut out = Vec::new();
    for s in specs {
        let fetched = async {
            let (owner, data) = one(rpc, s.id).await?;
            let pd = if owner == pk(UPGRADEABLE_LOADER) { let a = programdata_address(&data)?; Some((a, one(rpc, a).await?.1)) } else { None };
            anyhow::Ok((owner, data, pd))
        }.await;
        let mut e = program_entry(s, fetched);
        e["source"] = json!("rpc");
        out.push(e);
    }
    out
}

/// The campaign's cache of venue program hashes (`<campaign>/programs.cache.json`): one entry per programdata account,
/// valid while its last deploy slot is unchanged (an upgrade always changes it)
pub const PROGRAMS_CACHE: &str = "programs.cache.json";
pub const PROGRAMS_CACHE_SCHEMA: &str = "arbx.programs-cache/1.0";

/// `programs` entries for `specs`, hashed once per campaign (review M8). Without a cache file every program is fetched
/// whole (`fetch_programs`). With one: the program accounts (small) and the programdata headers (45 bytes each, one
/// `dataSlice` call) are read; a programdata account whose address and last deploy slot match the cache reuses its
/// hashes (`source: "cache"`, the upgrade authority taken from the fresh header); the others are fetched whole and
/// cached (`source: "rpc"`). Failures are recorded in the entry, never fatal
pub async fn fetch_programs_cached(rpc: &Rpc, specs: &[ProgramSpec], cache: Option<&Path>) -> Vec<Value> {
    let Some(cache) = cache else { return fetch_programs(rpc, specs).await };
    let mut store: Value = std::fs::read_to_string(cache).ok().and_then(|t| serde_json::from_str(&t).ok())
        .filter(|v: &Value| v["schema"] == PROGRAMS_CACHE_SCHEMA).unwrap_or_else(|| json!({ "schema": PROGRAMS_CACHE_SCHEMA, "programs": {} }));
    // the programdata addresses and their headers, in two small calls
    let ids: Vec<Pk> = specs.iter().map(|s| s.id).collect();
    let headers: Vec<Option<(Pk, ProgramHeader)>> = match rpc.accounts(&ids).await {
        Ok((_, accts)) => {
            let pds: Vec<Option<Pk>> = accts.iter().map(|a| a.as_ref().filter(|a| a.owner == pk(UPGRADEABLE_LOADER)).and_then(|a| programdata_address(&a.data).ok())).collect();
            let want: Vec<Pk> = pds.iter().flatten().copied().collect();
            let heads = if want.is_empty() { None } else { rpc.accounts_slice(&want, 0, PROGRAMDATA_HEADER).await.ok() };
            let mut by: std::collections::HashMap<Pk, ProgramHeader> = Default::default();
            if let Some((_, hs)) = heads {
                for (k, h) in want.iter().zip(hs) { if let Some(h) = h.and_then(|h| parse_programdata_header(&h.data).ok()) { by.insert(*k, h); } }
            }
            pds.iter().map(|pd| pd.and_then(|pd| by.get(&pd).map(|h| (pd, h.clone())))).collect()
        }
        Err(_) => vec![None; specs.len()],
    };
    let mut out = Vec::new();
    let mut changed = false;
    for (s, h) in specs.iter().zip(headers) {
        if let Some((pd, h)) = &h {
            let c = &store["programs"][b58(pd)];
            if c["last_deploy_slot"].as_u64() == Some(h.last_deploy_slot) && c["entry"]["elf_sha256"].is_string() && c["entry"]["id"] == json!(b58(&s.id)) {
                let mut e = c["entry"].clone();
                e["upgrade_authority"] = json!(h.upgrade_authority.map(|a| b58(&a)));
                e["expected_sha256"] = json!(Some(s.expected_sha256.clone()).filter(|x| !x.is_empty()));
                e["expected_md5"] = json!(Some(s.expected_md5.clone()).filter(|x| !x.is_empty()));
                e["ok"] = if s.expected_sha256.is_empty() && s.expected_md5.is_empty() { Value::Null } else {
                    json!((s.expected_sha256.is_empty() || e["elf_sha256"] == json!(s.expected_sha256)) && (s.expected_md5.is_empty() || e["elf_md5"] == json!(s.expected_md5)))
                };
                e["source"] = json!("cache");
                out.push(e);
                continue;
            }
        }
        let e = fetch_programs(rpc, std::slice::from_ref(s)).await.pop().unwrap_or(Value::Null);
        if let (Some(pd), Some(slot), true) = (e["programdata"].as_str(), e["last_deploy_slot"].as_u64(), e["elf_sha256"].is_string()) {
            let mut kept = e.clone();
            if let Some(o) = kept.as_object_mut() { o.remove("source"); }
            store["programs"][pd] = json!({ "last_deploy_slot": slot, "entry": kept, "t_ns": crate::feeds::clock::now_ns() });
            changed = true;
        }
        out.push(e);
    }
    if changed { let _ = crate::control::write_atomic(cache, serde_json::to_string_pretty(&store).unwrap_or_default().as_bytes()); }
    out
}

/// A programdata account's header: last deploy slot and upgrade authority
#[derive(Debug, Clone, PartialEq)]
pub struct ProgramHeader { pub last_deploy_slot: u64, pub upgrade_authority: Option<Pk> }

pub fn parse_programdata_header(data: &[u8]) -> Result<ProgramHeader> {
    if data.len() < PROGRAMDATA_HEADER { bail!("programdata header of {} bytes", data.len()); }
    let tag = u32::from_le_bytes(data[..4].try_into().unwrap());
    if tag != 3 { bail!("not a programdata account (state {tag}, expected 3)"); }
    let upgrade_authority = match data[12] { 0 => None, 1 => Some(data[13..45].try_into().unwrap()), x => bail!("bad Option tag {x} for the upgrade authority") };
    Ok(ProgramHeader { last_deploy_slot: u64_at(data, 4)?, upgrade_authority })
}

/// The route program's check: None when no hash is expected; else (ok, a line for run.log)
pub fn route_check(programs: &[Value]) -> Option<(bool, String)> {
    let r = programs.iter().find(|p| p["role"] == "route")?;
    let ok = r["ok"].as_bool()?;
    Some((ok, format!("route program {}: sha256 {} md5 {} (expected sha256 {} md5 {}){}", r["id"].as_str().unwrap_or("?"),
        r["elf_sha256"].as_str().unwrap_or("-"), r["elf_md5"].as_str().unwrap_or("-"), r["expected_sha256"].as_str().unwrap_or("-"),
        r["expected_md5"].as_str().unwrap_or("-"), r["error"].as_str().map(|e| format!(": {e}")).unwrap_or_default())))
}

// ------------------------------------------------------------------ clock

/// meta.json `clock`: the kernel's view (adjtimex: state, offset, error bounds, unsynchronised flag) and chrony's
/// (`chronyc -c tracking`, 2 s at most) when it runs. `sync_offset_ms` comes from chrony when present (its signed
/// "system time" correction), else from the kernel's NTP offset
pub fn clock_json() -> Value {
    let mut tx: libc::timex = unsafe { std::mem::zeroed() };
    let state = unsafe { libc::adjtimex(&mut tx) };
    let kernel = if state < 0 { Value::Null } else {
        let nano = tx.status & libc::STA_NANO != 0;
        let offset_ns = if nano { tx.offset as i64 } else { tx.offset as i64 * 1_000 };
        json!({ "state": state, "offset_ns": offset_ns, "maxerror_us": tx.maxerror, "esterror_us": tx.esterror, "unsynced": tx.status & libc::STA_UNSYNC != 0 })
    };
    let chrony = chrony_tracking();
    let (offset_ms, src) = match (&chrony, &kernel) {
        (Some(c), _) if c["system_time_s"].is_number() => (c["system_time_s"].as_f64().map(|s| s * 1e3), "chronyc"),
        (_, k) if k["offset_ns"].is_number() => (k["offset_ns"].as_i64().map(|n| n as f64 / 1e6), "adjtimex"),
        _ => (None, "none"),
    };
    json!({ "source": "CLOCK_REALTIME", "sync_offset_ms": offset_ms, "sync_source": src, "adjtimex": kernel, "chrony": chrony })
}

fn chrony_tracking() -> Option<Value> {
    use std::process::{Command, Stdio};
    let mut child = Command::new("chronyc").args(["-c", "tracking"]).stdout(Stdio::piped()).stderr(Stdio::null()).stdin(Stdio::null()).spawn().ok()?;
    let t0 = std::time::Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(st)) if st.success() => break,
            Ok(None) if t0.elapsed() < std::time::Duration::from_secs(2) => std::thread::sleep(std::time::Duration::from_millis(20)),
            _ => { let _ = child.kill(); let _ = child.wait(); return None; }
        }
    }
    let mut out = String::new();
    std::io::Read::read_to_string(&mut child.stdout.take()?, &mut out).ok()?;
    parse_chrony_csv(&out)
}

/// `chronyc -c tracking`: ref id, ref name, stratum, ref time, system time, last offset, rms offset, frequency,
/// residual frequency, skew, root delay, root dispersion, update interval, leap status
pub fn parse_chrony_csv(line: &str) -> Option<Value> {
    let f: Vec<&str> = line.trim().split(',').collect();
    if f.len() < 14 { return None; }
    let n = |i: usize| f[i].trim().parse::<f64>().ok();
    Some(json!({ "ref_id": f[0], "ref_name": f[1], "stratum": f[2].trim().parse::<u32>().ok(), "system_time_s": n(4), "last_offset_s": n(5),
        "rms_offset_s": n(6), "frequency_ppm": n(7), "skew_ppm": n(9), "root_delay_s": n(10), "root_dispersion_s": n(11), "leap": f[13].trim() }))
}

// ------------------------------------------------------------------ meta.json

/// The files a segment writes outside the recorder, with their schemas (MEASUREMENT §4). `arbx run` adds every recorder
/// stream (`rec::Rec::streams_json`: `attempts` `arbx.attempts/1.1`, `status` `arbx.status/2.0`, ...; WP-02)
pub fn streams_json() -> Value {
    let mut m = serde_json::Map::new();
    for (k, v) in [("meta", META_SCHEMA), ("stop", crate::control::STOP_SCHEMA), ("control", crate::control::CONTROL_SCHEMA), ("config", "toml (frozen copy)"),
        ("manifest", crate::rec::manifest::SCHEMA)] {
        m.insert(k.into(), v.into());
    }
    Value::Object(m)
}

/// The `arbx provenance` report: what meta.json would say without booting anything: build, binary, config, host,
/// clock, the programs (unless offline) and the config-derived sections (feeds, send paths, RPC hosts, normalized
/// strategy / send / builder / live). Pools, held mints and the send paths' ids need a boot: they are not here
pub fn report(path: &Path, raw: &[u8], cfg: &Config, programs: Option<Vec<Value>>) -> Value {
    json!({ "schema": PROVENANCE_SCHEMA, "t_ns": crate::feeds::clock::now_ns(), "host": hostname(), "build": build_json(),
        "config": config_json(path, raw, cfg, None, None), "programs": programs, "clock": clock_json(),
        "feeds": feeds_json(cfg), "send_paths": send_paths_json(cfg, &[]), "rpc": rpc_json(cfg), "state": { "url_host": host_of(&cfg.state.url) },
        "inputs": inputs_json(cfg),
        "strategy": section(&cfg.strategy), "send": section(&cfg.sends), "builder": section(&cfg.exec), "live": section(&cfg.live),
        "sim": section(&cfg.sim), "canary": section(&cfg.canary), "gate": section(&cfg.gate), "record": section(&cfg.record), "control": section(&cfg.control) })
}

#[cfg(test)]
mod tests {
    use super::*;
    use base64::Engine as _;

    fn fixture(name: &str) -> (Value, Vec<u8>) {
        let p = Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/programs").join(name);
        let v: Value = serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap();
        let data = base64::engine::general_purpose::STANDARD.decode(v["result"]["value"]["data"][0].as_str().unwrap()).unwrap();
        (v, data)
    }

    const ROUTE_MD5: &str = "809315befcb9554211f8019bf9df290b";
    const ROUTE_SHA256: &str = "e4f03590bda38d95b884f56a1192070f7e34320840a6d89a568c6ed6024bae2f";

    /// PLAN WP-01 acceptance (F21): the deployed 8K8uyQDt programdata, without its header and zero padding, hashes to the
    /// reproducible build's md5 809315be…
    #[test]
    fn programdata_elf_hash_of_the_deployed_route_program() {
        let (prog, pdata) = fixture("8K8uyQDt-program.json");
        let (_, data) = fixture("8K8uyQDt-programdata.json");
        assert_eq!(prog["result"]["value"]["owner"], UPGRADEABLE_LOADER);
        let addr = programdata_address(&pdata).unwrap();
        assert_eq!(b58(&addr), "5V3ssdCfTyENu2YGzXdWo9RQP2se8KrqmLRHsLVrvGji");
        let p = parse_programdata(&data).unwrap();
        assert_eq!(data.len(), 43_485);
        assert_eq!(p.elf.elf_len, 35_240, "the section header table's end: 34,984 + 4 x 64");
        assert_eq!(p.elf.md5, ROUTE_MD5);
        assert!(p.elf.md5.starts_with("809315be"));
        assert_eq!(p.elf.sha256, ROUTE_SHA256);
        assert_eq!(p.elf.trailing_nonzero, 0, "everything after the ELF is padding");
        assert_eq!(p.last_deploy_slot, 451_798_124);
        assert!(p.upgrade_authority.is_some());
        // the padding is excluded: hashing the whole account body gives something else
        assert_ne!(md5_hex(&data[PROGRAMDATA_HEADER..]), ROUTE_MD5);
        // and the meta.json entry with the expectation met, then missed
        let spec = |sha: &str| ProgramSpec { role: "route", id: pk("8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg"), name: "route".into(), expected_sha256: sha.into(), expected_md5: ROUTE_MD5.into() };
        let fetched = || Ok((pk(UPGRADEABLE_LOADER), pdata.clone(), Some((addr, data.clone()))));
        let e = program_entry(&spec(ROUTE_SHA256), fetched());
        assert_eq!((e["ok"].as_bool(), e["elf_len"].as_u64(), e["elf_md5"].as_str()), (Some(true), Some(35_240), Some(ROUTE_MD5)));
        assert_eq!(e["programdata"], "5V3ssdCfTyENu2YGzXdWo9RQP2se8KrqmLRHsLVrvGji");
        assert_eq!(route_check(&[e]).map(|x| x.0), Some(true));
        let bad = program_entry(&spec(&"0".repeat(64)), fetched());
        assert_eq!(route_check(&[bad]).map(|x| x.0), Some(false), "a different program: live refused");
        let err = program_entry(&spec(ROUTE_SHA256), Err(anyhow::anyhow!("rate limited by https://rpc.example/?api-key=SECRET")));
        assert_eq!(err["ok"], false, "an expected hash that cannot be checked is not met");
        assert!(!err["error"].as_str().unwrap().contains("SECRET"));
        let none = program_entry(&ProgramSpec { expected_sha256: String::new(), expected_md5: String::new(), ..spec("") }, fetched());
        assert!(none["ok"].is_null() && route_check(&[none]).is_none(), "no expectation: recorded, not checked");
    }

    /// A JSON-RPC server on 127.0.0.1 that answers getMultipleAccounts (with or without `dataSlice`) from `accounts`
    /// and records every request: (keys, sliced)
    struct MockRpc { url: String, accounts: std::sync::Arc<std::sync::Mutex<std::collections::HashMap<String, (String, Vec<u8>)>>>, log: std::sync::Arc<std::sync::Mutex<Vec<(Vec<String>, bool)>>> }

    async fn mock_rpc() -> MockRpc {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        let l = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", l.local_addr().unwrap());
        let m = MockRpc { url, accounts: Default::default(), log: Default::default() };
        let (accounts, log) = (m.accounts.clone(), m.log.clone());
        tokio::spawn(async move {
            loop {
                let Ok((mut c, _)) = l.accept().await else { return };
                let (accounts, log) = (accounts.clone(), log.clone());
                tokio::spawn(async move {
                    let mut buf = Vec::new();
                    loop {
                        // one request: headers, then Content-Length bytes
                        let mut tmp = [0u8; 65536];
                        let head_end = loop {
                            if let Some(i) = buf.windows(4).position(|w| w == b"\r\n\r\n") { break i + 4; }
                            match c.read(&mut tmp).await { Ok(0) | Err(_) => return, Ok(n) => buf.extend_from_slice(&tmp[..n]) }
                        };
                        let head = String::from_utf8_lossy(&buf[..head_end]).to_lowercase();
                        let len: usize = head.lines().find_map(|l| l.strip_prefix("content-length:")).and_then(|v| v.trim().parse().ok()).unwrap_or(0);
                        while buf.len() < head_end + len { match c.read(&mut tmp).await { Ok(0) | Err(_) => return, Ok(n) => buf.extend_from_slice(&tmp[..n]) } }
                        let req: Value = serde_json::from_slice(&buf[head_end..head_end + len]).unwrap();
                        buf.drain(..head_end + len);
                        let keys: Vec<String> = req["params"][0].as_array().unwrap().iter().map(|k| k.as_str().unwrap().to_string()).collect();
                        let slice = &req["params"][1]["dataSlice"];
                        log.lock().unwrap().push((keys.clone(), slice.is_object()));
                        let value: Vec<Value> = keys.iter().map(|k| match accounts.lock().unwrap().get(k) {
                            Some((owner, data)) => {
                                let d = if slice.is_object() {
                                    let (o, n) = (slice["offset"].as_u64().unwrap() as usize, slice["length"].as_u64().unwrap() as usize);
                                    data[o.min(data.len())..(o + n).min(data.len())].to_vec()
                                } else { data.clone() };
                                json!({ "data": [base64::engine::general_purpose::STANDARD.encode(&d), "base64"], "owner": owner, "lamports": 1, "executable": false, "rentEpoch": 0 })
                            }
                            None => Value::Null,
                        }).collect();
                        let body = json!({ "jsonrpc": "2.0", "id": req["id"], "result": { "context": { "slot": 400_000_000u64 }, "value": value } }).to_string();
                        let resp = format!("HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\n\r\n{body}", body.len());
                        if c.write_all(resp.as_bytes()).await.is_err() { return; }
                    }
                });
            }
        });
        m
    }

    /// review M8 (and F1): the venue programs are hashed once per campaign. The first segment fetches each programdata
    /// whole and caches its hashes; the next one reads only the 45-byte headers and reuses them while the last deploy
    /// slot is unchanged; a redeploy (a new slot) is fetched whole again. Without a cache every program is fetched whole
    #[tokio::test]
    async fn venue_programs_are_hashed_once_per_campaign() {
        let (prog, pdata) = fixture("8K8uyQDt-program.json");
        let (_, data) = fixture("8K8uyQDt-programdata.json");
        let id = "8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg";
        let pd = "5V3ssdCfTyENu2YGzXdWo9RQP2se8KrqmLRHsLVrvGji";
        let m = mock_rpc().await;
        m.accounts.lock().unwrap().insert(id.into(), (prog["result"]["value"]["owner"].as_str().unwrap().into(), pdata.clone()));
        m.accounts.lock().unwrap().insert(pd.into(), (UPGRADEABLE_LOADER.into(), data.clone()));
        let rpc = Rpc::new(m.url.clone());
        let spec = ProgramSpec { role: "venue", id: pk(id), name: "Fixture".into(), expected_sha256: String::new(), expected_md5: String::new() };
        let d = std::env::temp_dir().join(format!("arbx-prog-cache-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
        std::fs::create_dir_all(&d).unwrap();
        let cache = d.join(PROGRAMS_CACHE);
        let full = |log: &[(Vec<String>, bool)]| log.iter().filter(|(k, sliced)| k.contains(&pd.to_string()) && !sliced).count();
        // segment 1: fetched whole, cached
        let e = fetch_programs_cached(&rpc, std::slice::from_ref(&spec), Some(&cache)).await;
        assert_eq!((e[0]["source"].as_str(), e[0]["elf_md5"].as_str(), e[0]["last_deploy_slot"].as_u64()), (Some("rpc"), Some(ROUTE_MD5), Some(451_798_124)));
        assert!(e[0]["ok"].is_null() && e[0]["error"].is_null(), "{}", e[0]);
        assert_eq!(full(&m.log.lock().unwrap()), 1);
        let c: Value = serde_json::from_str(&std::fs::read_to_string(&cache).unwrap()).unwrap();
        assert_eq!((c["schema"].as_str(), c["programs"][pd]["last_deploy_slot"].as_u64()), (Some(PROGRAMS_CACHE_SCHEMA), Some(451_798_124)));
        // segment 2: headers only (one sliced call), the same hashes from the cache
        m.log.lock().unwrap().clear();
        let e2 = fetch_programs_cached(&rpc, std::slice::from_ref(&spec), Some(&cache)).await;
        assert_eq!((e2[0]["source"].as_str(), e2[0]["elf_sha256"].as_str(), e2[0]["upgrade_authority"].clone()), (Some("cache"), Some(ROUTE_SHA256), e[0]["upgrade_authority"].clone()));
        let log = m.log.lock().unwrap().clone();
        assert_eq!(full(&log), 0, "no programdata fetched whole: {log:?}");
        assert_eq!(log.iter().filter(|x| x.1).count(), 1, "one dataSlice call for the headers");
        // a cached hash still meets (or misses) an expectation
        let route = ProgramSpec { role: "route", expected_md5: ROUTE_MD5.into(), ..spec.clone() };
        assert_eq!(fetch_programs_cached(&rpc, std::slice::from_ref(&route), Some(&cache)).await[0]["ok"], true);
        let wrong = ProgramSpec { role: "route", expected_md5: "0".repeat(32), ..spec.clone() };
        assert_eq!(fetch_programs_cached(&rpc, std::slice::from_ref(&wrong), Some(&cache)).await[0]["ok"], false);
        // a redeploy: a new last deploy slot is fetched whole again
        let mut redeployed = data.clone();
        redeployed[4..12].copy_from_slice(&451_900_000u64.to_le_bytes());
        m.accounts.lock().unwrap().insert(pd.into(), (UPGRADEABLE_LOADER.into(), redeployed));
        m.log.lock().unwrap().clear();
        let e3 = fetch_programs_cached(&rpc, std::slice::from_ref(&spec), Some(&cache)).await;
        assert_eq!((e3[0]["source"].as_str(), e3[0]["last_deploy_slot"].as_u64()), (Some("rpc"), Some(451_900_000)));
        assert_eq!(full(&m.log.lock().unwrap()), 1);
        // no cache (a run outside a campaign): fetched whole
        m.log.lock().unwrap().clear();
        let e4 = fetch_programs_cached(&rpc, std::slice::from_ref(&spec), None).await;
        assert_eq!((e4[0]["source"].as_str(), full(&m.log.lock().unwrap())), (Some("rpc"), 1));
        // an RPC that cannot answer: recorded in the entry, never fatal
        let dead = Rpc::new("http://127.0.0.1:1".into());
        let e5 = fetch_programs_cached(&dead, std::slice::from_ref(&spec), Some(&cache)).await;
        assert!(e5[0]["error"].is_string() && e5[0]["elf_sha256"].is_null());
        // the entry meta.json holds until the background fetch ends
        let p = pending_entry(&spec);
        assert_eq!((p["pending"].as_bool(), p["error"].is_null(), p["ok"].is_null(), p["elf_sha256"].is_null()), (Some(true), true, true, true));
        let _ = std::fs::remove_dir_all(&d);
    }

    /// review N8: the other input files are hashed; unset ones are left out, missing ones say so
    #[test]
    fn inputs_are_hashed() {
        let d = std::env::temp_dir().join(format!("arbx-inputs-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
        std::fs::create_dir_all(&d).unwrap();
        let mut cfg = Config::load(&Path::new(env!("CARGO_MANIFEST_DIR")).join("deploy/arb.toml")).unwrap();
        std::fs::write(d.join("crowded.json"), "[]").unwrap();
        cfg.live.crowded_pools_file = d.join("crowded.json").display().to_string();
        cfg.pools.templates_json = None;
        cfg.strategy.signer_stats_file = d.join("missing.json").display().to_string();
        let v = inputs_json(&cfg);
        assert_eq!((v["crowded_pools_file"]["sha256"].as_str(), v["crowded_pools_file"]["size"].as_u64()), (Some(sha256_hex(b"[]").as_str()), Some(2)));
        assert!(v.get("templates_json").is_none());
        assert!(v["signer_stats_file"]["sha256"].is_null() && v["signer_stats_file"]["error"].is_string());
        let _ = std::fs::remove_dir_all(&d);
    }

    /// the shipped configs expect exactly the deployed route program
    #[test]
    fn maintained_configs_expect_the_deployed_route_program() {
        for f in ["deploy/arbx-stage0.toml", "deploy/arb.toml"] {
            let cfg = Config::load(&Path::new(env!("CARGO_MANIFEST_DIR")).join(f)).unwrap();
            assert_eq!((cfg.exec.expected_program_sha256.as_str(), cfg.exec.expected_program_md5.as_str()), (ROUTE_SHA256, ROUTE_MD5), "{f}");
            let specs = program_specs(&cfg);
            assert_eq!(specs[0].role, "route");
            assert_eq!(b58(&specs[0].id), "8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg");
            assert_eq!(specs.iter().filter(|s| s.role == "venue").count(), 5);
        }
    }

    #[test]
    fn elf_len_refuses_what_is_not_an_elf() {
        assert!(elf_len(b"not an elf at all, not even close to sixty-four bytes long........").is_err());
        let (_, data) = fixture("8K8uyQDt-programdata.json");
        let elf = &data[PROGRAMDATA_HEADER..];
        assert!(elf_len(&elf[..35_000]).is_err(), "truncated before the section headers");
        assert_eq!(elf_len(&elf[..35_240]).unwrap(), 35_240, "no padding at all");
        let mut be = elf.to_vec();
        be[5] = 2;
        assert!(elf_len(&be).is_err(), "big-endian");
        assert!(parse_programdata(&data[..40]).is_err());
        let mut wrong = data.clone();
        wrong[0] = 2;
        assert!(parse_programdata(&wrong).is_err(), "a program account is not programdata");
    }

    /// PLAN WP-01 acceptance: `arbx provenance` prints build, config and binary hashes (the hashing helpers)
    #[test]
    fn provenance_hashes() {
        assert_eq!(sha256_hex(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
        assert_eq!(md5_hex(b"abc"), "900150983cd24fb0d6963f7d28e17f72");
        let f = std::env::temp_dir().join(format!("arbx-prov-{}", std::process::id()));
        std::fs::write(&f, vec![7u8; 3 << 20]).unwrap();
        assert_eq!(file_sha256(&f).unwrap(), (sha256_hex(&vec![7u8; 3 << 20]), 3 << 20), "streamed = whole");
        let _ = std::fs::remove_file(&f);
        let b = build_json();
        assert_eq!(b["binary_sha256"].as_str().map(str::len), Some(64), "the running file is hashed");
        assert!(b["binary_size"].as_u64().unwrap() > 0);
        assert!(b["git_commit"].as_str().is_some_and(|c| c == "unknown" || c.len() == 40), "{}", b["git_commit"]);
        assert!(b["profile"].is_string() && b["rustc"].as_str().unwrap().starts_with("rustc"));
        assert!(b["build_ts"].as_u64().unwrap() > 1_700_000_000_000_000_000);
        // config: the file hash changes with a comment, the normalized one does not
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let (cfg, raw) = Config::load_raw(&root.join("deploy/arb.toml")).unwrap();
        let mut raw2 = b"# a comment\n".to_vec();
        raw2.extend_from_slice(&raw);
        let cfg2 = Config::parse(std::str::from_utf8(&raw2).unwrap()).unwrap();
        let (a, b2) = (config_json(Path::new("arb.toml"), &raw, &cfg, None, None), config_json(Path::new("arb.toml"), &raw2, &cfg2, None, None));
        assert_ne!(a["file_sha256"], b2["file_sha256"]);
        assert_eq!(a["normalized_sha256"], b2["normalized_sha256"]);
        assert_eq!(a["config_version"], 2);
        let r = report(Path::new("deploy/arb.toml"), &raw, &cfg, None);
        assert_eq!(r["schema"], PROVENANCE_SCHEMA);
        assert!(r["build"]["binary_sha256"].is_string() && r["config"]["normalized_sha256"].is_string());
        assert_eq!(r["clock"]["source"], "CLOCK_REALTIME");
        assert!(r["feeds"].is_array() && r["send"].is_array() && r["builder"]["expected_program_md5"].is_string());
        // review M11 / F3: the sections v1 had, and the control socket the supervisor checks
        assert!(r["sim"].is_object() && r["canary"].is_object() && r["gate"].is_object() && r["record"].is_object() && r["inputs"].is_object());
        assert_eq!(r["control"]["socket"], true);
        assert_eq!(r["config"]["effective_mode"], r["config"]["mode"]);
    }

    /// the campaign's frozen config: same bytes = matches
    #[test]
    fn config_matches_the_campaign() {
        let d = std::env::temp_dir().join(format!("arbx-prov-camp-{}", std::process::id()));
        std::fs::create_dir_all(&d).unwrap();
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let (cfg, raw) = Config::load_raw(&root.join("deploy/arb.toml")).unwrap();
        std::fs::write(d.join("campaign.json"), json!({ "config": { "sha256": sha256_hex(&raw) } }).to_string()).unwrap();
        let c = config_json(Path::new("x.toml"), &raw, &cfg, Some("config.toml"), Some(&d));
        assert_eq!((c["matches_campaign"].as_bool(), c["frozen_copy"].as_str()), (Some(true), Some("config.toml")));
        let c = config_json(Path::new("x.toml"), b"other", &cfg, None, Some(&d));
        assert_eq!(c["matches_campaign"], false);
        assert!(config_json(Path::new("x.toml"), &raw, &cfg, None, None)["matches_campaign"].is_null());
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn hosts_never_carry_keys() {
        assert_eq!(host_of("https://edge.erpc.global?api-key=SECRET"), "edge.erpc.global");
        assert_eq!(host_of("http://fra1.landx.dev/txb/${LANDX_KEY}"), "fra1.landx.dev");
        assert_eq!(host_of("udp://fra3.landx.dev:10000"), "fra3.landx.dev:10000");
        assert_eq!(host_of("https://user:pw@grpc.example:443/x"), "grpc.example:443");
        let s = section(&json!({ "url": "https://a.b/key/SECRET?token=X", "n": 1 }));
        assert!(!s.to_string().contains("SECRET") && !s.to_string().contains("token=X"), "{s}");
        let cfg = Config::load(&Path::new(env!("CARGO_MANIFEST_DIR")).join("deploy/arbx-stage0.toml")).unwrap();
        let all = format!("{} {} {}", feeds_json(&cfg), send_paths_json(&cfg, &["jito-bundle".into()]), rpc_json(&cfg));
        assert!(!all.contains("api-key=") && !all.contains("${"), "{all}");
        let sp = send_paths_json(&cfg, &["jito-bundle".into()]);
        assert_eq!(sp.as_array().unwrap().len(), 1, "enabled paths only");
        assert_eq!((sp[0]["id"].as_u64(), sp[0]["name"].as_str()), (Some(0), Some("jito-bundle")));
        // feed ids: the index among the enabled feeds
        let f = feeds_json(&cfg);
        let ids: Vec<Option<u64>> = f.as_array().unwrap().iter().map(|x| x["id"].as_u64()).collect();
        let enabled = cfg.feeds.iter().filter(|x| x.enabled).count();
        assert_eq!(ids.iter().flatten().copied().collect::<Vec<_>>(), (0..enabled as u64).collect::<Vec<_>>());
    }

    #[test]
    fn chrony_csv() {
        let v = parse_chrony_csv("A9FEA97B,169.254.169.123,4,1759571234.5,-0.000001234,0.000002,0.00003,-12.5,0.001,0.02,0.0004,0.0002,64.2,Normal\n").unwrap();
        assert_eq!((v["stratum"].as_u64(), v["system_time_s"].as_f64(), v["leap"].as_str()), (Some(4), Some(-0.000001234), Some("Normal")));
        assert!(parse_chrony_csv("506 Cannot talk to daemon").is_none());
        let c = clock_json();
        assert_eq!(c["source"], "CLOCK_REALTIME");
        assert!(c["adjtimex"].is_object(), "the kernel always answers: {c}");
    }
}
