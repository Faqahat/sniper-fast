# READ-ONLY (host): price every launch of TODAY's live paper engine log (copied, with the paper_c6 loop's cached block
# recordings) with filters.py's unchanged model -> <work>/paper_rows.json, group "D" = launches after period C's last slot
# (10-21 ~10:13 UTC onwards; new out-of-sample data for FILTERS2.md). Uses only cached recordings (no RPC).
# usage: python3 paper_rows.py <work dir with launches_ready.json, leaders.json, rec/> <tipmap.json>
import sys, os, json

WORK, TIPMAP = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
C_LAST = 459591337                                              # last slot of period C (dry_run1.log copied 10:13 UTC)
src = open(os.path.join(HERE, "filters.py")).read()
src = src.replace('GROUPS = {"A": ["dry1h", "run1"], "B": ["cov", "alt", "cad", "edge1", "latest", "edge2", "edge3", "edge5", "night"], "C": ["morning"]}', 'GROUPS = {"P": ["paper"]}')
src = src.split('json.dump(dict(rows=rows')[0]
sys.argv = ["filters.py", os.path.join(WORK, "launches_ready.json"), os.path.join(WORK, "rec"), os.path.join(WORK, "leaders.json"), TIPMAP, os.path.join(WORK, "out")]
ns = {"__name__": "filters_paper"}
exec(compile(src, "filters.py", "exec"), ns)
rows = [r for r in ns["rows"] if r["S"] > C_LAST]
for r in rows: r["grp"] = "D"; r["log"] = "today"
D = json.load(open(os.path.join(WORK, "launches_ready.json")))
sp = D["spans"]["paper"]
hours = (sp["last_slot"] - C_LAST) * sp["slot_ms"] / 1000 / 3600
json.dump(dict(rows=rows, hours={"D": hours}, missing=dict(ns["miss"])), open(os.path.join(WORK, "paper_rows.json"), "w"))
print(f"today (D) rows {len(rows)}  hours {hours:.2f}  missing {dict(ns['miss'])}")
