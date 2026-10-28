# E2X1 DISSECT — shared brief for every analyst agent (10-28 ~20:20 PKT)

Wallet: **E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb** (GMGN: https://gmgn.ai/sol/address/E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb)

## The owner's request (his words, condensed)
> Like we analyzed haqq — every single bot/strategy broken down — do this wallet. **Especially his selection.**
Standing owner requirements carried over from the haqq dissection:
- validate everything; if numbers don't add up, dig until they do; act like analysts and prove every claim with numbers;
- give each bot / strategy type a short NAME;
- every claim backed by **at least 5 example trades with GMGN token links** (https://gmgn.ai/sol/token/<mint>) and solscan tx links;
- **exact per-bot P&L over 24 h**, whose sum must reconcile to the wallet's balance change minus/plus transfers (to the lamport);
- find which of his strategies is **closest to ours** (must appear on tokens we trade) and how it differs;
- final deliverable is an HTML playbook of what we can use, with figures and proofs.

GMGN screenshot (owner, 10-28 ~20:15 PKT, his last ~30 min): tokens 13–31 min old; buys/sells 1/1 to 4/4 per token;
holds 1 s to 1 min (one 23 min bag-hold POOCOIN −38%); position sizes ~$25–$330 (~0.15–2 SOL?); winners +30% to +62%
(TIT +61.6% 2/2 held 6 s, Chroma +52% 2/2 1 m, TIT +54.7% 1/1 1 m, S&P500 +38.9% 1/1 2 s, NOCAP +32% 2/2 33 s), losers small
(−1.5% to −8%) except ZENO −68% (3 s) and POOCOIN. So: mostly winners with big %, short holds, tokens past launch (13–31 min).

## Our context (what "us" means)
- Our live strategy is **pre-send dip buying**: when a wallet buys ≥6% of a pump.fun token, we pre-send buy orders (0.45 SOL,
  8 tries/slot, price limit 0.88×) that fill only if the whale dumps within 10 slots; we sell 200 ms after the fill.
  ~+2–3 SOL/day. Live runs: FRA r27/r28 records /home/moiz/sniper-data/runs/fra/runs/dip_r2{7,8}.jsonl; AMS runs
  /home/moiz/sniper-data/runs/ams/runs/.
- Our measured landing: a reactive buy lands ~60–90 ms after the trigger (median), pre-send lands ~20 ms after the dump.
- We already dissected haqqiUUX (7 bots, +28 SOL/day; selection was the edge and NOT reproducible from on-chain features):
  /home/moiz/sniper/ops/strategies/haqq_dissect/ (FINDINGS.md, BOT_SPOTCHECK.md, */REPORT.md). Reuse its tooling:
  recon/ (rpc.py public-RPC client with 429 backoff, txparse.py, r1_sigs.py, r2_fetch.py, r6_recon.py lamport reconciliation,
  r7_bots.py bot split by CU-price code), bots/, exit/ (xlib.py, xsim.py), verify/vlib.py (Tape class).

## Data (READ ONLY)
- Raw recordings of every pump.fun tx (recorder, ~17 GB/day): /home/moiz/sniper-data/collect/run_*/txs/*.jsonl.gz
  (10-27 14:10 → 10-28 14:05 UTC complete; 10-28 run in progress on the FRA server
  ssh -p 1996 it@84.32.100.36 /root/sniper-collect/run_*/txs/ — read only, sudo). Line fields: s, i, bt, sig, err, fee,
  cup (CU price), signers, ixn, ev (event bytes; decode with /home/moiz/sniper/ops/strategies/presend/real/decode.py
  chunks_of + parse_trade → mint, sol, tok, is_buy, …, vsol, vtok), tb/sd (token/SOL balance deltas), tips.
  KNOWN GAP: the recorder misses "version 1" txs (some routers, e.g. FLASHX8D) — ~3.5% of trades. Fill gaps for this
  wallet from public RPC (getSignaturesForAddress + getTransaction), as the haqq recon did.
- Public RPC only (https://api.mainnet-beta.solana.com, ≤0.5 getTransaction/s). Never use the Constant-K key
  (~/.config/sniper/ck_rpc_url) for research. Never print secrets.

## Rules
- Times in PKT (UTC+5). Label MEASURED vs INFERRED. Plain, short reports.
- Local disk is at 87% (~41 GB free): keep each agent's outputs < 2 GB; delete only your own regenerable intermediates.
- Each agent writes ONLY in its own folders: code + report in /home/moiz/sniper/ops/strategies/e2x1_dissect/<agent>/,
  data in /home/moiz/sniper-data/e2x1_dissect/<agent>/, scratch in
  /tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/e2x1_<agent>/. No bulk deletes elsewhere.
- No live sends, no server writes, no deploys, no engine changes.
- Shared lot table (once recon writes it): /home/moiz/sniper-data/e2x1_dissect/recon/lots.parquet or .pkl — read its README.
