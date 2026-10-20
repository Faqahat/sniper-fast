#!/usr/bin/env python3
"""Leader book for the feed race: slot -> leader identity -> client class + gossip IP (+ RTT/city when known).
Reads CONSTANTK_TOKEN from /root/sniper/deploy/.env by name (never printed). Writes /root/gap/leaders.json.
Usage: leaders.py [out.json]"""
import json, sys, urllib.request, os

ENV = "/root/sniper/deploy/.env"
def env(name):
    if os.environ.get(name): return os.environ[name]
    for line in open(ENV):
        line = line.strip()
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

TOK = env("CONSTANTK_TOKEN")
URL = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"

def rpc(method, params=None):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.load(r)
    if "error" in j: raise SystemExit(f"{method}: {j['error'].get('message')}")
    return j["result"]

def klass(c, ver):
    c = c or ""
    if "Bam" in c or "BAM" in c: return "bam"
    if "Harmonic" in c: return "harmonic"
    if c == "JitoLabs": return "jito"
    if "dancer" in c: return "fd"
    if c == "Agave": return "agave"
    if not c and ver:
        try:
            m = int(ver.split(".")[0])
            return "fd" if (m == 0 or m >= 26) else "agave?"
        except Exception: pass
    return "other" if c else "unknown"

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "/root/gap/leaders.json"
    ei = rpc("getEpochInfo")
    first = ei["absoluteSlot"] - ei["slotIndex"]
    sched = {}
    for ep_first in (first, first + ei["slotsInEpoch"]):
        try:
            s = rpc("getLeaderSchedule", [ep_first])
        except SystemExit:
            continue
        if not s: continue
        for ident, idxs in s.items():
            for i in idxs: sched[ep_first + i] = ident
    nodes = {}
    for n in rpc("getClusterNodes"):
        ip = (n.get("gossip") or "").rsplit(":", 1)[0]
        nodes[n["pubkey"]] = {"ip": ip, "ver": n.get("version"), "client": n.get("clientId"),
                              "class": klass(n.get("clientId"), n.get("version")),
                              "tpu_quic": n.get("tpuQuic")}
    rtt = {}
    for p in ("/root/lat/geo_rtt.json",):
        try: rtt.update({k: v for k, v in json.load(open(p)).items() if v is not None})
        except Exception: pass
    geo = {}
    try: geo = json.load(open("/root/geo_ip.json"))
    except Exception: pass
    for k, n in nodes.items():
        n["rtt_ms"] = rtt.get(n["ip"])
        g = geo.get(n["ip"]) or {}
        n["city"] = (g.get("countryCode", "") + "-" + g.get("city", "")) if g else None
    lo = min(sched) if sched else 0
    json.dump({"first_slot": lo, "leaders": {str(s): i for s, i in sched.items()}, "nodes": nodes}, open(out, "w"))
    cls = {}
    for s, i in sched.items():
        c = nodes.get(i, {}).get("class", "unknown"); cls[c] = cls.get(c, 0) + 1
    print(f"leaders: {len(sched)} slots from {lo}, {len(nodes)} nodes; slot share by class: " +
          ", ".join(f"{k} {v*100/len(sched):.0f}%" for k, v in sorted(cls.items(), key=lambda x: -x[1])))

if __name__ == "__main__":
    main()
