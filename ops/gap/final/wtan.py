#!/usr/bin/env python3
"""Ground truth from the kernel: decide -> write() syscall exit per send path, from a bpftrace write trace (wtrace.bt).
usage: wtan.py <tag>   (reads /root/fast/wt_<tag>.txt, fd_<tag>.txt, dry_<tag>.log, trace_<tag>.jsonl if present)
Anchor = the decision: the after binary's own t_decide_mono (trace), else the stderr write of the 'RACE decide ... pass=true'
line (old binary: printed by race.due() at the decision, before the fire task is spawned)."""
import sys, re, json, os, collections

tag = sys.argv[1]
D = "/root/gap/final"
PEERS = [('64.130.50.91:80', 'helius'), ('64.130.47.135:443', 'nozomi'), ('185.191.117.97:443', 'astralane'), (':10000', 'landx-fra3'),
         ('64.34.85.119:443', 'ck443')]

def pname(peer):
    for k, v in PEERS:
        if peer.endswith(k) or k in peer: return v
    if re.match(r'64\.130\.(32|50|48|49|51|33|34|35)\.\d+:443', peer): return 'jito?'
    return None

# fd -> peer (all snapshots; conflicts noted)
fdpeer = {}
for line in open(f'{D}/fd_{tag}.txt'):
    m = re.search(r'\s(\S+:\d+)\s+users:(.*)', line)
    if m:
        for fd in re.findall(r'"snipe_engine[^"]*",pid=\d+,fd=(\d+)', m.group(2)):
            fdpeer.setdefault(int(fd), set()).add(m.group(1))
writes = []          # (t, fd, n)
stderr = []          # (t, text)
for line in open(f'{D}/wt_{tag}.txt', errors='replace'):
    p = line.split()
    if line.startswith('S ') and len(p) >= 4: stderr.append((int(p[1]), p[3])); continue
    if not line.startswith('W ') or len(p) < 5: continue
    writes.append((int(p[1]), int(p[3]), int(p[4])))
writes.sort()
# name fds; the constant-k :443 fds: rpc (polls 4+/s) vs staked-rpc (keep-alive 0.5/s + sends): fewest writes = staked-rpc
cnt = collections.Counter(fd for _, fd, _ in writes)
fdname = {}
ck = []
for fd, peers in fdpeer.items():
    names = {pname(x) for x in peers} - {None}
    if len(names) != 1: continue
    nm = names.pop()
    if nm == 'ck443': ck.append(fd)
    else: fdname[fd] = nm
# jito: several 64.130.x fds may exist (block engine + result stream): keep them all as jito
CK = ck
for fd, nm in list(fdname.items()):
    if nm == 'jito?': fdname[fd] = 'jito-bundle'

anchors = []   # (t_decide_mono, mint-ish, route)
tr = f'{D}/trace_{tag}.jsonl'
if os.path.exists(tr):
    for line in open(tr):
        try: v = json.loads(line)
        except Exception: continue
        if v.get('ev') == 'fire': anchors.append((v['t_decide_mono'], v['mint'], v.get('route', ''), v))
else:
    # old binary: the fire point = the create's t_rx (DETECT first=1, realtime) + rx_to_fire_us (FIRE line: taken in the event
    # loop at the fire, after the decision), moved to CLOCK_MONOTONIC with the realtime-monotonic offset
    import time
    off = time.clock_gettime_ns(time.CLOCK_REALTIME) - time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    trx = {}
    for line in open(f'{D}/dry_{tag}.log', errors='replace'):
        m = re.search(r'DETECT .*first=1 .* t_rx=(\d+) .*mint=(\S+)', line)
        if m and m.group(2) not in trx: trx[m.group(2)] = int(m.group(1))
        m = re.search(r'  FIRE slot=\d+ mint=(\S+) .*rx_to_fire_us=(\d+)', line)
        if m and m.group(1) in trx: anchors.append((trx[m.group(1)] + int(m.group(2)) * 1000 - off, m.group(1), '', None))
if CK:
    import bisect
    ts = [w[0] for w in writes]
    def hits(fd):
        n = 0
        for t0, *_ in anchors:
            i = bisect.bisect_left(ts, t0)
            while i < len(writes) and writes[i][0] < t0 + 5_000_000:
                if writes[i][1] == fd: n += 1; break
                i += 1
        return n
    best = max(CK, key=hits)
    fdname[best] = 'staked-rpc'
    print('staked-rpc fd candidates (fires with a write <5 ms):', [(f, hits(f)) for f in CK])
W = 30_000_000  # 30 ms window
res = collections.defaultdict(list)
firsts, lasts = [], []
seen_paths = collections.Counter()
for t0, mint, route, v in anchors:
    per = {}
    for t, fd, n in writes:
        if t < t0: continue
        if t > t0 + W: break
        nm = fdname.get(fd)
        if nm and nm not in per: per[nm] = (t - t0) / 1e3
    expect = None
    if v is not None:
        expect = {w['path'] for w in v['writes']}
        per = {k: x for k, x in per.items() if k in expect}
    for k, x in per.items(): res[k].append(x); seen_paths[k] += 1
    if per:
        firsts.append(min(per.values())); lasts.append(max(per.values()))

def q(v, x):
    v = sorted(v); return v[min(len(v) - 1, int(round((len(v) - 1) * x)))] if v else float('nan')
print(f'== {tag}: {len(anchors)} fires, decide -> write() syscall exit (bpftrace, µs) ==')
print(f"{'path':14} {'n':>4} {'p50':>9} {'p90':>9} {'p99':>9} {'max':>9}")
for k in sorted(res):
    v = res[k]; print(f'{k:14} {len(v):4d} {q(v,.5):9.1f} {q(v,.9):9.1f} {q(v,.99):9.1f} {max(v):9.1f}')
print(f"{'FIRST path':14} {len(firsts):4d} {q(firsts,.5):9.1f} {q(firsts,.9):9.1f} {q(firsts,.99):9.1f} {max(firsts) if firsts else 0:9.1f}")
print(f"{'LAST path':14} {len(lasts):4d} {q(lasts,.5):9.1f} {q(lasts,.9):9.1f} {q(lasts,.99):9.1f} {max(lasts) if lasts else 0:9.1f}")
print('fd map:', {fd: fdname[fd] for fd in sorted(fdname)}, 'ck443 fds by write count:', [(f, cnt.get(f, 0)) for f in ck])
