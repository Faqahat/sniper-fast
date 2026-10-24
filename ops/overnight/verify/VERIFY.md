# S4 forward replay: independent verification

Checked: `report/s4_forward.json` (269 launches, 2026-10-22 17:09 → 10-23 00:34 UTC). Done 2026-10-23.
The replay was rebuilt from the raw collector chunks with my own decoder. I did not read or import anything in `core/`.

## Verdict: arithmetic CONFIRMED, but with DISCREPANCIES

- **The math adds up exactly.** My replay matches the file on 269/269 launches at L45, L60 and L75: after_sig, filled, ratio and PnL all agree (max |PnL diff| 0.0 at 6 dp). The fill counts and totals are identical.
- **Discrepancy 1, exit rule.** The written rule is "hold 5 slots from *our* buy slot". The code counts the 5 slots from the slot of the *next chain trade after us*. In 10 fills per L this stretched the hold up to 44 slots (about 9 s). Net effect is small and mixed (table below).
- **Discrepancy 2, placement is optimistic (inferred).** In 9–11 fills per L, the replay puts our buy *ahead* of buys that reached our engine before L. These are buys the engine logged as `0.000:0` sells (dKMjeG, FiFawH, 2EsRia) or never logged at all (early create-slot buys). With block-order-consistent placement every one of them becomes a guard fail, and the total drops by about 1.2–1.3 SOL per L.

| total SOL (fills) | L45 | L60 | L75 |
|---|---|---|---|
| file (claimed) | 7.058 (125) | 5.597 (110) | 4.915 (98) |
| my replay, file's rules | 7.058 (125) | 5.597 (110) | 4.915 (98) |
| my replay, exit rule as written | 6.955 | 5.751 | 5.056 |
| block-order-consistent placement | **5.843 (114)** | **4.402 (101)** | **3.626 (88)** |
| written exit rule + block-order placement | 5.739 | 4.557 | 3.767 |
| raw-data gaps fixed (4 launches) | +0.099 | +0.022 | +0.022 |

At realistic landing (L75) the defensible number is **≈ +3.6–3.8 SOL over 7.4 h**, not +4.9. The top 5 trades are 54% of that; without them it is +1.67 SOL.

## 1. Trade-by-trade recompute (raw data → placement → guard → fill → replay → exit)

- **Raw data:** 115 chunks, 30.43M tx lines, 104,907 TradeEvents for the 269 mints. Two chunks are truncated: one at the collector crash before the 20:57 restart, and the last chunk. There are no slot gaps over 8 slots (normal skipped leaders). 18 duplicate events after the restart were deduped; they fall outside every hold window.
- **File's implementation rules** (all three must be used to reproduce the file exactly):
  - Matching window is slots cs..cs+6.
  - The exit hold starts at the slot of the first chain trade after our buy.
  - The glued bundle is listed once per event, so a tx with 2 bundled buys appears twice.
- **Exit rule as written:** 33/32/31 launches differ, all on the exit point. Max |diff| is 0.258 SOL (EHs8DcjX at L45: file +0.383, literal +0.125). 51xsvihE shows the look-ahead: the file holds through the dev's full dump 44 slots later (−0.060 vs −0.030).
- **Window cs..cs+5 instead:** 3 placements change (CRMGiMh1, BLjAMp32, 7T62Ahhf). All three are early-seen sells matched to the same wallet's sell at slot +6, which is pessimistic for the file. Only 7T62Ahhf@L45 changes PnL, and block order says the file's fail is right there anyway.
- **Formula check against chain:** sells replay exactly (378/378). Buys are within ≤35,696 raw token units (≤0.036 tokens) because exact-token buys round differently. Negligible.
- **Fees:** 95+30 bps at all 333 fill points and all sell points.
- **Field meanings:**
  - `ahead` = number of matched outs (807/807).
  - `mc_sell_sol` = chain spot at the trade before our sell. It is display only; PnL uses the modified curve and matches.
- **Placements that split a multi-event tx:** 8, all buy+sell wash txs. All are guard fails either way, so PnL effect is 0.

## 2. Live-chain spot check (Constant-K RPC, read-only, 92 calls, ≤4/s)

