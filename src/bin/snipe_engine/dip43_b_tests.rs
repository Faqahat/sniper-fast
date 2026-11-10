// ===================================================================================================================
// dip43 BUILDER B tests (11-10): B1 cap / re-route / single token / skip clients, B2 fee tier, B3 two-lot exit, B4 cheap timer sells,
// B5 window start (ps43_b.rs). THE RULE: with none of their flags the engine sends, prices, routes, exits and sells exactly as dip42:
//  * defaults: every item off, no new record field, no run_start / run_end / status part, the sell command as dip42's (x43 None)
//  * route / fee decisions with default flags equal dip42's (pick_route = take_rate on the planned lane; tier_apply = att_fee's values)
//  * the sell loop's helpers with keep 0 equal dip42's (zero_at, the remainder)
//  * the two-lot exit: lot 1 = floor(T x FRAC) with the rest KEPT (sell_until_zero never sells it), lot 2 one slot later until 0, a stop
//    while lot 2 waits sells it at once, stops whole, realized over both sells, either answer order, a late fill in lot 2, the A/B arm,
//    the control key, the wall backstop, the sell-land "lot"
//  * cheap timer sells: the price only on time-limit / time-ms, the A/B on the id's second bit
// ===================================================================================================================
use super::*;

fn pk32(s: &str) -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }
fn sig64(s: &str) -> [u8; 64] { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }

/// dip19's w51 accounts (FRA run 22)
const MINT: &str = "6ESztPpqDyndKTfWZyhnuVEC2tC4QtVgVSAgXy6Bpump";
const WHALE: &str = "DxvwmNvYTUAPUQBtioT1SS3iL2Jj22b8qyPBk4WnE34B";
const SIG_TRIG: &str = "35eE9ByHoRVudQyJmnFymVx66ZTwBwHRgiHtqSV7cfdurGxwNxxwenSdhrnzSRdvF55irV8cRWdNtJi1Jarb2JTQ";
const SIG_A: &str = "4WT6Vdm5VpnGbzuqvdmxAt2xvHQN9UiP8ErwFvCtWMagb7CeQwoPx6EaHDTow5Nox4eDXGzQjY94GeLFxsoxJqVL";
const SIG_B: &str = "465WMBNiK2gSrkxzJbJc9SZBjKwNoP4BMrZojthKTzUR99KXQd1FDsH6YHstm9P5BScsDDYtkYkGSG3G1oba7Sfd";
const N: u64 = 461_415_576;
const USER: Pk = [0x5Au8; 32];
/// fill A's tokens; lot 1 / lot 2 at 0.5
const TA: u64 = 9_803_077_983_112;
const A1: u64 = 4_901_538_991_556;
const R2: u64 = TA - A1;

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }

fn arr(slot: u64, sig: [u8; 64], payer: Pk, ok: bool, exec: Option<arbx::feeds::ExecInfo>, t_rx: u64) -> arbx::feeds::Arrival {
    let tx = arbx::tx::Tx { sig, keys: vec![payer], ..Default::default() };
    arbx::feeds::Arrival { feed: 0, slot, t_rx, t_decoded: t_rx, executed: Some(ok), tx, poh: None, raw: arbx::feeds::RawTx::None, exec: exec.map(Arc::new) }
}
fn recs(orx: &crossbeam_channel::Receiver<Out>) -> Vec<serde_json::Value> { orx.try_iter().filter_map(|o| match o { Out::Rec(v) => Some(v), Out::Line(_) => None }).collect() }

#[allow(clippy::too_many_arguments)]
fn trade(p: &mut PsLive, slot: u64, idx: u64, sig: [u8; 64], user: Pk, buy: bool, sol: u64, tok: u64, vsol: u64, vtok: u64, launch: &Launch) {
    let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades: vec![arbx::dip::TradeEvent { mint: launch.mint, sol, tok, buy, user, vsol, vtok, fbps: 95, cbps: 30 }],
        creates: Vec::new(), mayhem: false };
    let a = arr(slot, sig, user, true, Some(x.clone()), slot * 1_000_000 + idx);
    let l = launch.clone();
    p.on_arrival(&a, slot);
    p.on_exec(&a, &x, slot, move |m: &Pk| (*m == l.mint).then(|| l.clone()), &|_| false, None);
}

fn att(w: u64, n: u32, mint: Pk, sig: [u8; 64], slot: u64) -> Att {
    Att { w, n, mint, sig, tag: pl::PS_TAG | (0xD43 << 8) | n as u64, path: "helius-ps".into(), client: "AgaveBam".into(), slot, deadline: slot + 1, lim: 0.000041, min_out: 9_524_401_719_354,
        p_sign: 0.0000466, sign_pos: (slot, 34, 0), t_send: slot * 1_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) }, tip: 200_000, wst: "written", ob6: 0.0,
        grd: Grd::default(), fa: None, bd: None }
}

fn sold(c: Option<u64>, sigs: &[&str], qty: u64) -> SellOut {
    SellOut { sold_at: c, sigs: sigs.iter().map(|s| (s.to_string(), true, 1_200_000)).collect(), last: None, attempts: sigs.len() as u32, last_qty: (qty, true), first_send_us: None }
}

/// the probe with `extra` flags, w51's window armed (create N - 2, whale N - 1) and fill A (slot N, TA tokens): the position open
fn open(extra: &[&str]) -> (PsLive, crossbeam_channel::Sender<Att>, crossbeam_channel::Receiver<Out>, Pk, Launch) {
    arbx::feeds::own_fail_watch(USER);
    let c = cfg(extra).unwrap().unwrap();
    let (mut p, atx, orx) = PsLive::for_test(c, USER);
    let mint = pk32(MINT);
    let launch = snipe_build::launch_from_target(mint, [0xC1u8; 32]);
    let creator = [0xC1u8; 32];
    let x = arbx::feeds::ExecInfo { index: 7, fee: 5_000, ok: true, trades: Vec::new(), mayhem: false,
        creates: vec![arbx::dip::CreateEvent { mint, bonding_curve: launch.bonding_curve, user: creator, creator }] };
    let a = arr(N - 2, [0xC7u8; 64], creator, true, Some(x.clone()), (N - 2) * 1_000_000);
    let l = launch.clone();
    p.on_exec(&a, &x, N - 2, move |m: &Pk| (*m == l.mint).then(|| l.clone()), &|_| false, None);
    trade(&mut p, N - 1, 34, sig64(SIG_TRIG), pk32(WHALE), true, 2_666_666_666, 61_580_021_739_287, 38_692_888_509, 831_935_821_811_615, &launch);
    assert_eq!(p.armed.get(&mint), Some(&1), "armed: {:?}", p.st.skips);
    atx.send(att(1, 1, mint, sig64(SIG_A), N - 1)).unwrap();
    atx.send(att(1, 2, mint, sig64(SIG_B), N)).unwrap();
    p.drain_atts();
    trade(&mut p, N, 192, sig64(SIG_A), USER, true, 395_061_727, TA, 36_215_421_019, 888_847_874_680_162, &launch);
    assert!(p.pos.contains_key(&mint));
    (p, atx, orx, mint, launch)
}

