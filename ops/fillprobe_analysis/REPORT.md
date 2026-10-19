# Sniper Fill-Quality Probe — 5 Live Buys

Wallet/payer `FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS`. RPC = constantk staked (Frankfurt). Buys are v0; creates v1.

## Method

- **Floor** = marginal pool price *immediately after the dev buy* (first trade in the create slot), `virtual_sol/virtual_token`.

- **Reserves**: pump constant-product, verified empirically on-chain. SOL offset 30e9, token offset 73e12, k = 30e9*(1e15+73e12). Predicted dev-buy SOL matched measured curve lamport delta to <0.2% on every probe.

- **Our fill** = SOL actually added to the bonding curve by our buy (curve lamport delta, net of the 1% pump fee / ATA rent / priority — pure pool price) / base tokens we received. Apples-to-apples vs floor (also a pool price).

- **Ordering** taken from `getBlock` (authoritative block index), across the create slot + next 2 slots.

- All prices in **lamports per base token** (6-decimal units).


## Per-probe results

| # | mint | dev SOL | create→land | floor | our fill | **fill ratio** | buys before us (✓) | rank in our landed slot | distinct buyers in create slot |
|---|------|---------|-------------|-------|----------|----------------|--------------------|-------------------------|-------------------------------|
| 1 | A8FjoUQX | 3.0 | c+1 | 3.3754e-05 | 4.4983e-05 | **1.333** | 4 | 1 | 4 |
| 2 | U5jNL2jH | 2.0 | c+1 | 3.1762e-05 | 3.8157e-05 | **1.201** | 4 | 3 | 2 |
| 3 | 4WXrvNPH | 2.0 | c+0 | 3.1762e-05 | 4.2703e-05 | **1.344** | 5 | 6 | 8 |
| 4 | F7YM1Tjm | 2.5 | c+1 | 3.2751e-05 | 5.8158e-05 | **1.776** | 7 | 3 | 6 |
| 5 | 3xHxWfca | 5.0 | c+1 | 3.7921e-05 | 3.9654e-05 | **1.046** | 5 | 5 | 1 |

## Aggregate

