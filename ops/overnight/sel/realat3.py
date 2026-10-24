#!/usr/bin/env python3
# The 407 wider-tier IMIT1 picks of the TEST hours (10-23 06:00-18:19 PKT, never seen by the model; sel_exitbt.py's set) re-traded
# at the REAL landing measured live on 10-24 (FRZ test: our buys executed 108 / 123 ms after the dump): entry 35..150 ms, 2% guard,
# real follower limits, size DIP_B; a guard-skipped pick costs the failed buy's fee (0.0005 SOL).
import os, sys, json, collections
os.environ.update(RP_PHASEA_R2="phaseA_sel", SELL_LAT="75", SLIPIMP="1", DIP_REAL_SLIP="1", SEL_SLIP="1", DIP_LATS="35,50,75")
os.environ.setdefault("DIP_B", "0.25")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import selexit2 as X
import live_exits as LE
from multiprocessing import Pool
LATS = (35, 50, 75, 100, 110, 125, 150); EX = ("tp5_sl10_1.3s", "tp8_sl5_1.3s", "tpnone_slnone_6s"); FAIL = 0.0005
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
            done.add(age); out.append({L: LE.detail(X, tr, k, L) for L in LATS})
    return out
if __name__ == "__main__":
    R = []
    with Pool(6) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=2): R += o
    print(f"TEST picks re-priced: {len(R)} of {sum(len(v) for v in need.values())} (12.3 h) | size {os.environ['DIP_B']} SOL | failed buy -{FAIL} SOL")
    for nm in EX:
        print(f"  {LE.label(nm)}:")
        for L in LATS:
            v = [x[L] for x in R if x.get(L) is not None]
            fills = [x[nm][0] for x in v if x["f"]]; sk = sum(1 for x in v if not x["f"])
            print(f"    {L:3d} ms: {sum(fills) - FAIL * sk:+.3f} SOL | fills {len(fills)} (won {sum(1 for f in fills if f > 0)}) | guard-skipped {sk} | per fill {sum(fills) / max(1, len(fills)):+.4f}")
