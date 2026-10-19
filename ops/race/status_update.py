#!/usr/bin/env python3
# rewrite the progress line at the top of NOTES.md with run-2 health counts only (no outcomes are looked at)
import re, time, os
L = open("/root/race/paper_night.log", errors="replace").read()
seen, fired = L.count("RACE seen"), L.count("pass=true")
stalls = len(re.findall(r"PAPER_RACE stall", L))
oc = sum(1 for _ in open("/root/race/night_onchain.jsonl")) if os.path.exists("/root/race/night_onchain.jsonl") else 0
mw = sum(1 for _ in open("/root/race/meta_night.jsonl")) if os.path.exists("/root/race/meta_night.jsonl") else 0
now = time.strftime("%H:%M", time.gmtime())
M = open("/root/race/paper_mnight.log", errors="replace").read() if os.path.exists("/root/race/paper_mnight.log") else ""
mseen, mfired = M.count("RACE seen"), M.count("pass=true")
line = (f"> **Overnight run progress ({now} UTC):** {seen} base launches seen, {fired} fired by the frozen Gate B, "
        f"{oc} labelled on chain, {mw} metadata/X fetches, {stalls} engine restarts; merged-binary run `mnight`: {mseen} seen, {mfired} fired. "
        f"Outcomes are not looked at until the runs end (blind test).")
s = open("/root/race/NOTES.md").read()
if "> **Overnight run progress" in s:
    s = re.sub(r"> \*\*Overnight run progress.*\n", line + "\n", s, count=1)
else:
    s = s.replace("\n\n## Bottom line so far", "\n" + line + "\n\n## Bottom line so far", 1)
open("/root/race/NOTES.md", "w").write(s)
print(line)
