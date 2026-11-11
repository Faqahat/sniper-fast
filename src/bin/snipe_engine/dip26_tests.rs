// ===================================================================================================================
// dip26 tests (10-29 PKT; owner 19:35 PKT "add re-arm in the engine"): the LIVE RE-ARM (--presend-live-rearm on; the observatory's
// log-only rule R0, src/obs/rearm.rs). Declared inside pslive.rs (the probe's state machine is private to it), driven through
// on_arrival / on_exec / tick / on_msg as the event loop calls them; the chain work is queued and answered by the tests.
//  * GOLDEN: --presend-live-rearm off = dip25's records, lines, shadow records and run totals byte for byte (the digest below was
//    taken on the dip25 tree before any dip26 change), on the parity tapes with attempts, fills, exits, sells, reads and closes
//  * the rule on synthetic tokens: the holders check at dump + 3 and the window (test 1: B dumps, a fill at the re-arm size, its exit /
//    sell / close / realized tagged rearm); no window without a holder >= 6%, past 141 slots, at a curve >= 100 SOL (2-4); the stops
//    (whale_dump, no_holder); a T2 window blocks the check / takes the token over (5); the waits on our position / account / attempts in
//    flight (6, 6b); QUIET N:M (7); one position both ways (8); the re-arm size and the per-buy cap (9); the fee pause, the kill switch /
//    profit lock stop (10); the flags (11); R5; the T2 side unchanged with the re-arm on (the parity tapes)
//  * by hand: a recorded hour through the probe and the observatory's paper re-arm side by side (live vs paper agreement)
// ===================================================================================================================
use super::*;
use arbx::dip::{CreateEvent, TradeEvent};

const USER: Pk = [0x5Au8; 32];

// ---- GOLDEN -------------------------------------------------------------------------------------------------------------

/// the digest of golden_digest() on the dip25 tree (10-29 ~20:30 PKT, before any dip26 change)
pub(super) const DIP25_GOLDEN: &str = "380c2a18cd138f0aec33c86c976abe548849e2e731bf00dd1959a2b4f873c1c4";

/// the parity tapes' executed txs in chain order and their launches (the loader of pslive's own tests, duplicated: those stay as they are)
fn gtapes(n: usize) -> Option<(Vec<(u64, u64, [u8; 64], arbx::feeds::ExecInfo)>, HashMap<Pk, Launch>)> {
    let root = env!("CARGO_MANIFEST_DIR");
    let par: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(format!("{root}/testdata/presend_parity.json")).ok()?).ok()?;
    let pk = |s: &str| -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() };
    let mut by: std::collections::BTreeMap<(u64, u64), ([u8; 64], Vec<(i64, TradeEvent)>, Vec<CreateEvent>)> = Default::default();
    let mut launches = HashMap::new();
    for tk in par["tokens"].as_array().unwrap().iter().take(n) {
        let mint = pk(tk["mint"].as_str().unwrap());
        let users: Vec<Pk> = tk["users"].as_array().unwrap().iter().map(|u| pk(u.as_str().unwrap())).collect();
        let la = &tk["launch"];
        let signer = pk(la["user"].as_str().unwrap());
        let creator = la["creator"].as_str().map(pk).unwrap_or(signer);
        let (cs, ci) = (la["slot"].as_u64().unwrap(), la["idx"].as_u64().unwrap_or(0));
        for r in tk["trades"].as_array().unwrap() {
            let (s, i, j) = (r[0].as_u64().unwrap(), r[1].as_u64().unwrap(), r[2].as_i64().unwrap());
            let sig: [u8; 64] = bs58::decode(r[3].as_str().unwrap()).into_vec().unwrap().try_into().unwrap();
            by.entry((s, i)).or_insert_with(|| (sig, Vec::new(), Vec::new())).1.push((j, TradeEvent { mint, sol: r[6].as_u64().unwrap(), tok: r[7].as_u64().unwrap(),
                buy: r[5].as_u64().unwrap() == 1, user: users[r[4].as_u64().unwrap() as usize], vsol: r[8].as_u64().unwrap(), vtok: r[9].as_u64().unwrap(),
                fbps: r[10].as_u64().unwrap_or(0), cbps: r[11].as_u64().unwrap_or(0) }));
        }
        by.entry((cs, ci)).or_insert_with(|| ([1; 64], Vec::new(), Vec::new())).2.push(CreateEvent { mint, bonding_curve: [0; 32], user: signer, creator });
        launches.insert(mint, snipe_build::launch_from_target(mint, creator));
    }
    let all = by.into_iter().map(|((s, i), (sig, mut tr, cr))| {
        tr.sort_by_key(|x| x.0);
        (s, i, sig, arbx::feeds::ExecInfo { index: i, fee: 5000, ok: true, trades: tr.into_iter().map(|x| x.1).collect(), creates: cr, mayhem: false })
    }).collect();
    Some((all, launches))
}

/// the golden passes' command line: dip20's test line + `extra`
fn gargs(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps",
        "--presend-live-fee-budget-sol", "0.5", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}

/// a record without its wall-clock fields (the top-level "t" of the disarm / stop / follow-up exit records, armed_ms, held_s, the
/// send acks) and the timing / memory figures of the totals (anywhere in it)
fn gstrip(mut v: serde_json::Value) -> serde_json::Value {
    if let Some(o) = v.as_object_mut() { for k in ["t", "armed_ms", "held_s", "ack", "ack_ms", "acks"] { o.remove(k); } }
    fn deep(v: &mut serde_json::Value) {
        match v {
            serde_json::Value::Object(o) => { for k in ["sig_us_p50", "sig_us_p99", "merge_us", "mem_mb", "load_ms"] { o.remove(k); } for x in o.values_mut() { deep(x); } }
            serde_json::Value::Array(a) => { for x in a.iter_mut() { deep(x); } }
            _ => {}
        }
    }
    deep(&mut v);
    v
}

/// the chain work queued so far: as text (`cmds`) and kept for its answers (`held`)
fn gtake(p: &mut PsLive, cmds: &mut Vec<String>, held: &mut Vec<Cmd>) { let c = p.take_cmds(); cmds.extend(c.iter().map(gcmd)); held.extend(c); }

/// the chain work a test answers, as text (the fields every build since dip19 has; a field added later is not in it)
fn gcmd(c: &Cmd) -> String {
    match c {
        Cmd::Sell { mint, pid, round, derived, known, guess, land_slot, read_first, keep_ata, .. } =>
            format!("sell {} pid {pid} round {round} derived {derived} known {known:?} guess {guess} land {land_slot} read_first {read_first} keep {keep_ata}", b58(mint)),
        Cmd::Read { mint, min_slot, why, n } => format!("read {} {min_slot} {why:?} {n}", b58(mint)),
        Cmd::Close { mint } => format!("close {}", b58(mint)),
        Cmd::Realized { pid, w, mint, buys, sells, .. } => format!("realized pid {pid} w {w} {} buys {buys:?} sells {sells:?}", b58(mint)),
        Cmd::Unsold { mint, land_slot, last_qty, .. } => format!("unsold {} {land_slot} {last_qty:?}", b58(mint)),
        Cmd::Alert { level, title } => format!("alert {level:?} {title}"),
        // dip35 (log-only; only with --presend-live-fam-log)
        Cmd::Fam(q) => format!("fam w {} {} rearm {}", q.w, b58(&q.mint), q.rearm),
        // dip43 A2 (only with --presend-live-deadman live)
        Cmd::Status(q) => format!("status {} w {}", bs58::encode(&q.sig).into_string(), q.w),
        Cmd::Largest(q) => format!("largest w {} {}", q.w, b58(&q.mint)),
    }
}

/// ONE GOLDEN PASS: the parity tapes through the probe and the shadow (presend_tx_live) as the event loop calls them; per tx one attempt
/// per armed window registered as the sender does (none while the fee budget pauses it), every `fill_every`-th a fill (our buy at the
/// window's latest curve state), the others a 6042 through the failed-tx side channel. After the tape: every queued sell answered
/// (sold), the reads answered (0), the closes answered (landed), then the run's end. -> the probe's records (wall clock removed), its
/// lines, the chain work, the shadow's records, the totals: one text line each
pub(super) fn golden_pass(tag: u8, extra: &[&str], ps: arbx::presend::Params, fill_every: u64) -> Option<Vec<String>> {
    let (txs, launches) = gtapes(312)?;
    let cfg = Cfg::from_argv(&gargs(extra), &ps, true, 1_000_000_000).unwrap().unwrap();
    let fail_fee = cfg.fail_fee();
    let spend = cfg.spend;
    let (mut p, atx, orx) = PsLive::for_test(cfg, USER);
    let f = std::env::temp_dir().join(format!("dip26_golden_{}_{tag}.jsonl", std::process::id()));
    let _ = std::fs::remove_file(&f);
    let log = DipLog::open(Some(f.display().to_string())).unwrap();
    let mut sh = arbx::presend::Shadow::new(ps);
    let launch_of = |m: &Pk| launches.get(m).cloned();
    let roles = pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) };
    let err6042 = [8u8, 0, 0, 0, 5, 25, 0, 0, 0, 0x9a, 0x17, 0, 0];
    let (mut seq, mut slot_now, mut cmds) = (0u64, 0u64, Vec::new());
    // the chain work queued during the tape (answered after it)
    let mut held: Vec<Cmd> = Vec::new();
    for (s, idx, sig, x) in &txs {
        slot_now = slot_now.max(*s);
        let a = arbx::feeds::Arrival { feed: 0, slot: *s, t_rx: *s * 1_000_000 + *idx, t_decoded: *s * 1_000_000 + *idx, executed: Some(true),
            tx: arbx::tx::Tx { sig: *sig, keys: vec![[3u8; 32]], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        p.on_arrival(&a, slot_now);
        p.on_exec(&a, x, slot_now, launch_of, &|_| false, None);
        let marks: Vec<[u64; 5]> = (0..=x.trades.len()).map(|_| [0u64; 5]).collect();
        presend_tx_live(&mut sh, *s, slot_now, x, sig, *s * 1_000_000 + *idx, &marks, &log, Some(&mut p));
        gtake(&mut p, &mut cmds, &mut held);
        let mut armed: Vec<(Pk, u64)> = p.armed.iter().map(|(m, w)| (*m, *w)).collect();
        armed.sort_by_key(|x| x.1);
        if p.sh.pause_fee.load(Ordering::Relaxed) { armed.clear(); }
        for (m, w) in armed {
            seq += 1;
            let mut sg = [0u8; 64]; sg[..8].copy_from_slice(&seq.to_be_bytes()); sg[8] = 0xD6; sg[9] = tag;
            // one lock for both fields (two in one struct literal keep the first guard alive: a std Mutex deadlock)
            let (o6, gd) = p.sh.wins.lock().unwrap().iter().find(|x| x.id == w).map_or((0.0, pslive::Grd::default()), |x| (x.ob6, x.grd));
            atx.send(Att { w, n: 1, mint: m, sig: sg, tag: pl::PS_TAG | (0xD26 << 32) | seq, path: "helius-ps".into(), client: "JitoLabs".into(), slot: *s, deadline: *s + 1,
                lim: 1.0, min_out: 1, p_sign: 1.0, sign_pos: (*s, *idx as u32, 0), t_send: *s * 1_000_000, roles, tip: 200_000, wst: "written",
                // dip27: the window's other holder, as the sender copies it (0 with the annotations off: the golden records unchanged)
                ob6: o6, grd: gd, fa: None, bd: None, x46: Default::default() }).unwrap();
            if fill_every > 0 && seq % fill_every == 0 {
                let (wv, wt) = p.sh.wins.lock().unwrap().iter().find(|x| x.id == w).map(|x| (x.vsol, x.vtok)).unwrap();
                let tok = pl::buy_out(wv, wt, spend, 0.0125);
                let sol = (spend as f64 / 1.0125) as u64;
                let ev = TradeEvent { mint: m, sol, tok, buy: true, user: USER, vsol: wv + sol, vtok: wt - tok, fbps: 95, cbps: 30 };
                let xf = arbx::feeds::ExecInfo { index: 50, fee: 5_090, ok: true, trades: vec![ev], creates: Vec::new(), mayhem: false };
                let af = arbx::feeds::Arrival { feed: 0, slot: *s, t_rx: *s * 1_000_000 + 40_000_000, t_decoded: *s * 1_000_000 + 40_000_000, executed: Some(true),
                    tx: arbx::tx::Tx { sig: sg, keys: vec![USER], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(xf.clone())) };
                p.on_arrival(&af, slot_now);
                p.on_exec(&af, &xf, slot_now, launch_of, &|_| false, None);
            } else {
                arbx::feeds::own_fail_note(&sg, Some(&USER[..]), *s, 60, fail_fee, &err6042);
                let af = arbx::feeds::Arrival { feed: 0, slot: *s, t_rx: *s * 1_000_000 + 30_000_000, t_decoded: *s * 1_000_000 + 30_000_000, executed: Some(false),
                    tx: arbx::tx::Tx { sig: sg, keys: vec![USER], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: None };
                p.on_arrival(&af, slot_now);
            }
            gtake(&mut p, &mut cmds, &mut held);
        }
    }
    sh.complete();
    let mut evs = sh.drain();
    p.annotate_shadow(&mut evs);
    for e in evs.iter().filter(|e| e.rec["ev"] == "presend_arm") { p.on_shadow_arm(&e.rec); }
    log.w_all(evs.into_iter().map(|e| e.rec));
    // the chain's answers: every sell sold (a confirmed 0 at the end slot), then the reads (0) and the closes (landed), in order
    let end = slot_now + 50;
    p.tick(end, None);
    gtake(&mut p, &mut cmds, &mut held);
    for round in 0..5u64 {
        let pend = std::mem::take(&mut held);
        for c in pend {
            match c {
                Cmd::Sell { mint, pid, round: r, known, .. } => {
                    let q = known.unwrap_or(0);
                    p.on_msg(PsMsg::Sold(mint, pid, r, SellOut { sold_at: Some(end + round), sigs: vec![(format!("GSELL{pid}r{r}"), true, 1_200_000)], last: None, attempts: 1,
                        last_qty: (q, true), first_send_us: None }), &|_| false);
                }
                Cmd::Read { mint, min_slot, why, n } => p.on_msg(PsMsg::Read(mint, why, min_slot, n, crate::Tok::Amount(0, end + round)), &|_| false),
                Cmd::Close { mint } => p.on_msg(PsMsg::Closed(mint, format!("GCLOSE{}", &b58(&mint)[..6]), Some(end + round), String::new()), &|_| false),
                _ => {}
            }
            gtake(&mut p, &mut cmds, &mut held);
        }
        p.tick(end + 10 * (round + 1), None);
        gtake(&mut p, &mut cmds, &mut held);
    }
    let fin = p.finish(end + 100, None);
    gtake(&mut p, &mut cmds, &mut held);
    drop(log);
    let mut out: Vec<String> = Vec::new();
    for o in orx.try_iter() { match o { Out::Rec(v) => out.push(format!("R {}", gstrip(v))), Out::Line(l) => out.push(format!("L {l}")) } }
    out.extend(cmds.into_iter().map(|c| format!("C {c}")));
    for l in std::fs::read_to_string(&f).ok()?.lines() { out.push(format!("S {l}")); }
    let _ = std::fs::remove_file(&f);
    out.push(format!("F {}", gstrip(fin)));
    Some(out)
}

/// the golden passes: (1) dip20's test line, 5% whale, TP 10%, a fill every 7th attempt; (2) AMS run 37's pre-send options (6% whale,
/// TP 20%, k 8, QUIET stop 5:2 + the arm rule with fol 4.0, the v2 log, min token age 2; the exit-ms is LEFT OUT: a wall-clock exit;
/// the size and the fee budget stay the test line's: the first of a repeated flag counts), a fill every 5th; (3) no fill (every attempt
/// a 6042)
pub(super) fn golden_digest() -> Option<(String, usize)> {
    use sha2::Digest;
    let mut h = sha2::Sha256::new();
    let mut n = 0usize;
    let passes: [(u8, Vec<&str>, arbx::presend::Params, u64); 3] = [
        (1, vec![], arbx::presend::Params::default(), 7),
        (2, vec!["--presend-live-k", "8", "--presend-live-size-sol", "0.696", "--presend-live-quiet-stop", "5:2", "--presend-live-quiet-skip", "on", "--presend-live-fbots",
            "/unused-in-tests.json", "--presend-live-quiet-fol", "4.0", "--presend-live-quiet-v2-log", "--presend-live-min-age-slots", "2"],
            arbx::presend::Params { whale_pct: 6.0, tp: 0.20, ..Default::default() }, 5),
        (3, vec!["--presend-live-fee-budget-sol", "0.0005"], arbx::presend::Params::default(), 0),
    ];
    for (tag, extra, ps, fe) in passes {
        let lines = golden_pass(tag, &extra, ps, fe)?;
        if let Ok(dir) = std::env::var("DIP26_GOLDEN_OUT") { let _ = std::fs::write(format!("{dir}/golden_{tag}.txt"), lines.join("\n")); }
        h.update([tag]);
        for l in &lines { h.update(l.as_bytes()); h.update(b"\n"); n += 1; }
    }
    Some((h.finalize().iter().map(|b| format!("{b:02x}")).collect(), n))
}

/// GOLDEN: with --presend-live-rearm off (every pass above has no re-arm flag) the probe's records, lines, chain work, the shadow's
/// records and the run totals are dip25's byte for byte (wall-clock fields removed)
#[test]
fn dip26_golden_rearm_off_equals_dip25() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let Some((d, n)) = golden_digest() else { eprintln!("presend_parity.json missing: skipped"); return };
    eprintln!("dip26 golden: {n} lines, sha256 {d}");
    assert!(n > 3_000, "{n}");
    // twice: the passes are deterministic
    let (d2, _) = golden_digest().unwrap();
    assert_eq!(d, d2, "the golden passes are deterministic");
    assert_eq!(d, DIP25_GOLDEN, "rearm off: the records must be dip25's ({n} lines)");
}

// ---- the re-arm on synthetic tokens -------------------------------------------------------------------------------------

const CREATOR: Pk = [0xC1u8; 32];
const S: u64 = 1_000_000_000;
const RE_ON: [&str; 2] = ["--presend-live-rearm", "on"];

/// dip20's test line (0.4 SOL pre-send, fills cap 100, fee budget 0.1) + `extra`
fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }
/// `pct` % of the supply (raw tokens)
fn pct(x: f64) -> u64 { (x / 100.0 * pl::SUPPLY) as u64 }

