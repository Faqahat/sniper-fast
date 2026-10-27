#!/usr/bin/env python3
# NORMAL-MODE test (the code paths that run after the cut-over) on a local fake RPC that serves real recorded blocks
# and canned answers for the enrichment / final-pass methods. Two block endpoints (round-robin + failover: one of them
# always answers 429 like the dead RMR key), RPC enrichment ON (creator history, funder, earlier creates), midnight
# rotation, then the per-day final pass (curve account + top holders). Checks: no trip in normal mode, every launch has
# an enrich row with the RPC fields, the finished day has phase DONE / final_pass done and one final.jsonl row per launch.
# Usage: test_normal.py <raw dir> [N]
import os, sys, json, gzip, glob, time, subprocess, threading, http.server, socketserver, shutil, calendar, signal
HERE = os.path.dirname(os.path.abspath(__file__)); REC = os.path.dirname(HERE)
RAWDIR = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 120
WORK = os.environ.get("TEST_WORK", "/home/moiz/sniper-data/rec/test/normal" + ("_fallback" if os.environ.get("TEST_FALLBACK") == "1" else "")); shutil.rmtree(WORK, ignore_errors=True); os.makedirs(WORK)
S0 = 600_000_000; LAG = 3; PKT = 5 * 3600; FAILS = []
FALLBACK = os.environ.get("TEST_FALLBACK") == "1"      # primaries = the dead endpoint only, the good one only as REC_*_FALLBACK
def check(c, w):
    print(("PASS " if c else "FAIL ") + w, flush=True)
    if not c: FAILS.append(w)
blocks = []
for p in sorted(glob.glob(os.path.join(RAWDIR, "raw_*.jsonl.gz"))):
    try:
        for l in gzip.open(p, "rt"):
            if len(blocks) >= N: break
            blocks.append(json.loads(l)["block"])
    except (EOFError, OSError): pass
    if len(blocks) >= N: break
N = len(blocks)
M = calendar.timegm(time.strptime(time.strftime("%Y-%m-%d", time.gmtime(time.time() + PKT)), "%Y-%m-%d")) - PKT
kmid = N // 2; shift = M - blocks[kmid]["blockTime"]
for b in blocks: b["blockTime"] += shift
DAY1 = time.strftime("%Y-%m-%d", time.gmtime(M - 1 + PKT))
BODY = [json.dumps({"jsonrpc": "2.0", "id": 1, "result": b}).encode() for b in blocks]
calls = {}; T0 = [None]
def tip():
    if T0[0] is None: return S0 + LAG
    return S0 + LAG + min(N - 1, int((time.time() - T0[0]) * 25))
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        q = json.loads(self.rfile.read(int(self.headers["content-length"]))); m = q["method"]; calls[(self.server.name, m)] = calls.get((self.server.name, m), 0) + 1
        if self.server.name == "dead":                                                   # like RMR today
            self.send_response(429); self.send_header("content-length", "17"); self.end_headers(); self.wfile.write(b"max usage reached"); return
        r = None
        if m == "getSlot": r = tip()
        elif m == "getBlock":
            if T0[0] is None: T0[0] = time.time()
            k = q["params"][0] - S0
            if 0 <= k < N: body = BODY[k]; self.send_response(200); self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            r = None
        elif m == "getSignaturesForAddress": r = [{"signature": "sigA", "slot": 1, "blockTime": 1, "err": None}, {"signature": "sigB", "slot": 0, "blockTime": 0, "err": None}]
        elif m == "getTransaction": r = {"slot": 0, "transaction": {"message": {"accountKeys": ["Funder1111", "Creator111"]}}, "meta": {"preBalances": [10, 0], "postBalances": [5, 5], "logMessages": []}}
        elif m == "getMultipleAccounts": r = {"value": [{"data": ["AA==", "base64"], "lamports": 1} for _ in q["params"][0]]}
        elif m == "getTokenLargestAccounts": r = {"value": [{"address": "x", "amount": "1"}]}
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": r}).encode()
        self.send_response(200); self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)
