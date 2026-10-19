import sys, json
sys.path.insert(0, "/root/indep")
from common import rpc, get_block, events, is_vote, tx_summary, load_tipmap
nodes = {x["pubkey"]: x for x in json.load(open("/root/stakepaths/clusternodes.json"))["result"]}
S = 458481724
M = "GHEc1Z7L7xuFUsjDk1a1o7bLFsAaVTckiiF5ebXCpump"
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
l = rpc("getSlotLeaders", [S, 1])[0]
print("leader", l[:8], "client", nodes.get(l, {}).get("clientId"))
tm = load_tipmap()
blk = get_block(S)
txs = [t for t in blk["transactions"] if not is_vote(t)]
ci = None
for i, t in enumerate(txs):
    tr, cr = events((t.get("meta") or {}).get("logMessages"))
    if any(c["mint"] == M for c in cr):
        ci = i
n = 0
for j, t in enumerate(txs[ci:], start=ci):
    meta = t.get("meta") or {}
    tr, cr = events(meta.get("logMessages"))
    ev = [e for e in tr if e["mint"] == M]
    if not ev and not cr:
        continue
    s = tx_summary(t, tm)[0]
    who = "4yFAz" if any(e["user"] == W for e in ev) else s["payer"][:8]
    acts = [("BUY" if e["buy"] else "SELL", round(e["sol"] / 1e9, 2)) for e in ev]
    prio = ((s["fee"] or 0) - 5000 * len(s["signers"])) / 1e9
    print(f"  pos {j - ci:+4}  {who:9} {'CREATE' if cr else '':6} {acts} prio {prio:.4f} SOL tips {s['tips']} err {s['err']}")
    n += 1
    if n >= 12:
        break
