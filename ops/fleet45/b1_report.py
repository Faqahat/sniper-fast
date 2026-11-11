#!/usr/bin/env python3
"""dip46 B1 LOG shadow: the offline report (docs/dip46_b1.md).

  b1_report.py --engine dip_fra_rNN.jsonl [more.jsonl ...] [--fills dip_ams_rMM.jsonl ...] [--rule b1|b0]
               [--calib ~/sniper-data/gatecheck/calib.pkl] [--model testdata/dip46_b1_model.json]

--engine  jsonl of the run(s) with --presend-live-b1-log on (the FRA dry run): "presend_live_b1" window records
--fills   optional jsonl(s) of LIVE runs (AMS): their presend_live_arm / presend_live_fill on the same token inside a window make it
          "same" (the engine's own live / dry overlap counts too); everything else is "new"
Prints the FILTERS-style rows (windows, same / new, would-fills, won / lost, net raw AND calibrated, per fill, later-buy median, gate
split, per day PKT), the parity check (every record's features re-scored by the offline Python scorer: decoder, value, feat_hash) and
the frozen pass / stop lines. Read-only; no network.

Calibrated = ~/sniper-data/gatecheck/calib.pkl: the mean real SOL of our fills by (kind, paper-value bucket); kind t2 -> 'T2',
rearm -> 'rearm', other -> the mean of the two. Net = sum(value) - 0.055 mSOL per armed slot (frozen; slots = fill slot - start + 1,
else 8).
"""
import argparse, os, sys, json, pickle, datetime, collections, math
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b1_lib as B

