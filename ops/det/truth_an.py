#!/usr/bin/env python3
# READ-ONLY summary of truth.py output: coverage risks (CPI, ALT), kinds, token program, quote mints, reserves, flags
# (engine parse vs CreateEvent), dev read (BEFORE / AFTER vs true), and how many filter-eligible launches each read keeps.
import sys, json, collections as C
sys.path.insert(0, "/root/det")
from dlib import WSOL, T22, SPL, W4

R = [json.loads(l) for l in open(sys.argv[1])]
ok = [r for r in R if not r.get("err") and not r.get("miss") and not r.get("exc") and not r.get("nocreate")]
print(f"records {len(R)} | ok creates {len(ok)} | failed creates {sum(1 for r in R if r.get('err'))} | missing {sum(1 for r in R if r.get('miss') or r.get('exc'))} | no create ix {sum(1 for r in R if r.get('nocreate'))}")
cnt = lambda f: C.Counter(f(r) for r in ok).most_common(12)
print("kind               ", cnt(lambda r: r["kind"]))
print("create top-level   ", cnt(lambda r: r["top"]))
print("  CPI outer progs  ", C.Counter(r["outer"] for r in ok if not r["top"]).most_common(8))
print("pump in static keys", cnt(lambda r: r["pump_static"]))
print("tx uses ALT        ", cnt(lambda r: r["nalt"] > 0))
print("mint/bc/abc via ALT", cnt(lambda r: r["acct_alt"]))
ev = [r for r in ok if r.get("ev")]
print("CreateEvent parsed ", len(ev))
print("token_program      ", C.Counter({T22: "T22", SPL: "SPL"}.get(r["ev"].get("token_program"), r["ev"].get("token_program")) for r in ev).most_common(5))
print("quote_mint         ", C.Counter("WSOL" if r["ev"].get("quote_mint") == WSOL else (r["ev"].get("quote_mint") or "none")[:12] for r in ev).most_common(8))
print("vsol0 / vquote0    ", C.Counter((r["ev"].get("vsol"), r["ev"].get("vquote")) for r in ev).most_common(6))
print("vtok0              ", C.Counter(r["ev"].get("vtok") for r in ev).most_common(4))
print("depth              ", C.Counter(r["ev"].get("depth") for r in ev).most_common(6))
# flags: engine parse (args) vs event
mm = C.Counter()
for r in ev:
    a, e = r["args"], r["ev"]
    if r["kind"] != "create_v2":
        continue
    for k, ek in (("mayhem", "mayhem"), ("cashback", "cashback"), ("fee_bps", "fee_bps"), ("holder", "holder")):
        if ek in e:
            mm[(k, "match" if a.get(k) == e[ek] else f"MISMATCH")] += 1
    if a.get("creator") != e.get("creator"):
        mm[("creator", "MISMATCH")] += 1
print("flag parse vs event", sorted(mm.items()))
print("trailing arg bytes ", cnt(lambda r: r["args"].get("trailing")))
print("flags (event)      ", "mayhem", sum(r["ev"].get("mayhem", False) for r in ev), "cashback", sum(r["ev"].get("cashback", False) for r in ev),
      "fee>0", sum((r["ev"].get("fee_bps") or 0) > 0 for r in ev), "holder", sum(r["ev"].get("holder", False) for r in ev))
# dev read
def err(a, b):
    return abs(a - b) / max(b, 1)
band = lambda x: 0.5e9 <= x <= 8e9
nonbl = [r for r in ok if not r["bl"]]
true_el = [r for r in nonbl if band(r["true_dev"])]
print(f"\nnon-blacklisted creates {len(nonbl)} | TRUE dev in 0.5-8 SOL: {len(true_el)}")
for name, k in (("BEFORE (sized only)", "dev_before"), ("AFTER (sized+cap)", "dev_after")):
    keep = [r for r in nonbl if band(r[k])]
    tp = [r for r in keep if band(r["true_dev"])]
    fn = [r for r in true_el if not band(r[k])]
    e5 = sum(1 for r in true_el if err(r[k], r["true_dev"]) <= 0.05)
    print(f"  {name:20} keeps {len(keep):4} | of true-eligible kept {len(tp):4} ({len(tp)/max(len(true_el),1):.0%}) | false-keep {len(keep)-len(tp)} | "
          f"missed {len(fn)} | read within 5% of truth {e5}/{len(true_el)}")
fnA = [r for r in true_el if not band(r["dev_after"])]
print("  AFTER misses by reason:", C.Counter(("inner_buy" if r.get("inner_buy") else "no_top_buy_for_mint" if not any(k[2] for k in r["dev_kinds"]) else "read_off") for r in fnA))
for r in fnA[:6]:
    print("    ", r["mint"][:10], "true", r["true_dev"], "after", r["dev_after"], "kinds", r["dev_kinds"][:3], "top", r["top"])
print("dev kinds (first)  ", C.Counter((r["dev_kinds"][0][0] + (" UNL" if r["dev_kinds"][0][4] > 10**15 else "")) if r["dev_kinds"] else "none" for r in ok).most_common(12))
his = [r for r in ok if W4 in (r.get("dev_users") or [])]
print("4yFAz in create tx ", len(his))
