import json
K=30e9*1.073e15
def fp(dev): return (30e9+dev)**2/K
# mint -> trade metadata parsed from /root/arbx-fast/live_bl_exit.log
T={
"2pQgSF6QZ9zfxDDEvbKHauUbk6Sh5nZs2KV4CMfqpump":dict(dev=1.00e9,entry=3.890662e-5,land=458197062,cost=11384840,real=-18925919,derisk_r=0.998,ride_r=1.007,ride_slot=458197243,armed=False),
"GzYCJrGDJzBj5Um8xzTqNPE5ViR9x5XJXmjW7Qrapump":dict(dev=3.00e9,entry=3.905973e-5,land=458197128,cost=11331093,real=-13374923,derisk_r=0.988,ride_r=0.826,ride_slot=458197308,armed=False),
"DT3XpNHrMNXFp21DZj6PrcZG6HFopiLEdWTV3odPpump":dict(dev=4.94e9,entry=1.383511e-4,land=458197141,cost=10500961,real=-391175,derisk_r=0.992,ride_r=0.670,ride_slot=458197323,armed=False),
"3vYr2zKAoSjHtpC5WXTEwKiWyJpTBpBcsSXwg4Pppump":dict(dev=1.00e9,entry=4.379290e-5,land=458197278,cost=11384840,real=613403,derisk_r=0.988,ride_r=1.259,ride_slot=458197287,armed=True),
"3jh3EVr6FMdCX5xxQq9rh9HXYHhRoayCVZFeHtoTpump":dict(dev=1.00e9,entry=3.949740e-5,land=458197565,cost=11384840,real=-2767036,derisk_r=1.000,ride_r=0.780,ride_slot=458197748,armed=False),
"CsSqMZxjR4Z8n9VxTV3shmptSekqaiwp2ySrSJaFR9jn":dict(dev=2.00e9,entry=5.432900e-5,land=458197817,cost=11384840,real=-9827770,derisk_r=0.988,ride_r=0.978,ride_slot=458197997,armed=False),
"6Txr19fyrDJ5TH1ph9NB8QtCafLrcGYd6waUJLdqpump":dict(dev=1.00e9,entry=4.946705e-5,land=458197934,cost=11384840,real=410948,derisk_r=0.988,ride_r=0.703,ride_slot=458198120,armed=False),
"FV7Z7H7QaR4ZgfCWe3mKoZgEkoLEkdFmTCzy5jy6pump":dict(dev=1.00e9,entry=3.940693e-5,land=458198078,cost=11384840,real=3032119,derisk_r=1.033,ride_r=1.132,ride_slot=458198188,armed=True),
"JE9LHzWe2ovReNuxPBfxvfAci18gr54nRpcsGLG6pump":dict(dev=1.00e9,entry=4.812195e-5,land=458198896,cost=11384840,real=-625287,derisk_r=0.990,ride_r=1.028,ride_slot=458198928,armed=True),
}
SHORT={k:k[:4] for k in T}
cache=json.load(open("/root/exitfix/series_cache.json"))

def build(mint,m):
    pts=cache.get(mint,[])
    pts=[p for p in pts if p[1]]
    if len(pts)<3: return None
    pts=sorted(pts,key=lambda x:x[0])
    f=fp(m["dev"]); create_bt=min(p[1] for p in pts)
    ent=None
    for i,(sl,bt,lam) in enumerate(pts):
        if sl>=m["land"]: ent=i; break
    if ent is None: ent=len(pts)-1
    lam_land=pts[ent][2]
    # anchor base so mid price at our land == our logged fill (robust to incomplete-dump sampling)
    base=lam_land+30e9-(m["entry"]*K)**0.5
    series=[]
    for sl,bt,lam in pts:
        vsol=lam-base+30e9
        if vsol<0: vsol=0.0
        series.append((sl,bt-create_bt,vsol*vsol/K,(vsol*vsol/K)/f))
    return dict(series=series,ent=ent,f=f)

