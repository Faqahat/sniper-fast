#!/bin/bash
# Shallow-fetch public client repos into their own new folders (READ-ONLY study; never build or run anything from them).
# usage: fetch_src.sh NAME URL REF [sparse dirs...]
set -u
BASE=/home/moiz/sniper-data/clients_src
name=$1; url=$2; ref=$3; shift 3
dst=$BASE/$name
if [ -e "$dst" ]; then echo "exists: $dst"; exit 0; fi
mkdir -p "$dst"
export GIT_TERMINAL_PROMPT=0 GIT_LFS_SKIP_SMUDGE=1
G="git -c core.hooksPath=/dev/null -c protocol.file.allow=never -c submodule.recurse=false"
if [ $# -gt 0 ]; then
  nice $G clone --quiet --depth 1 --branch "$ref" --filter=blob:none --sparse --no-recurse-submodules "$url" "$dst" || { echo "FAIL $name"; exit 1; }
  nice $G -C "$dst" sparse-checkout set --cone "$@" || { echo "FAIL sparse $name"; exit 1; }
else
  nice $G clone --quiet --depth 1 --branch "$ref" --no-recurse-submodules "$url" "$dst" || { echo "FAIL $name"; exit 1; }
fi
echo "OK $name $(git -C "$dst" rev-parse HEAD) $(du -sh "$dst" | cut -f1)"
