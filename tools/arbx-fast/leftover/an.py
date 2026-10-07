import json,collections,statistics as st
def q(a,p): a=sorted(a); return a[int(p*(len(a)-1))] if a else None
for seg in ['ft012c-p2','ft012c-p3']:
    D=json.load(open(f'ep-{seg}.json')); H=D['hours']; E=D['eps']
    print(f"\n== {seg} {H:.2f} h, episodes(net>0 at 0.2 SOL cap) {len(E)}")
    first=[e['obs'][0][1] for e in E]
    print(" net at open p50/p90/max", q(first,.5),q(first,.9),max(first), "sum SOL/h", sum(first)/H/1e9)
    durs=[e['dur'] for e in E]
    print(" dur ms p50/p90", q(durs,.5),q(durs,.9), " same-slot close", sum(1 for e in E if e['es']==e['ss'])/len(E))
    for L in (0,80,130,250,500):
        # value available at L: still open at L, net = last obs <= L
        vals=[];pairs=collections.Counter();ven=collections.Counter()
        for e in E:
            if e['dur']<L or (e['why']=='eof' and L>0 and e['dur']<L): continue
            o=[x for x in e['obs'] if x[0]<=L] or e['obs'][:1]
            n=o[-1][1]; vals.append(n); pairs[e['mint'][:8]]+=n; ven['>'.join(e['v'])]+=n
        big=[v for v in vals if v>=20000]
        print(f" open>={L}ms: n={len(vals)} ({len(vals)/H:.0f}/h) net p50={q(vals,.5)} p90={q(vals,.9)} sum={sum(vals)/H/1e9:.4f} SOL/h; net>=20k: n={len(big)} sum={sum(big)/H/1e9:.4f}")
        if L in (80,250):
            print("   top mints", [(m,round(v/1e9/H,4)) for m,v in pairs.most_common(8)])
            print("   venues", [(m,round(v/1e9/H,4)) for m,v in ven.most_common(8)])
    # concentration: top 10 episodes share
    s=sorted(first,reverse=True); print(" top10 eps share of net", sum(s[:10])/sum(s))
    sz=[e['obs'][0][2] for e in E]; print(" size p50/p90", q(sz,.5),q(sz,.9), "at cap 0.2", sum(1 for x in sz if x>=2e8)/len(sz))
