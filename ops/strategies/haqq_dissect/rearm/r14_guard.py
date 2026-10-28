#!/usr/bin/env python3
"""REARM step 14 (read-only; G2): (a) the HOLDER GUARD (a buy only executes after the whale's sale: T2 = the armed whale's first sell,
re = the token's next whale dump; implementable on-chain as an assertion on the whale's token account) and (b) the T2 WINDOW LENGTH
(live 10 slots) -> 20 / 30 / 50, with and without the guard. Replay = rsim.run_x (INFERRED), same draw / seeds as tags g2/h2.
MEASURED (tape): when the armed T2 whales sell relative to the window. Out: r14.txt"""
import sys, os, pickle, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r8_report as R8
import dv8lib as L
OUT = R8.OUT
Lo = []
def P(s=""): print(s, flush=True); Lo.append(s)
days = [0, 1, 2, 3, 4, 5, 6]
RE = "any:20:30:8:2"

# (b0) MEASURED: when do T2 whales first sell (slots after the trigger)?
P("# Holder guard and T2 window length")
P("\n## 1. When the T2 whale first sells, slots after its trigger buy (MEASURED tape, usable hours, v2 vanilla, not create slot)")
P("| Day | T2 triggers | <= 10 (inside today's window) | 11-20 | 21-30 | 31-50 | > 50 | never on the tape |")
P("|---|---|---|---|---|---|---|---|")
tot = np.zeros(7)
for d in days:
    T2 = pickle.load(open(f"{OUT}/ev_D{d}.pkl", "rb"))["T2"]
    T2 = [x for x in T2 if x["v2"] is not False and not x["cashback"] and x["age_slots"] > 0]
    c = np.zeros(7); c[0] = len(T2)
    for x in T2:
        ws = x["whale_sell"]
        if ws is None: c[6] += 1; continue
        g = ws[0] - x["slot"]
        c[1 + int(np.searchsorted([10, 20, 30, 50], g, side="left"))] += 1
    tot += c
    P(f"| {L.day_name(d)} | {c[0]:,.0f} | " + " | ".join(f"{100 * v / c[0]:.0f}%" for v in c[1:]) + " |")
P(f"| all | {tot[0]:,.0f} | " + " | ".join(f"{100 * v / tot[0]:.0f}%" for v in tot[1:]) + " |")


def base_net(res, lvl="model"):
    t = R8.tot(res["base"]); return R8.level(t["pf"], t["fee"], t["f"], lvl), t


P("\n## 2. Today's pre-send (base, no re-arm) under the guard / longer T2 windows: change vs today (window 10, no guard), SOL per day")
P("| Day | today model | W20 | W30 | W50 | guard W10 | guard W20 | guard W30 | guard W50 | fills today / guard W10 / guard W50 | fees today / guard W50 |")
P("|---|---|---|---|---|---|---|---|---|---|---|")
S = collections.defaultdict(float)
for d in days:
    r0 = R8.load_day(d, ["g2"])
    if r0 is None: continue
    n0, t0 = base_net(r0)
    cells = []; extra = {}
    for tag in ("nw20", "nw30", "nw50", "gw10", "gw20", "gw30", "gw50"):
        r = R8.load_day(d, [tag])
        if r is None: cells.append("n/a"); continue
        n, t = base_net(r); extra[tag] = t
        delta = n - n0
        # calibrated: 0.81 on the fill P&L change when > 0
        dpf = t["pf"] - t0["pf"]; dfe = t["fee"] - t0["fee"]
        cal = (0.81 * dpf if dpf > 0 else dpf) - dfe
        cells.append(f"{delta:+.2f} ({cal:+.2f})"); S[tag + "m"] += delta; S[tag + "c"] += cal
    fl = f"{t0['f']} / {extra.get('gw10', {}).get('f', 'n/a')} / {extra.get('gw50', {}).get('f', 'n/a')}"
    fe = f"{t0['fee']:.2f} / {extra['gw50']['fee']:.2f}" if 'gw50' in extra else ""
    P(f"| {L.day_name(d)} | {n0:+.2f} | " + " | ".join(cells) + f" | {fl} | {fe} |")
P("| **Sum** | | " + " | ".join(f"{S[t + 'm']:+.2f} ({S[t + 'c']:+.2f})" for t in ("nw20", "nw30", "nw50", "gw10", "gw20", "gw30", "gw50")) + " | | |")
P("(cells: model (cal 0.81))")

