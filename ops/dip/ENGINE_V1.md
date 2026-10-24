# Dip engine v1: build spec (2026-10-23 PKT; NOT built; owner's OK needed to build, shadow-run and go live)

Evidence: `ops/dip/PLAN.md`, sections from "KEY engine finding" on. Every number below is replay or real-data analysis, not live.

## What v1 trades
- **Trigger (revised 15:14 PKT):** a ≥1 SOL sell on a launch aged 1–120 s, from two paths:
  - direct pump.fun sells seen in shreds (fast);
  - routed sells seen as TradeEvents on the executed feed (~15 ms later).
  - In the CV, direct picks carried 74–86% of the profit, but in the first forward hours routed picks did better, so take both. All buys guarded.
- **Decision:** frozen GBDT (`src/dip.rs`, 35 features, parity 218/218 with Python; models `dip/frozen_dip2r_L*.json`) ≥ top-5% threshold, on triggers from both paths.
- **Buy:** 0.5 SOL, guarded: min tokens out = tokens at 1.02 × the post-dump price. If faster bots already lifted the price, it fails cheaply.
- **Sell:** all tokens, landing 2–4 slots after our buy's slot (the independent check found 2 vs 4 a tie; take-profit and holds of 8+ slots are worse).
- **Spacing:** the next trigger on the same launch is allowed 5 slots later.

