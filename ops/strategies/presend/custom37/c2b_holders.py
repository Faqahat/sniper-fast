#!/usr/bin/env python3
"""CUSTOM37 step 2b [MEASURED, arm-time only]: holder features of every window's mint at its trigger, from the chain (every trade of
the mint before the trigger trade; our wallets and the whale kept apart). Features: n_big2 (other wallets holding >= 2% of supply),
other1 (% of supply held by other wallets with >= 1%), top_other (largest other holder %), n_hold (wallets holding > 0), hist_ok
(the chain covers the mint's first trade: its create slot + 2 is in the table).
Out: /home/moiz/sniper-data/custom37/holders_<run>.pkl {(ses, w): feats}"""
import sys, json, pickle, numpy as np
OUT = "/home/moiz/sniper-data/custom37"; SC = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/custom37"
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
SUP = 1e15

def feats(rows, W):
    """rows: (slot, idx, j, buy, tok, user) chain order, all trades of the mint"""
    tg = W["trig"]; key = (tg["slot"], tg["idx"], tg.get("j", 0))
    bal = {}; n = 0; first = None
    for r in rows:
        if (r[0], r[1], r[2]) >= key: break
        if first is None: first = r[0]
        bal[r[5]] = bal.get(r[5], 0) + (r[4] if r[3] else -r[4]); n += 1
    wh = tg["wallet"]
    oth = {u: b for u, b in bal.items() if u != wh and u not in OURS and b > 0}
    v = sorted(oth.values(), reverse=True)
    return {"n_big2": sum(1 for b in v if b >= 0.02 * SUP), "other1": sum(b for b in v if b >= 0.01 * SUP) / SUP * 100, "top_other": (v[0] / SUP * 100) if v else 0.0,
            "n_hold": len(v), "n_prev": n, "first_slot": first, "hist_ok": first is not None and tg["slot"] - tg.get("age_slots", 0) >= first - 2}

def from_tab(X, tab):
    T = np.load(f"{tab}/trades.npy", mmap_mode="r"); ids = json.load(open(f"{tab}/ids.json")); gid = {k: i for i, k in enumerate(ids)}
    mm = np.asarray(T["mint"]); order = np.argsort(mm, kind="stable"); ms = mm[order]
    out = {}
    for W in X["wins"]:
        g = gid.get(W["mint"])
        if g is None: continue
        a, b = np.searchsorted(ms, g), np.searchsorted(ms, g, side="right")
        t = T[np.sort(order[a:b])]
        rows = [(int(x["slot"]), int(x["idx"]), int(x["j"]), int(x["buy"]), int(x["tok"]), ids[int(x["user"])]) for x in t]
        out[(W["ses"], W["w"])] = feats(rows, W)
    return out

def from_chain(X, srcs):
    want = {}
    for W in X["wins"]: want.setdefault(W["mint"], []).append(W)
    rows = {}
    for npz, idsf in srcs:
        I = json.load(open(idsf)); ml = I["mint"]; ul = I["user"]
        mid = {m: k for k, m in enumerate(ml) if m in want}
        z = np.load(npz); mint = z["mint"]
        sel = np.nonzero(np.isin(mint, np.array(list(mid.values()), dtype=np.uint32)))[0]
        cols = {k: z[k][sel] for k in ("s", "i", "j", "buy", "tok", "mint", "user")}
        inv = {v: k for k, v in mid.items()}
        for n in range(len(sel)):
            m = inv[int(cols["mint"][n])]
            rows.setdefault(m, set()).add((int(cols["s"][n]), int(cols["i"][n]), int(cols["j"][n]), int(cols["buy"][n]), int(cols["tok"][n]), ul[int(cols["user"][n])]))
    out = {}
    for m, Ws in want.items():
        L = sorted(rows.get(m, ()))
        for W in Ws: out[(W["ses"], W["w"])] = feats(L, W)
    return out

if __name__ == "__main__":
    for run in sys.argv[1:]:
        X = pickle.load(open(f"{OUT}/win_{run}.pkl", "rb"))
        H = from_tab(X, f"{OUT}/tab37") if run == "r37" else from_chain(X, [("/home/moiz/sniper-data/presend_quiet3/chain.npz", "/home/moiz/sniper-data/presend_quiet3/ids.json"),
                                                                         ("/home/moiz/sniper-data/presend_young/ext/chain.npz", "/home/moiz/sniper-data/presend_young/ext/ids.json")])
        pickle.dump(H, open(f"{OUT}/holders_{run}.pkl", "wb"))
        print(run, "windows", len(X["wins"]), "with holder feats", len(H), "hist_ok", sum(1 for v in H.values() if v["hist_ok"]), flush=True)
