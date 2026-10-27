#!/bin/bash
# ck_remote.sh — Constant-K feed race next to the Shreder recorder, SERVER side (FRA, as root). ZERO COST: the harness
# only subscribes (pump.fun-filtered gRPC streams), never sends anything. Tokens/URLs are never printed or logged.
# Deployed by the host's ck_start.sh to /root/shreder/ck/ (never edit it in place while a race runs: .new + mv).
#   bash ck_remote.sh start [MINUTES=75] [TAG]   generate ck_race.toml from the engine config, start the harness (nice 10,
#                                                oom_score_adj 800 = killed before collect.py / an engine), a watchdog
#                                                (hard stop at MINUTES+3, RSS cap), and return at once
#   bash ck_remote.sh stop                       SIGTERM the harness (SIGKILL after 15 s)
#   bash ck_remote.sh status                     one header line + one line per feed (tx/s last 60 s, last tx age, health)
# Output: /root/shreder/ck/out/race_<TAG>.log (X lines: X feed t_ns slot sig16hex create eidx created_at_ns),
#         race_<TAG>.err (stderr: feed list, H health lines, errors), run_<TAG>.json, watch_<TAG>.log
# Env overrides (tests): CK_DIR, CK_SRC_BIN, CK_FEEDS, CK_RSS_MAX_MB, CK_ENGINE_CFG, CK_ENV_FILE
set -u
D=${CK_DIR:-/root/shreder/ck}
OUT=$D/out
BIN=$D/bin/feed_race
SRC_BIN=${CK_SRC_BIN:-/root/gap/bin/feed_race}
PIDF=$D/race.pid
FEEDS=${CK_FEEDS:-kaldera,turbo-kaldera,kaldera-tx}
RSS_MAX_MB=${CK_RSS_MAX_MB:-500}
cmd=${1:-status}

alive() {   # pid is a live feed_race (not a recycled pid)
  local p=$1
  [ -n "$p" ] && kill -0 "$p" 2>/dev/null && [ "$(cat /proc/$p/comm 2>/dev/null)" = "$(basename "$BIN" | cut -c1-15)" ]
}
read_pidf() { P_PID=; P_TAG=; P_T0=; P_MIN=; [ -s "$PIDF" ] && read -r P_PID P_TAG P_T0 P_MIN < "$PIDF"; return 0; }

case "$cmd" in
install)   # install SRC_DIR: copy ck_remote.sh + make_race_toml.py from SRC_DIR (.new + mv), never while a race runs
  S=${2:?install SRC_DIR}; mkdir -p "$OUT" "$D/bin"
  read_pidf
  if alive "$P_PID"; then echo "deploy: a race is running (pid $P_PID): files NOT replaced"; exit 0; fi
  for f in ck_remote.sh make_race_toml.py; do install -m 700 "$S/$f" "$D/$f.new" && mv "$D/$f.new" "$D/$f" || { echo "deploy: FAILED on $f"; exit 2; }; done
  echo "deploy: ok -> $D (ck_remote.sh $(md5sum "$D/ck_remote.sh" | cut -c1-8))"
  ;;
