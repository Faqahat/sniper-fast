// ===================================================================================================================
// dip36 LIVE WALLET BLOCKLIST tests (11-05 PKT; psblock.rs): --presend-live-blocklist PATH [--presend-live-blocklist-pct X].
// Off: nothing of it runs. On: the T2 whale / re-arm dumper / a holder >= X% listed -> the arm is skipped ("blocklist" /
// "rearm_blocklist", bl_wallet / bl_role / bl_pct); not listed -> the arm as without the flag; the 3% boundary; the file's reload.
// ===================================================================================================================
use super::*;
use super::psblock::*;
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
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }
fn pct(x: f64) -> u64 { (x / 100.0 * pl::SUPPLY) as u64 }
fn w(k: u8) -> Pk { let mut x = [k; 32]; x[31] = 0x36; x }
fn list(path_tag: &str, ws: &[Pk]) -> String {
    let p = std::env::temp_dir().join(format!("dip36-bl-{}-{path_tag}.json", std::process::id()));
    std::fs::write(&p, serde_json::json!({"version": 3, "wallets": ws.iter().map(|k| serde_json::json!({"w": b58(k), "why": "test"})).collect::<Vec<_>>()}).to_string()).unwrap();
    p.to_string_lossy().to_string()
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
    fn create(&self) -> CreateEvent { CreateEvent { mint: self.mint, bonding_curve: self.launch.bonding_curve, user: CREATOR, creator: CREATOR } }
}

struct Ctx { p: PsLive, orx: crossbeam_channel::Receiver<Out>, launches: Vec<Launch>, recs: Vec<serde_json::Value>, lines: Vec<String> }
impl Ctx {
    fn new(extra: &[&str]) -> Ctx { let (p, _a, orx) = PsLive::for_test(cfg(extra).unwrap().unwrap(), USER); Ctx { p, orx, launches: Vec::new(), recs: Vec::new(), lines: Vec::new() } }
    fn tx(&mut self, slot: u64, idx: u64, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&slot.to_be_bytes()); sig[8..16].copy_from_slice(&idx.to_be_bytes()); sig[16] = 0xB7;
        let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades, creates, mayhem: false };
        let a = arbx::feeds::Arrival { feed: 0, slot, t_rx: slot * 1_000_000 + idx, t_decoded: slot * 1_000_000 + idx, executed: Some(true),
            tx: arbx::tx::Tx { sig, keys: vec![[0x77; 32]], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        let ls = self.launches.clone();
        self.p.on_arrival(&a, slot);
        self.p.on_exec(&a, &x, slot, move |m: &Pk| ls.iter().find(|l| l.mint == *m).cloned(), &|_| false, None);
        for o in self.orx.try_iter() { match o { Out::Rec(v) => self.recs.push(v), Out::Line(l) => self.lines.push(l) } }
    }
    fn ev(&self, k: &str) -> Vec<serde_json::Value> { self.recs.iter().filter(|r| r["ev"] == k).cloned().collect() }
    /// T2: a token created at 1000 (dev buy), `h` buys `h_tok` raw at 1001, others trade, the whale's 2 SOL buy at 1005 (>= 6%: a trigger)
    fn t2(&mut self, h: Pk, h_tok: u64, whale: Pk) -> Tk {
        let mut tk = Tk::new(0x61);
        self.launches.push(tk.launch.clone());
        let dev = tk.buy(CREATOR, S / 2);
        self.tx(1000, 1, vec![dev], vec![tk.create()]);
        let e = tk.buy_tok(h, h_tok);
        self.tx(1001, 2, vec![e], vec![]);
        let e = tk.buy(w(0x11), S / 10);
        self.tx(1003, 2, vec![e], vec![]);
        let e = tk.buy(whale, 2 * S);
        self.tx(1005, 50, vec![e], vec![]);
        tk
    }
    /// re-arm: create-slot buys of a 7% / b 8%, a dumps at 1005, the check at the first tx of 1008 (a filler token moves the clock)
    fn rearm(&mut self, a: Pk, b: Pk) -> Tk {
        let mut tk = Tk::new(0x62);
        let mut z = Tk::new(0x63);
        self.launches.push(tk.launch.clone());
        self.launches.push(z.launch.clone());
        let dev = tk.buy(CREATOR, S / 2);
        self.tx(1000, 1, vec![dev], vec![tk.create()]);
        let e = tk.buy_tok(a, pct(7.0)); self.tx(1000, 2, vec![e], vec![]);
        let e = tk.buy_tok(b, pct(8.0)); self.tx(1000, 3, vec![e], vec![]);
        let dz = z.buy(CREATOR, S / 2);
        self.tx(1000, 4, vec![dz], vec![z.create()]);
        for s in 1001..=1004 { let e = tk.buy(w(0x33), S / 10); self.tx(s, 5, vec![e], vec![]); }
        let d = tk.sell_tok(a, pct(7.0));
        self.tx(1005, 5, vec![d], vec![]);
        for s in 1006..=1008 { let e = z.buy(w(0x2F), 1_000_000); self.tx(s, 900, vec![e], vec![]); }
        tk
    }
}

