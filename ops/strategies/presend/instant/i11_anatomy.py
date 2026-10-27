#!/usr/bin/env python3
# INSTANT-BOTS study, step 11 (read-only RPC, cached, <= 4 calls/s): tx anatomy of the key bots' landed fast-follow buys (and, for
# the pre-senders, of a few of their failed / no-op attempts right before a fill): version, signatures, durable nonce
# (AdvanceNonce first), CU limit / price, tip transfers (service, lamports, position), address-lookup tables, instruction list,
# fee, CU used. Also the dumps of the rotation / same-program families.
# usage: python3 -I i11_anatomy.py CLASSES.json WTX.jsonl.gz OUT.json
import sys, json, gzip, collections, random
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/instant")
import rpc_ro as R
C = json.load(open(sys.argv[1])); wtx = sys.argv[2]; outp = sys.argv[3]; random.seed(11)
KEY = ["Dk2jdQ93", "CZ77onJz", "9K5QgBKa", "FUru6V3L", "5k2Ckkiu", "2KtcBCfh", "5ZKd8DNB", "CVPz447t", "2XyiEK56", "7VrFNnRw", "FNuoWSQc",
       "DF7eRXHn", "haqqiUUX", "HkQ7hMjy", "GKd5EMzR", "ssssswdk", "EMKY7r6U", "8PgC4ngp", "BUkpShoE", "EJX629cp",
       "AFrSqSLk", "nya666pQ", "E2x1ewwX", "kBDycuZW", "2zMj6wNq", "2Dd3TRSd", "Fm4KUVJz", "7wqrdPux"]
def fam969(r): return r["cup"] == 500 and r["cul"] == 200000 and not r["tsv"]
pick = []
for k in KEY:
    ev = [r for r in C if r["u"].startswith(k)]
    ev.sort(key=lambda r: r["gap"])
    for r in ev[:2]: pick.append(("buy", k, r))
for r in random.sample([r for r in C if fam969(r)], 3): pick.append(("buy", "rotation969", r)); pick.append(("dump", "rotation969", r))
# a few attempts of the pre-senders right before one of their fills
PRE = {"Dk2jdQ93", "CZ77onJz", "9K5QgBKa", "FUru6V3L", "2KtcBCfh", "5ZKd8DNB", "2XyiEK56", "7VrFNnRw", "CVPz447t"}
want = {}
for kind, k, r in pick:
    if kind == "buy" and k in PRE: want.setdefault(r["mint"], []).append((k, r))
att = collections.defaultdict(list)
for l in gzip.open(wtx, "rt"):
    s, i, sig, sg, err, fee, cup, cul, cu, pr, ixn, mints, tr, tips, sd0 = json.loads(l)
    for m in mints:
        for k, r in want.get(m, []):
            if sg[0].startswith(k) and r["s"] - 3 <= s <= r["s"] and (s, i) < (r["s"], r["di"]) and (err or not tr):
                att[(k, r["sig"])].append((s, i, sig, err))
for (k, bsig), v in att.items():
    v.sort()
    for x in v[-2:]: pick.append(("attempt", k, dict(sig=x[2], s=x[0], err=x[3])))
out = []
for kind, k, r in pick:
    sig = r["sig"] if kind != "dump" else r["dsig"]
    a = R.anatomy(R.tx(sig))
    out.append(dict(kind=kind, wallet=k, sig=sig, gap=r.get("gap"), client=r.get("client"), a=a))
    if a:
        print(f"{kind:7s} {k:12s} gap {str(r.get('gap')):3s} {str(r.get('client')):8s} v={a['version']} nsig={a['nsig']} nonce={a['nonce']} cup={a['cup']} cul={a['cul']} cu={a['cu']} fee={a['fee']} "
              f"alts={a['alts']} tips={[(t[0], t[1], t[2]) for t in a['tips']]} err={a['err']} ixs={a['ixs']}", flush=True)
json.dump(out, open(outp, "w"), indent=1)
print("rpc calls", R.calls())
