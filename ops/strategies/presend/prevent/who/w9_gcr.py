#!/usr/bin/env python3
"""WHO step 9: who drives the post-hoc G-cr (creator fair-list) result: skipped fills per creator, w/o the top creator, listing times, r38 six."""
import pickle, json, collections, sys, datetime
import numpy as np
D = "/home/it/sniper-data/prevent/who"
X = pickle.load(open(f"{D}/rules_posthoc.pkl", "rb")); meta, res = X["meta"], X["res"]
S = json.load(open(f"{D}/score_rules_posthoc.json"))["rules"]
PKT = lambda t: datetime.datetime.utcfromtimestamp(t + 5 * 3600).strftime("%m-%d %H:%M")
for name in ["G-cr fair-list creator m2 S0.05", "G-cr fair-list creator m3 S0.05", "G-cr fair-list creator m2 S0.2", "G fair-list m2 S0.1"]:
    sk = res[name][1]
    by = collections.defaultdict(lambda: collections.defaultdict(float)); first = {}
    for m, s in zip(meta, sk):
        if not s or m["mode"] != "live": continue
        c = (m["creator"] or "?")[:8]
        by[c][m["run"]] += -m["val_s"]; first.setdefault(c, m["t"])
    tot = {c: sum(v.values()) for c, v in by.items()}
    pt = lambda c: sum(v for r, v in by[c].items() if r not in ("AMS38",))
    print(f"== {name}: verdict {S[name]['verdict']} | live saving by creator (top 8), first skip time PKT")
    for c in sorted(tot, key=lambda z: -abs(tot[z]))[:8]:
        print(f"   {c} total {tot[c]:+.3f}  first skip {PKT(first[c])}  runs " + ", ".join(f"{r} {v:+.3f}" for r, v in sorted(by[c].items())))
    top = max(tot, key=lambda z: pt(z))
    print(f"   PICK+TEST saving {S[name]['pt']:+.3f}; without the top creator ({top}): {S[name]['pt'] - pt(top):+.3f}; six r38 losses skipped: {S[name]['six']} 5cMetpCp {S[name]['five_c']}")
