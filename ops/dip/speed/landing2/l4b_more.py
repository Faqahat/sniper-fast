#!/usr/bin/env python3
# LANDING2 step 4b: extra tables. Who the first reacting rival is (spam vs real), the guard deadline (first crossing) we must beat,
# the feed clock per client for rivals, our write->seen per (path x client), and the lowest send->seen floors.
import json, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()):      # l4_tables prints its own tables on import
    from l4_tables import R, L, grp, quart, first_react, best_pro, P, pct, PROS, COHORT, INSTANT

print("\n### X1. The first reacting rival on our dumps: who, and did its buy succeed?")
fr = [(r, first_react(r)) for r in L]; fr = [(r, x) for r, x in fr if x]
c = collections.Counter(x["user"] for _, x in fr)
print(f"- first reacting rival succeeded (ok) on {sum(1 for _, x in fr if x['ok'])}/{len(fr)} dumps; distinct wallets {len(c)}; "
      f"in cohort {sum(1 for _, x in fr if x['user'] in COHORT)}; named pros {sum(1 for _, x in fr if x['user'] in PROS)}")
print("- most frequent:", ", ".join(f"{u[:8]} {n} ({sum(1 for _, x in fr if x['user'] == u and x['ok'])} ok)" for u, n in c.most_common(10)))


def first_ok_react(r):
    rv = [x for x in r["C"].get("rivals", []) if x["ok"] and (x["ds"] > 0 or (x["di"] is not None and x["di"] > INSTANT))]
    return min(rv, key=lambda x: (x["s"], x["i"])) if rv else None


print("\n### X2. The deadline: when the price first passes our +5% guard (block clock), vs when we land")
print("| group | fires | guard first crossed p25 / p50 / p75 (ms) | crossed inside the dump's block | first SUCCESSFUL reacting buy p50 | us p50 | fills |")
print("|---|---|---|---|---|---|---|")
for g in ("bam", "harmonic", "jito-own", "jito-relayer", "fd", "all"):
    rows = [r for r in L if g == "all" or grp(r) == g]
    fc = [r["C"].get("first_cross_ms") for r in rows if r["C"].get("first_cross_ms") is not None]
    inb = sum(1 for r in rows if r["C"].get("first_cross_slot") == 0)
    fo = [first_ok_react(r) for r in rows]
    print(f"| {g} | {len(rows)} | {P(fc, (25, 50, 75))} | {pct(inb, len(rows))} | {P([x['ms'] for x in fo if x], (50,))} | {P([r['C']['our_ms'] for r in rows], (50,))} | {pct(sum(r['C']['our_ok'] for r in rows), len(rows))} |")

print("\n### X3. Feed clock by leader client (ms after the dump on our executed feed; rivals = successful buys only)")
print("| group | us (first sighting) p50 | first rival buy p50 | HkQ7 p50 (n) | best named pro p50 (n) | first cohort p50 (n) |")
print("|---|---|---|---|---|---|")
for g in ("bam", "harmonic", "jito-own", "jito-relayer", "fd", "all"):
    rows = [r for r in R if g == "all" or grp(r) == g]
    first = [min(r["F"].values()) for r in rows if r["F"]]
    hk = [r["F"]["HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ"] for r in rows if "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ" in r["F"]]
    bp = [min(v for u, v in r["F"].items() if u in PROS) for r in rows if any(u in PROS for u in r["F"])]
    co = [min(v for u, v in r["F"].items() if u in COHORT) for r in rows if any(u in COHORT for u in r["F"])]
    print(f"| {g} | {P([r['our_feed_ms'] for r in rows], (50,))} | {P(first, (50,))} | {P(hk, (50,))} ({len(hk)}) | {P(bp, (50,))} ({len(bp)}) | {P(co, (50,))} ({len(co)}) |")

print("\n### X4. Our write -> our tx first seen (ms), by the copy that landed x leader client (same-slot landings; p50 (n))")
cl = ("bam", "harmonic", "jito-own", "jito-relayer", "fd")
print("| copy | " + " | ".join(cl) + " |")
print("|---|" + "---|" * len(cl))
for p in ("nozomi", "staked-rpc", "helius", "landx-fra3", "helius-swqos", "jito-bundle", "bolt"):
    cells = []
    for g in cl:
        v = [r["W"]["send_to_seen"] for r in L if r["C"].get("our_path") == p and grp(r) == g and r["C"]["slot_delta"] == 0 and r["W"]["send_to_seen"] is not None]
        cells.append(f"{np.median(v):.0f} ({len(v)})" if v else "–")
    print(f"| {p} | " + " | ".join(cells) + " |")

