# Rival arbitrage bot wallets (as of 2026-10-09)

Addresses, strategy, and what we measured. Profit figures are from this session's samples and the Oct-4 rival study
(`arbx/docs/research/rival-synthesis.md`); treat per-hour numbers as estimates over short windows.

## Profitable — the ones to learn from
| Wallet | Strategy | Measured |
|---|---|---|
| `Bgokg3jutarxEMWQVospwUucSQfpG6Jw27jRbMxcvU2q` | React once, on-chain sizing, basket + bundle-level guard, DLMM↔PumpSwap | **+1.71 SOL/h**; 54% of landings on BAM |
| `A9pQ1QsvGXJbQfvi1h9ZbSPNJ5hLTN2xMtWqjxjEU65Z` | Same design, 4 instances, 3-tx bundles, ~16% tip | **+0.82 SOL/h** |
| `MriyaNN8TMp6qRWjfr723PK7xgQK7yCt7Kg2v2PQu7X` | Big size (75% of gain from ≥4.2 SOL trades), 1.24 tx/slot, own program | top earner on our pools (~13.6 SOL won) |
| `8NQ32SyFKD1d5kenq4oM8Da6C6J9TQSMW1uAgFRveEQr` | **Profitable sprayer:** cheap misses (~5k, 84% fail) + big *proportional* tips on wins | +0.80 SOL over a sampled 37-min window |
| `7dGrdJRYtsNR8UYxZ3TnifXGjGc9eRYLq9sELwYpuuUu` | Few/s, 97% fail at ~8k, occasional big tip (Nozomi/Astralane/Jito) | **+0.90 SOL/h** |
| `8oSD5a9EG933qyuL8YdnSy6YPF7peNiXm7PAx19R1phB` | Own program (HMS28j), trio of legs, big Jito tips (1.4–7.8M) | ~0.65–0.7 SOL/h |
| `GLiCiNEnku3pQsmkVkRvnDLbfUN9BWbsrPDWLdPaADng` | Leftover gaps, tiny trades (~0.00065 SOL), ~15% tips, p50 react 124 ms | ~0.06 SOL/h gross |
| `4BQ6ATUt26GFdiYQfht23iwfKyYD9D7XbL5ATqNGk3xK` | Uses the MEViEnsc program (the BitFancy bot) | +1.85 SOL (corrected) |

## Losing / break-even sprayers — do NOT copy
| Wallet | Strategy | Measured |
|---|---|---|
| `Dy1jE82CCKsSE6aRFVfxQZemHqJ1Qa81CvGdLhxnJXJj` | 53 tx/s spray, 0% traded in sample | **−1.6 SOL/h** at the wallet |
| `CzYQ2kFnBxsNEt9Zy34vQ3n5fSDhvA4o4XaTnq1rLvyr` | 52 tx/s spray | **−1.4 SOL/h** (−1.20 in Oct-4 study) |
| `HuTshmtwcQkWBLzgW3m4uwcmik7Lmz4YFpYcTqMJpXiP` | 2.3 tx/s, 73% fail | ~break-even (−0.02 SOL/h) |

## Other known rivals (from the Oct-4 catalog)
| Wallet | Note |
|---|---|
| `FUJKrQhxWYu4z59G6JGVfZstjQKi1fY1BZNwoekgs9vL` | Baskets, uncapped on-chain sizing, strict+soft modes, 4–5 send paths, 29.6k tx/h |
| `R32xAccFis3YzBzGwZ1C4QkGiehLxSao7gDmErA3kjk` | Two arms; arm B landed 196 of 284 on BAM; Jito + Astralane |
| `DtvmxrTACskMG2W8a6KXgSemUfvyNVeQTgfpJoGvMVKx` | Same-slot reactive; ~0.88 SOL won on our pools |
| `HiPMPcYjLNPgjvdzBoavzMbCeHaXWkAuDxyuE9VoPrk` | Standing-queue sprayer, ~−0.25 SOL/h |
| `26b966MheUKjyRTes8vLbpH1qV6pVY7cNzAiyZuyrB9W` | Studied separately (`rival-26b966Mh-pools.md`) |

`9EwQoN74Hzw747EM7wB3WtvgAdRGH1czaPtbqZj1qDj4` — Astralane, ~2.1M tips.

Prefix-only (full address not in our notes; I can resolve on request): `GxDC9e…` (Jito up to 0.21 SOL + Nozomi),
`DsCJ5siu…`, `JAkGWTYL…`.

## The pattern
The **profitable** bots either (a) react once and **size on chain** with a bundle-level profit guard (Bgok, A9pQ,
Mriya), or (b) **spray cheap misses (~5–8k each) and pay big tips only on wins, sized to the gain** (8NQ32, 7dGrdJRY).
The **losing** bots spray at 50/s and pay on attempts that do nothing (Dy1jE82C, CzYQ2kFn). We currently resemble the
losing group — ~105k per miss, 1M tip on every big send — which is the opposite of what works.
