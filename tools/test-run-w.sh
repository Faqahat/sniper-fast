#!/bin/bash
# Dry run of the campaign supervisor deploy/run-w.sh against a fake arbx (PLAN WP-01 acceptance "Supervisor dry run").
# The fake binary plays a plan: each segment exits with a given code, writes a given stop.json reason and status lines,
# or waits for a stop through `ctl`. Checked:
#   - operator stops (signal, control) are not counted as crashes; crashes are (more than 6 in 15 min end the campaign);
#   - exit 20 (a safety stop) ends the whole campaign;
#   - the budget is each segment's LAST status line, never the sum of its lines; an unreadable one means records only;
#     under 1,000,000 left the segment runs with --shadow (the records-only fallback no longer crashes);
#   - the config is never edited: every segment runs the frozen copy, whose bytes equal the original's; the binary is
#     the campaign's frozen copy arbx-<sha8>;
#   - the control files: .pause (sending paused; segments that start while it exists record only, and are restarted
#     when it goes), .next (restart now, with its reason), .stop;
#   - a pause the segment refuses or cannot be asked (no socket) is logged and, after 3 polls, the segment is stopped
#     and the next one records only; a segment already shadow for the rest of the segment confirms it without change; a
#     refused resume restarts the segment (review F3);
#   - a stop that does not end the segment escalates to SIGINT, then SIGKILL (a crash); disk low ends the campaign;
#     a second supervisor on the same runs directory is refused; a config without the control socket is refused;
#   - the budget is unknown (records only) when a --live segment's last line is not a readable total, and an error in
#     reading it does not kill the supervisor (review M4); a crash while stopping (stop.json `secondary`) is a crash;
#   - each segment's send gate is logged, with a warning for a --live segment that does not send (review M2).
# usage: tools/test-run-w.sh   (exit 0 when every check passes; needs bash, python3, coreutils)
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d "${TMPDIR:-/tmp}/arbx-test-run-w.XXXXXX")
trap 'rm -rf "$T"' EXIT
FAILS=0; N=0
ok() { N=$((N + 1)); echo "ok   $*"; }
bad() { N=$((N + 1)); FAILS=$((FAILS + 1)); echo "FAIL $*"; }
check() { local what=$1; shift; if "$@"; then ok "$what"; else bad "$what"; fi; }
eq() { [ "$1" = "$2" ] || { echo "     expected [$2], got [$1]" >&2; return 1; }; }
# j <json file> <python expression over v>
j() { python3 -c 'import json,sys; v=json.load(open(sys.argv[1])); print(eval(sys.argv[2]))' "$1" "$2"; }
# jl <jsonl file> <python expression over L (the parsed lines)>
jl() { python3 -c 'import json,sys; L=[json.loads(x) for x in open(sys.argv[1]) if x.strip()]; print(eval(sys.argv[2]))' "$1" "$2"; }
wait_for() { local i; for i in $(seq 1 200); do eval "$1" && return 0; sleep 0.1; done; echo "     timed out waiting for: $1" >&2; return 1; }

