#!/usr/bin/env python3
"""print trip k's tape: 6 trades before buy .. sell + 4 after (outside trades with ret/dd). usage RUN MINT k [k..]"""
import sys, json, gzip
D = "/home/it/sniper-data/rivals/9pQQ/casebook"
run, m = sys.argv[1], sys.argv[2]
R = [json.loads(l) for l in gzip.open(f"{D}/tapes/{run}/{m}.ev.jsonl.gz", "rt")]
own = [k for k, r in enumerate(R) if r["own"]]
for k in map(int, sys.argv[3:]):
    a, b = own[2 * (k - 1)], own[2 * (k - 1) + 1]
    print(f"--- T{k}")
    emc = R[a]["mc"]
    for r in R[max(0, a - 6):b + 5]:
        tag = ">>" if r["own"] else ("*S" if r.get("trig") == "S" else ("*B" if r.get("trig") == "B" else "  "))
        print(f"{tag} +{r['age']:<6} {r['i']:>4} {'B' if r['buy'] else 'S'} {r['sol']:7.3f} {r['u'][:5]} uc{r['ucnt']:<3} {r['pr'][:12]:12s} mc {r['mc']:6.1f} ret {100*(r['mc']/emc-1):6.1f} sob {r['since_ob']}")
