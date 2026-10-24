#!/usr/bin/env python3
# Owner 10-24 05:15 PKT: "from all of our TP hit triggers, what potential did we have — maximum and median — if we hadn't sold at
# our %". For every LIVE fill (runs 1-3; TP exits first, then all fills): our buy and sell located on the collector's full tape,
# then the value of OUR token amount after every later trade (constant-product sell-out on that trade's post-state, minus the pump
# fee) vs our cost (curve SOL in + pump fee): the peak within 2 / 10 / 30 / 60 / 120 s after our buy (the most we could have made,
# hindsight) and the value if simply held to 1.3 / 5 / 10 / 30 / 60 s (the realistic alternative). Tips / tx fees left out (fixed).
# usage: python3 -I tp_potential.py run1.jsonl run2.jsonl ...      (RP_PHASEA_R3 = the extracted collector window)
import os, sys, json, statistics, collections
os.environ["RP_PHASEA_R3"] = os.environ.get("RP_PHASEA_R3", "phaseA_r3tp"); os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd")
os.environ.update(SELL_LAT="75", DIP_LATS="35,50,75", DIP_B="0.35", DIP_COHORT_FILE="/home/moiz/sniper/ops/overnight/sel/cohort_train.json")
D = "/home/moiz/sniper/ops/overnight/sel"; sys.path.insert(0, D)
import selexit2 as X
US = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
HZ = (2, 10, 30, 60, 120); AT = (1.3, 5, 10, 30, 60)
fills = []
for path in sys.argv[1:]:
    ev = [json.loads(l) for l in open(path)]
    for f in [e for e in ev if e["ev"] == "fire"]:
        bl = next((e for e in ev if e["ev"] == "buy_land" and e.get("sig") == f["buy_sig"]), None)
        cl = next((e for e in ev if e["ev"] == "close" and e.get("buy_sig") == f["buy_sig"]), None)
        if bl and cl: fills.append(dict(run=os.path.basename(path)[:6], m=f["mint"], buy=bl, close=cl))
rows = []
for x in fills:
    m = x["m"]; L = X.L.get(m)
    tr = X.rp.read_bucket(L["run"], X.rp.bucket(m), {m}).get(m) if L else None
    if not tr: print(f"{x['run']} {m[:6]}: no tape"); continue
    kb = next((k for k, t in enumerate(tr) if t.get("user") == US and t["buy"] and t["s"] == x["buy"]["slot"]), None)
    if kb is None: print(f"{x['run']} {m[:6]}: our buy not on the tape"); continue
    b = tr[kb]; tokens = b["tok"]; fr = ((b.get("fbps") or 95) + (b.get("cbps") or 30)) / 1e4
    cost = b["sol"] / 1e9 * (1 + fr); a0 = X.arr(b)
    ks = next((k for k in range(kb + 1, len(tr)) if tr[k].get("user") == US and not tr[k]["buy"]), None)
    real = tr[ks]["sol"] / 1e9 * (1 - fr) / cost - 1 if ks is not None else None
    def val(t):                      # our tokens sold right after trade t, on its post-trade curve
        k = t["vsol"] * t["vtok"]; out = t["vsol"] - k / (t["vtok"] + tokens)
        return out / 1e9 * (1 - fr) / cost - 1
    later = [t for t in tr[kb + 1:] if t.get("user") != US]
    peak = {}; held = {}
    for h in HZ:
        w = [t for t in later if X.arr(t) - a0 <= h * 1000]
        if w:
            best = max(w, key=val); peak[h] = (val(best), (X.arr(best) - a0) / 1000)
    for h in AT:
        w = [t for t in later if X.arr(t) - a0 <= h * 1000]
        held[h] = val(w[-1]) if w else 0.0
    rows.append(dict(run=x["run"], m=m, why=x["close"].get("exit_why"), real=real, peak=peak, held=held, sol=b["sol"] / 1e9))
json.dump(rows, open(f"{D}/tp_potential.json", "w"), indent=1)
pc = lambda v: f"{100 * v:+6.1f}%"
for grp, sel in (("TAKE-PROFIT exits", [r for r in rows if r["why"] == "take-profit"]), ("ALL fills", rows)):
    print(f"\n=== {grp}: {len(sel)} trades (P&L vs our cost incl. pump fees, tips excluded)")
    print(f"{'run':6s} {'token':7s} {'exit':12s} {'we got':>8s} | " + " ".join(f"{'peak<=' + str(h) + 's':>15s}" for h in HZ) + " | " + " ".join(f"{'held ' + str(h) + 's':>9s}" for h in AT))
    for r in sel:
        print(f"{r['run']:6s} {r['m'][:6]:7s} {r['why'] or '?':12s} {pc(r['real']) if r['real'] is not None else '   ?':>8s} | "
              + " ".join(f"{pc(r['peak'][h][0]) + ' @' + format(r['peak'][h][1], '.1f'):>15s}" if h in r['peak'] else f"{'-':>15s}" for h in HZ) + " | "
              + " ".join(f"{pc(r['held'][h]):>9s}" for h in AT))
    if not sel: continue
    print("  MAX     " + " ".join(f"peak<={h}s {pc(max(r['peak'][h][0] for r in sel if h in r['peak']))}" for h in HZ))
    print("  MEDIAN  " + " ".join(f"peak<={h}s {pc(statistics.median([r['peak'][h][0] for r in sel if h in r['peak']]))}" for h in HZ))
    print("  MEDIAN  " + " ".join(f"held {h}s {pc(statistics.median([r['held'][h] for r in sel]))}" for h in AT) + f" | we got {pc(statistics.median([r['real'] for r in sel if r['real'] is not None]))}")
    print("  SUM SOL " + " ".join(f"held {h}s {sum(r['held'][h] * r['sol'] for r in sel):+.4f}" for h in AT) + f" | we got {sum((r['real'] or 0) * r['sol'] for r in sel):+.4f}")
