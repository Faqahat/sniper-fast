# READ-ONLY (host, no RPC): one markdown row per competitor from comp_summary.json + comp_rows.json (+ cand.json feed timing)
# usage: python3 -I table.py <comp_summary.json> <comp_rows.json> <cand.json> <launches.json>
import sys, json, statistics, collections
SU = json.load(open(sys.argv[1])); CR = json.load(open(sys.argv[2])); CA = {c["wallet"]: c for c in json.load(open(sys.argv[3]))}
LA = json.load(open(sys.argv[4]))
AG = 459653000
med = lambda xs: statistics.median(xs) if xs else None
print("| wallet | hours | trades/h | net SOL/h | SOL/trade | size med (tiers) | win | median | w/o best 3 | hold med | exit | dslot 0 / +1 | our feed saw it | fill vs post-bundle | buy fee+tip | watched picks (rule #2) | PnL on watched / rule #2 | pre-AG / post-AG per trade |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for s in sorted(SU, key=lambda s: -(s["net_h"] or 0)):
    W = s["wallet"]; rows = [r for r in CR if r["wallet"] == W]; cl = [r for r in rows if r["closed"]]
    if not cl: continue
    tiers = collections.Counter(round(r["sol_in"], 1) for r in rows).most_common(4)
    ks = [r for r in rows if r["dslot"] is not None]
    d0 = sum(r["dslot"] == 0 for r in ks) / len(ks) if ks else None; d1 = sum(r["dslot"] == 1 for r in ks) / len(ks) if ks else None
    c = CA.get(W, {})
    feed = [t["feed_ms"] for t in c.get("trades", []) if t["feed_ms"] is not None]
    fill = [t["fill"] for t in c.get("trades", []) if t["fill"]]
    ns = collections.Counter(r["n_sells"] == 1 for r in cl)
    ex = "single" if ns[True] / len(cl) > 0.8 else ("ladder" if ns[False] / len(cl) > 0.6 else "mixed")
    w = [r for r in cl if r["watched"]]; r2 = [r for r in cl if r["r2"]]
    pre = [r for r in cl if r["slot"] < AG]; post = [r for r in cl if r["slot"] >= AG]
    pt = lambda xs: f"{sum(r['pnl'] for r in xs)/len(xs):+.3f} (n {len(xs)})" if xs else "-"
    print(f"| {W[:8]} | {s['hours']:.1f} | {s['per_h']:.1f} | **{s['net_h']:+.2f}** | {s['mean']:+.3f} | {s['size_med']:.2f} ({', '.join(f'{k}x{v}' for k, v in tiers)}) | {s['win']:.0%} | {s['median']:+.3f} | {s['ex3']:+.1f} | {s['hold_med']} s | {ex} | "
          f"{(f'{d0:.0%} / {d1:.0%}' if d0 is not None else '-')} (n {len(ks)}) | {(f'{med(feed):.0f} ms (n {len(feed)})' if feed else '-')} | {(f'{med(fill):.2f}x' if fill else '-')} | "
          f"{s['buycost_med']:.4f} ({100*s['buycost_pct']:.1f}%) | {len(w)} ({len(r2)}) | {sum(r['pnl'] for r in w):+.2f} / {sum(r['pnl'] for r in r2):+.2f} | {pt(pre)} / {pt(post)} |")
