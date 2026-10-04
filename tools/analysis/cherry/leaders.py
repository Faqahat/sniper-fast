#!/usr/bin/env python3
"""Long run, leader stage (run ON CHERRY after the run: RPC + ping from where we trade). For every slot of the run: its
leader; for every leader: client version, gossip IP, TPU-QUIC host (same host or a relayer in front), stake, Jito /
BAM, DoubleZero (IBRL user owned by its identity, or its IP), round-trip time from Cherry, city/country/ASN.
usage: leaders.py <run name prefix, e.g. long-1> -> runs/<prefix>-leaders.json"""
import json, sys, glob, os, subprocess, re, urllib.request, concurrent.futures as cf

os.chdir("/root/arb-lab")
PFX = sys.argv[1]
env = dict(l.strip().split("=", 1) for l in open(".env") if "=" in l and not l.startswith("#"))
URL = env["RMR_RPC_URL"]

def rpc(method, params):
    req = urllib.request.Request(URL, json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(), {"content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60)).get("result")

slots = []
for f in sorted(glob.glob(f"runs/{PFX}*/slots.log")):
    for l in open(f):
        p = l.split()
        if len(p) > 2: slots.append(int(p[1]))
lo, hi = min(slots), max(slots)
leaders = []
s = lo
while s <= hi:
    n = min(5000, hi - s + 1)
    leaders += rpc("getSlotLeaders", [s, n]) or []
    s += n
print(f"slots {lo}..{hi}: {len(leaders)} leaders, {len(set(leaders))} distinct", file=sys.stderr)

nodes = {n["pubkey"]: n for n in rpc("getClusterNodes", [])}
va = rpc("getVoteAccounts", [{"commitment": "confirmed"}])
stake = {v["nodePubkey"]: v["activatedStake"] for v in va["current"] + va["delinquent"]}
# Jito's validator list (Cherry gets 403: fetched elsewhere into runs/kobe.json when needed)
try:
    src = open("runs/kobe.json").read() if os.path.exists("runs/kobe.json") else urllib.request.urlopen("https://kobe.mainnet.jito.network/api/v1/validators", timeout=60).read()
    kobe = {v["identity_account"]: v for v in json.loads(src)["validators"]}
except Exception as e:
    kobe = {}; print("kobe:", e, file=sys.stderr)
# DoubleZero: IBRL users (validators connected for unicast) by owner identity and by client IP
dz_owner, dz_ip = {}, {}
# the DZ ledger read can be slow: wait up to 5 min, keep a copy, fall back to the last copy
try:
    txt = subprocess.run(["doublezero", "user", "list"], capture_output=True, text=True, timeout=300).stdout
    if txt.count("\n") > 100: open("runs/dz-users.txt", "w").write(txt)
except Exception as e:
    print("doublezero user list:", e, file=sys.stderr); txt = ""
if txt.count("\n") <= 100 and os.path.exists("runs/dz-users.txt"): txt = open("runs/dz-users.txt").read()
for l in txt.splitlines()[1:]:
    c = [x.strip() for x in l.split("|")]
    if len(c) < 17: continue
    row = {"user_type": c[2], "device": c[4], "location": c[5], "client_ip": c[7], "status": c[13], "owner": c[16], "groups": c[3][:80]}
    if c[2] == "IBRL" or c[1] == "solana":
        dz_owner.setdefault(c[16], row); dz_ip.setdefault(c[7], row)

def ping(h):
    if not h: return None
    try:
        out = subprocess.run(["ping", "-c", "3", "-i", "0.2", "-W", "1", "-q", h], capture_output=True, text=True, timeout=8).stdout
        m = re.search(r"= ([\d.]+)/", out)
        return float(m.group(1)) if m else None
    except Exception: return None

ids = sorted(set(leaders))
ip = {k: (nodes.get(k, {}).get("gossip") or "").split(":")[0] for k in ids}
with cf.ThreadPoolExecutor(32) as ex: rtt = dict(zip(ids, ex.map(lambda k: ping(ip[k]), ids)))
geo = {}
ips = sorted({v for v in ip.values() if v})
for i in range(0, len(ips), 100):
    try:
        req = urllib.request.Request("http://ip-api.com/batch?fields=query,city,countryCode,as", json.dumps(ips[i:i + 100]).encode(), {"content-type": "application/json"})
        for g in json.load(urllib.request.urlopen(req, timeout=30)): geo[g["query"]] = g
    except Exception as e: print("geo:", e, file=sys.stderr)
info = {}
for k in ids:
    n = nodes.get(k, {}); kb = kobe.get(k, {})
    q = (n.get("tpuQuic") or "").split(":")[0]
    d = dz_owner.get(k) or dz_ip.get(ip[k])
    g = geo.get(ip[k], {})
    info[k] = {"version": n.get("version"), "ip": ip[k], "tpu_same_host": (q == ip[k]) if q else None, "tpu_host": q, "stake_sol": round(stake.get(k, 0) / 1e9),
               "jito": kb.get("running_jito"), "bam": kb.get("running_bam"), "bam_rate": kb.get("bam_connection_rate"),
               "dz": bool(d), "dz_device": d and d["device"], "dz_location": d and d["location"], "rtt_ms": rtt.get(k),
               "city": g.get("city"), "country": g.get("countryCode"), "asn": g.get("as")}
json.dump({"first_slot": lo, "leaders": leaders, "info": info}, open(f"runs/{PFX}-leaders.json", "w"))
print(f"wrote runs/{PFX}-leaders.json: {len(info)} leaders, {sum(1 for v in info.values() if v['dz'])} on DoubleZero, "
      f"{sum(1 for v in info.values() if v['bam'])} BAM, {sum(1 for v in info.values() if v['rtt_ms'] is not None)} answered ping", file=sys.stderr)
