// ===================================================================================================================
// dip19 tests (10-26 PKT; owner: "Huge Blunder, how did this happen, please fix it"). FRA run 22, window w51, mint 6ESztPpq…:
// fill A in slot 461415576, a same-slot stop-loss sold it AND CLOSED the token account, attempt B (sent at slot 576, deadline 577)
// passed its NON-idempotent ATA create in slot 577 and bought 11.8T tokens again; B was merged into the position whose sell was
// done, the Sold message closed it, B was never sold; realized counted A's buy only (-0.084 SOL vs about -0.48).
// Declared inside pslive.rs (the probe's state machine is private to it). The chain work is QUEUED (PsLive::for_test): every sell,
// read, close and realized lookup is a Cmd the test answers through on_msg as the chain did (no RPC, no send, no Telegram).
//  * w51 replayed with its real slots, indexes, signatures, amounts and curve states: B is not merged; it gets its own sell round
//    after A's; the pre-send sells never close the account; realized covers both buys and both sells; the account is closed only
//    after the last deadline + 2 slots, on a confirmed 0
//  * the close rules: never before quiet + 2, never with a window armed or a position open, never on Unknown / a balance (that is
//    an ORPHAN: a recovery sell, a critical alert); CLOSE_TRIES failed closes leave it to the run's end
//  * a FILLED window is re-checked (dip18 checked only unfilled windows with an unseen attempt): a fill the feed missed is an ORPHAN
//  * P&L over every buy and sell; the run's end list; golden: --presend-live off = dip18's bytes, a reactive sell still closes
// ===================================================================================================================
use super::*;

fn pk32(s: &str) -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }
fn sig64(s: &str) -> [u8; 64] { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }

/// the w51 window's real accounts and transactions (dip_r22.jsonl)
const MINT: &str = "6ESztPpqDyndKTfWZyhnuVEC2tC4QtVgVSAgXy6Bpump";
const WHALE: &str = "DxvwmNvYTUAPUQBtioT1SS3iL2Jj22b8qyPBk4WnE34B";
const SIG_TRIG: &str = "35eE9ByHoRVudQyJmnFymVx66ZTwBwHRgiHtqSV7cfdurGxwNxxwenSdhrnzSRdvF55irV8cRWdNtJi1Jarb2JTQ";
const SIG_N1: &str = "4iG5oZMzy67m8GxRH1vVQVXZmPmxhBnhe7fgttUihMfkQg7xPJG4Z8qVwK62nEX2U7gkX3KHZ2s7dgmiwpYVXern";
const SIG_A: &str = "4WT6Vdm5VpnGbzuqvdmxAt2xvHQN9UiP8ErwFvCtWMagb7CeQwoPx6EaHDTow5Nox4eDXGzQjY94GeLFxsoxJqVL";
const SIG_N3: &str = "4FQdczV5kUF4aAfDqTFV7KWbgXKAZdH3T1TYS3E3dKXtMKiAFvjixGvN4cipR5eQB4aSVi9yco2BKB7pnnbwmrXQ";
const SIG_B: &str = "465WMBNiK2gSrkxzJbJc9SZBjKwNoP4BMrZojthKTzUR99KXQd1FDsH6YHstm9P5BScsDDYtkYkGSG3G1oba7Sfd";
const SIG_SELL1: &str = "1cHN4wV5aZEe95FQbGfYv25LeAgTCzErjq8Vw6vPKcwvkWpGjmFDPDK8Evq5doKWfxPt1T1XTcrcWv9ETMVreDu";
/// the slot of fill A, the stop-loss and A's sell (B landed in N + 1)
const N: u64 = 461_415_576;
/// A's real buy delta and the realized dip18 reported (-0.084 SOL: A's buy + its sell only); the sell's delta follows
const A_DELTA: i64 = -401_718_960;
const DIP18_REALIZED: i64 = -84_172_151;
const SELL1_DELTA: i64 = DIP18_REALIZED - A_DELTA;

/// the test wallet: the payer of the existing wiring test (the failed-tx side channel watches one payer per process)
const USER: Pk = [0x5Au8; 32];

fn arr(slot: u64, sig: [u8; 64], payer: Pk, ok: bool, exec: Option<arbx::feeds::ExecInfo>, t_rx: u64) -> arbx::feeds::Arrival {
    let tx = arbx::tx::Tx { sig, keys: vec![payer], ..Default::default() };
    arbx::feeds::Arrival { feed: 0, slot, t_rx, t_decoded: t_rx, executed: Some(ok), tx, poh: None, raw: arbx::feeds::RawTx::None, exec: exec.map(Arc::new) }
}

fn recs(orx: &crossbeam_channel::Receiver<Out>) -> Vec<serde_json::Value> { orx.try_iter().filter_map(|o| match o { Out::Rec(v) => Some(v), Out::Line(_) => None }).collect() }

/// the probe as FRA run 22 ran it (0.4 SOL, 4 attempts a slot, TP +10% / SL -20%, exit 2 slots), its chain work queued
fn probe() -> PsLive {
    let a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    let cfg = Cfg::from_argv(&a, &arbx::presend::Params::default(), true, 1_000_000_000).unwrap().unwrap();
    assert_eq!((cfg.spend, cfg.k, cfg.deadline_slots, cfg.exit_slots, cfg.tp, cfg.sl), (400_000_000, 4, 1, 2, 0.10, 0.20));
    let (p, _atx, _orx) = PsLive::for_test(cfg, USER);
    p
}

