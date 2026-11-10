import json, collections
D="/home/it/sniper-data/filters3/ten/"
wide=json.load(open(D+"wide.json")); H=json.load(open(D+"hours.json")); gap={tuple(k.split("|")):v for k,v in json.load(open(D+"gap.json")).items()}
trig=json.load(open(D+"trig.json"))
hrs={"DEV":H["DEV:r41"]+H["DEV:r42"],"VAL":H["VAL:r42"]}
print("wide hours",hrs)
def summ(rs,h):
    if not rs: return "n 0"
    c=sorted([r for r in rs],reverse=True)
    return f"n {len(c):4d} cal {sum(c)/h*24:+6.2f}/day w/o top5 {sum(c[5:])/h*24:+6.2f} win {sum(1 for x in c if x>0)/len(c):.0%} {1000*sum(c)/len(c):+5.1f} mSOL/fill"
def band(x,cuts):
    for c in cuts:
        if x<c: return f"<{c}"
    return f">={cuts[-1]}"
for name,keyf in (("all",lambda w:"all"),("pct",lambda w:band(w["pct"],[4,5,6])),("age",lambda w:band(w["age"],[2,5,10,20,50,150])),("sol",lambda w:band(w["sol"],[1,1.5,2,3,5])),("vsol",lambda w:band(w["vsol"],[35,40,45,60])),("hour",lambda w:f"{w['hour']//4*4:02d}")):
    print("##",name)
    for sg in ("DEV","VAL"):
        g=collections.defaultdict(list); gp=collections.defaultdict(list)
        for w in wide:
            if w["seg"]!=sg or w["paper"] is None: continue
            g[keyf(w)].append(w["paper"]+gap[(sg,w["run"])]); gp[keyf(w)].append(w["paper"])
        for k in sorted(g): print(f"  {sg} {k:>6s} {summ(g[k],hrs[sg])}  (paper {sum(gp[k])/hrs[sg]*24:+.2f})")
# compare: main shadow at 6%+ in same hours with same calibration, age>=2
print("## main shadow (6%+) same runs, age>=2, calibrated")
for sg in ("DEV","VAL"):
    rs=[x["paper"]+gap[(sg,x["run"])] for x in trig if x["seg"]==sg and x["run"] in ("r41","r42") and x["paper"] is not None and x["age"]>=2]
    print(" ",sg,summ(rs,hrs[sg]))
