# 9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1: how he gets position (2026-10-22, read-only, chain data)

## Data
- **His transactions:** 933 recent successful txs (138 buys, 587 sells, 10-20 03:51 → 10-22 14:50 UTC), via the owner's RPC.
- **Block positions:** 45 of his create-block buys, each block classified with Jito's bundle API (bundlestudy.py).
- **Population:** 343 recorded launches (717 outside create-block buys) for comparison.
- **Speed:** our engine logs (RACE obs) for arrival times.

## Facts
- **Not an insider.**
  - 0 of 43 SOL-quoted create-block buys sit in the dev's bundle. 4 sit in a Jito bundle of their own.
  - Wallet created 10-17 and funded with 13.70 SOL from 5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9, a multi-payout wallet (looks like an exchange).
  - 3,665 txs all-time.
- **Position.**
  - First outside buyer in 42 of 43 create-block buys. Once he was 2nd, behind D24ipY, which paid 0.16 SOL.
  - Median position: 67 txs after the dev's bundle. TTO: +107, 1st of 4 outside buyers.
  - 107 of 138 buys land in the create block, 24 in the next block.
- **What he pays.**
  - Priority fee: only 0.002–0.005 SOL. This is GMGN's "Gas".
  - LandX tip, a separate transfer to LandX's tip accounts (LandX1…–LandX9…), in 120 of 138 buys. It scales with size:
    - 1.78 SOL buys: 0.0218 tip;
    - 2.96 SOL buys: 0.0618 tip (also 0.06, 0.08, 0.12).
  - Total ≈ 1.4–2.3% of the buy. That is our ratio, but almost all of it goes to one landing service.
- **LandX across all 343 launches.** LandX-tipping buys were the first outside buyer 67% of the time. Helius was 39%, Nozomi 35%, Astralane 40%.
- **TTO example.** Buy tx 5CLAuCjHjay2Mh5NFsjKteof7LppMJxVpk2Us2zFvGgKCPpUKkoEv4HsuwBC7CJiXWuSrL5T8fVc6JiCXyjEDMnF, slot 460055279.
  - He paid a 0.0632 LandX tip and 0.0025 priority.
  - 4BHB…PqHP paid ~$12.6 gas and landed after him.
- **His transaction format:**
  - v1 transaction: the fee is set in the header, with no compute-budget instructions;
  - advanceNonce, a durable nonce on account 59Je5dKouRf3iiDAseujAGUwzrsqrMps9Y3EdBgiDFRi, so no blockhash is needed and the tx can be signed and sent instantly to several endpoints;
  - the LandX tip transfer;
  - a token account made with createAccountWithSeed + initializeAccount3, instead of the ATA program;
  - the pump buy.
  - 50,622 CU in total, about half of ours. Single signer.
- **Size tiers:** 1.78 SOL (54 buys) and 2.96 SOL (48). Also 1.98 and 2.47.
- **Other-quoted tokens:** 20 buys of USDC- or PUMP-quoted pump tokens go through his own program akbotssnVdpbCyjxbZJbspZspRcXJqzLjqteNBMJF9i (swap first, then buy).
- **Leader clients:** he snipes on all of them (AgaveBam, Harmonic, Jito, Firedancer), in about the same mix as all launches. Half of the slots could not be attributed.
- **Speed (our feed):** 6.4 ms and 13.4 ms after the create on two 10-21 launches; we were at 73–75 ms. Across 17 sightings the median was 137 ms.
- **Exits** (noted, not analyzed): 587 sells for 138 buys (about 4 sells per buy); GMGN shows holds of mostly 2–13 s.

## Inference (not proven: LandX internals are not public)
His position is bought with the LandX tip, not the priority fee. LandX appears to get high-tip transactions to the leader ahead of other paths. The lean nonce-based v1 transaction lets him fire immediately.

## Test to settle it (needs the owner's OK: send path + paid)
- Send buy-shaped probes (a real buy with min_out = max, which fails on slippage) through LandX only, with tips of 0.005, 0.02 and 0.06 SOL.
- Measure landing ms and position against him.
- Cost: a failed tx reverts the tip, so we pay only the priority fee per probe.

## Update: the separate 1% transfers (owner asked about tx 2kg89b5V…)
Tx 2kg89b5VDftK5CEhknFLoURNMpTuGxZH3rAFYuTpstw4JgoUDVdFdcappoR44iytmb9YGzNcTFyf2gf8rj6fBBjJ (slot 460055493) is a plain transfer, with no trade:
- 0.017777778 SOL to AKbotZVF3zr9i4Cz2Lv34s6SydytjdidruoGTnvwPxFh;
- that is exactly 1% of his 1.777777777 SOL TTO buy;
- sent 214 slots (~45 s) after the buy.

**The pattern in his last 933 txs:**
- 121 standalone transfers like this one.
- 83 of them equal exactly 1% of the previous buy (0.02963 on 2.963 buys, 0.017778 on 1.7778 buys).
- Paid a median ~671 slots (~2.3 min) after the buy, never inside the buy tx.
- "AKbot" matches his router program akbotssnVdpbCyjxbZJbspZspRcXJqzLjqteNBMJF9i.

**Reading (inference):** this is a commercial sniping bot's 1% fee ("AK bots"), and 9Sh2fd is probably a customer. The bot provides the LandX tips, durable nonces and v1 txs.

**His full cost per buy:**
- LandX tip: 1.2–2.1%;
- bot fee: 1%;
- priority: ~0.1–0.15%;
- plus pump fees.

**Lead:** other wallets paying AKbotZVF… would be the same bot's other users.

## Relation to D24ipY (and DGmspiBs), 2026-10-22
- **Direct transfers:** none between 9Sh2fd and D24ipY.
- **Shared funder.** Both were funded by hot wallet 5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9: 9Sh2fd with 13.70 SOL on 10-17, D24ipY with 29.999 SOL.
  - 5tzFki does about 1,250 txs/hour, pays out in batches and receives sweeps from deposit addresses.
  - So it is an exchange (or custody) hot wallet, which makes this a weak link.
- **Same bot, different settings.** Both pay AKbot and use a 0.0025 priority fee, LandX tips and durable nonces.

  | | 9Sh2fd | D24ipY |
  |---|---|---|
  | Buy sizes (SOL) | 1.78 / 2.96 | 0.49 / 0.98 / 1.76 / 1.95 |
  | LandX tip | ~2% | 0.001–0.0066, or none / Helius |
- **Same devs, never the same launch.**
  - Dev 49fAsUF3 made 219 launches in the window. Each wallet bought 27 of them, with 0 in common. Chance by luck: 2.2% (3.3 shared launches expected).
  - They share 5 target devs, and only 1 token in common out of 122 vs 418.
- **Stronger link: 9Sh2fd ↔ DGmspiBs.**
  - 9Sh2fd's withdrawal address DKoJUtXygzRkTB6XtQX9TEtxT1kGDgcFi2PcSMxtJcuW gets deposits from only 3 wallets: 9Sh2fd (7.76 SOL), 9NFzHf4Q… (6.29) and DGmspiBs (5.78). It sweeps everything to 5tzFki.
  - That looks like one exchange account, so likely the same owner.
  - 9Sh2fd and DGmspiBs bought 0 tokens in common (137 vs 134) and target different devs.
