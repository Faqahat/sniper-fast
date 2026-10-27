# Are the dumpers related to the dev? (owner 10-25 ~16:45 PKT)

**Short answer:**
- **Often, yes.** The creator itself made 27 of the 112 dumps we bought live, and about half of IMIT1's picks in the 61 h replay.
- **But a creator dump is not a bad trade.** In the 61 h replay, creator dumps pay, and skipping them would halve profit on every day.
- **What hurts is the creator and its wallets selling *while we hold*.**
  - That happened in **13 of 58 losers but only 3 of 54 winners** (live, MEASURED).
  - We can trace who funded the sellers for only about a quarter of the selling. The rest are busy bots or wallets older than our RPC's 3.4-day history.

Data:
- **Live:** 112 closed fills, runs dip_r14–r16 and dip_ams_r13/14/16/17. Losers: 58 fills, −1.440 SOL. Winners: 54 fills, +1.547 SOL.
- **Recording:** raw recording run_20261024_1425, covering all 104 tokens' launches.
- **Funding:** read-only RPC funding trace of 453 wallets.
- **Replay:** 61 h (R1–R4, 0.55 SOL, all costs, near leaders, one position per server, 5-slot hold).


**Caveat (added 17:40 PKT):** the VM1 check (ops/dip/vm1/VERIFY.md) measured that our landing replays over-predict real fires by
~5 mSOL per fire (M2 fires ~+1.9, IMIT1 ~+6.6), because we land later on dumps that bounce. So the 75 ms creator-dump numbers
above are about break-even after that correction (M2 +0.0035/fill − 0.0019; IMIT1 +0.0068 − 0.0066). The "don't skip" ranking is
a same-replay comparison and should hold, but treat the absolute numbers as optimistic.

## 1. The dump we bought after: who sold it
Live, MEASURED:

| Dump made by | Fills | P&L SOL | Win rate |
|---|---|---|---|
| The creator itself (create signer / creator) | 27 | −0.104 | 9/27 |
| Creator-linked wallet (create bundle, funded by or with the dev, funder network) | 8 | +0.145 | 4/8 |
| Launch sniper bot (bought ≤ 10 slots after the launch, trades many tokens; e.g. dKMjeGJ4) | 17 | −0.202 | 7/17 |
| Fresh launch wallet (≤ 10 slots, ≤ 5 tokens in 24 h) | 2 | +0.016 | 2/2 |
| Everyone else | 58 | +0.251 | 32/58 |

The engine's `dev` flag on fire records means "dev-list token", not "the creator dumped". Dev-list fills: 16, **+0.100 SOL**.

61 h replay (MEASURED in replay; IMIT1 was fit on data before 10-23 06:00):

| Picks | Creator-dump fills | SOL at 35 / 50 / 75 ms | Skip creator + insider dumps (SOL at 50 ms) |
|---|---|---|---|
| IMIT1 top4 | 328 of 679 | +8.7 / +5.9 / +2.2 | +13.8 → **+7.4** (worse on all 4 days) |
| M2 gate | 310 of 1,203 | +6.9 / +4.0 / +1.1 | +24.4 → **+16.8** (worse on all 4 days) |

- Creator dumps are M2's thinnest edge: +0.013 per fill at 50 ms, against +0.025–0.036 for dumps by bots or wallet families.
- So they are the first to turn negative when our landing is slow (INFERRED from the per-latency rows).
- Buying every envelope dump loses for every seller type. The model picks are what make the money.

## 2. Who sold while we held (live)
Sell SOL by others between our buy and our sell:

| | Creator | Creator-linked | Fresh launch wallets | Launch snipers | Everyone else |
|---|---|---|---|---|---|
| Losers (136 SOL) | 16% | 4% | 5% | 17% | 59% |
| Winners (53 SOL) | 5% | 3% | 0% | 14% | 78% |

- The creator or a linked wallet sold during the hold in **13/58 losers vs 3/54 winners**.
- Traceability of the losers' selling:

