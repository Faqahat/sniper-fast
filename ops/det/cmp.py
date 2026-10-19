#!/usr/bin/env python3
# READ-ONLY: BEFORE vs AFTER paper comparison (det audit 2026-10-18).
# usage: cmp.py <before_log> <after_log> <truth.jsonl> <his.jsonl> <contest.jsonl> <paths_before> <paths_after>
import sys, re, json, statistics as st, collections as C
sys.path.insert(0, "/root/det")
sys.path.insert(0, "/root/det/lib")
from dlib import W4, WSOL
from rl import labels

BL, AL, TR, HIS, CON, PB, PA = sys.argv[1:8]
SOLQ = "11111111111111111111111111111111"


def parse_log(fn):
    L = {"fired": {}, "done": {}, "stats": {}, "detect": [], "feedstatus": [], "feeds": [], "restarts": 0, "stalls": 0}
    for l in open(fn, errors="replace"):
        m = re.search(r"PAPER launch #\d+ slot=(\d+) mint=(\w+) dev_buy=(\d+)", l)
        if m:
            L["fired"].setdefault(m.group(2), (int(m.group(1)), int(m.group(3))))
            continue
        m = re.search(r"PAPER done mint=(\w+) .*?fill=([\d.]+)x peak_r=([\d.]+) .*?@1\.00=([+-][\d.]+) @1\.05=([+-][\d.]+) @1\.08=([+-][\d.]+) @1\.10=([+-][\d.]+) @1\.25=([+-][\d.]+)", l)
        if m:
            L["done"][m.group(1)] = dict(peak=float(m.group(3)), f100=float(m.group(4)), f105=float(m.group(5)), f110=float(m.group(7)), f125=float(m.group(8)))
            continue
        m = re.search(r"PAPER stats mint=(\w+) rd_ok=(\d+) rd_fail=(\d+) wait_ms=(\d+)", l)
        if m:
            L["stats"][m.group(1)] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
            continue
        if "DETECT feed=" in l:
            d = dict(re.findall(r"(\w+)=(\S+)", l))
            L["detect"].append(d)
            continue
        if "FEEDSTATUS" in l:
            L["feedstatus"].append(l.strip()[:200])
        if "FEEDS t=" in l:
            L["feeds"].append(l.strip())
        if "PAPER_DET (re)launch" in l:
            L["restarts"] += 1
        if "PAPER_DET stall" in l:
            L["stalls"] += 1
    return L


B, A = parse_log(BL), parse_log(AL)
T = [json.loads(l) for l in open(TR)]
T = [r for r in T if r.get("mint") and not r.get("miss") and not r.get("exc")]
# window = slots both engines were running: from the later start to the earlier end (by fired/detect slots)
def span(L):
    s = [v[0] for v in L["fired"].values()] + [int(d["slot"]) for d in L["detect"] if "slot" in d]
    return (min(s), max(s)) if s else (0, 0)
sb, sa = span(B), span(A)
W0, W1 = max(sb[0], sa[0], min(r['slot'] for r in T)), min(sb[1], sa[1], max(r['slot'] for r in T) - 2)
print(f"window slots {W0}..{W1} ({(W1-W0)*0.213/60:.0f} min at 213 ms/slot) | BEFORE span {sb} AFTER span {sa}")
inw = lambda s: W0 <= s <= W1
TW = [r for r in T if inw(r["slot"])]
ok = [r for r in TW if not r.get("err")]
fail = [r for r in TW if r.get("err")]
ok_mints = {r["mint"] for r in ok}
print(f"on-chain creates in window: {len(ok)} OK + {len(fail)} failed create txs (phantoms: failed mint never landed: {len({r['mint'] for r in fail} - ok_mints)})")

ev = lambda r: r.get("ev") or {}
sol = lambda r: ev(r).get("quote_mint") in (SOLQ, WSOL)
band = lambda x: 0.5e9 <= x <= 8e9
snip_true = lambda r: (ev(r).get("fee_bps") or 0) == 0 and not ev(r).get("mayhem")
snip_args = lambda r: (r["args"].get("fee_bps") or 0) == 0 and not r["args"].get("mayhem")
TRUE_EL = [r for r in ok if sol(r) and r.get("kind") == "create_v2" and band(r["true_dev"]) and snip_true(r) and not r["bl"]]
true_el = {r["mint"] for r in TRUE_EL}
rule_B = {r["mint"] for r in TW if r.get("top") and not r.get("acct_alt") and band(r["dev_before"]) and snip_args(r) and not r["bl"]}
rule_A = {r["mint"] for r in TW if r.get("top") and sol(r) and r.get("kind") == "create_v2" and band(r["dev_after"]) and snip_args(r) and not r["bl"]}

