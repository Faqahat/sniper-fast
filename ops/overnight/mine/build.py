#!/usr/bin/env python3
# PATTERN MINE (read-only): every trade >= 0.3 SOL in a token's first 15 min (R2 + R3 SOL curves) -> ~40 features known at that moment
# + labels = PnL of OUR 1 SOL buy landing 75 ms later (constant-product replay with our impact, fees 1.25%/side + 0.0015 SOL/tx x2),
# sold after 1 / 3 / 10 / 30 s (followers kept) and after 3 s with followers in the 2 slots after us dropped (pessimistic).
import os, sys, json, re, pickle, collections, math, numpy as np
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def ms(s, i): return s * 212.0 + i / max(SS.get(s, 0), i + 1, 380) * 212.0
L = rp.load_launches(); REP = pickle.load(open("rep.pkl", "rb"))
HOST = {}
for l in open("/home/moiz/sniper/ops/overnight/minhold/tw/meta.jsonl"):
    try: r = json.loads(l); HOST[r["m"]] = r.get("host")
    except Exception: pass
TWH = {"metadata.j7tracker.io", "meta.uxento.io", "m.rapidlaunch.io"}
byb = collections.defaultdict(set)
for m, c in L.items():
    if c["run"] in ("R2", "R3") and not c.get("mayhem"): byb[(c["run"], rp.bucket(m))].add(m)
FEE = 0.0125; TX = 0.0015; B = 1.0; HOLDS = (1, 3, 10, 30)
FEAT = ["age", "vsol", "rel_peak", "ch1", "ch5", "ch15", "ch60", "buy1", "sell1", "buy5", "sell5", "buy15", "sell15", "buy60", "sell60", "nb5", "ns5", "nb60", "ns60",
        "ntr", "gap", "trig_buy", "trig_sol", "trig_rep", "trig_win", "trig_known", "trig_dev", "dev_buy", "dev_sold", "bundle", "w2", "w10", "w60", "l10", "wnet10",
        "rep_last5", "uniq_buyers", "max_buy", "hour", "tweet_host", "first_after_quiet"]
def label(tr, k, t0, drop2):
    kf = k
    while kf + 1 < len(tr) and ms(tr[kf + 1]["s"], tr[kf + 1]["i"]) - t0 <= 75: kf += 1
    V, Tk = tr[kf]["vsol"], tr[kf]["vtok"]
    if V <= 0 or V > 112e9: return None
    X = B * 1e9 / (1 + FEE); kk = V * Tk; V2 = V + X; Tk2 = kk / V2; q = Tk - Tk2; V, Tk = V2, Tk2; fill = t0 + 75; fs = tr[kf]["s"]
    val = lambda V, Tk: (V - V * Tk / (Tk + q)) * (1 - FEE) / 1e9
    path = [(fill, val(V, Tk))]
    for t in tr[kf + 1:]:
        mt = ms(t["s"], t["i"])
        if mt - fill > 31_000: break
        if t["buy"]:
            if drop2 and t["s"] - fs <= 2: continue
            V2 = V + t["sol"]; Tk = V * Tk / V2; V = V2
        else: Tk2 = Tk + t["tok"]; V = V * Tk / Tk2; Tk = Tk2
        path.append((mt, val(V, Tk)))
    return [[p for m_, p in path if m_ - fill <= h * 1000][-1] - B - 2 * TX for h in HOLDS]
