#!/usr/bin/env python3
# H2H step 3 (read-only, local): (e) costs, (f) selection, (g) scale - haqq vs us in the SAME hours (our live run windows, FRA/AMS runs
# 9-14), plus the exit split on the contested dumps (we failed, haqq filled).
import sys, json, glob, pickle, zlib, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
import importlib.util
R = json.load(open(f"{H.OUT}/h2h_fires.json")); lots = json.load(open(f"{H.OUT}/lots.json")); led = json.load(open(f"{H.OUT}/ledger.json"))
_a = np.polyfit([r["s"] for r in led], [r["bt"] for r in led], 1); bt_of = lambda s: float(np.polyval(_a, s))
# our run windows (union of FRA and AMS runs 9-14)
win = []
for f in sorted(glob.glob("/home/moiz/sniper-data/runs/fra/runs/dip_r*.jsonl") + glob.glob("/home/moiz/sniper-data/runs/ams/runs/dip_ams_r*.jsonl")):
    run = int(f.split("_r")[-1].split(".")[0])
    if not 9 <= run <= 14: continue
    ts = []
    for l in open(f):
        try: t = json.loads(l).get("t")
        except Exception: continue
        if t: ts.append(t / 1e9)
    if ts: win.append((min(ts), max(ts)))
win.sort(); U = []
for a, b in win:
    if U and a <= U[-1][1]: U[-1] = (U[-1][0], max(U[-1][1], b))
    else: U.append((a, b))
hours = sum(b - a for a, b in U) / 3600
inwin = lambda t: any(a <= t <= b for a, b in U)
print(f"our live windows (union FRA+AMS runs 9-14): {len(U)} spans, {hours:.1f} h, {H.pkt(U[0][0])} -> {H.pkt(U[-1][1])} PKT")
# haqq lots in those hours
HL = [(li, l) for li, l in enumerate(lots) if inwin(bt_of(l["buy"]["s"]))]
shared_li = set()
for r in R:
    if r.get("haqq") == "fill" and r.get("h_li") is not None: shared_li.add(r["h_li"])
def pnl(l): return l["got"] - l["cost"] if l["closed"] else None
grp = collections.defaultdict(list)
for li, l in HL:
    if li in shared_li: g = "on dumps WE fired at"
    elif l["buy"]["dip"]: g = "dip, dumps we never fired at"
    else: g = "non-dip entries"
    grp[g].append(l)
tot = 0.0
print(f"\n(f) haqq lots in our live hours: {len(HL)} ({len(HL) / hours:.0f}/h)")
for g in ("on dumps WE fired at", "dip, dumps we never fired at", "non-dip entries"):
    L = grp[g]; p = [pnl(l) for l in L if pnl(l) is not None]; tot += sum(p)
    print(f"   {g:30s} lots {len(L):5d}: P&L {sum(p):+8.3f} SOL, mean {np.mean(p) * 1000:+.1f} mSOL, win {np.mean([x > 0 for x in p]):.0%}")
print(f"   total {tot:+.3f} SOL = {tot / hours:+.2f} SOL/h ({tot / hours * 24:+.1f}/day)")
# by profile within dumps we never fired at
L = grp["dip, dumps we never fired at"]
c = collections.defaultdict(list)
for l in L:
    if pnl(l) is not None: c[round(l["buy"]["sol"], 2)].append(pnl(l))
print("   dumps we never fired at, by its size:", {k: (len(v), round(sum(v), 2)) for k, v in sorted(c.items()) if len(v) >= 20})
ages = collections.defaultdict(list)
for l in L:
    if pnl(l) is not None:
        a = l["buy"]["age"]; ages["<2 s" if a < 2000 else ("2-5 s" if a < 5000 else ("5-30 s" if a < 30000 else ">=30 s"))].append(pnl(l))
print("   dumps we never fired at, by token age:", {k: (len(v), round(sum(v), 2)) for k, v in ages.items()})
# (g) scale: ours
fills = [r for r in R if r["status"] == "fill"]; fails = [r for r in R if r["status"] == "fail"]
ours = sum(r["our_pnl"] for r in fills if r.get("our_pnl") is not None) - sum(r.get("fail_fee", 0) for r in fails)
print(f"\n(g) scale in the same {hours:.1f} h: us {len(R)} fires / {len(fills)} fills ({len(fills) / hours:.1f} fills/h, one position at a time per server), net {ours:+.3f} SOL ({ours / hours:+.3f}/h); "
      f"haqq {len(HL)} lots ({len(HL) / hours:.0f}/h), net {tot:+.3f} SOL ({tot / hours:+.2f}/h)")
dips = [l for l in HL if l[1]["buy"]["dip"]]
print(f"   haqq dip lots {len(dips)} ({len(dips) / hours:.0f}/h); its per-lot mean on all lots {tot / max(1, len(HL)) * 1000:+.1f} mSOL vs ours per fill {ours / max(1, len(fills)) * 1000:+.1f} mSOL")
# (e) costs
hb_tx = [l["buy"]["txc"] for _, l in HL]
hfail = [r for r in led if r["kind"] == "fail" and inwin(r["bt"])]
hsell = [r for r in led if r["kind"] == "sell" and inwin(r["bt"])]
h_tx_total = sum(hb_tx) + sum((r["fee"] + r["tips"]) / 1e9 for r in hsell) + sum(r["fee"] / 1e9 for r in hfail)
C = json.load(open(f"{H.OUT}/h31_costs.json"))
our_tx = sum(r["our_buy_tx"] + r["our_sell_tx"] for r in fills) + sum(r.get("fail_fee", 0) for r in fails)
print(f"\n(e) tx costs in the same hours: haqq {h_tx_total:.3f} SOL for {len(HL)} lots ({h_tx_total / len(HL) * 1000:.2f} mSOL per lot incl. {len(hfail)} failed attempts) | "
      f"us {our_tx:.3f} SOL for {len(fills)} fills ({our_tx / len(fills) * 1000:.2f} mSOL per fill incl. {len(fails)} failed attempts)")
print(f"   per round trip: haqq buy {np.median(hb_tx) * 1000:.3f} + sell {np.median([(r['fee'] + r['tips']) / 1e9 for r in hsell]) * 1000:.3f} mSOL | us buy {C['BUY_TX'] * 1000:.3f} + sell {C['SELL_TX'] * 1000:.3f} mSOL")
print(f"   failed attempt: haqq median {np.median([r['fee'] for r in hfail]) / 1e9 * 1000:.3f} mSOL ({len(hfail)} = {len(hfail) / (len(hfail) + len(HL)):.0%} of its attempts) | us {np.median([r['fail_fee'] for r in fails]) * 1000:.3f} mSOL ({len(fails)} = {len(fails) / len(R):.0%})")
