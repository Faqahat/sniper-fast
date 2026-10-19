# READ-ONLY: who is the relay that wraps user txs in a Jito bundle with its own 1,013,000-lamport tip tx?
# For each wrapper payer: recent sigs -> bundle -> the partner (user) tx -> which provider tips it pays.
import sys, json, collections as C
sys.path.insert(0, "/root/jitolate"); sys.path.insert(0, "/root/indep")
from buys import bundle_of_tx, cached
from common import rpc, tx_summary, load_tipmap
tm = load_tipmap()
for w in sys.argv[1:]:
    sigs = rpc("getSignaturesForAddress", [w, {"limit": 12}])
    cnt = C.Counter(); n = 0
    for s in sigs[:12]:
        b = bundle_of_tx(s["signature"])
        if not b: continue
        for us in b.get("txSignatures", []):
            if us == s["signature"]: continue
            t = cached("tx_" + us[:40], lambda: rpc("getTransaction", [us, {"encoding": "json", "maxSupportedTransactionVersion": 1}]))
            if isinstance(t, dict) and "transaction" in t:
                ss = tx_summary(t, tm)[0]; n += 1
                cnt[tuple(sorted(x[0] for x in ss["tips"]))] += 1
    print(w[:8], "partner txs", n, dict(cnt))
