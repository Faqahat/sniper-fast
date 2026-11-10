// ===================================================================================================================
// dip40 REACT R1 tests (react_r1.rs + dipmode.rs r1_trade / r1_act). The frozen rule's every condition at its boundaries, the windows
// (prior 200 / dip buyers 200 / bots 100 / anchor 200), the anchor's position, our own trades left out, no look-ahead (a candidate is
// decided on the trades seen before it; its own trade and later ones never count), the price guard, the token block, the flags, and
// PARITY with the study's own feature code on 120 random tapes (ops/strategies/react_r1/r1_parity_fixture.py ->
// testdata/dip40_r1_parity.json). The lane end to end in log mode (r1_trade: records, rule fails, skips, block).
// ===================================================================================================================
use super::react_r1::*;
use super::*;
use arbx::dip::TradeEvent;
use rustc_hash::FxHashSet;

const USER: Pk = [0x5Au8; 32];
const S: u64 = 1_000_000_000;
fn w(k: u8) -> Pk { let mut x = [k; 32]; x[31] = 0x40; x }
fn anchor() -> Pk { pk(ANCHOR_DEFAULT) }
fn pct(x: f64) -> u64 { (x * PCT1 as f64).round() as u64 }
fn bots(ks: &[u8]) -> FxHashSet<Pk> { ks.iter().map(|k| w(*k)).collect() }
const MINT: Pk = [0x71u8; 32];
const C0: u64 = 1_000;

/// a book with MINT created at C0
fn book() -> Book { let mut b = Book::new(anchor(), USER); b.create(MINT, C0, false); b }
/// a trade into the book (as r1_trade: after its decision)
fn t(b: &mut Book, user: Pk, buy: bool, sol: u64, tok: u64, s: u64) { let i = b.m[&MINT].tr.len() as u64; b.push(&MINT, user, buy, sol, tok, s, i); }
/// a passing set-up at slot C0 + 10: an earlier 1.5% sell, 2 dip buyers after a 0.5 SOL sell, 5 listed bots, the anchor bought 2%
fn pass_book() -> (Book, FxHashSet<Pk>) {
    let mut b = book();
    let bl = bots(&[1, 2, 3, 4, 5, 6]);
    for k in 1..=5u8 { t(&mut b, w(k), true, S / 2, pct(1.0), C0 + 1); }
    t(&mut b, anchor(), true, S, pct(2.0), C0 + 2);
    t(&mut b, w(20), false, S / 2, pct(1.5), C0 + 4);           // prior >= 1%, a big sell (>= 0.3 SOL)
    t(&mut b, w(21), true, S / 10, pct(0.3), C0 + 5);           // dip buyer 1 (1 slot after)
    t(&mut b, w(22), true, S / 10, pct(0.3), C0 + 6);           // dip buyer 2 (2 slots after)
    (b, bl)
}
fn feat(b: &Book, bl: &FxHashSet<Pk>, s: u64, sol: u64, tok: u64) -> Feat { b.features(&MINT, s, sol, tok, bl).unwrap() }

#[test]
fn r1_passes_and_each_condition_fails_alone() {
    let (b, bl) = pass_book();
    let f = feat(&b, &bl, C0 + 10, S, pct(4.0));
    assert_eq!((f.age, f.prior1, f.dipb, f.bots, f.anchor_hold), (10, 1, 2, 5, true));
    assert!(f.pass(), "{:?}", f.fails());
    // each condition alone
    let one = |g: Feat, why: &str| assert_eq!(g.fails(), vec![why], "{g:?}");
    one(Feat { sol: MIN_SELL_SOL - 1, ..f }, "sell_sol");
    one(Feat { tok: pct(2.99), ..f }, "pct");
    one(Feat { tok: PCT_HI, ..f }, "pct");
    one(Feat { age: AGE_MAX + 1, ..f }, "age");
    one(Feat { prior1: 0, ..f }, "prior");
    one(Feat { dipb: 1, ..f }, "dipb");
    one(Feat { bots: 4, ..f }, "bots");
    one(Feat { anchor_hold: false, ..f }, "anchor");
    // boundaries that pass: exactly 3%, just under 6%, exactly 0.2 SOL, age exactly 30
    assert!(Feat { tok: PCT_LO, ..f }.pass());
    assert!(Feat { tok: PCT_HI - 1, ..f }.pass());
    assert!(Feat { sol: MIN_SELL_SOL, ..f }.pass());
    assert!(Feat { age: AGE_MAX, ..f }.pass());
    assert_eq!(Feat { sol: 0, tok: 0, age: 99, prior1: 0, dipb: 0, bots: 0, anchor_hold: false, ..f }.fails(), vec!["sell_sol", "pct", "age", "prior", "dipb", "bots", "anchor"]);
    // the age from the book's create slot
    assert_eq!(feat(&b, &bl, C0 + 30, S, pct(4.0)).age, 30);
    assert!(feat(&b, &bl, C0 + 30, S, pct(4.0)).pass());
    assert_eq!(feat(&b, &bl, C0 + 31, S, pct(4.0)).fails(), vec!["age"]);
    // not followed (create unseen): no candidate at all
    assert!(b.features(&[9u8; 32], C0 + 10, S, pct(4.0), &bl).is_none());
}

