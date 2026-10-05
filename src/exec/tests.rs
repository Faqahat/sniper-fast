//! exec.rs's tests: PLAN WP-05's offline acceptance (bundle-only, the send checks, the in-flight lock, the network-call
//! counter, settlement), PLAN-ADDENDUM I-7 (a shadow run's would-sends) and the go-live gate's dry run (item 4)
use super::*;
use crate::control::GateMode;
use crate::feeds::PohGauge;
use crate::leaders::{LeaderBook, LeaderKind};
use crate::send::jito::{CachedToken, Jito, Outcome};
use crate::send::Path;
use crate::store_health::{HealthFlags, Shut};
use crate::venues::Venue;
use serde_json::json;
use std::sync::atomic::Ordering::Relaxed;
use std::sync::Mutex;

/// the route's token (no pool, vault or wallet key uses this byte)
const MINT: Pk = [251u8; 32];
/// a token the wallet holds no account for
const M2: Pk = [252u8; 32];
const S: u64 = 1_000_000_000;
/// the leaders of the test schedule: a Jito validator, a BAM one, another kind
const LJ: Pk = [231u8; 32];
const LB: Pk = [232u8; 32];
const LO: Pk = [233u8; 32];
/// the test blockhash: the ring's confirmed head, slot 100, height 90
const BH: [u8; 32] = [5u8; 32];

fn wallet_key() -> ed25519_dalek::SigningKey { ed25519_dalek::SigningKey::from_bytes(&[1u8; 32]) }
fn dry_key() -> ed25519_dalek::SigningKey { ed25519_dalek::SigningKey::from_bytes(&[77u8; 32]) }
fn unix_ms() -> i64 { (now_ns() / 1_000_000) as i64 }
fn tip_accounts() -> Vec<Pk> { send::known_tip_accounts(SendKind::JitoBundle).iter().map(|a| pk(a)).collect() }

/// the schedule, slots 96-119: 96-101 the Jito leader, 102-105 the BAM one, 106-109 the other kind, 110-119 Jito again
fn leader_of(slot: u64) -> Pk { match slot { 102..=105 => LB, 106..=109 => LO, _ => LJ } }
fn schedule() -> Vec<Pk> { (96..120).map(leader_of).collect() }
fn window_json() -> Value { json!({ "start": 96, "leaders": schedule().iter().map(b58).collect::<Vec<_>>() }) }

/// a config with one jito-bundle path (70% of the edge, 1,000-100,000 lamports, 5 a second); `extra`: more TOML
fn test_cfg(dir: &std::path::Path, extra: &str) -> Config {
    let wallet = b58(&wallet_key().verifying_key().to_bytes());
    Config::parse(&format!("config_version = 2\nout_dir = \"{}\"\nwallet = \"{wallet}\"\n[pools]\nseed_csv = \"s.csv\"\n[rpc]\n[state]\nurl = \"http://localhost\"\n\
        [[send]]\nname = \"jito-bundle\"\nkind = \"jito-bundle\"\nurl = \"https://127.0.0.1:9\"\ntip_lamports = 1000\ntip_share = 0.7\ntip_max_lamports = 100000\nmax_per_sec = 5\n{extra}",
        dir.display())).unwrap()
}

/// a recorder in `dir` (no monitor thread)
fn test_rec(dir: &std::path::Path) -> Rec {
    rec::start(rec::Opts { dir: dir.to_path_buf(), run: "test".into(), producer: "test".into(), cfg: Default::default(), feeds: vec![], monitor: false, echo: None }).unwrap()
}

fn test_dir(name: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("arbx-exec-{name}-{}-{}", std::process::id(), now_ns()));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn damm(n: u8, t0: Pk) -> PoolMeta {
    PoolMeta { venue: Venue::DammV2, pool: [n; 32], t0, t1: *WSOL, vault0: [n + 50; 32], vault1: [n + 100; 32],
        t0_prog: *crate::pda::TOKEN_PROGRAM, t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![], flag: false }
}

/// a round trip of 1 SOL through DAMM v2 pools `buy` and `sell` expecting `expected`, priced on state version `sv`
fn route(buy: u8, sell: PoolMeta, expected: u64, sv: u64) -> RouteIn {
    let size = 1_000_000_000u64;
    RouteIn { opp: buy as u64, trig: [3u8; 64], trig_feed: None, slot: 99, st: [100, 100, 200, 300, now_ns()], buy: damm(buy, MINT), sell,
        buy_data: vec![], sell_data: vec![], buy_source: "ours", sell_source: "ours", mint: MINT, size, mid: 1_000, back: size + expected, spent: size,
        gross_at_opp: expected as i64, net_at_opp: expected as i64, cu: 100_000,
        buy_live: vec![], sell_live: vec![], buy_end: None, sell_end: None, state_version: sv, route_age_ms: Some(1.5), decision: 40 + sv,
        trig_kind: "commit", t_first_shred: Some(90), t_commit: 150, t_priced: 400, parts_skew: Some((0, 1)),
        crowding: Crowding { signers_6h: Some(3), bucket: 0, src: "map_partial" }, accounts: vec![([buy; 32], 98, 7)] }
}

/// what the in-memory block engine got: each bundle's transaction, and the send path's network calls when it got it
type Got = Arc<Mutex<Vec<(Vec<u8>, Option<u64>)>>>;

/// an in-memory block engine behind `j`: bundles land in the returned list, their ids b0, b1, ...
fn fake_engine(j: &Arc<Jito>) -> Got {
    let got: Got = Default::default();
    let g2 = got.clone();
    j.set_fake(Arc::new(move |txs: &[&[u8]]| {
        let net = crate::netcount::current().map(|c| c.load(Relaxed));
        let mut g = g2.lock().unwrap();
        g.push((txs[0].to_vec(), net));
        format!("b{}", g.len() - 1)
    }));
    got
}

/// a valid cached Jito token (an hour left)
fn fresh_token() -> CachedToken { CachedToken { value: "tok".into(), exp_ms: unix_ms() + 3_600_000, issued_ms: unix_ms() } }

/// a LeaderBook that knows the schedule and the three leaders' kinds
fn book() -> Arc<LeaderBook> {
    let b = LeaderBook::new(Rec::off());
    b.set_list("kobe", &json!({ "validators": [{ "identity_account": b58(&LJ), "running_jito": true }, { "identity_account": b58(&LB), "running_jito": true,
        "running_bam": true }, { "identity_account": b58(&LO), "running_jito": false }] }), now_ns()).unwrap();
    b.add_window(96, &schedule());
    b
}

/// the send view a decision reads: the ring's head at slot 100 (height 90) and the schedule
fn view() -> SendView {
    let mut v = SendView::default();
    v.on_head(&json!({ "hash": b58(&BH), "slot": 100, "height": 90, "src": "slotidx", "commitment": "confirmed", "t_ns": 1 }));
    v.on_window(&window_json());
    v
}

struct Rig {
    x: Exec,
    dir: std::path::PathBuf,
    rec: Rec,
    rx: crossbeam_channel::Receiver<Event>,
    got: Got,
    jito: Option<Arc<Jito>>,
    view: SendView,
    health: Arc<HealthFlags>,
    gauge: &'static PohGauge,
    book: Arc<LeaderBook>,
    /// events from the executor that were not settlements (the Jito sink's INPUT 5)
    buffered: Vec<Event>,
}
impl Drop for Rig { fn drop(&mut self) { self.rec.close(); let _ = std::fs::remove_dir_all(&self.dir); } }

/// An executor in `mode` on a made-up wallet, recording into its own directory. Live and canary send through a
/// jito-bundle path whose block engine is in memory (a valid cached token); shadow and dry runs hold no path (the dry run's
/// key is a throwaway one). The store is ready, the LeaderBook knows the schedule and the kinds, the ring's head is slot
/// 100, the `poh_trigger_pct` gauge is the rig's own. `extra`: more config
async fn rig(name: &str, mode: Mode, extra: &str) -> Rig {
    let dir = test_dir(name);
    let rec = test_rec(&dir);
    let cfg = test_cfg(&dir, extra);
    let (tx, rx) = crossbeam_channel::unbounded();
    let (paths, jito, got) = if mode.sends() {
        let j = Jito::for_test(rec.clone());
        j.set_cached(Some(fresh_token()));
        let got = fake_engine(&j);
        (Some(Paths::for_test(vec![Path::test_bundle(j.clone(), Some(5), cfg.send_policy.queue_ms)], rec.clone())), Some(j), got)
    } else { (None, None, Got::default()) };
    let key = match mode { Mode::Live | Mode::Canary => Some(wallet_key()), Mode::DryRun => Some(dry_key()), Mode::Shadow => None };
    let held: HashSet<Pk> = [*WSOL, MINT].into_iter().collect();
    let mut x = Exec::assemble(&cfg, Rpc::race(vec![]), paths, rec.clone(), tx, vec![], vec![], None, held, mode, key).unwrap();
    let health = Arc::new(HealthFlags::default());
    health.set(Shut::Ready);
    x.set_health(health.clone());
    let book = book();
    x.set_leaders(book.clone());
    let gauge: &'static PohGauge = Box::leak(Box::new(PohGauge::new()));
    x.poh_gauge = gauge;
    Rig { x, dir, rec, rx, got, jito, view: view(), health, gauge, book, buffered: Vec::new() }
}

/// an executor that does nothing (to take a rig's own out for an engine)
fn idle_exec() -> Exec {
    Exec::assemble(&test_cfg(&std::env::temp_dir(), ""), Rpc::race(vec![]), None, Rec::off(), crossbeam_channel::unbounded().0, vec![], vec![], None,
        HashSet::default(), Mode::Shadow, None).unwrap()
}

impl Rig {
    /// the executor's turn at chain tip `tip` (target slot `tip + 1`), engine time `t`
    fn decide(&mut self, r: RouteIn, tip: u64, t: u64) -> Decided {
        let i = self.x.inputs(&self.view, tip, t);
        self.x.decide(r, &i, &self.view, tip, t)
    }
    /// what came back from the executor's tasks so far, into `buffered`
    fn drain(&mut self) { while let Ok(ev) = self.rx.try_recv() { self.buffered.push(ev); } }
    /// the next settlement from the executor's tasks (other events are kept)
    async fn settled(&mut self) -> Settled {
        let t0 = std::time::Instant::now();
        loop {
            self.drain();
            if let Some(i) = self.buffered.iter().position(|e| matches!(e, Event::Settled(_))) {
                let Event::Settled(s) = self.buffered.remove(i) else { unreachable!() };
                return *s;
            }
            assert!(t0.elapsed() < std::time::Duration::from_secs(10), "no settlement");
            tokio::time::sleep(std::time::Duration::from_millis(2)).await;
        }
    }
    /// the INPUT 5 records the Jito sink sent so far (taken out)
    fn releases(&mut self) -> Vec<Value> {
        self.drain();
        let mut out = Vec::new();
        self.buffered.retain(|e| match e {
            Event::Input { kind: InputKind::InflightRelease, data } => { out.push((**data).clone()); false }
            _ => true,
        });
        out
    }
    fn lines(&self, stream: &str) -> Vec<Value> { self.rec.sync(); rec::read_jsonl(&self.dir, stream).unwrap_or_default() }
    fn n(&self, k: &str) -> u64 { self.x.counts.get(k).copied().unwrap_or(0) }
}

/// the inputs of a send that passes every check
fn ok_inputs() -> SendInputs {
    SendInputs { gate: GateMode::Live, gate_reason: "".into(), recorder_ok: true, shut: Shut::Ready, sender: None,
        blockhash: Some(BhSeen { slot: 100, age_slots: Some(3), src: "slotidx".into(), commitment: "confirmed" }), max_blockhash_age_slots: 20,
        leader: LeaderSeen { slot: 104, identity: Some(b58(&LJ)), kind: LeaderKind::Jito, kind_src: Some("kobe".into()) },
        skip_leader_kinds: vec![LeaderKind::Other, LeaderKind::Unknown], token: TokenSeen::Valid { age_s: 10 } }
}

// ------------------------------------------------------------------------------------------------ pure functions

/// PLAN WP-05 acceptance (`send_checks`, table-driven): a blockhash older than `max_blockhash_age_slots` (or none, or of
/// unknown age), a leader of a skipped kind (`other`, `unknown` by default; BAM allowed), an expired token and every other
/// input each refuse with their reason, in the plan's order (the gate first)
#[test]
fn send_checks_refuse_with_their_reasons_in_order() {
    assert_eq!(send_checks(&ok_inputs()), Ok(()));
    let with = |f: &dyn Fn(&mut SendInputs)| { let mut i = ok_inputs(); f(&mut i); send_checks(&i).err() };
    assert_eq!(with(&|i| i.blockhash.as_mut().unwrap().age_slots = Some(20)), None, "20 slots: the limit");
    assert_eq!(with(&|i| i.blockhash.as_mut().unwrap().age_slots = Some(21)).as_deref(), Some("blockhash_stale"));
    assert_eq!(with(&|i| i.blockhash.as_mut().unwrap().age_slots = None).as_deref(), Some("blockhash_stale"), "an age that cannot be told");
    assert_eq!(with(&|i| i.blockhash = None).as_deref(), Some("blockhash_stale"));
    assert_eq!(with(&|i| i.leader.kind = LeaderKind::Other).as_deref(), Some("leader_skip_kind"));
    assert_eq!(with(&|i| { i.leader.kind = LeaderKind::Unknown; i.leader.identity = None; }).as_deref(), Some("leader_unknown"));
    assert_eq!(with(&|i| i.leader.kind = LeaderKind::Bam), None, "BAM is not skipped by default");
    assert_eq!(with(&|i| { i.leader.kind = LeaderKind::Bam; i.skip_leader_kinds.push(LeaderKind::Bam); }).as_deref(), Some("leader_skip_kind"));
    assert_eq!(with(&|i| i.token = TokenSeen::Stale).as_deref(), Some("jito_auth_stale"), "only a valid cached token (F28)");
    assert_eq!(with(&|i| i.token = TokenSeen::NotUsed), None, "no bundle path, no token");
    assert_eq!(with(&|i| { i.gate = GateMode::Shadow; i.gate_reason = "control".into(); }).as_deref(), Some("gate_shadow:control"));
    assert_eq!(with(&|i| i.gate = GateMode::Stopped).as_deref(), Some("gate_stopped"));
    assert_eq!(with(&|i| i.recorder_ok = false).as_deref(), Some("recorder_unhealthy"));
    for (s, why) in [(Shut::Warmup, "warmup"), (Shut::StateUnavailable, "state_unavailable"), (Shut::Resync, "resync")] {
        assert_eq!(with(&|i| i.shut = s).as_deref(), Some(why));
    }
    assert_eq!(with(&|i| i.sender = Some("fee_cap")).as_deref(), Some("fee_cap"));
    // the order: every input bad, then fixed one at a time
    let mut all = ok_inputs();
    all.gate = GateMode::Shadow;
    all.gate_reason = "x".into();
    all.recorder_ok = false;
    all.shut = Shut::Warmup;
    all.sender = Some("fee_cap");
    all.blockhash = None;
    all.leader.kind = LeaderKind::Other;
    all.token = TokenSeen::Stale;
    let mut seen = Vec::new();
    while let Err(e) = send_checks(&all) {
        seen.push(e.split(':').next().unwrap().to_string());
        match seen.len() {
            1 => all.gate = GateMode::Live,
            2 => all.recorder_ok = true,
            3 => all.shut = Shut::Ready,
            4 => all.sender = None,
            5 => all.blockhash = ok_inputs().blockhash,
            6 => all.leader.kind = LeaderKind::Jito,
            _ => all.token = TokenSeen::NotUsed,
        }
    }
    assert_eq!(seen, ["gate_shadow", "recorder_unhealthy", "warmup", "fee_cap", "blockhash_stale", "leader_skip_kind", "jito_auth_stale"]);
    assert_eq!(SEND_CHECKS, ["gate", "recorder", "store_health", "sender", "blockhash", "leader", "jito_auth"]);
    let mut shadow = ok_inputs();
    shadow.gate = GateMode::Shadow;
    assert_eq!(input_checks(&shadow), Ok(()), "input_checks is send_checks without the gate");
}

