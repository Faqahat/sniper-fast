# Plan for the rest of 10-25 (after you wake up)

## Where we are (one paragraph)
- **The paper model is right.** Live loses because our buys land a median **58 ms** after the dump, not 35. 22% miss the dump's block. Faster bots take the good dumps and we fill the leftovers.
- **Our engine is fast** (2.7 ms to send). **94% of the delay is after the send.**
- **Costs** (~0.0045 SOL per round trip + 2.5% pump fees) eat the thin edge.
- **Pre-send:** live matches paper, about break-even at 0.2 SOL. The "instant bots" are mostly the seller's own rebuy tool, plus a few dense pre-senders on creator dumps.
- **Today's goal:** make the normal bot **faster and cheaper**, measure it live, and fix nothing by guesswork.

## Done while you sleep (me)
1. **Frankfurt run 15** ends ~15:08 PKT.
   - Make its report.
   - Tally the full-day pre-send shadow (06:08–15:08) for its real daily average.
2. **Speed fixes (engine dip14)** when the agent finishes:
   - check the tests and the parity on recorded data;
   - stage the binary on both servers. NOT started.
   - Contents:
     - fire on the first sight of the dump, shadow mode first;
     - logging after the send;
     - skip Rakurai leaders;
     - relay probe tools;
     - leader-clock fix;
     - the Frankfurt feed-delay finding.
