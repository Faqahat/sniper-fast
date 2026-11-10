#!/bin/bash
# ===== APEX-PROBE (FRA) — APEX S2 launch-snipe probe: buy watched creators' launches from the create shred, sell after 2 s =====
# A SEPARATE program (not the dip engine). Shadow (default) never sends. Live = REAL SOL from the FRA wallet (2g7rYv7y...),
# started by the owner inside tmux (the engine asks for the keystore passphrase at a hidden prompt).
#
#   tmux new -s apex
#   sudo bash /root/apex/run_apex_probe.sh --run 1                                   # SHADOW (no sends, no passphrase)
#   sudo bash /root/apex/run_apex_probe.sh --run 2 --live --kill-below 13.5 --minutes 60   # LIVE (caps below)
#   options: --size 0.05 (max 0.25)  --max-buys 20  --max-spend 1.5  --hold-ms 2000  --sell-guard 0.5  --slot-delta 1
#            v2 (APEX-FEES recipe, default): --recipe lanes (one durable-nonce copy per lane, ONE tip each) | multitip (v1, --routes v13)
#            --lanes "class=path[:tip][@prio],...;default=..." (default: the recipe, see apex_probe --help) --prio 100000 (lamports, lanes without @)
#            FIRST-OR-REVERT on by default (--no-first) --first-tol 0.005 --bundle-wait auto|always|never --bundle-wait-us 300 --busy-poll
#            --nonce FILE = durable-nonce accounts of the FRA wallet, one base58 pubkey per line (# comments), made with
#              snipe_engine --create-nonces N --nonce-out FILE; REQUIRED live with --recipe lanes. /root/prod/nonce_fra.txt may be
#              reused only while no dip engine runs (the probe refuses to start live with nonces while any snipe_engine runs)
#            --watchlist /home/.../watchlist.json (default /root/apex/watchlist.json)  --match creator|args|signer|either
#              (creator = the CreateEvent creator, as the APEX backtests; args = the pre-11-04 match on the create args' creator)
#            APEX-3 entry score: --entry-filter log|on|off (default log: score recorded on every watched create, never gates)
#              --entry-model /root/apex/entry_model.json (ops/apex_probe/entry_export.py)  --entry-thr X (override the file's)
#            --allow-dip   (start even though a dip engine runs on this server: same wallet, shared send-rate limits)
#   stop: Ctrl-c (no new buys; an open position finishes its sell; then the END CHECK sells leftovers + closes empty token accounts)
#   report: python3 /root/apex/report.py /root/apex/runs/apex_rN.jsonl
set -u
die() { echo "REFUSED: $*" >&2; exit 1; }
RUN= LIVE= KILL= MIN= SIZE=0.05 MAXB=20 SPEND=1.5 HOLD=2000 ROUTES=v13 GUARD=0.2 SGUARD=0.5 DELTA=1 NONCE= WATCH=/root/apex/watchlist.json MATCH=creator ALLOWDIP=
RECIPE=lanes LANES= PRIO=100000 NOFIRST= FTOL=0.005 BWAIT=auto BWUS=300 BUSY=
ENTRY=log EMODEL=/root/apex/entry_model.json ETHR=
BIN=${APEX_BIN:-/root/apex/apex_probe}
while [ $# -gt 0 ]; do
  case "$1" in
    --run) RUN=$2; shift 2;; --live) LIVE=1; shift;; --kill-below) KILL=$2; shift 2;; --minutes) MIN=$2; shift 2;;
    --size) SIZE=$2; shift 2;; --max-buys) MAXB=$2; shift 2;; --max-spend) SPEND=$2; shift 2;; --hold-ms) HOLD=$2; shift 2;;
    --routes) ROUTES=$2; shift 2;; --guard) GUARD=$2; shift 2;; --sell-guard) SGUARD=$2; shift 2;; --slot-delta) DELTA=$2; shift 2;;
    --nonce) NONCE=$2; shift 2;; --watchlist) WATCH=$2; shift 2;; --match) MATCH=$2; shift 2;; --allow-dip) ALLOWDIP=1; shift;;
    --recipe) RECIPE=$2; shift 2;; --lanes) LANES=$2; shift 2;; --prio) PRIO=$2; shift 2;; --no-first) NOFIRST=1; shift;; --first-tol) FTOL=$2; shift 2;;
    --bundle-wait) BWAIT=$2; shift 2;; --bundle-wait-us) BWUS=$2; shift 2;; --busy-poll) BUSY=1; shift;;
    --entry-filter) ENTRY=$2; shift 2;; --entry-model) EMODEL=$2; shift 2;; --entry-thr) ETHR=$2; shift 2;;
    *) die "unknown argument $1";;
  esac
done
[[ "$RUN" =~ ^[0-9]+$ ]] || die "--run N is required"
[ -x "$BIN" ] || die "missing $BIN"
[ -s "$WATCH" ] || die "missing or empty watchlist $WATCH"
case "$ENTRY" in log|off) ;; on) [ -s "$EMODEL" ] || die "--entry-filter on needs the model $EMODEL";; *) die "--entry-filter log|on|off";; esac
[ "$ENTRY" = off ] || [ -s "$EMODEL" ] || echo "NOTE: no entry model at $EMODEL: the entry score is not recorded"
W=2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE; KS=/root/prod/wallet-prod.enc
BASECFG=/root/sniper-dip/dip_probe.toml; PC=/root/apex/apex_probe.toml
[ -f "$BASECFG" ] || die "missing $BASECFG"
if [ -n "$LIVE" ]; then
  [ -n "$KILL" ] && [ -n "$MIN" ] || die "live needs --kill-below SOL and --minutes N"
  in_tmux() { local p=$$; while [ "${p:-1}" -gt 1 ]; do case "$(ps -o comm= -p "$p" 2>/dev/null)" in tmux*) return 0;; esac; p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' '); done; return 1; }
  [ -n "${TMUX:-}" ] || in_tmux || die "start a live run inside tmux (tmux new -s apex)"
  [ -t 0 ] || die "stdin must be your terminal: the probe asks for the keystore passphrase"
  [ -f "$KS" ] || die "missing $KS"
  [ "$RECIPE" != lanes ] || [ -n "$NONCE" ] || die "live --recipe lanes needs --nonce FILE (durable-nonce accounts of the FRA wallet)"
