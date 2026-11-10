# Step 5: MEASURED / EST / PAPER for VULTURE-2 picks on the FRA probe windows (r30, r31).
# Path sim = frozen ex.lot logic (TP 7% / 2-slot timer, band 0.88-1.04 x post-dump vsol, land in dump slot) but on OUR block clock:
#  entry = our real landing idx (fills) or the 55 measured (buy_idx-dump_idx)/slot_txs fractions (paper); timer exit = our real sell idx
#  (fills) or the measured sell-position fractions; TP sell lands at trigger + entry fraction (spill -> next slot).
#  Knock-out (verifier stress.py): if vsol after our buy > 1.04 x post-dump, all outside buys later in the dump slot are removed.
#  Costs: pump fee 1.25%/leg (~2.5% round trip) in curve math + 0.0033 SOL fixed per fill; failed try 5,120 lamports.
#  Tape for paths = feat_ex2g (our wallets 2g7r/Egxf removed and curve re-based, as ld.load does for OURS).
import sys,pickle,json,bisect,collections,datetime as Dt,numpy as np
sys.dont_write_bytecode=True
D='/home/it/sniper-data/vulture_probe_score/'
cfg=json.load(open('/home/it/sniper-studies/sniper-vulture2x/VULTURE_v2.json')); THR=cfg['select']['score_thr']; EDG=cfg['size']['edges']; SZ=cfg['size']['sizes']
S=pickle.load(open(D+'scored.pkl','rb')); P=pickle.load(open(D+'probe.pkl','rb'))
A=S['feat']; X=S['feat_ex2g']; TP=X['tape']; MAXI=X['maxi']
K=30e9*1073e12; FEE=0.0125; FIX=0.0033; FAILC=5120e-9; BAND=(0.88,1.04); TPX=0.07; HOLD=2; KO=1.04
KEYS={m:[(r[0],r[1]) for r in l] for m,l in TP.items()}
n_of=lambda s: MAXI.get(s,0)+1
pkt=lambda t: (Dt.datetime.utcfromtimestamp(t/1e9)+Dt.timedelta(hours=5)).strftime('%H:%M:%S')
# ---------- status of every engine dump ----------
st={}
for run in ('r30','r31'):
    p='/home/it/sniper-data/runs/fra_%s/dip_%s.jsonl'%(run[1:].join(['fra_r','']) and run,run)
for run,path in (('r30','/home/it/sniper-data/runs/fra_r30/dip_r30.jsonl'),('r31','/home/it/sniper-data/runs/fra_r31/dip_r31.jsonl')):
    for l in open(path):
        d=json.loads(l)
        if d.get('ev')=='pick_skip': st[d['sig']]='skip:'+d['why']
fills={}
for run in ('r30','r31'):
    for f in P[run]['fires']:
        st[f['dump_sig']]='landed' if f['landed'] else 'fire_failed'
        if f['landed']: fills[f['dump_sig']]=f
# ---------- measured landing distributions ----------
FR=[];SF=[];POS=[]
for f in fills.values():
    if f['buy_slot']==f['dump_slot']: FR.append((f['buy_idx']-f['dump_idx'])/n_of(f['buy_slot']))
    if f.get('pos_ms') is not None: POS.append(f['pos_ms'])
    sl=f['sell_land']
    if sl and sl[0] is not None and f['exit_why']=='time-limit' and sl[0]-f['dump_slot']==HOLD: SF.append(sl[1]/n_of(sl[0]))
FR=np.array(FR); SF=np.array(SF)
def trip(m,s,six,z,fol=1.0,ko=True,entry_idx=None,frac=None,exit_key=None,sfrac=None):
    """returns (filled, net SOL)"""
    l=TP.get(m); KY=KEYS.get(m)
    if not l: return None
    n=n_of(s); k0=bisect.bisect_left(KY,(s,six+1)); vpost=K/(l[k0-1][6] if k0>0 else 1073e12)
    lix=entry_idx if entry_idx is not None else six+frac*n
    if lix>n-1: return (False,-FAILC)
    k=bisect.bisect_left(KY,(s,lix)); vt=l[k-1][6] if k>0 else 1073e12; vs=K/vt
    if not BAND[0]<=vs/vpost<=BAND[1]: return (False,-FAILC)
    V=vs+z*1e9*(1-FEE); tok=vt-K/V; cut=ko and V/vpost>KO
    ef=frac if frac is not None else (lix-six)/n
    xk=exit_key if exit_key is not None else (s+HOLD,sfrac*n_of(s+HOLD))
    val=lambda V:(V-K/(K/V+tok))*(1-FEE)/1e9-z
    j=k; last=val(V); tpk=None
    while j<len(l):
        r=l[j]; key=(r[0],r[1])
        if key>=xk or (tpk is not None and key>=tpk): break
        prev=l[j-1][6] if j>0 else 1073e12; d=K/r[6]-K/prev
        if d>0:
            d*=fol
            if cut and r[0]==s: d=0.0
        V=max(V+d,1e9); last=val(V); j+=1
        if tpk is None and last/z>=TPX:
            ti=r[1]+ef*n_of(r[0]); tpk=(r[0],ti) if ti<=n_of(r[0])-1 else (r[0]+1,ef*n_of(r[0]+1))
    return (True,last-FIX)
