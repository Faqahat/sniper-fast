# READ-ONLY: who are the outside buyers that landed AHEAD of our live buys in the create slot?
import sys, re, json, time, urllib.request, collections as C
sys.path.insert(0, "/root/indep")
from common import get_block, events, is_vote, tx_summary, load_tipmap, rpc
TM = load_tipmap()
ME = "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
L = open(sys.argv[1], errors="replace").read()
fires = re.findall(r"FIRE slot=(\d+) mint=(\w+)", L)


def jito(sig):
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request("https://bundles.jito.wtf/api/v1/bundles/transaction/" + sig,
                                                                   headers={"user-agent": "research"}), timeout=15))
        time.sleep(0.6)
        return r[0].get("bundle_id", "")[:10] if isinstance(r, list) and r else "-"
    except Exception:
        time.sleep(0.6)
        return "-"


seen_w = C.Counter()
rows = []
for slot, mint in fires:
    b = get_block(int(slot))
    txs = [t for t in b.get("transactions", [])] if isinstance(b, dict) else []
    nv = [t for t in txs if not is_vote(t)]
    ci = None
    for i, t in enumerate(nv):
        tr, cr = events((t.get("meta") or {}).get("logMessages"))
        if any(c["mint"] == mint for c in cr):
            ci, creator = i, tx_summary(t, TM)[0]["payer"]
            break
    if ci is None:
        continue
    glued, run = 0, True
    print(f"\n=== {mint[:10]} slot {slot} create at pos {ci}/{len(nv)} creator {creator[:8]}")
    for j, t in enumerate(nv[ci + 1:], start=1):
        meta = t.get("meta") or {}
        tr, _ = events(meta.get("logMessages"))
        ev = [e for e in tr if e["mint"] == mint and e["buy"]]
        ok = meta.get("err") is None
        if run:
            if ev and ok:
                glued += 1
                continue
            run = False
        if not ev or not ok:
            continue
        s = tx_summary(t, TM)[0]
        users = {e["user"] for e in ev}
        if ME in users:
            print(f"   pos +{j:<4} US")
            break
        sol = sum(e["sol"] for e in ev) / 1e9
        prio = ((s["fee"] or 0) - 5000 * len(s["signers"])) / 1e9
        jb = jito(s["sig"])
        for u in users:
            seen_w[u] += 1
        print(f"   pos +{j:<4} {s['payer'][:8]} buy {sol:6.3f} SOL prio {prio:.4f} tips {[(x[0], x[1] / 1e9) for x in s['tips']]} jito_bundle {jb} signers {len(s['signers'])}")
        rows.append(dict(mint=mint, payer=s["payer"], pos=j, sol=sol))
print("\nwallets ahead of us, and on how many of our launches they appear:")
for w, n in seen_w.most_common():
    print(f"   {w}  {n}x")
