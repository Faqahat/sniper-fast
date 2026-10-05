#!/bin/bash
# arbx campaign supervisor (PLAN WP-01 item 8; it replaced arb-lab's supervisor script, removed with tools/analysis in I-11).
#
# usage: deploy/run-w.sh <campaign> <hours> <segment min> <fee budget lamports> <config> [operator]
#   e.g. from your own machine: ssh -t root@<host> 'cd /root/arbx && deploy/run-w.sh w6 5 20 25000000 deploy/arbx-stage0.toml moiz'
#
# What it does
#   - Campaign directory runs/<campaign>/ (MEASUREMENT §1.1). At start the binary is copied to arbx-<sha8> and the config
#     to config.frozen.toml, and every segment runs only those copies: a binary moved over the original mid-campaign
#     changes nothing. campaign.json (§4.1) is written at start and after each segment; supervisor.jsonl (§4.7) beside
#     the text log supervisor.log; control.jsonl (§4.7) for the control files.
#   - Segments <campaign>-p<i> back to back until <hours> are up, each `arbx run --campaign-dir` (its directory is
#     runs/<campaign>/<campaign>-p<i>/); its stdout and stderr go to runs/<campaign>/<campaign>-p<i>.out.
#   - Budget: each segment gets `--budget-left <lamports>`; the config is never edited (its hash stays the campaign's).
#     Spent = the sum over the campaign's segments of each segment's LAST status line (`failed_fees_lamports` before
#     WP-02, `failed_fees_total_lamports` after); the lines of one segment are never summed. A segment that may have sent
#     (it has attempts, or ran with --live and its engine started) and whose last line has no readable failed-fee total
#     makes the budget unknown (review M4: so does any error in reading it). From WP-05 a segment that could not send
#     (meta.json `run.mode` shadow or dry_run) writes would-sends to attempts: those are no evidence of sending. Under 1,000,000 left, or unknown: records
#     only, i.e. `--shadow` (the bot runs and records, never sends). WP-07 replaces this with the ledger.
#   - Controls by file in runs/ (no more kill -STOP):
#       <campaign>.pause  stop sending, keep recording (review M1): the running segment pauses sending (`arbx ctl
#                         pause-sending`) until the file is removed (`resume-sending`), and segments that start while it
#                         exists run with --shadow (records only); when it goes, such a segment is restarted so the next
#                         one sends. A pause the segment does not confirm is logged at once (supervisor.log,
#                         supervisor.jsonl `pause_failed`, control.jsonl accepted false), and after ARBX_PAUSE_TRIES (3)
#                         failed polls the segment is stopped as by .next: the next one records only (review F3). A
#                         segment that already sends nothing (shadow for the rest of the segment) confirms the pause
#                         without change and stays so. A refused `resume-sending` is logged and restarts the segment;
#       <campaign>.next   restart now: the running segment is stopped (`arbx ctl stop`, SIGINT if that fails), the file's
#                         text is the reason; the file is consumed;
#       <campaign>.stop   end the campaign; the file's text is the reason.
#     Each action is a control.jsonl line (src "file").
#   - A config with `[control] socket = false` is refused at start: pauses go through the segment's control socket
#     (the bot also refuses to run a --campaign-dir segment without one).
#   - Each segment's SendGate (meta.json `send_gate`) is logged once it is known (supervisor.jsonl `gate`); a --live
#     segment that is not sending (e.g. `program_hash_mismatch`) is a WARNING line (review M2).
#   - Early ends are classified from the segment's stop.json: deadline = natural, signal or control = operator,
#     equity_day or disk_budget (exit 20) = safety, anything else (error, panic, a `secondary` failure while stopping,
#     no stop.json, killed) = crash. Only crashes count toward the crash limit (more than 6 within 15 minutes ends the
#     campaign). A safety stop ends the whole campaign. A segment that does not exit after a stop gets SIGINT after
#     ARBX_STOP_INT_S (60) and SIGKILL after ARBX_STOP_KILL_S (180).
#   - One supervisor at a time on a runs directory (review M6): the campaign holds `flock` on runs/.supervisor.lock.
#   - Disk: no segment starts with less than ARBX_MIN_FREE_GB (25) free on the runs filesystem.
#   - Compression moved into the bot (WP-02): no post-segment zstd here.
#
# Passphrase, residual risk (PLAN WP-01 item 8, F31; owner decision OD-7). A live campaign asks the keystore passphrase
# once (read -rs, hidden), checks it unlocks the wallet, and keeps it in this script's memory for the whole campaign,
# handing it to each live segment over a pipe: never argv, the environment or a file. Mitigations: core dumps off
# (ulimit -c 0), shell history off, the variable cleared at exit. It is still readable by root from this process's
# memory while the campaign runs; a hardened `arbx campaign` launcher (zeroized, mlock'd buffer) is OD-7.
#
# Environment (overrides and tests):
#   ARBX_BIN          the binary to freeze (default: <repo>/target/release/arbx, else <repo>/arbx)
#   ARBX_RUNS         the runs directory (default: <repo>/runs)
#   ARBX_DRY=1        test mode (tools/test-run-w.sh): no passphrase, foreground, no pgrep check (the lock still holds)
#   ARBX_MAX_SEGMENTS stop after this many segments (default: no limit)
#   ARBX_MIN_FREE_GB  (25)   ARBX_BACKOFF_S: pause after a crash (10)   ARBX_POLL_S: control-file poll (2)
#   ARBX_PAUSE_TRIES  (3)    ARBX_STOP_INT_S (60)   ARBX_STOP_KILL_S (180)
set -u
umask 077
ulimit -c 0
set +o history 2>/dev/null

