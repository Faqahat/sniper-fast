#!/usr/bin/env python3
"""GUARDS step 7: score the replays (g4 guard rows, g6 context / SL rows) with the pre-registered bar.
Per window: delta = variant - base (SOL at 0.696, mean over reps). Blocks = (run, PKT hour) for the 90% bootstrap CI (PICK + TEST).
usage: g7_score.py"""
import json, glob, collections, os
import numpy as np
D = "/home/it/sniper-data/prevent/guards"
PICK = ["f26", "f27", "f28", "r34", "r35", "r36"]; TEST = "r37"
HOURS = {"r34": 3.2, "r35": 4.2, "r36": 3.9, "f26": 1.9, "f27": 12.0, "f28": 5.5, "r37": 10.8}
rng = np.random.default_rng(7)


def per_window(rows_list):
    """list over reps of rows (ses, w, hour, filled, pnl, ...) -> {(ses, w): (hour, mean pnl, mean filled)}"""
    acc = collections.defaultdict(lambda: [0, 0.0, 0.0, 0])
    for rows in rows_list:
        for r in rows:
            a = acc[(r[0], r[1])]; a[0] = r[2]; a[1] += r[4]; a[2] += r[3]; a[3] += 1
    return {k: (v[0], v[1] / v[3], v[2] / v[3]) for k, v in acc.items()}


def score(name, getter):
    """getter(run) -> (base rows list, var rows list, base_cut rows list, var_cut rows list) or None"""
    per = {}; deltas = []; blocks = collections.defaultdict(float)
    for run in PICK + [TEST]:
        g = getter(run)
        if g is None: continue
        b, v, bc, vc = (per_window(x) for x in g)
        d = {k: v[k][1] - b[k][1] for k in b}
        dc = {k: vc[k][1] - bc[k][1] for k in bc}
        per[run] = {"base": sum(x[1] for x in b.values()), "var": sum(x[1] for x in v.values()), "delta": sum(d.values()), "delta_cut": sum(dc.values()),
                    "fills_base": sum(x[2] for x in b.values()), "fills_var": sum(x[2] for x in v.values()),
                    "per_day": sum(d.values()) / HOURS[run] * 24}
        for k, x in d.items():
            deltas.append((run, k, x)); blocks[(run, b[k][0])] += x
    if TEST not in per or not any(r in per for r in PICK): return None
    pk = sum(per[r]["delta"] for r in PICK if r in per)
    allv = np.array([x for _, _, x in deltas]); srt = np.sort(allv)[::-1]
    bl = np.array(list(blocks.values()))
    boots = [bl[rng.integers(len(bl), size=len(bl))].sum() for _ in range(3000)]
    pick_d = sorted([x for r, _, x in deltas if r in PICK], reverse=True)
    out = {"name": name, "per_run": per, "pick_delta": pk, "pick_per_day": pk / sum(HOURS[r] for r in PICK) * 24, "test_delta": per[TEST]["delta"],
           "test_per_day": per[TEST]["per_day"], "pick_cut": sum(per[r]["delta_cut"] for r in PICK if r in per), "test_cut": per[TEST]["delta_cut"],
           "runs_plus": sum(1 for r in PICK if r in per and per[r]["delta"] > 1e-6), "runs_minus": sum(1 for r in PICK if r in per and per[r]["delta"] < -1e-6),
           "ci90": [float(np.percentile(boots, 5)), float(np.percentile(boots, 95))], "all_delta": float(allv.sum()),
           "pick_wo_top1": pk - (pick_d[0] if pick_d and pick_d[0] > 0 else 0), "all_wo_top1": float(allv.sum() - max(srt[0], 0)),
           "all_wo_top5": float(allv.sum() - srt[:5].clip(min=0).sum())}
    out["pass"] = bool(out["test_delta"] > 0 and out["runs_plus"] > out["runs_minus"] and out["ci90"][0] > 0 and out["all_wo_top1"] > 0 and out["test_cut"] >= 0 and out["pick_cut"] >= 0)
    return out


res = {}
lines = []
def P(s): lines.append(s); print(s)
# guard replays
for f in sorted(glob.glob(f"{D}/rp_*.json")):
    pass
vars_ = sorted({"_".join(os.path.basename(f)[3:-5].split("_")[1:]) for f in glob.glob(f"{D}/rp_*.json")})
for v in vars_:
    def getter(run, v=v):
        fn = f"{D}/rp_{run}_{v}.json"
        if not os.path.exists(fn): return None
        x = json.load(open(fn))
        return x["base"], x["guard"], x["base_cut"], x["guard_cut"]
    s = score("guard " + v, getter)
    if s: res["guard " + v] = s
# context / SL
ctx_names = ["d15_if_h1", "d18_if_h1", "skip_if_h1", "skip_if_h2", "win5_if_h1", "sl_off", "sl_after1"]
for v in ctx_names:
    def getter(run, v=v):
        fn = f"{D}/ctx_{run}.json"
        if not os.path.exists(fn): return None
        x = json.load(open(fn))["rows"]
        if f"{v}|0.0" not in x: return None
        return x["base|0.0"], x[f"{v}|0.0"], x["base|0.2"], x[f"{v}|0.2"]
    s = score(v, getter)
    if s: res[v] = s
P(f"{'variant':24s} | {'PICK d':>7s} {'/day':>6s} {'r37 d':>7s} {'/day':>6s} | {'PICK -20%':>9s} {'r37 -20%':>8s} | {'runs +/-':>8s} | {'CI90 PICK+TEST':>16s} | {'w/o top1':>8s} {'w/o top5':>8s} | {'fills PICK':>11s} {'fills r37':>11s} | pass")
for k, s in res.items():
    fb = sum(s["per_run"][r]["fills_base"] for r in PICK if r in s["per_run"]); fv = sum(s["per_run"][r]["fills_var"] for r in PICK if r in s["per_run"])
    t = s["per_run"]["r37"]
    P(f"{k:24s} | {s['pick_delta']:+7.3f} {s['pick_per_day']:+6.2f} {s['test_delta']:+7.3f} {s['test_per_day']:+6.2f} | {s['pick_cut']:+9.3f} {s['test_cut']:+8.3f} | {s['runs_plus']:3d}/{s['runs_minus']:<3d}  | "
      f"[{s['ci90'][0]:+6.2f},{s['ci90'][1]:+6.2f}] | {s['all_wo_top1']:+8.3f} {s['all_wo_top5']:+8.3f} | {fb:5.0f}->{fv:5.0f} {t['fills_base']:4.0f}->{t['fills_var']:4.0f} | {'PASS' if s['pass'] else 'no'}")
P("\nper run delta (SOL at 0.696, replay):")
P(f"{'variant':24s} | " + " ".join(f"{r:>7s}" for r in PICK + [TEST]))
for k, s in res.items():
    P(f"{k:24s} | " + " ".join(f"{s['per_run'][r]['delta']:+7.3f}" if r in s["per_run"] else f"{'-':>7s}" for r in PICK + [TEST]))
json.dump(res, open(f"{D}/replay_scores.json", "w"), indent=1)
open(f"{D}/replay_scores.txt", "w").write("\n".join(lines) + "\n")