/// a token on its curve (pump's constant product) and its launch
struct Tk { mint: Pk, v: u64, t: u64, launch: Launch }
impl Tk {
    fn new(k: u8) -> Tk { let mint = [k; 32]; Tk { mint, v: 30 * S, t: 1_073_000_000_000_000, launch: snipe_build::launch_from_target(mint, CREATOR) } }
    fn buy(&mut self, user: Pk, sol: u64) -> TradeEvent {
        let q = (self.t as u128 * sol as u128 / (self.v + sol) as u128) as u64;
        self.v += sol; self.t -= q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: true, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    /// a buy of exactly `q` tokens (its SOL rounded up)
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

/// a probe and the event loop around it: every launch known (the engine's toks map), the records / lines / chain work collected
struct Ctx { p: PsLive, atx: crossbeam_channel::Sender<Att>, orx: crossbeam_channel::Receiver<Out>, launches: HashMap<Pk, Launch>, recs: Vec<serde_json::Value>,
             lines: Vec<String>, cmds: Vec<Cmd>, seq: u64 }

impl Ctx {
    fn new(extra: &[&str]) -> Ctx { Ctx::with(cfg(extra).unwrap().unwrap()) }
    fn with(c: Cfg) -> Ctx {
        let (p, atx, orx) = PsLive::for_test(c, USER);
        Ctx { p, atx, orx, launches: HashMap::new(), recs: Vec::new(), lines: Vec::new(), cmds: Vec::new(), seq: 0 }
    }
    fn add(&mut self, tk: &Tk) { self.launches.insert(tk.mint, tk.launch.clone()); }
    /// one executed tx (signature from its position) through on_arrival + on_exec; t_rx = slot ms + idx (ns)
    fn tx(&mut self, slot: u64, idx: u64, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&slot.to_be_bytes()); sig[8..16].copy_from_slice(&idx.to_be_bytes()); sig[16] = 0xD6;
        self.tx_sig(slot, idx, sig, [0x77; 32], trades, creates);
    }
    fn tx_sig(&mut self, slot: u64, idx: u64, sig: [u8; 64], payer: Pk, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades, creates, mayhem: false };
        let a = arbx::feeds::Arrival { feed: 0, slot, t_rx: slot * 1_000_000 + idx, t_decoded: slot * 1_000_000 + idx, executed: Some(true),
            tx: arbx::tx::Tx { sig, keys: vec![payer], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        let ls = self.launches.clone();
        self.p.on_arrival(&a, slot);
        self.p.on_exec(&a, &x, slot, move |m: &Pk| ls.get(m).cloned(), &|_| false, None);
        self.drain();
    }
    /// an attempt of window `w`, as the sender registers it (before its write) -> its signature
    fn attempt(&mut self, w: u64, mint: Pk, slot: u64) -> [u8; 64] {
        self.seq += 1;
        let mut sg = [0u8; 64]; sg[..8].copy_from_slice(&self.seq.to_be_bytes()); sg[8] = 0xD6; sg[9] = 0xA7;
        self.atx.send(Att { w, n: self.seq as u32, mint, sig: sg, tag: pl::PS_TAG | (0xD26A << 32) | self.seq, path: "helius-ps".into(), client: "JitoLabs".into(), slot, deadline: slot + 1,
            lim: 1.0, min_out: 1, p_sign: 1.0, sign_pos: (slot, 0, 0), t_send: slot * 1_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) },
            tip: 200_000, wst: "written", ob6: 0.0, grd: pslive::Grd::default(), fa: None, bd: None, x46: Default::default() }).unwrap();
        self.p.drain_atts();
        sg
    }
    /// that attempt filled: our buy of `sol` (curve SOL) in slot / idx
    fn fill(&mut self, tk: &mut Tk, sig: [u8; 64], slot: u64, idx: u64, sol: u64) -> TradeEvent {
        let e = tk.buy(USER, sol);
        self.tx_sig(slot, idx, sig, USER, vec![e.clone()], vec![]);
        e
    }
    fn drain(&mut self) {
        for o in self.orx.try_iter() { match o { Out::Rec(v) => self.recs.push(v), Out::Line(l) => self.lines.push(l) } }
        self.cmds.extend(self.p.take_cmds());
    }
    fn tick(&mut self, slot: u64) { self.p.tick(slot, None); self.drain(); }
    fn ev(&self, k: &str) -> Vec<serde_json::Value> { self.recs.iter().filter(|r| r["ev"] == k).cloned().collect() }
    fn rearm(&self) -> &psrearm::Rearm { self.p.rm.as_ref().expect("re-arm on") }
    /// the token's creation (slot s0, the dev buy) and the create-slot buys of `whales` ((wallet, % of supply)): create-slot insiders,
    /// never T2 triggers
    fn token(&mut self, k: u8, s0: u64, whales: &[(Pk, f64)]) -> Tk {
        let mut tk = Tk::new(k);
        self.add(&tk);
        let dev = tk.buy(CREATOR, S / 2);
        self.tx(s0, 1, vec![dev], vec![tk.create()]);
        for (n, (w, x)) in whales.iter().enumerate() { let e = tk.buy_tok(*w, pct(*x)); self.tx(s0, 2 + n as u64, vec![e], vec![]); }
        tk
    }
}

/// the slot clock moves on any executed pump tx: a filler token's small buys, one per slot in [from, to]
fn clock(c: &mut Ctx, z: &mut Tk, from: u64, to: u64) {
    for s in from..=to { let e = z.buy([0x2F; 32], 1_000_000); c.tx(s, 900, vec![e], vec![]); }
}

fn sold(c: Option<u64>, sigs: &[&str], qty: u64) -> SellOut {
    SellOut { sold_at: c, sigs: sigs.iter().map(|s| (s.to_string(), true, 1_200_000)).collect(), last: None, attempts: sigs.len() as u32, last_qty: (qty, true), first_send_us: None }
}

/// TEST 1: whale A buys 7% and whale B 8%; A dumps (a single >= 6% sell): at the first executed tx of slot dump + 3 a re-arm window
/// arms with B listed (its own size, the window to dump + 3 + 20, at once); B dumps inside the window and our attempt fills right
/// after it: a re-arm position at the re-arm size; the exit (the slot limit), the sell landing, the close and the realized are all
/// tagged rearm (records "kind":"rearm", the log lines end " [rearm]", their prefixes dip25's)
#[test]
fn dip26_rearm_holder_b_dumps_fill_exit_realized_tagged() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let inflight0 = ACCT.inflight.load(Ordering::SeqCst);
    let mut c = Ctx::new(&["--presend-live-rearm", "on", "--presend-live-rearm-size-sol", "0.3"]);
    assert_eq!((c.p.cfg.spend, c.p.cfg.rearm.spend), (400_000_000, 300_000_000));
    let (a, b, x) = ([0xA1u8; 32], [0xB1u8; 32], [0x33u8; 32]);
    let mut tk = c.token(1, 1000, &[(a, 7.0), (b, 8.0)]);
    let mut z = c.token(90, 1000, &[]);
    for s in 1001..=1004 { let e = tk.buy(x, S / 10); c.tx(s, 5, vec![e], vec![]); }
    assert!(c.ev("presend_live_arm").is_empty() && c.p.st.triggers == 0, "create-slot buys are never T2 triggers");
    // A dumps all its 7% at slot 1005: a candidate (age 5)
    let d = tk.sell_tok(a, pct(7.0));
    c.tx(1005, 5, vec![d], vec![]);
    assert_eq!((c.rearm().cands.len(), c.rearm().st.cands, c.rearm().st.sells6), (1, 1, 1));
    // slots 1006 / 1007: no check yet; the first executed tx of slot 1008 = the end of slot dump + 2: the holders check, armed
    clock(&mut c, &mut z, 1006, 1007);
    assert!(c.p.armed.is_empty() && c.rearm().cands.len() == 1);
    clock(&mut c, &mut z, 1008, 1008);
    let w = *c.p.armed.get(&tk.mint).expect("armed at dump + 3");
    assert!(c.p.rearm_w(w) && c.rearm().cands.is_empty());
    {
        let g = c.p.sh.wins.lock().unwrap();
        let sw = g.iter().find(|s| s.id == w).unwrap();
        assert_eq!((sw.spend, sw.rearm, sw.en_slot, sw.stop_ns), (300_000_000, true, 1028, u64::MAX), "the re-arm size, the window to dump + 3 + 20");
        assert!(sw.st_ns <= arbx::fast::mono_ns(), "the window starts at once (no +50 ms)");
    }
    let arm = c.ev("presend_live_arm").pop().unwrap();
    assert_eq!((arm["kind"].as_str(), arm["w"].as_u64(), arm["gap"].as_u64(), arm["check_slot"].as_u64(), arm["arm_slot"].as_u64(), arm["en_slot"].as_u64()),
        (Some("rearm"), Some(w), Some(20), Some(1008), Some(1008), Some(1028)));
    assert_eq!((arm["dump"]["seller"].as_str(), arm["dump"]["slot"].as_u64(), arm["dump"]["tok"].as_u64(), arm["dump"]["age_slots"].as_u64()), (Some(b58(&a).as_str()), Some(1005), Some(pct(7.0)), Some(5)));
    assert!((arm["dump"]["pct"].as_f64().unwrap() - 7.0).abs() < 1e-9 && arm["dump"]["drop_pct"].as_f64().unwrap() > 5.0);
    assert_eq!(arm["holders"], serde_json::json!([{"w": b58(&b), "pct": 8.0}]), "B is listed (A sold out)");
    assert_eq!((arm["deferred_ms"].as_f64(), arm["spend"].as_u64()), (Some(0.0), Some(300_000_000)));
    assert!(arm.get("trig").is_none(), "no T2 trigger object (the observatory's tailer reads T2 arms by it)");
    assert!(c.lines.iter().any(|l| l.starts_with(&format!("  PRESEND LIVE REARM ARM w{w} {} | dump {}", b58(&tk.mint), &b58(&a)[..8])) && l.contains(&format!("holders {} 8.0%", &b58(&b)[..8]))
        && l.contains("until slot 1028")), "{:?}", c.lines);
    // the window's latest curve state on every trade (the next attempt's limit)
    let e = tk.buy(x, S / 20); c.tx(1009, 3, vec![e.clone()], vec![]);
    assert_eq!(c.p.sh.wins.lock().unwrap().iter().find(|s| s.id == w).map(|s| (s.vsol, s.vtok)), Some((e.vsol, e.vtok)));
    // an attempt (the sender's), then B dumps its 8% at slot 1012 and our attempt fills right after it, in the same slot
    let sig = c.attempt(w, tk.mint, 1011);
    let db = tk.sell_tok(b, pct(8.0));
    c.tx(1012, 7, vec![db], vec![]);
    assert_eq!(c.p.rearm_stop_why(w), Some("whale_dump"), "the next >= 6% sell stops the window 30 ms later");
    assert!(c.p.sh.wins.lock().unwrap().iter().find(|s| s.id == w).unwrap().stop_ns < u64::MAX);
    let f = c.fill(&mut tk, sig, 1012, 8, 296_296_296);
    let pp = &c.p.pos[&tk.mint];
    assert_eq!((pp.spend, pp.rearm, pp.tokens, pp.w), (300_000_000, true, f.tok, w), "a re-arm position at the re-arm size");
    assert_eq!(ACCT.open_pos.lock().unwrap().get(&tk.mint).copied(), Some(300_000_000 + 5_000 + 200_000 + T22_ATA_RENT), "the kill switch values it at its cost");
    assert!(c.p.sh.pause_pos.load(Ordering::Relaxed), "one position: every window pauses");
    let fill = c.ev("presend_live_fill").pop().unwrap();
    assert_eq!((fill["kind"].as_str(), fill["spend"].as_u64(), fill["window_open"].as_bool(), fill["slots_after_trigger"].as_u64()), (Some("rearm"), Some(300_000_000), Some(true), Some(7)));
    let dis = c.ev("presend_live_disarm").pop().unwrap();
    // the others since the arm: X's buy and B's dump (our fill is ours)
    assert_eq!((dis["kind"].as_str(), dis["why"].as_str(), dis["rearm"]["stop"].as_str(), dis["rearm"]["others"].as_u64()), (Some("rearm"), Some("filled"), Some("whale_dump"), Some(2)));
    assert!(dis.get("quiet").is_none());
    assert!(c.lines.iter().any(|l| l.starts_with(&format!("  PRESEND LIVE FILL w{w} {}", b58(&tk.mint))) && l.ends_with(" [rearm]")), "{:?}", c.lines);
    // the exit at entry slot + 2 (the slot limit), its sell round (the account kept open)
    clock(&mut c, &mut z, 1013, 1014);
    let ex = c.ev("presend_live_exit").pop().unwrap();
    assert_eq!((ex["kind"].as_str(), ex["why"].as_str(), ex["w"].as_u64()), (Some("rearm"), Some("time-limit"), Some(w)));
    assert!(c.lines.iter().any(|l| l.starts_with(&format!("  PRESEND LIVE EXIT {} time-limit slot 1014", b58(&tk.mint))) && l.ends_with(" [rearm]")), "{:?}", c.lines);
    let Some(Cmd::Sell { pid, round: 1, known, keep_ata: true, .. }) = c.cmds.iter().find(|x| matches!(x, Cmd::Sell { .. })).cloned() else { panic!("{:?}", c.cmds) };
    assert_eq!(known, Some(f.tok));
    // our sell lands; the round's answer: the position closes; its realized lookup is tagged
    let sg2 = { let mut s = [0u8; 64]; s[0] = 0x5E; s[1] = 0x11; s };
    let es = tk.sell_tok(USER, f.tok);
    c.tx_sig(1014, 9, sg2, USER, vec![es], vec![]);
    let sl = c.ev("presend_live_sell_land").pop().unwrap();
    assert_eq!((sl["kind"].as_str(), sl["pid"].as_u64()), (Some("rearm"), Some(pid)));
    c.p.on_msg(PsMsg::Sold(tk.mint, pid, 1, sold(Some(1014), &["RSELL1"], f.tok)), &|_| false);
    c.drain();
    assert!(c.p.pos.is_empty() && !c.p.sh.pause_pos.load(Ordering::Relaxed));
    let cl = c.ev("presend_live_close").pop().unwrap();
    assert_eq!((cl["kind"].as_str(), cl["result"].as_str(), cl["spend"].as_u64()), (Some("rearm"), Some("sold"), Some(300_000_000)));
    assert!(c.lines.iter().any(|l| l.starts_with(&format!("  PRESEND LIVE CLOSED {} sold via time-limit; curve PnL", b58(&tk.mint))) && l.ends_with(" [rearm]")), "{:?}", c.lines);
    let Some(Cmd::Realized { pid: rp, w: rw, rearm: true, buys, sells, .. }) = c.cmds.iter().find(|x| matches!(x, Cmd::Realized { .. })).cloned() else { panic!("{:?}", c.cmds) };
    assert_eq!((rp, rw, buys.len(), sells.len()), (pid, w, 1, 1));
    // the realized task's record and line (realized_out): tagged; the line's prefix is dip25's (the run report's and dipmon's regex)
    let bs = vec![(Some((-300_280_000i64, 5_000u64, true)), buys[0].1)];
    let (rec, line) = realized_out(w, pid, &tk.mint, -12_345_678, &buys, &bs, 1, 1, 1, true);
    assert_eq!((rec["kind"].as_str(), rec["pnl"].as_i64(), rec["src"].as_str()), (Some("rearm"), Some(-12_345_678), Some("tx")));
    assert_eq!(line, format!("  PRESEND LIVE REALIZED {} -0.012346 SOL (tx: 1/1 buy tx(s), 1/1 sell tx(s)) [rearm]", b58(&tk.mint)));
    let (rec2, line2) = realized_out(w, pid, &tk.mint, -12_345_678, &buys, &bs, 1, 1, 1, false);
    assert!(rec2.get("kind").is_none());
    assert_eq!(line2, format!("  PRESEND LIVE REALIZED {} -0.012346 SOL (tx: 1/1 buy tx(s), 1/1 sell tx(s))", b58(&tk.mint)), "T2: dip25's line");
    // the split by kind (the realized task adds to it)
    let z2 = c.p.rz().unwrap();
    z2.add(true, -12_345_678); z2.add(false, 40_000_000); z2.add(false, -1_000_000);
    assert_eq!(c.p.rearm_split().unwrap(), serde_json::json!({"t2": {"pnl": 39_000_000, "n": 2}, "rearm": {"pnl": -12_345_678, "n": 1}}));
    let st = c.p.status();
    assert!(st.contains(" | rearm: windows 1 armed now 0 fills 1 realized -0.0123 SOL (sells >= 6% 2 candidates 2 checks 1"), "{st}");
    let fin = c.p.finish(1100, None);
    assert_eq!((fin["rearm"]["windows"].as_u64(), fin["rearm"]["fills"].as_u64(), fin["rearm"]["closed"].as_u64(), fin["rearm"]["ends"]["filled"].as_u64()), (Some(1), Some(1), Some(1), Some(1)));
    assert_eq!(fin["cfg"]["rearm"]["spend"].as_u64(), Some(300_000_000));
    assert_eq!(fin["fills"].as_u64(), Some(1), "the pre-send fills (and their cap) count every kind");
    drop(c);
    assert_eq!(ACCT.inflight.load(Ordering::SeqCst), inflight0);
}

