#!/bin/bash
# PROD wallet 2g7rYv7y...: unwrap ALL its WSOL back to native SOL (one CloseAccount tx on its WSOL ATA, fee ~0.000005 SOL).
# Why: pump v3 buys/sells settle in NATIVE SOL; the engine never spends WSOL, and its balance checks read native SOL.
# Run by the OWNER (asks for the keystore passphrase): sudo bash /root/prod/unwrap_prod.sh
set -u
die() { echo "REFUSED: $*" >&2; exit 1; }
[ -t 0 ] || die "run it from your terminal (it asks for the passphrase)"
pgrep -x snipe_engine >/dev/null && die "a snipe_engine is running; unwrap only between runs"
W=2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE; KS=/root/prod/wallet-prod.enc; PC=/root/prod/prod_unwrap.toml
set -a; . /root/sniper/deploy/.env; set +a
python3 - <<'EOF'
import sys; sys.path.insert(0, "/root/indep")
from common import rpc
W = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
print("native SOL", rpc("getBalance", [W])["value"] / 1e9)
r = rpc("getTokenAccountsByOwner", [W, {"mint": "So11111111111111111111111111111111111111112"}, {"encoding": "jsonParsed"}])
for a in r["value"]: print("WSOL", a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmountString"], "in", a["pubkey"])
EOF
read -r -p "Type UNWRAP to close the WSOL account into native SOL: " OK; [ "$OK" = "UNWRAP" ] || die "not confirmed"
sed -e "s#^wallet *=.*#wallet          = \"$W\"#" -e "s#^wallet_keystore *=.*#wallet_keystore = \"$KS\"#" /root/run1/run1_landing.toml > $PC
/root/sniper-run1/target/release/snipe_engine --unwrap --live --send-path staked-rpc --config $PC --env-file /root/sniper/deploy/.env 2>&1 \
  | grep -E "payer =|UNWRAP|native after|holds|rror"
rm -f $PC
