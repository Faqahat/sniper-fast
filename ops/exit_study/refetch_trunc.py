import rpc,json,concurrent.futures as cf
def gettx2(sig): return rpc.call("getTransaction",[sig,{"maxSupportedTransactionVersion":1,"encoding":"jsonParsed","commitment":"confirmed"}])
src=open("pricepath.py").read().split("lock=threading.Lock()")[0]
ns={}; exec(src,ns)
curve_px=ns["curve_px"]
rows={r["mint"]:r for r in json.load(open("rows2.json"))}
res={r["mint"]:r for r in json.load(open("trades.json")) if not r.get("error")}
paths=json.load(open("paths.json"))
rm=rows
trunc=[m for m,o in paths.items() if o.get("pts") and (min(s for s,_ in o["pts"])-rm[m]["bslot"])>3]
print("refetch",len(trunc))
def allsigs_full(addr,lo,hi):
    out=[];before=None
    while True:
        page=rpc.getsigs(addr,before=before,limit=1000)
        if not page: break
        out+=[s for s in page if s["slot"]<=hi]
        if page[-1]["slot"]<lo: break
        before=page[-1]["signature"]
        if len(out)>8000: break
    return [s for s in out if lo<=s["slot"]<=hi]
def work(m):
    curve=res[m]["curve"]; b=rm[m]["bslot"]; hi=b+(rm[m]["last_dslot"] or 0)
    sigs=allsigs_full(curve,b,hi)
    pts=[]
    for s in sigs:
        if s.get("err"): continue
        tx=gettx2(s["signature"])
        if not tx: continue
        px=curve_px(tx,m,curve)
        if px: pts.append((tx["slot"],px))
    pts.sort(); return m,pts
with cf.ThreadPoolExecutor(max_workers=2) as ex:
    for m,pts in ex.map(work,trunc):
        paths[m]={"mint":m,"npts":len(pts),"pts":pts}
        print(m[:10],"npts",len(pts),"min dslot",(min(s for s,_ in pts)-rm[m]["bslot"]) if pts else None)
json.dump(paths,open("paths.json","w"))
print("saved")
