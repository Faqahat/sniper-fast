# "HIS STRATEGY" on our BLACKLIST paper trades, REALISTIC fills.
# Entry: right behind the creator bundle (bundled) or first (no bundle), x slip; own price impact on every leg; pump fee 1.25%/side.
# Exits like his: BUNDLED -> quick scalp in 2 legs (sell f1 at +a1, rest at +a2 or time cap/stop); NO-BUNDLE -> ride legs longer.
# Fees like his: high priority (0.013 SOL) on bundled, ~0 on no-bundle. Fit on night 1st half, test on night 2nd half + bl82
# (+ the forward run if present). Usage: real_his.py [extra_set_name out_jsonl paths_jsonl]
import json, itertools, statistics as st, sys

SETS = [("bl82", "/root/bsplit/out_bl82.jsonl", "/root/arbx-fast/paths_blacklist.jsonl"),
        ("night", "/root/bsplit/out.jsonl", "/root/arbx-fast/paths_blnight.jsonl")]
if len(sys.argv) >= 4:
    SETS.append((sys.argv[1], sys.argv[2], sys.argv[3]))
K = 30.0 * 1.073e9
F = 0.0125
SIZE = 1.0
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
h = len(night) // 2
TRAIN = night[:h]
TESTS = [("night 2nd half", night[h:]), ("bl82 (other day)", [r for r in D if r["set"] == "bl82"])]
if len(SETS) > 2:
    TESTS.append((SETS[2][0] + " (FORWARD)", [r for r in D if r["set"] == SETS[2][0]]))


def bundled(r):
    return r["glued"] >= 1


def run(r, slip, legs, T, sl, trail, prio):
    """legs: [(frac, mult_vs_entry)] sold when reached; remainder at T / stop / trail. Returns PnL fraction of SIZE."""
    vq0 = 30.0 + r["dev"] / 1e9
    E = max(1.0, r["bmult"]) * slip
    vqe = vq0 * E ** 0.5
    s_in = SIZE * (1 - F)
    tok = K / vqe - K / (vqe + s_in)
    left, net_in, out, ntx, peak = 1.0, s_in, 0.0, 1, 0.0
    pend = list(legs)

    def sell(frac, X):
        nonlocal left, net_in, out, ntx
        t = tok * frac
        vq = vq0 * X ** 0.5 + net_in
        o = (vq - K / (K / vq + t))
        net_in -= o
        out += o * (1 - F)
        left -= frac
        ntx += 1
    X = r["path"][0][1]
    for t, X in r["path"]:
        rr = X / E
        peak = max(peak, rr)
        while pend and rr >= pend[0][1] and left > 1e-9:
            f, _ = pend.pop(0)
            sell(min(f, left), X)
        if left <= 1e-9:
            break
        if t >= T or (sl and rr <= sl) or (trail and peak >= 1.08 and rr <= peak * trail):
            sell(left, max(X, E * 0.05))
            break
    if left > 1e-9:
        sell(left, max(X, E * 0.05))
    return (out - SIZE - prio * ntx) / SIZE


B_GRID = [dict(legs=[(f1, a1), (1 - f1, a2)] if f1 < 1 else [(1.0, a1)], T=T, sl=sl, trail=None)
          for f1, a1, a2, T, sl in itertools.product([0.5, 1.0], [1.06, 1.08, 1.10, 1.15, 1.25], [1.15, 1.25, 1.4],
                                                     [3000, 6000, 10000, 20000], [None, 0.9, 0.85])]
N_GRID = [dict(legs=[(f1, a1), (1 - f1, a2)], T=T, sl=sl, trail=tr)
          for f1, a1, a2, T, sl, tr in itertools.product([0.3, 0.5], [1.1, 1.2, 1.3], [1.5, 2.0, 3.0], [10000, 20000, 40000],
                                                         [None, 0.8], [None, 0.85])]
FILTS = {"all bundled": lambda r: bundled(r), "bundle 1-3 SOL": lambda r: bundled(r) and 1 <= r["gsol"] < 3,
         "bundle <10 SOL": lambda r: bundled(r) and r["gsol"] < 10, "bundle 1-10 SOL": lambda r: bundled(r) and 1 <= r["gsol"] < 10}


def fit(g, grid, slip, prio):
    best = None
    for p in grid:
        v = st.mean(run(r, slip, p["legs"], p["T"], p["sl"], p["trail"], prio) for r in g)
        if best is None or v > best[0]:
            best = (v, p)
    return best


def desc(p):
    return f"legs={[(round(f,2), a) for f, a in p['legs']]} T={p['T']//1000}s sl={p['sl']} trail={p['trail']}"


def show(v):
    if not v:
        return "n=0"
    ex = sorted(v)[:-3] if len(v) > 15 else v
    return f"n={len(v):3} avg {st.mean(v):+.3f} med {st.median(v):+.3f} ex-top3 {st.mean(ex):+.3f} win {sum(x>0 for x in v)/len(v):.0%}"


for slip in (1.00, 1.04):
    print(f"\n######## entry slip x{slip:.2f} behind bundle (1.00 = first outsider, like him) — size {SIZE} SOL ########")
    nb_tr = [r for r in TRAIN if not bundled(r)]
    nbest = fit(nb_tr, N_GRID, slip, 0.0003)
    print(f"NO-BUNDLE exit (fit n={len(nb_tr)}, train {nbest[0]:+.3f}): {desc(nbest[1])}")
    for tn, tg in TESTS:
        g = [r for r in tg if not bundled(r)]
        print(f"   TEST {tn:24} {show([run(r, slip, nbest[1]['legs'], nbest[1]['T'], nbest[1]['sl'], nbest[1]['trail'], 0.0003) for r in g])}")
    for fn, f in FILTS.items():
        b_tr = [r for r in TRAIN if f(r)]
        bbest = fit(b_tr, B_GRID, slip, 0.013)
        print(f"BUNDLED [{fn}] scalp (fit n={len(b_tr)}, train {bbest[0]:+.3f}): {desc(bbest[1])}")
        for tn, tg in TESTS:
            g = [r for r in tg if f(r)]
            vb = [run(r, slip, bbest[1]["legs"], bbest[1]["T"], bbest[1]["sl"], bbest[1]["trail"], 0.013) for r in g]
            gn = [r for r in tg if not bundled(r)]
            vn = [run(r, slip, nbest[1]["legs"], nbest[1]["T"], nbest[1]["sl"], nbest[1]["trail"], 0.0003) for r in gn]
            print(f"   TEST {tn:24} bundled {show(vb)} || COMBINED w/ no-bundle {show(vb + vn)}")
