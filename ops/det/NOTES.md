# det audit: launch DETECTION and SEND PATHS (2026-10-18)

The work copy is `/root/sniper-det`. It was copied from `/root/sniper-fast` at 19:20 BST and includes the other agent's
race-gate source. Nothing in `/root/sniper-fast` was edited, built or killed, and AFTER was **not** copied over it.

Nothing was traded live and nothing was sent. The only network actions were keep-alive pings, `simulateTransaction`,
an `--unwrap` dry run without `--live`, and RPC reads.

| binary | md5 | what |
|---|---|---|
| `/root/sniper-det/snipe_engine.BEFORE` | 8f79b252… | The copied source, unmodified. This is the arbx-fast build of 19:20 BST. |
| `/root/det/snipe_engine.BEFORE.frozen` | 0dc4c32d… | The arbx-fast binary of 19:13 BST, frozen at the start. The other agent's paper run uses it. |
| `/root/sniper-det/snipe_engine.AFTER` | 73d61236… | Detection fixes 1–8 below. **This is the binary in the paper comparison.** |
| `/root/sniper-det/snipe_engine.AFTER_FINAL` | df36da0d… | AFTER plus the send-path fixes, router-create firing, the PoH clock fix, the creator-fee rule and the path-dump fix. It only had paper smoke runs: 4–12 min each, 0 panics (`an_final_validation.txt`). |

- **Diff:** `/root/det/det.diff` covers 6 files: `snipe.rs`, `feeds/{grpc,entries,shred}.rs`, `send/mod.rs` and
  `bin/snipe_engine.rs`. The unmodified source is in `/root/det/src_before`.
- **Full outputs:** `/root/det/report.txt`.
- **Scripts:** `/root/det/*.py`.
- **Config for the recommended live test:** `/root/det/probe_det.toml`.

## BEFORE vs AFTER: paper, side by side

Both engines ran at the same time with the same feeds and the same `collect_blfwd.sh` flags. The run lasted 150 min,
from 18:48 to 21:18 UTC. The comparison window is 147 min of slots, checked against on-chain truth: every create
signed by the mint authority TSLvdd1 in the window, 5,512 that succeeded plus 392 failed create txs.

Two feeds can share the subscription: there were 3 engines running at once, no drops and no reconnects.

| metric | BEFORE | AFTER |
|---|---|---|
| Creates detected (coverage) | at most 95.0% by design: top-level creates with static accounts only. It logs only what it fires. | **99.3%** (5,476/5,512). The misses are 36 router CPI creates; AFTER_FINAL now decodes those. |
| Per feed, same feeds for both | erpc 98.8%, Kaldera 99.3% | Kaldera arrives first 89% of the time, by a median of 1.5 ms. erpc leads at p99 by 10 ms, max 71 ms. 0 stalls. |
| Fired | 217 | 1,249 |
| Truly eligible launches fired (SOL quote, create_v2, true dev 0.5–8 SOL, no fee or mayhem, host ok; n=1,278) | 212 (**17%**) | 1,193 (**93%**) |
| 4yFAz's launches in the window (29 bought; 21 truly eligible) | fired 7/29 | fired **21/29** (all 21 eligible); detected 29/29 |
| Contested: at least one outsider buyer in slot S or S+1, on chain | 84% (S alone: 62%) | 73% (S alone: 50%) |
| Paper PnL at floor (engine ladder) | +0.265/trade, **+56.7 SOL** (n=214) | +0.177/trade, **+214.2 SOL** (n=1,213) |
| Paper PnL at a 1.10x fill | +0.157/trade, +33.5 SOL | +0.072/trade, +86.8 SOL |
| **Realistic PnL**, his rule: entry right behind the creator bundle × 1.03 | +0.041/trade, **+8.7 SOL** (n=214) | +0.014/trade, **+16.7 SOL** (n=1,195) |
| Realistic PnL, derisk 30% + trail 0.95 + 40 s | −0.008/trade, −1.6 SOL | −0.008/trade, −9.6 SOL |
| Fired on launches whose create failed (phantoms) | 3 | 38 |

