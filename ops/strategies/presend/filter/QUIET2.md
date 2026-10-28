# QUIET v2 study: can the pre-send arm filter skip the flat fills? (analyst agent, 10-28 ~23:00–00:40 PKT)

Owner 10-28 23:00 PKT: "we need to improve QUIET". The AMS r34 screenshot shows a string of −0.0146 fills (−3.3% of 0.45:
pump fees + tip + rent, price unchanged), held 1 slot, landed 17–19 ms after the dump, nobody bought after us.
Offline replay only. Nothing sent, nothing deployed, no server written (only read-only `sudo grep` of the AMS records).
MEASURED = live records + the raw chain recording. INFERRED = a proxy or a model. Times PKT.
Code: `ops/strategies/presend/filter/quiet2/` (x1–x7 + their outputs x4–x7.txt). Data: `/home/moiz/sniper-data/presend_filter/quiet2/` (352 MB).

## Short answer (phone)

- **No arm-time rule passes the bar on the unseen test runs.** The pre-registered pick fails; the tree fails; the GBDT keeps
  too few winners. Flats are not visible at arm time, which is what the 10-27 flat study already found (AUC 0.65).
- **QUIET did not let those fills through by a bug or by the "no history" default.** 10 of the 11 AMS r34 flats had whales with
  7–510 past dumps that drew 3.0–7.6 followers on average (signal (d) false); 9 of 11 had another trade in the trigger slot
  ((a) false). The no-history path produces our BETTER fills (+0.014/fill on train, +0.007 on test). MEASURED.
- **Flats are a small cost.** Test runs: 15 of 185 fills, −0.197 SOL over 8.3 h (≈ −0.57 SOL/day); the losing fills cost
  −2.16 in the same hours. A flat and a winner look the same at the whale's buy: AMS r34 had 11 WINNERS (up to +0.110) on
  tokens with ≤ 5 buyers in the last 60 s, the same profile as the flats.
- **Engine change: none to the live rule.** Keep QUIET as it is (F 2.24, no history = skip when (a)(b)(c) hold, stop 6:2).
  Optional, log-only: annotate every arm with the one candidate that survived the test (section 5) and read it back after
  ≥ 2 days; it is post hoc, 90% CI includes 0.

## 0. Data and roles

| Role | Run | Span (PKT) | Size | Windows (chain-matched) | Fills | QUIET |
|---|---|---|---|---|---|---|
| train | AMS r28 | 10-27 18:20–22:03 | 0.50 | 609 | 150 | on |
| train | AMS r29, r30 | 22:04–22:31 | 0.50 / 0.35 | 92 | 26 | off (restarts) |
| train | AMS r31–r33 | 22:32–00:29 | 0.35 | 246 | 64 | on |
| train | FRA r27 | 10-28 02:26–14:26 | 0.45 | 1,089 | 200 | on |
| **test** | **FRA r28** | 10-28 14:31–20:02 | 0.45 | 375 | 78 | on |
| **test** | **AMS r34** | 10-28 20:06–22:58 (recording end) | 0.45 | 345 (7 later windows unmatched) | 107 | on |

- Records: every `presend_live_*`, `presend_attempt(_land)` and the shadow records. AMS r28–r34 fetched read-only (filtered lines).
- Chain: the host's raw recording copies 10-27 16:27 → 10-28 22:58 PKT, 5.02 M pump.fun trades, 53,805 whale dumps (the engine's
  dump rule). The replayed QUIET signals equal the engine's logged ones: (a) 2664/2664, (b) 2663/2664, (c) 2664/2664, (d) 597/607
  of the windows with a full 24 h of history (MEASURED).
- Labels (chain): **FLAT** = no other wallet's trade between our buy and our sell (its net is always −2.9% of size + 0.0015
  rent: −0.0107 / −0.0131 / −0.0144 at 0.35 / 0.45 / 0.50); **WIN** = net > 0; **LOSS** = the rest. Net = realized + rent back.
- The mechanism, for the record: the trigger is the WHALE'S BUY (≥ 6% of supply); our pre-sent buys land on the next ≥ 12% drop
  (any seller, 70% the whale); we sell 2 slots later. We are first in line after the dump in 95% of the fills, flat or not.