/// one trade tx of someone else (or ours) on the mint, through on_arrival + on_exec as the event loop calls them
#[allow(clippy::too_many_arguments)]
fn trade(p: &mut PsLive, slot: u64, idx: u64, sig: [u8; 64], user: Pk, buy: bool, sol: u64, tok: u64, vsol: u64, vtok: u64, fee: u64, launch: &Launch) {
    let x = arbx::feeds::ExecInfo { index: idx, fee, ok: true, trades: vec![arbx::dip::TradeEvent { mint: launch.mint, sol, tok, buy, user, vsol, vtok, fbps: 95, cbps: 30 }],
        creates: Vec::new(), mayhem: false };
    let a = arr(slot, sig, user, true, Some(x.clone()), slot * 1_000_000 + idx);
    let l = launch.clone();
    p.on_arrival(&a, slot);
    p.on_exec(&a, &x, slot, move |m: &Pk| (*m == l.mint).then(|| l.clone()), &|_| false, None);
}

/// one of our attempts failed on chain (`err`: its bincode error), seen through the failed-tx side channel
fn failed(p: &mut PsLive, slot: u64, idx: u64, sig: [u8; 64], err: &[u8]) {
    arbx::feeds::own_fail_note(&sig, Some(&USER[..]), slot, idx, p.cfg.fail_fee(), err);
    p.on_arrival(&arr(slot, sig, USER, false, None, slot * 1_000_000 + idx), slot);
}

/// an attempt as the sender registers it (before its write)
fn att(w: u64, n: u32, mint: Pk, sig: [u8; 64], slot: u64, client: &str) -> Att {
    Att { w, n, mint, sig, tag: pl::PS_TAG | (0xD19 << 8) | n as u64, path: "helius-ps".into(), client: client.into(), slot, deadline: slot + 1, lim: 0.000041, min_out: 9_524_401_719_354,
        p_sign: 0.0000466, sign_pos: (slot, 34, 0), t_send: slot * 1_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) }, tip: 200_000, wst: "written" }
}

fn sold(c: Option<u64>, sigs: &[&str], qty: u64) -> SellOut {
    SellOut { sold_at: c, sigs: sigs.iter().map(|s| (s.to_string(), true, 1_200_000)).collect(), last: None, attempts: sigs.len() as u32, last_qty: (qty, true), first_send_us: None }
}

/// the create (N - 2) and the whale's buy (N - 1, idx 34: 2.67 SOL, 6.16% of the supply) -> window w1 armed; the four attempts of
/// w51 registered as the sender did (n 1-3 at slot N - 1, deadline N; n 4 at slot N, deadline N + 1, sent 35 ms BEFORE A's fill was seen)
fn arm_w51(p: &mut PsLive, atx: &crossbeam_channel::Sender<Att>, launch: &Launch) {
    let creator = [0xC1u8; 32];
    let x = arbx::feeds::ExecInfo { index: 7, fee: 5_000, ok: true, trades: Vec::new(), mayhem: false,
        creates: vec![arbx::dip::CreateEvent { mint: launch.mint, bonding_curve: launch.bonding_curve, user: creator, creator }] };
    let a = arr(N - 2, [0xC7u8; 64], creator, true, Some(x.clone()), (N - 2) * 1_000_000);
    let l = launch.clone();
    p.on_exec(&a, &x, N - 2, move |m: &Pk| (*m == l.mint).then(|| l.clone()), &|_| false, None);
    trade(p, N - 1, 34, sig64(SIG_TRIG), pk32(WHALE), true, 2_666_666_666, 61_580_021_739_287, 38_692_888_509, 831_935_821_811_615, 5_000, launch);
    assert_eq!(p.armed.get(&launch.mint), Some(&1), "w51's trigger arms the window: {:?}", p.st.skips);
    for (n, s, slot, client) in [(1, SIG_N1, N - 1, "AgaveBam"), (2, SIG_A, N - 1, "AgaveBam"), (3, SIG_N3, N - 1, "AgaveBam"), (4, SIG_B, N, "HarmonicAgave")] {
        atx.send(att(1, n, launch.mint, sig64(s), slot, client)).unwrap();
    }
    p.drain_atts();
    assert_eq!((p.wins[&1].sent, p.last_deadline[&launch.mint], p.quiet[&launch.mint]), (4, N + 1, N + 1));
}

