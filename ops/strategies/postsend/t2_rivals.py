"""Task 2: rivals vs us on the same dump/slot (AMS r49..r55 pre-send attempts with a dump d before our tx).
All times MEASURED on our feed clock (first_rx = first time the tx appeared on any of our shred feeds).
head  = d.first_rx - our t_send (ms; >0: our tx was already sent when the dump appeared on our feed)
our_d = our first_rx - d.first_rx ; riv_d = rival first_rx - d.first_rx
'reactive rival' = a buy landing after the dump, before us, with riv_d >= 3 ms (could not be pre-sent in the dump's burst)."""
import json,glob,collections
B='/home/moiz/sniper-data/runs/'
RUNS=['ams_r49','ams_r50','ams_r51','ams_r52','ams_r53','ams_r54','ams_r55_snap']
def q(v,p):
    v=sorted(x for x in v if x is not None); return round(v[min(len(v)-1,int(p*len(v)))],1) if v else None
A=[]
for d in RUNS:
    f=[x for x in glob.glob(B+d+'/*.jsonl') if not x.endswith('obs.jsonl')][0]
    for l in open(f):
        if '"presend_attempt_land"' not in l or '"d":' not in l: continue
        e=json.loads(l)
        D=e.get('d'); 
        if not D or not D.get('first_rx') or not e.get('first_rx'): continue
        head=(D['first_rx']-e['t_send'])/1e6
        our_d=(e['first_rx']-D['first_rx'])/1e6
        riv=[]
        for b in e.get('between',[]):
            if b.get('buy') and b.get('first_rx'):
                riv.append(dict(user=b['user'],d=(b['first_rx']-D['first_rx'])/1e6,slot=b['slot'],idx=b['idx'],sol=b['sol']))
        A.append(dict(sig=e['sig'][:16],run=d,path=e['path'],client=e['client'],res=e['res'],head=head,our_d=our_d,s2f=e['ms_send_to_first_rx'],
            slot=e['slot'],idx=e['idx'],dslot=D['slot'],didx=D['idx'],dsol=D['sol'],drop=D['drop_pct'],n_between=e['n_between'],riv=riv,kind=e.get('kind'),
            sas=e.get('slots_after_send')))
json.dump(A,open('/home/moiz/sniper-data/postsend/t2_attempts.json','w'))
print('attempts with a dump before them:',len(A), collections.Counter(a['res'] for a in A))
# focus: we were in flight BEFORE the dump appeared (head>0), we landed in the dump's slot, and >=1 reactive rival landed between dump and us
S=[a for a in A if a['head']>0 and a['slot']==a['dslot']]
print('\nin flight before dump & landed in dump slot:',len(S))
R=[a for a in S if any(r['d']>=3 and r['slot']==a['slot'] for r in a['riv'])]
print('... of which a reactive rival (riv_d>=3ms) landed between dump and us:',len(R))
print('\n## head-start-lost cases by leader client: our head start, our dump->seen, first reactive rival dump->seen, our total send->seen')
print('| client | cases | of in-flight | head p50 | our dump->seen p50 | rival dump->seen p50 (p10) | our send->seen p50 | min transit gap p50 | idx ours/rival p50 |'); print('|---|---|---|---|---|---|---|---|---|')
for c in ['AgaveBam','JitoLabs','HarmonicAgave','HarmonicFiredancer','Firedancer','FireBAM','Agave','Rakurai','ALL']:
    s=[a for a in S if c=='ALL' or a['client']==c]; v=[a for a in R if c=='ALL' or a['client']==c]
    if not v: continue
    fr=[min(r['d'] for r in a['riv'] if r['d']>=3 and r['slot']==a['slot']) for a in v]
    fri=[min((r for r in a['riv'] if r['d']>=3 and r['slot']==a['slot']),key=lambda r:r['d'])['idx'] for a in v]
    # transit gap lower bound: (our send->seen) - (rival dump->seen): rival cannot have sent before dump executed (~d.first_rx - few ms)
    gap=[a['s2f']-f for a,f in zip(v,fr)]
    print(f"| {c} | {len(v)} | {len(s)} | {q([a['head'] for a in v],.5)} | {q([a['our_d'] for a in v],.5)} | {q(fr,.5)} ({q(fr,.1)}) | {q([a['s2f'] for a in v],.5)} | {q(gap,.5)} | {q([a['idx'] for a in v],.5)}/{q(fri,.5)} |")
print('\n## same split by our path')
for p in ('helius-ps','astralane-ps'):
    v=[a for a in R if a['path']==p]
    fr=[min(r['d'] for r in a['riv'] if r['d']>=3 and r['slot']==a['slot']) for a in v]
    print(p,len(v),'our s2f p50',q([a['s2f'] for a in v],.5),'rival d p50',q(fr,.5),'gap p50',q([a['s2f']-f for a,f in zip(v,fr)],.5))
# all reactive rivals (any of our attempts with d), rival dump->seen by client  (the field's speed)
print('\n## field speed: first reactive buyer after a dump (riv_d>=3, same slot as dump), by leader client of OUR attempt slot')
g=collections.defaultdict(list); seen=set()
for a in A:
    k=(a['dslot'],a['didx'])
    if k in seen: continue
    rr=[r['d'] for r in a['riv'] if r['d']>=3 and r['slot']==a['dslot']]
    if rr and a['slot']==a['dslot']: seen.add(k); g[a['client']].append(min(rr))
for c,v in sorted(g.items(),key=lambda kv:-len(kv[1])): print(c,len(v),'p10/p50/p90',q(v,.1),q(v,.5),q(v,.9))
# top rival wallets that beat an in-flight attempt
cnt=collections.Counter(); 
for a in R:
    r=min((r for r in a['riv'] if r['d']>=3 and r['slot']==a['slot']),key=lambda r:r['d']); cnt[r['user']]+=1
print('\ntop rivals beating in-flight attempts:',cnt.most_common(12))