## 1. Flat fills per run (MEASURED)

| Run | Fills | Flat | Flat % | Flat net | Flat windows' failed tries | Win | Win net | Loss | Loss net | Pre-send net | Fills/h |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AMS r28 | 150 | 20 | 13.3 | −0.287 | 0.001 | 70 | +2.480 | 60 | −1.843 | +0.272 | 40.6 |
| AMS r29–r33 | 90 | 16 | 17.8 | −0.175 | 0.001 | 39 | +1.327 | 35 | −0.872 | +0.225 | ~38 |
| FRA r27 | 200 | 20 | 10.0 | −0.263 | 0.002 | 110 | +4.658 | 70 | −2.670 | +1.553 | 16.8 |
| **FRA r28 (test)** | 78 | 4 | 5.1 | −0.053 | 0.000 | 43 | +1.864 | 31 | −1.239 | +0.516 | 14.2 |
| **AMS r34 (test)** | 107 | 11 | 10.3 | −0.144 | 0.001 | 51 | +1.720 | 47 | −0.918 | +0.575 | 37.6 |

- Flats cost −0.98 SOL/day on the train hours and −0.57 SOL/day on the test hours (one server each). Their failed-try fees are
  negligible (0.000–0.002 per run). The losing fills cost 7–10× more than the flats.
- The owner's −0.0146: realized −0.0146 + 0.0015 rent back = the −0.0131 net above (0.45 size).

**What QUIET saw on the fills** (pooled, the 7 QUIET runs; share of fills with the signal "quiet"):

| | FLAT (66) | WIN (304) | LOSS (231) |
|---|---|---|---|
| (a) no earlier trade in the trigger slot | 33% | 20% | 41% |
| (b) no cohort bot holding | 67% | 40% | 44% |
| (c) < 2 follower bots ever | 77% | 44% | 58% |
| (d) whale's dumps drew < 2.24, or no history | 27% | 23% | 20% |
| 3 of the 4 | 26% | 14% | 22% |
| whale has NO dump history (wh_dumps = 0) | 18% | 20% | 11% |
| mean followers of the whale's past dumps (when any) | 4.2 | 5.0 | 4.7 |

- Flats are "quieter" on (b) and (c), but (d) does not separate them: the flats' whales were followed whales. Signal (d) is
  about the whale; the flat is about the token at that moment.
- **The no-history default is not the leak.** Fills whose whale had no history: train 75 fills, 11 flat, **+1.065** (+0.0142/fill);
  test 23 fills, 1 flat, +0.161. Examples (wins): 9vZvqnoV +0.098, H1xvejvb +0.095, 4rAoKPxa +0.086, 9BKRhH6a +0.077, 4W2Es6pX
  +0.074 (links: section 7). Flats with no history exist (Bse32jEN, 8aLidyGM, FwpfhcMk, 4dzuQWJo, 6N6E5VYw) but they are 15% of
  that group, like everywhere else.
- Fills that were armed ONLY because (d) was false ((a)(b)(c) quiet, whale history ≥ 2.24): train 39 fills, 7 flat, **−0.518**;
  test 20 fills, 0 flat, −0.056. Section 4 sweeps this.

**The owner's AMS r34 flats** (11; all landed first after the dump; 10 of 11 "held 1 slot" = the time-ms exit):

