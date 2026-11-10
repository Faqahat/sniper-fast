#!/usr/bin/env python3
"""VERIFY look-ahead check of TAIL G3 (fresh holders >= 35% 'at signing'). The scorer's holder list is the one at OUR LANDING
(fill ann.holders) with sells after signing added back; holders who BOUGHT between signing and landing are not removed.
ann.holders[].age = slots since that holder's first buy of the token (pslive / presend_live.rs HolderClock), at landing. A holder
with age < (fill slot - signing slot) first bought AFTER signing: invisible at signing. This recomputes sum_fresh without them.
usage: v_g3check.py RUN.presend.jsonl [...]"""
import sys, json, importlib.util
FC = "/home/it/sniper/ops/strategies/presend/filters3/verify/frozen_copies"
s = importlib.util.spec_from_file_location("tl", f"{FC}/tail/tail_score.py"); tl = importlib.util.module_from_spec(s); s.loader.exec_module(tl)
for fn in sys.argv[1:]:
    pos, _, _ = tl.load(fn)
    for p in pos:
        F = tl.feats(p)
        if not F["has_holders"] or F["sum_fresh"] < tl.FRESH_MIN: continue
        sign_slot = (p["att"].get("pos") or [None])[0]
        fslot = p["fill"]["slot"]
        gap = (fslot - sign_slot) if sign_slot else None
        whale = F["whale"] or ""
        late = [h for h in (p["fill"].get("ann") or {}).get("holders", []) if h["w"][:8] != whale[:8] and h["w"] not in tl.OURS
                and (h.get("n") or 0) <= 1 and gap is not None and h.get("age") is not None and h["age"] < gap]
        late_pct = sum(h["pct"] for h in late)
        print(json.dumps({"run": fn.split("/")[-1][:3], "t": p["t"], "mint": p["mint"], "pnl": round(p["pnl"], 4), "sum_fresh": round(F["sum_fresh"], 1),
                          "sign_to_fill_slots": gap, "late_fresh_pct": round(late_pct, 1), "sum_fresh_at_sign": round(F["sum_fresh"] - late_pct, 1),
                          "still_fires": F["sum_fresh"] - late_pct >= tl.FRESH_MIN}))
