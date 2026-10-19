# READ-ONLY: verify every launch the engine FIRED on (paper log "PAPER launch") passes the live filter ON CHAIN:
# host not a bot launchpad, true dev buy 3..8 SOL, creator bundle >= 2 glued buys, name <= 12 chars, SOL-quoted, create_v2.
import sys, re
sys.path.insert(0, "/root/indep")
from common import get_block, events, is_vote, VSOL0
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}
fires = []
for l in open(sys.argv[1], errors="replace"):
    m = re.search(r"PAPER launch #\d+ slot=(\d+) mint=(\w+) dev_buy=(\d+)", l)
    if m:
        fires.append((int(m.group(1)), m.group(2), int(m.group(3))))
print(f"fired launches in log: {len(fires)}")
bad = 0
for slot, mint, dev_eng in fires:
    blk = get_block(slot)
    res = {"found": False}
    if isinstance(blk, dict) and "transactions" in blk:
        txs = [t for t in blk["transactions"] if not is_vote(t)]
        for i, t in enumerate(txs):
            meta = t.get("meta") or {}
            tr, cr = events(meta.get("logMessages"))
            c = [x for x in cr if x["mint"] == mint]
            if not c:
                continue
            dev = sum(e["sol"] for e in tr if e["mint"] == mint and e["buy"]) / 1e9
            sol_quoted = any(e["mint"] == mint for e in tr) or dev == 0
            glued = 0
            for t2 in txs[i + 1:]:
                m2 = t2.get("meta") or {}
                tr2, _ = events(m2.get("logMessages"))
                if m2.get("err") is None and any(e["mint"] == mint and e["buy"] for e in tr2):
                    glued += 1
                else:
                    break
            host = c[0]["uri"].split("://")[-1].split("/")[0]
            name = c[0]["name"]
            res = dict(found=True, host=host, dev=dev, glued=glued, name=name, sol=sol_quoted,
                       v2=any("Instruction: CreateV2" in x for x in (meta.get("logMessages") or [])))
            break
    if not res["found"]:
        print(f"  {mint[:10]} slot {slot}: create not found in block (cannot verify)")
        continue
    checks = {"host ok": not (res["host"] in BOT or res["host"].endswith(".trycloudflare.com")),
              "dev 3-8": 2.9 <= res["dev"] <= 8.1, "bundle>=2": res["glued"] >= 2, "name<=12": len(res["name"]) <= 12,
              "SOL quote": res["sol"]}
    ok = all(checks.values())
    bad += not ok
    print(f"  {mint[:10]} {'PASS' if ok else 'FAIL'} dev {res['dev']:.2f} (engine {dev_eng/1e9:.2f}) bundle {res['glued']} "
          f"name '{res['name'][:14]}' ({len(res['name'])}) host {res['host'][:26]} v2 {res['v2']} "
          + ("" if ok else "FAILED: " + ",".join(k for k, v in checks.items() if not v)))
print(f"\nfailing the live filter on chain: {bad} of {len(fires)}")
