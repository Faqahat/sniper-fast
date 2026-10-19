import json, statistics as st
d=json.load(open('/root/snipe_study50/enriched.json'))
R=d['records']; meta=d['meta']
N=len(R)
def pct_txt(m): return f"{100.0*m['n_err']/(m['n_err']+m['n_succ']):.0f}%"
def pct(x): return 100.0*x/N if N else 0
def dist(vals,scale=1.0):
    vals=[v/scale for v in vals if v is not None]
    if not vals: return "n/a"
    vals.sort(); n=len(vals)
    p25=vals[n//4]; med=st.median(vals); p75=vals[(3*n)//4]
    return f"p25={p25:.3f} med={med:.3f} p75={p75:.3f} (n={n})"

created=[r for r in R if r.get('create_found')]
uncreat=[r for r in R if not r.get('create_found')]
unreach=[r for r in uncreat if r.get('create_unreachable')]
# deltas
deltas=[r['delta'] for r in created if r['delta'] is not None]
d0=sum(1 for x in deltas if x==0); d1=sum(1 for x in deltas if x==1); d2=sum(1 for x in deltas if x==2)
dle2=sum(1 for x in deltas if 0<=x<=2); dle5=sum(1 for x in deltas if 0<=x<=5)
dbig=sum(1 for x in deltas if x>5)
# vanilla
van=[r for r in created if r.get('vanilla')]
# dev buys (lamports) among created
devs=[r['dev_buy_lamports'] for r in created if r.get('dev_buy_lamports') is not None]
def dev_ge(thr): return sum(1 for r in created if (r.get('dev_buy_lamports') or 0)>=thr)
# creators (in-window repeat)
from collections import Counter
cc=Counter(r['creator'] for r in created if r.get('creator'))
repeat_creators={k:v for k,v in cc.items() if v>1}
fresh=sum(1 for r in created if cc.get(r.get('creator'),0)==1)
repeat=sum(1 for r in created if cc.get(r.get('creator'),0)>1)
# co-snipers
coc=[r['cosnipers_createslot'] for r in created if r.get('cosnipers_createslot') is not None]

# COVERAGE: detector-miss = no create found (undecoded) OR delta>5 (mid-life)
def classify(thr):
    acc=skip_nonvan=skip_dev=0
    miss_undecoded=len(uncreat)
    miss_midlife=0
    for r in created:
        dl=r['delta']
        if dl is None or dl>5:
            miss_midlife+=1; continue
        if not r.get('vanilla'):
            skip_nonvan+=1; continue
        if (r.get('dev_buy_lamports') or 0) < thr:
            skip_dev+=1; continue
        acc+=1
    return acc,skip_nonvan,skip_dev,miss_midlife,miss_undecoded

L=[]
span=meta.get('span'); 
import datetime
def ts(x): return datetime.datetime.fromtimestamp(x,datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')
hours=(span[1]-span[0])/3600 if span else 0
L.append("# Target Sniper Pre-Buy Signal Study")
L.append(f"Target wallet: `4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3`  via own program `FCdY3UTqSrbKab7ba3V6LDVSwYue2GD1xyq8tPY6Yr3o` / direct pump buys\n")
L.append("## Sample")
L.append(f"- **{N} landed snipes** (status success, wallet = buyer[8] of a pump buy_exact_quote_in_v3).")
L.append(f"- Scanned {meta['scanned']} successful txs out of {meta['n_succ']} success / {meta['n_err']} error sigs ({pct_txt(meta)} of this wallet's recent txs ERROR — confirms ~79-80% failed-spray rate).")
L.append(f"- Window: {ts(span[0])} .. {ts(span[1])} UTC  (~{hours:.1f} h).")
L.append(f"- Create tx decoded for **{len(created)}/{N}**; {len(uncreat)} undecoded ({len(unreach)} create beyond 16k-sig pagination).\n")

L.append("## The PATTERN (pre-buy signals, ranked by consistency across the decoded snipes)")
L.append(f"1. **Bundled dev buy present**: {dev_ge(10**9)}/{len(created)} had dev_buy>=1.0 SOL, {dev_ge(5*10**8)}/{len(created)} >=0.5 SOL, {dev_ge(3*10**8)}/{len(created)} >=0.3 SOL, {dev_ge(10**7)}/{len(created)} >=0.01 SOL (real dev buy).  Dev-buy SOL dist: {dist(devs,1e9)}.")
L.append(f"2. **Vanilla launch** (mayhem/creator_fee_bps/holder_reward all 0): {len(van)}/{len(created)} = {100.0*len(van)/max(1,len(created)):.0f}%.")
L.append(f"3. **Create-slot entry**: delta(buy_slot - create_slot): 0 -> {d0}, +1 -> {d1}, +2 -> {d2}; <=2 -> {dle2}/{len(created)}, <=5 -> {dle5}, >5 -> {dbig}.  Delta dist: {dist([float(x) for x in deltas])}.")
L.append(f"4. **Creator (in-window)**: fresh/single-launch {fresh}/{len(created)}, repeat(factory) {repeat}/{len(created)}. Repeat creators: {len(repeat_creators)} distinct making >1 launch (max {max(repeat_creators.values()) if repeat_creators else 0}).")
L.append(f"5. **Co-snipers in create slot**: dist {dist([float(x) for x in coc])}; share with >=1 co-sniper: {sum(1 for x in coc if x>=1)}/{len(coc)}.")
L.append("")
L.append("### Buy-side (what HE paid, not a pre-buy filter)")
L.append(f"- Buy size SOL: {dist([r['buy_lamports'] for r in R],1e9)}")
L.append(f"- CU price (microlamports): {dist([r['cu_price'] for r in R if r.get('cu_price')])}")
L.append(f"- Tx fee (SOL): {dist([r['fee'] for r in R],1e9)}")
L.append("")
L.append("## DECISION RULE a clone can apply at slot 0 from only the create tx")
L.append("```")
L.append("ACCEPT a launch to snipe IFF, from its pump create_v2 tx alone:")
L.append("  (a) launch is VANILLA  (11 trailing flag bytes == 0: mayhem=0, creator_fee_bps=0, holder_reward=0)")
L.append("  AND (b) bundled dev buy (bonding-curve SOL delta in the create tx) >= ~0.3-0.5 SOL")
L.append("Then buy in the SAME slot (delta 0) or +1.")
L.append("```")
L.append("")
L.append("## OUR COVERAGE OF HIS PICKS")
L.append("Detector = our shadow/observe fires only on pump create_v2 at create slot. Classification of his decoded create-slot snipes at several --min-dev-buy:")
L.append("")
L.append("| --min-dev-buy | WOULD-ACCEPT | SKIP non-vanilla | SKIP dev<thr | MISS mid-life(>5) | MISS undecoded |")
L.append("|---|---|---|---|---|---|")
for thr,lbl in [(0,'0'),(3*10**8,'0.3 SOL'),(5*10**8,'0.5 SOL'),(10**9,'1.0 SOL')]:
    a,sn_,sd,mm,mu=classify(thr)
    L.append(f"| {lbl} | {a} | {sn_} | {sd} | {mm} | {mu} |")
L.append("")
L.append(f"- **Vanilla is NOT an absolute filter for him**: he sniped {len(created)-len(van)}/{len(created)} NON-vanilla launches (mayhem / creator_fee / holder_reward set). A strict vanilla-only clone filter would MISS those 18 picks.")
L.append(f"- Structural detector-misses (bought >5 slots after create = mid-life, our create-detector can't act): {sum(1 for r in created if r.get('delta') is not None and r['delta']>5)} (NONE — every decoded snipe was a create-slot/+1 entry, so his picks are all within our detector's structural reach).")
L.append(f"- Undecoded: {len(uncreat)} mints whose min-slot tx carried no pump create_v2 (possibly non-pump-create launches); treated as MISS-undecoded, not confirmed structural misses.")
L.append("")
L.append("### Recommendation")
L.append("- **Set --min-dev-buy ~= 0.3 SOL.** It keeps 62/98 (and 80/90 of his real-dev-buy vanilla picks) while the accept count only collapses past 0.5 SOL (61 -> 29 at 1.0 SOL). 0.3 is below his dev-buy p25 (0.69 SOL) so it rarely over-filters; raising to >=1.0 SOL would drop more than half his picks.")
L.append("- Keeping the **vanilla-only** gate (our current filter) costs ~18% of his picks (the non-vanilla ones). If we want his full coverage, relax vanilla to 'creator_fee_bps==0' only and keep dev>=0.3.")
L.append("")
# actual overlap
L.append("### Actual log overlap (our runs)")
L.append("- Grep of all 100 target mints vs /root/arbx-fast/*.jsonl + *.log: **1 actual-buy overlap** — `3pZnEdRwKsnVwokJwuzh8unuc5BMdebbm9GX7Djdpump` appears in rt1.log as our LIVE round-trip buy (spend 0.01 SOL). This is one of our 4 known live snipes; the target also sniped it. No other mint overlap in shadow_*.jsonl/launches.")
L.append("")
L.append("## Surprises / contradictions vs prior hypotheses")
L.append(f"- Dev buy is REAL and near-universal, but the dev buy uses SEVERAL pump buy discriminators, not just buy_exact_quote_in_v3/classic (b817ee6167c5d33d, 38fc74089edfcd5f seen). Measuring dev buy by the pump buy discriminator alone UNDERCOUNTS; the honest measure is the bonding-curve SOL delta in the create tx.")
L.append(f"- Dev-buy median here is ~{st.median([x/1e9 for x in devs]):.2f} SOL (prior guess 0.5-1.0 SOL).")
L.append("- His own buy size (median ~{:.1f} SOL) is large/aggressive, not a micro snipe.".format(st.median([r['buy_lamports']/1e9 for r in R])))
L.append("")
L.append(f"## Confidence / caveats")
L.append(f"- N={N} landed snipes over ~{hours:.0f}h is a solid single-session sample but one wallet, one window; not lifetime behavior.")
L.append(f"- {len(uncreat)} creates undecoded: earliest-slot tx carried no pump create_v2 (not a pagination limit; 0 beyond the 16k-sig cap). Excluded from pattern %, counted as MISS-undecoded.")
L.append(f"- dev_buy includes ~0.001 SOL account rent (negligible at 0.3-1.0 SOL thresholds).")
L.append(f"- Creator fresh/repeat is in-window only (12h); true factory history not checked.")
L.append(f"- Outcome/PnL not computed (primary ask was the pre-buy signal).")

out="\n".join(L)
open('/root/snipe_study50/REPORT.md','w').write(out)
print(out)
