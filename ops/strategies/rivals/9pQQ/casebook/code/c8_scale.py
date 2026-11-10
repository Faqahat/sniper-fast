#!/usr/bin/env python3
"""CASEBOOK step 8: scale event table from the LANES merged tape (curve trades, all tokens launched in the run).
One row per outside landed curve trade on a non-own signer; decision-time state; labels:
  tb = this trade is the trigger of a 9pQQ landed buy (last outside trade before its buy, same/prev slot)
  ts = trigger of a 9pQQ landed sell;  tf = trigger of a 9pQQ FAILED buy
usage: c8_scale.py RUN   -> casebook/scale_<run>.npz
memory: streams per column; ~1.5 GB peak."""
import sys, json, numpy as np, collections
D = "/home/it/sniper-data/rivals/9pQQ/casebook"; LT = "/home/it/sniper-data/rivals/9pQQ/lanes"; COL = "/data/tapes/collect"
W = "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN"; K = 30e9 * 1073e12
run = sys.argv[1]
z = np.load(f"{LT}/tape_{run}.npz")
mints = z["mints"]; users = z["users"]
fl = z["fl"]; keep = (fl & 1) == 1
s = z["s"][keep]; i = z["i"][keep].astype(np.int64); bt = z["bt"][keep]; u = z["u"][keep]; m = z["m"][keep]
tok = z["tok"][keep]; sol = z["sol"][keep]; cpost = z["cpost"][keep]; cpre = z["cpre"][keep]
ps = z["ps"][keep]; nt = z["nt"][keep]; cup = z["cup"][keep]; tip = z["tip"][keep]
o = np.lexsort((i, s, m)); s, i, bt, u, m, tok, sol, cpost, cpre, ps, nt, cup, tip = [x[o] for x in (s, i, bt, u, m, tok, sol, cpost, cpre, ps, nt, cup, tip)]
N = len(s); print("rows", N, flush=True)
wid = int(np.where(users == W)[0][0]) if W in set(users.tolist()) else -1
own = u == wid
buy = tok > 0
size = np.abs(sol) / 1e9
vtok = (cpost + 73e12); mc = (K / vtok) / vtok * 1e6  # vsol/vtok*1e6
vtok_pre = cpre + 73e12; mc_pre = (K / vtok_pre) / vtok_pre * 1e6
vsol = K / vtok / 1e9
# launch slot per mint
L = {}
for l in open(f"{COL}/{run}/launches.jsonl"):
    d = json.loads(l); L[d["mint"]] = (d["slot"], "mayhem" in l.lower() and '"is_mayhem_mode":true' in l)
mint_l = np.array([L.get(x, (-1, False))[0] for x in mints]); age = s - mint_l[m]
# segment boundaries per mint
starts = np.r_[0, np.where(np.diff(m) != 0)[0] + 1]; ends = np.r_[starts[1:], N]
seg = np.repeat(np.arange(len(starts)), ends - starts)
# own state per row: walk own rows per mint
holding = np.zeros(N, bool); ntrips = np.zeros(N, np.int32); since_sell = np.full(N, -1, np.int64); vs_exit = np.full(N, np.nan); since_buy = np.full(N, -1, np.int64)
ret = np.full(N, np.nan)
tb = np.zeros(N, bool); ts = np.zeros(N, bool)
own_idx = np.where(own)[0]
own_by_seg = collections.defaultdict(list)
for k in own_idx: own_by_seg[seg[k]].append(k)
for g, ks in own_by_seg.items():
    a, b = starts[g], ends[g]
    h = False; nt_ = 0; ls = None; lex = None; lb = None; emc = None; cur = a
    for k in ks + [b]:
        sl = slice(cur, k)
        holding[sl] = h; ntrips[sl] = nt_
        if ls is not None: since_sell[sl] = s[sl] - ls; vs_exit[sl] = (mc[sl] / lex - 1) * 100
        if h: since_buy[sl] = s[sl] - lb; ret[sl] = (mc[sl] / emc - 1) * 100
        if k == b: break
        # trigger label: last non-own row before k
        j = k - 1
        while j >= a and own[j]: j -= 1
        if j >= a and s[k] - s[j] <= 1:
            if buy[k]: tb[j] = True
            else: ts[j] = True
        if buy[k]: h = True; lb = s[k]; emc = mc[k]
        else: h = False; nt_ += 1; ls = s[k]; lex = mc_pre[k]
        holding[k] = h; cur = k + 1
