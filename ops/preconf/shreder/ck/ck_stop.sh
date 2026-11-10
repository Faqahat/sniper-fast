#!/bin/bash
# HOST side: stop the Constant-K feed race on FRA (SIGTERM, SIGKILL after 15 s). It also stops by itself after MINUTES.
FRA=${FRA:-it@cyberfra}; P=${FRA_PORT:-1996}
ssh -p "$P" -o ConnectTimeout=10 -o BatchMode=yes "$FRA" "sudo bash /root/shreder/ck/ck_remote.sh stop"
