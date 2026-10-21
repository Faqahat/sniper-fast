# READ-ONLY (host): tables for FILTERS.md from filters.py's <prefix>_rows.json (one row per watched launch, already priced
# on the landing model). Every variant is shown per period group: A = in-sample (evening), B / C = out-of-sample.
# usage: python3 report.py <prefix>_rows.json > tables.md
import sys, json, statistics, collections

D = json.load(open(sys.argv[1])); R = D["rows"]; H = D["hours"]


def stats(rs, g):
    rs = [r for r in rs if r["grp"] == g]
    n = len(rs); h = H[g] or 1
    if not n: return dict(n=0, ph=0.0)
    fil = [r for r in rs if not r["refused"]]
    p2 = [r["p2"] for r in rs]
    return dict(n=n, ph=n / h, fil=len(fil), ref=n - len(fil), t2=sum(p2), t1=sum(r["p1"] for r in rs), m2=sum(p2) / n,
                med=statistics.median(p2), win=sum(1 for x in p2 if x > 0) / n, worst=min(p2), tp2=sum(r["pp2"] for r in rs),
                ph2=sum(p2) / h, ts=sum(r["s2"] for r in rs), x3=sum(sorted(p2, reverse=True)[3:]))


def fmt(s):
    if not s["n"]: return "| 0 | - | - | - | - | - | - | - | - | - | - | - |"
    return (f"| {s['n']} | {s['ph']:.1f} | {s['fil']}/{s['ref']} | {s['t2']:+.2f} | {s['m2']:+.3f} | {s['med']:+.3f} | {100 * s['win']:.0f}% "
            f"| {s['worst']:+.2f} | {s['t1']:+.2f} | {s['tp2']:+.2f} | {s['ph2']:+.2f} | {s['x3']:+.2f} |")


