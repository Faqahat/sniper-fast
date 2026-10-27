#!/bin/bash
# ===== DURABLE-NONCE ACCOUNTS for the dip engine's nonce fan-out (run_dip_prod.sh --nonce FILE; engine dip10) =====
# Creates (or closes) the region wallet's nonce accounts WITH THE ENGINE ITSELF (snipe_engine_dip10 --create-nonces /
# --close-nonces): the keystore is unlocked at the engine's hidden passphrase prompt, exactly as for a run. Accounts are
# create_with_seed(wallet, "dip-nonce-<i>", System), authority = the wallet; idempotent (existing ones are verified and kept).
#   sudo bash /root/prod/nonce_accounts.sh --region fra --count 8          # plan only (no --live): nothing sent
#   sudo bash /root/prod/nonce_accounts.sh --region fra --count 8 --live   # creates them, writes /root/prod/nonce_fra.txt
#   sudo bash /root/prod/nonce_accounts.sh --region ams --count 8 --live   # Amsterdam wallet -> /root/prod/nonce_ams.txt
#   sudo bash /root/prod/nonce_accounts.sh --region fra --close --live     # rent back (engine STOPPED): closes every account in the file
# Cost: ~0.00145 SOL rent per account (all of it back with --close) + 0.000005 SOL fee per create / close.
set -u
die() { echo "REFUSED: $*" >&2; exit 1; }
REGION=fra COUNT= CLOSE=0 LIVE=()
while [ $# -gt 0 ]; do
  case "$1" in
    --region) REGION=$2; shift 2;; --count) COUNT=$2; shift 2;; --close) CLOSE=1; shift;; --live) LIVE=(--live); shift;;
    *) die "unknown argument $1";;
  esac
done
case "$REGION" in
  fra) W=2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE; KS=/root/prod/wallet-prod.enc; BASECFG=/root/sniper-dip/dip_probe.toml;;
  ams) [ -s /root/prod/wallet-ams.address ] || die "missing /root/prod/wallet-ams.address (the Amsterdam wallet's public key)"
       W=$(tr -d ' \n\r' < /root/prod/wallet-ams.address); KS=/root/prod/wallet-ams.enc; BASECFG=/root/sniper-dip/dip_edge_ams.toml;;
  *) die "--region fra|ams";;
esac
[[ "$W" =~ ^[1-9A-HJ-NP-Za-km-z]{32,44}$ ]] || die "wallet address for region $REGION looks wrong"
B=/root/sniper-dip/snipe_engine_dip10
OUT=/root/prod/nonce_$REGION.txt
PC=/root/prod/nonce_$REGION.toml
[ -x "$B" ] || die "missing $B"
[ -f "$KS" ] || die "missing $KS (the keystore)"
[ -f "$BASECFG" ] || die "missing $BASECFG (region $REGION base config)"
[ -t 0 ] || die "stdin must be your terminal: the engine asks for the keystore passphrase"
# the region's config, built as run_dip_prod.sh builds it (the wallet lines replaced; rpc_url from the base config)
sed -e "s#^wallet *=.*#wallet          = \"$W\"#" -e "s#^wallet_keystore *=.*#wallet_keystore = \"$KS\"#" "$BASECFG" > "$PC"
grep -q "^wallet *= *\"$W\"" "$PC" && grep -q "^wallet_keystore *= *\"$KS\"" "$PC" || die "could not build $PC"
echo "the engine now asks for the keystore passphrase (hidden):"
if [ "$CLOSE" = 1 ]; then
  [ -s "$OUT" ] || die "no $OUT to close"
  pgrep -f "snipe_engine_dip" >/dev/null && die "a dip engine is running: stop it first (it may be using these accounts)"
  "$B" --close-nonces "$OUT" ${LIVE[@]+"${LIVE[@]}"} --config "$PC" --env-file /root/sniper/deploy/.env
else
  [[ "$COUNT" =~ ^[0-9]+$ ]] && [ "$COUNT" -ge 1 ] && [ "$COUNT" -le 32 ] || die "--count N: 1..32"
  "$B" --create-nonces "$COUNT" --nonce-out "$OUT" ${LIVE[@]+"${LIVE[@]}"} --config "$PC" --env-file /root/sniper/deploy/.env
fi
echo "exit code $?"
