#!/usr/bin/env python3
"""WHO step 7: details for the report -- r38's six losses (sellers + roles + rule flags), the named repeat dumpers measured FAIRLY
(every fill where the wallet held at arm, not only fills it sold into), whale dump-history distribution, per-run tables of key rules."""
import pickle, json, collections, sys
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/prevent/who")
from w6_score import SIX, ALL_LIVE
from w5_rules import PAPER_RUNS

D = "/home/it/sniper-data/prevent/who"
NAMED = ["dtrzJPj7", "dKMjeGJ4", "8NMLaLAQ", "AMDEmVoc", "CHDbebWQ", "4zT7uCnA", "CvHEVC7S", "9wRuFPJZ", "2H6DwrqA", "bwamJzzt", "FfW5e8gK", "pfVKXXhG", "7WdiCkB7", "774XnM9x", "2Bonf26M", "85YwZaQa"]


def main():
    W = pickle.load(open(f"{D}/windows.pkl", "rb")); F = pickle.load(open(f"{D}/feats.pkl", "rb"))
    S = json.load(open(f"{D}/score.json")); X = pickle.load(open(f"{D}/rules.pkl", "rb"))
    out = {}
    fl = [(w, f) for w, f in zip(W, F) if w["mode"] == "live" and w.get("filled") and "sellers" in f]
    sc = lambda w: w["pnl"] * 0.696 / (w["spend"] / 1e9)
    # 1. r38 six losses
    print("== r38 six losses: in-hold sellers (SOL) with role at arm / pct at arm / bot / same-slot cluster")
    six = []
    for rn, mk, kd in SIX + [("AMS38", "5cMetpCp", "t2")]:
        for w, f in fl:
            if w["run"] == rn and w["mint"].startswith(mk) and w["kind"] == kd:
                ss = sorted(f["sellers"].items(), key=lambda z: -z[1]["sol"])[:5]
                hold = sorted(f["hold"].items(), key=lambda z: -z[1])[:5]
                print(f"{mk[:8]} {kd:5s} pnl {w['pnl']:+.3f} trig {w['wallet'][:8]} {w['pct']:.1f}% age {w['age']} creator {(f.get('creator') or '?')[:8]} cr% {f.get('creator_pct', 0):.1f}")
                print("   holders@arm:", ", ".join(f"{u[:8]} {p:.1f}%" for u, p in hold))
                print("   sellers:", ", ".join(f"{u[:8]} {x['sol']:.2f} {x['role']} {x['pct_arm']:.1f}%{' BOT' if x['bot'] else ''}{' cl' + str(x['cluster']) if x['cluster'] else ''}" for u, x in ss))
                six.append({"mint": w["mint"], "kind": kd, "pnl": w["pnl"], "trig": w["wallet"], "creator": f.get("creator"), "holders": hold,
                            "sellers": [(u, x["sol"], x["role"], x["pct_arm"], x["bot"], x["cluster"]) for u, x in ss]})
    out["six"] = six
    # 2. named wallets, fair view
    full = {}
    for w, f in fl:
        for u in list(f["hold"]) + [w["wallet"]] + list(f["sellers"]):
            full.setdefault(u[:8], set()).add(u)
    print("\n== named wallets: every live fill where it HELD >= 0.5% at arm (fair) vs fills it SOLD >= 0.5 SOL into (biased upper bound)")
    print("wallet    held:n  pnl@.696 | of which sold>=0.5: n pnl | sold-into but not holding at arm: n pnl | as trigger: n pnl | as creator: n pnl")
    named = {}
    for p in NAMED:
        us = full.get(p, set())
        if not us: continue
        u = max(us, key=lambda z: 1)
        a = [(w, f) for w, f in fl if f["hold"].get(u, 0) >= 0.5]
        b = [(w, f) for w, f in a if f["sellers"].get(u, {}).get("sol", 0) >= 0.5]
        c = [(w, f) for w, f in fl if f["sellers"].get(u, {}).get("sol", 0) >= 0.5 and f["hold"].get(u, 0) < 0.5]
        tr = [(w, f) for w, f in fl if w["wallet"] == u]; cr = [(w, f) for w, f in fl if f.get("creator") == u]
        g = lambda L: (len(L), sum(sc(w) for w, f in L))
        named[u] = {"held": g(a), "held_sold": g(b), "sold_not_held": g(c), "trigger": g(tr), "creator": g(cr)}
        print(f"{p:9s} {g(a)[0]:4d} {g(a)[1]:+7.3f} | {g(b)[0]:3d} {g(b)[1]:+7.3f} | {g(c)[0]:3d} {g(c)[1]:+7.3f} | {g(tr)[0]:3d} {g(tr)[1]:+7.3f} | {g(cr)[0]:3d} {g(cr)[1]:+7.3f}")
    out["named"] = named
    # dtrzJPj7 timeline
    u = next(iter(full.get("dtrzJPj7", [])), None)
    if u:
        print("\n== dtrzJPj7 timeline (all live fills where it held >= 0.5% at arm, created the token, or sold into the hold)")
        for w, f in sorted(fl, key=lambda z: z[0]["fill_t"]):
            if f["hold"].get(u, 0) >= 0.5 or f.get("creator") == u or u in f["sellers"]:
                print(f"  {w['run']:6s} {w['kind']:5s} {w['mint'][:8]} pnl@.696 {sc(w):+.3f} held {f['hold'].get(u, 0):5.1f}% creator {f.get('creator') == u} sold {f['sellers'].get(u, {}).get('sol', 0):5.2f}")
    # 3. whale dump-history distribution
    meta = X["meta"]
    c1 = [m["C1"] for m in meta if m["mode"] == "live" and m["kind"] == "t2"]
    print("\n== T2 whales: big dumps (>=3% supply, >=10% drop) on OTHER tokens in the past 24 h:",
          {k: round(float(np.mean([x >= k for x in c1])) * 100, 1) for k in (1, 2, 5, 10, 20, 50)}, "% of windows")
    # per-whale-history pnl
    bins = [(0, 0), (1, 4), (5, 19), (20, 10 ** 9)]
    for lo, hi in bins:
        L = [m for m in meta if m["mode"] == "live" and m["kind"] == "t2" and m["filled"] and lo <= m["C1"] <= hi]
        print(f"   whale dumps24h {lo}-{hi}: fills {len(L)} pnl@.696 {sum(m['pnl_s'] for m in L):+.2f} mean {np.mean([m['pnl_s'] for m in L]) * 1000 if L else 0:+.1f} mSOL big-loss rate {np.mean([m['pnl_s'] < -0.05 for m in L]) * 100 if L else 0:.1f}%")
    # 4. per-run tables of key rules
    keys = [S["finalists"].get(k) for k in sorted(S["finalists"])]
    keys += ["A X1.0 n2 L0.05 Y3.0", "A X1.0 n1 L0.05 Y3.0", "C2 trig past fills<0 n>=2", "D1 creator holds>=6.0", "D3 creator past fills<0 n>=2", "C1 whale dumps24h>=5", "F bot holds>=3.0"]
    keys = [k for k in dict.fromkeys(keys) if k]
    R = S["rules"]
    print("\n== per-run saving @0.696 SOL (+ = rule saves) for key rules")
    print("run    " + " ".join(f"{k[:16]:>16s}" for k in keys))
    for r in ALL_LIVE:
        print(f"{r:6s} " + " ".join(f"{R[k]['per_run'][r]:+16.3f}" for k in keys))
    for r in PAPER_RUNS:
        print(f"{r:6s}P" + " ".join(f"{R[k]['per_paper'][r]:+16.3f}" for k in keys))
    out["per_run_keys"] = keys
    json.dump(out, open(f"{D}/detail.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
