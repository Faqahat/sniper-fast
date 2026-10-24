#!/usr/bin/env python3
# READ-ONLY, offline: (1) position by the landing service of the copy that landed (R1/R2 launches, collector);
# (2) its slippage limit: min_tokens_out vs the expected fill at the curve state right after the dev's bundle.
import json, collections, statistics as S
L = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/ledger.json")); C = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/coll.json"))
A = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/buy_args.json"))
rows = {r["sig"]: r for r in L["rows"]}
g = collections.defaultdict(list)
for m, x in L["tokens"].items():
    if not x.get("buy_sig") or m not in C or "dk" not in C[m] or "ahead" not in C[m]["dk"]: continue
    r = rows[x["buy_sig"]]; svc = r["tips"][0][0] if r["tips"] else "none (priority only)"
    d = C[m]["dk"]; g[svc].append((d["ahead"], d["bslot"], C[m].get("first_out") == "dKMjeG", (d.get("ms") or [[None]])[0][0]))
print("landing service of the landed copy | buys (R1+R2) | first outside buyer | in create slot | outside buys ahead (median) | arrival in our feed, ms (median, n)")
for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
    ms = [z[3] for z in v if z[3] is not None]
    print(f"| {k} | {len(v)} | {sum(z[2] for z in v) / len(v):.0%} | {sum(1 for z in v if z[1] == 0) / len(v):.0%} | {S.median(z[0] for z in v):g} | {(str(round(S.median(ms), 1)) + ' (' + str(len(ms)) + ')') if ms else '-'} |")
q = lambda xs, p: round(sorted(xs)[int(p * (len(xs) - 1))], 3) if xs else None
res = collections.defaultdict(list)
for r in L["rows"]:
    if r["cat"] not in ("buy", "failed buy", "router skip (no buy)"): continue
    a = A.get(r["sig"]); m = r["mint"]
    if not a or not a.get("amt") or not a.get("minout") or m not in C: continue
    c = C[m]
    if not c.get("mc0") or not c["solq"]: continue
    P0 = c["mc0"] / 1e6; X = a["amt"] / 1.0125; V0 = 30e9 + (c["dev"] + c["gsol"]) * 1e9 / 1.0125
    res[r["cat"]].append((X / a["minout"]) / (P0 * (1 + X / V0)))
print("\nlimit price / expected average fill at the post-bundle curve state:")
for k, v in res.items(): print(f"   {k:22} n={len(v):4} p10 {q(v, .1)} p25 {q(v, .25)} median {q(v, .5)} p75 {q(v, .75)} p90 {q(v, .9)}")
