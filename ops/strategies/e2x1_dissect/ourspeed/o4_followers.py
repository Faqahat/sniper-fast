#!/usr/bin/env python3
"""ourspeed step 4 (MEASURED): real P&L of the 4 follower wallets on E2x1's tokens (tape), their landing delay after his buy,
and the same for the sibling Grozoe. P&L per wallet per day = sum over his mints of (sell SOL x (1-f) - buy SOL x (1+f) - tx fee - tip)
for trades inside [his buy, his close + 60 s] windows; positions still open at the window end are marked at the last curve price."""
import pickle, collections, numpy as np, sys
sys.argv = [sys.argv[0], "0"]
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/ourspeed")
R = "/home/moiz/sniper-data/e2x1_dissect/recon"
Z = pickle.load(open(f"{R}/tape.pkl", "rb"))
L = [l for l in pickle.load(open(f"{R}/lots.pkl", "rb")) if l["day"] in ("D0", "D1")]
import numpy as np
B = np.load("/home/moiz/sniper-data/e2x1_dissect/ourspeed/blocks.npy"); s_lo = int(B["slot"][0]); NB = np.zeros(int(B["slot"][-1]) - s_lo + 2); NB[B["slot"].astype(np.int64) - s_lo] = B["maxi"] + 1.0
clk = lambda s, i: s + min(i / max(NB[s - s_lo], 1), 0.999999)
users = collections.Counter()
for m, tr in Z["trades"].items():
    for t in tr: users[t[4]] += 1
PRE = ["3iawEZ", "Hj4uAC", "FiYZPb", "AZ45pU", "Grozoe"]
full = {p: [u for u in users if u.startswith(p)] for p in PRE}
print(full)
W = {p: full[p][0] for p in PRE if full[p]}
fee = {}
for l in L: fee[l["mint"]] = (l["fbps"] + l["cbps"]) / 1e4
bym = collections.defaultdict(list)
for l in L: bym[l["mint"]].append(l)
out = []
def P(s=""): print(s); out.append(s)
P("| wallet | day | his lots touched | buys | SOL bought | P&L SOL (all costs, MEASURED) | per buy mSOL | P&L/SOL bought | buy delay after his buy: same slot / median ms (p25-p75) | before him | sells after his sell: median ms |")
P("|---|---|---|---|---|---|---|---|---|---|---|")
for p, w in W.items():
    for day in ("D1", "D0"):
        n_l = 0; nb = 0; sb = 0.0; pnl = 0.0; dl = []; before = 0; same = 0; sdl = []
        for l in [l for l in L if l["day"] == day]:
            m = l["mint"]; f = fee.get(m, 0.0125)
            t_end = (l["close_bt"] or l["bt"]) + 60
            tr = [t for t in Z["trades"][m] if t[16] and t[4] == w and l["bt"] - 2 <= t[3] <= t_end]
            # attribute only trades not already attributed to an earlier lot of the same mint (re-entries): require buy after his buy-2s
            if not tr: continue
            tb = [t for t in tr if t[6]]
            if not tb: continue
            n_l += 1
            hb = clk(l["s"], l["i"])
            for t in tb:
                nb += 1; sb += t[7] / 1e9
                d = (clk(t[0], t[1]) - hb) * 212.07
                if d < 0: before += 1
                else: dl.append(d)
                if t[0] == l["s"]: same += 1
            if l["sells"]:
                hs = clk(l["sells"][0][1], l["sells"][0][2])
                for t in tr:
                    if not t[6]:
                        ds = (clk(t[0], t[1]) - hs) * 212.07
                        if ds > -5000: sdl.append(ds)
            bal = 0
            for t in tr:
                c = (t[11] or 0) / 1e9 + (t[14] or 0) / 1e9
                if t[6]: pnl -= t[7] / 1e9 * (1 + f) + c; bal += t[8]
                else: pnl += t[7] / 1e9 * (1 - f) - c; bal -= t[8]
            if bal > 0:  # mark open at last curve price in window
                last = [t for t in Z["trades"][m] if t[16] and t[3] <= t_end][-1]
                V, T = last[9], last[10]; pnl += (V - V * T / (T + bal)) / 1e9 * (1 - f)
        if nb == 0: P(f"| {w[:8]} | {day} | 0 |"); continue
        dl = np.array(dl) if dl else np.array([np.nan])
        P(f"| {w[:8]}… | {day} | {n_l} | {nb} | {sb:.1f} | {pnl:+.2f} | {pnl / nb * 1e3:+.1f} | {pnl / sb:+.1%} | {same / nb:.0%} / {np.nanmedian(dl):.0f} ({np.nanpercentile(dl, 25):.0f}-{np.nanpercentile(dl, 75):.0f}) | {before} | {np.median(sdl) if sdl else float('nan'):.0f} |")
open("/home/moiz/sniper-data/e2x1_dissect/ourspeed/o4_followers.md", "w").write("\n".join(out) + "\n")
