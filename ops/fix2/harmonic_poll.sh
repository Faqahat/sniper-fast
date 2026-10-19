#!/bin/bash
# zero cost: one junk (undecodable) request to Harmonic's public endpoints every 5 min, to see if the "rate limited" lifts
OUT=/root/fix2/harmonic_poll.log
printf '\x00\x00\x00\x00\x0a\x0a\x08\x1a\x06\x0a\x04\x01\x02\x03\x04' > /root/fix2/hb_junk.bin
for i in $(seq 1 30); do
  T=$(date -u +%H:%M:%S)
  J=$(curl -s -m5 -w " http=%{http_code}" -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"sendBundle","params":[["AQIDBA=="],{"encoding":"base64"}]}' https://fra.be.harmonic.gg/api/v1/bundles)
  sleep 3
  G=$(curl -s -m5 --http2 -D - -o /dev/null -H "content-type: application/grpc" -H "te: trailers" --data-binary @/root/fix2/hb_junk.bin https://fra.be.harmonic.gg/searcher.BundleService/SendBundle | grep -i "grpc-" | tr -d '\r' | tr '\n' ' ')
  echo "$T jsonrpc: $J | grpc: $G" >> $OUT
  sleep 297
done