/// TESTS 2-4: no window when no other wallet holds >= 6% at the check ("rearm_no_holder", B at 5.9%), when the token is older than 141
/// slots at the dump ("rearm_age"; 141 itself is a candidate), when the post-sell curve is >= 100 SOL ("rearm_untradeable"); sells below
/// 6% and our own sells are no candidates at all (nothing recorded)
#[test]
fn dip26_rearm_no_holder_age_untradeable() {
    let mut c = Ctx::new(&RE_ON);
    let (a, b) = ([0xA1u8; 32], [0xB1u8; 32]);
    let mut z = c.token(90, 1000, &[]);
    // no holder: B 5.9%
    let mut t1 = c.token(1, 1000, &[(a, 7.0), (b, 5.9)]);
    let d = t1.sell_tok(a, pct(7.0)); c.tx(1002, 5, vec![d], vec![]);
    // a 5.99% sell and a sell of ours: no candidates
    let mut t2 = c.token(2, 1000, &[(a, 7.0), (b, 8.0), (USER, 6.5)]);
    let d = t2.sell_tok(a, pct(5.99)); c.tx(1002, 6, vec![d], vec![]);
    let d = t2.sell_tok(USER, pct(6.5)); c.tx(1002, 7, vec![d], vec![]);
    clock(&mut c, &mut z, 1003, 1006);
    let sk = c.ev("presend_live_skip");
    assert_eq!(sk.len(), 1, "{sk:?}");
    assert_eq!((sk[0]["kind"].as_str(), sk[0]["why"].as_str(), sk[0]["mint"].as_str(), sk[0]["check_slot"].as_u64()), (Some("rearm"), Some("rearm_no_holder"), Some(b58(&t1.mint).as_str()), Some(1005)));
    assert_eq!(sk[0]["holders"], serde_json::json!([]));
    assert!(c.p.armed.is_empty() && c.ev("presend_live_arm").is_empty());
    assert_eq!((c.rearm().st.sells6, c.rearm().st.cands), (1, 1), "only the real candidate counts");
    // age: a dump at age 142 -> rearm_age (no candidate); at age 141 -> a candidate (armed at + 3)
    let mut t3 = c.token(3, 1000, &[(a, 7.0), (b, 8.0)]);
    let mut t4 = c.token(4, 1001, &[(a, 7.0), (b, 8.0)]);
    clock(&mut c, &mut z, 1007, 1141);
    let d = t3.sell_tok(a, pct(7.0)); c.tx(1142, 5, vec![d], vec![]);
    let d = t4.sell_tok(a, pct(7.0)); c.tx(1142, 6, vec![d], vec![]);
    let sk = c.ev("presend_live_skip").pop().unwrap();
    assert_eq!((sk["why"].as_str(), sk["mint"].as_str(), sk["dump"]["age_slots"].as_u64()), (Some("rearm_age"), Some(b58(&t3.mint).as_str()), Some(142)));
    assert_eq!(c.rearm().cands.len(), 1);
    clock(&mut c, &mut z, 1143, 1145);
    assert!(c.p.armed.get(&t4.mint).is_some_and(|w| c.p.rearm_w(*w)), "age 141: armed");
    // untradeable: the post-sell curve >= 100 SOL (a 110 SOL buyer in the create slot holds it there)
    let mut t5 = c.token(5, 1150, &[(a, 7.0), (b, 8.0)]);
    let e = t5.buy([0xC5; 32], 110 * S); c.tx(1150, 9, vec![e], vec![]);
    let d = t5.sell_tok(a, pct(7.0)); c.tx(1151, 5, vec![d.clone()], vec![]);
    assert!(d.vsol >= 100 * S, "{}", d.vsol);
    let sk = c.ev("presend_live_skip").pop().unwrap();
    assert_eq!((sk["why"].as_str(), sk["mint"].as_str()), (Some("rearm_untradeable"), Some(b58(&t5.mint).as_str())));
    assert_eq!(c.rearm().st.skips.get("rearm_untradeable"), Some(&1));
    let st = c.p.status();
    assert!(st.contains("skips {rearm_age 1, rearm_no_holder 1, rearm_untradeable 1}"), "{st}");
}

/// THE STOPS of an armed window: 30 ms after the next >= 6% sell ("whale_dump"; that sell is a new candidate itself), 30 ms after the
/// trade after which no wallet but ours holds >= 6% ("no_holder"); a smaller sell that leaves a holder stops nothing; the holders check
/// is made before the trades of the tx that moves the clock (a holder selling in it is still listed, then stops the window)
#[test]
fn dip26_rearm_stops_whale_dump_no_holder() {
    let mut c = Ctx::new(&RE_ON);
    let (a, b, d6) = ([0xA1u8; 32], [0xB1u8; 32], [0xD7u8; 32]);
    let mut z = c.token(90, 1000, &[]);
    let mut t1 = c.token(1, 1000, &[(a, 7.0), (b, 8.0), (d6, 7.0)]);
    let d = t1.sell_tok(a, pct(7.0)); c.tx(1002, 5, vec![d], vec![]);
    clock(&mut c, &mut z, 1003, 1005);
    let w1 = c.p.armed[&t1.mint];
    assert_eq!(c.ev("presend_live_arm").pop().unwrap()["holders"].as_array().unwrap().len(), 2);
    // D sells 1%: B (8%) and D (6%) still hold: nothing
    let e = t1.sell_tok(d6, pct(1.0)); c.tx(1006, 5, vec![e], vec![]);
    assert_eq!(c.p.rearm_stop_why(w1), None);
    // B sells 6.5%: a >= 6% sell: whale_dump (30 ms later), and a new candidate
    let e = t1.sell_tok(b, pct(6.5)); c.tx(1007, 5, vec![e], vec![]);
    assert_eq!(c.p.rearm_stop_why(w1), Some("whale_dump"));
    assert_eq!(c.rearm().cands.len(), 1, "the next dump is a candidate itself");
    c.tick(1007);
    assert!(c.p.wins[&w1].disarmed.is_none(), "not before 30 ms");
    std::thread::sleep(Duration::from_millis(35));
    c.tick(1007);
    let dis = c.ev("presend_live_disarm").pop().unwrap();
    assert_eq!((dis["w"].as_u64(), dis["why"].as_str(), dis["kind"].as_str()), (Some(w1), Some("whale_dump"), Some("rearm")));
    assert!(!c.p.armed.contains_key(&t1.mint));
    // its candidate: D still holds 6% at its check -> armed again (D listed)
    clock(&mut c, &mut z, 1008, 1010);
    let w2 = c.p.armed[&t1.mint];
    assert!(w2 != w1 && c.p.rearm_w(w2));
    assert_eq!(c.ev("presend_live_arm").pop().unwrap()["holders"], serde_json::json!([{"w": b58(&d6), "pct": 6.0}]));
    // D sells 0.5% (not >= 6%): no wallet holds >= 6% any more: no_holder (30 ms later)
    let e = t1.sell_tok(d6, pct(0.5)); c.tx(1011, 5, vec![e], vec![]);
    assert_eq!(c.p.rearm_stop_why(w2), Some("no_holder"));
    std::thread::sleep(Duration::from_millis(35));
    c.tick(1011);
    assert_eq!(c.ev("presend_live_disarm").pop().unwrap()["why"].as_str(), Some("no_holder"));
    // the check is made before the trades of the tx that moves the clock: B2 sells below 6% in the very first tx of slot dump + 3
    let mut t2 = c.token(2, 1012, &[(a, 7.0), (b, 6.5)]);
    let d = t2.sell_tok(a, pct(7.0)); c.tx(1013, 5, vec![d], vec![]);
    clock(&mut c, &mut z, 1014, 1015);
    let e = t2.sell_tok(b, pct(1.0)); c.tx(1016, 1, vec![e], vec![]);
    let arm = c.ev("presend_live_arm").pop().unwrap();
    assert_eq!((arm["mint"].as_str(), arm["check_slot"].as_u64()), (Some(b58(&t2.mint).as_str()), Some(1016)));
    assert_eq!(arm["holders"], serde_json::json!([{"w": b58(&b), "pct": 6.5}]), "the holders at the END of slot dump + 2");
    assert_eq!(c.p.rearm_stop_why(c.p.armed[&t2.mint]), Some("no_holder"), "then its trade stops it");
    assert_eq!(c.rearm().st.ends.get("whale_dump").copied(), Some(1));
}

/// TEST 5: (a) a T2 window armed on the token at the check: no re-arm window ("rearm_blocked_live_armed"); (b) a T2 trigger during a
/// re-arm window takes the token over: the re-arm window is disarmed "superseded" and the T2 window armed (a re-arm window never
/// blocks a T2 trigger; T2 records unchanged)
#[test]
fn dip26_rearm_t2_blocks_and_supersedes() {
    let mut c = Ctx::new(&RE_ON);
    let (a, b, wh) = ([0xA1u8; 32], [0xB1u8; 32], [0xE1u8; 32]);
    let mut z = c.token(90, 1000, &[]);
    // (a) the T2 whale buys 6% at slot 1002 (age 2): a T2 window; A dumps at 1003; the check at 1006: the T2 window is armed
    let mut t1 = c.token(1, 1000, &[(a, 7.0), (b, 8.0)]);
    let e = t1.buy_tok(wh, pct(6.0)); c.tx(1002, 5, vec![e], vec![]);
    let wt = c.p.armed[&t1.mint];
    assert!(!c.p.rearm_w(wt));
    let d = t1.sell_tok(a, pct(7.0)); c.tx(1003, 5, vec![d], vec![]);
    clock(&mut c, &mut z, 1004, 1006);
    let sk = c.ev("presend_live_skip").into_iter().find(|r| r["kind"] == "rearm").unwrap();
    assert_eq!((sk["why"].as_str(), sk["check_slot"].as_u64()), (Some("rearm_blocked_live_armed"), Some(1006)));
    assert_eq!(sk["holders"].as_array().unwrap().len(), 2, "B and the T2 whale");
    assert_eq!(c.p.armed[&t1.mint], wt, "the T2 window unchanged");
    // (b) a re-arm window on token 2; then a T2 trigger on it (whale buys 6% at age 8): it takes the token over
    let mut t2 = c.token(2, 1000, &[(a, 7.0), (b, 8.0)]);
    let d = t2.sell_tok(a, pct(7.0)); c.tx(1006, 6, vec![d], vec![]);
    clock(&mut c, &mut z, 1007, 1009);
    let wr = c.p.armed[&t2.mint];
    assert!(c.p.rearm_w(wr));
    let n_arm_t2 = c.p.st.armed;
    let e = t2.buy_tok(wh, pct(6.0)); c.tx(1010, 5, vec![e], vec![]);
    let wt2 = c.p.armed[&t2.mint];
    assert!(wt2 != wr && !c.p.rearm_w(wt2), "the T2 window holds the token");
    assert_eq!(c.p.st.armed, n_arm_t2 + 1);
    let dis = c.ev("presend_live_disarm").into_iter().find(|r| r["w"] == wr).unwrap();
    assert_eq!((dis["why"].as_str(), dis["kind"].as_str()), (Some("superseded"), Some("rearm")));
    assert!(c.p.sh.wins.lock().unwrap().iter().all(|s| s.id != wr), "the re-arm window's attempts stop");
    let arm = c.ev("presend_live_arm").into_iter().find(|r| r["w"] == wt2).unwrap();
    assert!(arm.get("kind").is_none() && arm["trig"]["mint"] == b58(&t2.mint), "the T2 arm record as dip25's");
    assert_eq!(c.p.st.skips.get("blocked_armed"), None, "a re-arm window never blocks a T2 trigger");
    assert_eq!(c.p.st.disarms.get("superseded"), None, "the T2 counters stay T2's");
    assert_eq!(c.rearm().st.ends.get("superseded"), Some(&1));
}

