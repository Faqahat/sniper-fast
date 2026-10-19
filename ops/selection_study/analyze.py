#!/usr/bin/env python3
"""Decompose the 28%->~80% selection gap.
Anchors + slot-0 feature lifts on the labeled unbiased population + enrichment in his attempted set,
+ attempted-vs-landed (fill survivorship) test + OOS rule fit."""
import json, bisect, statistics as st

POP = json.load(open("/root/selection_study/pop_labeled.json"))
HL = [r for r in json.load(open("/root/selection_study/his_landed_labeled.json")) if r.get("ok")]
NL = [r for r in json.load(open("/root/selection_study/neverland_labeled.json")) if r.get("ok")]
ATT = HL + NL  # his attempted (landed + never-landed)


def wr(sub):
    n = len(sub)
    if not n:
        return (0, 0.0, 0.0, 0.0)
    w = sum(1 for r in sub if r["win"]) / n
    m = sum(r["net"] for r in sub) / n
    med = st.median([r["net"] for r in sub])
    return (n, w, m, med)


def unbounded(r):
    return r.get("dev_buy_wire", 0) >= 1e17


def vanilla(r):
    return not (r.get("mayhem") or r.get("holder_reward") or r.get("cashback"))


def passes_filter(r):
    # our live filter: creator_fee_bps==0 AND dev_buy>=0.3 (unbounded passes)
    if r.get("creator_fee_bps", 0) != 0:
        return False
    dev = r["dev_buy"]
    if unbounded(r):
        dev = max(dev, 0.3)
    return dev >= 0.3


print("=" * 90)
print("PART 0 - ANCHORS (identical label: net R>0 under baseline ladder, create-slot-floor anchored)")
print("=" * 90)
for name, s in [("unbiased pop (full)", POP),
                ("unbiased pop, OUR filter passes", [r for r in POP if passes_filter(r)]),
                ("HIS landed picks", HL),
                ("HIS never-landed attempts", NL),
                ("HIS attempted (landed+failed)", ATT)]:
    n, w, m, med = wr(s)
    print("  %-34s n=%4d  flip-win=%5.1f%%  meanR=%+.4f  medR=%+.4f" % (name, n, w * 100, m, med))

print()
print("=" * 90)
print("PART 2 - FILL SURVIVORSHIP TEST: does LANDING raise win rate vs merely ATTEMPTING?")
print("=" * 90)
nL, wL = wr(HL)[:2]
nN, wN = wr(NL)[:2]
print("  landed      flip-win %.1f%% (n=%d)" % (wL * 100, nL))
print("  never-land  flip-win %.1f%% (n=%d)" % (wN * 100, nN))
print("  delta (landed - attempted-but-failed) = %+.1f pts" % ((wL - wN) * 100))
print("  => if ~0, his win rate is NOT post-selected by what filled; it is pre-selection of WHICH")
print("     mints he targets. If landed>>never, edge is fill-timing (not filter-fixable).")

base_n, base_w, base_m, _ = wr(POP)
passP = [r for r in POP if passes_filter(r)]
pn, pw, pm, _ = wr(passP)
print()
print("=" * 90)
print("PART 1 - SLOT-0 FEATURE LIFTS on unbiased population  (base full-pop win %.1f%%)" % (base_w * 100))
print("         HISshare = fraction of his ATTEMPTED picks (n=%d) in that bucket" % len(ATT))
print("=" * 90)


def feat(name, buckets, his=True):
    print("\n## %s" % name)
    print("  %-26s | %5s %7s %9s %6s | %-12s %-12s" % ("bucket", "n", "POPwin%", "meanR", "lift", "HIS-in-bucket", "HISshare"))
    for lab, fn in buckets:
        sub = [r for r in POP if safe(fn, r)]
        n, w, m, _ = wr(sub)
        if his:
            hsub = [r for r in ATT if safe(fn, r)]
            hn = len(hsub)
            hw = (sum(1 for r in hsub if r["win"]) / hn * 100) if hn else 0.0
            hisw = "win=%.0f%%(n=%d)" % (hw, hn)
            hs = "%.0f%%" % (hn / len(ATT) * 100)
        else:
            hisw = "n/a"; hs = "n/a"
        print("  %-26s | %5d %6.1f%% %+9.4f %+6.1f | %-12s %-12s" % (lab, n, w * 100, m, (w - base_w) * 100, hisw, hs))


def safe(fn, r):
    try:
        return fn(r)
    except KeyError:
        return False