HDR = ("| variant | grp | n | /h | fill/ref | PnL S+2 | per launch | median | win | worst | PnL S+1 | +20 ms S+2 | SOL/h S+2 | S+2 w/o best 3 |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def table(title, variants, groups=("A", "B", "C"), note=None):
    print(f"\n### {title}\n")
    if note: print(note + "\n")
    print(HDR)
    for name, sel in variants:
        rs = [r for r in R if sel(r)]
        for g in groups:
            print(f"| {name if g == groups[0] else ''} | {g} " + fmt(stats(rs, g)))


lun = lambda r: r["tipc"] == "lunar"
early = lambda r: r["create_ms"] is not None and r["create_ms"] <= 150
b35 = lambda r: 3 <= r["gsol"] <= 5
R2 = lambda r: lun(r) and b35(r) and early(r)

if "--overview" in sys.argv:
    print("| group | hours | watched launches | /h | rule #2 (on-chain reconstruction) | /h | engine FIRE lines |\n|---|---|---|---|---|---|---|")
    for g in "ABC":
        rs = [r for r in R if r["grp"] == g]
        print(f"| {g} | {H[g]:.2f} | {len(rs)} | {len(rs) / H[g]:.0f} | {sum(1 for r in rs if R2(r))} | {sum(1 for r in rs if R2(r)) / H[g]:.1f} | {sum(1 for r in rs if r['fired'])} |")
    sys.exit(0)

_table = table


def table(*a, **k):
    if "--combos" not in sys.argv: _table(*a, **k)


table("Rule #2 and the engine's own fires", [
    ("rule #2 (on-chain: Lunar largest, glued 3-5, create <=150)", R2),
    ("engine FIRED (FIRE line)", lambda r: r["fired"]),
])

BUCKETS = [("none (dev buy only)", lambda r: r["glued"] == 0), ("1-wallet bundle (any SOL)", lambda r: r["glued"] > 0 and r["bwal"] == 1),
           ("multi-wallet bundle", lambda r: r["glued"] > 0 and (r["bwal"] or 0) >= 2),
           ("0-1 SOL", lambda r: r["glued"] > 0 and r["gsol"] < 1), ("1-2", lambda r: 1 <= r["gsol"] < 2), ("2-3", lambda r: 2 <= r["gsol"] < 3),
           ("3-5 (rule #2)", lambda r: 3 <= r["gsol"] <= 5), ("5-8", lambda r: 5 < r["gsol"] <= 8), ("8+", lambda r: r["gsol"] > 8)]
table("1. Bundle size (Lunar largest + create <=150 ms held fixed)", [(n, (lambda f: lambda r: lun(r) and early(r) and f(r))(f)) for n, f in BUCKETS])
LEGS = [("0 legs", lambda r: r["glued"] == 0), ("1 leg", lambda r: r["glued"] == 1), ("2 legs", lambda r: r["glued"] == 2),
        ("3 legs", lambda r: r["glued"] == 3), ("4+ legs", lambda r: r["glued"] >= 4)]
table("1b. Bundle leg count (glued txs; Lunar + create <=150 held fixed)", [(n, (lambda f: lambda r: lun(r) and early(r) and f(r))(f)) for n, f in LEGS])
table("1c. 1-wallet bundle 3-5 SOL vs multi-wallet 3-5 SOL (rule #2 otherwise)", [
    ("rule #2, 1-wallet bundle", lambda r: R2(r) and r["bwal"] == 1), ("rule #2, 2+ wallets", lambda r: R2(r) and (r["bwal"] or 0) >= 2)])
table("1d. Bundle size with ANY create tip (create <=150 held fixed)", [(n, (lambda f: lambda r: early(r) and f(r))(f)) for n, f in BUCKETS])

TIPS = ["lunar", "jito", "nozomi", "other tip svc", "fee/other addr", "none"]
table("2. Largest create transfer (bundle 3-5 + create <=150 held fixed)", [(t, (lambda t: lambda r: r["tipc"] == t and b35(r) and early(r))(t)) for t in TIPS])
table("2b. Largest create transfer, no bundle (dev buy only; create <=150)", [(t, (lambda t: lambda r: r["tipc"] == t and r["glued"] == 0 and early(r))(t)) for t in TIPS])
table("2c. Largest create transfer, any bundle (create <=150)", [(t, (lambda t: lambda r: r["tipc"] == t and early(r))(t)) for t in TIPS])

DEVS = [("0.5-1", 0.5, 1), ("1-2", 1, 2), ("2-3", 2, 3), ("3-5", 3, 5), ("5-8", 5, 8.01)]
table("3. Dev buy (rule #2 otherwise)", [(n, (lambda lo, hi: lambda r: R2(r) and lo <= r["dev"] < hi)(lo, hi)) for n, lo, hi in DEVS])
table("3b. Dev buy, no bundle (Lunar + create <=150)", [(n, (lambda lo, hi: lambda r: lun(r) and early(r) and r["glued"] == 0 and lo <= r["dev"] < hi)(lo, hi)) for n, lo, hi in DEVS])

HOSTS = ["j7tracker", "ipfs.io", "uxento", "pinata", "other"]
table("4. Metadata host (rule #2 otherwise)", [(h, (lambda h: lambda r: R2(r) and r["host"] == h)(h)) for h in HOSTS])
table("4b. Metadata host (Lunar + create <=150, any bundle)", [(h, (lambda h: lambda r: lun(r) and early(r) and r["host"] == h)(h)) for h in HOSTS])
table("4c. Other create fields (rule #2 otherwise)", [
    ("cu_price = 0", lambda r: R2(r) and not r["cu_price"]), ("cu_price > 0", lambda r: R2(r) and bool(r["cu_price"])),
    ("no lookup table", lambda r: R2(r) and not r["luts"]), ("lookup table", lambda r: R2(r) and bool(r["luts"])),
    ("dev buy kind 1 (exact SOL)", lambda r: R2(r) and r["kind"] == 1), ("dev buy kind 2 (cap)", lambda r: R2(r) and r["kind"] == 2)])

CMS = [("0-50", 0, 50), ("50-100", 50, 100), ("100-150 (rule #2 edge)", 100, 150.0001), ("150-217 (late)", 150.0001, 999)]
table("5. Create time in slot (Lunar + bundle 3-5 held fixed)", [(n, (lambda lo, hi: lambda r: lun(r) and b35(r) and r["create_ms"] is not None and lo <= r["create_ms"] < hi)(lo, hi)) for n, lo, hi in CMS])
table("5b. Leader class (rule #2 otherwise)", [(c, (lambda c: lambda r: R2(r) and r["cls"] == c)(c)) for c in ("bam", "jito", "harmonic", "other")])
table("5c. Leader class, ALL watched launches (no create filter)", [(c, (lambda c: lambda r: r["cls"] == c)(c)) for c in ("bam", "jito", "harmonic", "other")])
table("All watched launches (base filter + close leader only)", [("all", lambda r: True), ("create <=150", early)])


def bylog(title, variants):
    """per log (period) totals: n, S+2 PnL, +20 ms S+2"""
    logs = [l for g in ("A", "B", "C") for l in D["groups"][g]]
    print(f"\n### {title}\n")
    print("| variant | " + " | ".join(logs) + " |\n|---|" + "---|" * len(logs))
    for name, sel in variants:
        cells = []
        for l in logs:
            rs = [r for r in R if r["log"] == l and sel(r)]
            cells.append(f"{len(rs)}: {sum(r['p2'] for r in rs):+.2f}" if rs else "0")
        print(f"| {name} | " + " | ".join(cells) + " |")


if "--combos" in sys.argv:
    harm_nb = lambda r: early(r) and r["glued"] == 0 and r["cls"] == "harmonic"
    COMBOS = [
        ("rule #2", R2),
        ("C1 rule #2 + Lunar no-bundle", lambda r: R2(r) or (lun(r) and early(r) and r["glued"] == 0)),
        ("C2 Lunar, bundle 0-5 (incl. none)", lambda r: lun(r) and early(r) and r["gsol"] <= 5),
        ("C3 Lunar, bundle 2-5", lambda r: lun(r) and early(r) and 2 <= r["gsol"] <= 5),
        ("C4 Lunar, bundle 3-8", lambda r: lun(r) and early(r) and 3 <= r["gsol"] <= 8),
        ("C5 any tip, bundle 3-5", lambda r: early(r) and b35(r)),
        ("C6 any tip, bundle 2-5", lambda r: early(r) and 2 <= r["gsol"] <= 5),
        ("C7 no bundle, Harmonic leader, any tip", harm_nb),
        ("C8 rule #2 + C7", lambda r: R2(r) or harm_nb(r)),
        ("C9 rule #2 without the 150 ms gate", lambda r: lun(r) and b35(r)),
    ]
    _table("Combinations", COMBOS)
    _table("Added launches only (combination minus rule #2)", [(n + " minus rule #2", (lambda f: lambda r: f(r) and not R2(r))(f)) for n, f in COMBOS[1:]])
    bylog("Combinations per log (n: PnL S+2 SOL)", COMBOS)
    import random
    random.seed(7)
    print("\n### Per-launch S+2 PnL, mean with a bootstrap 90% interval (2000 resamples)\n")
    print("| variant | A | B | C | B+C |\n|---|---|---|---|---|")
    for n, f in COMBOS + [(n + " minus rule #2", (lambda f: lambda r: f(r) and not R2(r))(f)) for n, f in COMBOS[1:]]:
        cells = []
        for gs in (("A",), ("B",), ("C",), ("B", "C")):
            v = [r["p2"] for r in R if r["grp"] in gs and f(r)]
            if len(v) < 2: cells.append(f"n={len(v)}"); continue
            ms = sorted(sum(random.choice(v) for _ in v) / len(v) for _ in range(2000))
            cells.append(f"{sum(v) / len(v):+.3f} [{ms[100]:+.3f}, {ms[1899]:+.3f}] n={len(v)}")
        print(f"| {n} | " + " | ".join(cells) + " |")
