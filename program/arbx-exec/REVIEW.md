# arbx-exec: adversarial review (security, correctness, tests)

Reviewed on 2026-10-04 against `docs/research/redesign-final.md` §3.9, with `program/nexus-arb-v2` as the reference.

**What was reviewed**
- `src/lib.rs`: md5 `dcfb1ec2`, mtime 08:27.
- The built `target/deploy/arbx_exec.so`: md5 `e66c5615`, SBPF v3 (e_flags 0x3).
- `src/tests.rs`, `src/v2_reference.rs` and `tests/mock-amm`.

**What I ran**
- `cargo test --release` in arbx-exec: 45 host tests pass.
- `cargo test --release` in nexus-arb-v2: 20 pass.
- `cargo-build-sbf --features onchain`: builds and is up to date.
- `review/` (new, REVIEW-ONLY): `cargo test --release -- --nocapture --test-threads=1`. These 15 LiteSVM tests run the built
  `.so` files:
  - arbx-exec;
  - the deployed nexus-arb-v2 ELF (md5 809315be);
  - the mock AMM, loaded at the DLMM, CPMM, PancakeSwap-fork and pump.fun addresses and at one unlisted address.

  The tests are a standalone workspace with their own target directory, so they never touch the crate's own build.
  Tests named `finding_*` pass while the weakness is present: they are proofs, not goals.

Severity scale:
- **Blocker**: the program does not work, or loses funds, as deployed.
- **Major**: fix this before any v3 feature is switched on.
- **Minor**: fix when convenient.
- **Info**: no action needed now.

---

## Summary

| # | Sev | Finding |
|---|---|---|
| 1 | **Blocker** | `sol_remaining_compute_units` is not enabled on mainnet. Every route, v2 or v3, aborts at the guard with "unsupported BPF instruction". |
| 2 | **Major** | PAYER_GUARD is optional in v3. A bare v3 route still passes after a hostile venue assigns the wallet to itself, takes lamports, or takes tokens. |
| 3 | **Major** | There are no on-chain tests. `tests/litesvm.rs` does not exist, the mock AMM is unused, and nothing runs the `.so` under mainnet features. That gap is how #1 got through. |
| 4 | **Major** | CPI_TIP without COUNT_LAMPORTS computes the tip from the quote gain alone. Lamports lost inside the legs are ignored, so a tip is paid on a transaction that lost money. |
| 5 | Minor | ERR_TIP_FUNDS ignores rent exemption. AXS1 can say `result 0` and the transaction then fails with InsufficientFundsForRent. |
| 6 | Minor | NATIVE_IN and NATIVE_OUT are accepted together on one leg. Its "delivered" is then the net lamport change. |
| 7 | Minor | The quote account is not tied to the authority. The guard passes when the profit lands in someone else's wSOL account. |
| 8 | Minor | The v2 path is parsed exactly like nexus-arb-v2 but does not behave identically: error codes, an extra log record, +241 CU, and codes the engine does not map. |
| 9 | Minor (engine) | `src/build.rs:213` accepts v2 legs with up to 255 accounts. A leg of 64 or more accounts is silently re-read as a NATIVE leg. |
| 10 | Info | Allocation and CU notes. One code comment is wrong, there is a redundant re-check, and LTO is off. |
| 11 | Info | The documents referenced in the code (README.md, LOGS.md, tests/litesvm.rs) do not exist. `MAX_IX_ACCOUNTS` is unused. |
| 12 | Info | The CPI tip can only go to the 8 Jito tip accounts. |
| 13 | Info | Attributing a failed leg by counting AXL1 records breaks when logs are truncated. AXS1 is missing on leg, venue and account errors. |
| 14 | Info (hardening) | Every venue receives the authority as a writable signer. A per-leg "authority read-only" flag would remove the theft surface. |

The v3 parser, the guard arithmetic, the tip gating, the allowlist and the per-leg guards all hold under test. See
"Verified OK" at the end. The blocker is a single syscall, and fixing it is a small change.

### CU (measured)

