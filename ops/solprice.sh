#!/bin/bash
# SOL/USD price every 10 min (cron). Latest -> /root/solprice.json, history -> /root/solprice.log. Public APIs, no keys.
P=$(curl -s -m 8 "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT" | python3 -c "import sys,json; print(float(json.load(sys.stdin)[\"price\"]))" 2>/dev/null)
SRC=binance
if [ -z "$P" ]; then
  P=$(curl -s -m 8 "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd" | python3 -c "import sys,json; print(float(json.load(sys.stdin)[\"solana\"][\"usd\"]))" 2>/dev/null); SRC=coingecko
fi
[ -z "$P" ] && { echo "$(date -u +%FT%TZ) FAIL" >> /root/solprice.log; exit 1; }
T=$(date -u +%FT%TZ)
printf "{\"sol_usd\": %s, \"source\": \"%s\", \"time_utc\": \"%s\"}\n" "$P" "$SRC" "$T" > /root/solprice.json.tmp && mv /root/solprice.json.tmp /root/solprice.json
echo "$T $P $SRC" >> /root/solprice.log
