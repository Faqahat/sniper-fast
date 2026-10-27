#!/usr/bin/env python3
# DF7e replay step 4: tables from runs/*.npy (mean over Monte-Carlo seeds). Read-only.
import sys, glob, json, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/dip/vm1")
import rlib, core, sim2
R = rlib.DD + "/runs"
S0, S1 = 460476411, 461295954
HOLES = json.load(open(rlib.DD + "/holes.json"))
def hours(a, b):
    n = b - a + 1
    for x, y in HOLES: n -= max(0, min(y, b) - max(x, a) + 1)
    return n * core.SLOT_SEC / 3600
MID = (S0 + S1) // 2
HRS = hours(S0, S1); H1 = hours(S0, MID); H2 = hours(MID + 1, S1)
HIS = json.load(open(rlib.DD + "/his_triggers.json")); HS0 = min(r[3] for r in HIS); HS1 = max(r[3] for r in HIS); HHRS = hours(HS0, HS1)
CN = ["D", "YD", "WU", "BB"]
COST = {"our 3.8": (0.0038, 0.0006), "his 1.65": (0.00138, 0.0010)}
BIAS = {0.2: 0.0053, 0.35: 0.0032, 0.0: 0.0}
def load(name):
    return [np.load(f) for f in sorted(glob.glob(f"{R}/{name}_s*.npy"))]
def agg(runs, C, R_, cut, bias=False, sel=None, hrs=HRS):
    tot = []; fills = []; fires = []; win = []; per = []
    for r in runs:
        if sel is not None: r = r[sel(r)]
        v = sim2.value(r, C, R_, cut, BIAS[cut] if bias else 0.0)
        fl = r[:, 1] == 1
        tot.append(v.sum()); fills.append(fl.sum()); fires.append(len(r)); win.append((v[fl] > 0).mean() if fl.any() else np.nan)
        per.append(v[fl].sum() / max(fl.sum(), 1))
    return dict(day=np.mean(tot) / hrs * 24, sd=np.std(tot) / hrs * 24, fills_day=np.mean(fills) / hrs * 24, fires_day=np.mean(fires) / hrs * 24,
                fill=np.mean(fills) / max(np.mean(fires), 1), win=np.nanmean(win), per_fire=np.mean(tot) / max(np.mean(fires), 1) * 1e3, tot=np.mean(tot))
def line(lbl, a):
    return f"| {lbl} | {a['day']:+.2f} | {a['per_fire']:+.2f} | {a['fills_day']:.0f} | {a['fill']:.0%} | {a['win']:.0%} |"
HDR = "| row | SOL/day | mSOL per fire | fills/day | fill | win |\n|---|---|---|---|---|---|"
out = {}
def main_tables():
    for mo in (1, 3):
        print(f"\n### Max {mo} open, 0.5 SOL, our landing, +5% guard, main exit (raw | corrected = −5.3 / −3.2 mSOL per fire)")
        print("| cost row | cut | SOL/day raw | SOL/day corrected | mSOL/fire raw | fills/day | fill | win (raw) |\n|---|---|---|---|---|---|---|---|")
        runs = load(f"main_ours_g105_m{mo}")
        for cn, (C, R_) in COST.items():
            for cut in (0.2, 0.35):
                a = agg(runs, C, R_, cut); b = agg(runs, C, R_, cut, True)
                print(f"| {cn} | {int(cut*100)}% | {a['day']:+.2f} | {b['day']:+.2f} | {a['per_fire']:+.2f} | {a['fills_day']:.0f} | {a['fill']:.0%} | {a['win']:.0%} |")
                out[f"main_m{mo}_{cn}_{cut}"] = (a["day"], b["day"])
        print(f"\nBy trigger class (max {mo}, cut 20%; raw / corrected SOL/day; mSOL per fire raw)")
        print("| class | fires/day | fill | our 3.8 raw | our 3.8 corr | his 1.65 raw | his 1.65 corr | mSOL/fire (our 3.8, raw) | mSOL/fire pre-cost |\n|---|---|---|---|---|---|---|---|---|")
        for j, c in enumerate(CN):
            sel = lambda r, j=j: r[:, 7] == j
            a = agg(runs, *COST["our 3.8"], 0.2, sel=sel); b = agg(runs, *COST["our 3.8"], 0.2, True, sel=sel)
            a2 = agg(runs, *COST["his 1.65"], 0.2, sel=sel); b2 = agg(runs, *COST["his 1.65"], 0.2, True, sel=sel)
            pre = agg(runs, 0, 0, 0.0, sel=sel)
            print(f"| {c} | {a['fires_day']:.0f} | {a['fill']:.0%} | {a['day']:+.2f} | {b['day']:+.2f} | {a2['day']:+.2f} | {b2['day']:+.2f} | {a['per_fire']:+.2f} | {pre['per_fire']:+.2f} |")
        print(f"\nHalves (max {mo}, cut 20%, raw SOL/day)")
        print("| half | our 3.8 | his 1.65 | fills/day |\n|---|---|---|---|")
        for nm, sel, h in (("1st (10-23 19:26 → 10-24 ~19:35)", lambda r: r[:, 8] <= MID, H1), ("2nd (10-24 ~19:35 → 10-25 19:47)", lambda r: r[:, 8] > MID, H2)):
            a = agg(runs, *COST["our 3.8"], 0.2, sel=sel, hrs=h); a2 = agg(runs, *COST["his 1.65"], 0.2, sel=sel, hrs=h)
            print(f"| {nm} | {a['day']:+.2f} | {a2['day']:+.2f} | {a['fills_day']:.0f} |")
        print(f"\nSpeed, guard, exit, null (max {mo}, cut 20%, raw SOL/day)")
        print("| row | our 3.8 | his 1.65 | mSOL/fire pre-cost | fills/day | fill | win (our 3.8) |\n|---|---|---|---|---|---|---|")
        for nm, jn in (("our landing (median 53 ms)", f"main_ours_g105_m{mo}"), ("25 ms faster", f"main_ours-25ms_g105_m{mo}"), ("35 ms faster", f"main_ours-35ms_g105_m{mo}"),
                       ("his guard −18% (reference only)", f"main_ours_g118_m{mo}"), ("exit: fixed 10 slots", f"exitfixed10_ours_g105_m{mo}"),
                       ("exit: his hold-time draw (timer)", f"exittimer_ours_g105_m{mo}"), ("NULL: random entries, same rate", f"null_ours_g105_m{mo}")):
            runs2 = load(jn)
            a = agg(runs2, *COST["our 3.8"], 0.2); a2 = agg(runs2, *COST["his 1.65"], 0.2); pre = agg(runs2, 0, 0, 0.0)
            print(f"| {nm} | {a['day']:+.2f} | {a2['day']:+.2f} | {pre['per_fire']:+.2f} | {a['fills_day']:.0f} | {a['fill']:.0%} | {a['win']:.0%} |")
            out[f"{jn}"] = (a["day"], a2["day"], pre["per_fire"])
