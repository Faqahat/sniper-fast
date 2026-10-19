# Off-Chain Source of Sniper 4yFAz…EQrG3 — On-Chain Footprint Analysis

TARGET: `4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3`

Method: For each of his 409 picked mints (`/root/last500/his_500.json`) we pulled EVERY pump.fun
bonding-curve buy (program `6EF8…wF6P`, buy disc `e1f7501ed5b38488`) in the token's create slot
and the next 3 slots via `getBlock` (intra-slot order preserved by tx index). 404 mints had block
data; target present in 385. A control of 300 random blocks (611 buys, 393
distinct mints) in the same slot range gives the base rate.

## VERDICT (most likely source)

**He does not follow a public named caller group. He is one wallet in a COORDINATED FLEET/CLUSTER
of ~10+ bot wallets that all act on the SAME private automated feed (a scanner/first-seen signal),
firing in the token's create slot.** The footprint is a tight recurring co-buyer cohort, not a
caller→follower lag chain, and the cohort is NOT a named/public service we could identify.

Decisive evidence: the target's OWN first-ever transaction (unix 1791842553) falls inside the SAME
194-second window (1791842359–1791842553) in which 10 of his top co-buyers were first activated.
A dozen wallets born within ~3 minutes, then repeatedly buying the same brand-new tokens in the same
slot, is a single batch-deployed operation (one operator's fleet, or a service that batch-provisions
wallets per subscriber). Confidence: HIGH that it's a coordinated cluster sharing one feed; the feed
itself is off-chain and unnamed (MEDIUM-LOW that we can ever name it from on-chain data alone).

## (a) Recurring co-buyer COHORT (ranked by co-occurrence, with lift vs random base)

`his_rate` = fraction of his 402 picks the wallet also bought in-window. `rand` = distinct random
launches it bought in the 300-block control (max any generic sniper reached = 3). `lift` = his_rate /
base_rate; `inf` means 0 random hits (lift effectively unbounded, floor ~>35x).

| wallet | #his picks | his_rate | rand mints | lift | first-tx (unix) |
|---|---|---|---|---|---|
| `AMDEmVocLtN5ji2gBY7BrmSHEyM5vt6TGszBbg4crMXg` | 36 | 0.093 | 1 | 36.7 | 1791842365 |
| `dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK` | 34 | 0.088 | 1 | 34.7 | 1791842458 |
| `9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw` | 33 | 0.086 | 0 | inf | — |
| `BXB7FF4m5x74ZoUvVHfPJnVBbqWHpMEU1WNUZAL9W8PL` | 29 | 0.075 | 0 | inf | 1791842501 |
| `G8gTguf7EUwqfwdRhiZ3KCBEgPURVB7LXoDzHif4p6oh` | 28 | 0.073 | 0 | inf | 1791842367 |
| `CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J` | 23 | 0.060 | 1 | 23.5 | 1791842359 |
| `GjsVMaLbPv4ZPL5Yvypzms8iyubXgP16JreJB3FGyGfd` | 19 | 0.049 | 0 | inf | 1791842359 |
| `GTfHPpyyoC6X4uxmhLBWzovQCsSMZ8cfckPt8dcxeKcq` | 20 | 0.052 | 0 | inf | 1791842523 |
| `G9sQPg9Eimkwe72w1xH1tPUc9RFNuK6Ufw5AyWy6j7ob` | 16 | 0.042 | 0 | inf | 1791842537 |
| `8ptvshQRZPRaRQBSCRxhHwbJFr6ktyUQ1SATDCLijkBW` | 13 | 0.034 | 0 | inf | 1791842523 |
| `AmN88ff21osxR5CWnawN3GWDbpKtReCzDABdGWQvdLyB` | 13 | 0.034 | 0 | inf | — |
| `HxcdEi6CWzQtPCmM8E2maEZ3oYVGZxESqCWU1iPzmhVW` | 11 | 0.029 | 0 | inf | — |
| `7PtVk5TZ8J9ohTVS6r2kLzrY33JzShaS3RC6ycC1NNEG` | 9 | 0.023 | 0 | inf | — |
| `2eYye8c22N5ABQZjdsUGEqcCxkAnm8FP936wFZ5TYK7T` | 10 | 0.026 | 0 | inf | — |

Median distinct buyers per his-pick window = 2 (just him + 1-2 siblings): his picks are thinly
sniped, and the few who show up are overwhelmingly these same recurring wallets — not the open market.