- **Fill ratio: median 1.33, mean 1.34, range 1.05–1.78.**
- Marginal price at our execution vs floor: median 1.32x.
- Successful buyers landing *before us*: 4,4,5,7,5 (median **5**). We are never 1st (that's the dev) or 2nd on any probe.
- Rank within our own landed slot: 1,3,6,3,5 (median **3**) — we are usually not even first among same-slot public buyers.
- Create→land: 4 of 5 at create+1; probe 3 landed in the create slot itself but still 6th.

## What the ordering shows (per probe)

**Probe 1 (A8FjoUQX, dev 3.0 SOL, create 456917832, land create+1):**
  - seq0 slot 456917832 blk-idx  1168 CREATE+DEVBUY `Dde9n8` tokens 96,449,438,144,093 solIn 2,964,456,482 margPost 3.3754e-05
  - seq1 slot 456917832 blk-idx  1169 buy `7cWpF6` tokens 55,211,339,135,631 solIn 1,975,308,641 margPost 3.7921e-05
  - seq2 slot 456917832 blk-idx  1170 buy `AaNmgc` tokens 37,478,205,611,749 solIn 1,481,481,480 margPost 4.1205e-05
  - seq3 slot 456917832 blk-idx  1171 buy `3uuGdt` tokens 34,548,313,319,831 solIn 1,481,481,480 margPost 4.4626e-05
  - seq4 slot 456917833 blk-idx   225 buy `FRZh63` tokens 221,261,564,130 solIn 9,953,086 margPost 4.4649e-05 **<- US**

**Probe 2 (U5jNL2jH, dev 2.0 SOL, create 456918320, land create+1):**
  - seq0 slot 456918320 blk-idx   571 CREATE+DEVBUY `2k7K6N` tokens 66,285,714,223,523 solIn 1,976,802,161 margPost 3.1762e-05
  - seq1 slot 456918320 blk-idx   572 buy `5syhKS` tokens 30,163,723,860,403 solIn 987,654,320 margPost 3.3754e-05
  - seq2 slot 456918321 blk-idx    85 buy `8ptvsh` tokens 34,111,974,730,820 solIn 1,202,355,382 margPost 3.6242e-05
  - seq3 slot 456918321 blk-idx    87 buy `2vzVZe` tokens 20,268,476,700,377 solIn 750,720,000 margPost 3.7853e-05
  - seq4 slot 456918321 blk-idx   231 buy `FRZh63` tokens 260,845,359,858 solIn 9,953,086 margPost 3.7874e-05 **<- US**
  - seq5 slot 456918322 blk-idx   101 buy `6SHf2w` tokens 37,523,651,895,265 solIn 1,481,481,480 margPost 4.1156e-05

**Probe 3 (4WXrvNPH, dev 2.0 SOL, create 456918406, land create+0):**
  - seq0 slot 456918406 blk-idx    18 CREATE+DEVBUY `EGGRb3` tokens 66,285,714,223,523 solIn 1,976,802,161 margPost 3.1762e-05
  - seq1 slot 456918406 blk-idx    19 buy `4ifVug` tokens 58,572,467,482,603 solIn 1,975,308,641 margPost 3.5808e-05
  - seq2 slot 456918406 blk-idx    20 buy `3bAUoA` tokens 39,785,352,509,097 solIn 1,487,012,344 margPost 3.9013e-05
  - seq3 slot 456918406 blk-idx    21 buy `6m9cXD` tokens 31,977,055,088,099 solIn 1,293,037,036 margPost 4.1912e-05
  - seq4 slot 456918406 blk-idx   642 buy `8QvkXm` tokens 4,685,497,949,142 solIn 197,433,366 margPost 4.2364e-05
  - seq5 slot 456918406 blk-idx   822 buy `FRZh63` tokens 233,075,048,185 solIn 9,953,086 margPost 4.2386e-05 **<- US**

**Probe 4 (F7YM1Tjm, dev 2.5 SOL, create 456918640, land create+1):**
  - seq0 slot 456918640 blk-idx   864 CREATE+DEVBUY `5NU14d` tokens 81,596,958,099,513 solIn 2,470,629,321 margPost 3.2751e-05
  - seq1 slot 456918640 blk-idx   912 buy `GBZe32` tokens 163,660,184,649,362 solIn 6,469,506,173 margPost 4.6982e-05
  - seq2 slot 456918640 blk-idx   914 buy `CUQqcZ` tokens 58,601,264,198,138 solIn 2,985,925,926 margPost 5.4414e-05
  - seq3 slot 456918640 blk-idx   966 buy `HxcdEi` tokens 13,376,375,483,934 solIn 746,481,481 margPost 5.6357e-05
  - seq4 slot 456918640 blk-idx   969 buy `Fv5JTU` tokens 7,804,804,270,776 solIn 444,444,443 margPost 5.7539e-05
  - seq5 slot 456918641 blk-idx   235 buy `4xxXgN` tokens 857,261,183,284 solIn 49,382,715 margPost 5.7671e-05
  - seq6 slot 456918641 blk-idx   397 buy `J5b8YG` tokens 171,216,451,272 solIn 9,876,542 margPost 5.7698e-05
  - seq7 slot 456918641 blk-idx   504 buy `FRZh63` tokens 171,137,992,607 solIn 9,953,086 margPost 5.7724e-05 **<- US**
  - seq8 slot 456918641 blk-idx   727 buy `2YprUs` tokens 1,707,076,881,975 solIn 98,765,431 margPost 5.7989e-05
  - seq9 slot 456918641 blk-idx   728 buy `DDzUi7` tokens 410,001,796,743 solIn 23,788,696 margPost 5.8053e-05
  - seq10 slot 456918641 blk-idx   825 buy `6wuFPg` tokens 417,086,028,966 solIn 24,226,624 margPost 5.8118e-05
  - seq11 slot 456918641 blk-idx   835 buy `B7auoj` tokens 427,222,241,978 solIn 24,843,559 margPost 5.8185e-05
  - seq12 slot 456918641 blk-idx   840 buy `9paMww` tokens 415,739,481,587 solIn 24,203,235 margPost 5.8250e-05
  - seq13 slot 456918641 blk-idx   938 buy `haqqiU` tokens 169,516,073,435 solIn 9,953,086 margPost 5.8276e-05
  - seq14 slot 456918641 blk-idx  1089 buy `3Vggwn` tokens 677,292,012,683 solIn 39,506,172 margPost 5.8383e-05
  - seq15 slot 456918642 blk-idx   418 buy `nya666` tokens 1,560,887,133,285 solIn 91,320,932 margPost 5.8629e-05
  - seq16 slot 456918642 blk-idx   739 buy `CuATPP` tokens 8,328,241,911,088 solIn 493,827,159 margPost 5.9970e-05

**Probe 5 (3xHxWfca, dev 5.0 SOL, create 456919487, land create+1):**
  - seq0 slot 456919487 blk-idx  1114 CREATE+DEVBUY `bwamJz` tokens 151,660,777,334,045 solIn 4,939,765,124 margPost 3.7921e-05
  - seq1 slot 456919488 blk-idx   343 buy `zWvdPm` tokens 130,206,179,098 solIn 4,976,543 margPost 3.7932e-05
  - seq2 slot 456919488 blk-idx   589 buy `AMDEmV` tokens 5,178,240,620,216 solIn 199,061,728 margPost 3.8362e-05
  - seq3 slot 456919488 blk-idx   651 buy `7PtVk5` tokens 2,567,350,775,019 solIn 99,530,864 margPost 3.8578e-05
  - seq4 slot 456919488 blk-idx   738 buy `9T4hET` tokens 8,873,499,768,752 solIn 345,679,011 margPost 3.9338e-05
  - seq5 slot 456919488 blk-idx   903 buy `FRZh63` tokens 250,996,038,598 solIn 9,953,086 margPost 3.9360e-05 **<- US**
  - seq6 slot 456919488 blk-idx  1457 buy `HYKRAt` tokens 1,252,894,003,835 solIn 49,382,715 margPost 3.9470e-05

## Verdict — is the intra-slot race winnable with our current warm path?

**No, not with the current path.** Median fill ratio **1.33** sits far above the ~1.0–1.1 "winnable" band and far above the value study's +EV bound (fill within ~0.6 slot of the floor). We pay a median ~33% premium to the floor because a median of 5 buyers fill ahead of us on every mint.

**Where the winners sit:** the fastest co-snipers occupy the *create slot itself*, in block indices immediately adjacent to the create instruction — e.g. probe 1 create at idx 1168, co-snipers at idx 1169/1170/1171; probe 3 create at idx 18, co-snipers at idx 19/20/21. That back-to-back adjacency = they are **bundled with the create** (same Jito bundle / same-leader pipeline), landing at ~0 slot gap and ~$0 extra. They are not outbidding us — they are structurally ahead. This matches the run48e finding exactly.

**What our warm send path actually buys us:** it wins the race *among the public (non-bundled) traffic* — in probe 1 we are idx 225, first of the public wave in create+1, beating ~12 submissions that failed on slippage. But first-of-public is still a full slot + a bundle behind the floor. And it is not even reliable: in 4 of 5 probes we were 3rd–6th within our own landed slot (only probe 1 we were 1st in-slot).

**Why ratios vary — competition, not our latency.** Probe 5 (ratio 1.05, best): only the dev bought in the create slot and followers were tiny → we land near floor. Probe 4 (ratio 1.78, worst): a 6.5-SOL whale plus 6 buyers front-ran inside the create slot, pumping the price +76% before create+1. Our fill quality is dominated by how many bundled/same-slot buyers a given mint attracts — which send latency does not control.

**Implication / lever:** to be +EV we must land *inside the create slot adjacent to the create* (co-located in the creator's bundle or in-shred insertion), not merely submit fast on the public path. Tips/size are not the lever (winners pay ~$0); same-slot placement is.
