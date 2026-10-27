#!/usr/bin/env python3
"""SIZE study: per-fill pre-send result by PKT hour of day and size, every live pre-send run with records (MEASURED).
Per fill: realized (engine) + rent back of the token account (presend_live_ata_close delta), as % of the run's size. Failed-try
fees are not in this table (they do not depend on size). Bootstrap 5-95 % over fills. Writes .../presend_size/hours.json"""
import json, collections, time
import numpy as np

AMS = "/home/moiz/sniper-data/presend_size/live"
FRA = "/home/moiz/sniper-data/presend_filter/live"
RUNS = [("AMS r24", f"{AMS}/dip_ams_r24.jsonl"), ("AMS r25", f"{AMS}/dip_ams_r25.jsonl"), ("AMS r26", f"{AMS}/dip_ams_r26.jsonl"),
        ("AMS r27", f"{AMS}/dip_ams_r27.jsonl"), ("AMS r28", f"{AMS}/dip_ams_r28.jsonl"),
        ("FRA r23", f"{FRA}/fra_dip_r23.jsonl"), ("FRA r24", f"{FRA}/fra_dip_r24.jsonl")]


def load(fn):
    seg = 0; spend = {}; W = {}; ac = collections.defaultdict(list)
    for line in open(fn):
        if '"presend_live' not in line and '"run_start"' not in line: continue
        r = json.loads(line); ev = r.get("ev")
        if ev == "run_start":
            seg += 1; spend[seg] = (r.get("presend_live") or {}).get("spend"); continue
        if ev == "presend_live_fill":
            W.setdefault((seg, r["w"]), dict(seg=seg, mint=r["mint"], t=r["t"], slot=r["slot"], spend=spend[seg]))
        elif ev == "presend_live_realized":
            if (seg, r["w"]) in W: W[(seg, r["w"])]["pnl"] = r["pnl"]
        elif ev == "presend_live_ata_close":
            ac[(seg, r["mint"])].append(r)
    out = []
    for k, w in W.items():
        if "pnl" not in w: continue
        a = next((x for x in ac[(w["seg"], w["mint"])] if x.get("slot", 0) >= w["slot"]), None)
        rb = (a or {}).get("delta") or 0
        out.append(dict(t=w["t"], spend=w["spend"], net=w["pnl"] + rb, rb=rb))
    return out


def boot(x, n=2000, seed=7):
    x = np.asarray(x, float)
    if len(x) == 0: return (None, None)
    rng = np.random.default_rng(seed)
    m = x[rng.integers(0, len(x), (n, len(x)))].mean(1)
    return float(np.percentile(m, 5)), float(np.percentile(m, 95))


if __name__ == "__main__":
    rows = []
    for name, fn in RUNS:
        F = load(fn)
        for f in F:
            h = int(time.strftime("%H", time.gmtime(f["t"] / 1e9 + 18000)))
            rows.append(dict(run=name, size=f["spend"] / 1e9, hour=h, pct=f["net"] / f["spend"] * 100, net=f["net"] / 1e9, rb=f["rb"]))
        X = [r for r in rows if r["run"] == name]
        hs = sorted({r["hour"] for r in X})
        print(f"{name} size {X[0]['size']:.2f} fills {len(X)} per fill {np.mean([r['pct'] for r in X]):+.2f}% of size  hours {hs[0]:02d}-{hs[-1]:02d}  rentback/fill {np.mean([r['rb'] for r in X]) / 1e9:.5f}")
    # hour x size table
    cells = collections.defaultdict(list)
    for r in rows: cells[(r["hour"], "0.50" if r["size"] >= 0.45 else "0.40" if r["size"] >= 0.38 else "0.34-0.35")].append(r["pct"])
    tab = []
    for (h, s), v in sorted(cells.items()):
        lo, hi = boot(v)
        tab.append(dict(hour=h, size=s, n=len(v), pct=float(np.mean(v)), lo=lo, hi=hi,
                        runs=sorted({r["run"] for r in rows if r["hour"] == h and ("0.50" if r["size"] >= 0.45 else "0.40" if r["size"] >= 0.38 else "0.34-0.35") == s})))
    for c in tab: print(f"  {c['hour']:02d}h {c['size']:>9} n={c['n']:3d} {c['pct']:+6.2f}% [{c['lo']:+.2f}, {c['hi']:+.2f}] {','.join(c['runs'])}")
    json.dump(dict(rows=rows, table=tab), open("/home/moiz/sniper-data/presend_size/hours.json", "w"))
