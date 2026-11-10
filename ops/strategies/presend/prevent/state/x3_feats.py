#!/usr/bin/env python3
"""STATE step 3 [MEASURED from the decoded tape, causal]: token state/flow features at every decision point, and the first slot of each
in-window event (for stop rules).
Decision points:
  live T2 window        cutoff = the trigger trade (its whole tx included)          s0 = trigger slot
  live re-arm window    cutoff = every trade before the arm slot (dump + 3)          s0 = arm slot - 1
  shadow T2 arm (paper) as live T2 (shadow-only runs)
  obs re-arm window     as live re-arm (r36/r37/r38 observatory)
No identity features (no wallet lists) except the generic follower cohort count (ops/overnight/sel/cohort_train.json), as QUIET.
Out: /home/it/sniper-data/prevent/state/feats.pkl  {key: {feat...}, ...} with keys ("L", run, seg, w) / ("S", run, seg, w) / ("O", run, i)"""
import json, pickle, time, collections, sys
import numpy as np
D = "/home/it/sniper-data/prevent/state"
COHORT = "/home/it/sniper-data/overnight/sel/cohort_train.json"
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
SUP = 1e15; P0 = 30e9 / 1.073e15
t0 = time.time()


def load():
    A = dict(np.load(f"{D}/tape.npz")); I = json.load(open(f"{D}/tape_ids.json"))
    mid = {m: k for k, m in enumerate(I["mints"])}; uid = {u: k for k, u in enumerate(I["users"])}
    lo = np.searchsorted(A["mint"], np.arange(len(I["mints"]) + 1))
    return A, I, mid, uid, lo


class Ctx:
    def __init__(self):
        self.A, self.I, self.mid, self.uid, self.lo = load()
        self.ours = {self.uid[u] for u in OURS if u in self.uid}
        self.coh = {self.uid[u] for u in json.load(open(COHORT)) if u in self.uid}

    def rows(self, mint):
        k = self.mid.get(mint)
        if k is None: return None
        a, b = self.lo[k], self.lo[k + 1]
        if a == b: return None
        A = self.A
        return {f: A[f][a:b] for f in ("slot", "idx", "j", "buy", "sol", "tok", "vsol", "vtok", "user", "signer")}


def cut_index(R, slot, idx=None):
    """number of rows at or before (slot, idx) [idx None = every row with slot < slot]"""
    s = R["slot"]
    if idx is None: return int(np.searchsorted(s, slot, side="left"))
    a = int(np.searchsorted(s, slot, side="left")); b = int(np.searchsorted(s, slot, side="right"))
    return a + int(np.searchsorted(R["idx"][a:b], idx, side="right"))