fn sells(c: &[Cmd]) -> Vec<(u32, Option<u64>, Option<SellX>)> {
    c.iter().filter_map(|c| match c { Cmd::Sell { round, known, x43, .. } => Some((*round, *known, *x43)), _ => None }).collect()
}
fn realized_sells(c: &[Cmd]) -> Option<Vec<String>> {
    c.iter().find_map(|c| match c { Cmd::Realized { sells, .. } => Some(sells.iter().map(|s| s.0.clone()).collect()), _ => None })
}
fn exits(r: &[serde_json::Value]) -> Vec<serde_json::Value> { r.iter().filter(|x| x["ev"] == "presend_live_exit").cloned().collect() }

// ------------------------------------------------------------------------------------------------------------------
// flags
// ------------------------------------------------------------------------------------------------------------------

#[test]
fn dip43b_defaults_off_and_flags_checked() {
    let c = cfg(&[]).unwrap().unwrap();
    assert_eq!(c.b43, ps43_b::B43Cfg::default(), "no flag: every item off");
    assert!(!c.b43.any_on() && c.json().get("b43").is_none(), "the run_start record is dip42's");
    // every flag is known to the start-up flag check (unknown flags refuse the start)
    let known = src_flags("\"");
    for f in B43FLAGS { assert!(known.contains(f), "{f} unknown to check_flags"); }
    assert!(check_flags(&args(&["--presend-live-reroute", "on", "--presend-live-exit-lots", "0.5:1"])).is_ok());
    // each value
    let c = cfg(&["--presend-live-reroute", "on", "--presend-live-single-token", "on", "--presend-live-skip-clients", "Rakurai,FireBAM", "--presend-live-fee-tier", "4:150000",
        "--presend-live-start-ms", "0", "--presend-live-exit-lots", "0.5:1", "--presend-live-exit-lots-ab", "on", "--presend-live-exit-lots-kinds", "t2,rearm",
        "--presend-live-lot2-cu-price-micro", "400000", "--presend-live-timer-sell-cu-price-micro", "500000", "--presend-live-timer-sell-ab", "on"]).unwrap().unwrap();
    let b = &c.b43;
    assert!(b.reroute && b.single_token && b.skip_clients == vec!["Rakurai".to_string(), "FireBAM".to_string()]);
    assert_eq!(b.tier, Some(ps43_b::TierCfg { n: 4, cu_price: 150_000, clients: psfeeab::AB_CLIENTS.split(',').map(String::from).collect() }));
    assert_eq!(b.start_ms, Some(0.0));
    assert_eq!(b.lots, Some(ps43_b::LotsCfg { frac: 0.5, slots: 1, kinds: vec!["t2", "rearm"], mode: ps43_b::LotsMode::Ab, lot2_price: 400_000 }));
    assert_eq!(b.timer_sell, Some(ps43_b::TimerSellCfg { cu_price: 500_000, ab: true }));
    assert!(c.json()["b43"]["exit_lots"]["mode"] == "ab");
    assert_eq!(b.desc_lines(60, 19, 50.0).len(), 6, "one banner line per item");
    // lots without -ab = every eligible exit; default kinds t2, lot 2 at 500,000
    let l = cfg(&["--presend-live-exit-lots", "0.5:1"]).unwrap().unwrap().b43.lots.unwrap();
    assert_eq!((l.mode, l.kinds.clone(), l.lot2_price), (ps43_b::LotsMode::Live, vec!["t2"], 500_000));
    assert_eq!(cfg(&["--presend-live-exit-lots", "0.5:1", "--presend-live-exit-lots-kinds", "all"]).unwrap().unwrap().b43.lots.unwrap().kinds, ps43_b::LOT_KINDS.to_vec());
    assert_eq!(cfg(&["--presend-live-fee-tier", "3:100000:JitoLabs"]).unwrap().unwrap().b43.tier.unwrap().clients, vec!["JitoLabs".to_string()]);
    // refusals
    for bad in [&["--presend-live-reroute", "yes"][..], &["--presend-live-skip-clients", "Nobody"], &["--presend-live-skip-clients", "Rakurai,Rakurai"],
        &["--presend-live-fee-tier", "0:150000"], &["--presend-live-fee-tier", "4:2000000"], &["--presend-live-fee-tier", "4"], &["--presend-live-fee-tier", "4:1000:Bad"],
        &["--presend-live-start-ms", "501"], &["--presend-live-start-ms", "x"], &["--presend-live-exit-lots", "1.0:1"], &["--presend-live-exit-lots", "0.5:0"],
        &["--presend-live-exit-lots", "0.5:5"], &["--presend-live-exit-lots", "0.5"], &["--presend-live-exit-lots-ab", "on"], &["--presend-live-exit-lots-kinds", "t2"],
        &["--presend-live-lot2-cu-price-micro", "500000"], &["--presend-live-exit-lots", "0.5:1", "--presend-live-exit-lots-kinds", "t3"],
        &["--presend-live-timer-sell-ab", "on"], &["--presend-live-timer-sell-cu-price-micro", "0"]] {
        assert!(cfg(bad).is_err(), "{bad:?} must be refused");
    }
    // a B flag without --presend-live is refused
    let a: Vec<String> = ["snipe_engine", "--dip", "--presend-live-exit-lots", "0.5:1"].iter().map(|s| s.to_string()).collect();
    assert!(Cfg::from_argv(&a, &arbx::presend::Params::default(), true, 1_000_000_000).is_err());
}

// ------------------------------------------------------------------------------------------------------------------
// B1 routes
// ------------------------------------------------------------------------------------------------------------------

