#!/usr/bin/env python3
"""FOLLOW step 5 (read-only): the walk-forward TEST days with the cap / threshold chosen on the previous day (f4), every variant, the
overlap with today's pre-send (only NEW fills count as added value), bootstrap ranges, feature importance, the haqq aux target, and
the decision log /home/moiz/sniper-data/haqq_dissect/follow/decisions.jsonl (every decision of the base config, all test days).
Base config: k = 4 tries/slot, <= 5 tokens armed at once (Helius 50/s at k = 4 on ~400 ms slots), wave exit, full followers,
calibrated, NOW costs. Variants: model (uncalibrated), S2 costs, followers x0.9 / x0.8, 2-slot exit, k = 8 (<= 2 tokens), no cap.
Out: f5.txt, decisions.jsonl"""
import sys, json, time, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/follow")
import flib as FL
import dv8lib as L
from f4_wf import load, account, boot_mint
OUT = FL.OUT
P_ = []


def P(*x):
    s = " ".join(str(y) for y in x); print(s, flush=True); P_.append(s)


def conc_stats(res):
    """time-weighted share of armed time with >= 2 / 3 / 5 / 8 tokens armed at once, and the max (merged token windows, uncut)"""
    iv = res[3]; ev = []
    for m, L_ in iv.items():
        L_ = sorted(L_); cur = None
        for s0, e0, i, S_ in L_:
            if cur and s0 <= cur[1]: cur[1] = max(cur[1], e0)
            else:
                if cur: ev += [(cur[0], 1), (cur[1], -1)]
                cur = [s0, e0]
        if cur: ev += [(cur[0], 1), (cur[1], -1)]
    ev.sort(); n = 0; last = None; tw = collections.Counter()
    for t, x in ev:
        if last is not None and n > 0: tw[n] += t - last
        n += x; last = t
    tot = sum(tw.values()) or 1
    return {k: sum(v for c, v in tw.items() if c >= k) / tot for k in (2, 3, 5, 8)}, max(tw) if tw else 0


