#!/bin/bash
# HOST: copy the trial data from FRA (+ the engine log snapshot) into /home/moiz/sniper-data/preconf/<YYYYMMDD>/ with
# sha256 verification, then write catalog.json. NEVER deletes anything on any server (server copies stay until the
# coordinator OKs a cleanup).
# usage: fetch.sh [RUN]
# env:   FORCE=1 (copy while the recorder still runs = partial)   NO_ENGINE=1
#        ENGINE_HOST=ams|fra (default ams)  ENGINE_LOG=<path on that host> (default: newest /root/prod/runs/dip_<host>_r*.jsonl)
set -uo pipefail
H=$(dirname "$(readlink -f "$0")")
RUN=${1:-$(cat /home/moiz/sniper-data/preconf/CURRENT_RUN 2>/dev/null)}
[ -n "$RUN" ] || { echo "no RUN"; exit 1; }
DATE=${RUN#trial_}; HD=/home/moiz/sniper-data/preconf/$DATE
mkdir -p "$HD/fra" "$HD/ck" "$HD/engine"
FRA=it@84.32.100.36; AMS=it@84.32.104.202
SSHO=(-o BatchMode=yes -o ConnectTimeout=10 -p 1996)
if ssh "${SSHO[@]}" $FRA "pgrep -f '[s]hreder_rec --out /root/shreder/data/$RUN ' >/dev/null"; then
  [ "${FORCE:-0}" = 1 ] || { echo "recorder still running -> wait for it, or FORCE=1 for a partial copy"; exit 1; }
  echo "WARNING: partial copy (recorder running)"
fi
verified_copy() {  # remote_dir local_dir
  local R=$1 L=$2
  ssh "${SSHO[@]}" $FRA "sudo test -d $R" || { echo "skip $R (absent)"; return 0; }
  echo "== manifest $R"
  ssh "${SSHO[@]}" $FRA "sudo sh -c 'cd $R && find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 -r sha256sum > MANIFEST.sha256 && echo \"\$(wc -l < MANIFEST.sha256) files, \$(du -sh . | cut -f1)\"'"
  echo "== copy -> $L"
  rsync -a --partial --info=stats1 --rsync-path="sudo rsync" -e "ssh ${SSHO[*]}" "$FRA:$R/" "$L/" | grep -E 'Total transferred|total size' || true
  if (cd "$L" && sha256sum -c --quiet MANIFEST.sha256); then echo "VERIFIED $(wc -l < "$L/MANIFEST.sha256") files in $L"; else echo "!! VERIFY FAILED in $L"; return 1; fi
}
ok=0
verified_copy /root/shreder/data/$RUN "$HD/fra" || ok=1
verified_copy /root/shreder/ck/out "$HD/ck" || ok=1
if [ "${NO_ENGINE:-0}" != 1 ]; then
  EH=${ENGINE_HOST:-ams}
  [ "$EH" = fra ] && EHOST=$FRA || EHOST=$AMS
  # default: the newest dip_<host>_r*.jsonl on that host (AMS r28 ended 22:03 PKT 10-27; r30 was live at 22:21)
  EL=${ENGINE_LOG:-$(ssh "${SSHO[@]}" $EHOST "sudo sh -c 'ls -t /root/prod/runs/dip_${EH}_r*.jsonl 2>/dev/null | head -1'")}
  if [ -n "$EL" ]; then
    echo "== engine log snapshot ($EH:$EL + its .log, read-only)"
    for f in "$EL" "${EL%.jsonl}.log"; do
      b=$(basename "$f")
      ssh "${SSHO[@]}" $EHOST "sudo cat $f" > "$HD/engine/$b.part" 2>/dev/null && mv "$HD/engine/$b.part" "$HD/engine/$b" || rm -f "$HD/engine/$b.part"
    done
    echo "$EH" > "$HD/engine/ENGINE_HOST"; basename "$EL" > "$HD/engine/ENGINE_LOG"
    ls -la "$HD/engine/"
  else
    echo "!! no engine log found on $EH"
  fi
fi
python3 -I "$H/make_catalog.py" "$HD" || ok=1
exit $ok
