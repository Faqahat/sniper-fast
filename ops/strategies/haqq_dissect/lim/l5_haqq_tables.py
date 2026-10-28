#!/usr/bin/env python3
"""LIM step 5 (read-only): haqq's buys (data/lim/hctx.pkl) - how his price limit binds and what his behind-the-crowd buys earn.
DIP = first buy (no open lot of his on the mint), curve before > 30.52 SOL, a >=5% single-sell drop within 2 slots (hs_lib.etype).
pr = price before his tx / post-dump price (what any limit vs the post-dump price acts on). All MEASURED on tape.
Lot P&L = FIFO lot (net of pump fees, before tx costs; his tx cost ~0.78 mSOL/lot, haqq_strat s2).
Out: data/lim/l5.txt"""
import pickle, sys, collections, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def boot_mean(v, n=1500, seed=2):
    v = np.asarray(v, float); g = np.random.default_rng(seed)
    if len(v) < 3: return (np.nan, np.nan)
    s = [v[g.integers(0, len(v), len(v))].mean() for _ in range(n)]
    return np.percentile(s, 5), np.percentile(s, 95)


def main():
    H = pickle.load(open(f"{OUT}/hctx.pkl", "rb"))
    H.sort(key=lambda r: (r["mint"], r["s"], r["i"]))
    # open-lot flag (add) per mint
    last_mint = None; opens = []
    for r in H:
        if r["mint"] != last_mint: opens = []; last_mint = r["mint"]
        r["add"] = any((c is None) or (c >= r["s"]) for c in opens)
        if r["ok"] and "lot_cost" in r: opens.append(r.get("close") if not r.get("open_") else None)
    for r in H:
        r["dip"] = (not r["add"]) and r["v_pre"] > 30.52 and r.get("dj_drop", 0) >= 0.05 and r.get("d_slots", 99) <= 2
    P("# haqq buys 10-22 03:08 -> 10-28 00:41 PKT on the tape (MEASURED). Gap 10-25 06:45-19:20 PKT has no raw haqq txs.")
    c = collections.Counter(json.dumps(r["err"])[:70] for r in H if not r["ok"])
    P(f"buy txs {len(H)}: filled {sum(r['ok'] for r in H)}, failed {sum(not r['ok'] for r in H)}; error codes: " + "; ".join(f"{k} x{v}" for k, v in c.most_common(6)))
    D = [r for r in H if r["dip"]]
    P(f"DIP buys (first buy, >=5% drop within 2 slots): {len(D)}; filled {sum(r['ok'] for r in D)}; failed {sum(not r['ok'] for r in D)} "
      f"({100*np.mean([not r['ok'] for r in D]):.1f}%); 6042 share of DIP fails {100*np.mean(['6042' in json.dumps(r['err']) for r in D if not r['ok']]):.0f}%")
    P("\n## 1. DIP buys: fail rate vs pr (price before his tx / post-dump price), per day")
    edges = [(0, 0.98), (0.98, 1.0001), (1.0001, 1.03), (1.03, 1.05), (1.05, 1.08), (1.08, 1.10), (1.10, 1.15), (1.15, 1.20), (1.20, 1.30), (1.30, 9)]
    days = sorted({r["day"] for r in D})
    P("| pr | n | fail % | " + " | ".join(f"D{d} n / fail%" for d in days) + " |"); P("|---|---|---|" + "---|" * len(days))
    for lo, hi in edges:
        v = [r for r in D if lo <= r["pr"] < hi]
        if not v: continue
        cells = []
        for d in days:
            w = [r for r in v if r["day"] == d]; cells.append(f"{len(w)} / {100*np.mean([not r['ok'] for r in w]):.0f}" if w else "-")
        P(f"| {lo:.2f}-{hi:.2f} | {len(v)} | {100*np.mean([not r['ok'] for r in v]):.0f} | " + " | ".join(cells) + " |")
    P("\n## 2. DIP fills: lot P&L by pr (price paid vs post-dump), all days (mSOL/lot before tx costs; % of SOL in; 90% bootstrap of mean)")
    F = [r for r in D if r["ok"] and "lot_pnl" in r]
    P(f"DIP fills with lots: {len(F)}; total {sum(r['lot_pnl'] for r in F):+.2f} SOL; mean size {np.mean([r['lot_cost'] for r in F]):.3f} SOL")
    P("| pr | lots | SOL | mSOL/lot [90%] | %/SOL | win % | " + " | ".join(f"D{d} SOL (n)" for d in days) + " |"); P("|---|---|---|---|---|---|" + "---|" * len(days))
    for lo, hi in edges:
        v = [r for r in F if lo <= r["pr"] < hi]
        if not v: continue
        p = np.array([r["lot_pnl"] for r in v]); a, b = boot_mean(p)
        cells = []
        for d in days:
            w = [r["lot_pnl"] for r in v if r["day"] == d]; cells.append(f"{sum(w):+.2f} ({len(w)})" if w else "-")
        P(f"| {lo:.2f}-{hi:.2f} | {len(v)} | {p.sum():+.2f} | {1000*p.mean():+.2f} [{1000*a:+.1f}..{1000*b:+.1f}] | {100*p.sum()/sum(r['lot_cost'] for r in v):+.2f} | {100*np.mean(p>0):.0f} | " + " | ".join(cells) + " |")
    P("\n## 3. DIP fills: lot P&L by outside BUYS between the dump and him")
    P("| buys ahead | lots | SOL | mSOL/lot [90%] | %/SOL | pr p50 | " + " | ".join(f"D{d} SOL (n)" for d in days) + " |"); P("|---|---|---|---|---|---|" + "---|" * len(days))
    for lo, hi in ((0, 0), (1, 1), (2, 3), (4, 7), (8, 999)):
        v = [r for r in F if lo <= r["nb_ahead"] <= hi]
        if not v: continue
        p = np.array([r["lot_pnl"] for r in v]); a, b = boot_mean(p)
        cells = []
        for d in days:
            w = [r["lot_pnl"] for r in v if r["day"] == d]; cells.append(f"{sum(w):+.2f} ({len(w)})" if w else "-")
        P(f"| {lo}-{hi} | {len(v)} | {p.sum():+.2f} | {1000*p.mean():+.2f} [{1000*a:+.1f}..{1000*b:+.1f}] | {100*p.sum()/sum(r['lot_cost'] for r in v):+.2f} | {np.median([r['pr'] for r in v]):.3f} | " + " | ".join(cells) + " |")
    P("\n## 4. DIP fills: buys ahead x pr (mSOL/lot, n)")
    pe = [(0, 1.0001), (1.0001, 1.05), (1.05, 1.10), (1.10, 1.20), (1.20, 9)]
    P("| buys ahead | " + " | ".join(f"pr {a:.2f}-{b:.2f}" for a, b in pe) + " |"); P("|---|" + "---|" * len(pe))
    for lo, hi in ((0, 0), (1, 1), (2, 3), (4, 999)):
        cells = []
        for a, b in pe:
            v = [r["lot_pnl"] for r in F if lo <= r["nb_ahead"] <= hi and a <= r["pr"] < b]
            cells.append(f"{1000*np.mean(v):+.1f} ({len(v)})" if v else "-")
        P(f"| {lo}-{hi} | " + " | ".join(cells) + " |")
    P("\n## 5. His DIP timing: slots after dump 0/1/2 %, chain-clock ms p25/50/75, outside trades ahead p25/50/75")
    for nm, v in (("fills", [r for r in D if r["ok"]]), ("fails", [r for r in D if not r["ok"]])):
        ds = np.array([r["d_slots"] for r in v])
        P(f"- {nm} n={len(v)}: slots 0/1/2 = " + "/".join(f"{100*np.mean(ds==k):.0f}" for k in (0, 1, 2)) +
          f"; ms {np.percentile([r['d_ms'] for r in v],[25,50,75]).round(0)}; trades ahead {np.percentile([r['n_ahead'] for r in v],[25,50,75])}; pr p50 {np.median([r['pr'] for r in v]):.3f}")
    pickle.dump(H, open(f"{OUT}/hctx2.pkl", "wb"))
    open(f"{OUT}/l5.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
