#!/usr/bin/env python3
"""High-value trades: opportunities and attempts by trade size band, what happened to each, expected profit at stake.
usage: bands.py <seg>..."""
import json, collections, sys, re
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
def jl(f):
    try:
        for l in open(f):
            try: yield json.loads(l)
            except Exception: pass
    except FileNotFoundError: return
def band(sz):
    s = sz / 1e9
    return "a <0.1" if s < 0.1 else "b 0.1-0.5" if s < 0.5 else "c 0.5-2.1" if s < 2.1 else "d 2.1-4.2"
opp_n = collections.Counter(); opp_exp = collections.Counter(); att = collections.defaultdict(collections.Counter); att_exp = collections.defaultdict(int)
mins = 0
for seg in sys.argv[1:]:
    d = f"/root/arb-lab/runs/{seg}"
    st = list(jl(f"{d}/status.jsonl")); mins += (st[-1]["t_ns"] - st[0]["t_ns"]) / 6e10 if len(st) > 1 else 0
    P = {p["id"]: p for p in jl(f"{d}/opportunities.jsonl")}
    for p in P.values():
        b = band(p.get("size_lamports") or 0); opp_n[b] += 1; opp_exp[b] += max(0, p.get("net_lamports") or 0)
    A = {a["attempt"]: a for a in jl(f"{d}/attempts.jsonl")}
    BU = {}
    for x in jl(f"{d}/bundles.jsonl"): BU[x.get("sig")] = x.get("outcome")
    for o in jl(f"{d}/outcomes.jsonl"):
        a = A.get(o["attempt"])
        if not a: continue
        b = band(a.get("size_lamports") or 0)
        se = o.get("settle_error") or ""
        bo = [BU.get(c.get("sig")) for c in a.get("copies") or [] if BU.get(c.get("sig"))]
        r = ("WIN" if o.get("ok") else "landed-fail" if o.get("landed") else "sim: gap gone" if "0x4e580002" in se and se.startswith("sim_gated")
             else "sim: other" if se.startswith("sim_gated") else ("bundle: " + bo[0]) if bo else "sent, not landed")
        att[b][r] += 1; att_exp[b] += max(0, a.get("expected_profit") or 0)
print(f"{mins:.0f} min of trading")
for b in sorted(opp_n):
    print(f"{b:10} opportunities {opp_n[b]:5}  expected net {opp_exp[b]/1e9:8.3f} SOL ({opp_exp[b]/1e9/max(mins,1)*60:6.2f} SOL/h)  |  attempts {sum(att[b].values()):4}  expected {att_exp[b]/1e9:7.3f} SOL  {dict(att[b].most_common())}")
