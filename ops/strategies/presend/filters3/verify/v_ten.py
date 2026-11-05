#!/usr/bin/env python3
"""VERIFY: run the FROZEN COPY of ten/score.py unchanged (runpy, its own argv) and dump per-trade values so pooled totals and
'w/o top 5' can be computed across runs. The SIZE15 per-trade loop mirrors score.py's own loop line for line.
usage: v_ten.py TAG OUT.json RUN.presend.jsonl [--from-ns T0] [--to-ns T1]"""
import sys, json, runpy, io, contextlib
FC = "/home/moiz/sniper/ops/strategies/presend/filters3/verify/frozen_copies"
tag, out = sys.argv[1], sys.argv[2]
sys.argv = [f"{FC}/ten/score.py"] + sys.argv[3:]
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    g = runpy.run_path(f"{FC}/ten/score.py", run_name="__main__")
real, replay, sel = g["real"], g["replay"], g["sel"]
size = []
for k in sel:
    pl = real[k] / 1e9
    r3 = replay(k, 1.5, 3.0, 0.0)
    if r3 is None:
        size.append({"k": list(k), "mint": g["fills"].get(k, {}).get("mint") or g["live_arm"][k]["mint"], "pl": pl, "rep": False,
                     "b3": pl * 0.5, "b0": pl * 0.5, "b9": pl * 0.5, "b3d20": pl * 0.5}); continue
    size.append({"k": list(k), "mint": g["fills"][k]["mint"], "pl": pl, "rep": True, "b3": r3 - pl, "b0": replay(k, 1.5, 0.0, 0.0) - pl,
                 "b9": replay(k, 1.5, 9.0, 0.0) - pl, "b3d20": replay(k, 1.5, 3.0, 0.2) - replay(k, 1.0, 0.0, 0.2)})
json.dump({"tag": tag, "hrs": g["hrs"], "live_size": g["live_size"], "stdout": buf.getvalue(), "base": [real[k] / 1e9 for k in g["base_keys"]],
           "wide": g["wv"], "wide_raw": g["wraw"], "size": size}, open(out, "w"))
print(buf.getvalue())
