#!/bin/bash
ssh -p 1996 -o ConnectTimeout=15 it@84.32.100.36 "sudo python3 /root/sniper-collect/health.py"
