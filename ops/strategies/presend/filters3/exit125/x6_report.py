#!/usr/bin/env python3
"""EXIT-125v200 step 6: tables from cf.json -> stdout + report.json.
Main table = the fills every own-lag setting covers (same fills in every row). P&L per trip = realized + ATA rent back."""
import json, collections, sys
D = "/home/it/sniper-data/filters3/exit125"
R = json.load(open(f"{D}/cf.json"))
HOURS = json.load(open(f"{D}/fills.json"))["hours"]
HOURS = {int(k): v for k, v in HOURS.items()}
T = [100, 125, 150, 200, 250, 300, 400, 600, 800, 1000, 1500, 2000]
KEYS = [f"t{t}" for t in T] + [f"s{n}" for n in range(1, 6)]
RUNS = list(range(42, 50))
P = [r for r in R if "cf" in r]
common = [r for r in P if r["run"] in RUNS and all(r["cf"].get(k) for k in KEYS)]
out = {}

def stats(rows, key, hours):
    v = [r["cf"][key]["pnl"] if not key.endswith("_rs") else r["cf"][key]["pnl"] for r in rows if r["cf"].get(key)]
    if not v: return None
    s = sorted(v)
    w125 = sum(1 for r in rows if r["cf"].get(key) and r["cf"][key]["pnl"] > r["cf"]["t125"]["pnl"] + 1e-6)
    l125 = sum(1 for r in rows if r["cf"].get(key) and r["cf"][key]["pnl"] < r["cf"]["t125"]["pnl"] - 1e-6)
    w200 = sum(1 for r in rows if r["cf"].get(key) and r["cf"][key]["pnl"] > r["cf"]["t200"]["pnl"] + 1e-6)
    l200 = sum(1 for r in rows if r["cf"].get(key) and r["cf"][key]["pnl"] < r["cf"]["t200"]["pnl"] - 1e-6)
    return dict(n=len(v), sol=sum(v), day=sum(v) / hours * 24 if hours else None, win=sum(1 for a in v if a > 0) / len(v) * 100,
                no5=sum(s[:-5]) if len(s) > 5 else None, w125=w125, l125=l125, w200=w200, l200=l200)

def table(rows, hours, title, keys):
    print(f"\n== {title}  (fills {len(rows)}, {hours:.1f} h)")
    print(f"{'exit':>9} {'n':>5} {'SOL':>8} {'SOL/day':>8} {'win%':>5} {'w/o top5':>8} {'vs125 +/-':>10} {'vs200 +/-':>10}")
    res = {}
    for k in keys:
        st = stats(rows, k, hours)
        if not st: continue
        res[k] = st
        print(f"{k:>9} {st['n']:>5} {st['sol']:>+8.3f} {st['day']:>+8.2f} {st['win']:>5.1f} {(st['no5'] if st['no5'] is not None else float('nan')):>+8.3f} {st['w125']:>4}/{st['l125']:<5} {st['w200']:>4}/{st['l200']:<5}")
    return res

# coverage
print("COVERAGE (fills priced per setting, own lag; 'raw' = fills whose tape was extended with the raw collector):")
cov = {}
for run in RUNS + [50]:
    rr = [r for r in R if r["run"] == run]
    pr = [r for r in rr if "cf" in r]
    c = {k: sum(1 for r in pr if r["cf"].get(k)) for k in KEYS}
    c_rs = {k: sum(1 for r in pr if r["cf"].get(k + "_rs")) for k in KEYS}
    cov[run] = dict(fills=len(rr), tape=len(pr), raw=sum(1 for r in pr if r.get("raw_ext")), own=c, rs=c_rs)
    short = {k: v for k, v in c.items() if v < len(pr)}
    print(f" r{run}: fills {len(rr)} tape {len(pr)} raw-extended {cov[run]['raw']} | short of full: {short or 'none'} | rs short: { {k: v for k, v in c_rs.items() if v < len(pr)} or 'none'}")
out["coverage"] = cov
print(f"common set (all {len(KEYS)} settings priced): {len(common)} of {len(P)}")

H = sum(HOURS[r] for r in RUNS)
out["total"] = table(common, H, "ALL RUNS r42-r49, own lag", KEYS)
out["total_rs"] = table(common, H, "ALL RUNS, resampled lag (25 draws of the run's own timer-delay+lag)", [k + "_rs" for k in KEYS])
out["total_fc20"] = table(common, H, "ALL RUNS, followers -20% (stress), own lag", [k + "_fc20" for k in KEYS])
# real realized for reference
print(f"\nreal realized on the common set: {sum(r['real'] for r in common):+.3f} SOL over {len(common)} fills")
out["per_run"] = {}
for run in RUNS:
    rows = [r for r in common if r["run"] == run]
    if not rows: continue
    out["per_run"][run] = table(rows, HOURS[run], f"r{run} (real timer {rows[0]['timer']} ms, real {sum(r['real'] for r in rows):+.3f})", KEYS)
