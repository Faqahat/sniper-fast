# snipe-guard error codes (PRIVATE: never publish; the chain shows only the numbers)

A failed guard returns `ProgramError::Custom(code)`. `code = ((raw ^ K1) * M + K2) mod 2^32` with the private constants in
`program/snipe-guard/src/lib.rs` (`logic::K1 / M / K2`, M odd = invertible), where `raw` packs 16 bits:

| bits | field | meaning |
|---|---|---|
| 0-3 | kind | 1 auth, 2 data, 3 accounts, 4 deadline, 5 curve_high, 6 curve_deep, 7 floors, 8 admin |
| 4-7 | idx | auth/data/accounts/admin: the sub-reason below; floors: the index (in the try's `guard.floors`) of the holder furthest below its floor |
| 8-11 | cnt | floors: how many holders were below (capped 15) |
| 12-15 | gap | how far: deadline = slots late (1: 1, 2: 2, 3: 3-4, 4: 5-8, 5: 9-16, 6: 17-64, 7: >64); curve = beyond the band edge (1: <0.5%, 2: 0.5-1%, 3: 1-2%, 4: 2-5%, 5: 5-10%, 6: 10-20%, 7: >=20%); floors = what the worst holder still holds of its floor (0: nothing, sold out / closed, 1: <25%, 2: 25-50%, 3: 50-75%, 4: 75-90%, 5: 90-100%) |

Decoders: `snipe_guard::client::decode` (engine: `guard_abort {kind, idx, cnt, gap_bucket, gap, sub, code}` on presend_attempt_land),
`ops/guard/sg-ops.sh decode 0x…` (one code), `ops/guard/sg-ops.sh codes` (this table). Codes that do not decode (e.g. pump's 6042 =
0x179a, Lighthouse's 0x1771) are not ours: logged raw. Check order in the program: auth (before anything), then data parsing / deadline /
curve / floors in that order, then the account count; the first failure is returned.

On success with the echo flag (0x80; smoke test only) the program sets 3 bytes of return data: [flags & 0x07, n_floors | violators << 4,
tightest margin bucket of the holders at or above their floor (1: <110%, 2: <125%, 3: <150%, 4: <200%, 5: more; 0: none)]. In a real try
the later Token-2022 ATA create overwrites the return data, so the engine does not request it.

## Instruction layout (private)

`[op 0x54, flags, (deadline u64 LE)?, (lo u64, hi u64)?, (n u8, max_viol u8, n x floor u32 whole tokens)?]`; flags 0x01 deadline,
0x02 curve, 0x04 floors, 0x80 echo. Accounts: wallet (signer), curve token account?, n floor token accounts (holders' Token-2022 ATAs),
allowlist PDA (last, only for a wallet not compiled in). Admin ops: 0x6a INIT `[op, bump, admin 32, lamports u64]` (payer s/w, list w,
upgrade authority s, programdata, system program); 0x37 ADD / 0x60 REMOVE / 0x3a ADMIN `[op, key 32]` (admin s, list w). Allowlist PDA
= create_program_address([seed ce b5 c3 bb 6e 5a 49 90, [bump]], program); data = admin 32 | bump | n | 16 x key 32.

## Table (generated: `sg-ops.sh codes`)

| kind | idx | meaning | example code (cnt 0, gap 0) |
|---|---|---|---|
| auth (1) | 1 | no_accounts | 0xfa3138eb |
| auth (1) | 2 | not_signer | 0x3b1027bb |
| auth (1) | 3 | not_ours_no_list | 0x7bef168b |
| auth (1) | 4 | list_owner | 0xb5d68edb |
| auth (1) | 5 | list_len | 0xf6b57dab |
| auth (1) | 6 | list_addr | 0x37946c7b |
| auth (1) | 7 | not_listed | 0x78735b4b |
| data (2) | 1 | op | 0x662349fe |
| data (2) | 2 | flags | 0xa70238ce |
| data (2) | 3 | short | 0xe7e1279e |
| data (2) | 4 | n | 0x21c89fee |
| data (2) | 5 | band | 0x62a78ebe |
| data (2) | 6 | trailing | 0xa3867d8e |
| data (2) | 7 | max_viol | 0xe4656c5e |
| accounts (3) | 1 | count | 0xd2155b11 |
| accounts (3) | 2 | too_many | 0x12f449e1 |
| accounts (3) | 3 | clock | 0x53d338b1 |
| accounts (3) | 4 | dup | 0x8dbab101 |
| deadline (4) | 0 | gap 1: 1 slot | 0x1e39ad54 |
| deadline (4) | 0 | gap 2: 2 slots | 0x3f4add54 |
| deadline (4) | 0 | gap 3: 3-4 slots | 0x605c0d54 |
| deadline (4) | 0 | gap 4: 5-8 slots | 0x816d3d54 |
| deadline (4) | 0 | gap 5: 9-16 slots | 0xa27e6d54 |
| deadline (4) | 0 | gap 6: 17-64 slots | 0xc38f9d54 |
| deadline (4) | 0 | gap 7: >64 slots | 0xe4a0cd54 |
| curve_high (5) | 0 | gap 1: <0.5% | 0x8a2bbe67 |
| curve_high (5) | 0 | gap 2: 0.5-1% | 0xab3cee67 |
| curve_high (5) | 0 | gap 3: 1-2% | 0xcc4e1e67 |
| curve_high (5) | 0 | gap 4: 2-5% | 0xed5f4e67 |
| curve_high (5) | 0 | gap 5: 5-10% | 0x0e707e67 |
| curve_high (5) | 0 | gap 6: 10-20% | 0x2f81ae67 |
| curve_high (5) | 0 | gap 7: >=20% | 0x5092de67 |
| curve_deep (6) | 0 | gap 1: <0.5% | 0xf61dcf7a |
| curve_deep (6) | 0 | gap 2: 0.5-1% | 0x172eff7a |
| curve_deep (6) | 0 | gap 3: 1-2% | 0x38402f7a |
| curve_deep (6) | 0 | gap 4: 2-5% | 0x59515f7a |
| curve_deep (6) | 0 | gap 5: 5-10% | 0x7a628f7a |
| curve_deep (6) | 0 | gap 6: 10-20% | 0x9b73bf7a |
| curve_deep (6) | 0 | gap 7: >=20% | 0xbc84ef7a |
| floors (7) | holder # | gap 0: 0% held (sold out / closed) | 0x5cdc8a8d |
| floors (7) | holder # | gap 1: <25% of floor | 0x7dedba8d |
| floors (7) | holder # | gap 2: 25-50% | 0x9efeea8d |
| floors (7) | holder # | gap 3: 50-75% | 0xc0101a8d |
| floors (7) | holder # | gap 4: 75-90% | 0xe1214a8d |
| floors (7) | holder # | gap 5: 90-100% | 0x02327a8d |
| admin (8) | 1 | count | 0xedcfb070 |
| admin (8) | 2 | signer | 0x2eae9f40 |
| admin (8) | 3 | programdata | 0x6f8d8e10 |
| admin (8) | 4 | not_authority | 0xa9750660 |
| admin (8) | 5 | list_addr | 0xea53f530 |
| admin (8) | 6 | list_state | 0x2b32e400 |
| admin (8) | 7 | not_admin | 0x6c11d2d0 |
| admin (8) | 8 | full | 0xa5f94b20 |
| admin (8) | 9 | present | 0xe6d839f0 |
| admin (8) | 10 | absent | 0x27b728c0 |
| admin (8) | 11 | zero_key | 0x68961790 |
| admin (8) | 12 | cpi | 0xa27d8fe0 |
| admin (8) | 13 | data | 0xe35c7eb0 |
| admin (8) | 14 | system | 0x243b6d80 |
