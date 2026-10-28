#!/usr/bin/env python3
"""BOTS step 2b (read-only): the BROAD trigger envelope (main-session hint: buys follow dev / big-holder CHUNK sells that are often < 5 %).
Every outside sell (not haqq, not our wallets) on a non-mayhem token <= 300 s old, from the whole tape (dv8/tab), with decision-time
features (all from rows up to and including the sell, chain order):
  drop (this sell's single-trade price drop), dd10 (price after the sell vs the max price over the previous 10 slots), sell SOL,
  seller type (dev = creator / cs = bought in the creation slot / early = first buy <= 10 slots after create / other), seller's balance
  before the sell (% of supply) and share of it sold, chunk count (this seller's sells on the token in the last 10 / 30 slots incl. this one),
  dev sells so far, curve SOL after, age, outside buys/sells in the last 3 slots, trades so far.
Labels: bot 247 / 248 (and 244, 226) BOUGHT within 0..2 slots after the sell (next code-c buy on the mint, after the sell row) - MEASURED.
Out: bots/b2b.npz (envelope rows: features, labels, keys), b2b.txt (trigger attribution of every 247/248 buy + buy rates)"""
import sys, json, pickle, time, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"
lines = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); lines.append(s)


def main():
    t0 = time.time()
    ids, idm = L.ids_map(); our = [idm[w] for w in L.WAL.values() if w in idm]; H = idm[L.HAQQ]
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    user = np.asarray(T["user"]); keep = ~np.isin(user, our)
    mt = np.asarray(T["mint"])[keep]; o = np.argsort(mt, kind="stable"); mt = mt[o].astype(np.int64)
    us = user[keep][o].astype(np.int64); del user
    sl = np.asarray(T["slot"])[keep][o].astype(np.int64); ix = np.asarray(T["idx"])[keep][o].astype(np.int64)
    bu = np.asarray(T["buy"])[keep][o].astype(bool); so = np.asarray(T["sol"])[keep][o] / 1e9; tk = np.asarray(T["tok"])[keep][o].astype(np.float64)
    vs = np.asarray(T["vsol"])[keep][o] / 1e9; vt = np.asarray(T["vtok"])[keep][o].astype(np.float64); bt = np.asarray(T["bt"])[keep][o].astype(np.int64)
    del o, keep
    N = len(mt); pos = np.arange(N)
    print(f"tape {N:,} ({time.time() - t0:.0f}s)", flush=True)
    CR = json.load(open(f"{L.TAB}/creates.json"))
    um, st = np.unique(mt, return_index=True); en = np.append(st[1:], N)
    cs_m = np.full(int(mt.max()) + 1, -1, np.int64); cr_m = np.full(int(mt.max()) + 1, -2, np.int64); may_m = np.zeros(int(mt.max()) + 1, bool)
    for m in um.tolist():
        c = CR.get(ids[m])
        if c and c.get("slot") is not None:
            cs_m[m] = int(c["slot"]); cr_m[m] = idm.get(c.get("creator"), -2); may_m[m] = bool(c.get("mayhem"))
    del CR
    cs = cs_m[mt]; age = np.where(cs >= 0, (sl - cs) * 0.212, 1e9)
    px = vs / np.maximum(vt, 1); first = np.zeros(N, bool); first[st] = True
    pxp = np.empty(N); pxp[1:] = px[:-1]; pxp[first] = px[first]
    drop = np.where(~bu, 1 - px / pxp, 0.0)
    # per (mint, user) balance and first-buy slot
    g = np.lexsort((pos, us, mt))
    key_g = mt[g] * 2 ** 32 + us[g]; gs = np.ones(N, bool); gs[1:] = key_g[1:] != key_g[:-1]
    gid_sorted = np.cumsum(gs) - 1
    signed = np.where(bu, tk, -tk)[g]
    cs_ = np.cumsum(signed); start_val = np.repeat(cs_[gs] - signed[gs], np.diff(np.append(np.flatnonzero(gs), N)))
    bal_after = np.empty(N); bal_after[g] = cs_ - start_val
    bal_before = bal_after - np.where(bu, tk, -tk)
    fb = np.where(bu[g], sl[g], 2 ** 62); seg = np.flatnonzero(gs)
    fbs = np.minimum.reduceat(fb, seg); first_buy = np.empty(N, np.int64); first_buy[g] = np.repeat(fbs, np.diff(np.append(seg, N)))
    # chunk counts: sells by the same (mint, user) in the last 10 / 30 slots, incl. this one
    sell_g = (~bu[g]).astype(np.int64); csell = np.cumsum(sell_g)
    k2 = gid_sorted * 2 ** 34 + sl[g]
    ch = {}
    for W in (10, 30):
        lo = np.searchsorted(k2, gid_sorted * 2 ** 34 + sl[g] - W, side="left")
        cnt = csell - np.where(lo > 0, csell[np.maximum(lo - 1, 0)], 0)
        c = np.empty(N, np.int64); c[g] = cnt; ch[W] = c
    del g, key_g, gs, gid_sorted, signed, cs_, start_val, fb, sell_g, csell, k2
    print(f"balances / chunks ({time.time() - t0:.0f}s)", flush=True)
    # dev sells so far on the mint (cumulative), seller type
    isdev = us == cr_m[mt]
    devsell = (~bu & isdev).astype(np.int64); cdev = np.cumsum(devsell)
    base = np.repeat(np.append(0, cdev[en[:-1] - 1]), en - st); cdev = cdev - base
    stype = np.where(isdev, 0, np.where(first_buy == cs, 1, np.where(first_buy <= cs + 10, 2, 3)))     # 0 dev 1 cs 2 early 3 other
    # haqq code buys
    codes = pickle.load(open(f"{OUT}/hcodes.pkl", "rb"))
    hq = np.flatnonzero((us == H) & bu)
    hcode = np.array([codes.get((int(sl[i]), int(ix[i])), -1) for i in hq])
    # envelope: outside sells, non-mayhem, age <= 300 s
    env = ~bu & (us != H) & (age <= 300) & ~may_m[mt] & (cs >= 0)
    E = np.flatnonzero(env)
    print(f"envelope {len(E):,} sells ({time.time() - t0:.0f}s)", flush=True)
    # dd10: price after the sell vs max over the previous 10 slots (rows before, plus pxp)
    dd10 = np.zeros(len(E)); lo10 = np.searchsorted(mt * 2 ** 34 + sl, mt[E] * 2 ** 34 + sl[E] - 10, side="left")
    for n, (i, a) in enumerate(zip(E.tolist(), lo10.tolist())):
        mx = px[a:i].max() if i > a else pxp[i]
        mx = max(mx, pxp[i]); dd10[n] = 1 - px[i] / mx
    print(f"dd10 ({time.time() - t0:.0f}s)", flush=True)
    # flows
    keyms = mt * 2 ** 34 + sl
    lo3 = np.searchsorted(keyms, mt[E] * 2 ** 34 + sl[E] - 3, side="left")
    cbo = np.cumsum(np.where(bu & (us != H), so, 0.0)); cso = np.cumsum(np.where(~bu & (us != H), so, 0.0))
    b3 = cbo[E] - np.where(lo3 > 0, cbo[lo3 - 1], 0); s3 = cso[E] - np.where(lo3 > 0, cso[lo3 - 1], 0) - so[E]
    ntr = E - st[np.searchsorted(st, E, side="right") - 1]
    # labels: next code-c buy after the sell row on the same mint within 2 slots
    LAB = {}
    for c in (247, 248, 244, 226):
        cb = hq[hcode == c]
        nb = np.searchsorted(cb, E, side="right")
        okn = nb < len(cb); j = cb[np.minimum(nb, len(cb) - 1)]
        LAB[c] = okn & (mt[j] == mt[E]) & (sl[j] <= sl[E] + 2)
    day = (bt[E] - L.DAY0) // 86400
    hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
    hs = (bt[E] + 18000) // 3600 * 3600 - 18000; usable = np.isin(hs, list(good))
    hold_pct = np.maximum(bal_before[E], 0) / 1e13          # % of 1e15 supply
    frac = np.where(bal_before[E] > 0, tk[E] / np.maximum(bal_before[E], 1), 1.0)
    np.savez_compressed(f"{OUT}/b2b.npz", row=E, mint=mt[E].astype(np.uint32), slot=sl[E], idx=ix[E].astype(np.uint32), user=us[E].astype(np.uint32), bt=bt[E],
                        drop=drop[E].astype(np.float32), dd10=dd10.astype(np.float32), sol=so[E].astype(np.float32), stype=stype[E].astype(np.int8),
                        hold=hold_pct.astype(np.float32), frac=np.clip(frac, 0, 1).astype(np.float32), ch10=ch[10][E].astype(np.int16), ch30=ch[30][E].astype(np.int16),
                        cdev=cdev[E].astype(np.int16), vpost=vs[E].astype(np.float32), age=age[E].astype(np.float32), b3=b3.astype(np.float32), s3=s3.astype(np.float32),
                        ntr=ntr.astype(np.int32), day=day.astype(np.int8), usable=usable, Y247=LAB[247], Y248=LAB[248], Y244=LAB[244], Y226=LAB[226])
    # ---- attribution: for every 247 / 248 buy (usable, non-mayhem, age <= 300 s), the outside sells in the 0..2 slots before it
    P("# Broad trigger envelope (MEASURED): every outside sell on non-mayhem tokens <= 300 s old; 10-22 03:07 -> 10-28 01:12 PKT")
    P(f"envelope sells {len(E):,} (usable hours {usable.sum():,})")
    P("\n## 1. What preceded each bot buy (latest outside sell within 0-2 slots before the buy; 'strongest' = the most specific class among those sells)")
    rows = pickle.load(open(f"{OUT}/b1.pkl", "rb"))
    eidx = {(int(mt[i]), int(sl[i]), int(ix[i])): n for n, i in enumerate(E)}
    keyE = mt[E] * 2 ** 34 + sl[E]
    def classify(n):
        d = drop[E[n]]; s = stype[E[n]]; h = hold_pct[n]
        if d >= 0.05: return "A single sell >= 5 %"
        if s == 0: return "B dev sell < 5 %"
        if s in (1, 2) and h >= 1: return "C bundle/early holder >= 1 % sell < 5 %"
        if h >= 2: return "D other holder >= 2 % sell < 5 %"
        if dd10[n] >= 0.10: return "E small sell, 10-slot drawdown >= 10 %"
        if d >= 0.02: return "F small sell 2-5 %"
        return "G tiny sell"
    for c in (247, 248):
        v = [r for r in rows if r["code"] == c and r["usable"] and not r["gap"] and r["mi"] is not None and r["age"] is not None and r["age"] * 0.212 <= 300]
        cls = collections.Counter(); net = collections.defaultdict(float); ex = collections.defaultdict(list)
        for r in v:
            k = r["mi"] * 2 ** 34
            a = np.searchsorted(keyE, k + r["slot"] - 2, side="left"); b = np.searchsorted(keyE, k + r["slot"] + 1, side="left")
            # keep sells strictly before the buy in chain order
            cand = [n for n in range(a, b) if (sl[E[n]], ix[E[n]]) < (r["slot"], r["idx"])]
            if not cand: lab = "H no outside sell within 2 slots"
            else: lab = min(classify(n) for n in cand)
            cls[lab] += 1; net[lab] += r["net"]
        P(f"\n### bot {c}: {len(v):,} lots (usable, token <= 300 s)")
        P("| trigger class (most specific sell in 0-2 slots before the buy) | lots | share | net SOL | mSOL/lot |"); P("|---|---|---|---|---|")
        for k in sorted(cls): P(f"| {k} | {cls[k]:,} | {100 * cls[k] / len(v):.0f}% | {net[k]:+.2f} | {1000 * net[k] / cls[k]:+.2f} |")
    # ---- buy rates per class on the envelope (usable hours)
    P("\n## 2. P(bot buys within 2 slots | sell class) on the envelope (usable hours)")
    cl = np.full(len(E), "G", "U1")
    dE = drop[E]; sE = stype[E]
    cl[(dE >= 0.02)] = "F"; cl[(dd10 >= 0.10) & (dE < 0.05)] = "E"; cl[(hold_pct >= 2) & (dE < 0.05)] = "D"; cl[np.isin(sE, (1, 2)) & (hold_pct >= 1) & (dE < 0.05)] = "C"
    cl[(sE == 0) & (dE < 0.05)] = "B"; cl[dE >= 0.05] = "A"
    P("| class | sells | 247 buy % | 248 buy % | 244 buy % | median curve SOL after | median age s |"); P("|---|---|---|---|---|---|---|")
    for k in "ABCDEFG":
        m = usable & (cl == k)
        P(f"| {k} | {m.sum():,} | {100 * LAB[247][m].mean():.2f} | {100 * LAB[248][m].mean():.2f} | {100 * LAB[244][m].mean():.2f} | {np.median(vs[E][m]):.1f} | {np.median(age[E][m]):.0f} |")
    P("\n## 3. Dev / holder chunk selling: buy rate by this seller's sells in the last 10 slots (incl. this one), dev + cs/early sellers, sells < 5 %")
    P("| seller | chunks in 10 slots | sells | 247 buy % | 248 buy % |"); P("|---|---|---|---|---|")
    for nm, sm in (("dev", sE == 0), ("cs/early >=1 %", np.isin(sE, (1, 2)) & (hold_pct >= 1))):
        for a, b in ((1, 2), (2, 3), (3, 5), (5, 1000)):
            m = usable & sm & (dE < 0.05) & (ch[10][E] >= a) & (ch[10][E] < b)
            if m.sum() < 100: continue
            P(f"| {nm} | {a}-{b - 1} | {m.sum():,} | {100 * LAB[247][m].mean():.2f} | {100 * LAB[248][m].mean():.2f} |")
    P("\n## 4. Buy rate by 10-slot drawdown after the sell (all envelope sells, usable)")
    P("| dd10 | sells | 247 buy % | 248 buy % |"); P("|---|---|---|---|")
    for a, b in ((0, .02), (.02, .04), (.04, .08), (.08, .12), (.12, .2), (.2, .32), (.32, 1.01)):
        m = usable & (dd10 >= a) & (dd10 < b)
        P(f"| {a:.2f}-{b:.2f} | {m.sum():,} | {100 * LAB[247][m].mean():.2f} | {100 * LAB[248][m].mean():.2f} |")
    open(f"{OUT}/b2b.txt", "w").write("\n".join(lines) + "\n")
    print(f"done ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
