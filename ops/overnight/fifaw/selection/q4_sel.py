#!/usr/bin/env python3
# READ-ONLY, offline. Q4: what FiFawH attempts (snipes), vs the launches it skips. Population = feature-table launches in
# its attempt window (sel_dataset.jsonl.gz from s1_build.py). Univariate attempt rates, then a simple rule search.
import json, gzip, collections, datetime, statistics as stt, math
R = [json.loads(l) for l in gzip.open("sel_dataset.jsonl.gz", "rt")]
PKT = datetime.timezone(datetime.timedelta(hours=5))
for r in R:
    r["hour_pkt"] = datetime.datetime.fromtimestamp(r["bt"], PKT).hour
    r["db"] = r.get("dev_buy") or 0.0
N = len(R); NA = sum(r["att"] for r in R); base = NA / N
print(f"population {N} launches in window, attempted {NA} ({base:.2%}); filled {sum(1 for r in R if r['att_filled'])}; snipe (<=5 slots) {sum(r['snipe'] for r in R)}")
def tab(name, key, order=None, minn=30):
    g = collections.defaultdict(lambda: [0, 0])
    for r in R:
        k = key(r); g[k][0] += 1; g[k][1] += r["att"]
    ks = order or sorted(g, key=lambda k: -g[k][1])
    rows = [(k, g[k][0], g[k][1], g[k][1] / g[k][0]) for k in ks if k in g and (g[k][0] >= minn or g[k][1] >= 5)]
    print(f"\n{name}: (value, launches, attempts, rate, lift)")
    for k, n, a, rt in rows[:14]: print(f"   {str(k)[:40]:40} {n:6} {a:4} {rt:7.2%} x{rt / base:5.1f}")
    return g
def bk(v, edges):
    if v is None: return "None"
    for e in edges:
        if v < e: return f"<{e}"
    return f">={edges[-1]}"
tab("quote_sol", lambda r: r["quote_sol"]); tab("mayhem", lambda r: r["mayhem"])
tab("dev buy SOL", lambda r: bk(r["db"], [0.01, 0.5, 1, 2, 3, 5, 8, 12, 20]), order=["<0.01", "<0.5", "<1", "<2", "<3", "<5", "<8", "<12", "<20", ">=20"])
tab("glued bundle txs", lambda r: min(r.get("glued_n") or 0, 5), order=[0, 1, 2, 3, 4, 5])
tab("glued SOL", lambda r: bk(r.get("glued_sol") or 0, [0.01, 1, 3, 6, 10]), order=["<0.01", "<1", "<3", "<6", "<10", ">=10"])
tab("create variant", lambda r: r.get("create_variant")); tab("created_on", lambda r: r.get("created_on"))
tab("uri host", lambda r: r.get("uri_host")); tab("has twitter/tg/web", lambda r: (r.get("has_tw"), r.get("has_tg"), r.get("has_web")))
tab("payer is creator", lambda r: r.get("payer_is_creator")); tab("signer is creator", lambda r: r.get("signer_is_creator"))
tab("create fingerprint (cu price|cu limit|tips)", lambda r: r.get("fp"))
tab("create tips", lambda r: bk(r.get("create_tips") or 0, [1e-9, 0.001, 0.01, 0.05]), order=["<1e-09", "<0.001", "<0.01", "<0.05", ">=0.05"])
tab("hour PKT", lambda r: r["hour_pkt"], order=list(range(24)))
tab("deployer prior launches (collector)", lambda r: bk(r.get("dep_prior"), [1, 2, 5, 20]), order=["<1", "<2", "<5", "<20", ">=20"])
tab("deployer prior FiFawH attempts", lambda r: bk(r.get("dep_prior_att"), [1, 2, 5]), order=["<1", "<2", "<5", ">=5"])
tab("creator prior creates (feature table cr_prior_n)", lambda r: bk(r.get("cr_prior_n"), [1, 2, 5, 20, 100]), order=["<1", "<2", "<5", "<20", "<100", ">=100"])
tab("creator wallet age", lambda r: bk(r.get("cr_age_s"), [600, 3600, 86400, 7 * 86400]), order=["None", "<600", "<3600", "<86400", "<604800", ">=604800"])
tab("meta keys", lambda r: r.get("meta_keys")); tab("show_name", lambda r: r.get("show_name"))
tab("name all-caps", lambda r: r.get("name_upper")); tab("description length", lambda r: bk(r.get("desc_len"), [1, 50, 200]), order=["None", "<1", "<50", "<200", ">=200"])
tab("tw_status", lambda r: r.get("tw_status")); tab("tw_community", lambda r: r.get("tw_community"))
tab("heat (launches in last 10 min)", lambda r: bk(r.get("heat_launches_10m"), [200, 300, 400]), order=["<200", "<300", "<400", ">=400"])
tab("dev share of first-slot buys", lambda r: bk(r.get("dev_share"), [0.25, 0.5, 0.9, 0.999]), order=["None", "<0.25", "<0.5", "<0.9", "<0.999", ">=0.999"])
# ---- rule search: conjunctions of up to 2 thresholds on numeric features + quote/mayhem filters, ranked by F1 on R1, tested on R2
FEATS = {"dev_buy>=": lambda r, t: r["db"] >= t, "glued_n<=": lambda r, t: (r.get("glued_n") or 0) <= t, "glued_sol<=": lambda r, t: (r.get("glued_sol") or 0) <= t,
         "create_tips>=": lambda r, t: (r.get("create_tips") or 0) >= t, "cr_prior_n>=": lambda r, t: (r.get("cr_prior_n") or 0) >= t,
         "dep_prior_att>=": lambda r, t: (r.get("dep_prior_att") or 0) >= t, "has_tw==": lambda r, t: (r.get("has_tw") or 0) == t,
         "quote_sol==": lambda r, t: (r.get("quote_sol") or 0) == t, "mayhem==": lambda r, t: (r.get("mayhem") or 0) == t,
         "cr_age_s>=": lambda r, t: (r.get("cr_age_s") or 0) >= t, "dev_share>=": lambda r, t: (r.get("dev_share") or 0) >= t}
