#!/usr/bin/env python3
# READ-ONLY, offline: what predicts dKMjeG's attempts (filled or failed) among all collected launches (R1 + R2),
# using only create-time features (table_dump) + the deployer's history in our data (walk-forward counts).
import json, gzip, collections, math, statistics as S
import numpy as np
C = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/coll.json"))
T = {}
for l in gzip.open("/home/moiz/sniper-data/collect/paper/table_dump.jsonl.gz", "rt"):
    r = json.loads(l)
    if r["mint"] in C: T[r["mint"]] = r
rows = []
for m, c in C.items():
    t = T.get(m)
    if not t or c["mayhem"]: continue
    rows.append((m, c, t))
rows.sort(key=lambda x: x[2]["bt"] or 0)
# walk-forward deployer history: launches by this deployer before, and how many dK attempted
nl = collections.Counter(); na = collections.Counter(); last_bt = {}
for m, c, t in rows:
    d = c["dep"]; t["dep_prev_n"] = nl[d]; t["dep_prev_att"] = na[d]
    t["dep_gap_min"] = (t["bt"] - last_bt[d]) / 60 if d in last_bt else None
    nl[d] += 1; last_bt[d] = t["bt"]
    if "dk" in c: na[d] += 1
A = lambda c: 1 if "dk" in c else 0
F = lambda c: 1 if ("dk" in c and "bslot" in c["dk"]) else 0
N = len(rows); na_ = sum(A(c) for _, c, _ in rows)
print(f"universe (non-mayhem launches with features): {N}; dK attempted {na_} ({na_ / N:.1%}); filled {sum(F(c) for _, c, _ in rows)}")
def auc(xs, ys):
    pairs = sorted(zip(xs, ys)); n1 = sum(ys); n0 = len(ys) - n1
    if not n1 or not n0: return None
    # rank-sum with ties
    r = 0; i = 0; rk = [0] * len(pairs)
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]: j += 1
        for k in range(i, j): rk[k] = (i + j + 1) / 2
        i = j
    s1 = sum(rk[k] for k in range(len(pairs)) if pairs[k][1])
    return (s1 - n1 * (n1 + 1) / 2) / (n1 * n0)
def num(name, fx, bins):
    xs, ys = [], []
    for m, c, t in rows:
        v = fx(c, t)
        if v is None: continue
        xs.append(v); ys.append(A(c))
    a = auc(xs, ys)
    cells = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        sel = [y for x, y in zip(xs, ys) if lo <= x < hi]
        if sel: cells.append(f"[{lo},{hi}) {sum(sel)}/{len(sel)}={sum(sel) / len(sel):.1%}")
    print(f"{name:26} AUC {a:.3f} n={len(xs)} | " + " | ".join(cells))
def cat(name, fx, top=10):
    g = collections.defaultdict(list)
    for m, c, t in rows: g[fx(c, t)].append(A(c))
    items = sorted(g.items(), key=lambda kv: -len(kv[1]))[:top]
    print(f"{name:26} " + " | ".join(f"{str(k)[:28]} {sum(v)}/{len(v)}={sum(v) / len(v):.1%}" for k, v in items))
inf = float("inf")
num("dev buy SOL", lambda c, t: t.get("dev_buy"), [0, 0.01, 0.5, 1, 2, 3, 5, 10, inf])
num("glued bundle txs", lambda c, t: t.get("glued_n"), [0, 1, 2, 3, 5, 10, inf])
num("glued bundle SOL", lambda c, t: t.get("glued_sol"), [0, 0.01, 1, 3, 6, 10, 20, inf])
num("glued wallets", lambda c, t: t.get("glued_wallets"), [0, 1, 2, 3, 5, 10, inf])
num("dev+bundle SOL", lambda c, t: (t.get("dev_buy") or 0) + (t.get("glued_sol") or 0), [0, 0.5, 1, 2, 3, 5, 8, 12, 20, inf])
num("MC after bundle (SOL)", lambda c, t: t.get("P0_mc_sol"), [0, 28, 30, 32, 35, 40, 50, 80, inf])
num("create priority (cup)", lambda c, t: t.get("create_cup"), [0, 1, 1e5, 1e6, 1e7, inf])
num("create tips SOL", lambda c, t: t.get("create_tips"), [0, 1e-6, 1e-3, 0.01, 0.05, inf])
num("hour UTC", lambda c, t: t.get("hour_utc"), list(range(0, 25, 3)))
num("creator prior creates", lambda c, t: t.get("cr_prior_n"), [0, 1, 2, 5, 20, 100, inf])
num("creator age (h)", lambda c, t: (t["cr_age_s"] / 3600) if t.get("cr_age_s") is not None else None, [0, 0.1, 1, 6, 24, 24 * 7, inf])
num("creator min since prev create", lambda c, t: t.get("cr_min_since_prev_create"), [0, 1, 5, 15, 60, 600, inf])
num("deployer prev launches (ours)", lambda c, t: t["dep_prev_n"], [0, 1, 2, 5, 20, inf])
num("deployer prev dK attempts", lambda c, t: t["dep_prev_att"], [0, 1, 2, 5, inf])
num("fund amount SOL", lambda c, t: t.get("fund_amt"), [0, 0.1, 1, 3, 10, 50, inf])
num("desc length", lambda c, t: t.get("desc_len"), [0, 1, 20, 100, 300, inf])
num("name length", lambda c, t: t.get("name_len"), [0, 4, 8, 12, 20, inf])
num("launches last 10 min", lambda c, t: t.get("heat_launches_10m"), [0, 40, 60, 80, 100, 130, inf])
cat("has twitter", lambda c, t: t.get("has_tw"))
cat("tw status/community", lambda c, t: (t.get("tw_status"), t.get("tw_community")))
cat("has website", lambda c, t: t.get("has_web"))
cat("has telegram", lambda c, t: t.get("has_tg"))
cat("created_on", lambda c, t: t.get("created_on"), 8)
cat("uri host", lambda c, t: t.get("uri_host"), 8)
cat("img host", lambda c, t: (t.get("img_host") or "")[-18:], 6)
cat("payer is creator", lambda c, t: t.get("payer_is_creator"))
cat("glued payer is creator", lambda c, t: t.get("glued_payer_is_creator"))
cat("create variant", lambda c, t: t.get("create_variant"))
cat("quote", lambda c, t: (t.get("quote_sol"), c["solq"]))
cat("same name before", lambda c, t: min(t.get("cr_same_name_before") or 0, 1))
cat("wave name 60m", lambda c, t: min(t.get("wave_name_60m") or 0, 2))
cat("web host = x.com/twitter", lambda c, t: ("x.com" in (t.get("web_host") or "") or "twitter" in (t.get("web_host") or "")))
json.dump([dict(m=m, att=A(c), fill=F(c), run=c["run"], bt=t["bt"], **{k: t.get(k) for k in ("dev_buy", "glued_n", "glued_sol", "glued_wallets", "P0_mc_sol", "create_cup", "create_tips", "hour_utc", "cr_prior_n", "cr_age_s", "cr_min_since_prev_create", "fund_amt", "desc_len", "has_tw", "has_web", "has_tg", "tw_status", "tw_community", "created_on", "uri_host", "payer_is_creator", "dep_prev_n", "dep_prev_att", "heat_launches_10m", "quote_sol", "name", "symbol", "creator", "web_host", "img_host", "name_len", "meta_keys")}) for m, c, t in rows], open("/home/moiz/sniper/ops/overnight/dkmjeg/sel_rows.json", "w"))
