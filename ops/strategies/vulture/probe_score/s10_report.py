# Step 10: tables for the full fresh-window PAPER (reads full_paper.pkl from s9_full.py). All numbers PAPER.
import sys,pickle,collections,datetime as Dt,numpy as np
sys.dont_write_bytecode=True
D='/home/moiz/sniper-data/vulture_probe_score/'
Z=pickle.load(open(D+'full_paper.pkl','rb')); keep=Z['keep']
H=(Z['t_hi']-Z['t_lo'])/3600
pkt=lambda t:Dt.datetime.utcfromtimestamp(t)+Dt.timedelta(hours=5)
SC={'A near only (far skipped)':lambda c:('NEAR' if c['lead']!='far' else None),
    'B1 near + far @FRA963 (61 ms)':lambda c:('NEAR' if c['lead']!='far' else 'FRA963'),
    'B2 near + far @r29 (81 ms)':lambda c:('NEAR' if c['lead']!='far' else 'R29'),
    'S1 near only @all-fires dist (incl. late)':lambda c:('NEARall' if c['lead']!='far' else None),
    'X  all at probe landing (far optimistic)':lambda c:'NEAR'}
def rows(sc,flt=lambda c:True):
    o=[]
    for c,r in keep:
        if not flt(c): continue
        d=SC[sc](c)
        if d is None: continue
        o.append((c,r[(d,1.0)][0],r[(d,1.0)][1],r[(d,0.8)][1]))
    return o
def stats(o,hrs):
    if not o: return None
    e=np.array([x[2] for x in o]); f=np.array([x[3] for x in o]); s=np.sort(e)
    tk=collections.defaultdict(float)
    for x in o: tk[x[0]['m']]+=x[2]
    return dict(n=len(o),ph=len(o)/hrs,fills=sum(x[1] for x in o),net=e.sum(),no5=e.sum()-s[-5:].sum(),notok=e.sum()-max(tk.values()),f20=f.sum(),per=1000*e.mean())
HDR='| group | picks | picks/h | exp fills | net SOL | w/o top5 trades | w/o top token | fol-20% | mSOL/pick |\n|---|---|---|---|---|---|---|---|---|'
fm=lambda g,s: f"| {g} | {s['n']} | {s['ph']:.0f} | {s['fills']:.0f} | {s['net']:+.2f} | {s['no5']:+.2f} | {s['notok']:+.2f} | {s['f20']:+.2f} | {s['per']:+.1f} |"
out=[]; pr=lambda *a:(print(*a,flush=True),out.append(' '.join(str(x) for x in a)))
pr(f"PAPER VULTURE-2 full fresh window: slots {Z['lo']}..{Z['hi']}, PKT {pkt(Z['t_lo']):%m-%d %H:%M} .. {pkt(Z['t_hi']):%m-%d %H:%M} ({H:.2f} h); one lot per mint-slot picks simulated: {len(keep)}")
pr("leader class of picks:",dict(collections.Counter(c['lead'] for c,_ in keep)),"| tier mix:",dict(collections.Counter(c['tier'] for c,_ in keep)),
   "| engine-visible (steady state):",dict(collections.Counter(c['vis'] for c,_ in keep)))
pr("landing quantiles (slot fraction):",{k:[round(x,2) for x in v[::3]] for k,v in Z['DIST'].items()})
pr("\n## TOTAL by scenario"); pr(HDR)
for sc in SC: s=stats(rows(sc),H); pr(fm(sc,s))
pr("\n## by leader class (each at its scenario landing: near @probe, far @FRA963 / @r29 / skipped)"); pr(HDR)
for lc in ('near','unknown','far'):
    for sc in (['A near only (far skipped)'] if lc!='far' else ['B1 near + far @FRA963 (61 ms)','B2 near + far @r29 (81 ms)','X  all at probe landing (far optimistic)']):
        s=stats(rows(sc,lambda c:c['lead']==lc),H)
        if s: pr(fm(f"{lc} / {sc.split()[0]}",s))
pr("\n## by score tier (scenario A and B1)"); pr(HDR)
for sc in ('A near only (far skipped)','B1 near + far @FRA963 (61 ms)'):
    for z in (1.0,1.25,1.5):
        for nm,fl in (('score<0.00022',lambda c:c['score']<2.1849e-4),('0.00022-0.00155',lambda c:2.1849e-4<=c['score']<1.5467e-3)) if z==1.0 else ((f'tier {z}',lambda c,z=z:c['tier']==z),):
            s=stats(rows(sc,fl),H)
            if s: pr(fm(f"{sc.split()[0]} {nm} ({z} SOL)",s))
pr("\n## by engine visibility (dip_imit rules in steady state: a >=1 SOL sell, 1 s<=age<=1800 s, vsol<100 in that mint-slot)"); pr(HDR)
for sc in ('A near only (far skipped)','B1 near + far @FRA963 (61 ms)'):
    for v in (True,False):
        s=stats(rows(sc,lambda c,v=v:c['vis']==v),H)
        if s: pr(fm(f"{sc.split()[0]} engine-visible={v}",s))
pr("\n## per PKT hour (scenario A near only | B1 far @FRA963)")
pr('| PKT hour | h | A picks/h | A net | A w/o top5 | A fol-20% | B1 picks/h | B1 net | B1 w/o top5 | B1 fol-20% |\n|---|---|---|---|---|---|---|---|---|---|')
hrs=collections.defaultdict(float); t=Z['t_lo']
while t<Z['t_hi']:
    h=pkt(t).strftime('%m-%d %H'); nxt=min(Z['t_hi'],(int(t//3600)+1)*3600); hrs[h]+=(nxt-t)/3600; t=nxt
for h in sorted(hrs):
    fl=lambda c,h=h:pkt(c['t']).strftime('%m-%d %H')==h
    a=stats(rows('A near only (far skipped)',fl),hrs[h]); b=stats(rows('B1 near + far @FRA963 (61 ms)',fl),hrs[h])
    g=lambda s,k,f: (f % s[k]) if s else '-'
    pr(f"| {h} | {hrs[h]:.2f} | {g(a,'ph','%.0f')} | {g(a,'net','%+.2f')} | {g(a,'no5','%+.2f')} | {g(a,'f20','%+.2f')} | {g(b,'ph','%.0f')} | {g(b,'net','%+.2f')} | {g(b,'no5','%+.2f')} | {g(b,'f20','%+.2f')} |")
open(D+'full_paper.txt','w').write('\n'.join(out)+'\n')
