#!/usr/bin/env python3
"""FRONT step 13 (read-only): bundle-aware front. A paying dump is 'bundle-fronted' when the dump tx pays a Jito tip and the buys at
idx+1, +2, ... are contiguous in the block (an atomic Jito bundle [sell, buy...]; 95% are astralane+jito dumps followed by CU-price-500
no-tip buys from fresh wallets). Nobody outside the bundle can land between; the reachable front = the first buyer after the run.
Re-does the cause split (T6) and the landing what-if (f11) with the reachable front. MEASURED order; values INFERRED as before.
Out: sniper-data/haqq_dissect/front/f13.txt"""
import pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
R = pickle.load(open(f"{OUT}/f8_rows.pkl", "rb")); R1 = pickle.load(open(f"{OUT}/f1.pkl", "rb")); W = pickle.load(open(f"{OUT}/f7.pkl", "rb"))
F10 = pickle.load(open(f"{OUT}/f10.pkl", "rb"))
FULL = (2, 3, 4, 5); nd = 4; out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
nb = 0
for r in R:
    r["bund"] = False; r["v2"] = r["v"]; r["ms2"] = r["f1"]["ms"] if not r.get("splus") else 1e9
    if r.get("splus") or r["i"] not in W: continue
    w = W[r["i"]]
    if not w["dump"]["jito"]: continue
    run = []; nxt = r["di"] + 1
    for a in w["after"]:
        if a["s"] != r["ds"] or a["i"] != nxt: break
        run.append(a); nxt += 1
    if not any(a["buy"] and a["ok"] for a in run) or run[0]["i"] != r["di"] + 1: continue
    r["bund"] = True; nb += 1
    last = run[-1]["i"]
    fr = R1[r["i"]]["front"]
    k = next((j for j, f in enumerate(fr) if (f["slot"], f["idx"]) > (r["ds"], last)), None)
    if k is None or fr[k].get("vpos") is None:
        r["v2"] = 0.0; r["ms2"] = 1e9
    else:
        r["v2"] = fr[k]["vpos"]; r["ms2"] = fr[k]["ms"]
P(f"# Bundle-aware front (paying set incl. our captures: {len(R):,}; bundle-fronted {nb:,} = {100*nb/len(R):.1f}%, "
  f"{100*sum(r['v'] for r in R if r['bund'])/sum(r['v'] for r in R):.1f}% of front value)")
b = [r for r in R if r["bund"]]
P(f"- reachable front value on bundle-fronted dumps: {sum(r['v2'] for r in b):+.1f} SOL vs {sum(r['v'] for r in b):+.1f} at the bundle's own first buy; "
  f"reachable front lands {np.median([r['ms2'] for r in b if r['ms2']<1e8]):.1f} ms after the dump (p50)")
P("\n## T6b. Cause split with bundles (front value SOL/day, D2..D5; bundle-fronted dumps count only their REACHABLE value, the rest is 'bundle ahead')")
cause = collections.defaultdict(float); cn = collections.Counter()
for r in R:
    if r["day"] not in FULL: continue
    st = r["st"]
    if r["bund"]:
        cause["G bundle ahead (dumper's own atomic Jito bundle; unreachable)"] += (r["v"] - r["v2"]) / nd; cn["G bundle ahead (dumper's own atomic Jito bundle; unreachable)"] += 1
    v = r["v2"]
    if st.startswith("1"): k = "A not running (no engine up)"
    elif st.startswith(("2", "3", "5")): k = "B not armed / not fired (engine threshold, gate, other skip)"
    elif st.startswith("4"): k = "C not fired: far-leader skip"
    elif st.startswith("6a"): k = "D armed, every try landed BEFORE the dump"
    elif st.startswith("6b"): k = "D2 armed, no try landed near the dump"
    elif st.startswith(("6d", "7b")): k = "E0 first after the dump but our price limit failed"
    elif st.startswith(("6c", "7 ")):
        if r["region"] != "EU": k = "E1 behind: far leader (non-EU)"
        elif F10.get(r["i"], {}).get("any"): k = "E2 behind: a pre-sender landed first"
        else: k = "E3 behind: a reactive buyer landed first (EU leader)"
    else: k = "F captured (we were first)"
    cause[k] += v / nd; cn[k] += 1
tt = sum(cause.values())
P("| cause | dumps (D2..D5) | SOL/day | share |")
P("|---|---|---|---|")
for k in sorted(cause): P(f"| {k} | {cn[k]:,} | {cause[k]:+.2f} | {100*cause[k]/tt:.1f}% |")
P(f"| total | | {tt:+.2f} | |")
# what-if with reachable front
att = [r for r in R if r["st"][0] in "678" and r["day"] in FULL]
P("\n## What-if (bundle-aware): our first landing t ms after the dump on the paying dumps we attempted; first iff the reachable front lands later")
for kind, cf, sel in (("pre-send", 2.01, lambda r: r["st"].startswith("6") or (r["st"].startswith("8") and r["ourbest"][2] == "ps")),
                      ("regular", 3.52, lambda r: r["st"].startswith("7") or (r["st"].startswith("8") and r["ourbest"][2] == "reg"))):
    g = [r for r in att if sel(r)]; days = len(set(r["day"] for r in g))
    ms = np.array([r["ms2"] for r in g]); v = np.array([r["v2"] for r in g])
    net = lambda x: 0.61 * x * 1000 - 1.17 - cf
    now = sum(net(r["v2"]) for r in g if r["st"].startswith("8")) / 1000 / days
    P(f"\n### {kind}: {len(g)} dumps over {days} days; bundle-fronted {sum(r['bund'] for r in g)}; reachable-front ms p25/p50/p75 "
      f"{np.percentile(ms[ms<1e8],25):.1f}/{np.median(ms[ms<1e8]):.1f}/{np.percentile(ms[ms<1e8],75):.1f}; captured now {now:+.2f} SOL/day (calibrated)")
    P("| our landing | first share | net SOL/day calibrated | gain vs now |")
    P("|---|---|---|---|")
    for t in (0, 5, 10, 15, 20, 30, 50):
        m = ms > t; a = sum(net(x) for x in v[m]) / 1000 / days
        P(f"| {t} ms | {100*m.mean():.0f}% | {a:+.2f} | {a-now:+.2f} |")
open(f"{OUT}/f13.txt", "w").write("\n".join(out) + "\n")
