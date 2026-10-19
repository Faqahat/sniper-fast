#!/usr/bin/env python3
# READ-ONLY. Does the create-slot LEADER's distance from our Frankfurt box decide landing position?
# Leader of S (getSlotLeaders cache) -> gossip IP (clusternodes) -> ICMP RTT from this server (cached geo_rtt.json).
# Outputs: (1) OUR 42 live fires: in-S rate and position by leader RTT bucket; (2) every OUTSIDE OK buy in S
# (landing-study rows): share at d<=25 by leader RTT bucket, overall and by sender; (3) stake share of leaders by bucket.
import sys, json, os, subprocess, collections, statistics as st
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/race"); sys.path.insert(0, "/root/nob")
src = open("/root/race/landing_study.py").read()
cut = src.index("rows = []")
exec(compile(src[:cut], "landing_study_head", "exec"))   # q, leaders_for, client_of, outsider_txs, sender, nodes, ME, pros
rows = []
for fn in ("blk_rand.jsonl", "blk_rand2.jsonl", "blk_his.jsonl"):
    for l in open("/root/nob/" + fn):
        try: b = json.loads(l)
        except Exception: continue
        if "later" in b: rows += [dict(t, slot=b["slot"]) for t in outsider_txs(b, b.get("client", "?"), "hist")]
tonight = []
for fn in ("/root/race/fwd_onchain.jsonl", "/root/race/night_onchain.jsonl", "/root/race/fresh_onchain.jsonl"):
    if not os.path.exists(fn): continue
    for l in open(fn):
        try: r = json.loads(l)
        except Exception: continue
        b = r.get("b") or {}
        if "later" in b: tonight.append(b)
live = []
for l in open("/root/race/live_fires.jsonl"):
    r = json.loads(l); live.append(r)
allslots = [t["slot"] for t in rows] + [b["slot"] for b in tonight] + [r["slot"] for r in live]
L = leaders_for(allslots)
for b in tonight:
    rows += [dict(t, slot=b["slot"]) for t in outsider_txs(b, client_of(L.get(b["slot"])), "fwd")]

ip_of = {}
for pk, n in nodes.items():
    g = n.get("gossip") or n.get("tpuQuic") or n.get("tpu") or ""
    if g: ip_of[pk] = g.rsplit(":", 1)[0]
cf = "/root/lat/geo_rtt.json"
rtt = json.load(open(cf)) if os.path.exists(cf) else {}
need = sorted({ip_of.get(L.get(s)) for s in allslots if ip_of.get(L.get(s))} - set(rtt))
def png(ip):
    try:
        o = subprocess.run(["ping", "-n", "-c", "3", "-i", "0.2", "-W", "1", ip], capture_output=True, text=True, timeout=5).stdout
        for ln in o.splitlines():
            if "min/avg" in ln: return ip, float(ln.split("=")[1].split("/")[0])
    except Exception: pass
    return ip, None
for ip, v in ThreadPoolExecutor(64).map(png, need): rtt[ip] = v
json.dump(rtt, open(cf, "w"))
def lrtt(slot):
    ip = ip_of.get(L.get(slot)); return rtt.get(ip) if ip else None
def bucket(r):
    if r is None: return "noping"
    return "<3ms" if r < 3 else "3-12ms" if r < 12 else "12-40ms" if r < 40 else "40-100ms" if r < 100 else ">100ms"
B = ["<3ms", "3-12ms", "12-40ms", "40-100ms", ">100ms", "noping"]

print("=== (1) OUR live fires by create-slot leader RTT from 77.223.215.155 ===")
by = collections.defaultdict(list)
for r in live:
    b = r["b"]; s = r.get("s") or {}
    mine = [x for x in b.get("later", []) if x["payer"] == ME]
    pos = mine[0]["d"] if mine else None
    by[bucket(lrtt(r["slot"]))].append((pos, client_of(L.get(r["slot"]))))
for k in B:
    v = by.get(k)
    if not v: continue
    ins = [p for p, _ in v if p is not None]
    print(f"  {k:9} n={len(v):2} inS={len(ins):2} ({len(ins)/len(v):.0%}) med_d={st.median(ins) if ins else '-'} clients={dict(collections.Counter(c for _, c in v))}")

print("\n=== (2) OUTSIDE OK buys in S: share at d<=25 by leader RTT (all senders) ===")
buys = [t for t in rows if t["ok"] and t["buy"] and t["outside"] and not t["ours"]]
g = collections.defaultdict(list)
for t in buys: g[bucket(lrtt(t["slot"]))].append(t)
for k in B:
    v = g.get(k)
    if not v: continue
    ds = [t["d"] for t in v]
    print(f"  {k:9} buys={len(v):5} launches={len({t['mint'] for t in v}):4} d<=25 {sum(d <= 25 for d in ds)/len(ds):.0%}  d6-25 {sum(6 <= d <= 25 for d in ds)/len(ds):.0%}  med_d={st.median(ds)}  med_ms={st.median(t['ms'] for t in v):.0f}")
print("\n  by sender (share d<=25 | n) per RTT bucket:")
senders = [s for s, _ in collections.Counter(sender(t) for t in buys).most_common(8)]
print("  " + "sender".ljust(16) + "".join(k.ljust(16) for k in B[:5]))
for sn in senders:
    line = "  " + sn[:15].ljust(16)
    for k in B[:5]:
        v = [t for t in g.get(k, []) if sender(t) == sn]
        line += (f"{sum(t['d'] <= 25 for t in v)/len(v):.0%} n={len(v)}" if v else "-").ljust(16)
    print(line)

print("\n=== (3) leader slots by RTT bucket (share of all create slots in the sample) ===")
cs = collections.Counter(bucket(lrtt(s)) for s in set(allslots))
tot = sum(cs.values())
for k in B: print(f"  {k:9} {cs.get(k,0)/tot:.0%}")
print("\n  by client x bucket:")
cc = collections.Counter((client_of(L.get(s)), bucket(lrtt(s))) for s in set(allslots))
for cl in ("AgaveBam", "Harmonic", "JitoLabs", "Firedancer", "Agave", "?"):
    print(f"  {cl:10} " + " ".join(f"{k}:{cc.get((cl, k), 0)}" for k in B))

print("\n=== (4) share of OUTSIDE OK buys in S landing d<=25, by sender x leader class (n) ===")
def cls(c):
    c = c or ""
    if c in ("AgaveBam", "FireBAM"): return "bam"
    if c.startswith("Harmonic"): return "harmonic"
    if c == "JitoLabs": return "jito"
    if c in ("Firedancer", "Frankendancer"): return "fd"
    return "agave/other"
def clof(t):
    return cls(client_of(L.get(t["slot"])) if L.get(t["slot"]) else t.get("client"))
CL = ["bam", "harmonic", "jito", "fd", "agave/other"]
cc = collections.Counter(clof(t) for t in buys)
print("  buys per class: " + ", ".join(f"{k} {cc.get(k,0)}" for k in CL))
print("  " + "sender".ljust(16) + "".join(k.ljust(17) for k in CL))
for sn in senders:
    line = "  " + sn[:15].ljust(16)
    for k in CL:
        v = [t for t in buys if sender(t) == sn and clof(t) == k]
        line += (f"{sum(t['d'] <= 25 for t in v)/len(v):.0%} n={len(v)}" if len(v) >= 5 else "-").ljust(17)
    print(line)
