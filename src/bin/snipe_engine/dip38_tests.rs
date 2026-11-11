// ===================================================================================================================
// dip38 ANTI-BAIT tests (11-05; pslog38.rs, psfund.rs, psblock.rs): --presend-live-blocklist-launcher (LIVE, default on with the blocklist),
// --presend-live-insider-log / --presend-live-fund-* / --presend-live-family-state, --presend-live-shape-log / --presend-live-shape-state
// (LOG ONLY). OFF: nothing of it runs (no record, no field, no launcher record, no queue). LOG ON: only extra records: every other record,
// the sender's windows and the signed attempt bytes are the same; the hot path never waits (a full queue drops). The resolver's walk on a
// tape; INSIDER / FAMILY / FAMILY LEDGER / SHAPE through the real hooks (on_exec, trigger, re-arm, drain_atts, fill, close -> realized).
// ===================================================================================================================
use super::*;
use super::pslog38::*;
use super::pslog38::Cand;
use super::psfund::*;
use arbx::dip::{CreateEvent, TradeEvent};

const USER: Pk = [0x5Au8; 32];
const CREATOR: Pk = [0xC1u8; 32];
const S: u64 = 1_000_000_000;

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params { whale_pct: 6.0, ..Default::default() }, true, 1_000_000_000) }
fn pctr(x: f64) -> u64 { (x / 100.0 * pl::SUPPLY).round() as u64 }
fn w(k: u8) -> Pk { let mut x = [k; 32]; x[31] = 0x38; x }
fn tmp(name: &str) -> String { std::env::temp_dir().join(format!("dip38-{}-{name}", std::process::id())).to_string_lossy().to_string() }
fn list(tag: &str, ws: &[Pk]) -> String {
    let p = tmp(&format!("bl-{tag}.json"));
    std::fs::write(&p, serde_json::json!({"version": 5, "wallets": ws.iter().map(|k| serde_json::json!({"w": b58(k), "why": "test"})).collect::<Vec<_>>()}).to_string()).unwrap();
    p
}
fn ch(links: &[(Pk, Kind, u8)]) -> Arc<Chain> {
    Arc::new(Chain { st: FSt::Ok, n: 3, t: unix_s(), links: links.iter().map(|(a, k, h)| Link { a: *a, kind: *k, hops: *h }).collect(), err: None })
}
fn sold(c: Option<u64>, sigs: &[&str], qty: u64) -> SellOut {
    SellOut { sold_at: c, sigs: sigs.iter().map(|s| (s.to_string(), true, 1_200_000)).collect(), last: None, attempts: sigs.len() as u32, last_qty: (qty, true), first_send_us: None }
}

