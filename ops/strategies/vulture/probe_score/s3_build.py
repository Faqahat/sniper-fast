# Step 3: VULTURE-2 features for the probe windows, using the FROZEN build.py feature code (copied verbatim below, only
# the attempt/label part (not model features) removed and the slow seller-history block restricted to the rows we score).
# Tape = same loader as bin_load.py (diprevive tape + vulture2x tape + new chunks extracted by s1_tape.py).
# usage: s3_build.py OUT.pkl [ex2g]   (ex2g: also drop FRA probe wallet 2g7r from the tape, like OURS -> sensitivity only)
import sys,glob,pickle,collections,bisect,numpy as np,time
sys.dont_write_bytecode=True
sys.path.insert(0,'/home/it/sniper-studies/sniper-diprevive/bin'); import ld
OUT=sys.argv[1]; EX2G=len(sys.argv)>2 and sys.argv[2]=='ex2g'
if EX2G: ld.O.OURS=set(ld.O.OURS)|{'2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE'}
t0=time.time()
fs=ld.files()+sorted(glob.glob('/home/it/sniper-studies/sniper-vulture2x/tape/run_*/*.pkl'))+sorted(glob.glob('/home/it/sniper-data/vulture_probe_score/tape/run_*/*.pkl'))
fs=sorted(set(fs),key=lambda f:int(f.split("_")[-1][:-4]))
T,MAXI,CRE,ep=ld.load(fs); T=dict(T)
print('tape',len(T),'files',len(fs),'OURS',sorted(ld.O.OURS),round(time.time()-t0),'s',flush=True)
W='8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3'; K=30e9*1073e12
for m in T: T[m].sort(key=lambda r:(r[0],r[1]))
KEY={m:[(x[0],x[1]) for x in l] for m,l in T.items()}
s0=464540931   # = min slot of 8yYMhu sigs (sigs.pkl+sigs_new.pkl), as in frozen build.py
s1=max(r[0] for l in T.values() for r in l)
PROBE=(465401500,465405100); CHECK=(465320000,465345000)   # CHECK = overlap with frozen cands.pkl (reproduction test)
def want(s): return PROBE[0]<=s<=PROBE[1] or CHECK[0]<=s<=CHECK[1]
SH={}
for f in glob.glob('/home/it/sniper-data/vulture_probe_score/shape/*.pkl')+glob.glob('/home/it/sniper-studies/sniper-vulture2x/shape/run_20261104_1240_*.pkl'): SH.update(pickle.load(open(f,'rb')))
ev=collections.defaultdict(list); creator={}
for m,l in T.items():
    creator[m]=l[0][5]
    for s,ix,isb,sol,tok,w,vt in l: ev[w].append((s,ix,m,isb,sol))
for w in ev: ev[w].sort()
launches=collections.defaultdict(list)
for m,c in creator.items(): launches[c].append(T[m][0][0])
for c in launches: launches[c].sort()
def vs_at(m,s,ix):
    j=bisect.bisect_right(KEY[m],(s,ix)); return K/T[m][j-1][6] if j else None
