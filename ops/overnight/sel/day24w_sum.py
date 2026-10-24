#!/usr/bin/env python3
# Summary of day24w.py. Owner 10-24: "With our current config, replay the last 24 hours with the 'wider' tier" -> what if the
# NON-dev tokens were picked from the wider tier (IMIT1 score >= top4) instead of strict (>= top2)? Run 5 = no TP / SL -10% / sell
# by 6 slots (1.3 s); the dev's tokens (bwamJzzt as user / creator / payer) from top4 at 0.75 SOL; all other tokens from top2 at 0.35.
# Same engine limits and real costs as day24_sum.py: rows in time order over both windows; one open position (busy 1.6 s after a
# filled buy, 0.8 s after a blocked one); >= 5 slots between picks on a token; +0.0035 SOL per fill over the replay's tx costs,
# 0.0005 per blocked buy. Day / night splits here include the blocked-buy costs (day24_sum.py's split left them out).
# usage: python3 -I day24w_sum.py      (needs day24w_r2.json + day24w_r3.json; day24_<win>.json, if present, for the cross-check)
import json, os, collections
D = "/home/moiz/sniper/ops/overnight/sel"; EXTRA = 0.0035; FAIL = 0.0005
TH = json.load(open(f"{D}/IMIT1.json"))["thresholds"]; T2, T4 = TH["top2"], TH["top4"]
EX, TP5 = "tpnone_sl10_1.3s", "tp5_sl10_1.3s"
W = [json.load(open(f"{D}/day24w_{w}.json")) for w in ("r2", "r3")]
rows = sorted([o for w in W for o in w["rows"]], key=lambda o: o["t"])
DAY_END = W[0]["t1"] + 1                 # day = the R2 window (10-23 06:30-18:33 PKT), night = R3 (19:26-06:27)
hours = sum((w["t1"] - w["t0"]) / 3600 for w in W)
wonly = lambda o: (not o["dev"]) and T4 <= o["score"] < T2           # what the wider tier adds: other tokens, top4 <= score < top2
strict_oth = lambda o: (not o["dev"]) and o["score"] >= T2
RULES = {
    "A run 5 as set": lambda o: (0.75, EX) if o["dev"] and o["score"] >= T4 else (0.35, EX) if o["score"] >= T2 else None,
    "B run 5 + wider for all tokens": lambda o: (0.75, EX) if o["dev"] and o["score"] >= T4 else (0.35, EX) if o["score"] >= T4 else None,
    "C wider for all, 0.35, no dev 0.75": lambda o: (0.35, EX) if o["score"] >= T4 else None,
    "D = B, wider-only picks at TP +5%": lambda o: ((0.75, EX) if o["dev"] and o["score"] >= T4 else (0.35, EX) if o["score"] >= T2 else
                                                  (0.35, TP5) if o["score"] >= T4 else None),
}
half = lambda o: "day" if o["t"] < DAY_END else "night"

def sim(rule, L, src=None):
    """day24_sum.py's engine loop; also returns the wider-only part [SOL, fills, won, blocked] and the picks taken {(m, s): P&L}"""
    busy_until = -1.0; last_pick = {}; tot = 0.0; fills = wins = blocked = 0; per = collections.Counter(); wo = [0.0, 0, 0, 0]; taken = {}
    for o in (rows if src is None else src):
        r = rule(o)
        if r is None: continue
        size, ex = r
        if o["t"] < busy_until: continue
        if o["m"] in last_pick and o["s"] < last_pick[o["m"]] + 5: continue
        last_pick[o["m"]] = o["s"]
        v = o["ours"].get(f"{L}|{size}")
        if v is None: continue
        if v == "b":
            tot -= FAIL; blocked += 1; busy_until = o["t"] + 0.8; per[half(o)] -= FAIL; taken[(o["m"], o["s"])] = -FAIL
            if wonly(o): wo[0] -= FAIL; wo[3] += 1
            continue
        p = v[ex] - EXTRA; tot += p; fills += 1; wins += p > 0; busy_until = o["t"] + (2.8 if "2.5s" in ex else 1.6)
        per[half(o)] += p; taken[(o["m"], o["s"])] = p
        if wonly(o): wo[0] += p; wo[1] += 1; wo[2] += p > 0
    return tot, fills, wins, blocked, per, wo, taken

def alone(sel, L, ex, size=0.35):
    """each pick on its own (no busy limit, no 5-slot rule): dumps, fills, won, blocked, SOL, {day/night: SOL}"""
    n = f = w = b = 0; sol = 0.0; per = collections.Counter()
    for o in rows:
        if not sel(o): continue
        n += 1; v = o["ours"].get(f"{L}|{size}")
        if v is None: continue
        if v == "b": b += 1; sol -= FAIL; per[half(o)] -= FAIL; continue
        p = v[ex] - EXTRA; f += 1; w += p > 0; sol += p; per[half(o)] += p
    return n, f, w, b, sol, per

def alone_s(sel, L, ex):
    n, f, w, b, sol, per = alone(sel, L, ex)
    pf = f"{sol / f / 0.35 * 100:+.2f}%/fill" if f else "n/a"
    return f"{n} dumps, {f} fills ({w} won) {b} blocked, {sol:+.3f} SOL (day {per['day']:+.3f} | night {per['night']:+.3f}), {pf}"

LATS = sorted({int(k.split("|")[0]) for o in rows for k in o["ours"]})
print(f"last 24 h replay, wider tier: {len(rows)} candidate dumps with score >= top4 over {hours:.1f} h recorded "
      f"(10-23 06:30 -> 10-24 06:27 PKT; 18:33-19:26 not recorded)")
