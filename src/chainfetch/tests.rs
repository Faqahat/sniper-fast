//! Chain-fetch tests (PLAN WP-03b offline acceptance). A fake chain serves the recorded replies of `testdata/rpc/` and
//! the wallet transactions of `testdata/wallet/` (real `getTransaction` replies), with a simulated latency; the service
//! runs on tokio's paused clock, so minutes of simulated time take a moment and every rate is exact.
use super::*;
use crate::feeds::grpc::PbTransaction;
use crate::rec::accounts::{RoleOf, NO_POOL};
use base64::Engine as _;
use std::path::{Path, PathBuf};

const WALLET: &str = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE";
const ROUTE: &str = "8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg";
const B64: base64::engine::GeneralPurpose = base64::engine::general_purpose::STANDARD;

fn repo(rel: &str) -> PathBuf { Path::new(env!("CARGO_MANIFEST_DIR")).join(rel) }
fn json_file(p: &Path) -> Value { serde_json::from_slice(&std::fs::read(p).unwrap()).unwrap() }
fn pk(s: &str) -> Pk { crate::tx::pk(s) }
fn sig64(s: &str) -> [u8; 64] { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }
fn sig_of(n: u32) -> [u8; 64] { let mut s = [9u8; 64]; s[..4].copy_from_slice(&n.to_le_bytes()); s }

/// a recorded reply's `result`, or its JSON-RPC error as the failure the client would return
fn reply(v: &Value) -> Result<Value, RpcFailure> {
    if let Some(e) = v.get("error") {
        let mut f = RpcFailure::new(ErrClass::Rpc, Some("fake"), format!("fake: {e}"));
        f.code = e["code"].as_i64();
        f.retryable = !crate::rpc::code_is_answer(f.code);
        return Err(f);
    }
    Ok(v["result"].clone())
}
fn fixture(name: &str) -> Value { json_file(&repo("testdata/rpc").join(name)) }
fn wallet_tx(sig: &str) -> Option<Value> { let p = repo("testdata/wallet").join(format!("{sig}.json")); p.exists().then(|| json_file(&p)) }

/// A wallet fixture as the `getTransaction` reply of another signature (its first signature replaced), with its
/// `transactionIndex` as given (None: the provider did not send one)
fn tx_as(sig: &[u8; 64], index: Option<u64>) -> Value {
    let mut v = wallet_tx("1WUBGeUhRymCbU8yyVqvxmbSkWEaNJwd3A98kxyAuyj2PjeN6VfcgAdJvyWxqX2fTQ4iX98UW6NocREXsNKq7q9").unwrap();
    let mut raw = B64.decode(v["transaction"][0].as_str().unwrap()).unwrap();
    assert_eq!(raw[0], 1, "one signature");
    raw[1..65].copy_from_slice(sig);
    v["transaction"][0] = json!(B64.encode(&raw));
    v["transactionIndex"] = json!(index);
    v
}

type Handler = Box<dyn Fn(Role, &str, &Value) -> Option<Result<Value, RpcFailure>> + Send + Sync>;

/// The fake chain: `extra` first, then the recorded replies; every call logged with its (paused-clock) time
struct FakeChain { calls: Mutex<Vec<(Role, String, Value, u64)>>, extra: Handler, latency: Duration, base: tokio::time::Instant }

impl FakeChain {
    fn new(extra: Handler) -> Arc<FakeChain> {
        Arc::new(FakeChain { calls: Mutex::new(Vec::new()), extra, latency: Duration::from_millis(50), base: tokio::time::Instant::now() })
    }
    fn calls(&self, method: &str) -> Vec<(Role, Value, u64)> {
        self.calls.lock().unwrap().iter().filter(|c| c.1 == method).map(|c| (c.0, c.2.clone(), c.3)).collect()
    }
    /// the recorded replies of testdata/rpc and testdata/wallet
    fn recorded(method: &str, p: &Value) -> Result<Value, RpcFailure> {
        match method {
            "getTransaction" => Ok(p[0].as_str().and_then(wallet_tx).unwrap_or(Value::Null)),
            "getBlock" => match (p[0].as_u64(), p[1]["transactionDetails"].as_str()) {
                (Some(453_032_285), Some("signatures")) => reply(&fixture("getBlock-453032285-signatures.json")),
                (Some(453_032_285), Some("full")) => reply(&fixture("getBlock-453032285-full-first30.json")),
                (Some(453_034_309), _) => reply(&fixture("getBlock-453034309-skipped.json")),
                (Some(453_034_312), _) => reply(&fixture("getBlock-453034312-signatures-first40.json")),
                (s, _) => { let mut f = RpcFailure::new(ErrClass::Rpc, Some("fake"), format!("Block not available for slot {s:?}")); f.code = Some(-32004); f.retryable = false; Err(f) }
            },
            "getSignaturesForAddress" => reply(&fixture("getSignaturesForAddress-2g7rYv7y-before-4RT9wv.json")),
            "getLatestBlockhash" => reply(&fixture("getLatestBlockhash.json")),
            m => Err(RpcFailure::new(ErrClass::Rpc, Some("fake"), format!("{m}: not recorded"))),
        }
    }
}

impl Chain for FakeChain {
    fn call(&self, role: Role, method: &'static str, params: Value, _b: Bounds) -> BoxFut {
        self.calls.lock().unwrap().push((role, method.to_string(), params.clone(), self.base.elapsed().as_nanos() as u64));
        let r = (self.extra)(role, method, &params).unwrap_or_else(|| FakeChain::recorded(method, &params));
        let lat = self.latency;
        Box::pin(async move {
            tokio::time::sleep(lat).await;
            r.map(|value| Fetched { value, provider: "fake".into(), latency_ms: lat.as_secs_f64() * 1e3, bytes: 2_000, attempts: 1 })
        })
    }
}

fn no_extra() -> Handler { Box::new(|_, _, _| None) }

fn rec_in(tag: &str) -> (Rec, PathBuf) {
    let dir = std::env::temp_dir().join(format!("arbx-cf-{tag}-{}-{}", std::process::id(), now_ns()));
    let rec = crate::rec::start(crate::rec::Opts { dir: dir.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![], monitor: false,
        echo: Some(Box::new(std::io::sink())) }).unwrap();
    (rec, dir)
}

fn quiet_cfg() -> ChainfetchCfg {
    ChainfetchCfg { blockhash_poll_ms: 0, sample_every_s: 0, sigs_every_s: 0, ..ChainfetchCfg::default() }
}

struct Run { shared: Arc<Shared>, stop: Arc<AtomicBool>, h: tokio::task::JoinHandle<()>, back: crossbeam_channel::Receiver<Event> }

fn run(cfg: ChainfetchCfg, roles: Arc<Roles>, rec: Rec, chain: Arc<dyn Chain>, cap: f64) -> Run { run_reg(cfg, roles, rec, chain, cap, Arc::new(Registry::default())) }

fn run_reg(cfg: ChainfetchCfg, roles: Arc<Roles>, rec: Rec, chain: Arc<dyn Chain>, cap: f64, reg: Arc<Registry>) -> Run {
    let (shared, rx) = Shared::new(reg);
    let (btx, back) = crossbeam_channel::unbounded();
    let svc = Service::new(Opts { cfg, wallet: Some(pk(WALLET)), route_program: pk(ROUTE), roles, rec, back: Some(btx), chain, backfill_cap: cap }, shared.clone());
    let stop = Arc::new(AtomicBool::new(false));
    let h = tokio::spawn(svc.run(rx, stop.clone()));
    Run { shared, stop, h, back }
}

impl Run {
    async fn end(self) -> (Arc<Shared>, Vec<(InputKind, Value)>) {
        self.stop.store(true, Relaxed);
        self.h.await.unwrap();
        let inputs = self.back.try_iter().filter_map(|e| match e { Event::Input { kind, data } => Some((kind, (*data).clone())), _ => None }).collect();
        (self.shared, inputs)
    }
}

fn acct(pubkey: Pk, slot: u64, txn: [u8; 64]) -> Note { Note::Account { pubkey, slot, txn, t: now_ns() } }
fn role_of(role: u8, pool_index: u32) -> RoleOf { RoleOf { role, pool_index } }

// ---------------------------------------------------------------- conversion

