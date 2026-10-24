# Seeing Twitter through launch metadata (free route), 10-25, read-only
Data: metadata for 46k non-IPFS launches (meta.jsonl), outcomes + buy-at-launch replays for 73,926 SOL-curve launches R1–R3 (outcome.pkl.gz).
Scripts: fetch_meta.py, outcome.py, tw_analyze.py (→ tw_analyze.txt), sibtrig.py (→ sibtrig.txt).

- **Tweet tokens draw ~10x the buyers of normal launches:** others buy a median 7.6 SOL in 60 s vs 0.65, but only 1.4% graduate vs 7.6%.
  - Fresh tweets (token launched < 15 s after the tweet): 14.9 SOL in 60 s, 22 buyers.
  - Old tweets (> 1 h): ~0.
- **Buying every tweet token 75 ms after launch loses at every exit** (R3: −0.010 per trade at 1 s up to −0.156 at 5 min).
- **Author rules (built on R1+R2, tested on R3): all negative.** Even authors whose tokens drew ≥ 10 SOL in 60 s give −0.005 per trade at 3 s.
- **"First of several tokens for the same tweet"** gives +0.054 per trade at 75 ms / 10 s, but that is hindsight (you only know later that copies came).
  - The live version — buy the first token when the 2nd or 3rd appears (+0.5–2 s) — loses on train and test.
  - Most copies come within 5 s, after the launch wave is over.
- **Knowable at launch, needs a metadata fetch:** first token for its tweet + tweet < 15 s old + dev buy ≥ 1 SOL.

  | Landing / hold | Train | Test |
  |---|---|---|
  | 75 ms, 1 s hold | +24.9 over 1,648 | +16.6 over 954 |

  - That is +1.5–1.7% per trade and optimistic (followers kept).
  - At 200 ms (realistic once the metadata fetch is included) it is negative.
- **Instant version (create tx only:** launcher host + new name + dev ≥ 1 SOL): ≈ 0 optimistic, −4% per trade pessimistic.
- **Verdict:** the tweet signal is real (buyers come), but the money goes to whoever is in within ~100 ms of launch, and it is thin. Not worth paying for an X feed for this; the human narrative picks of the group are not captured by tweet features.