# ---- 1. coverage (AFTER logs every create; BEFORE only what it fires)
detA = [d for d in A["detect"] if inw(int(d["slot"]))]
firstA = {d["mint"]: d for d in detA if d.get("first") == "1"}
by_feed = C.defaultdict(set)
for d in detA:
    by_feed[d["feed"]].add(d["mint"])
cov = ok_mints & set(firstA)
print("\n== 1. COVERAGE (on-chain OK creates in window) ==")
unk = set(firstA) - ok_mints - {r['mint'] for r in fail}
print(f"AFTER detected {len(cov)}/{len(ok_mints)} = {len(cov)/max(len(ok_mints),1):.1%}  (DETECT mints not among on-chain creates: {len(unk)}, by kind {dict(C.Counter(firstA[m].get('kind') for m in unk))}, by verdict {dict(C.Counter(firstA[m].get('verdict') for m in unk))})")
for f, s in sorted(by_feed.items()):
    print(f"   feed {f:8} saw {len(s & ok_mints)}/{len(ok_mints)} = {len(s & ok_mints)/max(len(ok_mints),1):.1%}")
miss = [r for r in ok if r["mint"] not in firstA]
print("   AFTER misses by cause:", dict(C.Counter("cpi" if not r.get("top") else "alt" if r.get("acct_alt") else "other" for r in miss)))
cpiA = [m for m, d in firstA.items() if d.get("kind") == "cpi"]
print(f"   of which CPI creates now DETECTED (kind=cpi, not fired): {len(set(cpiA) & ok_mints)} of {sum(1 for r in ok if not r.get('top'))} on-chain CPI creates")
print(f"BEFORE: sees only top-level creates with static accounts: {sum(1 for r in ok if r.get('top') and not r.get('acct_alt'))}/{len(ok)} = "
      f"{sum(1 for r in ok if r.get('top') and not r.get('acct_alt'))/max(len(ok),1):.1%} (CPI {sum(1 for r in ok if not r.get('top'))}, ALT {sum(1 for r in ok if r.get('top') and r.get('acct_alt'))})")
print(f"TRULY ELIGIBLE launches (SOL quote, create_v2, true dev 0.5-8, no fee/mayhem, host ok): {len(true_el)}")
for name, L, rule in (("BEFORE", B, rule_B), ("AFTER", A, rule_A)):
    fired = {m for m, v in L["fired"].items() if inw(v[0])}
    print(f"   {name:6} fired {len(fired):4} | rule-eligible on chain {len(rule & ok_mints):4} -> fired {len(fired & rule & ok_mints):4} ({len(fired & rule & ok_mints)/max(len(rule & ok_mints),1):.0%}) | "
          f"TRUE-eligible fired {len(fired & true_el):4} ({len(fired & true_el)/max(len(true_el),1):.0%}) | fired on non-SOL quote {sum(1 for r in ok if r['mint'] in fired and not sol(r))} | "
          f"on failed/phantom creates {len(fired - ok_mints)}")

# ---- 2. latency (AFTER DETECT)
print("\n== 2. DETECTION LATENCY (AFTER DETECT lines) ==")
pair = C.defaultdict(dict)
for d in detA:
    pair[d["mint"]].setdefault(d["feed"], d)
lag = C.defaultdict(list)
for d in detA:
    if d.get("lag_ms", "-") != "-":
        lag[d["feed"]].append(float(d["lag_ms"]))
for f, v in lag.items():
    v = sorted(v)
    print(f"   {f:8} lag after PoH position (BIASED: AFTER's PoH ms used 400 ms slots, real ~213): n={len(v)} p10={v[len(v)//10]:.0f} median={st.median(v):.0f} p90={v[9*len(v)//10]:.0f} ms")
both = [p for p in pair.values() if len(p) >= 2]
feeds = sorted(by_feed)
if len(feeds) >= 2 and both:
    f0, f1 = feeds[0], feeds[1]
    dts = [(int(p[f1]["t_rx"]) - int(p[f0]["t_rx"])) / 1e6 for p in both if f0 in p and f1 in p]
    w0 = sum(1 for x in dts if x > 0)
    sd = sorted(dts)
    print(f"   both feeds saw {len(dts)} creates: {f0} first {w0} ({w0/len(dts):.0%}), {f1} first {len(dts)-w0}; t({f1})-t({f0}) median {st.median(dts):+.2f} ms p1 {sd[len(sd)//100]:+.1f} p10 {sd[len(sd)//10]:+.2f} p90 {sd[9*len(sd)//10]:+.2f} p99 {sd[99*len(sd)//100]:+.1f} max {sd[-1]:+.1f}")
    pos = sorted(float(d["poh_ms"]) * 213 / 400 for d in detA if d["feed"] == "erpc" and d.get("poh_ms", "-") != "-")
    if pos:
        print(f"   create position inside its slot (erpc PoH, rescaled to 213 ms slots): p25 {pos[len(pos)//4]:.0f} median {st.median(pos):.0f} p75 {pos[3*len(pos)//4]:.0f} ms")
    only0 = sum(1 for p in pair.values() if list(p) == [f0])
    only1 = sum(1 for p in pair.values() if list(p) == [f1])
    print(f"   seen by ONE feed only: {f0}-only {only0}, {f1}-only {only1} (of {len(pair)} creates detected)")
