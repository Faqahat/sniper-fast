#!/usr/bin/env python3
"""Sim-gated memecoin vs USDC attempts: which leg was off and by how much, by venue pair; the error codes.
usage: gated.py <seg>..."""
import json, collections, sys, re
def jl(f):
    for l in open(f):
        try: yield json.loads(l)
        except Exception: pass
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
q = lambda v, p: round(sorted(v)[min(len(v) - 1, int(len(v) * p))], 1) if v else None
rx = re.compile(r"sim_gated after ([\d.]+) ms: (.*?) \| legs \[(\d+), (\d+)\] predicted \[(\d+), (\d+)\]")
rows = collections.defaultdict(lambda: {"n": 0, "l1": [], "l2": [], "err": collections.Counter(), "trig": collections.Counter()})
other = collections.Counter()
for seg in sys.argv[1:]:
    d = f"/root/arb-lab/runs/{seg}"
    A = {a["attempt"]: a for a in jl(f"{d}/attempts.jsonl")}
    P = {p["id"]: p for p in jl(f"{d}/opportunities.jsonl")}
    for o in jl(f"{d}/outcomes.jsonl"):
        se = o.get("settle_error") or ""
        if not se.startswith("sim_gated"): continue
        a = A.get(o["attempt"]) or {}
        p = P.get(a.get("opp")) or {}
        c = "USDC" if a.get("mint") == USDC else "meme"
        m = rx.match(se)
        if not m: other[(c, se[:90])] += 1; continue
        ms, why, l1, l2, mid, back = m.groups(); l1, l2, mid, back = map(int, (l1, l2, mid, back))
        k = (c, a.get("buy_venue"), a.get("sell_venue"))
        r = rows[k]; r["n"] += 1; r["err"][why[:40]] += 1
        r["trig"]["state" if p.get("trigger_feed") == "state" else "decoded"] += 1
        if mid: r["l1"].append((l1 - mid) / mid * 1e4)
        if l1 and mid and back: r["l2"].append(((l2 / l1) / (back / mid) - 1) * 1e4)
for k, r in sorted(rows.items(), key=lambda x: -x[1]["n"]):
    print(k, "n", r["n"], "| leg1 bps p10/50/90", q(r["l1"], .1), q(r["l1"], .5), q(r["l1"], .9),
          "| leg2 rate bps", q(r["l2"], .1), q(r["l2"], .5), q(r["l2"], .9), "|", dict(r["trig"]), r["err"].most_common(3))
for k, v in other.most_common(12): print("other:", v, k)
