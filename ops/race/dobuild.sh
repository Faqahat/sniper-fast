#!/bin/bash
# build snipe_engine (release) into /root/race/<log>
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-fast
cargo build --release --bin snipe_engine > /root/race/$1 2>&1
echo BUILD_EXIT=$? >> /root/race/$1
