# Three-document review: synthesis and redesign inputs

**Sources.** I read DOC1 (MEViEnsc), DOC2 (Babq) and DOC3 (Nexus), each with its analyst pass and verifier pass, and checked them against our own research: rival-synthesis, the MEViEnsc and 9EwQ dossiers, res-code and res-pnl. The verifiers' corrections are applied throughout.

**One rule for reading the numbers.** Any figure taken from `getSignaturesForAddress` counts only transactions that landed. It is a success rate among landed transactions, not a land rate.

## 1. Verdict per document

**DOC1 (MEViEnsc / SolanaMevBot, "Program 2"): reliable on the binary, unreliable on the business.** Every count we recomputed from the deployed programData matched: 192,275 instructions, 533 panic locations, 34 `sol_invoke_signed_c` sites and 22 `sol_try_find_program_address` sites.

What it gets right:
- The program is a Pinocchio quote-first executor. When it finds nothing, it exits without touching any venue: 0 of 46 no-ops had inner instructions.
- Sizing really happens on chain. Venue program IDs are compiled in, in a tag table where Raydium CLMM, Pancake and Byreal share one adapter tag.
- V9 is not legacy code. 4BQ6ATUt, the only clearly profitable customer, runs V9 (18 of 18 instructions).
- Live routes are 2-leg: DLMM+PumpSwap or DAMMv2+DLMM.

What it gets wrong in the binary:
- The "32-byte discriminators" are checks of which deployment is running, against three program IDs (MEViEnsc, MEMfqXbT, BPodLBws). They are not instruction variants.
- The 6,744-instruction "decoder" is a software SHA-256.
- 2.76 MB is the size of the account. The ELF itself is 1.66 MB.
- The "Newton-style" reading rests on per-function multiply counts. Those mean nothing here, because 128-bit multiplies go through a separate helper (0x182bc0).

What it gets wrong on chain:
- **Operator model.** It says one operator. In fact five vendor fee collectors are hardcoded, and they took exactly 10.0% of profit on 10 of 10 4BQ6 trades.
- **Flash loans.** It misses the built-in flash-loan vault, CHy11HNw, which holds 500.31 WSOL.
- **Priority fees.** It says priority is about 0. In fact 4vAqkstz pays a flat v1 priority fee, p50 3.3k–4.1k lamports.
- **Lookup tables.** It says v1 transactions use lookup tables. None did in two samples (56 and 40 transactions).
- **Where the wins come from.** It credits the program with "skipping marginal trades". In fact 4BQ6 sets min_profit = 0, so 2 of 10 fresh trades grossed less than its own 1.005M cost. Its money comes from exclusive FLASHX8D order-flow bundles.

**DOC2 (Babq / 9EwQoN74, "Program 1"): the most accurate binary description of the three.** The verifier reinstated two points the first-pass analyst had rejected:
- **57 functions is right.** The analyst's count of 73 included syscall call sites.
- **Flags sit in bits 5–6, as the doc says.** The code tests 0x20 and 0x40.

What it gets right:
- Babq is a thin, generic executor with no venue program IDs compiled in.
- Venue minimum-output is set to 0 (388 of 388 calls) or 1 (162 of 162 PumpSwap calls), so the end-of-route guard is the only economic protection.
- The header is 26 bytes and there are exactly 18 syscall relocations.
- A single operator runs it, and the program holds no funds.

Its errors fall exactly where our design choices depend on it:
- **The guard is not "net ≥ 0".** The bytecode returns Custom(3) when net < min_profit, and Custom(2) when net < min_profit + fee_in_quote. The operator puts its whole bid into min_profit: 0 of 142 wins were net-negative.
- **The on-chain sizer is never used.** It runs only when flag bit 6 is set on a 2-hop route. Bit 6 was set in 0 of 347 transactions, outflow equalled the bot's amount_in in 269 of 270, and the program emitted no log lines.
- **"PDA-signed CPIs" is wrong.** The signer-seeds length is 0 at all four call sites, and 932 of 932 transfers were authorised by the 9EwQ wallet.
- **"Nothing predicts success" is wrong.** The send class does:

  | Send class | Success among landed |
  |---|---|
  | No-nonce paths | about 100% |
  | Durable-nonce lottery | about 3% |
  | Fixed-bid fan-out | 0 |

