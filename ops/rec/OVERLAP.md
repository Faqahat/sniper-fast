# Overlap test: host recorder vs FRA's collector (10-27 PKT)

**Verdict: PASS.**
- **Same data.** On every slot both recorded, the host recorder produced exactly FRA's data:
  - 8,038 sampled slot comparisons across both FRA runs, and 1,053,239 records, all identical;
  - 96,472 of 96,472 host records identical field for field;
  - creates and skipped slots agree.
- **Tests.** Rotation, gaps, crash/resume, the cut-over and the archive tier passed, on real recorded blocks.
- **Not covered.** A multi-hour full-rate run from the host. Today's keys cannot carry it next to FRA; see below.
- **Recommendation.** Cut over, with the recorder on **its own RPC key** and Constant-K only as a last fallback (section
  4).

## 1. What was run, and why sampled

- **RMR key is dead.** On FRA, 122,767 of 122,771 getBlock calls in 21 h got `429 max usage reached`; the host gets the
  same. FRA silently fails those calls over to Constant-K (CK).
- **SHYFT cannot carry FRA plus a full-rate host.**
  - Smoke test at full rate, 16:34:09–16:35:24 PKT, SHYFT only, 4.83 req/s: 337 contiguous slots, 1,487 txs, and no
    429 on the host.
  - But FRA's SHYFT 429 counter went 1 → 2 in that window, so full rate was held.
- **Public RPCs are out by their published terms:**
  - `api.mainnet-beta` allows 40 calls per 10 s per method per IP (4 getBlock/s; we need 4.69) and 100 MB per 30 s
    (we need ~160 MB).
  - PublicNode's terms forbid "data mining, robots, scraping".
- **E (sampled overlap):**
  - **Load:** every 6th slot on SHYFT, at 0.78 getBlock/s + 0.03 getSlot/s (cap 0.95 req/s, so at most 1 call per
    second). No CK, no RMR.
  - **Comparison:** raw blocks were saved for an exact replay.
  - **Guard:** `guard.py` read FRA's counters every 3 min, read-only.
- **Ran 16:42:54 → 19:22:32 PKT (2 h 40 min).**
  - **Stop:** the guard stopped E when FRA's old run's SHYFT 429 counter went 2 → 5. That happened during FRA's own
    daily rotation (19:10–19:35, two FRA collectors fetching every block).
  - **Before it:** 2 h 27 min with one FRA collector plus the host gave **zero** new FRA 429s.
  - **After it:** with the host already stopped, FRA's two runs still took SHYFT 429s (19:26, 19:32). FRA also had
    7 / 1 / 1 SHYFT 429s in earlier runs that had no host at all.
  - So the trigger was FRA's own rotation load. No rerun (coordinator).
- **Host usage over E:** 7,502 getBlock + 319 getSlot on SHYFT (0.82 req/s), 0 errors. SHYFT returns no
  quota/credit headers (only Date / Content-Type / Length / `Connection: close` / CORS / HSTS).
- **FRA during E:** SHYFT failures +0; CK share 0.671 against a 0.678 baseline.

## 2. Results (`overlap_compare.py`, output in `rec/overlap/E1/compare_final.json`)

| Check | Result |
|---|---|
| Exact replay, FRA run_20261026_1415 | 7,479 sampled slots, 994,808 records = 994,808 recorded by FRA, **7,479/7,479 slots identical** |
| Exact replay, FRA run_20261027_1410 (from 19:10) | 559 slots, 58,431 = 58,431 records, **559/559 identical** |
| Direct: host records vs FRA records | **96,472/96,472 identical** (all fields; `mints`/`tb` list each recorder's own tracked mints and the host's are a subset) |
| Creates in sampled slots | 949 identical; FRA-only 0. 5 host-only, explained by sampling (see below) |
| Skipped slots | 11 on the host = the same 11 on FRA; 0 failed slots on either side |
| Host lag, block to written | p50 36 s (by design in E: getSlot every 30 s). Normal mode polls getSlot every 0.4 s like FRA, so about 7 s + a 10 s sync |

- **How the exact replay works.** Each block the host fetched goes through FRA's own `collect.py` `process_block`,
  with that FRA run's tracked-mint set at that slot, and the output is compared with what FRA wrote. So the host gets
  the same blocks and produces byte-identical records.
