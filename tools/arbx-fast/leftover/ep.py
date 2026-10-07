import json,sys,glob,subprocess,collections
seg=sys.argv[1]; files=sorted(glob.glob(f"/root/arbx/runs/ft012c/{seg}/decisions.*.jsonl.zst"))
open_ep={}; eps=[]; t0=t1=None
def close(k,t,slot,why):
    e=open_ep.pop(k); e['end_t']=t; e['end_slot']=slot; e['why']=why; eps.append(e)
for f in files:
    p=subprocess.Popen(["zstd","-dc",f],stdout=subprocess.PIPE)
    for l in p.stdout:
        if b'"routes"' not in l: continue
        d=json.loads(l); tr=d['trigger']; t=d['stages'].get('t_commit') or d['t_ns']; s=tr['slot']
        if t0 is None: t0=t
        t1=t
        for r in d['routes']:
            if r['net'] is None: continue
            k=(r['buy'],r['sell']); n=r['net']
            if n>0:
                if k not in open_ep:
                    open_ep[k]=dict(k=k,mint=r['mint'],v=(r['buy_venue'],r['sell_venue']),start_t=t,start_slot=s,obs=[(t,n,r['size'],r['gross'])],trig=tr['txn'][:8])
                else: open_ep[k]['obs'].append((t,n,r['size'],r['gross']))
            elif k in open_ep: close(k,t,s,'closed')
for k in list(open_ep): close(k,t1,None,'eof')
hours=(t1-t0)/3.6e12
out=dict(hours=hours,eps=[dict(mint=e['mint'],v=e['v'],k=e['k'],st=e['start_t'],ss=e['start_slot'],dur=(e['end_t']-e['start_t'])/1e6,es=e['end_slot'],why=e['why'],obs=[(round((o[0]-e['start_t'])/1e6,1),o[1],o[2],o[3]) for o in e['obs']][:50]) for e in eps])
json.dump(out,open(f"/tmp/ep-{seg}.json","w"))
print(seg,hours,len(eps))
