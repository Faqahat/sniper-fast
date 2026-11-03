#!/usr/bin/env python3
"""REPLAY4 step 2: turn the collector trades into c37lib's tape format, per window.
c37lib.prep_window needs rows (slot, idx, j, buy, sol, tok, vsol, vtok, user) and uses the TOKEN reserve r[7];
vtok comes from each tx's own post token balance (+ the measured 73e12 offset), so every row is independent; where the
collector has no balance for a tx the reserve is rolled from the previous row. vsol = k_curve / vtok with k_curve = V0 * T0.
Agreement with the engine's presend_live_tape rows (ground truth) is printed, not assumed.
Out: /home/moiz/sniper-data/custom37/tape_<run>.pkl {"tapes": {(ses, w): rows}, "maxi": {...}, "end_slot": int}
usage: adapt_tape.py r38 r39 r40
"""
import sys, pickle, collections

SRC = "/home/moiz/sniper-data/replay4"
D = "/home/moiz/sniper-data/custom37"
LO, HI = 3, 120            # trigger slot - LO .. + HI, as c2_tape


def build(run, conv="post"):
    """conv kept for the pre/post check; the direct reserve is the post-state (MEASURED)."""
    TP = pickle.load(open(f"{SRC}/tape_{run}.pkl", "rb"))
    X = pickle.load(open(f"{D}/win_{run}.pkl", "rb"))
    trades, maxi = TP["trades"], TP["maxi"]
    tapes = {}
    miss_trig = 0
    for W in X["wins"]:
        tg = W["trig"]; s0 = tg["slot"]
        rows_in = trades.get(W["mint"]) or []
        sel = [r for r in rows_in if s0 - LO <= r[0] <= s0 + HI]
        if not sel:
            continue
        # j = position of the trade among the trade events of the same tx
        byj = collections.defaultdict(int); out = []
        for tr in sel:
            s, i, buy, sol, tok, user = tr[:6]
            vt = tr[6] if len(tr) > 6 else None
            j = byj[(s, i)]; byj[(s, i)] += 1
            out.append([s, i, j, buy, sol, tok, 0, vt, user])
        k0 = next((n for n, r in enumerate(out) if (r[0], r[1], r[2]) == (s0, tg["idx"], tg.get("j", 0))), None)
        if k0 is None:
            miss_trig += 1
            continue
        V0, T0 = float(tg["vsol"]), float(tg["vtok"])
        k_curve = V0 * T0
        if out[k0][7] is None:
            out[k0][7] = T0
        # forward: keep each row's own reserve; roll only across gaps
        T = out[k0][7]
        for r in out[k0:]:
            if r[7] is None:
                T = T - r[5] if r[3] else T + r[5]
                r[7] = T
            else:
                T = r[7]
            r[6] = k_curve / T if T else 0
        # backward from the trigger, same rule
        T = out[k0][7]
        for r in reversed(out[:k0]):
            if r[7] is None:
                T = T + r[5] if r[3] else T - r[5]
                r[7] = T
            else:
                T = r[7]
            r[6] = k_curve / T if T else 0
        tapes[(W["ses"], W["w"])] = [tuple(r) for r in out]
    return tapes, maxi, miss_trig, X


def score(tapes, X):
    """agreement with the engine's own presend_live_tape rows"""
    ok = bad = 0
    for W in X["wins"]:
        tp = tapes.get((W["ses"], W["w"]))
        if not tp:
            continue
        idx = {(r[0], r[1], r[2]): r for r in tp}
        for (s, i, j, t, user, buy, sol, tok, vsol, vtok) in (W.get("ptape") or []):
            r = idx.get((s, i, j))
            if r is None:
                continue
            if abs(r[7] - vtok) <= max(2.0, vtok * 1e-9):
                ok += 1
            else:
                bad += 1
    return ok, bad


if __name__ == "__main__":
    for run in (sys.argv[1:] or ["r38", "r39", "r40"]):
        tapes, maxi, miss, X = build(run)
        ok, bad = score(tapes, X)
        tot = sum(len(t) for t in tapes.values())
        nogap = sum(1 for t in tapes.values() for r in t if r[7] is not None)
        print(f"{run}: windows {len(tapes)}, trigger not in tape {miss}, rows {tot}, "
              f"ptape match {ok} / {ok + bad} ({100 * ok / max(ok + bad, 1):.1f}%)", flush=True)
        conv = "post"
        end = max((max(r[0] for r in t) for t in tapes.values() if t), default=0)
        pickle.dump({"tapes": tapes, "maxi": maxi, "end_slot": end}, open(f"{D}/tape_{run}.pkl", "wb"))
        print(f"{run}: wrote tape_{run}.pkl with conv={conv} ({len(tapes)} windows)", flush=True)