def main():
    t0 = time.time()
    F, meta, names, CAPS, labs, CV, ccr, U, day = load()
    TAG = sys.argv[1] if len(sys.argv) > 1 else "f4"           # f10 = the final selector (value-dependent live fill model)
    Z = pickle.load(open(f"{OUT}/{TAG}.pkl", "rb")); S = np.load(f"{OUT}/{TAG}_scores.npz")
    PFJ = None
    if TAG == "f10":
        from f9_adverse import pf_bucket
        PFJ = pf_bucket(CV)[1]
    R = np.load(f"{OUT}/tape.npy", mmap_mode="r"); X = np.load(f"{OUT}/rowx.npz")
    MI = pickle.load(open(f"{OUT}/mints.pkl", "rb")); info = MI["info"]
    st = {int(m): int(a) for m, a in zip(MI["um"], MI["st"])}; en = {int(m): int(b) for m, b in zip(MI["um"], MI["en"])}
    ids, _ = L.ids_map()
    Xd = {k: X[k] for k in ("bb", "ba", "cc", "px", "ref")}
    bwin = {}

    def in_base(j, m):
        if m not in bwin: bwin[m] = FL.baseline_windows(R, Xd, st[m], en[m], info[m])
        c = ccr[j]
        return any(a < c <= b for a, b in bwin[m])
    keep_new = lambda j, m: not in_base(j, m)
    fi = {n: i for i, n in enumerate(names)}
    rows = []; logs = {}
    P("# FOLLOW test days (walk-forward; INFERRED replay with MEASURED landing, fill thinning and costs). SOL per test day.")
    P("| Day | cap / thr | armed episodes | fills | armed slots | model gross | calibrated NOW [90%] | calibrated S2 | NEW only (cal NOW) | fol 0.9 | fol 0.8 | 2-slot exit | k=8, <=2 tokens | no conc. cap | per fill cal. gross mSOL |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for d in sorted(Z["R"]):
        v0, ci, thr, _ = Z["R"][d]["choice"]
        s = S[f"s{d}"]; te = day == d
        sel = np.flatnonzero(te & (s >= thr))
        base = FL.replay(sel, meta, labs, ci, CV, ccr, U, conc=5, want_log=True, PFJ=PFJ)
        a_mod = account(base, cal=False); a_cal = account(base); a_s2 = account(base, fillc=FL.FILL_S2); a_new = account(base, keep=keep_new)
        bs = boot_mint(base)
        r9 = account(FL.replay(sel, meta, labs, ci, CV, ccr, U, conc=5, fol=1, PFJ=PFJ)); r8 = account(FL.replay(sel, meta, labs, ci, CV, ccr, U, conc=5, fol=2, PFJ=PFJ))
        rt2 = account(FL.replay(sel, meta, labs, ci, CV, ccr, U, conc=5, pol=1, PFJ=PFJ))
        rk8 = account(FL.replay(sel, meta, labs, ci, CV, ccr, U, conc=2, PFJ=PFJ), k=8)
        rnc_r = FL.replay(sel, meta, labs, ci, CV, ccr, U, conc=None, PFJ=PFJ); rnc = account(rnc_r); cst = conc_stats(rnc_r)
        nep = len(base[2]) - len([i for i in base[2].values() if i in base[4]])
        pf = 1000 * a_cal[1] / max(a_cal[2], 1e-9)
        P(f"| D{d} | {CAPS[ci]} / {thr:+.2f} | {nep:,} | {a_cal[2]:.0f} | {a_cal[3]:,.0f} | {a_mod[0]:+.2f} | **{a_cal[0]:+.2f}** [{bs[0]:+.2f}..{bs[1]:+.2f}] | {a_s2[0]:+.2f} | "
          f"{a_new[0]:+.2f} ({a_new[2]:.0f} new fills) | {r9[0]:+.2f} | {r8[0]:+.2f} | {rt2[0]:+.2f} | {rk8[0]:+.2f} | {rnc[0]:+.2f} | {pf:+.1f} |")
        rows.append(dict(d=d, ci=ci, thr=thr, cal=a_cal, mod=a_mod, s2=a_s2, new=a_new, f9=r9, f8=r8, t2=rt2, k8=rk8, nc=rnc, bs=bs))
        logs[d] = (base, sel, ci, thr, s)
        # splits of the base fills by the arming row: whale kind / creation-slot whale / N
        spl = collections.defaultdict(lambda: [0.0, 0])
        for dd in range(len(base[0])):
            for j, v, m, i in base[0][dd]:
                for k_, val in (("kind", "first" if F[i, fi["kind"]] == 0 else "after-sell"), ("cs", "creation-slot whale" if F[i, fi["w_cs"]] else "later whale"),
                                ("N", f"N={int(meta['N'][i])}"), ("new", "new" if keep_new(j, m) else "overlap")):
                    spl[(k_, val)][0] += (FL.CAL_A * v + FL.CAL_B - FL.FILL_NOW) / len(base[0]); spl[(k_, val)][1] += 1 / len(base[0])
        P(f"  D{d} fills by group (calibrated NOW, before arming): " + "; ".join(f"{v_}: {n:.0f} fills {1000 * g / max(n, 1e-9):+.1f} mSOL/fill = {g:+.2f}"
                                                                           for (k_, v_), (g, n) in sorted(spl.items())))
        P(f"  D{d} concurrency without a cap: share of armed time with >=2/3/5/8 tokens armed " + " / ".join(f"{v:.2f}" for v in cst[0].values()) + f", max {cst[1]}")
        n0 = te & (meta["N"] == 0)
        P(f"  D{d} aux: AUC of the score for 'haqq follows the whale's dump' {FL.auc(meta['hqf'][n0], s[n0]):.3f} (base {meta['hqf'][n0].mean():.3f}); "
          f"armed episodes haqq followed {np.mean([meta['hqf'][i] for i in base[2].values()]):.3f} ({time.time() - t0:.0f}s)")
    T = lambda k: sum(r[k][0] for r in rows)
    nd = sum(1 for r in rows if r["d"] <= 5) ; full = [r for r in rows if r["d"] <= 5]
    P(f"\nSum D2..D5 (full days): calibrated NOW {sum(r['cal'][0] for r in full):+.2f} SOL = {sum(r['cal'][0] for r in full) / max(nd, 1):+.2f}/day; "
      f"NEW only {sum(r['new'][0] for r in full) / max(nd, 1):+.2f}/day; fol 0.9 {sum(r['f9'][0] for r in full) / max(nd, 1):+.2f}/day; fol 0.8 {sum(r['f8'][0] for r in full) / max(nd, 1):+.2f}/day; "
      f"S2 {sum(r['s2'][0] for r in full) / max(nd, 1):+.2f}/day; model {sum(r['mod'][0] for r in full) / max(nd, 1):+.2f}/day; days > 0 (cal NOW) {sum(r['cal'][0] > 0 for r in full)}/{nd}")
    # feature importance of the chosen models
    imp = np.zeros(len(names)); k = 0
    for d in sorted(Z["R"]):
        ci = Z["R"][d]["choice"][1]; M = Z["MODELS"][(d, ci)]["M"]; imp += FL.importance(M, len(names)); k += 1
    imp /= max(k, 1)
    P("\nFeature importance (mean gain share over the chosen test-day models): " + ", ".join(f"{names[j]} {100 * imp[j]:.1f}%" for j in np.argsort(-imp)[:15]))
    open(f"{OUT}/f5{'' if TAG == 'f4' else '_' + TAG}.txt", "w").write("\n".join(P_) + "\n")
    pickle.dump(dict(rows=rows, imp=imp, names=names), open(f"{OUT}/f5{'' if TAG == 'f4' else '_' + TAG}.pkl", "wb"))
    # ---------------- the decision log (base config)
    pl = list(CV["PL"]); n_log = 0
    with open(f"{OUT}/decisions.jsonl", "w") as fo:
        def W(r):
            nonlocal n_log; fo.write(json.dumps(r) + "\n"); n_log += 1
        for d, (base, sel, ci, thr, s) in sorted(logs.items()):
            fills, armed, first, iv, dropped, log = base
            cap = int(CAPS[ci]); armed_e = set(first.values())
            te = np.flatnonzero(day == d)
            def dump_info(i):
                r1 = int(meta["r1"][i])
                return (dict(dump_slot=int(R["slot"][r1]), dump_idx=int(R["idx"][r1]), dump_sol=float(R["sol"][r1]) / 1e9) if r1 >= 0 else dict(dump_slot=None, dump_idx=None, dump_sol=None))
            # score: every checkpoint of the day (armed or not)
            for i in te.tolist():
                W(dict(kind="score", config=TAG, day=d, mint=ids[int(meta["m"][i])], whale=ids[int(meta["w"][i])], ep=int(meta["e"][i]), N=int(meta["N"][i]),
                       slot=int(meta["s_c"][i]), cc_ms=round(float(meta["t_c"][i]), 1), score=round(float(s[i]), 4), thr=round(float(thr), 4), pass_=bool(s[i] >= thr),
                       arms=bool(i in armed_e and i not in dropped), **dump_info(i)))
            for e, i in first.items():
                m = int(meta["m"][i]); S_, wend = labs[i][ci]
                rec = dict(day=d, mint=ids[m], whale=ids[int(meta["w"][i])], ep=int(e), N=int(meta["N"][i]), slot=int(meta["s_c"][i]), cc_ms=round(float(meta["t_c"][i]), 1),
                           score=round(float(s[i]), 4), cap_slots=cap, window_end_cc_ms=round(float(wend), 1), **dump_info(i))
                if i in dropped: W(dict(kind="arm_refused_concurrency", **rec)); continue
                W(dict(kind="arm", k_per_slot=4, **rec))
                why = "whale_dump" if abs(wend - meta["d_end"][i]) < 1e-6 else "cap"
                W(dict(kind="disarm", why_planned=why, armed_slots_mean4=round(float(armed[m].mean()), 1), tries_mean4=round(float(armed[m].mean()) * 4, 0), **rec))
            for (_, j, act, ok, m) in log:
                x = int(CV["row"][j]); g = int(CV["grow"][j, 0])
                W(dict(kind="buy_try", day=d, mint=ids[m], cross_slot=int(R["slot"][x]), cross_idx=int(R["idx"][x]), seller=ids[int(R["user"][x])],
                       sell_sol=float(R["sol"][x]) / 1e9, ref_px=float(Xd["ref"][x]) * 1e6, limit_px=0.88 * float(Xd["ref"][x]) * 1e6, cross_px=float(Xd["px"][x]) * 1e6,
                       k_ahead_draw0=int(CV["k"][j, 0]), land_slot=int(R["slot"][g]) if g >= 0 else None, land_after_idx=int(R["idx"][g]) if g >= 0 else None,
                       draw_fills=[bool(b) for b in CV["fill"][j]], thin_u0=round(float(U[j, 0]), 4), fill_prob_draw0=round(float(FL.PF if PFJ is None else PFJ[j, 0]), 3), fill_draw0=bool(ok), armed_eps=[int(meta["e"][a]) for a in act]))
            for dd in range(1):
                for j, v, m, i in fills[dd]:
                    x = int(CV["row"][j]); g = int(CV["grow"][j, dd])
                    base_r = dict(day=d, mint=ids[m], whale_armed=ids[int(meta["w"][i])], ep=int(meta["e"][i]), cross_slot=int(R["slot"][x]), cross_idx=int(R["idx"][x]))
                    W(dict(kind="fill", land_slot=int(R["slot"][g]), land_after_idx=int(R["idx"][g]), entry_px=float(CV["epx"][j, dd]), tokens=float(CV["etok"][j, dd]),
                           sol_in=0.40, new_vs_today=bool(keep_new(j, m)), **base_r))
                    vv = CV["val"][j, dd]
                    W(dict(kind="sell", exit="wave RIDE(150,150,1000)", pnl_model_sol=round(float(vv[0, 0]), 6), pnl_cal_sol=round(FL.CAL_A * float(vv[0, 0]) + FL.CAL_B, 6),
                           pnl_cal_now_net_sol=round(FL.CAL_A * float(vv[0, 0]) + FL.CAL_B - FL.FILL_NOW, 6), pnl_model_fol09=round(float(vv[1, 0]), 6), pnl_model_fol08=round(float(vv[2, 0]), 6),
                           pnl_model_t2=round(float(vv[0, 1]), 6), mean4draws_model=round(float(np.mean([CV['val'][j, q, 0, 0] if CV['fill'][j, q] else 0.0 for q in range(4)])), 6), **base_r))
    P(f"decision log: {n_log:,} lines -> {OUT}/decisions.jsonl ({time.time() - t0:.0f}s)")
    open(f"{OUT}/f5{'' if TAG == 'f4' else '_' + TAG}.txt", "w").write("\n".join(P_) + "\n")


if __name__ == "__main__":
    main()
