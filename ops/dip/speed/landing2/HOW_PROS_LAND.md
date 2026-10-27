# How the pros land faster than us (chain forensics)

10-25, finished ~19:55 PKT. Read-only: local recordings, our run logs, read-only RPC (≈ 910 `getTransaction`, 2 schedule/gossip calls), public docs. Nothing sent, no server or config touched.

- **Window:** recordings R3 + R4, **10-23 19:26 → 10-25 19:02 PKT** (47.6 h): 7.52 M curve trades, 498 k sells ≥ 0.5 SOL.
- **Dump** = a curve sell ≥ 1 SOL that drops the price ≥ 4%. **Reaction** = a wallet's first landed buy (failed ones too) ≤ 3 slots after it.
- **Our side:** 481 live dip fires (FRA runs 1–16, AMS runs 9–17), each matched to its dump and to our landed copy on chain.
- **Labels:** **MEASURED** = counted on chain (block positions, order, routes, tx contents). **INFERRED** = a model or my reading.
  - All "ms" are a **block clock** (INFERRED). It uses position in the block, with block 1 of a leader's 4-slot window ≤ 144 ms and blocks 2–4 200 ms.
  - Checked against our own feed timing on 13 fires: median error −2 ms, typical error ±17 ms per fire. Medians over many dumps are fine; single cases are rough.
- **Route** = the tip service paid by the copy that landed. "none" = no known tip: a direct TPU copy, a no-tip staked RPC, or an unknown service.
  - With a durable nonce only one copy can land, so the route is **the copy that won the bot's own race**.

---

## Verdict

1. **No single pro is much faster than us. The crowd is.**
   - On the same dumps, each top pro lands about when we do. Median ms, pro vs us: HkQ7 45 vs 47, haqq 49 vs 52, 6n2c 51 vs 50.
   - Each of them is ahead of us only 43–45% of the time (MEASURED order).
   - On a typical dump we fire on, 1–3 reactive bots land before us. The first one lands at a median **33 ms**, we land at **50 ms**.
   - We are ahead of every known reactive bot on only **27%** of our fires (MEASURED).
2. **Our feed and engine are not the gap.**
   - Through the same relay, on the same leader type, we land as fast as the pros. Nozomi on BAM: us 29, pros 36 ms. Nozomi on Harmonic: us 31, pros 36 ms. (Positions MEASURED, ms INFERRED.)
   - So seeing the dump, deciding and reaching the relay is at par. The other agent's waterfall (WHERE_TIME_GOES.md) finds the same.
3. **The gap is which route reaches each kind of leader.**
   - Pros send every trade through **2–10 services at once**: one durable nonce, **one tip per copy**. Different services win on different leaders. We send 4 copies, and on Jito and Firedancer leaders all 4 are slow.
   - **Jito leader behind a relayer** (6% of slots, mostly in AMS):
     - soyas, glaive and solami land at **~19–22 ms**.
     - No-tip TPU copies wait the relayer's 50 ms hold and land at ~92 ms.
     - **We land at ~94 ms.**
   - **Jito leader with its own TPU** (17% of slots):
     - glaive 24, falcon 29, soyas 30, flashblock 32, keyed helius 34 ms.
     - **We land at ~58 ms.** On Jito our helius copy is Sender Max (0.001 tip, top-of-block buffer): its fills landed at ~120 ms. Our swqos-only helius copy (used on BAM / Harmonic) has no API key and gets rate-limited.
   - **Firedancer** (7% of slots): 0slot, jito, flashblock and astralane land at 36–40 ms. **We land at ~69 ms.**
   - **BAM (37%) and Harmonic (30%):** nozomi, speedlanding and glaive all land at ~35–38 ms. We are at par on fills, and only ~6–7 ms behind the first bot.
4. **Location: all pros are EU-based.**
   - FRA and AMS leaders get the same speed from them (within ~3 ms), so I cannot say which city.
   - Three operators also land fast on **US** leaders (fastest 10% at 21–25 ms): the 11-wallet "hicu" family, GKd5EMzR and haqqiUUX.
   - The hicu family and GKd5 do the same on **Asia** leaders (fastest 10% at 20–25 ms). They run engines in more regions.
   - About **1/3 of all slots** have far leaders. HkQ7 never trades them; we lose there (fastest 10%: 87 ms on US leaders, 134 on Asia).
5. **Fees are not why they win.**
   - Winners paid a **lower** CU price than we do: median 2.0 M vs our 5.0 M µL/CU, plus a ~0.001 SOL tip.
   - Fee still orders txs inside BAM's 20 ms rounds and Harmonic's 50 ms buffers, so keep it as a lever to test.

## What to copy, and what each item buys

ms = median landing after the dump, on the dumps it applies to. Path speeds are the pros' landed copies, pooled over 7–25 wallets (MEASURED). That we would get the same speed is INFERRED.

