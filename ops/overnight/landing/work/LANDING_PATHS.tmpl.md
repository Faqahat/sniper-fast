# Landing paths for pump.fun snipe buys: which ones land first (2026-10-23)

Read-only study of on-chain data we already collected. Nothing was sent or traded, and nothing on the server was changed. The RPC was used read-only: 82 getSlotLeaders calls, 1 getClusterNodes call and 1,781 getTransaction calls, at 6 requests a second or less.

**Labels.** MEASURED = counted from the data. INFERRED = my interpretation of the data, not proven.

## Bottom line

- **No single service lands first everywhere. The winner depends on the leader's client.**
  - The best snipers handle this the same way: they sign one copy of the buy per service, each copy carrying only its own tip, all on the same durable nonce. Only one copy can land.
    - This is INFERRED from three things: a nonce in their sampled transactions, landed copies that switch between single-service paths, and no double buys.
  - MEASURED: the 20 fastest consistent snipers use a durable nonce in 97 of 98 sampled transactions. They land through 2 to 6 services each; 16 of the 20 use 4 or more.
  - Their landed copies by path: no tip (priority fee only) 29%, helius 21%, astralane 11%, jito 10%, speedlanding 8%, nozomi 8%, landx 7%.
  - Our engine does it differently. `--multi-send` and `--route-by-client` send ONE transaction, with a recent blockhash and no nonce, that carries every path's tip.
    - Source: `src/bin/snipe_engine.rs`, `lat::build_tx`.
    - So every landing pays all the tips, and every path carries the same transaction.
- **Head-to-head races inside the same bots** (150 nonce fan-out wallets, same wallet and same leader client). MEASURED win shares; reading them as races is INFERRED.
  - **BAM and Jito-Solana leaders (61% of slots):** Helius Sender wins 73% and 64% of head-to-heads. It beats Jito 64% of the time, speedlanding 80%, nozomi 78% and astralane 78%. It is even with LandX (52%).
  - **Harmonic leaders (30% of slots):** speedlanding wins 75% (71–89% against each rival). Nozomi is second at 60%.
  - **Firedancer leaders (7% of slots):** astralane wins 71%. A priority-fee-only copy and LandX each win 62%.
- **Across all buys** (35k outside buys, MEASURED), LandX lands earliest of the paths with 500 or more buys:
  - 70% in the create slot, median 41 ms after the create;
  - first outside buyer 2.25× as often as its share of buys.
  - Part of this is who uses it (AKbot-type bots with ~1% tips and nonces). In head-to-heads LandX is about even (49%).
  - Three small services (node1, soyas, stellium; 60–210 buys each) look as early. Their samples are small and they lose most head-to-heads.
- **Consistently late:** 0slot, blockrazor, nextblock, rpcfast, lunar and falcon. MEASURED: 13–35% in the create slot, medians of 125–223 ms. One transaction carrying several tips (`multi:helius+jito`) is no better: 35% and 168 ms.
- **The bar to beat.** The 20 fastest consistent snipers land a median 39 ms after the create (p25 24 ms) and are in the create slot 78% of the time. By client:
  - BAM 34 ms;
  - Jito-Solana 48 ms;
  - Harmonic 52 ms;
  - Firedancer 30 ms.
  - Our live buys landed at 73–75 ms (Run 2; only 2 fills).
- **What 74 ms costs us** (MEASURED on the R2 launches):
  - On contested launches (3 or more outside wallets in S..S+1), a buy landing at 74 ms is the first outside buyer only 33% of the time, with 1.7 outside buys ahead on average.
  - At 40 ms it would be first 54% of the time; at 30 ms, 71%.

## Recommendation (needs the owner's OK: this changes the send path)

1. **Switch from one multi-tip transaction to durable-nonce fan-out.**
   - Sign one copy per path, each with only that path's tip, all on the same nonce.
   - Only the first copy to arrive can land, so we pay one tip, not all of them. That part is INFERRED from how nonces work.
   - MEASURED: the 150 fan-out wallets show no double buys: at most 5% of their launches have a second buy, and the biggest ones have 0.
