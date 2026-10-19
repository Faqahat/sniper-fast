import json, statistics as st, datetime as dt

E=json.load(open("/root/last30/enriched.json"))
F={x["mint"]:x for x in json.load(open("/root/last30/fill2.json"))}
# order by slot desc (most recent first)
E=[x for x in E if not x.get("error")]
E.sort(key=lambda x:-x["buy_slot"])

def g(x,*ks,default=None):
    cur=x
    for k in ks:
        if cur is None: return default
        cur=cur.get(k) if isinstance(cur,dict) else default
    return cur if cur is not None else default

rows=[]
for x in E:
    m=x["mint"]; f=F.get(m,{})
    cf_=x.get("create_features") or {}
    rows.append(dict(
        mint=m, slot=x["buy_slot"], bt=x["bt"], delta=x.get("slot_delta"),
        dev_buy=cf_.get("dev_buy_sol"), create_cu=cf_.get("create_cu_price"),
        vanilla=cf_.get("vanilla") if cf_.get("vanilla") is not None else f.get("vanilla"),
        bundled=cf_.get("bundled"), cosnip=cf_.get("cosnipers_create_slot"),
        rank=f.get("his_rank_xslot"), ratio=f.get("fill_ratio_xslot"),
        peak=x.get("peak_mult"), pnl=x.get("pnl_sol"), win=x.get("win"),
        nsell=x.get("n_sells"), fss=x.get("first_sell_slot"), lss=x.get("last_sell_slot"),
        npk=x.get("npk"), nmint=x.get("n_mint_sigs"),
    ))

def med(v):
    v=[a for a in v if a is not None]
    return st.median(v) if v else None
def frac(cond,tot=None):
    c=sum(1 for a in rows if cond(a)); return c
n=len(rows)

print(f"\n=== LAST {n} LANDED TRADES (most recent first) ===")
hdr=f"{'#':>2} {'mint':8} {'slot':>10} {'Δ':>2} {'dev':>5} {'cu':>4} {'van':>3} {'bun':>3} {'cos':>3} {'rnk':>3} {'fill':>5} {'peak':>5} {'nsel':>4} {'pnl':>7} {'W':>1}"
print(hdr)
for i,r in enumerate(rows,1):
    cu="y" if (r['create_cu'] or 0)>0 else "."
    van="y" if r['vanilla'] else ("." if r['vanilla'] is not None else "?")
    bun="y" if r['bundled'] else "."
    print(f"{i:>2} {r['mint'][:8]} {r['slot']:>10} {str(r['delta']):>2} {('%.2f'%r['dev_buy']) if r['dev_buy'] is not None else '  -':>5} {cu:>4} {van:>3} {bun:>3} {str(r['cosnip']):>3} {str(r['rank']):>3} {('%.2f'%r['ratio']) if r['ratio'] else '   -':>5} {('%.2f'%r['peak']) if r['peak'] else '   -':>5} {str(r['nsell']):>4} {('%+.3f'%r['pnl']) if r['pnl'] is not None else '   -':>7} {'W' if r['win'] else 'L':>1}")

wins=[r for r in rows if r['win']]; losers=[r for r in rows if not r['win']]
tot=sum(r['pnl'] for r in rows if r['pnl'] is not None)
print(f"\nwin rate {len(wins)}/{n} = {len(wins)/n:.1%}   total PnL {tot:+.3f} SOL   mean {tot/n:+.4f}/trade")
print(f"BASELINE (his prior 200, exit_study): win 59.5%, mean +0.1915/trade")

print("\n=== FEATURE PREVALENCE ===")
dv=[r['dev_buy'] for r in rows if r['dev_buy'] is not None]
print(f"dev_buy present(decoded): {len(dv)}/{n}; >=0.3: {sum(1 for a in dv if a>=0.3)}; >=0.5: {sum(1 for a in dv if a>=0.5)}; >=1.0: {sum(1 for a in dv if a>=1.0)}; med={med(dv):.3f}" if dv else "dev_buy none")
van=[r['vanilla'] for r in rows if r['vanilla'] is not None]
print(f"vanilla: {sum(1 for a in van if a)}/{len(van)} decoded")
print(f"bundled (jito tip on create/adj): {sum(1 for r in rows if r['bundled'])}/{n}")
print(f"create_cu>0 (dev prio fee): {sum(1 for r in rows if (r['create_cu'] or 0)>0)}/{n}")
cos=[r['cosnip'] for r in rows if r['cosnip'] is not None]
print(f"co-snipers in create slot: med={med(cos)}, ==0: {sum(1 for a in cos if a==0)}/{len(cos)}, >=1: {sum(1 for a in cos if a>=1)}/{len(cos)}")
d0=sum(1 for r in rows if r['delta']==0); d1=sum(1 for r in rows if r['delta']==1)
print(f"slot delta: ==0 {d0}/{n}, ==1 {d1}/{n}, <=1 {d0+d1}/{n}")

print("\n=== FILL QUALITY (cross-slot, vs create floor) ===")
rk=[r['rank'] for r in rows if r['rank'] is not None]
rt=[r['ratio'] for r in rows if r['ratio'] is not None]
print(f"his rank among external buyers: med={med(rk)}, rank1: {sum(1 for a in rk if a==1)}/{len(rk)}, rank<=3: {sum(1 for a in rk if a<=3)}/{len(rk)}")
print(f"fill ratio (his_px/floor_px): med={med(rt):.4f}, p25={st.quantiles(rt,n=4)[0]:.4f}, p75={st.quantiles(rt,n=4)[2]:.4f}, max={max(rt):.3f}" if len(rt)>3 else f"fill ratios: {rt}")
print(f"  ratio<=1.05: {sum(1 for a in rt if a<=1.05)}/{len(rt)};  >1.2: {sum(1 for a in rt if a>1.2)}/{len(rt)}")

