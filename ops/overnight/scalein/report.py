#!/usr/bin/env python3
# scale-in replay report: per entry set, best (adds / exit) setting chosen on TRAIN at 60 ms, judged on TEST and LIVE; vs the quick
# single-buy exit and vs the same exit without adds (N = 0).
import json, time, calendar, collections, statistics
R = json.load(open("/home/moiz/sniper/ops/overnight/scalein/scalein.json"))
S1 = calendar.timegm(time.strptime("2026-10-23 06:00", "%Y-%m-%d %H:%M")) - 18000
def part(r): return "LIVE" if r["run"] == "R3" else ("TRAIN" if r["t"] < S1 else "TEST")
for r in R: r["part"] = part(r)
span = {}
for pt in ("TRAIN", "TEST", "LIVE"):
    ts = [r["t"] for r in R if r["part"] == pt]; span[pt] = (max(ts) - min(ts)) / 3600 if ts else 1
def stats(v):
    v = [x for x in v if x is not None]
    if not v: return "no trades"
    s = sorted(v, reverse=True); k = max(1, len(v) // 20); w = [x for x in v if x > 0]; l = [x for x in v if x <= 0]
    pf = sum(w) / -sum(l) if sum(l) < 0 else 99
    return f"n {len(v):5d} total {sum(v):+8.2f} avg {sum(v) / len(v):+.4f} win {len(w) / len(v):4.0%} PF {pf:4.2f} top5% {sum(s[:k]):+7.2f}"
keys = sorted({k for r in R for k in r["res"]})
for st in ("HAQQ", "MOM"):
    V = [r for r in R if r["set"] == st]
    print(f"\n######## entries {st}: TRAIN {sum(1 for r in V if r['part'] == 'TRAIN')} / TEST {sum(1 for r in V if r['part'] == 'TEST')} / LIVE {sum(1 for r in V if r['part'] == 'LIVE')} "
          f"(hours {span['TRAIN']:.0f} / {span['TEST']:.0f} / {span['LIVE']:.0f})")
    tr = [r for r in V if r["part"] == "TRAIN"]
    best = sorted([k for k in keys if k.startswith("60|") and k != "60|quick"], key=lambda k: -sum(r["res"][k] or 0 for r in tr))
    def name(k):
        lat, *g = k.split("|")
        if g == ["quick"]: return f"single buy, sell at 6 slots @{lat}"
        N, A, G, SL, T = g
        return f"adds {N} (each +0.3 when {A} SOL bought) | exit: stall {int(G) / 1000:g}s, SL {'-' + str(int(float(SL) * 100)) + '%' if float(SL) < 5 else 'none'}, cap {T}s @{lat}"
    show = [best[0], best[1], best[2]]
    noadd = [k for k in best if k.split("|")[1] == "0"][:1]
    for k in show + noadd + ["60|quick"]:
        print(f"  {name(k)}")
        for pt in ("TRAIN", "TEST", "LIVE"):
            v = [r["res"][k] for r in V if r["part"] == pt]
            print(f"      {pt:5s} {stats(v)} | {sum(x for x in v if x is not None) / span[pt]:+.2f} SOL/h")
    k = best[0]; g = k.split("|", 1)[1]
    print("  best TRAIN setting at other speeds (TEST / LIVE totals): " + " | ".join(f"@{lat}: {sum((r['res'].get(f'{lat}|{g}') or 0) for r in V if r['part'] == 'TEST'):+.2f} / {sum((r['res'].get(f'{lat}|{g}') or 0) for r in V if r['part'] == 'LIVE'):+.2f}" for lat in (35, 60, 75)))
