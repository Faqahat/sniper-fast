#!/usr/bin/env python3
"""Test concrete pre-create pre-buy rules OOS (train/val), robustness to tail winners,
and whether fund_amount adds signal beyond dev_buy. Uses precreate_feat.json."""
import json, statistics as st
F = json.load(open("/root/precreate/precreate_feat.json"))
POP = [r for r in F if not r["is_his"] and r["n_poll"] > 0]
SPLIT = 456742465


def summ(rows, key):
    v = [r[key] for r in rows if r.get(key) is not None]
    if not v:
        return None
    n = len(v)
    mean = sum(v) / n
    s = sorted(v, reverse=True)
    drop2 = (sum(v) - s[0] - s[1]) / (n - 2) if n > 2 else mean
    p15 = sum(1 for r in rows if r.get("pump15")) / len(rows)
    return dict(n=n, mean=mean, med=st.median(v), drop2=drop2, p15=p15,
                tot=sum(v), win=sum(1 for x in v if x > 0) / n)


def show(name, rows):
    tr = [r for r in rows if r["create_slot"] < SPLIT]
    va = [r for r in rows if r["create_slot"] >= SPLIT]
    for lab, rr in [("FULL", rows), ("TRAIN", tr), ("VAL", va)]:
        for fk in ["netR_opt", "netR_real"]:
            s = summ(rr, fk)
            if s:
                print("  %-26s %-5s %-10s n=%4d p15=%4.0f%% win=%3.0f%% mean=%+.4f med=%+.4f drop2=%+.4f" % (
                    name, lab, fk, s["n"], 100 * s["p15"], 100 * s["win"], s["mean"], s["med"], s["drop2"]))
    print()


def van(r):
    return r["vanilla"] == 1


print("=== E. Concrete pre-create pre-buy RULES (unbiased pop, OOS split, net R per snipe) ===\n")
show("vanilla ALL (baseline)", [r for r in POP if van(r)])
show("vanilla + fund>=1SOL", [r for r in POP if van(r) and (r["fund_amount"] or 0) >= 1])
show("vanilla + fund>=2SOL", [r for r in POP if van(r) and (r["fund_amount"] or 0) >= 2])
show("vanilla + recency>=750", [r for r in POP if van(r) and (r["fund_recency_slots"] or 0) >= 750])
show("vanilla + notfresh(rec>=750) + fund>=1 + serial<=2",
     [r for r in POP if van(r) and (r["fund_recency_slots"] or 0) >= 750
      and (r["fund_amount"] or 0) >= 1 and r["serial_launches"] <= 2])
show("vanilla + fund>=2 + serial<=2 + notfresh",
     [r for r in POP if van(r) and (r["fund_amount"] or 0) >= 2
      and r["serial_launches"] <= 2 and (r["fund_recency_slots"] or 0) >= 750])
show("vanilla + sharedfunder>=5", [r for r in POP if van(r) and r["src_fanout"] >= 5])

print("=== F. fund_amount orthogonal to dev_buy? pump15 by fund_amount WITHIN dev_buy>=1 band ===")
hi_dev = [r for r in POP if van(r) and r["dev_buy"] >= 1.0]
for lo, hiq, lab in [(0, 1, "fund<1"), (1, 2, "fund1-2"), (2, 5, "fund2-5"), (5, 1e9, "fund>=5")]:
    sub = [r for r in hi_dev if lo <= (r["fund_amount"] or 0) < hiq]
    if sub:
        p15 = sum(r["pump15"] for r in sub) / len(sub)
        mr = sum(r["netR_real"] for r in sub) / len(sub)
        print("  dev>=1 & %-8s n=%3d pump15=%4.0f%% netR_real=%+.4f" % (lab, len(sub), 100 * p15, mr))
print("  corr(fund_amount, dev_buy):", end=" ")
xs = [(r["fund_amount"], r["dev_buy"]) for r in POP if van(r) and r["fund_amount"] is not None]
import math
n = len(xs); mx = sum(a for a, _ in xs) / n; my = sum(b for _, b in xs) / n
cov = sum((a - mx) * (b - my) for a, b in xs) / n
sx = math.sqrt(sum((a - mx) ** 2 for a, _ in xs) / n); sy = math.sqrt(sum((b - my) ** 2 for _, b in xs) / n)
print("%.3f (n=%d)" % (cov / (sx * sy) if sx * sy else 0, n))
