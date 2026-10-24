#!/usr/bin/env python3
"""verify2 / v5 (INFERRED sensitivity): ~70% of follower buys inside the 8 s holds have no fetched slippage limit (the fetch list
slip_sigs_10.json stops 10 slots after our buy) and the claim treats them as always filling. Here each of them gets a limit
drawn from the empirical slack distribution of decoded limits (picks' followers, 6-10 slots after the create; a8_slack.py),
deterministically by signature hash, applied as a min-tokens-out limit."""
import sys, os, json, gzip, hashlib, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2core as V
P = V.load_picks(); L = V.load_launches(P); D, O = V.load_scores(P); X = V.load_x1()
SLIP, kinds = V.load_slip(); PRO, SNIPER = V.load_wallet_sets(); ENG = json.load(open(os.path.join(V.WORK, "a6_engine.json")))
CLAIM = {r["m"]: r for r in json.load(open("/home/moiz/sniper/ops/overnight/core/final2_picks_v3_become_B0.5_tu.json"))}
slots = {int(k): v for k, v in json.load(gzip.open(os.path.join(V.WORK, "x1_slots.json.gz"), "rt")).items()}
lo, hi = min(slots), max(slots); EMPTY = {s for s in range(lo, hi + 1) if slots.get(s, 0) == 0}
rows = json.load(open(os.path.join(V.WORK, "a8_slack.json")))["rows"]
DIST = {k: sorted(s for d, s, _ in rows if lo_ <= d <= hi_) for k, (lo_, hi_) in dict(late=(6, 10), all=(0, 10**6), early=(0, 1)).items()}
def imputed(M, salt, dist):
    out = dict(SLIP)
    for t in M.trades:
        if not t["buy"] or t["syn"] or t["sig"] in SLIP: continue
        h = int(hashlib.sha256((salt + t["sig"]).encode()).hexdigest()[:8], 16) / 2**32
        sl = dist[min(len(dist) - 1, int(h * len(dist)))]
        out[t["sig"]] = dict(kind="sol", a1=t["sol"], a2=int(t["tok"] / (1 + sl)))
    return out
picks = [m for m in P if m in CLAIM]
for Lm in (75, 45):
    for dname in ("late", "all"):
        for var, drop in (("slip", None), ("proafter_slip", PRO), ("nosnip_slip", SNIPER | PRO)):
            tots = []
            for salt in ("a", "b", "c"):
                tot = 0.0
                for m in picks:
                    M = V.Mint(m, L[m], X.get(m, []), repair=True, empty_slots=EMPTY)
                    seen, miss, how = V.match_anchors(M, V.parse_outs(O[m]["outs"])); ab = V.absorbed_units(M, ENG.get(m), seen)
                    ins = V.place2(M, seen, Lm, "opt", ab)
                    o = V.replay(M, ins, slip=imputed(M, salt, DIST[dname]), drop_buy=drop)
                    if o.get("fill") is not None: tot += o["pnl"]
                tots.append(tot)
            print(f"  L{Lm} slack-dist {dname:4s} {var:14s} imputed-limit totals (3 draws): " + " ".join(f"{x:+.3f}" for x in tots))
