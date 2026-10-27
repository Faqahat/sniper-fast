#!/usr/bin/env python3
# Step 1f: do the launch-phase pre-placers target specific CREATORS? For each pre-placer: mints attempted (raw) -> their creators;
# distinct creators, top-creator share, how many of each creator's launches they attempted, and the creators' early-dump record.
import json, collections, gzip, glob
import numpy as np
import ps_common as C
S = [json.loads(l) for l in open(f"{C.OUT}/ps3b_streams.jsonl")]
PP = ["FUru6V3LoEKKmFBBKr61BsCtDh3w4RznMaQybvUaCjwQ", "5ZKd8DNBFMVedS3D1ZkHVuf8X2Ha9tsUTWJZErCrg9Vz", "8g1w4PNCHooeQbAhYbNAM9yv4pbQJthPRpiqSpiSeVQh",
      "CVPz447tBYu35RvN6qyySxJFVCXn7ULwGef3y2bWybvA", "5k2CkkiuGHJ1f9J7sTbL8QUebXadUm1mHBERbXVmMMDi", "5aGuLApcHJw9ixp7xW2pr3CHSqi8aGtq1FQSfHVJzx22",
      "2KtcBCfhU3LRB31M6pwdDAtmceqGMrUx5AnajQUANBou", "QqQ8Dkknvr5mau29eYRXunR1DcfvtHuzxgoBMpKLgUJ", "94iQuYjVgTwGXxtM7ywfpzfLvx3gN4oQRuc9osRE2pEm",
      "2iioYzMyn8Ahqfgqndp5ppVHUDcXF1px31Urs8wBaraq", "8jBZVkWzLBsBvbaMk7a3ykUaVDymoHJ9eeSCqN7b8bXC", "A9KKBdLy7VU8vrN8FZcVN5o4MmhkpFextqeKJX9ZZX2u"]
cre = {}; launches = collections.Counter(); early = collections.Counter(); devbuy = {}
for day in ("R1", "R2", "R3", "R4"):
    M = json.load(open(f"{C.DAYS[day]}/day_{day}_meta.json"))["meta"]
    for x in M:
        cre[x["m"]] = x.get("creator"); launches[x.get("creator")] += 1
# early creator dump per mint from the tapes: creator sells >= 2% within 50 slots of the create
for day in ("R1", "R2", "R3", "R4"):
    d = C.load(day, cols=("tok", "s", "buy", "uid", "sol", "tokn", "vsol", "vtok"))
    for t, x in enumerate(d["meta"]):
        if not x.get("creator"): continue
        o = int(d["off"][t]); n = int(d["cnt"][t]); u = C.crc(x["creator"])
        sl = slice(o, o + n)
        m = (d["uid"][sl] == u) & (d["buy"][sl] == 0) & (d["s"][sl] <= x["S0"] + 50) & (d["move"][sl] <= -2.0)
        if m.any(): early[x["creator"]] += 1
        db = (d["uid"][sl] == u) & (d["buy"][sl] == 1) & (d["s"][sl] == x["S0"])
        devbuy[x["m"]] = float(d["sol"][sl][db].sum() / 1e9)
tot_l = sum(launches.values()); print(f"launches in the 4 tapes: {tot_l}, creators {len(launches)}, creators with >= 3 launches {sum(1 for v in launches.values() if v >= 3)}")
out = {}
for w in PP:
    ms = {(r["day"], r["m"]) for r in S if r["w"] == w and (r["n_buy_att"] > 0 or r["n_buy_ok"] > 0)}
    cs = collections.Counter(cre.get(m) for _, m in ms)
    top = cs.most_common(5); ncre = len(cs)
    rep = sum(v for c, v in cs.items() if launches[c] >= 3)
    cov = [cs[c] / launches[c] for c, _ in top if c]
    db = [devbuy.get(m, 0.0) for _, m in ms]
    print(f"\n{w[:9]}: mints {len(ms)}, creators {ncre}, mints by creators with >= 3 launches {100 * rep / max(len(ms), 1):.0f}%, "
          f"top creators {[(c[:8] if c else None, v, launches[c], early[c]) for c, v in top]}")
    print(f"   dev buy SOL at create p25/50/75 {np.percentile(db, 25):.2f}/{np.percentile(db, 50):.2f}/{np.percentile(db, 75):.2f}; "
          f"creators' early-dump share over all their launches: {sum(early[c] for c in cs) / max(sum(launches[c] for c in cs), 1):.2f}")
    out[w] = dict(mints=len(ms), creators=ncre, rep_share=rep / max(len(ms), 1), top=[(c, v, launches[c], early[c]) for c, v in top])
allm = list(cre)
print(f"\nall launches: dev buy > 0 share {np.mean([devbuy.get(m, 0) > 0 for m in allm]):.2f}; creators' early dump share overall {sum(early.values()) / tot_l:.2f}")
json.dump(out, open(f"{C.OUT}/ps3e_creators.json", "w"), indent=1)
