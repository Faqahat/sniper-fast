# Build per-(token, checkpoint) feature + PnL table. Paper/offline.
import sys, json, pickle
sys.path.insert(0, "/root/strat")
from sim import *
R = load()
MH = {}
for l in open("/root/nob/ds.jsonl"):
    y = json.loads(l); MH[y["mint"]] = 1 if y.get("mayhem") else 0
rows = []; meta = []
for x in R:
    st = x.get("stage")
    nonsol = x.get("nonsol", 0)
    meta.append((x["mint"], x["src"], x["bt"], st, nonsol))
    if st != 4 or nonsol: continue
    t = Tok(x)
    if not t.ds: continue
    for dk in x.get("passed") or []:
        f = feats(t, dk)
        if f is None: continue
        mh = 1 if (x.get("mayhem") or MH.get(x["mint"])) else 0
        f["mh"] = mh
        if f["v"] >= 114.0 and not mh: continue   # curve complete (migrated): cannot buy on the curve
        pn = {}; pn2 = {}; mfe = None
        for X in (1.0, 2.0):
            for e in EXITS:
                r = trade(t, dk, X, e)
                pn[(X, e)] = r[0] / X if r else None
                r = trade(t, dk, X, e, shift=True)
                pn2[(X, e)] = r[0] / X if r else None
        i0 = t.st(dk + 2)
        if i0 is not None:
            p0 = t.vs[i0] / t.vt[i0]
            mfe = max([t.vs[j] / t.vt[j] for j in range(i0, len(t.ds)) if t.ds[j] <= dk + 2 + 1386] + [p0]) / p0
        rows.append(dict(mint=x["mint"], src=x["src"], bt=x["bt"], dk=dk, f=f, pn=pn, pn2=pn2, mfe=mfe))
pickle.dump((rows, meta), open("/root/strat/table.pkl", "wb"))
print("rows", len(rows), "launches", len(meta))
