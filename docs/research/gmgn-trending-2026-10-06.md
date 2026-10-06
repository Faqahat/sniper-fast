# GMGN trending tokens: do they trade in more than one pool? (2026-10-06 ~16:20 UTC)

Source: the owner's four GMGN `trend?chain=sol` screenshots (40 tokens; the addresses shown are token mints, truncated).
Method: full mints resolved from the visible prefix/suffix via the public DexScreener and GeckoTerminal APIs (search and trending lists), then every pool of each token listed (DexScreener token-pairs + GeckoTerminal token pools) and compared with the canary's pool list `data/seed-pools-20261006.csv` (1,500 pools). A pool counts as live at ≥ $1k liquidity. Read-only; GMGN itself was not scraped. Script: scratchpad `gmgn/lookup.py`, `classify.py`.

## Result

- 37 of 40 identified. Not found: `4FEY…farS` (name cut off), ASTROCHU `DKg7…cHmE`; ANSEM's address was cut off and the name match was a fake-liquidity token, so it is left out.
- **11 tokens trade in 2+ live pools on venues we trade (same quote) → arbitrageable now.** Their 50 live pools on our venues: **36 already in our list (72%), 14 missing.**
- **The one that matters: BINDER** (57 min old) — none of its 3 pools in our list; its DAMM v2 pool did $1.29M volume / 11,015 trades in 1 h next to two DLMM pools.
- The other 13 missing pools are mostly USDC-quoted DLMM pools with little volume.
- 29 more live pools of these 11 tokens sit on venues we don't trade yet: Orca Whirlpool and Raydium CLMM (WP-21A, in progress), and prop AMMs (zerofi, humidifi, hadron). ZEC's Whirlpool SOL pool alone did $474k in 1 h.
- **24 tokens trade in one real pool only** (brand-new PumpSwap pools, or still on the pump.fun launch curve) → nothing to arbitrage. Two more (Local, Hero) have the pump.fun curve plus one pool: tradeable only once we support the curve (WP-21 phase A, launchpad curves).
- Tokens GMGN tags with another token (VVV, PUMP, SPCXX, ANSEM) are paired against that token in a single pool: a 3-leg route would be needed, and there is only one pool anyway.
- 19 of these tokens appeared in the public GeckoTerminal/DexScreener trending, new-pool and profile lists at the time, so an automatic feed does not need GMGN.

## Tokens