def feats(C, R, n, s_dec, who, ours, coh, events_to=None, wh_is_seller=False):
    """state at the cutoff (rows [0, n)), s_dec = the decision slot (the last slot whose trades are known), who = the whale / dumper"""
    f = {}
    if n <= 0: return {"ok": False}
    S = R["slot"][:n]; B = R["buy"][:n].astype(bool); SOL = R["sol"][:n].astype(np.float64); TOK = R["tok"][:n].astype(np.float64)
    VS = R["vsol"][:n].astype(np.float64); VT = R["vtok"][:n].astype(np.float64); U = R["user"][:n]
    notours = ~np.isin(U, list(ours)) if ours else np.ones(n, bool)
    p = VS / np.maximum(VT, 1.0); pnow = p[-1]
    f["ok"] = True; f["n_tr"] = int(notours.sum()); f["vsol"] = VS[-1] / 1e9
    f["ret_launch"] = pnow / P0 - 1.0
    pm = np.maximum.accumulate(p); f["dd_max"] = 1.0 - pnow / pm[-1]
    f["maxdd_hist"] = float(np.max(1.0 - p / pm))
    first = int(S[0]); f["age_tape"] = int(s_dec - first)
    # flow windows
    for w in (2, 5, 20, 50):
        m = (S > s_dec - w) & notours
        mb = m & B; ms = m & ~B
        f[f"nb{w}"] = int(mb.sum()); f[f"ns{w}"] = int(ms.sum())
        f[f"bsol{w}"] = float(SOL[mb].sum() / 1e9); f[f"ssol{w}"] = float(SOL[ms].sum() / 1e9)
        f[f"nbuyers{w}"] = len(set(U[mb].tolist())); f[f"nsellers{w}"] = len(set(U[ms].tolist()))
        f[f"net{w}"] = f[f"bsol{w}"] - f[f"ssol{w}"]
        # price change over the window
        k = int(np.searchsorted(S, s_dec - w + 1, side="left"))
        pref = p[k - 1] if k > 0 else P0
        f[f"ret{w}"] = pnow / pref - 1.0
        big = ms & (TOK >= 0.01 * SUP)
        f[f"nsell1p{w}"] = int(big.sum())
        f[f"maxsellpct{w}"] = float(TOK[ms].max() / SUP * 100) if ms.any() else 0.0
    sells = ~B & notours
    f["ndump3"] = int((sells & (TOK >= 0.03 * SUP)).sum()); f["ndump6"] = int((sells & (TOK >= 0.06 * SUP)).sum())
    f["nsell1sol"] = int((sells & (SOL >= 1e9)).sum())
    f["sell_sol_tot"] = float(SOL[sells].sum() / 1e9); f["buy_sol_tot"] = float(SOL[B & notours].sum() / 1e9)
    f["since_last"] = int(s_dec - S[-2]) if n >= 2 else 9999
    # balances + cost basis
    bal = collections.defaultdict(float); cost = collections.defaultdict(float); bought = collections.defaultdict(float); peak = collections.defaultdict(float)
    sold = collections.defaultdict(float)
    for u, b, sol, tok in zip(U.tolist(), B.tolist(), SOL.tolist(), TOK.tolist()):
        if b: bal[u] += tok; cost[u] += sol; bought[u] += tok
        else: bal[u] -= tok; sold[u] += tok
        if bal[u] > peak[u]: peak[u] = bal[u]
    hold = {u: v for u, v in bal.items() if v > 1e9 and u not in ours}
    pcts = sorted((v / SUP * 100 for v in hold.values()), reverse=True)
    f["top1"] = pcts[0] if pcts else 0.0; f["top3"] = sum(pcts[:3]); f["top10"] = sum(pcts[:10])
    f["nh1"] = sum(1 for x in pcts if x >= 1); f["nh3"] = sum(1 for x in pcts if x >= 3); f["nh6"] = sum(1 for x in pcts if x >= 6)
    f["n_holders"] = len(pcts)
    oth = [(u, v / SUP * 100) for u, v in hold.items() if u != who]
    f["oth_top1"] = max((x for _, x in oth), default=0.0); f["oth_sum3"] = sum(x for _, x in oth if x >= 3); f["oth_n3"] = sum(1 for _, x in oth if x >= 3)
    f["oth_n6"] = sum(1 for _, x in oth if x >= 6); f["oth_sum1"] = sum(x for _, x in oth if x >= 1)
    # profit overhang (holders' average entry vs now)
    o25 = o50 = o100 = 0.0; wret = 0.0; wsum = 0.0
    for u, v in hold.items():
        if bought.get(u, 0) <= 0: continue
        ent = cost[u] / bought[u]; r = pnow / ent - 1.0; x = v / SUP * 100
        if r >= 0.25: o25 += x
        if r >= 0.5: o50 += x
        if r >= 1.0: o100 += x
        wret += r * x; wsum += x
    f["ovh25"] = o25; f["ovh50"] = o50; f["ovh100"] = o100; f["hret"] = wret / wsum if wsum > 0 else 0.0
    # big holders' (>= 3 %, not the whale) profit
    f["oth3_ovh25"] = sum(v / SUP * 100 for u, v in hold.items() if u != who and v >= 0.03 * SUP and bought.get(u, 0) > 0 and pnow / (cost[u] / bought[u]) - 1 >= 0.25)
    # whale / dumper
    wb = bal.get(who, 0.0); f["who_pct"] = wb / SUP * 100
    if bought.get(who, 0) > 0: f["who_ret"] = pnow / (cost[who] / bought[who]) - 1.0
    else: f["who_ret"] = 0.0
    wm = (U == who)
    f["who_nbuy"] = int((wm & B).sum()); f["who_nsell"] = int((wm & ~B).sum())
    f["who_first_age"] = int(s_dec - S[np.argmax(wm)]) if wm.any() else -1
    f["who_sold_frac"] = sold.get(who, 0.0) / peak[who] if peak.get(who, 0) > 0 else 0.0
    # creator proxy = the first trade's user; launch cohort = other buyers in the first 3 slots
    cre = int(U[0]); f["cre_pct"] = max(bal.get(cre, 0.0), 0.0) / SUP * 100
    f["cre_sold"] = sold.get(cre, 0.0) / peak[cre] if peak.get(cre, 0) > 0 else 0.0
    f["cre_is_who"] = int(cre == who)
    lm = (S <= first + 2) & B & (U != cre) & notours
    lc = set(U[lm].tolist())
    lc_peak = sum(peak.get(u, 0.0) for u in lc); lc_now = sum(max(bal.get(u, 0.0), 0.0) for u in lc)
    f["lc_n"] = len(lc); f["lc_pct"] = lc_now / SUP * 100; f["lc_sold_frac"] = 1.0 - lc_now / lc_peak if lc_peak > 0 else 0.0
    f["lc_n_hold"] = sum(1 for u in lc if bal.get(u, 0.0) > 1e9)
    # create-slot cohort only
    cs = set(U[(S == first) & B & (U != cre) & notours].tolist())
    f["cs_pct"] = sum(max(bal.get(u, 0.0), 0.0) for u in cs) / SUP * 100; f["cs_n"] = len(cs)
    # same-signer groups (only where the tape has signers: r37/r38): wallets sharing a signer with >= 2 members, their holdings
    sg = R["signer"][:n]
    if (sg >= 0).any():
        grp = collections.defaultdict(set)
        for u, g in zip(U.tolist(), sg.tolist()):
            if g >= 0 and g != u: grp[g].add(u)
        mem = set().union(*[v for v in grp.values() if len(v) >= 2]) if grp else set()
        f["sg_pct"] = sum(max(bal.get(u, 0.0), 0.0) for u in mem) / SUP * 100; f["sg_n"] = len(mem)
    else: f["sg_pct"] = None; f["sg_n"] = None
    # follower cohort
    us = set(U.tolist())
    f["coh_tr"] = len(us & coh); f["coh_hold_n"] = sum(1 for u in us & coh if bal.get(u, 0) > 1e9)
    return f


