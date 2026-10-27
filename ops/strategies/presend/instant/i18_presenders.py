#!/usr/bin/env python3
# INSTANT-BOTS study, step 18 (read-only): pre-sender table per run: fills, attempts (failed + no-op) per fill, attempts per slot while
# streaming (max in one slot before the dump, median over fills), share of fills <= 5 / <= 10 positions after the dump, fee per attempt
# (median / mean from the recorded fees), attempt fees per fill, net SOL (fee payer's SOL delta over all its recorded txs).
# usage: python3 -I i18_presenders.py TAG   (uses /home/moiz/sniper-data/presend_instant/<TAG>_*)
import sys, json, gzip, collections, statistics
D = "/home/moiz/sniper-data/presend_instant"; tag = sys.argv[1]
C = json.load(open(f"{D}/{tag}_classes.json")); P = json.load(open(f"{D}/{tag}_profiles.json"))
KEY = ["9K5QgBKa", "CZ77onJz", "FNuoWSQc", "Dk2jdQ93", "FUru6V3L", "5ZKd8DNB", "8g1w4PNC", "2KtcBCfh", "CVPz447t", "5k2Ckkiu", "2XyiEK56", "7VrFNnRw"]
full = {w[:8]: w for w in P}
fee = collections.defaultdict(list)
for l in gzip.open(f"{D}/{tag}_wtx.jsonl.gz", "rt"):
    s, i, sig, sg, err, f, cup, cul, cu, pr, ixn, mints, tr, tips, sd0 = json.loads(l)
    k = sg[0][:8]
    if k in KEY and (err or not tr): fee[k].append(f or 0)
out = {}
print(f"{tag}: bot | fills | attempts/fill (failed, no-op) | max attempts in one slot (median) | fills <=5 / <=10 positions | fee/attempt med, mean | attempt fees per fill | net SOL")
for k in KEY:
    w = full.get(k)
    if not w: continue
    p = P[w]; ev = [r for r in C if r["u"] == w]; fills = p["buys"]
    if fills < 5: continue
    mx = [r["own_max_per_slot"] for r in ev if r["cls"] == "P"]
    fe = sorted(fee[k]); att = p["failed"] + p["noop"]
    mean = sum(fe) / len(fe) if fe else 0
    o = dict(w=w, fills=fills, att_per_fill=att / fills, failed=p["failed"], noop=p["noop"], max_slot=statistics.median(mx) if mx else None,
             le5=sum(1 for r in ev if r["gap"] <= 5) / fills, le10=sum(1 for r in ev if r["gap"] <= 10) / fills, fee_med=fe[len(fe) // 2] if fe else None, fee_mean=mean,
             att_cost_per_fill=att * mean / fills / 1e9, pnl=p["pnl_sol"], h1=f"{p['h1_any']}/{p['fast']}")
    out[k] = o
    print(f"{k} | {fills} | {o['att_per_fill']:.0f} ({p['failed']}, {p['noop']}) | {o['max_slot']} | {100 * o['le5']:.0f}% / {100 * o['le10']:.0f}% | {o['fee_med']}, {mean:.0f} | {o['att_cost_per_fill']:.4f} | {p['pnl_sol']:+.2f}")
json.dump(out, open(f"{D}/{tag}_presenders.json", "w"), indent=1)
