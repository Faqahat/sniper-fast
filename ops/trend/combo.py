#!/usr/bin/env python3
# READ-ONLY, offline. All 17 real buys (PROD 5 + FRZ 12): a 0.5 SOL buy placed where each real buy landed (Run 2 costs),
# every later trade replayed by amount. Facts per token, then a grid of causal exit policies (take-profit, stop-loss,
# time stop, trailing stop, "sell when the dev / an early wallet sells"), scored honestly:
#   in-sample best (optimistic) vs leave-one-out (pick on 16, test on the 17th) vs FRZ->PROD and PROD->FRZ splits.
import sys, os, json, itertools, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
SETS = [("PROD", os.path.join(HERE, "out"), "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"), ("FRZ", os.path.join(HERE, "out_frz"), "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS")]
X, COST, OVER, L = 493827160, 516585000, 91160, 1e9


def load():
    T = []
    for grp, d, W in SETS:
        RAW = json.load(open(os.path.join(d, "raw.json"))); META = json.load(open(os.path.join(d, "meta.json")))
        for mint, R in RAW.items():
            ev = R["events"]; buy = next(e for e in R["mine"] if e["buy"])
            ib = next(i for i, e in enumerate(ev) if e["sig"] == buy["sig"] and e["user"] == W and e["buy"])
            S = R["create"][0]; dev = ev[0]["user"]; early = {e["user"] for e in ev[:ib] if e["buy"]} - {W}
            V0, T0 = buy["vsol"] - buy["sol"], buy["vtok"] + buy["tok"]; fb, cb = buy["fee_bps"], buy["cfee_bps"]
            q = T0 * X // (V0 + X); V, Tk = V0 + X, T0 - q
            def pnl(V, Tk):
                x = V * q // (Tk + q); return (x - (-(-x * fb // 10000)) - (-(-x * cb // 10000)) - OVER - COST) / L
            path = [dict(slot=buy["slot"], d=buy["slot"] - S, pnl=pnl(V, Tk), buy=None, sol=0, who="us", sig=buy["sig"], user=W)]
            for e in ev[ib + 1:]:
                if e["user"] == W: continue
                if e["buy"]: dd = Tk * e["sol"] // (V + e["sol"]); V += e["sol"]; Tk -= dd
                else: so = V * e["tok"] // (Tk + e["tok"]); V -= so; Tk += e["tok"]
                who = "dev" if e["user"] == dev else ("early" if e["user"] in early else "other")
                path.append(dict(slot=e["slot"], d=e["slot"] - S, pnl=pnl(V, Tk), buy=e["buy"], sol=e["sol"] / L, who=who, sig=e["sig"], user=e["user"]))
            T.append(dict(grp=grp, mint=mint, name=(META.get(mint) or {}).get("symbol") or mint[:6], S=S, entry_d=buy["slot"] - S, n_before=ib,
                          sol_before=sum(e["sol"] for e in ev[:ib] if e["buy"]) / L, dev_sol=ev[0]["sol"] / L, path=path))
    return T


TOK = load()
print(f"{len(TOK)} tokens: " + ", ".join(f"{t['grp']}:{t['name']}" for t in TOK))
# ---------- facts ----------
print("\nFACTS (0.5 SOL at the real landing spot; S = create slot, ~0.21 s per slot)")
print(f"{'token':16} {'in':>4} {'1st outside trade':>18} {'dev 1st sell':>13} {'buys/sells in 10 s':>19} {'peak PnL (when)':>18} {'PnL @2s':>8} {'@10s':>7} {'@60s':>7}")
def at(t, k):
    x = [p for p in t["path"] if p["d"] <= k]; return x[-1]["pnl"]
for t in TOK:
    P = t["path"][1:]
    first = P[0] if P else None
    devs = next((p for p in P if p["who"] == "dev" and p["buy"] is False), None)
    b10 = sum(1 for p in P if p["d"] <= 50 and p["buy"]); s10 = sum(1 for p in P if p["d"] <= 50 and p["buy"] is False)
    pk = max(t["path"], key=lambda p: p["pnl"])
    print(f"{t['grp'] + ':' + t['name']:16} S+{t['entry_d']:<2} {('S+%d %s %s' % (first['d'], 'BUY' if first['buy'] else 'SELL', first['who'])) if first else '-':>18} "
          f"{('S+%d' % devs['d']) if devs else 'none':>13} {b10:>9}/{s10:<9} {pk['pnl']:+.3f} (S+{pk['d']:<3}) {at(t, 10):+8.3f} {at(t, 50):+7.3f} {at(t, 285):+7.3f}")
