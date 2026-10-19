import json, sys, threading, urllib.request, random
import concurrent.futures as cf
sys.path.insert(0,'/root/profit_backtest')
import common as C
CREATE_V2="d6904cec5f8b31b4"; CREATE="181ec828051c0777"
creates=json.load(open('/root/profit_backtest/creates.json'))
traj={x['mint']:x for x in json.load(open('/root/profit_backtest/trajectories.json'))}
def peak(x):
    s=x.get('series') or []; e=x.get('entry_px')
    if not s or not e: return None
    px=[p[1] for p in s if isinstance(p,list) and len(p)>=2]
    return (max(px)/e) if px else None
# sample universe creates that have an outcome
pool=[c for c in creates if c.get('sig') and traj.get(c['mint']) and peak(traj[c['mint']]) is not None]
random.seed(1); random.shuffle(pool)
pool=pool[:260]
def uri_of_tx(tx):
    try:
        msg=tx['transaction']['message']
        for ix in msg['instructions']:
            if ix.get('programId')!=C.PUMP_B58: continue
            dd=C.b58dec(ix.get('data',''))
            if dd[:8].hex() not in (CREATE_V2,CREATE): continue
            p=8
            def rstr():
                nonlocal p
                ln=int.from_bytes(dd[p:p+4],'little'); p+=4
                s=dd[p:p+ln].decode('utf-8','replace'); p+=ln; return s
            rstr(); rstr(); return rstr()
    except Exception: return None
    return None
def fetch(uri):
    try:
        req=urllib.request.Request(uri, headers={'User-Agent':'Mozilla/5.0'})
        return json.loads(urllib.request.urlopen(req,timeout=12).read())
    except Exception: return None
def feats(j):
    if not isinstance(j,dict): return None
    low={k.lower():v for k,v in j.items()}
    def has(*ks):
        for k in ks:
            v=low.get(k)
            if v and isinstance(v,str) and len(v.strip())>3: return 1
        return 0
    tw=has('twitter','x'); tg=has('telegram'); web=has('website','web')
    img=1 if low.get('image') else 0
    desc=1 if (low.get('description') and len(str(low.get('description')).strip())>5) else 0
    return dict(twitter=tw,telegram=tg,website=web,image=img,desc=desc,n_social=tw+tg+web)
out={}; lock=threading.Lock(); done=[0]
def work(c):
    tx=C.gettx(c['sig']); f=None; u=None
    if tx: 
        u=uri_of_tx(tx)
        if u: f=feats(fetch(u))
    with lock:
        done[0]+=1
        if done[0]%40==0: print(f"  {done[0]}/{len(pool)}",file=sys.stderr)
    return c['mint'], dict(feat=f, peak=peak(traj[c['mint']]), slot=c['create_slot'], had_uri=bool(u))
with cf.ThreadPoolExecutor(max_workers=16) as ex:
    for m,r in ex.map(work, pool):
        out[m]=r
json.dump(out, open('/root/every_angle/uni_social.json','w'))
got=sum(1 for v in out.values() if v['feat'])
hadu=sum(1 for v in out.values() if v['had_uri'])
print(f"universe: {len(pool)} sampled, {hadu} had uri, {got} socials fetched",file=sys.stderr)
