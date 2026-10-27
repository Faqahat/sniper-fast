#!/usr/bin/env python3
# LANDING2 step 4: the waterfall + pros tables (markdown) from OUT/timeline.json (+ presend_rows.json).
# Clocks: WALL = ms after the dump's first sighting on any of our feeds (our server clock). FEED = our tx's first sighting minus the
# dump's (same clock). BLOCK = chain position, real block sizes (getBlock), 212 ms per slot.
import json, collections, sys
import numpy as np

OUT = "/home/moiz/sniper-data/landing2"
R = json.load(open(f"{OUT}/timeline.json"))
PROS = {"HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ": "HkQ7hMjy", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq": "haqqiUUX",
        "8PgC4ngpx6zUG3KFQAQHqSeePDFA7kGyEaA2yMoZ4HUk": "8PgC4ngp", "6n2cCJrrEAi4SZbBquj9mffUGAFXhDBmFeQEi3maSRcx": "6n2cCJrr",
        "9k78QZywYyqUZvZrk1tDuE9qPUbZAz2aFbjUneihdgFX": "9k78QZyw", "G9G3dCBGjM1chfZJHvb722zzzm9FQfZi4KbLVGncGeTy": "G9G3dCBG",
        "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw": "DYXDDrZC", "CZ77onJzkSCwZC51Gg7H8oEUUJhqcx8LLKqnsNXWZSBx": "CZ77onJz",
        "6VzXcLk9rCLDHgRBmUGKK8HY2KvhHmR4pZPCxi4tA1kx": "6VzXcLk9", "5w8xtjc649Z628jVvJkwQE5p9aMhV2cUSWr8RVV9BieU": "5w8xtjc6"}
COHORT = set(json.load(open("/home/moiz/sniper/ops/overnight/dip/cohort_R1.json")))
INSTANT = 3


def P(v, ps=(50, 75, 90), f="{:.0f}"):
    v = [x for x in v if x is not None]
    if not v: return "–"
    return " / ".join(f.format(x) for x in np.percentile(v, ps))


def pct(n, d): return f"{n / d:.0%}" if d else "–"


def grp(r):
    c = r["L"]["cls"]
    if c == "jito": return "jito-relayer" if r["L"]["front"] == "relayer" else "jito-own"
    if c == "firebam": return "bam"
    if c in ("agave", "other", "?"): return "agave/other"
    return c


def quart(r):
    p = r["C"].get("dump_pos")
    if p is None: return "?"
    return "Q1" if p < .25 else "Q2" if p < .5 else "Q3" if p < .75 else "Q4"


def first_react(r):
    rv = [x for x in r["C"].get("rivals", []) if x["ds"] > 0 or (x["di"] is not None and x["di"] > INSTANT)]
    return min(rv, key=lambda x: (x["s"], x["i"])) if rv else None


def first_any(r):
    rv = r["C"].get("rivals", [])
    return min(rv, key=lambda x: (x["s"], x["i"])) if rv else None


def pro_first(r, w):
    rv = [x for x in r["C"].get("rivals", []) if x["user"] == w]
    return min(rv, key=lambda x: (x["s"], x["i"])) if rv else None


def best_pro(r):
    rv = [x for x in r["C"].get("rivals", []) if x["user"] in PROS and (x["ds"] > 0 or (x["di"] is not None and x["di"] > INSTANT))]
    return min(rv, key=lambda x: (x["s"], x["i"])) if rv else None


def cohort_first(r):
    rv = [x for x in r["C"].get("rivals", []) if x["user"] in COHORT and (x["ds"] > 0 or (x["di"] is not None and x["di"] > INSTANT))]
    return min(rv, key=lambda x: (x["s"], x["i"])) if rv else None


L = [r for r in R if r["C"].get("found_ours") and r["C"].get("found_dump")]
print(f"fires {len(R)}, both txs on chain {len(L)}, fills {sum(r['C']['our_ok'] for r in L)}, "
      f"dump block size from getBlock {sum(1 for r in L if r['C'].get('dump_n_src') == 'real')}/{len(L)}")
W = lambda r, k: r["W"].get(k)