| Token | Mint | Live pools | On our venues (same quote) | In our list | Status |
|---|---|---|---|---|---|
| AM | `51zV2Kh2xaaUt1ALCawMFAk4HpFSzpdmLBfxRUwfpump` | 1 | 1 | 0 | 1 pool |
| HeToo | `4oqeXR2DrZ4iBboq5GDTMvJQz792VTydtXs1Zfcn6NRH` | 1 | 1 | 0 | 1 pool |
| @bot | `DicUsXhftWsq4LqFq6J1wABnEJtyDvJgM8FGmeADfsq3` | 1 | 0 | 0 | 1 pool |
| Taylor | `H89VaRkRSfxzQFKpkrA9G1zPoXeNKjEg2to9AQADe1tw` | 1 | 1 | 0 | 1 pool |
| Tesla | `DuTkejFgHx3QGdxvGTwgLAneGWipqgzMCP1V6zZ3pump` | 1 | 1 | 0 | 1 pool |
| Apple | `5hCaNj2VFTcVkiJhMwmdy9Lu9Zi4bYnYqgJq1CMvpump` | 1 | 1 | 0 | 1 pool |
| Local | `25HkohYin45HYqUPf2ds8StV2EuGy1m9qCZsJGFipump` | 1 | 1 | 0 | curve + 1 pool |
| BINDER | `BQxzR4pLkDw46gzbrkRjFuUSsgvN5BhTWHh6EXUwf3F` | 3 | 3 | 0 | **arbitrageable** |
| Hero | `6yBgsW5qm8XewXUfgrj7oH6Z9chsReffyVN5mdU3X5K7` | 1 | 1 | 0 | curve + 1 pool |
| VCAT | `4z3SGZwXofSPAhLyjWe53uh3KmgfirxwBJZ9c9rW5nnr` | 1 | 0 | 0 | 1 pool |
| DAO | `ASYY2YVsKmhWMSLDQVzVsXb8s5thY3a5YdtgDeLupump` | 0 | 0 | 0 | 1 pool |
| JAY | `C8dTVPCLjU5KL9JxVK6VdRFZCb7N6oF4GNyQXqDU61dM` | 0 | 0 | 0 | 1 pool |
| Grok | `HzFxsUCb7BqpmFAajz6jwpMyD8GyAt62c8tbuzaDpump` | 1 | 1 | 0 | 1 pool |
| ZEC | `A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS` | 31 | 7 | 4 | **arbitrageable** |
| TheGreatWhite | `7ZL2uufCxnUr6ShdqdYsR1HEYV7DZ9RFF1p6rFzqN6v5` | 0 | 0 | 0 | 1 pool |
| HIGGS | `DoVAVzViX8Bjy3r15nwikSaSbzE6dV4ovd28aWpJpump` | 7 | 5 | 4 | **arbitrageable** |
| JEANPHIL | `GTBxUiw6wJdmmkCGZgRHLyYxqu1vG4KtRpeox6yDpump` | 15 | 5 | 5 | **arbitrageable** |
| Daofund | `7dC29hjoHwT36h6Bq2CprBPRbUTA21DLDgyA3fLun4Ra` | 0 | 0 | 0 | 1 pool |
| ? | `BXoHJddsWJLHtAopeiSbKUSELsu8hSFMs8baGMDkpump` | 5 | 5 | 4 | **arbitrageable** |
| GO | `D1YZZg9dBZ7AbfknZVbaeVLto36eySwoFYEVhZrD4F4n` | 7 | 2 | 2 | **arbitrageable** |
| cell | `CeLLzSZmkXAqpZqfaS5ThQF3bDT5Ec8xEoFawyG9TLhC` | 1 | 1 | 0 | 1 pool |
| MASK | `HuAXPyDWDaMYFKuwQHpqL1oPnj93zdzWmtvFGzCeCUa7` | 14 | 5 | 3 | **arbitrageable** |
| iPAID | `CNn1zv8GsPAQddUuYn6cm3fUMTWo61XANtUjSry4pump` | 1 | 1 | 0 | 1 pool |
| Jamie | `Gn3kFAY8XcN7eH8EEPrHMw7wh7khmcjTEJ3SwbUivhNF` | 0 | 0 | 0 | 1 pool |
| ser | `D8GWC95Nd3XN4wWzMH5aT4CoAPnafoQQ1sPKNZ42R2Lb` | 1 | 0 | 0 | 1 pool |
| ore | `76fvXLL5hPsr6CQUs6PrXTY7VgdyY5tPidjPrpaepump` | 2 | 2 | 2 | **arbitrageable** |
| FRANKIE | `7pMiuJjsFs1y4wvffUebSyvkNc7E6XCe85q2SjSXQJyo` | 1 | 1 | 1 | 1 pool |
| CHONK | `FeAWY9L9hr82TvTuEyi328V9FP7GxVuGLx7xNg6kzWVa` | 5 | 3 | 2 | **arbitrageable** |
| QUACKD | `GMogeMjrWFaEceasCPathoibjAh8qwhTC3Chw4Bfpump` | 1 | 1 | 0 | 1 pool |
| MANIFEST | `BCdwQBAn8dYB5YjTsoB6TdHAWokxv28k2oZUodERpump` | 5 | 3 | 2 | **arbitrageable** |
| comjak | `FiPumqrG428nXUAvQfXg76YNtzwMJoTKrzrhJGAzSTNK` | 0 | 0 | 0 | 1 pool |
| kukuli | `76EJ4At4q1ZjucPB7AN8o7FAseFFVXxrWQczhfMRpump` | 1 | 1 | 0 | 1 pool |
| hmu | `2uVFwiars3ouoon3QC9TQG69wc1nAbc4osuMUAxipump` | 0 | 0 | 0 | 1 pool |
| BIT | `AppUrnDCmTwLh6c5uwhUqF7CqRtBESCmG1CGEqsppump` | 0 | 0 | 0 | 1 pool |
| AA | `7zFi74gVgkwmgTkmAAqsn5RmVK2BFUCuBg8SBTKGpump` | 0 | 0 | 0 | 1 pool |
| $DAOFUND | `GiJuyuqa66x4ME6keuaLJqHmBpZV9GmmnNyMUtTvpump` | 0 | 0 | 0 | 1 pool |
| USELESS | `Dz9mQ9NzkBcCsuGPFJ3r1bS4wgqKMHBPiVuniW8Mbonk` | 25 | 10 | 8 | **arbitrageable** |

