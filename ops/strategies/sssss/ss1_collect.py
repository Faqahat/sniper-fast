#!/usr/bin/env python3
# sssssDdM (read-only): every bonding-curve trade of the wallet in R1-R4 (day arrays patterns/day_R*.npz), paired into trips,
# with the token state BEFORE each buy, the trigger candidates (last non-fleet trade before its buy; largest non-fleet buy /
# sell in the same slot and previous 3 slots), speed (slot / tx-index / modelled arrival-ms after the trigger), what
# preceded each sell, the peak during the hold, and FLEET context: the operator runs 4 vanity "sssss" wallets
# (sssssDdM, ssssswdk, sssssCUP, sssssyv2) - did a sibling trade this token right before / while it held?
# Adapted from bukp/bk1_collect.py (not modified).  -> /home/moiz/sniper-data/strategies/sssss/trips_<run>.json
import sys, os, json, zlib, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p4_eval as E
OUT = "/home/moiz/sniper-data/strategies/sssss"
W = "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"; UID = zlib.crc32(W.encode())
SIBS = {"wdk": "ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E", "CUP": "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi", "yv2": "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ"}
SUID = {zlib.crc32(v.encode()): k for k, v in SIBS.items()}
FLEET = np.array([UID] + list(SUID), np.int64)
WTN = {0: "other", 1: "creator", 2: "insider", 3: "new", 4: "bot", **{10 + k: f"F{k}" for k in range(1, 11)}}
SF = ("age", "curve", "ath_r", "from_bun", "ret1", "ret3", "ret10", "ret30", "ret100", "dd3", "dd10", "dd30", "net3", "net10", "net30", "nb1", "ns1", "maxb1", "maxs1",
      "nb3", "ns3", "maxb3", "maxs3", "nb10", "ns10", "maxb10", "maxs10", "nw10", "nw30", "ntr", "nwal", "peak", "dev_sold", "ins_sold", "nbot_hold", "fam_hold", "quiet",
      "fam_b10", "fam_s10", "bot_b10", "fresh_b10", "bigb3", "bigs3", "bigb10", "bigs10")

def who(d, j):
    u = int(d["uid"][j])
    if u == UID: return "ME"
    if u in SUID: return "SIB_" + SUID[u]
    return WTN.get(int(d["wt"][j]), "other")

def tr(d, j, s0, i0, a0):
    F = d["F"]; FI = d["FI"]
    return dict(k=int(j), side="B" if d["buy"][j] else "S", sol=round(float(d["sol"][j]) / 1e9, 4), move=round(float(F[j, FI["move"]]), 2), who=who(d, j),
                bid=int(d["bid"][j]), dslot=int(s0 - d["s"][j]), didx=int(i0 - d["i"][j]) if d["s"][j] == s0 else None, dms=round(float(a0 - d["arr"][j]), 1))

