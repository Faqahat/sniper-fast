# sol-trade-sdk and "Bread": final report

**Scope.** We read github.com/0xfnzero/sol-trade-sdk at commit @13ff7f55 as text only, and built or ran nothing from it. We also checked its crates.io releases, public chain data, the providers' docs and our own data. Four investigations were each re-checked by an independent verifier. Claims the verifiers refuted are dropped, and partly-true ones are marked.

## Bottom line
- **The repo is risky, but not malicious as far as we read.** We found no key theft and no fee skimming. Its "submit lanes" are the same pattern that already cost us 986 failed landings out of 987.
- **Bread is most likely promoting a referral business (inference).** He used facts anyone can read from our public wallet. His advice is what we already tried.
- **Worth building ourselves:**
  - racing copies only over revert-protected lanes (WP-18/WP-19);
  - two corrections to WP-19;
  - missing entries in our tip-account map.
- **Not worth it:** unprotected spraying of any kind.

## 1. The repo

**Verdict: risky, and clean as far as we read.** The decisive evidence:
- **No key theft.** The payer key only signs locally. The main spot is `src/trading/common/transaction_builder.rs:251-254`. The others are `src/client/mod.rs:1262,1846-2019` and `src/trading/common/utils.rs:112,167`, and they all send only to the user's own RPC.
  - Every connection goes to the user's RPC or to the chosen provider (`src/swqos/mod.rs:329-354,405-718`).
  - There is no telemetry and no host belonging to the author.
- **No skimming.**
  - The only SOL transfer the SDK adds is the tip (`transaction_builder.rs:173-176`).
  - Every `close_account` refunds the payer, and there is no Approve or SetAuthority.
  - All 144 base58 constants that are not tip accounts check out: the pump fee recipients match pump-public-docs, and the PDAs were re-derived.
- **The supply chain is clean.**
  - The `src/` folder of crates.io 5.0.6 is byte-identical to the repo. It was built from dc9741b, the commit just before the snapshot.
  - Across all 127 published versions there is no build.rs, no git dependency, no proc-macro, and no code that is missing from public git.
  - The author's own crates match GitHub.
  - The force-pushes only rewrote commit messages.

**Why it is still risky:**
- **The send design loses money.**
  - It builds one separately signed transaction per provider (`src/trading/core/async_executor.rs:78-103,783-831`).
  - These use a recent blockhash unless the user opts into a durable nonce, so they are "not mutually exclusive" (README.md:399) and several can land.
  - The guard that required a nonce on buys was removed in 9af86c8, and `src/swqos/common.rs:97-99` wrongly claims "Only one will land".
  - No lane has revert protection. Jito is sent without `bundleOnly` (`jito.rs:76-91`), and BlockRazor has `revertProtection:false` hardcoded (`blockrazor.rs:452,501`).
- **API keys travel in clear text.**
  - 129 of 152 endpoint constants are plain `http://`, with keys in the query string or headers.
  - Six QUIC clients skip the server-certificate check. Temporal's QUIC client does check it (`temporal_quic.rs:77-82`).
  - Stellium defaults to `*.flashrpc.com`, which we cannot link to Stellium. The API key goes in the URL path (`src/constants/swqos.rs:420-431`).
  - Soyas, SpeedLanding and Solami take a base58 **secret key** as the API token.
- **Failures are silent.**
  - Several senders log a provider's rejection and still return Ok (`jito.rs:106-128`, `bloxroute.rs:100-124`, `node1.rs:183-205`, `lightspeed.rs:101-125`).
  - The built-in minimum tips are below the providers' documented minimums, and `check_min_tip` defaults to false.
  - The Lightspeed tip accounts are stale legacy ones (`swqos.rs:144-148`), inactive since April and August 2026.
- **Poor hygiene.**
  - Sensitive changes were hidden in unrelated commits. One example is a Temporal "community key" that routed tips to a separate address, hidden behind a hash (558188b, then dbde80b, removed without comment in 08ccaa3). It shipped in 70 published versions.
  - That address, `mwGELG…`, is swept together with Temporal's own accounts, so Temporal controls it. An off-chain referral share cannot be ruled out.
  - Much of `src/perf/` is stub code ("这里是伪代码", "this is pseudo-code", `syscall_bypass.rs:261-299`).
  - Two new, unofficial maths crates were added two days before the snapshot: meteora-dlmm 0.2.0 and solana-clmm-raydium 0.3.0.

