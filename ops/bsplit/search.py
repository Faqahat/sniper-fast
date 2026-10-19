# Systematic search for a POSITIVE strategy at OUR realistic landing, blacklist paper data only.
# Train = night (300). Tests = bl82 (Oct 17) and fwd (Oct 18 forward). A config counts only if positive on BOTH tests,
# also with the top 3 removed. Entry modes:
#   IMM   : right behind the bundle x 1.06 (where we land today)
#   WAITk : observe for k ms; gate on the move since t0; buy at the price ~400 ms later x 1.02 (no create race)
# Costs: own impact on buy and sell (constant product), pump fee 1.25%/side, 0.0003 SOL per tx.
import json, itertools, statistics as st, sys
K = 30.0 * 1.073e9
F = 0.0125
SIZE, PRIO = 1.0, 0.0003
SETS = [("bl82", "/root/bsplit/out_bl82.jsonl", "/root/arbx-fast/paths_blacklist.jsonl"),
        ("night", "/root/bsplit/out.jsonl", "/root/arbx-fast/paths_blnight.jsonl"),
        ("fwd", "/root/bsplit/out_fwd.jsonl", "/root/arbx-fast/paths_blfwd.jsonl")]
D = []
for name, bf, pf in SETS:
    B = {}
    for l in open(bf):
        try:
            r = json.loads(l)
        except Exception:
            continue
        if "glued" in r:
            B[r["mint"]] = r
    for l in open(pf):
        try:
            d = json.loads(l)
        except Exception:
            continue
        if d["mint"] in B and len(d["path"]) > 5:
            r = dict(B[d["mint"]]); r["path"] = d["path"]; r["set"] = name
            D.append(r)
print({s: sum(r["set"] == s for r in D) for s, _, _ in SETS})


def sim(r, start_i, E, tp, tr, sl, T):
    """buy at relative-floor price E at path index start_i; exit rule; returns pnl fraction"""
    vq0 = 30.0 + r["dev"] / 1e9
    vqe = vq0 * E ** 0.5
    s_in = SIZE * (1 - F)
    tok = K / vqe - K / (vqe + s_in)
    path = r["path"]
    t0 = path[start_i][0]
    peak = 0.0
    X = path[start_i][1]
    for t, X in path[start_i:]:
        rr = X / E
        peak = max(peak, rr)
        if (t - t0) >= T or (tp and rr >= tp) or (sl and rr <= sl) or (tr and peak >= 1.08 and rr <= peak * tr):
            break
    vq = vq0 * max(X, E * 0.05) ** 0.5 + s_in
    out = (vq - K / (K / vq + tok)) * (1 - F)
    return (out - SIZE - 2 * PRIO) / SIZE


def idx_at(path, t):
    for i, (tt, _) in enumerate(path):
        if tt >= t:
            return i
    return None


ENTRIES = [("IMM", None, None)]
for k, g in itertools.product([1000, 2000, 4000], [("up>=1.0", 1.0, 9), ("up>=1.1", 1.1, 9), ("up>=1.3", 1.3, 9), ("dip<=0.9", 0, 0.9)]):
    ENTRIES.append((f"WAIT{k//1000}s {g[0]}", k, g))
EXITS = list(itertools.product([None, 1.1, 1.2, 1.5, 2.0], [None, 0.85, 0.75], [None, 0.85, 0.7], [5000, 15000, 10**9]))


def entry_of(r, mode):
    name, k, g = mode
    if k is None:
        return 0, max(1.0, r["bmult"]) * 1.06
    i = idx_at(r["path"], k)
    j = idx_at(r["path"], k + 400)
    if i is None or j is None or j >= len(r["path"]) - 3:
        return None
    p0 = r["path"][0][1]
    mv = r["path"][i][1] / p0
    if not (g[1] <= mv <= g[2]):
        return None
    return j, r["path"][j][1] * 1.02


# precompute pnl[entry][exit][trade]
PN = {}
for ei, em in enumerate(ENTRIES):
    ent = [entry_of(r, em) for r in D]
    for xi, ex in enumerate(EXITS):
        PN[(ei, xi)] = [None if e is None else sim(r, e[0], e[1], *ex) for r, e in zip(D, ent)]
