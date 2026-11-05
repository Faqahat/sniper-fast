#!/usr/bin/env python3
"""CASEBOOK step 2: deliberate stratified token pick per run (seeded).
usage: c2_pick.py RUN SEED BATCHNAME  -> casebook/pick_<batch>.tsv (run, mint, stratum)"""
import sys, random, csv
OUT = "/home/moiz/sniper-data/rivals/9pQQ/casebook"
run, seed, batch = sys.argv[1], int(sys.argv[2]), sys.argv[3]
R = random.Random(seed)
rows = list(csv.DictReader(open(f"{OUT}/tokens_{run}.tsv"), delimiter="\t"))
for r in rows:
    r["n"] = int(r["n"]); r["net"] = float(r["net_mSOL"]); r["age"] = int(r["first_age"])
done = set()
try:
    import glob
    for f in glob.glob(f"{OUT}/pick_*.tsv"):
        for l in open(f): done.add(l.split("\t")[1])
except Exception: pass
rows = [r for r in rows if r["mint"] not in done]
big = sorted([r for r in rows if r["n"] >= 10 and r["net"] > 0], key=lambda r: -r["net"])
S = {
 "A_multi_win": R.sample(big[: max(3, len(big) // 4)], 3),
 "B_multi_loss": R.sample([r for r in rows if r["n"] >= 10 and r["net"] <= 0], 2),
 "C_mid": R.sample([r for r in rows if 3 <= r["n"] <= 9], 3),
 "D_two": R.sample([r for r in rows if r["n"] == 2], 2),
 "E_one_win": R.sample([r for r in rows if r["n"] == 1 and r["net"] > 30], 2),
 "F_one_bigloss": R.sample([r for r in rows if r["n"] == 1 and r["net"] < -200], 1),
 "F_one_smallloss": R.sample([r for r in rows if r["n"] == 1 and -60 < r["net"] < 0], 1),
 "G_late_first": R.sample([r for r in rows if r["age"] > 2000 and r["n"] >= 2], 2),
}
with open(f"{OUT}/pick_{batch}.tsv", "w") as fo:
    for k, v in S.items():
        for r in v:
            fo.write(f"{run}\t{r['mint']}\t{k}\t{r['n']}\t{r['net']}\t{r['age']}\t{r['first_pkt']}\n")
            print(k, r["mint"][:8], r["n"], r["net"], r["age"], r["first_pkt"])