/// TEST 6: our position open on the token at the check: the window WAITS ("presend_live_rearm_defer") and arms when the position is
/// sold, its margin passed and our token account closed (deferred_ms > 0), while it is <= its last slot; a window still blocked past
/// its last slot never arms ("rearm_blocked_ata_open", ended "expired"); the account guard is never weakened (no arm while it is open)
#[test]
fn dip26_rearm_deferred_until_clear_or_never() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let inflight0 = ACCT.inflight.load(Ordering::SeqCst);
    let mut c = Ctx::new(&RE_ON);
    let (a, b, wh) = ([0xA1u8; 32], [0xB1u8; 32], [0xE1u8; 32]);
    let mut z = c.token(90, 1000, &[]);
    for (k, close) in [(1u8, true), (2u8, false)] {
        let s0 = if close { 1000 } else { 1100 };
        let mut tk = c.token(k, s0, &[(a, 7.0), (b, 8.0)]);
        // a T2 window and its fill: our position on the token
        let e = tk.buy_tok(wh, pct(6.0)); c.tx(s0 + 2, 5, vec![e], vec![]);
        let wt = c.p.armed[&tk.mint];
        let sg = c.attempt(wt, tk.mint, s0 + 2);
        let f = c.fill(&mut tk, sg, s0 + 3, 4, 395_061_727);
        assert!(c.p.pos.contains_key(&tk.mint));
        // A dumps; the check at dump + 3 finds our position: the window waits
        let d = tk.sell_tok(a, pct(7.0)); c.tx(s0 + 4, 5, vec![d], vec![]);
        clock(&mut c, &mut z, s0 + 5, s0 + 7);
        assert!(!c.p.armed.contains_key(&tk.mint) && c.rearm().defer.len() == 1);
        let df = c.ev("presend_live_rearm_defer").pop().unwrap();
        assert_eq!((df["why"].as_str(), df["mint"].as_str(), df["check_slot"].as_u64(), df["en_slot"].as_u64()), (Some("position"), Some(b58(&tk.mint).as_str()), Some(s0 + 7), Some(s0 + 27)));
        // the position's exit (entry + 2 passed) and its sell: sold; the account stays open (the guard): still waiting
        let pid = c.p.pos[&tk.mint].pid;
        c.p.on_msg(PsMsg::Sold(tk.mint, pid, 1, sold(Some(s0 + 7), &["S1"], f.tok)), &|_| false);
        c.drain();
        assert!(c.p.pos.is_empty() && c.p.atas.contains_key(&tk.mint));
        c.tick(s0 + 7);
        assert_eq!(c.rearm().defer[0].why, "margin", "the sell's 300 ms margin first");
        c.p.free_at.remove(&tk.mint);
        c.tick(s0 + 7);
        assert_eq!((c.rearm().defer[0].why, c.p.armed.contains_key(&tk.mint)), ("ata_open", false), "never armed while our token account is open");
        if close {
            // no attempt can land any more (quiet + 2): the confirmed read (0) and the close; then the window arms at once
            clock(&mut c, &mut z, s0 + 8, s0 + 9);
            let rd = c.cmds.iter().rev().find_map(|x| match x { Cmd::Read { mint, min_slot, why: Why::Close, n } if *mint == tk.mint => Some((*min_slot, *n)), _ => None }).expect("the close read");
            c.p.on_msg(PsMsg::Read(tk.mint, Why::Close, rd.0, rd.1, crate::Tok::Amount(0, s0 + 9)), &|_| false);
            c.drain();
            assert!(c.cmds.iter().any(|x| matches!(x, Cmd::Close { mint } if *mint == tk.mint)));
            assert!(!c.p.armed.contains_key(&tk.mint), "not while the close is under way");
            c.p.on_msg(PsMsg::Closed(tk.mint, "CL".into(), Some(s0 + 10), String::new()), &|_| false);
            c.tick(s0 + 10);
            let w = *c.p.armed.get(&tk.mint).expect("armed once clear");
            assert!(c.p.rearm_w(w));
            let arm = c.ev("presend_live_arm").pop().unwrap();
            assert_eq!((arm["kind"].as_str(), arm["deferred"].as_str(), arm["check_slot"].as_u64(), arm["en_slot"].as_u64()), (Some("rearm"), Some("ata_open"), Some(s0 + 7), Some(s0 + 27)));
            assert!(arm["deferred_ms"].as_f64().unwrap() > 0.0 && arm["arm_ms_after_dump"].as_f64().unwrap() >= arm["deferred_ms"].as_f64().unwrap());
            assert_eq!(arm["holders"].as_array().unwrap().len(), 2, "the check's holders (B and the T2 whale)");
            assert!(arm["holders_arm"].is_array());
            assert_eq!(c.rearm().st.deferred_armed, 1);
        } else {
            // never cleared: past its last slot it is never armed
            clock(&mut c, &mut z, s0 + 8, s0 + 28);
            assert!(!c.p.armed.contains_key(&tk.mint) && c.rearm().defer.is_empty());
            let sk = c.ev("presend_live_skip").into_iter().filter(|r| r["kind"] == "rearm").next_back().unwrap();
            assert_eq!((sk["why"].as_str(), sk["ended"].as_str(), sk["deferred"].as_str()), (Some("rearm_blocked_ata_open"), Some("expired"), Some("ata_open")));
            assert!(sk["deferred_ms"].as_f64().unwrap() > 0.0);
        }
    }
    assert_eq!((c.rearm().st.deferred, c.rearm().st.deferred_armed), (2, 1));
    drop(c);
    assert_eq!(ACCT.inflight.load(Ordering::SeqCst), inflight0);
}

/// TEST 6b: an attempt of an earlier window on the token that can still land (its deadline / its window's disarm bound not passed) holds
/// the re-arm window back ("inflight"): it arms once no such attempt can land (a late fill would otherwise hold the token while it tries)
#[test]
fn dip26_rearm_waits_for_attempts_in_flight() {
    let mut c = Ctx::new(&RE_ON);
    let (a, b) = ([0xA1u8; 32], [0xB1u8; 32]);
    let mut z = c.token(90, 1000, &[]);
    let mut tk = c.token(1, 1000, &[(a, 7.0), (b, 8.0)]);
    let d = tk.sell_tok(a, pct(7.0)); c.tx(1002, 5, vec![d], vec![]);
    // an earlier window's attempt on the token, deadline 1006 (the dip19 quiet slot of the mint)
    c.p.quiet.insert(tk.mint, 1006);
    clock(&mut c, &mut z, 1003, 1005);
    assert!(!c.p.armed.contains_key(&tk.mint));
    assert_eq!(c.ev("presend_live_rearm_defer").pop().unwrap()["why"].as_str(), Some("inflight"));
    clock(&mut c, &mut z, 1006, 1006);
    assert!(!c.p.armed.contains_key(&tk.mint), "its deadline slot: it can still land");
    clock(&mut c, &mut z, 1007, 1007);
    let w = *c.p.armed.get(&tk.mint).expect("armed once no attempt can land");
    assert!(c.p.rearm_w(w));
    assert_eq!(c.ev("presend_live_arm").pop().unwrap()["deferred"].as_str(), Some("inflight"));
}

/// TEST 7: QUIET 6:2 on the re-arm's clock: at the first slot >= the arm slot + 6 a window with fewer than 2 trades by anyone but us
/// since the arm is disarmed "quiet" (our own trade not counted); with 2 it runs on (decided, never stops); N:M from the flag
#[test]
fn dip26_rearm_quiet_stop() {
    let mut c = Ctx::new(&RE_ON);
    let (a, b, x, y) = ([0xA1u8; 32], [0xB1u8; 32], [0x31u8; 32], [0x32u8; 32]);
    let mut z = c.token(90, 1000, &[]);
    let mut t1 = c.token(1, 1000, &[(a, 7.0), (b, 8.0)]);
    let mut t2 = c.token(2, 1000, &[(a, 7.0), (b, 8.0)]);
    let d = t1.sell_tok(a, pct(7.0)); c.tx(1002, 5, vec![d], vec![]);
    let d = t2.sell_tok(a, pct(7.0)); c.tx(1002, 6, vec![d], vec![]);
    clock(&mut c, &mut z, 1003, 1005);
    let (w1, w2) = (c.p.armed[&t1.mint], c.p.armed[&t2.mint]);
    // token 1: one other trade and one of ours; token 2: two others
    let e = t1.buy(x, S / 10); c.tx(1006, 5, vec![e], vec![]);
    let e = t1.buy(USER, S / 10); c.tx(1007, 5, vec![e], vec![]);
    let e = t2.buy(x, S / 10); c.tx(1006, 6, vec![e], vec![]);
    let e = t2.buy(y, S / 10); c.tx(1008, 6, vec![e], vec![]);
    clock(&mut c, &mut z, 1009, 1010);
    assert!(c.p.wins[&w1].disarmed.is_none(), "before arm slot + 6 (1011)");
    clock(&mut c, &mut z, 1011, 1011);
    assert_eq!(c.p.wins[&w1].disarmed, Some("quiet"));
    assert_eq!(c.p.wins[&w2].disarmed, None, "2 other trades: it runs on");
    let dis = c.ev("presend_live_disarm").pop().unwrap();
    assert_eq!((dis["w"].as_u64(), dis["why"].as_str(), dis["rearm"]["others"].as_u64(), dis["rearm"]["quiet_stop"].as_bool(), dis["rearm"]["quiet"].as_str()),
        (Some(w1), Some("quiet"), Some(1), Some(true), Some("6:2")));
    assert!(c.lines.iter().any(|l| l.starts_with(&format!("  PRESEND LIVE REARM QUIET STOP w{w1} {}: 1 other trade(s) since the arm by slot +6 (needs 2 by +6)", b58(&t1.mint)))), "{:?}", c.lines);
    assert!(c.p.sh.wins.lock().unwrap().iter().all(|s| s.id != w1));
    // token 2 later ends at its last slot (dump 1002 + 3 + 20 = 1025)
    clock(&mut c, &mut z, 1012, 1026);
    let dis = c.ev("presend_live_disarm").into_iter().find(|r| r["w"] == w2).unwrap();
    assert_eq!((dis["why"].as_str(), dis["rearm"]["quiet_stop"].as_bool()), (Some("expired"), Some(false)));
    // the flag's N:M (4:3): stopped at + 4 with 2 others
    let mut c = Ctx::new(&["--presend-live-rearm", "on", "--presend-live-rearm-quiet-stop", "4:3"]);
    let mut z = c.token(90, 1000, &[]);
    let mut t3 = c.token(3, 1000, &[(a, 7.0), (b, 8.0)]);
    let d = t3.sell_tok(a, pct(7.0)); c.tx(1002, 5, vec![d], vec![]);
    clock(&mut c, &mut z, 1003, 1005);
    let w3 = c.p.armed[&t3.mint];
    for (s, u) in [(1006, x), (1007, y)] { let e = t3.buy(u, S / 10); c.tx(s, 5, vec![e], vec![]); }
    clock(&mut c, &mut z, 1008, 1009);
    assert_eq!(c.p.wins[&w3].disarmed, Some("quiet"));
}

/// TEST 8: one position for every kind: a re-arm fill pauses every other window (T2 and re-arm) and blocks the reactive bot; a T2
/// position pauses the re-arm windows; the windows stay armed (paused, not dropped) and resume when the position closes
#[test]
fn dip26_rearm_one_position_both_ways() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let mut c = Ctx::new(&RE_ON);
    let (a, b, wh) = ([0xA1u8; 32], [0xB1u8; 32], [0xE1u8; 32]);
    let mut z = c.token(90, 1000, &[]);
    let mut tx_ = c.token(1, 1000, &[(a, 7.0), (b, 8.0)]);
    let mut ty = c.token(2, 1000, &[(a, 7.0), (b, 8.0)]);
    let mut tz = c.token(3, 1000, &[]);
    let d = tx_.sell_tok(a, pct(7.0)); c.tx(1002, 5, vec![d], vec![]);
    let d = ty.sell_tok(a, pct(7.0)); c.tx(1002, 6, vec![d], vec![]);
    let e = tz.buy_tok(wh, pct(6.0)); c.tx(1003, 5, vec![e], vec![]);
    clock(&mut c, &mut z, 1004, 1005);
    let (wx, wy, wt) = (c.p.armed[&tx_.mint], c.p.armed[&ty.mint], c.p.armed[&tz.mint]);
    assert!(c.p.rearm_w(wx) && c.p.rearm_w(wy) && !c.p.rearm_w(wt));
    let gate = |c: &Ctx, w: u64| { let sp = c.p.sh.wins.lock().unwrap().iter().find(|s| s.id == w).map(|s| s.spend).unwrap(); send_gate(&c.p.sh, c.p.cfg.one_position, sp) };
    assert_ne!(gate(&c, wx), Some("paused_presend_position"));
    // a re-arm fill on X: every other window pauses (armed, not dropped)
    let sg = c.attempt(wx, tx_.mint, 1005);
    let f = c.fill(&mut tx_, sg, 1006, 4, 395_061_727);
    assert!(c.p.sh.pause_pos.load(Ordering::Relaxed));
    for w in [wy, wt] { assert_eq!(gate(&c, w), Some("paused_presend_position"), "w{w}"); assert!(c.p.wins[&w].disarmed.is_none()); }
    assert_eq!(c.p.blocks_reactive(&[0x99; 32]), Some("presend_position_open"), "the reactive bot too");
    // its exit (entry + 2) and its sell: closed: they resume
    clock(&mut c, &mut z, 1007, 1008);
    assert!(c.p.pos[&tx_.mint].exit.is_some());
    for w in [wy, wt] { assert_eq!(gate(&c, w), Some("paused_presend_position"), "still held while it sells"); }
    let pid = c.p.pos[&tx_.mint].pid;
    c.p.on_msg(PsMsg::Sold(tx_.mint, pid, 1, sold(Some(1008), &["S"], f.tok)), &|_| false);
    assert!(c.p.pos.is_empty());
    for w in [wy, wt] { assert_ne!(gate(&c, w), Some("paused_presend_position"), "w{w}"); assert!(c.p.wins[&w].disarmed.is_none()); }
    // a T2 fill on Z: the re-arm window on Y pauses
    let sg = c.attempt(wt, tz.mint, 1008);
    let _ = c.fill(&mut tz, sg, 1009, 4, 395_061_727);
    assert!(c.p.pos.contains_key(&tz.mint) && !c.p.pos[&tz.mint].rearm);
    assert_eq!(gate(&c, wy), Some("paused_presend_position"));
    assert!(c.p.wins[&wy].disarmed.is_none());
    // and a re-arm check meanwhile still arms (paused like the others)
    let mut tw = c.token(4, 1000, &[(a, 7.0), (b, 8.0)]);
    let d = tw.sell_tok(a, pct(7.0)); c.tx(1009, 6, vec![d], vec![]);
    clock(&mut c, &mut z, 1010, 1012);
    let ww = c.p.armed[&tw.mint];
    assert!(c.p.rearm_w(ww) && gate(&c, ww) == Some("paused_presend_position"));
    let pid = c.p.pos[&tz.mint].pid;
    c.p.on_msg(PsMsg::Sold(tz.mint, pid, 1, sold(Some(1012), &["S2"], 1)), &|_| false);
    assert!(c.p.pos.is_empty() && gate(&c, ww) != Some("paused_presend_position"));
    drop(c);
}

