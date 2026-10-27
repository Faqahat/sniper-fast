# M2 dip detector: engine port (agent, 10-25 00:45 → 02:00 PKT)

MEASURED means a replay or a test result. INFERRED means my reading of it. Replay results are given for each landing time
(35 / 50 / 75 ms). They do not claim what our real landing time is.

## Bottom line
- **Ported model:** the 25-feature one (`v3_reg4_top25`). On the clean holdouts (R3 + R4) it keeps 98% of the full model's
  result at 35 ms and 97% at 50 ms (MEASURED).
- **Threshold:** M2 score ≥ **0.010095**, chosen on R2-val only.
- **The Rust port is exact (MEASURED, cargo test):** 9,360 study dump rows, 0 feature differences, score difference 0.
- **New engine flags:** `--dip-m2 FILE`, `--dip-m2-mode shadow|gate`, `--dip-m2-min X` and `--dip-m2-extra on|off`.
  Without `--dip-m2` the engine behaves exactly as today.
- **Exit:** `--dip-hold-slots 5` gives the replay's c4 exit (MEASURED on run 10).
- **Peak window:** 00:00–04:00 PKT (US peak) and 20:00–23:00 PKT.
- **Found while porting:** the engine never looked at ~20% of Stage A's picks. They are a second big sell in the same slot,
  and the IMIT1 rules take only the first big sell per slot. Fixed by "extra dumps" (on with `--dip-m2`). IMIT1 never
  picks them.
- **Binary (not deployed):** `/home/moiz/sniper-data/strategies/dipdetect/bin/snipe_engine_dip10_m2`, 77,418,536 bytes,
  sha256 `540569ff60066aea9c59441229adb677c8ae3ca9bbe042a257a7c7d129f37f71`.
  - Built from today's uncommitted dip10 tree plus M2.
  - The same file is at `/home/moiz/sniper/target/release/snipe_engine` until the next build.
- **Bundle (model + wallet lists, one file):** `m2_v3_reg4_top25.json`, sha256
  `5bf40a8288f7652c2a7db8aa7a68b2e8f93fa4290e728425b043c052b899bab0`.
  - Next to the binary, and in `/home/moiz/sniper-data/strategies/dipdetect/`.

## 1. Model and threshold (Phase 0, `dd15_stageA.py`)
- **Row alignment:** both prediction files match predictions recomputed from the model JSONs exactly (max diff 0 on all
  653,103 rows).
- **Threshold, R2-val only:** at 0.010 the full model picks 396 of 11,031 in-envelope dumps. The top25 model picks the same
  396 at ≥ 0.010095.
  - The R2-val sweep liked 0.002 better. It makes more at 35 ms but goes to −0.03 / −0.90 SOL at 75 ms on R3 / R1, so it was
    not used.

**Stage A replay results.** Envelope as today, exit c4 (sell lands 4 slots after the entry slot), FRA + AMS, 0.55 SOL.
Each cell is SOL, then fills / attempts.

| Detector | R2-val 6.5 h | R3 21 h | R1 14.9 h | R4 3.3 h |
|---|---|---|---|---|
| **top25 ≥ 0.010095, 35 ms** | +3.91 (114/201) | +10.45 (446/743) | +6.09 (397/588) | +2.86 (68/133) |
| top25, 50 ms | +2.12 | +6.21 | +3.30 | +2.09 |
| top25, 75 ms | +1.81 | +3.08 | +0.82 | +1.21 |
| full ≥ 0.010, 35 / 50 / 75 ms | +4.86 / +2.27 / +1.77 | +11.18 / +6.89 / +4.01 | +8.55 / +5.38 / +1.35 | +2.35 / +1.69 / +0.79 |
| IMIT1 top4, live exit (1.3 s, SL −10%) | +2.18 / +0.81 / +0.23 | +4.42 / +1.87 / +0.80 | +4.06 / +2.59 / +1.21 | +0.34 / +0.03 / +0.03 |
| IMIT1 top4, exit c4 | +2.81 / +1.27 / +0.85 | +4.33 / +1.99 / +0.80 | +6.12 / +3.93 / +1.54 | +1.03 / +0.64 / +0.37 |

**Pooled, SOL at 35 / 50 / 75 ms:**

