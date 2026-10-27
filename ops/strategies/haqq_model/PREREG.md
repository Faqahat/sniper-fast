# haqq_model: pre-registration (written 10-28 before any modelling, PKT)

Wallet: haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq ("haqq").

## Unit and population
- One pump.fun token per create seen on our chain tape (multi-day tape built from the host's recording copies, 10-23 19:26 to 10-27 23:20 PKT).
- Tokens are kept only if the 5-minute bin of their create and the next bin each have at least 90% of slots recorded. Gaps would hide haqq's trades and create false negatives.
- Tokens created in the last 15 minutes of the tape are dropped, because their label is censored.

## Decision time
- Primary: create slot + 14 slots (about 3.0 s at 0.212 s per slot), which is haqq's median first-trade age.
- Also reported: + 0 slots (end of the create slot), + 5 (about 1 s), + 24 (about 5 s) and + 47 (about 10 s).

## Label
- y = 1 if haqq (as trade user or tx signer) has at least one trade on the mint anywhere on the tape.

## Features
- Only trades with slot ≤ the decision slot are used.
- haqq's trades on the token itself are removed before any feature is computed.
- History features (creator, wallets, haqq's own activity on OTHER tokens) use only tokens created at least 10 minutes before the hour block. This is an expanding, causal history.
- Using haqq's trades on other, earlier tokens is allowed, because they are public on chain at decision time.

## Time split (no shuffling)
- Train: created 10-23 19:30 to 10-26 05:15 PKT. The first ~12 h only warm up the history features.
- Validate: 10-26 05:15 to 10-26 23:15 PKT (18 h). Used for early stopping and to pick the threshold.
- Test (held out): 10-26 23:15 to 10-27 23:05 PKT, the haqq_sel window. It is never used for fitting or for picking a threshold.

## Scores (on test)
- Threshold: the highest score at which VALIDATION recall is at least 80%, then frozen.
- Primary metric: test recall ("match %"), the share of haqq's test tokens the model picks. Target: at least 80%.
- Also reported:
  - precision;
  - picked set size against all tokens;
  - F1;
  - ROC AUC;
  - the precision/recall curve;
  - recall split by whether haqq had already traded the token by the decision time (informational).

## Replay on test (run-28 config)
- Pre-send: 0.50 SOL, k4, QUIET on, the R28 donor landing and calibration (haqq_sel/h3_presend.py). The stream is the triggers on picked tokens, with the trigger at or after the decision slot. A trigger before the decision time cannot be filtered yet, so it is dropped from the MODEL stream.
- M2: 0.55 SOL, haqq_sel's M2 pipeline. M2 picks on picked tokens at or after the decision slot.
- Compared against:
  - ALL tokens;
  - haqq's tokens (hindsight);
  - HQ-KNOWN (he traded the token before the trigger).
