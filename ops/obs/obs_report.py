#!/usr/bin/env python3
"""obs_report.py — summarize a dip24 OBSERVATORY file (<run>.obs.jsonl), per module. Read-only; works on a growing file (an incomplete
last line is skipped) and over rotated parts (<file>.1, .2, ... are read first, oldest first, then the current file).

usage: obs_report.py /root/prod/runs/dip_ams_r36.obs.jsonl [--since-h H] [--json]
  --since-h H   only records of the last H hours (by the file's own data clock)
  --json        one JSON object instead of text
Sections: re-arm (windows, fills by row, paper P&L by size x exit, R2 / R5 subsets, refused tries), hold tapes (second sellers vs our
decision), watch wallets (activity, CU-price codes, failed txs), migration (v100 / v105 / complete / migrate seen times), blink (trigger
counts, seen lag in slot), backrun census (sells, who backruns first, value by hold), selection census (per class: dumps, paper P&L),
feed race (per feed wins / lead), inslot (fill rate and net P&L by landing delay x hold x size), observatory health (drops, timing, memory)."""
import sys, os, json, glob, statistics as st, collections

def parts(path):
    rot = sorted((p for p in glob.glob(path + ".*") if p[len(path) + 1:].isdigit()), key=lambda p: int(p[len(path) + 1:]))
    return rot + ([path] if os.path.exists(path) else [])

def records(path):
    for p in parts(path):
        with open(p, "rb") as f:
            for line in f:
                if not line.endswith(b"\n"): break          # growing file: the last line is still being written
                try: yield json.loads(line)
                except Exception: continue

def q(v, p):
    v = sorted(x for x in v if x is not None)
    return v[min(len(v) - 1, int(round((len(v) - 1) * p)))] if v else None

