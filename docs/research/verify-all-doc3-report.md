# DOC3 (Nexus Arb v2) — final claim-by-claim verification report

Document checked: `scratchpad/docs/doc3-Nexus.md`. There are 243 claims (D3-001 to D3-243). Scratch work for this report is in `cherry/work/report-doc3/`.

## 1. Summary

### Counts by final verdict

| Claim type | Total | Verdicts |
|---|---|---|
| Factual (identity, number, behaviour, structure) | 177 | Confirmed 128 (72%) · Partly 35 (20%) · Wrong 14 (8%) · Unverifiable 0 |
| Interpretation or recommendation | 66 | Supported 38 · Partly supported 12 · Unsupported 16 |

| Section | Claims | Where the problems are |
|---|---|---|
| Header | 8 | 1 Partly (the source file name) |
| 1. Verdict | 18 | 1 Wrong (tip), 3 Partly, 1 Unsupported (wallet "bleed") |
| 2. Code + allowlist | 53 | 1 Wrong ("two upgradeable venues"), 5 Partly, 1 Unsupported; the rest Confirmed or Supported |
| 3. On-chain table | 25 | 1 Wrong (6036 = Whirlpool), 5 Partly (mostly the "land rate" label) |
| 4A. Losing the race | 16 | 5 Partly, 2 Unsupported, 2 Partly supported |
| 4B. Wins lose money | 25 | 3 Partly; the rest Confirmed or Supported |
| 5. Fixes | 25 | 3 Wrong, 8 Unsupported, 4 Partly supported, 2 Partly |
| 6. Head-to-head and takeaway | 64 | 8 Wrong, 11 Partly, 3 Unsupported, 3 Partly supported |
| 7. Bottom line | 9 | 1 Unsupported, 3 Partly supported |

### Overall trustworthiness

**High for describing the program and counting landed transactions. Low for the economics, the off-chain engine, the Program 1 comparison and the fixes.**

- **What is reliable.** Everything the doc says about the source and bytecode checks out against the deployed bytes:
  - The on-chain ELF is byte-identical to the build of the 812-line `arbed/program/nexus-arb-v2/src/lib.rs`, followed only by zero padding.
  - Correct: the 12-venue allowlist, balance-chaining, the NXV2LEG/NXV2OUT logs, the 0x4E58 error range, native legs, the optional guards, and the 1–8 leg limit.
  - The landed-transaction counts are exact: 953 / 23 / 19 / 5, the 5RS6vJ1h breakdown, and the success P&L (+0.011 SOL, all of it from one trade).
- **Where the errors are.** They cluster in four places:
  - **How money moves:** what turns wins into losses, and the wallet balance.
  - **Assumptions about our engine** that the author did not check: rent paid every trade, the wSOL account being closed, bundles not being used, the nonce causing delay.
  - **Metric labels:** "land rate", and landed tx/min read as the rate we fire at.
  - **Program 1 facts and lessons:** sizing, nonce use, legs, guards, native legs, median win.
- **The fixes section mostly fails.** Fix 2 is already how the engine works. Fix 3 needs a program upgrade and adds nothing over Fix 1. Most of Fix 4 is already done or contradicted by the data. Fix 5 would not cut costs with our fee setup. Fix 1 is feasible, but it only changes how rent is booked.

### Most consequential errors, with corrected facts

1. **The tip does not cause the losing wins** (D3-020, 143, 224; context in 011, 133).
   - On-chain `min_profit` is tip + 5,001 in all 22 bundle wins and tip + 1 in all 978 direct transactions.
   - For all 11 losing wins, wSOL gain minus tip minus fee is positive (+438 to +67,037).
   - The only uncovered cost was one-time ATA rent: 1,488,440 or 1,513,840 lamports each, 16,576,040 in total. Leave the rent out and 0 of 23 wins lose money.
2. **ATA rent is not paid every trade, and the wSOL account is not closed** (D3-150, 151, 149, 154, 204, 152).
   - Rent is paid once per new mint: 12 mints, 12 of 23 successes, and 0 of the 977 reverted transactions.
   - The engine keeps every ATA (the `held` set, `exec.rs:827`). There are 0 closeAccount instructions on chain and no close anywhere in `src`.
   - The wSOL account D3qtLfeA is reused in 1,000 of 1,000 transactions.
   - Rent is about 0.0015 SOL per account, not 0.002.
   - All 12 ATAs were still open with 0 tokens at 02:37Z, holding 18,089,880 lamports that closing them would recover. Fix 2 is already in place.
3. **The wallet is not "down to ~0.05 SOL"** (D3-025, 026, 092).
   - At 02:37Z: native 0.044 SOL, plus 4.232 SOL in the wSOL account D3qtLfeA, plus 0.018 SOL of rent in the ATAs, about 4.30 SOL in total. That is roughly flat since funding (4.349 SOL).
   - The window net is −0.013 SOL counting rent as spent, or +0.005 SOL leaving it out.
   - The native balance is low because fees, tips and rent are paid in SOL while gains stay in wSOL.
4. **"Land rate" and "~4 tx/min" are misread** (D3-083, 102, 193, 107, 109, 164, 236).
   - All 1,000 transactions landed. 2.3% is the success share among landed transactions.
   - Per attempt, 23 of 8,496 succeeded (0.27%).
   - We fired 35.3 attempts/min and 72.2 copies/min, not 4/min.
   - 88.6% of attempts were bundle-only. Failed bundles never appear on chain and cost nothing.
   - The landed failures are the direct copies: 964 direct plus 13 unmatched.
5. **Error 6036 is not Whirlpool slippage** (D3-098). All 19 came from Meteora DLMM, `BitmapExtensionAccountIsNotProvided`: the builder left out an account. Whirlpool was invoked in 0 of 1,000 transactions.
6. **All 12 allowlisted venues are upgradeable, not two** (D3-052, 053). Every one has a live upgrade authority, and each authority is a PDA.
   - The payer and token guards were never switched on: the trailer appears in 0 of 1,000 transactions.
   - The arb-lab builder cannot emit the trailer.
   - The hostile-venue test program is truncated at 1,414 bytes and no test uses it (D3-051, 061, 187).
7. **Program 1's "on-chain adaptive sizing" lesson is not supported** (D3-217, 219, 220, 233, 211, 241; capability-only in 200, 213, 214).
   - The sizing code is in the binary, but its gate flag (0x40) was set in 0 of 936 cached transactions.
   - The amount spent equals the off-chain `amount_in` in 290 of 291 measurable transactions, failures included. There are 0 sizing log lines.
   - Program 1 never "sizes down and lands". It reverts with Custom(3), which is 77.5% of its landed transactions.
8. **Other Program 1 facts are wrong:**
   - It uses durable nonces on about 88% of landed transactions (D3-228).
   - Routes of 2–4 hops were seen, and the program accepts 1–16, so Nexus supports fewer legs, not more (D3-180, 208).
   - It counts operator lamports in its profit check and has a token non-decrease check (Custom 8) (D3-186, 209).
   - It does run native-SOL pump.fun legs (D3-188).
   - Its median win is about +0.0011 to +0.0014 SOL, not +0.0004 (D3-196).
9. **The venue and quote-first claims are wrong** (D3-168, 167, 169, 115).
   - Our top venues are DLMM (~53% of landed legs), PumpSwap (~32%) and DAMM v2 (~15%). The engine has no CLMM support at all.
   - Priority fee equals CU limit × price in 978 of 978 priced transactions. So an in-program no-op would not cut fees, and bundle misses are already free.
   - Program 2's no-ops cost a median of about 47k–83k CU depending on the window, not ~40k.
10. **Fixes 1–2 would not stop the losses, and the nonce is not the delay** (D3-240, 148, 112, 160).
    - The recurring drain is 24,162,410 lamports of fees on 977 landed direct-copy failures, 55% of all SOL outflow.
    - Fix 1 only skips 11 wins that made +114,477 lamports leaving rent out. After Fix 1 the window is still about −23.6M lamports without the outlier trade.
    - The durable nonce adds no measured delay: landings are 0–2 slots after the decision. It stops the 16 multi-path copies from landing more than once.

### Claims that could not be fully checked, and why

- **Author's process:**
  - D3-003: where the name `nexus-program.rs` came from is unknown. The doc was pasted in from outside this machine.
  - D3-008: a full review cannot be observed directly. I judged it by how much of the file the doc's statements cover.
  - D3-043: the author decoding the logs personally cannot be observed. The logs themselves are present.
  - D3-007: the doc's fetch time is unknown. A ~243-minute window is reproducible from a fetch at 01:39–01:41Z.
- **Snapshots that were not saved:**
  - D3-084, 192: DOC2's "fresh 400-tx pull" (15.8%) was not saved. It can only be matched as a value seen in some 400-transaction windows.
  - D3-082, 108: a true time-average of Program 2's rate across 21:35–01:36 would need about 30–50 more signature pages from the shared public RPC. Not fetched.
- **Predictions and models:**
  - D3-240: "this week" is a prediction.
  - D3-219, 232, 241: whether trade sizing would rescue reverts was estimated with a crude size-response model. Pool state was not reconstructed.
- **Tests:** counted, not run (D3-059–064, 191). Builds were not allowed.
- **Rival samples:**
  - Program 1 and Program 2 figures come from the DOC1 and DOC2 evidence bases, partly non-uniform caches.
  - D3-188: 6 of 936 is a sample frequency.
  - D3-186: which accounts Program 1 snapshots in live transactions was not decoded. Custom(8) fired in 0 of 3,000 signatures.