- **The 5 host-only creates.** Each mint's first CreateEvent was in a **failed** create tx in a slot the host did not
  sample. FRA logged the create there; the host saw a later attempt.
  - The same rule applies on both sides: FRA's `launches.jsonl` also keeps creates first seen in failed txs, 2.4–3.7%
    of rows, with `err` set.
  - At full rate the host sees the same first event.
- **Data latency for tools on the host.** FRA writes at about 7 s lag, but its data reaches the host only through the
  10-min keeper, and the newest 5-min chunk is partial: 5–15 min. The host recorder writes on the host with a ≤ 20 s
  lag.
- **Cost.** E used 2.7% of a core at 1/6 rate including raw-block saving. Full rate is about 15% of a core and
  ~0.2–0.3 GB RSS; FRA uses 43% of its slower core and 1.1 GB.

## 3. Proven by tests (real recorded blocks served by a local fake RPC; `tests/`, all pass)

- **Rotation:** at the first block at or after 00:00 PKT; `end_slot(D) + 1 == start_slot(D+1)`. A block after
  midnight with an earlier blockTime stays in the new day.
- **Every slot exactly once** in `slots.tsv`, across two SIGKILLs (one at the midnight boundary). Records are
  byte-identical to collect.py's (702 = 702) with no duplicates, and every chunk is a complete gzip.
- **Gaps:** skips (-32007), a failing slot, a transient error and `-32004` are each logged exactly as injected.
- **Limit stop:** a 429 leads to a HOLD file, a clean exit and no restart.
- **Normal mode:** round-robin + failover past a 429-only endpoint (like RMR today); RPC enrichment fields; the
  final pass at rotation. Last-resort fallback endpoints also pass.
- **Cut-over:** start slot + seeded FRA mints + stop slot + resume give records equal to collect.py's (405 = 405).
- **Archive:** FTP/FTPS against a local server (TLS fallbacks, resume, server killed mid-upload, no downgrade), and
  archive → verify → free → fetch → due on ftp, mount and rsync.

## 4. Constant-K: FRA's collector hits the trading key's limits by itself

FRA's collector uses the CK key the engines use: getBlock (about 2/3 of blocks, since RMR is dead), getSlot,
enrichment, and the final pass.

**Per run**, from the keeper copies of the final counters:

| Run | CK getBlock 429 | % of CK getBlock | CK rpc 429 | % of rpc | Final pass reached |
|---|---|---|---|---|---|
| run_20261021_2207 (8 h run) | 183 | 0.20% | 246 | 0.09% | 500 / 25,493 |
| run_20261022_1543 (stopped early) | 707 | 0.57% | 5,509 | 1.33% | (none) |
| run_20261023_1426 | 279 | 0.16% | 179 | 0.04% | (enrich drain) |
| run_20261024_1425 | 387 | 0.15% | 6,530 | 1.50% | 10,100 / 42,408 |
| run_20261025_1420 | 245 | 0.09% | 1,023 | 0.25% | 2,100 / 42,343 |
| run_20261026_1415 | 342 | 0.12% | 171 (+ its final pass now) | 0.04% | ~500 / 53,592 at 19:50 |

**When they happen.** A 1-minute read-only poll of FRA's counters, 10-27 19:24–19:51 PKT:

| FRA phase | CK getBlock/min | 429/min | CK rpc/min | 429/min |
|---|---|---|---|---|
| one collector (steady) | 188 | **0** | 339 | **0** |
| rotation, 2 collectors (daily ~19:10–19:35 PKT, per run) | 191 | **4.8 (2.5%)** | 197 | 0.6 |
| final pass (getTokenLargestAccounts / getMultipleAccounts at up to 20/s) | 0 | 0 | 51 | **16.1 (32%)** |

- **getBlock 429s** come from the rotation overlap. Every run lives through two rotations (≈ 2 × 25 min × 4.8 ≈
  240), which matches the 183–707 per run.
- **rpc 429s** come from the final pass. Constant-K's "veryheavy" class allows 2/s (noted in FRA's own
  `final_pass.py`), and the collector's built-in final pass runs at 20/s. It takes about 16 429s a minute and crawls
  at about 38 mints/min, so 53k mints would need about 23 h. The keeper prunes the run 12 h after its tail, so the
  final pass **never completes**; the old runs stopped at 500, 2,100 and 10,100 mints. It still spends up to 12 h a
  day taking 429s on the trading key.
