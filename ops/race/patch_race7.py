#!/usr/bin/env python3
# RACE-GATE patch part 7 (2026-10-18 night): RACE seen also logs the metadata uri (for the off-chain/tweet side fetcher).
import sys
ep = sys.argv[1]
e = open(ep).read()
old = """creator={} name_len={} sym={} name={}",
        b58(&launch.mint),"""
new = """creator={} name_len={} sym={} name={} uri={}",
        b58(&launch.mint),"""
assert e.count(old) == 1
e = e.replace(old, new)
old2 = """        ci.name.chars().count(), clean(&ci.symbol), clean(&ci.name))"""
new2 = """        ci.name.chars().count(), clean(&ci.symbol), clean(&ci.name),
        snipe::create_strings(tx).map(|(_, _, u)| u.chars().filter(|c| !c.is_whitespace()).take(200).collect::<String>()).filter(|u| !u.is_empty()).unwrap_or_else(|| "-".into()))"""
assert e.count(old2) == 1
e = e.replace(old2, new2)
open(ep, "w").write(e)
print("patch7 OK")