print("\n### X5. Floors: the fastest write -> seen we ever measured (ms), per client (fires), and pre-sent attempts")
for g in cl:
    v = sorted(r["W"]["send_to_seen"] for r in L if grp(r) == g and r["W"]["send_to_seen"] is not None)
    print(f"- {g}: lowest {', '.join(f'{x:.1f}' for x in v[:5])} | p10 {np.percentile(v, 10):.1f}")
pr = json.load(open("/home/moiz/sniper-data/landing2/presend_rows.json"))
for g in ("bam", "harmonic", "jito", "fd"):
    v = sorted(r["s2seen"] for r in pr if r["cls"] == g and r["s2seen"] is not None)
    print(f"- pre-sent {g}: lowest {', '.join(f'{x:.1f}' for x in v[:5])} | p5 {np.percentile(v, 5):.1f} | p10 {np.percentile(v, 10):.1f}")

print("\n### X6. Feed vs block clock for our same-slot landings (how far the position clock is from real time)")
ss = [r for r in L if r["C"]["slot_delta"] == 0]
d = [r["C"]["our_ms"] - r["our_feed_ms"] for r in ss if r["our_feed_ms"] is not None]
print(f"- block minus feed (ms), p10 / p25 / p50 / p75 / p90: {P(d, (10, 25, 50, 75, 90))}; by quartile: " +
      ", ".join(f"{q} {P([r['C']['our_ms'] - r['our_feed_ms'] for r in ss if quart(r) == q and r['our_feed_ms'] is not None], (50,))}" for q in ("Q1", "Q2", "Q3", "Q4")))
print("- feed landing (same slot) by quartile p50: " + ", ".join(f"{q} {P([r['our_feed_ms'] for r in ss if quart(r) == q], (50,))}" for q in ("Q1", "Q2", "Q3", "Q4")))

print("\n### X7. Exec-feed wait and decision by server and run (ms, p50 / p90)")
for b in sorted({r["base"] for r in L}):
    rows = [r for r in L if r["base"] == b]
    print(f"- {b}: n={len(rows)} exec wait {P([r['W']['exec_wait'] for r in rows], (50, 90), '{:.1f}')} | decision {P([r['W']['decision'] for r in rows], (50, 90), '{:.1f}')} | "
          f"first write {P([r['W']['first_write'] for r in rows], (50, 90), '{:.1f}')} | first feed {collections.Counter(r['W']['first_feed'] for r in rows).most_common(3)}")
lat = collections.defaultdict(list)
for r in L:
    for k, v in (r.get("lat_us") or {}).items(): lat[k].append(v)
print("- decision parts (us, p50 / p90): " + ", ".join(f"{k} {P(v, (50, 90))}" for k, v in lat.items()))

print("\n### X8. Mean decomposition of our FEED-clock landing (ms per average fire)")
rows = [r for r in L if r["our_feed_ms"] is not None and r["W"]["first_write"] is not None]
m = lambda v: float(np.mean(v))
fw = m([r["W"]["first_write"] for r in rows]); fl = m([r["our_feed_ms"] for r in rows])
ss = [r for r in rows if r["C"]["slot_delta"] == 0]; sp = [r for r in rows if r["C"]["slot_delta"] > 0]
print(f"- fires {len(rows)}: mean feed landing {fl:.1f} = first write {fw:.1f} (exec wait {m([r['W']['exec_wait'] for r in rows]):.1f} + decision {m([r['W']['decision'] for r in rows]):.1f} + write gap) "
      f"+ write->seen {m([r['W']['send_to_seen'] for r in rows]):.1f}")
print(f"- same slot ({len(ss)}): mean {m([r['our_feed_ms'] for r in ss]):.1f}, median {np.median([r['our_feed_ms'] for r in ss]):.1f} | spilled ({len(sp)}): mean {m([r['our_feed_ms'] for r in sp]):.1f}, median {np.median([r['our_feed_ms'] for r in sp]):.1f}")
print(f"- spill share of the mean: {len(sp) / len(rows) * (m([r['our_feed_ms'] for r in sp]) - m([r['our_feed_ms'] for r in ss])):.1f} ms of {fl:.1f}")
