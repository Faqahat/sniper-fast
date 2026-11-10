#!/usr/bin/env python3
"""QUIET4 step 3: does the replay agree with LIVE on r37's armed windows? (before it values the skipped ones)
 (1) real tries (MEASURED): every armed window at the live config with its real tries -> same fills, same P&L (sanity).
 (2) VIRTUAL twins (the mode used for skipped windows; INFERRED): every armed window with its tries / stop / fill removed,
     phantom tries only, REPS worlds:
     (a) alone (no one-position knock-on);
     (b) MIXED: random halves of the armed windows virtual while the other half keeps its real tries, one-position knock-on
         on (run_sim in trigger order) - the setting of a looser rule (skipped windows virtual among real ones).
     Compared with live per window group (QUIET signals, age, hour, wh_fol bin, since_last) so the bias is known per segment.
Out: /home/it/sniper-data/presend_quiet4/calib.json + stdout"""
import sys, json, collections, datetime, numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filter/quiet4")
import q3lib as Q
L = Q.L
REPS = 8


def grp(P):
    q = P.W.get("quiet") or {}; tg = P.W["trig"]
    h = (datetime.datetime.fromtimestamp(P.t_trig / 1e3, datetime.UTC) + datetime.timedelta(hours=5)).hour
    nq3 = sum([q.get("since_last", 0) >= 1, q.get("coh_hold", 1) == 0, q.get("wh_fol", 99) < 4.0])
    wf = q.get("wh_fol", -1)
    return {"all": "all", "flags3": f"{nq3} of 3 quiet flags", "since": "since>=1" if q.get("since_last", 0) >= 1 else "since=0",
            "coh": "coh=0" if q.get("coh_hold", 1) == 0 else "coh>=1", "fol": ("none" if wf < 0 else "<2.24" if wf < 2.24 else "2.24-4" if wf < 4 else "4-6" if wf < 6 else ">=6"),
            "age": ("2" if tg["age_slots"] == 2 else "3-9" if tg["age_slots"] < 10 else "10-99" if tg["age_slots"] < 100 else "100+"),
            "half": "day 08-20" if 8 <= h < 20 else "night"}


