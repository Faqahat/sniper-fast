# Run 1 (PROD p1), 2026-10-20 21:53–22:26 UTC

Owner-started PROD run: 1.5 SOL per buy, landing fee about 0.025 SOL (priority 0.011, Jito tip 0.012, other paths 0.001 each), price cap 15% (`--slip-cap-bps 1500`), sell decision 1 slot after landing. The owner stopped it with Ctrl-C after 33 minutes. The drain was clean and fast-verify showed 107 identical, 0 mismatched.

**Result: 5 fires, 2 filled, −0.164 SOL** (4.3058 → 4.1414). The guard verified all 5 fires against rule #2. Telegram sent 17 of 17 alerts.

| # | mint | dev / bundle | our position (txs after bundle) | outcome | PnL SOL |
|---|---|---|---|---|---|
| 1 | 5P2QdrLQ | 3.00 / 3.40 | +140 | refused by the price cap (price 1.76x post-bundle) | −0.011 |
| 2 | FShDX4yU | 0.50 / 3.40 | +189 | refused by the price cap (1.63x) | −0.011 |
| 3 | 8HSxaXd3 | 1.00 / 3.00 | +169 | filled; nobody else bought; flat | −0.067 |
| 4 | 6foQ7s6E | 3.00 / 3.40 | +237 | refused by the price cap (1.38x) | −0.011 |
| 5 | 72K4cK98 | 0.65 / 3.40 | (filled) | filled; flat | −0.064 |

All 5 buys landed in the create slot (delta 0). The sell path worked: decision to send in 243–350 µs with no RPC, first sell seen 115–127 ms later in the same slot. The first sell uses the min-out guess, so about 15% of each position was sold 2 slots later.

## Who beat us (`landpos.py`, measured from the blocks)

| # | landed ahead of us | what they paid | would have made, right after the bundle (sold S+1) | would have made at our position, no cap (sold S+1) |
|---|---|---|---|---|
| 1 | dKMjeG 7.9 SOL (+112), 3yrJE1 3.95 (+122) | dK: Jito tip 0.25 SOL | +1.06 | −0.005 |
| 2 | 4yFAz 1.43 (+50), dKMjeG 7.9 (+51) | dK: priority fee 0.05 SOL | +0.50 (+0.83 at S+2) | −0.24 |
| 4 | 9XPMCa 1.98 (+5), HHxaMi 3.26 (+7), 8ptvsh 1.14 (+107) | Astralane tips 0.188 / 0.090 / 0.042 SOL | +0.46 | −0.16 |
| 3, 5 | nobody (the pros skipped these) | – | – | – |

**Conclusions**
- The price cap was right every time: at our position, the refused trades were break-even to −0.24.
- The launches worth having are taken by the wallets we studied (dK, 4yFAz, 9X). They pay 4–20x our tip and land 20–230 transactions ahead of us. When we do fill, nobody wanted the token, and we lose the fees (about 4.3% of size).
- The lever for Run 2 is the tip on the path the leader uses (Jito, Astralane), not size or cap. Size it on the 1-hour recording before any live run. It's a paid setting, so it needs the owner's OK.

Logs on the server: `/root/prod/runs/prod_p1_20261020_2153.log`, `/root/prod/runs/guard_p1_20261020_2153.log`.
