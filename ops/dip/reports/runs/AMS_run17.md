# Amsterdam run 17 — dip bot run report

*Pre-send live probe 2: 0.35 SOL, whale >= 6%, 8 tries per slot via helius-ps, exit 2 slots / TP 10% / SL 20%; normal bot IMIT1 (M2 shadow), no-BAM near list (2 h)*

> **Verdict:** −0.0186 SOL on the wallet balance. Pre-send: 71 armed windows, 13 fills (18%), 6 winners; fills' own P&L −0.001 SOL, failed-try fees 0.017 SOL (3,376 tries, 260 per fill). Fails its pre-set checks: landing after the crossing trade 45 ms median (pass ≤ 22), fill rate 18% (pass ≥ 20%), live vs paper on the same windows −5.6 mSOL per fill (pass ±5). Normal bot: 29 IMIT1 picks, 1 buy sent (failed on the +5% guard); 24 picks skipped as far leaders.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.0186 SOL** (wallet 1.2207 → 1.2021, Δ -0.0186) |
| Started (PKT) | 2026-10-25 15:30:25 |
| Ended (PKT) | ? — force-stopped (SIGKILL) at ~17:45 PKT: the engine was stuck at shutdown (pre-send bookkeeping), 0 positions open; the run's time limit was 17:30 |
| Ran for | ? of 120 min planned |
| First / last buy (PKT) | 17:10:32 / 17:10:32 |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 1 → **0 filled**, 1 failed on the +5% guard |
| Fill rate | 0% |
| Wins / losses (fills) | 0 / 0 |
| Per filled buy | – |
| Fills only / failed buys only | +0.0000 / -0.0005 SOL |
| Reactive bot / pre-send live | -0.0005 / -0.0181 SOL (pre-send: 13 fills, realized -0.0010, failed-attempt fees -0.0171, 6 wins; see section 4b) |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip13 (pre-send live + sell fan-out) |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.55 SOL |
| exit | take-profit off / stop-loss −50% / time limit 5 slots (~1.1 s) |
| price guard | +5% over the post-dump price (pump error 6042 if exceeded); slot deadline = dump slot + 1 |
| buy fee (priority) | 5M µL/CU × 100k CU limit = 0.0005 SOL per landed buy tx |
| sell fee | 5M µL/CU × 120k CU limit (0.0006 SOL per landed sell tx) |
| route: agave leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: bam leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: default leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: fd leaders | nozomi + landx-fra3 + staked-rpc |
| route: harmonic leaders | nozomi + helius-swqos + landx-fra3 + staked-rpc |
| route: jito leaders | helius + nozomi + jito-bundle + staked-rpc |
| route: other leaders | nozomi + helius-swqos + bolt + staked-rpc |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | 54 leaders (buys only when the dump's leader is on the near list) |
| pre-send | LIVE: whale >= 6%, 8 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 30 fills / 0.0600 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 120 min, loss cap 0.221 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 14**:

| Setting | AMS run 14 | AMS run 17 |
|---|---|---|
| engine build | dip12 (M2 + pre-send shadow) | dip13 (pre-send live + sell fan-out) |
| pre-send | off (shadow only) | LIVE: whale >= 6%, 8 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 30 fills / 0.0600 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| limits | max 60 fills, 1 open at a time, 540 min, loss cap 0.284 SOL | max 60 fills, 1 open at a time, 120 min, loss cap 0.221 SOL |

- Probe 1 → probe 2: 0.2 → 0.35 SOL, whale ≥ 6%, 8 tries per slot, helius-ps path at 30/s.
- 2 h run, 15:30–17:30 PKT.

## 4. Timeline (PKT)
- **15:30:25** engine start #1 (session with 1 buys)

## 4b. Pre-send live (pre-placed buys) — separate from the reactive bot
Buys pre-sent after a big whale buy, before any dump. **Not included in sections 5–11**, which cover only the reactive dip bot. Realized = the engine's PRESEND LIVE REALIZED records (chain txs of each buy and sell; the buy pays the token-account rent). Rent back = that rent returned when the engine closed each pre-send account after the exit (dip19+; before dip19 the sell closed it and the refund sat inside realized). Failed tries = fees of tries that landed and failed (6042 price, deadline, …). Net = realized + rent back − failed tries.

| Session | Started | Size / fill cap / fee cap | Tries sent | Fills | Wins | Realized | Rent back | Failed tries | Net | Stopped |
|---|---|---|---|---|---|---|---|---|---|---|
| #1 | 10-25 15:30 | 0.35 / 30 / 0.06 | 3,429 | 13 | 6 | -0.0010 | +0.0000 | -0.0171 | **-0.0181** | run_stopping |

**Try results (as seen on our feed):** 6042 3,068, deadline 246, unseen 70, ata_exists 23, ok 13.

Tries never seen on our feed: 70. If they landed and failed they cost up to 0.0004 SOL in fees that are **not** in the failed-try total above (5,120 lamports each; inferred, the engine does not see them).

**By exit reason:**

| Exit | Fills | Wins | Realized SOL | Per fill | Median hold |
|---|---|---|---|---|---|
| time-limit | 11 | 4 | -0.0734 | -0.0067 | 0.9 s |
| take-profit | 2 | 2 | +0.0724 | +0.0362 | 0.9 s |

**By leader type (the slot leader where the fill landed):**

| Leader type | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| BAM | 6 | 3 | -0.0025 | -0.0004 |
| Harmonic | 5 | 2 | +0.0116 | +0.0023 |
| Jito | 1 | 1 | +0.0370 | +0.0370 |
| Firedancer | 1 | 0 | -0.0471 | -0.0471 |

**By hour (PKT):**

| Hour | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| 10-25 15:00 | 3 | 1 | -0.0029 | -0.0010 |
| 10-25 16:00 | 6 | 4 | +0.0331 | +0.0055 |
| 10-25 17:00 | 4 | 1 | -0.0312 | -0.0078 |

**Best pre-send fills:** CcWwsjhs +0.0370 (Jito, take-profit); pkyVz2uR +0.0354 (Harmonic, take-profit); BMB1UAho +0.0172 (Harmonic, time-limit)

**Worst pre-send fills:** 9zJ6CkUF -0.0471 (Firedancer, time-limit); CyaaPF2F -0.0397 (Harmonic, time-limit); 2nWzumsh -0.0107 (BAM, time-limit)

**End-of-run checks:**

- session #1: no END CHECK line in the log (engine before dip19)

**Every pre-send fill** (time = fill; whale = the trigger buy; P&L = realized, rent back not included):

| # | Time | Token | Whale % / SOL | Slots after whale | Leader | Exit | P&L SOL | Links |
|---|---|---|---|---|---|---|---|---|
| 1 | 15:37:42 | [G3GsbF](https://gmgn.ai/sol/token/G3GsbFyyXFtAEcskYzGUY9FmgMXJGa1FabmNLmQfpump) | 8.5% / 2.96 | +6 | BAM `6WgdYh` | time-limit 0.9 s | **-0.0002** | [buy](https://solscan.io/tx/3TrVcPQ5xgVK536VSCvq1rr6sperccWec9VoLQwbibkb3gVSQR8EggKSvW6qRrapMZpGxLfADgRXbfkUUsoRBq7R) [sell](https://solscan.io/tx/3oYa3zub1mJYdeb91DVq6XP4RGubAf5CZKfd2ebHmtjFK2veDNJ8MvhLyinJP6HKYLt4oYY8ofYnVJKU4yHrsuFd) [whale](https://solscan.io/tx/3odXiDJL6UaYXK5tC99Ve73ooeZt7SYH3H5ie8WiwCxtJK5J38CFktbx4EwuWKGRqhkj6rhkSoEfHiTcNrZ1xstR) |
| 2 | 15:42:09 | [CcWwsj](https://gmgn.ai/sol/token/CcWwsjhsEUZSqMMarjdg1ZTYNiBN3bQZhdH478PXpump) | 8.5% / 2.96 | +6 | Jito `HEL1US` | take-profit 0.6 s | **+0.0370** | [buy](https://solscan.io/tx/5jFwdMpdJNNX8BHobxgvNEvzigvTAYfpnMJU12k9fXTEAEpq82HXGvXKCThitKfyZXWUzX7EPj1BRwfNsw1SBPL2) [sell](https://solscan.io/tx/4qZsBGjLn7qdPGbJ6DUhPWcZn13z5g87R38uv6eM3w2bbWcwCEdqnE3BbnPNu2d5FzeNV65pwv6Pg9SKU9Jjs4Th) [whale](https://solscan.io/tx/2cAABMQZaZJxQ2JmmvnGuQT2YdqusFsnQ7Q2QFSRyjhMpdhhhUREWuf1MEACsJH6SQhC3K6V3p3bQ5BxNjU4Uw1j) |
| 3 | 15:51:42 | [CyaaPF](https://gmgn.ai/sol/token/CyaaPF2FdFTqZyZY6bKNcAMb955C9qDHXbRp2tj8pump) | 6.3% / 2.96 | +6 | Harmonic `shftkx` | time-limit 0.9 s | **-0.0397** | [buy](https://solscan.io/tx/5M5E7VD549DDvv7bx2bfJjNYJWTv7dqJajMkELPgoYjVN8vrKkaYmBwzEzZ5gvjr9z5EXXmUxyHkoHgT24SrAKcs) [sell](https://solscan.io/tx/5FidHgsTiCp7qCWvcrysmQYuTv7M1NfmWaBFtJBQ1b4zafnvZwKhh2LivUndBPhrpAJdDyCErz4ogMrU96Kwm1nU) [whale](https://solscan.io/tx/2bS1GUUfujZM1Zb8t9w2X8JEiiwyn11bcXogeuj78LVMZK2dMbHd4RSgxYufkXLFQKp3U2f3qKVjgCvqPEfn9UKN) |
| 4 | 16:01:01 | [39CBv1](https://gmgn.ai/sol/token/39CBv1APeFCS5FjXQH8ifW7diJD1T3MKaEPH8TwCpump) | 8.6% / 8.89 | +1 | BAM `6WgdYh` | time-limit 1.5 s | **+0.0041** | [buy](https://solscan.io/tx/3TE81nAhmzpHQMKrSYgv8XPS8LYYk8xLZiXdySccghpUzGkeEtb8B3PdERHKji8LBxs9LkPDd5TuHAKhCsTfd8bY) [sell](https://solscan.io/tx/4BUZasgXw2ZqUhUWZgz52HXNsLqfsqMpTEzBkT4Z9EcsA1p2oc75bNJoCLyyQQExcYsrDgvjnWpZMtdfPHcczJja) [whale](https://solscan.io/tx/4cDP291xpX8Rf79rG4P3Sh2nypj5B1wPP2ReEYnhj7KJbEzwJeXF2ijCDLMY1xcdrwsaGkCaPCa8x98mZu5zNsar) |
| 5 | 16:10:58 | [4enWrp](https://gmgn.ai/sol/token/4enWrpFL8kRsuN5EBeWpysCvJiHgcQME8nXUm1preZNY) | 8.8% / 2.96 | +1 | BAM `BGAjni` | time-limit 0.9 s | **+0.0090** | [buy](https://solscan.io/tx/6653gUTxYRJRmZUU6P98KUQaXPzCPQ6hptAGqRF8V36djXsbYuTWv6k32A5WefmqNev5kd9zs3We26gYK6FbaeCB) [sell](https://solscan.io/tx/3juUyUt9aVcY2Y9yyy9YnEtg2H65fvpGDqS4zywD3isAXoPnJ8f21BDQPR4xBx4jpfZvLQEhVnS6kSgkMnjLcSwX) [whale](https://solscan.io/tx/3rUgjkch5QYJRMBAb9wm2ZrDGduqKumaHB6Ne1edoEuhEgcXwj9WbFbn9Z5SkpYCUyY1zgGwy2ZUpTa45JgFDAVD) |
| 6 | 16:11:48 | [9peTws](https://gmgn.ai/sol/token/9peTwsX2PnqPBGxPkRGr2s4VfM2zHAQsUHCWAuakpump) | 8.8% / 2.96 | +5 | BAM `3JotfS` | time-limit 0.8 s | **+0.0059** | [buy](https://solscan.io/tx/4RFNh46uS9MiARtSPW8tACUasNGwXTqJFJXJk7gs45R15cAMAHdXmqumWbiXQYkjCWUKVmB4wvRZAuQK4c6uW33j) [sell](https://solscan.io/tx/stMenHvd2nnx5yBQqkKkjpVF84FcnnVtfiPm3U5q3hijVrKKtxKYVTB6G8sq36FVkANmKWDBBennekAiyYsqVjG) [whale](https://solscan.io/tx/35WhBKeVZks27MP1mH7ZdfNFYS7tuQFYBcBRjTjKfi26RScZtfrbkb2qgiAyGs6ktF67kexGNuMZNR8GuURTAUeG) |
| 7 | 16:47:09 | [2nWzum](https://gmgn.ai/sol/token/2nWzumshEqRmJPRnaQM41oYvFyDH8if3XKLC1qBYpump) | 7.7% / 3.95 | +6 | BAM `G2TBEh` | time-limit 1.2 s | **-0.0107** | [buy](https://solscan.io/tx/4nXFdy8PDMTsxByg6FF1ygkcotgw3X2PSE2MjYG9nvPMEjwiSi7DVxs6ECAFmZaYrXegidWJToK1LcD3cicL8AXG) [sell](https://solscan.io/tx/eGHAc4MXWxNBsK8ckh9Vx5NY68VGhAUEWNGdcg8DqgjDLG9NqK3kyfQwHjzUyiR7NjwuMzBh4t7VKV3VheFyY54) [whale](https://solscan.io/tx/TRQ7qsE9qBh1VHQDGzy5kF9vrDsEShXBqn1bsf1Shs65xkY8c91wDqZjWsBbMLp5oy4VcxeaWhq6eaHghAVsXvX) |
| 8 | 16:52:30 | [pkyVz2](https://gmgn.ai/sol/token/pkyVz2uRkPMrNExL52FVqysWrfjjSc5KSsfRZBpFfHV) | 6.6% / 2.96 | +6 | Harmonic `9W3QTg` | take-profit 1.3 s | **+0.0354** | [buy](https://solscan.io/tx/SM5zJBaJMRX9kFnTCnERmFraze6ZBxuRn5GT8ZLiEVuZ1BQWU53VuHkWVcxx8urPq8VumHR6oZ9wgE71ua7rixi) [sell](https://solscan.io/tx/65nUZ8thKEzPLRFQw2MSuBTuekfcfzDyYp1ffbtz48a2iNcoapsWrGotCp5JER1c5kZN6xFVkN365KQAgCE1dHyW) [whale](https://solscan.io/tx/5wQza1HMMHvUQWJSXHeYJNc6awidbrh38CcBXWPqtoQtmZVRjctCHgNrvxWYaULsZhyEQveN682YNXLNA4q4c57p) |
| 9 | 16:57:07 | [7ZZLGT](https://gmgn.ai/sol/token/7ZZLGTSzXHjS1UqkXG4qfhqCaDRLZvjoHrn2rgnQpump) | 9.0% / 2.96 | +5 | BAM `DRpbCB` | time-limit 0.8 s | **-0.0107** | [buy](https://solscan.io/tx/4DaCFcUCJ87cj9TfRshE3unwgn8aD1njAJAVcCPJmHGL3fSg8Rnm8xcged5xzyW4g2fULTQFsvxaCyHUq3hPJdG5) [sell](https://solscan.io/tx/2VocdTroFvstXmVe2FkeKMCrVoXYTiW4QRkjrPLM139PAhc6bGzRtEjByEahMaNQiy3PnUhX3bcNiXc77G97Kcmp) [whale](https://solscan.io/tx/21NwVLMwCnpwsYSvzgMvdM3yutZ1hK9QAUR2SdA4miZYwARLWGaHT5kQJJsjmzYRwb9QhcDSLaVYxxCDjPU5BZi7) |
| 10 | 17:14:10 | [9TLduD](https://gmgn.ai/sol/token/9TLduDrC4ydeXxsz4dYXvcUW5NoG1znrojpcvFAdpump) | 9.9% / 4.44 | +2 | Harmonic `3iSQtP` | time-limit 0.9 s | **-0.0013** | [buy](https://solscan.io/tx/5sqwxXDrFbcFoygzh2gB2bibiULV2V4JEeYoC2ykziEmZYqeXYT5DeAjRcoCCgHm135U9fBEHyXXtFjjUyyq91rj) [sell](https://solscan.io/tx/3Y9oTJhYNxUnmApEp7smHYLf2RUrLFz1HZ45e1D71cirR3LC3Bdaua5jM2XUgcda4RahRe9nadhGxPQqDPwEB3hH) [whale](https://solscan.io/tx/2hmg5ToLrrZXSrjSr3Y96Pym8b3xzmmCwqs26ZhgRTkQjCg79wguFCMA9qXyu6HzRFUFuEii32rzVDkH6VDrBVb) |
| 11 | 17:14:25 | [9zJ6Ck](https://gmgn.ai/sol/token/9zJ6CkUFcyALjofJNcwT7jgMbKMYkvf53X3JD4Pppump) | 9.9% / 3.38 | +5 | Firedancer `VQwCCS` | time-limit 0.9 s | **-0.0471** | [buy](https://solscan.io/tx/5iZfP8HQqDBwVr5ALMxZXYyEZuVJdfq9PUtpef5Sq1mU8sRij8ZwXChbw2Kf8nCHiKxcvi5beCKNCKCkaqvYkcfr) [sell](https://solscan.io/tx/3miot3CYaxbnYoXeXMstWR3z15k4B7yQ8gx7e6oWVj19UbN9NyyUeZ7p1knDLijzR5VhwJzUY8kA28N3WW9tvH7w) [whale](https://solscan.io/tx/5XfviqpV6DazBf9huLWQ9R5pVLrQENu2NxcS4Nct4ftDDsK1Yyw9TB67ri75FZVDwEcHt2mtTn4eyDg7Ep5yRDBL) |
| 12 | 17:15:29 | [BMB1UA](https://gmgn.ai/sol/token/BMB1UAho52HRXbR2HfbsA2fS9X9QmdUZDdNzpNL4pump) | 9.1% / 2.96 | +6 | Harmonic `JUPiTE` | time-limit 0.9 s | **+0.0172** | [buy](https://solscan.io/tx/2thKhGLnMQMomxjRtPFN8pL3bUfVPVQ2VrATjTXeMpYp1y1AhR1gR8T3kvhP6uk41yYqmcWppKoWnxqWDVWesqP5) [sell](https://solscan.io/tx/3qjnRDijq6ZeVG9KXoNwj5WwdZr3Lak6fpMCb5pQt8XmPLhmzVMLgrvbUv1CV6paAs43s58Z6ByifiwpNFx9WQiR) [whale](https://solscan.io/tx/2KKvkfpGLkbH4JtTpvsMoofNtvjbo71hWvuY1ebfoiospS6SKy3NDDhCADgUieYVuPeco8kmAfCp3McBP6HtG2L) |
| 13 | 17:29:52 | [tBJGEN](https://gmgn.ai/sol/token/tBJGENo4bEowoSZU4wV7u6N3sPXoJwVfXZwi9Jtpump) | 6.4% / 1.98 | +2 | Harmonic `BbCQMW` | time-limit 0.9 s | **-0.0000** | [buy](https://solscan.io/tx/33zB4VpiGXeeW3otBMPqvzbQBYcCuXc2PX2sJT36YqK7BZ44ic8JgZzeV9pxfZmuvFFGmSSfXdAS9nikGK9up5Ne) [sell](https://solscan.io/tx/3FDFhQEx9r7oZbhdnG4fwoPmcVoyn3qykN3Rpf5Tb7eRRiL8yRemt9p87JdR1GXdEVf33h2u33J9RP17Rno11x6g) [whale](https://solscan.io/tx/Ltf8kQGxJsLZnwyjz73PAgrjjtZ3N6dwBv6LHZ2gNKnwfbFmfxSoKj9eu7FapCWUHuEHFYicZMg72B3AjXreqWU) |

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 1935 |
| Inside the envelope (age / drop / since-buy / size) | 1935 |
| Picks (score above the threshold) | 2 |
| Skipped | far_leader 24, spacing 2, legacy_create 1, presend_armed 1 |
| Buys sent | 1 |
| Filled | 0 |
| Failed on the +5% guard | 1 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 0 of 0 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 17:10:32 | [EXuFTr](https://gmgn.ai/sol/token/EXuFTrqrqv82MNw8ctQEpk2TLidhn8ap6Y6D8oaDn8z6) | 0.35 | 0.63 | 5.93 / −30% | 2.5 s | Jito `AEHqTB` | guard fail | -0.0005 |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 17 | same | 1 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4zm67d9auqxdLN4mnWFmS1Y2zaBg4CKjPkPdiUfRTcqRiCPXayTpFSWFex9aADqycdxm1ubRVqCoHgvkdnoD84SZ) [dump](https://solscan.io/tx/2nxmaWzUkqMfkqKyX7BaCahE4pTLqnHvq7VjbGGZgtPRWhUZNB8zEmySpS9w2okcF76UQXTPqDtX1voKEeDErrVF) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Jito | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 17:00 | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|

## 8. P&L leaders
**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `AEHqTB2R` | JitoLabs | 1 | 0 | -0.0005 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 898 (p25 898, p75 898, n 1) |
| Executed-feed lag behind first sighting, ms | 1.4 (p25 1.4, p75 1.4, n 1) |
| Buy sent → our tx seen on the feed, ms | 15.9 (p25 15.9, p75 15.9, n 1) |
| Fills: our buy seen on the feed after the dump, ms | – (p25 –, p75 –, n 0) |
| Guard fails: our failed buy seen after the dump, ms | 17 (p25 17, p75 17, n 1) |
| Fills in the dump's own block | 0 of 0 |
| Guard fails in the dump's own block | 1 of 1 |

**Which copy landed (nonce fan-out):** nozomi 1

**Send-path answers (FAST-ACK lines):** nozomi 1 (median ack 0.3 ms), helius 1 (median ack 0.4 ms), jito-bundle 1 (median ack 1.3 ms), staked-rpc 1 (median ack 2.0 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | – |
| Guard fails: rival buys ahead (median) | 1 |
| Guard fails: rival SOL ahead (median) | 0.75 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 8yYMhuYo | 1 | 1 |

## 11. Costs
No fills. Failed buys cost 0.0005 SOL in tx fees.

## 12. Health checks and red flags
- ⚠️ 14 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ℹ️ RPC bh-fallback getSlot: slow minutes (worst p99 303 ms, max 852 ms)
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)
- ⚠️ Engine did not exit at the end: the pre-send module counted 3,429 tries sent but only 3,420 resolved, and the run waits for all of them. Force-stopped (SIGKILL) at ~17:45 PKT with no positions open (13 bought / 13 sold / 0 unsold); the final run_end record is missing. Fix needed in the next build.
- ⚠️ Paper over-predicts each fill by ~5.6 mSOL on the same windows (matches the replay bias the VM1 check measured on 496 real fires).
- ℹ️ The normal bot barely traded: the no-BAM near list skipped 24 of 29 picks.

Checks passed: every reactive fill was sold; every pre-send fill was closed by a sell; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Done after this run:**

- Bug list for the next engine build: (1) pre-send shutdown waits forever on lost tries (resolve them as unseen after a grace period); (2) an empty pre-send route class panics.

**Recommended / open:**

- Hold pre-send scaling (0.75 SOL plan) until a fix for the paper bias or a faster landing is shown; probe 2 failed its checks.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r17.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r17.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Pre-send (section 4b): the jsonl presend_live_* records (fills, closes, REALIZED, account closes, stops, end checks) and presend_attempt_land (try results, failed-try fees); the log's PRESEND LIVE lines when a run has no such records.
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.
