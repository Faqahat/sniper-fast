#!/usr/bin/env python3
# READ-ONLY, offline. Fit the explicit AKbot-style exit rule (lightning sell, take-profit ladder, drawdown trims, stop loss,
# dev-follow clear, timeout) per copy-trade CONFIG (= wallet x followed dev), per wallet, and globally, on the wallets' real
# entries with market paths; replay and compare with the real per-token PnL. Writes exit_rules.json + fit_report.txt.
import sys, os, json, pickle, itertools, statistics, collections, math, time
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from sim import simulate
from replay import corr
from fit import prep, schedule_dist, make_rule

GRID1 = dict(L=[0, 0.1, 0.25, 0.35, 0.5, 0.6, 0.65, 0.75, 0.9], Ld=[1, 2, 6], sl=[0.06, 0.08, 0.10, 0.12, 0.15, 0.2, None], to=[None, 60],
             fd=[None, 0.5, 0.99], mir=[0, 1], tof=["buy", "last_tp"])
GRID2 = dict(g1=[0.15, 0.2, 0.25, 0.3, 0.4, 0.5], s1=[0.15, 0.25, 0.33, 0.5, 0.6, 0.75], s=[0.1, 0.15, 0.25, 0.33, 0.5, 0.6], step=[0.1, 0.15, 0.2, 0.3])
GRID3 = dict(dd=[0, 0.05, 0.08, 0.12], dd_f=[0.05, 0.1, 0.15, 0.25], dd_act=[0.1, 0.2, 0.3])
BASE = dict(L=0.5, Ld=6, g1=0.25, s=0.33, s1=0.33, step=0.2, dd_act=0.2, dd=0.08, dd_f=0.15, sl=0.10, to=None, fd=0.99, mir=0, tof="buy")
CASES = None

def ev(cases, rule):
    d = []; a = []; p = []
    for c in cases:
        try: s = simulate(c["rt"], WALLETS[c["w"]], c["tr"], c["dev"], rule)
        except StopIteration: continue
        d.append(schedule_dist(c, s["sells"])); a.append(c["rt"]["pnl"]); p.append(s["pnl"])
    return dict(dist=statistics.mean(d), mae=statistics.mean(abs(x - y) for x, y in zip(a, p)), corr=corr(a, p) if len(a) > 2 else float("nan"),
                act=sum(a), sim=sum(p), n=len(d), neg_sim=-sum(p))

def staged(args):
    name, idx, obj = args
    cases = [CASES[i] for i in idx]
    best = dict(BASE); log = []
    for g in (GRID1, GRID2, GRID3, GRID1, GRID2, GRID3):
        keys = list(g); sc = []
        for vals in itertools.product(*[g[k] for k in keys]):
            prm = dict(best); prm.update(dict(zip(keys, vals)))
            if "dd" in g and prm["dd"] == 0 and (prm["dd_f"] != g["dd_f"][0] or prm["dd_act"] != g["dd_act"][0]): continue
            e = ev(cases, make_rule(**prm)); sc.append((e[obj], e["mae"], prm, e))
        sc.sort(key=lambda x: (x[0], x[1])); best = sc[0][2]; log.append(sc[0][3])
    return name, best, log[-1]

def init(path):
    global CASES
    CASES = pickle.load(open(path, "rb"))
    for c in CASES: prep(c)

if __name__ == "__main__":
    obj = sys.argv[1] if len(sys.argv) > 1 else "dist"
    path = os.path.join(EXITS, "cache", "cases.pkl")
    init(path)
    groups = collections.defaultdict(list)
    for i, c in enumerate(CASES): groups[c["cfg"]].append(i)
    MINCFG = int(os.environ.get("MINCFG", "4"))
    jobs = [(g, idx, obj) for g, idx in groups.items() if len(idx) >= MINCFG]
    for w in WALLETS: jobs.append((f"wallet:{w}", [i for i, c in enumerate(CASES) if c["w"] == w], obj))
    if not os.environ.get("NOGLOBAL"): jobs.append(("global", list(range(len(CASES))), obj))
    print(f"objective {obj}: {len(CASES)} tokens; {len(jobs)} fits: " + ", ".join(f"{j[0]}({len(j[1])})" for j in jobs), flush=True)
    t0 = time.time(); out = {}
    with Pool(6, initializer=init, initargs=(path,)) as pool:
        for name, best, e in pool.imap_unordered(staged, sorted(jobs, key=lambda j: -len(j[1]))):
            out[name] = dict(params=best, fit=e); print(f"  [{time.time() - t0:5.0f}s] {name:22s} n={e['n']:3d} dist {e['dist']:.3f} mae {e['mae']:.3f} corr {e['corr']:.3f} "
                                                      f"real {e['act']:+.2f} replay {e['sim']:+.2f} | {best}", flush=True)
    json.dump(out, open(os.path.join(EXITS, "fits", f"fit_all_{obj}{os.environ.get('TAG', '')}.json"), "w"), indent=1)