print(f"   feed stalls/reconnects logged (AFTER FEEDSTATUS): {len(A['feedstatus'])}; watcher restarts BEFORE {B['restarts']-1} AFTER {A['restarts']-1}, stall-kills BEFORE {B['stalls']} AFTER {A['stalls']}")
for l in A["feedstatus"][:6]:
    print("     ", l)

# ---- 3/4. fired, 4yFAz
H = [json.loads(l) for l in open(HIS)]
hb = {}
for h in H:
    if inw(h["slot"]):
        for m, solx, tok in h.get("buys") or []:
            hb.setdefault(m, (h["slot"], solx))
create_slot = {r["mint"]: r["slot"] for r in ok}
hb_new = {m: v for m, v in hb.items() if m in create_slot and v[0] - create_slot[m] <= 150}
print(f"\n== 3/4. FIRED + 4yFAz ==\n4yFAz buys in window: {len(hb)} mints, {len(hb_new)} on launches created in the window (bought <=60 s after create)")
for name, L, rule in (("BEFORE", B, rule_B), ("AFTER", A, rule_A)):
    fired = {m for m, v in L["fired"].items() if inw(v[0])}
    det = set(firstA) if name == "AFTER" else None
    print(f"   {name:6} fired {len(fired)} | done {sum(1 for m in L['done'] if m in fired)} | his launches fired {len(fired & set(hb_new))}/{len(hb_new)}"
          + (f" | his launches DETECTED {len(det & set(hb_new))}/{len(hb_new)}" if det is not None else "")
          + f" | his launches truly eligible {len(true_el & set(hb_new))}")
hm = [r for r in ok if r["mint"] in hb_new]
print("   his launches by class:", dict(C.Counter(("cpi" if not r.get("top") else "nonSOL" if not sol(r) else "mayhem/fee" if not snip_true(r) else
      "dev<0.5" if r["true_dev"] < 0.5e9 else "dev>8" if r["true_dev"] > 8e9 else "bl" if r["bl"] else "eligible") for r in hm)))

# ---- 5. contested
CR = {}
for l in open(CON):
    try:
        r = json.loads(l)
    except Exception:
        continue
    if r.get("b") and "glued" in r["b"]:
        CR[r["mint"]] = r
print("\n== 5. CONTESTED (outsiders on chain, fired launches) ==")
for name, L in (("BEFORE", B), ("AFTER", A)):
    fired = [m for m, v in L["fired"].items() if inw(v[0]) and m in CR]
    lab = [labels(CR[m]["b"], CR[m]["s"]) for m in fired]
    if not lab:
        print(f"   {name}: no on-chain records"); continue
    n = len(lab)
    cS = sum(1 for x in lab if x["outS_n"] >= 1)
    c1 = sum(1 for x in lab if x["outS1_n"] >= 1)
    c01 = sum(1 for x in lab if x["out01_n"] >= 1)
    bund = sum(1 for m in fired if CR[m]["b"]["glued"] >= 1)
    print(f"   {name:6} n={n} | >=1 outsider in S {cS/n:.0%} | in S+1 {c1/n:.0%} | in S or S+1 {c01/n:.0%} | mean outsiders S+S1 {st.mean(x['out01_n'] for x in lab):.2f} | creator-bundled {bund/n:.0%}")

# ---- 6. PnL
print("\n== 6. PnL (1 SOL/trade) ==")
_src = open("/root/bsplit/real_his.py").read()
exec(_src[_src.index("K = 30.0"):_src.index("D = []")])                 # K, F (1.25%/side), SIZE
exec(_src[_src.index("def bundled"):_src.index("B_GRID")])              # bundled(), run() (own impact both sides)


