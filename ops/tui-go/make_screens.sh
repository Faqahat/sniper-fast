#!/bin/sh
# Text screenshots for ops/tui-go/screens (dipmon --screens renders each page off-screen at a size; no terminal needed),
# all from AMS r27 (the first dip20 run, with real QUIET lines):
#   ended/   r27 finished: every tab + help + a trade's details + the splash + the today card, at 200x35 160x50 80x24 50x30
#   live/    r27 replayed to 60% of its time and shown RUNNING at that instant (every tab, the same sizes)
#   warmup/  r27 at 10% of its time: the QUIET skip rule still warming up (the countdown), overview / pre-send / config
#   r28/     r28 (the latency run): Pre-send (LATENCY), Trades (d→land / s→seen / blk) and a fill's details, 200x35 + 50x30
#   filters/ the Filters tab (8) on AMS r40 (internal/core/testdata/filters: r40 trimmed to the table's records, the
#            ledger seed copy), 200x45 120x40 80x30 50x30
# .txt = plain text; .ans = the same with the colors (view with `cat` in a terminal, or `less -R`).
#   png/     a few of the .ans drawn as images (tests/ans2png.py: DejaVu Sans Mono on a dark background, roughly what a
#            terminal shows; for a phone), when Python has PIL
set -e
cd "$(dirname "$0")"
BIN=${DIPMON_BIN:-/home/moiz/sniper-data/tui/dipmon-go}
SRC=${SRC:-/home/moiz/sniper-data/runs/ams/runs/dip_ams_r27.jsonl}
OUT=screens
SIZES=200x35,160x50,80x24,50x30
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
rm -rf "$OUT/ended" "$OUT/live" "$OUT/warmup" "$OUT/png" "$OUT/r28" "$OUT/dipview" "$OUT/filters"
END=$(python3 -c "import json,subprocess,sys; print(json.loads(subprocess.run(['$BIN','--file','$SRC','--snapshot','--json','--usd','187.42','--load-duty','0'],capture_output=True,text=True).stdout)['ended']/1e9)")
"$BIN" --file "$SRC" --usd 187.42 --now "$END" --golden --screens "$OUT/ended" --sizes "$SIZES" > /dev/null
"$BIN" --file "$SRC" --usd 187.42 --now "$END" --golden --screens "$OUT/ended" --sizes 200x35,50x30 --screens-ansi > /dev/null
find "$OUT/ended" -name '50x30_*.ans' ! -name '*overview*' ! -name '*splash*' ! -name '*today*' -delete
T=$(python3 tests/replay.py "$SRC" "$TMP/live" --until-frac 0.6 --quiet | sed -n 's/^T_CUT=//p')
NOW=$(python3 -c "print(int(float('$T'))/1e9)")
"$BIN" --file "$TMP/live/dip_ams_r27.jsonl" --usd 187.42 --assume-running --now "$NOW" --golden --screens "$OUT/live" --sizes "$SIZES" > /dev/null
"$BIN" --file "$TMP/live/dip_ams_r27.jsonl" --usd 187.42 --assume-running --now "$NOW" --golden --screens "$OUT/live" --sizes 200x35 --screens-ansi > /dev/null
rm -f "$OUT"/live/*today* "$OUT"/live/*splash*
T=$(python3 tests/replay.py "$SRC" "$TMP/warm" --until-frac 0.10 --quiet | sed -n 's/^T_CUT=//p')
NOW=$(python3 -c "print(int(float('$T'))/1e9)")
"$BIN" --file "$TMP/warm/dip_ams_r27.jsonl" --usd 187.42 --assume-running --now "$NOW" --golden --screens "$OUT/warmup" --sizes 200x35,50x30 > /dev/null
find "$OUT/warmup" -type f ! -name '*overview*' ! -name '*presend*' ! -name '*config*' -delete
R28=${R28:-/home/moiz/sniper-data/tui/runs/ams/runs/dip_ams_r28.jsonl}
if [ -f "$R28" ]; then
  END28=$(python3 -c "import json,subprocess,sys; print(json.loads(subprocess.run(['$BIN','--file','$R28','--snapshot','--json','--usd','187.42','--load-duty','0'],capture_output=True,text=True).stdout)['ended']/1e9)")
  "$BIN" --file "$R28" --usd 187.42 --now "$END28" --golden --screens "$TMP/r28" --sizes 200x35,50x30 > /dev/null
  "$BIN" --file "$R28" --usd 187.42 --now "$END28" --golden --screens "$TMP/r28" --sizes 200x35,50x30 --screens-ansi > /dev/null
  mkdir -p "$OUT/r28"
  for f in "$TMP"/r28/*_02-presend.* "$TMP"/r28/*_04-trades.* "$TMP"/r28/*_09-detail.*; do cp "$f" "$OUT/r28/"; done
fi
# the Filters tab on r40 (the fixture of the filters tests; its end 10-31 00:45 PKT)
FX=internal/core/testdata/filters
gzip -dc "$FX/dip_ams_r40f.jsonl.gz" > "$TMP/dip_ams_r40f.jsonl"
mkdir -p "$OUT/filters"
for sz in 200x45 120x40 80x30 50x30; do
  "$BIN" --file "$TMP/dip_ams_r40f.jsonl" --usd 187.42 --now 1793389600 --golden --gcr-seed "$FX/gcr_seed.json" --load-duty 0 --screen "$sz" --tab 8 > "$OUT/filters/${sz}_12-filters.txt"
done
for sz in 200x45 50x30; do
  "$BIN" --file "$TMP/dip_ams_r40f.jsonl" --usd 187.42 --now 1793389600 --golden --gcr-seed "$FX/gcr_seed.json" --load-duty 0 --screen "$sz" --tab 8 --screens-ansi > "$OUT/filters/${sz}_12-filters.ans"
done
# dipview: the run explorer over the local AMS copies (the selected run = the newest, r27), at the end of r27
mkdir -p "$OUT/dipview"
for sz in 200x35 120x40 80x24 50x30; do
  "$BIN" --view --load-duty 0 --dir "$(dirname "$SRC")" --usd 187.42 --now "$END" --screen "$sz" > "$OUT/dipview/${sz}_runs.txt"
done
"$BIN" --view --load-duty 0 --dir "$(dirname "$SRC")" --usd 187.42 --now "$END" --screen 200x35 --screens-ansi > "$OUT/dipview/200x35_runs.ans"
# v4: the Trades tab in USD (u) is not a separate page; the trades / config / detail screens above show the new columns
if python3 -c 'import PIL' 2>/dev/null; then
  mkdir -p "$OUT/png"
  for f in ended/200x35_01-overview ended/200x35_11-today ended/200x35_10-splash ended/200x35_04-trades ended/200x35_02-presend \
           ended/200x35_08-help ended/200x35_07-config ended/50x30_01-overview ended/50x30_11-today live/200x35_01-overview dipview/200x35_runs; do
    python3 tests/ans2png.py "$OUT/$f.ans" "$OUT/png/$(dirname "$f")-$(basename "$f").png"
  done
  for f in filters/200x45_12-filters filters/50x30_12-filters; do
    python3 tests/ans2png.py "$OUT/$f.ans" "$OUT/png/$(dirname "$f")-$(basename "$f").png"
  done
  for f in r28/200x35_02-presend r28/200x35_04-trades r28/200x35_09-detail r28/50x30_02-presend r28/50x30_04-trades r28/50x30_09-detail; do
    [ -f "$OUT/$f.ans" ] && python3 tests/ans2png.py "$OUT/$f.ans" "$OUT/png/$(dirname "$f")-$(basename "$f").png"
  done
fi
ls "$OUT"/ended "$OUT"/live "$OUT"/warmup "$OUT"/r28 "$OUT"/dipview "$OUT"/filters 2>/dev/null | grep -c -E '\.(txt|ans)$'
du -sh "$OUT"