/// TEST 9: the re-arm size is what its attempts buy with (the sender's window, its min-out and buy instruction), what its position is
/// valued at (TP / SL) and costed at; T2 windows keep the pre-send size; the size above the per-buy cap is refused at the start
#[test]
fn dip26_rearm_size_used_and_cap_refused() {
    let c0 = cfg(&["--presend-live-rearm", "on", "--presend-live-rearm-size-sol", "0.25"]).unwrap().unwrap();
    assert_eq!((c0.spend, c0.rearm.spend), (400_000_000, 250_000_000));
    assert_eq!(cfg(&RE_ON).unwrap().unwrap().rearm.spend, 400_000_000, "default: the pre-send size");
    let mut c = Ctx::with(c0.clone());
    let (a, b, wh) = ([0xA1u8; 32], [0xB1u8; 32], [0xE1u8; 32]);
    let mut z = c.token(90, 1000, &[]);
    let mut t1 = c.token(1, 1000, &[(a, 7.0), (b, 8.0)]);
    let mut t2 = c.token(2, 1000, &[]);
    let d = t1.sell_tok(a, pct(7.0)); c.tx(1002, 5, vec![d], vec![]);
    let e = t2.buy_tok(wh, pct(6.0)); c.tx(1003, 5, vec![e], vec![]);
    clock(&mut c, &mut z, 1004, 1005);
    let (wr, wt) = (c.p.armed[&t1.mint], c.p.armed[&t2.mint]);
    let (sr, st) = { let g = c.p.sh.wins.lock().unwrap(); (g.iter().find(|s| s.id == wr).cloned().unwrap(), g.iter().find(|s| s.id == wt).cloned().unwrap()) };
    assert_eq!((sr.spend, st.spend), (250_000_000, 400_000_000));
    let user = pk("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE");
    let guard = guard_ix_enc(GuardEnc { disc: 15, op: 4, acct: true }, 1006);
    for (sw, want) in [(&sr, 250_000_000u64), (&st, 400_000_000)] {
        let (min_out, lim, _) = att_limit(sw, c0.drop).unwrap();
        assert_eq!(Some((min_out, lim)), pl::limit_min_out(sw.vsol, sw.vtok, want, sw.fr, c0.drop).map(|x| (x.0, x.1)), "the limit at the window's own size");
        let (ixs, roles) = att_ixs(user, sw, min_out, &c0, guard.clone(), None);
        let bi = &ixs[roles.buy.unwrap() as usize];
        assert_eq!((u64::from_le_bytes(bi.data[8..16].try_into().unwrap()), u64::from_le_bytes(bi.data[16..24].try_into().unwrap())), (want, min_out), "the buy spends the window's size");
        let (ref_ixs, ref_roles) = pl::attempt_ixs(user, &sw.launch, want, min_out, c0.cu_limit, c0.cu_price, guard.clone(), None);
        assert_eq!(roles, ref_roles);
        assert!(ixs.iter().zip(&ref_ixs).all(|(x, y)| x.program == y.program && x.data == y.data && x.accounts == y.accounts) && ixs.len() == ref_ixs.len(), "dip25's attempt otherwise");
    }
    // the position: valued and costed at the re-arm size
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let sg = c.attempt(wr, t1.mint, 1005);
    let f = c.fill(&mut t1, sg, 1006, 4, 246_913_580);
    assert_eq!(c.p.pos[&t1.mint].spend, 250_000_000);
    assert_eq!(c.p.pos[&t1.mint].buys[0].cost, 250_000_000 + 5_000 + 200_000 + T22_ATA_RENT);
    // a +25% move: take-profit (+10% default) on the re-arm size's value
    let e = t1.buy([0x44; 32], 8 * S); c.tx(1006, 9, vec![e.clone()], vec![]);
    let v = pl::value(e.vsol, e.vtok, f.tok, 0.0125, 250_000_000);
    assert!(v > 1.10, "{v}");
    assert_eq!(c.ev("presend_live_exit").pop().unwrap()["why"].as_str(), Some("take-profit"));
    let pid = c.p.pos[&t1.mint].pid;
    c.p.on_msg(PsMsg::Sold(t1.mint, pid, 1, sold(Some(1006), &["S"], f.tok)), &|_| false);
    drop(c);
    // the cap: the re-arm size above --max-sol is refused (live); at it accepted; a dry run has no cap (as the pre-send size)
    let p = arbx::presend::Params::default();
    let e = Cfg::from_argv(&args(&["--presend-live-rearm", "on", "--presend-live-rearm-size-sol", "0.6"]), &p, true, 500_000_000).unwrap_err().to_string();
    assert!(e.contains("REFUSED: --presend-live-rearm-size-sol 0.600 exceeds --max-sol"), "{e}");
    assert!(Cfg::from_argv(&args(&["--presend-live-rearm", "on", "--presend-live-rearm-size-sol", "0.4"]), &p, true, 500_000_000).is_ok());
    let mut dry = args(&["--presend-live-rearm", "on", "--presend-live-rearm-size-sol", "0.6", "--presend-live-dry"]); dry.retain(|x| x != "--live");
    assert!(Cfg::from_argv(&dry, &p, false, u64::MAX).is_ok());
}

/// TEST 10: the rolling fee budget's pause, the kill switch and the profit lock stop re-arm windows exactly as T2 windows. The fee pause:
/// the sender's gate pauses every window (re-arm windows still arm and are recorded, as T2 windows). The kill switch / profit lock: the
/// engine stops new buys (DIP_NO_FIRE: the same gate's "stopped") and stops the probe (stop("run_stopping") on its next loop pass): the
/// armed re-arm windows are disarmed "stopped", the candidates and the waiting windows end ("rearm_blocked_stopped" / ended "stopped"),
/// no new candidate afterwards
#[test]
fn dip26_rearm_fee_pause_kill_switch_profit_lock() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    // (the test line's fee budget: 0.1 SOL per rolling 24 h)
    let mut c = Ctx::new(&RE_ON);
    let (a, b, wh) = ([0xA1u8; 32], [0xB1u8; 32], [0xE1u8; 32]);
    let mut z = c.token(90, 1000, &[]);
    let mut t1 = c.token(1, 1000, &[(a, 7.0), (b, 8.0)]);
    let d = t1.sell_tok(a, pct(7.0)); c.tx(1002, 5, vec![d], vec![]);
    clock(&mut c, &mut z, 1003, 1005);
    let w1 = c.p.armed[&t1.mint];
    let sp = |c: &Ctx, w: u64| c.p.sh.wins.lock().unwrap().iter().find(|s| s.id == w).map(|s| s.spend).unwrap();
    // the fee budget: paused; the window stays armed; a new re-arm window still arms
    c.p.test_fee(1_800_000_000 * S, 100_000_000);
    assert!(c.p.fee_paused());
    assert_eq!(send_gate(&c.p.sh, true, sp(&c, w1)), Some("paused_fee_budget"));
    let mut t2 = c.token(2, 1000, &[(a, 7.0), (b, 8.0)]);
    let d = t2.sell_tok(a, pct(7.0)); c.tx(1005, 6, vec![d], vec![]);
    clock(&mut c, &mut z, 1006, 1008);
    let w2 = c.p.armed[&t2.mint];
    assert!(c.p.rearm_w(w2) && c.p.wins[&w1].disarmed.is_none());
    assert_eq!(send_gate(&c.p.sh, true, sp(&c, w2)), Some("paused_fee_budget"));
    // a candidate pending and a window waiting (our T2 position on token 3), then the kill switch / profit lock: the engine's stop
    let mut t3 = c.token(3, 1000, &[(a, 7.0), (b, 8.0)]);
    let e = t3.buy_tok(wh, pct(6.0)); c.tx(1008, 7, vec![e], vec![]);
    let wt = c.p.armed[&t3.mint];
    let sg = c.attempt(wt, t3.mint, 1008);
    let _ = c.fill(&mut t3, sg, 1009, 4, 395_061_727);
    let d = t3.sell_tok(a, pct(7.0)); c.tx(1009, 6, vec![d], vec![]);
    clock(&mut c, &mut z, 1010, 1012);
    assert_eq!(c.rearm().defer.len(), 1);
    let mut t4 = c.token(4, 1000, &[(a, 7.0), (b, 8.0)]);
    let d = t4.sell_tok(a, pct(7.0)); c.tx(1012, 7, vec![d], vec![]);
    assert_eq!(c.rearm().cands.len(), 1);
    // (the engine's stop is stop("run_stopping"); "run_end" takes the same path without its Telegram line, which a parallel test traps)
    // (w1 met its QUIET stop at slot 1011, no trade since its arm; w2 is still armed)
    assert_eq!((c.p.wins[&w1].disarmed, c.p.wins[&w2].disarmed), (Some("quiet"), None));
    c.p.stop("run_end");
    c.drain();
    assert_eq!(c.p.wins[&w2].disarmed, Some("stopped"));
    assert_eq!(c.ev("presend_live_disarm").into_iter().find(|r| r["w"] == w2).unwrap()["kind"].as_str(), Some("rearm"));
    assert!(c.p.sh.wins.lock().unwrap().is_empty());
    assert!(c.rearm().cands.is_empty() && c.rearm().defer.is_empty());
    let sk: Vec<serde_json::Value> = c.ev("presend_live_skip").into_iter().filter(|r| r["kind"] == "rearm").collect();
    assert!(sk.iter().any(|r| r["why"] == "rearm_blocked_stopped" && r["mint"] == b58(&t4.mint)), "{sk:?}");
    assert!(sk.iter().any(|r| r["why"] == "rearm_blocked_position" && r["ended"] == "stopped" && r["mint"] == b58(&t3.mint)), "{sk:?}");
    assert_eq!(send_gate(&c.p.sh, true, 1), Some("stopped"), "the sender's gate: stopped (DIP_NO_FIRE gives the same)");
    // no new candidate after the stop
    let mut t5 = c.token(5, 1012, &[(a, 7.0), (b, 8.0)]);
    let d = t5.sell_tok(a, pct(7.0)); c.tx(1013, 5, vec![d], vec![]);
    clock(&mut c, &mut z, 1014, 1017);
    assert!(c.rearm().cands.is_empty() && !c.p.armed.contains_key(&t5.mint));
    let pid = c.p.pos[&t3.mint].pid;
    c.p.on_msg(PsMsg::Sold(t3.mint, pid, 1, sold(Some(1017), &["S"], 1)), &|_| false);
    drop(c);
}

/// TEST 11: the flags: off by default (no state, dip25's config record, status line and totals); the owner's line; every refusal
#[test]
fn dip26_rearm_flags_and_refusals() {
    let p0 = arbx::presend::Params::default();
    // OFF by default
    let c = cfg(&[]).unwrap().unwrap();
    assert_eq!(c.rearm, RearmCfg { on: false, spend: 400_000_000, gap: 20, stop: pq::QStop { n: 6, m: 2 }, r5_skip: false });
    assert!(c.json().get("rearm").is_none());
    let (mut p, _atx, _orx) = PsLive::for_test(c, USER);
    assert!(p.rm.is_none() && !p.status().contains("rearm:") && p.finish(10, None).get("rearm").is_none() && p.rearm_split().is_none());
    assert_eq!(cfg(&["--presend-live-rearm", "off"]).unwrap().unwrap().rearm.on, false);
    // the full line (with QUIET's arm rule for the R5 skip)
    let full = ["--presend-live-rearm", "on", "--presend-live-rearm-size-sol", "0.4", "--presend-live-rearm-gap-slots", "10", "--presend-live-rearm-quiet-stop", "4:3",
        "--presend-live-rearm-r5-skip", "on", "--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x.json"];
    let c = cfg(&full).unwrap().unwrap();
    assert_eq!(c.rearm, RearmCfg { on: true, spend: 400_000_000, gap: 10, stop: pq::QStop { n: 4, m: 3 }, r5_skip: true });
    assert_eq!((c.json()["rearm"]["gap"].as_u64(), c.json()["rearm"]["quiet_stop"].as_str(), c.json()["rearm"]["r5_skip"].as_bool()), (Some(10), Some("4:3"), Some(true)));
    assert!(check_flags(&args(&full)).is_ok(), "{:?}", check_flags(&args(&full)));
    let c = cfg(&RE_ON).unwrap().unwrap();
    assert_eq!(c.rearm, RearmCfg { on: true, spend: 400_000_000, gap: 20, stop: pq::QStop { n: 6, m: 2 }, r5_skip: false });
    assert_eq!(c.json()["rearm"]["max_age_slots"].as_u64(), Some(141));
    // the T2 config is the same with or without the re-arm
    let (t0, t1) = (cfg(&[]).unwrap().unwrap(), cfg(&full[..2]).unwrap().unwrap());
    assert_eq!((t0.spend, t0.k, t0.drop, t0.one_position, t0.quiet.clone()), (t1.spend, t1.k, t1.drop, t1.one_position, t1.quiet.clone()));
    // every re-arm flag needs --presend-live
    for f in RFLAGS {
        let e = Cfg::from_argv(&["snipe_engine", "--dip", "--presend-shadow", f, "on"].iter().map(|s| s.to_string()).collect::<Vec<_>>(), &p0, true, 1_000_000_000).unwrap_err().to_string();
        assert!(e.contains("needs --presend-live"), "{f}: {e}");
    }
    // a parameter needs --presend-live-rearm on
    for (f, v) in [("--presend-live-rearm-size-sol", "0.3"), ("--presend-live-rearm-gap-slots", "10"), ("--presend-live-rearm-quiet-stop", "6:2"), ("--presend-live-rearm-r5-skip", "off")] {
        for extra in [vec![f, v], vec!["--presend-live-rearm", "off", f, v]] {
            let e = cfg(&extra).unwrap_err().to_string();
            assert!(e.contains("needs --presend-live-rearm on"), "{f}: {e}");
        }
    }
    // bad values
    for bad in [&["--presend-live-rearm", "yes"][..], &["--presend-live-rearm"], &["--presend-live-rearm", "--presend-live-k", "4"],
                &["--presend-live-rearm", "on", "--presend-live-rearm-size-sol", "abc"], &["--presend-live-rearm", "on", "--presend-live-rearm-size-sol", "0"],
                &["--presend-live-rearm", "on", "--presend-live-rearm-size-sol", "2.5"], &["--presend-live-rearm", "on", "--presend-live-rearm-size-sol"],
                &["--presend-live-rearm", "on", "--presend-live-rearm-gap-slots", "0"], &["--presend-live-rearm", "on", "--presend-live-rearm-gap-slots", "61"],
                &["--presend-live-rearm", "on", "--presend-live-rearm-gap-slots", "x"], &["--presend-live-rearm", "on", "--presend-live-rearm-gap-slots", "1.5"],
                &["--presend-live-rearm", "on", "--presend-live-rearm-quiet-stop", "6"], &["--presend-live-rearm", "on", "--presend-live-rearm-quiet-stop", "0:2"],
                &["--presend-live-rearm", "on", "--presend-live-rearm-quiet-stop", "6:x"], &["--presend-live-rearm", "on", "--presend-live-rearm-quiet-stop", "31:2"],
                &["--presend-live-rearm", "on", "--presend-live-rearm-r5-skip", "maybe"],
                // R5 needs QUIET's arm rule; the re-arm needs one position
                &["--presend-live-rearm", "on", "--presend-live-rearm-r5-skip", "on"],
                &["--presend-live-rearm", "on", "--presend-live-one-position", "off"]] {
        assert!(cfg(bad).is_err(), "{bad:?} must be refused");
    }
    assert!(cfg(&["--presend-live-rearm", "on", "--presend-live-rearm-r5-skip", "on"]).unwrap_err().to_string().contains("needs --presend-live-quiet-skip on"));
    assert!(cfg(&["--presend-live-rearm", "on", "--presend-live-one-position", "off"]).unwrap_err().to_string().contains("--presend-live-one-position on"));
    // limits: 1 and 60 slots, (0, 2] SOL
    assert_eq!(cfg(&["--presend-live-rearm", "on", "--presend-live-rearm-gap-slots", "1"]).unwrap().unwrap().rearm.gap, 1);
    assert_eq!(cfg(&["--presend-live-rearm", "on", "--presend-live-rearm-gap-slots", "60"]).unwrap().unwrap().rearm.gap, 60);
    // the start-up line's re-arm part (appended to "DIP PRESEND LIVE ..." only when on): none of the words dipmon / the run report parse
    // from that line's earlier parts
    let d = rearm_desc(&cfg(&full).unwrap().unwrap());
    assert!(d.starts_with("REARM ON: after a single sell >= 6% of supply on a followed token <= 141 slots old (curve < 100 SOL)") && d.contains("slot dump+3+10")
        && d.contains("size 0.400 SOL") && d.contains("QUIET 4:3") && d.contains("R5 skip on"), "{d}");
    for k in ["attempts per slot", "SOL, limit", "price x", "a failed attempt", "routes ", "caps:", "exit ", "TP +", "SL -", "QUIET: skips", "failed-attempt fees", "fills"] {
        assert!(!d.contains(k), "{k}: {d}");
    }
    // the engine's start-up check: numbers, misspellings
    assert!(check_flags(&args(&["--presend-live-rearm", "on", "--presend-live-rearm-gap-slots", "x"])).is_err());
    assert!(check_flags(&args(&["--presend-live-rearm", "on", "--presend-live-rearm-size-sol", "x"])).is_err());
    let wrong = ["-", "-presend-live-rearm-gap"].concat();
    assert!(check_flags(&args(&["--presend-live-rearm", "on", &wrong, "4"])).is_err());
}

