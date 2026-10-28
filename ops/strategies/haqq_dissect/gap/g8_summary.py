#!/usr/bin/env python3
"""GAP step 8 (read-only): summary tables over the full test days D2-D5 (10-24 .. 10-27, engines running):
 1. waterfall per day side by side + mean, with a 90 % bootstrap range (lots resampled within bucket and day) for his buckets;
 2. what our engine did with the dumps under his ADD / DIP_LATE lots (same classifier as the DIP lots);
 3. his gate-refused DIP lots by dumper type and by the dumper's pre-send status (create-slot whale etc.);
 4. his tokens with 1 lot vs 2+ lots per day (positions view).
Out: gap/g8_summary.txt"""
import pickle, collections, json, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/gap")
from g3_ledger import grp, classify
OUT = "/home/moiz/sniper-data/haqq_dissect/gap"
DAYS = (2, 3, 4, 5)


def boot(v, n=2000, seed=3):
    v = np.asarray(v, float)
    if len(v) == 0: return (0.0, 0.0)
    r = np.random.default_rng(seed); s = v[r.integers(0, len(v), (n, len(v)))].sum(1)
    return float(np.percentile(s, 5)), float(np.percentile(s, 95))


def main():
    Z = pickle.load(open(f"{OUT}/g3_rows.pkl", "rb")); rows = Z["rows"]
    W = json.load(open(f"{OUT}/g4.json"))["W"]
    out = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s); out.append(s)
    # 1. waterfall side by side
    names = [nm for nm, v, n in W["5"]["lines"]]
    P("# 1. Waterfall haqq -> us, SOL per day (MEASURED lots / wallet; f split INFERRED arithmetic on MEASURED values)")
    P("| step | " + " | ".join(L.day_name(d)[:9] for d in DAYS) + " | mean D2-D5 | his-bucket 90% range of the mean |")
    P("|---|" + "---|" * (len(DAYS) + 2))
    P("| haqq net | " + " | ".join(f"{W[str(d)]['X']:+.2f}" for d in DAYS) + f" | {np.mean([W[str(d)]['X'] for d in DAYS]):+.2f} | |")
    def bk_rows(nm):
        if nm.startswith("tape hour"): return lambda r: r["bucket"] == "NOCOV"
        if nm.startswith("a."): return lambda r: r["bucket"] == "a"
        if nm.startswith("b. type"): t = nm.split()[-1]; return lambda r: r["bucket"] == "b" and r["reason"] == t
        if nm.startswith("c."): g = nm[3:]; return lambda r: r["bucket"] == "c" and grp(r["reason"]) == g
        if nm.startswith("e. guard"): return lambda r: r["bucket"] == "e"
        return None
    for nm in names:
        vals = [dict((a, v) for a, v, n in W[str(d)]["lines"]).get(nm, 0.0) for d in DAYS]
        f = bk_rows(nm); rng = ""
        if f:
            per = []
            for d in DAYS: per.append([-r["net"] for r in rows if r["day"] == d and f(r)])
            r_ = np.random.default_rng(5); sims = []
            for _ in range(1000):
                sims.append(np.mean([np.sum(np.asarray(v)[r_.integers(0, len(v), len(v))]) if len(v) else 0.0 for v in per]))
            rng = f"{np.percentile(sims, 5):+.2f} .. {np.percentile(sims, 95):+.2f}"
        P(f"| {nm} | " + " | ".join(f"{v:+.2f}" for v in vals) + f" | {np.mean(vals):+.2f} | {rng} |")
    P("| = our wallet P&L | " + " | ".join(f"{W[str(d)]['Y']:+.3f}" for d in DAYS) + f" | {np.mean([W[str(d)]['Y'] for d in DAYS]):+.3f} | |")
    # 2. engine view of his ADD / DIP_LATE dumps
    RUNS = pickle.load(open(f"{OUT}/g2_engine.pkl", "rb"))
    runs = sorted((X["start"], X["end"], rn, X) for rn, X in RUNS.items() if X["start"] and not X["probe_run"])
    for X in RUNS.values():
        live_arms = [a for a in X["arms"] if not a[9]]
        X["ps_on"] = len(live_arms) > 0 or len(X["patt"]) > 0
        X["arms_by"] = collections.defaultdict(list); X["sk_by"] = collections.defaultdict(list)
        for a in live_arms: X["arms_by"][(a[0], a[1])].append(a)
        for s in X["pskips"]: X["sk_by"][(s[0], s[1])].append(s)
    ids, idm = L.ids_map()
    P("\n# 2. His ADD and DIP_LATE lots that sit on a >= 5 % dump within 2 slots (b bucket): what our running engine did with that dump (MEASURED logs)")
    P("| type | engine reason (grouped) | lots D2-D5 | his net | per day |"); P("|---|---|---|---|---|")
    g = collections.defaultdict(list)
    for r in rows:
        b = r["b"]
        if r["day"] not in DAYS or r["bucket"] != "b" or r["reason"] not in ("ADD", "DIP_LATE"): continue
        if b.get("d_slot") is None or b["d_drop"] < 0.05 or b["d_slots"] > 2:
            g[(r["reason"], "no >=5% dump within 2 slots")].append(r); continue
        tr = [(rn, X) for s, e, rn, X in runs if s <= b["bt"] <= e]
        c = classify(b, tr, ids); g[(r["reason"], grp(c["reason"]))].append(r)
    for k, v in sorted(g.items(), key=lambda kv: (kv[0][0], -sum(r["net"] for r in kv[1]))):
        P(f"| {k[0]} | {k[1]} | {len(v)} | {sum(r['net'] for r in v):+.2f} | {sum(r['net'] for r in v) / len(DAYS):+.2f} |")
    # 3. gate-refused by dumper type / pre-send status
    P("\n# 3. His gate-refused DIP lots (c bucket) D2-D5 by dumper type and the pre-send view of the dumper (MEASURED)")
    P("| dumper type | lots | his net | per day | win % | dumper held >= 6 % before the dump |"); P("|---|---|---|---|---|---|")
    G = [r for r in rows if r["day"] in DAYS and r["bucket"] == "c" and grp(r["reason"]) == "gate refused (M2/IMIT1)"]
    gt = collections.defaultdict(list)
    for r in G: gt[r["b"]["d_type"]].append(r)
    for k, v in sorted(gt.items(), key=lambda kv: -sum(r["net"] for r in kv[1])):
        P(f"| {k} | {len(v)} | {sum(r['net'] for r in v):+.2f} | {sum(r['net'] for r in v) / 4:+.2f} | {100 * np.mean([r['net'] > 0 for r in v]):.0f} | {100 * np.mean([(r['b'].get('d_bal_pct') or 0) >= 6 for r in v]):.0f}% |")
    P("\n| pre-send view of the dumper (runs with live pre-send only) | lots | his net | win % |"); P("|---|---|---|---|")
    pv = collections.defaultdict(list)
    for r in G: pv[r.get("ps_reason", "?")].append(r)
    for k, v in sorted(pv.items(), key=lambda kv: -sum(r["net"] for r in kv[1])):
        P(f"| {k} | {len(v)} | {sum(r['net'] for r in v):+.2f} | {100 * np.mean([r['net'] > 0 for r in v]):.0f} |")
    # 4. tokens with 1 lot vs 2+ lots
    P("\n# 4. His tokens per day: 1 lot vs 2+ lots (all buckets; MEASURED; NOT causal - the lot count is known only afterwards)")
    P("| day | tokens 1 lot | net | tokens 2+ lots | net | of which first lot | later lots |"); P("|---|---|---|---|---|---|---|")
    for d in range(0, 7):
        tm = collections.defaultdict(list)
        for r in rows:
            if r["day"] == d: tm[r["b"]["mint"]].append(r)
        one = [v for v in tm.values() if len(v) == 1]; mul = [v for v in tm.values() if len(v) > 1]
        first = sum(sorted(v, key=lambda r: r["b"]["bt"])[0]["net"] for v in mul); later = sum(r["net"] for v in mul for r in v) - first
        P(f"| {L.day_name(d)} | {len(one)} | {sum(r['net'] for v in one for r in v):+.2f} | {len(mul)} | {sum(r['net'] for v in mul for r in v):+.2f} | {first:+.2f} | {later:+.2f} |")
    open(f"{OUT}/g8_summary.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
