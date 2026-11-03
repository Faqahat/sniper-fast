#!/usr/bin/env python3
"""CUSTOM37 step 7: custom-config POLICIES picked on TRAIN only, then scored FROZEN on TEST (r37).
A policy = 1 or 2 ARM-TIME features -> at most 3 segments -> one config each, from a menu of single-knob configs (the grid).
Evaluation here = the sum of each window's paired replay result under its segment's config (grid.pkl, mean of 8 worlds);
the finalists are re-simulated exactly (one-position knock-on with mixed configs) by c8_final.py.
Per segment a config other than base is taken only when on TRAIN it is: > 0 in that segment, > 0 without the segment's top 3
windows, > 0 at -20% followers, and not negative in more than 2 of the 6 TRAIN runs. Policies are ranked by TRAIN gain.
Families: L = limit / quote / exit / tries menu (size fixed 0.696), S = L + size, K = S + skip (no arm).
Out: stdout + /home/moiz/sniper-data/custom37/policies.json"""
import sys, pickle, json, itertools, datetime, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/custom37")
import c37lib as L

G = pickle.load(open(f"{L.D}/grid.pkl", "rb"))
TRAIN = ["r34", "r35", "r36", "f26", "f27", "f28"]; TEST = ["r37"]
pkt = lambda t_ms: datetime.datetime.fromtimestamp(t_ms / 1e3, datetime.UTC) + datetime.timedelta(hours=5)
MENU_L = ["drop0.10", "drop0.15", "drop0.18", "drop0.20", "drop0.25", "quote_a0.5_f0.12_c0.18", "quote_a0.6_f0.12_c0.18", "quote_a0.8_f0.12_c0.18",
          "quote_a0.8_f0.12_c0.25", "exit100", "exit300", "tp_off", "tp10", "tp30", "win6", "q3:2", "q4:2", "dl2"]
MENU_S = MENU_L + ["size0.35", "size0.5", "size0.85", "size1.0"]
MENU_K = MENU_S + ["SKIP"]
MENU_D = MENU_L + ["size0.35", "size0.5", "SKIP"]          # exposure DOWN only (no size above 0.696)
MENU_Q = [c for c in MENU_L if c.startswith(("drop", "quote"))] + ["quote_a0.7_f0.12_c0.16", "quote_a0.8_f0.12_c0.16", "quote_a0.7_f0.12_c0.15"]   # limit / quote only
STRICT = {"on": False}
ALLC = list(dict.fromkeys(MENU_K + ["quote_a0.7_f0.12_c0.16", "quote_a0.8_f0.12_c0.16", "quote_a0.7_f0.12_c0.15"]))
FEATS = {"fulldrop": lambda w: w["fulldrop"], "wsol": lambda w: w["wsol"], "pct": lambda w: w["pct"], "vsol": lambda w: w["vsol"], "age": lambda w: w["age"],
         "wh_fol": lambda w: w["wh_fol"], "wh_dumps": lambda w: w["wh_dumps"], "since_last": lambda w: w["since_last"], "n_tr_60s": lambda w: w["n_tr_60s"],
         "hour": lambda w: pkt(w["t"]).hour, "n_big2": lambda w: w.get("n_big2"), "other1": lambda w: w.get("other1"), "top_other": lambda w: w.get("top_other"),
         "n_hold": lambda w: w.get("n_hold"), "lead_fd": lambda w: w.get("lead_fd"), "lead_bam": lambda w: w.get("lead_bam"), "lead_jito": lambda w: w.get("lead_jito"),
         "lead_harm": lambda w: w.get("lead_harm")}
# arm-time holder features (c2b_holders.py) joined into the grid's window meta
for _r in G["runs"]:
    _H = pickle.load(open(f"{L.D}/holders_{_r}.pkl", "rb"))
    for _w in G["runs"][_r]["wins"]:
        _h = _H.get((_w["ses"], _w["w"]))
        if _h and _h["hist_ok"]: _w.update({k: _h[k] for k in ("n_big2", "other1", "top_other", "n_hold")})
    _Ld = pickle.load(open(f"{L.D}/leaders_{_r}.pkl", "rb"))
    for _w in G["runs"][_r]["wins"]:
        _l = _Ld.get((_w["ses"], _w["w"]))
        if _l: _w.update({"lead_" + k: _l[k] for k in ("fd", "bam", "jito", "harm")})


