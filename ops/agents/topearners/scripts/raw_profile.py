#!/usr/bin/env python3
# read-only: per-wallet SEND profile from the raw txs extracted for the focus wallets (work/raw/*.jsonl.gz).
# Writes work/txrows.jsonl.gz: one compact row per (focus wallet, tx) for later joins, and prints nothing.
import os, sys, json, gzip, glob, collections, base64
from multiprocessing import Pool
W = set(l.strip() for l in open(sys.argv[1]) if l.strip())
TIP = json.load(open("/home/moiz/sniper/ops/agents/tipmap.json"))
STD = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
       "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
       "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", "MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e"}
TRADE = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def relay(k):
    if k in TIP: return TIP[k]
    if k.startswith("noz"): return "nozomi"
    return "?"
def work(path):
    out = []
    try:
        for line in gzip.open(path, "rt"):
            try: r = json.loads(line)
            except Exception: continue
            sg = r.get("signers") or []
            fw = [x for x in sg if x in W]
            if not fw: continue
            ixn = r.get("ixn") or []
            kind = "buy" if any(x.startswith("Buy") for x in ixn) else ("sell" if any(x.startswith("Sell") for x in ixn) else "unk")
            evs = []
            for e in r.get("ev") or []:
                try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
                except Exception: continue
                if raw[:8] == TRADE and len(raw) >= 225:
                    u = lambda o: int.from_bytes(raw[o:o + 8], "little")
                    evs.append([b58(raw[8:40]), raw[56], b58(raw[57:89]), u(40), u(48), u(97), u(105)])
            if evs: kind = "buy" if evs[0][1] == 1 else "sell"
            err = r.get("err"); ec = None
            if err:
                ie = err.get("InstructionError") if isinstance(err, dict) else None
                if ie: ec = [ie[0], ie[1].get("Custom") if isinstance(ie[1], dict) else str(ie[1])]
                else: ec = [None, str(err)[:40]]
            tips = [[relay(k), d, k] for k, d in r.get("tips") or []]
            progs = [p for p in r.get("progs") or [] if p not in STD]
            for w in fw:
                out.append(dict(w=w, s=r["s"], i=r["i"], bt=r.get("bt"), sig=r["sig"], ok=err is None, ec=ec, kind=kind, fee=r.get("fee"), cup=r.get("cup"),
                                cul=r.get("cul"), cu=r.get("cu"), nsig=len(sg), payer=sg[0], wpos=sg.index(w), tips=tips, progs=progs, ixn=ixn[:10],
                                mints=r.get("mints") or [], evs=evs, sdw=dict(r.get("sd") or []).get(w)))
    except (EOFError, OSError): pass
    return out
if __name__ == "__main__":
    files = sorted(glob.glob(sys.argv[2] + "/*.jsonl.gz"))
    fo = gzip.open(sys.argv[3], "wt", compresslevel=3); n = 0
    with Pool(4) as p:
        for rows in p.imap(work, files):
            for x in rows: fo.write(json.dumps(x, separators=(",", ":")) + "\n"); n += 1
    fo.close(); print("DONE", n)
