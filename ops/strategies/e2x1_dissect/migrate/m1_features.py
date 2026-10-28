#!/usr/bin/env python3
"""migrate agent, step 1: every ENTRABLE moment = a curve buy that takes vSOL to >= V (V in VS) without completing the curve
(first crossing and re-crossings after a dip below V-3), with CAUSAL features at that trade and labels
(curve completes within 30 s / 2 min / 10 min / ever). Non-entrable crossings (the crossing trade completes the curve) are kept
with ent=0 for the counting tables. Out: /home/moiz/sniper-data/e2x1_dissect/migrate/feat.pkl (dict: X (n x f), names, meta rows)."""
import numpy as np, pickle, time, collections, glob, json, datetime as dt
from mlib import Tape, D, pday, pkt, SLOT_S

VS = [85, 90, 95, 100, 105, 108]
WIN = [(1, 5), (5, 24), (10, 47), (30, 141), (120, 566)]          # (seconds, slots)
t0 = time.time()
T = Tape(); TR = T.T
nm = len(T.mints)
TAIL = [json.load(open(r))["tail_end_time"] for r in glob.glob("/home/moiz/sniper-data/collect/run_202610*_14*/run.json")]
TAIL = [t for t in TAIL if t < T.bt_of(T.shi)] + [T.bt_of(T.shi)]

# ---- wallet history (causal lookups)
W = np.load(D + "/wallets.npz")
cmp_bt = np.full(nm, -1, np.int64)
for m, c in T.cmp.items():
    k = T.mid.get(m)
    if k is not None: cmp_bt[k] = c["bt"]
wm = W["mint"]; w_grad = W["grad"]
t_res = np.where(w_grad, np.maximum(W["t_end"], cmp_bt[wm]), np.maximum(W["t_end"], W["t_first"] + 600))
wu = W["user"].astype(np.int64)
o = np.lexsort((t_res, wu)); wu = wu[o]; t_res = t_res[o]; wm = wm[o]
KEY = wu * (1 << 31) + t_res
cols = dict(n=np.ones(len(wu)), pnl=W["pnl"][o], ng=W["neargrad"][o].astype(float), ngg=(W["neargrad"][o] & W["grad"][o]).astype(float),
            po=W["poolopen"][o].astype(float), cp=W["completer"][o].astype(float), cs=W["compslot"][o].astype(float),
            win=(W["pnl"][o] > 0).astype(float))
CUM = {k: np.concatenate([[0.0], np.cumsum(v)]) for k, v in cols.items()}
MK = np.lexsort((wm, wu)); MKEY = wu[MK] * nm + wm[MK]            # (user, mint) -> trip row
def wstats(users, t, mint):
    """prior stats of each user at time t (trips resolved before t), excluding the current mint's trip. users: int array"""
    users = np.asarray(users, np.int64)
    lo = np.searchsorted(KEY, users * (1 << 31)); hi = np.searchsorted(KEY, users * (1 << 31) + t)
    out = {k: c[hi] - c[lo] for k, c in CUM.items()}
    j = np.searchsorted(MKEY, users * nm + mint); j = np.minimum(j, len(MKEY) - 1); r = MK[j]
    own = (MKEY[j] == users * nm + mint) & (t_res[r] < t)
    if own.any():
        for k, v in cols.items(): out[k] = out[k] - np.where(own, v[r], 0.0)
    return out

# ---- creator history
by_cre = collections.defaultdict(list)
for m, c in T.cr.items(): by_cre[c["creator"]].append((c["bt"], m))
cre_hist = {}
for cr_, lst in by_cre.items():
    lst.sort(); bts = np.array([b for b, _ in lst]); mx = np.array([T.M["mx"].get(m, 0) for _, m in lst], float)
    gb = np.array([cmp_bt[T.mid[m]] if m in T.mid else -1 for _, m in lst], np.int64)
    cre_hist[cr_] = (bts, np.concatenate([[0], np.cumsum(mx >= 78e9)]), gb)
def cstats(creator, t):
    h = cre_hist.get(creator)
    if h is None: return 0, 0, 0
    bts, cnear, gb = h
    n = int(np.searchsorted(bts, t - 1))                     # tokens created before t (excluding the current one at its bt)
    ng = int(((gb >= 0) & (gb < t)).sum())
    return n, int(cnear[n]), ng

# ---- candidates
cand = []
for m, v in T.M["mx"].items():
    cr = T.cr.get(m)
    if v < 85e9 or cr is None or cr.get("mayhem") or m not in T.mid: continue
    mg = T.mig.get(m)
    if mg and not mg["quote"].startswith("So111"): continue
    cand.append(m)