#[test]
fn r1_prior_window_size_and_ours() {
    let bl = bots(&[]);
    let mut b = book();
    let s = C0 + 300;
    t(&mut b, w(30), false, S, pct(0.99), s - 10);              // < 1%: no
    t(&mut b, USER, false, S, pct(5.0), s - 10);                // ours: no
    t(&mut b, w(31), true, S, pct(5.0), s - 10);                // a buy: no
    assert_eq!(feat(&b, &bl, s, S, pct(4.0)).prior1, 0);
    t(&mut b, w(32), false, 1, pct(1.0), s - 201);              // 201 slots before: out of the window
    assert_eq!(feat(&b, &bl, s, S, pct(4.0)).prior1, 0);
    t(&mut b, w(33), false, 1, pct(1.0), s - 200);              // exactly 200: in (any SOL size)
    assert_eq!(feat(&b, &bl, s, S, pct(4.0)).prior1, 1);
    t(&mut b, w(33), false, S, pct(1.2), s);                    // same slot, seen before: in (the same seller counts again)
    assert_eq!(feat(&b, &bl, s, S, pct(4.0)).prior1, 2);
}

#[test]
fn r1_dip_buyers() {
    let bl = bots(&[]);
    let mut b = book();
    let s = C0 + 20;
    t(&mut b, w(40), true, S / 10, pct(0.1), C0 + 1);           // a buy before any big sell: no
    t(&mut b, w(41), false, DIP_SELL - 1, pct(0.5), C0 + 2);    // 0.29.. SOL: not a big sell
    t(&mut b, w(42), true, S / 10, pct(0.1), C0 + 2);           // after a small sell: no
    assert_eq!(feat(&b, &bl, s, S, pct(4.0)).dipb, 0);
    t(&mut b, w(43), false, DIP_SELL, pct(0.5), C0 + 5);        // exactly 0.3 SOL: big
    t(&mut b, w(44), true, S / 10, pct(0.1), C0 + 5);           // same slot after it: yes
    t(&mut b, w(45), true, S / 10, pct(0.1), C0 + 7);           // 2 slots after: yes
    t(&mut b, w(46), true, S / 10, pct(0.1), C0 + 8);           // 3 slots after: no
    t(&mut b, USER, true, S / 10, pct(0.1), C0 + 6);            // ours: no
    t(&mut b, w(44), true, S / 10, pct(0.1), C0 + 6);           // the same wallet again: counted once
    assert_eq!(feat(&b, &bl, s, S, pct(4.0)).dipb, 2);
    // OUR big sell is a big sell too (sim.py lastbig: every sell >= 0.3 SOL)
    t(&mut b, USER, false, S, pct(0.5), C0 + 12);
    t(&mut b, w(47), true, S / 10, pct(0.1), C0 + 13);
    assert_eq!(feat(&b, &bl, s, S, pct(4.0)).dipb, 3);
    // the window: a dip buy 201 slots before the dump does not count (200 does)
    let mut b2 = book();
    t(&mut b2, w(50), false, S, pct(0.5), C0 + 100);
    t(&mut b2, w(51), true, 1, 1, C0 + 100);
    t(&mut b2, w(52), true, 1, 1, C0 + 101);
    assert_eq!(feat(&b2, &bl, C0 + 301, S, pct(4.0)).dipb, 1);
    assert_eq!(feat(&b2, &bl, C0 + 300, S, pct(4.0)).dipb, 2);
}

