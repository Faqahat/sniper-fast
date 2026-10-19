import json, statistics as st
from collections import defaultdict, Counter

D = json.load(open("/root/caller/buys_raw.json"))
TARGET = D["target"]
recs = D["records"]           # (mint, slot, txidx, buyer, lam)
his = D["his_mints"]          # mint -> {create_slot, his_buy_slot}

# group buys by mint
by_mint = defaultdict(list)
for mint,slot,ti,buyer,lam in recs:
    by_mint[mint].append((slot,ti,buyer,lam))

# order within mint by (slot, txidx)
for m in by_mint: by_mint[m].sort(key=lambda x:(x[0],x[1]))

N_picks_with_buys = 0
target_present = 0
cooc = Counter()          # wallet -> #distinct his-mints it appears in
leads = Counter()         # wallet -> #mints where it bought BEFORE target
lead_slotgap = defaultdict(list)  # wallet -> list of (target_slot - wallet_slot)
coappear_when_target = Counter()  # wallet -> #mints where BOTH present
same_slot_lead = Counter()
his_rank = []             # target's ordinal position among buyers (0-based) per mint
his_delta = []            # his_buy_slot - create_slot
his_slotpos = []          # target slot - create slot (from block data)
n_buyers_per_mint = []

for mint, buys in by_mint.items():
    cs = his[mint]["create_slot"]
    wallets_here = set(b[2] for b in buys)
    for w in wallets_here: cooc[w]+=1
    n_buyers_per_mint.append(len(wallets_here))
    N_picks_with_buys += 1
    # find target's first buy
    tpos=None; tslot=None
    for idx,(slot,ti,buyer,lam) in enumerate(buys):
        if buyer==TARGET:
            tpos=idx; tslot=slot; ti_t=ti; break
    if tpos is None: continue
    target_present += 1
    his_rank.append(tpos)
    his_slotpos.append(tslot-cs)
    # wallets that bought strictly before target (in order)
    seen_before=set()
    for idx in range(tpos):
        seen_before.add(buys[idx][2])
    for w in seen_before:
        if w==TARGET: continue
        leads[w]+=1
    # for all co-present wallets, record slot gap (target - their first buy)
    first_slot_of={}
    for slot,ti,buyer,lam in buys:
        if buyer not in first_slot_of: first_slot_of[buyer]=slot
    for w in wallets_here:
        if w==TARGET: continue
        coappear_when_target[w]+=1
        lead_slotgap[w].append(tslot-first_slot_of[w])

print(f"mints with any buy data: {N_picks_with_buys}")
print(f"mints where TARGET present in window: {target_present}")
print(f"median distinct buyers per mint window: {st.median(n_buyers_per_mint):.1f}")
print(f"target buyer-rank (0=first): median={st.median(his_rank)} mean={sum(his_rank)/len(his_rank):.2f}  first%={sum(1 for x in his_rank if x==0)/len(his_rank):.3f}")
sp=Counter(his_slotpos)
print(f"target slot offset from create: {dict(sorted(sp.items()))}")

# ---- COHORT: top co-occurring wallets ----
print("\n=== TOP CO-OCCURRING WALLETS (across his picks) ===")
print(f"{'wallet':<46} {'#his_mints':>10} {'coWtarget':>10} {'leads_him':>10} {'medSlotGap':>10}")
top = cooc.most_common(40)
cohort=[]
for w,c in top:
    if w==TARGET: continue
    cw=coappear_when_target.get(w,0)
    lh=leads.get(w,0)
    gaps=lead_slotgap.get(w,[])
    medgap = st.median(gaps) if gaps else None
    cohort.append({"wallet":w,"his_mints":c,"co_with_target":cw,
                   "leads_him":lh,"lead_frac": lh/cw if cw else 0,
                   "med_slotgap_targetminus":medgap,
                   "frac_of_targetpicks": cw/target_present})
    print(f"{w:<46} {c:>10} {cw:>10} {lh:>10} {str(medgap):>10}")

# ---- LEADS: wallets that most often precede him ----
print("\n=== WALLETS THAT LEAD HIM (bought before target, same window) ===")
print(f"{'wallet':<46} {'leads_him':>10} {'coW':>6} {'lead_frac':>9} {'medGap':>7}")
lead_rank=[]
for w,lh in leads.most_common(40):
    cw=coappear_when_target.get(w,0)
    gaps=lead_slotgap.get(w,[])
    medgap=st.median(gaps) if gaps else None
    lead_rank.append({"wallet":w,"leads_him":lh,"co_with_target":cw,
                      "lead_frac":lh/cw if cw else 0,"med_slotgap":medgap})
    print(f"{w:<46} {lh:>10} {cw:>6} {lh/cw if cw else 0:>9.3f} {str(medgap):>7}")

json.dump({"target_present":target_present,"n_mints":N_picks_with_buys,
           "cohort":cohort,"median_buyers_per_mint":st.median(n_buyers_per_mint)},
          open("/root/caller/cohort.json","w"),indent=1)
json.dump({"leads":lead_rank},open("/root/caller/leads.json","w"),indent=1)
print("\nwrote cohort.json + leads.json")
