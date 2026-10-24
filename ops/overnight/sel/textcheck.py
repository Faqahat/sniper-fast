#!/usr/bin/env python3
# Owner 10-24 07:00 PKT ("sure"): before trying Jev (a hosted text-decision model), does a token's TEXT (name, symbol, description,
# socials, copycat names) carry any signal for our strategy? Free, local, lexical stand-in (if simple text features show nothing,
# an API text model is unlikely to add much; if they do, Jev is worth a trial). TRAIN = 10-23 06:30-18:33 PKT, TEST = 10-23
# 19:26 -> 10-24 06:27 PKT (never seen). Rows: textcheck_rows.py (every in-envelope dump: IMIT1 score, label = a pro bought within
# 1 s, our P&L at 75 ms / 0.35 SOL, no TP / SL -10% / 1.3 s).
#  (a) token level: text alone -> "the pros bought this token's dumps" (AUC on TEST)
#  (b) dump level: IMIT1 score alone vs score + text (AUC on TEST)
#  (c) money: our picks on TEST split by the text score (P&L per third)
import json, re, math, collections, zlib, statistics
import numpy as np
D = "/home/moiz/sniper/ops/overnight/sel"; C = "/home/moiz/sniper-data/collect"
TH = json.load(open(f"{D}/IMIT1.json"))["thresholds"]; EX = "tpnone_sl10_1.3s"; EXTRA, FAIL = 0.0035, 0.0005
tr_rows = json.load(open(f"{D}/textcheck_r2.json"))["rows"]; te_rows = json.load(open(f"{D}/textcheck_r3.json"))["rows"]
need = {o["m"] for o in tr_rows + te_rows}
L, M = {}, {}
for run in ("run_20261022_1543", "run_20261023_1426"):
    for l in open(f"{C}/{run}/launches.jsonl"):
        try: c = json.loads(l)
        except Exception: continue
        L.setdefault(c["mint"], c)
    for l in open(f"{C}/{run}/enrich.jsonl"):
        try: e = json.loads(l)
        except Exception: continue
        if e.get("mint") in need: M.setdefault(e["mint"], (e.get("meta") or {}))
# copycat names: launches with the same normalized name in the hour before
norm = lambda s: re.sub(r"[^a-z0-9\u0080-￿]", "", (s or "").lower())
seen = collections.defaultdict(list)
for c in sorted(L.values(), key=lambda c: c.get("bt") or 0): seen[norm(c.get("name"))].append(c.get("bt") or 0)
def dup(c):
    v = seen.get(norm(c.get("name")), []); t = c.get("bt") or 0
    return sum(1 for x in v if t - 3600 <= x < t)
NB = 1 << 18
h = lambda s: zlib.crc32(s.encode()) % NB
def feats(m):
    c = L.get(m, {}); meta = M.get(m, {}); j = meta.get("json") or {}
    name = (c.get("name") or j.get("name") or "").strip(); sym = (c.get("symbol") or j.get("symbol") or "").strip(); desc = (j.get("description") or "").strip()
    tw = str(j.get("twitter") or ""); tg = str(j.get("telegram") or ""); ws = str(j.get("website") or "")
    toks = set()
    for w in re.findall(r"\w+", (name + " " + sym).lower()): toks.add("w:" + w)
    s = " " + norm(name) + " "
    for n in (3, 4):
        for i in range(len(s) - n + 1): toks.add(f"c{n}:" + s[i:i + n])
    for w in re.findall(r"\w+", desc.lower())[:60]: toks.add("d:" + w)
    k = dup(c)
    flags = {"has_desc": bool(desc), "tw_status": "/status/" in tw, "tw_profile": bool(tw) and "/status/" not in tw and tw not in ("x.com", "https://x.com"),
             "tw_placeholder": tw in ("x.com", "https://x.com"), "has_tg": bool(tg), "has_web": bool(ws), "nonascii": any(ord(ch) > 127 for ch in name),
             "digits": any(ch.isdigit() for ch in name), "allcaps": name.isupper(), "long_name": len(name) > 12, "meta_missing": not j,
             "dup0": k == 0, "dup1_3": 1 <= k <= 3, "dup4p": k >= 4}
    for f, v in flags.items():
        if v: toks.add("f:" + f)
    return [h(t) for t in toks], flags, k
F = {m: feats(m) for m in need}
def auc(y, s):
    y = np.asarray(y); s = np.asarray(s, float); o = np.argsort(s, kind="mergesort"); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    # ties: average ranks
    _, inv, cnt = np.unique(s, return_inverse=True, return_counts=True); sums = np.bincount(inv, weights=r); r = (sums / cnt)[inv]
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else float("nan")
def nb_model(items):                       # items: (hashed features, label) -> log-count ratios (naive Bayes text score)
    p = np.ones(NB); q = np.ones(NB); n1 = n0 = 0
    for hs, y in items:
        if y: p[hs] += 1; n1 += 1
        else: q[hs] += 1; n0 += 1
    return np.log(p / p.sum()) - np.log(q / q.sum())