# ------------------------------------------------------------------ the fake arbx
cat > "$T/fake-arbx" <<'FAKE'
#!/bin/bash
cmd=$1; shift
case "$cmd" in
  check) echo "fake check $*"; exit 0 ;;
  provenance)
    conf=$2
    mode=$(grep -E '^mode *=' "$conf" | head -1 | sed 's/^[^"]*"\([^"]*\)".*/\1/')
    sha=$(sha256sum "$conf" | cut -c1-64)
    sock=true; grep -qE '^socket *= *false' "$conf" && sock=false
    echo "{\"schema\":\"arbx.provenance/1.0\",\"config\":{\"mode\":\"$mode\",\"file_sha256\":\"$sha\",\"normalized_sha256\":\"norm-$sha\"},\"control\":{\"socket\":$sock}}"
    exit 0 ;;
  wallet) read -r _; exit 0 ;;
  ctl)  # ctl --run <dir> <cmd> --who <w> --why <y>; the segment's behaviour is in <dir>/.fake-ctl
    run=$2; c=$3; why=""
    while [ $# -gt 0 ]; do [ "$1" = --why ] && why=$2; shift; done
    echo "$c|$why" >> "$FAKE_DIR/ctl.log"
    b=$(cat "$run/.fake-ctl" 2>/dev/null)
    case "$b:$c" in
      fail:*) echo "Error: connecting to $run/control.sock (is the run alive?)" >&2; exit 1 ;;
      refuse-pause:pause-sending) printf '{\n  "accepted": false,\n  "result": "refused for the test",\n  "send_gate": {"mode": "live", "sticky": false}\n}\n'; exit 2 ;;
      refuse-resume:resume-sending) printf '{\n  "accepted": false,\n  "result": "shadow for the rest of the segment (control): restart to send",\n  "send_gate": {"mode": "shadow", "sticky": true, "reason": "control"}\n}\n'; exit 2 ;;
      sticky:pause-sending) echo '{"accepted":true,"result":"shadow","note":"already shadow","send_gate":{"mode":"shadow","sticky":true,"reason":"program_hash_mismatch"}}'; exit 0 ;;
    esac
    [ "$c" = stop ] && [ "$b" != ignore ] && touch "$run/.fake-stop"
    echo '{"accepted":true,"result":"shadow","send_gate":{"mode":"shadow","sticky":false,"reason":"control"}}'; exit 0 ;;
  run)
    flag=none; budget=""; conf=""; name=""; cdir=""; envf=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --config) conf=$2; shift ;; --name) name=$2; shift ;; --campaign-dir) cdir=$2; shift ;; --budget-left) budget=$2; shift ;;
        --env-file) envf=$2; shift ;; --minutes) shift ;; --live|--shadow) flag=$1 ;;
      esac; shift
    done
    i=$(( $(cat "$FAKE_DIR/runs.log" 2>/dev/null | wc -l) + 1 ))
    echo "seg=$i name=$name budget=$budget flag=$flag config=$conf config_sha=$(sha256sum "$conf" | cut -c1-64) bin=$0 env=$envf" >> "$FAKE_DIR/runs.log"
    # plan line: <exit code> <stop reason|none> <status lines|-|garbage|array|nofield|empty> [wait|ignore|-] [ctl behaviour|-] [secondary]
    read -r rc reason status wait behave second < <(sed -n "${i}p" "$FAKE_PLAN")
    d=$cdir/$name; mkdir -p "$d"
    [ -n "${behave:-}" ] && [ "$behave" != - ] && echo "$behave" > "$d/.fake-ctl"
    gmode=shadow; greason=mode_shadow; [ "$flag" = --shadow ] && greason=forced_shadow; [ "$flag" = --live ] && { gmode=live; greason=""; }
    [ "${behave:-}" = mismatch ] && { gmode=shadow; greason=program_hash_mismatch; }
    echo "{\"schema\":\"arbx.meta/2.0\",\"send_gate\":{\"mode\":\"$gmode\",\"reason\":\"$greason\",\"sticky\":true}}" > "$d/meta.json"
    case "$status" in
      -|"") ;;
      empty) : > "$d/status.jsonl" ;;
      array) echo '[1,2]' > "$d/status.jsonl" ;;
      nofield) echo '{"slot":1}' > "$d/status.jsonl" ;;
      garbage) echo '{"exec":{"sending":{"failed_fees_lamports":1}}}' > "$d/status.jsonl"; echo '{"exec":{"send' >> "$d/status.jsonl"; echo '{"attempt":1}' > "$d/attempts.jsonl" ;;
      v2:*) IFS=, read -ra xs <<< "${status#v2:}"; for x in "${xs[@]}"; do echo "{\"money\":{\"failed_fees_total_lamports\":$x}}" >> "$d/status.jsonl"; done ;;
      *) IFS=, read -ra xs <<< "$status"; for x in "${xs[@]}"; do echo "{\"exec\":{\"sending\":{\"failed_fees_lamports\":$x}}}" >> "$d/status.jsonl"; done ;;
    esac
    if [ "${wait:-}" = wait ]; then
      # until `ctl stop` or SIGINT. A background job of a non-interactive bash starts with SIGINT ignored, which a bash
      # script cannot undo: python (same pid, through exec) can, as the real binary's signal handler does
      exec python3 -c '
import json, os, signal, sys, time
d = sys.argv[1]; got = []
signal.signal(signal.SIGINT, lambda *a: got.append(1))
for _ in range(300):
    if got or os.path.exists(os.path.join(d, ".fake-stop")): break
    time.sleep(0.1)