# ---------- policies ----------
def run(t, tp, sl, ts, ev_exit, trail):
    P = t["path"]; peak = P[0]["pnl"]; prev = P[0]
    for p in P[1:]:
        if p["d"] > ts: return prev["pnl"]                              # time stop: sell at the state at the end of S+ts
        v = p["pnl"]; peak = max(peak, v)
        if ev_exit == "dev" and p["who"] == "dev" and p["buy"] is False: return v
        if ev_exit == "dev/early" and p["who"] in ("dev", "early") and p["buy"] is False: return v
        if ev_exit == "any sell" and p["buy"] is False: return v
        if tp is not None and v >= tp * 0.5166: return v
        if sl is not None and v <= -sl * 0.5166: return v
        if trail and peak >= trail[0] * 0.5166 and v <= peak - trail[1] * 0.5166: return v
        prev = p
    return prev["pnl"]
POL = list(itertools.product([0.05, 0.10, 0.15, 0.20, 0.30, 0.50, None], [0.08, 0.12, 0.15, 0.20, 0.30, None], [3, 5, 10, 20, 30, 50, 100, 285],
                             [None, "dev", "dev/early", "any sell"], [None, (0.05, 0.05), (0.10, 0.05), (0.10, 0.10), (0.20, 0.10)]))
M = [[run(t, *p) for t in TOK] for p in POL]
name = lambda p: (f"TP {p[0]:.0%}" if p[0] else "no TP") + " / " + (f"SL {p[1]:.0%}" if p[1] else "no SL") + f" / time S+{p[2]}" + (f" / exit on {p[3]} sell" if p[3] else "") + (f" / trail {p[4][0]:.0%}-{p[4][1]:.0%}" if p[4] else "")
idx = range(len(TOK)); tot = lambda i, ids: sum(M[i][j] for j in ids)
base = POL.index((None, None, 3, None, None))
print(f"\n{len(POL)} exit policies tried on {len(TOK)} tokens (0.5 SOL each)")
print(f"baseline 'sell at S+3' (what we do now): {tot(base, idx):+.3f} SOL")
best = sorted(range(len(POL)), key=lambda i: -tot(i, idx))[:8]
print("IN-SAMPLE best (picked looking at all 17 = optimistic):")
for i in best: print(f"   {tot(i, idx):+.3f}  wins {sum(M[i][j] > 0 for j in idx)}/17  {name(POL[i])}")
# leave-one-out: pick the best policy on the other 16, score it on the held-out token
loo = []
for j in idx:
    others = [k for k in idx if k != j]
    bi = max(range(len(POL)), key=lambda i: tot(i, others)); loo.append((M[bi][j], name(POL[bi])))
print(f"LEAVE-ONE-OUT (pick on 16, test on the 17th, x17): {sum(v for v, _ in loo):+.3f} SOL   (vs baseline {tot(base, idx):+.3f})")
for (v, n), t in zip(loo, TOK): print(f"   {t['grp']}:{t['name']:12} {v:+.3f}  picked: {n}")
for a, b in (("FRZ", "PROD"), ("PROD", "FRZ")):
    A = [j for j in idx if TOK[j]["grp"] == a]; B = [j for j in idx if TOK[j]["grp"] == b]
    bi = max(range(len(POL)), key=lambda i: tot(i, A))
    print(f"PICK ON {a} ({len(A)}) -> TEST ON {b} ({len(B)}): picked '{name(POL[bi])}' = {tot(bi, A):+.3f} on {a}; on {b}: {tot(bi, B):+.3f}  (baseline on {b}: {tot(base, B):+.3f})")
json.dump(dict(tokens=[{k: v for k, v in t.items() if k != "path"} for t in TOK], pol=[name(p) for p in POL], M=M), open(os.path.join(HERE, "out", "combo.json"), "w"))
