# RUN-1 GUARD (from /root/lat/guard.py; audit H1 2026-10-20). Watches the Run-1 log; every FIRE is checked ON CHAIN against
# rule #2 (host ok, dev 0.5-8, glued creator bundle 3-5 SOL, create tx tips a moon… Lunar account, create_v2).
# On the FIRST confirmed mismatch it stops the Run-1 engine with SIGTERM: the engine stops new fires and DRAINS its open
# positions (sells until the token account is 0, then logs HELD-AT-EXIT). Never SIGKILL (that would drop open positions).
# The engine is matched EXACTLY: the given PID, whose argv[0] must be /root/sniper-run1/target/release/snipe_engine and
# which must run --snipe-once (without a PID: every process with exactly that argv[0] and --snipe-once).
# Exits when the done marker (RUN1_DONE / DRY_RUN1_DONE) is in the log and no fire is still being verified.
# AUDIT 3: L-2 FAIL CLOSED: a fire that cannot be verified (block unavailable after 20 tries) also stops the engine
# (SIGTERM, drain); the log is read incrementally (new bytes only). L-3: a FAILED leg inside the glued run no longer ends
# the run here (the engine cannot see execution results and counts it); a bundle-range failure explained only by failed
# legs is a WARN, not an ALERT.
# usage: python3 guard_run1.py LOG OUT MARKER [ENGINE_PID]
import sys, re, time, os, signal
sys.path.insert(0, "/root/indep")
from common import get_block, events, is_vote, tx_summary, load_tipmap
TM = load_tipmap()
LOG, OUT, MARKER = sys.argv[1], sys.argv[2], sys.argv[3]
PID = int(sys.argv[4]) if len(sys.argv) > 4 else None
ENGINE = "/root/sniper-run1/target/release/snipe_engine"
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}
# L4-8 (audit 4): the glued run is delimited EXACTLY like the engine's snipe::bundle_legs: a following tx that references
# the mint and whose TOP-LEVEL pump instructions are only buys (of the mint) is a leg — counted whether it executed or
# failed (shreds carry no execution result; the guard counts its executed SOL and the failed ones separately); any other
# top-level pump instruction (a sell, ...) closes the run (NotBuy); no top-level pump instruction (a CPI buy) is an
# UNKNOWN leg (the engine rejects the launch); a tx not referencing the mint closes the run.
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
BUY_DISCS = {bytes(x) for x in ([0xe1, 0xf7, 0x50, 0x1e, 0xd5, 0xb3, 0x84, 0x88], [0xc2, 0xab, 0x1c, 0x46, 0x68, 0x4d, 0x5b, 0x2f],
                                [0x38, 0xfc, 0x74, 0x08, 0x9e, 0xdf, 0xcd, 0x5f], [0x66, 0x06, 0x3d, 0x12, 0x01, 0xda, 0xeb, 0xea],
                                [0xb8, 0x17, 0xee, 0x61, 0x67, 0xc5, 0xd3, 0x3d], [0x07, 0x05, 0x1d, 0xc4, 0xf5, 0x17, 0x65, 0x50])}
CREATE_DISCS = {bytes([0xd6, 0x90, 0x4c, 0xec, 0x5f, 0x8b, 0x31, 0xb4]), bytes([0x18, 0x1e, 0xc8, 0x28, 0x05, 0x1c, 0x07, 0x77])}
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58dec(s):
    n = 0
    for c in s:
        n = n * 58 + _B58.index(c)
    full = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + full


def leg_kind(t, mint):
    """the engine's bundle_legs for one getBlock(json) tx: None (does not reference the mint), buys, notbuy or unknown"""
    msg = (t.get("transaction") or {}).get("message") or {}
    la = (t.get("meta") or {}).get("loadedAddresses") or {}
    keys = list(msg.get("accountKeys") or []) + list(la.get("writable") or []) + list(la.get("readonly") or [])
    if mint not in keys:
        return None
    buys = pump = other = False
    for ix in msg.get("instructions") or []:
        pi = ix.get("programIdIndex")
        if pi is None or pi >= len(keys) or keys[pi] != PUMP:
            continue
        pump = True
        d = b58dec(ix.get("data") or "")[:8]
        if d in BUY_DISCS:
            buys = True
        elif d not in CREATE_DISCS:
            other = True
    return "buys" if buys and not other else ("notbuy" if pump else "unknown")


def say(s):
    with open(OUT, "a") as f:
        f.write(time.strftime("%H:%M:%S ") + s + "\n")


