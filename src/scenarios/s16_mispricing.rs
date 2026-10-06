//! S16 (PLAN WP-09; F42: the old bot's real losses that phantoms do not explain; docs/research/wallet-synthesis.md
//! section 4, "real gap, but our quote was wrong anyway"). The fixtures are real, all in testdata/scenarios/s16/
//! (`tools/capture-fixtures.py --s16`): the pools of w5h3-p2#664 as they are now, the chain's records of both cases'
//! landings and of #664's trigger, and the old bot's attempt and outcome lines of both (from testdata/legacy/raw/w5h3-p2
//! and w5h2-p10's own files).
//!
//! - **w5h3-p2#664** (4.2 SOL bought 3Dgwn5E7...pump on PumpSwap DreMAMRc, sold on DLMM AwmaWjsR; expected 454.5M; the
//!   landing failed the route's profit check, round trip −138.6M on chain). The CP-family leg is rebuilt from the
//!   landing's pre-token balances (the pool's reserves at its execution: 37,410,941,865,369 base, 540,192,702,838 quote,
//!   also in its BuyEvent) and the current pool account, but for its virtual quote reserve V, which has moved since: V
//!   then is pinned by the PumpSwap events of the two transactions (the trigger's SellEvent a slot before, on its own:
//!   17,579,766,263-333; our BuyEvent: 284-285; today's account: 17,583,646,841). The run boots on those pools, receives
//!   the rebuilt pool and vaults as one transaction's state-stream writes and prices the route (the decisions, replayed).
//!   arbx's quote of the buy at 4.2 SOL is the chain's to the unit: 276,985,551,117 tokens (the route program's NXV2OUT
//!   for leg 0, the BuyEvent's `base_amount_out`) for 4,200,000,000 (on today's V: 6.9 ppm low, the config's drift). At
//!   the trigger's state, the one the old bot priced, arbx quotes 278,480,720,280 and the old bot 311,092,620,532: 11.71%
//!   high, wallet-synthesis's 11.7%, on the right state (no phantom: its maths). With the right buy quote, the 4.2 SOL
//!   round trip the chain made loses 138.6M, which arbx's on-chain min_profit refuses.
//! - **w5h2-p10#156** (3.04 SOL, DAMM v2 BKH29Cr5 → DLMM HRhgfZpz, expected 37.3M; the DLMM leg quoted 1.26% high) stays
//!   the open item PLAN WP-09 names: the landing's record carries the delivered amounts (NXV2OUT), not the DLMM pair's bins
//!   (historical bin arrays are not retrievable from RPC), so its state cannot be rebuilt. The test pins what the record
//!   does show (the two legs' outputs against the old prediction: the 1.26%) and that nothing in it rebuilds the bins; the
//!   first Stage-0 recording with a ≥ 1% mispricing in accounts.bin becomes its fixture.
use super::*;

/// a transaction of testdata/scenarios/s16/tx (getTransaction, base64): its account keys (static, then the loaded
/// writable and read-only ones) and its JSON
fn tx_record(sig: &str) -> (Vec<Pk>, Value) {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/scenarios/s16/tx").join(format!("{sig}.json"));
    let v: Value = serde_json::from_slice(&std::fs::read(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()))).unwrap();
    let x = crate::chainfetch::txjson::from_rpc(&v).expect("the record reads");
    (x.keys, v)
}

/// the token amount of `key` before (`post` false) or after the transaction, from its token balances
fn token_balance(keys: &[Pk], v: &Value, key: &Pk, post: bool) -> u64 {
    let i = keys.iter().position(|k| k == key).unwrap_or_else(|| panic!("{} not in the transaction", b58(key)));
    let list = &v["meta"][if post { "postTokenBalances" } else { "preTokenBalances" }];
    list.as_array().unwrap().iter().find(|b| b["accountIndex"].as_u64() == Some(i as u64)).unwrap()["uiTokenAmount"]["amount"].as_str().unwrap().parse().unwrap()
}

