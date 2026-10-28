#!/usr/bin/env python3
"""FOLLOW step 1 (read-only): the full pump.fun tape (dv8/tab, 10-22 03:07 -> 10-28 01:12 PKT) in chain order with OUR two wallets'
rows removed (we are simulated; haqq stays), plus per-row wallet balances, prices, the chain clock and the per-mint create info.
Then the three event sets the selector needs (all MEASURED from the tape):
  * WHALE EPISODES: a wallet holding >= 6 % of supply (6e13 raw) on a token. An episode starts at the buy that takes it to >= 6 %
    (curve < 100 SOL) or right after one of its sells that leaves it still >= 6 %; it ends at the wallet's NEXT sell on the token
    (= "the dump"; the engine's window ends 30 ms after the whale's first sell). No next sell = open to the tape's end.
  * CROSSINGS (where an armed pre-send attempt can fill): an outside sell whose post-trade price is <= 0.88 x the reference = the
    post-trade price of the last trade >= 50 ms earlier on the chain clock (presend.rs FILL rule, drop 0.12, ref_ms 50), curve < 100 SOL.
  * BOOK DUMPS (presend_quiet.rs DumpBook): a sell >= 0.3 SOL, curve < 100 SOL, post price <= 0.92 x pre price; followers = distinct
    buyers (not the seller) after it in its slot and the next 2 slots. Plus the ideal 2-slot value of a 0.40 SOL buy right after it
    (exact curve, exit = state after the last trade of slot +2), known at the end of slot +2 (A's "paid" signal).
Out (data folder): tape.npy (sorted rows), rowx.npz (bal_before, bal_after, px, pxp, cc, ref), mints.pkl, episodes.npz, cross.npz,
bookdumps.npz"""
import json, sys, time, pickle
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/follow"
W6 = 6e13; UNTRADE = 100e9; DROP = 0.12; REF_MS = 50.0; SIZE = 0.40; FEE = 0.0125