json.dump({"schema": "arbx.stop/1.0", "reason": "signal" if got else "control", "exit_code": 10, "secondary": None}, open(os.path.join(d, "stop.json"), "w"))
sys.exit(10)' "$d"
    elif [ "${wait:-}" = ignore ]; then
      trap '' INT
      for _ in $(seq 1 300); do sleep 0.1; done
      exit 99
    fi
    sec=null; [ -n "${second:-}" ] && { sec="{\"reason\":\"$second\",\"detail\":\"x\"}"; rc=30; }
    [ "$reason" != none ] && echo "{\"schema\":\"arbx.stop/1.0\",\"reason\":\"$reason\",\"exit_code\":$rc,\"secondary\":$sec}" > "$d/stop.json"
    exit "$rc" ;;
  *) echo "fake arbx: unknown $cmd" >&2; exit 1 ;;
esac
FAKE
chmod +x "$T/fake-arbx"
printf 'config_version = 2\nout_dir = "/nowhere"\nmode = "live"\nwallet = "w"\n# a comment the supervisor must keep\n' > "$T/live.toml"
LIVE_SHA=$(sha256sum "$T/live.toml" | cut -c1-64)
FAKE_SHA=$(sha256sum "$T/fake-arbx" | cut -c1-64)
export ARBX_DRY=1 ARBX_BIN=$T/fake-arbx ARBX_RUNS=$T/runs ARBX_MIN_FREE_GB=0 ARBX_BACKOFF_S=0 ARBX_POLL_S=0.1 ARBX_STOP_INT_S=1 ARBX_STOP_KILL_S=2
mkdir -p "$T/runs"

# campaign <name> <budget> <max segments> <plan lines...>: run the supervisor in the foreground (dry)
campaign() {
  local name=$1 budget=$2 max=$3; shift 3
  export FAKE_DIR=$T/fake-$name FAKE_PLAN=$T/fake-$name/plan
  mkdir -p "$FAKE_DIR"; printf '%s\n' "$@" > "$FAKE_PLAN"
  ARBX_MAX_SEGMENTS=$max "$ROOT/deploy/run-w.sh" "$name" 1 20 "$budget" "$T/live.toml" tester
}
field() { sed -n "${2}p" "$T/fake-$1/runs.log" | tr ' ' '\n' | sed -n "s/^$3=//p"; }

# ------------------------------------------------------------------ A: budget, frozen config and binary
campaign A 5000000 3 "0 deadline 1000000,2000000,3000000" "0 deadline v2:500000,1500000" "0 deadline -"
C=$T/runs/A
check "A: segment 1 gets the whole budget, live" eq "$(field A 1 budget) $(field A 1 flag)" "5000000 --live"
check "A: segment 2 gets budget - last line of p1 (3,000,000), not the sum of its lines (6,000,000)" eq "$(field A 2 budget) $(field A 2 flag)" "2000000 --live"
check "A: segment 3: p2's last line (v2 total 1,500,000) leaves 500,000 < 1M: records only with --shadow" eq "$(field A 3 budget) $(field A 3 flag)" "500000 --shadow"
check "A: every segment runs the frozen config" eq "$(sed 's/.* config=\([^ ]*\) .*/\1/' "$T/fake-A/runs.log" | sort -u)" "$C/config.frozen.toml"
check "A: the frozen config's bytes are the original's, in every segment" eq "$(sed 's/.* config_sha=\([^ ]*\) .*/\1/' "$T/fake-A/runs.log" | sort -u)" "$LIVE_SHA"
check "A: the original config was not edited" eq "$(sha256sum "$T/live.toml" | cut -c1-64)" "$LIVE_SHA"
check "A: the frozen config is read-only" eq "$(stat -c %a "$C/config.frozen.toml")" "444"
check "A: every segment runs the frozen binary arbx-<sha8>" eq "$(sed 's/.* bin=\([^ ]*\) .*/\1/' "$T/fake-A/runs.log" | sort -u)" "$C/arbx-${FAKE_SHA:0:8}"
check "A: the frozen binary is the original's bytes" eq "$(sha256sum "$C/arbx-${FAKE_SHA:0:8}" | cut -c1-64)" "$FAKE_SHA"
check "A: segments name the original config's .env (a path)" eq "$(field A 1 env)" "$T/.env"
check "A: campaign.json: schema, binary, config, budget" eq "$(python3 -c 'import json,sys; v=json.load(open(sys.argv[1])); print((v["schema"], v["binary"]["sha256"]==sys.argv[2], v["config"]["sha256"]==sys.argv[3], v["budget"]["failed_fee_budget_lamports"], v["operator"]))' "$C/campaign.json" "$FAKE_SHA" "$LIVE_SHA")" "('arbx.campaign/1.0', True, True, 5000000, 'tester')"
check "A: campaign.json: 3 natural segments, ended" eq "$(j "$C/campaign.json" '([s["class"] for s in v["segments"]], v["crash_count_15min"], v["ended_ns"] is not None)')" "(['natural', 'natural', 'natural'], 0, True)"
check "A: supervisor.jsonl events" eq "$(jl "$C/supervisor.jsonl" '[x["event"] for x in L]')" "['start', 'segment_start', 'gate', 'segment_end', 'segment_start', 'gate', 'segment_end', 'budget', 'segment_start', 'gate', 'segment_end', 'stop']"
check "A: the send gates (review M2)" eq "$(jl "$C/supervisor.jsonl" '[x["detail"] for x in L if x["event"]=="gate"]')" "['mode=live reason=- flag=--live', 'mode=live reason=- flag=--live', 'mode=shadow reason=forced_shadow flag=--shadow']"
check "A: supervisor.jsonl budget fields" eq "$(jl "$C/supervisor.jsonl" '[(x["budget_left_lamports"], x["budget_src"]) for x in L if x["event"]=="segment_start"]')" "[(5000000, 'status'), (2000000, 'status'), (500000, 'status')]"