How the realistic PnL is modelled:
- The bundle classification comes from on-chain block S. It is identical to `bsplit2.py` on all 209 overlapping
  launches.
- Paths are rescaled to the true post-create curve.
- It includes our own price impact on both sides, the pump fee of 1.25% per side, and 0.010 SOL buy priority fee plus
  tip, plus 0.0003 SOL per sell.
- The "his rule" exit: on bundled launches, sell all at +10%, at 10 s, or at a −15% stop. On launches with no bundle,
  sell 30% at 1.3x and the rest at 3x or at 20 s.

**Sanity check:** AFTER's sized-dev subset (218 fired) reproduces BEFORE exactly: the same launches and the same PnL.

**AFTER split by dev-buy family:**
- The 1,031 newly admitted cap-family launches make +0.158/trade at floor.
- At realistic entry they make only +0.008/trade: median −0.057, 39% wins, +8.0 SOL in total.
- They are less contested (71%) and include 14 of 4yFAz's 21 picks.

The detection fix finds the launches. **On the new launches the realistic edge is about zero.** Either selection or
a better landing spot is needed to turn the extra coverage into profit.

## Problems found (evidence → impact)

### Detection

1. **The dev-buy read ignored cap-family buys** (`detect_launch`).
   - On chain the dev buy is cap-family in 59% of creates (91% of the creates that have a dev buy); buy_v2 with a
     u64::MAX cap alone is 30%. The old read counted those as 0 SOL.
   - Run window: of 1,485 creates with a true dev of 0.5–8 (TradeEvents), the old read kept **15%**. The new read
     keeps **94%**, and 1,392/1,485 are within 5% of the truth. All 90 misses are router CPI creates.
   - Paper: 17% vs 93% of truly eligible launches fired; 7 vs 21 of 4yFAz's launches.
2. **Non-SOL quote launches were read as SOL.**
   - They are **27.3%** of creates: the PUMP token, `A7bdiY…`, USDC and others.
   - The quote mint is create_v2 account [16]; SOL launches have only 16 accounts. The dev amount is in quote units,
     and our WSOL buy reverts on these launches.
   - BEFORE fired on 0 of them in the window: none had a sized quote amount in band. The read itself was wrong,
     though.
3. **Legacy `create` (SPL Token) launches are 0.7%** (39) of creates. Our buy is Token-2022 only, so it would revert.
   AFTER now skips them.
4. **CPI creates were invisible: 4.4%** (246) of creates.
   - Almost all come from pump's router `6Vo3245e…`: `CreateCoinAndBuyBondingCurveV3` (dev pays USDC, SOL curve) and
     the Jupiter variant (non-SOL quote).
   - Shreds carry no inner instructions, so there is no create to detect.
   - The router args are decoded (`router2.py`, 75 creates checked):
     - mint = account [1] (75/75);
     - creator in the args (72/75);
     - `min_tokens_out` priced on the curve = 0.98 × the true dev SOL;
     - tail byte [2] = mayhem, tail byte [3] = holder;
     - account [2] = WSOL on all 74 SOL curves.
5. **Accounts behind lookup tables were dropped.** `acct()` read only static keys. 0.5% of creates (29) have the
   bonding curve or its ATA in an ALT, and they were dropped even on Kaldera, which resolves them.
6. **Flags** (args vs CreateEvent, 5,491 create_v2):
   - mayhem and cashback match 100%.
   - holder_reward: 17 misses, all the 3-byte trailing form `(mayhem, cashback, holder)`. Now fixed.
   - creator_fee: 19 misses, all on **SOL** curves. The program drops the fee arg on SOL curves (19/19) and keeps it on
     non-SOL curves (1,176/1,176). Those 19 were wrongly skipped as creator-fee launches. Fixed in AFTER_FINAL.
   - The `creator` arg differs from the CreateEvent creator in **13%** (725). Our v3 buy has no creator_vault account,
     so it is unaffected. The race gate's creator-side classification and `--max-creator-sigs` do use that field.
