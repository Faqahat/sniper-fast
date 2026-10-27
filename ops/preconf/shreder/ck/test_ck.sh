#!/bin/bash
# test_ck.sh — synthetic end-to-end test of ck_compare.py (real race log + real engine snapshot + real chain truth + fake
# Shreder recorder files with KNOWN injected leads). Prints PASS/FAIL per check and exits 1 on any FAIL.
#   bash test_ck.sh [RACE_LOG] [ENGINE_JSONL] [T0_UNIX T1_UNIX]
# Defaults: the inputs kept in /home/moiz/sniper-data/preconf/ck_test/inputs/ (FRA /root/gap/race/race_exec1.log, a
# read-only snapshot of AMS run 28), engine window 2026-10-27 16:15-16:30 UTC (9 fires: per-feed timing records).
set -u
H=$(cd "$(dirname "$0")" && pwd)
D=/home/moiz/sniper-data/preconf/ck_test
IN=$D/inputs
RACE=${1:-$IN/race_exec1.log}; ENG=${2:-$IN/dip_ams_r28.snap1.jsonl}; T0=${3:-1793117700}; T1=${4:-1793118600}
COL=${COLLECT_ROOT:-/home/moiz/sniper-data/collect}
for f in "$RACE" "$ENG"; do [ -s "$f" ] || { echo "FAIL: missing input $f"; exit 1; }; done
rm -rf "$D/A" "$D/B" "$D/expect.json"
python3 "$H/make_test_ck.py" "$D" "$RACE" "$ENG" "$T0" "$T1" || { echo "FAIL: make_test_ck.py"; exit 1; }
S=$(date +%s)
python3 "$H/../ck_compare.py" --run-dir "$D/A" --collect-root "$COL" || { echo "FAIL: ck_compare A crashed"; exit 1; }
python3 "$H/../ck_compare.py" --run-dir "$D/B" --collect-root "$COL" || { echo "FAIL: ck_compare B crashed"; exit 1; }
# --from/--to (PKT HH:MM): a window holding all of A's data, and one holding none of it
python3 "$H/../ck_compare.py" --run-dir "$D/A" --collect-root "$COL" --from 23:50 --to 23:55 --no-rec > /dev/null 2>&1 && cp "$D/A/analysis/ck_compare.json" "$D/A/analysis/win_all.json" || { echo "FAIL: ck_compare A --from/--to crashed"; exit 1; }
python3 "$H/../ck_compare.py" --run-dir "$D/A" --collect-root "$COL" --from 23:55 --to 23:59 --no-rec > /dev/null 2>&1 && cp "$D/A/analysis/ck_compare.json" "$D/A/analysis/win_none.json" || { echo "FAIL: ck_compare A empty window crashed"; exit 1; }
python3 "$H/../ck_compare.py" --run-dir "$D/A" --collect-root "$COL" > /dev/null 2>&1 || { echo "FAIL: ck_compare A rerun crashed"; exit 1; }
# a run dir with nothing in it must not crash either
mkdir -p "$D/EMPTY"; python3 "$H/../ck_compare.py" --run-dir "$D/EMPTY" --collect-root "$COL" > /dev/null 2>&1 && echo "PASS empty run dir handled" || { echo "FAIL: empty run dir crashed"; exit 1; }
echo "ck_compare runs took $(( $(date +%s) - S )) s"
python3 - "$D" "$COL" "$T0" "$T1" "$H/.." <<'EOF'
import json, sys
D, COL, T0, T1, HD = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
sys.path.insert(0, HD)
import ck_compare as C
E = json.load(open(f"{D}/expect.json"))
A = json.load(open(f"{D}/A/analysis/ck_compare.json"))
B = json.load(open(f"{D}/B/analysis/ck_compare.json"))
fails = 0
def chk(name, got, want, tol):
    global fails
    ok = got is not None and want is not None and abs(got - want) <= tol
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'} {name}: got {got} want {want} (tol {tol})")
def chk_true(name, cond, info=""):
    global fails
    fails += not cond
    print(f"{'PASS' if cond else 'FAIL'} {name} {info}")
