#!/usr/bin/env python3
# REPLAY TEST of the host recorder against a local fake RPC that serves REAL recorded blocks (from the overlap test's raw
# dump), renumbered as consecutive slots, with block times shifted so that a PKT midnight falls in the middle.
# Injected: skipped slots (-32007), a permanently failing slot (HTTP 500), a transient error (HTTP 503 once), a block
# "not available yet" (-32004 twice), a block after midnight whose blockTime is BEFORE midnight (slot order must win),
# and two SIGKILL crashes (before and after the rotation). Reference output = FRA's own collect.py process_block run
# over the same blocks. Checks: rotation at the first block >= midnight, adjacent day slot ranges touch (no gap, no
# overlap), every slot exactly once in slots.tsv with the right status, records identical to FRA's code (no loss, no
# duplicate after the crashes), every chunk a complete gzip, both days finalized.
# Second scenario: HTTP 429 "max usage reached" -> recorder writes HOLD, exits 0, refuses to restart.
# Usage: test_replay.py <raw dir> [N blocks]      (exit 0 = all checks passed)
import os, sys, json, gzip, glob, time, signal, subprocess, threading, http.server, socketserver, shutil, importlib.util, calendar, zlib
HERE = os.path.dirname(os.path.abspath(__file__)); REC = os.path.dirname(HERE)
RAWDIR = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 240
WORK = os.environ.get("TEST_WORK", "/home/moiz/sniper-data/rec/test/replay")
PKT = 5 * 3600; S0 = 400_000_000; LAG = 3
FAILS = []
def check(cond, what):
    print(("PASS " if cond else "FAIL ") + what, flush=True)
    if not cond: FAILS.append(what)

# ---------- blocks ----------
blocks = []
for p in sorted(glob.glob(os.path.join(RAWDIR, "raw_*.jsonl.gz"))):
    try:
        with gzip.open(p, "rt") as f:
            for l in f:
                if len(blocks) >= N: break
                try: blocks.append(json.loads(l)["block"])
                except Exception: break
    except (EOFError, OSError): pass
    if len(blocks) >= N: break
N = len(blocks); assert N >= 60, f"need >= 60 raw blocks, have {N}"
now = time.time(); M = calendar.timegm(time.strptime(time.strftime("%Y-%m-%d", time.gmtime(now + PKT)), "%Y-%m-%d")) - PKT   # today 00:00 PKT
kmid = N // 2
while blocks[kmid]["blockTime"] <= blocks[kmid - 1]["blockTime"]: kmid += 1
shift = M - blocks[kmid]["blockTime"]
for b in blocks: b["blockTime"] += shift
K_SKIP = {10, kmid - 1}; K_FAIL = {20}; K_TRANS = {30}; K_NA = {40}; K_BACK = kmid + 3
blocks[K_BACK]["blockTime"] = M - 1                    # after midnight in slot order, but its blockTime is before midnight
DAY1 = time.strftime("%Y-%m-%d", time.gmtime(M - 1 + PKT)); DAY2 = time.strftime("%Y-%m-%d", time.gmtime(M + PKT))
print(f"{N} real blocks as slots {S0}..{S0 + N - 1}; midnight {DAY1}|{DAY2} at k={kmid} (slot {S0 + kmid}); skips {sorted(K_SKIP)} fail {sorted(K_FAIL)} transient {sorted(K_TRANS)} not-avail {sorted(K_NA)} bt-backwards {K_BACK}")
BODY = [json.dumps({"jsonrpc": "2.0", "id": 1, "result": b}).encode() for b in blocks]