/// the route program's NXV2OUT records of a transaction's logs: (leg, delivered)
fn delivered(v: &Value) -> Vec<(u8, u64)> {
    let logs: Vec<String> = v["meta"]["logMessages"].as_array().unwrap().iter().map(|l| l.as_str().unwrap().to_string()).collect();
    crate::proglog::delivered_from_logs(&logs)
}

/// the old bot's v1 line (`attempts` or `outcomes`) of a case (testdata/scenarios/s16/legacy.json: verbatim, from
/// testdata/legacy/raw/w5h3-p2 for #664 and the segment's own files for p10#156; `--s16`)
fn legacy_line(case: &str, stream: &str) -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/scenarios/s16/legacy.json");
    let v: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    assert_eq!(v["schema"], "arbx.fixture.s16-legacy/1");
    v["cases"][case][stream]["line"].clone()
}

const LANDED_664: &str = "5a11p2hYgGFPgANygqFZKMLig5dznyFW1vLwkQNZ4AqKTw782aQzh4GjLKh4W4WhuNDXLo7XciKEmZpEZS6LrS2C";
const TRIGGER_664: &str = "4ukKBXf9gczLfJ47XbZn62JbUGj3ntfnD6spxTQEAqMVtZ3A7BdZj6x7Prot8G8LsKzRfe5Pfs1kJXp5298S4uyY";
const LANDED_P10_156: &str = "5Sopwbo2QRgnwEmVPTT5ED8bGdKs9bGn7W11KCvWTBxzxAmsN8XnGGhgGiKZGcWBx6PzdPN5va5fDjFXouR5DgQr";
/// #664's size: the old bot's `size_lamports`, the BuyEvent's `quote_amount_in`
const SIZE_664: u64 = 4_200_000_000;

/// PumpSwap's BuyEvent / SellEvent (the program's `emit!`: an 8-byte discriminator, then u64 fields) of a transaction:
/// the fields named, from the first event of that kind in its logs
fn pump_event(v: &Value, disc: [u8; 8], fields: &[&str]) -> Vec<u64> {
    use base64::Engine as _;
    let all = ["timestamp", "base_amount", "max_or_min_quote", "user_base_token_reserves", "user_quote_token_reserves", "pool_base_token_reserves",
        "pool_quote_token_reserves", "quote_amount", "lp_fee_basis_points", "lp_fee", "protocol_fee_basis_points", "protocol_fee", "quote_amount_with_lp_fee",
        "user_quote_amount"];
    let b = v["meta"]["logMessages"].as_array().unwrap().iter().filter_map(|l| l.as_str()?.strip_prefix("Program data: "))
        .filter_map(|x| base64::engine::general_purpose::STANDARD.decode(x).ok()).find(|b| b.len() > 8 && b[..8] == disc).expect("the event");
    fields.iter().map(|f| { let i = all.iter().position(|a| a == f).unwrap(); u64::from_le_bytes(b[8 + 8 * i..16 + 8 * i].try_into().unwrap()) }).collect()
}

/// the virtual quote reserve V (pool bytes 245..261, i128) a curve output pins, as an inclusive range: out = ⌊n / (Q + V
/// + e)⌋ for a buy (n = B·(eff − 1), e = eff − 1), q = ⌊(Q + V)·b / (B + b)⌋ for a sell
fn v_of_buy(base: u64, quote: u64, eff: u64, out: u64) -> (i128, i128) {
    let n = base as i128 * (eff as i128 - 1);
    (n / (out as i128 + 1) + 1 - (eff as i128 - 1) - quote as i128, n / out as i128 - (eff as i128 - 1) - quote as i128)
}
fn v_of_sell(base: u64, quote: u64, b: u64, q: u64) -> (i128, i128) {
    let (bb, qq) = ((base + b) as i128, q as i128);
    ((qq * bb + b as i128 - 1) / b as i128 - quote as i128, ((qq + 1) * bb - 1) / b as i128 - quote as i128)
}

