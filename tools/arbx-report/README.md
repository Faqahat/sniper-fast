# arbx-report

The analysis toolkit of arbx (docs/PLAN.md WP-10, design in docs/MEASUREMENT.md §6). It regenerates per-segment
and per-campaign reports from the recorded files alone, with MEASUREMENT §6.2's correctness rules: counter
semantics, money from the ledger, rent apart from trading, land rates over sent attempts, acceptance apart from
landing, the landed-only caveat, block-order attribution, and "missing is not zero".

Python 3.10+, standard library only. zstd frames are walked in pure Python. Frames of raw blocks are decoded in
Python too. Compressed frames go to `compression.zstd` (3.14), `zstandard`, `zstd -dc` or Node >= 22.15, in that
order. Node decodes multi-frame files frame by frame, because its stream decoder stops after the first frame.

## Usage

```
python3 tools/arbx-report <command> <segment-dir> [options]        # or: cd tools/arbx-report && python3 -m arbx_report ...
python3 tools/arbx-report segment runs/<campaign>/<campaign>-p3    # every report -> <seg>/report/report.{json,md} + blockctx.jsonl
python3 tools/arbx-report campaign runs/<campaign>                 # campaign.json lists the segments
python3 tools/arbx-report compare <segA> <segB>
```

| Command | Report |
|---|---|
| `quality` | R0 data quality: schemas, producer, recorder drops, replay gaps, exec coverage over D1 ∪ D2, slot index, feeds, commits, unsettled/amends, recon, txfetch/resources/keepalive/probe |
| `ledger` | R1 money from `ledger.jsonl`/`snapshots`/`recon` (identities checked, status counters as a cross-check, toolkit recompute from `wallet.jsonl`); writes `ledger.toolkit.jsonl` |
| `funnel` | R2 hints → commits → evaluations → priced → ≥ min_profit → rejections → sent → first verdict → landed → ok |
| `attempts` | R3 would-fail by band × send delay × leader kind, verdict sequences, accepted → landed, lost auctions, blockhash age, queue |
| `blockctx` | §4.41 `report/blockctx.jsonl`; `--fill-gaps` fetches gap slots through `--rpc-url-env` |
| `attribution` | R4 closers in block order (needs `arbx quote`, WP-09; wins are attributed without it) |
| `latency` | R5 stage decomposition (A.8), commit lag, state-lag SLO, ours vs closers in PoH ms |
| `leaders` | R6 slot share, attempts/accepted/landed by kind, region, client, RTT buckets, landings per 1,000 slots |
| `feeds` | R7 feedhealth, txarr first-arrival shares and delays, dead feeds, slots-feed PoH completeness |
| `predictions` | R8 pre-state exact rates beside the at-hint rate, `pre_state_unknown` counted |
| `rivals` | R9 arbitrage-like transactions, clean wins per signer, tips, senders |
| `experiments [x2\|x4\|size\|margin\|x5\|x8\|x9\|all]` | R10 on a segment or a campaign directory (WP-11): the balance (decisions per arm from status.jsonl's per-arm counters or decisions.jsonl streamed, sends, bands and trigger kinds per arm), per arm attempts / landed / wins with 95% intervals, net per attempt and per win, tips/gross, meme vs common wins, canary_wait refusals, net per hour (net per send x the run's sends per hour), by leader kind and tip policy, each arm against its control (experiments.jsonl `control`) per decision, per send and on Jito-led sends, the factorial's cells; money from the ledger as R1 counts it; X2's two-sided trend; X4's go on the drop's 95% upper bound |
| `census`, `sizes`, `sizefit` | R11 (inputs only until WP-09/WP-12) |
| `caps` | R12 budget tiers deduplicated into gap episodes |
| `cu-table` | per-leg CU samples from venue log lines → `cu-table.json` (§4.48) |
| `compare A B` | R13 provenance diff and metrics side by side |

Options: `--out DIR`, `--offline` (the default unless `--rpc-url-env NAME` names an environment variable holding the
RPC URL; `.env` files are never read), `--quick` (skip big binary/text scans and hashing of files > 64 MiB),
`--arbx-bin PATH` (the WP-09 binary for `arbx quote`), `--match REGEX` (campaign segments), `--stdout`.