/// THE REGRESSION: w51 exactly as FRA run 22 saw it, in the event loop's order (the run-22 log: fill A, the stop-loss exit, A's sell
/// landed, fill B, then the Sold message). dip18: B merged into the sold position, never sold, realized = A only. dip19: the pre-send
/// sell keeps the account (no close instruction: B's create would fail, the guard); B (had it landed anyway) is NOT merged: it is the
/// position's second round, sold on its own once A's sell is done; realized counts both buys and both sells; the account is closed
/// only after B's deadline + 2 slots, on a confirmed 0
#[test]
fn dip19_w51_regression_fill_after_exit_gets_its_own_sell() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let inflight0 = ACCT.inflight.load(Ordering::SeqCst);
    let cfg = probe().cfg.clone();
    let (mut p, atx, orx) = PsLive::for_test(cfg, USER);
    let mint = pk32(MINT);
    let launch = snipe_build::launch_from_target(mint, [0xC1u8; 32]);
    arm_w51(&mut p, &atx, &launch);
    let other = |s: &str| pk32(s);
    // ---- slot N: n1 6042, FILL A (idx 192), n3 ata_exists (the guard inside the slot), three trades, the stop-loss at idx 253
    failed(&mut p, N, 150, sig64(SIG_N1), &[8, 0, 0, 0, 5, 25, 0, 0, 0, 0x9a, 0x17, 0, 0]);
    trade(&mut p, N, 192, sig64(SIG_A), USER, true, 395_061_727, 9_803_077_983_112, 36_215_421_019, 888_847_874_680_162, 5_120, &launch);
    assert!(p.pos.contains_key(&mint) && p.armed.is_empty(), "A opens the position, the window is disarmed");
    assert_eq!(p.atas[&mint].st, AtaSt::Held);
    failed(&mut p, N, 200, sig64(SIG_N3), &[8, 0, 0, 0, 3, 49, 0, 0, 0]);
    trade(&mut p, N, 203, [0x03; 64], other("747LPjmjoW2ACQ4ZuHToixEq46JQ1tsK23GqVTbHt7zX"), false, 2_513_329_104, 66_285_714_223_523, 33_702_091_915, 955_133_588_903_685, 5_000, &launch);
    trade(&mut p, N, 244, [0x04; 64], other("Bpv3GFKY93Q5c5b2q6X2zCKayRYi3aKpqZteWonxnixD"), true, 395_061_727, 11_066_516_817_378, 34_097_153_642, 944_067_072_086_307, 5_000, &launch);
    assert!(p.pos[&mint].exit.is_none() && p.take_cmds().iter().all(|c| !matches!(c, Cmd::Sell { .. })), "x0.85 / x0.86: no exit yet");
    trade(&mut p, N, 253, [0x05; 64], other("DGj4uaCV1edTgmMtw1TpGnYYHmcc566Ta1YP88quJmkm"), false, 1_426_077_186, 41_208_085_569_908, 32_671_076_456, 985_275_157_656_215, 5_000, &launch);
    // the stop-loss, held 0 slots, value x0.795 (the run's): round 1 sells A's 9.80T tokens and KEEPS the account (dip18 closed it)
    let x = p.pos[&mint].exit.expect("stop-loss");
    assert_eq!((x.0, x.1), ("stop-loss", N));
    assert!((x.2 - 0.7946).abs() < 0.001, "{}", x.2);
    let c = p.take_cmds();
    assert_eq!(c.len(), 1, "{c:?}");
    let Cmd::Sell { pid, round, known, guess, land_slot, read_first, keep_ata, launch: ref sl, derived, .. } = c[0] else { panic!("{c:?}") };
    assert_eq!((round, known, guess, land_slot, read_first, keep_ata, derived), (1, Some(9_803_077_983_112), 9_803_077_983_112, N, false, true, false));
    assert_eq!(sl, &launch);
    // the sell sell_until_zero sends for it (sell_exact_ixs): NO close of the token account; dip18's (keep_ata false) ended with it
    let (cu, price) = (sell_cu_limit(), 5_000_000);
    let keep = sell_exact_ixs(USER, &launch, 9_803_077_983_112, cu, price, false, keep_ata);
    let old = snipe_build::sell_message_ixs(USER, &launch, 9_803_077_983_112, 0, cu, price, false);
    let is_close = |ix: &build::Ix| ix.data == [9] && (ix.program == *pda::TOKEN_2022 || ix.program == *pda::TOKEN_PROGRAM);
    assert!(keep.iter().all(|ix| !is_close(ix)), "the pre-send sell must not close the account (B's NON-idempotent create is the guard)");
    assert!(is_close(old.last().unwrap()) && old.last().unwrap().accounts[0].key == pda::ata(&USER, &mint, &pda::TOKEN_2022), "dip18's sell closed it");
    assert_eq!(keep.len() + 1, old.len());
    assert!(keep.iter().zip(&old).all(|(a, b)| a.program == b.program && a.data == b.data && a.accounts == b.accounts), "the same sell otherwise");
    // ---- A's sell lands (idx 279), one more buyer (304)
    trade(&mut p, N, 279, sig64(SIG_SELL1), USER, false, 321_861_235, 9_803_077_983_112, 32_349_215_221, 995_078_235_639_327, 605_000, &launch);
    trade(&mut p, N, 304, [0x06; 64], other("DiqYk5RDxWgqDjnhcsefUyc3DY12T9vbhvjWQMLhc3j4"), true, 246_913_579, 7_537_653_598_889, 32_596_128_800, 987_540_582_040_438, 5_000, &launch);
    // ---- slot N + 1: FILL B (idx 33): the position's exit has started: NOT merged (dip18: "FILL MERGED" into a done sell)
    trade(&mut p, N + 1, 28, [0x07; 64], other("FpDCNLWHmyu7yL5BMcJLsL6UZvAx9YxAubT4NBepoTaY"), true, 49_381, 1_496_026_732, 32_596_178_181, 987_539_086_013_706, 5_000, &launch);
    trade(&mut p, N + 1, 33, sig64(SIG_B), USER, true, 395_061_727, 11_825_529_956_219, 32_991_239_908, 975_713_556_057_487, 5_120, &launch);
    {
        let pp = &p.pos[&mint];
        assert_eq!((pp.pid, pp.round, pp.selling, pp.merged, pp.late, pp.buys.len()), (pid, 1, true, 0, 1, 2));
        assert_eq!(pp.tokens, 9_803_077_983_112, "round 1 still sells A's tokens only");
        assert_eq!((pp.buys[1].sig.as_str(), pp.buys[1].round, pp.buys[1].slot), (SIG_B, 0, N + 1), "B waits for its own round");
    }
    let c = p.take_cmds();
    assert!(c.iter().all(|c| !matches!(c, Cmd::Sell { .. })), "no second sell while round 1 runs: {c:?}");
    assert!(c.iter().any(|c| matches!(c, Cmd::Alert { level: arbx::alerts::Level::Warning, .. })), "the late fill is told");
    // ---- A's Sold message: confirmed 0 at slot N (the run's "SOLD ... at slot 461415576"), BEFORE B's landing (N + 1): round 2
    p.on_msg(PsMsg::Sold(mint, pid, 1, sold(Some(N), &[SIG_SELL1], 9_803_077_983_112)), &|_| false);
    assert!(p.pos.contains_key(&mint), "the position stays open: B is not sold yet (dip18 closed it here)");
    let c = p.take_cmds();
    assert_eq!(c.len(), 1, "{c:?}");
    let Cmd::Sell { pid: pid2, round, known, land_slot, read_first, keep_ata, .. } = c[0] else { panic!("{c:?}") };
    assert_eq!((pid2, round, known, land_slot, read_first, keep_ata), (pid, 2, Some(11_825_529_956_219), N + 1, false, true), "B's own sell, at once (no read first: M4-1)");
    assert_eq!(p.pos[&mint].buys.iter().map(|b| b.round).collect::<Vec<_>>(), vec![1, 2]);
    // a stale answer (round 1 again) changes nothing
    p.on_msg(PsMsg::Sold(mint, pid, 1, sold(Some(N), &[], 0)), &|_| false);
    assert!(p.pos[&mint].selling && p.take_cmds().is_empty());
    // ---- B's sell lands (N + 3) and its round is confirmed empty (N + 3): the position closes with BOTH buys and BOTH sells
    trade(&mut p, N + 3, 40, [0x5E; 64], USER, false, 390_000_000, 11_825_529_956_219, 32_601_239_908, 987_539_086_013_706, 605_000, &launch);
    p.on_msg(PsMsg::Sold(mint, pid, 2, sold(Some(N + 3), &["SELL2"], 11_825_529_956_219)), &|_| false);
    assert!(p.pos.is_empty() && !p.sh.pause_pos.load(Ordering::Relaxed), "B sold: the position is done");
    let c = p.take_cmds();
    let Some(Cmd::Realized { buys, sells, .. }) = c.iter().find(|c| matches!(c, Cmd::Realized { .. })) else { panic!("{c:?}") };
    assert_eq!(buys.iter().map(|b| b.0.as_str()).collect::<Vec<_>>(), vec![SIG_A, SIG_B], "realized reads EVERY buy");
    assert_eq!(sells.iter().map(|s| s.0.as_str()).collect::<Vec<_>>(), vec![SIG_SELL1, "SELL2"], "and every sell of every round");
    // the realized sum with the run's real deltas (A, its sell) and B's (B paid as A did; its sell's delta made up): dip18 = A + sell 1
    let b = |d: i64| Some((d, 5_120u64, true));
    assert_eq!(pnl_of(&[(b(A_DELTA), 0)], &[b(SELL1_DELTA)]).0, DIP18_REALIZED, "dip18's number: A's buy + its sell only");
    // at the moment dip18 reported -0.084 (B bought, nothing sold of it), every buy counted gives the real loss: about -0.486 SOL
    let held = pnl_of(&[(b(A_DELTA), 0), (b(A_DELTA), 0)], &[b(SELL1_DELTA)]).0;
    assert_eq!(held, DIP18_REALIZED + A_DELTA);
    assert!((-0.49e9..-0.48e9).contains(&(held as f64)), "{held}");
    // and once B's own sell is done: both buys, both sells
    let (pnl, nb, ns) = pnl_of(&[(b(A_DELTA), 0), (b(A_DELTA), 0)], &[b(SELL1_DELTA), b(380_000_000)]);
    assert_eq!((pnl, nb, ns), (A_DELTA + SELL1_DELTA + A_DELTA + 380_000_000, 2, 2));
    assert_eq!(pnl - DIP18_REALIZED, A_DELTA + 380_000_000, "dip18 missed exactly B's buy and B's sell");
    // ---- the records
    let r = recs(&orx);
    let ev = |k: &str| r.iter().filter(|x| x["ev"] == k).cloned().collect::<Vec<_>>();
    let fills = ev("presend_live_fill");
    assert_eq!(fills.iter().map(|x| (x["sig"].as_str().unwrap().to_string(), x["after_exit"].as_bool().unwrap())).collect::<Vec<_>>(), vec![(SIG_A.to_string(), false), (SIG_B.to_string(), true)]);
    assert_eq!(ev("presend_live_late_fill").len(), 1);
    assert_eq!(ev("presend_live_exit").iter().map(|x| (x["why"].as_str().unwrap().to_string(), x["round"].as_u64().unwrap())).collect::<Vec<_>>(),
        vec![("stop-loss".to_string(), 1), ("follow-up".to_string(), 2)]);
    let close = ev("presend_live_close");
    assert_eq!(close.len(), 1);
    let cl = &close[0];
    assert_eq!((cl["result"].as_str(), cl["rounds"].as_u64(), cl["merged"].as_u64(), cl["late"].as_u64()), (Some("sold"), Some(2), Some(0), Some(1)));
    assert_eq!(cl["buy_sigs"], serde_json::json!([SIG_A, SIG_B]));
    assert_eq!(cl["buy_sig"], SIG_A, "dip18's field: the first buy");
    assert_eq!(cl["sell_sigs"].as_array().unwrap().len(), 2);
    assert_eq!(cl["tokens"].as_u64(), Some(9_803_077_983_112 + 11_825_529_956_219));
    assert_eq!(cl["sol_in_curve"].as_u64(), Some(2 * 395_061_727));
    assert_eq!(cl["sol_out_curve"].as_u64(), Some(321_861_235 + 390_000_000));
    assert_eq!(cl["curve_pnl"].as_i64(), Some(321_861_235 + 390_000_000 - 2 * 395_061_727), "the curve P&L over both buys and both sells");
    assert_eq!(cl["sell_land"][0].as_u64(), Some(N + 3), "dip18's field: the last sell landing");
    let lands: Vec<String> = ev("presend_attempt_land").iter().map(|x| x["res"].as_str().unwrap().to_string()).collect();
    let mut want = vec!["6042", "ok", "ata_exists", "ok"].into_iter().map(String::from).collect::<Vec<_>>();
    let mut got = lands.clone();
    // (the landing records are written once their tape is complete: their order is the tick's)
    want.sort(); got.sort();
    assert_eq!(got, want, "{lands:?}");
    // ---- the account: kept open; no read before B's deadline (N + 1) + 2 slots; at N + 4 the window's check and the close's read
    assert_eq!(p.atas[&mint].st, AtaSt::Idle);
    p.tick(N + 3, None);
    assert!(p.take_cmds().is_empty(), "nothing at the quiet slot + 2");
    p.tick(N + 4, None);
    let c = p.take_cmds();
    assert!(c.iter().any(|c| matches!(c, Cmd::Read { why: Why::Window(1), min_slot, .. } if *min_slot == N + 1)), "the FILLED window is re-checked: {c:?}");
    assert!(c.iter().any(|c| matches!(c, Cmd::Read { why: Why::Close, min_slot, .. } if *min_slot == N + 3)), "{c:?}");
    assert_eq!(p.checks, 2);
    p.on_msg(PsMsg::Read(mint, Why::Window(1), N + 1, 1, crate::Tok::Amount(0, N + 4)), &|_| false);
    p.on_msg(PsMsg::Read(mint, Why::Close, N + 3, 1, crate::Tok::Amount(0, N + 4)), &|_| false);
    let c = p.take_cmds();
    assert!(matches!(c.as_slice(), [Cmd::Close { mint: m }] if *m == mint), "a confirmed 0: the close (rent back): {c:?}");
    p.on_msg(PsMsg::Closed(mint, "CLOSE1".into(), Some(N + 5), String::new()), &|_| false);
    assert!(p.atas.is_empty() && p.checks == 0 && p.idle());
    assert_eq!((p.st.fills, p.st.after_exit, p.st.follow_ups, p.st.closed, p.st.orphans, p.st.ata_closed), (2, 1, 1, 1, 0, 1));
    // the run's end would read the mint (it was filled)
    assert_eq!(p.end_list().iter().map(|x| (x.0, x.1)).collect::<Vec<_>>(), vec![(mint, N + 1)]);
    drop(p);
    assert_eq!(ACCT.inflight.load(Ordering::SeqCst), inflight0, "the position's accounting released");
}

