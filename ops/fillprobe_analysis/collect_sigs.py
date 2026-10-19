import json, os, sys, urllib.request, time
URL=os.environ["CKURL"]
def rpc(method,params):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    for a in range(6):
        try:
            req=urllib.request.Request(URL,data=body,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=30) as r: d=json.load(r)
            if "error" in d: sys.stderr.write(f"err {d['error']}\n"); time.sleep(0.6); continue
            return d["result"]
        except Exception as e: sys.stderr.write(f"a{a} {e}\n"); time.sleep(0.8)
    return None

curve=sys.argv[1]
buy_slot=int(sys.argv[2])
low=buy_slot-6   # collect window: create expected at/just below buy_slot
high=buy_slot+3
all_sigs=[]
before=None
pages=0
while True:
    params=[curve,{"limit":1000}]
    if before: params[1]["before"]=before
    res=rpc("getSignaturesForAddress",params)
    pages+=1
    if not res: break
    all_sigs.extend(res)
    oldest=res[-1]["slot"]
    before=res[-1]["signature"]
    if oldest < low-1:  # walked past window
        break
    if len(res)<1000:
        break
    if pages>40:
        sys.stderr.write("page cap hit\n"); break
# filter to window, dedup, sort ascending by slot then keep rpc order
win=[s for s in all_sigs if low<=s["slot"]<=high]
# sort oldest-first: getSignaturesForAddress is newest-first, so reverse to approx chrono; within slot we'll order by actual tx index later
win_sorted=sorted(win,key=lambda s:(s["slot"],))
print(json.dumps({"total_collected":len(all_sigs),"pages":pages,"window":[low,high],"win":win}))
