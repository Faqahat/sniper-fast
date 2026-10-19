import json,math,random
from collections import Counter,defaultdict
random.seed(1)
F=json.load(open("/root/sep2/features2.json"))
rows=sorted(F.values(),key=lambda r:r["slot"])
# ---- merge trajectory from paths ----
paths={}
for ln in open("/root/arbx-fast/paths_blacklist.jsonl"):
    try: j=json.loads(ln)
    except: continue
    paths[j["mint"]]=j.get("path") or []
def traj(mint):
    p=paths.get(mint)
    if not p or len(p)<2: return {}
    t0=p[0][0]; first=p[0][1]
    def rat(cut):
        v=first
        for t,r in p:
            if t-t0<=cut: v=r
            else: break
        return v
    r1=rat(1000); r2=rat(2000)
    seg=[r for t,r in p if t-t0<=2000]
    mn=min(seg) if seg else first; mx=max(seg) if seg else first
    return {"first_r":first,"r_1s":r1,"r_2s":r2,"slope_2s":(r2-first),"min_r_2s":mn,"max_r_2s":mx,
            "dip_2s":(mn<first-1e-9),"ddip_frac":(first-mn)/first if first else 0,"n_ticks":len(p)}
# ---- cluster counts ----
cc=Counter(r.get("creator") for r in rows if r.get("creator"))
fc=Counter(r.get("funder") for r in rows if r.get("funder"))
for r in rows:
    r.update(traj(r["mint"]))
    r["creator_mint_count"]=cc.get(r.get("creator"),0)
    r["funder_mint_count"]=fc.get(r.get("funder"),0)
    r["serial_creator"]=cc.get(r.get("creator"),0)>=2
    r["serial_funder"]=fc.get(r.get("funder"),0)>=2
    r["has_funder"]=bool(r.get("funder"))
    d=r["dev"]
    r["dev_round_1"]=(d%1_000_000_000==0); r["dev_round_01"]=(d%100_000_000==0)
    r["tot_slot_sol"]=r["dev_sol"]+(r.get("sol_cobuy_slot01") or 0)
    r["cobuy_to_dev"]=(r.get("sol_cobuy_slot01") or 0)/r["dev_sol"] if r["dev_sol"]>0 else 0

WIN=[r for r in rows if r["label"]=="WIN"]; LOSE=[r for r in rows if r["label"]=="LOSE"]; MID=[r for r in rows if r["label"]=="MID"]
print("N=%d WIN=%d LOSE=%d MID=%d"%(len(rows),len(WIN),len(LOSE),len(MID)))
WL=[r for r in rows if r["label"] in ("WIN","LOSE")]
baseP=len(WIN)/(len(WIN)+len(LOSE))
print("base WIN-precision=%.3f  base LOSE-rate=%.3f\n"%(baseP,len(LOSE)/len(WL)))

def auc_num(valfn):
    pos=[valfn(r) for r in WIN if valfn(r) is not None]
    neg=[valfn(r) for r in LOSE if valfn(r) is not None]
    if not pos or not neg: return None
    gt=eq=0
    for a in pos:
        for b in neg:
            if a>b: gt+=1
            elif a==b: gt+=0.5
    a=gt/(len(pos)*len(neg))
    return a,len(pos),len(neg)
def perm_p(valfn,obs_auc,nperm=3000):
    vals=[(valfn(r),r["label"]) for r in WL if valfn(r) is not None]
    labs=[l for v,l in vals]; xs=[v for v,l in vals]
    nW=labs.count("WIN")
    import random as _r
    cnt=0; target=abs(obs_auc-0.5)
    for _ in range(nperm):
        _r.shuffle(labs)
        pos=[xs[i] for i in range(len(xs)) if labs[i]=="WIN"]
        neg=[xs[i] for i in range(len(xs)) if labs[i]=="LOSE"]
        gt=0.0
        for a in pos:
            for b in neg:
                if a>b: gt+=1
                elif a==b: gt+=0.5
        au=gt/(len(pos)*len(neg))
        if abs(au-0.5)>=target: cnt+=1
    return (cnt+1)/(nperm+1)

