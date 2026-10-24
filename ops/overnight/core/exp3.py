# fewer wasted (failed) buys: skip listed deployers on which our guarded buys almost never fill (walk-forward fill rate)
import sys, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import exp
exp.R = json.load(open("allres_static_0034.json"))
S9 = exp.S9
def run_fr(Lm, min_att, max_rate, fail_cost):
    L, R = exp.L, exp.R
    ev = sorted([(bt, 0, d, w) for bt, d, w in exp.LED] + [(c["bt"], 1, m, None) for m, c in L.items() if c.get("bt")])
    att = collections.defaultdict(collections.Counter); nl = collections.Counter(); hist = collections.defaultdict(list); tries = collections.defaultdict(lambda: [0, 0]); pend = []
    out = collections.defaultdict(list)
    for bt, kind, x, w in ev:
        while pend and pend[0][0] <= bt:
            _, d, v, ok = pend.pop(0); tries[d][0] += 1; tries[d][1] += ok
            if v is not None: hist[d].append(v)
        if kind == 0: att[w][x] += 1; continue
        m = x; c = L[m]; d = c["user"]; r = R.get(m)
        if r and str(Lm) in r:
            st = dict(att={k: att[k][d] for k in att}, n=nl[d], hist=hist[d], r=r)
            a, okc = tries[d]
            skip = a >= min_att and okc / a < max_rate
            if exp.listed(st, S9) and exp.gate_ok(st) and not skip:
                o = r[str(Lm)]; v = (o.get("0.5") if o["ok"] else -fail_cost)
                if v is not None: out[r["run"]].append(v)
            o = r[str(Lm)]
            pend.append((bt + 60, d, o.get("0.5") if o["ok"] else None, 1 if o["ok"] else 0)); pend.sort(key=lambda z: z[0])
        nl[d] += 1
        for k in exp.ATT.get(m, {}): att[k][d] += 1
    return {k: (sum(v), sum(1 for x in v if x != -fail_cost), len(v)) for k, v in out.items()}
for fc in (0.005, 0.011):
    print(f"\nfailed guarded buy costs {fc} SOL (75 ms):")
    for min_att, max_rate in ((10 ** 9, 0), (5, 0.10), (5, 0.20), (8, 0.15)):
        r = run_fr(75, min_att, max_rate, fc)
        lab = "S4G (no fill-rate skip)" if min_att > 10 ** 8 else f"S4G + skip deployers with fill rate < {max_rate:.0%} after {min_att} tries"
        print(f"   {lab:62} " + " | ".join(f"{k} {t:+.2f} ({f}/{n})" for k, (t, f, n) in sorted(r.items())))