#[test]
fn r1_listed_bots() {
    let bl = bots(&[1, 2, 3, 4, 5, 6, 7]);
    let mut b = book();
    let s = C0 + 150;
    for k in 1..=4u8 { t(&mut b, w(k), k % 2 == 0, S / 100, 1, s - 100); }   // buys and sells, any size; exactly 100 slots: in
    t(&mut b, w(4), true, 1, 1, s - 1);                                        // the same wallet again: once
    t(&mut b, w(9), true, 1, 1, s - 1);                                        // not listed
    assert_eq!(feat(&b, &bl, s, S, pct(4.0)).bots, 4);
    t(&mut b, w(5), true, 1, 1, s - 101);                                      // 101 slots: out
    assert_eq!(feat(&b, &bl, s, S, pct(4.0)).bots, 4);
    t(&mut b, w(6), false, 1, 1, s);                                           // same slot, seen before: in
    assert_eq!(feat(&b, &bl, s, S, pct(4.0)).bots, 5);
    // our wallet never counts, even when listed (list_parse drops it; the book too)
    let mut bl2 = bl.clone(); bl2.insert(USER);
    t(&mut b, USER, true, 1, 1, s);
    assert_eq!(feat(&b, &bl2, s, S, pct(4.0)).bots, 5);
}

#[test]
fn r1_anchor_holds() {
    let bl = bots(&[]);
    let mut b = book();
    let s = C0 + 20;
    assert!(!feat(&b, &bl, s, S, pct(4.0)).anchor_hold);
    t(&mut b, anchor(), true, S, ANCHOR_HOLD as u64, C0 + 1);           // exactly 1e10 raw: not holding (> 1e10)
    assert!(!feat(&b, &bl, s, S, pct(4.0)).anchor_hold);
    t(&mut b, anchor(), true, S, 1, C0 + 2);                            // 1e10 + 1: holding
    let f = feat(&b, &bl, s, S, pct(4.0));
    assert!(f.anchor_hold);
    assert_eq!((f.anchor_pos, f.anchor_last), (ANCHOR_HOLD + 1, Some(C0 + 2)));
    t(&mut b, anchor(), false, S, ANCHOR_HOLD as u64 + 1, C0 + 3);      // sold it all
    assert!(!feat(&b, &bl, s, S, pct(4.0)).anchor_hold);
    t(&mut b, anchor(), true, S, pct(1.0), C0 + 4);                     // bought again
    assert!(feat(&b, &bl, s, S, pct(4.0)).anchor_hold);
    // the latest anchor trade must be within 200 slots of the dump (sim.py scans back to w200 only)
    assert!(feat(&b, &bl, C0 + 204, S, pct(4.0)).anchor_hold);
    assert!(!feat(&b, &bl, C0 + 205, S, pct(4.0)).anchor_hold);
    // other wallets' trades never move it; an anchor at another address is another wallet
    let mut b2 = Book::new(w(77), USER); b2.create(MINT, C0, false);
    b2.push(&MINT, anchor(), true, S, pct(3.0), C0 + 1, 0);
    assert!(!b2.features(&MINT, s, S, pct(4.0), &bl).unwrap().anchor_hold);
    b2.push(&MINT, w(77), true, S, pct(3.0), C0 + 1, 1);
    assert!(b2.features(&MINT, s, S, pct(4.0), &bl).unwrap().anchor_hold);
}

#[test]
fn r1_no_look_ahead() {
    // the dump itself and everything seen after it never count in its features (r1_trade: features, then push)
    let (mut b, bl) = pass_book();
    let s = C0 + 10;
    let before = feat(&b, &bl, s, S, pct(4.0));
    // as r1_trade: decide, then the dump enters the book
    t(&mut b, w(30), false, S, pct(4.0), s);
    // trades after it (same slot and later): a buyer, more bots, the anchor selling out, another big sell
    t(&mut b, w(6), true, S, pct(0.2), s);
    t(&mut b, w(60), true, S, pct(0.2), s);
    t(&mut b, anchor(), false, S, pct(2.0), s + 1);
    // the same candidate re-scored on the prefix it saw is unchanged: features are a function of the book at decision time only
    let mut pre = book();
    for x in &b.m[&MINT].tr { if (x.s, x.i) < (s, 9) { pre.push(&MINT, x.user, x.buy, x.sol, x.tok, x.s, x.i); } }
    assert_eq!(feat(&pre, &bl, s, S, pct(4.0)), before);
    // the dump's own 4% sell is NOT its own "prior" (the prefix had one: the 1.5% sell); the NEXT candidate in the same slot sees it
    assert_eq!(before.prior1, 1);
    let next = feat(&b, &bl, s, S, pct(3.5));
    assert_eq!(next.prior1, 3);                                 // the 1.5% sell, the 4% dump, the anchor's 2% sell (all seen before it)
    // ... and sees the buyer after the dump as a dip buyer (the dump >= 0.3 SOL) and the anchor's later sell
    assert_eq!(next.dipb, 4, "{next:?}");
    assert!(!next.anchor_hold);
    assert_eq!(next.bots, 6);
}

