#!/usr/bin/env python3
# Stage A model choice for the engine port (agent 10-25 ~00:45 PKT, owner GO). Read-only on the study data.
# Stage A = today's envelope (d["env"]) + "model predicted value >= threshold" instead of the IMIT1 gate, exit c4_tpnone_slnone
# (sell lands 4 slots after the entry slot, 75 ms into the slot), engine replay dd_lib.sim, FRA + AMS near leaders.
#  1. row alignment of pred_v3_reg4_top25.npy / pred_v3_reg4_nof1.npy: predictions recomputed from the model JSONs
#  2. the top25 threshold is chosen on R2-val ONLY: (a) match the full model's in-envelope pick count at 0.010, (b) sweep
#  3. Stage A top25 / full, baseline IMIT1 top4 (c4 and c6_tpnone_sl10) on R2-val, R3, R1, R4 at 35 / 50 / 75 ms
#  4. per PKT hour: dumps, in-envelope dumps, Stage A attempts and replay SOL (35 / 50 ms)
# -> dd15_stageA.txt / .json in the data folder.  usage: python3 dd15_stageA.py
import json, sys
import numpy as np
import dd_lib as L
import dd_gbdt as GT
DAYS = ("R2", "R3", "R1", "R4")
OUT = L.OUT
E4 = L.EXI["c4_tpnone_slnone"]; E6 = L.EXI["c6_tpnone_sl10"]
LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.append(s)

def preds(name, D):
    P = np.load(f"{OUT}/pred_{name}.npy"); out = {}; o = 0
    for day in DAYS:
        n = len(D[day]["k"]); out[day] = P[o:o + n]; o += n
    assert o == len(P), f"{name}: {o} rows used of {len(P)}"
    return out

def recompute(name, D):
    m = json.load(open(f"{OUT}/model_{name}.json"))
    assert [L.FN[c] for c in m["cols"]] == m["fn"], "cols / fn mismatch"
    E = [np.array(e, dtype=np.float64) for e in m["edges"]]
    out = {}
    for day in DAYS:
        B = GT.binize(D[day]["Xall"][:, m["cols"]], E)
        out[day] = np.mean([GT.predict(mm, B) for mm in m["models"]], 0)
    return out, m

def cell(o, h):
    return f"{o['pnl']:+6.2f} ({o['pnl'] / h * 24:+6.2f}/24h) {o['fill']:4d}/{o['att']:4d} {100 * o['fill_rate']:3.0f}% {o['per_fill']:+.4f}/fill"

