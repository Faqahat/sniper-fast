#!/usr/bin/env python3
"""recon step 0 (read-only): every raw-recording line that mentions haqq with block time in [W0-6h, end of recordings], deduped by sig.
Keeps the full record (s, i, bt, sig, err, fee, cup, signers, ixn, ev, tb, sd, tips).  Out: recon/rec.pkl = {sig: rec}"""
import json, glob, os, pickle, collections
H = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
W0, W1 = 1793038500, 1793124900
OUT = "/home/moiz/sniper-data/haqq_dissect/recon"
rec = {}; nl = 0
files = sorted(f for f in glob.glob("/home/moiz/sniper-data/haqq_dissect/exec/ext/*.jsonl") if os.path.exists(f + ".done"))
for f in files:
    try: ts = int(f.rsplit("_", 1)[1].split(".")[0])
    except ValueError: continue
    if ts < W0 - 6 * 3600 - 7200: continue
    for l in open(f):
        if H not in l: continue
        try: d = json.loads(l)
        except Exception: continue
        if not (W0 - 6 * 3600 <= d["bt"]): continue
        nl += 1
        d["_f"] = os.path.basename(f)
        if d["sig"] in rec:
            # keep the copy with more info
            if len(json.dumps(d)) <= len(json.dumps(rec[d["sig"]])): continue
        rec[d["sig"]] = d
pickle.dump(rec, open(f"{OUT}/rec.pkl", "wb"))
inw = [d for d in rec.values() if W0 <= d["bt"] < W1]
print(f"lines {nl:,}, unique sigs {len(rec):,}, in window {len(inw):,}")
print("signer0==haqq in window:", sum(1 for d in inw if d["signers"][0] == H))
print("has sd:", sum(1 for d in inw if d.get("sd") is not None), "haqq in sd:", sum(1 for d in inw if any(a == H for a, v in (d.get("sd") or []))))
c = collections.Counter((d["signers"][0] == H, d["err"] is None, "|".join(sorted(set(d.get("ixn") or [])))) for d in inw)
for k, v in c.most_common(40): print(v, k)