#[test]
fn r1_parity_with_study() {
    // the study's own feature code (sim.py run_mint, test.py mask R1_hqadd) on 120 random tapes vs the book replayed in tape order
    let j: serde_json::Value = serde_json::from_str(include_str!("../../../testdata/dip40_r1_parity.json")).unwrap();
    let id = |k: u64| -> Pk { let mut x = [0u8; 32]; x[..8].copy_from_slice(&k.to_le_bytes()); x[31] = 0xAA; x };
    let me = id(j["ours"].as_u64().unwrap());
    let anc = id(j["anchor"].as_u64().unwrap());
    let bl: FxHashSet<Pk> = j["bots"].as_array().unwrap().iter().map(|x| id(x.as_u64().unwrap())).collect();
    let (mut n, mut passes, mut fails_seen) = (0, 0, std::collections::BTreeSet::new());
    for (mi, m) in j["mints"].as_array().unwrap().iter().enumerate() {
        let mint: Pk = { let mut x = [0x33u8; 32]; x[..8].copy_from_slice(&(mi as u64).to_le_bytes()); x };
        let mut b = Book::new(anc, me);
        b.create(mint, m["lslot"].as_u64().unwrap(), false);
        let exp: HashMap<u64, &serde_json::Value> = m["expect"].as_array().unwrap().iter().map(|f| (f["j"].as_u64().unwrap(), f)).collect();
        for (k, tr) in m["trades"].as_array().unwrap().iter().enumerate() {
            let v: Vec<u64> = tr.as_array().unwrap().iter().map(|x| x.as_u64().unwrap()).collect();
            let (s, i, buy, sol, tok, u) = (v[0], v[1], v[2] == 1, v[3], v[4], id(v[5]));
            let cand = is_candidate(buy, &u, &me, tok);
            let f = if cand { b.features(&mint, s, sol, tok, &bl) } else { None };
            b.push(&mint, u, buy, sol, tok, s, i);
            match (exp.get(&(k as u64)), f) {
                (Some(e), Some(f)) => {
                    n += 1;
                    let ctx = format!("mint {mi} trade {k}: {e} vs {f:?}");
                    assert_eq!(f.age, e["age"].as_u64().unwrap(), "{ctx}");
                    assert_eq!(f.prior1 as u64, e["prior1"].as_u64().unwrap(), "{ctx}");
                    assert_eq!(f.dipb as u64, e["dipb"].as_u64().unwrap(), "{ctx}");
                    assert_eq!(f.bots as u64, e["bots100"].as_u64().unwrap(), "{ctx}");
                    assert_eq!(f.anchor_hold, e["hq_hold"].as_bool().unwrap(), "{ctx}");
                    assert!((f.pct() - e["dpct"].as_f64().unwrap()).abs() < 1e-9, "{ctx}");
                    assert_eq!(f.pass(), e["pass"].as_bool().unwrap(), "{ctx}");
                    passes += f.pass() as u32;
                    for x in f.fails() { fails_seen.insert(x); }
                }
                // a candidate of ours the study skips: only a sell under 0.2 SOL (the rule then fails it on sell_sol)
                (None, Some(f)) => { assert!(f.sol < MIN_SELL_SOL, "mint {mi} trade {k}: not a study candidate but {f:?}"); assert!(!f.pass()); }
                (Some(e), None) => panic!("mint {mi} trade {k}: a study candidate the lane did not see: {e}"),
                (None, None) => {}
            }
        }
    }
    assert!(n > 2000 && passes >= 20, "candidates {n}, passes {passes}");
    // every condition failed somewhere (the fixture exercises them all)
    for x in ["pct", "age", "prior", "dipb", "bots", "anchor"] { assert!(fails_seen.contains(x), "{x} never failed in the fixture"); }
}

#[test]
fn r1_price_guard() {
    let (v, tk) = (40 * S, 800_000_000_000_000u64);
    let fr = 0.0125;
    let q = |vs: f64, vt: f64, sp: f64| { let x = (sp / (1.0 + fr)).floor(); (vt * x / (vs + x)).floor() as u64 };
    // x1.0 = the plain quote on the post-dump curve
    assert_eq!(min_out_price(S / 10, fr, v, tk, 1.0), q(v as f64, tk as f64, 1e8));
    // x1.10: the tokens the same SOL buys on the constant-product curve at virtual SOL sqrt(1.1) x V (price 1.1 x)
    let k = v as f64 * tk as f64;
    let vs = v as f64 * 1.1f64.sqrt();
    let m = min_out_price(S / 10, fr, v, tk, 1.10);
    assert_eq!(m, q(vs, k / vs, 1e8));
    // a curve whose price is <= 1.1 x fills (more tokens than the minimum); above it does not
    let at = |p: f64| { let vs = v as f64 * p.sqrt(); q(vs, k / vs, 1e8) };
    assert!(at(1.0) > m && at(1.05) > m && at(1.0999) >= m);
    assert!(at(1.1001) < m && at(1.2) < m);
    // never 0 (pump refuses a 0 minimum)
    assert_eq!(min_out_price(0, 0.0, v, tk, 1.5), 1);
}

