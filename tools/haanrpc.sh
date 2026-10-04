#!/bin/bash
# Reproduce Haan RPC failures: concurrent and sequential getMultipleAccounts; print status codes and error bodies.
cd ~/arb-lab
K=$(grep -E '^HAAN_API_KEY=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"' \r')
[ -z "$K" ] && { echo "no HAAN_API_KEY"; exit 1; }
BODY='{"jsonrpc":"2.0","id":1,"method":"getMultipleAccounts","params":[["So11111111111111111111111111111111111111112","EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"],{"encoding":"base64","commitment":"processed"}]}'
D=$(mktemp -d)
one() { curl -s -o "$D/b.$1" -w "%{http_code} %{time_total}\n" --max-time 5 -H "authorization: Bearer $K" -H 'content-type: application/json' -d "$BODY" https://rpc.haandigital.eu/ > "$D/s.$1"; }
echo "== burst: 60 requests at once"
for i in $(seq 1 60); do one "c$i" & done; wait
echo "== sequential: 40 requests back to back"
for i in $(seq 1 40); do one "q$i"; done
for kind in c q; do
  echo "-- $( [ $kind = c ] && echo burst || echo sequential ): HTTP status counts"
  cat $D/s.$kind* | awk '{print $1}' | sort | uniq -c
  echo "-- error replies (distinct, first 220 chars)"
  for f in $D/b.$kind*; do
    b=$(head -c 220 "$f")
    echo "$b" | grep -q '"result"' && ! echo "$b" | grep -q '"error"' && continue
    echo "$b"
  done | sort | uniq -c | sort -rn | head -6
  echo "-- latency of OK replies (s): $(paste -d' ' <(cat $D/s.$kind* | awk '$1==200{print $2}' | sort -n | awk '{a[NR]=$1} END{print "p50",a[int(NR/2)+1],"max",a[NR]}'))"
done
rm -rf "$D"
