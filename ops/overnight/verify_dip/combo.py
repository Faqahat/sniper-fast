#!/usr/bin/env python3
"""verify_dip / combo: combined realistic re-pricing of a pick list. Per pick and proxy delay L' (0..300 ms, step 5):
  - buy slot = slot of our own proxy arrival (fixes the claim's 'slot of the last trade ahead');
  - fast dip-backrunners (out/fast_backrunners.json) keep their buy only if the replayed price before it is within their
    measured tolerance tau (95th pct of accepted price / post-dip price, out/tau_backrunners.json); other followers: the
    claim's imputed slippage;
  - exit buy slot + 4 at 75 ms; pump fees from the events.
Then the expected PnL at a REAL delay L = average over d of PnL(L + d), d = proxy gap - real gap measured on the shadow
engine's real arrivals (pairs with real gap within +-7.5 ms of L). Reported at 0.0008 / 0.002 / 0.003 SOL per tx.
usage: python3 -I -B combo.py <picks json: cv_repro output> <LAT key> <label>"""
import sys, os, json, gzip, zlib, collections
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import vx_replay as R
GRID = list(range(0, 305, 5))
TAU = {}
def init2(tau):
    R.init("mine"); TAU.update(tau)
    if os.environ.get("DIPB"): R.B = float(os.environ["DIPB"])
def rt(tr, ke, fr, s_buy, p_dip, SL=75.0, H=4):
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(R.B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q
    E = s_buy + H; frs = fr
    for t in tr[ke:]:
        if t["s"] > E or (t["s"] == E and (SL <= 0 or R.pos_ms(t) >= SL)): break
        if t["buy"] and t["payer"] in TAU:
            if (V / T) / p_dip > TAU[t["payer"]]: continue
            d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        elif t["buy"] and not t["syn"]:
            d = T * t["sol"] // (V + t["sol"])
            if d < t["tok"] / (1 + R.slack(t["sig"])): continue
            V += t["sol"]; T -= d
        elif t["buy"]:
            d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else:
            so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        frs = R.fbps(t)
        if V >= 110e9 or T <= R.VT_DONE: break
    so = V * q // (T + q)
    return so * (1 - frs) / 1e9 - R.B
def work(arg):
    (tag, b), keys = arg
    data = json.load(gzip.open(os.path.join(R.WORK, tag, f"b{b:03d}.json.gz"), "rt")); out = {}
    want = collections.defaultdict(set)
    for m, a in keys: want[m].add(a)
    for m, ages in want.items():
        c = R.G["L"][m]; tr, _ = R.tape(data[m]["t"]); S = c["slot"]
        for k, t in enumerate(tr):
            if t["buy"] or t["syn"] or t["sol"] < R.MIN_SELL: continue
            age = round((t["s"] - S) * R.SMS / 1000, 2)
            if age not in ages: continue
            ages.discard(age)
            fr = R.fbps(t); a0 = R.arr(t); p_dip = t["vsol"] / t["vtok"]; res = {}
            for Lm in GRID:
                ke = k + 1
                while ke < len(tr) and R.arr(tr[ke]) < a0 + Lm: ke += 1
                if ke >= len(tr): continue
                res[str(Lm)] = round(rt(tr, ke, fr, int((a0 + Lm) // R.SMS), p_dip), 6)
            out[f"{m}|{age}"] = res
    return out
if __name__ == "__main__":
    picks, LAT, label = sys.argv[1], sys.argv[2], sys.argv[3]
    sel = json.load(open(picks))[LAT]["sel"]; keys = [(s["m"], s["age"]) for s in sel]
    tau = json.load(open(os.path.join(HERE, "out", os.environ.get("TAUFILE", "tau_backrunners.json"))))
    R.init("mine")
    by = collections.defaultdict(list)
    for m, a in keys: by[(R.G["L"][m]["run"], zlib.crc32(m.encode()) % 256)].append((m, a))
    res = {}
    with Pool(8, initializer=init2, initargs=(tau,)) as p:
        for o in p.imap_unordered(work, sorted(by.items())): res.update(o)
    an = json.load(open(os.path.join(HERE, "out", "proxy_anchors_mine.json")))["anchors"]
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
    if os.environ.get("DIPB"): R.B = float(os.environ["DIPB"])
    RT = -R.B * 0.0125 * 2
    def tot(Lp, txc): return sum((v[str(Lp)] if str(Lp) in v else RT) - 2 * txc for v in res.values())
    print(f"{label}: {len(sel)} picks (priced {len(res)})")
    print("  proxy delay grid, 0.0008/tx: " + " ".join(f"L{L}:{tot(L, 0.0008):+.1f}" for L in (0, 20, 35, 50, 75, 100)))
    for Lr in (20, 35, 50, 75):
        ds = [p[1] - p[0] for p in pairs if abs(p[0] - Lr) <= 7.5]
        w = collections.Counter(min(300, max(0, int(round((Lr + d) / 5.0)) * 5)) for d in ds)
        cells = [f"{txc}/tx {sum(c * tot(L, txc) for L, c in w.items()) / len(ds):+6.2f}" for txc in (0.0008, 0.002, 0.003)]
        print(f"  REAL delay {Lr:3d} ms -> expected PnL: " + " | ".join(cells))
    json.dump(res, open(os.path.join(HERE, "out", f"combo_{label}.json"), "w"))
