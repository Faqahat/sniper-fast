#!/usr/bin/env python3
"""HAQQ_SIZE step 2 (read-only): describe haqq's sizing (tiers, by day / hour, first vs add, buys per token, size vs his running
realized P&L) and his realized P&L per lot by size tier (did bigger pay for him?). Out: OUT/describe.json + printed tables."""
import pickle, collections, json, time
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_size"
W0 = 1793038500                       # 10-26 23:15 PKT (held-out day start)
pkt = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(int(t) + 18000))
Z = pickle.load(open(f"{OUT}/buys.pkl", "rb")); B = Z["buys"]; LOTS = Z["lots"]; TR = Z["trips"]
rng = np.random.default_rng(3)


def tier(x):
    return round(x, 2)


def boot_mean(v, nb=2000):
    v = np.asarray(v, float)
    if len(v) < 2: return (np.nan, np.nan)
    m = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(nb)]
    return float(np.percentile(m, 5)), float(np.percentile(m, 95))


if __name__ == "__main__":
    R = {}
    sz = np.array([b["size"] for b in B]); bt = np.array([b["bt"] for b in B]); add = np.array([b["add"] for b in B])
    day = (bt - W0) // 86400          # -1 = 10-25 23:15..10-26 23:15, 0 = held-out day
    t = np.array([tier(x) for x in sz])
    print(f"buys {len(B):,} on {len(set(b['mint'] for b in B)):,} mints, {pkt(bt.min())} -> {pkt(bt.max())}")
    c = collections.Counter(t.tolist())
    print("tiers (gross SOL):", [(k, v, f"{100 * v / len(t):.1f}%") for k, v in sorted(c.items())])
    R["tiers"] = {str(k): v for k, v in sorted(c.items())}
    print("\nby 24h block (ends at 23:15 PKT): n, mean size, share of tiers")
    TI = sorted(c)
    R["by_day"] = {}
    for d in sorted(set(day.tolist())):
        m = day == d
        sh = {k: round(float((t[m] == k).mean()), 3) for k in TI}
        R["by_day"][int(d)] = dict(n=int(m.sum()), mean=float(sz[m].mean()), sh=sh, start=pkt(W0 + d * 86400))
        print(f"  {pkt(W0 + d * 86400)} n={m.sum():5d} mean={sz[m].mean():.3f} median={np.median(sz[m]):.2f} " + " ".join(f"{k}:{100 * v:.0f}%" for k, v in sh.items() if v >= 0.01))
    # first vs add
    print(f"\nfirst buys in a trip: {(~add).sum():,}, adds: {add.sum():,}")
    for lab, m in (("first", ~add), ("add", add)):
        cc = collections.Counter(t[m].tolist()); n = m.sum()
        print(f"  {lab}: mean {sz[m].mean():.3f} " + " ".join(f"{k}:{100 * v / n:.0f}%" for k, v in sorted(cc.items()) if v / n >= 0.01))
    # buys per mint and per trip
    per_mint = collections.Counter(b["mint"] for b in B); per_trip = collections.Counter(b["trip_ix"] for b in B)
    pm = np.array(list(per_mint.values())); ptp = np.array(list(per_trip.values()))
    print(f"buys per mint: mean {pm.mean():.2f}, share >1: {100 * (pm > 1).mean():.0f}%, dist {collections.Counter(np.minimum(pm, 6).tolist())}")
    print(f"buys per trip: mean {ptp.mean():.2f}, share >1: {100 * (ptp > 1).mean():.0f}%; trips per mint mean {len(TR) / len(per_mint):.2f}")
    R["per_mint"] = dict(mean=float(pm.mean()), gt1=float((pm > 1).mean())); R["per_trip"] = dict(mean=float(ptp.mean()), gt1=float((ptp > 1).mean()))
    # second-buy relation to first in multi-buy trips
    pairs = collections.Counter()
    tr_b = collections.defaultdict(list)
    for b in B: tr_b[b["trip_ix"]].append(b)
    for v in tr_b.values():
        if len(v) > 1: pairs[(tier(v[0]["size"]), tier(v[1]["size"]))] += 1
    print("first->second tier in multi-buy trips (top):", pairs.most_common(10))
    # same-slot multiple buys (copies of one decision?)
    same = sum(1 for v in tr_b.values() for i in range(1, len(v)) if v[i]["slot"] == v[i - 1]["slot"])
    gaps = [v[i]["slot"] - v[i - 1]["slot"] for v in tr_b.values() for i in range(1, len(v))]
    print(f"adds in the same slot as the previous buy: {same}; add gap slots median {np.median(gaps) if gaps else 0}, p90 {np.percentile(gaps, 90) if gaps else 0}")
    # lot P&L by tier (closed lots only)
    print("\nrealized P&L per lot by size tier (closed lots, gross of tx fees/tips; MEASURED on tape)")
    lp = []
    for i, L in enumerate(LOTS):
        if L["close_bt"] is None: continue
        lp.append((tier(L["cost"]), L["cost"], L["out"] - L["cost"], L["bt"], i))
    unclosed = [L for L in LOTS if L["close_bt"] is None]
    print(f"closed lots {len(lp):,}; unclosed {len(unclosed):,} (cost {sum(L['cost'] for L in unclosed):.1f} SOL, marked value "
          f"{sum(L.get('mark', 0) for L in unclosed) / 1e0:.1f})")
    lt = np.array([x[0] for x in lp]); lc = np.array([x[1] for x in lp]); lpn = np.array([x[2] for x in lp]); lbt = np.array([x[3] for x in lp])
    R["lot_pnl"] = {}
    for k in TI:
        m = lt == k
        if m.sum() < 20: continue
        r = lpn[m] / lc[m]; lo, hi = boot_mean(r)
        R["lot_pnl"][str(k)] = dict(n=int(m.sum()), sol=float(lpn[m].sum()), per_sol=float(lpn[m].sum() / lc[m].sum()), mean_ret=float(r.mean()), lo=lo, hi=hi,
                                    win=float((lpn[m] > 0).mean()))
        print(f"  {k:5.2f}: lots {m.sum():5d} P&L {lpn[m].sum():+8.2f} SOL, per SOL {lpn[m].sum() / lc[m].sum():+.4f}, mean ret {r.mean():+.4f} [{lo:+.4f},{hi:+.4f}] win {100 * (lpn[m] > 0).mean():.0f}%")
    print(f"  total closed-lot P&L {lpn.sum():+.2f} SOL on {lc.sum():.0f} SOL bought; per day:")
    lday = (lbt - W0) // 86400
    for d in sorted(set(lday.tolist())):
        m = lday == d; print(f"    {pkt(W0 + d * 86400)}: {lpn[m].sum():+.2f} SOL ({m.sum()} lots, {lc[m].sum():.0f} SOL, {lpn[m].sum() / lc[m].sum():+.4f}/SOL)")
    # correlation of size with return (excluding 0.01 probes)
    m = lc > 0.05
    rr = lpn[m] / lc[m]
    print(f"  Spearman(size, return) excl. 0.01 probes: {np.corrcoef(np.argsort(np.argsort(lc[m])), np.argsort(np.argsort(rr)))[0, 1]:+.3f}")
    # size vs running realized P&L (proxy for balance; absolute balance not on tape)
    ev = sorted([(L["close_bt"], L["out"] - L["cost"]) for L in LOTS if L["close_bt"] is not None])
    cb = np.array([e[0] for e in ev]); cp = np.cumsum([e[1] for e in ev])
    run = np.array([cp[np.searchsorted(cb, x) - 1] if np.searchsorted(cb, x) > 0 else 0.0 for x in bt])
    mm = sz > 0.05
    hrs = (bt - bt.min()) // 3600
    hs = collections.defaultdict(list); hr_ = {}
    for x, hh, r_ in zip(sz[mm], hrs[mm], run[mm]): hs[hh].append(x); hr_[hh] = r_
    hx = np.array(sorted(hs)); hm_ = np.array([np.mean(hs[x]) for x in hx]); hrun = np.array([hr_[x] for x in hx])
    print(f"\nhourly mean size (excl. probes) vs running realized P&L at that hour: corr {np.corrcoef(hm_, hrun)[0, 1]:+.3f} over {len(hx)} hours; "
          f"size vs elapsed hours corr {np.corrcoef(hm_, hx)[0, 1]:+.3f}")
    R["bal_corr"] = dict(run=float(np.corrcoef(hm_, hrun)[0, 1]), time=float(np.corrcoef(hm_, hx)[0, 1]))
    # hour of day
    hod = np.array([b["hour"] for b in B])
    print("mean size by PKT hour (excl. probes):", " ".join(f"{hh}:{sz[mm & (hod == hh)].mean():.2f}" for hh in range(24) if (mm & (hod == hh)).sum() > 30))
    json.dump(R, open(f"{OUT}/describe.json", "w"), indent=1)
