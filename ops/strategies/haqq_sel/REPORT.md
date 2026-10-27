# haqq's tokens through our engine (agent, 10-27 ~23:50 PKT)

Saved by the main session from the agent's reply (the harness blocks subagent report writes).

Owner request: take the tokens haqqiUUX traded in the last 24 h (10-26 23:15 → 10-27 23:15 PKT), run only those tokens through our engine's logic at 0.50 SOL, report P&L at ideal / 50% / 30% landing, and compare with the same engine on every token. haqq's trades were used only to build the token list.

## Token list (MEASURED)
- 3,051 mints, 11,830 haqq txs.
- His first trade on a token comes a median 3 s after its create.
- His tokens hold 50% of all pre-send triggers and 81% of all M2 picks.

## P&L at 0.50 SOL over 24 h, haqq's tokens only (INFERRED; ranges = 5–95% bootstrap)
| Scenario | Pre-send | Regular M2 (AMS) | Total |
|---|---|---|---|
| (a) ideal | +27.8 (+23.8..+32.1), 702 fills | +1.71 (+0.47..+2.97) | +29.5 |
| (b) 50% land | +13.8 | +0.79 | +14.6 |
| (c) 30% land | +8.2 | +0.43 | +8.6 |
| (d) our measured landing | +6.5 | +1.19 (50 ms row) | +7.7 |
| (d') run-28 calibrated / 75 ms | +4.2 | +0.08 | +4.3 |

All tokens, same engine: ideal +32.8, 50% +16.1, 30% +9.4, measured +8.4 (calibrated +3.6).

## Selection value
| Token set | Pre-send ideal per chance | Realistic per fill | Realistic total |
|---|---|---|---|
| All tokens | +0.0270 | +0.0104 | +6.8 |
| haqq's tokens | +0.0399 | +0.0175 | +6.5 |
| Tokens he never traded | +0.0066 | +0.0013 | +0.4 |
| Knowable: he traded it before our trigger | +0.0269 | +0.0155 | +2.5 |
| What that filter would drop | +0.0270 | +0.0087 | +4.4 |

## Verdict
- Not worth copying as a filter. "haqq traded it" is mostly an outcome: he and other dip bots show up where a dump gets bought.
- 396 of his 702 chances are on tokens he first traded at or after our trigger, which we could not know when arming.
- The knowable version is no better per chance than the whole market (+0.0269 vs +0.0270), and it would drop +4.4 of the +6.8 SOL realistic pre-send profit.
- M2 already picks his kind of tokens (81% of its picks).
- The lever is a causal "bots will come" signal: the tokens he never traded are where pre-send's losers sit.

## Files
- Code: this folder (h0–h6 scripts).
- Data: /home/moiz/sniper-data/haqq_sel/ (tokens.json, presend_tables_*, m2_tables.txt, tab/).
