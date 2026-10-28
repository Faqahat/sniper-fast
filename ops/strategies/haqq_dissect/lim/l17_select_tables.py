#!/usr/bin/env python3
"""LIM step 17 (read-only): SELECTIVE loosening at our MEASURED landed positions (data/lim/sel_events.pkl).
A policy = (selection S, loosening g): on a dump selected by S, our limit becomes x(1+g) looser (regular: guard 1.05 -> 1+g;
pre-send: min_out / (1+g), only for tries that landed after a crossing of the real limit by that dump); elsewhere the live limit.
Pre-send: first filling try of the window wins (ATA guard). Exits: tm = our timer (regular hold / pre-send 2 slots), wv = wave
RIDE(150,150,700) with MEASURED sell delays. Costs per fill: NOW reg 3.52 / ps 2.01 mSOL, S2 reg 2.03 / ps 0.49 (exec analyst);
failed regular fire 0.53; failed pre-send tries unchanged (not counted). Delta = policy - live limit, same exit / fol / costs.
Selections: ALL; ORACLE (bot 247/248 bought within 2 slots, hindsight); HSEL (analyst H's f10 selector passed for that whale
dump, causal); C_IDE(t) seller's 24 h book-dump mean 2-slot value >= t (>=1 dump); C_CR seller = creator or creation-slot buyer;
C_OR(t) = either. Walk-forward: the C variant / t / g (and g for ORACLE / HSEL) chosen on all earlier days, tested on day D.
Out: data/lim/l17.txt"""
import pickle, sys, collections, itertools
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
COST = {"NOW": {"reg": (3.52e-3, 0.53e-3), "ps": (2.01e-3, 0.0)}, "S2": {"reg": (2.03e-3, 0.53e-3), "ps": (0.49e-3, 0.0)}}
GS = [0.05, 0.10, 0.20, 9.0]
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def SEL(name):
    if name == "ALL": return lambda d: True
    if name == "ORACLE": return lambda d: d["oracle"]
    if name == "HSEL": return lambda d: d["hsel"]
    if name == "C_CR": return lambda d: d["s_cr"] or d["s_cs"]
    kind, t = name.split(":"); t = float(t)
    ide = lambda d: d["wh_n"] >= 1 and d["wh_ide"] == d["wh_ide"] and d["wh_ide"] >= t
    if kind == "C_IDE": return ide
    if kind == "C_OR": return lambda d: ide(d) or d["s_cr"] or d["s_cs"]
    raise ValueError(name)


def net(e, sel, g, ex, fo, cs):
    cf, cx = COST[cs][e["kind"]]
    if e["kind"] == "reg":
        c = e["cands"][0]; lim = (1 + g) if (g is not None and sel(c["dump"])) else 1.05
        return (c["val"][(ex, fo)] - cf, 1) if c["need"] <= lim + 1e-9 else (-cx, 0)
    for c in e["cands"]:
        if c["ok"] or c["need"] <= 1 + 1e-9: return c["val"][(ex, fo)] - cf, 1
        if g is not None and c["crossed"] and sel(c["dump"]) and c["need"] <= 1 + g + 1e-9: return c["val"][(ex, fo)] - cf, 1
    return 0.0, 0


def tot(E, sel, g, ex, fo, cs):
    v = [net(e, sel, g, ex, fo, cs) for e in E]; return sum(x[0] for x in v), sum(x[1] for x in v), np.array([x[0] for x in v])


def boot(d, n=2000, seed=7):
    g = np.random.default_rng(seed); b = [d[g.integers(0, len(d), len(d))].sum() for _ in range(n)]
    return np.percentile(b, 5), np.percentile(b, 95)


