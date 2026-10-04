# Program fixtures

Fetched once, read-only, from the public RPC `https://api.mainnet-beta.solana.com` on 2026-10-04 (`getAccountInfo`,
base64), for the WP-01 provenance test (`provenance::tests::programdata_elf_hash_of_the_deployed_route_program`).

| File | Account | Slot | What |
|---|---|---|---|
| `8K8uyQDt-program.json` | `8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg` | 453232936 | the nexus-arb-v2 route program account (BPF upgradeable loader, state 2): points to its programdata |
| `8K8uyQDt-programdata.json` | `5V3ssdCfTyENu2YGzXdWo9RQP2se8KrqmLRHsLVrvGji` | 453232969 | its programdata account: 43,485 bytes = 45-byte header + ELF + zero padding |

Programdata: state 3, last deploy slot 451,798,124, an upgrade authority is set. The ELF ends at byte 35,240 (its section
header table: `e_shoff` 34,984 + 4 × 64); the 8,200 bytes after it are zero. Over bytes `[45, 45 + 35,240)`:

- md5 `809315befcb9554211f8019bf9df290b` (the reproducible build's md5, as PLAN WP-01 expects)
- sha256 `e4f03590bda38d95b884f56a1192070f7e34320840a6d89a568c6ed6024bae2f`

These are the `[exec] expected_program_md5` / `expected_program_sha256` of `deploy/arbx-stage0.toml` and `deploy/arb.toml`.
The procedure is MEASUREMENT.md §4.2 (`programs`).