7. **Failed creates fire as phantoms.** 7.8% of create txs (392) fail on chain, and shreds carry them. The engine
   fired 3 (BEFORE) and 38 (AFTER) phantoms. In paper a phantom has no curve; live it is a reverted buy and lost fees.
   This cannot be known at shred time.
8. **Feed stalls had no idle timeout.**
   - `st.message().await` could hang forever on a stream that stays connected but stops sending (HTTP/2 keep-alives
     still answered). This fits the overnight run's 6 watcher restarts and the 0-fire paper→live handoff.
   - The log-idle watchers also kill healthy BEFORE engines in quiet periods, because BEFORE logs only on fires.
9. **PoH clock assumed 400 ms slots.**
   - Mainnet slots now run about 213–221 ms with 64 ticks, so every PoH "ms" was **1.88× too large**. Create positions
     reached 394 "ms" inside a 213 ms slot.
   - Corrected: creates sit at median 109 ms into their slot (p25 57, p75 164).
   - Every earlier poh_ms-based analysis is mis-scaled.
10. **Close-leaders gate.**
    - The mapping is right: it matches `getSlotLeaders`.
    - It held ONE epoch, and an unknown leader counted as far, so after the next boundary every launch would be
      skipped. The boundary was 27 h away at test time.
    - The set covers only 334/658 leaders, **60.9% of slots**. It skipped 16 qualifying launches vs 15 fired (dual
      run) and 4 vs 6 (fast run).
    - It was built for tpu-direct. With relay senders, our own ping to the leader is the wrong distance.
11. **`max_inflight` skipped launches silently in live.** With the fixed read about 500 launches/h qualify; at a 40 s
    hold that is about 5 at once. `--max-inflight 2` would skip most of them. Paper waits instead of skipping: 0 waits
    in this run.
12. **Paper side.**
    - Curve polling is fine: 47 failures in 190k reads with 3 engines.
    - The path dump interleaved lines from concurrent trackers: 14 garbled lines out of about 1,250. Cause: `writeln!`
      on an unbuffered File.

### Send path

13. **The Helius 429s are the keyless limit.**
    - Helius docs: keyless Sender allows **1 request/s per egress IP per region**, and **rejected 429 requests count
      toward it**. With an API key the limit is 50/s.
    - `.env` has no Helius key.
    - In `live_land_helius.log`, a buy followed by a sell or another buy within about 1–2 s hit the limit: every sell
      and one buy (AnWD…). The cascade stretches the penalty.
    - The `/ping` keep-alive does not count toward the limit.
14. **send_slot / tpu SLOT was stale by 2–3 slots.** It came from a 250 ms getSlot poller. Example: send_slot
    458515365 for a create in 458515368. tpu-direct aimed at leaders that had already passed.
15. **`--also-send` double-sent every sell** and paid the second tip when `--sell-path` was missing.
16. **The tpu-direct keep_warm loop ran whenever the path was enabled**, even when it was not the fire path. It opened
    QUIC connections to upcoming leaders throughout every Helius run, against Agave's 8-new-connections/min/IP limit;
    the logs show its connect timeouts.
17. **Smaller items:**
    - The post-buy balance and token reads ran one after the other.
    - The land poll was fixed at 300 ms.
    - There was no per-path ack time and no constant-k route in the logs.
