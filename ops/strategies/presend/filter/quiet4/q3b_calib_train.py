#!/usr/bin/env python3
"""QUIET4 step 3b: the virtual (phantom-only) model on the segment it must value. No r37 armed window has all three current QUIET
flags (since_last >= 1, no cohort holder, whale's mean followers < 4.0 or none): r37 skipped them. The earlier QUIET-on runs (old rule:
fol 2.24 AND < 2 follower bots) ARMED many of them (fol 2.24..4, or >= 2 follower bots), with real tries and real P&L. custom37's
pickles of AMS r34 / r35 / r36 and FRA r26 / r27 / r28 (read-only) are replayed here: every window virtual alone and in mixed halves
(knock-on on), compared with live, split by "current QUIET would skip" (Q3) vs not, and by age (min-age 3 check).
Out: /home/moiz/sniper-data/presend_quiet4/calib_train.json + stdout"""
import sys, json, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filter/quiet4")
import q3lib as Q
L = Q.L
REPS = 6
RUNS = ["r34", "r35", "r36", "f26", "f27", "f28"]


def cur_skip(W, fol=4.0):
    q = W.get("quiet") or {}
    if "since_last" not in q: return None
    return q["since_last"] >= 1 and q["coh_hold"] == 0 and (q["wh_dumps"] == 0 or q["wh_fol"] < fol)


def live_v(P, fpa):
    real = (P.live_pnl or 0) / 1e9
    nf = sum(1 for tr in P.tries if tr["land"] is not None and tr["res"] not in ("ok",))
    return real - nf * fpa / 1e9, nf


def main():
    res = {}
    tot = collections.defaultdict(lambda: np.zeros(7))
    for run in RUNS:
        L.D = "/home/moiz/sniper-data/custom37"
        X, wins, R = Q.load(run)
        lc = X["cfg"][-1]["presend_live"]; q = (lc.get("quiet") or {}).get("stop")
        cfg = dict(L.BASE, drop=lc["drop"], size=lc["spend"] / 1e9, k=lc["k"], win=lc["window_slots"], dl=lc["deadline_slots"], exit_ms=lc.get("exit_ms") or 10 ** 9,
                   exit_slots=lc["exit_slots"], tp=lc["tp"], sl=lc["sl"], qstop=tuple(int(v) for v in q.split(":")) if q else None)
        fpa = L.FAIL
        A = [P for P in wins if P.W["trig"].get("age_slots", 99) >= 1]
        V = {id(P): Q.virtualize(P, R) for P in A}
        seg = {id(P): ("Q3 (cur QUIET skips)" if cur_skip(P.W) else "not Q3" if cur_skip(P.W) is False else "no signals") for P in A}
        age = {id(P): ("age1" if P.W["trig"].get("age_slots") == 1 else "age2" if P.W["trig"].get("age_slots") == 2 else "age3+") for P in A}
        acc = collections.defaultdict(lambda: np.zeros(7))   # n, live fills, alone fills, live v, alone v, mixed fills, mixed v
        lp = L.live_positions(A)
        for P in A:
            lv, _ = live_v(P, fpa)
            f = v = 0.0
            for rep in range(REPS):
                a, b, c = Q.value(Q.alone(V[id(P)], R, cfg, rep)); f += a / REPS; v += b / REPS
            for key in (("all",), (seg[id(P)],), (age[id(P)],), (seg[id(P)], age[id(P)])):
                acc[key] += [1, 1 if P.fill else 0, f, lv, v, 0, 0]
        rng = np.random.default_rng(3); npass = 0
        for sp in range(3):
            mask = rng.random(len(A)) < 0.5
            for half in (0, 1):
                ws = [(V[id(P)] if mask[n] == bool(half) else P) for n, P in enumerate(A)]
                virt = {id(V[id(P)]): P for n, P in enumerate(A) if mask[n] == bool(half)}
                o = L.run_sim(ws, R, cfg, rep=sp, livepos=lp); npass += 1
                for Wv in ws:
                    if id(Wv) not in virt: continue
                    P = virt[id(Wv)]; a, b, c = Q.value(o[id(Wv)])
                    for key in (("all",), (seg[id(P)],), (age[id(P)],), (seg[id(P)], age[id(P)])):
                        acc[key][5] += a; acc[key][6] += b
        k = npass / 2
        print(f"== {run}: windows {len(A)} cfg drop {cfg['drop']} size {cfg['size']} k {cfg['k']} stop {cfg['qstop']} exit {cfg['exit_ms']} | run first-try {R.first:.0f} ms, L med {np.median(R.L):.0f}, k_eff {R.k_eff:.2f}")
        print("| segment | windows | live fills | model fills alone / mixed | live value | model alone | model mixed |\n|---|---|---|---|---|---|---|")
        for key in sorted(acc, key=str):
            a = acc[key]
            print(f"| {' / '.join(key)} | {a[0]:.0f} | {a[1]:.0f} | {a[2]:.1f} / {a[5]/k:.1f} | {a[3]:+.3f} | {a[4]:+.3f} | {a[6]/k:+.3f} |")
            tot[(run[0] == "f" and "FRA" or "AMS",) + key] += np.array([a[0], a[1], a[2], a[3], a[4], a[5] / k, a[6] / k])
        res[run] = {" / ".join(k): acc[k].tolist() for k in acc}
    print("\n== TOTAL (AMS r34-r36 | FRA r26-r28)")
    print("| region / segment | windows | live fills | model fills alone / mixed | live value | model alone | model mixed |\n|---|---|---|---|---|---|---|")
    for key in sorted(tot, key=str):
        a = tot[key]
        print(f"| {' / '.join(key)} | {a[0]:.0f} | {a[1]:.0f} | {a[2]:.1f} / {a[5]:.1f} | {a[3]:+.3f} | {a[4]:+.3f} | {a[6]:+.3f} |")
    json.dump({"runs": res, "total": {" / ".join(k): v.tolist() for k, v in tot.items()}}, open("/home/moiz/sniper-data/presend_quiet4/calib_train.json", "w"))


if __name__ == "__main__":
    main()