def his_tables():
    print("\n### His exact trigger events (4,951), no position limit, 0.5 SOL, +5% guard, main exit, full tape (he is still ahead of us)")
    print("| landing | our 3.8 cut 20% raw | corrected | his 1.65 raw | mSOL/fire pre-cost | fills/day | fill |\n|---|---|---|---|---|---|---|")
    for nm, jn in (("ours", "histrig_ours_g105_m99"), ("25 ms faster", "histrig_ours-25ms_g105_m99")):
        runs = load(jn); a = agg(runs, *COST["our 3.8"], 0.2, hrs=HHRS); b = agg(runs, *COST["our 3.8"], 0.2, True, hrs=HHRS); a2 = agg(runs, *COST["his 1.65"], 0.2, hrs=HHRS); pre = agg(runs, 0, 0, 0, hrs=HHRS)
        print(f"| {nm} | {a['day']:+.2f} | {b['day']:+.2f} | {a2['day']:+.2f} | {pre['per_fire']:+.2f} | {a['fills_day']:.0f} | {a['fill']:.0%} |")
        for j, c in enumerate(CN):
            sel = lambda r, j=j: r[:, 7] == j
            a = agg(runs, *COST["our 3.8"], 0.2, sel=sel, hrs=HHRS); pre = agg(runs, 0, 0, 0, sel=sel, hrs=HHRS)
            print(f"|   {nm} {c} | {a['day']:+.2f} | | | {pre['per_fire']:+.2f} | {a['fills_day']:.0f} | {a['fill']:.0%} |")
    print(f"\n### Calibration: replay at HIS speed vs his real result (his window {HHRS:.1f} h; tape without his trades; 0.3 SOL; guard −18%; his costs 1.38/fill + 1.0/revert; no follower cut)")
    print("| replay | SOL in window | SOL/day | mSOL per fill | fills/h | fill | win |\n|---|---|---|---|---|---|---|")
    print(f"| HIS REAL (chain) | +25.16 | +22.2 | +5.8 | 159 | 79% | 45% |")
    insel = lambda r: (r[:, 8] >= HS0) & (r[:, 8] <= HS1)
    for nm, jn in (("his triggers, landing ours −16 ms (H2H)", "cal_histrig_ours-16ms_g118_m99"), ("his triggers, his measured delays", "cal_histrig_his_raw_g118_m99"),
                   ("my rules, max 13, ours −16 ms", "cal_rules_ours-16ms_g118_m13"), ("my rules, max 3, ours −16 ms", "cal_rules_ours-16ms_g118_m3"),
                   ("my rules, max 13, his delays", "cal_rules_his_raw_g118_m13")):
        runs = load(jn); a = agg(runs, *COST["his 1.65"], 0.0, sel=insel, hrs=HHRS)
        fl_per = a["tot"] / max(a["fills_day"] * HHRS / 24, 1) * 1e3
        print(f"| {nm} | {a['tot']:+.2f} | {a['day']:+.2f} | {fl_per:+.2f} | {a['fills_day']/24:.0f} | {a['fill']:.0%} | {a['win']:.0%} |")
        out[jn] = a["tot"]
if __name__ == "__main__":
    print(f"hours {HRS:.2f} (halves {H1:.2f} / {H2:.2f}); his window {HHRS:.2f} h")
    main_tables(); his_tables()
    json.dump({k: v for k, v in out.items()}, open(rlib.DD + "/report.json", "w"), default=float)
