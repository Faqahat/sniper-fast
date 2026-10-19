#!/usr/bin/env python3
# READ-ONLY. What separates 4yFAz's picks? A "his-like" score (weighted logistic regression, pure python) on the historical
# sample: positives = his picks (census), negatives = random launches he did not buy (weight 27 = sampling rate), all inside
# the FIX filter (dev 0.5-8 SOL incl. cap buys, host ok, not mayhem). Feature tiers by when they are visible:
#   A  create tx            B  + creator bundle (~3 ms)        C  + creator wallet history (RPC / cache)
#   D  + metadata JSON      T  + X/Twitter author+tweet (fxtwitter; author fields only, engagement is look-ahead)
# Fit on the first 60% by slot, judged on the last 40% (and on forward rows when given). Reports AUC, his-precision and
# his-recall by score tier, race rate and REALISTIC PnL (hc_search.sim: 2 SOL, land S @<=100, slip 1.03, 0.009 SOL prio).
import json, math, re, sys, statistics as st, collections, random
sys.path.insert(0, "/root/race")
from hc_search import sim, EXITS, stats, fmt, hostbad

WGT = 107544 / 3976
TW = {}
for l in open("/root/race/tweets.jsonl"):
    try:
        x = json.loads(l)
        TW[x["key"]] = x
    except Exception:
        pass
META = {}
for l in open("/root/nob/meta.jsonl"):
    try:
        x = json.loads(l)
        META[x["mint"]] = (x.get("j") or {})
    except Exception:
        pass
MON = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def joined_year(s):
    try:
        p = s.split()
        return int(p[-1]) + MON.get(p[1], 0) / 12
    except Exception:
        return None


def tweet_feats(r, j=None):
    j = META.get(r["mint"]) if j is None else j
    tw = str((j or {}).get("twitter") or "")
    m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,20})/status/(\d+)", tw)
    m2 = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,20})/?(?:\?|$)", tw)
    t = None
    if m:
        t = TW.get("s:" + m.group(2))
    elif m2:
        t = TW.get("u:" + m2.group(1).lower())
    f = {}
    f["tw_status"] = 1.0 if m else 0.0
    f["tw_profile"] = 1.0 if (m2 and not m) else 0.0
    ok = bool(t and t.get("ok"))
    f["tw_ok"] = 1.0 if ok else 0.0
    f["tw_dead"] = 1.0 if (t and not t.get("ok")) else 0.0
    fol = (t or {}).get("followers") if ok else None
    f["tw_logfol"] = math.log10(1 + fol) if fol is not None else 0.0
    f["tw_fol1k"] = 1.0 if (fol or 0) >= 1000 else 0.0
    f["tw_fol10k"] = 1.0 if (fol or 0) >= 10000 else 0.0
    f["tw_fol100k"] = 1.0 if (fol or 0) >= 100000 else 0.0
    f["tw_verified"] = 1.0 if ok and (t.get("verified") or t.get("vtype")) else 0.0
    jy = joined_year((t or {}).get("joined") or "") if ok else None
    f["tw_acct_old"] = 1.0 if (jy is not None and jy < 2024) else 0.0
    f["tw_acct_new"] = 1.0 if (jy is not None and jy >= 2026) else 0.0
    # tweet age at launch from the snowflake id (exact, no look-ahead)
    if m:
        ts = ((int(m.group(2)) >> 22) + 1288834974657) / 1000
        age = r.get("bt", 0) - ts if r.get("bt") else None
    else:
        age = None
    f["tw_age_lt5m"] = 1.0 if (age is not None and 0 <= age < 300) else 0.0
    f["tw_age_lt1h"] = 1.0 if (age is not None and 0 <= age < 3600) else 0.0
    f["tw_age_gt1d"] = 1.0 if (age is not None and age > 86400) else 0.0
    # engagement NOW (look-ahead; only in tier T+ for information)
    f["tw_loglikes_now"] = math.log10(1 + ((t or {}).get("likes") or 0)) if ok else 0.0
    f["tw_logviews_now"] = math.log10(1 + ((t or {}).get("views") or 0)) if ok else 0.0
    return f


HOSTS = ["ipfs.io", "metadata.j7tracker.io", "meta.uxento.io", "m.rapidlaunch.io", "gateway.pinata.cloud"]
TIPS = ["lunar", "jito", "helius_sender", "nozomi", "astralane"]