/// the same w51 timeline, but the round-1 sell's confirmed-0 read came AFTER B landed (its context slot >= N + 1): round 1's sell loop
/// sold B's tokens too (it sells the confirmed balance until 0), so no second round: one sell round covers both buys, realized still
/// lists both buys
#[test]
fn dip19_fill_before_the_rounds_confirmed_zero_is_covered_by_it() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, atx, _orx) = PsLive::for_test(probe().cfg.clone(), USER);
    let mint = pk32(MINT);
    let launch = snipe_build::launch_from_target(mint, [0xC1u8; 32]);
    arm_w51(&mut p, &atx, &launch);
    trade(&mut p, N, 192, sig64(SIG_A), USER, true, 395_061_727, 9_803_077_983_112, 36_215_421_019, 888_847_874_680_162, 5_120, &launch);
    trade(&mut p, N, 253, [0x05; 64], [0x99; 32], false, 1_426_077_186, 41_208_085_569_908, 32_671_076_456, 985_275_157_656_215, 5_000, &launch);
    let pid = p.pos[&mint].pid;
    trade(&mut p, N + 1, 33, sig64(SIG_B), USER, true, 395_061_727, 11_825_529_956_219, 32_991_239_908, 975_713_556_057_487, 5_120, &launch);
    let _ = p.take_cmds();
    p.on_msg(PsMsg::Sold(mint, pid, 1, sold(Some(N + 2), &[SIG_SELL1, "SELL1B"], 11_825_529_956_219)), &|_| false);
    assert!(p.pos.is_empty(), "B landed before the confirmed 0 at N + 2: sold in round 1");
    let c = p.take_cmds();
    let Some(Cmd::Realized { buys, sells, .. }) = c.iter().find(|c| matches!(c, Cmd::Realized { .. })) else { panic!("{c:?}") };
    assert_eq!((buys.len(), sells.len()), (2, 2));
    assert!(c.iter().all(|c| !matches!(c, Cmd::Sell { .. })), "no second round: {c:?}");
}

