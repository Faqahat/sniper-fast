#!/usr/bin/env python3
"""dipmon unit checks: the incremental tail (partial lines, truncation, replacement), odd / garbage lines, engine detection
by --dip-log (and that no path / URL leaks into what is shown), log-line cleaning, Python 3.9 syntax, small helpers."""
import ast
import atexit
import io
import shutil
import json
import os
import subprocess
import sys
import tempfile
import time
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import dipmon  # noqa: E402

FAILS = []
TMPS = []
atexit.register(lambda: [shutil.rmtree(d, ignore_errors=True) for d in TMPS])


def mkd(prefix):
    d = tempfile.mkdtemp(prefix=prefix)
    TMPS.append(d)
    return d


def check(name, cond, info=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"  ({info})" if info and not cond else ""))
    if not cond:
        FAILS.append(name)


def t_tail():
    print("tail:")
    d = mkd("dipmon-t-")
    p = os.path.join(d, "x.jsonl")
    with open(p, "wb") as f:
        f.write(b'{"ev":"dump","t":1}\n{"ev":"du')
    t = dipmon.Tail(p)
    ln = t.read(1 << 20)
    check("complete line read, partial kept", ln == [b'{"ev":"dump","t":1}'] and t.buf == b'{"ev":"du')
    with open(p, "ab") as f:
        f.write(b'mp","t":2}\n')
    ln = t.read(1 << 20)
    check("partial line completed on the next read", ln == [b'{"ev":"dump","t":2}'] and t.buf == b"")
    with open(p, "ab") as f:
        f.write(b'{"ev":"dump","t":3}')
    check("a complete record without its newline is held", t.read(1 << 20) == [] and t.buf)
    check("...and released when the writer stalls", t.flush_partial_json() == b'{"ev":"dump","t":3}' and t.buf == b"")
    with open(p, "ab") as f:
        f.write(b"\n")
    check("its late newline is not a new record", t.read(1 << 20) == [b""])
    with open(p, "wb") as f:
        f.write(b'{"ev":"dump","t":9}\n')
    t.read(1 << 20)
    check("truncation noticed (reset)", t.reset)
    p2 = p + ".new"
    with open(p2, "wb") as f:
        f.write(b'{"ev":"dump","t":10}\n' * 50)
    t2 = dipmon.Tail(p)
    t2.read(1 << 20)
    os.replace(p2, p)
    t2.read(1 << 20)
    check("replacement (new inode) noticed (reset)", t2.reset)
    t3 = dipmon.Tail(p)
    got = []
    while True:
        x = t3.read(37)
        got += x
        if not t3.pending():
            break
    check("small chunks give the same lines", len([g for g in got if g]) == 50)
    check("missing file: no lines, no error", dipmon.Tail(os.path.join(d, "nope.jsonl")).read(100) == [])


def t_odd_lines():
    print("odd lines:")
    m = dipmon.Model()
    junk = [b"", b"   ", b"\x00\xff\xfe binary", b"not json at all", b'{"ev":"fire"', b'{"ev":"fire","mint":5,"writes":"x"}',
            b'{"ev":"presend_attempt_land","fee":"abc","res":"6042"}', b'{"ev":"presend_live_realized","pnl":"x","w":1}',
            b'{"ev":"close","mint":null}', b'{"ev":"run_start","t":"soon","minutes":"x"}', b'{"ev":"' + b"x" * 300000 + b'"}',
            b'{"ev":"presend_live_ata_close","delta":null,"mint":"m"}', b'[1,2,3]', b'{"ev":"buy_land","mint":"m","variant":7}']
    try:
        m.feed_jsonl(junk)
        ok = True
    except Exception as e:
        ok = False
        print("   ", e)
    check("garbage jsonl lines never raise", ok)
    try:
        m.feed_log([b"\xff\xfe", b"DIP LIVE | model", b"START BALANCE x SOL", b"  REALIZED mint= pnl=abc SOL", b"DIP status: fired x",
                    b"=== DIP DONE: nonsense", b"RUNTIME lag 60s n=abc", b"keepalive: falcon keep-alive: Connection refused" * 100,
                    b"DIP PRESEND LIVE QUIET: arm rule from 99:99 PKT (warm-up x min)", "emoji \U0001F680 and wide 漢".encode()])
        ok = True
    except Exception as e:
        ok = False
        print("   ", e)
    check("garbage log lines never raise", ok)
    try:
        ctx = dipmon.Ctx(_FakeSrc(m), None, dipmon.Price(fixed=100.0), None)
        v = dipmon.build_view(ctx)
        app = _FakeApp(ctx, v)
        for w, h in ((50, 30), (80, 24), (160, 50), (36, 10), (20, 5)):
            for tab in range(7):
                app.tab = tab
                dipmon.render(app, dipmon.TextCanvas(h, w), w, h)
        ok = True
    except Exception as e:
        import traceback
        traceback.print_exc()
        ok = False
    check("views and every tab render on a garbage-only model", ok)


