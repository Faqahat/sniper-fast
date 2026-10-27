#!/usr/bin/env python3
# When WE spill to the next block, do the fastest pros still get into the dump's own block? Split by the dump's real position in its block
# (verify.json: real block sizes from getBlock). Same fires as h2h.py (runs 1-10, where verify.json has positions).
import json, collections, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
D = os.path.dirname(os.path.abspath(__file__)) + "/.."
V = {v["sig"]: v for v in json.load(open(f"{D}/latest/verify.json"))}
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
PROS = {"HkQ7hMjy", "G9G3dCBG", "5w8xtjc6", "6n2cCJrr", "8PgC4ngp", "9k78QZyw", "haqqiUUX"}
FILES = [f"dip_r{i}.jsonl" for i in range(1, 11)] + ["dip_ams_r9.jsonl", "dip_ams_r10.jsonl"]
B = collections.defaultdict(lambda: dict(n=0, our_spill=0, pro_dumps=0, pro_same=0, pro_same_when_we_spill=0, we_spill_pro_there=0, ms_pro_same=[]))
for fn in FILES:
    fires = {}; tape = collections.defaultdict(list)
    for l in open(f"{D}/{fn}"):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("ev") == "fire": fires[r["buy_sig"]] = r
        elif r.get("ev") == "tape": tape[r["mint"]].append(r)
    for sig, f in fires.items():
        v = V.get(sig)
        if not v or v.get("dump_pos") is None: continue
        S = f["slot"]; t0 = f["t_dump_rx"]; b = B[min(int(v["dump_pos"] * 4), 3)]
        b["n"] += 1; b["our_spill"] += bool(v["spill"])
        pro = [x for x in tape[f["mint"]] if x["buy"] and x["user"][:8] in PROS and S <= x["slot"] <= S + 1 and x["t"] >= t0]
        if not pro: continue
        first = min(pro, key=lambda x: (x["slot"], x["idx"])); b["pro_dumps"] += 1
        if first["slot"] == S: b["pro_same"] += 1; b["ms_pro_same"].append((first["t"] - t0) / 1e6)
        if v["spill"]: b["we_spill_pro_there"] += 1; b["pro_same_when_we_spill"] += first["slot"] == S
print("dump position in its block | fires | WE spill | dumps a pro bought | pro got the SAME block | on dumps where WE spilled: pro still got the same block")
for k in range(4):
    b = B[k]; ms = sorted(b["ms_pro_same"])
    print(f"  {k*25:3d}-{k*25+25:3d}%  | {b['n']:4d} | {b['our_spill']/max(b['n'],1):4.0%} | {b['pro_dumps']:4d} | {b['pro_same']/max(b['pro_dumps'],1):4.0%} (their ms median {ms[len(ms)//2] if ms else float('nan'):.1f}) | {b['pro_same_when_we_spill']}/{b['we_spill_pro_there']}")