/// THE CLOSE RULES of a kept-open account: only once no attempt of the mint can land (its quiet slot: the last deadline, or the
/// sender's slot at the disarm + the deadline slots) + 2, with no window armed and no position on it, and only on a CONFIRMED 0;
/// Unknown is read again later (never a close), a balance is an ORPHAN (a recovery sell, keep_ata, a critical alert, no close),
/// a failed close is retried CLOSE_TRIES times then left to the run's end
#[test]
fn dip19_ata_close_only_after_quiet_and_on_confirmed_zero() {
    // the predicate
    assert!(!close_due(100, 98, false, false) && close_due(101, 98, false, false), "past the quiet slot + 2 only");
    assert!(!close_due(1_000, 98, true, false), "never with a window armed on the mint");
    assert!(!close_due(1_000, 98, false, true), "never with a position open on it");
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let inflight0 = ACCT.inflight.load(Ordering::SeqCst);
    let (mut p, atx, orx) = PsLive::for_test(probe().cfg.clone(), USER);
    let mint = pk32(MINT);
    let launch = snipe_build::launch_from_target(mint, [0xC1u8; 32]);
    arm_w51(&mut p, &atx, &launch);
    trade(&mut p, N, 192, sig64(SIG_A), USER, true, 395_061_727, 9_803_077_983_112, 36_215_421_019, 888_847_874_680_162, 5_120, &launch);
    // the disarm's bound: the sender's slot then (N) + 1 deadline slot
    assert_eq!((p.wins[&1].quiet, p.quiet[&mint]), (N + 1, N + 1));
    // the position is open: no read at any slot
    for s in [N + 4, N + 10] { p.tick(s, None); assert!(p.take_cmds().iter().all(|c| !matches!(c, Cmd::Read { why: Why::Close, .. })), "position open at {s}"); }
    let pid = p.pos[&mint].pid;
    let _ = p.take_cmds();
    // its exit (time-limit at N + 2 already passed in the ticks above) and its sell
    assert!(p.pos[&mint].exit.is_some());
    p.on_msg(PsMsg::Sold(mint, pid, 1, sold(Some(N + 10), &["S1"], 9_803_077_983_112)), &|_| false);
    assert_eq!(p.atas[&mint].st, AtaSt::Idle);
    let take_close_reads = |p: &mut PsLive| p.take_cmds().into_iter().filter(|c| matches!(c, Cmd::Read { why: Why::Close, .. })).count();
    // a window armed on the mint (forced: the rule itself): no read
    p.armed.insert(mint, 99);
    p.tick(N + 11, None);
    assert_eq!(take_close_reads(&mut p), 0, "a window armed on the mint");
    p.armed.remove(&mint);
    // a NEW trigger on the mint while its account is open: not armed (every attempt would fail at its ATA create); the sell's 300 ms
    // margin (blocked_position) is over. on_exec's own tick then reads the account (it is due): once
    p.free_at.remove(&mint);
    let x = arbx::feeds::ExecInfo { index: 9, fee: 5_000, ok: true, mayhem: false, creates: Vec::new(),
        trades: vec![arbx::dip::TradeEvent { mint, sol: 3_000_000_000, tok: 70_000_000_000_000, buy: true, user: [0x77; 32], vsol: 36_000_000_000, vtok: 890_000_000_000_000, fbps: 95, cbps: 30 }] };
    let l = launch.clone();
    p.on_exec(&arr(N + 12, [0x77; 64], [0x77; 32], true, Some(x.clone()), 1), &x, N + 12, move |m: &Pk| (*m == l.mint).then(|| l.clone()), &|_| false, None);
    assert_eq!(p.st.skips.get("blocked_ata_open"), Some(&1), "{:?}", p.st.skips);
    assert!(p.armed.is_empty());
    assert_eq!(take_close_reads(&mut p), 1);
    p.tick(N + 12, None);
    assert_eq!(take_close_reads(&mut p), 0, "one read at a time");
    // Unknown: never a close; read again after its wait
    p.on_msg(PsMsg::Read(mint, Why::Close, N + 10, 1, crate::Tok::Unknown), &|_| false);
    assert!(p.take_cmds().is_empty());
    assert_eq!(p.atas[&mint].st, AtaSt::Idle);
    p.tick(N + 13, None);
    assert_eq!(take_close_reads(&mut p), 0, "not before its wait (2 s)");
    p.atas.get_mut(&mint).unwrap().not_before = None;
    p.tick(N + 13, None);
    assert_eq!(take_close_reads(&mut p), 1);
    // a 0 while the reactive bot holds the mint: later, no close
    p.on_msg(PsMsg::Read(mint, Why::Close, N + 10, 1, crate::Tok::Amount(0, N + 13)), &|m| *m == mint);
    assert!(p.take_cmds().is_empty() && p.atas[&mint].st == AtaSt::Idle);
    p.atas.get_mut(&mint).unwrap().not_before = None;
    p.tick(N + 14, None);
    assert_eq!(take_close_reads(&mut p), 1);
    // A BALANCE: an ORPHAN (a fill that landed after the last confirmed 0 and the feed missed): a recovery sell, keep_ata, critical
    p.on_msg(PsMsg::Read(mint, Why::Close, N + 10, 1, crate::Tok::Amount(5_000_000, N + 14)), &|_| false);
    let c = p.take_cmds();
    assert!(c.iter().all(|c| !matches!(c, Cmd::Close { .. })), "never a close on a balance: {c:?}");
    assert!(c.iter().any(|c| matches!(c, Cmd::Sell { known: Some(5_000_000), keep_ata: true, land_slot, .. } if *land_slot == N + 14)), "{c:?}");
    assert!(c.iter().any(|c| matches!(c, Cmd::Alert { level: arbx::alerts::Level::Critical, title } if title.contains("ORPHAN"))), "{c:?}");
    assert_eq!((p.st.orphans, p.atas[&mint].st), (1, AtaSt::Held));
    let o = recs(&orx).into_iter().filter(|x| x["ev"] == "presend_live_orphan").collect::<Vec<_>>();
    assert_eq!((o.len(), o[0]["tokens"].as_u64(), o[0]["from"].as_str()), (1, Some(5_000_000), Some("close_read")));
    // its sell done: Idle again; the read; a 0: the close; it fails CLOSE_TRIES times: left to the run's end
    let pid2 = p.pos[&mint].pid;
    p.on_msg(PsMsg::Sold(mint, pid2, 1, sold(Some(N + 16), &["S2"], 5_000_000)), &|_| false);
    let _ = p.take_cmds();
    for k in 1..=CLOSE_TRIES {
        p.atas.get_mut(&mint).unwrap().not_before = None;
        p.tick(N + 20 + k as u64, None);
        assert_eq!(take_close_reads(&mut p), 1);
        p.on_msg(PsMsg::Read(mint, Why::Close, N + 16, 1, crate::Tok::Amount(0, N + 20 + k as u64)), &|_| false);
        assert!(matches!(p.take_cmds().as_slice(), [Cmd::Close { .. }]));
        p.on_msg(PsMsg::Closed(mint, format!("C{k}"), None, "not seen".into()), &|_| false);
    }
    assert_eq!(p.atas[&mint].st, AtaSt::GaveUp);
    p.atas.get_mut(&mint).unwrap().not_before = None;
    p.tick(N + 40, None);
    assert_eq!(take_close_reads(&mut p), 0, "left to the run's end");
    assert!(p.end_list().iter().any(|x| x.0 == mint), "the run's end reads it");
    drop(p);
    assert_eq!(ACCT.inflight.load(Ordering::SeqCst), inflight0);
}