print(f"  the dev's tokens {sum(1 for o in rows if o['dev'])} | other tokens strict (>= top2) {sum(1 for o in rows if strict_oth(o))} | "
      f"other tokens wider-only (top4 <= score < top2) {sum(1 for o in rows if wonly(o))} (day {sum(1 for o in rows if wonly(o) and half(o) == 'day')}, "
      f"night {sum(1 for o in rows if wonly(o) and half(o) == 'night')})")
print(f"  costs: +{EXTRA} SOL per fill over the replay's tx costs, {FAIL} per blocked buy; exit {EX} unless stated; "
      f"day = 10-23 06:30-18:33, night = 19:26-06:27 PKT (splits include blocked-buy costs)\n")
RES = {}
for L in LATS:
    print(f"--- landing {L} ms after the dump")
    RES[L] = {nm: sim(rule, L) for nm, rule in RULES.items()}
    tA, *_, takenA = RES[L]["A run 5 as set"]
    for nm, (tot, f, w, b, per, wo, taken) in RES[L].items():
        s = f"  {nm:36s} {tot:+8.3f} SOL | {f:3d} fills ({w:3d} won) {b:3d} blocked | day {per['day']:+7.3f} | night {per['night']:+7.3f}"
        if not nm.startswith("A"):
            lost = [k for k in takenA if k not in taken]
            s += (f" | vs A {tot - tA:+.3f}: wider-only picks {wo[0]:+.3f} ({wo[1]} fills, {wo[2]} won, {wo[3]} blocked), "
                  f"rest {tot - tA - wo[0]:+.3f} ({len(lost)} of A's picks crowded out, worth {sum(takenA[k] for k in lost):+.3f} in A)")
        print(s)
    print(f"  wider-only picks on their own, no TP : {alone_s(wonly, L, EX)}")
    print(f"  wider-only picks on their own, TP +5%: {alone_s(wonly, L, TP5)}")
    print(f"  (reference) strict other-token picks : {alone_s(strict_oth, L, EX)}")

# sanity check: rule A must reproduce run 5 from day24_sum.py (+10.805 / +7.205 / +5.374 / +3.165 at 35 / 50 / 75 / 110 ms)
KNOWN = {35: 10.805, 50: 7.205, 75: 5.374, 110: 3.165}
print("\nsanity check, rule A vs run 5 of day24_sum.py:")
old = None
if all(os.path.exists(f"{D}/day24_{w}.json") for w in ("r2", "r3")):
    old = sorted([o for w in ("r2", "r3") for o in json.load(open(f"{D}/day24_{w}.json"))["rows"]], key=lambda o: o["t"])
    new = {(o["m"], o["s"]): o for o in rows}
    miss = [o for o in old if (o["m"], o["s"]) not in new]
    diff = [o for o in old if (o["m"], o["s"]) in new and (o["ours"], o["score"], o["dev"], o["t"]) != tuple(new[(o["m"], o["s"])][k] for k in ("ours", "score", "dev", "t"))]
    print(f"  rows: day24 {len(old)}, of them missing in day24w {len(miss)}, with different values {len(diff)}")
for L in LATS:
    tA = RES[L]["A run 5 as set"][0]
    s = f"  {L:>3} ms: A here {tA:+.3f}"
    if old is not None: s += f" | A on day24_<win>.json {sim(RULES['A run 5 as set'], L, old)[0]:+.3f}"
    if L in KNOWN: s += f" | day24_sum.py run 5 {KNOWN[L]:+.3f} (diff {tA - KNOWN[L]:+.3f})"
    print(s)

# robustness: t is the block time in whole seconds, so same-second rows keep the order the worker pool produced (22 of the 30
# same-second groups are two dumps on one token). Re-run with same-second rows ordered by slot (the physical order) and with a
# slot clock (212 ms per slot) for the busy windows; then a token-level bootstrap of the wider-only picks on their own.
import random
print("\nrobustness, rule totals as A and B / C / D minus A: [same-second rows ordered by slot] | [slot clock, 212 ms per slot]")
by_slot = sorted(rows, key=lambda o: (o["t"], o["s"]))
S0, TB = min(o["s"] for o in rows), min(o["t"] for o in rows)
clock = [dict(o, t=TB + (o["s"] - S0) * 0.212) for o in sorted(rows, key=lambda o: o["s"])]
for L in LATS:
    s = []
    for src in (by_slot, clock):
        R = {nm[0]: sim(rule, L, src)[0] for nm, rule in RULES.items()}
        s.append(f"A {R['A']:+.3f} B {R['B'] - R['A']:+.3f} C {R['C'] - R['A']:+.3f} D {R['D'] - R['A']:+.3f}")
    print(f"  {L:>3} ms: " + " | ".join(s))
random.seed(7)
print("wider-only picks on their own: total SOL [token-level bootstrap 90% interval, 4000 resamples]")
for L in LATS:
    s = []
    for ex in (EX, TP5):
        tok = collections.defaultdict(float)
        for o in rows:
            if not wonly(o): continue
            v = o["ours"].get(f"{L}|0.35")
            if v is None: continue
            tok[o["m"]] += -FAIL if v == "b" else v[ex] - EXTRA
        ks = list(tok); bs = sorted(sum(tok[random.choice(ks)] for _ in ks) for _ in range(4000))
        s.append(f"{'no TP' if ex == EX else 'TP +5%'} {sum(tok.values()):+.3f} [{bs[200]:+.3f}, {bs[3800]:+.3f}] on {len(ks)} tokens")
    print(f"  {L:>3} ms: " + " | ".join(s))
