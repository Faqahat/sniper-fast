#!/usr/bin/env python3
"""Q1/Q4 our side (MEASURED from run records + tape). Our live pre-send fills in FRA r27/r28 (+AMS r28): dump -> our fill on the same
chain clock and the same 't7' definition as his buys (previous outside trade = sell >= 0.5 SOL within 2 slots), by leader client.
Our per-fill costs: buy fee+tip, failed tries (presend_attempt_land non-ok fees), sell fee+tip, ATA close.
Out: sniper-data/e2x1_dissect/exec/x2.txt, x2.pkl"""
import sys, json, collections, pickle
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/exec")
import numpy as np, xlib as X
RUNS = {"FRA27": "/home/moiz/sniper-data/runs/fra/runs/dip_r27.jsonl", "FRA28": "/home/moiz/sniper-data/runs/fra/runs/dip_r28.jsonl",
        "AMS28": "/home/moiz/sniper-data/presend_filter/live28/dip_ams_r28.jsonl"}
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
fills = []; cost = collections.defaultdict(lambda: collections.Counter())
for run, f in RUNS.items():
    tmin = tmax = None; byp = {}
    for l in open(f, errors="ignore"):
        try: d = json.loads(l)
        except Exception: continue
        ev = d.get("ev"); t = d.get("t")
        if t: tmin = t if tmin is None else min(tmin, t); tmax = t if tmax is None else max(tmax, t)
        if ev == "presend_live_fill":
            fills.append(dict(run=run, mint=d["mint"], s=d["slot"], i=d["idx"], client=d.get("client"), path=d.get("path"), sig=d["sig"], t=d["t"], fee=d.get("fee"), tip=d.get("tip")))
        elif ev == "presend_attempt_land":
            c = cost[run]; c["tries_landed"] += 1
            if d.get("res") not in ("ok", "fill", None) and d.get("err"): c["tries_failed"] += 1; c["fail_fee"] += d.get("fee") or 0
            else: c["tries_ok"] += 1
        elif ev == "presend_live_close":
            c = cost[run]; c["closes"] += 1
            for b in d.get("buys", []): c["buy_fee"] += b.get("fee") or 0; c["buy_tip"] += b.get("tip") or 0
            for s in d.get("sell_sigs", []): c["sell_tip"] += s[2] if len(s) > 2 else 0
        elif ev == "presend_live_sell_land":
            cost[run]["sell_fee"] += d.get("fee") or 0; cost[run]["sells"] += 1
        elif ev == "presend_live_ata_close":
            cost[run]["ata_fee"] += d.get("fee") or 0
        elif ev == "presend_live_realized":
            cost[run]["pnl"] += d.get("pnl") or 0; cost[run]["realized"] += 1
        elif ev == "presend_live_stop":
            cost[run]["stop_fees"] = d.get("fees") or 0
    cost[run]["t0"] = tmin; cost[run]["t1"] = tmax
# tape: recon tape for his mints, haqqml/fresh tape for the rest
RT = X.tape()["trades"]
FT = np.load("/home/moiz/sniper-data/haqqml/fresh/tape/trades.npy", mmap_mode="r")
mids = {m: k for k, m in enumerate(json.load(open("/home/moiz/sniper-data/haqqml/fresh/tape/mints.json")))}
users = json.load(open("/home/moiz/sniper-data/haqqml/fresh/tape/users.json")); ourid = {k for k, u in enumerate(users) if u in OURS}
need = np.array([mids[f["mint"]] for f in fills if f["mint"] not in RT and f["mint"] in mids], np.uint32)
fm = np.asarray(FT["mint"]); sel = np.nonzero(np.isin(fm, need))[0]
sub = np.asarray(FT[sel]); bym = collections.defaultdict(list)
for r in sub: bym[int(r["mint"])].append((int(r["slot"]), int(r["idx"]), int(r["j"]), users[int(r["user"])], bool(r["buy"]), int(r["sol"])))
for v in bym.values(): v.sort()
rows = []
for f in fills:
    if f["mint"] in RT: tr = [(t[0], t[1], t[2], t[4], t[6], t[7]) for t in RT[f["mint"]] if t[16]]; src = "his"
    elif f["mint"] in mids: tr = bym.get(mids[f["mint"]], []); src = "fresh"
    else: continue
    prev = None
    for t in tr:
        if (t[0], t[1]) >= (f["s"], f["i"]): break
        if t[3] not in OURS: prev = t
    if prev is None: continue
    ld, cl = X.leader(f["s"])
    rows.append(dict(f, src=src, ps=prev[0], pi=prev[1], pbuy=prev[4], psol=prev[5] / 1e9, pgap=f["s"] - prev[0], pms=X.cc(f["s"], f["i"]) - X.cc(prev[0], prev[1]), lclient=cl,
                     day="D1" if X.D1[0] <= f["t"] / 1e9 < X.D1[1] else "other"))
pickle.dump(dict(rows=rows, cost={k: dict(v) for k, v in cost.items()}), open(f"{X.X}/x2.pkl", "wb"))
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
for run, c in cost.items():
    P(run, X.pkt(c["t0"] / 1e9), "->", X.pkt(c["t1"] / 1e9), {k: v for k, v in c.items() if k not in ("t0", "t1")})
P(f"fills {len(fills)}; with a previous outside trade on tape {len(rows)} (on his mints {sum(r['src']=='his' for r in rows)})")
D = [r for r in rows if not r["pbuy"] and r["psol"] >= 0.5 and r["pgap"] <= 2]
def S(v, lab):
    if len(v) < 8: return
    P(f"  {lab:30} n={len(v):4} ms p25/50/75 {X.pct([r['pms'] for r in v],25):4.0f}/{X.med([r['pms'] for r in v]):4.0f}/{X.pct([r['pms'] for r in v],75):4.0f}  same-slot {100*np.mean([r['pgap']==0 for r in v]):3.0f}%")
P("OUR pre-send fills, dump (prev outside sell>=0.5 within 2 slots) -> fill, chain clock")
S(D, "ALL")
for k in ("run", "lclient", "path", "src"):
    for v in sorted(set(r[k] for r in D)): S([r for r in D if r[k] == v], f"{k}={v}")
S([r for r in rows if r["pgap"] <= 2], "any prev outside trade <=2 slots")
open(f"{X.X}/x2.txt", "w").write("\n".join(out) + "\n")