if __name__ == "__main__":
    D = {day: L.load(day) for day in DAYS}
    cut = np.quantile(D["R2"]["t"], 0.70)
    WINM = {day: (D[day]["t"] >= cut) if day == "R2" else np.ones(len(D[day]["t"]), bool) for day in DAYS}
    HRS = {day: L.hours(D[day]) * (0.3 if day == "R2" else 1.0) for day in DAYS}
    res = {"cut_R2val": float(cut)}
    # ---- 1. alignment
    PT = preds("v3_reg4_top25", D); PA = preds("v3_reg4_nof1", D)
    for name, P in (("v3_reg4_top25", PT), ("v3_reg4_nof1", PA)):
        R, m = recompute(name, D)
        diffs = {day: float(np.max(np.abs(R[day] - P[day]))) for day in DAYS}
        say(f"alignment {name}: rows {sum(len(P[d]) for d in DAYS)}, max |recomputed - npy| per day {diffs}")
        res[f"align_{name}"] = diffs
        assert max(diffs.values()) < 1e-12, "pred rows do not align"
    # ---- 2. threshold for top25 on R2-val only
    d2 = D["R2"]; val = WINM["R2"]; ev = d2["env"] & val
    n_full = int(((PA["R2"] >= 0.010) & ev).sum())
    srt = np.sort(PT["R2"][ev])[::-1]
    thr_rm = float(srt[n_full - 1])
    say(f"\nR2-val: {int(val.sum())} dumps, {int(ev.sum())} in the envelope; full model >= 0.010 picks {n_full} ({100 * n_full / ev.sum():.1f}%)")
    say(f"  top25 rate-matched threshold = {thr_rm:.6f} (picks {int(((PT['R2'] >= thr_rm) & ev).sum())})")
    say("  R2-val sweep (in-envelope picks, SOL at 35 / 50 / 75 ms, FRA+AMS, c4):")
    sweep = []
    for nm, P in (("top25", PT), ("full", PA)):
        for thr in [round(x, 4) for x in np.arange(-0.004, 0.0241, 0.002)] + ([thr_rm] if nm == "top25" else []):
            sel = (P["R2"] >= thr) & ev
            o = [L.sim(d2, sel, li, E4) for li in range(3)]
            sweep.append((nm, thr, int(sel.sum()), [round(x["pnl"], 3) for x in o]))
            say(f"    {nm:5s} thr {thr:+.4f}{' (rate-matched)' if nm == 'top25' and thr == thr_rm else '':15s} picks {int(sel.sum()):4d}  "
                + "  ".join(f"{lat}ms {x['pnl']:+6.2f} ({x['fill']}/{x['att']})" for lat, x in zip((35, 50, 75), o)))
    res["sweep_R2val"] = sweep
    best = max([s for s in sweep if s[0] == "top25" and s[1] != thr_rm], key=lambda s: s[3][0] + s[3][1])
    say(f"  top25 sweep best on R2-val (35 + 50 ms): thr {best[1]:+.4f} picks {best[2]} SOL {best[3]}")
    THR25 = thr_rm
    say(f"  CHOSEN top25 threshold (rate match, fixed before looking at any test day): {THR25:.6f}")
    res["thr_top25"] = THR25; res["thr_top25_sweep_best"] = best[1]
    # ---- 3. Stage A tables
    DET = [("BASE IMIT1 top4, c6_tpnone_sl10 (live exit)", lambda day, d: np.isfinite(d["f1"]) & (d["f1"] >= L.THR["top4"]), E6),
           ("BASE IMIT1 top4, c4_tpnone_slnone", lambda day, d: np.isfinite(d["f1"]) & (d["f1"] >= L.THR["top4"]), E4),
           ("BASE IMIT1 top4 & env, c4_tpnone_slnone", lambda day, d: np.isfinite(d["f1"]) & (d["f1"] >= L.THR["top4"]) & d["env"], E4),
           ("STAGE A full v3_reg4_nof1 >= 0.010, c4", lambda day, d: (PA[day] >= 0.010) & d["env"], E4),
           (f"STAGE A top25 >= {THR25:.4f} (R2-val rate match), c4", lambda day, d: (PT[day] >= THR25) & d["env"], E4),
           (f"STAGE A top25 >= {best[1]:.4f} (R2-val sweep best), c4", lambda day, d: (PT[day] >= best[1]) & d["env"], E4),
           (f"GATE as built: top25 >= {THR25:.4f}, dev-list tokens IMIT1 top4, c4", lambda day, d: np.where(L.feat(d, "dev_tok") > 0,
                np.isfinite(d["f1"]) & (d["f1"] >= L.THR["top4"]), (PT[day] >= THR25) & d["env"]), E4)]
    tab = {}
    for nm, mk, e in DET:
        say(f"\n### {nm}")
        for day in DAYS:
            d = D[day]; sel = mk(day, d) & WINM[day]; h = HRS[day]
            cells = []
            for li, lat in enumerate((35, 50, 75)):
                o = L.sim(d, sel, li, e); tab[f"{nm}|{day}|{lat}"] = [o["pnl"], o["fill"], o["att"], o["per_fill"], h]
                cells.append(f"{lat}ms {cell(o, h)}")
            say(f"  {day + ('val' if day == 'R2' else ''):5s} {h:4.1f}h: " + " | ".join(cells))
    res["table"] = tab
    for day in DAYS:
        d = D[day]; w = WINM[day]; dv = L.feat(d, "dev_tok") > 0
        say(f"  {day}: dev-list token dumps in window {int((dv & w).sum())}, in envelope {int((dv & w & d['env']).sum())}, top25 picks among them "
            f"{int((dv & w & d['env'] & (PT[day] >= THR25)).sum())}, IMIT1 top4 picks among them {int((dv & w & np.isfinite(d['f1']) & (d['f1'] >= L.THR['top4'])).sum())}")
    # pooled holdouts + decision rule
    say("\n### pooled (SOL): R3+R4 (clean holdouts) | R3+R1+R4 (all test days)")
    for nm, _, _ in DET:
        a = [sum(tab[f"{nm}|{day}|{lat}"][0] for day in ("R3", "R4")) for lat in (35, 50, 75)]
        b = [sum(tab[f"{nm}|{day}|{lat}"][0] for day in ("R3", "R1", "R4")) for lat in (35, 50, 75)]
        say(f"  {nm:52s} R3+R4 {a[0]:+6.2f} / {a[1]:+6.2f} / {a[2]:+6.2f} | R3+R1+R4 {b[0]:+6.2f} / {b[1]:+6.2f} / {b[2]:+6.2f}")
    full = DET[3][0]; t25 = DET[4][0]
    for lat in (35, 50):
        f_ = sum(tab[f"{full}|{day}|{lat}"][0] for day in ("R3", "R4")); t_ = sum(tab[f"{t25}|{day}|{lat}"][0] for day in ("R3", "R4"))
        say(f"  decision rule {lat} ms (R3+R4): top25 / full = {t_:+.2f} / {f_:+.2f} = {t_ / f_:.2f} (port top25 if >= 0.85)")
    # ---- 4. per PKT hour (holdouts R1 + R3 + R4 for SOL; dumps over all 4 days)
    cov = np.zeros(24); covo = np.zeros(24)
    for day in DAYS:
        a, b = L.WIN[day]; t0, t1 = L.pk(a), L.pk(b)
        if day == "R2": t0 = int(cut)
        for t in range(t0, t1, 60):
            hh = ((t + 5 * 3600) // 3600) % 24; cov[hh] += 1 / 60
            if day != "R2": covo[hh] += 1 / 60
    dumps = np.zeros(24); envn = np.zeros(24); att = np.zeros((24,)); sol = np.zeros((24, 2)); base = np.zeros((24, 2)); atto = np.zeros(24)
    for day in DAYS:
        d = D[day]; w = WINM[day]
        np.add.at(dumps, d["hour"][w], 1); np.add.at(envn, d["hour"][w & d["env"]], 1)
        if day == "R2": continue
        sel = (PT[day] >= THR25) & d["env"]; bs = np.isfinite(d["f1"]) & (d["f1"] >= L.THR["top4"])
        for li in range(2):
            o = L.sim(d, sel, li, E4, detail=True); ob = L.sim(d, bs, li, E6, detail=True)
            for r, sv, p, fl in o["rows"]:
                sol[d["hour"][r], li] += p
                if li == 0: atto[d["hour"][r]] += 1
            for r, sv, p, fl in ob["rows"]: base[d["hour"][r], li] += p
    say("\n### per PKT hour: dumps (>=2% universe) and in-envelope dumps per hour over R2-val+R3+R1+R4; Stage A top25 attempts/h and replay SOL/h"
        " at 35 / 50 ms over the holdouts R3+R1+R4 (FRA+AMS); baseline (IMIT1 top4, live exit c6_sl10) SOL/h alongside")
    say("  hour  cov_h(all/test)  dumps/h  env/h  A_att/h  A_SOL/h@35  A_SOL/h@50 | base@35  base@50")
    hr = []
    for hh in range(24):
        if cov[hh] == 0: continue
        r = dict(h=hh, cov=cov[hh], covo=covo[hh], dumps=dumps[hh] / cov[hh], env=envn[hh] / cov[hh], att=atto[hh] / max(covo[hh], 1e-9),
                 a35=sol[hh, 0] / max(covo[hh], 1e-9), a50=sol[hh, 1] / max(covo[hh], 1e-9), b35=base[hh, 0] / max(covo[hh], 1e-9), b50=base[hh, 1] / max(covo[hh], 1e-9))
        hr.append(r)
        say(f"  {hh:02d}h  {cov[hh]:5.1f}/{covo[hh]:4.1f}      {r['dumps']:7.0f}  {r['env']:5.0f}  {r['att']:7.1f}  {r['a35']:+10.3f}  {r['a50']:+10.3f} | {r['b35']:+7.3f}  {r['b50']:+7.3f}")
    # best 2- and 3-hour windows (SOL/h at 35 + 50 ms, holdout hours only; needs >= 2 h of test coverage per hour)
    def score(ws):
        return sum(next(x for x in hr if x["h"] == h)["a35"] + next(x for x in hr if x["h"] == h)["a50"] for h in ws)
    ok = {x["h"] for x in hr if x["covo"] >= 0.95}          # >= ~1 h of holdout data in that hour
    for w in (2, 3):
        cands = [tuple((s + i) % 24 for i in range(w)) for s in range(24) if all(((s + i) % 24) in ok for i in range(w))]
        cands.sort(key=lambda ws: -score(ws))
        say(f"  best {w}-hour windows (sum of SOL/h at 35 + 50 ms, hours with >= 1 h of holdout data): " + "; ".join(
            f"{ws[0]:02d}-{(ws[-1] + 1) % 24:02d} PKT {score(ws):+.2f} (holdout h {sum(next(x for x in hr if x['h'] == h)['covo'] for h in ws):.1f})" for ws in cands[:5]))
    res["hours"] = hr
    open(f"{OUT}/dd15_stageA.txt", "w").write("\n".join(LOG) + "\n")
    json.dump(res, open(f"{OUT}/dd15_stageA.json", "w"))
