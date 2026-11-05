#!/usr/bin/env python3
"""VERIFY step 1 (read-only): for one run, build every live position with the features the frozen QUIET3 and TAIL scorers use,
by calling the FROZEN COPIES' own functions (quiet3_score.positions / a_rule, tail_score.load / feats / known_t), and join the two
position lists. Also re-derives the run's realized total straight from presend_live_realized (independent parse).
usage: v_extract.py RUN_TAG RUN.presend.jsonl OUT.json"""
import sys, json, importlib.util, collections
FC = "/home/moiz/sniper/ops/strategies/presend/filters3/verify/frozen_copies"

def mod(p, n):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

q3 = mod(f"{FC}/quiet3/quiet3_score.py", "q3"); tl = mod(f"{FC}/tail/tail_score.py", "tl")
tag, fn, out = sys.argv[1], sys.argv[2], sys.argv[3]

# independent realized total
raw_sum, raw_n = 0, 0
for l in open(fn, errors="replace"):
    if '"ev":"presend_live_realized"' in l:
        d = json.loads(l); raw_sum += d["pnl"]; raw_n += 1

tpos, t0, t1 = tl.load(fn)
qpos = q3.positions(fn)
rows = []
for p in tpos:
    F = tl.feats(p)
    c = p["close"]
    spend = (c.get("spend") or (p["arm"].get("spend")) or 0) / 1e9
    rows.append({"run": tag, "w": p["w"], "mint": p["mint"], "kind": (F["kind"] or "t2").lower(), "t": p["t"], "ts": F["ts"],
                 "pnl": p["pnl"], "known_tl": tl.known_t(p), "creator_tl": F["creator"], "has_holders": F["has_holders"],
                 "sum_fresh": F.get("sum_fresh"), "sum_oth": F.get("sum_oth"), "spend": spend,
                 "fresh_holders": [h for h in (F.get("holders") or "").split()] if F.get("holders") else []})
# join quiet3 positions to tail positions: same mint + kind, nearest buy time
by = collections.defaultdict(list)
for i, r in enumerate(rows): by[(r["mint"], r["kind"])].append(i)
used = set(); unmatched_q = 0
for q in qpos:
    k = (q["mint"], q["kind"].lower())
    cand = [i for i in by.get(k, []) if i not in used]
    if not cand: unmatched_q += 1; continue
    i = min(cand, key=lambda i: abs(rows[i]["t"] - q["buy_t"]))
    used.add(i); r = rows[i]
    r.update({"q_t0": q["t0"], "q_buy_t": q["buy_t"], "q_known": q["known"], "q_pnl": q["pnl"], "followed": q["followed"],
              "creator_q": q["creator"], "n120": q["n120"], "whd": q["whd"], "rule_on": q["rule_on"], "A": q3.a_rule(q)})
json.dump({"tag": tag, "t0": t0, "t1": t1, "raw_realized_sol": raw_sum / 1e9, "raw_realized_n": raw_n, "tail_n": len(tpos),
           "tail_sum": sum(p["pnl"] for p in tpos), "q3_n": len(qpos), "q3_sum": sum(q["pnl"] for q in qpos),
           "unmatched_q3": unmatched_q, "unmatched_tail": sum(1 for r in rows if "q_t0" not in r),
           "pnl_mismatch": sum(1 for r in rows if "q_pnl" in r and abs(r["q_pnl"] - r["pnl"]) > 1e-9), "rows": rows}, open(out, "w"))
print(tag, "raw", raw_n, round(raw_sum / 1e9, 4), "tail", len(tpos), round(sum(p["pnl"] for p in tpos), 4), "q3", len(qpos),
      round(sum(q["pnl"] for q in qpos), 4), "unmatched q3/tail", unmatched_q, sum(1 for r in rows if "q_t0" not in r))