/// re-route OFF: the lane and every bucket exactly as dip42's take_rate on the planned lane; ON: a lane refusal moves the try, a
/// global refusal never does
#[test]
fn dip43b_pick_route_default_equals_dip42() {
    let mk = || (send::TokenBucket::new(60.0, 15), vec![send::TokenBucket::new(19.0, 4), send::TokenBucket::new(40.0, 10), send::TokenBucket::new(19.0, 4)]);
    let (mut g1, mut l1) = mk();
    let (mut g2, mut l2) = mk();
    let (mut sent, mut refused) = (0u32, 0u32);
    // 20 ticks a slot for 30 s, round-robin over the lanes, one lane's configured budget refusing every 7th
    let mut t = 0u64;
    let mut k = 0usize;
    while t < 30_000_000_000 {
        let ri0 = k % 3;
        let cfg_ok = k % 7 != 0;
        let a = ps43_b::pick_route(3, ri0, false, |j| take_rate(&mut g1, &mut l1[j], t, || cfg_ok || j != 1));
        let b = take_rate(&mut g2, &mut l2[ri0], t, || cfg_ok || ri0 != 1).map(|_| (ri0, false));
        assert_eq!(a, b, "tick {k}");
        if a.is_ok() { sent += 1; } else { refused += 1; }
        t += 10_600_000;
        k += 1;
    }
    assert!(sent > 1000 && refused > 100, "{sent} {refused}");
    for j in 0..3 { assert_eq!(l1[j].peek(t), l2[j].peek(t)); }
    // ON: lane 0 empty -> lane 1 (moved); the global cap empty -> refused, no other lane tried
    let (mut g, mut l) = (send::TokenBucket::new(100.0, 25), vec![send::TokenBucket::new(1.0, 1), send::TokenBucket::new(40.0, 10)]);
    assert_eq!(take_rate(&mut g, &mut l[0], 1, || true), Ok(()));
    assert_eq!(take_rate(&mut g, &mut l[0], 2, || true), Err("rate_path"));
    let mut tried = Vec::new();
    assert_eq!(ps43_b::pick_route(2, 0, true, |j| { tried.push(j); take_rate(&mut g, &mut l[j], 3, || true) }), Ok((1, true)));
    assert_eq!(tried, vec![0, 1]);
    let mut g0 = send::TokenBucket::new(1.0, 1);
    assert!(g0.try_take(1));
    let mut tried = Vec::new();
    assert_eq!(ps43_b::pick_route(2, 1, true, |j| { tried.push(j); take_rate(&mut g0, &mut l[j], 2, || true) }), Err("rate_global"));
    assert_eq!(tried, vec![1], "a global refusal is never re-routed");
    // a configured-budget refusal is re-routed; every lane refusing -> the first refusal
    assert_eq!(ps43_b::pick_route(3, 2, true, |j| if j == 0 { Ok(()) } else { Err("rate_path_config") }), Ok((0, true)));
    assert_eq!(ps43_b::pick_route(3, 2, true, |_| Err("rate_path")), Err("rate_path"));
    assert_eq!(ps43_b::pick_route(1, 0, true, |_| Err("rate_path")), Err("rate_path"), "one lane: nothing to move to");
}

#[test]
fn dip43b_skip_clients() {
    let d = ps43_b::B43Cfg::default();
    for c in psfeeab::KNOWN_CLIENTS { assert!(!d.skip_client(c), "off: never"); }
    let b = cfg(&["--presend-live-skip-clients", "Rakurai"]).unwrap().unwrap().b43;
    assert!(b.skip_client("Rakurai") && !b.skip_client("AgaveBam") && !b.skip_client(""));
}

// ------------------------------------------------------------------------------------------------------------------
// B2 fee tier
// ------------------------------------------------------------------------------------------------------------------

/// with the tier off, every try's (CU limit, price, tip, A/B values) are att_fee's (dip42) and no counter moves; with it on, every Nth
/// try of a window-slot on a listed client is raised (never lowered), the fee A/B's values follow the signed price
#[test]
fn dip43b_fee_tier() {
    let base = cfg(&[]).unwrap().unwrap();
    let ab = cfg(&["--presend-live-fee-ab", "on", "--presend-live-ab-cu-price-micro", "50000"]).unwrap().unwrap();
    let tip = Some(([7u8; 32], 100_000u64));
    let mut ctr = ps43_b::TierCtr::default();
    for c in [&base, &ab] {
        for client in ["AgaveBam", "JitoLabs", "HarmonicAgave", "Rakurai", ""] {
            for arm in [None, Some(0u8), Some(1u8)] {
                let (lim, price, t, fa) = psfeeab::att_fee(c, arm, client, tip);
                for i in 0..9 {
                    let (p2, fa2, tag) = ps43_b::tier_apply(&c.b43, &mut ctr, 7, 100 + i, client, price, fa);
                    assert_eq!((p2, fa2, tag), (price, fa, None), "tier off: dip42's values");
                }
                assert_eq!(psfeeab::att_fee(c, arm, client, tip), (lim, price, t, fa));
            }
        }
    }
    assert!(ctr.next(1, 1) == 1, "the counter was never touched with the tier off");
    // on: 1 in 4 on fee-ordered leaders
    let on = cfg(&["--presend-live-fee-tier", "4:150000", "--presend-live-fee-ab", "on", "--presend-live-ab-cu-price-micro", "50000"]).unwrap().unwrap();
    let mut ctr = ps43_b::TierCtr::default();
    let mut tiered = Vec::new();
    for i in 1..=10u32 {
        let (_, price, _, fa) = psfeeab::att_fee(&on, Some(1), "AgaveBam", tip);
        let (p, fa2, tag) = ps43_b::tier_apply(&on.b43, &mut ctr, 9, 500, "AgaveBam", price, fa);
        let tag = tag.unwrap();
        assert_eq!(tag.i, i);
        if tag.on { tiered.push(i); assert_eq!((p, fa2.unwrap().cu_price), (150_000, 150_000)); } else { assert_eq!(p, 50_000); assert_eq!(fa2, fa); }
    }
    assert_eq!(tiered, vec![4, 8]);
    // a new slot restarts the count; another window has its own
    assert_eq!(ctr.next(9, 501), 1);
    assert_eq!(ctr.next(10, 501), 1);
    // Jito / unlisted leaders never; never lower than the try's own price
    assert_eq!(ps43_b::tier_price(&on.b43, 4, "JitoLabs", 1_000).0, 1_000);
    assert_eq!(ps43_b::tier_price(&on.b43, 4, "AgaveBam", 200_000), (200_000, Some(ps43_b::TierTag { i: 4, n: 4, on: false, client_ok: true, cu_price: 200_000 })));
    assert_eq!(ps43_b::tier_price(&on.b43, 8, "Firedancer", 1_000).0, 150_000);
    // the failed-fee fallback of a tiered try (the fee A/B off)
    ps43_b::tier_fee_note(&[0xEE; 64], psfeeab::fail_fee(120_000, 150_000));
    assert_eq!(ps43_b::tier_fail_fee(&[0xEE; 64]), Some(5_000 + 18_000));
    assert_eq!(ps43_b::tier_fail_fee(&[0xEF; 64]), None);
}

// ------------------------------------------------------------------------------------------------------------------
// B5 window start
// ------------------------------------------------------------------------------------------------------------------