def stage_row(name, rows):
    fw = [W(r, "first_write") for r in rows]
    ss = [r for r in rows if r["C"]["slot_delta"] == 0]
    return (f"| {name} | {len(rows)} | {pct(sum(r['C']['our_ok'] for r in rows), len(rows))} | {P([W(r, 'exec_wait') for r in rows], f='{:.1f}')} | "
            f"{P([W(r, 'decision') for r in rows], f='{:.1f}')} | {P(fw, f='{:.1f}')} | {P([W(r, 'send_to_seen') for r in ss])} | "
            f"{P([r['our_feed_ms'] for r in rows])} | {P([r['C']['our_ms'] for r in rows])} | {P([r['C']['our_ms'] for r in ss])} | "
            f"{pct(len(ss), len(rows))} |")


HDR = ("| group | fires | fill | exec-feed wait | decision | first write | write → seen (same slot) | feed landing | block landing (all) | block landing (same slot) | same slot |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|")
print("\n### W1. Waterfall per fire (ms; p50 / p75 / p90). Wall-clock stages start at the dump's first sighting on any of our feeds.")
print(HDR)
print(stage_row("all", L))
for s in ("FRA", "AMS"): print(stage_row(s, [r for r in L if r["srv"] == s]))
print(stage_row("fills", [r for r in L if r["C"]["our_ok"]]))
print(stage_row("failed buys", [r for r in L if not r["C"]["our_ok"]]))
print("\n### W2. By leader client (dump slot) and TPU front")
print(HDR)
for g in ("bam", "harmonic", "jito-own", "jito-relayer", "fd", "rakurai", "agave/other"):
    rows = [r for r in L if grp(r) == g]
    if rows: print(stage_row(g, rows))
print("\n### W3. By the dump's position in its block (real block size; Q4 = last quarter)")
print(HDR)
for q in ("Q1", "Q2", "Q3", "Q4"):
    rows = [r for r in L if quart(r) == q]
    if rows: print(stage_row(q, rows))
print("\n### W4. By the copy that landed (nonce: each path sends its own copy; the first to execute lands)")
print(HDR)
pc = collections.Counter(r["C"].get("our_path") for r in L)
for p, _ in pc.most_common():
    print(stage_row(str(p), [r for r in L if r["C"].get("our_path") == p]))
print("\n### W5. By window slot (1 = first block of the leader's 4-slot window; block 1 records <= 144 ms)")
print(HDR)
for k in (1, 2, 3, 4):
    rows = [r for r in L if r["L"]["window_slot"] == k]
    if rows: print(stage_row(f"window slot {k}", rows))

# ------------------------------------------------------------------ write order / acks per path
print("\n### W6. Per path: write start after the dump's first sighting, relay ack, and landing when that copy landed")
print("| path | fires sent | write start p50 / p90 (ms) | relay ack p50 / p90 (ms) | HTTP non-200 | landed (any) | of those fills | block landing of its landings p50 / p75 | same slot |")
print("|---|---|---|---|---|---|---|---|---|")
paths = collections.Counter(p for r in L for p in r["W"]["writes"])
for p, n in paths.most_common():
    ws = [r["W"]["writes"][p]["t0"] for r in L if p in r["W"]["writes"]]
    ak = [r["W"]["acks"][p]["ack_ms"] for r in L if p in r["W"]["acks"]]
    bad = sum(1 for r in L if p in r["W"]["acks"] and r["W"]["acks"][p]["status"] not in (200, None))
    ld = [r for r in L if r["C"].get("our_path") == p]
    print(f"| {p} | {n} | {P(ws, (50, 90), '{:.2f}')} | {P(ak, (50, 90), '{:.2f}')} | {bad} | {len(ld)} | {sum(r['C']['our_ok'] for r in ld)} | "
          f"{P([r['C']['our_ms'] for r in ld], (50, 75))} | {pct(sum(1 for r in ld if r['C']['slot_delta'] == 0), len(ld))} |")

# ------------------------------------------------------------------ spills
print("\n### S1. Spills (our tx in a later block than the dump)")
sp = [r for r in L if r["C"]["slot_delta"] > 0]
print(f"- spills {len(sp)}/{len(L)} ({pct(len(sp), len(L))}); land at block clock {P([r['C']['our_ms'] for r in sp])} ms; "
      f"same leader's next block {sum(1 for r in sp if r['L']['our_leader'] == r['leader'])}")