/// PLAN WP-05 acceptance (the in-flight lock, table-driven): same state, a later slot of the same leader, a new state, a
/// new leader; an entry held `inflight_hold_slots` past its target slot, or until its attempt's final verdict
#[test]
fn the_inflight_lock() {
    let key = InflightKey { buy: [1; 32], sell: [2; 32], mint: MINT };
    let reverse = InflightKey { buy: [2; 32], sell: [1; 32], mint: MINT };
    let mut l = Inflight::new(2);
    assert_eq!(l.check(&key, 7, 101, Some(LJ)), Ok(("first", None)));
    l.insert(key, InflightEntry { sv: 7, target_slot: 101, leader: Some(LJ), attempt: 0, t: 0 });
    // (state version, target slot, leader) -> verdict
    let table: [(u64, u64, Pk, Result<&str, &str>); 6] = [
        (7, 101, LJ, Err("inflight_same_state")),
        (7, 102, LJ, Err("inflight_same_leader")),
        (8, 101, LJ, Ok("new_state")),
        (7, 102, LB, Ok("new_leader")),
        (8, 102, LB, Ok("new_state")),
        (7, 104, LJ, Ok("first")),
    ];
    for (sv, target, leader, want) in table {
        assert_eq!(l.check(&key, sv, target, Some(leader)).map(|x| x.0), want, "sv {sv} target {target}");
    }
    assert_eq!(l.check(&key, 8, 101, Some(LJ)).unwrap().1, Some((0, 7)), "the attempt and state it follows");
    assert_eq!(l.check(&reverse, 7, 101, Some(LJ)), Ok(("first", None)), "the reverse route is another key");
    // held while the chain is at target + 1, gone at target + 2
    l.expire(102);
    assert_eq!(l.len(), 1);
    l.expire(103);
    assert!(l.is_empty());
    // the final verdict releases it at once
    l.insert(key, InflightEntry { sv: 7, target_slot: 101, leader: Some(LJ), attempt: 5, t: 0 });
    assert!(!l.release(4) && l.len() == 1, "another attempt's verdict");
    assert!(l.release(5) && l.is_empty());
    assert_eq!(l.check(&key, 7, 101, Some(LJ)), Ok(("first", None)));
    // an unknown leader is the same unknown leader
    l.insert(key, InflightEntry { sv: 7, target_slot: 101, leader: None, attempt: 6, t: 0 });
    assert_eq!(l.check(&key, 7, 101, None), Err("inflight_same_state"));
    assert_eq!(l.check(&key, 7, 101, Some(LJ)), Ok(("new_leader", Some((6, 7)))));
}

/// PLAN WP-05 item 8: on-chain min_profit = tip + base fee + margin, margin = max(floor, share × net); the Stage-0
/// defaults (floor 1, share 0) keep today's floor (tip + base fee + 1). The bundle path's tip: its share of the edge within
/// its floor and cap, to its accounts in turn
#[test]
fn margins_and_tips() {
    assert_eq!(min_profit_onchain(31_500, 13_500, 1, 0.0), (36_501, 1), "today's floor");
    assert_eq!(min_profit_onchain(31_500, 200_000, 2_000, 0.02), (40_500, 4_000), "R §3.9's arm: 2% of the net");
    assert_eq!(min_profit_onchain(31_500, 50_000, 2_000, 0.02), (38_500, 2_000), "the floor");
    assert_eq!(min_profit_onchain(0, -5, 1, 0.5), (5_001, 1), "a negative net takes the floor");
    let c = test_cfg(&std::env::temp_dir(), "");
    let mut t = TipPolicy::from_path(&c.sends[0]);
    let (a, x) = t.tip(50_000).unwrap();
    let (b, _) = t.tip(50_000).unwrap();
    assert_eq!(x, 35_000);
    assert_eq!(t.tip(45_000).unwrap().1, 31_499, "the share is rounded down: never more than it");
    assert_ne!(a, b, "the accounts rotate");
    assert_eq!(t.tip(100).unwrap().1, 1_000, "the floor");
    assert_eq!(t.tip(10_000_000).unwrap().1, 100_000, "the cap");
    assert!(tip_accounts().contains(&a));
}

/// data/crowded-pools.json: the 21 pools with 150 or more bots, with its source and date; bad entries are errors
#[test]
fn crowded_pools_file_loads() {
    let text = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/data/crowded-pools.json")).unwrap();
    let set = parse_crowded_pools(&text).unwrap();
    assert_eq!(set.len(), 21, "PATTERNS.md item 10: 21 pools with 150 or more bots");
    let v: Value = serde_json::from_str(&text).unwrap();
    assert!(v["source"].is_string() && v["date"].is_string());
    assert!(v["pools"].as_array().unwrap().iter().all(|p| p["bots"].as_u64().unwrap() >= 150));
    assert_eq!(parse_crowded_pools("[\"58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2\"]").unwrap().len(), 1, "a plain array");
    assert!(parse_crowded_pools("{\"pools\": [{\"pool\": \"not-a-key\"}]}").is_err());
    assert!(parse_crowded_pools("{\"pools\": [{\"bots\": 200}]}").is_err());
    assert!(parse_crowded_pools("{}").is_err());
    assert!(parse_crowded_pools("{\"pools\": []}").is_err(), "review N1: an empty list is a mistake, not a list");
    assert!(load_crowded_pools("/nonexistent/crowded-pools.json").is_err(), "a configured list must load");
}

/// The send view (journaled inputs only): the ring's head is the confirmed blockhash, a block meta the processed one; the
/// newest height; a blockhash expires 150 blocks after its own height (300 slots without heights); the schedule
#[test]
fn the_send_view() {
    let mut v = SendView::default();
    assert!(v.blockhash("confirmed").is_none());
    v.on_block_meta(103, [9; 32], Some(93), 5);
    assert!(v.blockhash("confirmed").is_none(), "a block meta is processed only");
    assert_eq!(v.blockhash("processed").map(|b| (b.slot, b.src.as_str())), Some((103, "blocks_meta")));
    v.on_head(&json!({ "hash": b58(&BH), "slot": 100, "height": 90, "src": "slotidx", "commitment": "confirmed", "t_ns": 1 }));
    assert_eq!(v.blockhash("confirmed").map(|b| (b.slot, b.hash)), Some((100, BH)));
    assert_eq!(v.blockhash("processed").map(|b| b.slot), Some(103), "the newer of the two");
    v.on_block_meta(101, [8; 32], Some(91), 6);
    assert_eq!(v.blockhash("processed").map(|b| b.slot), Some(103), "an older meta does not replace a newer one");
    assert_eq!(v.height, Some((103, 93)));
    assert_eq!(v.expired(100, Some(90), 0), Some(false));
    v.on_block_meta(400, [1; 32], Some(241), 7);
    assert_eq!(v.expired(100, Some(90), 0), Some(true), "height 241 > 90 + 150");
    assert_eq!(v.expired(100, None, 399), Some(false));
    assert_eq!(v.expired(100, None, 401), Some(true), "no height: slot + 300");
    assert_eq!(SendView::default().expired(100, None, 0), None, "nothing known");
    v.on_window(&json!({ "start": 500, "leaders": [b58(&LJ), b58(&LB)] }));
    assert_eq!((v.leader(500), v.leader(501), v.leader(502)), (Some(LJ), Some(LB), None));
}

// ------------------------------------------------------------------------------------------------ the executor's start

/// What each mode refuses at its start, before any RPC call: a live or canary executor needs the trading key (the
/// config's wallet), bundle-only send paths and its bundle path; a dry run refuses send paths and the trading key; a
/// shadow one holds no key; a configured crowded list that does not load stops every start (review F8 c)
#[tokio::test]
async fn exec_new_refuses_what_its_mode_forbids() {
    let dir = test_dir("new");
    let cfg = test_cfg(&dir, "");
    let (tx, _rx) = crossbeam_channel::unbounded();
    let j = Jito::for_test(Rec::off());
    let paths = Paths::for_test(vec![Path::test_bundle(j, Some(5), 10)], Rec::off());
    let err = |cfg: &Config, paths: Option<Arc<Paths>>, mode: Mode, key: Option<ed25519_dalek::SigningKey>| {
        let (cfg, tx) = (cfg.clone(), tx.clone());
        async move { format!("{:#}", Exec::new(&cfg, &Rpc::race(vec![]), paths, Rec::off(), tx, vec![], mode, key, vec![]).await.err().expect("refused")) }
    };
    assert!(err(&cfg, Some(paths.clone()), Mode::Live, None).await.contains("needs the trading key"));
    assert!(err(&cfg, Some(paths.clone()), Mode::Live, Some(dry_key())).await.contains("not the config's wallet"));
    assert!(err(&cfg, None, Mode::Canary, Some(wallet_key())).await.contains("needs its send paths"));
    let helius = "[[send]]\nname = \"helius\"\nkind = \"helius\"\nurl = \"https://fra-sender.helius-rpc.com/fast\"\ntip_lamports = 5000\n";
    let mixed = test_cfg(&dir, helius);
    assert!(err(&mixed, Some(paths.clone()), Mode::Live, Some(wallet_key())).await.contains("bundle-only"));
    assert!(err(&cfg, Some(paths.clone()), Mode::DryRun, Some(dry_key())).await.contains("a dry run builds no send path"));
    assert!(err(&cfg, None, Mode::DryRun, Some(wallet_key())).await.contains("must not be the trading wallet"));
    assert!(err(&cfg, None, Mode::Shadow, Some(dry_key())).await.contains("holds no key"));
    let crowded = test_cfg(&dir, "[send_policy]\ncrowded_pools_file = \"/nonexistent/crowded-pools.json\"\n");
    for mode in [Mode::Shadow, Mode::DryRun] {
        let key = (mode == Mode::DryRun).then(dry_key);
        assert!(err(&crowded, None, mode, key).await.contains("crowded_pools_file"), "{mode:?}");
    }
    let _ = std::fs::remove_dir_all(&dir);
}

// ------------------------------------------------------------------------------------------------ live

