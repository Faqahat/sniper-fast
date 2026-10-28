#!/usr/bin/env python3
"""MINOR step 1 (read-only): every haqq lot on the exit tape (haqq_dissect/exit/tape.npy, 10-22 03:07 -> 10-28 01:12 PKT) with
code-matched FIFO accounting (code = CU price mod 1000, from exec/txs.pkl, else pos/codes.pkl), and per lot:
  - its same-code sells (slot / chain-ms after the buy, token fraction of the lot, SOL),
  - which OTHER codes held an open lot on the mint at the buy (causal: lots bought before, not yet closed),
  - the latest earlier haqq buy on the mint by another code (code, ms / slots before) and by the same code,
  - buy sig and first-sell sig (for Solscan links).
Joined to pos/p1.pkl buys by (mint, slot, idx) for the decision-time context (dump, age, curve) and the pos analyst's code-matched P&L.
Out: /home/moiz/sniper-data/haqq_dissect/minor/m1.pkl"""
import pickle, sys, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import xlib as X
from plib import load
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/minor"


def main():
    t0 = time.time()
    TX = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/exec/txs.pkl", "rb"))
    hx = {}; fails = []
    for r in TX:
        if r["w"] != "haqq": continue
        if r["ok"]: hx[(r["s"], r["i"])] = r
        else: fails.append(dict(code=(r["cup"] or 0) % 1000, s=r["s"], bt=r["bt"], kind=r["kind"], ecode=r["ecode"], mint=r["mint"], sig=r["sig"],
                                cul=r["cul"], cup=r["cup"], fee=r["fee"], tip=r["tip"], path=r["path"]))
    del TX
    CODES = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/pos/codes.pkl", "rb"))
    B, LO, T = load()
    bkey = {(b["mint"], b["slot"], b["idx"]): i for i, b in enumerate(B)}
    lot_of_b = {l["b"]: li for li, l in enumerate(LO)}
    ids, idm = L.ids_map()
    R, MI, span, CC = X.tape()
    H = MI["who"]["haqq"]
    hm = np.unique(R["mint"][R["user"] == H]).tolist()
    print(f"haqq txs landed {len(hx):,} failed {len(fails):,}; mints {len(hm):,} ({time.time() - t0:.0f}s)", flush=True)
    lots = []; nocode = 0
    for n_m, m in enumerate(hm):
        M = X.Mint(m); ms = ids[m]
        hk = np.flatnonzero(M.us == H).tolist()
        openl = []                       # open lots (dicts) chain order
        lastbuy = {}                     # code -> (k, cc, slot)
        for k in hk:
            key = (int(M.sl[k]), int(M.ix[k]))
            t = hx.get(key); c = (t["cup"] % 1000) if t and t.get("cup") else (CODES[key][0] if key in CODES else None)
            if c is None: nocode += 1
            if M.bu[k]:
                cost = M.so[k] * (1 + M.fee[k])
                others = sorted({l["code"] for l in openl if l["code"] != c})
                same_open = sum(1 for l in openl if l["code"] == c)
                ob = [(cc_, kk, sl_, cd) for cd, (kk, cc_, sl_) in lastbuy.items() if cd != c]
                prev_other = max(ob) if ob else None
                bi = bkey.get((ms, key[0], key[1]))
                lot = dict(mint=m, ms=ms, k=k, slot=key[0], idx=key[1], cc=float(M.cc[k]), bt=int(M.bt[k]), code=c, cost=float(cost), tok=float(M.tk[k]),
                           left=float(M.tk[k]), out=0.0, sells=[], others=others, same_open=same_open,
                           po_code=prev_other[3] if prev_other else None, po_ms=float(M.cc[k] - prev_other[0]) if prev_other else None,
                           po_slots=int(M.sl[k] - prev_other[2]) if prev_other else None,
                           ps_ms=float(M.cc[k] - lastbuy[c][1]) if c in lastbuy else None,
                           sig=t["sig"] if t else None, cul=t["cul"] if t else None, cup=t["cup"] if t else None, tip=t["tip"] if t else None,
                           fee=t["fee"] if t else None, path=t["path"] if t else None, b=bi, plot=lot_of_b.get(bi) if bi is not None else None,
                           vsol_pre=float(M.vsp[k]), age=int(M.sl[k] - M.cs) if M.cs is not None else None, mayhem=bool(MI["info"][m]["mayhem"]))
                openl.append(lot); lots.append(lot)
                lastbuy[c] = (k, float(M.cc[k]), int(M.sl[k]))
            else:
                gross = M.so[k] * (1 - M.fee[k]); tot = M.tk[k]; need = tot
                sig = t["sig"] if t else None
                for pas in (0, 1):
                    for l in list(openl):
                        if need <= 0.5: break
                        if pas == 0 and l["code"] != c: continue
                        take = min(l["left"], need)
                        if take <= 0: continue
                        l["out"] += gross * take / tot; l["left"] -= take; need -= take
                        l["sells"].append((int(M.sl[k] - l["slot"]), float(M.cc[k] - l["cc"]), take / l["tok"], gross * take / tot, sig, c, pas))
                        if l["left"] <= 0.5: openl.remove(l)
        px_end = M.px[-1]
        for l in openl: l["mark"] = l["left"] * px_end * 0.9875
        if n_m % 5000 == 0: print(f"  {n_m:,}/{len(hm):,} mints, {len(lots):,} lots ({time.time() - t0:.0f}s)", flush=True)
    pickle.dump(dict(lots=lots, fails=fails), open(f"{OUT}/m1.pkl", "wb"))
    c = collections.Counter(l["code"] for l in lots)
    print("lots by code", c.most_common(), "nocode rows", nocode)
    cf = collections.Counter((f["code"], f["kind"]) for f in fails)
    print("fails by code/kind", sorted(cf.items(), key=lambda x: -x[1])[:30])
    print(f"done ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
