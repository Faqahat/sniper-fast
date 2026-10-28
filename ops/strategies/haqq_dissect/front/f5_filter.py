#!/usr/bin/env python3
"""FRONT step 5b helper: stdin = raw lines that mention one of the chunk's mints; keep a line only if one of its mints has a slot
window containing the line's slot; drop the bulky ev/tb/sd fields. argv[1] = the chunk's windows json."""
import sys, json, re
W = json.load(open(sys.argv[1]))
H = re.compile(r'^\{"s":(\d+),')
out = sys.stdout
for l in sys.stdin:
    m = H.match(l)
    if not m: continue
    s = int(m.group(1))
    try: d = json.loads(l)
    except Exception: continue
    ok = False
    for mt in d.get("mints") or []:
        for a, b in W.get(mt, ()):
            if a <= s <= b: ok = True; break
        if ok: break
    if not ok:
        # mint may appear only in accounts (failed tx: no mints decoded) -> keep if any window mint string is in the line and slot fits
        for mt, ws in W.items():
            if mt in l and any(a <= s <= b for a, b in ws): ok = True; break
    if not ok: continue
    for k in ("ev", "tb", "sd"): d.pop(k, None)
    out.write(json.dumps(d, separators=(",", ":")) + "\n")
