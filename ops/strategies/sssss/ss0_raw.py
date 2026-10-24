#!/usr/bin/env python3
# sssss fleet RAW tx profile (read-only) from sssss/raw/*.jsonl (scan_raw.sh: every recorded tx mentioning an "sssss..."
# address in R1-R4). Per wallet and run: tx counts, failures (by kind and error), fee / priority (cup) / CU limit / CU used,
# tips -> relay (ops/agents/tipmap.json), programs and instruction sequences, fee payer, failed-buy attempts (mint, slot,
# idx), SOL transfers in/out (funding). -> sssss/raw_profile.json + sssss/attempts.jsonl (failed buys/sells of sssssDdM)
import json, glob, os, collections, sys
import numpy as np
OUT = "/home/moiz/sniper-data/strategies/sssss"
TIP = json.load(open("/home/moiz/sniper/ops/agents/tipmap.json"))
FLEET = {"sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d": "DdM", "ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E": "wdk",
         "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi": "CUP", "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ": "yv2"}
RUNTAG = {"run_20261021_2207": "R1", "run_20261022_1543": "R2", "run_20261023_1426": "R3", "run_20261024_1425": "R4"}
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
def pct(x, ps=(10, 25, 50, 75, 90)):
    x = sorted(v for v in x if v is not None)
    return [round(x[min(len(x) - 1, int(p / 100 * len(x)))], 1) for p in ps] if x else None
def kind(r):
    ix = r.get("ixn") or []
    if any(x in ("Buy", "BuyExactSolIn", "BuyV2", "BuyExactSolInV2") for x in ix): return "buy"
    if any(x in ("Sell", "SellV2") for x in ix): return "sell"
    if any("Transfer" == x for x in ix): return "transfer"
    return "other:" + ",".join(sorted(set(ix)))[:60]

S = collections.defaultdict(lambda: collections.defaultdict(list)); C = collections.defaultdict(collections.Counter)
seen = set(); att = open(f"{OUT}/attempts.jsonl", "w"); funding = collections.defaultdict(collections.Counter)
for f in sorted(glob.glob(f"{OUT}/raw/*.jsonl")):
    run = RUNTAG.get(os.path.basename(f).split("__")[0], "?")
    for l in open(f):
        try: r = json.loads(l)
        except ValueError: continue
        if r.get("sig") in seen: continue
        seen.add(r.get("sig"))
        sg = r.get("signers") or []
        w = next((FLEET[s] for s in sg if s in FLEET), None)
        if w is None:
            # an sssss address appears only as an account: SOL sent to / from it by someone else
            for a, dl in r.get("sd") or []:
                if a in FLEET: funding[(run, FLEET[a])][("in-from-other" if dl > 0 else "out-by-other", kind(r))] += 1
            continue
        k = kind(r); key = (run, w); err = r.get("err")
        C[key][(k, "fail" if err else "ok")] += 1
        if err: C[key][("err", k, str(err)[:60])] += 1
        S[key][f"{k}_fee"].append(r.get("fee")); S[key][f"{k}_cup"].append(r.get("cup")); S[key][f"{k}_cul"].append(r.get("cul")); S[key][f"{k}_cu"].append(r.get("cu"))
        S[key][f"{k}_idx"].append(r.get("i"))
        tips = r.get("tips") or []
        C[key][("tip", k, TIP.get(tips[0][0], "unknown") if tips else "none")] += 1
        if tips: S[key][f"{k}_tip"].append(tips[0][1])
        C[key][("progs", k, ",".join(sorted(p[:6] for p in r.get("progs") or [])))] += 1
        C[key][("ixn", k, ",".join(r.get("ixn") or []))] += 1
        C[key][("payer_is_wallet", sg[0] in FLEET)] += 1
        C[key][("nsigners", len(sg))] += 1
        C[key][("nmints", k, len(r.get("mints") or []))] += 1
        if k == "transfer":
            for a, dl in r.get("sd") or []:
                if a not in FLEET and dl != 0: funding[key][("to" if dl > 0 else "from", a[:8])] += abs(dl) / 1e9
        if w == "DdM" and k in ("buy", "sell"):
            att.write(json.dumps(dict(run=run, s=r["s"], i=r["i"], bt=r.get("bt"), k=k, err=str(err)[:80] if err else None, mint=(r.get("mints") or [None])[0],
                                      fee=r.get("fee"), cup=r.get("cup"), cul=r.get("cul"), cu=r.get("cu"), tip=tips[0][1] if tips else 0,
                                      relay=TIP.get(tips[0][0], "unknown") if tips else None, sd=[x for x in r.get("sd") or [] if x[0] in FLEET])) + "\n")
att.close()
res = {}
for key in sorted(C):
    run, w = key; c = C[key]; s = S[key]
    o = dict(counts={f"{a}|{b}": n for (a, b), n in ((kk, v) for kk, v in c.items() if len(kk) == 2 and kk[0] in ("buy", "sell", "transfer") or (len(kk) == 2 and str(kk[0]).startswith("other")))})
    o["errors"] = [(f"{kk[1]} {kk[2]}", v) for kk, v in c.most_common() if kk[0] == "err"][:8]
    o["tips"] = [(f"{kk[1]} {kk[2]}", v) for kk, v in c.most_common() if kk[0] == "tip"][:10]
    o["progs"] = [(f"{kk[1]} {kk[2]}", v) for kk, v in c.most_common() if kk[0] == "progs"][:6]
    o["ixn"] = [(f"{kk[1]} {kk[2]}", v) for kk, v in c.most_common() if kk[0] == "ixn"][:8]
    o["payer_is_wallet"] = [(kk[1], v) for kk, v in c.items() if kk[0] == "payer_is_wallet"]
    o["nsigners"] = [(kk[1], v) for kk, v in c.items() if kk[0] == "nsigners"]
    o["nmints"] = [(f"{kk[1]} {kk[2]}", v) for kk, v in c.items() if kk[0] == "nmints"]
    for k in ("buy", "sell"):
        o[k] = {m: pct(s.get(f"{k}_{m}", [])) for m in ("fee", "cup", "cul", "cu", "tip", "idx")}
        o[k]["cup_values"] = collections.Counter(s.get(f"{k}_cup", [])).most_common(6)
        o[k]["fee_values"] = collections.Counter(s.get(f"{k}_fee", [])).most_common(6)
        o[k]["tip_values"] = collections.Counter(s.get(f"{k}_tip", [])).most_common(6)
    o["funding_transfers"] = funding[key].most_common(10)
    res[f"{run}|{w}"] = o
res["funding_by_others"] = {f"{k[0]}|{k[1]}": v.most_common(8) for k, v in funding.items() if len(k) == 2 and k[1] in FLEET.values() and k not in C}
json.dump(res, open(f"{OUT}/raw_profile.json", "w"), indent=1, default=str)
for k, v in res.items():
    if k == "funding_by_others": print("\nfunding by others:", v); continue
    print(f"\n=== {k}")
    for kk, vv in v.items(): print(f"   {kk}: {vv}")
