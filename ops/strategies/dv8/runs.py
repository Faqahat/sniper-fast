"""DV8 shared: list of all live run record files (read-only)."""
import glob, os, re
D = "/home/moiz/sniper-data"
def run_files():
    R = {}
    for f in glob.glob(f"{D}/runs/ams/runs/dip_ams_r*.jsonl") + [f"{D}/presend_filter/live28/dip_ams_r28.jsonl"] + glob.glob(f"{D}/haqq_strat/live/dip_ams_r*.jsonl"):
        R["AMS%02d" % int(re.search(r"_r(\d+)", f).group(1))] = f
    for f in glob.glob(f"{D}/runs/fra/runs/dip_r*.jsonl"):
        R["FRA%02d" % int(re.search(r"_r(\d+)", f).group(1))] = f
    extra = glob.glob(f"{D}/dv8/live/dip_r*.jsonl")
    for f in extra: R["FRA%02d" % int(re.search(r"_r(\d+)", f).group(1))] = f
    return dict(sorted(R.items()))
