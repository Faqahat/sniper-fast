#!/usr/bin/env python3
"""TAIL t4: candidate guards on real live fills. A blocked trade saves exactly its realized P&L (proof rule 3).
Per guard: per run-part (r39 r40 r41 r42a = DEV with holders; r37 r38 = DEV without holders; r42b = VAL): blocked n, saved SOL;
totals DEV / VAL: saved, SOL/day, blocked winners (n, SOL), blocked losers, saved without the guard's 5 best saves.
Ledgers (repeat dumpers / whales / creators) are built chronologically from earlier positions' tapes only (closed before signing)."""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/tail")
from tlib import *; from tfeat import feats, outcome
HOURS = {"r37": 18.4, "r38": 1.6, "r39": 3.1, "r40": 17.3, "r41": 1.3, "r42a": 32.13, "r42b": 20.58}
P = load()
# ---- chronological ledgers: events (t_known, kind, key, value)
ev = []
for d in P:
    sells, _ = outcome(d, OURS)
    c = d.get("close") or {}
    tk = (c.get("sell_land") or [None, None, None])[2] or d["t"] + 2_000_000_000
    tk += 2_000_000_000  # realized lookup lag margin
    for u, s in sells.items():
        if s >= 0.5: ev.append((tk, "dump", u[:8], (d["pnl"], s)))
    F = feats(d)
    if F.get("whale"): ev.append((tk, "whale", F["whale"][:8], d["pnl"]))
    if F.get("creator"): ev.append((tk, "creator", F["creator"][:8], d["pnl"]))
    ev.append((tk, "loss", None, d["pnl"]))
ev.sort(key=lambda x: x[0])
rows = []
L = {"dump": collections.defaultdict(list), "whale": collections.defaultdict(list), "creator": collections.defaultdict(list)}
losses = []
j = 0
for d in P:
    ts = (d.get("att") or {}).get("t") or d["t"]
    while j < len(ev) and ev[j][0] <= ts:
        t, k, key, v = ev[j]
        if k == "loss": losses.append((t, v))
        else: L[k][key].append((t, v))
        j += 1
    F = feats(d)
    hs = F.get("holders") or []
    wh8 = (F.get("whale") or "")[:8]
    # ledger features (strictly past)
    def dl(w8, hours=None):
        x = L["dump"].get(w8, [])
        if hours: x = [e for e in x if e[0] >= ts - hours * 3.6e12]
        return x
    F["led_dump_n"] = max([len(dl(h["w"][:8])) for h in hs if h["pct"] >= 2], default=0)
    F["led_dump_bad"] = max([sum(1 for e in dl(h["w"][:8]) if e[1][0] < -0.02) for h in hs if h["pct"] >= 2], default=0)
    F["led_dump_pnl"] = min([sum(e[1][0] for e in dl(h["w"][:8])) for h in hs if h["pct"] >= 2 and dl(h["w"][:8])], default=0.0)
    F["led_dump_oth_bad"] = max([sum(1 for e in dl(h["w"][:8]) if e[1][0] < -0.02) for h in hs if h["pct"] >= 2 and h["w"][:8] != wh8], default=0)
    F["led_dump24_bad"] = max([sum(1 for e in dl(h["w"][:8], 24) if e[1][0] < -0.02) for h in hs if h["pct"] >= 2], default=0)
    F["led_whale_dumpbad"] = sum(1 for e in dl(wh8) if e[1][0] < -0.02) if wh8 else 0
    wl = L["whale"].get(wh8, []); F["led_whale_n"] = len(wl); F["led_whale_pnl"] = sum(e[1] for e in wl); F["led_whale_bad"] = sum(1 for e in wl if e[1] < -0.04)
    cl = L["creator"].get((F.get("creator") or "")[:8], []); F["led_cr_n"] = len(cl); F["led_cr_pnl"] = sum(e[1] for e in cl); F["led_cr_bad"] = sum(1 for e in cl if e[1] < -0.04)
    # recent realized losses (breaker inputs): list of (t, pnl) known before signing
    F["_recent"] = [(t, v) for t, v in losses[-30:] if t >= ts - 3.6e12]
    F["_ts"] = ts
    rows.append({"rk": d["rk"], "set": d["set"], "pnl": d["pnl"], "kind": F["kind"], "F": F, "mint": d["mint"], "t": d["t"]})
import pickle
pickle.dump(rows, open(f"{T}/eval_rows.pkl", "wb"))
print("rows", len(rows))
