#!/usr/bin/env python3
# refresh the '## Forward proof (landing models)' section of NOTES.md from the latest forward_proof.py output
import re, time, sys
src = sys.argv[1] if len(sys.argv) > 1 else "/root/race/fp_fresh.txt"
txt = open(src).read()
v = [l for l in txt.splitlines() if l.startswith("VERDICT")]
head = [l for l in txt.splitlines() if l.startswith("FORWARD PROOF")]
now = time.strftime("%H:%M", time.gmtime())
sec = (f"## Forward proof (landing models)\n> **Verdict ({now} UTC, fresh run only):** {v[0][9:] if v else 'not enough data yet'}\n"
       f"> {head[0] if head else ''}\n\n"
       "- **Fresh run** `fresh`: merged binary, started 05:00 UTC, every base launch tracked, labelled on chain. It is scored only on launches after its start, with rules and exits frozen earlier (no refit). Re-scored every ~2 h by `forward_proof.py fresh`.\n"
       "- **Landing models:**\n"
       "  - (a) **OURS:** 38% land in S at our 18 measured positions (median ~104); the rest land in S+1.\n"
       "  - (b) **JITO / (c) LANDX:** the in-S positions of Jito- or LandX-tipped outside buyers on the same leader client (`landing_dist.json`; the d <= 5 bundle riders are excluded). These assume we land in S.\n"
       "  - (d) **<= 25 txs:** the ceiling.\n"
       "- **Whale rule:** the trigger is the first outside buy >= 5 SOL in S; we land 'model' txs after it; sell at +3 s.\n\n"
       "```\n" + txt.strip() + "\n```\n\n")
s = open("/root/race/NOTES.md").read()
if "## Forward proof (landing models)" in s:
    s = re.sub(r"## Forward proof \(landing models\)[\s\S]*?(?=\n# FINAL|\n## Blind run|\Z)", sec, s, count=1)
else:
    s = sec + s
open("/root/race/NOTES.md", "w").write(s)
print("updated", now)
