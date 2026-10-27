#!/usr/bin/env python3
# LANDING2 step N2 (read-only network probe, runs ON a server via `ssh ... python3 -I -`; writes nothing there, prints JSON lines).
# Per target: ICMP ping 8 x at 1/s (ping -i 1) and TCP connect 4 x at 1/s (time to SYN-ACK or to RST = one round trip).
# At most PAR targets at once (~PAR probes/s in total). Targets come from targets.json (embedded by n2_run.sh).
# usage (local): python3 n2_probe.py --emit targets.json > /tmp/x.py ; ssh host python3 -I - < /tmp/x.py
import json, sys

TEMPLATE = r'''
import json, socket, subprocess, time, re, sys, errno
from concurrent.futures import ThreadPoolExecutor
T = json.loads(TARGETS)
PAR = 16
out = []
def emit(d):
    sys.stdout.write(json.dumps(d) + "\n"); sys.stdout.flush()

def ping(ip, n=8):
    try:
        o = subprocess.run(["ping", "-n", "-c", str(n), "-i", "1", "-W", "1", ip], capture_output=True, text=True, timeout=n + 6).stdout
    except Exception as e:
        return dict(err=str(e)[:60])
    rtts = [float(x) for x in re.findall(r"time=([\d.]+) ms", o)]
    return dict(n=n, got=len(rtts), rtts=rtts)

def tcp(ip, port, n=4):
    res = []
    for k in range(n):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(1.0)
        t0 = time.perf_counter()
        try:
            s.connect((ip, port)); res.append(("ok", (time.perf_counter() - t0) * 1e3))
        except ConnectionRefusedError:
            res.append(("rst", (time.perf_counter() - t0) * 1e3))
        except socket.timeout:
            res.append(("timeout", None))
        except OSError as e:
            res.append(("err" + str(e.errno), None))
        finally:
            s.close()
        time.sleep(max(0.0, 1.0 - (time.perf_counter() - t0)))
    return res

def resolve(h):
    try:
        return sorted({a[4][0] for a in socket.getaddrinfo(h, None, socket.AF_INET)})[:2]
    except Exception as e:
        return []

jobs = []   # (kind, label, ip, ports)
for h in T["hosts"]:
    for ip in resolve(h):
        jobs.append(("host", h, ip, T["ports"].get(h, [443])))
seen = set()
for pk, l in T["leaders"].items():
    for role in ("gossip", "tpu_quic"):
        v = l.get(role)
        if not v: continue
        ip, port = v
        if not ip or not port: continue
        key = (ip, role)
        if key in seen: continue
        seen.add(key)
        # TCP: the gossip port (validators listen for TCP ip-echo there); the TPU port is UDP/QUIC -> TCP gets RST or nothing
        jobs.append(("leader_" + role, pk, ip, [port]))
emit(dict(kind="meta", host=socket.gethostname(), t=time.time(), jobs=len(jobs)))

SKIP = set(tuple(x) for x in json.loads(SKIPJ))
jobs = [j for j in jobs if (j[0], j[1], j[2]) not in SKIP]
emit(dict(kind="meta2", todo=len(jobs), skipped=len(SKIP)))

def run(j):
    kind, label, ip, ports = j
    try:
        d = dict(kind=kind, label=label, ip=ip, icmp=ping(ip), tcp={str(p): tcp(ip, p) for p in ports})
    except Exception as e:
        d = dict(kind=kind, label=label, ip=ip, err=str(e)[:80])
    emit(d)

with ThreadPoolExecutor(PAR) as ex:
    list(ex.map(run, jobs))
emit(dict(kind="done", t=time.time()))
'''

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--emit":
        t = json.load(open(sys.argv[2]))
        skip = []
        if len(sys.argv) == 4:      # an earlier partial output: skip the jobs already done
            for l in open(sys.argv[3]):
                d = json.loads(l)
                if d.get("kind", "").startswith(("host", "leader")) and "icmp" in d: skip.append([d["kind"], d["label"], d["ip"]])
        hosts = sorted(set(t["hosts"]["FRA"]))
        slim = dict(hosts=hosts, ports=t["ports"], leaders={pk: dict(gossip=l["gossip"], tpu_quic=l["tpu_quic"]) for pk, l in t["leaders"].items()})
        print("TARGETS = " + repr(json.dumps(slim)))
        print("SKIPJ = " + repr(json.dumps(skip)))
        print(TEMPLATE)
    else:
        print(__doc__ if __doc__ else "usage: n2_probe.py --emit targets.json")
