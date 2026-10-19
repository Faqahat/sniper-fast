#!/usr/bin/env python3
# READ-ONLY. Build the target's per-mint trade list from wtx.jsonl, resolve each mint's create sig/slot
# (getSignaturesForAddress on the mint before his first buy; oldest = create), merge /root/sel2/pos_meta.json.
# out: his_mints.json, his_targets.json (for blk.py)
import sys, json, os, collections, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import rpc

W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
csig = {}
for l in open("/root/nob/csigs.jsonl"):
    x = json.loads(l)
    if not x["err"]:
        csig[x["signature"]] = x["slot"]
txs = [json.loads(l) for l in open("/root/nob/wtx.jsonl")]
txs = [t for t in txs if "fail" not in t]
txs.sort(key=lambda t: (t["slot"], t["sig"]))
M = collections.defaultdict(lambda: {"buys": [], "sells": [], "dsol_ok": 0, "fee_fail": 0, "n_fail": 0, "n_ok": 0, "txs": []})
other = collections.Counter()
for t in txs:
    mine = [e for e in t.get("ev", []) if e["user"] == W]
    if t["err"]:
        for m in t.get("mints", [])[:1]:
            M[m]["fee_fail"] += t.get("fee") or 0
            M[m]["n_fail"] += 1
        if not t.get("mints"):
            other["fail_nomint"] += 1
        continue
    if not mine:
        other["ok_no_trade"] += 1
        continue
    mints = {e["mint"] for e in mine}
    for m in mints:
        d = M[m]
        d["n_ok"] += 1
        if len(mints) == 1:
            d["dsol_ok"] += t["dsol"] or 0
        else:
            other["multi_mint_tx"] += 1
        for e in mine:
            if e["mint"] != m:
                continue
            row = {"sig": t["sig"], "slot": t["slot"], "bt": t["bt"], "sol": e["sol"], "tok": e["tok"], "vsol": e["vsol"], "vtok": e["vtok"],
                   "fee": t["fee"], "cu_price": t["cu_price"], "tips": t["tips"], "dsol": t["dsol"], "progs": t["progs"]}
            (d["buys"] if e["buy"] else d["sells"]).append(row)
print("other", dict(other))
bought = {m: d for m, d in M.items() if d["buys"]}
print("mints with buys", len(bought), "mints touched (incl failed only)", len(M))
pos = json.load(open("/root/sel2/pos_meta.json"))


def resolve(m):
    d = bought[m]
    b0 = d["buys"][0]
    before = b0["sig"]
    oldest = None
    for _ in range(5):
        r = rpc("getSignaturesForAddress", [m, {"before": before, "limit": 1000}])
        if not isinstance(r, list) or not r:
            break
        hit = [x for x in r if x["signature"] in csig]
        if hit:
            oldest = hit[-1]
            break
        oldest = r[-1]
        if len(r) < 1000:
            break
        before = r[-1]["signature"]
    if oldest is None or oldest["signature"] not in csig:
        # his buy may be in the create slot listed after the create in a different order: try sigs of the slot incl. his
        r = rpc("getSignaturesForAddress", [m, {"before": d["buys"][-1]["sig"], "limit": 1000}])
        if isinstance(r, list):
            hit = [x for x in r if x["signature"] in csig]
            if hit:
                oldest = hit[-1]
    d["create_sig"] = oldest["signature"] if oldest else None
    d["create_slot"] = oldest["slot"] if oldest else None
    d["in_csigs"] = bool(oldest and oldest["signature"] in csig)


with ThreadPoolExecutor(8) as ex:
    list(ex.map(resolve, list(bought)))
for m, d in bought.items():
    if not d.get("in_csigs") and m in pos and pos[m].get("create_sig") in csig:
        d["create_sig"] = pos[m]["create_sig"]
        d["create_slot"] = csig[d["create_sig"]]
        d["in_csigs"] = True
    d["in_pos_meta"] = m in pos
print("resolved in csigs", sum(1 for d in bought.values() if d.get("in_csigs")))
print("pos_meta mints", len(pos), "of which bought in wtx", sum(1 for m in pos if m in bought),
      "pos create_sig in csigs", sum(1 for m in pos if pos[m].get("create_sig") in csig))
json.dump(bought, open("/root/nob/his_mints.json", "w"))
tg = [{"slot": d["create_slot"], "sig": d["create_sig"], "tag": "his", "mint": m} for m, d in bought.items() if d.get("in_csigs")]
# pos_meta mints not in wtx (should be none in ledger window)
for m, p in pos.items():
    if m not in bought and p.get("create_sig") in csig:
        tg.append({"slot": csig[p["create_sig"]], "sig": p["create_sig"], "tag": "his_pos_only", "mint": m})
json.dump(tg, open("/root/nob/his_targets.json", "w"))
print("targets", len(tg))