def paper(c,z,**kw):
    """expected net over the measured entry x sell fractions"""
    v=[];f=[]
    for fr in FR:
        for sf in np.quantile(SF,[.1,.3,.5,.7,.9]):
            r=trip(c['m'],c['slot'],c['idx'],z,frac=fr,sfrac=sf,**kw)
            if r is None: return None
            f.append(r[0]); v.append(r[1])
    return np.mean(f),np.mean(v)
# ---------- picks table over the engine's envelope dumps ----------
J=A['J']; Jx=X['J']
rows=[]
for sig,v in J.items():
    d=v['d']; c=v['row']; r=dict(run=v['run'],sig=sig,mint=d['mint'],slot=d['slot'],idx=d['idx'],sell=d['sell'],drop=d['drop_pct'],t=d['t'],
        status=st.get(sig,'pass' if d.get('pass') else 'no_pass'),matched=c is not None)
    if c:
        r.update(score=c['score'],tier=c['tier'],pick=c['score']>=THR,sc_ex2g=(Jx[sig]['row'] or {}).get('score'))
    f=fills.get(sig)
    if f: r.update(pnl=f['pnl'],buy_idx=f['buy_idx'],pos_ms=f['pos_ms'],sell_land=f['sell_land'],exit_why=f['exit_why'],n_after=f['n_after'],sol_after=f['sol_after'],buy_slot=f['buy_slot'])
    rows.append(r)
rows.sort(key=lambda r:(r['slot'],r['idx']))
pk=[r for r in rows if r.get('pick')]
out=[]; pr=lambda *a: (print(*a,flush=True),out.append(' '.join(str(x) for x in a)))
pr(f"COVERAGE: engine envelope dumps {len(rows)}, matched on the tape {sum(r['matched'] for r in rows)}; model picks {len(pk)} (r30 {sum(r['run']=='r30' for r in pk)}, r31 {sum(r['run']=='r31' for r in pk)})")
pr("picks unchanged when our probe wallet is removed from the tape:",sum(1 for r in pk if r['sc_ex2g'] is not None and r['sc_ex2g']>=THR),'/',len(pk))
pr("pick status:",dict(collections.Counter(r['status'] for r in pk)),"| all dumps status:",dict(collections.Counter(r['status'] for r in rows)))
pr(f"measured landing: entry fraction of slot after dump (n {len(FR)}) p25/p50/p75 {np.percentile(FR,[25,50,75]).round(3)}; block-pos ms p50 {np.median(POS):.1f}; timer-sell idx fraction (n {len(SF)}) p50 {np.median(SF):.2f}")
# ---------- calibration: sim vs measured on the 55 real fills at 0.05 SOL, real entry + real exit ----------
cal=[]
for r in rows:
    if 'pnl' not in r: continue
    sl=r['sell_land']; xk=(sl[0],sl[1]) if sl and sl[0] is not None else None
    q=trip(r['mint'],r['slot'],r['idx'],0.05,ko=False,entry_idx=r['buy_idx'],exit_key=xk,sfrac=np.median(SF))
    if q: cal.append((r['pnl'],q[1] if q[0] else None,r.get('pick',False)))
cm=np.array([c[0] for c in cal if c[1] is not None]); cs=np.array([c[1] for c in cal if c[1] is not None])
pr(f"CALIBRATION (0.05 SOL, real entry/exit idx, no knock-out): n {len(cm)} measured sum {cm.sum():+.4f} sim sum {cs.sum():+.4f}; per-fill corr {np.corrcoef(cm,cs)[0,1]:.2f}; sim says band-fail on {sum(1 for c in cal if c[1] is None)}")
# ---------- MEASURED ----------
L=[r for r in rows if 'pnl' in r]
for nm,g in (('picked fills',[r for r in L if r.get('pick')]),('non-picked fills',[r for r in L if r['matched'] and not r.get('pick')]),('unmatched fills',[r for r in L if not r['matched']])):
    p=[r['pnl'] for r in g]
    pr(f"MEASURED {nm}: n {len(g)}, sum {sum(p):+.4f} SOL, avg {1000*np.mean(p) if p else 0:+.1f} mSOL, wins {sum(x>0 for x in p)}")
# ---------- EST: picked fills at tier size, real entry idx ----------
def est(group,fol,ko,real_exit=True,z=None):
    res=[]
    for r in group:
        sl=r['sell_land']; xk=(sl[0],sl[1]) if (real_exit and sl and sl[0] is not None and r['exit_why']=='time-limit') else None
        q=trip(r['mint'],r['slot'],r['idx'],z or r['tier'],fol=fol,ko=ko,entry_idx=r['buy_idx'],exit_key=xk,sfrac=np.median(SF))
        res.append(q[1] if q else 0.0)
    return np.array(res)
