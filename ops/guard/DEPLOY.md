# snipe-guard: deploy, verify, smoke, allowlist, rollback (dip43)

PRIVATE. The program source is `program/snipe-guard/`, the tool is `sg_ops` (`src/bin/sg_ops.rs`, wrapper `ops/guard/sg-ops.sh`),
the private error-code table is `ops/guard/codes.md`, the engine flags are `ops/guard/r76_guard_flags.md`.

## What gets deployed

| Item | Value |
|---|---|
| File | `program/snipe-guard/release/snipe_guard.so` (committed; built by `program/snipe-guard/build_sbf.sh`) |
| sha256 | `eb08c504a51b865f8590fa4aaf097ce8be01d496105f0f3b74134866913e4266` |
| Size | 15,776 bytes, SBPF v3 (the SBPF v3 feature `5cC3foj7…` is active on mainnet; `sg_ops deploy` re-checks it on the target cluster) |
| Toolchain | agave release v4.4.0 tarball (sha256 `3363f472…c574`, cargo-build-sbf 4.5.0), platform-tools v1.57 (Rust 1.95.0), `--arch v3`, `--locked`. Rebuilding on the same toolchain gives the same sha256 (checked from two directories) |
| SOL locked | about **0.112 SOL** (programdata 0.1110 + program account 0.0011; `sg_ops info --cluster mainnet` prints the exact figure). The deploy also needs a temporary buffer of the same size (refunded at the end) and ~0.0002 SOL of fees: have **≥ 0.25 SOL** on the payer |
| Allowlist PDA (optional) | 546 bytes, +0.0047 SOL rent, only if you init it |

The program: one assert-only instruction placed at index 2 of a pre-send try (where Lighthouse is today). It checks, in this order:
AUTH (account 0 signs and is AMS / FRA / FRZ, compiled in; or is listed in the allowlist PDA, passed last), then the slot deadline,
the optional curve band, the optional holder floors. Any failure fails the whole try (pump never runs, the tip reverts, the base +
priority fee is paid, as a 6042 today).

## Build report (11-10)

| Check | Result |
|---|---|
| Host tests (`cargo test` in program/snipe-guard) | 10/10 (AUTH first, every check + code, allowlist ops, code scramble round trip over all 32,768 packed reasons: never 0, distinct, < 8 below 0x10000, golden bytes, 300k-mutation fuzz) |
| LiteSVM, mainnet features (program/snipe-guard-svm on the BUILT .so) | 6/6: compiled wallets pass; other signer / wallet not signing / no accounts / fake list refused at AUTH; allowlist INIT (not-authority, fake programdata, wrong bump refused; pre-funded PDA OK; twice refused), ADD / REMOVE / ROTATE, non-admin refused, look-alikes (other owner, other address, short) refused; every check's code decoded; echo; CU table; syscall audit; strings scan |
| CU (pass path, compiled wallet) | deadline 330 · +curve 454 · 4 floors 1,097 · 6 floors 1,445 · 8 floors 1,793 · curve + 12 floors 2,613 · listed wallet via the PDA +1,647 · AUTH refusal 140 |
| Syscalls in the ELF | sol_get_clock_sysvar, sol_set_return_data, sol_create_program_address, sol_try_find_program_address, sol_invoke_signed_c, sol_memcpy_, sol_memset_: all registered under mainnet features |
| Strings scan (`strings -n 4`) | only `.text`, `.shstrtab`, `.rodata` and three random 4-byte runs of key/constant bytes (`%9I]`, `+]2$`, `8JPH`); no word from the list guard/holder/floor/slot/deadline/curve/abort/allow/admin/auth/snipe/pump/error/fail/panic/token/wallet/signer/list/assert/check/band/src/.rs; no symbol table (`llvm-readelf -s`: none) |

## Trust: what the program can and cannot do

- **No funds, no CPI on the try path.** The assert instruction gets only read-only accounts plus our wallet as a read-only signer. A
  program can pass on only the privileges it was given, and it makes no call, so even a hostile upgrade could only make our tries
  always fail (no fills) or always pass (= today without a deadline). It cannot move SOL or tokens.
- The one CPI in the program is the system-program create of the allowlist PDA in `INIT` (an admin transaction signed by the upgrade
  authority; never in a try).
- **Only we can use it.** Every instruction fails with an opaque code unless signed by one of our wallets (compiled in) or a wallet the
  allowlist admin added. An outsider can call it, but the only effect is that **his own** transaction fails: no state of ours changes.
- **Discreet, not secret.** No text on chain (no logs, no panic messages, no names; checked by the strings scan in the build and the
  SVM tests: only section names remain), opaque scrambled error codes, compact binary data. The bytecode is public and can be
  disassembled: this makes the purpose costly to read, not impossible.