/// PLAN WP-05 acceptance: a live decision yields exactly one bundle copy, built on the ring's recent blockhash (no durable
/// nonce), its tip last to a Jito tip account, its route instruction carrying the size and the on-chain min_profit (tip +
/// base fee + 1) as signed (review WP-05 #12); the network-call counter is 0 when the send reaches the (in-memory) block
/// engine, while a token refresh's calls run in the background (F28). The attempt line (v2) carries the blockhash with
/// its age and source, the band, the crowding, the LeaderBook's snapshot of the target slot, the in-flight key, the state
/// version and the queue; copies.jsonl has the copy; `leader_known_pct` counts it (the `poh_trigger_pct` gauge is the
/// engine's, after the decision: `a_shadow_run_records_would_sends`)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_live_decision_sends_one_bundle_copy_with_no_network_call() {
    let mut r = rig("live-one", Mode::Live, "").await;
    crate::leaders::note_be_rtt(12.5);
    let t0 = crate::netcount::total();
    // a "token refresh" in the background while the send runs: its calls are not the send path's
    let bg = tokio::spawn(async { for _ in 0..50 { crate::netcount::note(); tokio::time::sleep(std::time::Duration::from_millis(1)).await; } });
    let d = r.decide(route(1, damm(2, MINT), 55_000, 7), 100, now_ns());
    assert_eq!((d.verdict, d.reason.as_str(), d.attempt, d.sent, d.would_send), ("send", "sent", Some(0), Some(true), false), "{d:?}");
    assert_eq!((d.rank, d.crowding.map(|c| c.bucket), d.ev), (Some(0), Some(0), Some(15_000)), "net: 55,000 - the 35,000 tip - the base fee");
    let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
    bg.await.unwrap();
    assert_eq!((attempt, fired.copies.len()), (0, 1), "exactly one bundle copy");
    let c = &fired.copies[0];
    assert!(c.ok && c.t_sent > 0 && c.bundle.as_deref() == Some("b0") && c.drop.is_none(), "{c:?}");
    let got = r.got.lock().unwrap().clone();
    assert_eq!(got.len(), 1, "one bundle reached the block engine");
    assert_eq!(got[0].1, Some(0), "no network call between the decision and the block engine (F28)");
    assert_eq!(r.x.net_calls(), 0);
    assert!(crate::netcount::total() >= t0 + 50, "the background calls were counted, outside the send path");
    // the transaction: one signature (the wallet's), the ring's blockhash, no AdvanceNonce, the tip last to a Jito account
    let raw = &got[0].0;
    let (tx, used) = crate::tx::parse_wire(raw).unwrap();
    assert_eq!((used, tx.num_signers, tx.keys[0]), (raw.len(), 1, r.x.payer));
    assert!(!tx.ixs.iter().any(|ix| tx.keys[ix.program as usize] == [0u8; 32] && ix.data.first() == Some(&4)), "no durable nonce");
    let tip = Some((tx.keys[tx.ixs.last().unwrap().accounts[1] as usize], 35_000));
    let checks = verify_bundle(raw, &live_want(&r.x, tip, 40_001));
    for c in &checks { assert_eq!(c["ok"], json!(true), "{c}"); }
    // the route instruction as signed: the size and min_profit = the 35,000 tip + the base fee + 1
    let all = tx.resolve(|t| r.x.alt_lists.get(t).cloned()).unwrap();
    let seen = route_of(&tx, &all, &r.x.program).unwrap();
    assert_eq!((seen.amount_in, seen.min_profit, seen.authority, seen.legs.len()), (1_000_000_000, 40_001, r.x.payer, 2));
    assert_eq!((seen.legs[0].program, seen.legs[1].program), (Venue::DammV2.program(), Venue::DammV2.program()));
    assert_eq!(send::tip_paid(&tx, &tip_accounts()), 35_000, "70% of the 50,000 edge");
    r.x.on_settled(Settled::Fired { attempt, fired }, now_ns(), &|_| None);
    let a = r.lines("attempts");
    assert_eq!(a.len(), 1);
    let l = &a[0];
    assert_eq!((l["kind"].as_str(), l["sent"].as_bool(), l["copies"].as_array().map(|c| c.len())), (Some("live"), Some(true), Some(1)));
    assert_eq!((l["blockhash"]["hash"].as_str(), l["blockhash"]["slot"].as_u64(), l["blockhash"]["age_slots"].as_u64(), l["blockhash"]["src"].as_str(),
        l["blockhash"]["commitment"].as_str()), (Some(b58(&BH).as_str()), Some(100), Some(0), Some("slotidx"), Some("confirmed")));
    assert_eq!((l["leader"]["slot"].as_u64(), l["leader"]["leader"].as_str(), l["leader"]["kind"].as_str(), l["leader"]["kind_src"].as_str()),
        (Some(101), Some(b58(&LJ).as_str()), Some("jito"), Some("kobe")), "the LeaderBook's snapshot of the target slot");
    assert!(l["leader"]["be_rtt_ms"].as_f64().is_some(), "the block engine's keep-alive RTT");
    assert_eq!((l["band"].as_u64(), l["sv"].as_str(), l["inflight"]["why_allowed"].as_str(), l["inflight"]["key"][0].as_str()),
        (Some(1), Some("0000000000000007"), Some("first"), Some(b58(&[1u8; 32]).as_str())));
    assert_eq!((l["queue"]["rank"].as_u64(), l["queue"]["ev"].as_i64()), (Some(0), Some(15_000)));
    assert_eq!((l["tip"]["lamports"].as_u64(), l["min_profit_onchain"].as_u64(), l["margin"].as_u64()), (Some(35_000), Some(40_001), Some(1)),
        "min_profit = tip + base fee + max(margin_floor 1, 0 x net)");
    assert_eq!((l["crowding"]["src"].as_str(), l["crowding"]["bucket"].as_u64()), (Some("map_partial"), Some(0)));
    assert_eq!((l["tx"]["sig"].as_str(), l["route_in"]["accounts"][0]["wv"].as_u64()), (c_sig(&got[0].0).as_deref(), Some(7)));
    assert!(l["stages"]["t_signed"].as_u64().is_some() && l["stages"]["t_enqueued"].as_u64().is_some());
    assert_eq!(l["checks"].as_array().map(|c| c.len()), Some(SEND_CHECKS.len() + 10));
    let cp = r.lines("copies");
    assert_eq!((cp.len(), cp[0]["blockhash_slot"].as_u64(), cp[0]["queue_wait_us"].as_u64(), cp[0]["drop"].is_null()), (1, Some(100), Some(0), true));
    assert_eq!(r.gauge.status(&[], now_ns())["attempts_total"].as_u64(), Some(0), "the executor no longer reads the PoH index before the fire (review #8)");
    assert_eq!(r.x.leader_known_pct(), json!(100.0));
    assert_eq!(r.x.leader_known_pct(), Value::Null, "none since");
    assert_eq!((r.n("live_sent"), r.x.open_attempts()), (1, vec![0]));
}

fn c_sig(raw: &[u8]) -> Option<String> { send::first_signature(raw) }

/// what a live rig's bundle on the test route (pools [1; 32] and [2; 32], 1 SOL, DAMM v2 legs, signed by the wallet)
/// must be, with its tip and on-chain min_profit
fn live_want(x: &Exec, tip: Option<(Pk, u64)>, min_profit: u64) -> VerifyWant<'_> {
    VerifyWant { payer: x.payer, signer: x.payer, blockhash: BH, tip, tips: tip_accounts(), program: x.program, pools: [[1; 32], [2; 32]], cu_limit: 100_000,
        alts: &x.alt_lists, amount_in: 1_000_000_000, min_profit, margin_floor: 1, quote: build::ata_of(&x.payer, &WSOL, &crate::pda::TOKEN_PROGRAM),
        mid: build::ata_of(&x.payer, &MINT, &crate::pda::TOKEN_PROGRAM), leg_programs: [Venue::DammV2.program(), Venue::DammV2.program()] }
}

/// Fail closed (WP-04 review #8; PLAN WP-05 item 2): an executor is not ready until an engine installs its health; a
/// non-Jito leader, a stale or missing blockhash, a slot outside the schedule, an expiring token and a closed recorder
/// each refuse, before anything is built or sent
#[tokio::test]
async fn the_executor_fails_closed() {
    let mut r = rig("closed", Mode::Live, "").await;
    let t = now_ns();
    r.x.set_health(Arc::new(HealthFlags::default()));
    let d = r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t);
    assert_eq!((d.reason.as_str(), d.attempt), ("warmup", None), "not ready by default");
    r.x.set_health(r.health.clone());
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 2), 105, t + 1).reason, "leader_skip_kind", "slot 106: the other kind");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 3), 200, t + 2).reason, "blockhash_stale", "100 slots old");
    let mut empty = SendView::default();
    std::mem::swap(&mut empty, &mut r.view);
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 4), 100, t + 3).reason, "blockhash_stale", "no blockhash at all");
    std::mem::swap(&mut empty, &mut r.view);
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 5), 120, t + 4).reason, "leader_unknown", "slot 121: outside the schedule");
    // the journaled schedule names the leader; a LeaderBook that names another for the slot makes it unknown
    r.view.on_window(&json!({ "start": 101, "leaders": [b58(&LB)] }));
    let i = r.x.inputs(&r.view, 100, t + 5);
    assert_eq!((i.leader.identity.clone(), i.leader.kind, i.leader.kind_src.as_deref()), (Some(b58(&LB)), LeaderKind::Unknown, Some("schedule_mismatch")));
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 6), 100, t + 5).reason, "leader_unknown");
    r.view.on_window(&json!({ "start": 101, "leaders": [b58(&LJ)] }));
    let j = r.jito.clone().unwrap();
    j.set_cached(Some(CachedToken { value: "t".into(), exp_ms: unix_ms() + 2_000, issued_ms: unix_ms() - 600_000 }));
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 6), 100, now_ns()).reason, "jito_auth_stale", "2 s left: the send path would not use it");
    j.set_cached(None);
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 100, now_ns()).reason, "jito_auth_stale", "none");
    j.set_cached(Some(fresh_token()));
    r.rec.close();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 8), 100, now_ns()).reason, "recorder_unhealthy", "a closed recorder");
    r.x.rec = Rec::off();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 9), 100, now_ns()).reason, "recorder_unhealthy", "no recorder");
    assert!(r.got.lock().unwrap().is_empty(), "nothing was sent");
    assert_eq!((r.n("reject_warmup"), r.n("reject_blockhash_stale"), r.n("reject_jito_auth_stale"), r.n("reject_leader_unknown"), r.n("reject_leader_skip_kind")),
        (1, 2, 2, 2, 1));
    assert_eq!(r.x.next_attempt, 0, "no attempt");
}

/// The route checks in a live run: the in-flight lock (the same state, a later slot of the same leader, a new state, a new
/// leader), the ≥1M class's bucket (a token every 2 s), the crowded skip (`crowded_skip`, from
/// `crowded_skip_min_expected_lamports`) and the crowded rank, the decision's bar, an implausible gap, the rent cap, token
/// cooling after 25 attempts' would-fails in a row (a second would-fail of one bundle does not count again: review #16)
#[tokio::test]
async fn the_route_checks() {
    let mut r = rig("route", Mode::Live, "[send_policy]\ncrowded_skip_min_expected_lamports = 100000\n").await;
    let t = now_ns();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 100, t).reason, "sent");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 100, t + 1).reason, "inflight_same_state");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 100, t + 2).reason, "inflight_same_state");
    // tip 101: target 102, the BAM leader: a new leader; tip 102: target 103, the same BAM leader, a later slot
    let d = r.decide(route(1, damm(2, MINT), 50_000, 7), 101, t + 3);
    assert_eq!(d.reason, "sent", "a new leader");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 102, t + 4).reason, "inflight_same_leader");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 8), 102, t + 5).reason, "sent", "a new state");
    let a = r.lines("attempts");
    assert_eq!(a.iter().map(|l| (l["inflight"]["why_allowed"].as_str().unwrap().to_string(), l["inflight"]["prev_attempt"].as_u64())).collect::<Vec<_>>(),
        vec![("first".into(), None), ("new_leader".into(), Some(0)), ("new_state".into(), Some(1))]);
    // the big class: 0.5/s, burst 1
    let big = 1_100_000;
    assert_eq!(r.decide(route(3, damm(4, MINT), big, 1), 100, t).reason, "sent");
    assert_eq!(r.decide(route(3, damm(4, MINT), big, 2), 100, t + S).reason, "band_throttle");
    assert_eq!(r.decide(route(3, damm(4, MINT), big, 3), 100, t + 2 * S + 1).reason, "sent", "a token every 2 s");
    // crowded: bucket 2 from 100k expected is not sent; below it, it goes ranked behind its band's others
    let mut c = route(5, damm(6, MINT), 150_000, 1);
    c.crowding = Crowding { signers_6h: None, bucket: 2, src: "static_list" };
    assert_eq!(r.decide(c.clone(), 100, t).reason, "crowded_skip");
    let mut c2 = route(5, damm(6, MINT), 60_000, 2);
    c2.crowding = c.crowding;
    let d = r.decide(c2, 100, t);
    assert_eq!((d.reason.as_str(), d.rank), ("sent", Some(1)));
    // the decision's bar: tip + base fee + [live] margin_lamports (6,999 pays a 1,399 tip: the bar is 7,399)
    assert_eq!(r.decide(route(7, damm(8, MINT), 6_999, 1), 100, t).reason, "expected_below_min_profit");
    assert_eq!(r.decide(route(7, damm(8, MINT), 0, 2), 100, t).reason, "expected_below_min_profit");
    assert_eq!(r.decide(route(7, damm(8, MINT), 2_000_000_000, 3), 100, t).reason, "implausible_gap");
    // a token the wallet holds no account for, the rent cap reached ([live] max_new_token_accounts)
    let mut m2 = route(7, damm(8, M2), 50_000, 4);
    m2.mint = M2;
    m2.buy = damm(7, M2);
    r.x.max_new_atas = 0;
    assert_eq!(r.decide(m2, 100, t).reason, "rent_cap");
    assert_eq!((r.n("reject_inflight_same_state"), r.n("reject_inflight_same_leader"), r.n("reject_band_throttle"), r.n("reject_crowded_skip"), r.n("rank_crowded")),
        (2, 1, 1, 1, 1));
    // token cooling: would-fails of 25 attempts in a row (the block engine's results) pause the token 60 s; one bundle's
    // repeated would-fails count once
    for k in 0..24u8 { assert_eq!(r.decide(route(40 + 2 * k, damm(41 + 2 * k, MINT), 50_000, 1), 100, t).reason, "sent"); }
    let open = r.x.open_attempts();
    assert_eq!(open.len(), 30);
    let wf = |a: u64| json!({ "attempt": a, "outcome": "would-fail", "release": false, "sig": null });
    for k in 0..24 { r.x.on_release(&wf(open[k]), t + k as u64); }
    for _ in 0..5 { r.x.on_release(&wf(open[0]), t + 30); }
    assert_eq!((r.decide(route(9, damm(10, MINT), 50_000, 1), 100, t + 30).reason.as_str(), r.n("cool_repeat")), ("sent", 5), "24 attempts: not yet");
    r.x.on_release(&wf(open[24]), t + 31);
    assert_eq!(r.decide(route(11, damm(12, MINT), 50_000, 1), 100, t + 32).reason, "token_cooling");
    assert_eq!(r.decide(route(11, damm(12, MINT), 50_000, 2), 100, t + 61 * S).reason, "sent", "60 s later");
    assert_eq!(r.n("verdict_would_fail"), 30, "every result is counted as a verdict");
    // the run stops: every attempt still open gets its `unsettled` final line (stop.json lists them)
    let open = r.x.open_attempts();
    assert_eq!(open.len(), 32);
    assert_eq!(r.x.settle_at_stop(), open);
    let o = r.lines("outcomes");
    assert_eq!((o.len(), o.iter().all(|l| l["final"] == "unsettled" && l["final_src"] == "stop")), (32, true));
    assert!(r.x.open_attempts().is_empty() && r.x.inflight.is_empty());
    assert_eq!(r.n("unsettled"), 32);
}

