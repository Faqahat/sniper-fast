#!/usr/bin/env python3
# READ-ONLY, offline: what CWiNFA attempts vs skips (question 4). Universe = SOL-quoted, non-mayhem launches in the feature
# table (R1 10-21 22:07 -> 10-22 13:00, R2 10-22 15:43 -> 10-23 00:36). Attempt = a filled buy or a failed tx of CWiNFA on
# the launch (collector rows). Only CREATE-TIME features are used as predictors (its decision is made ~50 ms after the
# create); post-create flow features include its own buy and are shown as outcomes only.
import os, sys, json, collections, statistics, math
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches()
T = [x for x in json.load(open(os.path.join(HERE, "table_slim.json"))) if x["quote_sol"] == 1 and x["mayhem"] == 0]
C = json.load(open(os.path.join(HERE, "coll_cw.json")))
for x in T:
    c = L.get(x["mint"], {}); x["dep"] = c.get("user") or x["payer"]; x["run"] = c.get("run")
    x["sz"] = (C.get(x["mint"], {}).get("buy") or {}).get("sol")
N = len(T); NA = sum(x["att"] for x in T)
out = []
P = lambda *a: out.append(" ".join(str(z) for z in a))
P(f"universe: {N} SOL-quoted non-mayhem launches, attempted {NA} ({NA / N:.2%})")
# ---- deployer concentration
byd = collections.defaultdict(list)
for x in sorted(T, key=lambda x: x["bt"]): byd[x["dep"]].append(x)
ad = {d: v for d, v in byd.items() if any(x["att"] for x in v)}
P(f"deployers: {len(byd)} total, {len(ad)} with >= 1 attempt")
cov = sorted(((sum(x['att'] for x in v), len(v), d) for d, v in ad.items()), reverse=True)
P("top deployers by attempts (attempted / launches in window):", [(d[:8], a, n) for a, n, d in cov[:15]])
tot_att_top10 = sum(a for a, n, d in cov[:10]); P(f"top-10 deployers carry {tot_att_top10}/{NA} attempts ({tot_att_top10 / NA:.0%})")
rates = [a / n for a, n, d in cov if n >= 5]
P(f"coverage of a deployer's launches (deployers with >= 5 launches and >= 1 attempt, n={len(rates)}): median {statistics.median(rates):.0%}, "
  f"share with >= 80% covered: {sum(r >= 0.8 for r in rates) / len(rates):.0%}, <= 30%: {sum(r <= 0.3 for r in rates) / len(rates):.0%}")
# walk-forward: was the deployer already attempted before (in window)?
seen = set(); first = 0; rep = 0; after_first_launches = 0; after_first_att = 0
for x in sorted(T, key=lambda x: x["bt"]):
    if x["dep"] in seen:
        after_first_launches += 1; after_first_att += x["att"]
        if x["att"]: rep += 1
    elif x["att"]: first += 1
    if x["att"]: seen.add(x["dep"])
P(f"attempts on a deployer it had attempted before: {rep}/{NA} ({rep / NA:.0%}); first-time deployers: {first}. "
  f"After its first attempt on a deployer it attempts {after_first_att}/{after_first_launches} ({after_first_att / max(1, after_first_launches):.0%}) of that deployer's later launches")
# ---- univariate create-time features
def rate_by(name, f, order=None):
    g = collections.defaultdict(lambda: [0, 0])
    for x in T:
        k = f(x); g[k][0] += 1; g[k][1] += x["att"]
    ks = order or sorted(g, key=lambda k: str(k))
    P(f"  by {name}: " + " | ".join(f"{k}: {g[k][1]}/{g[k][0]} ({g[k][1] / g[k][0]:.1%})" for k in ks if k in g))
P("attempt rate by create-time feature:")
rate_by("dev buy SOL", lambda x: "0" if not x["dev_buy"] else ("<0.5" if x["dev_buy"] < 0.5 else ("0.5-1.5" if x["dev_buy"] < 1.5 else ("1.5-2.5" if x["dev_buy"] < 2.5 else ("2.5-3.5" if x["dev_buy"] < 3.5 else ("3.5-5" if x["dev_buy"] < 5 else "5+"))))),
        ["0", "<0.5", "0.5-1.5", "1.5-2.5", "2.5-3.5", "3.5-5", "5+"])
rate_by("glued bundle txs", lambda x: min(x["glued_n"] or 0, 6))
rate_by("glued SOL", lambda x: "0" if not x["glued_sol"] else ("<1" if x["glued_sol"] < 1 else ("1-2.5" if x["glued_sol"] < 2.5 else ("2.5-4" if x["glued_sol"] < 4 else ("4-8" if x["glued_sol"] < 8 else "8+")))),
        ["0", "<1", "1-2.5", "2.5-4", "4-8", "8+"])