## Missing pools on venues we trade (candidates to add)

| Token | Venue | Quote | Liquidity | 1 h volume | Pool |
|---|---|---|---|---|---|
| BINDER | DAMMv2 | SOL | $125,470 | $1,290,252 | `CHQ5CAEGDj5aREtyivnjk3CmNJZiWJhaXTKDGNpvKE7p` |
| BINDER | DLMM | SOL | $9,793 | $29,688 | `67mcDJDVSJpWf5No5ZtFxhZHqLHt63pntc5g3SVmwWCB` |
| BINDER | DLMM | SOL | $1,987 | $14,305 | `D4ghcnAbHWW36ZjVSJJNreqf94QzynGFt7XTx95WcQm6` |
| ZEC | DLMM | USDC | $383,087 | $19,534 | `9ToMYnmEeYKc1AWYAFo8yjPKM1bt3vPhgw1U6qh9RxBd` |
| ZEC | RayCPMM | USDC | $51,534 | $0 | `FrMLgdeZrFp6mG4DZsvcVDpbyFMaBcsWRQ9WNk7pbM5e` |
| ZEC | DLMM | SOL | $2,587 | $0 | `6FAgr8FZfsyqFY3qfAbJ9VJpV1od2gpUbRyCgEyYJyj5` |
| HIGGS | DLMM | USDC | $13,228 | $1,899 | `5VggWUCjpQN4X6tVLxA3xGx6eZ3wQoMoxXumhaWyPXa5` |
| BXoH… | DLMM | USDC | $5,892 | $0 | `7dBZFLSZtw6Br7LdFWAU9NMYc1gpv6r3stq2EwvhZrwY` |
| MASK | DLMM | USDC | $3,065 | $74 | `2UxecroK3FiBuDmjjLJhUgP31tLr1PX7ACfWasJma33V` |
| MASK | DLMM | USDC | $2,206 | $60 | `E1W77z7CWqMwDLHagoBdfrXXQ2yNqFzTydxv6E82vPsn` |
| CHONK | DLMM | USDC | $1,380 | $1,303 | `6WVNfLFeidTcYrHw8NuKVoDipe29JUuTGkBS79uemWcx` |
| MANIFEST | DAMMv2 | SOL | $1,100 | $0 | `Es2Df5rLYsa8fu322MGFKkYjEQhrBNuFQJJxaW8bktQj` |
| USELESS | DLMM | USDC | $42,928 | $894 | `8bCaqhnpeeVXXbx7oHyytsWecpHoiXhqeRBEdMEwEu7n` |
| USELESS | DLMM | USDC | $1,925,496 | $292 | `9Ux4vtd8juEH4NMF4ae3tXYpKBdeCUUipX8z3EficKme` |

## What it means for discovery

- A trending list is mostly single-pool launches; the arbitrageable tokens on it are mostly older ones our refresh already picked up (36/50 pools).
- The gain is catching fresh multi-pool tokens like BINDER within the hour. A static list refreshed between tests can't: that needs the automatic refresh at every segment boundary (proposed WP-22) fed by the public trending/new-pool APIs plus our own on-chain new-pool events.
- The bigger coverage gaps on this list are venues, not pools: Whirlpool/CLMM (WP-21A) and the pump.fun curve (11 of 37 tokens were still on it).