def main():
    t0 = time.time()
    ids, idm = L.ids_map()
    ours = np.array([idm[w] for w in L.WAL.values() if w in idm])
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    keep = ~np.isin(np.asarray(T["user"]), ours)
    cols = ("slot", "idx", "j", "mint", "user", "buy", "sol", "tok", "vsol", "vtok", "fee_bps", "cfee_bps", "bt", "sigh")
    R = np.zeros(int(keep.sum()), dtype=[(c, T.dtype[c]) for c in cols])
    for c in cols: R[c] = np.asarray(T[c])[keep]
    del keep
    R = R[np.lexsort((R["j"], R["idx"], R["slot"], R["mint"]))]
    n = len(R)
    np.save(f"{OUT}/tape.npy", R)
    print(f"tape {n:,} rows ({time.time() - t0:.0f}s)", flush=True)
    mint = R["mint"].astype(np.int64); user = R["user"].astype(np.int64); buy = R["buy"].astype(bool)
    tok = R["tok"].astype(np.int64)
    stok = np.where(buy, tok, -tok)
    o2 = np.lexsort((np.arange(n), user, mint))
    cs = np.cumsum(stok[o2])
    newg = np.ones(n, bool); newg[1:] = (mint[o2][1:] != mint[o2][:-1]) | (user[o2][1:] != user[o2][:-1])
    gstart = np.maximum.accumulate(np.where(newg, np.arange(n), 0))
    base = np.where(gstart > 0, cs[gstart - 1], 0)
    ba = np.empty(n, np.int64); ba[o2] = cs - base
    bb = ba - stok
    print(f"balances ({time.time() - t0:.0f}s)", flush=True)
    # mints, create info
    um, st = np.unique(mint, return_index=True); en = np.append(st[1:], n)
    CR = json.load(open(f"{L.TAB}/creates.json"))
    info = {}
    for m in um.tolist():
        c = CR.get(ids[m]) or {}
        info[m] = dict(cs=c.get("slot"), ci=c.get("idx"), cbt=c.get("bt"), creator=idm.get(c.get("creator"), -1), mayhem=bool(c.get("mayhem")),
                       vsol=c.get("vsol"), vtok=c.get("vtok"), quote_ok=(c.get("quote") == "11111111111111111111111111111111"))   # native SOL quote (vsol 30 SOL at create)
    del CR
    vs = R["vsol"].astype(np.float64); vt = R["vtok"].astype(np.float64)
    px = vs / np.maximum(vt, 1)
    pxp = np.empty(n); pxp[1:] = px[:-1]
    for m, a in zip(um.tolist(), st.tolist()):
        c = info[m]; pxp[a] = (float(c.get("vsol") or 30e9)) / float(c.get("vtok") or 1.073e15)
    cc = L.cc(R["slot"], R["idx"])
    # reference = post-trade price of the last trade >= 50 ms earlier on the same mint (else the first trade's pre-trade price)
    c0 = cc.min()
    key = mint.astype(np.float64) * 1e9 + (cc - c0)
    ri = np.searchsorted(key, key - REF_MS, side="right") - 1
    mst = np.repeat(st, en - st)
    ok = ri >= mst
    ref = np.where(ok, px[np.clip(ri, 0, n - 1)], pxp[mst])
    np.savez(f"{OUT}/rowx.npz", bb=bb, ba=ba, px=px, cc=cc, ref=ref)   # (pxp / mst not used downstream: not saved, disk cap)
    pickle.dump(dict(info=info, um=um, st=st, en=en, haqq=idm[L.HAQQ]), open(f"{OUT}/mints.pkl", "wb"))
    print(f"prices/ref ({time.time() - t0:.0f}s)", flush=True)
    sl = R["slot"].astype(np.int64)
    # ---- whale episodes
    sell = ~buy
    start = (buy & (bb < W6) & (ba >= W6) & (vs < UNTRADE)) | (sell & (ba >= W6))
    # next sell of the same (mint, user) after each row: in o2 order (grouped, chain order inside)
    pos = np.empty(n, np.int64); pos[o2] = np.arange(n)
    sell_pos = np.flatnonzero(sell[o2])
    nxt = np.searchsorted(sell_pos, pos, side="right")
    has = nxt < len(sell_pos)
    nsp = np.where(has, sell_pos[np.clip(nxt, 0, len(sell_pos) - 1)], -1)
    same = has & (nsp >= 0)
    same &= (mint[o2][np.clip(nsp, 0, n - 1)] == mint) & (user[o2][np.clip(nsp, 0, n - 1)] == user)
    endrow = np.where(same, o2[np.clip(nsp, 0, n - 1)], -1)
    es = np.flatnonzero(start)
    E = dict(r0=es, r1=endrow[es], mint=mint[es], user=user[es], s0=sl[es], cc0=cc[es], pct0=ba[es] / 1e13, kind=np.where(buy[es], 0, 1))
    np.savez(f"{OUT}/episodes.npz", **E)
    print(f"episodes {len(es):,} (buy-start {int((E['kind'] == 0).sum()):,}, after-sell {int((E['kind'] == 1).sum()):,}; open {int((E['r1'] < 0).sum()):,}) "
          f"({time.time() - t0:.0f}s)", flush=True)
    # ---- crossings
    cr = np.flatnonzero(sell & (px <= (1 - DROP) * ref) & (vs < UNTRADE))
    # N_w = outside rows after the crossing to the end of slot +1 on the mint
    k2 = mint * (1 << 24) + (sl - sl.min())
    hi = np.searchsorted(k2, k2[cr] + 1, side="right")
    np.savez(f"{OUT}/cross.npz", row=cr, nw=hi - cr - 1)
    print(f"crossings {len(cr):,} ({time.time() - t0:.0f}s)", flush=True)
    # ---- book dumps
    so = R["sol"].astype(np.int64)
    pre = (vs + so) / np.maximum(vt - tok, 1)
    bd = np.flatnonzero(sell & (so >= 300_000_000) & (vs < UNTRADE) & (vt > tok) & ~(px > 0.92 * pre))
    hi3 = np.searchsorted(k2, k2[bd] + 2, side="right")
    fol = np.zeros(len(bd), np.int32); ide = np.full(len(bd), np.nan); fsol = np.zeros(len(bd))
    fee = (R["fee_bps"].astype(np.float64) + R["cfee_bps"]) / 1e4
    for q, (r, h) in enumerate(zip(bd.tolist(), hi3.tolist())):
        if h > r + 1:
            b_ = buy[r + 1:h]; u_ = user[r + 1:h]
            fol[q] = len(set(u_[b_ & (u_ != user[r])].tolist()))
            fsol[q] = float(so[r + 1:h][b_].sum()) / 1e9
        # ideal 2-slot value of 0.40 SOL right after the dump (exact constant-product, later trades keep their amounts)
        f = fee[r] if fee[r] > 0 else FEE
        V = vs[r] / 1e9; Tk = vt[r]; K = V * Tk; sn = SIZE / (1 + f)
        V += sn; Tk2 = K / V; mine = vt[r] - Tk2; Tk = Tk2
        for g in range(r + 1, h):
            if buy[g]: V += so[g] / 1e9; Tk = K / V
            else: Tk += tok[g]; V = K / Tk
        ide[q] = (V - K / (Tk + mine)) * (1 - f) - SIZE
    np.savez(f"{OUT}/bookdumps.npz", row=bd, fol=fol, fsol=fsol, ide=ide, end_slot=sl[bd] + 2)
    print(f"book dumps {len(bd):,} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
