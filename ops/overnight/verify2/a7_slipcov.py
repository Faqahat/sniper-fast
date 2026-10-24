#!/usr/bin/env python3
"""verify2 / a7: (1) coverage of decoded follower slippage limits in our hold windows; (2) do the decoded limits agree with
the chain outcome (each successful buy must satisfy its own limit at its real price)?; (3) graduation inside holds."""
import sys, os, json, gzip, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2core as V
P = V.load_picks(); L = V.load_launches(P); D, O = V.load_scores(P); X = V.load_x1()
SLIP, kinds = V.load_slip(); ENG = json.load(open(os.path.join(V.WORK, "a6_engine.json")))
slots = {int(k): v for k, v in json.load(gzip.open(os.path.join(V.WORK, "x1_slots.json.gz"), "rt")).items()}
lo, hi = min(slots), max(slots); EMPTY = {s for s in range(lo, hi + 1) if slots.get(s, 0) == 0}
cov = collections.Counter(); cov_sol = collections.Counter(); bad = []; grads = []
for Lm in (75, 45):
    for m in P:
        M = V.Mint(m, L[m], X.get(m, []), repair=True, empty_slots=EMPTY)
        seen, miss, how = V.match_anchors(M, V.parse_outs(O[m]["outs"])); ab = V.absorbed_units(M, ENG.get(m), seen)
        ins = V.place2(M, seen, Lm, "opt", ab); o = V.replay(M, ins, slip=SLIP)
        if not o.get("fill"): continue
        if o["grad"]: grads.append((Lm, m))
        for t in M.trades:
            if t["u"] <= ins or t["s"] >= o["sslot"] or not t["buy"] or t["syn"]: continue
            k = SLIP.get(t["sig"], {}).get("kind", "missing")
            cov[(Lm, k)] += 1; cov_sol[(Lm, k)] += t["sol"] / 1e9
print("follower buys inside our hold windows (fills), by decoded-limit kind:")
for Lm in (75, 45):
    n = sum(v for (l, k), v in cov.items() if l == Lm); s = sum(v for (l, k), v in cov_sol.items() if l == Lm)
    print(f"  L{Lm}: " + ", ".join(f"{k} {cov[(Lm, k)]} ({cov_sol[(Lm, k)]:.1f} SOL)" for k in ("sol", "tok", "unk", "nofetch", "noevent", "missing") if cov[(Lm, k)]) + f" | total {n} ({s:.1f} SOL)")
# chain consistency of the decoded limits (all decoded buys of the picks)
chk = collections.Counter()
for m in P:
    M = V.Mint(m, L[m], X.get(m, []), repair=False)
    prev = None
    for t in M.trades:
        lim = SLIP.get(t["sig"])
        if lim and t["buy"] and lim.get("kind") in ("sol", "tok") and lim.get("tok") == t["tok"]:
            if lim["kind"] == "sol": ok = t["tok"] >= lim["a2"] and lim["a1"] >= t["sol"]
            else: ok = lim["a1"] == t["tok"]
            chk["ok" if ok else "violated"] += 1
print("decoded limits vs the chain's own fills:", dict(chk))
print("fills whose replayed curve completed (graduated) inside the hold:", grads)