18. **Latency budget, all zero-cost measurements:**

    | step | time |
    |---|---|
    | Engine shred → send | < 1 ms (BUY-PREP 0.3–0.4 + SEND-PREP 0.1–0.2) |
    | fra-sender, warm | 0.5–0.8 ms |
    | Nozomi fra2, warm (h2) | 0.6 ms |
    | staked-rpc, warm (h2) | about 1 ms |
    | Cold TLS | 38–45 ms (the 2 s keep-alive keeps one connection warm) |
    | Helius global HTTPS (Cloudflare) | 14–17 ms |
    | Kaldera vs erpc | Kaldera 1.5 ms earlier |

    **The send code is not where races are lost.** About 100 positions after the create is roughly 30–50 ms of block
    time. That is the delay of shred → us → relay → leader, not internal cost.
19. **Our live landings** (`/root/det/measure_land.out`):

    | run | same slot as create | first behind bundle | median gap |
    |---|---|---|---|
    | Helius | 4/5 | 2 | +2.8% |
    | staked-rpc | 1/6 | 0 | +7.5% |
    | Helius + Nozomi | 4/14 | 1 | +0.1% |
    | Helius + latency fix | 3/6 | 3 | +0.0% |

    Same-slot positions ranged from 38 to 407 after the create.

## Fixes (lines in /root/sniper-det, final source)

Detection (AFTER and AFTER_FINAL):
- **`src/snipe.rs`**
  - Account lookup resolves loaded ALT addresses: `acct`/`key_at`, lines 102–112.
  - Effective dev read: `dev_buy_effective`, line 177, used at line 148. The old read is kept as `dev_buy_sized`
    (207) behind `--dev-sized-only`.
  - Quote mint: `create_quote_mint`, line 220.
  - CPI create detection: `detect_cpi_create`, line 234.
  - 3-byte flag form: line 342.
- **`src/feeds/grpc.rs`**: idle timeout, `idle_timeout()` line 439, applied at lines 469 and 501. Set with env
  `FEED_IDLE_MS`, default 15 s.
- **`src/bin/snipe_engine.rs`**
  - New `DetLog` (line 120): one `DETECT` line per create arrival per feed, `FEEDS` heartbeat every 60 s, and
    `FEEDSTATUS`.
  - New skips for non-SOL quotes and legacy creates (lines 1582, 1905). Flags restore the old behaviour:
    `--allow-nonsol-quote`, `--allow-legacy-create`.
  - `PAPER stats` lines: read failures and tracker wait.
  - Leader map covers the current and next epoch, and unknown leaders fail open: `leader_map` line 692, gate line 1915.

AFTER_FINAL only:
- **Router (CPI) creates are decoded and fired:**
  - `snipe::router_create`, line 259 (WSOL-quote check, holder/mayhem bytes);
  - `router_launch`, line 199;
  - `cand` at lines 1564 and 1889;
  - `--no-router` disables it.
- **Creator fee** is ignored on SOL curves (`detect_launch`).
- **PoH clock** follows the real slot length:
  - `feeds/entries.rs` `SLOT_US` (line 157) and `ms()` (line 163);
  - `feeds/shred.rs` line 335;
  - `set_slot_clock` from `getRecentPerformanceSamples` (line 678).
- **Path dump** uses one write per line (line 1683).
- **Send path** (all opt-in or diagnostic, so the default send behaviour is unchanged):
  - tpu SLOT follows the shred slot (1885);
  - also-send applies to buys only (`is_buy`, 799);
  - `--fallback-path <tipless>` re-sends a refused or 429 tx (53, 290, `send_and_poll`);
  - `SEND-ACK` line per path with ack ms, status and constant-k `x-ck-tx-route` (822; `send/mod.rs` 784);
  - `--land-poll-ms` (861);
  - post-buy reads run concurrently (2038);
  - `FIRE … rx_to_fire_us` and `SKIP-INFLIGHT` / `MAX-INFLIGHT` counters (1927, 1934).
- **Config** (`/root/det/probe_det.toml`): helius `max_per_sec = 1`, `queue_ms = 0` (refused locally instead of
  eating a 429); tpu-direct `enabled = false`.