#[test]
fn dip43b_window_start() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let arm = |extra: &[&str]| -> (u64, u64, u64) {
        let c = cfg(extra).unwrap().unwrap();
        let (mut p, _atx, _orx) = PsLive::for_test(c, USER);
        let mint = pk32(MINT);
        let launch = snipe_build::launch_from_target(mint, [0xC1u8; 32]);
        let x = arbx::feeds::ExecInfo { index: 7, fee: 5_000, ok: true, trades: Vec::new(), mayhem: false,
            creates: vec![arbx::dip::CreateEvent { mint, bonding_curve: launch.bonding_curve, user: [0xC1u8; 32], creator: [0xC1u8; 32] }] };
        let a = arr(N - 2, [0xC7u8; 64], [0xC1u8; 32], true, Some(x.clone()), (N - 2) * 1_000_000);
        let l = launch.clone();
        p.on_exec(&a, &x, N - 2, move |m: &Pk| (*m == l.mint).then(|| l.clone()), &|_| false, None);
        let t0 = arbx::fast::mono_ns();
        trade(&mut p, N - 1, 34, sig64(SIG_TRIG), pk32(WHALE), true, 2_666_666_666, 61_580_021_739_287, 38_692_888_509, 831_935_821_811_615, &launch);
        let t1 = arbx::fast::mono_ns();
        let g = p.sh.wins.lock().unwrap();
        (g[0].st_ns.saturating_sub(t0), g[0].st_ns.saturating_sub(t1), g[0].en_slot)
    };
    let (d0, d1, en) = arm(&[]);
    assert!(d1 <= 50_000_000 && d0 >= 50_000_000 - 1, "dip42: +50 ms ({d0} {d1})");
    let (z0, _, en0) = arm(&["--presend-live-start-ms", "0"]);
    assert!(z0 < 50_000_000, "at once ({z0})");
    assert_eq!(en0, en, "the end slot is dip42's");
    let (t0, _, en20) = arm(&["--presend-live-start-ms", "20"]);
    assert!((20_000_000..50_000_000).contains(&t0), "{t0}");
    assert_eq!(en20, en);
}

// ------------------------------------------------------------------------------------------------------------------
// the sell loop's helpers
// ------------------------------------------------------------------------------------------------------------------

/// keep 0 = dip42's loop (zero_at, the whole remainder); keep R = lot 1: done at a confirmed balance <= R, NEVER sells the rest
#[test]
fn dip43b_sell_loop_helpers() {
    for t in [crate::Tok::Amount(0, 9), crate::Tok::Amount(1, 9), crate::Tok::Amount(TA, 9), crate::Tok::Closed(9), crate::Tok::Unknown] {
        assert_eq!(sell_done_at(t, 0), t.zero_at(), "{t:?}");
    }
    for h in [0, 1, R2, TA] { assert_eq!(sell_next_qty(h, 0), h); }
    // lot 1: T in the account, sell A, keep R
    assert_eq!(sell_next_qty(TA, R2), A1, "the first sell: lot 1's tokens");
    assert_eq!(sell_done_at(crate::Tok::Amount(TA, 10), R2), None, "lot 1 not landed yet: not done");
    assert_eq!(sell_next_qty(TA, R2), A1, "re-sent: still only lot 1's part");
    assert_eq!(sell_done_at(crate::Tok::Amount(R2, 11), R2), Some(11), "lot 1 landed: DONE, the remainder (lot 2's) is NOT sold");
    assert_eq!(sell_done_at(crate::Tok::Amount(0, 12), R2), Some(12), "lot 2 already sold too");
    assert_eq!(sell_done_at(crate::Tok::Closed(12), R2), Some(12));
    assert_eq!(sell_done_at(crate::Tok::Unknown, R2), None);
    // half landed elsewhere (a partial fill of lot 1 cannot happen on pump: an exact-in sell sells all or fails); a larger balance
    // (a late buy) still sells only the part above the kept tokens
    assert_eq!(sell_next_qty(TA + 5, R2), A1 + 5);
    assert_eq!(SellX::default(), SellX { keep: 0, cu_price: None, lot: 0 });
}

// ------------------------------------------------------------------------------------------------------------------
// B3 / B4 exits through the probe's state machine (the chain work queued: no RPC, no send)
// ------------------------------------------------------------------------------------------------------------------

/// no flag: the time exit is dip42's: one whole sell, no SellX, no new record field, no status / run_end part
#[test]
fn dip43b_default_exit_is_dip42() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, _atx, orx, mint, _l) = open(&[]);
    let _ = p.take_cmds();
    p.tick(N + 2, None);
    let c = p.take_cmds();
    assert_eq!(sells(&c), vec![(1, Some(TA), None)], "one whole sell, dip42's command");
    let pid = p.pos[&mint].pid;
    assert!(p.b43.lots.is_empty());
    p.on_msg(PsMsg::Sold(mint, pid, 1, sold(Some(N + 3), &["S1"], TA)), &|_| false);
    assert!(p.pos.is_empty());
    assert_eq!(realized_sells(&p.take_cmds()), Some(vec!["S1".to_string()]));
    let r = recs(&orx);
    let x = exits(&r);
    assert_eq!(x.len(), 1);
    for k in ["lot", "lots", "timer_sell", "tokens_all", "lot2_tokens"] { assert!(x[0].get(k).is_none(), "{k} on a dip42 exit"); }
    assert!(r.iter().all(|x| x["ev"] != "presend_live_lot_sold" && x.get("lot").is_none()));
    assert!(!p.status().contains("DIP43") && p.b43_finish().is_none());
}

