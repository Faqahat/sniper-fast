#!/usr/bin/env python3
"""verify_dip / vx_tolstress: competitor-reaction stress with MEASURED tolerances. For each fast dip-backrunner wallet
(out/fast_backrunners.json), tau_w = 95th percentile of (price before its tx / price right after the dip sell) over its
SUCCESSFUL backrun buys in the whole sample (bk_tolerance.json). In the replay with our buy, such a wallet's buy within the
hold is dropped if the replayed price before it exceeds tau_w x the post-dip price (its own guard would fail).
Other followers: the claim's imputed slippage. Claim spec otherwise (exit buy slot + 4, 75 ms, TXC 0.0008).
usage: python3 -I -B vx_tolstress.py <keys.json> <out.json>"""
import sys, os, json, gzip, zlib, collections
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import vx_replay as R
GRID = (0, 10, 20, 25, 30, 35, 40, 45, 50, 60, 75, 100)
TAU = {}
def init2(tau):
    R.init("mine"); TAU.update(tau)
def rt(tr, ke, fr, s_buy, p_dip, use_tau, SL=75.0, H=4):
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(R.B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q
    E = s_buy + H; frs = fr; ndrop = 0
    for t in tr[ke:]:
        if t["s"] > E or (t["s"] == E and (SL <= 0 or R.pos_ms(t) >= SL)): break
        if t["buy"] and use_tau and t["payer"] in TAU and (V / T) / p_dip > TAU[t["payer"]]: ndrop += 1; continue
        if t["buy"] and use_tau and t["payer"] in TAU:                  # measured-tolerance wallet: no extra random slack
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
    return so * (1 - frs) / 1e9 - R.B, ndrop
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
                s_in = tr[ke - 1]["s"]
                a, _ = rt(tr, ke, fr, s_in, p_dip, False); b2, nd = rt(tr, ke, fr, s_in, p_dip, True)
                res[str(Lm)] = (round(a, 6), round(b2, 6), nd)
            out[f"{m}|{age}"] = res
    return out
if __name__ == "__main__":
    keys = json.load(open(sys.argv[1])); outp = sys.argv[2]
    bk = json.load(open(os.path.join(HERE, "out", "bk_tolerance.json")))
    okr = collections.defaultdict(list)
    for payer, kind, ratio, nb, dly, m, age in bk:
        if kind == "ok": okr[payer].append(ratio)
    pooled = sorted(x for v in okr.values() for x in v); p95 = pooled[int(0.95 * len(pooled))]
    tau = {}
    for u in json.load(open(os.path.join(HERE, "out", "fast_backrunners.json"))):
        v = sorted(okr.get(u, []))
        tq = float(os.environ.get("TAUQ", "0.95"))
        tau[u] = v[min(len(v) - 1, int(tq * len(v)))] if len(v) >= 20 else p95
    json.dump(tau, open(os.path.join(HERE, "out", os.environ.get("TAUFILE", "tau_backrunners.json")), "w"), indent=0)
    print("tau: pooled p95", round(p95, 4), "| per wallet: " + " ".join(f"{u[:6]}:{t:.3f}" for u, t in sorted(tau.items(), key=lambda kv: kv[1])[:12]), "...")
    R.init("mine")
    by = collections.defaultdict(list)
    for m, a in keys:
        c = R.G["L"][m]; by[(c["run"], zlib.crc32(m.encode()) % 256)].append((m, a))
    res = {}
    with Pool(8, initializer=init2, initargs=(tau,)) as p:
        for o in p.imap_unordered(work, sorted(by.items())): res.update(o)
    json.dump(res, open(outp, "w"))
    RT = -0.5 * 0.0125 * 2 - 0.0016
    for Lm in GRID:
        a = sum((v[str(Lm)][0] - 0.0016) if str(Lm) in v else RT for v in res.values())
        b2 = sum((v[str(Lm)][1] - 0.0016) if str(Lm) in v else RT for v in res.values())
        nd = sum(v[str(Lm)][2] for v in res.values() if str(Lm) in v)
        print(f"  L{Lm:3d}: claim spec {a:+7.2f} | backrunners with measured tolerance {b2:+7.2f} (their buys dropped: {nd})")
