#!/usr/bin/env python3
"""APEX2 step 4: walk-forward CREP (S2) re-score by create-slot POSITION, sizes, followers, per day, costs.

CREP at decision time b (create block time): creator's launches with bt <= b - 300 s ("judged", outcome window of the label
is <= ~90 s, so fully known), count >= NMIN, sum(label) > 0, mean(label) > MEANMIN.
label = replay net at 0.2 SOL, phi 0, exit h6, at the label position, minus 2.9 mSOL - pen(0.2) (old APEX definition);
a guard-reverted launch counts 0 (old code). History = every simulated launch since the first tape (10-26 14:15 UTC).
Costs per landed trip ("meas"): measured buy cost (median tx fee + tips of non-bundle create-slot buyers on these creators)
+ measured sell cost (median of sells 5..20 slots after create) ; guard revert: buy tx fee only.
"old" costs: 2.9 mSOL + pen(S) per landed trip, 0.3 mSOL per revert (frozen APEX accounting).
usage: a2_eval.py [label_pos=same|P18|A] [exit=h2]"""
import sys, glob, pickle, collections, json, numpy as np
import os
RES = os.environ.get("APEX2_RES", "/home/it/sniper-data/apex2/res")
POS = ("P18", "A", "R1", "R2", "M", "E", "N"); SIZES = (0.05, 0.2, 0.4); PHIS = (0.0, 0.2, 0.4); EXITS = ("h2", "h2L", "h6")
HOLDOUT_END = 1793262240          # old freeze cut: 10-29 13:24 PKT
def pen(S): return max(13.62 * S + 10.38 * S * S, -4.4 + 28.1 * S) / 1e3
PKT = 5 * 3600

def load(strings=False):
    """strings=True: translate run-local wallet ids in info (cst, cs_pnl, cs_users) to base58 strings"""
    import json
    L = []; seen = set()
    for f in sorted(glob.glob(f"{RES}/run_*.pkl")):
        run = f.split("/")[-1][:-4]
        ids = json.load(open(f"/home/it/sniper-data/apex2/tab/{run}/ids.json")) if strings else None
        for r in pickle.load(open(f, "rb")):
            if r[0] in seen: continue
            seen.add(r[0])
            if strings:
                info = r[5]
                info["cst"] = [(ids[x[0]], ids[x[1]]) + tuple(x[2:]) for x in info["cst"]]
                if "cs_pnl" in info: info["cs_pnl"] = {ids[u]: v for u, v in info["cs_pnl"].items()}
                info["cs_users"] = [ids[u] for u in info["cs_users"]]
            info = r[5]; info["run"] = run
            L.append(r)
        ids = None
    L.sort(key=lambda r: (r[3], r[4]))
    return L

def costs(L):
    b = []; s = []
    for r in L:
        info = r[5]
        b += [x[6] + x[7] for x in info["cst"] if not x[8] and x[4]]
        s += info.get("sellc", [])
    return np.median(b) / 1e9, np.median(s) / 1e9, np.percentile(b, [25, 75]) / 1e9, np.median([x for x in b]) / 1e9

def crep(L, lpos, nmin=3, meanmin=0.002):
    """returns bool array: launch selected by CREP at decision time (walk-forward)"""
    pi = POS.index(lpos) if lpos != "same" else None
    hist = collections.defaultdict(list); pend = collections.deque(); sel = {}
    for p in (POS if lpos == "same" else (lpos,)):
        sel[p] = np.zeros(len(L), bool)
    ps = POS if lpos == "same" else (lpos,)
    H = {p: collections.defaultdict(lambda: [0, 0.0]) for p in ps}       # creator -> [n judged, sum label]
    order = sorted(range(len(L)), key=lambda i: L[i][2])
    for i in order:
        bt = L[i][2]
        while pend and pend[0][0] <= bt - 300:
            _, j = pend.popleft(); cre = L[j][1]; R = L[j][6]
            for p in ps:
                v = R[POS.index(p), 1, 0, 2]
                lab = (float(v) - 0.0029 - pen(0.2)) if np.isfinite(v) else 0.0
                h = H[p][cre]; h[0] += 1; h[1] += lab
        cre = L[i][1]
        for p in ps:
            h = H[p].get(cre)
            if h and h[0] >= nmin and h[1] > 0 and h[1] / h[0] > meanmin: sel[p][i] = True
        pend.append((bt, i))
    return sel