| PKT | Token | (a)(b)(c)(d) | Whale dumps / followers | Buyers last 60 s | Follower bots ever | Holders > 0.5% |
|---|---|---|---|---|---|---|
| 20:14 | [2umsPVJR](https://gmgn.ai/sol/token/2umsPVJRHXAjsbLZRaTiNzfWqXsaQkcXLJFT1YSEpR3p) | 0010 | 143 / 4.2 | 6 | 1 | 3 |
| 21:04 | [FMUu6obv](https://gmgn.ai/sol/token/FMUu6obvAzssfqBesaMEvPCfD4U4oHAyjg6kVc1S36w) | 0010 | 103 / 7.6 | 6 | 1 | 2 |
| 21:18 | [87UM4Tke](https://gmgn.ai/sol/token/87UM4TkeYU7CDR8pgphW4yBGQ3XRVhJFNys1a1Gnpump) | 1010 | 18 / 4.7 | 3 | 0 | 3 |
| 21:40 | [HL3npANb](https://gmgn.ai/sol/token/HL3npANbTXTXRPxkcsyR1ztSt1AeJLYat8DyFQ4kpump) | 0010 | 15 / 3.0 | 11 | 0 | 5 |
| 22:27 | [CX3nNNpf](https://gmgn.ai/sol/token/CX3nNNpfW7nETEAGtTzdr5G5qxHwGsh9UK5UJdRgpump) | 0100 | 510 / 3.4 | 1 | 17 | 1 |

(the other 6: 34uhqSv2 0000, DNy5E5in 0110, HMLomPJj 0110, 2q2XgABv 1010, 9PfUr2Ss 0110, i35N7aNq 0110 — none has all 4, so the
live rule could not skip them; the stop rule never reached them because they filled at +1..+4 slots.)

## 2. What a flat looks like, and why that is not enough (MEASURED means)

| At the whale's buy | FLAT | WIN | LOSS |
|---|---|---|---|
| trades in the last 60 s | 15.5 | 50.2 | 36.6 |
| distinct buyers, last 60 s | 8.6 | 23.2 | 17.3 |
| cohort bots trading, last 60 s | 1.0 | 3.9 | 2.8 |
| follower bots ever on the token | 1.4 | 5.7 | 4.2 |
| holders > 0.5% of supply | 4.2 | 7.0 | 6.3 |
| whale buy (SOL) / curve (SOL) | 3.4 / 38 | 4.0 / 40 | 4.3 / 42 |
| token age (slots) | 355 | 268 | 286 |
| At the dump (fill time) | | | |
| other buyers during the whale's hold | 1.5 | 4.8 | 3.7 |
| whale sold everything | 56% | 50% | 32% |
| others between the dump and our fill | 0.20 | 0.30 | 0.44 |
| our send → receive (ms) | 109 | 105 | 125 |

- Flats sit on tokens with a third of the attention. But a third of the winners sit there too: AMS r34 alone had 11 winners with
  ≤ 5 buyers in the last 60 s, worth +0.358: [8tPdzUYD](https://gmgn.ai/sol/token/8tPdzUYDqFS48mcGio6YcXtZ79kqn5mDLZ7BcFC8pump) +0.110,
  [FVkeRFGG](https://gmgn.ai/sol/token/FVkeRFGGsCroTy8PicNJUih8rcd61YceqseeL5ropump) +0.069, [AGzqUxeR](https://gmgn.ai/sol/token/AGzqUxeR6YEaXCepXojVb4K3HfpYEWfVXysoQsXcpump) +0.052,
  [GY5UngnH](https://gmgn.ai/sol/token/GY5UngnHxvoJRXacZHkGimnUKG8mfQvhC5BecDahpump) +0.030, [MqzaCYnZ](https://gmgn.ai/sol/token/MqzaCYnZbBy6ZHLvNHN3MjhjShY7TtpN2qXsTrfpump) +0.024.
- Speed is not the difference (109 vs 105 ms; first in line in 95% of both). A whale selling everything is a mild flat marker
  (56% vs 50%) but it is known only at fill time, and the exit is fixed.

## 3. The rule search (pre-registered on train, one look at test)

Selection rule, written in `x5_rules.py` before any test number: single thresholds on 59 arm-time features at train deciles
(1,605 rules) and ANDs of the 25 best (300 pairs); keep those that on TRAIN remove ≥ 40% of the flats, ≤ 15% of the winners'
P&L and gain on both big train runs; pick the highest train gain (160 candidates qualified). Gain of a rule = fees of the removed
windows' failed tries − net of the removed fills (MEASURED; a removed window is a pure subtraction on top of the live QUIET).

| Rule | Train gain (90% CI) | Train flats removed | TEST gain (90% CI) | Test flats | Test win P&L removed | FRA r28 | AMS r34 | Bar |
|---|---|---|---|---|---|---|---|---|
| **Pick: holders > 0.5% ≤ 2** | +1.374 (+0.74..+2.10) | 28/56 | **−0.209** (−0.71..+0.27) | 5/15 (33%) | 22% | −0.284 | +0.075 | FAIL |
| Depth-3 tree (economic objective) | +2.487 | 29/56 | −0.325 (−0.86..+0.16) | 5/15 | 26% | −0.358 | +0.033 | FAIL |
| GBDT (numpy, 120 rounds, train-constrained cut) | +3.634 | 44/56 | +0.531 (−0.23..+1.40) | 6/15 (40%) | 28% | +0.405 | +0.126 | FAIL (winners) |
| Runner-up, post hoc: trades ≤ 6 in 60 s AND price at its 120 s high | +1.278 | 24/56 | +0.296 (−0.15..+0.77) | 6/15 (40%) | 15% | +0.232 | +0.064 | passes, but chosen after the test |

- The pick removes on test: 5 flats (−0.066), 18 losses (−0.459), 14 WINNERS (+0.780): [Aqb6b9p6](https://gmgn.ai/sol/token/Aqb6b9p6KTuYzfaAAdRLgtVQR98EzqnuxhS3YzHgSbN3) +0.132,
  [BV5X1mUy](https://gmgn.ai/sol/token/BV5X1mUyiUhTCN1QbPsRekqtM2LXcdqriuXRuuJVpump) +0.115, [8tPdzUYD](https://gmgn.ai/sol/token/8tPdzUYDqFS48mcGio6YcXtZ79kqn5mDLZ7BcFC8pump) +0.110,
  [CHVhuzzz](https://gmgn.ai/sol/token/CHVhuzzzxDoDfEih9Tp8JwjrmPYbU3rKhsczRTqhpump) +0.109, [AG8Kc15f](https://gmgn.ai/sol/token/AG8Kc15fbxkPF5Fo3eobjJax7zY6pJVKE8KPGrpKDB7) +0.099.
- Fills/h with the pick: FRA r28 14.2 → 10.9, AMS r34 37.5 → 30.9. Top-5 share of the kept fills' net rises from 50% to 57%.
- **Multiple testing.** 1,905 rules tried; 160 met the train bar; 5 of those meet the test bar, all of the same family
  ("≤ 6–7 trades or ≤ 5 buyers in the last 1–2 min AND the price at its 2-minute high"). The 160 candidates average +0.089 on
  test (77% > 0) against −0.236 for random removal of the same number of windows: attention rules remove slightly more losers
  than winners, a small real effect, but the best of 160 is expected to look better than it is. Only 8% beat the random
  null's 95th percentile.
- The runner-up removes on test: flats [87UM4Tke](https://gmgn.ai/sol/token/87UM4TkeYU7CDR8pgphW4yBGQ3XRVhJFNys1a1Gnpump),
  [DNy5E5in](https://gmgn.ai/sol/token/DNy5E5inAm1sfREmZuYMeiDWX23GaGjq5hMhPy22pump), [HMLomPJj](https://gmgn.ai/sol/token/HMLomPJj5i8SU1hikok2i6ibzKtufL78n1sEdyydpump),
  [CX3nNNpf](https://gmgn.ai/sol/token/CX3nNNpfW7nETEAGtTzdr5G5qxHwGsh9UK5UJdRgpump), [2q2XgABv](https://gmgn.ai/sol/token/2q2XgABvd6V13kYP41E7C5mCiKpCEKWYZh5p1pwpGdJZ);
  but also 8tPdzUYD +0.110 and FVkeRFGG +0.069.

## 4. The existing knobs: F, the no-history default, a minimum dump count, the 6:2 stop, the try-time gate

Tightening is MEASURED (live fills newly removed). Loosening is INFERRED: a quiet-skipped trigger is valued by a chain proxy
(first drop to the re-signed limit inside the 10-slot window → P(fill) 0.55, net ≈ 0.57 × size × (2-slot return − 3.3%); corr
with real nets 0.77 on 590 filled windows).

| (d) variant, with (a)(b)(c) quiet | Train MEASURED (fills rm: flat/win/loss) | Train INFERRED (skips re-armed) | Test MEASURED | Test INFERRED |
|---|---|---|---|---|
| live: F 2.24, no history → skip | 0 | 0 | 0 | 0 |
| no history → ARM | 0 | 227 skips re-armed: −0.024 | 0 | 68: −0.052 |
| F 1.0 (no history → skip) | 0 | 59 re-armed: −0.029 | 0 | 22: −0.005 |
| F 3.0 | +0.033 (6: 1/3/2) | 0 | **−0.075** (5: 0/2/3) | 0 |
| F 4.0 | +0.208 (24: 4/8/12) | 0 | −0.065 (11: 0/4/7) | 0 |
| F 7.0 (= skip on (a)(b)(c) alone) | +0.543 (39: 7/13/19) | 0 | +0.063 (19: 0/7/12) | 0 |
| F 2.24 + skip whales with < 10 dumps | +0.304 (9: 1/4/4) | 0 | +0.284 (7: 0/1/6) | 0 |

- No row removes a single test flat. The "< 10 dumps" row gains on both sides but on 16 fills in total (noise; 48 variants tried).
- The no-history default should stay "skip": arming those 295 triggers is worth −0.08 (INFERRED; 64 would fill, 37 of them with
  no follower).
- **Stop 6:2.** Every stricter N:M loses on test (2:1 −0.166, 3:2 −0.093, 4:2 −0.165, 5:2 −0.150, 6:3 −0.043: they remove winners).
  The live stop disarmed 412 windows; the proxy says 39 would have filled later, worth +0.20 in total (INFERRED, 26 run-hours,
  5 of the 39 with no follower). The stop is close to neutral either way; switching it off is worth ≈ +0.2 SOL/day at most.
- **Try-time gate** (the 10-27 flat study's post-hoc lead, pre-specified, tested once here, conservative accounting): M = 1
  train +0.324 (90% −0.02..+0.67), **test −0.069** (−0.36..+0.18; FRA r28 −0.156, AMS r34 +0.087). Not confirmed. M = 2:
  test +0.073 (−0.56..+0.74), removes 22% of the winners' P&L. Only 9 of 56 train flats had no other trade at signing time:
  most flats happen on tokens that WERE trading during the whale's hold.

## 5. What to change in the engine

1. **Live rule: nothing.** Keep `--presend-live-quiet-fol 2.24`, the no-history = skip default, `--presend-live-quiet-stop 6:2`.
   The flats the owner saw are not reachable from arm-time information; every rule that removes them removes winners worth more.
2. **Optional, log-only ("QUIET v2 candidate")**, to settle it with fresh data instead of this one look at 8 test hours:
   - per token keep a 120 s ring of (block time, post-trade price);
   - at the trigger compute `n_tr_60s` (trades in the last 60 s before the trigger tx) and `maxdd_120s` = pre-trigger price /
     max price of the last 120 s − 1;
   - candidate skip = `n_tr_60s <= 6 AND maxdd_120s >= -0.2%` (the token traded ≤ 6 times in the last minute and the whale
     bought at the 2-minute high);
   - write it into the arm/skip records as `"v2":{"n_tr_60s":..,"maxdd_120s":..,"skip":bool}`; no live effect; evaluate after
     ≥ 2 days (≥ 60 flats) with `quiet2/x5_rules.py`'s accounting. Do not go live on it before that.
   Expected if real: +0.3 to +0.85 SOL/day per server at the observed fill rates (test +0.296 over 8.3 h), fills −25%, and it
   would still cost winners such as 8tPdzUYD. 90% CI includes zero.
3. Where the money is instead (MEASURED on the test runs): losses −2.16 vs flats −0.20. The five biggest test losses were all
   big follow-on sells inside our 2-slot hold ([AaXkyTAB](https://gmgn.ai/sol/token/AaXkyTABPynETQmQzhc2LSrBs1G9CMfm9R5BdhoEpump) −0.314 with 18 SOL sold after us,
   [HRzj4J2Q](https://gmgn.ai/sol/token/HRzj4J2Q8HdcYWkJJMGsDiJMDBubqf472Jr7N3rUpump) −0.214, [AiCdMSJX](https://gmgn.ai/sol/token/AiCdMSJXGrGC3NJxqJ6AQwqjHHEfpZMVtmeWFaW8pump) −0.141,
   [B1CFQWAg](https://gmgn.ai/sol/token/B1CFQWAgaj6Y9uX4KUBxPKiueNWe4E4VdRAcnpzdpump) −0.081, [4oWJ4e68](https://gmgn.ai/sol/token/4oWJ4e6893qrozpc9mbtAXaTitzc5A6LEGMv7T3vpump) −0.081).
   That is an exit / second-seller question, not a QUIET question; not studied here.

## 6. Caveats
- Test = 8.3 run-hours, 185 fills, 15 flats. One big fill moves a run by ±0.1–0.3.
- AMS r34's last minutes (after 22:58) are not in the recording copy; 7 windows and 2 fills are missing from the chain tables.
- The INFERRED rows use a proxy calibrated on our own fills (P(fill) 0.55, 0.57 slope); they are for direction, not size.
- Rules tried: 1,905 arm-time + 48 (d) variants + 24 stops + 2 gates + a tree + a GBDT. Treat any post-hoc winner accordingly.

## 7. Example links
No-history winners: [9vZvqnoV](https://gmgn.ai/sol/token/9vZvqnoVGXwzpg9C89do6zpNjaAXDKjSYxLkCD5mpump), [H1xvejvb](https://gmgn.ai/sol/token/H1xvejvbsWNexJ2xq2SHqPSuAh6p5er8ZvRmNa5Kpump),
[4rAoKPxa](https://gmgn.ai/sol/token/4rAoKPxaV9EQ3H9bi2r2oeTzLFZximS27TcD5g98pump), [9BKRhH6a](https://gmgn.ai/sol/token/9BKRhH6axEv5PqkAU8f5f7CYBAoHdqRSAacLRDHdpump), [4W2Es6pX](https://gmgn.ai/sol/token/4W2Es6pXgBPsNGnKvNk7MtvXWsjWBWtyDQ3T6Niapump).
No-history flats: [Bse32jEN](https://gmgn.ai/sol/token/Bse32jEN1BrPBGM3G3zkDeHSk9Xvi85vg3UJSZCpump), [8aLidyGM](https://gmgn.ai/sol/token/8aLidyGMcn7hSnd24Qv21tRBxBQ7C6spXQVe4x31pump),
[FwpfhcMk](https://gmgn.ai/sol/token/FwpfhcMkvAcg3Sq7KaqLMVtGHMWPYUSuToATrwzJpump), [4dzuQWJo](https://gmgn.ai/sol/token/4dzuQWJofP3cGXBikZsng2c9dEcEH6HfZ4G7odxRpump), [6N6E5VYw](https://gmgn.ai/sol/token/6N6E5VYw6mwvwKEdctikkUW5Sy1g2Kojt2VYxscgpump).
Armed only because the whale was "followed" ((a)(b)(c) quiet, (d) false), biggest losses: [G3badS9g](https://gmgn.ai/sol/token/G3badS9gyCjsSYecK2uDtPAWMFfP3gvCSYDAppTpump) −0.290 (9 dumps / 5.9),
[AiCdMSJX](https://gmgn.ai/sol/token/AiCdMSJXGrGC3NJxqJ6AQwqjHHEfpZMVtmeWFaW8pump) −0.141 (1 / 6.0), [85Z21cFK](https://gmgn.ai/sol/token/85Z21cFKMKSg4Jiki64PLKpaHjfHynSfBytuiMawpump) −0.101 (27 / 3.8),
[AhjhzQ2Y](https://gmgn.ai/sol/token/AhjhzQ2Ynnu33YFagpXuQqyiA5nmwyc8XDDSAwiE2Dbp) −0.097 (272 / 4.4), [BoTW4t6E](https://gmgn.ai/sol/token/BoTW4t6Eo336w2SdseqLaJmkatKiSAC8KFrnSPh6pump) −0.081 (296 / 4.3);
and wins in the same group: BV5X1mUy +0.115, 8tPdzUYD +0.110, [Gfa6tvRP](https://gmgn.ai/sol/token/Gfa6tvRPAA6ucAgVbJ1HAcYRVvGjKMD9gR9PJ9Hypump) +0.087.
