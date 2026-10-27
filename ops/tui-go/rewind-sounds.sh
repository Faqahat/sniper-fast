#!/bin/bash
# REWIND sounds: run this on your Mac. It plays a different sound for every closed trade of the live run:
#   big win (>= +0.05 SOL) Hero · win Glass · fee-only (about -0.016) Tink · loss Basso · big loss (<= -0.05) Sosumi.
# It reads the run's log over SSH (read-only) and plays the sounds locally with afplay. Ctrl-C stops it.
# Use:      bash rewind-sounds.sh                 (Amsterdam)
#           NODE=84.32.100.36 bash rewind-sounds.sh   (Frankfurt)
# Options (environment): NODE PORT SSHUSER VOL (0.0-1.0, default 0.6) WIN LOSS BIGWIN BIGLOSS FLAT (sound files) BIG (0.05)
# Any sound in /System/Library/Sounds works: Basso Blow Bottle Frog Funk Glass Hero Morse Ping Pop Purr Sosumi Submarine Tink.
# Mute the bell in dipmon with `m` if you use this instead.
NODE=${NODE:-84.32.104.202}; PORT=${PORT:-1996}; SSHUSER=${SSHUSER:-it}; VOL=${VOL:-0.6}; BIG=${BIG:-0.05}
S=/System/Library/Sounds
WIN=${WIN:-$S/Glass.aiff}; LOSS=${LOSS:-$S/Basso.aiff}; BIGWIN=${BIGWIN:-$S/Hero.aiff}; BIGLOSS=${BIGLOSS:-$S/Sosumi.aiff}; FLAT=${FLAT:-$S/Tink.aiff}
command -v afplay >/dev/null 2>&1 || { echo "afplay not found: run this on your Mac"; exit 1; }
play() { afplay -v "$VOL" "$1" >/dev/null 2>&1 & }
echo "REWIND sounds: listening to the live run on $NODE (Ctrl-C to stop) ..."
play "$S/Pop.aiff"
while true; do
  # the newest run log on the node (the live run), followed from now on; only closed trades
  ssh -p "$PORT" -o ServerAliveInterval=30 -o ConnectTimeout=15 "$SSHUSER@$NODE" \
    'L=$(sudo ls -t /root/prod/runs/ 2>/dev/null | grep -E "^dip_.*r[0-9]+\.log$" | head -1); [ -n "$L" ] || exit 3; echo "#RUN $L";
     sudo tail -n 0 -F "/root/prod/runs/$L" | grep --line-buffered -E "PRESEND LIVE REALIZED|^ *REALIZED mint="' |
  while IFS= read -r line; do
    case "$line" in
      "#RUN "*) echo "following ${line#\#RUN }"; continue;;
    esac
    # the trade's P&L in SOL: "PRESEND LIVE REALIZED <mint> +0.0123 SOL" or "REALIZED mint=<mint> pnl=-0.0123 SOL"
    v=$(printf '%s\n' "$line" | sed -nE 's/.*pnl=([+-][0-9.]+) SOL.*/\1/p; s/.*PRESEND LIVE REALIZED [^ ]+ ([+-][0-9.]+) SOL.*/\1/p' | head -1)
    [ -n "$v" ] || continue
    kind=$(awk -v v="$v" -v b="$BIG" 'BEGIN { if (v >= b) print "BIGWIN"; else if (v > 0) print "WIN"; else if (v >= -0.0162 && v <= -0.0155) print "FLAT"; else if (v <= -b) print "BIGLOSS"; else print "LOSS" }')
    type=$(case "$line" in *PRESEND*) echo "pre-send";; *) echo "regular";; esac)
    printf '%s  %-8s %-8s %s SOL\n' "$(date +%H:%M:%S)" "$type" "$kind" "$v"
    case "$kind" in
      BIGWIN) play "$BIGWIN";; WIN) play "$WIN";; FLAT) play "$FLAT";; BIGLOSS) play "$BIGLOSS";; *) play "$LOSS";;
    esac
  done
  echo "connection ended; reconnecting in 5 s (Ctrl-C to stop)"; sleep 5
done
