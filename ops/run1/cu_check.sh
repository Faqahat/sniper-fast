#!/bin/bash
# L7 ZERO COST CU check of the Run-1 buy: simulateTransaction (sigVerify off, nothing sent, nothing signed for real) of the
# exact Run-1 buy — 1.5 SOL, CU limit 95,000, price 110M uL, the worst-case route's 3 tip transfers (Jito 0.012 + two
# 0.001 relay tips; +300 CU limit bump as live) — on the next N fresh SOL create_v2 launches off the feeds, each simulated
# 1.5 s after its create. Prints unitsConsumed and "CU-CHECK ... OK / WARN (<10% headroom) / FAIL".
# The wallet holds < 1.5 SOL until it is funded, so simulate AS a funded system-owned account (--sim-as; the engine checks
# owner = System and balance >= 1.6 SOL) — or, once the wallet is funded, pass the wallet's own pubkey.
# usage: bash /root/run1/cu_check.sh <FUNDED_SYSTEM_ACCOUNT_PUBKEY> [N=5]
ACC=${1:?usage: cu_check.sh <funded system-owned pubkey> [N]}; N=${2:-5}
cd /root/run1; . /root/run1/run1_common.sh
$B --simulate --sim-as $ACC --sim-count $N --sim-delay-ms 1500 --spend-lamports 1500000000 --cu-limit 95000 --cu-price-micro 110000000 \
  --sim-tips 12000000,1000000,1000000 --config $C --env-file /root/sniper/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass 2>&1 | tee /root/run1/cu_check.log | grep -E "SIMULATE AS|DETECTED|^err|unitsConsumed|CU-CHECK|>>>|simulate failed"