#[test]
fn dip36_blocklist_flags() {
    let p = list("flags", &[w(1)]);
    let c0 = cfg(&[]).unwrap().unwrap();
    assert!(c0.blocklist.is_none() && c0.blocklist_pct == 3.0 && c0.json().get("blocklist").is_none(), "off by default: dip35's start record");
    let c = cfg(&["--presend-live-blocklist", &p]).unwrap().unwrap();
    assert!(c.blocklist.as_deref() == Some(p.as_str()) && c.blocklist_pct == 3.0 && c.json()["blocklist"]["holder_pct"] == 3.0);
    let c = cfg(&["--presend-live-blocklist", &p, "--presend-live-blocklist-pct", "4.5"]).unwrap().unwrap();
    assert_eq!(c.blocklist_pct, 4.5);
    for (a, needle) in [(&["--presend-live-blocklist-pct", "4"][..], "needs --presend-live-blocklist PATH"), (&["--presend-live-blocklist"][..], "needs a path"),
        (&["--presend-live-blocklist", &p, "--presend-live-blocklist-pct", "0"][..], "(0, 100]"), (&["--presend-live-blocklist", &p, "--presend-live-blocklist-pct", "101"][..], "(0, 100]")] {
        let e = cfg(a).unwrap_err().to_string();
        assert!(e.contains(needle), "{a:?}: {e}");
    }
    for f in ["--presend-live-blocklist", "--presend-live-blocklist-pct"] {
        let e = Cfg::from_argv(&["snipe_engine", "--dip", "--presend-shadow", f, "1"].iter().map(|s| s.to_string()).collect::<Vec<_>>(), &arbx::presend::Params::default(), true, 1_000_000_000)
            .unwrap_err().to_string();
        assert!(e.contains("needs --presend-live"), "{f}: {e}");
    }
    assert!(crate::check_flags(&args(&["--presend-live-blocklist", "/root/dip/blocklist_ams.json", "--presend-live-blocklist-pct", "3"])).is_ok());
    assert!(crate::check_flags(&args(&["--presend-live-blocklist", "/x", "--presend-live-blocklist-pct", "abc"])).is_err(), "a number");
    // the seed file parses: 4 full keys
    let seed = std::fs::read(concat!(env!("CARGO_MANIFEST_DIR"), "/ops/prod/blocklist_ams.json")).unwrap();
    let (m, v) = bl_parse(&seed).unwrap();
    assert!(m.len() == 4 && v == 1 && m.contains_key(&<Pk>::try_from(&bs58::decode("8ZN71XTdVo8yRovnGLmNgW3Tgniw6A4J3JGLvPD686FP").into_vec().unwrap()[..]).unwrap()));
}