fi
[ -z "$NONCE" ] || [ -s "$NONCE" ] || die "--nonce $NONCE: missing or empty"
pgrep -x apex_probe >/dev/null && die "an apex_probe is already running"
if pgrep -f "[s]nipe_engine_dip" >/dev/null; then
  [ -n "$ALLOWDIP" ] || die "a dip engine is running on this server (same wallet, shared Helius 1 req/s and other send limits): stop it or pass --allow-dip"
  echo "NOTE: a dip engine runs too (--allow-dip): the wallet balance (kill switch) moves with its trades as well"
fi
mkdir -p /root/apex/runs
# the run's config: the dip engine's FRA base + its side paths (glaive, falcon-udp, soyas/solami, 0slot), the wallet lines, and
# every path the routes / sells name switched on (probe-only paths are enabled = false in the base)
sed -e "s#^wallet *=.*#wallet          = \"$W\"#" -e "s#^wallet_keystore *=.*#wallet_keystore = \"$KS\"#" "$BASECFG" > $PC.tmp
for side in /root/sniper-dip/paths_glaive.toml /root/sniper-dip/paths_falcon_udp.toml /root/sniper-dip/paths_quic.toml /root/sniper-dip/paths_0slot.toml; do
  [ -f "$side" ] || continue
  # append a side file only when none of its path names is in the config yet (no duplicate [[send]] names)
  dup=
  for n in $(grep -o '^name *= *"[^"]*"' "$side" | sed 's/.*"\(.*\)"/\1/'); do grep -q "^name *= *\"$n\"" $PC.tmp && dup=1; done
  [ -n "$dup" ] || cat "$side" >> $PC.tmp
done
for n in nozomi helius-swqos helius bolt falcon falcon-udp soyas solami 0slot glaive landx-fra3 staked-rpc jito-bundle astralane; do
  awk -v n="$n" '/^\[\[send\]\]/{inb=0} $0 ~ ("^name *= *\"" n "\"") {inb=1} inb && /^enabled *= *false/ {sub(/false/, "true")} {print}' $PC.tmp > $PC.tmp2 && mv $PC.tmp2 $PC.tmp
done
mv $PC.tmp $PC
grep -q "^wallet *= *\"$W\"" $PC && grep -q "^wallet_keystore *= *\"$KS\"" $PC || die "could not build $PC"
TAG=apex_r$RUN; LOG=/root/apex/runs/$TAG.log; OUT=/root/apex/runs/$TAG.jsonl
MODEARGS=(--mode shadow)
[ -n "$LIVE" ] && MODEARGS=(--mode live --kill-below "$KILL" --max-runtime-min "$MIN")
[ -z "$LIVE" ] && [ -n "$MIN" ] && MODEARGS+=(--max-runtime-min "$MIN")
NARGS=(); [ -n "$NONCE" ] && NARGS=(--nonce-accounts "$NONCE")
V2=(--recipe "$RECIPE" --prio-lamports "$PRIO" --first-tol "$FTOL" --bundle-wait "$BWAIT" --bundle-wait-us "$BWUS")
[ -n "$LANES" ] && V2+=(--lanes "$LANES")
[ -n "$NOFIRST" ] && V2+=(--no-first-or-revert)
[ -n "$BUSY" ] && V2+=(--busy-poll)
V2+=(--entry-filter "$ENTRY" --entry-model "$EMODEL"); [ -n "$ETHR" ] && V2+=(--entry-thr "$ETHR")
echo "APEX-PROBE run $RUN: $([ -n "$LIVE" ] && echo "LIVE (real SOL, wallet $W)" || echo "SHADOW (no sends)") | size $SIZE SOL x max $MAXB buys, at risk <= $SPEND SOL$([ -n "$LIVE" ] && echo ", kill below $KILL SOL, $MIN min") | hold $HOLD ms | recipe $RECIPE$([ -z "$NOFIRST" ] && echo " + FIRST-OR-REVERT") | sell -$SGUARD | slot deadline create+$DELTA$([ -n "$NONCE" ] && echo " | nonce $NONCE") | match $MATCH | entry score $ENTRY"
echo "log: $LOG  records: $OUT"
: >> "$LOG"
setsid tail -n 0 -F "$LOG" &
TAILPID=$!
trap 'echo; echo "(Ctrl-c -> probe: no new buys; an open position finishes its sell; then the end check; wait for APEX_PROBE DONE)"' INT
$BIN "${MODEARGS[@]}" --config $PC --env-file /root/sniper/deploy/.env --watchlist "$WATCH" --match "$MATCH" \
  --size-sol "$SIZE" --max-buys "$MAXB" --max-spend-sol "$SPEND" --hold-ms "$HOLD" --routes "$ROUTES" --buy-guard "$GUARD" --sell-guard "$SGUARD" \
  --max-slot-delta "$DELTA" --sell-path staked-rpc --sell-fallback nozomi ${NARGS[@]+"${NARGS[@]}"} "${V2[@]}" --out "$OUT" >> "$LOG" 2>&1
RC=$?
sleep 1; kill $TAILPID 2>/dev/null
trap - INT
echo "apex_probe exit code $RC"
python3 /root/apex/report.py "$OUT" | tail -n 40
