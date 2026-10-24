#!/usr/bin/env python3
# A few HkQ7hMjy round trips from the last 24 h ledger (FIFO per mint) with Solscan links: a quick win, a typical 6-slot exit,
# a long-held loss. Net = the wallet's balance change on the buy tx + the sell tx (fees and tips included). Local file only.
import json, time, statistics
R = sorted([r for r in json.load(open("/home/moiz/sniper/ops/overnight/hkq7/ledger24.json")) if r["ok"] and r["evs"]], key=lambda r: r["slot"])
op = {}; T = []
for r in R:
    for e in r["evs"]:
        if e["buy"]: op.setdefault(e["mint"], []).append(r)
        elif op.get(e["mint"]):
            b = op[e["mint"]].pop(0)
            T.append(dict(m=e["mint"], hold=r["slot"] - b["slot"], net=(b["dsol"] + r["dsol"]) / 1e9, bt=b["bt"], bs=b["sig"], ss=r["sig"]))
T = [t for t in T if time.gmtime(t["bt"] + 18000).tm_hour in range(9, 19)]           # recent daytime, still easy to find on GMGN
pick = []
pick += sorted([t for t in T if 3 <= t["hold"] <= 5 and t["net"] > 0.03], key=lambda t: -t["bt"])[:1]
pick += sorted([t for t in T if t["hold"] == 6 and t["net"] > 0.01], key=lambda t: -t["bt"])[:1]
pick += sorted([t for t in T if 12 <= t["hold"] <= 30 and t["net"] > 0.02], key=lambda t: -t["bt"])[:1]
pick += sorted([t for t in T if t["hold"] >= 40 and t["net"] < -0.02], key=lambda t: -t["bt"])[:1]
for t in pick:
    print(f"{time.strftime('%m-%d %H:%M:%S', time.gmtime(t['bt'] + 18000))} PKT | held {t['hold']} slots (~{t['hold'] * 0.212:.1f} s) | net {t['net']:+.4f} SOL\n"
          f"  token https://gmgn.ai/sol/token/{t['m']}\n  buy  https://solscan.io/tx/{t['bs']}\n  sell https://solscan.io/tx/{t['ss']}")