2. **Paths: three main ones, chosen by the create-slot leader's client** (`--route-by-client` already exists).
   - **Helius Sender, on BAM and Jito-Solana leaders (61% of slots).**
     - Head-to-head: 73% (BAM) and 64% (Jito-Solana).
     - Sniper-sized buys: 62% in the create slot, 51 ms.
     - Cheap: winners tip a median 0.001–0.002 SOL (about 0.2–0.3% of size).
   - **LandX, on every client.**
     - Earliest absolute landings: 74% in the create slot and 37 ms for sniper-sized buys.
     - By client: BAM 81% / 33 ms, Firedancer 90% / 17 ms, Harmonic 57%.
     - Wins head-to-heads on Harmonic (55%) and Firedancer (62%).
     - Its users tip about 1% of size (median 0.0175 SOL on buys of 0.5 SOL or more). Whether a smaller LandX tip still lands this early is untested.
   - **speedlanding, on Harmonic leaders (30% of slots).**
     - Head-to-head: 75%.
     - Population: 52% in the create slot at 59 ms on Harmonic, the best median among the big paths there.
     - Tip about 0.001–0.003 SOL.
     - We have no account yet. Until we do, keep **nozomi** on Harmonic (60% head-to-head there).
   - **Cheap extras:**
     - astralane on Firedancer (71% head-to-head);
     - a priority-fee-only staked-RPC copy everywhere. Sniper-sized no-tip buys land 60% in the create slot at 40 ms, with about 0.5% of size as priority fee.
   - **Jito bundles:** only on BAM and Jito-Solana, and only with a real tip. Big buyers tipping about 1.5% of size land 76% in the create slot at 42 ms. Jito-tipped buys on Harmonic and Firedancer leaders land late (31% and 25% in the create slot).
   - **Drop or never add:** 0slot, blockrazor, nextblock, rpcfast, lunar, falcon.
3. **Expected result.** INFERRED: our decision already fires 2–5 ms after we see the create (measured earlier). If the paths deliver for us what they deliver for the fan-out bots:
   - median landing about 35–50 ms instead of 74;
   - in the create slot about 70–85% of the time;
   - first outside buyer on roughly 45–70% of contested launches instead of 33%.
   - This is not measured for our own sender. Per the "measure, don't infer" rule, validate it first (step 5).
4. **Cost per landed buy.** One tip plus one priority fee:
   - about 0.3–0.6% of a 1 SOL buy when Helius or speedlanding wins;
   - about 1–1.3% when LandX wins at its users' tip level;
   - today's multi-tip transaction costs about 2% of size, because it pays every path's tip on every landing.
   - Copies that fail never land (nonce), and a failed transaction's tip reverts. That part is INFERRED from how nonces and failed transactions work.
5. **Validate before going live:** a capped probe run.
   - Each probe is a buy-shaped transaction with `min_out = u64::MAX`, so it fails on slippage.
   - Send one copy per path on the same nonce. The copy that lands tells us which path won *for our sender*, and when, against the real buyers.
   - Cost: the priority fee on the one copy that lands; tips revert.
   - Spread about 60–100 launches across the leader clients. Include the tip level as a lever (for example LandX at 0.3% vs 1%), because tip effects cannot be separated in this data.

## The numbers