avoid = [r for r in sp if (lambda x: x is not None and x["ds"] == 0)(first_react(r))]
print(f"- a reacting rival still got into the dump's block in {len(avoid)} of {len(sp)} spills (avoidable); {len(sp) - len(avoid)} nobody reacting got in (structural)")
print("| time left in the dump's block (block clock) | fires | our spill | first reacting rival in the dump's block | best pro in the dump's block |")
print("|---|---|---|---|---|")
for lo, hi in ((0, 40), (40, 80), (80, 120), (120, 999)):
    rows = [r for r in L if lo <= r["C"]["left_ms"] < hi]
    fr = [first_react(r) for r in rows]; bp = [best_pro(r) for r in rows]
    print(f"| {lo}–{hi if hi < 999 else '212'} ms | {len(rows)} | {pct(sum(1 for r in rows if r['C']['slot_delta'] > 0), len(rows))} | "
          f"{pct(sum(1 for x in fr if x and x['ds'] == 0), sum(1 for x in fr if x))} | {pct(sum(1 for x in bp if x and x['ds'] == 0), sum(1 for x in bp if x))} |")

# ------------------------------------------------------------------ pros on the same dumps
def who_row(name, rows, pick):
    xs = [(r, pick(r)) for r in rows]
    xs = [(r, x) for r, x in xs if x]
    ms = [x["ms"] for _, x in xs]
    ss = sum(1 for _, x in xs if x["ds"] == 0)
    ahead = sum(1 for r, x in xs if (x["s"], x["i"]) < (r["C"]["our_slot"], r["C"]["our_idx"]))
    paired = [r["C"]["our_ms"] - x["ms"] for r, x in xs]
    return f"| {name} | {len(xs)} | {P(ms, (25, 50, 75))} | {pct(ss, len(xs))} | {pct(ahead, len(xs))} | {P(paired, (25, 50, 75))} |"


print("\n### P1. Who lands where on OUR dumps (block clock, ms after the dump; first buy attempt per wallet, ok or failed)")
print("| who | dumps | p25 / p50 / p75 | same slot | ahead of us | our lag behind them, paired (p25 / p50 / p75) |")
print("|---|---|---|---|---|---|")
print(f"| us | {len(L)} | {P([r['C']['our_ms'] for r in L], (25, 50, 75))} | {pct(sum(1 for r in L if r['C']['slot_delta'] == 0), len(L))} | – | – |")
print(who_row("first rival (any)", L, first_any))
print(who_row("first REACTING rival (> 3 txs after)", L, first_react))
print(who_row("first cohort bot (reacting)", L, cohort_first))
print(who_row("best named pro (reacting)", L, best_pro))
for w, n in PROS.items():
    if sum(1 for r in L if pro_first(r, w)) >= 8: print(who_row(n, L, lambda r, w=w: pro_first(r, w)))

print("\n### P2. Us vs the first reacting rival and the best pro, by leader client (block clock, median ms; same-slot share)")
print("| group | fires | us | us same slot | first reacting rival | its same slot | best pro | its same slot | our lag vs first reacting (paired p50) | vs best pro (paired p50) |")
print("|---|---|---|---|---|---|---|---|---|---|")
def cmp_row(name, rows):
    fr = [(r, first_react(r)) for r in rows]; fr = [(r, x) for r, x in fr if x]
    bp = [(r, best_pro(r)) for r in rows]; bp = [(r, x) for r, x in bp if x]
    return (f"| {name} | {len(rows)} | {P([r['C']['our_ms'] for r in rows], (50,))} | {pct(sum(1 for r in rows if r['C']['slot_delta'] == 0), len(rows))} | "
            f"{P([x['ms'] for _, x in fr], (50,))} | {pct(sum(1 for _, x in fr if x['ds'] == 0), len(fr))} | {P([x['ms'] for _, x in bp], (50,))} (n={len(bp)}) | "
            f"{pct(sum(1 for _, x in bp if x['ds'] == 0), len(bp))} | {P([r['C']['our_ms'] - x['ms'] for r, x in fr], (50,))} | {P([r['C']['our_ms'] - x['ms'] for r, x in bp], (50,))} |")
