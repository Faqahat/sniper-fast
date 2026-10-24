#!/usr/bin/env python3
# READ-ONLY, offline (reads trend_w.py's raw.json). Entry = a SIZE-SOL buy placed EXACTLY where the wallet's real buy landed
# (same pre-trade curve state), with Run 2's real costs (0.5 SOL buy tx cost 0.516585 SOL incl. pump fees, priority, tips and
# token-account rent; real sell overhead 0.000091 = tx fee + tip - rent back). Every later trade is replayed by amount
# (buys by SOL, sells by tokens; the wallet's own real trades removed). Then the same exit rules as analyze5.py.
# usage: python3 -I analyze_sim.py <out dir> [seed]
import sys, os, json, csv, random, datetime
OUT = sys.argv[1]; SEED = int(sys.argv[2]) if len(sys.argv) > 2 else int.from_bytes(os.urandom(3), "big")
W = os.environ.get("WALLET", "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS")
X_CURVE = 493827160            # SOL into the curve for a 0.5 SOL buy (pump fees on top), as in our real 0.5 SOL buys
COST = 516585000               # what that buy tx really cost our wallet (Run 2, Jito-client route: 0.004 tips)
SELL_OVER = 91160              # real sell: 605,000 tx fee + 1,000,000 tip - 1,513,840 rent back
L = 1e9
RAW = json.load(open(os.path.join(OUT, "raw.json"))); META = json.load(open(os.path.join(OUT, "meta.json")))
utc = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%m-%d %H:%M:%S") if t else "-"
mc = lambda V, T: V * 1e6 / T


def analyze(mint, R):
    ev = R["events"]; mine = R["mine"]
    buy = next(e for e in mine if e["buy"])
    ib = next(i for i, e in enumerate(ev) if e["sig"] == buy["sig"] and e["user"] == W and e["buy"])
    S = R["create"][0] if R.get("create") else ev[0]["slot"]
    fb, cb = buy["fee_bps"], buy["cfee_bps"]
    # (a) check: replay the wallet's REAL tiny trade path and compare with the chain until its real sell
    V, T = buy["vsol"], buy["vtok"]; mism = 0
    for e in ev[ib + 1:]:
        if e["user"] == W: break
        if e["buy"]: d = T * e["sol"] // (V + e["sol"]); V += e["sol"]; T -= d
        else: so = V * e["tok"] // (T + e["tok"]); V -= so; T += e["tok"]
        mism = max(mism, abs(V - e["vsol"]) / e["vsol"], abs(T - e["vtok"]) / e["vtok"])
    # (b) our 0.5 SOL buy in the same spot
    V0, T0 = buy["vsol"] - buy["sol"], buy["vtok"] + buy["tok"]
    q = T0 * X_CURVE // (V0 + X_CURVE); V, T = V0 + X_CURVE, T0 - q
    def pnl(V, T):
        x = V * q // (T + q); fees = -(-x * fb // 10000) - (-x * cb // 10000)
        return (x - fees - SELL_OVER - COST) / L
    rows = [dict(n=0, slot=buy["slot"], sk=buy["slot"] - S, time=utc(buy["bt"]), side="BUY", sol=X_CURVE / L, user="(us, 0.5 SOL in place of " + W[:6] + ")", sig=buy["sig"],
                 mc=mc(V, T), mc_chain=mc(buy["vsol"], buy["vtok"]), pnl=pnl(V, T), tag="US-BUY (simulated)")]
    pre = [dict(n=-(ib - i), slot=e["slot"], sk=e["slot"] - S, time=utc(e["bt"]), side="BUY" if e["buy"] else "SELL", sol=e["sol"] / L, user=e["user"], sig=e["sig"],
                mc=mc(e["vsol"], e["vtok"]), mc_chain=mc(e["vsol"], e["vtok"]), pnl=None, tag="DEV" if i == 0 else "before us") for i, e in enumerate(ev[:ib])]
    n = nb = 0
    for e in ev[ib + 1:]:
        if e["user"] == W:
            rows.append(dict(n=None, slot=e["slot"], sk=e["slot"] - S, time=utc(e["bt"]), side="BUY" if e["buy"] else "SELL", sol=e["sol"] / L, user=e["user"], sig=e["sig"],
                             mc=None, mc_chain=mc(e["vsol"], e["vtok"]), pnl=None, tag="FRZ real tiny trade (removed)")); continue
        if e["buy"]: d = T * e["sol"] // (V + e["sol"]); V += e["sol"]; T -= d; nb += 1
        else: so = V * e["tok"] // (T + e["tok"]); V -= so; T += e["tok"]
        n += 1
        rows.append(dict(n=n, nb=nb, slot=e["slot"], sk=e["slot"] - S, time=utc(e["bt"]), side="BUY" if e["buy"] else "SELL", sol=e["sol"] / L, user=e["user"], sig=e["sig"],
                         mc=mc(V, T), mc_chain=mc(e["vsol"], e["vtok"]), pnl=pnl(V, T), tag="DEV" if e["user"] == ev[0]["user"] else ""))
    real = sum(e["chg"] for e in mine) / L
    return dict(mint=mint, name=(META.get(mint) or {}).get("symbol") or mint[:6], S=S, buy=buy, sells=[e for e in mine if not e["buy"]], real=real,
                real_sol=buy["sol"] / L, mism=mism, rows=pre + rows, cost=COST / L)