start)
  MIN=${2:-75}; TAG=${3:-$(date -u +%Y%m%d_%H%M)}
  [[ "$MIN" =~ ^[0-9]+$ ]] && [ "$MIN" -ge 1 ] && [ "$MIN" -le 180 ] || { echo "REFUSED: MINUTES must be 1..180"; exit 2; }
  [[ "$TAG" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "REFUSED: bad TAG"; exit 2; }
  mkdir -p "$OUT" "$D/bin"
  read_pidf
  if alive "$P_PID"; then echo "ALREADY RUNNING: pid $P_PID tag $P_TAG (stop it first)"; exit 1; fi
  [ -e "$OUT/race_$TAG.log" ] && { echo "REFUSED: $OUT/race_$TAG.log exists (pick another TAG)"; exit 2; }
  if [ ! -x "$BIN" ]; then
    [ -x "$SRC_BIN" ] || { echo "REFUSED: no harness binary at $SRC_BIN"; exit 2; }
    cp "$SRC_BIN" "$BIN.new" && chmod 755 "$BIN.new" && mv "$BIN.new" "$BIN" || { echo "REFUSED: could not copy the harness binary"; exit 2; }
  fi
  python3 "$D/make_race_toml.py" "$D/ck_race.toml" --feeds "$FEEDS" > "$OUT/cfg_$TAG.txt" 2>&1 || { cat "$OUT/cfg_$TAG.txt"; echo "REFUSED: race config"; exit 2; }
  cat "$OUT/cfg_$TAG.txt"
  AVAIL=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
  NENG=$(ps -eo comm= | grep -c '^snipe_engine' || true)
  echo "host: $(hostname) | mem available ${AVAIL} MB | snipe_engine processes: $NENG | load $(cut -d' ' -f1-3 /proc/loadavg)"
  [ "${AVAIL:-0}" -ge 400 ] || { echo "REFUSED: only ${AVAIL} MB memory available (need >= 400)"; exit 2; }
  # the harness: own session (survives the ssh), nice 10, oom_score_adj 800 (the kernel kills it before collect.py / an engine)
  setsid nohup bash -c 'echo 800 > /proc/self/oom_score_adj; exec nice -n 10 "$0" "$@"' "$BIN" \
    --config "$D/ck_race.toml" --out "$OUT/race_$TAG.log" --minutes "$MIN" > "$OUT/race_$TAG.err" 2>&1 < /dev/null &
  PID=$!
  T0=$(date +%s)
  echo "$PID $TAG $T0 $MIN" > "$PIDF.new" && mv "$PIDF.new" "$PIDF"
  python3 - "$OUT/run_$TAG.json" "$TAG" "$MIN" "$FEEDS" "$BIN" "$PID" <<'EOF'
import json, sys, time, hashlib, socket
p, tag, mn, feeds, b, pid = sys.argv[1:7]
md5 = hashlib.md5(open(b, "rb").read()).hexdigest()
json.dump({"tag": tag, "minutes": int(mn), "feeds": feeds.split(","), "start_ns": time.time_ns(), "bin": b, "bin_md5": md5,
           "pid": int(pid), "host": socket.gethostname(), "clock": "CLOCK_REALTIME ns (X lines t), chrony-synced"}, open(p, "w"), indent=1)
EOF
  setsid nohup bash "$D/ck_remote.sh" watch "$PID" "$MIN" "$TAG" > "$OUT/watch_$TAG.log" 2>&1 < /dev/null &
  sleep 3
  if alive "$PID"; then echo "STARTED ck race $TAG: pid $PID, $MIN min (self-stop), feeds $FEEDS -> $OUT/race_$TAG.log"
  else echo "FAILED: the harness exited at once:"; sed -E 's#(https?|wss?)://[^ "]+#<URL>#g' "$OUT/race_$TAG.err" | tail -5; exit 1; fi
  ;;
watch)   # internal: hard stop at MIN+3 min, RSS cap; logs one line a minute
  PID=$2; MIN=$3; TAG=$4; END=$(( $(date +%s) + MIN*60 + 180 )); n=0
  while kill -0 "$PID" 2>/dev/null; do
    RSS=$(awk '/VmRSS/{print int($2/1024)}' /proc/$PID/status 2>/dev/null); RSS=${RSS:-0}
    if [ "$RSS" -gt "$RSS_MAX_MB" ]; then echo "$(date -u +%FT%TZ) RSS ${RSS} MB > ${RSS_MAX_MB}: SIGTERM"; kill -TERM "$PID"; sleep 15; kill -KILL "$PID" 2>/dev/null; break; fi
    if [ "$(date +%s)" -gt "$END" ]; then echo "$(date -u +%FT%TZ) past MIN+3: SIGTERM"; kill -TERM "$PID"; sleep 15; kill -KILL "$PID" 2>/dev/null; break; fi
    n=$((n+1)); [ $((n % 6)) -eq 1 ] && echo "$(date -u +%FT%TZ) alive rss ${RSS} MB"
    sleep 10
  done
  echo "$(date -u +%FT%TZ) harness $PID gone"
  ;;