def feats(r, tiers):
    f = {}
    d = r["dev_sol"]
    f["log_dev"] = math.log(d)
    for t in (1, 2, 3, 5):
        f[f"dev>={t}"] = 1.0 if d >= t else 0.0
    f["dev_sized"] = 1.0 if r["dev_kind"] == "sized" else 0.0
    for h in HOSTS:
        f["host=" + h] = 1.0 if r.get("uri_host") == h else 0.0
    for tp in TIPS:
        f["tip=" + tp] = 1.0 if r.get("ctip_label") == tp else 0.0
    cu = r.get("cu_price") or 0
    f["log_cu"] = math.log10(1 + cu)
    f["nsig>=2"] = 1.0 if (r.get("nsig") or 0) >= 2 else 0.0
    f["mint_pump"] = 1.0 if r.get("mint_pump") else 0.0
    nl = r.get("n_len") or 0
    f["name<=8"] = 1.0 if nl <= 8 else 0.0
    f["name<=12"] = 1.0 if nl <= 12 else 0.0
    if "B" in tiers:
        g = r.get("glued") or 0
        f["bundle"] = 1.0 if g else 0.0
        f["bundle>=2"] = 1.0 if g >= 2 else 0.0
        f["log_gsol"] = math.log(1 + (r.get("gsol") or 0))
    if "C" in tiers:
        nlch = r.get("cr_nlaunch")
        f["cr_0launch"] = 1.0 if nlch == 0 else 0.0
        f["cr_serial"] = 1.0 if (nlch or 0) >= 5 else 0.0
        f["cr_idle30m"] = 1.0 if (r.get("cr_idle_s") or 0) >= 1800 else 0.0
        f["cr_logbal"] = math.log10(1 + (r.get("cpre_sol") or 0))
        f["cr_logprior"] = math.log10(1 + (r.get("cr_nprior") or 0))
    if "D" in tiers:
        f["has_tw"] = 1.0 if r.get("has_tw") else 0.0
        f["has_web"] = 1.0 if r.get("has_web") else 0.0
        f["socials>=2"] = 1.0 if (r.get("n_socials") or 0) >= 2 else 0.0
        f["community"] = 1.0 if r.get("has_community") else 0.0
        f["desc"] = 1.0 if (r.get("desc_len") or 0) > 20 else 0.0
    if "T" in tiers:
        tf = tweet_feats(r)
        for k, v in tf.items():
            if k.endswith("_now") and "T+" not in tiers:
                continue
            f[k] = v
    return f


def fit(X, y, w, l2=1.0, iters=300, lr=0.5):
    n, k = len(X), len(X[0])
    mu = [sum(x[j] * wi for x, wi in zip(X, w)) / sum(w) for j in range(k)]
    sd = [max(1e-6, math.sqrt(sum(((x[j] - mu[j]) ** 2) * wi for x, wi in zip(X, w)) / sum(w))) for j in range(k)]
    Z = [[(x[j] - mu[j]) / sd[j] for j in range(k)] for x in X]
    b = [0.0] * (k + 1)
    W = sum(w)
    # class balance: rescale positives so both classes carry equal total weight
    pw = sum(wi for wi, yi in zip(w, y) if yi)
    nw = W - pw
    cw = [wi * (0.5 / pw if yi else 0.5 / nw) for wi, yi in zip(w, y)]
    for it in range(iters):
        g = [0.0] * (k + 1)
        for z, yi, wi in zip(Z, y, cw):
            s = b[k] + sum(bj * zj for bj, zj in zip(b, z))
            p = 1 / (1 + math.exp(-max(-30, min(30, s))))
            e = (p - yi) * wi
            for j in range(k):
                g[j] += e * z[j]
            g[k] += e
        for j in range(k):
            b[j] -= lr * (g[j] + l2 * b[j] / n)
        b[k] -= lr * g[k]
    return b, mu, sd


def score(b, mu, sd, x):
    k = len(x)
    return b[k] + sum(b[j] * (x[j] - mu[j]) / sd[j] for j in range(k))


def auc(pos, neg, wneg):
    # weighted AUC: P(score_pos > score_neg)
    neg_sorted = sorted(neg)
    import bisect
    tot = 0.0
    for p in pos:
        tot += bisect.bisect_left(neg_sorted, p)
    return tot / (len(pos) * len(neg)) if pos and neg else float("nan")


