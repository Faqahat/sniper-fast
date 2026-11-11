"""dip46 B1 LOG shadow: the offline side (docs/dip46_b1.md).

  * the frozen B0 model as JSON (exported by b1_export.py from the push-l5/opt2 FINAL-train models, re-created and verified by
    ~/sniper-studies/push4-audit/p4_models.py) and a pure-Python scorer of it (same tree walk and summation order as sklearn's
    HistGradientBoosting predict: baseline first, then the trees in order; a numerical split goes left when x <= threshold, NaN by
    missing_go_to_left)
  * the reference feature builder: the arm-time features of push-l5/snap2.py / push4-audit/p4_snap.py (trades strictly before slot s),
    written per token as a stream so the Rust engine (ps46_b1.rs) can be checked against it row by row
Read-only; no network.
"""
import json, hashlib, math, struct

F0 = ["age", "vsol", "last_buy", "last_pct", "last_gap", "bb5", "bs5", "ntr5", "busy", "nbuyers", "bsol100", "ssol100", "runup", "ddhigh", "top1", "top1_age", "top3",
      "n_ge2", "n_ge4", "n_ge6", "sum_ge2", "cr_bal", "n_prev_dumps", "last_dump_gap", "last_dump_spct"]
LITE = ["age", "vsol", "bb5", "bs5", "ntr5", "runup", "ddhigh", "nbuyers", "busy", "n_prev_dumps", "last_dump_gap", "score"]
KSTD = 3.219e25
FEE = 0.0125


def fbits(x): return struct.unpack("<Q", struct.pack("<d", float(x)))[0]
def bitsf(b): return struct.unpack("<d", struct.pack("<Q", int(b)))[0]


def feat_hash(f):
    """first 16 hex of sha256 over the feature values as little-endian f64 (the engine's per-record feat_hash)"""
    return hashlib.sha256(b"".join(struct.pack("<d", float(x)) for x in f)).hexdigest()[:16]


def schema_hash():
    return hashlib.sha256((",".join(F0) + "|" + ",".join(LITE)).encode()).hexdigest()[:16]


# ---- the model ------------------------------------------------------------------------------------------------------------

def export_gbm(m):
    trees = []
    for pr in m._predictors:
        nd = pr[0].nodes
        assert not nd["is_categorical"].any()
        trees.append(dict(f=[int(x) for x in nd["feature_idx"]], t=[fbits(x) for x in nd["num_threshold"]], l=[int(x) for x in nd["left"]], r=[int(x) for x in nd["right"]],
                          leaf=[int(x) for x in nd["is_leaf"]], v=[fbits(x) for x in nd["value"]], ml=[int(x) for x in nd["missing_go_to_left"]]))
    return dict(baseline=fbits(float(m._baseline_prediction.ravel()[0])), n_features=int(m.n_features_in_), features=[str(x) for x in m.feature_names_in_], trees=trees)


class Gbm:
    def __init__(self, j):
        self.base = bitsf(j["baseline"]); self.features = j["features"]
        self.trees = [(t["f"], [bitsf(x) for x in t["t"]], t["l"], t["r"], t["leaf"], [bitsf(x) for x in t["v"]], t["ml"]) for t in j["trees"]]

    def raw(self, x):
        s = self.base
        for f, t, l, r, leaf, v, ml in self.trees:
            k = 0
            while not leaf[k]:
                xv = x[f[k]]
                if xv != xv: k = l[k] if ml[k] else r[k]
                else: k = l[k] if xv <= t[k] else r[k]
            s += v[k]
        return s


class Model:
    def __init__(self, path):
        raw = open(path, "rb").read(); self.sha = hashlib.sha256(raw).hexdigest(); j = json.loads(raw)
        self.dec = Gbm(j["dec"]); self.reg = Gbm(j["reg"]); self.rule = j["rule"]
        assert self.dec.features == F0 and self.reg.features == LITE, "feature order"

    def score(self, f):
        """f = the 25 F0 values -> (decoder probability, regressor value or None when the decoder score < dec_min)"""
        p = 1.0 / (1.0 + math.exp(-self.dec.raw(f)))
        if p < self.rule["dec_min"]: return p, None
        d = dict(zip(F0, f)); x = [d[n] for n in LITE[:-1]] + [p]
        return p, self.reg.raw(x)


def kind_of(f):
    """push-l5 cls_of: T2-like (bb5 >= 3 and bs5 < 2), re-arm-like (bs5 >= 2), other"""
    bb5, bs5 = f[F0.index("bb5")], f[F0.index("bs5")]
    return "t2" if (bb5 >= 3 and bs5 < 2) else ("rearm" if bs5 >= 2 else "other")


# ---- the reference feature builder (p4_snap.py work(), per token, trades strictly before slot qs) ----------------------------

def find_dumps_one(tr):
    """the plan1110 dump definition on one token's trades (chain order): maximal runs of sells in one slot, drop >= 3% and >= 0.3 SOL.
    tr rows: (s, i, k, user, buy, sol, tok, vsol, vtok). Returns [(slot, i0, i1, drop, spct, sol, j, q)]."""
    out = []; n = len(tr); j = 0
    pa = [r[7] / r[8] for r in tr]
    pb = [(r[7] - (1.0 if r[4] else -1.0) * r[5]) / (r[8] + (1.0 if r[4] else -1.0) * r[6]) for r in tr]
    while j < n:
        if tr[j][4]: j += 1; continue
        q = j
        while q + 1 < n and (not tr[q + 1][4]) and tr[q + 1][0] == tr[j][0]: q += 1
        drop = 1 - pa[q] / pb[j]; sol = 0.0
        for x in range(j, q + 1): sol += tr[x][5] / 1e9
        if drop >= 0.03 and sol >= 0.3:
            ws = {}; order = []
            for x in range(j, q + 1):
                u = tr[x][3]
                if u not in ws: ws[u] = 0.0; order.append(u)
                ws[u] += tr[x][6]
            sw = max(order, key=lambda u: ws[u])
            out.append((tr[j][0], tr[j][1], tr[q][1], drop, ws[sw] / 1e13, sol, j, q))
        j = q + 1
    return out


