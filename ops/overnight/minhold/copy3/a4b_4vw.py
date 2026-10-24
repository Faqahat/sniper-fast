#!/usr/bin/env python3
# 4vw54BmA: its own address is flooded by other bots' txs, so its full history cannot be paged. Its trades come from the tapes and its
# token accounts' txs (raw/4vw54BmA_ata.jsonl.gz). Here: which token-account txs did it sign (sells after graduation on PumpSwap, token
# transfers), real PnL per token = native SOL + WSOL over all of its own txs of that token, and how many OTHER bots' txs touch its token
# accounts (copy bots reading its balance). -> out/4vw_tokens.json
import os, sys, json, gzip, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib3, a1_parse as AP
W = lib3.W3["4vw54BmA"]
own = []; others = collections.Counter(); other_payers = collections.Counter(); other_progs = collections.Counter()
def lines():
    for fn in ("raw/4vw54BmA_ata_a.jsonl.gz", "raw/4vw54BmA_ata_b.jsonl.gz"):
        try:
            for l in gzip.open(os.path.join(lib3.HERE, fn), "rt"): yield l
        except (EOFError, OSError): pass
seen = set()
for l in lines():
    try: t = json.loads(l)
    except Exception: continue
    if t["sig"] in seen: continue
    seen.add(t["sig"]); r = AP.parse(t, W); r["ata_mint"] = t.get("ata_mint")
    if r["payer"] == W or r["w_signer"]: own.append(r)
    else:
        others[r["ata_mint"]] += 1; other_payers[r["payer"]] += 1
        for p in r["top"]: other_progs[p[:8]] += 1
base = json.load(open(os.path.join(lib3.HERE, "out/chain_4vw54BmA.json")))
per = collections.defaultdict(lambda: dict(net=0.0, n=0, pumpswap=0, sells_after=0))
for r in base:
    for m in {e["mint"] for e in r["wev"]}: per[m]["net"] += (r["dn"] + r["dw"]) / 1e9; per[m]["n"] += 1
for r in own:
    m = r["ata_mint"]; per[m]["net"] += (r["dn"] + r["dw"]) / 1e9; per[m]["n"] += 1; per[m]["sells_after"] += 1
    if any(p.startswith("pAMMBay6") for p in r["inv"]): per[m]["pumpswap"] += 1
P = {p["m"]: p for p in json.load(open(os.path.join(lib3.HERE, "out/pos3.json"))) if p["w"] == "4vw54BmA" and not p.get("nobuy")}
op = [m for m, p in P.items() if p["open"]]
res = dict(own_ata_txs=len(own), other_bot_txs_on_its_token_accounts=sum(others.values()), tokens=len(per), other_payers=len(other_payers),
           top_other_payers=other_payers.most_common(8), top_other_programs=other_progs.most_common(8),
           open_positions=len(op), open_tape_mark=sum(P[m]["pnl"] for m in op), open_chain_real=sum(per[m]["net"] for m in op),
           open_detail=[(m[:8], round(P[m]["pnl"], 3), round(per[m]["net"], 3), per[m]["sells_after"], per[m]["pumpswap"]) for m in op],
           all_tokens_chain=sum(v["net"] for v in per.values()), closed_chain=sum(v["net"] for m, v in per.items() if m not in op))
json.dump(dict(summary=res, per={m: v for m, v in per.items()}), open(os.path.join(lib3.HERE, "out/4vw_tokens.json"), "w"), indent=1)
for k, v in res.items(): print(k, ":", v)