def main():
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit(1)
    path = a[0]; since = float(a[a.index("--since-h") + 1]) if "--since-h" in a else None; as_json = "--json" in a
    recs = list(records(path))
    if since:
        tmax = max((r.get("t") or r.get("t_rx") or 0) for r in recs if isinstance(r.get("t") or r.get("t_rx"), int)) if recs else 0
        lo = tmax - since * 3.6e12
        recs = [r for r in recs if not isinstance(r.get("t") or r.get("t_rx"), int) or (r.get("t") or r.get("t_rx")) >= lo or r["ev"].startswith("obs_")]
    by = collections.defaultdict(list)
    for r in recs: by[r.get("ev")].append(r)
    out = {"file": path, "parts": parts(path), "records": {k: len(v) for k, v in sorted(by.items())}}
    # ---- re-arm
    W = by["rearm_window"]
    if W or by["rearm_cand"]:
        cands = collections.Counter(r.get("verdict") for r in by["rearm_cand"])
        ends = collections.Counter(w["end"]["why"] for w in W)
        fills = {row: sum(1 for w in W if (w["rows"].get(row) or {}).get("fill")) for row in "abc"}
        pnl = collections.defaultdict(list)
        for w in W:
            f = (w["rows"].get("c") or {}).get("fill")
            if not f: continue
            for size, ex in f["px"].items():
                for pol, v in ex.items():
                    pnl[(size, pol, "all")].append(v)
                    if f.get("r2"): pnl[(size, pol, "r2")].append(v)
                    if not w.get("r5_skip"): pnl[(size, pol, "r5")].append(v)
        tab = {f"{s} {p} {sub}": {"n": len(v), "sum_msol": round(sum(v), 1), "mean": round(st.mean(v), 2), "win": round(sum(1 for x in v if x > 0) / len(v), 3)} for (s, p, sub), v in sorted(pnl.items())}
        tries = sum(w["tries"]["n"] for w in W); refused = sum(w["tries"]["refused"] for w in W)
        second = [w["rows"]["c"]["fill"]["second"] for w in W if (w["rows"].get("c") or {}).get("fill") and w["rows"]["c"]["fill"].get("second")]
        out["rearm"] = {"candidates": dict(cands), "windows": len(W), "ends": dict(ends), "fills_by_row": fills, "tries": tries, "refused": refused,
                        "refused_share": round(refused / tries, 4) if tries else None, "r5_skip_windows": sum(1 for w in W if w.get("r5_skip")),
                        "second_seller_row_c": {"n": len(second), "before_200ms": sum(1 for s in second if s.get("before_200ms"))}, "paper_row_c": tab}
    # ---- hold tapes
    H = by["hold_tape"]
    if H:
        s1 = [h["first_1sol_sell"] for h in H if h.get("first_1sol_sell")]
        sb = [h["first_big_sell"] for h in H if h.get("first_big_sell")]
        pnl = [h["close"].get("curve_pnl") for h in H if h.get("close") and h["close"].get("curve_pnl") is not None]
        out["hold"] = {"tapes": len(H), "with_1sol_sell": len(s1), "1sol_seen_before_decision": sum(1 for x in s1 if x.get("seen_before_decision")),
                       "1sol_ms_before_decision_p50": q([x.get("ms_before_decision") for x in s1 if x.get("seen_before_decision")], 0.5),
                       "with_big_sell": len(sb), "big_seen_before_decision": sum(1 for x in sb if x.get("seen_before_decision")),
                       "curve_pnl_sum_sol": round(sum(pnl) / 1e9, 4) if pnl else None,
                       "pnl_when_1sol_before_decision_sol": round(sum(h["close"]["curve_pnl"] for h in H if h.get("close") and h["close"].get("curve_pnl") is not None
                           and (h.get("first_1sol_sell") or {}).get("seen_before_decision")) / 1e9, 4)}
    # ---- watch
    if by["watch_trade"] or by["watch_fail"]:
        per = collections.defaultdict(lambda: collections.Counter())
        codes = collections.defaultdict(collections.Counter)
        for r in by["watch_trade"]:
            k = r.get("name") or r["w"][:8]; per[k]["buys" if r["buy"] else "sells"] += 1; per[k]["sol"] += r["sol"] / 1e9
            if r.get("cu_mod1000") is not None: codes[k][r["cu_mod1000"]] += 1
        for r in by["watch_fail"]: per[r.get("name") or r["w"][:8]]["fails"] += 1
        for r in by["watch_fail_agg"]: per[r.get("name") or r["w"][:8]]["fails"] += r["total"] - r["written"]
        out["watch"] = {k: {**{x: round(y, 2) for x, y in v.items()}, "top_cu_mod1000": codes[k].most_common(3)} for k, v in sorted(per.items(), key=lambda kv: -sum(kv[1].values()))}
    # ---- migration
    if by["mig_v100"] or by["mig_complete"]:
        out["migration"] = {"v100": len(by["mig_v100"]), "v105": len(by["mig_v105"]), "v105_sells": sum(1 for r in by["mig_v105"] if not r["buy"]),
                            "completes": len(by["mig_complete"]), "migrations_seen": len(by["mig_migrate"]), "pool_txs_seen": len(by["mig_pool_tx"]),
                            "complete_ms_after_v105_p50": q([r.get("ms_after_v105") for r in by["mig_complete"]], 0.5),
                            "migrate_ms_after_complete_p50": q([r.get("ms_after_complete") for r in by["mig_migrate"]], 0.5),
                            "v105_completed_within_10s": sum(1 for r in by["mig_follow"] if r["kind"] == "v105" and r.get("completed_ms") is not None and r["completed_ms"] <= 10000)}
    # ---- blink
    B = by["blink_trigger"]
    if B:
        out["blink"] = {"triggers": len(B), "by_class": dict(collections.Counter({3: "dev", 2: "bundler", 1: "early"}[r["cls"]] for r in B)),
                        "in_create_slot": sum(1 for r in B if r["in_create_slot"]), "age_ms_p50": q([r.get("age_ms") for r in B], 0.5),
                        "seen_lag_in_slot_ms_p50": q([r.get("seen_lag_in_slot_ms") for r in B], 0.5), "seen_lag_in_slot_ms_p90": q([r.get("seen_lag_in_slot_ms") for r in B], 0.9)}
    # ---- backrun census
    R = by["backrun_sell"]
    if R:
        first = collections.Counter(r["first"]["w"] for r in R if r.get("first"))
        vals = {h: [r["v_br"][k] for r in R if r.get("first") and r["v_br"][k] is not None] for k, h in enumerate([1, 2, 5, 9, 31])}
        vsell = {h: [r["v_sell"][k] for r in R if r["v_sell"][k] is not None] for k, h in enumerate([1, 2, 5, 9, 31])}
        out["backrun"] = {"sells": len(R), "with_backrunner": sum(1 for r in R if r.get("first")), "same_slot_first": sum(1 for r in R if r.get("first") and r["first"]["ds"] == 0),
                          "top_first_backrunners": first.most_common(10),
                          "value_after_first_br_mean": {h: round(st.mean(v), 4) for h, v in vals.items() if v},
                          "value_as_first_br_mean": {h: round(st.mean(v), 4) for h, v in vsell.items() if v},
                          "pro_buyers": sum(1 for r in R for b in r["buys"] if b.get("pro")), "armable_live": sum(1 for r in R if (r.get("armable") or {}).get("live"))}
    # ---- selection census
    S = by["select_cand"]
    if S:
        cls = collections.defaultdict(lambda: collections.Counter())
        for r in S:
            c = cls[r["class"]]; c["n"] += 1; c["live_arms"] += r["live_arms"]
            o = r.get("outcome") or {}
            if o.get("dump"):
                g = o["dump"]["slot_gap"]
                for w in (10, 20, 30): c[f"dump_{w}"] += g <= w
                if o.get("paper_065_msol") is not None: c["paper_fills"] += 1; c["paper_msol"] += o["paper_065_msol"]
        out["select"] = {k: dict(v) for k, v in cls.items()}
    # ---- feed race
    sums = [r for r in by["obs_summary"] if r.get("race")]
    if sums: out["race"] = sums[-1]["race"]
    # ---- inslot (8yYMhu's same-slot backrun, our paper): the last 10-min summary (cumulative)
    isum = [r for r in by["obs_summary"] if r.get("inslot")]
    if isum: out["inslot"] = isum[-1]["inslot"]
    # ---- health
    stt = by["obs_status"]
    if stt:
        last = stt[-1]
        out["health"] = {"sent": last.get("sent"), "dropped": last.get("dropped"), "timing": last.get("timing"), "mem_mb_est": last.get("mem_mb_est"), "write_errors": last.get("write_errors"),
                         "parts": last.get("part")}
    if as_json: print(json.dumps(out, indent=1)); return
    for k, v in out.items():
        print(f"== {k}")
        print(json.dumps(v, indent=1) if not isinstance(v, (str, int)) else v)

if __name__ == "__main__":
    main()
