#!/usr/bin/env python3
"""HAQQ_STRAT step 6 (read-only): haqq's dip buys (DIP / DIP_LATE / ADD-on-dump lots) in the last 24 h while one of our engines
was live, and why we had no landed tx on that dump. His net P&L (s3 lot accounting) per reason. MEASURED.
Reason order: we landed a tx > pre-send armed on the mint (window covers the dump) > regular path: dump logged in our envelope ->
M2 no / pick skipped (engine's why) / picked not fired; else outside our envelope (sell < 1.08 SOL, drop < 4.66%, age > 344 s)."""
import json, pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_strat")
from hs_lib import *
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def main():
    L = pickle.load(open(f"{D}/live.pkl", "rb")); lots = pickle.load(open(f"{D}/lots24.pkl", "rb")); h2h = pickle.load(open(f"{D}/h2h.pkl", "rb"))
    att = {}
    for e in h2h:
        if e["us"]: att.setdefault((e["mint"], e["ds"], e["di"]), []).append(e)
    att_m = collections.defaultdict(list)
    for (m, ds, di), v in att.items(): att_m[m].append(ds)
    runs = [(R["start"], R["end"], run, R) for run, R in L.items() if R["start"]]
    rows = []
    for r in lots:
        b = r["b"]
        if r["probe"] or r["t"] not in ("DIP", "DIP_LATE", "ADD") or b.get("d_slot") is None: continue
        if r["t"] == "ADD" and b.get("d_drop", 0) < 0.05: continue
        live = [x for x in runs if x[0] <= b["bt"] <= x[1]]
        if not live: rows.append((r, "no engine live", None)); continue
        key = (b["mint"], b["d_slot"], b["d_i"])
        if key in att:
            rows.append((r, "we landed a tx: " + ("fill" if any(e["fill"] for e in att[key]) else "failed/late") + " (" + att[key][0]["kind"] + ")", None)); continue
        if any(abs(ds - b["d_slot"]) <= 2 for ds in att_m.get(b["mint"], [])):
            rows.append((r, "we landed a tx on a neighbouring dump", None)); continue
        why = None
        for st, en, run, R in live:
            for a in R["arms"]:
                if a["mint"] == b["mint"] and a["slot"] <= b["d_slot"] <= (a["en"] or a["slot"] + 10): why = "pre-send armed, nothing landed"; break
            if why: break
            dm = R.setdefault("_dix", {(v["mint"], v["slot"], v["idx"]): (s, v) for s, v in R["dumps"].items()})
            hit = dm.get(key)
            if hit:
                s, v = hit
                if not v["m2_pick"]: why = "M2 said no"
                elif s in R["pick_skip"]: why = "picked, skipped: " + R["pick_skip"][s]
                else: why = "picked, not fired (other)"
                break
        if not why:
            if run.startswith("FRA") and all(x[2].startswith("FRA") for x in live): pass
            if b["d_sol"] < 1.08: why = "outside envelope: dump < 1.08 SOL"
            elif b["d_drop"] < 0.0466: why = "outside envelope: drop < 4.7%"
            elif (b["d_age"] or 0) * 0.212 > 344: why = "outside envelope: token > 5.7 min old"
            else: why = "dump not logged (in envelope by our measure)"
        rows.append((r, why, None))
    P(f"# haqq dip lots in the last 24 h vs our engines ({len(rows):,} lots; his net per lot from s3)")
    P("| reason | lots | his net SOL | mSOL/lot | win | his median ms after dump |"); P("|---|---|---|---|---|---|")
    c = collections.defaultdict(list)
    for r, why, _ in rows: c[why].append(r)
    J = {}
    for why, v in sorted(c.items(), key=lambda kv: -sum(x["net"] for x in kv[1])):
        n = sum(x["net"] for x in v)
        P(f"| {why} | {len(v)} | {n:+.2f} | {1000 * n / len(v):+.1f} | {100 * np.mean([x['net'] > 0 for x in v]):.0f}% | {np.median([x['b']['d_ms'] for x in v]):.0f} |")
        J[why] = dict(n=len(v), net=n)
    json.dump(J, open(f"{D}/s6.json", "w"), indent=1)
    open(f"{D}/s6.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
