# haqq dissection: findings so far (main session, 10-28 ~03:10 PKT, overnight)

Simple summary first; details in each analyst's REPORT.md (lim, exit, exec, gap, pos). Spot-check list with tx links: BOT_SPOTCHECK.md.

## What haqq really is (MEASURED)
- **About 7 separate bots share one wallet.** Each tx carries a code in the last 3 digits of its compute price, and a lot's buy and sell have the same code.
- **Two dump-buying bots make ~80% of his money:**

  | Bot | Size | Profit over 6 days | Per trade | Positive days |
  |---|---|---|---|---|
  | 247 | 0.40 SOL | +90 SOL | +10.5 mSOL | 6 of 6 |
  | 248 | 0.30 SOL | +84 SOL | +7.5 mSOL | 6 of 6 |

  The smaller bots (244, 226, 231) add about +6/day.
- **His "multi-buy" tokens are several bots buying the same token.** A single bot almost never adds to its own position. Your GMGN view is right looking back: tokens he buys 3+ times make all the money and 1-buy tokens lose. But that is decided by what happens after the buy: the token got busy.
- **He does NOT pre-send and is NOT faster than us.** His dump-buys land 45–80 ms after the dump; ours land 21–55 ms (pre-send fills ~28 ms).
- **His small buys have no price limit; his costs are 0.79 mSOL per trade.** Ours are 2.6 (pre-send) and 4.6 (regular), mostly on sells: 1.8 mSOL per sell vs his 0.27.
- **His exit:** he holds while outside buys keep landing and sells when they stop (the "wave" exit). That explains 85% of his exit profit.

## Your three hidden test tokens (not shown to the agents)
On all three, the trades are from bots 247, 248, 244 and 226. The pattern:
1. a big holder or dev sells in chunks;
2. a bot buys after each sell;
3. it holds through a drop with no tight stop;
4. it sells into the next coordinated buy wave (identical-size bot buys).

On ENsLg our pre-send bought the first dump before him, at the same slot, but our 2-slot exit sold before the wave.

## What does NOT close the gap (proven with numbers)
- **Loosening our +5% price check.** Replayed at the exact chain positions where our failed buys landed, it loses: −7 SOL over 4 days with no limit.
- **Copying his picks with our current style.** Even knowing all his events in advance, our style makes only ~0 to +6 SOL/day on them.
- **Reactive adds** (buying again while holding). They lose in every causal test.

## What DOES help (each needs your OK before live)
1. **A faster "wave" exit on our own fills.** Sell at the first short pause in outside buying instead of after 2 or 5 slots. Independently re-checked by me: better on every day; about +1–1.6 SOL/day at our pre-send volume.
2. **His cheaper tx recipe**, mainly sells with one tip on a durable nonce and lower compute. About +0.9 SOL/day.
3. **Switching regular buys off** (done for FRA run 27). Regular lost −0.40 in run 26.

## Still being built (agents running now)
- **Re-arm pre-send:** after a whale dump on a token already paid, arm pre-send for its next dumps. First replay: about +5.4 SOL/day calibrated, positive all 4 test days. Now being rebuilt with the engine's exact logic.
- **Who-will-be-followed selector:** buying big-holder dumps in their own slot pays +6.6 to +10.8 SOL/day, but only on the dumps haqq picks. Predicting those in advance is the missing piece.
- **"Become bots 247/248":** imitate their picks at our faster landing, with the best exit and cheaper costs.

After these, an independent agent will try to break the winner, and it will be tested on recordings made after the rule is frozen (paper), plus your three tokens.
