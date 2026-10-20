#!/bin/bash
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-feed
nice -n 10 cargo build --release --bin snipe_engine > /root/gap/$1 2>&1
echo BUILD_EXIT=$? >> /root/gap/$1
