#!/usr/bin/env python3
"""EXIT step 2 (read-only): haqq's positions, FIFO lots and every sell on the multi-day tape (10-22 03:07 -> 10-28 01:12 PKT),
with the market state at each of his sells (MEASURED from the tape; state = curve and outside trades strictly before his sell).

Per buy (lot): row, slot, idx, chain clock, cost (SOL incl. pump fee), tokens, add (position already open), dump context (biggest
  outside price drop by a sell in the 5 slots before: drop, SOL, slots / ms to the buy), entry type (hs_lib.etype rules).
Per sell: tokens, SOL out (net of pump fee), fraction of the position sold, piece number, and the state just before it:
  pos_ret  = curve sell value of the whole open balance / FIFO cost of the open tokens - 1
  lot_ret  = same for the oldest open lot
  ms / slots since the position's first buy, its last buy, the dump before the first buy
  outside flow (buy SOL, sell SOL, buy count) in the last 212 / 424 / 636 ms (chain clock) and since his last own trade
  hi_ratio = price before the sell / highest price seen (after any outside trade) since his last buy; at_high = within 0.5%
  last outside trade: buy?, SOL, ms before; biggest outside buy in the last 424 ms and since his last trade
  curve SOL before the sell
Lots: P&L = share of sell proceeds (FIFO by tokens) - cost; hold = chain-clock ms from the buy to the sell that closes it.
Chain clock (dv8lib.cc): slot*212 + idx / block size * 212 ms.
Out: haqq_dissect/exit/haqq.pkl = dict(lots, sells, pos); lots closed by MATCHED sells (see the sell loop), else FIFO"""
import pickle, time, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
DEAD_V = 30.52


def etype(b):
    if b["add"]: return "ADD"
    if b["vsol_pre"] <= DEAD_V: return "DEAD"
    if b.get("d_drop", 0) >= 0.05 and b.get("d_slots", 99) <= 2: return "DIP"
    if b["age"] is not None and b["age"] <= 5: return "LAUNCH"
    if b.get("dd10", 0) >= 0.10: return "DIP_LATE"
    if b.get("wb_sol", 0) >= 1.0 and (b.get("wb_slots") if b.get("wb_slots") is not None else 99) <= 2: return "MOMO"
    return "OTHER"


def flow(M, k, lo_cc, H):
    """outside rows j < k with cc >= lo_cc: (buy SOL, sell SOL, n buys, max buy)"""
    j0 = int(np.searchsorted(M.cc[:k], lo_cc, side="left"))
    w = slice(j0, k); o = M.us[w] != H; b = M.bu[w] & o; s = ~M.bu[w] & o
    so = M.so[w]
    return float(so[b].sum()), float(so[s].sum()), int(b.sum()), float(so[b].max()) if b.any() else 0.0


