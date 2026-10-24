#!/usr/bin/env python3
# BUkpShoE (read-only): every bonding-curve trade of the wallet in R1-R3 (+R4 when built), paired into trips, with the token
# state BEFORE each buy, the most likely trigger (largest other-wallet trade in the same slot before it / the previous
# 3 slots), speed (slot / tx-index delay after the trigger), and what preceded each sell. Uses the pattern-search day
# arrays (patterns/day_R*.npz: causal features per trade, wallet types, bot IDs, uid = crc32(wallet)).
# -> /home/moiz/sniper-data/strategies/bukp/trips_<run>.json
import sys, os, json, zlib, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p4_eval as E
OUT = "/home/moiz/sniper-data/strategies/bukp"
W = "BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP"; UID = zlib.crc32(W.encode())
WTN = {0: "other", 1: "creator", 2: "insider", 3: "new", 4: "bot", **{10 + k: f"F{k}" for k in range(1, 11)}}

def collect(run):
    d = E.DAYS[run]; F = d["F"]; FI = d["FI"]; M = d["M"]
    me = np.flatnonzero(d["uid"] == UID)
    by_tok = collections.defaultdict(list)
    for k in me: by_tok[int(d["tok"][k])].append(int(k))
    trips = []
    for t, ks in by_tok.items():
        pos = 0.0; peak = 0.0; cur = None
        for k in ks:
            buy = bool(d["buy"][k]); sol = float(d["sol"][k]) / 1e9; tok = float(d["tokn"][k]); fr = float(d["fr"][k])
            if buy:
                if cur is None:
                    cur = dict(run=run, tok=t, mint=M["meta"][t]["m"], buys=[], sells=[], k0=k)
                cur["buys"].append(k); pos += tok; peak = max(peak, pos)
            else:
                if cur is None: continue
                cur["sells"].append(k); pos -= tok
                if pos <= 0.01 * peak:
                    trips.append(cur); cur = None; pos = 0.0; peak = 0.0
        if cur is not None: cur["open"] = True; trips.append(cur)
    out = []
    for tp in trips:
        k0 = tp["k0"]; a = k0 - int(F[k0, FI["ntr"]]) + 1                 # first index of the token
        s0 = int(d["s"][k0]); i0 = int(d["i"][k0])
        # trigger: largest other-wallet trade in the window [s0-3, s0] before k0 (sells and buys separately)
        bs = None; bb = None; j = k0 - 1
        while j >= a and d["s"][j] >= s0 - 3:
            if d["uid"][j] != UID:
                c = dict(k=j, sol=round(float(d["sol"][j]) / 1e9, 3), move=round(float(F[j, FI["move"]]), 2), who=WTN.get(int(d["wt"][j]), "other"),
                         bid=int(d["bid"][j]), dslot=int(s0 - d["s"][j]), didx=int(i0 - d["i"][j]) if d["s"][j] == s0 else None)
                if d["buy"][j]:
                    if bb is None or c["sol"] > bb["sol"]: bb = c
                elif bs is None or c["sol"] > bs["sol"]: bs = c
            j -= 1
        pre = k0 - 1 if k0 > a else None
        st = {f: round(float(F[pre, FI[f]]), 3) for f in ("age", "curve", "ath_r", "ret10", "ret30", "ret100", "dd3", "dd10", "net3", "net10", "nb10", "ns10", "nw30", "ntr", "nwal", "peak", "dev_sold", "ins_sold", "nbot_hold")} if pre is not None else {}
        st["hour"] = int(F[k0, FI["hour"]]); st["theme"] = int(F[k0, FI["theme"]]); st["x"] = int(F[k0, FI["x"]]); st["eff"] = int(F[k0, FI["eff"]])
        st["quiet"] = int(F[k0, FI["quiet"]])
        buys = [dict(k=k, slot=int(d["s"][k]), idx=int(d["i"][k]), sol=round(float(d["sol"][k]) / 1e9, 4), tok=float(d["tokn"][k]), fr=float(d["fr"][k]),
                     vsol=float(d["vsol"][k]), vtok=float(d["vtok"][k]), arr=float(d["arr"][k])) for k in tp["buys"]]
        sells = []
        for k in tp["sells"]:
            p = k - 1
            prev = dict(side="B" if d["buy"][p] else "S", sol=round(float(d["sol"][p]) / 1e9, 3), who=WTN.get(int(d["wt"][p]), "other"), bid=int(d["bid"][p]),
                        dslot=int(d["s"][k] - d["s"][p]), mine=bool(d["uid"][p] == UID)) if p >= a else None
            # biggest other buy / sell in the 3 slots before this sell
            j = k - 1; mb = 0.0; ms = 0.0
            while j >= a and d["s"][j] >= d["s"][k] - 3:
                if d["uid"][j] != UID:
                    if d["buy"][j]: mb = max(mb, float(d["sol"][j]) / 1e9)
                    else: ms = max(ms, float(d["sol"][j]) / 1e9)
                j -= 1
            sells.append(dict(k=k, slot=int(d["s"][k]), idx=int(d["i"][k]), sol=round(float(d["sol"][k]) / 1e9, 4), tok=float(d["tokn"][k]), fr=float(d["fr"][k]),
                              vsol=float(d["vsol"][k]), vtok=float(d["vtok"][k]), prev=prev, maxb3=round(mb, 3), maxs3=round(ms, 3)))
        cost = sum(b["sol"] * (1 + b["fr"]) for b in buys); got = sum(s["sol"] * (1 - s["fr"]) for s in sells)
        tb = sum(b["tok"] for b in buys); ts = sum(s["tok"] for s in sells)
        grad = bool(d["vsol"][int(d["tend"][k0]) - 1] >= 113e9)
        p_in = sum(b["sol"] for b in buys) * 1e9 / tb if tb else 0
        # peak price during the hold (after entry until the last sell or token end)
        k_end = sells[-1]["k"] if sells else int(d["tend"][k0]) - 1
        seg = slice(k0, k_end + 1); pk = float((d["vsol"][seg] / d["vtok"][seg]).max()) / p_in if p_in else 0
        out.append(dict(run=run, mint=tp["mint"], tok=tp["tok"], k0=k0, slot=s0, idx=i0, bt=int(d["bt"][k0]), state=st, trig_sell=bs, trig_buy=bb,
                        buys=buys, sells=sells, nb=len(buys), ns=len(sells), cost=round(cost, 5), got=round(got, 5),
                        closed=ts >= 0.99 * tb, grad=grad, pnl_curve=round(got - cost, 5) if ts >= 0.99 * tb else None,
                        hold=(sells[-1]["slot"] - s0) if sells else None, first_sell=(sells[0]["slot"] - s0) if sells else None,
                        exit_mult=round(((sells[-1]["vsol"] + sells[-1]["sol"] * 1e9) / (sells[-1]["vtok"] - sells[-1]["tok"])) / p_in, 4) if sells and p_in else None,
                        peak_mult=round(pk, 4)))
    json.dump(out, open(f"{OUT}/trips_{run}.json", "w"))
    return out

if __name__ == "__main__":
    runs = sys.argv[1:] or ["R1", "R2", "R3"]
    E.load(runs)
    for run in runs:
        T = collect(run)
        cl = [t for t in T if t["closed"]]
        print(f"{run}: {len(T)} trips, closed {len(cl)}, graduated-open {sum(1 for t in T if not t['closed'] and t['grad'])}, curve P&L (closed, excl. tx fees) {sum(t['pnl_curve'] for t in cl):+.2f} SOL")
