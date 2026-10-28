#!/usr/bin/env python3
"""recon step 12 (read-only): overlap of E2x1's tokens with ours (live pre-send fills + arms: FRA r27/r28, AMS r25-r27) and with haqqiUUX
(haqq trades on E2x1's mints from the tape). Out: r12.txt"""
import json, pickle, collections, time
import numpy as np
OUT = "/home/moiz/sniper-data/e2x1_dissect/recon"
HQ = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
L = [l for l in pickle.load(open(f"{OUT}/lots.pkl", "rb")) if l["day"] in ("D0", "D1")]
Z = pickle.load(open(f"{OUT}/tape.pkl", "rb"))
bym = collections.defaultdict(list)
for l in L: bym[l["mint"]].append(l)
pk = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(t + 18000))
Lines = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); Lines.append(s)
runs = [("FRA r27", "/home/moiz/sniper-data/runs/fra/runs/dip_r27.jsonl"), ("FRA r28", "/home/moiz/sniper-data/runs/fra/runs/dip_r28.jsonl"),
        ("AMS r25", "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r25.jsonl"), ("AMS r26", "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r26.jsonl"),
        ("AMS r27", "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r27.jsonl")]
P("## Overlap with our live runs (MEASURED; our fills = presend_live_fill, arms = presend_live_arm)")
P("| run | window PKT | our fills | fill mints he traded (D0/D1) | fills where he held / bought within +-60 s | our armed mints | armed mints he traded |")
P("|---|---|---|---|---|---|---|")
ex = []
for name, fn in runs:
    fills = []; arms = set(); t0 = t1 = None
    for line in open(fn):
        if '"presend_live_fill"' not in line and '"presend_live_arm"' not in line and '"run_start"' not in line and '"run_end"' not in line: continue
        d = json.loads(line); t = d.get("t", 0) / 1e9 if d.get("t") else None
        if t: t0 = t0 or t; t1 = t
        if d["ev"] == "presend_live_fill": fills.append(d)
        elif d["ev"] == "presend_live_arm" and (d.get("trig") or {}).get("mint"): arms.add(d["trig"]["mint"])
    fm = {f["mint"] for f in fills}
    near = 0
    for f in fills:
        t = f["t"] / 1e9
        for l in bym.get(f["mint"], []):
            cb = l["close_bt"] or 1e12
            if l["bt"] - 60 <= t <= cb + 60:
                near += 1; ex.append((name, f, l)); break
    P(f"| {name} | {pk(t0) if t0 else '?'} -> {pk(t1) if t1 else '?'} | {len(fills)} | {len(fm & set(bym))} of {len(fm)} | {near} | {len(arms)} | {len(arms & set(bym))} |")
P("\nExamples (our fill vs his lot on the same mint):")
for name, f, l in ex[:12]:
    P(f"- {name} {pk(f['t'] / 1e9)} we bought {f['sol_in'] / 1e9:.3f} slot {f['slot']}; he: {l['bot']} buy slot {l['s']} ({l['s'] - f['slot']:+d} slots) {l['cost']:.3f} SOL, sold after {l['hold_s']} s, P&L {l['pnl']:+.3f}; https://gmgn.ai/sol/token/{l['mint']}")
# haqq overlap
P("\n## Overlap with haqqiUUX (tape on E2x1's mints, MEASURED)")
for dn in ("D0", "D1"):
    x = [l for l in L if l["day"] == dn]; ms = {l["mint"] for l in x}
    hm = {m for m in ms if any(t[4] == HQ for t in Z["trades"].get(m, []) if t[16])}
    # haqq trading within +-60 s of E2x1's lot
    near = 0; before = after = 0; bb = collections.Counter()
    for l in x:
        h = [t for t in Z["trades"].get(l["mint"], []) if t[16] and t[4] == HQ and t[6] and l["bt"] - 60 <= t[3] <= (l["close_bt"] or l["bt"]) + 60]
        if h:
            near += 1; bb[l["bot"]] += 1
            if (h[0][0], h[0][1]) < (l["s"], l["i"]): before += 1
            else: after += 1
    P(f"{dn}: E2x1 mints {len(ms)}; haqq also traded {len(hm)} ({100 * len(hm) / len(ms):.0f}%); lots with a haqq buy within his hold +-60 s: {near} of {len(x)} (haqq bought first in that span {before}, E2x1 first {after}); by bot {dict(bb)}")
open(f"{OUT}/r12.txt", "w").write("\n".join(Lines) + "\n")