| Detector | R3 + R4 (clean holdouts) | R3 + R1 + R4 |
|---|---|---|
| top25 | +13.31 / +8.30 / +4.29 | +19.40 / +11.61 / +5.11 |
| full | +13.53 / +8.57 / +4.80 | +22.08 / +13.96 / +6.15 |
| IMIT1, live exit | +4.76 / +1.90 / +0.82 | +8.82 / +4.48 / +2.03 |

- **Decision rule (R3 + R4):** top25 / full = 0.98 at 35 ms and 0.97 at 50 ms, and top25 is far above IMIT1. So top25 was
  ported.
- **R1 is weaker for top25** (0.71 / 0.61 of the full model). R1 is a test day for M2 but overlaps IMIT1's training.

## 2. What the engine will actually do (`dd16_visible.py`, `dd23_port_tables.py`)
- **IMIT1 dump rule:** the engine scores a dump only when the IMIT1 book makes it a dump event, and that is the first big
  sell of its slot. The study scores every dump.
  - 18–21% of in-envelope dumps are later big sells in a slot. They are 17–23% of Stage A's picks.
- **Dev-list tokens:** in gate mode they keep their IMIT1 tier, so nothing changes for them.

**SOL at 35 / 50 / 75 ms (MEASURED replay):**

| Variant | R3 + R4 | R3 + R1 + R4 |
|---|---|---|
| Study (every dump) | +13.31 / +8.30 / +4.29 | +19.40 / +11.61 / +5.11 |
| **As built: extra dumps on (default), dev list on IMIT1** | **+12.36 / +7.59 / +4.00** | **+19.05 / +11.45 / +5.35** |
| Extra dumps off, dev list on IMIT1 | +10.20 / +6.19 / +3.24 | +16.43 / +9.97 / +4.75 |
| As built, but SL −30% instead of no SL | +12.34 / +7.57 / +3.98 | +19.05 / +11.46 / +5.36 |
| IMIT1 today (live exit) | +4.76 / +1.90 / +0.82 | +8.82 / +4.48 / +2.03 |

- **Why dev-list tokens keep IMIT1:** that rule (IMIT1 "wider" tier, bigger size) is the owner's choice, based on the bots
  over-weighting that dev. The M2 study never tested dev tokens separately or at the bigger size, so the gate should not
  silently change it.
  - Cost in the replay: about −1 SOL on R3 + R4 at 35 ms.
  - Making M2 decide dev tokens too is a one-line change if the owner wants it.
- **Stop-loss:** in a 4-slot hold, SL −30% equals no SL within 0.02 SOL. The prod script's `--sl 0.5` is fine.

## 3. Hold slots: use `--dip-hold-slots 5`
- **Code:** the time-limit check is `slot_now + 1 >= buy_land_slot + N`. It fires at the first feed trade of slot
  buy + N − 1 and sends right away.
- **MEASURED on run 10:** the time-limit sell lands in slot buy + N − 1.
  - FRA hold 19: 20 of 20 at +18.
  - AMS hold 6: 17 of 18 at +5.
  - Block index median 134–198, about 70–105 ms into the slot on the replay's clock.
- **The replay's c4:** the sell lands in slot s_in + 4, 75 ms into the slot (s_in = the slot our buy landed in).
- So N − 1 = 4 → **N = 5**, with no TP and no SL.
- The comment in `time_exits` ("lands at buy slot + hold") is off by one slot. I left it as it is (not my code).

## 4. Peak window (`dd15_stageA.py`; SOL from the holdouts R3 + R1 + R4, both servers)

| PKT hour | dumps/h | in envelope/h | Stage A attempts/h | Stage A SOL/h 35 / 50 ms | IMIT1 SOL/h 35 ms |
|---|---|---|---|---|---|
| 00 | 12,498 | 2,297 | 36 | +0.81 / +0.62 | −0.43 |
| 01 | 17,007 | 3,037 | 62 | +1.22 / +0.30 | +0.46 |
| 02 | 14,898 | 2,707 | 67 | +1.01 / +0.51 | +0.63 |
| 03 | 13,716 | 2,571 | 71 | +0.67 / +0.24 | +0.65 |
| 04–09 | 9,700–13,400 | 1,500–2,400 | 27–50 | +0.36 to +0.79 / +0.12 to +0.56 | |
| 10–15 (weakest) | 6,350–10,100 | 820–1,600 | 13–31 | +0.09 to +0.29 / +0.04 to +0.22 | |
| 20 | 13,517 | 2,638 | 34 | +0.60 / +0.34 | +0.34 |
| 21 | 14,196 | 2,533 | 50 | +0.87 / +0.63 | +0.23 |
| 22 | 12,406 | 2,063 | 48 | +0.78 / +0.68 | −0.10 |