| Seller wallet | SOL | Share |
|---|---|---|
| Busy bots (> 4,000 txs) | 59 | 44% |
| Older wallets (funder outside our RPC's ~3.4-day history) | 45 | 33% |
| Young wallets (funder seen) | 31 | 23% |

  So "everyone else" means "no link found", not "proven unrelated".

## 3. Funding networks found (MEASURED; verify on Solscan)

| Private funder | What it funded |
|---|---|
| 791eGAi3… | 6 wallets. 4 of them sold into our hold on **HEncXe** (−0.025), whose dump came from a create-bundle wallet. That loss was the creator's own group. |
| 2UPzAimP… | 4 wallets, incl. dev 5KhMUK (creator of DJasC1, E9jEzy, EfKB6n; all three were our losers) and dev 5s1Wc7 (CyaaPF, sold 2.25 into our pre-send hold). One operator running several dev wallets. |
| 4hjgcRxa… | 2 devs (8hGKQA, EDHxyc), plus the dumper on 36JuJo and a seller on 3xu825 |
| 3uxuYqju… | A dev (Hhey99), plus the dumpers on 7AJSXi and E9jEzy |
| FykEV8eV… | 2 devs (FzeP2j, 8WAAk1) |

- Exchange hot wallets break the trail. 5tzFkiKs… funded 6 traced wallets incl. 3 devs, 8szGUCBx… 5 devs, 3umDofh3… 4 devs; AxiomRXZ… also appears.
- **Biggest loser, Az6Arr7o (−0.118):**
  - The dump came from dKMjeGJ4, a big launch-sniper bot exiting.
  - During our 5-slot hold, the creator (1.29 SOL) and 7 wallets that bought 3–7 slots after the launch all sold together. Each of those wallets traded only 2–6 tokens in 24 h.
  - The ones we could trace were funded through exchange hot wallets: B48kNVXs ×2 and iGdFcQoy. That looks like the creator's group (INFERRED), but it can't be proven past the exchange.

## 4. What it means
- Don't skip creator dumps. The replay says they pay, and the dev list is positive live.
- The risk is a coordinated exit after our buy, and we found no entry-time signal for it (§5).

## 5. Bag still held at the dump (61 h replay): no filter found
Picks split by how much of its bag the creator and the create-slot insiders had sold by the time of the dump (sold tokens / bought tokens). SOL at 35 / 50 / 75 ms:

| Picks | Creator sold all | Creator sold part | Creator sold none (or no bag) |
|---|---|---|---|
| IMIT1 top4 | 383 fills +16.7 / +8.9 / +3.9 | 219 fills +4.4 / +3.7 / +1.9 | 77 fills +2.6 / +1.5 / +0.8 |
| M2 gate | 870 fills +30.5 / +19.0 / +10.8 | 195 fills +4.8 / +3.6 / +1.9 | 138 fills +4.5 / +2.4 / +1.3 |

Skip tests (SOL at 50 ms):

| Skip rule | IMIT1 | M2 |
|---|---|---|
| None (today) | +13.8 | +24.4 |
| Creator still holds some | +10.1 | +20.9 |
| Creator sold nothing and the dump isn't the creator's | +12.3 | +22.1 |
| Insiders sold part | +10.6 | +17.0 |

- **Every skip rule loses money at every latency.** The "bag still held" picks earn a bit less per fill, but they are still positive.
- Most of our picks come after the creator has already sold everything (M2: 870 of 1,203 fills).
- **Verdict:**
  - The creator's group selling into our hold is real in the live losers, but we found no entry-time signal for it.
  - Keep buying creator dumps; don't add a creator/insider filter.
  - The lever stays landing speed: creator dumps are the thinnest edge and the first to flip at slow landing.

Files:
- loss_causes.py (LC_DUMP → out/fills.json)
- dev_link_scan.py (out/scan1.json, scan2.json)
- dev_link_fund.py (out/fund.json)
- dev_link.py (out/dev_link.txt, dev_link.json)
- replay_seller_type.py, replay_bag_held.py (out/*.txt)