stop)
  read_pidf
  if ! alive "$P_PID"; then echo "not running (last tag ${P_TAG:-none})"; exit 0; fi
  kill -TERM "$P_PID"
  for _ in $(seq 1 15); do alive "$P_PID" || break; sleep 1; done
  if alive "$P_PID"; then kill -KILL "$P_PID"; echo "KILLED (no exit 15 s after SIGTERM): pid $P_PID tag $P_TAG"; else echo "STOPPED: pid $P_PID tag $P_TAG"; fi
  ;;
status)
  read_pidf
  [ -n "$P_TAG" ] || { echo "ck race: never started here ($PIDF missing)"; exit 0; }
  if alive "$P_PID"; then ST="RUNNING pid $P_PID"; else ST="NOT RUNNING"; fi
  python3 - "$OUT/race_$P_TAG.log" "$OUT/race_$P_TAG.err" "$P_TAG" "$ST" "${P_T0:-0}" "${P_MIN:-0}" "$P_PID" <<'EOF'
import os, re, sys, time
log, err, tag, st, t0, mn, pid = sys.argv[1:8]
now = time.time_ns()
rss = "-"
try:
    rss = next((str(int(l.split()[1]) // 1024) for l in open(f"/proc/{pid}/status") if l.startswith("VmRSS")), "-")
except Exception:
    pass
size = os.path.getsize(log) / 1e6 if os.path.exists(log) else 0
el = (time.time() - int(t0)) / 60 if int(t0) else 0
print(f"ck race {tag}: {st} | {el:.1f} of {mn} min | rss {rss} MB | log {size:.1f} MB")
last, n60, feeds = {}, {}, []
if os.path.exists(log):
    with open(log, "rb") as f:
        f.seek(max(0, os.path.getsize(log) - 8_000_000))
        for raw in f:
            p = raw.split(b"\t")
            if len(p) < 4 or p[0] != b"X":
                continue
            try:
                fd, t = p[1].decode(), int(p[2])
            except ValueError:
                continue
            if fd not in last:
                feeds.append(fd)
            last[fd] = max(last.get(fd, 0), t)
            if now - t <= 60e9:
                n60[fd] = n60.get(fd, 0) + 1
health, errs = {}, []
if os.path.exists(err):
    for l in open(err, errors="replace"):
        l = l.rstrip("\n")
        if l.startswith("H\t"):
            p = l.split("\t")
            if len(p) >= 4:
                health[p[1]] = " ".join(x for x in p[3].split() if x.startswith(("reconnects=", "errors=")))
        elif l.startswith("feed_race: feed "):
            fd = l.split()[2]
            if fd not in feeds:
                feeds.append(fd)
        elif l.strip() and "done" not in l:
            errs.append(re.sub(r"(https?|wss?)://\S+", "<URL>", l)[:160])
for fd in feeds:
    age = (now - last[fd]) / 1e9 if fd in last else None
    conn = "connected" if age is not None and age < 15 else ("NO DATA YET" if age is None else f"SILENT {age:.0f} s")
    if not st.startswith("RUNNING"):
        conn = "stopped" if age is not None else "stopped, never delivered"
    print(f"  {fd:<14} {n60.get(fd, 0) / 60:6.1f} tx/s (60 s) | last tx {'-' if age is None else f'{age:.1f} s'} ago | {conn}"
          f"{' | ' + health[fd] if fd in health else ''}")
if errs:
    print("  last error:", errs[-1])
EOF
  ;;
*) echo "usage: ck_remote.sh start [MINUTES] [TAG] | stop | status | install SRC_DIR"; exit 2;;
esac
