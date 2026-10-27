#!/usr/bin/env python3
# haqq SELL study, step 4: compact per-mint tapes from pass-2 rows. Per bucket -> /home/moiz/sniper-data/haqq/tp/b{bb}.pkl:
#   {mint: dict(W=[wallets], T=np.array (trades, chain order), F=np.array (failed txs), X=[non-trade tx rows])}
# T columns: s i j bt payer user buy sol tok vsol vtok pfee cfee fbps cbps txfee cup cul cu tips router(id)  (+ sigs list)
# Trades kept from the token's first recorded trade to the last haqq / our trade + 600 slots (~2 min).
import sys, os, json, gzip, glob, zlib, pickle, re
import numpy as np
from multiprocessing import Pool
OUT = "/home/moiz/sniper-data/haqq"; W = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
US = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
TC = ["s", "i", "j", "bt", "payer", "user", "buy", "sol", "tok", "vsol", "vtok", "pfee", "cfee", "fbps", "cbps", "txfee", "cup", "cul", "cu", "tips", "router"]
FC = ["s", "i", "bt", "payer", "kind", "code", "txfee", "cup", "tips", "router"]
OURM = set(json.load(open(f"{OUT}/our_mints.json")))
def work(b):
    T = {}; F = {}; X = {}; seenT = set(); seenF = set()
    for f in sorted(glob.glob(f"{OUT}/tape/b{b:02d}_*.jsonl.gz")):
        try:
            for line in gzip.open(f, "rt"):
                r = json.loads(line); k = r[0]; m = r[1]
                # base: s i bt sig payer fee cup cul cu tips router
                if k == "T":
                    key = (r[5], r[13])
                    if key in seenT: continue
                    seenT.add(key); T.setdefault(m, []).append(r)
                elif k == "F":
                    if (r[5], m) in seenF: continue
                    seenF.add((r[5], m)); F.setdefault(m, []).append(r)
                else:
                    if (r[5], m) in seenF: continue
                    seenF.add((r[5], m)); X.setdefault(m, []).append(r)
        except (EOFError, OSError, zlib.error): pass
    out = {}; nT = 0
    for m, rows in T.items():
        rows.sort(key=lambda r: (r[2], r[3], r[13]))
        users = [r[14] for r in rows]
        ends = [r[2] for r in rows if r[14] == W or r[14] in US or r[6] in US or r[6] == W]
        if not ends and m not in OURM: continue
        cut = (max(ends) + 600) if ends else None
        if cut is not None: rows = [r for r in rows if r[2] <= cut]
        wl = {}; rid = {}
        def wid(x):
            if x not in wl: wl[x] = len(wl)
            return wl[x]
        def rr(x):
            if x not in rid: rid[x] = len(rid)
            return rid[x]
        A = np.zeros((len(rows), len(TC)), np.int64)
        sigs = []
        for n, r in enumerate(rows):
            # ["T", m, s, i, bt, sig, payer, fee, cup, cul, cu, tips, router, j, user, buy, sol, tok, vsol, vtok, pfee, cfee, fbps, cbps]
            A[n] = (r[2], r[3], r[13], r[4] or 0, wid(r[6] or "?"), wid(r[14]), r[15], r[16], r[17], r[18], r[19], r[20], r[21], r[22] or 0, r[23] or 0,
                    r[7] or 0, r[8] or 0, r[9] or 0, r[10] or 0, r[11] or 0, rr(r[12] or ""))
            sigs.append(r[5][:16])
        fr = sorted(F.get(m, []), key=lambda r: (r[2], r[3]))
        if cut is not None: fr = [r for r in fr if r[2] <= cut]
        FA = np.zeros((len(fr), len(FC)), np.int64); fsig = []
        for n, r in enumerate(fr):
            # ["F", m, s, i, bt, sig, payer, fee, cup, cul, cu, tips, router, errjson, ixs]
            ix = r[14] or ""; kind = 1 if "Sell" in ix else (0 if "Buy" in ix else 2)
            mm = re.search(r'"Custom":(\d+)', r[13] or ""); code = int(mm.group(1)) if mm else -1
            FA[n] = (r[2], r[3], r[4] or 0, wid(r[6] or "?"), kind, code, r[7] or 0, r[8] or 0, r[11] or 0, rr(r[12] or ""))
            fsig.append(r[5][:16])
        xr = sorted(X.get(m, []), key=lambda r: (r[2], r[3]))
        if cut is not None: xr = [r for r in xr if r[2] <= cut]
        xr = [(r[2], r[3], r[6], r[13][:60]) for r in xr]
        out[m] = dict(W=list(wl), R=list(rid), T=A, sig=sigs, F=FA, fsig=fsig, X=xr)
        nT += len(rows)
    os.makedirs(f"{OUT}/tp", exist_ok=True)
    with open(f"{OUT}/tp/b{b:02d}.pkl", "wb") as f: pickle.dump(out, f, protocol=4)
    return b, len(out), nT
if __name__ == "__main__":
    P = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    with Pool(P) as p:
        for b, n, nT in p.imap_unordered(work, range(64)): print(b, n, nT, flush=True)
    print("DONE", flush=True)
