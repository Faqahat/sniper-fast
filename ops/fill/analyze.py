import json, math
from collections import defaultdict
OUR_PAYER="FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
VSOL0=30_000_000_000; VTOK0=1_073_000_000_000_000
raw=[json.loads(l) for l in open("/root/fill/rows.jsonl") if l.strip()]
bymint=defaultdict(list)
for r in raw: bymint[r["mint"]].append(r)

# Recompute floor = post-dev marginal; split dev vs co-snipers
co=[]; devs=[]; launch_info=[]
for m,rs in bymint.items():
    rs.sort(key=lambda r:(r["slot"],r["pos"]))
    devlog=rs[0]["dev_log"]
    if devlog>0:
        dev=rs[0]; floor=dev["vsol"]/dev["vtok"]; group=rs[1:]; dev_lam=dev["vsol"]-VSOL0
        dev["fill_mult"]=(dev["sol_in"]/dev["tok_out"])/((dev["vsol"]-dev["sol_in"])/(dev["vtok"]+dev["tok_out"]))
        devs.append(dev)
    else:
        f0=rs[0]; floor=(f0["vsol"]-f0["sol_in"])/(f0["vtok"]+f0["tok_out"]); group=rs; dev_lam=0
    sa=0
    for i,r in enumerate(group):
        r["floor_px"]=floor; r["fill_mult"]=(r["sol_in"]/r["tok_out"])/floor
        r["co_rank"]=i; r["sol_ahead_co"]=sa; r["dev_lam_eff"]=dev_lam
        sa+=r["sol_in"]; co.append(r)
    launch_info.append((m,len(group),dev_lam))

print("launches:",len(bymint),"| co-sniper rows:",len(co),"| dev rows:",len(devs))
nml=sum(1 for _,n,_ in launch_info if n>=2)
print("launches with >=2 co-snipers:",nml)

def pct(xs,p):
    xs=sorted(x for x in xs if x is not None)
    if not xs: return None
    k=(len(xs)-1)*p; f=math.floor(k); c=math.ceil(k)
    return xs[int(k)] if f==c else xs[f]*(c-k)+xs[c]*(k-f)
def summ(n,xs):
    xs=[x for x in xs if x is not None]
    if not xs: print(f"  {n}: (none)"); return
    print(f"  {n}: n={len(xs)} p10={pct(xs,.1):.4g} p50={pct(xs,.5):.4g} p90={pct(xs,.9):.4g} mean={sum(xs)/len(xs):.4g}")

print("\n=== FILL MULTIPLE (vs post-dev floor) ===")
summ("dev fill",[d["fill_mult"] for d in devs])
summ("co-sniper fill ALL",[r["fill_mult"] for r in co])
summ("co-sniper fill SAME-SLOT(sd0)",[r["fill_mult"] for r in co if r["sd"]==0])
summ("co-sniper fill NEXT-SLOT(sd1)",[r["fill_mult"] for r in co if r["sd"]==1])
print("  fill by co_rank:")
br=defaultdict(list)
for r in co: br[r["co_rank"]].append(r["fill_mult"])
for rk in sorted(br)[:8]:
    xs=br[rk]; print(f"    co_rank{rk}: n={len(xs)} p10={pct(xs,.1):.3f} p50={pct(xs,.5):.3f} p90={pct(xs,.9):.3f}")

print("\n=== cu_price / fee usage (co-snipers) ===")
summ("cu_price (micro-lamp)",[r["cu_price"] for r in co])
print(f"  co-snipers with NO cu_price: {sum(1 for r in co if r['cu_price'] is None)/len(co):.1%}")
summ("cu_limit",[r["cu_limit"] for r in co])
summ("prio_fee_lam",[r["prio_fee_lam"] for r in co])
summ("tip_lam (tips>0 only)",[r["tip_lam"] for r in co if r["tip_lam"]>0])
print(f"  co-snipers with a tip: {sum(1 for r in co if r['tip_lam']>0)/len(co):.1%}")

print("\n=== CORRELATION within-slot: does higher X => earlier execution order? ===")
sg=defaultdict(list)
for r in co: sg[(r["mint"],r["slot"])].append(r)
groups=[g for g in sg.values() if len(g)>=2]
print(f"  same-slot co-sniper groups(>=2): {len(groups)}  (0.50=no effect, 1.0=X fully orders, <0.5=inverse)")
def conc(key):
    c=d=t=0
    for g in groups:
        gg=[r for r in g if r.get(key) is not None]
        for i in range(len(gg)):
            for j in range(i+1,len(gg)):
                a,b=gg[i],gg[j]
                if a["pos"]==b["pos"]: continue
                if a[key]==b[key]: t+=1; continue
                earlier=a if a["pos"]<b["pos"] else b
                higher=a if a[key]>b[key] else b
                if earlier is higher: c+=1
                else: d+=1
    tot=c+d
    return c,d,t,(c/tot if tot else None)
for key in ["cu_price","cu_limit","prio_fee_lam","tip_lam","sol_in"]:
    c,d,t,f=conc(key)
    print(f"  {key:14s} concordance={('%.3f'%f) if f is not None else 'NA':>6}  concordant={c} discordant={d} tied={t}")

