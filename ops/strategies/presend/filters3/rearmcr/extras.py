#!/usr/bin/env python3
"""REARM-CREATOR step 5: (a) one-position effect ESTIMATE of the blocked re-arm fills, (b) drawdown / variance effect, (c) biggest blocked trades."""
import json, collections
D = "/home/moiz/sniper-data/filters3/rearmcr"
R = json.load(open(f"{D}/rows.json"))
fills = [x for x in R["rearm"] if x["filled"] and x["pnl"] is not None]
RULES = {"cr>=6": lambda x: x["cr_pct"] >= 6, "cr>=10": lambda x: x["cr_pct"] >= 10, "cr>=15": lambda x: x["cr_pct"] >= 15,
         "cr_only_holder": lambda x: [w for w, p in x["holders"]] == [x["creator"]] if x["creator"] else False}
# skips on the same token caused by our open position / account
blk = collections.defaultdict(list)
for r in range(38, 52):
    for l in open(f"{D}/ext/r{r}.jsonl"):
        if '"presend_live_skip"' not in l and '"presend_live_rearm_defer"' not in l: continue
        d = json.loads(l)
        why = d.get("why")
        if why in ("blocked_position", "blocked_ata_open", "rearm_blocked_position", "rearm_blocked_ata_open", "rearm_blocked_rearm_armed") or d["ev"] == "presend_live_rearm_defer":
            t = (d.get("dump") or {}).get("t") or (d.get("trig") or {}).get("t") or d.get("t")
            blk[r].append((d["mint"] if "mint" in d else (d.get("trig") or {}).get("mint"), t, why if d["ev"] != "presend_live_rearm_defer" else "defer"))
live_fill_t = collections.defaultdict(list)
for x in R["fills"]:
    if x["t"]: live_fill_t[(x["r"], x["mint"])].append(x["t"])
sh = collections.defaultdict(list)
for s in R["shadow"]: sh[s["r"]].append(s)
wins = collections.defaultdict(list)
for w in R["wins"]: wins[w["r"]].append(w)
# shadow-vs-live calibration on the same T2 triggers (fills both sides), mean per fill
lt2 = collections.defaultdict(list)
for x in R["fills"]:
    if x["kind"] == "t2": lt2[(x["r"], x["mint"])].append(x["pnl"])
pairs = [(s["net"], sum(lt2[(s["r"], s["mint"])])) for s in R["shadow"] if (s["r"], s["mint"]) in lt2 and s["net"] is not None]
cal = (sum(b for a, b in pairs) / len(pairs), sum(a for a, b in pairs) / len(pairs))
print(f"calibration: {len(pairs)} T2 triggers filled live+shadow: live mean {cal[0]*1000:+.2f} mSOL vs shadow row c {cal[1]*1000:+.2f} mSOL per fill")
for name, f in RULES.items():
    print(f"\n== {name}: one-position effect (ESTIMATE)")
    for per in ("DEV", "VAL", "HOLD"):
        xs = [x for x in fills if x["per"] == per and f(x)]
        hold_s = 0.0; n_sh = 0; v_sh = 0.0; n_ov = 0; n_ov_nofill = 0; n_blk = collections.Counter()
        for x in xs:
            a = x["tf"]; b = x["tx"] or (a + 2 * 10**9)
            b = max(b, a + 300 * 10**6)
            hold_s += (b - a) / 1e9
            for s in sh[x["r"]]:
                if a <= s["t"] <= b and s["mint"] != x["mint"] and s["net"] is not None:
                    lf = live_fill_t.get((x["r"], s["mint"]), [])
                    if not any(abs(t - s["t"]) < 30 * 10**9 for t in lf): n_sh += 1; v_sh += s["net"]
            for w in wins[x["r"]]:
                if w["mint"] == x["mint"] or w["ta"] is None: continue
                if w["ta"] <= b and (w["tend"] or w["ta"]) >= a:
                    n_ov += 1
                    if not w["filled"]: n_ov_nofill += 1
            for m, t, why in blk[x["r"]]:
                if m == x["mint"] and t and a - 1e9 <= t <= b + 3e9: n_blk[why] += 1
        print(f"  {per}: blocked fills {len(xs)}, position-open time {hold_s:.0f} s total; other live windows open meanwhile {n_ov} (never filled {n_ov_nofill}); "
              f"shadow row-c T2 fills on other tokens inside those holds that live never took: {n_sh} worth {v_sh:+.3f} SOL (shadow); same-token skips/defers: {dict(n_blk)}")
# drawdown / variance
def mdd(seq):
    c = pk = m = 0.0
    for v in seq:
        c += v; pk = max(pk, c); m = min(m, c - pk)
    return c, m
print("\n== drawdown (all live fills T2 + re-arm, chronological, per period)")
CUT = 1793516400 * 10**9
def per_of(r, t):
    return "DEV" if r <= 41 or (r == 42 and t < CUT) else "VAL" if r == 42 else "HOLD"
allf = [x for x in R["fills"] if x["t"]]
blocked = {}
for name, f in RULES.items(): blocked[name] = {(x["r"], x["w"]) for x in fills if f(x)}
for per in ("DEV", "VAL", "HOLD"):
    seq = sorted([x for x in allf if per_of(x["r"], x["t"]) == per], key=lambda x: x["t"])
    tot, m = mdd([x["pnl"] for x in seq])
    line = f"  {per}: base total {tot:+.3f} maxDD {m:+.3f}"
    for name in RULES:
        t2, m2 = mdd([x["pnl"] for x in seq if (x["r"], x["w"]) not in blocked[name]])
        line += f" | {name}: total {t2:+.3f} maxDD {m2:+.3f}"
    print(line)
print("\n== loss tail of re-arm fills, by creator band (all periods): n, sum, worst, p5, share of fills <= -0.05")
for lo, hi in ((0, 2), (2, 6), (6, 15), (15, 101)):
    xs = sorted(x["pnl"] for x in fills if lo <= x["cr_pct"] < hi)
    n = len(xs)
    print(f"  cr {lo}-{hi}%: n {n} sum {sum(xs):+.3f} mean {1000*sum(xs)/n:+.1f} mSOL worst {xs[0]:+.3f} p5 {xs[int(0.05*n)]:+.3f} big-loss share {100*sum(1 for v in xs if v <= -0.05)/n:.1f}% big-win share {100*sum(1 for v in xs if v >= 0.05)/n:.1f}%")
print("\n== top-5 saves / top-5 costs of cr>=6 per period")
for per in ("DEV", "VAL", "HOLD"):
    xs = sorted([x for x in fills if x["per"] == per and x["cr_pct"] >= 6], key=lambda x: x["pnl"])
    print(f"  {per} worst:", [(f"r{x['r']}", x["mint"][:8], round(x["cr_pct"], 1), round(x["pnl"], 3)) for x in xs[:5]])
    print(f"  {per} best: ", [(f"r{x['r']}", x["mint"][:8], round(x["cr_pct"], 1), round(x["pnl"], 3)) for x in xs[-5:]])