print("candidates", len(cand), time.time() - t0, flush=True)

NAMES = None; X = []; META = []
for n_, m in enumerate(cand):
    rows = T.trades(m)
    if len(rows) == 0: continue
    cr = T.cr[m]; mg = T.mig.get(m)
    vs = rows["vsol"].astype(float) / 1e9; sol = rows["sol"].astype(float) / 1e9; buy = rows["buy"] == 1
    slot = rows["slot"].astype(np.int64); bt = rows["bt"].astype(np.int64); user = rows["user"].astype(np.int64)
    tok = rows["tok"].astype(float)
    comp = np.nonzero(rows["rtok"] == 0)[0]; c = int(comp[0]) if len(comp) else None
    sg = np.where(buy, 1.0, -1.0)
    cb = np.concatenate([[0.0], np.cumsum(np.where(buy, sol, 0))]); cs_ = np.concatenate([[0.0], np.cumsum(np.where(buy, 0, sol))])
    cnb = np.concatenate([[0], np.cumsum(buy)]); cns = np.concatenate([[0], np.cumsum(~buy)])
    first50 = np.nonzero(vs >= 50)[0]; first80 = np.nonzero(vs >= 80)[0]
    t50 = bt[first50[0]] if len(first50) else None; t80 = bt[first80[0]] if len(first80) else None
    K = vs[0] * rows["vtok"][0] / 1e9 * 1e9  # placeholder, recomputed per row
    # crossing events per V (first and re-crossings)
    events = []
    for V in VS:
        below = True; ncross = 0
        above = vs >= V
        k = 0; n = len(vs)
        while k < n:
            if above[k] and below:
                if buy[k]:
                    events.append((k, V, ncross)); ncross += 1
                below = False
            elif not above[k] and not below and vs[k] < V - 3: below = True
            k += 1
    events.sort()
    # balances pass (snapshot at each event index)
    bal = collections.defaultdict(float); ev_i = 0; snaps = {}
    dev = cr["creator"]; dev_id = T.uid.get(dev, -1)
    cre_slot = cr["slot"]; snip_users = set(user[slot == cre_slot][buy[slot == cre_slot]].tolist())
    dev_sold = False
    want = sorted({e[0] for e in events})
    wi = 0
    for i in range(len(rows)):
        u = user[i]
        if buy[i]: bal[u] += tok[i]
        else:
            bal[u] -= tok[i]
            if u == dev_id: dev_sold = True
        while wi < len(want) and want[wi] == i:
            vals = np.array(list(bal.values())); keys = np.array(list(bal.keys()))
            vals = np.maximum(vals, 0); tot = vals.sum()
            srt = np.sort(vals)[::-1]
            snaps[i] = dict(top1=srt[0] / tot if tot > 0 else 0, top5=srt[:5].sum() / tot if tot > 0 else 0,
                            nhold=int((vals > tot * 1e-4).sum()), dev_share=max(bal.get(dev_id, 0), 0) / tot if tot > 0 else 0,
                            dev_sold=float(dev_sold), snip_share=sum(max(bal.get(u2, 0), 0) for u2 in snip_users) / tot if tot > 0 else 0,
                            holders=(keys[vals > 0], vals[vals > 0]))
            wi += 1
    for (k, V, ncross) in events:
        f = collections.OrderedDict()
        ent = int(rows["rtok"][k] != 0)
        Kk = vs[k] * (rows["vtok"][k] / 1e9); Vc = Kk / ((rows["vtok"][k] - rows["rtok"][k]) / 1e9) if rows["rtok"][k] else vs[k]
        t = int(bt[k]); sk = int(slot[k])
        f["V"] = V; f["vsol"] = vs[k]; f["sol_left"] = max(Vc - vs[k], 0); f["ncross"] = ncross
        f["cross_sol"] = sol[k]; f["age_s"] = t - cr["bt"]; f["t_since50"] = t - t50 if t50 is not None else -1
        f["t_since80"] = t - t80 if t80 is not None else -1
        f["n_tr"] = k + 1; f["n_buys"] = cnb[k + 1]; f["n_sells"] = cns[k + 1]; f["buy_sol_tot"] = cb[k + 1]; f["sell_sol_tot"] = cs_[k + 1]
        f["vmax_prev"] = vs[:k].max() if k else vs[k]; f["dd"] = vs[k] / max(f["vmax_prev"], 1e-9)
        for (sec, nsl) in WIN:
            a = int(np.searchsorted(slot, sk - nsl, "left"))
            f[f"net{sec}"] = cb[k + 1] - cb[a] - (cs_[k + 1] - cs_[a]); f[f"buy{sec}"] = cb[k + 1] - cb[a]; f[f"sell{sec}"] = cs_[k + 1] - cs_[a]
            f[f"nb{sec}"] = cnb[k + 1] - cnb[a]; f[f"ns{sec}"] = cns[k + 1] - cns[a]
            w = slice(a, k + 1); bb = buy[w]
            f[f"ub{sec}"] = len(set(user[w][bb].tolist())); f[f"maxb{sec}"] = sol[w][bb].max() if bb.any() else 0.0
        sn = snaps[k]
        for kk in ("top1", "top5", "nhold", "dev_share", "dev_sold", "snip_share"): f[kk] = sn[kk]
        f["dev_prior_n"], f["dev_prior_near"], f["dev_prior_grad"] = cstats(dev, cr["bt"])
        # buyer quality: buyers in the last 10 s (incl. the crossing trade) and current holders
        a = int(np.searchsorted(slot, sk - 47, "left")); w = slice(a, k + 1); bb = buy[w]
        bu = user[w][bb]; bs = sol[w][bb]
        uu, inv = np.unique(bu, return_inverse=True); usol = np.bincount(inv, weights=bs)
        st = wstats(uu, t, T.mid[m])
        f["b10_n_known"] = int((st["n"] >= 3).sum()); f["b10_pnl"] = float(st["pnl"].sum()); f["b10_pnl_w"] = float((st["pnl"] * usol).sum() / max(usol.sum(), 1e-9))
        f["b10_ngrate"] = float(((st["ngg"] + 1) / (st["ng"] + 2) * usol).sum() / max(usol.sum(), 1e-9))
        f["b10_ng_n"] = float(st["ng"].sum()); f["b10_ngg_n"] = float(st["ngg"].sum())
        f["b10_completer_max"] = float(st["cp"].max()); f["b10_compslot_max"] = float(st["cs"].max()); f["b10_poolopen_max"] = float(st["po"].max())
        f["b10_bots_po"] = int((st["po"] >= 3).sum()); f["b10_sol_po"] = float(usol[st["po"] >= 3].sum())
        f["b10_winrate"] = float(((st["win"] + 1) / (st["n"] + 2) * usol).sum() / max(usol.sum(), 1e-9))
        # crossing trade's own wallet
        st1 = wstats([user[k]], t, T.mid[m])
        for kk in ("n", "pnl", "ng", "ngg", "cp", "po"): f[f"cx_{kk}"] = float(st1[kk][0])
        # holders: known pool-open bots / completers holding now
        hk, hv = sn["holders"]
        if len(hk):
            sh = wstats(hk, t, T.mid[m]); tot = hv.sum()
            f["hold_po_share"] = float(hv[sh["po"] >= 3].sum() / tot); f["hold_cp_share"] = float(hv[sh["cp"] >= 2].sum() / tot)
            f["hold_known_share"] = float(hv[sh["n"] >= 5].sum() / tot); f["hold_pnl_w"] = float((sh["pnl"] * hv).sum() / tot)
            f["hold_ngrate_w"] = float(((sh["ngg"] + 1) / (sh["ng"] + 2) * hv).sum() / tot)
        else:
            for kk in ("hold_po_share", "hold_cp_share", "hold_known_share", "hold_pnl_w", "hold_ngrate_w"): f[kk] = 0.0
        pk_ = pkt(t); f["hour"] = pk_.hour + pk_.minute / 60; f["wday"] = pk_.weekday()
        if NAMES is None: NAMES = list(f.keys())
        X.append([float(f[q]) for q in NAMES])
        tc = (slot[c] - sk) * SLOT_S if c is not None else np.inf
        META.append(dict(mint=m, k=int(k), V=V, ent=ent, c=c, t_complete=tc, day=pday(t), bt=t, slot=sk,
                         edge=any(tt - 2100 <= t <= tt for tt in TAIL), has_mig=mg is not None, grad=c is not None,
                         cross_completes=(c == k), ncross=ncross))
    if n_ % 500 == 0: print(n_, len(X), f"{time.time() - t0:.0f}s", flush=True)
X = np.array(X, np.float32)
pickle.dump(dict(X=X, names=NAMES, meta=META), open(D + "/feat.pkl", "wb"))
print("rows", len(X), "features", len(NAMES), f"{time.time() - t0:.0f}s", flush=True)
