//! The replay harness itself (`replay::replay`, `replay::quote`; the `arbx replay` and `arbx quote` arms call them) on
//! a scenario's run directory: one route priced at a recorded state version (single and batch), the compare's window and
//! `--to-slot` cut, journal and accounts.bin gaps, the what-if overrides, the repricing (X3), the refusals, and (review
//! WP-09) what makes a replay whole, the gate each decision read, the timers' scopes, later copies, an executor's run,
//! the run's digests, rotation and the output directory.
use super::*;
use crate::control::SendGate;
use crate::rec::journal::JBody;
use crate::replay::{self, Opts, QuoteReq, Reprice};
use std::sync::atomic::{AtomicBool, Ordering};

const POOLS: [&str; 3] = ["usdc.pump", "usdc.ammv4", "usdc.dlmm"];

/// a run: a large USDC sale on the AMM v4 pool (a real gap: opportunities), two slots later a small trade on PumpSwap
fn run(name: &'static str) -> (Done, [u8; 64], [u8; 64]) {
    let mut r = Rig::new(name, Setup { pools: &POOLS, ..Default::default() });
    r.make_ready(T0);
    let a = r.meta("usdc.ammv4");
    let p = r.meta("usdc.pump");
    let s2 = r.s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    let usdc_in = token_amount(&r.data(if sol_is_t0(&a) { &a.vault1 } else { &a.vault0 })) / 40;
    let w = swap(&r.chain, &a, !sol_is_t0(&a), usdc_in, s2, r.unix0).0;
    let (ta, tp) = (r.sig("A"), r.sig("P"));
    let mut t = T0 + 10 * MS;
    for (k, d) in w { r.write(k, d, s2, Some(ta), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    let s4 = r.s0 + 4;
    r.tick(r.s0 + 3, t + 400 * MS);
    r.tick(s4, t + 800 * MS);
    let w = swap(&r.chain, &p, !sol_is_t0(&p), 1_000_000_000, s4, r.unix0).0;
    let mut t = t + 810 * MS;
    for (k, d) in w { r.write(k, d, s4, Some(tp), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    (r.finish_and_replay(), ta, tp)
}

fn sig58(s: &[u8; 64]) -> String { bs58::encode(s).into_string() }

#[test]
fn quote_prices_a_route_at_a_recorded_state_version() {
    let (done, ta, tp) = run("h-quote");
    let ev = done.evaluations();
    let d0 = ev.iter().find(|d| d["trigger"]["txn"] == json!(sig58(&ta))).unwrap();
    let k = d0["best"].as_u64().unwrap() as usize;
    let best = &d0["routes"][k];
    assert!(d0["opp"].is_u64(), "A opened a gap: {d0}");
    let route = format!("{},{},{}", best["buy"].as_str().unwrap(), best["sell"].as_str().unwrap(), best["mint"].as_str().unwrap());
    let size = best["size"].as_u64().unwrap();
    // A's post-state: the decision's own state (the engine's pricing at its size gives its gross, net and CU)
    let q = replay::quote(&done.dir, None, None, vec![QuoteReq::parse(&route, &sig58(&ta), size, json!("post-A")).unwrap()]).unwrap();
    assert_eq!(q[0]["ok"], json!(true), "{}", q[0]);
    assert_eq!((&q[0]["gross"], &q[0]["net"], &q[0]["cu"]), (&best["gross"], &best["net"], &best["cu"]), "the engine's price at the decision's state: {}", q[0]);
    assert_eq!(q[0]["schema"], json!(replay::QUOTE_SCHEMA));
    // the same state named by A's last account record, and by its slot:write_version; A's pre-state differs
    let a_seen: Vec<&Value> = done.commits.iter().find(|c| c["txn"] == json!(sig58(&ta))).unwrap()["w_seen"].as_array().unwrap().iter().collect();
    let last = a_seen.iter().max_by_key(|m| m["aseq"].as_u64()).unwrap();
    let first = a_seen.iter().min_by_key(|m| m["aseq"].as_u64()).unwrap();
    let batch = vec![
        QuoteReq::parse(&route, &format!("aseq:{}", last["aseq"]), size, json!(1)).unwrap(),
        QuoteReq::parse(&route, &format!("{}:{}", last["slot"], last["wv"]), size, json!(2)).unwrap(),
        QuoteReq::parse(&route, &format!("pre:{}", sig58(&ta)), size, json!(3)).unwrap(),
        QuoteReq::parse(&route, &format!("aseq:{}", first["aseq"]), size, json!(4)).unwrap(),
        QuoteReq::parse(&route, &sig58(&tp), size, json!(5)).unwrap(),
        QuoteReq::parse(&route, &sig58(&[9; 64]), size, json!(6)).unwrap(),
        QuoteReq::parse(&route, "aseq:1", size, json!(7)).unwrap(),
    ];
    let q = replay::quote(&done.dir, None, None, batch).unwrap();
    assert_eq!(q.iter().map(|x| x["id"].clone()).collect::<Vec<_>>(), (1..=7).map(|i| json!(i)).collect::<Vec<_>>(), "answers in the order asked");
    assert_eq!((q[0]["gross"].clone(), q[1]["gross"].clone()), (best["gross"].clone(), best["gross"].clone()), "the post-A state by its aseq and by slot:write_version");
    assert_ne!(q[2]["gross"], best["gross"], "A's pre-state has no gap: {}", q[2]);
    assert!(q[2]["gross"].as_i64().unwrap() < 0, "{}", q[2]);
    assert_ne!(q[3]["gross"], best["gross"], "half of A: {}", q[3]);
    assert_eq!(q[4]["ok"], json!(true));
    assert_eq!((q[5]["ok"].clone(), q[5]["error"].as_str().map(|e| e.contains("no account update stamped"))), (json!(false), Some(true)), "{}", q[5]);
    assert!(q[6]["version"]["at_seq"].is_null(), "a boot record: answered on the boot state, before any input: {}", q[6]);
    // what the price read: every account of both pools at its version, and whether a decision would leave it out now:
    // A was not seen in shreds (W(A) unknown), so right after its last write its group still waits for quiescence (the
    // decision came at the timer): A's accounts are pending there, and so is A's first write at half of A (a torn
    // state R8 can see); on the boot state nothing is
    let pending = |x: &Value| -> Vec<String> { x["state"].as_array().unwrap().iter().filter(|s| s["pending"] == json!(true)).map(|s| s["acct"].as_str().unwrap().to_string()).collect() };
    assert!(q[0]["state"].as_array().unwrap().iter().any(|s| s["txn"] == json!(sig58(&ta))));
    let a_accts: Vec<String> = a_seen.iter().map(|m| m["acct"].as_str().unwrap().to_string()).collect();
    assert!(!pending(&q[0]).is_empty() && pending(&q[0]).iter().all(|k| a_accts.contains(k)), "{} {a_accts:?}", q[0]["state"]);
    assert!(!pending(&q[3]).is_empty(), "{}", q[3]["state"]);
    assert!(pending(&q[6]).is_empty() && q[6]["state"].as_array().unwrap().iter().all(|s| s["unverified"] == json!(false)), "{}", q[6]["state"]);
    // the arm's batch mode: JSON lines in and out
    let b = done.dir.join("batch.jsonl");
    std::fs::write(&b, format!("{{\"id\":\"x\",\"route\":\"{route}\",\"version\":\"{}\",\"size\":{size}}}\n", sig58(&ta))).unwrap();
    assert_eq!(replay::cli_quote(&done.dir, None, None, None, None, None, Some(&b)).unwrap(), 0);
}

/// review WP-09 #8: a batch is one pass whatever its size: thousands of questions on the same few versions answer in
/// about the time of one
#[test]
fn a_quote_batch_is_one_pass() {
    let (done, ta, _tp) = run("h-batch");
    let ev = done.evaluations();
    let d0 = ev.iter().find(|d| d["trigger"]["txn"] == json!(sig58(&ta))).unwrap();
    let best = &d0["routes"][d0["best"].as_u64().unwrap() as usize];
    let route = format!("{},{},{}", best["buy"].as_str().unwrap(), best["sell"].as_str().unwrap(), best["mint"].as_str().unwrap());
    let size = best["size"].as_u64().unwrap();
    let t0 = std::time::Instant::now();
    let one = replay::quote(&done.dir, None, None, vec![QuoteReq::parse(&route, &sig58(&ta), size, json!(0)).unwrap()]).unwrap();
    let t_one = t0.elapsed();
    let many: Vec<QuoteReq> = (0..4_000).map(|i| QuoteReq::parse(&route, &if i % 2 == 0 { sig58(&ta) } else { format!("pre:{}", sig58(&ta)) }, size, json!(i)).unwrap()).collect();
    let t0 = std::time::Instant::now();
    let q = replay::quote(&done.dir, None, None, many).unwrap();
    let t_many = t0.elapsed();
    assert_eq!(q.len(), 4_000);
    assert!(q.iter().step_by(2).all(|x| x["gross"] == one[0]["gross"]) && q.iter().skip(1).step_by(2).all(|x| x["gross"] != one[0]["gross"]));
    eprintln!("quote: 1 question {:.1} ms, 4,000 questions {:.1} ms", t_one.as_secs_f64() * 1e3, t_many.as_secs_f64() * 1e3);
    // each answer prices the route once (about 10 µs); the replay itself is shared
    assert!(t_many < t_one * 20 + std::time::Duration::from_secs(2), "{t_many:?} for 4,000 against {t_one:?} for one");
}

#[test]
fn the_compare_window_and_the_to_slot_cut() {
    let (done, _ta, tp) = run("h-window");
    let n = done.evaluations().len() as u64;
    assert!(n >= 2);
    // stop once the tip passes s0+3: the PumpSwap trade (slot s0+4) is not replayed, and not compared
    let s0 = fixtures().slot;
    let r = replay::replay(&done.dir, &Opts { to_slot: Some(s0 + 3), compare: true, out: Some(done.dir.join("cut")), ..Default::default() }).unwrap();
    assert!(r.ok, "{}", r.diff.unwrap());
    let c = &r.summary["compare"];
    assert!(r.summary["window"]["stopped_at_seq"].is_u64(), "stopped: {}", r.summary["window"]);
    assert!(c["outside_window"].as_u64().unwrap() >= 1 && c["compared"].as_u64().unwrap() < n, "{c}");
    assert_eq!(r.summary["digests"]["checked"], json!(false), "a replay cut short cannot reach the run's final digests");
    let replayed = rec::read_jsonl(&done.dir.join("cut"), "decisions").unwrap();
    assert!(replayed.iter().all(|d| d["trigger"]["txn"] != json!(sig58(&tp))), "nothing past the cut was replayed");
    // compare only from s0+4: the earlier decisions are outside the window, replayed all the same
    let r = replay::replay(&done.dir, &Opts { from_slot: Some(s0 + 4), compare: true, out: Some(done.dir.join("from")), ..Default::default() }).unwrap();
    assert!(r.ok);
    let c = &r.summary["compare"];
    assert_eq!(c["compared"].as_u64().unwrap() + c["outside_window"].as_u64().unwrap(), n, "{c}");
    assert!(c["compared"].as_u64().unwrap() >= 1);
    // a replay into a directory that exists is refused
    assert!(replay::replay(&done.dir, &Opts { out: Some(done.dir.join("from")), ..Default::default() }).is_err());
}

#[test]
fn what_if_overrides_change_the_decisions_and_the_compare_says_so() {
    let (done, ta, _tp) = run("h-whatif");
    let ev = done.evaluations();
    let opp = ev.iter().find(|d| d["trigger"]["txn"] == json!(sig58(&ta))).unwrap();
    assert!(opp["opp"].is_u64());
    // a min_profit no route clears: the opportunity becomes below_min_profit
    let sets = vec!["strategy.min_profit_lamports=1000000000000".parse().unwrap()];
    let r = replay::replay(&done.dir, &Opts { compare: true, sets, out: Some(done.dir.join("whatif")), ..Default::default() }).unwrap();
    let diff = r.diff.unwrap();
    assert!(!r.ok && diff["summary"]["what_if"] == json!(true), "{}", diff["summary"]);
    assert!(diff["diffs"].as_array().unwrap().iter().any(|x| x["field"] == "reason" && x["replay"] == "below_min_profit" && x["class"] == "pricing"), "{diff}");
    assert_eq!(r.summary["overrides"], json!(["strategy.min_profit_lamports=1000000000000"]));
    // a knob: a quiescence longer than the run's timer waits moves every quiescent evaluation to the next stream message
    let r = replay::replay(&done.dir, &Opts { compare: true, sets: vec!["state.quiescence_ms=10".parse().unwrap()], out: Some(done.dir.join("q10")), ..Default::default() }).unwrap();
    assert!(!r.ok);
    assert!(r.diff.unwrap()["summary"]["by_field"]["t_ns"].as_u64().unwrap() >= 1);
    // the tip every net is computed with
    let r = replay::replay(&done.dir, &Opts { compare: true, sets: vec!["min_tip=2000".parse().unwrap()], out: Some(done.dir.join("tip")), ..Default::default() }).unwrap();
    assert!(r.diff.unwrap()["summary"]["by_field"]["routes"].as_u64().unwrap() >= 1);
    // unknown keys are refused, before anything is written (review WP-09 #9: no half-made directory)
    for bad in ["strategy.no_such_key=1", "nothing=1", "state.nope=2"] {
        let out = done.dir.join(format!("bad-{bad}"));
        let e = replay::replay(&done.dir, &Opts { sets: vec![bad.parse().unwrap()], out: Some(out.clone()), ..Default::default() }).err().unwrap();
        assert!(format!("{e:#}").contains("--set"), "{bad}: {e:#}");
        assert!(!out.exists(), "{bad}: a refused replay leaves no directory");
    }
}

#[test]
fn reprice_sizes_requotes_every_opportunity_at_its_decision() {
    let (done, _ta, _tp) = run("h-reprice");
    let opps = done.evaluations().iter().filter(|d| d["opp"].is_u64()).count();
    assert!(opps >= 1);
    let sizes: Vec<Reprice> = ["0.5", "0.25", "0.125", "opt"].iter().map(|s| s.parse().unwrap()).collect();
    let r = replay::replay(&done.dir, &Opts { compare: true, reprice: sizes, out: Some(done.dir.join("rp")), ..Default::default() }).unwrap();
    assert!(r.ok, "the repricing (in the compare's own pass) changes nothing the compare reads: {}", r.summary);
    let lines: Vec<Value> = std::fs::read_to_string(done.dir.join("rp/reprice.jsonl")).unwrap().lines().map(|l| serde_json::from_str(l).unwrap()).collect();
    assert_eq!(lines[0]["schema"], json!(replay::REPRICE_SCHEMA));
    assert_eq!(lines.len() - 1, opps, "one line per opportunity");
    for l in &lines[1..] {
        assert_eq!(l["requote_same_gross"], json!(true), "the repricing reads the decision's state: {l}");
        // review WP-09 #10: the decision's own pricing (net and CU too)
        assert_eq!((&l["requote"]["net"], &l["requote"]["cu"]), (&l["run"]["net"], &l["run"]["cu"]), "{l}");
        assert_eq!(l["at"].as_array().unwrap().len(), 3);
        let half = &l["at"][0];
        assert_eq!(half["size"].as_u64(), Some(l["size"].as_u64().unwrap() / 2));
        assert!(l["opt"]["net"].as_i64().unwrap() >= l["run"]["net"].as_i64().unwrap() - 1, "the optimum is at least the ladder's best: {l}");
    }
    assert_eq!(r.summary["reprice"]["repriced"].as_u64(), Some(opps as u64));
    assert!("2".parse::<Reprice>().is_err() && "x".parse::<Reprice>().is_err());
}

/// the raw records of an uncompressed journal file (after its header): (kind, seq, t_engine, the record's bytes)
pub(super) fn raw_records(b: &[u8]) -> (usize, Vec<(u8, u64, u64, Vec<u8>)>) {
    let hlen = u16::from_le_bytes([b[10], b[11]]) as usize;
    let mut p = 12 + hlen;
    let mut out = Vec::new();
    while p < b.len() {
        let n = u32::from_le_bytes(b[p + 1..p + 5].try_into().unwrap()) as usize;
        let seq = u64::from_le_bytes(b[p + 5..p + 13].try_into().unwrap());
        let t = u64::from_le_bytes(b[p + 13..p + 21].try_into().unwrap());
        out.push((b[p], seq, t, b[p..p + 21 + n].to_vec()));
        p += 21 + n;
    }
    (12 + hlen, out)
}

/// the run's journal rewritten: `edit` gets each raw record and returns what to write in its place
pub(super) fn rewrite_journal(dir: &Path, mut edit: impl FnMut(usize, &(u8, u64, u64, Vec<u8>)) -> Vec<u8>) {
    let files = rec::stream_files(dir, "journal");
    assert_eq!(files.len(), 1);
    let bytes = rec::decode_zst(&files[0]).unwrap().0;
    let (head, recs) = raw_records(&bytes);
    let mut out = bytes[..head].to_vec();
    for (i, r) in recs.iter().enumerate() { out.extend(edit(i, r)); }
    std::fs::remove_file(&files[0]).unwrap();
    std::fs::write(dir.join("journal.000.bin"), &out).unwrap();
}

/// a GAP record for `n` records from `seq`
pub(super) fn gap_rec(seq: u64, t: u64, n: u64) -> Vec<u8> {
    let mut o = vec![crate::rec::journal::J_GAP];
    o.extend(16u32.to_le_bytes());
    o.extend(seq.to_le_bytes());
    o.extend(t.to_le_bytes());
    o.extend(seq.to_le_bytes());
    o.extend(n.to_le_bytes());
    o
}

/// Journal gaps (replay-class drops): a GAP record where records were lost. The replay lists the gap, does not compare
/// the decisions made inside it, and marks every difference after it `after_gap`; an account record accounts.bin lost is
/// counted and its input skipped
#[test]
fn journal_and_accounts_gaps_are_reported_and_skipped() {
    let (done, ta, _tp) = run("h-gap");
    // lose A's first account record from the journal (as a full queue would): a GAP record takes its place
    let a_first = done.commits.iter().find(|c| c["txn"] == json!(sig58(&ta))).unwrap()["w_seen"][0]["aseq"].as_u64().unwrap();
    let mut lost = None;
    rewrite_journal(&done.dir, |_, r| {
        if r.0 == crate::rec::journal::J_ACCOUNT && u64::from_le_bytes(r.3[21..29].try_into().unwrap()) == a_first { lost = Some((r.1, r.2)); return vec![]; }
        match lost.take() { Some((s, t)) => { let mut o = gap_rec(s, t, 1); o.extend(&r.3); o } None => r.3.clone() }
    });
    let r = replay::replay(&done.dir, &Opts { compare: true, out: Some(done.dir.join("gap")), ..Default::default() }).unwrap();
    let diff = r.diff.unwrap();
    assert!(diff["gaps"][0]["first_lost_seq"].is_u64(), "{}", diff["gaps"]);
    assert_eq!(r.summary["journal"]["gaps"].as_array().unwrap().len(), 1);
    // A's group never completes as in the run: the decisions after the gap differ, every difference marked after_gap
    assert!(!r.ok);
    assert!(diff["diffs"].as_array().unwrap().iter().all(|x| x["after_gap"] == json!(true)), "{diff}");
    // accounts.bin without A's second record: the journal names it, the replay counts it and skips the input
    let (done2, ta2, _) = run("h-gap2");
    let a2 = done2.commits.iter().find(|c| c["txn"] == json!(sig58(&ta2))).unwrap()["w_seen"][1]["aseq"].as_u64().unwrap();
    remove_account_record(&done2.dir, a2);
    let r = replay::replay(&done2.dir, &Opts { compare: true, out: Some(done2.dir.join("agap")), ..Default::default() }).unwrap();
    assert_eq!(r.summary["accounts"]["missing"], json!(1));
    assert!(!r.ok);
}

/// accounts.bin without the record `aseq` (FULL or XOR): as if the recorder had lost it
fn remove_account_record(dir: &Path, aseq: u64) {
    let af = rec::stream_files(dir, "accounts");
    assert_eq!(af.len(), 1);
    let ab = rec::decode_zst(&af[0]).unwrap().0;
    let hlen = u16::from_le_bytes([ab[10], ab[11]]) as usize;
    let mut p = 12 + hlen;
    let mut kept = ab[..p].to_vec();
    while p < ab.len() {
        let n = u32::from_le_bytes(ab[p + 1..p + 5].try_into().unwrap()) as usize;
        let is_it = matches!(ab[p], 2 | 3) && u64::from_le_bytes(ab[p + 5..p + 13].try_into().unwrap()) == aseq;
        if !is_it { kept.extend(&ab[p..p + 5 + n]); }
        p += 5 + n;
    }
    std::fs::remove_file(&af[0]).unwrap();
    std::fs::write(dir.join("accounts.000.bin"), &kept).unwrap();
}

/// a run whose losses change no decision: three pools, trades and Clock writes every few trades (review E3)
fn quiet_losses_run(name: &'static str) -> Done {
    let pools = ["usdc.pump", "usdc.ammv4", "usdc.cpmm"];
    let mut r = Rig::new(name, Setup { pools: &pools, ..Default::default() });
    r.make_ready(T0);
    let metas: Vec<PoolMeta> = pools.iter().map(|n| r.meta(n)).collect();
    let mut t = T0 + 10 * MS;
    let mut slot = r.s0 + 1;
    for n in 0..60u64 {
        if n % 4 == 0 { slot += 1; r.tick(slot, t); t += MS; }
        let m = &metas[(n % 3) as usize];
        let zfo = if n % 2 == 0 { sol_is_t0(m) } else { !sol_is_t0(m) };
        let amt = if n % 2 == 0 { SOL / 10 } else { 12_000_000 };
        let Some((w, _)) = try_swap(&r.chain, m, zfo, amt, slot, r.unix0) else { continue };
        let sig = { let mut s = [0u8; 64]; s[..8].copy_from_slice(&n.to_le_bytes()); s[8] = 0xe3; s };
        for (k, d) in w { t += 50 * US; r.write(k, d, slot, Some(sig), t); }
        t += 5 * MS;
        r.timers(t);
        t += 20 * MS;
    }
    r.finish_and_replay()
}

/// the stream's Clock writes (src grpc) in accounts.bin, by aseq
fn clock_aseqs(dir: &Path) -> Vec<u64> {
    crate::rec::accounts::read_dir(dir).unwrap().records.iter().filter(|r| r.pubkey == *CLOCK_SYSVAR && r.src == asrc::GRPC).map(|r| r.aseq).collect()
}

/// Review WP-09 #2 (E3): `ok` needs a whole replay. Three recordings whose losses change no decision (a lost Clock
/// record, in the journal or in accounts.bin, and a store verdict the replay does not reproduce) compare identically
/// field by field, and are still not ok: the replay is not what the run did
#[test]
fn ok_needs_a_whole_replay() {
    let not_whole = |r: &replay::Report| -> Vec<String> { r.summary["not_whole"].as_array().unwrap().iter().map(|w| w["why"].as_str().unwrap().to_string()).collect() };
    // (a) a journal GAP in place of a Clock ACCOUNT record
    let done = quiet_losses_run("h-e3a");
    let clocks = clock_aseqs(&done.dir);
    let mut k = 0;
    let mut lost = None;
    rewrite_journal(&done.dir, |_, r| {
        if r.0 == crate::rec::journal::J_ACCOUNT && r.2 > 0 && clocks.contains(&u64::from_le_bytes(r.3[21..29].try_into().unwrap())) {
            k += 1;
            if k == 6 { lost = Some((r.1, r.2)); return vec![]; }
        }
        match lost.take() { Some((s, t)) => { let mut o = gap_rec(s, t, 1); o.extend(&r.3); o } None => r.3.clone() }
    });
    let r = replay::replay(&done.dir, &Opts { compare: true, out: Some(done.dir.join("gap")), ..Default::default() }).unwrap();
    assert_eq!(r.diff.as_ref().unwrap()["summary"]["field_diffs"], json!(0), "the lost record changed no decision: {}", r.diff.as_ref().unwrap()["summary"]);
    assert!(!r.ok && not_whole(&r).contains(&"journal_gap".to_string()), "{}", r.summary["not_whole"]);
    assert_eq!(r.diff.as_ref().unwrap()["ok"], json!(false), "replay-diff.json says the same");
    // (b) accounts.bin without one Clock record the journal names (its last: a record removed mid-chain breaks the XOR chain)
    let done = quiet_losses_run("h-e3b");
    remove_account_record(&done.dir, *clock_aseqs(&done.dir).last().unwrap());
    let r = replay::replay(&done.dir, &Opts { compare: true, out: Some(done.dir.join("miss")), ..Default::default() }).unwrap();
    assert_eq!(r.diff.as_ref().unwrap()["summary"]["field_diffs"], json!(0));
    assert!(!r.ok && not_whole(&r).contains(&"accounts_missing".to_string()), "{}", r.summary["not_whole"]);
    // (c) an ACCOUNT record whose journaled verdict differs from the replayed store's
    let done = quiet_losses_run("h-e3c");
    let mut n = 0;
    rewrite_journal(&done.dir, |_, r| {
        let mut b = r.3.clone();
        if r.0 == crate::rec::journal::J_ACCOUNT && r.2 > 0 { n += 1; if n == 20 { let l = b.len() - 1; b[l] ^= 1; } }
        b
    });
    let r = replay::replay(&done.dir, &Opts { compare: true, out: Some(done.dir.join("verdict")), ..Default::default() }).unwrap();
    assert_eq!(r.diff.as_ref().unwrap()["summary"]["field_diffs"], json!(0));
    assert!(!r.ok && not_whole(&r).contains(&"verdict_mismatch".to_string()), "{}", r.summary["not_whole"]);
    // (d) the run's recorder dropped decisions (manifest.json): not whole either, even without --compare
    let done = quiet_losses_run("h-e3d");
    std::fs::write(done.dir.join("manifest.json"), serde_json::to_string(&json!({ "schema": "arbx.manifest/1.0", "final": true,
        "streams": [{ "name": "decisions", "dropped_total": 3, "suppressed_total": 0 }], "queues": { "core": { "lost_at_close": 0 } } })).unwrap()).unwrap();
    let r = replay::replay(&done.dir, &Opts { out: Some(done.dir.join("drops")), ..Default::default() }).unwrap();
    assert!(!r.ok && not_whole(&r).contains(&"run_recorder_loss".to_string()), "{}", r.summary["not_whole"]);
    // and the CLI says so with its exit code
    assert_eq!(replay::cli_replay(&done.dir, &Opts { out: Some(done.dir.join("drops-cli")), ..Default::default() }).unwrap(), 1);
}

/// Review WP-09 #3: the gate each decision without an executor read is journaled at the decision (INPUT 3 `src`
/// "decision", the reason with it) and the replay applies it at that opportunity. The gate is paused, resumed and paused
/// again between decisions (non-sticky changes, as the control socket makes them), and a stale 100 ms sample arrives
/// while it is paused (a replay that applied the samples would read the gate open there): the replay reproduces each
/// reason
#[test]
fn the_gate_each_decision_read_is_journaled_and_replayed() {
    let mut r = Rig::new("h-gate", Setup { pools: &POOLS, ..Default::default() });
    let gate = SendGate::new();
    r.e.gate = Some(gate.clone());
    r.make_ready(T0);
    let a = r.meta("usdc.ammv4");
    let mut t = T0 + 10 * MS;
    let mut slot = r.s0 + 1;
    // each trade sells USDC into the AMM v4 pool: the gap against the other pools widens, every trade is an opportunity
    let trade = |r: &mut Rig, label: &str, t: &mut u64, slot: &mut u64| {
        *slot += 1;
        r.tick(*slot, *t);
        let amount = token_amount(&r.data(if sol_is_t0(&a) { &a.vault1 } else { &a.vault0 })) / 40;
        let w = swap(&r.chain, &a, !sol_is_t0(&a), amount, *slot, r.unix0).0;
        let s = r.sig(label);
        *t += MS;
        for (k, d) in w { r.write(k, d, *slot, Some(s), *t); *t += 100 * US; }
        r.timers(*t + 4 * MS);
        *t += 50 * MS;
        s
    };
    gate.shadow("paused", "harness", false).unwrap();
    let s1 = trade(&mut r, "G1", &mut t, &mut slot);
    // a 100 ms sample read before the pause and dequeued after it (status only: the run's decisions read the live gate)
    r.input(InputKind::Gate, json!({ "mode": "live", "reason": null, "detail": null, "since_ns": T0, "sticky": false, "src": "watch" }), t);
    let s1b = trade(&mut r, "G1b", &mut t, &mut slot);
    gate.resume("harness").unwrap();
    let s2 = trade(&mut r, "G2", &mut t, &mut slot);
    gate.shadow("paused", "harness again", false).unwrap();
    let s3 = trade(&mut r, "G3", &mut t, &mut slot);
    let ev = r.evaluations();
    let reason_of = |s: &[u8; 64]| -> Vec<String> { ev.iter().filter(|d| d["trigger"]["txn"] == json!(sig58(s)) && d["opp"].is_u64()).map(|d| d["reason"].as_str().unwrap().to_string()).collect() };
    let (g1, g1b, g2, g3) = (reason_of(&s1), reason_of(&s1b), reason_of(&s2), reason_of(&s3));
    assert!(!g1.is_empty() && !g1b.is_empty() && !g2.is_empty() && !g3.is_empty(), "each trade opened an opportunity: {g1:?} {g1b:?} {g2:?} {g3:?}");
    assert!(g1.iter().chain(&g1b).chain(&g3).all(|x| x == "gate_shadow:paused") && g2.iter().all(|x| x == "no_executor"), "{g1:?} {g1b:?} {g2:?} {g3:?}");
    r.rec.sync();
    let recs: Vec<Value> = crate::rec::journal::read_dir(&r.dir).unwrap().into_iter().filter(crate::rec::journal::is_gate_decision)
        .map(|x| match x.body { JBody::Input { data, .. } => data, _ => unreachable!() }).collect();
    assert_eq!(recs.iter().map(|x| x["why"].as_str().unwrap()).collect::<Vec<_>>(), vec!["gate_shadow:paused", "no_executor", "gate_shadow:paused"], "{recs:?}");
    assert!(recs.iter().all(|x| x["opp"].is_u64() && x["executor"] == json!(false)));
    let done = r.finish_and_replay();
    assert_eq!(done.replay["journal"]["gate_staged"], json!(3), "{}", done.replay["journal"]);
}

/// Review WP-09 #3 (E1): the real `Engine::run` loop on the real clock, fed by another thread, with a live SendGate
/// shared with a 100 ms sampler (INPUT 3 `src` "watch", as `arbx run` spawns it) and paused then resumed by a third
/// thread mid-run. The decisions on either side of each change read the gate at the decision; the replay reproduces
/// every one of them (the 100 ms samples are status only)
#[test]
fn a_run_loop_with_a_paused_gate_replays_identically() {
    let pools = ["usdc.pump", "usdc.ammv4", "usdc.cpmm"];
    let mut r = Rig::new("h-runloop", Setup { pools: &pools, ..Default::default() });
    let gate = SendGate::new();
    std::fs::write(r.dir.join("meta.json"), serde_json::to_string(&json!({ "schema": "arbx.meta/2.0", "send_gate": gate.json() })).unwrap()).unwrap();
    r.e.gate = Some(gate.clone());
    r.make_ready(T0);
    let (tx, rx) = crossbeam_channel::unbounded::<Event>();
    let stop = Arc::new(AtomicBool::new(false));
    let sampler = {
        let (gate, back, stop) = (gate.clone(), tx.clone(), stop.clone());
        std::thread::spawn(move || {
            let mut last = Value::Null;
            while !stop.load(Ordering::Relaxed) {
                let mut g = gate.json();
                if let Some(m) = g.as_object_mut() { m.remove("since_ns"); }
                if g != last {
                    let mut d = gate.json();
                    d["src"] = json!("watch");
                    let _ = back.send(Event::Input { kind: InputKind::Gate, data: Arc::new(d) });
                    last = g;
                }
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
        })
    };
    let metas: Vec<PoolMeta> = pools.iter().map(|n| r.meta(n)).collect();
    let (ar, mut chain, s0, unix0) = (r.ar.clone(), r.chain.clone(), r.s0, r.unix0);
    let feeder = {
        let (tx, gate) = (tx.clone(), gate.clone());
        std::thread::spawn(move || {
            let now = crate::feeds::clock::real_ns;
            let mut wv = 10_000u64;
            let send_acct = |chain: &mut HashMap<Pk, Vec<u8>>, wv: &mut u64, key: Pk, data: Vec<u8>, slot: u64, txn: Option<[u8; 64]>| {
                *wv += 1;
                let t = now();
                let d: Arc<[u8]> = data.clone().into();
                let fx = fixtures().get(&key);
                let (lamports, owner) = (fx.map_or(1, |x| x.lamports), fx.map_or([0; 32], |x| x.owner));
                let aseq = ar.record(&AcctUpdate { pubkey: key, slot, write_version: *wv, t_recv: t, src: asrc::GRPC, is_startup: false, txn, lamports, owner, data: &d, bank_id: None });
                chain.insert(key, data);
                tx.send(Event::Account { slot, pubkey: key, owner, lamports, data: d, t, txn, write_version: *wv, is_startup: false, src: asrc::GRPC, aseq, bank_id: None }).unwrap();
            };
            let t_start = now();
            let (mut slot, mut next_slot, mut n) = (s0, t_start, 0u64);
            let (mut paused, mut resumed) = (false, false);
            while now() < t_start + 1_200_000_000 {
                let t = now();
                if t >= next_slot {
                    slot += 1;
                    tx.send(Event::Slot { slot, status: 0, t, parent: Some(slot - 1), dead_error: None, bank_id: None }).unwrap();
                    let c = clock_at(&chain[&*CLOCK_SYSVAR], slot, unix0 + (slot.saturating_sub(s0) * 400 / 1_000) as i64);
                    send_acct(&mut chain, &mut wv, *CLOCK_SYSVAR, c, slot, None);
                    next_slot += 400_000_000;
                }
                // the operator pauses sending 300 ms in and resumes it 300 ms later (another thread, as the control socket does)
                if !paused && t >= t_start + 300_000_000 { let _ = gate.shadow("paused", "harness", false); paused = true; }
                if paused && !resumed && t >= t_start + 600_000_000 { let _ = gate.resume("harness"); resumed = true; }
                n += 1;
                let m = &metas[(n % metas.len() as u64) as usize];
                let sol_in = n % 2 == 0;
                let zfo = if sol_in { sol_is_t0(m) } else { !sol_is_t0(m) };
                if let Some((w, _)) = try_swap(&chain, m, zfo, if sol_in { SOL / 10 } else { 12_000_000 }, slot, unix0) {
                    let sig = { let mut s = [0u8; 64]; s[..8].copy_from_slice(&n.to_le_bytes()); s[8] = 0xe1; s };
                    let wk: Vec<Pk> = w.iter().map(|x| x.0).collect();
                    tx.send(Event::Tx(shred_tx(sig, [0x33; 32], &wk, &[m.pool], vec![], slot, now()))).unwrap();
                    for (k, d) in w { send_acct(&mut chain, &mut wv, k, d, slot, Some(sig)); }
                }
                std::thread::sleep(std::time::Duration::from_millis(3));
            }
        })
    };
    let s2 = stop.clone();
    let stopper = std::thread::spawn(move || { std::thread::sleep(std::time::Duration::from_millis(1_400)); s2.store(true, Ordering::Relaxed); });
    let end = r.e.run(&rx, &stop, u64::MAX, |_| {});
    assert_eq!(end, crate::engine::RunEnd::Stopped);
    feeder.join().unwrap();
    sampler.join().unwrap();
    stopper.join().unwrap();
    // `Engine::run` ended with `finish`: the recorder closes, as `arbx run` closes it
    r.rec.close();
    let decisions = rec::read_jsonl(&r.dir, "decisions").unwrap();
    let opps: Vec<&Value> = decisions.iter().filter(|d| d["opp"].is_u64()).collect();
    let n_with = |p: &str| opps.iter().filter(|d| d["reason"].as_str().is_some_and(|x| x.starts_with(p))).count();
    assert!(n_with("no_executor") > 0 && n_with("gate_shadow:paused") > 0, "decisions on both sides of the pause: {} opportunities", opps.len());
    let rp = r.replay_compare("replay");
    let c = &rp.summary["compare"];
    assert!(rp.ok, "the replay reproduces every decision's gate: {} {}", rp.summary["not_whole"], serde_json::to_string_pretty(rp.diff.as_ref().unwrap()).unwrap());
    assert_eq!((c["identical"].clone(), c["digests_same"].clone()), (c["compared"].clone(), json!(true)), "{c}");
    assert!(rp.summary["journal"]["gate_staged"].as_u64().unwrap() >= 3, "{}", rp.summary["journal"]);
}

/// Review WP-09 #5 (R2): a TIMER is replayed with its journaled scope. After an input the run evaluates the commit
/// timers only (`TIMER_COMMIT`), with housekeeping due: Tier A is not checked then, so a decision right after it is
/// still `warmup`. A replay that ran every TIMER with everything allowed would open the gate there and differ
#[test]
fn timers_are_replayed_at_their_journaled_scope() {
    let mut r = Rig::new("h-scope", Setup { pools: &POOLS, ..Default::default() });
    let s1 = r.s0 + 1;
    r.tick(s1, T0);
    // housekeeping is due (6 ms after the first input), but this evaluation may only run the commit timers
    r.e.timers_at(T0 + 6 * MS, engine::TIMER_COMMIT, &mut nop());
    assert_eq!(r.e.shut(), crate::store_health::Shut::Warmup, "Tier A not checked yet");
    let a = r.meta("usdc.ammv4");
    let usdc_in = token_amount(&r.data(if sol_is_t0(&a) { &a.vault1 } else { &a.vault0 })) / 40;
    let w = swap(&r.chain, &a, !sol_is_t0(&a), usdc_in, s1, r.unix0).0;
    let s = r.sig("scope");
    let mut t = T0 + 7 * MS;
    for (k, d) in w { r.write(k, d, s1, Some(s), t); t += 100 * US; }
    r.e.timers_at(t + 4 * MS, engine::TIMER_COMMIT, &mut nop());
    let d = r.evaluations().into_iter().find(|d| d["opp"].is_u64()).expect("an opportunity");
    assert_eq!(d["reason"], "warmup", "{d}");
    // the next idle wake-up runs everything: Tier A complete, the gate opens
    r.timers(t + 10 * MS);
    assert_eq!(r.e.shut(), crate::store_health::Shut::Ready);
    r.finish_and_replay();
}

/// Review WP-09 #5 (R3) and #15: a later copy of a transaction (another unexecuted feed, journaled as TX_COPY) with an
/// earlier receive time is its first shred (`trigger.t_first_shred`, commits.jsonl `t_first_shred`), and its slot raises
/// the engine's shred slot (in the state digest). The replay feeds every copy with its slot
#[test]
fn later_copies_are_replayed_with_their_time_and_slot() {
    let mut r = Rig::new("h-copy", Setup { pools: &POOLS, ..Default::default() });
    r.make_ready(T0);
    let a = r.meta("usdc.ammv4");
    let s2 = r.s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    let usdc_in = token_amount(&r.data(if sol_is_t0(&a) { &a.vault1 } else { &a.vault0 })) / 40;
    let w = swap(&r.chain, &a, !sol_is_t0(&a), usdc_in, s2, r.unix0).0;
    let s = r.sig("copied");
    let wk: Vec<Pk> = w.iter().map(|x| x.0).collect();
    // the first copy from feed 0 at T0+12 ms; feed 2's copy, received at T0+11 ms, is dequeued after it (and says s2+1)
    r.tx(shred_tx(s, [0x51; 32], &wk, &[*crate::venues::RAYAMMV4], vec![], s2, T0 + 12 * MS));
    let mut copy = shred_tx(s, [0x51; 32], &wk, &[*crate::venues::RAYAMMV4], vec![], s2 + 1, T0 + 11 * MS);
    copy.feed = 2;
    r.e.step(Event::Tx(copy), T0 + 12 * MS + 50 * US, &mut nop());
    let mut t = T0 + 13 * MS;
    for (k, d) in w { r.write(k, d, s2, Some(s), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    r.rec.sync();
    assert!(crate::rec::journal::read_dir(&r.dir).unwrap().iter().any(|x| matches!(x.body, JBody::TxCopy { slot: Some(sl), .. } if sl == s2 + 1)), "a TX_COPY with its slot");
    let c = r.commits().into_iter().find(|c| c["txn"] == json!(sig58(&s))).unwrap();
    assert_eq!(c["t_first_shred"].as_u64(), Some(T0 + 11 * MS), "the copy's earlier receive time: {c}");
    let d = r.evaluations().into_iter().find(|d| d["trigger"]["txn"] == json!(sig58(&s))).unwrap();
    assert_eq!(d["trigger"]["t_first_shred"].as_u64(), Some(T0 + 11 * MS), "{d}");
    r.finish_and_replay();
}

/// Review WP-09 #4: a run with an executor whose executor the replay cannot rebuild (engine_init `executor` true, no
/// exec_init record: a recording made before the executor replay) is never replayed OK (`executor_not_replayed`), even
/// when every decision line compares equal
#[test]
fn a_run_with_an_executor_is_not_ok_until_its_executor_is_replayed() {
    let mut r = Rig::new("h-exec", Setup { pools: &POOLS, executor: true, ..Default::default() });
    r.make_ready(T0);
    let a = r.meta("usdc.ammv4");
    let s2 = r.s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    let usdc_in = token_amount(&r.data(if sol_is_t0(&a) { &a.vault1 } else { &a.vault0 })) / 40;
    let w = swap(&r.chain, &a, !sol_is_t0(&a), usdc_in, s2, r.unix0).0;
    let s = r.sig("exec");
    let mut t = T0 + 10 * MS;
    for (k, d) in w { r.write(k, d, s2, Some(s), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    r.e.finish();
    r.rec.close();
    let rp = r.replay_compare("replay");
    assert_eq!(rp.summary["executor_replayed"], json!(false));
    assert_eq!(rp.diff.as_ref().unwrap()["summary"]["differences_ok"], json!(true), "the lines themselves compare equal: {}", rp.diff.as_ref().unwrap()["summary"]);
    assert!(!rp.ok, "never a silent OK");
    assert!(rp.summary["not_whole"].as_array().unwrap().iter().any(|w| w["why"] == "executor_not_replayed" && w["detail"].as_str().unwrap().contains("no exec_init record")),
        "{}", rp.summary["not_whole"]);
    assert_eq!(rp.summary["executor"]["replayed"], json!(false));
}

/// Review WP-09 #6, FT-001: the run records its digests where it takes them (journal INPUT 14 `digest_point` and
/// events.jsonl `engine_digests`: before and after `finish`, each part's too), a replay checks them at that point of the
/// journal, and a run whose state the replay does not reach is not ok, the part that differs named
#[test]
fn the_run_records_its_digests_and_the_replay_checks_them() {
    let (done, _ta, _tp) = run("h-digests");
    let ev = rec::read_jsonl(&done.dir, "events").unwrap();
    let dg = ev.iter().find(|e| e["kind"] == "engine_digests").expect("an engine_digests event");
    assert!(dg["detail"]["before_finish"]["digest"].is_string() && dg["detail"]["decision_digest"].is_string() && dg["detail"]["point"] == json!("run_end"), "{dg}");
    assert!(dg["detail"]["parts"]["store.accounts"].is_string() && dg["detail"]["before_finish"]["parts"]["opps"].is_string(), "{dg}");
    assert_eq!((done.replay["digests"]["same"].clone(), done.replay["digests"]["point"].clone()), (json!(true), json!("marker")), "{}", done.replay["digests"]);
    // the same run with another state digest recorded at its digest point, and another digest of its commit groups: the
    // replay finds it and names the part
    let real = dg["detail"]["before_finish"]["digest"].as_str().unwrap().to_string();
    let fake = format!("{:016x}", u64::from_str_radix(&real, 16).unwrap() ^ 1);
    let mut n = 0;
    rewrite_journal(&done.dir, |_, x| {
        let b = &x.3;
        if x.0 != crate::rec::journal::J_INPUT || b[21] != InputKind::DigestPoint as u8 { return b.clone(); }
        n += 1;
        let mut v: Value = serde_json::from_slice(&b[26..]).unwrap();
        v["before_finish"]["digest"] = json!(fake);
        v["before_finish"]["parts"]["commit"] = json!("0000000000000000");
        let js = serde_json::to_vec(&v).unwrap();
        let mut body = vec![InputKind::DigestPoint as u8];
        body.extend((js.len() as u32).to_le_bytes());
        body.extend(&js);
        let mut o = vec![b[0]];
        o.extend((body.len() as u32).to_le_bytes());
        o.extend(&b[5..21]);
        o.extend(body);
        o
    });
    assert_eq!(n, 1, "one digest point (the run ended with finish, no stop sequence)");
    let r = replay::replay(&done.dir, &Opts { compare: true, out: Some(done.dir.join("tampered")), ..Default::default() }).unwrap();
    let d = &r.summary["digests"];
    assert_eq!((d["checked"].as_bool(), d["same"].as_bool()), (Some(true), Some(false)), "{d}");
    assert_eq!((d["points"][0]["before_finish_parts_differ"].clone(), d["points"][0]["parts_differ"].clone()), (json!(["commit"]), json!([])), "{d}");
    assert!(!r.ok && r.diff.unwrap()["summary"]["field_diffs"] == json!(0), "the lines are identical; the state is not");
}

/// Review WP-09 #5: a recording rotated into many files (every stream at 20 KB raw) replays identically, streaming
/// across the rotation files
#[test]
fn a_rotated_recording_replays_identically() {
    let pools = ["usdc.pump", "usdc.cpmm", "usdc.ammv4", "usdc.dlmm", "usdc.damm"];
    let mut r = Rig::new("h-rot", Setup { pools: &pools, rotate_mb: Some(0.02), ..Default::default() });
    r.make_ready(T0);
    let metas: Vec<PoolMeta> = pools.iter().map(|n| r.meta(n)).collect();
    let mut t = T0 + 10 * MS;
    let mut slot = r.s0 + 1;
    for n in 0..600u64 {
        if n % 20 == 0 { slot += 1; r.tick(slot, t); t += MS; }
        let m = &metas[(n % 5) as usize];
        let sol_in = n % 2 == 0;
        let zfo = if sol_in { sol_is_t0(m) } else { !sol_is_t0(m) };
        let Some((w, _)) = try_swap(&r.chain, m, zfo, if sol_in { SOL / 20 } else { 6_000_000 }, slot, r.unix0) else { t += MS; continue };
        let sig = { let mut s = [0u8; 64]; s[..8].copy_from_slice(&n.to_le_bytes()); s[8] = 0xe2; s };
        if n % 3 == 0 { let wk: Vec<Pk> = w.iter().map(|x| x.0).collect(); r.tx(shred_tx(sig, [0x34; 32], &wk, &[m.pool], vec![], slot, t)); }
        for (k, d) in w { t += 50 * US; r.write(k, d, slot, Some(sig), t); }
        t += 5 * MS;
        r.timers(t);
        t += 5 * MS;
    }
    let dir = r.dir.clone();
    let done = r.finish_and_replay();
    let files = |s: &str| rec::stream_files(&dir, s).len();
    assert!(files("journal") > 1 && files("accounts") > 1 && files("decisions") > 1 && files("commits") > 1, "rotated: journal {} accounts {} decisions {} commits {}",
        files("journal"), files("accounts"), files("decisions"), files("commits"));
    assert!(done.replay["compare"]["compared"].as_u64().unwrap() > 100);
}

/// Review WP-09 #9: the replay's directory is new (never one that exists, never inside the run by default), and a
/// refused replay leaves none behind
#[test]
fn the_output_directory_is_new_and_never_half_made() {
    let (done, _ta, _tp) = run("h-out");
    let d = replay::default_out(&done.dir);
    assert!(d.is_relative() && !d.starts_with(&done.dir) && d.to_string_lossy().contains(&std::process::id().to_string()), "{}", d.display());
    // an existing directory, even empty, is refused
    let empty = done.dir.join("empty");
    std::fs::create_dir_all(&empty).unwrap();
    assert!(format!("{:#}", replay::replay(&done.dir, &Opts { out: Some(empty.clone()), ..Default::default() }).err().unwrap()).contains("already exists"));
    // a config that is not the run's: refused before anything is written
    let other = done.dir.join("other.toml");
    std::fs::write(&other, std::fs::read_to_string(done.dir.join("config.toml")).unwrap().replacen("min_profit_lamports = 1", "min_profit_lamports = 2", 1)).unwrap();
    let out = done.dir.join("refused");
    assert!(replay::replay(&done.dir, &Opts { config: Some(other), out: Some(out.clone()), ..Default::default() }).is_err());
    assert!(!out.exists());
    // the replay writes no journal of its own (it would not be replayable)
    let r = replay::replay(&done.dir, &Opts { out: Some(done.dir.join("nojournal")), ..Default::default() }).unwrap();
    assert!(r.ok && rec::stream_files(&r.out, "journal").is_empty() && !rec::stream_files(&r.out, "decisions").is_empty());
}

#[test]
fn recordings_that_cannot_be_replayed_are_refused_with_the_reason() {
    let d = std::env::temp_dir().join(format!("arbx-replay-refuse-{}-{}", std::process::id(), crate::feeds::clock::real_ns()));
    std::fs::create_dir_all(&d).unwrap();
    // an arb-lab v1 run: no journal
    std::fs::write(d.join("opportunities.jsonl"), "{}\n").unwrap();
    let e = replay::replay(&d, &Opts::default()).err().unwrap();
    assert!(format!("{e:#}").contains("before WP-03"), "{e:#}");
    assert!(replay::cli_quote(&d, None, None, Some("a,b,c"), Some("1"), Some(1), None).is_err());
    let _ = std::fs::remove_dir_all(&d);
    let (done, _, _) = run("h-refuse");
    // another [strategy] than the run's (`--config`)
    let other = done.dir.join("other.toml");
    let text = std::fs::read_to_string(done.dir.join("config.toml")).unwrap().replacen("min_profit_lamports = 1", "min_profit_lamports = 2", 1);
    std::fs::write(&other, text).unwrap();
    let e = replay::replay(&done.dir, &Opts { config: Some(other), out: Some(done.dir.join("o1")), ..Default::default() }).err().unwrap();
    assert!(format!("{e:#}").contains("[strategy]"), "{e:#}");
    // a pools.json that is not a list of pools (MEASUREMENT §4.29)
    let pools = std::fs::read(done.dir.join("pools.json")).unwrap();
    std::fs::write(done.dir.join("pools.json"), "{}").unwrap();
    let e = replay::replay(&done.dir, &Opts { out: Some(done.dir.join("o2")), ..Default::default() }).err().unwrap();
    assert!(format!("{e:#}").contains("not a list of pools"), "{e:#}");
    // a pools.json registry-run.json was not written with
    let mut v: Value = serde_json::from_slice(&pools).unwrap();
    v[0]["flag"] = json!(!v[0]["flag"].as_bool().unwrap());
    std::fs::write(done.dir.join("pools.json"), serde_json::to_vec(&v).unwrap()).unwrap();
    let e = replay::replay(&done.dir, &Opts { out: Some(done.dir.join("o3")), ..Default::default() }).err().unwrap();
    assert!(format!("{e:#}").contains("was not written with this"), "{e:#}");
    // no registry-run.json
    std::fs::write(done.dir.join("pools.json"), &pools).unwrap();
    std::fs::remove_file(done.dir.join("registry-run.json")).unwrap();
    let e = replay::replay(&done.dir, &Opts { out: Some(done.dir.join("o4")), ..Default::default() }).err().unwrap();
    assert!(format!("{e:#}").contains("registry-run.json"), "{e:#}");
    // no pools.json: the registry the run traded is unknown
    std::fs::remove_file(done.dir.join("pools.json")).unwrap();
    let e = replay::replay(&done.dir, &Opts { out: Some(done.dir.join("o5")), ..Default::default() }).err().unwrap();
    assert!(format!("{e:#}").contains("no pools.json"), "{e:#}");
    for o in ["o1", "o2", "o3", "o4", "o5"] { assert!(!done.dir.join(o).exists(), "{o}: a refused replay writes nothing"); }
}

/// pools.json (MEASUREMENT §4.29: a list, the toolkit's form) and registry-run.json round trip: the registry the run
/// traded (pools in index order, two pairs with each pair's pool order, seeds and ours) and the watch list with its roles
#[test]
fn pools_json_round_trips_the_registry_and_the_watch_list() {
    let mut reg = boot_registry(&["usdc.pump", "usdc.cpmm", "usdc.ammv4", "usdc.dlmm", "usdc.damm", "bolt.pump", "bolt.dlmm"]);
    assert_eq!(reg.pairs.len(), 2, "{}", reg.summary());
    reg.seeds.insert(reg.pools[1].pool);
    let extra = reg.extra_watch(true, &[], None);
    let mut roles_l = reg.watch_roles();
    roles_l.extend(extra.iter().copied());
    let roles = Roles::new(roles_l);
    let mut watch = reg.static_accounts();
    watch.extend(extra.iter().map(|e| e.0));
    let d = std::env::temp_dir().join(format!("arbx-pools-json-{}-{}", std::process::id(), crate::feeds::clock::real_ns()));
    std::fs::create_dir_all(&d).unwrap();
    let sha = replay::write_pools_json(&d, &reg, &watch, &roles).unwrap();
    // pools.json is the §4.29 list the toolkit reads (blockctx: `idx`, `pool`, `vault0`, `vault1`, `extra`)
    let list: Value = serde_json::from_slice(&std::fs::read(d.join("pools.json")).unwrap()).unwrap();
    let list = list.as_array().expect("pools.json is a list");
    assert_eq!(list.len(), reg.pools.len());
    for (i, p) in list.iter().enumerate() {
        for f in ["idx", "venue", "pool", "t0", "t1", "vault0", "vault1", "t0_prog", "t1_prog", "extra", "flag", "source", "tier", "pair_key"] { assert!(p.get(f).is_some(), "{f}: {p}"); }
        assert_eq!((p["idx"].as_u64(), p["pool"].as_str()), (Some(i as u64), Some(b58(&reg.pools[i].pool).as_str())));
    }
    assert_eq!(crate::provenance::sha256_hex(&std::fs::read(d.join("pools.json")).unwrap()), sha);
    let back = replay::read_pools_json(&d.join("pools.json")).unwrap();
    assert_eq!(back.reg.pools.len(), reg.pools.len());
    for (a, b) in back.reg.pools.iter().zip(&reg.pools) {
        assert_eq!((a.venue, a.pool, a.t0, a.t1, a.vault0, a.vault1, a.t0_prog, a.t1_prog, &a.extra, a.flag), (b.venue, b.pool, b.t0, b.t1, b.vault0, b.vault1, b.t0_prog, b.t1_prog, &b.extra, b.flag));
    }
    assert_eq!(back.reg.pairs, reg.pairs, "both pairs, each with its pool order");
    assert_eq!((&back.reg.seeds, back.reg.ours.len()), (&reg.seeds, reg.ours.len()));
    assert_eq!(back.watch.iter().map(|w| w.0).collect::<Vec<_>>(), watch);
    assert!(back.watch.iter().all(|(k, r)| roles.get(k) == Some(*r)));
    assert_eq!(back.reg.static_accounts(), reg.static_accounts());
    let _ = std::fs::remove_dir_all(&d);
}

/// The analysis toolkit's fixture (tools/arbx-report/tests/fixtures/wp09-run/): a recording made by this code (pools.json,
/// registry-run.json, accounts.bin), which the toolkit's test_wp09_recording.py reads. `ARBX_BLESS=1` writes it; without,
/// the fixture's pools.json must be what this code writes for the same run (the toolkit then reads the current format)
#[test]
fn the_toolkit_fixture_is_this_codes_recording() {
    let pools = ["usdc.pump", "usdc.cpmm", "usdc.ammv4"];
    let mut r = Rig::new("toolkit", Setup { pools: &pools, ..Default::default() });
    r.make_ready(T0);
    let a = r.meta("usdc.ammv4");
    let s2 = r.s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    let usdc_in = token_amount(&r.data(if sol_is_t0(&a) { &a.vault1 } else { &a.vault0 })) / 40;
    let w = swap(&r.chain, &a, !sol_is_t0(&a), usdc_in, s2, r.unix0).0;
    let s = r.sig("toolkit-trade");
    let wk: Vec<Pk> = w.iter().map(|x| x.0).collect();
    r.tx(shred_tx(s, [0x61; 32], &wk, &[*crate::venues::RAYAMMV4], vec![], s2, T0 + 9 * MS));
    let mut t = T0 + 10 * MS;
    for (k, d) in w { r.write(k, d, s2, Some(s), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    let dir = r.dir.clone();
    let done = r.finish_and_replay();
    assert!(done.evaluations().iter().any(|d| d["opp"].is_u64()));
    let fx = Path::new(env!("CARGO_MANIFEST_DIR")).join("tools/arbx-report/tests/fixtures/wp09-run");
    // registry-run.json without its writer's clock and build
    let strip = |p: &Path| -> Value { let mut v: Value = serde_json::from_slice(&std::fs::read(p).unwrap_or_default()).unwrap_or(Value::Null);
        if let Some(o) = v.as_object_mut() { o.remove("written_ns"); o.remove("producer"); } v };
    // accounts.bin as the toolkit reads it, decompressed (the repository ignores `*.zst`: run output)
    let accts: Vec<(String, Vec<u8>)> = rec::stream_files(&dir, "accounts").iter().map(|p| {
        let n = p.file_name().unwrap().to_string_lossy().trim_end_matches(".zst").to_string();
        (n, if p.extension().is_some_and(|e| e == "zst") { rec::decode_zst(p).unwrap().0 } else { std::fs::read(p).unwrap() })
    }).collect();
    let same = std::fs::read(fx.join("pools.json")).ok() == std::fs::read(dir.join("pools.json")).ok()
        && strip(&fx.join("registry-run.json")) == strip(&dir.join("registry-run.json"))
        && accts.iter().all(|(n, b)| std::fs::read(fx.join(n)).ok().as_ref() == Some(b));
    if std::env::var_os("ARBX_BLESS").is_some() && !same {
        let _ = std::fs::remove_dir_all(&fx);
        std::fs::create_dir_all(&fx).unwrap();
        for n in ["pools.json", "registry-run.json"] { std::fs::copy(dir.join(n), fx.join(n)).unwrap(); }
        for (n, b) in &accts { std::fs::write(fx.join(n), b).unwrap(); }
        std::fs::write(fx.join("expected.json"), serde_json::to_string_pretty(&json!({
            "_doc": "WP-09: a recording made by src/scenarios/harness.rs `the_toolkit_fixture_is_this_codes_recording` (ARBX_BLESS=1 rewrites it); read by test_wp09_recording.py",
            "trade_txn": sig58(&s), "traded_pool": b58(&a.pool), "pools": pools.iter().map(|n| b58(&r_pool(n))).collect::<Vec<_>>() })).unwrap() + "\n").unwrap();
    }
    if std::env::var_os("ARBX_BLESS").is_some() { return; }
    assert_eq!(std::fs::read(fx.join("pools.json")).unwrap_or_default(), std::fs::read(dir.join("pools.json")).unwrap(),
        "tools/arbx-report/tests/fixtures/wp09-run/pools.json is not what this code writes: ARBX_BLESS=1 cargo test --release --lib toolkit_fixture");
    assert_eq!(strip(&fx.join("registry-run.json")), strip(&dir.join("registry-run.json")), "registry-run.json: ARBX_BLESS=1 cargo test --release --lib toolkit_fixture");
}

/// a fixture pool's address
fn r_pool(name: &str) -> Pk { fixtures().pool(name).1 }
