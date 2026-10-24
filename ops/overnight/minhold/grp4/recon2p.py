# 2pLugeBD: why gmgn shows ~+$1–3K/day realized while 24 h cash flow is ~+1.6–3.3 SOL. Splits the window's cash flow into
# tokens bought+sold in the window (realized), bags bought but not sold, and tokens bought before the window but sold in it.
import json, os, urllib.request, time, collections
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p):
    for i in range(6):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(), headers={"content-type":"application/json"}), timeout=60)).get("result")
        except Exception: time.sleep(2*(i+1))
U = "2pLugeBDKkFxaD2JKxSifNXoegYQyVpVoFikc6SEdqdv"; WSOL="So11111111111111111111111111111111111111112"
R = json.load(open("/home/moiz/sniper/ops/overnight/minhold/ledw_2pLugeBD.json"))
print("window", time.strftime("%m-%d %H:%M", time.gmtime(min(r["bt"] for r in R)+18000)), "->", time.strftime("%m-%d %H:%M", time.gmtime(max(r["bt"] for r in R)+18000)), "PKT")
T = collections.defaultdict(lambda: dict(buy=0.0, sell=0.0, nb=0, ns=0, off=0.0))
for r in R:
    if r["ok"] and r["evs"]:
        v = (r["nat"] + r["dws"]) / 1e9; m = r["evs"][0][0]
        if r["evs"][0][1]: T[m]["buy"] += -v; T[m]["nb"] += 1
        else: T[m]["sell"] += v; T[m]["ns"] += 1
oth = [r for r in R if r["ok"] and not r["evs"] and abs(r["nat"]+r["dws"]) > 1e6]
other = []
for r in oth:
    t = rpc("getTransaction", [r["sig"], {"encoding":"json","maxSupportedTransactionVersion":1}]); time.sleep(0.3)
    if not t: continue
    own = lambda L: {b["mint"]: int(b["uiTokenAmount"]["amount"]) for b in (L or []) if b.get("owner") == U}
    pre, post = own(t["meta"].get("preTokenBalances")), own(t["meta"].get("postTokenBalances"))
    ch = {m: post.get(m,0)-pre.get(m,0) for m in set(pre)|set(post) if m != WSOL and post.get(m,0) != pre.get(m,0)}
    v = (r["nat"]+r["dws"])/1e9
    if ch:
        m = next(iter(ch)); T[m]["off"] += v; other.append((time.strftime("%H:%M", time.gmtime(r["bt"]+18000)), round(v,2), m, ch[m]))
    else: other.append((time.strftime("%H:%M", time.gmtime(r["bt"]+18000)), round(v,2), "no-token", None))
print("off-curve txs (time PKT, SOL, token, token change):")
for o in other: print("  ", o)
closed = {m: x for m, x in T.items() if (x["ns"] or x["off"] > 0) and x["nb"]}
opened = {m: x for m, x in T.items() if x["nb"] and not (x["ns"] or x["off"] > 0)}
sold_only = {m: x for m, x in T.items() if not x["nb"]}
rz = sum(x["sell"] + x["off"] - x["buy"] for x in closed.values())
print(f"tokens bought AND sold in window: {len(closed)}  realized {rz:+.2f} SOL | win {sum(1 for x in closed.values() if x['sell']+x['off']-x['buy']>0)}/{len(closed)}")
print(f"tokens bought in window, NOT sold (bags): {len(opened)}  cost {sum(x['buy'] for x in opened.values()):.2f} SOL")
print(f"tokens only SOLD in window (bought before): {len(sold_only)}  proceeds {sum(x['sell']+x['off'] for x in sold_only.values()):+.2f} SOL")
print("native SOL balance now", round(rpc("getBalance", [U])["value"]/1e9, 2))
