#!/usr/bin/env python3
# DF7e replay step 7: tables for the selective rules (SEL-A/B) and copying his buys. Read-only.
import numpy as np, json
import r4_report as R4
HIS = R4.HIS; HS0, HS1 = R4.HS0, R4.HS1; HMID = (HS0 + HS1) // 2
P = {"before his life (10-23 19:26 → 10-24 15:52, he is absent)": (R4.S0, HS0 - 1), "his 1st half (rules fit here)": (HS0, HMID),
     "his 2nd half (test)": (HMID + 1, HS1), "all 48 h": (R4.S0, R4.S1)}
C3, C1 = R4.COST["our 3.8"], R4.COST["his 1.65"]
for ck, desc in (("A", "SEL-A (his take 12%)"), ("B", "SEL-B (take >= 3.5%)")):
    for mo in (1, 3, 99):
        print(f"\n### {desc}, max {mo if mo < 99 else 'unlimited'} open, 0.5 SOL, +5% guard, cut 20%: SOL/day raw (corrected −5.3/fire)")
        print("| period | landing | our 3.8 | his 1.65 | mSOL/fire pre-cost | fills/day | fill | win (our 3.8) |\n|---|---|---|---|---|---|---|---|")
        for pn, (a, b) in P.items():
            h = R4.hours(a, b); sel = lambda r, a=a, b=b: (r[:, 8] >= a) & (r[:, 8] <= b)
            for land in ("ours", "ours-25ms", "ours-35ms"):
                runs = R4.load(f"sel{ck}_{land}_m{mo}")
                x = R4.agg(runs, *C3, 0.2, sel=sel, hrs=h); xc = R4.agg(runs, *C3, 0.2, True, sel=sel, hrs=h)
                y = R4.agg(runs, *C1, 0.2, sel=sel, hrs=h); yc = R4.agg(runs, *C1, 0.2, True, sel=sel, hrs=h); pre = R4.agg(runs, 0, 0, 0, sel=sel, hrs=h)
                print(f"| {pn} | {land} | {x['day']:+.2f} ({xc['day']:+.2f}) | {y['day']:+.2f} ({yc['day']:+.2f}) | {pre['per_fire']:+.2f} | {x['fills_day']:.0f} | {x['fill']:.0%} | {x['win']:.0%} |")
            runs = R4.load(f"nullsel{ck}_ours_m{mo}")
            x = R4.agg(runs, *C3, 0.2, sel=sel, hrs=h); y = R4.agg(runs, *C1, 0.2, sel=sel, hrs=h); pre = R4.agg(runs, 0, 0, 0, sel=sel, hrs=h)
            print(f"| {pn} | NULL (random, same rate) | {x['day']:+.2f} | {y['day']:+.2f} | {pre['per_fire']:+.2f} | {x['fills_day']:.0f} | {x['fill']:.0%} | {x['win']:.0%} |")
print("\n### COPY: buy right after his own landed buy (trigger = his buy on our feed), no limit, 0.5 SOL, +5% guard, cut 20%")
print("| landing | our 3.8 raw (corr) | his 1.65 raw (corr) | mSOL/fire pre-cost | fills/day | fill | win |\n|---|---|---|---|---|---|---|")
h = R4.HHRS
for land in ("ours", "ours-25ms", "ours-35ms"):
    runs = R4.load(f"copy_{land}_m99")
    x = R4.agg(runs, *C3, 0.2, hrs=h); xc = R4.agg(runs, *C3, 0.2, True, hrs=h); y = R4.agg(runs, *C1, 0.2, hrs=h); yc = R4.agg(runs, *C1, 0.2, True, hrs=h); pre = R4.agg(runs, 0, 0, 0, hrs=h)
    print(f"| {land} | {x['day']:+.2f} ({xc['day']:+.2f}) | {y['day']:+.2f} ({yc['day']:+.2f}) | {pre['per_fire']:+.2f} | {x['fills_day']:.0f} | {x['fill']:.0%} | {x['win']:.0%} |")
    for half, (a, b) in (("1st half", (HS0, HMID)), ("2nd half", (HMID + 1, HS1))):
        sel = lambda r, a=a, b=b: (r[:, 8] >= a) & (r[:, 8] <= b); hh = R4.hours(a, b)
        x = R4.agg(runs, *C3, 0.2, sel=sel, hrs=hh); pre = R4.agg(runs, 0, 0, 0, sel=sel, hrs=hh)
        print(f"|   {land} {half} | {x['day']:+.2f} | | {pre['per_fire']:+.2f} | {x['fills_day']:.0f} | {x['fill']:.0%} | {x['win']:.0%} |")
