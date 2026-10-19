# Mayhem curves: compare virtual vs real SOL reserves and the payout a seller could actually get.
import sys, json
sys.path.insert(0, "/root/strat")
from srpc import rpc
from pev import events
n = 0
for l in open("/root/strat/pipe.jsonl"):
    x = json.loads(l)
    if not x.get("mayhem") or x.get("stage") != 4: continue
    rows = [r for r in x["rows"] if r[1]]
    hi = [r for r in rows if r[1][-1][4] > 80e9]
    if not hi: continue
    r = hi[0]
    sigs = None
    # refetch the tx at that slot via the mint's signatures is costly; use the stored sig prefix? not stored -> refetch by slot list
    s = rpc("getSignaturesForAddress", [x["mint"], {"limit": 1000}])
    if not isinstance(s, list): continue
    cand = [y for y in s if y["slot"] - x["slot"] == r[0] and y.get("err") is None]
    if not cand: continue
    t = rpc("getTransaction", [cand[0]["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    tr, _ = events((t.get("meta") or {}).get("logMessages"))
    for e in tr:
        if e["mint"] == x["mint"]:
            print(x["mint"][:8], "d", r[0], "vsol %.1f rsol %.2f vtok %.3e k/kstd %.3f user %s buy %d sol %.3f" % (e["vsol"] / 1e9, e["rsol"] / 1e9, e["vtok"], e["vsol"] * e["vtok"] / 3.219e25, e["user"][:8], e["buy"], e["sol"] / 1e9))
    n += 1
    if n >= 6: break
