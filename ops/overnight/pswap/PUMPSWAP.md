# PumpSwap (post-graduation AMM) study, 10-25, read-only
Data: 15.3M PumpSwap trades R2+R3 (extract.py → parts/), 7.7M ≥ 0.001 SOL (bucket.py → bk/). Cleaning drops dust and mis-parsed rows (account-rent "buys" with impossible reserves).
Scripts: study.py → study.txt (census + trigger replays), winners.py → winners.txt (top-40 winner profiles + copy replay).
- **Pools are deep:** median ~300 SOL, fresh graduations ~85–95 SOL. Fees ~0.95% per side incl. tx.
- **Generic triggers at our speed (1 SOL, cleaned): all negative on both days.**
  - Dip after a sell ≥ 1 / 3 / 10 SOL at 35 or 75 ms: −0.03 to −0.07 per trade at 1–3 s.
  - Graduation snipe: small negatives.
  - Momentum: negative.
- **143 consistent winners** (≥ 20 closed positions both days, both days > 0):
  - HkUarWAn +244 / +184 (75% win)
  - DqH8MdY9 +86 / +70 (76% win)
  - AhdtDQrM +47 / +87
  - Style of the top group: buy ~1 min after graduation, 44–61% right after a ≥ 3 SOL sell, sell part after 2–4 s. They are fast graduation-dump backrunners, often several in the same slot.
- **Copy their first buy** (1 SOL, T = 0.2 / 0.5 / 1 / 3 s, exit = mirror their first sell or 1 / 5 / 15 min timers): negative for every wallet on both days.
  - Mirror exit: −0.07 per copy. Timers: −0.10 to −0.31 per copy.
  - (The "we pay vs their fill" line in winners.txt is wrong: it uses the price at the end of the replay. Ignore it.)
- **Verdict:** PumpSwap has the same structure as the curve. Winners are fast backrun bots; generic rules and copying lose at ≥ 35 ms / ≥ 200 ms.