print("precomputed", len(PN), "entry x exit combos", flush=True)


def dband(r):
    s = r["dev"] / 1e9
    return 0 if s < 1 else 1 if s < 3 else 2


FILTERS = {}
for dv, bb, ct in itertools.product(["any", "dev<1", "dev1-3", "dev>=3"], ["any", "nob", "bundled", "b<3", "b>=3"], ["any", "tip", "notip"]):
    def f(r, dv=dv, bb=bb, ct=ct):
        if dv != "any" and dband(r) != ["dev<1", "dev1-3", "dev>=3"].index(dv):
            return False
        g = r["gsol"] if r["glued"] else 0
        if bb == "nob" and g > 0: return False
        if bb == "bundled" and g == 0: return False
        if bb == "b<3" and not (0 < g < 3): return False
        if bb == "b>=3" and g < 3: return False
        if ct == "tip" and not r.get("creator_tip"): return False
        if ct == "notip" and r.get("creator_tip"): return False
        return True
    FILTERS[f"{dv}/{bb}/{ct}"] = f
FM = {fn: [f(r) for r in D] for fn, f in FILTERS.items()}
SETI = {s: [r["set"] == s for r in D] for s in ("night", "bl82", "fwd")}


def stats(v):
    if len(v) < 1:
        return None
    ex = sorted(v)[:-3] if len(v) > 10 else v
    return dict(n=len(v), avg=st.mean(v), med=st.median(v), ex3=st.mean(ex) if ex else -1, win=sum(x > 0 for x in v) / len(v))


tested = 0
good = []
for (ei, xi), pn in PN.items():
    for fn, fm in FM.items():
        res = {}
        okk = True
        for s in ("night", "bl82", "fwd"):
            v = [p for p, m, si in zip(pn, fm, SETI[s]) if m and si and p is not None]
            mn = 40 if s == "night" else 15
            if len(v) < mn:
                okk = False
                break
            res[s] = stats(v)
        if not okk:
            continue
        tested += 1
        if res["night"]["avg"] > 0:
            good.append((res["night"]["avg"], ENTRIES[ei][0], EXITS[xi], fn, res))
print(f"configs with enough trades: {tested}; positive on TRAIN: {len(good)}")
both = [g for g in good if g[4]["bl82"]["avg"] > 0 and g[4]["fwd"]["avg"] > 0]
robust = [g for g in both if g[4]["bl82"]["ex3"] > 0 and g[4]["fwd"]["ex3"] > 0 and g[4]["night"]["ex3"] > 0]
print(f"positive on BOTH tests: {len(both)}; also positive with top-3 removed everywhere: {len(robust)}")


def line(g):
    a, en, ex, fn, res = g
    tp, tr, sl, T = ex
    s = " | ".join(f"{k} n{v['n']} {v['avg']:+.1%} med {v['med']:+.1%} ex3 {v['ex3']:+.1%} w{v['win']:.0%}" for k, v in res.items())
    return f"{en:16} {fn:22} tp={tp} tr={tr} sl={sl} T={'end' if T > 10**8 else T//1000}s || {s}"


print("\n== ROBUST (sorted by worst test avg) ==")
for g in sorted(robust, key=lambda g: -min(g[4]["bl82"]["avg"], g[4]["fwd"]["avg"]))[:15]:
    print(line(g))
print("\n== best TRAIN configs and how they did on tests (overfit check) ==")
for g in sorted(good, key=lambda g: -g[0])[:8]:
    print(line(g))

print("\n== the 72 positive on BOTH tests, sorted by worst test avg ==")
for g in sorted(both, key=lambda g: -min(g[4]["bl82"]["avg"], g[4]["fwd"]["avg"]))[:20]:
    print(line(g))
import collections
print("\nfilter frequency among the 72:", collections.Counter(g[3] for g in both).most_common(8))
print("entry frequency among the 72:", collections.Counter(g[1] for g in both).most_common(6))
