#!/usr/bin/env python3
# POST-MIGRATION STUDY, pass 4: wallet round trips on PumpSwap after migration (all graduated tokens of the run).
#  - per (wallet, mint): average-cost book; a round trip opens at 0 -> >0 tokens and closes when the holding is back
#    below 1% of its peak. Cost = SOL debited (pool fees included); proceeds = SOL received net of pool fees.
#  - tx costs (network fee + tips) are charged once per tx to the event's user.
#  - tokens held from the bonding curve at migration ("curve inventory") are booked separately: their sells are dumps,
#    with the curve cost from the BC trades.
#  - open positions at the end of the recording are marked at the last pool price minus the fee (flag open=1).
# Output: <RUN>_trips.npz (one row per round trip) and <RUN>_dumps.npz (curve-holder sells), plus wallet string table.
import sys, os, json, pickle, collections, time
import numpy as np
OUT = "/home/moiz/sniper-data/strategies/postmig"

def main(run):
    t0 = time.time()
    R = dict(np.load(os.path.join(OUT, f"{run}_rows.npz")))
    BC = dict(np.load(os.path.join(OUT, f"{run}_bc.npz")))
    st = pickle.load(open(os.path.join(OUT, f"{run}_strs.pkl"), "rb")); strs = st["strs"]; gid = {x: j for j, x in enumerate(strs)}
    toks = [json.loads(l) for l in open(os.path.join(OUT, f"{run}_tokens.jsonl"))]
    mig = {gid[t["mint"]]: (t["mig_s"], t["mig_i"]) for t in toks if t["mint"] in gid}
    # curve inventory and curve cost at migration per (user, mint)
    inv = collections.defaultdict(lambda: [0, 0.0])
    for m, u, s, i, b, sol, tok in zip(BC["mint"].tolist(), BC["user"].tolist(), BC["s"].tolist(), BC["i"].tolist(), BC["isbuy"].tolist(),
                                       BC["sol"].tolist(), BC["tok"].tolist()):
        ms = mig.get(m)
        if ms is None or (s, i) > ms: continue
        r = inv[(u, m)]
        if b: r[0] += tok; r[1] += sol
        else:
            if r[0] > 0: r[1] -= r[1] * min(1.0, tok / r[0])
            r[0] -= tok
    print(run, "curve inventory", len(inv), f"{time.time()-t0:.0f}s", flush=True)
    n = len(R["s"])
    m_ = R["mint"]; starts = np.r_[0, np.nonzero(np.diff(m_))[0] + 1]; ends = np.r_[starts[1:], n]
    trips = collections.defaultdict(list); dumps = collections.defaultdict(list)
    TR = ["user", "mint", "s_in", "i_in", "s_out", "arr_in", "arr_out", "cost", "proceeds", "txcost", "nb", "ns", "open", "mark", "peak_tok",
          "delay", "first_row", "p_in"]
    for a, b in zip(starts.tolist(), ends.tolist()):
        mint = int(m_[a]); ms = mig.get(mint)
        if ms is None: continue
        S = R["s"][a:b].tolist(); I = R["i"][a:b].tolist(); K = R["k"][a:b].tolist(); SD = R["side"][a:b].tolist(); U = R["user"][a:b].tolist()
        BA = R["base"][a:b].tolist(); QT = R["qtot"][a:b].tolist(); FE = (R["fee"][a:b].astype(np.int64) + R["tip"][a:b]).tolist()
        AR = R["arr"][a:b].tolist(); PP = R["p_post"][a:b].tolist(); PR = R["p_pre"][a:b].tolist(); F = R["F"][a:b].tolist()
        last_F = F[-1]
        # liquidation state after the last trade: (B, Qv) post-trade; payout capped by the real quote vault
        jl = b - 1; bl = float(R["base"][jl]); ql = float(R["qcurve"][jl]); lpl = float(R["lpb"][jl]) / 1e4
        if R["side"][jl] == 1: B_l = float(R["B"][jl]) - bl; Qv_l = float(R["Qv"][jl]) + ql + ql * lpl; Qr_l = float(R["Q"][jl]) + ql + ql * lpl
        else: B_l = float(R["B"][jl]) + bl; Qv_l = float(R["Qv"][jl]) - ql + ql * lpl; Qr_l = float(R["Q"][jl]) - ql + ql * lpl
        book = {}
        for j in range(b - a):
            if (S[j], I[j]) < ms: continue
            u = U[j]; tc = FE[j] if K[j] == 0 else 0
            bk = book.get(u)
            if bk is None:
                iv = inv.get((u, mint))
                bk = book[u] = dict(h=0, c=0.0, inv=max(0, iv[0]) if iv else 0, invc=iv[1] if iv and iv[0] > 0 else 0.0, rt=None)
            if SD[j] == 1:
                if bk["rt"] is None:
                    bk["rt"] = dict(s_in=S[j], i_in=I[j], arr_in=AR[j], cost=0.0, proceeds=0.0, txcost=0.0, nb=0, ns=0, peak=0, first_row=a + j, p_in=PR[j])
                rt = bk["rt"]; rt["cost"] += QT[j]; rt["txcost"] += tc; rt["nb"] += 1
                bk["h"] += BA[j]; rt["peak"] = max(rt["peak"], bk["h"])
            else:
                tok = BA[j]
                # sell curve inventory first only if no post-migration position is open
                if bk["rt"] is None and bk["inv"] > 0:
                    use = min(tok, bk["inv"]); frac = use / bk["inv"]
                    dumps[run].append((u, mint, S[j], AR[j], QT[j] * use / tok, bk["invc"] * frac, tc, use))
                    bk["invc"] -= bk["invc"] * frac; bk["inv"] -= use; tok -= use; tc = 0
                    if tok <= 0: continue
                rt = bk["rt"]
                if rt is None:
                    if bk["inv"] > 0 or tok > 0:
                        dumps[run].append((u, mint, S[j], AR[j], QT[j] * tok / BA[j], 0.0, tc, tok))
                    continue
                rt["proceeds"] += QT[j] * min(1.0, tok / max(bk["h"], 1)); rt["txcost"] += tc; rt["ns"] += 1
                bk["h"] -= tok
                if bk["h"] <= 0.01 * rt["peak"]:
                    trips[run].append((u, mint, rt["s_in"], rt["i_in"], S[j], rt["arr_in"], AR[j], rt["cost"], rt["proceeds"], rt["txcost"], rt["nb"],
                                       rt["ns"], 0, 0.0, rt["peak"], rt["s_in"] - ms[0], rt["first_row"], rt["p_in"]))
                    bk["rt"] = None; bk["h"] = 0
        for u, bk in book.items():
            rt = bk["rt"]
            if rt is None: continue
            h = max(bk["h"], 0)
            mark = max(0.0, min(Qv_l * h / (B_l + h), Qr_l)) * (1 - last_F / 1e4)
            trips[run].append((u, mint, rt["s_in"], rt["i_in"], -1, rt["arr_in"], -1.0, rt["cost"], rt["proceeds"], rt["txcost"], rt["nb"],
                               rt["ns"], 1, mark, rt["peak"], rt["s_in"] - ms[0], rt["first_row"], rt["p_in"]))
    T = trips[run]
    arr = {c: np.array([t[k] for t in T]) for k, c in enumerate(TR)}
    np.savez(os.path.join(OUT, f"{run}_trips.npz"), **arr)
    D = dumps[run]; DC = ["user", "mint", "s", "arr", "proceeds", "curve_cost", "txcost", "tok"]
    np.savez(os.path.join(OUT, f"{run}_dumps.npz"), **{c: np.array([t[k] for t in D]) for k, c in enumerate(DC)})
    print(run, "trips", len(T), "dumps", len(D), f"{time.time()-t0:.0f}s", flush=True)

if __name__ == "__main__":
    for r in sys.argv[1:]: main(r)
