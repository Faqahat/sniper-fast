# What triggers the 1.5 SOL group's buys? (10-24/25, read-only; scripts pre.py, meta.py, tweets.py, siblings.py, leader.py)
- **No on-chain trigger:**
  - The tx before their buy is random: buy 23 / sell 23 / non-trade 25. It comes a median 5 s before (0.2 s – 2 min).
  - No leader wallet: every frequent earlier buyer is a busy bot with lift < 1.
  - No copycat-launch heat: same-name launches in 30 min are a median 1 vs 2 for random tokens.
- **They buy QUIET moments, not momentum** (at the group's buy vs random earlier moments on the same tokens):

  | | At group buy | Random earlier moment |
  |---|---|---|
  | Price change, last 60 s | 0% | +21% |
  | Buyers, last 60 s | 9.5 | 21 |
  | Gap since last trade | 6 s | 0.13 s |

- **Tweet tokens:**
  - 96% of their tokens link an X post (86% for random tokens).
  - 56% come from tweet-to-token launchers (j7tracker 44% vs 22% overall; uxento 12% vs 5%).
  - Tweet → launch: ~8 s. Tweet → group buy: median ~10 min (11 s to hours).
- **They buy narratives, not single tokens:** two "Saviour of the Internet", two "Hurricane Vance", two "4skinners", two "OGCALLERS", two "The Coal Man" (same tweet), two "TigerPrawnJacketPotato", three "Chosen Chud", plus the PHP set.
- **Human hours (inference):** they trade 17:00–09:00 PKT and never 10:00–17:00 PKT, with a 9–10 h pause every day (= 01:00–08:00 US Eastern). Likely a US-based human on Trojan with 4 wallets.
- **Reading (inference):** the trigger is off-chain — a person watching X / tweet trackers and choosing narratives. It is not visible on chain before their own buy. Their own 4-wallet buy is the only on-chain signal, and that is what the copy bots race on.
