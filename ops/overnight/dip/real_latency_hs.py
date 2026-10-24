#!/usr/bin/env python3
# REAL-latency estimate for the current dip version (direct-only picks, real follower limits, HOLD_SLOTS exit (default 2), spacing 5), with
# the independent check's method (verify_dip/combo.py): price every pick on a grid of proxy delays L' (0..300 ms, step 5),
# then the expected P&L at a REAL delay Lr = average of P&L(Lr + d) over d = proxy gap - real gap, measured on the shadow
# engine's real arrivals (verify_dip/out/proxy_anchors_mine.json: pairs with real gap within +-7.5 ms of Lr).
# Unguarded and with the 2% guard. Local data only.
# usage: python3 -I real_latency.py sel_oof_real2_filter.jsonl LAT_MODEL [more models]
import sys, os, json, gzip, collections
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "1"
os.environ.setdefault("SELL_LAT", "75"); os.environ.setdefault("SLIPIMP", "1"); os.environ.setdefault("DIP_REAL_SLIP", "1")
os.environ.setdefault("DIP_B", "0.5"); os.environ.setdefault("DIP_HS", "2")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import dipbuy5 as D
from multiprocessing import Pool
GRID = list(range(0, 305, 5)); HS = int(os.environ.get("HOLD_SLOTS", "2"))
SELF, MODELS = sys.argv[1], sys.argv[2:]
picks = collections.defaultdict(list)
for l in open(SELF):
    r = json.loads(l)
    if r["LAT"] in MODELS: picks[r["LAT"]].append(r)
need = collections.defaultdict(set)
for L, v in picks.items():
    for r in v: need[r["m"]].add(r["age"])
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
            fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
            p_after = t["vsol"] / t["vtok"]; a0 = D.arr(t); row = {}
            for Lp in GRID:
                ke = k + 1
                while ke < len(tr) and D.arr(tr[ke]) < a0 + Lp: ke += 1
                if ke >= len(tr): continue
                s_land = int((a0 + Lp) // D.SMS)
                p = D.rt_fixed(tr, ke, fr, HS, s_land)
                px = (tr[ke - 1]["vsol"] / tr[ke - 1]["vtok"]) / p_after
                row[Lp] = (p, p if px <= 1.02 else -0.0002)
            out[(m, age)] = row
    return out
if __name__ == "__main__":
    res = {}
    with Pool(6) as p:
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
    for L in MODELS:
        keys = [(r["m"], r["age"]) for r in picks[L] if (r["m"], r["age"]) in res]
        FL = json.load(open(os.environ["FLAGS"])) if os.environ.get("FLAGS") else {}
        SH = int(os.environ.get("ROUTED_SHIFT", "0"))
        def tot(Lp, g):
            # outside the grid / no trade after: the trade does not happen (0). Routed triggers (FLAGS == 0) are seen SH ms
            # later on the executed feed, so they are priced SH ms later.
            s = 0.0
            for k in keys:
                L2 = Lp + (SH if FL.get(f"{k[0]}|{k[1]}") == 0 else 0)
                if L2 in res[k]: s += res[k][L2][g]
            return s
        print(f'model "{L} ms" direct-only picks: {len(picks[L])} (priced {len(keys)})')
        print("  proxy grid, unguarded: " + " ".join(f"L{x}:{tot(x, 0):+.1f}" for x in (0, 20, 35, 50, 75, 100)))
        print("  proxy grid, guarded:   " + " ".join(f"L{x}:{tot(x, 1):+.1f}" for x in (0, 20, 35, 50, 75, 100)))
        for Lr in (20, 35, 50, 75):
            ds = [p[1] - p[0] for p in pairs if abs(p[0] - Lr) <= 7.5]
            w = collections.Counter(min(300, max(0, int(round((Lr + d) / 5.0)) * 5)) for d in ds)
            un = sum(c * tot(x, 0) for x, c in w.items()) / len(ds); gu = sum(c * tot(x, 1) for x, c in w.items()) / len(ds)
            print(f"  REAL delay {Lr:3d} ms -> expected P&L per ~33.5 h: unguarded {un:+6.2f} | guarded {gu:+6.2f}   ({len(ds)} measured pairs)")
