# REVIEW: kernel-level check of the junk-fanout dry run: for each fire, every network syscall of the engine (all threads)
# between the create's dequeue (detection) and the first send-path write; decision -> first send write from bpftrace.
import sys, json, re, socket, subprocess
tag = sys.argv[1]; D = "/root/review"
hosts = {}
cfg = open("/root/lat/final_landing.toml").read()
names = re.findall(r'name\s*=\s*"([^"]+)"[^\[]*?url\s*=\s*"([^"]+)"', cfg, re.S)
rpc_host = re.search(r'rpc_url\s*=\s*"https?://([^/:?"]+)', cfg).group(1)
names.append(("RPC(" + rpc_host.split(".")[0] + ")", "https://" + rpc_host))
ip2name = {}
for n, u in names:
    h = re.sub(r"^[a-z]+://", "", u).split("/")[0].split("?")[0]
    host, _, port = h.partition(":")
    try:
        for ai in socket.getaddrinfo(host, None, socket.AF_INET): ip2name.setdefault(ai[4][0], set()).add(n)
    except Exception as e: print("resolve fail", host, e)
SEND = {"staked-rpc", "jito-bundle", "landx-fra3", "helius", "nozomi", "astralane"}
# fd -> peers over time (ss every 0.5 s)
fdpeer = {}
for l in open(f"{D}/ss_{tag}.txt"):
    if l.startswith("T "): continue
    m = re.search(r"(\S+):(\d+)\s+users:.*fd=(\d+)", l)
    parts = l.split()
    if len(parts) >= 6 and m:
        peer = parts[5]; fd = int(m.group(3)); ip = peer.rsplit(":", 1)[0].strip("[]")
        if ip.startswith("::ffff:"): ip = ip[7:]
        nm = "/".join(sorted(ip2name.get(ip, {peer})))
        fdpeer.setdefault(fd, set()).add(nm)
def cls(fd):
    p = fdpeer.get(fd)
    if not p: return "non-socket/file(fd%d)" % fd
    return "+".join(sorted(p))
ev = []
for l in open(f"{D}/bt_{tag}.txt"):
    p = l.split()
    if not p or p[0] not in ("W", "C"): continue
    try: ev.append((int(p[1]), p[0], int(p[2]), int(p[3]), p[4:]))
    except: pass
ev.sort()
fires = [json.loads(l) for l in open(f"{D}/trace_{tag}.jsonl") if '"ev":"fire"' in l]
import bisect
ts = [e[0] for e in ev]
d2w, det2w = [], []
allbad = 0
print(f"fires {len(fires)}; bpftrace events {len(ev)}; fd classes: " + ", ".join(f"fd{k}={cls(k)}" for k in sorted(fdpeer)))
for f in fires:
    t_dec = f["t_decide_mono"]
    w0 = f["writes"][0]
    t_det = t_dec - (w0["from_create_deq_ns"] - w0["from_decide_ns"])
    # first send-path write seen by the kernel after the decision
    i = bisect.bisect_left(ts, t_det)
    first = None; inwin = []
    for e in ev[i:]:
        t, k, tid, fd, rest = e
        c = cls(fd)
        if t >= t_dec and k == "W" and any(s in c.split("+") for s in SEND):
            first = e; break
        inwin.append((t - t_det, k, tid, c, rest))
        if t > t_dec + 50_000_000: break
    net_bad = [x for x in inwin if not x[3].startswith("non-socket") and not (x[1] == 'W' and x[4] and x[4][0] == '0')]
    zero = [x for x in inwin if x[1] == 'W' and x[4] and x[4][0] == '0']
    allbad += len(net_bad)
    if first:
        d2w.append((first[0] - t_dec) / 1e3); det2w.append((first[0] - t_det) / 1e3)
    print(f"  fire {f['id']:4} {f['route']:22} detect->decide {(t_dec - t_det)/1e3:8.0f} us  decide->first send write (kernel) {((first[0]-t_dec)/1e3) if first else float('nan'):6.1f} us "
          f"(engine {f['decide_to_first_write_ns']/1e3:6.1f}) first={cls(first[3]) if first else '-'} tid={first[2] if first else '-'} | in window: {len(inwin)} syscalls ({len(zero)} zero-length prewarm writes), NON-ZERO network: {len(net_bad)} "
          + (str([(round(x[0]/1e3), x[1], 'tid%d' % x[2], x[3].split('/')[0][:12], 'ret=' + x[4][0] if x[4] else '') for x in net_bad][:6]) if net_bad else "") )
def q(v, p):
    v = sorted(v); return v[min(len(v) - 1, int(round((len(v) - 1) * p)))] if v else float("nan")
print(f"\ndecide -> first send write (kernel): n={len(d2w)} p50 {q(d2w,.5):.1f} us  p90 {q(d2w,.9):.1f}  p99 {q(d2w,.99):.1f}  max {max(d2w) if d2w else 0:.1f}")
print(f"detect -> first send write (kernel): p50 {q(det2w,.5):.0f} us  p99 {q(det2w,.99):.0f} us")
print(f"NON-ZERO network writes/connects inside detection->first-send-write windows: {allbad}")
