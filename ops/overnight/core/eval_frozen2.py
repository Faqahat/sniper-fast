#!/usr/bin/env python3
# Forward test of the strategies frozen at 02:24 (dryrun/frozen2.json): recompute the outcome table on the latest synced
# data (phaseA_dry, shadow timelines), then run the frozen exp.py walk-forward logic and count only launches created
# after the freeze. Also S4 after its own freeze (01:10). Output: report/frozen2_forward.json
import os, sys, json, datetime, subprocess
os.environ["RP_PHASEA_R2"] = "phaseA_dry"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
HERE = "/home/moiz/sniper/ops/overnight/core"
subprocess.run([sys.executable, "-I", os.path.join(HERE, "precompute_all.py")], check=True, env=dict(os.environ), cwd=HERE)
import exp, statistics
# data refresh only (rules unchanged): the case wallets' attempts up to the latest sync (the dry run's attempts file)
for m, v in json.load(open("/home/moiz/sniper/ops/overnight/dryrun/attempts_dry.json")).items(): exp.ATT[m].update(v)
T2 = datetime.datetime(2026, 10, 23, 2, 24, tzinfo=datetime.timezone.utc).timestamp()
T1 = datetime.datetime(2026, 10, 23, 1, 10, tzinfo=datetime.timezone.utc).timestamp()
def run_from(strategy, Lm, t_from):
    # same as exp.run but keep only launches created at/after t_from
    import collections
    L, R = exp.L, exp.R
    ev = sorted([(bt, 0, d, w) for bt, d, w in exp.LED] + [(c["bt"], 1, m, None) for m, c in L.items() if c.get("bt")])
    att = collections.defaultdict(collections.Counter); nl = collections.Counter(); hist = collections.defaultdict(list); pend = []; out = []
    for bt, kind, x, w in ev:
        while pend and pend[0][0] <= bt:
            _, d, v = pend.pop(0); hist[d].append(v)
        if kind == 0: att[w][x] += 1; continue
        m = x; c = L[m]; d = c["user"]; r = R.get(m)
        if r and str(Lm) in r:
            st = dict(att={k: att[k][d] for k in att}, n=nl[d], hist=hist[d], r=r)
            B = strategy(st)
            if B and bt >= t_from:
                o = r[str(Lm)]; v = (o.get(str(B)) if o["ok"] else -0.005)
                if v is not None: out.append((bt, m, v, B))
            if r[str(Lm)]["ok"] and r[str(Lm)].get("0.5") is not None: pend.append((bt + 60, d, r[str(Lm)]["0.5"])); pend.sort()
        nl[d] += 1
        for k in exp.ATT.get(m, {}): att[k][d] += 1
    return out
res = {}
for name, f, t0 in (("S4 (frozen 01:10)", exp.STRATS["S4 (9Sh2fd+DGmspi list) 0.5"], T1), ("S4G (frozen 02:24)", exp.STRATS["S4 + gate (drop deployers whose own fills avg < 0)"], T2),
                    ("S4GS (frozen 02:24)", exp.STRATS["S4 + gate + size"], T2), ("MULTI_GS (frozen 02:24)", exp.STRATS["MULTI list + gate + size"], T2),
                    ("S4 same window as S4G (02:24)", exp.STRATS["S4 (9Sh2fd+DGmspi list) 0.5"], T2)):
    for Lm in (45, 75):
        v = run_from(f, Lm, t0)
        last = max((b for b, _, _, _ in v), default=t0)
        res.setdefault(name, {})[str(Lm)] = dict(tot=sum(x for _, _, x, _ in v), n=len(v), fills=sum(1 for _, _, x, _ in v if x != -0.005),
                                                 hours=(last - t0) / 3600, trades=[(b, m, x, B) for b, m, x, B in v])
        print(f"{name:32} L{Lm}: {sum(x for _, _, x, _ in v):+6.2f} SOL, fills {sum(1 for _, _, x, _ in v if x != -0.005)}/{len(v)}, {(last - t0) / 3600:.1f} h")
json.dump(res, open("/home/moiz/sniper/ops/overnight/report/frozen2_forward.json", "w"))