# Telegram (owner: "update everything to telegram"): ALERT / UNVERIFIED lines go to the same chat as the engine's
# (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from the env run1.sh sources). Posted from a daemon thread (the guard never waits
# on it); the token is never printed (an error prints only its class name). GUARD_ENV labels the message (DEV / PROD).
def tg_post(text):
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not tok or not chat:
        return

    def go():
        import urllib.request, urllib.parse
        try:
            data = urllib.parse.urlencode({"chat_id": chat, "text": f"GUARD {os.environ.get('GUARD_ENV', 'DEV')}: {text}"[:3900],
                                           "disable_web_page_preview": "true"}).encode()
            urllib.request.urlopen(urllib.request.Request("https://api.telegram.org/bot" + tok + "/sendMessage", data=data), timeout=10).read()
        except Exception as e:  # never the URL (it carries the token)
            say(f"telegram post failed: {type(e).__name__}")
    import threading
    threading.Thread(target=go, daemon=True).start()


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
        failed_legs = unknown_legs = 0
        for t2 in txs[i + 1:]:
            m2 = t2.get("meta") or {}
            k = leg_kind(t2, mint)
            if k is None or k == "notbuy":
                break  # the engine's run ends here too
            if k == "unknown":
                unknown_legs += 1  # a CPI buy: the engine counts it UNKNOWN and rejects the launch
            if m2.get("err") is not None:
                failed_legs += 1  # counted by the engine (no execution result in shreds); no SOL went in
                continue
            tr2, _ = events(m2.get("logMessages"))
            gsol += sum(e["sol"] for e in tr2 if e["mint"] == mint and e["buy"]) / 1e9
        tips = tx_summary(t, TM)[0]["tips"]
        moon = any(str(x[2]).startswith("moon") for x in tips)
        host = c[0]["uri"].split("://")[-1].split("/")[0]
        v2 = any("Instruction: CreateV2" in x for x in (meta.get("logMessages") or []))
        fails = [k for k, ok in {"host": not (host in BOT or host.endswith(".trycloudflare.com")), "dev 0.5-8": 0.49 <= dev <= 8.1,
                                 "bundle 3-5 SOL": 2.95 <= gsol <= 5.05, "lunar tip": moon, "create_v2": v2}.items() if not ok]
        if unknown_legs:
            fails.append("unknown (CPI) leg: the engine rejects these")
        info = f"dev {dev:.2f} bundle {gsol:.2f} SOL (failed legs {failed_legs}, unknown legs {unknown_legs}) lunar {moon} host {host[:24]} " + ("" if not fails else "FAILED: " + ",".join(fails))
        if fails == ["bundle 3-5 SOL"] and failed_legs > 0:
            return "warn", info + " (explained by failed bundle legs the engine counts: WARN, not stopped)"
        return (not fails), info
    return None, "create not in that slot"


def argv_of(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
    except OSError:
        return []


def is_engine(pid):
    a = argv_of(pid)
    return bool(a) and a[0] == ENGINE and "--snipe-once" in a


def engine_pids():
    if PID is not None:
        return [PID] if is_engine(PID) else []
    return [int(d) for d in os.listdir("/proc") if d.isdigit() and is_engine(int(d))]


def stop_engine():
    pids = engine_pids()
    for p in pids:
        try:
            os.kill(p, signal.SIGTERM)
        except OSError:
            pass
    return pids


seen, pending, stopped = set(), {}, False
say(f"GUARD start log={LOG} marker={MARKER} engine={ENGINE} pid={PID} (matches now: {engine_pids()})")
pos, buf, done_seen = 0, "", False
while True:
    # L-2: read only the new bytes (complete lines)
    try:
        with open(LOG, "rb") as f:
            f.seek(pos)
            chunk = f.read()
            pos += len(chunk)
    except FileNotFoundError:
        chunk = b""
    buf += chunk.decode(errors="replace")
    txt, _, buf = buf.rpartition("\n")
    if re.search(r"^" + re.escape(MARKER) + r"\b", txt, re.M):
        done_seen = True
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
                # L-2: fail closed: an unverifiable fire stops the engine too
                pids = stop_engine() if not stopped else []
                stopped = stopped or bool(pids)
                say(f"UNVERIFIED {k[1]} slot {k[0]}: {info} (gave up after retries) -> ENGINE SIGTERM (fail closed; pids {pids})")
                tg_post(f"UNVERIFIED {k[1]} slot {k[0]}: {info} -> ENGINE SIGTERM (fail closed)")
                del pending[k]
            continue
        del pending[k]
        if ok == "warn":
            say(f"WARN {k[1]} slot {k[0]} {info}")
        elif ok:
            say(f"OK   {k[1]} slot {k[0]} {info}")
        else:
            pids = stop_engine() if not stopped else []
            stopped = stopped or bool(pids)
            say(f"ALERT {k[1]} slot {k[0]} {info} -> ENGINE SIGTERM (pids {pids}): no new fires, open positions drain")
            tg_post(f"ALERT {k[1]} slot {k[0]} {info} -> ENGINE SIGTERM: no new fires, open positions drain")
    if done_seen and not pending:
        say("GUARD done")
        break
    time.sleep(3)
