import sys, json
sys.path.insert(0, '/root/every_angle')
from ea_common import *

tape = load_tape()
# keep ones with price path / peak for outcome tests
withpk = [d for d in tape if d.get('peak_r') is not None and d.get('create_slot') is not None and d.get('sol_in') is not None]
print(f"N total={len(tape)}  with peak_r={len(withpk)}")
IS, OOS = split_oos(withpk)
print(f"IS n={len(IS)}  OOS n={len(OOS)}  split_slot={OOS[0]['create_slot']}")

def corr(xs, ys):
    pairs=[(x,y) for x,y in zip(xs,ys) if x is not None and y is not None]
    if len(pairs)<3: return float('nan')
    import math
    xs=[p[0] for p in pairs]; ys=[p[1] for p in pairs]
    mx=sum(xs)/len(xs); my=sum(ys)/len(ys)
    sx=math.sqrt(sum((x-mx)**2 for x in xs)); sy=math.sqrt(sum((y-my)**2 for y in ys))
    if sx==0 or sy==0: return float('nan')
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/(sx*sy)

def spearman(xs, ys):
    pairs=[(x,y) for x,y in zip(xs,ys) if x is not None and y is not None]
    if len(pairs)<3: return float('nan')
    def rank(vs):
        order=sorted(range(len(vs)), key=lambda i:vs[i])
        r=[0]*len(vs)
        for rnk,i in enumerate(order): r[i]=rnk
        return r
    rx=rank([p[0] for p in pairs]); ry=rank([p[1] for p in pairs])
    return corr(rx,ry)

print("\n========== HYP 5: BUY-SIZE AS CONVICTION ==========")
print("Does his own sol_in (position size) predict token's forward outcome?")
for name, grp in [('ALL',withpk),('IS',IS),('OOS',OOS)]:
    si=[d['sol_in'] for d in grp]
    for ok in ['peak_r','r5','r10','r20','realized_R']:
        yy=[d.get(ok) for d in grp]
        print(f"  {name:4s} corr(sol_in, {ok:9s})= {corr(si,yy):+.3f}  spearman={spearman(si,yy):+.3f}")
    print()
# tercile analysis on sol_in -> peak_r
def terciles(grp, feat, out='peak_r'):
    g=sorted([d for d in grp if d.get(feat) is not None and d.get(out) is not None], key=lambda d:d[feat])
    n=len(g); t=n//3
    lo=g[:t]; hi=g[-t:]
    return (mean([d[out] for d in lo]), mean([d[out] for d in hi]),
            winrate([d['realized_R'] for d in lo]), winrate([d['realized_R'] for d in hi]), t)
for name,grp in [('IS',IS),('OOS',OOS)]:
    lo,hi,wlo,whi,t = terciles(grp,'sol_in','peak_r')
    print(f"  {name} sol_in terciles (n={t} each): peak_r lo={lo:.3f} hi={hi:.3f} lift={hi-lo:+.3f}; realized winrate lo={wlo:.2f} hi={whi:.2f}")

print("\n========== HYP 4b: INTERTRADE MOMENTUM (his own book) ==========")
# order by create_slot; does prev trade result predict next outcome? does size change after win?
t = sorted(withpk, key=lambda d:d['create_slot'])
# prev realized win -> next realized_R / peak_r
after_win=[]; after_loss=[]
sz_after_win=[]; sz_after_loss=[]
for i in range(1,len(t)):
    prev_win = t[i-1]['realized_R']>0
    (after_win if prev_win else after_loss).append(t[i])
    (sz_after_win if prev_win else sz_after_loss).append(t[i]['sol_in'])
print(f"  next realized_R  after WIN n={len(after_win)} mean={mean([d['realized_R'] for d in after_win]):+.4f} win={winrate([d['realized_R'] for d in after_win]):.2f}")
print(f"  next realized_R  after LOSS n={len(after_loss)} mean={mean([d['realized_R'] for d in after_loss]):+.4f} win={winrate([d['realized_R'] for d in after_loss]):.2f}")
print(f"  next peak_r      after WIN mean={mean([d['peak_r'] for d in after_win]):.3f}  after LOSS mean={mean([d['peak_r'] for d in after_loss]):.3f}")
print(f"  next sol_in      after WIN mean={mean(sz_after_win):.3f}  after LOSS mean={mean(sz_after_loss):.3f}  (does he size up after win?)")
# rolling hit-rate (last 5) -> next outcome
import statistics
hr=[]; nxt=[]
for i in range(5,len(t)):
    recent=[1 if t[j]['realized_R']>0 else 0 for j in range(i-5,i)]
    hr.append(sum(recent)/5); nxt.append(t[i]['realized_R'])
print(f"  corr(recent5 hitrate, next realized_R)= {corr(hr,nxt):+.3f}")

print("\n========== HYP 4: TIME-OF-DAY / SESSION / BURST (slot-based) ==========")
# burst: intertrade gap in slots. small gap = burst.
gaps=[t[i]['create_slot']-t[i-1]['create_slot'] for i in range(1,len(t))]
print(f"  intertrade slot gap: median={median(gaps):.0f} mean={mean(gaps):.0f} min={min(gaps)} (1 slot~0.4s)")
# define burst = gap to prev <= 150 slots (~60s)
burst=[]; nonburst=[]
for i in range(1,len(t)):
    (burst if (t[i]['create_slot']-t[i-1]['create_slot'])<=150 else nonburst).append(t[i])
print(f"  BURST (<=150 slots from prev) n={len(burst)} realized mean={mean([d['realized_R'] for d in burst]):+.4f} win={winrate([d['realized_R'] for d in burst]):.2f} peak={mean([d['peak_r'] for d in burst]):.3f}")
print(f"  NONBURST                      n={len(nonburst)} realized mean={mean([d['realized_R'] for d in nonburst]):+.4f} win={winrate([d['realized_R'] for d in nonburst]):.2f} peak={mean([d['peak_r'] for d in nonburst]):.3f}")
# save for report
json.dump({'n':len(withpk)}, open('/root/every_angle/cheap_done.json','w'))
