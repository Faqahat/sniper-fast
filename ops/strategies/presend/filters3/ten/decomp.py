#!/usr/bin/env python3
"""TEN step 1: where today's money comes from and where it goes (DEV vs VAL). Read-only on pos.json / trig.json / hours.json."""
import json, collections, statistics as stt
D = "/home/moiz/sniper-data/filters3/ten/"
pos = json.load(open(D + "pos.json")); trig = json.load(open(D + "trig.json")); H = json.load(open(D + "hours.json"))
SEGS = ("DEV", "VAL")

def summ(v, hrs):
    if not v: return "n    0"
    s = sorted(v, reverse=True)
    return (f"n {len(v):4d} | {sum(v):+7.3f} SOL | {sum(v) / hrs * 24:+6.2f}/day | win {sum(1 for x in v if x > 0) / len(v):4.0%} | "
            f"{1000 * sum(v) / len(v):+6.1f} mSOL/tr | w/o top5 {sum(s[5:]) / hrs * 24:+6.2f}/day")

def table(title, keyf, order=None):
    print(f"\n## {title}")
    for sg in SEGS:
        g = collections.defaultdict(list)
        for p in pos:
            if p["seg"] == sg: g[keyf(p)].append(p["pnl"])
        for k in (order or sorted(g, key=str)):
            if k in g: print(f"  {sg} {str(k):>14s}  {summ(g[k], H[sg])}")

print("# DECOMPOSITION (real money = presend_live_realized; failed-try fees shown apart)")
for sg in SEGS:
    v = [p["pnl"] for p in pos if p["seg"] == sg]
    ff = sum(x["live_failfee"] for x in trig if x["seg"] == sg)  # T2 only
    ffa = sum(p["fail_fee"] for p in pos if p["seg"] == sg)
    print(f"{sg} {H[sg]:.1f} h: {summ(v, H[sg])}")
    for r in sorted({p['run'] for p in pos if p['seg'] == sg}):
        vv = [p["pnl"] for p in pos if p["seg"] == sg and p["run"] == r]
        print(f"   {r} {H[sg + ':' + r]:5.1f} h {summ(vv, H[sg + ':' + r])}")

table("kind", lambda p: p["kind"])
def band(x, cuts):
    if x is None: return "?"
    for c in cuts:
        if x < c: return f"<{c}"
    return f">={cuts[-1]}"
table("whale/dump pct of supply (T2: whale buy; rearm: dump)", lambda p: (p["kind"], band(p["trig_pct"], [7, 8, 10, 13, 20])))
table("whale buy SOL (T2)", lambda p: band(p["trig_sol"], [2, 3, 4, 6, 10]) if p["kind"] == "t2" else "rearm")
table("dip depth at fill (ann.depth)", lambda p: band(p["depth"], [0.13, 0.15, 0.18, 0.22, 0.3]))
table("token age at trigger (slots)", lambda p: band(p["age"], [3, 5, 10, 20, 50, 150]))
table("hour PKT (4 h blocks)", lambda p: f"{p['hour'] // 4 * 4:02d}-{p['hour'] // 4 * 4 + 4:02d}", [f"{h:02d}-{h + 4:02d}" for h in range(0, 24, 4)])
table("size (spend)", lambda p: round(p["spend"], 3))
table("followers: other buys within 10 slots after our buy (POST-HOC, not signing-time)", lambda p: band(p["n_fol10"], [1, 2, 4, 8]))
table("trade outcome bucket", lambda p: "win" if p["pnl"] > 0 else ("small loss" if p["pnl"] > -0.04 else "big loss <-0.04"))
table("curve vsol at trigger (SOL)", lambda p: band(p["trig_vsol"], [35, 45, 60, 90]))

# what an oracle loss-cut is worth: drop every losing trade / every big loss / every no-follower trade
print("\n## upper bounds: 'cut every loss we can identify'")
for sg in SEGS:
    v = [p["pnl"] for p in pos if p["seg"] == sg]; h = H[sg]
    wins = sum(x for x in v if x > 0); small = sum(x for x in v if -0.04 < x <= 0); big = sum(x for x in v if x <= -0.04)
    nof = sum(p["pnl"] for p in pos if p["seg"] == sg and p["n_fol10"] == 0)
    print(f"  {sg}: today {sum(v) / h * 24:+.2f}/day = wins {wins / h * 24:+.2f} + small losses {small / h * 24:+.2f} + big losses {big / h * 24:+.2f}"
          f" | no-follower trades {nof / h * 24:+.2f}/day")
    print(f"        perfect oracle (no losing trade) {wins / h * 24:+.2f}/day; cut all big losses {(sum(v) - big) / h * 24:+.2f}; cut no-follower trades {(sum(v) - nof) / h * 24:+.2f}")
    print(f"        failed-try fees (records) {sum(p['fail_fee'] for p in pos if p['seg'] == sg) / h * 24:.2f}/day on filled windows; all windows see trig.json")

# skips that would have won: shadow row c of skipped T2 triggers, calibrated per run+seg (wide_report method)
print("\n## live T2 skips scored by the shadow (row c, scaled to live size) + calibration (live - paper per shadow-filled armed window)")
gap = {}
for sg in SEGS:
    for r in sorted({x["run"] for x in trig if x["seg"] == sg}):
        pr = [(x["paper"], x["live_pnl"]) for x in trig if x["seg"] == sg and x["run"] == r and x["status"] == "armed" and x["paper"] is not None]
        g = sum(l - p for p, l in pr) / len(pr) if pr else 0.0
        allarm = [x for x in trig if x["seg"] == sg and x["run"] == r and x["status"] == "armed"]
        g2 = (sum(x["live_pnl"] for x in allarm) - sum(x["paper"] or 0 for x in allarm)) / max(1, len(pr))
        gap[(sg, r)] = g
        print(f"  {sg} {r}: {len(pr)} pairs paper {sum(p for p, _ in pr):+.3f} live {sum(l for _, l in pr):+.3f} gap {1000 * g:+.2f} mSOL/window "
              f"(all armed windows incl. live-only fills: live {sum(x['live_pnl'] for x in allarm):+.3f}, alt gap {1000 * g2:+.2f})")
json.dump({f"{a}|{b}": c for (a, b), c in gap.items()}, open(D + "gap.json", "w"))
for sg in SEGS:
    g = collections.defaultdict(list)
    for x in trig:
        if x["seg"] != sg or x["paper"] is None: continue
        g[x["status"]].append((x["paper"], x["paper"] + gap[(sg, x["run"])]))
    print(f"  {sg}:")
    for k in sorted(g, key=lambda k: -len(g[k])):
        pp = [a for a, _ in g[k]]; cc = sorted([b for _, b in g[k]], reverse=True)
        print(f"    {k:28s} shadow fills {len(pp):5d} paper {sum(pp) / H[sg] * 24:+6.2f}/day  CALIBRATED {sum(cc) / H[sg] * 24:+6.2f}/day (w/o top5 {sum(cc[5:]) / H[sg] * 24:+6.2f}) win {sum(1 for c in cc if c > 0) / len(cc):.0%}  ESTIMATE")
