#!/usr/bin/env python3
"""BIGLOSS b3: per-position features at the FILLED ATTEMPT'S SIGNING (causal point; the engine can stop sending there) +
outcome labels (hold sellers) used ONLY to update causal ledgers after the position closes.
Signing holders = landing list (>= ~2%) with: sells after signing put back (crossing dump + between), buys after signing
removed (holders whose first buy is after the signing slot dropped; 'between' buys subtracted). APPROX: buys in slots between
the signing slot and the fill slot by wallets that already held are not removed (unknown).
Out: /home/moiz/sniper-data/bigloss/feats.jsonl"""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/bigloss")
from blib import *


def restore2(at, L):
    add = collections.defaultdict(float); sub = collections.defaultdict(float)
    V, K = float(at.get("vsol") or 0), float(at.get("vtok") or 0)
    xs = [x for x in [L.get("d")] + list(L.get("between") or []) if x]
    xs.sort(key=lambda x: (x.get("slot", 0), x.get("idx", 0)))
    for x in xs:
        s = float(x.get("sol") or 0); u = (x.get("user") or "")[:8]
        if V <= 0 or K <= 0: break
        if x.get("buy"):
            K2 = V * K / (V + s); sub[u] += (K - K2) / SUP * 100.0; V, K = V + s, K2
        elif s < V:
            K2 = V * K / (V - s); add[u] += (K2 - K) / SUP * 100.0; V, K = V - s, K2
    return add, sub


def sign_holders2(d):
    f = d["fill"]; fa = f.get("ann") or {}
    if fa.get("holders") is None: return None
    at = d.get("att") or {}; L = d.get("land") or {}
    gap = f["slot"] - ((at.get("pos") or [f["slot"]])[0])
    add, sub = restore2(at, L)
    hs = []
    for h in fa["holders"]:
        w8 = h["w"][:8]
        if w8 in OURS8: continue
        if h.get("age") is not None and h["age"] < gap: add.pop(w8, None); continue  # first buy after signing slot
        pct = h["pct"] + add.pop(w8, 0.0) - sub.get(w8, 0.0)
        if pct < 1.5: continue
        hs.append({"w": w8, "pct": pct, "age": (h.get("age") or 0) - gap, "n": h.get("n") or 0, "hz3": h.get("hz3") or 0.0,
                   "p50": h.get("p50") or 0, "risk": h.get("risk") or 0, "gone": False})
    for w8, pct in add.items():
        if pct >= 2.0 and w8 not in OURS8:
            hs.append({"w": w8, "pct": pct, "age": None, "n": None, "hz3": 0.0, "p50": 0, "risk": 0, "gone": True})
    return hs


P = load()
with open(f"{D}/feats.jsonl", "w") as o:
    for d in P:
        a = d.get("arm") or {}; f = d["fill"]; at = d.get("att") or {}; c = d.get("close") or {}
        src = (a.get("trig") if d["kind"] == "t2" else a.get("dump")) or {}
        wh = whale_of(d)
        cr = ((a.get("ann") or {}).get("creator") or "")[:8]
        hs = sign_holders2(d)
        sign_slot = (at.get("pos") or [f["slot"]])[0]
        tok_age_sign = (src.get("age_slots") + (sign_slot - src["slot"])) if src.get("age_slots") is not None and src.get("slot") else None
        F = {"run": d["run"], "rk": d["rk"], "set": d["set"], "mint": d["mint"], "w": d["w"], "kind": d["kind"], "pnl": d["pnl"],
             "sol_in": f.get("sol_in", 0) / 1e9, "t_arm": d.get("t_arm") or at.get("t") or d["t"], "t_sign": at.get("t") or d["t"],
             "t_fill": d["t"], "t_close": (c.get("sell_land") or [0, 0, 0])[2] or (d["t"] + int(1e9)),
             "whale": wh, "creator": cr, "w_pct": src.get("pct"), "age_arm": src.get("age_slots"), "tok_age_sign": tok_age_sign,
             "cr_pct": (a.get("ann") or {}).get("cr_pct"), "nb50": (a.get("ann") or {}).get("nb50"),
             "hour": hour_pkt(d["t"]), "client": f.get("client"), "has_h": hs is not None,
             "eqgrp": bool((f.get("eqgrp") or {}).get("flag")), "fam": (d.get("fam") or {}).get("fam"),
             "cs_pct": (d.get("fam") or {}).get("cs_pct"),
             "arm_holders": [x["w"][:8] for x in (a.get("holders") or [])]}
        if hs is not None:
            oth = [h for h in hs if h["w"] != wh]
            whh = [h for h in hs if h["w"] == wh]
            F["holders"] = [[h["w"], round(h["pct"], 3), h["age"], h["n"]] for h in hs]
            F["whale_sign"] = whh[0]["pct"] if whh else 0.0
            F["sum_oth"] = sum(h["pct"] for h in oth); F["n_oth"] = len(oth)
            F["max_oth"] = max([h["pct"] for h in oth], default=0.0)
            ta = tok_age_sign
            F["ls_sum"] = sum(h["pct"] for h in oth if ta is not None and h["age"] is not None and h["age"] >= ta - 1)
            F["fresh_sum"] = sum(h["pct"] for h in oth if h["n"] is not None and h["n"] <= 1)
            F["bot_sum"] = sum(h["pct"] for h in oth if h["n"] is not None and h["n"] >= 10)
            F["cr_sign"] = sum(h["pct"] for h in hs if h["w"] == cr)
        s, b = hold_sellers(d)
        F["sellers"] = {w: round(v, 4) for w, v in s.items() if v >= 0.2}
        F["buy_hold"] = round(sum(b.values()), 4)
        o.write(json.dumps(F) + "\n")
print("rows", len(P))
