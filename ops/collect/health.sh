#!/bin/bash
ssh -p 1996 -o ConnectTimeout=15 it@cyberfra "sudo python3 /root/sniper-collect/health.py"
