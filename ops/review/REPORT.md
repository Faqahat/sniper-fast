# Independent review: final sniper engine before the live landing test (2026-10-19, 14:11–15:02 UTC)

Reviewed: binary /root/arbx-final/target/release/snipe_engine (md5 df3ca55b85d2…, unchanged), /root/lat/live_final.sh
(md5 c97136ea…, now --max-loss-sol 0.096), /root/lat/final_landing.toml.
I never passed --live, never ran live_final.sh, and sent no valid transaction.
Wallet FRZh63L6…: 0.310818539 SOL at 14:11 UTC and 0.310818539 SOL at 15:01 UTC.
Every script and output is in /root/review/. The patched review build lives in /root/review/arbx-rv and was never used live.

## Verdict: GO for the one landing test, with the conditions at the end

| # | Check | Result | Evidence (files in /root/review) |
|---|---|---|---|
| 1 | Filter correctness | PASS | 38 fire decisions over 3 runs; every one passes rule #2 on chain. 0 mismatches in 759 rejected launches. Paper and live-loop selections are identical. |
| 2 | No network round trip before the buy | PASS | bpftrace over 24 fires: 0 RPC or non-send writes on the buy thread, and no awaits on the path. |
| 3 | Speed | PASS | Decision → first send write (kernel): p50 ≈ 50 µs, p99/max 95 µs (n=24). |
| 4 | The buy tx | PASS | 69 real presigned buys decoded: all structural checks OK, 69/69 byte-identical to the full compile, 69/69 signatures valid with unique nonces. Simulation OK, including live rule-#2 mints. |
| 5 | The sell | PASS (findings 1–3) | Buy+sell+close simulates OK and closes the ATA. The sell is attempted only once. |
| 6 | Feeds | PASS | 5 of 5 feeds delivering, 0 errors/drops. DZ BGP up. Dedup holds. Reconnect seen working in a real outage. |
| 7 | Safety caps | PASS (finding 4, note A) | Engine stopped at exactly 10 fires. Caps are reserved before the send. No double-buy path. The kill-switch reads 0.096. |
| 8 | Keys and paths | PASS (LandX UDP unverifiable) | Our key vs a bogus key: each provider accepts ours and rejects only the junk. |
| 9 | Code review | PASS, no CRITICAL | 4 MEDIUM, 5 LOW (below). |
| 10 | Environment | PASS (notes) | Clock synced, core 1 free of NIC IRQs, 42 GB disk free, doublezerod active. |

## 1. Filter (rule #2 + base filter)
- Runs:
  - paper_rv1 (30 min --paper-trade, the live_final.sh filter flags verbatim, plus --race-track-rejects, which only logs);
  - rvd (junk-fanout, live flags verbatim: 10 fires, then "TOTAL spend cap reached");
  - rve (the same with --max-total-sol 0.04: 14 fires).
- Verifier: verify_rv.py, written new. The on-chain checks are:
  - host not a bot launchpad;
  - true dev 0.5–8 SOL (TradeEvent buys in the create tx);
  - CreateV2;
  - SOL quote (create account 16 is SOL/WSOL and there is no foreign quote-token balance);
  - glued bundle (the unbroken run of successful buys right after the create): at least 1 tx and 3–5 SOL by TradeEvent;
  - Lunar tip: the largest top-level System transfer to a non-signer goes to moon…. This is the prereg definition, see below. Transfers are parsed from System ixs, not balance deltas.
- Results:

| Run | Fires: pass on chain | Rejects checked | Mismatches | Output |
|---|---|---|---|---|
| paper_rv1 | 13/13 (E8G8… could not be fetched there; it passed in rvd) | 324 | 0 | verify_paper_rv1.txt |
| rvd | 10/10 | 196 | 0 | verify_dry_rvd.txt |
| rve | 14/14 | 239 | 0 | verify_dry_rve.txt |

  - The rejects include every race-gate reject (bundle and tip) and 40 base-filter rejects per run.
  - Engine bundle SOL equals chain TradeEvent SOL on every fire.
  - One boundary case, DZXis96tRf: chain bundle exactly 5.000 SOL, engine rejected it (LOW, rounding at the bound, fail-safe).
