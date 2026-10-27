# Instant bots — how buys land right after a pump.fun dump

Agent study, 10-25 ~09:35 → 10:50 PKT. Read-only. Local recording + probe records, read-only RPC (~200 calls, cached),
public Jito bundle API (~1,400 calls, cached). No server touched, nothing sent.
MEASURED = chain rows / recording / API answers. INFERRED = my reading.
- R4 = collector run 10-24 19:25 → 10-25 09:50 PKT (14.5 h). R3 = 10-23 19:26 → 10-24 19:25 (24 h), same pipeline, as a second day.
- Probe = AMS r16, final copy (118 windows, 3,808 attempts, 20 fills).
- Dump = one curve sell that drops the price ≥ 4% by itself, ≥ 0.3 SOL (R4 77,774; R3 137,035).
- Gap = block positions after the dump, same slot.

## Verdict
1. **"They must send far more often than we do" is true for ONE group only.**
   Buys landing 1–10 positions after a dump (what our feed shows as "within ~1 ms"):
   R4 3,451, R3 6,337. MEASURED split (R4 / R3):
   - **Seller's own tool: 38% / 44%.** A sell and a rebuy by sibling wallets, sent together. The price is put back inside the same bundle.
     Not a dip; nothing to catch. (H2 + H4)
   - **Pre-senders: 16% / 14%.** Conditional buys already streaming at 5–85 per slot. One of them is simply next in line. (H1)
   - **Neither: 46% / 43%.** Mostly **chance**: these wallets' buys land just BEFORE dumps almost as often as just after
     (987 vs 1,259 in R4; 1,542 vs 2,200 in R3). Their dumps follow an earlier ≥ 3% sell more often than usual (54% vs 36% of all dumps),
     so some are late reactions to that 1st sell (INFERRED). A Jito check of all 448 such buys at gap 1–3 found 72 in the dump's bundle: ~60 more seller tools, ~12 relay bundles (point 5).
   - **Pure reaction (H5) never lands this close.** The fastest reactive bots (HkQ7, haqqi, DF7e, GKd5, EMKY, 6n2c, G9G3, 8PgC) land ≤ 10 positions
     after a dump in 0.2–1.7% of their follows on both days. Their real wave starts at 11–40 positions (≈ 5–40 ms of leader time).
2. **The probe's "instant bots" were 14 dumps, not 80 landings.** AFrSqSLk 12, nya666pQ 12 … counted OUR repeated landings after the same dump.
   Each named bot was there once. The 19 instant buys:
   - **5 = seller's own bundle.** EcmLLsxm + DrdaADiz: the same Jito bundle as the sell. Fm4KUVJz + BSwWpdoR: the same vault program.
     CUiianSP: first funded by the same wallet as the seller.
   - **3 = pre-sent.** FUru6V3L (19 failed attempts on that token just before) and **our own attempts twice** (EgxfYgEb, +8 and +33 positions).
   - **11 = busy traders**: ssssswdk, AFrSqSLk, nya666pQ, E2x1ewwX, 2zMj6wNq, kBDycuZW, E7LYdw2g, 2Dd3TRSd, BXZ5mXaR, 3Le7cTEL, 84UBp52F.
     No attempts before. Not in the dump's bundle. Near-dump buys are ≤ 3.5% of their buys → chance or a late reaction (INFERRED).
3. **"Within 1 ms on our feed" is a shred-batch effect, not leader time.**
   - Those 19 buys sat 1–37 positions after the dump. Blocks held 190–490 txs per ~212 ms → ≈ 0.5–30 ms of leader time (INFERRED average).
   - Our feed first saw the dump and the buy 0.01–0.2 ms apart (MEASURED): one shred batch.
   - Feed calibration (466 probe pairs, MEASURED): gap 1–10 → median 0.4–0.7 ms on our feed; 11–20 → 1.8 ms; 21–40 → 16 ms; 41–80 → 35 ms.