def load_set(L, pf):
    """bundle classification from the on-chain block-S records (race_lib.block_record: the same glued-run classifier as
    bsplit2.py) + the engine's dumped path. The path (price / the ENGINE's floor) is rescaled to the TRUE post-create
    curve (on-chain base vsol), and dev = base - 30 SOL, so both engines are scored on identical on-chain terms."""
    out = []
    bad = 0
    for l in open(pf):
        try:
            d = json.loads(l)
        except Exception:
            bad += 1          # interleaved concurrent appends from the engine's path dump (engine bug, fixed in AFTER_FINAL)
            continue
        m = d["mint"]
        if not d.get("fired", True) or m not in CR or m not in L["fired"]:
            continue
        b = CR[m]["b"]
        base = b.get("base") or 30e9
        dev_eng = L["fired"][m][1]
        k = ((30e9 + dev_eng) / base) ** 2          # X_true = X_engine * floor_engine / floor_true
        r = {"mint": m, "slot": b["slot"], "dev": base - 30e9, "glued": b["glued"], "gsol": b["gsol"] / 1e9,
             "bmult": (b["gv"] / base) ** 2, "path": [[t, x * k] for t, x in d["path"]], "rescale": k}
        out.append(r)
    if bad:
        print(f"   ({pf}: {bad} garbled path lines skipped)")
    return out


def show(v):
    if not v:
        return "n=0"
    s = sorted(v)
    ex = s[:-5] if len(v) > 20 else s
    return f"n={len(v):3} mean {st.mean(v):+.4f} med {st.median(v):+.4f} ex-top5 {st.mean(ex):+.4f} win {sum(x>0 for x in v)/len(v):.0%} total {sum(v):+.2f}"


for name, L, pf in (("BEFORE", B, PB), ("AFTER", A, PA)):
    fired = {m for m, v in L["fired"].items() if inw(v[0])}
    fl = [d["f100"] for m, d in L["done"].items() if m in fired]
    f110 = [d["f110"] for m, d in L["done"].items() if m in fired]
    print(f"   {name:6} paper @floor (engine ladder)  {show(fl)}")
    print(f"   {name:6} paper @1.10x                  {show(f110)}")
    D = [r for r in load_set(L, pf) if r["mint"] in fired]
    print(f"   {name:6} scored on chain: {len(D)} (bundled {sum(bundled(r) for r in D)}, median post-bundle {st.median([max(1, r['bmult']) for r in D]) if D else 0:.3f}x floor, engine-floor rescale median {st.median([r['rescale'] for r in D]) if D else 0:.3f})")
    # realistic: entry right behind the creator bundle x 1.03 (Helius), own impact, 1.25%/side, buy prio+tip 0.010, sell 0.0003
    HIS_B = dict(legs=[(1.0, 1.10)], T=10000, sl=0.85)
    HIS_N = dict(legs=[(0.3, 1.3), (0.7, 3.0)], T=20000, sl=None)
    real = []
    for r in D:
        p = HIS_B if bundled(r) else HIS_N
        real.append(run(r, 1.03, p["legs"], p["T"], p["sl"], None, 0.0) - (0.010 + 0.0003 * 2) / SIZE)
    lad = []
    for r in D:   # the engine's own ladder rule (derisk .3 / ride 1.15 / trail .95 / ladder .25 / 40 s) at the realistic entry
        lad.append(run(r, 1.03, [(0.30, 0.0)], 40000, None, 0.95, 0.0) - (0.010 + 0.0003 * 3) / SIZE)
    print(f"   {name:6} REALISTIC his-rule (bundle x1.03) {show(real)}")
    print(f"   {name:6} REALISTIC derisk+trail  x1.03    {show(lad)}")
    st_ = [L["stats"][m] for m in fired if m in L["stats"]]
    if st_:
        print(f"   {name:6} curve reads ok {sum(x[0] for x in st_)} fail {sum(x[1] for x in st_)} | tracker wait>0: {sum(1 for x in st_ if x[2] > 0)}")

# ---- 7. AFTER split: launches BEFORE could also fire (sized dev >= 0.5) vs the newly admitted cap-family launches
print("\n== 7. AFTER split by dev-buy family ==")
sized_m = {d["mint"] for d in A["detect"] if d.get("first") == "1" and int(d.get("dev_sized", "0")) >= 5e8}
fA = {m for m, v in A["fired"].items() if inw(v[0])}
DA = {r["mint"]: r for r in load_set(A, PA)}
for lab, sub in (("sized (old rule also fires)", fA & sized_m), ("cap-family only (new)", fA - sized_m)):
    fl = [A["done"][m]["f100"] for m in sub if m in A["done"]]
    D = [DA[m] for m in sub if m in DA]
    real = [run(r, 1.03, (HIS_B if bundled(r) else HIS_N)["legs"], (HIS_B if bundled(r) else HIS_N)["T"], (HIS_B if bundled(r) else HIS_N)["sl"], None, 0.0) - (0.010 + 0.0006) for r in D]
    lab_ = [labels(CR[m]["b"], CR[m]["s"]) for m in sub if m in CR]
    con = sum(1 for x in lab_ if x["out01_n"] >= 1) / max(len(lab_), 1)
    print(f"   {lab:30} fired {len(sub):4} | floor {show(fl)}")
    print(f"   {'':30}            | realistic {show(real)} | contested S/S+1 {con:.0%} | 4yFAz {len(sub & set(hb_new))}")
