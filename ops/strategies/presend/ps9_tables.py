#!/usr/bin/env python3
# Markdown tables for REPORT.md from ps6_select.json, ps7_test.json, ps7b_cross.json, ps8_compare.json, ps3g_costs.json.
import json, os, collections
import ps_common as C
O = C.OUT
best = json.load(open(f"{O}/ps6_select.json"))["best"]
T = json.load(open(f"{O}/ps7_test.json"))
DAYS = ("R2", "R3", "R4", "R1")
QN = {"a": "(a) right after", "b": "(b) +5 ms", "c": "(c) +10 ms", "r20": "20/slot U[0,11) ms", "r4": "4/slot U[0,53) ms", "r1": "1/slot U[0,212) ms"}
def fam_table(fam):
    print(f"\n#### {fam}: each row = the config chosen on R2 for that queue row (cheap fees); SOL per 24 h")
    print("| Queue row (k/slot) | R2 train | R3 | R4 | R1 | fills/24h (R3) | net/fill (R3) | att/fill (R3) | config |")
    print("|---|---|---|---|---|---|---|---|---|")
    for dm in ("a", "b", "c", "r20", "r4", "r1"):
        key = f"{fam}|{dm}"
        if key not in best: continue
        b = best[key]; cells = []
        for day in DAYS:
            r = T.get(f"{key}|{day}", {}).get("cheap-k")
            cells.append(f"{r['per24']:+.2f}" if r else "-")
        r3 = T.get(f"{key}|R3", {}).get("cheap-k", {})
        h3 = 21.0
        cfg = f"y {int(b['y'] * 100)}%, W {b['W']}, {b['size']} SOL, {b['ex']}, {b['filt']}" + (", stop at creator sell" if b.get("end_cre") else "")
        print(f"| {QN[dm]} (k={ {'a': 20, 'b': 20, 'c': 20, 'r20': 20, 'r4': 4, 'r1': 1}[dm] }) | " + " | ".join(cells) +
              f" | {r3.get('fill', 0) / h3 * 24:.0f} | {r3.get('per_fill', 0):+.4f} | {r3.get('att_per_fill', 0):.0f} | {cfg} |")

if __name__ == "__main__":
    for fam in ("T1", "T1t", "T2", "T3"): fam_table(fam)
    if os.path.exists(f"{O}/ps7b_cross.json"):
        X = json.load(open(f"{O}/ps7b_cross.json")); keys = sorted({k.rsplit("|", 2)[0] for k in X})
        print("\n#### Sensitivity: a config chosen under one queue row, replayed under every row (SOL per 24 h)")
        print("| Config (chosen under) | Day | (a) | (b) | (c) | r20 | r4 | r1 |")
        print("|---|---|---|---|---|---|---|---|")
        for key in keys:
            for day in DAYS:
                cells = [f"{X[f'{key}|{dm}|{day}']['per24']:+.2f}" if f"{key}|{dm}|{day}" in X else "-" for dm in ("a", "b", "c", "r20", "r4", "r1")]
                print(f"| {key} | {day} | " + " | ".join(cells) + " |")
    if os.path.exists(f"{O}/ps8_compare.json"):
        P = json.load(open(f"{O}/ps8_compare.json"))
        print("\n#### Reactive bot (IMIT1 top4 in envelope) vs pre-sent, same hours (SOL per window; combined = shared 2 servers)")
        print("| Day | Exit | Latency | Reactive alone | Pre-sent key | Pre-sent alone | Same dump | Combined (react + pre) |")
        print("|---|---|---|---|---|---|---|---|")
        for k, v in P.items():
            if k.startswith("base|"): continue
            key, exn, lat, day = k.rsplit("|", 3)
            cb = v["combined"]
            print(f"| {day} | {exn} | {(35, 50, 75)[int(lat)]} ms | {v['react_alone']:+.2f} | {key} | {v['pre_pnl']:+.2f} | {v['same_dump']}/{v['pre_fills']} | "
                  f"{cb['total']:+.2f} ({cb['react']:+.2f} + {cb['pre']:+.2f}) |")
