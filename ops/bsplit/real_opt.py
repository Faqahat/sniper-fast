# REALISTIC re-score of the BLACKLIST paper runs (bl82 = 10-17 evening, blnight = 10-18 night).
# Entry = right behind the creator bundle x slip. Own price impact on buy AND sell (constant product), pump fee 1.25%/side,
# priority fee per tx. Filters = things knowable when we fire (dev, bundle size seen in the create slot). Exits = simple grid.
# OOS: fit on blnight 1st half, test on blnight 2nd half AND on bl82 (separate session).
import json, itertools, statistics as st, sys

SETS = [("bl82", "/root/bsplit/out_bl82.jsonl", "/root/arbx-fast/paths_blacklist.jsonl"),
        ("night", "/root/bsplit/out.jsonl", "/root/arbx-fast/paths_blnight.jsonl")]
K = 30.0 * 1.073e9          # SOL x Mtok
F = 0.0125                  # pump fee per side
D = []
for name, bf, pf in SETS:
    B = {}
    for l in open(bf):
        r = json.loads(l)
        if "glued" in r:
            B[r["mint"]] = r
    for l in open(pf):
        d = json.loads(l)
        if d["mint"] in B:
            r = dict(B[d["mint"]]); r["path"] = d["path"]; r["set"] = name
            D.append(r)
D.sort(key=lambda r: r["slot"])
night = [r for r in D if r["set"] == "night"]
bl82 = [r for r in D if r["set"] == "bl82"]
h = len(night) // 2
TRAIN, TEST1, TEST2 = night[:h], night[h:], bl82
print(f"n: bl82={len(bl82)} night={len(night)} (train {len(TRAIN)}, test {len(TEST1)} + bl82 {len(TEST2)})")

EXITS = list(itertools.product([None, 1.15, 1.25, 1.4, 1.6, 2.0, 3.0], [None, 0.92, 0.85, 0.75], [None, 0.9, 0.8],
                               [3000, 6000, 10000, 20000, 40000]))
SLIPS = [1.00, 1.04, 1.08]


def exit_mult(path, E, tp, tr, sl, T):
    peak = 0
    p = path[0][1]
    for t, p in path:
        r = p / E
        if r > peak:
            peak = r
        if t >= T or (tp and r >= tp) or (sl and r <= sl) or (tr and peak >= 1.08 and r <= peak * tr):
            return max(p, E * 0.05)
    return max(p, E * 0.05)


def pnl(r, E, X, size, prio):
    vq0 = 30.0 + r["dev"] / 1e9
    vqe = vq0 * E ** 0.5
    s_in = size * (1 - F)
    tok = K / vqe - K / (vqe + s_in)
    vqx = vq0 * X ** 0.5 + s_in            # our SOL still in the curve when we sell
    vtx = K / vqx
    out = (vqx - K / (vtx + tok)) * (1 - F)
    return (out - size - 2 * prio) / size


def entry(r, slip):
    return max(1.0, r["bmult"]) * slip


# precompute exit multiple per (slip, exit, token)
XM = {}
for slip in SLIPS:
    for ei, ex in enumerate(EXITS):
        for i, r in enumerate(D):
            XM[(slip, ei, i)] = exit_mult(r["path"], entry(r, slip), *ex)
IDX = {id(r): i for i, r in enumerate(D)}


def dband(r):
    s = r["dev"] / 1e9
    return "dev<1" if s < 1 else "dev1-2" if s < 2 else "dev2-3" if s < 3 else "dev3-8"


def bband(r):
    g = r["gsol"] if r["glued"] else 0
    return "nob" if g == 0 else "b<1" if g < 1 else "b1-3" if g < 3 else "b3-10" if g < 10 else "b10+"


FILTERS = {"ALL": lambda r: True}
for dv in ["dev<1", "dev1-2", "dev2-3", "dev3-8", "dev<3"]:
    FILTERS[dv] = (lambda dv: lambda r: (dband(r) != "dev3-8") if dv == "dev<3" else dband(r) == dv)(dv)
for bb in ["nob", "b<1", "b1-3", "b3-10", "b10+"]:
    FILTERS[bb] = (lambda bb: lambda r: bband(r) == bb)(bb)
FILTERS["b0-3"] = lambda r: bband(r) in ("nob", "b<1", "b1-3")
FILTERS["b1-10"] = lambda r: bband(r) in ("b1-3", "b3-10")
FILTERS["bundled"] = lambda r: bband(r) != "nob"
for a, b in itertools.product(["dev<3", "dev<1", "dev1-2"], ["bundled", "b1-3", "b1-10", "b0-3"]):
    FILTERS[a + "&" + b] = (lambda a, b: lambda r: FILTERS[a](r) and FILTERS[b](r))(a, b)


def score(g, slip, ei, size, prio):
    v = [pnl(r, entry(r, slip), XM[(slip, ei, IDX[id(r)])], size, prio) for r in g]
    return v


def show(tag, v):
    if not v:
        return f"{tag} n=0"
    ex = sorted(v)[:-3] if len(v) > 15 else v
    return f"{tag} n={len(v):3} avg {st.mean(v):+.3f} med {st.median(v):+.3f} ex-top3 {st.mean(ex):+.3f} win {sum(x > 0 for x in v)/len(v):.0%}"


def fmt(ex):
    tp, tr, sl, T = ex
    return f"tp={tp} trail={tr} sl={sl} T={T//1000}s"


for size, prio in [(0.2, 0.0003), (1.0, 0.0003), (2.0, 0.0003), (1.0, 0.013), (2.0, 0.013)]:
    for slip in SLIPS:
        print(f"\n===== size {size} SOL  prio {prio} SOL/tx  entry = behind-bundle x {slip:.2f} =====")
        # baseline: whole blacklist set, best single exit picked on TRAIN
        res = []
        for fn, f in FILTERS.items():
            g = [r for r in TRAIN if f(r)]
            if len(g) < 25:
                continue
            for ei in range(len(EXITS)):
                v = score(g, slip, ei, size, prio)
                res.append((st.mean(v), fn, ei, len(g)))
        res.sort(key=lambda x: -x[0])
        base = max((x for x in res if x[1] == "ALL"), key=lambda x: x[0])
        for tag, (m, fn, ei, n) in [("BASE (all blacklist)", base)] + [(f"#{k+1}", res[k]) for k in range(3)]:
            f = FILTERS[fn]
            t1 = score([r for r in TEST1 if f(r)], slip, ei, size, prio)
            t2 = score([r for r in TEST2 if f(r)], slip, ei, size, prio)
            print(f"{tag:20} {fn:18} {fmt(EXITS[ei]):34} train n={n} {m:+.3f} | TEST night2 {show('', t1)} | TEST bl82 {show('', t2)}")
