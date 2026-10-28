#!/usr/bin/env python3
"""SELLID step 4 (read-only): WALK-FORWARD test of 'specific wallets trigger his sells'.
For each test day d (D2..D6), learn on days < d (s2 units: outside trades while a 247/248 lot is open; y = his first sell within
212 ms; E = time x size matched expectation): per wallet (separately for its BUYS and its SELLS) n >= 30 and followed >= 5;
shrunk lift = (Y + 3) / (E + 3); top-N wallets with shrunk lift > 1.
On day d: (a) lift of those wallets' trades = Y / E; (b) share of his first sells with such a trade in the 212 ms before vs the
same share at 10 matched random moments per lot (uniform in [slot buy+2, sell)) -> ratio; (c) precision = P(his sell within 212 ms
| top-N trade while a lot is open).
Out: sellid/s4.txt, s4_lists.json (the learned lists per test day)"""
import pickle, json, collections
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_dissect/sellid"
SMS = 212.0
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)


def main():
    U = dict(np.load(f"{OUT}/s2_units.npz"))
    Z = pickle.load(open(f"{OUT}/s1.pkl", "rb")); LOTS = Z["lots"]
    ids = json.load(open("/home/moiz/sniper-data/dv8/tab/ids.json"))
    y = (U["gap"] <= 212).astype(np.float64)
    strat = ((U["code"] - 247).astype(np.int64) * 2 + U["bu"]) * 100 + U["tb"].astype(np.int64) * 10 + U["sb"]
    _, inv = np.unique(strat, return_inverse=True)
    g = np.random.default_rng(11)
    RM = {}
    for l in LOTS:
        if l["first_sell_k"] is None: continue
        T = l["sell_dcc"]; t0 = 2 * SMS - l["off_in_slot"]
        if T <= t0: continue
        RM[l["id"]] = (T, g.uniform(t0, T, 10))
    LISTS = {}
    P("# Walk-forward: wallet lists learned on earlier days -> his sells on the test day (MEASURED)")
    for side, sname in ((1, "BUYS"), (0, "SELLS")):
        for code in (247, 248, 0):
            P(f"\n## {'both bots' if code == 0 else 'bot ' + str(code)}: wallets' {sname}")
            P("| test day | N | wallets used | test trades | followed | lift (Y/E) | sells with a list trade <=212 ms before | random moments | ratio | precision |")
            P("|---|---|---|---|---|---|---|---|---|---|")
            agg = collections.defaultdict(lambda: np.zeros(6))
            for d in range(2, 7):
                tr = (U["day"] < d) & (U["bu"] == side) & ((U["code"] == code) if code else True)
                te = (U["day"] == d) & (U["bu"] == side) & ((U["code"] == code) if code else True)
                if te.sum() == 0: continue
                # expectation from training strata only (no peeking at the test day)
                trs = (U["day"] < d)
                sm = np.bincount(inv[trs], y[trs], minlength=inv.max() + 1) / np.maximum(np.bincount(inv[trs], minlength=inv.max() + 1), 1)
                E = sm[inv]
                w = U["us"][tr]; uw, iw = np.unique(w, return_inverse=True)
                N = np.bincount(iw); Y = np.bincount(iw, y[tr]); EE = np.bincount(iw, E[tr])
                sh = (Y + 3) / (EE + 3); ok = (N >= 30) & (Y >= 5) & (sh > 1)
                order = np.argsort(-sh * ok)
                for Nn in (10, 25, 50, 100, 200):
                    top = set(uw[order[:Nn]][ok[order[:Nn]]].tolist())
                    LISTS[f"{sname}_{code}_{d}_{Nn}"] = [ids[x] for x in top]
                    mt = te & np.isin(U["us"], list(top))
                    Yt = y[mt].sum(); Et = E[mt].sum()
                    # sells with a list trade in the 212 ms before vs random moments
                    hs = hr = nl = 0
                    for l in LOTS:
                        if l["day"] != d or l["id"] not in RM or (code and l["code"] != code): continue
                        T, rr = RM[l["id"]]
                        msk = np.isin(l["p_us"], list(top)) & (l["p_bu"] == bool(side))
                        dd = l["p_dcc"][msk].astype(np.float64)
                        nl += 1
                        hs += bool(((dd < T) & (dd >= T - 212)).any())
                        hr += np.mean([((dd < t) & (dd >= t - 212)).any() for t in rr])
                    P(f"| D{d} | {Nn} | {len(top)} | {mt.sum():,} | {int(Yt)} | {Yt / max(Et, 1e-9):.2f} | {hs / max(nl, 1):.4f} | {hr / max(nl, 1):.4f} | {hs / max(hr, 1e-9):.2f} | {Yt / max(mt.sum(), 1):.4f} |")
                    agg[Nn] += np.array([mt.sum(), Yt, Et, hs, hr, nl])
            for Nn, a in agg.items():
                P(f"| ALL | {Nn} | | {int(a[0]):,} | {int(a[1])} | {a[1] / max(a[2], 1e-9):.2f} | {a[3] / max(a[5], 1):.4f} | {a[4] / max(a[5], 1):.4f} | {a[3] / max(a[4], 1e-9):.2f} | {a[1] / max(a[0], 1):.4f} |")
    json.dump(LISTS, open(f"{OUT}/s4_lists.json", "w"))
    open(f"{OUT}/s4.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