**DOC3 (Nexus Arb v2, ours): right headline and right counts, wrong readings.** It is correct that the program is not the bottleneck.

What it gets right:
- The deployed program is byte-identical to `arbed/program/nexus-arb-v2` (the 812-line lib.rs, ELF md5 809315be). It is not the arbed-live version.
- Balance chaining, the NXV2LEG/NXV2OUT leg logs and the 0x4E58 error range all work on chain.
- All 953 ERR_PROFIT reverts ran every leg before reverting.
- Our median win really is far smaller than Babq's.

What it gets wrong:
- **"2.3% land rate", "~4 tx/min" and "95.3% ERR_PROFIT" come from counting landed transactions only.** In that window we sent 8,507 attempts, 35.4 per minute:

  | Arm | Attempts | Landed | Succeeded |
  |---|---|---|---|
  | Bundles | 7,538 | 22 | 22 of 22 |
  | Direct | 969 | 965 | 1 |

- **The guard is not blind to the tip.** min_profit = tip + fee + 1 on 22 of 22 bundle wins. Its showcase loss, 5RS6vJ1h, was −0.001421 SOL, all of it recoverable rent; excluding rent the trade made +67,037 lamports.
- **The 19 "Whirlpool 6036" failures are Meteora DLMM failures.** The extension account the doc blames does not exist for any of the 11 pools involved. More likely the swap ran out of liquidity (inference).
- **The wallet is not "bleeding to 0.05 SOL".** WSOL holds 4.232 SOL. After about 63.3M lamports of closable rent, the real loss since funding is about 9.5M lamports.
- **Two of its five fixes point the wrong way:** adding rent to min_profit, and dropping the nonce to fire more often.

## 2. Key claims and final verdicts