#[test]
fn r1_token_block_and_prune() {
    // ev.py block: a pick at s blocks the token through s + h (exit 4: s .. s + 4 blocked, s + 5 free)
    assert!(!blocked(None, 100, 4));
    assert!(blocked(Some(100), 100, 4) && blocked(Some(100), 104, 4));
    assert!(!blocked(Some(100), 105, 4));
    // the book drops a token KEEP_SLOTS after its create unless kept (an open position)
    let mut b = book();
    b.create([0x72; 32], C0, false);
    b.prune(C0 + KEEP_SLOTS, |_| false);
    assert_eq!(b.m.len(), 2);
    b.prune(C0 + KEEP_SLOTS + 11, |m| *m == MINT);
    assert_eq!(b.m.len(), 1);
    assert!(b.m.contains_key(&MINT));
    // a second create of a followed token keeps its book
    t(&mut b, w(1), true, 1, 1, C0 + 1);
    b.create(MINT, C0 + 50, true);
    assert_eq!((b.m[&MINT].create_slot, b.m[&MINT].tr.len(), b.m[&MINT].mayhem), (C0, 1, false));
}

fn argv(extra: &[&str]) -> Vec<String> { ["snipe_engine", "--dip"].iter().chain(extra.iter()).map(|s| s.to_string()).collect() }
fn blist(n: u8) -> Vec<u8> { serde_json::json!((1..=n).map(|k| b58(&w(k))).collect::<Vec<_>>()).to_string().into_bytes() }
fn cfg(extra: &[&str], live: bool) -> Result<Option<Cfg>> { Cfg::from_argv(&argv(extra), live, &USER, Some(&blist(8))) }

