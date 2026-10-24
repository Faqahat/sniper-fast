# Our real landing speed from past trades (read-only chain check, 23 Oct 2026 ~17:20 PKT)

Scale: ms after the token's create by block position (slot × 212 ms + index / block size × 212 ms, votes included). This is the same scale as the dip replay's "L" and as HkQ7hMjy's "39 ms". Scripts: `our_speed.py`, `frz_all.py`; data: `our_speed.json`, `FRZ_all_buys.json`.

| Trades | Fee per tx | Tips (routes in one tx) | Landed after the create |
|---|---|---|---|
| FRZ, 18 attempts (6 tiny buys + 12 fail-by-design probes), 21 Oct 00:03–05:46 PKT | ~0.003 SOL | Jito 0.002 + 0–3 others, or single routes | **median 24.5 ms**, 16 / 18 in the create's slot |
| PROD Run 1, 2 buys, 21 Oct 03:17–03:20 | 0.011 SOL | Jito 0.012 + 1 other | **34–36 ms** |
| PROD Run 2, 3 buys, 21 Oct 22:06–22:30 | 0.011 SOL | nozomi + helius + astralane + landx, **no Jito** | **75–104 ms** (one missed the slot) |

**By leader client** (all 23 sends):

| Leader | Jito tip | n | ms | Median |
|---|---|---|---|---|
| Jito-Solana | yes | 3 | 22.6, 23.2, 33.6 | **23.2** |
| Jito-Solana | **no** | 2 | 75.2, 95.9 | **85.6** (Run 2) |
| Harmonic | no | 10 | 9.7 … 50.9, and 103.9 (Run 2 slot miss) | 24.9 |
| Harmonic | yes | 4 | 25.8, 32.7, 36.0, 155.0 (slot miss) | 34.4 |
| BAM | yes | 4 | 18.4, 19.3, 46.3, 180.7 (slot miss) | 32.8 |

- **What made Run 2 slow:** on Jito-client leaders, every send WITH a Jito tip landed at 23–34 ms, and both sends WITHOUT one at 75–96 ms. A high priority fee (0.011) did not help. On Harmonic, non-Jito routes were fast in the morning.
- **Not the network:** during Run 2, pro snipers landed 35–75 ms after the create (`ops/run2/RUN2_RESULTS.md`), ahead of us.
- **For the dip strategy:** a FRZ-style route set (Jito tip on Jito / BAM leaders; Nozomi, LandX or plain priority on Harmonic) landed at ~20–35 ms on this same scale. That is the replay's "35 ms" column. HkQ7hMjy's median is 39 ms.
- **Caveats:**
  - small samples;
  - the FRZ sends are from 21 Oct morning (2.5 days old);
  - the leader client is today's label for those validators;
  - cost: FRZ-style ≈ 0.003 fee + 0.002–0.005 tips per landed buy vs 0.0008 in the replay. That cuts the dip profit per fill from ~+0.017 to ~+0.011–0.014 at "35 ms", unless the fee can come down (HkQ7hMjy pays ~0.0011).
- **Suggestion:** instead of the 0.25 SOL five-phase probe, a small confirmation probe of ~10 fail-by-design sends with the FRZ route set (~0.03 SOL of fees) to confirm ~25–35 ms on today's network. Owner's OK needed.

## 2026-10-23 22:26–22:56 PKT: 8 fail-by-design probes from FRZ, one route per leader client (owner OK; `ops/final2/probe_buy_hk.sh`)
Routes like HkQ7hMjy: bam=nozomi, jito=helius, harmonic=nozomi, fd=nozomi, agave=helius, other=landx-fra3 (engine maps some leaders to two).
Real cost 0.0241 SOL (FRZ 0.1009 → 0.0768). Paper engine stopped 22:25, restarted 22:56 PKT with its exact command (`/root/sniper-shadow/restart_paper.sh`).
Landed after the create, block-position ms (`frz_all.py ... FRZ1023`):

| Leader | Route | ms |
|---|---|---|
| BAM | nozomi | 12.4 |
| Jito | helius + nozomi | 13.8 |
| Jito (Rakurai) | helius + landx | 15.4 (+1 slot) |
| Firedancer | nozomi | 39.4 |
| Jito | helius | 65.4 |
| Harmonic | nozomi | 78.6 (+1 slot) |
| Firedancer | nozomi | 105.4 |
| Harmonic | nozomi | 124.3 |

Median ~52 ms (3/8 ≤ 15 ms, 4/8 ≥ 65 ms). Dip bots on the same scale (live picks 10-23 evening): haqqiUUX median 130, DYXDDrZC 80, other profitable bots 210, fastest 10% 10–17 ms. Weak spot: Harmonic via Nozomi (10-21: Harmonic no tip ≈ 25 ms).
