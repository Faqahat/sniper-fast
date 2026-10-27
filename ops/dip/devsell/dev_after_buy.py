#!/usr/bin/env python3
# Owner 10-25 ~06:05 PKT: "how much of our losing trades had the DEV selling after our buy?" Every live fill of every dip run
# (local copies of /root/prod/runs), the token's dev = its create tx's signer + creator + payer (recorder launches.jsonl), the
# engine's trade tape (our buy -> our sell, +2 slots), and the dump we bought after: was its seller the dev? (getTransaction).
import json, glob, re, os, collections, urllib.request, sys
from concurrent.futures import ThreadPoolExecutor
DEV = {}
for d in ("run_20261023_1426", "run_20261024_1425"):
    for l in open(f"/home/moiz/sniper-data/collect/{d}/launches.jsonl"):
        try: c = json.loads(l)
        except Exception: continue
        DEV[c["mint"]] = {x for x in (c.get("user"), c.get("creator"), c.get("payer")) if x}
URL = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def signer(sig):
    try:
        req = urllib.request.Request(URL, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}]}).encode(), headers={"content-type": "application/json"})
        t = json.load(urllib.request.urlopen(req, timeout=30)).get("result")
        return t["transaction"]["message"]["accountKeys"][0] if t else None
    except Exception: return None
rows = []
for f in sorted(glob.glob("/home/moiz/sniper-data/runs/*/runs/dip_*r*.jsonl")):
    run = os.path.basename(f)[:-6]
    pnl = collections.defaultdict(list)
    for l in open(f[:-6] + ".log", errors="ignore"):
        m = re.search(r"REALIZED mint=(\S+) pnl=([-+0-9.]+)", l)
        if m: pnl[m.group(1)].append(float(m.group(2)))
    cur = {}; tapes = collections.defaultdict(list)
    for l in open(f):
        if '"ev":"dump"' in l: continue
        try: o = json.loads(l)
        except Exception: continue
        e = o.get("ev")
        if e == "fire": cur[o["mint"]] = dict(fire=o, tape=[])
        elif e == "tape" and o.get("mint") in cur: cur[o["mint"]]["tape"].append(o)
        elif e == "close" and o.get("mint") in cur:
            c = cur.pop(o["mint"])
            if o.get("result") != "sold" or not o.get("land") or not o.get("sell_land"): continue
            p = pnl[o["mint"]].pop(0) if pnl.get(o["mint"]) else None
            b = (o["land"][0], o["land"][1]); s = (o["sell_land"][0], o["sell_land"][1])
            dev = DEV.get(o["mint"])
            ds = [t for t in c["tape"] if not t["buy"] and dev and t["user"] in dev and b < (t["slot"], t["idx"]) < s]
            rows.append(dict(run=run, mint=o["mint"], pnl=p, dev_known=dev is not None, dev_sold=bool(ds), dev_sol=sum(t["sol"] for t in ds) / 1e9,
                             dump_sig=o.get("dump_sig"), dev_set=dev, exit=o.get("exit_why"), held=o.get("held_s")))
# who sold the dump we bought after?
with ThreadPoolExecutor(8) as ex: sellers = list(ex.map(lambda r: signer(r["dump_sig"]), rows))
for r, sg in zip(rows, sellers): r["dump_by_dev"] = bool(r["dev_set"] and sg in r["dev_set"]); r["dump_seller_known"] = sg is not None
fills = [r for r in rows if r["pnl"] is not None]; known = [r for r in fills if r["dev_known"]]
print(f"fills with chain P&L: {len(fills)} (runs {len(set(r['run'] for r in fills))}); dev known for {len(known)} (token launched inside the recorder's window)")
def line(name, g):
    if not g: print(f"  {name}: none"); return
    n = len(g); ds = [r for r in g if r["dev_sold"]]; dd = [r for r in g if r["dump_by_dev"]]
    print(f"  {name}: {n} fills, {sum(r['pnl'] for r in g):+.4f} SOL | dev SOLD during our hold: {len(ds)} ({100*len(ds)/n:.0f}%, {sum(r['pnl'] for r in ds):+.4f} SOL, dev sold {sum(r['dev_sol'] for r in ds):.2f} SOL) | the dump we bought WAS the dev's sell: {len(dd)} ({100*len(dd)/n:.0f}%, {sum(r['pnl'] for r in dd):+.4f} SOL)")
lose = [r for r in known if r["pnl"] <= 0]; win = [r for r in known if r["pnl"] > 0]
line("LOSERS", lose); line("WINNERS", win)
big = [r for r in lose if r["pnl"] <= -0.03]; line("big losers (<= -0.03)", big)
print("dev sold during our hold (all):")
for r in sorted([r for r in known if r["dev_sold"]], key=lambda r: r["pnl"]):
    print(f"   {r['run']:<12} {r['mint'][:8]} {r['pnl']:+.4f} SOL  dev sold {r['dev_sol']:.2f} SOL during our {r['held'] or 0:.1f} s hold ({r['exit']}){'  [dump was dev too]' if r['dump_by_dev'] else ''}")
