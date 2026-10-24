# our 69 live fires joined with the chain: where our tx landed vs the dump, who bought in between, the price path
import json, gzip, collections, sys
ME = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
fires = []; ev = collections.defaultdict(dict)
for n in range(1, 6):
    for l in open(f"/home/moiz/sniper/ops/dip/speed/dip_r{n}.jsonl"):
        try: d = json.loads(l)
        except Exception: continue
        e = d.get("ev")
        if e == "fire": d["run"] = n; fires.append(d)
        elif e in ("buy_land", "land_poll", "timing"): ev[e][d.get("sig") or d.get("buy_sig")] = d
mine = {}
for line in gzip.open("/home/moiz/sniper/ops/agents/topearners/work/txrows.jsonl.gz", "rt"):
    x = json.loads(line)
    if x["w"] == ME: mine[x["sig"]] = x
# race rows for our dump sigs
dsigs = {f["dump_sig"] for f in fires}
races = {}
for line in gzip.open("/home/moiz/sniper/ops/agents/topearners/work/races.jsonl.gz", "rt"):
    if not any(s in line[:400] for s in ()): pass
    r = json.loads(line)
    if r["sig"] in dsigs: races[r["sig"]] = r
json.dump(dict(fires=fires, mine=mine, races=races, ev={k: v for k, v in ev.items()}), open("/home/moiz/sniper/ops/agents/topearners/work/our_join.json", "w"))
print("fires", len(fires), "our chain txs", len(mine), "races found", len(races))