- **Steady state is clean.**

**Do the engines notice?** Probably not, so far:
- The engines' `POLL-RPC-ERROR` lines (1,363 in AMS r9–r27 and FRA r1–r25) are all `-32016 Minimum context slot has
  not been reached`, which is node freshness, **not rate limits**. There are no 429s in the engine logs. RPC-LAT
  timeouts are on the `bh-*` blockhash-poll endpoints.
- Errors were timed through the slots they name (±1 min) over 7,560 engine-minutes, 10-24 to 10-27. Engine errors
  are **not higher** in FRA's stress windows:

  | Window | Poll errors/min | Timeout lines/min |
  |---|---|---|
  | Rotation | 0.156 | 0.011 |
  | Final pass | 0.100 | 0.022 |
  | Rest of the day | 0.187 | 0.028 |

- Caveats: the history of FRA's 429 times is inferred from the daily schedule (poll data exists only from 19:24 on
  10-27), and there are few engine-minutes inside the windows (180 and 539).

**Recommendation to the owner:** after the cut-over the host recorder should use **its own RPC key**, and keep
Constant-K only as a last fallback, so recording can never eat the trading key's limit.
- Built and tested: `REC_BLOCK_EPS=SHYFT_RPC_URL,NEW_RPC_URL`, `REC_RPC_EP=NEW_RPC_URL`, `REC_BLOCK_FALLBACK=CK`,
  `REC_RPC_FALLBACK=CK` (`NEW_RPC_URL` in `/etc/sniper-rec/env`).
- Already fixed in the host recorder: the final pass is paced at 1.8/s (Constant-K's heavy limit). On CK it would
  finish in ~8 h (00:00 to ~08:00 PKT) instead of never.
- There are no rotation overlaps on the host (one continuous process), so the daily rotation 429 burst disappears.
- Without a new key, the host on CK (normal mode) puts the same steady load on CK as FRA does today: about 3.2
  getBlock/s + 5.6 rpc/s, which ran with 0 429s above. Its final pass is a slower 1.8/s instead of FRA's 20/s
  burst.

## 5. Cut-over (owner decision)

Avoid 19:05–19:40 PKT, when FRA rotates its runs.

Pre-checks:
- `rec status` on the host: the HOLD present is the manual one, and disk is below 85%.
- FRA's collector is healthy (`bash ops/collect/health.sh`).

The CK key already works from the host IP: host research tools use the same key on rpc-frankfurt
(`~/.config/sniper/ck_rpc_url`). It was not called during the overlap.

If the owner gets a recorder key first, put it in `/etc/sniper-rec/env` as `NEW_RPC_URL` and add the four lines
from section 4 to `rec.conf` in step 3.

1. **Stop FRA's collector** (FRA):
   ```
   ssh -p 1996 it@84.32.100.36
   sudo touch /root/sniper-collect/ROTATE_OFF                 # rotate.sh (cron */5) will not start a new collector
   R=$(sudo cat /root/sniper-collect/current_run); echo $R
   sudo pkill -TERM -f '^python3 -I collect.py$'               # no final pass; its last chunk ends without a gzip trailer (readable up to the last line)
   sudo python3 -c "import json; print(json.load(open('/root/sniper-collect/$R/status.json'))['last_slot'])"   # = L
   ```
2. **Final keeper copy** (host): `bash /home/moiz/sniper/ops/collect/keeper.sh`. The stopped run stays on FRA, because
   it is still `current_run` and the keeper never prunes that.
3. **Start the host on CK + SHYFT like FRA** (host):
   - It starts 300 slots before L, so the slots in between are fetched from RPC history and recorded by both: no gap.
   - It keeps following FRA's mints.
   ```
   L=<from step 1>; R=<from step 1>; TODAY=$(TZ=Asia/Karachi date +%F)
   sudo sed -i -e 's/^REC_MODE=.*/REC_MODE=normal/' -e 's/^REC_EXPECT_RUNNING=.*/REC_EXPECT_RUNNING=1/' -e "s/^REC_LINK_FROM=.*/REC_LINK_FROM=$TODAY/" /etc/sniper-rec/rec.conf
   printf 'REC_START_SLOT=%s\nREC_SEED_LAUNCHES=/home/moiz/sniper-data/collect/%s/launches.jsonl\n' $((L - 300)) $R | sudo tee -a /etc/sniper-rec/rec.conf
   rm /home/moiz/sniper-data/rec/HOLD
   sudo systemctl enable --now sniper-rec.service
   ```
4. **Watch** (first 30 min):
   - `rec status` shows the lag falling to about 7 s. It catches up from history at up to 18 getBlock/s.
   - `tail -f /home/moiz/sniper-data/rec/logs/recorder.log` shows "FRESH START ... at slot L-300" and "seeded N mints".
   - `rec check $TODAY` reports `slots.tsv` as contiguous.
   - The watchdog is quiet (Telegram).
   - The first host day is partial (from L-300). Its first ~1–1.5 min are also in FRA's last run.
5. **Then turn the keeper's copying off** (host):
   ```
   bash /home/moiz/sniper/ops/collect/keeper.sh && kill $(cat /home/moiz/sniper-data/collect/keeper_loop.pid)
   sudo sed -i '/^REC_START_SLOT=/d; /^REC_SEED_LAUNCHES=/d' /etc/sniper-rec/rec.conf    # only used on a fresh start; tidy
   python3 -I /home/moiz/sniper/ops/rec/rec.py link                                     # collect/run_YYYYMMDD_0000 -> today's host day
   ```
   - FRA's stopped run (about 13 GB on FRA) can be deleted later, by the owner.
   - Its final pass did not run. It is optional, and slow on CK.

## 6. Rollback (anything off: alerts, lag, errors)

1. **Host, stop and hold:**
   ```
   sudo systemctl stop sniper-rec.service
   python3 -c "import json,time; json.dump(dict(reason='rollback to FRA', by='owner', t=time.time()), open('/home/moiz/sniper-data/rec/HOLD','w'))"
   sudo sed -i 's/^REC_EXPECT_RUNNING=.*/REC_EXPECT_RUNNING=0/' /etc/sniper-rec/rec.conf
   ```
2. **FRA, start the collector again.** It starts a new 24 h run now, at the tip. Note its `start_slot` = S.
   ```
   sudo rm /root/sniper-collect/ROTATE_OFF && sudo /root/sniper-collect/rotate.sh
   ```
3. **Host, keeper copying back on:** `setsid nohup bash /home/moiz/sniper/ops/collect/keeper_loop.sh > /dev/null 2>&1 &`
4. **Backfill the gap** from the host's last slot to S−1, from RPC history.
   - SHYFT only at ≤ 0.95 req/s; no CK, since FRA runs again. This is the load proven safe in E.
   - The recorder resumes at its last slot + 1 and stops cleanly at S−1. A 10 min gap takes about 50 min.
   ```
   sudo sed -i 's/^REC_MODE=.*/REC_MODE=overlap/' /etc/sniper-rec/rec.conf
   printf 'REC_STOP_SLOT=%s\nREC_RESUME_MAX_H=48\nREC_EP_TOTAL_RPS=0.95\nREC_BLOCK_RPS=0.95\nREC_RPC_RPS=0.95\n' $((S - 1)) | sudo tee -a /etc/sniper-rec/rec.conf
   rm /home/moiz/sniper-data/rec/HOLD && sudo systemctl start sniper-rec.service     # ends with a HOLD "REC_STOP_SLOT reached"
   sudo sed -i '/^REC_STOP_SLOT=/d; /^REC_RESUME_MAX_H=/d; /^REC_EP_TOTAL_RPS=/d; /^REC_BLOCK_RPS=/d; /^REC_RPC_RPS=/d' /etc/sniper-rec/rec.conf
   ```

## 7. Files

| What | Where |
|---|---|
| E data | `/home/moiz/sniper-data/rec/overlap/E1/` (days/, raw/ = 4.1 GB raw sampled blocks, logs/guard.log, compare_final.json). A test artifact, kept until the owner says it can go. |
| FRA counter polls | `/home/moiz/sniper-data/rec/state/fra_poll.jsonl`; report with `ops/rec/fra_poll_report.py` |
| Test outputs | `/home/moiz/sniper-data/rec/test/` (replay_run6.txt, final_suite.txt, archive_run4.txt) |
