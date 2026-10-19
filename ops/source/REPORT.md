# SOURCE / DEPLOYER-FINGERPRINT STUDY — does launch source explain 4yFAz's ~1% pick rule?

Target: 4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3
Question driven to the bottom: the strongest un-cracked slot-0 lead was that his tokens over-index on
specific DEPLOYER TERMINALS / launch SOURCES (every_angle: j7tracker 21% vs 12%, uxento 11% vs 3%).
Does the LAUNCH SOURCE / DEPLOYER FINGERPRINT visible in the create tx at slot 0 explain and reproduce
his pick set — closing the unexplained 24%->1% tightening?

Data: his 505 last landed picks (404 with create tx recovered) vs unbiased population (1,141 creates,
all with create tx). Every slot-0 source fingerprint extracted from the create tx.
Files: /root/source/his_src.json, pop_src.json, extract_src.py, analyze_src.py, combo.py.
Builds on /root/every_angle (terminal lead), /root/last500 (vanilla+dev-buy filter), /root/profit_backtest (population).

## VERDICT (up front, decisive)

**NO. The launch source / deployer fingerprint is NOT his selector and does NOT reproduce his ~1%
selection.** The j7tracker/uxento over-index is real but (a) modest, (b) covers only ~27% of his picks,
and (c) collapses to a wash once you condition on the vanilla/launch-config filter already known.
Conditional on the exact pool our filter fires on (vanilla & dev-buy>=0.5 - "the 24%"), his picks'
source distribution is statistically indistinguishable from the rest of the pool. His residual
selection looks like a random draw by source from the launches he already qualifies - the
signature of OFF-CHAIN selection (caller groups / scanners / alpha feeds) that chain data cannot reveal.

## THE SLOT-0 SOURCE FINGERPRINTS EXTRACTED (every one requested)

1. Metadata URI host / terminal (parsed from create_v2 uri arg) - the deployer-tool identity.
2. Mint vanity suffix (...pump, ...fomo, custom vanity).
3. Create-tx structure: # instructions, program sequence, # compute-budget ix, cu_limit, cu_price,
   jito-tip presence/amount, # pump ix, account count, fee payer.
4. Dev-buy instruction shape: discriminator (7 variants = tool versions), bundled vs separate, sol offset.
5. Dev/creator wallet config flags (mayhem/holder_reward/cashback/vanilla) joined per mint.
6. (Creator funding/age cluster already ruled out at every_angle: 118 funders/146 creators, top cluster 15%, no EV.)

## RANKED SOURCE-FEATURE SEPARATION (his vs population, unconditional)

Lift = P(feature | his) / P(feature | population). N: his=404, pop=1141.

| source feature | P(his) | P(pop) | lift | recall of his | pop coverage |
|---|---|---|---|---|---|
| uri host = uxento | 0.121 | 0.052 | 2.35 | 12% | 5% |
| uri host = j7tracker | 0.146 | 0.107 | 1.37 | 15% | 11% |
| any pro-terminal (j7+uxento+rapid+quick+viola+extraction) | 0.309 | 0.211 | 1.46 | 31% | 21% |
| NOT plain ipfs.io | 0.505 | 0.283 | 1.78 | 51% | 28% |
| uri host = plain ipfs.io | 0.495 | 0.717 | 0.69 | - | 72% |
| has compute-budget ix (n_cb>=1) | 0.649 | 0.350 | 1.85 | 65% | 35% |
| cu_limit = 520000 | 0.059 | 0.010 | 6.16 | 6% | 1% |
| cu_limit = 400000 | 0.089 | 0.029 | 3.08 | 9% | 3% |
| dev-buy disc 38fc7408... | 0.151 | 0.060 | 2.53 | 15% | 6% |
| prog_seq CB-CB-SYS-PUMP-ATA-PUMP | 0.059 | 0.011 | 5.65 | 6% | 1% |
| mint suffix != pump | 0.136 | 0.083 | 1.64 | 14% | 8% |
| jito tip in create tx | 0.196 | 0.167 | 1.17 | 20% | 17% |

Pattern: his picks tilt toward tool-deployed launches (compute-budget present, pro-terminal hosts,
specific cu_limit/cu_price/dev-buy-disc values) rather than the bare pump.fun web client. But the
individually high-lift fingerprints (cu_limit 520k, exotic prog_seqs, lift 5-6x) are RARE - each
recalls only 6-9% of his picks. The features that recall a lot of his (plain ipfs.io 50%, j7tracker
15%) have low lift and huge population coverage.