**Not covered:**
- a line-by-line read of about 35k lines of instruction and quote code (it was only grep-audited);
- transitive dependencies (solana, quinn, h3, tonic, reqwest);
- the Telegram groups and the repo's star history;
- who owns the tip account `9tYF5…` and the `flashrpc.com` hosts.

**Live threat.** Malware lookalikes were pushed today: `Agit8037/sol-trade-sdk-golang` and `psychicalcommunicationapparatus88/sol-trade-sdk-nodejs`. Their READMEs tell readers to download a zip and run an `.exe`. Treat any "sol-trade-sdk" link from an owner other than 0xfnzero as hostile.

**Handling rule:**
- never use it as a dependency;
- never clone it onto a machine that holds keys;
- never build or run it, including `test_latency.sh`, which places a mainnet trade when `PAYER_KEYPAIR` is set;
- never paste any key into anything from it or from its partners.

**Our exposure:** nothing references it under /home/moiz/arbed or ~/.cargo, so nothing needs rotating. The Cherry server and the owner's personal machines were not checked.

## 2. The person and the contact

**Social-engineering signs:**
- an unsolicited message from someone not in contacts;
- fishing questions ("how fast do you need to land?", "server in Frankfurt?");
- trust-building ("trust me … alpha for nothing");
- heading off doubt in advance ("not my repo", "get ur llm to check it", the Chinese group as social proof);
- narrowing the ask to "just the submit lanes", which invites us to pull code in;
- a benchmark nobody can check.

**Against it being an attack:** the link is the genuine upstream repo, and he asked for no keys, money or files.

**Likely motive: sales (inference).**
- The README sends users to fnzero.dev/swqos (README.md:682). That partners page shows "奖励 50%" (reward 50%) on LunarLander, Solami, Glaive, SpeedLanding, Astralane and FlashBlock, plus `?ref=fnzero` links for Temporal and others. What the "50%" pays, and to whom, is unclear.
- Bread's top four lanes (Astralane, Temporal, Glaive, BlockRazor) are all on that page; Jito and Helius are not.
- His yardstick, AllenHark, is a Frankfurt vendor. It sells Slipstream ("through the worker closest to the current leader"), a relay with a 0.001 SOL tip, and its own arbitrage bot.
- We have no proof he is affiliated with either.

**What he could read on chain:**
- Our wallet's last 1,000 signatures (2026-10-04, 01:00–05:47 UTC) are 967 failed and 33 successful.
- All 33 successes are Jito bundles tipping 3,375–39,471 lamports (median 8,424).
- The failed copies tip exactly 1,000,000 lamports to Nozomi, NextBlock, SpeedLanding, Helius, Jupiter, Astralane and LandX. 954 of them failed on our profit check.
- Frankfurt cannot be read from the chain; the owner confirmed it himself.

**Did he know our real tip?**
- He knew our **public direct-copy tip** of 0.001 SOL (the sender race in `deploy/legacy/arb-w-live.toml`). That is also the generic default: Nozomi's and Helius Max's minimum, and the SDK's README:283.
- He never mentioned our **winning** tip: Jito bundles, median 8,424 lamports, capped at 100k (`deploy/arb.toml:145`).
- So he needed no inside knowledge.
- Since 2026-10-03 22:00Z the wallet has been spraying across 10+ senders. Telling us "not just Helius" therefore suggests he read older history or the owner's earlier messages (inference).

The owner has already told him we land late and only win small Jito bundles. Share nothing more.

## 3. Bread's claims

