#!/usr/bin/env python3
# GDM forward test, step 5: score the forward rows with the FROZEN rule (dryrun/frozen_gdm.json, sha checked), both the LM
# model (with token metadata) and the L fallback; FINAL-2 live picks from the shadow log; UNIONs; replay every pick with
# gdm/become_eval6.py (= core/become_eval.py with Pool(6)) on OUR phase-A dir; summary appended to fwd/forward_gdm.txt.
# usage: python3 -I fwd_eval.py <feats prefix> <freeze_bt> <hi_bt> <data_end>
import sys, os, json, hashlib, time, datetime, subprocess, statistics, collections
import numpy as np
FP, FREEZE, HI, DEND = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
GDM = "/home/moiz/sniper/ops/overnight/gdm"; FZP = "/home/moiz/sniper/ops/overnight/dryrun/frozen_gdm.json"
FD = os.environ.get("GDM_FWD_OUT", f"{GDM}/fwd"); REPORT = os.environ.get("GDM_FWD_REPORT", "forward_gdm.txt"); TAG = os.environ.get("GDM_FWD_TAG", "")
os.makedirs(FD, exist_ok=True)
PKT = datetime.timezone(datetime.timedelta(hours=5)); fmt = lambda t: datetime.datetime.fromtimestamp(t, PKT).strftime("%m-%d %H:%M")
raw = open(FZP).read(); h = hashlib.sha256(raw.encode()).hexdigest()
assert h == open(FZP + ".sha256").read().strip(), "frozen_gdm.json changed - refusing to score"
FZ = json.loads(raw)
Z = np.load(FP + ".npz"); M = json.load(open(FP + "_meta.json")); mints = M["mints"]
def bins(X, E):
    B = np.zeros(X.shape, np.int32)
    for j, e in enumerate(E):
        b = np.searchsorted(np.array(e), X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; B[:, j] = b
    return B
def tree_pred(t, B):
    out = np.zeros(len(B)); stack = [(t, np.arange(len(B)))]
    while stack:
        n, ix = stack.pop()
        if "w" in n: out[ix] = n["w"]; continue
        m = B[ix, n["f"]] <= n["b"]; stack.append((n["l"], ix[m])); stack.append((n["r"], ix[~m]))
    return out
SC = {}; PK = {}
for nm in ("LM", "L"):
    Mo = FZ["models"][nm]
    if len(mints):
        X = Z["X"][:, [M["names"].index(k) for k in Mo["features"]]]; B = bins(X, Mo["edges"])
        s = np.mean([Mo["F0"] + Mo["lr"] * sum(tree_pred(t, B) for t in b["trees"]) for b in Mo["bag"]], 0)
    else: s = np.zeros(0)
    SC[nm] = s; PK[nm] = [m for m, v, g in zip(mints, s, Z["guard"]) if v >= Mo["threshold_top3"] and g == 1]
os.environ["RP_PHASEA_R2"] = "phaseA_gdmfwd"                # rp reads R2 trades from OUR phase-A dir (set before import)
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
assert rp.RUNS["R2"][1] == "phaseA_gdmfwd"
L = rp.load_launches()
f2 = []
for l in open("/home/moiz/sniper-data/collect/shadow/scores_v3.jsonl"):
    try: r = json.loads(l)
    except Exception: continue
    if r.get("type") == "decide" and r.get("final_pick"):
        c = L.get(r.get("mint"))
        if c and c.get("bt") and FREEZE < c["bt"] < HI: f2.append(r["mint"])
f2 = sorted(set(f2))
LISTS = {"FINAL2_live": f2, "GDM_LM": sorted(PK["LM"]), "GDM_L": sorted(PK["L"]), "UNION_LM": sorted(set(f2) | set(PK["LM"])), "UNION_L": sorted(set(f2) | set(PK["L"]))}
for k, v in LISTS.items(): json.dump(v, open(f"{FD}/picks_{k}.json", "w"))
cand = sorted(set().union(*LISTS.values())); json.dump(cand, open(f"{FD}/cand.json", "w"))
now = time.time()
hdr = [f"=== {TAG}GDM forward test (FRZ-GDM-U, sha {h[:12]}, frozen {FZ['frozen_at_pkt']}) run {datetime.datetime.fromtimestamp(now, PKT).strftime('%Y-%m-%d %H:%M PKT')}",
       f"window: launches created {fmt(FREEZE)} -> {fmt(HI)} PKT (data to {fmt(DEND)}; each launch >= 6 min old) | scored launches {len(mints)} | "
       f"GDM picks LM {len(PK['LM'])} ({len(PK['LM']) / max(1, len(mints)):.1%}), L {len(PK['L'])} | FINAL-2 live picks {len(f2)} | "
       f"overlap F2&LM {len(set(f2) & set(PK['LM']))}, F2&L {len(set(f2) & set(PK['L']))}"]
lines = list(hdr)
if cand:
    env = dict(os.environ, RP_PHASEA_R2="phaseA_gdmfwd", LANDS="30,45,75", OUT_SFX="_x")
    r = subprocess.run(["nice", "python3", "-I", f"{GDM}/become_eval6.py", f"{FD}/cand.json", "0.5", "1.005"], env=env, capture_output=True, text=True)
    if r.returncode: print(r.stdout[-1500:], r.stderr[-1500:]); raise SystemExit("become_eval failed")
    R = json.load(open(f"{FD}/cand_become_B0.5_x.json"))
    g = {"__name__": "gsum_lib"}; src = open(f"{GDM}/gsum.py").read(); sys.argv = ["gsum.py"]
    os.environ["EXITS"] = "t8,t10"; os.environ["LANDS"] = "75,45,30"; os.environ["VARS"] = "slip,proafter_slip,nosnip,base"
    exec(src[:src.index('if __name__ == "__main__":')], g)
    S = {k: g["summarize"](R, set(v), FREEZE, HI) for k, v in LISTS.items()}
    # follower slippage limits are known only for txs someone fetched (core/slip_args.jsonl; this pipeline does no RPC):
    SLIP = rp.load_slip(); cov = {}
    byb = collections.defaultdict(set)
    for m in cand:
        if m in L: byb[rp.bucket(m)].add(m)
    tot = collections.Counter(); known = collections.Counter()
    for b, ms in byb.items():
        for m, tr in rp.read_bucket("R2", b, ms).items():
            S0 = L[m]["slot"]; st = rp.structure(tr, L[m])
            for t in tr[st["g_end"]:]:
                if t["buy"] and t["user"] not in st["insiders"] and t["s"] <= S0 + 50:
                    for k, v in LISTS.items():
                        if m in v: tot[k] += 1; known[k] += t["sig"] in SLIP
    lines.append("per list / landing / variant, exits 8 s | 10 s: fills/tries | today-cost SOL | PRO-cost SOL | median SOL per fill | win | PRO w/o top 5 | PRO halves")
    lines.append("NOTE: follower slippage limits come only from core/slip_args.jsonl (fetched by other jobs for FINAL-2 picks); when coverage differs between lists, compare on nosnip / base")
    for k in LISTS:
        lines.append(f" {k} ({len(LISTS[k])} picks; follower slippage limits known for {known[k]}/{tot[k]} follower buys <= 10 s)")
        for Lm in ("75", "45", "30"):
            for var in ("slip", "proafter_slip", "nosnip", "base"):         # base = real path, no slippage drops (fair when limit coverage differs)
                a = next(x for x in S[k] if x["L"] == Lm and x["var"] == var and x["ex"] == "t8"); b = next(x for x in S[k] if x["L"] == Lm and x["var"] == var and x["ex"] == "t10")
                lines.append(f"   L{Lm} {var:13s} {a['fills']:3d}/{a['att']:3d} | 8 s: today {a['cur']:+6.3f} PRO {a['pro']:+6.3f} med {a['med']:+.4f} win {a['win']:.0%} w/o5 {a['wo5']:+6.3f} "
                             f"halves {a['h1']:+.2f}/{a['h2']:+.2f} | 10 s: today {b['cur']:+6.3f} PRO {b['pro']:+6.3f} med {b['med']:+.4f} win {b['win']:.0%}")
    json.dump(dict(header=hdr, lists=LISTS, summary=S, coverage={k: [known[k], tot[k]] for k in LISTS}), open(f"{FD}/{REPORT.replace('.txt', '')}_latest.json", "w"))
else:
    lines.append("no forward picks yet (no launch created after the freeze is >= 6 min old in the synced data, or none was picked)")
    json.dump(dict(header=hdr, lists=LISTS), open(f"{FD}/{REPORT.replace('.txt', '')}_latest.json", "w"))
with open(f"{FD}/{REPORT}", "a") as fo: fo.write("\n".join(lines) + "\n\n")
print("\n".join(lines))
