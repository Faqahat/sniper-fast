//! End-to-end: the real shreder_rec binary against the local fake gRPC server (shreder_fake).
//! Checks: dataset records decode with the documented layout, seq is gap-free, idx matches, the pump view holds only
//! pump txs, a server-side stream end triggers a reconnect, the live lead estimate sees the injected lead, token auth
//! works and fails cleanly, and an 'unfiltered not allowed' server triggers the broad-filter fallback.
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

const REC: &str = env!("CARGO_BIN_EXE_shreder_rec");
const FAKE: &str = env!("CARGO_BIN_EXE_shreder_fake");

fn tmpdir(tag: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("shreder_e2e_{}_{}", tag, std::process::id()));
    let _ = std::fs::remove_dir_all(&d);
    std::fs::create_dir_all(&d).unwrap();
    d
}

fn start_fake(args: &[&str]) -> (Child, u16) {
    start_fake_err(args, None)
}

fn start_fake_err(args: &[&str], err: Option<&Path>) -> (Child, u16) {
    let se = match err {
        Some(p) => Stdio::from(std::fs::File::create(p).unwrap()),
        None => Stdio::null(),
    };
    let mut c = Command::new(FAKE).args(args).stdout(Stdio::piped()).stderr(se).spawn().unwrap();
    let mut out = c.stdout.take().unwrap();
    let mut buf = Vec::new();
    let t0 = Instant::now();
    let mut b = [0u8; 1];
    while t0.elapsed() < Duration::from_secs(10) {
        if out.read(&mut b).unwrap_or(0) == 1 {
            if b[0] == b'\n' {
                break;
            }
            buf.push(b[0]);
        }
    }
    let s = String::from_utf8(buf).unwrap();
    let port: u16 = s.trim().strip_prefix("PORT ").expect("PORT line").parse().unwrap();
    (c, port)
}

