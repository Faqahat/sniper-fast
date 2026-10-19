#!/usr/bin/env python3
# RACE-GATE patch part 3 (2026-10-18): better outside-buy SOL estimate in the race window. mint_touch returns the token
# amount too; cap-family buys are priced on the post-dev curve (capped by max_sol_cost) instead of using the raw cap.
import sys
sp, ep = sys.argv[1], sys.argv[2]
s = open(sp).read()
e = open(ep).read()
def rep(txt, old, new):
    assert txt.count(old) == 1, old[:80]
    return txt.replace(old, new)
s = rep(s, """pub enum MintTouch { Buy(u64), Sell, Other }""", """pub enum MintTouch { Buy(u64), BuyCap { tokens: u64, max_sol: u64 }, Sell, Other }""")
s = rep(s, """        if DEV_BUY_SOL_AT_16.contains(&d) {
            let cap = read(ix, 16).unwrap_or(0);
            return Some(MintTouch::Buy(if cap > 1_000_000_000_000_000 { 0 } else { cap }));
        }""", """        if DEV_BUY_SOL_AT_16.contains(&d) {
            return Some(MintTouch::BuyCap { tokens: read(ix, 8).unwrap_or(0), max_sol: read(ix, 16).unwrap_or(0) });
        }""")
s = rep(s, """/// How a non-create pump tx touches a watched mint (race window): a top-level pump BUY (with its SOL hint: the spendable
/// amount for sized buys, the max_sol_cost for capped cap-family buys, 0 when unknown/unlimited), a SELL, or OTHER (the""",
"""/// How a non-create pump tx touches a watched mint (race window): a top-level pump BUY (sized: the spendable SOL; cap-family:
/// token amount + max_sol_cost, priced by the caller on the curve), a SELL, or OTHER (the""")
s = s.replace("""/// Fresh bonding-curve virtual reserves (lamports / raw token units, 6 decimals).""", """/// SOL (lamports) to buy `tokens` on a curve whose virtual SOL reserve is `vq` (constant product with the fresh k).
pub fn curve_cost(vq: u64, tokens: u64) -> u64 {
    let k = CURVE_VQ0 as u128 * CURVE_VT0 as u128;
    let vq = (vq as u128).max(1);
    let vt = k / vq;
    let t = tokens as u128;
    if t == 0 || t >= vt { return 0; }
    let nvq = k.div_ceil(vt - t);
    nvq.saturating_sub(vq).min(u64::MAX as u128) as u64
}

/// Fresh bonding-curve virtual reserves (lamports / raw token units, 6 decimals).""", 1)
e = rep(e, """            let (sol, buy) = match touch { snipe::MintTouch::Buy(s) => (s, true), _ => (0, false) };""",
"""            // cap-family buys: price the token amount on the curve after the dev buy + the outside SOL seen so far
            let seen: u64 = p.out.iter().map(|o| o.2).sum();
            let (sol, buy) = match touch {
                snipe::MintTouch::Buy(s) => (s, true),
                snipe::MintTouch::BuyCap { tokens, max_sol } => {
                    let est = snipe::curve_cost(snipe::CURVE_VQ0 + p.launch.dev_buy_lamports + seen, tokens);
                    (if max_sol > 0 && max_sol < est { max_sol } else { est }, true)
                }
                _ => (0, false),
            };""")
e = rep(e, """                if matches!(touch, snipe::MintTouch::Buy(_)) { p.bundle_n += 1; }""",
"""                if matches!(touch, snipe::MintTouch::Buy(_) | snipe::MintTouch::BuyCap { .. }) { p.bundle_n += 1; }""")
open(sp, "w").write(s)
open(ep, "w").write(e)
print("patch3 OK")
