#!/usr/bin/env python3
import json, urllib.request, time
from collections import Counter, defaultdict

d=json.load(open("/root/geo_leaders.json"))
leaders={int(k):v for k,v in d["leaders"].items()}
buy_slots=set(d["buy_slots"])
baseline_slots=set(d["baseline_slots"])
id2ip=d["id2ip"]
slot_meta=json.load(open("/root/geo_slots.json"))  # mint-> create/buy/delta

# unique IPs for all leaders we need
need_ids=set(leaders.values())
ips=sorted({id2ip[i] for i in need_ids if i in id2ip})
print(f"unique IPs to geolocate: {len(ips)}")

def geo_batch(chunk):
    body=json.dumps([{"query":ip,"fields":"status,country,countryCode,regionName,city,lat,lon,isp,query"} for ip in chunk]).encode()
    req=urllib.request.Request("http://ip-api.com/batch",data=body,headers={"Content-Type":"application/json"})
    for a in range(6):
        try:
            with urllib.request.urlopen(req,timeout=40) as r:
                return json.loads(r.read())
        except Exception as e:
            time.sleep(3*(a+1))
    return []

geo={}
for i in range(0,len(ips),100):
    chunk=ips[i:i+100]
    res=geo_batch(chunk)
    for item in res:
        geo[item.get("query")]=item
    time.sleep(4)  # batch rate limit 15/min
print(f"geolocated {len(geo)} IPs")
json.dump(geo, open("/root/geo_ip.json","w"))

# region bucket from countryCode
EU={"DE","NL","FR","GB","FI","LT","LV","EE","PL","IE","AT","CH","SE","NO","DK","BE","ES","IT","CZ","RO","BG","PT","LU","UA","RU","MD","HU","SK","SI","HR","RS","GR","IS","NO"}
NA={"US","CA","MX"}
ASIA={"JP","SG","KR","HK","CN","IN","TW","ID","TH","VN","MY","AE","IL","TR","KZ","PH","GE"}
def bucket(cc):
    if cc in EU: return "EU"
    if cc in NA: return "NorthAmerica"
    if cc in ASIA: return "Asia"
    return "Other"

def leader_geo(slot):
    lid=leaders.get(slot)
    if not lid: return None
    ip=id2ip.get(lid)
    if not ip: return None
    g=geo.get(ip)
    if not g or g.get("status")!="success": return None
    return {"id":lid,"ip":ip,"cc":g.get("countryCode"),"country":g.get("country"),
            "city":g.get("city"),"region":g.get("regionName"),"isp":g.get("isp"),
            "lat":g.get("lat"),"lon":g.get("lon"),"bucket":bucket(g.get("countryCode"))}

# Classify his landings via delta
same_slots=[]   # delta<=0
slow_slots=[]   # delta>=1
for v in slot_meta.values():
    if v["delta"]<=0: same_slots.append(v["buy_slot"])
    else: slow_slots.append(v["buy_slot"])

def dist(slot_list,label):
    b=Counter(); cities=Counter(); unresolved=0
    for s in slot_list:
        lg=leader_geo(s)
        if not lg: unresolved+=1; continue
        b[lg["bucket"]]+=1
        cities[f'{lg["country"]}/{lg["city"]}']+=1
    tot=sum(b.values())
    print(f"\n=== {label} (n={len(slot_list)}, resolved={tot}, unresolved={unresolved}) ===")
    for k in ["EU","NorthAmerica","Asia","Other"]:
        print(f"  {k:14s}: {b[k]:4d}  {100*b[k]/tot:5.1f}%" if tot else f"  {k}: 0")
    print("  top cities:")
    for c,n in cities.most_common(10):
        print(f"    {c}: {n}")
    return b

bb_same=dist(same_slots,"SAME-SLOT (delta<=0) landings")
bb_slow=dist(slow_slots,"SLOW (delta>=1) landings")
bb_base=dist(sorted(baseline_slots),"BASELINE (random leader slots)")

# Distance from Frankfurt (50.11,8.68)
import math
FRA=(50.11,8.68)
def hav(a,b):
    R=6371; p=math.pi/180
    dlat=(b[0]-a[0])*p; dlon=(b[1]-a[1])*p
    x=math.sin(dlat/2)**2+math.cos(a[0]*p)*math.cos(b[0]*p)*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(x))

def dist_stats(slot_list,label):
    ds=[]
    for s in slot_list:
        lg=leader_geo(s)
        if lg and lg.get("lat") is not None:
            ds.append(hav(FRA,(lg["lat"],lg["lon"])))
    ds.sort()
    if not ds: print(f"{label}: no dist"); return
    import statistics
    near=sum(1 for x in ds if x<600)  # within ~600km ~= EU core near Frankfurt
    print(f"{label}: n={len(ds)} median_km={statistics.median(ds):.0f} "
          f"mean={statistics.mean(ds):.0f} <600km={100*near/len(ds):.0f}% "
          f"min={ds[0]:.0f} max={ds[-1]:.0f}")

print("\n--- distance-from-Frankfurt (km) ---")
dist_stats(same_slots,"SAME-SLOT")
dist_stats(slow_slots,"SLOW    ")
dist_stats(sorted(baseline_slots),"BASELINE")
