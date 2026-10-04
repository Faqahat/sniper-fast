#!/usr/bin/env python3
"""Big attempts (size >= 0.5 SOL): who took the gap and how many ms after the trigger arrived, vs when we decided,
simulated and sent. usage: taken.py <seg>..."""
import json, collections, sys, re
def jl(f):
    try:
        for l in open(f):
            try: yield json.loads(l)
            except Exception: pass
    except FileNotFoundError: return
q = lambda v, p: round(sorted(v)[min(len(v) - 1, int(len(v) * p))], 1) if v else None
tk, dec, sim, ex, sent = [], [], [], [], []
kinds = collections.Counter()
for seg in sys.argv[1:]:
    d = f"/root/arb-lab/runs/{seg}"
    P = {p["id"]: p for p in jl(f"{d}/opportunities.jsonl")}
    O = {o["attempt"]: o for o in jl(f"{d}/outcomes.jsonl")}
    for a in jl(f"{d}/attempts.jsonl"):
        if (a.get("size_lamports") or 0) < 5e8: continue
        p = P.get(a["opp"]) or {}; o = O.get(a["attempt"]) or {}
        t0 = min((p.get("arrivals") or {}).values() or [0])
        if not t0: continue
        t = p.get("taker") or {}
        dec.append(((p.get("st") or {}).get("decided", t0) - t0) / 1e6)
        pass
        ms = t.get("window_ms") if isinstance(t, dict) else None
        cs = [c.get("t_sent") for c in (o.get("copies") or []) if c.get("t_sent")]
        if cs: sent.append((min(cs) - t0) / 1e6)
        if ms is not None: tk.append(ms)
        kinds["taker known" if t else "no taker recorded"] += 1
        if t and len(ex) < 3: ex.append(t)
print("big attempts:", dict(kinds))
print("ms after trigger arrival: we decided p50", q(dec, .5), "| our first send p50", q(sent, .5), "p10", q(sent, .1), "p90", q(sent, .9), "n", len(sent))
print("taker ms after trigger: n", len(tk), "p10", q(tk, .1), "p25", q(tk, .25), "p50", q(tk, .5), "p75", q(tk, .75), "p90", q(tk, .9))
print("share taken within 20 ms:", round(sum(1 for x in tk if x <= 20) / max(1, len(tk)), 2), " within 50:", round(sum(1 for x in tk if x <= 50) / max(1, len(tk)), 2), " after 150:", round(sum(1 for x in tk if x > 150) / max(1, len(tk)), 2))
for e in ex: print("sample taker:", json.dumps(e)[:300])