Validated at zero cost:
- `simulateTransaction` of our v3 buy on two cap-family-only launches: err null, 72–77k CU.
- Router launches tracked in paper with the derived bonding curve: fill 1.000x, curve readable.
- `--unwrap` dry run with the new config: helius shows `max 1/s`, the fallback and also-send paths are set,
  keep-alive is 0.7 ms.

## Open risks

- **The fixed detection fires about 5.7× more** (≈500/h), and the extra launches are about breakeven at realistic
  entry. A live run with AFTER would multiply fees with no shown edge, so cap it with `--max-total-sol` or pair it with a
  selection gate. `--dev-sized-only` restores the old firing set while keeping the other fixes.
- **The router decode is reverse-engineered from one day** (75/75 checks). It is guarded by the discriminator, the args
  length and the WSOL quote. A pump router upgrade could change it; `--no-router` turns it off.
- **Quote detection relies on create_v2 account [16].** If pump adds accounts to SOL launches, they would be skipped:
  safe, but silent. Watch `verdict=skip_quote`.
- **The cap-dev read assumes the fresh 30 SOL / 1.073e15 curve.** All 4,019 SOL launches had it; depth 1/2 curves were
  all non-SOL.
- **Phantoms (failed creates) still fire.**
- **The Helius guard is per process.** Other processes on this IP share the 1 req/s keyless budget, so 429s are still
  possible until a key is used.
- **AFTER_FINAL had only short paper validation.** Its paper path differs from AFTER only by router fires, the PoH
  scaling and the dump fix.
- **The paper "his rule" and derisk exits are fixed rules, not fitted.** Realistic entry assumes a 1.03 slip behind
  the bundle (Helius).

## Recommended next live test (the owner decides; not run)

**Goal:** prove the send fixes (no 429, fallback, ack times, rx→fire) and measure Helius landing on the newly detected
launches by leader client. Fees are capped.

1. **Optional but best:** create a free Helius project key and add `HELIUS_API_KEY` to `.env`. Then set
   `url = "http://fra-sender.helius-rpc.com/fast?api-key=${HELIUS_API_KEY}"` and
   `no_tls_endpoint = "Helius regional Sender is HTTP-only (docs)"` in `probe_det.toml`. This raises the limit to
   50 req/s. The key travels in cleartext on that hop; the global HTTPS endpoint costs about 15 ms.
2. Run with no paper engines or builds on the box:

   ```
   cd /root/sniper-det && ./snipe_engine.AFTER_FINAL --snipe-once --concurrent --live --uri-blacklist \
     --spend-lamports 1000000 --fill-cap 2.5 --max-sol 0.0015 --max-total-sol 0.006 --max-loss-sol 0.07 \
     --max-inflight 4 --min-dev-buy 500000000 --max-dev-buy-sol 8 --minutes 30 \
     --cu-price-micro 100000000 --cu-limit 90000 --sell-cu-price-micro 1500000 \
     --send-path helius --sell-path staked-rpc --fallback-path staked-rpc --land-poll-ms 100 \
     --config /root/det/probe_det.toml --env-file /root/sniper/deploy/.env < /root/.nexus-v2-trading-wallet.pass
   ```

   - It makes 6 buys of 0.001 SOL, at about 0.0105 SOL each in priority fee and tip: **≈0.065 SOL total**. The
     wallet holds 0.111 SOL.
   - There is no `--close-leaders`, so every leader client is sampled.
3. **Measure:**
   - `/root/bsplit/measure_land.py <log>`: same-slot rate, position, outsiders ahead, gap vs the post-bundle price, by
     leader client.
   - From the log: `grep -c 429`, the `fallback` lines, the `SEND-ACK` ack_ms per path, `FIRE … rx_to_fire_us`,
     `MAX-INFLIGHT`.
   - **Pass criteria:** 0 refused buys, and same-slot at least 4/6.
   - An A/B with `--also-send nozomi` (Harmonic leaders) is the natural follow-up.
