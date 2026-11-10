import sys, glob, pickle, json, statistics as St
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/f3_omen4check/src"); import o4sim as O
run, lab, t0, t1 = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
fs = [f for f in sorted(glob.glob(f"{O.TAPE}/{run}/*.pkl")) if t0 - 900 <= int(f.split("_")[-1][:-4]) <= t1 + 300]
tl0 = int(fs[0].split("_")[-1][:-4]) + 600; tl1 = int(fs[-1].split("_")[-1][:-4]) + 300 - 60
t0 = max(t0, tl0); t1 = min(t1, tl1)
D = O.load(fs)
live = [r for r in pickle.load(open("/home/it/sniper-data/filters3/omen4_check/live.pkl", "rb")) if t0 <= r["t"] <= t1 and r["pnl"] is not None]
S = St.median(r["size"] for r in live) if live else 0.55
res = dict(run=run, lab=lab, t0=t0, t1=t1, hours=(t1 - t0) / 3600, live_n=len(live), live_pnl=sum(r["pnl"] for r in live), size=S)
cfgs = {"OMEN4_frozen": dict(O.DEF, W=10, RE=True, EXIT="wave", TOL=0.10, S=0.5, TRIP=0.0),
        "timer291_live": dict(O.DEF, S=S, TRIP=0.0),
        "wave_live_t10": dict(O.DEF, EXIT="wave", TOL=0.10, S=S, TRIP=0.0)}
for name, P in cfgs.items():
    fills, ft, arm = O.run(D, P); fills = [f for f in fills if t0 <= f["t"] <= t1]
    net = [f["gross"] / 1e9 - 0.00076 for f in fills]
    by = {}
    for f in fills: by.setdefault(f["m"], []).append(f)
    pr = []; ml = set()
    for k, r in enumerate(live):
        c = [f for f in by.get(r["mint"], []) if abs(f["s"] - r["slot"]) <= 3]
        if c: pr.append((c[0]["gross"] / 1e9 - 0.00076, r["pnl"], r["size"])); ml.add(id(c[0]))
    simonly = [f["gross"] / 1e9 - 0.00076 for f in fills if id(f) not in ml]
    res[name] = dict(n=len(fills), net=sum(net), ft_sol=(arm - len(fills)) * 5120 / 1e9 * min(1, (t1 - t0) / max(1, (tl1 - tl0))),
                     matched=len(pr), m_sim=sum(a for a, b, s in pr), m_live=sum(b for a, b, s in pr),
                     m_diff_med=(St.median(a - b for a, b, s in pr) * 1e3 if pr else None),
                     simonly_n=len(simonly), simonly_net=sum(simonly), liveonly_n=len(live) - len(pr),
                     liveonly_pnl=sum(r["pnl"] for r in live) - sum(b for a, b, s in pr))
print(json.dumps(res), flush=True)
open("/home/it/sniper-data/filters3/omen4_check/calib.jsonl", "a").write(json.dumps(res) + "\n")
