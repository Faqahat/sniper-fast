#!/usr/bin/env python3
"""SMARTEXIT step 2: validate the simulator on every run before any policy.
 A  time placement at the REAL sell landing rx time vs the real sell's gross (exit125 method B), per run
 B  replaying the REAL decision time (real exit t) + own lag reproduces the real P&L exactly (settle() identity)
 C  lag (decision -> land) distribution per run; tape coverage; fills whose real exit was TP/SL
 D  exact-125 baseline vs real P&L on r51+ (where the live exit WAS exact 125 ms)"""
import sys, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/smartexit")
import slib as L

F, J, sk = L.load_fills()
print("loaded", len(F), "skipped", dict(sk))
A = collections.defaultdict(list); B = collections.defaultdict(list); lag = collections.defaultdict(list); D = collections.defaultdict(lambda: [0.0, 0.0, 0])
why = collections.Counter()
for f in F:
    s = f.x["sells"][0]
    g = f.value(s["t"])
    A[f.run].append((g - s["sol"]) / s["sol"] * 100 if s["sol"] else 0)
    net, _, _ = L.settle(f, [(f.x["exit"]["t"], 1.0)])
    B[f.run].append(net - f.real)
    lag[f.run].append(f.lag)
    why[(f.run >= 51, f.x["exit"]["why"])] += 1
    if f.run >= 51:
        evs = L.events(f)
        d, w = L.with_tpsl(evs, L.timer_t(f, 125))
        p, _, _ = L.settle(f, [(d, 1.0)])
        D[f.run][0] += p; D[f.run][1] += f.real; D[f.run][2] += 1
for r in sorted(A):
    a = A[r]
    print(f"r{r}: n {len(a)}  A |err|<0.1% {sum(abs(v) < 0.1 for v in a)}/{len(a)} p50 {L.pct(a, .5):+.4f}%  "
          f"B max|err| {max(abs(v) for v in B[r]):.2e} SOL  lag p10/50/90 {L.pct(lag[r], .1):.0f}/{L.pct(lag[r], .5):.0f}/{L.pct(lag[r], .9):.0f} ms")
print("exit reasons", dict(why))
for r, (p, re, n) in sorted(D.items()):
    print(f"D r{r}: n {n} exact-125 model {p:+.4f} vs real {re:+.4f} SOL")
