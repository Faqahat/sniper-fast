#!/usr/bin/env python3
"""pos step 11 (read-only): CAUSAL post-entry rules -- after we hold a lot, does state known at the 5-slot timer decide 'hold longer'
and/or 'add a 2nd lot' profitably? Exact curve replay (dv8 exact follower model, joint simulation when 2 lots overlap).
Entries:
  LIVE = our 596 real regular fills (dv8 fires_tape.pkl), entry = our real tape position (c1: replay = live +0.02 mSOL/fill);
  OOS  = dv8 g1 walk-forward picks on test days D2-D6 (gate never saw the day), rank-model entries (4 draws, +5% guard).
State at the decision (end of slot entry+5, all public): u5 = our P&L if sold now; follower buy / sell SOL since entry; new >= 5%
outside dumps since entry; haqq bought since entry; drawdown from the high since entry.
Rules: HOLD(x,H) hold to H slots when u5 >= x else sell at 5; ADD(x,H): when u5 >= x (or <= x for 'down') buy a 2nd 0.40 SOL lot
right after the decision (1 trade later) and sell both at H; FLOW(f,H): hold when follower buys >= f SOL.
Out: p11.txt"""
import sys, pickle, json, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import p6_rules as R6
import dv8lib as L
from plib import Out, OUT, day_name
P = Out(f"{OUT}/p11.txt")
SIZE = 0.4; FEE = 0.0125
HS = (5, 8, 12, 20, 30)