The route is the same 2-leg mock round trip (DLMM-addr → CPMM-addr) on the same pools in every row, and the quote
delta is identical (92,330,399) in every row. The arbx-exec numbers were taken with the remaining-CU syscall enabled,
because without it the program aborts (#1).

| Program / layout | CU of the route instruction |
|---|---|
| nexus-arb-v2 .so, v2 | 19,905 |
| arbx-exec, v2 | 20,146 (+241) |
| nexus-arb-v2 .so, v2 + guard trailer | 22,216 |
| arbx-exec, v2 + guard trailer | 22,384 (+168) |
| arbx-exec, v3 bare | 19,945 |
| arbx-exec, v3 PAYER_GUARD | 22,014 |
| arbx-exec, v3 PAYER_GUARD \| COUNT_LAMPORTS | 22,005 |
| arbx-exec, v3 PAYER_GUARD \| COUNT_LAMPORTS \| CPI_TIP | 24,202 (the tip CPI costs about 2.2k) |
| v3 native: lamports → X → wSOL / wSOL → X → lamports | 21,408 / 18,821 |

---

## Findings

### 1. BLOCKER: `sol_remaining_compute_units` does not exist on mainnet, so every route dies at the guard

**Location:** `src/lib.rs:774` (import) and `src/lib.rs:997` (`cu_remaining: sol_remaining_compute_units()` inside the AXS1 record). This
path runs for both layouts, on every route that reaches the guard.

**Problem**
- The syscall is gated by the feature `remaining_compute_units_syscall_enabled` (`5TuppMutoyzhUSfuYdhgzD47F92GL1g89KpCZQKqedxP`), which is not active on mainnet.
- The ELF is SBPF v3, which uses static syscalls. The verifier accepts any `CALL_IMM` (solana-sbpf 0.23 `verifier.rs:401`). The interpreter and JIT raise `UnsupportedInstruction` only at run time, when the hash is not registered (`interpreter.rs:582-585`).
- So the program **deploys without error**. Then every route runs all its legs and aborts at the guard with `ProgramFailedToComplete: unsupported BPF instruction`, and AXS1 is never logged.
- The engine's sim gate (`exec.rs`, `config.rs:217`: "ok or 0x4e580002 means the encoding is right") would read this as an encoding failure on every opportunity.
- Because v2 routes are affected too, switching only the program id is not a working rollback path to this program.

**Proof**
- On-chain evidence:
  - The mainnet RPC (apiVersion 4.3.0, slot 453,208,111) returns `getMultipleAccounts([5TuppMut…]) → [null]`. The feature has never been activated.
  - agave 4.3 (`solana-syscalls-4.3.0/src/lib.rs:514-519`) registers the syscall only through `register_feature_gated_function!`.
  - LiteSVM 0.17's mainnet feature list (taken from the cluster on 2026-09-27) does not contain it either.
- ELF audit: decoding every `call imm` with src=0 against murmur3 syscall hashes gives:
  - arbx_exec.so = {**sol_remaining_compute_units**, sol_log_, sol_panic_, sol_log_data, sol_invoke_signed_rust, abort, sol_memcmp_, sol_memcpy_};
  - nexus_arb_v2.so = the same set without `sol_remaining_compute_units`.
- Test `review/tests/adversarial.rs::finding_00_blocker_every_route_dies_at_the_guard_with_mainnet_features`:
  - with LiteSVM's mainnet features, arbx-exec v2 and v3 both fail with `InstructionError(1, ProgramFailedToComplete)` / "failed: unsupported BPF instruction";
  - the identical v2 bytes succeed on the deployed nexus-arb-v2 ELF.

**Fix**
- Do not call the syscall. Set `cu_remaining = 0` (meaning "unknown") until 5TuppMut… is active. If CU at the guard is wanted now, call `sol_log_compute_units()` right before the AXS1 record: that syscall is always registered and costs about 100 CU.
- Add a CI step that lists the static-syscall hashes of the built ELF and checks they are a subset of what mainnet has registered. The decoder used here is about 30 lines of Python.
- Make every SVM test use `LiteSVM::new()`, which loads mainnet features (see #3).

### 2. MAJOR: PAYER_GUARD is optional in v3, so a hostile venue can take the wallet while the profit guard passes

**Location:** `src/lib.rs:527-534` (guard parsing) and `884-897` and `957-965` (snapshots and the token guard, which run only when `guard.is_some()`).
The foreign-signer check does run for every v3 route (`check_signers = v3 || guard`), but the lamport, owner and token guards do not.

**Problem**
- Every leg receives the authority as a **signer and writable**, because the CPI metas copy the AccountInfo flags.
- In a v3 route without PAYER_GUARD, a venue can do any of the following and the profit guard still passes:
  - a System `assign` of the trading wallet to itself (an upgradeable venue, a hijacked upgrade authority, or a Raydium-CLMM fork such as allowlisted ids 4 and 5);
  - transfer lamports out of it;
  - drain any authority-owned token account that is passed to it writable.
- This is the exact threat nexus-arb-v2's guard trailer was added for (UPGRADE-2026-09-15). v3 keeps it opt-in, while the plan says "the builder adds the payer-guard trailer to every route". That makes a single engine flag the only barrier against losing the whole wallet.

**Proof:** `finding_01_v3_without_payer_guard_lets_a_hostile_venue_take_the_wallet`, using the mock at the PancakeSwap-fork address.
- A bare v3 route whose venue assigns the authority **succeeds**, and the authority's owner afterwards is `HpNfyc2S…`. The wallet is bricked: it can no longer pay fees, and the venue can debit it at will.
- The same with COUNT_LAMPORTS also **succeeds**. With CPI_TIP it happens to fail with `ExternalAccountLamportSpend`, because the System program no longer owns the payer. That is an accident, not a guard.
- Taking 0.5 SOL of lamports: **succeeds**, and the attacker is paid.
- Draining 4,000 X from a second authority token account: **succeeds**.
- With PAYER_GUARD the same routes revert: assign gives ERR_PAYER_GUARD and the token drain gives ERR_TOKEN_GUARD.

**Fix**
- Make PAYER_GUARD **mandatory in v3**: no flag means ERR_BAD_DATA. That costs 8 bytes and was measured at +2,069 CU for 2 legs (19,945 → 22,014).
- Alternatively, make it mandatory whenever any leg's venue is one that third parties can upgrade, but "always" is simpler and auditable.
- Keep v2 unchanged for compatibility.
- See also #14.

### 3. MAJOR: no on-chain tests; the plan's required test suites are missing

**Location**
- `Cargo.toml:22` and `src/tests.rs:2` refer to `tests/litesvm.rs`, which does not exist.
- `tests/mock-amm` is built (`target/deploy/mock_amm.so`), but no test in the crate loads it.
- The dev-dependencies (litesvm, solana-*) are compiled and never used.

**Problem**
- `cargo test` runs only the 45 host tests: parser, arithmetic and log codecs. Nothing executes `arbx_exec.so`.
- Not one of the following has an on-chain test:
  - CPI, invoke_unchecked or the system transfer;
  - the account-structure errors;
  - the tip gating;
  - the native legs;
  - the payer guard against a hostile venue;
  - running under mainnet features. That gap is exactly what let #1 through.
- §3.9 requires:
  - "SVM integration tests for each venue, on captured mainnet account snapshots";
  - "Finish the truncated test against a malicious venue";
  - "Regression tests for CU and transaction size".

  None of these exist.
- The v3 cross-language fixture is pinned only in this crate. The engine (`src/build.rs`) has no v3 encoder or decoder yet, so nothing checks that it builds these bytes.

**Proof**
```
ls tests/                     # → mock-amm only
cargo test --release          # → 45 host tests, 0 SVM tests
```
The new harness in `review/tests/adversarial.rs` (15 tests) found #1, #2, #4, #5 and #7 within minutes.

**Fix**
- Promote `review/tests/adversarial.rs` into `tests/litesvm.rs`. It uses LiteSVM mainnet features by default. Once #1 is fixed, change `Env::new()` to `Env::build(false)`.
- Add venue snapshot tests (DLMM, PumpSwap, DAMM v2, CPMM, AMM v4) from accounts fetched with public RPC.
- Add CU budgets as assertions. The table above is a starting baseline.
- Add a 1,232-byte transaction-size test with ALTs for the widest real route.
- Add the ELF syscall audit from #1.
- Add a v3 encoder in `src/build.rs` that asserts `V3_FIXTURE_HEX`.

### 4. MAJOR: CPI_TIP without COUNT_LAMPORTS pays a tip on a losing transaction

**Location:** `src/lib.rs:535-545` (CPI_TIP parsing), `571-575` (COUNT_LAMPORTS is required only for native legs), and `976-977` (the gain and tip calculation).

**Problem**
- The tip is paid in authority **lamports**, but without COUNT_LAMPORTS the guard measures only the wSOL quote: `g = quote_delta`, and `tip = clamp(bps·g)`.
- Any lamports the authority loses *inside* the legs are invisible to both the guard and the tip. Examples:
  - an `init_if_needed` account the venue makes the user pay rent for;
  - a SOL-denominated venue fee;
  - an allowed payer-guard `max_drop`.
- So the plan's invariant "g − tip ≥ min_profit, never pay a tip larger than the gain" does not hold for the wallet.
- With CPI_TIP, min_profit is set to "base fee + margin" only (§3.9), so nothing else absorbs the difference.

**Proof:** `finding_03_cpi_tip_without_count_lamports_pays_a_tip_on_a_losing_transaction`. Leg 1's venue takes 0.1 SOL of lamports from the user.
- The route passes with g = 92,330,399 and tip = 46,165,199 (50%).
- The wallet's net change, excluding the fee, is **−53,834,800 lamports**, and the tip was still paid.
- The same route with COUNT_LAMPORTS reverts with ERR_PROFIT.

**Fix:** have CPI_TIP imply COUNT_LAMPORTS: reject CPI_TIP without COUNT_LAMPORTS with ERR_BAD_DATA. Both already require a wSOL quote (`QuoteNotWsol`), so no valid use is lost.

### 5. Minor: ERR_TIP_FUNDS ignores rent exemption, and AXS1 "result 0" does not mean the transaction landed

**Location:** `src/lib.rs:985` (`tip > lamports_after`) and `986-999`, where AXS1 is logged before the tip CPI.

**Problem**
- A tip that leaves the authority with 0 < lamports < the rent-exempt minimum (890,880 for 0 bytes) passes the program, which logs AXS1 `result=0, tip=…`. The runtime then fails the whole transaction with `InsufficientFundsForRent`.
- The same applies when the tip CPI itself fails, which #2 shows can happen.
- Profit accrues in wSOL while tips and fees come out of native lamports, so the authority's native balance falls steadily and this case will occur in operation.
- The recorder must not treat AXS1.result == 0 as success.

**Proof:** `finding_09_tip_that_breaks_rent_exemption_fails_after_a_passing_summary`. Authority balance 1,000,000 and tip 500,000: the result is `InsufficientFundsForRent { account_index: 1 }` with AXS1 `(result 0, tip 500000)`.

**Fix**
- Require `lamports_after − tip ≥ Rent::minimum_balance(0)`. `sol_get_rent_sysvar` is always registered; a constant with a comment is also acceptable.
- Document that AXS1 is the guard's verdict, not the transaction outcome.
- In the engine, keep a native buffer and unwrap wSOL periodically.

### 6. Minor: one leg may carry both NATIVE_IN and NATIVE_OUT

**Location:** `src/lib.rs:456-464` (`check_native_chain`) and `565-566`. v2 accepts it the same way.

**Problem**
- For such a leg, `before` and `after` are both authority lamports, so `delivered` is the **net** change: the output minus the input it spent.
- The next leg is then patched with only that profit (an under-spend), and AXL1 `delivered` is wrong.
- No venue swaps lamports for lamports, so this combination is always a builder error.

**Proof:** `finding_06_one_leg_with_both_native_flags_is_accepted`. It parses in both layouts.

**Fix:** in v3, reject `LEG_NATIVE_IN | LEG_NATIVE_OUT` on one leg as `BadLegFlags`. Leave v2 byte-identical.

### 7. Minor: the quote account is not tied to the authority

**Location:** `src/lib.rs:863-867`. Only the token-program owner and, for v3, the wSOL mint are checked.

**Problem**
- If the builder passes someone else's wSOL account as the quote, the guard can pass while our wallet loses. Ways this can happen: a wrong ATA derivation, a stale cache, or reusing a counterparty's account from a parsed transaction.
- Example: on a native-in route, the quote gains X and the authority's lamports drop by Y. Then g = X − Y > 0, but X went to a stranger.

**Proof:** `finding_07_quote_account_need_not_belong_to_the_authority`. The route passes, our lamports fall from 100.000 to 98.999995 SOL, and the foreign wSOL account receives 1.0923 SOL.

**Fix:** in v3, require the quote's token-owner field (`data[32..64]`) to equal the authority, failing with ERR_BAD_ACCOUNTS. It is one 32-byte compare at entry. Optionally do the same for every non-native leg's output account.

### 8. Minor: the v2 path parses identically but does not behave identically

**Location:** `src/lib.rs:860-862`, `915-923` and `986-998`; `src/exec.rs:215-221` and `src/send/jito.rs:33` in the engine.

**Problem**
- The parser is proven identical by the property tests against the verbatim copy. Execution differs in these ways:
  - **New checks with new codes:**
    - a last leg that does not deliver into the quote: 0x4E580009 (nexus gave ERR_PROFIT 0x4E580002);
    - a native route with a read-only authority: 0x4E580009 (nexus gave a runtime `PrivilegeEscalation`);
    - a token leg whose output is its input: 0x4E580009.
  - **The order of checks changed.** The NATIVE_OUT slot check now runs before the foreign-signer scan.
  - **An AXS1 record is added** to every v2 route. That is about 130 more log bytes and +241 CU (20,146 against 19,905).
  - **The engine does not know the new codes.** Its error map (`exec.rs:215-221`) has no entry for 0x4E580008-0x4E58000C, and the Jito gate keys only on 0x4E580002.
- All of these are safe, and the engine already enforces last leg == quote (`build.rs:208`). But "the current engine can target this program by switching only the program id" overstates it.

**Proof:** `account_structure_errors_and_v2_differences_from_nexus` runs both binaries side by side.

**Fix**
- State the differences in the module doc.
- Add the new codes to `exec.rs` and to the recorder.
- If strict log parity matters for old analysis tools, skip AXS1 for v2.

### 9. Minor (engine, v2 compatibility): a v2 leg with 64 or more accounts is misread as a native leg

**Location:** `src/build.rs:213`, which checks `l.accounts.len() > 255`.

**Problem**
- In v2 the n_accounts byte carries the NATIVE flags in bits 6-7.
- The builder accepts up to 255 accounts and writes `len as u8`. A leg with 64 or more accounts is therefore re-read on chain as NATIVE_IN or NATIVE_OUT with `len & 0x3F` accounts.

**Proof:** `finding_v2_leg_with_64_accounts_is_misread_on_chain`. Both nexus-arb-v2 and arbx-exec reject it with ERR_BAD_DATA 0x4E580001. It fails safely, but the send is wasted and the cause is misleading.

**Fix:** in the v2 builder, reject any leg with 64 or more accounts (`> 63`), or build such legs as v3.

### 10. Info: allocation and CU notes

**Location and notes**
- **`src/lib.rs:889`, the comment is wrong.** The comment "one CPI instruction is reused, so the bump allocator grows once" does not hold. solana-cpi 3.1.0 `invoke_signed_unchecked` does `StableInstruction::from(instruction.clone())` on **every** CPI, so the heap still grows per leg.
  - Measured: it is harmless. These all succeed at the default 32 KiB heap:
    - 2 legs with 230 accounts in one leg (243 metas);
    - 8 legs × 28 accounts (242 metas).
  - At 266 metas the runtime refuses the instruction (`MaxAccountsExceeded`) before the program runs.
  - Fix the comment. Calling `sol_invoke_signed_rust` with one `StableInstruction` built once would save the clone, but that is optional.
- **`src/lib.rs:1004-1006` is redundant.** The second `check_payer_guard` after the tip provably passes, because the System transfer moves exactly `tip`, and the owner and length cannot change. Drop it, or keep it as an assert and accept the roughly 100 CU.
- **LTO is off.** `crate-type = ["cdylib", "lib"]` disables LTO (cargo-build-sbf warns about it). nexus-arb-v2 has the same setup. Consider a cdylib-only deploy build and measure the difference.
- **The CPI tip costs about 2.2k CU** inside the instruction (24,202 against 22,005). A top-level System transfer costs about 150 CU. The engine should weigh that against the benefit of a conditional tip.

### 11. Info: missing documents and dead constants

**Location:** `src/lib.rs:27`, `172` and `515`, `src/tests.rs:587`, and `Cargo.toml:22`.

**Problem**
- README.md (the v3 byte table), LOGS.md (the AXL1 and AXS1 formats) and `tests/litesvm.rs` are referenced but do not exist.
- `MAX_IX_ACCOUNTS` (`lib.rs:95`) is defined but unused.
- The runtime limit of 255 account metas per instruction applies to the whole instruction: 2 + Σ(2 + nᵢ), plus 2 with CPI_TIP. So "1..=255 per leg" is only an upper bound per leg.

**Fix:** write the two documents, and either use the constant in `parse_v3` (`required_accounts() <= 255`) or delete it.

### 12. Info: the CPI tip is Jito-only

**Location:** `JITO_TIP_ACCOUNTS_B58` and `src/lib.rs:871-881`.

**Note**
- This is intentional and safe: the tip can never go to an arbitrary account.
- But sender paths that need their own tip accounts (`data/sender-tip-accounts.json`: helius_sender and others) cannot use CPI_TIP.
- A rotation of Jito's tip accounts would need a program upgrade.
- Record this as an engine constraint: CPI_TIP is only for Jito bundles and Jito sendTransaction.

### 13. Info: v3 leg attribution and AXS1 coverage

**Problem**
- v3 dropped the NXV2LEG pre-marker. The failing leg is "the number of AXL1 records logged before the failure".
- Logs are capped at 10 KB. DLMM and Anchor event CPIs log heavily, and failed bundles often come back without logs. When the logs are cut, the count is a lower bound, not the answer.
- AXS1 is emitted only at the guard. It is missing on leg errors, venue errors, account-structure errors and parse errors.

**Fix:** the recorder should flag "Log truncated", and fall back to counting `Program <venue> invoke [2]` lines. Document which errors carry AXS1.

### 14. Info (hardening): every venue gets the authority as a writable signer

**Location:** `src/lib.rs:942`. The metas copy `is_writable` from the AccountInfo, and the fee payer is always writable.

**Note**
- Most swap instructions need the user only as a read-only signer: DLMM `swap2`, Whirlpool `swap_v2`, Raydium CLMM, CPMM and DAMM v2.
- A v3 leg flag, for example `LEG_AUTH_RO = 0x04`, could pass the authority as `is_writable=false` for that CPI. That takes lamport theft and `assign` off the table for the leg at the runtime level, whether or not PAYER_GUARD is set.
- The engine must know which venues mark the user `mut`, for example PumpSwap. Test each venue on snapshots (#3).

---

## Verified OK (no finding)

**Parsing**
- The v3 parser has no panics or overflows. It was fuzzed with the crate's 400k mutations and the proptests, and I hand-checked every index: `need()` is called before each read, and amount_offset ≤ 255.
- Encodings are canonical, and the exact length is enforced.
- Reserved flags are rejected.
- The v2 parser is identical to nexus-arb-v2, by the property tests against the verbatim copy.

**Allowlist and keys**
- The allowlist is compared as raw bytes and is identical to nexus-arb-v2 (same 12 programs, same order). An unlisted venue gives ERR_NOT_ALLOWLISTED before any CPI.
- The Jito tip accounts match `data/sender-tip-accounts.json`.

**Tip**
- The tip is paid only after the guard passes.
- It goes only to `JITO[tip_acct_ix]`, which must be writable, through the System program, whose slot is checked by key.
- It is never more than g − min_profit, and a miss pays nothing (the tip account is unchanged).
- A wrong or read-only tip account, or a wrong System slot, gives ERR_TIP_ACCOUNT before any venue runs.
- The tip arithmetic is exact in i128 (proptest model).

**Guards**
- The payer guard catches `assign`, lamport theft and token theft or delegation. A foreign signer is refused in v3 even without PAYER_GUARD.
- A skimming venue gives ERR_PROFIT, and AXS1 reports the negative gain.
- A leg that delivers nothing gives LEG_ERR+i.
- Native routes account correctly in both directions: `gain = quote_delta + lamport_delta`, matching the balances.

**Runtime safety**
- No re-entrancy: arbx-exec is not on its own allowlist, and the runtime forbids A→B→A.
- Privilege escalation is blocked by the runtime (nexus gives `PrivilegeEscalation` on a read-only authority).
- `invoke_unchecked` is sound: no RefCell borrow is held across a CPI.

**Heap**
- Fits within 32 KiB up to the 255-meta instruction limit.

---

## Disposition (2026-10-04)

All four blocker and major findings are fixed, and so are the minor ones (#5-#9). For the info findings: #10, #11 and #14 are done, and #12 and #13 are now documented. Every fix has a regression test that asserts the fixed behaviour. The suites that run the built program use LiteSVM's mainnet feature set and nothing else.

**What changed**
- `src/lib.rs`: md5 `5d2de73e`, was `dcfb1ec2`.
- Built program: `target/deploy/arbx_exec.so`, md5 `ad04d309d16dd9241b63aaf0145fb4b1`, sha256 `d08493e8…609532e`, 48,744 bytes, SBPF v3. A clean rebuild in a separate target directory gives the same md5.
- New files:
  - `tests/common/mod.rs`, `tests/litesvm.rs`, `tests/venues.rs`;
  - `tests/fixtures/` (venue snapshots, venue ELFs with a MANIFEST, golden vectors, `fetch_venues.py`);
  - `README.md`, `LOGS.md`, `ci.sh`;
  - `proptest-regressions/tests.txt`.
- Engine:
  - `src/build.rs`: the v2 leg limit and a v3 encoder with tests;
  - `src/exec.rs`: the error map and a test.
- `review/` is marked superseded, see below.
- Untouched: nexus-arb-v2 (still md5 809315be) and the mock AMM.

| # | Sev | Disposition | Regression tests |
|---|---|---|---|
| 1 | Blocker | **Fixed.** The syscall is gone, and AXS1 `cu_remaining` is now a reserved field that is always 0 (LOGS.md). The ELF audit compares every static syscall in the built ELF against agave's own registry (solana-syscalls 4.3) twice: under mainnet features, and with every known feature active. The ELF calls 8 syscalls: abort, sol_get_rent_sysvar, sol_invoke_signed_rust, sol_log_, sol_log_data, sol_memcmp_, sol_memcpy_, sol_panic_. Every SVM test builds its VM with `LiteSVM::new()` (mainnet features) and asserts that 5TuppMut… is still inactive. | `review_01_elf_uses_only_syscalls_mainnet_registers`, `review_01_every_route_completes_under_mainnet_features` (v2, v2 with guard, v3 PG, PG\|CL, PG\|CL\|TIP), plus every other SVM test |
| 2 | Major | **Fixed.** PAYER_GUARD is mandatory in v3: without it the parser returns PayerGuardRequired → ERR_BAD_DATA, and no venue runs. v2 is unchanged. | host `review_02_v3_payer_guard_is_mandatory`. SVM: `review_02_v3_without_payer_guard_is_refused_before_any_venue_runs`, `review_02_hostile_venue_reverts_on_every_v3_flag_combination` (assign → ERR_PAYER_GUARD with the wallet still System-owned; a 0.5 SOL theft → ERR_PAYER_GUARD with the attacker unpaid; a token drain → ERR_TOKEN_GUARD; each under PG, PG\|CL and PG\|CL\|TIP), `review_02_payer_guard_max_drop_is_exact` |
| 3 | Major | **Fixed.** `review/tests/adversarial.rs` is promoted to `tests/litesvm.rs` (20 tests), and every `finding_*` proof became a test of the fix. New `tests/venues.rs` (4 tests) runs the mainnet ELFs of DLMM, PumpSwap and its fee program, DAMM v2, CPMM and AMM v4, on account snapshots from slot 453,214,843 fetched by public read-only RPC. Its legs are ports of the engine's `build.rs` builders, account for account. Also added: CU budgets as assertions, transaction-size tests with lookup tables, the ELF audit, golden vectors shared with the engine, a v3 encoder in the engine, and `ci.sh` (build, then the md5 check of the nexus reference, then all tests). | the suites themselves; engine `v3_route_matches_the_shared_golden_vectors`, `v3_route_refuses_what_the_program_refuses`, `v3_jito_tip_accounts_are_the_programs` |
| 4 | Major | **Fixed.** CPI_TIP without COUNT_LAMPORTS gives TipNeedsCountLamports → ERR_BAD_DATA. | host `review_04_cpi_tip_requires_count_lamports`. SVM `review_04_cpi_tip_without_count_lamports_is_refused`: the reviewer's losing route is refused before any venue runs. With COUNT_LAMPORTS it gives ERR_PROFIT, AXS1 shows lamport_delta −0.1 SOL, and no tip is paid. |
| 5 | Minor | **Fixed.** The authority must keep at least its rent-exempt minimum after the tip, otherwise ERR_TIP_FUNDS, which is also written in AXS1. The minimum comes from `sol_get_rent_sysvar`, which is always registered (`Rent::get()` would use the feature-gated `sol_get_sysvar`). The arithmetic is integer-only: it is exact for both mainnet Rent representations (3480 × 2.0 and 6960 × 1.0), rounds a threshold below 2.0 up to 2.0, and fails closed above 2.0. It costs about 100 CU, only when a tip is due. LOGS.md documents that AXS1 is the guard's verdict, not the transaction's outcome. | host `review_05_tip_must_leave_the_authority_rent_exempt`, `review_05_rent_exempt_minimum_matches_both_rent_representations`. SVM `review_05_tip_that_would_break_rent_exemption_is_err_tip_funds`: 1,000,000 / 500,000 now gives ERR_TIP_FUNDS instead of InsufficientFundsForRent. A tip that leaves exactly 890,880 passes, and one lamport more fails. |
| 6 | Minor | **Fixed** in v3: a leg with both NATIVE flags → BadLegFlags. v2 still parses it, byte-identical to nexus-arb-v2. | host `review_06_v3_leg_cannot_be_both_native_in_and_out`; SVM `review_06_one_leg_with_both_native_flags_is_refused_on_chain` |
| 7 | Minor | **Fixed** in v3, for the quote and also for every token output (the optional part): the token-owner field must be the authority, otherwise ERR_BAD_ACCOUNTS before any venue runs. This costs about 40 CU per checked account (+127 CU on a 2-leg route). v2 is unchanged, and a test pins that, as a documented compatibility trade-off. | host `review_07_token_owner_field_must_be_the_authority`; SVM `review_07_quote_and_token_outputs_must_belong_to_the_authority` (foreign quote, foreign intermediate output, v2 parity) |
| 8 | Minor | **Fixed.** The differences are listed in the module doc and in README.md. The engine's `exec::meaning` now names 0x4E580008-0C. AXS1 stays on v2 routes, because it is the measurement record (+232 CU). The recorder (WP-08 proglog) and the Jito gate are WP-15's: only ERR_PROFIT means "the encoding is right", which stays correct. | SVM `review_08_v2_account_structure_differences_from_nexus_are_the_documented_ones` (also pins the log difference: 4 records on nexus, 5 on arbx-exec with one AXS1); engine `meaning_knows_the_arbx_exec_codes` |
| 9 | Minor (engine) | **Fixed.** `route_ix` refuses a leg with more than 63 accounts (`V2_MAX_LEG_ACCOUNTS`), and the error says to use v3. | engine `v2_refuses_a_leg_of_64_accounts`; SVM `review_09_v2_leg_with_64_accounts_is_misread_by_both_binaries` (the same leg runs in v3) |
| 10 | Info | **Done.** The comment is corrected (the heap grows per CPI, which is harmless), the redundant post-tip check is removed (it holds by construction; see the guard comment), and LTO was **measured** (see below). LTO is not adopted, because it needs a crate split. | `cpi_tip_is_paid_exactly_and_only_when_the_guard_passes` asserts that the wallet moves by exactly −tip − fee; `wide_legs_and_long_routes_fit_the_heap_up_to_the_runtime_account_limit` |
| 11 | Info | **Done.** README.md (byte tables, accounts, guard, codes) and LOGS.md are written. The v3 parser enforces `MAX_IX_ACCOUNTS` with TooManyAccounts → ERR_BAD_DATA. Measured: 255 metas run at the default heap, and 256 give MaxAccountsExceeded before the program runs. | host `review_11_v3_route_must_fit_255_accounts`; SVM `wide_legs_and_long_routes_fit_the_heap_up_to_the_runtime_account_limit` |
| 12 | Info | **Documented** as an engine constraint in README.md: CPI_TIP pays only the 8 Jito tip accounts, so it is for Jito bundles and Jito sendTransaction only. The engine's encoder takes the list from the program source. | `cpi_tip_account_and_system_slot_are_validated`, engine `v3_jito_tip_accounts_are_the_programs` |
| 13 | Info | **Documented** in LOGS.md: which errors carry AXS1, leg attribution from the AXL1 count, the "Log truncated" fallback to depth-2 `invoke [2]` lines, and logs missing from failed bundles. Recorder work belongs to WP-08 and WP-15. | `v3_foreign_signer_skim_unlisted_venue_and_empty_leg` asserts that one AXL1 precedes a leg-1 failure |
| 14 | Info | **Implemented.** New v3 leg flag `LEG_AUTH_RO` (0x04): the CPI passes the authority read-only, so the runtime itself refuses any debit or `assign` of the wallet in that leg. It is rejected on native legs and costs +68 CU on a 2-leg route. On the mainnet snapshots, DLMM, CPMM, DAMM v2 and AMM v4 accept it, and PumpSwap does not (PrivilegeEscalation). | host `review_14_leg_auth_ro_flag`; SVM `review_14_auth_ro_leg_cannot_debit_or_assign_the_wallet`; venues `which_venues_accept_a_read_only_authority` |

**A bug in a test, fixed along the way.** `prop_v2_valid_and_mutated_match_nexus_arb_v2` could randomly flip the version byte to 3, and then compared a v3 parse with nexus's BadVersion(3). It was rare and latent, and showed up once. Inputs tagged v3 are now checked against nexus's BadVersion only. The case is saved in `proptest-regressions/`, and 200 further runs of the host suite (4,000 cases per property) all passed.

### Test results (final run, `./ci.sh`)

| Suite | Result |
|---|---|
| arbx-exec host (`src/tests.rs`) | 54 passed (was 45: 8 regression tests and 1 golden-vector test added; existing tests updated for mandatory PAYER_GUARD) |
| arbx-exec `tests/litesvm.rs` (mainnet features) | 20 passed |
| arbx-exec `tests/venues.rs` (mainnet venue ELFs on snapshots) | 4 passed |
| arbx engine `cargo test --release` | 61 passed (was 55). `cargo build --release` has the same 24 warnings as the baseline and no new ones. |
| nexus-arb-v2 `cargo test` | 20 passed (unchanged; `.so` md5 809315be) |
| `review/` harness against the fixed build | 11 failed, 4 passed. This is expected. Every finding proof fails (finding_00, 01, 03, 06, 07, 09), and the other failures are bare-v3 or tip-without-COUNT_LAMPORTS routes now refused with 0x4E580001, or the foreign quote refused with 0x4E580009. `finding_v2_leg_with_64_accounts` still passes, because #9 is fixed in the engine and the on-chain behaviour is unchanged by design. The harness is marked SUPERSEDED. |

### CU after the fixes (mock 2-leg round trip, mainnet features, same pools as the table above)

| Program / layout | Before (remaining-CU feature forced on) | After (mainnet features) | Budget asserted |
|---|---|---|---|
| nexus-arb-v2 .so, v2 | 19,905 | 19,905 | 20,500 |
| arbx-exec, v2 | 20,146 | 20,137 | 20,700 |
| nexus-arb-v2 .so, v2 + guard | 22,216 | 22,216 | 22,900 |
| arbx-exec, v2 + guard | 22,384 | 22,386 | 23,100 |
| arbx-exec, v3 bare | 19,945 | refused, ERR_BAD_DATA (~3.2k CU, no venue runs) | — |
| arbx-exec, v3 PG | 22,014 | 22,141 (+127: quote and output owner checks) | 22,900 |
| arbx-exec, v3 PG \| CL | 22,005 | 22,145 | 22,900 |
| arbx-exec, v3 PG \| CL \| TIP | 24,202 | 24,551 (owner checks and the Rent sysvar read; the redundant check is gone) | 25,400 |
| arbx-exec, v3 PG, both legs AUTH_RO | — | 22,209 | 22,900 |
| v3 native in / native out | 21,408 / 18,821 | 21,539 / 18,943 | 22,400 / 19,900 |

Before the fix, every row above failed on mainnet (#1).

**Real venues** (`tests/venues.rs`). Each run is wSOL → X → wSOL on one pool through v3 PG\|CL. It runs both legs and must end in ERR_PROFIT, with leg 1 spending exactly what leg 0 delivered. The payer is a fixed test key, because PumpSwap's PDA bump search makes CU depend on it.

| Snapshot | Venue CU per leg | Route CU | arbx-exec's own CU (budget) | Round-trip loss |
|---|---|---|---|---|
| DLMM SOL/USDC | 33,664 / 33,743 | 82,026 | 14,619 (15,400) | 3 bps |
| Raydium AMM v4 SOL/USDC | 15,391 / 15,404 | 41,348 | 10,553 (11,100) | 49 bps |
| Meteora DAMM v2 SOL/USDC | 13,505 / 14,142 | 40,064 | 12,417 (13,100) | 7 bps |
| Raydium CPMM SOL/token | 24,474 / 24,350 | 61,239 | 12,415 (13,100) | 48 bps |
| PumpSwap SOL/USDC | 77,078 / 65,156 | 160,099 | 17,865 (18,800) | 59 bps |
| PumpSwap canonical pump token | 89,611 / 77,486 | 185,332 | 18,235 (19,200) | 59 bps |

- **A passing route on real programs.** wSOL → USDC on DLMM, then USDC → wSOL on AMM v4, with a 2% gap put into the AMM v4 snapshot:
  - gain 18,153,590, tip 5,446,077 (30%), 70,147 CU;
  - the wallet's real balances match AXS1;
  - the Jito account receives exactly the tip;
  - with min_profit one lamport above gain − tip, the route reverts with nothing moved except the fee.
- **The first PumpSwap buy** charges the payer 1,844,400 lamports of rent for its user volume accumulator. With the mandatory guard, the engine must either cover that rent with `max_drop` or create the account beforehand (WP-06 already checks for this account).
- **Transaction size** (v0 transactions with 2 lookup tables):
  - the widest real route (PumpSwap buy and sell on a canonical pool, CPI tip, compute-budget instructions, 58 metas): 486 bytes;
  - a mock route with 26- and 21-account legs: 520 bytes with the tables, 1,878 without them.
- **LTO (#10).** A cdylib-only build with `lto = "fat"`: the same tests pass, and the binary is 48,360 bytes. It saves:
  - 972 CU on v3 PG (22,141 → 21,169);
  - 897 CU on arbx v2 (20,137 → 19,240, below nexus);
  - 1,351 to 1,788 CU of arbx-exec's own cost on the real venues.

  Adopting it needs `crate-type = ["cdylib"]`, which means splitting `logic` into an `arbx-exec-logic` crate. WP-15 already anticipates that split for the engine's dependency, so it is left to WP-15. `ARBX_EXEC_SO=<path> cargo test --release` runs every suite against such a build.

### Still open (owner or later work packages)

- **WP-15:**
  - wire `build::route_ix_v3` into `Exec::build` (it is tested but not called; the flag defaults to nexus-v2);
  - decode AXL1 and AXS1 in proglog;
  - the crate split for LTO.
- **Deployment:** the owner's action. Run `./ci.sh` and check the buffer's hash against md5 `ad04d309` / sha256 `d08493e8…`.
- **Engine policies:**
  - set LEG_AUTH_RO only on the four venues measured above;
  - use CPI_TIP only on Jito paths;
  - keep the authority's native balance above rent exemption plus tips.
- **Snapshot coverage:** the snapshots age. Refresh them with `tests/fixtures/fetch_venues.py`. Orca Whirlpool and the CLMM family have no snapshot yet, because the engine has no builder for them. The harness does not build Token-2022 user accounts.
