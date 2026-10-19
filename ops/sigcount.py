import os, json, time, urllib.request, urllib.error, sys
RPC="https://rpc-frankfurt.constant-k.com/?api-key="+os.environ["CONSTANTK_TOKEN"]
TARGET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
def rpc(m,p,tries=8):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    last=None
    for t in range(tries):
        try:
            req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=45) as r: j=json.loads(r.read())
            if "error" in j: last=j["error"]; time.sleep(0.4*(t+1)); continue
            return j.get("result")
        except urllib.error.HTTPError as e:
            last=e; time.sleep(1.0+0.8*t if e.code==429 else 0.5*(t+1))
        except Exception as e:
            last=e; time.sleep(0.5*(t+1))
    raise RuntimeError(f"fail {m}: {last}")
total=0; landed=0; before=None; pages=0
oldest_time=None; newest_time=None
while True:
    p=[TARGET,{"limit":1000}]
    if before: p[1]["before"]=before
    r=rpc("getSignaturesForAddress",p)
    if not r: break
    pages+=1; total+=len(r); landed+=sum(1 for s in r if s.get("err") is None)
    if newest_time is None and r[0].get("blockTime"): newest_time=r[0]["blockTime"]
    if r[-1].get("blockTime"): oldest_time=r[-1]["blockTime"]
    before=r[-1]["signature"]
    if len(r)<1000:
        print(f"short page {len(r)} at page {pages}", file=sys.stderr)
        # keep going anyway one more time to confirm end
        p2=[TARGET,{"limit":1000,"before":before}]
        r2=rpc("getSignaturesForAddress",p2)
        if not r2: break
        else:
            print(f"  ...but more exist ({len(r2)}), continuing", file=sys.stderr)
            pages+=1; total+=len(r2); landed+=sum(1 for s in r2 if s.get("err") is None)
            before=r2[-1]["signature"]
            if len(r2)<1000 and len(r2)==0: break
            continue
    if pages>60: print("cap 60 pages",file=sys.stderr); break
print(f"pages={pages} total_sigs={total} landed={landed} failed={total-landed}")
import datetime as dt
if oldest_time and newest_time:
    print("newest:",dt.datetime.utcfromtimestamp(newest_time),"oldest:",dt.datetime.utcfromtimestamp(oldest_time))