PKT = datetime.timezone(datetime.timedelta(hours=5))
ap = argparse.ArgumentParser()
ap.add_argument("--engine", nargs="+", required=True); ap.add_argument("--fills", nargs="*", default=[])
ap.add_argument("--rule", default="b1", choices=["b1", "b0"])
ap.add_argument("--calib", default=os.path.expanduser("~/sniper-data/gatecheck/calib.pkl"))
ap.add_argument("--model", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../testdata/dip46_b1_model.json"))
ap.add_argument("--cost-slot", type=float, default=0.055e-3)
ap.add_argument("--boot", type=int, default=2000)
a = ap.parse_args()


def recs(path, ev):
    with open(path) as fh:
        for l in fh:
            if ev not in l: continue
            try: yield json.loads(l)
            except json.JSONDecodeError: continue


W = []; cfgs = []
for p in a.engine:
    for r in recs(p, "presend_live_b1"):
        if r.get("stage") == "window": r["_src"] = os.path.basename(p); W.append(r)
        elif r.get("stage") == "config": cfgs.append(r)
print(f"engine records: {len(W)} windows from {len(a.engine)} file(s); configs {len(cfgs)}; model sha {set(c.get('model_sha') for c in cfgs)}")

# ---- parity: the offline Python scorer on every logged feature vector ----------------------------------------------------
M = B.Model(a.model)
bad_dec = bad_val = bad_hash = bad_sha = 0; mx = 0.0
for r in W:
    f = [float(x) for x in r["f"]]
    if B.feat_hash(f) != r["feat_hash"]: bad_hash += 1
    if r.get("model_sha") != M.sha[:16]: bad_sha += 1
    p, v = M.score(f); mx = max(mx, abs(p - r["dec_score"]))
    if abs(p - r["dec_score"]) > 1e-9: bad_dec += 1
    rv = r.get("b0_score")
    if (v is None) != (rv is None) or (v is not None and abs(v - rv) > 1e-9): bad_val += 1
    elif v is not None: mx = max(mx, abs(v - rv))
parity_bad = bad_dec + bad_val + bad_hash + bad_sha
print(f"PARITY (offline scorer vs engine) on {len(W)} windows: decoder mismatches {bad_dec}, value mismatches {bad_val}, feat_hash {bad_hash}, model_sha {bad_sha}"
      f" | max |diff| {mx:.2e} -> {'OK' if parity_bad == 0 else 'MISMATCH'}")

# ---- AMS live overlap -------------------------------------------------------------------------------------------------------
live = collections.defaultdict(list)   # mint -> [(from, to)]
for p in a.fills:
    for r in recs(p, "presend_live_"):
        ev = r.get("ev")
        if ev == "presend_live_fill" and r.get("mint") and r.get("slot"): live[r["mint"]].append((r["slot"], r["slot"]))
        elif ev == "presend_live_arm":
            m = r.get("mint") or (r.get("trig") or {}).get("mint"); s0 = (r.get("trig") or {}).get("slot") or r.get("slot") or (r.get("dump") or {}).get("slot")
            if m and s0: live[m].append((s0, r.get("en_slot") or s0 + 23))

# ---- calibration --------------------------------------------------------------------------------------------------------------
cal = pickle.load(open(a.calib, "rb")); bins = cal["bins"]; cm = {}
for (k, iv), v in cal["cal"].items(): cm[(k, iv.left, iv.right)] = v
def calib(kind, x):
    for lo, hi in zip(bins[:-1], bins[1:]):
        if lo < x <= hi:
            if kind == "t2": return cm[("T2", lo, hi)]
            if kind == "rearm": return cm[("rearm", lo, hi)]
            return 0.5 * (cm[("T2", lo, hi)] + cm[("rearm", lo, hi)])
    return x

rows = []
for r in W:
    if not r["opens"].get(a.rule): continue
    end = r.get("end_slot", r["slot"] + 7)
    same = r["overlap"] == "same" or any(lo <= end and hi >= r["slot"] for lo, hi in live.get(r["mint"], []))
    fill = bool(r.get("fill"))
    slots = (r.get("dslot_fill", 7) + 1) if fill else (end - r["slot"] + 1)
    raw = r["paper_sol"] if fill else 0.0
    t = r["eval"]["t"]
    day = datetime.datetime.fromtimestamp(t / 1e9, PKT).strftime("%m-%d") if t else "?"
    rows.append(dict(same=same, fill=fill, raw=raw, cal=calib(r["kind"], raw) if fill else 0.0, cost=a.cost_slot * slots, kind=r["kind"], lb=r.get("later_buy_sol_3"),
                     pre8=(r.get("gate_pre8") or 0) > 0, on2=bool(r.get("gate_on2")), on8=bool(r.get("gate_on8")), day=day, t=t, complete=r.get("complete", True)))
if not rows: print(f"no {a.rule.upper()} windows"); sys.exit(0)
ts = [x["t"] for x in rows if x["t"]]
hours = max(1e-9, (max(ts) - min(ts)) / 3.6e12) if ts else float("nan")
print(f"{a.rule.upper()} windows {len(rows)} over {hours:.1f} h (record times), incomplete at run end {sum(1 for x in rows if not x['complete'])}")


def line(name, xs, h):
    n = len(xs); f = [x for x in xs if x["fill"]]
    if n == 0: return f"{name:<22} windows     0"
    won = sum(1 for x in f if x["raw"] > 0); cost = sum(x["cost"] for x in xs)
    net_raw = sum(x["raw"] for x in f) - cost; net_cal = sum(x["cal"] for x in f) - cost
    lb = [x["lb"] for x in f if x["lb"] is not None]; med = float(np.median(lb)) if lb else float("nan")
    pf = 1000 * net_cal / len(f) if f else float("nan"); per_day = 24 / h if h > 0 else float("nan")
    return (f"{name:<22} windows {n:6d} | would-fills {len(f):5d} won {won:5d} lost {len(f) - won:5d} | net raw {net_raw:+8.3f} cal {net_cal:+8.3f} SOL "
            f"(cal {pf:+6.1f} mSOL/fill; /day raw {net_raw * per_day:+7.2f} cal {net_cal * per_day:+7.2f}) | later-buy median {med:5.2f} "
            f">=1.4 {np.mean([v >= 1.4 for v in lb]) if lb else float('nan'):4.0%} <1.0 {np.mean([v < 1.0 for v in lb]) if lb else float('nan'):4.0%} | fills/day {len(f) * per_day:6.0f}")


print("\n=== FILTERS row:", a.rule.upper(), "(LOG ONLY shadow; paper at position 26, 0.8 SOL, 3-slot exit) ===")
print(line("ALL", rows, hours))
print(line("  same (live overlap)", [x for x in rows if x["same"]], hours))
print(line("  NEW", [x for x in rows if not x["same"]], hours))
for k in ("t2", "rearm", "other"):
    print(line(f"  NEW kind {k}", [x for x in rows if not x["same"] and x["kind"] == k], hours))
print(line("  gate pre-exec seen", [x for x in rows if x["pre8"]], hours))
print(line("  gate exec-only", [x for x in rows if not x["pre8"]], hours))
print(line("  fleet on2", [x for x in rows if x["on2"]], hours))
print(line("  fleet on8 only", [x for x in rows if x["on8"] and not x["on2"]], hours))
print(line("  no fleet in 8", [x for x in rows if not x["on8"]], hours))

print("\n=== per day (PKT) ===")
days = sorted(set(x["day"] for x in rows)); rng = np.random.default_rng(46); day_ok = []
for d in days:
    xs = [x for x in rows if x["day"] == d]; dt = [x["t"] for x in xs if x["t"]]
    h = max(1e-9, (max(dt) - min(dt)) / 3.6e12) if dt else float("nan")
    nf = [x["cal"] - x["cost"] for x in xs if x["fill"] and not x["same"]]
    lo = float("nan")
    if len(nf) >= 5:
        v = np.array(nf); bs = rng.choice(v, size=(a.boot, len(v)), replace=True).mean(axis=1); lo = float(np.percentile(bs, 5))
        day_ok.append((d, 1000 * v.mean(), 1000 * lo))
    print(line(f"{d} ({h:4.1f} h)", xs, h), f"| NEW cal per fill {1000 * np.mean(nf) if nf else float('nan'):+6.1f} mSOL, bootstrap 5% {1000 * lo:+6.1f}")

# ---- frozen pass / stop lines -----------------------------------------------------------------------------------------------
fills = [x for x in rows if x["fill"]]; newf = [x for x in fills if not x["same"]]
lb = [x["lb"] for x in fills if x["lb"] is not None]; med = float(np.median(lb)) if lb else float("nan")
ndays = hours / 24
pf_new = 1000 * np.mean([x["cal"] - x["cost"] for x in newf]) if newf else float("nan")
good_days = sum(1 for d in day_ok if d[1] >= 6 and d[2] > 0)
print("\n=== PASS / STOP (frozen, B1 LOG PLAN v1) ===")
print(f"  coverage   : {ndays:.2f} days (>= 3) and {len(fills)} would-fills (>= 1,200) -> {'PASS' if ndays >= 3 and len(fills) >= 1200 else 'NOT YET'}")
print(f"  edge       : NEW would-fills {len(newf)}, calibrated {pf_new:+.1f} mSOL/fill (>= +6); days with mean >= +6 and bootstrap 5% > 0: {good_days} of {len(day_ok)} "
      f"(need >= 3 of 4) -> {'PASS' if pf_new >= 6 and good_days >= 3 else 'NOT YET / FAIL'}")
print(f"  followers  : later-buy median {med:.2f} (pass >= 1.4, kill < 1.0) -> {'PASS' if med >= 1.4 else ('KILL' if med < 1.0 else 'between')}")
print(f"  parity     : {parity_bad} mismatches (must be 0) -> {'PASS' if parity_bad == 0 else 'FAIL'}")
