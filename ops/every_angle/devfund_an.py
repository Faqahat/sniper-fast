import json, statistics
from collections import Counter
df=json.load(open('/root/every_angle/devfund.json'))   # creator -> {funder,...}
tape=json.load(open('/root/mirror/his_tape.json'))
# map creator -> list of his picks (with outcomes)
bycre={}
for d in tape:
    if d.get('creator') and d.get('peak_r') is not None:
        bycre.setdefault(d['creator'],[]).append(d)
funder_of={c:(v.get('funder') if v and 'funder' in v else None) for c,v in df.items()}
fc=Counter(f for f in funder_of.values() if f)
print("distinct creators funded:",sum(1 for v in funder_of.values() if v),"/",len(funder_of))
print("distinct funders:",len(fc))
print("top funders (creators funded):")
for f,n in fc.most_common(12): print(f"  {n:3d}  {f}")
# how concentrated: share of his picks whose creator is funded by a top-K funder cluster
topK={f for f,_ in fc.most_common(5)}
# build per-pick funder, outcome
picks=[]
for d in tape:
    if d.get('peak_r') is None: continue
    c=d.get('creator'); f=funder_of.get(c)
    picks.append(dict(slot=d['create_slot'], f=f, peak=d['peak_r'], rr=d['realized_R'], c=c))
picks=[p for p in picks if p['slot'] is not None]
picks.sort(key=lambda p:p['slot'])
N=len(picks); h=N//2; IS=picks[:h]; OOS=picks[h:]
def mp(g,k='peak'): return statistics.mean([x[k] for x in g]) if g else float('nan')
def wr(g): return sum(1 for x in g if x['rr']>0)/len(g) if g else float('nan')
print(f"\npicks with slot+outcome: N={N} IS={len(IS)} OOS={len(OOS)}")
sh=sum(1 for p in picks if p['f'] in topK)/N
print(f"share of his picks funded by top-5 funder cluster: {sh:.3f}")
# OOS: build cluster from IS funders appearing >=2, test whether cluster membership predicts peak OOS
clus={f for f,n in Counter(p['f'] for p in IS if p['f']).items() if n>=2}
print(f"IS recurring-funder cluster size (>=2 picks): {len(clus)}")
ina=[p for p in OOS if p['f'] in clus]; out=[p for p in OOS if p['f'] not in clus]
print(f"OOS: in-cluster n={len(ina)} meanpeak={mp(ina):.3f} winrate={wr(ina):.2f} | out n={len(out)} meanpeak={mp(out):.3f} winrate={wr(out):.2f}")
json.dump({'topK':list(topK),'share':sh}, open('/root/every_angle/devfund_done.json','w'))
