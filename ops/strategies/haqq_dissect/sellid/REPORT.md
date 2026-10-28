# Analyst N (sellid): his sells react to PAUSES, not to specific wallets (10-28 ~04:35 PKT)
Saved by the main session from the agent's reply. Code: this folder (s1–s12). Data: /home/moiz/sniper-data/haqq_dissect/sellid/ (s11, s2, s3, s4, s6, s6b, s7, s8, s9 .txt; s12_presell.tsv.gz; s10_examples.json).

## Verdict (MEASURED, 10-22 → 10-28)
- **The wallet-trigger hypothesis is rejected.** Sell vs random moments in the same lots:

  | Bot | Outside buy in last 212 ms | No outside buy in last 1 s |
  |---|---|---|
  | 247 | 0.65× [0.63..0.67] | **1.51×** |
  | 248 | 0.82× | **1.41×** |

  Holds on every day. There is no bump at his reaction delay; the hazard rises only 0.6–2 s after the last buy, i.e. the wave/pause pattern.
- **Known lists are not triggers:**

  | Bot | fbots | cohort | Named dip bots | Identical-size clusters |
  |---|---|---|---|---|
  | 247 | 0.81 | 0.81 | 0.65 | 0.66–1.25 |
  | 248 | 0.97 | 0.99 | 0.88 | 0.66–1.25 |

  Walk-forward top-N wallet lists appear before his sells LESS than at random (0.36–0.78×).
- **Co-sellers** (HXHoJwF5, Fau6ESkZ, …) precede 248's sells 1.4–1.7×: a common cause (the same pause logic), not a signal. They add ±0.1 SOL on our fills.
- **On our fills, wallet rules lose to the wave exit:**

  | Fills | Current exit | Wave exit | Best wallet rule (chosen in-sample) |
  |---|---|---|---|
  | Pre-send, 1,143 | +7.48 | **+11.02** | +9.24 (−0.9 SOL/day vs wave) |
  | Regular, 596 | +2.63 | **+6.22** | +6.23 (≈ 0 vs wave) |

- **On his own lots the wave exit reproduces 94% (247) / 85% (248) of his exit P&L at our sell delays:**

  | Bot | His exit | Wave exit | Best wallet rule |
  |---|---|---|---|
  | 247 | +53.9 | +50.7 | +25.5 |
  | 248 | +57.7 | +49.2 | +31.9 |

- **247's < 1 s winners vs its 4–8 s losers:** early flow differs (2.7 vs 1.1 SOL of outside buys in 400 ms; bigger entry dumps), but prediction is weak (AUC 0.52–0.69), and a ride-if-busy rule loses walk-forward.
- **Where he beats the pure wave rule:**

  | Hold | His exit | Wave rule |
  |---|---|---|
  | 1–2 s | +31.4 | +19.2 |
  | 2–4 s | +13.7 | +5.9 |

  INFERRED lead: a shorter pause threshold when the lot is in profit.

**Recommendation:** ship the wave exit (C's spec). Don't build a wallet-watch trigger; at most log it for proof.
