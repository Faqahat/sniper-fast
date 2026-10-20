#!/bin/bash
# build the MERGED engine (/root/sniper-merge = det AFTER_FINAL fixes + race gate patches 1-8). Never touches /root/sniper-fast.
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-merge
cargo build --release --bin snipe_engine > /root/race/$1 2>&1
echo BUILD_EXIT=$? >> /root/race/$1
