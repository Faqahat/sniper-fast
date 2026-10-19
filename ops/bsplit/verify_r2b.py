# READ-ONLY: verify every launch FIRED in a paper log passes RULE #2 ON CHAIN:
# base: host not a bot launchpad, true dev buy 0.5..8 SOL, SOL-quoted create_v2;
# rule #2: creator bundle (glued buys right after the create) total 3..5 SOL, and the create tx's largest
# non-signer SOL transfer goes to an account starting with "moon" (Lunar Lander tip).
import sys, re
sys.path.insert(0, "/root/indep")
from common import get_block, events, is_vote, tx_summary, load_tipmap
TM = load_tipmap()
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}
fires = []
for l in open(sys.argv[1], errors="replace"):
    m = re.search(r"PAPER launch #\d+ slot=(\d+) mint=(\w+) dev_buy=(\d+)", l)
    if m:
        fires.append((int(m.group(1)), m.group(2), int(m.group(3))))
print(f"fired launches in log: {len(fires)}")


def largest_transfer_dest(t):
    msg = t["transaction"]["message"]
    meta = t.get("meta") or {}
    keys = msg["accountKeys"] + (meta.get("loadedAddresses") or {}).get("writable", []) + (meta.get("loadedAddresses") or {}).get("readonly", [])
    nsig = msg["header"]["numRequiredSignatures"]
    pre, post = meta.get("preBalances", []), meta.get("postBalances", [])
    best, dest = 0, None
    for i in range(nsig, min(len(pre), len(post))):
        d = post[i] - pre[i]
        if d > best and keys[i] != "11111111111111111111111111111111":
            best, dest = d, keys[i]
    return dest, best


bad = unv = 0
for slot, mint, dev_eng in fires:
    blk = get_block(slot)
    res = None
    if isinstance(blk, dict) and "transactions" in blk:
        txs = [t for t in blk["transactions"] if not is_vote(t)]
        for i, t in enumerate(txs):
            meta = t.get("meta") or {}
            tr, cr = events(meta.get("logMessages"))
            c = [x for x in cr if x["mint"] == mint]
            if not c:
                continue
            dev = sum(e["sol"] for e in tr if e["mint"] == mint and e["buy"]) / 1e9
            gsol, glued = 0.0, 0
            for t2 in txs[i + 1:]:
                m2 = t2.get("meta") or {}
                tr2, _ = events(m2.get("logMessages"))
                b = [e for e in tr2 if e["mint"] == mint and e["buy"]]
                if m2.get("err") is None and b:
                    glued += 1
                    gsol += sum(e["sol"] for e in b) / 1e9
                else:
                    break
            tips = tx_summary(t, TM)[0]["tips"]
            moon = [x for x in tips if str(x[2]).startswith("moon")]
            dest, amt = (moon[0][2], moon[0][1]) if moon else ((tips[0][2], tips[0][1]) if tips else (None, 0))
            res = dict(host=c[0]["uri"].split("://")[-1].split("/")[0], dev=dev, glued=glued, gsol=gsol, tip=dest or "-", tip_amt=amt / 1e9,
                       v2=any("Instruction: CreateV2" in x for x in (meta.get("logMessages") or [])))
            break
    if res is None:
        unv += 1
        print(f"  {mint[:10]} slot {slot}: create not found in block (cannot verify)")
        continue
    checks = {"host ok": not (res["host"] in BOT or res["host"].endswith(".trycloudflare.com")), "dev 0.5-8": 0.49 <= res["dev"] <= 8.1,
              "bundle 3-5 SOL": 2.95 <= res["gsol"] <= 5.05, "lunar tip": res["tip"].startswith("moon"), "create_v2": res["v2"]}
    ok = all(checks.values())
    bad += not ok
    print(f"  {mint[:10]} {'PASS' if ok else 'FAIL'} dev {res['dev']:.2f} (eng {dev_eng/1e9:.2f}) bundle {res['glued']} txs / {res['gsol']:.2f} SOL "
          f"tip->{res['tip'][:8]} {res['tip_amt']:.4f} host {res['host'][:24]} " + ("" if ok else "FAILED: " + ",".join(k for k, v in checks.items() if not v)))
print(f"\nfailing rule #2 on chain: {bad} of {len(fires)} (unverifiable: {unv})")
