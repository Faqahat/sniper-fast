# dipshadow: what a live dip engine can see, and how the dip pros trade (2026-10-23, analysis only)

All read-only: local collector data, plus read-only RPC on the owner's endpoint (`~/.config/sniper/ck_rpc_url`, never printed). Nothing is sent.

| Script | What it does | Output |
|---|---|---|
| `fetch_sample2.py`, `variants.py` | 1,500 random pump trades: share with a top-level pump instruction; layouts of the top-level variants | `sample_txs2.jsonl` (76% routed) |
| `trig_sigs.py` | trigger tx (the big sell) of each dip event, plus who traded right after it and how fast (block-position proxy) | `trig_sigs*.jsonl` |
| `fetch_trig.py`, `trig_analyze.py` | RPC truth for 7,719 trigger txs: direct (top-level) or routed, by pick set, router list, backrun speed | `trig_tx.jsonl` |
| `scan_progs.py`, `direct_rule.py` | direct/routed label for all triggers from the collector's `progs` (99.8% vs truth) | `direct_flags_prelim.json` (for `dip/dipcv.py` DIRECT_FILE) |
| `trig_decode.py` | validates the shred-side decoder of the 3 direct sell layouts on 800 real triggers | `trig_decode.json` |
| `scan_rows.py`, `backrun_paths.py` | how backrunners send: landing service (tip account), tip, priority fee, direct or own program | `backrun_rows.jsonl` |
| `leaders_host.py` | leader schedule + client class for the data period | `leaders_book.json` |
| `dip_census.py` | every dip backrunner's real round trips: P&L by wallet, delay, hold | `dip_census.json` |

Findings: `ops/dip/PLAN.md`, sections from "KEY engine finding" on.