| Doc | Claim | Verdict | Corrected fact |
|---|---|---|---|
| 1 | 192,275 instructions, 614 functions, 2.76 MB | Partly | Counts exact. 614 is a lower bound (14 indirect targets). The ELF is 1,657,608 B; 2.76 MB is the account allocation. |
| 1 | 11 venue IDs hardcoded, 5 "pending" | Confirmed, mostly resolved | Byreal REALQ…, Futarchy FUTARELB… and BisonFi BiSoNHV… found. Heaven and Vertigo unresolved. The table starts at 0x186bc7 with 11 entries, Manifest at tag 0. |
| 1 | 32-byte discriminators are instruction variants | Wrong | They are checks of which deployment is running. V9 vs V10 is chosen by opcode 28 vs 61. |
| 1 | 0x165cf0 is the instruction decoder | Wrong | It is SHA-256. decode.rs and encode.rs belong to a base58 crate. |
| 1 | Newton-style refinement with few multiplies | Downgraded | Multiplies are out of line (helper called 29 and 22 times). The algorithm is unverified. |
| 1 | No flash loans | Wrong | Vendor vault CHy11HNw with PDA 5LFpzqgs, used by 4vAqkstz (29 of 29) and 2BKYGMaD (11 of 11). |
| 1 | One operator; SMB key is not a fee sink | Partly | The SMB key is absent from trades, but the vendor collectors take 10.0%. Customers look separate (inference). |
| 1 | Land rate 99.8% | Misnamed | 996–998 of 1,000 succeeded among landed transactions. |
| 1 | Priority ~0; v1 transactions use lookup tables | Wrong | v1 priority is a flat p50 of 3.3k–4.1k lamports. 0 of 96 v1 transactions had lookup tables. |
| 1 | Miss costs the base fee | Partly | 4vAqkstz ~8.6–9.1k, 2BKYGMaD 24,500, 4BQ6 1,005,000 lamports. |
| 1 | Fewer, fatter wins because it skips marginal trades | Wrong | min_profit = 0 in 18 of 18. Wins come from FLASHX8D flow. |
| 2 | 57 functions, 13,734 instructions | Confirmed | — |
| 2 | PDA-signed CPIs | Wrong | Seeds length 0. 9EwQ signs every transfer. The program owns 0 accounts. |
| 2 | Optimal sizing on chain, logged | Wrong in practice | Gated behind bit 6, which was never set. Outflow = amount_in in 269 of 270. 0 log lines. |
| 2 | Guard is net ≥ 0, tip outside it | Wrong | net ≥ min_profit (Custom 3) and net ≥ min_profit + fee_in_quote (Custom 2). The bid is inside min_profit. |
| 2 | Venue min-out 0; the guard is the only protection | Confirmed | 0 on 388 calls, 1 on 162 PumpSwap calls. |
| 2 | ZeroFi uses a 25-byte XOR-masked payload | Unsupported | All 6 ZeroFi CPIs were 17 B. |
| 2 | Route does not predict success | Partly | Route does not; send class does (~100% / ~3% / 0). |
| 2 | Losing is nearly free | Partly | 5,000 lamports on the nonce tier. The fixed-bid tier pays p50 798k per failure and won 0 times. |
| 2 | Custom(14) = i128 overflow | Unverified | In the data: all legs ran but no quote was returned (13 of 13). |
| 3 | Deployed program = arbed source | Confirmed | 62 worktrees hold the stale 709-line source; 2 hold mismatched .so files. |
| 3 | 2.3% land rate, ~4 tx/min | Meaning wrong | 35.4 attempts/min. Bundles: 0.29% landed, 100% of those OK. Direct: 99.6% landed, 0.1% OK. |
| 3 | Guard blind to the tip | Wrong | tip + fee + 1 on 22 of 22. Only rent is outside the guard. |
| 3 | 6036 failures are Whirlpool slippage | Wrong | DLMM liquidity exhausted (inference). 7 of 19 are one pool, FpJWjYZ5. |
| 3 | Wallet bleeding at ~0.05 SOL | Misleading | WSOL 4.232 SOL. Real loss about 9.5M lamports. |
| 3 | Durable nonce is a latency smell | Wrong | Bundles carrying a nonce land at slot +0 or +1, about 66 ms after sending. |
| 3 | Babq uses no nonce and sizes on chain | Wrong | 80 nonce accounts. The sizer is never enabled. |
| 3 | Program is not the bottleneck | Confirmed | Our own overhead is 11.6k–18.5k CU per 2-leg route. |

## 3. Docs versus our research

**Where our research was right and the docs were wrong:**
- **MEViEnsc (DOC1).** Our dossier described a public SolanaMevBot product with a 10% vendor fee and separate customers. It also had 4vAqkstz paying priority, flashloan = 1 for the sprayers, and 4BQ6's edge as order flow (22 of 133 backruns below cost). The binary now proves the vendor fee sink.
- **9EwQ (DOC2).** Our 9EwQ dossier already had these:
  - F7: min_profit carries the bid.
  - F1: two businesses in one wallet (no-nonce 105 of 105 vs nonce 6 of 413).
  - F2–F4: Astralane bundles; the priority path only on non-BAM Jito leaders; index +1 behind the opener.
  - F10: the fixed-bid fan-out loses.
- **Our own program (DOC3).** res-code, res-pnl and rival-synthesis were right on these points:
  - Bundle min_profit is tip + fee + priority + 1.
  - Failed bundles cost nothing.
  - Rent can be recovered by closing accounts.
  - The ~14.9 ms delay is waiting for the state feed, not the nonce.
- **No-ops in bundles.** Rival-synthesis says not to put plain no-ops in bundles. DOC1 §6 recommends a quote-first, no-failure design. Rival-synthesis is right, and the verifier went further: a no-op is never cheaper than a revert when the transaction carries any unconditional payment.

