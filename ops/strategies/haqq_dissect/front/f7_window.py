#!/usr/bin/env python3
"""FRONT step 7 (read-only): the full order around each paying dump from the window extraction (every recorded tx touching the
mint in slots [dump-2, dump+1], landed AND failed).
Per dump: the dump tx; every signer's failed txs on the mint BEFORE the dump in [dump-2, dump] (= pre-send signature) and after;
the front buyers' shape; our wallets' txs (tries/fires) and their position; the CU price of every landed buy between the dump and
our first landed try.
Out: sniper-data/haqq_dissect/front/f7.pkl"""
import json, glob, gzip, pickle, collections, sys, os
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8"); sys.path.insert(0, os.path.dirname(__file__))
import dv8lib as L
from f6_shape import shape
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
OURS = set(L.WAL.values())


def main():
    R = pickle.load(open(f"{OUT}/f1.pkl", "rb")); SE = pickle.load(open(f"{OUT}/f2_sets.pkl", "rb"))
    ids, _ = L.ids_map()
    want = collections.defaultdict(list)       # mint -> [(ds, di, i)]
    for i in SE["S"]:
        r = R[i]; want[ids[r["mint"]]].append((r["ds"], r["di"], i))
    W = collections.defaultdict(dict)          # mint -> {(s, i): rec}
    nf = 0
    for f in sorted(glob.glob(f"{OUT}/win/*.jsonl.gz")):
        try:
            for l in gzip.open(f, "rt"):
                d = json.loads(l)
                for m in (d.get("mints") or []):
                    if m in want: W[m][(d["s"], d["i"])] = d
                if not d.get("mints"):
                    pass
        except EOFError:
            pass
        nf += 1
    print(f"window files {nf}, mints with data {len(W):,}", flush=True)
    out = {}
    for m, lst in want.items():
        X = W.get(m)
        if not X: continue
        keys = sorted(X)
        for ds, di, i in lst:
            if (ds, di) not in X: continue
            win = [k for k in keys if ds - 2 <= k[0] <= ds + 1]
            pre = collections.Counter(); post = collections.Counter(); prel = collections.Counter()
            for k in win:
                d = X[k]; sg = d["signers"][0]
                if d.get("err") is not None:
                    if k < (ds, di): pre[sg] += 1
                    else: post[sg] += 1
                elif k < (ds, di) and any(x.startswith("Buy") for x in (d.get("ixn") or [])): prel[sg] += 1
            # ordered list after the dump within ds..ds+1
            after = []
            for k in win:
                if k <= (ds, di): continue
                d = X[k]; ixn = d.get("ixn") or []
                isbuy = any(x.startswith("Buy") for x in ixn); issell = any(x.startswith("Sell") for x in ixn)
                sg = d["signers"][0]
                after.append(dict(s=k[0], i=k[1], ok=d.get("err") is None, buy=isbuy, sell=issell, signer=sg, ours=sg in OURS,
                                  err=(str(d.get("err"))[:50] if d.get("err") else None), sh=shape(d), pre_fail=pre.get(sg, 0)))
            dump_sh = shape(X[(ds, di)])
            out[i] = dict(dump=dump_sh, after=after[:400], pre_fail=dict(pre.most_common(40)), n_pre_fail=sum(pre.values()), n_pre_signers=len(pre),
                          n_post_fail=sum(post.values()), ours_pre=sum(v for s_, v in pre.items() if s_ in OURS))
    pickle.dump(out, open(f"{OUT}/f7.pkl", "wb"))
    print(f"dumps with window data: {len(out):,} of {len(SE['S']):,}")


if __name__ == "__main__":
    main()
