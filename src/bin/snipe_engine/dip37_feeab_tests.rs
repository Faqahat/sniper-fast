// ===================================================================================================================
// dip37 FEE A/B tests (11-04; psfeeab.rs): --presend-live-fee-ab on|off, --presend-live-ab-cu-price-micro / -cu-limit / -tip-lamports,
// --presend-live-ab-clients, --presend-live-ab-split. OFF: every attempt byte and record as dip36. ON: the window's arm once at its arm
// (id parity / UTC hour parity), the client rule per attempt (Jito and unlisted leaders get A's values), the CU limit / price / tip in the
// signed attempt, the records' fee fields, the per-arm counters and the realized tag.
// ===================================================================================================================
use super::*;
use super::psfeeab::*;
use arbx::dip::{CreateEvent, TradeEvent};

const USER: Pk = [0x5Au8; 32];
const CREATOR: Pk = [0xC1u8; 32];
const S: u64 = 1_000_000_000;
const ON: [&str; 4] = ["--presend-live-fee-ab", "on", "--presend-live-ab-cu-price-micro", "20000"];

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }
fn on(extra: &[&str]) -> Cfg { let mut v: Vec<&str> = ON.to_vec(); v.extend_from_slice(extra); cfg(&v).unwrap().unwrap() }
fn helius() -> Vec<Pk> { send::known_tip_accounts(config::SendKind::Helius).iter().map(|a| pk(a)).collect() }
fn ix_u32(ix: &build::Ix) -> u32 { u32::from_le_bytes(ix.data[1..5].try_into().unwrap()) }
fn ix_u64(ix: &build::Ix) -> u64 { u64::from_le_bytes(ix.data[1..9].try_into().unwrap()) }
/// a system transfer's lamports (instruction 2: u32 tag, u64 lamports)
fn tip_of(ix: &build::Ix) -> u64 { u64::from_le_bytes(ix.data[4..12].try_into().unwrap()) }

struct Tk { mint: Pk, v: u64, t: u64, launch: Launch }
impl Tk {
    fn new(k: u8) -> Tk { let mint = [k; 32]; Tk { mint, v: 30 * S, t: 1_073_000_000_000_000, launch: snipe_build::launch_from_target(mint, CREATOR) } }
    fn buy(&mut self, user: Pk, sol: u64) -> TradeEvent {
        let q = (self.t as u128 * sol as u128 / (self.v + sol) as u128) as u64;
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

struct Ctx { p: PsLive, atx: crossbeam_channel::Sender<Att>, orx: crossbeam_channel::Receiver<Out>, launches: Vec<Launch>, recs: Vec<serde_json::Value>, lines: Vec<String>,
             cmds: Vec<Cmd>, seq: u64 }
impl Ctx {
    fn with(c: Cfg) -> Ctx { let (p, atx, orx) = PsLive::for_test(c, USER); Ctx { p, atx, orx, launches: Vec::new(), recs: Vec::new(), lines: Vec::new(), cmds: Vec::new(), seq: 0 } }
    fn tx_sig(&mut self, slot: u64, idx: u64, sig: [u8; 64], payer: Pk, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades, creates, mayhem: false };
        let a = arbx::feeds::Arrival { feed: 0, slot, t_rx: slot * 1_000_000 + idx, t_decoded: slot * 1_000_000 + idx, executed: Some(true),
            tx: arbx::tx::Tx { sig, keys: vec![payer], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        let ls = self.launches.clone();
        self.p.on_arrival(&a, slot);
        self.p.on_exec(&a, &x, slot, move |m: &Pk| ls.iter().find(|l| l.mint == *m).cloned(), &|_| false, None);
        self.drain();
    }
    fn tx(&mut self, slot: u64, idx: u64, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&slot.to_be_bytes()); sig[8..16].copy_from_slice(&idx.to_be_bytes()); sig[16] = 0xD3; sig[17] = trades.first().map_or(0, |t| t.mint[0]);
        self.tx_sig(slot, idx, sig, [0x77; 32], trades, creates);
    }
    fn drain(&mut self) {
        for o in self.orx.try_iter() { match o { Out::Rec(v) => self.recs.push(v), Out::Line(l) => self.lines.push(l) } }
        self.cmds.extend(self.p.take_cmds());
    }
    fn ev(&self, k: &str) -> Vec<serde_json::Value> { self.recs.iter().filter(|r| r["ev"] == k).cloned().collect() }
    fn swin(&self, id: u64) -> SWin { self.p.sh.wins.lock().unwrap().iter().find(|s| s.id == id).cloned().unwrap() }
    /// a T2 token `k` created at `s0` (dev buy), a small buy at s0 + 3, the whale's 2 SOL buy at s0 + 5 (>= 6%: a trigger) -> its window id
    fn t2(&mut self, k: u8, s0: u64, whale: Pk) -> (Tk, u64) {
        let mut tk = Tk::new(k);
        self.launches.push(tk.launch.clone());
        let dev = tk.buy(CREATOR, S / 2);
        self.tx(s0, 1, vec![dev], vec![tk.create()]);
        let e = tk.buy([0x11; 32], S / 10);
        self.tx(s0 + 3, 2, vec![e], vec![]);
        let e = tk.buy(whale, 2 * S);
        self.tx(s0 + 5, 50, vec![e], vec![]);
        let w = *self.p.armed.get(&tk.mint).unwrap_or_else(|| panic!("armed: {:?} {:?}", self.p.st.skips, self.lines));
        (tk, w)
    }
    /// an attempt of window `w` on a `client` leader, its fee values as the sender takes them (psfeeab::att_fee) -> (signature, its fee)
    fn attempt(&mut self, w: u64, mint: Pk, slot: u64, client: &str) -> ([u8; 64], Option<AttFee>) {
        self.seq += 1;
        let mut sg = [0u8; 64]; sg[..8].copy_from_slice(&self.seq.to_be_bytes()); sg[8] = 0xD3; sg[9] = 0x7A;
        let (_, _, tip, fa) = att_fee(&self.p.cfg, self.swin(w).fab, client, Some((helius()[0], 200_000)));
        self.atx.send(Att { w, n: self.seq as u32, mint, sig: sg, tag: pl::PS_TAG | (0xD37A << 32) | self.seq, path: "helius-ps".into(), client: client.into(), slot, deadline: slot + 1,
            lim: 1.0, min_out: 1, p_sign: 1.0, sign_pos: (slot, 0, 0), t_send: slot * 1_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) },
            tip: tip.map_or(0, |t| t.1), wst: "written", ob6: 0.0, grd: Grd::default(), fa, bd: None }).unwrap();
        self.p.drain_atts();
        (sg, fa)
    }
}