- **Best 3-hour windows:**
  - 00–03 PKT: +4.47 (sum of SOL/h at 35 + 50 ms), but only 1 day of data per hour.
  - 20–23 PKT: +3.90, on 5.7 h of data (the best-covered strong window).
  - 01–04 PKT: +3.96.
- **For the shadow:** now (00:00–04:00 PKT) or tonight 20:00–23:00 PKT.

## 5. Parity and tests
- **Parity file:** `testdata/dip_m2_parity.json` from `dd22_m2_parity.py`.
  - 260 tokens (130 R4 + 130 R3), 61,449 trades as the engine receives them, 9,360 study dump rows.
  - Every tape was rebuilt from phase A and checked equal to the day arrays.
- **Features and score (MEASURED):** 0 feature differences in all 25 features, 0 score differences, worst |Δscore| 0,
  correlation 1.0.
- **Engine path** (IMIT1 book → envelope → M2):
  - 1,741 of the 1,747 study-envelope dumps are scored, 319 of them as extra dumps.
  - Stage A picks: study 136, engine 135, all 135 shared, agreement 99.3%. Without extra dumps it is 80%.
  - The 6 dumps never scored are on one token whose create tx had no buy (the IMIT1 book needs one; an old rule).
  - 2 envelope edge cases come from IMIT1's rounded features.
- **Engine wiring test (shadow and gate):** the dump record carries the study's exact score.
  - Shadow writes the record only after the decision.
  - A token with no state is skipped as `no_history`.
- **Test counts:**
  - Dip lib tests 6 / 6 (the 3 existing + 3 new).
  - Full lib 679 passed, 0 failed, 9 ignored. The old timing failure did not show this time.
  - Engine 27 / 27 (the 25 existing + 2 new).
- **Bundle check (`dd21_m2_bundle.py`):** the bundle's flattened trees, re-scored on all 653,103 rows, equal the study's
  predictions exactly.
  - Floats are stored as strings, because serde_json's default reader can be 1 ulp off; I hit this in a test.
- **`dd20` self-check:** rebuilt from the raw recording, it matches the study's own R4 rows on 3,647 rows.
  - The rest come from a hole in the study's R4 data at 21:01–21:05 PKT (MEASURED): its copy of chunk `txs_1792857624` has
    4,294 trade rows; the raw chunk has 23,984. R4 results are slightly affected (5 of its 196 minutes).

## 6. Timing (MEASURED, local release build)
- Per scored dump (state update + 25 features + 2,355 trees): **p50 26–28 µs, p99 30–40 µs**. Single outliers reached
  175 µs to 1.4 ms.
- Per trade: O(1) amortised.
- A trade out of chain order is inserted in place. The token's state is then replayed at its next scored dump, which in
  shadow mode is after the send.
- Live timing is in each record (`m2_us`) and in the status line (p50 / p99 of the last 4,096 dumps).

## 7. How to run (not deployed; the coordinator deploys)
Copy the binary and the bundle to the server, e.g. bundle → `/root/dip/m2_v3_reg4_top25.json`.

**`run_dip_prod.sh` was NOT changed (ops/prod is off limits):**
- It hardcodes `B=/root/sniper-dip/snipe_engine_dip10`.
- It has no M2 option. The flag has to be added to its engine line (or the engine started by hand).

**Shadow:** add one flag to today's engine command. Trading stays IMIT1.
```
--dip-m2 /root/dip/m2_v3_reg4_top25.json
```
- Defaults: mode shadow, min 0.010095262901162569, extra dumps on.
- Every in-envelope `dump` record gets `m2`, `m2_pick`, `m2_min`, `m2_feats` (the 25 values), `m2_us` and `m2_mode`.
- When they apply it also gets `m2_extra`, `m2_skip`, `m2_gaps` and `m2_reorders`.
- One line per would-be pick: `DIP M2-SHADOW pick ...`.
- The status line ends with `| M2 shadow: scored N picks N (IMIT1 also N; extra dumps N picks N) skipped {...} | p50 / p99 us`.

