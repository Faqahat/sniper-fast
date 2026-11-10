#!/usr/bin/env python3
"""APEX-FEES step 7: recipe / lane classes vs create-slot position per leader client, at SIMILAR pay.
Class of a landed non-bundle create-slot buy from its tip accounts + priority:
  'jito+astra' (both a Jito-account tip and an Astralane tip in the one tx: the 9pQQc1xy recipe), 'astralane', 'jito', 'helius',
  'nozomi', '0slot', 'node1', 'other-lane' (any other tip lane), 'multi' (2+ lanes, not jito+astra), 'no-tip' (priority only).
Metrics per (class, client): n, pay p50, first-rate in contested slots, and the pairwise win-rate vs opponents paying within
x0.67..x1.5 of the same tot (pay-matched: what the lane / arrival adds at equal money) [M]. Also high CU-price (>=1M uL/CU) split.
Also a value table: S2 A-row (0.4 SOL, h2, 3 mSOL cost) SOL/day split by the max rival pay in the create slot."""
import sys, collections, numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/apex2"); sys.path.insert(0, "/home/it/sniper/ops/strategies/apex2/fees")
import fl
CL = ["AgaveBam", "JitoLabs", "HarmonicAgave", "HarmonicFiredancer", "Firedancer", "FireBAM"]
C, LT = fl.load(); tot = C["prio"] + C["tips"]
def cls(k):
    ls = set(x for x in C["lanes"][k].split("+") if x)
    if not ls: return "no-tip"
    if ls == {"jito", "astralane"}: return "jito+astra"
    if len(ls) > 1: return "multi"
    l = next(iter(ls))
    return l if l in ("astralane", "jito", "helius", "nozomi", "0slot", "node1") else "other-lane"
G = collections.defaultdict(list)
for k in np.flatnonzero((C["role"] == "buy") & (C["so"] == 0) & (C["rank"] >= 0)): G[C["mint"][k]].append(k)
for v in G.values(): v.sort(key=lambda k: C["i"][k])
K = {k: cls(k) for v in G.values() for k in v}
print("[M] class counts (landed non-bundle create-slot buys):", collections.Counter(K.values()).most_common())
ja = [k for k, c in K.items() if c == "jito+astra"]
if ja:
    print("jito+astra txs: jito tip p50 %.4f mSOL, total tip p50 %.3f, prio p50 %.3f mSOL, cupe p50 %.0f, wallets %s" % (
        np.median([C["tips"][k] for k in ja]) / 1e6, np.median([C["tips"][k] for k in ja]) / 1e6, np.median([C["prio"][k] for k in ja]) / 1e6,
        np.median([C["cupe"][k] for k in ja]), collections.Counter(C["user"][k][:8] for k in ja).most_common(6)))
for split in ("class", "class x cu-price"):
    print(f"\n## {split}: client | class | n | tot p50 mSOL | first-rate (contested) | pay-matched pair win-rate (n pairs)")
    for cl in CL:
        S = collections.defaultdict(lambda: [0, [], 0, 0, 0, 0])
        for m, v in G.items():
            if C["client"][v[0]] != cl: continue
            for r, k in enumerate(v):
                c = K[k]
                if split != "class": c = c + (" hiCUP" if C["cupe"][k] >= 1e6 and C["cupsrc"][k] != "cu" else " loCUP")
                s = S[c]; s[0] += 1; s[1].append(tot[k])
                if len(v) >= 2:
                    s[2] += 1; s[3] += r == 0
                    for r2, k2 in enumerate(v):
                        if k2 == k: continue
                        ratio = max(tot[k], 1e4) / max(tot[k2], 1e4)
                        if 0.67 <= ratio <= 1.5: s[4] += 1; s[5] += r < r2
        for c, s in sorted(S.items(), key=lambda kv: -kv[1][0]):
            if s[0] < 30: continue
            print(f"{cl} | {c} | {s[0]} | {np.median(s[1])/1e6:.2f} | {s[3]/max(s[2],1):.0%} (n {s[2]}) | {s[5]/max(s[4],1):.0%} ({s[4]})")
# value by max rival pay
import a2_eval as E
L = E.load(); bt = np.array([r[2] for r in L]); cb, cs_, _, _ = E.costs(L)
sel = E.crep(L, "same")["A"]; U = sel & (bt >= E.UNSEEN)
hrs = sum((min(b, bt.max()) - max(a, bt.min())) / 3600 for nm, a, b in E.WIN if a >= E.UNSEEN and ((bt >= a) & (bt < b)).any()); per = 24 / hrs
pi = E.POS.index("A"); xi = E.EXITS.index("h2")
bins = [-1, -0.1, 1e6, 3e6, 10e6, 30e6, 100e6, 1e12]; agg = collections.defaultdict(lambda: [0, 0.0, 0.0, 0.0])
for i in np.flatnonzero(U):
    oth = [tot[k] for k in G.get(L[i][0], [])]; mx = max(oth) if oth else -0.5
    b = np.searchsorted(bins, mx, side="left")
    for h, j in ((0, 1), (1, 2), (2, 3)):
        v = float(L[i][6][pi, 2, h, xi]); agg[b][j] += (v - 0.003 - cs_) if np.isfinite(v) else -0.0009
    agg[b][0] += 1
print("\n## S2 A-row value (0.4 SOL, h2, 3 mSOL cost; UNSEEN) by the MAX rival pay in the create slot [M]")
print("max rival pay | picks/day | SOL/day phi0 / -20% / -40% | mean mSOL/pick")
nm = {1: "no rival", 2: "<1 mSOL", 3: "1-3", 4: "3-10", 5: "10-30", 6: "30-100", 7: ">100"}
for b in sorted(agg):
    a = agg[b]; print(f"{nm.get(b, b)} | {a[0]*per:.0f} | {a[1]*per:+.2f} / {a[2]*per:+.2f} / {a[3]*per:+.2f} | {a[1]/a[0]*1e3:+.1f}")
