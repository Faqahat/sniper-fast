# READ-ONLY aggregation of bundlestudy.py output: inside the create slot, does paying more put a REAL sniper earlier?
# Variant A: snipers = every buy not linked to the creator through Jito bundles / shared wallets.
# Variant B: A minus every cheap buyer (paid < CHEAP SOL), on the owner's read that the cheap early buys are the creator's.
# Paid = priority fee + every tip in the tx (SOL). Position = txs after the creator's glued bundle (same block).
# usage: python3 bsagg.py <bundlestudy json> [record_window dir for the sold-with-creator test] [sim_window json (1.5 SOL, fee 0)]
import sys, os, json, glob, collections, statistics as st

R = json.load(open(sys.argv[1]))
REC = sys.argv[2] if len(sys.argv) > 2 else None
SIM = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else None
CHEAP = 0.005
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"}
BUCKETS = [(0, 0.002), (0.002, 0.005), (0.005, 0.02), (0.02, 0.05), (0.05, 0.1), (0.1, 0.2), (0.2, 99)]


def q(v, p):
    v = sorted(v); return v[min(len(v) - 1, int(p * len(v)))] if v else None


def paid(r): return r["prio"] + sum(t[1] for t in r["tips"])
def path(r): return max(r["tips"], key=lambda t: t[1])[0] if r["tips"] else "prio-only"


rows = []
for L in R:
    for r in L["rows"]:
        if r["ok"] and r["buy"] and r["pos"] > 0:
            rows.append(dict(r, mint=L["mint"], S=L["S"], lc=L.get("leader_client") or "?", paid=paid(r), path=path(r), ours=bool(set(r["users"]) & OURS)))
cls = collections.Counter(r["cls"] for r in rows)
print(f"launches {len(R)}; buys in the create slot after the glued bundle: {len(rows)}  by class {dict(cls)}")
print(f"  Jito-bundled buys: {sum(1 for r in rows if r['bundle'] and r['bundle'] != 'ERR')}, Jito lookup errors: {sum(1 for r in rows if r['bundle'] == 'ERR')}")

# ---- evidence: do the cheap early buyers sell together with the creator side? (recorded launches only)
if REC:
    recs = {}
    for f in glob.glob(os.path.join(REC, "*.json")):
        if f.endswith("_index.json"): continue
        x = json.load(open(f)); recs[x["mint"]] = x
    def first_sell(x, wallets):
        s = [t["slot"] for t in x["trades"] if not t["buy"] and t["user"] in wallets]
        return min(s) if s else None
    stats = {"cheap": [], "paying": []}
    for r in rows:
        if r["cls"] != "sniper" or r["ours"] or r["mint"] not in recs: continue
        x = recs[r["mint"]]
        cs = first_sell(x, set(x.get("bundle_members") or []) | {x["creator"]})
        ws = first_sell(x, set(r["users"]))
        if cs is None or ws is None: continue
        stats["cheap" if r["paid"] < CHEAP else "paying"].append(ws - cs)
    for k, v in stats.items():
        if v: print(f"  {k:7} snipers: first sell minus creator-side first sell (slots): n {len(v)}  same slot {sum(1 for d in v if d == 0) / len(v):.0%}"
                    f"  within 1 slot {sum(1 for d in v if abs(d) <= 1) / len(v):.0%}  median {q(v, .5)}  (negative = sold before the creator)")


def report(name, keep):
    sn = [r for r in rows if keep(r)]
    print(f"\n==== {name}: {len(sn)} sniper buys")
    print("  paid SOL          n   pos p25  median  p75   in first 20   first sniper of its launch")
    firsts = {}
    for r in sorted(sn, key=lambda r: (r["mint"], r["pos"])):
        firsts.setdefault(r["mint"], r)
    for lo, hi in BUCKETS:
        b = [r for r in sn if lo <= r["paid"] < hi]
        if not b: continue
        pos = [r["pos"] for r in b]
        print(f"  {lo:.3f}-{('%.3f' % hi) if hi < 99 else '     '}  {len(b):4} {q(pos, .25):8} {q(pos, .5):7} {q(pos, .75):5} {sum(1 for p in pos if p <= 20) / len(b):11.0%}"
              f" {sum(1 for r in b if firsts[r['mint']] is r) / len(b):14.0%}")
    j = [r["pos"] for r in sn if r["bundle"] and r["bundle"] != "ERR"]; nj = [r["pos"] for r in sn if not r["bundle"]]
    print(f"  Jito bundle: n {len(j)} median +{q(j, .5)}   not bundled: n {len(nj)} median +{q(nj, .5)}")
    fp = [r["paid"] for r in firsts.values()]
    print(f"  FIRST sniper per launch: {len(firsts)} launches  paid p25 {q(fp, .25):.4f} median {q(fp, .5):.4f} p75 {q(fp, .75):.4f}; position median +{q([r['pos'] for r in firsts.values()], .5)}")
    by = collections.defaultdict(list)
    for r in sn: by[(r["lc"], r["path"])].append(r)
    print("  by leader client x path (n>=4): median position, median paid")
    for (lc, p), v in sorted(by.items(), key=lambda kv: (kv[0][0], -len(kv[1]))):
        if len(v) >= 4: print(f"    {lc:20} {p:12} n {len(v):3}  +{q([r['pos'] for r in v], .5):<4} paid {st.median([r['paid'] for r in v]):.4f}")
    return firsts


fa = report("A: snipers = not linked to the creator", lambda r: r["cls"] == "sniper" and not r["ours"])
fb = report(f"B: A minus cheap buyers (paid < {CHEAP})", lambda r: r["cls"] == "sniper" and not r["ours"] and r["paid"] >= CHEAP)
us = [r for r in rows if r["ours"]]
print("\nOUR buys in this set: " + ", ".join(f"+{r['pos']} paid {r['paid']:.3f}" for r in sorted(us, key=lambda r: r['pos'])))

# ---- what would being FIRST have been worth, against what the first (variant B) sniper paid
if SIM:
    pnl = {r["mint"]: r["sim"]["1.5|0"]["out"]["1"]["pnl"] for r in SIM["rows"] if "1.5|0" in r["sim"]}
    rowsS = []
    for L in R:
        m = L["mint"]
        if m not in pnl: continue
        f = fb.get(m)
        rowsS.append((m, pnl[m], f["paid"] if f else None, f["pos"] if f else None))
    print(f"\nWORTH OF FIRST PLACE (1.5 SOL, sell end of S+1, pump fees in, landing cost NOT in) on {len(rowsS)} recorded launches:")
    for lo, hi, lab in ((None, None, "no paying sniper in the create slot"), (0, 99, "contested (a paying sniper was in the create slot)")):
        v = [x for x in rowsS if (x[2] is None) == (lo is None)]
        if v: print(f"  {lab:52} n {len(v):3}  sum {sum(x[1] for x in v):+.3f}  mean {st.mean(x[1] for x in v):+.4f}  winners {sum(1 for x in v if x[1] > 0)}")
    print("  contested launches, best first: worth if first | first sniper paid | its position")
    for m, w, p, pos in sorted([x for x in rowsS if x[2] is not None], key=lambda x: -x[1])[:15]:
        print(f"    {m[:8]}  {w:+.3f}   {p:.4f}   +{pos}")
