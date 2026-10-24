# Other bots' winning strategies on pump.fun (last ~46 h)

10-24 ~20:30 PKT. Read-only study: no trades, no server touched. MEASURED = counted from chain data; INFERRED = my reading.
Scripts: ops/strategies/s1_trips.py … s9_qcheck.py. Outputs: /home/moiz/sniper-data/strategies/ (rank.txt, families.txt,
cards/, llm/labels_cards.jsonl, llm/families_llm.json, replay_select.txt, qcheck.txt).

## Bottom line
1. **The method works (MEASURED).** With no hints it found the three known dip-backrun wallets:

   | Wallet | Rank | 46 h profit |
   |---|---|---|
   | haqqiUUX | #4 | +90 SOL |
   | DYXDDrZC | #13 | +42 SOL |
   | HkQ7hMjy | #17 | +37 SOL |

   - 88% of HkQ7's buys come right after a ≥1 SOL sell in the same block; an average trader does that 7% of the time.
   - Haiku marked all three as dip-backrun without being told. It also marked all 55 wallets of the three dip families,
     and none in F4, F6, F7, F8 or F10.
2. **424 wallets were consistently profitable (MEASURED):** ≥30 round trips, profit on both days and in most 6-hour blocks.
   Together they realized **+3,166 SOL**. Insiders, the mayhem agent and holders are left out. They form 10 families; the dip
   families (F1+F2+F3) make about +586 SOL of that.
3. **One new opportunity a bot like ours could do: buy first on a quiet token (F7, "quiet bait").**
   - **Trigger:** a token ≥150 slots old (~32 s), quiet for ≥20 slots (~4 s), curve still ≤45 SOL. Someone buys 0.9–3 SOL.
   - **What follows:** in 62–65% of these events other bots buy in the same or the next slot (MEASURED).
   - **Pay-off:** the first buyer sells into them about 21 s later.
   - **Replay:** rule chosen on day 1, tested on day 2: +209 SOL on 4,977 events, +3.4% per SOL, 49% wins. Still positive
     without the best 1% of events.
   - **Real money:** the wallets that really made these buys realized +199 SOL on day 1 and +213 SOL on day 2.
   - **No speed needed:** we would be the trigger, not the racer.
4. **Too fast for us (INFERRED):**
   - **F4, big-buy backrun scalp, +194 SOL:** these wallets land a median of 2 transactions behind the trigger buy. That
     looks like being placed in the same bundle.
   - **F1, the fastest buyers after the creator sells:** they land 5–13 transactions behind the creator's sell.
   - We land about 65 transactions behind, and the replay agrees: copied at 35–50 ms, both strategies lose.
5. **Not copyable:** about 200 insider wallets (creators and create-slot bundles) made about +11,700 SOL. The biggest is
   bwamJzzt at +1,313 SOL.

## Families (46 h realized profit, MEASURED)
| # | What they do | Wallets | Profit | Per SOL | Hold | How fast (tx after trigger) | Us? |
|---|---|---|---|---|---|---|---|
| F10 | Mixed late swing (catch-all) | 80 | +567 | +7.6% | 20 s | mixed | partly |
| F8 | Follow big buys, add more, hold 15 s–5 min | 27 | +566 | +4.0% | 16 s | mostly 1–10 | no |
| F9 | 0.3 SOL scalper on busy tokens | 31 | +560 | +1.9% | 17 s | ~80–110 | thin |
| F2 | **Big-sell dip backrun (ours)** | 29 | +352 | +1.4% | 5 s | ~93 | yes, near leaders only |
| F6 | Momentum buy + sell in pieces | 14 | +274 | +5.0% | 13 s | ~45 | no (replay loses) |
| F7 | **Quiet-token first buy** | 25 | +202 | **+11.6%** | 68 s | not a race | **yes** |
| F4 | Big-buy backrun, out in 0.8 s | 38 | +194 | +3.0% | 0.8 s | **2** | no |
| F5 | Early-launch momentum | 30 | +165 | +3.9% | 7 s | ~100–150 | weak |
| F3 | Dip buy, fixed 30 s timer | 8 | +123 | +1.4% | 30 s | ~100 | no (replay loses) |
| F1 | Buy right after the creator sells | 18 | +112 | +3.1% | 2 s | 5–13 (top) / 54–107 | no (replay loses) |

- **Speed (INFERRED):** a block averages ~395 transactions per 212 ms, so 65 transactions ≈ 35 ms ≈ our landing.
- **Crowding (MEASURED):** a typical winning entry has 2–5 wallets starting a trade in the same token in the same slot.
- **Shared operators (INFERRED from identical fee and tip settings):**
  - F4 looks like one operator with 38 near-identical wallets.
  - Six F9 wallets share fee 150,000 + 1.1M tip and sizes 0.25 / 0.3 / 0.45 SOL.
  - One operator (fee 1,105,000 + 1.1M tip) runs three strategies from different wallets: dip backrun at 0.6–0.9 SOL,
    a 30 s-timer dip at 0.5 SOL, and 0.3 SOL scalps.