def build(runs):
    """per window: features, base net, base net -20%, per config delta (0 / -20%)"""
    W = []
    for r in runs:
        res = G["runs"][r]["res"]; b0 = res["base"][0.0]; b2 = res["base"][0.2]
        for n, w in enumerate(G["runs"][r]["wins"]):
            d = {}; d20 = {}
            for c in ALLC:
                if c == "SKIP": d[c] = -(b0[n, 1] + b0[n, 2]); d20[c] = -(b2[n, 1] + b2[n, 2]); continue
                a = res[c][0.0][n]; a2 = res[c][0.2][n]
                d[c] = (a[1] + a[2]) - (b0[n, 1] + b0[n, 2]); d20[c] = (a2[1] + a2[2]) - (b2[n, 1] + b2[n, 2])
            W.append({"run": r, "w": w, "f": {k: f(w) for k, f in FEATS.items()}, "d": d, "d20": d20})
    return W


def arrays(W):
    A = {"n": len(W), "run": np.array([x["run"] for x in W]), "D": {c: np.array([x["d"][c] for x in W]) for c in ALLC},
         "D20": {c: np.array([x["d20"][c] for x in W]) for c in ALLC},
         "F": {f: np.array([np.nan if x["f"][f] is None else float(x["f"][f]) for x in W]) for f in FEATS}}
    A["runs"] = sorted(set(A["run"].tolist())); A["ri"] = {r: A["run"] == r for r in A["runs"]}
    return A


def seg_ok(A, idx, c):
    """is config c safe-better than base on TRAIN segment idx (bool mask)? -> gain or None"""
    if not idx.any(): return None
    v = A["D"][c][idx]; t = v.sum()
    if t <= 0: return None
    if len(v) > 3 and t - np.partition(v, len(v) - 3)[-3:].sum() <= 0: return None
    if len(v) <= 3: return None
    if A["D20"][c][idx].sum() <= 0: return None
    neg = 0
    for r in A["runs"]:
        m = idx & A["ri"][r]
        if m.any() and A["D"][c][m].sum() < -1e6: neg += 1
    if neg > 2: return None
    if STRICT["on"]:
        # both regions must gain on their own
        for reg in ("r", "f"):
            m = idx & np.array([x.startswith(reg) for x in A["run"]])
            if m.any() and A["D"][c][m].sum() <= 0: return None
    return t


def segs_of(A, spec):
    """spec = (feat, (t1,)) / (feat, (t1, t2)) / ("2d", featA, tA, featB, tB, side) -> list of bool masks (unknown -> base)"""
    if spec[0] == "2d":
        _, fa, ta, fb, tb, side = spec
        a, b = A["F"][fa], A["F"][fb]
        known = ~np.isnan(a) & ~np.isnan(b)
        inA = known & ((a < ta) if side == "lo" else (a >= ta))
        return [~inA, inA & (b < tb), inA & (b >= tb)]
    f, ts = spec
    v = A["F"][f]; known = ~np.isnan(v)
    k = np.zeros(A["n"], int)
    for t in ts: k += (np.nan_to_num(v, nan=-1e18) >= t)
    return [known & (k == j) for j in range(len(ts) + 1)] + [~known]


def fit(A, spec, menu):
    segs = segs_of(A, spec)
    pick = []; gain = 0.0
    for j, idx in enumerate(segs):
        unknown = (spec[0] != "2d" and j == len(segs) - 1)
        best = ("base", 0.0)
        if not unknown:
            for c in menu:
                g = seg_ok(A, idx, c)
                if g is not None and g > best[1]: best = (c, g)
        pick.append(best[0]); gain += best[1]
    return pick, gain


def score(A, spec, pick, which="D"):
    segs = segs_of(A, spec); tot = 0.0; per = {}
    for j, idx in enumerate(segs):
        c = pick[j]
        if c == "base": continue
        v = A[which][c]
        tot += v[idx].sum()
        for r in A["runs"]:
            m = idx & A["ri"][r]
            per[r] = per.get(r, 0) + v[m].sum()
    return tot, per


def thresholds(A, f, qs=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)):
    v = A["F"][f]; v = v[~np.isnan(v)]
    if len(v) < 50: return []
    return sorted(set(float(np.round(np.quantile(v, q), 4)) for q in qs))