- The paper loop and the live loop (--snipe-once) picked exactly the same launches over their overlapping 18 minutes. The gate code is the same (snipe_engine.rs ~1817-1845 vs ~2160-2185).
- INFO (owner decision): the tip definition. The engine's --race-create-tip-prefix tests the LARGEST top-level System transfer to a non-signer, and only for static keys (snipe.rs:463-474).
  - This matches the labels behind PREREG_v2 #2 (/root/race/fwdrows.py:87, ctip_label from the engine's tip_to), so the rule as backtested is implemented correctly.
  - Under the literal reading "the create has a System transfer to a moon… account", 13 more launches in the 30-min paper run would qualify. The engine fired 14. Those 13 tip moon… 0.0025–0.003 SOL but pay a larger fee (0.02 SOL or more) to a lookup-table address (j7tracker/uxento tools).
  - The direction is fail-safe: it can only miss.

## 2. No network round trip before the buy
- Own bpftrace (rv.bt) on connect, write, writev, sendto, sendmsg, sendmmsg and pwrite64 of every thread, with an fd → peer map from ss every 0.5 s (net_rv.py, outputs bt_rv?.txt, ss_rv?.txt).
- Window: from the create's dequeue to the first send-path write.
  - Across 24 fires, the only writes on the buy thread are the zero-length prewarm sends (ret=0, nothing on the wire).
  - In 1 of 24 windows (rvd fire 57), a background tokio worker (tid 920968) wrote 251 B to the constant-k RPC socket 30 µs before our first write. This is the blockhash/slot poller running concurrently; the buy does not wait on it.
  - The first send write is always on the pinned event-loop thread, which is the main thread.
- Code: prepare (snipe_engine.rs:3162) uses in-memory caches only (BLOCKHASH_CACHE, the leader book, local ATA derivation, presign). fire (:3229) does synchronous non-blocking writes; the tonic Jito path is spawned. The busy-poll loop has no .await between dequeue and fire.

## 3. Speed (kernel timestamps, live flags, busy-poll, pinned to core 1)

| Measure | Value |
|---|---|
| Decision → first send write, rvd | p50 54 µs, max 95 µs |
| Decision → first send write, rve | p50 48 µs, max 81 µs |
| Engine's own trace, n=24 | p50 61 µs, p99 105 µs |
| Detect → first send write | p50 2.5–3.2 ms, p99 6.6–7.8 ms. This is waiting for the glued run to close, as designed. |

## 4. The buy tx
- arbx-rv = a copy of arbx-final plus a hook that, only in --junk-fanout, writes the real signed tx the engine discards to rawtx.jsonl. Run "dump": base filter, the live send/tip/CU flags, plus --fast-verify.
- 69 txs decoded (decode_sim.py), all OK:
  - one signature, payer FRZh;
  - CU price 30,000,000 µL; CU limit 90,000, plus 300 for each tip beyond 2, as coded;
  - ix order: tips, then CU limit and price, then idempotent ATA creates (base Token-2022, WSOL), then buy_exact_quote_in_v3 (disc e1f7501e…);
  - spend 1,000,000;
  - min_tokens_out = floor(1e6 / (2.5 × floor_px(dev))) exactly, on all 69;
  - tips match the route: jito 0.002, landx, helius, nozomi and astralane 0.001 each, one tip per family;
  - no lookup table; 895–1010 B.
- Byte and signature checks: --fast-verify found 69 identical to the full compile and 0 mismatched. sigcheck.py (RFC 8032, self-tested on chain txs) found 69/69 presigned signatures valid, with 69 distinct nonces R.
- Blockhash: age at the fire was 55–419 ms against a 200 ms getLatestBlockhash(confirmed) poll (bh.txt); the refresher runs every 300 ms.
- Tip accounts (tipcheck.py): the Jito list equals the block engine's live getTipAccounts. Every helius, nozomi, astralane and landx account we tip had 50 incoming txs in the last hour.
- simulateTransaction (signature zeroed, sigVerify false, replaceRecentBlockhash):
  - All 69 buys succeed (BuyExactQuoteInV3, TransferChecked, 71–81.5k CU), including the live rule-#2 mints 93B6bcTb, 88QzQFLy and 7rj5jzKM.
  - One expected failure: EhroDRjb returned IncorrectProgramId because its create tx itself failed on chain, so the mint does not exist.
  - The account list (17 accounts, including fee_config and buyback A7hAgCzF…) works with the current program.

