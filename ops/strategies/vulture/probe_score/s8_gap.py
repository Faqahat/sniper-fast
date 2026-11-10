# Step 8: why the engine's dump stream (r30/r31) had only 516 of the 1,947 tape envelope dumps (sell>=0.3, drop>=3).
# Engine rules (read from src/dip_imit.rs TokenBook::push + dipmode.rs, read only):
#   token tracked only if its create was seen live (created after engine start), kept max_age_s+300 s;
#   dump event: sell >= MIN_SELL 1.0 SOL, not synthetic, after the launch "glued" group (k >= g_end), 1 s <= age <= max_age_s (1800 default),
#   post-trade vsol < 100 SOL, and only the FIRST such sell per mint-slot (busy slot). Then VULT_PROBE envelope sell>=0.3 & drop>=3.
import sys,pickle,json,collections,numpy as np
sys.dont_write_bytecode=True
D='/home/it/sniper-data/vulture_probe_score/'
cfg=json.load(open('/home/it/sniper-studies/sniper-vulture2x/VULTURE_v2.json')); THR=cfg['select']['score_thr']
S=pickle.load(open(D+'scored.pkl','rb'))['feat']; P=pickle.load(open(D+'probe.pkl','rb'))
SLOT_MS=None
out=[];pr=lambda *a:(print(*a,flush=True),out.append(' '.join(str(x) for x in a)))
tot=collections.Counter(); totp=collections.Counter()
for run in ('r30','r31'):
    dm=P[run]['dumps']; t0=P[run]['start']['t']
    ts=np.array([d['t'] for d in dm],float); ss=np.array([d['slot'] for d in dm],float)
    a,b=np.polyfit(ts,ss,1); start_slot=int(a*t0+b)
    lo,hi=min(d['slot'] for d in dm),max(d['slot'] for d in dm)
    eng={(d['mint'],d['slot'],d['idx']) for d in dm}
    rows=[c for c in S['rows'] if lo<=c['slot']<=hi and c['sol']>=0.3 and c['drop']>=3]
    # first >=1 SOL sell per mint-slot among ALL tape sells (the engine's busy-slot rule)
    big=collections.defaultdict(list)
    for c in S['rows']:
        if lo<=c['slot']<=hi and c['sol']>=1.0: big[(c['m'],c['slot'])].append(c['idx'])
    # NB: S['rows'] holds only drop>=3 sells; a >=1 SOL sell with drop<3 earlier in the slot would also block (not visible here -> 'other')
    reasons=collections.Counter(); rp=collections.Counter()
    for c in rows:
        k=(c['m'],c['slot'],c['idx'])
        if k in eng: r='0 engine reported'
        elif c['slot']-c['age']<start_slot: r='1 token created before engine start'
        elif c['sol']<1.0: r='2 sell < 1.0 SOL (engine MIN_SELL)'
        elif c['age']*0.2137<1.0: r='3 age < 1 s'
        elif c['age']*0.2137>1800: r='3b age > 1800 s'
        elif c['vpost']>=100: r='4 vsol >= 100'
        elif min(big[(c['m'],c['slot'])])<c['idx']: r='5 not first >=1 SOL sell in slot'
        else: r='6 other (launch group g_end / feed miss)'
        reasons[r]+=1
        if c['score']>=THR: rp[r]+=1
    pr(f"{run}: start slot ~{start_slot}, window {lo}..{hi}, tape envelope dumps {len(rows)}")
    for r in sorted(reasons): pr(f"   {r}: {reasons[r]}  (model picks {rp[r]})")
    tot+=reasons; totp+=rp
pr("TOTAL:"); [pr(f"   {r}: {tot[r]}  (model picks {totp[r]})") for r in sorted(tot)]
open(D+'gap.txt','w').write('\n'.join(out)+'\n')