def events(C, R, n, s0, who, ours, s_end, base_bal=None):
    """first slot (>= s0) of each in-window event from the trades after the cutoff (rows >= n) through s_end; None = never"""
    E = {}
    S = R["slot"]; m = len(S)
    if n >= m: return E
    B = R["buy"]; SOL = R["sol"]; TOK = R["tok"]; U = R["user"]; VS = R["vsol"]; VT = R["vtok"]
    p_arm = float(VS[n - 1]) / max(float(VT[n - 1]), 1.0) if n > 0 else P0
    bal = collections.defaultdict(float)
    for k in range(n):
        u = int(U[k]); bal[u] += float(TOK[k]) if B[k] else -float(TOK[k])
    lc_first = int(S[0]); cre = int(U[0])
    lc = set(int(U[k]) for k in range(n) if S[k] <= lc_first + 2 and B[k] and U[k] != cre)
    big0 = {u for u, v in bal.items() if v >= 0.03 * SUP and u not in ours and u != who}
    cum_s = 0.0; sellers = set(); lc_sold = 0.0; cum_sp = 0.0
    def setE(name, s):
        if name not in E: E[name] = s
    for k in range(n, m):
        s = int(S[k])
        if s > s_end: break
        u = int(U[k])
        if u in ours: continue
        b = bool(B[k]); sol = float(SOL[k]); tok = float(TOK[k])
        bal[u] += tok if b else -tok
        p = float(VS[k]) / max(float(VT[k]), 1.0)
        if not b:
            cum_s += sol; sellers.add(u)
            if tok >= 0.03 * SUP: setE("sell3", s)
            if tok >= 0.06 * SUP: setE("sell6", s)
            if sol >= 1e9: setE("sell1sol", s)
            if sol >= 2e9: setE("sell2sol", s)
            if u == who: setE("who_sell", s)
            if u == who and tok >= 0.02 * SUP: setE("who_sell2", s)
            if u in big0: setE("bigh_sell", s)
            if u in lc:
                lc_sold += tok
                if lc_sold >= 0.02 * SUP: setE("lc_sell2", s)
                if lc_sold >= 0.05 * SUP: setE("lc_sell5", s)
            if cum_s >= 2e9: setE("cums2", s)
            if cum_s >= 4e9: setE("cums4", s)
            if len(sellers) >= 3: setE("nsell3", s)
            if len(sellers) >= 5: setE("nsell5", s)
            if p <= p_arm * 0.95: setE("drop5", s)
            if p <= p_arm * 0.92: setE("drop8", s)
        else:
            if bal[u] >= 0.06 * SUP and u != who: setE("newwhale", s)
            if p >= p_arm * 1.10: setE("up10", s)
    return E


