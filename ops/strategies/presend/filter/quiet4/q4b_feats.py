#!/usr/bin/env python3
"""QUIET4 step 4b [MEASURED, read-only]: arm-time QUIET signal values recomputed CAUSALLY from the chain for every window / skip of the 24
earlier runs and every r37 trigger (armed + virtual), logic = quiet3/f2_feats.py (it matched the engine's logged signals 2663/2664), plus:
  * the whale's mean followers over its dumps of the last 24 / 12 / 6 h (wf24 / wf12 / wf6; -1 = none) and their counts;
  * fb_n with the FROZEN follower-bot list (ops/strategies/presend/filter/fbots_frozen.json, 297 wallets; r37 ran with no list);
  * the v2 annotation recomputed (n_tr_60s, maxdd_120s, at_120s_high; block-time windows) for runs that did not log it;
  * oth[o] = other wallets' trades (not the whale, not ours) after the trigger through slot s0 + o, o = 0..12 (stop rule N:M input).
Chain = presend_quiet3/chain.npz (block time < 1793240200 = 10-29 07:16:40 PKT) + presend_quiet4/tab37 (from there to 10-30 01:20 PKT).
Out: /home/moiz/sniper-data/presend_quiet4/feats.json {"w24": [c per windows24 window], "s24": [c per windows24 skip], "r37": {"ses:w": c}}"""
import json, collections, time, pickle
import numpy as np
D3 = "/home/moiz/sniper-data/presend_quiet3"; D4 = "/home/moiz/sniper-data/presend_quiet4"
COHORT = "/home/moiz/sniper/ops/overnight/sel/cohort_train.json"; FBOTS = "/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json"
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
CUT_BT = 1793240200
t0 = time.time()


def load_chain():
    C = np.load(f"{D3}/chain.npz"); I = json.load(open(f"{D3}/ids.json"))
    ml = list(I["mint"]); ul = list(I["user"])
    cols = {k: C[k] for k in ("s", "i", "j", "bt", "buy", "sol", "tok", "vsol", "vtok", "mint", "user")}
    print("quiet3 chain", len(cols["s"]), f"{time.time()-t0:.0f}s", flush=True)
    T = np.load(f"{D4}/tab37/trades.npy"); ids = json.load(open(f"{D4}/tab37/ids.json"))
    T = T[T["bt"] >= CUT_BT]
    mid = {m: k for k, m in enumerate(ml)}; uid = {u: k for k, u in enumerate(ul)}
    gm = np.unique(T["mint"]); gu = np.unique(T["user"])
    mapm = np.zeros(len(ids), np.uint32); mapu = np.zeros(len(ids), np.uint32)
    for g in gm.tolist():
        s = ids[g]; k = mid.get(s)
        if k is None: k = mid[s] = len(ml); ml.append(s)
        mapm[g] = k
    for g in gu.tolist():
        s = ids[g]; k = uid.get(s)
        if k is None: k = uid[s] = len(ul); ul.append(s)
        mapu[g] = k
    add = {"s": T["slot"].astype(np.uint64), "i": T["idx"].astype(np.uint32), "j": T["j"].astype(np.uint8), "bt": T["bt"].astype(np.uint32), "buy": T["buy"].astype(np.uint8),
           "sol": T["sol"].astype(np.uint64), "tok": T["tok"].astype(np.uint64), "vsol": T["vsol"].astype(np.uint64), "vtok": T["vtok"].astype(np.uint64),
           "mint": mapm[T["mint"]], "user": mapu[T["user"]]}
    assert int(add["s"].min()) > int(cols["s"].max()), "tab37 part must start after the quiet3 chain"
    out = {k: np.concatenate([cols[k].astype(add[k].dtype), add[k]]) for k in cols}
    print("combined", len(out["s"]), "mints", len(ml), "users", len(ul), f"{time.time()-t0:.0f}s", flush=True)
    return out, ml, ul, mid, uid


