#!/usr/bin/env python3
# READ-ONLY, offline: "dev snipe" replay on every launch of the watched devs (devreplay.json).
# Entry: our SIZE-SOL buy right after the dev's create tx (the spot AKbot winners take: first outside buyer).
#   opt  = every later trade kept (replayed by amount)
#   pess = the real first outside buyer removed (we took its place, so its buy and its sells never happen)
# Costs: pump fee (event bps) both sides, priority 0.0025, landing tip TIP% of size, sell overhead 0.0016 (tx + 0.001 sell tip).
# Exits (causal): hold to S+k; take-profit X% with a time stop; stop-loss; follow the dev's first sell; trailing stop.
# Honest split: devs/exits chosen on the first half of the window, scored on the second half.
import sys, json, collections, statistics, itertools
D = json.load(open(sys.argv[1])); SIZE = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5; TIP = float(sys.argv[3]) if len(sys.argv) > 3 else 0.015
PRIO, SELL_OVER = 0.0025, 0.0016
def pre(e): return (e["vsol"] - e["sol"], e["vtok"] + e["tok"]) if e["buy"] else (e["vsol"] + e["sol"], e["vtok"] - e["tok"])
def order(E):
    by = collections.defaultdict(list)
    for e in E: by[e["slot"]].append(e)
    out, V = [], None
    for s in sorted(by):
        left = list(by[s])
        while left:
            nx = [e for e in left if V is not None and abs(pre(e)[0] - V) <= 2] or sorted(left, key=lambda e: pre(e)[0])
            e = nx[0]; out.append(e); left.remove(e); V = e["vsol"]
    return out
import os as _os; sys.path.insert(0, _os.path.dirname(_os.path.abspath(sys.argv[0]))); sys.path.insert(0, ".")
from devside import build_devside
SIDE = build_devside(D["launches"], order)
def path(L, variant, me=None):
    E = order(L["events"])
    ci = [i for i, e in enumerate(E) if e["sig"] == L["create_sig"]]
    if not ci: return None
    S = L["S"]; dev = L["dev"]; side = SIDE(L, E)
    # entry after the create AND every dev-side buy in the create slot (we can never get ahead of the dev's bundle)
    k = max([ci[-1]] + [i for i, e in enumerate(E) if e["buy"] and e["user"] in side and e["slot"] == S])
    if me: E = [e for e in E if e["user"] != me]; k = max([i for i, e in enumerate(E) if e["sig"] == L["create_sig"] or (e["buy"] and e["user"] in side and e["slot"] == S)] or [0])
    V, T = E[k]["vsol"], E[k]["vtok"]
    fee = ((E[k].get("fbps") or 95) + (E[k].get("cbps") or 30)) / 1e4
    x = SIZE * 1e9 / (1 + fee); q = T * x // (V + x); V += x; T -= q
    cost = SIZE + PRIO + TIP * SIZE + 0.000005
    rest = E[k + 1:]
    first_out = next((e["user"] for e in rest if e["buy"] and e["user"] not in side), None)
    if variant == "pess" and first_out: rest = [e for e in rest if e["user"] != first_out]
    def val(V, T):
        so = V * q / (T + q); return so * (1 - fee) / 1e9 - SELL_OVER - cost
    pts = [(S, val(V, T), None)]
    for e in rest:
        if e["buy"]: d = T * e["sol"] // (V + e["sol"]); V += e["sol"]; T -= d
        else: so = V * e["tok"] // (T + e["tok"]); V -= so; T += e["tok"]
        pts.append((e["slot"], val(V, T), "devsell" if (e["user"] == dev and not e["buy"]) else None))
    return dict(S=S, bt=L["bt"], dev=dev, pts=pts, cost=cost)
def hold(p, k):
    v = [x for x in p["pts"] if x[0] <= p["S"] + k]; return v[-1][1]
def tp(p, x, ts, sl=None):
    for s, v, _ in p["pts"][1:]:
        if s > p["S"] + ts: break
        if v >= x * p["cost"] or (sl is not None and v <= -sl * p["cost"]): return v
    return hold(p, ts)