print("\n=== FLOOR-fillers (<=1.05) vs LATE (>=1.15) co-snipers ===")
fl=[r for r in co if r["fill_mult"]<=1.05]; la=[r for r in co if r["fill_mult"]>=1.15]
print(f"  n floor<=1.05: {len(fl)}   late>=1.15: {len(la)}")
summ("  floor cu_price",[r["cu_price"] for r in fl]); summ("  late  cu_price",[r["cu_price"] for r in la])
print(f"  floor: NO cu_price {sum(1 for r in fl if r['cu_price'] is None)/max(1,len(fl)):.0%} | late: NO cu_price {sum(1 for r in la if r['cu_price'] is None)/max(1,len(la)):.0%}")
summ("  floor sol_ahead_co(SOL)",[r["sol_ahead_co"]/1e9 for r in fl]); summ("  late sol_ahead_co(SOL)",[r["sol_ahead_co"]/1e9 for r in la])
summ("  floor sol_in(SOL)",[r["sol_in"]/1e9 for r in fl]); summ("  late sol_in(SOL)",[r["sol_in"]/1e9 for r in la])
summ("  floor co_rank",[r["co_rank"] for r in fl]); summ("  late co_rank",[r["co_rank"] for r in la])
summ("  floor tip_lam",[r["tip_lam"] for r in fl]); summ("  late tip_lam",[r["tip_lam"] for r in la])
def lc(rs):
    d=defaultdict(int)
    for r in rs: d[r["tip_labels"] or "(none)"]+=1
    return dict(sorted(d.items(),key=lambda x:-x[1]))
print("  floor tip labels:",lc(fl)); print("  late  tip labels:",lc(la))

print("\n=== EARLIEST co-sniper (co_rank0) ===")
r0=[g[0] for g in sg.values()]  # per (mint,slot) earliest; use per-launch below
# per launch earliest co-sniper
e0=[rs[1] if rs[0]["dev_log"]>0 and len(rs)>=2 else (rs[0] if rs[0]["dev_log"]==0 else None) for rs in [sorted(v,key=lambda r:(r["slot"],r["pos"])) for v in bymint.values()]]
e0=[r for r in co if r["co_rank"]==0]
summ("  co_rank0 fill",[r["fill_mult"] for r in e0])
summ("  co_rank0 cu_price",[r["cu_price"] for r in e0])
summ("  co_rank0 sol_in(SOL)",[r["sol_in"]/1e9 for r in e0])
summ("  co_rank0 tip_lam",[r["tip_lam"] for r in e0])
print("  co_rank0 tip labels:",lc(e0))
print(f"  co_rank0 with NO cu_price: {sum(1 for r in e0 if r['cu_price'] is None)/len(e0):.0%}")

print("\n=== sol_ahead_co -> fill (curve mechanics) ===")
bk=defaultdict(list)
for r in co:
    sa=r["sol_ahead_co"]/1e9
    b="0-0.5" if sa<.5 else "0.5-1" if sa<1 else "1-2" if sa<2 else "2-4" if sa<4 else "4-8" if sa<8 else "8+"
    bk[b].append(r["fill_mult"])
for b in ["0-0.5","0.5-1","1-2","2-4","4-8","8+"]:
    if bk[b]: print(f"  sol_ahead {b}: n={len(bk[b])} p50_fill={pct(bk[b],.5):.3f}")

print("\n=== cu_price tiers -> order & fill (co-snipers, same-slot) ===")
def tier(cp):
    if cp is None: return "none"
    if cp<100_000: return "<0.1M"
    if cp<500_000: return "0.1-0.5M"
    if cp<1_500_000: return "0.5-1.5M"
    if cp<4_000_000: return "1.5-4M"
    return ">=4M"
tg=defaultdict(list)
for r in co: tg[tier(r["cu_price"])].append(r)
for t in ["none","<0.1M","0.1-0.5M","0.5-1.5M","1.5-4M",">=4M"]:
    rs=tg[t]
    if rs: print(f"  {t:9s}: n={len(rs)} p50_fill={pct([x['fill_mult'] for x in rs],.5):.3f} p50_corank={pct([x['co_rank'] for x in rs],.5):.1f} p50_tip={pct([x['tip_lam'] for x in rs],.5)/1e9:.5f}")

print("\n=== OUR payer / 5M cu_price ===")
ours=[r for r in raw if r["fee_payer"]==OUR_PAYER]
print("  rows by OUR payer FRZh..:",len(ours))
for r in ours[:15]: print("   ",r["mint"][:8],"corank?",r.get("co_rank"),"fill=%.3f"%r.get("fill_mult",0),"cu_price",r["cu_price"],"tip",r["tip_lam"])
n5=[r for r in co if r["cu_price"] and 4e6<=r["cu_price"]<=6e6]
print("  co-snipers cu_price 4-6M:",len(n5))
summ("   their fill",[r["fill_mult"] for r in n5]); summ("   their co_rank",[r["co_rank"] for r in n5])
