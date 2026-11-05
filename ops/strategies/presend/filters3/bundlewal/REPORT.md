# Bundle-wallet rug filter (11-04)

Verdict: the bundle-ladder count FAILS. "fam" (create-slot holders + plain-transfer recipients ≥ 26.8% of supply)
is the best variant: positive in all three splits but small and mixed per run → LOG-ONLY candidate. It needs new engine
state (create-slot owners + token-transfer watching).

Bnx6XibY: 4 create-slot bundles gave ~13 wallets equal bags (~2.56% each). In slots +1..+9 they transferred tokens to
~80 fresh wallets, which never bought on the curve, so trade-only features can't see them. At arm (age 27 slots): fam 46.1%,
transfer recipients 80 holding 27.9%, create-slot holders 18.2%, ladder count 6. One of 2,316 covered fills had ≥10 recipients.

Ladder counts: e.g. ladder ≥ 36 on DEV blocked 49 fills (35W/14L) and cost −1.30 SOL; no count feature was positive on DEV.

Frozen fam ≥ 26.8% (arm cutoff; fill−1 cutoff in brackets). "−20% followers" = crude estimate, not a replay.

| split | blocked | W/L | net saved | no top 5 | −20% followers | /day |
|---|---|---|---|---|---|---|
| DEV | 122 [108] | 54/68 | +0.505 [+0.554] | +0.589 | +1.127 | +0.16 |
| VAL | 8 [7] | 4/4 | +0.113 [+0.020] | +0.037 | +0.157 | 6.9 h |
| HOLDOUT | 43 [42] | 14/29 | +0.899 [+1.057] | +0.394 | +1.025 | +0.94 |

Per run, DEV: r37 −0.008, r38 +0.304, r39 −0.637, r40 +0.710, r41 +0.115, r42 +0.020.
Per run, HOLDOUT: r44 +0.347, r45 +0.021, r46 +0.012, r47 −0.004, r49 −0.060, r50 +0.278, r51 −0.033, r53 +0.338.

Re-arms add little; T2 positions without top 5: DEV +0.928, HOLDOUT +0.187.
Create-slot share alone (≥ 25.7%) is close to fam: DEV +0.433, VAL +0.113, HOLDOUT +0.569 (+0.255 without top 5).
Overlap with fresh ≥ 35% (TAIL G3): 2 of 43 HOLDOUT blocks.

Limits:
- Recording gap 11-01 19:06 – 11-02 17:50 PKT: VAL covers only 107 of 733 fills, and r43 and the 11-02 attack are missing.
- Refills after a block are not modelled.

Code in this folder; FROZEN.json was written before VAL/HOLDOUT were scored. Outputs: /home/moiz/sniper-data/filters3/bundlewal/