## Authority policy

- **Program keypair**: generate it offline (`solana-keygen new -o snipe-guard-program.json`, a vanity grind is fine). It is needed
  only for the first deploy; keep it with the cold key afterwards.
- **Upgrade authority = a COLD keypair the owner holds** (not the trading wallet, not on any server). `sg_ops deploy` deploys with the
  payer as a *temporary* authority and hands the authority to the cold **pubkey** right after (no cold signature needed for that).
- The cold key is needed only to upgrade (a new build), to init the allowlist PDA, or to close the program. Keep it upgradeable while
  the checks still change; set it final later (`solana program set-upgrade-authority <ID> --final`) only by the owner's choice.
- **Allowlist admin**: a separate key (can be the cold key). Adds / removes wallets and can rotate itself.
- The payer: any funded wallet the owner chooses (NOT a trading keystore: `sg_ops` refuses `.enc` / keystore paths; it reads only
  solana-keygen JSON files named on its command line).

## Steps for the owner (mainnet, before r76)

All commands from `~/sniper` on the build host (the tool needs only an RPC URL; no server is touched).

```bash
cargo build --release --bin sg_ops
G=ops/guard/sg-ops.sh            # = target/release/sg_ops

# 0. the build you deploy is the tested one
sha256sum program/snipe-guard/release/snipe_guard.so    # eb08c504a51b865f…3e4266
bash program/snipe-guard/test_svm.sh                    # optional: 10 host + 6 LiteSVM tests on this .so

# 1. keys (offline): program id, cold upgrade authority; a payer with >= 0.25 SOL
solana-keygen new -o ~/guard-keys/snipe-guard-program.json
solana-keygen new -o ~/guard-keys/snipe-guard-cold.json      # keep offline; only its PUBKEY is used below
$G info --cluster mainnet                                      # SOL locked

# 2. the plan (dry: prints everything, sends nothing)
$G deploy --cluster mainnet --payer ~/guard-keys/payer.json --program-keypair ~/guard-keys/snipe-guard-program.json \
          --upgrade-authority <COLD_PUBKEY>
# 3. deploy for real (+ --init-allowlist-admin <ADMIN_PUBKEY> to create the allowlist now; not needed for AMS/FRA/FRZ)
$G deploy ... --yes        # runs `solana program deploy`, hands the authority to COLD, then VERIFY
# 4. verify (anyone can re-run it any time)
$G verify --cluster mainnet --program-id <PROGRAM_ID> --expect-authority <COLD_PUBKEY>
# 5. smoke: simulations only (no key, nothing sent): one passing guarded try and four aborts, each code decoded
$G smoke --cluster mainnet --program-id <PROGRAM_ID>          # wallet AMS by default; --wallet <FRA/FRZ> for the others
```

Then the engine flags (`ops/guard/r76_guard_flags.md`): `--presend-live-guard deadline|holders --presend-live-guard-program <PROGRAM_ID>`.
The engine itself re-checks at start (fail closed): the program account is executable, a deadline 50 slots ahead passes and one 50
behind fails at the guard with the decoded deadline code (holders mode: two empty floors fail with the floors code). The line
`GUARD verified on chain (simulated): …` is in the start log.

Use a paid RPC URL for `--cluster` if the public one is slow (`--cluster https://…`). A failed `solana program deploy` leaves a
buffer account holding the SOL: `solana program show --buffers --keypair payer.json` and `solana program close <BUFFER>` refund it.

### Program id from an engine-format keystore (11-10: the vanity id CYBERjpcr…TudiZ)

The program keypair can stay in our encrypted keystore format (`.enc`). `sg_ops deploy` unlocks it only for the deploy call:
`--program-keystore FILE.enc --program-id-expect <PUBKEY>` replaces `--program-keypair`.
- The dry plan (no `--yes`) never opens the keystore; it shows the expected id.
- With `--yes` it asks the passphrase on the terminal (hidden), checks the key unlocks to `--program-id-expect` and is not one of our
  trading wallets, writes the keypair to a fresh owner-only folder in RAM (`/dev/shm`), runs `solana program deploy`, then overwrites
  the file with zeros and removes it (also on any error). Test: `cargo test --release --bin sg_ops` (round trip with a throwaway key).

```bash
$G deploy --cluster mainnet --payer ~/guard-keys/payer.json \
  --program-keystore /home/it/sniper-keys/cyber-program.enc --program-id-expect CYBERjpcrxMLkZyuvP3D3aEKpvuTKHiwwU8cvT5TudiZ \
  --upgrade-authority <COLD_PUBKEY>          # dry plan; then the same + --yes (asks the passphrase)
```
Mainnet cost measured 11-10 by the dry plan: 0.0819 SOL stays locked (programdata 0.0810 + program 0.0008); the payer needs >= 0.173 SOL
(a buffer of ~0.081 is refunded after the deploy).

