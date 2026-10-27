# Wallets doing the bait on chain (verified 2026-10-25)
"Bait" = first buy on a quiet token (no trades ≥8 s, curve ≤40 SOL) or a young token (6–25 s old, paused 2 s), 0.75–3 SOL,
then selling into the bots that buy after. P&L = realized from chain data (pump fee 1.25%/side + tx fees + tips), 4 days:
R1 10-22, R2 10-22/23, R3 10-23/24, R4 = today 10-24 19:25 → 10-25. All active on chain today (last tx PKT).

| Wallet | GMGN | Baits (4 d) | P&L 4 d | Days + | Win | Size | Hold | Last tx today |
|---|---|---|---|---|---|---|---|---|
| pXGQ6J2z | [gmgn](https://gmgn.ai/sol/address/pXGQ6J2ziRCvmYSLTT55FASf2jSHeCD6gju5xka31yV) | 42 | **+21.35** | 4/4 | 88% | 1.66 | ~150 s | 13:46 |
| HRduFFnK | [gmgn](https://gmgn.ai/sol/address/HRduFFnKv1pk7ALsQoDZseNvLAt9jUmiNq8DDtpePRps) | 63 | +10.40 | 4/4 | 78% | 1.17 | ~30 s | 16:09 |
| 2XUsvRRv | [gmgn](https://gmgn.ai/sol/address/2XUsvRRvLUqqU9rcu4hZH5Xcw56sceyps2VK19vsAqih) | 66 | +10.14 | 4/4 | 73% | 0.98 | ~3 min | — |
| 8XzVYjjV | [gmgn](https://gmgn.ai/sol/address/8XzVYjjVdpDoD3zBtXqMiMBRNj7eMhayr8DyWZQiRgs8) | 33 | +9.80 | 4/4 | 76% | 0.95 | ~40 s | 12:42 |
| 3hXxYe8X | [gmgn](https://gmgn.ai/sol/address/3hXxYe8XrxSn38RRE3u8xhB3d1rEhjYUTFRTx1Qr9r9A) | 40 | +6.85 | 4/4 | 62% | 0.95 | ~3 min | — |
| 3VUNtVtj | [gmgn](https://gmgn.ai/sol/address/3VUNtVtjjx5ckUojT7UocJ5fbuAJRsNUXNfTBnPte9vC) | 22 | +5.99 | 4/4 | 95% | 1.97 | ~45 s | 16:24 |
| 4omMYfvy | [gmgn](https://gmgn.ai/sol/address/4omMYfvyG4B3PoLpJ5PKBKWPmx4K1nZKve73iCskadnG) | 50 | +4.56 | 4/4 | 52% | 0.98 | ~2 s | 16:06 |

## Example baits today (open on Solscan)
- pXGQ6J2z buys 1.70 SOL on a quiet token → +0.320 SOL: [tx](https://solscan.io/tx/aqS1BXyPv6aq5PRhTA3VqLTRykK4Mi944Hbt8uLGt5R9qMrfvBSDSFzSf51Sh7RVkteJn8NTJf3WU7JjGuuwZGx)
- 3VUNtVtj buys 1.97 SOL → +0.259 SOL, out in 40 slots: [tx](https://solscan.io/tx/41jFQedGcB2VfCjzxXM3vW8K8hXxoDNzdLJspyXv7xKfKvd73xUGRCPqu5gbA5bmr5giWfX9yTsmasptASsv4Xv1)
- HRduFFnK buys 1.54 SOL → +0.390 SOL, out in 18 slots: [tx](https://solscan.io/tx/2eJkeEVw83mXSvJVshkw5d4izoTn4Fp7b6yXKvCReRqr5cvVabCdDjV76BoFtTgRkavpa14p6NvB6vt9cWzK7GRJ)
- 4omMYfvy buys 1.48 SOL → +0.421 SOL: [tx](https://solscan.io/tx/2ThPFa9y2uZ6BXtubC6YEsssTbSrJvFjpuvjVjsfu4iSk6KCRntgmPLyXgvwwdGL2ytr3yiACYASzgpBrRVAuajt)
- 8XzVYjjV buys 1.46 SOL → +0.085 SOL, out in 16 slots: [tx](https://solscan.io/tx/63TLTPWcHPWNos3Px6zGepCjqy454ckoUonW9ZJ6PNTCEv1MvTTmYoqDec8zf5umVxMEspCv2CtPrq1EB9fwZhhw)

## Red flags
- **Copy-traders/own wallets:** some followers buy a fixed 0.1–0.2 SOL after one baiter nearly every time
  (7pqsMoUB after 4omMYfvy 98%, 2TZonxx5 after FdSShBiR 95% and pXGQ6J2z 74%, HVE8996r/H6obhoSN after HRduFFnK ~70%).
  Small sizes, but part of their follower rate comes from their name, which our fresh wallets would not have.
- **2XUsvRRv + 3hXxYe8X = probably one operator** (same tokens, 2XUsvRRv buys after 3hXxYe8X).
- They do ~10–20 baits/day each, not ~90/h; holds are mostly longer (30 s–3 min) than our 13 s rule.
- pXGQ6J2z (0.17 SOL) and HRduFFnK (0 SOL) keep almost nothing in the wallet → they sweep funds out after trades.
