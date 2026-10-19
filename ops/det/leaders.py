#!/usr/bin/env python3
# READ-ONLY: close-leaders gate check: epoch mapping, how much of the schedule the close set covers, next boundary.
import sys, json
sys.path.insert(0, "/root/det")
from dlib import rpc
ei = rpc("getEpochInfo", [])
start = ei["absoluteSlot"] - ei["slotIndex"]
ls = rpc("getLeaderSchedule", [None])
close = {l.strip() for l in open("/root/arbx-fast/close_leaders.txt") if l.strip()}
slots = sum(len(v) for v in ls.values())
cs = sum(len(v) for k, v in ls.items() if k in close)
print(f"epoch {ei['epoch']} start {start} slotIndex {ei['slotIndex']} slotsInEpoch {ei['slotsInEpoch']} -> next boundary in {ei['slotsInEpoch']-ei['slotIndex']} slots (~{(ei['slotsInEpoch']-ei['slotIndex'])*0.4/3600:.1f} h)")
print(f"schedule leaders {len(ls)} slots {slots} | close set {len(close)} | leaders in close set {sum(1 for k in ls if k in close)} | slots covered {cs} ({cs/slots:.1%})")
cur = ei["absoluteSlot"]
mine = rpc("getSlotLeaders", [cur, 10])
idx = ei["slotIndex"]
calc = [k for k, v in ls.items() if idx in v]
print("mapping check: getSlotLeaders(cur) =", mine[0][:8], "| schedule[epoch_start+idx] =", calc[0][:8] if calc else None, "| match", bool(calc) and calc[0] == mine[0])
nxt = rpc("getLeaderSchedule", [start + ei["slotsInEpoch"]])
print("next-epoch schedule available:", isinstance(nxt, dict) and len(nxt) > 0)