class _FakeSrc:
    def __init__(self, m):
        self.model = m
        self.jsonl = "/x/dip_ams_r1.jsonl"
        self.region, self.run = "AMS", 1
        self.tj = dipmon.Tail("/nonexistent/a")
        self.tl = dipmon.Tail("/nonexistent/b")


class _FakeApp:
    def __init__(self, ctx, v):
        self.ctx = ctx
        self.view = v
        self.tab = 0
        self.scroll = {}
        self.sel = self.top = self.tfilter = 0
        self.detail = None
        self.help = False
        self.usd_first = False
        self.paused = False
        self.interval = 1.0
        self.log_all = self.log_wrap = False
        self.log_off = 0
        self._tlist = []


def t_engine():
    print("engine detection:")
    d = mkd("dipmon-e-")
    p = os.path.join(d, "dip_ams_r77.jsonl")
    open(p, "w").close()
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "snipe_engine_dip20", "--dip-log", p, "--minutes", "130",
                             "--cu-limit", "100000", "--cu-price-micro", "5000000", "--config", "/root/secret.toml",
                             "--rpc-fallback-url-env", "RMR_RPC_URL", "--wallet-keystore", "/root/prod/wallet-ams.enc"])
    try:
        time.sleep(0.3)
        e = dipmon.Engine(p)
        e.scan(force=True)
        check("engine found by its --dip-log", e.alive and e.pid == proc.pid)
        check("build from the binary name", e.build == "dip20", e.build)
        check("only whitelisted flags kept", set(e.flags) <= dipmon.SAFE_FLAGS | dipmon.SAFE_SWITCHES and "--config" not in e.flags
              and not any("/root" in str(v) for v in e.flags.values()), str(e.flags))
        e.sample()
        time.sleep(0.3)
        e.sample()
        check("cpu / rss sampled", e.rss and e.rss > 0 and e.cpu is not None)
    finally:
        proc.terminate()
        proc.wait()
    e.sample()
    check("engine exit noticed", not e.alive and e.gone_at)


def t_clean():
    print("log cleaning:")
    s = dipmon.clean("url https://x.io/?api-key=SECRET123&a=1 token=abc http://user:pw@host/ \U0001F680 漢 tab\there \x07bell")
    check("secrets masked", "SECRET123" not in s and "abc" not in s.split("token=")[1][:3] and "user:pw" not in s, s)
    check("emoji / wide chars replaced", "\U0001F680" not in s and "漢" not in s, s)
    check("control chars replaced", "\x07" not in s and "\t" not in s, s)
    check("box / block glyphs single width", all(__import__("unicodedata").east_asian_width(c) not in ("W", "F")
                                                 for c in "".join(dipmon.UNI.values()) + "".join("".join(g) for g in dipmon.BIG_UNI.values())))


def t_py39():
    print("python 3.9 compatibility:")
    src = open(os.path.join(ROOT, "dipmon.py"), encoding="utf-8").read()
    try:
        ast.parse(src, feature_version=(3, 9))
        ok = True
    except SyntaxError as e:
        ok = False
        print("   ", e)
    check("grammar parses as 3.9", ok)
    bad = []
    if hasattr(tokenize, "FSTRING_START"):          # 3.12+: look inside f-strings for PEP 701 things 3.9 cannot parse
        stack = []
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.FSTRING_START:
                q = tok.string.lstrip("rRbBfF")[:3] if tok.string.lstrip("rRbBfF").startswith(('"""', "'''")) else tok.string.lstrip("rRbBfF")[:1]
                if any(q[0] == o for o in stack):
                    bad.append((tok.start[0], "nested f-string reuses the quote"))
                stack.append(q[0])
            elif tok.type == tokenize.FSTRING_END:
                stack.pop()
            elif stack and tok.type == tokenize.STRING:
                body = tok.string.lstrip("rRbBuU")
                if body[:1] in stack:
                    bad.append((tok.start[0], "string inside an f-string reuses its quote"))
                if "\\" in tok.string:
                    bad.append((tok.start[0], "backslash inside an f-string expression"))
    check("no PEP 701-only f-strings", not bad, str(bad[:5]))
    walrus_ok = True
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Match) if hasattr(ast, "Match") else False:
            walrus_ok = False
    check("no match statements", walrus_ok)


def t_helpers():
    print("helpers:")
    check("route preset v13 recognised", dipmon.route_preset(dipmon._route_map(dipmon.ROUTE_PRESETS["v13"])) == "v13")
    check("custom routes", dipmon.route_preset({"bam": ("nozomi",), "jito": ("x",), "fd": ("y",), "agave": ("z",), "other": ("q",)}) == "custom")
    rows = dipmon.big_text("+0.300")
    check("big numerals: 3 rows, equal width", len(rows) == 3 and len(set(len(r) for r in rows)) == 1)
    rows5 = dipmon.big_text5("-12.34")
    check("large numerals: 5 rows, equal width", len(rows5) == 5 and len(set(len(r) for r in rows5)) == 1)
    check("sol / usd formats", dipmon.sol(412_000_000) == "+0.4120" and dipmon.usd(412_000_000, 100) == "+$41.20" and dipmon.usd(-5e7, 100) == "-$5.00")
    check("usd n/a without a price", dipmon.usd(1, None) == "USD n/a")
    check("hh:mm resolves after midnight", dipmon.hhmm_ns(int(1793116800e9), 0, 30) > int(1793116800e9) - 3600e9)


