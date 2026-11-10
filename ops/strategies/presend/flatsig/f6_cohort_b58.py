#!/usr/bin/env python3
"""FLATSIG: recover base58 addresses of the cohort ids (u64 prefixes) by decoding TradeEvent users in a sample of DEV raw chunks.
Out: /home/it/sniper-data/flatsig/cohort_b58.json and a copy next to this script (engine list)."""
import json, gzip, base64, glob, sys, os
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/replay4")
from ev import b58
D = "/home/it/sniper-data/flatsig"
ids = {int(x) for x in json.load(open(f"{D}/cohort.json"))["ids"]}
found = {}
files = sorted(glob.glob("/data/tapes/collect/run_20261030_1355/txs/*.gz"))[::6] + sorted(glob.glob("/data/tapes/collect/run_20261031_1350/txs/*.gz"))[::6]
for fn in files:
    with gzip.open(fn, "rt", errors="replace") as f:
        try:
            for l in f:
                if '"ev":["' not in l: continue
                d = json.loads(l)
                if d.get("err") is not None: continue
                for e in d.get("ev") or []:
                    try: raw = base64.b64decode(e)
                    except Exception: continue
                    if len(raw) < 89: continue
                    u = int.from_bytes(raw[57:65], "big")
                    if u in ids and u not in found: found[u] = b58(raw[57:89])
        except EOFError: pass
    if len(found) == len(ids): break
out = {"n": len(ids), "found": len(found), "wallets": sorted(found.values())}
json.dump(out, open(f"{D}/cohort_b58.json", "w"), indent=1)
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cohort_b58.json"), "w"), indent=1)
print(out["n"], out["found"])
