#!/usr/bin/env python3
"""APEX-REALISM step 2: for every live attempt, the chain tape on its mint (collector run_20261103_1245, own build):
create, sim-bundle (contiguous buys after create), our tx (landed trade or failed tx), every other buy in cs..cs+3 with
fee/tips/signer, and who was first non-bundle.  Out: realism/live_tape.json"""
import json, numpy as np
TAB = "/home/moiz/sniper-data/apex2/realism/tab/run_20261103_1245"
PAYER = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
live = json.load(open("/home/moiz/sniper-data/apex2/realism/live.json"))
T = np.load(f"{TAB}/trades.npy"); F = np.load(f"{TAB}/fails.npy"); S = np.load(f"{TAB}/slots.npy")
ids = json.load(open(f"{TAB}/ids.json")); C = json.load(open(f"{TAB}/creates.json")); gid = {k: i for i, k in enumerate(ids)}
sidx = {int(s): k for k, s in enumerate(S["slot"].tolist())}; bsz = S["maxi"].astype(np.float64) + 1
def clock(s, i):
    k = sidx.get(int(s)); b = bsz[k] if k is not None else 700.0
    return int(s) + min(int(i) / b, 0.999999)
pid = gid.get(PAYER, -1); out = []
for a in live:
    m = a["mint"]; c = C.get(m)
    if c is None or m not in gid: print("no tape", a["run"], a["id"], m); continue
    mi = gid[m]; cs, ci = int(c["slot"]), int(c["idx"])
    tr = T[(T["mint"] == mi) & (T["slot"] <= cs + 40)]; tr = tr[np.lexsort((tr["syn"], tr["j"], tr["idx"], tr["slot"]))]
    fl = F[(F["mint"] == mi)]; fl = fl[np.lexsort((fl["idx"], fl["slot"]))]
    ev = []
    for t in tr:
        if t["syn"]: continue
        ev.append(dict(k="t", s=int(t["slot"]) - cs, i=int(t["idx"]), j=int(t["j"]), buy=int(t["buy"]), sol=int(t["sol"]) / 1e9,
                       signer=ids[t["signer"]], user=ids[t["user"]], fee=int(t["txfee"]), tips=int(t["tips"]), cu=int(t["cu"]), ixk=int(t["ixk"]),
                       clk=clock(t["slot"], t["idx"]) - clock(cs, ci)))
    for f in fl:
        ev.append(dict(k="f", s=int(f["slot"]) - cs, i=int(f["idx"]), j=0, buy=1, sol=0, signer=ids[f["signer"]], user=ids[f["signer"]],
                       fee=int(f["txfee"]), tips=int(f["tips"]), cu=int(f["cu"]), ixk=int(f["ixk"]), clk=clock(f["slot"], f["idx"]) - clock(cs, ci)))
    ev.sort(key=lambda e: (e["s"], e["i"], e["j"]))
    # sim bundle rule: trades in create tx, then contiguous (idx last/last+1) buys in create slot
    k = 0; tt = [e for e in ev if e["k"] == "t"]
    while k < len(tt) and tt[k]["s"] == 0 and tt[k]["i"] == ci: tt[k]["role"] = "create"; k += 1
    last = ci
    while k < len(tt) and tt[k]["s"] == 0 and tt[k]["i"] in (last, last + 1) and tt[k]["buy"]: tt[k]["role"] = "bundle"; last = tt[k]["i"]; k += 1
    ours = [e for e in ev if e["signer"] == PAYER]
    for e in ours: e["role"] = "ours"
    o = ours[0] if ours else None
    others = [e for e in tt if "role" not in e and e["buy"] and e["s"] <= 3]
    first = others[0] if others else None
    ahead = [e for e in others if o and (e["s"], e["i"]) < (o["s"], o["i"])]
    out.append(dict(a, cs_tape=cs, ci=ci, bsz=bsz[sidx[cs]] if cs in sidx else None, creator_ev=c.get("creator"), payer_ev=c.get("payer"),
                    create_fee=c.get("txfee"), create_tips=c.get("tips"), nbund=sum(1 for e in tt if e.get("role") == "bundle"),
                    ours_tape=o, first_other=first, ahead=ahead, others=others[:12],
                    fails_before=[e for e in ev if e["k"] == "f" and e["signer"] != PAYER and o and (e["s"], e["i"]) < (o["s"], o["i"])][:10]))
json.dump(out, open("/home/moiz/sniper-data/apex2/realism/live_tape.json", "w"))
print(len(out), "attempts with tape")
for x in out:
    o = x["ours_tape"]; f = x["first_other"]
    print(f'{x["run"]}.{x["id"]:<2} {x["outcome"][:4]} {x["cls"][:4]:4} nb={x["nbund"]} ours={"-" if not o else (o["k"], o["s"], o["i"], round(o["clk"],3))} '
          f'first={"-" if not f else (f["s"], f["i"], round(f["clk"],3), f["signer"][:6], f["fee"], f["tips"], round(f["sol"],2))} ahead={len(x["ahead"])}')