/// Every RPC transaction converts to the same record the transaction stream writes: the 147 wallet fixtures (legacy,
/// v0; `getTransaction`) and the first 30 transactions of slot 453,032,285 (`getBlock` "full", legacy, v0 and v1),
/// whose signatures (v1: at the end of the wire) sit at their positions in the slot's signature list
#[test]
fn rpc_transactions_convert_like_the_stream() {
    let mut n = 0;
    for f in std::fs::read_dir(repo("testdata/wallet")).unwrap().flatten() {
        let p = f.path();
        if p.extension().and_then(|e| e.to_str()) != Some("json") { continue; }
        let v = json_file(&p);
        let x = txjson::from_rpc(&v).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        let stem = p.file_stem().unwrap().to_str().unwrap();
        assert_eq!(b58s(&x.sig), stem);
        let m = &v["meta"];
        assert_eq!(x.keys.len(), m["preBalances"].as_array().unwrap().len(), "{stem}: static + loaded keys");
        assert_eq!((x.slot, x.idx), (v["slot"].as_u64(), v["transactionIndex"].as_u64()));
        let raw = B64.decode(v["transaction"][0].as_str().unwrap()).unwrap();
        assert_eq!(txjson::wire_sig(&raw), Some(x.sig));
        let r = crate::rec::exec::exec_json(&x.sig, 1, x.idx, 1, "rpc-wallet", &["sigs_for_address"], &x.tx, x.meta.as_ref().unwrap(), None);
        assert_eq!(r["fee"], m["fee"]);
        assert_eq!(r["cu"], m["computeUnitsConsumed"]);
        assert_eq!(r["logs"].as_array().unwrap().len(), m["logMessages"].as_array().unwrap().len());
        assert_eq!(r["inner"].as_array().unwrap().iter().map(|g| g["list"].as_array().unwrap().len()).sum::<usize>(),
            m["innerInstructions"].as_array().unwrap().iter().map(|g| g["instructions"].as_array().unwrap().len()).sum::<usize>());
        assert_eq!(r["version"].as_str(), Some(if v["version"] == "legacy" { "legacy" } else { "0" }));
        assert_eq!(r["ok"].as_bool(), Some(m["err"].is_null()));
        assert_eq!(r["keys"].as_array().unwrap().len(), x.keys.len());
        n += 1;
    }
    assert_eq!(n, 147);
    // failures read as the stream's do (bincode TransactionError)
    let s = json_file(&repo("testdata/legacy/signatures.json"));
    let case = |id: &str| s["cases"].as_array().unwrap().iter().find(|c| c["id"] == id).unwrap()["sig"].as_str().unwrap().to_string();
    let err = |id: &str| { let x = txjson::from_rpc(&wallet_tx(&case(id)).unwrap()).unwrap();
        crate::rec::exec::exec_json(&x.sig, 1, None, 1, "x", &[], &x.tx, x.meta.as_ref().unwrap(), None) };
    let e = err("landed_fail_compete_bid");
    assert_eq!((e["err"].as_str(), e["err_ix"].as_u64()), (Some("ix4:custom:0x4e580002"), Some(4)));
    assert_eq!(err("landed_fail_venue_error")["err"].as_str(), Some("ix4:custom:0x1794"));
    assert_eq!(err("foreign_failed")["err"].as_str(), Some("tx31"), "InsufficientFundsForRent");
    assert_eq!(txjson::encode_tx_error(&json!("BlockhashNotFound")), 7u32.to_le_bytes().to_vec());
    assert_eq!(crate::rec::tx_error(&txjson::encode_tx_error(&json!({ "InstructionError": [2, "InvalidAccountData"] }))), "ix2:ie3");
    assert_eq!(crate::rec::tx_error(&txjson::encode_tx_error(&json!({ "InstructionError": [0, { "BorshIoError": "x" }] }))), "ix0:ie44");
    assert_eq!(crate::rec::tx_error(&txjson::encode_tx_error(&json!({ "Unheard": 1 }))), "?");
    // the full block: legacy, v0 and v1, every one at its position in the slot's signature list
    let full = fixture("getBlock-453032285-full-first30.json");
    let sigs = fixture("getBlock-453032285-signatures.json");
    let list = sigs["result"]["signatures"].as_array().unwrap();
    let mut v1 = 0;
    for (i, t) in full["result"]["transactions"].as_array().unwrap().iter().enumerate() {
        let x = txjson::from_rpc(t).unwrap();
        assert_eq!(list[i].as_str(), Some(b58s(&x.sig).as_str()), "position {i}");
        assert_eq!(x.keys.len(), t["meta"]["preBalances"].as_array().unwrap().len(), "{i}");
        let r = crate::rec::exec::exec_json(&x.sig, 453_032_285, Some(i as u64), 1, "rpc-block-sample", &[], &x.tx, x.meta.as_ref().unwrap(), None);
        assert_eq!(r["fee"], t["meta"]["fee"]);
        if t["version"] == 1 {
            v1 += 1;
            assert!(x.is_v1());
            assert_eq!(r["version"].as_str(), Some("1"));
            let raw = B64.decode(t["transaction"][0].as_str().unwrap()).unwrap();
            assert_eq!(txjson::wire_sig(&raw), Some(x.sig), "a v1 transaction's signatures come last");
        }
    }
    assert!(v1 >= 2, "{v1}");
}

/// wallet.jsonl's own fields against the known answers of the legacy cases (testdata/legacy/signatures.json `chain`):
/// the kind, the wallet's lamport and WSOL changes, and the accounts created (lamports; owner and space from the
/// System create)
#[test]
fn wallet_fields_match_the_known_cases() {
    let s = json_file(&repo("testdata/legacy/signatures.json"));
    let (wallet, route) = (pk(WALLET), pk(ROUTE));
    let wsol = crate::build::ata_of(&wallet, &crate::venues::WSOL, &crate::pda::TOKEN_PROGRAM);
    assert_eq!(b58(&wsol), s["wsol_account"].as_str().unwrap());
    for c in s["cases"].as_array().unwrap() {
        let id = c["id"].as_str().unwrap();
        let x = txjson::from_rpc(&wallet_tx(c["sig"].as_str().unwrap()).unwrap()).unwrap();
        let f = wallet::fields(&x, &wallet, &wsol, &route);
        let ch = &c["chain"];
        assert_eq!(f.wallet_kind, c["kind"].as_str().unwrap(), "{id}");
        assert_eq!(f.wallet_sol, ch["wallet_sol"].as_i64(), "{id}");
        let wsol_change = f.wallet_tok.get("So11111111111111111111111111111111111111112").and_then(|v| v.as_str()).map(|v| v.parse::<i64>().unwrap()).unwrap_or(0);
        assert_eq!(wsol_change, ch["wsol"].as_i64().unwrap(), "{id}");
        let want: Vec<(String, u64)> = ch["created"].as_array().unwrap().iter().map(|a| (a["account"].as_str().unwrap().to_string(), a["lamports"].as_u64().unwrap())).collect();
        let got: Vec<(String, u64)> = f.created.iter().map(|a| (a["acct"].as_str().unwrap().to_string(), a["lamports"].as_u64().unwrap())).collect();
        let (mut w, mut g) = (want.clone(), got.clone());
        w.sort();
        g.sort();
        assert_eq!(g, w, "{id}");
        for a in &f.created {
            let space = a["space"].as_u64();
            match a["owner"].as_str() {
                Some("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA") => assert_eq!(space, Some(165), "{id}"),
                Some("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb") => assert_eq!(space, Some(170), "{id}"),
                Some("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA") => assert_eq!(space, Some(137), "{id}: the user volume accumulator"),
                Some("11111111111111111111111111111111") => assert_eq!(space, Some(80), "{id}: a nonce account"),
                o => panic!("{id}: created account owner {o:?}"),
            }
        }
        assert!(f.closed.is_empty(), "{id}");
    }
}

// ---------------------------------------------------------------- wallet discovery

/// PLAN WP-03b acceptance: wallet discovery from synthetic wallet updates and from a getSignaturesForAddress page, with
/// deduplication. Two signatures come from the state stream's wallet and WSOL-account updates (one named twice); the
/// hourly page (run 30 s in) lists them and 10 more. Every signature is fetched exactly once; the 10 found only by the
/// page are `wallet_update_missing` a minute later; each record reaches wallet.jsonl (and exec.jsonl: the wallet pays)
/// and the engine (INPUT wallet_tx); the wallet coverage gauge is 100%
#[tokio::test(start_paused = true)]
async fn wallet_discovery_dedups_and_flags_missing_updates() {
    let (rec, dir) = rec_in("wallet");
    let wallet = pk(WALLET);
    let wsol = crate::build::ata_of(&wallet, &crate::venues::WSOL, &crate::pda::TOKEN_PROGRAM);
    let roles = Arc::new(Roles::new([(wallet, role_of(role::WALLET, NO_POOL)), (wsol, role_of(role::WALLET_TOKEN_ACCOUNT, NO_POOL))]));
    let page: Vec<String> = fixture("getSignaturesForAddress-2g7rYv7y-before-4RT9wv.json")["result"].as_array().unwrap().iter()
        .map(|r| r["signature"].as_str().unwrap().to_string()).collect();
    assert_eq!(page.len(), 12);
    let fake = FakeChain::new(no_extra());
    let cfg = ChainfetchCfg { sigs_every_s: 3_600, ..quiet_cfg() };
    let r = run(cfg, roles, rec.clone(), fake.clone(), f64::INFINITY);
    let (a, b) = (sig64(&page[0]), sig64(&page[1]));
    // the stream's first update is older than every page entry: all of them could have had an update in this run
    r.shared.send(acct(wallet, 453_031_900, a));
    r.shared.send(acct(wsol, 453_031_900, a));
    r.shared.send(acct(wallet, 453_031_901, b));
    tokio::time::sleep(Duration::from_secs(5)).await;
    assert_eq!(fake.calls("getTransaction").len(), 2, "A and B, A once");
    tokio::time::sleep(Duration::from_secs(120)).await;
    let (shared, inputs) = r.end().await;
    // each signature fetched exactly once, the page asked once
    let got = fake.calls("getTransaction");
    let mut fetched: Vec<String> = got.iter().map(|c| c.1[0].as_str().unwrap().to_string()).collect();
    fetched.sort();
    let mut want = page.clone();
    want.sort();
    assert_eq!(fetched, want);
    assert!(got.iter().all(|c| c.0 == Role::Wallet && c.1[1]["encoding"] == "base64" && c.1[1]["maxSupportedTransactionVersion"] == 1));
    assert_eq!(fake.calls("getSignaturesForAddress").len(), 1);
    rec.close();
    let w = crate::rec::read_jsonl(&dir, "wallet").unwrap();
    assert_eq!(w.len(), 12);
    let by: HashMap<&str, &Value> = w.iter().map(|r| (r["sig"].as_str().unwrap(), r)).collect();
    assert_eq!(by[page[0].as_str()]["found_by"], json!(["account_update"]));
    assert_eq!(by[page[5].as_str()]["found_by"], json!(["sigs_for_address"]));
    let x = by[page[0].as_str()];
    assert_eq!((x["src"].as_str(), x["wallet_kind"].as_str(), x["slot"].as_u64(), x["idx"].as_u64()), (Some("rpc-wallet"), Some("route"), Some(453_032_285), Some(29)));
    assert_eq!(x["wallet_sol"].as_i64(), x["signer_sol"].as_i64());
    assert!(x["attempt"].is_null() && x["created"] == json!([]));
    let ev = crate::rec::read_jsonl(&dir, "events").unwrap();
    let missing: Vec<&str> = ev.iter().filter(|e| e["kind"] == "wallet_update_missing").map(|e| e["detail"]["sig"].as_str().unwrap()).collect();
    assert_eq!(missing.len(), 10);
    assert!(!missing.contains(&page[0].as_str()) && !missing.contains(&page[1].as_str()));
    // exec.jsonl too: our wallet pays
    let ex = crate::rec::read_jsonl(&dir, "exec").unwrap();
    assert_eq!(ex.iter().filter(|e| e["src"] == "rpc-wallet").count(), 12);
    let txf = crate::rec::read_jsonl(&dir, "txfetch").unwrap();
    assert_eq!(txf.iter().filter(|t| t["method"] == "getTransaction" && t["ok"] == true).count(), 12);
    assert!(txf.iter().any(|t| t["reason"] == "wallet_update") && txf.iter().any(|t| t["reason"] == "sigs_for_address"));
    let wins: Vec<&Value> = inputs.iter().filter(|i| i.0 == InputKind::WalletTx).map(|i| &i.1).collect();
    assert_eq!(wins.len(), 12);
    assert!(wins.iter().all(|i| i["wallet_kind"] == "route" && i["idx"].is_u64()));
    let (cf, cov) = shared.status_json();
    assert_eq!((cov["wallet_with_tx_pct"].as_f64(), cov["wallet_update_missing_delta"].as_u64()), (Some(100.0), Some(10)));
    assert_eq!(cf["wallet_pending_now"].as_u64(), Some(0));
    let _ = std::fs::remove_dir_all(&dir);
}

