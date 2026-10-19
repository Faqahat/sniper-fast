#!/usr/bin/env python3
import json, urllib.request, time, subprocess
from collections import Counter

d=json.load(open("/root/geo_leaders.json"))
leaders={int(k):v for k,v in d["leaders"].items()}
id2ip=d["id2ip"]
geo=json.load(open("/root/geo_ip.json"))
slot_meta=json.load(open("/root/geo_slots.json"))

EU={"DE","NL","FR","GB","FI","LT","LV","EE","PL","IE","AT","CH","SE","NO","DK","BE","ES","IT","CZ","RO","BG","PT","LU","UA","RU","MD","HU","SK","SI","HR","RS","GR","IS"}
NA={"US","CA","MX"}
def bk(cc):
    if cc in EU: return "EU"
    if cc in NA: return "NA"
    return "Asia/Other"

# List all SAME-SLOT (delta<=0) far (non-EU) landings
print("=== SAME-SLOT landings on NON-EU leaders (his fast wins on far leaders) ===")
far=[]
for mint,v in slot_meta.items():
    if v["delta"]>0: continue
    lid=leaders.get(v["buy_slot"])
    if not lid: continue
    ip=id2ip.get(lid); g=geo.get(ip,{})
    cc=g.get("countryCode")
    if bk(cc)!="EU":
        far.append((mint,v["create_slot"],v["buy_slot"],v["delta"],lid,ip,g.get("country"),g.get("city"),g.get("isp")))
for x in far:
    print(f"  {x[0][:10]} create={x[1]} buy={x[2]} d={x[3]} {x[6]}/{x[7]} ip={x[5]} {x[8]}")
print(f"total non-EU same-slot: {len(far)}")

# Verify: re-fetch create tx and buy slot leader independently for 4 far examples?
# Cross-check geo with ipinfo.io for a spread of IPs
print("\n=== geo cross-check (ip-api vs ipinfo.io) ===")
check_ips=[]
seen=set()
for x in far[:6]:
    if x[5] not in seen: check_ips.append(x[5]); seen.add(x[5])
# add a couple EU ones
for mint,v in slot_meta.items():
    if v["delta"]<=0:
        lid=leaders.get(v["buy_slot"]); ip=id2ip.get(lid); g=geo.get(ip,{})
        if g.get("countryCode")=="DE" and ip not in seen:
            check_ips.append(ip); seen.add(ip)
            if len([i for i in check_ips if geo.get(i,{}).get("countryCode")=="DE"])>=2: break
for ip in check_ips[:10]:
    try:
        with urllib.request.urlopen(f"https://ipinfo.io/{ip}/json",timeout=15) as r:
            j=json.loads(r.read())
        ipinfo=f'{j.get("country")}/{j.get("city")} ({j.get("org","")[:30]})'
    except Exception as e:
        ipinfo=f"ERR {e}"
    g=geo.get(ip,{})
    print(f"  {ip}: ip-api={g.get('countryCode')}/{g.get('city')} | ipinfo={ipinfo}")
    time.sleep(0.5)

# Ping RTT from Frankfurt to a spread of leader IPs
print("\n=== ping RTT from Frankfurt server (ms) ===")
def ping(ip):
    try:
        out=subprocess.run(["ping","-c","3","-W","2",ip],capture_output=True,text=True,timeout=15).stdout
        for line in out.splitlines():
            if "min/avg" in line or "rtt" in line:
                return line.split("=")[1].strip().split("/")[1]+"ms avg"
        if "0 received" in out or "100% packet loss" in out: return "no-reply"
    except Exception as e:
        return f"err"
    return "?"
pset=[]
seen=set()
for x in far:
    if x[5] not in seen: pset.append((x[6],x[7],x[5])); seen.add(x[5])
    if len(pset)>=8: break
# a few EU for contrast
for mint,v in slot_meta.items():
    if v["delta"]<=0:
        lid=leaders.get(v["buy_slot"]); ip=id2ip.get(lid); g=geo.get(ip,{})
        if g.get("countryCode") in ("DE","NL") and ip not in seen:
            pset.append((g.get("country"),g.get("city"),ip)); seen.add(ip)
    if len(pset)>=12: break
for country,city,ip in pset:
    print(f"  {country}/{city} {ip}: {ping(ip)}")
