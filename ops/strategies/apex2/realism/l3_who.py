#!/usr/bin/env python3
"""Who was ahead of us: per signer, early-buy breadth over the whole day-7 tape (distinct creators where the signer buys in
cs..cs+1 non-bundle) and repeat count with the same creator.  Prints table."""
import json, collections, numpy as np
TAB = "/home/moiz/sniper-data/apex2/realism/tab/run_20261103_1245"
X = json.load(open("/home/moiz/sniper-data/apex2/realism/live_tape.json"))
T = np.load(f"{TAB}/trades.npy"); ids = json.load(open(f"{TAB}/ids.json")); C = json.load(open(f"{TAB}/creates.json"))
std = {m: c for m, c in C.items() if c.get("std")}
gid = {k: i for i, k in enumerate(ids)}
mint_cs = np.full(len(ids), -1, np.int64); mint_cr = {}
for m, c in std.items():
    if m in gid: mint_cs[gid[m]] = int(c["slot"]); mint_cr[gid[m]] = c["creator"]
cs = mint_cs[T["mint"]]
e = (cs >= 0) & (T["buy"] == 1) & (T["slot"].astype(np.int64) <= cs + 1) & (T["syn"] == 0)
E_ = T[e]
by_signer = collections.defaultdict(set); by_sc = collections.Counter()
for s, mm in zip(E_["signer"].tolist(), E_["mint"].tolist()):
    cr = mint_cr[mm]
    if (s, mm) in by_sc: continue
    by_sc[(s, mm)] = 1; by_signer[ids[s]].add(cr)
pair = collections.Counter()
for (s, mm) in by_sc: pair[(ids[s], mint_cr[mm])] += 1
ncre = collections.Counter(c["creator"] for c in std.values())
json.dump({"breadth": {k: len(v) for k, v in by_signer.items()}, "pair": {f"{a}|{b}": n for (a, b), n in pair.items()}},
          open("/home/moiz/sniper-data/apex2/realism/signer_breadth_d7.json", "w"))
for x in X:
    if not x["ahead"]: continue
    cr = x["creator_ev"]
    print(f'{x["run"]}.{x["id"]} {x["outcome"][:4]} {x["cls"][:4]} creator={cr[:6]} (launches today {ncre[cr]}) ours clk {x["ours_tape"]["clk"]:.3f}')
    for a in x["ahead"][:6]:
        sg = a["signer"]
        print(f'    {sg[:8]} s{a["s"]} i{a["i"]} clk {a["clk"]:.3f} fee {a["fee"]/1e6:.3f} tips {a["tips"]/1e6:.2f} sol {a["sol"]:.2f} '
              f'breadth {len(by_signer.get(sg, ()))} w/creator {pair.get((sg, cr), 0)}')