def main():
    ids, idm = L.ids_map(); h = idm[L.HAQQ]
    our = [idm[w] for w in L.WAL.values() if w in idm]
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    keep = ~np.isin(np.asarray(T["user"]), our)
    mi = np.asarray(T["mint"])[keep]; o = np.argsort(mi, kind="stable")
    US = np.asarray(T["user"])[keep][o].astype(np.int64); IX = np.asarray(T["idx"])[keep][o].astype(np.int64); MI = mi[o]
    del keep, mi, o
    tape = R6.Tape()
    um, st = np.unique(MI, return_index=True); en = np.append(st[1:], len(MI)); span = {int(a): (int(b), int(c)) for a, b, c in zip(um, st, en)}
    px = tape.vs / np.maximum(tape.vt, 1)
    entries = []        # (set, day, r, es, end)
    F = pickle.load(open(f"{L.D}/fires_tape.pkl", "rb"))
    for f in F:
        if f.get("out") != "fill" or f["mint"] not in idm or not f.get("us"): continue
        a, b = span.get(idm[f["mint"]], (0, 0))
        if b <= a: continue
        key = tape.sl[a:b] * 100000 + IX[a:b]
        r = a + int(np.searchsorted(key, f["us"][0] * 100000 + f["us"][1]))
        if r <= a or r > b: continue
        entries.append(("LIVE", L.day_of(f["t"]), r, int(f["us"][0]), b))
    Z = np.load(f"{L.D}/uni.npz"); M = Z["M"]; FILL = Z["FILL"]; R = Z["R"]; ES = Z["ES"]
    G1 = pickle.load(open(f"{L.D}/g1_picks.pkl", "rb"))
    for D, g in G1.items():
        for i in g["idx"]:
            for c in (2, 3, 4, 5):
                if FILL[i, c]: entries.append(("OOS", int(D), int(R[i, c]), int(ES[i, c]), int(M["end"][i])))
    P(f"# post-entry rules: LIVE entries {sum(e[0] == 'LIVE' for e in entries)}, OOS entries (gate picks x filled rank draws) {sum(e[0] == 'OOS' for e in entries)}")
    rows = []
    for st_, d, r, es, end in entries:
        q = {H: tape.qrow(r, end, es, H) for H in HS}
        pn = {H: tape.joint([(r, q[H])])[0] for H in HS}
        q5 = q[5]; seg = slice(r, q5 + 1)
        bu = tape.bu[seg]; so = tape.so[seg]; us = US[seg]
        pp = np.r_[px[r - 1], px[seg]]
        drop = np.where(~bu, 1 - pp[1:] / pp[:-1], 0)
        st = dict(set=st_, day=d, u5=pn[5], pn=pn, fb=float(so[bu].sum()), fs=float(so[~bu].sum()), nd=int((drop >= 0.05).sum()),
                  hq=bool(((us == h) & bu).any()), dd=float(1 - px[q5] / max(pp.max(), 1e-30)), r=r, q=q, end=end, es=es)
        # adds at the decision: 2nd lot entered 1 trade after q5 (row q5+2), sold at H with lot 1 (joint)
        r2 = q5 + 2
        st["add"] = {}
        if r2 <= end - 1:
            for H in (12, 30):
                if q[H] >= r2: st["add"][H] = sum(tape.joint([(r, q[H]), (r2, q[H])]))
        rows.append(st)
    def rule_val(s, rule, x, H):
        if rule == "HOLD": return s["pn"][H] if s["u5"] >= x else s["pn"][5]
        if rule == "HOLDDN": return s["pn"][H] if s["u5"] <= x else s["pn"][5]
        if rule == "FLOW": return s["pn"][H] if s["fb"] >= x else s["pn"][5]
        if rule == "DUMP": return s["pn"][H] if s["nd"] >= 1 else s["pn"][5]
        if rule == "HQ": return s["pn"][H] if s["hq"] else s["pn"][5]
        if rule == "ADD": return s["add"].get(H, s["pn"][5]) if s["u5"] >= x else s["pn"][5]
        if rule == "ADDDN": return s["add"].get(H, s["pn"][5]) if (s["u5"] <= x and s["nd"] >= 1) else s["pn"][5]
    COST2 = 0.00352   # an add costs one more fill (NOW)
    grid = [("HOLD", x, H) for x in (-0.02, 0.0, 0.01, 0.02, 0.04, 0.08) for H in (8, 12, 20, 30)] + \
           [("HOLDDN", x, H) for x in (-0.04, -0.02, 0.0) for H in (8, 12, 30)] + \
           [("FLOW", x, H) for x in (0.5, 1, 2, 4) for H in (8, 12, 30)] + [("DUMP", 0, H) for H in (8, 12, 30)] + [("HQ", 0, H) for H in (8, 12, 30)] + \
           [("ADD", x, H) for x in (0.0, 0.02, 0.04, 0.08) for H in (12, 30)] + [("ADDDN", x, H) for x in (-0.02, 0.0) for H in (12, 30)]
    def gain(v, rule, x, H):
        g = 0.0
        for s in v:
            g += rule_val(s, rule, x, H) - s["pn"][5]
            if rule.startswith("ADD") and ((rule == "ADD" and s["u5"] >= x) or (rule == "ADDDN" and s["u5"] <= x and s["nd"] >= 1)) and H in s["add"]: g -= COST2
        return g
    for SET in ("LIVE", "OOS"):
        V = [s for s in rows if s["set"] == SET]
        days = sorted(set(s["day"] for s in V))
        P(f"\n## {SET}: {len(V)} entries; baseline 5-slot exit P&L {sum(s['pn'][5] for s in V):+.2f} SOL (curve, before tx costs; OOS = sum over 4 draws / 4)")
        div = 4.0 if SET == "OOS" else 1.0
        P("| rule (x, H) | gain SOL vs 5-slot timer (pooled) | per entry mSOL | per day gains " + " ".join(f"D{d}" for d in days) + " | days > 0 |")
        P("|---|---|---|---|---|")
        res = []
        for g_ in grid:
            pdg = [gain([s for s in V if s["day"] == d], *g_) / div for d in days]
            res.append((sum(pdg), g_, pdg))
        for tot, g_, pdg in sorted(res, key=lambda t: -t[0])[:14]:
            P(f"| {g_} | {tot:+.3f} | {1000 * tot / (len(V) / div):+.2f} | " + " ".join(f"{p:+.2f}" for p in pdg) + f" | {sum(p > 0 for p in pdg)}/{len(pdg)} |")
        # walk-forward: choose rule on day D-1, apply on D
        P(f"\nWalk-forward ({SET}): rule chosen on the previous day, applied to the day")
        wf = 0.0
        for d in days[1:]:
            prev_ = [s for s in V if s["day"] == d - 1]
            if not prev_: continue
            best = max(grid, key=lambda g_: gain(prev_, *g_))
            gd = gain([s for s in V if s["day"] == d], *best) / div; wf += gd
            P(f"- D{d}: chosen {best} (prev-day gain {gain(prev_, *best) / div:+.3f}); gain on D{d} {gd:+.3f} SOL")
        P(f"- walk-forward total {wf:+.3f} SOL")
        # state at the decision vs extension value (hold 5 -> 30)
        P(f"\nExtension value (P&L at 30 slots - at 5) by state at the 5-slot mark ({SET}, mSOL per entry):")
        for nm, f in (("u5 < -5%", lambda s: s["u5"] < -0.02), ("u5 -5..0%", lambda s: -0.02 <= s["u5"] < 0), ("u5 0..+5%", lambda s: 0 <= s["u5"] < 0.02),
                      ("u5 +5..+10%", lambda s: 0.02 <= s["u5"] < 0.04), ("u5 >= +10%", lambda s: s["u5"] >= 0.04), ("new dump since entry", lambda s: s["nd"] >= 1),
                      ("haqq bought since entry", lambda s: s["hq"]), ("followers >= 2 SOL", lambda s: s["fb"] >= 2)):
            v = [s for s in V if f(s)]
            if v: P(f"- {nm}: n {len(v)}, 5->12 {1000 * np.mean([s['pn'][12] - s['pn'][5] for s in v]):+.2f}, 5->30 {1000 * np.mean([s['pn'][30] - s['pn'][5] for s in v]):+.2f}, "
                    f"add+hold30 vs 5 (minus add fill cost) {1000 * np.mean([s['add'].get(30, s['pn'][5]) - s['pn'][5] - (COST2 if 30 in s['add'] else 0) for s in v]):+.2f}")
    P.save()


if __name__ == "__main__":
    main()