## Replays
Costs: pump fee 1.25% each side, +0.0035 SOL per round trip, 0.0005 per failed buy. Guard +5%. Each rule was chosen on day 1
(R2) and run unchanged on day 2 (R3).

| Test | Day 1 | Day 2 | Verdict |
|---|---|---|---|
| F7 quiet-token bait, sell after 21 s | +212 SOL / 4,684 events | **+209 / 4,977** (+3.4%/SOL) | **holds** |
| F6/F4 momentum at 35 ms (best day-1 rule) | +0.5 | −11.6 | no; none of the top 20 rules held |
| F1 creator-dump backrun at 35 ms (all dumps) | −73 | −82 | no |
| F3: 30 s timer instead of a 1 s exit (best dip subset) | −23 vs +6 | −38 vs +9 | no, short exits win |
| Best plain dip rule at 35 ms (sell ≥2 SOL, drop ≥15%, token 25–100 slots old, exit 1 s) | +6.6 | +10.0 | thin, as known; ~0 at 50 ms |

**How the quiet bait works (MEASURED):**
- When a follower buys within 1 slot, the event makes +6.4% to +7.5% per SOL.
- When nobody buys within 5 slots, it loses about 2.3% per SOL.
- 56–59% of the follower SOL comes from bot-like wallets (≥100 trades in 48 h).
- Fresh or occasional wallets profit as baiters on both days. Bot-like baiters draw fewer followers (+2.2% per SOL instead
  of +2.8% to +4.4%), so the bait should come from a fresh wallet.
- **Sharper version** (curve ≤35 SOL, buy 1.2–2.1 SOL, sell after 21 s): +59 SOL on day 1 (+6.0%/SOL) and +48 SOL on day 2
  (+4.9%/SOL), about +0.075 SOL a trade. These thresholds were set after seeing both days, so this is not a clean
  out-of-sample result.
- Launch labels (Haiku): coherent listings, an X post link and fun score 2 do slightly better (+4–6%/SOL). Random-letter and
  bare-name tokens do worse (+2–3%).

## Narrative trends (MEASURED)
- In every 6-hour block, winners traded the same theme mix as everyone else; the theme gives them no edge.
- Winners' realized profit by theme follows volume: "other" +679, crypto/finance +447, animal +379, AI/tech +367,
  news +351, meme characters +344.

## Excluded (MEASURED)
- 497 insider wallets: trades mostly in the create slot, or the creator, or the create-slot bundle.
- The mayhem agent BwWK17cb: it trades only mayhem launches and never sells 73% of its positions, so its +333 SOL is paper.
- 9 holders with more than 30% of positions still open.
- Tokens moved between a bot's own wallets: sells are capped at the tokens the wallet bought (ARu4n5mF went from +125 to −371).
- Positions still open at graduation are left out of the profit numbers.

## Caveats
- **Our own bait is untested.** The replay uses other people's bait buys and the followers' real reactions to them. Only a
  live test shows whether followers react the same way to our buys on tokens we pick. Follower bots may learn to ignore a
  repeat wallet.
- **Shared opportunity:** about 4,800 baits a day already split roughly +200 SOL a day; more baits compete for the same
  followers.
- **Not covered:** funding links between wallets (no transfer data); which relay each bot uses (tip amounts only); the last
  hour of R3 (not synced yet).

## Next steps
1. **Quiet bait live probe — needs the owner's explicit OK.** It conflicts with the "race pools only" rule, and paper can't
   test it.
   - Setup: 20–30 baits from a fresh wallet, 1.2 SOL each, on tokens with curve ≤35 SOL, quiet ≥20 slots, ≥150 slots old;
     sell after 100 slots.
   - Measure: follower-within-1-slot rate (the data says ~63%) and profit per trade (the data says +0.04 to +0.075 SOL).
   - Typical worst case: about −1.5 SOL.
2. **Free first step:** identify the follower bots that buy within 1 slot of these baits and learn their filters.
3. **Leave the rest:** keep the dip bot as is (its generic edge only exists at ~35 ms). Drop F4, the fastest F1 wallets, F6
   at our speed, and the 30 s timer.

## API spend
- This study: $0.331 (test call $0.002, batch of 300 wallet cards $0.305, 10 family summaries $0.023).
- Separate launch-labeling batch: $4.67 (113k launches).
- Ledger: llm/spend.json.
