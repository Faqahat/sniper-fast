//! PLAN WP-09, through the real binary: `arbx replay` and `arbx quote` on a run directory made the way `arbx run` makes
//! one (a recorder, the boot snapshot in accounts.bin and the journal, engine_init, pools.json, the frozen config, then
//! journaled inputs and timers), with two synthetic Raydium AMM v4 pools (the real layouts are the scenario tests' own,
//! src/scenarios/).
//! - `replay --compare`: exit 0, replay.json and replay-diff.json written, every decision identical, the run's digests
//!   reproduced;
//! - `replay --set ... --compare` (what-if): exit 1, the differences in replay-diff.json;
//! - `replay --reprice-sizes 0.5,opt`: reprice.jsonl;
//! - a recording that is not whole (its recorder dropped decisions): exit 1, `NOT WHOLE`;
//! - `quote` (one question, and `--batch`): the route's price at the trade's post-state, exit 0;
//! - a recording made before WP-03 (no journal): refused, exit 2, with the reason; an `--out` that exists: refused.
//!
//! The binary is copied first and the copy is run (review WP-09 §8: a target directory shared with another lane can
//! swap `CARGO_BIN_EXE_arbx` between the build and the test).
use arbx::engine::{self, Engine, EngineInit, EngineKnobs};
use arbx::feeds::{src, Event, InputKind};
use arbx::pools::{pair_key, Registry, CLOCK_SYSVAR};
use arbx::rec::accounts::{AcctRec, AcctUpdate, Roles};
use arbx::rec::journal::Journal;
use arbx::store::{Acct, Store};
use arbx::venues::{PoolMeta, Venue, WSOL};
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::Arc;

const BIN: &str = env!("CARGO_BIN_EXE_arbx");
const MINT: [u8; 32] = [7; 32];
const T0: u64 = 1_791_000_000_000_000_000;
const MS: u64 = 1_000_000;
const SOL: u64 = 1_000_000_000;

fn tmp(name: &str) -> PathBuf {
    let t = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    std::env::temp_dir().join(format!("arbx-replay-cli-{name}-{}-{t}", std::process::id()))
}

fn ammv4_pool() -> Vec<u8> { let mut p = vec![0u8; 752]; p[0..8].copy_from_slice(&1u64.to_le_bytes()); p[176..184].copy_from_slice(&25u64.to_le_bytes()); p[184..192].copy_from_slice(&10_000u64.to_le_bytes()); p }
fn vault(amount: u64) -> Vec<u8> { let mut v = vec![0u8; 165]; v[64..72].copy_from_slice(&amount.to_le_bytes()); v }
fn clock(slot: u64) -> Vec<u8> { let mut d = vec![0u8; 40]; d[0..8].copy_from_slice(&slot.to_le_bytes()); d[32..40].copy_from_slice(&1_791_000_000i64.to_le_bytes()); d }
fn meta(n: u8) -> PoolMeta {
    PoolMeta { venue: Venue::RayAmmV4, pool: [n; 32], t0: MINT, t1: *WSOL, vault0: [n + 10; 32], vault1: [n + 20; 32], t0_prog: *arbx::pda::TOKEN_PROGRAM,
        t1_prog: *arbx::pda::TOKEN_PROGRAM, extra: vec![], flag: false }
}

