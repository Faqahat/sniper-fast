#!/usr/bin/env python3
"""Profile one competitor from its own recent transactions: success rate and pace, fees vs profit (does it bid a share
of the profit?), tips and sender, version, cost of its failures, and, from the blocks, where it lands relative to the
trigger (the swap just before it on the same pool) and how its bid compares with the trigger's. Read-only RPC."""
import json, time, collections, statistics as S, sys, types
_ns = {}
exec(open("/root/arb-lab/takers.py").read().split('out = open("/root/arb-lab/runs/takers.jsonl"')[0], _ns)
T = types.SimpleNamespace(**_ns)

WHO = sys.argv[1]
N_TX = int(sys.argv[2]) if len(sys.argv) > 2 else 250
N_BLK = int(sys.argv[3]) if len(sys.argv) > 3 else 60
LISTS = {
    "jito": "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5 HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49 DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL 3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
    "helius": "4ACfpUFoaSD9bfPdeu6DBt89gB6ENTeHBXCAi87NhDEE D2L6yPZ2FmmmTKPgzaMKdhu6EWZcTpLy1Vhx8uvZe7NZ 9bnz4RShgq1hAnLnZbP8kbgBg1kEmcJBYQq3gQbmnSta 5VY91ws6B2hMmBFRsXkoAAdsPHBJwRfBht4DXox3xkwn 2nyhqdwKcJZR2vcqCyrYsaPVdAnFoJjiksCXJ7hfEYgD 2q5pghRs6arqVjRvT5gfgWfWcHWmw1ZuCzphgd5KfWGJ wyvPkWjVZz1M8fHQnMMCDTQDbkManefNNhweYk5WkcF 3KCKozbAaF75qEU33jtzozcJ29yJuaLJTy2jFdzUY8bT 4vieeGHPYPG2MmyPRcYjdiDmmhN3ww7hsFNap8pVN3Ey 4TQLFNWK8AovT1gFvda5jfw2oJeRMKEmw7aH6MGBJ3or",
}
TIPNAME = {}
for k in T.TIPS:
    TIPNAME[k] = next((n for n, l in LISTS.items() if k in l.split()), "astralane" if k.lower().startswith("astra") or k[:4] in ("Ax2J", "ASdX") else "bolt" if k[:2] in ("t1","t2","t3","t4","t5","t6","t7","t8","t9") else "lunar" if k.startswith("moon") else "?")
VENUES = {"pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "PumpSwap", "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "DLMM",
          "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "RayCPMM", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "RayAMMv4",
          "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG": "DAMMv2", "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "RayCLMM",
          "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Whirl", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "pump.fun"}
q = lambda v, p: sorted(v)[min(len(v) - 1, int(len(v) * p))] if v else None

# 1. recent signatures
sigs = []
before = None
while len(sigs) < N_TX:
    r = T.rpc("getSignaturesForAddress", [WHO, {"limit": 1000, **({"before": before} if before else {})}])
    if not r or "_error" in r or not r: break
    sigs += r
    before = r[-1]["signature"]
    if len(r) < 1000: break
sigs = sigs[:max(N_TX, 1000)]
okn = sum(1 for s in sigs if s["err"] is None)
span = (sigs[0]["blockTime"] - sigs[-1]["blockTime"]) / 60 if len(sigs) > 1 and sigs[0].get("blockTime") and sigs[-1].get("blockTime") else None
print(f"{WHO}: last {len(sigs)} txs over {span:.0f} min = {len(sigs)/span:.1f} tx/min; succeeded {okn} ({okn*100/len(sigs):.0f}%)" if span else f"{len(sigs)} txs")

# 2. transactions: fees vs profit, tips, version, venues, failures
wins, fails = [], []
for s in sigs[:N_TX]:
    tx = T.rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    time.sleep(0.03)
    if not tx or "_error" in tx or tx.get("meta") is None: continue
    f = T.facts(tx, -1, tx["slot"])
    m, t = tx["meta"], tx["transaction"]
    keys = t["message"]["accountKeys"] + m.get("loadedAddresses", {}).get("writable", []) + m.get("loadedAddresses", {}).get("readonly", [])
    f["tip_to"] = sorted({TIPNAME.get(k, "?") for i, k in enumerate(keys) if k in T.TIPS and i < len(m["postBalances"]) and m["postBalances"][i] > m["preBalances"][i]})
    inner = [keys[ix["programIdIndex"]] for g in m.get("innerInstructions") or [] for ix in g["instructions"]]
    f["venues"] = sorted({VENUES[p] for p in set(inner) | set(f["programs"]) if p in VENUES})
    f["nonce"] = any(keys[ix["programIdIndex"]] == "11111111111111111111111111111111" and T.b58d(ix["data"])[:4] == b"\x04\0\0\0" for ix in t["message"]["instructions"])
    f["alts"] = len(t["message"].get("addressTableLookups") or [])
    f["gross"] = f["signer_sol_wsol_change"] + f["fee"] + f["tip"]
    f["err"] = m["err"]
    (wins if f["ok"] and f["signer_sol_wsol_change"] > 0 else fails if not f["ok"] else []).append(f)
