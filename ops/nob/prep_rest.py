#!/usr/bin/env python3
# after blk_rand: retry targets not parsed (-> rand_retry.json) and list random no-bundle launches for paths (-> paths_rand_targets.json)
import json
D = "/root/nob/"
ok = {}
for f in ("blk_rand.jsonl", "blk_rand2.jsonl"):
    try:
        for l in open(D + f):
            r = json.loads(l)
            if not r.get("missing"):
                ok[r["key"]] = r
    except FileNotFoundError:
        pass
tg = json.load(open(D + "rand_targets.json"))
retry = [t for t in tg if t["sig"] not in ok]
json.dump(retry, open(D + "rand_retry.json", "w"))
pt = [{"mint": r["mint"], "csig": r["csig"], "slot": r["slot"]} for r in ok.values()
      if not r["cx"].get("quote") and r["v0"] == 30_000_000_000 and r["gsol"] <= 300_000_000]
json.dump(pt, open(D + "paths_rand_targets.json", "w"))
print("parsed", len(ok), "retry", len(retry), "paths targets (std, no-bundle)", len(pt))
