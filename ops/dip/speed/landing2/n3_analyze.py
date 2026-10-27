#!/usr/bin/env python3
# LANDING2 step N3: network placement tables from the probes (both servers).
# RTT per target = min and median of the ICMP replies (ms); TCP = time to SYN-ACK (ok) or RST (rst) = one round trip.
# Leaders: gossip IP = the validator itself (where the block is made); TPU-QUIC IP = its front (own / Jito relayer / BAM node / Harmonic relay).
import json, collections, sys
import numpy as np

OUT = "/home/moiz/sniper-data/landing2"
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
from l3_timeline import client_class, front

T = json.load(open(f"{OUT}/targets.json"))
L = T["leaders"]


def load(srv):
    d = {}
    for fn in (f"{OUT}/probe_{srv}.jsonl", f"{OUT}/probe_{srv}_2.jsonl"):
        for l in open(fn):
            r = json.loads(l)
            if r.get("kind", "").startswith(("host", "leader")) and "icmp" in r: d[(r["kind"], r["label"], r["ip"])] = r
    return d


def icmp(r):
    v = (r.get("icmp") or {}).get("rtts") or []
    return (min(v), float(np.median(v)), len(v)) if v else (None, None, 0)


def tcp(r):
    out = []
    for port, lst in (r.get("tcp") or {}).items():
        v = [ms for st, ms in lst if st in ("ok", "rst") and ms is not None]
        kinds = collections.Counter(st for st, _ in lst)
        out.append((port, min(v) if v else None, float(np.median(v)) if v else None, dict(kinds)))
    return out


P = {s: load(s) for s in ("FRA", "AMS")}
print("probe records:", {s: len(v) for s, v in P.items()})
fmt = lambda x: "-" if x is None else f"{x:.2f}"

# ---------------- send endpoints / feeds / block engines
print("\n## Endpoints (ICMP min / median ms | TCP connect min / median ms), from FRA and from AMS")
hosts = sorted({k[1] for s in P for k in P[s] if k[0] == "host"})
print(f"{'host':42s} | {'FRA icmp':13s} {'FRA tcp':13s} | {'AMS icmp':13s} {'AMS tcp':13s} | ip (FRA / AMS)")
for h in hosts:
    cells, ips = [], []
    for s in ("FRA", "AMS"):
        rs = [r for k, r in P[s].items() if k[0] == "host" and k[1] == h]
        if not rs: cells += ["-", "-"]; ips.append("-"); continue
        best = min(rs, key=lambda r: icmp(r)[0] if icmp(r)[0] is not None else 1e9)
        mi, md, n = icmp(best); tc = tcp(best)
        cells.append(f"{fmt(mi)} / {fmt(md)}"); cells.append(" ".join(f"{fmt(a)} / {fmt(b)}" for _, a, b, _ in tc) or "-")
        ips.append(",".join(sorted({r['ip'] for r in rs})))
    print(f"{h:42s} | {cells[0]:13s} {cells[1]:13s} | {cells[2]:13s} {cells[3]:13s} | {ips[0]} / {ips[1]}")

# ---------------- leaders: validator (gossip) vs front (TPU)
def leader_rtt(srv, pk, role):
    l = L.get(pk) or {}
    v = l.get(role)
    if not v or not v[0]: return None
    r = P[srv].get(("leader_" + role, pk, v[0]))
    if r is None:       # the same IP probed under another leader's label
        r = next((x for k, x in P[srv].items() if k[0] == "leader_" + role and k[2] == v[0]), None)
    if r is None: return None
    mi, md, n = icmp(r)
    if mi is None:      # no ICMP answer: TCP (gossip port ip-echo, or a RST from the TPU host)
        t = [a for _, a, _, _ in tcp(r) if a is not None]
        return min(t) if t else None
    return mi


fires = json.load(open(f"{OUT}/fires_engine.json"))
print("\n## Our 250 nonce-era fires: RTT from the firing server to the leader's FRONT (TPU) and to the VALIDATOR (gossip IP)")
print(f"{'client':10s} {'front':15s} {'fires':>5s} | {'front RTT p50 / p90':22s} | {'validator RTT p10 / p50 / p90':30s} | validator > 2 ms")
groups = collections.defaultdict(list)
for a in fires:
    l = L.get(a["leader"]) or {}
    k = (client_class(a["client"]), front(l))
    groups[k].append((leader_rtt(a["srv"], a["leader"], "tpu_quic"), leader_rtt(a["srv"], a["leader"], "gossip")))
    groups[("ALL", "")].append(groups[k][-1])
