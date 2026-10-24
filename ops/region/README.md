# Multi-region dip bot (Frankfurt + Amsterdam edge) — 10-24

Why: the bot only makes money when it lands within ~50 ms of a dump, which from Frankfurt means Frankfurt leaders only (35.9%
of slots). Amsterdam (~19% of slots) and London (~10%) leaders are 6–15 ms away from Frankfurt; an engine IN Amsterdam with its
own Amsterdam feed and Amsterdam send endpoints can land on them as early as Frankfurt lands on Frankfurt leaders.

Design: one full engine per region (feed → decision → send all local), **separate wallet and loss budget per region**, and a
**disjoint near-leader list per region** (each leader belongs to the server closest to it), so the two bots never buy the same
dump and each kill switch only sees its own trades. Same engine build (dip9), same model, same run script (`--region`).

## Files
- `ops/region/make_edge_config.sh` (runs on the Frankfurt server): builds `/root/sniper-dip/dip_edge_ams.toml` from the
  Frankfurt config by swapping every endpoint for its Amsterdam twin (all resolved by DNS 10-24): constant-k rpc / staked-rpc /
  kaldera / turbo-kaldera → `*-amsterdam.constant-k.com`; jito → `amsterdam.mainnet.block-engine.jito.wtf`; helius →
  `ams-sender.helius-rpc.com`; nozomi → `ams1.nozomi.temporal.xyz`; astralane → `ams.gateway.astralane.io`; harmonic →
  `ams.be.harmonic.gg`; bolt → `ams.bolt.raiden.wtf`; landx → `ams1.landx.dev`. Kept: the eRPC shred feed (Frankfurt only,
  auxiliary) and haan (one EU endpoint). Built 10-24 16:05 PKT.
- `ops/region/deploy_edge.sh user@host [port] [region]` (runs in the container): checks the edge (glibc ≥ 2.34), installs
  tmux / python3 / ping, copies the engine (sha = Frankfurt's dip9), the keystore tool (`arbx`), the run script and
  leader_rtt.py, and pipes the model, dev list, RPC helper, `.env` and the edge config Frankfurt → edge (secrets never shown),
  sha-checking everything; then pings the Amsterdam endpoints.
- `ops/region/leader_rtt.py` (runs on each server): RTT to every leader of this and next epoch → `leader_rtt_<region>.json`.
- `ops/region/split_near.py fra=… ams=…`: gives each leader to the closer server (RTT < 5 ms) → `near_leaders_<region>.txt`.
- `ops/prod/run_dip_prod.sh --region fra|ams`: fra = unchanged (2g wallet, dip_probe.toml, dip_budget.json, logs dip_rN);
  ams = wallet `/root/prod/wallet-ams.enc` + `.address`, config dip_edge_ams.toml, budget `/root/prod/dip_budget_ams.json`,
  logs `dip_ams_rN` (Telegram env name PROD: the engine accepts only DEV | PROD).

## Steps
1. Owner: create the VPS (Ubuntu 22.04+ / Debian 12+; ideally dedicated cores; check that INCOMING traffic is not capped —
   the live feed is a constant stream, ~1–3 MB/s ≈ 3–8 TB a month), add the container's SSH key, send host / port / user.
2. Me: `bash ops/region/deploy_edge.sh user@host port ams` (zero cost).
3. Me: leader distances from the edge (`leader_rtt.py`, zero cost) → copy back → `split_near.py` → install
   `near_leaders_fra.txt` (Frankfurt) and `near_leaders_ams.txt` (edge). Report the slot share each covers.
4. Owner: create the edge wallet ON THE EDGE (interactive passphrase ≥ 16 chars; prints a one-time backup):
   `sudo /root/sniper-dip/arbx keystore-encrypt --out /root/prod/wallet-ams.enc --generate --show-backup`,
   then `echo <ADDRESS> | sudo tee /root/prod/wallet-ams.address`, and fund it (e.g. 1–1.5 SOL).
5. Me (zero cost): `--fast-bench` byte check of the buy templates and the endpoint warm-up on the edge; then a few cheap landing
   probes (fail-by-design buys, ~0.0005 SOL each, owner OK) on Amsterdam leaders to measure send → land there.
6. Owner: start runs on the edge in tmux: `sudo bash /root/prod/run_dip_prod.sh --region ams --run 1 --trades … --size …
   --tier wider --tp off --near /root/sniper-dip/near_leaders_ams.txt --minutes …` (same options as Frankfurt).

## Not yet
- The recorder / daily replay run in Frankfurt only (they see every dump anyway); the replay can split results by region.
- A London edge (helius `lon-sender`, jito `london`, nozomi `lon1` resolve) would follow the same steps.
