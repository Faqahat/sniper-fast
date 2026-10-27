#!/usr/bin/env python3
"""PRESEND FILTER, step 3: chain-wide event tables (MEASURED from the chain table; used ONLY causally: a feature at time T reads
events that were complete before T).
  T2-like triggers: the detector's rules replayed on every token (balances from the token's first trade; creator = launch creator;
    create-slot insiders = bought in the create slot, not the creator nor the create's signer; the first >= 3% crossing; holding >= 5%
    at that buy; curve < 100 SOL; non-standard curves excluded as the engine does). Per event, its outcome over the next 10 slots:
    'fill-like' = a trade whose post-trade price is <= 0.88 x the price at the end of the previous slot (the try limit, latest price x
    0.88); then the distinct other buyers in that slot (after it) and the next 2 slots, and the price 2 slots later / the fill price.
  dumps: every sell that by itself drops the price >= 8%, >= 0.3 SOL, curve < 100 SOL; the distinct other wallets buying after it in
    its slot and the next 2 slots (follow-buys).
Writes /home/moiz/sniper-data/presend_filter/events.npz"""
import json, time, collections
import numpy as np
from chainlib import Chain, B

HX = 30_000_000_000_000; SUP = 1e15


def main():
    t0 = time.time()
    C = Chain()
    cr = json.load(open(f"{B}/creates.json"))
    c = C.c
    S, I, J, BUY, SOL, TOK, VS, VT, U, BT = (c[k] for k in ("s", "i", "j", "buy", "sol", "tok", "vsol", "vtok", "user", "bt"))
    trig = collections.defaultdict(list); dumps = collections.defaultdict(list); fol = []
    for mk, mint in enumerate(C.mints):
        rows = C.morder[C.mstart[mk]:C.mstart[mk + 1]]
        if len(rows) < 2: continue
        info = cr.get(mint)
        s0 = info["slot"] if info else None
        creator = C.wid.get(info["creator"]) if info else None
        signer = C.wid.get(info["user"]) if info else None
        s = S[rows]; i = I[rows]; buy = BUY[rows]; sol = SOL[rows]; tok = TOK[rows]; vs = VS[rows]; vt = VT[rows]; u = U[rows]; bt = BT[rows]
        p = vs / np.maximum(vt, 1)
        pre = np.where(buy == 1, (vs - sol) / np.maximum(vt + tok, 1), (vs + sol) / np.maximum(vt - tok, 1))
        # price at the end of each slot (for the try limit reference): last trade of the slot
        last_in_slot = np.r_[s[1:] != s[:-1], True]
        bal = collections.defaultdict(int); became = set(); ins = set(); out = False
        n = len(rows)
        # end-of-previous-slot price per row
        endp = np.empty(n); cur = pre[0]; k0 = 0
        for k in range(n):
            if k > 0 and s[k] != s[k - 1]: cur = p[k - 1]
            endp[k] = cur
        for k in range(n):
            if k < 50 and (vs[k] < 25e9 or vs[k] > 200e9 or vt[k] == 0): out = True; break
            w = int(u[k])
            if buy[k]:
                bal[w] += int(tok[k])
                if s0 is not None and s[k] == s0 and w != creator and w != signer: ins.add(w)
                if vs[k] < 100e9 and w not in became:
                    ht = 1 if w == creator else 2 if w in ins else 3 if bal[w] >= HX else 0
                    if ht: became.add(w)
                    if ht == 3:
                        pct = bal[w] / SUP * 100
                        if pct >= 5.0:
                            # outcome over the next 10 slots
                            sl_end = s[k] + 10
                            fk = None
                            for q in range(k + 1, n):
                                if s[q] > sl_end: break
                                if p[q] <= 0.88 * endp[q] and vs[q] < 100e9: fk = q; break
                            nf = 0; bounce = np.nan; whale_dump = 0
                            if fk is not None:
                                bset = set(); q2 = fk + 1; lastq = fk
                                while q2 < n and s[q2] <= s[fk] + 2:
                                    if buy[q2] and u[q2] != u[fk]: bset.add(int(u[q2]))
                                    lastq = q2; q2 += 1
                                nf = len(bset); bounce = p[lastq] / p[fk]; whale_dump = int(u[fk] == w)
                            trig[w].append((int(s[k]), int(i[k]), mk, pct, float(vs[k]) / 1e9, int(s[k] - s0) if s0 is not None else -1,
                                            fk is not None, nf, bounce, whale_dump, int(bt[k])))
            else:
                bal[w] -= int(tok[k])
                if sol[k] >= 3e8 and vs[k] < 100e9 and p[k] <= 0.92 * pre[k]:
                    bset = set(); q2 = k + 1
                    while q2 < n and s[q2] <= s[k] + 2:
                        if buy[q2] and u[q2] != w:
                            bset.add(int(u[q2]))
                        q2 += 1
                    dumps[mk].append((int(s[k]), int(i[k]), w, len(bset), int(bt[k])))
                    for b in bset: fol.append((b, mk, int(s[k]), int(bt[k])))
        if mk % 20000 == 0: print(mk, f"{time.time() - t0:.0f}s", flush=True)
    # flatten
    T = [(w,) + e for w, L in trig.items() for e in L]
    T.sort(key=lambda x: (x[1], x[2]))
    ta = np.array(T, dtype=object)
    np.savez(f"{B}/events.npz",
             tr_w=np.array([x[0] for x in T], np.uint32), tr_s=np.array([x[1] for x in T], np.uint64), tr_i=np.array([x[2] for x in T], np.uint32),
             tr_m=np.array([x[3] for x in T], np.uint32), tr_pct=np.array([x[4] for x in T]), tr_v=np.array([x[5] for x in T]), tr_age=np.array([x[6] for x in T], np.int64),
             tr_fill=np.array([x[7] for x in T], bool), tr_nf=np.array([x[8] for x in T], np.int32), tr_bounce=np.array([x[9] for x in T], float),
             tr_wdump=np.array([x[10] for x in T], np.int8), tr_bt=np.array([x[11] for x in T], np.int64),
             du_m=np.array([mk for mk, L in dumps.items() for e in L], np.uint32), du_s=np.array([e[0] for L in dumps.values() for e in L], np.uint64),
             du_i=np.array([e[1] for L in dumps.values() for e in L], np.uint32), du_w=np.array([e[2] for L in dumps.values() for e in L], np.uint32),
             du_nf=np.array([e[3] for L in dumps.values() for e in L], np.int32), du_bt=np.array([e[4] for L in dumps.values() for e in L], np.int64),
             fo_w=np.array([x[0] for x in fol], np.uint32), fo_m=np.array([x[1] for x in fol], np.uint32), fo_s=np.array([x[2] for x in fol], np.uint64),
             fo_bt=np.array([x[3] for x in fol], np.int64))
    print(f"triggers {len(T):,} (fill-like {sum(1 for x in T if x[7]):,}), dumps {sum(len(L) for L in dumps.values()):,}, follow-buys {len(fol):,}, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
