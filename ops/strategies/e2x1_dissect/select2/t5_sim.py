#!/usr/bin/env python3
"""select2 t5: simulated P&L at OUR landing for every universe row (trigger event e), ourspeed/o2_sim method (read-only):
 - counterfactual tape WITHOUT E2x1 + Grozoe2L (their SOL removed from the curve, constant product kept)
 - our buy lands d after e on the block clock (d = live delay-shape quantiles q_pre rescaled to median L ms; 7 quantiles)
 - size: his tier code (age < 30 s: 0.7 % of vsol after e; 30-120 s: 1.0 %; older: 1.0 SOL), clipped to [0.2, 1.0]; also fixed 0.3
 - guard: fill only if our entry price <= 1.05 x the post-e price
 - exits: entry + 5 s / 20 s / 34 s, and 'band' (18 / 34 / 83 s by age bucket), sell lands d' later
 - P&L per lot in SOL before tx costs (our live cost ~4.5 mSOL per trip is applied in the report); phi = 0.2 variant removes
   20 % of other wallets' buy SOL landing in the first 10 slots after our entry (fast followers)
Out: OUT/sim.npz aligned with U2.npz rows"""
import sys, json, time, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select2"); from lib import *
t0 = time.time()
L_MS = float(sys.argv[1]) if len(sys.argv) > 1 else 66.0
D = load(); w = int(D["wid"]); sib = int(D["sibid"])
sl = D["slot"].astype(np.int64); ix = D["idx"].astype(np.int64); bu = D["buy"].astype(bool); so = D["sol"].astype(np.float64)
vs = D["vsol"].astype(np.float64); vt = D["vtok"].astype(np.float64); mi = D["mint"].astype(np.int64); us = D["user"].astype(np.int64)
fee = (D["fee_bps"].astype(np.float64) + D["cfee_bps"].astype(np.float64)) / 1e4
N = len(sl); S0 = int(sl.min()); AR = np.arange(N)
seg_a = np.zeros(N, np.int64); st = D["span_a"]; en = D["span_b"]
for a, b in zip(st, en): seg_a[a:b] = a
# counterfactual reserves: remove E2x1 + sib net SOL (cumulative within mint)
own = (us == w) | (us == sib)
net = np.where(own, np.where(bu, so, -so), 0.0); c = np.cumsum(net); c = c - c[seg_a] + net[seg_a]
K = vs * vt; vcf = vs - c; vcf = np.maximum(vcf, 1e6); vtcf = K / vcf
ob = np.where(bu & ~own, so, 0.0); CB = np.r_[0.0, np.cumsum(ob)]
KEY = (mi << 24) | (ix.astype(np.int64) << 4) | 0
KEYS = (mi << 40) | ((sl - S0) << 16) | np.minimum(ix, 65535)
# block clock
B = np.load(f"{SCR}/blocks.npy"); b_lo = int(B[0, 0]); NB = np.zeros(int(B[-1, 0]) - b_lo + 2, np.int64); NB[B[:, 0] - b_lo] = B[:, 1] + 1
def bsize(s):
    k = np.clip(np.asarray(s, np.int64) - b_lo, 0, len(NB) - 1); return NB[k]
def clock(s, i):
    n = bsize(s).astype(float); n[n <= 0] = 1
    return np.asarray(s, float) + np.minimum(np.asarray(i, float) / n, 0.999999)
def position(t):
    t = np.asarray(t, float); s = np.floor(t).astype(np.int64); fr = t - s; n = bsize(s)
    for _ in range(12):
        miss = n <= 0
        if not miss.any(): break
        s = np.where(miss, s + 1, s); fr = np.where(miss, 0.0, fr); n = bsize(s)
    return s, np.floor(fr * np.maximum(n, 1)).astype(np.int64)
def before(m, s, i):
    """index of the last tape row on mint m strictly before chain position (s, i); -1 if none"""
    k = (m << 40) | (np.maximum(s - S0, 0) << 16) | np.minimum(np.maximum(i, 0), 65535)
    return np.searchsorted(KEYS, k, side="left") - 1
dq = json.load(open("/home/moiz/sniper-data/e2x1_dissect/ourspeed/delay_q.json")); Q = np.array(dq["q_pre"])[::3]; QMED = dq["med_pre"]
dd = Q * (L_MS / QMED) / SMS; dd2 = dd[::-1]
U = np.load(f"{OUT}/U2.npz"); rows = U["row"]; n = len(rows); print("rows", n, "delays(slots)", dd.round(3))
e_s = sl[rows]; e_i = ix[rows]; e_m = mi[rows]; age = U["age_s"]
tT = clock(e_s, e_i)
Vd = vcf[rows]; Td = vtcf[rows]; f = fee[rows]
tier = np.where(age < 30, 0.007, np.where(age < 120, 0.010, np.nan))
S_tier = np.where(np.isnan(tier), 1.0, np.clip(tier * Vd / 1e9, 0.2, 1.0))
BAND = np.where(age < 30, 18.0, np.where(age < 120, 34.0, 83.0)) * 1000 / SMS
out = {}
EXITS = {"5s": 5000 / SMS, "20s": 20000 / SMS, "34s": 34000 / SMS, "band": BAND}
for sname, S in (("tier", S_tier), ("fix", np.full(n, 0.3))):
    x = S * 1e9 / (1 + f)
    qref = Td - Vd * Td / (Vd + x)
    acc = {}
    for di, d in enumerate(dd):
        te = tT + d; se, ie = position(te)
        same = (se == e_s) & (ie <= e_i); te = np.where(same, e_s + (e_i + 1) / np.maximum(bsize(e_s), 1), te); se, ie = position(te)
        ke = np.maximum(before(e_m, se, ie), rows)
        Ve = vcf[ke]; Te = vtcf[ke]; Kk = Ve * Te
        q = Te - Kk / (Ve + x)
        fill = q >= qref / 1.05
        for nm, h in EXITS.items():
            tx = te + h + dd2[di]
            sx, ixx = position(tx); kx = np.maximum(before(e_m, sx, ixx), ke)
            Vx = vcf[kx]
            kf = np.maximum(np.minimum(before(e_m, *position(np.minimum(tx, te + 10))), kx), ke)
            bf = CB[kf + 1] - CB[ke + 1]
            for phi in (0.0, 0.2):
                V2 = np.maximum(Vx + x - phi * bf, 1e6)
                o = (V2 - Kk / (Kk / V2 + q)) * (1 - f)
                pnl = np.where(fill, o / 1e9 - S, 0.0)
                kk_ = (nm, phi); a = acc.setdefault(kk_, [np.zeros(n), np.zeros(n)]); a[0] += fill / len(dd); a[1] += pnl / len(dd)
    for (nm, phi), (fl, p) in acc.items():
        out[f"{sname}|{nm}|{phi}|fill"] = fl.astype(np.float32); out[f"{sname}|{nm}|{phi}|pnl"] = p.astype(np.float32)
    out[f"{sname}|S"] = S.astype(np.float32)
    print(sname, "done", time.time() - t0, flush=True)
np.savez(f"{OUT}/sim_{int(L_MS)}.npz", **out)
print("saved", time.time() - t0)
