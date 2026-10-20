#!/bin/bash
# ZERO COST: prove the prod keystore unlocks to 2g7rYv7y... (the engine refuses if the decrypted key is any other
# wallet), then stop. --shadow only observes launches; nothing is signed for the chain, nothing is sent.
# usage (owner, in a terminal on the server): sudo bash /root/prod/unlock_test.sh
set -u
[ -t 0 ] || { echo "REFUSED: run it from your terminal (it asks for the passphrase)"; exit 1; }
KS=/root/prod/wallet-prod.enc; PC=/root/prod/prod_unlock.toml
sed -e 's#^wallet *=.*#wallet          = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"#' \
    -e "s#^wallet_keystore *=.*#wallet_keystore = \"$KS\"#" /root/run1/run1_landing.toml > $PC
timeout --foreground 25 /root/sniper-run1/target/release/snipe_engine --shadow --minutes 1 --no-telegram --config $PC --env-file /root/sniper/deploy/.env 2>&1 \
  | grep -m1 -E "payer =|holds|error|Error" ; rm -f $PC
echo "PASS = a line 'snipe_engine: payer = 2g7rYv7y...'. 'holds <other key>' = this keystore is not the prod wallet."
