#!/usr/bin/env python3
# READ-ONLY, offline: dKMjeG's sending infrastructure from its own txs (ledger.json): routes, landing-service variants
# (lamport tag in the buy amount), tips / priority by service, nonce accounts, tx versions, CU, outcomes, soft-skips,
# slippage limits (min_tokens_out vs the curve state right after the dev's bundle, from the collector).
import json, collections, statistics as S, sys, os
HERE = "/home/moiz/sniper/ops/overnight/dkmjeg"; sys.path.insert(0, HERE)
from parse import b58d
L = json.load(open(os.path.join(HERE, "ledger.json"))); R = L["rows"]; T = L["tokens"]
q = lambda xs, p: round(sorted(xs)[int(p * (len(xs) - 1))], 5) if xs else None
B = [r for r in R if r["cat"] in ("buy", "failed buy", "router skip (no buy)")]
def dec(r):
    for d in r["router_data"] or []:
        raw = b58d(d)
        if len(raw) == 17 and raw[0] == 7: return int.from_bytes(raw[1:9], "little"), int.from_bytes(raw[9:17], "little")
        if len(raw) >= 24 and raw[:8].hex() == "e1f7501ed5b38488": return int.from_bytes(raw[8:16], "little"), int.from_bytes(raw[16:24], "little")
    return None, None
fam = collections.defaultdict(lambda: dict(n=0, cats=collections.Counter(), tags=collections.Counter(), tips=[], prio=[], cu=[], v=collections.Counter(), jdf=0))
for r in B:
    amt, mo = dec(r); r["amt"] = amt; r["minout"] = mo
    route = "ENFJAV router" if "ENFJAV" in r["tops"] else ("pump direct" if "pump" in r["tops"] and not (set(r["tops"]) & {"whirlpool", "raydium_clmm", "meteora_dlmm", "jupiter", "pumpswap"}) else "swap + pump (non-SOL quote)")
    svc = r["tips"][0][0] if r["tips"] else "none"
    f = fam[(route, svc)]; f["n"] += 1; f["cats"][r["cat"]] += 1; f["tips"].append(r["tipsum"]); f["prio"].append(r["prio"]); f["cu"].append(r["cu"] or 0); f["v"][str(r["v"])] += 1; f["jdf"] += int(bool(r["jdf"]))
    if amt: f["tags"][amt % 1000] += 1
print(f"buy-type txs signed by dK: {len(B)} ({dict(collections.Counter(r['cat'] for r in B))})")
print("route | landing service | txs | landed buy / failed / soft-skip | lamport tag in amount | tip med | priority med | CU med | version | jitodontfront")
for k, f in sorted(fam.items(), key=lambda kv: -kv[1]["n"]):
    print(f"{k[0]:28} {k[1]:18} {f['n']:4} | {f['cats']['buy']}/{f['cats']['failed buy']}/{f['cats']['router skip (no buy)']} | {f['tags'].most_common(3)} | {q(f['tips'], .5)} | {q(f['prio'], .5)} | {q(f['cu'], .5)} | {dict(f['v'])} | {f['jdf']}")
non = collections.Counter(r["nonce"] for r in B if r["nonce"])
print("\nbuy nonce accounts:", non.most_common())
S_ = [r for r in R if r["cat"] in ("sell", "failed sell")]
sn = collections.Counter(r["nonce"] for r in S_ if r["nonce"])
print(f"sell txs {len(S_)}: with nonce {sum(1 for r in S_ if r['nonce'])}, distinct sell nonces {len(sn)}, shared with buys {len(set(sn) & set(non))}")
print("sell landing:", collections.Counter((r["tips"][0][0] if r["tips"] else "none") for r in S_).most_common(), "| tip amounts", collections.Counter(round(r["tipsum"], 5) for r in S_).most_common(5),
      "| priority med", q([r["prio"] for r in S_], .5), "| versions", dict(collections.Counter(str(r["v"]) for r in S_)), "| CU med", q([r["cu"] or 0 for r in S_], .5))
ok = [r for r in B if r["cat"] == "buy"]
print(f"\nlanded buys {len(ok)}: CU med {q([r['cu'] for r in ok], .5)}, versions {dict(collections.Counter(str(r['v']) for r in ok))}")
print("buy fail reasons:", collections.Counter(((r["efail"] or "").split("Error Code: ")[1].split(".")[0] if "Error Code: " in (r["efail"] or "") else (r["efail"] or r["err"] or "")[:60]) for r in B if r["cat"] == "failed buy").most_common(6))
print("sell fail reasons:", collections.Counter(((r["efail"] or "").split("Error Code: ")[1].split(".")[0] if "Error Code: " in (r["efail"] or "") else (r["efail"] or r["err"] or "")[:60]) for r in S_ if r["cat"] == "failed sell").most_common(4))
fb = [r for r in B if r["cat"] == "failed buy"]; sk = [r for r in B if r["cat"] == "router skip (no buy)"]
print(f"failed buys {len(fb)} cost {sum(-r['val'] for r in fb):.3f} SOL (fee+tip that landed) | soft-skips {len(sk)} cost {sum(-r['val'] for r in sk):.3f}")
pings = [r for r in R if r["cat"] == "compute-budget only (ping)"]; cl = [r for r in R if r["cat"] == "close token acct"]
print(f"pings (compute-budget-only txs) {len(pings)}; token-account closes {len(cl)} (+{sum(r['val'] for r in cl):.3f} SOL rent back)")
# costs on landed buys
tot_tip = sum(r["tipsum"] for r in ok); tot_prio = sum(r["prio"] for r in ok); spend = sum(r["amt"] or 0 for r in ok) / 1e9
print(f"landing cost on landed buys: tips {tot_tip:.2f} + priority {tot_prio:.2f} = {tot_tip + tot_prio:.2f} SOL on {spend:.1f} SOL spent ({(tot_tip + tot_prio) / max(spend, 1e-9):.2%})")
sells_tip = sum(r["tipsum"] + r["prio"] for r in S_); print(f"sell-side landing cost: {sells_tip:.2f} SOL over {len(S_)} sell txs")
json.dump({r["sig"]: dict(amt=r["amt"], minout=r["minout"]) for r in B}, open(os.path.join(HERE, "buy_args.json"), "w"))
# any transfer out of the wallet in a landed trade that is NOT the curve payment and NOT a known tip = a possible bot fee
odd = collections.Counter()
for r in R:
    if r["cat"] not in ("buy", "sell") or not r["xo"]: continue
    t = json.load(open(os.path.join(HERE, "txc", r["sig"] + ".json"))); m = t["transaction"]["message"]
    acc = set()
    for ix in m["instructions"]:
        if ix.get("programId") in ("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", "ENFJAVp6hQWbzCbdRm69pUnuAmLgKPy18DiNg8fEDve8"): acc |= set(ix.get("accounts") or [])
    for inn in t["meta"].get("innerInstructions") or []:
        for ix in inn["instructions"]:
            if ix.get("programId") == "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": acc |= set(ix.get("accounts") or [])
    for d, l in r["xo"]:
        if d not in acc: odd[d] += l / 1e9
print("transfers out in landed trades that are neither the curve payment nor a known tip (possible bot fees):", [(d, round(v, 4)) for d, v in odd.most_common(8)] or "none")