# ---------- fake RPC ----------
class Fake:
    t0 = None; hits = {}; trip_at = None; rate = 25.0
    @classmethod
    def tip(cls):
        if cls.t0 is None: return S0 + LAG
        return S0 + LAG + min(N - 1, int((time.time() - cls.t0) * cls.rate))
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def reply(self, code, body):
        self.send_response(code); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["content-length"])))
        m = req["method"]
        if m == "getSlot": return self.reply(200, json.dumps({"jsonrpc": "2.0", "id": 1, "result": Fake.tip()}).encode())
        if m != "getBlock": return self.reply(200, b'{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"no"}}')
        if Fake.t0 is None: Fake.t0 = time.time()
        k = req["params"][0] - S0; Fake.hits[k] = Fake.hits.get(k, 0) + 1
        if not (0 <= k < N) or req["params"][0] > Fake.tip() - 0: return self.reply(200, b'{"jsonrpc":"2.0","id":1,"error":{"code":-32004,"message":"Block not available for slot"}}')
        if Fake.trip_at is not None and k >= Fake.trip_at: return self.reply(429, b"max usage reached")
        if k in K_SKIP: return self.reply(200, b'{"jsonrpc":"2.0","id":1,"error":{"code":-32007,"message":"Slot was skipped"}}')
        if k in K_FAIL: return self.reply(500, b"boom")
        if k in K_TRANS and Fake.hits[k] == 1: return self.reply(503, b"busy")
        if k in K_NA and Fake.hits[k] <= 2: return self.reply(200, b'{"jsonrpc":"2.0","id":1,"error":{"code":-32004,"message":"Block not available for slot"}}')
        self.reply(200, BODY[k])