print(f"sampled {len(wins)} profitable wins, {len(fails)} failures")
for name, xs in (("WINS", wins), ("FAILURES", fails)):
    if not xs: continue
    g = lambda k: [x[k] or 0 for x in xs]
    print(f"  {name}: cu_price p10/p50/p90 {q(g('cu_price'),.1)}/{q(g('cu_price'),.5)}/{q(g('cu_price'),.9)} | priority fee p50 {q(g('priority_fee'),.5)} p90 {q(g('priority_fee'),.9)} | tip p50 {q(g('tip'),.5)} | cu limit p50 {q(g('cu_limit'),.5)} used p50 {q(g('cu_used'),.5)}")
    print(f"    versions {dict(collections.Counter(x['version'] for x in xs))} | tips to {dict(collections.Counter(tuple(x['tip_to']) for x in xs).most_common(4))} | nonce {sum(x['nonce'] for x in xs)} | uses ALTs {sum(1 for x in xs if x['alts'])} | venues {collections.Counter(tuple(x['venues']) for x in xs).most_common(4)}")
if wins:
    share = [x["priority_fee"] / x["gross"] for x in wins if x["gross"] > 0]
    print(f"  WINS: gross p50 {q([x['gross'] for x in wins],.5)} | net gain p50 {q([x['signer_sol_wsol_change'] for x in wins],.5)} | priority fee as share of gross p10/p50/p90 {q(share,.1):.2f}/{q(share,.5):.2f}/{q(share,.9):.2f}")
    # is the bid a fixed share of the gross?
    import math
    pts = [(math.log10(x["gross"]), math.log10(max(1, x["priority_fee"]))) for x in wins if x["gross"] > 0 and x["priority_fee"] > 0]
    if len(pts) > 3:
        mx, my = S.mean(p[0] for p in pts), S.mean(p[1] for p in pts)
        cov = sum((a - mx) * (b - my) for a, b in pts); vx = sum((a - mx) ** 2 for a, _ in pts); vy = sum((b - my) ** 2 for _, b in pts)
        print(f"  WINS: log(priority fee) vs log(gross): correlation {cov/math.sqrt(vx*vy):.2f}, slope {cov/vx:.2f} (1.0 = fee proportional to profit)")
if fails:
    print(f"  FAILURES: what a failure costs p50 {q([x['fee'] for x in fails],.5)} p90 {q([x['fee'] for x in fails],.9)} lamports; errors {collections.Counter(json.dumps(x['err'])[:70] for x in fails).most_common(4)}")

# 3. position after the trigger (the last earlier tx in the same block that touched one of the same pools)
pos = []
for f in wins[:N_BLK]:
    b = T.block(f["slot"])
    if not b or "_error" in b: continue
    txs = b["transactions"]
    me = next((i for i, x in enumerate(txs) if x["transaction"]["signatures"][0] == f["sig"]), None)
    if me is None: continue
    mykeys = f["keys"]
    trig = None
    for i in range(me - 1, -1, -1):
        x = txs[i]
        if x["meta"] is None: continue
        ks = set(x["transaction"]["message"]["accountKeys"]) | set(x["meta"].get("loadedAddresses", {}).get("writable", []))
        ks -= {"11111111111111111111111111111111", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "So11111111111111111111111111111111111111112", "ComputeBudget111111111111111111111111111111", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "SysvarRecentB1ockHashes11111111111111111111"}
        ks -= set(VENUES)
        if ks & mykeys:
            trig = T.facts(x, i, f["slot"]); break
    pos.append({"me": me, "n": len(txs), "trig": trig, "f": f})
if pos:
    withtrig = [p for p in pos if p["trig"]]
    gap = [p["me"] - p["trig"]["index"] for p in withtrig]
    print(f"POSITION ({len(pos)} wins with their block): earlier tx on the same pool in the block: {len(withtrig)}; index gap to it p50 {q(gap,.5)}, right behind it (gap 1) {sum(1 for g in gap if g==1)}, within 3 {sum(1 for g in gap if g<=3)}")
    print(f"  their position in block p50 {q([p['me'] for p in pos],.5)} of p50 {q([p['n'] for p in pos],.5)}; trigger signer is themselves {sum(1 for p in withtrig if p['trig']['signer']==WHO)}")
    rat = [p["f"]["cu_price"] / p["trig"]["cu_price"] for p in withtrig if p["trig"]["cu_price"] and p["f"]["cu_price"]]
    if rat: print(f"  their cu_price / trigger's p10/p50/p90 {q(rat,.1):.2f}/{q(rat,.5):.2f}/{q(rat,.9):.2f} (n={len(rat)}); within 0.85-1.0x: {sum(1 for r in rat if 0.85<=r<=1.0)}")
    print(f"  trigger tx: succeeded {sum(1 for p in withtrig if p['trig']['ok'])}/{len(withtrig)}; trigger v1 {sum(1 for p in withtrig if p['trig'].get('version')=='1')}")
