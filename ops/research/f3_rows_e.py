# READ-ONLY (host): price the live paper engine's watched launches AFTER period D (10-21 12:37 UTC onwards = group "E")
# with filters.py's unchanged model, from a COPY of the paper_c6 loop's files (launches_ready.json, leaders.json, rec/).
# Same as paper_rows.py, only the cut-off differs. No RPC.
# usage: python3 f3_rows_e.py <copied work dir> <tipmap.json>
import sys, os, json

WORK, TIPMAP = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
D_LAST = max(r["S"] for r in json.load(open(os.path.join(HERE, "filters2_rows.json")))["rows"])   # last slot of period D
src = open(os.path.join(HERE, "filters.py")).read()
src = src.replace('GROUPS = {"A": ["dry1h", "run1"], "B": ["cov", "alt", "cad", "edge1", "latest", "edge2", "edge3", "edge5", "night"], "C": ["morning"]}', 'GROUPS = {"P": ["paper"]}')
src = src.split('json.dump(dict(rows=rows')[0]
sys.argv = ["filters.py", os.path.join(WORK, "launches_ready.json"), os.path.join(WORK, "rec"), os.path.join(WORK, "leaders.json"), TIPMAP, os.path.join(WORK, "out")]
ns = {"__name__": "filters_paper"}
exec(compile(src, "filters.py", "exec"), ns)
rows = [r for r in ns["rows"] if r["S"] > D_LAST]
for r in rows: r["grp"] = "E"; r["log"] = "today"
D = json.load(open(os.path.join(WORK, "launches_ready.json")))
sp = D["spans"]["paper"]
hours = (sp["last_slot"] - D_LAST) * sp["slot_ms"] / 1000 / 3600
json.dump(dict(rows=rows, hours={"E": hours}, missing=dict(ns["miss"])), open(os.path.join(WORK, "paper_rows_e.json"), "w"))
print(f"E rows {len(rows)}  hours {hours:.2f}  missing {dict(ns['miss'])}")