/// A recorded run: two AMM v4 pools, the boot snapshot, a trade on pool 1 (a 3% gap: an opportunity), its timers
fn record(dir: &Path) -> [u8; 64] {
    let cfg_text = std::fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join("deploy/arbx-stage0.toml")).unwrap();
    let cfg = arbx::config::Config::parse(&cfg_text).unwrap();
    std::fs::create_dir_all(dir).unwrap();
    std::fs::write(dir.join("config.toml"), &cfg_text).unwrap();
    let (a, b) = (meta(1), meta(2));
    let mut reg = Registry { pools: vec![a.clone(), b.clone()], by_pool: Default::default(), pairs: Default::default(), seeds: Default::default(), ours: Default::default() };
    reg.by_pool.insert(a.pool, 0);
    reg.by_pool.insert(b.pool, 1);
    reg.pairs.insert(pair_key(&MINT, &WSOL), vec![0, 1]);
    let rec = arbx::rec::start(arbx::rec::Opts { dir: dir.to_path_buf(), run: "cli".into(), producer: "test".into(), cfg: Default::default(), feeds: vec![], monitor: false,
        echo: Some(Box::new(std::io::sink())) }).unwrap();
    let extra = reg.extra_watch(true, &[], None);
    let mut roles = reg.watch_roles();
    roles.extend(extra.iter().copied());
    let roles = Arc::new(Roles::new(roles));
    let ar = AcctRec::new(rec.clone(), roles.clone());
    let mut base = reg.static_accounts();
    base.extend(extra.iter().map(|e| e.0));
    let j = Journal::new(rec.clone());
    let mut store = Store::default();
    for k in &base {
        let d: Vec<u8> = if *k == *CLOCK_SYSVAR { clock(10) } else if reg.by_pool.contains_key(k) { ammv4_pool() } else if *k == a.vault1 || *k == b.vault1 { vault(1_000 * SOL) }
            else { vault(1_000_000_000_000_000) };
        let data: Arc<[u8]> = d.into();
        let aseq = ar.record(&AcctUpdate { pubkey: *k, slot: 10, write_version: 0, t_recv: T0, src: src::RPC_BOOT, is_startup: false, txn: None, lamports: 1, owner: [3; 32],
            data: &data, bank_id: None });
        j.account(0, aseq, store.is_stale(k, 10, src::RPC_BOOT, 0, aseq));
        store.apply(*k, Acct::rpc(data, 10, T0, aseq, src::RPC_BOOT).with_lamports(1));
    }
    let reg = Arc::new(reg);
    arbx::replay::write_pools_json(dir, &reg, &base, &roles).unwrap();
    let mut e = Engine::new_offline(reg.clone(), store, cfg.strategy.clone());
    e.set_rec(rec.clone());
    e.set_acct_rec(ar.clone());
    e.set_base_watch(base);
    e.apply_init(&EngineInit { min_tip: 1_000, strategy_sha256: engine::strategy_sha256(&cfg.strategy), knobs: Some(EngineKnobs::from_cfg(&cfg)), ..Default::default() }).unwrap();
    e.journal().input(0, InputKind::EngineInit, Arc::new(e.init().json()));
    let mut st = |_: &str| {};
    let mut wv = 100;
    let mut write = |e: &mut Engine, k: [u8; 32], d: Vec<u8>, slot: u64, txn: Option<[u8; 64]>, t: u64| {
        wv += 1;
        let data: Arc<[u8]> = d.into();
        let aseq = ar.record(&AcctUpdate { pubkey: k, slot, write_version: wv, t_recv: t, src: src::GRPC, is_startup: false, txn, lamports: 1, owner: [3; 32], data: &data, bank_id: None });
        e.step(Event::Account { slot, pubkey: k, owner: [3; 32], lamports: 1, data, t, txn, write_version: wv, is_startup: false, src: src::GRPC, aseq, bank_id: None }, t + 10_000, &mut |_| {});
    };
    e.step(Event::Slot { slot: 11, status: 0, t: T0 + MS, parent: Some(10), dead_error: None, bank_id: None }, T0 + MS, &mut st);
    write(&mut e, *CLOCK_SYSVAR, clock(11), 11, None, T0 + 2 * MS);
    e.timers(T0 + 8 * MS, &mut st);
    // the trade: pool 1 gains 3% SOL (its MINT gets dearer): a gap against pool 2
    let txn = [0x99u8; 64];
    write(&mut e, a.vault1, vault(1_030 * SOL), 11, Some(txn), T0 + 20 * MS);
    write(&mut e, a.vault0, vault(990_000_000_000_000), 11, Some(txn), T0 + 20 * MS + 100_000);
    e.timers(T0 + 25 * MS, &mut st);
    e.finish();
    rec.close();
    txn
}

/// the binary under test, copied once (its sha256 checked against the build's)
fn bin() -> &'static Path {
    static B: std::sync::OnceLock<PathBuf> = std::sync::OnceLock::new();
    B.get_or_init(|| {
        let p = tmp("bin");
        std::fs::create_dir_all(&p).unwrap();
        let dst = p.join("arbx");
        std::fs::copy(BIN, &dst).unwrap();
        assert_eq!(std::fs::read(BIN).unwrap(), std::fs::read(&dst).unwrap(), "the copy is the build's binary");
        dst
    })
}

fn run(args: &[&str]) -> (i32, String, String) {
    let o = Command::new(bin()).args(args).output().unwrap();
    (o.status.code().unwrap(), String::from_utf8_lossy(&o.stdout).into_owned(), String::from_utf8_lossy(&o.stderr).into_owned())
}

fn json(p: &Path) -> Value { serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap() }