# ------------------------------------------------------------------ B: operator stops are not crashes
campaign B 50000000 8 "10 signal -" "10 control -" "10 signal -" "10 signal -" "10 control -" "10 signal -" "10 signal -" "10 signal -"
check "B: 8 operator stops in a row: all 8 segments ran (7 crashes would have ended it)" eq "$(wc -l < "$T/fake-B/runs.log" | tr -d ' ')" "8"
check "B: classed operator, crash count 0" eq "$(j "$T/runs/B/campaign.json" '(set(s["class"] for s in v["segments"]), v["crash_count_15min"], v["end_reason"])')" "({'operator'}, 0, 'max segments (8)')"

# ------------------------------------------------------------------ C: crashes are counted
campaign C 50000000 12 "10 control -" "10 signal -" "30 error -" "30 panic -" "30 error -" "30 error -" "137 none -" "30 error -" "137 none -" "0 deadline -"
check "C: the 7th crash in 15 min ends the campaign (2 operator stops not counted)" eq "$(wc -l < "$T/fake-C/runs.log" | tr -d ' ')" "9"
check "C: classes and count" eq "$(j "$T/runs/C/campaign.json" '([s["class"] for s in v["segments"]], v["crash_count_15min"], v["end_reason"])')" "(['operator', 'operator', 'crash', 'crash', 'crash', 'crash', 'crash', 'crash', 'crash'], 7, 'crash limit: 7 crashes in 15 min')"
check "C: a segment killed without stop.json is a crash" eq "$(j "$T/runs/C/campaign.json" '(v["segments"][6]["exit_code"], v["segments"][6]["stop_reason"])')" "(137, None)"

# ------------------------------------------------------------------ D: exit 20 ends the campaign
campaign D 50000000 5 "0 deadline -" "20 equity_day -" "0 deadline -"
check "D: a safety stop (exit 20) ends the campaign" eq "$(wc -l < "$T/fake-D/runs.log" | tr -d ' ')" "2"
check "D: classed safety" eq "$(j "$T/runs/D/campaign.json" '([s["class"] for s in v["segments"]], v["end_reason"])')" "(['natural', 'safety'], 'safety stop in D-p2 (equity_day)')"

# ------------------------------------------------------------------ E: an unreadable last status line: records only
campaign E 50000000 2 "0 deadline garbage" "0 deadline -"
check "E: unknown spend (p1's last line unreadable, it sent): p2 records only" eq "$(field E 2 flag) $(field E 2 budget)" "--shadow 0"
check "E: budget_src unknown" eq "$(jl "$T/runs/E/supervisor.jsonl" '[x["budget_src"] for x in L if x["event"]=="segment_start"]')" "['status', 'unknown']"

