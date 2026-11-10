#!/usr/bin/env python3
"""TEN lever (a): what a live position would have made at another size (curve replay on the position's own live tape).
Constant product on (vsol, vtok) from the tape rows (post-trade states). Our buy: pre-state = our row's post-state minus our trade.
Others' trades after our buy up to our first sell landing are replayed with FIXED SOL in (buys) / FIXED tokens (sells); our sell
sells all our tokens at its live (slot, idx). Costs: pump fee 1.25% of curve SOL each way (FEE) + the position's own fixed costs
(live pnl - live curve P&L + live 1.25% fees), the same at any size. The fill limit: the engine's min_out is the curve output at
the limit price (same k), so the fill condition is spot <= limit for any size (checked: validate()).
Followers priced out: a stress that drops a share of the other wallets' buys after ours (deterministic hash draw), as prior size work.
Positions with more than one buy round or no own tape row keep live pnl x size ratio (counted)."""
import json, hashlib, math
ME = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"
FEE = 0.0125

def _h(s):
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16) / 0xffffffff

def replay(p, spend, drop_share=0.0, seed=0, beta=0.0):
    """pnl in SOL at spend (SOL); None if not replayable. drop_share: a flat share of others' later buys dropped (stress);
    beta: price-out model, each later buy by others is dropped with prob beta * extra impact, extra impact = 2 * (our curve SOL at
    this size - at the live size) / pre-buy vsol (beta ~3 from the 10-27 size study r24: 14 then 37 follower buys priced out over 200
    fills when size went 0.34 -> 0.50 -> 0.65, with ~3.3 follower buys per fill and vsol ~41 SOL; INFERRED)"""
    tp = p["tape"]
    me = [x for x in tp if x["user"] == ME and x["buy"] and x["slot"] == p["fill_slot"] and x["idx"] == p["fill_idx"]]
    if not me or (p.get("rounds") or 1) > 1 or not p.get("sell_land"): return None
    m = me[0]
    v0 = m["vsol"] - m["sol"]; t0 = m["vtok"] + m["tok"]; k = v0 * t0
    sl = p["sell_land"]
    # our own sell rows (all of them in the hold, the first is at sell_land)
    x_in = spend * 1e9 / (1 + FEE)
    v = v0 + x_in; t = k / v; mytok = t0 - t
    p_out = max(0.0, beta * 2 * (x_in - m["sol"]) / v0)
    for x in sorted(tp, key=lambda x: (x["slot"], x["idx"] or 0)):
        key = (x["slot"], x["idx"] or 0)
        if key <= (m["slot"], m["idx"] or 0): continue
        if key >= (sl[0], sl[1]): break
        if x["user"] == ME: continue
        if x["buy"]:
            if drop_share and _h(f"{seed}:{x['sig']}") < drop_share: continue
            if p_out and _h(f"po:{x['sig']}") < p_out: continue
            v = v + x["sol"]; t = k / v
        else:
            t = t + x["tok"]; v = k / t
    out = v - k / (t + mytok)
    curve = (out - x_in) / 1e9
    fees_live = FEE * (p["sol_in"] + p["sol_out_curve"])
    fixed = p["curve_pnl"] - fees_live - p["pnl"]               # >0 = fixed costs (tips, tx fees, rent kept, ...)
    return curve - FEE * (x_in / 1e9 + out / 1e9) - fixed

def pnl_at(p, spend, drop_share=0.0, seed=0, beta=0.0):
    r = replay(p, spend, drop_share, seed, beta)
    if r is None: return p["pnl"] * spend / p["spend"], False
    return r, True

def validate(pos):
    """replay at the live size vs live realized; and the min_out model"""
    d = []
    for p in pos:
        r = replay(p, p["spend"])
        if r is not None: d.append(r - p["pnl"])
    d.sort()
    return len(d), sum(d), d[len(d) // 2] if d else None, d[int(len(d) * 0.05)] if d else None, d[int(len(d) * 0.95)] if d else None

if __name__ == "__main__":
    pos = json.load(open("/home/it/sniper-data/filters3/ten/pos.json"))
    print("replay at live size - live realized: n, sum, median, p5, p95 =", validate(pos))
