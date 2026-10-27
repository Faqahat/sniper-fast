#!/usr/bin/env python3
# PRE-SEND V2 step c3: an attempt-level landing model calibrated on the live probe (AMS r16), checked against the probe's own
# dumps at the probe's rate AND at thinned rates (c2), then moved to 4 / 8 / 12 / 20 attempts per slot.
# Model (all on our server's clock; the dump is first seen at time 0):
#   attempts are sent every g = 212 / k ms from the window's start (random phase); each one draws a WHOLE probe attempt (its
#   send -> first sighting time R, and whether it landed / failed on the deadline), iid;
#   an attempt can fill the dump if it was sent before we saw the dump (t < 0: signed with the pre-dump price), lands after the
#   dump (t + R > 0), and did not fail on its deadline;  D = the first such landing (ms after the dump), none = no such attempt.
# Checked against the MEASURED per-dump D of the probe (first sighting clock and block clock) at k = 3.79, 1.90, 1.26, 0.95.
# Output: P(none) and the D quantiles per k and per time since the window went live -> presend_v2/c3_model.json (the replay's
# landing rows L2 / L4 / L8 / L12 / L20; deadline +2 = attempts fail only when they land >= 3 slots after their send slot).
import sys, json, collections
import numpy as np
F = sys.argv[1] if len(sys.argv) > 1 else "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r16.jsonl"
OUT = "/home/moiz/sniper-data/presend_v2/c3_model"
LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.append(s)
QS = (10, 25, 50, 75, 90)
def qfmt(v):
    v = [x for x in v if x is not None]
    return f"n {len(v):5d} " + " ".join(f"p{p} {np.percentile(v, p):6.1f}" for p in QS) if v else "n 0"

att = {}; land = {}
for l in open(F):
    if '"presend_attempt' not in l: continue
    o = json.loads(l)
    if o["ev"] == "presend_attempt": att[o["sig"]] = o
    elif o["ev"] == "presend_attempt_land": land[o["sig"]] = o
A = []
for s, a in att.items():
    l = land.get(s)
    if not l or l.get("res") == "unseen" or l.get("first_rx") is None:
        A.append(dict(R=np.inf, dl1=True, dl2=True, w=a["w"], n=a["n"], ts=a["t"] / 1e6, rx=None, a=None)); continue
    R = l["first_rx"] / 1e6 - a["t"] / 1e6
    dsl = (l["slot"] - a["slot"]) if l.get("slot") is not None and a.get("slot") is not None else 9
    A.append(dict(R=R, dl1=(l["res"] == "deadline"), dl2=(dsl >= 3), w=a["w"], n=a["n"], ts=a["t"] / 1e6, rx=l["first_rx"] / 1e6, a=l["a"], slot=l.get("slot")))
Rv = np.array([x["R"] for x in A]); D1 = np.array([x["dl1"] for x in A]); D2 = np.array([x["dl2"] for x in A])
say(f"probe attempts {len(A)}: landed {np.isfinite(Rv).sum()}, send -> first sighting {qfmt(Rv[np.isfinite(Rv)])}; deadline fails (+1) {D1.mean() * 100:.1f}%, "
    f"would fail at +2 (landed >= 3 slots after the send slot or unseen) {D2.mean() * 100:.1f}%")

# ---- measured per dump (first sighting clock AND block clock), with the time since the window's first attempt
byw = collections.defaultdict(list)
for x in A: byw[x["w"]].append(x)
dumps = {}
for l in land.values():
    d = l.get("d")
    if d and d.get("a"): dumps[(l["w"], d["slot"], d["idx"], d.get("j", 0))] = d
