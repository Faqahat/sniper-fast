#!/bin/bash
# PROD wallet 2g7rYv7y...: ONE SOL transfer to one of OUR wallets: frz (FRZh63..., the test wallet) or ams (EgxfYgEb..., the
# Amsterdam edge's wallet; owner 10-24: "we need to transfer some funds from 2g to this").
# Run by the OWNER (asks for the keystore passphrase):  sudo bash /root/prod/transfer_prod.sh [SOL] [frz|ams]   (default 0.1 frz;
# max 0.5 per transfer = the engine's cap; repeat for more). Refused while any engine runs (a live dip run's kill switch reads
# this wallet's balance). After a landed transfer the dip budget (/root/prod/dip_budget.json) is told: first_start is lowered
# by what left the wallet, so moving funds is not counted as a trading loss.
# Uses a separate engine binary (/root/prod/snipe_engine_xfer, the PROD engine + --transfer-sol); the PROD engine is untouched.
set -u
die() { echo "REFUSED: $*" >&2; exit 1; }
[ -t 0 ] || die "run it from your terminal (it asks for the passphrase)"
pgrep -x snipe_engine >/dev/null && die "a snipe_engine is running; transfer only between runs"
pgrep -f "snipe_engine_dip[0-9]* --dip" >/dev/null && die "a dip engine is running (its kill switch reads this wallet): stop it first"
AMT=${1:-0.1}; DEST=${2:-frz}
awk -v a="$AMT" 'BEGIN{exit !(a>0 && a<=0.5)}' || die "amount must be > 0 and <= 0.5 SOL"
W=2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE
case "$DEST" in frz) TO=FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS;; ams) TO=EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR;; *) die "destination must be frz or ams";; esac
KS=/root/prod/wallet-prod.enc; PC=/root/prod/prod_transfer.toml; BIN=/root/prod/snipe_engine_xfer
[ -x "$BIN" ] || die "missing $BIN"; [ -f "$KS" ] || die "missing $KS"
set -a; . /root/sniper/deploy/.env; set +a
python3 - "$W" "$TO" <<'EOF'
import sys; sys.path.insert(0, "/root/indep")
from common import rpc
for n, w in (("PROD", sys.argv[1]), ("TO  ", sys.argv[2])): print(f"{n} {w}  {rpc('getBalance', [w])['value'] / 1e9:.6f} SOL")
EOF
BEFORE=$(python3 -c "import sys; sys.path.insert(0, '/root/indep'); from common import rpc; print(rpc('getBalance', ['$W'])['value'])")
echo "About to send $AMT SOL  PROD $W  ->  $DEST $TO  (network fee ~0.000005 SOL)"
read -r -p "Type SEND to continue: " OK; [ "$OK" = "SEND" ] || die "not confirmed"
sed -e "s#^wallet *=.*#wallet          = \"$W\"#" -e "s#^wallet_keystore *=.*#wallet_keystore = \"$KS\"#" /root/run1/run1_landing.toml > $PC
"$BIN" --transfer-sol "$AMT" --transfer-to "$TO" --live --send-path staked-rpc --config $PC --env-file /root/sniper/deploy/.env 2>&1 \
  | grep -E "payer =|TRANSFER|native after|rror|assphrase"
rm -f $PC
# the dip budget: lower first_start by what actually left the wallet (only when the balance really dropped by ~the amount)
python3 - "$W" "$BEFORE" "$AMT" "$DEST" "$TO" <<'EOF'
import sys, json, os, time
sys.path.insert(0, "/root/indep")
from common import rpc
W, before, amt, dest, to = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4], sys.argv[5]
for _ in range(10):
    after = rpc("getBalance", [W])["value"]
    if before - after >= amt * 1e9 - 100_000: break
    time.sleep(2)
gone = before - after
P = "/root/prod/dip_budget.json"
if gone >= amt * 1e9 - 100_000 and os.path.exists(P):
    b = json.load(open(P)); b["first_start"] -= gone
    b.setdefault("transfers", []).append({"t": int(time.time()), "sol": amt, "to": dest, "address": to, "left_wallet": gone})
    json.dump(b, open(P, "w"), indent=1)
    print(f"dip budget: transfer of {gone / 1e9:.6f} SOL recorded (first_start now {b['first_start'] / 1e9:.6f}); PROD balance {after / 1e9:.6f} SOL")
else:
    print(f"NOTE: the PROD balance moved by {gone / 1e9:.6f} SOL (expected ~{amt}); the dip budget was NOT changed")
EOF
