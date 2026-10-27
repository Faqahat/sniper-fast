import json, collections, random, datetime as dt
D = "/home/moiz/sniper-data/presend_filter/daily"
W = json.load(open(f"{D}/pw8.json")) + json.load(open(f"{D}/pw26.json"))
H = 3600e9; PKT = 5 * 3600e9
for w in W:
    if w["run"] == "ams:r26":   # r26 windows: no split stored; size already 0.50
        w.setdefault("realized", None)
# active intervals per run: arm times split on gaps > 20 min (+2 min tail for the last window's 10 slots + exit)
by = collections.defaultdict(list)
for w in W: by[w["run"]].append(w["t"])
iv = {}
for r, ts in by.items():
    ts.sort(); segs = []; a = ts[0]; p = ts[0]
    for t in ts[1:]:
        if t - p > 20 * 60e9: segs.append((a, p + 120e9)); a = t
        p = t
    segs.append((a, p + 120e9)); iv[r] = segs
hours = {r: sum(b - a for a, b in s) / H for r, s in iv.items()}
TOT = sum(hours.values())
def tot(key, runs=None): return sum(w[key] for w in W if runs is None or w["run"] in runs)
print(f"active pre-send hours: {TOT:.2f}  " + "  ".join(f"{r} {h:.2f}" for r, h in sorted(hours.items())))
b, a = tot("before"), tot("after")
print(f"POOLED live sizes: before {b:+.3f} after {a:+.3f} over {TOT:.2f} h -> per 24 h before {b/TOT*24:+.2f} after {a/TOT*24:+.2f}")
# scale to 0.50 (INFERRED, linear in the trade part; rent + failed fees unchanged)
def s50(w, key):
    if w["run"] == "ams:r26" or not w["filled"]: return w[key]
    f = 0.5e9 / w["spend"] - 1
    if key == "before": return w[key] + w["realized"] * f
    return w[key] + (w["realized"] * f if w.get("kept") else 0)
b5, a5 = sum(s50(w, "before") for w in W), sum(s50(w, "after") for w in W)
print(f"POOLED at 0.50 (INFERRED linear): before {b5:+.3f} after {a5:+.3f} -> per 24 h before {b5/TOT*24:+.2f} after {a5/TOT*24:+.2f}")
# periods
P = {"Night1 10-25/26 (r19,r20,r21,r22,r23)": ["ams:r19", "ams:r20", "fra:r21", "fra:r22", "fra:r23"],
     "Day1 10-26 16-20 (FRA r24)": ["fra:r24"], "Night2 10-26/27 (AMS r24,r25)": ["ams:r24", "ams:r25"], "Day2 10-27 07-14 (AMS r26, 0.50)": ["ams:r26"]}
for name, rs in P.items():
    h = sum(hours[r] for r in rs); bb = tot("before", rs); aa = tot("after", rs)
    bb5 = sum(s50(w, "before") for w in W if w["run"] in rs); aa5 = sum(s50(w, "after") for w in W if w["run"] in rs)
    print(f"  {name:40s} {h:5.2f} h | before {bb:+.3f} ({bb/h*24:+.2f}/day) | QUIET {aa:+.3f} ({aa/h*24:+.2f}/day) | at 0.50: {bb5/h*24:+.2f} -> {aa5/h*24:+.2f}/day")
# split of the QUIET gain by research role
for name, rs in {"dev": ["ams:r24", "ams:r25"], "validation": ["ams:r19", "ams:r20", "fra:r21", "fra:r22", "fra:r23", "fra:r24"], "holdout": ["ams:r26"]}.items():
    h = sum(hours[r] for r in rs); g = tot("after", rs) - tot("before", rs)
    print(f"  QUIET gain {name:10s} {g:+.3f} in {h:.2f} h = {g/h*24:+.2f}/day")
# hour-of-day (PKT) profile
cov = collections.defaultdict(float); pb = collections.defaultdict(float); pa = collections.defaultdict(float)
for r, segs in iv.items():
    for a0, b0 in segs:
        t = a0
        while t < b0:
            hh = int(((t + PKT) // H) % 24); nxt = min(b0, ((t + PKT) // H + 1) * H - PKT)
            cov[hh] += (nxt - t) / H; t = nxt
for w in W:
    hh = int(((w["t"] + PKT) // H) % 24); pb[hh] += w["before"]; pa[hh] += w["after"]
rb_all, ra_all = b / TOT, a / TOT
db = da = 0; filled = []
row = []
for hh in range(24):
    if cov[hh] >= 0.3: db += pb[hh] / cov[hh]; da += pa[hh] / cov[hh]
    else: db += rb_all; da += ra_all; filled.append(hh)
    row.append(f"{hh:02d}:{cov[hh]:.1f}h {pb[hh]/max(cov[hh],1e-9):+.3f}->{pa[hh]/max(cov[hh],1e-9):+.3f}" if cov[hh] >= 0.3 else f"{hh:02d}:none")
print("hour-of-day PKT (coverage h, SOL/h before->QUIET):"); [print("   " + "  ".join(row[i:i+4])) for i in range(0, 24, 4)]
print(f"TIME-OF-DAY weighted day (uncovered hours {filled} filled with pooled rate): before {db:+.2f}  QUIET {da:+.2f}")
# bootstrap: 1-hour blocks (run, segment, hour from segment start); rate per block; resample 24 h of blocks
blocks = []
for r, segs in iv.items():
    for a0, b0 in segs:
        n = 0; t = a0
        while t < b0:
            e = min(b0, t + H); ln = (e - t) / H
            if ln >= 0.25:
                ws = [w for w in W if w["run"] == r and t <= w["t"] < e]
                blocks.append((ln, sum(w["before"] for w in ws), sum(w["after"] for w in ws)))
            t = e
random.seed(1)
def boot(idx):
    res = []
    for _ in range(20000):
        ln = vb = va = 0.0
        while ln < 24:
            L, x, y = blocks[random.randrange(len(blocks))]; ln += L; vb += x; va += y
        res.append((vb * 24 / ln, va * 24 / ln))
    return res
res = boot(None)
for k, nm in ((0, "before"), (1, "QUIET")):
    v = sorted(x[k] for x in res); n = len(v)
    print(f"BOOTSTRAP 24 h from {len(blocks)} one-hour blocks, {nm}: p10 {v[n//10]:+.2f}  p50 {v[n//2]:+.2f}  p90 {v[9*n//10]:+.2f}  P(<0) {sum(1 for x in v if x < 0)/n:.0%}")
nb = sum(1 for x in blocks if x[2] < 0); print(f"one-hour blocks: {len(blocks)}, negative with QUIET {nb}, negative before {sum(1 for x in blocks if x[1] < 0)}")
fills = sum(1 for w in W if w["filled"]); kept = sum(1 for w in W if w["filled"] and (w.get("kept", None) == 1 or (w['run']=='ams:r26' and abs(w['after'])>0 and w['filled'])))
print(f"fills {fills} over {TOT:.1f} h = {fills/TOT*24:.0f}/day")
