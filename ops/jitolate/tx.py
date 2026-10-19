# READ-ONLY: print compact summaries of given tx sigs (getTransaction, cached)
import sys, json
sys.path.insert(0, "/root/indep")
from common import rpc, tx_summary, load_tipmap, events
tm = load_tipmap()
for sig in sys.argv[1:]:
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not isinstance(t, dict) or "transaction" not in t:
        print(sig[:12], "ERR", t); continue
    s, keys = tx_summary(t, tm)
    tr, cr = events(t["meta"].get("logMessages"))
    # raw sys transfers (any dst)
    msg = t["transaction"]["message"]
    xfers = []

    print(json.dumps({"sig": sig[:16], "slot": t["slot"], "payer": s["payer"], "signers": s["signers"], "fee": s["fee"], "cu_price": s["cu_price"], "cu_limit": s["cu_limit"],
                      "cuu": s["cuu"], "tips": s["tips"], "keytip": s["keytip"], "progs": s["progs"], "nkeys": len(keys), "trades": [(e["user"][:6], e["sol"], e["buy"], e["mint"][:6]) for e in tr],
                      "err": t["meta"].get("err"), "pre": t["meta"]["preBalances"][:3], "post": t["meta"]["postBalances"][:3], "keys": keys[:12]}))