# ------------------------------------------------------------------ F: control files while a segment runs
export FAKE_DIR=$T/fake-F FAKE_PLAN=$T/fake-F/plan
mkdir -p "$FAKE_DIR"; printf '%s\n' "0 deadline - wait" "0 deadline - wait" "0 deadline - wait" > "$FAKE_PLAN"
ARBX_MAX_SEGMENTS=3 "$ROOT/deploy/run-w.sh" F 1 20 50000000 "$T/live.toml" tester & SUP=$!
check "F: segment 1 starts" wait_for '[ -s "$T/fake-F/runs.log" ]'
echo "checking fills" > "$T/runs/F.pause"
check "F: .pause pauses the running segment's sending" wait_for 'grep -q "^pause-sending|pause file: checking fills" "$T/fake-F/ctl.log" 2>/dev/null'
rm -f "$T/runs/F.pause"
check "F: removing it resumes sending" wait_for 'grep -q "^resume-sending|" "$T/fake-F/ctl.log" 2>/dev/null'
echo "restart for the test" > "$T/runs/F.next"
check "F: .next stops the segment with its reason, and the next one starts" wait_for '[ "$(wc -l < "$T/fake-F/runs.log")" -ge 2 ]'
check "F: the stop went through ctl with the reason" eq "$(grep '^stop|' "$T/fake-F/ctl.log" | head -1)" "stop|next: restart for the test"
check "F: .next was consumed" test ! -e "$T/runs/F.next"
echo "end of the test" > "$T/runs/F.stop"
check "F: .stop ends the campaign" wait_for '! kill -0 $SUP 2>/dev/null'
wait "$SUP" 2>/dev/null
check "F: two segments, both operator stops" eq "$(j "$T/runs/F/campaign.json" '([(s["class"], s["stop_reason"]) for s in v["segments"]], v["end_reason"])')" "([('operator', 'control'), ('operator', 'control')], 'stop file: end of the test')"
check "F: control.jsonl (src file): pause, resume, next, stop" eq "$(jl "$T/runs/F/control.jsonl" '[(x["src"], x["cmd"], x["accepted"]) for x in L]')" "[('file', 'pause-sending', True), ('file', 'resume-sending', True), ('file', 'next', True), ('file', 'stop', True)]"
check "F: the reasons are recorded" eq "$(jl "$T/runs/F/control.jsonl" '[x["why"] for x in L if x["cmd"] in ("next", "stop")]')" "['restart for the test', 'end of the test']"

# ------------------------------------------------------------------ G: .pause between segments: records only (review M1)
export FAKE_DIR=$T/fake-G FAKE_PLAN=$T/fake-G/plan
mkdir -p "$FAKE_DIR"; printf '%s\n' "0 deadline - wait" "0 deadline - wait" > "$FAKE_PLAN"
echo "wait for the owner" > "$T/runs/G.pause"
ARBX_MAX_SEGMENTS=2 "$ROOT/deploy/run-w.sh" G 1 20 50000000 "$T/live.toml" tester & SUP=$!
check "G: a segment starts while paused" wait_for '[ -s "$T/fake-G/runs.log" ]'
check "G: ... with --shadow (records only, nothing sent)" eq "$(field G 1 flag)" "--shadow"
check "G: no pause-sending to a records-only segment" test ! -e "$T/fake-G/ctl.log"
rm -f "$T/runs/G.pause"
check "G: when the file goes, the records-only segment is restarted and the next one sends" wait_for '[ "$(wc -l < "$T/fake-G/runs.log")" -ge 2 ]'
check "G: segment 2 runs --live" eq "$(field G 2 flag)" "--live"
echo "end" > "$T/runs/G.stop"
check "G: the campaign ends" wait_for '! kill -0 $SUP 2>/dev/null'
wait "$SUP" 2>/dev/null
check "G: the restart went through ctl stop" eq "$(grep -c '^stop|pause lifted' "$T/fake-G/ctl.log")" "1"
check "G: supervisor.jsonl pause, then resume of p1" eq "$(jl "$T/runs/G/supervisor.jsonl" '[(x["event"], x["segment"]) for x in L if x["event"] in ("pause", "resume")]')" "[('pause', None), ('resume', 'G-p1')]"
check "G: control.jsonl: pause (records only), resume (restart)" eq "$(jl "$T/runs/G/control.jsonl" '[(x["cmd"], x["accepted"], x["result"]) for x in L][:2]')" "[('pause-sending', True, 'segments record only (--shadow) while the file exists'), ('resume-sending', True, 'segment G-p1 (records only) restarted: the next one sends')]"

