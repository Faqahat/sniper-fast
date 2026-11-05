# Step 2: parse the two FRA probe runs (r30, r31) -> dumps + fills (fire joined to buy_land by signature, as probe_report.py)
import sys,json,re,collections,pickle
sys.dont_write_bytecode=True
R={'r30':'/home/moiz/sniper-data/runs/fra_r30/dip_r30','r31':'/home/moiz/sniper-data/runs/fra_r31/dip_r31'}
OUT='/home/moiz/sniper-data/vulture_probe_score/probe.pkl'
OURS={"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE","EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
res={}
for run,p in R.items():
    dumps=[];fires=[];land={};tim={};close={};tape=collections.defaultdict(list);start=end=None;fails=[]
    for l in open(p+'.jsonl',errors='replace'):
        d=json.loads(l);e=d.get('ev')
        if e=='dump': dumps.append(d)
        elif e=='fire': fires.append(d)
        elif e=='buy_land': land[d['sig']]=d
        elif e=='timing': tim[d['buy_sig_seen']]=d; tim[d['buy_sig']]=d
        elif e=='close': close[d['buy_sig']]=d
        elif e=='tape': tape[d['mint']].append(d)
        elif e=='run_start': start=d
        elif e=='run_end': end=d
    pnl=collections.defaultdict(list)
    for l in open(p+'.log',errors='replace'):
        m=re.search(r"REALIZED mint=(\S+) pnl=([-+0-9.]+)",l)
        if m: pnl[m.group(1)].append(float(m.group(2)))
    pi=collections.Counter();F=[]
    for f in fires:
        sigs={v['sig'] for v in f.get('variants',[])}|{f['buy_sig']}|{q['sig'] for q in (f.get('nonce') or {}).get('per_path',[])}
        b=next((land[s] for s in sigs if s in land),None)
        r=dict(run=run,mint=f['mint'],dump_sig=f.get('dump_sig'),fire_t=f.get('t'),landed=b is not None,sell=f.get('sell'),client=f.get('client'),leader=f.get('leader'))
        c=next((close[s] for s in sigs if s in close),{})
        r.update(dump_slot=c.get('dump_slot'),dump_idx=c.get('dump_idx'),result=c.get('result'))
        if b:
            t=tim.get(b['sig']) or {};c2=t.get('clock2') or {}
            k=pi[f['mint']];pi[f['mint']]+=1
            sl=c.get('sell_land') or [None,None,None]
            oth=[x for x in tape[f['mint']] if x['buy'] and x['user'] not in OURS]
            ds,di=c.get('dump_slot'),c.get('dump_idx')
            before=[x for x in oth if ds is not None and (ds,di)<(x['slot'],x['idx'])<(b['slot'],b['idx'])]
            after=[x for x in oth if (x['slot'],x['idx'])>(b['slot'],b['idx']) and (sl[0] is None or (x['slot'],x['idx'])<(sl[0],sl[1]))]
            r.update(buy_sig=b['sig'],buy_slot=b['slot'],buy_idx=b['idx'],buy_sol=b['sol']/1e9,buy_vsol=b['vsol'],buy_vtok=b['vtok'],tokens=b['tokens'],
                     same=b['slots_after_dump']==0,feed_ms=b['rx_ms_after_dump'],pos_ms=c2.get('land_ms_pos'),buy_pos=c2.get('buy_pos'),dump_pos=c2.get('dump_pos'),
                     slot_txs=c2.get('buy_slot_txs'),first=len(before)==0,n_after=len(after),sol_after=sum(x['sol'] for x in after)/1e9,
                     sell_land=sl,exit_why=c.get('exit_why'),dump_vsol=c.get('dump_vsol'),dump_vtok=c.get('dump_vtok'),
                     pnl=pnl[f['mint']][k] if k<len(pnl[f['mint']]) else None)
        F.append(r)
    res[run]=dict(dumps=dumps,fires=F,start=start,end=end,nrealized=sum(len(v) for v in pnl.values()),realized=sum(sum(v) for v in pnl.values()))
    L=[r for r in F if r['landed']]
    print(run,'dumps',len(dumps),'fires',len(F),'landed',len(L),'pnl sum',round(sum(r['pnl'] or 0 for r in L),4),'realized lines',res[run]['nrealized'],round(res[run]['realized'],4),
          'slots',min(d['slot'] for d in dumps),max(d['slot'] for d in dumps),'t',start['t']/1e9,end['t']/1e9,'missing pnl',sum(r['pnl'] is None for r in L))
pickle.dump(res,open(OUT,'wb'))