def features_at(tr, qs, cslot, creator, dumps):
    """the 25 F0 features at (token, slot qs) from its trades `tr` (chain order) strictly before qs; None when there is none"""
    import bisect
    S = [r[0] for r in tr]
    hi = bisect.bisect_left(S, qs)
    if hi == 0: return None
    lo = min(bisect.bisect_left(S, qs - 100), hi - 1); l5 = bisect.bisect_left(S, qs - 5); last = hi - 1
    pa = lambda r: r[7] / r[8]
    pb = lambda r: (r[7] - (1.0 if r[4] else -1.0) * r[5]) / (r[8] + (1.0 if r[4] else -1.0) * r[6])
    bal = {}; fb = {}
    for r in tr[:hi]:
        u = r[3]; bal[u] = bal.get(u, 0.0) + (r[6] / 1e13 if r[4] else -r[6] / 1e13)
        if r[4] and u not in fb: fb[u] = r[0]
    ex = sorted(((v, u) for u, v in bal.items() if u != creator and v > 0.05), reverse=True); top = ex[:3]
    w5 = tr[l5:hi]; seg = tr[lo:hi]
    bb = [r[6] / 1e13 for r in w5 if r[4]]; bs = [r[6] / 1e13 for r in w5 if not r[4]]
    ds = [d for d in dumps if d[0] < qs]; nd = len(ds)
    L = tr[last]
    f = dict(age=(qs - cslot) if cslot is not None else -1, vsol=L[7] / 1e9, last_buy=1 if L[4] else 0, last_pct=L[6] / 1e13, last_gap=qs - L[0],
             bb5=max(bb) if bb else 0.0, bs5=max(bs) if bs else 0.0, ntr5=hi - l5, busy=hi - lo, nbuyers=len(set(r[3] for r in seg if r[4])),
             bsol100=sum(r[5] / 1e9 for r in seg if r[4]), ssol100=sum(r[5] / 1e9 for r in seg if not r[4]),
             runup=pb(L) / pb(tr[lo]), ddhigh=pb(L) / max(pa(r) for r in seg),
             top1=top[0][0] if top else 0.0, top1_age=(qs - fb[top[0][1]]) if top else -1, top3=sum(v for v, _ in top), n_ge2=sum(1 for v, _ in ex if v >= 2),
             n_ge4=sum(1 for v, _ in ex if v >= 4), n_ge6=sum(1 for v, _ in ex if v >= 6), sum_ge2=sum(v for v, _ in ex if v >= 2),
             cr_bal=bal.get(creator, 0.0) if creator is not None else 0.0,
             n_prev_dumps=nd, last_dump_gap=(qs - ds[-1][0]) if nd else 10 ** 6, last_dump_spct=ds[-1][4] if nd else 0.0)
    return [float(f[n]) for n in F0]


def outcome(tr, dumps, qs, W, smax, dp=26, hold=3, size=0.8, G=0.10):
    """the window [qs, qs+W-1]'s paper outcome (push-l5 outcomes + push2-d sim_one, fol 1): the first dump with drop >= G in the window
    fills at position i1 + dp behind it (next slot past the slot's last pump index + 20), exit at the start of slot es + hold.
    smax = {slot: last pump tx index}. None = no fill."""
    d = next((d for d in dumps if qs <= d[0] <= qs + W - 1 and d[3] >= G), None)
    if d is None: return None
    s0, i0, i1, drop, spct, sol, j, q = d
    b = len(tr); S = [r[0] for r in tr]; I = [r[1] for r in tr]
    VS = lambda x: tr[x][7] / 1e9; VT = lambda x: float(tr[x][8])
    blen = smax.get(s0, 1200) + 20
    K = VS(q) * VT(q); pos = i1 + dp
    if pos <= blen: es, ei = s0, pos
    else: es, ei = s0 + 1, pos - blen
    e = q
    while e + 1 < b and (S[e + 1] < es or (S[e + 1] == es and I[e + 1] <= ei)): e += 1
    vs = VS(e); vt = VT(e)
    vs2 = vs + size; vt2 = K / vs2; mytok = vt - vt2
    cost = size * (1 + FEE) + 0.0002 + 0.000005
    x = e + 1; lb = 0.0; buyers = set()
    while x < b and S[x] < es + hold:
        if tr[x][4]: vs2 += tr[x][5] / 1e9; vt2 = K / vs2; lb += tr[x][5] / 1e9; buyers.add(tr[x][3])
        else: vt2 += float(tr[x][6]); vs2 = K / vt2
        x += 1
    paper = (vs2 - K / (vt2 + mytok)) * (1 - FEE) - 0.0006 - cost
    return dict(dump=(s0, i0, i1), drop=drop, es=es, ei=ei, exit_slot=es + hold, paper=paper, lb=lb, nbuy=len(buyers))
