#!/bin/bash
# HOST: read-only preflight on FRA (no gRPC call, starts nothing): binary sha, disk, memory, endpoint TCP reachability,
# collector lag, load. usage: preflight.sh [RUN] [MIN]
H=$(dirname "$(readlink -f "$0")")
RUN=${1:-trial_$(TZ=Asia/Karachi date +%Y%m%d)}; MIN=${2:-75}
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -p 1996 it@84.32.100.36)
want=$(cut -d' ' -f1 "$H/dist/shreder_rec.sha256")
echo "== $(TZ=Asia/Karachi date +%H:%M:%S) PKT preflight (run $RUN, $MIN min)"
"${SSH[@]}" "uptime | sed 's/.*load average/load average/'
pgrep -fa '[s]hreder_rec --out' | cut -c1-120 | sed 's/^/already running: /'
got=\$(sudo sha256sum /root/shreder/bin/shreder_rec 2>/dev/null | cut -d' ' -f1); [ \"\$got\" = '$want' ] && echo 'binary: OK' || echo 'binary: MISSING/MISMATCH -> run deploy.sh'
df -h / | awk 'NR==2{print \"disk: \"\$5\" used, \"\$4\" free\"}'
free -m | awk '/Mem:/{print \"mem: \"\$7\" MB available of \"\$2}'
timeout 4 bash -c '</dev/tcp/fra-allnodes.binary.shreder.xyz/9991' 2>/dev/null && echo 'endpoint: TCP reachable' || echo 'endpoint: TCP NOT reachable'
sudo python3 -c \"import json,time;r=open('/root/sniper-collect/current_run').read().strip();s=json.load(open('/root/sniper-collect/'+r+'/status.json'));print('collector: lag_slots',s.get('lag_slots'),'status_age %.0f s'%(time.time()-s.get('now',0)))\" 2>/dev/null || echo 'collector: status unreadable'"
