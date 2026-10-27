#!/usr/bin/env python3
# DF7eRXHn study: buys with no curve sell = tokens that graduated; the exit is a PumpSwap (pAMM) sell paid in WSOL.
# Reads those sells via read-only getTransaction and adds WSOL proceeds -> amm_exits.json
import sys, json
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
from rpc_ro import get_tx
D = "/home/moiz/sniper-data/landing2/df7e"; W = "DF7eRXHnvRQ9QeVCrdfS56a7RpBD6se6mgPvzApHPNr9"; WSOL = "So11111111111111111111111111111111111111112"
R = json.load(open(f"{D}/buys2.json")); SD = json.load(open(f"{D}/raw_sd.json"))
bym = {}
for sig, v in SD.items():
    if v["mints"]: bym.setdefault(v["mints"][0], []).append((v["s"], v["i"], sig, v))
out = []
for x in R:
    if not x["ok"] or x.get("sell_sigs"): continue
    later = [t for t in sorted(bym.get(x["mint"], []), key=lambda t: (t[0], t[1])) if (t[0], t[1]) > (x["s"], x["i"]) and t[3]["err"] is None
             and any(a.startswith("Sell") for a in t[3]["ixn"])]
    if not later: out.append(dict(sig=x["sig"], exit=None)); continue
    s = later[0][2]; t = get_tx(s)
    m = t["meta"]; pre = {b["accountIndex"]: b for b in m.get("preTokenBalances") or []}; post = {b["accountIndex"]: b for b in m.get("postTokenBalances") or []}
    wsol = 0
    for k in set(pre) | set(post):
        b = post.get(k) or pre.get(k)
        if b["mint"] == WSOL and b.get("owner") == W:
            a = int((post.get(k) or {}).get("uiTokenAmount", {}).get("amount", 0)); z = int((pre.get(k) or {}).get("uiTokenAmount", {}).get("amount", 0)); wsol += a - z
    progs = [l for l in m.get("logMessages") or [] if "invoke [1]" in l]
    out.append(dict(sig=x["sig"], exit=s, slot=t["slot"], hold_slots=t["slot"] - x["s"], d_native=SD[s]["d"], wsol=wsol, net=x["d_buy"] + SD[s]["d"] + wsol,
                    progs=[p.split()[1][:8] for p in progs]))
json.dump(out, open(f"{D}/amm_exits.json", "w"), indent=0)
for o in out: print(o)
print("sum net", sum(o.get("net", 0) or 0 for o in out) / 1e9)
