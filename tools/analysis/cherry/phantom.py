#!/usr/bin/env python3
"""Big attempts nobody took (phantom gaps): which leg the simulation says is short, by venue and size; and the free
sims (sims.jsonl) at the same sizes. usage: phantom.py <seg>..."""
import json, collections, sys, re
def jl(f):
    try:
        for l in open(f):
            try: yield json.loads(l)
            except Exception: pass
    except FileNotFoundError: return
q = lambda v, p: round(sorted(v)[min(len(v) - 1, int(len(v) * p))]) if v else None
rx = re.compile(r"sim_gated .*? \| legs \[(\d+), (\d+)\] predicted \[(\d+), (\d+)\]")
rows = collections.defaultdict(lambda: {"n": 0, "l1": [], "l2": [], "pools": collections.Counter(), "exp": []})
for seg in sys.argv[1:]:
    d = f"/root/arb-lab/runs/{seg}"
    P = {p["id"]: p for p in jl(f"{d}/opportunities.jsonl")}
    O = {o["attempt"]: o for o in jl(f"{d}/outcomes.jsonl")}
    for a in jl(f"{d}/attempts.jsonl"):
        if (a.get("size_lamports") or 0) < 5e8: continue
        p = P.get(a["opp"]) or {}; o = O.get(a["attempt"]) or {}
        if p.get("taker"): continue
        m = rx.match(o.get("settle_error") or "")
        if not m: continue
        l1, l2, mid, back = map(int, m.groups())
        k = (a["buy_venue"], a["sell_venue"])
        r = rows[k]; r["n"] += 1; r["exp"].append(a["expected_profit"] / 1e6)
        r["l1"].append((l1 - mid) / mid * 1e4 if mid else 0)
        r["l2"].append(((l2 / l1) / (back / mid) - 1) * 1e4 if l1 and mid and back else 0)
        r["pools"][(a["buy_pool"][:6], a["sell_pool"][:6], a["mint"][:6])] += 1
for k, r in sorted(rows.items(), key=lambda x: -x[1]["n"]):
    print(k, "n", r["n"], "expected (M lamports) p50", q(r["exp"], .5), "| leg1 bps p10/50/90", q(r["l1"], .1), q(r["l1"], .5), q(r["l1"], .9), "| leg2 bps", q(r["l2"], .1), q(r["l2"], .5), q(r["l2"], .9))
    print("     top pool pairs:", r["pools"].most_common(4))
