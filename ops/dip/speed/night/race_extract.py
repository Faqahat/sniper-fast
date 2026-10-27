#!/usr/bin/env python3
# Chain-wide race study, step 1 (READ-ONLY, local raw recording): per 5-min file, every pump-relevant tx -> compact rows:
# (slot, idx, sig8, signer, ok, cup, cul, tips [(service, lamports)], buy_ix?, sell events [(mint, sol, user)], buy events / buy mints)
import sys, json, gzip, base64, glob, os
from multiprocessing import Pool
TIP = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tipmap.json")))
DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = A[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s
BUYIX = {"Buy", "BuyExactSolIn", "BuyExactQuoteIn", "BuyExactQuoteInV2", "BuyExactQuoteInV3", "BuyV2", "BuyV3"}
SELLIX = {"Sell", "SellV2", "SellV3"}
def one(fn):
    out = []
    try:
      with gzip.open(fn, "rt") as f:
        for l in f:
            if '"6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"' not in l: continue   # pump curve program only
            r = json.loads(l)
            ix = set(r.get("ixn") or [])
            trades = []
            for e in r.get("ev") or []:
                try: b = base64.b64decode(e)
                except Exception: continue
                if len(b) < 113 or b[:8] != DISC: continue
                u = lambda o: int.from_bytes(b[o:o + 8], "little")
                trades.append((b58(b[8:40]), u(40), u(48), b[56] == 1, b58(b[57:89]), u(97), u(105)))
            tips = [(TIP.get(a, "other"), lam) for a, lam in (r.get("tips") or [])]
            out.append((r["s"], r["i"], r["sig"][:12], (r.get("signers") or ["?"])[0], r.get("err") is None, r.get("cup"), r.get("cul"), tips,
                        bool(ix & BUYIX), bool(ix & SELLIX), r.get("mints") or [], trades, "CreateIdempotentAssociatedTokenAccount" in ix or "CreateAssociatedTokenAccount" in ix, r.get("bt")))
    except (EOFError, OSError, json.JSONDecodeError): pass     # the file being written: keep what is complete
    return out
if __name__ == "__main__":
    files = sorted(glob.glob(sys.argv[1] + "/txs_*.jsonl.gz"))
    with Pool(12) as p:
        res = p.map(one, files)
    rows = [x for r in res for x in r]
    rows.sort(key=lambda x: (x[0], x[1]))
    json.dump(rows, open(sys.argv[2] if len(sys.argv) > 2 else "race_rows.json", "w"))
    print("files", len(files), "pump txs", len(rows), "slots", rows[0][0], "->", rows[-1][0])