# ------------------------------------------------------------------ I: a refused pause falls back to a records-only restart (review F3)
export FAKE_DIR=$T/fake-I FAKE_PLAN=$T/fake-I/plan
mkdir -p "$FAKE_DIR"; printf '%s\n' "0 deadline - wait refuse-pause" "0 deadline - wait" "0 deadline - wait" > "$FAKE_PLAN"
ARBX_MAX_SEGMENTS=3 "$ROOT/deploy/run-w.sh" I 1 20 50000000 "$T/live.toml" tester & SUP=$!
check "I: segment 1 starts --live" wait_for '[ -s "$T/fake-I/runs.log" ]'
echo "stop sending" > "$T/runs/I.pause"
check "I: after 3 refused pauses the segment is stopped, the next records only" wait_for '[ "$(wc -l < "$T/fake-I/runs.log")" -ge 2 ]'
check "I: p2 runs --shadow while the file exists" eq "$(field I 1 flag) $(field I 2 flag)" "--live --shadow"
check "I: three pause attempts, then the stop" eq "$(grep -c '^pause-sending|' "$T/fake-I/ctl.log") $(grep -c '^stop|pause not confirmed' "$T/fake-I/ctl.log")" "3 1"
check "I: the refusal is logged once (supervisor.jsonl pause_failed, control.jsonl accepted false)" eq "$(jl "$T/runs/I/supervisor.jsonl" '[x["detail"] for x in L if x["event"]=="pause_failed"]') $(jl "$T/runs/I/control.jsonl" '[(x["cmd"], x["accepted"]) for x in L][:2]')" "['refused for the test'] [('pause-sending', False), ('next', True)]"
check "I: supervisor.log says so" grep -q "PAUSE NOT CONFIRMED: refused for the test" "$T/runs/I/supervisor.log"
rm -f "$T/runs/I.pause"
check "I: the pause gone, p2 is restarted and p3 sends" wait_for '[ "$(wc -l < "$T/fake-I/runs.log")" -ge 3 ]'
check "I: p3 runs --live" eq "$(field I 3 flag)" "--live"
echo "end" > "$T/runs/I.stop"
check "I: the campaign ends" wait_for '! kill -0 $SUP 2>/dev/null'
wait "$SUP" 2>/dev/null

# ------------------------------------------------------------------ J: no control socket at all: the pause and the stop fail, SIGINT
export FAKE_DIR=$T/fake-J FAKE_PLAN=$T/fake-J/plan
mkdir -p "$FAKE_DIR"; printf '%s\n' "0 deadline - wait fail" "0 deadline - wait" > "$FAKE_PLAN"
ARBX_MAX_SEGMENTS=2 "$ROOT/deploy/run-w.sh" J 1 20 50000000 "$T/live.toml" tester & SUP=$!
check "J: segment 1 starts" wait_for '[ -s "$T/fake-J/runs.log" ]'
echo "stop sending" > "$T/runs/J.pause"
check "J: the unreachable segment is stopped (SIGINT), the next records only" wait_for '[ "$(wc -l < "$T/fake-J/runs.log")" -ge 2 ]'
check "J: p2 --shadow" eq "$(field J 2 flag)" "--shadow"
check "J: the failure is named" eq "$(jl "$T/runs/J/supervisor.jsonl" '[x["detail"].startswith("ctl failed (exit 1): Error: connecting to") for x in L if x["event"]=="pause_failed"]')" "[True]"
echo "end" > "$T/runs/J.stop"; rm -f "$T/runs/J.pause"
check "J: the campaign ends" wait_for '! kill -0 $SUP 2>/dev/null'
wait "$SUP" 2>/dev/null
check "J: p1 stopped by SIGINT (operator), not a crash" eq "$(j "$T/runs/J/campaign.json" '[(s["class"], s["stop_reason"]) for s in v["segments"]][0]')" "('operator', 'signal')"

