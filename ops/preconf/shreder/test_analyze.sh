#!/usr/bin/env bash
# End-to-end test of analyze.py on synthetic data with KNOWN injected values (built by make_synth.py from a real chain-recording
# window + a real engine log). Prints PASS/FAIL per check and the runtimes. Then runs a second variant: fra/ only, no engine,
# no dataset files, streams named fpre/fbin (view-only fallback + --streams flag).
# usage: test_analyze.sh [OUT_DIR]   env: MINUTES (default 20), ENGINE (engine log), FROM (HH:MM PKT, default 20:45), DATE
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-/home/moiz/sniper-data/preconf/synth_test}
MIN=${MINUTES:-20}; FROM=${FROM:-20:45}; DATE=${DATE:-2026-10-27}
ENGINE=${ENGINE:-/home/moiz/sniper-data/presend_filter/live28/dip_ams_r28.jsonl}
ts() { date +%s.%N; }
T0=$(ts)
mkdir -p "$OUT"
python3 "$HERE/make_synth.py" --out "$OUT" --minutes "$MIN" --from "$FROM" --date "$DATE" --engine "$ENGINE" 2> "$OUT/synth.log" \
  || { echo "FAIL make_synth (see $OUT/synth.log)"; exit 1; }
T1=$(ts)
python3 "$HERE/analyze.py" --run-dir "$OUT" > "$OUT/analyze_stdout.txt" 2> "$OUT/analyze_stderr.txt"; RC=$?
T2=$(ts)
cat "$OUT/analyze_stdout.txt"
python3 - "$OUT" "$RC" <<'EOF'
import json, sys, os
out, rc = sys.argv[1], int(sys.argv[2])
T = json.load(open(os.path.join(out, "truth.json")))
fails = 0
def chk(name, ok, detail):
    global fails
    print(("PASS " if ok else "FAIL ") + name + ": " + detail)
    fails += 0 if ok else 1
chk("analyze exit code", rc == 0, f"rc={rc}")
if rc != 0: sys.exit(1)
R = json.load(open(os.path.join(out, "analysis", "summary.json")))
c = R["coverage"]["fra"]["pre"]; cb = R["coverage"]["fra"]["bin"]
chk("coverage inside covered slots (dataset incl. ALT-CPI txs)", abs(c["tx_share_within_covered_slots"] - T["keep_in_covered_slot"]) <= 0.01,
    f"got {c['tx_share_within_covered_slots']:.4f} want {T['keep_in_covered_slot']} ±0.01 (view-only would give ~{T['keep_in_covered_slot'] * T['view_share']:.3f})")
chk("slot share (connected leaders' slots)", abs(c["slot_share"] - T["slot_share_connected"]) <= 0.03,
    f"got {c['slot_share']:.4f} want {T['slot_share_connected']:.4f} ±0.03")
fr_got = c["leaders_connected"] / c["leaders_seen"]; fr_want = T["connected_windows"] / T["windows"]
chk("connected-leader fraction", abs(fr_got - fr_want) <= 0.04, f"got {c['leaders_connected']}/{c['leaders_seen']}={fr_got:.3f} want {fr_want:.3f} ±0.04")
chk("bin coverage", cb["tx_share"] is not None and cb["tx_share"] >= 0.995, f"got {cb['tx_share']}")
L = R["lead"]["fra"]["pre_vs_bin_chain_pump"]["all"]
chk("lead P50 pre vs bin", abs(L["p50"] - T["lead_p50_ms"]) <= 0.3, f"got {L['p50']:.3f} want {T['lead_p50_ms']:.3f} ±0.3 ms (n={L['n']} vs {T['n_lead']})")
chk("lead P10/P90", abs(L["p10"] - T["lead_p10_ms"]) <= 0.4 and abs(L["p90"] - T["lead_p90_ms"]) <= 1.0,
    f"got {L['p10']:.2f}/{L['p90']:.2f} want {T['lead_p10_ms']:.2f}/{T['lead_p90_ms']:.2f}")
A = R["accuracy"]["fra"]
chk("never-landed share", abs(A["never_landed_share"] - T["never_landed_share_expected"]) <= 0.003,
    f"got {A['never_landed_share']:.4f} want {T['never_landed_share_expected']:.4f} ±0.003 ({A['never_landed']} judged absent vs {T['fakes']} fakes)")
chk("same-slot share", abs(A["same_slot_share"] - (1 - T["slot_mismatch"])) <= 0.005, f"got {A['same_slot_share']:.4f} want {1 - T['slot_mismatch']:.3f}")
chk("in-slot order agreement", abs(A["order"]["pair_agreement"] - T["order_pair_agreement"]) <= 0.01,
    f"got {A['order']['pair_agreement']:.4f} want {T['order_pair_agreement']:.4f} ±0.01")
