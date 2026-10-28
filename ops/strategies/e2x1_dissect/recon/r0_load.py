#!/usr/bin/env python3
"""recon step 0 (read-only): every recorded line mentioning E2x1 (local ext/ + server tail), deduped by sig -> rec.pkl {sig: rec}"""
import json, glob, pickle, collections
H = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"
OUT = "/home/moiz/sniper-data/e2x1_dissect/recon"
rec = {}
for f in sorted(glob.glob(f"{OUT}/ext/*.jsonl")) + [f"{OUT}/server_tail.jsonl"]:
    for l in open(f):
        try: d = json.loads(l)
        except Exception: continue
        if d["sig"] in rec and len(l) <= rec[d["sig"]].get("_len", 0): continue
        d["_len"] = len(l); rec[d["sig"]] = d
pickle.dump(rec, open(f"{OUT}/rec.pkl", "wb"))
S = json.load(open(f"{OUT}/sigs.json")); ss = {s["signature"]: s for s in S}
print("recorded", len(rec), "chain sigs", len(S), "recorded∩chain", len(set(rec) & set(ss)), "recorded not in chain list", len(set(rec) - set(ss)))
W0 = 1793113200; W1 = W0 + 86400
for name, a, b in (("D0 (10-26 20:00→10-27 20:00)", W0 - 86400, W0), ("D1 (10-27 20:00→10-28 20:00)", W0, W1)):
    cs = [s for s in S if s.get("blockTime") and a <= s["blockTime"] < b]
    print(name, "chain", len(cs), "failed", sum(1 for s in cs if s.get("err")), "recorded", sum(1 for s in cs if s["signature"] in rec),
          "missing ok", sum(1 for s in cs if s["signature"] not in rec and not s.get("err")), "missing failed", sum(1 for s in cs if s["signature"] not in rec and s.get("err")))
print("rec time range", min(d["bt"] for d in rec.values()), max(d["bt"] for d in rec.values()))
c = collections.Counter((d["signers"][0] == H, d["err"] is None, "|".join(sorted(set(d.get("ixn") or [])))) for d in rec.values())
for k, v in c.most_common(25): print(v, k)