/// R5 (--presend-live-rearm-r5-skip on, with QUIET's arm rule): no window when all four QUIET arm signals hold for the LARGEST remaining
/// holder ("rearm_r5": no trade earlier in the check slot, no cohort wallet holding the token, < 2 follower bots on it, the holder's dumps
/// drew < fol buyers or none); one signal off: armed (its record carries the signals); the arm rule warming up: armed, "would_skip"
#[test]
fn dip26_rearm_r5_skip_largest_holder() {
    let mut c = Ctx::new(&["--presend-live-rearm", "on", "--presend-live-rearm-r5-skip", "on", "--presend-live-quiet-skip", "on", "--presend-live-fbots", "/unused-in-tests.json"]);
    let (a, b, w2, coh) = ([0xA1u8; 32], [0xB1u8; 32], [0xB2u8; 32], [0xC0u8; 32]);
    c.p.qt.as_mut().unwrap().coh = [coh].into_iter().collect();
    let mut z = c.token(90, 1000, &[]);
    // W2's earlier dump on token X drew 3 distinct buyers within 2 slots (its history: 3.0 >= 2.24)
    let mut tx_ = c.token(60, 1000, &[]);
    // (4.5%: below the 5% T2 whale, and its sell drops the price > 8%: a QUIET dump)
    let e = tx_.buy_tok(w2, pct(4.5)); c.tx(1001, 1, vec![e], vec![]);
    let e = tx_.sell_tok(w2, pct(4.5)); c.tx(1002, 1, vec![e.clone()], vec![]);
    assert!(arbx::presend_quiet::is_dump(e.buy, e.sol, e.tok, e.vsol, e.vtok));
    for (s, i, u) in [(1002u64, 2u64, [0x41u8; 32]), (1003, 1, [0x42; 32]), (1003, 2, [0x43; 32])] { let e = tx_.buy(u, S / 10); c.tx(s, i, vec![e], vec![]); }
    clock(&mut c, &mut z, 1004, 1010);
    // token 1: B is the largest holder, no history: all four -> rearm_r5
    let mut t1 = c.token(1, 1000, &[(a, 7.0), (b, 8.0)]);
    let d = t1.sell_tok(a, pct(7.0)); c.tx(1011, 5, vec![d], vec![]);
    // token 2: W2 (8%, the largest) and B (6.5%): W2's dumps drew 3 buyers -> armed
    let mut t2 = c.token(2, 1000, &[(a, 7.0), (w2, 8.0), (b, 6.5)]);
    let d = t2.sell_tok(a, pct(7.0)); c.tx(1011, 6, vec![d], vec![]);
    // token 3: a cohort wallet holds it -> armed
    let mut t3 = c.token(3, 1000, &[(a, 7.0), (b, 8.0), (coh, 0.5)]);
    let d = t3.sell_tok(a, pct(7.0)); c.tx(1011, 7, vec![d], vec![]);
    clock(&mut c, &mut z, 1012, 1014);
    let sk = c.ev("presend_live_skip").into_iter().find(|r| r["kind"] == "rearm").unwrap();
    assert_eq!((sk["why"].as_str(), sk["mint"].as_str()), (Some("rearm_r5"), Some(b58(&t1.mint).as_str())));
    assert_eq!((sk["r5"]["holder"].as_str(), sk["r5"]["all4"].as_bool(), sk["r5"]["since_last"].as_u64(), sk["r5"]["wh_fol"].as_f64()), (Some(b58(&b).as_str()), Some(true), Some(3), Some(-1.0)));
    assert_eq!(sk["r5"]["q"], serde_json::json!([true, true, true, true]));
    assert!(!c.p.armed.contains_key(&t1.mint));
    let arm2 = c.ev("presend_live_arm").into_iter().find(|r| r["mint"] == b58(&t2.mint)).unwrap();
    assert_eq!((arm2["r5"]["holder"].as_str(), arm2["r5"]["wh_fol"].as_f64(), arm2["r5"]["wh_dumps"].as_u64()), (Some(b58(&w2).as_str()), Some(3.0), Some(1)));
    assert_eq!(arm2["r5"]["q"], serde_json::json!([true, true, true, false]));
    assert_eq!(arm2["holders"].as_array().unwrap().len(), 2);
    let arm3 = c.ev("presend_live_arm").into_iter().find(|r| r["mint"] == b58(&t3.mint)).unwrap();
    assert_eq!(arm3["r5"]["q"], serde_json::json!([true, false, true, true]));
    // the QUIET arm rule warming up: all four -> armed, would_skip
    { let q = c.p.qt.as_mut().unwrap(); q.start_ns = arbx::feeds::clock::now_ns(); q.warm_ns = 60 * 60_000_000_000; }
    let mut t4 = c.token(4, 1000, &[(a, 7.0), (b, 8.0)]);
    let d = t4.sell_tok(a, pct(7.0)); c.tx(1014, 8, vec![d], vec![]);
    clock(&mut c, &mut z, 1015, 1017);
    let arm4 = c.ev("presend_live_arm").into_iter().find(|r| r["mint"] == b58(&t4.mint)).unwrap();
    assert_eq!((arm4["r5"]["all4"].as_bool(), arm4["r5"]["rule_on"].as_bool(), arm4["r5"]["would_skip"].as_bool()), (Some(true), Some(false), Some(true)));
    assert_eq!((c.rearm().st.skips.get("rearm_r5").copied(), c.rearm().st.r5_would), (Some(1), 1));
    // without the R5 flag no signals are computed
    let mut c = Ctx::new(&RE_ON);
    let mut z = c.token(90, 1000, &[]);
    let mut t1 = c.token(1, 1000, &[(a, 7.0), (b, 8.0)]);
    let d = t1.sell_tok(a, pct(7.0)); c.tx(1002, 5, vec![d], vec![]);
    clock(&mut c, &mut z, 1003, 1005);
    assert!(c.ev("presend_live_arm").pop().unwrap().get("r5").is_none());
}

