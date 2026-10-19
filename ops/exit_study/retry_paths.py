import rpc,json,concurrent.futures as cf,threading,time
def gettx2(sig): return rpc.call("getTransaction",[sig,{"maxSupportedTransactionVersion":1,"encoding":"jsonParsed","commitment":"confirmed"}])
rpc.gettx=gettx2
import importlib.util
spec=importlib.util.spec_from_file_location("ppmod","pricepath.py")
# avoid running main: read funcs manually
src=open("pricepath.py").read().split("lock=threading.Lock()")[0]
ns={}; exec(src,ns)
curve_px=ns["curve_px"]; all_sigs_window=ns["all_sigs_window"]
res={r["mint"]:r for r in json.load(open("trades.json")) if not r.get("error")}
rows={r["mint"]:r for r in json.load(open("rows.json"))}
paths=json.load(open("paths.json"))
def work(mint):
    r=rows[mint]; curve=res[mint]["curve"]; bslot=r["bslot"]; hi=bslot+(r["last_dslot"] or 0)
    sigs=all_sigs_window(curve,bslot,hi)
    pts=[]
    for s in sigs:
        if s.get("err"): continue
        tx=gettx2(s["signature"])
        if not tx: continue
        px=curve_px(tx,mint,curve)
        if px: pts.append((tx["slot"],px))
    pts.sort(); return dict(mint=mint,npts=len(pts),pts=pts)
todo=[m for m,o in paths.items() if o.get("error")]
print("retry",len(todo))
with cf.ThreadPoolExecutor(max_workers=4) as ex:
    futs={ex.submit(work,m):m for m in todo}
    for f in cf.as_completed(futs):
        m=futs[f]
        try: paths[m]=f.result()
        except Exception as e: paths[m]={"mint":m,"error":str(e)}
json.dump(paths,open("paths.json","w"))
e=[o for o in paths.values() if o.get("error")]
print("errs now",len(e),"pts",sum(o.get("npts",0) for o in paths.values()))
