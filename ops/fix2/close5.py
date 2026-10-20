#!/usr/bin/env python3
# ZERO COST, read-only: leaders of the CURRENT and NEXT epoch -> their gossip / TPU / TPU-QUIC IPs (getClusterNodes) ->
# ICMP RTT from this server (3 pings each, min over the node's IPs). Writes /root/fix2/close_leaders_5ms.txt (RTT < 5 ms)
# and /root/fix2/leader_rtt.json (every leader: rtt, ips, client, slots this/next epoch). Same idea as /root/close_leaders.py
# (which pinged every cluster node's gossip IP at 20 ms), restricted to scheduled leaders and their TPU IPs.
import json, os, subprocess, urllib.request, collections, sys, time
from concurrent.futures import ThreadPoolExecutor
TOK = os.environ["CONSTANTK_TOKEN"]
RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
THRESH = float(os.environ.get("CLOSE_MS", "5"))
OUT = "/root/fix2/close_leaders_5ms.txt"


def rpc(m, p):
    req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                 headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60)).get("result")


ei = rpc("getEpochInfo", [])
start = ei["absoluteSlot"] - ei["slotIndex"]
L = ei["slotsInEpoch"]
sched = {}
for k, arg in ((0, None), (1, start + L)):
    ls = rpc("getLeaderSchedule", [arg]) or {}
    for pk, slots in ls.items():
        sched.setdefault(pk, [0, 0])[k] += len(slots)
print(f"epoch {ei['epoch']} start {start} len {L}: leaders this epoch {sum(1 for v in sched.values() if v[0])}, next {sum(1 for v in sched.values() if v[1])}", flush=True)
nodes = {n["pubkey"]: n for n in (rpc("getClusterNodes", []) or [])}


def ips_of(n):
    out = []
    for k in ("tpuQuic", "tpu", "gossip", "tpuForwardsQuic"):
        v = n.get(k)
        if v:
            ip = v.rsplit(":", 1)[0].strip("[]")
            if ip and ip not in out:
                out.append(ip)
    return out


allips = sorted({ip for pk in sched for ip in ips_of(nodes.get(pk, {}))})
print(f"unique IPs to ping: {len(allips)}", flush=True)


def png(ip):
    try:
        o = subprocess.run(["ping", "-n", "-c", "3", "-i", "0.2", "-W", "1", ip], capture_output=True, text=True, timeout=6).stdout
        for l in o.splitlines():
            if "min/avg" in l:
                return ip, float(l.split("=")[1].strip().split("/")[0])
    except Exception:
        pass
    return ip, None


t0 = time.time()
rtt = dict(ThreadPoolExecutor(48).map(png, allips))
print(f"pinged in {time.time()-t0:.0f}s, answered {sum(1 for v in rtt.values() if v is not None)}/{len(rtt)}", flush=True)
rows = {}
for pk, (a, b) in sched.items():
    n = nodes.get(pk, {})
    ips = ips_of(n)
    rs = [rtt.get(ip) for ip in ips if rtt.get(ip) is not None]
    rows[pk] = {"rtt": min(rs) if rs else None, "ips": ips, "client": n.get("clientId", ""), "slots_cur": a, "slots_next": b,
                "tpu": n.get("tpuQuic") or n.get("tpu")}
close = sorted(pk for pk, r in rows.items() if r["rtt"] is not None and r["rtt"] < THRESH)
with open(OUT, "w") as f:
    f.write("\n".join(close) + "\n")
json.dump({"epoch": ei["epoch"], "start": start, "len": L, "thresh_ms": THRESH, "t": time.time(), "leaders": rows}, open("/root/fix2/leader_rtt.json", "w"))
tot = [sum(r["slots_cur"] for r in rows.values()), sum(r["slots_next"] for r in rows.values())]
cov = [sum(rows[pk]["slots_cur"] for pk in close), sum(rows[pk]["slots_next"] for pk in close)]
nop = [sum(r["slots_cur"] for r in rows.values() if r["rtt"] is None), sum(r["slots_next"] for r in rows.values() if r["rtt"] is None)]
print(f"CLOSE (<{THRESH} ms): {len(close)} leaders -> {OUT}")
print(f"slot share covered: this epoch {cov[0]/tot[0]:.1%}, next epoch {cov[1]/max(tot[1],1):.1%}; no ping answer: {nop[0]/tot[0]:.1%} / {nop[1]/max(tot[1],1):.1%}")


def cls(c):
    return {"AgaveBam": "bam", "FireBAM": "bam", "JitoLabs": "jito", "Firedancer": "fd", "Frankendancer": "fd", "Agave": "agave"}.get(c, "harmonic" if c.startswith("Harmonic") else ("unknown" if not c else "other"))


by = collections.defaultdict(lambda: [0, 0])
for pk, r in rows.items():
    by[cls(r["client"])][1] += r["slots_cur"]
    if pk in close:
        by[cls(r["client"])][0] += r["slots_cur"]
print("this epoch, close slots / all slots by client: " + ", ".join(f"{k} {v[0]}/{v[1]} ({v[0]/max(v[1],1):.0%})" for k, v in sorted(by.items(), key=lambda x: -x[1][1])))
bk = collections.Counter()
for r in rows.values():
    x = r["rtt"]
    b = "noping" if x is None else ("<1" if x < 1 else "<3" if x < 3 else "<5" if x < 5 else "<12" if x < 12 else "<40" if x < 40 else ">=40")
    bk[b] += r["slots_cur"]
print("this-epoch slot share by leader RTT (ms): " + ", ".join(f"{k} {v/tot[0]:.1%}" for k, v in sorted(bk.items())))
old = {l.strip() for l in open("/root/sniper-final/close_leaders.txt") if l.strip()}
print(f"old close_leaders.txt: {len(old)} keys; leaders in it {sum(1 for pk in rows if pk in old)}; old-close slot share {sum(r['slots_cur'] for pk, r in rows.items() if pk in old)/tot[0]:.1%}; overlap with new {len(old & set(close))}")
