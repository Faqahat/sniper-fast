#!/usr/bin/env python3
"""recover the full base58 of every cohort id (u64 = first 8 bytes) from DEV raw chunks: TradeEvent users + failed-tx signers.
Out: /home/moiz/sniper-data/flatperfect/cohort_full_b58.json"""
import json, gzip, base64, glob, sys
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatsig"); import flib as L
B58 = L.B58
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
ids = {int(x) for x in json.load(open(f"{L.D}/cohort.json"))["ids"]}
known = {L.pk64(w): w for w in json.load(open(f"{L.D}/cohort_b58.json"))["wallets"]}
want = ids - set(known)
def job(fn):
    got = {}
    try:
        with gzip.open(fn, "rt", errors="replace") as f:
            for l in f:
                d = json.loads(l)
                for s in d.get("signers") or []:
                    u = L.pk64(s)
                    if u in want: got[u] = s
                for e in d.get("ev") or []:
                    try: raw = base64.b64decode(e)
                    except Exception: continue
                    if len(raw) >= 89:
                        u = int.from_bytes(raw[57:65], "big")
                        if u in want: got[u] = b58(raw[57:89])
    except (EOFError, OSError, ValueError): pass
    return got
if __name__ == "__main__":
    files = sorted(glob.glob("/home/moiz/sniper-data/collect/run_202610*/txs/*.gz"))
    found = dict(known)
    with Pool(12) as p:
        for g in p.imap_unordered(job, files[::2]):
            found.update(g)
            if ids <= set(found): p.terminate(); break
    out = {"n": len(ids), "found": sum(1 for i in ids if i in found), "missing_u64": sorted(str(i) for i in ids if i not in found),
           "cohort": sorted(found[i] for i in ids if i in found), "named": sorted(L.NAMED), "ours_excluded": sorted(L.OURS)}
    json.dump(out, open("/home/moiz/sniper-data/flatperfect/cohort_full_b58.json", "w"), indent=1)
    print(out["n"], out["found"], out["missing_u64"])
