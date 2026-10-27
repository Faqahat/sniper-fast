# Who beats our dip buys, and how (agent study, 10-24 ~23:55 PKT)

Read-only; 1,174 rival transactions decoded from raw bytes. MEASURED unless marked.
Data: /home/moiz/sniper-data/competitors2/ (summary.json first; dossier.txt, timing.txt, shapes.txt, counterfactual.txt,
examples.json).

## Summary
- **We are not slow inside the bot:** dump → send is about 2.6 ms. The time is lost after we send.
- **By leader type:**
  - Harmonic: we are as fast as the best (~35 ms after the dump).
  - BAM, Frankfurt server: 5–10 ms slower than the leading pack.
  - Jito: 20–60 ms slower. Worst on HEL1USMZ (Helius's own validator, ~90 ms) and on the Amsterdam Jito validators
    GnC339vk and ACvL73V4 (110–145 ms, none filled).
- **Who beats us:**
  - The 41Pr/6gY1 family: about 45 wallets, one operator, the #1 first buyer overall. It pays 14–22M µL/CU, and its winning
    copies are mostly untipped.
  - HkQ7hMjy pushes the price past our +5% limit most often (18 of 92 losses). haqqiUUX is ahead most often (32 of 92).
  - Then 6n2cCJrr, 7PedQZmc, BfvkhDip and 8PgC4ngp.
  - Pre-placed bots (2KtcBCfh, CVPz447t, two more families) keep conditional buys queued and land 1–9 ms after a dump.
    Reaction speed cannot beat them.
- **All 25 of the fast reacting bots sampled use a durable-nonce fan-out:** one tip per copy, usually plus an untipped copy.
  They also use a small priority fee and a tight compute limit.
  - A filled buy costs us a median 0.0027 SOL in fee + tips, against 0.0003–0.0011 for them.
- **10 ms faster would have saved 38 of our 92 losses.**
- **Tonight's 0 of 10 since 23:00:** the same rivals. Our leader lookup is still correct after the epoch change at ~22:59.

## Fixable gaps, ranked
1. **Jito leaders** (27 of 92 losses; fill rate 37% vs 47–53% elsewhere). Our Helius copy probably isn't the one landing.
   - Test A (free): the fast_ack logs for Helius and nozomi replies on the 43 Jito fires.
   - Test B (probes, ~0.0005 SOL each): about 10 each through Helius-only with a single tip, soyas, solami_beam, speedlanding
     and jito-bundle.
   - Fallback: skip HEL1USMZ, GnC339vk and ACvL73V4.
2. **BAM leaders from Frankfurt:** 27.8 ms and 9 of 26 filled, vs Amsterdam's 23.6 ms and 13 of 25. The winning copies there
   go through jito, speedlanding, nozomi, an untipped path, or astralane. Test: probes of those relays.
3. **Nonce fan-out:** 25 of 25 fast reacting bots use it. Build in progress. Saves about 0.002 SOL per fill, allows more
   relays at no extra tip cost, and shows which relay won each trade.
4. **Priority on BAM / Harmonic ties:** the top operators pay 14–24M µL/CU; an earlier report measured that BAM and Harmonic
   order near-simultaneous arrivals by fee 76–90% of the time. Test: 5M vs 15M on BAM / Harmonic fires, at least 30 each.
5. **Pre-placed bots:** removing them would flip 14 of our losses. The only answer is to pre-send conditional buys guarded by
   a price check: a strategy change, shadow study first.
6. **Transaction shape:** our CU limit is 100.3k against 66–79k used (85k would cut every attempt's fee about 15%); no
   loaded-data limit; two separate token-account creations; failures are not cheap. Test: free simulation for safe limits.

## Not levers / can't change
- Transaction size and format (legacy, v0, v1): mixed among the fast bots.
- No sign of co-location or private order flow: no wallet is first on any one leader more than 24% of the time.
- Untipped fast lines (41Pr family, 7PedQZmc, GKd5) probably come from their own staked connections (INFERRED).
