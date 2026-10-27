#!/usr/bin/env python3
# INSTANT-BOTS study, step 4 (read-only): every DUMP of the run (a successful curve sell that drops the price >= 3% by itself) with
# its block context from the pass-1 trade extracts: the trades right before it in its slot and every trade after it in the same
# slot and the next slot (block index gap, wallet, size, tip / landing service, CU price / limit, custom programs, signature).
# Also writes per-wallet buy totals (all successful curve buys) for the "share of a wallet's buys that follow a dump" metric.
# usage: nice python3 -I i4_census.py X_DIR OUT_PREFIX [min_drop_pct]
import sys, json, glob, gzip, collections, time
xdir, outp = sys.argv[1], sys.argv[2]; MIN_DROP = float(sys.argv[3]) / 100 if len(sys.argv) > 3 else 0.03
t0 = time.time()
TAPE = collections.defaultdict(list); BUYS = collections.Counter(); SELLS = collections.Counter(); BUYSOL = collections.Counter()
intern = sys.intern
for f in sorted(glob.glob(f"{xdir}/T_*.jsonl.gz")):
    for l in gzip.open(f, "rt"):
        r = json.loads(l)
        # r = [s, i, j, sig, signers, user, mint, buy, sol, tok, vsol, vtok, fee, cup, cul, cu, tip_total, tip_svcs, progs_ns, sdw, ixn]
        u = intern(r[5]); m = intern(r[6])
        TAPE[m].append((r[0], r[1], r[2], r[7], r[8], r[9], r[10], r[11], u, intern(r[4][0]) if r[4] else "", r[3], r[13], r[14], r[16], intern(r[17]), intern(r[18]), r[12], len(r[4])))
        if r[7]: BUYS[u] += 1; BUYSOL[u] += r[8]
        else: SELLS[u] += 1
print(f"loaded {sum(len(v) for v in TAPE.values())} trades on {len(TAPE)} mints in {time.time() - t0:.0f}s", flush=True)
def row(t, d=None):
    s, i, j, buy, sol, tok, vsol, vtok, u, sg, sig, cup, cul, tip, tsv, pr, fee, nsig = t
    x = dict(s=s, i=i, j=j, buy=buy, sol=sol, u=u, sg=sg if sg != u else "", sig=sig, cup=cup, cul=cul, tip=tip, tsv=tsv, pr=pr, fee=fee, nsig=nsig)
    if d is not None: x["gap"] = (i - d[1]) if s == d[0] else None
    return x
nd = 0
with gzip.open(outp + "_dumps.jsonl.gz", "wt", compresslevel=3) as fo:
    for m, tp in TAPE.items():
        tp.sort(key=lambda t: (t[0], t[1], t[2]))
        n = len(tp)
        for k, t in enumerate(tp):
            if t[3]: continue
            s, i, j, buy, sol, tok, vsol, vtok = t[:8]
            if vtok <= tok or vsol <= 0: continue
            pre = (vsol + sol) / (vtok - tok); post = vsol / vtok
            drop = 1 - post / pre
            if drop < MIN_DROP: continue
            before = [row(x, t) for x in tp[max(0, k - 6):k] if x[0] >= s - 1]
            after = []
            for x in tp[k + 1:]:
                if x[0] > s + 1: break
                if x[0] == s or len([a for a in after if a["s"] == s + 1]) < 12: after.append(row(x, t))
                if len(after) >= 60: break
            d = row(t); d.update(mint=m, drop=drop, p_pre=pre, p_post=post)
            fo.write(json.dumps(dict(d=d, before=before, after=after), separators=(",", ":")) + "\n"); nd += 1
json.dump(dict(buys=BUYS, sells=SELLS, buysol=BUYSOL), open(outp + "_wallets.json", "w"))
print(f"dumps >= {MIN_DROP * 100:.0f}%: {nd}; {time.time() - t0:.0f}s", flush=True)
