# after pass 1: the mints the group traded (from its own txs) -> mints.txt for pass 2
import json, glob
G = set(l.strip() for l in open("/home/moiz/sniper/ops/overnight/minhold/g3/grp.txt") if l.strip())
ms = set()
for f in glob.glob("/home/moiz/sniper/ops/overnight/minhold/g3/p1/*.jsonl"):
    for line in open(f):
        try: r = json.loads(line)
        except Exception: continue
        if (r.get("signers") or [None])[0] in G:
            for m in r.get("mints") or []: ms.add(m)
open("/home/moiz/sniper/ops/overnight/minhold/g3/mints.txt", "w").write("\n".join(sorted(ms)) + "\n")
print("mints traded by the group:", len(ms))
