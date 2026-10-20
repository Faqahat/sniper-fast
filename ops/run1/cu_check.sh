#!/bin/bash
# ZERO COST CU checks of the Run-1 transactions: simulateTransaction only (sigVerify off, replaceRecentBlockhash; nothing
# is sent, nothing is signed by the simulated payer). Two parts, on fresh SOL create_v2 launches off the feeds:
# 1. BUY (L7): the exact Run-1 buy — 1.5 SOL, CU limit 95,000, price 110M uL, the worst-case route's 3 tip transfers (Jito
#    0.012 + two 0.001 relay tips; +300 CU limit bump as live) — simulated AS a funded system-owned account (--sim-as; the
#    engine checks owner = System and balance >= 1.6 SOL; once the wallet is funded, its own pubkey works too), each 1.5 s
#    after its create. Pass: every "CU-CHECK ... OK".
# 2. SELL (N4): the engine's own sell tx (sell_v3 of the whole balance + close of the Token-2022 ATA, --sell-cu-limit
#    120,000, --sell-cu-price-micro 5,000,000) simulated AS a wallet that already holds the fresh token: the largest holder
#    (getTokenLargestAccounts) that is not the bonding curve, is a funded system wallet whose token account is its T22 ATA,
#    and has a WSOL ATA + pump volume accumulator (as our wallet does after its buy). 3 s after the create (the bundle
#    buyers hold by then). Pass: every "SELL-CU-CHECK ... OK" (unitsConsumed < 90% of 120,000).
# usage: bash /root/run1/cu_check.sh <FUNDED_SYSTEM_ACCOUNT_PUBKEY> [N=5]
ACC=${1:?usage: cu_check.sh <funded system-owned pubkey> [N]}; N=${2:-5}
cd /root/run1; . /root/run1/run1_common.sh
echo "== BUY CU check ($N launches) =="
$B --simulate --sim-as $ACC --sim-count $N --sim-delay-ms 1500 --spend-lamports 1500000000 --cu-limit 95000 --cu-price-micro 110000000 \
  --sim-tips 12000000,1000000,1000000 --config $C --env-file /root/sniper/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass 2>&1 | tee /root/run1/cu_check.log | grep -E "SIMULATE AS|DETECTED|^err|unitsConsumed|CU-CHECK|>>>|simulate failed"
echo "== SELL CU check ($N launches) =="
$B --simulate --sim-sell --sim-count $N --sim-delay-ms 3000 --sell-cu-limit 120000 --sell-cu-price-micro 5000000 \
  --config $C --env-file /root/sniper/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass 2>&1 | tee /root/run1/cu_check_sell.log | grep -E "DETECTED|as holder|^err|unitsConsumed|SELL-CU-CHECK|SELL-SIMULATE|simulate failed"
