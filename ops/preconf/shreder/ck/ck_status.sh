#!/bin/bash
# HOST side: one header line + one line per feed (tx/s over the last 60 s, last tx age, connected/SILENT, reconnects/errors).
FRA=${FRA:-it@84.32.100.36}; P=${FRA_PORT:-1996}
ssh -p "$P" -o ConnectTimeout=10 -o BatchMode=yes "$FRA" "sudo bash /root/shreder/ck/ck_remote.sh status"
