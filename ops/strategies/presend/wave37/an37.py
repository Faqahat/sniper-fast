import json, numpy as np, datetime as D
R = json.load(open("/home/moiz/sniper-data/wave37/wave37.json")); n = len(R)
A = lambda k: np.array([r[k] for r in R])
pk = lambda t: (D.datetime.utcfromtimestamp(t) + D.timedelta(hours=5))
bt = A("bt"); print("fills", n, "PKT", pk(bt.min()), "->", pk(bt.max()))
print("timer-leg |model - real curve out| mean mSOL", np.mean(abs(A("base") - A("sout"))) * 1e3, "max", np.max(abs(A("base") - A("sout"))) * 1e3)
print("real pnl sum SOL", A("pnl").sum(), "mean mSOL", A("pnl").mean() * 1e3, "size mean", A("sin").mean())
def ci(d): b = [np.random.default_rng(i).choice(d, len(d)).mean() for i in range(4000)]; return np.percentile(b, [5, 95])
for lab, b, w in (("wave TP10/SL20 all", "base", "wave"), ("wave TP10/SL20 -20%", "base20", "wave20"), ("wave TP20/SL50 all", "base", "tpw"), ("wave TP20/SL50 -20%", "base20", "tpw20")):
    d = (A(w) - A(b)) * 1e3; lo, hi = ci(d)
    print(f"{lab}: {d.mean():+.2f} mSOL/fill [{lo:+.2f},{hi:+.2f}] total {d.sum()/1e3:+.3f} SOL better {np.sum(d>0.05)} worse {np.sum(d<-0.05)} same {np.sum(abs(d)<=0.05)}")
d = (A("wave") - A("base")) * 1e3; o = np.argsort(d)
for name, ix in (("worst", o[:5]), ("best", o[::-1][:5])):
    print(name)
    for i in ix: r = R[i]; print(f"  {d[i]:+.1f} mSOL  {pk(r['bt']):%H:%M} dump {r['dump']:.2f} why {r['why']} https://gmgn.ai/sol/token/{r['m']}")
h = np.array([pk(b).hour for b in bt]); d20 = (A("wave20") - A("base20")) * 1e3; dt = (A("tpw") - A("base")) * 1e3
print("by PKT hour: n, wave-timer all, -20%, TP20/SL50 all (mSOL/fill)")
for x in sorted(set(h)): s = h == x; print(f"  {x:02d}: {s.sum():3d} {d[s].mean():+6.2f} {d20[s].mean():+6.2f} {dt[s].mean():+6.2f}")
dp = A("dump"); print("by dump size (SOL):")
for lo, hi in ((0, 1), (1, 2), (2, 4), (4, 1e9)):
    s = (dp >= lo) & (dp < hi); print(f"  {lo}-{hi}: {s.sum():3d} {d[s].mean() if s.any() else 0:+6.2f} {d20[s].mean() if s.any() else 0:+6.2f} {dt[s].mean() if s.any() else 0:+6.2f}")
print("by live exit:", {w: (int((A('why') == w).sum()), round(float(d[A('why') == w].mean()), 2)) for w in set(A("why"))})
