#!/usr/bin/env python3
# PANIC-SELL BOUNCE (read-only, offline): the owner's spec (2026-10-23).
#   dump   = one sell >= ~1 SOL that drops the price >= 5%
#   score  = bounce likelihood from facts known at the dump: drop size, sell size, token age, run-up before the dump,
#            buys in the last 3 s by PROFITABLE wallets (realized profit on their earlier, already-finished tokens:
#            leak-free), activity so far, curve size, dev / bundle; only the top 4% of dumps (threshold from BUILD) trade
#   trade  = 0.5 SOL right behind the dump (also 1 and 2 trades later: our buy does not always land next); skip if the
#            price already bounced > 2%; sell at +8% / -5% (price) or after 1.3 s, whichever first
# Exact curve replay (our own impact, pump fee per side from the events) + fixed cost per round trip. Score learned on
# BUILD (run 1, first 80% train / last 20% early stop + threshold), reported on TEST (forward run, never used).
# usage: python3 dump_bounce.py <table.jsonl.gz> <phaseA dirs,> <launches,> <run2 start bt> <out dir>
import sys, os, json, gzip, glob, zlib, collections, math
import numpy as np
from multiprocessing import Pool
TAB, PAS, LJS, FWD0, OUT = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), sys.argv[5]; os.makedirs(OUT, exist_ok=True)
X = 493827160; SPS = 5; MIN_SELL = 1e9; MIN_DROP = 0.05; TP, SL, HOLD = 0.08, 0.05, 7      # 1.3 s ~ 7 slots (5 slots/s, as training)
FIXES = [float(x) for x in os.environ.get("FIXES", "0.0015,0.015").split(",")]; TOPQ = float(os.environ.get("TOPQ", "0.04"))
L = {}
for p in LJS.split(","):
    for l in open(p):
        try: c = json.loads(l)
        except Exception: continue
        L.setdefault(c["mint"], c)
INFO = {}
for l in gzip.open(TAB, "rt"):
    r = json.loads(l)
    if r.get("quote_sol") == 1 and (r.get("max_vsol") or 0) <= 200 and r.get("bt") and r.get("n_trades", 0) >= 5 and r["mint"] in L:
        INFO[r["mint"]] = dict(bt=r["bt"], dev=r.get("dev_buy") or 0, gn=r.get("glued_n") or 0, gs=r.get("glued_sol") or 0)
def bucket(m): return zlib.crc32(m.encode()) % 256