/// LOTS: lot 1 (floor(T/2), the rest kept) at the timer; lot 2 one slot later until 0 at its own price; lot 1's answer does not close
/// the position; lot 2's does; realized has both sells
#[test]
fn dip43b_lots_timer_exit() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, _atx, orx, mint, launch) = open(&["--presend-live-exit-lots", "0.5:1"]);
    let _ = p.take_cmds();
    let pid = p.pos[&mint].pid;
    p.tick(N + 2, None);
    assert_eq!(sells(&p.take_cmds()), vec![(1, Some(TA), Some(SellX { keep: R2, cu_price: None, lot: 1 }))], "lot 1: sells T - R, keeps R");
    // the same slot: lot 2 waits
    p.tick(N + 2, None);
    assert!(sells(&p.take_cmds()).is_empty(), "lot 2 waits for the next slot");
    // lot 1 lands (its sell-land record says lot 1)
    trade(&mut p, N + 2, 50, [0x51; 64], USER, false, 190_000_000, A1, 34_000_000_000, 940_000_000_000_000, &launch);
    // lot 1's answer before lot 2 went: the position stays open, no realized, lot 1's sells kept
    p.on_msg(PsMsg::Sold(mint, pid, 1, sold(Some(N + 2), &["L1"], A1)), &|_| false);
    assert!(p.pos.contains_key(&mint) && realized_sells(&p.take_cmds()).is_none(), "lot 1's answer never closes the position");
    assert_eq!(p.pos[&mint].sells.iter().map(|s| s.0.as_str()).collect::<Vec<_>>(), vec!["L1"]);
    // the next slot: lot 2, every remaining token, at --presend-live-lot2-cu-price-micro (500,000 default), until 0
    p.tick(N + 3, None);
    assert_eq!(sells(&p.take_cmds()), vec![(2, Some(R2), Some(SellX { keep: 0, cu_price: Some(500_000), lot: 2 }))]);
    p.tick(N + 4, None);
    assert!(sells(&p.take_cmds()).is_empty(), "lot 2 goes once");
    trade(&mut p, N + 3, 20, [0x52; 64], USER, false, 185_000_000, R2, 33_000_000_000, 950_000_000_000_000, &launch);
    p.on_msg(PsMsg::Sold(mint, pid, 2, sold(Some(N + 4), &["L2"], R2)), &|_| false);
    assert!(p.pos.is_empty() && p.b43.lots.is_empty(), "lot 2's confirmed 0 closes the position");
    let c = p.take_cmds();
    assert_eq!(realized_sells(&c), Some(vec!["L1".to_string(), "L2".to_string()]), "realized sums BOTH sells");
    let r = recs(&orx);
    let x = exits(&r);
    assert_eq!(x.len(), 2, "{x:?}");
    assert_eq!((x[0]["why"].as_str(), x[0]["lot"].as_u64(), x[0]["tokens"].as_u64(), x[0]["lot2_tokens"].as_u64(), x[0]["lots"]["arm"].as_str()),
        (Some("time-limit"), Some(1), Some(A1), Some(R2), Some("lots")));
    assert_eq!((x[1]["why"].as_str(), x[1]["lot"].as_u64(), x[1]["tokens"].as_u64(), x[1]["round"].as_u64()), (Some("lot2"), Some(2), Some(R2), Some(2)));
    let lands: Vec<u64> = r.iter().filter(|x| x["ev"] == "presend_live_sell_land").map(|x| x["lot"].as_u64().unwrap()).collect();
    assert_eq!(lands, vec![1, 2]);
    let close = r.iter().find(|x| x["ev"] == "presend_live_close").unwrap();
    assert_eq!((close["result"].as_str(), close["curve_pnl"].as_i64()), (Some("sold"), Some(190_000_000 + 185_000_000 - 395_061_727)), "the curve P&L over both lots");
    assert!(r.iter().any(|x| x["ev"] == "presend_live_lot_sold" && x["lot"] == 1));
    assert_eq!(p.st.exits, 1, "one exit counted");
    assert!(p.status().contains("DIP43-B lots live"));
}

/// lot 2's answer before lot 1's: it waits; lot 1's answer then closes the position with both sells
#[test]
fn dip43b_lots_answers_any_order() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, _atx, _orx, mint, _l) = open(&["--presend-live-exit-lots", "0.5:1"]);
    let pid = p.pos[&mint].pid;
    p.tick(N + 2, None);
    p.tick(N + 3, None);
    assert_eq!(sells(&p.take_cmds()).len(), 2);
    p.on_msg(PsMsg::Sold(mint, pid, 2, sold(Some(N + 4), &["L2"], R2)), &|_| false);
    assert!(p.pos.contains_key(&mint) && realized_sells(&p.take_cmds()).is_none(), "lot 2 done, lot 1's loop still running: wait");
    p.on_msg(PsMsg::Sold(mint, pid, 1, sold(Some(N + 4), &["L1a", "L1b"], A1)), &|_| false);
    assert!(p.pos.is_empty() && p.b43.lots.is_empty());
    assert_eq!(realized_sells(&p.take_cmds()), Some(vec!["L1a".to_string(), "L1b".to_string(), "L2".to_string()]));
    // a stale answer afterwards changes nothing
    p.on_msg(PsMsg::Sold(mint, pid, 1, sold(Some(N + 4), &[], 0)), &|_| false);
    assert!(p.take_cmds().is_empty());
}

/// lot 1 never confirmed (its loop's deadline): lot 2 (until 0) closes the position; no UNSOLD retry from lot 1
#[test]
fn dip43b_lots_lot1_unconfirmed() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, _atx, _orx, mint, _l) = open(&["--presend-live-exit-lots", "0.5:1"]);
    let pid = p.pos[&mint].pid;
    p.tick(N + 2, None);
    p.tick(N + 3, None);
    let _ = p.take_cmds();
    p.on_msg(PsMsg::Sold(mint, pid, 2, sold(Some(N + 5), &["L2", "L2b"], TA)), &|_| false);
    p.on_msg(PsMsg::Sold(mint, pid, 1, sold(None, &["L1"], A1)), &|_| false);
    let c = p.take_cmds();
    assert!(p.pos.is_empty() && c.iter().all(|c| !matches!(c, Cmd::Unsold { .. })), "{c:?}");
    assert_eq!(realized_sells(&c), Some(vec!["L1".to_string(), "L2".to_string(), "L2b".to_string()]));
    assert_eq!(p.b43.n.l1_unconfirmed, 1);
}

/// a stop-loss value while lot 2 waits sells lot 2 AT ONCE (the run's sell price); a quiet trade does not; the timer does not fire it again
#[test]
fn dip43b_lots_stop_sells_lot2_at_once() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, _atx, orx, mint, launch) = open(&["--presend-live-exit-lots", "0.5:1"]);
    let _ = p.take_cmds();
    p.tick(N + 2, None);
    assert_eq!(sells(&p.take_cmds()).len(), 1);
    // an outside buy near the entry price: no stop
    trade(&mut p, N + 2, 60, [0x61; 64], [0x61; 32], true, 1_000_000, 24_000_000_000, 36_215_421_019, 888_847_874_680_162, &launch);
    assert!(sells(&p.take_cmds()).is_empty());
    // an outside dump: lot 2's value x0.3 -> lot 2 at once, the same slot
    trade(&mut p, N + 2, 70, [0x62; 64], [0x62; 32], false, 9_000_000_000, 600_000_000_000_000, 20_000_000_000, 1_500_000_000_000_000, &launch);
    assert_eq!(sells(&p.take_cmds()), vec![(2, Some(R2), Some(SellX { keep: 0, cu_price: None, lot: 2 }))], "the stop's lot 2: the run's sell price");
    p.tick(N + 3, None);
    assert!(sells(&p.take_cmds()).is_empty(), "never twice");
    let x = exits(&recs(&orx));
    assert_eq!((x[1]["why"].as_str(), x[1]["lot"].as_u64()), (Some("lot2-stop"), Some(2)));
    assert!(x[1]["value"].as_f64().unwrap() < 0.8);
    assert_eq!(p.b43.n.lot2_stop, 1);
}

