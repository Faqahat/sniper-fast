#!/usr/bin/env python3
"""OMEN triggers per day (read-only): the live T2 detector (rlib.detect logic) with the holder floor lowered to 2% so every first
>= 2% (X=2) or >= 3% crossing is seen; per trigger: wallet, pct, the wallet's first later sell, QUIET signals (ev.qsig, as live)
and the CAUSAL habit features of that wallet (hab.pkl: only positions whose first sell / 150-slot censor was before the open).
Usable hours as rearm2 ev_D<k>.pkl. usage: omtrig.py D TAB -> trig_D<k>.pkl"""
import sys, os, json, pickle, time, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real")
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/rearm2/code")
import rlib, ev, rep
from rlib import UNTRADE_V, SUPPLY, float32
W = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/omen"
R2 = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/rearm2"
OUR = ev.OUR
HX2 = 20_000_000_000_000; HX3 = 30_000_000_000_000


def detect2(tp, keep):
    """rlib.detect with two floors: returns crossings of 2% (floor2) and of 3% (live floor) with pct >= 2."""
    out = []; ids = tp.ids; idm = tp.id_map()
    for mint, c in tp.creates.items():
        if c.get("mayhem") or c.get("mayhem_ix"): continue
        mid = idm.get(mint)
        if mid is None or mid not in tp.span: continue
        a, e = tp.span[mid]
        s0 = c["slot"]; creator = idm.get(c.get("creator")); signer = idm.get(c.get("user"))
        bal = {}; bec = {2: set(), 3: set()}; ins = set(); trig = []; n = 0; first_sell = {}
        rows = []
        for k in range(a, e):
            if not keep[k]: continue
            s = tp.s[k]
            if (s, tp.i[k]) < (s0, c["idx"]): continue
            v = tp.vsol[k]; t = tp.vtok[k]
            if n < 50 and (v < 25_000_000_000 or v > 200_000_000_000 or t == 0): break
            n += 1
            u = tp.user[k]; b = tp.buy[k]
            bal[u] = bal.get(u, 0) + (tp.tok[k] if b else -tp.tok[k])
            if b and s == s0 and u != creator and u != signer: ins.add(u)
            if not b:
                for d in trig:
                    if d["whale_id"] == u and d["whale_sell"] is None: d["whale_sell"] = (int(s), int(tp.i[k]))
            if b and v < UNTRADE_V:
                for fl, hx in ((2, HX2), (3, HX3)):
                    if u in bec[fl]: continue
                    ht = 1 if u == creator else 2 if u in ins else 3 if bal[u] >= hx else 0
                    if ht: bec[fl].add(u)
                    if ht == 3:
                        pct = float32(bal[u] / SUPPLY * 100.0)
                        trig.append(dict(kind="t2", floor=fl, mint=mint, mid=mid, k=k, slot=int(s), idx=int(tp.i[k]), j=int(tp.j[k]), whale_id=int(u), whale_b58=ids[int(u)],
                                         pct=pct, age_slots=int(s - s0), create_slot=int(s0), v2=bool(c.get("v2")), cashback=bool(c.get("cashback")),
                                         whale_sell=None, bt=int(tp.blockt[k]), sol=int(tp.sol[k])))
        out += trig
    return out


def main(D, tab):
    t0 = time.time()
    Z = pickle.load(open(f"{R2}/ev_D{D}.pkl", "rb")); good = set(rep.day_hours(D)); a_day, b_day = Z["a"], Z["b"]
    ev.QB = pickle.load(open(f"{R2}/qbook.pkl", "rb"))
    H = pickle.load(open(f"{W}/hab_slim.pkl", "rb"))     # (wallet, mint) -> (pos_s, feats)
    tp = rlib.Tape(tab=tab, with_ours=False); ids = tp.ids; idm = tp.id_map()
    our_ids = {idm[w] for w in OUR if w in idm}
    keep = ~np.isin(tp.user, np.array(sorted(our_ids), dtype=np.int64)) if our_ids else np.ones(len(tp.s), bool)
    def ok_t(bt): return a_day <= bt < b_day and (bt // 3600) * 3600 in good
    TR = [x for x in detect2(tp, keep) if ok_t(x["bt"])]
    print(f"D{D}: crossings {len(TR):,} ({time.time() - t0:.0f} s)", flush=True)
    rows_of = {}
    out = []
    for x in TR:
        h = H.get((x["whale_b58"], x["mint"]))
        x["om"] = dict(h[1], pos_s=h[0]) if h else dict(n=0, pos_s=x["slot"])
        f = x["om"]
        # QUIET only where it can matter (base 6% arms, and OMEN candidates)
        need = x["pct"] >= 6.0 or (f["n"] >= 3 and f.get("pbig30", 0) >= 0.3 and f.get("med", 999) <= 30)
        if need and x["age_slots"] > 0:
            mid = x["mid"]
            if mid not in rows_of:
                a, e = tp.span[mid]; rows_of[mid] = [k for k in range(a, e) if keep[k]]
            rr = rows_of[mid]; up = rr.index(x["k"])
            x["q"] = ev.qsig(tp, rr, up, x["slot"], x["bt"], x["whale_b58"], ids)
        else: x["q"] = None
        out.append(x)
    pickle.dump(dict(TR=out, D=D, a=a_day, b=b_day, hours=sorted(good), tab=tab), open(f"{W}/trig_D{D}.pkl", "wb"))
    n6 = [x for x in out if x["floor"] == 3 and x["pct"] >= 6.0]
    print(f"D{D}: saved {len(out):,}; floor3 & >=6%: {len(n6):,} (rearm2 T2 {len(Z['T2']):,}); quiet all4 {sum(1 for x in n6 if x['q'] and x['q']['all4']):,} ({time.time() - t0:.0f} s)", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])