ga = A["groups"][0]; pa = ga["pairwise_ck_minus_shreder_ms"]; ea = E["A"]
chk("A bin vs CK_BEST P50 ms", pa["shreder_bin vs CK_BEST"]["all"]["p50"], ea["bin_vs_ckbest_p50"], 0.002)
chk("A bin vs CK_BEST Shreder-earlier %", pa["shreder_bin vs CK_BEST"]["all"]["shreder_earlier_pct"], 100.0, 0.05)
chk("A pre vs CK_BEST P50 ms", pa["shreder_pre vs CK_BEST"]["all"]["p50"], ea["pre_vs_ckbest_p50"], 0.002)
chk("A bin vs kaldera P50 ms", pa["shreder_bin vs kaldera"]["all"]["p50"], ea["bin_vs_kaldera_p50"], 0.002)
chk("A union size", ga["n_any"], ea["n_union"], 0)
chk("A bin miss vs union %", ga["miss_vs_union"]["shreder_bin"]["miss_pct"], ea["bin_miss_union_pct"], 0.01)
chk("A pre miss in own slots %", ga["miss_vs_union"]["shreder_pre"]["in_preconf_slots"]["miss_pct"], ea["pre_miss_own_slots_pct"], 0.01)
chk("A dataset recovered txs", A["sources"]["shreder_rec"]["shreder_bin"]["added_to_view"], ea["rec_added"], 0)
fa = ga["first_any"]
chk_true("A first shares: preconf + bin take ~all firsts", (fa["shreder_bin"] or 0) + (fa["shreder_pre"] or 0) > 95, str(fa))
mk = ga.get("miss_vs_chain", {}).get("kaldera", {})
chk_true("A chain truth loaded + kaldera chain-miss < 10%", mk.get("n_chain", 0) > 1000 and (mk.get("miss_pct") or 100) < 10,
         f"(n_chain {mk.get('n_chain')}, kaldera miss {mk.get('miss_pct')}%, turbo {ga['miss_vs_chain'].get('turbo-kaldera', {}).get('miss_pct')}%, kaldera-tx {ga['miss_vs_chain'].get('kaldera-tx', {}).get('miss_pct')}%)")
chk_true("A classes typed from chain (unknown < 5%)", ga["classes"].get("unknown", 0) < 0.05 * ga["n_any"], str(ga["classes"]))
gb = B["groups"][1] if len(B["groups"]) > 1 else {}
pb = gb.get("pairwise_ck_minus_shreder_ms", {}); eb = E["B"]
chk_true("B engine host auto = ams, offset read", B["sources"]["engine_host"] == "ams" and B["sources"]["engine_clock_offset_ms_ams_minus_fra"] == eb["offset_ms"])
chk("B bin vs eng_first P50 ms (offset-corrected)", pb.get("shreder_bin vs eng_first", {}).get("all", {}).get("p50"), eb["eng_first_vs_bin_p50"], 0.002)
chk("B bin vs eng_exec P50 ms (offset-corrected)", pb.get("shreder_bin vs eng_exec", {}).get("all", {}).get("p50"), eb["eng_exec_vs_bin_p50"], 0.002)
for f, want in sorted(eb.get("eng_feed_vs_bin_p50", {}).items()):
    chk(f"B bin vs {f} P50 ms (per-feed timing, offset-corrected)", pb.get(f"shreder_bin vs {f}", {}).get("all", {}).get("p50"), want, 0.002)
chk_true("B per-feed engine arrivals present (kaldera, turbo-kaldera, kaldera-tx)", len(eb.get("eng_feed_vs_bin_p50", {})) >= 3, str(sorted(eb.get("eng_feed_vs_bin_p50", {}))))
WA = json.load(open(f"{D}/A/analysis/win_all.json")); WN = json.load(open(f"{D}/A/analysis/win_none.json"))
chk("A --from 23:50 --to 23:55 keeps every tx", WA["groups"][0].get("n_any"), ea["n_union"], 0)
chk_true("A --from 23:55 --to 23:59 (no data) handled", WN["groups"][0].get("skipped") is not None or not WN["groups"][0].get("n_any"), str(WN["groups"][0].get("skipped")))
md = open(f"{D}/A/analysis/ck_compare.md").read()
chk_true("A a started-but-silent race feed is reported (deadfeed in missing_feeds)", "deadfeed" in ga.get("missing_feeds", []), str(ga.get("missing_feeds")))
chk_true("A markdown has the headline + tables", "## Headline" in md and "shreder_bin vs CK_BEST" in md)
# chain classifier vs the engine's own decisions in [T0, T1] (whale = presend_arm at whale_pct 6; dump >= 0.3 SOL)
cls, pump, st, amm = C.load_chain(COL, T0 - 3600, T1 + 5, 6.0, 300_000_000, win_lo=T0)
arms, dumps = eb["engine_arms"], eb["engine_dumps"]
wa = sum(1 for k in arms if cls.get(k) == "whale"); da = sum(1 for k in dumps if cls.get(k) in ("dump", "whale"))
chk_true("B chain whale rule reproduces the engine's 6% triggers (>= 85%)", arms and wa >= 0.85 * len(arms), f"({wa}/{len(arms)})")
chk_true("B chain dump class covers the engine's >= 0.3 SOL dumps (>= 95%)", dumps and da >= 0.95 * len(dumps), f"({da}/{len(dumps)})")
print("RESULT:", "PASS" if not fails else f"FAIL ({fails} check(s))")
sys.exit(1 if fails else 0)
EOF
