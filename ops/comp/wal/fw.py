# READ-ONLY. For each 9XPMCaxt first buy: launch + entry features (create block), to find what sets his size units (k x 0.494 SOL).
import sys, json, os, collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep"); sys.path.insert(0, "/root/comp")
from common import get_block, events, is_vote, tx_summary, load_tipmap, rpc
W = sys.argv[1]
R = json.load(open(sys.argv[2]))
OUT = sys.argv[3]
TM = load_tipmap()
OTHER = {}
for w, fn in (("dK", "/root/comp/wal/dKMjeGJ4_rows.json"), ("4y", "/root/comp/wal/4yFAz_rows.json")):
    try:
        for r in json.load(open(fn)): OTHER.setdefault(r["mint"], {})[w] = r["sol"]
    except Exception: pass
done = set()
if os.path.exists(OUT):
    done = {json.loads(l)["mint"] for l in open(OUT)}


def create_sig(mint, before):
    oldest = None; b = before
    for _ in range(10):
        r = rpc("getSignaturesForAddress", [mint, {"limit": 1000, "before": b}])
        if not isinstance(r, list) or not r: break
        oldest = r[-1]; b = r[-1]["signature"]
        if len(r) < 1000: break
    return oldest


def work(row):
    m = row["mint"]
    f = dict(mint=m, sol=row["sol"], k=round(row["sol"] / 0.49383), pnl_pct=row["pnl_pct"], bt=row["bt"], mc_pre=row["mc_pre"],
             land=row["land"], cu=row["cu"], tip=row["tip"], tiplab=row["tiplab"], other=OTHER.get(m, {}))
    cs = create_sig(m, row["sig"])
    if not cs: return f
    cslot = cs["slot"]
    f["dslot"] = row["slot"] - cslot
    b = get_block(cslot)
    if not isinstance(b, dict): return f
    nv = [t for t in b.get("transactions", []) if not is_vote(t)]
    ci = None
    for i, t in enumerate(nv):
        tr, cr = events((t.get("meta") or {}).get("logMessages"))
        if any(c["mint"] == m for c in cr):
            ci = i; cr0 = [c for c in cr if c["mint"] == m][0]; tr0 = tr; break
    if ci is None: return f
    ct = nv[ci]; s, keys = tx_summary(ct, TM)
    f["name"] = cr0.get("name", ""); f["sym"] = cr0.get("symbol", ""); f["uri"] = (cr0.get("uri") or "").split("://")[-1].split("/")[0]
    f["dev"] = sum(e["sol"] for e in tr0 if e["mint"] == m and e["buy"]) / 1e9
    f["ctips"] = [(x[0], x[1] / 1e9) for x in s["tips"]]
    f["moon"] = any(str(x[0]).startswith("lunar") or str(x[2]).startswith("moon") for x in s["tips"])
    f["ctip_sol"] = sum(x[1] for x in s["tips"]) / 1e9
    f["c_cu"] = s["cu_price"]; f["c_fee"] = s["fee"] / 1e9; f["creator"] = s["payer"]
    f["mayhem"] = any("ayhem" in l for l in (ct["meta"].get("logMessages") or []))
    f["cpos"] = ci; f["nnv"] = len(nv)
    # glued bundle + buyers after it in the create slot
    gl, gs, j = 0, 0, ci + 1
    while j < len(nv):
        tr, _ = events((nv[j].get("meta") or {}).get("logMessages"))
        ev = [e for e in tr if e["mint"] == m and e["buy"]]
        if ev and (nv[j].get("meta") or {}).get("err") is None:
            gl += 1; gs += sum(e["sol"] for e in ev); j += 1
        else: break
    f["glued"] = gl; f["gsol"] = gs / 1e9
    nb, sb, my = 0, 0, None
    for i in range(j, len(nv)):
        t = nv[i]; tr, _ = events((t.get("meta") or {}).get("logMessages"))
        ev = [e for e in tr if e["mint"] == m]
        if not ev or (t.get("meta") or {}).get("err") is not None: continue
        if any(e["user"] == W for e in ev): my = i; break
        nb += sum(1 for e in ev if e["buy"]); sb += sum(e["sol"] for e in ev if e["buy"]) - sum(e["sol"] for e in ev if not e["buy"])
    f["pos"] = (my - ci) if my is not None else None
    f["n_ahead_slot"] = nb; f["sol_ahead_slot"] = sb / 1e9
    return f


todo = [r for r in R if r["mint"] not in done]
print("todo", len(todo), flush=True)
with ThreadPoolExecutor(3) as ex, open(OUT, "a") as fo:
    for f in ex.map(work, todo):
        fo.write(json.dumps(f) + "\n"); fo.flush()
print("DONE", flush=True)