ROOT=$(cd "$(dirname "$0")/.." && pwd)
NAME=${1:-}; HOURS=${2:-}; SEG=${3:-}; BUDGET=${4:-}; CONF=${5:-}; OPERATOR=${6:-${SUDO_USER:-$(id -un)}}
usage() { echo "usage: deploy/run-w.sh <campaign> <hours> <segment min> <fee budget lamports> <config> [operator]" >&2; exit 2; }
[ -n "$CONF" ] && [ -f "$CONF" ] || usage
[[ "$NAME" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "campaign name: letters, digits, _ . - only" >&2; exit 2; }
[[ "$HOURS" =~ ^[0-9]+([.][0-9]+)?$ ]] && [[ "$SEG" =~ ^[0-9]+$ ]] && [[ "$BUDGET" =~ ^[0-9]+$ ]] || usage

DRY=${ARBX_DRY:-0}
RUNS=${ARBX_RUNS:-$ROOT/runs}
MAXSEG=${ARBX_MAX_SEGMENTS:-0}
MIN_FREE=${ARBX_MIN_FREE_GB:-25}
BACKOFF=${ARBX_BACKOFF_S:-10}
POLL=${ARBX_POLL_S:-2}
PAUSE_TRIES=${ARBX_PAUSE_TRIES:-3}
STOP_INT_S=${ARBX_STOP_INT_S:-60}
STOP_KILL_S=${ARBX_STOP_KILL_S:-180}
RECORDS_ONLY_BELOW=1000000
CRASH_LIMIT=6          # more than this many crashes within 15 minutes ends the campaign
BIN=${ARBX_BIN:-}
if [ -z "$BIN" ]; then for b in "$ROOT/target/release/arbx" "$ROOT/arbx"; do [ -x "$b" ] && { BIN=$b; break; }; done; fi
[ -n "$BIN" ] && [ -x "$BIN" ] || { echo "no arbx binary (set ARBX_BIN)" >&2; exit 1; }

CDIR=$RUNS/$NAME
PAUSEF=$RUNS/$NAME.pause; NEXTF=$RUNS/$NAME.next; STOPF=$RUNS/$NAME.stop
LOG=$CDIR/supervisor.log; SJ=$CDIR/supervisor.jsonl; CJ=$CDIR/control.jsonl; CAMP=$CDIR/campaign.json
CONF_ABS=$(cd "$(dirname "$CONF")" && pwd)/$(basename "$CONF")
ENVF=$(dirname "$CONF_ABS")/.env      # the .env a run of the original config would load (a path only; never read here)

# JSON helpers (python3, as the arb-lab supervisor used)
PY=$(cat <<'PYEOF'
import glob, json, os, sys, time
op, a = sys.argv[1], sys.argv[2:]
def load(p):
    with open(p) as f: return json.load(f)
def save(p, v):
    t = p + ".tmp"
    with open(t, "w") as f: json.dump(v, f, indent=1); f.write("\n")
    os.replace(t, p)
def num(x):
    try: return int(x)
    except Exception: return None
if op == "line":          # line <file> <json fields as k=v...>: one JSON line, t_ns first
    out = {"t_ns": time.time_ns()}
    for kv in a[1:]:
        k, v = kv.split("=", 1)
        out[k] = num(v) if k in ("budget_left_lamports", "free_gb", "exit_code") and num(v) is not None else (v == "true" if v in ("true", "false") else (None if v == "" else v))
    if "accepted" in out and not isinstance(out["accepted"], bool): out["accepted"] = None
    with open(a[0], "a") as f: f.write(json.dumps(out) + "\n")
elif op == "init":        # init <campaign.json> <name> <operator> <bin> <bin sha> <config> <config sha> <normalized sha> <budget>
    save(a[0], {"schema": "arbx.campaign/1.0", "name": a[1], "started_ns": time.time_ns(), "ended_ns": None, "operator": a[2],
        "binary": {"path": a[3], "sha256": a[4]}, "config": {"path": a[5], "sha256": a[6], "normalized_sha256": a[7] or None},
        "budget": {"equity_drop_day_sol": None, "failed_fee_budget_lamports": int(a[8])}, "segments": [], "crash_count_15min": 0})
elif op == "seg":         # seg <campaign.json> <name> <started_ns> <exit code> <stop reason> <class> <crash count>
    v = load(a[0])
    v["segments"].append({"name": a[1], "started_ns": int(a[2]), "ended_ns": time.time_ns(), "exit_code": num(a[3]),
        "stop_reason": None if a[4] in ("", "none") else a[4], "class": a[5]})
    v["crash_count_15min"] = int(a[6])
    save(a[0], v)
elif op == "end":         # end <campaign.json> <why>
    v = load(a[0]); v["ended_ns"] = time.time_ns(); v["end_reason"] = a[1]; save(a[0], v)
elif op == "classify":    # classify <segment dir> <exit code>: "<class> <stop reason>"
    rc = num(a[1]); reason = ""; secondary = None
    try:
        st = load(os.path.join(a[0], "stop.json"))
        reason = st.get("reason") or ""; secondary = st.get("secondary")
    except Exception: pass
    if not isinstance(reason, str): reason = ""
    if rc == 20 or reason in ("equity_day", "disk_budget"): cls = "safety"
    elif rc not in (0, 10, 20, 30) or not reason: cls = "crash"
    elif secondary: cls = "crash"          # failed while stopping (review M5): exit 30, not an operator stop
    elif reason == "deadline": cls = "natural"
    elif reason in ("signal", "control"): cls = "operator"
    else: cls = "crash"
    print(cls, reason or "none")
elif op == "spent":       # spent <campaign dir> <campaign> [segments run with --live...]: "<lamports> status" or "unknown <why>"
    # review M4: a segment may have sent when it left attempts (any name: attempts.jsonl in arb-lab,
    # attempts.NNN.jsonl.zst from WP-02, whose core writer puts each attempt on disk at once) or ran with --live (the
    # supervisor knows) and its engine started (status.jsonl exists: from WP-02 the recorder creates it, with its schema
    # header line, right before the engine starts, so before anything can be sent; a boot that failed earlier sent
    # nothing). The header line (`schema` arbx.status/..., `file_seq`) is not a status line. For those segments, a last
    # status line that is missing, unreadable, not an object or without a numeric failed-fee total makes the budget
    # unknown. Any error at all: unknown
    def is_header(l):
        try: o = json.loads(l)
        except Exception: return False
        return isinstance(o, dict) and isinstance(o.get("schema"), str) and o["schema"].startswith("arbx.status/") and "file_seq" in o
    try:
        total = 0; live = set(a[2:])
        for d in sorted(glob.glob(os.path.join(a[0], a[1] + "-p*"))):
            if not os.path.isdir(d): continue
            seg = os.path.basename(d)
            st = os.path.join(d, "status.jsonl")
            atts = [f for f in glob.glob(os.path.join(d, "attempts*")) if os.path.getsize(f) > 0]
            # review WP-05 #6: from WP-05 a segment that cannot send (meta.json `run.mode` shadow or dry_run, written before
            # anything could be sent: a --shadow or paused segment) records its would-sends in attempts too, which are no
            # evidence of sending. A meta.json that is missing or unreadable says nothing: its attempts count
            try: mode = load(os.path.join(d, "meta.json"))["run"]["mode"]
            except Exception: mode = None
            if mode in ("shadow", "dry_run"): atts = []
            sent = bool(atts) or (seg in live and os.path.exists(st))
            lines = [l for l in open(st, errors="replace").read().splitlines() if l.strip() and not is_header(l)] if os.path.exists(st) else []
            if not lines:
                if sent: print("unknown", seg + ":no-status-line"); sys.exit(0)
                continue
            try: s = json.loads(lines[-1])         # the LAST line only: its counters are totals (never sum lines)
            except Exception: s = None
            if not isinstance(s, dict):
                if sent: print("unknown", seg + ":unreadable-last-line"); sys.exit(0)
                continue
            v = (s.get("money") or {}).get("failed_fees_total_lamports") if isinstance(s.get("money"), dict) else None
            if v is None:
                ex = s.get("exec") if isinstance(s.get("exec"), dict) else {}
                snd = ex.get("sending") if isinstance(ex.get("sending"), dict) else {}
                v = snd.get("failed_fees_lamports")
            if v is None or isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                if sent: print("unknown", seg + ":no-failed-fee-field"); sys.exit(0)
                v = 0
            total += int(v)
        print(total, "status")
    except SystemExit: raise
    except Exception as e:
        print("unknown", "error:" + type(e).__name__)
elif op == "reply":       # reply <ctl exit code> <ctl output>: "<accepted 0|1> <sticky 0|1> <gate reason|-> <result or why it failed>"
    rc = num(a[0]); out = a[1] if len(a) > 1 else ""
    try: v = json.loads(out)
    except Exception: v = None
    if not isinstance(v, dict):
        first = " ".join(out.split())[:200] or "no output"
        print(0, 0, "-", "ctl failed (exit %s): %s" % (a[0], first))
    else:
        g = v.get("send_gate") if isinstance(v.get("send_gate"), dict) else {}
        acc = 1 if (v.get("accepted") is True and rc == 0) else 0
        print(acc, 1 if g.get("sticky") is True else 0, (g.get("reason") or "-").replace(" ", "_"), " ".join(str(v.get("result") or "").split())[:200] or "-")
elif op == "gate":        # gate <meta.json>: "<mode> <reason>" of its send_gate, nothing for a partial or unreadable one
    try:
        v = load(a[0]); g = v.get("send_gate")
        if not v.get("partial") and isinstance(g, dict) and g.get("mode"): print(g["mode"], " ".join(str(g.get("reason") or "-").split()))
    except Exception: pass
elif op == "get":         # get <json file> <dotted key>
    v = load(a[0])
    for k in a[1].split("."): v = v.get(k) if isinstance(v, dict) else None
    print("" if v is None else v)
PYEOF
)
py() { python3 -c "$PY" "$@"; }
say() { echo "$(date -u +%FT%TZ) $*"; }
sj() { py line "$SJ" "event=$1" "segment=${2:-}" "budget_left_lamports=${LEFT:-}" "budget_src=${BUDGET_SRC:-}" "free_gb=${FREE:-}" "detail=${3:-}"; }
cj() { py line "$CJ" "src=file" "who=$1" "cmd=$2" "why=$3" "accepted=$4" "result=$5"; }
reason_of() { local t; t=$(head -c 500 "$1" 2>/dev/null | head -1 | tr -d '\r'); [ -n "$t" ] && echo "$t" || echo "(no reason given)"; }
owner_of() { stat -c %U "$1" 2>/dev/null || echo "?"; }
free_gb() { df --output=avail -BG "$RUNS" 2>/dev/null | tail -1 | tr -dc 0-9; }
# ctl <segment dir> <command> <why>: `arbx ctl` with the supervisor as who; prints "<accepted> <sticky> <gate reason> <text>"
ctl() { local out rc; out=$("$BINC" ctl --run "$1" "$2" --who supervisor --why "$3" 2>&1 9>&-); rc=$?; py reply "$rc" "$out"; }

# ------------------------------------------------------------------ start
[ -e "$CDIR" ] && { echo "campaign $NAME exists ($CDIR): pick a new name" >&2; exit 1; }
# one supervisor at a time (review M6): the lock is held by this process and the campaign's background subshell (the
# segments do not inherit it), so a second campaign is refused during pauses and backoffs too
mkdir -p "$RUNS"
exec 9>>"$RUNS/.supervisor.lock"
if ! flock -n 9; then echo "another campaign supervisor holds $RUNS/.supervisor.lock: not starting" >&2; exit 1; fi
if [ "$DRY" != 1 ] && pgrep -f 'arbx-[0-9a-f]{8} run ' >/dev/null; then echo "an arbx campaign segment is already running" >&2; exit 1; fi
mkdir -p "$CDIR"
SHA=$(sha256sum "$BIN" | cut -c1-64)
BINC=$CDIR/arbx-${SHA:0:8}
CONFC=$CDIR/config.frozen.toml
cp "$BIN" "$BINC" && chmod 0555 "$BINC"
cp "$CONF" "$CONFC" && chmod 0444 "$CONFC"
"$BINC" check --config "$CONFC" > "$CDIR/check.out" 2>&1 || { echo "the config does not load: see $CDIR/check.out" >&2; exit 1; }
"$BINC" provenance --config "$CONFC" --offline > "$CDIR/provenance.json" 2>/dev/null || { echo "arbx provenance failed" >&2; exit 1; }
MODE=$(py get "$CDIR/provenance.json" config.mode)
CSHA=$(py get "$CDIR/provenance.json" config.file_sha256)
NSHA=$(py get "$CDIR/provenance.json" config.normalized_sha256)
# review F3: pauses go through each segment's control socket
if [ "$(py get "$CDIR/provenance.json" control.socket)" = False ]; then
  echo "the config has [control] socket = false: the supervisor pauses sending through the segment's control socket; not starting ($CDIR)" >&2
  exit 1
fi
py init "$CAMP" "$NAME" "$OPERATOR" "$BINC" "$SHA" "$CONFC" "$CSHA" "$NSHA" "$BUDGET"

PASS=""
if [ "$MODE" = live ]; then
  if [ "$DRY" = 1 ]; then PASS=dry; else
    read -rs -p "keystore passphrase (hidden): " PASS; echo
    if ! printf '%s\n' "$PASS" | "$BINC" wallet --config "$CONFC" > /dev/null; then
      PASS=""; echo "the passphrase does not unlock the wallet: not starting" >&2; py end "$CAMP" "passphrase refused"; exit 1
    fi
  fi
fi

# log_gate <i> <segment> <segment dir> <flag>: the segment's SendGate from its meta.json, once it is written (review
# M2); fails while it is not known yet
log_gate() {
  local g mode reason
  g=$(py gate "$3/meta.json" 2>/dev/null) || return 1
  [ -n "$g" ] || return 1
  mode=${g%% *}; reason=${g#* }
  say "segment $1: send gate $mode ($reason)"
  sj gate "$2" "mode=$mode reason=$reason flag=${4:-none}"
  if [ "$4" = --live ] && [ "$mode" != live ]; then say "WARNING: segment $1 runs with --live but is NOT SENDING: send gate $mode ($reason)"; fi
  return 0
}

campaign() {
  say "start $NAME: $HOURS h in $SEG-min segments, fee budget $BUDGET lamports, mode $MODE, binary $(basename "$BINC"), config sha256 ${CSHA:0:16} (normalized ${NSHA:0:16}), operator $OPERATOR"
  LEFT=$BUDGET; BUDGET_SRC=status; FREE=$(free_gb)
  sj start "" "hours=$HOURS segment_min=$SEG budget=$BUDGET mode=$MODE binary=$(basename "$BINC")"
  local end_t; end_t=$(( $(date +%s) + $(python3 -c "print(int(float('$HOURS') * 3600))") ))
  # paused: the pause file's presence has been logged (its removal is logged once too)
  local i=0 crashes=() why_end="time up" paused=0 live_segs=()
  while :; do
    [ "$(date +%s)" -lt "$end_t" ] || { why_end="time up"; break; }
    [ "$MAXSEG" -gt 0 ] && [ "$i" -ge "$MAXSEG" ] && { why_end="max segments ($MAXSEG)"; break; }
    if [ -f "$STOPF" ]; then why_end="stop file: $(reason_of "$STOPF")"; cj "$(owner_of "$STOPF")" stop "$(reason_of "$STOPF")" true "campaign ends"; break; fi
    # .pause stops sending, not recording (review M1): a segment that starts while it exists runs with --shadow
    local pause_now=0
    if [ -f "$PAUSEF" ]; then
      pause_now=1
      [ "$paused" = 1 ] || { paused=1; say "paused: $(reason_of "$PAUSEF") (segments record only while the file exists)"; sj pause "" "$(reason_of "$PAUSEF")"
        cj "$(owner_of "$PAUSEF")" pause-sending "$(reason_of "$PAUSEF")" true "segments record only (--shadow) while the file exists"; }
    elif [ "$paused" = 1 ]; then paused=0; say "resumed"; sj resume "" "pause file removed"; cj "?" resume-sending "pause file removed" true "segments send again"; fi
    FREE=$(free_gb)
    if [ -n "$FREE" ] && [ "$FREE" -lt "$MIN_FREE" ]; then why_end="disk low (${FREE}G < ${MIN_FREE}G)"; sj disk_low "" "$why_end"; break; fi
    local mins=$(( (end_t - $(date +%s)) / 60 )); [ "$mins" -gt "$SEG" ] && mins=$SEG
    [ "$DRY" = 1 ] && [ "$mins" -lt 2 ] && mins=2
    [ "$mins" -lt 2 ] && { why_end="time up"; break; }
    # a .next left from between segments would stop the new one at once: it is consumed here
    [ -f "$NEXTF" ] && { cj "$(owner_of "$NEXTF")" next "$(reason_of "$NEXTF")" false "no segment running: ignored"; rm -f "$NEXTF"; }
    i=$((i + 1))
    local seg="$NAME-p$i" segdir="$CDIR/$NAME-p$i"
    # the budget: each earlier segment's last status line (never summed within a segment). Anything but "<n> status"
    # (unknown, an error, no output) is unknown: records only (review M4)
    local sp; sp=$(py spent "$CDIR" "$NAME" "${live_segs[@]+"${live_segs[@]}"}" 2>&1)
    if [[ "$sp" =~ ^[0-9]+\ status$ ]]; then LEFT=$(( BUDGET - ${sp%% *} )); BUDGET_SRC=status; else LEFT=0; BUDGET_SRC=unknown; fi
    local flag="" for_pause=0
    if [ "$MODE" = live ]; then
      if [ "$BUDGET_SRC" = unknown ] || [ "$LEFT" -lt "$RECORDS_ONLY_BELOW" ]; then
        flag=--shadow; say "segment $i records only (--shadow): budget ${BUDGET_SRC/status/left $LEFT} (${sp#* })"; sj budget "$seg" "records only: ${sp:-no output}"
      elif [ "$pause_now" = 1 ]; then
        flag=--shadow; for_pause=1; say "segment $i records only (--shadow): paused"
      else flag=--live; live_segs+=("$seg"); fi
    fi
    [ "$LEFT" -lt 0 ] && LEFT=0
    local args=(run --config "$CONFC" --minutes "$mins" --name "$seg" --campaign-dir "$CDIR" --budget-left "$LEFT" --env-file "$ENVF")
    [ -n "$flag" ] && args+=("$flag")
    say "segment $i: $mins min, budget left $LEFT ($BUDGET_SRC), disk ${FREE}G, ${flag:-shadow config}"
    sj segment_start "$seg" "minutes=$mins flag=${flag:-none}$( [ "$for_pause" = 1 ] && echo " paused=true")"
    local t0; t0=$(date +%s%N)
    # the segment does not inherit the supervisor's lock (fd 9)
    if [ "$flag" = --live ]; then
      printf '%s\n' "$PASS" | "$BINC" "${args[@]}" > "$CDIR/$seg.out" 2>&1 9>&- &
    else
      "$BINC" "${args[@]}" < /dev/null > "$CDIR/$seg.out" 2>&1 9>&- &
    fi
    local pid=$! stop_sent=0 stop_t=0 int_sent=0 kill_sent=0 gate_logged=0
    # seg_paused: this segment confirmed the pause (seg_sticky: it was not sending anyway); pause_fail: polls in a row
    # whose pause it did not confirm
    local seg_paused=0 seg_sticky=0 sticky_why="" pause_fail=0 acc sticky greason text
    while kill -0 "$pid" 2>/dev/null; do
      [ "$gate_logged" = 0 ] && log_gate "$i" "$seg" "$segdir" "$flag" && gate_logged=1
      # a stop that does not end the segment: SIGINT, then SIGKILL (then classed a crash: no stop.json)
      if [ "$stop_sent" = 1 ]; then
        local waited=$(( $(date +%s) - stop_t ))
        if [ "$waited" -ge "$STOP_KILL_S" ]; then
          [ "$kill_sent" = 1 ] || { kill_sent=1; say "segment $i: no exit $STOP_KILL_S s after the stop: SIGKILL"; sj kill "$seg" "SIGKILL ${STOP_KILL_S}s after the stop"; }
          kill -KILL "$pid" 2>/dev/null
        elif [ "$waited" -ge "$STOP_INT_S" ] && [ "$int_sent" = 0 ]; then
          int_sent=1; say "segment $i: no exit $STOP_INT_S s after the stop: SIGINT"; kill -INT "$pid" 2>/dev/null
        fi
      fi
      if [ "$stop_sent" = 0 ] && [ -f "$STOPF" ]; then
        local why; why=$(reason_of "$STOPF")
        stop_segment "$segdir" "$pid" "campaign stop: $why"; stop_sent=1; stop_t=$(date +%s)
        cj "$(owner_of "$STOPF")" stop "$why" true "segment $seg stopped; campaign ends"
      elif [ "$stop_sent" = 0 ] && [ -f "$NEXTF" ]; then
        local why who; why=$(reason_of "$NEXTF"); who=$(owner_of "$NEXTF"); rm -f "$NEXTF"
        stop_segment "$segdir" "$pid" "next: $why"; stop_sent=1; stop_t=$(date +%s)
        cj "$who" next "$why" true "segment $seg stopped; next segment starts"; sj stop "$seg" "next: $why"
      fi
      if [ "$stop_sent" = 0 ] && [ "$seg_paused" = 0 ] && [ "$for_pause" = 0 ] && [ -f "$PAUSEF" ]; then
        # pause the running segment; it must confirm (review F3)
        local pwhy; pwhy=$(reason_of "$PAUSEF")
        read -r acc sticky greason text < <(ctl "$segdir" pause-sending "pause file: $pwhy")
        if [ "${acc:-0}" = 1 ]; then
          seg_paused=1; seg_sticky=${sticky:-0}; sticky_why=$greason; paused=1
          if [ "$seg_sticky" = 1 ]; then say "segment $i: not sending already (shadow for the rest of the segment: $greason): the pause changes nothing"
          else say "segment $i: sending paused"; fi
          sj pause "$seg" "$pwhy"
          cj "$(owner_of "$PAUSEF")" pause-sending "$pwhy" true "segment $seg $( [ "$seg_sticky" = 1 ] && echo "already shadow ($greason)" || echo paused)"
        else
          pause_fail=$((pause_fail + 1))
          if [ "$pause_fail" = 1 ]; then
            paused=1; say "segment $i: PAUSE NOT CONFIRMED: ${text:-no reply}"; sj pause_failed "$seg" "${text:-no reply}"
            cj "$(owner_of "$PAUSEF")" pause-sending "$pwhy" false "segment $seg: ${text:-no reply}"
          fi
          if [ "$flag" != --live ]; then
            # a segment run without --live sends nothing: nothing to fall back to
            seg_paused=1; seg_sticky=1; sticky_why="not run with --live"
          elif [ "$pause_fail" -ge "$PAUSE_TRIES" ]; then
            say "segment $i: the pause was not confirmed $pause_fail times: stopping it; segments record only while the pause file exists"
            stop_segment "$segdir" "$pid" "pause not confirmed: restart records-only"; stop_sent=1; stop_t=$(date +%s)
            sj stop "$seg" "pause not confirmed ($pause_fail tries): ${text:-no reply}"
            cj supervisor next "pause not confirmed after $pause_fail tries" true "segment $seg stopped; the next one records only while the pause file exists"
          fi
        fi
      elif [ "$seg_paused" = 1 ] && [ ! -f "$PAUSEF" ]; then
        seg_paused=0; paused=0
        if [ "$seg_sticky" = 1 ]; then
          say "segment $i: pause file removed; this segment stays shadow ($sticky_why)"; sj resume "$seg" "pause file removed; stays shadow ($sticky_why)"
          cj "?" resume-sending "pause file removed" true "segment $seg stays shadow ($sticky_why)"
        elif [ "$stop_sent" = 0 ]; then
          read -r acc sticky greason text < <(ctl "$segdir" resume-sending "pause file removed")
          if [ "${acc:-0}" = 1 ]; then
            say "segment $i: sending resumed"; sj resume "$seg" "pause file removed"; cj "?" resume-sending "pause file removed" true "segment $seg resumed"
          else
            say "segment $i: RESUME NOT CONFIRMED: ${text:-no reply}: restarting it so the next segment sends"; sj resume_failed "$seg" "${text:-no reply}"
            cj "?" resume-sending "pause file removed" false "segment $seg: ${text:-no reply}; restarted"
            stop_segment "$segdir" "$pid" "resume not confirmed: restart"; stop_sent=1; stop_t=$(date +%s); sj stop "$seg" "resume not confirmed"
          fi
        else
          sj resume "$seg" "pause file removed while stopping"; cj "?" resume-sending "pause file removed" true "segment $seg is stopping; the next one sends"
        fi
      elif [ "$seg_paused" = 0 ] && [ "$pause_fail" -gt 0 ] && [ ! -f "$PAUSEF" ]; then
        pause_fail=0   # the file went before the fallback: the next pause starts counting afresh
      elif [ "$for_pause" = 1 ] && [ "$stop_sent" = 0 ] && [ ! -f "$PAUSEF" ]; then
        # this segment records only because of the pause: restart it so the next one sends
        paused=0; say "segment $i: pause file removed: restarting this records-only segment so the next one sends"
        sj resume "$seg" "pause file removed: restart"; cj "?" resume-sending "pause file removed" true "segment $seg (records only) restarted: the next one sends"
        stop_segment "$segdir" "$pid" "pause lifted: restart to send"; stop_sent=1; stop_t=$(date +%s)
      fi
      sleep "$POLL"
    done
    wait "$pid"; local rc=$?
    [ "$gate_logged" = 0 ] && log_gate "$i" "$seg" "$segdir" "$flag" && gate_logged=1
    local dur_s=$(( ($(date +%s%N) - t0) / 1000000000 ))
    local cls reason; read -r cls reason < <(py classify "$segdir" "$rc")
    local now; now=$(date +%s)
    if [ "$cls" = crash ]; then crashes+=("$now"); fi
    local recent=0 c
    for c in "${crashes[@]+"${crashes[@]}"}"; do [ $((now - c)) -lt 900 ] && recent=$((recent + 1)); done
    py seg "$CAMP" "$seg" "$t0" "$rc" "$reason" "$cls" "$recent"
    say "segment $i ended after ${dur_s}s: exit $rc, stop reason $reason, class $cls (crashes in 15 min: $recent)"
    sj segment_end "$seg" "exit=$rc reason=$reason class=$cls duration_s=$dur_s crashes_15min=$recent"
    if [ "$cls" = safety ]; then why_end="safety stop in $seg ($reason)"; break; fi
    if [ -f "$STOPF" ]; then why_end="stop file: $(reason_of "$STOPF")"; break; fi
    if [ "$recent" -gt "$CRASH_LIMIT" ]; then why_end="crash limit: $recent crashes in 15 min"; break; fi
    if [ "$cls" = crash ]; then say "crash: last lines of $seg.out:"; tail -3 "$CDIR/$seg.out" 2>/dev/null | cut -c1-300 | sed 's/^/    /'; sleep "$BACKOFF"; fi
  done
  py end "$CAMP" "$why_end"
  sj stop "" "$why_end"
  say "done: $why_end"
  PASS=""
}

# stop the running segment: through its control socket, SIGINT if that fails (stop.json then names this supervisor)
stop_segment() {
  local segdir=$1 pid=$2 why=$3
  if ! "$BINC" ctl --run "$segdir" stop --who supervisor --why "$why" > /dev/null 2>&1 9>&-; then kill -INT "$pid" 2>/dev/null; fi
}

if [ "$DRY" = 1 ]; then
  campaign >> "$LOG" 2>&1
  PASS=""; unset PASS
  exit 0
fi
(
  trap '' HUP
  exec < /dev/null >> "$LOG" 2>&1
  campaign
) &
disown
PASS=""; unset PASS
echo "started campaign $NAME in the background: $CDIR (log supervisor.log; controls: touch $RUNS/$NAME.pause | .next | .stop, with a reason inside)"
