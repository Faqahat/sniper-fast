# How the "instant bots" land 1–3 txs after a dump — PROVEN (10-25, chain + Jito public explorer, read-only)

Data: 7 h chain recording (10-24 14:25–21:30 UTC): 38,306 dumps (pump sells ≥ 1 SOL).
- 1,221 buys by OTHER wallets landed 1–3 txs after the dump in the same block, on 964 dumps (2.5%).
- 640 of them are exactly 1 tx after. They are spread over many wallets and every leader client (BAM 438, Harmonic 399, Jito 252, FD 97), and most carry no tip.

Sample of 60 (full signatures from the raw recording, bundle membership via bundles.jito.wtf, scripts instant*.py / this folder):
- **Exactly 1 tx after: 29 of 40 are in the SAME Jito bundle as the dump.** 2–3 txs after: 5 of 20.
- Of the 34 same-bundle pairs:
  - **28 have the bundle's Jito tip paid by the SELLER (the dumper) itself**; the bundle is [sell, buy from another wallet, tip], always in that order.
  - **6 are tipped by a third wallet.** One has dip bot 4oN18efp as the buyer. Several carry 0.00015 SOL tips from shared wallets, which looks like a trading platform packing user trades.

## Conclusion
- **Most instant buys are the seller's OWN bundle** (sell + buy by another wallet of the same operator: wallet rotation / volume).
- **The rest are third parties that received the seller's tx before it landed** (private order flow / platform bundling).
- **None of it is reacting faster.** No reaction speed (and no pre-send) can be ahead of a buy packed into the seller's own bundle.

## What it means for us
- Pre-send cannot catch these buys: the buy is not a race, it is part of the dump.
- **Dumps with a same-bundle buy are not real dumps** (the operator buys back within the same atomic bundle). They are a signal to SKIP, or at least score differently.
  - The bundle is invisible before landing, but the pattern can be learned: same dumper wallets repeat (e.g. ENEodZD5, EVjqwzVu) and the tip size is fixed (0.003 / 0.006 / 0.01 SOL).