def search(Atr, menu, two_d=True):
    Wtr = Atr
    out = []
    for f in FEATS:
        ts = thresholds(Wtr, f)
        for t in ts:
            spec = (f, (t,)); pick, g = fit(Wtr, spec, menu); out.append((g, spec, pick))
        for t1, t2 in itertools.combinations(ts, 2):
            spec = (f, (t1, t2)); pick, g = fit(Wtr, spec, menu); out.append((g, spec, pick))
    if two_d:
        for fa, fb in itertools.permutations(FEATS, 2):
            for ta in thresholds(Wtr, fa, (0.2, 0.5, 0.8)):
                for tb in thresholds(Wtr, fb, (0.2, 0.5, 0.8)):
                    for side in ("lo", "hi"):
                        spec = ("2d", fa, ta, fb, tb, side); pick, g = fit(Wtr, spec, menu); out.append((g, spec, pick))
    out.sort(key=lambda x: -x[0])
    return out


def describe(spec, pick):
    if spec[0] == "2d":
        _, fa, ta, fb, tb, side = spec
        cond = f"{fa} {'<' if side == 'lo' else '>='} {ta:g}"
        return f"if {cond} and {fb} < {tb:g}: {pick[1]}; if {cond} and {fb} >= {tb:g}: {pick[2]}; else: {pick[0]}"
    f, ts = spec
    edges = [-np.inf] + list(ts) + [np.inf]
    parts = []
    for j in range(len(ts) + 1):
        lo, hi = edges[j], edges[j + 1]
        rng = (f"{f} < {hi:g}" if lo == -np.inf else (f"{f} >= {lo:g}" if hi == np.inf else f"{lo:g} <= {f} < {hi:g}"))
        parts.append(f"{rng}: {pick[j]}")
    return "; ".join(parts) + "; unknown: base"


if __name__ == "__main__":
    Wtr = arrays(build(TRAIN)); Wte = arrays(build(TEST))
    H = {}
    for r in TRAIN + TEST:
        X = pickle.load(open(f"{L.D}/win_{r}.pkl", "rb")); m = X["meta"]; H[r] = (m["t1"] - m["t0"]) / 3.6e12
    htr = sum(H[r] for r in TRAIN); hte = H["r37"]
    J = {}
    for fam, menu, strict in (("Q", MENU_Q, False), ("L", MENU_L, False), ("S", MENU_S, False), ("K", MENU_K, False), ("D", MENU_D, False), ("L-strict", MENU_L, True), ("D-strict", MENU_D, True)):
        STRICT["on"] = strict
        res = search(Wtr, menu)
        print(f"===== family {fam}: {len(res)} policies searched; top 10 by TRAIN gain (SOL) -> frozen TEST r37")
        J[fam] = []
        seen = set()
        for g, spec, pick in res:
            key = describe(spec, pick)
            if key in seen or all(p == "base" for p in pick): continue
            seen.add(key)
            te, per = score(Wte, spec, pick); te20, _ = score(Wte, spec, pick, "D20")
            tr20, _ = score(Wtr, spec, pick, "D20"); tr, ptr = score(Wtr, spec, pick)
            J[fam].append({"spec": spec, "pick": pick, "desc": key, "train": tr / 1e9, "train20": tr20 / 1e9, "test": te / 1e9, "test20": te20 / 1e9,
                           "train_runs": {k: v / 1e9 for k, v in ptr.items()}})
            if len(J[fam]) <= 10:
                print(f"  TRAIN {tr / 1e9:+.3f} ({tr / 1e9 / htr * 24:+.2f}/day; -20% {tr20 / 1e9:+.3f}) | TEST {te / 1e9:+.3f} ({te / 1e9 / hte * 24:+.2f}/day; -20% {te20 / 1e9:+.3f}) | {key}")
        # the ORACLE (upper bound): the same search fitted on r37 itself
        ores = search(Wte, menu, two_d=False)
        g, spec, pick = ores[0]
        te, _ = score(Wte, spec, pick)
        print(f"  ORACLE on r37 (upper bound, fitted on TEST, 1 feature): {te / 1e9:+.3f} SOL ({te / 1e9 / hte * 24:+.2f}/day) | {describe(spec, pick)}")
        J[fam + "_oracle"] = {"spec": spec, "pick": pick, "test": te / 1e9, "desc": describe(spec, pick)}
    json.dump(J, open(f"{L.D}/policies.json", "w"), default=str)
