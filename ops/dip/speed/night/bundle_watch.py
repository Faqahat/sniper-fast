#!/usr/bin/env python3
# READ-ONLY night watcher: new jito-bundle ids in the LIVE engines' logs (ssh tail, read-only) -> Jito's public
# getInflightBundleStatuses (from THIS host's IP, no auth: nothing the live engine uses) -> bundle_watch.jsonl. Every 30 s.
import json, subprocess, re, time, urllib.request
HOSTS = {"fra": "84.32.100.36", "ams": "84.32.104.202"}
EP = "https://frankfurt.mainnet.block-engine.jito.wtf/api/v1/getInflightBundleStatuses"
seen = {}; out = open("bundle_watch.jsonl", "a")
def q(ids):
    req = urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getInflightBundleStatuses", "params": [ids]}).encode(), headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=20))
while True:
    for reg, h in HOSTS.items():
        try:
            cmd = 'p=$(pgrep -af "[s]nipe_engine_dip" | grep -o "dip-log [^ ]*" | head -1 | cut -d" " -f2); [ -n "$p" ] && sudo -n tail -n 400 "${p%.jsonl}.log"'
            txt = subprocess.run(["ssh", "-p", "1996", "-o", "ConnectTimeout=8", f"it@{h}", cmd], capture_output=True, text=True, timeout=30).stdout
        except Exception: continue
        for tag, bid in re.findall(r"FAST-ACK tag=(\d+) path=jito-bundle ack_ms=\S+ status=Some\(200\) reply=([0-9a-f]{64})", txt):
            if bid not in seen: seen[bid] = (reg, tag, time.time())
    pend = [b for b, (r, t, ts) in seen.items() if time.time() - ts < 280 and ts > 0]
    if pend:
        try:
            res = q(pend[:5])
            for v in (res.get("result") or {}).get("value") or []:
                if not v: continue
                b = v.get("bundle_id"); st = v.get("status")
                rec = {"t": time.time(), "region": seen.get(b, ("?",))[0], "tag": seen.get(b, ("?", "?"))[1], "bundle": b, "status": st, "landed_slot": v.get("landed_slot")}
                out.write(json.dumps(rec) + "\n"); out.flush()
                if st in ("Landed", "Failed", "Invalid"): seen[b] = (seen[b][0], seen[b][1], 0)   # final: stop asking
        except Exception as e:
            out.write(json.dumps({"t": time.time(), "err": str(e)[:200]}) + "\n"); out.flush()
    time.sleep(30)
