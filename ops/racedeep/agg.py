#!/usr/bin/env python3
# READ-ONLY. Aggregate search res.pkl: PnL map, train selection (hist random + fwd run 1), blind test on night.
import sys, collections, statistics as st, json, pickle, math
sys.path.insert(0, "/root/racedeep")
from rdlib import load, stats, fmt
ARG = sys.argv[1] if len(sys.argv) > 1 else "0.4"
try:
    PS, SEL = float(ARG), "blend"   # P(land in S at +100 txs after the trigger); else S+1 mid
except ValueError:
    PS, SEL = 0.4, ARG              # select on one landing, e.g. "S1 front"
D = pickle.load(open("/root/racedeep/res.pkl", "rb"))
res, SIM, XN, hours, hours_f = D["res"], D["SIM"], D["XN"], D["hours"], D["hours_f"]
U = [o for o in load() if o["in_rand"]]
for o in U:
    o["gateB"] = o["dev"] >= 3 and o["glued"] >= 2 and o["n_len"] <= 12
PRE = {"all": lambda o: True, "gateB": lambda o: o["gateB"], "dev>=2": lambda o: o["dev"] >= 2, "dev<=3": lambda o: o["dev"] <= 3}
CAPS = (1.3, 1.6, 2.0, 99)
SETS = ("hist", "fwd", "night")
bys = {s: [o for o in U if o["set"] == s] for s in SETS}
rate_night = len(bys["night"]) / hours * 24   # base launches/day


def pnl(o, j, land, xi, size=2):
    if land == "blend":
        a = SIM[(o["mint"], "S+100", j)][0 if size == 2 else 1][xi]
        b = SIM[(o["mint"], "S1 mid", j)][0 if size == 2 else 1][xi]
        return PS * a + (1 - PS) * b
    return SIM[(o["mint"], land, j)][0 if size == 2 else 1][xi]


def members(pre, trig, win, cap):
    out = {s: [] for s in SETS}
    for s in SETS:
        for o in bys[s]:
            if not PRE[pre](o):
                continue
            if trig == "create":
                out[s].append((o, -1))
                continue
            x = res.get((trig, win), {}).get(o["mint"])
            if x and x[1] <= cap:
                out[s].append((o, x[0]))
    return out


RULES = [(p, "create", "-", 99) for p in PRE]
TRIGS = sorted({k[0] for k in res})
for p in PRE:
    for tn in TRIGS:
        for wn in ("S", "S..S+1", "S..S+2"):
            for c in CAPS:
                RULES.append((p, tn, wn, c))
print(f"selection landing = {SEL} (P(S)={PS} if blend); rules (pre x trigger x window x price-cap) = {len(RULES)}; x {len(XN)} exits = {len(RULES) * len(XN)} combos judged on the blended landing")
print(f"night base launches {len(bys['night'])} over {hours:.2f} h = {rate_night:.0f}/day")

# ---- selection on train
cands = []
for rule in RULES:
    m = members(*rule)
    nh, nf, nn = len(m["hist"]), len(m["fwd"]), len(m["night"])
    if nh < 15 or nf < 15:
        continue
    for xi, xn in enumerate(XN):
        vh = [pnl(o, j, SEL, xi) for o, j in m["hist"]]
        vf = [pnl(o, j, SEL, xi) for o, j in m["fwd"]]
        sh, sf, stn = stats(vh), stats(vf), stats(vh + vf)
        cands.append((min(sh["avg"], sf["avg"]), rule, xi, sh, sf, stn))
print(f"candidate (rule, exit) with n_hist>=15 & n_fwd>=15: {len(cands)}")
ok = [c for c in cands if c[0] > 0 and c[5]["ex3"] > 0]
print(f"passing train (worst-period blended mean > 0 and pooled ex-top3 > 0): {len(ok)}")
ok.sort(key=lambda c: -c[0])