rate_by("X link", lambda x: x["has_tw"]); rate_by("website", lambda x: x["has_web"]); rate_by("telegram", lambda x: x["has_tg"])
rate_by("created_on", lambda x: (x["created_on"] or "-")[:24])
rate_by("uri host", lambda x: (x["uri_host"] or "-")[:28])
rate_by("hour UTC", lambda x: x["hour_utc"], list(range(24)))
rate_by("create tx tip", lambda x: "none" if not x["create_tips"] else ("<0.002" if x["create_tips"] < 0.002 else ("0.002-0.005" if x["create_tips"] < 0.005 else ">=0.005")), ["none", "<0.002", "0.002-0.005", ">=0.005"])
rate_by("deployer launches before (feature h_cr_n)", lambda x: "0" if not x["h_cr_n"] else ("1-2" if x["h_cr_n"] <= 2 else ("3-10" if x["h_cr_n"] <= 10 else ("11-50" if x["h_cr_n"] <= 50 else "50+"))), ["0", "1-2", "3-10", "11-50", "50+"])
rate_by("min since deployer's previous create", lambda x: "first" if x["cr_min_since_prev_create"] is None else ("<2" if x["cr_min_since_prev_create"] < 2 else ("2-5" if x["cr_min_since_prev_create"] < 5 else ("5-15" if x["cr_min_since_prev_create"] < 15 else ("15-60" if x["cr_min_since_prev_create"] < 60 else "60+")))),
        ["first", "<2", "2-5", "5-15", "15-60", "60+"])
rate_by("description length", lambda x: "0" if not x["desc_len"] else ("1-50" if x["desc_len"] <= 50 else "51+"), ["0", "1-50", "51+"])
rate_by("payer is creator", lambda x: x["payer_is_creator"])
# ---- the simple rule that reproduces most of its attempts
def rule(x): return (x["dev_buy"] or 0) >= 1 and (x["glued_n"] or 0) >= 1
r_n = sum(rule(x) for x in T); r_a = sum(rule(x) and x["att"] for x in T)
P(f"rule 'dev buy >= 1 SOL and >= 1 glued bundle tx': {r_n} launches, covers {r_a}/{NA} attempts ({r_a / NA:.0%}), precision {r_a / r_n:.1%}")
def rule2(x): return 2.5 <= (x["dev_buy"] or 0) < 3.5 and (x["glued_n"] or 0) >= 2
r_n = sum(rule2(x) for x in T); r_a = sum(rule2(x) and x["att"] for x in T)
P(f"rule 'dev buy 2.5-3.5 SOL and >= 2 glued txs': {r_n} launches, covers {r_a}/{NA} ({r_a / NA:.0%}), precision {r_a / r_n:.1%}")
# within the rule-1 pool: what separates attempts from skips (create-time)
pool = [x for x in T if rule(x)]
def cmp(name, f):
    a = [f(x) for x in pool if x["att"] and f(x) is not None]; b = [f(x) for x in pool if not x["att"] and f(x) is not None]
    if a and b: P(f"  {name:38} attempted med {statistics.median(a):.3g} (n {len(a)}) | skipped med {statistics.median(b):.3g} (n {len(b)})")
P("inside the 'dev >= 1 SOL + bundle' pool, attempted vs skipped (create-time):")
for k in ("dev_buy", "glued_n", "glued_sol", "glued_wallets", "h_cr_n", "h_cr_wins", "cr_min_since_prev_create", "cr_recent_creates", "cr_age_s", "fund_amt", "create_tips", "create_cup", "name_len", "desc_len", "has_tw", "has_web", "hour_utc"):
    cmp(k, lambda x, k=k: x.get(k))
# ---- are its picks better? outcomes measured from the post-bundle price (no fees, no placement): px_2s / px_10s / px_60s ratio, peak 10 min, y_good
P("outcomes (post-bundle price based, all launches / same pool skipped / its attempts):")
for k in ("px_2s", "px_5s", "px_10s", "px_30s", "px_60s", "peak_10m", "y_good", "y_dump5", "E_bundle_h2s", "E_k1_h2s"):
    a = [x[k] for x in T if x["att"] and x[k] is not None]; s = [x[k] for x in pool if not x["att"] and x[k] is not None]; u = [x[k] for x in T if x[k] is not None]
    P(f"  {k:13} all med {statistics.median(u):.3f} mean {statistics.mean(u):.3f} | pool-skipped med {statistics.median(s):.3f} mean {statistics.mean(s):.3f} | attempted med {statistics.median(a):.3f} mean {statistics.mean(a):.3f}")
# same deployers' skipped launches
sd = [x for x in T if x["dep"] in ad and not x["att"]]
for k in ("px_2s", "px_10s", "px_60s", "peak_10m", "y_good", "E_bundle_h2s"):
    a = [x[k] for x in T if x["att"] and x[k] is not None]; s = [x[k] for x in sd if x[k] is not None]
    P(f"  same deployers, skipped launches: {k:12} med {statistics.median(s):.3f} mean {statistics.mean(s):.3f} (n {len(s)}) vs attempted med {statistics.median(a):.3f} mean {statistics.mean(a):.3f}")
# ---- size
P("its buy size (curve SOL) on attempted launches:", collections.Counter(round(x["sz"], 4) for x in T if x["sz"]).most_common(4))
open(os.path.join(HERE, "sel.txt"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
