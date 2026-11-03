#!/usr/bin/env python3
"""PAPER AUDIT step 10 [MEASURED, read-only]: the LIVE regular (IMIT1 / M2) round trips of earlier runs, to check the regular paper
(regpaper.rs) cost and accounting. Per run: picks, fires, landed buys, buy_failed, realized (REALIZED lines), gross (sell SOL after pump's
fee - spend, from the close record), costs per trip = gross - realized, landing (ms / slots after the dump), hold, tips.
Also the paper records (regular_paper_*) of r36 / r37 for the same numbers.
usage: pa10_regular_live.py OUT.json RUN.jsonl[:RUN.log] ..."""
import sys, json, re, collections, statistics

RX_REAL = re.compile(r"REALIZED mint=(\S+) pnl=([-+]?[\d.]+) SOL source=(\S+)")
FR = 0.0125


def one(jl, lg):
    picks = fires = 0
    closes = []; lands = {}; realized = collections.defaultdict(list); m2 = None; spend = None; paper = []
    for line in open(jl, errors="replace"):
        if '"ev":"' not in line: continue
        if '"ev":"run_start"' in line:
            r = json.loads(line); m2 = (r.get("m2") or {}).get("model"); spend = r.get("spend"); continue
        if '"ev":"pick"' in line: picks += 1; continue
        if '"ev":"fire"' in line: fires += 1; continue
        if '"ev":"buy_land"' in line:
            r = json.loads(line); lands[r["mint"]] = r; continue
        if '"ev":"close"' in line:
            r = json.loads(line); closes.append(r); continue
        if '"ev":"regular_paper' in line: paper.append(json.loads(line))
    if lg:
        for line in open(lg, errors="replace"):
            m = RX_REAL.search(line)
            if m: realized[m.group(1)].append(float(m.group(2)))
    sold = [c for c in closes if c.get("result") == "sold"]
    failed = [c for c in closes if c.get("result") == "buy_failed"]
    rows = []
    for c in sold:
        g = (c.get("sol_out_curve") or 0) * (1 - FR) / 1e9 - c["spend"] / 1e9 if c.get("sol_out_curve") is not None else None
        rl = realized.get(c["mint"])
        r = rl.pop(0) if rl else None
        L = lands.get(c["mint"]) or {}
        rows.append({"mint": c["mint"], "spend": c["spend"] / 1e9, "gross": g, "realized": r, "tips": c.get("tips"), "sell_tips": [s[2] for s in (c.get("sell_sigs") or []) if s[1]],
                     "exit_why": c.get("exit_why"), "held_s": c.get("held_s"), "rx_ms_after_dump": L.get("rx_ms_after_dump"), "slots_after_dump": L.get("slots_after_dump"),
                     "buy_fee": L.get("fee"), "land": c.get("land"), "dump_slot": c.get("dump_slot"), "dump_idx": c.get("dump_idx"), "sell_land": c.get("sell_land")})
    have = [x for x in rows if x["gross"] is not None and x["realized"] is not None]
    cost = [x["gross"] - x["realized"] for x in have]
    out = {"m2": m2, "spend": spend, "picks": picks, "fires": fires, "sold": len(sold), "buy_failed": len(failed), "landed_share": len(sold) / max(1, len(sold) + len(failed)),
           "realized": sum(x["realized"] for x in have), "gross": sum(x["gross"] for x in have), "n_pnl": len(have),
           "gross_per_sol_mean_pct": 100 * statistics.mean(x["gross"] / x["spend"] for x in have) if have else None,
           "realized_per_sol_mean_pct": 100 * statistics.mean(x["realized"] / x["spend"] for x in have) if have else None,
           "cost_per_trip_mSOL_median": 1e3 * statistics.median(cost) if cost else None, "cost_per_trip_mSOL_mean": 1e3 * statistics.mean(cost) if cost else None,
           "buy_tips_mSOL": dict(collections.Counter(round((x["tips"] or 0) / 1e6, 2) for x in rows)), "sell_tips_mSOL": dict(collections.Counter(str(tuple(round(t / 1e6, 2) for t in x["sell_tips"])) for x in rows)),
           "rx_ms_after_dump_median": statistics.median([x["rx_ms_after_dump"] for x in rows if x["rx_ms_after_dump"] is not None]) if any(x["rx_ms_after_dump"] is not None for x in rows) else None,
           "slots_after_dump": dict(collections.Counter(x["slots_after_dump"] for x in rows)), "exit_why": dict(collections.Counter(x["exit_why"] for x in rows)),
           "held_s_median": statistics.median([x["held_s"] for x in rows if x["held_s"]]) if rows else None}
    if paper:
        ex = [p for p in paper if p["ev"] == "regular_paper_exit"]; fl = [p for p in paper if p["ev"] == "regular_paper_fill"]
        out["paper"] = {"picks": sum(1 for p in paper if p["ev"] == "regular_paper_pick"), "fills": sum(1 for p in fl if p["filled"]), "nofill": sum(1 for p in fl if not p["filled"]),
                        "exits": len(ex), "gross": sum(p["gross"] for p in ex) / 1e9, "net_exits": sum(p["net"] for p in ex) / 1e9,
                        "gross_per_sol_mean_pct": 100 * statistics.mean(p["gross"] / p["spend"] for p in ex) if ex else None,
                        "costs_per_trip_mSOL": statistics.mean((p["gross"] - p["net"]) / 1e6 for p in ex) if ex else None,
                        "ms_after_pick_median": statistics.median(p["ms_after_pick"] for p in fl) if fl else None,
                        "ms_held_median": statistics.median(p["ms_held"] for p in ex) if ex else None}
    return out, rows


if __name__ == "__main__":
    res = {}; allrows = {}
    for a in sys.argv[2:]:
        jl, lg = (a.split(":") + [None])[:2]
        name = jl.split("/")[-1].replace(".jsonl", "")
        o, rows = one(jl, lg); res[name] = o; allrows[name] = rows
        print(name, json.dumps(o, default=str)[:900])
    json.dump({"runs": res, "rows": allrows}, open(sys.argv[1], "w"), indent=1, default=str)