def score(L, sel_mask, p, zi, exit, cmode, cb, cs_, rng=None):
    pi = POS.index(p); xi = EXITS.index(exit); S = SIZES[zi]
    out = {}
    for hi, phi in enumerate(PHIS):
        v = np.array([L[i][6][pi, zi, hi, xi] for i in np.flatnonzero(sel_mask)], np.float64)
        ok = np.isfinite(v)
        if cmode == "meas": net = np.where(ok, v - cb - cs_, -cb * 0.3)
        elif cmode.startswith("b"):
            c_ = float(cmode[1:]) / 1e3; net = np.where(ok, v - c_ - cs_, -min(c_ * 0.3, 0.001))
        else: net = np.where(ok, v - 0.0029 - pen(S), -0.0003)
        out[phi] = net
    return out

WIN = [("10-26/27", 1793024101, 1793110202), ("10-27/28", 1793110202, 1793196306), ("10-28/29a", 1793196306, 1793262240),
       ("10-29b", 1793262240, 1793282404), ("10-29/30", 1793282404, 1793368501), ("10-30/31", 1793368501, 1793454601),
       ("10-31/11-01", 1793454601, 1793542202), ("11-02/03", 1793623811, 1793709905), ("11-03", 1793709905, 1793900000)]
UNSEEN = 1793262240

def summarize(net_by_phi, hours):
    per = 24 / hours; v0 = np.sort(net_by_phi[0.0])[::-1]; n = len(v0)
    if n == 0: return dict(n=0, perday=0, sol=0, f20=0, f40=0, wo5=0, win=0, mean=0)
    return dict(n=n, perday=n * per, sol=v0.sum() * per, f20=net_by_phi[0.2].sum() * per, f40=net_by_phi[0.4].sum() * per,
                wo5=v0[int(np.ceil(n * 0.05)):].sum() * per, win=float((v0 > 0).mean()), mean=float(v0.mean() * 1e3))

def main():
    lpos = sys.argv[1] if len(sys.argv) > 1 else "same"; exit = sys.argv[2] if len(sys.argv) > 2 else "h2"
    cmode = sys.argv[3] if len(sys.argv) > 3 else "meas"
    L = load(); bt = np.array([r[2] for r in L])
    cb, cs_, cbq, _ = costs(L)
    print(f"launches simulated {len(L)}; measured buy cost {cb*1e3:.3f} mSOL (IQR {cbq[0]*1e3:.3f}-{cbq[1]*1e3:.3f}), sell {cs_*1e3:.3f}; costs={cmode} label={lpos} exit={exit}")
    sel = crep(L, lpos); rng = np.random.default_rng(7)
    hours = {}
    for nm, a, b in WIN:
        m = (bt >= a) & (bt < b)
        if m.sum(): hours[nm] = (min(b, bt.max()) - max(a, bt.min())) / 3600
    out = {}
    for p in POS:
        sp = sel[p] if lpos == "same" else sel[lpos]
        for zi, S in enumerate(SIZES):
            rows = {}
            for nm, a, b in WIN:
                m = (bt >= a) & (bt < b)
                if not m.sum(): continue
                rows[nm] = summarize(score(L, sp & m, p, zi, exit, cmode, cb, cs_), hours[nm])
                # random same count among all simulated (serial-creator) launches of the window
                pool = np.flatnonzero(m); k = int((sp & m).sum())
                if k:
                    rs = []
                    for _ in range(20):
                        mm = np.zeros(len(L), bool); mm[rng.choice(pool, k, replace=False)] = True
                        rs.append(score(L, mm, p, zi, exit, cmode, cb, cs_)[0.0].sum() * 24 / hours[nm])
                    rows[nm]["rand"] = float(np.mean(rs))
            mu = sp & (bt >= UNSEEN); hu = sum(hours[nm] for nm, a, b in WIN if a >= UNSEEN and nm in hours)
            rows["UNSEEN"] = summarize(score(L, mu, p, zi, exit, cmode, cb, cs_), hu)
            out[(p, S)] = rows
    pickle.dump(dict(out=out, cb=cb, cs=cs_, hours=hours), open(f"{RES}/eval_{lpos}_{exit}_{cmode}.pkl", "wb"))
    for (p, S), rows in out.items():
        print(f"== pos {p} size {S}")
        for nm, r in rows.items():
            if r["n"] == 0: continue
            print(f"  {nm:12s} n/d={r['perday']:6.0f} SOL/d={r['sol']:+7.2f} f20={r['f20']:+7.2f} f40={r['f40']:+7.2f} wo5={r['wo5']:+7.2f} win={r['win']:.2f} mean={r['mean']:+.2f}mSOL rand={r.get('rand', float('nan')):+.2f}")

if __name__ == "__main__":
    main()