print("\n=== REGIME / TIME CLUSTERING ===")
bts=sorted([r['bt'] for r in rows if r['bt']])
span=(max(bts)-min(bts))
print(f"window: {dt.datetime.utcfromtimestamp(min(bts))} .. {dt.datetime.utcfromtimestamp(max(bts))} UTC  ({span/60:.1f} min, {span/3600:.2f} h)")
# inter-trade gaps
sb=sorted(rows,key=lambda r:r['bt'])
gaps=[sb[i+1]['bt']-sb[i]['bt'] for i in range(len(sb)-1)]
print(f"inter-trade gap sec: med={med(gaps):.0f}, max={max(gaps):.0f} -> {'bursty/clustered' if max(gaps)>3*med(gaps) else 'fairly even'}")
# first half vs second half win rate
half=n//2
early=sb[:half]; late=sb[half:]
print(f"early-half win {sum(1 for r in early if r['win'])}/{len(early)}  vs late-half {sum(1 for r in late if r['win'])}/{len(late)}")
pk=[r['peak'] for r in rows if r['peak'] is not None]
print(f"token peak-mult after entry: med={med(pk):.3f}; >=1.5x: {sum(1 for a in pk if a>=1.5)}/{len(pk)}; >=1.2x: {sum(1 for a in pk if a>=1.2)}/{len(pk)}; >=2x: {sum(1 for a in pk if a>=2)}/{len(pk)}; <1.1x: {sum(1 for a in pk if a<1.1)}/{len(pk)}")
# peak reliability: winners whose peak<=1.05 but pnl>0 (window may be unreached)
susp=[r for r in rows if r['win'] and (r['peak'] or 0)<=1.05]
print(f"peak reliability: winners with peak<=1.05 (suspect/thin-pump): {len(susp)} -> "+", ".join(f"{r['mint'][:6]}(pk{r['peak']},npk{r['npk']},nmint{r['nmint']},pnl{r['pnl']:+.2f})" for r in susp))
# win-run clustering
seq=''.join('W' if r['win'] else 'L' for r in sb)
print(f"win/loss sequence (time order): {seq}")

print("\n=== PROFIT CONCENTRATION ===")
srt=sorted(rows,key=lambda r:-(r['pnl'] or 0))
top4=srt[:4]
print(f"total net {tot:+.3f} SOL over {n} trades")
print(f"top-4 PnL trades sum = {sum(r['pnl'] for r in top4):+.3f} ({sum(r['pnl'] for r in top4)/tot:.0%} of net); their peaks = {[r['peak'] for r in top4]}, dev_buy={[round(r['dev_buy'],2) if r['dev_buy'] else None for r in top4]}, fill={[r['ratio'] for r in top4]}")
rest=srt[4:]
print(f"other {len(rest)} trades sum = {sum(r['pnl'] for r in rest):+.3f}")
# peak vs pnl
print(f"trades with peak>=2x: {sum(1 for r in rows if (r['peak'] or 0)>=2)} -> their PnL sum {sum(r['pnl'] for r in rows if (r['peak'] or 0)>=2):+.3f}")
print(f"trades with peak<1.2x: {sum(1 for r in rows if (r['peak'] or 0)<1.2)} -> their PnL sum {sum(r['pnl'] for r in rows if (r['peak'] or 0)<1.2):+.3f}")

print("\n=== DOES ANY PRE-BUY FEATURE SEPARATE WIN FROM LOSS? ===")
def ms(key,fn=lambda r:r):
    wv=[fn(r) for r in wins if fn(r) is not None]; lv=[fn(r) for r in losers if fn(r) is not None]
    return med(wv),med(lv)
for name,fn in [("dev_buy",lambda r:r['dev_buy']),("create_cu>0",lambda r:1 if (r['create_cu'] or 0)>0 else 0),
                ("vanilla",lambda r:1 if r['vanilla'] else 0),("bundled",lambda r:1 if r['bundled'] else 0),
                ("cosnipers",lambda r:r['cosnip']),("his_rank",lambda r:r['rank']),("fill_ratio",lambda r:r['ratio']),
                ("peak_mult",lambda r:r['peak'])]:
    w,l=ms(name,fn)
    print(f"  {name:12s}: winners med={w}  losers med={l}")
fst=[(r['fss']-r['slot']) for r in rows if r['fss']]
holdw=[(r['lss']-r['slot']) for r in wins if r['lss']]
holdl=[(r['lss']-r['slot']) for r in losers if r['lss']]
print(f"first-sell timing (slots after buy): med={med(fst)}")
print(f"n_sells: winners med={med([r['nsell'] for r in wins])}, losers med={med([r['nsell'] for r in losers])}")
print(f"hold to last sell (slots): winners med={med(holdw)}, losers med={med(holdl)}")
print(f"win PnL med={med([r['pnl'] for r in wins]):+.3f}, loser PnL med={med([r['pnl'] for r in losers]):+.3f}")
print(f"exit_study baseline: derisk ~30% at slot+1; winners 2 sells; losers dump whole at slot~10; winner hold p75=31")
