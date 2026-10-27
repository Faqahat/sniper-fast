#!/usr/bin/env python3
# LANDING2 step N1 (read-only, 3 RPC calls): build the network-probe target list.
#  - getEpochInfo + getClusterNodes from the Constant-K RPC (URL read from ~/.config/sniper/ck_rpc_url, never printed)
#  - leaders: (a) every leader our nonce-era fires targeted (FRA r11-16, AMS r11-17), (b) the leaders of the next ~3000 slots
#    (epoch schedule file already on disk), each with its gossip IP (the validator itself) and its TPU-QUIC IP (the front:
#    own TPU, Jito relayer, BAM node or Harmonic relay)
#  - send endpoints / feeds / Jito + Harmonic block engines by hostname (resolved on each server at probe time)
# Output: /home/moiz/sniper-data/landing2/targets.json (no secrets)
import json, os, time, urllib.request, collections, glob

OUT = "/home/moiz/sniper-data/landing2"
RUNS = "/home/moiz/sniper-data/runs"
URL = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()


def rpc(m, p=None):
    req = urllib.request.Request(URL, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p or []}).encode(),
                                 headers={"content-type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=60))
    time.sleep(0.3)                      # <= 5 req/s
    return r.get("result")


ei = rpc("getEpochInfo")
nodes = {n["pubkey"]: n for n in rpc("getClusterNodes")}
print("epoch", ei["epoch"], "slot", ei["absoluteSlot"], "cluster nodes", len(nodes))
sch = json.load(open("/home/moiz/sniper-data/competitors2/schedule_1067.json"))
assert sch["epoch"] == ei["epoch"], "schedule file is for another epoch"
ids, sl = sch["ids"], sch["slot_leader"]
cur = ei["absoluteSlot"]
upcoming = collections.Counter()
for s in range(cur + 50, min(cur + 3050, sch["start"] + len(sl))):
    x = sl[s - sch["start"]]
    if x is not None: upcoming[ids[x]] += 1

# leaders our fires targeted (nonce era)
fired = collections.Counter(); fired_srv = collections.defaultdict(set)
for srv, pat in (("FRA", "fra/runs/dip_r1[1-6].jsonl"), ("AMS", "ams/runs/dip_ams_r1[1-7].jsonl")):
    for fn in glob.glob(f"{RUNS}/{pat}"):
        for l in open(fn):
            if "fire" not in l: continue
            r = json.loads(l)
            if r.get("ev") == "fire" and r.get("leader"):
                fired[r["leader"]] += 1; fired_srv[r["leader"]].add(srv)


def ipport(v):
    if not v: return None, None
    h, p = v.rsplit(":", 1)
    return h.strip("[]"), int(p)


leaders = {}
for pk in set(fired) | set(upcoming):
    n = nodes.get(pk, {})
    g = ipport(n.get("gossip")); tq = ipport(n.get("tpuQuic")); tu = ipport(n.get("tpu"))
    leaders[pk] = dict(client=n.get("clientId") or n.get("version"), version=n.get("version"), gossip=g, tpu_quic=tq, tpu_udp=tu,
                       fired=fired.get(pk, 0), fired_srv=sorted(fired_srv.get(pk, [])), upcoming_slots=upcoming.get(pk, 0),
                       in_gossip=pk in nodes)
hosts = {
    "FRA": ["staked-rpc-frankfurt.constant-k.com", "rpc-frankfurt.constant-k.com", "frankfurt.mainnet.block-engine.jito.wtf",
            "amsterdam.mainnet.block-engine.jito.wtf", "fra3.landx.dev", "ams1.landx.dev", "fra-sender.helius-rpc.com", "ams-sender.helius-rpc.com",
            "fra2.nozomi.temporal.xyz", "ams1.nozomi.temporal.xyz", "fr.gateway.astralane.io", "ams.gateway.astralane.io", "fra.be.harmonic.gg",
            "ams.be.harmonic.gg", "fra.tpu.harmonic.gg", "ams.tpu.harmonic.gg", "sender.haandigital.eu", "fra.bolt.raiden.wtf", "ams.bolt.raiden.wtf",
            "kaldera-frankfurt.constant-k.com", "turbo-kaldera-frankfurt.constant-k.com", "kaldera-amsterdam.constant-k.com",
            "turbo-kaldera-amsterdam.constant-k.com", "shreds-fra6-1.erpc.global", "staked-rpc-amsterdam.constant-k.com", "rpc-amsterdam.constant-k.com"],
}
hosts["AMS"] = hosts["FRA"]
# TCP ports per hostname (the port the engine uses; landx is UDP 10000 -> TCP 443 tried; tpu.harmonic.gg is QUIC -> ICMP only)
ports = {h: [443] for h in hosts["FRA"]}
for h in ("fra-sender.helius-rpc.com", "ams-sender.helius-rpc.com"): ports[h] = [80]
for h in ("kaldera-frankfurt.constant-k.com", "kaldera-amsterdam.constant-k.com"): ports[h] = [8443]
for h in ("fra.tpu.harmonic.gg", "ams.tpu.harmonic.gg", "fra3.landx.dev", "ams1.landx.dev"): ports[h] = [443]
json.dump(dict(t=time.time(), epoch=ei["epoch"], slot=cur, leaders=leaders, hosts=hosts, ports=ports), open(f"{OUT}/targets.json", "w"), indent=0)
ips = {l["gossip"][0] for l in leaders.values() if l["gossip"]} | {l["tpu_quic"][0] for l in leaders.values() if l["tpu_quic"]}
print(f"leaders: fired {len(fired)} (fires {sum(fired.values())}), upcoming {len(upcoming)} | union {len(leaders)} | not in gossip "
      f"{sum(1 for l in leaders.values() if not l['in_gossip'])} | unique IPs {len(ips)}")
print("clients:", collections.Counter((l["client"] or "?") for l in leaders.values()).most_common())
