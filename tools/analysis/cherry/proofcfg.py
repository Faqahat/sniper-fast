p = "/root/arb-lab/arb-live-proof.toml"
s = open(p).read()
old = "bid_tiers = false   # proof run: the normal bid, so our copies reach the leader as fast as they normally do"
assert old in s
s = s.replace(old, "bid_tiers = true    # DEFAULT tier on every attempt (owner, 2026-10-03): about zero priority; CONTEST tier off (its minimum below is unreachable)\n"
                   "spec_cu_price_micro = 1   # 1 micro-lamport per CU (about 0.2 lamports), enough for the Helius CU-price rule; a miss costs about 5,000", 1)
old2 = "bid_min_expected_lamports = 100000"
assert old2 in s
s = s.replace(old2, "bid_min_expected_lamports = 1000000000000000   # CONTEST tier off until the PoH data shows we can reach the trigger", 1)
open(p, "w").write(s)
print("ok")
