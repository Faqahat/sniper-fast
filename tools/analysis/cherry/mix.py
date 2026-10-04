#!/usr/bin/env python3
"""Why USDC? Per segment: attempts and outcomes by token class (USDC vs memecoin) and arm; implausible gaps by pair;
per-trade economics of USDC trades. usage: mix.py <seg>..."""
import json, collections, sys, os
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
cls = lambda m: "USDC" if m == USDC else "meme"
q = lambda v, p: sorted(v)[min(len(v) - 1, int(len(v) * p))] if v else None
for seg in sys.argv[1:]:
    d = f"/root/arb-lab/runs/{seg}"
    A = [json.loads(l) for l in open(f"{d}/attempts.jsonl")]
    O = {x["attempt"]: x for x in map(json.loads, open(f"{d}/outcomes.jsonl"))}
    print(f"== {seg}: {len(A)} attempts")
    res = collections.defaultdict(collections.Counter)
    exp = collections.defaultdict(list)
    for a in A:
        o = O.get(a["attempt"]) or {}
        se = o.get("settle_error") or ""
        r = ("WIN" if o.get("landed") and (o.get("ok") or (o.get("gate") or {}).get("ok")) else
             "landed-fail" if o.get("landed") else "sim-gated" if se.startswith("sim_gated") else
             "pending" if not o else "not-landed")
        k = (cls(a["mint"]), a.get("path_arm") or "-")
        res[k][r] += 1
        exp[cls(a["mint"])].append(a.get("expected_profit") or 0)
    for k, v in sorted(res.items()): print("  ", k, dict(v))
    for c, v in exp.items(): print(f"   expected profit {c}: n={len(v)} p50={q(v,.5)} p90={q(v,.9)} max={max(v)}")
    # one outcome record that landed, to see its fields
    L = [o for o in O.values() if o.get("landed")]
    for o in L[:1]: print("   landed sample keys:", sorted(o.keys()))
