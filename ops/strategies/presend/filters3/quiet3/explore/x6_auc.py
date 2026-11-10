from lib import *
import json
T=load2()
of=json.load(open('ourfol.json'))
for t in T:
    t.update(of[str(t['run'])+t['mint']+str(t['pid'])+str(t['t'])])
    t['whf0']=t['whf'] if t['whf'] is not None and t['whf']>=0 else 0.0
    t['tsol']=(t['trig_sol'] or 0)/1e9
def auc(X,f):
    # P(score_fol > score_nf): >0.5 means higher value -> followed
    a=[t[f] for t in X if t['nf'] and t.get(f) is not None]; b=[t[f] for t in X if not t['nf'] and t.get(f) is not None]
    if len(a)<10 or len(b)<10: return None
    import bisect
    sb=sorted(b); s=0
    for v in a:
        lo=bisect.bisect_left(sb,v); hi=bisect.bisect_right(sb,v)
        s+=(len(sb)-hi)+0.5*(hi-lo)
    return s/len(a)/len(b)
F=['n60','n120','nb50','whf0','whd','coh','since_last','maxdd','pct','tsol','age_slots','vsol','cr','sat','mk_n5','mk_wb15','mk_v15','mk_bots60','tk_n','tk_buyers','act2_5','actfr6_15','ourfol2','p_tr20','p_tr50','p_tr150','p_ub20','p_ub50','p_ub150','p_us50','p_bs50','p_last','p_first','p_bots','p_bots_buy','q_tr2','q_ub2','q_bot2','q_ub3','q_bs3','q_bot3','q_ub5']
for kind in ('T2','rearm'):
    print(kind)
    for f in F:
        r=[]
        for sp in ('DEV','VAL'):
            X=[t for t in T if t['kind']==kind and t['split']==sp]
            a=auc(X,f); n=sum(1 for t in X if t.get(f) is not None)
            r.append('%s %s n=%4d'%(sp,'%.3f'%a if a else '  -  ',n))
        print('  %-11s'%f,' | '.join(r))
