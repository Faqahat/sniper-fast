#!/usr/bin/env python3
"""exit2 step 6: example TEST trips with links (GMGN token, solscan buy/sell tx from recon lots.pkl matched by (slot, idx)),
the event that fired the rule (who / side / size / slot vs his sell) and the simulated P&L per exit. Out: e6.md"""
import sys, json, pickle, time, numpy as np
OUT = "/home/moiz/sniper-data/e2x1_dissect/exit2"; L = int(sys.argv[1]) if len(sys.argv) > 1 else 66
pkt = lambda t: time.strftime("%m-%d %H:%M:%S", time.gmtime(int(t) + 18000))
Z = np.load(f"{OUT}/tape_his.npz"); slot = Z["slot"].astype(np.int64); idx = Z["idx"].astype(np.int64); user = Z["user"]; buy = Z["buy"].astype(bool); sol = Z["sol"] / 1e9; bt = Z["bt"]
users = json.load(open("/home/moiz/sniper-data/haqqml/fresh/tape/users.json")); mints = json.load(open("/home/moiz/sniper-data/haqqml/fresh/tape/mints.json"))
names = json.load(open("/home/moiz/sniper-data/e2x1_dissect/select/names.json"))
TR = pickle.load(open(f"{OUT}/trips.pkl", "rb")); rows = pickle.load(open(f"{OUT}/e4_rows_{L}.pkl", "rb"))
EV = np.load(f"{OUT}/ev.npz"); META = EV["meta"]; X = EV["X"]; F = list(EV["feats"]); FI = {f: k for k, f in enumerate(F)}
E = np.load(f"{OUT}/e3_scores.npz"); p = E["p"]; THR = float(E["thr"])
lots = pickle.load(open("/home/moiz/sniper-data/e2x1_dissect/recon/lots.pkl", "rb"))
bysi = {(l["s"], l["i"]): l for l in lots}
def links(t):
    l = bysi.get((int(slot[t["entry"]]), int(idx[t["entry"]])))
    if not l: return "-", "-"
    return f"[buy](https://solscan.io/tx/{l['buy_sig']})", (f"[sell](https://solscan.io/tx/{l['sells'][0][0]})" if l["sells"] else "-")
def who(u, t, k):
    tags = []
    if int(Z["sid"]) == u: tags.append("TWIN Grozoe")
    if X[k, FI["ev_creator"]]: tags.append("creator")
    if X[k, FI["ev_trig"]]: tags.append("trigger wallet")
    if X[k, FI["ev_copier"]]: tags.append("copier")
    if X[k, FI["ev_follower"]]: tags.append("bought after him")
    if X[k, FI["ev_prebuyer"]]: tags.append("bought before him")
    r = int(X[k, FI["ev_rank"]]); tags.append(f"holder rank {r+1}" if r < 99 else "no balance")
    tags.append(f"{int(X[k, FI['ev_act_mints']])} mints on tape")
    return ", ".join(tags)
first = {}
for k in np.flatnonzero(p >= THR):
    t = int(META[k, 0]); first.setdefault(t, k)
out = ["# exit2 examples (TEST day, 10-27 18:41 -> 10-28 18:41 PKT); P&L in SOL pre tx-costs; H = his entry, O = our 66 ms entry (phi 0.2)\n"]
R = {r["trip"]: r for r in rows}
def row(ti, tag):
    t = TR[ti]; r = R[ti]; m = mints[t["mint"]]; nm = (names.get(m) or ["?"])[0]; b, s = links(t)
    ks = t["sells"][0]; ss = int(slot[ks])
    k = first.get(ti); fire = "no fire (timeout)"
    if k is not None:
        kk = int(META[k, 4]); fire = f"slot {int(META[k,2]) - ss:+d} vs his sell: {'BUY' if buy[kk] else 'SELL'} {sol[kk]:.2f} SOL ({100*X[k,FI['ev_sol_rel']]:.1f}% of curve) by {users[int(user[kk])][:8]} ({who(int(user[kk]), t, k)}); p={p[k]:.2f}; price vs entry {X[k,FI['r']]:.2f}, dd {X[k,FI['dd']]:.2f}, hold {int(X[k,FI['dslots']])} slots"
    out.append(f"### {tag}: [{nm}](https://gmgn.ai/sol/token/{m}) {pkt(t['bt'])} bot {['FRESH','MINUTE','OLD'][t['bot']]} size {t['cost']:.3f} SOL hold {int(r['hold_slots'])} slots  {b} {s}")
    out.append(f"- rule fire: {fire}")
    out.append(f"- H: his real {r['H|real']:+.3f} | HIS(sim) {r['H|HIS']:+.3f} | FIXED {r['H|FIXED']:+.3f} | 200ms {r['H|200ms']:+.3f} | RULE|FIXED {r['H|RULE|FIXED']:+.3f} | RULE q95|FIXED {r['H|RULE@q0.95|FIXED']:+.3f}")
    if "O0.2|HIS" in r: out.append(f"- O(66 ms): HIS {r['O0.2|HIS']:+.3f} | COPY-fill {r['O0.2|HIS|fill']:.2f} | FIXED {r['O0.2|FIXED']:+.3f} | 200ms {r['O0.2|200ms']:+.3f} | RULE|FIXED {r['O0.2|RULE|FIXED']:+.3f} | RULE q95|FIXED {r['O0.2|RULE@q0.95|FIXED']:+.3f}")
    out.append("")
d = sorted(rows, key=lambda r: -(r["H|RULE|FIXED"] - r["H|FIXED"]))
out.append("## Rule exit beats the fixed hold most (gap recovered)")
for r in d[:6]: row(r["trip"], "rule>fixed")
out.append("## Rule|FIXED exit worst vs his real exit (his hold made the most)")
for r in sorted(rows, key=lambda r: (r["H|RULE|FIXED"] - r["H|HIS"]))[:6]: row(r["trip"], "rule<his")
out.append("## Rule fired within +-1 slot of his sell (random 6)")
ok = [r for r in rows if r["trip"] in first and abs(int(META[first[r["trip"]], 2]) - int(slot[TR[r["trip"]]["sells"][0]])) <= 1]
rng = np.random.default_rng(3)
for r in (rng.choice(ok, min(6, len(ok)), replace=False) if ok else []): row(r["trip"], "match")
out.append("## Twin (Grozoe) sold in the same slot (random 5)")
tw = [r for r in rows if any(X[k, FI["sib_sold_slot"]] > 0 for k in np.flatnonzero(META[:, 0] == r["trip"]))]
for r in (rng.choice(tw, min(5, len(tw)), replace=False) if tw else []): row(r["trip"], "twin")
open(f"{OUT}/e6.md", "w").write("\n".join(out) + "\n"); print(len(out))
