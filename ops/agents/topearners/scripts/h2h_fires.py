# per our fire: each focus wallet's EARLIEST attempt (ok or failed) after the same dump vs our tx position
import json, gzip, collections
B = "/home/moiz/sniper/ops/agents/topearners/work/"
ME = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
J = json.load(open(B + "our_join.json")); mine = J["mine"]; races = J["races"]
fires = [f for f in J["fires"] if f["buy_sig"] in mine and f["dump_sig"] in races]
need = {}
for f in fires:
    r = races[f["dump_sig"]]; need[r["m"]] = need.get(r["m"], []) + [(r["s"], r["i"], f)]
att = collections.defaultdict(list)    # mint -> attempts of focus wallets
for line in gzip.open(B + "txrows.jsonl.gz", "rt"):
    x = json.loads(line)
    if x["w"] == ME or x["kind"] not in ("buy", "unk") or not x["mints"]: continue
    m = x["mints"][0]
    if m in need: att[m].append(x)
h2h = collections.defaultdict(lambda: [0, 0]); detail = []
for m, L in need.items():
    for (s0, i0, f) in L:
        us = mine[f["buy_sig"]]; up = (us["s"], us["i"])
        best = {}
        for x in att[m]:
            if (x["s"], x["i"]) <= (s0, i0) or x["s"] - s0 > 5: continue
            p = (x["s"], x["i"])
            if x["w"] not in best or p < best[x["w"]][0]: best[x["w"]] = (p, x["ok"], x["ec"])
        for w, (p, ok, ec) in best.items():
            h2h[w][0 if up < p else 1] += 1
            detail.append((f["buy_sig"][:8], w[:8], p[0] - s0, p[1] - i0 if p[0] == s0 else p[1], ok, ec, up[0] - s0, up[1] - i0 if up[0] == s0 else up[1], us["ok"]))
print("per-race head-to-head vs focus wallets' earliest attempt (ok OR failed): [we earlier, they earlier]")
for w, v in sorted(h2h.items(), key=lambda kv: -sum(kv[1]))[:20]: print("  ", w[:10], v)
json.dump(detail, open(B + "h2h_fires_detail.json", "w"))