/// PLAN WP-05 item 1: a canary run is a live run under `[canary]`'s caps: trades of at most `size_sol` (never above 0.2
/// SOL, nor `[live] max_size_sol`), `count` attempts at least `every_ms` apart, then the sender stops (`canary_count`);
/// its failed-fee cap is `max_spend_lamports`
#[tokio::test]
async fn a_canary_is_a_capped_live_run() {
    let mut r = rig("canary", Mode::Canary, "[canary]\nenabled = true\ncount = 2\nevery_ms = 1000\nsize_sol = 0.05\nmax_spend_lamports = 20000\n").await;
    assert_eq!((r.x.size_cap(), r.x.cap_failed_fees), (50_000_000, 20_000));
    let t = now_ns();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t).reason, "sent");
    assert_eq!(r.decide(route(3, damm(4, MINT), 50_000, 1), 100, t + 1).reason, "canary_wait");
    assert_eq!(r.decide(route(3, damm(4, MINT), 50_000, 2), 100, t + S + 1).reason, "sent", "every_ms later");
    assert_eq!(r.decide(route(5, damm(6, MINT), 50_000, 1), 100, t + 3 * S).reason, "canary_count");
    assert_eq!(r.x.status()["stopped"].as_str(), Some("canary count reached"));
    assert_eq!(r.decide(route(7, damm(8, MINT), 50_000, 1), 100, t + 4 * S).reason, "sender_stopped", "for good");
    let a = r.lines("attempts");
    assert_eq!(a.iter().map(|l| (l["kind"].as_str().unwrap().to_string(), l["sent"].as_bool().unwrap())).collect::<Vec<_>>(),
        vec![("canary".to_string(), true), ("canary".to_string(), true)]);
    assert_eq!((r.n("canary_sent"), r.n("reject_canary_wait"), r.n("reject_canary_count"), r.n("reject_sender_stopped")), (2, 1, 1, 1));
}

/// PLAN WP-01's control test on the WP-05 executor: `pause-sending` through the control socket closes the gate. The
/// decision's reason is `gate_shadow:control`; one that passes every other check is a would-send (decisions `would_send`,
/// attempts `sent = false`, nothing reaches the block engine), one another check refuses says which (`reason_ungated`).
/// `resume-sending` sends again; a stop closes the gate for good
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_pause_records_would_sends_and_sends_nothing() {
    use crate::control::{self, StopInfo, StopReason};
    let mut r = rig("ctl", Mode::Live, "").await;
    let sess = control::Session::new();
    sess.set_dir(r.dir.clone());
    r.x.set_gate(sess.gate.clone());
    let _srv = control::serve(sess.clone(), &r.dir).unwrap();
    let rep = control::send_command(&r.dir, "pause-sending", "moiz", "WP-05 control test").unwrap();
    assert_eq!((rep["accepted"].as_bool(), rep["send_gate"]["mode"].as_str()), (Some(true), Some("shadow")));
    let t = now_ns();
    let d = r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t);
    assert_eq!((d.verdict, d.reason.as_str(), d.would_send, d.sent, d.attempt, d.reason_ungated.clone()), ("reject", "gate_shadow:control", true, Some(false), Some(0), None));
    let d2 = r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t + 1);
    assert_eq!((d2.reason.as_str(), d2.would_send, d2.attempt, d2.reason_ungated.as_deref()), ("gate_shadow:control", false, None, Some("inflight_same_state")));
    assert!(control::send_command(&r.dir, "resume-sending", "moiz", "done").unwrap()["accepted"].as_bool().unwrap());
    assert_eq!(r.decide(route(3, damm(4, MINT), 50_000, 1), 100, t + 2).reason, "sent");
    sess.stopper.request(StopInfo::new(StopReason::Signal, "SIGINT"));
    assert_eq!(r.decide(route(5, damm(6, MINT), 50_000, 1), 100, t + 3).reason, "gate_stopped");
    let _ = r.settled().await;
    tokio::time::sleep(std::time::Duration::from_millis(20)).await;
    assert_eq!(r.got.lock().unwrap().len(), 1, "only the resumed decision reached the block engine");
    assert_eq!((r.n("reject_gate_shadow"), r.n("reject_gate_stopped"), r.n("would_send"), r.n("live_sent")), (2, 1, 2, 1));
    // review #16: what else refused a gated decision is `ungated_<reason>`: the `reject_*` counters sum to the refusals
    assert_eq!((r.n("ungated_inflight_same_state"), r.n("reject_inflight_same_state")), (1, 0));
    let rejects: u64 = r.x.counts.iter().filter(|(k, _)| k.starts_with("reject_")).map(|(_, v)| *v).sum();
    assert_eq!(rejects, r.x.status()["decisions"].as_u64().unwrap() - r.n("live_sent"), "one reject_* per refused decision");
    let a = r.lines("attempts");
    assert_eq!(a.iter().map(|l| (l["attempt"].as_u64().unwrap(), l["sent"].as_bool().unwrap())).collect::<Vec<_>>(), vec![(0, false), (1, true), (2, false)]);
    assert_eq!((a[0]["not_sent"].as_str(), a[2]["not_sent"].as_str(), a[0]["tx"]["sig"].as_str()), (Some("gate_shadow:control"), Some("gate_stopped"), None),
        "a would-send of a sending mode is not signed");
}

// ------------------------------------------------------------------------------------------------ settlement

/// PLAN WP-05 acceptance (settlement, stream-based): every block-engine result of our bundle reaches the engine as INPUT
/// 5 (a landing releases the in-flight entry); the wallet stream's record of our signature makes the attempt final
/// (`landed_ok`, its fee, CU and the route program's events, with the results in order); an expiry check that finds a
/// landing makes it landed (`statuses`), one that finds nothing `not_landed_expired`, and a landing seen later writes an
/// amend line; cross-checks are kept. Review WP-05 #3: a landing the expiry check found first counts the base fee and an
/// unknown round trip until its wallet record amends it (an amend line with its fee, CU and events; its round trip
/// counted then, its landing and tip once). A send the queue dropped is final at once and gives back its in-flight entry
/// and its big-band token
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn settlement_from_the_chain() {
    let mut r = rig("settle", Mode::Live, "").await;
    let t = now_ns();
    let mut sigs = Vec::new();
    for k in 0..3u8 {
        assert_eq!(r.decide(route(10 + 2 * k, damm(11 + 2 * k, MINT), 50_000, 1), 100, t).reason, "sent");
        let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
        assert_eq!(attempt, k as u64);
        sigs.push(fired.copies[0].sig.clone().unwrap());
        r.x.on_settled(Settled::Fired { attempt, fired }, now_ns(), &|_| None);
    }
    // the block engine's results of attempt 0's bundle (b0): accepted, then processed
    let j = r.jito.clone().unwrap();
    let res = |outcome: &'static str| Outcome { bundle: "b0".into(), outcome, slot: Some(101), index: (outcome == "processed").then_some(4), bid: None, detail: None,
        validator: Some(b58(&LJ)) };
    j.on_result_at(res("accepted"), t + 1);
    j.on_result_at(res("processed"), t + 2);
    let rel = r.releases();
    assert_eq!(rel.iter().map(|d| (d["attempt"].as_u64(), d["outcome"].as_str(), d["release"].as_bool(), d["seq"].as_u64())).collect::<Vec<_>>(),
        vec![(Some(0), Some("accepted"), Some(false), Some(0)), (Some(0), Some("processed"), Some(true), Some(1))]);
    let keys = r.x.inflight.len();
    for d in &rel { r.x.on_release(d, t + 3); }
    assert_eq!((r.x.inflight.len(), r.n("inflight_released")), (keys - 1, 1), "the landing released the entry");
    // attempt 0 lands (the wallet stream), with the route program's events
    let events = |back: u64| json!([{ "kind": "leg", "leg": 0 }, { "kind": "out", "leg": 0, "amount": 77 }, { "kind": "out", "leg": 1, "amount": back }]);
    r.x.on_wallet_tx(&json!({ "sig": sigs[0], "attempt": 0, "slot": 101, "idx": 12, "ok": true, "err": null, "fee": 5_000, "cu_consumed": 87_000,
        "prog_events": events(1_000_049_000) }), now_ns(), &|_| None);
    // a cross-check of attempt 1 (+2 s): nothing yet
    r.x.on_settled(Settled::Statuses { why: "check", at: vec![(1, "+2s")], result: Ok(vec![None]), t_ns: t }, t, &|_| None);
    // the expiry check: attempt 1 landed (the wallet stream missed it), attempt 2 did not
    let hit = SigStatus { slot: 102, err: None, confirmation: Some("confirmed".into()) };
    r.x.on_settled(Settled::Statuses { why: "expiry", at: vec![(1, "expiry"), (2, "expiry")], result: Ok(vec![Some(hit), None]), t_ns: t }, t, &|_| None);
    assert!(r.x.open_attempts().is_empty());
    // attempt 1 is a win whose fee and round trip only its wallet record has: the base fee is counted, the round trip is
    // unknown (the money says it is partial), the tip is counted once
    let money = |r: &Rig| { let (_, m) = r.x.status_v2(&mut ExecPrev::default()); m };
    let m = money(&r);
    assert_eq!((m["round_trip_total_lamports"].as_i64(), m["round_trip_unknown_total"].as_u64(), m["tips_paid_total_lamports"].as_u64(), m["fees_landed_total_lamports"].as_u64()),
        (Some(49_000), Some(1), Some(2 * 31_499), Some(10_000)));
    // attempt 2 landed after all (seen later): an amend line; its failed fee counts against the cap
    r.x.on_wallet_tx(&json!({ "sig": sigs[2], "attempt": 2, "slot": 140, "idx": 3, "ok": false, "err": { "InstructionError": [2, { "Custom": 1314390018u64 }] },
        "fee": 5_000 }), now_ns(), &|_| None);
    // attempt 1's wallet record comes after its final: it amends the fee, CU and events, and its round trip is counted
    r.x.on_wallet_tx(&json!({ "sig": sigs[1], "attempt": 1, "slot": 102, "idx": 7, "ok": true, "err": null, "fee": 5_000, "cu_consumed": 91_000,
        "prog_events": events(1_000_021_000) }), now_ns(), &|_| None);
    // a second copy of a wallet record changes nothing
    r.x.on_wallet_tx(&json!({ "sig": sigs[1], "attempt": 1, "slot": 102, "idx": 7, "ok": true, "err": null, "fee": 5_000, "cu_consumed": 91_000,
        "prog_events": events(1_000_021_000) }), now_ns(), &|_| None);
    let o = r.lines("outcomes");
    let by = |a: u64| o.iter().filter(|l| l["attempt"].as_u64() == Some(a)).cloned().collect::<Vec<_>>();
    let o0 = &by(0)[0];
    assert_eq!((o0["final"].as_str(), o0["final_src"].as_str(), o0["landed"]["slot"].as_u64(), o0["fee_lamports"].as_u64(), o0["cu_consumed"].as_u64()),
        (Some("landed_ok"), Some("wallet"), Some(101), Some(5_000), Some(87_000)));
    assert_eq!((o0["delivered"].clone(), o0["round_trip_on_chain"].as_i64(), o0["landed"]["leader_kind"].as_str()), (json!([77, 1_000_049_000u64]), Some(49_000), Some("jito")));
    assert_eq!(o0["verdicts"].as_array().map(|v| v.iter().map(|x| x["outcome"].as_str().unwrap().to_string()).collect::<Vec<_>>()),
        Some(vec!["accepted".to_string(), "processed".into()]), "every result, in order");
    assert_eq!((o0["processed"]["index"].as_u64(), o0["accepted"]["validator"].as_str(), o0["bundle"].as_str()), (Some(4), Some(b58(&LJ).as_str()), Some("b0")));
    let o1 = by(1);
    assert_eq!(o1.len(), 2, "the final line and the wallet record's amend");
    assert_eq!((o1[0]["final"].as_str(), o1[0]["final_src"].as_str(), o1[0]["landed"]["slot"].as_u64(), o1[0]["fee_lamports"].is_null()),
        (Some("landed_ok"), Some("statuses"), Some(102), true));
    assert_eq!(o1[0]["statuses_checks"].as_array().map(|a| a.iter().map(|c| c["at"].as_str().unwrap().to_string()).collect::<Vec<_>>()),
        Some(vec!["+2s".to_string(), "expiry".into()]));
    assert_eq!((o1[1]["amend"].as_bool(), o1[1]["amends"].as_str(), o1[1]["final_src"].as_str(), o1[1]["fee_lamports"].as_u64(), o1[1]["cu_consumed"].as_u64(),
        o1[1]["round_trip_on_chain"].as_i64()), (Some(true), Some("statuses"), Some("wallet"), Some(5_000), Some(91_000), Some(21_000)));
    let o2 = by(2);
    assert_eq!(o2.len(), 2);
    assert_eq!((o2[0]["final"].as_str(), o2[0]["final_src"].as_str(), o2[0]["amend"].as_bool()), (Some("not_landed_expired"), Some("expiry"), Some(false)));
    assert_eq!((o2[1]["final"].as_str(), o2[1]["amend"].as_bool(), o2[1]["amends"].as_str(), o2[1]["final_src"].as_str(), o2[1]["fee_lamports"].as_u64()),
        (Some("landed_fail"), Some(true), Some("not_landed"), Some("wallet"), Some(5_000)), "the amend line");
    assert_eq!((r.n("landed_ok"), r.n("not_landed_expired"), r.n("expiry_status_hit"), r.n("amended")), (2, 1, 1, 2));
    let (exec, m) = r.x.status_v2(&mut ExecPrev::default());
    assert_eq!((exec["landed_total"].as_u64(), exec["ok_total"].as_u64(), exec["sent_total"].as_u64(), m["failed_fees_total_lamports"].as_u64(), m["src"].as_str()),
        (Some(3), Some(2), Some(3), Some(5_000), Some("bot")), "each landing once");
    assert_eq!((m["round_trip_total_lamports"].as_i64(), m["round_trip_unknown_total"].as_u64(), m["tips_paid_total_lamports"].as_u64(), m["fees_landed_total_lamports"].as_u64()),
        (Some(49_000 + 21_000), Some(0), Some(2 * 31_499), Some(15_000)), "both winners' round trips and tips; every landed fee");
    // a send the rate queue dropped: final at once; its in-flight entry and its big-band token come back
    let big = 1_100_000;
    assert_eq!(r.decide(route(30, damm(31, MINT), big, 1), 100, t).reason, "sent");
    let Settled::Fired { attempt, fired: mut f } = r.settled().await else { panic!("a fire result") };
    assert_eq!(r.decide(route(30, damm(31, MINT), big, 1), 100, t + 1).reason, "inflight_same_state", "held while it is open");
    f.copies[0].t_sent = 0;
    f.copies[0].ok = false;
    f.copies[0].drop = Some("rate_queue_timeout");
    r.x.on_settled(Settled::Fired { attempt, fired: f }, now_ns(), &|_| None);
    let last = r.lines("outcomes").last().cloned().unwrap();
    assert_eq!((last["attempt"].as_u64(), last["final"].as_str(), last["final_src"].as_str(), last["error"].as_str()),
        (Some(attempt), Some("not_landed_refused"), Some("send"), Some("rate_queue_timeout")));
    assert_eq!(r.n("drop_rate_queue_timeout"), 1);
    assert_eq!(r.decide(route(30, damm(31, MINT), big, 1), 100, t + 2).reason, "sent", "the entry and the token came back");
}

