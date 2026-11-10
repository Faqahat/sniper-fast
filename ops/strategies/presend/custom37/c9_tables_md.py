#!/usr/bin/env python3
"""CUSTOM37 step 9: the report's markdown tables from knobs.json (each knob alone) and final.json (policies). Out: stdout"""
import json
D = "/home/it/sniper-data/custom37"
K = json.load(open(f"{D}/knobs.json")); F = json.load(open(f"{D}/final.json"))
HTR, HTE = 30.7, 10.8
ROWS = [("Limit depth", ["drop0.08", "drop0.10", "drop0.15", "drop0.18", "drop0.20", "drop0.25"]),
        ("Custom quote (limit = latest x (1 - a x full-dump drop), floor, cap)", ["quote_a0.3_f0.12_c0.18", "quote_a0.5_f0.12_c0.18", "quote_a0.5_f0.10_c0.18", "quote_a0.6_f0.12_c0.18",
                                                                                "quote_a0.7_f0.12_c0.16", "quote_a0.7_f0.12_c0.18", "quote_a0.8_f0.12_c0.16", "quote_a0.8_f0.12_c0.18",
                                                                                "quote_a0.8_f0.12_c0.25", "quote_a0.8_f0.08_c0.18", "quote_a1.0_f0.12_c0.16"]),
        ("Size", ["size0.35", "size0.5", "size0.85", "size1.0"]),
        ("Tries / window / deadline", ["k4", "k12", "win4", "win6", "win15", "dl2", "k12_win15"]),
        ("Exit", ["exit100", "exit300", "exit300s3", "exit500", "exit500s3", "tp_off", "tp10", "tp30", "sl10", "sl15", "sl30", "sl50"]),
        ("Flat extension", ["flat600", "flat1000", "flat2000"]),
        ("QUIET stop", ["q3:2", "q4:2", "q6:2", "q_off"])]
NAMES = {"drop0.08": "drop 0.08", "drop0.10": "drop 0.10", "drop0.15": "drop 0.15", "drop0.18": "drop 0.18", "drop0.20": "drop 0.20", "drop0.25": "drop 0.25",
         "size0.35": "size 0.35", "size0.5": "size 0.50", "size0.85": "size 0.85", "size1.0": "size 1.00", "k4": "k 4", "k12": "k 12", "win4": "window 4", "win6": "window 6",
         "win15": "window 15", "dl2": "deadline +2", "k12_win15": "k 12 + window 15", "exit100": "exit 100 ms", "exit300": "exit 300 ms", "exit300s3": "exit 300 ms, 3-slot backstop",
         "exit500": "exit 500 ms", "exit500s3": "exit 500 ms, 3-slot backstop", "tp_off": "TP off", "tp10": "TP 10%", "tp30": "TP 30%", "sl10": "SL 10%", "sl15": "SL 15%",
         "sl30": "SL 30%", "sl50": "SL 50%", "flat600": "flat ext 0.6 s", "flat1000": "flat ext 1.0 s", "flat2000": "flat ext 2.0 s", "q3:2": "QUIET 3:2", "q4:2": "QUIET 4:2",
         "q6:2": "QUIET 6:2", "q_off": "QUIET stop off"}


def nm(k):
    if k in NAMES: return NAMES[k]
    a, f, c = k.split("_")[1:]
    return f"quote {a[1:]}x, floor {f[1:]}, cap {c[1:]}"


print("| knob | TRAIN dSOL (/day) | TRAIN -20% | TRAIN w/o top 5 | TEST r37 dSOL (/day) | TEST -20% | TEST 90% CI | TEST w/o top 5 | r37 1st / 2nd half | r37 d losers / d winners / d fees | r37 fills +/- | INFERRED share | runs + / - (of 7) |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for sec, ks in ROWS:
    print(f"| **{sec}** | | | | | | | | | | | | |")
    for k in ks:
        if k not in K: continue
        a = K[k]["train"]; b = K[k]["test"]
        npos = sum(1 for v in K[k]["per_run"].values() if v > 0.001); nneg = sum(1 for v in K[k]["per_run"].values() if v < -0.001)
        print(f"| {nm(k)} | {a['dnet']:+.2f} ({a['dnet'] / HTR * 24:+.2f}) | {K[k]['train20']:+.2f} | {a['no_top5']:+.2f} | {b['dnet']:+.2f} ({b['dnet'] / HTE * 24:+.2f}) | {K[k]['test20']:+.2f} | "
              f"[{b['ci'][0]:+.2f}, {b['ci'][1]:+.2f}] | {b['no_top5']:+.2f} | {K[k]['h1']:+.2f} / {K[k]['h2']:+.2f} | {b['dloss']:+.2f} / {b['dwin']:+.2f} / {b['dfees']:+.3f} | "
              f"+{b['added']:.0f} / -{abs(b['lost']):.0f} | {b['infer']:.0%} | {npos} / {nneg} |")
print()
for pname, J in F.items():
    print(f"#### {pname}")
    print("| set | d net SOL | SOL/day @0.696 | 90% CI | w/o top 5 | -20% followers | d losers | d winners | d failed-try fees | fills + / - | INFERRED share |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for lab, a, a20 in (("TRAIN (30.7 h)", J["train"], J["train20"]), ("TEST r37 (10.8 h)", J["test"], J["test20"])):
        print(f"| {lab} | {a['dnet']:+.3f} | {a['day']:+.2f} | [{a['ci'][0]:+.2f}, {a['ci'][1]:+.2f}] | {a['no_top5']:+.3f} | {a20['dnet']:+.3f} | {a['dloss']:+.3f} | {a['dwin']:+.3f} | "
              f"{a['dfee']:+.3f} | +{a['added']:.1f} / -{abs(a['lost']):.1f} | {a['infer']:.0%} |")
    print(f"r37 1st half {J['h1']:+.3f}, 2nd half {J['h2']:+.3f}. Per run: " + ", ".join(f"{r} {v:+.3f}" for r, v in J["per_run"].items()))
    print()