- **Launches checked:** CQujDSKR, Hc5sxDEh, FkNS4X12, 3nJzJCM2 and 7u1ydjJj (the top-4 L75 trades plus #5), and 24nTChMf (#3 at L45).
- **TradeEvents match:** for the create tx, the tx we land after, and the last tx before our sell, every field matches the raw files (18/18 txs). That covers vsol, vtok, real reserves, amounts, user, side and fee bps.
- **Block order matches:** `getBlock` indexes of the create and every create-slot trade equal the collector's `i` (6/6 slots), so the bundle and ordering logic sit on correct data.
- **Raw-data gaps:** 4 launches miss a trade inside their replay window. All were found on chain:
  - Htfy9hg6: 2.21 + 0.99 SOL buys at cs+1.
  - 5Y7mzPwN: the dev's 0.1 SOL sell at cs+2.
  - Hc5sxDEh: a 0.02 SOL buy.
  - 4RzBrX3M: a 0.0001 SOL buy.
  - Re-running with these trades inserted changes the totals by +0.099/+0.022/+0.022, so the file was slightly conservative here.

## 3. Skeptic checks

**(a) Timing and look-ahead**
- **Placement** uses only outs with ms < L. The guard compares against the post-bundle price, which is known at decision time (~3 ms), so it is equivalent to an on-chain slippage limit. Neither looks ahead.
- **Exit:** the file's hold start uses future information (when the next trade happens). Net effect is −0.10/+0.15/+0.14 SOL, so it does not inflate the profit.
- **Placement realism (inferred, not measured):** I mapped `outs` to every tx in block order, including failed ones. I used only one-to-one wallet anchors; arrival order matches block order with 3 inversions in 1,740 pairs and none over 5 ms.
  - Misplaced fills: 11/9/10.
  - About 82% of the L75 correction rests on block order alone; the rest relies on the engine's mislabeled `0.000:0` buy for the same wallet.
  - Example, 7u1ydjJj (+0.298 in the file): 10.86 SOL of create-slot buys were never logged, yet txs in the *next* slot were seen at 40.2 ms. Placed correctly it is a guard fail (ratio 1.67).
  - 52 of the 98 L75 fills have at least one buy behind us that can't be bounded either way from this data.
- **Other engine facts:** `outs` is capped at 24 entries for 259/269 launches. The engine logs some real buys as `0.000:0`.

**(b) Concentration (file numbers)**
- L75: top-5 = 2.007 SOL = 41% of the total; without them +2.91 SOL; top-1 is CQujDSKR at +0.563.
- 65 wins and 33 losses among 98 fills; median fill +0.029 SOL; 171 fails cost −0.855 SOL.
- L45/L60: top-5 share is 31% / 36%.
- After the placement correction at L75: top-5 = 54% of the total; median fill +0.021 SOL.

**(c) Graduation:** none. No replayed curve reached 114 SOL during a hold; the max was 60.6 SOL.

**(d) Non-SOL quote or mayhem:** none.
- All 269 CreateEvents are standard: 30 SOL / 1.073e15 virtual, 7.931e14 real, Token-2022, mayhem byte 0.
- The engine's own decide features agree (mayhem=0, quote "sol"; the 17 v1 rows have no quote field, but the chain confirms SOL curves).
- vsol at fill ranges 30.0–44.8 SOL.

**Assumptions, not errors**
- **Exit timing is sensitive.** Totals under the written rule at L75: 4 slots 4.63, 5 slots 5.06, 6 slots 5.13, 8 slots 3.76, 10 slots 3.23, 12 slots 3.06 SOL. The edge fades with longer holds, so the live sell must land about 1 s after the buy, at the top of slot +5.
- **The sell is costed at a flat 0.0005 SOL.** If sells need the same 0.01 SOL tip as buys, subtract about 0.0095 per fill (L75: −0.93 SOL).
- **The replay assumes later buyers still execute after our 0.5 SOL buy moves the price ~2–3%.**

## Files (`ops/overnight/verify/`)

| File | What it does |
|---|---|
| `extract.py` | Raw chunks → `work/chain_events.json.gz` (own TradeEvent/CreateEvent decoder) |
| `extract_alltx.py` | Every tx, success or failed, touching the mints in slots cs..cs+10 |
| `replay.py` | Placement, guard, fill, replay and exit, both hold rules |
| `verify_main.py` | Comparison and diagnostics → `verify.json` |
| `arrival_bounds.py`, `placement_consistency.py` | Block-order placement check |
| `rpc_check.py`, `rpc_missing2.py` | Read-only RPC; the URL is read in code and never printed |
| `patch_missing.py` | Raw-gap PnL effect |
| `assemble.py` | Merges everything into `verify.json` |
| `verify.json` | Summary plus per-launch, per-L PnL (file rule, my rule, as written) |

Run order: `extract.py → extract_alltx.py → verify_main.py → arrival_bounds.py → placement_consistency.py → rpc_check.py → rpc_missing2.py → patch_missing.py → assemble.py`, all with `python3 -I`.