### 1. Per path: all buys, sniper-sized buys, and head-to-head races (MEASURED)
- **Columns 2 and 3:** in-create-slot %, then median ms (our feed's clock, 10-22 17:10 UTC onward), then first-buyer ratio (share of first outside buys ÷ share of all buys) or tip as % of size.
- **Head-to-head:** within the same nonce fan-out wallet and leader client, this path's share of the races it was in. Wallet-majority = the share of wallet×client cells where this path won more often.

{{S1}}

How to read it:
- **Population numbers mix the path with its users.** Helius carries 31% of all buys, mostly small retail-bot buys with a median size of 0.10 SOL, and looks slow (34% in the create slot, 139 ms). The same path on sniper-sized buys does 62% and 51 ms, and it wins most head-to-heads.
- **LandX looks best in the population** but is only even head-to-head.
- **Head-to-head win share alone is not enough:** rpcfast and 0slot "win" races only among slow copies. Their winners land in the create slot 7% and 20% of the time.

### 2. By the leader's client (MEASURED; leader = getSlotLeaders, client = getClusterNodes clientId)

{{S2}}

- Jito-tipped buys only work where Jito bundles can land (BAM, Jito-Solana, Rakurai): 51–57% in the create slot and 68–85 ms there, against 25–31% and 166–284 ms on Harmonic and Firedancer.
- Every path is slower on Harmonic.
- Full cross tables are T3/T3b (client), T5 (region) and the race matrices under T13 in the appendix.

### 3. What landing time buys (R2 launches with our engine timeline, MEASURED)

{{S3}}

Where the best actually land (first buy per launch):

{{S4}}

- **Create position matters a lot.** For the top 20, a create in the first third of its block gives them the create slot 96% of the time. A create in the last third gives 48% (T4 and T16).
- Our engine's "create in slot" gate is the right idea.

### 4. Nonce and tx format
- **Durable nonce goes with early landing** (MEASURED correlation).
  - Random sample of OK buys: nonce users land 45% in the create slot (median 110 ms); non-nonce users land 22% (147 ms).
  - Top 20 snipers: 97 of 98 sampled transactions use a nonce.
  - My reading (INFERRED): the nonce lets a bot race several services without double buys. It is not faster by itself.
- **v1 transactions** (fee in the header, no compute-budget instructions) also go with early landing: 55% vs 35% in the create slot.
  - Within the same wallet and path the difference vanishes: −1.5 pp, but only 16 cells (T14). So v1 marks the users; it does not make the transaction faster (MEASURED, small sample).
  - My v1 test (no compute-budget instruction and fee above base) agreed with the RPC `version` field on all 164 transactions it flagged, and missed 35 v1 transactions.

### 5. Failed transactions (T11)
- **Volume:** 406k failed outside transactions sit in S..S+3, against 35k OK buys.
  - 82% of the failures come from 20 spam payers.
  - Most never reach pump.fun: the bot's own guard program aborts.
- **Path of failed buy instructions** (RPC sample: 400 failed buy instructions plus 300 guard fails), scaled up, as a rough fail rate of buy attempts:
  - Helius about 71%, LandX about 77%, nozomi about 73%, no-tip about 59%;
  - astralane about 22%, Jito about 10%, speedlanding about 15%. The last three rest on only 1–7 sampled failures.
- These rates mostly describe the bots, not the paths. AKbot-style LandX users try every launch of a followed dev and fail on slippage when someone lands first.
- A failed buy costs only the fee: the tip reverts.

### 6. Representative transactions (sniper-sized, create-slot, near the path's median ms)

{{S5}}

## Confounders and limits

- **Population numbers mix the path with the sender.** The user's detection speed, location, buy size and launch choice all differ by path.
  - Helius is retail-heavy; LandX is AKbot-heavy.
  - The head-to-head table is the cleanest comparison, but:
    - it assumes each bot sends all its copies at the same moment;
    - we only see winners, so a path a bot uses but never wins with is invisible;
    - each bot's tip differs by path;
    - a few large bot families dominate the race counts. The wallet-majority column and the R1 vs R2 split (helius 64% / 65%, speedlanding 53 / 46, landx 54 / 49, jito 47 / 52, nozomi 44 / 41) show the result is stable.
- **Tip size could not be isolated.**
  - Inside the same wallet, path and client, the buys with higher fees landed *later* (−11 pp in the create slot), because bots raise fees on hot or late launches.
  - This does not show that fees don't help. Treat the tip as a lever and test it (step 5).
- **Where the ms figures come from.**
  - ms values exist only for R2 from 10-22 17:10 UTC on: 9,354 buys.
  - 15% of create-slot outside buys could not be matched to our engine's timeline. These are mostly buys through router programs (5DVzy5Ep…, ENFJAVp6…, L2TExMFK…).
  - Side finding (INFERRED): the engine's RACE obs may not see some fast competitors. That would also undercount competitors in any gate that counts outside buyers.
- **Our own landing is barely measured.** We have 2 live fills since Alpenglow (73 and 75 ms). The earlier single-route probes (nozomi 25, staked-rpc 27, landx 30, helius 32, Jito bundle 53 ms) were tiny and pre-Alpenglow.
- **Leader clients** come from today's getClusterNodes; some validators may have changed client during the runs.
- **Create position** is a proxy: the create's index ÷ the highest index we saw in that slot.
- **Window.** About 24 h of data (R1 10-21 22:07 → 10-22 13:00 and R2 10-22 15:43 → 10-23 00:35 UTC). Only SOL-quoted launches are counted: 6,898 buys on other-quote curves are left out because their amounts are in quote-token units.
- **The creator side is excluded:**
  - the creator, the create's signers and payer;
  - the "glued" bundle: OK buys at consecutive block indexes right after the create. The Jito bundle decided membership when known (1,712 creates). Otherwise a known multi-launch sniper (471 found in the data plus 591 from pros.json) breaks the run.
  - Dev side-wallets that land elsewhere can still look like fast "snipers", which is why T2/T2b keep repeat wallets only.

## Method and files

All files are in `/home/moiz/sniper/ops/overnight/landing/`. Run them in this order with `python3 -I`. Everything is read-only.

| File | What it does |
|---|---|
| `l0_leaders.py` | getSlotLeaders for both runs' slot ranges plus getClusterNodes. The URL is read from `~/.config/sniper/ck_rpc_url` and never printed. |
| `l1_scan.py` | Scans 300 collector chunks (72.7M lines) and keeps every transaction touching a new mint in S..S+4: 966k records. Tips are recomputed from balance deltas with `tipmap.json`, and pump.fun TradeEvents are decoded. |
| `l2_build.py` | Per launch: creator side, glued bundle, outside buys and failed transactions; path, position, leader and client; create position; match to engine-timeline ms. |
| `l3_rpc_sample.py` | getTransaction sample: nonce, version, and the tip accounts of failed transactions. |
| `l4_report.py` | All tables (`work/tables.md`) and `landing_stats.json`. |
| `l5_summary.py` | The summary tables above. |
| `l6_assemble.py` | Builds this file from `work/LANDING_PATHS.tmpl.md` plus the generated tables. |

Intermediate files are in `work/`: the scan, rows, the RPC cache and the logs.

**Definitions:**
- **Path** = the services of the tip accounts a buy paid. "none" = no known tip account: priority fee only, or the tip was in another transaction.
- **Position** = OK outside buys ahead in chain order.
- **ms** = the buy's arrival in our engine's shred feed minus the create's arrival. This is the same clock as our 73–75 ms live landings.

## Appendix: all generated tables

{{TABLES}}