## 2. Full claim table (document order)

Verdicts: **Confirmed / Partly / Wrong / Unverifiable** for facts; **Supported / Partly supported / Unsupported** for interpretations and recommendations. "—" means no correction needed.

| id | section | claim | final verdict | evidence (short) | corrected statement |
|---|---|---|---|---|---|
| D3-001 | Header | Doc dated 2026-10-04 | Confirmed | Header line 3; newest sampled tx 2026-10-04 01:36:15Z | — |
| D3-002 | Header | Wallet studied is 2g7rYv7y… | Confirmed | accountKeys[0] = 2g7rYv7y in 1,000/1,000 cached txs; all invoke 8K8uyQDt | — |
| D3-003 | Header | Source reviewed is `nexus-program.rs` | Partly | No such file on this machine. Content matches arbed `program/nexus-arb-v2/src/lib.rs` (812 lines, sha 5dbc404b), the deployed version. Doc was pasted in from elsewhere | Source is `program/nexus-arb-v2/src/lib.rs` (812-line deployed version); "nexus-program.rs" is only a label for a copy |
| D3-004 | Header | Native Rust on solana-program, not Anchor | Confirmed | Cargo.toml: solana-program 1.18 only; no anchor in lock; `entrypoint!`; 0 Anchor strings in ELF | — |
| D3-005 | Header (implicit) | Reviewed source = program the wallet invokes (8K8uyQDt) | Confirmed | On-chain ELF = arbed `target/deploy/nexus_arb_v2.so` (35,240 B) + zero padding; deploy slot 451798124 (09-30 00:07Z); 12/12 allowlist keys as immediates; 709-line arbed-live build does not match | — |
| D3-006 | Header / Scope | Covers the 1,000 most recent wallet txs | Confirmed | wallet-sigs.json: 1,000 unique landed sigs, 21:35:44–01:36:15Z, fetched 01:36:28Z; 167 more landed before the doc's mtime | The 1,000 most recent LANDED txs as of ~01:36Z; failed bundles are not included |
| D3-007 | Header / Scope | Window ~243 min | Confirmed | Our snapshot spans 240.52 min. A fetch at 01:39–01:41Z gives 242.7–243.3 min with identical outcome counts (953/23/19/5) and the same success set | — (our snapshot: 240.5 min) |
| D3-008 | Header / Scope | Full source review performed | Confirmed | Process not observable. The doc's source statements cover lines 3–802 of the 812-line lib.rs, including deep comments. Its errors are interpretation errors, judged separately | — |
| D3-009 | 1. Verdict | Program is well-built | Supported | Validation before any CPI, per-leg allowlist, token-owner checks, checked/i128 math, own error range, 20 host tests; behaved as designed in 1,000/1,000; own CU median 17,719 | Caveats: guards never enabled; any signer may call; process_instruction not unit-tested |
| D3-010 | 1. Verdict | Money is lost off-chain, not by the program | Supported | 953 ERR_PROFIT were real losers; 19 × 6036 = missing DLMM account; 5 out-of-CU = engine CU limit; 24,162,410 failed fees all on direct/unmatched copies | — |
| D3-011 | 1. Verdict | Also lost at edges the guard can't see (tip, rent, fee) | Supported | check_profit sees only the quote delta; 11/23 wins net negative, all from rent; failed fees 24.16M | Only ATA rent (and direct-copy priority fees) escaped; tip + base fee are inside bundle min_profit (tip + 5,001); rent is recoverable |
| D3-012 | 1. Verdict | Fire-&-Revert: runs legs, reverts on failed profit check | Confirmed | CPI loop, then check_profit → 0x4E580002; 953 ERR_PROFIT ran both legs; all 977 failures SOL Δ = −fee, quote Δ = 0 | — |
| D3-013 | 1. Verdict | Clean and careful | Supported | As D3-009; no failure traces to a program bug | Caveats: guards off; lib.rs:94 comment pairs 6036 with Whirlpool; no process_instruction unit tests |
| D3-014 | 1. Verdict | Same family as Program 1 | Supported | Babq: 81/81 cached Custom(3) ran ≥2 DEX CPIs then reverted; guard sits after the swaps | Differences: operator gate, dormant on-chain sizing code |
| D3-015 | 1. Verdict | Not in Program 2's family | Confirmed | Nexus 1,000/1,000 make venue CPIs; MEVi 998/1,000 Ok and 49/49 sampled with no CPI | — |
| D3-016 | 1. Verdict | Correctly reverts unprofitable trades | Confirmed | 953/953 ERR_PROFIT had a negative round trip (median −151.7 bps); all reverted to −fee | "Unprofitable" = below off-chain min_profit; rent-paying trades can still pass |
| D3-017 | 1. Verdict | ~95% of the time the opportunity is gone when we land | Confirmed | 953/1,000 landed = 95.3%. All 953 negative vs median expected +104.6 bps. In 44 of 50 checked blocks another tx hit our pools earlier in the block | Share of LANDED txs; per attempt 953/8,496 = 11.2%; a misquote is not ruled out per tx |
| D3-018 | 1. Verdict | Only ~2% of transactions land successfully | Confirmed | 23/1,000 err = null = 2.3% | Success share among landed (all 1,000 landed), not a land rate; per attempt 23/8,496 = 0.27% |
| D3-019 | 1. Verdict | About half of landed wins lose money | Confirmed | 11/23 (47.8%) net negative (−1,513,402 to −1,421,403), all ATA-rent payers; residual 0 | Only with rent counted as spent; leaving rent out, 0/23 lose; rent sits in 12 open, empty ATAs |
| D3-020 | 1. Verdict | Wins lose because the check ignores the Jito tip | Wrong | min_profit − tip = 5,001 in 22/22 bundle wins and 1 in 978/978 direct txs. For the 11 losers, gain − tip − fee = +438 to +67,037. Remove the tip and all 11 stay negative; remove the rent and all 11 turn positive | The tip is built into min_profit; the 11 losses come only from one-time ATA rent |
| D3-021 | 1. Verdict | Wins lose because the check ignores rent | Confirmed | All 11 created an ATA before nexus (1,513,840 ×8, 1,488,440 ×3); quote_before is read inside nexus; min_profit excludes rent | Rent is a refundable deposit (ATAs still open) |
| D3-022 | 1. Verdict | Window net roughly break-even | Partly | All 1,000: −13,116,830 with rent spent, +4,973,050 leaving rent out; doc's +0.011 SOL covers successes only and leaves out 24,162,410 of failed fees | Leaving rent out ≈ break-even (+0.005 SOL); counting rent as spent, −0.013 SOL (small loss, ~0.3% of capital) |
| D3-023 | 1. Verdict | Break-even only because of one lucky outlier | Partly | 4bkYuxT9 +27,459,627 = 249% of successes' net; without it −24.0M (rent left out) or −40.6M (rent spent); engine forecast 19,967,380, realized round trip 30,002,068 | The outlier carries the whole positive result. But counting rent as spent the window is −0.013 SOL even with it, and the trade was forecast and over-delivered, not pure luck |
| D3-024 | 1. Verdict | Without best trade, a steady bleed | Confirmed | −40,576,457 (rent spent) or −24,000,417 (rent left out); negative in all 9 30-min buckets | Bleed ≈0.04 SOL per 4 h |
| D3-025 | 1. Verdict | Wallet down to ~0.05 SOL | Partly | Native 43,973,370 at 02:37Z (52.3M at window end), but wSOL D3qtLfeA holds 4,232,243,448 and 12 ATAs hold 18,089,880 of rent: 4.296 SOL total | Native SOL ~0.044–0.05; total holdings ~4.30 SOL, roughly flat since funding (4.349 SOL) |
| D3-026 | 1. Verdict | The bleed explains the ~0.05 SOL wallet | Unsupported | Native fell 43,778,394 = fees 24,301,011 + tips 1,387,503 + rent 18,089,880, while all revenue (+30,661,564) stayed in wSOL; total value 4,299,101,012 → 4,285,984,182 | Low native SOL comes from paying costs in SOL while gains stay in wSOL; it is a fee-SOL operational risk, not the result of a bleed |
| D3-027 | 2. Code | Atomic multi-leg executor | Confirmed | 1..8 legs, CPI loop, any Err reverts the tx; deployed = 812-line lib.rs | — |
| D3-028 | 2. Code | amount_in supplied off-chain | Confirmed | parse bytes 2..10; build.rs route_ix writes it; leg-0 CPI amount = amount_in in 1,000/1,000 | — |
| D3-029 | 2. Code | min_profit supplied off-chain | Confirmed | Bytes 10..18; exec.rs:518-520; tip + 5,001 (22/22 bundles), tip + 1 (978/978 direct) | — |
| D3-030 | 2. Code | Whole route supplied off-chain | Confirmed | Legs, venue data and accounts come from ix data and the account list; the program only checks the allowlist and patches amounts | — |
| D3-031 | 2. Code | Program only executes and guards | Confirmed | No pool/price math; reads only token amounts and lamports; syscalls are only log, log_data, invoke_signed_rust, abort, memcmp, memcpy | — |
| D3-032 | 2. Code | Not a beginner's program | Supported | Private error range with collision test, per-leg logs, raw-byte allowlist, bounds-checked patching, optional guards, 20 tests | — |
| D3-033 | 2. Code | Exact balance-chaining | Confirmed | input = got (l.796), patched into the next leg (l.769); leg-1 CPI amount = NXV2OUT leg 0 in 988/988; transfers equal in 976/976 | — |
| D3-034 | 2. Code | Delivered measured from output account balance | Confirmed | token_amount before/after invoke (l.765/781); actual inflow = logged amount in 989/989 | — |
| D3-035 | 2. Code | Function is named `delivered()` | Confirmed | lib.rs:216 | — |
| D3-036 | 2. Code | Chained amount is a measurement | Confirmed | checked_sub on real balances; NXV2OUT = actual inflow 989/989 | — |
| D3-037 | 2. Code | Chaining correct and robust | Supported | Chain data consistent (1,000/1,000, 988/988, 23/23); pre-existing balance handled (test l.421) | Caveats: binds the amount, not the account; NATIVE_OUT counts any lamport change inside the CPI; patch/invoke loop has no unit test |
| D3-038 | 2. Code | Per-leg error attribution | Confirmed | LEG_ERR_BASE + i, NXV2LEG before each CPI, NXV2OUT after; last NXV2LEG names the failing leg in all 24 non-ERR_PROFIT failures | ERR_PROFIT itself is route-level |
| D3-039 | 2. Code | Logs NXV2LEG | Confirmed | lib.rs:97/767; lddw "NXV2LEG\0" at .text 0x26b8; present in 1,000/1,000 txs (Program data:) | — |
| D3-040 | 2. Code | Logs NXV2OUT | Confirmed | lib.rs:102/784; built by two stw immediates; present in 989/1,000 (11 failed before delivering) | — |
| D3-041 | 2. Code | Logs name which leg under-delivered | Partly | NXV2OUT carries the leg index and raw amount, no expectation; the engine compares it with its prediction (exec.rs:796-804); in 950 of 1,178 landed ERR_PROFIT rows both legs were short | Logs record each leg's delivered amount. Naming the short leg needs the off-chain prediction, and usually both legs are short |
| D3-042 | 2. Code | Attribution is "genuinely smart" | Supported | Solves a real attribution problem cheaply (8 + 16 B per leg); the engine consumes it | Somewhat generous: runtime invoke/failed lines gave the same leg in 23 of 24 failures |
| D3-043 | 2. Code | Logs visible on-chain in our txs | Confirmed | NXV2LEG 1,000/1,000 and NXV2OUT 989/1,000, surviving reverts | The author's own decoding cannot be observed |
| D3-044 | 2. Code | Error codes live in 0x4E58_xxxx | Confirmed | ERR_BASE 0x4E580000, codes 1–7 and 0x100 + leg; immediates in ELF; 953 × 0x4E580002 on chain | Some failures use builtin ProgramErrors |
| D3-045 | 2. Code | Token error codes are < 32 | Partly | SPL Token 0–19, but Token-2022 is 0–68 (32 = FeeMismatch); Nexus accepts Token-2022 and the wallet created 9 Token-2022 ATAs | SPL Token 0–19, Token-2022 0–68; all far below 0x4E58xxxx |
| D3-046 | 2. Code | Anchor venue errors are 6000+ | Partly | ERROR_CODE_OFFSET 6000 applies to program-defined errors; framework errors are 100–5999; 0xbbd (3005) seen in 5 of our bundle simulations | Program-defined Anchor errors are 6000+; framework errors 100–5999 also occur |
| D3-047 | 2. Code | Nexus codes can't be confused with token/Anchor errors | Supported | Smallest Nexus code 1,314,390,017; no overlap seen in landed txs or bundle simulations; collision test l.623 | Holds for honest venues; the justifying ranges are slightly off |
| D3-048 | 2. Code | Error-range design is thoughtful | Supported | Documented motive (v1's Custom(1) ambiguity), stable codes, mnemonic base, test | — |
| D3-049 | 2. Code | Optional payer guard exists | Confirmed | lib.rs:25-40, 199-206, 260, 801; 0x4E580005 ×2 in ELF | Never enabled: trailer in 0/1,000; builder cannot emit it |
| D3-050 | 2. Code | Optional token guard exists | Confirmed | lib.rs:285-305, 752-793; 0x4E580006 ×2 in ELF | Never enabled (0/1,000) |
| D3-051 | 2. Code | Guards defend against an allowlisted venue draining the wallet in a leg | Confirmed | Code covers payer lamports/owner/data_len, every writable authority-owned token account and foreign signers; present in deployed bytes | As designed only: 0/1,000 txs carried the trailer, arb-lab cannot emit it, and the evil-venue end-to-end test is truncated and unused |
| D3-052 | 2. Code | Exactly two allowlisted venues are upgradeable | Wrong | 12/12 owned by BPFLoaderUpgradeable with an upgrade authority set; all 6 teams' authorities are PDAs (allowlist-upgradeability.json) | All 12 are upgradeable; the forks are only the two the source comment trusts less |
| D3-053 | 2. Code | The two upgradeable venues targeted are the PancakeSwap and Byreal forks | Partly | On-chain security.txt reads pancake-clmm and byreal-clmm, with the Raydium CLMM source tree; the source names them as motivation | Identity right; but all 12 are upgradeable, and the guard applies to every leg |
| D3-054 | 2. Code | Most people never think of this guard | Unsupported | No evidence on how common such guards are; neither rival has a comparable guard; our own stack never enables it | Unusual compared with the two rivals; nothing supports "most people" |
| D3-055 | 2. Code | Native-SOL legs supported | Confirmed | NATIVE_IN 0x80 / NATIVE_OUT 0x40, check_profit_native | Unused (0/1,000) |
| D3-056 | 2. Code | Native legs exist for pump.fun's curve | Confirmed | lib.rs:52, 683; pubkey present in ELF; TS builder sets the flags only for PumpCurve | — |
| D3-057 | 2. Code | Lamports chain only into lamports | Confirmed | parse 194-198 BadNativeChain; test l.375 | — |
| D3-058 | 2. Code | That rule is correct | Supported | No mis-chained route passes on review | Test comment l.380 misleading; no test that NATIVE_OUT→NATIVE_IN is accepted; host tests only |
| D3-059 | 2. Code | There is a host-side test suite | Confirmed | 20 `#[test]` in lib.rs (counted, not run) | tests/ holds only a truncated evil-venue program |
| D3-060 | 2. Code | Tests pin parsing | Confirmed | 6 tests assert exact parse output | — |
| D3-061 | 2. Code | Tests pin the guards | Partly | Profit/payer/token decision functions pinned with boundary values. Foreign-signer, signer and process_instruction wiring untested; no test makes a guard fire on chain | Host tests pin the guards' decision functions only |
| D3-062 | 2. Code | Tests pin encoding | Confirmed | FIXTURE_HEX, GUARDED_FIXTURE_HEX, log byte layouts | encode() is test-only |
| D3-063 | 2. Code | Tests pin the cross-language fixture | Confirmed | lib.rs and arbed nexus-v2.test.ts assert the same hex | The live arb-lab Rust builder, which built all 1,000 txs, is not tested against it |
| D3-064 | 2. Code | Test suite is thorough | Supported | Thorough for the pure-logic layer | Thin on-chain integration: 6 LiteSVM cases, none covering success, ERR_PROFIT, guards or native legs |
| D3-065 | 2. Code / Allowlist | Allowlist has 12 venues | Confirmed | `ALLOWLIST: [Pubkey; 12]` l.670; unrolled 144-slot compare block with 12 × 8/8 key words; negative controls 0/8 | — |
| D3-066 | 2. Code / Allowlist | Meteora DLMM allowlisted | Confirmed | LBUZKhRx… l.671; 8/8 words; Meteora SDK | — |
| D3-067 | 2. Code / Allowlist | Orca Whirlpool allowlisted | Confirmed | whirLb… l.672; 8/8; Orca declare_id | — |
| D3-068 | 2. Code / Allowlist | Raydium CLMM allowlisted | Confirmed | CAMMCzo5… l.673; 8/8 | — |
| D3-069 | 2. Code / Allowlist | Raydium CPMM allowlisted | Confirmed | CPMMoo8L… l.677; 8/8 | — |
| D3-070 | 2. Code / Allowlist | Raydium AMMv4 allowlisted | Confirmed | 675kPX9M… l.680; 8/8 | — |
| D3-071 | 2. Code / Allowlist | PumpSwap allowlisted | Confirmed | pAMMBay6… l.674; 8/8; pump docs | — |
| D3-072 | 2. Code / Allowlist | PancakeSwap CLMM allowlisted | Confirmed | HpNfyc2S… l.675; 8/8; security.txt pancake-clmm; Jupiter label PancakeSwap | — |
| D3-073 | 2. Code / Allowlist | PancakeSwap's CLMM is a Raydium-CLMM fork | Confirmed | Same discriminators, Raydium source paths and error numbers (including the typo) as Raydium commit eb7c392be9 | Source not public; OtterSec unverified |
| D3-074 | 2. Code / Allowlist | Byreal allowlisted | Confirmed | REALQqNE… l.676; 8/8 | — |
| D3-075 | 2. Code / Allowlist | Byreal is a Raydium-CLMM fork | Confirmed | Public repo byreal-clmm: Raydium tree, raydium-amm-v3 registry, identical error numbering; adds SwapV3Dyn | A modified fork |
| D3-076 | 2. Code / Allowlist | Meteora DAMM v2 allowlisted | Confirmed | cpamdp… l.681; 8/8 | — |
| D3-077 | 2. Code / Allowlist | pump.fun curve allowlisted | Confirmed | 6EF8… l.683; 8/8; added in the 09-30 upgrade | Unused in window |
| D3-078 | 2. Code / Allowlist | Meteora DBC allowlisted | Confirmed | dbcij3… l.684; 8/8 | — |
| D3-079 | 2. Code / Allowlist | Raydium LaunchLab allowlisted | Confirmed | LanMV9… l.685; 8/8 | — |
| D3-080 | 3. Table / Throughput | Nexus ~4 tx/min | Confirmed | 1,000 landed / 240.52 min = 4.16/min, the same landed convention as the rival columns | Landed rate; we sent 35.3 attempts/min (72.2 copies/min) |
| D3-081 | 3. Table / Throughput | Program 1 ~10–17 tx/min | Confirmed | Landed 15.35/min (3,000 sigs); 16.70/min in our window (3,328 sigs / 199 min); pages 14.7–20.8; hourly 14.3–19.7 | Average ~15–17 landed/min, with bursts above 17 |
| D3-082 | 3. Table / Throughput | Program 2 ~118 tx/min | Confirmed | 3,000 sigs 02:10:53–02:36:14Z = 118.3/min exactly; pages inside our window run 58–345/min | A snapshot of a very bursty landed rate |
| D3-083 | 3. Table / Land rate | Nexus land rate 2.3% | Partly | 23/1,000 is the success share; all 1,000 landed | Success share among landed 2.3%; per attempt ~11.8% landed anything and 0.27% succeeded |
| D3-084 | 3. Table / Land rate | Program 1 land rate 15.8% | Partly | Success share 14.36% in our window (478/3,328), 13.6–15.9% per page; 15.8% is DOC2's unsaved 400-tx pull (seen in 187 of 2,601 400-tx windows) | ~14–16% success share among landed (14.4% in our window); not a land rate |
| D3-085 | 3. Table / Land rate | Program 2 land rate 99.8% | Partly | 1,992/2,000 = 99.6% at 02:20–02:36Z (pages 99.4 and 99.8%); a 22:08–22:11 page is only 51.1%; mostly no-op exits | 99.4–99.8% of landed txs end Ok at 02:20–02:36 (51% in one earlier page); a success share, not a land rate |
| D3-086 | 3. Table / Outcome | Nexus 95.3% ERR_PROFIT reverts | Confirmed | 953/1,000 Custom 1314390018; all reverted | Landed only; all are direct or unmatched copies |
| D3-087 | 3. Table / Outcome | Program 1 83% reverts | Confirmed | Custom(3) + Custom(14), both post-swap profit guards: 83.3% of 4,000 sigs, 83.3% in our window, 83.2% in DOC2's window | Custom(3) alone ~78%; all failures together ~85% |
| D3-088 | 3. Table / Outcome | Program 2 98.5% clean no-ops | Confirmed | 1,971/2,000 = 98.55% no-ops (assuming the unsampled 4vAqkstz txs don't trade); 206/206 sampled 4vAqkstz txs are no-ops | Each still burns ~80k CU |
| D3-089 | 3. Table / Swaps | Nexus runs swaps on 100% | Confirmed | 1,000/1,000 have a depth-2 venue CPI; 976 completed both legs | — |
| D3-090 | 3. Table / Swaps | Program 1 runs swaps on 100% | Confirmed | 214/214 cached and 80/80 random-sample txs make DEX CPIs | Rare outcome classes not uniformly sampled |
| D3-091 | 3. Table / Swaps | Program 2 runs swaps on 1.2% | Confirmed | 21/2,000 = 1.05% (02:20–02:36Z); 1.2% in DOC1's 400-tx window | ~1% |
| D3-092 | 3. Table / Balance | Wallet balance now ~0.05 SOL | Partly | Native 0.044 SOL (02:37Z), 0.029 SOL (04:49Z); plus wSOL 4.232 and rent 0.018 | Native ~0.03–0.05 SOL; total ~4.30 SOL |
| D3-093 | 3. Failure breakdown | Breakdown is over 1,000 txs | Confirmed | 953 + 23 + 19 + 5 = 1,000 | Landed only |
| D3-094 | 3. Failure breakdown | 95.3% ERR_PROFIT | Confirmed | ix3 654, ix4 298, ix5 1 | — |
| D3-095 | 3. Failure breakdown | ERR_PROFIT = legs ran, missed min_profit, reverted | Confirmed | Raised only by check_profit(_native) after the leg loop; 953 ran both legs and reverted; round trip negative in 953/953 (median −20.5M) | Not near-misses: none fell in the (0, min_profit) band |
| D3-096 | 3. Failure breakdown | 2.3% landed successfully | Confirmed | 23/1,000 | Label should be "succeeded": all 1,000 landed |
| D3-097 | 3. Failure breakdown | 1.9% venue error 6036 | Confirmed | 13 at ix4 + 6 at ix3 = 19 | — |
| D3-098 | 3. Failure breakdown | 6036 is Whirlpool slippage | Wrong | 19/19 logs: LBUZKhRx (Meteora DLMM) `BitmapExtensionAccountIsNotProvided`, 6036; Whirlpool invoked in 0/1,000 | Meteora DLMM, missing bitmap-extension account: an off-chain builder defect |
| D3-099 | 3. Failure breakdown | ~0.5% out of compute | Confirmed | 5 ProgramFailedToComplete; CU used = CU limit in all 5; "exceeded CUs meter" | — |
| D3-100 | 3. Failure breakdown | The four categories cover all 1,000 | Confirmed | No other error codes | The 2.3% are successes; all 1,000 landed |
| D3-101 | 3. Interpretation | Working exactly as designed, safely reverting | Supported | ERR_PROFIT comes only from the profit check; every revert avoided a real loss; each failure cost exactly its fee | "As designed" includes a guard that ignores rent; optional guards off |
| D3-102 | 3. Interpretation | 2.3% is ~7× worse than Program 1 | Partly | 15.8 / 2.3 = 6.9; same period: 14.36 / 2.86 = 5.0×; full window: 14.36 / 2.3 = 6.2× | Success share among landed is ~5–6× lower over the same period; neither is a land rate, and ours mostly reflects direct copies |
| D3-103 | 3. Interpretation | Program 1 runs the same philosophy | Supported | Both execute, then revert | P1 also has an operator gate, a fee- and lamport-aware guard, and dormant sizing code |
| D3-104 | 3. Interpretation | Gap = off-chain pipeline losing the race, not the program | Supported | Program correct; landed failures all direct; lag 0–1 slots; 4,901/6,616 bundle simulations rejected with ERR_PROFIT within ~27 ms | Also caused by the direct-copy send policy and stale or phantom quotes, not only race speed |
| D3-105 | 4A | Losing the race = ~95% of spend | Partly | ERR_PROFIT fees 23,406,395 = 96.3% of fees, 91.1% of fees + tips, 53.5% of all 43,778,394 SOL out including rent | 95% is the count share; ~53% of SOL outflow counting rent (the doc's own Problem B convention), ~91% without rent |
| D3-106 | 4A | Spread gone at landing, guard correctly reverts | Supported | 940/940 matched reverts had a negative round trip (median −152 bps); 382/964 landed in the trigger slot itself | Spread usually gone, or never real, when sent; slow landing is not the main cause |
| D3-107 | 4A | ~4 tx/min is slow for latency arb | Unsupported | 4.16/min is landed; we fired 35.3 attempts/min and 72.2 copies/min; failed bundles never appear; fire rate is not a latency measure (rx→signed median 0.196 ms) | We land fewer txs and wins than rivals (0.096 vs P1's 2.26 wins/min) but do not send slowly |
| D3-108 | 4A | Program 2 fires ~118 tx/min | Confirmed | 118.3/min landed over 3,000 sigs (02:10–02:36Z), 99.67% Ok | Landed rate (a lower bound on firing); bursty (60–256/min in other probes); mostly no-ops |
| D3-109 | 4A | Not firing on enough opportunities, or not fast enough | Partly supported | Fired 66% of 12,811 detected opportunities (35.3/min); rivals took 79.6% of contested spreads in the trigger slot; 39.7% of rivals seen before our first copy left | "Not fast enough" (at the landing stage) holds; "not firing enough" does not |
| D3-110 | 4A | Txs are built with a durable nonce | Confirmed | advanceNonce at ix0 in 1,000/1,000; recentBlockhash = leased nonce value in 987/987 | — |
| D3-111 | 4A | advanceNonce is instruction 0 | Confirmed | 1,000/1,000 | — |
| D3-112 | 4A | Durable nonce is a latency smell (late landing) | Unsupported | Landed − decision slot is 0–2 for 931/964 direct failures (max 15) and 0–1 for bundles; nonce cached off the hot path; dedups multi-path copies; P1 uses nonces too | The nonce adds no measured delay and prevents duplicate landings |
| D3-113 | 4A | Nexus does no on-chain quoting | Confirmed | No pool parsing or price math; only 6 syscalls | — |
| D3-114 | 4A | Program 2 re-checks the opportunity in-program | Confirmed | MEVi ELF has optimal_input, search and quote modules and "No profitable arbitrage opportunity found"; 166/172 sampled txs succeed with 0 CPIs | Inferred from code plus behaviour |
| D3-115 | 4A | Program 2 no-ops for ~40k CU | Partly | No-op CU medians: 46,856 (10,827 exec rows, Oct 3 20:28–21:36Z; recomputed by me), 61,847 (69 in our window), 83,055 (166 at 02:20–02:36Z). Two clusters: 30–50k and 90–130k | Median ~47–83k depending on window; ~40k is the low cluster |
| D3-116 | 4A | Nexus commits and pays a full revert on every miss | Partly | Every LANDED miss ran both legs and paid its fee (977); 7,509 missed attempts, mostly bundles, landed nothing and cost nothing | A miss costs money only when it lands (almost always a direct copy): 977 landed reverts paid 24,162,410 |
| D3-117 | 4A | A revert costs ~100–170k CU | Partly | Median 139,793; 61.5% fall in 100–170k, 28.9% below 100k (DAMM v2 routes), 9.7% above 170k (max 399,472); fee set by the CU limit | Median ~140k with a wide spread; lamport cost = CU limit × price (mean 24,731) |
| D3-118 | 4A | Program 1 uses the same model, including no on-chain quoting | Partly | Commit-revert confirmed (229/229 Custom(3) ran their CPIs). Binary has quoting/sizing code behind flag 0x40, set in 0/936 txs; spend = amount_in in 290/291 | Same commit-revert model; P1's binary can quote and size on chain but never did in sampled traffic |
| D3-119 | 4A | Nexus miss rate far higher than Program 1's | Confirmed | Landed failures 97.7% vs 85.3%; per attempt 0.27% success | Send mixes differ, but Nexus is worse on every measure |
| D3-120 | 4A | Therefore Nexus's revert waste is larger | Partly supported | Per minute P1 burns more (~2.0M CU and ~0.9–1.4M lamports on mean fee) than Nexus (~0.52M CU, 0.10M lamports); per win Nexus wastes more (1.05M vs ~0.03–0.6M) | Larger only per successful trade |
| D3-121 | 4B | About half of landed wins still lose money | Confirmed | 11/23 (47.8%), counting rent as spent | 0/23 leaving rent out; the losses are refundable rent |
| D3-122 | 4B | Problem B is quieter and more fixable | Supported | B = 18.09M of recoverable rent; A = 24.16M of fees that are gone; B's fix is engine-only | B is mostly an accounting effect; the tip is already in min_profit |
| D3-123 | 4B | Trade 5RS6vJ1h exists | Confirmed | Slot 453093764, 00:23:40Z, err null | — |
| D3-124 | 4B | 5RS6vJ1h passed the profit check | Confirmed | err null; quote Δ 228,454 ≥ 161,418 | — |
| D3-125 | 4B | 5RS6vJ1h net −0.00165 SOL | Partly | Native −1,649,857 = fee 5,000 + tip 156,417 + rent 1,488,440, but wSOL +228,454 in the same tx | Wallet net −0.00142 SOL (−1,421,403) counting rent as spent, +0.000067 leaving rent out; −0.00165 is native SOL only |
| D3-126 | 4B | Tip ≈0.00016 SOL | Confirmed | 156,417 lamports; Jito explorer agrees | — |
| D3-127 | 4B | Tip went to a Jito tip account | Confirmed | 3AVi9Tg9… is a Jito tip account; bundle 57c429c7… | — |
| D3-128 | 4B | ATA rent ≈0.0015 SOL | Confirmed | createAccount 1,488,440 (165 B, Tokenkeg) | — |
| D3-129 | 4B | createIdempotent is ix2 | Confirmed | ix0 nonce, ix1 CU limit, ix2 ATA, ix3 nexus, ix4 tip | — |
| D3-130 | 4B | ATA create runs before nexus | Confirmed | ix2 before ix3, in log order too | — |
| D3-131 | 4B | Guard measures only the quote account | Confirmed | check_profit on accounts[1]; no native flags or trailer in 5RS6vJ1h or in any of the 1,000 | — |
| D3-132 | 4B | Guard saw a tiny gain ≥ min_profit | Confirmed | +228,454 vs 161,418 (margin 67,036) | min_profit = tip + 5,001 |
| D3-133 | 4B | Guard is blind to the tip and the rent | Confirmed | Snapshots are taken inside the nexus ix; the tip comes after nexus and the ATA before | The guard itself can't see them, but off-chain min_profit includes the tip; only rent is uncovered |
| D3-134 | 4B | Source comment admits fees/tips/creations outside don't count | Confirmed | lib.rs:60-62, exact text | The comment is about native-mode lamport accounting |
| D3-135 | 4B | 23 landed successes in window | Confirmed | 23 err null | — |
| D3-136 | 4B | ~10 of 23 are ~−0.0015 SOL | Confirmed | Exactly 11, from −0.00151 to −0.00142, all rent payers | 11 |
| D3-137 | 4B | Most others are + a few lamports | Partly | 11 of the other 12 gained +1,293 to +10,557 lamports; the 12th is the outlier | Gains of thousands of lamports (0.0000013–0.0000106 SOL), not "a few" |
| D3-138 | 4B | One outlier made +0.0274 SOL | Confirmed | 4bkYuxT9 +27,459,627 (direct via bolt; tip 1,000,000) | — |
| D3-139 | 4B | The 23 sum to +0.011 SOL | Confirmed | +11,045,580 | Counting rent as spent; +29,135,460 leaving rent out |
| D3-140 | 4B | All of it from the outlier | Confirmed | The other 22 sum to −16,414,047 | Leaving rent out, the other 22 are +161,993 |
| D3-141 | 4B | Without the outlier, wins are net negative | Confirmed | −16,414,047 | +161,993 leaving rent out; the rent is recoverable |
| D3-142 | 4B | That sum is before revert fees | Confirmed | 977 failures paid 24,162,410; all 1,000 net −13,116,830 | — |
| D3-143 | 4B Root cause | Builder sets min_profit to clear the guard, not all-in cost | Partly | min_profit = tip + 5,001 for bundles (covers tip and fee), tip + 1 for direct; never rent or margin (exec.rs:514-520) | min_profit always covers the tip, and for bundles the fees too; it never covers ATA rent (nor direct-copy fees or margin). Rent alone caused the losing wins |
| D3-144 | 4B Root cause | Guard rejects min_profit == 0 | Confirmed | lib.rs:173-174 → ERR_BAD_DATA; 0/1,000 used 0, 492 used 1 | — |
| D3-145 | 4B Root cause | Rejecting 0 isn't enough; small min_profit lets losers through | Supported | 5RS6vJ1h passed, then lost after rent | In the data, rent was the only cost the guard didn't see |
| D3-146 | 5. Fix 1 | Set min_profit ≥ tip + rent + fee + margin | Supported | Feasible in exec.rs: creates_ata is known before mp is set; quote is wSOL, so units are lamports | Better form: add rent to the send decision (mp); keep tip + 5,001 for bundles and the tip + 1 floor for direct; or spread the recoverable rent across trades |
| D3-147 | 5. Fix 1 | Fix 1 turns most of the ~10 losing wins into correct skips | Supported | Replay: blocks all 11 losers and 0 of the 12 winners | All 11; "correct" only if rent counts as a loss (leaving rent out they made +114,477) |
| D3-148 | 5. Fix 1 | Fix 1 is the cheapest, highest-impact fix | Partly supported | Cheapest: one extra term. Impact +16.46M per 4 h counting rent as spent, but −0.11M leaving rent out; the 24.16M of failed fees is barely touched | Cheapest; highest-impact only in booking terms, mostly rent that closing the ATAs would recover anyway |
| D3-149 | 5. Fix 2 | Stop paying rent every trade: pre-create/keep ATAs, reuse wSOL | Unsupported | Rent paid only 12 times (12 mints, once each, only on wins); ATAs kept; D3qtLfeA reused in 1,000/1,000 | Already implemented; pre-creating only pays rent earlier (would save ~0.75–0.94M lamports of priority fees per 4 h) |
| D3-150 | 5. Fix 2 | We pay ATA rent on every trade | Wrong | Rent in 12/23 successes and 0/977 failures; no mint paid twice; creates on 2,540 of 8,496 attempts | Once per new mint, on the first landed win |
| D3-151 | 5. Fix 2 | We close the wSOL account between trades | Wrong | 0 closeAccount; D3qtLfeA is the quote account in 1,000/1,000; no close in src | The wSOL account is persistent and never closed |
| D3-152 | 5. Fix 2 | A new-token ATA costs ~0.002 SOL | Partly | 1,488,440 (Tokenkeg, 165 B) or 1,513,840 (Token-2022, 170 B) = 5,080 lamports/byte; 0.002 is the old 2,039,280 rent | ~0.0015 SOL |
| D3-153 | 5. Fix 2 | Guard ignores ATA rent | Confirmed | Separate ix before nexus; min_profit excludes rent | — |
| D3-154 | 5. Fix 2 | Maintain a warm set of ATAs | Unsupported | `held` is seeded from chain, grows, never closed; 10 of 11 rent-free wins used mints held before the window | Already done; more pre-warming saves only CU-priority fees, not rent |
| D3-155 | 5. Fix 3 | check_profit_native exists | Confirmed | lib.rs:238, called at :806 | — |
| D3-156 | 5. Fix 3 | It counts quote tokens plus authority lamports | Confirmed | l.238-242 | Only on native routes (0/1,000); counts only lamports moved inside the ix |
| D3-157 | 5. Fix 3 | Route the tip and rent through the instruction | Unsupported | System and ATA programs are not allowlisted; the native check runs only with native legs; send/mod.rs expects a top-level tip; the tip is already in min_profit | Needs a program upgrade and an engine change, and adds nothing over Fix 1 |
| D3-158 | 5. Fix 3 | With Fix 3, a landed trade is profit-after-tip by construction | Supported | Logic holds if the tip moves into the ix and the lamport check applies to all routes | Not after the tx/priority fee; already achieved off-chain |
| D3-159 | 5. Fix 3 | Fix 3 is optional but strong | Partly supported | Optional, yes. It changes the same 11 trades as Fix 1 and needs an upgrade. Its only extra value is an on-chain guarantee against builder bugs (exec.rs:509-510 records a past −4,447 bundle) | Optional; "strong" only as defence in depth |
| D3-160 | 5. Fix 4 | Drop the durable nonce for a fresh blockhash | Unsupported | No late landing that a blockhash would have prevented; the nonce makes at most one of 16 direct copies land; costs only 36 no-free-nonce skips and 12 "Blockhash not found" | Keep it; dropping it is reasonable only on the single-copy bundle arm |
| D3-161 | 5. Fix 4 | Send via Jito bundle | Partly supported | 7,529/8,496 attempts (88.6%) are already bundle-only; 22/23 wins are bundles; all 977 failure fees come from the direct arm, which also produced the +27.46M win | Already the main path; the open choice is moving the 11.4% direct arm to bundles |
| D3-162 | 5. Fix 4 (implicit) | We are not sending (all) txs as bundles | Partly | Literally true (967 direct-only attempts; 0 attempts used both paths); false if read as "not using bundles" | 88.6% bundle-only, 11.4% direct-only |
| D3-163 | 5. Fix 4 | Co-locate the sender | Unsupported | Send acks p50 0.26–0.82 ms to Frankfurt endpoints; rx→signed 0.196 ms | Already co-located; remaining delay is upstream in the trigger feed |
| D3-164 | 5. Fix 4 | Raise the fire rate | Unsupported | Already 35.3 attempts/min; 0.27% success per attempt; direct attempts land ~1:1 and pay ~24.7k each | The limit is hit quality, not volume |
| D3-165 | 5. Fix 4 | Latency is where the real upside is | Partly supported | Race lost at or before send (would-fail simulations return p50 4.5 ms after send), but our own path is sub-ms; failures are big trades (median 1.904 SOL vs 0.025 SOL for wins), where our quotes are off | Timing matters, but it is upstream (feed and in-block order); quote and sizing quality at large sizes is at least as big; the doc's latency fixes have little left to gain |
| D3-166 | 5. Fix 4 | The latency fix is an off-chain project | Supported | Nonce, send path, sender placement and fire rate are all engine or infrastructure | — |
| D3-167 | 5. Fix 5 | Quote-first path: port venue math and check in-program | Unsupported | Fee = ceil(CU limit × price) in 978/978, so a no-op under the same limit pays the same; 6,531 failed bundles already cost nothing; venue list wrong | Would not cut costs with our fees; worth it only as part of on-chain re-sizing for DLMM, PumpSwap and DAMM v2 |
| D3-168 | 5. Fix 5 | DLMM, CLMM and CPMM are our top venues | Wrong | Landed legs: DLMM 1,050, PumpSwap 626, DAMM v2 305, AMMv4 4, CPMM 3, CLMM 0; the engine has no CLMM venue | DLMM (~53%), PumpSwap (~32%), DAMM v2 (~15%) |
| D3-169 | 5. Fix 5 | Quote-first converts reverts into ~40k-CU no-ops | Unsupported | Program 2 no-op medians 47–83k CU; fees follow the CU limit; an Ok no-op inside a bundle would land and pay fee + tip | Would roughly halve CU but not cost, and would turn free bundle misses into paid ones |
| D3-170 | 5. Fix 5 | Fix 5 is a big lift; do it after 1–4 | Supported | MEVi ELF account 2.76 MB vs Nexus 35 KB; P1's sizing code ~4,200 instructions; payoff doubtful | Fix 2 is already in place |
| D3-171 | 6. Head-to-head | Program 1 and Nexus are the same species | Supported | Both run every swap, then revert on a per-tx floor; both trade own capital | Neither guard is net ≥ 0; P1 has an operator gate, no allowlist, and dormant sizing code |
| D3-172 | 6. Head-to-head | Program 1 is native Rust | Confirmed | No Anchor strings or logs; no 8-byte discriminator; uses sol_invoke_signed_c | — |
| D3-173 | 6. Head-to-head | Program 1 is Fire-&-Revert | Confirmed | 119/119 Custom(3) ran all hops; Custom(3) is 77.5% of landed; jslt → code 3 | — |
| D3-174 | 6. Head-to-head | Both commit-then-revert on a net ≥ 0 guard | Partly | Commit-revert true. Both guards fail when net < min_profit taken from ix data (P1 0x16eb0/0x16ff0; Nexus l.231). P1's min_profit ≥ fee + tip in 271/271 SOL-quoted txs; Nexus uses tip + 5,001 or tip + 1 and never rent | Both revert below a per-tx min_profit floor; P1's floor is ≈ its fee + tip, Nexus's leaves out the direct fee and rent |
| D3-175 | 6. Head-to-head | Program 1 trades own capital, no flash loans | Confirmed | No lending programs; wSOL ≥ amount_in in 287/287; first hop paid from the operator's account in 290/293 | — |
| D3-176 | 6. Head-to-head | Nexus trades own capital | Confirmed | Quote account D3qtLfeA in 1,000/1,000; max amount_in 4.2 SOL vs ~4.23 SOL held | — |
| D3-177 | 6. Head-to-head | Program 1 does no on-chain quoting | Partly | Behaviour: spend = amount_in (290/293 and 370/370), flag 0x40 in 0/936, no logs. Bytes: dlmm.rs/optimize.rs simulators and a solver behind flag 0x40 | No on-chain quoting in observed traffic; the capability exists but is dormant |
| D3-178 | 6. Head-to-head | Same philosophy, opposite results | Supported | P1: 14.7% success share and profitable (win median +1.33M, 0 negative in sample). Nexus: −0.013 SOL (rent spent) or +0.005 SOL (rent left out) | "Opposite" means profitable vs. flat-to-slightly-negative |
| D3-179 | 6. Table / Legs | Program 1's route is passed in | Confirmed | Hop count d[17]&0x1f = number of venue CPIs in 154/154 wins; venue IDs are not hardcoded | — |
| D3-180 | 6. Table / Legs | Program 1 routes of 1–3 legs seen | Wrong | 936 cached txs: 2 hops 683, 3 hops 190, 4 hops 63, 1 hop 0 | 2–4 hops seen; the program accepts 1–16 |
| D3-181 | 6. Table / Legs | Nexus supports 1–8 legs | Confirmed | MAX_LEGS = 8; bytecode check at .text 0x720; all 1,000 txs are 2-leg | — |
| D3-182 | 6. Table / Legs | Nexus runs legs in one clean loop | Confirmed | One `for` loop in source; the ELF has one 639-slot loop holding the only invoke site | — |
| D3-183 | 6. Table / Diagnostics | Program 1 reports a generic Custom(3) | Confirmed | 77.5% of landed; Babq emits no logs; code 3 also used for a data-length check | P1 also has ~10 other codes |
| D3-184 | 6. Table / Diagnostics | Nexus has per-leg NXV2LEG/NXV2OUT diagnostics | Confirmed | NXV2 immediates in ELF; 2 LEG + 2 OUT in all 976 completed routes | — |
| D3-185 | 6. Table / Guards | Program 1's security is an operator signer gate | Confirmed | 4 lddw immediates assemble to 9EwQ; error 7 | — |
| D3-186 | 6. Table / Guards (implicit) | Program 1 has no payer/token guards beyond the signer gate | Wrong | babq.dis: signer lamports snapshotted (0x150e8) and added to net before the min_profit check. Up to 16 token amounts snapshotted (0x157c8) and re-checked after the route (0x16ad8 jge, else code 8 via [r10−0x938] → 0x15150); re-read by me | P1 also counts operator lamports in its profit check and reverts with Custom 8 if a listed token account ends below its start balance; it lacks owner/foreign-signer checks and an allowlist |
| D3-187 | 6. Table / Guards | Nexus has signer + payer + token guards | Confirmed | Code present (:726, :801, :792, :756); 0x4E580005/6/7 immediates in ELF | The signer check accepts any signer; payer/token guards are optional and were never enabled (0/1,000) |
| D3-188 | 6. Table / Native legs | Program 1 has no native-SOL legs | Wrong | My scan (pumpcheck.py): 6 cached Babq wins CPI pump.fun 6EF8 at depth 2. 4 BuyExactSolIn paid from operator lamports (e.g. 1GzymZuM, 1,234,659); 2 Sell paying SOL to the operator (e.g. 47DRFAuk, +3,182,183 SOL / −2,820,185 wSOL) | P1 does run native-SOL pump.fun legs (rare: 6 of 936 sampled) |
| D3-189 | 6. Table / Native legs | Nexus supports native-SOL legs | Confirmed | As D3-055 | Unused |
| D3-190 | 6. Table / Tests | Program 1's tests not visible (stripped) | Confirmed | No .symtab or debug sections; OtterSec not verified | The real reason is no public source; tests never ship in a release binary |
| D3-191 | 6. Table / Tests | Nexus has thorough tests | Supported | 20 host + 10 TS + 6 LiteSVM cases | Thin on-chain integration coverage |
| D3-192 | 6. Table / Land rate | Program 1 land rate 15.8% | Partly | 14.73% of 3,000; 15.9% for the newest 1,000; 400-tx windows 10.25–18.75% | ~15% success share among landed; not a land rate |
| D3-193 | 6. Table / Land rate | Nexus 2.3%, ~7× worse than Program 1 | Partly | 23/1,000; ratio 6.4–6.9× | A success share among landed; per attempt 0.27% |
| D3-194 | 6. Table / Throughput | Program 1 10–17/min | Confirmed | 15.35/min (3,000 sigs); pages 14.7–16.8; 10-min bins 9.4–24.2 | Landed rate |
| D3-195 | 6. Table / Throughput | Nexus 4/min | Confirmed | 4.16 landed/min | Sent 35.3 attempts/min |
| D3-196 | 6. Table / Median win | Program 1 median win +0.0004 SOL | Wrong | All-in net median 1,134,570 lamports over 579 wins; 1.12–1.36M over the random 40; DOC2 says +0.0007 | ~+0.0011 to +0.0014 SOL |
| D3-197 | 6. Table / Median win | Program 1's wins are net-positive | Confirmed | 0/154 negative (minimum +16,040) | A wider 579-win scan finds 3.1% ≤ 0 (USDC handled differently) |
| D3-198 | 6. Table / Median win | Nexus median win ~0 | Confirmed | Median +1,293 lamports (+3,101 leaving rent out) | — |
| D3-199 | 6. Table / Median win | About half of Nexus wins net-negative | Confirmed | 11/23 | Counting rent as spent; 0/23 leaving rent out |
| D3-200 | 6. Table / Sizing | Program 1 performs on-chain sizing | Partly | Code exists (optimize.rs, dlmm.rs; reachable 0x15bc0 → 0x11dd0) but flag 0x40 set in 0/936; spend = amount_in | The capability is present but was never used in sampled traffic |
| D3-201 | 6. Table / Sizing | Program 1's sizing is in optimize.rs | Confirmed | Path src/sizing/optimize.rs, used by the solver and clamp functions | Full path src/sizing/optimize.rs, plus dlmm.rs |
| D3-202 | 6. Table / Sizing | Nexus does no on-chain sizing | Confirmed | amount_in read from ix data; only patched for chaining | — |
| D3-203 | 6. Table / ATA rent | Program 1 avoids per-trade rent by reusing accounts | Confirmed | 150/154 wins used existing accounts; 3 created and closed an ATA in the same tx; net rent 0 | Also uses create-then-close |
| D3-204 | 6. Table / ATA rent | Nexus pays ~0.0015 SOL rent each trade | Partly | Amount right; paid in 12/23 successes, never on reverts, once per mint | Only on the first landed win for each new mint |
| D3-205 | 6. Table / Net | Program 1 is net profitable | Confirmed | Operator balances +5.24 SOL-equivalent over 2.98 h; +0.53 SOL+wSOL and +960 USDC over 5.69 h; no deposits in sample | — |
| D3-206 | 6. Table / Net | Nexus is bleeding | Confirmed | −13.1M in window (rent spent); since funding −86.4M liquid, ~−19.3M even counting recoverable rent; in-window +4.97M (rent left out) exists only because of one trade | Bleeding slowly (−0.013 SOL per 4 h) |
| D3-207 | 6. Head-to-head | Nexus arguably the better-engineered program | Partly supported | Better tests and observability; but fewer legs (8 vs 16), optional guards off, and P1 carries far more machinery (9,426 of its 13,734 instructions are planner-only) | Cleaner and more observable, not more capable |
| D3-208 | 6. Head-to-head | Nexus supports more legs than Program 1 | Wrong | P1 accepts 1–16 hops (0x14bd0–0x14bf8, loop bound 0x14d60) and 4-hop routes were seen; Nexus max is 8 | Nexus supports fewer legs |
| D3-209 | 6. Head-to-head | Nexus has real guards, more than Program 1 | Partly | Nexus: allowlist, token-owner checks, per-leg delivery checks; optional guards off; any signer. P1: operator gate, lamport netting, token non-decrease (code 8), index and overflow checks, min_profit + fee check | Each has guards the other lacks; neither clearly has more |
| D3-210 | 6. Head-to-head | Nexus has better diagnostics | Supported | NXV2 logs vs 0 Babq log lines | P1 has ~10 distinct codes |
| D3-211 | 6. Head-to-head | Nexus loses because Program 1 has three things it lacks | Partly supported | Sizing: dormant (flag 0x40 in 0/293; spend = amount_in). Cost: P1 failure median fee 5,000 vs Nexus 25,600. Pipeline: P1's no-nonce backrun channel produced 140/154 wins, but P1 uses nonces on ~88% of txs | Two of the three have substance (cheap failures, fast no-nonce backrun channel); sizing does not explain the gap |
| D3-212 | 6. Head-to-head | None of the three is fancy | Unsupported | Sizing is 68.6% of Babq code (9,426 of 13,734 instructions planner-only); order-flow access is not simple | Only cost discipline is simple |
| D3-213 | 6. Sizing | Program 1 reads live pool state at execution | Partly | Planner function 0x26d8 reads pool data; planner path (flag 0x40) taken in 0/293 (and 0/877 shred-seen) | Capability only, unused |
| D3-214 | 6. Sizing | Program 1 sizes the trade on-chain | Partly | Code path 0x11dd0 → 0x13770 → 0x9ae8 exists; spend = amount_in in 290/291, failures included | The binary can; observed trades are sized off-chain |
| D3-215 | 6. Sizing | Program 1 has fixed vs adaptive modes | Confirmed | Flag 0x40 gate; logger strings fixed_in / adaptive_in | Only fixed mode observed |
| D3-216 | 6. Sizing | Program 1's adaptive sizing is capped | Confirmed | Logs adaptive_in plus cap = d[18:26]; 'min <= max' clamp | Never exercised |
| D3-217 | 6. Sizing | When a spread shrinks, P1 sizes down and lands | Wrong | 137 measurable failures spent exactly amount_in and reverted; 0/293 adaptive_in logs; wins spent amount_in in 154/154 | Never observed; P1 reverts with Custom(3) (77.5% of landed) when the spread is gone |
| D3-218 | 6. Sizing | Nexus commits to amount_in and reverts | Confirmed | l.739, l.769, check at l.808; wSOL Δ = NXV2OUT leg 1 − amount_in in 23/23 | — |
| D3-219 | 6. Sizing | On-chain sizing turns marginal spreads into wins Nexus throws away | Unsupported | P1 doesn't use it; Nexus reverts sit at median −1.52% of amount_in, and only 19 of 953 within −0.2% | No evidence; the rescue rate is unmeasured (at most ~1/3 by a crude model) |
| D3-220 | 6. Sizing | That is a direct chunk of the ~7× gap | Unsupported | P1 never sized in sample; the gap reflects send mix (our direct copies land when they fail) and P1's backrun channel | No share of the gap can be attributed to sizing |
| D3-221 | 6. Cost | Program 1's wins are net-positive | Confirmed | ≥152 of 154 (141/141 SOL-quoted, min +16,040, median +1.33M) | One SOL→USDC win probably slightly negative |
| D3-222 | 6. Cost | P1 wins are positive because it reuses accounts | Supported | 0/293 top-level ATA ix; 3 wins create and close in the same tx; 75 of 141 wins are below 1,488,440, so per-trade rent would matter | Also because its wins are larger (gross median 3.53M) and min_profit ≥ fee + tip |
| D3-223 | 6. Cost | Program 1 scales its fee to profit | Confirmed | Spearman(cost, gross) = 0.935 over 141 wins; fee set off-chain | Nexus bundles do the same (tip = 0.7 × (expected − 5,000)) |
| D3-224 | 6. Cost | Nexus pays rent plus a tip the guard can't see | Partly | Rent in 12/23, outside both the guard and min_profit. The tip is unseen by the guard but built into min_profit (tip + 5,001) | Only rent is uncovered |
| D3-225 | 6. Cost | Nexus pays these on trades too thin to cover them | Supported | 11 of the 12 rent-paying wins gained 11,794–228,454 against ~1.5M rent | True for rent only; every win covered its tip and fee |
| D3-226 | 6. Pipeline | Program 1 has a faster pipeline | Supported | P1's tx seen before our first send in 37 of 40 duels (median lead 13.7 ms) | Comes from pre-execution access (backrunning), not fire rate or avoiding nonces |
| D3-227 | 6. Pipeline | Program 1 fires 10–17 tx/min | Confirmed | 15.35 landed/min; 30-min bins 11.9–17.6 | A landed rate, which is a lower bound on firing |
| D3-228 | 6. Pipeline | Program 1 does not use a durable nonce | Wrong | Uniform sample: advanceNonce at ix0 in 40/40 failures and 7/40 wins, so ~87.8% of landed txs; 64 nonce accounts | P1 uses a nonce on ~88% of landed txs; its winning backruns mostly don't (140 of 154) |
| D3-229 | 6. Pipeline | Program 1 reaches opportunities while alive | Supported | No-nonce txs 107/107 Ok vs nonce txs 8/107; 2.26 wins/min vs our 0.096 | True only for its no-nonce channel; the doc's stated reasons are wrong |
| D3-230 | 6. Takeaway | Program 2 has ~2.76 MB of ported math | Partly | 2.76 MB is the programData account; the ELF is 1.66 MB (plus 1.10 MB zero padding); .text is 1.59 MB, of which ~0.5–1.1 MB is DEX math | ~1.6 MB of code, a third to two-thirds of it DEX math; still ~14× P1's .text |
| D3-231 | 6. Takeaway | You need P1's discipline, not P2's approach | Partly supported | P1 succeeds without P2-style search (111 KB vs 1.59 MB .text). Perfect discipline would leave our non-outlier wins at only +161,993 per 4 h (rent left out) | Discipline would stop most losses but not create P1-like wins; P1's profit comes from its no-nonce backrun channel |
| D3-232 | 6. Takeaway | Highest-leverage architectural change is on-chain adaptive sizing | Supported | The only program change with modelled value: ~91M lamports upper bound, from 199 of 688 uncapped reverts; other program fixes ≈0 | A model-based upper bound; not the biggest lever overall (71% of reverts had no profitable size); P1 doesn't use it |
| D3-233 | 6. Takeaway | Sizing is the one thing P1 has that Nexus doesn't | Wrong | P1 also has in-instruction ATA create/close, a lamport-netting guard, a fee_in_quote check (code 2), an operator gate and a token non-decrease check; its sizing is dormant | One of several, and the one P1 doesn't use |
| D3-234 | 6. Takeaway | The rest of the gap is cost accounting and latency | Supported | SOL outflow = 24.16M failed fees + 18.09M rent + 1.39M tips + 0.14M success fees | Also engine bugs (19 DLMM, 5 CU-limit), misprediction (median actual/expected −1.25) and send-path mix |
| D3-235 | 7. Bottom line | Nexus is a safe, correct executor | Supported | Correct in 1,000/1,000; uses invoke only, with no PDA signing | Optional guards off; every venue upgradeable |
| D3-236 | 7. Bottom line | The pipeline "starved" the executor | Partly supported | Not short of volume: 53.3 opportunities/min detected, 35.3 attempts/min, 72.2 copies/min, fee cap never stopped the engine. Short of viable ones: rivals took spreads a median 24.4 ms after the trigger; 71% of bundle simulations failed ERR_PROFIT | Over-fed with stale or mispredicted opportunities, not under-fed |
| D3-237 | 7. Bottom line | An arb bot's edge lives or dies off-chain | Supported | All Nexus losses are off-chain; P1's money comes from its backrun channel | Sizing sits on both sides; the doc itself recommends on-chain sizing |
| D3-238 | 7. Bottom line | Nexus is losing in the off-chain parts | Supported | 953/953 reverts correct; losses = direct-copy fees, rent, engine bugs | — |
| D3-239 | 7. Bottom line | None of the fixes requires a rewrite | Supported | Fixes 1, 2 and 4 are engine-only; Fix 3 needs an upgrade; Fix 5 and sizing are large additions | Fixes 3 and 5 need program upgrades |
| D3-240 | 7. Bottom line | Fixes 1–2 stop the self-inflicted losses this week | Unsupported | Fix 1 blocks 11 wins worth +114,477 leaving rent out; Fix 2 is already in place; after Fix 1 the window is still −23.6M without the outlier; the 24.16M of failed fees is untouched | Would not stop the bleed; gate or drop the direct/TPU send arm |
| D3-241 | 7. Bottom line | On-chain adaptive sizing (the P1 lesson) attacks the land rate | Partly supported | Model: a smaller profitable size exists for ≤337/940 reverts (36%), ≤171/940 (18%) after fees; P1 doesn't use sizing; for bundles the tip is fixed at 70% of the original expectation | A secondary lever (at most ~1/3 of reverts), and not a P1 lesson |
| D3-242 | 7. Bottom line | Latency is the real battle | Partly supported | Loss ÷ expected rises with lag (1.18 → 1.57), but 382 reverts that landed in the trigger slot still lost; lamports lost went mostly to send policy (24.16M) and rent (18.09M) | Timing (including in-slot order and trigger-state quality) explains the failures; the money was lost to send policy |
| D3-243 | 7. Bottom line | The program is not why; the pipeline is | Supported | Every lost lamport traces to off-chain choices | Better: "not the main reason", since the program lacks on-chain sizing |

## 3. Method notes

**Inputs used**
- The DOC3 evidence base, `cherry/work/shared/derived/doc3/`: on-chain ELF, build-compare, ELF checks, source-facts, wallet-1000.jsonl, successes-23, summary, engine-minprofit, live-state snapshot.
- First-verifier (V1) results from `ver-doc3-*` and second-check (V2) results from `dispute-doc3-0..6`.
- The DOC1 and DOC2 evidence bases, for the Program 1 and Program 2 rows.
- The run records under `cherry/root/runs` (w5h2-p1..p11, w5h3-p1..p2).
- `ledger-w5h2w5h3.jsonl`, which existed by the time some verifiers ran and was used by them.

**Ground-truth order:** deployed bytes, then live transactions, then source, then docs and prior research.

**Decisive checks I ran myself.** All used the RPC cache only, with no new RPC calls. Files are in `cherry/work/report-doc3/`.
- **D3-188** (`pumpcheck.py`, `pumpcheck.out`): scanned every cached Babq transaction for pump.fun 6EF8 inner instructions. Found 6 wins: 4 BuyExactSolIn with system transfers from operator lamports, and 2 Sell paying native SOL to the operator. That settles V1 "unverifiable" against V2 "wrong" as Wrong.
- **D3-186** (`babq-dis-157c0.txt`, `babq-dis-169f8.txt`): re-read the disassembly.
  - 0x157c8 snapshots token-account amounts ([acct+0x98]) into a 16-entry stack array at r10−0x858.
  - The post-route loop at 0x169f8–0x16ae0 re-reads each amount. `jge` passes; otherwise it sets [r10−0x938] = 8 and jumps to the shared error return at 0x15140, which loads that code.
  - This is a token non-decrease guard, so the verdict is Wrong.
- **D3-115:** recomputed MEVi no-op CU from `dossier-mevi/ext/exec-*.jsonl`: n = 10,827, median 46,856, 33.9% at or below 40k (Oct 3, 20:28–21:36Z). That settles V1 "wrong" against V2 "partly" as Partly.
- **Doc wording:**
  - D3-063: the doc does not contain the "(shared with the off-chain builder)" gloss, so Confirmed.
  - D3-045: the doc says "token (<32)", so Token-2022 counts, so Partly.
  - D3-236: the doc's colon defines "starved" as losing on speed, quality and sizing, so Partly supported.

**Conventions**
- **Landed vs attempts.** getSignaturesForAddress sees only landed transactions. Where the doc's stated scope is the 1,000 landed transactions, a number exact in that scope is Confirmed, with the per-attempt figure as a caveat. A label that changes the meaning, such as calling a success share a "land rate" or a landed rate a "fire rate" when drawing a conclusion, is Partly or Unsupported.
- **Rent.** "Rent spent" means liquid SOL + wSOL. This matches the engine's own `profit_lamports`, which equals the chain net for all 23 wins. "Rent left out" treats the 12 open, empty ATAs (18,089,880 lamports) as still owned. Claims true only under rent-spent are Confirmed with that caveat, for example D3-019, 121, 199.
- **Capability vs behaviour.** A statement true about Program 1's binary but false about its observed traffic, or the reverse, is Partly. This applies to D3-118, 177, 200, 213, 214. A specific behaviour never observed is Wrong (D3-217).
- **Duplicate claims are harmonized** to one verdict:
  - 019, 121, 199;
  - 081, 194, 227;
  - 082, 108;
  - 083, 192, 193;
  - 025, 092;
  - 051, 187.
  - Doing this overrode both verifiers' "Partly" on D3-082 and D3-194. The measured averages, 118.3/min and 15.35–16.7/min, fall on or inside the doc's figures; burstiness is noted as a caveat.
- **Relabels.** Where V1's verdict text itself said "supported in part" or "overstated" on the main point, I mapped it to Partly supported (D3-241, 242).

**Address conventions**
- Nexus ELF offsets in the evidence are relative to .text; .text sits at file offset 0x5b0. Classic `.dynsym` does not exist in SBPF v3, so syscalls were identified by murmur3 hash.
- `babq.dis` addresses are file offsets. Its `<.text+X>` jump labels are offset by −0x120 (for example, label `.text+0x15020` is address 0x15140).

**Corrections to the evidence base found along the way**
- "967 [attempts] also had direct copies" is wrong. The 967 attempts were direct-only; 0 attempts used both a bundle and direct copies.
- Landed failures are 964 direct + 13 unmatched. Some rows say "965 direct", which includes the bolt success.
- Program 1's "0 negative wins" holds for the 154-win sample. A wider 579-win scan with different USDC handling finds 3.1% at or below 0.
- Landing-lag tables differ slightly by source: summary 0:382, 1:481, 2:68 over 964; outcomes.jsonl n = 949; ledger n = 1,010. Conclusions are unchanged.

**Limits**
- No full disassembly of the Nexus ELF. The version verdict rests on byte-identity with the local build.
- Tests were counted, not run.
- Program 1 and Program 2 samples are partly non-uniform caches.
- The Program 2 rate across our window was not time-averaged.
- No ledger-wide re-run of the sizing model; pool state was not reconstructed.
- No write operations anywhere under /home/moiz.