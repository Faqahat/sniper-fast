#!/usr/bin/env python3
# FORWARD TEST of every frozen strategy (read-only): rebuild the outcome table on the latest synced data (phaseA_dry +
# shadow timelines), refresh the copied wallets' attempts (data only), run each strategy's frozen rule walk-forward and
# count only launches created after that strategy's freeze time. Output: report/forward.json + a printed table.
# Do not run while a dry-run cycle is rebuilding phaseA_dry (check dryrun/cycle.log / pgrep cycle.sh).
import os, sys, json, datetime, subprocess, statistics, collections
os.environ["RP_PHASEA_R2"] = "phaseA_dry"
HERE = "/home/moiz/sniper/ops/overnight/core"; sys.path.insert(0, HERE)
if "--no-rebuild" not in sys.argv:
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "precompute_all.py")], check=True, env=dict(os.environ), cwd=HERE)
import exp
for m, v in json.load(open("/home/moiz/sniper/ops/overnight/dryrun/attempts_dry.json")).items(): exp.ATT[m].update(v)
T = lambda h, mi: datetime.datetime(2026, 10, 23, h, mi, tzinfo=datetime.timezone.utc).timestamp()
S9 = exp.S9; g = lambda st: exp.gate_ok(st)
good = lambda st: len(st["hist"]) >= 3 and statistics.mean(st["hist"]) >= 0.02
STR = [  # (name, rule, frozen at)
    ("S4", lambda st: 0.5 if exp.listed(st, S9) else 0, T(1, 10)),
    ("S4G", lambda st: 0.5 if exp.listed(st, S9) and g(st) else 0, T(2, 24)),
    ("S4GS", lambda st: (1.0 if good(st) else 0.5) if exp.listed(st, S9) and g(st) else 0, T(2, 24)),
    ("MULTI_GS", lambda st: (1.0 if good(st) else 0.5) if exp.listed(st, exp.MULTI) and g(st) else 0, T(2, 24)),
    ("S4GM", lambda st: (1.0 if st["r"]["mc_b"] >= 36 else 0.5) if exp.listed(st, S9) and g(st) else 0, T(2, 46)),
    ("S4GSM", lambda st: (1.0 if (good(st) or st["r"]["mc_b"] >= 36) else 0.5) if exp.listed(st, S9) and g(st) else 0, T(2, 46)),
    ("S4G_BIG_ONLY", lambda st: 1.0 if exp.listed(st, S9) and g(st) and st["r"]["mc_b"] >= 36 else 0, T(2, 46)),
    ("S4G_1SOL", lambda st: 1.0 if exp.listed(st, S9) and g(st) else 0, T(2, 46)),
]
def run_from(strategy, Lm, t_from):
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
                if v is not None: out.append(dict(bt=bt, mint=m, pnl=v, size=B, name=c.get("name"), dep=d))
            if r[str(Lm)]["ok"] and r[str(Lm)].get("0.5") is not None: pend.append((bt + 60, d, r[str(Lm)]["0.5"])); pend.sort(key=lambda z: z[0])
        nl[d] += 1
        for k in exp.ATT.get(m, {}): att[k][d] += 1
    return out
res = {}; last_bt = max(c["bt"] for c in exp.L.values() if c.get("bt") and c["run"] == "R2")
for name, f, t0 in STR:
    for Lm in (45, 75):
        v = run_from(f, Lm, t0)
        res.setdefault(name, {"frozen": t0})[str(Lm)] = dict(tot=sum(x["pnl"] for x in v), n=len(v), fills=sum(1 for x in v if x["pnl"] != -0.005),
                                                             sol_in=sum(x["size"] for x in v if x["pnl"] != -0.005), hours=(last_bt - t0) / 3600, trades=v)
print(f"forward data through {datetime.datetime.fromtimestamp(last_bt, datetime.timezone.utc):%H:%M} UTC")
for name, r in res.items():
    print(f"   {name:14} frozen {datetime.datetime.fromtimestamp(r['frozen'], datetime.timezone.utc):%H:%M}: " + " | ".join(f"L{Lm} {r[Lm]['tot']:+6.2f} SOL fills {r[Lm]['fills']}/{r[Lm]['n']} over {r[Lm]['hours']:.1f} h" for Lm in ("45", "75")))
json.dump(res, open("/home/moiz/sniper/ops/overnight/report/forward.json", "w"))
