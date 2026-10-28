#!/usr/bin/env python3
"""pos step 1b (read-only): haqq's per-tx CU-price code (cup mod 1000), fee+tips, CU price and tip path for EVERY haqq-signed tx in the
raw recordings, read from the exec analyst's extraction (haqq_dissect/exec/ext/*.jsonl, finished chunks only) + haqq_strat/haqq_raw.jsonl.
Out: haqq_dissect/pos/codes.pkl = {(slot, idx): (code, cost_sol, cup, err, kind, tip_accounts)}"""
import json, glob, os, pickle
H = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
out = {}
files = [f for f in glob.glob("/home/moiz/sniper-data/haqq_dissect/exec/ext/*.jsonl") if os.path.exists(f + ".done")]
files.append("/home/moiz/sniper-data/haqq_strat/haqq_raw.jsonl")
for f in files:
    for l in open(f):
        if H not in l: continue
        try: d = json.loads(l)
        except Exception: continue
        if not d.get("signers") or d["signers"][0] != H: continue
        ix = d.get("ixn") or []
        kind = "B" if any(x.startswith("Buy") for x in ix) else "S" if any(x.startswith("Sell") for x in ix) else "?"
        tips = d.get("tips") or []
        out[(d["s"], d["i"]) if d["err"] is None else ("F", d["sig"])] = ((d.get("cup") or 0) % 1000, (d["fee"] + sum(v for a, v in tips)) / 1e9,
                                                                        d.get("cup"), d["err"] is not None, kind, tuple(a for a, v in tips), d["bt"])
pickle.dump(out, open("/home/moiz/sniper-data/haqq_dissect/pos/codes.pkl", "wb"))
import collections
print(len(files), "files;", len(out), "haqq txs; failed", sum(1 for v in out.values() if v[3]))
bt = [v[6] for v in out.values()]
import time
print("bt range", time.strftime("%m-%d %H:%M", time.gmtime(min(bt) + 18000)), time.strftime("%m-%d %H:%M", time.gmtime(max(bt) + 18000)))
