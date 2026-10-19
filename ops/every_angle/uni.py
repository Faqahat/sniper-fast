import json, math, statistics
C=json.load(open('/root/profit_backtest/creates.json'))
T=json.load(open('/root/profit_backtest/trajectories.json'))
traj={x['mint']:x for x in T}
def peak(x):
    s=x.get('series') or []; e=x.get('entry_px')
    if not s or not e: return None
    px=[p[1] for p in s if isinstance(p,list) and len(p)>=2]
    return (max(px)/e) if px else None
rows=[]
for c in C:
    tr=traj.get(c['mint'])
    if not tr: continue
    pk=peak(tr)
    if pk is None: continue
    rows.append(dict(slot=c['create_slot'], peak=pk,
        mayhem=c.get('mayhem'), fee=c.get('creator_fee_bps'), hr=c.get('holder_reward'),
        dev_buy=c.get('dev_buy'), entry_px=c.get('entry_px'),
        cosnipers=tr.get('cosnipers'), n=tr.get('n')))
rows.sort(key=lambda r:r['slot'])
N=len(rows); h=N//2; IS=rows[:h]; OOS=rows[h:]
print(f"universe rows with peak: N={N}  IS={len(IS)} OOS={len(OOS)}")
PUMP_THR=2.0   # "pump" = peak >= 2x
def rate(g): 
    return sum(1 for r in g if r['peak']>=PUMP_THR)/len(g) if g else float('nan')
def mp(g): return statistics.mean([r['peak'] for r in g]) if g else float('nan')
print(f"baseline: pump(>=2x) rate IS={rate(IS):.3f} OOS={rate(OOS):.3f}  meanpeak IS={mp(IS):.3f} OOS={mp(OOS):.3f}")

def test_bool(name, pred):
    print(f"\n-- {name} --")
    for nm,g in [('IS',IS),('OOS',OOS)]:
        a=[r for r in g if pred(r)]; b=[r for r in g if not pred(r)]
        print(f"  {nm}: TRUE n={len(a)} pumprate={rate(a):.3f} meanpeak={mp(a):.3f} | FALSE n={len(b)} pumprate={rate(b):.3f} meanpeak={mp(b):.3f} | lift_rate={rate(a)-rate(b):+.3f}")

test_bool("mayhem==1", lambda r:r['mayhem']==1)
test_bool("creator_fee_bps>0", lambda r:(r['fee'] or 0)>0)
test_bool("holder_reward==1", lambda r:r['hr']==1)

def corr(xs,ys):
    pr=[(x,y) for x,y in zip(xs,ys) if x is not None and y is not None]
    if len(pr)<3: return float('nan')
    xs=[p[0] for p in pr]; ys=[p[1] for p in pr]
    mx=statistics.mean(xs); my=statistics.mean(ys)
    sx=math.sqrt(sum((x-mx)**2 for x in xs)); sy=math.sqrt(sum((y-my)**2 for y in ys))
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/(sx*sy) if sx and sy else float('nan')

print("\n== HYP 5 EARLY-FLOW proxy (cosnipers, n trades in window) vs peak ==")
print("  NOTE: cosnipers/n are CONTEMPORANEOUS (measured over the trade window), not strictly pre-buy.")
for nm,g in [('IS',IS),('OOS',OOS)]:
    cs=[r['cosnipers'] for r in g]; nn=[r['n'] for r in g]; pk=[r['peak'] for r in g]
    print(f"  {nm}: corr(cosnipers,peak)={corr(cs,pk):+.3f}  corr(n,peak)={corr(nn,pk):+.3f}")
# tercile on cosnipers
def terc(feat):
    g=sorted([r for r in OOS if r.get(feat) is not None], key=lambda r:r[feat])
    t=len(g)//3; lo=g[:t]; hi=g[-t:]
    return mp(lo),mp(hi),rate(lo),rate(hi),t
lo,hi,rl,rh,t=terc('cosnipers')
print(f"  OOS cosnipers terciles(n={t}): meanpeak lo={lo:.3f} hi={hi:.3f}  pumprate lo={rl:.3f} hi={rh:.3f}  lift={rh-rl:+.3f}")

print("\n== dev_buy & entry_px vs peak (pre-buy knowable) ==")
for nm,g in [('IS',IS),('OOS',OOS)]:
    db=[r['dev_buy'] for r in g]; ep=[r['entry_px'] for r in g]; pk=[r['peak'] for r in g]
    print(f"  {nm}: corr(dev_buy,peak)={corr(db,pk):+.3f}  corr(entry_px,peak)={corr(ep,pk):+.3f}")

json.dump({'N':N,'base_oos':rate(OOS)}, open('/root/every_angle/uni_done.json','w'))