#[test]
fn r1_flags() {
    // off without the flag; any lane flag alone is refused
    assert!(cfg(&[], true).unwrap().is_none());
    for f in FLAGS.iter().skip(1) {
        let e = cfg(&[f, "1"], true).unwrap_err().to_string();
        assert!(e.contains("needs --react-r1 log|live"), "{f}: {e}");
    }
    // defaults (the frozen R1 exit 4, 1.10, haqq6 anchor; TP / SL off)
    let c = cfg(&["--react-r1", "log", "--react-r1-bots", "/x.json"], false).unwrap().unwrap();
    assert_eq!((c.mode, c.size, c.exit_slots, c.max_open, c.max_per_min, c.max_price), (Mode::Log, 100_000_000, 4, 1, 10, 1.10));
    assert_eq!(b58(&c.anchor), ANCHOR_DEFAULT);
    assert!(c.tp.is_infinite() && c.sl.is_infinite());
    assert_eq!(c.bots.len(), 8);
    assert_eq!(c.json()["tp"], serde_json::Value::Null);
    assert_eq!(c.json()["rule"]["policy"], "R1_hqadd");
    // the probe's line
    let c = cfg(&["--react-r1", "live", "--react-r1-bots", "/x", "--react-r1-size-sol", "0.1", "--react-r1-exit-slots", "4", "--react-r1-max-open", "1",
                  "--react-r1-max-per-min", "6", "--react-r1-tp", "0.2", "--react-r1-sl", "0.3", "--react-r1-anchor", &b58(&w(9))], true).unwrap().unwrap();
    assert_eq!((c.mode, c.size, c.max_per_min, c.tp, c.sl, c.anchor), (Mode::Live, 100_000_000, 6, 0.2, 0.3, w(9)));
    // refusals
    for (x, live, want) in [
        (&["--react-r1", "on", "--react-r1-bots", "/x"][..], true, "log | live"),
        (&["--react-r1", "live", "--react-r1-bots", "/x"][..], false, "needs --live"),
        (&["--react-r1", "log"][..], true, "needs --react-r1-bots"),
        (&["--react-r1", "log", "--react-r1-bots", "--minutes"][..], true, "needs a file"),
        (&["--react-r1", "log", "--react-r1-bots", "/x", "--react-r1-size-sol", "0.04"][..], true, "0.05..1.0"),
        (&["--react-r1", "log", "--react-r1-bots", "/x", "--react-r1-size-sol", "1.01"][..], true, "0.05..1.0"),
        (&["--react-r1", "log", "--react-r1-bots", "/x", "--react-r1-size-sol", "x"][..], true, "not a number"),
        (&["--react-r1", "log", "--react-r1-bots", "/x", "--react-r1-exit-slots", "0"][..], true, "1..25"),
        (&["--react-r1", "log", "--react-r1-bots", "/x", "--react-r1-exit-slots", "2.5"][..], true, "not a whole number"),
        (&["--react-r1", "log", "--react-r1-bots", "/x", "--react-r1-max-open", "4"][..], true, "1..3"),
        (&["--react-r1", "log", "--react-r1-bots", "/x", "--react-r1-max-per-min", "0"][..], true, "1..60"),
        (&["--react-r1", "log", "--react-r1-bots", "/x", "--react-r1-anchor", "nope"][..], true, "not a wallet"),
        (&["--react-r1", "log", "--react-r1-bots", "/x", "--react-r1-tp", "0.001"][..], true, "0 (off) or 0.01..1"),
        (&["--react-r1", "log", "--react-r1-bots", "/x", "--react-r1-sl", "0.95"][..], true, "0 (off) or 0.01..0.9"),
        (&["--react-r1", "log", "--react-r1-bots", "/x", "--react-r1-max-price", "0.9"][..], true, "1.0..1.5"),
    ] {
        let e = cfg(x, live).unwrap_err().to_string();
        assert!(e.contains(want), "{x:?}: {e}");
    }
    let me = b58(&USER);
    let e = cfg(&["--react-r1", "log", "--react-r1-bots", "/x", "--react-r1-anchor", &me], true).unwrap_err().to_string();
    assert!(e.contains("our own wallet"), "{e}");
    // the bot list: a bad file, too few wallets, the registry format
    let bad = Cfg::from_argv(&argv(&["--react-r1", "log", "--react-r1-bots", "/x"]), true, &USER, Some(b"{}")).unwrap_err().to_string();
    assert!(bad.contains("--react-r1-bots /x"), "{bad}");
    let few = Cfg::from_argv(&argv(&["--react-r1", "log", "--react-r1-bots", "/x"]), true, &USER, Some(&blist(4))).unwrap_err().to_string();
    assert!(few.contains("fewer than the rule's 5"), "{few}");
    let reg = serde_json::json!({"wallets": (1..=6u8).map(|k| serde_json::json!({"wallet": b58(&w(k)), "state": "retired"})).collect::<Vec<_>>()}).to_string();
    assert_eq!(Cfg::from_argv(&argv(&["--react-r1", "log", "--react-r1-bots", "/x"]), true, &USER, Some(reg.as_bytes())).unwrap().unwrap().bots.len(), 6);
    let missing = Cfg::from_argv(&argv(&["--react-r1", "log", "--react-r1-bots", "/nonexistent/dip40.json"]), true, &USER, None).unwrap_err().to_string();
    assert!(missing.contains("read"), "{missing}");
    // the engine's flag check knows every lane flag and types the numeric ones
    let ok = argv(&["--react-r1", "live", "--react-r1-bots", "/x", "--react-r1-size-sol", "0.1", "--react-r1-exit-slots", "4", "--react-r1-max-open", "1",
                    "--react-r1-max-per-min", "6", "--react-r1-tp", "0", "--react-r1-sl", "0", "--react-r1-anchor", ANCHOR_DEFAULT, "--react-r1-max-price", "1.1"]);
    assert!(crate::check_flags(&ok).is_ok(), "{:?}", crate::check_flags(&ok));
    assert!(crate::check_flags(&argv(&["--react-r1-exit-slots", "x"])).is_err());
    assert!(crate::check_flags(&argv(&["--react-r1-size-sol", "-1"])).is_err());
    assert!(crate::check_flags(&argv(&["--react-r1-bogus", "1"])).is_err());
}

// ---- the lane end to end (log mode: r1_trade decides, logs, never sends)

