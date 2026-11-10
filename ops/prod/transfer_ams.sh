#!/bin/bash
# AMS wallet (EgxfYgEb..., /root/prod/wallet-ams.address): ONE SOL transfer to one of OUR wallets: fra (2g7rYv7y..., the
# Frankfurt PROD wallet), frz (FRZh63..., the test wallet) or efw (EFWcYe1P..., the owner's wallet, as on FRA since 11-03). Owner 11-05: "yes add it on AMS" (same pattern as FRA's
# transfer_prod.sh).
# Run by the OWNER (asks for the keystore passphrase):  sudo bash /root/prod/transfer_ams.sh [SOL] [fra|frz|efw] [--dry]
#   default 0.1 fra; max 0.5 per transfer = the engine's cap (repeat for more); --dry = everything except --live (nothing sent).
# Refused while any engine runs (a live dip run's kill switch reads this wallet's balance). After a landed transfer the AMS dip
# budget (/root/prod/dip_budget_ams.json) is told: first_start is lowered by what left the wallet, so moving funds is not
# counted as a trading loss. Uses the current dip engine binary in --transfer-sol mode (one plain SOL transfer, nothing else).
set -u
die() { echo "REFUSED: $*" >&2; exit 1; }
[ -t 0 ] || die "run it from your terminal (it asks for the passphrase)"
pgrep -f "^/root/sniper-dip/snipe_engine" >/dev/null && die "a dip engine is running (its kill switch reads this wallet): stop it first"
pgrep -x snipe_engine >/dev/null && die "a snipe_engine is running; transfer only between runs"
AMT=${1:-0.1}; DEST=${2:-fra}; DRY=${3:-}
awk -v a="$AMT" 'BEGIN{exit !(a>0 && a<=0.5)}' || die "amount must be > 0 and <= 0.5 SOL"
case "$DEST" in fra) TO=2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE;; frz) TO=FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS;; efw) TO=EFWcYe1P1ohYoW2ooSuE1NmY4QQctD9AEDWbqUV8rjsZ;; *) die "destination must be fra, frz or efw";; esac
[ -z "$DRY" ] || [ "$DRY" = "--dry" ] || die "third argument can only be --dry"
W=$(tr -d ' \n\r' < /root/prod/wallet-ams.address)
[ "$W" = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR" ] || die "unexpected AMS wallet address in /root/prod/wallet-ams.address: $W"
KS=/root/prod/wallet-ams.enc; BASECFG=/root/sniper-dip/dip_edge_ams.toml; PC=/root/prod/ams_transfer.toml
BIN=/root/sniper-dip/snipe_engine_dip37; ENVF=/root/sniper/deploy/.env; BUDGETF=/root/prod/dip_budget_ams.json
[ -x "$BIN" ] || die "missing $BIN"; [ -f "$KS" ] || die "missing $KS"; [ -f "$BASECFG" ] || die "missing $BASECFG"; [ -f "$ENVF" ] || die "missing $ENVF"
set -a; . "$ENVF"; set +a
bal() { python3 -c "import sys; sys.path.insert(0, '/root/indep'); from common import rpc; print(rpc('getBalance', ['$1'])['value'])"; }
BEFORE=$(bal "$W") || die "could not read the AMS balance"
TOBAL=$(bal "$TO") || TOBAL=0
awk -v b="$BEFORE" -v t="$TOBAL" -v w="$W" -v to="$TO" 'BEGIN{printf "AMS  %s  %.6f SOL\nTO   %s  %.6f SOL\n", w, b/1e9, to, t/1e9}'
awk -v b="$BEFORE" -v a="$AMT" 'BEGIN{exit !(b >= a*1e9 + 10000000)}' || die "balance too low: keeps 0.01 SOL for fees"
if [ -n "$DRY" ]; then echo "DRY RUN: builds and signs nothing that lands (no --live); checks the keystore + config only"; LIVE=
else
  echo "About to send $AMT SOL  AMS $W  ->  $DEST $TO  (network fee ~0.000005 SOL)"
  read -r -p "Type SEND to continue: " OK; [ "$OK" = "SEND" ] || die "not confirmed"; LIVE=--live
fi
sed -e "s#^wallet *=.*#wallet          = \"$W\"#" -e "s#^wallet_keystore *=.*#wallet_keystore = \"$KS\"#" "$BASECFG" > $PC
grep -q "^wallet *= *\"$W\"" $PC && grep -q "^wallet_keystore *= *\"$KS\"" $PC || { rm -f $PC; die "could not build $PC"; }
echo "the engine now asks for the keystore passphrase (hidden):"
"$BIN" --transfer-sol "$AMT" --transfer-to "$TO" $LIVE --env-name PROD --send-path staked-rpc --config $PC --env-file "$ENVF" 2>&1 \
  | grep -E "payer =|TRANSFER|native after|DRY|rror|assphrase"
rm -f $PC
[ -n "$DRY" ] && exit 0
# the AMS dip budget: lower first_start by what actually left the wallet (only when the balance really dropped by ~the amount)
python3 - "$W" "$BEFORE" "$AMT" "$DEST" "$TO" "$BUDGETF" <<'EOF'
import sys, json, os, time
sys.path.insert(0, "/root/indep")
from common import rpc
W, before, amt, dest, to, P = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4], sys.argv[5], sys.argv[6]
for _ in range(10):
    after = rpc("getBalance", [W])["value"]
    if before - after >= amt * 1e9 - 100_000: break
    time.sleep(2)
gone = before - after
if gone >= amt * 1e9 - 100_000 and os.path.exists(P):
    b = json.load(open(P)); b["first_start"] -= gone
    b.setdefault("transfers", []).append({"t": int(time.time()), "sol": amt, "to": dest, "address": to, "left_wallet": gone})
    tmp = P + ".new"; json.dump(b, open(tmp, "w"), indent=1); os.replace(tmp, P)
    print(f"AMS dip budget: transfer of {gone / 1e9:.6f} SOL recorded (first_start now {b['first_start'] / 1e9:.6f}); AMS balance {after / 1e9:.6f} SOL")
else:
    print(f"NOTE: the AMS balance moved by {gone / 1e9:.6f} SOL (expected ~{amt}); the dip budget was NOT changed")
EOF