BOTS=('haqq6qnV','8PgC4ngp','9pQQc1xy','E2x1')
rows=[]
for m,l in T.items():
    cs=CRE.get(m,l[0][0]); first={}; npd=0; bal=collections.Counter(); wpos=0; wtr=0; lastW=-10**9
    for i,r in enumerate(l):
        s,ix,isb,sol,tok,w,vt=r
        if w==W:
            wpos+= tok if isb else -tok; wtr+=isb; lastW=s
        if not isb and sol>=0.8e9: npd+=0
        if not isb and w!=W and sol>=0.3e9 and s0<=s<=s1:
            vtp=l[i-1][6] if i else 1073e12; vpre=K/vtp/1e9; vpost=K/vt/1e9; drop=(1-(vpost/vpre)**2)*100
            if drop>=3:
              if not want(s):
                c=dict(m=m,slot=s,idx=ix,seller=w)   # only needed for ret8 -> seller dump history of later rows
              else:
                k=i-1;bf=sf=nb=0
                while k>=0 and l[k][0]>=s-20:
                    if l[k][2]: bf+=l[k][3];nb+=1
                    else: sf+=l[k][3]
                    k-=1
                held=bal[w]
                pre=l[max(0,i-200):i]; vs=[K/x[6]/1e9 for x in pre[-200:]]
                bh={b:0 for b in BOTS}
                for ww,v in bal.items():
                    if v>1e9:
                        for b in BOTS:
                            if ww.startswith(b): bh[b]=1
                c=dict(m=m,slot=s,idx=ix,seller=w,sol=sol/1e9,pct=tok/1e15*100,vsol=vpre,vpost=vpost,drop=drop,age=s-cs,hold=s-first.get(w,s),
                  creator=int(w==l[0][5]),fracsold=tok/max(held,1),full=int(tok>=0.97*held),bf=bf/1e9,sf=sf/1e9,nb=nb,
                  nholders=sum(1 for v in bal.values() if v>1e9),wholding=int(wpos>1e6),wtraded=wtr,last8y=s-lastW,
                  peak_ratio=vpre/max(vs) if vs else 1,n_buyers=len(first),
                  n_same_slot_before=sum(1 for x in pre[-60:] if x[0]==s),buys_same_slot_before=sum(1 for x in pre[-60:] if x[0]==s and x[2]),
                  prev_dumps_tok=npd,
                  s_bundle=int(first.get(w,-1)==cs),s_entry_age=first.get(w,s)-cs,
                  **{'bot_'+b:bh[b] for b in BOTS})
                c['n_bot_hold']=sum(bh.values())
                sh=SH.get((s,ix)); c['sh_found']=sh is not None
                c.update(dict(zip(['sh_fee','sh_cup','sh_cul','sh_tip','sh_nrouter','sh_direct','sh_nsig','sh_nix'],sh if sh else [-1]*8)))
                c['vtok_post']=vt; c['vtok_pre']=vtp
              rows.append(c)
        if not isb and sol>=0.8e9: npd+=1
        if w not in first: first[w]=s
        bal[w]+= tok if isb else -tok
print('cands',len(rows),round(time.time()-t0),'s',flush=True)
rows.sort(key=lambda c:(c['slot'],c['idx']))
for c in rows:
    v0=vs_at(c['m'],c['slot'],c['idx']); v1=vs_at(c['m'],c['slot']+8,10**6)
    c['ret8']=((v1/v0)**2*0.98-1) if v0 and v1 else 0
hist=collections.defaultdict(list); keep=[]
for c in rows:
    w=c['seller'];s=c['slot']
    if want(s):
        e=ev[w]
        j=bisect.bisect_left(e,(s,c['idx'])); past=e[:j]
        c['s_ntok']=len({x[2] for x in past}); c['s_nsell_big']=sum(1 for x in past if not x[3] and x[4]>=0.8e9)
        c['s_nbuy']=sum(1 for x in past if x[3]); c['s_age']=s-past[0][0] if past else -1
        c['s_bigs_1h']=sum(1 for x in past if not x[3] and x[4]>=0.8e9 and x[0]>=s-9000)
        c['s_nbuy_sol']=sum(x[4] for x in past if x[3])/1e9
        h=[r for (sk,r) in hist[w] if sk<s]
        c['s_ndump_known']=len(h); c['s_dump_ret']=float(np.mean(h)) if h else -9
        c['c_nlaunch']=bisect.bisect_left(launches[creator[c['m']]],s)
        c['c_is_serial']=int(c['c_nlaunch']>=3)
        c['tape_first_slot_seller']=past[0][0] if past else None
        keep.append(c)
    hist[w].append((s+8,c['ret8']))
tape_lo=min(r[0] for l in T.values() for r in l)
PM={c['m'] for c in keep if PROBE[0]<=c['slot']<=PROBE[1]}
TP={m:[r for r in T[m] if PROBE[0]-400<=r[0]<=PROBE[1]+60] for m in PM}
MX={s:i for s,i in MAXI.items() if PROBE[0]-400<=s<=PROBE[1]+60}
pickle.dump(dict(rows=keep,s1=s1,tape_lo=tape_lo,nf=len(fs),ex2g=EX2G,tape=TP,maxi=MX,cre={m:CRE.get(m) for m in PM}),open(OUT,'wb'),protocol=5)
print('saved',len(keep),'tape slots',tape_lo,s1,round(time.time()-t0),'s',flush=True)