/// The merge of WP-03b and WP-08 (WP-08 review #13's hand-off): the service's records go through WP-08's derived-field
/// hook as the transaction stream's do. Our Jito-tipped bundle transaction (testdata/wallet 1WUBGeUh..., named by a
/// wallet account update) reaches wallet.jsonl and exec.jsonl with its transfers classified (classify::tests'
/// `a_jito_bundle_of_ours_with_a_pumpswap_creator_fee`: 9 transfers, one top-level `sender_tip` of 7,254 lamports to
/// Jito), `tip_total` and `tip_asked` 7,254, `tip_senders` ["jito"], `jito_tipped`; wallet.jsonl's own fields stay
#[tokio::test(start_paused = true)]
async fn the_services_records_carry_wp08s_derived_fields() {
    let (rec, dir) = rec_in("derive");
    let wallet = pk(WALLET);
    let roles = Arc::new(Roles::new([(wallet, role_of(role::WALLET, NO_POOL))]));
    let fake = FakeChain::new(no_extra());
    let r = run(quiet_cfg(), roles, rec.clone(), fake.clone(), f64::INFINITY);
    let s = "1WUBGeUhRymCbU8yyVqvxmbSkWEaNJwd3A98kxyAuyj2PjeN6VfcgAdJvyWxqX2fTQ4iX98UW6NocREXsNKq7q9";
    let slot = wallet_tx(s).unwrap()["slot"].as_u64().unwrap();
    r.shared.send(acct(wallet, slot, sig64(s)));
    tokio::time::sleep(Duration::from_secs(5)).await;
    let _ = r.end().await;
    assert_eq!(fake.calls("getTransaction").len(), 1);
    rec.close();
    let w = crate::rec::read_jsonl(&dir, "wallet").unwrap();
    let e = crate::rec::read_jsonl(&dir, "exec").unwrap();
    for (name, rows) in [("wallet", &w), ("exec", &e)] {
        let x = rows.iter().find(|x| x["sig"] == s && x["src"] == "rpc-wallet").unwrap_or_else(|| panic!("{name}: no record"));
        let t = x["transfers"].as_array().unwrap_or_else(|| panic!("{name}: transfers not filled: {x}"));
        let tips: Vec<(Option<u64>, Option<&str>, u64)> = t.iter().filter(|t| t["kind"] == "sender_tip")
            .map(|t| (t["lamports"].as_u64(), t["sender"].as_str(), t["depth"].as_u64().unwrap())).collect();
        assert_eq!((t.len(), tips), (9, vec![(Some(7_254), Some("jito"), 0)]), "{name}");
        assert_eq!((x["tip_total"].as_u64(), x["tip_asked"].as_u64(), x["tip_senders"].clone(), x["jito_tipped"].as_bool()),
            (Some(7_254), Some(7_254), json!(["jito"]), Some(true)), "{name}");
        // the bundle (heuristic, or the block engine's result once classify::note_bundle_processed named it) and arb_like
        // depend on process-wide state other tests change: filled, whatever their content
        assert!(x["bundle"].is_object() && x["arb_like"].is_object(), "{name}: {x}");
    }
    let x = w.iter().find(|x| x["sig"] == s).unwrap();
    assert!(x["wallet_kind"].is_string() && x["wallet_sol"].is_i64() && x["pre_run"] == json!(false), "wallet.jsonl's own fields: {x}");
    let _ = std::fs::remove_dir_all(&dir);
}

/// PLAN WP-03b item 1: a wallet signature the provider never has is fetched again after 1 s, 5 s, then every 30 s, and
/// given up 10 minutes after it was found (its last txfetch line says so); it is never backfilled on top
#[tokio::test(start_paused = true)]
async fn a_wallet_signature_never_found_is_given_up_after_ten_minutes() {
    let wallet = pk(WALLET);
    let roles = Arc::new(Roles::new([(wallet, role_of(role::WALLET, NO_POOL))]));
    let fake = FakeChain::new(no_extra());
    let (rec, dir) = rec_in("giveup");
    let r = run(quiet_cfg(), roles, rec.clone(), fake.clone(), f64::INFINITY);
    let z = sig_of(42);
    r.shared.send(acct(wallet, 100, z));
    tokio::time::sleep(Duration::from_secs(11 * 60)).await;
    let (shared, inputs) = r.end().await;
    let calls = fake.calls("getTransaction");
    assert!(calls.iter().all(|c| c.0 == Role::Wallet), "never backfilled on top");
    let t: Vec<u64> = calls.iter().map(|c| c.2 / 1_000_000_000).collect();
    assert_eq!(&t[..4], &[0, 1, 6, 36], "after 1 s, 5 s, then every 30 s");
    assert!(*t.last().unwrap() >= 600 && *t.last().unwrap() < 640, "{t:?}");
    rec.close();
    let txf = crate::rec::read_jsonl(&dir, "txfetch").unwrap();
    let lines: Vec<&Value> = txf.iter().filter(|l| l["key"] == b58s(&z)).collect();
    assert_eq!(lines.len(), calls.len());
    assert!(lines.iter().all(|l| l["err"] == "not_found" && l["ok"] == false && l["reason"] == "wallet_update"));
    assert_eq!(lines.last().unwrap()["note"], "gave_up");
    assert!(lines[..lines.len() - 1].iter().all(|l| l["note"].is_null()));
    assert!(inputs.iter().all(|i| i.0 != InputKind::WalletTx));
    let (cf, cov) = shared.status_json();
    assert_eq!(cf["wallet_gave_up_delta"].as_u64(), Some(1));
    assert_eq!(cov["wallet_with_tx_pct"].as_f64(), Some(0.0));
    let _ = std::fs::remove_dir_all(&dir);
}

// ---------------------------------------------------------------- backfill

