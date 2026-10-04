#!/usr/bin/env python3
"""Big attempts whose gap stayed open (taker came late or never): what did our gate / Jito say? A 'gap gone' sim on
a gap a rival took only 100+ ms later means our check looked at state without the trigger. usage: late.py <seg>..."""
import json, collections, sys
def jl(f):
    try:
        for l in open(f):
            try: yield json.loads(l)
            except Exception: pass
    except FileNotFoundError: return
tab = collections.defaultdict(collections.Counter); ex = []
for seg in sys.argv[1:]:
    d = f"/root/arb-lab/runs/{seg}"
    P = {p["id"]: p for p in jl(f"{d}/opportunities.jsonl")}
    O = {o["attempt"]: o for o in jl(f"{d}/outcomes.jsonl")}
    BU = {x.get("sig"): x for x in jl(f"{d}/bundles.jsonl")}
    for a in jl(f"{d}/attempts.jsonl"):
        if (a.get("size_lamports") or 0) < 5e8: continue
        p = P.get(a["opp"]) or {}; o = O.get(a["attempt"]) or {}
        t = p.get("taker") or {}
        w = t.get("window_ms")
        b = "no taker seen" if w is None else "taken <=20ms" if w <= 20 else "taken 20-60ms" if w <= 60 else "taken 60-150ms" if w <= 150 else "taken >150ms"
        se = o.get("settle_error") or ""
        bo = [BU[c["sig"]].get("outcome") for c in a.get("copies") or [] if c.get("sig") in BU]
        r = "WIN" if o.get("ok") else "landed-fail" if o.get("landed") else "sim gap gone" if se.startswith("sim_gated") else ("bundle " + bo[0]) if bo else "sent, no land"
        tab[b][r] += 1
        if b in ("taken >150ms", "no taker seen") and r == "sim gap gone" and len(ex) < 6:
            ex.append((seg, a["attempt"], a["buy_venue"], a["sell_venue"], round(a["size_lamports"] / 1e9, 2), a["expected_profit"], w, se[:150]))
for b in sorted(tab): print(f"{b:16}", dict(tab[b].most_common()))
for e in ex: print("  ", e)