/// Review WP-05 #3: a failed landing the expiry check found first counts against the failed-fee cap at once (the base
/// fee, what the bundle paid), and its wallet record replaces it by the fee recorded, without counting the landing twice
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_failed_landing_found_by_the_expiry_check_counts_against_the_cap() {
    let mut r = rig("settle-fail", Mode::Live, "[live]\nmax_failed_fees_lamports = 9000\n").await;
    let t = now_ns();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t).reason, "sent");
    let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
    let sig = fired.copies[0].sig.clone().unwrap();
    r.x.on_settled(Settled::Fired { attempt, fired }, t, &|_| None);
    let fail = SigStatus { slot: 102, err: Some(json!({ "InstructionError": [2, { "Custom": 1314390018u64 }] })), confirmation: Some("confirmed".into()) };
    r.x.on_settled(Settled::Statuses { why: "expiry", at: vec![(attempt, "expiry")], result: Ok(vec![Some(fail)]), t_ns: t }, t, &|_| None);
    let (_, m) = r.x.status_v2(&mut ExecPrev::default());
    assert_eq!((m["failed_fees_total_lamports"].as_u64(), m["fees_landed_total_lamports"].as_u64(), m["tips_paid_total_lamports"].as_u64()), (Some(5_000), Some(5_000), Some(0)));
    // 5,000 spent + 5,000 for the next send is over the 9,000 cap: the sender stops
    assert_eq!(r.decide(route(3, damm(4, MINT), 50_000, 1), 100, t + 1).reason, "fee_cap");
    assert_eq!(r.x.status()["stopped"].as_str(), Some("failed-fee cap reached"));
    // the wallet record then says 6,000 (the fee it really paid): it replaces the 5,000, the landing counts once
    r.x.on_wallet_tx(&json!({ "sig": sig, "attempt": attempt, "slot": 102, "idx": 1, "ok": false, "err": { "InstructionError": [2, { "Custom": 1314390018u64 }] },
        "fee": 6_000 }), now_ns(), &|_| None);
    let (exec, m) = r.x.status_v2(&mut ExecPrev::default());
    assert_eq!((m["failed_fees_total_lamports"].as_u64(), m["fees_landed_total_lamports"].as_u64(), exec["landed_total"].as_u64(), exec["ok_total"].as_u64()),
        (Some(6_000), Some(6_000), Some(1), Some(0)));
    let o = r.lines("outcomes");
    assert_eq!(o.iter().map(|l| (l["final_src"].as_str().unwrap().to_string(), l["amend"].as_bool().unwrap())).collect::<Vec<_>>(),
        vec![("statuses".to_string(), false), ("wallet".to_string(), true)]);
    assert_eq!(o[1]["failed_fees_total_lamports"].as_u64(), Some(6_000));
}

/// The executor's timers: the cross-checks fall due at +2 s, +10 s and +60 s (one batched getSignatureStatuses each);
/// once the chain passes the blockhash's validity (height + 150) the attempt is checked once more (with
/// `searchTransactionHistory`, F43) and the answer makes it final. With no RPC to ask, the check fails and the attempt is
/// `not_landed_expired`, the failure noted
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn expiry_and_cross_checks_from_the_timers() {
    let mut r = rig("expiry", Mode::Live, "").await;
    let t = now_ns();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t).reason, "sent");
    let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
    let t_sent = fired.copies[0].t_sent;
    r.x.on_settled(Settled::Fired { attempt, fired }, now_ns(), &|_| None);
    r.x.tick(t_sent + S, &r.view, 101);
    assert_eq!((r.n("status_check"), r.n("expiry_check")), (0, 0), "nothing due yet");
    r.x.tick(t_sent + 2 * S, &r.view, 102);
    assert_eq!(r.n("status_check"), 1, "the +2 s check");
    let Settled::Statuses { why, at, result, .. } = r.settled().await else { panic!("a statuses answer") };
    assert_eq!((why, at.clone(), result.is_err()), ("check", vec![(attempt, "+2s")], true), "no provider to ask");
    r.x.on_settled(Settled::Statuses { why, at, result, t_ns: t }, t, &|_| None);
    // the chain passes height 90 + 150
    r.view.on_block_meta(400, [1; 32], Some(241), t);
    r.x.tick(t_sent + 3 * S, &r.view, 400);
    assert_eq!(r.n("expiry_check"), 1);
    r.x.tick(t_sent + 4 * S, &r.view, 401);
    assert_eq!(r.n("expiry_check"), 1, "once");
    let s = r.settled().await;
    assert!(matches!(&s, Settled::Statuses { why: "expiry", .. }));
    r.x.on_settled(s, now_ns(), &|_| None);
    let o = r.lines("outcomes");
    assert_eq!((o.len(), o[0]["final"].as_str(), o[0]["final_src"].as_str()), (1, Some("not_landed_expired"), Some("expiry")));
    assert!(o[0]["error"].as_str().is_some_and(|e| e.contains("expiry check failed")), "{}", o[0]);
    assert_eq!(o[0]["statuses_checks"].as_array().map(|a| a.len()), Some(2));
    assert_eq!((o[0]["blockhash"]["valid_until_height"].as_u64(), o[0]["target_slot"].as_u64()), (Some(240), Some(101)));
    assert!(r.x.open_attempts().is_empty() && r.x.inflight.is_empty());
}

// ------------------------------------------------------------------------------------------------ with an engine

/// two AMM v4 pools on MINT / WSOL (1,000 and 1,010 SOL), in an offline engine
fn amm_engine() -> (crate::engine::Engine, PoolMeta, PoolMeta) {
    use crate::config::StrategyCfg;
    let amm = |n: u8| PoolMeta { venue: Venue::RayAmmV4, pool: [n; 32], t0: MINT, t1: *WSOL, vault0: [n + 10; 32], vault1: [n + 20; 32],
        t0_prog: *crate::pda::TOKEN_PROGRAM, t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![], flag: false };
    let pool_data: Arc<[u8]> = { let mut p = vec![0u8; 752]; p[0..8].copy_from_slice(&1u64.to_le_bytes()); p[176..184].copy_from_slice(&25u64.to_le_bytes());
        p[184..192].copy_from_slice(&10_000u64.to_le_bytes()); p.into() };
    let (a, b) = (amm(1), amm(2));
    let mut reg = crate::pools::Registry { pools: vec![a.clone(), b.clone()], by_pool: Default::default(), pairs: Default::default(), seeds: Default::default(), ours: Default::default() };
    reg.by_pool.insert(a.pool, 0);
    reg.by_pool.insert(b.pool, 1);
    reg.pairs.insert(crate::pools::pair_key(&MINT, &WSOL), vec![0, 1]);
    let mut store = crate::store::Store::default();
    for (m, sol) in [(&a, 1_000u64), (&b, 1_010)] {
        store.update(m.pool, pool_data.clone(), 10, 1, None);
        store.update(m.vault0, amm_vault(1_000_000_000_000_000), 10, 1, None);
        store.update(m.vault1, amm_vault(sol * 1_000_000_000), 10, 1, None);
    }
    (crate::engine::Engine::new_offline(Arc::new(reg), store, StrategyCfg { state_triggers: true, ..StrategyCfg::default() }), a, b)
}

fn amm_vault(amount: u64) -> Arc<[u8]> { let mut v = vec![0u8; 165]; v[64..72].copy_from_slice(&amount.to_le_bytes()); v.into() }

/// the stream delivers at `slot` and Tier A is complete (the warm-up gate opens, WP-04); the ring's head (slot 99) and
/// the schedule arrive as journaled inputs
fn amm_start(e: &mut crate::engine::Engine, t: &mut u64) {
    let mut status = |_: &str| {};
    e.step(Event::Slot { slot: 100, status: 0, t: *t, parent: Some(99), dead_error: None, bank_id: None }, *t, &mut status);
    e.step(Event::Input { kind: InputKind::BlockhashHead, data: Arc::new(json!({ "hash": b58(&BH), "slot": 99, "height": 89, "src": "slotidx",
        "commitment": "confirmed", "t_ns": *t })) }, *t, &mut status);
    e.step(Event::Input { kind: InputKind::LeaderWindow, data: Arc::new(window_json()) }, *t, &mut status);
    *t += 6_000_000;
    e.timers(*t, &mut status);
}

/// one transaction moving pool `m` to `sol` SOL at slot 100; its group resolves by quiescence at the timers 4 ms later
fn amm_move(e: &mut crate::engine::Engine, m: &PoolMeta, n: u8, sol: u64, t: &mut u64) {
    let mut status = |_: &str| {};
    let txn = [n + 50; 64];
    for (k, data) in [(m.vault1, amm_vault(sol * 1_000_000_000)), (m.vault0, amm_vault(1_000_000_000_000_000 - n as u64))] {
        *t += 1_000;
        e.step(Event::Account { slot: 100, pubkey: k, owner: [3; 32], lamports: 1, data, t: *t, txn: Some(txn), write_version: *t, is_startup: false,
            src: 0, aseq: 0, bank_id: None }, *t, &mut status);
    }
    *t += 4_000_000;
    e.timers(*t, &mut status);
}

/// the journal's decision-point records (INPUT 3 `gate`, `src` "decision")
fn decision_records(dir: &std::path::Path) -> Vec<(usize, Value)> {
    use crate::rec::journal::{self, JBody};
    journal::read_dir(dir).unwrap().iter().enumerate().filter_map(|(i, r)| match &r.body {
        JBody::Input { kind: 3, data } if data["src"] == "decision" => Some((i, data.clone())),
        _ => None,
    }).collect()
}

/// PLAN-ADDENDUM I-7: a shadow run with an engine runs every send check up to the signature. A decision that passes them
/// all but the SendGate is a would-send, recorded with `sent = false` in decisions.jsonl (with its attempt) and in
/// attempts.jsonl (built, unsigned); one another check refuses says which (`reason_ungated`). What each decision saw from
/// outside (the gate, the leader's kind, the token, the recorder) is journaled at the decision when it changes (WP-08
/// review #18): the leader's kind reaches replay. Review WP-05 #9: decisions.jsonl `band` is the attempt's (the
/// executor's, at the size it would trade), the engine's at its priced size is `band_at_opp`; #8: the engine notes each
/// attempt in the `poh_trigger_pct` gauge after the decision
#[tokio::test]
async fn a_shadow_run_records_would_sends() {
    let mut r = rig("shadow-engine", Mode::Shadow, "[send_policy]\nbig_band_max_per_sec = 1000\n").await;
    let gate = SendGate::new();
    let _ = gate.shadow("mode_shadow", "no --live or --canary: nothing is sent", true);
    let (mut e, a, b) = amm_engine();
    e.set_rec(r.rec.clone());
    let mut x = std::mem::replace(&mut r.x, idle_exec());
    x.set_gate(gate);
    x.set_health(e.health_flags());
    e.exec = Some(x);
    let mut t = now_ns();
    amm_start(&mut e, &mut t);
    amm_move(&mut e, &a, 0, 1_030, &mut t);
    amm_move(&mut e, &b, 1, 1_060, &mut t);
    // the third one while the target slot's leader is of another kind (a new window, journaled; the LeaderBook agrees)
    let mut status = |_: &str| {};
    e.step(Event::Input { kind: InputKind::LeaderWindow, data: Arc::new(json!({ "start": 101, "leaders": [b58(&LO)] })) }, t, &mut status);
    r.book.add_window(101, &[LO]);
    amm_move(&mut e, &a, 2, 1_090, &mut t);
    r.rec.sync();
    let d: Vec<Value> = rec::read_jsonl(&r.dir, "decisions").unwrap().into_iter().filter(|l| l["opp"].is_u64()).collect();
    assert_eq!(d.len(), 3, "{d:?}");
    for l in &d[..2] {
        assert_eq!((l["verdict"].as_str(), l["reason"].as_str(), l["would_send"].as_bool(), l["sent"].as_bool()),
            (Some("reject"), Some("gate_shadow:mode_shadow"), Some(true), Some(false)), "{l}");
        assert!(l["attempt"].is_u64() && l["reason_ungated"].is_null() && l["ev"].is_i64() && l["crowding"]["src"].as_str() == Some("map_partial"), "{l}");
    }
    assert_eq!((d[2]["would_send"].as_bool(), d[2]["reason_ungated"].as_str(), d[2]["attempt"].is_null(), d[2]["sent"].is_null()),
        (Some(false), Some("leader_skip_kind"), true, true), "{}", d[2]);
    let att = rec::read_jsonl(&r.dir, "attempts").unwrap();
    assert_eq!(att.len(), 2);
    for (k, l) in att.iter().enumerate() {
        assert_eq!((l["kind"].as_str(), l["sent"].as_bool(), l["not_sent"].as_str(), l["tx"]["sig"].is_null()), (Some("shadow"), Some(false), Some("gate_shadow:mode_shadow"), true));
        assert_eq!((l["attempt"].as_u64(), l["decision"].clone(), l["blockhash"]["slot"].as_u64(), l["blockhash"]["age_slots"].as_u64(), l["leader"]["kind"].as_str()),
            (Some(k as u64), d[k]["decision"].clone(), Some(99), Some(1), Some("jito")));
        assert!(l["tx"]["bytes"].as_u64().unwrap() <= build::MAX_TX_BYTES as u64 && l["dry_run"].is_null(), "built, not signed");
        assert!(l["tip"]["lamports"].as_u64().unwrap() >= 1_000 && l["min_profit_onchain"].as_u64().unwrap() > l["tip"]["lamports"].as_u64().unwrap());
        assert_eq!((d[k]["band"].as_u64(), d[k]["band_at_opp"].is_u64()), (l["band"].as_u64(), true), "the band the attempt was queued and tipped by");
        assert_eq!(l["band"].as_u64(), Some(crate::bands::of_gross(l["expected"]["gross"].as_i64().unwrap()) as u64));
    }
    assert_eq!(r.gauge.status(&[], now_ns())["attempts_total"].as_u64(), Some(2), "the engine noted both attempts' triggers");
    let x = e.exec.as_ref().unwrap();
    assert_eq!((x.counts.get("would_send").copied(), x.counts.get("reject_gate_shadow").copied(), x.net_calls()), (Some(2), Some(3), 0));
    r.rec.close();
    let seen: Vec<(String, String, bool)> = decision_records(&r.dir).into_iter()
        .map(|(_, d)| (d["mode"].as_str().unwrap().to_string(), d["leader"]["kind"].as_str().unwrap().to_string(), d["jito_token_ok"].as_bool().unwrap())).collect();
    assert_eq!(seen, vec![("shadow".into(), "jito".into(), true), ("shadow".into(), "other".into(), true)], "one record per change");
}