#[test]
fn dip36_blocklist_parse_and_reload() {
    assert!(bl_parse(br#"{"wallets": []}"#).unwrap().0.is_empty(), "an empty list is valid");
    for bad in [&br#"{"wallets": [{"w": "nope"}]}"#[..], br#"{"wallets": [{"why": "x"}]}"#, b"{}", b"[", br#"{"wallets": [{"w": "11111111111111111111111111111111111"}]}"#] {
        assert!(bl_parse(bad).is_err(), "{}", String::from_utf8_lossy(bad));
    }
    let p = list("reload", &[w(1)]);
    let mut b = Blocklist::load(&p).unwrap();
    assert!(b.set.len() == 1 && b.ver == 3 && b.check(false).is_none(), "unchanged: nothing");
    std::fs::write(&p, serde_json::json!({"version": 4, "wallets": [{"w": b58(&w(1))}, {"w": b58(&w(2)), "why": "b"}]}).to_string()).unwrap();
    let r = b.check(true).unwrap();
    assert!(r["ok"] == true && r["n"] == 2 && r["was"] == 1 && b.set.len() == 2 && b.ver == 4 && b.set[&w(2)] == "b", "{r}");
    std::fs::write(&p, "{\"wallets\": [{\"w\": \"bad\"}]}").unwrap();
    let r = b.check(true).unwrap();
    assert!(r["ok"] == false && r["kept"] == 2 && b.set.len() == 2 && b.fails == 1, "a bad file keeps the last good list: {r}");
    std::fs::remove_file(&p).unwrap();
    let r = b.check(true).unwrap();
    assert!(r["ok"] == false && b.set.len() == 2, "a missing file too: {r}");
    assert!(Blocklist::load(&p).is_err(), "missing at the start: refused");
    // full-key matching: a key with the same first bytes is not a hit
    let mut near = w(1); near[31] ^= 1;
    assert!(b.hit((&near, "whale", 0), &[], 1).is_none());
    assert!(b.hit((&w(1), "whale", pct(7.0) as i64), &[], 1).is_some_and(|h| h.1 == "whale" && (h.2 - 7.0).abs() < 1e-9));
    assert_eq!(bl_min(3.0), 30_000_000_000_000);
}

/// T2: whale listed -> skip "blocklist" (role whale); a listed holder at exactly 3.0% -> skip (holder); just under 3% -> armed; not
/// listed -> armed, every record as without the flag
#[test]
fn dip36_blocklist_t2_roles_and_boundary() {
    let (h, whale) = (w(0x41), w(0xEE));
    let run = |extra: &[&str], h_tok: u64| { let mut c = Ctx::new(extra); c.t2(h, h_tok, whale); c };
    let three = pct(3.0);
    assert_eq!(three, 30_000_000_000_000);
    // off
    let c0 = run(&[], three);
    assert_eq!(c0.ev("presend_live_arm").len(), 1, "{:?}", c0.recs);
    // the whale listed
    let pw = list("t2w", &[whale]);
    let c = run(&["--presend-live-blocklist", &pw], three);
    assert!(c.ev("presend_live_arm").is_empty() && c.p.armed.is_empty());
    let s = c.ev("presend_live_skip").pop().unwrap();
    assert!(s["why"] == "blocklist" && s["bl_wallet"] == b58(&whale) && s["bl_role"] == "whale" && s["bl_pct"].as_f64().unwrap() > 6.0 && s["bl_why"] == "test", "{s}");
    assert!(c.lines.iter().any(|l| l.contains("PRESEND LIVE BLOCKLIST SKIP")) && c.p.bl.as_ref().unwrap().skips == 1);
    // a holder at exactly 3.0%: skipped
    let ph = list("t2h", &[h]);
    let c = run(&["--presend-live-blocklist", &ph], three);
    let s = c.ev("presend_live_skip").pop().expect("skipped");
    assert!(s["why"] == "blocklist" && s["bl_role"] == "holder" && s["bl_wallet"] == b58(&h) && s["bl_pct"] == 3.0 && c.ev("presend_live_arm").is_empty(), "{s}");
    // just under 3%: armed (and at a 2.5% threshold: skipped)
    let c = run(&["--presend-live-blocklist", &ph], three - 1);
    assert!(c.ev("presend_live_arm").len() == 1 && c.ev("presend_live_skip").is_empty());
    let c = run(&["--presend-live-blocklist", &ph, "--presend-live-blocklist-pct", "2.5"], three - 1);
    assert!(c.ev("presend_live_arm").is_empty() && c.ev("presend_live_skip")[0]["bl_role"] == "holder");
    // nobody listed: the same records as without the flag
    let pn = list("t2n", &[w(0x99)]);
    let c = run(&["--presend-live-blocklist", &pn], three);
    let strip = |v: &Vec<serde_json::Value>| -> Vec<String> { v.iter().map(|r| r.to_string()).collect() };
    assert_eq!(strip(&c.recs), strip(&c0.recs), "not listed: no change");
}

/// re-arm: the dumper listed -> "rearm_blocklist" (role dumper); the remaining 8% holder listed -> (role holder); nobody -> armed
#[test]
fn dip36_blocklist_rearm_roles() {
    let (a, b) = (w(0xA1), w(0xB1));
    let run = |extra: &[&str]| { let mut x = vec!["--presend-live-rearm", "on"]; x.extend_from_slice(extra); let mut c = Ctx::new(&x); c.rearm(a, b); c };
    let c0 = run(&[]);
    assert!(c0.ev("presend_live_arm").iter().any(|r| r["kind"] == "rearm"), "{:?}", c0.recs.iter().map(|r| r["ev"].clone()).collect::<Vec<_>>());
    let pa = list("rad", &[a]);
    let c = run(&["--presend-live-blocklist", &pa]);
    assert!(!c.ev("presend_live_arm").iter().any(|r| r["kind"] == "rearm"));
    let s = c.ev("presend_live_skip").into_iter().find(|r| r["why"] == "rearm_blocklist").expect("skipped");
    assert!(s["kind"] == "rearm" && s["bl_role"] == "dumper" && s["bl_wallet"] == b58(&a) && s["bl_pct"] == 0.0, "the dumper sold out: {s}");
    let pb = list("rah", &[b]);
    let c = run(&["--presend-live-blocklist", &pb]);
    let s = c.ev("presend_live_skip").into_iter().find(|r| r["why"] == "rearm_blocklist").expect("skipped");
    assert!(s["bl_role"] == "holder" && s["bl_wallet"] == b58(&b) && s["bl_pct"] == 8.0, "{s}");
    let pn = list("ran", &[w(0x99)]);
    let c = run(&["--presend-live-blocklist", &pn]);
    let strip = |v: &Vec<serde_json::Value>| -> Vec<String> { v.iter().map(|r| r.to_string()).collect() };
    assert_eq!(strip(&c.recs), strip(&c0.recs), "not listed: no change");
}
