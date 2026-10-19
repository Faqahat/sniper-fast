# READ-ONLY: for every FIRE in a live log, confirm on chain the launch passes the BLACKLIST filter:
# metadata host not a bot launchpad, dev buy 0.5-8 SOL, create_v2 flags (no mayhem / creator fee).
import sys, re
sys.path.insert(0, "/root/indep")
from common import get_block, events, b58dec, PUMP
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}
fires = []
for l in open(sys.argv[1]):
    m = re.search(r"FIRE slot=(\d+) mint=(\w+) dev_buy=(\d+)", l)
    if m:
        fires.append((int(m.group(1)), m.group(2), int(m.group(3))))
print(f"FIRES in log: {len(fires)}")
bad = 0
for slot, mint, devlog in fires:
    blk = get_block(slot)
    host, devsol, flags = "?", None, "?"
    if isinstance(blk, dict) and "transactions" in blk:
        for t in blk["transactions"]:
            meta = t.get("meta") or {}
            tr, cr = events(meta.get("logMessages"))
            c = [x for x in cr if x["mint"] == mint]
            if not c:
                continue
            uri = c[0]["uri"]
            host = uri.split("://")[-1].split("/")[0]
            dv = [e for e in tr if e["mint"] == mint and e["buy"]]
            devsol = sum(e["sol"] for e in dv) / 1e9
            logs = meta.get("logMessages") or []
            flags = "create_v2" if any("Instruction: CreateV2" in x for x in logs) else "create"
            break
    bl = host in BOT or host.endswith(".trycloudflare.com")
    ok_dev = 0.5 <= devlog / 1e9 <= 8
    verdict = "PASS" if (not bl and ok_dev and host != "?") else "FAIL"
    bad += verdict == "FAIL"
    print(f"  {mint[:10]} host={host:28} dev(engine)={devlog/1e9:5.2f} dev(chain create-tx buys)={devsol if devsol is None else round(devsol, 2)} {flags:9} -> {verdict}")
print(f"\nfailing the blacklist filter: {bad} of {len(fires)}")
