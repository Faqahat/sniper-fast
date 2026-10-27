#!/usr/bin/env python3
# Owner 10-25 ~16:45 PKT: "wana check if the dumpers are related to dev/". Step 1 of 3 (local recording only, no RPC).
# Raw recording run_20261024_1425 (every pump.fun tx, 24 h) covers the launch of all 104 tokens we traded in out/fills.json.
#  pass 1: every tx touching one of those tokens, plus the txs in each token's launch Jito bundle (enrich.jsonl jito_create)
#  pass 2: for every wallet of interest (devs, dumpers, sellers while we held, launch-bundle / launch-window buyers):
#          the tokens it traded in those 24 h (bot vs dedicated wallet; does it keep trading the same creator's tokens?)
# out: out/scan1.json (per token), out/scan2.json (per wallet)
import json, gzip, base64, os, sys, glob
from multiprocessing import Pool
REC = "/home/moiz/sniper-data/collect/run_20261024_1425"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
TD = bytes.fromhex("bddb7fd34ee661ee")          # pump.fun TradeEvent
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); s = []
    while n: n, r = divmod(n, 58); s.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(s))
def trades(o):
    out = []
    for e in o.get("ev") or []:
        if " " in e: e = e.split()[-1]
        try: b = base64.b64decode(e[:len(e) // 4 * 4])
        except Exception: continue
        if b[:8] == TD and len(b) >= 89:
            out.append((b58(b[8:40]), b58(b[57:89]), b[56] == 1, int.from_bytes(b[40:48], "little")))   # mint, user, buy, lamports
    return out
FILES = sorted(glob.glob(f"{REC}/txs/*.jsonl.gz"))
def lines(fn):                       # the newest file can still be mid-copy (truncated gzip): read what is there
    try:
        for l in gzip.open(fn, "rt", errors="ignore"): yield l
    except (EOFError, OSError): return
G = {}
def p1(fn):
    M, BS = G["M"], G["BS"]; res = []
    for l in lines(fn):
        try: o = json.loads(l)
        except Exception: continue
        hit = [m for m in (o.get("mints") or []) if m in M]
        if not hit and o.get("sig") not in BS: continue
        res.append(dict(s=o["s"], i=o["i"], sig=o["sig"], err=o.get("err") is not None, signers=o.get("signers") or [],
                        create=any(x.startswith("Create") for x in o.get("ixn") or []), mints=hit, tr=trades(o)))
    return res
def p2(fn):
    W = G["W"]; act = {}
    for l in lines(fn):
        try: o = json.loads(l)
        except Exception: continue
        if o.get("err") is not None: continue
        sg = o.get("signers") or []
        tr = trades(o)
        us = set(sg) | {t[1] for t in tr}
        if not (us & W): continue
        for t in tr:
            if t[1] in W:
                a = act.setdefault(t[1], {})
                x = a.setdefault(t[0], [0, 0, 0, 0, o["s"]])     # buys, sells, buy lamports, sell lamports, first slot
                x[0 if t[2] else 1] += 1; x[2 if t[2] else 3] += t[3]
        for w in sg:                                            # signer of someone else's trade (fee payer / relayer)
            if w in W and not any(t[1] == w for t in tr):
                for t in tr: act.setdefault(w, {}).setdefault("signed:" + t[0], [0, 0, 0, 0, o["s"]])[0] += 1
    return act
def init(g): G.update(g)
if __name__ == "__main__":
    F = json.load(open(f"{OUT}/fills.json"))
    M = {r["mint"] for r in F}
    L = {}; ENR = {}
    for l in open(f"{REC}/launches.jsonl"):
        try: c = json.loads(l)
        except Exception: continue
        L[c["mint"]] = c
    for l in open(f"{REC}/enrich.jsonl"):
        try: c = json.loads(l)
        except Exception: continue
        if c["mint"] in M: ENR[c["mint"]] = c
    BS = set()
    for m, c in ENR.items():
        for x in [c.get("jito_create")] + [e.get("bundle") for e in c.get("jito_early") or []]:
            if x: BS.update(x.get("txs") or [])
    np = int(os.environ.get("NP", "14"))
    if not os.path.exists(f"{OUT}/scan1.json"):
        with Pool(np, init, ({"M": M, "BS": BS},)) as p: rs = [r for x in p.imap(p1, FILES, 2) for r in x]
        per = {m: [] for m in M}; bund = {}
        for r in rs:
            for m in r["mints"]: per[m].append(r)
            if r["sig"] in BS: bund[r["sig"]] = r
        for m in per: per[m].sort(key=lambda r: (r["s"], r["i"]))
        json.dump({"per": per, "bund": bund, "launch": {m: L.get(m) for m in M}, "enrich": ENR}, open(f"{OUT}/scan1.json", "w"))
        print("pass 1:", len(rs), "txs", flush=True)
    S1 = json.load(open(f"{OUT}/scan1.json"))
    W = set()
    for r in F:
        if r.get("dumper"): W.add(r["dumper"])
        W.update(t["user"] for t in r["trades"])
        c = L.get(r["mint"]) or {}
        W.update(x for x in (c.get("creator"), c.get("user"), c.get("payer")) if x)
    for m, rs in S1["per"].items():
        c0 = (S1["launch"].get(m) or {}).get("slot") or 0
        for r in rs:
            if r["s"] <= c0 + 30 or r["sig"] in BS:
                W.update(r["signers"]); W.update(t[1] for t in r["tr"])
    for r in S1["bund"].values():
        W.update(r["signers"]); W.update(t[1] for t in r["tr"])
    W -= M
    with Pool(np, init, ({"W": W},)) as p: parts = list(p.imap(p2, FILES, 2))
    act = {}
    for a in parts:
        for w, d in a.items():
            z = act.setdefault(w, {})
            for m, x in d.items():
                y = z.setdefault(m, [0, 0, 0, 0, x[4]])
                for k in range(4): y[k] += x[k]
                y[4] = min(y[4], x[4])
    creators = {m: c.get("creator") for m, c in L.items()}
    json.dump({"act": act, "creators": {m: creators.get(m.split(":")[-1]) for d in act.values() for m in d}}, open(f"{OUT}/scan2.json", "w"))
    print("pass 2:", len(W), "wallets of interest,", len(act), "seen", flush=True)
