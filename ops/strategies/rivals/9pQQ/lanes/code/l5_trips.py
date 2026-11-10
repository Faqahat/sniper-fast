#!/usr/bin/env python3
"""LANES step 5: one row per 9pQQ round trip (all 5 runs) with decision-time BUY features, SELL features, P&L.
Decision time = chain order: only tape rows strictly before its tx (slot, index). -> lanes/trips_<run>.pkl (list of dicts) + fails_<run>.pkl
usage: l5_trips.py RUN"""
import sys, json, pickle, collections, re, numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/rivals/9pQQ/lanes/code")
import llib
run = sys.argv[1]; W = llib.W; K = llib.K; V = llib.V
t = llib.load(run, failed=True); L = llib.launches(run)
own = []
for l in open(f"{llib.D}/own_{run}.jsonl"):
    d = json.loads(l); ix = d.get("ixn") or []
    mm = collections.Counter()
    for m, ow, pre, post in d.get("tb") or []:
        if ow == W: mm[m] += (post or 0) - (pre or 0)
    m = max(mm, key=lambda k: abs(mm[k])) if mm else next((x for x in d.get("mints") or [] if not x.startswith("So111")), None)
    if d.get("err") is not None:
        kind = "fbuy" if any(x.startswith("Buy") for x in ix) else ("fsell" if any(x.startswith("Sell") for x in ix) else "fother")
        code = re.search(r'"Custom":\s*(\d+)', json.dumps(d["err"])); code = int(code.group(1)) if code else -1
    else:
        kind = "buy" if mm.get(m, 0) > 0 else ("sell" if mm.get(m, 0) < 0 else "other"); code = None
    sol = dict((a, v) for a, v in d.get("sd") or []).get(W, 0)
    rent = 0
    if kind == "buy" and "InitializeAccount3" in ix:
        rent = 1513840 if any(p.startswith("TokenzQd") for p in d.get("progs") or []) else 2039280
    own.append(dict(s=d["s"], i=d.get("i") or 0, bt=d.get("bt") or 0, sig=d["sig"], kind=kind, mint=m, tok=mm.get(m, 0), sol=sol, rent=rent,
                    code=code, amm=any(p.startswith("pAMMBay") for p in d.get("progs") or []), ix=",".join(x for x in ix if x not in ("GetAccountDataSize", "InitializeImmutableOwner", "InitializeAccount3", "TransferChecked"))))
own.sort(key=lambda x: (x["s"], x["i"]))
s_lo, s_hi = int(t.s.min()), int(t.s.max())
def vs(c): return K / (np.asarray(c, float) + V)
def price(c): c = np.asarray(c, float) + V; return (K / c) / c
# trips
openpos = {}; trips = []; fails = []; nopen = 0
for x in own:
    if x["kind"] == "buy":
        if x["mint"] in openpos: openpos[x["mint"]]["dup"] = True; continue
        openpos[x["mint"]] = dict(b=x, nopen=len(openpos))
    elif x["kind"] == "sell":
        p = openpos.pop(x["mint"], None)
        if p: trips.append(dict(b=p["b"], sx=x, nopen=p["nopen"]))
    elif x["kind"] in ("fbuy", "fsell"): fails.append(x)
