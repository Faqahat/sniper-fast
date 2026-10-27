# BAIT plan — be the first buyer, sell into the bots (2026-10-25)

## What we copy
Wallets like pXGQ6J2z (+21 SOL / 4 days), HRduFFnK (+10), 8XzVYjjV (+10), 3VUNtVtj (+6) — see BAITERS.md.
They buy ~1–2 SOL on a token nobody is trading. Follower bots read it as "someone entering" and buy within 1 slot
(~60–70% of the time). The baiter sells into that buying.

Two entry rules, frozen on 10-24 and confirmed on today's unseen data (replay with real costs):

| Rule | When we buy | Size | Exit | Today (unseen, ~21 h) |
|---|---|---|---|---|
| **Young-token bait** | token 6–25 s old, no trade for ≥2 s, curve ≤45 SOL | 0.9–2 SOL | +8% / −8% / 13 s / into a follower buy or a big sell | +22.9 SOL, 484 baits, 64% win, +0.047/bait |
| **Quiet-token bait** | token ≥32 s old, no trade for ≥8 s, curve ≤40 SOL | 0.75–3 SOL | +8% / −6% / 25 s / into a follower buy, big sell or dev sell | +39.3 SOL, 1,403 baits, 50% win, +0.028/bait |

**Speed does not matter here.** We are the trigger, not the racer, so our ~58 ms landing is fine.
That is the big difference from dip-backrun, where speed is everything.

## The 3 things that decide if it works for us
1. **Fresh wallets.** Bots stop following a wallet that baits again and again: 1st bait 61–67% followed,
   2nd–5th 43–55%, 6th–20th 24–42%, 21st+ 2–7%. → a pool of wallets, each used for only 1–3 baits per day.
2. **Our picks vs theirs.** The replay used other people's baits (they chose the tokens). Only a live probe shows
   if bots follow OUR picks the same way. This is the main unknown.
3. **Size.** Below 0.75 SOL the followers mostly ignore it (41% followed, ~break-even). Keep 0.9–2 SOL.

## Phases

### Phase 0 — paper, free, no risk (1 day, I can start now)
- Paper bait watcher on the 24/7 raw recording (host side; does not touch the servers or the live dip engine):
  every moment our rule would bait, logged with what happened after (real baits by others at the same moment, their
  followers, P&L). Daily replay of both rules on each new day.
- Exit study on fresh-wallet baits: the real winners hold 30 s–3 min, much longer than our 13–25 s. Test longer holds
  and trailing exits.
- Bait size study, both rules running together (one position at a time vs 2–3), hour-of-day profile (PKT).
- Crowding check: how many baits per hour can we add before the followers are spread too thin.
- **Done when:** both rules still positive on each new day; exit and size fixed.

### Phase 1 — build (2–3 days, all on the host repo)
- **Engine `--bait` mode** in snipe_engine, reusing dipmode: same executed feed and TokenBook per token, same buy/sell
  paths, nonce fan-out, guard, budget kill switch, JSONL log. New parts:
  - trigger = a timer that scans followed tokens for the young/quiet state (no outside trade needed);
  - exit on "follower buy" (any outside buy after ours) plus TP / SL / time;
  - one position at a time first (`--max-inflight 1`), `--max-buys`, `--max-loss-sol`, `--minutes` as today.
- **Wallet pool:** N bait wallets derived from one encrypted seed (one keystore; the owner unlocks it once per run;
  the passphrase is never stored). Wallets are funded a few minutes before use (1.05 SOL + fees each) and swept back
  after the sell (token account closed, rent back). Each wallet is used for at most `--bait-uses` baits per day.
- **Checks before any money:** trigger parity vs the Python rule on recorded data; zero-cost `--simulate` buy +
  sell from a fresh wallet; sweep/close tested with 0.01 SOL.
- **Run report:** the standard per-run report (ops/dip/report) plus bait-specific lines: followed within 1 slot?,
  who followed, how much SOL they bought, our exit vs the replay of the same moment.

### Phase 2 — shadow, 2–3 h at peak time
Engine in `--bait` without `--live`: logs every bait it would make. Compare against the paper watcher on the same
moments (same picks, same timing). Runs only when no live engine needs that server.

### Phase 3 — live probe, 30 baits (needs your OK; you start it)
- 1.0 SOL per bait, one position at a time, fresh wallet for every bait, both rules, max loss 1.5 SOL.
- Typical worst case about −1.5 SOL. Expected if bots follow us like they follow others: about +0.03–0.05 per bait
  (≈ +1–1.5 SOL for 30).
- **GO to scale if:** a follower buys within 1 slot on ≥50% of our baits AND P&L per bait ≥ 0 after costs.
- **STOP if:** followed < 40% after 30 baits, or the loss cap is hit.

### Phase 4 — staged scale (same as the dip plan: 30 → 60 → 100 → …)
- One change per run, A/B where possible: wallet reuse (1 vs 3 baits per wallet), size 1.0 vs 1.5, exit.
- Then 2–3 positions at once, both rules all day, second region if crowding allows.
- Target: your ~10–20 SOL/day goal needs ~300–400 baits/day at +0.04. The real baiters each do only 10–20/day,
  so we find out how much the followers can absorb before we get there.

## Risks
- **Followers ignore our picks** (they may react to off-chain news the real baiters saw) → the probe tells us; cheap.
- **Bots learn our wallets** → rotation; bots might also link wallets through the funding source (unknown) → measure
  follower rate by funding pattern in phase 4.
- **Crowding:** ~4,800 baits/day already share the followers; our extra baits share the same money.
- **Rugs / dev dumps during the hold** → dev-sell exit, small curves only, curve-SOL caps as in the rules.

## Decisions I need from you
1. **OK to break the "race pools only" rule** for this strategy (it buys quiet tokens on purpose).
2. **Which server:** a 3rd small VPS (cleanest; the live dip engines keep FRA/AMS), or share FRA with the dip runs.
3. **Wallet + budget:** a new bait seed/keystore, created by you, and how much SOL for the probe (suggest 3 SOL,
   max loss 1.5).
4. **Start Phase 0 + Phase 1 now?** Both are free and touch nothing live.
