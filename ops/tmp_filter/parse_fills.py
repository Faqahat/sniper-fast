import re,json,glob
logs=["floor_test.log","floor112_test.log","floor_ride.log","floor_ride20.log","concurrent_live.log"]
fills=[]  # mint,dev_buy,delta,log
for lg in logs:
    path="/root/sniper-fast/"+lg
    lines=open(path,errors="replace").read().splitlines()
    cur_mint=None; cur_dev=None; cur_delta=None
    for ln in lines:
        m=re.search(r"mint=([1-9A-HJ-NP-Za-km-z]{32,44})",ln)
        if m and ("FIRE" in ln or "ROUND-TRIP" in ln): cur_mint=m.group(1)
        d=re.search(r"dev_buy=(\d+)",ln)
        if d and "FIRE" in ln: cur_dev=int(d.group(1))/1e9
        b=re.search(r"land_slot=(\d+) delta=(\d+) ok=true",ln)
        if "BUY" in ln and b: cur_delta=int(b.group(2))
        if "tokens received:" in ln and "(ATA" in ln:
            # a real fill
            fills.append({"mint":cur_mint,"dev_buy":cur_dev,"delta":cur_delta,"log":lg})
print("total fill events:",len(fills))
# dedupe by mint
seen={}
for f in fills:
    if f["mint"] and f["mint"] not in seen: seen[f["mint"]]=f
uniq=list(seen.values())
print("unique filled mints:",len(uniq))
for f in uniq:
    print("  %-45s dev_buy=%s delta=%s [%s]"%(f["mint"],f["dev_buy"],f["delta"],f["log"]))
json.dump(uniq,open("/root/tmp_filter/our_fills.json","w"))
# dev_buy dist
devs=[f["dev_buy"] for f in uniq if f["dev_buy"] is not None]
import statistics as st
print()
print("our fills dev_buy: n=%d zero=%d med=%.3f"%(len(devs),sum(1 for d in devs if d==0),st.median(devs) if devs else 0))
