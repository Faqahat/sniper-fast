#!/usr/bin/env python3
# per-position profile of the 3 wallets from the collector tapes (all runs R1-R3), read-only -> out/pos3.json
# position = all of the wallet's trades in one token. PnL (tape) = sells x (1-fee) - buys x (1+fee), pump fee bps from each event;
# tokens left at the end are marked at the last curve price (flag open; flag grad when the curve completed).
import os, sys, json, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat, lib3
SL = feat.SL
T, F = lib3.load_tapes(); L = lib3.load_launches()
def ms(t):
    n = lib3.slot_size(t["s"]) or 450
    return t["s"] * 212.0 + min(t["i"] / max(n, t["i"] + 1), 0.999) * 212.0
def fr(t): return (t["fbps"] + t["cbps"]) / 1e4
P = []
for m, tr in T.items():
    c = L.get(m)
    if not c: continue
    may = feat.is_mayhem(tr); st = feat.structure(tr, c); S = c["slot"]
    last = tr[-1]; grad_tape = last["vsol"] >= 110e9
    for w8, W in lib3.W3.items():
        ks = [k for k, t in enumerate(tr) if t["user"] == W]
        if not ks: continue
        bk = [k for k in ks if tr[k]["buy"]]; sk = [k for k in ks if not tr[k]["buy"]]
        if not bk: P.append(dict(w=w8, m=m, run=c["run"], nobuy=True, nsell=len(sk))); continue
        k0 = bk[0]; b0 = tr[k0]
        sin = sum(tr[k]["sol"] * (1 + fr(tr[k])) for k in bk) / 1e9; sout = sum(tr[k]["sol"] * (1 - fr(tr[k])) for k in sk) / 1e9
        tin = sum(tr[k]["tok"] for k in bk); tout = sum(tr[k]["tok"] for k in sk if k > k0)
        pre_sells = [k for k in sk if k < k0]
        rem = max(0, tin - tout)
        mark = (last["vsol"] * rem / (last["vtok"] + rem) * (1 - fr(last)) / 1e9) if rem > 0.01 * tin and last["vtok"] else 0.0
        snap = feat.snapshot(tr, c, st, k0, b0["s"])
        # followers after the first buy
        m0 = ms(b0)
        fol = [t for t in tr[k0 + 1:] if t["user"] != W and t["buy"] and t["s"] - b0["s"] <= 25]
        def folw(slots): return [t for t in fol if t["s"] - b0["s"] <= slots]
        sk_after = [k for k in sk if k > k0]
        fs = tr[sk_after[0]] if sk_after else None; ls_ = tr[sk_after[-1]] if sk_after else None
        avgp = (sum(tr[k]["sol"] for k in bk) / tin) if tin else 0
        end_k = sk_after[-1] if sk_after else len(tr) - 1
        hold_tr = tr[k0:end_k + 1]
        prices = [feat.px(t["vsol"], t["vtok"]) for t in hold_tr]
        d = dict(w=w8, m=m, run=c["run"], bt=b0["bt"], hour=int(((b0["bt"] + 18000) % 86400) // 3600), mayhem=may, isdev=W in (st["creator"], st["signer"]),
                 create_slot=b0["s"] == S, in_bundle=W in st["insiders"], age=(b0["s"] - S) * SL, k0=k0, pos_ms_in_slot=ms(b0) - b0["s"] * 212.0,
                 nb=len(bk), ns=len(sk_after), pre_sells=len(pre_sells), b0_sol=b0["sol"] / 1e9, sin=sin, sout=sout, mark=mark, open=mark > 0, grad=grad_tape and mark > 0,
                 pnl=sout + mark - sin, ret=(sout + mark) / sin - 1 if sin else 0,
                 buy_ts=[round((tr[k]["s"] - b0["s"]) * SL, 2) for k in bk], buy_sols=[round(tr[k]["sol"] / 1e9, 3) for k in bk],
                 sell_ts=[round((tr[k]["s"] - b0["s"]) * SL, 2) for k in sk_after], sell_tok=[round(tr[k]["tok"] / tin, 3) if tin else 0 for k in sk_after],
                 t_first_sell=(fs["s"] - b0["s"]) * SL if fs else None, hold=(ls_["s"] - b0["s"]) * SL if ls_ else None,
                 mfe=max(prices) / avgp if avgp else 0, mae=min(prices) / avgp if avgp else 0,
                 fol1=len(folw(1)), fol1_sol=sum(t["sol"] for t in folw(1)) / 1e9, fol2=len(folw(2)), fol5s=len(folw(24)), fol5s_sol=sum(t["sol"] for t in folw(24)) / 1e9,
                 fol_sameslot=len([t for t in fol if t["s"] == b0["s"]]),
                 fol_first_ms=(ms(fol[0]) - m0) if fol else None, fol_first_slots=(fol[0]["s"] - b0["s"]) if fol else None,
                 fees_bps=b0["fbps"] + b0["cbps"], cup=b0.get("cup"), cul=b0.get("cul"), tips=b0.get("tips"), payer_is_w=b0["payer"] == W,
                 **{"e_" + k: v for k, v in snap.items()})
        if fs:
            kf = sk_after[0]
            px_fs = feat.px(tr[kf - 1]["vsol"], tr[kf - 1]["vtok"])
            peak = max(feat.px(t["vsol"], t["vtok"]) for t in tr[k0:kf])
            pre = [t for t in tr[k0 + 1:kf] if t["user"] != W]
            pre10 = [t for t in pre if (fs["s"] - t["s"]) * SL <= 10]
            pre3 = [t for t in pre if (fs["s"] - t["s"]) * SL <= 3]
            # first sell's own position relative to the trade right before it
            prev = tr[kf - 1]
            d.update(x_ret_px=px_fs / avgp if avgp else 0, x_vs_peak=px_fs / peak if peak else 1, x_dev_sold=any(t["user"] == st["creator"] and not t["buy"] for t in pre),
                     x_net10=sum(t["sol"] if t["buy"] else -t["sol"] for t in pre10) / 1e9, x_sells10=sum(1 for t in pre10 if not t["buy"]),
                     x_buys10=sum(1 for t in pre10 if t["buy"]), x_net3=sum(t["sol"] if t["buy"] else -t["sol"] for t in pre3) / 1e9,
                     x_bigsell10=max([t["sol"] for t in pre10 if not t["buy"]] or [0]) / 1e9, x_prev_is_sell=not prev["buy"], x_prev_same_slot=prev["s"] == fs["s"],
                     x_prev_user_other=prev["user"] != W, x_gap_prev=(fs["s"] - prev["s"]) * SL,
                     x_out_buy_sol=sum(t["sol"] for t in pre if t["buy"]) / 1e9, x_out_sell_sol=sum(t["sol"] for t in pre if not t["buy"]) / 1e9,
                     x_out_buyers=len({t["user"] for t in pre if t["buy"]}), x_frac_first=fs["tok"] / tin if tin else 0)
        P.append(d)
json.dump(P, open(os.path.join(lib3.HERE, "out/pos3.json"), "w"))
print("positions", len(P))
