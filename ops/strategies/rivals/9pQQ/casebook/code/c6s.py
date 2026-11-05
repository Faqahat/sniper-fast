#!/usr/bin/env python3
"""short digest: one line per trip + taken/skipped/hold tables (from c6_digest output file). usage RUN MINT"""
import sys, subprocess, re
run, m = sys.argv[1], sys.argv[2]
subprocess.run(["python3", "-W", "ignore", "/home/moiz/sniper/ops/strategies/rivals/9pQQ/casebook/code/c6_digest.py", run, m], capture_output=True)
txt = open(f"/home/moiz/sniper-data/rivals/9pQQ/casebook/tapes/{run}/{m}.digest.txt").read().split("\n")
out = []; cur = None
for l in txt:
    if l.startswith("T") and " buy +" in l:
        mm = re.match(r"(T\d+) buy \+(\d+) (\S+ \S+) mc ([\d.]+).*vs_exit (\S+) since_sell (\S+) \| trig\[(\S+)\] nf10 (\S*) ch10 (\S*) ch50 (\S*) g_open (\d+)", l)
        cur = dict(zip("T age t mc vx ss trig nf10 ch10 ch50 go".split(), mm.groups())); cur["pre"] = []
    elif cur and l.startswith("     <") and "sell" not in cur: cur["pre"].append(l.split()[1])
    elif cur and l.startswith("   hold"):
        mm = re.search(r"hold (\d+) sl \((\d+) s\): (\d+) outside trades, \+([\d.]+)/-([\d.]+) SOL, ret hi (\S+) lo (\S+); exit ret (\S+)%", l)
        cur["hold"] = mm.groups(); cur["sell"] = 1
    elif cur and l.startswith("   sell"):
        mm = re.search(r"sell \+(\d+) (\S+) trig\[(\S+)\] since_ob (\S*) peak_ret (\S+) dd_at_sell (\S+) ch3 (\S+)%", l)
        g = mm.groups(); h = cur["hold"]
        out.append(f"{cur['T']:>4} {cur['t'][6:]} +{cur['age']:<6} mc{float(cur['mc']):6.1f} ch10 {cur['ch10']:>6} nf10 {cur['nf10']:>7} ss {cur['ss']:>6} vx {cur['vx']:>6} pre[{' '.join(cur['pre'][-3:])}] "
                   f"| {g[1]} hold {h[0]}sl/{h[1]}s n{h[2]} ret {h[7]} pk {g[4]} dd {g[5]} ch3 {g[6]} sob {g[3]} tr{g[2]}")
        cur = None
    elif l.startswith("## flat") or l.startswith("eligible") or l.startswith("  ") or l.startswith("## hold") or l.startswith("## after") or l.startswith("###") or l.startswith("trades"):
        out.append(l)
print("\n".join(out))