arb-lab (v1) runs: `--wallet-txs FILE|DIR` (the wallet's getTransaction results, e.g. WP-00b's `testdata/wallet/`)
or `--chain-ledger FILE` (the research chain ledger) adds the landings the bot never recorded and splits rent;
`--wallet PUBKEY` when `meta.json` is absent.

Reports are deterministic: sorted keys, floats rounded to 9 significant digits, no wall-clock time, inputs listed
by sha256. Every section has `complete`, `incomplete` (reasons), `caveats` and `coverage`. A section that lacks an
input says so and is never approximated.

## Layout

```
arbx_report/
  zstd.py        frame walker, raw-block codec, backends
  streams.py     discovery and rotation, JSON-lines headers and schema versions, text logs, accounts/journal/entries
  solana.py      base58, sig8, wire-message parser, getTransaction / exec records as TxView
  legacy.py      arb-lab v1 records mapped to the v2 model (MEASUREMENT §7) and what is not comparable
  model.py       Segment / Campaign: lazy streams and the joins (attempt, decision, outcome, ledger, verdicts)
  tokens.py      the owner's Stage 0 common-token list by mint (the win mix: meme vs common)
  counters.py    _total / _delta / _now semantics, seq gaps, campaign sums
  ledgercalc.py  §4.42 money by signature from a wallet transaction; ledger and recon identities
  blockctx.py    §4.41 block-ordered route context (windows, shared slots built once, gaps)
  quote.py       `arbx quote` adapter (WP-09) and a table pricer for tests
  chain.py       optional cached, rate-limited RPC (getBlock, getTransaction)
  stats.py       quantiles (also over histograms), money summary with top-1 share, Wilson, bootstrap, Fisher,
                 Mann-Whitney, Cochran-Armitage, chi-square balance
  reports/       r0_quality … r13_compare, cu_table
  runner.py, render.py, __main__.py
tests/           unittest suite; gen.py writes a synthetic v2 segment/campaign; golden/synth-report.json
```

## Tests

```
cd tools/arbx-report/tests && python3 -m unittest discover -s .
ARBX_REPORT_UPDATE_GOLDEN=1 python3 -m unittest test_reports.Golden      # after a deliberate report change
ARBX_REPORT_CHERRY=<scratch cherry root> python3 -m unittest test_legacy  # also the full w5h2/w5h3 window
```

- Synthetic v2 streams for every stream reports use, including multi-frame and truncated zstd files, replay-class
  gaps, `idx_update` lines and amended outcomes.
- The rules: `_delta` summed against `_total` taken last, land-rate denominators, missing-is-not-zero, the §4.42
  golden examples and identities, the recon identity, the coverage denominator D1 ∪ D2, `blockctx` windows and
  deduplication, and R4 on a synthetic block with a single-pool closer, a failed attempted closer and a persisted gap.
- Golden `report.json` of the synthetic segment, byte-identical on re-run.
- Legacy known answers on `testdata/legacy/` (res-pnl p1-p10: trading net -2,337,448, rent 16,383,000 = 15,036,800 +
  1,346,200, profit_lamports -16,201,607, liquid change -18,720,448; the bolt trade). The wallet transactions come
  from `testdata/wallet/` when WP-00b has added it, else from `tests/fixtures/legacy/`.

## Points to keep in step with the Rust side

- `journal.bin` framing: `u8 kind | u32 body_len | u64 seq | u64 t_engine_ns | body`, where `body_len` counts the
  body only (`streams.JOURNAL_BODY_LEN_EXCLUDES_SEQ_T`). WP-03 must write it that way, or flip the constant.
- `accounts.bin` FULL/XOR body as §4.12. Unknown record kinds are skipped by length and counted.
- `arbx quote` CLI (WP-09): `quote.ArbxQuote.net_after` passes `--run --route --version --size` and reads `{"net"}`.
- `attempts.route_in.accounts` carries `{acct, wv}`. R4 maps `(acct, wv)` to `aseq` through accounts.bin. An `aseq`
  field there, if WP-05/06 add one, is used directly.