**Where the docs and their checks agree with us:**
- Program design does not decide who earns most (DOC3 and synthesis §6).
- PumpSwap↔DLMM 2-leg routes dominate.
- Babq's edge is order-flow position, not its program.

**Where the checks correct our own research:**
1. **MEViEnsc size.** Our catalogue quoted 2.7–2.76 MB, which is the account size.
2. **Babq route length.** The dossier's "2–9 venue CPIs" counted the venues' own event self-calls. Real routes have 2–4 hops, and 75% of 174 successes are 2-hop.
3. **Babq sizing.** We said Babq's sizing had no visible effect; the reason is now known (gated behind a flag that is never set).
4. **"Failed bundles never land."** This is almost always true but not strictly: 10 would-fail bundles landed in the synthesis window, and 1 in w5h3-p1.
5. **The `failed_fees_lamports` counter.** In outcomes.jsonl it is a running cumulative counter, so summing it line by line overcounts.
   - **True totals:** 28,059,910 lamports across all segments, and 2,247,284 for p12, p14 and w5h2-p1 together.
   - **To redo:** any figure built by per-line summing, including "~0.42 SOL in ~0.30 h".
   - **Unaffected:** DOC3's 24.16M, which was measured on chain.

**New facts none of us had:**
- **MEViEnsc:**
  - The vendor fee collectors are compiled into the binary, and their proceeds are swept to DEXWBmnN.
  - BPodLBws is a second deployment of the same build.
- **Babq:**
  - Custom(2) is the second guard term.
  - Custom(14) means "all legs ran but no quote came back".
- **Our own system:**
  - The DLMM 6036 failures are liquidity exhaustion, not a missing account.
  - The live tip_share is 0.7, while repo `deploy/arb.toml:139` says 0.5.
  - On-chain profit equalled the prediction exactly on 18 of 22 bundle wins, so those wins were uncontested.
  - Direct-copy fee = 5,000 + ceil(CU limit × 100,000 / 1e6), exactly, on 977 of 977 landed failures.
  - A latent encoding bug: a leg with 64 or more accounts collides with the NATIVE flag bits.

## 4. Redesign inputs

**1. What happens on a miss: revert everywhere by default (ADOPT). Quote-first no-op as the main mode (REJECT). No-failure mode only when riding a counterparty's bundle (ADAPT).**
- Bundle misses never land: 6,359 of 7,529 window bundle attempts were Jito "would-fail", at zero cost.
- Landed direct failures paid only their fee: the tip rolled back in 977 of 977.
- A no-op pays any unconditional tip: 2BKYGMaD pays 19,500 per no-op, and 4BQ6 pays 1,005,000.
- A low-CU no-op saves nothing on fees. v0 fees follow the requested CU limit, and v1 priority is flat.
- For order-flow backruns, where a revert would drop the counterparty's transaction, use no-failure mode and price the unconditional payment as the miss cost.

**2. On-chain sizing: INVESTIGATE first; then ADAPT as an optional per-route flag (Babq-style, off by default). Pool basket (2–4 pools or 2 routes per bundle) with a bundle-level guard: ADAPT, conditional on the same replay.**
- **For:** A9pQ (+0.82 SOL/h) and Bgok (+1.71 SOL/h) win with sizing, baskets and a guard.
- **Against:**
  - Our direct failures had an on-chain round trip of p50 −150 bps of size: the gap had closed or reversed, not shrunk.
  - 18 of 19 attempts that 4BQ6 beat were gaps already closed.
  - Babq never uses its own sizer.
- **Maths, if built:** closed form for CPMM/PumpSwap, a bin-walk for DLMM, and a per-range closed form for DAMMv2 (it is a sqrt-price curve, not bins).
- Do not copy MEViEnsc's 1.66 MB engine.

