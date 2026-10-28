#!/usr/bin/env python3
"""ourspeed step 6: how much of the oracle-pick P&L comes from lots where his own buy landed later than our L after the trigger
(then the same-latency exit also lands BEFORE his sell + his sibling's same-slot sell). Split by his trigger->buy gap g."""
import pickle, numpy as np
R = "/home/moiz/sniper-data/e2x1_dissect/recon"; O = "/home/moiz/sniper-data/e2x1_dissect/ourspeed"
L = {l["lot_id"]: l for l in pickle.load(open(f"{R}/lots.pkl", "rb"))}
S = pickle.load(open(f"{O}/sim_rows.pkl", "rb"))
Z = pickle.load(open(f"{R}/tape.pkl", "rb"))
B = np.load(f"{O}/blocks.npy"); s_lo = int(B["slot"][0]); NB = np.zeros(int(B["slot"][-1]) - s_lo + 2); NB[B["slot"].astype(np.int64) - s_lo] = B["maxi"] + 1.0
clk = lambda s, i: s + min(i / max(NB[s - s_lo], 1), 0.999999)
C, RV = 0.0029, 0.0003; gap = lambda S: max(0.0, -4.4 + 28.1 * S) / 1000
sigloc = {}
need = {L[r["lot_id"]]["trig_sig"] for r in S if L[r["lot_id"]].get("trig_sig")}
prev = {}
for r in S:
    l = L[r["lot_id"]]
    if not l.get("trig_sig"):
        tr = [t for t in Z["trades"][l["mint"]] if t[16] and (t[0], t[1]) < (l["s"], l["i"]) and t[4] not in ("E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb", "Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ")]
        prev[r["lot_id"]] = (tr[-1][0], tr[-1][1]) if tr else None
for m, tr in Z["trades"].items():
    for t in tr:
        if t[15] in need: sigloc[t[15]] = (t[0], t[1])
out = []
def P(s=""): print(s); out.append(s)
P("| day | band | his trigger->buy gap g | lots | his P&L | A-his @66 raw | A2-his @66 raw | A2-his @66 calibrated | B-copy @66 raw |")
P("|---|---|---|---|---|---|---|---|---|")
for day in ("D1", "D0"):
    for b in ("FRESH", "MINUTE", "OLD", "ALL"):
        groups = {"g<66 ms (we land after him)": [], "g>=66 ms (we can land before him)": []}
        for r in S:
            if r["day"] != day or (b != "ALL" and r["bot"] != b): continue
            l = L[r["lot_id"]]
            loc = sigloc.get(l.get("trig_sig")) if l.get("trig_sig") else prev.get(r["lot_id"])
            if loc is None: continue
            g = (clk(l["s"], l["i"]) - clk(*loc)) * 212.07
            groups["g<66 ms (we land after him)" if g < 66 else "g>=66 ms (we can land before him)"].append(r)
        for gname, rows in groups.items():
            def tot(tag, cal=False):
                s = 0.0
                for r in rows:
                    v = r.get(tag)
                    if v is None: continue
                    s += v[1] - C * v[0] - RV * (1 - v[0]) - (gap(r["S"]) if cal else 0)
                return s
            P(f"| {day} | {b} | {gname} | {len(rows)} | {sum(r['his_pnl'] for r in rows):+.2f} | {tot('A|his|66|0.0|fast'):+.2f} | {tot('A2|his|66|0.0|fast'):+.2f} | {tot('A2|his|66|0.0|fast', True):+.2f} | {tot('B|copy|66|0.0|fast'):+.2f} |")
open(f"{O}/o6_split.md", "w").write("\n".join(out) + "\n")
