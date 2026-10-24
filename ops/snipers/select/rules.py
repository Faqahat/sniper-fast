#!/usr/bin/env python3
# READ-ONLY, offline: selection rate per filter combination. Universe sample is random, so a combination's launch count in the
# window ~= NU * share in sample. Rate = bought / estimated launches. Then a small decision tree (bought vs universe, universe
# re-weighted to the full window) to read off their filter.
import sys, json, collections, math
S = json.load(open(sys.argv[1])); F = S["features"]; P = S.get("prior", {}); NU = S["n_universe_total"]
U = [dict(F[s], sig=s) for s in S["universe"] if s in F]; W = NU / len(U)
B = collections.defaultdict(list)
sig_of = {}
for b in S["bought"]:
    if b["create_sig"] in F: B[b["w"]].append(dict(F[b["create_sig"]], sig=b["create_sig"]))
def f_(x):
    p = P.get(x["sig"], {})
    tl = {t[0] for t in x["tips"]}
    return dict(sol_quote=x["quote"] == "SOL", dev=x["dev_sol"], tool=x["host"] in ("metadata.j7tracker.io", "meta.uxento.io", "m.rapidlaunch.io"),
                tip_paid=bool(tl), lunar="lunar" in tl, prior=p.get("prior", 0), prior24=p.get("prior24", 0), age_h=p.get("age_h"))
RULES = {
    "SOL quote": lambda f: f["sol_quote"],
    "+ dev buy >= 0.5": lambda f: f["sol_quote"] and f["dev"] >= 0.5,
    "+ dev buy >= 1": lambda f: f["sol_quote"] and f["dev"] >= 1,
    "+ dev >= 0.5 + create tipped": lambda f: f["sol_quote"] and f["dev"] >= 0.5 and f["tip_paid"],
    "+ dev >= 0.5 + tipped + creator >= 50 prior txs": lambda f: f["sol_quote"] and f["dev"] >= 0.5 and f["tip_paid"] and f["prior"] >= 50,
    "+ dev >= 0.5 + tipped + creator >= 500 prior txs": lambda f: f["sol_quote"] and f["dev"] >= 0.5 and f["tip_paid"] and f["prior"] >= 500,
    "+ dev >= 0.5 + Lunar tip": lambda f: f["sol_quote"] and f["dev"] >= 0.5 and f["lunar"],
    "+ dev >= 0.5 + launch tool host": lambda f: f["sol_quote"] and f["dev"] >= 0.5 and f["tool"],
}
print(f"window: {NU} launches (~{NU / 50:.0f}/h); universe sample {len(U)}")
print(f"{'filter':52} {'launches':>9} " + " ".join(f"{w + ' buys(cover)':>22}" for w in B) + "   all 3: bought / launches")
for rn, r in RULES.items():
    nu = sum(1 for x in U if r(f_(x))) * W
    cells = []; tot = 0
    for w, v in B.items():
        k = sum(1 for x in v if r(f_(x))); tot += k
        cells.append(f"{k:>5} ({k / len(v):4.0%}) {k / nu if nu else 0:7.1%}")
    print(f"{rn:52} {nu:9.0f} " + " ".join(f"{c:>22}" for c in cells) + f"   {tot / nu if nu else 0:6.1%}")
# prior-activity profile of the creators they buy vs all creators (strictly before the create)
def bucket(n): return "0" if n == 0 else ("1-9" if n < 10 else ("10-99" if n < 100 else ("100-999" if n < 1000 else "1000+")))
print("\ncreator's transactions BEFORE the create:")
cu = collections.Counter(bucket(f_(x)["prior"]) for x in U)
for b in ("0", "1-9", "10-99", "100-999", "1000+"):
    print(f"   {b:8} all launches {cu[b] / len(U):6.1%}   " + "   ".join(f"{w} {sum(1 for x in v if bucket(f_(x)['prior']) == b) / len(v):6.1%}" for w, v in B.items()))
