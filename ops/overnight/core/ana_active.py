import sys, os, json, gzip, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
exec(open("ana_rate_wf.py").read().split("for name, f in")[0])
# previous launch of the same deployer (any time before this one): was it attempted by 9Sh2fd/DGmspi?
seqs = collections.defaultdict(list)
for m, c in L.items():
    if c.get("bt"): seqs[c["user"]].append((c["bt"], m))
prev_att = {}
for d, s in seqs.items():
    s.sort(); p = None
    for bt, m in s:
        prev_att[m] = p
        p = int("9Sh2fd" in A.get(m, {}) or "DGmspi" in A.get(m, {}))
S3 = lambda r: (lambda a, n: a >= 2 and (n == 0 or a / n >= 0.10))(*state[r["mint"]])
SEL = {"S3 (list by attempt rate)": S3,
       "ACTIVE: prev launch of deployer attempted": lambda r: prev_att.get(r["mint"]) == 1,
       "S3 and prev attempted (active)": lambda r: S3(r) and prev_att.get(r["mint"]) == 1,
       "S3 and prev NOT attempted (paused)": lambda r: S3(r) and prev_att.get(r["mint"]) == 0}
for name, f in SEL.items():
    R = [r for r in rows if f(r)]
    out = []
    for c in ("L35", "L45", "L60", "L75"):
        v = [r["cfg"][c]["pnl"][i] for r in R if c in r["cfg"]]; a = sum(r["cfg"][c]["pnl"][i] for r in R if c in r["cfg"] and r["bt"] < mid)
        out.append(f"{c} {sum(v):+6.2f} ({a:+.1f}/{sum(v) - a:+.1f})")
    att_now = sum(1 for r in R if "9Sh2fd" in r["att"] or "DGmspi" in r["att"])
    print(f"{name:42} n {len(R):4} (they attempted {att_now}) | " + " | ".join(out))