# window features via per-mint cumulative sums (searchsorted on (seg, s))
key = seg.astype(np.int64) * (1 << 32) + s
def back(k):
    return np.searchsorted(key, key - k, side="left")  # first index with slot >= s-k in same mint
out_ = ~own
flow = np.where(out_, np.where(buy, size, -size), 0.0); cf = np.r_[0, np.cumsum(flow)]
cnt = out_.astype(np.int64); cc = np.r_[0, np.cumsum(cnt)]
cb = (out_ & buy).astype(np.int64); ccb = np.r_[0, np.cumsum(cb)]
idx = np.arange(N)
feat = {}
for k in (3, 10, 75):
    j = back(k); feat[f"nf{k}"] = (cf[idx] - cf[j]).astype(np.float32); feat[f"n{k}"] = (cc[idx] - cc[j]).astype(np.int32); feat[f"nb{k}"] = (ccb[idx] - ccb[j]).astype(np.int32)
j10 = back(10); feat["ch10"] = ((mc_pre / mc_pre[j10]) - 1).astype(np.float32) * 100
j50 = back(50); feat["ch50"] = ((mc_pre / mc_pre[j50]) - 1).astype(np.float32) * 100
first = np.zeros(N, bool); first[starts] = True
gap = np.r_[0, np.diff(s)]; gap[first] = -1
ntr = idx - starts[seg]  # trades so far on token
# user activity: global trade count so far (bot-ness) in this run
uo = np.lexsort((i, s, u)); uc_sorted = np.zeros(N, np.int32)
us = u[uo]; ust = np.r_[0, np.where(np.diff(us) != 0)[0] + 1]
uc_sorted = np.arange(N) - np.repeat(ust, np.diff(np.r_[ust, N]))
ucnt = np.empty(N, np.int32); ucnt[uo] = uc_sorted
utot = np.bincount(u, minlength=len(users))[u]
# failed txs per (mint, slot): failed buys/sells on curve
fm = z["fm"]; fs_ = z["fs"]; fside = z["fside"]; fcode = z["fcode"]
fk = fm.astype(np.int64) * (1 << 34) + fs_
fk_sorted = np.sort(fk)
mk = m.astype(np.int64) * (1 << 34)
fail_slot = np.searchsorted(fk_sorted, mk + s, "right") - np.searchsorted(fk_sorted, mk + s, "left")
fail_prev = np.searchsorted(fk_sorted, mk + s - 1, "right") - np.searchsorted(fk_sorted, mk + s - 1, "left")
# own failed buys -> tf label
fu = z["fu"]; wf = (fu == wid) & (fside == 1) if wid >= 0 else np.zeros(len(fu), bool)
tf = np.zeros(N, bool)
key3 = (m.astype(np.int64) << 42) | (s << 13) | np.minimum(i, 8191)
fq = (fm[wf].astype(np.int64) << 42) | (fs_[wf] << 13) | np.minimum(z["fi"][wf].astype(np.int64), 8191)
for q, fmm, fss in zip(fq, fm[wf], fs_[wf]):
    j = np.searchsorted(key3, q) - 1
    while j >= 0 and m[j] == fmm and own[j]: j -= 1
    if j >= 0 and m[j] == fmm and fss - s[j] <= 1: tf[j] = True
np.savez(f"{D}/scale_{run}.npz", s=s, i=i, bt=bt, u=u, m=m, buy=buy, size=size.astype(np.float32), mc=mc.astype(np.float32), mc_pre=mc_pre.astype(np.float32),
         vsol=vsol.astype(np.float32), age=age, own=own, holding=holding, ntrips=ntrips, since_sell=since_sell, vs_exit=vs_exit.astype(np.float32),
         since_buy=since_buy, ret=ret.astype(np.float32), tb=tb, ts=ts, tf=tf, gap=gap, ntr=ntr, ucnt=ucnt, utot=utot, ps=ps, nt=nt, cup=cup, tip=tip,
         fail_slot=fail_slot.astype(np.int32), fail_prev=fail_prev.astype(np.int32), seg=seg, **feat, users=users, mints=mints, psets=z["psets"])
print("saved; own", own.sum(), "tb", tb.sum(), "ts", ts.sum(), "tf", tf.sum(), flush=True)
