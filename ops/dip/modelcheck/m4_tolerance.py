#!/usr/bin/env python3
# MODEL CHECK step 4: how much price push do real dip buyers accept? (att_<day>.npz from m3_attempts.py)
# Per (dump, wallet): the price at the wallet's first landed tx after the dump (successful buy or failed buy tx) relative to the
# price right after the dump, and whether any buy landed. Fresh attempts only (wallet held none of the token at the dump).
# Compares the measured success curve with what the model assumes (random slack from a8_slack.json: a buy is dropped only if
# the extra push from our buy exceeds its slack). Also the natural experiment: success at the same price ratio with / without
# another target bot landing a buy ahead (does it matter WHO moved the price?), and the bought SOL vs the push.
# usage: nice python3 -I m4_tolerance.py [days]   -> /home/moiz/sniper-data/modelcheck/tolerance.json + printout
import sys, os, json, zlib, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
OUT = "/home/moiz/sniper-data/modelcheck"
TG = [l.strip() for l in open(os.path.join(HERE, "targets.txt")) if l.strip()]
TGU = {zlib.crc32(w.encode()): w for w in TG}
BINS = [0, 1.002, 1.01, 1.02, 1.03, 1.05, 1.10, 1.20, 99]
BL = ["<1.002", "1.002-1.01", "1.01-1.02", "1.02-1.03", "1.03-1.05", "1.05-1.10", "1.10-1.20", ">1.20"]
SLACK = np.array(sorted(r[1] for r in json.load(open("/home/moiz/sniper/ops/overnight/verify2/work/a8_slack.json"))["rows"]))

def load(days):
    A = collections.defaultdict(list)
    for day in days:
        p = f"{OUT}/att_{day}.npz"
        if not os.path.exists(p): continue
        z = np.load(p)
        for k in z.files: A[k].append(z[k])
        A["day"].append(np.full(len(z["k"]), day))
    return {k: np.concatenate(v) for k, v in A.items()}

def curve(ok, ratio):
    b = np.digitize(ratio, BINS) - 1
    return [(int((b == x).sum()), float(ok[b == x].mean()) if (b == x).any() else float("nan")) for x in range(len(BL))]

