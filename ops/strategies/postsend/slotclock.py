"""Per-slot feed clock (MEASURED samples, start time ESTIMATED by idx extrapolation).
Samples: obs race_tx (t=first feed arrival, idx) + presend_attempt_land (first_rx, idx) of the same run.
start(s) = median over samples of (t - r*idx), r = global median ms/idx inside a slot."""
import json, glob, sys, collections, pickle, statistics as st
B='/home/moiz/sniper-data/runs/'
def samples(run_dir):
    S=collections.defaultdict(list)
    for f in glob.glob(B+run_dir+'/*.jsonl*'):
        for l in open(f):
            if '"race_tx"' in l:
                e=json.loads(l)
                if e.get('idx') is not None: S[e['slot']].append((e['t'],e['idx']))
            elif '"presend_attempt_land"' in l:
                e=json.loads(l)
                if e.get('first_rx') and e.get('idx') is not None and e.get('slot'): S[e['slot']].append((e['first_rx'],e['idx']))
    return S
def fit(S):
    rs=[]
    for s,v in S.items():
        v=sorted(v,key=lambda x:x[1])
        for (t1,i1),(t2,i2) in zip(v,v[1:]):
            if i2-i1>=50: rs.append((t2-t1)/(i2-i1))
    r=st.median(rs)
    start={s:st.median([t-r*i for t,i in v]) for s,v in S.items() if len(v)>=3}
    return r,start
if __name__=='__main__':
    out={}
    for d in sys.argv[1:]:
        S=samples(d); r,start=fit(S); out[d]=dict(r=r,start=start)
        s=sorted(start); g=sorted((start[b]-start[a])/1e6 for a,b in zip(s,s[1:]) if b==a+1)
        print(d,'slots',len(start),'ns/idx',round(r),'slot len p10/50/90',[round(g[int(p*len(g))],1) for p in (.1,.5,.9)],file=sys.stderr)
    pickle.dump(out,open('/home/moiz/sniper-data/postsend/slotclock.pkl','wb'))