**3. Guard: ADOPT Babq's two-term shape, `net ≥ min_profit + fee_in_quote`, measured including lamports.** Measure the quote-token delta plus payer lamports spent inside the instruction.
- **Bundle and revert-protected paths:** keep min_profit = tip + fee + priority + margin (exec.rs:517-521). Consider a margin above +1; A9pQ uses tip + 15k.
- **Unprotected paths:** keep tip + 1. Raising it there turns small-loss completions into full-fee reverts. Better still, send no priority-paying unprotected copies at all.
- **Never allow min_profit = 0.** That is how 4BQ6 loses on 2 of 10 trades.
- **Do not add recoverable rent to min_profit** (REJECT; the stake is +114,477 lamports across 11 wins). Remove rent structurally instead (item 5).

**4. Tips: ADOPT plain top-level System-transfer tips. CPI tips: REJECT for now.**
- Atomic revert already makes a top-level tip conditional on profit.
- Against CPI tips: our sender-services.md:119 says most senders require plain top-level transfers, and MEViEnsc hardcodes 0 of 253 known sender tip accounts. Its 10% fee is a token transfer to the vendor, not an auction tip.
- Revisit CPI tips only if basket sizing makes the executed route unknowable off-chain, and only after one small test bundle.
- **A/B tip_share 0.7 vs about 0.3 (ADOPT).** Tips are 58.8% of bundle-win gross, and those wins look uncontested. Babq bids 60–75% only on contested backrun channels; A9pQ and Bgok bid 16–33%.
- Fix the repo/server config drift (0.5 in the repo vs 0.7 live).

**5. Token accounts: ADOPT a CloseAccount in the same transaction for any freshly created intermediate account.**
- In a 2-leg round trip, leg 1 spends what leg 0 delivered, so the intermediate balance returns to 0 and can be closed.
- Keep a warm, pre-created set for hot mints.
- Sweep the 28 empty accounts (42,158,920 lamports) between segments. That is an operator action, for later.
- 12 of 23 wins created accounts, locking 18,089,880 lamports; Babq created accounts in 0 of 259 successes.
- Check the size limit: copies already reach 1,209 of 1,232 bytes.

**6. Nonce vs blockhash.**
- **Keep the durable nonce for the multi-path direct fan-out (ADOPT).** It dedupes the copies: 965 landings from 969 attempts.
- **Recent blockhash for bundle-only attempts (INVESTIGATE).** It would remove "Blockhash not found" on consumed nonces and the gaps from the 1-second settle window.
- **"The nonce adds latency" (REJECT).** There is no evidence for it.

**7. Send paths.**
- **Per-leader routing across BAM, non-BAM Jito and other leaders (ADOPT).** Babq's priority path appears only on non-BAM Jito leaders. Bgok lands 54% of its bundles on BAM; we landed 2 of 17 known bundles there.
- **Fixed-bid paid fan-out (REJECT).** Babq's version won 0 of 84 in every sample and paid p50 798k per failure.
- **Our direct arm (INVESTIGATE / restructure).** It produced 1 win in 969 attempts against 24.16M lamports of fees, and its sign was decided by a single +27.46M bolt win. p12 and p14 had 0 wins. Options:
  - a pre-send conflict check (the taker was already in our shreds in 480 of 798 attempts);
  - zero-priority shots at a 5,000-lamport fee, like Babq's nonce tier;
  - dropping the arm.
- **Order-flow channels (INVESTIGATE):** Astralane backruns and Helius backrun rebates.
- **v1 transactions (INVESTIGATE).** Jito accepts them as 1-transaction bundles (8 of 8), and priority is flat. But v1 has no lookup tables and a 64-key limit.

**8. Latency: ADOPT shred-level triggers with correct simulation state.**
- Our internal path is 0.19 ms.
- Trigger-to-send is 14.1 ms (bundles) and 15.2 ms (direct). 90% of attempts are triggered by the state feed.
- Simulations ran at slot −1 in 98–99% of cases.
- Two caveats: 218 of 220 shred-decoded bundles came back would-fail, and the rivals who win the earliest positions see the opener before it executes.