def collect(run):
    d = E.DAYS[run]; F = d["F"]; FI = d["FI"]; M = d["M"]
    isfleet = np.isin(d["uid"], FLEET)
    me = np.flatnonzero(d["uid"] == UID)
    by_tok = collections.defaultdict(list)
    for k in me: by_tok[int(d["tok"][k])].append(int(k))
    trips = []
    for t, ks in by_tok.items():
        pos = 0.0; peak = 0.0; cur = None
        for k in ks:
            buy = bool(d["buy"][k]); tok = float(d["tokn"][k])
            if buy:
                if cur is None: cur = dict(tok=t, mint=M["meta"][t]["m"], buys=[], sells=[], k0=k)
                cur["buys"].append(k); pos += tok; peak = max(peak, pos)
            else:
                if cur is None: continue
                cur["sells"].append(k); pos -= tok
                if pos <= 0.01 * peak: trips.append(cur); cur = None; pos = 0.0; peak = 0.0
        if cur is not None: cur["open"] = True; trips.append(cur)
    out = []
    for tp in trips:
        k0 = tp["k0"]; a = k0 - int(F[k0, FI["ntr"]]) + 1; end = int(d["tend"][k0])
        s0 = int(d["s"][k0]); i0 = int(d["i"][k0]); a0 = float(d["arr"][k0])
        # trigger candidates (non-fleet trades only)
        last = None; j = k0 - 1
        while j >= a:
            if not isfleet[j]: last = tr(d, j, s0, i0, a0); break
            j -= 1
        bs = bb = None; j = k0 - 1; same = []
        while j >= a and d["s"][j] >= s0 - 3:
            if not isfleet[j]:
                c = tr(d, j, s0, i0, a0)
                if d["s"][j] == s0: same.append(c)
                if d["buy"][j]:
                    if bb is None or c["sol"] > bb["sol"]: bb = c
                elif bs is None or c["sol"] > bs["sol"]: bs = c
            j -= 1
        # fleet: sibling trades of this token in [s0-50, s0] before its buy, and sibling position at entry
        fl_before = []; j = k0 - 1
        while j >= a and d["s"][j] >= s0 - 50:
            if isfleet[j] and d["uid"][j] != UID: fl_before.append(tr(d, j, s0, i0, a0))
            j -= 1
        sibpos = collections.Counter()
        for q in (a + np.flatnonzero(isfleet[a:k0] & (d["uid"][a:k0] != UID))).tolist():
            u = int(d["uid"][q]); sibpos[SUID[u]] += float(d["tokn"][q]) * (1 if d["buy"][q] else -1)
        pre = k0 - 1 if k0 > a else None
        st = {f: round(float(F[pre, FI[f]]), 4) for f in SF} if pre is not None else {}
        for f in ("hour", "theme", "x", "eff", "fun", "rw", "cpy", "red"): st[f] = int(F[k0, FI[f]])
        st["wt_me"] = int(d["wt"][k0])
        buys = [dict(k=k, slot=int(d["s"][k]), idx=int(d["i"][k]), sol=round(float(d["sol"][k]) / 1e9, 4), tok=float(d["tokn"][k]), fr=float(d["fr"][k]),
                     vsol=float(d["vsol"][k]), vtok=float(d["vtok"][k]), arr=float(d["arr"][k]), move=round(float(F[k, FI["move"]]), 2)) for k in tp["buys"]]
        sells = []
        for k in tp["sells"]:
            sk = int(d["s"][k]); ik = int(d["i"][k]); ak = float(d["arr"][k])
            p = k - 1
            while p >= a and d["uid"][p] == UID: p -= 1
            prev = tr(d, p, sk, ik, ak) if p >= a else None
            j = k - 1; mb = 0.0; ms = 0.0; nso = 0; sib_s = []
            while j >= a and d["s"][j] >= sk - 3:
                if not isfleet[j]:
                    if d["buy"][j]: mb = max(mb, float(d["sol"][j]) / 1e9)
                    else: ms = max(ms, float(d["sol"][j]) / 1e9); nso += 1
                elif d["uid"][j] != UID: sib_s.append(tr(d, j, sk, ik, ak))
                j -= 1
            # the last 6 non-own trades before the sell (tape)
            tape = []; j = k - 1
            while j >= max(a, k0 + 1) and len(tape) < 6:
                if d["uid"][j] != UID: tape.append(tr(d, j, sk, ik, ak))
                j -= 1
            sells.append(dict(k=k, slot=sk, idx=ik, arr=ak, sol=round(float(d["sol"][k]) / 1e9, 4), tok=float(d["tokn"][k]), fr=float(d["fr"][k]),
                              vsol=float(d["vsol"][k]), vtok=float(d["vtok"][k]), prev=prev, maxb3=round(mb, 3), maxs3=round(ms, 3), ns3=nso, sib3=sib_s, tape=tape))
        cost = sum(b["sol"] * (1 + b["fr"]) for b in buys); got = sum(s["sol"] * (1 - s["fr"]) for s in sells)
        tb = sum(b["tok"] for b in buys); ts = sum(s["tok"] for s in sells)
        grad = bool(d["vsol"][end - 1] >= 113e9)
        p_in = sum(b["sol"] for b in buys) * 1e9 / tb if tb else 0
        k_end = sells[-1]["k"] if sells else end - 1
        seg = slice(k0, k_end + 1); px = d["vsol"][seg] / d["vtok"][seg]
        pk = float(px.max()) / p_in if p_in else 0; mn = float(px.min()) / p_in if p_in else 0
        # path stats while held: other-wallet buy / sell SOL, count of trades, time to the peak
        oth = ~isfleet[k0 + 1:k_end]
        bsol = float((d["sol"][k0 + 1:k_end] * (d["buy"][k0 + 1:k_end] == 1) * oth).sum()) / 1e9
        ssol = float((d["sol"][k0 + 1:k_end] * (d["buy"][k0 + 1:k_end] == 0) * oth).sum()) / 1e9
        kpk = k0 + int(np.argmax(px))
        # price 3 / 10 / 30 / 100 slots after entry (on the real tape) vs its fill
        after = {}
        for w in (1, 3, 10, 30, 100, 300):
            q = int(np.searchsorted(d["s"][k0:end], s0 + w, side="right")) - 1 + k0
            after[w] = round(float(d["vsol"][q] / d["vtok"][q]) / p_in, 4) if p_in else None
        out.append(dict(run=run, mint=tp["mint"], tok=tp["tok"], k0=k0, slot=s0, idx=i0, arr=a0, bt=int(d["bt"][k0]), state=st, last=last, same=same[:12],
                        trig_sell=bs, trig_buy=bb, fleet_before=fl_before[:10], sibpos={k: round(v / 1e6, 1) for k, v in sibpos.items() if abs(v) > 1e6},
                        buys=buys, sells=sells, nb=len(buys), ns=len(sells), cost=round(cost, 5), got=round(got, 5),
                        closed=ts >= 0.99 * tb, grad=grad, pnl_curve=round(got - cost, 5) if ts >= 0.99 * tb else None,
                        hold=(sells[-1]["slot"] - s0) if sells else None, first_sell=(sells[0]["slot"] - s0) if sells else None,
                        exit_mult=round(((sells[-1]["vsol"] + sells[-1]["sol"] * 1e9) / (sells[-1]["vtok"] - sells[-1]["tok"])) / p_in, 4) if sells and p_in else None,
                        peak_mult=round(pk, 4), min_mult=round(mn, 4), peak_slot=int(d["s"][kpk] - s0), oth_buy_sol=round(bsol, 3), oth_sell_sol=round(ssol, 3),
                        n_path=int(oth.sum()), after=after, p_in=p_in))
    out.sort(key=lambda t: t["arr"])
    json.dump(out, open(f"{OUT}/trips_{run}.json", "w"))
    # fleet activity summary for this day: trades / buys per sibling
    fs = {("ME" if u == UID else SUID[int(u)]): int((d["uid"] == u).sum()) for u in FLEET}
    return out, fs

if __name__ == "__main__":
    runs = sys.argv[1:] or ["R1", "R2", "R3", "R4"]
    for run in runs:
        E.load([run])
        T, fs = collect(run)
        cl = [t for t in T if t["closed"]]
        print(f"{run}: {len(T)} trips, closed {len(cl)}, graduated-open {sum(1 for t in T if not t['closed'] and t['grad'])}, curve P&L (closed, excl. tx fees) "
              f"{sum(t['pnl_curve'] for t in cl):+.2f} SOL; fleet trades in day arrays {fs}", flush=True)
        del E.DAYS[run]