class TS(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    def handle_error(self, *a): pass
srvs = {}
for name in ("good", "dead"):
    s = TS(("127.0.0.1", 0), H); s.name = name; threading.Thread(target=s.serve_forever, daemon=True).start(); srvs[name] = s
root = os.path.join(WORK, "root")
e = {k: v for k, v in os.environ.items() if not k.startswith(("REC_", "SHYFT", "RMR", "CONSTANTK", "TELEGRAM", "FTP_"))}
e.update(REC_MODE="normal", REC_ROOT=root, GOOD_URL=f"http://127.0.0.1:{srvs['good'].server_address[1]}/", DEAD_URL=f"http://127.0.0.1:{srvs['dead'].server_address[1]}/",
         REC_BLOCK_EPS="GOOD_URL,DEAD_URL" if not FALLBACK else "DEAD_URL", REC_RPC_EP="GOOD_URL" if not FALLBACK else "DEAD_URL",
         REC_BLOCK_FALLBACK="" if not FALLBACK else "GOOD_URL", REC_RPC_FALLBACK="" if not FALLBACK else "GOOD_URL", REC_BLOCK_RPS="300", REC_RPC_RPS="300", REC_LAG=str(LAG), REC_TEST_NO_NET="1",
         REC_FINALIZE_DELAY_S="1", REC_RESUME_MAX_H="1000", REC_SYNC_S="0.5", REC_FETCH_THREADS="6")
p = subprocess.Popen([sys.executable, "-I", os.path.join(REC, "recorder.py")], env=e, stdout=open(os.path.join(WORK, "out.txt"), "w"), stderr=subprocess.STDOUT)
def jl(x):
    try: return json.load(open(x))
    except Exception: return {}
t0 = time.time()
while time.time() - t0 < 400:
    stt = jl(os.path.join(root, "state", "recorder.json"))
    if jl(os.path.join(root, "days", DAY1, "status.json")).get("phase") == "DONE" and (stt.get("last_slot") or 0) >= S0 + N - 1 \
       and stt.get("enrich_queue") == 0 and not stt.get("pending_by_day") and time.time() - stt.get("now", 0) < 31: break
    if p.poll() is not None: break
    time.sleep(0.5)
time.sleep(1); p.send_signal(signal.SIGTERM); rc = p.wait(60)
st = jl(os.path.join(root, "days", DAY1, "status.json")); run = jl(os.path.join(root, "days", DAY1, "run.json"))
check(rc == 0 and not os.path.exists(os.path.join(root, "HOLD")), f"normal mode: the 429-only endpoint did not stop the recorder (rc {rc}, no HOLD)")
check(calls.get(("dead", "getBlock"), 0) > 0 and calls.get(("good", "getBlock"), 0) >= N, f"round-robin + failover over 2 block endpoints (dead {calls.get(('dead', 'getBlock'))}, good {calls.get(('good', 'getBlock'))})")
L = [json.loads(l) for d in glob.glob(os.path.join(root, "days", "*")) if os.path.exists(os.path.join(d, "launches.jsonl")) for l in open(os.path.join(d, "launches.jsonl"))]
EN = {json.loads(l)["mint"]: json.loads(l) for d in glob.glob(os.path.join(root, "days", "*")) if os.path.exists(os.path.join(d, "enrich.jsonl")) for l in open(os.path.join(d, "enrich.jsonl"))}
check(L and all(c["mint"] in EN for c in L), f"every launch has an enrich row ({len(EN)}/{len(L)})")
check(all(EN[c["mint"]].get("creator_prior_n") == 2 and EN[c["mint"]].get("funder", {}).get("from_") == "Funder1111" for c in L if c["mint"] in EN), "enrich rows carry the RPC fields (creator history, funder) like FRA")
L1 = [json.loads(l) for l in open(os.path.join(root, "days", DAY1, "launches.jsonl"))] if os.path.exists(os.path.join(root, "days", DAY1, "launches.jsonl")) else []
F1 = [json.loads(l) for l in open(os.path.join(root, "days", DAY1, "final.jsonl"))] if os.path.exists(os.path.join(root, "days", DAY1, "final.jsonl")) else []
check(st.get("phase") == "DONE" and st.get("final_pass") == "done" and run.get("final_pass") == "done", f"day {DAY1} finalized with the final pass (phase {st.get('phase')}, final_pass {st.get('final_pass')})")
check(sorted(f["mint"] for f in F1) == sorted(c["mint"] for c in L1 if c.get("bonding_curve")) and all(f.get("curve") and f.get("top_holders") for f in F1), f"final.jsonl: one row per launch of the day with curve + top holders ({len(F1)}/{len(L1)})")
check(calls.get(("good", "getTokenLargestAccounts"), 0) >= len(L1), "final pass used the RPC endpoint (getMultipleAccounts + getTokenLargestAccounts)")
for s in srvs.values(): s.shutdown()
print("\nRESULT:", "ALL PASSED" if not FAILS else f"{len(FAILS)} FAILED"); sys.exit(1 if FAILS else 0)
