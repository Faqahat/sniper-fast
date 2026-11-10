import json, random, datetime, collections
D=json.load(open('/home/it/sniper-data/presend_losses/verify/fills.json'))
R=D['rows']; F=D['fills']; CUR=0.696
pkt=lambda ns: datetime.datetime.utcfromtimestamp(ns/1e9+5*3600).strftime('%m-%d %H:%M')
rules={'age1':lambda f:f['age']==1,'w6':lambda f:f['wsol']>=6,'w6fd':lambda f:f['wsol']>=6 and (f['client'] or '').lower().startswith('fire'),
 'combo':lambda f:f['age']==1 or (f['wsol']>=6 and (f['client'] or '').lower().startswith('fire'))}
def boot(x,n=10000):
    random.seed(1); s=sorted(sum(random.choice(x) for _ in x) for _ in range(n)) if x else [0]
    return s[int(.05*len(s))],s[int(.95*len(s))]
hrs=lambda rs: sum((r['t1']-r['t0'])/3.6e12 for r in rs)
print('clients',collections.Counter(f['client'] for f in F))
print('age0 fills',[ (f['run'],f['reg']) for f in F if f['age']==0])
key=lambda f:(f['reg'],f['run'])
print('\n| reg | run | PKT span | h | size | fills | P&L | age1 n | age1 P&L | win/lose | rest | unfilled age1 tries | w6 n/P&L | w6+FD n/P&L |')
for r in R:
    fs=[f for f in F if key(f)==(r['reg'],r['run'])]
    a=[f for f in fs if f['age']==1]; w6=[f for f in fs if rules['w6'](f)]; fd=[f for f in fs if rules['w6fd'](f)]
    print(f"| {r['reg']} | {r['run']} | {pkt(r['t0'])}–{pkt(r['t1'])[6:]} | {(r['t1']-r['t0'])/3.6e12:.1f} | {r['size']:.3f} | {len(fs)} | {sum(f['pnl'] for f in fs):+.3f} | {len(a)} | {sum(f['pnl'] for f in a):+.3f} | {sum(f['pnl']>0 for f in a)}/{sum(f['pnl']<=0 for f in a)} | {sum(f['pnl'] for f in fs if f['age']!=1):+.3f} | {r['att_un_age1']} | {len(w6)}/{sum(f['pnl'] for f in w6):+.3f} | {len(fd)}/{sum(f['pnl'] for f in fd):+.3f} |")
used={('FRA','r28'),('AMS','r34'),('AMS','r35'),('AMS','r36')}
for name,rule in rules.items():
  for lab,sel in [('ALL',lambda k:True),('OOS (not r28/34/35/36)',lambda k:k not in used),('used 4',lambda k:k in used)]:
    rs=[r for r in R if sel((r['reg'],r['run']))]; fs=[f for f in F if sel(key(f))]
    sk=[f for f in fs if rule(f)]; saved=-sum(f['pnl'] for f in sk); savedN=-sum(f['pnl']*CUR/f['size'] for f in sk)
    h=hrs(rs); tot=sum(f['pnl'] for f in fs)
    lo,hi=boot([-f['pnl'] if rule(f) else 0 for f in fs]) if fs else (0,0)
    top5=saved-sum(sorted([-f['pnl'] for f in sk],reverse=True)[:5])
    per=collections.defaultdict(float)
    for f in sk: per[key(f)]-=f['pnl']
    helps=sum(1 for r in rs if per[(r['reg'],r['run'])]>0); hurts=sum(1 for r in rs if per[(r['reg'],r['run'])]<0)
    print(f"{name:6} {lab:22} runs {len(rs)} h {h:.1f} fills {len(fs)} P&L {tot:+.3f} skip {len(sk)} (W{sum(f['pnl']>0 for f in sk)}/L{sum(f['pnl']<=0 for f in sk)}) saved {saved:+.3f} ({saved/abs(tot)*100 if tot else 0:.0f}% of |P&L|) /h {saved/h:+.4f} /day {saved/h*24:+.2f} | @0.696 INFERRED {savedN:+.3f} /day {savedN/h*24:+.2f} | CI90 [{lo:+.3f},{hi:+.3f}] | w/o top5 {top5:+.3f} | runs help {helps} hurt {hurts}")
a=[f for f in F if f['age']==1]
print('\nage1 by PKT hour',sorted(collections.Counter(int(pkt(f['t'])[6:8]) for f in a).items()))
print('top whales',collections.Counter(f['whale'][:8] for f in a).most_common(4))
print('mints repeated',collections.Counter(f['mint'] for f in a).most_common(2))
print('age1 by size-ratio:', [ (f['run'],round(f['pnl'],3)) for f in sorted(a,key=lambda f:f['pnl'])[:6]])
print('age dist P&L', {k:(len(v),round(sum(v),3)) for k,v in sorted(((k,[f['pnl'] for f in F if min(f['age'],10)==k]) for k in range(11)))})