| # | Copy this | Where (share of all slots) | ms it buys there | Needs |
|---|---|---|---|---|
| 1 | **Relayer-skipping services** on relayer-fronted Jito leaders: **soyas, glaive** (solami: 1 wallet only); Jito block-engine `sendTransaction` (jito-tx) as backup | Jito-relayer 6.2% (AMS 4.4%, FRA 1.3%) | **94 → ~22–45: −50 to −70** | Sign-up / keys for soyas, glaive, solami. Tips 0.0001 (glaive, solami) to 0.001 (soyas) per landed buy; failed copies pay nothing. No stake needed; access is by key (no allowlist seen in their docs). FRA + AMS endpoints exist. jito-tx is already staged for the probes. |
| 2 | **Fast routes for Jito own-TPU leaders:** glaive, falcon, flashblock, soyas, plus **helius swqos-only with our API key at a 0.0002 tip** (haqq's setup) in place of Sender Max 0.001 | Jito-own 16.8% | **58 → ~25–35: −20 to −30** | Free Helius API key (sign-up). Glaive / falcon / soyas accounts. flashblock is staged (FRA). |
| 3 | **Firedancer routes:** 0slot, flashblock, astralane, jito-tx | FD 7.0% | **69 → ~36–40: −30** | 0slot account (min tip 0.001). Astralane is already configured (free tier: 5 tx/s, 0.001 tip). |
| 4 | **More copies on BAM / Harmonic:** speedlanding, soyas, glaive, astralane next to nozomi | BAM 37.4% + Harmonic 30.2% | **−3 to −7** (closes our 5.6 / 7.4 ms median lag to the first bot; INFERRED) | speedlanding (staged, min tip 0.001). Astralane (configured). |
| 5 | **Engines in more regions:** New York, then Tokyo / Singapore | far leaders ≈ 1/3 of slots | fastest 10%: **87 / 134 → ~21–25**. Makes these slots playable instead of skipped (MEASURED for hicu / GKd5 / haqq) | Money and location: a server, shred feed and relay keys per region. |
| 6 | **Tx shape:** CU limit ~60–75 k (now 100 k); `SetLoadedAccountsDataSizeLimit`; create the token account with CreateAccountWithSeed, not 2 ATA-program calls; optional lookup table (haqq's tx is 562 B, ours 967 B) | all slots | ≤ 1–3 ms (INFERRED: better fee per CU inside BAM / Harmonic windows), and cheaper buys | Engine change, owner's OK. Free. |
| 7 | **Fee per copy** (hicu style): the no-tip copy bids by CU price (~15 M µL); tip copies use CU price 0 plus the tip | BAM / Harmonic / FD | small, same cost (INFERRED) | Engine change. |
| 8 | **Skip Rakurai:** we land at 203 ms there vs the first bot's 37 | 1.1% | avoids lost buys | Already a dip14/15 flag. |
| 9 | **Late dumps** (last quarter of the block; 16% of our fires): winners made the dump's block only 30% of the time, so the race is in the **next** leader's block. Also route by the next leader. | 16% of fires | not measured | Engine change. |

**Together (INFERRED, block clock):** items 1–4 would put us ahead of every known reactive bot (our 58-wallet list) on **~56%** of our fires (now 27%). Items 1–3 alone give ~41%. Wallets outside the list also buy, so the real first-place rate is lower. The fill and SOL effect needs the guard model in WHERE_TIME_GOES.md.

**Probe order (fits PROBES_V2.md):**
1. P1 on Jito: add **glaive and soyas**. They need accounts and are not in the staged list.
2. jito-tx, speedlanding, flashblock and keyed helius-swqos are already staged.
3. On Firedancer leaders, add **0slot** and astralane.
4. Do not judge "none" paths on relayer-fronted Jito leaders: they always wait the 50 ms hold.

---

## E1. Same relay, same leader type: us vs the pros (is our upstream slower?)

Same-slot landings, dumps in the first 3/4 of their block. Median ms (p25) (n). The pros are pooled: the 8 pros plus the hicu family.

| Leader | Route | Us | Pros | Best single pro |
|---|---|---|---|---|
| BAM | nozomi | **28.9** (24.5) n=13 | 35.8 (23.5) n=628 | HkQ7 35.2 |
| BAM | none | 39.3 (29.0) n=73 | 44.5 (29.9) n=3459 | – |
| Harmonic | nozomi | **31.2** (23.6) n=24 | 36.0 (26.3) n=1159 | haqq 33.4 |
| Harmonic | none | 51.4 (38.4) n=65 | 47.0 (32.4) n=3257 | – |
| Jito-own | none | 53.2 (39.4) n=48 | 46.7 (31.9) n=1505 | – |
| Jito-own | helius | **50.0** n=7 (Sender Max) | 31.0 (21.3) n=691 | 8PgC 22.5 |
| Jito-relayer | helius | 73.6 n=3 | 46.6 (35.1) n=338 | HkQ7 34.6 |
| Jito-relayer | none | **105.1** n=14 | 88.2 (41.4) n=332 | – |
| Firedancer | none | 45.3 n=11 | 47.0 (29.5) n=1072 | DF7e 29.9 |

On the same relay we are not slower. We lose on the routes we don't have (E2), and with the helius tier we use on Jito.

## E2. Which route lands first, per leader type (30+ reactive bots pooled, MEASURED)

When a route was the copy that won the bot's own race: median ms (p10), n, number of wallets.
This mixes path speed with bot quality.

| Leader | Fastest routes | Middle | No tip ("none") |
|---|---|---|---|
| **Jito-relayer** | solami 18.5 (9.5) n=53 w=1 · **soyas 21.7** (10.3) n=141 w=14 · **glaive 22.0** (14.0) n=25 w=9 | speedlanding 39.7 · blockrazor 46.5 · jito 46.6 · bolt 47.3 · astralane 48.2 · helius 49.1 · nozomi 50.2 | **92.2** (21.4) n=592 |
| **Jito-own** | **glaive 24.4** (14.9) n=63 · falcon 28.9 · soyas 30.2 · unknown D1Mc 31.3 · flashblock 31.7 · helius 34.3 (15.9) n=1214 | Node1 36.8 · blockrazor 40.5 · stellium 41.0 · landx 41.2 · nozomi 43.4 · speedlanding 45.4 · astralane 47.2 | 48.0 (20.3) n=2731 |
| **BAM** | nozomi 36.4 (17.8) n=654 · speedlanding 37.4 · glaive 38.1 | 0slot 40.2 · jito 40.3 · soyas 41.1 · bolt 42.6 · astralane 42.8 · helius 44.2 | 44.8 (20.4) n=7211 |
| **Harmonic** | speedlanding 35.2 (17.4) n=1071 · soyas 35.6 · nozomi 36.4 (19.3) n=1190 | astralane 39.4 · 0slot 40.0 · flashblock 43.2 · helius 44.0 | 46.7 (22.0) n=6841 |
| **Firedancer** | unknown Node1 23.8 (2 wallets) · 0slot 35.7 · jito 35.9 · flashblock 39.2 · astralane 40.0 | soyas 44.3 · speedlanding 45.1 · helius 45.7 · nozomi 48.1 | 48.1 (17.3) n=1856 · landx 83.7 |

What our own copies did (nonce era, fires r11+). Landed copy, result: median ms (n).
- **Jito-own:** helius fill 119.5 (15); staked-rpc fail 61.5 (22); nozomi fail 59.0 (8).
- **Jito-relayer:** nozomi fail 111 (9); helius fill 73.6 (3).
- **BAM:** nozomi fill 33.6 (21); staked-rpc fail 38.4 (26).
- **Harmonic:** nozomi fill 32.0 (28); staked-rpc fail 65.0 (46).
- **Firedancer:** landx 38.5 fail / 62.6 fill (3 + 3).

## E3. The pros, one line each (48 h, MEASURED; ms INFERRED)

| Wallet | Reactions | Same slot | Positions after dump p25 / p50 | ms p25 / p50 / p75 | Landed routes | CU price µL | CU limit |
|---|---|---|---|---|---|---|---|
| **OURS-FRA** (fires) | 357 | 75% | 66 / 100 | 34 / 52 / 91 | none 65%, nozomi 10%, helius+landx+nozomi 7% | 5.0 M | 100 k |
| **OURS-AMS** (fires) | 104 | 81% | 50 / 82 | 26 / 38 / 66 | none 53%, bolt+helius+nozomi 13%, nozomi 12% | 5.0 M | 100 k |
| HkQ7hMjy | 6047 | **78%** | 54 / 82 | **27 / 42 / 66** | none 64%, nozomi 27%, helius 4%, stellium / soyas / flashblock 1% each | 1.70 M | 76 k |
| haqqiUUX | 8101 | 61% | 59 / 94 | 34 / 58 / 112 | helius 53% (0.0002 tip), none 35%, 0slot 5%, astralane 4% | 1.78 M | 66 k |
| DYXDDrZC | 2309 | 61% | 53 / 88 | 32 / 58 / 119 | none 34%, speedlanding 23%, helius 15%, astralane 13%, unknown Node1 5% | 2.48 M | 115 k |
| 8PgC4ngp | 2286 | 63% | 47 / 76 | 28 / 51 / 108 | none 28%, speedlanding 27%, astralane 25%, helius 8%, Node1 3% | 3.26 M | 55 k |
| 6n2cCJrr | 3762 | 63% | 59 / 93 | 36 / 60 / 116 | none 73%, astralane 25% (0.003 tip) | 1.11 M | 90 k |
| 9u5f8WMf | 202 | 65% | 67 / 102 | 33 / 57 / 105 | speedlanding 39%, bolt 32%, astralane 12% (0.002 tips) | 0.50 M | 120 k |
| G9G3dCBG | 1989 | 67% | 68 / 108 | 38 / 64 / 108 | none 84%, speedlanding 13% | 2.00 M | 65 k |
| 5w8xtjc6 | 1000 | 68% | 60 / 96 | 34 / 58 / 115 | none 59%, nozomi 18%, jito 15%, helius 6% | 2.58 M | 62 k |
| hicu family (11 wallets) | 11032 | 66% | 48 / 78 | **28 / 49 / 100** | none 69%, helius 10%, astralane, landx, glaive, soyas, bolt, nozomi, unknown D1Mc / Sp | 14.6 M on no-tip copies | 72 k |
| GKd5EMzR | 6297 | 67% | 51 / 82 | 30 / 51 / 98 | none 88%, flashblock 4%, blockrazor 3%, jito 3%, solami 2% | 2.15 M | 53 k |

Not in the tables:
- **dKMjeGJ4** made 2 buys in our dump window in 48 h. It is a launch sniper, not a dip bot.
- **CZ77onJz** and the other "instant" wallets land 1–6 positions after the dump. They are pre-sent attempts (INSTANT_BOTS.md), not faster reactions.
- **hicu family** = DF7eRXHn, EprLoV21, HLU8QbLd, 5TFXfcHb, D1QuMgpv, EorGEbt1, EJX629cp, 4oN18efp, 6vB9VfGp, 5mWe9kLZ, J3gZFpvs. They share one template: no-tip copy at 13–16 M µL, CU limit ~70–75 k, own program 41Pr4X…, the same 3 nonce accounts each, and the same route mix.

### Copies per trade and fee per route (MEASURED)

| Wallet | Routes seen (≥ 1% of its buys) | Nonce accounts in sample | Fee shape per copy |
|---|---|---|---|
| HkQ7 | 5 (9 seen) | 26 / 38 txs | one CU price (1.7 M) on all copies; tips: nozomi 0.001, helius / flashblock / jito 0.0003, soyas / stellium 0.001 |
| haqq | 5 | 34 / 40 | helius 0.0002 + 1.8 M µL; astralane / nozomi 0.002 + 0.18 M µL |
| DYXD | 8 | – | every copy 2.48 M µL + 0.001 tip |
| 8PgC | 7 | 15 / 40 | every copy 3.26 M µL + 0.001 tip |
| hicu | 9 | 3 / ~37 each | **no-tip copy 15 M µL; helius / bolt / soyas copies CU price 0 + 0.0011 tip; astralane / glaive 13–14 M µL + 0.0001; landx / nozomi 1.3 M + 0.001** |
| GKd5 | 6 | 19 / 38 | no-tip 2.15 M µL; flashblock / blockrazor / solami 0.29 M + 0.0001 |
| ours | 4 (nozomi, helius-swqos, landx, staked-rpc) | 8 | 5 M µL on every copy + tip per path (nozomi 0.001, helius-swqos 0.0002, landx 0.001, staked 0) |

The route count is a lower bound: copies that never land leave no trace on chain.

## E4. Tx anatomy (getTransaction, ~30–40 landed reaction buys per wallet, MEASURED)

| Wallet | Durable nonce | Version | Size B | Keys | Lookup table | CU limit | CU price µL | Loaded-data limit set | Tips per tx | Tip vs buy | Lighthouse guard | Own program |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| OURS-FRA | 75% (100% since r11) | v0 | 967 | 23 | no | 100,000 | 5,000,000 | no | 1 (older runs up to 4) | before | yes | – |
| HkQ7 | 100% | legacy | 1150 | 23 | no | 76,459 | 1,700,258 | yes | 1 | after | yes | – |
| haqq | 100% | v0 | **562** | 21 | **yes** | 65,545 | 1,830,748 | yes | 0–1 | after | no | haqqqM… |
| 8PgC | 100% | v0 | 1076 | 22 | no | 54,539 | 3,259,620 | yes | 1 | after | no | – |
| 6n2c | 100% | legacy | 1049 | 22 | no | 89,999 | 1,111,123 | no | 0–1 | before | yes | – |
| 9u5f | 100% | legacy | 997 | 24 | no | 120,000 | 500,000 | yes | 1 | after | no | HQLDfq… |
| G9G3 | 100% | legacy | 1088 | 22 | no | 65,000 | 2,000,000 | yes | 1 | before | yes | – |
| 5w8x | 100% | legacy | 1104 | 22 | no | 61,920 | 2,583,979 | yes | 1 | after | yes | – |
| DF7e / EprL / HLU8 (hicu) | 100% | legacy | 1029 | 23 | no | 70–74 k | 1.3–1.5 M (median of all copies) | no | 0–1 | after | ~35% | 41Pr4X… |
| GKd5 | 100% | v0 | 839 | 20 | no | 53,456 | 2,037,292 | no | 0–1 | after | no | – |
| EMKY / BUkp | 100% | legacy, some **v1** | 1001–1050 | 21 | no | 56–62 k | 2.8–3.2 M | 82–87% | 1 | before | no | – |

- Every pro in the main list uses **one tip per copy and a durable nonce**, rotating many nonce accounts (HkQ7 26, haqq 34).
- Most create the token account with **CreateAccountWithSeed + InitializeAccount3** (system instruction 3; seen for HkQ7, 8PgC, hicu). We call the ATA program **twice**.
- Spot checks (Solscan):
  - HkQ7's soyas buy: nonce → CU limit / price / loaded-data → 2 Lighthouse asserts → CreateAccountWithSeed + token init → buy → soyas tip ([4j239dSn…](https://solscan.io/tx/4j239dSnrjDKYqkbqnKLrCqf8xMxuzGahCzGwPim9K6J5Z9DH8ojhDGe4WieG57xf8Nv1dJQhWb6vh3SrN1rCKNt)).
  - GKd5's solami buy has 5 instructions in total: nonce, CU limit, CU price, buy, tip 0.0001 ([2RPHTqAh…](https://solscan.io/tx/2RPHTqAhnBEpL5SA6sn1Js5ZuvoADJRVWXs5XZ5ySuq1XMNAafN5eHEuT9Y9DuNd42gtGCbcqTYkrCchGnZr3y5g)).

## E5. By leader client: median ms · same-slot share (n)

| Wallet | Jito-own | Jito-relayer | BAM | Harmonic | Firedancer | Rakurai |
|---|---|---|---|---|---|---|
| OURS-FRA | 63 · 66% (97) | 87 · 100% (13) | 42 · 74% (97) | 47 · 83% (123) | 66 · 73% (22) | – (5) |
| OURS-AMS | 27 · 80% (10) | **94 · 47% (19)** | 32 · 94% (49) | 31 · 80% (25) | – | – |
| HkQ7 | 44 · 73% (1067) | 68 · 69% (440) | 38 · 83% (1724) | 42 · 78% (2203) | 39 · 85% (470) | 102 · 44% (82) |
| haqq | 57 · 60% | 72 · 58% | 62 · 56% | 51 · 65% | 54 · 72% | 88 · 47% |
| 8PgC | 52 · 61% | 56 · 61% | 59 · 57% | 44 · 73% | 76 · 56% | 25 · 76% |
| hicu family | 52 · 63% | **46 · 68%** | 52 · 62% | 43 · 69% | 53 · 71% | 40 · 68% |
| GKd5 | 63 · 60% | 64 · 61% | 48 · 67% | 48 · 72% | 49 · 74% | 91 · 46% |

The fastest 10% of each wallet's same-slot reactions (dumps in the first 3/4 of the block), in ms:

| Wallet | Jito-own | Jito-relayer | BAM | Harmonic | Firedancer |
|---|---|---|---|---|---|
| **us** | 23.0 | **58.1** | 21.0 | 20.7 | 23.2 |
| HkQ7 | 17.1 | 16.1 | 19.4 | 21.1 | 17.5 |
| 8PgC | 15.2 | 15.6 | 17.3 | 17.6 | 11.4 |
| DYXD | 15.0 | 17.5 | 20.9 | 20.9 | **8.2** |
| DF7e (hicu) | 16.6 | 15.3 | 16.8 | 17.3 | 14.3 |
| GKd5 | 18.8 | 15.2 | 19.0 | 20.5 | 16.1 |

On BAM and Harmonic our fastest landings match theirs. On Jito-relayer we are ~40 ms behind at the fast end (the hold). On Jito-own we are ~4–8 ms behind, on Firedancer 6–15 ms.

## E6. Where the dump sits, and the first slot of a leader's window (median ms · same-slot share)

| Wallet | Q1 | Q2 | Q3 | **Q4 (last 25% of block)** | **window slot 1** | slots 2–4 |
|---|---|---|---|---|---|---|
| OURS-FRA | 65 · 88% | 49 · 88% | 45 · 72% | 50 · **13%** | 49 · **62%** | 47–55 · 79% |
| HkQ7 | 49 · 96% | 42 · 93% | 37 · 84% | 38 · 29% | 40 · 75% | 42–43 · 76–85% |
| haqq | 67 · 81% | 56 · 76% | 49 · 62% | 56 · 18% | 57 · 56% | 55–64 · 60–66% |
| 8PgC | 59 · 84% | 49 · 76% | 43 · 64% | 52 · 21% | 52 · 58% | 48–53 · 60–68% |
| hicu family | 56 · 86% | 50 · 80% | 41 · 69% | 46 · 22% | 49 · 62% | 46–54 · 65–69% |

- **Late dumps:** nobody makes the dump's block reliably (17–29% same slot). The race moves to the next leader.
- **Window slot 1:** we are as good as most pros (62% vs 56–62%). Only HkQ7 is better (75%).
  - On Jito leaders in slot 1 we are worse: 41% same slot (n=34) vs 75% for the first bot that beat us.
- Q1 ms look high for everyone: the block clock over-counts at the start of a block (backlog packed first). INFERRED.

## E7. Location: the fastest 10% / median ms by where the dump's leader is

Leader place comes from RTT from our FRA and AMS servers (≤ 2 ms = same city) plus geo.

| Wallet | FRA | AMS | US | Asia | Reading |
|---|---|---|---|---|---|
| OURS-FRA | 22.9 / 48.8 | 34.4 / 65.7 | 87.4 / 102.3 | 133.6 / 164.6 | EU only |
| HkQ7 | 17.1 / 40.9 | 17.4 / 38.0 | (10 trades) | (2) | EU only, **skips far leaders** |
| haqq | 18.4 / 47.1 | 20.1 / 46.6 | **24.6** / 74.5 | 118.6 / 169.6 | EU + US |
| 8PgC | 15.5 / 37.2 | 15.1 / 34.3 | 76.1 / 120.5 | 118.1 / 165.5 | EU only |
| DYXD | 16.9 / 44.8 | 18.7 / 40.3 | 84.1 / 133.3 | 112.1 / 165.7 | EU only |
| G9G3 | 22.9 / **58.1** | 20.0 / **41.8** | 84.1 / 120.3 | 118.7 / 167.2 | EU, leans AMS |
| DF7e (hicu) | 15.2 / 39.2 | 16.0 / 36.4 | **21.2** / 74.3 | **21.1** / 120.9 | **EU + US + Asia** |
| GKd5 | 18.7 / 47.2 | 16.3 / **38.5** | **24.4** / 75.4 | **21.3** / 102.1 | EU (leans AMS) + US + Asia |

Leader slot share in the window (10-25 gossip):
- **By client:** BAM 37.4%, Harmonic 30.2%, Jito-own 16.8%, Firedancer 7.0%, Jito-relayer 6.2%, Rakurai 1.1%.
- **By place:** FRA 35%, AMS 21%, other EU 10%, far ~34% (US 15%, Asia 10%, other 9%).

## E8. Win / loss vs us on our 481 fires (MEASURED order; ms INFERRED)

"First bot" = the first reactive bot ahead of us. Pre-senders and seller tools are excluded.

| Situation | Our fires | A bot ahead | Us (ms · same slot) | First bot (ms · in dump's block) | Its route (top) | Our lag p50 |
|---|---|---|---|---|---|---|
| All | 481 | 73% | 50 · 75% | 33 · 87% | none 103, astralane 88, helius 56, speedlanding 36, nozomi 30, jito 18 | 11.5 |
| Jito-own | 111 | 77% | 58 · 66% | 34 · 85% | none 31, helius 29, astralane 14 | 22.2 |
| **Jito-relayer** | 32 | 78% | **94** · 69% | 40 · 88% | helius 7, astralane 5, none 4, soyas 3, nozomi 2, jito 2, solami 1 | **76.5** |
| BAM | 150 | 69% | 40 · 80% | 27 · 91% | astralane 30, none 24, helius 14, jito 12, nozomi 12 | 5.6 |
| Harmonic | 155 | 72% | 49 · 81% | 34 · 84% | astralane 36, none 28, speedlanding 27, nozomi 12 | 7.4 |
| Firedancer | 23 | 83% | 69 · 70% | 31 · 84% | none 10, helius 3 | 20.3 |
| Rakurai | 10 | 90% | 203 · 20% | 37 · 89% | none 6 | 148 |
| Dump in last 25% of block | 75 | 59% | 50 · **19%** | 32 · **30%** | none 15, helius 14, astralane 7 | 13.5 |
| Dump in window slot 1 | 118 | 72% | 48 · 64% | 33 · 80% | none 34, astralane 16, helius 11, speedlanding 10 | 11.4 |
| **We spilled** (missed the dump's block) | 122 | 68% | 106 · 0% | 38 · 43% | none 29, helius 23, astralane 14 | 44.8 |
| We spilled on an early dump (Q1–Q3) | 61 | 75% | 137 · 0% | 47 · **65%** | none 16, helius 10, astralane 9 | 54.2 |

- Who beat us most often: 6n2cCJrr 60, 8PgC4ngp 48, HkQ7 46, haqq 34, DF7e 17, GonzYBmk 13, HLU8 12.
- Our landed copy was the no-tip staked-rpc (CK) in 298 / 481 fires. On BAM and Harmonic nozomi drops reverting buys, so the CK copy lands our failures, and late (65 ms on Harmonic).

## E9. Examples to check on Solscan (`https://solscan.io/tx/<sig>`)

**Jito behind a relayer: the winner skips the hold, our no-tip copy waits.**
- Dump [4RsPEBZo…](https://solscan.io/tx/4RsPEBZo9Kfmh87pH3aCxVAjnr6R4aC1YrXfyCRsAknJAF4kPWZxSQ6BBpjctcXm147PzeCbFTJR22krPbbkK5FF):
  - HLU8 (hicu) +46 ms via helius, CU price 0, tip 0.0011: [4HsHne12…](https://solscan.io/tx/4HsHne12dEWZWECJpJ84Dvo7PYu5FE4EF9aZxLddreNisdY2cx4BkXuSAs2G2F9h2BHZX52WsBxpxXJtimJ8xhdJ)
  - Us (FRA r15) +129 ms via staked-rpc, failed: [4MhgYkEP…](https://solscan.io/tx/4MhgYkEP6ZBFoMdHuUCnLnxX42fxbko89yQuXvbMaULFXLqE8ioZYjMZ9fJDKt1yywq2Pz7Wvpd57wWoMovPVQFy)
- HkQ7 via **soyas**, +19 ms, 33 positions after dump [2zfvZnmh…](https://solscan.io/tx/2zfvZnmhGiDYbP9eUp6wKxBMjz6SHq7wVZ5tC228SB3Qy7tGJEHPf7k8vjFJmYoXfEvFMTY5rQkNmP89ortbwcVQ): [4j239dSn…](https://solscan.io/tx/4j239dSnrjDKYqkbqnKLrCqf8xMxuzGahCzGwPim9K6J5Z9DH8ojhDGe4WieG57xf8Nv1dJQhWb6vh3SrN1rCKNt)
  - The same bot's no-tip copy on another relayer leader landed at +58 ms (114 positions): [29vM3bYz…](https://solscan.io/tx/29vM3bYzVg9ZG7BXgB95wCWiVQsW12uwLcPYSLfeU7iYa5sKi4hccosKH59kPP6a59k1gdACmDPGFyZbaHStAaaq)
- GKd5 via **solami**, tip 0.0001, +6 ms (22 positions): [2RPHTqAh…](https://solscan.io/tx/2RPHTqAhnBEpL5SA6sn1Js5ZuvoADJRVWXs5XZ5ySuq1XMNAafN5eHEuT9Y9DuNd42gtGCbcqTYkrCchGnZr3y5g)

**Jito own TPU**
- DF7e (hicu) via helius, CU price 0, tip 0.0011, +25 ms (30 positions): [51vCw3D7…](https://solscan.io/tx/51vCw3D71MLmymV1MgqvrREm4SzLbyLPhREYZJCfqxk7G5AZFNDzosK941mdSRWr6Wg6SiLVRWWYhENALsvSkFCh)
- Dump [5eSryLbL…](https://solscan.io/tx/5eSryLbLLL3kAGND4pJjDaG4ZZgwMsR3AKH3Kp3ZTC9kq3xh4d8JuuumqiUJde1HSqRJQuThYWSbe38vnd8LTNXo):
  - 3MHg via helius (0.000005 swqos tip) +37.5 ms: [4DipJ7mh…](https://solscan.io/tx/4DipJ7mhjcAEsZFbhapnvirQB59ZG2uNwweFZJE6Jm7ynGaAx1Hn6JjWs3S5RurDndfdsJFJQ5BH2RUjQHxZJEWZ)
  - Us +40.7 ms, failed: [2KWQzBqm…](https://solscan.io/tx/2KWQzBqmv9wtrzB8YUt8cJPY2PFZT1CvAddf9Jk1fiBTgPZ78Etbzt2oWEkhoeWzzHMM1oL3dtYvT35yMZf6D391)

**Harmonic.** Dump [5EtqFS9Q…](https://solscan.io/tx/5EtqFS9QGKNriZ2K3Ae9WqNanhbkgQJquFFJTTKA8YwZk7SL6qZgz6nPvdNnjQxSm7H4rgLieSnwnu7TSuCqHjUf):
- 8PgC via speedlanding +22.1 ms: [Uuf2WfsH…](https://solscan.io/tx/Uuf2WfsHfjToM1JSkwK59NykQN1adCsqiqSYr1ouJULa1TNorx3f2dagnJ1EGDd2tZ5XJKMZndfA91jFzLGiQ2a)
- Us via nozomi +23.0 ms, filled, one tx later: [3oVKxbyu…](https://solscan.io/tx/3oVKxbyu54JTjb2QAGruCXdz9nnmMDnQq2q7C8z5gcaAY53MmaTYVAuTbZnS7MeBwqcsErV6z4iQskWvYSUjCKGX)
- Same speed; they won by a hair.

**Firedancer.**
- Dump [3YTFsjNd…](https://solscan.io/tx/3YTFsjNdcEamKpZ3iHxNa4aD8MTF4w7Np8DiXXdqhdHcaFJb8jvqaGiyucrDjsWTzm4UwJu5SkSVTZiFx9MCjCUZ):
  - 8PgC via nozomi +7 ms: [4CL1JRFF…](https://solscan.io/tx/4CL1JRFFvEtwJ4XUkjNDYaE5FXo3LGqd52RjzpT28jvW44WkMgE11VKEmhXApjRjSDFheeL8XFJWcNJPsKwErqxY)
  - Us via landx +62.6 ms: [5F1NCpDs…](https://solscan.io/tx/5F1NCpDsHixou3zkMUWw4EpE8SNwVzLmriU3TaFbnWoEBsu2QjPTtGDqcFPYvjMkbSucvNduPkde7tWiGQTw3tau)
- 8PgC via the unknown **Node1** tip, +8.8 ms: [24EjBd2z…](https://solscan.io/tx/24EjBd2zo2JhSsE3jdzPX3PA7qWs668J9nvRrCRcT4Cy2kUwdogsziq3QrY9xRk3EtPobAccnGeieVZgXTVB6FMV)

**Far leaders (multi-region), all no-tip copies at ~+20–22 ms.**
- EJX6 (hicu) on an Asia BAM leader, +20 ms: [5wDDgJHA…](https://solscan.io/tx/5wDDgJHAzjWKJ6dyUSxjzhhsTgXXek8mosiUmFq231EEyArho1XMqmAPAX4SqJm4NMb5KmD9noBEctPizeUMXTbV)
- GKd5 on an Asia leader, +20 ms: [toHG8jxg…](https://solscan.io/tx/toHG8jxgjxZBDodX9Yf8DwTdGtEn7gqQmViYBVs8V8hTaZoaWZXHHDm8YgSfs3CauVNWJfAGcdPotiamZwmDsxd)
- DF7e on a US leader, +22 ms: [44ogwzea…](https://solscan.io/tx/44ogwzeAafLTmittgSqFP6NvvVFpx7h7u5zVnxcRm1noujNNKQb7RZ5osfwLeXSgYBPZjGcE34NyVRu31yFK4U9F)

---

## Tip map (tip account → service)

Usage = pump.fun txs that paid the service in the 47.6 h recording (from SOL balance changes; approximate).

| Service | Accounts (example) | Min tip SOL | EU endpoints | Usage, 48 h | Source (checked live 10-25 = ✔) |
|---|---|---|---|---|---|
| Jito block engine | 8 (96gYZGLn…) | 0.000001 | frankfurt / amsterdam / london.mainnet.block-engine.jito.wtf | 1,987,583 | docs.jito.wtf/lowlatencytxnsend ✔ |
| Helius Sender | 10 (4ACfpUFo…) | 0.000005 swqos-only; 0.001 Sender Max ("priority tip buffer for top of block") | fra / ams / lon-sender.helius-rpc.com | 2,033,988 | helius.dev/docs/sending-transactions/sender ✔ |
| Nozomi (Temporal) | 17 (TEMPaMeC…, noz…) | 0.001 (below = silently dropped); retries; "may deprioritize durable-nonce txs" | fra2 / ams1 .nozomi.temporal.xyz | 40,615 | use.temporal.xyz/nozomi/tipping-and-faq ✔ |
| Astralane (Iris) | 17 (astra…, AstrA…) | 0.001 free · 0.0001 VIP1–2 · 0.00001 VIP3; FIFO routers | fr / fr2 / ams / ams2 (Cherry 84.32.186.73) / lim / lit / lon .gateway.astralane.io | 897,523 | astralane.gitbook.io/docs/low-latency/… ✔ |
| bloXroute | 17 (+2 legacy) (3UQUKjhM…, bLx…) | 0.001 | germany / amsterdam / uk.solana.dex.blxrbdn.com | 1,072 | docs.bloxroute.com/solana/trader-api/introduction/tip-and-tipping-addresses ✔ |
| BlockRazor | 15 live (68Pwb4jS…; 5 new vs our list) | 0.0001 | frankfurt.solana.blockrazor.xyz | 7,224 | docs.blockrazor.io/…/priority-fee-and-tip ✔ |
| Bolt (Raiden) | 9 (t1TcSg9b…) | 0.001 (higher tip = higher routing priority) | fra / ams / lnd .bolt.raiden.wtf | 3,189 | raiden-4.gitbook.io/…/tip-addresses ✔ |
| SpeedLanding | 8 (SpEEdz8S…) | 0.001 | fra / ams / lon / ny / tyo / sgp .speedlanding.trade (QUIC :17778) | 28,528 | speedlanding.trade/docs.html ✔ |
| Glaive | 6 (GLaiv…) | 0.0001; ranks by priority fee | ams1 / ams2 / fra / lon / ny .glaive.trade (QUIC UDP 4000) | 1,877 | glaive.trade/docs ✔ |
| LandX | 10 (LandX1EM…) | n/a | (our landx-fra3, UDP) | 5,528 | landx-1.gitbook.io/landx-docs/tip-addresses ✔ |
| soyas | 10 (soyas4s6…) | 0.001 | fra / fra2 / ams .landing.soyas.xyz:9000 | 69 (rare, premium) | soyas.xyz/fast-landing (our catalogue, 10-03; page is JS-only now) |
| 0slot | 21 (6fQaVhYZ…) | 0.001 | de / ams .0slot.trade | 102,768 | 0slot.trade/docs.php (catalogue; 404 on 10-25) |
| Flashblock | 10 (FLaShB3i…) | 0.0001 | fra / ams / london / lithuanian .flashblock.trade | 11,834 | doc.flashblock.trade/en/transaction (catalogue; 403 on 10-25) |
| NextBlock | 8 (NextbLoCk…) | n/a ($249–1,749 per month tiers) | frankfurt / amsterdam / london / dublin .nextblock.io | 5 | docs.nextblock.io (catalogue) |
| Falcon (Corvus) | 10 (Fa1con11…) | 0.001 | fra / ams / lon .falcon.wtf | 138 | docs.corvus-labs.io/falcon/tips (catalogue) |
| Stellium | 9 (ste11…) | 0.001 | on request | 8,643 | docs.stellium.dev/products/fast-tx-landing (catalogue) |
| node1 | 6 (node1PqA…) | 0.001 | fra / fra2 / ams / lon / dub .node1.me | 347 | node1.gitbook.io/… (catalogue) |
| Lunar Lander (Hello Moon) | 10 (moon…) | 0.001 | fra / ams / lon .lunar-lander.hellomoon.io | 77,868 | docs.hellomoon.io/reference/lunar-lander (catalogue) |
| solami Beam | 15 (…beam, …1ami) | 0.0001 | beam.solami.dev:11000 (QUIC) | 1 wallet seen | solami.dev/docs (catalogue) |
| RPC Fast Beam | 18 (rfB…) | 0.0001 | beam.rpcfast.com | 855 | docs.rpcfast.com (catalogue) |
| Others in our catalogue | AllenHark relay 11, Everstake SWQoS 10, P2P Syncro 9, QuickNode Fastlane 8, Jupiter tx 16, SVS Lightspeed 1 + 2, Rakurai 8 | 0.0002–0.001 | – | small | data/sender-tip-accounts.json |
| **Unknown, found in pros' txs** (round tips, no public page found) | Node1HiScWKC9UmmWYu3AftMdtCZ3qE1qs2FqSLukX8, Node1j2ru8UmagMVkpcRW8xB6PmrvKEbFoZPSvo1fex (0.001; DYXD, 8PgC) · D1Mc6j9xQWgR1o1Z7yU5nVVXFQiAYx7FG9AW1aVfwrUM, MANKAZYMJSUFEui63ZzSRzk6NsdZj8ej7wkcrk13vzS (0.0011; hicu) · Sp4JHSh9…, SpWrza9E…, SpagSJmn…, Sp1xMS2c…, Sp1x2Aqp… (0.001; DYXD, hicu, CatkiN) · FASTYKWXRfAoty7SQCM1mGVrmPUyyNcF4tc3DUkLDAu9 (0.001; DYXD, 8PgC) · APeX2oLt… (5k2C) · AS6RWKUi…, AVwZ5Mvv… (hicu) | – | – | 15–171 txs each | web search 10-25: nothing found |

Notes:
- The recorder's `tips` field only knows listed accounts. The unknown ones were found in its SOL-balance changes.
- "none" routes can still hide services we don't know.
- Catalogue = `/home/moiz/sniper/data/sender-tip-accounts.json` (sourced, fetched 10-03/04). Map used here: `lib2.py`.

## Method and limits

**Pipeline** (`ops/dip/speed/landing2/`, data in `/home/moiz/sniper-data/landing2/`):
1. `x1_extract.py`: compact trades, target-wallet txs (failed too), block sizes, SOL recipients.
2. `x2_unknown_tips.py`: unknown tip accounts.
3. `x3_reactions.py`: dumps, followers, landings.
4. `x4_pros.py`, `x6_tables.py`: per-wallet tables.
5. `x5_ourfires.py`, `x7_h2h.py`, `x10_winners.py`, `x12_examples.py`: our fires, head to head, win/loss, examples.
6. `x8_anatomy.py`, `x11_anatomy_tables.py`: tx anatomy.
7. `x9_sameroute.py`: same-route test.
8. Shared code: `lib2.py` (tip map, leader client / front / place, block clock), `rpc_ro.py` (read-only, ≤ 4 req/s, URL never printed).

**Leaders:**
- Schedule: `leaders_by_slot.json`, plus the previous epoch fetched read-only.
- Client and Jito relayer front: gossip of 10-25 ~19:10 PKT. TPU on port 11228 or on another IP = relayer.
- Place: RTT books from 10-23 plus geo.

**Limits:**
- **Block clock:** ms are INFERRED and ±17 ms per case. Positions and order are exact.
- **Route speeds** are conditional (the copy that won) and mix path with bot quality. Pooling over 7–25 wallets reduces that bias but does not remove it.
- **Copies that never land are invisible.** Copies per trade is a lower bound.
- **"Reaction"** = first buy ≤ 3 slots after a dump. A few are coincidences or pre-sends; "instant" pre-senders are listed apart.
- **Our older fires (r1–r10)** used multi-tip txs. The tables mix eras; the E2 note on our own copies is nonce-era only.
- **Gossip labels are a snapshot.** A validator can switch client or front.
