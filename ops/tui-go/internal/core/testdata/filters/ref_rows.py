"""Reference: run filters_report.py (unchanged) via runpy and dump its rows at full precision (JSON, repr floats).
usage: python3 -I ref_rows.py RUN.jsonl [--seed PATH] > out.json"""
import sys, json, runpy, io, contextlib
SCRIPT = "/home/it/sniper/ops/strategies/presend/prevent/forward/filters_report.py"
sys.argv = [SCRIPT] + sys.argv[1:]
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    g = runpy.run_path(SCRIPT, run_name="__main__")
rows = [dict(name=n, type=t, blocked=b, win_n=wn, win_sol=float(ws), lose_n=ln, lose_sol=float(ls), net=float(-(ws + ls)), note=note)
        for n, t, b, wn, ws, ln, ls, note in g["rows"]]
def _u(t): return dict(blocked=t[0], win_n=t[1], win_sol=float(t[2]), lose_n=t[3], lose_sol=float(t[4]), net=float(-(t[2] + t[4])))
unique = {k: _u(g[v]) for k, v in (("live", "LIVE_U"), ("log", "LOG_U"), ("all", "ALL_U"))} if "LIVE_U" in g else None
print(json.dumps(dict(unique=unique, positions=len(g["real"]), realized=float(sum(g["real"].values())), rows=rows, text=buf.getvalue()), indent=1))
