#!/bin/bash
# ===== PROD — REAL SOL — wallet 2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE =====
# Started MANUALLY by the owner, inside tmux, on the server. The keystore passphrase is typed by the owner at the
# engine's hidden prompt; it is never stored anywhere. Caps and parameters are explicit arguments (no defaults).
#
#   tmux new -s prod                      # (or: tmux attach -t prod)
#   sudo bash /root/prod/run_prod.sh --size 1.5 --max-buys 20 --max-loss 0.5 --minutes 180 [--tag p1] [--lock 0.3:0,0.6:0.3]
#   detach: Ctrl-b d      stop cleanly: Ctrl-c in the tmux window (engine only: stop new fires, drain, EXIT CHECK; wait for PROD_DONE)
#
# Same engine build, rule, gates, fees and exit as Dev (/root/run1/run1_common.sh); only the wallet + caps differ.
set -u
die() { echo "REFUSED: $*" >&2; exit 1; }
SIZE= BUYS= LOSS= MIN= TAG=prod LOCK="0.3:0,0.6:0.3"
while [ $# -gt 0 ]; do
  case "$1" in
    --size) SIZE=$2; shift 2;; --max-buys) BUYS=$2; shift 2;; --max-loss) LOSS=$2; shift 2;;
    --minutes) MIN=$2; shift 2;; --tag) TAG=$2; shift 2;; --lock) LOCK=$2; shift 2;;
    *) die "unknown argument $1";;
  esac
done
[ -n "$SIZE" ] && [ -n "$BUYS" ] && [ -n "$LOSS" ] && [ -n "$MIN" ] || die "--size, --max-buys, --max-loss and --minutes are all required"
num() { [[ "$1" =~ ^[0-9]+([.][0-9]+)?$ ]]; }
for v in "$SIZE" "$LOSS"; do num "$v" || die "not a number: $v"; done
[[ "$BUYS" =~ ^[0-9]+$ ]] && [[ "$MIN" =~ ^[0-9]+$ ]] || die "--max-buys and --minutes must be integers"
# PROD hard limits (edit here, deliberately, if the plan changes)
awk -v s="$SIZE" 'BEGIN{exit !(s>=0.05 && s<=4)}' || die "--size must be 0.05..4 SOL"
awk -v l="$LOSS" 'BEGIN{exit !(l>0 && l<=2)}' || die "--max-loss must be >0 and <= 2 SOL"
[ "$BUYS" -ge 1 ] && [ "$BUYS" -le 60 ] || die "--max-buys must be 1..60"
[ "$MIN" -ge 1 ] && [ "$MIN" -le 300 ] || die "--minutes must be 1..300"

[ -n "${TMUX:-}" ] || die "start PROD inside tmux (tmux new -s prod), so an SSH drop cannot stop it"
[ -t 0 ] || die "stdin must be your terminal: the engine asks for the keystore passphrase"
pgrep -x snipe_engine >/dev/null && die "another snipe_engine is running (Dev or Prod): one engine per server"

KS=/root/prod/wallet-prod.enc
[ -f "$KS" ] || die "missing $KS (the prod keystore)"
mkdir -p /root/prod/runs
. /root/run1/run1_common.sh                # B, FLAGS (Dev's exact rule/gates/fees/exit)
PC=/root/prod/prod_landing.toml
sed -e 's#^wallet *=.*#wallet          = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"#' \
    -e "s#^wallet_keystore *=.*#wallet_keystore = \"$KS\"#" /root/run1/run1_landing.toml > $PC
grep -q '^wallet *= *"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"' $PC && grep -q "^wallet_keystore *= *\"$KS\"" $PC || die "could not build $PC"

LAM=$(awk -v s="$SIZE" 'BEGIN{printf "%d", s*1e9}')
MAXSOL=$(awk -v s="$SIZE" 'BEGIN{printf "%.4f", s*1.07}')
BUDGET=$(awk -v s="$SIZE" -v n="$BUYS" 'BEGIN{printf "%.3f", n*(s*1.0125+0.03)+0.5}')
FL=("${FLAGS[@]}")
for i in "${!FL[@]}"; do
  case "${FL[$i]}" in
    --config) FL[$((i+1))]=$PC;; --spend-lamports) FL[$((i+1))]=$LAM;; --max-sol) FL[$((i+1))]=$MAXSOL;;
    --max-total-sol) FL[$((i+1))]=$BUDGET;; --max-buys) FL[$((i+1))]=$BUYS;; --max-loss-sol) FL[$((i+1))]=$LOSS;;
    --minutes) FL[$((i+1))]=$MIN;; --lock-tiers) FL[$((i+1))]=$LOCK;;
  esac
