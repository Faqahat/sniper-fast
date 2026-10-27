#!/usr/bin/env python3
"""PRESEND FILTER: the ARM features of a trigger (shared by the live windows, f1_features.py, and the chain-wide trigger events,
f3_chain_events.py). Only chain rows strictly before the trigger tx (chain order) plus the trigger itself; chain-wide histories only
from events complete before the trigger slot. See f1_features.py for the knowable-when rule."""
import json, collections, bisect
import numpy as np
from chainlib import B, SUPPLY

FROZEN = 1792948200          # follower-bot list: follow-buys before 10-25 22:00 PKT (before every studied run)


class Ctx:
    def __init__(self, C):
        self.C = C
        c = C.c
        self.E = E = np.load(f"{B}/events.npz")
        self.cr = json.load(open(f"{B}/creates.json"))
        coh = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
        self.cohid = {C.wid[w] for w in coh if w in C.wid}
        fw, fm, fbt = E["fo_w"], E["fo_m"], E["fo_bt"]
        m = fbt < FROZEN
        cnt = collections.Counter(fw[m].tolist())
        toks = collections.defaultdict(set)
        for w, mk in zip(fw[m].tolist(), fm[m].tolist()): toks[w].add(mk)
        nb_all = collections.Counter(c["user"][(c["buy"] == 1) & (c["bt"] < FROZEN)].tolist())
        self.fbots = {w for w, n in cnt.items() if n >= 20 and len(toks[w]) >= 10 and n / max(nb_all[w], 1) >= 0.2}
        self.cre_list = collections.defaultdict(list)
        for mint, x in self.cr.items(): self.cre_list[x["creator"]].append(x["slot"])
        for v in self.cre_list.values(): v.sort()
        self.ev_by_w = collections.defaultdict(list)
        for k in range(len(E["tr_w"])): self.ev_by_w[int(E["tr_w"][k])].append(k)
        self.du_by_w = collections.defaultdict(list)
        for k in range(len(E["du_w"])): self.du_by_w[int(E["du_w"][k])].append(k)
        self.du_by_m = collections.defaultdict(list)
        for k in range(len(E["du_m"])): self.du_by_m[int(E["du_m"][k])].append(k)