def fwd_of(b):
    series=b["series"]; ent=b["ent"]; ent_ts=series[ent][1]
    return [(ts-ent_ts,pr) for (sl,ts,pr,rf) in series[ent:]]

# ride exit: 0.70 rides; arms at ride_mult; exits at trail*peak, or at cap, or hold-to-frac-of-peak
def ride_r(fwd,er,trail,cap,ride_mult=1.15,fop=None):
    peak=er; armed=False
    for t,pr in fwd:
        if cap is not None and t>cap: return pr/er
        if pr>peak: peak=pr
        if pr>=ride_mult*er: armed=True
        if fop is not None:
            if armed and pr<=fop*peak: return pr/er
        else:
            if armed and pr<=trail*peak: return pr/er
    return (fwd[-1][1]/er) if fwd else 1.0

B={mint:build(mint,m) for mint,m in T.items()}

print("=== PER-TOKEN (anchored to our fill) ===")
print(f"{'tok':4} {'dev':>4} {'entFillFloor':>12} {'ourRideR':>8} {'pkR_entry':>9} {'pkR_floor':>9} {'tpk_entry_s':>11} {'upsideLeft':>10} {'realSOL':>9}")
PT={}
for mint,m in T.items():
    b=B[mint]
    fwd=fwd_of(b)
    pk=max(pr for _,pr in fwd); pki=max(range(len(fwd)),key=lambda i:fwd[i][1])
    tpk=fwd[pki][0]
    pkR_e=pk/m["entry"]; pkR_f=pk/b["f"]
    ups=pkR_e-m["ride_r"]
    PT[mint]=dict(pkR_e=pkR_e,pkR_f=pkR_f,tpk=tpk,ups=ups)
    print(f"{SHORT[mint]:4} {m['dev']/1e9:>4.1f} {m['entry']/b['f']:>12.3f} {m['ride_r']:>8.3f} {pkR_e:>9.3f} {pkR_f:>9.3f} {tpk:>11} {ups:>+10.3f} {m['real']/1e9:>+9.4f}")

print("\n=== EXIT RE-SIM (idealized mid-price; 30% locked @derisk_r + 70% ride) ===")
caps=[40,90,300,None]; trails=[0.95,0.90,0.80,0.70]
grid={}
for cap in caps:
    for tr in trails:
        tot=sum(T[k]['cost']*(0.30*(T[k]['derisk_r']-1)+0.70*(ride_r(fwd_of(B[k]),T[k]['entry'],tr,cap)-1)) for k in T)
        grid[(cap,tr)]=tot
        print(f"cap={str(cap):>4}s trail={tr:.2f}  total={tot/1e9:+.5f} SOL")
print("-- hold-to-fraction-of-peak (no time cap) --")
for fop in [0.95,0.90,0.80,0.70,0.50]:
    tot=sum(T[k]['cost']*(0.30*(T[k]['derisk_r']-1)+0.70*(ride_r(fwd_of(B[k]),T[k]['entry'],None,None,fop=fop)-1)) for k in T)
    print(f"frac_of_peak={fop:.2f}  total={tot/1e9:+.5f} SOL")

# perfect hindsight
tot=sum(T[k]['cost']*(0.30*(T[k]['derisk_r']-1)+0.70*(max(pr for _,pr in fwd_of(B[k]))/T[k]['entry']-1)) for k in T)
print(f"\nPERFECT (70% @ exact forward peak): {tot/1e9:+.5f} SOL")
# our-rule idealized (cap40 trail0.95) is grid[(40,0.95)]
best=max(grid.items(),key=lambda kv:kv[1])
print(f"OUR-RULE idealized (cap40,trail0.95): {grid[(40,0.95)]/1e9:+.5f} SOL")
print(f"BEST realistic grid exit: cap={best[0][0]} trail={best[0][1]} -> {best[1]/1e9:+.5f} SOL")
print(f"ACTUAL engine realized (log): {sum(m['real'] for m in T.values())/1e9:+.5f} SOL")
print(f"-> execution gap (actual - our-rule-idealized): {(sum(m['real'] for m in T.values())-grid[(40,0.95)])/1e9:+.5f} SOL")