fn sold(c: Option<u64>, sigs: &[&str], qty: u64) -> SellOut {
    SellOut { sold_at: c, sigs: sigs.iter().map(|s| (s.to_string(), true, 1_200_000)).collect(), last: None, attempts: sigs.len() as u32, last_qty: (qty, true), first_send_us: None }
}

/// signed attempt bytes (a fixed key and blockhash): what the sender writes
fn signed(ixs: &[build::Ix]) -> Vec<u8> {
    let user = pk("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE");
    build::sign(&build::compile_v0(user, ixs, [9u8; 32], &[], &[]).unwrap(), &SigningKey::from_bytes(&[7u8; 32]))
}

/// OFF (no flag) = dip36: the config, the start record, att_fee = the run's own values; every attempt's SIGNED BYTES equal dip36's build
/// (the run's cu_limit / cu_price, the path's tip with --presend-live-tip-lamports over it); with the A/B ON an arm-A attempt and an arm-B
/// attempt on a Jito / unlisted leader are those same bytes; no record field, no status part, no run_end block
#[test]
fn dip37_off_is_dip36_bytes_and_records() {
    let user = pk("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE");
    let c0 = cfg(&[]).unwrap().unwrap();
    assert!(c0.fab == FeeAbCfg::default() && !c0.fab.on && c0.json().get("fee_ab").is_none(), "off by default: dip36's start record");
    let ct = cfg(&["--presend-live-tip-lamports", "150000"]).unwrap().unwrap();
    let mut c = Ctx::with(c0.clone());
    let (_tk, w) = c.t2(0x71, 1000, [0xE1; 32]);
    let sw = c.swin(w);
    assert_eq!(sw.fab, None, "off: no arm");
    let arm = c.ev("presend_live_arm").pop().unwrap();
    assert!(arm.get("fee_arm").is_none() && arm.get("cu_price").is_none() && arm.get("tip").is_none(), "dip36's arm record: {arm}");
    let guard = guard_ix_enc(GuardEnc { disc: 15, op: 4, acct: true }, 1006);
    let (min_out, _, _) = att_limit(&sw, c0.drop).unwrap();
    let h = helius();
    let c_on = on(&["--presend-live-ab-cu-limit", "90000", "--presend-live-ab-tip-lamports", "300000"]);
    for cf in [&c0, &ct] {
        for client in ["JitoLabs", "AgaveBam", "HarmonicAgave", "Firedancer", "", "FireBAM"] {
            for pt in [Some((h[2], 200_000u64)), None] {
                // dip36's sender, line for line: the path's tip (the run's override over it), att_ixs with the run's CU values
                let tip36 = pt.map(|(a, l)| (a, cf.tip.unwrap_or(l)));
                let (ref_ixs, ref_roles) = att_ixs(user, &sw, min_out, cf, guard.clone(), tip36);
                let (lim, price, tip, fa) = att_fee(cf, sw.fab, client, pt);
                assert_eq!((lim, price, tip, fa), (cf.cu_limit, cf.cu_price, tip36, None), "{client}");
                let (ixs, roles) = att_ixs_fee(user, &sw, min_out, lim, price, guard.clone(), tip);
                assert_eq!(roles, ref_roles);
                assert_eq!(signed(&ixs), signed(&ref_ixs), "off: dip36's attempt bytes ({client}, {pt:?})");
                // an A/B config but the window carries no arm (never armed with it): still the run's own values
                assert_eq!(att_fee(cf, None, client, pt).3, None);
            }
        }
    }
    // A/B ON: arm A everywhere, arm B on a Jito / unlisted / unknown leader = the run's own bytes (only the fee fields differ)
    for (arm, client) in [(0u8, "AgaveBam"), (0, "JitoLabs"), (1, "JitoLabs"), (1, "FireBAM"), (1, ""), (1, "Frankendancer")] {
        let pt = Some((h[1], 200_000u64));
        let (ref_ixs, _) = att_ixs(user, &sw, min_out, &c_on, guard.clone(), pt.map(|(a, l)| (a, c_on.tip.unwrap_or(l))));
        let (lim, price, tip, fa) = att_fee(&c_on, Some(arm), client, pt);
        let (ixs, _) = att_ixs_fee(user, &sw, min_out, lim, price, guard.clone(), tip);
        assert_eq!(signed(&ixs), signed(&ref_ixs), "arm {arm} on {client:?}: A's bytes");
        let f = fa.unwrap();
        assert!(!f.b && f.arm == arm && (f.cu_limit, f.cu_price) == (c_on.cu_limit, c_on.cu_price), "{f:?}");
    }
    // off: an attempt has no fee fields; the counters, the status part and run_end's block do not exist
    let (sg, fa) = c.attempt(w, sw.mint, 1006, "AgaveBam");
    assert_eq!(fa, None);
    assert!(c.p.fab.is_none());
    assert!(!c.p.status().contains("FEE A/B"));
    c.p.on_arrival(&arbx::feeds::Arrival { feed: 0, slot: 1006, t_rx: 1_006_000_001, t_decoded: 1_006_000_001, executed: Some(false),
        tx: arbx::tx::Tx { sig: sg, keys: vec![USER], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: None }, 1006);
    assert_eq!(c.p.st.fees, c0.fail_fee(), "the fallback fee: the run's own (dip36)");
    let end = c.p.finish(1010, None);
    c.drain();
    assert!(end.get("fee_ab").is_none() && c.p.fee_ab_end().is_none());
    let land = c.ev("presend_attempt_land").pop().unwrap();
    assert!(land.get("fee_arm").is_none() && land.get("slot_tr").is_none() && land.get("cu_price").is_none(), "dip36's landing record: {land}");
}

/// the flags: parse, defaults, start record; every refusal (a parameter without the A/B on, no B price, bad numbers / words / clients,
/// the ranges, a flag without --presend-live); the start-up flag check knows them and their number types
#[test]
fn dip37_flags() {
    let c = on(&[]);
    assert!(c.fab.on && c.fab.cu_price == 20_000 && c.fab.cu_limit.is_none() && c.fab.tip.is_none() && c.fab.split == Split::Arm);
    assert_eq!(c.fab.clients, vec!["AgaveBam", "HarmonicAgave", "HarmonicFiredancer", "Firedancer", "Agave"], "the default: fee-ordered leaders, not JitoLabs");
    let j = c.json()["fee_ab"].clone();
    assert_eq!((j["split"].as_str(), j["a"]["cu_price"].as_u64(), j["a"]["cu_limit"].as_u64(), j["b"]["cu_price"].as_u64(), j["b"]["cu_limit"].as_u64()),
        (Some("arm"), Some(1_000), Some(CU_DEFAULT), Some(20_000), Some(CU_DEFAULT)), "B's limit defaults to A's: {j}");
    assert!(j["b"]["tip"].is_null() && j["a"]["tip"].is_null(), "no tip override: each path's own");
    let c = on(&["--presend-live-ab-cu-limit", "90000", "--presend-live-ab-tip-lamports", "300000", "--presend-live-ab-clients", "AgaveBam,JitoLabs,Unknown(38813)",
        "--presend-live-ab-split", "hour", "--presend-live-tip-lamports", "100000"]);
    assert_eq!((c.fab.cu_limit, c.fab.tip, c.fab.split), (Some(90_000), Some(300_000), Split::Hour));
    assert_eq!(c.fab.clients, vec!["AgaveBam", "JitoLabs", "Unknown(38813)"]);
    assert_eq!((c.json()["fee_ab"]["b"]["tip"].as_u64(), c.json()["fee_ab"]["a"]["tip"].as_u64()), (Some(300_000), Some(100_000)));
    let c = on(&["--presend-live-tip-lamports", "100000"]);
    assert_eq!(c.json()["fee_ab"]["b"]["tip"].as_u64(), Some(100_000), "B's tip defaults to A's");
    assert!(cfg(&["--presend-live-fee-ab", "off"]).unwrap().unwrap().fab == FeeAbCfg::default(), "off = no flag");
    for (a, needle) in [
        (&["--presend-live-ab-cu-price-micro", "20000"][..], "--presend-live-ab-cu-price-micro needs --presend-live-fee-ab on"),
        (&["--presend-live-fee-ab", "off", "--presend-live-ab-clients", "Agave"][..], "--presend-live-ab-clients needs --presend-live-fee-ab on"),
        (&["--presend-live-ab-split", "arm"][..], "needs --presend-live-fee-ab on"),
        (&["--presend-live-fee-ab", "on"][..], "needs --presend-live-ab-cu-price-micro N"),
        (&["--presend-live-fee-ab", "yes", "--presend-live-ab-cu-price-micro", "1"][..], "on | off"),
        (&["--presend-live-fee-ab"][..], "--presend-live-fee-ab needs a value"),
        (&["--presend-live-fee-ab", "on", "--presend-live-ab-cu-price-micro", "2e4"][..], "not a whole number"),
        (&["--presend-live-fee-ab", "on", "--presend-live-ab-cu-price-micro", "1", "--presend-live-ab-tip-lamports", "-5"][..], "not a whole number"),
        (&["--presend-live-fee-ab", "on", "--presend-live-ab-cu-price-micro", "1", "--presend-live-ab-split", "day"][..], "arm | hour"),
        (&["--presend-live-fee-ab", "on", "--presend-live-ab-cu-price-micro", "1", "--presend-live-ab-clients", "Jito"][..], "'Jito' is not a leader client"),
        (&["--presend-live-fee-ab", "on", "--presend-live-ab-cu-price-micro", "1", "--presend-live-ab-clients", "Agave,Agave"][..], "'Agave' twice"),
        (&["--presend-live-fee-ab", "on", "--presend-live-ab-cu-price-micro", "1", "--presend-live-ab-clients", "Agave,"][..], "an empty name"),
        (&["--presend-live-fee-ab", "on", "--presend-live-ab-cu-price-micro", "1", "--presend-live-ab-clients", "Unknown()"][..], "is not a leader client"),
        (&["--presend-live-fee-ab", "on", "--presend-live-ab-cu-price-micro", "1000001"][..], "--presend-live-ab-cu-price-micro above 1,000,000"),
        (&["--presend-live-fee-ab", "on", "--presend-live-ab-cu-price-micro", "1", "--presend-live-ab-cu-limit", "19999"][..], "--presend-live-ab-cu-limit must be 20000..400000"),
        (&["--presend-live-fee-ab", "on", "--presend-live-ab-cu-price-micro", "1", "--presend-live-ab-cu-limit", "400001"][..], "--presend-live-ab-cu-limit must be 20000..400000"),
        (&["--presend-live-fee-ab", "on", "--presend-live-ab-cu-price-micro", "1", "--presend-live-ab-tip-lamports", "10000001"][..], "above 0.01 SOL"),
    ] {
        let e = cfg(a).unwrap_err().to_string();
        assert!(e.contains(needle), "{a:?}: {e}");
    }
    assert!(on(&["--presend-live-ab-cu-price-micro", "1000000", "--presend-live-ab-cu-limit", "400000", "--presend-live-ab-tip-lamports", "10000000"]).fab.on, "the edges");
    for f in ["--presend-live-fee-ab", "--presend-live-ab-cu-price-micro", "--presend-live-ab-cu-limit", "--presend-live-ab-tip-lamports", "--presend-live-ab-clients", "--presend-live-ab-split"] {
        let e = Cfg::from_argv(&["snipe_engine", "--dip", "--presend-shadow", f, "1"].iter().map(|s| s.to_string()).collect::<Vec<_>>(), &arbx::presend::Params::default(), true, 1_000_000_000)
            .unwrap_err().to_string();
        assert!(e.contains("needs --presend-live"), "{f}: {e}");
    }
    // the start-up check: every flag known; the numbers are numbers
    assert!(crate::check_flags(&args(&["--presend-live-fee-ab", "on", "--presend-live-ab-cu-price-micro", "20000", "--presend-live-ab-cu-limit", "90000",
        "--presend-live-ab-tip-lamports", "100000", "--presend-live-ab-clients", "AgaveBam,Agave", "--presend-live-ab-split", "hour"])).is_ok());
    for f in ["--presend-live-ab-cu-price-micro", "--presend-live-ab-cu-limit", "--presend-live-ab-tip-lamports"] {
        assert!(crate::check_flags(&args(&["--presend-live-fee-ab", "on", f, "abc"])).is_err(), "{f}: a number");
    }
    // the start line's part names both arms
    let d = on(&["--presend-live-ab-cu-limit", "90000"]).fab.desc(CU_DEFAULT as u32, 1_000, None);
    assert!(d.starts_with("FEE A/B ON (split window id parity") && d.contains("A = 1000 uL x 120000 CU") && d.contains("B = 20000 uL x 90000 CU")
        && d.contains("failed try A 5120 / B 6800 lamports"), "{d}");
}

/// the arm: window id parity (T2 and re-arm share the counter) or the UTC hour's parity; the client rule per attempt (B's values only on
/// a listed client; Jito / unlisted / unknown leaders get A's); the CU limit, CU price and tip in the BUILT, SIGNED attempt
#[test]
fn dip37_arm_parity_client_rule_and_built_values() {
    let c = on(&["--presend-live-ab-cu-limit", "90000", "--presend-live-ab-tip-lamports", "300000"]);
    assert_eq!((1..=6).map(|id| c.fab.assign(id, 0)).collect::<Vec<_>>(), vec![1, 0, 1, 0, 1, 0], "arm: odd ids B, even A");
    let ch = on(&["--presend-live-ab-split", "hour"]);
    let h = |hh: u64, mm: u64| 1_793_750_400_000_000_000u64 + hh * 3_600_000_000_000 + mm * 60_000_000_000;     // 2026-11-04 00:00 UTC
    assert_eq!(1_793_750_400u64 % 86_400, 0, "the base is a UTC midnight");
    assert_eq!((ch.fab.assign(7, h(10, 0)), ch.fab.assign(7, h(10, 59)), ch.fab.assign(8, h(11, 0)), ch.fab.assign(8, h(23, 30))), (0, 0, 1, 1), "hour: even A, odd B, not the id");
    let hp = helius();
    let pt = Some((hp[0], 200_000u64));
    // the client rule and the groups
    for (arm, client, b, grp) in [(1u8, "AgaveBam", true, 0u8), (1, "HarmonicAgave", true, 0), (1, "HarmonicFiredancer", true, 0), (1, "Firedancer", true, 0), (1, "Agave", true, 0),
                                  (1, "JitoLabs", false, 1), (1, "FireBAM", false, 2), (1, "Frankendancer", false, 2), (1, "", false, 2), (0, "AgaveBam", false, 0), (0, "JitoLabs", false, 1)] {
        let (lim, price, tip, fa) = att_fee(&c, Some(arm), client, pt);
        let f = fa.unwrap();
        assert_eq!((f.arm, f.grp, f.b), (arm, grp, b), "{arm} {client:?}");
        let want = if b { (90_000u32, 20_000u64, 300_000u64) } else { (CU_DEFAULT as u32, 1_000, 200_000) };
        assert_eq!((lim, price, tip.map(|t| t.1)), (want.0, want.1, Some(want.2)), "{arm} {client:?}");
        assert_eq!((f.cu_limit, f.cu_price), (lim, price));
        assert_eq!(f.fail_fee(), 5_000 + (lim as u64 * price).div_ceil(1_000_000));
    }
    // JitoLabs listed by hand: B there too
    let cj = on(&["--presend-live-ab-clients", "JitoLabs"]);
    assert!(att_fee(&cj, Some(1), "JitoLabs", pt).3.unwrap().b && !att_fee(&cj, Some(1), "AgaveBam", pt).3.unwrap().b);
    // the tip defaults: B's = A's (the run's override, else the path's own); a tipless path stays tipless
    let cd = on(&[]);
    assert_eq!(att_fee(&cd, Some(1), "AgaveBam", pt).2, pt, "no override anywhere: the path's own tip");
    let ct = on(&["--presend-live-tip-lamports", "150000"]);
    assert_eq!(att_fee(&ct, Some(1), "AgaveBam", pt).2, Some((hp[0], 150_000)), "B's tip = A's override");
    assert_eq!(att_fee(&c, Some(1), "AgaveBam", None).2, None, "a tipless path");
    assert_eq!((att_fee(&cd, Some(1), "AgaveBam", pt).0, att_fee(&cd, Some(1), "AgaveBam", pt).1), (CU_DEFAULT as u32, 20_000), "B's limit = A's");
    // the built, signed attempt: B's values on a listed leader, A's on Jito; one packet; the Helius Sender's own check passes
    let user = pk("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE");
    let l = snipe_build::launch_from_target(pk("7oeUduY1zhUwQ3YdSP9CGDYF8nYzfRdhgqtc6wAbpump"), pk("3tNPvytXB9yTZLgh5RGdjrXVxHp89vGeCiwx9juqgp7q"));
    let sw = SWin { id: 1, mint: l.mint, launch: l.clone(), st_ns: 0, stop_ns: u64::MAX, en_slot: 10, vsol: 40 * S, vtok: 800_000_000_000_000, fr: 0.0125, pos: (1, 0, 0),
                    pace: pl::Pace::new(0, 4, 400_000_000), n: 0, done: false, spend: 400_000_000, rearm: false, ob6: 0.0, grd: Grd::default(), fpg: None, fab: Some(1), blk: None, bd: None };
    let guard = guard_ix_enc(GuardEnc { disc: 15, op: 4, acct: true }, 461_000_123);
    for (client, want) in [("HarmonicAgave", (90_000u32, 20_000u64, 300_000u64)), ("JitoLabs", (CU_DEFAULT as u32, 1_000, 200_000))] {
        let (lim, price, tip, _) = att_fee(&c, sw.fab, client, pt);
        let (ixs, r) = att_ixs_fee(user, &sw, 1_234_567, lim, price, guard.clone(), tip);
        assert_eq!((ix_u32(&ixs[0]), ix_u64(&ixs[1]), tip_of(&ixs[r.tip.unwrap() as usize])), want, "{client}");
        assert_eq!((ixs[0].data[0], ixs[1].data[0]), (2, 3), "SetComputeUnitLimit, SetComputeUnitPrice");
        assert!(ixs[r.tip.unwrap() as usize].accounts[1].key == hp[0]);
        assert_eq!(r, pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) }, "the layout is dip36's");
        let raw = signed(&ixs);
        assert!(raw.len() <= 1232, "{} bytes", raw.len());
        assert!(send::verify_copy(&raw, config::SendKind::Helius, &hp, "helius-ps").is_ok(), "{client}");
    }
    // the run_end per-1k figure
    assert_eq!((per_1k(3, 1_500), per_1k(0, 0)), (2.0, 0.0));
}