P(f"\n## 3. The re-arm ({RE}) and other re configs on top, with / without the guard: ADDED vs its own base, model (cal), SOL")
P("| Day | re no guard (W10) | re guard W10 | re guard W50 | any:50:30:8:2 no guard | any:50:30:8:2 guard | A's 0.02:50:120:2:0 no guard | A's guard | best combo: guard W? + re vs today |")
P("|---|---|---|---|---|---|---|---|---|")
S = collections.defaultdict(float)
for d in days:
    cells = []
    for tags, c in ((["g2", "h2"], RE), (["gw10"], RE), (["gw50"], RE), (["nw10x"], "any:50:30:8:2"), (["gw10"], "any:50:30:8:2"),
                    (["g2"], "0.02:50:120:2:0"), (["gw10"], "0.02:50:120:2:0")):
        r = R8.load_day(d, tags)
        if r is None or c not in r: cells.append("n/a"); continue
        m = R8.added(r, c)["net"]; k = R8.added(r, c, lvl="cal")["net"]
        cells.append(f"{m:+.2f} ({k:+.2f})"); S[str(tags) + c + "m"] += m; S[str(tags) + c + "c"] += k
    # combo: guard W (best of 10..50 by sum, shown for W10 and W50) + re vs today's base
    r0 = R8.load_day(d, ["g2"]); comb = []
    for tag in ("gw10", "gw50"):
        r = R8.load_day(d, [tag])
        if r is None or r0 is None: continue
        t = R8.tot(r[RE]); t0 = R8.tot(r0["base"])
        dpf = t["pf"] - t0["pf"]; dfe = t["fee"] - t0["fee"]
        comb.append(f"{tag}: {dpf - dfe:+.2f} ({(0.81 * dpf if dpf > 0 else dpf) - dfe:+.2f})"); S[tag + "combm"] += dpf - dfe; S[tag + "combc"] += (0.81 * dpf if dpf > 0 else dpf) - dfe
    P(f"| {L.day_name(d)} | " + " | ".join(cells) + " | " + "; ".join(comb) + " |")
keys = [(["g2", "h2"], RE), (["gw10"], RE), (["gw50"], RE), (["nw10x"], "any:50:30:8:2"), (["gw10"], "any:50:30:8:2"), (["g2"], "0.02:50:120:2:0"), (["gw10"], "0.02:50:120:2:0")]
P("| **Sum** | " + " | ".join(f"{S[str(t) + c + 'm']:+.2f} ({S[str(t) + c + 'c']:+.2f})" for t, c in keys) + f" | gw10 {S['gw10combm']:+.2f} ({S['gw10combc']:+.2f}); gw50 {S['gw50combm']:+.2f} ({S['gw50combc']:+.2f}) |")
open(f"{OUT}/r14.txt", "w").write("\n".join(Lo) + "\n")

# ---- 4. the guard on RE windows only (T2 windows as today): tag gre
P("\n## 4. Guard on the re-arm windows only (T2 as today, W10): ADDED vs today's base, model (cal), SOL")
CS = ["any:20:30:8:2", "any:50:30:8:2", "any:50:120:4:2"]
P("| Day | " + " | ".join(f"{c} guard-re" for c in CS) + f" | {RE} no guard (for reference) |")
P("|---|---|---|---|---|")
S = collections.defaultdict(float)
for d in days:
    r = R8.load_day(d, ["gre"]); r0 = R8.load_day(d, ["g2", "h2"])
    if r is None: continue
    cells = []
    for c in CS:
        m = R8.added(r, c)["net"]; k = R8.added(r, c, lvl="cal")["net"]; cells.append(f"{m:+.2f} ({k:+.2f})"); S[c + "m"] += m; S[c + "c"] += k
    m = R8.added(r0, RE)["net"]; k = R8.added(r0, RE, lvl="cal")["net"]; S["refm"] += m; S["refc"] += k
    P(f"| {L.day_name(d)} | " + " | ".join(cells) + f" | {m:+.2f} ({k:+.2f}) |")
P("| **Sum** | " + " | ".join(f"{S[c + 'm']:+.2f} ({S[c + 'c']:+.2f})" for c in CS) + f" | {S['refm']:+.2f} ({S['refc']:+.2f}) |")
open(f"{OUT}/r14.txt", "w").write("\n".join(Lo) + "\n")