#[test]
fn s16_w5h3_p2_664_the_cp_leg_is_priced_as_the_chain_executed_it() {
    let (old, old_out) = (legacy_line("w5h3-p2#664", "attempts"), legacy_line("w5h3-p2#664", "outcomes"));
    assert_eq!((old["size_lamports"].as_u64(), old["buy_pool"].as_str(), old["sell_pool"].as_str(), old["expected_profit"].as_i64()),
        (Some(SIZE_664), Some("DreMAMRc83uJtbvWuWrDqDaQUGHDbFGopmbTYbM3tJFW"), Some("AwmaWjsRQ55hYGJfiHcqTwzQX9QLBtGZHPQnjhjDpPkz"), Some(454_489_365)));
    let old_mid = old["predicted_mid"].as_u64().unwrap();
    assert_eq!(old_out["sig"].as_str(), Some(LANDED_664), "the landed copy");
    let mut r = Rig::new("s16-664", Setup { pools: &["s16.pump", "s16.dlmm"], exec: Some(ExecSetup::default()), ..Default::default() });
    r.make_ready(T0);
    let (p, d) = (r.meta("s16.pump"), r.meta("s16.dlmm"));
    assert!(!sol_is_t0(&p) && p.t0 == crate::tx::pk("3Dgwn5E7H5a8k6iGrz3qirkaJqUaJrKHEZ2xPcLRpump"), "the token is PumpSwap's base, SOL its quote");
    // the landing: its pre-token balances are the pool's reserves when it executed (it failed: nothing moved), its logs what
    // each leg delivered; its BuyEvent says the same reserves, the 4.2 SOL in and the tokens out
    let (keys, landed) = tx_record(LANDED_664);
    let (base0, quote0) = (token_balance(&keys, &landed, &p.vault0, false), token_balance(&keys, &landed, &p.vault1, false));
    assert_eq!((base0, quote0), (37_410_941_865_369, 540_192_702_838), "the reserves at our execution");
    assert_eq!((token_balance(&keys, &landed, &p.vault0, true), token_balance(&keys, &landed, &p.vault1, true)), (base0, quote0), "a failed transaction moves nothing");
    let legs = delivered(&landed);
    assert_eq!(legs, vec![(0, 276_985_551_117), (1, 4_061_405_592)], "what the chain's legs delivered");
    assert_eq!(landed["meta"]["err"]["InstructionError"][1]["Custom"].as_u64(), Some(0x4e58_0002), "the route's profit check");
    const BUY: [u8; 8] = [0x67, 0xf4, 0x52, 0x1f, 0x2c, 0xf5, 0x77, 0x77];
    const SELL: [u8; 8] = [0x3e, 0x2f, 0x37, 0x0a, 0xa5, 0x03, 0xdc, 0x2a];
    let be = pump_event(&landed, BUY, &["base_amount", "pool_base_token_reserves", "pool_quote_token_reserves", "quote_amount", "user_quote_amount"]);
    assert_eq!(be[..4], [legs[0].1, base0, quote0, SIZE_664], "the BuyEvent: {be:?}");
    // the trigger: a PumpSwap sell on the same pool a slot before; its post-token balances are the state the old bot priced
    let (tkeys, trig) = tx_record(TRIGGER_664);
    let (base_t, quote_t) = (token_balance(&tkeys, &trig, &p.vault0, true), token_balance(&tkeys, &trig, &p.vault1, true));
    assert_eq!((base_t, quote_t), (37_511_071_736_303, 538_671_603_148));
    // the pool's virtual quote reserve then: both events pin it (the trigger's sell on its own, independent of our buy), and
    // it has moved since (the current pool account: the config the fixture holds)
    let se = pump_event(&trig, SELL, &["base_amount", "pool_base_token_reserves", "pool_quote_token_reserves", "quote_amount"]);
    let (vb, vs) = (v_of_buy(base0, quote0, be[4], legs[0].1), v_of_sell(se[1], se[2], se[0], se[3]));
    let pool_now = r.data(&p.pool);
    let v_now = i128::from_le_bytes(pool_now[245..261].try_into().unwrap());
    eprintln!("S16 #664: V from our BuyEvent {vb:?}, from the trigger's SellEvent {vs:?}, the pool's now {v_now}");
    let v_then = vb.0.max(vs.0);
    assert!(v_then <= vb.1.min(vs.1), "the two events agree on V: {vb:?} {vs:?}");
    assert!(v_now > vs.1 + 1_000_000, "V moved since #664 ({v_now} now)");
    // the run: the pool rebuilt at our execution (the landing's reserves; the pool account as it is now but for V, the one
    // field the events pin), received on the state stream as one transaction's writes; its pool evaluated
    let s2 = r.s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    let mut pool_then = pool_now.clone();
    pool_then[245..261].copy_from_slice(&v_then.to_le_bytes());
    let sig = r.sig("S16-664-state");
    let t = T0 + 10 * MS;
    r.write(p.pool, pool_then.clone(), s2, Some(sig), t);
    r.write(p.vault0, with_amount(&r.data(&p.vault0), base0), s2, Some(sig), t + 100 * US);
    r.write(p.vault1, with_amount(&r.data(&p.vault1), quote0), s2, Some(sig), t + 200 * US);
    r.timers(t + 4 * MS);
    let ev = r.evaluations();
    assert_eq!(ev.len(), 1, "the pool evaluated: {ev:?}");
    // arbx's quote of #664's buy at 4.2 SOL on that state: the chain's, to the unit
    let q = r.e.quote_route(&p.pool, &d.pool, &p.t0, SIZE_664).expect("the route quotes");
    eprintln!("S16 #664: arbx at our execution: {} tokens for {} (chain: {} for {SIZE_664}); the old bot: {old_mid} ({:+.2}%)", q.mid, q.spent, legs[0].1,
        (old_mid as f64 / q.mid as f64 - 1.0) * 100.0);
    assert_eq!((q.mid, q.spent), (legs[0].1, SIZE_664), "arbx prices the CP leg as the chain executed it");
    assert!(old_mid as f64 > 1.12 * q.mid as f64, "the old bot's leg was >12% high: {old_mid} vs {}", q.mid);
    // the same reserves on today's V: 7 ppm off, the drift of the pool's config, not the maths
    let sig_n = r.sig("S16-664-v-now");
    r.write(p.pool, pool_now.clone(), s2, Some(sig_n), t + 6 * MS);
    r.timers(t + 10 * MS);
    let qn = r.e.quote_route(&p.pool, &d.pool, &p.t0, SIZE_664).expect("the route quotes");
    let ppm = (legs[0].1 as f64 - qn.mid as f64) / legs[0].1 as f64 * 1e6;
    eprintln!("S16 #664: with today's V: {} tokens ({ppm:.1} ppm below the chain)", qn.mid);
    assert!(qn.mid < legs[0].1 && ppm < 10.0, "{ppm}");
    // at the trigger's state (what the old bot priced, V then) arbx's buy quote is still far below the old one: the old
    // quote was not its state's either (no phantom: its maths)
    let sig_t = r.sig("S16-664-trigger-state");
    r.write(p.pool, pool_then, s2, Some(sig_t), t + 12 * MS);
    r.write(p.vault0, with_amount(&r.data(&p.vault0), base_t), s2, Some(sig_t), t + 12 * MS + 100 * US);
    r.write(p.vault1, with_amount(&r.data(&p.vault1), quote_t), s2, Some(sig_t), t + 12 * MS + 200 * US);
    r.timers(t + 16 * MS);
    let qt = r.e.quote_route(&p.pool, &d.pool, &p.t0, SIZE_664).expect("the route quotes");
    eprintln!("S16 #664: arbx at the trigger's state: {} tokens (the old bot: {old_mid}, {:+.2}%)", qt.mid, (old_mid as f64 / qt.mid as f64 - 1.0) * 100.0);
    assert!(qt.mid > q.mid && (old_mid as f64) > 1.10 * qt.mid as f64, "{} vs {old_mid}", qt.mid);
    // with the right buy quote, the 4.2 SOL round trip the chain made (the sell of exactly those tokens returned
    // 4,061,405,592) loses 138.6M: the on-chain min_profit (tip + fee + margin, all positive) refuses what the old bot sent
    assert_eq!(legs[1].1 as i64 - SIZE_664 as i64, -138_594_408);
    let done = r.finish_and_replay();
    done.check_expected();
}

