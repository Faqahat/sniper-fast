#!/usr/bin/env python3
"""FLAT study, step 4 (read-only): arm-time features of every live window (knowable at the trigger: the token's chain rows
strictly before the trigger tx + the trigger itself; chain-wide whale dump history from dumps closed before the trigger slot,
last 24 h), incl. QUIET's four signals exactly as apply_filter.py / the dip20 parity (MEASURED inputs, rule logic replayed).
  dump = a sell >= 0.3 SOL, curve < 100 SOL after it, post price <= 0.92 x pre price; its followers = distinct other wallets
         buying the token after it in its slot and the next 2 slots
Adds w['f'] (features) and w['qs'] (QUIET signals) to base_<run>.pkl. Also checks the replayed signals against the engine's own
logged QUIET record where present (r27 / r28).
usage: f4_features.py r24 r25 r26 r27"""
import sys, json, pickle, collections, bisect
import numpy as np
import flatlib as FL


def dump_book(C):
    c = C.c
    S, BUY, SOL, TOK, VS, VT, U, BT = c["s"], c["buy"], c["sol"], c["tok"], c["vsol"], c["vtok"], c["user"], c["bt"]
    m = (BUY == 0) & (SOL >= 300_000_000) & (VS < 100_000_000_000) & (VT > TOK)
    idx = np.nonzero(m)[0]
    vs = VS[idx].astype(float); vt = VT[idx].astype(float); so = SOL[idx].astype(float); tk = TOK[idx].astype(float)
    post = vs / np.maximum(vt, 1); pre = (vs + so) / np.maximum(vt - tk, 1)
    idx = idx[post <= 0.92 * pre]
    book = collections.defaultdict(list)
    # position of every row inside its mint's ordering
    inv = np.empty(C.n, np.int64); inv[C.morder] = np.arange(C.n)
    for r in idx.tolist():
        mk = int(c["mint"][r]); a, e = C.mstart[mk], C.mstart[mk + 1]
        p = int(inv[r]); s = int(S[r]); u = int(U[r]); bs = set()
        q = p + 1
        while q < e:
            rr = C.morder[q]
            if S[rr] > s + 2: break
            if BUY[rr] and U[rr] != u: bs.add(int(U[rr]))
            q += 1
        book[u].append((s, int(BT[r]), len(bs)))
    for v in book.values(): v.sort()
    return book


def feats(C, w, book, coh, fb):
    c = C.c; tr = w["trig"]
    rows = C.mint_rows(w["mint"])
    kt = w["k_trig"]
    s0 = tr["slot"]
    f = {}
    if kt is None:
        return None, None
    R0 = rows[:kt]
    sl = c["s"][R0].astype(np.int64); U = c["user"][R0]; BUY = c["buy"][R0]; TOK = c["tok"][R0].astype(np.int64); SOL = c["sol"][R0]
    f["n_tr"] = int(len(R0))
    for L in (10, 50):
        mm = sl >= s0 - L
        f[f"n_tr_{L}"] = int(mm.sum()); f[f"n_u_{L}"] = int(len(set(U[mm].tolist())))
    f["vol_50"] = float(SOL[sl >= s0 - 50].sum()) / 1e9
    f["since_last"] = int(s0 - sl[-1]) if len(sl) else 9999
    bal = collections.defaultdict(int)
    for u, b, t in zip(U.tolist(), BUY.tolist(), TOK.tolist()): bal[u] += t if b else -t
    seen = set(U.tolist())
    f["coh_hold"] = sum(1 for u in seen if u in coh and bal[u] > 0)
    f["fb_n"] = sum(1 for u in seen if u in fb)
    wid = C.wid.get(tr["wallet"])
    tb = tr["t"] / 1e9
    d = [nf for s, bt, nf in book.get(wid, []) if s + 2 < s0 and bt >= tb - 24 * 3600] if wid is not None else []
    f["wh_dump_fol"] = float(np.mean(d)) if d else -1.0
    f["wh_dumps"] = len(d)
    f["vsol"] = tr["vsol"] / 1e9
    f["whale_pct"] = float(tr["pct"]); f["whale_sol"] = tr["sol"] / 1e9; f["age_slots"] = int(tr["age_slots"])
    q = [f["since_last"] >= 1, f["coh_hold"] == 0, f["fb_n"] < 2, f["wh_dump_fol"] < 2.24]
    f["quiet_n"] = int(sum(q))
    return f, q


def main():
    runs = sys.argv[1:]
    phases = sorted(set(p for r in runs for p in FL.RUN_PHASES[r]))
    C = FL.Chain(phases)
    coh_s = set(json.load(open(FL.COHORT))); fb_s = set(json.load(open(FL.FBOTS)))
    coh = {C.wid[x] for x in coh_s if x in C.wid}; fb = {C.wid[x] for x in fb_s if x in C.wid}
    book = dump_book(C)
    print(f"dumps {sum(len(v) for v in book.values()):,} sellers {len(book):,}, cohort {len(coh)}/{len(coh_s)}, fbots {len(fb)}/{len(fb_s)}", flush=True)
    for run in runs:
        B = FL.load_base(run)
        par = collections.Counter()
        for w in B["W"]:
            f, q = feats(C, w, book, coh, fb)
            w["f"] = f; w["qs"] = q
            w["quiet_skip_replay"] = bool(q is not None and all(q))
            lq = w.get("quiet")
            if lq and q is not None:
                lv = lq.get("q")
                par["logged"] += 1
                if lv == q: par["same4"] += 1
                else:
                    for k in range(4):
                        if lv[k] != q[k]: par[f"diff_sig{k + 1}"] += 1
                if lq.get("all4") == all(q): par["same_all4"] += 1
        pickle.dump(B, open(f"{FL.D}/base_{run}.pkl", "wb"))
        n = len(B["W"]); sk = sum(1 for w in B["W"] if w["quiet_skip_replay"])
        print(f"{run}: windows {n}, features {sum(1 for w in B['W'] if w['f'] is not None)}, QUIET all-4 (replayed) {sk}, parity vs logged {dict(par)}", flush=True)


if __name__ == "__main__":
    main()
