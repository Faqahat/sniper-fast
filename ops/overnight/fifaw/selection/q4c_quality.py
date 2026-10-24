#!/usr/bin/env python3
# READ-ONLY, offline. (1) Are FiFawH's picks better than average? Price multiples vs the post-bundle price P0 with ITS OWN
# trades removed (x_ columns, s1_build delta replay) for SOL-quoted non-mayhem launches, vs all other launches (table
# values, same definition). (2) Follow-on demand: distinct non-sniper, non-insider buyers and their SOL after the create
# (q6_res.json demand rows; fast snipers excluded; FiFawH excluded). (3) Its block position on filled snipes.
import json, gzip, collections, statistics as stt
R = [json.loads(l) for l in gzip.open("sel_dataset.jsonl.gz", "rt")]
ok = lambda r: r.get("out_ok") and not r.get("mayhem")
att = [r for r in R if r["att"] and ok(r)]; oth = [r for r in R if not r["att"] and ok(r)]
def q(v, ps=(0.25, 0.5, 0.75)):
    v = sorted(x for x in v if x is not None); return [round(v[int(p * (len(v) - 1))], 3) for p in ps] if v else None
print(f"SOL-quoted non-mayhem launches with an outcome: attempted {len(att)}, others {len(oth)}")
print("checkpoint | attempted (ex-FiFawH) p25/50/75, share>1.1 | others p25/50/75, share>1.1")
for k_x, k_t in (("x_slot", "fslot_px"), ("x_1s", "f1s_px"), ("x_5s", "f5s_px"), ("x_15s", "f15s_px"), ("x_60s", "px_60s"), ("x_peak_10m", "peak_10m")):
    a = [r.get(k_x) for r in att if r.get(k_x) is not None]; o = [r.get(k_t) for r in oth if r.get(k_t) is not None]
    print(f"  {k_x:11} {q(a)} {sum(x > 1.1 for x in a) / len(a):.0%} (n={len(a)}) | {q(o)} {sum(x > 1.1 for x in o) / len(o):.0%} (n={len(o)})")
# controls matched on dev-buy bucket (FiFawH picks have more mid-size dev buys)
def bk(v): return 0 if v < 0.5 else 1 if v < 1 else 2 if v < 3 else 3 if v < 8 else 4
mm = collections.defaultdict(list)
for r in oth: mm[bk(r.get("dev_buy") or 0)].append(r)
print("dev-buy-matched comparison of x_5s / x_60s medians (attempted vs others in same bucket):")
for b in range(5):
    a = [r for r in att if bk(r.get("dev_buy") or 0) == b]
    if len(a) < 5: continue
    print(f"   bucket {b}: n={len(a)} att x_5s {stt.median([r['x_5s'] for r in a if r.get('x_5s')]):.3f} vs {stt.median([r['f5s_px'] for r in mm[b] if r.get('f5s_px')]):.3f}"
          f" | x_60s {stt.median([r['x_60s'] for r in a if r.get('x_60s')]):.3f} vs {stt.median([r['px_60s'] for r in mm[b] if r.get('px_60s')]):.3f}")
# (2) follow-on demand
D = json.load(open("../copy/q6_res.json"))["demand"]; A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts_fifaw.json"))
SETS = json.load(open("../copy/sets.json"))["sets"]; ctrl = set(SETS["(z) random control launches"])
Rm = {r["mint"]: r for r in R}
def solq(m): return Rm.get(m, {}).get("quote_sol") == 1
for nm, ms in (("FiFawH attempts (SOL-quoted)", [m for m in A if m in D and solq(m)]), ("random controls (SOL-quoted)", [m for m in ctrl if m in D and solq(m)])):
    print(f"\n{nm}: n={len(ms)}")
    for w in ("0_2", "2_10", "10_60"):
        g = [D[m][w][0] for m in ms]; f = [D[m][w][1] for m in ms]; gs = [D[m][w][2] for m in ms]; gsl = [D[m][w][3] for m in ms]
        print(f"   {w:5}s: generic buyers mean {stt.mean(g):5.1f} median {stt.median(g):4.0f} | fast snipers mean {stt.mean(f):4.1f} | generic buy SOL mean {stt.mean(gs):6.2f} median {stt.median(gs):5.2f} | generic sell SOL mean {stt.mean(gsl):6.2f}")
# (3) block position of its filled snipes
me = [r for r in R if r["att"] and r.get("me") and r["me"].get("buy_s") is not None]
print(f"\nits landed buys in the replay set: {len(me)}; slot offset {collections.Counter(r['me']['buy_s'] for r in me).most_common(6)}")
print("   outside (non-insider) buys ahead of it in its launch: ", collections.Counter(min(r["me"]["n_before"], 5) for r in me).most_common())
print("   index in block (create slot only) p10/50/90:", q([r["me"]["buy_i"] - (r.get("create_idx") or 0) for r in me if r["me"]["buy_s"] == 0], (0.1, 0.5, 0.9)))
print("   its buy SOL (curve) tiers:", collections.Counter(round(r["me"]["buy_sol"] * 2) / 2 for r in me).most_common(8))
