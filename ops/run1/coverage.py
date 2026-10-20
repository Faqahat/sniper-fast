# READ-ONLY, zero cost: did the engine SEE every pump create? Sample every Kth slot in the window of an engine log,
# find all pump create events on chain, and check which mints the engine logged a DETECT for. For missed rule-#2-like
# creates (dev 0.5-8, bundle 3-5, any Lunar tip) print why (kind: top-level / router-CPI / other program).
# usage: python3 coverage.py <engine log> [K=6]
import sys, re, collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import get_block, events, is_vote, tx_summary, load_tipmap
TM = load_tipmap()
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
LOG = sys.argv[1]; K = int(sys.argv[2]) if len(sys.argv) > 2 else 6
txt = open(LOG, errors="replace").read()
seen = set(re.findall(r"DETECT feed=\S+ .*?mint=(\w+)", txt))
slots = [int(s) for s in re.findall(r"DETECT feed=\S+ first=1 .*?slot=(\d+)", txt)]
lo, hi = min(slots), max(slots)


def scan(slot):
    b = get_block(slot)
    if not (isinstance(b, dict) and "transactions" in b): return slot, None
    txs = [t for t in b["transactions"] if not is_vote(t)]
    out = []
    for i, t in enumerate(txs):
        meta = t.get("meta") or {}
        if meta.get("err") is not None: continue
        tr, cr = events(meta.get("logMessages"))
        for c in cr:
            m = c["mint"]
            msg = t["transaction"]["message"]
            keys = msg["accountKeys"]
            top = [keys[ix["programIdIndex"]] for ix in msg["instructions"] if ix["programIdIndex"] < len(keys)]
            kind = "top-level" if PUMP in top else ("cpi:" + ",".join(sorted({p[:8] for p in top if not p.startswith("ComputeB")})))
            dev = sum(e["sol"] for e in tr if e["mint"] == m and e["buy"]) / 1e9
            g = 0.0
            for t2 in txs[i + 1:]:
                m2 = t2.get("meta") or {}
                tr2, _ = events(m2.get("logMessages"))
                bb = [e for e in tr2 if e["mint"] == m and e["buy"]]
                if m2.get("err") is None and bb: g += sum(e["sol"] for e in bb) / 1e9
                else: break
            moon = any(str(x[2]).startswith("moon") for x in tx_summary(t, TM)[0]["tips"])
            out.append(dict(mint=m, kind=kind, dev=dev, gsol=g, moon=moon, alt=bool(msg.get("addressTableLookups"))))
    return slot, out


with ThreadPoolExecutor(6) as ex:
    res = [r for _, r in ex.map(scan, range(lo, hi + 1, K)) if r is not None]
creates = [c for r in res for c in r]
miss = [c for c in creates if c["mint"] not in seen]
print(f"window slots {lo}..{hi} ({hi - lo} slots), sampled every {K}: {len(res)} blocks, {len(creates)} creates on chain, engine saw {len(creates) - len(miss)} ({(len(creates) - len(miss)) / max(1, len(creates)):.1%})")
print("missed by kind:", collections.Counter(c["kind"] for c in miss).most_common(8))
print("seen by kind:  ", collections.Counter(c["kind"] for c in creates if c["mint"] in seen).most_common(8))
r2 = [c for c in creates if 0.49 <= c["dev"] <= 8.1 and 2.95 <= c["gsol"] <= 5.05 and c["moon"]]
print(f"rule-#2-like creates (dev 0.5-8, bundle 3-5, Lunar) in sample: {len(r2)}; MISSED by the engine: {sum(1 for c in r2 if c['mint'] not in seen)}")
for c in r2:
    if c["mint"] not in seen: print(f"   MISSED {c['mint']} kind {c['kind']} dev {c['dev']:.2f} bundle {c['gsol']:.2f} alt {c['alt']}")