fn run_rec(port: u16, out: &Path, extra: &[&str], secs: f64) -> std::process::ExitStatus {
    let ep = format!("http://127.0.0.1:{port}");
    let mins = format!("{}", secs / 60.0);
    let mut args = vec!["--endpoint", ep.as_str(), "--out", out.to_str().unwrap(), "--minutes", mins.as_str(), "--status-secs", "2", "--quiet"];
    args.extend_from_slice(extra);
    let mut c = Command::new(REC).args(&args).stdout(Stdio::null()).stderr(Stdio::inherit()).spawn().unwrap();
    let t0 = Instant::now();
    loop {
        if let Some(s) = c.try_wait().unwrap() {
            return s;
        }
        if t0.elapsed() > Duration::from_secs_f64(secs + 20.0) {
            let _ = c.kill();
            panic!("recorder did not stop by itself");
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}

struct Rec {
    seq: u64,
    rx: i64,
    ca: i64,
    slot: u64,
    flags: u8,
    tx: Vec<u8>,
}

fn read_dataset(dir: &Path, stream: &str) -> (Vec<Rec>, u64) {
    let mut files: Vec<PathBuf> = std::fs::read_dir(dir)
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|p| {
            let n = p.file_name().unwrap().to_str().unwrap();
            n.starts_with(&format!("{stream}_")) && n.ends_with(".rec.gz")
        })
        .collect();
    files.sort();
    let mut out = Vec::new();
    let mut idx_n = 0u64;
    for f in files {
        let mut raw = Vec::new();
        flate2::read::MultiGzDecoder::new(std::fs::File::open(&f).unwrap()).read_to_end(&mut raw).unwrap();
        let mut off = 0;
        while off + 44 <= raw.len() {
            let rl = u32::from_le_bytes(raw[off..off + 4].try_into().unwrap()) as usize;
            let b = &raw[off + 4..off + 4 + rl];
            let txl = u32::from_le_bytes(b[36..40].try_into().unwrap()) as usize;
            assert_eq!(rl, 40 + txl);
            out.push(Rec {
                seq: u64::from_le_bytes(b[0..8].try_into().unwrap()),
                rx: i64::from_le_bytes(b[8..16].try_into().unwrap()),
                ca: i64::from_le_bytes(b[16..24].try_into().unwrap()),
                slot: u64::from_le_bytes(b[24..32].try_into().unwrap()),
                flags: b[32],
                tx: b[40..40 + txl].to_vec(),
            });
            off += 4 + rl;
        }
        assert_eq!(off, raw.len(), "no trailing garbage");
        let idx = f.to_str().unwrap().replace(".rec.gz", ".idx.jsonl");
        for l in std::fs::read_to_string(idx).unwrap().lines() {
            let v: serde_json::Value = serde_json::from_str(l).unwrap();
            idx_n += v["n"].as_u64().unwrap();
        }
    }
    (out, idx_n)
}

fn read_view(dir: &Path, stream: &str) -> Vec<serde_json::Value> {
    let mut v = Vec::new();
    for e in std::fs::read_dir(dir).unwrap() {
        let p = e.unwrap().path();
        let n = p.file_name().unwrap().to_str().unwrap().to_string();
        if n.starts_with(&format!("{stream}_")) && n.ends_with(".jsonl") && !n.ends_with(".idx.jsonl") {
            for l in std::fs::read_to_string(&p).unwrap().lines() {
                v.push(serde_json::from_str(l).unwrap());
            }
        }
    }
    v
}

fn events(dir: &Path) -> Vec<serde_json::Value> {
    std::fs::read_to_string(dir.join("events.jsonl")).unwrap().lines().map(|l| serde_json::from_str(l).unwrap()).collect()
}

#[test]
fn e2e_unfiltered_pre_bin_reconnect_and_lead() {
    let (mut fake, port) = start_fake(&["--rate", "3000", "--lead-ms", "5", "--pre-share", "0.5", "--pump-share", "0.2", "--drop-after", "4000", "--secs", "40"]);
    let d = tmpdir("main");
    let st = run_rec(port, &d, &[], 8.0);
    let _ = fake.kill();
    assert!(st.success());
    for stream in ["pre", "bin"] {
        let (recs, idx_n) = read_dataset(&d, stream);
        assert!(recs.len() > 1000, "{stream}: only {} records", recs.len());
        assert_eq!(idx_n, recs.len() as u64, "{stream}: idx counts match");
        for (i, r) in recs.iter().enumerate() {
            assert_eq!(r.seq, i as u64 + 1, "{stream}: seq gap-free");
            assert!(r.ca > 0 && r.slot >= 400_000_000);
            assert_eq!(r.flags & 1 == 1, stream == "pre", "preconf flag");
            assert!(shreder_rec::txparse::parse_tx(&r.tx).is_some());
        }
        let mono = recs.windows(2).filter(|w| w[1].rx >= w[0].rx).count();
        assert!(mono as f64 >= 0.999 * (recs.len() - 1) as f64, "rx stamps monotonic");
        let view = read_view(&d, stream);
        assert!(!view.is_empty());
        let n_pump_ds = recs
            .iter()
            .filter(|r| {
                let p = shreder_rec::txparse::parse_tx(&r.tx).unwrap();
                let pump = shreder_rec::txparse::decode_pubkey(shreder_rec::txparse::PUMP_PROGRAM).unwrap();
                p.keys.iter().any(|k| *k == &pump[..])
            })
            .count();
        assert_eq!(view.len(), n_pump_ds, "{stream}: view = pump subset of dataset");
        for v in &view {
            assert_eq!(v["p"][0][0], "bq3");
            assert!(v["sig"].as_str().unwrap().len() > 80);
            assert!(v["t"].as_i64().unwrap() > 0);
        }
        eprintln!("{stream}: {} records, {} in pump view", recs.len(), view.len());
    }
    let ev = events(&d);
    let ends = ev.iter().filter(|e| e["ev"] == "stream_end").count();
    assert!(ends >= 2, "server-side stream end seen on both streams (got {ends})");
    let subs = ev.iter().filter(|e| e["ev"] == "subscribed").count();
    assert!(subs >= 4, "re-subscribed after the stream end (got {subs})");
    let leads: Vec<f64> = ev.iter().filter(|e| e["ev"] == "lead").map(|e| e["p50_ms"].as_f64().unwrap()).collect();
    assert!(!leads.is_empty(), "lead estimates present");
    let mut l = leads.clone();
    l.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let med = l[l.len() / 2];
    eprintln!("lead p50 per interval: {leads:?}");
    assert!((3.0..15.0).contains(&med), "injected 5 ms lead, measured median {med}");
    let _ = std::fs::remove_dir_all(&d);
}

#[test]
fn e2e_token_auth() {
    let (mut fake, port) = start_fake(&["--rate", "500", "--token", "s3cr3t-token", "--secs", "30"]);
    let d1 = tmpdir("tok_ok");
    std::fs::write(d1.join("key"), "token = s3cr3t-token\n").unwrap();
    let key = d1.join("key");
    let st = run_rec(port, &d1, &["--key", key.to_str().unwrap(), "--stream", "bin:bin:pump"], 4.0);
    assert!(st.success());
    let (recs, _) = read_dataset(&d1, "bin");
    assert!(recs.len() > 50, "token accepted: {} records", recs.len());
    let log = std::fs::read_to_string(d1.join("rec.log")).unwrap() + &std::fs::read_to_string(d1.join("events.jsonl")).unwrap();
    assert!(!log.contains("s3cr3t-token"), "token never logged");
    assert!(!log.contains("127.0.0.1"), "endpoint never logged");
    let d2 = tmpdir("tok_bad");
    let st = run_rec(port, &d2, &["--stream", "bin:bin:pump"], 3.0);
    let _ = fake.kill();
    assert!(st.success());
    let ev = events(&d2);
    assert!(ev.iter().any(|e| e["ev"] == "error" && e["msg"].as_str().unwrap().contains("PermissionDenied")));
    assert!(read_dataset(&d2, "bin").0.is_empty());
    let _ = std::fs::remove_dir_all(&d1);
    let _ = std::fs::remove_dir_all(&d2);
}

#[test]
fn e2e_unfiltered_rejected_falls_back_to_broad() {
    let (mut fake, port) = start_fake(&["--rate", "1000", "--reject-unfiltered", "--secs", "30"]);
    let d = tmpdir("fallback");
    let st = run_rec(port, &d, &["--stream", "bin:bin:all"], 5.0);
    let _ = fake.kill();
    assert!(st.success());
    let ev = events(&d);
    assert!(ev.iter().any(|e| e["ev"] == "filter_fallback"), "fallback event");
    let (recs, _) = read_dataset(&d, "bin");
    assert!(recs.len() > 20, "data after fallback: {}", recs.len());
    let _ = std::fs::remove_dir_all(&d);
}

#[test]
fn e2e_both_sources_on_one_connection_when_server_allows_only_one() {
    // server allows ONE active subscription: the default two-connection mode loses one stream (clean ResourceExhausted
    // errors, retried), while NAME:both records both sources over one connection into the usual pre/bin files.
    let (mut fake, port) = start_fake(&["--rate", "2000", "--max-conns", "1", "--lead-ms", "5", "--secs", "40"]);
    let d1 = tmpdir("both_default");
    assert!(run_rec(port, &d1, &[], 4.0).success());
    let ev = events(&d1);
    assert!(ev.iter().any(|e| e["ev"] == "error" && e["msg"].as_str().unwrap().contains("ResourceExhausted")), "limit hit in two-connection mode");
    std::thread::sleep(Duration::from_millis(500));
    let d2 = tmpdir("both_mode");
    assert!(run_rec(port, &d2, &["--stream", "mix:both:all"], 6.0).success());
    let _ = fake.kill();
    let ev2 = events(&d2);
    // a both-connection reports its events under both output names: count the pre copies only
    let errs: Vec<String> = ev2.iter().filter(|e| e["ev"] == "error" && e["st"] == "pre").map(|e| e["msg"].as_str().unwrap().to_string()).collect();
    assert!(ev2.iter().any(|e| e["ev"] == "subscribed" && e["st"] == "bin") && ev2.iter().any(|e| e["ev"] == "subscribed" && e["st"] == "pre"));
    eprintln!("both-mode errors: {errs:?}");
    // the first run's subscription may still count as active for a moment on the fake: allow one early retry
    assert!(errs.len() <= 1, "at most one transient error in both mode: {errs:?}");
    let (pre, _) = read_dataset(&d2, "pre");
    let (bin, _) = read_dataset(&d2, "bin");
    assert!(pre.len() > 500 && bin.len() > 1000, "pre {} bin {}", pre.len(), bin.len());
    assert!(pre.iter().all(|r| r.flags & 1 == 1) && bin.iter().all(|r| r.flags & 1 == 0), "routed by update.preconf");
    for (i, r) in pre.iter().enumerate() {
        assert_eq!(r.seq, i as u64 + 1);
    }
    let leads: Vec<f64> = ev2.iter().filter(|e| e["ev"] == "lead").map(|e| e["p50_ms"].as_f64().unwrap()).collect();
    assert!(!leads.is_empty() && leads.iter().all(|&l| (3.0..15.0).contains(&l)), "lead {leads:?}");
    let _ = std::fs::remove_dir_all(&d1);
    let _ = std::fs::remove_dir_all(&d2);
}

#[test]
fn e2e_exclude_votes_only_on_binary() {
    let d = tmpdir("excl");
    let errp = d.join("fake.err");
    let (mut fake, port) = start_fake_err(&["--rate", "500", "--secs", "20"], Some(&errp));
    assert!(run_rec(port, &d, &["--exclude-votes"], 2.5).success());
    std::thread::sleep(Duration::from_millis(300));
    let _ = fake.kill();
    let txt = std::fs::read_to_string(&errp).unwrap();
    assert!(txt.contains("FILTER name=bin preconf=false include= exclude=Vote111111111111111111111111111111111111111"), "{txt}");
    assert!(txt.contains("FILTER name=pre preconf=true include= exclude="), "{txt}");
    assert!(!txt.contains("preconf=true include= exclude=Vote"), "no exclude on preconf");
    let _ = std::fs::remove_dir_all(&d);
}
