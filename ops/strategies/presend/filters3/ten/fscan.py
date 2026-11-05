import json, collections
D="/home/moiz/sniper-data/filters3/ten/"
pos=json.load(open(D+"pos.json")); H=json.load(open(D+"hours.json"))
def feats(p):
    q=p["q"] or {}; v2=p["v2"] or {}; a=p["ann"] or {}
    return {"wh_fol":q.get("wh_fol"),"wh_dumps":q.get("wh_dumps"),"coh_hold":q.get("coh_hold"),"since_last":q.get("since_last"),"fb_n":q.get("fb_n"),
            "n_tr_60s":v2.get("n_tr_60s"),"n_120s":v2.get("n_120s"),"maxdd":v2.get("maxdd_120s"),"at_high":v2.get("at_120s_high"),"ring_s":v2.get("ring_s"),
            "nb":p["nb"] if p["nb"] is not None else a.get("nb50"),"cr_pct":a.get("cr_pct"),"trig_pct":p["trig_pct"],"trig_sol":p["trig_sol"],"age":p["age"],"vsol":p["trig_vsol"],
            "sat":p["sat"],"rh_max":max(p["rearm_holders"]) if p["rearm_holders"] else None,"dump_drop":p["dump_drop"]}
import statistics
for kind in ("t2","rearm"):
    print("=====",kind)
    P=[p for p in pos if p["kind"]==kind]
    names=feats(P[0]).keys()
    for nm in names:
        vals=[(feats(p)[nm],p) for p in P]
        vals=[(x,p) for x,p in vals if x is not None and not isinstance(x,dict)]
        if len(vals)<50: print(nm,"n",len(vals)); continue
        xs=sorted(float(x) for x,_ in vals)
        qs=[xs[int(len(xs)*f)] for f in (0.25,0.5,0.75)]
        line=f"{nm:10s} q={[round(q,2) for q in qs]} "
        for sg in ("DEV","VAL"):
            bins=collections.defaultdict(list)
            for x,p in vals:
                if p["seg"]!=sg: continue
                b=sum(1 for q in qs if float(x)>q)
                bins[b].append((p["pnl"],p["n_fol10"]))
            line+=f"| {sg} "+" ".join(f"{1000*sum(a for a,_ in bins[b])/max(1,len(bins[b])):+5.1f}({len(bins[b])},{statistics.mean([f for _,f in bins[b]]) if bins[b] else 0:.1f})" for b in range(4))
        print(line)