def main():
    X, wins, R = Q.load()
    A = [P for P in wins if P.W["kind"] == "armed"]
    cfg = dict(L.BASE)
    out = {}
    # (1) real tries
    r1 = L.run_sim(A, R, cfg, rep=0)
    lf = sum(1 for P in A if P.fill); sf = sum(1 for P in A if r1[id(P)]["filled"]); same = sum(1 for P in A if r1[id(P)].get("live_try"))
    lv = sum(P.W["v"] for P in A); sv = sum(Q.value(r1[id(P)])[1] for P in A)
    print(f"(1) REAL tries: windows {len(A)} live fills {lf} replay fills {sf} same try {same} | value live {lv:+.4f} replay {sv:+.4f} SOL")
    out["real"] = {"windows": len(A), "live_fills": lf, "fills": sf, "same": same, "live_v": lv, "v": sv}
    # (2a) virtual twins alone
    VA = {id(P): Q.virtualize(P, R) for P in A}
    acc = collections.defaultdict(lambda: np.zeros(6))   # live fills, sim fills, live v, sim v, live fails, sim fails  (per group)
    per = {}
    for P in A:
        V = VA[id(P)]
        f = v = fl = 0.0
        for rep in range(REPS):
            a, b, c = Q.value(Q.alone(V, R, cfg, rep)); f += a / REPS; v += b / REPS; fl += c / REPS
        per[id(P)] = (f, v, fl)
        for k, g in grp(P).items():
            acc[(k, g)] += [1 if P.fill else 0, f, P.W["v"], v, P.W["n_fail"], fl]
    print(f"\n(2a) VIRTUAL twins ALONE ({REPS} worlds each; no one-position knock-on): live vs model per group")
    print("| group | windows | live fills | model fills | live value | model value | model - live | live failed tries | model failed tries |\n|---|---|---|---|---|---|---|---|---|")
    n_by = collections.Counter()
    for P in A:
        for k, g in grp(P).items(): n_by[(k, g)] += 1
    rows2a = []
    for key in sorted(acc, key=lambda x: (x[0] != "all", x[0], x[1])):
        a = acc[key]
        print(f"| {key[0]}: {key[1]} | {n_by[key]} | {a[0]:.0f} | {a[1]:.1f} | {a[2]:+.3f} | {a[3]:+.3f} | {a[3]-a[2]:+.3f} | {a[4]:.0f} | {a[5]:.0f} |")
        rows2a.append({"group": key, "n": n_by[key], "live_f": a[0], "f": a[1], "live_v": a[2], "v": a[3], "live_fail": a[4], "fail": a[5]})
    out["alone"] = rows2a
    # (2b) MIXED halves with knock-on
    rng = np.random.default_rng(5)
    acc2 = collections.defaultdict(lambda: np.zeros(4)); nsp = 0
    lp = L.live_positions(A)
    for sp in range(4):
        mask = rng.random(len(A)) < 0.5
        for half in (0, 1):
            ws = [(VA[id(P)] if (mask[n] == bool(half)) else P) for n, P in enumerate(A)]
            virt = {id(VA[id(P)]): P for n, P in enumerate(A) if mask[n] == bool(half)}
            for rep in range(2):
                o = L.run_sim(ws, R, cfg, rep=rep + 10 * sp, livepos=lp)
                nsp += 1
                for W in ws:
                    if id(W) not in virt: continue
                    P = virt[id(W)]; a, b, c = Q.value(o[id(W)])
                    for k, g in grp(P).items(): acc2[(k, g)] += [1 if P.fill else 0, a, P.W["v"], b]
                # the real half: does its value change when the other half is virtual? (knock-on of virtual fills on real windows)
                rv = sum(Q.value(o[id(W)])[1] for W in ws if id(W) not in virt)
                lv_half = sum(W.W["v"] for W in ws if id(W) not in virt)
                acc2[("real half", "value replay vs live")] += [0, 0, lv_half, rv]
    k = nsp / 2  # each window is virtual in half of the runs: nsp/2 times
    print(f"\n(2b) MIXED: half the armed windows virtual among real ones, knock-on on ({nsp} replays; each window virtual {k:.0f} times; means per pass)")
    print("| group | live fills | model fills | live value | model value | model - live |\n|---|---|---|---|---|---|")
    rows2b = []
    for key in sorted(acc2, key=lambda x: (x[0] != "all", x[0], x[1])):
        a = acc2[key] / k
        print(f"| {key[0]}: {key[1]} | {a[0]:.0f} | {a[1]:.1f} | {a[2]:+.3f} | {a[3]:+.3f} | {a[3]-a[2]:+.3f} |")
        rows2b.append({"group": key, "live_f": a[0], "f": a[1], "live_v": a[2], "v": a[3]})
    out["mixed"] = rows2b
    # per-window error spread (alone): mean abs error and the error of a random 343-window subset (the size of the QUIET-skip set)
    errs = np.array([per[id(P)][1] - P.W["v"] for P in A])
    sub = [np.sum(rng.choice(errs, 343, replace=False)) for _ in range(2000)]
    print(f"\nper-window model - live (alone): mean {errs.mean()*1e3:+.2f} mSOL, sd {errs.std()*1e3:.1f} mSOL; sum over a random 343-window set: "
          f"q05 {np.percentile(sub,5):+.3f} q50 {np.percentile(sub,50):+.3f} q95 {np.percentile(sub,95):+.3f} SOL")
    out["err"] = {"mean_msol": errs.mean() * 1e3, "sd_msol": errs.std() * 1e3, "sub343": [float(np.percentile(sub, q)) for q in (5, 50, 95)]}
    json.dump(out, open(f"{L.D}/calib.json", "w"), default=str)
    # per-window model values of the armed windows (for the bias correction per segment)
    json.dump({f"{P.W['ses']}:{P.W['w']}": per[id(P)] for P in A}, open(f"{L.D}/calib_alone_per.json", "w"))


if __name__ == "__main__":
    main()