done

read BAL WSOLBAL < <(python3 - <<'EOF'
import sys; sys.path.insert(0, "/root/indep")
from common import rpc
W = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
r = rpc("getTokenAccountsByOwner", [W, {"mint": "So11111111111111111111111111111111111111112"}, {"encoding": "jsonParsed"}])
ws = sum(float(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmountString"]) for a in r["value"])
print(rpc("getBalance", [W])["value"] / 1e9, ws)
EOF
)
# pump v3 buys/sells settle in NATIVE SOL: WSOL in the wallet is idle and invisible to the engine's balance checks
awk -v w="$WSOLBAL" 'BEGIN{exit !(w>0.01)}' && echo "NOTE: the wallet also holds ${WSOLBAL} WSOL, which the engine does NOT use; run /root/prod/unwrap_prod.sh first to make it native SOL"
NEED=$(awk -v s="$SIZE" -v l="$LOSS" 'BEGIN{printf "%.3f", 2*(s*1.0125+0.03)+l}')
STAMP=$(date -u +%Y%m%d_%H%M); LOG=/root/prod/runs/prod_${TAG}_${STAMP}.log
cat <<EOF

=================== PROD RUN — REAL SOL ===================
 wallet        2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE   balance ${BAL} SOL (needs >= ${NEED} for 2 open + stop)
 buy size      ${SIZE} SOL per buy (cap ${MAXSOL})          max landed buys ${BUYS}   budget ${BUDGET} SOL
 run stop      -${LOSS} SOL     profit lock ${LOCK}       time ${MIN} min
 rule/gates    rule #2 + close leaders + create<=150 ms; fees, exit, slot deadline = Dev (run1_common.sh)
 engine        $B  ($(sha256sum $B | cut -c1-16))
 log           $LOG
============================================================
EOF
awk -v b="$BAL" -v n="$NEED" 'BEGIN{exit !(b>=n)}' || die "wallet balance ${BAL} < ${NEED} SOL needed"
read -r -p "Type PROD to start (anything else aborts): " OK
[ "$OK" = "PROD" ] || die "not confirmed"

# guard: verifies every fire on chain, stops the engine by its exact PID (SIGTERM -> drain) on a rule mismatch
( for _ in $(seq 1 120); do P=$(pgrep -n -x snipe_engine) && break; sleep 0.5; done
  [ -n "${P:-}" ] && exec python3 /root/run1/guard_run1.py "$LOG" /root/prod/runs/guard_${TAG}_${STAMP}.log PROD_DONE "$P" ) \
  > /root/prod/runs/guard_${TAG}_${STAMP}.out 2>&1 &
cd /root/prod
# AUDIT6 H6-1: the engine writes STRAIGHT to the log file (no pipe a Ctrl-c could kill: a dead pipe makes its next log
# line panic and would break the drain). The live view is a tail in its OWN session (setsid), so Ctrl-c in this window
# reaches only the engine (-> stop new fires, drain, EXIT CHECK) and this script (trap below), never the viewer.
: >> "$LOG"
setsid tail -n +1 -F "$LOG" &
TAILPID=$!
trap 'echo; echo "(Ctrl-c -> engine: stopping new fires, draining open positions, then EXIT CHECK; wait for PROD_DONE)"' INT
echo "the engine now asks for the keystore passphrase (hidden):"
$B --snipe-once --concurrent --live "${FL[@]}" --send-log /root/prod/runs/sends_${TAG}_${STAMP}.jsonl \
  --lat-trace /root/prod/runs/trace_${TAG}_${STAMP}.jsonl >> "$LOG" 2>&1
RC=$?
echo "PROD_DONE $TAG rc=$RC $(date -u)" >> "$LOG"
sleep 1; kill $TAILPID 2>/dev/null
trap - INT
echo "after the run: check UNSOLD / HELD-AT-EXIT / PENDING-AT-EXIT lines above, then sweep leftovers with --sell-held"
