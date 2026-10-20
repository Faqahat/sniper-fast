#!/bin/bash
# REVIEW: zero-cost auth discrimination: the same junk tx with our key vs a bogus key. Prints replies only, never keys.
set -a; . /root/sniper/deploy/.env; set +a
echo "LANDX_KEY length: ${#LANDX_KEY} chars (UDP needs exactly the 12-byte key)"
J='{"jsonrpc":"2.0","id":1,"method":"sendTransaction","params":["AQID",{"encoding":"base64"}]}'
r() { curl -s -m 8 -o /tmp/rv_r.txt -w "%{http_code}" "$@"; echo " $(head -c 160 /tmp/rv_r.txt | tr '\n' ' ')"; }
echo -n "landx fra1 json  OUR key: "; r -X POST "http://fra1.landx.dev/$LANDX_KEY" -H 'content-type: application/json' -d "$J"
echo -n "landx fra1 json  BOGUS  : "; r -X POST "http://fra1.landx.dev/AAAAAAAAAAAA" -H 'content-type: application/json' -d "$J"
echo -n "landx fra1 txb   OUR key: "; r -X POST "http://fra1.landx.dev/txb/$LANDX_KEY" -H 'content-type: application/octet-stream' --data-binary $'\x01\x02\x03\x04'
echo -n "landx fra1 txb   BOGUS  : "; r -X POST "http://fra1.landx.dev/txb/AAAAAAAAAAAA" -H 'content-type: application/octet-stream' --data-binary $'\x01\x02\x03\x04'
echo -n "nozomi fra2      OUR key: "; r -X POST "https://fra2.nozomi.temporal.xyz/?c=$NOZOMI_KEY" -H 'content-type: application/json' -d "$J"
echo -n "nozomi fra2      BOGUS  : "; r -X POST "https://fra2.nozomi.temporal.xyz/?c=00000000-0000-0000-0000-000000000000" -H 'content-type: application/json' -d "$J"
echo -n "astralane fr     OUR key: "; r -X POST "https://fr.gateway.astralane.io/irisb?api-key=$ASTRALANE_KEY&method=sendTransaction" -H 'content-type: application/octet-stream' --data-binary $'\x01\x02\x03\x04'
echo -n "astralane fr     BOGUS  : "; r -X POST "https://fr.gateway.astralane.io/irisb?api-key=bogus0000&method=sendTransaction" -H 'content-type: application/octet-stream' --data-binary $'\x01\x02\x03\x04'
echo -n "helius keyless          : "; r -X POST "http://fra-sender.helius-rpc.com/fast" -H 'content-type: application/json' -d "$J"
echo -n "staked-rpc       OUR key: "; r -X POST "https://staked-rpc-frankfurt.constant-k.com/?api-key=$CONSTANTK_TOKEN" -H 'content-type: application/json' -d "$J"
echo -n "staked-rpc       BOGUS  : "; r -X POST "https://staked-rpc-frankfurt.constant-k.com/?api-key=bogus" -H 'content-type: application/json' -d "$J"
rm -f /tmp/rv_r.txt