score_of = lambda w, m: float(w[F[m][0]].sum())
# (a) token level
def tok_lab(rows):
    d = collections.defaultdict(int)
    for o in rows: d[o["m"]] = max(d[o["m"]], o["lab"])
    return d
ta, tb = tok_lab(tr_rows), tok_lab(te_rows)
W = nb_model([(F[m][0], y) for m, y in ta.items()])
print(f"rows: TRAIN {len(tr_rows)} dumps on {len(ta)} tokens (pros bought {sum(ta.values())}), TEST {len(te_rows)} dumps on {len(tb)} tokens (pros bought {sum(tb.values())})")
print(f"(a) token level, text alone -> the pros bought this token: AUC TEST {auc(list(tb.values()), [score_of(W, m) for m in tb]):.3f}  (0.5 = no signal)")
for f in ("dup0", "dup1_3", "dup4p", "tw_status", "tw_profile", "tw_placeholder", "has_tg", "has_web", "has_desc", "nonascii", "meta_missing"):
    a = [y for m, y in tb.items() if F[m][1][f]]; b = [y for m, y in tb.items() if not F[m][1][f]]
    if a: print(f"     {f:15s}: {len(a):5d} tokens, pros bought {100 * sum(a) / len(a):5.1f}% vs {100 * sum(b) / max(1, len(b)):5.1f}% without")
# (b) dump level: score alone vs score + text (2-feature logistic regression fitted on TRAIN; the text score of a TRAIN token from a
# model fitted on the OTHER half of the TRAIN tokens, so the stacker never sees an in-sample text score)
ms = sorted(ta); half = {m: (zlib.crc32(m.encode()) & 1) for m in ms}
W0 = nb_model([(F[m][0], y) for m, y in ta.items() if half[m] == 0]); W1 = nb_model([(F[m][0], y) for m, y in ta.items() if half[m] == 1])
tx_tr = np.array([score_of(W1 if half[o["m"]] == 0 else W0, o["m"]) for o in tr_rows]); tx_te = np.array([score_of(W, o["m"]) for o in te_rows])
def fit_lr(X, y, it=50):
    X = np.c_[np.ones(len(X)), X]; w = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X @ w)); g = X.T @ (y - p); Hh = X.T @ (X * (p * (1 - p))[:, None]) + 1e-6 * np.eye(len(w)); w += np.linalg.solve(Hh, g)
    return w
mu, sd = tx_tr.mean(), tx_tr.std() + 1e-9
Xtr = np.c_[[o["score"] for o in tr_rows], (tx_tr - mu) / sd]; ytr = np.array([o["lab"] for o in tr_rows], float)
w = fit_lr(Xtr, ytr); Xte = np.c_[[o["score"] for o in te_rows], (tx_te - mu) / sd]; yte = np.array([o["lab"] for o in te_rows])
comb = np.c_[np.ones(len(Xte)), Xte] @ w
print(f"(b) dump level (label: a pro bought within 1 s), TEST AUC: IMIT1 score alone {auc(yte, Xte[:, 0]):.3f} | score + text {auc(yte, comb):.3f} | text alone {auc(yte, Xte[:, 1]):.3f}  (text weight {w[2]:+.3f} vs score {w[1]:+.3f})")
# (c) money on TEST picks (run-5 rule: strict, or wider on the dev's tokens), split by the text score
picks = [(o, t) for o, t in zip(te_rows, tx_te) if o["score"] >= (TH["top4"] if o["dev"] else TH["top2"])]
qs = np.quantile([t for _, t in picks], [1 / 3, 2 / 3]) if picks else [0, 0]
print(f"(c) our TEST picks ({len(picks)}), P&L at 75 ms / 0.35 SOL by text score (each pick on its own):")
for lab, lo, hi in (("low text score", -1e18, qs[0]), ("middle", qs[0], qs[1]), ("high text score", qs[1], 1e18)):
    v = [o["ours"].get("75|0.35") for o, t in picks if lo <= t < hi]
    f = [x[EX] - EXTRA for x in v if isinstance(x, dict)]; nb = sum(1 for x in v if x == "b")
    print(f"     {lab:16s}: {len(v):3d} picks, {len(f):3d} fills, {sum(f) - FAIL * nb:+.3f} SOL ({100 * sum(f) / max(1, len(f)) / 0.35:+.1f}%/fill), win {100 * sum(1 for x in f if x > 0) / max(1, len(f)):.0f}%")
