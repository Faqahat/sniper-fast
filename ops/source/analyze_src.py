#!/usr/bin/env python3
"""Rank slot-0 SOURCE fingerprints: his picks vs population. Lift, recall, coverage,
OOS chronological persistence, and whether source adds beyond vanilla. Fit a source rule
and test if it reproduces his ~1% selectivity with high precision/recall."""
import json, sys
from collections import Counter, defaultdict
sys.path.insert(0, "/root/profit_backtest")

his = [r for r in json.load(open("/root/source/his_src.json")) if r.get("ok")]
pop = [r for r in json.load(open("/root/source/pop_src.json")) if r.get("ok")]
# merge vanilla/mayhem/holder_reward flags from feat_500 (his) & creates.json (pop)
feath = {r["mint"]: r for r in json.load(open("/root/last500/feat_500.json"))}
cren = {c["mint"]: c for c in json.load(open("/root/profit_backtest/creates.json"))}
for r in his:
    f = feath.get(r["mint"], {})
    r["vanilla"] = f.get("vanilla"); r["mayhem"] = f.get("mayhem")
    r["holder_reward"] = f.get("holder_reward"); r["dev_buy"] = f.get("dev_buy")
    r["create_slot"] = f.get("create_slot")
for r in pop:
    c = cren.get(r["mint"], {})
    mh = c.get("mayhem"); hr = c.get("holder_reward"); cb = c.get("cashback")
    r["mayhem"] = mh; r["holder_reward"] = hr
    r["vanilla"] = int(mh == 0 and hr == 0 and cb == 0) if mh is not None else None
    r["dev_buy"] = c.get("dev_buy")

NH = len(his); NP = len(pop)
print(f"HIS ok={NH}  POP ok={NP}\n")

def host_tool(h):
    """classify uri host into a deployer-tool label."""
    if not h: return "none"
    if "ipfs.io" in h: return "ipfs.io(plain)"
    if "j7tracker" in h: return "j7tracker"
    if "uxento" in h: return "uxento"
    if "mypinata" in h or "pinata" in h: return "pinata/pumpdefault"
    if "rapidlaunch" in h: return "rapidlaunch"
    if "quicknode" in h: return "quicknode"
    if "violasnipe" in h: return "violasnipe"
    if "googleapis" in h: return "gcs"
    if "extraction.live" in h: return "extraction"
    return "other:" + h

for r in his + pop: r["tool"] = host_tool(r.get("uri_host"))

def dist(rows, fld, top=12):
    c = Counter(str(x.get(fld)) for x in rows)
    return c, len(rows)

print("=" * 70)
print("SINGLE-FEATURE SOURCE DISTRIBUTIONS (his vs pop, lift=Ph/Pp)")
print("=" * 70)
def lift_table(fld, label):
    ch = Counter(str(x.get(fld)) for x in his)
    cp = Counter(str(x.get(fld)) for x in pop)
    keys = set(ch) | set(cp)
    rows = []
    for k in keys:
        ph = ch[k] / NH; pp = cp[k] / NP
        lift = (ph / pp) if pp > 0 else float("inf")
        rows.append((k, ph, pp, lift, ch[k], cp[k]))
    rows.sort(key=lambda x: -x[1])
    print(f"\n--- {label} ({fld}) ---")
    print(f"{'value':32s} {'Ph':>6s} {'Pp':>6s} {'lift':>6s} {'nh':>4s} {'np':>4s}")
    for k, ph, pp, lift, nh, np_ in rows[:14]:
        lf = f"{lift:5.2f}" if lift != float("inf") else " inf"
        print(f"{k[:32]:32s} {ph:6.3f} {pp:6.3f} {lf:>6s} {nh:4d} {np_:4d}")

lift_table("tool", "DEPLOYER TOOL (uri host)")
lift_table("prog_seq", "CREATE-TX STRUCTURE (program sequence)")
lift_table("cu_limit", "compute-unit LIMIT")
lift_table("cu_price", "compute-unit PRICE")
lift_table("dev_buy_disc", "dev-buy instruction discriminator")
lift_table("mint_suffix_pump", "mint vanity ends 'pump'")
lift_table("mint_suffix4", "mint suffix(4)")
lift_table("has_jito_tip", "jito tip in create tx")
lift_table("n_pump_ix", "# pump instructions")
lift_table("n_cb_ix", "# compute-budget ix")

