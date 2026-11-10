#!/usr/bin/env python3
"""FLATPERFECT step 2 [causal, engine-log only]: arm-record fields + OUR OWN recent outcomes (live positions closed and known before the
trigger time, and shadow row-c paper exits known before it) + same token / whale / creator memory inside the run.
A closed position counts as known at p['known'] (= max(buy + 3 s, last sell landing)); a shadow paper exit at fill t + 2 s.
usage: fp2_own.py EX.pkl [EX.pkl ...] OUT.pkl   (EX = flatsig f2 extract of a run)"""
import sys, pickle, bisect, math, collections
import numpy as np


def cls(p):
    if p < -0.025: return "bigloss"
    if p <= 0: return "flat"
    if p < 0.025: return "small"
    return "win"


def arm_fields(p):
    q, v, f3, a = p.get("quiet") or {}, p.get("v2") or {}, p.get("f3") or {}, p.get("tags") or {}
    hs = p.get("arm_holders") or []
    f = {"is_T2": 1 if p["kind"] == "T2" else 0, "a_pct": p.get("trig_pct"), "a_sol": (p.get("trig_sol") or 0) / 1e9, "a_age": p.get("trig_age"),
         "a_vsol": (p.get("trig_vsol") or 0) / 1e9, "a_nb": p.get("nb"), "a_nb50": p.get("nb50"), "a_crpct": p.get("cr_pct"),
         "a_spend": (p.get("spend") or 0) / 1e9,
         "q_coh_hold": q.get("coh_hold"), "q_wh_dumps": q.get("wh_dumps"), "q_wh_fol": q.get("wh_fol"), "q_since_last": q.get("since_last"),
         "q_fb_n": q.get("fb_n"), "v_n120": v.get("n_120s"), "v_dd120": v.get("maxdd_120s"), "v_ntr60": v.get("n_tr_60s"), "v_ring": v.get("ring_s"),
         "v_high": (1 if v.get("at_120s_high") else 0) if v else None,
         "h_n": len(hs), "h_max": max((h.get("pct", 0) for h in hs), default=None) if hs else None,
         "h_sum": sum(h.get("pct", 0) for h in hs) if hs else None,
         "t_hour": ((p["t0"] / 1e9 + 5 * 3600) % 86400) / 3600}
    return {k: (np.nan if v_ is None else float(v_)) for k, v_ in f.items()}


def run_feats(x):
    pos = sorted(x["pos"], key=lambda p: p["t0"])
    known = sorted((p["known"], p["pnl"], len(p.get("fol") or []), p["kind"], p["mint"], p.get("whale"), p.get("creator")) for p in pos)
    kt = [k[0] for k in known]
    shf = sorted(((s["cfill"][2] or s["t"]) + 2e9, s["c"]) for s in x["sh"] if s["c"] is not None and s.get("cfill"))
    st = [s[0] for s in shf]
    sha = sorted(s["t"] for s in x["sh"])
    start = min([p["t0"] for p in pos] + [t for t in (x.get("starts") or []) if t] or [0])
    out = {}
    for p in pos:
        t = p["t0"]
        f = arm_fields(p)
        j = bisect.bisect_left(kt, t)
        prev = known[:j]
        f["o_run_min"] = (t - start) / 6e10
        f["o_n"] = len(prev)
        for N in (5, 10, 20, 40):
            L = prev[-N:]
            if len(L) >= min(N, 5):
                pn = np.array([z[1] for z in L])
                f[f"o_mean{N}"] = pn.mean(); f[f"o_flat{N}"] = float(np.mean([cls(z) == "flat" for z in pn]))
                f[f"o_win{N}"] = float(np.mean([z >= 0.025 for z in pn])); f[f"o_fol{N}"] = float(np.mean([z[2] for z in L]))
            else:
                for k in ("mean", "flat", "win", "fol"): f[f"o_{k}{N}"] = np.nan
        # time-window versions (last 15 / 60 min)
        for W in (15, 60):
            L = [z for z in prev if z[0] >= t - W * 6e10]
            f[f"o_n_{W}m"] = len(L)
            f[f"o_sum_{W}m"] = sum(z[1] for z in L)
            f[f"o_flat_{W}m"] = float(np.mean([cls(z[1]) == "flat" for z in L])) if L else np.nan
            f[f"o_win_{W}m"] = float(np.mean([z[1] >= 0.025 for z in L])) if L else np.nan
        lw = [z[0] for z in prev if z[1] >= 0.025]
        f["o_lastwin_min"] = (t - lw[-1]) / 6e10 if lw else np.nan
        # same token / whale / creator in this run (closed before t)
        sm = [z for z in prev if z[4] == p["mint"]]
        f["o_tok_n"] = len(sm); f["o_tok_sum"] = sum(z[1] for z in sm) if sm else np.nan
        sw = [z for z in prev if p.get("whale") and z[5] == p.get("whale")]
        f["o_wh_n"] = len(sw); f["o_wh_sum"] = sum(z[1] for z in sw) if sw else np.nan
        sc = [z for z in prev if p.get("creator") and z[6] == p.get("creator")]
        f["o_cr_n"] = len(sc); f["o_cr_sum"] = sum(z[1] for z in sc) if sc else np.nan
        # shadow paper regime
        js = bisect.bisect_left(st, t)
        for N in (10, 30):
            L = [z[1] for z in shf[max(0, js - N):js]]
            f[f"s_mean{N}"] = float(np.mean(L)) if len(L) >= 5 else np.nan
            f[f"s_pos{N}"] = float(np.mean([z > 0.005 for z in L])) if len(L) >= 5 else np.nan
        L = [z[1] for z in shf[:js] if z[0] >= t - 15 * 6e10]
        f["s_n_15m"] = len(L); f["s_mean_15m"] = float(np.mean(L)) if L else np.nan
        f["s_arms_5m"] = bisect.bisect_left(sha, t) - bisect.bisect_left(sha, t - 5 * 6e10)
        out[f'{p["run"]}|{p["mint"]}|{p["pid"]}|{p["kind"]}|{p["w"]}'] = f
    return out


if __name__ == "__main__":
    out = {}
    for fn in sys.argv[1:-1]:
        out.update(run_feats(pickle.load(open(fn, "rb"))))
    pickle.dump(out, open(sys.argv[-1], "wb"))
    print("done", len(out))