/// review WP-03 #3, on the WP-05 executor: the SendGate mode each send check saw is journaled on the engine thread at the
/// decision (INPUT gate, `src` "decision", with the opportunity) whenever it differs from the last one journaled; the
/// live gate still decides (a pause closes the very next check; the first decision was sent)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_gate_each_send_check_saw_is_journaled() {
    use crate::rec::journal::{self, JBody};
    let mut r = rig("gatej", Mode::Live, "[send_policy]\nbig_band_max_per_sec = 1000\n").await;
    let gate = SendGate::new();
    let (mut e, a, b) = amm_engine();
    e.set_rec(r.rec.clone());
    let mut x = std::mem::replace(&mut r.x, idle_exec());
    x.set_gate(gate.clone());
    x.set_health(e.health_flags());
    e.exec = Some(x);
    let mut t = now_ns();
    amm_start(&mut e, &mut t);
    amm_move(&mut e, &a, 0, 1_030, &mut t);
    gate.shadow("control", "pause-sending by test", false).unwrap();
    amm_move(&mut e, &b, 1, 1_060, &mut t);
    amm_move(&mut e, &a, 2, 1_090, &mut t);
    let x = e.exec.as_ref().unwrap();
    assert_eq!((x.counts.get("reject_gate_shadow").copied(), x.gate_seen()), (Some(2), Some(GateMode::Shadow)), "the live gate decided the last two");
    assert_eq!(x.counts.get("live_sent").copied(), Some(1), "the first was sent");
    let _ = r.settled().await;
    assert_eq!(r.got.lock().unwrap().len(), 1);
    r.rec.close();
    let recs = decision_records(&r.dir);
    assert_eq!(recs.iter().map(|(_, d)| (d["mode"].as_str().unwrap().to_string(), d["opp"].as_u64().unwrap())).collect::<Vec<_>>(),
        vec![("live".to_string(), 0), ("shadow".to_string(), 1)], "one record per change, at the decision that saw it");
    let (i, d) = &recs[1];
    assert_eq!((d["reason"].as_str(), d["leader"]["kind"].as_str(), d["jito_token_ok"].as_bool(), d["recorder_ok"].as_bool()),
        (Some("control"), Some("jito"), Some(true), Some(true)));
    let j = journal::read_dir(&r.dir).unwrap();
    assert!(matches!(j[i - 1].body, JBody::Timer { .. }) && j[i - 1].t_engine == j[*i].t_engine, "{:?}", j[i - 1]);
}

// ------------------------------------------------------------------------------------------------ the dry run

/// Go-live gate item 4: a dry run builds and signs at least 100 would-send bundles and sends none. Each is recorded in
/// full (the signed transaction, its size, tip and accounts, the checks it passed); its signature is the throwaway key's
/// (it verifies with that key and not with the payer's: it could not land even if it left). Transmitting is impossible: a
/// dry-run executor refuses send paths at its start (`exec_new_refuses_what_its_mode_forbids`), drops any it is handed,
/// holds no Jito client and no trading key; the in-memory block engine behind the paths it was handed receives nothing;
/// the send path makes no network call. The would-sends follow the bundle path's rate (5 a second)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_dry_run_signs_and_never_sends() {
    let mut r = rig("dry", Mode::DryRun, "").await;
    // send paths to a block engine in memory, handed to a dry-run executor anyway
    let j = Jito::for_test(Rec::off());
    j.set_cached(Some(fresh_token()));
    let got = fake_engine(&j);
    let paths = Paths::for_test(vec![Path::test_bundle(j.clone(), Some(5), 10)], Rec::off());
    let (tx, rx) = crossbeam_channel::unbounded();
    let held: HashSet<Pk> = [*WSOL, MINT].into_iter().collect();
    let mut x = Exec::assemble(&test_cfg(&r.dir, ""), Rpc::race(vec![]), Some(paths), r.rec.clone(), tx, vec![], vec![], None, held, Mode::DryRun, Some(dry_key())).unwrap();
    assert!(x.paths.is_none() && x.bundle_path.is_none() && x.jito.is_none() && x.key.is_none(), "no path, no block engine, no trading key");
    assert_eq!(x.dry_signer(), Some(dry_key().verifying_key().to_bytes()));
    x.set_health(r.health.clone());
    x.set_leaders(r.book.clone());
    x.poh_gauge = r.gauge;
    r.x = x;
    assert!(r.x.gate.allows(), "the gate is open: still nothing may leave");
    let payer = wallet_key().verifying_key().to_bytes();
    let signer = dry_key().verifying_key();
    let tips = tip_accounts();
    let mut t = now_ns();
    for k in 0..120u64 {
        let n = (k % 50) as u8 * 2 + 1;
        let d = r.decide(route(n, damm(n + 1, MINT), 50_000 + k * 1_000, k), 100, t);
        assert_eq!((d.would_send, d.sent, d.reason.as_str(), d.attempt), (true, Some(false), "would_send", Some(k)), "{k}: {d:?}");
        t += S / 4;
    }
    tokio::time::sleep(std::time::Duration::from_millis(50)).await;
    assert!(got.lock().unwrap().is_empty(), "nothing reached the block engine");
    assert_eq!(r.x.net_calls(), 0, "no network call");
    assert!(rx.try_iter().all(|e| !matches!(e, Event::Settled(_))), "nothing was fired");
    let a = r.lines("attempts");
    assert_eq!(a.len(), 120);
    for l in &a {
        assert_eq!((l["kind"].as_str(), l["sent"].as_bool(), l["not_sent"].as_str()), (Some("dry_run"), Some(false), Some("dry_run")));
        let dr = &l["dry_run"];
        assert_eq!((dr["checks_ok"].as_bool(), dr["signer"].as_str(), dr["simulated"].as_bool()), (Some(true), Some(b58(&signer.to_bytes()).as_str()), Some(false)), "{dr}");
        let raw = { use base64::Engine as _; base64::engine::general_purpose::STANDARD.decode(dr["tx_b64"].as_str().unwrap()).unwrap() };
        assert_eq!((Some(raw.len() as u64), dr["bytes"].as_u64()), (l["tx"]["bytes"].as_u64(), Some(raw.len() as u64)), "the size as built");
        assert!(raw.len() <= build::MAX_TX_BYTES);
        let names: Vec<&str> = dr["checks"].as_array().unwrap().iter().map(|c| c["check"].as_str().unwrap()).collect();
        assert_eq!(names, ["parses", "one_signature", "signature_verifies", "payer_is_wallet", "size", "accounts_resolve", "locks", "blockhash", "cu_limit", "no_cu_price",
            "tip_last", "tip_to_jito", "tip_check", "route_program", "pools_named", "route_data", "route_amount_in", "route_min_profit", "min_profit_covers_tip",
            "route_accounts"]);
        // the route as signed: the decision's size and on-chain min_profit (review #12)
        let route = dr["checks"].as_array().unwrap().iter().find(|c| c["check"] == "route_min_profit").unwrap();
        assert_eq!((route["detail"]["signed"].as_u64(), l["min_profit_onchain"].as_u64()), (route["detail"]["want"].as_u64(), route["detail"]["want"].as_u64()));
        // the tip as recorded is what the transaction pays to a Jito tip account, last
        let (tx, _) = crate::tx::parse_wire(&raw).unwrap();
        assert_eq!(send::tip_paid(&tx, &tips), l["tip"]["lamports"].as_u64().unwrap());
        assert_eq!((tx.keys[0], tx.num_signers), (payer, 1), "the payer is the wallet, the only signer");
        let accts = dr["accounts"].as_array().unwrap();
        assert_eq!((accts[0]["key"].as_str(), accts[0]["signer"].as_bool(), accts[0]["writable"].as_bool()), (Some(b58(&payer).as_str()), Some(true), Some(true)));
        assert_eq!(accts.iter().filter(|x| x["signer"] == json!(true)).count(), 1);
        // the signature is the throwaway key's, never the payer's: it cannot pass on chain
        use ed25519_dalek::Verifier;
        let sig = ed25519_dalek::Signature::from_bytes(raw[1..65].try_into().unwrap());
        assert!(signer.verify(&raw[65..], &sig).is_ok());
        assert!(ed25519_dalek::VerifyingKey::from_bytes(&payer).unwrap().verify(&raw[65..], &sig).is_err());
        assert_eq!(l["tx"]["sig"].as_str(), c_sig(&raw).as_deref());
    }
    assert_eq!((r.n("dry_run_ok"), r.n("dry_run_check_failed"), r.n("would_send")), (120, 0, 120));
    // the bundle path's rate: of 7 would-sends in one instant, 5 go and 2 are refused by the rate model (`would_rate`, not
    // the queue's own `rate_queue_timeout`: review #10)
    t += 2 * S;
    let reasons: Vec<String> = (0..7u64).map(|k| r.decide(route(101, damm(102, MINT), 50_000, 1_000 + k), 100, t).reason).collect();
    assert_eq!(reasons.iter().filter(|x| *x == "would_send").count(), 5, "{reasons:?}");
    assert_eq!(reasons.iter().filter(|x| *x == "would_rate").count(), 2, "{reasons:?}");
    let mut c = route(105, damm(106, MINT), 50_000, 2_000);
    c.crowding = Crowding { signers_6h: None, bucket: 2, src: "static_list" };
    assert_eq!(r.decide(c, 100, t).reason, "would_rate_crowded", "a crowded route over the modelled rate");
    // a signed would-send whose bytes were tampered with fails its checks
    let raw = { use base64::Engine as _; base64::engine::general_purpose::STANDARD.decode(a[0]["dry_run"]["tx_b64"].as_str().unwrap()).unwrap() };
    let mut bad = raw.clone();
    let (ptx, _) = crate::tx::parse_wire(&raw).unwrap();
    bad[65 + 4 + 1 + 32 * ptx.keys.len()] ^= 1;
    let tip0 = (pk(a[0]["tip"]["account"].as_str().unwrap()), a[0]["tip"]["lamports"].as_u64().unwrap());
    let want = VerifyWant { signer: signer.to_bytes(), ..live_want(&r.x, Some(tip0), a[0]["min_profit_onchain"].as_u64().unwrap()) };
    assert!(verify_bundle(&raw, &want).iter().all(|c| c["ok"] == json!(true)));
    let failed: Vec<String> = verify_bundle(&bad, &want).iter().filter(|c| c["ok"] != json!(true)).map(|c| c["check"].as_str().unwrap().to_string()).collect();
    assert_eq!(failed, ["signature_verifies", "blockhash"], "one bit of the blockhash");
}

/// The dry run from its start (`Exec::new`, through a local mock RPC): it reads accounts (the lookup tables, PumpSwap's
/// GlobalConfig, the wallet's token accounts) and, with `[dry_run] simulate`, simulates its signed would-sends read-only
/// (`simulateTransaction`, sigVerify off: the throwaway key is not the payer; the blockhash kept, so its age is checked),
/// at most `max_sim_per_sec` a second. It calls no method that sends. Each simulation is written to sims.jsonl with its
/// attempt; none is on the send path (its network-call counter stays 0)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_dry_run_reads_and_simulates_only() {
    let m = crate::rpc::mock::MockRpc::start();
    m.slot.store(500, Relaxed);
    let payer = wallet_key().verifying_key().to_bytes();
    for mint in [*WSOL, MINT] { m.set(build::ata_of(&payer, &mint, &crate::pda::TOKEN_PROGRAM), &[0u8; 165]); }
    let dir = test_dir("dry-sim");
    let rec = test_rec(&dir);
    let cfg = test_cfg(&dir, "[exec]\nrpc = [\"mock\"]\n[dry_run]\nsimulate = true\nmax_sim_per_sec = 2\n");
    let rpc = Rpc::race(vec![crate::rpc::Endpoint { name: "mock".into(), url: m.url.clone(), bearer: None }]);
    let (tx, rx) = crossbeam_channel::unbounded();
    let (x, notes) = Exec::new(&cfg, &rpc, None, rec.clone(), tx, vec![], Mode::DryRun, Some(dry_key()), vec![(MINT, *crate::pda::TOKEN_PROGRAM)]).await.unwrap();
    assert!(notes.iter().any(|n| n.starts_with("DRY RUN") && n.contains("simulated read-only")), "{notes:?}");
    let mut held = vec![b58(&WSOL), b58(&MINT)];
    held.sort();
    assert_eq!(x.held_mints(), held);
    let mut r = Rig { x, dir, rec, rx, got: Got::default(), jito: None, view: view(), health: Arc::new(HealthFlags::default()), gauge: Box::leak(Box::new(PohGauge::new())),
        book: book(), buffered: Vec::new() };
    r.health.set(Shut::Ready);
    r.x.set_health(r.health.clone());
    r.x.set_leaders(r.book.clone());
    r.x.poh_gauge = r.gauge;
    let t = now_ns();
    for k in 0..3u8 { assert_eq!(r.decide(route(1 + 2 * k, damm(2 + 2 * k, MINT), 50_000, 1), 100, t).reason, "would_send"); }
    let mut sims = Vec::new();
    for _ in 0..2 {
        let Settled::DrySim { attempt, line } = r.settled().await else { panic!("a dry run's simulation") };
        sims.push(attempt);
        r.x.on_settled(Settled::DrySim { attempt, line }, now_ns(), &|_| None);
    }
    sims.sort();
    assert_eq!(sims, vec![0, 1], "at most 2 a second");
    let a = r.lines("attempts");
    assert_eq!(a.iter().map(|l| l["dry_run"]["simulated"].as_bool().unwrap()).collect::<Vec<_>>(), vec![true, true, false]);
    let s = r.lines("sims");
    assert_eq!(s.len(), 2);
    assert!(s.iter().all(|l| l["src"] == "dry_run" && l["sim_slot"] == 500 && l["sim_error"].is_null() && l["attempt"].is_u64()), "{s:?}");
    // the RPC calls: account reads at the start, then two read-only simulations of the signed would-sends
    let reqs = m.reqs.lock().unwrap().clone();
    let methods: Vec<&str> = reqs.iter().map(|q| q["method"].as_str().unwrap()).collect();
    assert!(methods.iter().all(|x| *x == "getMultipleAccounts" || *x == "simulateTransaction"), "{methods:?}");
    let sim_reqs: Vec<&Value> = reqs.iter().filter(|q| q["method"] == "simulateTransaction").collect();
    assert_eq!(sim_reqs.len(), 2);
    for q in &sim_reqs {
        assert_eq!((q["params"][1]["sigVerify"].as_bool(), q["params"][1]["replaceRecentBlockhash"].as_bool()), (Some(false), Some(false)));
        assert!(a.iter().any(|l| l["dry_run"]["tx_b64"] == q["params"][0]), "the would-send as recorded");
        let raw = { use base64::Engine as _; base64::engine::general_purpose::STANDARD.decode(q["params"][0].as_str().unwrap()).unwrap() };
        assert_eq!(crate::tx::parse_wire(&raw).unwrap().0.keys[0], payer);
    }
    assert_eq!(r.x.net_calls(), 0, "the simulations run after the decision, off the send path");
}

