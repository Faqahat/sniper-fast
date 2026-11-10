#!/usr/bin/env python3
"""REACTGUARD step 1: per M2-envelope dump, per landing delay L, simulate a REACTIVE buy with an EXACT first-or-revert guard.

Clock (same as sniper-m2v4/sim.py, "block clock"): a tx at (slot s, index i) arrives at s + i/n_s slots (n_s = max index + 1
seen in that slot, 1 slot = 212.07 ms measured). Our buy arrives at clock(dump) + L; its block position is
floor(frac * n) of that slot (same slot and not behind the dump -> right behind the dump).
Guard variants (all fill at the ACTUAL curve state at our position, our own impact kept on the tape after us):
  g01  no other BUY >= 0.01 SOL between the dump and us      g05  same for >= 0.05 SOL
  gx   exact state: tokens out at our position >= expected-at-post-dump-state x (1 - 0.005) (the probe's tol; sells help)
Exits (sell all, lands at decision + L on the block clock; pump fee per token from the tape; graduation >= 110 SOL -> gain 0):
  T   live: decision = 125 ms after our landing, earlier if the sell quote is >= +20% / <= -20% at a tape row before that
  S2  sell lands 2 slots after our entry slot, 0.4 into the slot
Follower stress c20: 20% of all outside buy SOL landing between our buy and our sell is removed from the curve.
Front: the same exit but filled right behind the dump (state = post-dump) -> adverse-selection test.
usage: r1_sim.py RUN  (reads /home/it/sniper-data/reactguard/c_RUN_*; writes o_RUN.npz)"""
import sys, numpy as np
sys.path.insert(0, "/home/it/sniper-studies/sniper-m2v4"); import sim as SM, m2feat as MF
D = "/home/it/sniper-data/reactguard/"; run = sys.argv[1]
S = 0.45; K0 = SM.K0; MS = SM.MS
LMS = [0, 5, 10, 20, 30, 45, 60]
LDIST = SM.lat_samples(12)                                  # measured FRA reactive landings (slots), 12 quantiles, median 61 ms

Y = np.array(np.load(D + f"c_{run}_sub.npy", mmap_mode="r")); z = np.load(D + f"c_{run}_cand.npz"); K = z["k"]; X = z["X"]
SL = np.load(D + f"tape_{run}/slots.npy"); tp = SM.Tape(Y, SL)
V = tp.V; n = len(Y)
CL = tp.clock(Y["slot"], Y["idx"])
isb = Y["buy"] == 1; sol = Y["sol"].astype(np.float64)
c01 = np.cumsum(isb & (sol >= 1e7)); c05 = np.cumsum(isb & (sol >= 5e7)); cany = np.cumsum(isb)
mint = Y["mint"].astype(np.int64); ME = tp.me[mint]           # end row (excl) of each row's mint

def outv(Vs, q, fe):
    return (Vs - K0 / (K0 / Vs + q)) * (1 - fe) / 1e9

def one(d):
    k = K; m = mint[k]; a = tp.ms[m]; sl = Y["slot"][k]; i = Y["idx"][k]
    t0 = CL[k]
    se, ie = tp.position(t0 + d); same = (se == sl) & (ie <= i); ie = np.where(same, i + 1, ie)
    ke = np.maximum(tp.before(m, se, ie, a), k)
    tl = np.maximum(tp.clock(se, ie), t0)
    fe = Y["fee"][k] / 1e4; x = S * 1e9 / (1 + fe)
    qd = K0 / V[k] - K0 / (V[k] + x); q = K0 / V[ke] - K0 / (V[ke] + x)
    g01 = (c01[ke] - c01[k]) == 0; g05 = (c05[ke] - c05[k]) == 0; gx = q >= qd * (1 - 0.005); nb = cany[ke] - cany[k]
    # ---- exit T: scan rows after us up to 125 ms for +-20% quote
    tdec = tl + 125.0 / MS; act = np.ones(len(k), bool); j = 1
    while act.any() and j < 400:
        r = ke + j; ok = act & (r < ME[k]); r = np.where(ok, r, ke)
        ok &= CL[r] <= tdec
        pr = outv(V[r] + x, q, fe) / S - 1
        hit = ok & ((pr >= 0.2) | (pr <= -0.2))
        tdec = np.where(hit, CL[r], tdec); act = ok & ~hit; j += 1
    res = {}
    for ex, tx in (("T", None), ("S2", None)):
        if ex == "T": sx, ix = tp.position(tdec + d)
        else: sx, ix = tp.position(se + 2 + 0.4)
        kx = np.maximum(tp.before(m, sx, ix, a), ke); kx = np.minimum(kx, ME[k] - 1); kx = np.maximum(kx, ke)
        B = tp.cb[kx] - tp.cb[ke]
        grad = tp.mxk[kx] >= 110e9
        for cut in (0.0, 0.2):
            Vs = V[kx] + x - cut * B
            p = outv(Vs, q, fe) - S; pf = outv(Vs, qd, fe) - S
            p = np.where(grad, np.minimum(p, 0), p); pf = np.where(grad, np.minimum(pf, 0), pf)
            res[f"p_{ex}_{int(cut*100)}"] = p; res[f"pf_{ex}_{int(cut*100)}"] = pf
        res[f"tx_{ex}"] = tp.clock(sx, ix)
    res.update(g01=g01, g05=g05, gx=gx, nb=nb, tl=tl, slip=q / qd)
    return res

out = {}
for L in LMS:
    r = one(L / MS)
    for kk, v in r.items(): out[f"L{L}|{kk}"] = v.astype(np.float32)
# measured FRA distribution: expectations over the 12 quantile samples (fill prob and fill-weighted P&L per variant)
acc = {}
for d in LDIST:
    r = one(d)
    for g in ("g01", "g05", "gx"):
        f = r[g].astype(float); acc[f"F_{g}"] = acc.get(f"F_{g}", 0) + f / len(LDIST)
        for ex in ("T", "S2"):
            for c in (0, 20):
                acc[f"FP_{g}_{ex}_{c}"] = acc.get(f"FP_{g}_{ex}_{c}", 0) + f * r[f"p_{ex}_{c}"] / len(LDIST)
    for ex in ("T", "S2"):
        for c in (0, 20):
            acc[f"P_{ex}_{c}"] = acc.get(f"P_{ex}_{c}", 0) + r[f"p_{ex}_{c}"] / len(LDIST)
            acc[f"PF_{ex}_{c}"] = acc.get(f"PF_{ex}_{c}", 0) + r[f"pf_{ex}_{c}"] / len(LDIST)
    acc["tx_T"] = np.maximum(acc.get("tx_T", 0), r["tx_T"]); acc["tl"] = np.maximum(acc.get("tl", 0), r["tl"])
for kk, v in acc.items(): out[f"Lfra|{kk}"] = np.asarray(v, np.float32)
sc3 = MF.Bundle("/home/it/sniper-data/m2v4/m2_v3_server.json").score(X); sc4 = MF.Bundle("/home/it/sniper-studies/sniper-m2v4/m2_v4_real61_h3.json").score(X)
first_bt = Y["bt"][tp.ms[mint[K]]]
np.savez(D + f"o_{run}.npz", sc3=sc3, sc4=sc4, bt=Y["bt"][K], cbt=first_bt, slot=Y["slot"][K], idx=Y["idx"][K], mint=mint[K],
         dsol=sol[K] / 1e9, drop=X[:, 22], clk=CL[K], **out)
print(run, len(K), "done")
