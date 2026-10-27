#!/usr/bin/env python3
# POST-MIGRATION STUDY: descriptive statistics for the report (MEASURED from the recorded chain data).
import json, pickle, collections, sys
import numpy as np
OUT = "/home/moiz/sniper-data/strategies/postmig"
SMS = 212.0
HOURS = {"R2": 21.8, "R3": 25.0, "R4": 3.7}

def typ(t):
    if t["mayhem"]: return "mayhem"
    if t.get("age_s") is not None and t["age_s"] <= 1.0: return "instant"
    return "fast" if (t.get("age_s") or 1e9) < 300 else "slow"

def q(v, ps=(10, 25, 50, 75, 90)):
    v = [x for x in v if x is not None and np.isfinite(x)]
    return [round(float(np.percentile(v, p)), 3) for p in ps] if v else None

def main():
    allT = {}
    for run in ("R2", "R3", "R4"):
        T = [json.loads(l) for l in open(f"{OUT}/{run}_tokens.jsonl")]
        for t in T: t["typ"] = typ(t)
        allT[run] = T
    print("== graduations per run (per day)")
    for run, T in allT.items():
        c = collections.Counter(t["typ"] for t in T)
        print(f"  {run} ({HOURS[run]} h): total {len(T)} ({len(T)/HOURS[run]*24:.0f}/day)  " + "  ".join(f"{k} {v} ({v/HOURS[run]*24:.0f}/day)" for k, v in sorted(c.items())))
    T = allT["R2"] + allT["R3"]
    print("\n== price path vs the pool's open price (R2+R3; median and p10/p90), by type")
    for ty in ("instant", "fast", "slow", "mayhem"):
        S = [t for t in T if t["typ"] == ty]
        print(f"  {ty} n={len(S)}")
        for w in ("slot0", "1s", "10s", "1m", "10m", "1h"):
            print(f"     {w:5s} r={q([t.get('r_'+w) for t in S], (10, 50, 90))}  max={q([t.get('max_'+w) for t in S], (50, 90))} min={q([t.get('min_'+w) for t in S], (10, 50))}"
                  f" buys={q([t.get('nb_'+w) for t in S], (50,))} sells={q([t.get('ns_'+w) for t in S], (50,))} buySOL={q([t.get('vb_'+w) for t in S], (50, 90))} sellSOL={q([t.get('vs_'+w) for t in S], (50, 90))}"
                  f" buyers={q([t.get('ub_'+w) for t in S], (50,))}")
        print(f"     share with 1h price < 0.3x open: {np.mean([(t.get('r_1h') or 1) < 0.3 for t in S if t.get('r_1h') is not None]):.2f};"
              f" 1h max >= 2x open: {np.mean([(t.get('max_1h') or 0) >= 2 for t in S if t.get('max_1h') is not None]):.2f};"
              f" >= 5x: {np.mean([(t.get('max_1h') or 0) >= 5 for t in S if t.get('max_1h') is not None]):.2f}")
        print(f"     pre-migration: age_s {q([t.get('age_s') for t in S])} curve buyers {q([t.get('bc_buyers') for t in S])} last curve trade SOL {q([t.get('last_sol') for t in S])}"
              f" holders {q([t.get('holders_mig') for t in S])} top10 share {q([t.get('top10_mig') for t in S])} creator tokens at mig {q([t.get('creator_tok_mig') for t in S])}"
              f" first-slot buy SOL {q([t.get('fb_sol') for t in S])}")
    print("\n== organic (fast+slow) runners by hour of day (PKT): count, median 10m ratio, share with 1h max >= 2x")
    H = collections.defaultdict(list)
    for t in T:
        if t["typ"] in ("fast", "slow"): H[t["hour"]].append(t)
    for h in sorted(H):
        S = H[h]
        print(f"  {h:02d}h n={len(S):3d} r10m_med={np.median([t.get('r_10m') or 0 for t in S]):.2f} max1h>=2x={np.mean([(t.get('max_1h') or 0) >= 2 for t in S]):.2f}")
    print("\n== instant graduations by hour (PKT): count")
    Hc = collections.Counter(t["hour"] for t in T if t["typ"] == "instant")
    print("  " + " ".join(f"{h:02d}:{Hc[h]}" for h in range(24)))
    # first-slot buyers of instant graduations: operator wallets
    print("\n== instant graduations: first-slot buyer wallets (R2+R3)")
    C = collections.Counter(); SOL = collections.defaultdict(float)
    for t in T:
        if t["typ"] != "instant": continue
        for w in t.get("fb_wallets") or []: C[w] += 1
    for w, n in C.most_common(15): print(f"  {w[:12]} tokens {n}")
    # labels
    print("\n== Haiku labels of graduates (R2+R3): theme / X link")
    for ty in ("instant", "fast", "slow"):
        S = [t for t in T if t["typ"] == ty]
        th = collections.Counter(t.get("th") for t in S); xl = collections.Counter(t.get("xl") for t in S)
        print(f"  {ty}: themes {th.most_common(6)}  x {xl.most_common(4)}  copycat {np.mean([t.get('cpy') or 0 for t in S]):.2f}")
        names = collections.Counter((t.get("name") or "")[:20] for t in S)
        print(f"     common names: {names.most_common(8)}")

if __name__ == "__main__":
    main()
