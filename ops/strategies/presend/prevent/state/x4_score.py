#!/usr/bin/env python3
"""STATE step 4: PICK/TEST search per PREREG.txt (/home/it/sniper-data/prevent/state/PREREG.txt).
Families: A = T2 arm-time skip, B = T2 in-window stop, C = re-arm arm-time skip. Writes RESULTS.json / RESULTS.txt."""
import pickle, json, collections, math, sys, datetime
import numpy as np
D = "/home/it/sniper-data/prevent/state"
SIZE = 0.696; FAIL = 5120e-9
PICK = ["FRA21", "FRA22", "FRA23", "FRA24", "FRA26", "FRA27", "FRA28", "AMS16", "AMS17", "AMS19", "AMS20", "AMS24", "AMS25", "AMS26", "AMS27",
        "AMS28", "AMS29", "AMS30", "AMS31", "AMS32", "AMS33", "AMS34", "AMS35", "AMS36"]
TEST = "AMS37"; R38 = "AMS38"
LIVE20 = ["FRA21", "FRA22", "FRA23", "FRA24", "FRA26", "FRA27", "FRA28", "AMS16", "AMS17", "AMS19", "AMS20", "AMS24", "AMS25", "AMS26", "AMS27",
          "AMS34", "AMS35", "AMS36", "AMS37", "AMS38"]
SHADOW = ["AMS14", "AMS15", "AMS21", "AMS22", "AMS23", "FRA15", "FRA16", "FRA20", "FRA25"]
SIX = {("AMS38", 418): "9wU2 rearm -0.262", ("AMS38", 348): "HDnC T2 -0.170", ("AMS38", 423): "7fNX T2 -0.097", ("AMS38", 424): "7fNX rearm -0.030",
       ("AMS38", 431): "27Jg T2 -0.097", ("AMS38", 390): "9hGU rearm -0.068", ("AMS38", 398): "AJvB rearm -0.045"}
QS = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95]
EPS = 1e-3; NBOOT = 2000; RNG = np.random.default_rng(7)
EVENTS = ["sell3", "sell6", "sell1sol", "sell2sol", "who_sell", "who_sell2", "bigh_sell", "lc_sell2", "lc_sell5", "cums2", "cums4", "nsell3", "nsell5",
          "drop5", "drop8", "newwhale", "up10"]
SKIPF = {"ok", "ev", "fill_prev_sell", "fill_prev_pct", "fill_prev_left", "fill_prev_is_who", "hold_sell_sol", "hold_max_sell", "sg_pct", "sg_n"}


def pkt(t_ns): return datetime.datetime.fromtimestamp(t_ns / 1e9, datetime.UTC) + datetime.timedelta(hours=5)


