import json, statistics
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
# ---------- HIS create-slot bands ----------
d=json.load(open('/root/every_angle/slotdata.json'))
items=[(m,v) for m,v in d.items() if v['rows'] is not None and v.get('peak_r') is not None and v.get('create_slot')]
items.sort(key=lambda x:x[1]['create_slot'])
def ext(v):
    cre=[r for r in v['rows'] if r['iscre']]; dev=cre[0]['signer'] if cre else None
    b=[r for r in v['rows'] if r['isbuy'] and r['ok'] and r['signer']!=dev and r['signer']!=WALLET]
    return b,dev
def feat(v):
    b,dev=ext(v)
    sells=[r for r in v['rows'] if (not r['isbuy']) and (not r['iscre'])]
    return dict(ncos=len(set(r['signer'] for r in b)), nbuy=len(b),
                sol=sum(max(0,r['csol']) for r in b)/1e9, nsell=len(sells),
                peak=v['peak_r'], rr=v['realized_R'])
F=[feat(v) for m,v in items]
N=len(F); h=N//2; ISf=F[:h]; OOSf=F[h:]
def runr(g,thr): return sum(1 for r in g if r['peak']>=thr)/len(g) if g else float('nan')
def mR(g): return statistics.mean([r['rr'] for r in g]) if g else float('nan')
def band_report(title, keyf, bands):
    print(f"\n### {title} (his tape, n={N}) ###")
    print("  band            | OOS n | pump>=1.5 | pump>=2.0 | mean R   | (IS n, pump>=1.5)")
    for lab,lo,hi in bands:
        o=[r for r in OOSf if lo<=keyf(r)<hi]; i=[r for r in ISf if lo<=keyf(r)<hi]
        print(f"  {lab:15s} | {len(o):4d}  |   {runr(o,1.5):.3f}   |   {runr(o,2.0):.3f}   | {mR(o):+.4f} | ({len(i)}, {runr(i,1.5):.3f})")
INF=10**9
band_report("CO-SNIPER COUNT in create slot", lambda r:r['ncos'],
            [("0",0,1),("1-2",1,3),("3-5",3,6),("6+",6,INF)])
band_report("NET SOL inflow create slot", lambda r:r['sol'],
            [("<0.5",0,0.5),("0.5-2",0.5,2),("2-5",2,5),("5+",5,INF)])
band_report("#DISTINCT buyers create slot", lambda r:r['ncos'],
            [("0",0,1),("1-3",1,4),("4-7",4,8),("8+",8,INF)])
band_report("#SELLS in create slot", lambda r:r['nsell'],
            [("0",0,1),("1-2",1,3),("3+",3,INF)])

# ---------- UNIVERSE cosnipers bands (bigger N) ----------
print("\n\n===== UNIVERSE (creates+trajectories) =====")
C=json.load(open('/root/profit_backtest/creates.json'))
T={x['mint']:x for x in json.load(open('/root/profit_backtest/trajectories.json'))}
def peak(x):
    s=x.get('series') or []; e=x.get('entry_px')
    if not s or not e: return None
    px=[p[1] for p in s if isinstance(p,list) and len(p)>=2]
    return (max(px)/e) if px else None
U=[]
for c in C:
    t=T.get(c['mint']);
    if not t: continue
    pk=peak(t)
    if pk is None: continue
    U.append(dict(slot=c['create_slot'],peak=pk,ncos=t.get('cosnipers'),n=t.get('n')))
U.sort(key=lambda r:r['slot']); hn=len(U)//2; UIS=U[:hn]; UOS=U[hn:]
def ur(g,thr): return sum(1 for r in g if r['peak']>=thr)/len(g) if g else float('nan')
def uband(title,keyf,bands):
    print(f"\n### {title} (universe, N={len(U)}) ###")
    print("  band    | OOS n | pump>=1.5 | pump>=2.0 | meanpeak | (IS n, pump>=1.5)")
    for lab,lo,hi in bands:
        o=[r for r in UOS if r.get(keyf) is not None and lo<=r[keyf]<hi]
        i=[r for r in UIS if r.get(keyf) is not None and lo<=r[keyf]<hi]
        mp=statistics.mean([r['peak'] for r in o]) if o else float('nan')
        print(f"  {lab:7s} | {len(o):4d}  |   {ur(o,1.5):.3f}   |   {ur(o,2.0):.3f}   |  {mp:.3f}  | ({len(i)}, {ur(i,1.5):.3f})")
uband("CO-SNIPER COUNT (window)", 'ncos', [("0",0,1),("1-2",1,3),("3-5",3,6),("6-10",6,11),("11+",11,INF)])
uband("#TRADES n (window)", 'n', [("0",0,1),("1-5",1,6),("6-15",6,16),("16-40",16,41),("41+",41,INF)])
json.dump({'his_N':N,'uni_N':len(U)}, open('/root/every_angle/banded_done.json','w'))
