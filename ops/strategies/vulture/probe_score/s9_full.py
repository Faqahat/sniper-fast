# Step 9: PAPER VULTURE-2 over the FULL fresh window (465188147 .. tape end), s6 method:
#  one lot per mint-slot (highest score), tier sizes, knock-out on (>1.04x post-dump -> later in-slot outside buys removed),
#  costs: pump fee 1.25%/leg + 0.0033 SOL fixed per fill, failed try 5,120 lamports; TP 7% / 2-slot timer; band 0.88-1.04.
#  Landing on the block-position clock (entry idx = dump idx + frac * block txs; frac >= rest of slot -> spill -> fail):
#   NEAR  = probes r30+r31 timing clock2.land_ms_pos / slot_ms of the LANDED fills (same slot 100%)  [coordinator spec]
#   NEARall = all r30+r31 fire timing records (incl. the 16 that landed a slot late and failed)       [sensitivity]
#   FRA963 = /home/moiz/sniper-data/ld247/fra_lat.npy (slots), R29 = r29 timing land_ms_pos (all fires)  [far leaders, slow]
#  Leader class from the epoch 1076/1077 leader schedule (public RPC getLeaderSchedule) vs ops/region/near_leaders_fra.txt (198, the probes' list).
import sys,pickle,json,bisect,collections,datetime as Dt,numpy as np
sys.dont_write_bytecode=True
D='/home/moiz/sniper-data/vulture_probe_score/'
cfg=json.load(open('/home/moiz/sniper-vulture2x/VULTURE_v2.json')); THR=cfg['select']['score_thr']; EDG=cfg['size']['edges']; SZ=cfg['size']['sizes']
F=pickle.load(open(D+'fresh_feat.pkl','rb')); TP=F['tape']; MAXI=F['maxi']
LEAD=pickle.load(open(D+'sched/slot_leader.pkl','rb')); NEAR=set(l.strip() for l in open('/home/moiz/sniper/ops/region/near_leaders_fra.txt') if l.strip())
SF=pickle.load(open(D+'est.pkl','rb'))['SF']; SFQ=np.quantile(SF,[1/6,.5,5/6])
K=30e9*1073e12; FEE=0.0125; FIX=0.0033; FAILC=5120e-9; BAND=(0.88,1.04); TPX=0.07; HOLD=2; KO=1.04
KEYS={m:[(r[0],r[1]) for r in l] for m,l in TP.items()}
n_of=lambda s: MAXI.get(s,0)+1
def timing(run,landed_only):
    v=[]
    for l in open(f'/home/moiz/sniper-data/runs/fra_{run}/dip_{run}.jsonl'):
        if '"timing"' not in l: continue
        d=json.loads(l); c=d.get('clock2') or {}
        if c.get('land_ms_pos') is None: continue
        if landed_only and c.get('buy_slot')!=c.get('dump_slot'): continue
        v.append(c['land_ms_pos']/d.get('slot_ms',214.4))
    return np.array(v)
Q=lambda a,n=12: np.quantile(a,(np.arange(n)+0.5)/n)
DIST={'NEAR':Q(np.concatenate([timing('r30',True),timing('r31',True)])),'NEARall':Q(np.concatenate([timing('r30',False),timing('r31',False)])),
      'FRA963':Q(np.load('/home/moiz/sniper-data/ld247/fra_lat.npy')),'R29':Q(timing('r29',False))}
def trip(m,s,six,z,frac,sfrac,fol=1.0,ko=True):
    l=TP.get(m); KY=KEYS.get(m)
    if not l: return None
    n=n_of(s); k0=bisect.bisect_left(KY,(s,six+1)); vpost=K/(l[k0-1][6] if k0>0 else 1073e12)
    lix=six+frac*n
    if lix>n-1: return (False,-FAILC)
    k=bisect.bisect_left(KY,(s,lix)); vt=l[k-1][6] if k>0 else 1073e12; vs=K/vt
    if not BAND[0]<=vs/vpost<=BAND[1]: return (False,-FAILC)
    V=vs+z*1e9*(1-FEE); tok=vt-K/V; cut=ko and V/vpost>KO
    xk=(s+HOLD,sfrac*n_of(s+HOLD))
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
            ti=r[1]+frac*n_of(r[0]); tpk=(r[0],ti) if ti<=n_of(r[0])-1 else (r[0]+1,frac*n_of(r[0]+1))
    return (True,last-FIX)
def paper(c,dist,fol):
    f=[];v=[]
    for fr in DIST[dist]:
        for sf in SFQ:
            r=trip(c['m'],c['slot'],c['idx'],c['tier'],fr,sf,fol)
            if r is None: return None
            f.append(r[0]);v.append(r[1])
    return float(np.mean(f)),float(np.mean(v))
def one(c):
    o={}
    for dist in DIST:
        for fol in (1.0,0.8):
            q=paper(c,dist,fol)
            if q is None: return None
            o[(dist,fol)]=q
    return o
if __name__=='__main__':
    from multiprocessing import Pool
    R=[c for c in F['rows'] if c['sol']>=0.3 and c['drop']>=3]
    pk=[c for c in R if c['score']>=THR]
    best={}
    for c in pk:
        k=(c['m'],c['slot'])
        if k not in best or c['score']>best[k]['score']: best[k]=c
    U=sorted(best.values(),key=lambda c:(c['slot'],c['idx']))
    # engine visibility in steady state (dip_imit rules): some sell in this mint-slot with >=1 SOL, 1 s<=age<=1800 s, vsol<100
    vis=collections.defaultdict(bool)
    for c in R:
        if c['sol']>=1.0 and 1.0<=c['age']*0.2137<=1800 and c['vpost']<100: vis[(c['m'],c['slot'])]=True
    for c in U:
        c['tier']=SZ[int(np.searchsorted(EDG,c['score']))]; ld=LEAD.get(c['slot'])
        c['lead']='unknown' if ld is None else ('near' if ld in NEAR else 'far'); c['vis']=vis[(c['m'],c['slot'])]
    with Pool(6) as p: res=p.map(one,U,chunksize=20)
    keep=[(c,r) for c,r in zip(U,res) if r is not None]
    print('rows',len(R),'row picks',len(pk),'one per mint-slot',len(U),'simulated',len(keep),flush=True)
    pickle.dump(dict(keep=keep,DIST={k:v.tolist() for k,v in DIST.items()},SFQ=SFQ.tolist(),lo=min(c['slot'] for c in R),hi=max(c['slot'] for c in R),
                     t_lo=min(c['t'] for c in R),t_hi=max(c['t'] for c in R)),open(D+'full_paper.pkl','wb'))
    print('saved',flush=True)
