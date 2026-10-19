import json, sys, threading, urllib.request
import concurrent.futures as cf
uris=json.load(open('/root/every_angle/uris.json'))   # mint -> uri
def fetch(uri):
    try:
        req=urllib.request.Request(uri, headers={'User-Agent':'Mozilla/5.0'})
        raw=urllib.request.urlopen(req, timeout=15).read()
        j=json.loads(raw)
        return j
    except Exception as e:
        return {"__err":str(e)[:60]}
def feats(j):
    if not isinstance(j,dict) or '__err' in j: return None
    low={k.lower():v for k,v in j.items()}
    def has(*keys):
        for k in keys:
            v=low.get(k)
            if v and isinstance(v,str) and len(v.strip())>3: return 1
        return 0
    tw=has('twitter','x'); tg=has('telegram'); web=has('website','web'); img=1 if low.get('image') else 0
    desc=1 if (low.get('description') and len(str(low.get('description')).strip())>5) else 0
    return dict(twitter=tw,telegram=tg,website=web,image=img,desc=desc,
                n_social=tw+tg+web)
out={}; lock=threading.Lock(); done=[0]
def work(item):
    m,u=item
    j=fetch(u); f=feats(j)
    with lock:
        done[0]+=1
        if done[0]%40==0: print(f"  {done[0]}/{len(uris)}",file=sys.stderr)
    return m,f
with cf.ThreadPoolExecutor(max_workers=16) as ex:
    for m,f in ex.map(work, list(uris.items())):
        out[m]=f
json.dump(out, open('/root/every_angle/his_social.json','w'))
got=sum(1 for v in out.values() if v)
print(f"fetched socials for {got}/{len(uris)}",file=sys.stderr)
