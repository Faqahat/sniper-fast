# S3 (attempt-rate deployer list, walk-forward) in the development window: per-trade stats, bootstrap CI, fee sensitivity
import sys, os, json, gzip, collections, statistics, random
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
exec(open("ana_rate_wf.py").read().split("for name, f in")[0])
R = [r for r in rows if (lambda a, n: a >= 2 and (n == 0 or a / n >= 0.10))(*state[r["mint"]])]
hours = (rows[-1]["bt"] - rows[0]["bt"]) / 3600
random.seed(1)
print(f"S3 dev window: {len(R)} trades in {hours:.1f} h = {len(R) / hours:.1f}/h")
for c in ("L35", "L45", "L60", "L75", "L35_B1", "L35_drop", "L60_drop"):
    v = [r["cfg"][c]["pnl"][i] for r in R if c in r["cfg"]]
    B = 1.0 if c.endswith("B1") else 0.5
    bs = sorted(statistics.mean(random.choices(v, k=len(v))) for _ in range(2000))
    fee = " ".join(f"fee{f}%:{sum(v) + (0.02 - f / 100) * B * len(v):+.2f}" for f in (0.5, 1, 3))
    print(f"   {c:9} total {sum(v):+6.2f} SOL | mean {statistics.mean(v):+.4f} (95% CI {bs[50]:+.4f}..{bs[1950]:+.4f}) | per h {sum(v) / hours:+.2f} SOL | {fee}")
