#!/usr/bin/env python3
"""SL-REDFLAGS s2: flat feature rows for every LIVE position r37..r49 (signing-time features via TAIL tfeat.feats + arm fields;
outcome fields prefixed o_ are AFTER the fact, labels only). out: /home/moiz/sniper-data/filters3/slflags/rows.jsonl"""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/tail")
from tfeat import feats, outcome
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
SPLIT = 1793516400000000000  # 11-01 12:00 PKT
TD = "/home/moiz/sniper-data/filters3/tail"; MD = "/home/moiz/sniper-data/filters3/slflags"
src = [(r, f"{TD}/pos_r{r}.jsonl") for r in range(37, 43)] + [(r, f"{MD}/pos_r{r}.jsonl") for r in range(43, 50)]
out = open(f"{MD}/rows.jsonl", "w")
for r, p in src:
    for l in open(p):
        d = json.loads(l)
        F = feats(d)
        F.pop("holders", None) if False else None
        a = d.get("arm") or {}; f = d["fill"]; c = d.get("close") or {}
        q = a.get("quiet") or {}; v2 = a.get("v2") or {}; f3 = a.get("f3") or {}; tr = a.get("trig") or {}; du = a.get("dump") or {}
        F.update(run=r, t=d["t"], mint=d["mint"], w=d["w"], pnl=d["pnl"], exit=c.get("exit_why"),
                 set=("DEV" if r < 42 or (r == 42 and d["t"] < SPLIT) else ("VAL42" if r == 42 else "VAL")),
                 n120=v2.get("n_120s"), hi120=v2.get("at_120s_high"), ring=v2.get("ring_s"),
                 qrule=q.get("rule_on"), qall4=q.get("all4"), fb_n=q.get("fb_n"),
                 f3=f3 or None, trig_sol=(tr.get("sol") or du.get("sol") or 0) / 1e9,
                 trig_vsol=(tr.get("vsol") or du.get("vsol") or 0) / 1e9,
                 sat=f.get("slots_after_trigger"), spend=a.get("spend"), rholders=a.get("holders"),
                 lim_ratio=(f.get("lim") / f.get("p_sign")) if f.get("lim") and f.get("p_sign") else None,
                 p_rel=((d.get("land") or {}).get("d") or {}).get("p_rel"),
                 n_between=(d.get("land") or {}).get("n_between"))
        at = d.get("att") or {}; T0 = tr if tr.get("vsol") else du
        F["rise"] = ((at["vsol"] / at["vtok"]) / (T0["vsol"] / T0["vtok"]) - 1) if (at.get("vsol") and at.get("vtok") and T0.get("vsol") and T0.get("vtok")) else None
        F["dv_sign"] = ((at.get("vsol") or 0) - (T0.get("vsol") or 0)) / 1e9 if at.get("vsol") and T0.get("vsol") else None
        wa = F.get("whale")
        wh = [h for h in (f.get("ann") or {}).get("holders") or [] if wa and h["w"] == wa]
        F["wh_p50"] = wh[0].get("p50") if wh else None; F["wh_h3"] = wh[0].get("h3") if wh else None
        F["wh_hz3"] = wh[0].get("hz3") if wh else None; F["wh_risk"] = wh[0].get("risk") if wh else None; F["wh_age"] = wh[0].get("age") if wh else None
        s, b = outcome(d, OURS)
        hl = {h["w"] for h in (f.get("ann") or {}).get("holders") or []}
        F["o_sells"] = sorted([[u, round(v, 3), u in hl] for u, v in s.items()], key=lambda x: -x[1])[:6]
        F["o_sold"] = sum(s.values()); F["o_bought"] = sum(b.values()); F["o_nbuy"] = len(b)
        F["o_held"] = c.get("held_s")
        F["l_holders"] = [[h["w"], round(h["pct"], 2), h["age"], h.get("n")] for h in (f.get("ann") or {}).get("holders") or []]
        out.write(json.dumps(F, default=str) + "\n")
out.close()