def t_snapshot_cli():
    print("snapshot cli:")
    d = mkd("dipmon-s-")
    p = os.path.join(d, "dip_r5.jsonl")
    open(p, "w").close()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "dipmon.py"), "--file", p, "--snapshot", "--usd", "100"], capture_output=True, text=True, timeout=30)
    check("empty run file: snapshot works", r.returncode == 0 and "WAITING" in r.stdout, r.stderr[-300:])
    r = subprocess.run([sys.executable, os.path.join(ROOT, "dipmon.py"), "--file", p, "--snapshot", "--json", "--no-usd"], capture_output=True, text=True, timeout=30)
    ok = r.returncode == 0
    try:
        j = json.loads(r.stdout)
        ok = ok and j["status"] == "WAITING" and j["sol_usd"] in (None,) or isinstance(j.get("sol_usd"), float)
    except Exception:
        ok = False
    check("--json parses", ok, r.stderr[-300:])
    r = subprocess.run([sys.executable, os.path.join(ROOT, "dipmon.py"), "--run", "5", "--dir", d, "--snapshot", "--usd", "100", "--ascii"],
                       capture_output=True, text=True, timeout=30)
    check("--run N --dir finds dip_rN (FRA)", r.returncode == 0 and "FRA run 5" in r.stdout and r.stdout.isascii(), r.stdout[:200] + r.stderr[-200:])
    r = subprocess.run([sys.executable, os.path.join(ROOT, "dipmon.py"), "--run", "6", "--dir", d, "--snapshot"], capture_output=True, text=True, timeout=30)
    check("--run of a missing run: clean message", r.returncode != 0 and "no run 6" in (r.stderr + r.stdout), r.stderr[-200:])


def t_fuzz():
    print("fuzz (mutated real lines):")
    import random
    rnd = random.Random(1027)
    src = "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r26"
    if not os.path.exists(src + ".jsonl"):
        print("  (no local r26 copy: skipped)")
        return
    lines = []
    with open(src + ".jsonl", "rb") as f:
        for i, ln in enumerate(f):
            if i % 7 == 0 or b"presend_live" in ln or b'"ev":"fire"' in ln or b'"ev":"close"' in ln or b"run_" in ln:
                lines.append(ln.rstrip(b"\n"))
    logl = open(src + ".log", "rb").read().split(b"\n")
    vals = [b'"x"', b"null", b"true", b"-1", b"1e400", b"[]", b"{}", b'"\\u0000"', b"99999999999999999999999"]

    def mutate(ln):
        r = rnd.random()
        if r < 0.25:
            return ln[: rnd.randint(0, len(ln))]
        if r < 0.5 and b":" in ln:
            parts = ln.split(b":")
            k = rnd.randint(1, len(parts) - 1)
            tail = parts[k]
            cut = min([i for i in (tail.find(b","), tail.find(b"}")) if i >= 0] or [len(tail)])
            parts[k] = rnd.choice(vals) + tail[cut:]
            return b":".join(parts)
        if r < 0.7:
            b = bytearray(ln)
            for _ in range(rnd.randint(1, 5)):
                if b:
                    b[rnd.randrange(len(b))] = rnd.randrange(256)
            return bytes(b)
        return ln
    m = dipmon.Model()
    ok = True
    try:
        for _ in range(3):
            m.feed_jsonl([mutate(x) for x in lines])
            m.feed_log([mutate(x) for x in logl[:4000]])
    except Exception as e:
        ok = False
        print("   ", repr(e))
    check(f"{3 * (len(lines) + 4000):,} mutated lines ingested", ok)
    try:
        ctx = dipmon.Ctx(_FakeSrc(m), None, dipmon.Price(fixed=100.0), None)
        for scope in (None, 0):
            v = dipmon.build_view(ctx, scope)
            app = _FakeApp(ctx, v)
            for w, h in ((50, 30), (80, 24), (160, 50)):
                for tab in range(7):
                    app.tab = tab
                    dipmon.render(app, dipmon.TextCanvas(h, w), w, h)
                app.tab = 3
                for t in dipmon.sorted_trades(v)[:40]:
                    app.detail = t
                    dipmon.render(app, dipmon.TextCanvas(h, w), w, h)
                app.detail = None
            dipmon.snapshot_text(v, ctx)
            dipmon.snapshot_json(v, ctx)
        ok = True
    except Exception:
        import traceback
        traceback.print_exc()
        ok = False
    check("every tab, detail view and snapshot render on the fuzzed model", ok)


def main():
    t_tail()
    t_fuzz()
    t_odd_lines()
    t_engine()
    t_clean()
    t_py39()
    t_helpers()
    t_snapshot_cli()
    print("RESULT:", "PASS" if not FAILS else f"FAIL {FAILS}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