NUM=[("dev_sol",lambda r:r.get("dev_sol")),
 ("n_cobuy_slot0",lambda r:r.get("n_cobuy_slot0")),
 ("n_cobuy_slot01",lambda r:r.get("n_cobuy_slot01")),
 ("n_cobuy_slot1_only",lambda r:r.get("n_cobuy_slot1_only")),
 ("sol_cobuy_slot0",lambda r:r.get("sol_cobuy_slot0")),
 ("sol_cobuy_slot01",lambda r:r.get("sol_cobuy_slot01")),
 ("max_cobuy_slot01",lambda r:r.get("max_cobuy_slot01")),
 ("dev_share_slot01",lambda r:r.get("dev_share_slot01")),
 ("cobuy_to_dev",lambda r:r.get("cobuy_to_dev")),
 ("tot_slot_sol",lambda r:r.get("tot_slot_sol")),
 ("name_len",lambda r:r.get("name_len")),
 ("symbol_len",lambda r:r.get("symbol_len")),
 ("name_wc",lambda r:r.get("name_wc")),
 ("desc_len",lambda r:r.get("desc_len")),
 ("n_meta_fields",lambda r:r.get("n_meta_fields")),
 ("n_socials",lambda r:r.get("n_socials")),
 ("creator_total_sigs",lambda r:r.get("creator_total_sigs")),
 ("creator_prior_before_create",lambda r:r.get("creator_prior_before_create")),
 ("creator_mint_count",lambda r:r.get("creator_mint_count")),
 ("funder_mint_count",lambda r:r.get("funder_mint_count")),
 ("hour_utc",lambda r:r.get("hour_utc")),
 ("first_r",lambda r:r.get("first_r")),
 ("r_1s",lambda r:r.get("r_1s")),
 ("r_2s",lambda r:r.get("r_2s")),
 ("slope_2s",lambda r:r.get("slope_2s")),
 ("min_r_2s",lambda r:r.get("min_r_2s")),
 ("max_r_2s",lambda r:r.get("max_r_2s")),
 ("ddip_frac",lambda r:r.get("ddip_frac")),
 ("launch_order",lambda r:r.get("order")),
]
print("===== UNIVARIATE NUMERIC (AUC, WIN vs LOSE; |AUC-.5| ranks) =====")
res=[]
for nm,fn in NUM:
    a=auc_num(fn)
    if a is None: continue
    au,np_,nn_=a
    res.append((nm,au,fn))
res.sort(key=lambda x:abs(x[1]-0.5),reverse=True)
print("%-28s %6s %8s %6s"%("feature","AUC","dir","perm_p"))
for nm,au,fn in res:
    p=perm_p(fn,au,2500)
    wv=sorted([fn(r) for r in WIN if fn(r) is not None]); lv=sorted([fn(r) for r in LOSE if fn(r) is not None])
    wm=wv[len(wv)//2]; lm=lv[len(lv)//2]
    d="hi=WIN" if au>=.5 else "lo=WIN"
    star="***" if p<0.05 else ("*" if p<0.10 else "")
    print("%-28s %6.3f %8s %6.3f %s  Wmed=%.3g Lmed=%.3g"%(nm,max(au,1-au),d,p,star,wm,lm))

def cat_stat(name,keyfn):
    g=defaultdict(lambda:[0,0,0])
    for r in rows:
        k=keyfn(r); idx={"WIN":0,"LOSE":1,"MID":2}[r["label"]]; g[k][idx]+=1
    print("\n[%s]"%name)
    for k in sorted(g,key=lambda x:str(x)):
        w,l,m=g[k]; prec=w/(w+l) if (w+l) else float("nan")
        lift=(prec/baseP) if (w+l) else float("nan")
        print("   %-20s n=%2d W=%2d L=%2d M=%2d  winP=%.2f lift=%.2f"%(str(k),w+l+m,w,l,m,prec,lift))
print("\n===== CATEGORICAL / BINARY =====")
for nm,kf in [("whale_slot01",lambda r:r.get("whale_slot01")),
 ("serial_creator",lambda r:r.get("serial_creator")),
 ("serial_funder",lambda r:r.get("serial_funder")),
 ("has_funder",lambda r:r.get("has_funder")),
 ("vanilla",lambda r:r.get("vanilla")),
 ("dev_round_1(N.0)",lambda r:r.get("dev_round_1")),
 ("name_lower",lambda r:r.get("name_lower")),
 ("name_upper",lambda r:r.get("name_upper")),
 ("name_title",lambda r:r.get("name_title")),
 ("symbol_upper",lambda r:r.get("symbol_upper")),
 ("name_has_space",lambda r:r.get("name_has_space")),
 ("name_has_emoji",lambda r:r.get("name_has_emoji")),
 ("name_has_digit",lambda r:r.get("name_has_digit")),
 ("name_eq_symbol",lambda r:r.get("name_eq_symbol")),
 ("has_image",lambda r:r.get("has_image")),
 ("has_twitter",lambda r:r.get("has_twitter")),
 ("has_website",lambda r:r.get("has_website")),
 ("uri_host",lambda r:r.get("uri_host")),
 ("cid_style",lambda r:r.get("cid_style")),
 ("dip_2s",lambda r:r.get("dip_2s")),
 ("create_disc",lambda r:r.get("create_disc")),
 ]:
    cat_stat(nm,kf)

# repeated/spam name
print("\n===== repeated NAME across launches =====")
nn=Counter((r.get("name") or "").strip().lower() for r in rows if r.get("name"))
dups={k:v for k,v in nn.items() if v>=2}
print("dup names:",dups)
for k in dups:
    sub=[r for r in rows if (r.get("name") or "").strip().lower()==k]
    print("   %-18s -> %s"%(k,Counter(r["label"] for r in sub)))
json.dump(rows,open("/root/sep2/rows_enriched.json","w"))
