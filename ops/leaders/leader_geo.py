# READ-ONLY, zero cost: geolocate every scheduled leader (ip-api.com batch, public validator IPs) on top of the
# close-leader measurement (/root/fix2/leader_rtt_new.json from close5_new.py, RTT from THIS server).
# Output /root/fix2/leader_geo.json: per leader rtt, client, slots this/next epoch, ip, city, country, ISP/ASN.
# Re-run on any new server (after close5_new.py) to rebuild the region map for that location.
import json, urllib.request, time
D = json.load(open("/root/fix2/leader_rtt_new.json"))
L = D["leaders"]
ip_of = {pk: (r["ips"][0] if r["ips"] else None) for pk, r in L.items()}
ips = sorted({i for i in ip_of.values() if i})
geo = {}
for i in range(0, len(ips), 100):
    req = urllib.request.Request("http://ip-api.com/batch?fields=query,status,country,countryCode,regionName,city,isp,org,as,hosting",
                                 data=json.dumps(ips[i:i + 100]).encode(), headers={"content-type": "application/json"})
    for g in json.load(urllib.request.urlopen(req, timeout=30)):
        geo[g["query"]] = g
    time.sleep(1.5)   # ip-api free tier: 15 batch requests / min
rows = []
for pk, r in L.items():
    g = geo.get(ip_of[pk]) or {}
    rows.append(dict(pk=pk, rtt=r["rtt"], client=r["client"], slots_cur=r["slots_cur"], slots_next=r["slots_next"], ip=ip_of[pk],
                     country=g.get("country"), cc=g.get("countryCode"), city=g.get("city"), region=g.get("regionName"),
                     isp=g.get("isp"), org=g.get("org"), asn=g.get("as"), hosting=g.get("hosting")))
json.dump(dict(epoch=D["epoch"], t=D["t"], rows=rows), open("/root/fix2/leader_geo.json", "w"))
print(len(rows), "leaders,", sum(1 for x in rows if x["country"]), "geolocated")
