#!/usr/bin/env python3
"""BOTS step 0 (read-only): signature map of haqq's LANDED txs, (slot, idx) -> sig, from the exec analyst's extraction
(haqq_dissect/exec/ext/*.jsonl, finished chunks) + haqq_strat/haqq_raw.jsonl. Used only for the example links.
Out: bots/hsigs.pkl"""
import glob, os, json, pickle
H = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
out = {}
files = [f for f in glob.glob("/home/moiz/sniper-data/haqq_dissect/exec/ext/*.jsonl") if os.path.exists(f + ".done")]
files.append("/home/moiz/sniper-data/haqq_strat/haqq_raw.jsonl")
for f in files:
    for l in open(f):
        if H not in l: continue
        try: d = json.loads(l)
        except Exception: continue
        if not d.get("signers") or d["signers"][0] != H or d.get("err") is not None: continue
        out[(d["s"], d["i"])] = d["sig"]
pickle.dump(out, open("/home/moiz/sniper-data/haqq_dissect/bots/hsigs.pkl", "wb"))
print(len(files), "files", len(out), "landed haqq txs")
