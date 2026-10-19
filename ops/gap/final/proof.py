#!/usr/bin/env python3
"""Kernel-level proof: between each create detection and its first send-path write there is no network round trip.
Inputs (dry run TAG in /root/gap/final): net_TAG.txt (bpftrace: C/W lines, CLOCK_MONOTONIC ns), fd2_TAG.txt (fd -> peer
snapshots), trace_TAG.jsonl (engine --lat-trace: fire lines with t_decide_mono, create_deq_to_decide_us, writes[]).
Window per fire = [create dequeued (detection) , first send-path write done]. Every socket write / connect inside it is
listed by thread and peer. Usage: proof.py TAG"""
import sys, json, collections, bisect
D = "/root/gap/final"; tag = sys.argv[1]
def pct(v, q):
    if not v: return float("nan")
    v = sorted(v); i = (len(v) - 1) * q; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)
NAMES = [("64.130.50.91:80", "helius"), ("64.130.47.135:", "nozomi"), ("185.191.117.97:", "astralane"), ("84.32.100.212:10000", "landx-fra3"),
         ("64.34.85.119:8443", "kaldera(feed)"), ("64.34.85.119:443", "ck443"), ("151.241.178.73:", "erpc(feed)")]
def label(peer):
    for k, v in NAMES:
        if peer.startswith(k): return v
    if peer.startswith("64.130.") and peer.endswith(":443"): return "jito-bundle"
    return "other:" + peer
fdpeer = {}; fdlink = {}
import re, os
for fn in (f"{D}/fd3_{tag}.txt", f"{D}/fd_{tag}.txt"):
    if not os.path.exists(fn): continue
    for line in open(fn):
        if line.startswith("T "): continue
        p = line.split()
        if line.startswith("R "): p = p[1:]
        if len(p) >= 6 and p[0] in ("tcp", "udp"):
            for fd in re.findall(r"fd=(\d+)", line): fdpeer.setdefault(int(fd), p[5])
for line in open(f"{D}/fd2_{tag}.txt"):
    p = line.split()
    if len(p) >= 4 and p[0] == "S": fdpeer[int(p[1])] = p[3]
    elif len(p) >= 3 and p[0] == "L": fdlink.setdefault(int(p[1]), p[2])
ev = []
for line in open(f"{D}/net_{tag}.txt"):
    p = line.split()
    # tuples: (t, kind, fd, tid, extra)
    if p and p[0] == "W" and len(p) >= 6: ev.append((int(p[1]), "W", int(p[3]), int(p[2]), int(p[4])))
    elif p and p[0] == "C" and len(p) >= 6: ev.append((int(p[1]), "C", int(p[3]), int(p[2]), f"{p[4]}:{p[5]}"))
ev.sort(); ts = [e[0] for e in ev]
def what(fd):
    if fd in fdpeer: return label(fdpeer[fd])
    l = fdlink.get(fd, "?")
    return "eventfd" if "eventfd" in l else ("pipe" if "pipe" in l else ("socket?" if "socket" in l else "file"))
# per-fd write counts over the run (to tell the ck443 connections apart: blockhash refresher, feed, staked-rpc)
fdcount = collections.Counter(e[2] for e in ev if e[1] == "W")
fires = [json.loads(l) for l in open(f"{D}/trace_{tag}.jsonl") if '"ev":"fire"' in l.replace(" ", "")]
print(f"fires: {len(fires)}   trace events: {len(ev)}   (net socket writes total {sum(1 for e in ev if e[1]=='W' and e[2] in fdpeer)})")
rows = []; agg = collections.Counter(); lat_detect_first = []; lat_dec_first = []; loop_tids = collections.Counter()
send_fds = collections.defaultdict(set)
for f in fires:
    td = f["t_decide_mono"]; t0 = td - int(f.get("create_deq_to_decide_us", 0)) * 1000
    t1 = td + int(f.get("decide_to_first_write_ns", 0))
    # the first send write = the socket write closest to t1 (exit time)
    i0 = bisect.bisect_left(ts, t0 - 1000); i1 = bisect.bisect_right(ts, t1 + 20000)
    inwin = [e for e in ev[i0:i1] if e[0] >= t0 and e[0] <= t1 + 2000]
    first = None
    for e in inwin:
        if e[1] == "W" and what(e[2]) in ("helius", "nozomi", "astralane", "landx-fra3", "jito-bundle", "ck443"):
            first = e; break
    if first: loop_tids[first[3]] += 1
    lat_detect_first.append((t1 - t0) / 1000); lat_dec_first.append(f.get("decide_to_first_write_ns", 0) / 1000)
    before = [e for e in inwin if first is None or e[0] < first[0]]
    c = collections.Counter()
    for e in before:
        k = "connect" if e[1] == "C" else what(e[2])
        same = first is not None and e[3] == first[3]
        c[k + ("@hot-thread" if same else "@other-thread")] += 1
    agg.update(c)
    rows.append((f["id"], f.get("route"), f.get("create_deq_to_decide_us"), (t1 - t0) / 1000, f.get("decide_to_first_write_ns", 0) / 1000,
                 [w["path"] for w in f.get("writes", [])], dict(c)))
print(f"\ncreate detected -> first send write: p50 {pct(lat_detect_first,.5):.0f} us, p99 {pct(lat_detect_first,.99):.0f} us, max {max(lat_detect_first) if lat_detect_first else 0:.0f}")
print(f"decision -> first send write:        p50 {pct(lat_dec_first,.5):.0f} us, p99 {pct(lat_dec_first,.99):.0f} us, max {max(lat_dec_first) if lat_dec_first else 0:.0f}")
print("\nper fire: id route detect->decide(us) detect->first_write(us) decide->first_write(us) paths | writes/connects BEFORE the first send write, by target")
for r in rows: print(f"  {r[0]:3d} {r[1]:22s} {r[2]:6} {r[3]:9.0f} {r[4]:9.0f}  {'+'.join(r[5]):45s} | {r[6] or 'none'}")
print(f"\nall windows together, writes before the first send write: {dict(agg) or 'none'}")
net = {k: v for k, v in agg.items() if k.split("@")[0] not in ("eventfd", "pipe", "file")}
hot = {k: v for k, v in net.items() if k.endswith("@hot-thread")}
print(f"NETWORK writes/connects inside detection->first-write windows: {sum(net.values())} {net or ''}")
print(f"  ... of them on the thread that does the buy write (the event loop): {sum(hot.values())} {hot or ''}")
print(f"threads doing the first send write: {dict(loop_tids)}")
print("\nsocket fds seen: " + ", ".join(f"fd{fd}={label(p)}({fdcount[fd]} writes)" for fd, p in sorted(fdpeer.items())))