/// a FILLED window is re-checked once it settles (dip18: only an unfilled one with an attempt never seen): a fill the feed did not show
/// (here w51's B with no TradeEvent) is found by the window's confirmed read and sold (ORPHAN); Unknown is read again, never as 0
#[test]
fn dip19_filled_window_rechecked_orphan_found_and_sold() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let inflight0 = ACCT.inflight.load(Ordering::SeqCst);
    let (mut p, atx, orx) = PsLive::for_test(probe().cfg.clone(), USER);
    let mint = pk32(MINT);
    let launch = snipe_build::launch_from_target(mint, [0xC1u8; 32]);
    arm_w51(&mut p, &atx, &launch);
    trade(&mut p, N, 192, sig64(SIG_A), USER, true, 395_061_727, 9_803_077_983_112, 36_215_421_019, 888_847_874_680_162, 5_120, &launch);
    trade(&mut p, N, 253, [0x05; 64], [0x99; 32], false, 1_426_077_186, 41_208_085_569_908, 32_671_076_456, 985_275_157_656_215, 5_000, &launch);
    let pid = p.pos[&mint].pid;
    let _ = p.take_cmds();
    p.on_msg(PsMsg::Sold(mint, pid, 1, sold(Some(N), &[SIG_SELL1], 9_803_077_983_112)), &|_| false);
    assert!(p.pos.is_empty());
    // B landed (N + 1) but the feed never showed it: its attempt resolves unseen
    p.tick(N + 5, None);
    let c = p.take_cmds();
    let reads: Vec<&Cmd> = c.iter().filter(|c| matches!(c, Cmd::Read { why: Why::Window(1), .. })).collect();
    assert_eq!(reads.len(), 1, "the filled window w1 is read: {c:?}");
    // the close's read was issued too (quiet N + 1 + 2 < N + 5): it races the window's; the window's answer comes first: unreadable
    p.on_msg(PsMsg::Read(mint, Why::Window(1), N + 1, 1, crate::Tok::Unknown), &|_| false);
    assert!(p.pos.is_empty() && p.retry.len() == 1, "never read as 0: again later");
    assert!(p.end_list().iter().any(|x| x.0 == mint));
    p.retry[0].0 = Instant::now();
    p.tick(N + 6, None);
    let c = p.take_cmds();
    assert!(c.iter().any(|c| matches!(c, Cmd::Read { why: Why::Window(1), n: 2, .. })), "{c:?}");
    // B's 11.8T tokens: no position open on the mint: ORPHAN, sold now (the account kept open)
    p.on_msg(PsMsg::Read(mint, Why::Window(1), N + 1, 2, crate::Tok::Amount(11_825_529_956_219, N + 6)), &|_| false);
    let c = p.take_cmds();
    assert!(c.iter().any(|c| matches!(c, Cmd::Sell { known: Some(11_825_529_956_219), keep_ata: true, round: 1, .. })), "{c:?}");
    assert!(c.iter().any(|c| matches!(c, Cmd::Alert { level: arbx::alerts::Level::Critical, .. })));
    assert_eq!((p.st.orphans, p.st.held_found), (1, 1));
    // the feed shows B's fill after all (it lagged): it is the balance the read found, not a second buy
    let b = |p: &PsLive| p.pos[&mint].buys.clone();
    assert_eq!(b(&p).len(), 1);
    trade(&mut p, N + 1, 33, sig64(SIG_B), USER, true, 395_061_727, 11_825_529_956_219, 32_991_239_908, 975_713_556_057_487, 5_120, &launch);
    assert_eq!(b(&p).len(), 1, "the late feed fill is the read's buy");
    assert_eq!((b(&p)[0].sig.as_str(), b(&p)[0].via), (SIG_B, "rpc_read+feed"));
    let r = recs(&orx);
    assert!(r.iter().any(|x| x["ev"] == "presend_live_orphan" && x["from"] == "window_read" && x["w"] == 1));
    drop(p);
    assert_eq!(ACCT.inflight.load(Ordering::SeqCst), inflight0);
}

