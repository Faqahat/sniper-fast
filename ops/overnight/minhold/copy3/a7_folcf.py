#!/usr/bin/env python3
# DOES THEIR PROFIT COME FROM FOLLOWERS? Counterfactual replay of each wallet's OWN position (tapes): remove every outside buy that
# lands within N slots after their first buy (N = 1, 2, 5, 25 ~ 5 s), keep everything else; their later buys keep their SOL, their sells
# keep their token amounts (SOL recomputed). Compare PnL with the real tape PnL (same fee model). Read-only -> out/folcf.json
import os, sys, json, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat, lib3
T, _ = lib3.load_tapes(); P = [p for p in json.load(open(os.path.join(lib3.HERE, "out/pos3.json"))) if not p.get("nobuy") and not p["mayhem"]]
def fr(t): return (t["fbps"] + t["cbps"]) / 1e4
def cf(tr, k0, W, n_slots):
    s0 = tr[k0]["s"]; V, Tk = tr[k0 - 1]["vsol"], tr[k0 - 1]["vtok"] if k0 > 0 else (feat.V0, feat.T0)
    if k0 == 0: V, Tk = feat.V0, feat.T0
    spent = 0.0; got = 0.0; held = 0; removed = 0.0
    for t in tr[k0:]:
        if t["user"] == W:
            if t["buy"]:
                d = Tk * t["sol"] // (V + t["sol"]); V += t["sol"]; Tk -= d; held += d; spent += t["sol"] * (1 + fr(t)) / 1e9
            else:
                k = min(t["tok"], held)
                if k <= 0: continue
                so = V * k // (Tk + k); V -= so; Tk += k; held -= k; got += so * (1 - fr(t)) / 1e9
            continue
        if t["buy"] and t["s"] - s0 <= n_slots: removed += t["sol"] / 1e9; continue
        if t["buy"]: d = Tk * t["sol"] // (V + t["sol"]); V += t["sol"]; Tk -= d
        else: so = V * t["tok"] // (Tk + t["tok"]); V -= so; Tk += t["tok"]
        if V >= 115e9 or Tk <= 279_950_000_000_000: break
    if held > 0 and Tk > 0:
        so = V * held // (Tk + held); got += so * (1 - 0.0125) / 1e9
    return got - spent, removed
out = {}
for w8, W in lib3.W3.items():
    v = [p for p in P if p["w"] == w8 and not p["open"]]
    res = {}
    for n in (0, 1, 2, 5, 25):
        tot = 0.0; rem = []; wins = 0
        for p in v:
            pn, r = cf(T[p["m"]], p["k0"], W, n if n > 0 else -1)
            tot += pn; rem.append(r); wins += pn > 0
        res[n] = dict(pnl=tot, removed_sol_med=statistics.median(rem), win=wins / len(v))
    out[w8] = dict(n=len(v), real=sum(p["pnl"] for p in v), cf=res)
    print(f"{w8}: {len(v)} closed positions | tape PnL {out[w8]['real']:+.2f} | replay check (nothing removed) {res[0]['pnl']:+.2f} | "
          + " | ".join(f"no outside buys {n} slot{'s' if n > 1 else ''} after: {res[n]['pnl']:+.2f} (win {res[n]['win']:.0%}, removed med {res[n]['removed_sol_med']:.2f} SOL)" for n in (1, 2, 5, 25)))
json.dump(out, open(os.path.join(lib3.HERE, "out/folcf.json"), "w"), indent=1)
