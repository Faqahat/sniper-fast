#!/usr/bin/env python3
# POST-MIGRATION STUDY: what triggers the consistent winners' entries? For each round trip of the chosen wallets, the
# trades right before the entry in the same pool: the previous trade's side/size/price move, how many txs and ms
# separate the entry from it (speed), the price move over the last ~1 s and ~10 s, token age, and the exit.
import json, pickle, collections, sys
import numpy as np
OUT = "/home/moiz/sniper-data/strategies/postmig"
SMS = 212.0

def profile(run, wallets):
    R = np.load(f"{OUT}/{run}_rows.npz")
    cols = ["s", "i", "k", "arr", "side", "user", "mint", "qtot", "p_pre", "p_post", "cup", "tip", "fee", "cu", "relay"]
    D = {c: R[c] for c in cols}
    st = pickle.load(open(f"{OUT}/{run}_strs.pkl", "rb")); strs = st["strs"]; gid = {x: j for j, x in enumerate(strs)}
    tr = dict(np.load(f"{OUT}/{run}_trips.npz"))
    out = {}
    for w in wallets:
        u = gid.get(w)
        if u is None: continue
        ix = np.nonzero(tr["user"] == u)[0]
        recs = []
        for t in ix.tolist():
            fr = int(tr["first_row"][t]); m = D["mint"][fr]
            # previous trades in the same pool (not by this wallet)
            j = fr - 1
            while j >= 0 and D["mint"][j] == m and D["user"][j] == u: j -= 1
            if j < 0 or D["mint"][j] != m: prev = None
            else: prev = j
            r = dict(size=float(D["qtot"][fr] / 1e9), cup=int(D["cup"][fr]), tip=int(D["tip"][fr]), fee=int(D["fee"][fr]),
                     pnl=float((tr["proceeds"][t] + tr["mark"][t] - tr["cost"][t] - tr["txcost"][t]) / 1e9), open=int(tr["open"][t]),
                     hold=float((tr["arr_out"][t] - tr["arr_in"][t]) / 1000) if tr["open"][t] == 0 else None, delay=float(tr["delay"][t] * SMS / 1000))
            if prev is not None:
                r.update(prev_side=int(D["side"][prev]), prev_sol=float(D["qtot"][prev] / 1e9),
                         prev_move=float(D["p_post"][prev] / D["p_pre"][prev] - 1), dt_ms=float(D["arr"][fr] - D["arr"][prev]),
                         dtx=int(D["i"][fr] - D["i"][prev]) if D["s"][fr] == D["s"][prev] else None, same_slot=int(D["s"][fr] == D["s"][prev]))
                # price move over the last ~1 s and ~10 s before entry
                for lbl, ms in (("m1s", 1000), ("m10s", 10000)):
                    k = prev
                    while k - 1 >= 0 and D["mint"][k - 1] == m and D["arr"][k - 1] >= D["arr"][fr] - ms: k -= 1
                    r[lbl] = float(D["p_post"][prev] / D["p_pre"][k] - 1)
                # biggest sell / buy in the last 1 s
                k = prev; bs = 0.0; bb = 0.0
                while k >= 0 and D["mint"][k] == m and D["arr"][k] >= D["arr"][fr] - 1000:
                    if D["side"][k] == -1: bs = max(bs, float(D["qtot"][k] / 1e9))
                    else: bb = max(bb, float(D["qtot"][k] / 1e9))
                    k -= 1
                r["bigsell1s"] = bs; r["bigbuy1s"] = bb
            recs.append(r)
        out[w] = recs
    return out

def summarize(w, recs):
    n = len(recs)
    if not n: return
    P = [r for r in recs if "prev_side" in r]
    ps = collections.Counter("sell" if r["prev_side"] == -1 else "buy" for r in P)
    ss = sum(r["same_slot"] for r in P) / max(1, len(P))
    dtx = [r["dtx"] for r in P if r.get("dtx") is not None]
    dtm = [r["dt_ms"] for r in P]
    pnl = np.array([r["pnl"] for r in recs])
    print(f"  {w[:10]} n={n} pnl={pnl.sum():+.1f} mean={pnl.mean():+.4f} size_med={np.median([r['size'] for r in recs]):.2f} "
          f"prev: sell {ps['sell']/max(1,len(P)):.2f} buy {ps['buy']/max(1,len(P)):.2f} same-slot {ss:.2f} dtx_med {np.median(dtx) if dtx else None} "
          f"dt_ms_med {np.median(dtm):.0f} | prev_sol_med {np.median([r['prev_sol'] for r in P]):.2f} prev_move_med {np.median([r['prev_move'] for r in P])*100:+.2f}% "
          f"m1s_med {np.median([r['m1s'] for r in P])*100:+.2f}% m10s_med {np.median([r['m10s'] for r in P])*100:+.2f}% "
          f"bigsell1s>=1: {np.mean([r['bigsell1s']>=1 for r in P]):.2f} bigbuy1s>=1: {np.mean([r['bigbuy1s']>=1 for r in P]):.2f} "
          f"hold_med {np.median([r['hold'] for r in recs if r['hold'] is not None]):.1f}s delay_med {np.median([r['delay'] for r in recs]):.0f}s "
          f"cup_med {np.median([r['cup'] for r in recs]):.0f} tip_med {np.median([r['tip'] for r in recs]):.0f}")

if __name__ == "__main__":
    W = json.load(open(f"{OUT}/wallets.json"))
    pick = []
    for w, x in W.items():
        r2 = x["runs"].get("R2"); r3 = x["runs"].get("R3")
        if x["insider"] or not r2 or not r3: continue
        if r2["n"] >= 100 and r3["n"] >= 100 and r2["pnl"] > 0 and r3["pnl"] > 0:
            pick.append((r2["pnl"] + r3["pnl"], w))
    pick.sort(reverse=True); wl = [w for _, w in pick[:40]]
    print("profiling", len(wl), "wallets (>=100 trips and profit in R2 and R3, non-insider)")
    res = profile("R3", wl)
    json.dump(res, open(f"{OUT}/profile_R3.json", "w"))
    for w in wl: summarize(w, res.get(w, []))
