#!/usr/bin/env python3
"""QUIET4 step 2 [MEASURED, read-only]: the chain tape of every r37 window's mint (armed AND virtual), trigger slot - 3 .. + 120,
plus the per-slot max tx index (block-position clock), from the fresh decode of the recorder chunks 10-29 07:11 -> 10-30 01:20 PKT
(/home/moiz/sniper-data/presend_quiet4/tab37, built by ops/strategies/presend/real/decode.py + build.py). Same format as
custom37/c2_tape.py: rows = (slot, idx, j, buy, sol, tok, vsol, vtok, user).
Out: /home/moiz/sniper-data/presend_quiet4/tape_r37.pkl"""
import json, pickle, numpy as np
OUT = "/home/moiz/sniper-data/presend_quiet4"; TAB = f"{OUT}/tab37"
LO, HI = 3, 120


def main():
    X = pickle.load(open(f"{OUT}/win_r37.pkl", "rb"))
    T = np.load(f"{TAB}/trades.npy", mmap_mode="r"); ids = json.load(open(f"{TAB}/ids.json")); gid = {k: i for i, k in enumerate(ids)}
    S = np.load(f"{TAB}/slots.npy")
    mm = np.asarray(T["mint"]); order = np.argsort(mm, kind="stable"); ms = mm[order]
    out = {}; slots = set(); miss = 0
    for W in X["wins"]:
        g = gid.get(W["mint"])
        if g is None: miss += 1; continue
        a, b = np.searchsorted(ms, g), np.searchsorted(ms, g, side="right")
        t = T[np.sort(order[a:b])]
        s0 = W["trig"]["slot"]; t = t[(t["slot"] >= s0 - LO) & (t["slot"] <= s0 + HI)]
        out[(W["ses"], W["w"])] = [(int(x["slot"]), int(x["idx"]), int(x["j"]), int(x["buy"]), int(x["sol"]), int(x["tok"]), int(x["vsol"]), int(x["vtok"]), ids[int(x["user"])]) for x in t]
        slots.update(range(s0 - LO, s0 + HI + 1))
    sl = S["slot"]; k = np.isin(sl, np.array(sorted(slots), dtype=sl.dtype))
    maxi = {int(s): int(i) for s, i in zip(sl[k], S["maxi"][k])}
    end = int(sl[-1])
    pickle.dump({"tapes": out, "maxi": maxi, "end_slot": end}, open(f"{OUT}/tape_r37.pkl", "wb"))
    # the trigger trade must be on the tape (else the window cannot be replayed)
    ok = 0; late = 0
    for W in X["wins"]:
        tp = out.get((W["ses"], W["w"])) or []
        tg = W["trig"]
        if any((r[0], r[1], r[2]) == (tg["slot"], tg["idx"], tg.get("j", 0)) for r in tp): ok += 1
        if tg["slot"] + HI > end: late += 1
    print("windows", len(X["wins"]), "with tape", len(out), "trigger on tape", ok, "no mint", miss, "tape end slot", end, "windows past tape end - 120", late,
          "trades", sum(len(v) for v in out.values()))


if __name__ == "__main__":
    main()
