#!/usr/bin/env python3
"""SPEED35 step 3 [MEASURED stream + MODELLED change]: where our first try lands after an outside sell, now and if our tries
landed faster. Engine facts used: in an armed window the engine sends a pre-signed try every ~26.5 ms (MEASURED r37); each landed
try has send time and feed rx time (latency L = rx - send). We keep every real send time and only change L:
  prop m : L' = L * m / median(L)   (whole distribution faster, spread shrinks too)
  shift m: L' = max(L - (median(L) - m), 5 ms)   (constant saving, same spread)
The first try (in arrival time) after the sell is the landing; each try keeps its REAL chain position
(coordinate c = slot*SMS + idx share of the slot, SMS 213 ms MEASURED) moved earlier by the ms it saves; the dump's position is exact.
Check row 'time1' (factor 1) must equal 'cur'.
Sells: decision t -> land rx scaled by the same factor; new landing slot/pos from the same clock.
Out: /home/moiz/sniper-data/speed35/scen.pkl {run: {setting: {"scen": [((doff, idx), w)], "mix": [(h, pos, w)], ...}}}"""
import json, pickle, collections, numpy as np
D = "/home/moiz/sniper-data/speed35"; SMS = 213.0
B = pickle.load(open(f"{D}/rows.pkl", "rb")); TAPES = B["tapes"]; MAXI = B["maxi"]
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
RUNS = {"r36": "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r36.jsonl", "r37": f"{D}/dip_ams_r37.jsonl"}
def mx(s): return MAXI.get(s, 400)
def cc(s, i): return s * SMS + (i + 0.5) / (mx(s) + 1.0) * SMS
def pos_of(c):
    s = int(c // SMS); return s, int((c - s * SMS) / SMS * (mx(s) + 1))
SET = [("cur", None), ("time1", ("p", None))] + [(f"prop{m}", ("p", m)) for m in (50, 35, 25, 10)] + [("shift35", ("s", 35))]

def load(fn):
    sends = {}; lands = {}; wins = []; cur = {}; exits = {}; sells = []; fills = {}
    for l in open(fn):
        if '"ev":"presend_' not in l: continue
        r = json.loads(l); e = r["ev"]
        if e == "presend_attempt": sends[r["sig"]] = (r["t"], r["mint"])
        elif e == "presend_attempt_land" and r.get("first_rx") and r.get("slot") and r.get("idx") is not None: lands[r["sig"]] = (r["slot"], r["idx"], r["first_rx"])
        elif e == "presend_live_arm": cur[r["trig"]["mint"]] = {"sig": r["trig"]["sig"], "t0": r["trig"]["t"], "mint": r["trig"]["mint"]}
        elif e == "presend_live_disarm":
            w = cur.pop(r["mint"], None)
            if w: w["t1"] = r["t"]; w["slot1"] = r["slot"]; wins.append(w)
        elif e == "presend_live_fill": fills[(r["mint"], 1)] = r
        elif e == "presend_live_exit": exits[(r["mint"], r.get("pid"), r.get("round"))] = r
        elif e == "presend_live_sell_land": sells.append(r)
    return sends, lands, wins, exits, sells, fills

def scen_from(samples):
    by = collections.defaultdict(list)
    for d, i in samples: by[min(d, 3)].append(i)
    n = len(samples); out = []
    for d, v in sorted(by.items()):
        qs = np.percentile(v, np.arange(5, 100, 10))
        for q in qs: out.append(((d, int(round(q))), len(v) / n / 10))
    return out

res = {}
for rn, fn in RUNS.items():
    sends, lands, wins, exits, sells, fills = load(fn)
    A = sorted((cc(s, i), rx / 1e6) for s, i, rx in lands.values())
    Ac = np.array([a[0] for a in A]); Ao = np.array([a[1] - a[0] for a in A])
    def off(c):
        k = np.searchsorted(Ac, c); lo, hi = max(0, k - 3), min(len(Ac), k + 3); return float(np.median(Ao[lo:hi]))
    def t_of(c): return c + off(c)
    def c_of(t):
        c = t - off(t - Ao[len(Ao) // 2])
        for _ in range(3): c = t - off(c)
        return c
    L = [lands[s][2] / 1e6 - sends[s][0] / 1e6 for s in lands if s in sends]
    medL = float(np.median(L)); print(rn, "landed tries", len(L), "median L ms", round(medL, 1), "anchors", len(A))
    bym = collections.defaultdict(list)
    for s, (t, m) in sends.items():
        if s in lands: bym[m].append((t / 1e6, lands[s][2] / 1e6, cc(lands[s][0], lands[s][1])))
    out = {}
    for name, how in SET:
        samp = []; ndump = 0; nnone = 0
        for w in wins:
            tape = TAPES.get(w["sig"])
            if not tape: continue
            tr = [x for x in tape if x[8] not in OURS]
            trig = next((x for x in tr if True), None)
            tries = [x for x in bym[w["mint"]] if w["t0"] / 1e6 - 1 <= x[0] <= w["t1"] / 1e6]
            if not tries: continue
            for x in tr:
                if x[3] or x[0] > w["slot1"]: continue
                cd = cc(x[0], x[1]); td = t_of(cd)
                if td < tries[0][1] or td > tries[-1][1] - 30: continue  # only dumps inside the live try stream (window clock)
                ndump += 1
                if how is None:
                    after = [c for _, _, c in tries if c > cd]
                    if not after: nnone += 1; continue
                    c1 = min(after)
                else:
                    k = (how[1] or medL) / medL
                    # each try keeps its real chain position, moved earlier by the time it saves (1 ms = 1 coordinate unit)
                    arr = [c - ((rx - ts) - ((rx - ts) * k if how[0] == "p" else max(rx - ts - (medL - (how[1] or medL)), 5.0))) for ts, rx, c in tries]
                    aft = [a for a in arr if a > cd]
                    if not aft: nnone += 1; continue
                    c1 = min(aft)
                s1, i1 = pos_of(c1)
                d = s1 - x[0]
                samp.append((d, max(i1 - x[1], 1) if d == 0 else i1))
        S = []
        for sl in sells:
            ex = exits.get((sl["mint"], sl.get("pid"), sl.get("round"))); fl = fills.get((sl["mint"], 1))
            if not ex or not fl: continue
            cdec = c_of(ex["t"] / 1e6); ms = sl["t"] / 1e6 - ex["t"] / 1e6
            if how is None: c1 = cc(sl["slot"], sl["idx"])
            else:
                k = (how[1] or medL) / medL
                ms2 = ms * k if how[0] == "p" else max(ms - (medL - (how[1] or medL)), 5.0)
                c1 = cc(sl["slot"], sl["idx"]) - (ms - ms2)
            s1, i1 = pos_of(c1); S.append((s1 - fl["slot"], i1 / (mx(s1) + 1)))
        g = collections.defaultdict(list)
        for h, p in S: g[max(h, 1)].append(p if h >= 1 else 0.0)
        mix = [(h, float(np.mean(v)), len(v) / len(S)) for h, v in sorted(g.items())]
        sc = scen_from(samp)
        same = np.mean([d == 0 for d, _ in samp]); gq = np.percentile([i for d, i in samp if d == 0], [10, 50, 90]).round(0).tolist()
        out[name] = {"scen": sc, "mix": mix, "n": len(samp), "none": nnone, "same": float(same), "gap_q": gq}
        print(f"  {name:8s} dumps {ndump} landed-after {len(samp)} none {nnone} | same slot {same:.0%} idx gap q10/50/90 {gq} | sell mix "
              + " ".join(f"+{h}:{w:.0%}@{p:.2f}" for h, p, w in mix), flush=True)
    res[rn] = out
pickle.dump(res, open(f"{D}/scen.pkl", "wb"))