# ---- group tools into "pro-terminal" set and test as a rule ----
print("\n" + "=" * 70)
print("TOOL GROUPS as selection rule (recall his / coverage pop)")
print("=" * 70)
groups = {
    "j7tracker only": {"j7tracker"},
    "uxento only": {"uxento"},
    "j7+uxento": {"j7tracker", "uxento"},
    "all pro-terminals (j7+uxento+rapidlaunch+quicknode+viola+extraction)":
        {"j7tracker", "uxento", "rapidlaunch", "quicknode", "violasnipe", "extraction"},
    "NOT plain ipfs.io": None,  # special
    "ipfs.io(plain) only": {"ipfs.io(plain)"},
}
for name, s in groups.items():
    if name == "NOT plain ipfs.io":
        rh = sum(1 for x in his if x["tool"] != "ipfs.io(plain)")
        rp = sum(1 for x in pop if x["tool"] != "ipfs.io(plain)")
    else:
        rh = sum(1 for x in his if x["tool"] in s)
        rp = sum(1 for x in pop if x["tool"] in s)
    recall = rh / NH; cov = rp / NP
    print(f"{name[:52]:52s} recall_his={recall:5.3f} ({rh:3d})  cov_pop={cov:5.3f} ({rp:4d})  lift={recall/cov if cov else 0:4.2f}")

# ---- does source add BEYOND vanilla? condition on vanilla ----
print("\n" + "=" * 70)
print("DOES SOURCE ADD BEYOND VANILLA? (tool dist among vanilla-only)")
print("=" * 70)
hv = [x for x in his if x.get("vanilla") == 1]
pv = [x for x in pop if x.get("vanilla") == 1]
print(f"his vanilla={len(hv)}/{NH}  pop vanilla={len(pv)}/{NP}")
ch = Counter(x["tool"] for x in hv); cp = Counter(x["tool"] for x in pv)
print(f"{'tool(vanilla only)':24s} {'Ph|v':>6s} {'Pp|v':>6s} {'lift':>6s}")
for k in sorted(set(ch)|set(cp), key=lambda z: -ch[z]):
    ph = ch[k]/len(hv) if hv else 0; pp = cp[k]/len(pv) if pv else 0
    lf = ph/pp if pp else float('inf')
    print(f"{k[:24]:24s} {ph:6.3f} {pp:6.3f} {(f'{lf:5.2f}' if lf!=float('inf') else ' inf'):>6s}")

# ---- OOS chronological persistence: split his by create_slot median ----
print("\n" + "=" * 70)
print("OOS PERSISTENCE: his tool dist, IS (early half) vs OOS (late half) by create_slot")
print("=" * 70)
hs = [x for x in his if x.get("create_slot")]
hs.sort(key=lambda x: x["create_slot"])
mid = len(hs)//2
IS, OOS = hs[:mid], hs[mid:]
ci = Counter(x["tool"] for x in IS); co = Counter(x["tool"] for x in OOS)
print(f"IS n={len(IS)}  OOS n={len(OOS)}")
print(f"{'tool':24s} {'P_IS':>6s} {'P_OOS':>6s}")
for k in sorted(set(ci)|set(co), key=lambda z:-(ci[z]+co[z])):
    print(f"{k[:24]:24s} {ci[k]/len(IS):6.3f} {co[k]/len(OOS):6.3f}")

# ---- combined source rule search: maximize recall at coverage near pop 1% is impossible
#      if his favored sources cover <100% of his. Report cumulative coverage of his by tool. ----
print("\n" + "=" * 70)
print("CUMULATIVE: can ANY source subset recall most of his at low pop coverage?")
print("=" * 70)
ch_all = Counter(x["tool"] for x in his)
cp_all = Counter(x["tool"] for x in pop)
# order tools by his-lift (Ph/Pp), accumulate
order = sorted(ch_all, key=lambda k: -((ch_all[k]/NH)/(cp_all[k]/NP) if cp_all[k] else 999))
cum_h = cum_p = 0
print(f"{'add tool (by lift desc)':24s} {'cumRecall':>9s} {'cumCov':>7s}")
for k in order:
    cum_h += ch_all[k]; cum_p += cp_all[k]
    print(f"{k[:24]:24s} {cum_h/NH:9.3f} {cum_p/NP:7.3f}")
