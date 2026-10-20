#!/bin/bash
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-fast
cargo build --release --bin snipe_engine > /root/sniper-fast/build_slim.log 2>&1
echo "EXIT=$?" >> /root/sniper-fast/build_slim.log
