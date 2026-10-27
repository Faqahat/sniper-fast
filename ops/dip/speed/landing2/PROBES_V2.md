# Landing probes v2: rank every send path we can use, per leader type (prepared 10-25 ~20:10 PKT)

Owner OK 10-25 ~19:50 PKT ("ok") to prepare (a) routes v9, (b) the probes, (c) dip16. Nothing has run yet.

## What a probe is
- A real buy on a real dump that cannot fill (minimum-out = max, so pump fails it with 6042). We only pay the fee when it lands, about 0.0005 SOL.
- The tip transfer is inside the failing tx, so the tip reverts.
- One send path per probe, rotated across the list. Only on near leaders of the chosen client types.
- We learn each path's landing time and same-slot rate, per leader client. Split Jito leaders into relayer-fronted (50 ms hold) vs own TPU afterwards (CLIENTS.md §3).
- Evaluate with `ops/dip/speed/fixes/probe_eval.py`.

## What is deployed (both servers)
- Engine dip15 (sha256 00c94aa5…). Probes need a dip14+ engine; the run script picks dip15 for any probe flag.
- Run script md5 009ef220, with these additions:
  - `--routes v9` preset (opt-in; the default is still v8);
  - probe-only paths are switched on in the run's own config copy only when `--probe-paths` names them.
- Probe-only paths, `enabled = false` in the base configs (never built in normal runs):
  - FRA: jito-tx (Jito block-engine sendTransaction: skips a Jito relayer's 50 ms hold), speedlanding, nextblock, flashblock, blockrazor. Keys are already in deploy/.env.
  - AMS: jito-tx only. The other providers' Amsterdam hostnames come from the market scan.
- Astralane is already configured and enabled on FRA (free tier, 5 tx/s).
- Nozomi is left out of the probes on purpose. Its docs say a high failure rate lowers our priority, and probes always fail.

## Commands (FRA; the owner starts them, inside tmux, one engine per server)
```bash
# P1  Jito leaders: 8 paths x 15 = 120 probes (~30-60 min). staked-rpc = the tipless control.
sudo bash /root/prod/run_dip_prod.sh --run 17 --trades 1 --size 0.05 --fallback ck \
  --near /root/sniper-dip/near_leaders_5ms.txt --minutes 60 \
  --probe 120 --probe-paths jito-tx,helius-swqos,staked-rpc,speedlanding,nextblock,flashblock,blockrazor,helius --probe-clients jito

# P2  Harmonic + BAM leaders: 6 paths x 12 = 72 probes (speedlanding parked: its key is a wallet keypair and its only working endpoint is http)
sudo bash /root/prod/run_dip_prod.sh --run 18 --trades 1 --size 0.05 --fallback ck \
  --near /root/sniper-dip/near_leaders_5ms.txt --minutes 60 \
  --probe 72 --probe-paths astralane,landx-fra3,helius-swqos,nextblock,flashblock,blockrazor --probe-clients harmonic,bam
```

| Run | Probes | Max cost (every probe lands, 0.0005 each) |
|---|---|---|
| P1 | 120 | 0.061 SOL |
| P2 | 72 | 0.037 SOL |
| Both | 192 | **0.098 SOL** |

Probes that never land through a path mean "revert-protected" (it drops failing txs), not "slow" (CLIENTS.md §8).

## After the probes
- Pick the fastest path per client type, then live A/B with `--routes v9` plus the winners, and `--skip-clients Rakurai`.
- P3 (needs dip16 `--dip-probe-no-nonce on`): nozomi with vs without the durable nonce, 10 + 10 probes.
- Lock-only probes (dip16 optional) would also rank the revert-protected paths: Sender Max, Jito bundles, nozomi's builder leg.

## Routes v9 (opt-in `--routes v9`; from CLIENTS.md, MEASURED reasons)
```
jito     = helius + helius-swqos + staked-rpc      (drop nozomi: 0 fills / 15 late failures; drop jito-bundle: 1 landing / 54)
bam      = nozomi + helius-swqos + bolt            (drop staked-rpc: lands our failures, 2 fills / 18 fails)
harmonic = nozomi + landx-fra3                     (drop helius-swqos 0/3 and staked-rpc 2/29: slow relay)
fd / agave / other / default unchanged
```

## Results: P1 (FRA run 17, 10-25 19:24–20:24 PKT, Jito leaders, ~10 probes per path; probe_eval.py → probe_r17.json)

| Path | Landed | Same block | Feed p50 (ms) | Block-clock p50 (ms) |
|---|---|---|---|---|
| helius-swqos (keyed, 0.0002) | 10/10 | 80% | 53 (p10 15) | 48 |
| helius (Sender Max 0.001) | 9/9 | 78% | 55 (p90 136) | 45 |
| flashblock | 10/10 | 70% | 65 | 76 |
| nextblock | 10/10 | 40% | 70 | 62 |
| blockrazor | 5/9 | 60% | 80 | 77 |
| staked-rpc | 10/10 | 20% | 71 (p90 478) | 36 |
| jito-tx (block engine) | 10/10 | 20% | 340 | 107 |
| speedlanding | 0/10 | – | (https dead) | – |

Reading (small samples):
- On Jito, keyed helius-swqos is our best path: as fast as Sender Max for a fifth of the tip, with a better tail.
- jito-tx and staked-rpc are bad on Jito. flashblock is the only usable second lane so far.
- The pros' lanes (falcon / glaive / soyas / solami) are still untested. Cost ≈ 64 × 0.000505 = 0.032 SOL.

## Next probes (prepared 10-25 ~20:35 PKT; the owner starts them; the two servers can run at once)
```bash
# FRA P2  Harmonic + BAM leaders, 7 paths x 12 (falcon added)
sudo bash /root/prod/run_dip_prod.sh --run 18 --trades 1 --size 0.05 --fallback ck --near /root/sniper-dip/near_leaders_5ms.txt --minutes 60 --probe 84 --probe-paths astralane,landx-fra3,helius-swqos,nextblock,flashblock,blockrazor,falcon --probe-clients harmonic,bam
# AMS P1b  Jito leaders (most relayer-fronted ones are AMS), 6 paths x 12
sudo bash /root/prod/run_dip_prod.sh --region ams --run 18 --trades 1 --size 0.05 --fallback ck --near /root/sniper-dip/near_leaders_ams.txt --minutes 60 --probe 72 --probe-paths helius-swqos,helius,flashblock,falcon,nextblock,blockrazor --probe-clients jito
```
Max cost: FRA 0.043 SOL, AMS 0.037 SOL. The pre-send probe 3 then runs on AMS as run 19 after 00:00 PKT (real/PROBE3.md).
