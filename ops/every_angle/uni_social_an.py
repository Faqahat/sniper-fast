import json, statistics
us=json.load(open('/root/every_angle/uni_social.json'))
hs=json.load(open('/root/every_angle/his_social.json'))
# universe resolved
ur=[v for v in us.values() if v['feat']]
print(f"UNIVERSE: sampled {len(us)}, socials resolved {len(ur)}")
def rate(rows,k): return sum(r['feat'][k] for r in rows)/len(rows) if rows else float('nan')
print("  universe resolved socials:", {k:round(rate(ur,k),2) for k in ['twitter','telegram','website','image','desc']})
# his resolved
hr=[v for v in hs.values() if v]
print(f"HIS: resolved {len(hr)}")
print("  his resolved socials:", {k:round(sum(r[k] for r in hr)/len(hr),2) for k in ['twitter','telegram','website','image','desc']})
# socials -> pump in universe (resolved, with peak), OOS by slot
rows=[dict(slot=v['slot'],peak=v['peak'],**v['feat']) for v in us.values() if v['feat'] and v['peak'] is not None]
rows.sort(key=lambda r:r['slot']); h=len(rows)//2; OOS=rows[h:]
def runr(g): return sum(1 for r in g if r['peak']>=1.5)/len(g) if g else float('nan')
print(f"\nsocials->pump in universe (OOS n={len(OOS)}):")
for f in ['twitter','website','desc']:
    a=[r for r in OOS if r[f]]; b=[r for r in OOS if not r[f]]
    print(f"  {f:8s}: has n={len(a)} pump>=1.5={runr(a):.3f} | no n={len(b)} pump>=1.5={runr(b):.3f}")
a=[r for r in OOS if (r['twitter']+r['website']+r['telegram'])>=2]; b=[r for r in OOS if (r['twitter']+r['website']+r['telegram'])<2]
print(f"  n_social>=2: n={len(a)} pump={runr(a):.3f} | <2 n={len(b)} pump={runr(b):.3f}")
