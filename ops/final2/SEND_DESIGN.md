# Send design for FINAL-2: why fees decide it, and the proposed change (owner's decision)

2026-10-23 PKT. This is a proposal only. The send path is unchanged, and no transactions were sent.

## Why it matters (MEASURED, replay)
- **Most attempts fail by design.** FINAL-2 buys only when first after the bundle, so about 60% of attempts fail at 75 ms (about 40% at 45 ms). Each failed buy still pays the transaction's priority fee. Tips in the same tx revert when it fails.
- **At today's settings the strategy doesn't work in daytime.** Run 2 paid about 0.0105 SOL priority (CU 95k × 110M µL), a 0.012 Jito tip and about 0.001 in relay tips per buy, so about 0.0235 per landed buy and 0.0105 per failed buy.
  - Daytime PKT: −1.45 SOL per 9.5 h at 75 ms (pros' later buys removed, slippage).
  - Overnight: only +0.40 per 8.3 h.
- **With CW's cost structure** (0.003 priority + 0.003 tip per buy, 0.003 per failed buy):
  - +0.43 / +2.38 at 75 ms (daytime / overnight);
  - +0.44 / +3.44 at 45 ms.
  - Scaled to 24 h overnight at 1 SOL: **+13 SOL at 75 ms, +18 at 45 ms**.

## What the profitable bots do (MEASURED, from their own transactions)

| Bot | Design | Cost | Landing (our feed) |
|---|---|---|---|
| CWiNFAEk | Durable nonce; one copy per service (≈10: Nozomi, Astralane, Flashblock, Helius, Stellium, Jito, …), each with a 0.003 SOL tip; 0.003 SOL priority. Only one copy can land. | 0.006 SOL per buy (0.6% at 1 SOL); 0.003 per failed buy | median 49 ms |
| dKMjeGJ4 | Durable nonce (3 accounts); ~20 copies. The Jito copy has no priority fee, a ~3% tip and `jitodontfront`; the others 0.003 tip + 0.01 priority. | 2.4% of SOL bought | median 42 ms, first after the bundle 65% |
| FiFawH | One nonce; ~9 services; tip ≈ 1.9% of size; one priority-only copy | ~1.9%, but failed priority copies cost it 14.4 SOL / 61 h | median 61 ms |
| 9Sh2fd (AKbot) | Durable nonce; LandX only | ~2% tip + AKbot 1% | median 39–45 ms |

**Per path, from the landing study** (`ops/overnight/landing/LANDING_PATHS.md`):
- **LandX:** sniper-sized buys land in the create slot 74% of the time, median 37 ms.
- **By leader client:**
  - BAM / Jito-Solana: Helius wins 64–73% of races.
  - Harmonic: speedlanding wins 75%.
  - Firedancer: astralane wins 71%.
- **Priority-fee-only staked-RPC copies:** 60% in the create slot at 40 ms, for about 0.5% of size in priority.
- **Always late:** 0slot, blockrazor, nextblock, rpcfast, lunar and falcon.

## Proposal (needs the owner's OK)
1. **Durable nonce for every buy.** The tx needs no recent blockhash, so it is signed once per copy instantly. Only one copy can land; the others become invalid.
2. **One copy per service, by leader client**, each copy carrying only its own tip:

   | Leader client | Copies |
   |---|---|
   | BAM / Jito-Solana | helius + landx + speedlanding (+ a Jito bundle copy only on BAM) |
   | Harmonic | speedlanding + nozomi + landx |
   | Firedancer | astralane + landx |
   | All | one low-priority staked-RPC copy |

3. **Small fixed tips,** about 0.002–0.003 SOL per copy (CW lands with 0.003).
4. **Low priority fee,** about 0.001–0.003 SOL (CU ≈ 60–80k at 15–40M µL), because it is what a failed guarded buy pays.
5. **Keep the guard tx-failing:** min-out on the pump buy, so the tx fails (CW and dK do this). FiFawH's guard returns "success" and still pays the tip; that cost it 6.2 SOL in 61 h.
6. **Expected (INFERRED from the bots' and paths' measured results):**
   - landing about 35–50 ms instead of 74;
   - about 0.005–0.008 SOL per landed buy;
   - about 0.002–0.003 SOL per failed buy.

## How to test it cheaply (needs OK)
- **Buy-shaped probes from FRZ that fail by design** (min-out = u64::MAX). They cost only the priority fee. One probe per launch on about 50–100 launches, routed as above.
- **Measure:**
  - our arrival ms in our own feed vs the create;
  - the in-slot position;
  - which copy landed (by tip account).
- **Compare with the pros:** median 39–49 ms.
- **Code base** (checked 10-23 10:45 PKT):
  - The snipe engine (`src/bin/snipe_engine.rs`) has routes per leader client and multi-route sends, but builds ONE transaction with the cached blockhash and every route's tip.
  - The shared library already has the nonce pieces:
    - `build::advance_nonce_ix` (AdvanceNonceAccount, must be the first instruction);
    - `build::nonce_value` (reads the stored value from the account's 80 bytes);
    - `build::Plan.nonce` (prepends the advance; ALT handling keeps the nonce account static);
    - `build::create_nonce_ixs`, and the `nonces` command in `src/main.rs` to create the accounts (owner, on chain).
  - Missing in the snipe engine:
    - one copy per route, each with only its own tip and the nonce value as blockhash;
    - nonce-value tracking after each use (read the account; rotate 3+ accounts so a read can finish before reuse).
- **Engineering estimate** (INFERRED): about half a day to a day:
  - nonce accounts (created on chain by the owner);
  - an `advanceNonce` instruction plus the nonce value as blockhash;
  - one signed copy per route with that route's tip only;
  - a nonce refresh after each use.
- **Probe first:** with buy-shaped probes that fail by design.

## Config-only option first (no code; 10-23 11:20 PKT; needs the owner's OK)
**Evidence** (our own probes, `ops/run2/RUN2_PLAN.md`):
- one route per send landed 17–34 ms after the create;
- one transaction to several routes landed 96–148 ms (Harmonic, 7 of 7);
- Run 2 (5 routes in one transaction on Jito-client leaders) landed 73–75 ms.

**Proposed** `ROUTES` in `run1_common.sh`, one path per leader client (head-to-head winners from `ops/overnight/landing/LANDING_PATHS.md`; speedlanding has no account, so nozomi on Harmonic):

    ROUTES="bam=helius;jito=helius;harmonic=nozomi;fd=astralane;agave=helius;other=landx-fra3;default=helius"

**Tips:** Helius winners tip ~0.001–0.002 SOL. HkQ7hMjy lands dip buys at ~36 ms with a 0.0003–0.001 SOL tip and ~0.00013 SOL priority.

**Check first** with `ops/final2/probe_speed.sh`: the owner runs it; 4 single-route phases plus the current multi-route design; fail-by-design buys; ≤0.05 SOL per phase.

**Evidence from the best dip bot (2026-10-23 13:13 PKT, `ops/dip/PLAN.md` "How HkQ7hMjy routes"):** HkQ7hMjy sends plain direct pump buys with one landing service per leader client: Nozomi on BAM (73%, 41 ms) and Harmonic (84%, 37 ms); on Jito-client leaders, Helius is its fastest (29 ms) ahead of Nozomi (44 ms); on Firedancer, mostly no tip (43 ms) or Nozomi (35 ms). Tip 0.001 SOL, priority fee ~0.00013 SOL. So the probe should also try **bam=nozomi** and **fd=nozomi**, e.g. `ROUTES="bam=nozomi;jito=helius;harmonic=nozomi;fd=nozomi;agave=helius;other=landx-fra3;default=helius"`. Nothing changed; owner's OK needed.
