#!/usr/bin/env python3
# READ-ONLY, offline. MEASURED exit settings per copy-trade config (= wallet x followed dev) from the wallets' own sells on all
# SOL-quoted pump round trips (10-17 .. 10-23): lightning sell, take-profit steps, down-sell size, stop level, timeouts.
import sys, os, json, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
CI = json.load(open(os.path.join(EXITS, "cache", "create_info.json")))
LA = load_launches()
def mode(c): return c.most_common(1)[0][0] if c else None
rows = []
for w in WALLETS:
    R = json.load(open(f"{EXITS}/roundtrips_{w}.json"))["tokens"]
    by = collections.defaultdict(list)
    for r in R:
        dev = (CI[r["mint"]]["user"] if r["mint"] in CI else (LA[r["mint"]]["user"] if r["mint"] in LA else r["creator"]))
        by[dev].append(r)
    for dev, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        if len(rs) < 5: continue
        light = collections.Counter(); ldel = collections.Counter(); tp = collections.defaultdict(list); down = collections.Counter(); clr_lo = []; t_fin = []
        for r in rs:
            ss = [l for l in r["legs"] if l["side"] == "sell"]; hi = 0; k = 0
            for i, l in enumerate(ss):
                if i == 0 and l["dslot"] <= 8 and len(ss) > 1:
                    light[round(l["frac"] * 20) * 5] += 1; ldel[l["dslot"]] += 1; hi = max(hi, l["mult_pre"]); continue
                if i == len(ss) - 1:
                    if l["mult_pre"] < 1: clr_lo.append(l["mult_pre"])
                    t_fin.append(l["dslot"]); continue
                if l["mult_pre"] >= hi: k += 1; tp[k].append((l["mult_pre"], round(l["frac"] * 100)))
                else: down[round(l["frac"] * 100)] += 1
                hi = max(hi, l["mult_pre"])
        tps = []
        for k in sorted(tp)[:3]:
            v = tp[k]; tps.append(f"#{k}: x{statistics.median(x[0] for x in v):.2f} sell {mode(collections.Counter(x[1] for x in v))}% (n={len(v)})")
        rows.append(dict(w=w, dev=dev, n=len(rs), pnl=round(sum(r["pnl"] for r in rs), 2), sizes=[s for s, n in collections.Counter(round(r["buy_sol"] * 1.0125, 1) for r in rs).most_common(2)],
                         light=f"{mode(light)}% @ {mode(ldel)} slots" if light else "-", light_mix=dict(light.most_common(3)),
                         tp="; ".join(tps) or "-", down=f"{mode(down)}%" if down else "-",
                         stop=f"x{statistics.median(clr_lo):.2f} (n={len(clr_lo)})" if clr_lo else "-",
                         final_slots_median=statistics.median(t_fin) if t_fin else None, two_piece=sum(1 for r in rs if r["n_sells"] == 2)))
json.dump(rows, open(os.path.join(EXITS, "config_table.json"), "w"), indent=1)
print("| wallet | dev (followed) | tokens | PnL SOL | buy SOL | lightning sell (mode) | take-profit steps (price x entry, sell % of rest) | down-sell | clear below entry (median) | final sell (median slots) |")
print("|---|---|---|---|---|---|---|---|---|---|")
for r in rows:
    print(f"| {r['w']} | {r['dev'][:6]} | {r['n']} | {r['pnl']:+.2f} | {'/'.join(str(s) for s in r['sizes'])} | {r['light']} | {r['tp']} | {r['down']} | {r['stop']} | {r['final_slots_median']} |")