## 5. The sell
- rv_sellsim (review build) builds the engine's own build_buy and sell_message_ixs(amount, 0, 90k, 1.5M µL, wrap=false) for live rule-#2 mints (5Fz6…, E8G8…, AHgD…). It simulates the buy alone to get the exact token amount, then buy+sell+close in one tx.
- Result: no error. SellV3 ≈ 44–56k CU, then CloseAccount succeeds, so the ATA is closed and its rent returned.
- Sell fee: 90k × 1.5M µL = 0.000135 SOL plus base fee, tipless, via staked-rpc only.
- Failure handling: there is no retry (finding 1). A position left unsold is recovered with --sell-held <mints> --live (snipe_engine.rs:988), which the owner runs.

## 6. Feeds
- FEEDS at the end of rvd: dz-leader 3.86M msgs, dz-retrans-eu 19.7M, kaldera 531k, turbo-kaldera 531k, erpc 113k; all rc=0, err=0, drops=0.
- First arrival (paper and rvd): dz-leader 666, dz-retrans-eu 577, kaldera 258, turbo-kaldera 235, erpc 23.
- doublezero status: BGP Session Up, fra-velia, edge-solana-shreds and retrans-eu subscribed.
- Dedup: in every log each mint has exactly one first=1 copy, and fires per mint are unique (10/10, 14/14, 69/69, 14/14).
- Reconnect: /root/race/paper_fresh.log shows kaldera refused for about 10 min (61 failures, backoff 1–10 s), then "delivering again", with the other feeds unaffected.

## 7. Safety caps (code: snipe_engine.rs:2053-2110, 2142-2143, 2216-2222)

| Cap | Where enforced | Behaviour |
|---|---|---|
| --max-total-sol 0.010 | Reserved with spent.fetch_add before the send, in a single-threaded loop | Stops at exactly 10 fires, landed or not. Seen: "TOTAL spend cap reached — no more fires" after 10 in rvd. |
| --max-inflight 2 | try_acquire_owned | A third launch is skipped while 2 are busy. |
| --minutes 90 | Top of the loop | Ends the run. |
| --max-loss-sol 0.096 | loss_cap = 96,000,000 lamports, getBalance polled every 8 s | Sets stop. The banner prints "loss kill-switch 0.096". |
| --max-sol 0.0015 | Spend only | Does not cover tips or fees (note A). |

- No double buy. Each mint fires once (cross-feed dedup, then one race decision, then preps.remove). All paths get one byte-identical payload, carrying every tip, under one signature. Land polling uses p.meta.sig/p.sig, which is the presigned signature actually written into the tx (round_trip_fast, :2370), so the presign concern does not apply.
- Note A, worst-case cost. The per-buy cap counts spend only.

| Item | SOL |
|---|---|
| Tips, up to 5 families when the create is in a leader's last slot (fd+jito) | 0.006 |
| Priority fee (30M µL × 90.9k CU) | 0.00273 |
| Sell | 0.00014 |
| Token loss, worst case | ≤ 0.001 |
| Total per landed buy | ≈ 0.0099 |

  - 10 buys ≈ 0.099 SOL worst case; typically 3–4 tips, ≈ 0.075.
  - A fill-cap revert costs ≈ 0.0027 SOL, because the tips revert.
  - The 0.096 kill-switch is therefore a backstop near the 10th buy. The wallet (0.31) covers the worst case.

## 8. Keys and paths (keys_rv.sh, ack.log)

| Path | Our key | Bogus key | Configured rate | Provider limit |
|---|---|---|---|---|
| jito-bundle (gRPC) | "invalid argument: Transaction had…" (got past auth, only the junk tx refused) | – | 2/s | owner's 2/s |
| nozomi fra2 | 200 "Malformed transaction string" | 401 | 5/s | 5/s per region |
| astralane fr | 400 "failed to parse binary transaction" | 401 | 5/s | free tier 5/s |
| helius fra-sender (keyless) | 500 parse error on junk (request accepted) | n/a | 1/s, refused locally ("over_rate") | 1/s per IP |
| staked-rpc | 200 deserialize error | 403 "Invalid API key" | none | – |
| LandX fra1 JSON-RPC | 200 "invalid wire transaction" | 401 | – | – |
| LandX fra1 /txb | 500 "ok" | 403 "api-key does not exist" | – | – |

- The /txb result differs from GAP NOTES §8.4: the new key now passes the binary endpoint too.
- LandX fra3 UDP cannot be verified at zero cost: UDP never answers. The key is 12 chars, which is the documented 12-byte prefix format, and the same key passes JSON-RPC and binary auth on fra1. If fra3 still drops it, only the landx copy is lost; jito-bundle and staked-rpc (plus helius on jito routes) still carry the buy. The landx tip is paid only if the tx lands by another path.
- Our send rate is at most 2 fires in flight and 10 in total. Two fires within 1 s make helius refuse the second locally, but that tx still pays the helius tip if it lands elsewhere (LOW).