def work(key):
    run = key[0]; rep = REP["for_R2" if run == "R2" else "for_R3"]
    win = lambda u: rep.get(u, (0, 0, 0))
    good = lambda u: u in rep and rep[u][0] >= 2 and rep[u][1] >= 0.5
    bad = lambda u: u in rep and rep[u][0] <= -1
    rows = []; labs = []; meta = []
    for m, tr in rp.read_bucket(run, key[1], byb[key]).items():
        if not tr or sum(1 for t in tr if t["vsol"] == 0) > len(tr) / 2: continue
        c = L[m]; dev = c.get("creator"); tc = ms(c["slot"], c.get("idx") or 0); S0 = c["slot"]
        T = [ms(t["s"], t["i"]) for t in tr]; P = [t["vsol"] / t["vtok"] if t["vtok"] else 0 for t in tr]
        dev_buy = sum(t["sol"] for t in tr if t["user"] == dev and t["buy"] and t["s"] == S0) / 1e9
        bundle = len({t["user"] for t in tr if t["buy"] and t["s"] == S0})
        cand = [k for k, t in enumerate(tr) if t["sol"] >= 3e8 and T[k] - tc <= 900_000 and k >= 1]
        if len(cand) > 40: cand = [cand[int(j * len(cand) / 40)] for j in range(40)]
        peak = 0; dev_sold = 0.0; seen_b = set(); maxb = 0.0; pk = 0
        ci = set(cand)
        for k, t in enumerate(tr):
            peak = max(peak, P[k]); 
            if t["user"] == dev and not t["buy"]: dev_sold += t["sol"] / 1e9
            if t["buy"]: seen_b.add(t["user"]); maxb = max(maxb, t["sol"] / 1e9)
            if k not in ci: continue
            t0 = T[k]
            def win_(sec):
                j = k; b = s = 0.0; nb = set(); ns = set()
                while j >= 0 and t0 - T[j] <= sec * 1000:
                    x = tr[j]
                    if x["buy"]: b += x["sol"]; nb.add(x["user"])
                    else: s += x["sol"]; ns.add(x["user"])
                    j -= 1
                return b / 1e9, s / 1e9, len(nb), len(ns), j
            def ch(sec):
                j = k
                while j > 0 and t0 - T[j - 1] <= sec * 1000: j -= 1
                return math.log(P[k] / P[j - 1]) if j > 0 and P[j - 1] > 0 and P[k] > 0 else 0.0
            b1, s1, _, _, _ = win_(1); b5, s5, nb5, ns5, _ = win_(5); b15, s15, _, _, _ = win_(15); b60, s60, nb60, ns60, _ = win_(60)
            recent = [x for x in tr[max(0, k - 200):k + 1] if t0 - ms(x["s"], x["i"]) <= 60_000 and x["buy"]]
            w2 = sum(1 for x in recent if good(x["user"]) and t0 - ms(x["s"], x["i"]) <= 2000)
            w10 = sum(1 for x in recent if good(x["user"]) and t0 - ms(x["s"], x["i"]) <= 10_000); w60 = sum(1 for x in recent if good(x["user"]))
            l10 = sum(1 for x in recent if bad(x["user"]) and t0 - ms(x["s"], x["i"]) <= 10_000)
            wnet10 = sum((x["sol"] / 1e9) for x in recent if good(x["user"]) and t0 - ms(x["s"], x["i"]) <= 10_000)
            last5 = [x["user"] for x in tr[max(0, k - 5):k + 1] if x["buy"]]
            gap = (t0 - T[k - 1]) / 1000; prevgap = (T[k - 1] - T[k - 2]) / 1000 if k >= 2 else 999
            r_ = win(t["user"])
            f = [(t0 - tc) / 1000, t["vsol"] / 1e9, P[k] / peak if peak else 1, ch(1), ch(5), ch(15), ch(60), b1, s1, b5, s5, b15, s15, b60, s60, nb5, ns5, nb60, ns60,
                 k, gap, 1 if t["buy"] else 0, t["sol"] / 1e9, r_[0], r_[1], 1 if t["user"] in rep else 0, 1 if t["user"] == dev else 0, dev_buy, dev_sold, bundle,
                 w2, w10, w60, l10, wnet10, sum(win(u)[0] for u in last5), len(seen_b), maxb, ((t["bt"] + 18000) // 3600) % 24,
                 1 if HOST.get(m) in TWH else 0, 1 if (t["buy"] and prevgap >= 5) else 0]
            a = label(tr, k, t0, False); d = label(tr, k, t0, True)
            if a is None or d is None: continue
            rows.append(f); labs.append(a + [d[1]]); meta.append((m, t0, run, t["bt"]))
    return np.array(rows, np.float32), np.array(labs, np.float32), meta
if __name__ == "__main__":
    X = []; Y = []; M = []
    with Pool(14) as p:
        for x, y, m in p.imap_unordered(work, sorted(byb), chunksize=2):
            if len(x): X.append(x); Y.append(y); M += m
    X = np.concatenate(X); Y = np.concatenate(Y)
    pickle.dump(dict(X=X, Y=Y, M=M, F=FEAT, H=list(HOLDS) + ["3d"]), open("mine.pkl", "wb"))
    print("rows", len(X), "| R2", sum(1 for m in M if m[2] == "R2"), "R3", sum(1 for m in M if m[2] == "R3"))
