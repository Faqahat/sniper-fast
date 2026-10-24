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

EXG = [(tp, sl, h) for tp in (0.05, 0.08, 0.12, 0.20) for sl in (0.03, 0.05, 0.08) for h in (3, 7, 12, 25)]   # take-profit, stop-loss, max hold (slots)
def trade(tr, k0, fb, cb, TP=TP, SL=SL, HOLD=HOLD, why=False):
    """our 0.5 SOL buy into the state after tr[k0-1]; +TP / -SL on price or HOLD slots; None if the curve fills meanwhile"""
    st = tr[k0 - 1]; V, T = st[7], st[9]
    if not T or V >= 114e9: return None
    p_in = V / T; q = T * X // (V + X); V += X; T -= q; cost = X * (1 + (fb + cb) / 1e4); S0 = st[0]
    val = lambda V, T: (V * q // (T + q)) * (1 - (fb + cb) / 1e4) / cost - 1
    for t in tr[k0:]:
        if t[0] - S0 > HOLD: return (val(V, T), "time", t[0] - S0) if why else val(V, T)
        if t[7] >= 114e9: return None
        if t[5]: dd = T * t[6] // (V + t[6]); V += t[6]; T -= dd
        else: so = V * t[8] // (T + t[8]); V -= so; T += t[8]
        p = (V - X) / (T + q) if T + q else p_in                   # market price without our own tokens
        if p >= p_in * (1 + TP): return (val(V, T), "profit", t[0] - S0) if why else val(V, T)
        if p <= p_in * (1 - SL): return (val(V, T), "loss", t[0] - S0) if why else val(V, T)
    return (val(V, T), "end", 0) if why else val(V, T)

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
                    ex = {}
                    for g in EXG:
                        z = trade(tr, k + 1, fb, cb, *g, why=True)
                        if z is not None: ex[g] = z
                    ev.append(dict(m=m, t=I["bt"] + d / SPS, fwd=I["bt"] >= FWD0, slot=t[0],
                                   f=dict(drop=drop, sell_sol=t[6] / 1e9, age_s=d / SPS, runup=pb / P0, runup_peak=pb / peak, from_peak=p / peak, vsol=t[7] / 1e9,
                                          nb=nb, ns=ns, buys3=len(buys), buys3_sol=sum(x[1] for x in buys) / 1e9, seller_insider=int(t[4] in ins),
                                          dev=I["dev"], gn=I["gn"], gs=I["gs"]),
                                   buyers3=[x[2] for x in buys], ret=ret, ex=ex))
            if t[5]:
                buys.append((t[0], t[6], t[4]))
                if t[4] not in ins: nb += 1
            else: ns += 1
            if p and p > peak: peak = p
    return ev, pnl

if __name__ == "__main__":
    with Pool(14) as pool: parts = pool.map(work, range(256))
    EV = sorted((e for ev, _ in parts for e in ev), key=lambda e: e["t"]); PN = sorted((x for _, pn in parts for x in pn), key=lambda x: x[0])
    # leak-free profitable-wallet feature: wallets whose realized result on earlier, finished tokens is > 0 over >= 5 tokens
    hist = collections.defaultdict(lambda: [0, 0.0]); j = 0
    for e in EV:
        while j < len(PN) and PN[j][0] <= e["t"]:
            for u, r in PN[j][1]: h = hist[u]; h[0] += 1; h[1] += r
            j += 1
        good = [u for u in e["buyers3"] if hist[u][0] >= 5 and hist[u][1] > 0]
        e["f"]["pbots3"] = len(set(good)); e["f"]["pbots3_share"] = len(set(good)) / max(len(set(e["buyers3"])), 1)
        del e["buyers3"]
    print(f"dumps found: {len(EV)} (BUILD {sum(not e['fwd'] for e in EV)}, TEST {sum(e['fwd'] for e in EV)})", flush=True)
    # ---- score: GBDT on the trade outcome at lag 1 (e_model's fit), trained on BUILD only
    H = os.path.dirname(os.path.abspath(__file__))
    esrc = open(os.path.join(H, "e_model.py")).read(); bstart = esrc.index("def binize("); bend = esrc.index("REPORT = {}")
    ns_ = {"np": np, "collections": collections}; exec(esrc[bstart:bend], ns_); fit, pred = ns_["fit"], ns_.get("pred")
    FK = sorted(EV[0]["f"]); Xm = np.array([[e["f"][k] if e["f"][k] is not None else np.nan for k in FK] for e in EV], float)
    fwd = np.array([e["fwd"] for e in EV]); nB = (~fwd).sum(); idx = np.arange(len(EV))
    TRN = ~fwd & (idx < int(nB * .8)); VAL = ~fwd & (idx >= int(nB * .8)); TEST = fwd
    Bm = ns_["binize"](Xm, TRN)
    r1 = np.array([e["ret"][1] for e in EV]); y = ((r1 * 0.5 - FIXES[0]) > 0).astype(float)
    trees, f = fit(Bm, y, TRN, VAL)
    thr = float(np.quantile(f[VAL], 1 - TOPQ))
    hrs = lambda msk: (max(e["t"] for e, s in zip(EV, msk) if s) - min(e["t"] for e, s in zip(EV, msk) if s)) / 3600
    rep = {}
    for nm, msk in (("VAL (build, last 20%)", VAL), ("TEST (forward, never used)", TEST)):
        sel = msk & (f >= thr); h = hrs(msk)
        print(f"\n{nm}: {msk.sum()} dumps over {h:.1f} h; top {TOPQ:.0%} by score -> {sel.sum()} trades ({sel.sum() / h:.1f}/h)")
        for lag in (1, 2, 3):
            for FIX in FIXES:
                v = []; skipped = 0
                for i in np.where(sel)[0]:
                    x = EV[i]["ret"].get(lag)
                    if x == "skip": skipped += 1
                    elif x is not None: v.append(x * 0.5 - FIX)
                v = np.array(v)
                if not len(v): continue
                lab = {1: "right behind the dump", 2: "1 trade gets in first", 3: "2 trades get in first"}[lag]
                print(f"   {lab:22} cost {FIX:.4f}: trades {len(v):4} (skipped {skipped}) win {(v > 0).mean():4.0%} mean {v.mean():+.4f} SOL median {np.median(v):+.4f} total {v.sum():+.2f} SOL = {v.sum() / h:+.2f} SOL/h")
                rep[f"{nm}|{lag}|{FIX}"] = dict(n=len(v), win=float((v > 0).mean()), mean=float(v.mean()), total=float(v.sum()), per_h=float(v.sum() / h))
        allv = np.array([EV[i]["ret"][1] * 0.5 - FIXES[0] for i in np.where(msk)[0]])
        print(f"   (all dumps, no score, right behind, cost {FIXES[0]}: win {(allv > 0).mean():.0%} mean {allv.mean():+.4f})")
    FIX = FIXES[0]
    for nm, msk in (("VAL", VAL), ("TEST", TEST)):
        sel = [i for i in np.where(msk & (f >= thr))[0] if (TP, SL, HOLD) in EV[i]["ex"]]
        why = collections.Counter(EV[i]["ex"][(TP, SL, HOLD)][1] for i in sel); hold = [EV[i]["ex"][(TP, SL, HOLD)][2] for i in sel]
        print(f"\n{nm}: spec sell (+8% / -5% / 1.3 s) on {len(sel)} trades: " + ", ".join(f"{k} {v / len(sel):.0%}" for k, v in why.most_common()) +
              f" | blocks held: median {np.median(hold):.0f} (about {np.median(hold) / SPS:.1f} s)")
    grid = []
    for g in EXG:
        out = {}
        for nm, msk in (("VAL", VAL), ("TEST", TEST)):
            v = np.array([EV[i]["ex"][g][0] * 0.5 - FIX for i in np.where(msk & (f >= thr))[0] if g in EV[i]["ex"]])
            out[nm] = (len(v), float((v > 0).mean()) if len(v) else 0, float(v.mean()) if len(v) else 0, float(v.sum()) if len(v) else 0)
        grid.append((g, out))
    grid.sort(key=lambda x: -x[1]["VAL"][2])
    hv, ht = hrs(VAL), hrs(TEST)
    print(f"\nSELL RULES (right behind the dump, cost {FIX}) ranked on VAL, then TEST:")
    for g, o in grid[:10] + [x for x in grid if x[0] == (TP, SL, HOLD)]:
        print(f"   +{g[0]:.0%} / -{g[1]:.0%} / {g[2] / SPS:.1f} s  VAL win {o['VAL'][1]:.0%} mean {o['VAL'][2]:+.4f} {o['VAL'][3] / hv:+.2f} SOL/h | TEST win {o['TEST'][1]:.0%} mean {o['TEST'][2]:+.4f} total {o['TEST'][3]:+.2f} SOL {o['TEST'][3] / ht:+.2f} SOL/h" + ("   <- your spec" if g == (TP, SL, HOLD) else ""))
    imp = collections.Counter()
    def walk(n):
        if "w" in n: return
        imp[FK[n["f"]]] += 1; walk(n["l"]); walk(n["r"])
    for t in trees: walk(t)
    print("\nwhat the score leans on:", ", ".join(f"{k} {v}" for k, v in imp.most_common(10)))
    json.dump(dict(report=rep, features=FK, threshold=thr, n_trees=len(trees)), open(os.path.join(OUT, "dump_bounce.json"), "w"), indent=1)
