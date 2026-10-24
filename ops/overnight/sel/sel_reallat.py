#!/usr/bin/env python3
# REAL-latency estimate for a selection + TP/SL/time-limit exit (local only), same method as dip/real_latency.py (the
# checker's): price every pick on a grid of proxy delays L' (0..300 ms, step 5) with the chosen exit and the 2% guard, then the
# expected P&L at a REAL delay Lr = average over the measured proxy-vs-real gap errors (verify_dip/out/proxy_anchors_mine.json).
# usage: python3 -I sel_reallat.py PICKS.jsonl EXIT [ROUTED_SHIFT_MS]   (PICKS rows: {"m", "age"}; EXIT like T,0.08,0.05,6,1 or H,4)
import sys, os, json, collections
os.environ.setdefault("RP_PHASEA_R2", "phaseA_sel"); os.environ.setdefault("SELL_LAT", "75"); os.environ.setdefault("SLIPIMP", "1")
os.environ.setdefault("DIP_REAL_SLIP", "1"); os.environ.setdefault("DIP_B", "0.5"); os.environ.setdefault("DIP_LATS", "35,50,75"); os.environ.setdefault("SEL_SLIP", "1")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import selexit2 as D
from multiprocessing import Pool
GRIDL = list(range(0, 305, 5))
PF = sys.argv[1]; _x = sys.argv[2].split(","); EX = (_x[0],) + tuple(float(v) if "." in v else int(v) for v in _x[1:]); EI = [tuple(g) for g in D.GRID].index(EX)
SH = int(sys.argv[3]) if len(sys.argv) > 3 else 0
need = collections.defaultdict(set)
for l in open(PF):
    r = json.loads(l); need[r["m"]].add(r["age"])
byb = collections.defaultdict(set)
for m in need: byb[(D.L[m]["run"], D.rp.bucket(m))].add(m)
def work(key):
    run, b = key; out = {}
    for m, tr in D.rp.read_bucket(run, b, byb[key]).items():
        S0 = D.L[m]["slot"]
        for k, t in enumerate(tr):
            if t["buy"] or t["sol"] < D.MIN_SELL or t.get("syn"): continue
            age = round((t["s"] - S0) * D.SMS / 1000, 2)
            if age not in need[m]: continue
            fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4; p_after = t["vsol"] / t["vtok"]; a0 = D.arr(t); row = {}
            for Lp in GRIDL:
                ke = k + 1
                while ke < len(tr) and D.arr(tr[ke]) < a0 + Lp: ke += 1
                if ke >= len(tr): continue
                s_land = int((a0 + Lp) // D.SMS)
                p = D.exit_grid(*D.rt_path(tr, ke, fr, s_land))[EI]
                px = (tr[ke - 1]["vsol"] / tr[ke - 1]["vtok"]) / p_after
                row[Lp] = (p, p if px <= 1.02 else -0.0002)
            out[(m, age)] = row
    return out
if __name__ == "__main__":
    res = {}
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=2): res.update(o)
    an = json.load(open("/home/moiz/sniper/ops/overnight/verify_dip/out/proxy_anchors_mine.json"))["anchors"]
    byl = collections.defaultdict(list)
    for a in an: byl[a[0]].append(a)
    pairs = []
    for m, v in byl.items():
        v.sort(key=lambda a: a[3])
        for x in range(len(v)):
            for y in range(x + 1, len(v)):
                dr = v[y][3] - v[x][3]
                if dr > 320: break
                pairs.append((dr, v[y][4] - v[x][4]))
    keys = list(res)
    def tot(Lp, g):
        s = 0.0
        for k in keys:
            L2 = Lp + SH
            if L2 in res[k]: s += res[k][L2][g]
        return s
    print(f"picks {sum(len(v) for v in need.values())} (priced {len(keys)}) | exit '{D.GRID[EI]}' | routed shift {SH} ms")
    print("  proxy grid, guarded: " + " ".join(f"L{x}:{tot(x, 1):+.2f}" for x in (0, 20, 35, 50, 75, 100)))
    for Lr in (20, 35, 50, 75):
        ds = [p[1] - p[0] for p in pairs if abs(p[0] - Lr) <= 7.5]
        w = collections.Counter(min(300, max(0, int(round((Lr + d) / 5.0)) * 5)) for d in ds)
        gu = sum(c * tot(x, 1) for x, c in w.items()) / len(ds)
        print(f"  REAL delay {Lr:3d} ms -> expected P&L (guarded): {gu:+7.2f}   ({len(ds)} measured pairs)")
