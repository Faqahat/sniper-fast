import json, glob
NAMES=json.load(open("/root/copyable/candidates.json"))
nm={c["wallet"]:c["name"] for c in NAMES}
out={}
for f in glob.glob("/root/copyable/copyres/*.json"):
    d=json.load(open(f)); w=d["wallet"]
    out[w]={"name":nm.get(w,"?"),"med_lag_mult":d["med_lag_mult"],
            "frac_buys_price_moved_gt5pct":d["frac_buys_price_moved_gt5pct"],
            "n_closed":d["n_closed"],"their_net":d["their_net"],"copy_net":d["copy_net"]}
json.dump(out, open("/root/copyable/copy_results.json","w"),indent=1)
print("wrote copy_results.json for",list(out.keys()))