Q = R["quality"]["fra"]
chk("reconnect gap excluded", abs(Q["pre"]["connected_min"] - T["connected_min_pre"]) <= 0.05 and len(Q["pre"]["connected_windows"]) == 2,
    f"pre connected {Q['pre']['connected_min']} min in {len(Q['pre']['connected_windows'])} windows; want {T['connected_min_pre']} in 2")
chk("duplicates counted", Q["pre"]["view_stats"].get("dups", 0) == T["pre_view_dups"], f"got {Q['pre']['view_stats'].get('dups', 0)} want {T['pre_view_dups']}")
chk("truncated last view line tolerated", Q["pre"]["view_stats"].get("bad_json", 0) >= 1, f"bad_json={Q['pre']['view_stats'].get('bad_json', 0)}")
chk("truncated gzip member tolerated", Q["pre"]["dataset_stats"].get("truncated_member", 0) >= 1, f"dataset_stats={Q['pre']['dataset_stats']}")
E = R["lead"].get("pre_vs_engine", {}).get("all", {})
chk("pre vs AMS engine lead P50 (offset-corrected)", E.get("n", 0) >= 20 and abs(E["p50"] - T["engine_lead_p50_ms"]) <= 0.5,
    f"got {E.get('p50')} n={E.get('n')} want {T['engine_lead_p50_ms']:.3f} ±0.5 (n={T['n_engine_lead']}); clock unc ±{(R.get('clock_unc_ms') or 0):.2f} ms")
W = R.get("whatif") or {}
chk("what-if ran", bool(W) and W["A_arms"]["n"] + W["A_fires"]["n"] > 0,
    f"fires {W.get('A_fires', {}).get('n')} (pre copy {W.get('A_fires', {}).get('with_pre')}), arms {W.get('A_arms', {}).get('n')} "
    f"(pre copy {W.get('A_arms', {}).get('with_pre')}), B1/B2/B3 applies {W.get('B1', {}).get('applies')}/{W.get('B2', {}).get('applies')}/{W.get('B3', {}).get('applies')}")
print(f"RESULT main: {'ALL PASS' if not fails else str(fails) + ' FAIL'}")
sys.exit(1 if fails else 0)
EOF
R1=$?
# ---------------- variant: fra only, no engine, no dataset, streams fpre/fbin
V2=$OUT/variant_fraonly
rm -rf "$V2"; mkdir -p "$V2/fra"
for f in "$OUT"/fra/pre_????????_??.jsonl "$OUT"/fra/bin_????????_??.jsonl; do ln -s "$f" "$V2/fra/f$(basename "$f")"; done
sed -e 's/"st": "pre"/"st": "fpre"/; s/"st": "bin"/"st": "fbin"/' "$OUT/fra/events.jsonl" > "$V2/fra/events.jsonl"
T3=$(ts)
python3 "$HERE/analyze.py" --run-dir "$V2" --streams fpre,fbin > "$V2/stdout.txt" 2> "$V2/stderr.txt"; RC2=$?
T4=$(ts)
python3 - "$V2" "$RC2" <<'EOF'
import json, sys, os
d, rc = sys.argv[1], int(sys.argv[2]); fails = 0
def chk(n, ok, det):
    global fails
    print(("PASS " if ok else "FAIL ") + "variant fra-only/no-engine/view-only/fpre,fbin: " + n + ": " + det); fails += 0 if ok else 1
chk("exit code", rc == 0, f"rc={rc}")
if rc == 0:
    R = json.load(open(os.path.join(d, "analysis", "summary.json")))
    c = R["coverage"]["fra"]["pre"]
    chk("report + coverage present", os.path.exists(os.path.join(d, "analysis", "report.md")) and c.get("tx_share") is not None,
        f"view-only tx share inside covered slots {c.get('tx_share_within_covered_slots')} (expected ~0.97*0.92=0.89: the view misses ALT-CPI txs)")
    chk("engine parts skipped cleanly", "whatif" not in R and any("engine" in s for s in R["skipped"]), f"skipped={R['skipped']}")
    chk("gap still excluded (events st=fpre)", abs(R["quality"]["fra"]["pre"]["connected_min"] - json.load(open(os.path.join(os.path.dirname(d), "truth.json")))["connected_min_pre"]) <= 0.05,
        f"connected {R['quality']['fra']['pre']['connected_min']} min")
print(f"RESULT variant: {'ALL PASS' if not fails else str(fails) + ' FAIL'}")
sys.exit(1 if fails else 0)
EOF
R2=$?
python3 -c "import sys; t=[float(x) for x in sys.argv[1:]]; print(f'TIMING make_synth {t[1]-t[0]:.1f}s, analyze main {t[2]-t[1]:.1f}s, analyze variant {t[4]-t[3]:.1f}s, total {t[4]-t[0]:.1f}s')" $T0 $T1 $T2 $T3 $T4
[ $R1 -eq 0 ] && [ $R2 -eq 0 ] && echo "TEST: ALL PASS" || { echo "TEST: FAILURES"; exit 1; }