**9. Venues and routes: ADAPT.**
- **The program already does more than we use.** It supports 8 legs, any quote token and native-SOL legs. The engine builds 2-leg WSOL routes over 5 venues.
- **Order new venues by measured missed opportunity:** USDC quotes, Manifest, Tessera V, Whirlpool, and the CLMM forks (one CLMM math layer serves Raydium CLMM, Pancake and Byreal). 9 of 23 slow-slice candidates touched pools we never priced.
- **Breadth matters more than depth.** 75% of Babq's successes are 2-hop.
- **Pass venue IDs per transaction** and check them against a compiled allowlist, as ours already does with 12 venues.
- **DLMM:**
  - cap leg input at the liquidity in the bin arrays we hold;
  - quarantine pools like FpJWjYZ5;
  - size CU limits from the bins crossed (5 transactions ran out of CU).

**10. CU budget and Pinocchio: ADAPT.**
- Our 11.6k–18.5k CU of overhead per route is fine. Pinocchio is only worth it if basket sizing needs the headroom.
- The real fee lever is the requested limit: p50 206k requested vs 140k used.
- **MEViEnsc-style anti-clone checks and SHA-256 in the hot path (REJECT).** They cost CU and buy nothing for a private bot.

**11. Security and keys.**
- **ADOPT:** swap with the trading wallet's own signature, with no PDA vault and nothing held by the program (Babq works this way, and so do we).
- **ADOPT:** keep the upgrade authority (GNv76A95) cold and separate from the trading wallet. 9EwQ's single hot key for both is the anti-pattern.
- **Fix the meta-byte bug** (64 or more accounts in a leg would be misparsed).
- **INVESTIGATE:** enabling the payer/token guard trailer once fork venues are added, and finishing the evil-venue test, which stops at 30 lines.

**12. Capital.**
- **Flash loans (REJECT).** MEViEnsc's vault is vendor-only, and its borrowers are the losing sprayers.
- **Raise the 4.2 SOL cap only after sizing exists.** 4BQ6's trade sizes run p90 5.03 and max 23.4 SOL, and 75% of Mriya's gain came from trades of 4.2 SOL or more.

**13. Observability: ADOPT.**
- Track each arm from attempt to copy to landing to success, reconciled against the chain after each segment.
- Separate Jito acceptance from landing (146 accepted vs 17 landed in the window).
- Never compute a land rate from getSignaturesForAddress.
- Treat `failed_fees_lamports` as cumulative.
- Report rent separately from trading P&L, and use a longer settle window.
- Auto-unwrap WSOL when native SOL runs low. Native is 43.97M lamports, against a per-segment failed-fee cap of 23.4M.
- Save would-fail state so it can be replayed at smaller sizes.
- Keep one source of truth for the program source.

**14. High-volume spraying: REJECT.** 4vAqkstz runs about 10k tx/h at roughly 0.089 SOL/h in miss costs.

**Open questions to answer before building:**
1. What share of bundle would-fails (450 of 579, 571 of 802) still had a positive smaller size against the post-trigger state? This decides item 2.
2. Do Jito and BAM count tips paid by CPI?
3. Is the direct arm positive EV? It needs an average win of at least 25M lamports per ~1,000 attempts. How do its failures split between lost races and stale quotes?
4. Why are bundle wins so small (9k–228k lamports) when bundle attempts expect p50 196k? Are we pricing phantom large gaps?
5. Does a lower tip_share reduce landing?
6. Does a same-transaction CloseAccount fit in 1,232 bytes?
7. Can bundles use a recent blockhash instead of the nonce?
8. Can we get admitted to order-flow channels, and how does 9EwQ land its priority path at index +1 without bundles?
9. Does our own bundle path have a hidden failure rate between acceptance and landing?
10. Lower priority: the meaning of Custom(14), the Heaven and Vertigo program IDs, and who controls 4BQ6's 1M-lamport recipients.