def measured(m):
    out = []
    for ph in range(m):
        for (w, s, i, j), d in dumps.items():
            seen = d.get("first_rx", d["t"]) / 1e6; X = d["a"]
            AA = [x for x in byw[w] if (x["n"] - 1) % m == ph]
            if not AA: continue
            t0 = min(x["ts"] for x in byw[w])
            c = [x for x in AA if x["rx"] is not None and x["ts"] < seen and x["a"] > X and not x["dl1"]]
            Drx = min(x["rx"] for x in c) - seen if c else None
            Da = min(x["a"] for x in c) - X if c else None
            out.append(dict(el=seen - t0, Drx=Drx, Da=Da))
    return out

rng = np.random.default_rng(7)
def sim(k, elapsed, n=20000, dl="dl1", R=Rv, DL=None):
    """D (ms) or inf per draw; attempts from -elapsed (window start) to 0 (the dump seen), every 212 / k ms"""
    g = 212.0 / k; DL = (D1 if dl == "dl1" else D2) if DL is None else DL
    nmax = int(min(elapsed, 2000) / g) + 2
    ph = rng.uniform(0, g, n)
    # send times: -ph - i*g for i = 0.. while >= -elapsed
    best = np.full(n, np.inf)
    for i in range(nmax):
        t = -ph - i * g
        ok = t >= -elapsed
        idx = rng.integers(0, len(R), n)
        land_ = t + R[idx]
        good = ok & (land_ > 0) & ~DL[idx]
        best = np.where(good & (land_ < best), land_, best)
    return best

say("\nCHECK: measured per dump vs the model at the same rate and the same time-since-window-start (first sighting clock):")
CHK = {}
for m in (1, 2, 3, 4):
    k = 3.79 / m; M = measured(m)
    el = np.array([x["el"] for x in M])
    meas = np.array([x["Drx"] if x["Drx"] is not None else np.inf for x in M])
    meas_a = np.array([x["Da"] if x["Da"] is not None else np.inf for x in M])
    simv = np.concatenate([sim(k, e, n=400) for e in el])
    f = lambda v: (100 * np.isinf(v).mean(), [float(np.percentile(v[np.isfinite(v)], p)) for p in QS])
    a1, b1 = f(meas); a2, b2 = f(simv); a3, b3 = f(meas_a)
    CHK[m] = dict(k=k, meas_none=a1, meas_q=b1, sim_none=a2, sim_q=b2, meas_block_none=a3, meas_block_q=b3)
    say(f"  k {k:4.2f}: none measured {a1:4.1f}% model {a2:4.1f}% | D measured " + " ".join(f"{x:6.1f}" for x in b1) + " | model " + " ".join(f"{x:6.1f}" for x in b2)
        + " | measured on the block clock " + " ".join(f"{x:6.1f}" for x in b3) + "  (p10 p25 p50 p75 p90 ms)")

# ---- the model grid for the replay
ELS = (0, 25, 50, 100, 150, 200, 300, 500, 1000, 3000)
KS = (1.0, 2.0, 3.79, 4.0, 8.0, 12.0, 20.0)
grid = {}
say("\nMODEL GRID (P none %, D p10 / p50 / p90 ms) per attempts per slot x time since the window went live:")
for dl in ("dl1", "dl2"):
    for k in KS:
        row = []
        for e in ELS:
            v = sim(k, e, n=20000, dl=dl)
            fin = v[np.isfinite(v)]
            qd = np.percentile(fin, np.arange(0, 101, 1)).tolist() if len(fin) else [np.inf] * 101
            grid[f"{dl}|{k}|{e}"] = dict(none=float(np.isinf(v).mean()), q=qd)
            row.append(f"{100 * np.isinf(v).mean():4.0f}% {qd[10]:5.1f}/{qd[50]:5.1f}/{qd[90]:5.1f}" if len(fin) else "100%")
        say(f"  {dl} k {k:5.2f}: " + " | ".join(f"{e}ms {r}" for e, r in zip(ELS, row)))
json.dump(dict(grid=grid, els=ELS, ks=KS, check=CHK), open(OUT + ".json", "w"))
open(OUT + ".txt", "w").write("\n".join(LOG) + "\n")
