# Token-selection search on the 15-hour raw dataset (round 1), 2026-10-22

## Data
Collected on the server 2026-10-21 22:07 → 2026-10-22 13:00 UTC; dataset at `/home/moiz/sniper-data/collect/run_20261021_2207`.

- **Launches:** 24,889 real creates (604 failed creates excluded).
  - 20,301 are SOL-quoted with sane reserves; these are the universe.
  - Excluded from the universe: 4,299 quoted in other currencies, 289 with fake (mayhem) reserves.
- **Never traded:** 5,373 launches have no dev buy and no trades at all. They are kept in the universe; a buy there just pays the round trip.
- **Transactions:** 43.9M recorded on the launched tokens.

## Pipeline (`ops/select/`)
- `a_extract.py`: trade rows bucketed by mint.
- `b_launch.py`: per-launch features and an exact bonding-curve replay of a 0.5 SOL buy, for 6 entries × 14 exits.
- `c_join.py`: joins creator/funder/metadata lookups and adds leak-free history features. History counts only launches whose 10-minute outcome was already known.
- `d_search.py`: the rule search.
  - Single thresholds at train quantiles, categorical values, and AND-pairs/triples.
  - Each rule may only use features a sniper knows at that entry.
  - Exit chosen on train.
  - Time split: train 50% / validation 25% / test 25%.
  - 2,006 rules tested.

## Costs
- Pump fee from the events (1.25% per side).
- Fixed 0.015 SOL per round trip (our priority + tips at 0.5 SOL); the 0.005 case is shown as well.

## Entries
| Entry | Meaning |
|---|---|
| E_bundle | First outside buy right after the dev's bundle. Best case; never achieved live. |
| E_slot | After the whole create slot. About our measured live landing. |
| E_s1 | One slot later than E_slot. |
| E_1s, E_5s, E_15s | Delayed entries; these may use early-flow, metadata and early-buyer-identity features. |

## Baseline: buy every launch
Test period, best exit:

| Entry | Mean | Median | Win rate |
|---|---|---|---|
| E_bundle | −3.7% | −5.5% | 10% |
| E_slot | −5.1% | | |
| E_1s, E_5s, E_15s | about −6% | | |

Peaks: 2,215 launches reached 2x, 326 reached 5x, 23 reached 10x (vs the post-bundle price).

## Result
**78 rules passed validation, and every one of them uses E_bundle.** No rule passed validation at any realistic entry (E_slot, E_s1, E_1s, E_5s, E_15s), including all early-flow, metadata, early-buyer-identity and history features.

Best E_bundle rules, test period (last 25% of launches, never used for selection), sell after 5 s:

| Rule | Test n | Mean | Median | Win | PF | Bootstrap p10 | 5 periods |
|---|---|---|---|---|---|---|---|
| creator's previous tx ≥ 352 s before create AND dev buy ≥ 1.08 SOL AND post-bundle price ≥ 3.08e-8 | 272 | +5.3% | −5.0% | 39% | 1.62 | +2.6% | all positive (+4…+9%) |
| creator idle ≥ 352 s AND dev buy ≥ 0.99 | 321 | +4.0% | −4.9% | 36% | 1.51 | +1.5% | all ≥ 0 |
| glued bundle ≥ 3 txs AND metadata host meta.uxento.io | 32 | +6.3% | −2.2% | 44% | 1.93 | −0.4% | all positive, small n |

The same rule A at later entries (test, fixed cost 0.015 / 0.005 SOL):

| Entry | Mean at 0.015 | Mean at 0.005 |
|---|---|---|
| E_bundle | +5.3% | +7.3% |
| E_slot | −1.7% | +0.3% |
| E_s1 | −4.4% | −2.4% |
| E_1s | −5.7% | −3.7% |
| E_5s | −9.3% | −7.3% |

## Reading
- **There is a real pre-buy selection signal**, positive in every 3-hour period:
  - the creator wallet was quiet for at least 6 minutes before the create, rather than a freshly funded launch-spam wallet;
  - the dev bought at least 1 SOL.
- **It pays only from the first-outside-buyer position**, right after the dev's bundle. At our measured landing (after the create slot), it is break-even at best.
- **The median trade still loses**, by about the fees. The edge comes from a minority of winners: win rate about 39%, PF 1.6.
- **Execution:** "creator idle" needs the creator's latest prior transaction before buying. That means a fast RPC lookup or a local index of wallet activity.

## Not yet done (round 2 candidates)
- Funder-cluster graph features.
- Model-based search (trees) with the same time split.
- Wallet-level sequences.
- Re-running with the metadata retries and the final snapshot added.
