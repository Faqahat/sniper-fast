#!/usr/bin/env python3
# Accounts that receive small SOL amounts (<= 0.05 SOL) from many distinct signers across the recording (R_ files),
# minus the tip accounts we know (catalogue + engine registry). Candidates for tip accounts of services we do not know.
import json, glob, collections, sys
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
CAT = json.load(open("/home/moiz/sniper/data/sender-tip-accounts.json"))
for svc, v in CAT.items():
    if isinstance(v, dict):
        for a in v.get("tip_accounts") or []: TIP.setdefault(a, svc)
agg = collections.defaultdict(lambda: [0, 0, 0, 0])   # n txs, sum of per-chunk distinct signers, lamports, chunks
for f in glob.glob("/home/moiz/sniper-data/landing2/x_r*/R_*.json"):
    for a, (n, ns, tot) in json.load(open(f)).items():
        x = agg[a]; x[0] += n; x[1] += ns; x[2] += tot; x[3] += 1
rows = sorted(agg.items(), key=lambda kv: -kv[1][1])
print("known tip accounts seen:", sum(1 for a, _ in rows if a in TIP))
print("\nTOP unknown recipients (by distinct signers summed over chunks):")
k = 0
for a, (n, ns, tot, ch) in rows:
    if a in TIP: continue
    print(f"  {a:44s} txs {n:8d} signers~{ns:7d} chunks {ch:3d} avg {tot/n/1e9:.6f} SOL")
    k += 1
    if k >= 70: break
print("\nKNOWN services by txs:")
c = collections.Counter(); s = collections.Counter()
for a, (n, ns, tot, ch) in rows:
    if a in TIP: c[TIP[a]] += n; s[TIP[a]] += tot
for svc, n in c.most_common(): print(f"  {svc:24s} txs {n:8d} SOL {s[svc]/1e9:9.3f}")
