#!/usr/bin/env python3
# ANTI-DUMP selection check (read-only, offline): which pick rule gets GOOD tokens and avoids FAST DUMPS?
# Rules / thresholds are chosen on VAL (last 20% of run 1 = the frozen models' holdout); TEST = the forward run (never
# used to fit or choose anything). Entry: right after the creator's bundle (speed set aside, as the owner asked).
# fast dump = price <= 0.85x of our entry within 5 s; good = not a fast dump and >= 1.1x at 30 s or peak >= 1.5x.
# usage: python3 g_dump_eval.py <table_dump.jsonl.gz> <run2 start bt> <model.json,...>
import sys, os, json, gzip, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from live2score import load
TAB, FWD0, MODS = sys.argv[1], float(sys.argv[2]), sys.argv[3].split(",")
FIXR = 0.015 / 0.5
R = [json.loads(l) for l in gzip.open(TAB, "rt")]
R = [r for r in R if r.get("quote_sol") == 1 and (r.get("max_vsol") or 0) <= 200 and r.get("bt") and r.get("E_bundle_h5s") is not None]
R.sort(key=lambda r: (r["bt"], r["S"]))
run1 = [r for r in R if r["bt"] < FWD0]; val0 = run1[int(len(run1) * .8)]["bt"]
VAL = [r for r in run1 if r["bt"] >= val0]; TEST = [r for r in R if r["bt"] >= FWD0 and r["bt"] <= max(x["bt"] for x in R) - 900]
models = {}
for p in MODS:
    M, sc = load(p); nm = os.path.basename(p).replace("frozen_", "").replace(".json", "")
    models[nm] = (M, sc)
    for r in VAL + TEST: r["_" + nm] = sc(r)
EX = [("fsell_30s_eos", "first sell, end of slot"), ("fsell_30s", "first sell, instant"), ("h5s", "hold 5 s"), ("h30s", "hold 30 s"),
      ("trail20_10_s15_2m", "trail +20/-10, stop -15, 2 min"), ("tp20_sl10_30s", "+20% / -10%, 30 s")]
def row(lab, rs, hrs):
    if not rs: return f"  {lab:58} n=0"
    d5 = sum(r["y_dump5"] for r in rs) / len(rs); gd = sum(r["y_good"] for r in rs) / len(rs)
    v = [r["E_bundle_fsell_30s_eos"] - FIXR for r in rs]
    ex = "  ".join(f"{k.split('_')[0] if k.startswith(('fsell', 'trail', 'tp')) else k}:{statistics.mean(r['E_bundle_' + k] - FIXR for r in rs):+.1%}" for k, _ in EX)
    return (f"  {lab:58} n={len(rs):4} ({len(rs) / hrs:4.1f}/h) dump {d5:4.0%} good {gd:4.0%} | first-sell(eos) mean {statistics.mean(v):+.1%} med {statistics.median(v):+.1%}"
            f" win {sum(1 for x in v if x > 0) / len(v):3.0%} total {sum(v) * 0.5:+.2f} SOL | {ex}")
def rules(r):
    return dict(cr=not (r.get("hd_cr_n", 0) >= 1 and (r.get("hd_cr_fast") or 0) >= 0.5),
                bw=not ((r.get("hd_bw_worst") or 0) >= 0.5),
                dev=not ((r.get("hd_dev_fast") or 0) >= 0.5))
for name, rs in (("VAL (run 1, last 20%: used to choose)", VAL), ("TEST (forward run, never used)", TEST)):
    hrs = (rs[-1]["bt"] - rs[0]["bt"]) / 3600
    print(f"\n=== {name}: {len(rs)} SOL launches, {hrs:.1f} h | all launches: dump {sum(r['y_dump5'] for r in rs) / len(rs):.0%} good {sum(r['y_good'] for r in rs) / len(rs):.0%}")
    for nm, (M, _) in models.items():
        for top in ("1%", "2%", "5%"):
            P = [r for r in rs if r["_" + nm] >= M["thresholds"][top]]
            print(row(f"{nm} top {top}", P, hrs))
            if nm == "live2_fsell" and top in ("2%", "5%"):
                for rl in ("cr", "bw", "dev"):
                    print(row(f"   + no fast-dump {'creator' if rl == 'cr' else 'bundle wallet' if rl == 'bw' else 'dev wallet'} history", [r for r in P if rules(r)[rl]], hrs))
                print(row("   + all three", [r for r in P if all(rules(r).values())], hrs))