/// a stop-loss EXIT stays whole (no lot); take-profit goes in lots
#[test]
fn dip43b_lots_stop_whole_tp_lots() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, _atx, _orx, mint, launch) = open(&["--presend-live-exit-lots", "0.5:1"]);
    let _ = p.take_cmds();
    trade(&mut p, N, 253, [0x63; 64], [0x63; 32], false, 9_000_000_000, 600_000_000_000_000, 20_000_000_000, 1_500_000_000_000_000, &launch);
    assert_eq!(p.pos[&mint].exit.map(|x| x.0), Some("stop-loss"));
    assert_eq!(sells(&p.take_cmds()), vec![(1, Some(TA), None)], "a stop: dip42's whole sell");
    assert!(p.b43.lots.is_empty());
    let (mut p, _atx, _orx, mint, launch) = open(&["--presend-live-exit-lots", "0.5:1"]);
    let _ = p.take_cmds();
    trade(&mut p, N, 253, [0x64; 64], [0x64; 32], true, 9_000_000_000, 200_000_000_000_000, 45_000_000_000, 715_000_000_000_000, &launch);
    assert_eq!(p.pos[&mint].exit.map(|x| x.0), Some("take-profit"));
    assert_eq!(sells(&p.take_cmds()), vec![(1, Some(TA), Some(SellX { keep: R2, cu_price: None, lot: 1 }))], "take-profit: lot 1");
}

/// the A/B: even position id = lots, odd = whole (logged as the whole arm); the control file's exit_lots flips the mode
#[test]
fn dip43b_lots_ab_and_control_key() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, _atx, orx, mint, _l) = open(&["--presend-live-exit-lots", "0.5:1", "--presend-live-exit-lots-ab", "on"]);
    let _ = p.take_cmds();
    assert_eq!(p.pos[&mint].pid % 2, 1);
    p.tick(N + 2, None);
    assert_eq!(sells(&p.take_cmds()), vec![(1, Some(TA), None)], "odd pid: the whole arm (dip42's sell)");
    let x = exits(&recs(&orx));
    assert_eq!((x[0]["lots"]["arm"].as_str(), x[0]["lots"]["mode"].as_str()), (Some("whole"), Some("ab")));
    let (mut p, _atx, _orx, mint, _l) = open(&["--presend-live-exit-lots", "0.5:1", "--presend-live-exit-lots-ab", "on"]);
    let _ = p.take_cmds();
    p.pos.get_mut(&mint).unwrap().pid = 2;
    p.tick(N + 2, None);
    assert_eq!(sells(&p.take_cmds())[0].2.map(|x| x.lot), Some(1), "even pid: lots");
    // the control key (needs --presend-live-ledger-control): off -> whole; live -> lots; a bad value keeps the mode
    let dir = std::env::temp_dir().join(format!("dip43b_ctl_{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let f = dir.join("ctl.json");
    std::fs::write(&f, r#"{"whale": "live", "exit_lots": "off"}"#).unwrap();
    let fs = f.to_str().unwrap().to_string();
    // (the control file needs a ledger / gate it switches: the holder ledger here, the bot depth gate in the runs)
    let (mut p, _atx, orx, mint, _l) = open(&["--presend-live-exit-lots", "0.5:1", "--presend-live-ledger-control", &fs, "--presend-live-holder-loss", "2:0.10:0.05"]);
    let _ = p.take_cmds();
    p.b43_ctl_check(true);
    assert_eq!(p.b43_mode(), ps43_b::LotsMode::Off);
    let r = recs(&orx);
    assert!(r.iter().any(|x| x["ev"] == "presend_live_ledger_mode" && x["exit_lots"] == "off" && x["was"]["exit_lots"] == "live"), "{r:?}");
    p.tick(N + 2, None);
    assert_eq!(sells(&p.take_cmds()), vec![(1, Some(TA), None)], "exit_lots off: whole");
    assert!(exits(&recs(&orx))[0].get("lots").is_none());
    std::fs::write(&f, r#"{"exit_lots": "sideways"}"#).unwrap();
    p.b43_ctl_check(true);
    assert_eq!((p.b43_mode(), p.b43.n.ctl_errors), (ps43_b::LotsMode::Off, 1));
    std::fs::write(&f, r#"{"exit_lots": "live"}"#).unwrap();
    p.b43_ctl_check(true);
    assert_eq!(p.b43_mode(), ps43_b::LotsMode::Live);
    // without --presend-live-exit-lots the key is ignored
    let (mut q, _atx, _orx, _mint, _l) = open(&["--presend-live-ledger-control", &fs, "--presend-live-holder-loss", "2:0.10:0.05"]);
    q.b43_ctl_check(true);
    assert_eq!(q.b43_mode(), ps43_b::LotsMode::Off);
    let _ = std::fs::remove_dir_all(&dir);
}

/// a fill landing after lot 1 went (an attempt in flight) is sold with lot 2; the wall backstop fires lot 2 on a stalled slot clock
#[test]
fn dip43b_lots_late_fill_and_wall() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, _atx, orx, mint, launch) = open(&["--presend-live-exit-lots", "0.5:1"]);
    let _ = p.take_cmds();
    let pid = p.pos[&mint].pid;
    p.tick(N + 2, None);
    let _ = p.take_cmds();
    trade(&mut p, N + 2, 33, sig64(SIG_B), USER, true, 395_061_727, 1_000_000, 36_300_000_000, 886_000_000_000_000, &launch);
    assert_eq!(p.pos[&mint].late, 1);
    // the slot clock stalls at N + 2: the wall backstop (400 + 600 ms) fires lot 2
    p.b43.lots.get_mut(&mint).unwrap().dec_at = Instant::now() - Duration::from_millis(1_100);
    p.tick(N + 2, None);
    assert_eq!(sells(&p.take_cmds()), vec![(2, Some(R2 + 1_000_000), Some(SellX { keep: 0, cu_price: Some(500_000), lot: 2 }))], "lot 2 + the late buy");
    assert!(p.pos[&mint].buys.iter().all(|b| b.round == 2), "every buy in lot 2's round");
    p.on_msg(PsMsg::Sold(mint, pid, 1, sold(Some(N + 3), &["L1"], A1)), &|_| false);
    p.on_msg(PsMsg::Sold(mint, pid, 2, sold(Some(N + 3), &["L2"], R2)), &|_| false);
    assert!(p.pos.is_empty());
    let c = p.take_cmds();
    let Some(Cmd::Realized { buys, sells, .. }) = c.iter().find(|c| matches!(c, Cmd::Realized { .. })) else { panic!("{c:?}") };
    assert_eq!((buys.len(), sells.len()), (2, 2), "both buys, both sells");
    assert!(exits(&recs(&orx)).iter().any(|x| x["why"] == "lot2-wall"));
}

/// B4: the cheap price only on timer exits; the A/B on the id's second bit; TP unchanged; with lots, lot 1 of a timer exit is cheap
#[test]
fn dip43b_cheap_timer_sells() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, _atx, orx, _mint, _l) = open(&["--presend-live-timer-sell-cu-price-micro", "500000"]);
    let _ = p.take_cmds();
    p.tick(N + 2, None);
    assert_eq!(sells(&p.take_cmds()), vec![(1, Some(TA), Some(SellX { keep: 0, cu_price: Some(500_000), lot: 0 }))]);
    assert_eq!(exits(&recs(&orx))[0]["timer_sell"]["arm"], "cheap");
    // take-profit: the run's price (dip42's command)
    let (mut p, _atx, orx, mint, launch) = open(&["--presend-live-timer-sell-cu-price-micro", "500000"]);
    let _ = p.take_cmds();
    trade(&mut p, N, 253, [0x64; 64], [0x64; 32], true, 9_000_000_000, 200_000_000_000_000, 45_000_000_000, 715_000_000_000_000, &launch);
    assert_eq!(p.pos[&mint].exit.map(|x| x.0), Some("take-profit"));
    assert_eq!(sells(&p.take_cmds()), vec![(1, Some(TA), None)]);
    assert!(exits(&recs(&orx))[0].get("timer_sell").is_none());
    // the A/B: pid 1 ((1 >> 1) & 1 = 0) cheap, pid 2 base
    assert!(ps43_b::cheap_arm(&ps43_b::TimerSellCfg { cu_price: 1, ab: true }, 1) && !ps43_b::cheap_arm(&ps43_b::TimerSellCfg { cu_price: 1, ab: true }, 2));
    let (mut p, _atx, orx, mint, _l) = open(&["--presend-live-timer-sell-cu-price-micro", "500000", "--presend-live-timer-sell-ab", "on"]);
    let _ = p.take_cmds();
    p.pos.get_mut(&mint).unwrap().pid = 2;
    p.tick(N + 2, None);
    assert_eq!(sells(&p.take_cmds()), vec![(1, Some(TA), None)], "the base arm: dip42's sell");
    assert_eq!(exits(&recs(&orx))[0]["timer_sell"]["arm"], "base");
    // lots + cheap: lot 1 of a timer exit at the cheap price, lot 2 at lot 2's
    let (mut p, _atx, _orx, _mint, _l) = open(&["--presend-live-timer-sell-cu-price-micro", "700000", "--presend-live-exit-lots", "0.5:1"]);
    let _ = p.take_cmds();
    p.tick(N + 2, None);
    p.tick(N + 3, None);
    assert_eq!(sells(&p.take_cmds()), vec![(1, Some(TA), Some(SellX { keep: R2, cu_price: Some(700_000), lot: 1 })), (2, Some(R2), Some(SellX { keep: 0, cu_price: Some(500_000), lot: 2 }))]);
}