## WHY SOURCE CANNOT REPRODUCE HIS SELECTION (the cumulative test)

Order tools by lift, accumulate recall of his vs population coverage:

| after adding (high-lift -> low) | cum recall of his | cum pop coverage |
|---|---|---|
| all exotic hosts + extraction + vortex + uxento | 0.31 | 0.06 |
| + j7tracker | 0.46 | 0.17 |
| + rapidlaunch | 0.48 | 0.19 |
| + plain ipfs.io | 0.97 | 0.91 |

To recall more than ~48% of his picks you are forced to include plain ipfs.io, which instantly
pushes coverage to 91% of all launches. There is no source subset that recalls most of his picks at
low coverage - recall and coverage rise together. The best source-only cut tops out at ~48% recall /
~19% coverage (lift ~2.5), nowhere near reproducing a ~1% pick rate at high recall.

## SOURCE ADDS NOTHING BEYOND THE KNOWN VANILLA/CONFIG FILTER (the killer)

The j7tracker/uxento over-index is a proxy for the vanilla launch-type filter, not an independent
selector. Restricting BOTH sets to the exact pool our filter already fires on - vanilla & dev-buy>=0.5
(the "24%") - his source distribution ~= the population pool's:

| tool | P(his | pool) | P(pop | pool) | lift |
|---|---|---|---|---|
| plain ipfs.io | 0.585 | 0.612 | 0.96 |
| j7tracker | 0.116 | 0.134 | 0.87 (now UNDER-indexes) |
| uxento | 0.105 | 0.080 | 1.31 |
| rapidlaunch | 0.031 | 0.065 | 0.48 |
| pinata | 0.031 | 0.062 | 0.50 |

Conditional on the filter he already passes, his picks are a random draw by source - j7tracker even
drops below parity. Source carries no information about which of the qualified launches he actually fires on.

Combined rules confirm source cannot tighten the 24% toward 1%:

| rule | recall of his | pop coverage | lift |
|---|---|---|---|
| vanilla | 0.76 | 0.50 | 1.53 |
| vanilla & dev>=0.5 (the 24%) | 0.64 | 0.24 | 2.64 |
| vanilla & tool in pro | 0.19 | 0.13 | 1.45 |
| vanilla & dev>=0.5 & tool in pro | 0.18 | 0.07 | 2.45 |
| vanilla & dev>=2.0 & tool in pro | 0.10 | 0.04 | 2.63 |

Adding a source condition only trades recall for coverage at ~constant lift (~2.5). No source-augmented
rule gets near his 1% rate while keeping meaningful recall.

## OOS PERSISTENCE (chronological split by create_slot, IS=early half, OOS=late half, his picks)

His favored sources persist but are modest and stable, not tightening:
- plain ipfs.io 0.495 -> 0.528 (flat, dominant in both halves)
- j7tracker 0.161 -> 0.145 (flat)
- uxento 0.078 -> 0.171 (grows, but still ~17%)
- ("none" = create-tx-unrecovered older picks: IS 0.146 -> OOS 0.000 - a pure recovery artifact, not a source)

No source concentrates over time toward a tight set; the dominant source in both windows is the same
plain ipfs.io that dominates the population.

## FINAL VERDICT

His token-choice rule is NOT a launch-source / deployer rule. The deployer-terminal lead, driven to
the bottom at 500 scale, resolves to: his picks mildly favor tool-deployed launches (uxento 2.4x,
compute-budget present 1.85x), but this (1) recalls too little of his set, (2) never separates at low
coverage, and (3) entirely collapses once conditioned on the vanilla/dev-buy filter already known -
his source profile inside that pool is indistinguishable from the pool itself.

Combined with every prior negative (not creator-whitelist, not dev-buy size, not socials/time/funding,
co-snipe/early-flow contemporaneous-only), no on-chain slot-0 feature reproduces his ~1% selection.
Conditional on vanilla+dev-buy, his picks look random with respect to every static create-tx fingerprint
tested. That is the fingerprint of OFF-CHAIN selection - the final filter from 24% -> 1% is made on
information not present in the create transaction (caller groups, Telegram/alpha feeds, external scanners,
or his own discretion). Chain data cannot recover it.

The one on-chain thread that survives (and all it is): he fires on vanilla pump.fun launches with a
real curve dev-buy - and within that set he picks on something off-chain. The actionable on-chain levers
remain those from last500 (curve-truth dev-buy >= threshold + vanilla for EV; create-slot co-snipe for his
variance profile). Source is not a usable additional gate.
