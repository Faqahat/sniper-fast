#!/usr/bin/env python3
"""WHALEFLIP step 6 [MEASURED counts, INFERRED sizes]: what the check would cost per day at our real try rates.
Per run: T2 tries sent / landed (presend_attempt_land res != unseen), their tx bytes and CU limit (presend_attempt), the live hours.
Two-variant Lighthouse = every T2 try sent twice (amount <= X | account closed): every landed extra copy that does not fill pays 5,120.
Also the share of the trigger whale's own dumps that CLOSE its token account (exact, w4: tape CloseAccount + balance 0).
usage: w6_costs.py"""
import sys, json, pickle, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/whaleflip")
import wlib as W
R = "/home/moiz/sniper-data/filters3/runs/r{}.presend.jsonl"
SRC = {47: "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r47.jsonl", 48: "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/grp/r48.jsonl"}
F = W.load(); h, hp, P = W.hours(F)
out = {}
for r in range(39, 49):
    c = collections.Counter(); by = collections.Counter(); kinds = {}
    for l in open(SRC.get(r, R.format(r)), "rb"):
        if b'"ev":"presend_attempt' not in l: continue
        d = json.loads(l)
        k = d.get("kind") or "t2"
        if d["ev"] == "presend_attempt":
            c[(k, "sent")] += 1; by[d.get("bytes")] += 1
        elif d["ev"] == "presend_attempt_land":
            c[(k, "landed" if d.get("res") != "unseen" else "unseen")] += 1
            c[(k, d.get("res"))] += 1
    hrs = sum(v for s, v in h.items() if s.startswith(f"r{r}"))
    out[r] = {"hours": round(hrs, 2), "t2_sent": c[("t2", "sent")], "t2_landed": c[("t2", "landed")], "t2_ok": c[("t2", "ok")], "rearm_landed": c[("rearm", "landed")],
              "bytes": by.most_common(3)}
    out[r]["t2_landed_per_day"] = round(c[("t2", "landed")] / hrs * 24) if hrs else None
    out[r]["two_variant_extra_sol_day"] = round((c[("t2", "landed")] - c[("t2", "ok")]) / hrs * 24 * 5120 / 1e9 + c[("t2", "ok")] / hrs * 24 * 5120 / 1e9, 3) if hrs else None
    print(f"r{r}", out[r], flush=True)
X = json.load(open(f"{W.D}/exact.json"))
fl = [x for x in X if x["kind"] == "t2" and x["covered"] and x.get("xlab") == "FLIP"]
cl = sum(1 for x in fl if x.get("wh_closed"))
print(f"whale's own-dump fills (exact, covered): {len(fl)}, whale's account CLOSED at our landing {cl} ({cl / max(1, len(fl)):.0%})")
for per in ("DEV", "VAL", "HOLD"):
    z = [x for x in fl if x["period"] == per]; print(f"  {per}: {sum(1 for x in z if x.get('wh_closed'))}/{len(z)} closed, their P&L {sum(x['pnl'] for x in z if x.get('wh_closed')):+.3f}")
out["flip_closed"] = {"n_flip": len(fl), "closed": cl}
json.dump(out, open(f"{W.D}/costs.json", "w"), indent=1)