/// w5h2-p10#156: the open item (PLAN WP-09 S16). Its landing's record shows each leg's output and nothing of the DLMM
/// pair's bins: the case's 1.26% is pinned from the record and the old prediction, its state cannot be rebuilt
#[test]
fn s16_w5h2_p10_156_stays_open_its_dlmm_state_is_not_on_chain() {
    let (keys, landed) = tx_record(LANDED_P10_156);
    assert_eq!((landed["slot"].as_u64(), landed["meta"]["err"]["InstructionError"][1]["Custom"].as_u64()), (Some(453_089_316), Some(0x4e58_0002)));
    let legs = delivered(&landed);
    assert_eq!(legs, vec![(0, 186_118_876_247), (1, 2_993_742_708)], "DAMM v2 then DLMM");
    // the old bot's prediction (its attempt line): 3,037,926,873 in, 188,780,020,269 tokens, 3,075,214,183 back; its
    // outcome line's `delivered` is the record's
    let (old, old_out) = (legacy_line("w5h2-p10#156", "attempts"), legacy_line("w5h2-p10#156", "outcomes"));
    assert_eq!((old["size_lamports"].as_u64(), old["buy_venue"].as_str(), old["sell_venue"].as_str(), old["expected_profit"].as_i64(), old_out["sig"].as_str()),
        (Some(3_037_926_873), Some("DammV2"), Some("Dlmm"), Some(37_287_310), Some(LANDED_P10_156)));
    assert_eq!(old_out["delivered"], json!([legs[0].1, legs[1].1]), "the old bot's outcome line read the same delivered amounts");
    let (pred_mid, pred_back) = (old["predicted_mid"].as_u64().unwrap(), old["predicted_back"].as_u64().unwrap());
    // the DLMM leg at the tokens it really got, against the old price per token
    let dlmm_high = pred_back as f64 * legs[0].1 as f64 / pred_mid as f64 / legs[1].1 as f64 - 1.0;
    eprintln!("S16 p10#156: DAMM v2 leg {:+.2}% high, DLMM leg {:+.2}% high", (pred_mid as f64 / legs[0].1 as f64 - 1.0) * 100.0, dlmm_high * 100.0);
    assert!((dlmm_high - 0.0126).abs() < 0.0005, "the DLMM leg was quoted 1.26% high: {dlmm_high}");
    // nothing in the record rebuilds the pair's bins: the only events in its logs are the route program's markers (the
    // DLMM program emitted none), and the pair's reserves (its token balances) do not say how they sit in its bins
    let logs: Vec<String> = landed["meta"]["logMessages"].as_array().unwrap().iter().map(|l| l.as_str().unwrap().to_string()).collect();
    let data_lines = logs.iter().filter(|l| l.starts_with("Program data: ")).count();
    assert_eq!(data_lines, crate::proglog::events(&logs).len(), "every event is a route program marker: {logs:?}");
    assert!(keys.contains(&crate::tx::pk("HRhgfZpzapYZNY9QwBN2CS4j3ftxgAySYWjFaUa1g7KH")), "the DLMM pair");
}
