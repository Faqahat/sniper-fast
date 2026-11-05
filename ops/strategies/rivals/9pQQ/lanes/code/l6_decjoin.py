#!/usr/bin/env python3
"""LANES step 6: classify every RPC-sampled 9pQQ BUY by the curve state its min_tokens_out was priced on
(min_out = E_buy(state)/1.15 exactly, |err|<1e-8):
  EXACT0 = latest landed state before its tx; EXACTk = k landed trades back; PHANTOM = no landed state in the 400 slots before.
For PHANTOM: dec_dev = implied price at decision / landing pre-state price - 1.  Joins to trips (by buy sig). -> lanes/decjoin.pkl"""
import sys, json, math, pickle, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/rivals/9pQQ/lanes/code")
import llib, rpcdec
K, V = llib.K, llib.V
rpc = collections.defaultdict(list)
for f in sys.argv[1:]:
    for l in open(f):
        d = json.loads(l); rpc[d["run"]].append(d)
out = []
for run in llib.RUNS:
    if run not in rpc: continue
    t = llib.load(run)
    trips = {r["bsig"]: r for r in pickle.load(open(f"{llib.D}/trips_{run}.pkl", "rb"))["rows"]}
    for d in rpc[run]:
        o = rpcdec.dec(d["tx"])
        if o.get("pdisc") != "e1f7501ed5b38488": continue
        keys = d["tx"]["transaction"]["message"]["accountKeys"]
        cand = [k for k in keys if k in t.mix and not k.startswith("So1111")]
        if not cand: continue
        m = t.mix[cand[0]]
        X = o["pargs"][0]; x = {700000000: 691358023, 480000000: 474074074}[X]
        tgt = o["pargs"][1] * 1.15
        cstar = (tgt * x + math.sqrt((tgt * x) ** 2 + 4 * x * tgt * K)) / (2 * x) - V
        a, b = t.ms[m], t.ms[m + 1]; s, i = d["s"], d["i"]
        key = t.s[a:b].astype(np.int64) * 100000 + t.i[a:b]
        pos = int(np.searchsorted(key, s * 100000 + i))
        lo = int(np.searchsorted(t.s[a:b], s - 400))
        cp = t.cpost[a + lo:a + pos].astype(float)
        if not len(cp): continue
        land = cp[-1]
        rel = np.abs(cp - cstar) / cstar
        hit = np.nonzero(rel < 1e-8)[0]
        rec = dict(run=run, sig=d["sig"], kind=d["kind"], s=s, i=i, X=X)
        pland = (K / (land + V)) / (land + V); pstar = (K / (cstar + V)) / (cstar + V)
        rec["dec_dev"] = pstar / pland - 1
        if len(hit):
            j = hit[-1]; back = len(cp) - 1 - j; kk = a + lo + j
            rec.update(cls="EXACT0" if back == 0 else "EXACTk", back=int(back), st_ds=int(s - t.s[kk]), st_di=int(i - t.i[kk]) if t.s[kk] == s else None,
                       st_u=t.users[t.u[kk]], st_own=bool(t.u[kk] == t.wid), st_dv=float(K / (t.cpost[kk] + V) - K / (t.cpre[kk] + V)) / 1e9)
        else:
            rec["cls"] = "PHANTOM"
            # nearest landed state in price terms, and whether c* lies outside the recent range
            rec["near"] = float(rel.min()); rec["near_back"] = int(len(cp) - 1 - rel.argmin())
            last10 = cp[-10:]
            rec["outside_range"] = bool(cstar < last10.min() or cstar > last10.max())
        tr = trips.get(d["sig"])
        if tr: rec["trip"] = tr
        out.append(rec)
    del t
pickle.dump(out, open(f"{llib.D}/decjoin.pkl", "wb"))
C = collections.Counter((r["kind"], r["cls"]) for r in out); print(C)
