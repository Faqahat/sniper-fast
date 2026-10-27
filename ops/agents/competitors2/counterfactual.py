#!/usr/bin/env python3
# competitors2/counterfactual.py -- READ-ONLY. For each FAILED fire: replay the curve from the dump's post-trade reserves applying
# only the trades between the dump and our buy, leaving out a group of wallets, and check whether our min_out would then have
# been met (= that group alone cost us the fill). Groups: pre-positioned streams (wallet had >= 2 txs on the mint in S-1..dump),
# each top rival alone, and "everyone ahead of us by >= X positions" (speed what-if). Also the SOL bought ahead by class.
import json, gzip, collections, statistics
D2 = "/home/moiz/sniper-data/competitors2"
US = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
fires = {f["buy_sig"]: f for f in json.load(open(f"{D2}/fires.json"))}
def out_tokens(x, v, t): return t - v * t // (v + x)
res = []
for l in gzip.open(f"{D2}/races.jsonl.gz", "rt"):
    R = json.loads(l)
    for fr in R["fires"]:
        f = fires.get(fr["buy_sig"])
        if not f: continue
        A = R["after"]; k = next(j for j, a in enumerate(A) if a["sig"] == fr["buy_sig"])
        S = R["s"]; d0 = R["dump"]["tr"]; v0, t0 = d0[4], d0[5]; T = fr["min_out"] * 1.05
        x = int(v0 * t0 / (t0 - T) - v0)
        stream = {w for w, n in collections.Counter(b["w"] for b in R["before"] if b["s"] >= S - 1).items() if n >= 2}
        trades = []   # (wallet, dsol, dtok, slot, idx) applied in order
        for a in A[:k]:
            if a["err"] is not None or a["w"] in US: continue
            # every trade event of this tx on our mint: rebuild from the post-trade reserves chain (only last one kept) -> use deltas
            if not a["tr"]: continue
            trades.append((a["w"], a))
        def replay(skip):
            v, t = v0, t0
            for w, a in trades:
                if skip(w, a): continue
                sol, tok, buy = a["tr"][0], a["tr"][1], a["tr"][2]
                if buy: v += sol; t -= tok
                else: v -= sol; t += tok
            return out_tokens(x, v, t) >= fr["min_out"]
        full = replay(lambda w, a: False)
        di_us = (A[k]["i"] - R["dump"]["i"]) if A[k]["s"] == S else 10**6
        r = dict(fill=fr["fill"], replay_fill=full, region=fr["region"], kind=R["li"].get("kind"), stream=sorted(stream & {w for w, _ in trades}),
                 no_stream=replay(lambda w, a: w in stream),
                 sol_stream=sum(a["tr"][0] for w, a in trades if w in stream and a["tr"][2]) / 1e9,
                 sol_react=sum(a["tr"][0] for w, a in trades if w not in stream and a["tr"][2]) / 1e9,
                 sol_sell=sum(a["tr"][0] for w, a in trades if not a["tr"][2]) / 1e9,
                 ahead_w=sorted({w for w, a in trades if a["tr"][2]}))
        for w in set(r["ahead_w"]): r.setdefault("alone", {})[w] = replay(lambda ww, a, w=w: ww == w)
        # speed what-if: we land N positions earlier in the same slot (txs between our new spot and old spot no longer ahead)
        for gain in (10, 25, 50, 100):
            if A[k]["s"] == S: r[f"earlier_{gain}"] = replay(lambda w, a, g=gain: a["s"] == S and a["i"] - R["dump"]["i"] >= di_us - g)
            else: r[f"earlier_{gain}"] = replay(lambda w, a, g=gain: a["s"] > S)   # next-slot landings: drop the S+1 trades ahead (as if we made slot S)
        res.append(r)
F = [r for r in res if not r["fill"]]
print(f"failed fires {len(F)}; replay agrees (no fill) {sum(1 for r in F if not r['replay_fill'])}")
print(f"would fill without pre-positioned streams: {sum(r['no_stream'] for r in F)} / {len(F)}  (fires with a stream buy ahead: {sum(1 for r in F if r['stream'])})")
print(f"SOL bought ahead of us per failed fire, median: streams {statistics.median([r['sol_stream'] for r in F]):.3f}, reactive {statistics.median([r['sol_react'] for r in F]):.3f}; totals {sum(r['sol_stream'] for r in F):.2f} / {sum(r['sol_react'] for r in F):.2f} SOL")
alone = collections.Counter(); present = collections.Counter()
for r in F:
    for w, ok in r.get("alone", {}).items(): present[w] += 1; alone[w] += ok
print("\nremoving ONE wallet's buys turns the loss into a fill (pivotal wallet): top")
for w, n in alone.most_common(15): print(f"   {w[:9]}  pivotal {n} / present {present[w]}")
print("\nspeed what-if (land N positions earlier in the dump slot; next-slot landings moved into S):")
for g in (10, 25, 50, 100): print(f"   {g:3d} positions earlier: {sum(r[f'earlier_{g}'] for r in F)} / {len(F)} failed fires would fill")
for kd in ("bam", "harmonic", "jito"):
    X = [r for r in F if r["kind"] == kd]
    print(f"   {kd:9s} n={len(X)}: 25 earlier {sum(r['earlier_25'] for r in X)}, 50 earlier {sum(r['earlier_50'] for r in X)}, 100 earlier {sum(r['earlier_100'] for r in X)}; no streams {sum(r['no_stream'] for r in X)}")
json.dump(res, open(f"{D2}/counterfactual.json", "w"))
