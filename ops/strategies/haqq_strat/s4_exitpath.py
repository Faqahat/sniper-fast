#!/usr/bin/env python3
"""HAQQ_STRAT step 4 (read-only): what triggers haqq's exits, last 24 h, non-dead lots (DIP / DIP_LATE / ADD / OTHER / LAUNCH).
For each lot: the lot's exit value path (curve sell value of its tokens after each outside trade, pump fee in) from his buy to his
first sell of the lot. Measures: return at his sell, the best return seen before it, slots from his buy, and the per-slot sell rate
by (slots held, current return) = a hazard table. MEASURED."""
import json, pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_strat")
from hs_lib import *
TAB = "/home/moiz/sniper-data/haqq_model/tab"
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def main():
    lots = pickle.load(open(f"{D}/lots24.pkl", "rb"))
    Z = load_pos(); LOTS = Z["lots"]
    ids = json.load(open(f"{TAB}/ids.json")); idm = {k: i for i, k in enumerate(ids)}; h = idm["haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"]
    T = np.load(f"{TAB}/trades.npy", mmap_mode="r")
    sel = [r for r in lots if not r["probe"] and r["t"] in ("DIP", "DIP_LATE", "ADD", "OTHER", "LAUNCH") and r["hold_slots"] is not None]
    mids = np.array(sorted({idm[r["b"]["mint"]] for r in sel}), np.uint32)
    TT = T[np.isin(T["mint"], mids)]; TT = TT[np.lexsort((TT["j"], TT["idx"], TT["slot"], TT["mint"]))]
    um, st_ = np.unique(TT["mint"], return_index=True); en_ = np.append(st_[1:], len(TT))
    span = {ids[int(m)]: (int(a), int(e)) for m, a, e in zip(um, st_, en_)}
    haz = collections.defaultdict(lambda: [0, 0])      # (slot bucket, ret bucket) -> [lot-slots at risk, sells]
    res = []
    for r in sel:
        b = r["b"]; L = LOTS[b["lot_ix"]]; a, e = span[b["mint"]]
        sl = TT["slot"][a:e].astype(np.int64); ix = TT["idx"][a:e].astype(np.int64); us = TT["user"][a:e]
        vs = TT["vsol"][a:e].astype(np.float64); vt = TT["vtok"][a:e].astype(np.float64)
        key = sl * 100000 + ix
        k0 = int(np.searchsorted(key, b["slot"] * 100000 + b["idx"])); s_end = L["sells"][0][0]
        k1 = int(np.searchsorted(sl, s_end))                         # first trade in his first-sell slot
        tok = L["tok"]; cost = L["cost"]
        best = -1.0; cur = None; per_slot = {}
        for k in range(k0 + 1, k1):
            if us[k] == h: continue
            kk = vs[k] * vt[k]; val = (vs[k] - kk / (vt[k] + tok)) / 1e9 * 0.9875
            cur = val / cost - 1; best = max(best, cur); per_slot[int(sl[k])] = cur
        # value just before his sell
        res.append(dict(t=r["t"], ret_sell=r["ret"], best=best, hs=r["hold_slots"], net=r["net"], size=r["size"]))
        # hazard: for each slot held from 1..hold, the return at the end of the previous slot
        last = 0.0
        for s in range(b["slot"] + 1, s_end + 1):
            if s - 1 in per_slot: last = per_slot[s - 1]
            hs_ = s - b["slot"]
            sb = 0 if hs_ <= 2 else 1 if hs_ <= 5 else 2 if hs_ <= 10 else 3 if hs_ <= 25 else 4
            rb = 0 if last < -0.10 else 1 if last < -0.03 else 2 if last < 0.03 else 3 if last < 0.10 else 4 if last < 0.25 else 5
            haz[(sb, rb)][0] += 1
            if s == s_end: haz[(sb, rb)][1] += 1
    P("# haqq exit triggers, last 24 h, non-dead lots (MEASURED)")
    P("\nSell rate per slot by slots held x lot return at the end of the previous slot (lot-slots at risk in brackets):")
    P("| slots held | < -10% | -10..-3% | -3..+3% | +3..+10% | +10..+25% | > +25% |"); P("|---|---|---|---|---|---|---|")
    for sb, nm in enumerate(("1-2", "3-5", "6-10", "11-25", "> 25")):
        cells = []
        for rb in range(6):
            n, s = haz[(sb, rb)]
            cells.append(f"{100 * s / n:.0f}% ({n})" if n >= 30 else "-")
        P(f"| {nm} | " + " | ".join(cells) + " |")
    v = res
    P(f"\nReturn at his sell vs best return seen before it (lots {len(v)}):")
    for lo_, hi_, nm in ((0, 3, "sold within 2 slots"), (3, 11, "3-10 slots"), (11, 31, "11-30"), (31, 10 ** 9, "> 30")):
        vv = [x for x in v if lo_ <= x["hs"] < hi_]
        if vv: P(f"- {nm}: {len(vv)} lots, return at sell p25/50/75 {pct([100 * x['ret_sell'] for x in vv], (25, 50, 75))}%, best seen before p50 {np.median([100 * x['best'] for x in vv]):.1f}%, "
                 f"gave back from best > 5 pts {100 * np.mean([x['best'] - x['ret_sell'] > 0.05 for x in vv]):.0f}%, net {sum(x['net'] for x in vv):+.2f}")
    open(f"{D}/s4.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