/// slot_tr: the trades of the landing slot nearest our tx index (half before, half at or after)
#[test]
fn dip37_slot_tr() {
    let tr = |s: u64, i: u32, u: u8| pl::Trade { mint: [1; 32], s, i, j: 0, sig: [0; 64], user: [u; 32], buy: u % 2 == 0, sol: 1, tok: 1, vsol: 1, vtok: 1, fbps: 0, cbps: 0, t_rx: 0 };
    let tape: Vec<pl::Trade> = (0..60u32).map(|i| tr(100, i * 2, i as u8)).chain([tr(99, 5, 200), tr(101, 1, 201)]).collect();
    let mut v: Vec<&pl::Trade> = tape.iter().collect();
    v.sort_by_key(|t| t.pos());
    let x = slot_tr(&v, 100, 61);
    assert_eq!(x.len(), SLOT_TR_MAX);
    let idx: Vec<u64> = x.iter().map(|e| e[0].as_u64().unwrap()).collect();
    assert_eq!((idx[0], idx[SLOT_TR_MAX / 2 - 1], idx[SLOT_TR_MAX / 2], *idx.last().unwrap()), (30, 60, 62, 92), "16 before 61, 16 from it");
    assert_eq!(x[0][2].as_str().map(str::to_string), Some(b58(&[15u8; 32])), "full addresses");
    let few = slot_tr(&v, 101, 0);
    assert_eq!(few.len(), 1);
    assert!(slot_tr(&v, 102, 0).is_empty());
}