/// PLAN WP-03b acceptance: backfill priority and the auto rate under tokio's paused clock, with the backlog drop and
/// the gauges. 20 uncovered watched signatures a second for 120 s, the backfill providers capped at 10/s: `need_rps_now`
/// follows the demand (a 1-minute EWMA, about 20), the auto rate wants 1.25 x that and is held at the cap from the
/// start, `have_rps_now` stays at the cap, the backlog fills to `max_backlog` and the oldest low-priority signatures are
/// dropped and counted (`chainfetch_backlog`); our attempt's route pool (priority 0) is still fetched as soon as it is due
#[tokio::test(start_paused = true)]
async fn backfill_priority_and_auto_rate_under_a_paused_clock() {
    let (p0, p1, v1) = ([10u8; 32], [11u8; 32], [12u8; 32]);
    let roles = Arc::new(Roles::new([(p0, role_of(role::POOL, 0)), (p1, role_of(role::POOL, 1)), (v1, role_of(role::VAULT, 1))]));
    let fake = FakeChain::new(Box::new(|_, m, p| (m == "getTransaction").then(|| Ok(tx_as(&sig64(p[0].as_str().unwrap()), None)))));
    let cfg = ChainfetchCfg { max_backlog: 300, ..quiet_cfg() };
    let (rec, dir) = rec_in("backfill");
    let r = run(cfg, roles, rec.clone(), fake.clone(), 10.0);
    let mut ours = Vec::new();
    for step in 0..2_400u32 {
        r.shared.send(acct(p0, 1_000 + step as u64 / 8, sig_of(step)));
        if step == 2_000 { r.shared.send(Note::Ours { attempt: 7, sigs: vec![], accounts: vec![p1], t: 0 }); }
        if step > 2_000 && step % 20 == 0 {
            let s = sig_of(1_000_000 + step);
            ours.push((s, step as u64 * 50_000_000));
            r.shared.send(acct(v1, 1_000 + step as u64 / 8, s));
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    let (cf, cov) = r.shared.status_json();
    let need = cf["need_rps_now"].as_f64().unwrap();
    assert!((19.0..22.0).contains(&need), "need {need}");
    assert_eq!((cf["target_rps_now"].as_f64(), cf["cap_rps_now"].as_f64()), (Some(10.0), Some(10.0)), "1.25 x need, held at the cap");
    let have = cf["have_rps_now"].as_f64().unwrap();
    assert!((9.0..=10.6).contains(&have) && have < need, "have {have}");
    let backlog = cf["backlog_now"].as_u64().unwrap();
    assert!((280..=300).contains(&backlog), "the backlog fills to max_backlog: {backlog}");
    let dropped = cf["dropped_delta"].as_u64().unwrap();
    assert!(dropped > 500, "{dropped}");
    // the shortfall shows in the coverage gauge
    assert!(cov["watched_with_tx_pct"].as_f64().unwrap() < 90.0, "{cov}");
    // the fetches: every one a background-role getTransaction; about 10 a second
    let got = fake.calls("getTransaction");
    assert!(got.iter().all(|c| c.0 == Role::Backfill));
    assert!((1_100..=1_250).contains(&got.len()), "{}", got.len());
    // priority 0: every one of our route's signatures fetched within a second of its due time (1.5 s after it was seen;
    // the last ones are not due yet)
    assert!(ours.len() >= 15);
    for (s, t) in ours.iter().filter(|(_, t)| *t + 3_000_000_000 <= 120_000_000_000) {
        let at = got.iter().find(|c| c.1[0].as_str() == Some(b58s(s).as_str())).map(|c| c.2);
        let at = at.unwrap_or_else(|| panic!("ours not fetched"));
        assert!(at >= t + 1_500_000_000 && at <= t + 2_600_000_000, "{} ms after it was seen", (at - t) / 1_000_000);
    }
    let (_, _) = r.end().await;
    rec.close();
    let ev = crate::rec::read_jsonl(&dir, "events").unwrap();
    assert!(ev.iter().any(|e| e["kind"] == "chainfetch_backlog"));
    let ex = crate::rec::read_jsonl(&dir, "exec").unwrap();
    assert!(ex.iter().all(|e| e["src"] == "rpc-backfill" && e["found_by"] == json!(["account_update"])));
    assert!(ex.len() + 16 >= got.len(), "{} records of {} fetches", ex.len(), got.len());
    let _ = std::fs::remove_dir_all(&dir);
}

// ---------------------------------------------------------------- slot index

/// PLAN WP-03b acceptance: the slot index's idx mapping, `missing`, and the idx check. Slot 453,032,285: a backfilled
/// record without a `transactionIndex` gets its idx from the block (`idx_update`); a wallet transaction keeps its
/// `transactionIndex` (29, its position); a signature an account update stamped with the slot but absent from the block
/// is `missing` (fork evidence: an INPUT slotidx_missing, and it is no longer fetched); the transaction stream's idx
/// matches once and not once; the confirmed blockhash reaches the ring (INPUT blockhash_head), and a shred assembler
/// naming another hash for the slot is a disagreement
#[tokio::test(start_paused = true)]
async fn slot_index_maps_idx_reports_missing_and_checks_the_stream() {
    let p = [10u8; 32];
    let roles = Arc::new(Roles::new([(p, role_of(role::POOL, 0))]));
    let list: Vec<String> = fixture("getBlock-453032285-signatures.json")["result"]["signatures"].as_array().unwrap().iter().map(|s| s.as_str().unwrap().to_string()).collect();
    let x = sig64(&list[100]);
    let fake = FakeChain::new(Box::new(move |_, m, p| (m == "getTransaction" && p[0].as_str() == Some(b58s(&x).as_str())).then(|| Ok(tx_as(&x, None)))));
    let (rec, dir) = rec_in("slotidx");
    let r = run(quiet_cfg(), roles, rec.clone(), fake.clone(), f64::INFINITY);
    let (w, y) = (sig64(&list[29]), sig_of(77));
    let slot = 453_032_285;
    for s in [x, y, w] { r.shared.send(acct(p, slot, s)); }
    r.shared.send(Note::StreamTx { sig: sig64(&list[154]), slot, idx: 154, ok: true, recorded: true, t: 0 });
    r.shared.send(Note::StreamTx { sig: sig64(&list[10]), slot, idx: 11, ok: true, recorded: true, t: 0 });
    // the backfill runs 1.5 s in; the slot is confirmed at 4 s
    tokio::time::sleep(Duration::from_secs(4)).await;
    r.shared.send(Note::Slot { slot, status: 1, parent: Some(slot - 1), t: 0 });
    tokio::time::sleep(Duration::from_secs(2)).await;
    r.shared.send(Note::EntryHash { slot, hash: [5u8; 32], feed: 3, t: now_ns() });
    tokio::time::sleep(Duration::from_secs(2)).await;
    let (shared, inputs) = r.end().await;
    rec.close();
    let si = crate::rec::read_jsonl(&dir, "slotidx").unwrap();
    assert_eq!(si.len(), 1);
    let l = &si[0];
    assert_eq!((l["slot"].as_u64(), l["status"].as_str(), l["tx_count"].as_u64(), l["parent_slot"].as_u64()), (Some(slot), Some("ok"), Some(1_193), Some(slot - 1)));
    assert_eq!(l["blockhash"].as_str(), Some("4Lfy7vyBkHtohTXP44W8yQcKF2Gy3kQbE6ctLkDFcYMv"));
    assert_eq!(l["tracked"], json!([[list[29], 29], [list[100], 100]]));
    assert_eq!(l["missing"], json!([b58s(&y)]));
    assert_eq!(l["idx_check"], json!({ "n": 2, "mismatches": 1, "absent": 0 }));
    let ex = crate::rec::read_jsonl(&dir, "exec").unwrap();
    let rx = ex.iter().find(|e| e["sig"] == list[100] && e.get("idx_update").is_none()).unwrap();
    assert!(rx["idx"].is_null() && rx["src"] == "rpc-backfill");
    assert!(ex.iter().any(|e| e["sig"] == list[100] && e["idx_update"] == 100 && e["src"] == "slotidx"));
    let rw = ex.iter().find(|e| e["sig"] == list[29]).unwrap();
    assert_eq!(rw["idx"].as_u64(), Some(29), "getTransaction's transactionIndex");
    // y: missing, an INPUT, and fetched no more after the block said so
    let miss: Vec<&Value> = inputs.iter().filter(|i| i.0 == InputKind::SlotidxMissing).map(|i| &i.1).collect();
    assert_eq!(miss, vec![&json!({ "slot": slot, "status": "ok", "missing": [b58s(&y)] })]);
    let y_fetches = fake.calls("getTransaction").iter().filter(|c| c.1[0].as_str() == Some(b58s(&y).as_str())).count();
    assert!(y_fetches <= 3, "{y_fetches}");
    let heads: Vec<&Value> = inputs.iter().filter(|i| i.0 == InputKind::BlockhashHead).map(|i| &i.1).collect();
    assert_eq!(heads.len(), 1);
    assert_eq!((heads[0]["slot"].as_u64(), heads[0]["src"].as_str(), heads[0]["hash"].as_str()), (Some(slot), Some("slotidx"), Some("4Lfy7vyBkHtohTXP44W8yQcKF2Gy3kQbE6ctLkDFcYMv")));
    let ev = crate::rec::read_jsonl(&dir, "events").unwrap();
    let d = ev.iter().find(|e| e["kind"] == "blockhash_source_disagree").unwrap();
    assert_eq!((d["detail"]["slot"].as_u64(), d["detail"]["a"]["src"].as_str(), d["detail"]["b"]["src"].as_str()), (Some(slot), Some("slotidx"), Some("entries")));
    let (cf, cov) = shared.status_json();
    assert_eq!(cf["idx_check_delta"], json!({ "n": 2, "mismatches": 1 }));
    assert_eq!((cf["missing_delta"].as_u64(), cf["idx_updates_delta"].as_u64()), (Some(1), Some(1)));
    assert_eq!(cf["slotidx_lag_slots_now"].as_u64(), Some(0));
    assert!(cov["slotidx_pct"].is_null(), "the slot's minute has not passed yet");
    let txf = crate::rec::read_jsonl(&dir, "txfetch").unwrap();
    assert!(txf.iter().any(|t| t["method"] == "getBlock" && t["role"] == "slotidx" && t["reason"] == "slot_index" && t["ok"] == true));
    let _ = std::fs::remove_dir_all(&dir);
}

/// PLAN WP-03b acceptance: a skipped slot. A confirmed slot whose parent is four slots back: those four were skipped
/// on this fork and get their lines without an RPC call (an account update stamped with one of them is `missing`);
/// a slot the RPC reports skipped (-32009) gets a `skipped` line (txfetch `ok`, note `skipped`); the coverage of
/// confirmed slots counts both
#[tokio::test(start_paused = true)]
async fn skipped_slots_by_parent_and_by_rpc() {
    let p = [10u8; 32];
    let roles = Arc::new(Roles::new([(p, role_of(role::POOL, 0))]));
    let synthetic = json!({ "blockHeight": 431_072_815, "blockTime": 1, "blockhash": b58(&[7u8; 32]), "parentSlot": 453_034_306, "previousBlockhash": b58(&[6u8; 32]),
        "signatures": [] });
    let fake = FakeChain::new(Box::new(move |_, m, p| (m == "getBlock" && p[0].as_u64() == Some(453_034_307)).then(|| Ok(synthetic.clone()))));
    let (rec, dir) = rec_in("skipped");
    let r = run(quiet_cfg(), roles, rec.clone(), fake.clone(), f64::INFINITY);
    let z = sig_of(5);
    r.shared.send(acct(p, 453_034_309, z));
    r.shared.send(Note::Slot { slot: 453_034_307, status: 1, parent: Some(453_034_306), t: 0 });
    tokio::time::sleep(Duration::from_secs(1)).await;
    r.shared.send(Note::Slot { slot: 453_034_312, status: 1, parent: Some(453_034_307), t: 0 });
    tokio::time::sleep(Duration::from_secs(70)).await;
    let (shared, inputs) = r.end().await;
    let blocks: Vec<u64> = fake.calls("getBlock").iter().map(|c| c.1[0].as_u64().unwrap()).collect();
    assert_eq!(blocks, vec![453_034_307, 453_034_312], "no call for the four skipped slots");
    // a slot the RPC says was skipped
    let fake2 = FakeChain::new(no_extra());
    let r2 = run(quiet_cfg(), Arc::new(Roles::default()), rec.clone(), fake2.clone(), f64::INFINITY);
    r2.shared.send(Note::Slot { slot: 453_034_309, status: 1, parent: None, t: 0 });
    tokio::time::sleep(Duration::from_secs(2)).await;
    let _ = r2.end().await;
    rec.close();
    let si = crate::rec::read_jsonl(&dir, "slotidx").unwrap();
    let by: HashMap<(u64, &str), &Value> = si.iter().map(|l| ((l["slot"].as_u64().unwrap(), l["by"].as_str().unwrap_or("-")), l)).collect();
    for s in 453_034_308..=453_034_311u64 { assert_eq!(by[&(s, "parent")]["status"], "skipped", "{s}"); }
    assert_eq!(by[&(453_034_309, "parent")]["missing"], json!([b58s(&z)]));
    assert_eq!((by[&(453_034_312, "-")]["status"].as_str(), by[&(453_034_312, "-")]["parent_slot"].as_u64(), by[&(453_034_312, "-")]["tx_count"].as_u64()),
        (Some("ok"), Some(453_034_307), Some(40)));
    assert_eq!(by[&(453_034_309, "rpc")]["status"], "skipped");
    assert!(inputs.iter().any(|i| i.0 == InputKind::SlotidxMissing && i.1["missing"] == json!([b58s(&z)]) && i.1["status"] == "skipped"));
    let txf = crate::rec::read_jsonl(&dir, "txfetch").unwrap();
    assert!(txf.iter().any(|t| t["key"] == "453034309" && t["ok"] == true && t["note"] == "skipped" && t["rpc_code"] == -32009));
    let (cf, cov) = shared.status_json();
    assert_eq!(cf["slotidx_delta"], json!({ "ok": 2, "skipped": 4, "error": 0, "dropped": 0, "refused": 0 }));
    assert_eq!(cov["slotidx_pct"].as_f64(), Some(100.0), "every confirmed slot got its line within its minute");
    let _ = std::fs::remove_dir_all(&dir);
}

/// The gap logic itself: slots after the parent are skipped; slots between the last confirmed slot and the parent are
/// fetched (their confirmation was missed); a dead slot is not fetched; a gap longer than 2,000 slots is dropped
#[test]
fn confirmed_slot_gaps() {
    let mut s = slotidx::SlotIndex::new(4, 3_000);
    assert!(s.confirmed(100, Some(99), 0).is_empty());
    assert_eq!(s.confirmed(106, Some(103), 0), vec![104, 105]);
    assert_eq!(s.due(0), vec![100, 101, 102, 103], "101-103 fetched (their confirmation was missed), within the in-flight cap");
    s.dead(106);
    s.confirmed(9_000, None, 0);
    assert_eq!(s.dropped_total, 9_000 - 106 - 1);
}

// ---------------------------------------------------------------- coverage sampler

/// PLAN WP-03b item 3: the coverage sampler. Slot 453,032,285 is indexed, then sampled 30 s in (a block indexed at least
/// 20 s before): of the block's transactions that touch a watched account, the ones no source reported are the unseen
/// share; every watched transaction without a record gets one from the block (src `rpc-block-sample`, its position as
/// idx), the stream's keeps its own
#[tokio::test(start_paused = true)]
async fn the_coverage_sampler_measures_the_unseen_share() {
    let full = fixture("getBlock-453032285-full-first30.json");
    let txs: Vec<RpcTx> = full["result"]["transactions"].as_array().unwrap().iter().map(|t| txjson::from_rpc(t).unwrap()).collect();
    // watch the first writable non-signer account of transactions 1 (v1), 5 and 12
    let pick = |i: usize| -> Pk {
        let h = txs[i].tx.message.as_ref().unwrap().header.clone().unwrap();
        txs[i].keys[h.num_required_signatures as usize]
    };
    let watched: Vec<Pk> = [1, 5, 12].iter().map(|i| pick(*i)).collect();
    let roles = Arc::new(Roles::new(watched.iter().enumerate().map(|(i, k)| (*k, role_of(role::POOL, i as u32)))));
    let touching: Vec<usize> = (0..txs.len()).filter(|i| txs[*i].keys.iter().any(|k| watched.contains(k))).collect();
    assert!(touching.len() >= 3, "{touching:?}");
    let fake = FakeChain::new(no_extra());
    let (rec, dir) = rec_in("sample");
    let cfg = ChainfetchCfg { sample_every_s: 30, ..quiet_cfg() };
    let r = run(cfg, roles, rec.clone(), fake.clone(), f64::INFINITY);
    let slot = 453_032_285;
    // transaction 5 came on the transaction stream; transaction 1 on a shred feed (keys resolved by the engine)
    r.shared.send(Note::StreamTx { sig: txs[5].sig, slot, idx: 5, ok: true, recorded: true, t: 0 });
    r.shared.send(Note::Seen { sig: txs[1].sig, slot, feed: 2, keys: txs[1].keys.clone(), t: 0 });
    r.shared.send(Note::Slot { slot, status: 1, parent: Some(slot - 1), t: 0 });
    tokio::time::sleep(Duration::from_secs(35)).await;
    let (shared, _) = r.end().await;
    assert_eq!(fake.calls("getBlock").iter().filter(|c| c.1[1]["transactionDetails"] == "full" && c.0 == Role::Sample).count(), 1);
    rec.close();
    let (_, cov) = shared.status_json();
    let (w, u) = (touching.len() as u64, touching.len() as u64 - 2);
    assert_eq!(cov["unseen_sample"], json!({ "slot": slot, "watched": w, "unseen": u }));
    assert_eq!(cov["unseen_share_sample"].as_f64(), Some(((u as f64 / w as f64) * 10_000.0).round() / 10_000.0));
    let ex = crate::rec::read_jsonl(&dir, "exec").unwrap();
    let sampled: Vec<&Value> = ex.iter().filter(|e| e["src"] == "rpc-block-sample").collect();
    assert_eq!(sampled.len(), touching.len() - 1, "all but the stream's");
    for e in &sampled {
        let i = txs.iter().position(|t| b58s(&t.sig) == e["sig"].as_str().unwrap()).unwrap();
        assert_eq!((e["idx"].as_u64(), e["slot"].as_u64()), (Some(i as u64), Some(slot)));
    }
    let one = sampled.iter().find(|e| e["sig"] == b58s(&txs[1].sig)).unwrap();
    assert_eq!((one["found_by"].clone(), one["version"].as_str()), (json!(["shred", "block_sample"]), Some("1")));
    let txf = crate::rec::read_jsonl(&dir, "txfetch").unwrap();
    assert!(txf.iter().any(|t| t["role"] == "sample" && t["reason"] == "coverage_sample"));
    let _ = std::fs::remove_dir_all(&dir);
}

// ---------------------------------------------------------------- blockhash poll

/// The getLatestBlockhash poll feeds the ring (by height: lastValidBlockHeight - 150) and the head reaches the engine
/// once (the same answer again changes nothing); the poll is not in txfetch.jsonl (per-role stats only)
#[tokio::test(start_paused = true)]
async fn the_blockhash_poll_feeds_the_head() {
    let fake = FakeChain::new(no_extra());
    let (rec, dir) = rec_in("poll");
    let cfg = ChainfetchCfg { blockhash_poll_ms: 400, ..quiet_cfg() };
    let r = run(cfg, Arc::new(Roles::default()), rec.clone(), fake.clone(), f64::INFINITY);
    tokio::time::sleep(Duration::from_secs(3)).await;
    let (shared, inputs) = r.end().await;
    let polls = fake.calls("getLatestBlockhash");
    assert!((6..=9).contains(&polls.len()), "{}", polls.len());
    assert!(polls.iter().all(|c| c.0 == Role::Blockhash && c.1[0]["commitment"] == "confirmed"));
    let heads: Vec<&Value> = inputs.iter().filter(|i| i.0 == InputKind::BlockhashHead).map(|i| &i.1).collect();
    assert_eq!(heads.len(), 1);
    assert_eq!((heads[0]["hash"].as_str(), heads[0]["height"].as_u64(), heads[0]["src"].as_str(), heads[0]["commitment"].as_str()),
        (Some("CiPxYZQ8YxDQtgRW8kyYmpHgXC8SABRwRYLp1ofU8jeC"), Some(431_367_332 - 150), Some("poll"), Some("confirmed")));
    let (cf, _) = shared.status_json();
    assert_eq!(cf["blockhash"]["src_now"].as_str(), Some("poll"));
    rec.close();
    assert!(crate::rec::read_jsonl(&dir, "txfetch").unwrap_or_default().is_empty());
    let _ = std::fs::remove_dir_all(&dir);
}

/// Without the service the taps do nothing (the engine and the feeds call them unconditionally), and the status
/// sections are null
#[test]
fn taps_without_a_service_are_noops() {
    assert!(SHARED.get().is_none());
    note_stream_tx(&[1u8; 64], 1, 2, true, true);
    note_jito_processed(&[1u8; 64], None);
    note_entry_hash(1, [0; 32], 0);
    note_fired(1, &[], &[]);
    assert_eq!(status_sections(), (Value::Null, Value::Null));
    // a wire signature: legacy / v0 after the count
    let mut raw = vec![1u8];
    raw.extend([4u8; 64]);
    raw.extend([0u8; 10]);
    assert_eq!(txjson::wire_sig(&raw), Some([4u8; 64]));
    let _ = PbTransaction::default();
}

// ---------------------------------------------------------------- shared buckets (review WP-03b #1, #6, #10)

type Served = Arc<Mutex<Vec<(Role, &'static str, &'static str, u64)>>>;

/// A chain on real token buckets (`Registry`, `Limiter`): each call takes its role's token from the provider a bounded
/// call would pick (the one ready soonest for the role's priority, then in order), waiting at most until its deadline
/// (else `rate_budget`, recorded as `Rpc::attempt` records it), then answers after `latency`. Blocks list the
/// signatures `blocks` holds for their slot, every getTransaction finds its transaction, statuses are unknown
struct BucketChain {
    reg: Arc<Registry>,
    providers: HashMap<Role, Vec<&'static str>>,
    blocks: Arc<Mutex<HashMap<u64, Vec<String>>>>,
    served: Served,
    latency: Duration,
    base: tokio::time::Instant,
}

impl BucketChain {
    fn new(reg: Arc<Registry>, providers: HashMap<Role, Vec<&'static str>>, latency: Duration) -> Arc<BucketChain> {
        Arc::new(BucketChain { reg, providers, blocks: Default::default(), served: Default::default(), latency, base: tokio::time::Instant::now() })
    }
    fn served(&self, role: Role, provider: &str, method: &str) -> usize {
        self.served.lock().unwrap().iter().filter(|c| c.0 == role && c.1 == provider && c.2 == method).count()
    }
}

impl Chain for BucketChain {
    fn call(&self, role: Role, method: &'static str, params: Value, b: Bounds) -> BoxFut {
        let (reg, list, blocks, served, latency, base) = (self.reg.clone(), self.providers.get(&role).cloned().unwrap_or_default(), self.blocks.clone(),
            self.served.clone(), self.latency, self.base);
        Box::pin(async move {
            let prio = role.priority();
            let now = tokio::time::Instant::now();
            let Some(p) = list.iter().enumerate().min_by_key(|(i, p)| (reg.limiter(p).wait_hint(prio, now), *i)).map(|(_, p)| *p) else {
                return Err(RpcFailure::new(ErrClass::NoProvider, None, format!("{method}: no provider")));
            };
            let waited = match reg.limiter(p).take(prio, Some(now + b.deadline)).await {
                Ok(w) => w,
                Err(()) => {
                    reg.record(role, p, Err(ErrClass::Budget), Duration::ZERO);
                    return Err(RpcFailure::new(ErrClass::Budget, Some(p), format!("{p} {method}: no token in time")));
                }
            };
            served.lock().unwrap().push((role, p, method, base.elapsed().as_millis() as u64));
            tokio::time::sleep(latency).await;
            reg.record(role, p, Ok(latency.as_micros() as u32), waited);
            let value = match method {
                "getBlock" => {
                    let slot = params[0].as_u64().unwrap_or(0);
                    let mut h = [0u8; 32];
                    h[..8].copy_from_slice(&slot.to_le_bytes());
                    h[31] = 1;
                    let mut v = json!({ "blockhash": b58(&h), "parentSlot": slot - 1, "blockHeight": slot - 100, "blockTime": 1, "previousBlockhash": b58(&[2u8; 32]) });
                    if params[1]["transactionDetails"] == "full" { v["transactions"] = json!([]); }
                    else { v["signatures"] = json!(blocks.lock().unwrap().remove(&slot).unwrap_or_default()); }
                    v
                }
                "getTransaction" => tx_as(&sig64(params[0].as_str().unwrap()), None),
                "getLatestBlockhash" => fixture("getLatestBlockhash.json")["result"].clone(),
                "getSignatureStatuses" => json!({ "context": { "slot": 1 }, "value": params[0].as_array().map(|a| vec![Value::Null; a.len()]).unwrap_or_default() }),
                _ => json!([]),
            };
            Ok(Fetched { value, provider: p.to_string(), latency_ms: latency.as_secs_f64() * 1e3, bytes: 2_000, attempts: 1 })
        })
    }
    fn spare_rps(&self, role: Role) -> Option<f64> {
        let mut sum = 0.0;
        for p in self.providers.get(&role)? { sum += self.reg.spare_rps(p, role)?; }
        Some(sum)
    }
}

fn deploy_split() -> HashMap<Role, Vec<&'static str>> {
    HashMap::from([(Role::Wallet, vec!["haan", "shyft"]), (Role::Blockhash, vec!["haan"]), (Role::Backfill, vec!["haan", "shyft"]),
        (Role::Slotidx, vec!["shyft"]), (Role::Sample, vec!["shyft"])])
}

fn pools(n: u8) -> (Vec<Pk>, Arc<Roles>) {
    let ps: Vec<Pk> = (0..n).map(|i| { let mut k = [0u8; 32]; k[0] = i; k[1] = 0xAB; k }).collect();
    let roles = Arc::new(Roles::new(ps.iter().enumerate().map(|(i, k)| (*k, role_of(role::POOL, i as u32)))));
    (ps, roles)
}

/// Review WP-03b #1 (the blocker; probe P1 on tokio's clock): the deploy split, Haan {wallet, blockhash, backfill} and
/// Shyft {slotidx, sample, backfill, wallet} at 4 requests/s each, under P1's load: 3.7 confirmed slots a second and 30
/// uncovered watched signatures a second (PLAN §0: 16-35/s non-PumpSwap), for 150 s. The slot index is served on Shyft
/// ahead of the backfill: it keeps up (lag of a few slots, none of its calls refused), the blockhash poll stays off while
/// the slot index's confirmed hashes are fresh, and the backfill takes what the providers have spare (about 3.9/s,
/// nearly all on Haan) with few refusals. Before the fix the slot index got 18 blocks in 150 s and fell 531 slots behind
#[tokio::test(start_paused = true)]
async fn the_slot_index_keeps_up_while_the_backfill_has_demand() {
    let reg = Arc::new(Registry::default());
    reg.set_limit("haan", 4.0, None);
    reg.set_limit("shyft", 4.0, None);
    let chain = BucketChain::new(reg.clone(), deploy_split(), Duration::from_millis(30));
    let (ps, roles) = pools(50);
    let cfg = ChainfetchCfg { sigs_every_s: 0, ..ChainfetchCfg::default() };
    let r = run_reg(cfg, roles, Rec::off(), chain.clone(), 8.0, reg.clone());
    let t0 = tokio::time::Instant::now();
    // (slots after the poll fixture's context slot, 453,328,807: the poll's answer names the chain's newest slot too)
    let (mut slot, mut n, mut next_slot) = (453_400_000u64, 0u64, t0);
    let mut lag_max = 0;
    while t0.elapsed() < Duration::from_secs(150) {
        let now = tokio::time::Instant::now();
        if now >= next_slot {
            next_slot += Duration::from_millis(270);
            slot += 1;
            r.shared.send(Note::Slot { slot, status: 0, parent: Some(slot - 1), t: 0 });
            r.shared.send(Note::Slot { slot: slot - 3, status: 1, parent: Some(slot - 4), t: 0 });
        }
        n += 1;
        let s = sig_of(n as u32);
        chain.blocks.lock().unwrap().entry(slot).or_default().push(b58s(&s));
        r.shared.send(acct(ps[(n % 50) as usize], slot, s));
        if t0.elapsed() > Duration::from_secs(20) {
            let (cf, _) = r.shared.status_json();
            lag_max = lag_max.max(cf["slotidx_lag_slots_now"].as_u64().unwrap_or(0));
        }
        tokio::time::sleep(Duration::from_millis(33)).await;
    }
    let (cf, _) = r.shared.status_json();
    let confirmed = slot - 3 - 453_400_000;
    let blocks = chain.served(Role::Slotidx, "shyft", "getBlock");
    // the slot index: every confirmed slot fetched (the last few in flight), on Shyft, none refused
    assert!(blocks as u64 + 4 >= confirmed, "slot index: {blocks} blocks for {confirmed} confirmed slots");
    assert!(lag_max <= 8, "the slot index fell {lag_max} slots behind");
    let si = reg.total(Role::Slotidx, "shyft");
    assert_eq!(si.budget, 0, "no slot-index call refused: {si:?}");
    // the poll: off while the slot index's confirmed hashes are fresh
    let polls = chain.served(Role::Blockhash, "haan", "getLatestBlockhash");
    assert!(polls <= 10, "{polls} polls");
    assert!(cf["blockhash"]["src_now"] == "slotidx", "{}", cf["blockhash"]);
    // the backfill: what the providers have spare (Haan nearly whole, Shyft about 0.3/s), at 0.9 of it, few refusals
    let (bh, bs) = (chain.served(Role::Backfill, "haan", "getTransaction"), chain.served(Role::Backfill, "shyft", "getTransaction"));
    let have = cf["have_rps_now"].as_f64().unwrap();
    let cap = cf["cap_rps_now"].as_f64().unwrap();
    assert!((3.0..=4.3).contains(&have), "have {have}");
    assert!((3.0..=4.0).contains(&cap) && cap < cf["cap_max_rps_now"].as_f64().unwrap(), "cap {cap}: {cf}");
    assert!(bs * 8 < bh, "the backfill runs on Haan: {bh} there, {bs} on Shyft");
    let refused = reg.total(Role::Backfill, "haan").budget + reg.total(Role::Backfill, "shyft").budget;
    assert!(refused * 10 <= (bh + bs) as u64, "{refused} refusals for {} fetches", bh + bs);
    let need = cf["need_rps_now"].as_f64().unwrap();
    assert!(need > 25.0 && need > have, "the shortfall shows: need {need}, have {have}");
    eprintln!("P1 (150 s): {confirmed} confirmed slots, {blocks} slot-index blocks (lag at most {lag_max}), {polls} polls ({} skipped), backfill {bh} on Haan + {bs} on \
        Shyft ({refused} refused), need {need} have {have} cap {cap} rps", cf["blockhash"]["poll_skipped_delta"]);
    let (_, _) = r.end().await;
}

// ---------------------------------------------------------------- our attempts (review WP-03b #2, #20)

/// Review WP-03b #2 (probe P2): one attempt every 1.72 s (2,090 an hour) for 16 minutes, each with one signature, and
/// almost none lands. The signatures are watched with batched getSignatureStatuses (one call every 2 s, each with the
/// signatures of the last 90 s), not fetched blind: the one whose status shows it landed is fetched once, one an account
/// update names (source (a), 5 s after its attempt) is fetched at once without waiting for a status (#20), and a Jito
/// `processed` signature (source (c)) is watched the same way. The rest are counted as never landed. Before: 22
/// getTransaction calls per signature, 13.4/s
#[tokio::test(start_paused = true)]
async fn our_attempts_are_watched_with_batched_statuses() {
    let wallet = pk(WALLET);
    let roles = Arc::new(Roles::new([(wallet, role_of(role::WALLET, NO_POOL))]));
    let (landed, jito) = (b58s(&sig_of(10)), b58s(&sig_of(5_000_000)));
    let (l2, j2) = (landed.clone(), jito.clone());
    let fake = FakeChain::new(Box::new(move |_, m, p| match m {
        "getSignatureStatuses" => Some(Ok(json!({ "context": { "slot": 9 }, "value": p[0].as_array().unwrap().iter().map(|s| if s.as_str() == Some(l2.as_str()) || s.as_str() == Some(j2.as_str()) {
            json!({ "slot": 453_032_285, "confirmations": 0, "err": null, "confirmationStatus": "confirmed" }) } else { Value::Null }).collect::<Vec<_>>() }))),
        "getTransaction" => Some(Ok(tx_as(&sig64(p[0].as_str().unwrap()), Some(42)))),
        _ => None,
    }));
    let (rec, dir) = rec_in("ours");
    let r = run(quiet_cfg(), roles, rec.clone(), fake.clone(), f64::INFINITY);
    let t0 = tokio::time::Instant::now();
    let mut k = 0u32;
    let mut account_at = None;
    while t0.elapsed() < Duration::from_secs(16 * 60) {
        k += 1;
        r.shared.send(Note::Ours { attempt: k as u64, sigs: vec![sig_of(k)], accounts: vec![], t: 0 });
        if k == 20 { account_at = Some(t0.elapsed() + Duration::from_secs(5)); }
        if k == 30 { r.shared.send(Note::JitoProcessed { sig: sig_of(5_000_000), slot: Some(453_032_287), t: 0 }); }
        if account_at.is_some_and(|t| t0.elapsed() >= t) { account_at = None; r.shared.send(acct(wallet, 453_032_286, sig_of(20))); }
        tokio::time::sleep(Duration::from_millis(1_722)).await;
    }
    let (shared, inputs) = r.end().await;
    let gets = fake.calls("getTransaction");
    let mut fetched: Vec<String> = gets.iter().map(|c| c.1[0].as_str().unwrap().to_string()).collect();
    fetched.sort();
    let mut want = vec![landed.clone(), b58s(&sig_of(20)), jito.clone()];
    want.sort();
    assert_eq!(fetched, want, "only the three that landed, once each");
    let (t20, tget) = ((19.0 * 1.722 * 1e9) as u64, gets.iter().find(|c| c.1[0] == b58s(&sig_of(20))).unwrap().2);
    assert!(tget >= t20 + 5_000_000_000 && tget < t20 + 6_800_000_000, "(a) after (b): fetched at once ({} ms after the attempt)", (tget - t20) / 1_000_000);
    let st = fake.calls("getSignatureStatuses");
    assert!((470..=482).contains(&st.len()), "one call every 2 s: {}", st.len());
    assert!(st.iter().all(|c| c.0 == Role::Wallet && c.1[1]["searchTransactionHistory"] == false));
    let biggest = st.iter().map(|c| c.1[0].as_array().unwrap().len()).max().unwrap();
    assert!(biggest <= 54, "a batch holds the last 90 s of signatures: {biggest}");
    // per minute, in the steady state: 30 status calls and nothing else
    let per_min = |m: u64| st.iter().filter(|c| c.2 / 60_000_000_000 == m).count() + gets.iter().filter(|c| c.2 / 60_000_000_000 == m).count();
    assert!((11..15).all(|m| per_min(m) <= 31), "{:?}", (0..16).map(per_min).collect::<Vec<_>>());
    let (cf, cov) = shared.status_json();
    let unlanded = cf["wallet_unlanded_delta"].as_u64().unwrap();
    eprintln!("P2 (16 min): {k} attempts, {} getSignatureStatuses (largest batch {biggest}), {} getTransaction, {unlanded} never landed", st.len(), gets.len());
    assert!(unlanded + 60 >= k as u64 && unlanded < k as u64, "{unlanded} of {k} never landed");
    assert_eq!((cf["wallet_landed_by_status_delta"].as_u64(), cf["wallet_fetched_delta"].as_u64()), (Some(2), Some(3)));
    assert!(cf["wallet_watch_now"].as_u64().unwrap() <= 54);
    assert_eq!(cov["wallet_with_tx_pct"].as_f64(), Some(100.0), "the wallet coverage counts landed signatures only");
    let wins: Vec<&Value> = inputs.iter().filter(|i| i.0 == InputKind::WalletTx).map(|i| &i.1).collect();
    assert_eq!(wins.len(), 3);
    assert!(wins.iter().any(|w| w["attempt"] == 10 && w["found_by"] == json!(["ours"])));
    assert!(wins.iter().any(|w| w["attempt"].is_null() && w["found_by"] == json!(["jito_processed"]) && w["sig"] == jito));
    assert!(wins.iter().any(|w| w["attempt"] == 20 && w["found_by"] == json!(["account_update", "ours"])));
    rec.close();
    let txf = crate::rec::read_jsonl(&dir, "txfetch").unwrap();
    assert_eq!(txf.iter().filter(|t| t["method"] == "getSignatureStatuses" && t["reason"] == "ours_status").count(), st.len());
    let _ = std::fs::remove_dir_all(&dir);
}

/// The exec tap (`note_fired`) reports only the copies that left (a copy the Jito gate kept back has no `t_sent`)
#[test]
fn the_exec_tap_reports_the_copies_that_left() {
    let (shared, rx) = Shared::new(Arc::new(Registry::default()));
    let sent = |sig: [u8; 64], t_sent: u64| crate::send::Sent { attempt: 3, path: "jito".into(), sig: Some(b58s(&sig)), tip_account: None, tip_lamports: 0, t_sent,
        t_ack: 0, ms: 0.0, ok: true, status: None, reply: None, bundle: None };
    with_test_service(shared, || note_fired(3, &[sent(sig_of(1), 5), sent(sig_of(2), 0)], &[[7u8; 32]]));
    let notes: Vec<Note> = rx.try_iter().collect();
    assert!(matches!(&notes[..], [Note::Ours { attempt: 3, sigs, accounts, .. }] if *sigs == vec![sig_of(1)] && *accounts == vec![[7u8; 32]]), "{notes:?}");
}

// ---------------------------------------------------------------- memory (review WP-03b #3)

/// Review WP-03b #3 (probe P5 on tokio's clock): 30 uncovered watched signatures a second for 40 minutes against a
/// backfill held to 5/s. The backlog grows by the shortfall until its oldest signatures turn 10 minutes old, then stays
/// level (they leave the queue, counted as expired); every signature's entry is forgotten 15 minutes after it was seen
/// (the ones that waited in the backfill too), so `known_now` levels off at about 15 minutes of signatures instead of
/// growing for the rest of the run
#[tokio::test(start_paused = true)]
async fn memory_stays_bounded_while_the_backfill_falls_short() {
    let blocks: Arc<Mutex<HashMap<u64, Vec<String>>>> = Default::default();
    let b2 = blocks.clone();
    let fake = FakeChain::new(Box::new(move |_, m, p| match m {
        "getBlock" => {
            let slot = p[0].as_u64().unwrap();
            Some(Ok(json!({ "blockhash": b58(&[3u8; 32]), "parentSlot": slot - 1, "blockHeight": 1, "blockTime": 1, "previousBlockhash": b58(&[2u8; 32]),
                "signatures": b2.lock().unwrap().remove(&slot).unwrap_or_default() })))
        }
        "getTransaction" => Some(Ok(tx_as(&sig64(p[0].as_str().unwrap()), None))),
        _ => None,
    }));
    let (ps, roles) = pools(50);
    let r = run(quiet_cfg(), roles, Rec::off(), fake.clone(), 5.0);
    let t0 = tokio::time::Instant::now();
    let (mut n, mut slot) = (0u32, 1_000u64);
    let mut known = Vec::new();
    let mut backlog_max = 0;
    let mut expired = 0;
    while t0.elapsed() < Duration::from_secs(40 * 60) {
        for _ in 0..3 {
            n += 1;
            blocks.lock().unwrap().entry(slot).or_default().push(b58s(&sig_of(n)));
            r.shared.send(acct(ps[(n % 50) as usize], slot, sig_of(n)));
        }
        if n % 9 == 0 {
            slot += 1;
            r.shared.send(Note::Slot { slot: slot - 3, status: 1, parent: Some(slot - 4), t: 0 });
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
        if n % 3_000 == 0 {
            let (cf, _) = r.shared.status_json();
            known.push((t0.elapsed().as_secs() / 60, cf["known_now"].as_u64().unwrap()));
            backlog_max = backlog_max.max(cf["backlog_now"].as_u64().unwrap());
            expired += cf["expired_delta"].as_u64().unwrap();
        }
    }
    let (_, _) = r.end().await;
    eprintln!("P5 (40 min): known_now by minute {known:?}; backlog at most {backlog_max}; {expired} expired");
    // 30/s for 15 minutes is 27,000 signatures
    let late: Vec<u64> = known.iter().filter(|(m, _)| *m >= 25).map(|x| x.1).collect();
    assert!(!late.is_empty() && late.iter().all(|k| *k <= 29_000), "known_now {known:?}");
    let (lo, hi) = (*late.iter().min().unwrap(), *late.iter().max().unwrap());
    assert!(hi - lo <= 1_500, "known_now levels off: {known:?}");
    // the backlog: 25/s of shortfall for at most 10 minutes
    assert!(backlog_max <= 15_500, "backlog {backlog_max}");
    assert!(expired > 20_000, "expired {expired}");
}

// ---------------------------------------------------------------- D2, deferral, dropped stream records

/// Review WP-03b #21 (the D2 path, end to end) and #11: three transactions a shred feed saw touching a watched pool. One
/// is in its confirmed block: it enters the coverage denominator and is backfilled 1.5 s after it was seen (reason
/// `shred_seen_landed`). One is absent from its block: forgotten, counted `d2_absent`. One is in a slot whose block
/// could not be read: forgotten, counted `d2_unknown` (not absent: nothing is known of it)
#[tokio::test(start_paused = true)]
async fn shred_seen_transactions_join_the_denominator_when_their_block_has_them() {
    let p = [10u8; 32];
    let roles = Arc::new(Roles::new([(p, role_of(role::POOL, 0))]));
    let (s1, s2, s3) = (sig_of(1), sig_of(2), sig_of(3));
    let fake = FakeChain::new(Box::new(move |_, m, prm| match (m, prm[0].as_u64()) {
        ("getBlock", Some(500)) => Some(Ok(json!({ "blockhash": b58(&[3u8; 32]), "parentSlot": 499, "blockHeight": 1, "blockTime": 1, "previousBlockhash": b58(&[2u8; 32]),
            "signatures": [b58s(&sig_of(9)), b58s(&s1)] }))),
        ("getBlock", Some(501)) => { let mut f = RpcFailure::new(ErrClass::Rpc, Some("fake"), "Invalid params".into()); f.code = Some(-32602); f.retryable = false; Some(Err(f)) }
        ("getTransaction", _) => Some(Ok(tx_as(&sig64(prm[0].as_str().unwrap()), None))),
        _ => None,
    }));
    let (rec, dir) = rec_in("d2");
    let r = run(quiet_cfg(), roles, rec.clone(), fake.clone(), f64::INFINITY);
    let keys = vec![[1u8; 32], p];
    for (s, slot) in [(s1, 500), (s2, 500), (s3, 501)] { r.shared.send(Note::Seen { sig: s, slot, feed: 2, keys: keys.clone(), t: 0 }); }
    // a shred-seen transaction touching nothing watched is not a candidate
    r.shared.send(Note::Seen { sig: sig_of(4), slot: 500, feed: 2, keys: vec![[1u8; 32]], t: 0 });
    tokio::time::sleep(Duration::from_millis(500)).await;
    r.shared.send(Note::Slot { slot: 500, status: 1, parent: Some(499), t: 0 });
    r.shared.send(Note::Slot { slot: 501, status: 1, parent: Some(500), t: 0 });
    tokio::time::sleep(Duration::from_secs(70)).await;
    let (shared, _) = r.end().await;
    let gets: Vec<String> = fake.calls("getTransaction").iter().map(|c| c.1[0].as_str().unwrap().to_string()).collect();
    assert_eq!(gets, vec![b58s(&s1)], "only the landed one is fetched");
    let (cf, cov) = shared.status_json();
    assert_eq!((cf["d2_landed_delta"].as_u64(), cf["d2_absent_delta"].as_u64(), cf["d2_unknown_delta"].as_u64()), (Some(1), Some(1), Some(1)));
    assert_eq!((cov["denominator_delta"].as_u64(), cov["watched_with_tx_pct"].as_f64()), (Some(1), Some(100.0)));
    rec.close();
    let txf = crate::rec::read_jsonl(&dir, "txfetch").unwrap();
    assert!(txf.iter().any(|t| t["key"] == b58s(&s1) && t["reason"] == "shred_seen_landed" && t["role"] == "backfill"));
    let ex = crate::rec::read_jsonl(&dir, "exec").unwrap();
    let e1 = ex.iter().find(|e| e["sig"] == b58s(&s1) && e.get("idx_update").is_none()).unwrap();
    assert_eq!((e1["src"].as_str(), e1["found_by"].clone(), e1["idx"].as_u64()), (Some("rpc-backfill"), json!(["shred"]), Some(1)), "idx from the slot index");
    let si = crate::rec::read_jsonl(&dir, "slotidx").unwrap();
    assert!(si.iter().any(|l| l["slot"] == 501 && l["status"] == "error"));
    let _ = std::fs::remove_dir_all(&dir);
}

/// Review WP-03b #9: the first backfill try waits for the slot's confirmation (a getTransaction at `confirmed` finds
/// nothing before it), then goes at once; counted once in `deferred_delta`
#[tokio::test(start_paused = true)]
async fn the_first_backfill_try_waits_for_the_slot_to_be_confirmed() {
    let p = [10u8; 32];
    let roles = Arc::new(Roles::new([(p, role_of(role::POOL, 0))]));
    let fake = FakeChain::new(Box::new(|_, m, prm| (m == "getTransaction").then(|| Ok(tx_as(&sig64(prm[0].as_str().unwrap()), None)))));
    let r = run(quiet_cfg(), roles, Rec::off(), fake.clone(), f64::INFINITY);
    r.shared.send(Note::Slot { slot: 100, status: 1, parent: Some(99), t: 0 });
    let s = sig_of(7);
    r.shared.send(acct(p, 103, s));
    tokio::time::sleep(Duration::from_secs(3)).await;
    assert!(fake.calls("getTransaction").is_empty(), "slot 103 is not confirmed yet");
    r.shared.send(Note::Slot { slot: 103, status: 1, parent: Some(102), t: 0 });
    tokio::time::sleep(Duration::from_secs(1)).await;
    let (shared, _) = r.end().await;
    let gets = fake.calls("getTransaction");
    assert_eq!(gets.len(), 1);
    assert!(gets[0].2 >= 3_000_000_000 && gets[0].2 < 3_400_000_000, "{} ms", gets[0].2 / 1_000_000);
    let (cf, _) = shared.status_json();
    assert_eq!((cf["deferred_delta"].as_u64(), cf["fetched_delta"].as_u64()), (Some(1), Some(1)));
}

/// Review WP-03b #13: a transaction stream record the recorder did not take does not cover its signature (the backfill
/// fetches it); one it took does. Both still feed the idx check
#[tokio::test(start_paused = true)]
async fn a_stream_record_the_recorder_dropped_is_backfilled() {
    let p = [10u8; 32];
    let roles = Arc::new(Roles::new([(p, role_of(role::POOL, 0))]));
    let fake = FakeChain::new(Box::new(|_, m, prm| (m == "getTransaction").then(|| Ok(tx_as(&sig64(prm[0].as_str().unwrap()), None)))));
    let r = run(quiet_cfg(), roles, Rec::off(), fake.clone(), f64::INFINITY);
    let (a, b) = (sig_of(1), sig_of(2));
    r.shared.send(acct(p, 100, a));
    r.shared.send(acct(p, 100, b));
    r.shared.send(Note::StreamTx { sig: a, slot: 100, idx: 4, ok: true, recorded: true, t: 0 });
    r.shared.send(Note::StreamTx { sig: b, slot: 100, idx: 5, ok: true, recorded: false, t: 0 });
    tokio::time::sleep(Duration::from_secs(3)).await;
    let (_, _) = r.end().await;
    let gets: Vec<String> = fake.calls("getTransaction").iter().map(|c| c.1[0].as_str().unwrap().to_string()).collect();
    assert_eq!(gets, vec![b58s(&b)]);
}

// ---------------------------------------------------------------- the taps and the watchdog (review WP-03b #12, #21)

/// The feed taps (review WP-03b #21), at their real call sites: the WP-03 stream fixture through `grpc::tx_stream_item`
/// and `feeds::forward` with this thread's taps going to a test service. Account updates name their transactions; the
/// service gets the processed, confirmed and dead slot statuses, the block meta, and the transaction stream's records
/// with their idx, `recorded` as the recorder took them (with the recorder off, nothing is covered)
#[test]
fn the_feed_taps_report_what_the_stream_carries() {
    use crate::feeds::{fixture, forward, grpc, FeedCounters, Fwd, Interest};
    use prost::Message as _;
    let p = fixture::Proto::load();
    let msgs = fixture::stream(&p);
    let replay = |rec: &Rec| -> Vec<Note> {
        let (shared, rx) = Shared::new(Arc::new(Registry::default()));
        with_test_service(shared, || {
            let (out, _evs) = crossbeam_channel::unbounded();
            let (cs, ct) = (FeedCounters::named("state", "state-stream"), FeedCounters::named("haan-grpc", "yellowstone-tx"));
            let interest = Interest { keys: [fixture::pumpswap()].into_iter().collect(), tables: Default::default() };
            let mut recent = crate::rec::exec::Recent::default();
            let fwd = Fwd { state: true, acct: None, leaders: None };
            for (t, b) in &msgs {
                let m = grpc::SubscribeUpdate::decode(&b[..]).unwrap();
                match m.transaction.clone() {
                    Some(u) => { let it = grpc::tx_stream_item(u, *t, rec, None, &mut recent).unwrap(); forward(0, &interest, &out, &ct, None, rec, &Fwd::default(), it); }
                    None => { let it = grpc::state_item(m, *t).unwrap(); forward(u16::MAX, &interest, &out, &cs, None, rec, &fwd, it); }
                }
            }
        });
        rx.try_iter().collect()
    };
    let (rec, dir) = rec_in("taps");
    let notes = replay(&rec);
    let accts: Vec<(Pk, u64, [u8; 64])> = notes.iter().filter_map(|n| match n { Note::Account { pubkey, slot, txn, .. } => Some((*pubkey, *slot, *txn)), _ => None }).collect();
    assert_eq!(accts.len(), 6);
    assert_eq!(accts[0], (fixture::k(fixture::WALLET), 1_000, fixture::sig(fixture::OURS)));
    let slots: Vec<(u64, i32)> = notes.iter().filter_map(|n| match n { Note::Slot { slot, status, .. } => Some((*slot, *status)), _ => None }).collect();
    assert_eq!(slots, vec![(1_000, 0), (1_002, 0), (1_001, 6), (1_000, 1)], "processed, dead and confirmed only");
    assert!(notes.iter().any(|n| matches!(n, Note::BlockMeta { slot: 1_000, height: Some(900), .. })));
    let txs: Vec<([u8; 64], u64, u64, bool)> = notes.iter().filter_map(|n| match n { Note::StreamTx { sig, slot, idx, recorded, .. } => Some((*sig, *slot, *idx, *recorded)), _ => None }).collect();
    assert_eq!(txs, vec![(fixture::sig(fixture::T1), 1_000, 17, true), (fixture::sig(fixture::T2), 1_002, 3, true)]);
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
    // the recorder off: the records were not taken, so they do not cover their signatures
    let off = replay(&Rec::off());
    assert!(off.iter().filter(|n| matches!(n, Note::StreamTx { .. })).all(|n| matches!(n, Note::StreamTx { recorded: false, .. })));
}

/// Review WP-03b #21: the taps' queue is bounded; past it notes are dropped and counted, and the service reports the
/// drops (events.jsonl `chainfetch_tap_drop`, status `tap_dropped_delta`)
#[tokio::test(start_paused = true)]
async fn tap_drops_are_counted_and_reported() {
    let (rec, dir) = rec_in("tapdrop");
    let (shared, rx) = Shared::with_capacity(Arc::new(Registry::default()), 4);
    for k in 0..7 { shared.send(Note::Slot { slot: 10 + k, status: 0, parent: None, t: 0 }); }
    assert_eq!(shared.tap_dropped.load(Relaxed), 3);
    let fake = FakeChain::new(no_extra());
    let stop = Arc::new(AtomicBool::new(false));
    let h = spawn_watched(Opts { cfg: quiet_cfg(), wallet: None, route_program: pk(ROUTE), roles: Arc::new(Roles::default()), rec: rec.clone(), back: None, chain: fake,
        backfill_cap: f64::INFINITY }, shared.clone(), rx, &tokio::runtime::Handle::current(), stop.clone(), None);
    tokio::time::sleep(Duration::from_secs(61)).await;
    let (cf, _) = shared.status_json();
    assert_eq!((cf["tap_dropped_delta"].as_u64(), cf["service_ok_now"].as_bool()), (Some(3), Some(true)));
    stop.store(true, Relaxed);
    h.await.unwrap();
    rec.close();
    let ev = crate::rec::read_jsonl(&dir, "events").unwrap();
    let d = ev.iter().find(|e| e["kind"] == "chainfetch_tap_drop").expect("chainfetch_tap_drop");
    assert_eq!((d["detail"]["dropped_total"].as_u64(), d["detail"]["queue"].as_u64()), (Some(3), Some(TAP_CAP as u64)));
    assert!(!ev.iter().any(|e| e["kind"] == "chainfetch_dead"), "a stop is not a death");
    let _ = std::fs::remove_dir_all(&dir);
}

/// Review WP-03b #12: the watchdog. A service whose task panics (here its chain panics at the first blockhash poll) is
/// reported: events.jsonl `chainfetch_dead` with the panic, a run.log WARNING, the status (`service_ok_now` false), and
/// `on_dead`, with which the run closes its SendGate for the rest of the segment
#[tokio::test(start_paused = true)]
async fn a_dead_service_is_reported_and_closes_the_gate() {
    struct Boom;
    impl Chain for Boom {
        fn call(&self, _: Role, method: &'static str, _: Value, _: Bounds) -> BoxFut {
            if method == "getLatestBlockhash" { panic!("boom in {method}"); }
            Box::pin(async { Err(RpcFailure::new(ErrClass::NoProvider, None, "none".into())) })
        }
    }
    let (rec, dir) = rec_in("dead");
    let (shared, rx) = Shared::new(Arc::new(Registry::default()));
    let gate = crate::control::SendGate::new();
    let g2 = gate.clone();
    let on_dead: OnDead = Arc::new(move |why: &str| { let _ = g2.shadow("chainfetch_dead", why, true); });
    let cfg = ChainfetchCfg { blockhash_poll_ms: 400, ..quiet_cfg() };
    let h = spawn_watched(Opts { cfg, wallet: None, route_program: pk(ROUTE), roles: Arc::new(Roles::default()), rec: rec.clone(), back: None, chain: Arc::new(Boom),
        backfill_cap: f64::INFINITY }, shared.clone(), rx, &tokio::runtime::Handle::current(), Arc::new(AtomicBool::new(false)), Some(on_dead));
    tokio::time::sleep(Duration::from_secs(2)).await;
    h.await.unwrap();
    assert!(shared.dead.load(Relaxed));
    assert_eq!((gate.mode(), gate.reason().as_str(), gate.sticky()), (crate::control::GateMode::Shadow, "chainfetch_dead", true));
    let (cf, _) = shared.status_json();
    assert_eq!(cf["service_ok_now"], false);
    rec.close();
    let ev = crate::rec::read_jsonl(&dir, "events").unwrap();
    let d = ev.iter().find(|e| e["kind"] == "chainfetch_dead").expect("chainfetch_dead");
    assert!(d["detail"]["why"].as_str().unwrap().contains("boom in getLatestBlockhash"), "{d}");
    let log = std::fs::read_to_string(dir.join("run.log")).unwrap_or_default();
    assert!(log.contains("WARNING: the chain-fetch service stopped"), "{log}");
    let _ = std::fs::remove_dir_all(&dir);
}
