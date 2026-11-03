#!/usr/bin/env python3
"""CUSTOM37 step 2 [MEASURED, read-only]: the chain tape of every window's mint (all pump.fun trades, chain order) from
trigger slot - 3 to trigger slot + 120, with the per-slot max tx index (block-position clock).
Sources: r37 = fresh decode of the recorder chunks 10-29 07:21 -> 18:21 PKT (custom37/tab37, built by real/decode.py + build.py);
earlier runs = presend_quiet3/chain.npz (10-24 19:10 -> 10-29 07:16 PKT) + presend_young/ext/chain.npz (07:16 -> 09:11 PKT).
Out: /home/moiz/sniper-data/custom37/tape_<run>.pkl {"tapes": {(ses, w): rows}, "maxi": {slot: max idx}, "end_slot": last slot}
rows = list of (slot, idx, j, buy, sol, tok, vsol, vtok, user)"""
import sys, json, pickle, numpy as np
OUT = "/home/moiz/sniper-data/custom37"
SC = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/custom37"
LO, HI = 3, 120


def from_tab(X, tab):
    T = np.load(f"{tab}/trades.npy", mmap_mode="r"); ids = json.load(open(f"{tab}/ids.json")); gid = {k: i for i, k in enumerate(ids)}
    S = np.load(f"{tab}/slots.npy")
    mm = np.asarray(T["mint"]); order = np.argsort(mm, kind="stable"); ms = mm[order]
    out = {}; slots = set()
    for W in X["wins"]:
        g = gid.get(W["mint"])
        if g is None: continue
        a, b = np.searchsorted(ms, g), np.searchsorted(ms, g, side="right")
        t = T[np.sort(order[a:b])]
        s0 = W["trig"]["slot"]; t = t[(t["slot"] >= s0 - LO) & (t["slot"] <= s0 + HI)]
        out[(W["ses"], W["w"])] = [(int(x["slot"]), int(x["idx"]), int(x["j"]), int(x["buy"]), int(x["sol"]), int(x["tok"]), int(x["vsol"]), int(x["vtok"]), ids[int(x["user"])]) for x in t]
        slots.update(range(s0 - LO, s0 + HI + 1))
    sl = S["slot"]; k = np.isin(sl, np.array(sorted(slots), dtype=sl.dtype))
    maxi = {int(s): int(i) for s, i in zip(sl[k], S["maxi"][k])}
    return out, maxi, int(sl[-1])


def from_chain(X, srcs):
    want = {}
    for W in X["wins"]: want.setdefault(W["mint"], []).append(W)
    rows = {}; maxi = {}; end = 0
    for npz, idsf in srcs:
        I = json.load(open(idsf)); ml = I["mint"]; ul = I["user"]
        mid = {m: k for k, m in enumerate(ml) if m in want}
        z = np.load(npz)
        mint = z["mint"]; sel = np.nonzero(np.isin(mint, np.array(list(mid.values()), dtype=np.uint32)))[0]
        cols = {k: z[k][sel] for k in ("s", "i", "j", "buy", "sol", "tok", "vsol", "vtok", "mint", "user")}
        inv = {v: k for k, v in mid.items()}
        B = z["blocks"]
        for s, i, bt in B.tolist(): maxi[s] = max(i, maxi.get(s, 0)); end = max(end, s)
        for n in range(len(sel)):
            m = inv[int(cols["mint"][n])]
            rows.setdefault(m, set()).add((int(cols["s"][n]), int(cols["i"][n]), int(cols["j"][n]), int(cols["buy"][n]), int(cols["sol"][n]), int(cols["tok"][n]),
                                           int(cols["vsol"][n]), int(cols["vtok"][n]), ul[int(cols["user"][n])]))
        print(npz, "mints hit", sum(1 for m in want if m in rows), flush=True)
    out = {}; keep = set()
    for m, Ws in want.items():
        L = sorted(rows.get(m, ()))
        for W in Ws:
            s0 = W["trig"]["slot"]
            out[(W["ses"], W["w"])] = [x for x in L if s0 - LO <= x[0] <= s0 + HI]
            keep.update(range(s0 - LO, s0 + HI + 1))
    maxi = {s: i for s, i in maxi.items() if s in keep}
    return out, maxi, end


if __name__ == "__main__":
    for run in sys.argv[1:]:
        X = pickle.load(open(f"{OUT}/win_{run}.pkl", "rb"))
        if run == "r37": tapes, maxi, end = from_tab(X, f"{OUT}/tab37")
        else: tapes, maxi, end = from_chain(X, [("/home/moiz/sniper-data/presend_quiet3/chain.npz", "/home/moiz/sniper-data/presend_quiet3/ids.json"),
                                                ("/home/moiz/sniper-data/presend_young/ext/chain.npz", "/home/moiz/sniper-data/presend_young/ext/ids.json")])
        pickle.dump({"tapes": tapes, "maxi": maxi, "end_slot": end}, open(f"{OUT}/tape_{run}.pkl", "wb"))
        n = len(X["wins"]); nt = sum(1 for W in X["wins"] if tapes.get((W["ses"], W["w"])))
        print(run, "windows", n, "with tape", nt, "end slot", end, "trades", sum(len(v) for v in tapes.values()), flush=True)
