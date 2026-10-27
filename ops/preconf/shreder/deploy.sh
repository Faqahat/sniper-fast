#!/bin/bash
# HOST: copy the recorder binary + FRA scripts into FRA:/root/shreder (does NOT start anything). Re-runnable:
# installs as .new then mv (a running recorder keeps its old inode).
set -euo pipefail
H=$(dirname "$(readlink -f "$0")")
FRA_HOST=it@84.32.100.36
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -p 1996 "$FRA_HOST")
want=$(cut -d' ' -f1 "$H/dist/shreder_rec.sha256")
[ "$(sha256sum "$H/dist/shreder_rec" | cut -d' ' -f1)" = "$want" ] || { echo "dist binary sha mismatch"; exit 1; }
scp -q -P 1996 "$H/dist/shreder_rec" "$H/server/run_rec.sh" "$H/server/stop_rec.sh" "$H/server/rec_status.sh" "$FRA_HOST:/tmp/"
"${SSH[@]}" 'set -e; sudo mkdir -p /root/shreder/bin /root/shreder/data
sudo install -m 755 /tmp/shreder_rec /root/shreder/bin/shreder_rec.new && sudo mv -f /root/shreder/bin/shreder_rec.new /root/shreder/bin/shreder_rec
for f in run_rec.sh stop_rec.sh rec_status.sh; do sudo install -m 755 /tmp/$f /root/shreder/$f.new && sudo mv -f /root/shreder/$f.new /root/shreder/$f; done
rm -f /tmp/shreder_rec /tmp/run_rec.sh /tmp/stop_rec.sh /tmp/rec_status.sh
sudo sha256sum /root/shreder/bin/shreder_rec | cut -d" " -f1' | { read -r got; [ "$got" = "$want" ] && echo "deployed OK sha $got" || { echo "DEPLOY SHA MISMATCH got=$got want=$want"; exit 1; }; }
