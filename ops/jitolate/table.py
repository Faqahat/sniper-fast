# READ-ONLY: markdown per-buy timeline from buys.json. Time in slot ~ position fraction x 203.5 ms (txs assumed evenly spread).
import json
SL = 203.5
B = json.load(open("/root/jitolate/buys.json"))
def path(f):
    lb = f["landed_bundle"]
    if lb and lb["same_as_ours"]: return "our jito-bundle"
    if lb and lb["ntx"] == 2: return "Helius Sender (2-tx bundle, its tip tx)"
    return "non-bundle (" + {"route:harmonic": "nozomi/staked-rpc", "route:bam": "LandX/staked-rpc", "route:jito": "LandX/Helius-TPU/staked-rpc"}.get(f["route"], f["route"]) + ")"
print("| tag | mint | S leader (slot#/4) | create pos / txs (≈ms into S) | first feed | det→send ms | Jito result | landed | land pos / txs (≈ms) | landed via | outsiders ahead in S |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for f in B:
    cms = f["create_idx"] / f["S_nonvote"] * SL
    lms = f["land_idx"] / f["land_nonvote"] * SL
    land = "S" if f["land"] == f["slot"] else f"S+{f['land']-f['slot']}"
    ok_out = [x for x in f["S_buys_after_create"] if x["ok"] and not x["is_me"] and x["d"] > 3]
    if land == "S":
        ahead = sum(1 for x in ok_out if x["d"] < f["land_idx"] - f["create_idx"])
    else:
        ahead = f"{len(ok_out)} (all of S) + {f.get('buys_before_us_in_land_slot')} in S+1"
    after_send = (lms + (SL if land != "S" else 0)) - (cms + 14 + f["detect_to_send_ms"])
    print(f"| {f['tag']} | {f['mint'][:6]} | {f['S_client']} ({f['S_slot_in_window']+1}/4) | {f['create_idx']}/{f['S_nonvote']} (≈{cms:.0f}) | {f['first_feed']} | {f['detect_to_send_ms']} | {f.get('jito_result','')[:28]} | {land} | {f['land_idx']}/{f['land_nonvote']} (≈{lms:.0f}; send→land ≈{after_send:.0f} ms) | {path(f)} | {ahead} |")