for k in sorted(groups, key=lambda k: -len(groups[k])):
    v = groups[k]; fr = [x for x, _ in v if x is not None]; va = [y for _, y in v if y is not None]
    p = lambda arr, ps: " / ".join(f"{x:.2f}" for x in np.percentile(arr, ps)) if arr else "-"
    print(f"{k[0]:10s} {k[1]:15s} {len(v):5d} | {p(fr, (50, 90)):22s} | {p(va, (10, 50, 90)):30s} | {sum(1 for y in va if y > 2)}/{len(va)}")

print("\n## Validator RTT of the fired leaders, by server (unique leaders)")
for srv in ("FRA", "AMS"):
    lds = sorted({a["leader"] for a in fires if a["srv"] == srv})
    v = [(pk, leader_rtt(srv, pk, "gossip"), leader_rtt(srv, pk, "tpu_quic"), (L.get(pk) or {}).get("client")) for pk in lds]
    va = [x[1] for x in v if x[1] is not None]
    print(f"  {srv}: {len(lds)} leaders | validator RTT p10/p50/p90 {np.percentile(va, 10):.2f} / {np.percentile(va, 50):.2f} / {np.percentile(va, 90):.2f} ms"
          f" | <1 ms {sum(1 for x in va if x < 1)} | 1-5 ms {sum(1 for x in va if 1 <= x < 5)} | 5-15 ms {sum(1 for x in va if 5 <= x < 15)} | >=15 ms {sum(1 for x in va if x >= 15)}")
    far = sorted([x for x in v if x[1] is not None and x[1] >= 5], key=lambda x: -x[1])[:12]
    for pk, g, t, c in far:
        print(f"      far validator: {pk[:8]} {c:18s} validator {g:.1f} ms, front {fmt(t)} ms, fires {sum(1 for a in fires if a['leader'] == pk and a['srv'] == srv)}")

print("\n## Upcoming leaders (next ~3000 slots), validator RTT from each server, by client (slot-weighted share < 2 ms)")
for srv in ("FRA", "AMS"):
    by = collections.defaultdict(list)
    for pk, l in L.items():
        if not l.get("upcoming_slots"): continue
        g = leader_rtt(srv, pk, "gossip")
        if g is None: continue
        by[client_class(l.get("client"))].append((g, l["upcoming_slots"]))
    tot = sum(w for v in by.values() for _, w in v)
    print(f"  {srv}: " + " | ".join(f"{c} {sum(w for g, w in v if g < 2) / max(1, sum(w for _, w in v)):.0%} of {sum(w for _, w in v)} slots" for c, v in sorted(by.items(), key=lambda kv: -sum(w for _, w in kv[1]))))
    allv = [(g, w) for v in by.values() for g, w in v]
    print(f"      all clients: validator < 1 ms {sum(w for g, w in allv if g < 1) / tot:.0%}, < 2 ms {sum(w for g, w in allv if g < 2) / tot:.0%}, < 10 ms {sum(w for g, w in allv if g < 10) / tot:.0%} of slots")

# BAM nodes and the Harmonic relays (fronts) seen from each server
print("\n## Fronts: BAM nodes / Harmonic relays / Jito relayers used by fired leaders (RTT from the firing server)")
for srv in ("FRA", "AMS"):
    fr = collections.defaultdict(set)
    for a in fires:
        if a["srv"] != srv: continue
        l = L.get(a["leader"]) or {}
        f = front(l)
        if f in ("bam-node", "harmonic-relay", "relayer") and l.get("tpu_quic"): fr[f].add(l["tpu_quic"][0])
    for f, ips in fr.items():
        rt = sorted(x for x in (min((icmp(r)[0] for k, r in P[srv].items() if k[2] == ip and icmp(r)[0] is not None), default=None) for ip in ips) if x is not None)
        print(f"  {srv} {f:15s} {len(ips)} IPs, RTT ms: {', '.join(f'{x:.2f}' for x in rt)}")