def trade(tr, k0, fb, cb):
    """our 0.5 SOL buy into the state after tr[k0-1]; +8% / -5% on price or 1.3 s; None if the curve fills meanwhile"""
    st = tr[k0 - 1]; V, T = st[7], st[9]
    if not T or V >= 114e9: return None
    p_in = V / T; q = T * X // (V + X); V += X; T -= q; cost = X * (1 + (fb + cb) / 1e4); S0 = st[0]
    val = lambda V, T: (V * q // (T + q)) * (1 - (fb + cb) / 1e4) / cost - 1
    for t in tr[k0:]:
        if t[0] - S0 > HOLD: return val(V, T)
        if t[7] >= 114e9: return None
        if t[5]: dd = T * t[6] // (V + t[6]); V += t[6]; T -= dd
        else: so = V * t[8] // (T + t[8]); V -= so; T += t[8]
        p = (V - X) / (T + q) if T + q else p_in                   # market price without our own tokens
        if p >= p_in * (1 + TP) or p <= p_in * (1 - SL): return val(V, T)
    return val(V, T)

def work(b):
    tgt = {m for m in INFO if bucket(m) == b}; ev = []; pnl = []
    if not tgt: return ev, pnl
    rows = collections.defaultdict(list); seen = set()
    for pa in PAS.split(","):
        for f in glob.glob(os.path.join(pa, f"b{b:03d}", "*.jsonl.gz")):
            try:
                for line in gzip.open(f, "rt"):
                    if line[2] != "T": continue
                    r = json.loads(line)
                    if r[1] not in tgt or (r[5], r[13]) in seen: continue
                    seen.add((r[5], r[13]))
                    rows[r[1]].append((r[2], r[3], r[13], r[5], r[14], r[15] == 1, r[16], r[18], r[17], r[19], r[22], r[23]))
            except (EOFError, OSError, zlib.error): pass
    for m, tr in rows.items():
        tr.sort(); c = L[m]; S = c["slot"]; I = INFO[m]
        creator = c.get("creator") or c.get("user"); ins = {creator, c.get("user"), c.get("payer")}
        ci = c.get("idx"); prev = ci; gi = 0
        for k, t in enumerate(tr):
            if t[3] == c.get("sig"): gi = k + 1; continue
            if t[0] == S and t[1] in (prev, prev + 1) and t[5]: ins.add(t[4]); prev = t[1]; gi = k + 1
            elif t[0] == S and t[1] > prev + 1: break
            elif t[0] > S: break
        if gi == 0 or not tr[gi - 1][9]: continue
        fb, cb = (tr[0][10] or 95), (tr[0][11] or 30)
        P0 = tr[gi - 1][7] / tr[gi - 1][9]
        # per-wallet realized result on this token within 10 min (for the leak-free "profitable wallet" history)
        w = collections.defaultdict(lambda: [0, 0, 0])            # sol in, sol out, trades
        for t in tr:
            if t[0] - S > 2860: break
            a = w[t[4]]; a[2] += 1
            if t[5]: a[0] += t[6]
            else: a[1] += t[6]
        pnl.append((I["bt"] + 600, [(u, (a[1] - a[0]) / 1e9) for u, a in w.items() if a[0] > 0 and a[1] > 0]))
        px = [(t[7] / t[9]) if t[9] else None for t in tr]
        nb = ns = 0; peak = P0; buys = collections.deque()
        for k in range(gi, len(tr)):
            t = tr[k]; d = t[0] - S
            if d > 1500: break                                     # dumps in the first 5 minutes
            if t[7] >= 114e9: break
            pb = px[k - 1] if px[k - 1] else P0; p = px[k]
            while buys and t[0] - buys[0][0] > 15: buys.popleft()  # last ~3 s of buys
            if not t[5] and t[6] >= MIN_SELL and p and pb and p <= pb * (1 - MIN_DROP):
                drop = 1 - p / pb
                ret = {}
                for lag in (1, 2, 3):                              # our buy right behind the dump / 1 / 2 trades later
                    k0 = k + lag
                    if k0 > len(tr): continue
                    if lag > 1 and px[k0 - 1] and px[k0 - 1] > p * 1.02: ret[lag] = "skip"; continue   # already bounced > 2%
                    v = trade(tr, k0, fb, cb)
                    if v is not None: ret[lag] = v
                if 1 in ret and ret[1] != "skip":
                    ev.append(dict(m=m, t=I["bt"] + d / SPS, fwd=I["bt"] >= FWD0, slot=t[0],
                                   f=dict(drop=drop, sell_sol=t[6] / 1e9, age_s=d / SPS, runup=pb / P0, runup_peak=pb / peak, from_peak=p / peak, vsol=t[7] / 1e9,
                                          nb=nb, ns=ns, buys3=len(buys), buys3_sol=sum(x[1] for x in buys) / 1e9, seller_insider=int(t[4] in ins),
                                          dev=I["dev"], gn=I["gn"], gs=I["gs"]),
                                   buyers3=[x[2] for x in buys], ret=ret))
            if t[5]:
                buys.append((t[0], t[6], t[4]))
                if t[4] not in ins: nb += 1
            else: ns += 1
            if p and p > peak: peak = p
    return ev, pnl

if __name__ == "__main__":
    # FREEZE for the live paper trader: events + leak-free wallet history exactly as the backtest, model trained on ALL
    # data (time-ordered: first 80% train, last 20% early stop + top-4% threshold); saves the model and the wallet history
    with Pool(14) as pool: parts = pool.map(work, range(256))
    EV = sorted((e for ev, _ in parts for e in ev), key=lambda e: e["t"]); PN = sorted((x for _, pn in parts for x in pn), key=lambda x: x[0])
    hist = collections.defaultdict(lambda: [0, 0.0]); j = 0
    for e in EV:
        while j < len(PN) and PN[j][0] <= e["t"]:
            for u, r in PN[j][1]: h = hist[u]; h[0] += 1; h[1] += r
            j += 1
        good = [u for u in e["buyers3"] if hist[u][0] >= 5 and hist[u][1] > 0]
        e["f"]["pbots3"] = len(set(good)); e["f"]["pbots3_share"] = len(set(good)) / max(len(set(e["buyers3"])), 1); del e["buyers3"]
    while j < len(PN):                                         # history up to the end of the data (the paper trader continues from here)
        for u, r in PN[j][1]: h = hist[u]; h[0] += 1; h[1] += r
        j += 1
    H = os.path.dirname(os.path.abspath(__file__))
    esrc = open(os.path.join(H, "e_model.py")).read(); ns_ = {"np": np, "collections": collections}; exec(esrc[esrc.index("def binize("):esrc.index("REPORT = {}")], ns_)
    FK = sorted(EV[0]["f"]); Xm = np.array([[e["f"][k] if e["f"][k] is not None else np.nan for k in FK] for e in EV], float)
    idx = np.arange(len(EV)); TRN = idx < int(len(EV) * .8); HOL = ~TRN
    edges = []
    for jj in range(Xm.shape[1]):
        x = Xm[:, jj]; xt = x[TRN & ~np.isnan(x)]
        edges.append(np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])).tolist() if len(xt) else [])
    Bm = np.zeros(Xm.shape, np.int16)
    for jj in range(Xm.shape[1]):
        b = np.searchsorted(np.array(edges[jj]), Xm[:, jj], side="right") + 1; b[np.isnan(Xm[:, jj])] = 0; Bm[:, jj] = b
    r1 = np.array([e["ret"][1] for e in EV]); y = ((r1 * 0.5 - FIXES[0]) > 0).astype(float)
    trees, f = ns_["fit"](Bm, y, TRN, HOL)
    p0 = y[TRN].mean(); thr = float(np.quantile(f[HOL], 1 - TOPQ))
    sel = HOL & (f >= thr); v = r1[sel] * 0.5 - FIXES[0]
    print(f"frozen on {len(EV)} dumps: {len(trees)} trees, {len(FK)} features; holdout top {TOPQ:.0%}: {sel.sum()} trades, win {(v > 0).mean():.0%}, mean {v.mean():+.4f} SOL (instant sell, right behind)")
    json.dump(dict(kind="dump_bounce", features=FK, edges=edges, trees=trees, F0=float(np.log(p0 / (1 - p0))), lr=0.05, threshold=thr, topq=TOPQ,
                   min_sell=MIN_SELL, min_drop=MIN_DROP, tp=TP, sl=SL, hold_slots=HOLD, trained_on="run_20261021_2207 + run_20261022_1543", n_events=len(EV)),
              open(os.path.join(OUT, "frozen_dump_bounce.json"), "w"))
    json.dump({u: h for u, h in hist.items() if h[0] >= 2}, open(os.path.join(OUT, "wallet_hist_seed.json"), "w"))
    print("wallet history saved:", sum(1 for h in hist.values() if h[0] >= 2), "wallets (2+ finished tokens)")
