# READ-ONLY (host, no RPC): competitors' REAL results on the same launches we watch / fire on (rule #2), next to our model.
# usage: python3 -I same_launch.py <comp_rows.json> <launches.json> <comp_summary.json>
import sys, json, statistics, collections
CR = json.load(open(sys.argv[1])); LA = {l["mint"]: l for l in json.load(open(sys.argv[2]))}; SU = json.load(open(sys.argv[3]))
AG = 459653000
lane = {s["wallet"] for s in SU}
t0 = max(min(s["t0"] for s in SU), 0)
by = collections.defaultdict(list)
for r in CR:
    if r["mint"] in LA and r["closed"]: by[r["mint"]].append(r)
# launches inside the fetched window (competitor histories cover ~ last 24 h)
win = [l for l in LA.values() if l["bt"] and l["bt"] >= t0]
print(f"watched launches inside the competitors' fetched window: {len(win)} (rule #2 {sum(l['r2'] for l in win)}, with our model p2 {sum(l['p2'] is not None for l in win)})")
for lab, sel in (("rule #2", lambda l: l["r2"]), ("rule #2 w/o create-ms", lambda l: l["r2nc"] and not l["r2"]), ("other watched", lambda l: not l["r2nc"])):
    xs = [l for l in win if sel(l)]
    tr = [r for l in xs for r in by.get(l["mint"], [])]
    hit = [l for l in xs if by.get(l["mint"])]
    p2 = [l["p2"] for l in xs if l["p2"] is not None]
    pn = [r["pnl"] for r in tr]; rt = [r["ret"] for r in tr]
    print(f"\n{lab}: launches {len(xs)}, traded by >=1 tracked competitor {len(hit)} ({len(hit)/max(1,len(xs)):.0%}), competitor trades {len(tr)}")
    if pn:
        print(f"  competitors' real PnL: total {sum(pn):+.2f} SOL, mean {statistics.mean(pn):+.4f}, median {statistics.median(pn):+.4f}, win {sum(p>0 for p in pn)/len(pn):.0%}, "
              f"mean return {statistics.mean(rt):+.2%}, median return {statistics.median(rt):+.2%}")
        pre = [r for r in tr if r["slot"] < AG]; post = [r for r in tr if r["slot"] >= AG]
        for nm, ys in (("pre-AG", pre), ("post-AG", post)):
            if ys: print(f"    {nm}: n {len(ys)} total {sum(r['pnl'] for r in ys):+.2f} mean ret {statistics.mean([r['ret'] for r in ys]):+.2%} win {sum(r['pnl']>0 for r in ys)/len(ys):.0%}")
    if p2:
        print(f"  our model S+2 on these launches (n {len(p2)}): total {sum(p2):+.2f}, mean {statistics.mean(p2):+.4f}, median {statistics.median(p2):+.4f}, win {sum(p>0 for p in p2)/len(p2):.0%}")
    # same launches where both exist: per launch mean competitor return vs our p2/1.5
    both = [(statistics.mean([r["ret"] for r in by[l["mint"]]]), l["p2"] / 1.5) for l in xs if by.get(l["mint"]) and l["p2"] is not None]
    if len(both) >= 5:
        a = [x for x, _ in both]; b = [y for _, y in both]
        try: c = statistics.correlation(a, b)
        except Exception: c = float("nan")
        print(f"  launches with both (n {len(both)}): competitors' mean return {statistics.mean(a):+.2%} vs our model return {statistics.mean(b):+.2%}; corr {c:.2f}")
    per = collections.defaultdict(list)
    for r in tr: per[r["wallet"][:6]].append(r)
    print("  by competitor:", " ".join(f"{w}:{len(v)}/{sum(r['pnl'] for r in v):+.2f}" for w, v in sorted(per.items(), key=lambda kv: -len(kv[1]))))
print("\nrule #2 launches in the window, one line each (our model p2 | competitors: wallet size ret hold_s n_sells dslot):")
for l in sorted([l for l in win if l["r2"]], key=lambda l: l["S"]):
    rs = sorted(by.get(l["mint"], []), key=lambda r: r["slot"])
    print(f"  {l['mint'][:8]} {l['grp'] or 'P'} {'post' if l['post_ag'] else 'pre '} gsol {l['gsol']:.2f} dev {l['dev']:.2f} p2 {('%+.3f' % l['p2']) if l['p2'] is not None else '  -   '}{' REF' if l['refused'] else '    '} | "
          + " ".join(f"{r['wallet'][:5]} {r['sol_in']:.2f} {r['ret']:+.0%} {r['hold_s']}s x{r['n_sells']} d{r['dslot']}" for r in rs))
