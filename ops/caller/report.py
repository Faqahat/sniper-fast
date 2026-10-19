import json
coh=json.load(open("/root/caller/cohort.json"))
leads=json.load(open("/root/caller/leads.json"))["leads"]
rows=coh["cohort"]

def esc(w): return w
lines=[]
A=lines.append
A("# Off-Chain Source of Sniper 4yFAz…EQrG3 — On-Chain Footprint Analysis\n")
A("TARGET: `4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3`\n")
A("Method: For each of his 409 picked mints (`/root/last500/his_500.json`) we pulled EVERY pump.fun")
A("bonding-curve buy (program `6EF8…wF6P`, buy disc `e1f7501ed5b38488`) in the token's create slot")
A("and the next 3 slots via `getBlock` (intra-slot order preserved by tx index). 404 mints had block")
A(f"data; target present in {coh['target_present']}. A control of 300 random blocks (611 buys, 393")
A("distinct mints) in the same slot range gives the base rate.\n")

A("## VERDICT (most likely source)\n")
A("**He does not follow a public named caller group. He is one wallet in a COORDINATED FLEET/CLUSTER")
A("of ~10+ bot wallets that all act on the SAME private automated feed (a scanner/first-seen signal),")
A("firing in the token's create slot.** The footprint is a tight recurring co-buyer cohort, not a")
A("caller→follower lag chain, and the cohort is NOT a named/public service we could identify.\n")
A("Decisive evidence: the target's OWN first-ever transaction (unix 1791842553) falls inside the SAME")
A("194-second window (1791842359–1791842553) in which 10 of his top co-buyers were first activated.")
A("A dozen wallets born within ~3 minutes, then repeatedly buying the same brand-new tokens in the same")
A("slot, is a single batch-deployed operation (one operator's fleet, or a service that batch-provisions")
A("wallets per subscriber). Confidence: HIGH that it's a coordinated cluster sharing one feed; the feed")
A("itself is off-chain and unnamed (MEDIUM-LOW that we can ever name it from on-chain data alone).\n")

A("## (a) Recurring co-buyer COHORT (ranked by co-occurrence, with lift vs random base)\n")
A("`his_rate` = fraction of his 402 picks the wallet also bought in-window. `rand` = distinct random")
A("launches it bought in the 300-block control (max any generic sniper reached = 3). `lift` = his_rate /")
A("base_rate; `inf` means 0 random hits (lift effectively unbounded, floor ~>35x).\n")
A("| wallet | #his picks | his_rate | rand mints | lift | first-tx (unix) |")
A("|---|---|---|---|---|---|")
for c in rows[:14]:
    lift = c['lift'] if c['lift'] is not None else "inf"
    A(f"| `{c['wallet']}` | {c['co_with_target']} | {c['his_pick_rate']:.3f} | {c['random_mints_bought']} | {lift} | {c.get('genesis_unix') or '—'} |")
A("\nMedian distinct buyers per his-pick window = %.0f (just him + 1-2 siblings): his picks are thinly"%coh['median_buyers_per_mint'])
A("sniped, and the few who show up are overwhelmingly these same recurring wallets — not the open market.\n")
A("Every cohort wallet is highly SELECTIVE: 0–1 of 393 random launches. They are not 'snipe-everything'")
A("bots; they specifically track the same tokens he does (lift 23–37x where measurable, unbounded otherwise).\n")

A("## (b) LEAD wallets (who buys BEFORE him)\n")
A("Target is the FIRST non-dev buyer in **78%** of his picks and buys IN the create slot in 79% (319/402),")
A("+1 slot in the rest. So on-chain almost nobody leads him. When a sibling does precede him it is within")
A("the SAME slot (median slot gap = 0) — i.e. a near-simultaneous race on the same trigger, decided by")
A("landing/tip, NOT a caller firing seconds ahead. No single wallet consistently leads him; the 'leads'")
A("are spread across siblings:\n")
A("| wallet | leads_him | co-occur | lead_frac | med slot gap |")
A("|---|---|---|---|---|")
for l in leads[:8]:
    A(f"| `{l['wallet']}` | {l['leads_him']} | {l['co_with_target']} | {l['lead_frac']:.2f} | {l['med_slotgap']} |")
A("\nTop sibling leaders `9qz7cW…` (12/36) and `dKMje…` (11/35) lead ~1/3 of shared picks, same-slot.")
A("This is consistent with a shared feed, not a signal-source wallet he mirrors.\n")

A("## (c) Timing signature\n")
A("Create-slot entry 319/402 (79%), +1 slot 83/402 (21%). A 0–1 slot (sub-second to ~0.4s) deterministic")
A("lag from token creation = an AUTOMATED SCANNER/mempool feed. Human Telegram calls would land many")
A("slots / seconds later with high variance. This is a bot feed, not manual calling.\n")

A("## (d) Cohort character & funding\n")
A("- 10+ wallets (incl. the target) share a ~3-minute genesis window → single batch deployment.\n")
A("- All are moderate-to-high frequency bots (target ~5 buys/min bursts; `9qz7cW` ~15/min; 800–14k lifetime txs).\n")
A("- `9qz7cW…` is a later addition to the cluster (genesis ~1792008018, ~2 days after), funded with 4.32 SOL")
A("  from `E5uu9U8tCDewc8wr2ceyEakZJP6PTL357FaiC8CtbgBN` — an unlabeled wallet (not a known exchange/service).\n")
A("- No incoming-transfer funder was resolvable at genesis for the core 10 (first recorded sig is already")
A("  a buy), consistent with pre-funded, script-deployed wallets.\n")

A("## (e) Naming the source (web cross-reference)\n")
A("WebSearch/WebFetch on the target and the top cohort/lead/funder wallets across gmgn.ai, Solscan, X,")
A("Dune and pump.fun community sources returned **no labels, handles, or named associations** for any of")
A("them. gmgn returns 403 to automated fetch; kolscan/gmgn require live JS lookups we could not script.")
A("No public caller group, scanner brand, or KOL handle maps to this cluster.\n")
A("**Honest bottom line:** the off-chain signal is real and its footprint is unmistakable — a tight,")
A("batch-deployed cohort of ~10+ wallets (the target among them) that buy the same brand-new tokens in")
A("the same slot on a shared automated feed. We can NAME the cohort (wallets listed above) but we CANNOT")
A("name the service/group behind the feed from on-chain + public web data. Most likely it is a private")
A("sniper operation / paid scanner cluster, not a public Telegram caller group.\n")

A("## Files\n")
A("- `cohort.json` — co-buyer cohort with lift + genesis\n- `leads.json` — lead-wallet table\n")
A("- `buys_raw.json` — raw per-mint buy records\n- `control2.json` — random-block base-rate control\n")
A("- `collect.py / analyze.py / control.py / control2.py / char.py / fund2.py` — pipeline\n")

open("/root/caller/REPORT.md","w").write("\n".join(lines))
print("wrote REPORT.md", len("\n".join(lines)), "bytes")
