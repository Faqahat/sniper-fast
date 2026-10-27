#!/usr/bin/env bash
# QUIET BOOK PUSH (dip21; owner 10-27 PM: "keep the 24 h whale dump history on the host and give it to every node at engine start").
# Runs after each keeper pass and book build (ops/collect/keeper_loop.sh.quietbook). For every node in ops/collect/nodes.txt:
#   the book   /home/moiz/sniper-data/quiet_book/quiet_book.jsonl (built by quiet_book) -> /root/dip/quiet_book.jsonl:
#              rsync (delta + compressed: only the new lines travel) to a private stage dir on the node (/tmp/quiet_book), its
#              sha256 checked there, then `sudo install -m 644` to /root/dip/quiet_book.jsonl.new and `sudo mv -f` over the book
#              (a rename: an engine starting at that moment reads the old book or the new one, never a mix); skipped when the
#              node already has these bytes
#   the lists  cohort_train.json and fbots_frozen.json (the host's masters) -> /root/dip/, the same way, only when the node's
#              sha256 differs, and only a valid list (a non-empty JSON array of 32-byte base58 wallets)
# Prints one status line (also appended to the log). Exit 0 = every node has the book and the book is fresh; 1 = alert: the book
# is stale (older than QB_STALE_MIN: the engines will not turn the arm rule on from it; pushed anyway), missing or not a book
# (nothing pushed), or a master list is invalid (not pushed); 2 = a node could not be updated (unreachable, rsync or install
# failed: it keeps its previous files). Never deletes anything on a node; never touches a running engine.
# Overrides (tests): QB_BOOK QB_NODES QB_LOG QB_COHORT QB_FBOTS QB_DEST QB_STAGE QB_STALE_MIN QB_WORK, QB_LOCAL=1 (no ssh: each
# node is this machine; {node} in QB_DEST / QB_STAGE is its name), QB_SUDO (default sudo; "" in a local test).
set -u
ROOT=/home/moiz/sniper
BOOK=${QB_BOOK:-/home/moiz/sniper-data/quiet_book/quiet_book.jsonl}
NODES=${QB_NODES:-$ROOT/ops/collect/nodes.txt}
LOG=${QB_LOG:-/home/moiz/sniper-data/quiet_book/push.log}
COHORT=${QB_COHORT:-$ROOT/ops/overnight/sel/cohort_train.json}
FBOTS=${QB_FBOTS:-$ROOT/ops/strategies/presend/filter/fbots_frozen.json}
DEST=${QB_DEST:-/root/dip}
STAGE=${QB_STAGE:-/tmp/quiet_book}
STALE_MIN=${QB_STALE_MIN:-30}
WORK=${QB_WORK:-/home/moiz/sniper-data/quiet_book/push_work}
LOCAL=${QB_LOCAL:-}
SUDO=${QB_SUDO-sudo}
SSHO=(-o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=15)
mkdir -p "$WORK" "$(dirname "$LOG")"
exec 9> "$WORK/push.lock"
if ! flock -n 9; then echo "quiet_book_push: another push is running: skipped"; exit 0; fi
say() { echo "$1"; echo "$(date -u +%FT%TZ) $1" >> "$LOG"; }

# ---- the book: a private snapshot (the builder may rename a new one in meanwhile), its end, its age
rc=0
snap=$WORK/quiet_book.jsonl
book_ok=
if [ -s "$BOOK" ] && cp "$BOOK" "$snap.tmp" 2>/dev/null && mv -f "$snap.tmp" "$snap"; then
  end_ns=$(tail -n 1 "$snap" | grep -o '"k":"stop","t":[0-9]*' | grep -o '[0-9]*$')
  if [ -n "$end_ns" ]; then book_ok=1; fi
fi
if [ -z "$book_ok" ]; then
  say "quiet_book_push: NO BOOK at $BOOK (missing, empty or not a book: its last line is not a session's stop) | nothing pushed"
  exit 1
fi
bsha=$(sha256sum "$snap" | cut -c1-64)
bsize=$(stat -c %s "$snap")
ndumps=$(grep -c '"k":"d"' "$snap")
end_s=$(( end_ns / 1000000000 ))
age_min=$(( ($(date +%s) - end_s) / 60 ))
head="book $(awk -v b="$bsize" 'BEGIN {printf "%.2f MB", b / 1e6}'), $ndumps dumps, to $(TZ=Asia/Karachi date -d @"$end_s" +%H:%M) PKT ($age_min min old), sha ${bsha:0:8}"
if [ "$age_min" -gt "$STALE_MIN" ]; then head="$head STALE (> $STALE_MIN min: the engines will warm up)"; rc=1; fi