#[test]
fn replay_and_quote_through_the_binary() {
    let dir = tmp("run");
    let txn = record(&dir);
    let d = dir.to_str().unwrap();
    // the replay with the compare: identical
    let out = dir.join("r1");
    let (code, stdout, stderr) = run(&["replay", "--run", d, "--compare", "--out", out.to_str().unwrap()]);
    assert_eq!(code, 0, "{stdout}{stderr}");
    assert!(stdout.contains("OK"), "{stdout}");
    let s = json(&out.join("replay.json"));
    assert_eq!((s["schema"].as_str(), s["ok"].as_bool(), s["whole"].as_bool()), (Some(arbx::replay::REPLAY_SCHEMA), Some(true), Some(true)));
    assert_eq!((s["digests"]["checked"].as_bool(), s["digests"]["same"].as_bool()), (Some(true), Some(true)), "{}", s["digests"]);
    // pools.json is MEASUREMENT §4.29's list (the toolkit reads it), registry-run.json beside it
    let pools: Value = json(&dir.join("pools.json"));
    assert_eq!(pools.as_array().map(|a| a.len()), Some(2), "{pools}");
    assert_eq!(json(&dir.join("registry-run.json"))["schema"].as_str(), Some(arbx::replay::REGISTRY_RUN_SCHEMA));
    let diff = json(&out.join("replay-diff.json"));
    let c = &diff["summary"];
    assert!(c["compared"].as_u64().unwrap() >= 1 && c["identical"] == c["compared"], "{c}");
    let decisions = arbx::rec::read_jsonl(&dir, "decisions").unwrap();
    let best = decisions.iter().find(|x| x["opp"].is_u64()).expect("the trade opened a gap");
    let r = &best["routes"][best["best"].as_u64().unwrap() as usize];
    // what-if: no route clears this min_profit; the compare reports it, exit 1
    let (code, stdout, _) = run(&["replay", "--run", d, "--compare", "--out", dir.join("r2").to_str().unwrap(), "--set", "strategy.min_profit_lamports=1000000000000"]);
    assert_eq!(code, 1, "{stdout}");
    assert_eq!(json(&dir.join("r2/replay-diff.json"))["summary"]["what_if"], Value::Bool(true));
    // X3: the opportunity re-priced at half its size and at the optimum
    let (code, stdout, _) = run(&["replay", "--run", d, "--out", dir.join("r3").to_str().unwrap(), "--reprice-sizes", "0.5,opt"]);
    assert_eq!(code, 0, "{stdout}");
    let rp = std::fs::read_to_string(dir.join("r3/reprice.jsonl")).unwrap();
    assert_eq!(rp.lines().count(), 2, "{rp}");
    // an --out that exists is refused (exit 2): two replays never share a directory
    let (code, _, stderr) = run(&["replay", "--run", d, "--out", dir.join("r3").to_str().unwrap()]);
    assert_eq!(code, 2, "{stderr}");
    assert!(stderr.contains("already exists"), "{stderr}");
    // a recording that is not whole: its recorder dropped decisions (manifest.json): exit 1, said why
    std::fs::write(dir.join("manifest.json"), r#"{"schema":"arbx.manifest/1.0","final":true,"streams":[{"name":"decisions","dropped_total":2}]}"#).unwrap();
    let (code, stdout, _) = run(&["replay", "--run", d, "--compare", "--out", dir.join("r4").to_str().unwrap()]);
    assert_eq!(code, 1, "{stdout}");
    assert!(stdout.contains("NOT WHOLE: run_recorder_loss"), "{stdout}");
    std::fs::remove_file(dir.join("manifest.json")).unwrap();
    // quote: the best route at the trade's post-state and size: the decision's own price
    let route = format!("{},{},{}", r["buy"].as_str().unwrap(), r["sell"].as_str().unwrap(), r["mint"].as_str().unwrap());
    let size = r["size"].as_u64().unwrap().to_string();
    let sig = bs58::encode(txn).into_string();
    let (code, stdout, stderr) = run(&["quote", "--run", d, "--route", &route, "--version", &sig, "--size", &size]);
    assert_eq!(code, 0, "{stdout}{stderr}");
    let q: Value = serde_json::from_str(&stdout).unwrap();
    assert_eq!((q["ok"].as_bool(), &q["gross"], &q["net"]), (Some(true), &r["gross"], &r["net"]), "{q}");
    let batch = dir.join("batch.jsonl");
    std::fs::write(&batch, format!("{{\"id\":1,\"route\":\"{route}\",\"version\":\"pre:{sig}\",\"size\":{size}}}\n{{\"id\":2,\"route\":\"{route}\",\"version\":\"{sig}\",\"size\":{size}}}\n")).unwrap();
    let (code, stdout, _) = run(&["quote", "--run", d, "--batch", batch.to_str().unwrap()]);
    assert_eq!(code, 0);
    let lines: Vec<Value> = stdout.lines().map(|l| serde_json::from_str(l).unwrap()).collect();
    assert_eq!((lines[0]["id"].as_u64(), lines[1]["id"].as_u64()), (Some(1), Some(2)));
    assert!(lines[0]["gross"].as_i64().unwrap() < 0 && lines[1]["gross"] == r["gross"], "pre-state: no gap; post-state: the gap");
    // a recording made before WP-03: refused with the reason, exit 2
    let old = tmp("v1");
    std::fs::create_dir_all(&old).unwrap();
    std::fs::write(old.join("opportunities.jsonl"), "{}\n").unwrap();
    let (code, _, stderr) = run(&["replay", "--run", old.to_str().unwrap(), "--compare"]);
    assert_eq!(code, 2);
    assert!(stderr.contains("before WP-03"), "{stderr}");
    let (code, _, _) = run(&["quote", "--run", old.to_str().unwrap(), "--route", &route, "--version", &sig, "--size", "1"]);
    assert_eq!(code, 2);
    let _ = std::fs::remove_dir_all(&dir);
    let _ = std::fs::remove_dir_all(&old);
    let _ = std::fs::remove_dir_all(bin().parent().unwrap());
}
