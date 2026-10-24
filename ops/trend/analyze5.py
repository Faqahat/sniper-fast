#!/usr/bin/env python3
# READ-ONLY, offline (reads trend5.py's raw.json). Per token: every trade after our REAL buy, and our PnL if we had sold
# right after each one; then simple "trend" exit rules (after N trades, after X buys, at the first sell after K buys,
# take-profit, fixed time), each also with a realistic delay (our sell lands at the end of the trigger trade's slot).
# usage: python3 -I analyze5.py <out dir>
import sys, os, json, csv, datetime
OUT = sys.argv[1]
W = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
PROS = ("dKMjeG", "4yFAz7", "9XPMCa", "3yrJE1", "AHwJSn", "2EsRia", "9qz7cW")
RAW = json.load(open(os.path.join(OUT, "raw.json")))
META = json.load(open(os.path.join(OUT, "meta.json"))) if os.path.exists(os.path.join(OUT, "meta.json")) else {}
L = 1e9
utc = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%H:%M:%S") if t else "-"
mc = lambda V, T: V * 1e6 / T                         # market cap in SOL (1B supply, 6 decimals; V lamports, T raw units)


def analyze(mint, R):
    ev = R["events"]; mine = R["mine"]
    buy = next(e for e in mine if e["buy"]); sells = [e for e in mine if not e["buy"]]
    q = buy["tok"]; cost_chg = buy["chg"]                               # wallet change of the buy tx (negative)
    realized = sum(e["chg"] for e in mine) / L
    ls_ = sells[-1]
    # what our real final sell paid besides the curve + pump fees: tx fee + sell tip - token-account rent returned
    sell_over = -(ls_["chg"] - (ls_["sol"] - ls_["fee"] - ls_["cfee"]))
    fb, cb = sells[0]["fee_bps"], sells[0]["cfee_bps"]
    ib = next(i for i, e in enumerate(ev) if e["sig"] == buy["sig"] and e["user"] == W and e["buy"])
    S = R["create"][0] if R.get("create") else ev[0]["slot"]
    creator = next((e["user"] for e in ev if e["slot"] == S), None)    # first trade in the create slot = the dev buy
    early = {e["user"] for e in ev[:ib] if e["buy"]}                   # dev, bundle and anyone who bought before us
    def pnl(V, T):
        x = V * q // (T + q)
        fees = -(-x * fb // 10000) - (-x * cb // 10000)                 # pump fee + creator fee, each rounded up (as on chain)
        return (cost_chg + x - fees - sell_over) / L, x / L
    V, T = buy["vsol"], buy["vtok"]
    rows = []; n = 0; nb = 0; ns = 0; held_real = True; mismatch = 0
    for k, e in enumerate(ev):
        tag = "US-BUY" if k == ib else ("US-SELL" if (e["user"] == W and not e["buy"]) else ("DEV" if e["user"] == creator and k <= ib else ("early" if k < ib else "")))
        if e["user"] in early and k > ib and e["user"] != W: tag = "dev/early wallet" if e["user"] != creator else "DEV"
        if e["user"][:6] in PROS: tag = (tag + " PRO").strip()
        r = dict(k=k - ib, slot=e["slot"], sk=e["slot"] - S, time=utc(e["bt"]), side="BUY" if e["buy"] else "SELL", sol=e["sol"] / L, tok=e["tok"] / 1e6,
                 user=e["user"], payer=e["payer"], sig=e["sig"], mc_chain=mc(e["vsol"], e["vtok"]), tag=tag)
        if k > ib:
            if e["user"] == W and not e["buy"]:
                held_real = False                                          # our real sell: skipped in the "what if we held" replay
                r.update(mc_replay=mc(V, T), pnl=None, gross=None, n=None)
                rows.append(r); continue
            if e["buy"]:
                d = T * e["sol"] // (V + e["sol"]); V += e["sol"]; T -= d; nb += 1
            else:
                so = V * e["tok"] // (T + e["tok"]); V -= so; T += e["tok"]; ns += 1
            n += 1
            if held_real and (abs(V - e["vsol"]) > 2 or abs(T - e["vtok"]) > 2): mismatch += 1
            p, g = pnl(V, T)
            r.update(mc_replay=mc(V, T), pnl=p, gross=g, n=n, nb=nb, ns=ns, held_real=held_real, V=V, T=T)
        elif k == ib:
            p, g = pnl(V, T); r.update(mc_replay=mc(V, T), pnl=p, gross=g, n=0, nb=0, ns=0, held_real=True, V=V, T=T)
        rows.append(r)
    # check: our real exit through the formula (single-sell tokens: state right before our sell)
    chk = None
    if len(sells) == 1:
        js = next(i for i, r in enumerate(rows) if r["tag"].startswith("US-SELL"))
        prev = [r for r in rows[:js] if r.get("V") is not None][-1]
        chk = pnl(prev["V"], prev["T"])[0]
    return dict(mint=mint, S=S, buy=buy, sells=sells, realized=realized, chk=chk, sell_over=sell_over / L, mismatch=mismatch, rows=rows, creator=creator,
                cost=-cost_chg / L, size=buy["sol"] / L, create=R.get("create"))


A = [analyze(m, R) for m, R in RAW.items()]
A.sort(key=lambda a: a["S"])
for a in A:
    nm = META.get(a["mint"], {}); a["name"] = nm.get("symbol") or a["mint"][:6]
    print(f"{a['name']:8} {a['mint']}  S={a['S']}  size {a['size']:.3f}  realized {a['realized']:+.6f}  formula-check {a['chk'] if a['chk'] is None else round(a['chk'], 6)}  "
          f"replay mismatches before our sell {a['mismatch']}  trades after our buy {sum(1 for r in a['rows'] if r.get('n'))}")


# ---------- rules (causal) ----------
def after(a):
    return [r for r in a["rows"] if r.get("n")]                       # outside trades after our buy (our real sells excluded)


def end_of_slot(a, r):
    same = [x for x in after(a) if x["slot"] == r["slot"]]
    return same[-1]["pnl"]


def last(a):
    x = after(a)
    return x[-1] if x else next(r for r in a["rows"] if r["k"] == 0)


def rule(a, trig):
    """trig(r) -> True on the trade that triggers our sell; returns (instant pnl, end-of-slot pnl, trade n or None=never->held to window end)"""
    for r in after(a):
        if trig(r): return r["pnl"], end_of_slot(a, r), r["n"]
    l = last(a); return l["pnl"], l["pnl"], None


RULES = []
for N in (1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30):
    RULES.append((f"sell right after {N} trades", lambda a, N=N: rule(a, lambda r: r["n"] >= N)))
for X in (1, 2, 3, 4, 5, 6, 8, 10):
    RULES.append((f"sell right after {X} outside buys", lambda a, X=X: rule(a, lambda r: r["nb"] >= X)))
for K in (0, 1, 2, 3, 4, 5):
    RULES.append((f"sell at the first sell after {K}+ buys", lambda a, K=K: rule(a, lambda r: r["side"] == "SELL" and r["nb"] >= K)))
for Y in (0.05, 0.10, 0.20, 0.30, 0.50):
    RULES.append((f"sell when up {Y:.0%} (net of all fees)", lambda a, Y=Y: rule(a, lambda r: r["pnl"] >= Y * a["cost"])))
def tp_ts(a, Y, k):
    """take profit at +Y (net, right after the trade that gets there) or, if not reached by the end of slot S+k, sell there"""
    base = next(r for r in a["rows"] if r["k"] == 0)
    prev = base
    for r in after(a):
        if r["slot"] > a["S"] + k: return prev["pnl"], prev["pnl"], None
        if r["pnl"] >= Y * a["cost"]: return r["pnl"], end_of_slot(a, r), r["n"]
        prev = r
    return prev["pnl"], prev["pnl"], None
for Y in (0.05, 0.10, 0.20):
    for k in (20, 50, 100):
        RULES.append((f"up {Y:.0%} or time stop S+{k} (~{k * 0.21:.0f} s)", lambda a, Y=Y, k=k: tp_ts(a, Y, k)))
for k in (2, 3, 5, 10, 20, 50, 100, 200, 400):
    def tr(a, k=k):
        x = [r for r in after(a) if r["slot"] <= a["S"] + k]
        p = x[-1]["pnl"] if x else next(r for r in a["rows"] if r["k"] == 0)["pnl"]
        return p, p, None
    RULES.append((f"hold to end of slot S+{k} (~{k * 0.21:.1f} s)", tr))
RULES.append(("BEST possible (hindsight)", lambda a: (max(r["pnl"] for r in after(a) + [next(r for r in a['rows'] if r['k'] == 0)]),) * 2 + (None,)))
RES = {name: [f(a) for a in A] for name, f in RULES}

# ---------- outputs ----------
for a in A:
    with open(os.path.join(OUT, f"{a['name']}_{a['mint'][:8]}.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n_after_our_buy", "slot", "S+k", "time_utc", "side", "sol", "tokens", "wallet", "fee_payer", "tx_signature", "mc_sol_onchain", "mc_sol_if_we_held",
                    "our_pnl_sol_if_sold_right_after", "tag"])
        for r in a["rows"]:
            w.writerow([r["k"], r["slot"], r["sk"], r["time"], r["side"], f"{r['sol']:.6f}", f"{r['tok']:.0f}", r["user"], r["payer"], r["sig"], f"{r['mc_chain']:.2f}",
                        "" if r.get("mc_replay") is None else f"{r['mc_replay']:.2f}", "" if r.get("pnl") is None else f"{r['pnl']:+.6f}", r["tag"]])
json.dump(dict(tokens=[{k: v for k, v in a.items() if k != "rows"} | {"rows": a["rows"]} for a in A], rules={n: v for n, v in RES.items()}), open(os.path.join(OUT, "analysis.json"), "w"))
print("\nrule | " + " | ".join(a["name"] for a in A) + " | TOTAL (instant) | TOTAL (sell lands end of that slot)")
for name, v in RES.items():
    print(f"{name:42} | " + " | ".join(f"{p:+.4f}" + ("" if n is not None or name.startswith(("hold", "BEST", "up ")) else "*") for p, _, n in v)
          + f" | {sum(p for p, _, _ in v):+.4f} | {sum(e for _, e, _ in v):+.4f}")
print("* = rule never triggered inside the window: held to the window end (~85 s)")