/// one pass of the parity tapes with attempts for the T2 windows only (every 7th fills), every chain answer given at the end: the T2
/// records (no "kind"), wall clock and window ids removed, sorted; the totals without the re-arm's; the re-arm windows armed
fn t2_pass(extra: &[&str]) -> Option<(Vec<String>, serde_json::Value, u64)> {
    let (txs, launches) = gtapes(312)?;
    let cfg = Cfg::from_argv(&gargs(extra), &arbx::presend::Params::default(), true, 1_000_000_000).unwrap().unwrap();
    let (fail_fee, spend) = (cfg.fail_fee(), cfg.spend);
    let (mut p, atx, orx) = PsLive::for_test(cfg, USER);
    let launch_of = |m: &Pk| launches.get(m).cloned();
    let roles = pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) };
    let err6042 = [8u8, 0, 0, 0, 5, 25, 0, 0, 0, 0x9a, 0x17, 0, 0];
    let (mut seq, mut slot_now, mut held, mut n_re) = (0u64, 0u64, Vec::<Cmd>::new(), 0u64);
    for (s, idx, sig, x) in &txs {
        slot_now = slot_now.max(*s);
        let a = arbx::feeds::Arrival { feed: 0, slot: *s, t_rx: *s * 1_000_000 + *idx, t_decoded: *s * 1_000_000 + *idx, executed: Some(true),
            tx: arbx::tx::Tx { sig: *sig, keys: vec![[3u8; 32]], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        p.on_arrival(&a, slot_now);
        p.on_exec(&a, x, slot_now, launch_of, &|_| false, None);
        held.extend(p.take_cmds());
        let mut armed: Vec<(Pk, u64)> = p.armed.iter().map(|(m, w)| (*m, *w)).filter(|(_, w)| !p.rearm_w(*w)).collect();
        armed.sort_by_key(|x| x.1);
        for (m, w) in armed {
            seq += 1;
            let mut sg = [0u8; 64]; sg[..8].copy_from_slice(&seq.to_be_bytes()); sg[8] = 0xD6; sg[9] = 0x77;
            atx.send(Att { w, n: 1, mint: m, sig: sg, tag: pl::PS_TAG | (0xD26B << 32) | seq, path: "helius-ps".into(), client: "JitoLabs".into(), slot: *s, deadline: *s + 1,
                lim: 1.0, min_out: 1, p_sign: 1.0, sign_pos: (*s, *idx as u32, 0), t_send: *s * 1_000_000, roles, tip: 200_000, wst: "written", ob6: 0.0, grd: pslive::Grd::default(), fa: None, bd: None, x46: Default::default() }).unwrap();
            if seq % 7 == 0 {
                let (wv, wt) = p.sh.wins.lock().unwrap().iter().find(|x| x.id == w).map(|x| (x.vsol, x.vtok)).unwrap();
                let tok = pl::buy_out(wv, wt, spend, 0.0125);
                let sol = (spend as f64 / 1.0125) as u64;
                let ev = TradeEvent { mint: m, sol, tok, buy: true, user: USER, vsol: wv + sol, vtok: wt - tok, fbps: 95, cbps: 30 };
                let xf = arbx::feeds::ExecInfo { index: 50, fee: 5_090, ok: true, trades: vec![ev], creates: Vec::new(), mayhem: false };
                let af = arbx::feeds::Arrival { feed: 0, slot: *s, t_rx: *s * 1_000_000 + 40_000_000, t_decoded: *s * 1_000_000 + 40_000_000, executed: Some(true),
                    tx: arbx::tx::Tx { sig: sg, keys: vec![USER], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(xf.clone())) };
                p.on_arrival(&af, slot_now);
                p.on_exec(&af, &xf, slot_now, launch_of, &|_| false, None);
            } else {
                arbx::feeds::own_fail_note(&sg, Some(&USER[..]), *s, 60, fail_fee, &err6042);
                let af = arbx::feeds::Arrival { feed: 0, slot: *s, t_rx: *s * 1_000_000 + 30_000_000, t_decoded: *s * 1_000_000 + 30_000_000, executed: Some(false),
                    tx: arbx::tx::Tx { sig: sg, keys: vec![USER], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: None };
                p.on_arrival(&af, slot_now);
            }
            held.extend(p.take_cmds());
        }
        n_re = n_re.max(p.rm.as_ref().map_or(0, |r| r.st.windows));
    }
    let end = slot_now + 50;
    p.tick(end, None);
    held.extend(p.take_cmds());
    for round in 0..5u64 {
        for c in std::mem::take(&mut held) {
            match c {
                Cmd::Sell { mint, pid, round: r, known, .. } => p.on_msg(PsMsg::Sold(mint, pid, r, SellOut { sold_at: Some(end + round), sigs: vec![(format!("TSELL{pid}r{r}"), true, 1_200_000)],
                    last: None, attempts: 1, last_qty: (known.unwrap_or(0), true), first_send_us: None }), &|_| false),
                Cmd::Read { mint, min_slot, why, n } => p.on_msg(PsMsg::Read(mint, why, min_slot, n, crate::Tok::Amount(0, end + round)), &|_| false),
                Cmd::Close { mint } => p.on_msg(PsMsg::Closed(mint, "TCLOSE".into(), Some(end + round), String::new()), &|_| false),
                _ => {}
            }
            held.extend(p.take_cmds());
        }
        p.tick(end + 10 * (round + 1), None);
        held.extend(p.take_cmds());
    }
    let mut fin = p.finish(end + 100, None);
    if let Some(o) = fin.as_object_mut() { o.remove("rearm"); o.remove("acks"); }
    if let Some(o) = fin["cfg"].as_object_mut() { o.remove("rearm"); }
    // the T2 records: window ids (they shift by the re-arm's), wall clock and the landing records' tape-derived fields (a re-arm window's
    // tape can hold earlier trades of the token) removed
    fn strip(v: &mut serde_json::Value) {
        match v {
            serde_json::Value::Object(o) => {
                for k in ["w", "t", "armed_ms", "held_s", "ack", "ack_ms", "x", "d", "between", "after", "n_between", "instant_before_us", "instant_after_us", "ahead_of_instant",
                          "ms_after_x_rx", "ms_after_x_a", "ms_after_x_first", "ms_after_x_poh", "ms_after_d_rx", "ms_after_d_a", "ms_after_d_first", "ms_after_d_poh"] { o.remove(k); }
                for x in o.values_mut() { strip(x); }
            }
            serde_json::Value::Array(a) => { for x in a.iter_mut() { strip(x); } }
            _ => {}
        }
    }
    let mut recs: Vec<String> = orx.try_iter().filter_map(|o| o.rec()).filter(|r| r.get("kind").is_none()).map(|mut r| { strip(&mut r); r.to_string() }).collect();
    recs.sort();
    Some((recs, gstrip(fin), n_re))
}

/// the re-arm ON leaves the T2 side as it was: on the parity tapes (T2 attempts, fills, exits, sells, reads, closes) every T2 record and
/// the T2 totals are the same with --presend-live-rearm on as off (window ids aside: the re-arm's windows take ids too), while re-arm
/// windows arm (no attempts for them here: a re-arm fill would hold the one position and change what T2 can do, by design)
#[test]
fn dip26_rearm_on_leaves_t2_unchanged() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let Some((r_off, f_off, n0)) = t2_pass(&[]) else { eprintln!("presend_parity.json missing: skipped"); return };
    let (r_on, f_on, n1) = t2_pass(&RE_ON).unwrap();
    eprintln!("dip26 T2 unchanged with the re-arm on: {} T2 records; re-arm windows armed {n1}", r_off.len());
    assert_eq!(n0, 0);
    assert!(n1 >= 5, "re-arm windows armed on the parity tapes: {n1}");
    assert!(r_off.len() > 1_000);
    assert_eq!(r_off.len(), r_on.len());
    for (a, b) in r_off.iter().zip(&r_on) { assert_eq!(a, b); }
    assert_eq!(f_off, f_on);
}

/// LIVE vs PAPER on a RECORDED HOUR (by hand; the 24/7 recording):
///   DIP26_HOUR=<run dir>[:<from unix s>] [DIP26_OUT=DIR] cargo test --release --bin snipe_engine dip26_recorded_hour -- --ignored --nocapture
/// The hour's executed txs (chain order) through THE PROBE (re-arm on, AMS run 37's T2 options: 6% whale, TP 20%, k 8, QUIET stop 5:2,
/// min token age 2; no attempt is sent: no fill, no position) and, side by side, the OBSERVATORY's paper re-arm (src/obs/rearm.rs: its
/// own token book and slot clock, the probe's live records fed to it at once, as its tailer would). The live 30 ms stops (T2 and re-arm)
/// are emulated on the FEED clock (a replay's wall clock runs far faster than its feed clock). Per dump (its signature): the verdict
/// (a window / no holder / a T2 window armed), the holders at the check, the arm slot and last slot, the end; the agreement printed.
#[test]
#[ignore]
fn dip26_recorded_hour_live_vs_paper() {
    let spec = std::env::var("DIP26_HOUR").expect("DIP26_HOUR=<run dir>[:<from unix s>]");
    let (run, from) = match spec.split_once(':') { Some((r, f)) => (r.to_string(), Some(f.parse::<i64>().unwrap())), None => (spec.clone(), None) };
    let runp = std::path::PathBuf::from(&run);
    let chunks = arbx::presend_quiet::chunks(&runp, 0, u64::MAX);
    assert!(!chunks.is_empty(), "no chunks in {run}");
    let from = from.unwrap_or(chunks[chunks.len() / 2].0 as i64);
    let to = from + 3600;
    let ps = arbx::presend::Params { whale_pct: 6.0, tp: 0.20, ..Default::default() };
    let c = Cfg::from_argv(&args(&["--presend-live-k", "8", "--presend-live-quiet-stop", "5:2", "--presend-live-min-age-slots", "2", "--presend-live-rearm", "on",
        "--presend-live-size-sol", "0.65"]), &ps, true, 1_000_000_000).unwrap().unwrap();
    let (mut p, _atx, orx) = PsLive::for_test(c, USER);
    // the observatory's re-arm, driven as its thread drives it (Hub::on_tx / on_slot / housekeeping)
    let ocfg = arbx::obs::Cfg { rearm: true, user: USER, rate_cap: 40, k: 8, drop: 0.12, quiet_fol: 2.24, ..Default::default() };
    let mut book = arbx::obs::book::Book::new(USER);
    let mut clock = arbx::obs::Clock::default();
    let mut live = arbx::obs::Live::default();
    let mut paper = arbx::obs::rearm::Rearm::new(&ocfg);
    let mut orecs: Vec<(usize, serde_json::Value)> = Vec::new();
    let mut lrecs: Vec<serde_json::Value> = Vec::new();
    let mut rec = arbx::presend_quiet::Recording::open(&[runp.clone()], (from - 600) as u64, to as u64, from, to, true, true);
    let (mut slot_now, mut n, mut t_last) = (0u64, 0u64, 0u64);
    let t_of = |bt: i64, i: u32| bt as u64 * S + i as u64 * 100_000;
    // the 30 ms stops on the feed clock: window -> the feed time its stop was first seen
    let mut stop_t: HashMap<u64, u64> = HashMap::new();
    let t0 = Instant::now();
    while let Some(t) = rec.next().unwrap() {
        slot_now = slot_now.max(t.s);
        let t_rx = t_of(t.bt, t.i);
        t_last = t_last.max(t_rx);
        let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&t.s.to_be_bytes()); sig[8..12].copy_from_slice(&t.i.to_be_bytes()); sig[12] = 0xD6;
        // the paper first (its own clock and book), then the probe; then the probe's records into the paper's live state
        if let Some(prev) = clock.see(t.s, t_rx) { paper.on_slot(prev, t.s, t_rx, &book, &clock, None, &ocfg, &live, &mut orecs); }
        for cr in &t.creates { book.create(cr.mint, t.s, t_rx, cr.creator, cr.user, t.mayhem); }
        for (j, e) in t.trades.iter().enumerate() {
            let tr = arbx::obs::book::Tr { mint: e.mint, s: t.s, i: t.i, j: j as u32, t: t_rx, sig, user: e.user, buy: e.buy, sol: e.sol, tok: e.tok, vsol: e.vsol, vtok: e.vtok,
                fbps: e.fbps.min(u16::MAX as u64) as u16, cbps: e.cbps.min(u16::MAX as u64) as u16 };
            let ctx = book.apply(&tr, false);
            if let Some(tok) = book.get(&e.mint) { paper.on_trade(tok, &tr, &ctx, &clock, &mut orecs); }
        }
        let x = arbx::feeds::ExecInfo { index: t.i as u64, fee: 5_000, ok: true, trades: t.trades, creates: t.creates, mayhem: t.mayhem };
        let a = arbx::feeds::Arrival { feed: 0, slot: t.s, t_rx, t_decoded: t_rx, executed: Some(true), tx: arbx::tx::Tx { sig, keys: vec![[3u8; 32]], ..Default::default() },
            poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        p.on_arrival(&a, slot_now);
        p.on_exec(&a, &x, slot_now, |m: &Pk| Some(snipe_build::launch_from_target(*m, *m)), &|_| false, None);
        // the 30 ms stops on the feed clock
        let mut due = false;
        let ids: Vec<u64> = p.wins.iter().filter(|(_, w)| w.disarmed.is_none() && w.stop_at.is_some()).map(|(k, _)| *k).collect();
        for id in ids {
            let first = *stop_t.entry(id).or_insert(t_rx);
            let w = p.wins.get_mut(&id).unwrap();
            if t_rx >= first + WHALE_SELL_MS * 1_000_000 { w.stop_at = Some(Instant::now() - Duration::from_millis(1)); due = true; } else { w.stop_at = Some(Instant::now() + Duration::from_secs(3600)); }
        }
        if due { p.tick(slot_now, None); }
        for o in orx.try_iter() {
            if let Out::Rec(v) = o {
                if let Some(e) = arbx::obs::parse_live(v.to_string().as_bytes()) { live.on(&e, clock.max_t); paper.on_live(&e); }
                lrecs.push(v);
            }
        }
        paper.tick(clock.max_t, false, &book, &live, &ocfg, &mut orecs);
        n += 1;
    }
    let _ = p.finish(slot_now + 50, None);
    lrecs.extend(orx.try_iter().filter_map(|o| o.rec()));
    paper.finish(t_last + 10 * S, &book, &live, &ocfg, &mut orecs);
    let secs = t0.elapsed().as_secs_f64();
    // per dump: the paper's verdict / holders / arm / end, the live one's
    let mut pv: HashMap<String, serde_json::Value> = HashMap::new();
    let mut pw: HashMap<String, serde_json::Value> = HashMap::new();
    for (_, r) in &orecs {
        let k = r["dump"]["sig"].as_str().unwrap_or("").to_string();
        match r["ev"].as_str() { Some("rearm_cand") => { pv.insert(k, r.clone()); } Some("rearm_window") => { pw.insert(k, r.clone()); } _ => {} }
    }
    let mut lv: HashMap<String, (String, serde_json::Value)> = HashMap::new();
    let mut lw_end: HashMap<u64, String> = HashMap::new();
    for r in lrecs.iter().filter(|r| r["kind"] == "rearm") {
        let k = r["dump"]["sig"].as_str().unwrap_or("").to_string();
        match r["ev"].as_str() {
            Some("presend_live_arm") => { lv.insert(k, ("window".into(), r.clone())); }
            Some("presend_live_skip") => {
                let why = r["why"].as_str().unwrap_or("?");
                if why == "rearm_age" || why == "rearm_untradeable" { continue; }
                lv.insert(k, (why.trim_start_matches("rearm_").to_string(), r.clone()));
            }
            Some("presend_live_disarm") => { lw_end.insert(r["w"].as_u64().unwrap_or(0), r["why"].as_str().unwrap_or("?").to_string()); }
            _ => {}
        }
    }
    let (mut both, mut only_p, mut only_l, mut same_v, mut same_h, mut same_arm, mut same_end, mut n_win, mut ends_cmp) = (0, 0, 0, 0, 0, 0, 0, 0, 0);
    let mut diffs: Vec<String> = Vec::new();
    let mut end_pairs: std::collections::BTreeMap<(String, String), u32> = Default::default();
    for (k, c) in &pv {
        let verdict = c["verdict"].as_str().unwrap_or("?");
        if verdict == "run_end" { continue; }
        let Some((lverd, lr)) = lv.get(k) else { only_p += 1; diffs.push(format!("paper only: {k} {verdict}")); continue };
        both += 1;
        let lverd = if lverd == "blocked_live_armed" { "blocked_live_armed" } else { lverd.as_str() };
        if verdict == lverd { same_v += 1; } else { diffs.push(format!("verdict {k}: paper {verdict} live {lverd}")); }
        if verdict == "window" && lverd == "window" {
            n_win += 1;
            let w = pw.get(k);
            let ph: Vec<(String, f64)> = w.map(|w| w["holders"].as_array().unwrap().iter().map(|h| (h["w"].as_str().unwrap().to_string(), (h["pct"].as_f64().unwrap() * 1e6).round())).collect()).unwrap_or_default();
            let lh: Vec<(String, f64)> = lr["holders"].as_array().unwrap().iter().map(|h| (h["w"].as_str().unwrap().to_string(), (h["pct"].as_f64().unwrap() * 1e6).round())).collect();
            if ph == lh { same_h += 1; } else { diffs.push(format!("holders {k}: paper {ph:?} live {lh:?}")); }
            let (pa, pe) = w.map(|w| (w["arm"]["slot"].as_u64(), w["en_slot"].as_u64())).unwrap_or((None, None));
            if (pa, pe) == (lr["arm_slot"].as_u64(), lr["en_slot"].as_u64()) { same_arm += 1; } else { diffs.push(format!("arm {k}: paper {pa:?}/{pe:?} live {:?}/{:?}", lr["arm_slot"], lr["en_slot"])); }
            if let (Some(w), Some(le)) = (w, lr["w"].as_u64().and_then(|id| lw_end.get(&id))) {
                ends_cmp += 1;
                let pe = w["end"]["why"].as_str().unwrap_or("?").to_string();
                if pe == *le { same_end += 1; }
                *end_pairs.entry((pe, le.clone())).or_default() += 1;
            }
        }
    }
    for (k, (lverd, _)) in &lv { if !pv.contains_key(k) { only_l += 1; diffs.push(format!("live only: {k} {lverd}")); } }
    let pct = |a: usize, b: usize| if b == 0 { 100.0 } else { a as f64 * 100.0 / b as f64 };
    eprintln!("dip26 recorded hour {from}..{to}: {n} txs in {secs:.1} s | paper candidates {} (windows {}), live {} (windows {}) | matched {both}, paper only {only_p}, live only {only_l}",
        pv.len(), pw.len(), lv.len(), lv.values().filter(|x| x.0 == "window").count());
    eprintln!("  verdict agree {same_v}/{both} ({:.1}%) | both windows {n_win}: holders agree {same_h} ({:.1}%), arm + last slot agree {same_arm} ({:.1}%), end agree {same_end}/{ends_cmp} ({:.1}%)",
        pct(same_v, both), pct(same_h, n_win), pct(same_arm, n_win), pct(same_end, ends_cmp));
    eprintln!("  ends (paper, live): {end_pairs:?}");
    for d in diffs.iter().take(30) { eprintln!("  {d}"); }
    if let Ok(o) = std::env::var("DIP26_OUT") {
        std::fs::write(format!("{o}/hour_live_rearm.jsonl"), lrecs.iter().filter(|r| r["kind"] == "rearm").map(|r| r.to_string() + "\n").collect::<String>()).unwrap();
        std::fs::write(format!("{o}/hour_paper_rearm.jsonl"), orecs.iter().filter(|r| r.1["ev"] == "rearm_cand" || r.1["ev"] == "rearm_window").map(|r| r.1.to_string() + "\n").collect::<String>()).unwrap();
        std::fs::write(format!("{o}/hour_diffs.txt"), diffs.join("\n")).unwrap();
    }
    assert!(both > 0 && pct(same_v, both) >= 95.0 && pct(same_h, n_win) >= 95.0 && pct(same_arm, n_win) >= 95.0, "live and paper must agree");
}

// ---- dip27: the lone-whale skip and the log-only annotations ----------------------------------------------------------------

impl Ctx {
    /// dip27: an attempt as the sender builds it: its window's curve price at signing (p_sign) and largest other holder (ob6)
    fn attempt_at(&mut self, w: u64, mint: Pk, slot: u64) -> [u8; 64] {
        let (p_sign, ob6) = { let g = self.p.sh.wins.lock().unwrap(); g.iter().find(|s| s.id == w).map(|s| (s.vsol as f64 / s.vtok.max(1) as f64, s.ob6)).unwrap() };
        self.seq += 1;
        let mut sg = [0u8; 64]; sg[..8].copy_from_slice(&self.seq.to_be_bytes()); sg[8] = 0xD7; sg[9] = 0xA7;
        self.atx.send(Att { w, n: self.seq as u32, mint, sig: sg, tag: pl::PS_TAG | (0xD27A << 32) | self.seq, path: "helius-ps".into(), client: "JitoLabs".into(), slot, deadline: slot + 1,
            lim: p_sign * 0.88, min_out: 1, p_sign, sign_pos: (slot, 0, 0), t_send: slot * 1_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) },
            tip: 200_000, wst: "written", ob6, grd: pslive::Grd::default(), fa: None, bd: None, x46: Default::default() }).unwrap();
        self.p.drain_atts();
        sg
    }
}

/// dip27 TEST A: --presend-live-lone-whale-slots 50: a whale whose buy is the token's only buy in its last 50 slots (the trigger's slot
/// and the 49 before it) is skipped "lone_whale" (its record carries "nb": 1, a line says so); another buyer inside the window: armed
/// ("nb": 2); one at the window's edge -1: skipped; our own buys never count; flag off: armed, no "nb" (dip26's records)
#[test]
fn dip27_lone_whale_skip() {
    let w = [0xA1u8; 32];
    // (lone whale on, the other buyer's slot (None: none), skipped)
    for (lw, other, skip) in [(true, None, true), (true, Some(160u64), false), (true, Some(150), true), (true, Some(151), false), (false, None, false)] {
        let mut c = Ctx::new(if lw { &["--presend-live-lone-whale-slots", "50"][..] } else { &[][..] });
        let mut tk = c.token(0x27, 100, &[]);
        if let Some(s) = other { let e = tk.buy([0xB2; 32], S / 10); c.tx(s, 4, vec![e], vec![]); }
        // our own buy inside the window: never a buyer of the count
        let e = tk.buy(USER, S / 10); c.tx(170, 4, vec![e], vec![]);
        let e = tk.buy_tok(w, pct(7.0)); c.tx(200, 5, vec![e], vec![]);
        assert_eq!(c.p.st.triggers, 1, "{lw} {other:?}");
        let (arms, skips) = (c.ev("presend_live_arm"), c.ev("presend_live_skip"));
        if skip {
            assert!(arms.is_empty(), "{other:?}: skipped");
            assert_eq!((skips.len(), skips[0]["why"].as_str(), skips[0]["nb"].as_u64()), (1, Some("lone_whale"), Some(1)), "{other:?}");
            assert_eq!(c.p.st.skips.get("lone_whale"), Some(&1));
            assert!(c.lines.iter().any(|l| l.starts_with(&format!("  PRESEND LIVE LONE-WHALE SKIP {} whale {}", b58(&tk.mint), &b58(&w)[..8]))
                && l.ends_with("buyers in the last 50 slots: 1")), "{:?}", c.lines);
        } else {
            assert!(skips.is_empty() && arms.len() == 1, "{lw} {other:?}: armed");
            assert_eq!(arms[0]["nb"].as_u64(), if lw { Some(2) } else { None }, "{lw} {other:?}");
            assert!(!c.lines.iter().any(|l| l.contains("LONE-WHALE")));
        }
        assert!(arms.iter().chain(skips.iter()).all(|r| r.get("ann").is_none()), "annotations off");
    }
    // decided LAST: a create-slot trigger stays "create_slot" (the window of the age-0 whale holds only the creator and the whale)
    let mut c = Ctx::new(&["--presend-live-lone-whale-slots", "50"]);
    let mut tk = c.token(0x29, 300, &[]);
    let mut e = tk.buy_tok([0xA2; 32], pct(7.0));
    e.user = [0xA2; 32];
    // the create's signer buying in its own create slot is not a T2 trigger; a later wallet at age 0 is: the create slot's own trade
    c.tx(300, 9, vec![e], vec![]);
    assert!(c.ev("presend_live_skip").iter().all(|r| r["why"] != "lone_whale"), "{:?}", c.ev("presend_live_skip"));
}

