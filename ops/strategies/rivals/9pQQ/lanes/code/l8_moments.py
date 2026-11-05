#!/usr/bin/env python3
"""LANES step 8: decision moments (= every landed OUTSIDE curve trade on a non-mayhem recorded token, age>=8 slots) for the two entry
modules, with decision-time features (everything strictly before or at that trade in chain order).
  module NEW : token never traded by 9pQQ yet (or tracking expired: >20,000 slots since its last sell)
  module TRK : 9pQQ has a closed trip on the token, is flat, own sell >= 2 slots ago and <= 20,000 slots
Label y=1: 9pQQ's next buy on this token lands in this trade's slot or the next one and no other outside trade... (window label:
  buy within [s, s+1] and at most 10 trades later).  Sampling: all rows with a 9pQQ buy within 3 slots after + 4% of the rest (w=25).
-> lanes/mom_<run>.npz (X float32, y, w, mod, fs names, ids)"""
import sys, pickle, numpy as np, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/rivals/9pQQ/lanes/code")
import llib
run = sys.argv[1]; K, V = llib.K, llib.V; RATE = 0.04
rng = np.random.default_rng(11)
t = llib.load(run, failed=True); L = llib.launches(run)
T = pickle.load(open(f"{llib.D}/trips_{run}.pkl", "rb"))["rows"]
# global open-position count by slot
ev = sorted([(r["bs"], 1) for r in T] + [(r["ss"], -1) for r in T]); es = np.array([e[0] for e in ev]); ec = np.cumsum([e[1] for e in ev])
def nopen(s): k = np.searchsorted(es, s, side="right") - 1; return np.where(k >= 0, ec[np.maximum(k, 0)], 0)
# wallet activity: trades so far in run per user (global chain order)
order = np.lexsort((t.i, t.s)); uu = t.u[order]
o2 = np.lexsort((np.arange(len(uu)), uu)); cnt = np.empty(len(uu), np.int32)
first = np.r_[True, uu[o2][1:] != uu[o2][:-1]]; grp = np.cumsum(first) - 1; starts = np.nonzero(first)[0]
cnt[o2] = np.arange(len(uu)) - starts[grp]
ucount = np.empty(len(uu), np.int32); ucount[order] = cnt
PFL = ["41Pr4XqE", "L2TExMFK", "6gY1osmP", "7xdwTaV5", "haqqqMGN", "tRunsb6N", "2Emmffdg", "FLASHX8D", "6Vo3245e", "JUP6LkbZ", "term9"]
pflag = np.array([[p in ps for p in PFL] + [0 if ps == "" else ps.count(",") + 1] for ps in t.psets], np.int16)
trips_by = collections.defaultdict(list)
for r in T: trips_by[r["mint"]].append(r)
FN = None; XS, YS, WS, MS, IDS = [], [], [], [], []
def vs(c): return K / (np.asarray(c, float) + V)
for mint, la in L.items():
    if la["may"] or mint not in t.mix: continue
    m = t.mix[mint]; a, b = t.ms[m], t.ms[m + 1]
    if b - a < 3: continue
    S = t.s[a:b]; I = t.i[a:b]; U = t.u[a:b]; age = S - la["slot"]
    C1 = t.cpost[a:b].astype(float); DV = (vs(C1) - vs(t.cpre[a:b])) / 1e9
    P = vs(C1) / (C1 + V); own = U == t.wid; out = ~own
    key = S.astype(np.int64) * 100000 + I
    TR = trips_by.get(mint, [])
    buys = np.array([[r["bs"], r["bi"]] for r in TR], np.int64).reshape(-1, 2); sells = np.array([[r["ss"], r["si"]] for r in TR], np.int64).reshape(-1, 2)
    if not len(TR): buys = np.array([[10**9, 0]], np.int64); sells = np.array([[10**9, 0]], np.int64)
    bkey = buys[:, 0] * 100000 + buys[:, 1]; skey = sells[:, 0] * 100000 + sells[:, 1]
    if not len(TR): bkey = bkey[:0]; skey = skey[:0]; buys = buys[:0]; sells = sells[:0]
    # module per row: number of own trips completed before row, holding?
    nb = np.searchsorted(bkey, key, side="right"); ns = np.searchsorted(skey, key, side="right")
    holding = nb > ns
    last_sell_s = np.where(ns > 0, sells[np.maximum(ns - 1, 0), 0], -1) if len(sells) else np.full(len(S), -1)
    since = np.where(ns > 0, S - last_sell_s, -1)
    mod = np.where(holding, -1, np.where((ns == 0) | (since > 20000), 0, np.where(since >= 2, 1, -1)))
    cand = out & (age >= 8) & (mod >= 0)
    if not cand.any(): continue
    # label: next own buy after row within [s, s+1] and <= 10 trades later
    nxt = np.searchsorted(bkey, key, side="right")
    has = nxt < len(bkey)
    nb_s = np.where(has, buys[np.minimum(nxt, len(bkey) - 1), 0], 10**12) if len(bkey) else np.full(len(S), 10**12)
    nb_pos = np.searchsorted(key, np.where(has, bkey[np.minimum(nxt, len(bkey) - 1)], 10**18)) if len(bkey) else np.full(len(S), 10**9)
    y = has & (nb_s - S <= 1) & (nb_pos - np.arange(len(S)) <= 10)
    near = has & (nb_s - S <= 3)
    keep = cand & (near | (rng.random(len(S)) < RATE))
    idx = np.nonzero(keep)[0]
    if not len(idx): continue
    # prefix sums
    cdv = np.r_[0, np.cumsum(np.where(out, DV, 0))]; cb = np.r_[0, np.cumsum(out & (DV > 0))]; cs = np.r_[0, np.cumsum(out & (DV < 0))]
    cbs = np.r_[0, np.cumsum(np.where(out & (DV > 0), DV, 0))]
    F = collections.OrderedDict()
    j = idx; jj = j + 1  # inclusive of the trigger row
    F["side"] = np.sign(DV[j]); F["size"] = DV[j]; F["abssize"] = np.abs(DV[j]); F["age"] = age[j]; F["logage"] = np.log1p(age[j])
    F["vsol"] = vs(C1[j]) / 1e9; F["ntr"] = j; F["impact"] = P[j] / np.where(j > 0, P[np.maximum(j - 1, 0)], P[j]) - 1
    for w in (1, 3, 10, 30, 75, 450):
        lo = np.searchsorted(S, S[j] - w + (1 if w == 1 else 0))
        F[f"flow{w}"] = cdv[jj] - cdv[lo]; F[f"nb{w}"] = cb[jj] - cb[lo]; F[f"ns{w}"] = cs[jj] - cs[lo]; F[f"bsol{w}"] = cbs[jj] - cbs[lo]
        F[f"dpx{w}"] = P[j] / P[np.maximum(lo - 1, 0)] - 1
    # drawdown/runup over 75 / 450 slots (loop over rows; rows are sampled so it's cheap)
    for w in (75, 450):
        lo = np.searchsorted(S, S[j] - w)
        F[f"dd{w}"] = np.array([P[k] / P[l:k + 1].max() - 1 for k, l in zip(j, lo)]); F[f"ru{w}"] = np.array([P[k] / P[l:k + 1].min() - 1 for k, l in zip(j, lo)])
    F["same_before"] = j - np.searchsorted(S, S[j]); F["di_prev"] = np.where(j > 0, np.where(S[np.maximum(j - 1, 0)] == S[j], I[j] - I[np.maximum(j - 1, 0)], -1), -1)
    F["gap_prev"] = np.where(j > 0, S[j] - S[np.maximum(j - 1, 0)], -1)
    F["ucount"] = np.log1p(ucount[a + j]); F["cup"] = np.log1p(t.cup[a + j]); F["nt"] = t.nt[a + j]; F["tip"] = np.log1p(t.tip[a + j])
    pf = pflag[t.ps[a + j]]
    for k_, p in enumerate(PFL + ["nprog"]): F["p_" + p] = pf[:, k_]
    F["idx"] = I[j]
    fa, fb = t.fms[m], t.fms[m + 1]; fkey = t.fs[fa:fb].astype(np.int64) * 100000 + t.fi[fa:fb]; fside = t.fside[fa:fb]
    lo_same = np.searchsorted(fkey, S[j].astype(np.int64) * 100000); hi_ = np.searchsorted(fkey, key[j], side="right"); lo_prev = np.searchsorted(fkey, (S[j] - 1).astype(np.int64) * 100000)
    F["fail_same"] = hi_ - lo_same; F["fail_prev"] = lo_same - lo_prev
    cfb = np.r_[0, np.cumsum(fside == 1)]
    F["failbuy_2"] = cfb[hi_] - cfb[lo_prev]
    # own state
    F["mod"] = mod[j]; F["k_prev"] = ns[j]; F["since"] = since[j]
    lastnet = np.array([TR[n - 1]["net"] if n > 0 else np.nan for n in ns[j]]); F["last_net"] = lastnet
    F["last_hold"] = np.array([TR[n - 1]["hold"] if n > 0 else np.nan for n in ns[j]])
    lsp = np.searchsorted(key, np.where(ns[j] > 0, skey[np.maximum(ns[j] - 1, 0)], 0)) if len(skey) else np.zeros(len(j), int)
    F["vs_exit"] = np.where(ns[j] > 0, P[j] / P[np.minimum(lsp, len(P) - 1)] - 1, np.nan)
    lbp = np.searchsorted(key, np.where(ns[j] > 0, bkey[np.maximum(ns[j] - 1, 0)], 0)) if len(bkey) else np.zeros(len(j), int)
    F["vs_lastbuy"] = np.where(ns[j] > 0, P[j] / P[np.minimum(lbp, len(P) - 1)] - 1, np.nan)
    F["nopen"] = nopen(S[j]); F["hour"] = ((t.bt[a + j] + 5 * 3600) % 86400) // 3600
    F["creator_sold"] = np.array([0] * len(j))
    if FN is None: FN = list(F.keys())
    XS.append(np.stack([np.asarray(F[k], np.float32) for k in FN], 1)); YS.append(y[j]); WS.append(np.where(near[j], 1.0, 1 / RATE).astype(np.float32))
    MS.append(mod[j].astype(np.int8)); IDS.append(np.stack([np.full(len(j), m), a + j], 1).astype(np.int64))
X = np.concatenate(XS); y = np.concatenate(YS); w = np.concatenate(WS); mo = np.concatenate(MS); ids = np.concatenate(IDS)
np.savez(f"{llib.D}/mom_{run}.npz", X=X, y=y, w=w, mod=mo, ids=ids, fn=np.array(FN))
print(run, X.shape, "pos", int(y.sum()), "NEW pos", int(y[mo == 0].sum()), "TRK pos", int(y[mo == 1].sum()), "weighted N NEW %.0f TRK %.0f" % (w[mo == 0].sum(), w[mo == 1].sum()), flush=True)
