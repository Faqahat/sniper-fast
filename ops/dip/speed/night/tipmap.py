#!/usr/bin/env python3
# tip account -> service, parsed from the engine's own registry (src/send/mod.rs: ("addr", "name") rows + SendKind::X => &[..] blocks)
import re, json, sys
src = open("/home/moiz/sniper-landfix/src/send/mod.rs").read()
M = {}
for a, n in re.findall(r'\("([1-9A-HJ-NP-Za-km-z]{32,44})",\s*"([^"]+)"\)', src): M[a] = n
for kinds, body in re.findall(r'((?:SendKind::\w+\s*\|?\s*)+)=>\s*&\[(.*?)\]', src, flags=re.S):
    name = re.findall(r'SendKind::(\w+)', kinds)[0].lower()
    name = {"jitobundle": "jito", "iris": "astralane", "rpcfast": "rpcfast_beam"}.get(name, name)
    for a in re.findall(r'"([1-9A-HJ-NP-Za-km-z]{32,44})"', body): M.setdefault(a, name)
if __name__ == "__main__":
    json.dump(M, open("/home/moiz/sniper/ops/dip/speed/night/tipmap.json", "w"), indent=0)
    import collections; print(len(M), collections.Counter(M.values()).most_common(40))