## 9. Bugs and risks (none CRITICAL; none needs a fix before a 10-buy test)

| # | Severity | Finding | Suggested fix |
|---|---|---|---|
| 1 | MEDIUM | The sell is sent once. If it is not seen in 15 s, or lands with ok=false, the code only logs; the position stays (round_trip_tail, snipe_engine.rs:2416-2420). | Retry 2–3×: re-read the balance, resend; fall back to the ladder's flush logic (:2604). |
| 2 | MEDIUM | The land poll gives up after 15 s, and then no sell is attempted (:2382). A late landing (blockhash valid for about 30–60 s) leaves tokens held. | After the timeout, read the ATA; if the balance is above 0, sell. Or set --land-timeout-ms ≥ the blockhash lifetime. |
| 3 | MEDIUM | token_balance maps any RPC error to 0 (:1028-1031), and amount 0 aborts before the sell (:2399). | Retry the read about 3× at 100 ms; treat Err as unknown, not 0. |
| 4 | MEDIUM | Kill-switch baseline start_bal = native_balance().unwrap_or(0) (:2093): if that first read fails, the kill-switch can never trip. | Bail at start if it fails, and print the start balance. |
| 5 | LOW | Buy CU limit 90k vs 71–81.5k consumed (about 9% headroom on E8G8…). Running out fails the buy and costs about 0.0027 SOL. | 100–110k (+0.0003–0.0006 SOL per buy). |
| 6 | LOW | prepare takes BLOCKHASH_CACHE with no age check (:3164); sells check 20 s. If the refresher dies, buys go out dead. This costs nothing but uses up fires. | Skip or refetch if older than 20 s. |
| 7 | LOW | The end-of-run drain waits only 30 s (:2280); an in-flight sell can be cut off. | Wait up to land timeout × 2 + margin. |
| 8 | LOW | Fires on a create that then fails on chain (EhroDRjb…); the buy fails and pays fees. | Rare; accept. |
| 9 | LOW | A bundle of exactly 5.000 SOL is rejected (rounding at the bound). | Accept, or compare with a 1-lamport tolerance. |
| 10 | INFO | The RACE: banner (describe()) omits the bundle-SOL bounds, the tip prefix and glued. | Cosmetic. |
| 11 | INFO | The tip-prefix definition (see §1). | Owner decision. |

## 10. Environment
- Stop before live:
  - Re-run pgrep -af "snipe_engine|cargo|feed_race|bpftrace|python3|cont_fresh|paper_race|chain_loop|fp_loop".
  - At 15:01 UTC none of the READY.txt race processes were running. The /root/race fresh2 paper engine stopped at about 14:39 UTC with no summary line; I did not stop it. Something else stopped it, so the list in READY.txt is out of date.
  - The only other process found was a leftover "bash -c until [ -s /root/gap/race/ck3_rt.txt ] …" sleep loop (pid 756702). It is harmless, but can be killed.
  - None of my review processes remain.
  - Keep /usr/bin/doublezerod.
- Core 1: NIC IRQs are rx on CPU2 and tx on CPU3; core 1 has no NIC IRQs. With the race engine gone, core 1 is free.
- Clock: chrony, 43 µs from NTP.
- Disk: 42 GB free (87% used). /root/review holds 1.9 GB and can be deleted after the test.
- doublezerod: active, BGP up.

## Conditions for GO
1. Stop everything listed above (the leftover until loop) and confirm top is quiet.
2. Accept findings 1–3: a stranded position is worth about 0.001 SOL plus about 0.002 SOL ATA rent. Keep this ready, filling in mints from the log:
   snipe_engine --sell-held <mint,…> --live --send-path staked-rpc --sell-path staked-rpc --cu-limit 90000 --sell-cu-price-micro 1500000 --config /root/lat/final_landing.toml --env-file /root/arbx/deploy/.env < /root/.nexus-v2-trading-wallet.pass
3. The startup log does not print the start balance (it appears only in the final DONE line), so check right before the start that getBalance on rpc-frankfurt answers (finding 4). Also check that the banner reads "loss kill-switch 0.096 SOL".
4. Accept up to about 0.0099 SOL per landed buy (tips plus priority fee), so up to about 0.1 SOL for the 10 buys.
