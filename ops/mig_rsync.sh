#!/bin/bash
# one-shot migration copy old -> new (/root -> /root via sudo rsync). Excludes build dirs, old arb run logs, caches.
cd /root
rsync -aH --numeric-ids --info=progress2 --rsync-path="sudo rsync" -e "ssh -p 1996 -i /root/.ssh/mig_ed25519 -o BatchMode=yes" \
  --exclude="/arbx/runs/" --exclude="target/" --exclude="/.rustup/" --exclude="/.cargo/" --exclude="cache/" --exclude="blockcache/" \
  --exclude="/.ssh/" --exclude="/.cache/" /root/ it@84.32.100.36:/root/
echo "RSYNC_EXIT $?"
# release binaries the scripts call (target/ was excluded)
for d in arbx-final2 arbx-final arbx-lat arbx-feed arbx-merge arbx-fast arbx-det arbx-race; do
  [ -f /root/$d/target/release/snipe_engine ] && rsync -a --rsync-path="sudo mkdir -p /root/$d/target/release && sudo rsync" -e "ssh -p 1996 -i /root/.ssh/mig_ed25519 -o BatchMode=yes" /root/$d/target/release/snipe_engine it@84.32.100.36:/root/$d/target/release/snipe_engine
done
echo "BIN_DONE"
