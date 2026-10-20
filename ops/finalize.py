import json, statistics
THRESH = 30
res = json.load(open("/root/creators_resolved.json"))        # fee-payer/deployer mapping
counts = json.load(open("/root/creator_sigcounts.json"))     # deployer -> total lifetime sigs (cap100)
pit = json.load(open("/root/creator_pit.json"))              # true-creator (create-ix acct7) + prior-at-launch

picks_fp = {m: c for m, c in res["picks"].items() if c}      # mint -> deployer(fee payer)
pop_fp   = {m: c for m, c in res["pop"].items() if c}

# ---- DELIVERABLE BLOCKLIST: serial DEPLOYER wallets (fee payer), lifetime sigs > THRESH ----
# union of all observed deployer wallets (picks+pop) that are serial
all_deployers = set(picks_fp.values()) | set(pop_fp.values())
blocked = sorted(c for c in all_deployers if counts.get(c, -1) > THRESH)
with open("/root/sniper-fast/creator_blocklist.txt", "w") as f:
    for c in blocked:
        f.write(c + "\n")

def dist(vals, label):
    vals = sorted(v for v in vals if v >= 0)
    if not vals:
        print(f"{label}: EMPTY"); return
    def q(x): return vals[min(len(vals)-1, int(x*len(vals)))]
    b = {"0":0,"1-5":0,"6-30":0,"31-99":0,"100(cap)":0}
    for v in vals:
        if v==0: b["0"]+=1
        elif v<=5: b["1-5"]+=1
        elif v<=30: b["6-30"]+=1
        elif v<100: b["31-99"]+=1
        else: b["100(cap)"]+=1
    print(f"{label}: n={len(vals)} median={statistics.median(vals)} p25={q(.25)} p75={q(.75)} p90={q(.9)} max={max(vals)} buckets={b}")

print("================ DEFINITION A: creator = DEPLOYER wallet (tx fee payer) ================")
pop_dep = set(pop_fp.values()); pick_dep = set(picks_fp.values())
dist([counts.get(c,-1) for c in pop_dep], "pop deployers (lifetime sigs)")
dist([counts.get(c,-1) for c in pick_dep], "pick deployers (lifetime sigs)")
print(f"unique pop deployers: {len(pop_dep)}  measured: {sum(1 for c in pop_dep if counts.get(c,-1)>=0)}")
print(f"BLOCKLIST size (serial deployers, lifetime>{THRESH}): {len(blocked)}  -> /root/sniper-fast/creator_blocklist.txt")
# validation
blockset = set(blocked)
pick_dep_meas = [c for c in pick_dep if counts.get(c,-1)>=0]
pick_dep_blocked = sum(1 for c in pick_dep_meas if counts[c] > THRESH)
pick_mint_meas = sum(1 for m,c in picks_fp.items() if counts.get(c,-1)>=0)
pick_mint_blocked = sum(1 for m,c in picks_fp.items() if counts.get(c,-1) > THRESH)
print(f"VALIDATION: 4yFAz pick DEPLOYERS blocked = {pick_dep_blocked}/{len(pick_dep_meas)} = {100*pick_dep_blocked/max(1,len(pick_dep_meas)):.1f}%")
print(f"VALIDATION: 4yFAz pick MINTS blocked     = {pick_mint_blocked}/{pick_mint_meas} = {100*pick_mint_blocked/max(1,pick_mint_meas):.1f}%")

print("================ DEFINITION B: creator = true pump CREATE-ix acct[7] (dev) ================")
pr_pop = [r["prior"] for r in pit["pop"].values() if r.get("creator") and r.get("prior",-1)>=0]
pr_pick = [r["prior"] for r in pit["picks"].values() if r.get("creator") and r.get("prior",-1)>=0]
dist(pr_pop, "pop true-creator (prior-at-launch)")
dist(pr_pick, "pick true-creator (prior-at-launch)")
pop_tc = {}
for r in pit["pop"].values():
    if r.get("creator") and r.get("prior",-1)>=0:
        pop_tc[r["creator"]] = max(pop_tc.get(r["creator"],-1), r["prior"])
serial_tc = [c for c,p in pop_tc.items() if p>THRESH]
print(f"unique pop true-creators measured: {len(pop_tc)}  serial(prior>{THRESH}): {len(serial_tc)}")
pick_tc_block = sum(1 for r in pit["picks"].values() if r.get("creator") and r.get("prior",-1)>THRESH)
pick_tc_meas = sum(1 for r in pit["picks"].values() if r.get("creator") and r.get("prior",-1)>=0)
print(f"VALIDATION: 4yFAz pick true-creators blocked = {pick_tc_block}/{pick_tc_meas}")
print("NOTE: true-creator coverage limited to create-ix discs {181ec828,07051dc4}; parsed subset only.")
