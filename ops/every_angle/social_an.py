import json, statistics
soc=json.load(open('/root/every_angle/his_social.json'))
tape={d['mint']:d for d in json.load(open('/root/mirror/his_tape.json'))}
rows=[]
for m,f in soc.items():
    if not f: continue
    d=tape.get(m)
    if not d or d.get('peak_r') is None or d.get('create_slot') is None: continue
    rows.append(dict(slot=d['create_slot'], peak=d['peak_r'], rr=d['realized_R'], **f))
rows.sort(key=lambda r:r['slot'])
N=len(rows)
print(f"his picks with socials fetched & outcome: {N}")
print(f"socials presence among his picks: twitter={sum(r['twitter'] for r in rows)/N:.2f} telegram={sum(r['telegram'] for r in rows)/N:.2f} website={sum(r['website'] for r in rows)/N:.2f} image={sum(r['image'] for r in rows)/N:.2f} desc={sum(r['desc'] for r in rows)/N:.2f}")
h=N//2; IS=rows[:h]; OOS=rows[h:]
def mp(g): return statistics.mean([r['peak'] for r in g]) if g else float('nan')
def wr(g): return sum(1 for r in g if r['rr']>0)/len(g) if g else float('nan')
for feat in ['twitter','telegram','website','image','desc']:
    a=[r for r in OOS if r[feat]]; b=[r for r in OOS if not r[feat]]
    print(f"  OOS {feat:9s}: has n={len(a)} meanpeak={mp(a):.3f} wr={wr(a):.2f} | no n={len(b)} meanpeak={mp(b):.3f} wr={wr(b):.2f}")
# n_social >=2
a=[r for r in OOS if r['n_social']>=2]; b=[r for r in OOS if r['n_social']<2]
print(f"  OOS n_social>=2: n={len(a)} meanpeak={mp(a):.3f} wr={wr(a):.2f} | <2 n={len(b)} meanpeak={mp(b):.3f} wr={wr(b):.2f}")
# error breakdown
errs=sum(1 for v in soc.values() if v is None)
print(f"fetch failures (None): {errs}/{len(soc)}")