A = sorted([analyze(m, R) for m, R in RAW.items()], key=lambda a: -a["S"])
after = lambda a: [r for r in a["rows"] if (r.get("n") or 0) >= 1]
base = lambda a: next(r for r in a["rows"] if r.get("n") == 0 and r["tag"].startswith("US-BUY"))
def eos(a, r): return [x for x in after(a) if x["slot"] == r["slot"]][-1]["pnl"]
def rule(a, trig):
    for r in after(a):
        if trig(r): return r["pnl"], eos(a, r), r["n"]
    x = after(a); l = x[-1] if x else base(a); return l["pnl"], l["pnl"], None
def tp_ts(a, Y, k):
    prev = base(a)
    for r in after(a):
        if r["slot"] > a["S"] + k: return prev["pnl"], prev["pnl"], None
        if r["pnl"] >= Y * a["cost"]: return r["pnl"], eos(a, r), r["n"]
        prev = r
    return prev["pnl"], prev["pnl"], None
def hold(a, k):
    x = [r for r in after(a) if r["slot"] <= a["S"] + k]; p = x[-1]["pnl"] if x else base(a)["pnl"]; return p, p, None
RULES = [("sell right after 2 trades (S+2-style quick flip)", lambda a: rule(a, lambda r: r["n"] >= 2))]
for N in (3, 4, 5): RULES.append((f"sell right after {N} trades", lambda a, N=N: rule(a, lambda r: r["n"] >= N)))
for Y, k in ((0.10, 50), (0.10, 20), (0.10, 100), (0.05, 50), (0.20, 50)):
    RULES.append((f"up {Y:.0%} or time stop S+{k} (~{k * 0.21:.0f} s)", lambda a, Y=Y, k=k: tp_ts(a, Y, k)))
for k in (2, 20, 50, 100): RULES.append((f"hold to S+{k} (~{k * 0.21:.1f} s)", lambda a, k=k: hold(a, k)))
RULES.append(("BEST possible (hindsight)", lambda a: (max(r["pnl"] for r in after(a) + [base(a)]),) * 2 + (None,)))

pick = sorted(random.Random(SEED).sample(range(len(A)), 5))
print(f"FRZ last {len(A)} tokens (newest first); random 5 with seed {SEED}: {[A[i]['name'] for i in pick]}")
for i, a in enumerate(A):
    print(f"  {'*' if i in pick else ' '} {a['name']:10} {a['mint']}  S={a['S']}  FRZ real buy {a['real_sol']:.6f} SOL at S+{a['buy']['slot'] - a['S']}, FRZ real result {a['real']:+.6f}  replay check: max deviation from chain {a['mism']:.1e}  trades after {len(after(a))}")
RES = {n: [f(a) for a in A] for n, f in RULES}
def table(idx, title):
    print(f"\n{title}\nrule | " + " | ".join(A[i]["name"][:9] for i in idx) + " | TOTAL | realistic")
    for n, v in RES.items():
        print(f"{n:46} | " + " | ".join(f"{v[i][0]:+.4f}" for i in idx) + f" | {sum(v[i][0] for i in idx):+.4f} | {sum(v[i][1] for i in idx):+.4f}")
table(pick, "RANDOM 5 (0.5 SOL each at FRZ's real landing spot, SOL)")
table(range(len(A)), f"ALL {len(A)}")
json.dump(dict(seed=SEED, pick=pick, tokens=A, rules=RES), open(os.path.join(OUT, "analysis_sim.json"), "w"))
for a in A:
    with open(os.path.join(OUT, f"{a['name']}_{a['mint'][:8]}.csv".replace("/", "_")), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["n_trades_after_our_buy", "slot", "S+k", "time_utc", "side", "sol", "wallet", "tx_signature", "mc_sol", "our_pnl_sol_if_sold_right_after", "tag"])
        for r in a["rows"]:
            w.writerow([r["n"], r["slot"], r["sk"], r["time"], r["side"], f"{r['sol']:.6f}", r["user"], r["sig"], "" if r["mc"] is None else f"{r['mc']:.2f}",
                        "" if r["pnl"] is None else f"{r['pnl']:+.6f}", r["tag"]])