openleft = len(openpos)
mint_trips = collections.defaultdict(list)
for tr in trips: mint_trips[tr["b"]["mint"]].append(tr)
rows = []
for mint, TR in mint_trips.items():
    if mint not in t.mix: continue
    m = t.mix[mint]; a, b = t.ms[m], t.ms[m + 1]
    S = t.s[a:b]; I = t.i[a:b]; U = t.u[a:b]; CPRE = t.cpre[a:b]; CPOST = t.cpost[a:b]; BT = t.bt[a:b]; PS = t.ps[a:b]; NT = t.nt[a:b]; TIP = t.tip[a:b]
    key = S.astype(np.int64) * 100000 + I
    DV = vs(CPOST) - vs(CPRE)           # +SOL into curve = buy
    PR = price(CPOST)
    isown = U == t.wid; outside = ~isown
    fa, fb = t.fms[m], t.fms[m + 1]; FS = t.fs[fa:fb]; FI = t.fi[fa:fb]; FU = t.fu[fa:fb]; FSIDE = t.fside[fa:fb]
    fkey = FS.astype(np.int64) * 100000 + FI
    la = L.get(mint)
    prev_sell = None; prev_net = None; prev_exit_px = None; k_prev = 0
    for tr in TR:
        B, Sx = tr["b"], tr["sx"]
        pb = int(np.searchsorted(key, B["s"] * 100000 + B["i"])); ps_ = int(np.searchsorted(key, Sx["s"] * 100000 + Sx["i"]))
        if pb >= len(key) or key[pb] != B["s"] * 100000 + B["i"]: continue
        r = dict(run=run, mint=mint, bs=B["s"], bi=B["i"], bbt=B["bt"], ss=Sx["s"], si=Sx["i"], sbt=Sx["bt"], bsig=B["sig"], ssig=Sx["sig"],
                 spend=-B["sol"], net=(B["sol"] + Sx["sol"] + B["rent"]) / 1e9, amm_exit=Sx["amm"], nopen=tr["nopen"], ix_b=B["ix"], ix_s=Sx["ix"])
        r["size"] = round(-DV[pb], 3) if False else float(DV[pb])
        r["age"] = (B["s"] - la["slot"]) if la else -1
        r["may"] = bool(la["may"]) if la else None
        r["creator"] = la["creator"] if la else None
        c0 = CPRE[pb]; r["vsol"] = float(vs(c0)) / 1e9; r["px0"] = float(price(c0))
        # outside trades strictly before own buy
        ob = np.nonzero(outside[:pb])[0]
        r["ntr_before"] = int(pb)
        if len(ob):
            j = ob[-1]
            r.update(tg_side=1 if DV[j] > 0 else -1, tg_sol=float(DV[j]) / 1e9, tg_ds=int(B["s"] - S[j]), tg_di=int(B["i"] - I[j]) if S[j] == B["s"] else None,
                     tg_u=t.users[U[j]], tg_ps=t.psets[PS[j]], tg_nt=int(NT[j]), tg_tip=int(TIP[j]))
            # number of outside trades between trigger-slot start and own
        for w in (3, 10, 75, 450):
            sel = ob[S[ob] >= B["s"] - w]
            r[f"buys{w}"] = int((DV[sel] > 0).sum()); r[f"sells{w}"] = int((DV[sel] < 0).sum()); r[f"flow{w}"] = float(DV[sel].sum()) / 1e9
            r[f"maxsell{w}"] = float(-DV[sel].min()) / 1e9 if len(sel) else 0.0
            r[f"maxbuy{w}"] = float(DV[sel].max()) / 1e9 if len(sel) else 0.0
            pr = PR[:pb][S[:pb] >= B["s"] - w]
            r[f"dpx{w}"] = float(r["px0"] / pr[0] - 1) if len(pr) else 0.0
            r[f"dd{w}"] = float(r["px0"] / pr.max() - 1) if len(pr) else 0.0
            r[f"ru{w}"] = float(r["px0"] / pr.min() - 1) if len(pr) else 0.0
        same = ob[S[ob] == B["s"]]; r["n_same_before"] = int(len(same))
        r["n_prev_slot"] = int((S[ob] == B["s"] - 1).sum())
        # failed txs on the mint before own buy, this slot & previous
        fsel = (fkey < B["s"] * 100000 + B["i"]) & (FS >= B["s"] - 1); r["fails_before"] = int(fsel.sum())
        r["fails_buy_before"] = int((fsel & (FSIDE == 1)).sum()); r["fails_same"] = int(((fkey < B["s"] * 100000 + B["i"]) & (FS == B["s"])).sum())
        # re-entry state
        r["k_prev"] = k_prev; r["since_sell"] = (B["s"] - prev_sell) if prev_sell else -1; r["prev_net"] = prev_net
        r["vs_exit"] = float(r["px0"] / prev_exit_px - 1) if prev_exit_px else None
        # sell side
        r["hold"] = int(Sx["s"] - B["s"]); r["hold_s"] = int(Sx["bt"] - B["bt"])
        if ps_ < len(key) and key[ps_] == Sx["s"] * 100000 + Sx["i"]:
            cs = CPRE[ps_]; r["ret"] = float(price(cs) / r["px0"] - 1)
            hold_pr = PR[pb + 1:ps_]
            r["maxret"] = float(hold_pr.max() / r["px0"] - 1) if len(hold_pr) else 0.0
            r["minret"] = float(hold_pr.min() / r["px0"] - 1) if len(hold_pr) else 0.0
            os_ = np.nonzero(outside[pb + 1:ps_])[0] + pb + 1
            r["hold_trades"] = int(len(os_))
            if len(os_):
                j = os_[-1]; r.update(sx_side=1 if DV[j] > 0 else -1, sx_sol=float(DV[j]) / 1e9, sx_ds=int(Sx["s"] - S[j]), sx_di=int(Sx["i"] - I[j]) if S[j] == Sx["s"] else None, sx_u=t.users[U[j]])
                r["hold_flow"] = float(DV[os_].sum()) / 1e9
                r["last_buy_gap"] = int(Sx["s"] - S[os_[DV[os_] > 0][-1]]) if (DV[os_] > 0).any() else r["hold"]
            # after-sell move (25 / 150 slots)
            for w in (25, 150):
                aft = PR[ps_ + 1:][S[ps_ + 1:] <= Sx["s"] + w]
                r[f"post{w}"] = float(aft[-1] / price(cs) - 1) if len(aft) else 0.0
            r["sell_fails_before"] = int(((fkey < Sx["s"] * 100000 + Sx["i"]) & (FS >= Sx["s"] - 1)).sum())
        k_prev += 1; prev_sell = Sx["s"]; prev_net = r["net"]
        if ps_ < len(key): prev_exit_px = float(price(CPRE[ps_]))
        rows.append(r)
rows.sort(key=lambda r: (r["bs"], r["bi"]))
hours = (int(t.bt.max()) - int(t.bt.min())) / 3600
pickle.dump(dict(rows=rows, fails=fails, hours=hours, openleft=openleft, own_counts=collections.Counter(x["kind"] for x in own)), open(f"{llib.D}/trips_{run}.pkl", "wb"))
print(run, len(rows), "trips", round(sum(r["net"] for r in rows), 2), "SOL", round(hours, 2), "h", collections.Counter(x["kind"] for x in own), flush=True)
