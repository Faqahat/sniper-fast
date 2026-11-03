#!/usr/bin/env python3
"""RIVALS85 step 3: each named competitor's presence in the 2x2 groups (F flagged / S shallow no other6 / H other6 deep / N neither),
a Poisson check of its flagged count vs its rate on S and on all non-flagged fills, its median first-sell ratio per group, and the
'selective' subset (named wallets that are rare in flagged fills; POST-HOC pick -> to be confirmed on new runs). Appends to RESULTS.json,
writes the verdict block at the top of RESULTS.txt.
usage: r3_named_groups.py   (after r2_report.py)"""
import pickle, json, math, collections, statistics as st

OUT = "/home/moiz/sniper-data/rivals85"
X = pickle.load(open(f"{OUT}/fills.pkl", "rb")); R = [o for o in X["fills"] if o.get("dump")]
SEL = ["DF7eRXHn", "AEgTuy8L", "EprLoV21", "8PgC4ngp", "GKd5EMzR", "9pQQc1xy"]


def grp(o):
    sh = o["depth"] is not None and o["depth"] < 0.15
    return ("F" if sh else "H") if o["other6"] else ("S" if sh else "N")


def pois_le(k, lam): return sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k + 1))


N = collections.Counter(grp(o) for o in R)
pres = collections.defaultdict(collections.Counter); rat = collections.defaultdict(lambda: collections.defaultdict(list))
for o in R:
    g = grp(o)
    for c in o.get("comp", []):
        if c["named"]:
            pres[c["named"]][g] += 1
            if c.get("ratio") is not None: rat[c["named"]][g].append(c["ratio"])
out = {}
for k, v in pres.items():
    expS = v["S"] / N["S"] * N["F"]; nonF = (v["S"] + v["H"] + v["N"]) / (N["S"] + N["H"] + N["N"]) * N["F"]
    out[k] = {"pct": {g: round(100 * v[g] / N[g], 1) for g in "FSHN"}, "F": v["F"], "exp_at_S_rate": round(expS, 1), "p_le_F_vs_S": round(pois_le(v["F"], expS), 3),
              "exp_at_nonF_rate": round(nonF, 1), "p_le_F_vs_nonF": round(pois_le(v["F"], nonF), 3),
              "median_ratio": {g: (round(st.median(rat[k][g]), 3) if rat[k][g] else None) for g in "FSHN"}}
sel = {g: round(100 * sum(1 for o in R if grp(o) == g and any(c["named"] in SEL for c in o.get("comp", []))) / N[g], 1) for g in "FSHN"}
oth = {g: round(100 * sum(1 for o in R if grp(o) == g and any(c["named"] and c["named"] not in SEL for c in o.get("comp", []))) / N[g], 1) for g in "FSHN"}
res = json.load(open(f"{OUT}/RESULTS.json"))
res["named_by_group"] = {"group_fills": dict(N), "wallets": out, "selective_set": SEL, "selective_present_pct": sel, "other_named_present_pct": oth}
json.dump(res, open(f"{OUT}/RESULTS.json", "w"), indent=1)
L = ["J. named wallets by group (% of fills with the wallet in the dump's slot+next): F / S / H / N | flagged count, expected at S rate, P(<=) | median ratio F/S/H/N"]
for k, v in sorted(out.items(), key=lambda kv: -sum(pres[kv[0]].values())):
    p = v["pct"]; m = v["median_ratio"]
    L.append(f"{k:9s} {p['F']:5.1f} {p['S']:5.1f} {p['H']:5.1f} {p['N']:5.1f} | {v['F']:3d} {v['exp_at_S_rate']:5.1f} {v['p_le_F_vs_S']:.3f} | {m['F']} / {m['S']} / {m['H']} / {m['N']}")
L.append(f"selective set {SEL} (POST-HOC): present in F {sel['F']}% / S {sel['S']}% / H {sel['H']}% / N {sel['N']}% ; other named: {oth}")
open(f"{OUT}/RESULTS.txt", "a").write("\n" + "\n".join(L) + "\n")
print("\n".join(L))