| Claim | Verdict | Evidence |
|---|---|---|
| Send to all SWQoS providers, not just Helius | **Partly** | Sending to many providers can land faster, but we already ran it: 731 rounds of 9–16 paths under one nonce, plus 256 Helius-only rounds. 986 of 987 landed transactions failed, costing 24.37M lamports. The test is confounded: in 62.7% of cases the opportunity was already taken before we sent, and some losses were bad quotes from our own engine. Even so, rival Dy1jE82C sprays at least 8 providers and nets −1.24 SOL on our pools (rival-synthesis.md:144). |
| The provider closest to the leader wins | **Plausible, unverifiable** | In our race the untipped tpu-direct (253 wins) and Haan (235) paths won 66% of rounds. |
| The repo has a "provider racing module" | **False** | `execute_parallel` sends to every lane and returns on the first HTTP acknowledgement (`async_executor.rs:504-533`). It cannot tell which lane landed (`executor.rs:217`). "Racing" and "AllenHark" appear nowhere in the repo's history. |
| "Fully open source", "not my repo" | **True / unverifiable** | It is the genuine upstream, MIT-licensed, and the published crate matches git. We found no link between Bread and the repo. |
| The 100-transaction table | **Unverifiable** | There are no signatures. The same-slot column adds up to 89, not 100. AllenHark is not in the SDK, so he used other tooling. A gap measured in transactions means the AllenHark reference was a separate transaction that also landed (inference). Temporal 31 against Astralane 33 is a tie. |
| Helius won only 6 of 100 | **Consistent with ours, irrelevant to profit** | Ours was 26 of 731 (3.6%). But rival wins tipped through Helius carry 5.57 SOL, against Nozomi 0.79 and Astralane 0.66 (rival-synthesis.md:166). |
| Temporal and Astralane did the heavy lifting | **Partly** | Counting only his lanes, our Nozomi share is 38.9% (his 35%), but our Astralane share is 6.25% (his 37%). |
| Same tip, 0.001 SOL | **True, but public** | See §2. |

## 4. What is useful for arbx (built ourselves), and what loses money

- **Keep WP-05 as it is.** The SDK's own failure mode confirms the bundle-only, fail-closed policy.
- **WP-18 is the safe version of Bread's idea.** Sending one signed bundle to several Jito regions cannot land twice.

**Corrections to WP-19:**
- **BlockRazor:** it has a **per-transaction** `revertProtection` flag (docs.blockrazor.io, send-transaction page), not only protected bundles. We need to test whether it works on our binary endpoint.
- **Astralane:** it does document `revertProtection` on sendBundle. That needs a VIP tier; the free tier allows 0 bundles per second.
- **New candidates to add:**
  - Helius Sender Max's sendBundle;
  - AllenHark Relay's `/v1/sendBundle`, which goes to Jito's block engine and adds a 0.001 SOL relay tip.
- **Lunar Lander may reject arbitrage.** HelloMoon's own client has a `BlockedArbProgram` rejection (lunar-lander-quic-client 0.4.0, `lib.rs:221-237`), applied per API key.
- **Caveat:** most "protected" lanes end up in Jito's auction (Nozomi bundles go to builder paths such as Jito and Harmonic), so they add little over WP-18. The real prize is the unidentified revert-protected, non-Jito path used by rivals 9EwQ and 8oSD (rival-synthesis.md:171-172).

**New, for us to build:**
1. **Protected-lane race.** Send the same transaction, or copies under one durable nonce, all at once, but only over lanes that passed WP-19's revert test. Measure with and without a nonce: Nozomi warns that builders may deprioritize nonce transactions, and BlockRazor forbids nonces with its sandwichMitigation mode.
2. **Tip-account map.** Add these to `OTHER_TIP_ACCOUNTS` in `src/send/mod.rs` (lines 62-114):
   - Glaive (6 accounts), Soyas (10), SpeedLanding (8), AllenHark (11);
   - Solami (10, listed by api.solami.dev/onchain/tip-addresses);
   - bloXroute legacy HWEoBx… and 95cfoy… (95cfoy… is bloxroute1.sol per a 2025-06-24 Wayback snapshot);
   - SVS legacy 53PhM3… and 9tYF5….

   In cmp2, 4,197 rival transactions tipped Glaive (p50 5.64M lamports), 458 tipped Soyas and 72 tipped the bloXroute legacy accounts. All of them are currently recorded as "unknown".
3. **Hygiene.**
   - `consultant/research-log.md:102` lists the unattributed Stellium host without an "unverified" flag.
   - `arb-w-live.toml:410` sends `SPEEDLANDING_KEY` over plain HTTP on port 80. SpeedLanding's docs say this key is a base58 **secret key**, so it must be a throwaway keypair and never 2g7rYv7….
   - Our Nozomi `?c=` and Astralane `api-key` values also go over plain http.
