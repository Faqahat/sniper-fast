#!/bin/bash
export PATH=/root/.cargo/bin:$PATH
cd /root/arbx-fast
cargo build --release --bin snipe_engine > /root/arbx-fast/build_slim.log 2>&1
echo "EXIT=$?" >> /root/arbx-fast/build_slim.log