def main():
    R = [json.loads(l) for l in open("/root/race/race_ds.jsonl")]
    U = [r for r in R if not r["quote"] and not r["mayhem"] and not hostbad(r.get("uri_host")) and 0.5 <= r["dev_sol"] <= 8]
    U.sort(key=lambda r: r["slot"])
    cut = U[int(len(U) * 0.6)]["slot"]
    print(f"universe (FIX filter): random rows {sum(r['in_rand'] for r in U)}, 4yFAz picks {sum(r['his'] for r in U)}; split at slot {cut}")
    print("his picks with an X link: status %d profile %d | random: status %d profile %d" % (
        sum(1 for r in U if r["his"] and tweet_feats(r)["tw_status"]), sum(1 for r in U if r["his"] and tweet_feats(r)["tw_profile"]),
        sum(1 for r in U if r["in_rand"] and not r["his"] and tweet_feats(r)["tw_status"]), sum(1 for r in U if r["in_rand"] and not r["his"] and tweet_feats(r)["tw_profile"])))
    # univariate view of the tweet features
    print("\n-- X/Twitter features: share among his picks vs random non-his launches (FIX universe)")
    tf_his = [tweet_feats(r) for r in U if r["his"]]
    tf_rnd = [tweet_feats(r) for r in U if r["in_rand"] and not r["his"]]
    for k in tf_his[0]:
        a = st.mean(x[k] for x in tf_his)
        c = st.mean(x[k] for x in tf_rnd)
        print(f"   {k:18} his {a:6.2f} | random {c:6.2f}")
    rows = [r for r in U if r["his"] or r["in_rand"]]
    res = {}
    for tiers in ("A", "AB", "ABC", "ABD", "ABT", "ABCDT", "ABCDT+"):
        keys = list(feats(rows[0], tiers).keys())
        X = [[feats(r, tiers)[k] for k in keys] for r in rows]
        y = [1 if r["his"] else 0 for r in rows]
        w = [1.0 if r["his"] else WGT for r in rows]
        tr = [i for i, r in enumerate(rows) if r["slot"] < cut]
        te = [i for i, r in enumerate(rows) if r["slot"] >= cut]
        b, mu, sd = fit([X[i] for i in tr], [y[i] for i in tr], [w[i] for i in tr])
        S = [score(b, mu, sd, x) for x in X]
        # thresholds from TRAIN: the score above which the top q of TRAIN random launches sit
        rnd_tr = sorted(S[i] for i in tr if not y[i])
        pos_te = [S[i] for i in te if y[i]]
        neg_te = [S[i] for i in te if not y[i]]
        a = auc(pos_te, neg_te, None)
        print(f"\n== tier {tiers}: TEST AUC {a:.3f} | top weights: " + ", ".join(f"{keys[j]} {b[j]:+.2f}" for j in sorted(range(len(keys)), key=lambda j: -abs(b[j]))[:10]))
        print(f"   {'top q of launches':18} | TEST his-prec | his-recall | race% (random) | fires/day | X1 avg/med/ex3/win (2 SOL realistic) | 3s avg/med/ex3")
        span_te_h = (rows[te[-1]]["slot"] - rows[te[0]]["slot"]) * 0.4 / 3600
        for q in (0.30, 0.15, 0.08, 0.04, 0.02):
            thr = rnd_tr[int(len(rnd_tr) * (1 - q))]
            sel_r = [rows[i] for i in te if not y[i] and S[i] >= thr] + [rows[i] for i in te if y[i] and rows[i]["in_rand"] and S[i] >= thr]
            sel_h = [rows[i] for i in te if y[i] and S[i] >= thr]
            n_rand_sel = sum(1 for i in te if rows[i]["in_rand"] and S[i] >= thr)
            hp = len(sel_h) / (n_rand_sel * WGT) if n_rand_sel else float("nan")
            hr = len(sel_h) / max(1, sum(y[i] for i in te))
            rr = [rows[i] for i in te if rows[i]["in_rand"] and S[i] >= thr and rows[i]["has_path"]]
            race = sum(1 for r in rr if r["out2s_nx"] >= 3 and r["out2s_solx"] >= 3) / max(1, len(rr))
            x1 = stats([sim(r, EXITS["time 1s"]) for r in rr])
            x3 = stats([sim(r, EXITS["time 3s"]) for r in rr])
            print(f"   top {q:4.0%} (n={n_rand_sel:3}) | {hp:12.1%} | {hr:9.0%} | {race:13.0%} | {n_rand_sel * WGT / span_te_h * 24:8.0f} | {x1['avg']:+.1%}/{x1['med']:+.1%}/{x1['ex3']:+.1%}/{x1['win']:.0%} | {x3['avg']:+.1%}/{x3['med']:+.1%}/{x3['ex3']:+.1%}")
        res[tiers] = (keys, b, mu, sd, cut)
    json.dump({k: {"keys": v[0], "b": v[1], "mu": v[2], "sd": v[3]} for k, v in res.items()}, open("/root/race/his_model.json", "w"))
    print("\n(base rates in TEST: his-prec of the whole FIX universe ~2%; race ~20%)")


if __name__ == "__main__":
    main()