struct Tk { mint: Pk, v: u64, t: u64, launch: Launch }
impl Tk {
    fn new(k: u8) -> Tk { let mint = [k; 32]; Tk { mint, v: 30 * S, t: 1_073_000_000_000_000, launch: snipe_build::launch_from_target(mint, CREATOR) } }
    fn buy(&mut self, user: Pk, sol: u64) -> TradeEvent {
        let q = (self.t as u128 * sol as u128 / (self.v + sol) as u128) as u64;
        self.v += sol; self.t -= q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: true, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    fn buy_tok(&mut self, user: Pk, q: u64) -> TradeEvent {
        let sol = ((self.v as u128 * q as u128).div_ceil((self.t - q) as u128)) as u64;
        self.v += sol; self.t -= q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: true, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    fn sell_tok(&mut self, user: Pk, q: u64) -> TradeEvent {
        let sol = (self.v as u128 * q as u128 / (self.t + q) as u128) as u64;
        self.v -= sol; self.t += q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: false, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    /// the create: its tx paid by `launcher` (the create event's user), the pump creator field CREATOR (a fresh wallet, dtrz's way)
    fn create(&self, launcher: Pk) -> CreateEvent { CreateEvent { mint: self.mint, bonding_curve: self.launch.bonding_curve, user: launcher, creator: CREATOR } }
}

struct Ctx { p: PsLive, atx: crossbeam_channel::Sender<Att>, orx: crossbeam_channel::Receiver<Out>, launches: Vec<Launch>, recs: Vec<serde_json::Value>, lines: Vec<String>, cmds: Vec<Cmd> }
impl Ctx {
    fn new(extra: &[&str]) -> Ctx { Ctx::with(cfg(extra).unwrap().unwrap()) }
    fn with(c: Cfg) -> Ctx {
        let (p, atx, orx) = PsLive::for_test(c, USER);
        Ctx { p, atx, orx, launches: Vec::new(), recs: Vec::new(), lines: Vec::new(), cmds: Vec::new() }
    }
    fn pump(&mut self) {
        for o in self.orx.try_iter() { match o { Out::Rec(v) => self.recs.push(v), Out::Line(l) => self.lines.push(l) } }
        self.cmds.extend(self.p.take_cmds());
    }
    fn tx_sig(&mut self, slot: u64, idx: u64, sig: [u8; 64], payer: Pk, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades, creates, mayhem: false };
        let a = arbx::feeds::Arrival { feed: 0, slot, t_rx: slot * 1_000_000 + idx, t_decoded: slot * 1_000_000 + idx, executed: Some(true),
            tx: arbx::tx::Tx { sig, keys: vec![payer], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        let ls = self.launches.clone();
        self.p.on_arrival(&a, slot);
        self.p.on_exec(&a, &x, slot, move |m: &Pk| ls.iter().find(|l| l.mint == *m).cloned(), &|_| false, None);
        self.pump();
    }
    fn tx(&mut self, slot: u64, idx: u64, payer: Pk, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&slot.to_be_bytes()); sig[8..16].copy_from_slice(&idx.to_be_bytes()); sig[16] = 0x38; sig[17] = trades.first().map_or(0, |t| t.mint[0]);
        self.tx_sig(slot, idx, sig, payer, trades, creates);
    }
    fn ev(&self, k: &str) -> Vec<serde_json::Value> { self.recs.iter().filter(|r| r["ev"] == k).cloned().collect() }
    fn stage(&self, k: &str, st: &str) -> Vec<serde_json::Value> { self.recs.iter().filter(|r| r["ev"] == k && r["stage"] == st).cloned().collect() }
    /// T2 the dtrz way on token `k`: `launcher` pays the create and buys 26.64% (a create-slot trigger: skipped), `helper` buys exactly 5.5753%
    /// at 1004, a small buy, the whale's 8% at 1005 (a trigger: armed)
    fn t2(&mut self, k: u8, launcher: Pk, helper: Pk, whale: Pk) -> Tk {
        let mut tk = Tk::new(k);
        self.launches.push(tk.launch.clone());
        let dev = tk.buy_tok(launcher, pctr(26.64));
        self.tx(1000, 1, launcher, vec![dev], vec![tk.create(launcher)]);
        let e = tk.buy_tok(helper, pctr(5.5753));
        self.tx(1004, 2, helper, vec![e], vec![]);
        let e = tk.buy(w(0x11), S / 10);
        self.tx(1004, 3, w(0x11), vec![e], vec![]);
        let e = tk.buy_tok(whale, pctr(8.0));
        self.tx(1005, 50, whale, vec![e], vec![]);
        tk
    }
    /// an attempt of window `id` at `slot` (the sender's registration) -> drain_atts
    fn att(&mut self, id: u64, mint: Pk, slot: u64, tag: u8) -> [u8; 64] {
        let mut sg = [0u8; 64]; sg[0] = 0xD3; sg[1] = 0x38; sg[2] = tag; sg[3] = slot as u8;
        self.atx.send(Att { w: id, n: 1, mint, sig: sg, tag: pl::PS_TAG | (tag as u64), path: "helius-ps".into(), client: "JitoLabs".into(), slot, deadline: slot + 1,
            lim: 1.0, min_out: 1, p_sign: 1.0, sign_pos: (slot, 0, 0), t_send: slot * 1_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) },
            tip: 200_000, wst: "written", ob6: 0.0, grd: Grd::default(), fa: None, bd: None, x46: Default::default() }).unwrap();
        self.p.drain_atts();
        self.pump();
        sg
    }
    /// fill window `id` at 1007 with attempt `sg`, a filler token moves the clock to the exit, the sell lands, the sell round ends ->
    /// close -> realized (the Cmd::Realized queued)
    fn fill_close(&mut self, tk: &mut Tk, sg: [u8; 64], filler: u8) -> Cmd {
        let e = tk.buy(USER, 396_000_000);
        self.tx_sig(1007, 4, sg, USER, vec![e.clone()], vec![]);
        let mut z = Tk::new(filler);
        self.launches.push(z.launch.clone());
        let dz = z.buy(CREATOR, S / 2);
        self.tx(1007, 900, CREATOR, vec![dz], vec![z.create(CREATOR)]);
        for s in 1008..=1009 { let e = z.buy([0x2F; 32], 1_000_000); self.tx(s, 900, [0x2F; 32], vec![e], vec![]); }
        let Some(Cmd::Sell { pid, .. }) = self.cmds.iter().rev().find(|x| matches!(x, Cmd::Sell { .. })).cloned() else { panic!("no sell: {:?}", self.cmds) };
        let es = tk.sell_tok(USER, e.tok);
        self.tx_sig(1009, 9, { let mut s = [0u8; 64]; s[0] = 0x5E; s[1] = 0x38; s[2] = filler; s }, USER, vec![es], vec![]);
        self.p.on_msg(PsMsg::Sold(tk.mint, pid, 1, sold(Some(1009), &["S38"], e.tok)), &|_| false);
        self.pump();
        self.cmds.iter().rev().find(|x| matches!(x, Cmd::Realized { .. })).cloned().expect("realized")
    }
    fn q(&mut self) -> Vec<Pk> { self.p.l38.q.as_mut().map(std::mem::take).unwrap_or_default() }
}

/// a run's Cmds with the dip38 part taken out of Realized
fn cmds_wo38(v: &[Cmd]) -> Vec<String> {
    v.iter().map(|c| match c.clone() {
        Cmd::Realized { pid, w, mint, buys, sells, rearm, cr, ab, wh, hl, s1, .. } => format!("{:?}", Cmd::Realized { pid, w, mint, buys, sells, rearm, cr, ab, wh, hl, l38: None, s1, wd: None, f2: None }),
        x => format!("{x:?}"),
    }).collect()
}
/// the records but dip38's, the disarm's wall-clock fields out
fn recs_wo38(v: &[serde_json::Value]) -> Vec<String> {
    v.iter().filter(|r| !["presend_live_insider", "presend_live_shape", "presend_live_fund"].contains(&r["ev"].as_str().unwrap_or(""))).map(|r| {
        let mut r = r.clone();
        // the wall-clock fields (the disarm's age and time, the exit's time, the close's hold) differ between any two runs
        if let Some(o) = r.as_object_mut() {
            match o.get("ev").and_then(|e| e.as_str()) {
                Some("presend_live_disarm") => { o.remove("armed_ms"); o.remove("t"); }
                Some("presend_live_exit") => { o.remove("t"); }
                Some("presend_live_close") => { o.remove("held_s"); }
                _ => {}
            }
        }
        r.to_string()
    }).collect()
}
fn signed(ixs: &[build::Ix]) -> Vec<u8> { build::sign(&build::compile_v0(USER, ixs, [9u8; 32], &[], &[]).unwrap(), &SigningKey::from_bytes(&[7u8; 32])) }
/// the sender's view of a window that the attempt bytes depend on, and those bytes (the run's own CU / tip)
fn swin_view(c: &Ctx, id: u64) -> (String, Vec<u8>) {
    let sw = c.p.sh.wins.lock().unwrap().iter().find(|x| x.id == id).cloned().expect("window");
    let v = format!("{} {:?} {:?} {} {} {} {} {:?} {} {} {} {:?} {:?} {}", sw.id, sw.mint, sw.launch, sw.en_slot, sw.vsol, sw.vtok, sw.fr, sw.pos, sw.spend, sw.rearm, sw.ob6, sw.blk, sw.fab, sw.done);
    let (min_out, _, _) = att_limit(&sw, c.p.cfg.drop).unwrap();
    let (ixs, _) = att_ixs(USER, &sw, min_out, &c.p.cfg, guard_ix_enc(GuardEnc { disc: 15, op: 4, acct: true }, 1006), Some(([0x71; 32], 200_000)));
    (v, signed(&ixs))
}

#[test]
fn dip38_flags() {
    let c0 = cfg(&[]).unwrap().unwrap();
    assert!(!c0.insider_log && !c0.shape_log && !c0.blocklist_launcher && c0.fund_rpc.is_none() && c0.fund_rps == FUND_RPS && c0.fund_state.is_none());
    let j = c0.json();
    assert!(j.get("insider_log").is_none() && j.get("shape_log").is_none() && j.get("blocklist").is_none(), "off: dip37c's start record");
    let bl = list("flags", &[w(1)]);
    let c = cfg(&["--presend-live-blocklist", &bl]).unwrap().unwrap();
    assert!(c.blocklist_launcher && c.json()["blocklist"]["launcher"] == true, "on by default with the blocklist");
    let c = cfg(&["--presend-live-blocklist", &bl, "--presend-live-blocklist-launcher", "off"]).unwrap().unwrap();
    assert!(!c.blocklist_launcher && c.json()["blocklist"].get("launcher").is_none(), "off: dip37c's blocklist record");
    let c = cfg(&["--presend-live-insider-log", "on", "--presend-live-fund-rpc", "${FUND_URL}", "--presend-live-fund-rps", "2.5", "--presend-live-fund-state", "/x/f.json",
        "--presend-live-family-state", "/x/fl.json", "--presend-live-shape-log", "on", "--presend-live-shape-state", "/x/s.json"]).unwrap().unwrap();
    assert!(c.insider_log && c.shape_log && c.fund_rps == 2.5 && c.fund_rpc.as_deref() == Some("${FUND_URL}") && c.fund_state.as_deref() == Some("/x/f.json")
        && c.family_state.as_deref() == Some("/x/fl.json") && c.shape_state.as_deref() == Some("/x/s.json"));
    let j = c.json();
    assert!(j["insider_log"]["rpc"] == "--presend-live-fund-rpc" && j["insider_log"]["rps"] == 2.5 && j["shape_log"]["shape_state"] == "/x/s.json", "{j}");
    assert!(!j.to_string().contains("FUND_URL"), "the URL never in a record");
    for (a, needle) in [(&["--presend-live-blocklist-launcher", "on"][..], "needs --presend-live-blocklist PATH"),
        (&["--presend-live-insider-log", "yes"][..], "on | off"), (&["--presend-live-shape-log", "1"][..], "on | off"),
        (&["--presend-live-fund-rpc", "http://x"][..], "needs --presend-live-insider-log on"), (&["--presend-live-fund-rps", "2"][..], "needs --presend-live-insider-log on"),
        (&["--presend-live-fund-state", "/x"][..], "needs --presend-live-insider-log on"), (&["--presend-live-family-state", "/x"][..], "needs --presend-live-insider-log on"),
        (&["--presend-live-shape-state", "/x"][..], "needs --presend-live-shape-log on"),
        (&["--presend-live-insider-log", "on", "--presend-live-fund-rps", "0"][..], "(0, 50]"), (&["--presend-live-insider-log", "on", "--presend-live-fund-rps", "51"][..], "(0, 50]"),
        (&["--presend-live-insider-log", "on", "--presend-live-fund-state"][..], "needs a value"), (&["--presend-live-insider-log", "on", "--presend-live-fund-rpc", "--presend-live-k"][..], "needs a value")] {
        let e = cfg(a).unwrap_err().to_string();
        assert!(e.contains(needle), "{a:?}: {e}");
    }
    for f in ["--presend-live-blocklist-launcher", "--presend-live-insider-log", "--presend-live-fund-rpc", "--presend-live-fund-rps", "--presend-live-fund-state",
        "--presend-live-family-state", "--presend-live-shape-log", "--presend-live-shape-state"] {
        let e = Cfg::from_argv(&["snipe_engine", "--dip", "--presend-shadow", f, "1"].iter().map(|s| s.to_string()).collect::<Vec<_>>(), &arbx::presend::Params::default(), true, 1_000_000_000)
            .unwrap_err().to_string();
        assert!(e.contains("needs --presend-live"), "{f}: {e}");
    }
    assert!(crate::check_flags(&args(&["--presend-live-blocklist", "/x", "--presend-live-blocklist-launcher", "on", "--presend-live-insider-log", "on", "--presend-live-fund-rpc", "http://r",
        "--presend-live-fund-rps", "3", "--presend-live-fund-state", "/f", "--presend-live-family-state", "/fl", "--presend-live-shape-log", "on", "--presend-live-shape-state", "/s"])).is_ok());
    assert!(crate::check_flags(&args(&["--presend-live-insider-log", "on", "--presend-live-fund-rps", "abc"])).is_err(), "a number");
}

/// LIVE: the blocklist matches the token's launcher (its create tx's fee payer, not the creator field): T2 "blocklist" / re-arm
/// "rearm_blocklist" with bl_role "launcher" even when it holds nothing; the whale's own hit keeps its role; off: armed as dip37c;
/// a reload that lists the launcher of an armed window withholds its sends
#[test]
fn dip38_blocklist_launcher() {
    let (l, h, whale) = (w(0x4C), w(0x48), w(0xEE));
    // the launcher sells its whole bag before the trigger: no holder role can catch it
    let run = |extra: &[&str]| {
        let mut c = Ctx::new(extra);
        let mut tk = Tk::new(0x61);
        c.launches.push(tk.launch.clone());
        let dev = tk.buy_tok(l, pctr(26.64));
        c.tx(1000, 1, l, vec![dev], vec![tk.create(l)]);
        let d = tk.sell_tok(l, pctr(26.64));
        c.tx(1003, 1, l, vec![d], vec![]);
        let e = tk.buy_tok(h, pctr(2.0));
        c.tx(1004, 2, h, vec![e], vec![]);
        let e = tk.buy_tok(whale, pctr(8.0));
        c.tx(1005, 50, whale, vec![e], vec![]);
        (c, tk)
    };
    let pl_ = list("lnch", &[l]);
    let (c, _) = run(&["--presend-live-blocklist", &pl_]);
    assert!(c.ev("presend_live_arm").is_empty() && c.p.armed.is_empty(), "{:?}", c.recs);
    let s = c.ev("presend_live_skip").into_iter().find(|r| r["why"] == "blocklist").expect("skipped");
    assert!(s["bl_role"] == "launcher" && s["bl_wallet"] == b58(&l) && s["bl_pct"] == 0.0 && s["bl_why"] == "test", "{s}");
    assert!(c.lines.iter().any(|x| x.contains("PRESEND LIVE BLOCKLIST SKIP") && x.contains("launcher")));
    // the flag off: armed, every record dip37c's
    let (c_off, _) = run(&["--presend-live-blocklist", &pl_, "--presend-live-blocklist-launcher", "off"]);
    assert_eq!(c_off.ev("presend_live_arm").len(), 1);
    let pn = list("lnch-n", &[w(0x99)]);
    let (c_n, _) = run(&["--presend-live-blocklist", &pn]);
    assert_eq!(recs_wo38(&c_n.recs), recs_wo38(&c_off.recs), "not listed: the same as the flag off");
    assert!(c_off.p.l38.launch.is_empty() && !c_n.p.l38.launch.is_empty(), "the launchers are recorded only with the match on");
    // the creator field is NOT the launcher: listing CREATOR does nothing
    let pc = list("lnch-c", &[CREATOR]);
    let (c, _) = run(&["--presend-live-blocklist", &pc]);
    assert_eq!(c.ev("presend_live_arm").len(), 1);
    // the whale listed too: its own role first (dip37c's record)
    let pw = list("lnch-w", &[l, whale]);
    let (c, _) = run(&["--presend-live-blocklist", &pw]);
    assert_eq!(c.ev("presend_live_skip").into_iter().find(|r| r["why"] == "blocklist").unwrap()["bl_role"], "whale");
    // per-send: the list names the launcher after the arm -> the armed window's sends are withheld (its holding as the %)
    let p2 = list("lnch-r", &[w(0x99)]);
    let (mut c, tk) = run(&["--presend-live-blocklist", &p2]);
    let id = c.p.armed[&tk.mint];
    assert_eq!(c.p.sh.wins.lock().unwrap().iter().find(|x| x.id == id).unwrap().blk, None);
    std::fs::write(&p2, serde_json::json!({"version": 6, "wallets": [{"w": b58(&l), "why": "dtrz"}]}).to_string()).unwrap();
    c.p.bl.as_mut().unwrap().mtime_reset_for_test();
    c.p.tick(1006, None);
    let sw = c.p.sh.wins.lock().unwrap().iter().find(|x| x.id == id).cloned().unwrap();
    assert_eq!(sw.blk, Some((l, 0.0)));
    assert_eq!(bl_send_check(&c.p.sh, &sw), Some((l, 0.0, true)), "live: withheld");
    // re-arm: the launcher listed -> "rearm_blocklist" role launcher
    let rearm = |extra: &[&str]| {
        let mut x = vec!["--presend-live-rearm", "on"]; x.extend_from_slice(extra);
        let mut c = Ctx::new(&x);
        let (a, b) = (w(0xA1), w(0xB1));
        let mut tk = Tk::new(0x62);
        let mut z = Tk::new(0x63);
        c.launches.push(tk.launch.clone());
        c.launches.push(z.launch.clone());
        let dev = tk.buy(l, S / 2);
        c.tx(1000, 1, l, vec![dev], vec![tk.create(l)]);
        let e = tk.buy_tok(a, pctr(7.0)); c.tx(1000, 2, a, vec![e], vec![]);
        let e = tk.buy_tok(b, pctr(8.0)); c.tx(1000, 3, b, vec![e], vec![]);
        let dz = z.buy(CREATOR, S / 2);
        c.tx(1000, 4, CREATOR, vec![dz], vec![z.create(CREATOR)]);
        for s in 1001..=1004 { let e = tk.buy(w(0x33), S / 10); c.tx(s, 5, w(0x33), vec![e], vec![]); }
        let d = tk.sell_tok(a, pctr(7.0));
        c.tx(1005, 5, a, vec![d], vec![]);
        for s in 1006..=1008 { let e = z.buy(w(0x2F), 1_000_000); c.tx(s, 900, w(0x2F), vec![e], vec![]); }
        c
    };
    let c = rearm(&["--presend-live-blocklist", &pl_]);
    assert!(!c.ev("presend_live_arm").iter().any(|r| r["kind"] == "rearm"));
    let s = c.ev("presend_live_skip").into_iter().find(|r| r["why"] == "rearm_blocklist").expect("re-arm skipped");
    assert!(s["bl_role"] == "launcher" && s["bl_wallet"] == b58(&l), "{s}");
    let c = rearm(&["--presend-live-blocklist", &pl_, "--presend-live-blocklist-launcher", "off"]);
    assert!(c.ev("presend_live_arm").iter().any(|r| r["kind"] == "rearm"));
}

/// LOG ON = only extra records: every other record, the queued chain work (realize aside: its dip38 part), the sender's window and the
/// SIGNED ATTEMPT BYTES equal the flags-off run; off: no dip38 record, no launcher record, nothing queued
#[test]
fn dip38_log_changes_nothing_else() {
    let _g = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (l, h, whale) = (w(0x4C), w(0x48), w(0xEE));
    let fam_p = tmp("same-fl.json");
    let run = |extra: &[&str]| {
        let mut c = Ctx::new(extra);
        let mut tk = c.t2(0x61, l, h, whale);
        let id = c.p.armed[&tk.mint];
        let view = swin_view(&c, id);
        let sg = c.att(id, tk.mint, 1006, 1);
        // a late >= 3% buyer while armed, a second send slot
        let e = tk.buy_tok(w(0x22), pctr(3.5));
        c.tx(1006, 7, w(0x22), vec![e], vec![]);
        c.att(id, tk.mint, 1007, 2);
        let rz = c.fill_close(&mut tk, sg, 0x7F);
        let end = c.p.finish(1012, None);
        (c, view, rz, end)
    };
    let (mut c0, v0, rz0, end0) = run(&[]);
    let (mut c1, v1, rz1, end1) = run(&["--presend-live-insider-log", "on", "--presend-live-shape-log", "on", "--presend-live-family-state", &fam_p]);
    assert!(c0.ev("presend_live_arm").len() == 1 && c0.ev("presend_live_fill").len() == 1 && c0.ev("presend_live_close").len() == 1, "armed, filled, closed");
    assert_eq!(v0, v1, "the sender's window and the signed attempt bytes: the same");
    assert_eq!(recs_wo38(&c0.recs), recs_wo38(&c1.recs), "every other record the same");
    assert_eq!(cmds_wo38(&c0.cmds), cmds_wo38(&c1.cmds), "the same chain work");
    // off: nothing of dip38
    assert!(c0.recs.iter().all(|r| !r["ev"].as_str().unwrap().starts_with("presend_live_insider") && !r["ev"].as_str().unwrap().starts_with("presend_live_shape")));
    assert!(c0.p.l38.launch.is_empty() && c0.p.l38.wins.is_empty() && c0.p.l38.q.is_none() && c0.p.l38.sd.is_empty());
    assert!(matches!(rz0, Cmd::Realized { l38: None, .. }) && matches!(rz1, Cmd::Realized { l38: Some(_), .. }));
    assert!(end0.get("dip38_log").is_none() && end1["dip38_log"]["arms"] == 1 && end1["dip38_log"]["fills"] == 1, "{}", end1["dip38_log"]);
    assert!(!c0.p.status().contains("DIP38") && c1.p.status().contains("DIP38 LOG"));
    // on: arm + 2 sends + fill of each log
    for ev in ["presend_live_insider", "presend_live_shape"] {
        let st: Vec<String> = c1.ev(ev).iter().map(|r| r["stage"].as_str().unwrap().to_string()).collect();
        assert_eq!(st, ["arm", "send", "send", "fill"], "{ev}");
    }
    assert!(std::path::Path::new(&fam_p).exists(), "the family ledger saved at the end");
}

/// INSIDER / FAMILY / FAMILY LEDGER end to end: the arm queues the whale and the >= 3% holders (launcher included, never us); a chain
/// that reaches the launcher through a pass-through makes the next send / the fill INSIDER (role, hop, walk); a listed pass-through is
/// FAMILY; the realize teaches the launcher's ledger; the launcher's NEXT token is then a would-block from its arm
#[test]
fn dip38_insider_family_ledger() {
    let _g = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (l, h, whale, hub, pass) = (w(0x4C), w(0x48), w(0xEE), w(0x8D), w(0xEB));
    let fund = tmp("fund.json");
    let famf = tmp("fam.json");
    let _ = std::fs::remove_file(&fund);
    let _ = std::fs::remove_file(&famf);
    let bl = list("ins", &[pass]);
    let mut c = Ctx::new(&["--presend-live-insider-log", "on", "--presend-live-fund-state", &fund, "--presend-live-family-state", &famf, "--presend-live-blocklist", &bl]);
    let mut tk = c.t2(0x61, l, h, whale);
    let id = c.p.armed[&tk.mint];
    assert_eq!(c.q(), vec![whale, l, h], "first sight: the whale, then the holders >= 3% largest first");
    let arm = c.stage("presend_live_insider", "arm").pop().unwrap();
    assert!(arm["launcher"] == b58(&l) && arm["creator"] == b58(&CREATOR) && arm["payer_ne_creator"] == true && arm["kind"] == "T2" && arm["w"] == id, "{arm}");
    assert!((arm["launcher_pct"].as_f64().unwrap() - 26.64).abs() < 1e-3 && arm["launcher_sold_pct"] == 0.0 && (arm["launcher_bought_pct"].as_f64().unwrap() - 26.64).abs() < 1e-3);
    assert!(arm["insider"] == false && arm["cands"] == 3 && arm["cov"]["pending"] == 3 && arm["fl"]["n"] == 0 && arm["would"] == false, "{arm}");
    // the chains come back: h = [exchange hub 0.9 SOL, a 2-tx pass-through funded by the launcher]; the whale's an exchange's; the launcher deep
    c.p.on_msg(PsMsg::Fund(Box::new(FundOut::Done(h, ch(&[(hub, Kind::Hub, 0), (pass, Kind::Oneshot, 0), (l, Kind::Hub, 1)]), 9_000.0, 11))), &|_| false);
    c.p.on_msg(PsMsg::Fund(Box::new(FundOut::Done(whale, ch(&[(hub, Kind::Hub, 0)]), 3_000.0, 5))), &|_| false);
    c.p.on_msg(PsMsg::Fund(Box::new(FundOut::Done(l, Arc::new(Chain { st: FSt::Deep, n: 2000, t: unix_s(), links: vec![], err: None }), 1_000.0, 2))), &|_| false);
    c.pump();
    let f = c.ev("presend_live_fund");
    assert!(f.len() == 3 && f[0]["wallet"] == b58(&h) && f[0]["st"] == "ok" && f[0]["chain"][2][0] == b58(&l) && f[0]["chain"][2][1] == "hub" && f[0]["chain"][2][2] == 1 && f[2]["st"] == "deep");
    // a re-sight never asks again
    let sg = c.att(id, tk.mint, 1006, 1);
    assert!(c.q().is_empty());
    let snd = c.stage("presend_live_insider", "send").pop().unwrap();
    assert!(snd["insider"] == true && snd["ins"]["wallet"] == b58(&h) && snd["ins"]["role"] == "holder" && snd["ins"]["via"] == "launcher" && snd["ins"]["hops"] == 1, "{snd}");
    let walk = format!("{}<-{}<-{}", &b58(&h)[..8], &b58(&pass)[..8], &b58(&l)[..8]);
    assert_eq!(snd["ins"]["chain"], walk.as_str(), "the walk from the pass-through (the hub before it is another walk)");
    assert!(snd["family"] == true && snd["fam"]["link"] == b58(&pass) && snd["fam"]["via"] == "blocklist", "a listed pass-through: FAMILY {snd}");
    assert!(snd["cov"]["ok"] == 2 && snd["cov"]["deep"] == 1 && snd["would"] == false && snd["fl"]["n"] == 0, "no ledger history yet: {snd}");
    // the fill: INSIDER; the realize (P&L -0.25) teaches the launcher's family ledger
    let Cmd::Realized { l38: Some(z), .. } = c.fill_close(&mut tk, sg, 0x7F) else { panic!("no dip38 part") };
    let fill = c.stage("presend_live_insider", "fill").pop().unwrap();
    assert!(fill["insider"] == true && fill["would"] == false, "{fill}");
    assert!(z.ins_fill && z.launcher == Some(l) && z.mint == tk.mint);
    let t_real = 1_009_000_100;
    let out = z.learn(-250_000_000, t_real);
    assert!(out[0]["stage"] == "realize" && out[0]["learned"] == true && out[0]["pnl"] == -250_000_000 && out[0]["fl_after"]["would"] == true && out[0]["fl_after"]["n"] == 1, "{}", out[0]);
    // the launcher's next token, the same helper: the arm is INSIDER and the family ledger would block it
    let mut c2tk = Tk::new(0x64);
    c.launches.push(c2tk.launch.clone());
    let dev = c2tk.buy_tok(l, pctr(26.64));
    c.tx(1010, 1, l, vec![dev], vec![c2tk.create(l)]);
    let e = c2tk.buy_tok(h, pctr(5.5753)); c.tx(1014, 2, h, vec![e], vec![]);
    let e = c2tk.buy_tok(w(0xE2), pctr(8.0)); c.tx(1015, 50, w(0xE2), vec![e], vec![]);
    let arm2 = c.stage("presend_live_insider", "arm").pop().unwrap();
    assert!(arm2["mint"] == b58(&c2tk.mint) && arm2["insider"] == true && arm2["fl"]["would"] == true && arm2["would"] == true && arm2["fl"]["sum"] == -0.25, "{arm2}");
    assert!(c.lines.iter().any(|x| x.contains("PRESEND LIVE INSIDER (log) arm") && x.contains("WOULD BLOCK")), "{:?}", c.lines);
    // a win >= 0.05 lifts it (the win protection)
    z.learn(60_000_000, t_real + 1);
    let v = c.p.l38.fl.lock().unwrap().view(&l, t_real + 2);
    assert!(v.n == 2 && !v.blocks(FL_LOSS, FL_WIN));
    // the run's end: the chains and the ledger saved, run_end counts
    let end = c.p.finish(1020, None);
    let d = &end["dip38_log"];
    assert!(d["insider"][1] == 1 && d["insider"][2] == 1 && d["insider"][0] == 1 && d["family_would"][0] == 1 && d["resolved"]["ok"] == 2 && d["resolved"]["deep"] == 1, "{d}");
    let m = fund_load(&fund).unwrap();
    assert!(m.len() == 3 && m[&h].find(&l) == Some(2), "ok + deep saved");
    let fl: Led<Pk> = led_load(&famf, FL_WIN_NS).unwrap();
    assert_eq!(fl.view(&l, t_real + 2).n, 2);
    // the next run preloads both (no task in the tests: the queue)
    let c3 = Ctx::new(&["--presend-live-insider-log", "on", "--presend-live-fund-state", &fund, "--presend-live-family-state", &famf]);
    assert!(c3.p.l38.chains.len() == 3 && c3.p.l38.fl.lock().unwrap().m.contains_key(&l));
}

/// INSIDER's definition: never the launcher itself; the creator field counts too; a deep / failed chain is coverage, not a hit; the
/// whale role; FAMILY needs a list
#[test]
fn dip38_judge_rules() {
    let (l, cr, a, b, x) = (w(1), w(2), w(3), w(4), w(5));
    let mut chains = Chains::default();
    chains.insert(l, ch(&[(cr, Kind::Normal, 0)]));
    chains.insert(a, ch(&[(x, Kind::Hub, 0), (cr, Kind::Normal, 0)]));
    chains.insert(b, Arc::new(Chain { st: FSt::Fail, n: 0, t: 1, links: vec![], err: Some("x".into()) }));
    let pend: FxHashSet<Pk> = [w(6)].into_iter().collect();
    let cands = |v: &[(Pk, &'static str)]| -> Vec<Cand> { v.iter().map(|(k, r)| Cand { w: *k, role: r, pct: 5.0 }).collect() };
    // the launcher funded by the creator: not INSIDER (the launcher itself)
    let v = judge(&cands(&[(l, "holder")]), Some(&l), Some(&cr), &chains, &pend, None);
    assert!(v.ins.is_none() && v.cov == [1, 0, 0, 0, 0]);
    // a holder funded by the creator field: INSIDER via creator
    let v = judge(&cands(&[(b, "whale"), (a, "holder"), (w(6), "holder"), (w(7), "holder")]), Some(&l), Some(&cr), &chains, &pend, None);
    let h = v.ins.unwrap();
    assert!(h.c.w == a && h.via == "creator" && h.hops == 0 && v.cov == [1, 0, 1, 1, 1] && v.fam.is_none());
    // FAMILY: a listed address anywhere in the chain (hubs too)
    let listed: FxHashMap<Pk, String> = [(x, "t".to_string())].into_iter().collect();
    let v = judge(&cands(&[(a, "whale")]), None, None, &chains, &pend, Some(&listed));
    assert!(v.ins.is_none() && v.fam.as_ref().is_some_and(|f| f.link == x && f.c.role == "whale"));
}

/// SHAPE: els = holders >= 3% held BEFORE the current slot (a same-slot buyer out until the next slot; the whale out); a loss on an el makes
/// the next token with the same exact size a would-block (any wallet); a win >= 0.05 protects it; the 6 h window
#[test]
fn dip38_shape_ledger() {
    let _g = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (l, h, whale, z) = (w(0x4C), w(0x48), w(0xEE), w(0x5A));
    let shp = tmp("shape.json");
    let _ = std::fs::remove_file(&shp);
    let mut c = Ctx::new(&["--presend-live-shape-log", "on", "--presend-live-shape-state", &shp]);
    let mut tk = Tk::new(0x61);
    c.launches.push(tk.launch.clone());
    let dev = tk.buy_tok(l, pctr(26.64));
    c.tx(1000, 1, l, vec![dev], vec![tk.create(l)]);
    let e = tk.buy_tok(h, pctr(5.5753)); c.tx(1004, 2, h, vec![e], vec![]);
    // z buys 4% in the trigger's own slot, before the whale
    let e = tk.buy_tok(z, pctr(4.0)); c.tx(1005, 10, z, vec![e], vec![]);
    let e = tk.buy_tok(whale, pctr(8.0)); c.tx(1005, 50, whale, vec![e], vec![]);
    let id = c.p.armed[&tk.mint];
    let arm = c.stage("presend_live_shape", "arm").pop().unwrap();
    assert_eq!(arm["els"], serde_json::json!([26.64, 5.575]), "the launcher's and the helper's bags; z bought in this slot, the whale out: {arm}");
    assert!(arm["would"] == false && arm["hit"].is_null());
    let sg = c.att(id, tk.mint, 1006, 1);
    let snd = c.stage("presend_live_shape", "send").pop().unwrap();
    assert_eq!(snd["els"], serde_json::json!([26.64, 5.575, 4.0]), "a slot later z's 4% counts: {snd}");
    // the fill learns -0.15 on every el of the fill
    let Cmd::Realized { l38: Some(zr), .. } = c.fill_close(&mut tk, sg, 0x7F) else { panic!() };
    assert_eq!(zr.els.len(), 3);
    let t0 = 1_009_000_000;
    let out = zr.learn(-150_000_000, t0);
    assert!(out.len() == 1 && out[0]["ev"] == "presend_live_shape" && out[0]["stage"] == "realize" && out[0]["learned"] == true);
    // another token: a DIFFERENT wallet lands the same 5.5753%: would block
    let mut t2 = Tk::new(0x65);
    c.launches.push(t2.launch.clone());
    let dev = t2.buy(w(0x4D), S / 2); c.tx(1010, 1, w(0x4D), vec![dev], vec![t2.create(w(0x4D))]);
    let e = t2.buy_tok(w(0x49), pctr(5.5753)); c.tx(1014, 2, w(0x49), vec![e], vec![]);
    let e = t2.buy_tok(w(0xE3), pctr(8.0)); c.tx(1015, 50, w(0xE3), vec![e], vec![]);
    let arm2 = c.stage("presend_live_shape", "arm").pop().unwrap();
    assert!(arm2["mint"] == b58(&t2.mint) && arm2["would"] == true && arm2["hit"]["el"] == 5.575 && arm2["hit"]["n"] == 1 && arm2["hit"]["sum"] == -0.15, "{arm2}");
    assert!(c.lines.iter().any(|x| x.contains("PRESEND LIVE SHAPE (log) arm")));
    // a 0.001% different size is another el
    let g = c.p.l38.sl.lock().unwrap();
    assert!(g.view(&el_of(pctr(5.5753) as i64), 1_015_000_050).blocks(SH_LOSS, SH_WIN) && !g.view(&el_of(pctr(5.5763) as i64), 1_015_000_050).blocks(SH_LOSS, SH_WIN));
    // after 6 h: forgotten
    assert_eq!(g.view(&5575, t0 + SH_WIN_NS + 2).n, 0);
    drop(g);
    zr.learn(50_000_000, t0 + 1);
    assert!(!c.p.l38.sl.lock().unwrap().view(&5575, t0 + 2).blocks(SH_LOSS, SH_WIN), "a win >= 0.05: protected");
    let end = c.p.finish(1020, None);
    assert!(end["dip38_log"]["shape_would"][0] == 1 && end["dip38_log"]["shape_keys"] == 3, "{}", end["dip38_log"]);
    let s: Led<u32> = led_load(&shp, SH_WIN_NS).unwrap();
    assert!(s.m.contains_key(&5575) && s.m.contains_key(&26640) && s.m.contains_key(&4000));
}

/// the ledgers' arithmetic and files
#[test]
fn dip38_ledgers() {
    let mut l: Led<u32> = Led::new(SH_WIN_NS);
    let t = 10 * SH_WIN_NS;
    l.add(5575, t, -60_000_000);
    assert!(!l.view(&5575, t).blocks(SH_LOSS, SH_WIN), "-0.06 > -0.10");
    l.add(5575, t + 1, -40_000_000);
    let v = l.view(&5575, t + 2);
    assert!(v == LView { n: 2, sum: -100_000_000, best: -40_000_000 } && v.blocks(SH_LOSS, SH_WIN), "exactly -0.10 blocks");
    assert_eq!(l.view(&5575, t - 1).n, 0, "never a position later than the check");
    assert_eq!(l.view(&5575, t + SH_WIN_NS + 1).n, 1, "the window: the second position is still in");
    assert_eq!(l.view(&5575, t + SH_WIN_NS + 2).n, 0, "the window");
    l.add(5575, t + SH_WIN_NS + 5, -1);
    assert_eq!(l.m[&5575].len(), 1, "old positions dropped on add");
    assert!(<u32 as LKey>::kp("5.575") == Some(5575) && 5575u32.ks() == "5.575" && 26640u32.ks() == "26.640" && <u32 as LKey>::kp("x").is_none());
    assert_eq!(el_of(pctr(5.5753) as i64), 5575);
    let p = tmp("led.json");
    let mut f: Led<Pk> = Led::new(FL_WIN_NS);
    f.add(w(1), 5, -7);
    f.add(w(2), 6, 8);
    led_save(&f, &p, "family").unwrap();
    let g: Led<Pk> = led_load(&p, FL_WIN_NS).unwrap();
    assert!(g.m.len() == 2 && g.view(&w(1), 6).sum == -7);
    std::fs::write(&p, r#"{"l": {"nope": [[1, 2]]}}"#).unwrap();
    assert!(led_load::<Pk>(&p, FL_WIN_NS).is_err());
    // a bad state file refuses the start; a missing one starts empty
    let c = cfg(&["--presend-live-insider-log", "on", "--presend-live-family-state", &p]).unwrap().unwrap();
    assert!(L38::new(&c, None).is_err());
    let c = cfg(&["--presend-live-insider-log", "on", "--presend-live-family-state", &tmp("nofile.json")]).unwrap().unwrap();
    assert!(L38::new(&c, None).is_ok_and(|l| l.fl.lock().unwrap().m.is_empty()));
}

/// the hot path never waits: a full queue drops the wallet (counted) and asks it again at the next sight; known / pending / our own
/// wallet are never queued; a failed chain is asked again after FUND_RETRY_S
#[test]
fn dip38_queue_never_blocks() {
    let mut c = Ctx::new(&["--presend-live-insider-log", "on"]);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<Pk>(2);
    c.p.l38.q = None;
    c.p.l38.tx = Some(tx);
    let t0 = Instant::now();
    for k in 1..=5 { c.p.l38_ask(w(k)); }
    c.p.l38_ask(USER);
    c.p.l38_ask(w(1));
    assert!(t0.elapsed() < Duration::from_millis(50));
    assert!(c.p.l38.st.asked == 2 && c.p.l38.st.dropped == 3 && c.p.l38.pending.len() == 2, "{:?}", c.p.l38.st);
    assert_eq!((rx.try_recv().ok(), rx.try_recv().ok()), (Some(w(1)), Some(w(2))));
    c.p.l38_ask(w(3));
    assert_eq!(rx.try_recv().ok(), Some(w(3)), "a dropped wallet: asked again at its next sight");
    c.p.l38.chains.insert(w(4), ch(&[]));
    c.p.l38_ask(w(4));
    assert!(rx.try_recv().is_err(), "known: never again");
    c.p.l38.chains.insert(w(5), Arc::new(Chain { st: FSt::Fail, n: 0, t: unix_s() - FUND_RETRY_S - 1, links: vec![], err: None }));
    c.p.l38_ask(w(5));
    assert_eq!(rx.try_recv().ok(), Some(w(5)), "a stale failure: asked again");
}

// ---- the resolver on a tape ---------------------------------------------------------------------------------------------------------

struct Tape { sigs: FxHashMap<Pk, Vec<SigI>>, txs: FxHashMap<String, serde_json::Value>, fail: Option<Pk>, calls: std::sync::atomic::AtomicU64 }
impl FundSrc for Tape {
    fn sigs(&self, a: &Pk, before: Option<String>) -> impl std::future::Future<Output = std::result::Result<Vec<SigI>, String>> + Send {
        self.calls.fetch_add(1, Ordering::Relaxed);
        let r = if self.fail == Some(*a) { Err("429 forever".to_string()) } else {
            let all = self.sigs.get(a).cloned().unwrap_or_default();
            let from = before.and_then(|b| all.iter().position(|s| s.sig == b).map(|i| i + 1)).unwrap_or(0);
            Ok(all.into_iter().skip(from).take(1000).collect())
        };
        async move { r }
    }
    fn tx(&self, sig: &str) -> impl std::future::Future<Output = std::result::Result<serde_json::Value, String>> + Send {
        self.calls.fetch_add(1, Ordering::Relaxed);
        let r = Ok(self.txs.get(sig).cloned().unwrap_or(serde_json::Value::Null));
        async move { r }
    }
}
/// `n` signatures of `a` (newest first) `span` s apart in all; the oldest ones named a-0, a-1, ...
fn sigs_of(a: &Pk, n: usize, span: i64) -> Vec<SigI> {
    let step = if n > 1 { span / (n as i64 - 1) } else { 0 };
    (0..n).rev().map(|i| SigI { sig: format!("{}-{i}", &b58(a)[..6]), slot: 1000 + i as u64, bt: Some(1_762_000_000 + i as i64 * step), ok: true }).collect()
}
fn xfer(src: &Pk, dst: &Pk, lam: u64, inner: bool, create: bool) -> serde_json::Value {
    let ix = if create { serde_json::json!({"parsed": {"type": "createAccount", "info": {"source": b58(src), "newAccount": b58(dst), "lamports": lam}}, "program": "system"}) }
        else { serde_json::json!({"parsed": {"type": "transfer", "info": {"source": b58(src), "destination": b58(dst), "lamports": lam}}, "program": "system"}) };
    if inner { serde_json::json!({"transaction": {"message": {"instructions": [{"programId": "x", "data": "y"}]}}, "meta": {"innerInstructions": [{"index": 0, "instructions": [ix]}]}}) }
    else { serde_json::json!({"transaction": {"message": {"instructions": [ix]}}, "meta": {"innerInstructions": []}}) }
}

#[test]
fn dip38_resolver_walk() {
    let (wal, hub, pass, l, small, deep, bad) = (w(0x10), w(0x8D), w(0xEB), w(0x4C), w(0x51), w(0xDE), w(0xBA));
    let mut t = Tape { sigs: FxHashMap::default(), txs: FxHashMap::default(), fail: Some(bad), calls: Default::default() };
    // the wallet: 3 txs; its oldest from an exchange hub (0.9 SOL), its 2nd from a pass-through (17.8 SOL, inner createAccount), a dust 0.01
    t.sigs.insert(wal, sigs_of(&wal, 3, 600));
    t.txs.insert(format!("{}-0", &b58(&wal)[..6]), xfer(&hub, &wal, 900_000_000, false, false));
    t.txs.insert(format!("{}-1", &b58(&wal)[..6]), xfer(&pass, &wal, 17_800_000_000, true, true));
    t.txs.insert(format!("{}-2", &b58(&wal)[..6]), xfer(&small, &wal, 10_000_000, false, false));
    t.sigs.insert(hub, sigs_of(&hub, 1000, 86_400));
    t.sigs.insert(pass, sigs_of(&pass, 2, 30));
    t.txs.insert(format!("{}-0", &b58(&pass)[..6]), xfer(&l, &pass, 18_000_000_000, false, false));
    t.sigs.insert(l, sigs_of(&l, 1000, 3_600));
    // a busy wallet: 2,000+ txs (its history start not reached in 2 pages)
    t.sigs.insert(deep, sigs_of(&deep, 2500, 86_400 * 30));
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let mut r = Resolver::new(t);
    let c = rt.block_on(r.resolve(&wal, 77));
    assert!(c.st == FSt::Ok && c.n == 3 && c.t == 77 && c.err.is_none(), "{c:?}");
    assert_eq!(c.links, vec![Link { a: hub, kind: Kind::Hub, hops: 0 }, Link { a: pass, kind: Kind::Oneshot, hops: 0 }, Link { a: l, kind: Kind::Hub, hops: 1 }], "dust out, hubs kept");
    assert_eq!(c.summary(&wal, 2), format!("{}<-{}<-{}", &b58(&wal)[..8], &b58(&pass)[..8], &b58(&l)[..8]));
    let calls1 = r.calls;
    let c = rt.block_on(r.resolve(&deep, 78));
    assert!(c.st == FSt::Deep && c.n == 2000 && c.links.is_empty() && r.calls == calls1 + 2, "2 pages then deep: {c:?}");
    let c = rt.block_on(r.resolve(&bad, 79));
    assert!(c.st == FSt::Fail && c.err.as_deref() == Some("429 forever"));
    // the kinds are cached across wallets: the same wallet again costs only its own reads
    let calls2 = r.calls;
    let _ = rt.block_on(r.resolve(&wal, 80));
    assert_eq!(r.calls - calls2, 1 + 3 + 2, "its signatures + its 3 txs + the pass-through's 2 txs (kinds cached, its page kept)");
    // json / state file round trip (a failure is not saved)
    let mut m = Chains::default();
    m.insert(wal, Arc::new(rt.block_on(r.resolve(&wal, 81))));
    m.insert(bad, Arc::new(rt.block_on(r.resolve(&bad, 82))));
    let p = tmp("fundrt.json");
    assert_eq!(fund_save(&m, &p, "t").unwrap(), 1);
    let back = fund_load(&p).unwrap();
    assert!(back.len() == 1 && *back[&wal] == *m[&wal]);
    assert!(Chain::from_json(&serde_json::json!({"st": "ok", "chain": [["bad", "hub", 0]]})).is_none());
    assert!(!back[&wal].stale(u64::MAX / 2) && Chain { st: FSt::Deep, n: 0, t: 0, links: vec![], err: None }.stale(FUND_DEEP_RETRY_S));
    // Kind::of: <= 5 oneshot; 1,000 within 2 days hub; 1,000 over a week normal
    assert!(Kind::of(&sigs_of(&hub, 5, 10)) == Kind::Oneshot && Kind::of(&sigs_of(&hub, 1000, 86_400)) == Kind::Hub && Kind::of(&sigs_of(&hub, 1000, 7 * 86_400)) == Kind::Normal);
    // sigs_parse
    let s = sigs_parse(&serde_json::json!([{"signature": "a", "slot": 5, "err": null, "blockTime": 9}, {"signature": "b", "slot": 4, "err": {"x": 1}, "blockTime": null}])).unwrap();
    assert!(s[0].ok && !s[1].ok && s[1].bt.is_none());
}

/// the study's seed (fund_seed.py over /home/it/sniper-data/antibait/resolve_*.json) loads, and dtrz's helpers carry dtrzJPj7 in
/// their chains (skipped when the seed was not built on this machine)
#[test]
fn dip38_seed_file() {
    let p = "/home/it/sniper-data/antibait/fund_seed.json";
    if !std::path::Path::new(p).exists() { eprintln!("{p} missing: skipped"); return; }
    let m = fund_load(p).unwrap();
    let k = |s: &str| -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() };
    let dtrz = k("dtrzJPj7yDdvm6eRqBAgxsK2sMJeD9HhBEBB3XMedXy");
    for h in ["AG9E49eux4V4BdPUAvDJTeeVnb951Sreg9mF3yaRFnWB", "CwG4WsHeH4eQ1awX4nKV2Vk65YyoUxNgdaVQNSkDJFEf", "zFxVT1MUG4onferPyiHY5ewLL8zMia1qiSTqxGQCRpm"] {
        assert!(m.get(&k(h)).is_some_and(|c| c.find(&dtrz).is_some()), "{h}");
    }
}

/// HOT PATH cost (run: cargo test --release --bin snipe_engine dip38_hot_path -- --ignored --nocapture): on_exec per trade with the logs off /
/// on over 200 tokens (2 armed), 40,000 trades
#[test]
#[ignore]
fn dip38_hot_path_bench() {
    let run = |extra: &[&str]| -> (f64, f64, f64) {
        let mut c = Ctx::new(extra);
        let mut tks: Vec<Tk> = (0..200u32).map(|i| { let mut t = Tk::new(0x80); t.mint[1] = i as u8; t.mint[2] = (i >> 8) as u8; t.launch = snipe_build::launch_from_target(t.mint, CREATOR); t }).collect();
        for t in &tks { c.launches.push(t.launch.clone()); }
        for (i, t) in tks.iter_mut().enumerate() { let e = t.buy(w(0x4C), S / 2); let cr = t.create(w(0x4C)); c.tx(1000, i as u64, w(0x4C), vec![e], vec![cr]); }
        // two armed windows, each with 3 other holders >= 3% (one of them a known chain)
        for (j, t) in tks.iter_mut().take(2).enumerate() {
            for h in 0..3u8 { let e = t.buy_tok(w(0x60 + h), pctr(3.5)); c.tx(1002, 10 + h as u64, w(0x60 + h), vec![e], vec![]); }
            let e = t.buy_tok(w(0xEE), pctr(8.0)); c.tx(1003, 1 + j as u64, w(0xEE), vec![e], vec![]);
        }
        c.p.l38.chains.insert(w(0x61), ch(&[(w(0x8D), Kind::Hub, 0), (w(0xEB), Kind::Oneshot, 0), (w(0x4C), Kind::Hub, 1)]));
        // a logged send (drain_atts' stage "send": the event loop, never the sender thread): 1,000 slots x the armed windows
        let ids: Vec<u64> = c.p.armed.values().copied().collect();
        assert_eq!(ids.len(), 2);
        let t0 = Instant::now();
        let mut k = 0u64;
        for s in 0..1000u64 { for id in &ids { c.p.l38_send(*id, 1003 + s); k += 1; } }
        let send_us = t0.elapsed().as_secs_f64() * 1e6 / k as f64;
        for _ in c.orx.try_iter() {}
        if let Some(q) = c.p.l38.q.as_mut() { q.clear(); }
        let (mut us, mut n) = (Vec::new(), 0u64);
        for k in 0..40_000u64 {
            let i = (k * 7919) as usize % tks.len();
            let u = { let mut x = [0u8; 32]; x[..8].copy_from_slice(&(k % 997).to_le_bytes()); x[31] = 0x77; x };
            let e = if k % 3 == 0 && tks[i].t < 1_000_000_000_000_000 { tks[i].sell_tok(u, 1_000_000_000) } else { tks[i].buy(u, 1_000_000) };
            let slot = 1004 + k / 400;
            let x = arbx::feeds::ExecInfo { index: k, fee: 5_000, ok: true, trades: vec![e], creates: vec![], mayhem: false };
            let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&k.to_le_bytes());
            let a = arbx::feeds::Arrival { feed: 0, slot, t_rx: slot * 1_000_000 + k, t_decoded: 0, executed: Some(true), tx: arbx::tx::Tx { sig, keys: vec![u], ..Default::default() },
                poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
            let ls = &c.launches;
            let t0 = Instant::now();
            c.p.on_exec(&a, &x, slot, |m: &Pk| ls.iter().find(|l| l.mint == *m).cloned(), &|_| false, None);
            us.push(t0.elapsed().as_secs_f64() * 1e6);
            n += 1;
            if k % 1000 == 0 { for _ in c.orx.try_iter() {} let _ = c.p.take_cmds(); if let Some(q) = c.p.l38.q.as_mut() { q.clear(); } }
        }
        us.sort_by(|a, b| a.total_cmp(b));
        let mean = us.iter().sum::<f64>() / n as f64;
        (mean, us[us.len() / 2], send_us)
    };
    for _ in 0..2 { let _ = run(&[]); }
    let off = run(&[]);
    let on = run(&["--presend-live-insider-log", "on", "--presend-live-shape-log", "on"]);
    let bl = list("bench", &[w(0x99)]);
    let blo = run(&["--presend-live-blocklist", &bl, "--presend-live-blocklist-launcher", "off"]);
    let bll = run(&["--presend-live-blocklist", &bl]);
    eprintln!("DIP38 HOT PATH on_exec per trade (mean / p50 us): logs off {:.3} / {:.3} | insider+shape logs on {:.3} / {:.3} (+{:.3} mean) | blocklist {:.3} / {:.3} vs + launcher match {:.3} / {:.3}",
        off.0, off.1, on.0, on.1, on.0 - off.0, blo.0, blo.1, bll.0, bll.1);
    eprintln!("DIP38 a logged send slot (stage \"send\" records of both logs, event loop; 4 candidates, 3 holders >= 3%): logs off {:.3} us, on {:.3} us", off.2, on.2);
}

/// the real resolver against the public RPC (read-only; run: cargo test --bin snipe_engine dip38_resolver_public_rpc -- --ignored --nocapture):
/// dtrz's helper AG9E49eu (REPORT §4a: funded 18.03 SOL by dtrzJPj7 through the 2-tx pass-through EukVZRhF) resolves to a chain holding
/// dtrzJPj7 at hop 1
#[test]
#[ignore]
fn dip38_resolver_public_rpc() {
    let k = |s: &str| -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() };
    let (h, pass, dtrz) = (k("AG9E49eux4V4BdPUAvDJTeeVnb951Sreg9mF3yaRFnWB"), k("EukVZRhFLKxKK5izrHwu8yCj7mx9VjDeHQms1ZVLHJPf"), k("dtrzJPj7yDdvm6eRqBAgxsK2sMJeD9HhBEBB3XMedXy"));
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let sh = Arc::new(FundShared::default());
    let mut r = Resolver::new(RpcSrc::new(FUND_RPC.to_string(), FUND_RPS, sh.clone()));
    let t0 = Instant::now();
    let c = rt.block_on(r.resolve(&h, unix_s()));
    eprintln!("AG9E49eu: {:?} n {} in {:.1} s, {} calls ({} 429) | {:?}", c.st, c.n, t0.elapsed().as_secs_f64(), sh.calls.load(Ordering::Relaxed), sh.r429.load(Ordering::Relaxed),
        c.links.iter().map(|l| format!("{} {} {}", &b58(&l.a)[..8], l.kind.s(), l.hops)).collect::<Vec<_>>());
    if c.st == FSt::Deep { eprintln!("deep now (the wallet traded > 2,000 txs since the study): nothing to check"); return; }
    assert_eq!(c.st, FSt::Ok, "{:?}", c.err);
    let i = c.find(&dtrz).expect("dtrzJPj7 in the chain");
    assert!(c.links[i].hops == 1 && c.find(&pass).is_some(), "{:?}", c.links);
}
