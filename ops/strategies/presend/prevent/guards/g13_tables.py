#!/usr/bin/env python3
"""GUARDS step 13: the per-run table over all 20 live runs (DIRECT = MEASURED live fills blocked/removed at their real landing; REPLAY =
custom37 paired replay incl. replacement fills, 7 runs) + RESULTS.json / RESULTS.txt assembly.
usage: g13_tables.py"""
import json, pickle, os
D = "/home/moiz/sniper-data/prevent/guards"
ORDER = ["F21", "F22", "F23", "F24", "F26", "F27", "F28", "A16", "A17", "A19", "A20", "A24", "A25", "A26", "A27", "A34", "A35", "A36", "A37", "A38"]
RP = {"F26": "f26", "F27": "f27", "F28": "f28", "A34": "r34", "A35": "r35", "A36": "r36", "A37": "r37"}
R = pickle.load(open(f"{D}/feats.pkl", "rb"))
FIXC = 0.003524
def sc(o): return (o["pnl"] + FIXC) * 0.696 / (o["spend"] / 1e9) - FIXC
dr = json.load(open(f"{D}/direct.json")); cd = json.load(open(f"{D}/ctx_direct.json")); rs = json.load(open(f"{D}/replay_scores.json"))
cr = json.load(open(f"{D}/creator.json"))
def rp(var, run):
    k = RP.get(run)
    if not k or var not in rs or k not in rs[var]["per_run"]: return None
    return rs[var]["per_run"][k]["delta"]
lines = ["PER RUN (SOL at 0.696 SOL size; DIRECT = minus the realized P&L of the live fills the rule blocks, MEASURED; REPLAY = custom37 paired replay",
         "incl. replacement fills and extra failed tries, r37 config, INFERRED parts = phantom tries; '-' = run not in the replay set)",
         f"{'run':4s} {'fills':>5s} {'live P&L':>8s} | {'A0.75 dir':>9s} {'A0.75 rpl':>9s} | {'B6a1 dir':>8s} {'B6a1 rpl':>8s} | {'lim.85 if 6% dir':>16s} {'rpl':>7s} | {'creator<1% dir':>14s}"]
tab = {}
for run in ORDER:
    v = [o for o in R if o["run"] == run]
    live = sum(sc(o) for o in v)
    a_d = dr["A_0.75|OPEN"]["per_run"][run]["gain_scaled"]; b_d = dr["B_6_abs_1|OPEN"]["per_run"][run]["gain_scaled"]
    c_d = cd[run]["d15"][1]; k_d = cr[run]["Z1"][1]
    a_r = rp("guard A_0.75_open", run); b_r = rp("guard B6a1_open", run); c_r = rp("guard sign0.15_open", run)
    f = lambda x: f"{x:+.3f}" if x is not None else "-"
    tab[run] = {"fills": len(v), "live_scaled": live, "A075_direct": a_d, "A075_replay": a_r, "B6a1_direct": b_d, "B6a1_replay": b_r, "lim085_direct": c_d, "lim085_replay": c_r, "creator1_direct": k_d}
    lines.append(f"{run:4s} {len(v):5d} {live:+8.3f} | {a_d:+9.3f} {f(a_r):>9s} | {b_d:+8.3f} {f(b_r):>8s} | {c_d:+16.3f} {f(c_r):>7s} | {k_d:+14.3f}")
pk = [r for r in ORDER if r not in ("A37", "A38")]
for key, lab in (("A075_direct", "A0.75 direct"), ("B6a1_direct", "B6a1 direct"), ("lim085_direct", "limit .85 if other 6% holder, direct"), ("creator1_direct", "creator<1% direct")):
    g = sum(tab[r][key] for r in pk); p = sum(1 for r in pk if tab[r][key] > 1e-9); m = sum(1 for r in pk if tab[r][key] < -1e-9)
    lines.append(f"{lab}: PICK (18 runs) {g:+.3f}, runs +{p}/-{m}; r37 {tab['A37'][key]:+.3f}; r38 {tab['A38'][key]:+.3f}")
json.dump(tab, open(f"{D}/per_run.json", "w"), indent=1)
open(f"{D}/per_run.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