feat("dev_buy size (curve truth SOL)", [
    ("<0.3", lambda r: r["dev_buy"] < 0.3),
    ("0.3-0.5", lambda r: 0.3 <= r["dev_buy"] < 0.5),
    ("0.5-1.0", lambda r: 0.5 <= r["dev_buy"] < 1.0),
    ("1.0-2.0", lambda r: 1.0 <= r["dev_buy"] < 2.0),
    ("2.0-5.0", lambda r: 2.0 <= r["dev_buy"] < 5.0),
    (">=5.0", lambda r: r["dev_buy"] >= 5.0),
])
feat("dev_buy sized vs unbounded cap", [
    ("sized (finite)", lambda r: not unbounded(r)),
    ("unbounded (u64MAX)", unbounded),
])
feat("vanilla", [("vanilla", vanilla), ("non-vanilla", lambda r: not vanilla(r))])
feat("same-create-slot co-snipers (slot-0-ish)", [
    ("0", lambda r: r["cosnipers"] == 0),
    ("1", lambda r: r["cosnipers"] == 1),
    ("2", lambda r: r["cosnipers"] == 2),
    (">=3", lambda r: r["cosnipers"] >= 3),
    (">=1 (any)", lambda r: r["cosnipers"] >= 1),
])
feat("creator in-window launch freq", [
    ("1 fresh", lambda r: r["rep"] == 1),
    ("2", lambda r: r["rep"] == 2),
    (">=3 factory", lambda r: r["rep"] >= 3),
], his=False)

# creator prior in-window launch outcome (ordered by slot)
POPs = sorted(POP, key=lambda r: r["create_slot"])
seen = {}
for r in POPs:
    pri = seen.get(r["creator"], [])
    r["_prior_n"] = len(pri)
    r["_prior_spike"] = any(p >= 1.5 for p in pri)
    seen.setdefault(r["creator"], []).append(r["peak"])
feat("creator prior in-window launch", [
    ("no prior (first)", lambda r: r.get("_prior_n", 0) == 0),
    ("has prior", lambda r: r.get("_prior_n", 0) >= 1),
    ("prior spiked >=1.5x", lambda r: r.get("_prior_spike", False)),
], his=False)

# congestion
slots = sorted(r["create_slot"] for r in POP)
for r in POP:
    s = r["create_slot"]
    r["_dens"] = bisect.bisect_right(slots, s + 10) - bisect.bisect_left(slots, s - 10)
dv = sorted(r["_dens"] for r in POP)
med = dv[len(dv) // 2]
feat("launch congestion +-10 slots (med=%d)" % med, [
    ("low <=med", lambda r: r["_dens"] <= med),
    ("high >med", lambda r: r["_dens"] > med),
], his=False)

# OUTCOME (not slot-0) diagnostics - how much follow-on these got
feat("[OUTCOME] post-create trade count", [
    ("0 (dead-on-arrival)", lambda r: r["n_trades"] == 0),
    ("1-4", lambda r: 1 <= r["n_trades"] <= 4),
    (">=5", lambda r: r["n_trades"] >= 5),
    (">=10", lambda r: r["n_trades"] >= 10),
])

# His attempted picks' own feature distributions vs population (enrichment summary)
print()
print("=" * 90)
print("HIS ATTEMPTED vs POP: feature distribution (median / share)")
print("=" * 90)


def summ(label, s):
    dev = sorted(r["dev_buy"] for r in s)
    co = sorted(r["cosnipers"] for r in s)
    nt = sorted(r["n_trades"] for r in s)
    van = sum(1 for r in s if vanilla(r)) / len(s)
    doa = sum(1 for r in s if r["n_trades"] == 0) / len(s)
    print("  %-22s dev_med=%.2f  cosnip_med=%d  cosnip_p75=%d  ntrades_med=%d  van=%.0f%%  DOA=%.0f%%" % (
        label, dev[len(dev) // 2], co[len(co) // 2], co[int(len(co) * .75)], nt[len(nt) // 2], van * 100, doa * 100))


summ("POP (all)", POP)
summ("POP filter-pass", passP)
summ("HIS attempted", ATT)

# ---- OOS rule fit: can a slot-0 rule move pop win 28% -> higher? ----
print()
print("=" * 90)
print("OOS RULE FIT - time-split train/val on population; test slot-0 rules")
print("=" * 90)
POPt = sorted(POP, key=lambda r: r["create_slot"])
cut = int(len(POPt) * 0.70)
TR, VA = POPt[:cut], POPt[cut:]


def rule_eval(name, fn):
    for lab, S in [("TRAIN", TR), ("VAL", VA)]:
        sub = [r for r in S if fn(r)]
        n, w, m, med = wr(sub)
        print("  %-42s %-5s n=%4d win=%5.1f%% meanR=%+.4f medR=%+.4f" % (name, lab, n, w * 100, m, med))


rule_eval("baseline filter (fee0 & dev>=0.3)", passes_filter)
rule_eval("filter + vanilla", lambda r: passes_filter(r) and vanilla(r))
rule_eval("filter + cosnipers>=1", lambda r: passes_filter(r) and r["cosnipers"] >= 1)
rule_eval("filter + cosnipers>=2", lambda r: passes_filter(r) and r["cosnipers"] >= 2)
rule_eval("filter + vanilla + cosnipers>=1", lambda r: passes_filter(r) and vanilla(r) and r["cosnipers"] >= 1)
rule_eval("filter + vanilla + cosnipers>=2", lambda r: passes_filter(r) and vanilla(r) and r["cosnipers"] >= 2)
rule_eval("cosnipers>=2 only", lambda r: r["cosnipers"] >= 2)
rule_eval("cosnipers>=3 only", lambda r: r["cosnipers"] >= 3)
