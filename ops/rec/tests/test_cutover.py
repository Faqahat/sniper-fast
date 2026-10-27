#!/usr/bin/env python3
# CUT-OVER test on a local fake RPC serving real recorded blocks: the host recorder starts at a given slot
# (REC_START_SLOT, i.e. where FRA's collector stopped) with FRA's mints seeded (REC_SEED_LAUNCHES), stops cleanly at
# REC_STOP_SLOT (rollback / backfill), then resumes after the HOLD is removed and goes on; seeded mints survive the
# restart. Reference = FRA's collect.py over ALL blocks from the first one (so its TRACK holds the earlier mints too),
# keeping only records from the start slot on. Usage: test_cutover.py <raw dir> [N]
import os, sys, json, gzip, glob, time, subprocess, threading, http.server, socketserver, shutil, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__)); REC = os.path.dirname(HERE)
RAWDIR = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 150
WORK = os.environ.get("TEST_WORK", "/home/moiz/sniper-data/rec/test/cutover"); shutil.rmtree(WORK, ignore_errors=True); os.makedirs(WORK)
S0 = 500_000_000; LAG = 3; START = S0 + 80; STOP1 = S0 + 115; FAILS = []
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
N = len(blocks); BODY = [json.dumps({"jsonrpc": "2.0", "id": 1, "result": b}).encode() for b in blocks]
# reference + the "FRA launches" used for seeding: FRA's code over every block 0..N-1
os.environ.update(CONSTANTK_TOKEN="dummy", OUT=os.path.join(WORK, "fra"), TIPMAP=os.path.join(REC, "tipmap.json"))
spec = importlib.util.spec_from_file_location("C", os.path.join(REC, "..", "collect", "collect.py")); C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
for k in range(N): C.process_block(S0 + k, blocks[k], True)
C._chunk["f"].close()
exp = [json.loads(l) for c in sorted(glob.glob(os.path.join(WORK, "fra", "txs", "*.gz"))) for l in gzip.open(c, "rt")]
seed = os.path.join(WORK, "fra", "launches.jsonl")
seeded = [json.loads(l) for l in open(seed) if json.loads(l)["slot"] < START]
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        q = json.loads(self.rfile.read(int(self.headers["content-length"])))
        if q["method"] == "getSlot": body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": S0 + N - 1 + LAG}).encode()
        else:
            k = q["params"][0] - S0; body = BODY[k] if 0 <= k < N else b'{"jsonrpc":"2.0","id":1,"error":{"code":-32004,"message":"na"}}'
        self.send_response(200); self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)
class TS(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    def handle_error(self, *a): pass
srv = TS(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
root = os.path.join(WORK, "root")
def run(extra):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("REC_", "SHYFT", "RMR", "CONSTANTK", "TELEGRAM", "FTP_"))}
    e.update(REC_MODE="normal", REC_ROOT=root, FAKE_RPC_URL=f"http://127.0.0.1:{srv.server_address[1]}/", REC_BLOCK_EPS="FAKE_RPC_URL", REC_RPC_EP="FAKE_RPC_URL",
             REC_BLOCK_RPS="400", REC_RPC_RPS="400", REC_LAG=str(LAG), REC_ENRICH="off", REC_FINALIZE_DELAY_S="1", REC_RESUME_MAX_H="1000", REC_SYNC_S="0.5", **extra)
    return subprocess.run([sys.executable, "-I", os.path.join(REC, "recorder.py")], env=e, timeout=300, capture_output=True, text=True).returncode
rc = run(dict(REC_START_SLOT=str(START), REC_SEED_LAUNCHES=seed, REC_STOP_SLOT=str(STOP1)))
hold = json.load(open(os.path.join(root, "HOLD")))
lines = [l.split("\t") for d in sorted(glob.glob(os.path.join(root, "days", "*"))) for l in open(os.path.join(d, "slots.tsv"))]
check(rc == 0 and "REC_STOP_SLOT" in hold["reason"] and hold["by"] == "maintenance", f"stopped cleanly at REC_STOP_SLOT with a maintenance HOLD (rc {rc})")
check([int(x[0]) for x in lines] == list(range(START, STOP1 + 1)), f"recorded exactly slots {START - S0}..{STOP1 - S0} (REC_START_SLOT .. REC_STOP_SLOT)")
os.remove(os.path.join(root, "HOLD"))
rc = run(dict(REC_START_SLOT=str(START), REC_SEED_LAUNCHES=seed, REC_STOP_SLOT=str(S0 + N - 1)))      # resume: START/SEED ignored now
lines = [l.split("\t") for d in sorted(glob.glob(os.path.join(root, "days", "*"))) for l in open(os.path.join(d, "slots.tsv"))]
check([int(x[0]) for x in lines] == list(range(START, S0 + N)), f"resumed after the HOLD was removed: slots {START - S0}..{N - 1}, contiguous, no repeat")
log = open(os.path.join(root, "logs", "recorder.log")).read()
check(log.count("seeded ") == 1 and "RESUME" in log, f"seeded once ({len(seeded)} FRA mints), resumed once (seed + start slot not re-applied)")
got = sorted(json.dumps(dict(r, mints=sorted(r["mints"])), sort_keys=True) for c in sorted(glob.glob(os.path.join(root, "days", "*", "txs", "*.gz"))) for r in (json.loads(l) for l in gzip.open(c, "rt")))
want = sorted(json.dumps(dict(r, mints=sorted(r["mints"])), sort_keys=True) for r in exp if r["s"] >= START)
check(got == want, f"records from the start slot on == FRA's collect.py (with the seeded mints followed across the restart): {len(got)} vs {len(want)}")
own = [json.loads(l) for d in glob.glob(os.path.join(root, "days", "*")) if os.path.exists(os.path.join(d, "launches.jsonl")) for l in open(os.path.join(d, "launches.jsonl"))]
check(all(c["slot"] >= START for c in own), f"the host's launches.jsonl holds only its own creates ({len(own)}); seeded mints are in state/seed_launches.jsonl")
srv.shutdown(); print("\nRESULT:", "ALL PASSED" if not FAILS else f"{len(FAILS)} FAILED"); sys.exit(1 if FAILS else 0)
