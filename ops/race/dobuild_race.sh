#!/bin/bash
# build the SEPARATE race engine (/root/sniper-race) — never touches /root/sniper-fast
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-race
cargo build --release --bin snipe_engine > /root/race/$1 2>&1
echo BUILD_EXIT=$? >> /root/race/$1