3. **Relay probe plan** with exact commands and cost (Jito and Harmonic leaders, one path per probe).
4. **Instant-bot walkthrough:** 4–6 clear Solscan examples (seller's own rebuy, a pro pre-sender, a chance landing, our own pre-sent buy).

## Your steps today (in order)
| # | Step | You do | Time | Max cost | Pass if |
|---|---|---|---|---|---|
| 1 | Walkthrough: instant bots, pre-send verdict | read / discuss | 15 min | 0 | – |
| 2 | **Speed shadow run.** Both servers on dip14 with "fire on first sight" in SHADOW: it trades exactly as today, only logs when it WOULD have fired. Rakurai skip on. | start both with the passphrase | 2 h | as a normal run | decisions match ≥ 99%; the ms saved is measured |
| 3 | **Relay probe.** Fail-by-design buys on Jito and Harmonic leaders, one path per probe, ~20 per path | OK + start | ~1 h | ~0.05 SOL (exact figure before you OK) | we know the fastest path per leader type |
| 4 | **Speed live A/B.** One server fires on first sight with the new per-leader routes; the other stays as today. Same model and size. | OK + start | 3–4 h | loss caps | median landing ≤ 40 ms (now 58), fill rate ≥ 55% (now 42%), net per fill ≥ 0 |
| 5 | **Fee test.** One server with a fixed low priority fee and a tight compute limit (haqqiUUX style); the other as today | OK | 3–4 h, can run with step 4 on the other server | small | landing no worse, cost per trip down ~0.001 |
| 6 | **Free studies (me, in parallel):** an exit that rides winners on crowded dumps (bots' exits beat ours by +5.3 mSOL per trade); pre-send v2 options (skip seller tools, 0.55 SOL, BAM only, creator-dump targeting) | – | – | 0 | a ranked list |

## Decisions I need from you
- **Model for both servers during the speed tests:**
  - **M2 (Recommended):** it trades ~10× more often on Amsterdam's leaders, so we get more samples.
  - IMIT1, as on Amsterdam today.
- Amsterdam's leader list: keep the no-BAM list (BAM fills were losing there), or test BAM again once we are faster.
- OK for the relay probe (cost shown before start).
- OK for the fee test on one server.
- Pre-send: keep it as a free shadow only, or design v2 (after the walkthrough).

## Budget
- Loss budget left: **Frankfurt ~0.46 SOL, Amsterdam ~0.22 SOL** (of 0.5 each).
- The speed and fee tests run inside those caps. The probe costs about the fee of each failed buy.

## What success looks like by tonight
- Landing measured faster (target ≤ 40 ms median, < 15% next-block spills).
- Fill rate up (target ≥ 55%).
- Cost per round trip down.
- With those, the corrected replay says the normal bot moves from about +1 SOL/day toward +5–9 SOL/day (one-night estimate; we confirm live, not on paper).

## Ready-to-run commands (staged 10-25 ~11:30 PKT)
- Engine dip14 (sha256 e349fb36…) and run script (md5 392a5c91) are on both servers. Nothing is started.
- Details: `ops/dip/speed/fixes/FIXES.md`.
- Tests: lib 698 / bin 40 passed.
- Shred-fire parity on 14.8 h of chain data: 0 wrong decisions. It covers 43% of IMIT1 picks and 62% of M2-gate picks.
- The rest still waits for the executed feed, as today.

**Step 2: speed shadow, ~2 h.** The bot trades as today, plus three things:
- logs when "fire on first sight" WOULD have fired;
- records the new clocks and the feed delay;
- skips Rakurai leaders.

The model shown is M2 (recommended). For IMIT1, remove `--m2-mode gate`.

Amsterdam (idle now):
```bash
sudo bash /root/prod/run_dip_prod.sh --region ams --run 17 --trades 60 --size 0.35 --tier wider --tp off --sl 0.5 --hold-slots 5 --dev-list /root/sniper-dip/dev_list.txt --dev-size 0.55 --near /root/sniper-dip/near_leaders_ams_nobam.txt --nonce /root/prod/nonce_ams.txt --fallback ck --m2 /root/dip/m2_v3_reg4_top25.json --m2-mode gate --presend --sell-fanout helius-swqos --shred-fire shadow --clock2 --feed-lag --defer --skip-clients Rakurai --minutes 120
```
Frankfurt (after run 15 ends ~15:08 PKT):
```bash
sudo bash /root/prod/run_dip_prod.sh --run 16 --trades 60 --size 0.35 --tier wider --tp off --sl 0.5 --hold-slots 5 --dev-list /root/sniper-dip/dev_list.txt --dev-size 0.35 --near /root/sniper-dip/near_leaders_fra.txt --nonce /root/prod/nonce_fra.txt --fallback ck --m2 /root/dip/m2_v3_reg4_top25.json --m2-mode gate --presend --sell-fanout helius-swqos --shred-fire shadow --clock2 --feed-lag --defer --skip-clients Rakurai --minutes 120
```
Go / no-go (I check it): 0 wrong decisions; the phantom-dump rate on picks; ms saved on the picks it covers.

**Step 3: relay probes** (fail-by-design buys, ~0.0005 SOL each; at most 0.162 SOL per region, ~0.12 likely). Frankfurt commands are in FIXES.md (P1 Jito 6 paths × 20, P2 Harmonic 4 × 20, P3 tipped vs tipless).
- Correction for Amsterdam: its config names the LandX path `landx-fra3` (not landx-ams2), and it has no `near_leaders_5ms.txt`. Use `--region ams --near /root/sniper-dip/near_leaders_ams.txt` with `landx-fra3`.

## What the validator-code study changes (ops/dip/speed/clients/CLIENTS.md, ready 10-25 ~12:00 PKT)
Recommendations only; each needs your OK.
- **Jito** (our worst, 54 ms vs 26):
  - Stop the 0.001 Helius "Sender Max" copy. It goes into Helius's tip buffer and landed at 121 ms. Use keyed helius swqos-only instead.
  - 39 of 146 Jito leaders sit behind a Jito relayer that holds plain txs 50 ms: we land at 72 vs 43 ms on the others. Test a direct block-engine copy there, or skip those leaders (6% of slots).
- **Harmonic** (41 vs 27): builders sort 50 ms buffers by fee, and arrival decides.
  - Keep nozomi as the main copy (23 fills / 3 fails). helius-swqos (0 / 3) and staked-rpc (2 / 29) mostly land late as failures.
- **BAM** (29 vs 18–21): 20 ms auction rounds ranked by fee per CU.
  - Keep nozomi.
  - Bid partly with a Jito tip on the staked copy, so failed buys are cheaper.
  - Apply for BAM direct bundle ingest: revert-protected, so failed buys cost 0.
- **Rakurai:** holds our txs a slot. Skip it (dip14 `--skip-clients Rakurai`).
- **Firedancer:** we already beat rivals (23 vs 29 ms). Never send a jito-bundle copy sharing the nonce there.
- **Structural:** with Alpenglow, a leader's first block records ≤ 144 ms (blocks 2–4: 200 ms). That is why the first slot of a Jito turn spills; no path fixes it.
- **New lever: preconfirmation feeds** (BAM via Helius, Harmonic via Triton) show a dump 5–10 ms before shreds. Estimate: +8–12 fills per 309 on BAM. Shadow-log the lead first; Helius charges credits per message.
- **Probe design:** our always-fail probes cannot see routes that drop failing txs (Jito bundles, Helius top tier, BAM direct, Harmonic endpoint). Add a cheap always-succeed probe that only locks the bonding curve.
- **Cheap check:** log Constant-K's route header. Over its plan's staked cap it silently re-sends from its own node every 420 ms.
- **Effect on the steps above:**
  - Step 3 (probes) should include keyed helius swqos-only on Jito, and the relayer-fronted Jito leaders as a separate group.
  - Step 4's ROUTES should drop the Helius 0.001 copy on Jito and keep nozomi first on Harmonic and BAM.

## Pre-send v2 research (ops/strategies/presend/V2_OPTIONS.md, ready 10-25 ~12:05 PKT; a fresh-hours check appends ~13:30)
- **Replay validated against probe 1:** 23 vs 20 fills on the same 118 windows. On the 18 shared windows, P&L after pump fees +0.0077 vs +0.0080 live. Probe 1's settings give +0.9 SOL/day (−0.1 to +2.0), consistent with live ≈ 0.
- **Recommended B6:** whale ≥ 6%, 0.55 SOL, 8 attempts per slot.
  - **+7.8 SOL/day** on test days (90% +5.5 to +10.2); pessimistic landing +5.0. All 4 days positive.
  - It needs a second attempt path (~40 sends/s) and one run-script line to pass `--presend-whale-pct`.
- **No-new-path fallback A6** (4/slot, whale ≥ 6%, 0.55): +5.4/day. Runnable now with whale ≥ 5% (A): +4.6/day.
- **Upside, unproven:** 1.0 SOL C6 +11.8, D6 (12/slot) +14.1.
- **Not worth it:** creator-dump targeting, T1t, leader filters, skipping seller tools, create-slot triggers, an 8% limit.
- **Why probe 1 was ≈ 0:** at 0.2 SOL the fixed tx costs are ~1% of size (0.37% at 0.55), and it ran in a weak hour (06–12 PKT).
- **Correction:** probe-1 FILLS landed a median **29 ms** after the crossing; 53 ms was all post-crossing attempts.
- **Risks:**
  - The profit = the 541 consistent-winner bots buying after us: without them B6 −7.1/day.
  - The 6% threshold was chosen after seeing a split that included test data.
  - The landing at 8/slot and the follower model at 0.55 SOL are model steps.
  - Hourly swings: the worst hour is −0.35.
- **Probe 2 (your OK):** B6 on Amsterdam, 30 fills, 0.06 SOL fee cap.
  - Needs the second path. For path choice, CLIENTS.md says nozomi is the copy that lands on BAM / Harmonic.
  - Needs the script line.
- **Engine bug found (code read):** an empty class like `jito=` in `--presend-live-routes` makes the attempt sender panic (divide by zero). Avoid empty classes; fix in the next build.

## Exit study: "hold the winners" (ops/dip/exits/EXIT_MODEL.md, ready 10-25 ~12:50 PKT)
- **Verdict:** a learned exit does NOT reliably hold winners out of sample.
  - Holding longer: +1.6 SOL/day on training, but only +0.4 on M2 on unseen hours (CI −0.1 to +1.0), −0.03 on IMIT1, ~0 on our 62 real fills, and 0 in a time-reversed test.
  - It helps on crowded dumps (3+ fast bots buying) and loses about as much on quiet ones.
- **Keep today's exit** (hold 5, no stop). Runs 10–14's exit (hold 6, SL −10%) was worse: IMIT1 −0.5 SOL/day, real fills −0.23.
- **Optional tiny tweak:** if no outside buy in the 2 slots after our buy, sell at slot +3 instead of +4. +0.13–0.15 SOL/day on the test hours, +0.06 on real fills, marginal.
- **Takeaway:** riding winners needs a faster landing, not a smarter exit.
- **Fresh-hours check** (10-25 09:56–12:56 PKT; never used for any choice):
  - B6 **+0.38 SOL in 3 h (+3.0/day)**, 34 fills, +0.011 per fill; pessimistic landing +1.5/day.
  - Others: A6 +1.0/day, C6 (1.0 SOL) +4.1/day, B (whale ≥ 5%, 8/slot) +3.5/day.
  - Probe 1's settings: −0.7/day.
  - B6 held up, but lower than on test (+7.8). Midday is quiet and the first hour carried it. This is a sanity check, not proof.