## Verify: the on-chain bytes are the build

`sg_ops verify` reads the program account → its programdata address → the programdata account, and checks:
`programdata[45 .. 45+len(.so)] == snipe_guard.so` byte for byte and every byte after it is zero; prints both sha256, the deployed
slot and the upgrade authority (`--expect-authority` makes a mismatch an error). `solana program dump <ID> out.so` gives the same
bytes plus zero padding (compare `cmp -n 15776 out.so program/snipe-guard/release/snipe_guard.so`).

## Allowlist: adding a wallet later

The three trading wallets are compiled in (zero cost per try). Another wallet: either a program upgrade (add it to `logic::COMPILED`,
rebuild, `solana program deploy --program-id <ID> --upgrade-authority cold.json …`), or the allowlist PDA (no upgrade):

```bash
$G allow-init   --cluster mainnet --program-id <ID> --payer payer.json --authority cold.json --admin <ADMIN_PUBKEY> --yes   # once
$G allow-add    --cluster mainnet --program-id <ID> --admin admin.json --wallet <NEW_WALLET> --yes
$G allow-list   --cluster mainnet --program-id <ID>                     # prints the PDA, the admin and the wallets
$G allow-remove --cluster mainnet --program-id <ID> --admin admin.json --wallet <WALLET> --yes
$G allow-admin  --cluster mainnet --program-id <ID> --admin admin.json --new-admin <PUBKEY> --yes
```

The engine on that wallet needs `--presend-live-guard-allowlist <PDA>` (printed by `allow-list`); it then carries the PDA as one extra
account (+32 bytes, +~1,650 CU for the PDA check). Up to 16 extra wallets. The PDA is checked by owner, size and address (seeds +
stored bump): a look-alike account is refused (LiteSVM tests).

## Rollback

- **Instant**: restart the engine with `--presend-live-guard off` (the default). Every try is then dip42's (Lighthouse deadline), byte
  for byte. Nothing on chain needs to change.
- The program can stay deployed unused. To get the ~0.112 SOL back: `solana program close <ID> --authority cold.json --recipient <WALLET>`
  (irreversible: the id can never be reused).
- A bad upgrade: deploy the previous `.so` (git history of `program/snipe-guard/release/`) with the cold authority, `verify`, `smoke`.

## Rehearsal (11-10, Builder C)

The public devnet faucet was closed (`requestAirdrop`: "The RPC faucet is closed on this cluster"; `solana airdrop`: rate limited), so
the full flow was rehearsed on a local `solana-test-validator` (agave 4.4.0, SBPF v3 active) with throwaway keys
(`~/sniper-data/plan1110/builder_c/`): deploy → hand-over to the cold key → verify → smoke → allowlist init / add / list / remove.
Script `ops/guard/rehearse_localnet.sh`, transcript `ops/guard/rehearsal_localnet.txt` (REHEARSAL PASS). A devnet run needs only a funded devnet payer: the same commands with `--cluster devnet`.

## MAINNET DEPLOYMENT (11-10 ~20:05 PKT)
- Program id **CYBERjpcrxMLkZyuvP3D3aEKpvuTKHiwwU8cvT5TudiZ** (owner's vanity key); programdata ABmSK92cvRyZf69FJGRFssGNqiRzJTLbGfwyB46y78D9,
  deployed slot 467762257, tx 5s9SD7PW9kLxqHVjYTtW6P4a5tobD7edALZDSgNZ4E4edJKZTM3W6MhpR5HoJtZED4R9Na5xF3jFZpuecp5wFfe4.
- .so sha256 eb08c504a51b865f8590fa4aaf097ce8be01d496105f0f3b74134866913e4266 (15,776 bytes): VERIFY PASS (on-chain bytes = build).
- Upgrade authority **7RbmHNNHMvByKUyzJAy8xSpo4Getk7iUDm4RW7H6Ln9T** (= the payer; owner's choice; the owner removes the key files from rewind after
  the deploy, so it is cold from then on). Payer balance after: 0.118 SOL (0.0810 locked in programdata + 0.0008 program account; no buffer left).
- SMOKE PASS (simulation) for AMS EgxfYgEb…, FRA 2g7rYv7y…, FRZ FRZh63L6…: pass ~850 CU; deadline / floors / other signer / not signing abort
  with their opaque codes, decoded.
- Engine flag: `--presend-live-guard-program CYBERjpcrxMLkZyuvP3D3aEKpvuTKHiwwU8cvT5TudiZ`.
