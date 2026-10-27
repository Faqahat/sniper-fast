#!/usr/bin/env python3
"""dipmon's totals on finished local runs == the standard run reports (ops/dip/reports/runs/*.md), each figure to +-0.0005 SOL.

The reports print 4 decimals, so a figure matches when |dipmon - report| <= 0.0005 SOL (in practice they agree to the 4th
decimal). The wallet line compares dipmon's estimate (the last session's START BALANCE + its P&L) with the budget file's end
balance: the gap is the fees of pre-send tries never seen on the feed (the report's own note), so it must be <= that bound."""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import dipmon  # noqa: E402

DATA = os.environ.get("DIPMON_DATA", "/home/moiz/sniper-data/runs")
REPORTS = os.environ.get("DIPMON_REPORTS", "/home/moiz/sniper/ops/dip/reports/runs")
RUNS = [("ams", 24), ("ams", 25), ("ams", 26), ("fra", 24), ("fra", 25), ("ams", 23)]
TOL = 0.0005


def report_figures(path):
    t = open(path).read()
    f = {}
    m = re.search(r"Result \(chain, after every cost\) \| \*\*([-+][\d.]+) SOL\*\*(?: \(wallet ([\d.]+) → ([\d.]+), Δ ([-+][\d.]+)\))?", t)
    f["total"] = float(m.group(1))
    if m.group(2):
        f["wallet0"], f["wallet1"] = float(m.group(2)), float(m.group(3))
    m = re.search(r"\| Buys sent \| (\d+) → \*\*(\d+) filled\*\*, (\d+) failed on the \+5% guard(?:, (\d+) failed \(other\))?", t)
    f["reg_fires"], f["reg_fills"], f["reg_guard"], f["reg_other"] = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4) or 0)
    m = re.search(r"\| Wins / losses \(fills\) \| (\d+) / (\d+)", t)
    f["reg_wins"] = int(m.group(1))
    m = re.search(r"\| Fills only / failed buys only \| ([-+][\d.]+) / ([-+][\d.]+) SOL", t)
    f["reg_fill_pnl"], f["reg_fail_pnl"] = float(m.group(1)), float(m.group(2))
    m = re.search(r"\| Reactive bot / pre-send live \| ([-+][\d.]+) / ([-+][\d.]+) SOL \(pre-send: (\d+) fills, realized ([-+][\d.]+), "
                  r"(?:rent back ([-+][\d.]+), )?failed-attempt fees ([-+][\d.]+), (\d+) wins", t)
    if m:
        f["reg_total"], f["ps_net"] = float(m.group(1)), float(m.group(2))
        f["ps_fills"], f["ps_real"], f["ps_rent"] = int(m.group(3)), float(m.group(4)), float(m.group(5) or 0)
        f["ps_fees"], f["ps_wins"] = -float(m.group(6)), int(m.group(7))
    else:
        f["reg_total"] = f["total"]
        f["ps_net"] = f["ps_fills"] = f["ps_real"] = f["ps_rent"] = f["ps_fees"] = f["ps_wins"] = 0
    m = re.search(r"pre-send tries never seen on our feed[^(]*\(up to ([\d.]+) SOL", t) or re.search(r"Tries never seen on our feed: [\d,]+\. If they landed and failed they cost up to ([\d.]+) SOL", t)
    f["unseen_bound"] = float(m.group(1)) if m else 0.0
    return f


def budget_end(region, run):
    p = os.path.join(DATA, region, "dip_budget_ams.json" if region == "ams" else "dip_budget.json")
    try:
        rows = [r for r in json.load(open(p))["runs"] if r.get("run") == run]
        return rows[-1].get("end_balance") / 1e9 if rows and rows[-1].get("end_balance") else None
    except Exception:
        return None


def main():
    fails = 0
    rows = []
    print(f"{'run':<8} {'figure':<14} {'report':>10} {'dipmon':>10} {'diff':>9}  ok")
    for region, run in RUNS:
        tag = f"dip_ams_r{run}" if region == "ams" else f"dip_r{run}"
        rp = os.path.join(REPORTS, f"{region.upper()}_run{run:02d}.md")
        jp = os.path.join(DATA, region, "runs", tag + ".jsonl")
        if not (os.path.exists(rp) and os.path.exists(jp)):
            print(f"{region}{run}: missing report or data, skipped")
            continue
        R = report_figures(rp)
        src = dipmon.Source(jp)
        src.load_all()
        T = dipmon.run_totals(src.model)
        D = {"total": T["total"] / 1e9, "ps_fills": T["ps_fills"], "ps_wins": T["ps_wins"], "ps_real": T["ps_real"] / 1e9,
             "ps_rent": T["ps_rent"] / 1e9, "ps_fees": T["ps_fees"] / 1e9, "ps_net": T["ps_net"] / 1e9, "reg_fires": T["reg_fires"],
             "reg_fills": T["reg_fills"], "reg_wins": T["reg_wins"], "reg_guard": T["reg_guard"],
             "reg_other": T["reg_lighthouse"] + T["reg_other"], "reg_fill_pnl": T["reg_fill_pnl"] / 1e9,
             "reg_fail_pnl": T["reg_fail_pnl"] / 1e9, "reg_total": T["reg_total"] / 1e9}
        name = f"{region.upper()} r{run}"
        for k in ("ps_fills", "ps_wins", "ps_real", "ps_rent", "ps_fees", "ps_net", "reg_fires", "reg_fills", "reg_wins", "reg_guard",
                  "reg_other", "reg_fill_pnl", "reg_fail_pnl", "reg_total", "total"):
            a, b = R[k], D[k]
            ok = (a == b) if isinstance(a, int) else abs(a - b) <= TOL
            fails += not ok
            diff = "" if isinstance(a, int) else f"{b - a:+.5f}"
            print(f"{name:<8} {k:<14} {a:>10} {(b if isinstance(b, int) else round(b, 4)):>10} {diff:>9}  {'ok' if ok else 'FAIL'}")
        # wallet: dipmon's estimate vs the budget file's end balance (gap = unseen pre-send tries' fees, the report's note)
        S = src.model.sessions[-1]
        est = (S.start_bal + S.total()) / 1e9 if S.start_bal is not None else None
        end = budget_end(region, run)
        if est is not None and end is not None:
            unseen = sum(x.ps_res.get("unseen", 0) for x in src.model.sessions[-1:]) * dipmon.PS_FAIL_FEE / 1e9
            gap = end - est
            ok = gap <= TOL and -gap <= unseen + TOL
            fails += not ok
            print(f"{name:<8} {'wallet end':<14} {end:>10.4f} {est:>10.4f} {gap:>+9.5f}  {'ok' if ok else 'FAIL'}  "
                  f"(est. = START BALANCE {S.start_bal / 1e9:.4f} + session P&L; gap <= unseen tries' fees {unseen:.4f})")
        rows.append((name, D["total"]))
        print()
    print("RESULT:", "PASS" if not fails else f"FAIL ({fails})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
