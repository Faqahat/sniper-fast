#!/usr/bin/env python3
"""LANES step 11: exit decision moments = every landed OUTSIDE curve trade while 9pQQ holds (after its buy, before its sell), plus
decision-time features; y=1 if its sell lands in this trade's slot or the next and within 10 trades. Negatives sampled 30% (w=1/0.3).
Prices with 9pQQ's own position added back (9pQQ removed). -> lanes/xmom_<run>.npz"""
import sys, pickle, numpy as np, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/rivals/9pQQ/lanes/code")
import llib
run = sys.argv[1]; K, V = llib.K, llib.V; RATE = 0.3
rng = np.random.default_rng(5)
t = llib.load(run)
T = pickle.load(open(f"{llib.D}/trips_{run}.pkl", "rb"))["rows"]
ev = sorted([(r["bs"], 1) for r in T] + [(r["ss"], -1) for r in T]); es = np.array([e[0] for e in ev]); ec = np.cumsum([e[1] for e in ev])
def nopen(s): k = np.searchsorted(es, s, side="right") - 1; return np.where(k >= 0, ec[np.maximum(k, 0)], 0)
FN = None; XS, YS, WS, IDS = [], [], [], []
for r in T:
    if r["mint"] not in t.mix: continue
    m = t.mix[r["mint"]]; a, b = t.ms[m], t.ms[m + 1]
    S = t.s[a:b]; I = t.i[a:b]; U = t.u[a:b]
    key = S.astype(np.int64) * 100000 + I
    jb = int(np.searchsorted(key, r["bs"] * 100000 + r["bi"])); js = int(np.searchsorted(key, r["ss"] * 100000 + r["si"]))
    if js >= len(key) or key[js] != r["ss"] * 100000 + r["si"] or js - jb < 2: continue
    held = float(t.tok[a + jb])
    seg = slice(jb + 1, js)
    Ss = S[seg]; Us = U[seg]; out = Us != t.wid
    C = t.cpost[a + jb + 1:a + js].astype(float) + held
    Cp = t.cpre[a + jb + 1:a + js].astype(float) + held
    DV = (K / (C + V) - K / (Cp + V)) / 1e9
    P = (K / (C + V)) / (C + V)
    c0 = float(t.cpost[a + jb]) + held; p0 = (K / (c0 + V)) / (c0 + V)    # price right after its buy, 9pQQ removed (= its entry state)
    c0b = float(t.cpre[a + jb]); p_entry = (K / (c0b + V)) / (c0b + V)
    idx = np.nonzero(out)[0]
    if not len(idx): continue
    y = (r["ss"] - Ss[idx] <= 1) & ((js - (jb + 1 + idx)) <= 10)
    keep = y | (rng.random(len(idx)) < RATE) | (r["ss"] - Ss[idx] <= 3)
    j = idx[keep]
    if not len(j): continue
    F = collections.OrderedDict()
    pmax = np.maximum.accumulate(P); pmin = np.minimum.accumulate(P)
    F["hold"] = Ss[j] - r["bs"]; F["hold_s"] = (t.bt[a + jb + 1 + j] - r["bbt"]).astype(float)
    F["ret"] = P[j] / p_entry - 1; F["maxret"] = pmax[j] / p_entry - 1; F["dd"] = P[j] / pmax[j] - 1; F["fromlow"] = P[j] / pmin[j] - 1
    F["side"] = np.sign(DV[j]); F["size"] = DV[j]; F["impact"] = P[j] / np.where(j > 0, P[np.maximum(j - 1, 0)], p0) - 1
    cdv = np.r_[0, np.cumsum(np.where(out, DV, 0))]; cb = np.r_[0, np.cumsum(out & (DV > 0))]; cs = np.r_[0, np.cumsum(out & (DV < 0))]
    cbs = np.r_[0, np.cumsum(np.where(out & (DV > 0), DV, 0))]
    for w in (1, 3, 10, 30):
        lo = np.searchsorted(Ss, Ss[j] - w + (1 if w == 1 else 0))
        F[f"flow{w}"] = cdv[j + 1] - cdv[lo]; F[f"nb{w}"] = cb[j + 1] - cb[lo]; F[f"ns{w}"] = cs[j + 1] - cs[lo]; F[f"bsol{w}"] = cbs[j + 1] - cbs[lo]
        F[f"dpx{w}"] = P[j] / np.where(lo > 0, P[np.maximum(lo - 1, 0)], p0) - 1
    lastbuy = np.where(out & (DV > 0), Ss, -1); lastbuy = np.maximum.accumulate(lastbuy)
    prevb = np.r_[-1, lastbuy[:-1]]
    F["since_buy"] = np.where(prevb[j] >= 0, Ss[j] - prevb[j], Ss[j] - r["bs"])
    F["ntr_hold"] = cb[j + 1] + cs[j + 1]; F["flow_hold"] = cdv[j + 1]
    F["same_before"] = j - np.searchsorted(Ss, Ss[j])
    F["vsol"] = K / (C[j] + V) / 1e9; F["age"] = r["age"]; F["k_prev"] = r["k_prev"]; F["mod"] = 0 if (r["k_prev"] == 0 or r["since_sell"] > 20000) else 1
    F["nopen"] = nopen(Ss[j]); F["hour"] = ((t.bt[a + jb + 1 + j] + 5 * 3600) % 86400) // 3600
    if FN is None: FN = list(F.keys())
    XS.append(np.stack([np.broadcast_to(np.asarray(F[k], np.float32), (len(j),)) for k in FN], 1)); YS.append(y[keep]); WS.append(np.where(y[keep] | (r["ss"] - Ss[j] <= 3), 1.0, 1 / RATE))
    IDS.append(np.stack([np.full(len(j), m), a + jb + 1 + j, np.full(len(j), jb + a), np.full(len(j), js + a)], 1))
X = np.concatenate(XS); y = np.concatenate(YS); w = np.concatenate(WS).astype(np.float32); ids = np.concatenate(IDS)
np.savez(f"{llib.D}/xmom_{run}.npz", X=X, y=y, w=w, ids=ids, fn=np.array(FN))
print(run, X.shape, int(y.sum()), flush=True)