def arm_feats(X, rows, k, whale, mint, s0_, row):
    """X: Ctx; rows: the mint's chain rows; k: index of the trigger in rows; whale: wallet id; s0_: trigger slot. Fills row."""
    C = X.C; c = C.c; E = X.E; cr = X.cr; cohid = X.cohid; fbots = X.fbots; cre_list = X.cre_list
    ev_by_w = X.ev_by_w; du_by_w = X.du_by_w; du_by_m = X.du_by_m
    S, BUY, SOL, TOK, VS, VT, U, CUP, TIP, PROG, SIG = (c[q] for q in ("s", "buy", "sol", "tok", "vsol", "vtok", "user", "cup", "tip", "prog", "signer"))
    R0 = rows[:k]; Rt = rows[:k + 1]
    s0 = s0_
    sl = S[R0].astype(np.int64)
    info = cr.get(mint) or {}
    creator = C.wid.get(info.get("creator")); csigner = C.wid.get(info.get("user"))
    # ---- ARM: token history before the trigger
    row["n_tr"] = len(R0); row["n_buy"] = int(BUY[R0].sum()); row["n_sell"] = len(R0) - row["n_buy"]
    row["n_users"] = len(set(U[R0].tolist()))
    for L in (2, 5, 10, 20, 50):
        mm = sl >= s0 - L
        row[f"n_tr_{L}"] = int(mm.sum()); row[f"n_u_{L}"] = len(set(U[R0][mm].tolist()))
        row[f"vol_{L}"] = float(SOL[R0][mm].sum()) / 1e9
    row["vol"] = float(SOL[R0].sum()) / 1e9
    row["since_last"] = int(s0 - sl[-1]) if len(sl) else 9999
    vs = VS[Rt].astype(float); vt = VT[Rt].astype(float); p = vs / np.maximum(vt, 1)
    row["vmax"] = float(vs.max()) / 1e9; row["dd_peak"] = float(vs[-1] / vs.max())
    row["p_ret_20"] = float(p[-1] / p[:-1][sl >= s0 - 20][0]) if (sl >= s0 - 20).any() else 1.0
    # balances
    bal = collections.defaultdict(int)
    for w_, b_, t_ in zip(U[R0].tolist(), BUY[R0].tolist(), TOK[R0].tolist()): bal[w_] += t_ if b_ else -t_
    row["dev_hold"] = bal.get(creator, 0) / SUPPLY * 100 if creator is not None else -1
    row["dev_sold"] = int(any((not b) and w_ == creator for w_, b in zip(U[R0].tolist(), BUY[R0].tolist())))
    big = [w_ for w_, v in bal.items() if v >= 0.03 * SUPPLY and w_ != whale]
    row["n_big"] = len(big)
    row["top10"] = sum(sorted((v for v in bal.values() if v > 0), reverse=True)[:10]) / SUPPLY * 100
    row["whale_prev_bal"] = bal.get(whale, 0) / SUPPLY * 100
    row["whale_prev_trades"] = int((U[R0] == whale).sum()) if whale is not None else 0
    # bots on the token before the trigger
    us = U[R0]
    row["coh_n"] = len(set(w_ for w_ in us.tolist() if w_ in cohid))
    row["coh_hold"] = sum(1 for w_ in set(us.tolist()) if w_ in cohid and bal.get(w_, 0) > 0)
    row["fb_n"] = len(set(w_ for w_ in us.tolist() if w_ in fbots))
    row["fb_hold"] = sum(1 for w_ in set(us.tolist()) if w_ in fbots and bal.get(w_, 0) > 0)
    mm = sl >= s0 - 20
    row["fb_n20"] = len(set(w_ for w_ in us[mm].tolist() if w_ in fbots)); row["coh_n20"] = len(set(w_ for w_ in us[mm].tolist() if w_ in cohid))
    # earlier dumps on this token and how many wallets followed them (complete before the trigger slot)
    mk = C.mid[mint]
    dl = [q for q in du_by_m.get(mk, []) if E["du_s"][q] + 2 < s0]
    row["tok_dumps"] = len(dl); row["tok_dump_fol"] = float(np.mean([E["du_nf"][q] for q in dl])) if dl else -1
    # trigger tx
    tk = rows[k]
    row["trig_cup"] = int(CUP[tk]); row["trig_tip"] = int(TIP[tk]); row["trig_prog"] = C.progs[int(PROG[tk])][:20]
    row["trig_signer_is_user"] = int(SIG[tk] == U[tk])
    # ---- chain-wide whale history (events complete before the trigger slot)
    hist = [q for q in ev_by_w.get(whale, []) if E["tr_s"][q] + 12 < s0]
    row["wh_n"] = len(hist)
    row["wh_fill"] = float(np.mean([E["tr_fill"][q] for q in hist])) if hist else -1
    fl = [q for q in hist if E["tr_fill"][q]]
    row["wh_nf"] = float(np.mean([E["tr_nf"][q] for q in fl])) if fl else -1
    row["wh_bounce"] = float(np.nanmean([E["tr_bounce"][q] for q in fl])) if fl else -1
    row["wh_dumps"] = len([q for q in du_by_w.get(whale, []) if E["du_s"][q] + 2 < s0])
    dw = [q for q in du_by_w.get(whale, []) if E["du_s"][q] + 2 < s0]
    row["wh_dump_fol"] = float(np.mean([E["du_nf"][q] for q in dw])) if dw else -1
    if whale is not None:
        ur = C.user_rows(whale); us_ = S[ur]
        row["wh_trades_before"] = int((us_ < s0).sum())
        row["wh_tokens_before"] = len(set(c["mint"][ur][us_ < s0].tolist()))
        row["wh_first_age"] = int(s0 - us_.min()) if len(us_) else 0
    ch = cre_list.get(info.get("creator"), [])
    row["cre_prev"] = bisect.bisect_left(ch, info.get("slot", 0)) if info else -1
    # T2 history of this creator's earlier tokens (events on tokens by the same creator, complete before the trigger)
    # (computed cheaply: count earlier tokens of the creator only)

    return row
