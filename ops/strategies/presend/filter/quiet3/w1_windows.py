#!/usr/bin/env python3
"""QUIET3 step 2: every live pre-send ARM of the 24 verified runs -> one window (signals if logged, attempts, fill, realized P&L),
plus the QUIET skips (censored arms). Read-only on the run records. Output windows.json."""
import json, collections
L='/home/it/sniper-data/runs'; V='/home/it/sniper-data/presend_losses/verify/raw'
runs=[('FRA',f'r{n}',f'{L}/fra/runs/dip_r{n}.jsonl') for n in (21,22,23,24,26,27,28)]
runs+=[('AMS',f'r{n}',f'{L}/ams/runs/dip_ams_r{n}.jsonl') for n in (16,17,19,20,24,25,26,27,34,35)]
runs+=[('AMS',f'r{n}',f'{V}/dip_ams_r{n}.jsonl') for n in (28,29,30,31,32,33,36)]
OUT='/home/it/sniper-data/presend_quiet3/windows.json'
W=[];SK=[];meta={}
for reg,r,p in runs:
    seg=0;win={};qcfg=None;stopfees=None;nsk=collections.Counter()
    for line in open(p,errors='ignore'):
        if '"ev":"' not in line: continue
        if not ('presend_live' in line or '"run_start"' in line or 'presend_attempt"' in line): continue
        try: d=json.loads(line)
        except Exception: continue
        ev=d.get('ev')
        if ev=='run_start':
            seg+=1; c=d.get('cfg') or d
            q=json.dumps(d)
            if '"quiet"' in q and qcfg is None:
                import re; m=re.search(r'"quiet":(\{[^{}]*\})',q); qcfg=json.loads(m.group(1)) if m else True
            continue
        k=(seg,d.get('w'))
        if ev=='presend_live_arm':
            t=d['trig']; win[k]=dict(reg=reg,run=r,seg=seg,w=d['w'],mint=t['mint'],whale=t['wallet'],t=t['t'],slot=t['slot'],idx=t['idx'],
                age=t.get('age_slots'),pct=t.get('pct'),wsol=t['sol']/1e9,size=d['spend']/1e9,q=d.get('quiet'),att=0,filled=False,pnl=None,
                fill_off=None,why=None,en_slot=d.get('en_slot'))
        elif ev=='presend_live_fill' and k in win:
            x=win[k]
            if not x['filled']: x['filled']=True; x['fill_off']=d.get('slots_after_trigger'); x['fill_slot']=d.get('slot'); x['fill_idx']=d.get('idx')
        elif ev=='presend_live_realized' and k in win:
            x=win[k]; x['pnl']=(x['pnl'] or 0)+d['pnl']/1e9
        elif ev=='presend_live_disarm' and k in win:
            x=win[k]; x['att']=d.get('attempts',0); x['why']=d.get('why'); x['dis_slot']=d.get('slot')
            if d.get('quiet'): x['qd']=d['quiet']
        elif ev=='presend_live_skip':
            nsk[d.get('why')]+=1
            if d.get('why')=='quiet':
                t=d['trig']; SK.append(dict(reg=reg,run=r,seg=seg,mint=t['mint'],whale=t['wallet'],t=t['t'],slot=t['slot'],idx=t['idx'],age=t.get('age_slots'),q=d.get('quiet')))
        elif ev=='presend_live_stop': stopfees=d.get('fees')
    W+=list(win.values()); meta[r+reg]=dict(qcfg=qcfg,skips=dict(nsk),fees=stopfees,arms=len(win),segs=seg)
    print(reg,r,'arms',len(win),'fills',sum(1 for x in win.values() if x['pnl'] is not None),'pnl %+.3f'%sum(x['pnl'] or 0 for x in win.values()),'quiet' if qcfg else '-',dict(nsk))
json.dump(dict(windows=W,skips=SK,meta=meta),open(OUT,'w'))
