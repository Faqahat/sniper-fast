# /root/sniper-dip/dip_probe.toml — how it is built (server only; it holds tokens / keyed URLs, never commit it)

Base: `/root/sniper-dip/dip_shadow.toml` = `/root/run1/run1_landing.toml` + `[[feed]] kaldera-tx` (kind `yellowstone-tx`,
`token_env = "KALDERA_TOKEN"`, `token_header = "x-token"`). Wallet lines are replaced per wallet by the run scripts
(run_dip_prod.sh → 2g + /root/prod/wallet-prod.enc; FRZ scripts keep FRZh63… + /root/.nexus-v2-trading-wallet.enc).

Extra `[[send]]` blocks appended (10-24):
- `haan`, `bolt` — copied from deploy/arbx-stage0.toml with `enabled = true` (keys from .env: HAAN_API_KEY + JITO_UUID,
  RAIDEN_BOLT_KEY; bolt tip 0.001, max 5/s; haan max 1/s).
- `tpu-direct` — kind `tpu`, `url` = the staked-rpc block's url (constant-k RPC used for the leader schedule / TPU
  addresses; the url carries a token → server only).
- `helius-swqos` — the `helius` block with `url = "http://fra-sender.helius-rpc.com/fast?swqos_only=true"`,
  `tip_lamports = 200000` (Helius Sender SWQoS-only tier, min 5,000; 0.0002 like haqqiUUX), `max_per_sec = 1`.
  Keyless Sender = 1 request/s per IP across BOTH helius paths: never route `helius` and `helius-swqos` together.
Backup before the helius-swqos change: `/root/sniper-dip/dip_probe.toml.bak_20261024`.
