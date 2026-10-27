#!/bin/bash
# HOST side: deploy the Constant-K feed race to FRA (/root/shreder/ck/) and start it next to the Shreder recorder.
#   bash ck_start.sh [MINUTES=75] [TAG=YYYYMMDD_HHMM UTC]
# Feeds = the engines' CURRENT Constant-K feeds (kaldera, turbo-kaldera = SubscribeDeshred; kaldera-tx = Subscribe,
# processed), Frankfurt endpoints + tokens taken from the FRA engine config on the server (never printed).
# Override: CK_FEEDS=kaldera,turbo-kaldera,kaldera-tx[,erpc]   FRA=user@host FRA_PORT=1996
# Deploy = scp to /tmp, then the new ck_remote.sh installs itself (.new + mv; never while a race runs); start = a SEPARATE ssh.
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd)
FRA=${FRA:-it@84.32.100.36}; P=${FRA_PORT:-1996}
MIN=${1:-75}; TAG=${2:-$(date -u +%Y%m%d_%H%M)}
SSH=(ssh -p "$P" -o ConnectTimeout=10 -o BatchMode=yes "$FRA")
TMP=/tmp/ck_deploy_$$_$(date +%s)
"${SSH[@]}" "mkdir -p $TMP"
scp -q -P "$P" -o ConnectTimeout=10 -o BatchMode=yes "$H/ck_remote.sh" "$H/make_race_toml.py" "$FRA:$TMP/"
"${SSH[@]}" "sudo bash $TMP/ck_remote.sh install $TMP; rm -rf $TMP"
"${SSH[@]}" "sudo CK_FEEDS=${CK_FEEDS:-kaldera,turbo-kaldera,kaldera-tx} bash /root/shreder/ck/ck_remote.sh start $MIN $TAG"