/// the pure rules
#[test]
fn dip43b_exit_rules() {
    use ps43_b::*;
    assert_eq!(lots_split(TA, 0.5), Some((A1, R2)));
    assert_eq!(lots_split(1, 0.5), None, "one token: whole");
    assert_eq!(lots_split(3, 0.5), Some((1, 2)));
    assert_eq!(lots_split(0, 0.5), None);
    assert!(lots_reason("time-limit") && lots_reason("time-ms") && lots_reason("take-profit"));
    for w in ["stop-loss", "time-limit-wall", "orphan", "follow-up"] { assert!(!lots_reason(w) && !timer_reason(w), "{w}"); }
    assert!(timer_reason("time-limit") && timer_reason("time-ms") && !timer_reason("take-profit"));
    assert_eq!((lots_arm(LotsMode::Off, 2), lots_arm(LotsMode::Live, 1), lots_arm(LotsMode::Ab, 2), lots_arm(LotsMode::Ab, 3)), (None, Some(true), Some(true), Some(false)));
    assert_eq!(lot2_wall_ms(1), 1_000);
    assert_eq!(ctl_parse_lots(br#"{"whale": "log"}"#), Ok(None));
    assert_eq!(ctl_parse_lots(br#"{"exit_lots": "ab"}"#), Ok(Some(LotsMode::Ab)));
    assert!(ctl_parse_lots(br#"{"exit_lots": 1}"#).is_err() && ctl_parse_lots(b"nope").is_err());
}

/// B6 the exit-timer A/B: off = cfg.exit_ms for every position (dip42); on = odd pid an N ms timer, even the run's exit; the arm on
/// every exit record; refused with the lots A/B (both on pid parity)
#[test]
fn dip43b_exit_timer_ab() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    assert_eq!(cfg(&[]).unwrap().unwrap().b43.exit_ab, None);
    assert_eq!(cfg(&["--presend-live-exit-ab", "ms:200"]).unwrap().unwrap().b43.exit_ab, Some(200));
    for bad in ["200", "ms:20", "ms:3000", "ms:x"] { assert!(cfg(&["--presend-live-exit-ab", bad]).is_err(), "{bad}"); }
    assert!(cfg(&["--presend-live-exit-ab", "ms:200", "--presend-live-exit-lots", "0.5:1", "--presend-live-exit-lots-ab", "on"]).is_err());
    // off: every position's ms timer is the run's (0 here, and 125 with --presend-live-exit-ms 125)
    let (p, _atx, _orx, mint, _l) = open(&[]);
    assert_eq!((p.b43_exit_ms(1), p.b43_exit_ms(2), p.next_exit_in()), (0, 0, None));
    let (p, _atx, _orx, _mint, _l) = open(&["--presend-live-exit-ms", "125"]);
    assert_eq!((p.b43_exit_ms(1), p.b43_exit_ms(2)), (125, 125));
    assert!(p.next_exit_in().is_some());
    let _ = mint;
    // on: pid 1 (odd) sells after 200 ms inside its fill slot; the record says arm ms
    let (mut p, _atx, orx, mint, _l) = open(&["--presend-live-exit-ab", "ms:200"]);
    let _ = p.take_cmds();
    assert!(p.next_exit_in().is_some_and(|d| d <= Duration::from_millis(200)));
    p.tick(N, None);
    assert!(sells(&p.take_cmds()).is_empty(), "not yet");
    p.pos.get_mut(&mint).unwrap().opened = Instant::now() - Duration::from_millis(210);
    p.tick(N, None);
    assert_eq!(sells(&p.take_cmds()), vec![(1, Some(TA), None)], "the ms arm: dip42's sell command");
    let x = exits(&recs(&orx));
    assert_eq!((x[0]["why"].as_str(), x[0]["exit_ab"]["arm"].as_str(), x[0]["exit_ab"]["ms"].as_u64()), (Some("time-ms"), Some("ms"), Some(200)));
    // even pid: the run's slot exit
    let (mut p, _atx, orx, mint, _l) = open(&["--presend-live-exit-ab", "ms:200"]);
    let _ = p.take_cmds();
    p.pos.get_mut(&mint).unwrap().pid = 2;
    assert_eq!(p.next_exit_in(), None, "even pid: no ms timer");
    p.pos.get_mut(&mint).unwrap().opened = Instant::now() - Duration::from_millis(500);
    p.tick(N, None);
    assert!(sells(&p.take_cmds()).is_empty());
    p.tick(N + 2, None);
    assert_eq!(sells(&p.take_cmds()), vec![(1, Some(TA), None)]);
    let x = exits(&recs(&orx));
    assert_eq!((x[0]["why"].as_str(), x[0]["exit_ab"]["arm"].as_str()), (Some("time-limit"), Some("base")));
}

// ---- dip43e: the dump exit ---------------------------------------------------------------------------------------------------------
/// a sell >= S SOL by another wallet into an open position sells it at once ("dump-exit"); a smaller sell does not; a buy never does
#[test]
fn dip43e_dump_exit_single_sell() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, _atx, orx, mint, launch) = open(&["--presend-live-dump-exit", "1.0:0:0"]);
    let _ = p.take_cmds();
    let _ = p.ctl43_apply(&ps43::ctl43_parse(br#"{"dump_exit": "live"}"#).unwrap());
    // a 0.5 SOL sell: no exit
    trade(&mut p, N, 240, [0x71; 64], [0x71; 32], false, 500_000_000, 12_000_000_000_000, 35_700_000_000, 901_000_000_000_000, &launch);
    assert!(p.pos[&mint].exit.is_none());
    // a 1.5 SOL buy: no exit
    trade(&mut p, N, 241, [0x72; 64], [0x72; 32], true, 1_500_000_000, 36_000_000_000_000, 37_200_000_000, 865_000_000_000_000, &launch);
    assert!(p.pos[&mint].exit.is_none());
    // a 1.5 SOL sell (value ~x0.92, above the -20% stop): dump-exit
    trade(&mut p, N, 242, [0x73; 64], [0x73; 32], false, 1_500_000_000, 40_000_000_000_000, 35_700_000_000, 905_000_000_000_000, &launch);
    assert_eq!(p.pos[&mint].exit.map(|x| x.0), Some("dump-exit"));
    let r = recs(&orx);
    let d: Vec<_> = r.iter().filter(|x| x["ev"] == "presend_live_dump_exit").collect();
    assert_eq!(d.len(), 1);
    assert_eq!((d[0]["mode"].as_str(), d[0]["sell_sol"].as_f64()), (Some("live"), Some(1.5)));
    assert!(sells(&p.take_cmds()).len() == 1, "sold");
}

/// cumulative sells into the hold; the value gate X; the control key's log mode records once and keeps holding
#[test]
fn dip43e_dump_exit_cum_gate_and_log() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    // C = 1.0: two 0.6 SOL sells
    let (mut p, _atx, _orx, mint, launch) = open(&["--presend-live-dump-exit", "0:1.0:0"]);
    let _ = p.take_cmds();
    let _ = p.ctl43_apply(&ps43::ctl43_parse(br#"{"dump_exit": "live"}"#).unwrap());
    trade(&mut p, N, 240, [0x74; 64], [0x74; 32], false, 600_000_000, 15_000_000_000_000, 35_600_000_000, 904_000_000_000_000, &launch);
    assert!(p.pos[&mint].exit.is_none());
    trade(&mut p, N, 241, [0x75; 64], [0x75; 32], false, 600_000_000, 15_500_000_000_000, 35_000_000_000, 919_500_000_000_000, &launch);
    assert_eq!(p.pos[&mint].exit.map(|x| x.0), Some("dump-exit"));
    // X = 0.5: a 1.5 SOL sell at value ~x0.92 does not fire (not down 50%)
    let (mut p, _atx, _orx, mint, launch) = open(&["--presend-live-dump-exit", "1.0:0:0.5"]);
    let _ = p.take_cmds();
    let _ = p.ctl43_apply(&ps43::ctl43_parse(br#"{"dump_exit": "live"}"#).unwrap());
    trade(&mut p, N, 242, [0x76; 64], [0x76; 32], false, 1_500_000_000, 40_000_000_000_000, 35_700_000_000, 905_000_000_000_000, &launch);
    assert!(p.pos[&mint].exit.is_none());
    // log mode (the default; also by the control key after live): recorded once, no exit
    let (mut p, _atx, orx, mint, launch) = open(&["--presend-live-dump-exit", "1.0:0:0"]);
    let _ = p.take_cmds();
    let ch = p.ctl43_apply(&ps43::ctl43_parse(br#"{"dump_exit": "live"}"#).unwrap());
    assert!(ch.iter().any(|c| c.0 == "dump_exit"));
    let ch = p.ctl43_apply(&ps43::ctl43_parse(br#"{"dump_exit": "log"}"#).unwrap());
    assert!(ch.iter().any(|c| c.0 == "dump_exit"));
    trade(&mut p, N, 242, [0x77; 64], [0x77; 32], false, 1_500_000_000, 40_000_000_000_000, 35_700_000_000, 905_000_000_000_000, &launch);
    trade(&mut p, N, 243, [0x78; 64], [0x78; 32], false, 1_500_000_000, 40_000_000_000_000, 34_300_000_000, 945_000_000_000_000, &launch);
    assert!(p.pos[&mint].exit.is_none() || p.pos[&mint].exit.map(|x| x.0) == Some("stop-loss"));
    let r = recs(&orx);
    let d: Vec<_> = r.iter().filter(|x| x["ev"] == "presend_live_dump_exit").collect();
    assert_eq!(d.len(), 1, "once per position");
    assert_eq!(d[0]["would"].as_bool(), Some(true));
}

/// flags: parse ranges; whale-ledger kinds
#[test]
fn dip43e_flags() {
    assert_eq!(dump_exit_parse("1.0:0:0").unwrap(), (1_000_000_000, 0, 0.0));
    assert_eq!(dump_exit_parse("0:2.5:0.1").unwrap(), (0, 2_500_000_000, 0.1));
    for bad in ["0:0:0", "1:1", "x:1:0", "1:1:0.9", "60:0:0"] { assert!(dump_exit_parse(bad).is_err(), "{bad}"); }
    let (p, ..) = open(&[]);
    assert!(p.cfg.dump_exit.is_none() && p.cfg.wh_kinds == 3, "off / all by default");
    let (p, ..) = open(&["--presend-live-wh-loss", "2:0.3", "--presend-live-wh-kinds", "t2"]);
    assert!(p.cfg.wh_kind_ok(false) && !p.cfg.wh_kind_ok(true));
}
