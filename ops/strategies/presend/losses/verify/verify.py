"""Independent check of 'skip arm when trigger age_slots<2' (+ whale>=6 SOL, +Firedancer) on live pre-send runs.
P&L = presend_live_realized.pnl (wallet deltas of buy+sell txs, rent back included; failed tries NOT included)."""
import json, glob, os, random, sys, collections
L='/home/moiz/sniper-data/runs'; V='/home/moiz/sniper-data/presend_losses/verify/raw'
runs=[('FRA',f'r{n}',f'{L}/fra/runs/dip_r{n}.jsonl') for n in (21,22,23,24,26,27,28)]
runs+=[('AMS',f'r{n}',f'{L}/ams/runs/dip_ams_r{n}.jsonl') for n in (16,17,19,20,24,25,26,27,34,35)]
runs+=[('AMS',f'r{n}',f'{V}/dip_ams_r{n}.jsonl') for n in (28,29,30,31,32,33,36)]
PKT=5*3600
rows=[];fills=[]
for reg,r,p in runs:
    arm={};fill={};real=collections.defaultdict(int);ts=[];stop=None;spend=None;un=collections.Counter();disarm={}
    for line in open(p):
        if '"presend_live' not in line: 
            continue
        d=json.loads(line); ev=d['ev']
        if 't' in d and isinstance(d['t'],int): ts.append(d['t'])
        if ev=='presend_live_arm': arm[d['w']]=d; spend=d['spend']
        elif ev=='presend_live_fill' and d['w'] not in fill: fill[d['w']]=d
        elif ev=='presend_live_realized': real[d['w']]+=d['pnl']
        elif ev=='presend_live_disarm': disarm[d['w']]=d
        elif ev=='presend_live_stop': stop=d
        elif ev=='presend_live_skip' and d['why']=='create_slot': un['skip0']+=1
    for w,pnl in real.items():
        a=arm[w]['trig']; f=fill.get(w,{})
        fills.append(dict(reg=reg,run=r,w=w,mint=a['mint'],age=a['age_slots'],wsol=a['sol']/1e9,whale=a['wallet'],client=f.get('client'),
            pnl=pnl/1e9,size=spend/1e9,t=a['t'],pct=a['pct']))
    # unfilled arms by age (attempts)
    ua=collections.Counter()
    for w,d in disarm.items():
        if not d.get('filled') and w in arm: ua[min(arm[w]['trig']['age_slots'],2)]+=d.get('attempts',0)
    tot_att=sum(d.get('attempts',0) for d in disarm.values())
    rows.append(dict(reg=reg,run=r,t0=min(ts),t1=max(ts),size=spend/1e9,fees=(stop or {}).get('fees'),skip0=un['skip0'],
        att_un_age1=ua[1],att_all=tot_att,arms_age1=sum(1 for x in arm.values() if x['trig']['age_slots']==1)))
json.dump(dict(rows=rows,fills=fills),open('/home/moiz/sniper-data/presend_losses/verify/fills.json','w'))
print(len(fills))