# per run compact: 125 vs 200 vs best
print("\nPER RUN 125 vs 200 (own lag / resampled) and best setting:")
for run in RUNS:
    rows = [r for r in common if r["run"] == run]
    if not rows: continue
    a = sum(r["cf"]["t125"]["pnl"] for r in rows); b = sum(r["cf"]["t200"]["pnl"] for r in rows)
    ars = sum(r["cf"]["t125_rs"]["pnl"] for r in rows if r["cf"].get("t125_rs")); brs = sum(r["cf"]["t200_rs"]["pnl"] for r in rows if r["cf"].get("t200_rs"))
    best = max(KEYS, key=lambda k: sum(r["cf"][k]["pnl"] for r in rows))
    print(f" r{run} timer{rows[0]['timer']} n{len(rows)}: 125 {a:+.3f} | 200 {b:+.3f} | diff200-125 {b - a:+.3f} | rs 125 {ars:+.3f} 200 {brs:+.3f} | best {best} {sum(r['cf'][best]['pnl'] for r in rows):+.3f}")
# splits
def split(name, f):
    print(f"\nSPLIT {name}:")
    res = {}
    for lab in sorted({f(r) for r in common}):
        rows = [r for r in common if f(r) == lab]
        a = sum(r["cf"]["t125"]["pnl"] for r in rows); b = sum(r["cf"]["t200"]["pnl"] for r in rows)
        w = sum(1 for r in rows if r["cf"]["t125"]["pnl"] > r["cf"]["t200"]["pnl"] + 1e-6); l = sum(1 for r in rows if r["cf"]["t125"]["pnl"] < r["cf"]["t200"]["pnl"] - 1e-6)
        extra = {k: round(sum(r["cf"][k]["pnl"] for r in rows), 3) for k in ("t100", "t150", "t250", "t300", "t400", "s1", "s2")}
        print(f"  {lab}: n {len(rows)} | 125 {a:+.3f} | 200 {b:+.3f} | 125 better {w}, 200 better {l} | {extra}")
        res[str(lab)] = dict(n=len(rows), t125=a, t200=b, w125=w, w200=l, **extra)
    out["split_" + name] = res
split("kind", lambda r: r["kind"])
split("big_holder_sell_between_our_125_and_200_landings", lambda r: "yes" if r["big_sell_125_200"] else "no")
split("real_timer", lambda r: r["timer"])
# r50 (partial, tapes from the run jsonl, covered only to each tape's last row)
r50 = [r for r in P if r["run"] == 50]
if r50:
    print("\nr50 (partial local copy, 200 ms real; jsonl tapes): per fill 125 vs 200 (None = past its tape)")
    for r in r50:
        a, b = r["cf"].get("t125"), r["cf"].get("t200")
        bs = "; ".join(f"{z['w']} sold {z['pct']:.1f}% ({z['sol']:.2f}) at +{z['ms']:.0f} ms" for z in r["big_sell_125_200"]) or "-"
        print(f"  {r['mint'][:8]} real {r['real']:+.4f} | 125 {a['pnl'] if a else None:+.4f} land +{a['land'] if a else 0:.0f} | 200 {b['pnl'] if b else 0:+.4f} | {bs}")
    ok = [r for r in r50 if r["cf"].get("t125") and r["cf"].get("t200")]
    print(f"  r50 sum over {len(ok)}: 125 {sum(r['cf']['t125']['pnl'] for r in ok):+.4f}  200 {sum(r['cf']['t200']['pnl'] for r in ok):+.4f}  real {sum(r['real'] for r in ok):+.4f}")
# biggest differences
d = sorted(common, key=lambda r: r["cf"]["t200"]["pnl"] - r["cf"]["t125"]["pnl"])
def show(r):
    a, b = r["cf"]["t125"], r["cf"]["t200"]
    bs = "; ".join(f"{z['w']} sold {z['pct']:.1f}% ({z['sol']:.2f} SOL) at +{z['ms']:.0f} ms" for z in r["big_sell_125_200"]) or "-"
    return (f"  r{r['run']} {r['kind']} {r['mint'][:8]} real {r['real']:+.3f} (timer {r['timer']}) | 125: {a['pnl']:+.3f} land +{a['land']:.0f} ms ({a['why']}) | "
            f"200: {b['pnl']:+.3f} land +{b['land']:.0f} ms ({b['why']}) | diff {b['pnl'] - a['pnl']:+.3f} | big sells in between: {bs}\n"
            f"     https://gmgn.ai/sol/token/{r['mint']}")
print("\nTOP 5 where 125 beat 200:"); [print(show(r)) for r in d[:5]]
print("TOP 5 where 200 beat 125:"); [print(show(r)) for r in d[::-1][:5]]
out["top125"] = [dict(run=r["run"], mint=r["mint"], d=r["cf"]["t200"]["pnl"] - r["cf"]["t125"]["pnl"]) for r in d[:5]]
out["top200"] = [dict(run=r["run"], mint=r["mint"], d=r["cf"]["t200"]["pnl"] - r["cf"]["t125"]["pnl"]) for r in d[::-1][:5]]
json.dump(out, open(f"{D}/report.json", "w"), indent=1)