/// UNSOLD: the background retry keeps the account (keep_ata), holds it (no close, no orphan, no new window) until it reports back
#[test]
fn dip19_unsold_keeps_the_account_until_its_retry_ends() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, atx, _orx) = PsLive::for_test(probe().cfg.clone(), USER);
    let mint = pk32(MINT);
    let launch = snipe_build::launch_from_target(mint, [0xC1u8; 32]);
    arm_w51(&mut p, &atx, &launch);
    trade(&mut p, N, 192, sig64(SIG_A), USER, true, 395_061_727, 9_803_077_983_112, 36_215_421_019, 888_847_874_680_162, 5_120, &launch);
    trade(&mut p, N, 253, [0x05; 64], [0x99; 32], false, 1_426_077_186, 41_208_085_569_908, 32_671_076_456, 985_275_157_656_215, 5_000, &launch);
    let pid = p.pos[&mint].pid;
    let _ = p.take_cmds();
    p.on_msg(PsMsg::Sold(mint, pid, 1, sold(None, &["S1"], 9_803_077_983_112)), &|_| false);
    let c = p.take_cmds();
    assert!(c.iter().any(|c| matches!(c, Cmd::Unsold { last_qty: (9_803_077_983_112, true), .. })), "{c:?}");
    assert_eq!((p.st.unsold, p.atas[&mint].st), (1, AtaSt::Held));
    p.tick(N + 10, None);
    let c = p.take_cmds();
    assert!(c.iter().all(|c| !matches!(c, Cmd::Read { why: Why::Close, .. })), "no close while its retry holds it");
    // the window's read sees the tokens: the retry sells them (not an orphan)
    p.on_msg(PsMsg::Read(mint, Why::Window(1), N + 1, 1, crate::Tok::Amount(9_803_077_983_112, N + 10)), &|_| false);
    assert!(p.pos.is_empty() && p.st.orphans == 0);
    p.on_msg(PsMsg::UnsoldDone(mint, true), &|_| false);
    assert_eq!(p.atas[&mint].st, AtaSt::Idle, "sold: the account is closed as any");
}

