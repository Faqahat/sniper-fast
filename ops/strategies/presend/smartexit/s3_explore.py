#!/usr/bin/env python3
"""SMARTEXIT step 3 (DEV ONLY): what the hold looks like.
 1 fixed exact timers H (own lag) and fc20 -> the timer curve on DEV
 2 when do followers buy / dumpers sell (rx ms after our fill), sizes
 3 conditional: at decision H=125, split fills by what the engine has seen (net flow, any sell >= X) -> P&L of 125 vs later timers
 4 'sell on seen sell >= X SOL' at any time (event exit) vs 125"""
import sys, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/smartexit")
import slib as L

F, J, _ = L.load_fills(("dev",))
H = J["split_hours"]["dev"]
print("DEV fills", len(F), "hours", round(H, 1))
EV = {id(f): L.events(f) for f in F}
EV20 = {id(f): L.events(f, 0.2) for f in F}

def timer_pnl(f, Hms, fc=0.0):
    evs = EV20[id(f)] if fc else EV[id(f)]
    d, w = L.with_tpsl(evs, L.timer_t(f, Hms))
    return L.settle(f, [(d, 1.0)], fc)[0]

base = {id(f): timer_pnl(f, 125) for f in F}
base20 = {id(f): timer_pnl(f, 125, 0.2) for f in F}
print(f"base t125 {sum(base.values()):+.3f}  fc20 {sum(base20.values()):+.3f}  real {sum(f.real for f in F):+.3f}")
print("\n1) timer curve (gain vs 125, own lag | fc20):")
for Hms in (0, 25, 50, 75, 100, 110, 125, 140, 160, 200, 250, 300, 400, 600, 800, 1000, 1500, 2000, 2500):
    p = sum(timer_pnl(f, Hms) for f in F); p20 = sum(timer_pnl(f, Hms, 0.2) for f in F)
    print(f"  t{Hms:<5} {p:+8.3f} ({p - sum(base.values()):+7.3f})   fc20 {p20:+8.3f} ({p20 - sum(base20.values()):+7.3f})")

print("\n2) timing of other trades (rx ms after fill), DEV:")
bms, sms, bsz, ssz = [], [], [], []
for f in F:
    for e in EV[id(f)]:
        (bms if e.buy else sms).append(e.ms); (bsz if e.buy else ssz).append(e.sol)
for nm, a in (("buys ms", bms), ("sells ms", sms), ("buy SOL", bsz), ("sell SOL", ssz)):
    print(f"  {nm}: n {len(a)} p10/25/50/75/90 " + "/".join(f"{L.pct(a, p):.2f}" for p in (.1, .25, .5, .75, .9)))
for lo, hi in ((-50, 0), (0, 25), (25, 50), (50, 100), (100, 150), (150, 200), (200, 300), (300, 500), (500, 1000), (1000, 2000), (2000, 3000)):
    nb = sum(1 for a in bms if lo <= a < hi); ns = sum(1 for a in sms if lo <= a < hi)
    vb = sum(e.sol for f in F for e in EV[id(f)] if e.buy and lo <= e.ms < hi); vs = sum(e.sol for f in F for e in EV[id(f)] if not e.buy and lo <= e.ms < hi)
    print(f"  [{lo:5},{hi:5}) buys {nb:5} {vb:8.1f} SOL   sells {ns:5} {vs:8.1f} SOL")

print("\n3) at t=125 (engine view, trades with rx < fill+125): split by flow seen; gain of later timers vs 125 per group")
groups = collections.defaultdict(list)
for f in F:
    seen = [e for e in EV[id(f)] if e.ms < 125]
    nb = sum(e.sol for e in seen if e.buy); ns = sum(e.sol for e in seen if not e.buy)
    mx = max((e.sol for e in seen if not e.buy), default=0)
    mk = seen[-1].mark if seen else None
    g = ("flow>0.5" if nb - ns > 0.5 else "flow<-0.5" if nb - ns < -0.5 else "flat") + ("|sell>=1" if mx >= 1 else "")
    groups[g].append(f)
    groups["mark>=1.05" if (mk or 0) >= 1.05 else "mark<1.05"].append(f)
for g, fs in sorted(groups.items()):
    b = sum(base[id(f)] for f in fs)
    row = " ".join(f"t{h}:{sum(timer_pnl(f, h) for f in fs) - b:+.3f}" for h in (75, 200, 300, 600, 1000, 2000))
    print(f"  {g:22} n {len(fs):4} base {b:+.3f} | {row}")

print("\n4) event exit: sell at the first seen outside sell >= X SOL (any time <= Hmax), else timer 125 ")
for X in (0.3, 0.5, 1.0, 2.0, 3.0):
    for mode in ("pre125", "post125_2000"):
        tot = 0
        for f in F:
            evs = EV[id(f)]
            if mode == "pre125":
                d0 = L.timer_t(f, 125)
                trg = next((e for e in evs if (not e.buy) and e.sol >= X and e.t < d0), None)
                d = trg.t + 200_000 if trg else d0
            else:  # hold to 2000 ms unless a sell >= X seen after 125 (sell then)
                d0 = L.timer_t(f, 2000)
                trg = next((e for e in evs if (not e.buy) and e.sol >= X and e.ms >= 125 and e.t < d0), None)
                d = trg.t + 200_000 if trg else d0
            d, w = L.with_tpsl(evs, d)
            tot += L.settle(f, [(d, 1.0)])[0]
        print(f"  X={X:<4} {mode:13} {tot:+.3f} ({tot - sum(base.values()):+.3f})")
