#!/usr/bin/env python3
# READ-ONLY. Forward test of the off-chain X/Twitter signal on the overnight run: metadata + X data fetched AT LAUNCH TIME by
# meta_watch.py (likes/views/followers as they were within ~1-3 s of the create), joined with the on-chain outcome.
# Reports latency, and race rate / 4yFAz overlap / realistic return (sell +1 s, 2 SOL) by X feature.
import sys, json, math, statistics as st, collections
sys.path.insert(0, "/root/race")
from fwdrows import build
from hc_search import sim, stats, fmt, hostbad

F = {o["mint"]: o for o in build("/root/race/paper_night.log", "/root/race/night_onchain.jsonl", "/root/race/paths_night.jsonl", verbose=False)
     if not hostbad(o["uri_host"]) and 0.5 <= o["dev_sol"] <= 8}
M = {}
for l in open("/root/race/meta_night.jsonl"):
    try:
        r = json.loads(l)
        M[r["mint"]] = r
    except Exception:
        pass
rows = [(F[m], M[m]) for m in F if m in M]
q = lambda v, p: sorted(v)[int(p * (len(v) - 1))] if v else float("nan")
print(f"launches with outcome and a launch-time metadata fetch: {len(rows)}")
okm = [m for _, m in rows if m.get("meta")]
tw = [m for _, m in rows if m.get("tw_ok")]
print(f"latency: metadata ok {len(okm)} p50 {q([m['meta_ms'] for m in okm], .5):.0f} ms p90 {q([m['meta_ms'] for m in okm], .9):.0f} | "
      f"with X data {len(tw)}: total p50 {q([m['total_ms'] for m in tw], .5):.0f} ms p90 {q([m['total_ms'] for m in tw], .9):.0f} | "
      f"share of X lookups done within 300 ms: {sum(m['total_ms'] <= 300 for m in tw) / max(1, len(tw)):.0%}")
RACE = lambda o: o["out2s_nx"] >= 3 and o["out2s_solx"] >= 3
G = {"all with metadata": lambda o, m: bool(m.get("meta")),
     "no X link": lambda o, m: m.get("tw_kind") in ("none", None) and bool(m.get("meta")),
     "X status link": lambda o, m: m.get("tw_kind") == "status",
     "X profile link": lambda o, m: m.get("tw_kind") == "profile",
     "tweet deleted/unavailable": lambda o, m: m.get("tw_kind") == "status" and not m.get("tw_ok"),
     "author >= 1k followers": lambda o, m: (m.get("followers") or 0) >= 1000,
     "author >= 10k followers": lambda o, m: (m.get("followers") or 0) >= 10000,
     "verified author": lambda o, m: bool(m.get("verified")),
     "tweet >= 10 likes at launch": lambda o, m: (m.get("likes") or 0) >= 10,
     "tweet >= 1k views at launch": lambda o, m: (m.get("views") or 0) >= 1000,
     "tweet < 5 min old": lambda o, m: m.get("tw_ts") and o.get("bt") and 0 <= o["bt"] - m["tw_ts"] < 300}
print(f"\n{'X feature':30} {'n':>5} | race | 4yFAz | Gate-B fired | sell +1 s realistic")
for nm, f in G.items():
    g = [o for o, m in rows if f(o, m)]
    if not g:
        continue
    s = stats([sim(o, dict(legs=[], T=1000)) for o in g])
    print(f"{nm:30} {len(g):5} | {sum(RACE(o) for o in g) / len(g):4.0%} | {sum(o['his'] for o in g):5} | {sum(o['fired'] for o in g):5} | {fmt(s)}")
