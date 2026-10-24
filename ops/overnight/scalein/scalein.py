#!/usr/bin/env python3
# haqqiUUX-STYLE SCALE-IN replay (local, read-only). Entry list x exit/add grid; every action (first buy, each add, the sell) lands
# LAT ms after the moment it was decided (block-position arrival proxy, like all our replays). 0.3 SOL first buy, +0.3 SOL per add
# when >= A SOL of outside buys arrived since our last action (max N adds); exit = buying stalls (no outside buy >= 0.1 SOL for G ms),
# stop-loss SL on the position value vs total cost, or time cap T. Pump fees each leg + TXC per tx. Plain curve (no follower limits).
# Entry sets: HAQQ = haqqiUUX's first buy on each token (we decide at its trigger, i.e. the trade right before its buy);
#             MOM  = token 0.4-5 s old, first outside buy >= 1 SOL after the launch bundle.
# Splits by PKT time: TRAIN < 10-23 06:00, TEST 10-23 06:00-18:31 (R2), LIVE = run R3 (10-23 19:26 -> now).
import os, sys, json, collections, itertools, statistics
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
W = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"; B0 = 0.3e9; BADD = 0.3e9; TXC = 0.0008
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def arr(t): return t["s"] * 212.0 + t["i"] / max(SS.get(t["s"], 400), t["i"] + 1) * 212.0
L = rp.load_launches(); byb = collections.defaultdict(set)
for m, c in L.items(): byb[(c["run"], rp.bucket(m))].add(m)
GRID = [(N, A, G, SL, T) for N in (0, 3, 8) for A in (1.5, 3.0) for G in (1500, 4000) for SL in (0.25, 9.0) for T in (20, 60) if not (N == 0 and A == 3.0)]
LATS = (35, 60, 75)
def fr(t): return ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
def sim(tr, A_, k_dec, lat, N, A, G, SL, T, quick=False):
    """k_dec = index of the trade at which we decide to enter; returns P&L in SOL (None if no trade after)."""
    a_dec = A_[k_dec]; ke = next((k for k in range(k_dec + 1, len(tr)) if A_[k] >= a_dec + lat), None)
    if ke is None: return None
    V, Tk = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]; f = fr(tr[ke - 1])
    X = int(B0 / (1 + f)); q = Tk * X // (V + X); V += X; Tk -= q; cost = B0 / 1e9 + TXC; frs = f
    a_in = A_[ke]; s_in = tr[ke]["s"]; adds = 0; flow = 0.0; last_buy = a_in; pend_add = None; pend_exit = None
    if quick: pend_exit = None
    for k in range(ke, len(tr)):
        t = tr[k]; a = A_[k]
        if quick:
            if t["s"] >= s_in + 6: break
        else:
            if pend_exit is not None and a >= pend_exit: break                     # our sell lands before this trade
            if pend_exit is None and a - last_buy >= G: pend_exit = last_buy + G + lat
            if pend_exit is not None and a >= pend_exit: break
            if pend_add is not None and a >= pend_add:                             # our add lands before this trade
                X = int(BADD / (1 + fr(t))); dq = Tk * X // (V + X); V += X; Tk -= dq; q += dq; cost += BADD / 1e9 + TXC; adds += 1; pend_add = None
        if t["buy"]:
            d = Tk * t["sol"] // (V + t["sol"]); V += t["sol"]; Tk -= d
            if t["sol"] >= 0.1e9: last_buy = a; flow += t["sol"] / 1e9
        else: so = V * t["tok"] // (Tk + t["tok"]); V -= so; Tk += t["tok"]
        frs = fr(t)
        if V >= 114e9: break
        if quick: continue
        val = (V * q / (Tk + q)) * (1 - frs) / 1e9 - TXC
        if pend_exit is None and (val <= (1 - SL) * cost or a - a_in >= T * 1000): pend_exit = a + lat
        if pend_add is None and pend_exit is None and adds < N and flow >= A: pend_add = a + lat; flow = 0.0
    return (V * q / (Tk + q)) * (1 - frs) / 1e9 - TXC - cost
def work(key):
    out = []
    for m, tr in rp.read_bucket(key[0], key[1], byb[key]).items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]
        if c.get("mayhem") or "InitializeMayhemState" in (c.get("ixn") or []): continue
        A_ = [arr(t) for t in tr]; S0 = c["slot"]; ents = []
        kh = next((k for k, t in enumerate(tr) if t["user"] == W and t["buy"]), None)
        if kh and kh > 0: ents.append(("HAQQ", kh - 1))
        st = rp.structure(tr, c); ge = max(st["g_end"], 1)
        km = next((k for k in range(ge, len(tr)) if tr[k]["buy"] and tr[k]["sol"] >= 1e9 and 0.4 <= (tr[k]["s"] - S0) * 0.212 <= 5 and tr[k]["user"] != W), None)
        if km is not None: ents.append(("MOM", km))
        for name, kd in ents:
            r = dict(set=name, m=m, run=c["run"], t=c["bt"] + (tr[kd]["s"] - S0) * 0.212, res={})
            for lat in LATS:
                r["res"][f"{lat}|quick"] = sim(tr, A_, kd, lat, 0, 0, 0, 0, 0, quick=True)
                for g in GRID: r["res"][f"{lat}|{'|'.join(map(str, g))}"] = sim(tr, A_, kd, lat, *g)
            out.append(r)
    return out
if __name__ == "__main__":
    R = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=4): R += o
    json.dump(R, open("/home/moiz/sniper/ops/overnight/scalein/scalein.json", "w"))
    print("entries", collections.Counter(r["set"] for r in R))