Every cohort wallet is highly SELECTIVE: 0–1 of 393 random launches. They are not 'snipe-everything'
bots; they specifically track the same tokens he does (lift 23–37x where measurable, unbounded otherwise).

## (b) LEAD wallets (who buys BEFORE him)

Target is the FIRST non-dev buyer in **78%** of his picks and buys IN the create slot in 79% (319/402),
+1 slot in the rest. So on-chain almost nobody leads him. When a sibling does precede him it is within
the SAME slot (median slot gap = 0) — i.e. a near-simultaneous race on the same trigger, decided by
landing/tip, NOT a caller firing seconds ahead. No single wallet consistently leads him; the 'leads'
are spread across siblings:

| wallet | leads_him | co-occur | lead_frac | med slot gap |
|---|---|---|---|---|
| `dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK` | 12 | 34 | 0.35 | 0.0 |
| `9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw` | 11 | 33 | 0.33 | 0 |
| `6uiavDTbUSpnLpekSv9sE2gZj15Lrsq9c39VWTrUsTov` | 5 | 9 | 0.56 | 0 |
| `JCabuXeNmk1s1mF7oCaYQUThkJEb4vWnDGbNFk9tcVU8` | 5 | 5 | 1.00 | 0 |
| `2EsRiaPazhbDCEsx8pztTfRPSkVG4TU8UpmGSYrWAnHJ` | 4 | 7 | 0.57 | 0 |
| `BXB7FF4m5x74ZoUvVHfPJnVBbqWHpMEU1WNUZAL9W8PL` | 4 | 29 | 0.14 | 0 |
| `8b7EKWC6QDENxt2ZEtVui2ewAqxcK1jzpHn9MG2LGBMF` | 4 | 4 | 1.00 | 0.0 |
| `8fn3aH5kBWDac3cgrLpyxNLkaSx29Qm9K46S28NGJnbw` | 4 | 4 | 1.00 | 0.0 |

Top sibling leaders `9qz7cW…` (12/36) and `dKMje…` (11/35) lead ~1/3 of shared picks, same-slot.
This is consistent with a shared feed, not a signal-source wallet he mirrors.

## (c) Timing signature

Create-slot entry 319/402 (79%), +1 slot 83/402 (21%). A 0–1 slot (sub-second to ~0.4s) deterministic
lag from token creation = an AUTOMATED SCANNER/mempool feed. Human Telegram calls would land many
slots / seconds later with high variance. This is a bot feed, not manual calling.

## (d) Cohort character & funding

- 10+ wallets (incl. the target) share a ~3-minute genesis window → single batch deployment.

- All are moderate-to-high frequency bots (target ~5 buys/min bursts; `9qz7cW` ~15/min; 800–14k lifetime txs).

- `9qz7cW…` is a later addition to the cluster (genesis ~1792008018, ~2 days after), funded with 4.32 SOL
  from `E5uu9U8tCDewc8wr2ceyEakZJP6PTL357FaiC8CtbgBN` — an unlabeled wallet (not a known exchange/service).

- No incoming-transfer funder was resolvable at genesis for the core 10 (first recorded sig is already
  a buy), consistent with pre-funded, script-deployed wallets.

## (e) Naming the source (web cross-reference)

WebSearch/WebFetch on the target and the top cohort/lead/funder wallets across gmgn.ai, Solscan, X,
Dune and pump.fun community sources returned **no labels, handles, or named associations** for any of
them. gmgn returns 403 to automated fetch; kolscan/gmgn require live JS lookups we could not script.
No public caller group, scanner brand, or KOL handle maps to this cluster.

**Honest bottom line:** the off-chain signal is real and its footprint is unmistakable — a tight,
batch-deployed cohort of ~10+ wallets (the target among them) that buy the same brand-new tokens in
the same slot on a shared automated feed. We can NAME the cohort (wallets listed above) but we CANNOT
name the service/group behind the feed from on-chain + public web data. Most likely it is a private
sniper operation / paid scanner cluster, not a public Telegram caller group.

## Files

- `cohort.json` — co-buyer cohort with lift + genesis
- `leads.json` — lead-wallet table

- `buys_raw.json` — raw per-mint buy records
- `control2.json` — random-block base-rate control

- `collect.py / analyze.py / control.py / control2.py / char.py / fund2.py` — pipeline
