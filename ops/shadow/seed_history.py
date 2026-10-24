#!/usr/bin/env python3
# Build the shadow scorer's starting state (host, offline): every launch's create time / creator / name (own-stream
# features) and every RESOLVED launch's 10-minute outcome + bundle wallets (history features), from the joined table
# and the phase-B rows of all collection runs so far. usage: seed_history.py <table_all.jsonl.gz> <phaseB dir,...> <out.json> [dump raw.jsonl.gz]
import sys, json, gzip, glob, re
T, BD, OUT = sys.argv[1:4]
norm = lambda x: re.sub(r"[^a-z0-9]", "", (x or "").lower())
bw = {}
for d in BD.split(","):
    for f in glob.glob(d + "/*.jsonl.gz"):
        for l in gzip.open(f, "rt"):
            r = json.loads(l); bw[r["mint"]] = r.get("bundle_wallets") or []
creates, resolved = [], []
for l in gzip.open(T, "rt"):
    r = json.loads(l)
    if not r.get("bt"): continue
    creates.append([r["bt"], r.get("creator"), norm(r.get("name")), norm(r.get("symbol"))])
    pk = r.get("peak_10m") if r.get("peak_10m") is not None else (1.0 if r.get("no_trades") else 0.0)
    resolved.append([r["bt"] + 600, r.get("creator"), (r.get("name") or "").strip().lower(), int((pk or 0) >= 2.0), bw.get(r["mint"], []), r["mint"]])   # training's name key
LAST = max(c[0] for c in creates)
resolved = [x for x in resolved if x[0] - 600 <= LAST - 900]      # only launches whose 10-min window is complete in the data
creates.sort(); resolved.sort()
dump = []                                                   # anti-dump behaviour history (f_dump.py raw facts), same resolve rule
if len(sys.argv) > 4:
    for l in gzip.open(sys.argv[4], "rt"):
        x = json.loads(l)
        if x["bt"] <= LAST - 900: dump.append([x["bt"] + 600, x["creator"], x["fast"], x["first"], x["out"], x["wsell"], x["mint"]])
    dump.sort(key=lambda d: d[0])
json.dump(dict(creates=creates, resolved=resolved, dump=dump, last_bt=max(c[0] for c in creates)), open(OUT, "w"))
print("creates", len(creates), "resolved", len(resolved), "wins", sum(x[3] for x in resolved))
