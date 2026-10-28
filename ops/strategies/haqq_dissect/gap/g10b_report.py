#!/usr/bin/env python3
"""GAP step 10b (read-only): tables from g10_res.pkl. All P&L INFERRED (replay); his net MEASURED.
Per event: expected curve P&L = mean over landing draws of fill x P&L(exit policy, followers).
  reg landing: raw; calibrated = 0.61 x curve - 1.17 mSOL per fire (dv8 c2, fitted on our live regular fires with timer exits;
               applying it to wave exits is an assumption); costs NOW 1.75+1.77 mSOL per fill, 0.53 per failed fire; CHEAP 0.33+0.33 / 0.04
  ps landing:  x 0.45 (MEASURED fill rate of armed windows where the whale sold), costs: 2.51 mSOL per fill (MEASURED pre-send fill
               episode incl. tries) and 0.198 mSOL per unfilled armed window (MEASURED); CHEAP: 0.66 per fill + same tries.
               No calibration (pre-send fills land at MEASURED positions, which g10 draws from); arming beyond one window not costed.
Walk-forward: policy for test day D = best calibrated-NOW total over ALL events of days < D (reg landing, full followers).
Out: gap/g10_tables.txt"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
from g1_walkforward import calib_boot
OUT = "/home/moiz/sniper-data/haqq_dissect/gap"
PSF = 0.45; PS_FILL_NOW = 0.00251; PS_FILL_CHEAP = 0.00066; PS_X = 0.000198
COST = {"NOW": (0.00352, 0.00053), "CHEAP": (0.00066, 0.00004)}
WREG = ("RIDE", 150, 300, 2000); WPS = ("RIDE", 150, 150, 1000)


def main():
    SUF = sys.argv[1] if len(sys.argv) > 1 else ""
    Z = pickle.load(open(f"{OUT}/g10_res{SUF}.pkl", "rb")); meta = Z["meta"]; res = Z["res"]; PL = Z["PL"]; FOLS = Z["FOLS"]
    (A, B), _ = calib_boot()
    ids = [n for n in meta if res.get(n)]
    nP, nF = len(PL), len(FOLS)
    # per event arrays
    regC = np.zeros((len(ids), nF, nP)); regF = np.zeros(len(ids)); psC = np.zeros((len(ids), nF, nP)); psF = np.zeros(len(ids))
    agree = []
    for a, n in enumerate(ids):
        r = res[n]; reg = [x for x in r if x[0] == "reg"]; ps = [x for x in r if x[0] == "ps"]
        for x in reg:
            if x[1]: regC[a] += x[2] / len(reg)
        regF[a] = np.mean([x[1] for x in reg]); psF[a] = np.mean([x[1] for x in ps])
        for x in ps:
            if x[1]: psC[a] += x[2] / len(ps)
        agree += [x[1] == u for x, u in zip(reg, meta[n]["ufill"])]
    day = np.array([meta[n]["day"] for n in ids]); bk = np.array([meta[n]["bucket"] for n in ids]); his = np.array([meta[n]["his"] for n in ids])
    dty = np.array([meta[n]["dtype"] for n in ids]); bal = np.array([meta[n]["bal"] for n in ids])
    def grpb(b):
        if b in ("c:M2 gate score too low", "c:gate (IMIT1) score too low"): return "gate-refused"
        return {"b:ADD": "ADD dumps", "e": "guard-fail (e)", "a": "run gaps", "c:near-only (far leader)": "far leader", "b:DIP_LATE": "DIP_LATE",
                "f": "both filled (f)"}.get(b, "other")
    G = np.array([grpb(b) for b in bk])
    def reg_money(mask, pol, fi=0, cost="NOW", cal=True):
        c = regC[mask, fi, PL.index(pol) if isinstance(pol, tuple) else pol]; f = regF[mask]
        cb, cf = COST[cost]
        g = A * c + B if cal else c
        return float((g - f * cb - (1 - f) * cf).sum())
    def ps_money(mask, pol, fi=0, cost="NOW"):
        c = psC[mask, fi, PL.index(pol)]; f = psF[mask] * PSF
        fc = PS_FILL_NOW if cost == "NOW" else PS_FILL_CHEAP
        return float((PSF * c - f * fc - (1 - f) * PS_X).sum())
    out = []
    def P(*x):
        s = " ".join(str(y) for y in x); print(s); out.append(s)
    days = [d for d in range(0, 6)]
    P(f"# Wave-exit capture replay on HIS dump events: {len(ids):,} events (non-mayhem, usable hours, in the DV8 universe). "
      f"Our fill decision agrees with the DV8 universe's on {100 * np.mean(agree):.1f}% of {len(agree):,} rank draws (consistency check).")
    P(f"Calibration (dv8 c2): live = {A:.2f} x model {1000 * B:+.2f} mSOL/fire. WAVE_REG = {WREG}, WAVE_PS = {WPS}, T5 = current regular timer.")
    # ---- Table 1: exits compared, ALL events and key buckets, reg landing, mean per day
    P("\n## 1. Our REGULAR landing, mean SOL/day over D0-D5 (6 tape days) | D2-D5: exit policies compared (his net MEASURED for reference)")
    P("| events | his net/day | exit | raw full | cal NOW full / 0.9 / 0.8 fol | cal CHEAP full / 0.9 / 0.8 fol |"); P("|---|---|---|---|---|---|")
    groups = [("ALL", np.ones(len(ids), bool))] + [(g, G == g) for g in ("gate-refused", "ADD dumps", "guard-fail (e)", "run gaps", "far leader", "DIP_LATE", "both filled (f)", "other")]
    groups.insert(2, ("gate-refused dev/bundler", (G == "gate-refused") & np.isin(dty, ["dev", "bundler"])))
    for gname, gm in groups:
        for pol in (("T", 5), ("MS", 200), WPS, WREG):
            vals = []
            for D_ in (range(0, 6), range(2, 6)):
                m = gm & np.isin(day, list(D_)); nd = len(list(D_))
                vals.append((reg_money(m, pol, 0, "NOW", False) / nd,
                             [reg_money(m, pol, fi, "NOW") / nd for fi in range(nF)], [reg_money(m, pol, fi, "CHEAP") / nd for fi in range(nF)], his[m].sum() / nd))
            a6, a4 = vals
            P(f"| {gname} | {a6[3]:+.2f} / {a4[3]:+.2f} | {pol} | {a6[0]:+.2f} / {a4[0]:+.2f} | " + " / ".join(f"{v:+.2f}" for v in a6[1]) + " (D2-5: " + " / ".join(f"{v:+.2f}" for v in a4[1]) + ") | "
              + " / ".join(f"{v:+.2f}" for v in a6[2]) + " (D2-5: " + " / ".join(f"{v:+.2f}" for v in a4[2]) + ") |")
    # ---- Table 2: per day, WAVE_REG, buckets
    P("\n## 2. Per day, REGULAR landing + WAVE_REG exit: calibrated NOW | calibrated CHEAP | cal NOW at 0.9 followers (SOL/day; his net in brackets)")
    P("| bucket | " + " | ".join(f"D{d}" for d in days) + " | days > 0 (NOW, full) |"); P("|---|" + "---|" * (len(days) + 1))
    for gname, gm in groups:
        cells = []; pos = 0
        for d in days:
            m = gm & (day == d)
            if not m.any(): cells.append("-"); continue
            a_ = reg_money(m, WREG, 0, "NOW"); b_ = reg_money(m, WREG, 0, "CHEAP"); c_ = reg_money(m, WREG, 1, "NOW"); pos += a_ > 0
            cells.append(f"{a_:+.2f} / {b_:+.2f} / {c_:+.2f} ({his[m].sum():+.1f})")
        P(f"| {gname} | " + " | ".join(cells) + f" | {pos}/{len(days)} |")
    # ---- Table 3: walk-forward exit choice
    P("\n## 3. Walk-forward: exit policy chosen on ALL events of earlier days (reg landing, calibrated NOW, full followers), tested on day D")
    P("| test day | chosen | ALL cal NOW / CHEAP / 0.9 fol / 0.8 fol | gate-refused | gate dev/bundler | ADD dumps | guard-fail (e) | run gaps | far leader | DIP_LATE |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    WF = collections.defaultdict(float)
    for d in range(1, 6):
        tr = day < d; te = day == d
        sc = [reg_money(tr, a, 0, "NOW") for a in range(nP)]; a = int(np.argmax(sc))
        row = [f"{reg_money(te, a, 0, 'NOW'):+.2f} / {reg_money(te, a, 0, 'CHEAP'):+.2f} / {reg_money(te, a, 1, 'NOW'):+.2f} / {reg_money(te, a, 2, 'NOW'):+.2f}"]
        for gname in ("gate-refused", "gate-refused dev/bundler", "ADD dumps", "guard-fail (e)", "run gaps", "far leader", "DIP_LATE"):
            gm = dict(groups)[gname] & te
            v = reg_money(gm, a, 0, "NOW"); WF[gname] += v; row.append(f"{v:+.2f} ({reg_money(gm, a, 0, 'CHEAP'):+.2f})")
        WF["ALL"] += reg_money(te, a, 0, "NOW")
        P(f"| D{d} | {PL[a]} | " + " | ".join(row) + " |")
    P("cells: calibrated NOW (calibrated CHEAP). Walk-forward totals over D1-D5, cal NOW: " + ", ".join(f"{k} {v:+.2f}" for k, v in WF.items()))
    # ---- Table 4: pre-send-style entry on big-holder dumps
    P("\n## 4. PRE-SEND-STYLE entry (land in the dump's slot, MEASURED pre-send positions, x0.45 fill) on his dumps by large holders (dumper held >= 6 % before)")
    P("Per day: net SOL with WAVE_PS exit at NOW costs (full / 0.9 / 0.8 followers) | CHEAP full | his net. Arming beyond one 10-slot window NOT costed.")
    big = bal >= 6
    sets = [("creation-slot buyer (dev/bundler) >= 6%", big & np.isin(dty, ["dev", "bundler"])), ("other >= 6% holder", big & ~np.isin(dty, ["dev", "bundler"])),
            ("  of which gate-refused, dev/bundler >= 6%", big & np.isin(dty, ["dev", "bundler"]) & (G == "gate-refused")),
            ("all his dump events (reference)", np.ones(len(ids), bool))]
    P("| set | " + " | ".join(f"D{d}" for d in days) + " | mean/day | days > 0 (NOW, 0.9 fol) | per event mSOL (NOW full) |"); P("|---|" + "---|" * (len(days) + 3))
    for nm, sm in sets:
        cells = []; vs = []; pos = 0
        for d in days:
            m = sm & (day == d)
            if not m.any(): cells.append("-"); continue
            v = [ps_money(m, WPS, fi, "NOW") for fi in range(nF)]; vs.append(v[0]); pos += v[1] > 0
            cells.append(f"{v[0]:+.2f} / {v[1]:+.2f} / {v[2]:+.2f} / C {ps_money(m, WPS, 0, 'CHEAP'):+.2f} ({his[m].sum():+.1f}, n {m.sum()})")
        tot = ps_money(sm, WPS, 0, "NOW")
        P(f"| {nm} | " + " | ".join(cells) + f" | {np.mean(vs):+.2f} | {pos}/{len(vs)} | {1000 * tot / max(sm.sum(), 1):+.2f} |")
    # pre-send entry with other exits for the big-holder set
    P("\nPre-send-style entry, dev/bundler >= 6 % dumps, mean SOL/day D0-D5 by exit (NOW costs; full / 0.9 / 0.8 followers):")
    sm = sets[0][1]
    for pol in (("T", 2), ("MS", 200), WPS, WREG, ("RIDE", 200, 300, 2000)):
        P(f"- {pol}: " + " / ".join(f"{ps_money(sm, pol, fi, 'NOW') / 6:+.2f}" for fi in range(nF)))
    # regular landing on the same big-holder set for contrast
    P("Regular landing on the same dev/bundler >= 6 % dumps, WAVE_REG, calibrated NOW mean/day D0-D5: " + " / ".join(f"{reg_money(sm, WREG, fi, 'NOW') / 6:+.2f}" for fi in range(nF)))
    open(f"{OUT}/g10_tables{SUF}.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