## Data flow
1. **Shreds** (Kaldera / turbo-Kaldera / erpc, today's feeds) → `Arrival.tx`. A `DipWatch` sits beside `RaceWatch::observe` in `src/bin/snipe_engine.rs`.
   - Decode direct sells (validated on 800 real triggers, `ops/overnight/dipshadow/trig_decode.py`), all with 24-byte data: u64 @8 = tokens sold, u64 @16 = min SOL out.

     | Discriminator | Accounts | Mint | Seller |
     |---|---|---|---|
     | `33e685a4017f83ad` | 16 | 2 | 6 |
     | `1c92de7726c469d5` | 17 | 1 | 8 |
     | `5df6823ce7e940b2` | 26/27 | 1 | 13 |

   - Sum every direct sell on the mint in the tx: 14% of classic-sell triggers carry several wallets' sells.
   - **Parse v1 transactions too:** 12% of direct triggers (8% of direct picks) are v1 txs (independent check). `src/tx.rs` `parse_wire` already handles legacy, v0 and v1 (0x81, SIMD-0385); the dip decoder only needs to read `Tx` as the snipe path does.
   - Resolve lookup tables (`altc::fill`): the mint sits in an ALT in ~1/144 cases.
   - Take the seller from its account position, not from the signer (5/144 differ).
   - **A shred trigger can fail on chain:** 28.7% of direct sell txs fail, 72% of those with `3012` (the seller holds no token account). The replay never sees them.
     - Skip if the sell's min SOL out > ~1.1 × the expected SOL out on our curve. This catches 62% of the failed big sells.
     - Do NOT skip on the seller's holdings: 6.5% of real dumps come from sellers with no trade history, and those picks earn ~20% of the profit.
     - Always send the buy with the 2% guard, so a false trigger costs only a failed buy (~0.0002; about 0.002–0.003 SOL/h).
     - Measure the leftover rate in shadow mode.
2. **Trade history** (features) from an EXECUTED feed with logs (`yellowstone-tx`), decoding pump TradeEvents (`Program data:` = disc `bddb7fd34ee661ee` + mint, sol, tok, is_buy, user, …, virtual reserves), exactly like the collector.
   - 76% of pump trades are routed and invisible to shred decoding, so history must come from here.
   - **Lag tolerance (tested, direct-only six-block CV; independent check agrees):** history up to 100 ms late costs ~0 unguarded at "35–50 ms"; the guarded version loses 7% / 14% / 32% at 35 / 50 / 75 ms. At 400 ms (about one slot), "35–50 ms" stays at +20.7 / +13.6 unguarded, but the guard loses 1.5–3.5. At 1 s it fails. This test hides every trade in the lag window; live, direct trades from shreds fill part of it.
   - **Not configured today:** the snipe engine config has no executed feed.
   - **Probably no new provider needed:** Constant-K's Kaldera, which we already use for deshred (`kaldera-frankfurt.constant-k.com:8443`, `KALDERA_TOKEN`), is a full Yellowstone gRPC service with transaction streams, per the vendor page https://www.constant-k.com/yellowstone-grpc/ (vendor claim, not checked).
   - A `yellowstone-tx` feed on that endpoint (Subscribe, transactions filter on the pump program, processed commitment) should give the executed txs with logs.
   - Confirm our plan includes it, then measure its delay against the deshred feed with `ops/gap/feed_race.sh` (supports `yellowstone-tx`; zero cost; server run, owner's OK).
3. **Per-launch state** (launch ≤ 120 s old + margin): create slot, creator, glued bundle / insiders (as `rp.structure`: consecutive buys right after the create in its slot), latest curve (vsol, vtok), compact trade list (slot, idx, user, buy, sol, tok, vsol, vtok).
4. **Trigger time:** SOL out of the dump = constant product on the latest known curve with the dump's token amount, minus pump fees. Then the 35 features (`dip::features`, the replay's exact definitions), then `Gbdt::score`, then decide.
5. **Shadow mode:** log `DIP decide` with mint, trigger sig, slot/idx, score, threshold, pass, features, feed arrival time, decision time. No send.
   - Score offline afterwards against the collector's data (same events), to measure feature drift and the reaction-time distribution.

## Live mode (separate OK)
- One landing service per leader client, like HkQ7hMjy: Nozomi on BAM / Harmonic, Helius on Jito-client, Nozomi or plain priority fee on Firedancer. Tip ~0.001 SOL, priority ~0.00013 SOL (`ops/final2/SEND_DESIGN.md`).
- Target: land ≤ 45 ms after the dump (HkQ7hMjy median 39 ms, DYXDDrZC 43 ms).
- Caps: per-hour trade count, max open positions (1 per launch), daily loss stop.

## Expected (replay units = block-position latency, the same units as HkQ7hMjy's median 39 ms; ~33.5 h of data, direct-only, REAL follower limits)
| Replay entry | Unguarded | Guarded | Per day (unguarded) |
|---|---|---|---|
| "35 ms" | +20.1 (6/6 blocks) | +17.2 | ~14 SOL |
| "50 ms" | +11.1 (6/6) | +8.2 | ~8 SOL |
| "75 ms" | +3.5 (5/6) | +5.5 | ~2.5 SOL (guarded ~4) |

- **At our REAL latency** (sell executed → our buy executed): a real 35 ms ≈ +11…+17 per ~33.5 h (≈ 8–12 SOL/day), a real 50 ms ≈ +3…+12 (≈ 2–8.5).
  - The low end is the checker's strict model (fast bots skip once our buy moved the price); the high end is real limits + the measured timing errors (`dip/real_latency.py`).
- HkQ7hMjy's speed ≈ a real 30–35 ms.
- The shadow run must measure our real trigger→landing distribution before any forecast.

**Costs:** the replay charges 0.0008 SOL per tx, 0.0016 per round trip. HkQ7hMjy-style buys cost ~0.0011 (tip + priority); a sell needs no ms race, so ~0.0002 suffices. That is ~0.0013 per round trip, so the replay's cost is about right or slightly conservative. A guarded buy that fails costs the priority fee only (~0.00013; the replay uses 0.0002).

## Shadow-run acceptance (decide live vs stop after ~1 day of shadow on the server; no sends)
1. **Our real reaction:** median trigger shred arrival → decision ≤ 2 ms, and the expected landing (from the probe's route medians) ≤ 45 ms after the dump.
2. **Trigger quality:** ≥ 90% of shadow triggers match a real ≥1 SOL dump in the collector data (same mint and slot); the false-trigger rate is what the min-out check leaves.
3. **Feature drift:** live features vs the replay's features for the same dips (collector data): ≥ 95% of picks agree (score above / below threshold).
4. **Rate:** picks per hour within ±50% of the replay's for the same hours.
5. **Paper P&L:** the shadow picks priced by the replay at the measured latency (decoded follower limits) are positive over the day, and not driven by 3 or fewer launches.

## Built so far (host repo, not wired into the engine, not deployed)
- `src/dip.rs`:
  - `Gbdt` + `features` (parity 218/218 with Python);
  - **14:26 PKT:** `direct_sells(&Tx)` (3 sell layouts; seller and mint by account position, lookup addresses via `tx.loaded`), `sell_sol_out`, `trade_events(&logs)` and `trade_events_from_inner` (executed-feed TradeEvents).
- Tests: `cargo test --release --lib dip`, 2 passed.
  - 10 real trigger txs (legacy / v0 / v1, lookup tables, a 12-sell tx with truncated logs) in `testdata/dip_sells.json`: 21 direct sells and 15 TradeEvents all match. The dump's SOL from the pre-trade curve equals pump's own event SOL (±1 lamport).
- Fixtures were made by `ops/overnight/dipshadow/make_sell_fixtures.py` (read-only RPC).

## Size of the work
~500–800 lines of Rust:
- TradeEvent decoding on the gRPC feed (`src/feeds/grpc.rs` keeps the meta);
- `DipWatch` (state, trigger decode, features, score, log);
- sell timer;
- tests on recorded txs (the dipshadow samples have real tx JSON).
Then one shadow day on the server.

## v1.5: routed triggers from the executed feed. PROMOTED into v1 at 15:14 PKT
The forward test since 12:09 has direct picks flat (−0.09 on 51) while routed picks made +0.66 on 66. Build both trigger paths from the start; the executed feed is needed anyway.

### (as written 14:27 PKT)
- When the executed feed delivers a ≥1 SOL sell TradeEvent that was NOT a direct sell (a routed sell), treat it as a trigger, about 15 ms later than shreds. Same model; always use the 2% guard.
- Replay, guarded: "35 ms" +21.5 vs direct-only +17.2; "50 ms" +10.3 vs +8.2 (~25% more). Unguarded it does not pay at "50 ms".
- Cheap: the executed feed is already there for history, and `trade_events` decodes the sell.

## v1.1 (optional): the biggest router, FLASHX8D…, is decodable from shreds too (13:36 PKT)
- `FLASHX8DrLbgeR8FcfNV1F5krxYcYMUdBkrP1EPBtxB9` carries 2,851 of the routed triggers (1,058 sellers). Its common swap is tag `0x00`, 22-byte data, 29 accounts:
  - u64 @1 = amount in (tokens sold for a sell: 15/15 exact vs the TradeEvent; SOL in for a buy);
  - u64 @9 = min out;
  - byte 17 = direction (1 = sell, 0 = buy);
  - seller = account 1, mint = account 7.
- Longer variants (23–36 bytes, 41–59 accounts: multi-hop) are rarer. Leave them out.
- **Worth (14:11 PKT, real limits):** acting on direct + FLASHX8 triggers gives "35 ms" +21.2 (vs +20.1 direct-only), "50 ms" +10.3 (vs +11.1) and "75 ms" +0.3 (vs +3.5).
  - It helps only when very fast. Add it after v1, and only if the measured latency is ≤35 ms.
  - FLASHX8 carries 30% of all triggers; 97% of them use the 22-byte / 29-account layout.
