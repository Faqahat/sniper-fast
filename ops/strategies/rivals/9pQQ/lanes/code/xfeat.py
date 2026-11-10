"""Exit features for an arbitrary hold (same definitions as l11_exit_moments), computed on the 9pQQ-removed price path.
rows = tape rows (global index) of the hold window after entry; returns (feature matrix [n, len(FN)], outside-row mask)."""
import numpy as np, sys
sys.path.insert(0, "/home/it/sniper/ops/strategies/rivals/9pQQ/lanes/code")
import llib
K, V = llib.K, llib.V
FN = ["hold", "hold_s", "ret", "maxret", "dd", "fromlow", "side", "size", "impact"] + [f"{k}{w}" for w in (1, 3, 10, 30) for k in ("flow", "nb", "ns", "bsol", "dpx")] + \
     ["since_buy", "ntr_hold", "flow_hold", "same_before", "vsol", "age", "k_prev", "mod", "nopen", "hour"]
def feats(T, lo, hi, s_entry, bt_entry, p_entry, p0, ctx, extra_tok=0.0):
    t = T.t
    Ss = t.s[lo:hi]; out = t.u[lo:hi] != t.wid
    C = T.c9[lo:hi] - extra_tok; Cp = C - (t.cpost[lo:hi].astype(float) - t.cpre[lo:hi])
    DV = (K / (C + V) - K / (Cp + V)) / 1e9; P = (K / (C + V)) / (C + V)
    j = np.nonzero(out)[0]
    F = {}
    pmax = np.maximum.accumulate(P); pmin = np.minimum.accumulate(P)
    F["hold"] = Ss[j] - s_entry; F["hold_s"] = (t.bt[lo + j] - bt_entry).astype(float)
    F["ret"] = P[j] / p_entry - 1; F["maxret"] = pmax[j] / p_entry - 1; F["dd"] = P[j] / pmax[j] - 1; F["fromlow"] = P[j] / pmin[j] - 1
    F["side"] = np.sign(DV[j]); F["size"] = DV[j]; F["impact"] = P[j] / np.where(j > 0, P[np.maximum(j - 1, 0)], p0) - 1
    cdv = np.r_[0, np.cumsum(np.where(out, DV, 0))]; cb = np.r_[0, np.cumsum(out & (DV > 0))]; cs = np.r_[0, np.cumsum(out & (DV < 0))]
    cbs = np.r_[0, np.cumsum(np.where(out & (DV > 0), DV, 0))]
    for w in (1, 3, 10, 30):
        l_ = np.searchsorted(Ss, Ss[j] - w + (1 if w == 1 else 0))
        F[f"flow{w}"] = cdv[j + 1] - cdv[l_]; F[f"nb{w}"] = cb[j + 1] - cb[l_]; F[f"ns{w}"] = cs[j + 1] - cs[l_]; F[f"bsol{w}"] = cbs[j + 1] - cbs[l_]
        F[f"dpx{w}"] = P[j] / np.where(l_ > 0, P[np.maximum(l_ - 1, 0)], p0) - 1
    lastbuy = np.maximum.accumulate(np.where(out & (DV > 0), Ss, -1)); prevb = np.r_[-1, lastbuy[:-1]]
    F["since_buy"] = np.where(prevb[j] >= 0, Ss[j] - prevb[j], Ss[j] - s_entry)
    F["ntr_hold"] = cb[j + 1] + cs[j + 1]; F["flow_hold"] = cdv[j + 1]; F["same_before"] = j - np.searchsorted(Ss, Ss[j])
    F["vsol"] = K / (C[j] + V) / 1e9
    for k in ("age", "k_prev", "mod", "nopen", "hour"): F[k] = np.full(len(j), ctx[k], float)
    return np.stack([np.asarray(F[k], np.float32) for k in FN], 1), lo + j