struct Lane { r1: react_r1::R1, toks: HashMap<Pk, Tok>, open: HashMap<Pk, LivePos>, pend: Vec<Pend>, log: DipLog, path: String, idx: u64 }
impl Lane {
    fn new(name: &str, extra: &[&str]) -> Lane {
        let mut a = vec!["--react-r1", "log", "--react-r1-bots", "/x"];
        a.extend_from_slice(extra);
        let c = Cfg::from_argv(&argv(&a), false, &USER, Some(&blist(8))).unwrap().unwrap();
        let path = std::env::temp_dir().join(format!("dip40-r1-{}-{name}.jsonl", std::process::id())).to_string_lossy().to_string();
        let _ = std::fs::remove_file(&path);
        Lane { r1: react_r1::R1::new(c, USER), toks: HashMap::new(), open: HashMap::new(), pend: Vec::new(), log: DipLog::open(Some(path.clone())).unwrap(), path, idx: 0 }
    }
    fn create(&mut self, mint: Pk, slot: u64, mayhem: bool) {
        let mut launch = snipe_build::launch_from_target(mint, w(0xCC));
        launch.is_mayhem = mayhem;
        let li = LaunchInfo { slot, idx: Some(0), creator: None, signer: None, sig: String::new(), mayhem };
        self.toks.insert(mint, Tok { book: TokenBook::new(li), launch: Some(launch), t_created: Instant::now(), last_pick_slot: None, dev: false, keys: None });
        self.r1.book.create(mint, slot, mayhem);
    }
    fn trade(&mut self, mint: Pk, user: Pk, buy: bool, sol: u64, tok: u64, slot: u64) {
        self.idx += 1;
        let e = TradeEvent { mint, sol, tok, buy, user, vsol: 40 * S, vtok: 800_000_000_000_000, fbps: 95, cbps: 30 };
        let x = arbx::feeds::ExecInfo { index: self.idx, fee: 5_000, ok: true, trades: vec![e.clone()], creates: vec![], mayhem: false };
        let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&self.idx.to_be_bytes());
        let a = arbx::feeds::Arrival { feed: 0, slot, t_rx: slot * 1_000_000, t_decoded: slot * 1_000_000, executed: Some(true),
            tx: arbx::tx::Tx { sig, keys: vec![[0x77; 32]], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        let (mtx, _mrx) = tokio::sync::mpsc::unbounded_channel::<Msg>();
        let names: Vec<String> = vec!["feed".into()];
        r1_trade(&mut self.r1, &e, &a, &x, 0, &bs58::encode(&sig).into_string(), a.t_rx, &self.toks, &mut self.open, &mut self.pend,
            R1Ctx { allow_holder: true, skip_clients: None, pslive: None, npool: None, fast: None, user: USER, mtx: &mtx, log: &self.log, names: &names, net: None });
    }
    fn recs(&self) -> Vec<serde_json::Value> {
        std::fs::read_to_string(&self.path).unwrap_or_default().lines().map(|l| serde_json::from_str(l).unwrap()).collect()
    }
    /// the passing set-up on `mint` created at `c0`: 5 bots, the anchor, a 1.5% big sell, 2 dip buyers
    fn setup(&mut self, mint: Pk, c0: u64, mayhem: bool) {
        self.create(mint, c0, mayhem);
        for k in 1..=5u8 { self.trade(mint, w(k), true, S / 2, pct(1.0), c0 + 1); }
        self.trade(mint, anchor(), true, S, pct(2.0), c0 + 2);
        self.trade(mint, w(20), false, S / 2, pct(1.5), c0 + 4);
        self.trade(mint, w(21), true, S / 10, pct(0.3), c0 + 5);
        self.trade(mint, w(22), true, S / 10, pct(0.3), c0 + 6);
    }
}

#[test]
fn r1_lane_log_mode_end_to_end() {
    let mut l = Lane::new("e2e", &[]);
    l.setup(MINT, C0, false);
    // the set-up's own 1.5% sell was a candidate that failed (pct; no prior sell, no dip buyer before it)
    let d = l.recs().into_iter().filter(|r| r["ev"] == "react_r1_decision").collect::<Vec<_>>();
    assert_eq!(d.len(), 1);
    assert_eq!(d[0]["act"], "rule_fail");
    assert_eq!(d[0]["fails"], serde_json::json!(["pct", "prior", "dipb"]));
    // the dump: 4% by another wallet at age 10 -> pass, log mode: "log" (never sent: no position, no pending fire)
    l.trade(MINT, w(30), false, S, pct(4.0), C0 + 10);
    let d = l.recs().into_iter().filter(|r| r["ev"] == "react_r1_decision").last().unwrap();
    assert_eq!(d["act"], "log", "{d}");
    assert_eq!(d["rule_pass"], true);
    assert_eq!(d["mode"], "log");
    assert_eq!(d["seller"], b58(&w(30)));
    assert_eq!((d["feat"]["age"].as_u64(), d["feat"]["prior1"].as_u64(), d["feat"]["dipb"].as_u64(), d["feat"]["bots"].as_u64()), (Some(10), Some(1), Some(2), Some(5)));
    assert_eq!(d["feat"]["anchor_hold"], true);
    assert!(l.open.is_empty() && l.pend.is_empty());
    assert_eq!((l.r1.st.cand, l.r1.st.pass, l.r1.st.logged, l.r1.st.fired), (2, 1, 1, 0));
    // a second pass on the token within its block (exit 4 -> through slot + 4) is skipped; after it, decided again
    l.trade(MINT, w(31), false, S, pct(3.2), C0 + 14);
    let d = l.recs().into_iter().filter(|r| r["ev"] == "react_r1_decision").last().unwrap();
    assert_eq!(d["act"], "skip:token_blocked", "{d}");
    l.trade(MINT, w(32), false, S, pct(3.2), C0 + 15);
    let d = l.recs().into_iter().filter(|r| r["ev"] == "react_r1_decision").last().unwrap();
    assert_eq!(d["act"], "log", "{d}");
    // too old: age 31
    l.trade(MINT, w(33), false, S, pct(3.2), C0 + 31);
    let d = l.recs().into_iter().filter(|r| r["ev"] == "react_r1_decision").last().unwrap();
    assert_eq!((d["act"].as_str(), d["fails"].clone()), (Some("rule_fail"), serde_json::json!(["age"])));
    // our own sells and buys are never candidates; neither are sells < 1% of supply
    let n = l.recs().len();
    l.trade(MINT, USER, false, S, pct(4.0), C0 + 16);
    l.trade(MINT, w(34), false, S, pct(0.99), C0 + 16);
    l.trade(MINT, w(34), true, S, pct(4.0), C0 + 16);
    assert_eq!(l.recs().len(), n);
    // a mayhem token: the rule passes, the lane skips it
    let m2 = [0x72u8; 32];
    l.setup(m2, C0, true);
    l.trade(m2, w(30), false, S, pct(4.0), C0 + 10);
    let d = l.recs().into_iter().filter(|r| r["ev"] == "react_r1_decision").last().unwrap();
    assert_eq!((d["rule_pass"].as_bool(), d["act"].as_str()), (Some(true), Some("skip:mayhem")));
    // a token whose create was not seen: nothing (no candidate, no record)
    let n = l.recs().len();
    l.trade([0x73; 32], w(30), false, S, pct(4.0), C0 + 10);
    assert_eq!(l.recs().len(), n);
    assert_eq!(l.r1.st.skips.get("token_blocked"), Some(&1));
    assert_eq!(l.r1.st.skips.get("mayhem"), Some(&1));
    let _ = std::fs::remove_file(&l.path);
}

#[test]
fn r1_lane_skips_a_held_mint() {
    // a position (any lane) on the mint: never a second buy (the study's ours_ov exclusion); the block is not taken by it
    let mut l = Lane::new("held", &[]);
    l.setup(MINT, C0, false);
    let launch = l.toks[&MINT].launch.clone().unwrap();
    l.open.insert(MINT, LivePos { mint: MINT, launch, dump_sig: String::new(), dump_slot: C0, dump_idx: 0, t_dump_rx: 0, dump_vsol: 0, dump_vtok: 0, score: 0.0, t_fire_ns: 0,
        buy_sig: String::new(), buy_sig_b: [0; 64], route: String::new(), leader: String::new(), client: String::new(), tips: 0, spend: 0, min_out: 0, send_slot: 0,
        land: None, tokens: 0, sol_in: 0, buy_ok: None, exit: None, sell_land: None, pos: None, fired_at: Instant::now(), vars: Vec::new(), xr: None });
    l.trade(MINT, w(30), false, S, pct(4.0), C0 + 10);
    let d = l.recs().into_iter().filter(|r| r["ev"] == "react_r1_decision").last().unwrap();
    assert_eq!(d["act"], "skip:open_on_token");
    l.open.clear();
    l.trade(MINT, w(31), false, S, pct(4.0), C0 + 11);
    let d = l.recs().into_iter().filter(|r| r["ev"] == "react_r1_decision").last().unwrap();
    assert_eq!(d["act"], "log", "{d}");
    let _ = std::fs::remove_file(&l.path);
}

#[test]
fn r1_realized_record_and_counters() {
    let before = (RZ_N.load(Ordering::SeqCst), RZ_WINS.load(Ordering::SeqCst));
    let r = realized_rec(&MINT, "sig1", 1_234, "tx", Some(-100_000_000), 100_000_000);
    assert_eq!((r["ev"].as_str(), r["pnl"].as_i64(), r["src"].as_str(), r["buy_delta"].as_i64()), (Some("react_r1_realized"), Some(1_234), Some("tx"), Some(-100_000_000)));
    let _ = realized_rec(&MINT, "sig2", -5, "feed", None, 100_000_000);
    let after = (RZ_N.load(Ordering::SeqCst), RZ_WINS.load(Ordering::SeqCst));
    assert!(after.0 >= before.0 + 2 && after.1 > before.1);
}
