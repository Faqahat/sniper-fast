#!/usr/bin/env python3
# 3GzBLpxT (and its group) — positions + full tapes of every token it traded, from the raw recordings (R1–R4, SOL- and quote-token curves).
# Per trade event: slot, index, user, side, token amount, vtok after (@105), vsol after (@97; 0 on quote-token curves).
# Per group tx: the signer's real SOL change (includes priority fees, tips, and the SOL->quote swap) = real cash.
# Output: g3.pkl.gz {tapes: mint -> rows, pos: list of 3GzB positions, quote: mint -> bool, u: mint -> price unit (quote curves)}
import json, glob, gzip, base64, pickle, collections
G = [l.strip() for l in open("grp.txt") if l.strip()]; GS = set(G); W = "3GzBLpxTWWTPWwBYQ8Jgrz5XLUCg9aY6HiB3GEBUBAv6"
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238]); B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
U8 = lambda raw, a: int.from_bytes(raw[a:a + 8], "little")
MS = set(l.strip() for l in open("mints.txt") if l.strip())
tapes = collections.defaultdict(dict); gtx = {}
for f in sorted(glob.glob("p2/*.jsonl")) + sorted(glob.glob("p1/*.jsonl")):
    run = {"run_20261021_2207": "R1", "run_20261022_1543": "R2", "run_20261023_1426": "R3", "run_20261024_1425": "R4"}[f.split("/")[1][:17]]
    for line in open(f):
        try: r = json.loads(line)
        except Exception: continue
        if str(r.get("err")) not in ("None", "null"): continue
        sg = (r.get("signers") or [None])[0]
        for j, e in enumerate(r.get("ev") or []):
            try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
            except Exception: continue
            if raw[:8] != TD or len(raw) < 129: continue
            m = b58(raw[8:40])
            if m not in MS: continue
            key = (int(r["s"]), int(r["i"]), j)
            tapes[m][key] = dict(s=key[0], i=key[1], j=j, bt=int(r.get("bt") or 0), sig=r["sig"], run=run, user=b58(raw[57:89]), buy=raw[56] == 1,
                                 sol=U8(raw, 40), tok=U8(raw, 48), vsol=U8(raw, 97), vtok=U8(raw, 105), signer=sg)
        if sg in GS:
            sd = dict((a, d) for a, d in (r.get("sd") or []))
            gtx[r["sig"]] = dict(signer=sg, dsol=sd.get(sg, 0), fee=int(r.get("fee") or 0), cup=r.get("cup"), tips=r.get("tips"), ixn=r.get("ixn"))
T = {m: sorted(v.values(), key=lambda t: (t["s"], t["i"], t["j"])) for m, v in tapes.items()}
quote = {m: (sum(1 for t in tr if t["vsol"] == 0) > len(tr) / 2) for m, tr in T.items()}
pos = []
for m, tr in T.items():
    mine = [t for t in tr if t["user"] == W]
    if not any(t["buy"] for t in mine): continue
    sigs = list(dict.fromkeys(t["sig"] for t in mine))
    cash = sum(gtx[s]["dsol"] for s in sigs if s in gtx) / 1e9
    tb = sum(t["tok"] for t in mine if t["buy"]); ts = sum(t["tok"] for t in mine if not t["buy"])
    fb = next(t for t in mine if t["buy"]); ls = [t for t in mine if not t["buy"]]
    pos.append(dict(m=m, run=fb["run"], bt=fb["bt"], s=fb["s"], quote=quote[m], cash=cash, closed=ts >= 0.98 * tb, nb=sum(1 for t in mine if t["buy"]), ns=len(ls),
                    hold=(ls[-1]["s"] - fb["s"]) * 0.212 if ls else None, sol_in=-sum(gtx[s]["dsol"] for s in sigs if s in gtx and gtx[s]["dsol"] < 0) / 1e9))
pos.sort(key=lambda p: p["bt"])
pickle.dump(dict(tapes=T, pos=pos, quote=quote, gtx=gtx), gzip.open("g3.pkl.gz", "wb"))
print(f"tokens with tapes: {len(T)} | 3GzB positions: {len(pos)} | closed on the curve: {sum(p['closed'] for p in pos)} | quote-token curves: {sum(p['quote'] for p in pos)}")
print(f"runs: {collections.Counter(p['run'] for p in pos)} | cash PnL all positions {sum(p['cash'] for p in pos):+.2f} SOL (open ones count only what was paid)")
