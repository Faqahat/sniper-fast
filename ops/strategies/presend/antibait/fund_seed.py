#!/usr/bin/env python3
"""dip38 FUND SEED: the antibait study's resolved funding chains (/home/it/sniper-data/antibait/resolve_*.json, written by
/home/it/sniper-studies/sniper-antibait/resolve.py) -> the engine's --presend-live-fund-state file:
    {"v": 1, "saved": unix s, "w": {wallet: {"st": "ok" | "deep", "n": signatures read, "t": unix s, "chain": [[address, kind, hop], ...]}}}
  done true  -> "ok" with its chain (walk order; hubs kept), done false -> "deep" (> 2,000 txs: not traceable on public RPC), an "err"
  entry is left out (the engine asks it again). A wallet in several inputs: the one with the longer chain, then the newer file.
  Read-only on the inputs; writes OUT (default /home/it/sniper-data/antibait/fund_seed.json) via OUT.tmp + rename.
usage: fund_seed.py [OUT] [--in resolve_a.json,resolve_b.json]"""
import sys, os, json, glob, time

D = "/home/it/sniper-data/antibait"
args = [a for a in sys.argv[1:]]
inputs = None
if "--in" in args:
    i = args.index("--in"); inputs = args[i + 1].split(","); del args[i:i + 2]
out = args[0] if args else os.path.join(D, "fund_seed.json")
inputs = inputs or sorted(glob.glob(os.path.join(D, "resolve*.json")))
KINDS = {"hub", "oneshot", "normal"}
w, stats = {}, {"files": 0, "ok": 0, "deep": 0, "err": 0, "bad": 0}
for f in inputs:
    t = int(os.path.getmtime(f))
    stats["files"] += 1
    for k, e in json.load(open(f)).items():
        if not isinstance(e, dict) or "err" in e: stats["err"] += 1; continue
        if len(k) < 32 or len(k) > 44: stats["bad"] += 1; continue
        if e.get("done"):
            ch = [[a, kd, int(h)] for a, kd, h in (e.get("chain") or []) if kd in KINDS]
            new = {"st": "ok", "n": int(e.get("n") or 0), "t": t, "chain": ch}
        else:
            new = {"st": "deep", "n": int(e.get("n") or 0), "t": t, "chain": []}
        old = w.get(k)
        if old is None or (len(new["chain"]), new["t"]) >= (len(old["chain"]), old["t"]): w[k] = new
for e in w.values(): stats[e["st"]] += 1
tmp = out + ".tmp"
json.dump({"v": 1, "saved": int(time.time()), "w": w}, open(tmp, "w"))
os.replace(tmp, out)
print(f"{out}: {len(w)} wallets ({sum(1 for e in w.values() if e['st'] == 'ok')} ok, {sum(1 for e in w.values() if e['st'] == 'deep')} deep) from {stats['files']} files; "
      f"{stats['err']} error entries left out, {stats['bad']} bad keys")
