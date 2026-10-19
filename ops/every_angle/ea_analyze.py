import json, sys, math
from collections import Counter, defaultdict
from datetime import datetime, timezone
sys.path.insert(0,'/root/every_angle')
from ea_common import mean, median, winrate
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
d=json.load(open('/root/every_angle/slotdata.json'))
items=[(m,v) for m,v in d.items() if v['rows'] is not None and v.get('peak_r') is not None]
items.sort(key=lambda x:x[1]['create_slot'])
N=len(items)
half=N//2
IS=items[:half]; OOS=items[half:]
print(f"N={N}  IS={len(IS)} OOS={len(OOS)}")

def ext_buyers(v):
    """external successful buyers in create slot (exclude creator & him)."""
    cre=[r for r in v['rows'] if r['iscre']]
    dev=cre[0]['signer'] if cre else None
    s=set()
    for r in v['rows']:
        if r['isbuy'] and r['ok'] and r['signer']!=dev and r['signer']!=WALLET:
            s.add(r['signer'])
    return s
def flow(v):
    """create-slot flow features."""
    cre=[r for r in v['rows'] if r['iscre']]
    dev=cre[0]['signer'] if cre else None
    buys=[r for r in v['rows'] if r['isbuy'] and r['ok']]
    ext=[r for r in buys if r['signer']!=dev]
    ext_sol=sum(max(0,r['csol']) for r in ext)/1e9
    return dict(n_buys=len(buys), n_ext=len(ext),
                n_distinct_ext=len(set(r['signer'] for r in ext)),
                ext_sol=ext_sol)

print("\n========== HYP 1: SMART-MONEY CONSENSUS / COHORT ==========")
# cohort: co-buyer frequency across his tokens
freq=Counter()
for m,v in items:
    for w in ext_buyers(v): freq[w]+=1
print(f"distinct external co-buyers across his {N} tokens: {len(freq)}")
print("top recurring co-buyers (count of his tokens they also bought in create slot):")
for w,n in freq.most_common(15): print(f"  {n:3d}/{N}  {w}")
tokens_with_any_ext=sum(1 for m,v in items if ext_buyers(v))
print(f"his tokens with >=1 external create-slot co-buyer: {tokens_with_any_ext}/{N}")
# OOS causal test: build 'smart set' from IS (wallets appearing >=T times in IS), test OOS
for T in (2,3,4):
    smart={w for w,n in Counter(w for m,v in IS for w in ext_buyers(v)).items() if n>=T}
    # in OOS, does count of smart co-buyers predict peak_r?
    def kcount(v): return len(ext_buyers(v) & smart)
    hi=[v['peak_r'] for m,v in OOS if kcount(v)>=1]
    lo=[v['peak_r'] for m,v in OOS if kcount(v)==0]
    hr_hi=[v['realized_R'] for m,v in OOS if kcount(v)>=1]
    hr_lo=[v['realized_R'] for m,v in OOS if kcount(v)==0]
    print(f"  smartset(IS,T>={T}) size={len(smart)} | OOS: >=1 smart co-buyer n={len(hi)} peak={mean(hi):.3f} realR={mean(hr_hi):+.4f} | 0 smart n={len(lo)} peak={mean(lo):.3f} realR={mean(hr_lo):+.4f}")

print("\n========== HYP 6: FIRST-SLOT (create-slot) FLOW ==========")
def corr(xs,ys):
    pr=[(x,y) for x,y in zip(xs,ys) if x is not None and y is not None]
    if len(pr)<3: return float('nan')
    xs=[p[0] for p in pr]; ys=[p[1] for p in pr]
    mx=mean(xs); my=mean(ys)
    sx=math.sqrt(sum((x-mx)**2 for x in xs)); sy=math.sqrt(sum((y-my)**2 for y in ys))
    if sx==0 or sy==0: return float('nan')
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/(sx*sy)
for name,grp in [('IS',IS),('OOS',OOS)]:
    f=[flow(v) for m,v in grp]; pk=[v['peak_r'] for m,v in grp]; rr=[v['realized_R'] for m,v in grp]
    for key in ('n_ext','n_distinct_ext','ext_sol'):
        xs=[x[key] for x in f]
        print(f"  {name} corr({key:14s}, peak_r)={corr(xs,pk):+.3f}  corr(,realized_R)={corr(xs,rr):+.3f}")
    print()
# split: high ext-flow vs low, OOS
fl_is=[(flow(v)['n_ext']) for m,v in IS]
thr=sorted(fl_is)[len(fl_is)//2]
print(f"  median create-slot ext-buy count (IS) = {thr}")
hi=[v['peak_r'] for m,v in OOS if flow(v)['n_ext']>thr]; lo=[v['peak_r'] for m,v in OOS if flow(v)['n_ext']<=thr]
print(f"  OOS: high-flow(n_ext>{thr}) n={len(hi)} peak={mean(hi):.3f} | low n={len(lo)} peak={mean(lo):.3f} lift={mean(hi)-mean(lo):+.3f}")

print("\n========== HYP 4: TIME-OF-DAY (UTC hour from blocktime) ==========")
byhour=defaultdict(list)
for m,v in items:
    if v['blocktime']:
        h=datetime.fromtimestamp(v['blocktime'],timezone.utc).hour
        byhour[h].append(v)
print("  hour | n | realized_R mean | winrate | peak_r mean")
for h in sorted(byhour):
    g=byhour[h]
    print(f"   {h:02d}  | {len(g):3d} | {mean([x['realized_R'] for x in g]):+.4f} | {winrate([x['realized_R'] for x in g]):.2f} | {mean([x['peak_r'] for x in g]):.3f}")
span_bt=[v['blocktime'] for m,v in items if v['blocktime']]
print(f"  blocktime span hours: {(max(span_bt)-min(span_bt))/3600:.1f}h  ({datetime.fromtimestamp(min(span_bt),timezone.utc)} .. {datetime.fromtimestamp(max(span_bt),timezone.utc)})")

print("\n========== HYP 3: METADATA NAME/SYMBOL PATTERNS ==========")
def cmeta(v):
    cre=[r for r in v['rows'] if r['iscre'] and r['meta']]
    return cre[0]['meta'] if cre else None
uris=Counter()
for name,grp in [('IS',IS),('OOS',OOS)]:
    namelen=[]; symlen=[]; pk=[]
    for m,v in grp:
        cm=cmeta(v)
        if not cm: continue
        namelen.append(len(cm['name'])); symlen.append(len(cm['symbol'])); pk.append(v['peak_r'])
    print(f"  {name} corr(name_len,peak_r)={corr(namelen,pk):+.3f} corr(sym_len,peak_r)={corr(symlen,pk):+.3f}")
# uri host distribution
for m,v in items:
    cm=cmeta(v)
    if cm and cm['uri']:
        host=cm['uri'].split('/')[2] if '://' in cm['uri'] else cm['uri'][:20]
        uris[host]+=1
print("  uri host distribution:", dict(uris.most_common(8)))
# dump uris for social fetch
urilist={m:cmeta(v)['uri'] for m,v in items if cmeta(v) and cmeta(v).get('uri')}
json.dump(urilist, open('/root/every_angle/uris.json','w'))
print(f"  dumped {len(urilist)} uris for social fetch")
