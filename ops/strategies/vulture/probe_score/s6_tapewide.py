# Step 6: PAPER on ALL model picks on the tape inside the two probe windows (not only the engine's dump stream).
# One lot per (mint, slot) (highest score) as an engine would fire; leader near/far for a slot inferred from the engine's
# own far_leader skips / fires in the same 4-slot leader window [inference]. Uses s5_est.py's path sim.
import sys,pickle,json,numpy as np,collections
sys.dont_write_bytecode=True
D='/home/moiz/sniper-data/vulture_probe_score/'
src=open('/home/moiz/sniper/ops/strategies/vulture/probe_score/s5_est.py').read().split('# ---------- picks table')[0]
exec(src)
rows=pickle.load(open(D+'est.pkl','rb'))['rows']
eng={(r['mint'],r['slot'],r['idx']) for r in rows}
lead={}
for r in rows:
    g=r['slot']//4
    if r['status']=='skip:far_leader': lead.setdefault(g,set()).add('far')
    elif r['status'] in ('landed','fire_failed','skip:spacing','skip:max_open'): lead.setdefault(g,set()).add('near')
W={'r30':(min(r['slot'] for r in rows if r['run']=='r30'),max(r['slot'] for r in rows if r['run']=='r30')),'r31':(min(r['slot'] for r in rows if r['run']=='r31'),max(r['slot'] for r in rows if r['run']=='r31'))}
cre=pickle.load(open(D+'feat_ex2g.pkl','rb'))['cre']
first_slot={run:w[0] for run,w in W.items()}
em={r['mint'] for r in rows}
print('[check] engine-reported mints created after the run window start:',sum(1 for m in em if cre.get(m) and cre[m]>=min(w[0] for w in W.values())-1200),'/',len(em))
def win(c):
    for run,(a,b) in W.items():
        if a<=c['slot']<=b: return run
TW=[c for c in A['rows'] if win(c) and c['sol']>=0.3 and c['drop']>=3]
pk=[c for c in TW if c['score']>=THR]
best={}
for c in pk:
    k=(c['m'],c['slot'])
    if k not in best or c['score']>best[k]['score']: best[k]=c
U=sorted(best.values(),key=lambda c:(c['slot'],c['idx']))
def L(c):
    s=lead.get(c['slot']//4,set()); return 'far' if s=={'far'} else 'near' if s=={'near'} else 'unknown' if not s else 'mixed'
res=[]
for c in U:
    a=paper(c,c['tier']); b=paper(c,c['tier'],fol=0.8); n=paper(c,c['tier'],ko=False)
    if a is None: continue
    res.append(dict(c=c,run=win(c),lead=L(c),fill=a[0],net=a[1],f20=b[1],noko=n[1],eng=(c['m'],c['slot'],c['idx']) in eng))
mins={'r30':(P['r30']['end']['t']-P['r30']['start']['t'])/6e10,'r31':(P['r31']['end']['t']-P['r31']['start']['t'])/6e10}
out=[]; pr=lambda *a:(print(*a,flush=True),out.append(' '.join(str(x) for x in a)))
pr(f"tape envelope rows in windows {len(TW)}, picks {len(pk)}, one per mint-slot {len(U)}; leader label {dict(collections.Counter(r['lead'] for r in res))}")
for lab,flt in (('all',lambda r:True),('near or unknown leader',lambda r:r['lead']!='far'),('near leader only',lambda r:r['lead']=='near')):
    for run in ('r30','r31','total'):
        g=[r for r in res if flt(r) and (run=='total' or r['run']==run)]
        if not g: continue
        e=np.array([r['net'] for r in g]); tk=collections.defaultdict(float)
        for r in g: tk[r['c']['m']]+=r['net']
        hrs=(sum(mins.values()) if run=='total' else mins[run])/60
        pr(f"PAPER tape-wide {lab} {run}: picks {len(g)} ({len(g)/hrs:.0f}/h), exp fills {sum(r['fill'] for r in g):.1f}, net {e.sum():+.3f} | w/o top trade {e.sum()-e.max():+.3f} | w/o top token {e.sum()-max(tk.values()):+.3f} | fol-20% {sum(r['f20'] for r in g):+.3f} | no knock-out {sum(r['noko'] for r in g):+.3f} | per pick {1000*e.mean():+.1f} mSOL | tokens {len(tk)}")
# selection lift: non-picked tape envelope dumps (one per mint-slot) at 1.0 SOL
npk={}
for c in TW:
    if c['score']<THR: npk.setdefault((c['m'],c['slot']),c)
q=[paper(c,1.0) for c in npk.values()]; q=[x for x in q if x]
pr(f"PAPER tape-wide NON-picks at 1.0 SOL: n {len(q)}, per dump {1000*np.mean([x[1] for x in q]):+.1f} mSOL, fill {100*np.mean([x[0] for x in q]):.0f}%")
pr("\nper-pick (tape-wide, one per mint-slot):")
for r in res:
    c=r['c']; pr(f"  {r['run']} {pkt(c.get('t',0)) if c.get('t') else ''}{c['m'][:6]} slot {c['slot']} age {c['age']*0.2144:.0f}s sell {c['sol']:.2f} drop {c['drop']:.1f} score {1e3*c['score']:+.2f}e-3 z {c['tier']} lead {r['lead']} engine {r['eng']} fill {r['fill']:.2f} net {1000*r['net']:+.1f}m f20 {1000*r['f20']:+.1f}m")
open(D+'s6_out.txt','w').write('\n'.join(out)+'\n')
pickle.dump(res,open(D+'tapewide.pkl','wb'))
