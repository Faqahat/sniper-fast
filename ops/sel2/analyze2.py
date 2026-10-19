import json, math, sys, random
from collections import Counter
from urllib.parse import urlparse
random.seed(7)

POSM = json.load(open("/root/sel2/pos_meta.json"))
NEGM = json.load(open("/root/sel2/neg_meta.json"))
POSF = json.load(open("/root/sel/pos_feat.json"))
NEGF = json.load(open("/root/sel/neg_feat.json"))


def host(uri):
    try:
        h = urlparse(uri).netloc.lower()
        return h or "?"
    except Exception:
        return "?"


def build(metad, featd, label):
    rows = []
    for m, mv in metad.items():
        if mv.get("status") != "ok":
            continue
        fv = featd.get(m, {})
        slot = fv.get("create_slot")
        if not slot:
            continue
        r = {"mint": m, "y": label, "create_slot": slot, "bt": fv.get("block_time")}
        # metadata features
        for k in ("has_twitter", "has_telegram", "has_website", "has_discord",
                  "has_desc", "has_image", "show_name", "name_has_space", "symbol_upper"):
            r[k] = 1 if mv.get(k) else 0
        r["n_socials"] = mv.get("n_socials", 0)
        r["desc_len"] = mv.get("desc_len", 0)
        r["name_len"] = mv.get("name_len", 0)
        r["symbol_len"] = mv.get("symbol_len", 0)
        r["uri_host"] = host(mv.get("uri", ""))
        # bundle/dev/creator features (prior)
        for k in ("dev_buy_sol", "n_cobundlers", "cobundler_buys_same_slot", "n_same_slot_sigs",
                  "total_bundled_sol", "buys_in_create_tx", "creator_prior_sigs",
                  "creator_total_sigs", "creator_age_slots", "total_sigs_pages"):
            r[k] = fv.get(k)
        rows.append(r)
    return rows


pos = build(POSM, POSF, 1)
neg = build(NEGM, NEGF, 0)
print(f"built: pos(meta-ok & slot)={len(pos)}  neg(meta-ok & slot)={len(neg)}")

# time window to positive slot range
pslots = sorted(r["create_slot"] for r in pos)
lo, hi = pslots[0], pslots[-1]
neg = [r for r in neg if lo <= r["create_slot"] <= hi]
print(f"pos slot window {lo}..{hi}; neg in-window={len(neg)}")
base = len(pos) / (len(pos) + len(neg))
print(f"base rate = {base:.4f} (pos={len(pos)} neg={len(neg)})\n")


def mw_u(a, b):
    n1, n2 = len(a), len(b)
    if n1 == 0 or n2 == 0:
        return (None, None, None)
    allv = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks = [0.0] * len(allv); i = 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        r = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[k] = r
        i = j + 1
    R1 = sum(ranks[k] for k in range(len(allv)) if allv[k][1] == 0)
    U1 = R1 - n1 * (n1 + 1) / 2.0
    AUC = U1 / (n1 * n2)
    mu = n1 * n2 / 2.0
    cnt = Counter(v for v, _ in allv); N = n1 + n2
    tie = sum(t**3 - t for t in cnt.values())
    sig = math.sqrt(n1 * n2 / 12.0 * ((N + 1) - tie / (N * (N - 1)))) if N > 1 else 0
    if sig == 0:
        return (AUC, 0, 1)
    z = (U1 - mu) / sig
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return (AUC, z, p)


NUMERIC = ["n_socials", "desc_len", "name_len", "symbol_len", "dev_buy_sol",
           "n_cobundlers", "total_bundled_sol", "buys_in_create_tx", "n_same_slot_sigs",
           "creator_prior_sigs", "creator_total_sigs", "creator_age_slots", "total_sigs_pages"]
BOOL = ["has_twitter", "has_telegram", "has_website", "has_discord", "has_desc",
        "has_image", "show_name", "name_has_space", "symbol_upper"]


def vals(rows, f):
    return [r[f] for r in rows if r.get(f) is not None]


