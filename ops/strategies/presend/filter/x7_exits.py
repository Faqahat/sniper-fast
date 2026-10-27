#!/usr/bin/env python3
"""EXPLORATION (DEV ONLY, exact replay of AMS r24+r25, replay065): pre-send exit variants on the real chain sequence.
TP / SL thresholds and the time exit (entry slot + T). Same mechanics as positions.replay (follower limits, sell delays MEASURED);
only the exit parameters change. Rows exist up to max(live sell slot, fill + 4) + 1, so T <= 3 is fully covered.
Prints the per-run P&L (engine basis, + rent back is unchanged) at 0.34 (live size) and 0.50."""
import sys, json, pickle, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import numpy as np
import core, positions as PO, pmath as PM

SMS = core.SMS


def replay_x(D, p, size, delays, tp, sl, T):
    ob = p.ours_buy; fb, cb = ob["fbps"], ob["cbps"]; pre = p.pre
    n = PM.net_of_budget(size, fb, cb)
    q = pre["vtok"] * (n - 1) // (pre["vsol"] + n - 1)
    a = p.att
    mo = core.limit_min_out(a["vsol"], a["vtok"], size, p.fr_sign, 0.12)
    if mo is None or q < mo: return None
    W = core.walk(D, p.mint, pre, p.rows, size, fb, cb, (10 ** 15, 0, 0), buy_slot=p.buy_pos[0])
    st = {k: (v, t, ap) for k, v, t, ap in W["states"]}
    land = p.land_slot; last_chk = land + T - 1
    same_time = (T == 2)
    dec = None
    for k, row in enumerate(p.rows):
        if k not in st: continue
        if same_time:
            if not PO.checked(p, row, last_chk): continue
        elif row["s"] > last_chk: continue
        v, t, ap = st[k]
        if not ap: continue
        tfb, tcb = (row["tr"]["fbps"], row["tr"]["cbps"]) if row["kind"] == "trade" else (95, 30)
        val = PO.value_ps(v, t, q, tfb, tcb, size)
        if tp and val >= 1.0 + tp: dec = ("take-profit", k); break
        if sl and val <= 1.0 - sl: dec = ("stop-loss", k); break
    why = dec[0] if dec else "time-limit"
    live_row = getattr(p, "live_dec_row", None)
    if same_time and why == p.exit_why and (why == "time-limit" or (dec and dec[1] == live_row)):
        sp = p.sell_pos
    elif dec:
        rw = p.rows[dec[1]]; sp = D.ck.inv(D.ck.cc(rw["s"], rw["i"]) + delays["ps:tpsl"])
    else:
        sp = D.ck.inv((land + T) * SMS + delays["ps:time"])
    v, t = W["v_after"], W["t_after"]
    for k, row in enumerate(p.rows):
        if (row["s"], row["i"]) >= (sp[0], sp[1]): break
        if k in st: v, t = st[k][0], st[k][1]
    gross = PM.sell_sol(v, t, q)
    sfb, scb = (p.sell_tr["fbps"], p.sell_tr["cbps"]) if p.sell_tr else (fb, cb)
    return gross - PM.fees(gross, sfb, scb) - size - p.costs, why


def main():
    D = core.Data()
    PS, RG, RF = pickle.load(open(f"{core.BASE}/pos_cal.pkl", "rb"))
    delays = json.load(open(f"{core.BASE}/delays.json"))["median"]
    n = 0
    base = {}
    for size_name, size_fn in (("live", lambda p: p.spend), ("0.50", lambda p: 500_000_000)):
        print(f"== size {size_name}")
        for T in (2, 1, 3):
            for tp in (0.10, 0.06, 0.08, 0.12, 0.15, None):
                for sl in (0.20,):
                    n += 1
                    res = collections.defaultdict(float); wins = collections.Counter()
                    for p in PS:
                        r = replay_x(D, p, size_fn(p), delays, tp, sl, T)
                        if r is None: continue
                        res[p.run] += r[0] / 1e9; wins[p.run] += r[0] > 0
                    key = (size_name, T, tp, sl)
                    if (T, tp, sl) == (2, 0.10, 0.20): base[size_name] = dict(res)
                    b = base.get(size_name)
                    print(f"   T={T} tp={tp} sl={sl}: r24 {res['r24']:+.3f} r25 {res['r25']:+.3f} sum {res['r24'] + res['r25']:+.3f}" + (f"  (vs live config {res['r24'] + res['r25'] - b['r24'] - b['r25']:+.3f})" if b else ""), flush=True)
    print("configs", n)


if __name__ == "__main__":
    main()
