import sys
sys.path.insert(0, "/home/moiz/sniper/ops/agents/headtohead/work")
from race import *
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
