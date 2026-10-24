#!/usr/bin/env python3
# The live paper's own picks (sel/live_trades.jsonl, 10-23 19:32 PKT ->) re-traded at the REAL landing measured live on 10-24
# (FRZ test: our buys executed 108 and 123 ms after the dump): entry 35..150 ms, 2% guard, real follower limits, size DIP_B.
# A guard-skipped pick costs the failed buy's fee (0.0005 SOL). -> table per latency for the engine's exit and the paper's main exit.
import os, sys, json, collections
os.environ.update(RP_PHASEA_R2="phaseA_selfwd", RP_PHASEA_R3="phaseA_r3live", SELL_LAT="75", SLIPIMP="1", DIP_REAL_SLIP="1", SEL_SLIP="1",
                  DIP_LATS="35,50,75", DIP_BUSY="0", DIP_HLAG="0", DIP_MAX_AGE="1800", DIP_COHORT_FILE="/home/moiz/sniper/ops/overnight/sel/cohort_train.json")
os.environ.setdefault("DIP_B", "0.25")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import selexit2 as X
import live_exits as LE
from multiprocessing import Pool
LATS = (35, 75, 100, 110, 125, 150); EX = ("tp5_sl10_1.3s", "tp8_sl5_1.3s"); FAIL = 0.0005
recs = [json.loads(l) for l in open("/home/moiz/sniper/ops/overnight/sel/live_trades.jsonl")]
need = collections.defaultdict(dict)
for r in recs: need[r["m"]][r["age"]] = r["tier"]
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
            done.add(age); out.append((need[m][age], {L: LE.detail(X, tr, k, L) for L in LATS}))
    return out
if __name__ == "__main__":
    R = []
    with Pool(6) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=2): R += o
    print(f"live paper picks re-priced: {len(R)} of {len(recs)} | size {os.environ['DIP_B']} SOL | failed buy = -{FAIL} SOL")
    for tier in ("strict", "both"):
        rr = [x for t, x in R if tier == "both" or t == tier]
        print(f"\n{tier} tier ({len(rr)} picks):")
        for nm in EX:
            row = []
            for L in LATS:
                v = [x[L] for x in rr if x.get(L) is not None]
                fills = [x[nm][0] for x in v if x["f"]]; sk = sum(1 for x in v if not x["f"])
                row.append(f"{L} ms {sum(fills) - FAIL * sk:+.3f} ({len(fills)} fills, {sum(1 for f in fills if f > 0)} won)")
            print(f"  {LE.label(nm):26s} " + " | ".join(row))
