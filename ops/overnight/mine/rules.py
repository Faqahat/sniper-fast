# Turn the model's favourite moments into simple rules (hot-flow moments), choose on R2, test on R3 and R4. Labels as in mine.pkl (followers kept).
import pickle, numpy as np, itertools
D = pickle.load(open("mine.pkl", "rb")); D4 = pickle.load(open("mine_r4.pkl", "rb"))
X = np.concatenate([D["X"], D4["X"]]); Y = np.concatenate([D["Y"], D4["Y"]]); M = D["M"] + D4["M"]; F = D["F"]; fi = {f: i for i, f in enumerate(F)}
run = np.array([m[2] for m in M]); t = np.array([m[3] for m in M], float); tok = np.array([m[0] for m in M]); H4 = D4["hours"]
c = lambda n: X[:, fi[n]]
def nonoverlap(ix, hold=3):
    keep = []; last = {}
    for i in ix[np.argsort(t[ix])]:
        if tok[i] in last and t[i] - last[tok[i]] < hold: continue
        keep.append(i); last[tok[i]] = t[i]
    return np.array(keep, int)
res = []
for b15, nb5, gap, ch1, vlo, vhi, s1 in itertools.product((10, 20, 30), (10, 20, 30), (0.05, 0.2, 1.0), (-1, 0, 0.02), (30, 40, 45), (60, 80, 120), (0.5, 2, 99)):
    m = (c("buy15") >= b15) & (c("nb5") >= nb5) & (c("gap") <= gap) & (c("ch1") > ch1) & (c("vsol") >= vlo) & (c("vsol") < vhi) & (c("sell1") <= s1) & (c("trig_buy") == 1)
    out = {}
    for r in ("R2", "R3", "R4"):
        ix = nonoverlap(np.where(m & (run == r))[0])
        out[r] = (len(ix), Y[ix, 0].sum() if len(ix) else 0.0, Y[ix, 1].sum() if len(ix) else 0.0, Y[ix, 4].sum() if len(ix) else 0.0)
    if out["R2"][0] >= 100: res.append(((b15, nb5, gap, ch1, vlo, vhi, s1), out))
res.sort(key=lambda x: -x[1]["R2"][1] / max(x[1]["R2"][0], 1))
print("rules chosen on R2 by profit per trade at a 1 s hold (followers kept); columns: n, 1 s total, 3 s total, 3 s pessimistic")
for p, o in res[:15]:
    print(f"  buy15>={p[0]} nb5>={p[1]} gap<={p[2]} ch1>{p[3]} vsol {p[4]}-{p[5]} sell1<={p[6]} | " + " | ".join(
        f"{r} n={o[r][0]:5d} 1s {o[r][1]:+7.1f} ({o[r][1]/max(o[r][0],1):+.3f}) 3s {o[r][2]:+7.1f} pess3s {o[r][3]:+7.1f}" for r in ("R2", "R3", "R4")))