// ------------------------------------------------------------------------------------------------ review WP-05 fixes

/// A live executor like the rig's whose in-memory block engine answers with `engine` (it may refuse, or not answer)
fn with_engine(r: &mut Rig, engine: Arc<crate::send::jito::FakeEngine>) -> Arc<Jito> {
    let j = Jito::for_test(r.rec.clone());
    j.set_cached(Some(fresh_token()));
    j.set_fake_result(engine);
    let cfg = test_cfg(&r.dir, "");
    let paths = Paths::for_test(vec![Path::test_bundle(j.clone(), Some(5), cfg.send_policy.queue_ms)], r.rec.clone());
    let (tx, rx) = crossbeam_channel::unbounded();
    let held: HashSet<Pk> = [*WSOL, MINT].into_iter().collect();
    let mut x = Exec::assemble(&cfg, Rpc::race(vec![]), Some(paths), r.rec.clone(), tx, vec![], vec![], None, held, Mode::Live, Some(wallet_key())).unwrap();
    x.set_health(r.health.clone());
    x.set_leaders(r.book.clone());
    x.poh_gauge = r.gauge;
    r.x = x;
    r.rx = rx;
    r.jito = Some(j.clone());
    j
}

/// Review WP-05 #2: final means a landing or the blockhash's expiry (PLAN WP-07). A block-engine result that is not a
/// landing (would-fail, lost auction, dropped, rejected), through the Jito client's sink as the engine gets it, keeps
/// the in-flight entry: the same state version goes neither to the same leader at the same slot nor at its later slot
/// until the hold ends; a landing (`processed`) releases it. One bundle's several would-fails count once toward its
/// token's cooling
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_would_fail_keeps_the_lock() {
    let mut r = rig("wf-lock", Mode::Live, "").await;
    let t = now_ns();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 100, t).reason, "sent");
    let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
    r.x.on_settled(Settled::Fired { attempt, fired }, t, &|_| None);
    let j = r.jito.clone().unwrap();
    let res = |outcome: &'static str, detail: Option<&str>| Outcome { bundle: "b0".into(), outcome, slot: Some(101), index: None, bid: None, detail: detail.map(String::from),
        validator: None };
    for (o, d) in [("accepted", None), ("would-fail", Some("custom program error: 0x4e580002")), ("would-fail", Some("custom program error: 0x4e580002")),
        ("lost-auction", None), ("dropped", None), ("rejected", Some("boom"))] {
        j.on_result_at(res(o, d), t + 1);
    }
    let rel = r.releases();
    assert_eq!(rel.len(), 6);
    assert!(rel.iter().all(|d| d["release"] == json!(false)), "{rel:?}");
    for d in &rel { r.x.on_release(d, t + 2); }
    assert_eq!((r.x.inflight.len(), r.n("inflight_released")), (1, 0), "nothing released the entry");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 100, t + 3).reason, "inflight_same_state", "the same state, leader and slot");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 101, t + 4).reason, "sent", "the next slot's leader is another (BAM): allowed, as planned");
    let Settled::Fired { attempt: a1, fired } = r.settled().await else { panic!("a fire result") };
    r.x.on_settled(Settled::Fired { attempt: a1, fired }, t, &|_| None);
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 102, t + 5).reason, "inflight_same_leader");
    assert_eq!((r.x.mint_cool.get(&MINT).map(|c| c.0), r.n("cool_repeat"), r.n("verdict_would_fail")), (Some(1), 1, 2), "one would-fail for the attempt");
    // the hold ends 2 slots past the target slot: the same state may go again
    r.x.tick(t + 6, &r.view, 104);
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 7), 104, t + 7).reason, "sent", "the hold passed");
    // a landing releases its entry at once
    let Settled::Fired { attempt: a2, fired } = r.settled().await else { panic!("a fire result") };
    assert_eq!((a1, a2), (1, 2));
    r.x.on_settled(Settled::Fired { attempt: a2, fired }, t, &|_| None);
    let b = r.x.open.get(&a2).and_then(|o| o.bundle.clone()).unwrap();
    j.on_result_at(Outcome { bundle: b, outcome: "processed", slot: Some(103), index: Some(1), bid: None, detail: None, validator: None }, t + 8);
    let rel = r.releases();
    assert_eq!(rel.iter().map(|d| (d["outcome"].as_str(), d["release"].as_bool())).collect::<Vec<_>>(), vec![(Some("processed"), Some(true))]);
    let before = r.x.inflight.len();
    r.x.on_release(&rel[0], t + 9);
    assert_eq!((r.x.inflight.len(), r.n("inflight_released")), (before - 1, 1));
}

/// Review WP-05 #7: a copy that left but got no answer (a timeout, a transport error) may still land. It stays open (its
/// in-flight entry and its fee reservation kept), is cross-checked and settled by its landing or its blockhash's expiry,
/// with the send error on its final line. A copy the block engine refused (it answered) cannot land: final at once,
/// its entry and reservation given back
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_send_without_an_answer_stays_open() {
    let mut r = rig("no-answer", Mode::Live, "").await;
    let calls = Arc::new(AtomicU64::new(0));
    let c2 = calls.clone();
    let _j = with_engine(&mut r, Arc::new(move |_txs: &[&[u8]]| match c2.fetch_add(1, Relaxed) {
        0 | 1 => Err(crate::send::jito::BundleError::Other(anyhow::anyhow!("/searcher.SearcherService/SendBundle: Unavailable transport error"))),
        _ => Err(crate::send::jito::BundleError::Refused(anyhow::anyhow!("/searcher.SearcherService/SendBundle: ResourceExhausted rate limited"))),
    }));
    let t = now_ns();
    let mut sigs = Vec::new();
    for k in 0..2u8 {
        assert_eq!(r.decide(route(1 + 2 * k, damm(2 + 2 * k, MINT), 50_000, 1), 100, t).reason, "sent");
        let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
        let c = &fired.copies[0];
        assert!(!c.ok && c.t_sent > 0 && c.t_ack == 0 && c.drop.is_none(), "it left, no answer: {c:?}");
        sigs.push(c.sig.clone().unwrap());
        r.x.on_settled(Settled::Fired { attempt, fired }, t, &|_| None);
    }
    assert_eq!((r.x.open_attempts(), r.x.reserved, r.n("send_unanswered"), r.n("not_landed_refused")), (vec![0, 1], 2 * 5_000, 2, 0), "open, reserved");
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t + 1).reason, "inflight_same_state", "its entry holds");
    // attempt 0 had arrived after all: the wallet stream records it
    r.x.on_wallet_tx(&json!({ "sig": sigs[0], "attempt": 0, "slot": 101, "idx": 2, "ok": true, "err": null, "fee": 5_000, "cu_consumed": 80_000,
        "prog_events": [{ "kind": "out", "leg": 0, "amount": 9 }, { "kind": "out", "leg": 1, "amount": 1_000_020_000u64 }] }), now_ns(), &|_| None);
    // attempt 1 did not: its blockhash expires, the expiry check finds nothing
    r.x.on_settled(Settled::Statuses { why: "expiry", at: vec![(1, "expiry")], result: Ok(vec![None]), t_ns: t }, t, &|_| None);
    let o = r.lines("outcomes");
    assert_eq!((o[0]["final"].as_str(), o[0]["final_src"].as_str(), o[0]["round_trip_on_chain"].as_i64()), (Some("landed_ok"), Some("wallet"), Some(20_000)));
    assert_eq!((o[1]["final"].as_str(), o[1]["final_src"].as_str()), (Some("not_landed_expired"), Some("expiry")));
    assert!(o[1]["error"].as_str().is_some_and(|e| e.starts_with("send:") && e.contains("Unavailable")), "{}", o[1]);
    assert_eq!(r.x.reserved, 0);
    // a refusal (the block engine answered): final at once, the entry and the reservation back
    assert_eq!(r.decide(route(5, damm(6, MINT), 50_000, 1), 100, t + 2).reason, "sent");
    let Settled::Fired { attempt, fired } = r.settled().await else { panic!("a fire result") };
    let c = &fired.copies[0];
    assert!(!c.ok && c.t_sent > 0 && c.t_ack > 0 && c.drop.is_none(), "answered: {c:?}");
    r.x.on_settled(Settled::Fired { attempt, fired }, t, &|_| None);
    let last = r.lines("outcomes").last().cloned().unwrap();
    assert_eq!((last["final"].as_str(), last["final_src"].as_str()), (Some("not_landed_refused"), Some("send")));
    assert!(last["error"].as_str().is_some_and(|e| e.contains("ResourceExhausted")), "{last}");
    assert_eq!((r.x.reserved, r.n("send_refused"), r.x.never_left), (0, 1, 0));
    assert_eq!(r.decide(route(5, damm(6, MINT), 50_000, 1), 100, t + 3).reason, "sent", "the entry came back");
}

/// Review WP-05 #12 (go-live gate item 4): the dry run decodes the route instruction from the signed bytes. A builder
/// that signs a min_profit other than the decision's (here 1: a landed bundle could lose its tip and fee) or another
/// amount_in fails the dry run's checks, while every other check passes; the attempt records which
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_dry_run_catches_a_wrong_min_profit() {
    let mut r = rig("dry-mp", Mode::DryRun, "").await;
    let t = now_ns();
    let failed = |l: &Value| l["dry_run"]["checks"].as_array().unwrap().iter().filter(|c| c["ok"] != json!(true)).map(|c| c["check"].as_str().unwrap().to_string()).collect::<Vec<_>>();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t).reason, "would_send");
    let good = r.lines("attempts")[0].clone();
    assert_eq!((good["dry_run"]["checks_ok"].as_bool(), failed(&good)), (Some(true), Vec::<String>::new()));
    let mp = good["min_profit_onchain"].as_u64().unwrap();
    assert_eq!(mp, 31_499 + 5_000 + 1, "the tip (70% of the 45,000 edge) + the base fee + the margin floor");
    // the builder signs min_profit 1
    r.x.fault_route = Some((1_000_000_000, 1));
    assert_eq!(r.decide(route(3, damm(4, MINT), 50_000, 1), 100, t + S).reason, "would_send");
    let bad = r.lines("attempts")[1].clone();
    assert_eq!((bad["min_profit_onchain"].as_u64(), bad["dry_run"]["checks_ok"].as_bool()), (Some(mp), Some(false)), "the decision's value is recorded, the signed one is not it");
    assert_eq!(failed(&bad), ["route_min_profit", "min_profit_covers_tip"]);
    let c = bad["dry_run"]["checks"].as_array().unwrap().iter().find(|c| c["check"] == "route_min_profit").unwrap().clone();
    assert_eq!((c["detail"]["signed"].as_u64(), c["detail"]["want"].as_u64()), (Some(1), Some(mp)));
    // the builder signs another amount
    r.x.fault_route = Some((999_999_999, mp));
    assert_eq!(r.decide(route(5, damm(6, MINT), 50_000, 1), 100, t + 2 * S).reason, "would_send");
    assert_eq!(failed(&r.lines("attempts")[2]), ["route_amount_in"]);
    assert_eq!((r.n("dry_run_ok"), r.n("dry_run_check_failed")), (1, 2));
    // a signed min_profit that is the decision's but does not cover the tip, the fee and the margin is caught too
    let raw = { use base64::Engine as _; base64::engine::general_purpose::STANDARD.decode(good["dry_run"]["tx_b64"].as_str().unwrap()).unwrap() };
    let tip0 = (pk(good["tip"]["account"].as_str().unwrap()), good["tip"]["lamports"].as_u64().unwrap());
    let want = VerifyWant { signer: dry_key().verifying_key().to_bytes(), margin_floor: 2, ..live_want(&r.x, Some(tip0), mp) };
    let names: Vec<String> = verify_bundle(&raw, &want).iter().filter(|c| c["ok"] != json!(true)).map(|c| c["check"].as_str().unwrap().to_string()).collect();
    assert_eq!(names, ["min_profit_covers_tip"]);
    // the same bytes with min_profit set to 1 and signed again (a valid signature over a wrong value): caught
    let mut bad = raw.clone();
    let (tx, _) = crate::tx::parse_wire(&raw).unwrap();
    let ix = tx.ixs.iter().find(|ix| tx.keys[ix.program as usize] == r.x.program).unwrap();
    let at = raw.windows(ix.data.len()).position(|w| w == &ix.data[..]).unwrap();
    bad[at + 10..at + 18].copy_from_slice(&1u64.to_le_bytes());
    use ed25519_dalek::Signer;
    let sig = dry_key().sign(&bad[65..]).to_bytes();
    bad[1..65].copy_from_slice(&sig);
    let want = VerifyWant { signer: dry_key().verifying_key().to_bytes(), ..live_want(&r.x, Some(tip0), mp) };
    let names: Vec<String> = verify_bundle(&bad, &want).iter().filter(|c| c["ok"] != json!(true)).map(|c| c["check"].as_str().unwrap().to_string()).collect();
    assert_eq!(names, ["route_min_profit", "min_profit_covers_tip"], "the signature verifies; the signed value is wrong");
}

