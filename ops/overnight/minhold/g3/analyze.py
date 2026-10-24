#!/usr/bin/env python3
# 3GzBLpxT: (1) manual-style table of its last 100 positions, (2) copy-its-group's-first-buy + our own fast exit, replayed on the full tapes
# of each token (SOL curves exact; quote-token curves in SOL-equivalent units calibrated from the group's own SOL paid).
# Our buy lands T ms (block position) after the group's first buy in the token; exits are timers (sell lands at H), take-profit / stall /
# trailing (sell lands 50 ms after the trigger). Follower variants: keep (optimistic), dropbig (drop outside buys >= 2 SOL in the first slot
# after us: tight-slippage copy bots, heuristic), drop2 (drop every outside buy within 2 slots after us: pessimistic).
# Choose on R1+R2, test on R3+R4. Costs: pump fee 1.25% each side + 0.0015 SOL per tx x2 (+0.5% swap cost on quote-token curves, assumed).
import json, gzip, pickle, collections, statistics, time, os, urllib.request
D = pickle.load(gzip.open("g3.pkl.gz", "rb")); T = D["tapes"]; POS = D["pos"]; GT = D["gtx"]
G = set(l.strip() for l in open("grp.txt") if l.strip()); W = "3GzBLpxTWWTPWwBYQ8Jgrz5XLUCg9aY6HiB3GEBUBAv6"
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def ms(t): return t["s"] * 212.0 + t["i"] / max(SS.get(t["s"], 0), t["i"] + 1, 380) * 212.0
FEE = 0.0125; TX = 0.0015; SWAP = 0.005
def states(m):
    """per row: V (SOL-equiv quote reserves after the trade), Tk (virtual tokens after)."""
    tr = T[m]
    if not D["quote"][m]: return [(t["vsol"] / 1e9, t["vtok"]) for t in tr]
    cal = []
    for k, t in enumerate(tr):
        if t["user"] in G and t["buy"] and k and t["sig"] in GT:
            paid = -GT[t["sig"]]["dsol"] / 1e9 - 0.0155
            vb = tr[k - 1]["vtok"]
            if paid > 0.1 and t["vtok"] < vb: cal.append(paid / (1 + FEE + SWAP) / (1e0 / t["vtok"] - 1e0 / vb))
    if not cal: return None
    u = sorted(cal)[len(cal) // 2]
    return [(u / t["vtok"], t["vtok"]) for t in tr]
def replay(m, T_ms, B, var):
    tr = T[m]; S = states(m)
    if S is None: return None
    k0 = next((k for k, t in enumerate(tr) if t["user"] in G and t["buy"]), None)
    if k0 is None: return None
    t0 = ms(tr[k0]); kf = k0
    while kf + 1 < len(tr) and ms(tr[kf + 1]) - t0 <= T_ms: kf += 1
    V, Tk = S[kf]; kk = V * Tk; cost = FEE + (SWAP if D["quote"][m] else 0)
    X = B / (1 + cost); V2 = V + X; Tk2 = kk / V2; q = Tk - Tk2; V, Tk = V2, Tk2
    fill = max(ms(tr[kf]), t0 + T_ms); fs = tr[kf]["s"]
    val = lambda V, Tk: (V - V * Tk / (Tk + q)) * (1 - cost)
    path = [(fill, val(V, Tk), 0.0)]; lastbuy = fill
    for k in range(kf + 1, len(tr)):
        t = tr[k]; Vb = S[k - 1][0]; Va = S[k][0]
        if t["buy"]:
            dV = Va - Vb
            if var == "drop2" and t["user"] not in G and t["s"] - fs <= 2: continue
            if var == "dropbig" and t["user"] not in G and t["s"] - fs <= 1 and dV >= 2: continue
            V = V + dV; Tk = V * Tk / (V) if False else (V - dV) * Tk / V; lastbuy = ms(t)
        else:
            Tk = Tk + t["tok"]; V = (V * (Tk - t["tok"])) / Tk
        path.append((ms(t), val(V, Tk), lastbuy))
        if ms(t) - fill > 600_000: break
    return dict(path=path, fill=fill, over=(kk / Tk2 / Tk2 if False else (S[kf][0] / S[kf][1]) / (S[k0][0] / S[k0][1])) - 1, ahead=kf - k0)
def pnl_timer(R, H, B):
    v = [x for x in R["path"] if x[0] - R["fill"] <= H * 1000][-1][1]; return v - B - 2 * TX
def pnl_tp(R, tp, cap, B):
    for i, (mt, v, lb) in enumerate(R["path"]):
        if mt - R["fill"] > cap * 1000: break
        if v >= B * (1 + tp):
            land = [x for x in R["path"] if x[0] <= mt + 50][-1][1]; return land - B - 2 * TX
    return pnl_timer(R, cap, B)
def pnl_stall(R, idle, cap, B):
    p = R["path"]
    for i, (mt, v, lb) in enumerate(p):
        if mt - R["fill"] > cap * 1000: break
        nxt = p[i + 1][0] if i + 1 < len(p) else mt + 10_000
        if nxt - lb > idle * 1000 and mt - R["fill"] > 0:
            tsell = lb + idle * 1000 + 50; return [x for x in p if x[0] <= tsell][-1][1] - B - 2 * TX
    return pnl_timer(R, cap, B)
def pnl_trail(R, drop, cap, B):
    pk = -1
    for mt, v, lb in R["path"]:
        if mt - R["fill"] > cap * 1000: break
        pk = max(pk, v)
        if v <= pk * (1 - drop) and pk > B: return [x for x in R["path"] if x[0] <= mt + 50][-1][1] - B - 2 * TX
    return pnl_timer(R, cap, B)
RULES = [(f"hold{h}s", lambda R, B, h=h: pnl_timer(R, h, B)) for h in (0.3, 0.5, 1, 1.5, 2, 3, 5, 10, 30)]
RULES += [(f"tp{int(tp*100)}_cap{c}", lambda R, B, tp=tp, c=c: pnl_tp(R, tp, c, B)) for tp in (0.05, 0.10, 0.15, 0.20, 0.30) for c in (2, 5, 10)]
RULES += [(f"stall{i}s_cap{c}", lambda R, B, i=i, c=c: pnl_stall(R, i, c, B)) for i in (0.3, 0.5, 1, 2) for c in (5, 10)]
RULES += [(f"trail{int(d*100)}_cap{c}", lambda R, B, d=d, c=c: pnl_trail(R, d, c, B)) for d in (0.03, 0.05, 0.10) for c in (5, 10)]
if __name__ == "__main__":
    last = POS[-100:]
    print(f"3GzBLpxT positions found: {len(POS)} (R1–R4); showing the last {len(last)}\n")
    print("time PKT     token    curve  age   grp in slot  its SOL in  hold     PnL(cash)  followers 1s / 5s (SOL)  peak 5s vs grp fill  price at its sell")
    rows = []
    for p in last:
        tr = T[p["m"]]; S = states(p["m"])
        k0 = next((k for k, t in enumerate(tr) if t["user"] in G and t["buy"]), None)
        if S is None or k0 is None: print(f"{time.strftime('%m-%d %H:%M', time.gmtime(p['bt'] + 18000))}  {p['m'][:6]}  (no price data)"); continue
        t0 = ms(tr[k0]); p0 = S[k0][0] / S[k0][1]
        ingrp = len({t["user"] for t in tr if t["user"] in G and t["buy"] and t["s"] == tr[k0]["s"]})
        f1 = sum(S[k][0] - S[k - 1][0] for k in range(k0 + 1, len(tr)) if tr[k]["buy"] and tr[k]["user"] not in G and ms(tr[k]) - t0 <= 1000)
        f5 = sum(S[k][0] - S[k - 1][0] for k in range(k0 + 1, len(tr)) if tr[k]["buy"] and tr[k]["user"] not in G and ms(tr[k]) - t0 <= 5000)
        pk = max(((S[k][0] / S[k][1]) / p0, (ms(tr[k]) - t0) / 1000) for k in range(k0, len(tr)) if ms(tr[k]) - t0 <= 5000)
        ws = next((k for k in range(k0, len(tr)) if tr[k]["user"] == W and not tr[k]["buy"]), None)
        atsell = (S[ws - 1][0] / S[ws - 1][1]) / p0 if ws else None
        age = (tr[k0]["s"] - tr[0]["s"]) * 0.212
        rows.append(p)
        print(f"{time.strftime('%m-%d %H:%M', time.gmtime(p['bt'] + 18000))}  {p['m'][:6]} {'quote' if p['quote'] else 'SOL  '} {age:5.0f}s  {ingrp} wallets    {p['sol_in']:5.2f}   "
              f"{(p['hold'] or 0) / 60:5.1f}m  {p['cash']:+7.3f}{'' if p['closed'] else ' OPEN'}   {f1:6.2f} / {f5:6.2f}            {pk[0]:4.2f}x at {pk[1]:3.1f}s           {atsell if atsell else float('nan'):4.2f}x")
    cl = [p for p in last if p["closed"]]
    print(f"\nlast 100: closed {len(cl)}, cash PnL closed {sum(p['cash'] for p in cl):+.2f} SOL, win {sum(p['cash'] > 0 for p in cl) / max(len(cl), 1):.0%}, open {len(last) - len(cl)} (cash paid {sum(p['cash'] for p in last if not p['closed']):+.2f})")
    # strategy replay
    print("\n=== COPY THE GROUP'S FIRST BUY + OUR OWN EXIT (1 SOL). Choose on R1+R2 (train), test on R3+R4.")
    res = collections.defaultdict(list)
    for p in POS:
        for Tms in (35, 50, 75):
            for var in ("keep", "dropbig", "drop2"):
                R = replay(p["m"], Tms, 1.0, var)
                if R is None: continue
                for name, f in RULES: res[(Tms, var, name)].append(("train" if p["run"] in ("R1", "R2") else "test", f(R, 1.0), R["over"]))
    for Tms in (35, 50, 75):
        for var in ("keep", "dropbig", "drop2"):
            best = max(RULES, key=lambda r: sum(x[1] for x in res[(Tms, var, r[0])] if x[0] == "train"))[0]
            def s(name, part): v = [x[1] for x in res[(Tms, var, name)] if x[0] == part]; return sum(v), len(v), sum(1 for x in v if x > 0) / max(len(v), 1)
            tr_, te_ = s(best, "train"), s(best, "test")
            h1tr, h1te = s("hold1s", "train"), s("hold1s", "test")
            over = statistics.median([x[2] for x in res[(Tms, var, "hold1s")]])
            print(f"  T={Tms:2d} ms {var:7s} | we pay +{over:4.0%} vs group | best on train: {best:15s} train {tr_[0]:+6.2f} ({tr_[1]}, {tr_[2]:.0%} up) → TEST {te_[0]:+6.2f} ({te_[1]}, {te_[2]:.0%} up) | plain 1 s hold: train {h1tr[0]:+6.2f} test {h1te[0]:+6.2f}")
    json.dump({f"{k[0]}|{k[1]}|{k[2]}": v for k, v in res.items()}, open("strategy.json", "w"))
