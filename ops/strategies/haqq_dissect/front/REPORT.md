# Analyst M (front): who lands first on paying dumps, and how we could (10-28 ~04:20 PKT)
Saved by the main session from the agent's reply. Code: this folder (f1–f14). Tables: /home/moiz/sniper-data/haqq_dissect/front/ (f13, f8_tables, f9_blockpos, f10, f11, f6_shape, f12_examples, f14_perday .txt). MEASURED unless marked.

## Short answer
- **Paying dumps** (the first buyer lands in the dump's own slot and a 0.40 SOL buy just before it is worth ≥ +30 mSOL, wave exit): 19,789 dumps, ~4,800/day.
  - Gross "front value" +339 SOL/day: an upper bound, INFERRED.
- **The first buy lands a median 20 ms after the dump** (p25 ~4 ms). Who takes it:
  1. **The dumper's own Jito bundle:** 9.2% of dumps, 15.6% of value; atomic, unreachable.
  2. **Pre-senders:** 21% of first buyers (CZ77onJz, 9K5QgBKa, 5k2Ckkiu, Dk2jdQ93), ~2 ms after the dump with low CU price.
  3. **Fast reactive bots:** 28–39 ms (8yYMhuYo, 7PedQZmc, 8PgC4ngp, haqq 2.4% at 37 ms, GKd5EMzR, DF7eRX, HkQ7, EMKY7r6U). A long tail of 4,102 wallets.
- **We rarely try, and when we do we are 60–90 ms late.**
  - Value split: 63% never targeted (selection), 10.5% no engine running.
  - We attempted 10.4% of paying dumps and were first on 9.4% of those.
  - Our first landing is 59–79 ms after the dump, against ~25 ms for the reachable front; 3 buys ahead at the median.
- **Mechanism (KEY): pre-send try spacing.**
  - 4 tries per slot means one every 53 ms.
  - 54% land in the slot AFTER the target, late in the block (median position 0.76).
  - All go through Helius at CU 1000.
  - So after a dump our next try lands a median 83 ms later; fast bots fill the gap in ~25 ms.
  - This explains analyst H's adverse-fill finding.

## Value by cause (SOL/day, mean 10-24..10-27, bundle-aware)

| Cause | SOL/day | Share |
|---|---|---|
| No engine | 35.6 | 10.5% |
| Never targeted (thresholds / gate / skips) | 214.9 | 63.3% |
| Far-leader skip | 11.4 | 3.4% |
| Armed but tries never landed near the dump | 4.4 | 1.3% |
| Landed first, limit failed | 0.7 | 0.2% |
| Behind, far leader | 3.6 | 1.1% |
| Behind a pre-sender | 6.6 | 2.0% |
| Behind a reactive bot on an EU leader | 14.4 | 4.3% |
| We were first | 3.2 | 0.9% |
| The dumper's own bundle | 44.6 | 13.1% |

## By region and client
- **Region:** we are first EU 9.0%, US-East 11.1%, Asia 9.8%. The loss is NOT concentrated on US-East.
- **Client:** we are 40–80 ms late on every client, worst on Jito / Firedancer.

## Paths that reach the front (lift = share of first buys ÷ share of all buys)

| Path | Lift |
|---|---|
| Pre-senders | 2.2–2.7 |
| soyas (Harmonic) | 2.51 |
| solami_beam (Jito) | 2.07 |
| nozomi | 1.35–1.70 |
| speedlanding | 1.1–1.85 |
| No tip | 1.13–1.24 |
| astralane | 0.78–0.90 |
| **Helius (OUR pre-send path)** | **0.71–0.84** |
| Jito-tipped | 0.45–0.61 |
| 0slot | 0.38–0.45 |

## Changes (INFERRED; send-path changes need owner OK)
1. **Dense, evenly spaced pre-send tries:**
   - one every 10–20 ms, timed to the leader's clock, through the fastest path per client (nozomi on BAM/Harmonic, + speedlanding / soyas on Harmonic, solami / soyas on Jito, TPU on Firedancer);
   - low CU price.

   | Our landing after the dump | SOL/day vs +2.07 today | 10% fewer followers |
   |---|---|---|
   | 50 ms | +2.6 | |
   | 20 ms | +6.3 | +5.1 |
   | 10 ms | +9.0 | +7.3 |

   - Extra failed tries cost ≈ −0.9/day. **Net ≈ +4..+8 SOL/day.** Needs a shadow / A-B of per-client landing.
   - Risks: Helius 429; nozomi deprioritizing failing flow.
2. **Regular fires ≤ 20 ms after the dump** (preconfs / shred trigger): +2.5/day; 10 ms +3.7.
3. **US-East node:** +0.1..+0.4/day; more only after fix 1.
4. **Jito bundles:** ≈ 0.
5. **24/7 running:** ~+0.3/day.

## Contradictions resolved
- "We land first on 81% of shared dumps" was vs the slow bot 248 (66 ms). Against the true front on paying dumps we are first 9.4%.
- "Pre-send fills at 22–29 ms" counts only tries that filled; on paying dumps our first try after the dump is a median 83 ms.

## Addendum (10-28 ~04:30 PKT): live k4 vs k8 check (g0–g7; tables g2, g4, g5, g6, g7)
**Data:** k4 44.4 engine-hours vs k8 9.2 engine-hours (different days, not a clean A/B).

**The rate cap that bites is the per-path `max_per_sec` in the server toml (MEASURED):**

| Server | helius-ps cap | Effect |
|---|---|---|
| FRA (dip_prod.toml) | 20/s | FRA r26 refused **42%** of tries |
| AMS (dip_ams.toml) | 30/s | 18–20% refused |

One k8 window needs 37.7 tries/s.

**Tries:**
- k4 spacing 53 ms, k8 27 ms; no bunching.
- Landing 40% send slot / 54% next / 6% later for BOTH k4 and k8: the Helius path's ~85 ms send→landing delay dominates.
- **Correction to the main report:** tries are not at the end of blocks.

**Paying dumps:**

| Group | First try lands (median) | We were first |
|---|---|---|
| k4 | 65 ms | 20% |
| k8 | 96 ms | 22% |

- **Where a pre-sent try was in flight:** median 34 → 24 ms; first 35% → 45% (+9.7 pts [+1.9..+17.2]).
- **Where none was in flight:** 41% (k4) / 51% (k8) of paying dumps, in the whale's own arming slot; we are ~150 ms late and first 0%. **These hold 57% of paying front value.**
- **Realized SOL per engine-hour** (dates differ): k4 +0.051, k8 30/s +0.165, AMS33 +0.301, FRA k8 +0.220.

**Revised estimate:**
- **Denser pre-send** (k8 that actually gets ~40/s; raise the helius-ps cap): **+0.3..+2.5 SOL/day at 24/7, central +1.4**. The earlier +4..+8 was WRONG. k16 adds little.
- **The bigger lever is the dumps in the whale's own slot:** a fast reactive send landing ≤ 20–30 ms after the dump, +1..+3/day INFERRED. Ours lands ~60 ms (regular) / ~150 ms (pre-send re-sign).
- Raising caps or adding a reactive path needs owner OK.