def main():
    C = Ctx(); print("tape loaded", f"{time.time()-t0:.0f}s", flush=True)
    R = pickle.load(open(f"{D}/windows.pkl", "rb")); O = pickle.load(open(f"{D}/obs_rearm.pkl", "rb"))
    out = {}; miss = collections.Counter(); done = 0
    for rk, r in R.items():
        for x in r["wins"]:
            T = C.rows(x["mint"])
            if T is None: miss["L_nomint"] += 1; continue
            who = C.uid.get(x["who"], -1)
            if x["kind"] == "rearm":
                s0 = (x.get("arm_slot") or x["slot"] + 3) - 1; n = cut_index(T, s0 + 1)
            else:
                s0 = x["slot"]; n = cut_index(T, x["slot"], x["idx"])
                # the trigger must be in the tape
                if n == 0 or not (int(T["slot"][n - 1]) == x["slot"] and int(T["idx"][n - 1]) == x["idx"]): miss["L_notrig"] += 1
            f = feats(C, T, n, s0, who, C.ours, C.coh)
            if not f.get("ok"): miss["L_nohist"] += 1; continue
            s_end = max((x.get("dis") or {}).get("slot") or 0, x.get("en_slot") or 0, s0 + 25) + 2
            f["ev"] = events(C, T, n, s0, who, C.ours, s_end)
            # fill-time state (descriptive): the trade just before our fill in its slot, the dumper's remaining %, sells in the hold
            if x["fills"]:
                fl = x["fills"][0]; nf = cut_index(T, fl["slot"], (fl["idx"] or 0) - 1) if fl.get("idx") is not None else cut_index(T, fl["slot"])
                if nf > 0:
                    u = int(T["user"][nf - 1]); bal = 0.0
                    for k in range(nf):
                        if int(T["user"][k]) == u: bal += float(T["tok"][k]) if T["buy"][k] else -float(T["tok"][k])
                    f["fill_prev_sell"] = (not bool(T["buy"][nf - 1])); f["fill_prev_pct"] = float(T["tok"][nf - 1]) / SUP * 100
                    f["fill_prev_left"] = bal / SUP * 100; f["fill_prev_is_who"] = int(u == who)
                hm = (T["slot"] >= fl["slot"]) & (T["slot"] <= fl["slot"] + 2) & (T["buy"] == 0) & ~np.isin(T["user"], list(C.ours))
                hm[:nf] = False
                f["hold_sell_sol"] = float(T["sol"][hm].sum() / 1e9); f["hold_max_sell"] = float(T["sol"][hm].max() / 1e9) if hm.any() else 0.0
            out[("L", rk, x["seg"], x["w"])] = f; done += 1
        if not r["live"]:
            for x in r["shadow"]:
                T = C.rows(x["mint"])
                if T is None: miss["S_nomint"] += 1; continue
                who = C.uid.get(x["who"], -1); n = cut_index(T, x["slot"], x["idx"])
                f = feats(C, T, n, x["slot"], who, C.ours, C.coh)
                if not f.get("ok"): miss["S_nohist"] += 1; continue
                out[("S", rk, x["seg"], x["w"])] = f; done += 1
        print(rk, "done", done, dict(miss), f"{time.time()-t0:.0f}s", flush=True)
    for run, W in O.items():
        for i, x in enumerate(W):
            T = C.rows(x["mint"])
            if T is None: miss["O_nomint"] += 1; continue
            dm = x["dump"]; who = C.uid.get(dm["seller"], -1)
            arm = (x.get("arm") or {}).get("slot") or dm["slot"] + 3
            s0 = arm - 1; n = cut_index(T, s0 + 1)
            f = feats(C, T, n, s0, who, C.ours, C.coh)
            if not f.get("ok"): miss["O_nohist"] += 1; continue
            f["ev"] = events(C, T, n, s0, who, C.ours, (x.get("en_slot") or s0 + 21) + 2)
            out[("O", run, i)] = f; done += 1
        print("obs", run, "done", done, dict(miss), f"{time.time()-t0:.0f}s", flush=True)
    pickle.dump(out, open(f"{D}/feats.pkl", "wb"))
    print("saved", len(out), dict(miss), f"{time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
