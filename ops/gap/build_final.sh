#!/bin/bash
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-final
nice -n 5 cargo build --release --bin snipe_engine --bin feed_race > /root/gap/build_final.log 2>&1
echo BUILD_EXIT=$? >> /root/gap/build_final.log
