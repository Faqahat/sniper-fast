# READ-ONLY offline. Task 1: outside buyers on rule-#2 launches in the first 60 s; per-wallet PnL (window S..S+300 slots, rest marked at last price).
import sys, json, collections, statistics as st
sys.path.insert(0, "/root/comp")
from lib import *
SET = sys.argv[1] if len(sys.argv) > 1 else "r2"
FIRST = 150  # slots ~60 s
per = []  # (wallet, mint) rows
nl = 0
for r in load(f"/root/comp/tapes_{SET}.jsonl"):
    ev, fb = order_launch(r)
    if not ev: continue
    nl += 1
    S = r["slot"]; bw = bundle_set(r)
    last_px = ev[-1]["vsol"] / ev[-1]["vtok"]
    gv, gt = post_bundle_state(r)
    pb_px = gv / gt
    outs = []
    for e in ev:
        if e["buy"] and e["slot"] - S <= FIRST and e["user"] not in bw and e["user"] not in outs: outs.append(e["user"])
    idx = {u: i for i, u in enumerate(outs)}
    ahead_sol = 0.0; ahead_n = 0; seen = set()
    agg = {u: dict(cost=0, proc=0, tb=0, ts=0, land=0, nb=0, ns=0, first=None, sigs=set()) for u in outs}
    for k, e in enumerate(ev):
        u = e["user"]
        if u in agg:
            a = agg[u]
            if e["sig"] not in a["sigs"]:
                a["sigs"].add(e["sig"]); a["land"] += landing_cost(e)
            if e["buy"]:
                a["cost"] += e["sol"] + e["fee"] + e["cfee"]; a["tb"] += e["tok"]; a["nb"] += 1
                if a["first"] is None:
                    pre = pre_state(e)
                    a["first"] = dict(k=k, slot=e["slot"], dslot=e["slot"] - S, d=e["d"], sol=e["sol"] / 1e9, tok=e["tok"], vsol_pre=pre[0] / 1e9,
                                      px_pre=pre[0] / pre[1], px_vs_pb=(pre[0] / pre[1]) / pb_px, impact=(e["vsol"] / e["vtok"]) / (pre[0] / pre[1]) - 1,
                                      n_out_ahead=ahead_n, sol_out_ahead=ahead_sol / 1e9, cup=e["cup"], cul=e["cul"], txfee=e["txfee"], tips=e["tips"],
                                      xf=[x for x in e["xf"] if x[2] == 1][:4], payer=e["payer"], nsig=len(e["signers"]), lc=leader_client(r, e["slot"]))
            else:
                a["proc"] += e["sol"] - e["fee"] - e["cfee"]; a["ts"] += e["tok"]; a["ns"] += 1
        if e["buy"] and u not in bw and e["slot"] - S <= FIRST:
            if u not in seen: ahead_n += 1; seen.add(u)
            ahead_sol += e["sol"]
    for u, a in agg.items():
        rem = max(0, a["tb"] - a["ts"])
        val = rem * last_px * (1 - 0.0125)
        g = (a["proc"] + val - a["cost"]) / 1e9
        per.append(dict(w=u, mint=r["mint"], S=S, bt=r["bt"], dev=r["dev"] / 1e9, gsol=r["gsol"] / 1e9, order=idx[u], cost=a["cost"] / 1e9,
                        pnl_g=g, pnl_n=g - a["land"] / 1e9, land=a["land"] / 1e9, rem_frac=rem / max(1, a["tb"]), nb=a["nb"], ns=a["ns"], f=a["first"]))
json.dump(per, open(f"/root/comp/per_{SET}.json", "w"))
W = collections.defaultdict(list)
for p in per: W[p["w"]].append(p)
print(f"launches {nl}, outside (wallet,launch) pairs {len(per)}, wallets {len(W)}")
def pos(p):
    f = p["f"]; return f["d"] if f["dslot"] == 0 and f["d"] is not None else 1000 + f["dslot"]
rows = []
for w, L in W.items():
    n = len(L); s = sum(p["pnl_n"] for p in L); sg = sum(p["pnl_g"] for p in L)
    ps = sorted(pos(p) for p in L)
    rows.append(dict(w=w, n=n, pnl=s, pnl_g=sg, per=s / n, win=sum(1 for p in L if p["pnl_n"] > 0) / n, medpos=ps[n // 2],
                     inS=sum(1 for p in L if p["f"]["dslot"] == 0) / n, medsz=st.median(p["f"]["sol"] for p in L), cost=sum(p["cost"] for p in L),
                     land=st.median(p["land"] for p in L)))
json.dump(rows, open(f"/root/comp/wallets_{SET}.json", "w"))
def show(title, key, k=15, filt=lambda x: True):
    print("\n" + title)
    print(f"{'wallet':10} {'n':>4} {'pnl_net':>8} {'gross':>8} {'per':>7} {'win':>5} {'medpos':>6} {'inS':>4} {'medsz':>6} {'land':>6}")
    for x in sorted([x for x in rows if filt(x)], key=key)[:k]:
        mp = x["medpos"]; mps = str(mp) if mp < 1000 else f"S+{mp-1000}"
        print(f"{x['w'][:10]} {x['n']:4d} {x['pnl']:8.2f} {x['pnl_g']:8.2f} {x['per']:7.3f} {x['win']:5.2f} {mps:>6} {x['inS']:4.2f} {x['medsz']:6.2f} {x['land']:6.4f}")
show("by appearances", lambda x: -x["n"], 25)
show("by total net PnL (SOL)", lambda x: -x["pnl"], 25)
show("by PnL per trade (n>=8)", lambda x: -x["per"], 20, lambda x: x["n"] >= 8)
show("worst total PnL", lambda x: x["pnl"], 10)