4. **The real "instant" dip catchers are dense pre-senders (H1)**: 9K5QgBKa, CZ77onJz, FNuoWSQc, Dk2jdQ93, FUru6V3L.
   - 26–85 attempts in one slot; 650–1,700 failed or no-op attempts per fill (both days, MEASURED).
   - 28–53% of their fills land ≤ 5 positions after the dump. Clear dose-response: ≤ 10/slot gives 0–9%.
   - 91–100% of their catches are the token CREATOR's own dump, on tokens 4–12 s old.
   - Their fills are plain txs (0 of 30 sampled in the dump's bundle). No durable nonce. Own check program, CU limit 53–68k.
   - Net −0.6 to +6.6 SOL per run each (mostly positive), after 0.008–0.047 SOL of attempt fees per fill.
5. **A third party bundled with the dump (H2/H3) is rare.** Jito API on ALL 448 "neither" buys at gap 1–3 (Jito/BAM/Harmonic leaders):
   - 72 (16%) were in the dump's own bundle.
   - ~60 were more seller-side tools (fixed CU-limit templates, sizes 25–100% of the sell, tip paid by the seller or the tool).
   - ~12 (3%) were relay bundles: an independent fast bot (DF7eRXHn, EJX629cp, 4oN18efp, 5mWe9kLZ, D1QuMgpv, J3gZFpvs …) sat right behind
     the dump inside a bundle tipped by a relay account ("As…" accounts; INFERRED Astralane). Batching or a backrun service: not separable on chain.
   - gap 6–40: 0 of 24 sampled. Pre-senders: 0 of 30.
6. **Correction to the earlier study:** 9K5QgBKa, CZ77onJz and FNuoWSQc do NOT have "few failed txs" (MEASURED).
   - R4: 64,066 / 54,499 / 11,300 failed attempts, plus 311 / 60,100 / 5,591 attempts that succeed doing nothing.
   - The earlier census counted only failed txs that contained the pump program.
   - Theirs fail inside their own program before pump is called (9K5QgBKa: error 7002 at ix 3, ~1.9k CU), or succeed as no-ops.

## For us
- **Our probe (MEASURED):**
  - 3.8 attempts per armed slot, 190 attempts per fill, 5,120 lamports each = 0.00096 SOL of failed fees per fill.
  - We landed a median 53 ms after the crossing trade; 1% within 5 ms of the dump.
  - Twice our own attempt was the "instant bot".
- **What landing ≤ 5 positions takes (MEASURED on the pros, R4 / R3):**

| Bot | Max attempts in a slot | Attempts per fill | Fills ≤ 5 positions | Attempt fees per fill (SOL) | Net SOL |
|---|---|---|---|---|---|
| 9K5QgBKa | 85 / 78 | 1,073 / 1,244 | 50% / 53% | 0.027 / 0.028 | +2.3 / +4.9 |
| CZ77onJz | 69 / 65 | 1,710 / 1,575 | 48% / 50% | 0.038 / 0.047 | −0.6 / +1.9 |
| Dk2jdQ93 | 49 / – | 981 / – | 42% / – | 0.012 / – | +2.0 / – |
| FNuoWSQc | 60 / 51 | 1,206 / 819 | 36% / 32% | 0.014 / 0.010 | −0.2 / +4.8 |
| FUru6V3L | 26 / 26 | 856 / 651 | 34% / 28% | 0.011 / 0.008 | +3.9 / +6.6 |
| 5ZKd8DNB | 47 / 37 | 605 / 538 | 9% / 15% | 0.005 / 0.004 | +3.9 / +7.3 |
| 2KtcBCfh | 10 / 9 | 504 / 172 | 3% / 2% | 0.003 / 0.003 | +4.4 / +1.2 |
| CVPz447t | 5 / 5 | 195 / 183 | 3% / 4% | 0.001 / 0.001 | +2.6 / +1.4 |

  (R4 = 14.5 h, R3 = 24 h. Net = the fee payer's SOL change over all its recorded txs; open tokens not counted.)
- **Our cost at their density (INFERRED: our 50 armed slots per fill × density × our 5,120 lamports):**
  - 25 per slot ≈ 1,250 attempts per fill ≈ **0.0064 SOL per fill**.
  - 60 per slot ≈ 3,000 attempts per fill ≈ **0.015 SOL per fill**.
  - The T2 study's edge is ≈ +0.003–0.006 SOL per fill, so this density on T2 windows costs more than T2 earns.
  - Our per-attempt fee is already at the floor (5,000 per signature). The pros win on target choice: a near-certain creator dump, so
    ~15–35 armed slots per fill vs our ~50 (INFERRED: attempts per fill ÷ attempts per slot), and mostly +0.015–0.05 SOL net per fill.
  - Rate: 25–85 per slot = 120–400 tx/s per armed token. Our Helius path is 10/s (50/s for the whole region).
- **Small free fix (INFERRED, shadow first): skip seller-tool tokens.**
  - Probe: 9 of 118 windows (174 of 3,808 attempts, 5%) were on tokens run by these tools; 2 were TRIGGERED by the tool's own rebuy.
  - Feed signal: a sell followed at +1/+2 by buys from fresh wallets worth 25–100% of it, with a fixed template (CU price 500 / limit 200k,
    or limit 250k / 400k, no tip), or the same private program as the sell.
- **Reaction speed alone cannot get under ~10 positions (≈ 5 ms).** The fastest reactive pros never do it. (MEASURED, both days)
- **Relay bundling (Astralane-style) put a fast bot right behind a dump only ~12 times in 14.5 h.** Not a lever.

## Per-bot classification (R4; R3 agrees)
H1 = dense pre-sending · H2 = in the dump's bundle · H3 = backrun by someone who saw the dump early · H4 = same owner as the seller ·
H5 = fast reaction · CH = chance (a buy that was landing anyway).

| Bot | Label | Evidence (MEASURED unless marked) |
|---|---|---|
| 9K5QgBKa | **H1** | 60 fills, 64,066 failed attempts (error 7002 at ix 3); up to 85 per slot; 53/53 fills had own attempts just before; 50% ≤ 5 positions; v0 tx, own program 6ptPant1, no nonce, tip 0.006–0.007 SOL on attempts (reverted when they fail); 92% creator dumps |
| CZ77onJz | **H1** | 67 fills, 54,499 failed + 60,100 no-op; up to 69 per slot; 66/66; 48% ≤ 5; legacy tx, program GxAeRgjm; tips 0.012–0.019 SOL on fills and attempts (reverted when an attempt fails), 5,000 lamports on its no-op attempts; 91% creator dumps |
| Dk2jdQ93 | **H1** | 114 fills, 70,517 failed + 41,351 no-op; up to 49 per slot; 42% ≤ 5; program 4rhk8VRX, no tip; 94% creator dumps (2F6p8TXy, gVDXhoGb, ENskGQev); 1 fill in R3 (new) |
| FNuoWSQc | **H1** | 14 (R4) / 127 (R3) fills; ~800–1,200 attempts per fill; up to 51–60 per slot; program Fa4wabBS |
| FUru6V3L | **H1** | 88 fills, 74,236 failed; 26 per slot; 34% ≤ 5; v0 + lookup table, program FRt494oU, helius tip 0.001; 94% creator dumps |
| 5ZKd8DNB, 8g1w4PNC | **H1** | one program (3RHdR1Pb); 366–605 attempts per fill; 23–47 per slot but only 7–16% ≤ 5 positions |
| 2KtcBCfh | **H1** | 504 attempts per fill (Lighthouse 6001); ~10 per slot; all 61 fast follows are bwamJzzt's dumps (a serial launcher; a target choice — same owner not shown) |
| 2XyiEK56, 7VrFNnRw | **H1, no-op style** | 89,229 / 130,372 attempts that SUCCEED doing nothing (programs CkuYk5KU / GGaPdbyC); 6–8 per slot; 0–7% ≤ 5 |
| CVPz447t, 5k2Ckkiu | **H1, sparse** | 3–5 per slot; 183–407 attempts per fill; 3–9% ≤ 5 |
| EcmLLsxm, DrdaADiz, Fm4KUVJz, BSwWpdoR, 63wnCAg3, 4TvZtXrH, BDdhzyjZ, 9NojJSWX, 5Tkqfvi5, FNc2JCRj | **H2 + H4** | sellers 9LMeW9Sx / 9pkcMws3 / CpQf4h5J / GS8W1qoh sell into a vault (program DiTJQkwJ: VaultDrain → SellToVaultBonding); two buyers VaultClaim + buy at +1 and +2 (~50% each); same Jito bundle in 6 of 8 sampled (the 2 others, on a Harmonic leader, are not in the explorer) |
| CUiianSP + ~410 fresh wallets (rotation tool) | **H2 + H4** | buy = 96.9% of the sell, CU price 500 / limit 200k / no tip, always +1; the sell pays Jito + Astralane tips (≈ 0.006 SOL); same Jito bundle 28 of 36 sampled; 68% of buyers later sell the same token; KzCCTK4E and CUiianSP first funded by the same wallet (u6PJ8DtQ) |
| 7wqrdPux, 7eTU6LbY, 6PjmZ6PU, 5kYkf8hw | **H2 + H4** | seller B8zn7SyW; seller and buyers both use program J7pourVw + "lunar" tips (a volume service, INFERRED); +1…+5; same bundle 2/2 sampled |
| HkQ7hMjy, haqqiUUX, DF7eRXHn, GKd5EMzR, 8PgC4ngp, EMKY7r6U, 6n2cCJrr, G9G3dCBG | **H5 (11+ positions)** | 0.2–1.7% of follows ≤ 10 positions; most at 21–80 or the next slot; almost no own attempts before (0–13 of 100s); durable nonce on 12/12 sampled buys; their near-dump buys follow an earlier sell of a cascade 53–95% of the time (vs 36% for all dumps) |
| DF7eRXHn, EJX629cp, 4oN18efp, 5mWe9kLZ, D1QuMgpv, J3gZFpvs (gap 1–3 cases) | **H5 + some H2/H3** | ~12 buys in 14.5 h sat inside a relay-tipped bundle right behind the dump (tippers AsLDo4S8, AsTftkLQ, ASXA4dEB, ASteWQy5, 4k8mxqdk …) |
| ssssswdk (+ sibling sssssDdM) | **CH / late H5** | 11,893 buys in 14.5 h (one per ~4 s); 50 buys ≤ 10 positions after vs 25 before; 68% of them after a cascade's earlier sell; never in the dump's bundle (0/13) |
| AFrSqSLk, nya666pQ, E2x1ewwX, 2zMj6wNq, kBDycuZW, E7LYdw2g, 2Dd3TRSd, BXZ5mXaR, 3Le7cTEL, 84UBp52F | **CH** | 111–1,726 buys each; 2–19 near-dump buys each (≤ 3.5% of their buys); no attempts before; not in the dump's bundle |
| EgxfYgEb (us) | **H1, sparse** | 3.8 per slot; 2 of the probe's 19 instant buys were ours |

**How they send (MEASURED, getTransaction on 2–4 txs per bot):**
- Pre-senders: one signer, no durable nonce, own check program (or Lighthouse), CU limit 53–68k (7VrFNnRw 200k).
  CU price varies per attempt (~50 to 4.9M µL). Tip inside the tx or none, so a failed attempt pays only the fee (5,000–44,000 lamports; medians 5,000–13,600).
- Reactive bots: durable nonce (12/12 sampled), at most one tip per tx (astralane / helius / nozomi / falcon / speedlanding / none), CU price 1.2–70M µL.
- Seller tools: the SELL carries the tip (96%: Jito + Astralane, or lunar); the rebuys carry none (93%) and use a tiny CU price.

## Proof examples
`proof.md` next to this file: 49 solscan-linked examples (pre-senders with their last attempts before the fill, same-bundle cases with
Jito explorer links, reactive bots, and all 19 probe instant buys).

## How it was measured
- **Pass 1 (i1):** every raw chunk → compact trades (R4 2.53M, R3 3.91M) and failed txs (R4 22M), with slot, block index, signers,
  error, fees, CU, tips, programs.
- **Dumps + followers (i4/i5):** every buy after a dump in the same slot, with its block gap.
- **Classes (i8/i9/i15):** every recorded tx on the token from 3 slots before the dump.
  - Pre-sent = the buyer's own failed or no-op attempts there.
  - Seller tool = a shared signer, the same PRIVATE program as the sell (< 100 traders in the run; public terminals excluded), or the rotation template.
  - Mirror test = the same wallets' buys at the same distance BEFORE dumps.
- **Wallet profiles (i6/i7/i18):** every recorded tx of 109 wallets: failed, trades, and successful txs without a trade.
- **Bundles (i3/i10/i14/i16):** public Jito explorer API (`transaction/<sig>` → bundle; `bundle/<id>` → txs, tippers, tip).
- **Anatomy (i11), funding (i12), block sizes (i17):** read-only RPC.
- Scripts: `ops/strategies/presend/instant/` (run_pipeline.sh runs i1→i9 for one run). Data: `/home/moiz/sniper-data/presend_instant/`.

## Limits
- No PoH / entry timing in the AMS records (poh null). Leader-time ms are block-size averages (INFERRED).
- The recording holds only txs touching tracked mints. A relay's separate tip tx is invisible there (the Jito API covers it).
- The Jito explorer shows Jito-engine bundles (also on BAM / Harmonic leaders). Other builders' bundles are invisible.
- Owner links (H4): funding checked on 8 pairs (1 shared funder). The tools' link rests on same bundle + seller-paid tip + fixed sizes + chained wallets.
- "Chance" for the residual is a mirror-test inference. Single cases can still be reactions.
- Pre-sender targets: "creator dump" = the dumper is the launch's creator in the collector's launch record.
