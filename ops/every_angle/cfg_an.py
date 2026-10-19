import json, statistics
hc=json.load(open('/root/every_angle/his_config.json'))
tape={d['mint']:d for d in json.load(open('/root/mirror/his_tape.json'))}
C=json.load(open('/root/profit_backtest/creates.json'))
good=[(m,v) for m,v in hc.items() if v and 'mayhem' in v]
print(f"his config parsed: {len(good)}/{len(hc)}")
def rate(items,pred,den=None):
    den=den or items
    return sum(1 for m,v in items if pred(v))/len(items)
print("\nHIS picks config distribution:")
print(f"  is_v2:         {sum(1 for m,v in good if v.get('is_v2'))/len(good):.2f}")
print(f"  mayhem==1:     {sum(1 for m,v in good if v.get('mayhem')==1)/len(good):.2f}")
print(f"  holder_rew==1: {sum(1 for m,v in good if v.get('holder_reward')==1)/len(good):.2f}")
print(f"  fee_bps>0:     {sum(1 for m,v in good if (v.get('creator_fee_bps') or 0)>0)/len(good):.2f}")
print("\nUNIVERSE config distribution:")
print(f"  is_v2:         {sum(1 for c in C if c.get('is_v2'))/len(C):.2f}")
print(f"  mayhem==1:     {sum(1 for c in C if c.get('mayhem')==1)/len(C):.2f}")
print(f"  holder_rew==1: {sum(1 for c in C if c.get('holder_reward')==1)/len(C):.2f}")
print(f"  fee_bps>0:     {sum(1 for c in C if (c.get('creator_fee_bps') or 0)>0)/len(C):.2f}")
# does his mayhem/holder choice relate to his pump outcome? (OOS)
rows=[]
for m,v in good:
    d=tape.get(m)
    if not d or d.get('peak_r') is None or d.get('create_slot') is None: continue
    rows.append(dict(slot=d['create_slot'],peak=d['peak_r'],rr=d['realized_R'],
                     mayhem=v.get('mayhem'),hr=v.get('holder_reward')))
rows.sort(key=lambda r:r['slot']); h=len(rows)//2; OOS=rows[h:]
def mp(g): return statistics.mean([r['peak'] for r in g]) if g else float('nan')
def wr(g): return sum(1 for r in g if r['rr']>0)/len(g) if g else float('nan')
print(f"\nHIS picks: config vs his outcome (OOS n={len(OOS)}):")
for f in ['mayhem','hr']:
    a=[r for r in OOS if r[f]==1]; b=[r for r in OOS if r[f]==0]
    print(f"  {f:7s}=1 n={len(a)} meanpeak={mp(a):.3f} wr={wr(a):.2f} | =0 n={len(b)} meanpeak={mp(b):.3f} wr={wr(b):.2f}")