# ---- the lists: pushed only when valid and changed
valid_list() {
  python3 -I - "$1" <<'PY' 2>/dev/null
import json, sys
A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(s):
    n = 0
    for c in s: n = n * 58 + A.index(c)
    return b"\0" * (len(s) - len(s.lstrip("1"))) + (n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b"")
v = json.load(open(sys.argv[1]))
assert isinstance(v, list) and v and all(isinstance(w, str) and len(b58(w)) == 32 for w in v)
PY
}
declare -A LSHA=()
lists=()
for f in "$COHORT" "$FBOTS"; do
  n=$(basename "$f")
  if valid_list "$f"; then LSHA[$n]=$(sha256sum "$f" | cut -c1-64); lists+=("$f"); else head="$head | $n INVALID on the host: not pushed"; rc=1; fi
done

# ---- per node
on_node() {  # name host port user cmd
  if [ -n "$LOCAL" ]; then bash -c "$5"; else ssh -p "$3" "${SSHO[@]}" "$4@$2" "$5" < /dev/null; fi
}
send() {  # name host port user src dst -> bytes on the wire (stdout); non-zero on failure
  local out
  # -I: always send (the delta algorithm against the node's staged copy: only what changed travels), never a size/time skip
  if [ -n "$LOCAL" ]; then out=$(rsync -I --no-whole-file --stats --no-human-readable "$5" "$6" 2>&1) || return 1
  else out=$(rsync -Iz --stats --no-human-readable -e "ssh -p $3 ${SSHO[*]}" "$5" "$4@$2:$6" 2>&1 < /dev/null) || return 1; fi
  echo "$out" | awk '/^Total bytes sent:/ {s = $4} /^Total bytes received:/ {r = $4} END {gsub(",", "", s); gsub(",", "", r); print s + r}'
}
parts=()
while read -r name host port user _ <&3; do   # fd 3: ssh / rsync must not eat the node list from stdin
  case "$name" in ""|\#*) continue;; esac
  d=${DEST//\{node\}/$name}; st=${STAGE//\{node\}/$name}
  # one call: the stage dir, what the node has now
  have=$(on_node "$name" "$host" "$port" "$user" "umask 077; mkdir -p '$st' 2>/dev/null && $SUDO sha256sum '$d/quiet_book.jsonl' '$d/cohort_train.json' '$d/fbots_frozen.json' 2>/dev/null; echo REACHED")
  if ! echo "$have" | grep -q '^REACHED$'; then parts+=("$name UNREACHABLE"); rc=2; continue; fi
  todo=(); wire=0; what=()
  if ! echo "$have" | grep -q "^$bsha  $d/quiet_book.jsonl\$"; then
    if b=$(send "$name" "$host" "$port" "$user" "$snap" "$st/quiet_book.jsonl"); then todo+=("quiet_book.jsonl:$bsha"); wire=$(( wire + b )); what+=("book pushed")
    else parts+=("$name book rsync FAILED"); rc=2; continue; fi
  else what+=("book same"); fi
  for f in "${lists[@]}"; do
    n=$(basename "$f")
    if echo "$have" | grep -q "^${LSHA[$n]}  $d/$n\$"; then continue; fi
    if b=$(send "$name" "$host" "$port" "$user" "$f" "$st/$n"); then todo+=("$n:${LSHA[$n]}"); wire=$(( wire + b )); what+=("$n pushed")
    else what+=("$n rsync FAILED"); rc=2; fi
  done
  if [ ${#todo[@]} -gt 0 ]; then
    # one call: each staged file checked, installed beside its target and renamed over it, then read back
    cmd="$SUDO mkdir -p '$d' || exit 1; ok=1"
    for x in "${todo[@]}"; do
      n=${x%%:*}; s=${x#*:}
      cmd="$cmd; if echo '$s  $st/$n' | sha256sum -c --status && $SUDO install -m 644 '$st/$n' '$d/$n.new' && $SUDO mv -f '$d/$n.new' '$d/$n' && $SUDO sha256sum '$d/$n' | grep -q '^$s '; then echo 'OK $n'; else echo 'FAIL $n'; ok=0; fi"
    done
    res=$(on_node "$name" "$host" "$port" "$user" "$cmd; echo DONE")
    if ! echo "$res" | grep -q '^DONE$' || echo "$res" | grep -q '^FAIL'; then
      parts+=("$name INSTALL FAILED ($(echo "$res" | grep '^FAIL' | cut -c6- | tr '\n' ' ')): it keeps its previous files"); rc=2; continue
    fi
  fi
  lst="lists same"; for w in "${what[@]}"; do case "$w" in *.json*) lst=;; esac; done
  parts+=("$name $(printf '%s, ' "${what[@]}" | sed 's/, $//')${lst:+, $lst} ($(awk -v b="$wire" 'BEGIN {printf "%.1f KB", b / 1e3}') on the wire)")
done 3< "$NODES"
line="quiet_book_push: $head"
for p in "${parts[@]}"; do line="$line | $p"; done
say "$line"
exit $rc
