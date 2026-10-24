#!/usr/bin/env python3
# per-fire head-to-head reconstruction (read-only). Writes work/fires_h2h.json and prints a compact table.
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/agents/headtohead/work")
from race import *
R = json.load(open(W + "/runs.json"))
E = load_ext()
# tape rx times from run records (sig -> rx ns), per run
TAPE = {}
for r in range(1, 6):
    for l in open(f"/home/moiz/sniper/ops/dip/speed/dip_r{r}.jsonl"):
        d = json.loads(l)
        if d["ev"] == "tape": TAPE.setdefault(d["sig"], d["t"])
def kind(r, mint):
    trs = [t for t in r["tr"] if t["mint"] == mint]
    if not r["ec"]:
        if any(t["buy"] for t in trs) and not any(not t["buy"] for t in trs): return "BUY"
        if any(not t["buy"] for t in trs) and not any(t["buy"] for t in trs): return "SELL"
        if trs: return "MIX"
        return "OTHER"
    ix = r.get("ixn") or []
    if any("Buy" in x for x in ix):
        code = r["ec"].split(":")[-1]
        return "BUYFAIL_SLIP" if code in ("6002", "6042") else "BUYFAIL_" + code
    if any("Sell" in x for x in ix): return "SELLFAIL"
    return "EARLYFAIL"
def txinfo(r):
    prio = (r["cup"] or 0) * (r["cul"] or 200000) // 10**6
    return dict(sig=r["sig"], payer=r["signers"][0], nsig=len(r["signers"]), s=r["s"], i=r["i"], ec=r["ec"], cup=r["cup"], cul=r["cul"], cu=r["cu"],
                fee=r["fee"], prio=prio, tips=[[relay(a), v] for a, v in r["tips"]], tip=sum(v for _, v in r["tips"]),
                ixn=r.get("ixn") or [], progs=pshort(r["progs"]))
out = []
for f in R["fires"]:
    txs = E.get(f["mint"], [])
    me = next((r for r in txs if r["sig"] == f["buy_sig"]), None)
    sol_in = me["tr"][0]["sol"] if me and me["tr"] else int(f["spend"] / 1.0125)
    rc = race(txs, f["dump_sig"], sol_in, f["min_out"], horizon=5)
    if rc is None: print("NO RACE", f["mint"]); continue
    S = rc["S"]; t0 = f["t_dump_rx"]
    seq = []
    for k, row in enumerate(rc["rows"]):
        r = row["r"]; kd = kind(r, rc["mint"])
        x = txinfo(r); x.update(kind=kd, ds=r["s"] - S, pm=round(row["pmult"], 4), post_ok=row["post_ok"], pre_ok=row["pre_ok"], us=r["sig"] == f["buy_sig"],
                              sol=sum(t["sol"] for t in row["trs"]) if row["trs"] else 0,
                              rx_ms=(TAPE[r["sig"]] - t0) / 1e6 if r["sig"] in TAPE and t0 else None)
        seq.append(x)
    cross = rc["crossed"]
    usk = next((k for k, x in enumerate(seq) if x["us"]), None)
    o = dict(f=f, S=S, iD=rc["iD"], dump_payer=rc["D"]["signers"][0], dump_sol=sum(t["sol"] for t in rc["D"]["tr"] if not t["buy"]),
             cross=cross, usk=usk, seq=seq, sol_in=sol_in)
    out.append(o)
json.dump(out, open(W + "/fires_h2h.json", "w"))
# compact table
print("run mint     res      cl                 S%4  iD  | US: ds/idx   ec        rx   | CROSS: ds/idx  payer    rx    | buysBeforeUs okBuysBeforeCross")
for o in out:
    f = o["f"]; seq = o["seq"]; us = seq[o["usk"]] if o["usk"] is not None else None; cr = seq[o["cross"]] if o["cross"] is not None else None
    nb_before_us = sum(1 for x in seq[:o["usk"] or 0] if x["kind"] == "BUY")
    nb_before_cross = sum(1 for x in seq[:(o["cross"] + 1) if o["cross"] is not None else len(seq)] if x["kind"] == "BUY")
    print("%d %s %-10s %-18s %d %4d | %+d/%4s %-9s %6s | %s | %d %d" % (
        f["run"], f["mint"][:8], f["result"], f["client"] or "?", S % 4, o["iD"],
        us["ds"] if us else 9, us["i"] if us else "-", (us["ec"] or "ok") if us else "-", "%.1f" % us["rx_ms"] if us and us["rx_ms"] is not None else "-",
        ("%+d/%4d %s %s" % (cr["ds"], cr["i"], cr["payer"][:8], "%.1f" % cr["rx_ms"] if cr["rx_ms"] is not None else "-")) if cr else "never",
        nb_before_us, nb_before_cross))
