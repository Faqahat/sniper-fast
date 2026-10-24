# fill-ability vs landing position: would a B-SOL buy with a +5% max-price guard (min_out from the post-dump state) fill
# if it landed at same-slot index gap d (or next slot)?  Uses the curve state after the last other buy before that position.
import json, gzip, collections, sys
B = "/home/moiz/sniper/ops/agents/topearners/work/"
SOL = 0.35e9; G = 1.05
def tokens_out(V, T, x, fr=0.0125):
    X = x / (1 + fr); return T * X / (V + X)
D_SAME = [5, 10, 20, 35, 50, 75, 100, 150, 200, 300, 500]
res = {d: [0, 0] for d in D_SAME}; nxt = {d: [0, 0] for d in (0, 50, 150, 400)}
nr = 0
our_dsigs = set()
J = json.load(open(B + "our_join.json"))
for f in J["fires"]: our_dsigs.add(f["dump_sig"])
ours = {d: [0, 0] for d in D_SAME}
for line in gzip.open(B + "races.jsonl.gz", "rt"):
    r = json.loads(line)
    V0, T0 = r["vsol"], r["vtok"]
    if not T0 or V0 < 25e9 or V0 > 110e9: continue
    if r["sol"] < 1e9: continue
    nr += 1
    need = tokens_out(V0, T0, SOL) / G
    buys = r["buys"]
    def state_before(ds, idx):
        V, T = V0, T0
        for b in buys:
            if (b[1], b[2]) < (ds, idx): V, T = b[13], b[14]
            else: break
        return V, T
    for d in D_SAME:
        V, T = state_before(0, r["i"] + d)
        ok = tokens_out(V, T, SOL) >= need
        res[d][0] += 1; res[d][1] += ok
        if r["sig"] in our_dsigs: ours[d][0] += 1; ours[d][1] += ok
    for d in nxt:
        V, T = state_before(1, d)
        ok = tokens_out(V, T, SOL) >= need
        nxt[d][0] += 1; nxt[d][1] += ok
print("races used (>=1 SOL sells, curve 25-110 SOL):", nr)
print("P(0.35 SOL buy with +5% guard fills) if landing at same-slot index gap d:")
print("   all dumps : " + "  ".join(f"d={d}:{v[1]/v[0]:.2f}" for d, v in res.items()))
print("   our fired : " + "  ".join(f"d={d}:{v[1]/max(1,v[0]):.2f}" for d, v in ours.items()), " (n=%d)" % ours[5][0])
print("   next slot : " + "  ".join(f"pos={d}:{v[1]/v[0]:.2f}" for d, v in nxt.items()))
