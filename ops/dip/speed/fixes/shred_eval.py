#!/usr/bin/env python3
"""SHRED FIRE shadow / live evaluator (engine dip14 --dip-shred-fire; ops/dip/speed/fixes/FIXES.md).

usage: python3 shred_eval.py --jsonl dip_rN.jsonl [more.jsonl ...] [--json out.json]

From the engine's records:
  shred_dump    every decision on a dump's first shred sighting (pick / nopick / depends / skip:<why>, the index range, prices)
  shred_parity  the executed feed's verdict on it: result executed (inputs equal? decision equal? the true index in range /
                in the window? ms between the shred sighting and the executed arrival) | dump_failed (the dump's tx FAILED:
                a phantom) | no_exec_dump | exec_only (an executed dump the shred path did not decide, and why)
  shred_unseen  a decided dump the executed feed never delivered
  fire          with "via": "shred" for the buys fired on shreds (live)
Reports: coverage (of the executed path's picks, how many the shred path decided as picks), parity (must be 0 differ),
phantoms (picks whose dump failed or never executed: each would be a cheap 6042 fail live), ms saved (shred sighting ->
executed arrival, p10/p50/p90, on picks), why the executed-only dumps were not decided, the index policy's coverage.
"""
import argparse, json, sys, collections


def pct(v, qs=(10, 50, 90)):
    v = sorted(x for x in v if x is not None)
    if not v: return None
    return [round(v[min(len(v) - 1, int(round((len(v) - 1) * q / 100)))], 2) for q in qs]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jsonl", nargs="+", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()
    dumps, par, unseen, fires = {}, [], [], []
    for p in a.jsonl:
        for line in open(p, errors="replace"):
            if '"shred' not in line and '"fire"' not in line: continue
            try: r = json.loads(line)
            except Exception: continue
            ev = r.get("ev")
            if ev == "shred_dump": dumps[r["sig"]] = r
            elif ev == "shred_parity": par.append(r)
            elif ev == "shred_unseen": unseen.append(r)
            elif ev == "fire" and r.get("via") == "shred": fires.append(r)
    ex = [r for r in par if r.get("result") == "executed"]
    what = collections.Counter(d.get("what", "?").split(":")[0] if not d.get("what", "").startswith("skip:") else d["what"] for d in dumps.values())
    exec_picks = [r for r in par if r.get("pick_exec")]
    shred_picks_ok = [r for r in ex if r.get("pick_exec") and r.get("decision_equal") is True]
    res = {
        "decided": len(dumps), "what": dict(what),
        "parity": {"executed": len(ex), "decision_equal": sum(1 for r in ex if r.get("decision_equal") is True), "decision_differ": sum(1 for r in ex if r.get("decision_equal") is False),
                   "decision_depends": sum(1 for r in ex if r.get("decision_equal") is None), "inputs_equal": sum(1 for r in ex if r.get("inputs_equal")),
                   "inputs_differ": sum(1 for r in ex if r.get("inputs_equal") is False), "fees_equal": sum(1 for r in ex if r.get("fees_equal")),
                   "idx_in_range": sum(1 for r in ex if r.get("idx_in_range")), "idx_out": sum(1 for r in ex if r.get("idx_in_range") is False),
                   "idx_in_window": sum(1 for r in ex if r.get("idx_in_window") is True), "idx_out_window": sum(1 for r in ex if r.get("idx_in_window") is False)},
        "coverage": {"exec_picks": len(exec_picks), "shred_picked_too": len(shred_picks_ok),
                     "exec_only_why": dict(collections.Counter(r.get("why") for r in par if r.get("result") == "exec_only" and r.get("pick_exec")))},
        "phantoms": {"dump_failed": sum(1 for r in par if r.get("result") == "dump_failed"), "dump_failed_picks": sum(1 for r in par if r.get("result") == "dump_failed" and r.get("pick_shred")),
                     "dump_failed_seller_short": sum(1 for r in par if r.get("result") == "dump_failed" and r.get("seller_short")),
                     "no_exec_dump": sum(1 for r in par if r.get("result") == "no_exec_dump"), "unseen": len(unseen)},
        "ms_shred_to_exec": {"picks": pct([r.get("ms_shred_to_exec_rx") for r in ex if r.get("pick_shred")]), "all_decided": pct([r.get("ms_shred_to_exec_rx") for r in ex])},
        "ms_decide": pct([d.get("ms_decide") for d in dumps.values()]),
        "fired_on_shreds": len(fires),
        "fire_decision_us": pct([f.get("decision_us") for f in fires]),
        "seller_short_picks": sum(1 for d in dumps.values() if d.get("what") == "skip:seller_short"),
    }
    print(json.dumps(res, indent=1))
    if a.json: json.dump(res, open(a.json, "w"), indent=1)
    if res["parity"]["decision_differ"]: print(f"WARNING: {res['parity']['decision_differ']} shred decisions differ from the executed ones: read their shred_parity records", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