def devsell(p, ts):
    for s, v, tag in p["pts"][1:]:
        if s > p["S"] + ts: break
        if tag == "devsell": return v
    return hold(p, ts)
def trail(p, arm, drop, ts):
    pk = p["pts"][0][1]
    for s, v, _ in p["pts"][1:]:
        if s > p["S"] + ts: break
        pk = max(pk, v)
        if pk >= arm * p["cost"] and v <= pk - drop * p["cost"]: return v
    return hold(p, ts)
EX = {f"hold S+{k} (~{k * 0.21:.1f}s)": (lambda p, k=k: hold(p, k)) for k in (1, 2, 3, 5, 10, 25, 50, 100)}
for x, ts in itertools.product((0.05, 0.1, 0.2, 0.3, 0.5), (10, 25, 50, 100)): EX[f"TP {x:.0%} else S+{ts}"] = (lambda p, x=x, ts=ts: tp(p, x, ts))
for x, sl, ts in itertools.product((0.1, 0.2, 0.3), (0.1, 0.2), (25, 50, 100)): EX[f"TP {x:.0%} SL {sl:.0%} else S+{ts}"] = (lambda p, x=x, sl=sl, ts=ts: tp(p, x, ts, sl))
for ts in (25, 50, 100): EX[f"sell when dev sells, else S+{ts}"] = (lambda p, ts=ts: devsell(p, ts))
for a, d, ts in itertools.product((0.1, 0.2), (0.05, 0.1), (50, 100)): EX[f"trail arm {a:.0%} drop {d:.0%} max S+{ts}"] = (lambda p, a=a, d=d, ts=ts: trail(p, a, d, ts))
EX["BEST possible (hindsight)"] = lambda p: max(v for _, v, _ in p["pts"])
for variant in ("opt", "pess"):
    P = [p for p in (path(L, variant) for L in D["launches"]) if p]
    mid = statistics.median(p["bt"] for p in P if p["bt"])
    A = [p for p in P if p["bt"] and p["bt"] < mid]; Bh = [p for p in P if p["bt"] and p["bt"] >= mid]
    res = {n: (sum(f(p) for p in A), sum(f(p) for p in Bh)) for n, f in EX.items()}
    print(f"\n=== variant {variant}: {len(P)} launches of {len({p['dev'] for p in P})} devs, size {SIZE} SOL, tip {TIP:.1%}; first half {len(A)}, second half {len(Bh)}")
    print(f"   {'exit':40} {'first half':>11} {'2nd half':>10} {'per launch (2nd)':>17}")
    for n in sorted(res, key=lambda n: -res[n][0])[:12]:
        a, b = res[n]; print(f"   {n:40} {a:+11.2f} {b:+10.2f} {b / max(1, len(Bh)):+17.4f}")
    for n in ("hold S+1 (~0.2s)", "hold S+3 (~0.6s)", "hold S+10 (~2.1s)", "BEST possible (hindsight)"):
        a, b = res[n]; print(f"   {n:40} {a:+11.2f} {b:+10.2f} {b / max(1, len(Bh)):+17.4f}")
    best = max((n for n in EX if not n.startswith("BEST")), key=lambda n: res[n][0])
    print(f"   picked on the first half: '{best}' -> second half {res[best][1]:+.2f} SOL ({res[best][1] / max(1, len(Bh)):+.4f}/launch)")
    # per dev with the picked exit, chosen devs = positive on the first half
    f = EX[best]; per = collections.defaultdict(lambda: [0.0, 0, 0.0, 0])
    for p in A: per[p["dev"]][0] += f(p); per[p["dev"]][1] += 1
    for p in Bh: per[p["dev"]][2] += f(p); per[p["dev"]][3] += 1
    good = [d for d, v in per.items() if v[0] > 0]
    print(f"   devs positive on the first half with that exit: {len(good)} of {len(per)}; their second half: {sum(per[d][2] for d in good):+.2f} SOL over {sum(per[d][3] for d in good)} launches")
    for d, v in sorted(per.items(), key=lambda kv: -kv[1][0]): print(f"      {d[:8]}  1st half {v[0]:+7.2f} ({v[1]:3})  2nd half {v[2]:+7.2f} ({v[3]:3})")
