#!/bin/bash
# READ-ONLY: prints one JSON line with FRA collector counters for every run whose status.json was written in the
# last 10 min (the current run, plus the previous one while it is in its tail). Used by guard.py during the overlap.
ssh -p 1996 -o ConnectTimeout=15 -o ServerAliveInterval=10 -o BatchMode=yes it@84.32.100.36 "sudo python3 -I -c '
import json, os, glob, time
out = {\"t\": time.time(), \"runs\": {}}
for d in sorted(glob.glob(\"/root/sniper-collect/run_*\")):
    p = d + \"/status.json\"
    try: s = json.load(open(p))
    except Exception: continue
    if time.time() - os.path.getmtime(p) > 600: continue
    st = s.get(\"stats\") or {}
    keep = {k: v for k, v in st.items() if k.startswith((\"blk_\", \"blocks_\", \"rpc_\")) or k in (\"txs\", \"launches\")}
    out[\"runs\"][os.path.basename(d)] = dict(now=s.get(\"now\"), phase=s.get(\"phase\"), lag_slots=s.get(\"lag_slots\"), last_slot=s.get(\"last_slot\"), stats=keep)
out[\"collectors\"] = len([1 for p in os.listdir(\"/proc\") if p.isdigit() and open(\"/proc/%s/cmdline\" % p, \"rb\").read().replace(b\"\\0\", b\" \").strip() == b\"python3 -I collect.py\"]) if True else None
print(json.dumps(out))
'"