# ------------------------------------------------------------------ K: a segment already shadow (program_hash_mismatch) confirms the pause without change
export FAKE_DIR=$T/fake-K FAKE_PLAN=$T/fake-K/plan
mkdir -p "$FAKE_DIR"; printf '%s\n' "0 deadline - wait sticky" > "$FAKE_PLAN"
ARBX_MAX_SEGMENTS=1 "$ROOT/deploy/run-w.sh" K 1 20 50000000 "$T/live.toml" tester & SUP=$!
check "K: segment 1 starts" wait_for '[ -s "$T/fake-K/runs.log" ]'
echo "check" > "$T/runs/K.pause"
check "K: the pause is confirmed once" wait_for 'grep -q "the pause changes nothing" "$T/runs/K/supervisor.log"'
rm -f "$T/runs/K.pause"
check "K: removing it: no resume asked, the segment stays shadow" wait_for 'grep -q "stays shadow (program_hash_mismatch)" "$T/runs/K/supervisor.log"'
echo "end" > "$T/runs/K.stop"
check "K: the campaign ends" wait_for '! kill -0 $SUP 2>/dev/null'
wait "$SUP" 2>/dev/null
check "K: one pause-sending, no resume-sending" eq "$(grep -c '^pause-sending|' "$T/fake-K/ctl.log") $(grep -c '^resume-sending|' "$T/fake-K/ctl.log")" "1 0"

# ------------------------------------------------------------------ L: a refused resume restarts the segment
export FAKE_DIR=$T/fake-L FAKE_PLAN=$T/fake-L/plan
mkdir -p "$FAKE_DIR"; printf '%s\n' "0 deadline - wait refuse-resume" "0 deadline - wait" > "$FAKE_PLAN"
ARBX_MAX_SEGMENTS=2 "$ROOT/deploy/run-w.sh" L 1 20 50000000 "$T/live.toml" tester & SUP=$!
check "L: segment 1 starts" wait_for '[ -s "$T/fake-L/runs.log" ]'
echo "check" > "$T/runs/L.pause"
check "L: paused" wait_for 'grep -q "sending paused" "$T/runs/L/supervisor.log"'
rm -f "$T/runs/L.pause"
check "L: the refused resume restarts the segment; the next one sends" wait_for '[ "$(wc -l < "$T/fake-L/runs.log")" -ge 2 ]'
check "L: p2 --live, resume_failed logged" eq "$(field L 2 flag) $(jl "$T/runs/L/supervisor.jsonl" '[x["event"] for x in L if x["event"]=="resume_failed"]')" "--live ['resume_failed']"
echo "end" > "$T/runs/L.stop"
check "L: the campaign ends" wait_for '! kill -0 $SUP 2>/dev/null'
wait "$SUP" 2>/dev/null

# ------------------------------------------------------------------ M: a segment that ignores the stop: SIGINT, then SIGKILL (a crash)
export FAKE_DIR=$T/fake-M FAKE_PLAN=$T/fake-M/plan
mkdir -p "$FAKE_DIR"; printf '%s\n' "0 deadline - ignore ignore" > "$FAKE_PLAN"
ARBX_MAX_SEGMENTS=1 "$ROOT/deploy/run-w.sh" M 1 20 50000000 "$T/live.toml" tester & SUP=$!
check "M: segment 1 starts" wait_for '[ -s "$T/fake-M/runs.log" ]'
echo "restart" > "$T/runs/M.next"
check "M: SIGINT, then SIGKILL; the campaign ends" wait_for '! kill -0 $SUP 2>/dev/null'
wait "$SUP" 2>/dev/null
check "M: the escalation is logged" eq "$(grep -c 'after the stop: SIGINT' "$T/runs/M/supervisor.log") $(grep -c 'after the stop: SIGKILL' "$T/runs/M/supervisor.log")" "1 1"
check "M: killed = crash, no stop reason" eq "$(j "$T/runs/M/campaign.json" '[(s["class"], s["exit_code"], s["stop_reason"]) for s in v["segments"]]')" "[('crash', 137, None)]"

