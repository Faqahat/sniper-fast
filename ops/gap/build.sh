#!/bin/bash
export PATH=/root/.cargo/bin:$PATH
cd /root/arbx-feed
nice -n 10 cargo build --release --bin feed_race > /root/gap/$1 2>&1
echo BUILD_EXIT=$? >> /root/gap/$1