/// the probe with the A/B on: windows get A / B by id parity at their arm (the arm record says so with the arm's values); attempts are
/// counted per arm x leader group; a failed try without the chain's fee is charged at ITS values; a fill and its record carry the fee
/// fields; the realized lookup is tagged (arm, group, values); the status part, run_end's per-arm block and the summary line
#[test]
fn dip37_probe_counts_records_and_realized_tag() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let mut c = Ctx::with(on(&["--presend-live-ab-cu-limit", "90000", "--presend-live-ab-tip-lamports", "300000"]));
    let (mut t1, w1) = c.t2(0x71, 1000, [0xE1; 32]);
    let (t2, w2) = c.t2(0x72, 1010, [0xE2; 32]);
    assert_eq!((w1, w2), (1, 2));
    assert_eq!((c.swin(w1).fab, c.swin(w2).fab), (Some(1), Some(0)), "id 1 -> B, id 2 -> A");
    let arms = c.ev("presend_live_arm");
    assert_eq!((arms[0]["fee_arm"].as_str(), arms[0]["cu_price"].as_u64(), arms[0]["cu_limit"].as_u64(), arms[0]["tip"].as_u64()), (Some("B"), Some(20_000), Some(90_000), Some(300_000)));
    assert_eq!(arms[0]["ab_clients"][0].as_str(), Some("AgaveBam"));
    assert_eq!((arms[1]["fee_arm"].as_str(), arms[1]["cu_price"].as_u64(), arms[1]["cu_limit"].as_u64()), (Some("A"), Some(1_000), Some(CU_DEFAULT)));
    assert!(arms[1]["tip"].is_null(), "A: the path's own tip");
    assert_eq!(c.p.fab.as_ref().unwrap().armed, [1, 1]);
    // attempts: B on a fee leader (B's values), B on Jito (A's values, group jito), A on a fee leader
    let (s_bf, f_bf) = c.attempt(w1, t1.mint, 1006, "AgaveBam");
    let (s_bj, f_bj) = c.attempt(w1, t1.mint, 1006, "JitoLabs");
    let (s_af, f_af) = c.attempt(w2, t2.mint, 1016, "HarmonicAgave");
    let (f_bf, f_bj, f_af) = (f_bf.unwrap(), f_bj.unwrap(), f_af.unwrap());
    assert!(f_bf.b && !f_bj.b && !f_af.b && (f_bf.grp, f_bj.grp, f_af.grp) == (0, 1, 0));
    {
        let fs = c.p.fab.as_ref().unwrap();
        assert_eq!((fs.c[1][0].att, fs.c[1][1].att, fs.c[0][0].att, fs.c[0][1].att), (1, 1, 1, 0));
    }
    // failed tries, no fee from the chain: each at its own values (B on a fee leader 5,000 + 90,000 x 20,000 / 1e6 = 6,800)
    let fail = |c: &mut Ctx, sg: [u8; 64], slot: u64| c.p.on_arrival(&arbx::feeds::Arrival { feed: 0, slot, t_rx: slot * 1_000_000 + 7, t_decoded: slot * 1_000_000 + 7, executed: Some(false),
        tx: arbx::tx::Tx { sig: sg, keys: vec![USER], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: None }, slot);
    fail(&mut c, s_bj, 1006);
    fail(&mut c, s_af, 1016);
    {
        let fs = c.p.fab.as_ref().unwrap();
        assert_eq!((fs.c[1][1].fail, fs.c[1][1].fail_fee, fs.c[0][0].fail, fs.c[0][0].fail_fee), (1, 5_120, 1, 5_120));
    }
    assert_eq!(f_bf.fail_fee(), 6_800);
    // B's try on the fee leader fills
    let e = t1.buy(USER, 396_000_000);
    c.tx_sig(1007, 4, s_bf, USER, vec![e.clone()], vec![]);
    let fill = c.ev("presend_live_fill").pop().unwrap();
    assert_eq!((fill["fee_arm"].as_str(), fill["fee_grp"].as_str(), fill["fee_b"].as_bool(), fill["cu_price"].as_u64(), fill["cu_limit"].as_u64(), fill["tip"].as_u64()),
        (Some("B"), Some("fee"), Some(true), Some(20_000), Some(90_000), Some(300_000)), "{fill}");
    {
        let fs = c.p.fab.as_ref().unwrap();
        assert_eq!((fs.c[1][0].fills, fs.c[1][0].tips, fs.c[1][0].fill_fee), (1, 300_000, 5_000));
    }
    assert!(c.p.status().contains(" | FEE A/B A: windows 1 attempts 1 failed 1") && c.p.status().contains("| B: windows 1 attempts 2 failed 1"), "{}", c.p.status());
    // the exit (entry slot + 2), its sell, the close: the realized lookup carries B's tag
    let mut z = Tk::new(0x7F);
    c.launches.push(z.launch.clone());
    let dz = z.buy(CREATOR, S / 2);
    c.tx(1007, 900, vec![dz], vec![z.create()]);
    for s in 1008..=1009 { let e = z.buy([0x2F; 32], 1_000_000); c.tx(s, 900, vec![e], vec![]); }
    let Some(Cmd::Sell { pid, .. }) = c.cmds.iter().find(|x| matches!(x, Cmd::Sell { .. })).cloned() else { panic!("{:?} {:?}", c.cmds, c.lines) };
    let es = t1.sell_tok(USER, e.tok);
    c.tx_sig(1009, 9, { let mut s = [0u8; 64]; s[0] = 0x5E; s[1] = 0x37; s }, USER, vec![es], vec![]);
    c.p.on_msg(PsMsg::Sold(t1.mint, pid, 1, sold(Some(1009), &["S37"], e.tok)), &|_| false);
    c.drain();
    let Some(Cmd::Realized { ab, .. }) = c.cmds.iter().find(|x| matches!(x, Cmd::Realized { .. })).cloned() else { panic!("{:?}", c.cmds) };
    let ab = ab.expect("tagged with the A/B on");
    assert_eq!(ab, RzAb { arm: 1, grp: 0, fee: Some(f_bf), tip: 300_000 });
    let mut rec = serde_json::json!({"ev": "presend_live_realized"});
    ab.put(&mut rec);
    assert_eq!((rec["fee_arm"].as_str(), rec["fee_grp"].as_str(), rec["cu_price"].as_u64(), rec["tip"].as_u64()), (Some("B"), Some("fee"), Some(20_000), Some(300_000)));
    // the realized task's split (it adds as the lookups come in) and run_end
    let fs = c.p.fab.as_ref().unwrap();
    fs.rz.add(1, 0, 12_000_000); fs.rz.add(0, 0, -3_000_000);
    let end = c.p.finish(1012, None);
    c.drain();
    let fj = &end["fee_ab"];
    assert_eq!((fj["A"]["attempts"].as_u64(), fj["A"]["failed"].as_u64(), fj["A"]["failed_fees"].as_u64(), fj["A"]["fills"].as_u64(), fj["A"]["windows"].as_u64()),
        (Some(1), Some(1), Some(5_120), Some(0), Some(1)), "{fj}");
    assert_eq!((fj["B"]["attempts"].as_u64(), fj["B"]["fills"].as_u64(), fj["B"]["fills_per_1k"].as_f64(), fj["B"]["by_grp"]["jito"]["failed"].as_u64()),
        (Some(2), Some(1), Some(500.0), Some(1)));
    assert_eq!((fj["realized"]["B"]["pnl"].as_i64(), fj["realized"]["B"]["wins"].as_u64(), fj["realized"]["A"]["by_grp"]["fee"]["pnl"].as_i64()), (Some(12_000_000), Some(1), Some(-3_000_000)));
    let (rz, line) = c.p.fee_ab_end().unwrap();
    assert_eq!(rz["B"]["n"].as_u64(), Some(1));
    assert!(line.starts_with("=== DIP PRESEND LIVE FEE A/B: | A: windows 1 attempts 1 failed 1 (fees 0.000005 SOL) fills 0") && line.contains("| B: windows 1 attempts 2"), "{line}");
    // the landing records: fee fields; a landed try's slot_tr (full addresses)
    let lands = c.ev("presend_attempt_land");
    let lf = lands.iter().find(|l| l["sig"] == bs58::encode(&s_bf).into_string()).unwrap();
    assert_eq!((lf["res"].as_str(), lf["fee_arm"].as_str(), lf["fee_grp"].as_str(), lf["cu_price"].as_u64()), (Some("ok"), Some("B"), Some("fee"), Some(20_000)));
    assert!(lf["slot_tr"].as_array().is_some_and(|a| a.iter().any(|e| e[2].as_str() == Some(b58(&USER).as_str()))), "{lf}");
    let lj = lands.iter().find(|l| l["sig"] == bs58::encode(&s_bj).into_string()).unwrap();
    assert_eq!((lj["fee_arm"].as_str(), lj["fee_grp"].as_str(), lj["fee_b"].as_bool(), lj["cu_price"].as_u64(), lj["fee"].as_u64()), (Some("B"), Some("jito"), Some(false), Some(1_000), Some(5_120)));
}
