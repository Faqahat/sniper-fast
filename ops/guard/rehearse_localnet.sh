#!/usr/bin/env bash
# rehearse_localnet.sh: the whole DEPLOY.md flow against a local solana-test-validator (or --cluster devnet with a funded payer),
# THROWAWAY keys only (generated in $KEYS; never the trading keystores). Output: the transcript on stdout.
#   bash ops/guard/rehearse_localnet.sh [CLUSTER]     (default http://127.0.0.1:18899: start solana-test-validator --rpc-port 18899 first)
set -euo pipefail
C="${1:-http://127.0.0.1:18899}"
KEYS="${KEYS:-/home/it/sniper-data/plan1110/builder_c}"
S=/home/it/sniper-data/plan1110/onchain/toolchain/solana-release/bin
G="$(dirname "$0")/sg-ops.sh"
pubk() { "$S/solana-keygen" pubkey "$1"; }
P=$(pubk "$KEYS/devnet-payer.json"); PROG=$(pubk "$KEYS/devnet-program.json"); COLD=$(pubk "$KEYS/devnet-cold.json"); ADMIN=$(pubk "$KEYS/devnet-admin.json")
echo "== cluster $C payer $P program $PROG cold $COLD admin $ADMIN"
case "$C" in http://127.0.0.1*|http://localhost*) "$S/solana" airdrop 5 "$P" --url "$C" >/dev/null; "$S/solana" airdrop 1 "$ADMIN" --url "$C" >/dev/null; "$S/solana" airdrop 1 "$COLD" --url "$C" >/dev/null ;; esac
"$S/solana" balance "$P" --url "$C"
echo "== info";   "$G" info --cluster "$C"
echo "== deploy (dry)"; "$G" deploy --cluster "$C" --payer "$KEYS/devnet-payer.json" --program-keypair "$KEYS/devnet-program.json" --upgrade-authority "$COLD"
echo "== deploy";  "$G" deploy --cluster "$C" --payer "$KEYS/devnet-payer.json" --program-keypair "$KEYS/devnet-program.json" --upgrade-authority "$COLD" --yes 2>&1 | grep -v "^\s*$"
echo "== verify";  "$G" verify --cluster "$C" --program-id "$PROG" --expect-authority "$COLD"
echo "== verify against a different build must FAIL"; head -c 15776 /dev/urandom > /tmp/sg-wrong.so; "$G" verify --cluster "$C" --program-id "$PROG" --so /tmp/sg-wrong.so && exit 1 || echo "(failed as expected)"
echo "== smoke (wallet AMS, compiled; payer = $P since AMS holds nothing here)"; "$G" smoke --cluster "$C" --program-id "$PROG" --payer "$P"
echo "== smoke (wallet FRZ)"; "$G" smoke --cluster "$C" --program-id "$PROG" --payer "$P" --wallet FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS
echo "== allowlist"; "$G" allow-list --cluster "$C" --program-id "$PROG"
"$G" allow-init --cluster "$C" --program-id "$PROG" --payer "$KEYS/devnet-payer.json" --authority "$KEYS/devnet-payer.json" --admin "$ADMIN" --yes && exit 1 || echo "(init by a non-authority refused as expected)"
"$G" allow-init --cluster "$C" --program-id "$PROG" --payer "$KEYS/devnet-payer.json" --authority "$KEYS/devnet-cold.json" --admin "$ADMIN" --yes
"$G" allow-add --cluster "$C" --program-id "$PROG" --admin "$KEYS/devnet-admin.json" --wallet "$P" --yes
"$G" allow-list --cluster "$C" --program-id "$PROG"
PDA=$("$G" allow-list --cluster "$C" --program-id "$PROG" | awk '/allowlist PDA/{print $3}')
echo "== smoke with the payer as a LISTED wallet (allowlist $PDA)"; "$G" smoke --cluster "$C" --program-id "$PROG" --wallet "$P" --allowlist "$PDA" --payer "$ADMIN"
"$G" allow-add --cluster "$C" --program-id "$PROG" --admin "$KEYS/devnet-payer.json" --wallet "$COLD" --yes && exit 1 || echo "(add by a non-admin refused as expected)"
"$G" allow-remove --cluster "$C" --program-id "$PROG" --admin "$KEYS/devnet-admin.json" --wallet "$P" --yes
echo "== smoke after the removal must FAIL its pass case"; "$G" smoke --cluster "$C" --program-id "$PROG" --wallet "$P" --allowlist "$PDA" --payer "$ADMIN" && exit 1 || echo "(refused as expected)"
echo "== keystore paths refused"; "$G" allow-add --cluster "$C" --program-id "$PROG" --admin /home/it/sniper-keys/fra.enc --wallet "$P" && exit 1 || echo "(refused as expected)"
echo "== REHEARSAL PASS"