print("=== NUMERIC univariate (Mann-Whitney AUC; AUC>.5 => higher in his picks) ===")
print(f"{'feature':22s}{'pos_med':>9s}{'neg_med':>9s}{'AUC':>7s}{'z':>7s}{'p':>10s}")
num_rank = []
for f in NUMERIC:
    a = vals(pos, f); b = vals(neg, f)
    if not a or not b:
        continue
    AUC, z, p = mw_u(a, b)
    am = sorted(a)[len(a) // 2]; bm = sorted(b)[len(b) // 2]
    print(f"{f:22s}{am:>9.3f}{bm:>9.3f}{AUC:>7.3f}{z:>7.2f}{p:>10.2e}")
    num_rank.append((f, AUC, abs(AUC - 0.5)))

print("\n=== BOOLEAN univariate (rate in pos vs neg; lift = p(feat|pos)/p(feat|neg)) ===")
print(f"{'feature':16s}{'pos_rate':>9s}{'neg_rate':>9s}{'lift':>7s}{'p(chi2)':>10s}")


def chi2_2x2(a, b, c, d):
    # a=pos&feat, b=pos&nofeat, c=neg&feat, d=neg&nofeat
    n = a + b + c + d
    if min(a + c, b + d, a + b, c + d) == 0 or n == 0:
        return 0.0, 1.0
    exp = [(a + b) * (a + c) / n, (a + b) * (b + d) / n, (c + d) * (a + c) / n, (c + d) * (b + d) / n]
    obs = [a, b, c, d]
    chi = sum((o - e) ** 2 / e for o, e in zip(obs, exp) if e > 0)
    # p via survival of chi2 df=1 = erfc(sqrt(chi/2))
    p = math.erfc(math.sqrt(chi / 2)) if chi >= 0 else 1.0
    return chi, p


bool_rank = []
for f in BOOL:
    a = sum(1 for r in pos if r[f]); b = len(pos) - a
    c = sum(1 for r in neg if r[f]); d = len(neg) - c
    pr = a / len(pos); nr = c / len(neg) if neg else 0
    lift = (pr / nr) if nr > 0 else float('inf')
    chi, p = chi2_2x2(a, b, c, d)
    print(f"{f:16s}{pr:>9.3f}{nr:>9.3f}{lift:>7.2f}{p:>10.2e}")
    bool_rank.append((f, pr, nr, lift, p))

print("\n=== URI HOST (metadata service / launch tool fingerprint) ===")
ph = Counter(r["uri_host"] for r in pos); nh = Counter(r["uri_host"] for r in neg)
allh = set(ph) | set(nh)
print(f"{'host':34s}{'pos':>6s}{'pos%':>7s}{'neg':>6s}{'neg%':>7s}{'lift':>7s}")
host_stats = []
for h in sorted(allh, key=lambda x: -(ph[x] + nh[x])):
    pp = ph[h] / len(pos); npp = nh[h] / len(neg) if neg else 0
    lift = (pp / npp) if npp > 0 else float('inf')
    if ph[h] + nh[h] >= 3:
        print(f"{h[:34]:34s}{ph[h]:>6d}{pp:>7.3f}{nh[h]:>6d}{npp:>7.3f}{lift:>7.2f}")
    host_stats.append((h, ph[h], pp, nh[h], npp, lift))

# ---------- rule search: single + pair combos on booleans + host + numeric thresholds ----------
print("\n=== RULE SEARCH (in-sample precision/recall vs base) ===")
allrows = pos + neg
P = len(pos)


def evalrule(fn, name, rows=None, pp=None):
    rows = rows if rows is not None else allrows
    PP = pp if pp is not None else P
    tp = sum(1 for r in rows if r["y"] == 1 and fn(r))
    sel = sum(1 for r in rows if fn(r))
    if sel == 0:
        return None
    prec = tp / sel; rec = tp / PP
    brate = PP / len(rows)
    return dict(name=name, sel=sel, tp=tp, prec=prec, rec=rec, lift=prec / brate)


cands = []
# boolean positive triggers
for f in BOOL:
    cands.append((f + "=1", lambda r, f=f: r[f] == 1))
    cands.append((f + "=0", lambda r, f=f: r[f] == 0))
# n_socials thresholds
for t in (1, 2, 3):
    cands.append((f"n_socials>={t}", lambda r, t=t: (r.get("n_socials") or 0) >= t))
# desc/name
cands.append(("has_desc&has_twitter", lambda r: r["has_desc"] and r["has_twitter"]))
cands.append(("twitter&website", lambda r: r["has_twitter"] and r["has_website"]))
cands.append(("twitter&telegram", lambda r: r["has_twitter"] and r["has_telegram"]))
# host-based
top_hosts = [h for h, c in Counter(r["uri_host"] for r in allrows).most_common(8)]
for h in top_hosts:
    cands.append((f"host={h[:20]}", lambda r, h=h: r["uri_host"] == h))

res = [evalrule(fn, nm) for nm, fn in cands]
res = [x for x in res if x]
res.sort(key=lambda x: -x["lift"])
print(f"{'rule':34s}{'sel':>5s}{'tp':>5s}{'prec':>7s}{'recall':>8s}{'lift':>7s}")
for x in res[:25]:
    print(f"{x['name'][:34]:34s}{x['sel']:>5d}{x['tp']:>5d}{x['prec']:>7.3f}{x['rec']:>8.3f}{x['lift']:>7.2f}")

# ---------- logistic regression with TIME split ----------
LRF = ["has_twitter", "has_telegram", "has_website", "has_discord", "has_desc", "has_image",
       "show_name", "n_socials", "name_len", "symbol_len",
       "dev_buy_sol", "n_cobundlers", "total_bundled_sol", "creator_prior_sigs"]


def fv(r):
    return [float(r.get(f) or 0.0) for f in LRF]


data = [(fv(r), r["y"], r["create_slot"]) for r in allrows]
data.sort(key=lambda x: x[2])
cut = int(len(data) * 0.7)
train, test = data[:cut], data[cut:]
import statistics as st
cols = list(zip(*[x[0] for x in train]))
mean = [st.mean(c) for c in cols]
sd = [(st.pstdev(c) or 1.0) for c in cols]


def norm(v):
    return [(v[i] - mean[i]) / sd[i] for i in range(len(v))]


def train_lr(tr, l2=2.0, lr=0.1, epochs=3000):
    n = len(LRF); w = [0.0] * n; b = 0.0
    X = [norm(x[0]) for x in tr]; Y = [x[1] for x in tr]
    npos = sum(Y); nneg = len(Y) - npos
    wpos = len(Y) / (2 * npos) if npos else 1; wneg = len(Y) / (2 * nneg) if nneg else 1
    for ep in range(epochs):
        gw = [0.0] * n; gb = 0.0
        for xi, yi in zip(X, Y):
            z = b + sum(w[j] * xi[j] for j in range(n))
            p = 1 / (1 + math.exp(-max(-30, min(30, z))))
            cw = wpos if yi == 1 else wneg
            d = (p - yi) * cw
            for j in range(n):
                gw[j] += d * xi[j]
            gb += d
        for j in range(n):
            w[j] -= lr * (gw[j] / len(X) + l2 * w[j] / len(X))
        b -= lr * gb / len(X)
    return w, b


w, b = train_lr(train)
print(f"\n=== LOGISTIC REGRESSION  (time split: train={len(train)} pos={sum(y for _,y,_ in train)}, test={len(test)} pos={sum(y for _,y,_ in test)}) ===")
print("coeffs (standardized):")
for f, wi in sorted(zip(LRF, w), key=lambda t: -abs(t[1])):
    print(f"  {f:22s}{wi:+.3f}")


def prob(x):
    v = norm(x); z = b + sum(w[j] * v[j] for j in range(len(w)))
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def auc_of(rows):
    ps = [prob(x) for x, y, _ in rows if y == 1]
    ns = [prob(x) for x, y, _ in rows if y == 0]
    return mw_u(ps, ns)[0]


print(f"train AUC={auc_of(train):.3f}  test AUC={auc_of(test):.3f}")
bt = sum(y for _, y, _ in test) / len(test)
print(f"test base rate={bt:.4f}")
print("thr    sel  tp  prec   recall  lift")
for thr in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
    sel = [(y) for x, y, _ in test if prob(x) >= thr]
    if not sel:
        print(f"{thr:.2f}  (0)"); continue
    tp = sum(sel); prec = tp / len(sel); rec = tp / sum(y for _, y, _ in test)
    print(f"{thr:.2f}  {len(sel):4d} {tp:3d}  {prec:.3f}  {rec:.3f}  {prec/bt:.2f}")