def build_t2(R, F):
    rows = []
    for rk, r in R.items():
        if not r["live"]: continue
        t0 = min(a for a, b in r["spans"]) if r["spans"] else min(x["t"] for x in r["wins"])
        # earlier windows on the same mint in this run (any kind): count, fills, value of those already closed
        bym = collections.defaultdict(list)
        for x in sorted(r["wins"], key=lambda x: x["t"]): bym[x["mint"]].append(x)
        for x in r["wins"]:
            f = F.get(("L", rk, x["seg"], x["w"]))
            if not f or not f.get("ok"): continue
            prev = [y for y in bym[x["mint"]] if y["t"] < x["t"] and y is not x]
            closed = [y for y in prev if (y.get("dis") or {}).get("slot") is not None and y["dis"]["slot"] + 5 < x["slot"]]
            g = {k: v for k, v in f.items() if k not in SKIPF}
            g.update(age=x["age"] if x["age"] is not None else f["age_tape"], pct=x["pct"] or 0.0, wsol=x["wsol"], prev_arms=len(prev),
                     prev_fills=sum(1 for y in prev if y["filled"]), prev_v=sum(y["v"] for y in closed) * 1000)
            v = x["v"] if x["kind"] == "t2" else (x["pnl"] or 0.0) * SIZE / x["spend"] - x["n_fail"] * FAIL
            rows.append(dict(run=rk, kind=x["kind"], w=x["w"], seg=x["seg"], v=v, filled=x["filled"], hour=(rk, int((x["t"] - t0) // 3.6e12)), f=g, ev=f.get("ev") or {},
                             x=x, raw=f, t=x["t"]))
    return rows


def arr(rows, name):
    return np.array([(r["f"].get(name) if r["f"].get(name) is not None else np.nan) for r in rows], float)


class Set:
    """a scored set of decisions: values, runs, hours, bootstrap index"""
    def __init__(self, rows, vals=None):
        self.rows = rows; self.v = np.array([r["v"] if vals is None else vals[i] for i, r in enumerate(rows)], float)
        self.filled = np.array([r["filled"] for r in rows], bool)
        self.runs = sorted(set(r["run"] for r in rows)); ri = {k: i for i, k in enumerate(self.runs)}
        self.ri = np.array([ri[r["run"]] for r in rows], int)
        hs = sorted(set(r["hour"] for r in rows)); hi = {h: i for i, h in enumerate(hs)}
        self.hi = np.array([hi[r["hour"]] for r in rows], int); self.nh = len(hs)
        self.boot = RNG.integers(0, self.nh, size=(NBOOT, self.nh))

    def score(self, gain):
        """gain = per-row SOL saved by the rule (0 where untouched)"""
        tot = float(gain.sum())
        pos = np.sort(gain[gain > 0])[::-1]
        per = np.bincount(self.ri, weights=gain, minlength=len(self.runs))
        touched = np.bincount(self.ri, weights=(gain != 0).astype(float), minlength=len(self.runs))
        help_ = int(((per > 1e-9) & (touched > 0)).sum()); hurt = int(((per < -1e-9) & (touched > 0)).sum())
        hv = np.bincount(self.hi, weights=gain, minlength=self.nh)
        b = hv[self.boot].sum(1)
        lo, hi = np.percentile(b, [5, 95])
        return dict(save=tot, wo1=tot - (pos[0] if len(pos) else 0.0), wo5=tot - pos[:5].sum(), help=help_, hurt=hurt, ci=(float(lo), float(hi)),
                    per={k: float(per[i]) for i, k in enumerate(self.runs)})


def skip_gain(S, mask):
    g = np.where(mask, -S.v, 0.0)
    lose = float(-S.v[mask & S.filled & (S.v < 0)].sum()); win = float(S.v[mask & S.filled & (S.v > 0)].sum())
    return g, lose, win


def single_rules(P, feats):
    out = []
    for fn in feats:
        a = arr(P.rows, fn)
        ok = ~np.isnan(a)
        if ok.sum() < 50: continue
        qs = np.unique(np.percentile(a[ok], QS))
        for q in qs:
            for d in (">=", "<="):
                out.append((fn, d, float(q)))
    return out


def mask_of(rows, rule):
    m = np.ones(len(rows), bool)
    for fn, d, q in rule:
        a = arr(rows, fn)
        m &= (a >= q) if d == ">=" else (a <= q)
        m &= ~np.isnan(a)
    return m


def pick_ok(sc, lose, win, share):
    return (sc["save"] > EPS and sc["wo1"] > EPS and sc["wo5"] > EPS and sc["help"] > sc["hurt"] and sc["ci"][0] > EPS and lose > win and share <= 0.30)


def search_skip(P, feats, label):
    singles = single_rules(P, feats); res = []
    for ru in singles:
        m = mask_of(P.rows, [ru]); share = m.mean()
        if m.sum() == 0 or share > 0.30: continue
        g, lose, win = skip_gain(P, m); sc = P.score(g)
        res.append(([ru], sc, lose, win, share))
    n_single = len(res)
    top = sorted([x for x in res if x[1]["save"] > 0], key=lambda x: -x[1]["wo5"])[:20]
    pairs = 0
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            ru = top[i][0] + top[j][0]
            if ru[0][0] == ru[1][0]: continue
            m = mask_of(P.rows, ru); share = m.mean()
            if m.sum() == 0: continue
            g, lose, win = skip_gain(P, m); sc = P.score(g); pairs += 1
            res.append((ru, sc, lose, win, share))
    ok = [x for x in res if pick_ok(x[1], x[2], x[3], x[4])]
    ok.sort(key=lambda x: (-x[1]["wo5"], x[4]))
    print(f"[{label}] rules tried {len(res)} (single {n_single}, pairs {pairs}); pass PICK criteria {len(ok)}", flush=True)
    return ok[:5], len(res), len(ok)


def stop_value(row, E):
    """new value of a T2 window when tries stop from the slot after event E"""
    x = row["x"]; sE = row["ev"].get(E)
    if sE is None: return row["v"]
    sc = SIZE / x["spend"]
    fails_after = sum(1 for ss, res in x["tries"] if res not in (None, "unseen", "ok") and ss is not None and ss > sE)
    if x["filled"]:
        fl = x["fills"][0]; fs = fl.get("send_slot")
        if fs is None: fs = (fl.get("slot") or 0) - 1
        if fs > sE:
            fails_before = sum(1 for ss, res in x["tries"] if res not in (None, "unseen", "ok") and (ss is None or ss <= sE))
            return -fails_before * FAIL
    return row["v"] + fails_after * FAIL


def fmt(sc): return f"{sc['save']:+.3f} (w/o1 {sc['wo1']:+.3f}, w/o5 {sc['wo5']:+.3f}; runs +{sc['help']}/-{sc['hurt']}; CI90 {sc['ci'][0]:+.2f}..{sc['ci'][1]:+.2f})"


def main():
    R = pickle.load(open(f"{D}/windows.pkl", "rb")); F = pickle.load(open(f"{D}/feats.pkl", "rb")); O = pickle.load(open(f"{D}/obs_rearm.pkl", "rb"))
    allrows = build_t2(R, F)
    T2 = [r for r in allrows if r["kind"] == "t2"]
    feats = sorted(set(k for r in T2 for k in r["f"]))
    P = Set([r for r in T2 if r["run"] in PICK]); T = Set([r for r in T2 if r["run"] == TEST]); X38 = [r for r in allrows if r["run"] == R38]
    PT = Set(P.rows + T.rows)
    hours = {k: R[k]["hours"] for k in R}
    out = {"meta": {"t2_pick_windows": len(P.rows), "t2_pick_fills": int(P.filled.sum()), "t2_test_windows": len(T.rows), "t2_test_fills": int(T.filled.sum()),
                    "t2_pick_value": float(P.v.sum()), "t2_test_value": float(T.v.sum()), "features": feats, "hours": hours}}
    print(out["meta"]["t2_pick_windows"], out["meta"]["t2_pick_fills"], out["meta"]["t2_test_windows"], out["meta"]["t2_test_fills"], round(P.v.sum(), 3), round(T.v.sum(), 3))
    L = []
    # ---------------- family A
    chosen, ntried, npass = search_skip(P, feats, "A T2 skip")
    out["A"] = {"tried": ntried, "pass_pick": npass, "rules": []}
    sh_rows = shadow_rows(R, F)
    for ru, sc, lose, win, share in chosen:
        mT = mask_of(T.rows, ru); gT, lT, wT = skip_gain(T, mT); scT = T.score(gT)
        mPT = mask_of(PT.rows, ru); gPT, lPT, wPT = skip_gain(PT, mPT); scPT = PT.score(gPT)
        m38 = mask_of(X38, ru); g38 = sum(-r["v"] for r, m in zip(X38, m38) if m and r["kind"] == "t2")
        six = {lab: bool(m) for (r, m) in zip(X38, m38) for (rk, w), lab in SIX.items() if r["run"] == rk and r["w"] == w and r["kind"] == "t2"}
        verdict = "PASS" if (scT["save"] > EPS and scPT["ci"][0] > EPS and scPT["wo1"] > EPS and sc["help"] > sc["hurt"] and lPT > wPT) else ("LEAD" if scT["save"] > EPS else "FAIL")
        pap = paper_check(sh_rows, ru)
        d = dict(rule=ru, verdict=verdict, pick=sc, pick_share=share, pick_lose=lose, pick_win=win, test=scT, test_share=float(mT.mean()), test_lose=lT, test_win=wT,
                 pooled=scPT, pooled_lose=lPT, pooled_win=wPT, r38_t2=g38, r38_share=float(np.mean([m for r, m in zip(X38, m38) if r["kind"] == "t2"])), six=six, paper=pap)
        out["A"]["rules"].append(d)
        L.append(f"A {ru} -> {verdict}\n  PICK {fmt(sc)} skip {share:.1%} lose {lose:.2f} win {win:.2f}\n  TEST r37 {fmt(scT)} skip {mT.mean():.1%}\n  POOLED {fmt(scPT)} lose {lPT:.2f} win {wPT:.2f}\n  r38 T2 {g38:+.3f}; six {six}\n  paper {pap}")
    # ---------------- family B (stop)
    out["B"] = {"tried": len(EVENTS), "rules": []}
    resB = []
    for E in EVENTS:
        gP = np.array([stop_value(r, E) - r["v"] for r in P.rows]); sc = P.score(gP)
        blocked = np.array([stop_value(r, E) != r["v"] and r["filled"] for r in P.rows])
        lose = float(-P.v[blocked & (P.v < 0)].sum()); win = float(P.v[blocked & (P.v > 0)].sum())
        resB.append((E, sc, lose, win, float(blocked.mean())))
        print(f"[B] {E:10s} PICK {fmt(sc)} fills removed {blocked.sum()} lose {lose:.2f} win {win:.2f}", flush=True)
    okB = [x for x in resB if x[1]["save"] > EPS and x[1]["wo1"] > EPS and x[1]["wo5"] > EPS and x[1]["help"] > x[1]["hurt"] and x[1]["ci"][0] > EPS and x[2] > x[3]]
    okB.sort(key=lambda x: -x[1]["wo5"])
    out["B"]["pass_pick"] = len(okB); out["B"]["all_pick"] = [dict(event=E, pick=sc, lose=lo, win=wi, removed_share=bs) for E, sc, lo, wi, bs in resB]
    for E, sc, lose, win, bs in okB[:5]:
        gT = np.array([stop_value(r, E) - r["v"] for r in T.rows]); scT = T.score(gT)
        gPT = np.array([stop_value(r, E) - r["v"] for r in PT.rows]); scPT = PT.score(gPT)
        bl = np.array([stop_value(r, E) != r["v"] and r["filled"] for r in PT.rows])
        lPT = float(-PT.v[bl & (PT.v < 0)].sum()); wPT = float(PT.v[bl & (PT.v > 0)].sum())
        g38 = sum(stop_value(r, E) - r["v"] for r in X38 if r["kind"] == "t2")
        six = {lab: round(stop_value(r, E) - r["v"], 4) for r in X38 for (rk, w), lab in SIX.items() if r["w"] == w}
        verdict = "PASS" if (scT["save"] > EPS and scPT["ci"][0] > EPS and scPT["wo1"] > EPS and sc["help"] > sc["hurt"] and lPT > wPT) else ("LEAD" if scT["save"] > EPS else "FAIL")
        out["B"]["rules"].append(dict(event=E, verdict=verdict, pick=sc, test=scT, pooled=scPT, pooled_lose=lPT, pooled_win=wPT, r38_t2=g38, six=six))
        L.append(f"B stop on {E} -> {verdict}\n  PICK {fmt(sc)}\n  TEST {fmt(scT)}\n  POOLED {fmt(scPT)} lose {lPT:.2f} win {wPT:.2f}\n  r38 T2 {g38:+.3f}; six {six}")
    # ---------------- family C (re-arm)
    C = rearm_rows(O, F, R, allrows)
    out["C"] = rearm_search(C, L)
    json.dump(out, open(f"{D}/RESULTS.json", "w"), indent=1, default=str)
    open(f"{D}/RESULTS.txt", "w").write("\n".join(L) + "\n")
    print("\n".join(L))


def shadow_rows(R, F):
    rows = []
    for rk in SHADOW:
        r = R[rk]
        t0 = min(a for a, b in r["spans"]) if r["spans"] else 0
        for x in r["shadow"]:
            if (x.get("age") or 0) < 2: continue
            f = F.get(("S", rk, x["seg"], x["w"]))
            if not f or not f.get("ok"): continue
            ex = (x.get("ex") or {}).get("c")
            v = (ex or {}).get("pnl") or 0.0
            g = {k: vv for k, vv in f.items() if k not in SKIPF}; g.update(age=x["age"], pct=x["pct"] or 0.0, wsol=x["wsol"], prev_arms=0, prev_fills=0, prev_v=0.0)
            rows.append(dict(run=rk, v=v, filled=ex is not None, hour=(rk, int((x["t"] - t0) // 3.6e12)) if x.get("t") else (rk, 0), f=g))
    return rows


def paper_check(rows, ru):
    if not rows: return {}
    m = mask_of(rows, ru)
    per = collections.defaultdict(float); n = collections.Counter()
    for r, k in zip(rows, m):
        if k: per[r["run"]] += -r["v"]; n[r["run"]] += 1
    tot = sum(per.values()); help_ = sum(1 for v in per.values() if v > 0); hurt = sum(1 for v in per.values() if v < 0)
    return {"paper_save_raw_SOL": round(tot, 3), "runs_help": help_, "runs_hurt": hurt, "per_run": {k: round(v, 3) for k, v in per.items()}, "skipped": sum(n.values()), "of": len(rows)}


def rearm_rows(O, F, R, allrows):
    """re-arm decisions: r36 obs paper (PICK), r37 obs + multiarm replay (TEST), r38 live (MEASURED) + r38 obs paper"""
    import glob
    rep = collections.defaultdict(list)
    for p in sorted(glob.glob("/home/it/sniper-data/multiarm/runs/r37/R0__*.pkl")):
        d = pickle.load(open(p, "rb"))
        for r in d["rows"]:
            if r["kind"] == "rearm": rep[tuple(r["key"])].append(r["cash"])
    rows = []
    for run, W in O.items():
        t0 = W[0]["dump"]["t"] if W else 0
        for i, x in enumerate(W):
            f = F.get(("O", run, i))
            if not f or not f.get("ok"): continue
            dm = x["dump"]; c = x["rows"].get("c") or {}
            paper = (c.get("px") or 0.0) / 1000 * SIZE / 0.65 if (c.get("hit") == "fill" and not c.get("blocked")) else 0.0
            key = (x["mint"], dm["slot"], dm["idx"], dm.get("j", 0))
            repv = (float(np.mean(rep[key])) * SIZE / 0.65) if key in rep else None
            hs = x.get("holders") or []
            g = {k: v for k, v in f.items() if k not in SKIPF}
            g.update(age=dm.get("age_slots"), pct=dm.get("pct"), wsol=(dm.get("sol") or 0) / 1e9, drop=dm.get("drop_pct"), n_hold6=len(hs),
                     hold_sum=sum(h["pct"] for h in hs), hold_max=max((h["pct"] for h in hs), default=0.0))
            rows.append(dict(src="obs", run=run, v=paper, rep=repv, filled=paper != 0.0, hour=(run, int((dm["t"] - t0) // 3.6e12)), f=g, mint=x["mint"], dump=dm))
    for r in allrows:
        if r["run"] != R38 or r["kind"] != "rearm": continue
        x = r["x"]; hs = x.get("holders") or []; dm = x.get("dump") or {}
        g = dict(r["f"]); g.update(drop=dm.get("drop_pct"), n_hold6=len(hs), hold_sum=sum(h["pct"] for h in hs), hold_max=max((h["pct"] for h in hs), default=0.0))
        rows.append(dict(src="live", run="r38live", v=r["v"], rep=None, filled=r["filled"], hour=("r38live", r["hour"][1]), f=g, w=r["w"]))
    return rows


def rearm_search(C, L):
    P = Set([r for r in C if r["src"] == "obs" and r["run"] == "r36"])
    Trows = [r for r in C if r["src"] == "obs" and r["run"] == "r37" and r["rep"] is not None]
    T = Set(Trows, vals=[r["rep"] for r in Trows])
    Tp = Set([r for r in C if r["src"] == "obs" and r["run"] == "r37"])
    Lv = [r for r in C if r["src"] == "live"]; Lset = Set(Lv) if Lv else None
    O38 = Set([r for r in C if r["src"] == "obs" and r["run"] == "r38"])
    feats = sorted(set(k for r in P.rows for k in r["f"]))
    print("re-arm PICK r36 windows", len(P.rows), "fills", int(P.filled.sum()), "value %+.3f" % P.v.sum(), "| TEST r37 replay windows", len(T.rows), "value %+.3f" % T.v.sum(),
          "| r37 paper %+.3f" % Tp.v.sum(), "| r38 live", len(Lv), "%+.3f" % sum(r["v"] for r in Lv), "| r38 paper %+.3f" % O38.v.sum(), flush=True)
    chosen, ntried, npass = search_skip(P, feats, "C re-arm skip")
    res = {"tried": ntried, "pass_pick": npass, "pick_windows": len(P.rows), "pick_fills": int(P.filled.sum()), "test_windows": len(T.rows), "rules": []}
    for ru, sc, lose, win, share in chosen:
        mT = mask_of(T.rows, ru); gT = np.where(mT, -T.v, 0.0); scT = T.score(gT)
        mTp = mask_of(Tp.rows, ru); scTp = Tp.score(np.where(mTp, -Tp.v, 0.0))
        m38 = mask_of(Lset.rows, ru) if Lset else np.zeros(0, bool); sc38 = Lset.score(np.where(m38, -Lset.v, 0.0)) if Lset else None
        mO = mask_of(O38.rows, ru); scO = O38.score(np.where(mO, -O38.v, 0.0))
        six = {lab: bool(m) for r, m in zip(Lset.rows, m38) for (rk, w), lab in SIX.items() if r.get("w") == w} if Lset else {}
        verdict = "LEAD" if scT["save"] > 0 else "FAIL"
        if scT["save"] > 0 and scT["ci"][0] > 0 and scT["wo1"] > 0: verdict = "PASS"
        res["rules"].append(dict(rule=ru, verdict=verdict, pick=sc, pick_share=share, test_replay=scT, test_share=float(mT.mean()), test_paper=scTp, r38_live=sc38,
                                 r38_share=float(m38.mean()) if len(m38) else None, r38_paper=scO, six=six))
        L.append(f"C {ru} -> {verdict}\n  PICK r36 paper {fmt(sc)} skip {share:.1%}\n  TEST r37 replay {fmt(scT)} skip {mT.mean():.1%}; r37 paper {scTp['save']:+.3f}\n"
                 f"  r38 live {sc38['save'] if sc38 else 0:+.3f} skip {m38.mean() if len(m38) else 0:.1%}; r38 paper {scO['save']:+.3f}; six {six}")
    return res


if __name__ == "__main__":
    main()