def main():
    C, ml, ul, mid, uid = load_chain()
    S = C["s"].astype(np.int64); IX = C["i"]; J = C["j"]; BT = C["bt"].astype(np.int64); BUY = C["buy"]; SOL = C["sol"]; TOK = C["tok"]; VS = C["vsol"]; VT = C["vtok"]
    MI = C["mint"]; UI = C["user"]; n = len(S)
    coh = {uid[u] for u in json.load(open(COHORT)) if u in uid}; fb = {uid[u] for u in json.load(open(FBOTS)) if u in uid}
    ours = {uid[u] for u in OURS if u in uid}
    morder = np.argsort(MI, kind="stable"); mstart = np.searchsorted(MI[morder], np.arange(len(ml) + 1))
    inv = np.empty(n, np.int64); inv[morder] = np.arange(n)
    BT0 = int(BT.min())
    # ---- the dump book (engine rule: sell >= 0.3 SOL, curve < 100 SOL, post price <= 0.92 x pre price; followers = distinct buyers but
    # the seller after it in its slot and the next 2 slots)
    m = (BUY == 0) & (SOL >= 300_000_000) & (VS < 100_000_000_000) & (VT > TOK)
    idx = np.nonzero(m)[0]
    post = VS[idx].astype(float) / np.maximum(VT[idx].astype(float), 1); pre = (VS[idx] + SOL[idx]).astype(float) / np.maximum((VT[idx] - TOK[idx]).astype(float), 1)
    idx = idx[~(post > 0.92 * pre)]
    book = collections.defaultdict(list)
    for r in idx.tolist():
        mk = int(MI[r]); e = mstart[mk + 1]; p = int(inv[r]); s = int(S[r]); u = int(UI[r]); bs = set(); q = p + 1
        while q < e:
            rr = morder[q]
            if S[rr] > s + 2: break
            if BUY[rr] and UI[rr] != u: bs.add(int(UI[rr]))
            q += 1
        book[u].append((s, int(BT[r]), len(bs)))
    for v in book.values(): v.sort()
    print("dumps", len(idx), "sellers", len(book), f"{time.time()-t0:.0f}s", flush=True)

    def feats(mint, whale, slot, idx_, j=None):
        f = {}; mk = mid.get(mint); wh = uid.get(whale, -1)
        if mk is None: return {"ok": False}
        rows = morder[mstart[mk]:mstart[mk + 1]]
        k = np.nonzero((S[rows] == slot) & (IX[rows] == idx_) & (BUY[rows] == 1))[0]
        if len(k) > 1:
            kk = [a for a in k if UI[rows[a]] == wh]; k = kk or list(k)
            if j is not None and len(k) > 1:
                kj = [a for a in k if J[rows[a]] == j]; k = kj or k
        if len(k) == 0: return {"ok": False}
        kt = int(k[0]); s0 = slot; bt0 = int(BT[rows[kt]]); R0 = rows[:kt]
        sl = S[R0]; U = UI[R0]; B = BUY[R0]; Tk = TOK[R0].astype(np.int64)
        f["ok"] = True; f["bt"] = bt0
        f["since_last"] = int(s0 - sl[-1]) if len(sl) else 9999
        bal = collections.defaultdict(int)
        for u, b, t in zip(U.tolist(), B.tolist(), Tk.tolist()): bal[u] += t if b else -t
        seen = set(U.tolist())
        f["coh_hold"] = sum(1 for u in seen if u in coh and bal[u] > 0); f["fb_n"] = len(seen & fb); f["n_prev"] = int(len(R0))
        H = book.get(wh, [])
        for tag, h in (("24", 86400), ("12", 43200), ("6", 21600)):
            hist = [d for d in H if d[0] + 2 < s0 and d[1] >= bt0 - h]
            f[f"wd{tag}"] = len(hist); f[f"wf{tag}"] = float(np.mean([d[2] for d in hist])) if hist else -1.0
        f["hist_h"] = (bt0 - BT0) / 3600
        # v2 (block time): trades in [bt0 - 60, bt0) before the trigger; the 120 s high of post-trade prices vs the trigger's pre-trade price
        b60 = BT[R0] >= bt0 - 60; b120 = BT[R0] >= bt0 - 120
        f["n_tr_60s"] = int(b60.sum()); f["n_120s"] = int(b120.sum())
        tr = rows[kt]
        pre_p = float(VS[tr] - SOL[tr]) / max(float(VT[tr] + TOK[tr]), 1.0)
        if b120.any():
            pp = VS[R0][b120].astype(float) / np.maximum(VT[R0][b120].astype(float), 1.0); mx = float(pp.max())
            f["maxdd_120s"] = (mx - pre_p) / mx if mx > 0 else 0.0
        else: f["maxdd_120s"] = 0.0
        f["at_120s_high"] = f["maxdd_120s"] <= 0.001
        f["v2skip"] = f["n_tr_60s"] <= 6 and f["at_120s_high"]
        # stop rule input: others (not the whale, not ours) after the trigger through slot s0 + o
        RA = rows[kt + 1:]; ua = UI[RA]; sa = S[RA]; oth = (ua != wh) & ~np.isin(ua, list(ours))
        f["oth"] = [int(((sa <= s0 + o) & oth).sum()) for o in range(0, 13)]
        return f

    J24 = json.load(open(f"{D4}/windows24.json"))
    w24 = [feats(x["mint"], x["whale"], x["slot"], x["idx"], x.get("j")) for x in J24["windows"]]
    s24 = [feats(x["mint"], x["whale"], x["slot"], x["idx"], x.get("j")) for x in J24["skips"]]
    print("24 runs: windows", len(w24), "miss", sum(1 for c in w24 if not c["ok"]), "skips", len(s24), "miss", sum(1 for c in s24 if not c["ok"]), f"{time.time()-t0:.0f}s", flush=True)
    X = pickle.load(open(f"{D4}/win_r37.pkl", "rb"))
    r37 = {}
    for W in X["wins"]:
        tg = W["trig"]; r37[f"{W['ses']}:{W['w']}"] = feats(W["mint"], tg["wallet"], tg["slot"], tg["idx"], tg.get("j"))
    print("r37: triggers", len(r37), "miss", sum(1 for c in r37.values() if not c["ok"]), f"{time.time()-t0:.0f}s", flush=True)
    json.dump({"w24": w24, "s24": s24, "r37": r37}, open(f"{D4}/feats.json", "w"))
    # parity with the engine's logged signals (r37 all triggers; 24-run windows where logged)
    agree = collections.Counter()
    for W in X["wins"]:
        q = W.get("quiet") or {}; c = r37[f"{W['ses']}:{W['w']}"]
        if not c.get("ok") or "since_last" not in q: continue
        agree["n"] += 1
        agree["since_last"] += (min(q["since_last"], 9999) == c["since_last"]) or (q["since_last"] >= 1) == (c["since_last"] >= 1)
        agree["coh_hold"] += q["coh_hold"] == c["coh_hold"]
        agree["wh_fol<4"] += (q["wh_fol"] < 4.0) == (c["wf24"] < 4.0)
        agree["wh_fol~"] += abs(q["wh_fol"] - c["wf24"]) < 0.01
        agree["all3"] += (q["since_last"] >= 1 and q["coh_hold"] == 0 and q["wh_fol"] < 4.0) == (c["since_last"] >= 1 and c["coh_hold"] == 0 and c["wf24"] < 4.0)
        v = W.get("v2") or {}
        if "n_tr_60s" in v:
            agree["v2n"] += 1; agree["v2skip"] += bool(v["skip"]) == bool(c["v2skip"]); agree["n60"] += abs(v["n_tr_60s"] - c["n_tr_60s"]) <= 1
    print("r37 parity with the engine's logged signals:", dict(agree))


if __name__ == "__main__":
    main()
