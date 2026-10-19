#!/usr/bin/env python3
# READ-ONLY. Items 2-4: "if we landed after similar things". Trigger x landing x exit grid, realistic sim.
# Fit = hist (random sample) + fwd run 1; test = night (blind for selection). Output: search_out.txt + res.pkl
import sys, collections, statistics as st, json, pickle, itertools, math, time
sys.path.insert(0, "/root/racedeep")
from rdlib import load, pf, sim, land_time, stats, fmt, EXITS, SLOT
pros = set(json.load(open("/root/race/pros.json")))
t_start = time.time()
U = [o for o in load() if o["in_rand"]]
for o in U:
    o["gateB"] = o["dev"] >= 3 and o["glued"] >= 2 and o["n_len"] <= 12
PRE = {"all": lambda o: True, "gateB": lambda o: o["gateB"], "dev>=2": lambda o: o["dev"] >= 2, "dev<=3": lambda o: o["dev"] <= 3}


def running(o):
    """per trade index j: running state after trade j (observable in the stream up to and including j)"""
    out = []
    payers, sol, nbig, fails, his, pro, maxpf, nsell = set(), 0.0, collections.Counter(), 0, False, False, 1.0, 0
    for j, z in enumerate(o["tr"]):
        t, k, d, typ, s, p, cu, tip, v, h = z
        if typ == "E":
            fails += 1
        elif typ == "O":
            payers.add(p)
            sol += s
            for X in (0.5, 1, 2, 3, 5):
                if s >= X:
                    nbig[X] += 1
            his = his or h
            pro = pro or (p in pros)
        elif typ == "X":
            nsell += 1
        pfn = (v / o["base"]) ** 2 if v else (out[-1]["pf"] if out else 1.0)
        maxpf = max(maxpf, pfn)
        out.append(dict(j=j, k=k, n=len(payers), sol=sol, big=dict(nbig), fails=fails, his=his, pro=pro, pf=pfn, maxpf=maxpf,
                        cur=z, nsell=nsell))
    return out


TRIG = {}
for kk, X in itertools.product((1, 2, 3, 5), (0.5, 1, 2, 3)):
    TRIG[f"{kk}x outsider buy>={X}"] = lambda r, kk=kk, X=X: r["big"].get(X, 0) >= kk
for Y in (0.5, 1, 2, 3, 5, 8, 12):
    TRIG[f"cum out SOL>={Y}"] = lambda r, Y=Y: r["sol"] >= Y
for N in (1, 2, 3, 5, 8, 12):
    TRIG[f">={N} outsiders"] = lambda r, N=N: r["n"] >= N
for N, Y in ((2, 1), (3, 2), (3, 3), (5, 3), (5, 5), (8, 8)):
    TRIG[f">={N} out & >={Y} SOL"] = lambda r, N=N, Y=Y: r["n"] >= N and r["sol"] >= Y
for Y in (3, 5, 8, 10):
    TRIG[f"whale buy>={Y}"] = lambda r, Y=Y: r["cur"][3] == "O" and r["cur"][4] >= Y
    TRIG[f"whale buy>={Y} hiprio"] = lambda r, Y=Y: r["cur"][3] == "O" and r["cur"][4] >= Y and (r["cur"][6] >= 10e6 or r["cur"][7] >= 0.005)
TRIG["hiprio outsider (cu>=100M or tip>=0.01)"] = lambda r: r["cur"][3] == "O" and (r["cur"][6] >= 100e6 or r["cur"][7] >= 0.01)
TRIG["4yFAz buys"] = lambda r: r["his"]
TRIG["pro wallet buys"] = lambda r: r["pro"]
for F in (2, 5, 10, 20):
    TRIG[f"failed txs>={F}"] = lambda r, F=F: r["fails"] >= F
# second-wave / dip triggers: after a first wave, price retraced
for N, Y, dd in ((3, 3, 0.8), (3, 3, 0.65), (5, 5, 0.8), (5, 5, 0.65)):
    TRIG[f"wave1 {N}out/{Y}SOL then dip<={dd:g}x peak"] = lambda r, N=N, Y=Y, dd=dd: r["n"] >= N and r["sol"] >= Y and r["pf"] <= dd * r["maxpf"]
WIN = {"S": 0, "S..S+1": 1, "S..S+2": 2}
CAPS = (1.3, 1.6, 2.0, 99)
LAND = {"S+25": ("S", 25), "S+50": ("S", 50), "S+100": ("S", 100), "S1 front": ("S1", 0.0), "S1 q25": ("S1", 0.25), "S1 mid": ("S1", 0.5), "S1 end": ("S1", 1.0)}
XN = list(EXITS)

# --- per launch: trigger index for every (trigger, window); sims cached by (t0, exit)
res = collections.defaultdict(dict)   # (trig, win) -> mint -> (j, pf_at_trigger)
SIM = {}   # (mint, landing, j) -> {exit: (pnl2, pnl1)}
nsims = 0
for o in U:
    R = running(o)
    js = set()
    for tn, fn in TRIG.items():
        for wn, kmax in WIN.items():
            for r in R:
                if r["k"] > kmax:
                    break
                if fn(r):
                    res[(tn, wn)][o["mint"]] = (r["j"], r["pf"])
                    js.add(r["j"])
                    break
    js.add(-1)   # enter at the create (reference)
    for j in js:
        for ln, lm in LAND.items():
            t0 = land_time(o, j, lm)
            SIM[(o["mint"], ln, j)] = (tuple(round(sim(o, t0, EXITS[xn], 2.0), 5) for xn in XN),
                                       tuple(round(sim(o, t0, EXITS[xn], 1.0), 5) for xn in XN), round(pf(o, t0), 4))
            nsims += 2 * len(XN)
print(f"sims {nsims} in {time.time() - t_start:.0f}s", flush=True)
byid = {o["mint"]: o for o in U}
night = [o for o in U if o["set"] == "night"]
hours = (max(o["slot"] for o in night) - min(o["slot"] for o in night)) * 0.217 / 3600
fwd = [o for o in U if o["set"] == "fwd"]
hours_f = (max(o["slot"] for o in fwd) - min(o["slot"] for o in fwd)) * 0.217 / 3600
print(f"night {len(night)} launches over {hours:.2f} h ({len(night) / hours:.0f}/h); fwd {len(fwd)} over {hours_f:.2f} h")
pickle.dump(dict(res=dict(res), SIM=SIM, XN=XN, LAND=list(LAND), hours=hours, hours_f=hours_f), open("/root/racedeep/res.pkl", "wb"))
print("saved res.pkl", flush=True)
