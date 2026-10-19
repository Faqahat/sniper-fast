import rpc, json
E={x["mint"]:x for x in json.load(open("/root/last30/enriched.json"))}
m=[k for k in E if k.startswith("B9XWvC")][0]
x=E[m]
buy_slot=x["buy_slot"]; hi=min((x.get("last_sell_slot") or buy_slot+200),buy_slot+400)
curve=x["curve"]
print("mint",m[:8],"buy_slot",buy_slot,"hi",hi,"curve",curve[:8],"last_sell",x.get("last_sell_slot"))
def walk(addr,label):
    before=None; total=0; win=0; pages=0; slots=[]
    while pages<40:
        o={"limit":1000}
        if before: o["before"]=before
        page=rpc.call("getSignaturesForAddress",[addr,o])
        if not page: break
        total+=len(page); pages+=1
        for s in page:
            sl=s.get("slot")
            if sl is not None and buy_slot<=sl<=hi: win+=1; slots.append(sl)
        if len(page)<1000: break
        before=page[-1]["signature"]
    print(f"{label}: total {total} pages {pages} inwindow {win} slotrange {min(slots) if slots else None}..{max(slots) if slots else None}")
walk(m,"MINT")
walk(curve,"CURVE")
