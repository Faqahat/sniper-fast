#!/bin/bash
# build the SEPARATE race engine (/root/arbx-race) — never touches /root/arbx-fast
export PATH=/root/.cargo/bin:$PATH
cd /root/arbx-race
cargo build --release --bin snipe_engine > /root/race/$1 2>&1
echo BUILD_EXIT=$? >> /root/race/$1