# ------------------------------------------------------------------ N: disk low ends the campaign before a segment starts
export FAKE_DIR=$T/fake-N FAKE_PLAN=$T/fake-N/plan
mkdir -p "$FAKE_DIR"; printf '%s\n' "0 deadline -" > "$FAKE_PLAN"
ARBX_MIN_FREE_GB=999999999 ARBX_MAX_SEGMENTS=1 "$ROOT/deploy/run-w.sh" N 1 20 50000000 "$T/live.toml" tester
check "N: no segment ran" test ! -e "$T/fake-N/runs.log"
check "N: disk_low, then stop" eq "$(jl "$T/runs/N/supervisor.jsonl" '[x["event"] for x in L]') $(j "$T/runs/N/campaign.json" 'v["end_reason"][:9]')" "['start', 'disk_low', 'stop'] disk low "

# ------------------------------------------------------------------ O: one supervisor at a time (review M6)
export FAKE_DIR=$T/fake-O FAKE_PLAN=$T/fake-O/plan
mkdir -p "$FAKE_DIR"; printf '%s\n' "0 deadline - wait" > "$FAKE_PLAN"
ARBX_MAX_SEGMENTS=1 "$ROOT/deploy/run-w.sh" O 1 20 50000000 "$T/live.toml" tester & SUP=$!
check "O: the first campaign runs" wait_for '[ -s "$T/fake-O/runs.log" ]'
check "O: a second campaign is refused while it runs" bash -c '! "$0" O2 1 20 1 "$1" tester 2>"$2/o2.err" && grep -q "another campaign supervisor" "$2/o2.err"' "$ROOT/deploy/run-w.sh" "$T/live.toml" "$T"
check "O: ... and leaves nothing behind" test ! -e "$T/runs/O2"
echo "end" > "$T/runs/O.stop"
check "O: the first campaign ends" wait_for '! kill -0 $SUP 2>/dev/null'
wait "$SUP" 2>/dev/null

# ------------------------------------------------------------------ P: budget reading that cannot be trusted: records only (review M4)
campaign P 50000000 3 "0 deadline -" "0 deadline array" "0 deadline -"
check "P: p1 never started its engine (no status.jsonl): spent 0, p2 --live" eq "$(field P 2 flag)" "--live"
check "P: p2 (--live) left a last line that is not an object: p3 records only" eq "$(field P 3 flag) $(field P 3 budget)" "--shadow 0"
campaign P2 50000000 2 "0 deadline nofield" "0 deadline -"
check "P2: a --live segment's last line without a failed-fee total: records only" eq "$(field P2 2 flag)" "--shadow"
campaign P3 50000000 2 "0 deadline empty" "0 deadline -"
check "P3: a --live segment whose engine started but wrote no line: records only" eq "$(field P3 2 flag)" "--shadow"
check "P3: the supervisor survived to end the campaign" eq "$(j "$T/runs/P3/campaign.json" 'v["end_reason"]')" "max segments (2)"

# ------------------------------------------------------------------ Q: a crash while stopping is a crash (review M5); a --live segment not sending is a warning (review M2)
campaign Q 50000000 2 "30 signal - - - error" "0 deadline - - mismatch"
check "Q: stop.json secondary: a crash, not an operator stop" eq "$(j "$T/runs/Q/campaign.json" '[(s["class"], s["stop_reason"]) for s in v["segments"]]')" "[('crash', 'signal'), ('natural', 'deadline')]"
check "Q: the warning for a --live segment that does not send" grep -q "WARNING: segment 2 runs with --live but is NOT SENDING: send gate shadow (program_hash_mismatch)" "$T/runs/Q/supervisor.log"

# ------------------------------------------------------------------ H: refusals
check "H: an existing campaign name is refused" bash -c '! "$0" A 1 20 1 "$1" tester 2>/dev/null' "$ROOT/deploy/run-w.sh" "$T/live.toml"
check "H: bad arguments are refused" bash -c '! "$0" "bad name" 1 20 1 "$1" 2>/dev/null' "$ROOT/deploy/run-w.sh" "$T/live.toml"
printf 'config_version = 2\nout_dir = "/nowhere"\nmode = "live"\nwallet = "w"\n[control]\nsocket = false\n' > "$T/nosock.toml"
check "H: a config without the control socket is refused (review F3)" bash -c '! "$0" H1 1 20 1 "$1" tester 2>"$2/h1.err" && grep -q "socket = false" "$2/h1.err" && [ ! -e "$2/runs/H1/campaign.json" ]' "$ROOT/deploy/run-w.sh" "$T/nosock.toml" "$T"

echo "$((N - FAILS)) of $N checks passed"
[ "$FAILS" = 0 ]