PF=[r for r in L if r.get('pick')]
pr("EST picked fills detail (tier size, knock-out on): "+'; '.join(f"{r['run']} {r['mint'][:6]} z{r['tier']} meas {1000*r['pnl']:+.1f}m est {1000*x:+.1f}m" for r,x in zip(PF,est(PF,1.0,True))))
for run in ('r30','r31','total'):
    g=[r for r in PF if run=='total' or r['run']==run]
    if not g: pr(f"EST {run}: no picked fills"); continue
    a=est(g,1.0,True); b=est(g,0.8,True); c0=est(g,1.0,False)
    pr(f"EST {run}: picked fills {len(g)} | tier, knock-out {a.sum():+.3f} | w/o top trade {a.sum()-a.max():+.3f} | followers -20% {b.sum():+.3f} | no knock-out {c0.sum():+.3f} | per fill {1000*a.mean():+.1f} mSOL")
# ---------- PAPER: all model picks among engine envelope dumps, measured landing distribution ----------
def paper_group(g,fol=1.0,ko=True,z=None):
    E=[];F=[];used=[]
    for r in g:
        c=A['J'][r['sig']]['row']; q=paper(c,z or r['tier'],fol=fol,ko=ko)
        if q is None: continue
        F.append(q[0]);E.append(q[1]);used.append(r)
    return np.array(E),np.array(F),used
mins={'r30':(P['r30']['end']['t']-P['r30']['start']['t'])/6e10,'r31':(P['r31']['end']['t']-P['r31']['start']['t'])/6e10}
pr(f"window minutes r30 {mins['r30']:.1f}, r31 {mins['r31']:.1f}")
for lab,flt in (('all picks',lambda r:True),('picks NOT far_leader-skipped',lambda r:r['status']!='skip:far_leader')):
    for run in ('r30','r31','total'):
        g=[r for r in pk if flt(r) and (run=='total' or r['run']==run)]
        e,f,u=paper_group(g); e2,_,_=paper_group(g,fol=0.8); e3,_,_=paper_group(g,ko=False)
        top=e.max() if len(e) else 0
        hrs=(mins['r30']+mins['r31'] if run=='total' else mins[run])/60
        pr(f"PAPER {lab} {run}: picks {len(g)} ({len(g)/hrs:.0f}/h), exp fills {f.sum():.1f} ({100*f.mean() if len(f) else 0:.0f}%), net {e.sum():+.3f} | w/o top {e.sum()-top:+.3f} | fol-20% {e2.sum():+.3f} | no knock-out {e3.sum():+.3f} | per pick {1000*e.mean() if len(e) else 0:+.1f} mSOL")
# random baseline: same number of non-picked engine dumps (not far_leader), tier 1.0
rng=np.random.RandomState(7); npk=[r for r in rows if r['matched'] and not r.get('pick') and r['status']!='skip:far_leader']
e,f,_=paper_group(npk,z=1.0)
pr(f"PAPER non-picked engine dumps (not far_leader) at 1.0 SOL: n {len(npk)}, per dump {1000*e.mean():+.1f} mSOL, fill {100*f.mean():.0f}%")
# tape-wide picks inside the two run windows (envelope dumps the engine did not report too)
lo30,hi30=min(r['slot'] for r in rows if r['run']=='r30'),max(r['slot'] for r in rows if r['run']=='r30')
lo31,hi31=min(r['slot'] for r in rows if r['run']=='r31'),max(r['slot'] for r in rows if r['run']=='r31')
eng={(r['mint'],r['slot'],r['idx']) for r in rows}
TW=[c for c in A['rows'] if (lo30<=c['slot']<=hi30 or lo31<=c['slot']<=hi31) and c['sol']>=0.3 and c['drop']>=3]
TWp=[c for c in TW if c['score']>=THR]
pr(f"TAPE-WIDE in run windows: envelope rows {len(TW)} (engine reported {len(rows)}), model picks {len(TWp)}, of which engine-reported {sum((c['m'],c['slot'],c['idx']) in eng for c in TWp)}")
E=[];F=[]
for c in TWp:
    q=paper(c,c['tier'])
    if q: F.append(q[0]);E.append(q[1])
E=np.array(E);F=np.array(F)
pr(f"PAPER tape-wide picks: n {len(E)}, exp fills {F.sum():.1f}, net {E.sum():+.3f}, w/o top {E.sum()-E.max():+.3f}, per pick {1000*E.mean():+.1f} mSOL")
pickle.dump(dict(rows=rows,FR=FR,SF=SF,out=out),open(D+'est.pkl','wb'))
# picks table
pr("\n| run | PKT | token | sell SOL | drop % | score | tier SOL | status | measured P&L (0.05) |")
pr("|---|---|---|---|---|---|---|---|---|")
for r in pk:
    pr(f"| {r['run']} | {pkt(r['t'])} | [{r['mint'][:6]}](https://gmgn.ai/sol/token/{r['mint']}) | {r['sell']:.2f} | {r['drop']:.1f} | {r['score']*1000:+.2f}e-3 | {r['tier']} | {r['status']} | {('%+.4f'%r['pnl']) if 'pnl' in r else '-'} |")
open(D+'s5_out.txt','w').write('\n'.join(out)+'\n')
