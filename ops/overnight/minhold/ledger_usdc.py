#!/usr/bin/env python3
# ON-CHAIN TRUTH WITH WSOL (read-only RPC, endpoint never printed). Last N hours of a wallet: per tx, value change =
# native SOL change + change of the wallet-owned WSOL and USDC balances (USDC at SOLPX, default 101.7 USDC/SOL). Trade txs (pump trade
# event of this wallet) vs plain transfers; per-token PnL; win rate; failed-tx cost. usage: python3 -I ledger_wsol.py HOURS WALLET
import sys, os, json, time, base64, collections, statistics, urllib.request, concurrent.futures as cf
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
H, W = float(sys.argv[1]), sys.argv[2]; TD = bytes([189, 219, 127, 211, 78, 230, 97, 238]); WSOL = "So11111111111111111111111111111111111111112"; USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"; PX = float(os.environ.get("SOLPX", "101.7"))
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def rpc(m, p):
    for i in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.6 * (i + 1))
t0 = time.time() - H * 3600; sigs = []; before = None
while True:
    page = rpc("getSignaturesForAddress", [W, {"limit": 1000, **({"before": before} if before else {})}]) or []
    if not page: break
    sigs += [p for p in page if (p.get("blockTime") or 0) >= t0]; before = page[-1]["signature"]
    if (page[-1].get("blockTime") or 0) < t0 or len(page) < 1000: break
def one(p):
    t = rpc("getTransaction", [p["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t: return None
    meta = t["meta"]; la = meta.get("loadedAddresses") or {}; keys = t["transaction"]["message"]["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    i = keys.index(W) if W in keys else None
    nat = (meta["postBalances"][i] - meta["preBalances"][i]) if i is not None else 0
    ws = lambda L: sum(int(b["uiTokenAmount"]["amount"]) for b in (L or []) if b.get("mint") == WSOL and b.get("owner") == W)
    dws = ws(meta.get("postTokenBalances")) - ws(meta.get("preTokenBalances"))
    us = lambda L: sum(int(b["uiTokenAmount"]["amount"]) for b in (L or []) if b.get("mint") == USDC and b.get("owner") == W)
    dus = us(meta.get("postTokenBalances")) - us(meta.get("preTokenBalances"))          # micro-USDC
    dws += int(dus / 1e6 / PX * 1e9)                                                    # counted as SOL at PX USDC/SOL
    evs = []
    for l in meta.get("logMessages") or []:
        if l.startswith("Program data: "):
            x = l[14:].split()[0]; x += "=" * (-len(x) % 4)
            try: raw = base64.b64decode(x)
            except Exception: continue
            if raw[:8] == TD and len(raw) >= 113 and b58(raw[57:89]) == W: evs.append((b58(raw[8:40]), raw[56] == 1, int.from_bytes(raw[40:48], "little")))
    return dict(sig=p["signature"], bt=t.get("blockTime"), ok=meta["err"] is None, fee=meta["fee"], signer=keys[0] == W, nat=nat, dws=dws, evs=evs)
with cf.ThreadPoolExecutor(16) as ex: R = [r for r in ex.map(one, sigs) if r]
json.dump(R, open(f"/home/moiz/sniper/ops/overnight/minhold/ledu_{W[:8]}.json", "w"))
span = (max(r["bt"] for r in R) - min(r["bt"] for r in R)) / 86400 if R else 1
tr = [r for r in R if r["ok"] and r["evs"]]; oth = [r for r in R if r["ok"] and not r["evs"]]; bad = [r for r in R if not r["ok"] and r["signer"]]
toks = collections.defaultdict(float)
for r in tr: toks[r["evs"][0][0]] += (r["nat"] + r["dws"]) / 1e9
v = list(toks.values()); net = sum(v)
print(f"{W} | {len(R)} txs over {span*24:.1f} h | TRADING NET {net:+.2f} SOL = {net/span:+.1f}/day | tokens {len(v)} win {sum(x>0 for x in v)/max(len(v),1):.0%} "
      f"| WSOL/USDC-funded trade txs {sum(1 for r in tr if r['dws'])} of {len(tr)} | failed {len(bad)} cost {sum(r['fee'] for r in bad)/1e9:.3f} | transfers {sum(r['nat']+r['dws'] for r in oth)/1e9:+.2f}")
