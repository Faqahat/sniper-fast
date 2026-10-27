#!/usr/bin/env python3
# Profit by leader type (owner 10-25 ~01:00 PKT): replay over the recorded days (dipdetect dd1 data, read-only) of today's
# IMIT1 picks and the new detector's Stage A picks, split by the dump slot's leader client (gossip clientId snapshot
# 10-25 00:58 PKT). The replay lands us 35 / 50 ms after the dump on EVERY leader type, so this shows how good the dumps on each
# leader type are, not how well we land there (live landing differs by type).
import sys, json, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd_lib as L
CL = json.load(open(sys.argv[1]))
KIND = lambda c: {"AgaveBam": "bam", "FireBAM": "bam", "JitoLabs": "jito", "HarmonicAgave": "harmonic", "HarmonicFiredancer": "harmonic",
                  "Firedancer": "firedancer", "Frankendancer": "firedancer", "Agave": "agave", "Rakurai": "rakurai"}.get(c, "other")
lb = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/dipshadow/leaders_book.json"))["leaders"].items()}
sc = json.load(open("/home/moiz/sniper/ops/dip/speed/leaders/schedule_cur.json"))
def leader(s):
    if s in lb: return lb[s]
    i = s - sc["start"]
    return sc["ids"][sc["slot_leader"][i]] if 0 <= i < len(sc["slot_leader"]) else None
PRED = np.load(f"{L.OUT}/pred_v3_reg4_nof1.npy")
ORDER = ("R2", "R3", "R1", "R4"); TEST = ("R3", "R1", "R4")
agg = collections.defaultdict(lambda: [0, 0, 0.0])      # (det, lat, kind) -> attempts, fills, pnl
per_day = {}; o = 0
for day in ORDER:
    d = L.load(day); n = len(d["k"]); P = PRED[o:o + n]; o += n
    if day not in TEST: del d; continue
    kinds = np.array([KIND(CL.get(leader(int(s)) or "", "?")) for s in d["s"]])
    env = d["env"]; f1 = d["f1"]
    DET = {"today (IMIT1, 1.3 s / SL 10%)": (env & np.isfinite(f1) & (f1 >= L.THR["top4"]), L.EXI["c6_tpnone_sl10"]),
           "new detector Stage A (0.85 s)": (env & (P >= 0.010), L.EXI["c4_tpnone_slnone"])}
    for det, (sel, e) in DET.items():
        for latx, lat in ((0, 35), (1, 50)):
            r = L.sim(d, sel, latx, e, detail=True)
            for (row, sv, p, filled) in r["rows"]:
                a = agg[(det, lat, kinds[row])]; a[0] += 1; a[1] += filled; a[2] += p
                b = agg[(det, lat, "ALL")]; b[0] += 1; b[1] += filled; b[2] += p
    print(f"{day}: rows {n}, leader kinds of in-envelope dumps: {dict(collections.Counter(kinds[env]).most_common())}", flush=True)
    del d
print("\nPooled test days R3 + R1 + R4 (~39 h, both servers' near leaders), SOL after all costs:")
for det in ("today (IMIT1, 1.3 s / SL 10%)", "new detector Stage A (0.85 s)"):
    print(f"\n### {det}")
    print(f"  {'leader type':<12} | {'35 ms: tries  fills  SOL     per fill':<40} | {'50 ms: tries  fills  SOL     per fill':<40}")
    for k in ("harmonic", "bam", "jito", "firedancer", "agave", "rakurai", "other", "ALL"):
        cells = []
        for lat in (35, 50):
            a = agg.get((det, lat, k))
            if not a: cells.append(f"{'-':<40}"); continue
            cells.append(f"{a[0]:>11d} {a[1]:>6d} {a[2]:+7.2f} {a[2] / max(1, a[1]):+9.4f}{'':<4}")
        print(f"  {k:<12} | " + " | ".join(cells))
