#!/usr/bin/env python3
"""BOT P&L analysis. Read-only on pass1/pass2 output.
Trips: per (bot, mint), the bot's own landed txs in order; a trip opens on the first buy and closes when its token balance is back
to ~0. P&L = the bot's lamport deltas (fees and tips included). Trips still open at the end are valued at the last curve price
seen on that mint (pass 2), minus 1% sell fee. Dip context (pass 2): the largest sell by another wallet in the 3 slots up to the
bot's first buy, its drop (curve), and the slot gap. Overlap: OURS landed a buy on the same mint within 10 slots of the bot's buy.
usage: analyze.py OUTDIR"""
import sys, os, json, glob, collections
out = sys.argv[1]
W = {"haqqiUUX": "haqq", "2VggYpPu": "haqq", "haqq6qnV": "haqq", "8yYMhuYo": "8yYMhu", "DF7eRXHn": "DF7eRX",
     "E2x1ewwX": "E2x1", "CvHEVC7S": "CvHEVC7S", "HLU8QbLd": "HLU8QbLd", "6VzXcLk9": "6VzXcLk9", "4ggJqUDD": "4ggJqUDD",
     "DSvgfynk": "DSvgfynk", "EgxfYgEb": "OURS", "2g7rYv7y": "OURS"}
V = 73_000_000_000_000
def price(c): return 1.0 / (c + V) ** 2 if c is not None else None
rep = []
for rd in sorted(glob.glob(f"{out}/run_*")):
    r = os.path.basename(rd)
    tx = []                                             # (s, i, bt, bot, wallet, mint, tok, sol)
    for fn in glob.glob(f"{rd}/p1_*.jsonl"):
        for l in open(fn, errors="replace"):
            d = json.loads(l)
            if d.get("err") is not None: 
                for sg in d.get("signers") or []:
                    if sg[:8] in W: tx.append((d["s"], d.get("i") or 0, d.get("bt"), W[sg[:8]], sg, None, 0, dict(d.get("sd") or []).get(sg, 0)))
                continue
            sd = dict((a, v) for a, v in (d.get("sd") or []))
            for sg in d.get("signers") or []:
                if sg[:8] not in W: continue
                mm = collections.Counter()
                for m, own, pre, post in d.get("tb") or []:
                    if own == sg: mm[m] += (post or 0) - (pre or 0)
                m = max(mm, key=lambda k: abs(mm[k])) if mm else None
                tx.append((d["s"], d.get("i") or 0, d.get("bt"), W[sg[:8]], sg, m, mm.get(m, 0), sd.get(sg, 0)))
    tx.sort()
    # pass 2: per mint trades for dip context and last price
    p2 = collections.defaultdict(list)
    for fn in glob.glob(f"{rd}/p2_*.jsonl"):
        for l in open(fn):
            x = json.loads(l)
            if not x["err"]: p2[x["mint"]].append(x)
    for v in p2.values(): v.sort(key=lambda x: (x["s"], x["i"] or 0))
    ours_buys = collections.defaultdict(list)
    for s, i, bt, bot, w, m, tok, sol in tx:
        if bot == "OURS" and m and tok > 0: ours_buys[m].append(s)
    trips, pos, failed = [], {}, collections.Counter()
    t0 = min(t[2] for t in tx if t[2]); t1 = max(t[2] for t in tx if t[2])
    for s, i, bt, bot, w, m, tok, sol in tx:
        if m is None:
            failed[bot] += 1; failed[(bot, "sol")] += sol; continue
        k = (bot, m)
        if k not in pos:
            if tok <= 0: continue                       # a sell of a position opened before the recording
            pos[k] = {"bot": bot, "w": w, "mint": m, "s0": s, "bt0": bt, "bal": 0, "sol": 0, "nb": 0, "spend": 0}
        p = pos[k]; p["bal"] += tok; p["sol"] += sol
        if tok > 0: p["nb"] += 1; p["spend"] += -sol
        if p["bal"] <= 1000:
            p["s1"] = s; trips.append(pos.pop(k))
    for k, p in pos.items():                            # open at the end: mark to the last curve price
        tr = p2.get(p["mint"]) or []
        last = next((x for x in reversed(tr) if x["cpost"] is not None and x["tok"]), None)
        buy = next((x for x in tr if x["u"] == p["w"] and x["tok"] > 0), None)
        if last and buy and buy["tok"]:
            pb = -buy["sol"] / buy["tok"]               # lamports per token at the bot's buy (incl. its costs)
            val = p["bal"] * pb * price(last["cpost"]) / price(buy["cpost"]) * 0.99 if buy["cpost"] is not None else 0
        else: val = 0
        p["sol"] += val; p["open"] = True; p["s1"] = None; trips.append(p)
    for p in trips:                                     # dip context + overlap
        tr = p2.get(p["mint"]) or []
        pre = [x for x in tr if p["s0"] - 3 <= x["s"] <= p["s0"] and x["u"] != p["w"] and x["tok"] < 0 and x["sol"] > 0]
        pre = [x for x in pre if (x["s"], x["i"] or 0) < next(((y["s"], y["i"] or 0) for y in tr if y["u"] == p["w"] and y["s"] >= p["s0"]), (p["s0"], 1 << 30))]
        if pre:
            dmp = max(pre, key=lambda x: x["sol"])
            p["dump_sol"] = dmp["sol"] / 1e9; p["dump_gap"] = p["s0"] - dmp["s"]
            if dmp["cpre"] is not None and dmp["cpost"] is not None: p["drop"] = 1 - price(dmp["cpost"]) / price(dmp["cpre"])
        p["ours"] = any(abs(s - p["s0"]) <= 10 for s in ours_buys.get(p["mint"], []))
        p["ours_before"] = any(0 <= p["s0"] - s <= 10 for s in ours_buys.get(p["mint"], []))
    hrs = (t1 - t0) / 3600
    print(f"\n=== {r}  {hrs:.1f} h  (PKT {__import__('time').strftime('%m-%d %H:%M', __import__('time').gmtime(t0 + 18000))} -> {__import__('time').strftime('%m-%d %H:%M', __import__('time').gmtime(t1 + 18000))})")
    print(f"{'bot':10s} {'trips':>6s} {'net SOL':>8s} {'/day':>7s} {'win':>4s} {'mSOL/trip':>9s} {'size':>5s} {'hold slots p50':>14s} {'dip%':>5s} {'dump SOL':>8s} {'gap0':>5s} {'w/ OURS':>7s} {'OURS net':>8s} {'fail tx':>7s} {'fail SOL':>8s} {'NET+fail/day':>12s}")
    by = collections.defaultdict(list)
    for p in trips: by[p["bot"]].append(p)
    for bot, ps in sorted(by.items(), key=lambda kv: -sum(p["sol"] for p in kv[1])):
        net = sum(p["sol"] for p in ps) / 1e9
        hold = sorted(p["s1"] - p["s0"] for p in ps if p.get("s1") is not None)
        dips = sorted(p["drop"] for p in ps if "drop" in p); dsol = sorted(p["dump_sol"] for p in ps if "dump_sol" in p)
        g0 = sum(1 for p in ps if p.get("dump_gap") == 0) / len(ps)
        wo = [p for p in ps if p["ours"]]
        print(f"{bot:10s} {len(ps):6d} {net:+8.2f} {net / hrs * 24:+7.2f} {sum(1 for p in ps if p['sol'] > 0) / len(ps):4.0%} {net / len(ps) * 1000:+9.2f} "
              f"{sorted(p['spend'] for p in ps)[len(ps) // 2] / 1e9:5.2f} {hold[len(hold) // 2] if hold else -1:14d} "
              f"{100 * dips[len(dips) // 2] if dips else 0:5.1f} {dsol[len(dsol) // 2] if dsol else 0:8.2f} {g0:5.0%} {len(wo):7d} {sum(p['sol'] for p in wo) / 1e9:+8.2f} "
              f"{failed[bot]:7d} {failed[(bot, 'sol')] / 1e9:+8.3f} {(net + failed[(bot, 'sol')] / 1e9) / hrs * 24:+12.2f}")
    json.dump([{k: v for k, v in p.items()} for p in trips], open(f"{rd}/trips.json", "w"))