def main():
    E = [e for e in pickle.load(open(f"{OUT}/sel_events.pkl", "rb")) if not e["mayhem"]]
    SELS = ["ALL", "ORACLE", "HSEL", "C_CR", "C_IDE:0", "C_IDE:0.01", "C_IDE:0.02", "C_OR:0", "C_OR:0.01", "C_OR:0.02"]
    P("# Selective loosening at our MEASURED landed positions (exact replay; SOL; delta vs the live limit with the same exit/costs)")
    for kind in ("reg", "ps"):
        K = [e for e in E if e["kind"] == kind]; days = sorted({e["day"] for e in K})
        P(f"\n## {kind}: {len(K)} {'fires' if kind == 'reg' else 'windows'}; days {days}")
        for ex in ("tm", "wv"):
            b1, bf, b_1 = tot(K, None, None, ex, 1.0, "NOW")
            b9 = tot(K, None, None, ex, 0.9, "NOW")[0]; bs2 = tot(K, None, None, ex, 1.0, "S2")[0]
            P(f"\n### exit {ex}: LIVE limit = {b1:+.3f} NOW ({bf} fills), fol 0.9 {b9:+.3f}, S2 {bs2:+.3f}; per day NOW: " +
              ", ".join(f"D{d} {tot([e for e in K if e['day'] == d], None, None, ex, 1.0, 'NOW')[0]:+.2f}" for d in days))
            P("| selection | g | extra fills | delta NOW [90%] | per extra fill mSOL | delta fol 0.9 | delta fol 0.8 | delta S2 | delta per day NOW |")
            P("|---|---|---|---|---|---|---|---|---|")
            for sn in SELS:
                s = SEL(sn)
                for g in GS:
                    a, nf, va = tot(K, s, g, ex, 1.0, "NOW"); d = va - b_1
                    if nf == bf: continue
                    lo, hi = boot(d)
                    a9 = tot(K, s, g, ex, 0.9, "NOW")[0] - b9; a8 = tot(K, s, g, ex, 0.8, "NOW")[0] - tot(K, None, None, ex, 0.8, "NOW")[0]
                    a2 = tot(K, s, g, ex, 1.0, "S2")[0] - bs2
                    pd = " ".join(f"D{dd}:{sum(d[i] for i, e in enumerate(K) if e['day'] == dd):+.2f}" for dd in days)
                    P(f"| {sn} | {'none' if g > 1 else f'+{100*g:g}%'} | {nf - bf} | {d.sum():+.3f} [{lo:+.2f}..{hi:+.2f}] | {1000*d.sum()/(nf-bf):+.2f} | {a9:+.3f} | {a8:+.3f} | {a2:+.3f} | {pd} |")
        # walk-forward
        P(f"\n### {kind}: walk-forward (choice on all earlier days by delta NOW fol 1.0 of the same exit; test on day D)")
        P("| exit | family | test day | chosen | test delta NOW | fol 0.9 | S2 |"); P("|---|---|---|---|---|---|---|")
        for ex in ("tm", "wv"):
            for fam, cands in (("ORACLE g", [("ORACLE", g) for g in GS]), ("HSEL g", [("HSEL", g) for g in GS]),
                               ("simple C", [(s, g) for s in SELS[3:] for g in GS] + [("NONE", None)])):
                T = collections.Counter()
                for d in days[1:]:
                    tr = [e for e in K if e["day"] < d]; te = [e for e in K if e["day"] == d]
                    if not tr: continue
                    def score(c):
                        if c[0] == "NONE": return 0.0
                        return tot(tr, SEL(c[0]), c[1], ex, 1.0, "NOW")[0] - tot(tr, None, None, ex, 1.0, "NOW")[0]
                    best = max(cands + [("NONE", None)], key=score)
                    if best[0] == "NONE": dn = d9 = d2 = 0.0
                    else:
                        s = SEL(best[0]); dn = tot(te, s, best[1], ex, 1.0, "NOW")[0] - tot(te, None, None, ex, 1.0, "NOW")[0]
                        d9 = tot(te, s, best[1], ex, 0.9, "NOW")[0] - tot(te, None, None, ex, 0.9, "NOW")[0]
                        d2 = tot(te, s, best[1], ex, 1.0, "S2")[0] - tot(te, None, None, ex, 1.0, "S2")[0]
                    T["n"] += dn; T["9"] += d9; T["2"] += d2
                    P(f"| {ex} | {fam} | D{d} | {best[0]} {'' if best[1] is None else ('none' if best[1] > 1 else f'+{100*best[1]:g}%')} | {dn:+.3f} | {d9:+.3f} | {d2:+.3f} |")
                P(f"| {ex} | {fam} | total | | {T['n']:+.3f} | {T['9']:+.3f} | {T['2']:+.3f} |")
    open(f"{OUT}/l17.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