/// dip27 TEST B: --presend-live-ann on, T2: the arm record's "ann" (the 50-slot buyers, the creator and its holding), the window's
/// largest other holder (create-slot insider H, 8%), the attempt's ob6 at signing, the fill record's "ann" (ob6, depth ~0, ctx85, the
/// holders >= 2% just before our buy with their ages and clocks), the status line's ANN part; off: none of them
#[test]
fn dip27_annotations_t2_fill() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let (h, w, x) = ([0xB1u8; 32], [0xA1u8; 32], [0x33u8; 32]);
    for ann in [true, false] {
        let mut c = Ctx::new(if ann { &["--presend-live-ann", "on"][..] } else { &[][..] });
        let mut tk = c.token(0x28, 100, &[(h, 8.0)]);
        for s in 190..=192 { let e = tk.buy(x, S / 10); c.tx(s, 4, vec![e], vec![]); }
        let e = tk.buy_tok(w, pct(7.0)); c.tx(200, 5, vec![e], vec![]);
        let arm = c.ev("presend_live_arm");
        assert_eq!(arm.len(), 1, "armed");
        let id = arm[0]["w"].as_u64().unwrap();
        let ob6 = c.p.sh.wins.lock().unwrap().iter().find(|s| s.id == id).unwrap().ob6;
        if ann {
            let a = &arm[0]["ann"];
            assert_eq!((a["nb50"].as_u64(), a["creator"].as_str()), (Some(2), Some(b58(&CREATOR).as_str())), "{a}");
            assert!(a["cr_pct"].as_f64().unwrap() > 1.0, "{a}");
            assert!((ob6 - 8.0).abs() < 0.01, "H's 8% (the whale's and ours left out): {ob6}");
        } else {
            assert!(arm[0].get("ann").is_none() && ob6 == 0.0);
        }
        let sig = c.attempt_at(id, tk.mint, 201);
        c.fill(&mut tk, sig, 202, 3, S / 2);
        let f = c.ev("presend_live_fill");
        assert_eq!(f.len(), 1);
        if ann {
            let a = &f[0]["ann"];
            assert!((a["ob6"].as_f64().unwrap() - 8.0).abs() < 0.01 && a["depth"].as_f64().unwrap().abs() < 1e-9 && a["ctx85"] == true, "{a}");
            let hs = a["holders"].as_array().unwrap();
            assert_eq!(hs.iter().map(|x| x["w"].as_str().unwrap().to_string()).collect::<Vec<_>>(), vec![b58(&h), b58(&w)], "H, then the whale; not us, not the small ones");
            assert_eq!((hs[0]["age"].as_u64(), hs[1]["age"].as_u64(), hs[1]["n"].as_u64()), (Some(102), Some(2), Some(0)));
            assert!((hs[0]["pct"].as_f64().unwrap() - 8.0).abs() < 0.01);
            // dip30: the group-risk rule's fields (no holder has a risky clock here: not flagged, 0%)
            assert!(a["grp_block"] == false && a["grp_pct"].as_f64() == Some(0.0), "{a}");
            assert!(c.p.status().contains(" | ANN (log-only): ctx85 would-skip fills 1 | st-safe would-block fills 0 | group-risk would-block fills 0 | landing-guard would-fail fills 0 | hold clocks "), "{}", c.p.status());
        } else {
            assert!(f[0].get("ann").is_none());
            assert!(!c.p.status().contains("ANN"));
        }
    }
}

/// dip27 TEST C: --presend-live-ann on, re-arm: its arm record's "ann" and its window's ob6 (B's 8%: the dumper A sold out, ours left out)
#[test]
fn dip27_annotations_rearm_arm() {
    for ann in [true, false] {
        let mut flags = vec!["--presend-live-rearm", "on", "--presend-live-rearm-size-sol", "0.3"];
        if ann { flags.extend(["--presend-live-ann", "on"]); }
        let mut c = Ctx::new(&flags);
        let (a, b, x) = ([0xA1u8; 32], [0xB1u8; 32], [0x33u8; 32]);
        let mut tk = c.token(1, 1000, &[(a, 7.0), (b, 8.0)]);
        let mut z = c.token(90, 1000, &[]);
        for s in 1001..=1004 { let e = tk.buy(x, S / 10); c.tx(s, 5, vec![e], vec![]); }
        let d = tk.sell_tok(a, pct(7.0));
        c.tx(1005, 5, vec![d], vec![]);
        clock(&mut c, &mut z, 1006, 1008);
        let w = *c.p.armed.get(&tk.mint).expect("armed at dump + 3");
        let arm = c.ev("presend_live_arm").pop().unwrap();
        assert_eq!(arm["kind"].as_str(), Some("rearm"));
        let ob6 = c.p.sh.wins.lock().unwrap().iter().find(|s| s.id == w).unwrap().ob6;
        if ann {
            assert_eq!((arm["ann"]["creator"].as_str(), arm["ann"]["nb50"].as_u64()), (Some(b58(&CREATOR).as_str()), Some(4)), "{}", arm["ann"]);
            assert!((ob6 - 8.0).abs() < 0.01, "{ob6}");
        } else {
            assert!(arm.get("ann").is_none() && ob6 == 0.0);
        }
    }
}

/// dip27 on the REAL tapes (presend_parity.json, 312 tokens), golden pass 2's options (AMS run 37's) with and without the lone-whale skip
/// at 50 + the annotations: both run to the end; every lone-whale skip has "nb" <= 1, every T2 arm with the skip on "nb" >= 2 and an
/// "ann"; every fill with the annotations an "ann" (its holders listed, depth, ctx85); no more T2 arms than without the skip
#[test]
fn dip27_real_tapes_flags_on() {
    let base = vec!["--presend-live-k", "8", "--presend-live-size-sol", "0.696", "--presend-live-quiet-stop", "5:2", "--presend-live-quiet-skip", "on", "--presend-live-fbots",
        "/unused-in-tests.json", "--presend-live-quiet-fol", "4.0", "--presend-live-quiet-v2-log", "--presend-live-min-age-slots", "2"];
    let ps = || arbx::presend::Params { whale_pct: 6.0, tp: 0.20, ..Default::default() };
    let Some(off) = golden_pass(4, &base, ps(), 5) else { eprintln!("presend_parity.json missing: skipped"); return };
    let mut on_flags = base.clone();
    on_flags.extend(["--presend-live-lone-whale-slots", "50", "--presend-live-ann", "on"]);
    let on = golden_pass(5, &on_flags, ps(), 5).unwrap();
    let recs = |v: &Vec<String>| v.iter().filter_map(|l| l.strip_prefix("R ")).map(|x| serde_json::from_str::<serde_json::Value>(x).unwrap()).collect::<Vec<_>>();
    let (ro, rn) = (recs(&off), recs(&on));
    let t2_arms = |r: &[serde_json::Value]| r.iter().filter(|x| x["ev"] == "presend_live_arm" && x.get("kind").is_none()).cloned().collect::<Vec<_>>();
    let (ao, an) = (t2_arms(&ro), t2_arms(&rn));
    let lw: Vec<&serde_json::Value> = rn.iter().filter(|x| x["ev"] == "presend_live_skip" && x["why"] == "lone_whale").collect();
    let fills: Vec<&serde_json::Value> = rn.iter().filter(|x| x["ev"] == "presend_live_fill").collect();
    let ctx = fills.iter().filter(|f| f["ann"]["ctx85"] == true).count();
    eprintln!("dip27 real tapes: T2 arms {} -> {} with the skip, lone-whale skips {}, fills {} (ctx85 {}), holders listed {}", ao.len(), an.len(), lw.len(), fills.len(), ctx,
        fills.iter().map(|f| f["ann"]["holders"].as_array().map_or(0, |a| a.len())).sum::<usize>());
    assert!(an.len() <= ao.len());
    assert!(lw.iter().all(|r| r["nb"].as_u64().is_some_and(|n| n <= 1) && r["ann"]["nb50"].as_u64().is_some()), "{lw:?}");
    assert!(an.iter().all(|r| r["nb"].as_u64().is_some_and(|n| n >= 2) && r["ann"]["creator"].is_string()), "every arm annotated");
    assert!(!fills.is_empty() && fills.iter().all(|f| f["ann"]["holders"].is_array() && f["ann"]["depth"].is_number() && f["ann"]["ctx85"].is_boolean()));
    assert!(ao.iter().chain(ro.iter().filter(|x| x["ev"] == "presend_live_fill")).all(|r| r.get("ann").is_none() && r.get("nb").is_none()), "off: none");
}

// ---- dip28: the deeper limit and the safe sell-timer log ---------------------------------------------------------------------

/// dip28 TEST A: --presend-live-deep-drop 0.15: a T2 window whose token has another >= 6% holder (create-slot insider H, 8%) signs its
/// attempts with the deeper drop; once H sells below 6% the normal drop again; the fill record says whether its try was deep; off:
/// the window keeps no other-holder figure and every attempt uses the normal drop (dip27)
#[test]
fn dip28_deep_limit_drop_by_other_holder() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let (h, w, x) = ([0xB1u8; 32], [0xA1u8; 32], [0x33u8; 32]);
    for deep in [true, false] {
        let mut c = Ctx::new(if deep { &["--presend-live-deep-drop", "0.15"][..] } else { &[][..] });
        let mut tk = c.token(0x30, 100, &[(h, 8.0)]);
        for s in 190..=192 { let e = tk.buy(x, S / 10); c.tx(s, 4, vec![e], vec![]); }
        let e = tk.buy_tok(w, pct(7.0)); c.tx(200, 5, vec![e], vec![]);
        let id = c.ev("presend_live_arm")[0]["w"].as_u64().unwrap();
        let drop_now = |c: &Ctx| { let g = c.p.sh.wins.lock().unwrap(); let sw = g.iter().find(|s| s.id == id).unwrap(); (att_drop(sw, &c.p.cfg), sw.ob6) };
        let (d0, o0) = drop_now(&c);
        if deep { assert!((d0 - 0.15).abs() < 1e-12 && (o0 - 8.0).abs() < 0.01, "{d0} {o0}"); } else { assert!((d0 - c.p.cfg.drop).abs() < 1e-12 && o0 == 0.0); }
        // H sells most of its bag: below 6% -> the normal drop for the next attempts
        let e = tk.sell_tok(h, pct(5.0)); c.tx(201, 2, vec![e], vec![]);
        let (d1, o1) = drop_now(&c);
        assert!((d1 - c.p.cfg.drop).abs() < 1e-12, "{deep}: {d1} {o1}");
        if deep { assert!(o1 < 6.0 && o1 > 2.9, "{o1}"); }
        // a fill: its record says deep (an attempt signed while H still held 8%)
        let sig = { let g = c.p.sh.wins.lock().unwrap(); drop(g); c.attempt_at(id, tk.mint, 201) };
        c.fill(&mut tk, sig, 202, 3, S / 2);
        let f = c.ev("presend_live_fill");
        if deep { assert_eq!(f[0]["deep"], false, "the attempt was signed after H fell below 6%"); } else { assert!(f[0].get("deep").is_none()); }
    }
}

/// dip28 TEST B: --presend-live-ann on: the fill's "st_block" (the SAFE sell-timer check's would-block) is true when a holder >= 6% still
/// holding at our landing has >= 5 holds at risk and a 3-slot hazard >= 0.3 (H's preloaded clock: holds 102..105 and 150 at age 102 ->
/// at risk 5, hazard 4.05 / 6); false without a clock; the status counts it
#[test]
fn dip28_safe_sell_timer_log() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let (h, w, x) = ([0xB1u8; 32], [0xA1u8; 32], [0x33u8; 32]);
    for clock in [true, false] {
        let mut c = Ctx::new(&["--presend-live-ann", "on"]);
        if clock { c.p.det.clock_preload(h, pl::Holds::from_holds(&[102, 103, 104, 105, 150], 0)); }
        let mut tk = c.token(0x31, 100, &[(h, 8.0)]);
        for s in 190..=192 { let e = tk.buy(x, S / 10); c.tx(s, 4, vec![e], vec![]); }
        let e = tk.buy_tok(w, pct(7.0)); c.tx(200, 5, vec![e], vec![]);
        let id = c.ev("presend_live_arm")[0]["w"].as_u64().unwrap();
        let sig = c.attempt_at(id, tk.mint, 201);
        c.fill(&mut tk, sig, 202, 3, S / 2);
        let a = &c.ev("presend_live_fill")[0]["ann"];
        let hh = a["holders"].as_array().unwrap().iter().find(|x| x["w"] == b58(&h)).unwrap().clone();
        if clock {
            assert_eq!((a["st_block"].as_bool(), hh["risk"].as_u64(), hh["age"].as_u64()), (Some(true), Some(5), Some(102)), "{a}");
            assert!((hh["hz3"].as_f64().unwrap() - 4.05 / 6.0).abs() < 1e-5);
            assert!(c.p.status().contains("st-safe would-block fills 1"), "{}", c.p.status());
        } else {
            assert_eq!(a["st_block"].as_bool(), Some(false));
            assert!(c.p.status().contains("st-safe would-block fills 0"));
        }
    }
}

/// dip28 TEST C: the holds state: saved (every clock), loaded into a fresh detector (the same holds), a missing file is an error (the
/// engine then starts empty)
#[test]
fn dip28_holds_state_roundtrip() {
    let mut d = pl::Detector::new(6.0);
    d.track = true;
    d.clock_preload([7; 32], pl::Holds::from_holds(&[3, 9, 27], 10));
    d.clock_preload([8; 32], pl::Holds::from_holds(&[5], 10));
    let f = std::env::temp_dir().join(format!("dip28_holds_{}.json", std::process::id()));
    let p = f.display().to_string();
    assert_eq!(holds_save(&d, &p, 4242).unwrap(), 2);
    let mut d2 = pl::Detector::new(6.0);
    d2.track = true;
    assert_eq!(holds_load(&mut d2, &p).unwrap(), 2);
    let mut a = d2.holds_of(&[7; 32]).unwrap().all().to_vec(); a.sort_unstable();
    assert_eq!(a, vec![3, 9, 27]);
    assert_eq!(d2.holds_of(&[8; 32]).unwrap().all(), &[5]);
    let _ = std::fs::remove_file(&f);
    assert!(holds_load(&mut d2, &p).is_err());
}
