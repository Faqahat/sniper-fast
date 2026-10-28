# Analyst D (execution): how haqq sends, and what to copy (10-28 ~02:50 PKT)
Saved by the main session from the agent's reply. Scripts: this folder. Tables: /home/moiz/sniper-data/haqq_dissect/exec/ (read t0_summary.txt first, then t3–t9). Router binary: haqq_router_haqqqMGN.so.

## Short answers (M = measured, I = inferred)
1. **He lands almost everything because of WHAT he sends.**
   - Buys ≤0.45 SOL have no limit (min_out = 1) and fail 2.5–7.8%/day.
   - 1.0/1.25 SOL buys are cheap floor bids (12k-lamport priority) that fail 44–59%, at 0.017 mSOL per failure.
   - All copies share one durable nonce (~100 accounts in his pool; we have 8). He never retries.
   - Failures cost him 0.006 mSOL per lot.
2. **He does NOT pre-send (M).** He has ~1k failed txs/day vs our ~44k. His router never reads the Clock sysvar.
3. **The router haqqqMGN is a thin pass-through (M):**
   - one instruction, trade_v3, with argument order shuffled per tx;
   - token accounts via CreateAccountWithSeed + InitializeAccount3 instead of the ATA program;
   - the only check is a post-buy token-amount band on 0.5 SOL buys.
   - The "funder" HKVWNV… is the router's upgrade authority, not an exchange.
4. **His buys land slower than ours:** dump → buy median 45 ms (68% same slot). Ours: regular fills 21–35 ms (71–74%), pre-send fills 22–24 ms (95%). Don't copy his buy lanes; our nozomi wins.
5. **Our money goes on sells:** 1.805 mSOL per sell (two tips, 0.2 + 1.0, plus 600k priority). His sells cost 0.27.

## Cost per fill (M)

| | Cost per fill/lot | Made up of |
|---|---|---|
| haqq | 0.793 mSOL per lot | stable 0.67–0.90/day |
| Our pre-send fill | 2.64 | fill 0.205 + 122 failed tries 0.622 + sell 1.805 |
| Our regular fill | 4.61 | buy 1.75 + 2.03 failed fires × 0.521 + sell 1.805 |

**Our execution spend per day:** 10-25 0.925 SOL, 10-26 2.073, 10-27 2.084. Sells are 1.2–1.3 SOL/day of that.

## Speed of sells (M)
- Our sells land a median 53–58 ms after the decision (81–85% same slot).
- In an exact replay, landing 20 ms later changes proceeds by −0.07 mSOL/sell, which is noise. A cheaper sell is worth more than the speed.

## Recipes (needs owner OK; nothing built)
- **S1 (no speed risk): +0.47 SOL/day.**
  - Sells on durable nonces with one tip per copy; CU limit 55k.
  - Buys: CreateAccountWithSeed + InitializeAccount3 instead of the ATA program, reuse the WSOL account, CU limit 66k.
- **S2 = S1 + his sell recipe: +0.90 SOL/day** (pre-send +0.57, regular +0.34).
  - Sells as copies on one nonce: keyed Helius swqos 0.2 tip, a no-tip staked copy, 0slot 0.1. Priority 120k, so ~0.28 mSOL per sell.
  - Speed risk ≤ −0.27/day.
- **S3 = S2 + regular-fire priority at his 120k: +1.01/day.** A/B test first: our higher CU price wins close pairs on BAM 79% and Harmonic 66%.

**Don't copy:** his buy lanes, his loose limits, an on-chain program, or pre-send changes (small waste ~0.025/day). Adds/multi-buys would need a bigger nonce pool (~100).
