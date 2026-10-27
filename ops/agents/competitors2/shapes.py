#!/usr/bin/env python3
# competitors2/shapes.py -- READ-ONLY. Per-wallet summary of the RPC-decoded transaction shapes (txshape.jsonl): size, version,
# durable nonce, lookup tables, loaded-data limit, CU limit vs used, cost units, tips written in the message (also visible in
# FAILED txs, where the transfer reverted), the instruction pattern, example signatures. Out: shapes.json + printed table.
import json, collections, statistics
D2 = "/home/moiz/sniper-data/competitors2"
T = [json.loads(l) for l in open(f"{D2}/txshape.jsonl")]
T = list({t["sig"]: t for t in T if "size" in t}.values())
by = collections.defaultdict(list)
for t in T: by[t["signers"][0]].append(t)
def med(x): x = [v for v in x if v is not None]; return statistics.median(x) if x else None
def cul(t): return t["cb"].get("cul") or (t["cb"].get("v1config") or {}).get("computeUnitLimit")
def ldl(t): return t["cb"].get("ldl") or (t["cb"].get("v1config") or {}).get("loadedAccountsDataSizeLimit")
def cup(t):
    if "cup" in t["cb"]: return t["cb"]["cup"]
    v = t["cb"].get("v1config")
    if v and v.get("priorityFee") is not None and v.get("computeUnitLimit"): return v["priorityFee"] * 1_000_000 // v["computeUnitLimit"]
    return 0
def pat(t):
    out = []
    for x in t["ixs"]:
        p, _, k = x.partition(":")
        out.append(f"{p}:{k}" if p in ("system", "computebudget") else p)
    return " ".join(out)
out = {}
for w, L in sorted(by.items(), key=lambda x: -len(x[1])):
    if len(L) < 4: continue
    ok = [t for t in L if not t["err"]]; fl = [t for t in L if t["err"]]
    o = dict(n=len(L), n_ok=len(ok), n_fail=len(fl), size_med=med([t["size"] for t in L]), size_min=min(t["size"] for t in L), size_max=max(t["size"] for t in L),
             ver=dict(collections.Counter(t["ver"] for t in L)), nonce=sum(t["nonce"] for t in L), nonce_accts=len({t["nonce_acct"] for t in L if t["nonce"]}),
             alt=sum(1 for t in L if t["nalt"]), ldl=dict(collections.Counter(ldl(t) for t in L).most_common(3)),
             cul_med=med([cul(t) for t in L]), cu_med_ok=med([t["cu"] for t in ok]), cul_over_cu_ok=med([cul(t) / t["cu"] for t in ok if cul(t) and t["cu"]]),
             cup_med=med([cup(t) for t in L]), cost_med_ok=med([t.get("cost") for t in ok]), fee_med=med([t["fee"] for t in L]),
             tips_per_tx=dict(collections.Counter(len(t["tips"]) for t in L)), tip_relays_all=dict(collections.Counter(x[0] for t in L for x in t["tips"]).most_common(8)),
             tip_relays_failed=dict(collections.Counter(x[0] for t in fl for x in t["tips"]).most_common(6)),
             untipped_ok=sum(1 for t in ok if not t["tips"]), tip_lamports_med={r: med([x[1] for t in L for x in t["tips"] if x[0] == r]) for r in {x[0] for t in L for x in t["tips"]}},
             patterns=dict(collections.Counter(pat(t) for t in L).most_common(3)), errs=dict(collections.Counter(json.dumps(t["err"])[:60] for t in fl).most_common(3)),
             ex_ok=[t["sig"] for t in ok[:2]], ex_fail=[t["sig"] for t in fl[:1]], nkeys_med=med([t["nkeys"] for t in L]), nw_med=med([t.get("nwritable") for t in L]))
    out[w] = o
json.dump(out, open(f"{D2}/shapes.json", "w"), indent=1)
print(f"{'wallet':9s} {'n':>3s} ok/fl  size(min-max)  ver               nonce  accts alt  ldl                         cul    cu_ok  cul/cu  cup      cost   tips/tx        untipped_ok")
for w, o in out.items():
    print(f"{w[:8]:9s} {o['n']:3d} {o['n_ok']:2d}/{o['n_fail']:<2d} {o['size_med']:5.0f}({o['size_min']}-{o['size_max']}) {str(o['ver']):18s} {o['nonce']:3d}/{o['n']:<3d} {o['nonce_accts']:3d} {o['alt']:3d}  {str(o['ldl'])[:26]:26s} {o['cul_med'] or 0:6.0f} {o['cu_med_ok'] or 0:6.0f} {o['cul_over_cu_ok'] or 0:5.2f} {o['cup_med'] / 1e6:6.2f}M {o['cost_med_ok'] or 0:6.0f}  {str(o['tips_per_tx'])[:14]:14s} {o['untipped_ok']}/{o['n_ok']}")
    print(f"          tips: {o['tip_relays_all']}  in FAILED txs: {o['tip_relays_failed']}  lamports: { {k: v for k, v in o['tip_lamports_med'].items()} }")
    print(f"          pattern: {list(o['patterns'].items())[0][0][:200]} ({list(o['patterns'].values())[0]})  errs: {o['errs']}")
