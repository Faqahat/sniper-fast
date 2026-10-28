#!/usr/bin/env python3
"""FRONT step 10 (read-only): broader pre-sender signature for front buyer #1 on paying dumps: the same signer sent ANY tx touching
the mint in [dump-2, dump) that did not trade (failed, OR succeeded without a pump Buy/Sell = conditional no-op). Uses the window
extraction (front/win). MEASURED. Out: sniper-data/haqq_dissect/front/f10.txt + f10.pkl (i -> flags)"""
import json, glob, gzip, pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
R = pickle.load(open(f"{OUT}/f8_rows.pkl", "rb")); ids, _ = L.ids_map()
want = collections.defaultdict(list)
for r in R:
    if r.get("splus"): continue
    want[r["mint"]].append(r)
pre = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0]))   # i -> signer -> [failed, noop, nslots]
for f in sorted(glob.glob(f"{OUT}/win/*.jsonl.gz")):
    try:
        for l in gzip.open(f, "rt"):
            d = json.loads(l)
            ms = d.get("mints") or []
            for m in ms:
                for r in want.get(m, ()):
                    if not (r["ds"] - 2 <= d["s"] and (d["s"], d["i"]) < (r["ds"], r["di"])): continue
                    ixn = d.get("ixn") or []
                    trade = any(x.startswith(("Buy", "Sell")) for x in ixn)
                    sg = d["signers"][0]
                    if d.get("err") is not None: pre[r["i"]][sg][0] += 1
                    elif not trade: pre[r["i"]][sg][1] += 1
    except EOFError:
        pass
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
flags = {}
for r in R:
    if r.get("splus"): continue
    sg = ids[r["f1"]["signer"]]; x = pre.get(r["i"], {}).get(sg)
    flags[r["i"]] = dict(failed=bool(x and x[0]), noop=bool(x and x[1]), any=bool(x and (x[0] or x[1])),
                         n_presenders=sum(1 for v in pre.get(r["i"], {}).values() if v[0] or v[1]))
pickle.dump(flags, open(f"{OUT}/f10.pkl", "wb"))
g = [r for r in R if r["i"] in flags]
P(f"# Front buyer #1 pre-sender signature on paying dumps (n {len(g):,}; window data)")
for nm, sel in (("all", lambda r: True), ("front #1 <= 3 ms after dump", lambda r: r["f1"]["ms"] <= 3), ("3-15 ms", lambda r: 3 < r["f1"]["ms"] <= 15),
                ("15-40 ms", lambda r: 15 < r["f1"]["ms"] <= 40), ("> 40 ms", lambda r: r["f1"]["ms"] > 40)):
    x = [flags[r["i"]] for r in g if sel(r)]
    if not x: continue
    P(f"- {nm}: n {len(x):,}; failed try before dump {100*np.mean([f['failed'] for f in x]):.0f}%, no-op tx before dump {100*np.mean([f['noop'] for f in x]):.0f}%, "
      f"either {100*np.mean([f['any'] for f in x]):.0f}%; pre-sending signers on the mint p50 {np.median([f['n_presenders'] for f in x]):.0f}")
for cl in ("bam", "harmonic", "jito", "fd"):
    x = [flags[r["i"]] for r in g if r["client"] == cl]
    P(f"- client {cl}: n {len(x):,}; front #1 is a pre-sender (failed or no-op before) {100*np.mean([f['any'] for f in x]):.0f}%")
for rg in ("EU", "US-East", "Asia"):
    x = [flags[r["i"]] for r in g if r["region"] == rg]
    P(f"- region {rg}: n {len(x):,}; front #1 pre-sender {100*np.mean([f['any'] for f in x]):.0f}%")
x = [(flags[r["i"]]["any"], r["v"]) for r in g]
P(f"- value share of paying dumps whose front #1 was a pre-sender: {100*sum(v for a, v in x if a)/sum(v for a, v in x):.0f}%")
open(f"{OUT}/f10.txt", "w").write("\n".join(out) + "\n")
