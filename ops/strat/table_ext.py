# Late-entry table (checkpoints 300..1200 s) from ext.jsonl + pipe.jsonl. Paper/offline.
import sys, json, pickle
sys.path.insert(0, "/root/strat")
from sim import *
CKE = [1386, 1940, 2771, 4157, 5543]
EXE = [("time", 30), ("time", 60), ("time", 120), ("time", 300), ("time", 600), ("trail", 0.2, 600), ("trail", 0.3, 600),
       ("tpsl", 1.5, 0.75, 600), ("tpsl", 2.0, 0.7, 600), ("trailtp", 0.2, 1.3, 0.75, 600)]
MH = {}
for l in open("/root/nob/ds.jsonl"):
    y = json.loads(l); MH[y["mint"]] = 1 if y.get("mayhem") else 0
P = {}
for l in open("/root/strat/pipe.jsonl"):
    x = json.loads(l); P[x["mint"]] = x
rows = []
for l in open("/root/strat/ext.jsonl"):
    e = json.loads(l)
    p = P.get(e["mint"])
    if not p or e.get("sig_err") or e.get("trunc"): continue
    x = dict(p)
    x["act"] = [a for a in p["act"] if a[0] <= 1300] + e["act2"]
    x["rows"] = [r for r in (p.get("rows") or []) if r[0] <= 1300] + e["rows"]
    x["cks"] = e["cks"]
    t = Tok(x)
    if not t.ds or not t.v0: continue
    mh = 1 if (p.get("mayhem") or MH.get(p["mint"])) else 0
    late = sum(k for d, k in p["act"] if d >= 2300)
    oldmax = max([r[1][-1][4] for r in (p.get("rows") or []) if r[1]] + [c[1] for c in (p.get("cks") or []) if len(c) > 1 and c[1]] + [t.v0]) / 1e9
    for dk in e.get("passed") or []:
        v = t.ck.get(dk)
        if not v: continue
        v /= 1e9
        if v >= 114.0 and not mh: continue
        n30 = t.n_upto(dk) - t.n_upto(dk - 140)
        if dk <= 1940:
            if n30 < 3: continue
        else:
            if late < 3 or n30 < 3: continue
        prev = [c for c in CKE if c < dk and t.ck.get(c)]
        vprev = t.ck[prev[-1]] / 1e9 if prev else None
        vmax = max([v] + [t.ck[c] / 1e9 for c in prev] + ([oldmax] if dk > 2780 else [max([r[1][-1][4] / 1e9 for r in (p.get("rows") or []) if r[1] and r[0] <= dk] + [t.v0 / 1e9])]))
        f = dict(T=round(dk * SLOT), v=v, v0=t.v0 / 1e9, dev=t.v0 / 1e9 - 30, dv=(v - vprev) if vprev else 0.0, vmax=vmax, dd=v / vmax, n30=n30,
                 n=t.n_upto(dk), dsell=sum(1 for d in t.devd if d <= min(dk, 2780)), mh=mh)
        f["n15"] = n30
        i = t.n_upto(dk) - 1
        f["gap"] = (dk - t.okd[i]) * SLOT if i >= 0 else 999
        pn = {}; pn2 = {}
        for X in (1.0, 2.0):
            for ex in EXE:
                r = trade(t, dk, X, ex); pn[(X, ex)] = r[0] / X if r else None
                r = trade(t, dk, X, ex, shift=True); pn2[(X, ex)] = r[0] / X if r else None
        rows.append(dict(mint=x["mint"], src=x["src"], bt=x["bt"], dk=dk, f=f, pn=pn, pn2=pn2))
meta = [(x["mint"], x["src"], x["bt"], x.get("stage"), x.get("nonsol", 0)) for x in P.values()]
pickle.dump((rows, meta), open("/root/strat/table_ext.pkl", "wb"))
print("ext rows", len(rows), "tokens", len({r["mint"] for r in rows}))