4. **Endpoints.** Measure round-trip time from Cherry for 0slot `de2` against `de`, and for Lunar `fra-1.prod` against `fra`.

**What loses money:**
- unprotected copies of an atomic arb on any lane. Each copy that lands and fails costs 25,600 lamports at our compute-unit price, or about 5,000 with tip-only bidding; the tip itself is refunded on failure;
- copies built on a recent blockhash, because several can land;
- 0.001 SOL tips on small opportunities;
- high failure rates, which can get us throttled (Astralane documents this).

**How much a faster lane could win.** cmp2 data, 28 minutes, clean opportunities grouped by how long after our decision a rival took them:

| Rival taker arrives | Opportunities | Quoted (SOL) | Taken by rivals (SOL) |
|---|---|---|---|
| Before our decision | 132 | 2.27 | ≥0.45 |
| 0–20 ms after | 75 | 1.07 | ≥0.54 |
| 20–80 ms after | 123 | 0.393 | ≥0.0605 |
| ≥80 ms after | 105 | 0.080 | 0.006 |

Rivals' takers land p50 23.8 ms after our decision, while our bundles land p50 about 79 ms after sending. Only the 20–80 ms band is plausibly reachable by a faster lane:
- **Under the old live policy:** 0.39 SOL quoted per 28 min. That is at most about 0.84 SOL/h, and rivals realized at least about 0.13 SOL/h of it.
- **Under the arbx policy:** 54 opportunities quoting 0.0107 SOL (p50 53,149 lamports; only one above 1M), about 0.02 SOL/h.
  - It is low partly because arbx drops crowded pools: 173 decisions worth 1.84 SOL, 124 of them taken within 80 ms.
- **Cost of doing it unprotected:** sending all 312 arbx decisions that way would cost about 0.008 SOL per 28 min, roughly the band's whole value.

