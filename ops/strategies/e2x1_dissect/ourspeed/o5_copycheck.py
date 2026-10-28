#!/usr/bin/env python3
"""ourspeed step 5: live sanity check of the COPY-TRADE sim. For each copier wallet, lots where its FIRST buy lands 0-400 ms after
E2x1's buy (copy-style) -> its real curve P&L per SOL (before its tx costs, MEASURED) vs our sim B-copy per SOL on the same lots at
L = 50/66/90/120 (raw, phi 0, before tx costs; INFERRED model)."""
import pickle, collections, numpy as np
R = "/home/moiz/sniper-data/e2x1_dissect/recon"; O = "/home/moiz/sniper-data/e2x1_dissect/ourspeed"
Z = pickle.load(open(f"{R}/tape.pkl", "rb"))
L = {l["lot_id"]: l for l in pickle.load(open(f"{R}/lots.pkl", "rb")) if l["day"] in ("D0", "D1")}
S = {r["lot_id"]: r for r in pickle.load(open(f"{O}/sim_rows.pkl", "rb"))}
B = np.load(f"{O}/blocks.npy"); s_lo = int(B["slot"][0]); NB = np.zeros(int(B["slot"][-1]) - s_lo + 2); NB[B["slot"].astype(np.int64) - s_lo] = B["maxi"] + 1.0
clk = lambda s, i: s + min(i / max(NB[s - s_lo], 1), 0.999999)
W = {"Hj4uACn8": "Hj4uACn8Jp2QvbMFhkhWWCdHPzC2SEXg7fhpZayYVcyL", "FiYZPbS4": "FiYZPbS4wi7CSEBerzvyHEAzQkT7qj1apB2mZob3R3zj",
     "AZ45pUnD": "AZ45pUnDKayDSsqxASohrqTaAWSLRwwfTzTpdNoqAQSx", "3iawEZGf": "3iawEZGfWF3H7q6HLxHjSfeZHjCvPr8U9xjXpMgtobDN"}
out = []
def P(s=""): print(s); out.append(s)
P("| copier | day | lots copied (first buy 0-400 ms after him) | its median delay ms | its SOL in | its real curve P&L/SOL (before tx costs) | its real P&L incl. tx costs | sim B-copy/SOL @50 | @66 | @90 | @120 | sim @ its delay |")
P("|---|---|---|---|---|---|---|---|---|---|---|---|")
for nm, w in W.items():
    for day in ("D1", "D0"):
        ids = []; dly = []; sin = 0.0; gross = 0.0; net = 0.0
        for lid, l in L.items():
            if l["day"] != day: continue
            m = l["mint"]; f = (l["fbps"] + l["cbps"]) / 1e4; hb = clk(l["s"], l["i"])
            t_end = (l["close_bt"] or l["bt"]) + 60
            tr = [t for t in Z["trades"][m] if t[16] and t[4] == w and (t[0], t[1]) > (l["s"], l["i"]) and t[3] <= t_end]
            if not tr or not tr[0][6]: continue
            d = (clk(tr[0][0], tr[0][1]) - hb) * 212.07
            if not (0 <= d <= 400): continue
            bal = 0; g = 0.0; c = 0.0; si = 0.0
            for t in tr:
                c += (t[11] or 0) / 1e9 + (t[14] or 0) / 1e9
                if t[6]: g -= t[7] / 1e9 * (1 + f); bal += t[8]; si += t[7] / 1e9 * (1 + f)
                else: g += t[7] / 1e9 * (1 - f); bal -= t[8]
            if bal > 0:
                last = [t for t in Z["trades"][m] if t[16] and t[3] <= t_end][-1]; V, T = last[9], last[10]
                g += (V - V * T / (T + bal)) / 1e9 * (1 - f)
            ids.append(lid); dly.append(d); sin += si; gross += g; net += g - c
        if not ids: continue
        def simps(Lm):
            num = den = 0.0
            for lid in ids:
                r = S.get(lid); v = r.get(f"B|copy|{Lm}|0.0|fast") if r else None
                if v is None: continue
                num += v[1]; den += v[0] * r["S"]
            return num / den if den else np.nan
        md = float(np.median(dly)); Lnear = min([35, 50, 66, 90, 120, 150], key=lambda z: abs(z - md))
        P(f"| {nm}… | {day} | {len(ids)} | {md:.0f} | {sin:.1f} | {gross / sin:+.1%} | {net:+.2f} | {simps(50):+.1%} | {simps(66):+.1%} | {simps(90):+.1%} | {simps(120):+.1%} | {simps(Lnear):+.1%} (@{Lnear}) |")
open(f"{O}/o5_copycheck.md", "w").write("\n".join(out) + "\n")
