# LIVE GUARD (owner: "make sure we don't buy random"). Watches the live log; every FIRE is checked ON CHAIN against
# rule #2 (host ok, dev 0.5-8, glued creator bundle 3-5 SOL, create tx tips a moon… Lunar account, create_v2).
# On the FIRST confirmed mismatch it kills the live engine (exact PID) and writes ALERT. Read-only otherwise.
import sys, re, time, os, signal, subprocess
sys.path.insert(0, "/root/indep")
from common import get_block, events, is_vote, tx_summary, load_tipmap
TM = load_tipmap()
LOG, OUT = sys.argv[1], sys.argv[2]
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}


def say(s):
    with open(OUT, "a") as f:
        f.write(time.strftime("%H:%M:%S ") + s + "\n")


def check(slot, mint):
    blk = get_block(slot)
    if not (isinstance(blk, dict) and "transactions" in blk):
        return None, "block not available yet"
    txs = [t for t in blk["transactions"] if not is_vote(t)]
    for i, t in enumerate(txs):
        meta = t.get("meta") or {}
        tr, cr = events(meta.get("logMessages"))
        c = [x for x in cr if x["mint"] == mint]
        if not c:
            continue
        dev = sum(e["sol"] for e in tr if e["mint"] == mint and e["buy"]) / 1e9
        gsol = 0.0
        for t2 in txs[i + 1:]:
            m2 = t2.get("meta") or {}
            tr2, _ = events(m2.get("logMessages"))
            b = [e for e in tr2 if e["mint"] == mint and e["buy"]]
            if m2.get("err") is None and b:
                gsol += sum(e["sol"] for e in b) / 1e9
            else:
                break
        tips = tx_summary(t, TM)[0]["tips"]
        moon = any(str(x[2]).startswith("moon") for x in tips)
        host = c[0]["uri"].split("://")[-1].split("/")[0]
        v2 = any("Instruction: CreateV2" in x for x in (meta.get("logMessages") or []))
        fails = [k for k, ok in {"host": not (host in BOT or host.endswith(".trycloudflare.com")), "dev 0.5-8": 0.49 <= dev <= 8.1,
                                 "bundle 3-5 SOL": 2.95 <= gsol <= 5.05, "lunar tip": moon, "create_v2": v2}.items() if not ok]
        return (not fails), f"dev {dev:.2f} bundle {gsol:.2f} SOL lunar {moon} host {host[:24]} " + ("" if not fails else "FAILED: " + ",".join(fails))
    return None, "create not in that slot"


def kill_engine():
    out = subprocess.run(["bash", "-c", "ps -eo pid,args | grep -E '[a]rbx-final2?/target/release/snipe_engine --snipe-once' | awk '{print $1}'"],
                         capture_output=True, text=True).stdout.split()
    for p in out:
        try:
            os.kill(int(p), signal.SIGTERM)
        except Exception:
            pass
    return out


seen, pending = set(), {}
say("GUARD start")
while True:
    try:
        txt = open(LOG, errors="replace").read()
    except FileNotFoundError:
        txt = ""
    for m in re.finditer(r"^\s*FIRE slot=(\d+) mint=(\w+)", txt, re.M):
        k = (int(m.group(1)), m.group(2))
        if k not in seen:
            seen.add(k)
            pending[k] = 0
    for k in list(pending):
        ok, info = check(*k)
        if ok is None:
            pending[k] += 1
            if pending[k] > 20:
                say(f"UNVERIFIED {k[1]} slot {k[0]}: {info} (gave up after retries)")
                del pending[k]
            continue
        del pending[k]
        if ok:
            say(f"OK   {k[1]} slot {k[0]} {info}")
        else:
            pids = kill_engine()
            say(f"ALERT {k[1]} slot {k[0]} {info} -> ENGINE STOPPED (pids {pids})")
    if re.search(r"LIVE_FINAL2?_DONE", txt) and not pending:
        say("GUARD done")
        break
    time.sleep(3)