Two other bands are out of reach of any send lane:
- The 0–20 ms band is a feed-latency problem (our 14.9 ms wait behind Haan's state), not a send-lane problem.
- Opportunities taken before our decision, and order-flow backruns at block index +1 (41% of big-win SOL), cannot be reached by any lane.

The 20 ms and 80 ms band edges are a modelling assumption.

## 5. Proposed experiment X12: lane race (built ourselves, arbx only)

**Gates before anything runs:**
- the owner approves the budget and the wallet;
- the owner does a **native-SOL top-up** of a dedicated test wallet, never 2g7rYv7…. About 0.2 SOL covers it, including K nonce accounts at about 0.00145 SOL rent each (refundable);
- a dry run first (sign but don't send);
- a kill switch.

**Design:**
- Each round sends N copies that share one durable nonce. Each copy has:
  - AdvanceNonce as instruction 0;
  - a compute-unit limit of 10k and the same compute-unit price;
  - that lane's documented minimum tip;
  - a Memo `x12 r=<id> k=<lane>`.
- Send in random order from warm connections, and record the send and ack time of each copy.
- For the one copy that lands, record its first sighting, slot, position in the block, leader and leader kind.
- Only System, ComputeBudget and Memo instructions are allowed.
- Stop if more than one copy lands in a round, or if the spending cap is reached.
- **Arm A (Bread's approach, unprotected):** tpu-direct, Haan, jito-tx, Helius, Nozomi, Astralane, BlockRazor fast mode.
- **Arm B (what arbx would use):**
  - Jito bundle to Frankfurt, plus Amsterdam and London;
  - jito-tx with `bundleOnly`;
  - BlockRazor with revertProtection;
  - Nozomi sendBundle;
  - Astralane bundles and Harmonic, if we get access.
- **Arm C (this is WP-19 step 3):** a self-transfer built to fail, at least 30 per lane. Any landing disqualifies that lane.

**Sample size:** about 400 rounds per arm, which gives ±4.5% on a win share near 0.3. Interleave the arms every 15–30 s over at least 6 h. BAM leaders need about 850 rounds for their own estimate.

**Cost** (a landed round costs about 6k lamports plus the winner's tip):

| Arm | Expected cost |
|---|---|
| A, if our own win mix holds | about 0.045 SOL |
| A, if Bread is right | about 0.26 SOL |
| A, worst case at our 0.001 SOL tip | 0.40 SOL |
| B | 0.01–0.12 SOL |
| C | about 0.0012 SOL |

Hard stop at 0.15 SOL in total.

**Limits:** memo transactions don't compete for hot-pool write locks, so this measures landing speed, not arbitrage profit.

**Free steps first:**
- re-run the 731-round analysis split by leader;
- run WP-19 step 2 (attributing rivals' wins to services) once the tip-account map is updated;
- if the owner wants, ask Bread for the signatures of his 100 rounds, and share nothing in return.

## 6. Open questions
1. Does BlockRazor's `revertProtection=true` drop a failing transaction with zero fee, including on `/v2/sendBinaryTransaction`?
2. Do builders really deprioritize durable-nonce transactions, as Nozomi warns?
3. Who owns `9tYF5…` and the `flashrpc.com` hosts? Is `SPEEDLANDING_KEY` a dedicated keypair?
4. About Bread and the Glaive list:
   - What do his "same-slot rounds" and "AllenHark gap" actually measure?
   - Is he tied to Fnzero, AllenHark or Glaive?
   - Who supplied the Glaive tip list that we recorded as "sent by the owner 2026-10-03"?
5. Is our authenticated Jito rate limit per region (WP-18)?
6. Has anything from the repo or from Bread touched the Cherry server or the owner's machines?
7. Fetching the remaining 62 rival takers in the cmp2 20–80 ms band would turn the realized lower bound into an exact figure.

Supporting files are in `/tmp/claude-1000/-home-moiz-arbed-arb-lab/5e4b11f2-122d-406a-b161-b66016d99287/scratchpad/sts-audit/work/`, in the folders `sec-code/`, `sec-supply/`, `lanes/` and `osint/`, each with its verifier's notes.

## Addendum (main session, after the workflow): SpeedLanding key and wallet check

**SpeedLanding wants a keypair secret, and our live config sends it in cleartext.**
- speedlanding.trade/docs.html, fetched 2026-10-04: "Pass a base58-encoded Solana keypair secret as ?apikey=<BASE58_KEYPAIR_SECRET> … This is not a public key". The HTTP endpoints use port 80.
- Our live config (`deploy/legacy/arb-w-live.toml`, the `speedlanding` sender, enabled at w5h2 on 2026-10-03 22:17Z) sends `http://fra.speedlanding.trade/sendTx?apikey=${SPEEDLANDING_KEY}`.
- So whatever keypair secret SPEEDLANDING_KEY holds went over unencrypted HTTP on every send.
- Our notes (`data/active-senders.md:24`) do not say which keypair it is. We did not read the key.
- **If it is the trading wallet's secret, treat 2g7rYv7… as compromised:** move the funds to a new wallet and retire the key.
- If it is a dedicated, unfunded keypair, the exposure is limited to someone sending through our SpeedLanding identity. Re-register it anyway, and switch to QUIC (port 17778) or the header form.

**Wallet check (public RPC, read-only, 2026-10-04 ~16:00Z).**
- Since 2026-10-03 22:00Z, 2g7rYv7… has 1,583 signatures, 53 of them successful.
- All 53 successful ones invoke our program 8K8uyQDt, plus System / ComputeBudget / ATA.
- The only one with a SOL change below −0.002 SOL is an arb that created a token account (4bkYuxT9…, 22:36:58Z).
- The last activity was 05:47:43Z. Native SOL is 0.021823 SOL.
- So far there is no sign of a transfer that is not ours.

**Other plain-text credentials in the live config** (API keys, not wallet keys):
- Nozomi `?c=`;
- Astralane `api-key`;
- LandX `/txb/<key>` over http, plus the first 12 bytes of each UDP packet.

Move these to https/QUIC endpoints where the provider offers them, and rotate them if in doubt.

**fnzero.dev/partners.** The page lists Glaive and LunarLander keys as obtainable through Fnzero's own Telegram (t.me/xyz_0xfnzero), with "reward_percentage 50%".