def main():
    t0 = time.time()
    R, MI, span, CC = X.tape()
    H = MI["who"]["haqq"]
    hm = np.unique(R["mint"][R["user"] == H]).tolist()
    lots, sells, poss = [], [], []
    for n_m, m in enumerate(hm):
        M = X.Mint(m)
        hk = np.flatnonzero(M.us == H)
        q = collections.deque(); bal = 0.0; P = None; last_own = None
        for k in hk.tolist():
            if M.bu[k]:
                cost = M.so[k] * (1 + M.fee[k]); tok = M.tk[k]
                add = bal > 0 and P is not None
                if not add:
                    P = dict(mint=m, pid=len(poss), k0=k, slot0=int(M.sl[k]), cc0=float(M.cc[k]), bt0=int(M.bt[k]), nb=0, ns=0, cost=0.0, out=0.0,
                             peak=0.0, lots=[], sells=[], close_cc=None, close_k=None, dump_cc=None)
                    poss.append(P)
                # dump context: biggest outside sell drop in the 5 slots before
                lo5 = int(np.searchsorted(M.sl, M.sl[k] - 5)); lo10 = int(np.searchsorted(M.sl, M.sl[k] - 10)); lo3 = int(np.searchsorted(M.sl, M.sl[k] - 3))
                cand = [j for j in range(lo5, k) if not M.bu[j] and M.us[j] != H]
                drop = [1 - M.px[j] / M.pxp[j] for j in cand]
                B = dict(mint=m, pid=P["pid"], k=k, row=M.a + k, slot=int(M.sl[k]), idx=int(M.ix[k]), cc=float(M.cc[k]), bt=int(M.bt[k]), cost=cost, tok=tok,
                         left=tok, out=0.0, add=add, nth=P["nb"], vsol_pre=float(M.vsp[k]), age=int(M.sl[k] - M.cs) if M.cs is not None else None,
                         sells=[], close_cc=None, close_k=None)
                if cand:
                    jj = int(np.argmax(drop)); dj = cand[jj]
                    if drop[jj] > 0:
                        B.update(d_drop=float(drop[jj]), d_sol=float(M.so[dj]), d_slots=int(M.sl[k] - M.sl[dj]), d_ms=float(M.cc[k] - M.cc[dj]), d_cc=float(M.cc[dj]),
                                 d_k=dj, d_nbuy=int((M.bu[dj + 1:k] & (M.us[dj + 1:k] != H)).sum()))
                mx10 = float(M.px[lo10:k].max()) if k > lo10 else M.pxp[k]
                B["dd10"] = float(1 - M.pxp[k] / mx10) if mx10 > 0 else 0.0
                wb = [j for j in range(lo3, k) if M.bu[j] and M.us[j] != H]
                if wb:
                    bj = max(wb, key=lambda j: M.so[j]); B["wb_sol"] = float(M.so[bj]); B["wb_slots"] = int(M.sl[k] - M.sl[bj])
                B["t"] = etype(B)
                if not add and B.get("d_cc") is not None: P["dump_cc"] = B["d_cc"]
                B["lot_ix"] = len(lots); lots.append(B); q.append(B)
                P["nb"] += 1; P["cost"] += cost; P["lots"].append(len(lots) - 1); P["last_buy_cc"] = float(M.cc[k]); P["last_buy_k"] = k
                bal += tok; P["peak"] = max(P["peak"], bal)
                last_own = k
            else:
                if P is None or bal <= 0 or not q:
                    last_own = k; continue                                     # sell of a position opened before the tape: skip
                tok = M.tk[k]; gross = M.so[k] * (1 - M.fee[k])
                v0 = M.vsp[k]; t0 = M.vtp[k]
                open_cost = sum(L["cost"] * L["left"] / L["tok"] for L in q)
                val_all = X.sell_value(v0, t0, bal)
                L0 = q[0]; val_l0 = X.sell_value(v0, t0, L0["left"]); c_l0 = L0["cost"] * L0["left"] / L0["tok"]
                kb = P["last_buy_k"]
                hi = float(M.px[kb:k][M.us[kb:k] != H].max()) if (M.us[kb:k] != H).any() else float(M.pxp[k])
                hi = max(hi, float(M.px[kb]))
                jo = k - 1
                while jo >= 0 and M.us[jo] == H: jo -= 1
                f1 = flow(M, k, M.cc[k] - 212, H); f2 = flow(M, k, M.cc[k] - 424, H); f3 = flow(M, k, M.cc[k] - 636, H)
                fo = flow(M, k, M.cc[last_own] + 1e-6, H) if last_own is not None else (0.0, 0.0, 0, 0.0)
                S = dict(mint=m, pid=P["pid"], k=k, row=M.a + k, slot=int(M.sl[k]), idx=int(M.ix[k]), cc=float(M.cc[k]), bt=int(M.bt[k]), tok=tok, sol=gross,
                         frac=float(min(tok / bal, 1.0)), piece=P["ns"], nb_so_far=P["nb"], bal=bal,
                         pos_ret=float(val_all / open_cost - 1) if open_cost > 0 else None, lot_ret=float(val_l0 / c_l0 - 1) if c_l0 > 0 else None,
                         ms_first=float(M.cc[k] - P["cc0"]), ms_last_buy=float(M.cc[k] - P["last_buy_cc"]), slots_first=int(M.sl[k] - P["slot0"]),
                         slots_last_buy=int(M.sl[k] - M.sl[kb]), ms_dump=float(M.cc[k] - P["dump_cc"]) if P["dump_cc"] is not None else None,
                         ms_last_own=float(M.cc[k] - M.cc[last_own]) if last_own is not None else None,
                         f212=f1, f424=f2, f636=f3, f_own=fo, hi_ratio=float(M.pxp[k] / hi), vsol=float(v0),
                         last_buy=bool(M.bu[jo]) if jo >= 0 else None, last_sol=float(M.so[jo]) if jo >= 0 else None, last_ms=float(M.cc[k] - M.cc[jo]) if jo >= 0 else None,
                         ret_lastbuy_px=float(M.pxp[k] / M.px[kb]) if M.px[kb] > 0 else None)
                sells.append(S); P["sells"].append(len(sells) - 1); P["ns"] += 1; P["out"] += gross
                # lot matching (MEASURED 10-28: with >= 2 open lots, 80% of his sells equal ONE open lot's tokens within 1%, oldest or
                # newest about equally): a sell equal to one open lot's remaining tokens closes that lot; otherwise FIFO
                need = tok
                mt = [L for L in q if abs(L["left"] - tok) <= 0.01 * L["left"]]
                S["matched"] = len(mt) > 0
                if mt:
                    L = mt[0]; S["lot"] = L["lot_ix"]; S["lot_n_open"] = len(q); S["lot_pos_in_open"] = q.index(L)
                    c_l = L["cost"] * L["left"] / L["tok"]; S["mlot_ret"] = float(X.sell_value(v0, t0, L["left"]) / c_l - 1) if c_l > 0 else None
                    S["mlot_ms"] = float(M.cc[k] - L["cc"]); S["mlot_slots"] = int(M.sl[k] - L["slot"]); S["mlot_t"] = L["t"]
                    L["out"] += gross; L["left"] = 0.0; L["sells"].append((len(sells) - 1, 1.0)); L["close_cc"] = float(M.cc[k]); L["close_k"] = k
                    q.remove(L); need = 0.0
                while need > 0.5 and q:
                    L = q[0]; take = min(L["left"], need)
                    L["out"] += gross * take / tok; L["left"] -= take; need -= take
                    L["sells"].append((len(sells) - 1, take / L["tok"]))
                    if L["left"] <= 0.5:
                        L["close_cc"] = float(M.cc[k]); L["close_k"] = k; q.popleft()
                bal -= tok
                if bal <= 0.005 * P["peak"]:
                    P["close_cc"] = float(M.cc[k]); P["close_k"] = k; bal = 0.0
                    for L in q: L["left"] = 0.0; L["close_cc"] = float(M.cc[k]); L["close_k"] = k
                    q.clear()
                last_own = k
        # open lots at the tape end: marked at the last price (sell value) - flagged
        for L in q:
            L["mark"] = float(X.sell_value(M.vs[-1], M.vt[-1], L["left"])); L["open_end"] = True
        if n_m % 2000 == 0: print(f"{n_m}/{len(hm)} mints, lots {len(lots):,} sells {len(sells):,} ({time.time() - t0:.0f}s)", flush=True)
    for L in lots:
        L["pnl"] = L["out"] + L.get("mark", 0.0) - L["cost"]
        L["hold_ms"] = (L["close_cc"] - L["cc"]) if L["close_cc"] is not None else None
        L["day"] = X.day_of(L["bt"])
    for P in poss:
        P["day"] = X.day_of(P["bt0"]); P["pnl"] = sum(lots[i]["pnl"] for i in P["lots"])
    pickle.dump(dict(lots=lots, sells=sells, pos=poss), open(f"{X.OUT}/haqq.pkl", "wb"))
    print(f"done: positions {len(poss):,} lots {len(lots):,} sells {len(sells):,} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
