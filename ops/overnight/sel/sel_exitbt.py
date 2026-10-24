#!/usr/bin/env python3
# Fair backtest of the live run's 192 exits (live_exits.py) on the wider-tier picks of the TEST hours (10-23 06:00-18:19 PKT,
# never seen by the model), real follower limits, entry 35 / 50 / 75 ms, 2% guard. -> sel/exit_bt.json {exit: {L: [P&L, fills, wins]}}
import os, sys, json, collections
os.environ.update(RP_PHASEA_R2="phaseA_sel", SELL_LAT="75", SLIPIMP="1", DIP_REAL_SLIP="1", SEL_SLIP="1", DIP_LATS="35,50,75")
os.environ.setdefault("DIP_B", "0.5")      # buy size in SOL (owner 21:55 PKT: test 0.25 / 1 / 2)
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import selexit2 as X
import live_exits as LE
from multiprocessing import Pool
need = collections.defaultdict(set)
for l in open("/home/moiz/sniper/ops/overnight/sel/picks_imit1_top4_test.jsonl"):
    r = json.loads(l); need[r["m"]].add(r["age"])
byb = collections.defaultdict(set)
for m in need: byb[(X.L[m]["run"], X.rp.bucket(m))].add(m)
def work(key):
    run, b = key; out = []
    for m, tr in X.rp.read_bucket(run, b, byb[key]).items():
        S0 = X.L[m]["slot"]; done = set()
        for k, t in enumerate(tr):
            if t["buy"] or t["sol"] < X.MIN_SELL or t.get("syn"): continue
            age = round((t["s"] - S0) * X.SMS / 1000, 2)
            if age not in need[m] or age in done: continue
            done.add(age); out.append({str(L): LE.detail(X, tr, k, L) for L in (35, 50, 75)})
    return out
if __name__ == "__main__":
    R = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=2): R += o
    agg = {}
    for nm, *_ in LE.EXITS:
        agg[nm] = {}
        for L in ("35", "50", "75"):
            v = [r[L] for r in R if r.get(L) is not None]
            fills = [x[nm][0] for x in v if x["f"]]; skipped = sum(1 for x in v if not x["f"])
            agg[nm][L] = [round(sum(fills) - 0.0002 * skipped, 3), len(fills), sum(1 for x in fills if x > 0)]
    json.dump(agg, open("/home/moiz/sniper/ops/overnight/sel/exit_bt.json" if os.environ["DIP_B"] == "0.5" else f"/home/moiz/sniper/ops/overnight/sel/exit_bt_B{os.environ['DIP_B']}.json", "w"))
    top = sorted(agg, key=lambda n: -agg[n]["35"][0])
    print(f"buy size {os.environ['DIP_B']} SOL | TEST picks priced: {len(R)} (12.3 h). Top 20 exits by P&L at 35 ms (and 75 ms):")
    for n in top[:20]: print(f"  {LE.label(n):32s} 35 ms {agg[n]['35'][0]:+6.2f} ({agg[n]['35'][2]}/{agg[n]['35'][1]} won) | 75 ms {agg[n]['75'][0]:+6.2f} ({agg[n]['75'][2]}/{agg[n]['75'][1]})")
    n = LE.MAIN; print(f"  current main: {LE.label(n)} 35 ms {agg[n]['35'][0]:+.2f} | rank {top.index(n) + 1} of {len(top)}")
