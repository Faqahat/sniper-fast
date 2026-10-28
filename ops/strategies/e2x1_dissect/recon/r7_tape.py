#!/usr/bin/env python3
"""recon step 7 (read-only): compact tape of every pump trade + create on the mints E2x1 traded (from extm/*.jsonl.gz, the recordings
filtered by his mint list). Out: tape.pkl = dict(trades={mint: [rows]}, creates={mint: dict}) where a trade row is
(slot, idx, j, bt, user, signer0, buy, sol, tok, vsol, vtok, txfee, cup, relay, sig, ok) -- failed txs kept with ok=False (no event: sol=tok=0)."""
import json, gzip, glob, pickle, sys, os, hashlib
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r3_decomp import parse, chunks, DISC
OUT = "/home/moiz/sniper-data/e2x1_dissect/recon"
MINTS = set(open(f"{OUT}/mints.txt").read().split())
TIP = json.load(open(f"{OUT}/tipmap.json"))
CREATE_EV = hashlib.sha256(b"event:CreateEvent").digest()[:8]
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real")
from decode import parse_create
def one(fn):
    T = []; C = []; trunc = False
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                try: d = json.loads(line)
                except Exception: continue
                sg = (d.get("signers") or ["?"])[0]
                relay = "+".join(sorted({TIP.get(a, "?") for a, v in (d.get("tips") or [])})) or "none"
                tip = sum(v for a, v in (d.get("tips") or []))
                if d["err"] is not None:
                    ms = [m for m in (d.get("mints") or []) if m in MINTS]
                    if ms and any(x.startswith(("Buy", "Sell")) for x in (d.get("ixn") or [])):
                        T.append((ms[0], d["s"], d["i"], 0, d["bt"], sg, sg, "Buy" in "|".join(d.get("ixn") or []), 0, 0, 0, 0, d.get("fee"), d.get("cup"), relay, tip, d["sig"], False))
                    continue
                j = 0
                for b in chunks(d.get("ev")):
                    if b[:8] == DISC and len(b) >= 225:
                        e = parse(b)
                        if e["mint"] in MINTS:
                            T.append((e["mint"], d["s"], d["i"], j, d["bt"], e["user"], sg, e["buy"], e["sol"], e["tok"], e["vsol"], e["vtok"], d.get("fee"), d.get("cup"), relay, tip, d["sig"], True))
                        j += 1
                    elif b[:8] == CREATE_EV:
                        c = parse_create(b)
                        if c.get("mint") in MINTS:
                            c.update(slot=d["s"], idx=d["i"], bt=d["bt"], sig=d["sig"], payer=sg); C.append(c)
    except (EOFError, OSError) as ex:
        trunc = True
    return fn, T, C, trunc
if __name__ == "__main__":
    files = sorted(glob.glob(f"{OUT}/extm/*.jsonl.gz"))
    trades = {}; creates = {}; seen = set(); nt = 0
    with Pool(8) as p:
        for fn, T, C, tr in p.imap_unordered(one, files):
            if tr: print("TRUNC", fn, flush=True)
            for t in T:
                k = (t[16], t[3])
                if k in seen: continue
                seen.add(k); trades.setdefault(t[0], []).append(t[1:]); nt += 1
            for c in C: creates[c["mint"]] = c
    for m in trades: trades[m].sort()
    pickle.dump(dict(trades=trades, creates=creates, cols=("slot", "idx", "j", "bt", "user", "signer0", "buy", "sol", "tok", "vsol", "vtok", "txfee", "cup", "relay", "tip", "sig", "ok")),
                open(f"{OUT}/tape.pkl", "wb"))
    print("files", len(files), "trades", nt, "mints", len(trades), "creates", len(creates), "of", len(MINTS))