class TS(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    def handle_error(self, request, client_address): pass          # connections cut by the SIGKILLs
srv = TS(("127.0.0.1", 0), H); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

def env_for(root):
    e = dict(os.environ)
    for k in list(e):
        if k.startswith(("REC_", "SHYFT", "RMR", "CONSTANTK", "TELEGRAM", "FTP_")): e.pop(k)
    e.update(REC_MODE="overlap", REC_ROOT=root, FAKE_RPC_URL=f"http://127.0.0.1:{port}/", REC_BLOCK_EPS="FAKE_RPC_URL", REC_RPC_EP="FAKE_RPC_URL",
             REC_EP_TOTAL_RPS="400", REC_BLOCK_RPS="400", REC_RPC_RPS="400", REC_LAG=str(LAG), REC_SLOT_EVERY="0.2", REC_CHUNK_S="2",
             REC_SYNC_S="0.5", REC_ENRICH="off", REC_RESUME_MAX_H="1000", REC_FINALIZE_DELAY_S="2", REC_FETCH_THREADS="6", REC_TRIP_ON_LIMIT="1", REC_LEGACY=os.path.join(root, "nolegacy"))
    return e
def start(root): return subprocess.Popen([sys.executable, "-I", os.path.join(REC, "recorder.py")], env=env_for(root), stdout=open(os.path.join(root, "stdout.txt"), "a"), stderr=subprocess.STDOUT)
def nlines(root):
    return sum(sum(1 for _ in open(p)) for p in glob.glob(os.path.join(root, "days", "*", "slots.tsv")))
def jl(p):
    try: return json.load(open(p))
    except Exception: return {}
def state(root):
    try: return json.load(open(os.path.join(root, "state", "recorder.json")))
    except Exception: return {}
def wait(cond, timeout, what, proc=None):
    t = time.time()
    while time.time() - t < timeout:
        if cond(): return True
        if proc is not None and proc.poll() is not None:
            print("recorder exited early, rc", proc.returncode, "while waiting for", what); return False
        time.sleep(0.1)
    print("timeout waiting for", what); return False

# ---------- scenario 1: rotation + gaps + 2 crashes ----------
root = os.path.join(WORK, "s1"); shutil.rmtree(root, ignore_errors=True); os.makedirs(root)
p = start(root)
wait(lambda: nlines(root) >= int(N * 0.3), 120, "30% of slots", p); p.send_signal(signal.SIGKILL); p.wait(); print("SIGKILL 1 at", nlines(root), "slot lines")
p = start(root)
wait(lambda: os.path.exists(os.path.join(root, "days", DAY2, "slots.tsv")) and os.path.getsize(os.path.join(root, "days", DAY2, "slots.tsv")) > 0 and sum(1 for _ in open(os.path.join(root, "days", DAY2, "slots.tsv"))) >= 8, 180, "8 lines in day 2", p)
p.send_signal(signal.SIGKILL); p.wait(); print("SIGKILL 2 at", nlines(root), "slot lines")
p = start(root)
ok = wait(lambda: (state(root).get("last_slot") or 0) >= S0 + N - 1 and (jl(os.path.join(root, "days", DAY1, "status.json")).get("phase") == "DONE"), 300, "end + day 1 DONE", p)
time.sleep(1.5); p.send_signal(signal.SIGTERM); rc = p.wait(timeout=60)
check(ok and rc == 0, f"recorder reached the last slot, finalized day 1, stopped cleanly (rc {rc})")

r1 = json.load(open(os.path.join(root, "days", DAY1, "run.json"))); r2 = json.load(open(os.path.join(root, "days", DAY2, "run.json")))
check(r1["start_slot"] == S0, f"day 1 starts at the first slot ({r1['start_slot']})")
first_after = min(k for k in range(N) if k not in K_SKIP | K_FAIL and blocks[k]["blockTime"] >= M)
check(r1["end_slot"] == S0 + first_after - 1 and r2["start_slot"] == S0 + first_after, f"rotation at the first block >= midnight: day1 end {r1['end_slot'] - S0}, day2 start {r2['start_slot'] - S0}, expected {first_after}")
check(r1["end_slot"] + 1 == r2["start_slot"], "adjacent day slot ranges touch (end + 1 == next start)")
lines = {}
for d in (DAY1, DAY2):
    for l in open(os.path.join(root, "days", d, "slots.tsv")):
        x = l.rstrip("\n").split("\t"); lines.setdefault(int(x[0]), []).append((d, x[1]))
check(sorted(lines) == list(range(S0, S0 + N)), f"every slot {S0}..{S0 + N - 1} is in slots.tsv (have {len(lines)})")
check(all(len(v) == 1 for v in lines.values()), "no slot twice in slots.tsv (after 2 crashes)")
check(all(v[0][0] == (DAY1 if s <= r1["end_slot"] else DAY2) for s, v in lines.items()), "each slot is in the day its range says")
want = {S0 + k: ("skip" if k in K_SKIP else "fail" if k in K_FAIL else "ok") for k in range(N)}
check(all(lines[s][0][1] == want[s] for s in want), f"statuses: skips {[k for k in range(N) if lines[S0 + k][0][1] == 'skip']} fails {[k for k in range(N) if lines[S0 + k][0][1] == 'fail']}")
check(lines[S0 + K_BACK][0][0] == DAY2, "block after midnight with an earlier blockTime stays in day 2 (slot order wins)")
gaps = [json.loads(l) for d in (DAY1, DAY2) if os.path.exists(os.path.join(root, "days", d, "gaps.jsonl")) for l in open(os.path.join(root, "days", d, "gaps.jsonl"))]
check(sorted((g["slot"] - S0, g["why"].split()[0]) for g in gaps) == sorted([(k, "skip") for k in K_SKIP] + [(k, "fetch") for k in K_FAIL]), f"gaps.jsonl = exactly the injected skips + failure ({[(g['slot'] - S0, g['why']) for g in gaps]})")

# records vs FRA's collect.py
recs = []; badgz = []
for d in (DAY1, DAY2):
    for c in sorted(glob.glob(os.path.join(root, "days", d, "txs", "*.jsonl.gz"))):
        try:
            with gzip.open(c, "rt") as f: rows = [json.loads(l) for l in f]
        except (EOFError, OSError, zlib.error): badgz.append(c); continue
        for r in rows: recs.append((d, r))
check(not badgz, f"every chunk is a complete gzip ({len(badgz)} bad)")
check(all((r["s"] <= r1["end_slot"]) if d == DAY1 else (r["s"] >= r2["start_slot"]) for d, r in recs), "every record lies inside its day's slot range")
os.environ.update(CONSTANTK_TOKEN="dummy", OUT=os.path.join(WORK, "fra_expected"), TIPMAP=os.path.join(REC, "tipmap.json"))
shutil.rmtree(os.environ["OUT"], ignore_errors=True)
spec = importlib.util.spec_from_file_location("fra_collect", os.path.join(REC, "..", "collect", "collect.py")); C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
for k in range(N):
    if k in K_SKIP | K_FAIL: continue
    C.process_block(S0 + k, blocks[k], True)
C._chunk["f"].close()
exp = []
for c in sorted(glob.glob(os.path.join(os.environ["OUT"], "txs", "*.jsonl.gz"))):
    exp += [json.loads(l) for l in gzip.open(c, "rt")]
norm = lambda r: json.dumps(dict(r, mints=sorted(r["mints"])), sort_keys=True)
got = sorted(norm(r) for _, r in recs); expd = sorted(norm(r) for r in exp)
check(len(got) == len(set(got)), f"no duplicate records ({len(got) - len(set(got))} dups)")
check(got == expd, f"records identical to FRA's collect.py over the same blocks: {len(got)} vs {len(expd)}")
L = [json.loads(l) for d in (DAY1, DAY2) for l in open(os.path.join(root, "days", d, "launches.jsonl"))]
LE = [json.loads(l) for l in open(os.path.join(os.environ["OUT"], "launches.jsonl"))]
check(sorted(c["mint"] for c in L) == sorted(c["mint"] for c in LE) and len(L) == len(set(c["mint"] for c in L)), f"launches identical, no duplicates ({len(L)} vs {len(LE)})")
for d in (DAY1,):
    s = json.load(open(os.path.join(root, "days", d, "status.json")))
    check(s.get("phase") == "DONE", f"day {d} finalized (phase {s.get('phase')}, final pass {s.get('final_pass')})")
log = open(os.path.join(root, "logs", "recorder.log")).read()
check(log.count("RESUME") == 2, "resumed twice after the 2 SIGKILLs")
print("recorder log:\n" + "\n".join("   " + l for l in log.splitlines() if any(x in l for x in ("RESUME", "ROTATE", "repaired", "orphan", "dropped", "FRESH", "finalized", "stopp"))))

# ---------- scenario 2: 429 'max usage reached' -> HOLD, clean exit, no restart ----------
root2 = os.path.join(WORK, "s2"); shutil.rmtree(root2, ignore_errors=True); os.makedirs(root2)
Fake.t0 = None; Fake.hits = {}; Fake.trip_at = 15
p = start(root2); rc = p.wait(timeout=120)
hold = json.load(open(os.path.join(root2, "HOLD"))) if os.path.exists(os.path.join(root2, "HOLD")) else {}
check(rc == 0 and "TRIP" in hold.get("reason", ""), f"429 -> HOLD written ({hold.get('reason')}) and clean exit (rc {rc})")
last = max(int(l.split("\t")[0]) for l in open(glob.glob(os.path.join(root2, "days", "*", "slots.tsv"))[0]))
check(last < S0 + 15, f"nothing recorded at or after the 429 slot (last {last - S0})")
calls_after = sum(v for k, v in Fake.hits.items() if k >= 15)
p = start(root2); rc2 = p.wait(timeout=30)
check(rc2 == 0 and "HOLD present" in open(os.path.join(root2, "logs", "recorder.log")).read(), "restart refused while HOLD is present")
check(sum(v for k, v in Fake.hits.items() if k >= 15) == calls_after, f"no endpoint calls after the trip/restart ({calls_after} calls hit the 429 slots, all before stopping)")
srv.shutdown()
print("\nRESULT:", "ALL PASSED" if not FAILS else f"{len(FAILS)} FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