TH = {"dev_buy>=": [0.5, 1, 1.5, 2, 3, 4, 5, 6, 8, 10], "glued_n<=": [0, 1, 2], "glued_sol<=": [0.01, 1, 3], "create_tips>=": [0.0001, 0.001, 0.005],
      "cr_prior_n>=": [1, 2, 5], "dep_prior_att>=": [1, 2], "has_tw==": [0, 1], "quote_sol==": [0, 1], "mayhem==": [0], "cr_age_s>=": [3600, 86400], "dev_share>=": [0.5, 0.9, 0.999]}
conds = [(f, t) for f in FEATS for t in TH[f]]
def score(rows, cs):
    sel = [r for r in rows if all(FEATS[f](r, t) for f, t in cs)]
    a = sum(r["att"] for r in sel); A_ = sum(r["att"] for r in rows)
    p = a / len(sel) if sel else 0; rc = a / A_ if A_ else 0
    return dict(n=len(sel), a=a, prec=p, rec=rc, f1=2 * p * rc / (p + rc) if p + rc else 0)
R1 = [r for r in R if r["run"] == "R1"]; R2 = [r for r in R if r["run"] == "R2"]
res = []
for i, c1 in enumerate(conds):
    for c2 in [None] + conds[i + 1:]:
        cs = [c1] + ([c2] if c2 else [])
        if c2 and c2[0] == c1[0]: continue
        for c3 in [None, ("quote_sol==", 1)]:
            cc = cs + ([c3] if c3 and c3 not in cs else [])
            res.append((score(R1, cc)["f1"], cc))
res.sort(key=lambda x: -x[0])
print("\nrule search (trained on R1 by F1 of predicting FiFawH attempts; tested on R2):")
out = []
for f1, cc in res[:12]:
    s1 = score(R1, cc); s2 = score(R2, cc)
    print(f"   {' & '.join(f'{f}{t}' for f, t in cc):60} R1 n={s1['n']:5} prec {s1['prec']:.1%} rec {s1['rec']:.0%} | R2 n={s2['n']:5} prec {s2['prec']:.1%} rec {s2['rec']:.0%}")
    out.append(dict(rule=cc, R1=s1, R2=s2))
res2 = sorted(((score(R2, cc)["f1"], cc) for _, cc in res), key=lambda x: -x[0])
print("reverse (trained on R2, tested on R1):")
for f1, cc in res2[:6]:
    s1 = score(R1, cc); s2 = score(R2, cc)
    print(f"   {' & '.join(f'{f}{t}' for f, t in cc):60} R2 n={s2['n']:5} prec {s2['prec']:.1%} rec {s2['rec']:.0%} | R1 n={s1['n']:5} prec {s1['prec']:.1%} rec {s1['rec']:.0%}")
json.dump(dict(base=base, top_R1=out, top_R2=[dict(rule=cc, R1=score(R1, cc), R2=score(R2, cc)) for _, cc in res2[:6]]), open("q4_rules.json", "w"))
