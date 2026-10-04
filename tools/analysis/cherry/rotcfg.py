p_in, p_out = "/root/arb-lab/arb-live-flat.toml", "/root/arb-lab/arb-live-rotate.toml"
s = open(p_in).read()
s = s.replace("test_all_paths = false", "test_all_paths = true   # rotation: every path gets trades, whatever its tip", 1)
assert "test_all_paths = true" in s
old = "spec_cu_price_micro = 40000"
assert old in s
s = s.replace(old, "rotate_paths = true   # PATH ROTATION: one path per trade, in turn, each timed on the leader clock\n" + old, 1)
s = s.rstrip("\n") + """

[[send]]
# direct to the leader over QUIC (no relay, no tip, unstaked); the RPC only answers the leader schedule and TPU addresses
name = "tpu-direct"
kind = "tpu"
url = "${RMR_RPC_URL}"

[[send]]
# our normal Helius RPC (paid plan: staked connections), tip-less sendTransaction
name = "helius-rpc"
kind = "rpc"
url = "${RMR_RPC_URL}"
"""
open(p_out, "w").write(s)
print("ok")