/// Review WP-05 #16: a canary attempt whose copy never left (the rate queue dropped it) is not one of the canary's
/// `count` attempts
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_dropped_canary_send_is_not_counted() {
    let mut r = rig("canary-drop", Mode::Canary, "[canary]\nenabled = true\ncount = 2\nevery_ms = 1000\nsize_sol = 0.05\nmax_spend_lamports = 20000\n").await;
    let t = now_ns();
    assert_eq!(r.decide(route(1, damm(2, MINT), 50_000, 1), 100, t).reason, "sent");
    let Settled::Fired { attempt, fired: mut f } = r.settled().await else { panic!("a fire result") };
    f.copies[0].t_sent = 0;
    f.copies[0].ok = false;
    f.copies[0].drop = Some("rate_queue_timeout");
    r.x.on_settled(Settled::Fired { attempt, fired: f }, t, &|_| None);
    assert_eq!(r.decide(route(3, damm(4, MINT), 50_000, 1), 100, t + S + 1).reason, "sent");
    assert_eq!(r.decide(route(5, damm(6, MINT), 50_000, 1), 100, t + 2 * S + 2).reason, "sent", "the dropped one did not count");
    assert_eq!(r.decide(route(7, damm(8, MINT), 50_000, 1), 100, t + 3 * S + 3).reason, "canary_count");
    assert_eq!((r.x.never_left, r.n("drop_rate_queue_timeout"), r.n("canary_sent")), (1, 1, 3));
}

/// Review WP-05 #15, #10, #16: the round trip is the last leg's output (any number of legs); the reasons and their
/// counters: `crowded_skip` (not sent by policy), the queue's drops `crowded_pool` / `rate_queue_timeout` (`drop_*`), the
/// would-send rate model's `would_rate` / `would_rate_crowded`, `ungated_*` behind a closed gate
#[test]
fn round_trips_reasons_and_counters() {
    let ev = |v: Value| last_leg_out(&v);
    assert_eq!(ev(json!([{ "kind": "out", "leg": 0, "amount": 5 }, { "kind": "out", "leg": 1, "amount": 9 }])), Some(9));
    assert_eq!(ev(json!([{ "kind": "out", "leg": 0, "amount": 5 }, { "kind": "out", "leg": 1, "amount": 7 }, { "kind": "out", "leg": 2, "amount": 11 }])), Some(11), "three legs");
    assert_eq!(ev(json!([{ "kind": "out", "leg": 2, "amount": 11 }, { "kind": "out", "leg": 0, "amount": 5 }])), Some(11), "by leg, not order");
    assert_eq!(ev(json!([{ "kind": "out", "amount": 3 }, { "kind": "out", "amount": 4 }])), Some(4), "without leg numbers: the last");
    assert_eq!((ev(json!([{ "kind": "leg", "leg": 0 }])), ev(Value::Null)), (None, None));
    for (r, c, u) in [("crowded_skip", "reject_crowded_skip", "ungated_crowded_skip"), ("would_rate", "reject_would_rate", "ungated_would_rate"),
        ("would_rate_crowded", "reject_would_rate_crowded", "ungated_would_rate_crowded"), ("gate_shadow:control", "reject_gate_shadow", "ungated_gate_shadow"),
        ("build_error:buy leg: x", "reject_build_error", "ungated_build_error"), ("nonsense", "reject_other", "ungated_other")] {
        assert_eq!((reject_counter(r), ungated_counter(r)), (c, u), "{r}");
    }
    assert_eq!((drop_counter("crowded_pool"), drop_counter("rate_queue_timeout"), drop_counter("bad_tx"), drop_counter("x")),
        ("drop_crowded_pool", "drop_rate_queue_timeout", "drop_bad_tx", "drop_other"));
    assert_eq!(reject_counter("crowded_pool"), "reject_other", "the queue's drop is no decision's reason");
}

/// Probe (ignored; `cargo test --release --lib -- --ignored probe_ --nocapture --test-threads=1`): the engine thread's cost
/// of one decision that is built (a shadow would-send), signed and checked (a dry run) or signed and fired (live), and of
/// `inputs()` (review WP-05 #8: the leader read before the fire)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
#[ignore]
async fn probe_decide_costs() {
    for mode in [Mode::Shadow, Mode::DryRun, Mode::Live] {
        let mut r = rig(&format!("probe-{}", mode.as_str()), mode, "").await;
        if mode == Mode::Shadow { let g = SendGate::new(); let _ = g.shadow("mode_shadow", "probe", true); r.x.set_gate(g); }
        let mut t = now_ns();
        let mut v = Vec::new();
        let mut vi = Vec::new();
        for k in 0..400u64 {
            let n = (k % 100) as u8 * 2 + 1;
            let rt = route(n, damm(n + 1, MINT), 50_000 + k, k);
            let ti = std::time::Instant::now();
            let i = r.x.inputs(&r.view, 100, t);
            vi.push(ti.elapsed().as_nanos() as u64);
            let t0 = std::time::Instant::now();
            let d = r.x.decide(rt, &i, &r.view, 100, t);
            v.push(t0.elapsed().as_nanos() as u64);
            assert!(d.attempt.is_some(), "{d:?}");
            t += S; // past the rate window
        }
        v.sort();
        vi.sort();
        println!("PROBE decide {}: p50 {:.1} us, p90 {:.1} us, p99 {:.1} us, max {:.1} us", mode.as_str(), v[200] as f64 / 1e3, v[360] as f64 / 1e3, v[396] as f64 / 1e3, v[399] as f64 / 1e3);
        println!("PROBE inputs {}: p50 {:.2} us, p90 {:.2} us, p99 {:.2} us (a 3-validator LeaderBook)", mode.as_str(), vi[200] as f64 / 1e3, vi[360] as f64 / 1e3, vi[396] as f64 / 1e3);
        if mode == Mode::Live {
            let (a, b) = (r.x.lat[0].pct(0.5), r.x.lat[0].pct(0.9));
            let (c, d) = (r.x.lat[1].pct(0.5), r.x.lat[1].pct(0.9));
            println!("PROBE live decided_to_signed p50 {:.1} us p90 {:.1} us; signed_to_fired p50 {:.1} us p90 {:.1} us", a as f64 / 1e3, b as f64 / 1e3, c as f64 / 1e3, d as f64 / 1e3);
        }
    }
}

// ------------------------------------------------------------------------------------------------ WP-09: the replay's forms

/// Review WP-09 "For the WP-05 merge" item 4: INPUT 9 `settled` reads back in each of WP-05's `{what: …}` forms (a fire
/// result with its copies, a drop code among them; a statuses answer, landed, not found and failed; a dry run's
/// simulation) as the same settlement: written again, the same body
#[test]
fn settlements_read_back_from_the_journal() {
    let copy = |drop: Option<&'static str>| send::Sent { attempt: 3, path: "jito-bundle".into(), sig: Some("5ig".into()), tip_account: Some(b58(&[9; 32])), tip_lamports: 1_000,
        t_sent: 11, t_ack: 12, ms: 1.5, ok: drop.is_none(), status: Some(200), reply: None, bundle: Some("b0".into()), blockhash_slot: Some(99), queue_wait_us: Some(40),
        drop, lambda: Some(4) };
    let all = vec![
        Settled::Fired { attempt: 3, fired: Fired { id: 3, t_ns: 10, copies: vec![copy(None), copy(Some("rate_queue_timeout")), copy(Some("crowded_pool"))] } },
        Settled::Statuses { why: "expiry", at: vec![(1, "expiry"), (2, "expiry")], result: Ok(vec![Some(SigStatus { slot: 102, err: None, confirmation: Some("confirmed".into()) }), None]),
            t_ns: 20 },
        Settled::Statuses { why: "check", at: vec![(4, "+2s"), (5, "+10s"), (6, "+60s")], result: Err("timeout".into()), t_ns: 30 },
        Settled::Statuses { why: "check", at: vec![(4, "+2s")], result: Ok(vec![Some(SigStatus { slot: 7, err: Some(json!({ "InstructionError": [2, { "Custom": 6001 }] })),
            confirmation: None })]), t_ns: 31 },
        Settled::DrySim { attempt: 8, line: json!({ "attempt": 8, "src": "dry_run", "sim_ms": 2.5, "err": null }) },
    ];
    for s in &all {
        let j = s.json();
        let back = Settled::from_json(&j).unwrap_or_else(|| panic!("reads back: {j}"));
        assert_eq!(back.json(), j);
    }
    assert!(Settled::from_json(&json!({ "error": null, "landed": { "sig": "x" } })).is_none(), "the pre-WP-05 form is not a settlement");
    assert!(Settled::from_json(&json!({ "what": "statuses", "why": "other", "at": [], "result": [], "t_ns": 1 })).is_none());
    assert_eq!(send::drop_code("something new"), "other");
}

/// Review WP-09 "For the WP-05 merge" item 2: the exec_init record reads back as what the executor started with (its
/// lookup tables in order, PumpSwap's GlobalConfig, the held tokens, the size cap, the would-send rate, the tip policy,
/// the crowding map's static list); its size cap is the smaller of the cap and a bankroll's
#[tokio::test]
async fn exec_init_reads_back() {
    let dir = test_dir("exec-init");
    let cfg = test_cfg(&dir, "");
    let held: HashSet<Pk> = [*WSOL, MINT, M2].into_iter().collect();
    let pump = PumpGlobal { disable_flags: 8, protocol: vec![[1; 32], [2; 32]], reserved: vec![[3; 32]], buyback: vec![[4; 32]] };
    let x = Exec::assemble(&cfg, Rpc::race(vec![]), None, Rec::off(), crossbeam_channel::unbounded().0, vec![], vec![([7; 32], vec![[8; 32], [9; 32]]), ([6; 32], vec![[5; 32]])],
        Some(pump.clone()), held, Mode::Shadow, None).unwrap();
    let mut i = x.init();
    (i.crowding_window_h, i.crowding_buckets, i.crowded) = (6, [20, 150], vec![[11; 32], [12; 32]]);
    assert_eq!((i.alts[0].0, i.alts[1].0, i.pump.clone(), i.held.len(), i.max_size, i.would_send_per_sec), ([7; 32], [6; 32], Some(pump), 3, sol(cfg.live.max_size_sol), 5));
    assert_eq!(i.tips.as_ref().map(|p| (p.floor, p.share, p.max)), Some((1_000, Some(0.7), 100_000)));
    assert_eq!(i.cfg_sha256, cfg_sha256(&cfg));
    let back = ExecInit::from_json(&i.json()).unwrap();
    assert_eq!(back, i);
    assert_eq!(back.size_cap(), back.max_size);
    assert_eq!(ExecInit { bankroll_cap: Some(7), ..back.clone() }.size_cap(), 7);
    let _ = std::fs::remove_dir_all(&dir);
}

/// exec_init's `cfg_sha256`: the config the executor decides with. The supervisor's `--budget-left` (a lower failed-fee
/// cap for the segment; only a sending executor reads it) does not change it; the send policy does
#[test]
fn the_executor_config_hash() {
    let dir = std::env::temp_dir();
    let base = cfg_sha256(&test_cfg(&dir, ""));
    let mut c = test_cfg(&dir, "");
    c.live.max_failed_fees_lamports = 1;
    assert_eq!(cfg_sha256(&c), base);
    assert_ne!(cfg_sha256(&test_cfg(&dir, "[send_policy]\ninflight_hold_slots = 3\n")), base);
    c.strategy.cu_price_micro += 1;
    assert_ne!(cfg_sha256(&c), base);
}

/// Review WP-09 "For the WP-05 merge" items 1, 3: an offline executor (a replay's) reads the gate, the leader's kind, the
/// token and the recorder from the run's decision-point records, the last one at or before the opportunity, and nothing
/// of its own; the leader's identity is the journaled schedule's. A record of another opportunity, or one naming another
/// target slot or leader, is counted (`seen_mismatch`); a decision before any record reads the gate stopped
#[test]
fn an_offline_executor_reads_the_runs_records() {
    let cfg = test_cfg(&std::env::temp_dir(), "");
    let init = ExecInit { mode: Mode::Shadow, alts: vec![], pump: None, held: vec![*WSOL, MINT], max_size: 1_000, max_size_src: "live".into(), bankroll_cap: None,
        would_send_per_sec: 3, tips: None, crowding_window_h: 6, crowding_buckets: [20, 150], crowded: vec![], cfg_sha256: cfg_sha256(&cfg) };
    let mut x = Exec::offline(&cfg, &init, Rec::off()).unwrap();
    assert!(x.is_offline() && x.paths.is_none() && x.key.is_none() && x.jito.is_none());
    assert_eq!((x.size_cap(), x.path_rate), (1_000, 3));
    assert!(Exec::offline(&cfg, &ExecInit { mode: Mode::Live, ..init.clone() }, Rec::off()).is_err(), "a live executor is not replayed");
    let view = view();
    // before any record: fail closed
    let i = x.inputs(&view, 100, 1);
    assert_eq!((i.gate, i.recorder_ok, x.seen_missing), (GateMode::Stopped, false, 1));
    // the run's record of opportunity 4, at opportunity 4: its gate, kind and recorder; the schedule's identity (slot 101: LJ)
    let rec4 = json!({ "mode": "shadow", "reason": "paused", "src": "decision", "opp": 4, "leader": { "slot": 101, "identity": b58(&LJ), "kind": "bam", "kind_src": "kobe" },
        "jito_token_ok": true, "recorder_ok": true });
    x.stage_seen(4, 4, &rec4);
    let i = x.inputs(&view, 100, 2);
    assert_eq!((i.gate, i.gate_reason.as_str(), i.leader.kind, i.leader.identity.clone(), i.recorder_ok, i.token), (GateMode::Shadow, "paused", LeaderKind::Bam, Some(b58(&LJ)),
        true, TokenSeen::NotUsed));
    assert_eq!(x.seen_mismatch, 0);
    // the last record holds at the next opportunities
    assert_eq!(x.inputs(&view, 104, 3).leader.kind, LeaderKind::Bam);
    // a record naming another target slot than the replay's, a record staged at another opportunity, one it cannot read
    x.stage_seen(5, 5, &json!({ "mode": "live", "reason": null, "src": "decision", "opp": 5, "leader": { "slot": 999, "identity": b58(&LJ), "kind": "jito" },
        "jito_token_ok": true, "recorder_ok": true }));
    let _ = x.inputs(&view, 100, 4);
    x.stage_seen(6, 7, &rec4);
    x.stage_seen(8, 8, &json!({ "mode": null, "src": "decision", "opp": 8, "executor": false }));
    assert_eq!(x.seen_mismatch, 3);
}