**Gate (later, owner OK):**
```
--dip-m2 /root/dip/m2_v3_reg4_top25.json --dip-m2-mode gate --dip-hold-slots 5 --dip-tp 99 --dip-sl 1.0
```
- With the prod script: `--hold-slots 5 --tp off --sl 0.5`, plus the M2 flags on the engine line.
- `--dip-m2-min X` changes the threshold. `--dip-m2-extra off` gives today's dump rule.
- Unchanged in gate mode: envelope, near leaders, spacing, launch / vanilla checks, guard, sizes, dev list. IMIT1 is still
  scored and logged; the record carries `imit_pass` and `pass`.

**After the shadow, evaluate parity + replay:**
```
cd /home/moiz/sniper/ops/strategies/dipdetect
python3 dd20_shadow_eval.py --jsonl <dip_rN.jsonl> <dip_ams_rN.jsonl> \
  --run /home/moiz/sniper-data/collect/run_<date>_<time> --from "10-25 01:30" --to "10-25 04:30" \
  --schedule /home/moiz/sniper-data/competitors2/schedule_1067.json --procs 4
```
- The leader schedule for epoch 1067 covers 10-24 22:57 → 10-26 00:12 PKT.
- Tested on R4 hours with run 10's records in plumbing mode (`--fill-m2-from-offline`), because run 10 had no M2.

## 8. Files changed (nothing committed)
- **Engine:**
  - New `src/dip_model.rs`: features, GBDT, bundle loader, 3 tests.
  - `src/lib.rs`: +1 line.
  - `src/dip_imit.rs`: +1 read-only method, `later_in_slot`.
  - `src/bin/snipe_engine/dipmode.rs`: M2 flags, per-token state, hooks, `M2Stats` / `M2Dump`, 2 tests.
  - Only 3 existing statements in `dipmode.rs` changed, all with the same output when M2 is off:
    - the status line has one more placeholder, empty when M2 is off;
    - `let Some(k) = dump_k` became `dump_k.or(extra_k)`, and `extra_k` is always None when M2 is off;
    - the dump record is put in a variable before the same write.
- **Test data:** new `testdata/dip_m2_parity.json` (17.3 MB) and `testdata/dip_m2_bundle.json` (1.1 MB).
- **Scripts (ops/strategies/dipdetect):** `dd15_stageA.py`, `dd16_visible.py`, `dd20_shadow_eval.py`, `dd21_m2_bundle.py`,
  `dd22_m2_parity.py`, `dd23_port_tables.py`, this file.
- **Data (`/home/moiz/sniper-data/strategies/dipdetect/`):** `m2_v3_reg4_top25.json`, `dd15_stageA.{txt,json}`,
  `dd16_visible.json`, `dd23_port_tables.json`, `bin/`, `shadow/test_r4/`.

## 9. Open risks
1. **Live feature parity is not proven yet.** If the feed misses or reorders trades, features differ. They are flagged per
   record (`m2_gaps`, `m2_reorders`), and dd20 measures it.
2. **Train / live skew (INFERRED small):** R2 (training) used real block sizes for 41% of its slots, while live uses 400.
   This affects `since_buy_s` and `since_dump2_s`. R3 / R4 used 400 like live, so the holdout numbers already include it.
3. **Extra dumps are new behaviour in gate mode.** They are about 20% of Stage A picks. The study includes them, but there is
   no live evidence yet; the shadow will give it.
4. **M2 runs on the engine's one decision thread.** In shadow mode its ~30 µs come after the send, but they can delay the
   next trade's handling by about that much. INFERRED negligible next to the landing time.
5. **Log changes with `--dip-m2`:**
   - The status "dumps / in-envelope" counts include extra dumps.
   - In shadow mode a dump record is written after its pick / fire records. The readers I checked match records by mint + sig.
6. **Threshold:** 0.010095 copies the full model's 0.010 operating point, and that 0.010 was not picked on R2-val alone.
   The replay uses 0.55 SOL; live sizes differ.
7. **Wallet identity:** the study keyed wallets by crc32 of their text, the port by their 32 bytes. A collision there is
   about 1e-7 per wallet.

## 10. Not done
- No probe step, no live run and no deploy, by instruction.
- dd20 live parity needs the shadow's records and the recording of those hours. It was tested only in plumbing mode.
