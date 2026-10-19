# Stake behind send paths (2026-10-18, epoch 1061) — read-only research

All on-chain numbers: getVoteAccounts / getClusterNodes / validator-info (Config program) via
constant-k RPC, saved here (voteaccounts.json, clusternodes.json, validatorinfo.json).
Total activated stake: 437,350,803 SOL (680 vote accounts). SWQoS "staked" floor = 1/50,000 = ~8,747 SOL.
Tools: lookup.py (name/pubkey -> stake), blockpos.py (getBlock sampler), frontmix.py, createctx.py.

## Stake per identity (provider_stake_epoch1061.txt)
| provider (send path) | identity | stake SOL | % | link identity->send path |
|---|---|---|---|---|
| Helius Sender / staked conn | HEL1USMZKAL2odpNBj2oCjffnFGaYwmbGmyewGv1e2TU | 15,762,758 | 3.604 | vendor-implied |
| Jupiter tx.jup.ag (Beam) | JUPiTERrZqgf1jUyR7dSkhMx4Kn2qJyekWsg3LT1h4b | 9,718,484 | 2.222 | vendor says own validator; pubkey not in docs |
| Everstake SWQoS | EvnRmnMrd69kFdbLMxWkTn1icZ7DCceRhvmb2SJXqDo4 | 7,774,268 | 1.778 | vendor "Everstake validators" |
| P2P Syncro (largest P2P id) | GnC339vkyXRm1jRX69dt9mapPPu2LbzXfSDoxc91qta6 | 4,870,813 | 1.114 | which P2P id forwards: unknown |
| "blueshift" (NOT Shyft) | shftkxnsXmqAkmLgz9Mn7bNB5Fr6mKgFc58kFHfVikj | 3,647,337 | 0.834 | no link to Shyft found |
| Temporal Emerald (Nozomi?) | DcTPJqPNrTLv3te1c9ctA9H194x6DsaPA4ChuSEv7KPZ | 1,231,958 | 0.282 | inferred |
| Temporal Opal / Topaz | BEsnod... / 8LDyye... | 338,077 / 162,103 | 0.077 / 0.037 | inferred |
| Hello Moon (rotated id) | HM19KBHDJy93DYEJv4iFayMmCbJ1QVAk2EDG6XDgmnJS | 710,214 | 0.162 | inferred (vanity + validators.solutions); old HM1Kj... has no vote acct |
| QuickNode | 4SsMncJdtKiUcDtukkX15mqei7WiuQ9yvRtQrQW4reWC | 648,866 | 0.148 | no retail sender now |
| Corvus (Falcon) SolStack | soLStaCk5TiGCpeLKa9Fvv6f5JQGMa6S3uhLh826e9N | 246,197 | 0.056 | Falcon claims >1M (unverified) |
| Rakurai | Ed9WjPnZfAXsPttcqxMwj94qsuXVRyBsyXnDkxFva2Zv | 207,456 | 0.047 | client, not retail sender |
| Stellium | Ste1115xFGdAYK5jaWA3dEFcUc1S5jEbVvD8e327zty | 190,391 | 0.044 | |
| bloXroute EU | bxrAptB5ZpZBhoLedJpoGWY5hBjjt3zvVBr2323Rrq6 | 106,390 | 0.024 | US id has no vote acct |
| Solana Vibe Station | svsD6T44XJnuXQWB15sy1pBxxruzrFy8rR7gXy8Jsj3 | 99,204 | 0.023 | claims >500k peering |
| ERPC (vote EpicsoqL...) | CJFQNDPydtX4eL6TsgWS1hKxjh8xpJQXgkLTvkCBL4g2 | 80,158 | 0.018 | vendor said ~200k in Mar 2026 |
| Speedlanding | 3DaifGfDESUzer5ggUeo6UDjqEKMkCpdNSrrvyuggHVe | 32,833 | 0.008 | |
| constant-k RPC node | ENaBsQr4H9ALiJPQScoX8DHhXod6MWwByUS6tDVGR8tV | 0 (no vote acct) | 0 | staked path = undisclosed "staked provider" |

## Leader clients (client_share.txt, gossip clientId x stake)
AgaveBam 36.6%, JitoLabs 25.1%, HarmonicAgave 22.7%, Firedancer 7.1%, HarmonicFiredancer 4.2%, FireBAM 1.6%, Rakurai 1.2%, Agave 1.1%.
66.6% of stake advertises a tpuQuic IP != gossip IP: shared BAM / Harmonic ingress (tpu_proxies.txt), all TeraSwitch:
FRA 198.13.140.105 Harmonic 11.9% (31 validators); AMS 63.254.167.197 BAM 9.0% (67); LON 64.130.46.242 Harmonic 6.8%;
FRA 198.13.140.227 BAM 6.2% (101 validators); 88.216.192.51 (Cherry, Siauliai) BAM 4.5%.
Our host 77.223.215.155 geolocates to Limestone Networks FRA (not TeraSwitch).

## Agave v4.3.0 QUIC (source read: streamer/src/quic.rs, nonblocking/{quic,swqos,stream_throttle}.rs)
- staked = stake/total >= 1/(500*100); below -> treated as unstaked.
- staked streams NOT throttled until load EMA >= 95% of capacity; then quota ~ stake share (PR #9580, in 3.1+).
- unstaked: 200 TPS per connection, 2000 unstaked conns total (pruned oldest -> 90% when full), 8 conns per peer.
- per-IP 8 NEW connections/minute and global 2500/s (burst 1000): excess handshakes are incoming.ignore()'d
  -> client sees a CONNECT TIMEOUT, not a refusal. Likely cause of our tpu-direct timeouts, esp. because one
  shared BAM/Harmonic ingress IP fronts dozens of leaders (unverified that BAM/Harmonic ingress uses these limits).

## Our block sample (blockpos_700.json/.txt, indep_buyers_700.txt, createctx_sample.txt)
700 slots 458364285..458364984: 45 create blocks, 13 creates with same-slot buyers, 89 buyer txs.
- 31/89 buyers are glued to the create (contiguous create+1..+3). In the Lunar cases the CREATE tx itself tips
  Lunar Lander and the same creator (HV6qNY7P...) reuses the same 3 buyer wallets (NSqP5r, Gq4tf9, i1aQZJ) on two
  tokens -> creator's own Lunar bundle, not a racing sniper. 11 of 12 Lunar-tipped buyers are of this kind.
- Independent buyers: median 94-120 tx after the create. First independent buyer per create: jito 3, none 3,
  astralane 1, nozomi 1, helius 1, lunar 1 (n=10, too small to rank providers).
Caveat: Alpenglow activates 2026-10-21 ~14:50 UTC and BAM goes into maintenance mode -> re-measure after.
