p_in, p_out = "/root/arb-lab/arb-live-proof.toml", "/root/arb-lab/arb-live-flat.toml"
s = open(p_in).read()
old = "spec_cu_price_micro = 1   # 1 micro-lamport per CU (about 0.2 lamports), enough for the Helius CU-price rule; a miss costs about 5,000"
assert old in s
s = s.replace(old, "spec_cu_price_micro = 40000   # live-run-5: the normal flat bid on every copy, to measure our relay + leader-queue time fairly", 1)
open(p_out, "w").write(s)
print("ok")