for g in ("bam", "harmonic", "jito-own", "jito-relayer", "fd", "rakurai", "agave/other"):
    rows = [r for r in L if grp(r) == g]
    if rows: print(cmp_row(g, rows))
print(cmp_row("all", L))
print("\n### P3. Same, by the dump's position in its block")
print("| group | fires | us | us same slot | first reacting rival | its same slot | best pro | its same slot | our lag vs first reacting (paired p50) | vs best pro (paired p50) |")
print("|---|---|---|---|---|---|---|---|---|---|")
for q in ("Q1", "Q2", "Q3", "Q4"):
    rows = [r for r in L if quart(r) == q]
    if rows: print(cmp_row(q, rows))
print("\n### P4. Same-slot landings only (both us and them in the dump's block): the pure speed gap")
print("| group | dumps (both same slot) | us p50 | first reacting rival p50 | paired lag p25 / p50 / p75 |")
print("|---|---|---|---|---|")
for g in ("bam", "harmonic", "jito-own", "jito-relayer", "fd", "all"):
    rows = [r for r in L if (g == "all" or grp(r) == g) and r["C"]["slot_delta"] == 0]
    xs = [(r, first_react(r)) for r in rows]; xs = [(r, x) for r, x in xs if x and x["ds"] == 0]
    if xs: print(f"| {g} | {len(xs)} | {P([r['C']['our_ms'] for r, _ in xs], (50,))} | {P([x['ms'] for _, x in xs], (50,))} | {P([r['C']['our_ms'] - x['ms'] for r, x in xs], (25, 50, 75))} |")

# ------------------------------------------------------------------ feed clock (exec-feed tape) for the same people
print("\n### P5. Feed clock (our executed feed: rival's trade arrival minus the dump's; ours: first sighting minus the dump's), medians")
print("| who | dumps | median ms |")
print("|---|---|---|")
print(f"| us | {sum(1 for r in R if r['our_feed_ms'] is not None)} | {P([r['our_feed_ms'] for r in R], (50,))} |")
fr_feed = []
for r in R:
    if r["F"]: fr_feed.append(min(r["F"].values()))
print(f"| first rival buy on the feed | {len(fr_feed)} | {P(fr_feed, (50,))} |")
for w, n in PROS.items():
    v = [r["F"][w] for r in R if w in r["F"]]
    if len(v) >= 8: print(f"| {n} | {len(v)} | {P(v, (50,))} |")

# ------------------------------------------------------------------ r16 clock2 records (13 fires): per-feed arrivals
print("\n### C2. FRA run 16 clock2 records (13 fires): per-feed landing (our tx's arrival minus the dump's on the same feed) vs the block clocks")
print("| fire (PKT) | client | dump pos | buy pos | slots | land_ms_bmix | land_ms_pos | kaldera | turbo-kaldera | erpc | kaldera-tx (exec) | ours: write→seen |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
import time
for r in R:
    c = r["W"].get("clock2")
    if not c: continue
    f = c.get("feeds") or {}
    g = lambda k: f"{f[k][2]:.1f}" if k in f else "–"
    t = time.strftime("%H:%M:%S", time.gmtime(r["W"].get("clock2", {}) and (json.load(open(f'{OUT}/fires_engine.json'))[0]['t_fire'] if False else 0)))
    print(f"| {r['mint'][:6]} | {r['client']} | {c.get('dump_pos') and round(c['dump_pos'], 2)} | {c.get('buy_pos') and round(c['buy_pos'], 2)} | "
          f"{(c.get('buy_slot') or 0) - (c.get('dump_slot') or 0)} | {c.get('land_ms_bmix') and round(c['land_ms_bmix'], 1)} | {c.get('land_ms_pos') and round(c['land_ms_pos'], 1)} | "
          f"{g('kaldera')} | {g('turbo-kaldera')} | {g('erpc')} | {g('kaldera-tx')} | {r['W']['send_to_seen'] and round(r['W']['send_to_seen'], 1)} |")