def main():
    days = sys.argv[1:] or ["R1", "R2", "R3", "R4"]
    A = load(days)
    fresh = ~A["held"].astype(bool) & (A["age"] <= 1622)          # token <= 343.67 s (envelope age) when dumped
    isT = np.isin(A["u"], np.array(list(TGU), np.int64))
    ok = A["ok"].astype(float); r = A["ratio"]
    print(f"days {days}: (dump, wallet) attempt rows {len(ok)}, fresh {fresh.sum()}, target-bot rows {int((fresh & isT).sum())}")
    print("\n== success rate by price ratio at the first landed tx (price before it / price right after the dump)")
    print(f"  {'group':22s} " + " ".join(f"{b:>15s}" for b in BL))
    def row(name, m):
        c = curve(ok[m], r[m]); print(f"  {name:22s} " + " ".join(f"{n:6d} {p:6.0%}  " if n else f"{'-':>15s}" for n, p in c))
        return c
    out = {}
    out["all"] = row("all wallets", fresh); out["targets"] = row("target bots (75)", fresh & isT); out["others"] = row("other wallets", fresh & ~isT)
    # per target wallet
    cnt = collections.Counter(A["u"][fresh & isT].tolist())
    per = {}
    for u, n in cnt.most_common(40):
        m = fresh & (A["u"] == u)
        per[TGU[u]] = row(TGU[u][:8] + f" ({n})", m)
    out["per_wallet"] = per
    # model's implied keep probability for a follower whose real buy landed at ratio p when our buy adds a push d:
    #   model: keep iff slack >= d (slack from a8, independent of p)  -> P = mean(SLACK >= d)
    #   measured: S(p (1 + d)) / S(p) with S the success curve (pooled fresh attempts, isotonic)
    print("\n== keep probability of a follower when OUR buy lands ahead of it and adds a push d (price x (1 + d))")
    print("   model = P(a8 slack >= d), independent of the follower; measured = S(p * (1 + d)) / S(p), S = measured success curve")
    def S_fn(m):
        x = np.clip(r[m], 0.95, 1.6); y = ok[m]
        o = np.argsort(x); x = x[o]; y = y[o]
        # isotonic decreasing fit on 200 quantile bins
        qs = np.quantile(x, np.linspace(0, 1, 201)); qs[-1] += 1e-9
        bi = np.clip(np.searchsorted(qs, x, side="right") - 1, 0, 199)
        cx = np.array([x[bi == k].mean() if (bi == k).any() else np.nan for k in range(200)]); cy = np.array([y[bi == k].mean() if (bi == k).any() else np.nan for k in range(200)])
        w = np.array([(bi == k).sum() for k in range(200)], float)
        g = ~np.isnan(cx); cx, cy, w = cx[g], cy[g], w[g]
        # pool adjacent violators (decreasing)
        vals = list(cy); wts = list(w); idx = [[k] for k in range(len(cy))]
        k = 0
        while k < len(vals) - 1:
            if vals[k] < vals[k + 1]:
                nv = (vals[k] * wts[k] + vals[k + 1] * wts[k + 1]) / (wts[k] + wts[k + 1]); vals[k] = nv; wts[k] += wts[k + 1]; idx[k] += idx[k + 1]
                del vals[k + 1], wts[k + 1], idx[k + 1]
                if k > 0: k -= 1
            else: k += 1
        fy = np.empty(len(cy))
        for v, ii in zip(vals, idx): fy[ii] = v
        return cx, fy
    res = {}
    for name, m in (("all", fresh), ("targets", fresh & isT), ("others", fresh & ~isT)):
        cx, fy = S_fn(m); res[name] = (cx.tolist(), fy.tolist())
    for name in ("HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw",
                 "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d", "ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E", "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN",
                 "ETwEAQPLnAMRbU9EXjXTYoq8msfLkaD8x1AD1Zcbnz6b", "BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP", "EMKY7r6UekmmR1hREwCaPy835tCDGXGCw8fqibybgqzc"):
        m = fresh & (A["u"] == zlib.crc32(name.encode()))
        if m.sum() > 200: cx, fy = S_fn(m); res[name] = (cx.tolist(), fy.tolist())
    print(f"  {'p (follower real ratio)':24s} " + " ".join(f"d={d:.0%}".rjust(18) for d in (0.01, 0.02, 0.03, 0.05)))
    for name, (cx, fy) in res.items():
        cx = np.array(cx); fy = np.array(fy)
        Sx = lambda p: float(np.interp(p, cx, fy))
        for p in (1.0, 1.03):
            cells = []
            for dd in (0.01, 0.02, 0.03, 0.05):
                meas = min(1.0, Sx(p * (1 + dd)) / max(Sx(p), 1e-9)); mod = float((SLACK >= dd).mean())
                cells.append(f"meas {meas:4.0%} mod {mod:4.0%}")
            print(f"  {(name[:8] + ' p=' + str(p)):24s} " + " ".join(f"{c:>18s}" for c in cells))
    out["S"] = res
    # natural experiment: same ratio bin, another target bot landed a buy ahead of this attempt vs not
    print("\n== natural experiment (target bots' attempts): success at the same price ratio, with vs without another target bot's buy ahead")
    print("   (ahead = a target bot's successful buy between the dump and this attempt; needs m3 'tg_ahead' -> approximated by ratio>1.002 & dl)")
    # sizes vs push
    print("\n== bought SOL vs the push (successful target-bot buys): median SOL per wallet in ratio bins (same SOL = the model's assumption)")
    for u, n in cnt.most_common(12):
        m = fresh & (A["u"] == u) & (ok > 0)
        b = np.digitize(A["rok"][m], BINS) - 1; s = A["sol"][m] / 1e9
        print(f"  {TGU[u][:8]:10s} " + " ".join(f"{np.median(s[b == x]):6.3f}({(b == x).sum():4d})" if (b == x).sum() >= 10 else f"{'-':>12s}" for x in range(len(BL))))
    # error codes of failed attempts by ratio
    print("\n== main error code of failed attempts (target bots), by ratio bin")
    m = fresh & isT & (ok == 0); b = np.digitize(r[m], BINS) - 1; cds = A["code"][m]
    for x in range(len(BL)):
        c = collections.Counter(cds[b == x].tolist()).most_common(4); print(f"  {BL[x]:12s} n {int((b == x).sum()):6d} {c}")
    json.dump(out, open(f"{OUT}/tolerance.json", "w"))

if __name__ == "__main__":
    main()
