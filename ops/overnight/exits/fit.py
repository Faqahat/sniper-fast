#!/usr/bin/env python3
# READ-ONLY, offline. Fit an explicit AKbot-style exit rule to the wallets' REAL behaviour on tokens with market paths.
# Fidelity score = mean over tokens of the event-averaged |remaining position (actual) - remaining position (replayed)|
# (0 = identical sell schedule), reported with the per-token PnL correlation and totals.
# usage: python3 -I fit.py [subset]   subset: all | 9Sh2fd | DGmspi | dev:<prefix>
import sys, os, json, pickle, itertools, statistics, collections, math, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from sim import simulate
from replay import corr

def prep(c):
    """cache per token: unique slots from the buy on, and the actual remaining-position curve on them."""
    if "_slots" in c: return
    W = WALLETS[c["w"]]; tr = c["tr"]
    kb = next(k for k, t in enumerate(tr) if t["sig"] == c["rt"]["legs"][0]["sig"] and t["user"] == W)
    slots = sorted({t["s"] for t in tr[kb:]})
    act = [(l["slot"], l["frac"]) for l in c["rt"]["legs"] if l["side"] == "sell"]
    c["_slots"] = slots; c["_act"] = act; c["_actrem"] = rem_on(slots, act)

def rem_on(slots, sells):
    out = []; r = 1.0; j = 0; sells = sorted(sells)
    for s in slots:
        while j < len(sells) and sells[j][0] <= s: r *= (1 - sells[j][1]); j += 1
        out.append(r)
    return out

def schedule_dist(c, sim_sells):
    """slot-averaged |rem_actual - rem_sim| between the buy and the later of the two final sells."""
    prep(c); slots = c["_slots"]
    sim = [(s["slot"], s["frac"]) for s in sim_sells]
    end = max(c["_act"][-1][0] if c["_act"] else slots[0], sim[-1][0] if sim else slots[0])
    n = sum(1 for s in slots if s <= end) or 1
    sr = rem_on(slots[:n], sim)
    return sum(abs(a - b) for a, b in zip(c["_actrem"][:n], sr)) / n

def evaluate(cases, rule):
    d = []; a = []; p = []
    for c in cases:
        try: s = simulate(c["rt"], WALLETS[c["w"]], c["tr"], c["dev"], rule)
        except StopIteration: continue
        d.append(schedule_dist(c, s["sells"])); a.append(c["rt"]["pnl"]); p.append(s["pnl"])
    return dict(dist=statistics.mean(d), mae=statistics.mean(abs(x - y) for x, y in zip(a, p)), corr=corr(a, p), act=sum(a), sim=sum(p), n=len(d))
OBJ = os.environ.get("OBJ", "dist")

def make_rule(L, Ld, g1, s, step, dd_act, dd, dd_f, sl, to, fd, ms=0.01, mir=0, tof="buy", s1=None):
    r = dict(min_sell_sol=ms, timeout_from=tof)
    if L: r["lightning"] = dict(frac=L, delay=Ld)
    if g1 is not None:
        r["tp"] = [(g1 + k * step, (s1 if (k == 0 and s1 is not None) else s)) for k in range(8)]; r["tp_repeat"] = dict(step=step / (1 + g1 + 7 * step), frac=s)
    if dd: r["drawdown"] = dict(act=dd_act, dd=dd, frac=dd_f)
    if sl: r["stop_loss"] = sl
    if to: r["timeout_s"] = to
    if fd or mir: r["follow_dev"] = dict(clear_at=fd or 2.0, mirror=mir)
    return r

if __name__ == "__main__":
    sub = sys.argv[1] if len(sys.argv) > 1 else "all"
    cases = pickle.load(open(os.path.join(EXITS, "cache", "cases.pkl"), "rb"))
    if sub in WALLETS: cases = [c for c in cases if c["w"] == sub]
    elif sub.startswith("dev:"): cases = [c for c in cases if any(d.startswith(sub[4:]) for d in c["dev"])]
    print(f"subset {sub}: {len(cases)} tokens", flush=True)
    t0 = time.time()
    base = dict(L=0.5, Ld=6, g1=0.25, s=0.5, step=0.2, dd_act=0.2, dd=0.08, dd_f=0.25, sl=0.12, to=None, fd=0.99)
    grids = [
        dict(L=[0, 0.1, 0.25, 0.35, 0.5, 0.6, 0.65, 0.75], Ld=[1, 2, 6], sl=[0.08, 0.10, 0.12, 0.15, 0.2, None], to=[None, 60], fd=[None, 0.5, 0.99], mir=[0, 1], tof=["buy", "last_tp"]),
        dict(g1=[0.15, 0.2, 0.25, 0.3, 0.4], s=[0.15, 0.25, 0.33, 0.5, 0.6], step=[0.1, 0.15, 0.2, 0.3], dd=[0, 0.05, 0.08, 0.12], dd_f=[0.1, 0.15, 0.25], dd_act=[0.15, 0.3]),
        dict(L=[0, 0.1, 0.25, 0.35, 0.5, 0.6, 0.65, 0.75], Ld=[1, 2, 6], sl=[0.08, 0.10, 0.12, 0.15, 0.2, None], to=[None, 60], fd=[None, 0.5, 0.99], mir=[0, 1], tof=["buy", "last_tp"]),
    ]
    best = dict(base); hist = []
    for gi, g in enumerate(grids):
        keys = list(g); scored = []
        for vals in itertools.product(*[g[k] for k in keys]):
            prm = dict(best); prm.update(dict(zip(keys, vals)))
            if prm["dd"] == 0 and (prm["dd_f"] != g.get("dd_f", [prm["dd_f"]])[0] or prm["dd_act"] != g.get("dd_act", [prm["dd_act"]])[0]): continue
            ev = evaluate(cases, make_rule(**prm)); scored.append((ev[OBJ] if OBJ != "corr" else -ev["corr"], -ev["corr"], prm, ev))
        scored.sort(key=lambda x: (x[0], x[1]))
        best = scored[0][2]; hist.append(scored[:5])
        print(f"stage {gi + 1}: {len(scored)} rules, {time.time() - t0:.0f}s; best dist {scored[0][3]['dist']:.4f} mae {scored[0][3]['mae']:.4f} corr {scored[0][3]['corr']:.3f} "
              f"actual {scored[0][3]['act']:+.2f} sim {scored[0][3]['sim']:+.2f}  params {best}", flush=True)
    # also: the most PROFITABLE rule in the same family on these entries (for reference, in-sample)
    json.dump(dict(subset=sub, n=len(cases), best=best, top=[[dict(dist=x[0], corr=-x[1], prm=x[2], ev=x[3]) for x in h] for h in hist]),
              open(os.path.join(EXITS, "fits", f"fit_{OBJ}_{sub.replace(':', '_')}.json"), "w"), indent=1)
