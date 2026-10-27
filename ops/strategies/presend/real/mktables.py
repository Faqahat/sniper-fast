#!/usr/bin/env python3
"""REAL replay: Markdown tables for REAL_REPLAY.md from the run outputs (calib_<tag>.json, variants_<tag>_raw.pkl).
usage: mktables.py calib TAG | variants TAG [TAG ...] | days TAG NAME [NAME ...]"""
import sys, os, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vreport
OUT = "/home/moiz/sniper-data/presend_real"

def calib(tag):
    J = json.load(open(f"{OUT}/calib_{tag}.json"))
    print("| | Probe 1 (live) | Probe 1 (replay) | Probe 2 (live) | Probe 2 (replay) |")
    print("|---|---|---|---|---|")
    a, b = J["P1"], J["P2"]
    print(f"| Windows | {len(a['pf'])} | same | {len(b['pf'])} | same |")
    print(f"| Fills | {a['live_fills']} | {a['fills_mean']:.1f} ({a['fills_p5']:.0f}-{a['fills_p95']:.0f}) | {b['live_fills']} | {b['fills_mean']:.1f} ({b['fills_p5']:.0f}-{b['fills_p95']:.0f}) |")
    print(f"| Agreement, fill / no fill (mark >= 90%) | - | **{a['agree'] * 100:.1f}%** | - | **{b['agree'] * 100:.1f}%** |")
    print(f"| Net SOL (mark: within +-0.01 of live) | {a['live_net']:+.4f} | **{a['net_mean']:+.4f}** ({a['p5']:+.3f} to {a['p95']:+.3f}) | {b['live_net']:+.4f} | **{b['net_mean']:+.4f}** ({b['p5']:+.3f} to {b['p95']:+.3f}) |")
    print(f"| Fills P&L / failed-try fees, SOL | {a['live_realized']:+.4f} / {a['live_realized'] - a['live_net']:.4f} | {a['pnl']:+.4f} / {a['fees']:.4f} | {b['live_realized']:+.4f} / {b['live_realized'] - b['live_net']:.4f} | {b['pnl']:+.4f} / {b['fees']:.4f} |")
    print(f"| Tries sent / landed | {a['live_sent']} / {a['live_landed']} | {a['sent']:.0f} / {a['landed']:.0f} | {b['live_sent']} / {b['live_landed']} | {b['sent']:.0f} / {b['landed']:.0f} |")
    print(f"| Deadline failures | {a['live_deadline']} | {a['deadline']:.0f} | {b['live_deadline']} | {b['deadline']:.0f} |")
    print(f"| Fill lands after its crossing trade, ms p25/50/75 | {'/'.join('%.0f' % x for x in a['live_xgap'])} | {'/'.join('%.0f' % x for x in a['xgap'])} | {'/'.join('%.0f' % x for x in b['live_xgap'])} | {'/'.join('%.0f' % x for x in b['xgap'])} |")
    print(f"| Live net's place in the replay spread | - | {a['pct_live'] * 100:.0f}th pct | - | {b['pct_live'] * 100:.0f}th pct |")
    print("misses:", b["miss"])

def variants(tags):
    out, nulls, DH = vreport.table(tags)
    print("| Variant | SOL/day | Half 1 | Half 2 | Fills/day | Failed-try cost / fill | P&L / fill (before failed tries) | Null p95 | Pass |")
    print("|---|---|---|---|---|---|---|---|---|")
    for m in out:
        nl = ("%+.2f" % m["null95"]) if m["null95"] is not None else "-"
        print(f"| {m['name']} | {m['day']:+.2f} | {m['h1']:+.2f} | {m['h2']:+.2f} | {m['fills_day']:.0f} | {m['fee_fill']:.4f} | {m['pnl_fill']:+.4f} | {nl} | {'yes' if m['passes'] else 'no'} |")

def days(tag, names):
    out, nulls, DH = vreport.table([tag])
    ds = sorted(DH)
    print("| Variant | " + " | ".join(f"{d} ({DH[d]:.0f} h)" for d in ds) + " |")
    print("|---|" + "---|" * len(ds))
    for m in out:
        if m["name"] in names: print(f"| {m['name']} | " + " | ".join("%+.2f" % m["perday"][d] for d in ds) + " |")

if __name__ == "__main__":
    k = sys.argv[1]
    if k == "calib": calib(sys.argv[2])
    elif k == "variants": variants(sys.argv[2:])
    elif k == "days": days(sys.argv[2], sys.argv[3:])
