# dip45 FLEET SIGNAL shadow (LOG ONLY)

Build dip45 = dip43g + a log-only shadow that recognises the dip "fleet" (one bot, one fresh wallet every ~85 min, ~60 Lighthouse-guarded
pump buys per arm, 0.70 SOL, zero tip) by its **transaction shape**, on the feeds that carry transactions **before execution**
(shreds / entries / deshred), and annotates our arms, fills and the shadow's would-fills with "was the fleet on this token in the
last 1 / 2 / 3 / 8 slots". Spec: `/home/it/sniper-studies/push4-audit/REPORT.md` section 6. Code: `src/bin/snipe_engine/ps45_fleet.rs`,
tests `dip45_tests.rs`, offline checker `ops/fleet45/fleet_check.py`.

**Nothing is sent, armed, skipped, sized or changed.** With the flag off nothing of it exists (golden test: the dip25 digest, byte for byte).

## Flags (each needs `--presend-live`; works with `--presend-live-dry`)
| Flag | Default | Meaning |
|---|---|---|
| `--presend-live-fleet-log on\|off` | off | the shadow (its own thread `fleet-log`) |
| `--presend-live-fleet-sig FILE` | built-in | the signature as JSON (below); checked every 10 s, a change is used at once (record `stage: sig`), a bad file keeps the one in use |

Run command addition: `--presend-live-fleet-log on` (optionally `--presend-live-fleet-sig /root/dip/fleet_sig.json`). NOTE: the run
scripts (`run_dip_prod.sh.*`) pass `--presend-live-*` flags through a whitelist; both flags must be added to it (and to the
"not a number" exemption list).

### Signature (built-in = this file)
```json
{"cu_prices": [32000], "cu_price_ranges": [[11000, 13500]], "cu_limit": [40000, 80000],
 "layout": ["cb:02", "cb:03", "cb:04", "lh:02", "lh:0f", "sys:03000000", "t22:12", "pump:e1f7501ed5b38488"],
 "mint_ix": 7, "mint_acc": 1, "max_signers": 1}
```
A tx matches when: <= 1 signer, no lookup tables, exactly these 8 instructions in this order (program alias or base58 id : hex prefix of
the instruction data) = CB SetComputeUnitLimit, CB SetComputeUnitPrice, CB SetLoadedAccountsDataSizeLimit, Lighthouse assert (02),
Lighthouse slot assert (0f), System CreateAccountWithSeed, Token-2022 InitializeAccount3, pump buy. No tip transfer is possible in
this layout. Class **fleet** = layout + CU price in the set / ranges + CU limit in range; class **shape** = layout with another
price / limit (= signature drift; counted, never in the flags). Our own wallet is never counted. Mint = instruction 7's account 1.
Verified on 6 real fleet transactions (CU 32,000 / 12,510 / 11,298 / 13,219, two wallets, one landed buy) and 4 look-alikes
(`testdata/dip45_fleet_fixtures.json`). On 2.5 h of the recorder tape the equivalent tape rule finds 99% of the audit's 17-wallet
fleet tries (17,096 / 17,296) plus one wallet outside that list (BsZpYcBN, 1,071 tries at CU 11,530-11,532, most likely a fleet
wallet the audit's >= 10 buys rule missed).

## Records: `"ev": "presend_live_fleet"`, by `stage`
| stage | when | fields |
|---|---|---|
| config | start | sig, sig_src, err |
| sig | the file changed (or failed: err, kept) | sig |
| fleet_arm | a fleet arm ended (no try on the token for 5 slots) | mint, s0, s1, n (distinct tries), signers, cups [[price, n]], cul [min, max], first {t (wall ns), mono, feed, feed_name, pre, ms_after_slot_start}, slots [[slot-s0, tries, pre-exec, exec, pre-exec seen before the slot ended]], n_slots, slots_pre_by_end, slots_exec_only, per_feed |
| arm / fill | our live (or dry) window armed / filled (from presend_live_arm / presend_live_fill) | w, kind (t2 / rearm / wide), mint, slot (arm: the slot clock at the arm; fill: the landing slot), idx, sig, sol_in, dry, fleet {...}, fleet_arm_open |
| shadow_arm / shadow_fill | the pre-send shadow's paper arm / would-fill (presend_arm / presend_fill / presend_wide_*) | w, kind (shadow:a/b/c, wide:..), mint, slot, dump [slot, idx], fleet {...} |
| follow | 3 slots after a fill / would-fill | of, w, kind, mint, land [slot, idx], dump {slot, idx, sol, user}, first_buyer {slot, idx, sol, user, dslot, dpos, ours_first}, later_buy_sol, later_sell_sol, later_buyers |
| silent / back | no fleet try for 30 min (feed time) / the next try | t, slot, last_try_t, min |

`fleet {...}` = tries (distinct, any feed) in slot S so far (`n0`), in S-1 (`n1`), S-2..S-1 (`n2`), S-3..S-1 (`n3`), S-8..S-1 (`n8`),
of those seen on a pre-exec feed (`pre8`), distinct signers S-8..S (`signers8`), the fleet arm's first slot, the last try slot and the
gap, `on2` / `on8`. "Lead 1" = `on8` (and `on2` for the B1 gate). The flags are the state when the event loop handed the arm / fill
over (records are processed in order on the thread).

DRY run (no real fills): `arm` records carry `"dry": true`; a dry run's "fill" = the shadow's **would-fill** (`shadow_fill`, the
paper fill at the shadow's landing model, its dump = the trade it fills behind; the follow record puts the virtual landing right after
that dump). Real fills are joined offline from the live run by mint + slot (the fleet flags are chain facts, not engine-specific).

Status line part: `| FLEET LOG: tries N (pre-exec, exec, exec-only) slots S (pre-exec by slot end P%) arms A (~D/day) signers30m K
sig P% (shape-only) | ours: arms a/A fills f/F would-fills w/W (fleet in 8 slots) | last try N s ago [SILENT >30 min]`.
run_end: `fleet {...}` totals, signers with first / last time, CU-price histograms (fleet and shape-only), silent periods.

## Pass bars (push4 audit)
- Coverage: **>= 80% of the tape's fleet try-slots seen on the pre-exec feeds no later than the next slot** (`fleet_check.py --tape`).
- Lead 1 (fleet-tilt): **>= 300 real fills; fills with a fleet try in the 8 slots before >= +20 mSOL per fill better; same sign on >= 3 days**.
- Stop / kill for any B1 use: **no fleet-shape try for 30 minutes** (`silent` record, status `SILENT`).

## Offline checker
`python3 ops/fleet45/fleet_check.py --engine dip_fra_rNN.jsonl --tape /data/tapes/collect/run_... --fills dip_ams_r82.jsonl`
prints the engine's detections, coverage vs the tape, the engine's arms / would-fills by flag, and the joined live fills
(n, net, per fill, win share by n2 / n8, T2 vs re-arm, per day, the lead-1 verdict).

## No-key dry run (FRA)
`--presend-live-dry` builds, signs and logs every attempt and never sends; without `--live` the config accepts it. The engine still
loads `wallet_keystore` from `--config` at start (snipe_engine.rs: no keystore = refuse to start): use a THROWAWAY keystore (any new
key, its address as `wallet`, empty / unfunded), never the prod one. The shadow itself needs no key.
Without `--live`, also leave out `--profit-lock` / `--profit-lock-min-sol` (dipmode refuses them: they watch the wallet's balance);
`--max-sol` / `--max-loss-sol` are only required with `--live`. `--regular paper` keeps the reactive path paper. Not yet smoke-tested
end to end on a server (the unit / golden tests run the pre-send probe in dry and live configs only).
