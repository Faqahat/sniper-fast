#!/usr/bin/env python3
"""STATE step 1b [MEASURED engine paper, read-only]: the observatory re-arm windows (rule R0, dip24/dip25/dip26 obs log) of AMS r36, r37 (4 parts)
and r38, with the engine's paper fill per row (a/b/c) and its paper P&L (% of size) per exit variant; plus the obs rearm_cand rejects.
Out: /home/it/sniper-data/prevent/state/obs_rearm.pkl"""
import json, pickle, glob
OUT = "/home/it/sniper-data/prevent/state"
R = "/home/it/sniper-data/runs/ams/runs"
FILES = {"r36": [f"{R}/dip_ams_r36.obs.jsonl"],
         "r37": [f"{R}/dip_ams_r37.obs.jsonl.1", f"{R}/dip_ams_r37.obs.jsonl.2", "/home/it/sniper-data/multiarm/raw/r37.obs.jsonl.3", f"{R}/dip_ams_r37.obs.jsonl"],
         "r38": [f"{R}/dip_ams_r38.obs.jsonl"]}


def main():
    out = {}
    for run, fs in FILES.items():
        W = []; seen = set()
        for p in fs:
            for line in open(p, errors="ignore"):
                if '"ev":"rearm_window"' not in line: continue
                try: d = json.loads(line)
                except Exception: continue
                key = (d["mint"], d["dump"]["sig"])
                if key in seen: continue
                seen.add(key)
                rows = {}
                for r, v in (d.get("rows") or {}).items():
                    f = v.get("fill") or {}
                    px = (f.get("px") or {}).get("0.65") or {}
                    rows[r] = dict(hit=v.get("hit"), blocked=v.get("blocked"), s_in=f.get("s_in"), m=f.get("m"), x=f.get("x"), px=px.get("live"), px_tp20=px.get("tp20"),
                                   px_naive=((f.get("px_naive") or {}).get("0.65") or {}).get("live"), pos_open=f.get("live_pos_open"), n_ahead=f.get("n_ahead"),
                                   sad=f.get("slots_after_dump"), followers=f.get("followers"), second=f.get("second"), r2=f.get("r2"))
                W.append(dict(run=run, mint=d["mint"], dump=d["dump"], arm=d.get("arm"), en_slot=d.get("en_slot"), end=d.get("end"), holders=d.get("holders"),
                              quiet=d.get("quiet"), quiet_stop=d.get("quiet_stop"), r5_skip=d.get("r5_skip"), min_ratio=d.get("min_ratio"), others=d.get("others"), rows=rows))
        W.sort(key=lambda x: x["dump"]["t"])
        out[run] = W
        hit = sum(1 for x in W if (x["rows"].get("c") or {}).get("hit") == "fill")
        print(run, "windows", len(W), "row-c fills", hit, "px sum %", round(sum((x["rows"].get("c") or {}).get("px") or 0 for x in W if (x["rows"].get("c") or {}).get("hit") == "fill"), 1), flush=True)
    pickle.dump(out, open(f"{OUT}/obs_rearm.pkl", "wb"))


if __name__ == "__main__":
    main()