/// the P&L of a position: every buy (a buy whose tx is not found counts at minus its cost estimate), every sell (not found: 0);
/// the run's end: what it does with each read
#[test]
fn dip19_pnl_and_end_actions() {
    let f = |d: i64| Some((d, 5_000u64, true));
    assert_eq!(pnl_of(&[(f(-400), 0), (f(-401), 0)], &[f(300), f(380)]), (-400 - 401 + 300 + 380, 2, 2));
    assert_eq!(pnl_of(&[(f(-400), 0), (None, 402_279_200)], &[f(300), None]), (-400 - 402_279_200 + 300, 1, 1));
    assert_eq!(pnl_of(&[], &[]), (0, 0, 0));
    assert_eq!(end_act(crate::Tok::Amount(7, 1)), EndAct::Sell(7));
    assert_eq!(end_act(crate::Tok::Amount(0, 1)), EndAct::Close);
    assert_eq!(end_act(crate::Tok::Closed(1)), EndAct::Nothing);
    assert_eq!(end_act(crate::Tok::Unknown), EndAct::Unreadable, "never read as 0");
    // the close: CloseAccount of OUR Token-2022 account of the mint, rent to us, the attempts' CU price
    let mint = pk32(MINT);
    let c = close_ixs(USER, &mint, 1_000);
    assert_eq!(c.len(), 3);
    assert_eq!((c[0].data[0], u32::from_le_bytes(c[0].data[1..5].try_into().unwrap())), (2, CLOSE_CU));
    assert_eq!((c[1].data[0], u64::from_le_bytes(c[1].data[1..9].try_into().unwrap())), (3, 1_000));
    assert_eq!((c[2].program, c[2].data.clone()), (*pda::TOKEN_2022, vec![9]));
    assert_eq!((c[2].accounts[0].key, c[2].accounts[1].key, c[2].accounts[2].key), (pda::ata(&USER, &mint, &pda::TOKEN_2022), USER, USER));
    assert!(c[2].accounts[2].signer);
}

/// GOLDEN: with --presend-live off nothing of dip19 runs and every tx shape is dip18's bytes (DIP15_GOLDEN, unchanged since dip15);
/// the exact sell of every reactive / --sell-held / exit path (keep_ata false) is snipe_build::sell_message_ixs byte for byte, its
/// last instruction the base account's close; the pre-send one is the same minus that close
#[test]
fn dip19_golden_presend_live_off_equals_dip18() {
    let (d, n) = crate::dip16_tests::golden_digest();
    assert_eq!(d, crate::dip16_tests::DIP15_GOLDEN, "the tx bytes must be dip15's .. dip18's ({n} shapes)");
    assert!(!SellOpts::main().keep_ata, "every non-pre-send sell closes the account as before");
    let key = SigningKey::from_bytes(&[11; 32]);
    let user: Pk = key.verifying_key().to_bytes();
    for i in 0..12u64 {
        let l = snipe_build::launch_from_target(pk32(MINT).map(|b| b ^ i as u8), [i as u8; 32]);
        for (qty, cu, price, wrap) in [(9_000_000 + i, 120_000u32, 5_000_000u64, i % 2 == 0), (1, 180_000, 0, false), (u64::MAX, 400_000, 3_000_000, true)] {
            let old = snipe_build::sell_message_ixs(user, &l, qty, 0, cu, price, wrap);
            let same = sell_exact_ixs(user, &l, qty, cu, price, wrap, false);
            let (mo, ms) = (build::compile_v0(user, &old, [0x42; 32], &[], &[]).unwrap(), build::compile_v0(user, &same, [0x42; 32], &[], &[]).unwrap());
            assert_eq!(mo.bytes, ms.bytes, "keep_ata false = dip18's sell bytes");
            assert_eq!(build::sign(&mo, &key), build::sign(&ms, &key));
            let keep = sell_exact_ixs(user, &l, qty, cu, price, wrap, true);
            assert_eq!(keep.len() + 1, old.len());
            let last = old.last().unwrap();
            assert!(last.program == *pda::TOKEN_2022 && last.data == [9] && last.accounts[0].key == pda::ata(&user, &l.mint, &pda::TOKEN_2022));
            assert!(keep.iter().all(|ix| !(ix.program == *pda::TOKEN_2022 && ix.data == [9])), "the pre-send sell never closes the base account");
            // the WSOL unwrap (--wrap) is not the guard: kept as it was
            assert_eq!(keep.iter().any(|ix| ix.program == *pda::TOKEN_PROGRAM && ix.data == [9]), wrap);
        }
    }
    // --presend-live off: no probe at all (dip18's refusals of a stray flag unchanged)
    let p = arbx::presend::Params::default();
    assert!(Cfg::from_argv(&["snipe_engine".to_string(), "--dip".into(), "--presend-shadow".into()], &p, true, 1_000_000_000).unwrap().is_none());
}

/// the run's end list (fix 4) covers a window that never settled (the run stopped first) and a window read whose answer never came:
/// a fill the feed missed there is read at the end too; a definite answer (nothing there) takes the mint off the list
#[test]
fn dip19_end_list_covers_unsettled_windows_and_unanswered_reads() {
    let (mut p, atx, _orx) = PsLive::for_test(probe().cfg.clone(), USER);
    let mint = pk32(MINT);
    let launch = snipe_build::launch_from_target(mint, [0xC1u8; 32]);
    arm_w51(&mut p, &atx, &launch);
    // no fill seen; the window still armed (the run stops here): its mint is read at the end, from its last deadline
    assert_eq!(p.end_list().iter().map(|x| (x.0, x.1)).collect::<Vec<_>>(), vec![(mint, N + 1)]);
    // the window ends; its attempts resolve unseen; it settles: its read goes out (and the window is forgotten)
    p.sh.slot.store(N + 1, Ordering::Relaxed);
    p.disarm(1, "stopped");
    p.tick(N + 6, None);
    let c = p.take_cmds();
    assert!(c.iter().any(|c| matches!(c, Cmd::Read { why: Why::Window(1), min_slot, .. } if *min_slot == N + 2)), "{c:?}");
    assert!(p.wins.is_empty(), "forgotten once its read went out");
    assert_eq!(p.end_list().iter().map(|x| (x.0, x.1)).collect::<Vec<_>>(), vec![(mint, N + 2)], "the read under way: read at the end too");
    // the answer: no account (no fill): off the list
    p.on_msg(PsMsg::Read(mint, Why::Window(1), N + 2, 1, crate::Tok::Closed(N + 6)), &|_| false);
    assert!(p.end_list().is_empty() && p.checks == 0 && p.st.orphans == 0);
}
