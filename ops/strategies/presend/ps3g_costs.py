#!/usr/bin/env python3
# Step 1g: pre-placer economics inside the evaluation windows (C.WIN): fills, P&L on the curve (tape), failed-attempt fees and
# fill tips/fees (raw rows, failed txs included), net per 24 h. MEASURED (fees and tips are what the chain charged).
import json, gzip, glob, collections
import numpy as np
import ps_common as C
F = [json.loads(l) for l in open(f"{C.OUT}/ps3b_fills.jsonl")]
W = json.load(open(f"{C.OUT}/pp_wallets.json"))
H = {d: (C.pk(C.WIN[d][1]) - C.pk(C.WIN[d][0])) / 3600 for d in C.WIN}
win = lambda day, t: C.pk(C.WIN[day][0]) <= t < C.pk(C.WIN[day][1])
st = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0, 0, 0.0, 0.0, 0]))   # w -> day -> [failed, failed fee, ok buys, buy fee+tips, sell fee+tips, ok sells]
for day in C.WIN:
    for f in sorted(glob.glob(f"{C.OUT}/raw/{day}_*.jsonl.gz") + glob.glob(f"{C.OUT}/raw2/{day}_*.jsonl.gz")):
        for l in gzip.open(f, "rt"):
            r = json.loads(l)
            if r["w"] not in W or not r.get("bt") or not win(day, r["bt"]): continue
            ix = " ".join(r["ixn"]); side = "B" if "Buy" in ix else ("S" if "Sell" in ix else "O")
            if r["tr"]: side = "B" if r["tr"][0][3] else "S"
            s = st[r["w"]][day]
            if r["err"] is not None and side in ("B", "O"): s[0] += 1; s[1] += (r["fee"] or 0) / 1e9
            elif r["err"] is None and side == "B": s[2] += 1; s[3] += ((r["fee"] or 0) + r["tips"]) / 1e9
            elif r["err"] is None and side == "S": s[5] += 1; s[4] += ((r["fee"] or 0) + r["tips"]) / 1e9
pn = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0]))
for r in F:
    if win(r["day"], r["t"]): x = pn[r["w"]][r["day"]]; x[0] += 1; x[1] += r["tok_pnl"]
out = {}
print("inside the eval windows (R1 14.9 h, R2 21.6 h, R3 21.0 h, R4 3.3 h); SOL per 24 h; curve P&L from the tapes, fees/tips from the chain")
print(f"{'wallet':10s} {'day':3s} {'fills':>5s} {'curve':>7s} {'failed':>7s} {'fail fee':>8s} {'buy fee+tip':>11s} {'sell fee+tip':>12s} {'net':>7s} {'net/24h':>7s} {'att/fill':>8s} {'cost/fill':>9s}")
for w in W:
    for day in ("R2", "R3", "R4", "R1"):
        s = st[w][day]; p = pn[w][day]
        if p[0] == 0 and s[2] == 0: continue
        net = p[1] - s[1] - s[3] - s[4]
        out[f"{w}|{day}"] = dict(fills=p[0], curve=p[1], failed=s[0], fail_fee=s[1], buy_cost=s[3], sell_cost=s[4], net=net, net24=net / H[day] * 24,
                                 att_per_fill=s[0] / max(p[0], 1), cost_per_fill=(s[1] + s[3] + s[4]) / max(p[0], 1))
        o = out[f"{w}|{day}"]
        print(f"{w[:9]:10s} {day:3s} {p[0]:5d} {p[1]:+7.2f} {s[0]:7d} {s[1]:8.3f} {s[3]:11.3f} {s[4]:12.3f} {net:+7.2f} {o['net24']:+7.2f} {o['att_per_fill']:8.0f} {o['cost_per_fill']:9.4f}")
json.dump(out, open(f"{C.OUT}/ps3g_costs.json", "w"), indent=1)
