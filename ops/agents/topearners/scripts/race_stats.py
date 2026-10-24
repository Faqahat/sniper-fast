# where top wallets land relative to the trigger dump: dslot, same-slot index gap, rank among buyers, price vs post-dump
import json, gzip, collections, sys
TOP = [l.strip() for l in open(sys.argv[1]) if l.strip()]
ME = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
TS = set(TOP) | {ME}
st = {w: dict(n=0, ds=collections.Counter(), rank=collections.Counter(), didx=[], ratio=[], pre=[], first=0, sol=[], gap_rank=collections.Counter()) for w in TS}
firsts = collections.Counter(); nr = 0; nr_with_buy = 0
for line in gzip.open("/home/moiz/sniper/ops/agents/topearners/work/races.jsonl.gz", "rt"):
    r = json.loads(line); nr += 1
    B = r["buys"]
    if not B: continue
    nr_with_buy += 1
    firsts[B[0][0]] += 1
    pd = r["vsol"] / r["vtok"] if r["vtok"] else None
    seen = set()
    prev_state = (r["vsol"], r["vtok"])
    for k, b in enumerate(B):
        (user, ds, i, j, sig, payer, sol, tok, fee, cup, cul, cu, tips, vsol, vtok, nev, nsb) = b
        if user in TS and user not in seen:
            seen.add(user); S = st[user]; S["n"] += 1; S["ds"][ds] += 1; S["rank"][min(k, 9)] += 1
            if ds == 0: S["didx"].append(i - r["i"])
            if pd and tok: S["ratio"].append((sol / tok) / pd)
            # price right before this buy vs post-dump price
            if k > 0:
                pv = B[k - 1]; pre = (pv[13] / pv[14]) / pd if pv[14] and pd else None
            else: pre = 1.0
            if pre: S["pre"].append(pre)
            S["sol"].append(sol / 1e9)
        prev_state = (vsol, vtok)
def q(v, ps=(10, 25, 50, 75, 90)):
    v = sorted(v)
    if not v: return "-"
    return "/".join(f"{v[min(len(v)-1, int(p/100*len(v)))]:.3g}" for p in ps)
print("races (>=1 SOL sells):", nr, "with >=1 buy within 5 slots:", nr_with_buy)
print("most frequent FIRST buyer after a dump:", [(w[:10], c) for w, c in firsts.most_common(15)])
for w in TOP + [ME]:
    S = st[w]
    if not S["n"]: continue
    n = S["n"]
    print(f"{w[:10]} races={n} dslot%={ {k: round(100*v/n,1) for k, v in sorted(S['ds'].items())} } rank%={ {k: round(100*v/n,1) for k, v in sorted(S['rank'].items())} }")
    print(f"      same-slot idx gap p10/25/50/75/90={q(S['didx'])}  fill/postdump={q(S['ratio'])}  pre-price/postdump={q(S['pre'])}  size={q(S['sol'])}")
