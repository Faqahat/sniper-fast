#!/usr/bin/env python3
# READ-ONLY, offline. Generic create-time rules that imitate FiFawH's picks WITHOUT using FiFawH's own history:
# features known at the create (table): quote, mayhem, dev buy, glued bundle, signer!=creator, deployer prior launches,
# create fingerprint (learned on the TRAIN run only), metadata host, socials. Train on R1 -> test on R2, and the reverse.
# Writes ../copy/sets.json with the trading sets used by the copyability engine.
import json, gzip, collections, random, sys
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core"); import rp
R = [json.loads(l) for l in gzip.open("sel_dataset.jsonl.gz", "rt")]
for r in R: r["db"] = r.get("dev_buy") or 0.0
def fps_learn(rows, min_att=3, min_lift=4.0):
    base = sum(r["att"] for r in rows) / len(rows); g = collections.defaultdict(lambda: [0, 0])
    for r in rows: g[r.get("fp")][0] += 1; g[r.get("fp")][1] += r["att"]
    return {k for k, (n, a) in g.items() if a >= min_att and a / n >= min_lift * base}
def hosts_learn(rows, min_att=3, min_lift=1.3):
    base = sum(r["att"] for r in rows) / len(rows); g = collections.defaultdict(lambda: [0, 0])
    for r in rows: g[r.get("uri_host")][0] += 1; g[r.get("uri_host")][1] += r["att"]
    return {k for k, (n, a) in g.items() if a >= min_att and a / n >= min_lift * base}
CONDS = {
    "sol": lambda r, ctx: r.get("quote_sol") == 1, "nomay": lambda r, ctx: not r.get("mayhem"),
    "fp": lambda r, ctx: r.get("fp") in ctx["fps"], "host": lambda r, ctx: r.get("uri_host") in ctx["hosts"],
    "signer!=creator": lambda r, ctx: r.get("signer_is_creator") == 0, "fresh_dep(<2 prior)": lambda r, ctx: (r.get("dep_prior") or 0) < 2,
    "not_serial(<20 prior)": lambda r, ctx: (r.get("dep_prior") or 0) < 20, "glued<=1": lambda r, ctx: (r.get("glued_n") or 0) <= 1,
    "dev1-3": lambda r, ctx: 1 <= r["db"] < 3, "dev>=1": lambda r, ctx: r["db"] >= 1, "tw": lambda r, ctx: r.get("has_tw") == 1,
    "pumpfun_site": lambda r, ctx: r.get("created_on") == "https://pump.fun", "show_name": lambda r, ctx: r.get("show_name") is True}
def evalr(rows, conj, ctx):
    sel = [r for r in rows if all(CONDS[c](r, ctx) for c in conj)]
    a = sum(r["att"] for r in sel); A = sum(r["att"] for r in rows)
    p = a / len(sel) if sel else 0.0; rc = a / A if A else 0.0
    return dict(n=len(sel), att=a, prec=round(p, 4), rec=round(rc, 3), f1=2 * p * rc / (p + rc) if p + rc else 0.0), sel
names = list(CONDS)
out = {}
for tr_run, te_run in (("R1", "R2"), ("R2", "R1")):
    TR = [r for r in R if r["run"] == tr_run]; TE = [r for r in R if r["run"] == te_run]
    ctx = dict(fps=fps_learn(TR), hosts=hosts_learn(TR))
    best = []
    for i in range(len(names)):
        for j in range(i, len(names)):
            for k in range(j, len(names)):
                conj = sorted({names[i], names[j], names[k], "nomay"})
                s, _ = evalr(TR, conj, ctx)
                if s["n"] >= 40: best.append((s["f1"], tuple(conj)))
    best = sorted(set(best), key=lambda x: -x[0])[:5]
    print(f"\ntrain {tr_run} -> test {te_run} | learned fingerprints {sorted(ctx['fps'])} | hosts {sorted(ctx['hosts'])}")
    for f1, conj in best:
        s1, _ = evalr(TR, conj, ctx); s2, sel = evalr(TE, conj, ctx)
        print(f"   {' & '.join(conj):70} train n={s1['n']:5} prec {s1['prec']:.1%} rec {s1['rec']:.0%} | test n={s2['n']:5} prec {s2['prec']:.1%} rec {s2['rec']:.0%}")
    f1, conj = best[0]
    _, sel_te = evalr(TE, conj, ctx)
    out[f"(c) generic rule trained on {tr_run}, traded on {te_run}"] = dict(rule=list(conj), fps=sorted(ctx["fps"]), hosts=sorted(ctx["hosts"]), mints=[r["mint"] for r in sel_te])
# ---- trading sets for the engine
L = rp.load_launches(); A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts_fifaw.json"))
def wf_list(rate=0.10, k=2):
    ev = []
    for m, c in L.items():
        if not c.get("bt"): continue
        ev.append((c["bt"], c["user"], 0))
        if "FiFawH" in A.get(m, {}): ev.append((c["bt"], c["user"], 1))
    ev.sort(); na = collections.Counter(); nl = collections.Counter(); j = 0; keep = []
    for bt, m in sorted((c["bt"], m) for m, c in L.items() if c.get("bt")):
        while j < len(ev) and ev[j][0] < bt:
            _, d, a = ev[j]; (na if a else nl)[d] += 1; j += 1
        d = L[m]["user"]
        if na[d] >= k and (nl[d] == 0 or na[d] / nl[d] >= rate): keep.append(m)
    return keep
sets = {"(a) oracle: its attempts": sorted(A), "(a') oracle: its filled buys": sorted(m for m, v in A.items() if v["FiFawH"][0] == 1),
        "(b) walk-forward deployer list (>=2 att, >=10%)": wf_list()}
for k, v in out.items(): sets[k] = v["mints"]
win = [r["mint"] for r in R]; random.seed(11)
sets["(z) random control launches"] = random.sample([m for m in win if m not in A], 3000)
json.dump(dict(sets=sets, rules=out), open("../copy/sets.json", "w"))
print({k: len(v) for k, v in sets.items()})
