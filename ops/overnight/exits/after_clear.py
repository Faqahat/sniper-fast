#!/usr/bin/env python3
# READ-ONLY, offline. MEASURED: what the price did AFTER the wallets' real losing clears (final sell below entry) and after
# their winning clears, on tokens with a market path: price N slots later vs the clear price, and the worst price later.
import sys, os, json, pickle, statistics, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
cases = pickle.load(open(os.path.join(EXITS, "cache", "cases.pkl"), "rb"))
out = collections.defaultdict(list)
for c in cases:
    W = WALLETS[c["w"]]; tr = c["tr"]
    own = [k for k, t in enumerate(tr) if t["user"] == W and not t["buy"]]
    if not own: continue
    k = own[-1]; t = tr[k]; p0 = tr[k - 1]["vsol"] / tr[k - 1]["vtok"]
    kb = next(i for i, x in enumerate(tr) if x["sig"] == c["rt"]["legs"][0]["sig"] and x["user"] == W)
    entry = tr[kb]["sol"] / tr[kb]["tok"]
    cls = "losing clear (< entry)" if p0 < entry else "winning clear (>= entry)"
    later = tr[k + 1:]
    if not later: continue
    def px_at(ds):
        xs = [x for x in later if x["s"] <= t["s"] + ds]
        return (xs[-1]["vsol"] / xs[-1]["vtok"]) if xs else p0
    span = later[-1]["s"] - t["s"]
    out[cls].append(dict(r30=px_at(141) / p0, r60=px_at(283) / p0, r300=px_at(1415) / p0, rmin=min(x["vsol"] / x["vtok"] for x in later) / p0,
                         rmax=max(x["vsol"] / x["vtok"] for x in later) / p0, span=span))
for cls, v in out.items():
    q = lambda key: [round(sorted(x[key] for x in v)[int(p * len(v))], 3) for p in (0.1, 0.25, 0.5, 0.75, 0.9)]
    print(f"{cls}: n={len(v)} | price 30 s later / clear price q10..q90 {q('r30')} | 60 s {q('r60')} | 5 min {q('r300')} | "
          f"worst later {q('rmin')} | best later {q('rmax')} | path observed after clear (slots) median {statistics.median(x['span'] for x in v)}")