def line(rule, xi, land="blend", size=2):
    m = members(*rule)
    cells = []
    for s in SETS:
        v = [pnl(o, j, land, xi, size) for o, j in m[s]]
        cells.append(f"{s} {fmt(stats(v))}")
    return " | ".join(cells), m


print("\n== TOP 40 by worst-period train mean (blended landing, 2 SOL). Night = blind test.")
seen = set()
top = []
for c in ok:
    key = (c[1], c[2])
    if key in seen:
        continue
    seen.add(key)
    top.append(c)
    if len(top) >= 40:
        break
for c in top:
    rule, xi = c[1], c[2]
    m = members(*rule)
    vn = [pnl(o, j, SEL, xi) for o, j in m["night"]]
    sn = stats(vn)
    fpd = len(vn) / hours * 24
    print(f"{rule[0]:6} | {rule[1]:38} | {rule[2]:7} | cap {rule[3]:4} | {XN[xi]:20} || train worst {c[0]:+.1%} hist {fmt(c[3])} | fwd {fmt(c[4])} || NIGHT {fmt(sn)} | {fpd:.0f}/day -> {sn['avg'] * 2 * fpd if sn['n'] else 0:+.1f} SOL/day @2")

# ---- how did the whole train-positive set do on night? (selection honesty)
vals = []
for c in ok:
    m = members(*c[1])
    v = [pnl(o, j, SEL, c[2]) for o, j in m["night"]]
    if v:
        vals.append(st.mean(v))
if vals:
    print(f"\nAll {len(vals)} train-positive (rule, exit): night mean of means {st.mean(vals):+.2%}, share positive on night {sum(x > 0 for x in vals) / len(vals):.0%}")

# ---- PnL map for key triggers: landing x exit, night and train pooled
print("\n== PnL MAP (pre=all, window S, no price cap): mean (ex-top3) per landing x exit. TRAIN = hist+fwd, TEST = night. 2 SOL")
KEY = ["create", "1x outsider buy>=1", "2x outsider buy>=1", "cum out SOL>=2", "cum out SOL>=5", ">=3 out & >=3 SOL", ">=5 out & >=5 SOL",
       "whale buy>=5", "whale buy>=5 hiprio", "whale buy>=10", "4yFAz buys", "pro wallet buys", "failed txs>=5", "hiprio outsider (cu>=100M or tip>=0.01)",
       "wave1 3out/3SOL then dip<=0.65x peak"]
LANDS = ["S+25", "S+100", "S1 front", "S1 mid", "blend"]
for tn in KEY:
    for wn in (("-",) if tn == "create" else ("S", "S..S+2") if tn.startswith("wave1") else ("S",)):
        rule = ("all", tn, wn, 99)
        m = members(*rule)
        print(f"\n-- {tn} [{wn}]  n train {len(m['hist']) + len(m['fwd'])} / night {len(m['night'])} ({len(m['night']) / hours * 24:.0f}/day) | race share night {sum(o['race'] for o, _ in m['night']) / max(1, len(m['night'])):.0%}"
              f" | med entry/floor @S+100 night {st.median([SIM[(o['mint'], 'S+100', j)][2] for o, j in m['night']]) if m['night'] else 0:.2f}x")
        print("   " + f"{'exit':20} " + " ".join(f"{l:>22}" for l in LANDS))
        for xi, xn in enumerate(XN):
            cells = []
            for ln in LANDS:
                vt = [pnl(o, j, ln, xi) for o, j in m["hist"] + m["fwd"]]
                vn = [pnl(o, j, ln, xi) for o, j in m["night"]]
                a, b = stats(vt), stats(vn)
                cells.append(f"{a['avg']:+5.1%}/{b['avg']:+5.1%}({b['ex3']:+5.1%})")
            print(f"   {xn:20} " + " ".join(f"{c:>22}" for c in cells))
pickle.dump(top, open("/root/racedeep/top.pkl", "wb"))
