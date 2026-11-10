#!/usr/bin/env python3
"""BUNDLEWAL step 3b [MEASURED features, no look-ahead]: the six variants, fixed BEFORE any scoring.
Inputs: trades_<rec>.pkl (TradeEvents + create slot), bal_<rec>.pkl (token balances of every tx on the mint, incl. plain
SPL transfers). Cutoffs as step 3: A = arm (T2: up to and incl. the trigger tx; rearm: slots < arm_slot), F = slots <= fill-1.
Holdings = latest post balance per owner from tx token balances (exact for every owner the recording saw; covers transfers).
Curve = the owner with the largest balance after the create tx; our wallets excluded.
  nl     : # ladder wallets still holding (first curve-buy SOL clustered: >= 3 wallets within 5%, buys >= 0.02 SOL) [hypothesis]
  cs     : % supply held now by owners who got tokens in the create slot
  nrecv  : # owners that received tokens by plain transfer (tx without a pump.fun TradeEvent) and still hold >= 0.05%
  precv  : % supply held by those transfer recipients
  eqbal  : # holders (>= 0.05%, not curve) whose balance sits in a cluster of >= 3 balances within 5% (ladder by balance)
  fam    : % supply held by the "bundle family" = create-slot owners + transfer recipients
Out: features2.jsonl"""
import json, pickle, glob, collections, sys
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/bundlewal")
from x3_features import feats as tfeats, OUT, OURS
SUP = 1e15
MINH = 0.0005 * SUP


def bfeats(rows, cs, curve):
    bal, csown, recv = {}, set(), set()
    for s, i, ht, sg, rr in rows:
        for own, pre, post in rr:
            if own == curve or own.startswith(OURS): continue
            if post > pre:
                if s == cs: csown.add(own)
                if not ht: recv.add(own)
            bal[own] = post
    hold = {o: b for o, b in bal.items() if b >= MINH}
    xs = sorted((b, o) for o, b in hold.items())
    eq, g = set(), []
    for b, o in xs + [(1e30, None)]:
        if g and b <= g[0][0] * 1.05: g.append((b, o)); continue
        if len(g) >= 3: eq.update(oo for _, oo in g)
        g = [(b, o)]
    rh = [o for o in recv if o in hold]
    fam = (csown | recv)
    return dict(cs=100 * sum(bal.get(o, 0) for o in csown) / SUP, nrecv=len(rh),
                precv=100 * sum(hold[o] for o in rh) / SUP, eqbal=len(eq),
                fam=100 * sum(bal.get(o, 0) for o in fam) / SUP, nhold=len(hold))


if __name__ == "__main__":
    T, CR, B = {}, {}, {}
    for f in sorted(glob.glob(f"{OUT}/trades_*.pkl")):
        d = pickle.load(open(f, "rb"))
        for m, v in d["trades"].items():
            if m not in T or len(v) > len(T[m]): T[m] = v
        CR.update(d["create"])
    for f in sorted(glob.glob(f"{OUT}/bal_*.pkl")):
        for m, v in pickle.load(open(f, "rb")).items():
            if m not in B or len(v) > len(B[m]): B[m] = v
    for m in B: B[m].sort(key=lambda x: (x[0], x[1]))
    o = open(f"{OUT}/features2.jsonl", "w"); cov = collections.Counter()
    for l in open(f"{OUT}/positions.jsonl"):
        p = json.loads(l)
        m = p["mint"]; tr = T.get(m); c = CR.get(m); br = B.get(m)
        ok = bool(tr) and bool(br) and c is not None and tr[0][0] >= c[0] and tr[0][0] - c[0] <= 2 and br[0][0] == c[0]
        cov[(p["split"], ok)] += 1
        if ok:
            cs = c[0]
            ct = [r for r in br if r[0] == cs]
            curve = max(((own, post) for r in ct for own, pre, post in r[4]), key=lambda x: x[1])[0]
            a_s, a_i = p["arm_slot"], p.get("arm_idx")
            if p["kind"] == "t2" and a_i is not None:
                inA = lambda s, i: s < a_s or (s == a_s and i <= a_i)
            else:
                inA = lambda s, i: s < a_s
            inF = lambda s, i: s <= p["fill_slot"] - 1
            for key, f in (("A", inA), ("F", inF)):
                x = tfeats([t for t in tr if f(t[0], t[1])], cs)
                y = bfeats([r for r in br if f(r[0], r[1])], cs, curve)
                p[key] = dict(nl=x["nl"], **y, vsol=x["vsol"], nbuyers=x["nbuyers"])
            p["age"] = a_s - cs
        p["cov"] = ok
        o.write(json.dumps(p) + "\n")
    print(dict(cov))
