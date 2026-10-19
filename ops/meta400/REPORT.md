# Sniper 4yFAz…EQrG3 — Full Per-Token Attribute Sweep & Invariance Check

**Target:** 4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3
**His sample:** 409 landed snipes (/root/last500/his_500.json), enriched on-chain + metadata-URI JSON -> his_meta.json / his_meta.jsonl
**Population baseline:** 1,141 pump creates (/root/profit_backtest/creates.json); 300 randomly sampled & enriched identically -> pop_meta.json / pop_meta.jsonl
**Method:** 1 getAccountInfo(jsonParsed) per mint (program, decimals, supply, mint/freeze/update authority, Token-2022 extensions, on-chain name/symbol/uri) + metadata-URI JSON fetch (multi-gateway: pump.mypinata -> ipfs.io -> dweb.link -> nftstorage) for socials/description/image/createdOn. Saved incrementally (one JSON line per token).

## Data quality / honesty
- On-chain mint attributes: 409/409 his, 300/300 pop retrieved (100%).
- Metadata-URI JSON fetched OK for 363/409 his (88.8%) and 277/300 pop (92.3%). The ~11% failures are dead/unreachable IPFS CIDs (gateway 404/timeout), not a selection attribute — failure rate is ~equal in his set and population, so it does not bias the social-presence comparison materially (absent-social numbers are a floor).

## FULL ATTRIBUTE TABLE (his% invariant vs pop% vs distinguishing)

| Attribute | his % | pop % | diff | pre-buy knowable? | verdict |
|---|---|---|---|---|---|
| TOKEN-2022 program | 99.3 | 100.0 | -0.7 | yes (slot-0, create tx) | invariant but UNIVERSAL |
| decimals == 6 | 100.0 | 100.0 | 0.0 | yes | invariant but UNIVERSAL |
| mint authority renounced (null) | 100.0 | 100.0 | 0.0 | yes | invariant but UNIVERSAL |
| freeze authority none (null) | 100.0 | 100.0 | 0.0 | yes | invariant but UNIVERSAL |
| update authority null | 99.3 | 100.0 | -0.7 | yes | invariant but UNIVERSAL |
| metadataPointer+tokenMetadata ext | 99.3 | 100.0 | -0.7 | yes | invariant but UNIVERSAL |
| supply ~ 1e15 (1B x 1e6) | 78.0 | — | — | yes | near-invariant, protocol default |
| suffix "pump" | 86.3 | 89.7 | -3.4 | yes | NOT invariant, not distinguishing |
| createdOn ~ pump.fun | 83.9 | 87.7 | -3.8 | yes (uri) | NOT invariant, not distinguishing |
| has image | 88.8 | 92.3 | -3.6 | yes (uri) | NOT invariant, not distinguishing |
| has description | 45.5 | 45.0 | +0.5 | yes (uri) | not distinguishing |
| showName present | 56.5 | 73.7 | -17.2 | yes (uri) | (lower in his) |
| has coin_community key | 30.6 | 22.7 | +7.9 | yes (uri) | weak |
| has twitter | 76.5 | 46.7 | +29.9 | yes (uri) | distinguishing, NOT invariant |
| twitter on x.com/twitter.com | 76.3 | 46.0 | +30.3 | yes (uri) | distinguishing, NOT invariant |
| has website | 62.3 | 30.0 | +32.3 | yes (uri) | distinguishing, NOT invariant |
| has ANY social | 80.2 | 50.0 | +30.2 | yes (uri) | distinguishing, NOT invariant |
| has telegram | 1.0 | 4.0 | -3.0 | yes (uri) | ~absent in both |
| has discord | 0.0 | 0.0 | 0.0 | yes (uri) | absent in both |
| dev_buy >= 0.3 SOL | 88.5 | 48.3 | +40.2 | yes (create tx) | distinguishing, NOT invariant |
| dev_buy >= 0.5 SOL | 86.3 | 39.0 | +47.3 | yes (create tx) | strongest signal, NOT invariant |
| dev_buy >= 1.0 SOL | 58.7 | 22.3 | +36.3 | yes (create tx) | distinguishing, NOT invariant |

## Candidate invariant filters & OOS test
There is NO attribute that is both (a) near-invariant across his picks AND (b) rarer in the population. Every attribute >=98% in his set is also >=99% in the population — all are pump.fun v2 (Token-2022) protocol defaults, forced on every launch (renounced mint, no freeze, null update authority, 6 decimals, metadata extensions). They cannot be a selection filter because nobody can launch a pump token without them.

The distinguishing attributes (dev_buy size, social presence) are NOT invariant — present in only 62–88% of his picks — so none is a hard shared filter. OOS time-split (sort by create_slot, early vs late half) shows they persist (stable, not an artifact):
- dev_buy>=0.5: early 88.2% / late 84.4%
- has twitter: early 77.5% / late 75.6%
- twitter|website: early 82.4% / late 78.0%

No recurring hidden identity: 310 distinct twitter handles across 409 tokens (top handle 2x), 242 distinct website URLs (top 2x), 333 distinct creators (top creator 7 launches). So there is no single shared social domain, handle, deployer, or creator. He also DOES occasionally buy tokens with NO social AND dev_buy<0.3 SOL (17 tokens, 4.2%), proving neither is a hard gate.

## VERDICT
NO attribute is both invariant across (near) all his picks AND distinguishing vs the population.

- The owner's hypothesis (one shared on-chain / metadata attribute = a hidden hard filter) is NOT supported. The things invariant across his ~400 (Token-2022, renounced mint/freeze, null update authority, 6 decimals, "pump" suffix, createdOn=pump.fun) are UNIVERSAL pump.fun defaults present in ~90–100% of ALL creates — same pattern already noted for the "pump" suffix (86% his vs 90% pop).
- The things that are DISTINGUISHING are SOFT preferences, not invariants: he over-selects tokens with a Twitter/website (any social) ~80% vs 50% pop, and with a larger dev-buy (>=0.5 SOL 86% vs 39% pop). Both are knowable at slot 0 (socials in metadata URI, dev-buy in create tx), but neither is present in 100% of his picks, so neither is "the" hidden filter.

This confirms his selection is OFF-CHAIN (social/account signal, momentum, external alerts, or a dev-buy threshold combined with discretion) rather than a single shared, slot-0, on-chain/metadata attribute. The best slot-0 correlates to mimic him: dev-buy >= ~0.3–0.5 SOL AND presence of a Twitter/website in the metadata — but applied as soft filters these still pass a large chunk of the population and miss ~15–20% of his real picks.

## Files
- /root/meta400/his_meta.json, his_meta.jsonl — 409 his tokens, full attributes
- /root/meta400/pop_meta.json, pop_meta.jsonl — 300 population tokens, same attributes
- /root/meta400/enrich_meta.py, enrich_pop.py, analyze_his.py, compare.py
