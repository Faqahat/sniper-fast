"""Task 1: pre-send attempts per region x path x leader client. MEASURED (our feed clock).
Sources: AMS r38..r55 (local copies), FRA r21..r28. Writes /home/it/sniper-data/postsend/t1_*.json"""
import json, glob, collections, statistics as st, sys
B='/home/it/sniper-data/runs/'
FILES=[('AMS',f) for f in sorted(glob.glob(B+'ams/runs/dip_ams_r*.jsonl'))+sorted(glob.glob(B+'ams_r*/dip_ams_r*.jsonl')) if not f.endswith('obs.jsonl')]
FILES+=[('FRA',f) for f in sorted(glob.glob(B+'fra/runs/dip_r*.jsonl'))]
def q(v,p):
    v=sorted(v); return v[min(len(v)-1,int(p*len(v)))] if v else None
rows=[]
for reg,f in FILES:
    run=f.split('_')[-1].split('.')[0]
    if reg=='AMS' and int(run[1:])<38 and 'ams/runs' in f: pass
    for l in open(f):
        if '"presend_attempt_land"' not in l: continue
        e=json.loads(l)
        rows.append(dict(reg=reg,run=run,path=e['path'],client=e['client'],res=e['res'],ack=e.get('ack_ms'),
            s2f=e.get('ms_send_to_first_rx'),sas=e.get('slots_after_send'),idx=e.get('idx'),kind=e.get('kind'),
            t_send=e['t_send'],send_slot=e['send_slot'],slot=e.get('slot'),deadline=e['deadline'],first_rx=e.get('first_rx')))
json.dump(rows,open('/home/it/sniper-data/postsend/t1_rows.json','w'))
def table(keyf,title):
    g=collections.defaultdict(list)
    for r in rows: g[keyf(r)].append(r)
    print('\n##',title)
    print('| key | n | ack p50/p90 | send→seen p50/p90 | same-slot | +1 | +2+ | idx med | ok | 6042 | deadline | ata | unseen |')
    print('|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    for k in sorted(g,key=lambda k:(-len(g[k]))):
        v=g[k]; n=len(v)
        if n<30: continue
        ack=[r['ack'] for r in v if r['ack'] is not None]; s2f=[r['s2f'] for r in v if r['s2f'] is not None]
        seen=[r for r in v if r['sas'] is not None]
        c=collections.Counter(r['res'] for r in v)
        sas=collections.Counter(min(r['sas'],2) for r in seen)
        ns=len(seen) or 1
        print(f"| {k} | {n} | {q(ack,.5):.2f}/{q(ack,.9):.2f} | {q(s2f,.5):.1f}/{q(s2f,.9):.1f} | {100*sas[0]/ns:.0f}% | {100*sas[1]/ns:.0f}% | {100*sas[2]/ns:.0f}% | {q([r['idx'] for r in seen if r['idx'] is not None],.5)} | "
              + ' | '.join(f"{100*c[x]/n:.1f}%" for x in ['ok','6042','deadline','ata_exists','unseen'])+' |')
if __name__=='__main__':
    print('rows',len(rows))
    table(lambda r:(r['reg'],r['path']),'region x path')
    table(lambda r:(r['reg'],r['path'],r['client']),'region x path x client')
    table(lambda r:(r['reg'],r['run'][:4],r['path']),'by run')
