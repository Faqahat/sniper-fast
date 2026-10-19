#!/bin/bash
# build the MERGED engine (/root/arbx-merge = det AFTER_FINAL fixes + race gate patches 1-8). Never touches /root/arbx-fast.
export PATH=/root/.cargo/bin:$PATH
cd /root/arbx-merge
cargo build --release --bin snipe_engine > /root/race/$1 2>&1
echo BUILD_EXIT=$? >> /root/race/$1
