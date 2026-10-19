# JITOLATE: why our live buys land late, and what it would take to be in the first ~25 txs (READ-ONLY, 2026-10-19)

This was read-only work. Nothing was sent, `--live` was never used, and keys and .env were not touched (tokens were loaded only with `set -a; . .env`).

Inputs:
- `/root/lat/live_land_final1.log`, `sends_final1.jsonl` and `trace_final1.jsonl`;
- the chain via constant-k (cached in `cache/`);
- bundles.jito.wtf (cached);
- ICMP pings to the leaders.

Scripts in this directory:

| script | what it does | output |
|---|---|---|
| `buys.py` | per-buy timeline | `buys.json`; `table.py` turns it into `table.md` |
| `wrapper.py` | finds who wrapped our tx in a 2-tx bundle | — |
| `winners.py` + `win_an.py` + `rtt_an.py` | who lands ≤25 txs after a create, how, and on which leader | `win_ours.jsonl`, `win_moon.jsonl` (150 Lunar launches, the 15:00–16:00 paper census), `r2.jsonl`, `win_moon.txt`, `win_r2.txt` (91 launches of the rule-#2 type: glued creator bundle 3–5 SOL) |
| `obs.py` | first outsider arrival in shreds (RACE obs lines) | — |
| `tx.py` | one-line summary of a transaction | — |

"d" means non-vote txs after the create, minus the creator's glued run. This is the same "pos" that `measure_land.py` reports.
"≈ms" means position in the block × 203.5 ms, assuming txs are spread evenly through the block (±10–20 ms).

## 0. The answer in five lines
1. **On our 10 launches, no outside buyer landed within 25 txs of the creator bundle.** The first outsider in slot S was at d ≥ 45, and on 5 of 10 launches no outsider landed in S at all. On the 3 buys we landed in S, we were the first outsider twice (pos 82, 127) and second once (pos 229).
2. **On rule-#2-type launches in general the ≤25 lane is rare and fast.** An outsider lands at d ≤ 25 on only 15 of 91 launches (16%). Those winners land **≈ 6–17 ms after the create** (p50 ≈ 12 ms). That is earlier than we can even send: we send ≈ 14–20 ms after the create (≈ 11–14 ms to see it, plus 0.6–7 ms to decide).
3. **We miss the first Jito/BAM auction after the create and land one ~50 ms tick later.** Jito auctions run on 50 ms ticks and BAM batches every ~50 ms (sources below). When the bundle path works, send → land is **25–39 ms**. Whenever that next tick falls after the slot ends, we land in **S+1**.
4. **Half of our fires could never make S from Frankfurt.** 5 of 10 had a create-slot leader 31–220 ms RTT away, and 2 more had the create in the last ~15% of the slot. The existing `--close-leaders` gate was off.
5. Our own paths are part of it:
   - our jito-bundle landed only 3/10;
   - the Jito BE rejected 2 as `would-fail` (simulation failed);
   - Helius Sender out-bids our own bundle with the same tx (it adds a 1,013,000-lamport tip tx);
   - on Harmonic leaders we never used Harmonic's own bundle endpoint;
   - LandX cannot be shown to have delivered anything.

## 1. Per-buy timeline (`table.md`; from `buys.json`)
Detection is the first feed. det→send is first DETECT t_rx to the first path write (sends_final1 `t_ns − ack_ms`). In this run decision → first write was 28–103 µs, so almost all of det→send is the race-gate wait for the creator bundle to close (`RACE decide at_ms` 0.3–5.7). The leader RTT is ICMP from this box. "Landed via" is the Jito-explorer bundle id compared with our FAST-ACK bundle id; a 2-tx bundle whose second tx is a Helius tip tx means Helius Sender.

| tag | mint | S leader (slot n/4), RTT | create pos / txs (≈ms into S) | first feed | det→send ms | JITO-RESULT | landed | land pos / txs (≈ms) | ≈send→land | landed via | outsiders ahead |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 6 | AAV6uk | JitoLabs (4/4), **220 ms** | 234/368 (≈129) | dz-leader | 2.94 | (none) | S+1 (BAM 86 ms) | 59/905 (≈13) | ≈70 | **Helius Sender** 2-tx bundle ce9fb42f (tip 3,013,000; tx 2 = 7tBdqzq tip 1,013,000) | 1 in S + 1 in S+1 |
| 7 | EcRjWg | HarmonicAgave (1/4), 1.3 ms | 168/359 (≈95) | dz-retrans-eu | 2.98 | (none) | S+1 | 42/548 (≈16) | ≈107 | non-bundle (nozomi or staked-rpc) | 0 |
| 16 | 5mWdoV | HarmonicFD (1/4), 0.5 ms | 403/575 (≈143) | dz-retrans-eu | 5.45 | (none) | **S** pos 127 | 530/575 (≈188) | ≈25 | **our jito-bundle** ab0c66e5 | 0 (first outsider) |
| 44 | uACGKi | AgaveBam (4/4), 31 ms | 59/339 (≈35) | turbo-kaldera | 3.22 | (none) | **S** pos 82 | 141/339 (≈85) | ≈32 | **Helius Sender** 2-tx bundle (tx 2 = BCoRyb1L tip 1,013,000) | 0 (first outsider) |
| 48 | Eu9TUX | AgaveBam (1/4), 31 ms | 370/428 (≈176) | turbo-kaldera | 4.03 | (none) | S+1 | 81/555 (≈30) | ≈39 | **our jito-bundle** 6bf4ad0a | 0 + 1 in S+1 |
| 50 | 8u1HMf | JitoLabs (2/4), 0.9 ms | 186/287 (≈132) | dz-retrans-eu | 0.64 | (none) | S+1 | 156/319 (≈100) | ≈156 | non-bundle (LandX / Helius TPU leg / staked-rpc) | 0 |
| 72 | 2qMpwg | AgaveBam (1/4), **149 ms** | 379/387 (≈199) | dz-leader | 3.67 | **would-fail** | S+1 | 249/340 (≈149) | ≈136 | non-bundle (LandX or staked-rpc) | 0 + 2 in S+1 |
| 109 | GMYnEW | AgaveBam (4/4), far (Alibaba 8.222.x, no ping) | 212/540 (≈80) | turbo-kaldera | 3.61 | accepted@S ×2, accepted@S+1 ×2 | S+1 (BAM **149 ms**) | 193/607 (≈65) | ≈171 | **our jito-bundle** 62e91678 | 0 |
| 110 | 93Wrkd | AgaveBam (2/4), **149 ms** | 309/458 (≈137) | dz-retrans-eu | 5.21 | **would-fail** | S+1 | 306/517 (≈120) | ≈167 | non-bundle (LandX or staked-rpc) | 1 in S + 3 in S+1 |
| 128 | 36MPaZ | HarmonicFD (1/4), 0.5 ms | 8/591 (≈3) | dz-retrans-eu | 7.23 | (none) | **S** pos 229 | 237/591 (≈82) | ≈58 | non-bundle (nozomi or staked-rpc) | 1 (AHwJSn, nozomi) |

Notes on the table:
- **Creates.** Every create was a Lunar (`moon…` tip) launch. On BAM and Jito-Solana leaders the create was inside a 4–5-tx Jito bundle (tip 0.0015–0.002 SOL). On Harmonic leaders it went via Nozomi with no Jito bundle.
- **How each buy landed.** By bundle: our jito-bundle 3/10, Helius's bundle 2/10. Not in a bundle: 5/10.
  - The bundle paths land 25–39 ms after the send when the next tick is still inside the leader's slot (tags 16, 44, 48).
  - The non-bundle paths took 58–167 ms.
- **Tip transfers.** Every landed tx paid every tip on its route, because the tips sit in the same tx. The tip transfers therefore cannot tell which path delivered it. Only bundle membership can (§5).

## 2. Root causes, ranked
**R1: The ≤25 lane is a ~6–17 ms reaction lane that our pipeline cannot reach. It is not a tip contest.** (Evidence: `win_r2.txt`, `win_moon.txt`)
- **How rare it is.** In 91 rule-#2-type launches only 15 (16%) had any outsider at d ≤ 25. By client: BAM 25%, Jito-Solana 11%, Harmonic 9%, FD 2/6. On our 10 launches it was 0/10.
- **How fast it is.** Those winners land ≈ 6–17 ms after the create: BAM p25/p50/p75 5.7/13.8/14.8, Jito-Solana 7.1/8.7/16.8, Harmonic 2.4–9.6, FD 14.5–23.4.
- **Our timing.**
  - Seeing the create takes ≈ 11–14 ms: the leader's broadcast hold of BAM 7.4 / Jito 11.2 / Harmonic 12.2 / FD 19.9 ms, plus transit (/root/gap/NOTES.md).
  - Deciding takes another 0.6–7 ms (det→send above).
  - So our earliest send is ≈ 14–20 ms after the create, which is already later than the winners' landing time.
- **What the winners are.** Most are local to the leader or bigger spenders:

| wallet | sender / route | tip or priority | buy size |
|---|---|---|---|
| dKMjeG | Helius tip | 0.2–0.3 SOL | 7.9 SOL |
| DAYAW4 | Jito 1-tx bundle | 0.25 SOL | — |
| 2EsRia | priority fee | 0.26 SOL | — |
| Guc4Ya | priority fee | 0.05 SOL | — |
| 2QH19v | Harmonic, priority only | 0.035–0.06 SOL | 7.9 SOL |
| CWiNFA (4×) | flashblock / stellium / nozomi | 0.003 tip + 37M µlamports/CU | — |
| a few cheap ones | — | ≤ 0.001 | — |

- **The fast lane also exists on far leaders.** It shows up on 20–43% of the launches whose leader is 40–220 ms from us (`rtt_an.py`). Those winners must therefore be near the leader; nobody in Frankfurt can react that fast to a Tokyo or NY create.
- **How fast the next outsider is.** From RACE obs over 371 paper rule-#2 launches (`obs.py`), the first outsider seen in shreds is p10 10 ms, p25 22 ms and **p50 51 ms** after the create. Our same-slot landings (≈ 45–80 ms) are at that median.

**R2: Miss the first tick and you wait a full ~50 ms tick. Late creates and far leaders turn that wait into S+1.**
- **Mechanics** (cited §3): Jito BE auctions run every 50 ms. BAM builds a batch every ~50 ms. The validator rejects batches for a past slot (`OutsideLeaderSlot`) and Jito-Solana BundleStage drops bundles once the leader window ends. A bundle sent ≈ 15–20 ms after the create lands ≈ 25–40 ms later (tags 16, 44, 48), that is ≈ 45–60 ms after the create, so the create must sit in roughly the first ~140 ms of a 200 ms slot.
- **Our 10 fires:**

| case | tags | count | result |
|---|---|---|---|
| far leader (31–220 ms RTT) | 6, 72, 109, 110 + 44, 48 | 6 | 1 in S (44) |
| create at ≈ 176–199 ms into the slot | 48, 72 | 2 | no chance, whatever the path |
| near leader with time left | 7, 50 | 2 | S+1 anyway (path problem, R3) |
| near leader, made S | 16, 128 | 2 | S |

**R3: Path problems on our side.**
- **(a) Jito BE `would-fail` on 2/10** (both BAM, tags 72 and 110). The BE's simulation of our buy failed, and that path was gone. The tx itself succeeded later through another path, so the buy was valid. The most likely cause is that the BE's simulation state did not yet include the create in the slot still being built. This is a hypothesis: the error detail is thrown away (see §5).
- **(b) We compete with ourselves.** Helius Sender forwards the same signed tx to Jito as a 2-tx bundle: ours plus its own tip tx (7tBdqzq or BCoRyb1L, 1,013,000 lamports; `wrapper.py`: every partner tx of those payers pays a Helius tip). Its bundle bids 3,013,000 against our 2,000,000, so where both reach the same auction, Helius's copy wins and ours fails (tags 6 and 44). That is harmless, but it hides which path is fast, and Helius is limited to 1 request/s.
- **(c) Harmonic leaders (≈27% of slots).**
  - Our route was jito-bundle + nozomi + staked-rpc.
  - Tag 7 (Frankfurt leader, ≈ 89 ms left in the slot) still went to S+1.
  - Tag 128 took ≈ 58 ms by a non-bundle path.
  - Harmonic's own bundle engine streams microbatches "the moment it arrives" and is free (§3). It was never tried.
- **(d) Jito-Solana leader in Frankfurt (tag 50, 0.9 ms away, ≈ 50 ms left).** Our bundle never landed and got no result. The tx landed 156 ms later by a non-bundle path. That fits a bundle that arrived after the last useful 50 ms tick, but this cannot be confirmed without the results.
- **(e) BAM tag 109.** The BE reported `accepted@S` twice (forwarded to the far leader Fc6NNdS2, last slot of its window) but the bundle landed in S+1 at ≈ 65 ms, under the next far leader. This is unexplained. The likely cause is the BE→far-BAM hop plus a batch cutoff.

**R4: The engine waits for the creator bundle (0.6–7.2 ms).**
- The rule-#2 gate needs the glued bundle's SOL, so it waits for the run to close (`--race-bundle-ms 3`; at_ms 0.3–5.7). That is 3–4 ms at the median, a real part of the ~5–10 ms we are behind.
- The rest of the engine is negligible: decision → first write 28–103 µs.
- The blockhash is not a factor. It is `confirmed` and ≤ 300 ms old, refreshed every 300 ms, valid ~60 s.
- Compute is not a factor either. The CU limit is 105,300 and 71,457 were used, so the tx is not oversized or slow to simulate. Priority is 30M µlamports × 105.3k = 0.00316 SOL.

## 3. Jito / BAM / Harmonic mechanics (docs and source, with citations)
**Jito BE on Jito-Solana leaders**
- "Parallel auctions are run at 50ms ticks … Jito submits the highest paying combination of bundles to the validator up to some CU limit" ([docs.jito.wtf/lowlatencytxnsend](https://docs.jito.wtf/lowlatencytxnsend/)).
- With sendBundle "only the Jito tip matters".
- BundleStage ([jito-solana core/src/bundle_stage.rs](https://github.com/jito-foundation/jito-solana/blob/master/core/src/bundle_stage.rs)) holds bundles before and during the leader window and drops them after it. `MAX_BUNDLE_RETRY_DURATION = 40ms`, `SLOT_BOUNDARY_CHECK_PERIOD = 10ms`, and "a bundle cannot cross slot boundaries". Execution inside the validator is FIFO; tip ranking happens in the BE auction.
- No published cutoff exists for the end of the slot. Same-slot landing for a mid-slot bundle follows from the mechanics but is not documented.
- So a bigger tip only wins **within the same 50 ms tick**, against bundles that touch the same state. It does not make the tick come sooner.

**BAM**
- "Every auction round (~50 ms), BAM assembles a batch". In phase 2, bundles and normal txs "compete on the same priority score" ([bam.dev maker-plugin/how-it-works](https://bam.dev/docs/bam/maker-plugin/how-it-works/)).
- The validator executes "in strict FIFO order" ([bam.dev/validators](https://bam.dev/validators/)). Batches for a past slot are rejected as `OutsideLeaderSlot` and pending batches are drained at the end of the slot ([bam_scheduler.rs](https://github.com/jito-foundation/jito-solana/blob/master/core/src/banking_stage/transaction_scheduler/bam_scheduler.rs)).
- BAM receives txs "via QUIC and Block Engine" ([bam.dev/overview](https://bam.dev/overview)), so searchers use the normal Jito BE sendBundle. TPU/RPC txs also go through the BAM batch, which is why our non-bundle txs on BAM took 136–167 ms.
- BAM advertises **preconfirmations with a p50 advantage of 5–10 ms over shred streams**. Their access terms are not verified.
- "Direct Bundle Ingest" (whitelisted, straight to BAM nodes) appears only in a news item that could not be loaded. Unverified.

**Harmonic** ([docs.harmonic.gg/searchers/harmonic-bundles](https://docs.harmonic.gg/searchers/harmonic-bundles), [streaming-mode](https://docs.harmonic.gg/concepts/streaming-mode))
- **Endpoints.** `https://fra.be.harmonic.gg` (also lon/ams/ewr/tyo/sgp/slc).
- **Protocols.** An authenticated gRPC `SearcherService.SendBundle` that is Jito-proto compatible (needs a whitelisted key). Also a **public, unauthenticated** gRPC `BundleService` and a public JSON-RPC `POST /api/v1/bundles` (`sendBundle`, base64 only), with lower, unpublished rate limits.
- **Cost.** "No protocol fees", and the "tips are simply priority fees", with no tip account. This explains the "no tip" fast lane on Harmonic.
- **Timing.** Microbatches "flow throughout the slot", forwarded "the moment it arrives". No auction interval is published.

**Jito sendTransaction**
- It forwards the tx to the validator. With `bundleOnly=true` it is sent as a 1-tx bundle with revert protection and returns `x-bundle-id`.
- The limit is 1 req/s per IP per region.
- It is the same 50 ms auction, so it is not faster than sendBundle. It would be one more copy of the same tx and gives no position gain.

**Status APIs**
- `getInflightBundleStatuses` has a 5-minute window, up to 5 ids, and reports Pending / Landed / Failed / Invalid.
- `getBundleStatuses` reports processed / confirmed / finalized and returns null if the bundle has not landed.
- The SubscribeBundleResults proto defines accepted, rejected (`simulation_failure`, `state_auction_bid_rejected`, …), processed, finalized and dropped. There is no evidence the BE still emits processed or finalized. We saw none, even for our 3 landed bundles.

**Explorer limits.** bundles.jito.wtf gives the landed slot, block index, tippers and landed tip, and a whole-second timestamp. It gives **no receive time**, so the receive → landed gap of other searchers' bundles cannot be measured from public data.

## 4. Alternatives: expected landing, with the evidence for each
| option | expected effect | evidence / caveat |
|---|---|---|
| **Fire only on near leaders** (`--close-leaders /root/arbx-final/close_leaders.txt`, already in the concurrent engine, 1,971 pubkeys, 10-16) | Turns ~5 of 10 S+1 losses into no-trades. Among near-leader fires, S rate ≈ 50% (2/4 here; earlier probe: in-time 84% near vs 62% far, per code comment) | Of our 10, the gate keeps 7, 16, 50, 128 (2 S, 2 S+1). About 30% of rule-#2 launches have a <5 ms leader (`win_r2.txt`), so fires drop ~3× |
| **Skip creates late in the slot** (create PoH > ~150 ms; DETECT already logs `poh_ms` from erpc) | Removes no-chance fires (48 at ≈176 ms, 72 at ≈199 ms) | Needs a small gate flag (not a send-path change). PoH maps to wall time within ±25 ms. A tighter 130 ms cut would also drop 6, 50 and 110 (all S+1) but **also tag 16 (≈143 ms, landed in S)**, so use ~150 ms with the near-leader gate |
| **Harmonic BE** `fra.be.harmonic.gg/api/v1/bundles` (public JSON-RPC, free; priority fee = tip) | Harmonic leaders: likely the best path there (streams immediately, no 50 ms tick). Expect S for near Harmonic leaders when ≥ ~40 ms are left; maybe ≤25 only if the create is seen quickly (Harmonic hold 12.2 ms) | Docs above; 4 of 5 Harmonic winners at d ≤ 25 are "no tip". **New send path: owner's OK needed** |
| Keep jito-bundle on BAM/Jito, **drop Helius from those routes** (or keep it knowing it wins the Jito auction with its own +0.001 tip) | Clean attribution. Helius as a second route into Jito is a bid +1M above ours, so keeping it is fine for landing but breaks measurement | Bundle ids ce9fb42f and the 44 bundle; `wrapper.py` |
| **Bigger Jito tip** (0.002 → 0.01) | No change in timing. Only wins inside a tick against same-state bundles; on our launches nobody was ahead of us in S | §1 "outsiders ahead" = 0 on 2 of 3 S landings; the ≤25 winners range from 1,000 lamports to 0.25 SOL |
| Jito sendTransaction (bundleOnly) as an extra copy | ≈ same as sendBundle (same auction) | 1 req/s/IP |
| Multiple bundles / duplicate submission (other BE regions) | Little gain for near leaders. For far leaders the physical round trip (≥ 2 × one-way) still loses S | — |
| **Direct TPU with stake** (constant-k staked-rpc; our tpu-direct) | On BAM, TPU txs wait for the BAM batch anyway. Our staked/non-bundle landings took 58–167 ms. tpu-direct stays broken (Agave: 8 connections/min/IP, 16 per staked peer, from `streamer/src/quic.rs`) | Not worth fixing for this goal |
| **BAM preconfirmations / plugin, or co-location near BAM nodes** | The only lever on the ~7–11 ms leader hold (preconf advertised 5–10 ms ahead of shreds). It is what the ≤25 lane looks like | Access terms unverified. Business/infra decision |
| Remove the race-gate wait (decide on bundle SOL as soon as ≥3 SOL is seen; treat the >5 SOL cap as a post-check) | −2 to −4 ms per fire | Changes the rule semantics slightly (owner's call) |

**Bottom line on ≤25 txs.** From Frankfurt shreds, with a 50 ms auction, the ≤25 lane (≈ 6–17 ms after the create) is out of reach on almost every launch. The best we can expect is to keep our earliest send close to that lane (cut ~3 ms of gating) and get lucky with the tick phase on near BAM/Jito leaders, plus Harmonic streaming. The realistic target for the next test is **"same slot S, first outsider"**. We already did that 2 of 3 times when we landed in S.

## 5. Bugs and checks on our side
1. **jito_result is (almost) always empty.**
   - `jito_results()` reads the in-memory verdicts once, right after `poll_land` returns (≈ 420 ms after the send), and never again.
   - The BE stream gave results for only 3 of 10 bundles: `accepted@S…` for 109, `would-fail` for 72 and 110. It gave nothing for 7 bundles, including the 3 that landed (16, 48, 109). `processed` was never seen.
   - snipe_engine builds everything with `arbx::rec::Rec::off()`, so the BUNDLES record (detail and error code of a `would-fail`) is never written. The JITO-RESULT line drops `detail`.
   - The bundle-id join itself is correct: FAST-ACK → `note_bundle` (snipe_engine.rs:3038) → `id_of_sig` (send/jito.rs:536).
   - **Fix (logging only):** print `o.detail` and the decoded `error_code` in JITO-RESULT. Re-read the verdicts at +2 s and +10 s. Poll `getInflightBundleStatuses` for the FAST-ACK ids at +2 s. Post-hoc, check bundles.jito.wtf `/bundles/transaction/<sig>` (as `buys.py` does).
2. **Does the bundle reach the right BE in time?**
   - Every bundle goes to `frankfurt.mainnet.block-engine.jito.wtf`. That is right for Frankfurt leaders (tags 16 and 48 landed 25–39 ms after the send).
   - For far leaders the region is irrelevant, because the shreds and the reply must cross the RTT anyway.
   - The 1 ms ack is the BE's receipt, not the auction. The auction phase (≤ 50 ms) is the big variable.
3. **Blockhash and compute:** fine (see R4). No sign of delayed or late simulation from our side. The `would-fail`s point to the BE's state lagging behind the fresh mint, not to our tx.
4. **LandX (fra3 UDP)** delivery could not be shown.
   - No landing can be attributed to it. All 3 non-bundle landings with LandX on the route (50, 72, 110) were slow (136–167 ms), which looks like the staked-rpc/TPU path.
   - LandX has never been tested alone live, and its UDP format (12-byte key prefix) was not confirmed in its docs (the region page lists only endpoints).
   - To attribute paths, a test needs a per-path variant tx: distinct signatures made mutually exclusive by a non-idempotent ATA create, so only the first one succeeds. Each losing variant costs only its base fee plus priority. The tip transfers revert in a failed tx. This changes the send path, so it needs the owner's OK.

## 6. Fix list for the next live test (exact flags and config; each send-path item needs the owner's explicit OK)
1. **Gate to near leaders.** Add `--close-leaders /root/arbx-final/close_leaders.txt` to `live_final.sh`. The gate already exists, so this is not a send-path change.
   - Before the run, refresh the file from current pings: keep leaders with RTT < 5 ms. 27 of 91 rule-#2 launches fall in that bucket.
   - Expected result: far-leader S+1 losses (6 of 10 here) become no-trades.
2. **Late-create gate** (small code change, gate only): add a new `--max-create-poh-ms 150` that skips a fire when the DETECT `poh_ms` (erpc PoH) is above 150. If PoH is unknown, use DZ/Kaldera slot timing. On this run, 150 skips 48 and 72 (both no-chance); 130 would also skip tag 16, which landed in S.
3. **Harmonic route (send-path change, owner's OK).**
   - Add a `[[send]] name="harmonic-be" kind="jito-bundle"`-style path pointing at `https://fra.be.harmonic.gg`. Use the public JSON-RPC `/api/v1/bundles` (base64), or gRPC `SendBundle` if they whitelist our auth pubkey.
   - The tip is the priority fee, so keep cu-price 30M or raise it.
   - Route: `harmonic=harmonic-be+jito-bundle+nozomi+staked-rpc`.
4. **Attribution and results (logging only).**
   - Print `detail` and the error code on JITO-RESULT, and re-read the verdicts at +2 s and +10 s.
   - Log `getInflightBundleStatuses` for each FAST-ACK id.
   - For attribution, run one test arm with Helius off the BAM/Jito routes: `bam=jito-bundle+landx-fra3+staked-rpc` (already) and `jito=jito-bundle+landx-fra3+staked-rpc` (drop helius). Then a bundle landing is unambiguous.
5. **Optional, the owner's call on rule semantics.** Shorten the race wait: `--race-bundle-ms 1.5` (now 3). Check on paper first that the rule-#2 decisions still match the chain; they matched 47/47 at 3 ms.
6. **Measure the next test against "S and first outsider"**, not d ≤ 25. Use `measure_land.py` plus `python3 /root/jitolate/buys.py` (change LOG/SENDS at the top) and `table.py`.

Not recommended for this goal:
- a bigger Jito tip (it does not move the tick);
- tpu-direct;
- Jito sendTransaction as an extra copy;
- more relays on BAM (non-bundle txs wait for the BAM batch: 136–167 ms here).
