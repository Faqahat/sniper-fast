#!/usr/bin/env python3
# STANDARD DIP RUN REPORT (owner 10-25 ~01:30 PKT: "a very detailed run report, standardized, covering everything that happened
# in each run: what's different from the last one, P&L, leaders, red flags, fixes"). One Markdown file per run per region.
# Sources (read-only):
#   <data>/<region>/runs/<tag><N>.jsonl + .log   copies of /root/prod/runs on the server (engine records + engine log)
#   <data>/<region>/<budget file>                 the run script's dip budget (wallet balance at each start / end)
#   the chain                                     getTransaction of every landed buy / sell (fee, the wallet's SOL change)
#   ops/dip/report/run_notes.json                 hand-written per run: purpose, owner decisions, what changed and why,
#                                                 incidents, fixes (from ops/dip/PLAN.md and the session log)
# usage: python3 make_run_report.py --region fra --run 7      one report
#        python3 make_run_report.py --all                     every run found (+ INDEX.md)
#        --no-chain  skip RPC (fees then come from the engine records)
# RPC: the URL in ~/.config/sniper/ck_rpc_url (never printed); answers cached in <data>/txcache.json.
import argparse, json, os, re, sys, time, statistics as st, collections, urllib.request, datetime as dt
from concurrent.futures import ThreadPoolExecutor

DATA = "/home/moiz/sniper-data/runs"
OUT = "/home/moiz/sniper/ops/dip/reports/runs"
NOTES = "/home/moiz/sniper/ops/dip/report/run_notes.json"
COHORT = "/home/moiz/sniper/ops/overnight/sel/cohort_train.json"
REG = {"fra": dict(name="Frankfurt", short="FRA", server="cybershock (84.32.100.36)", tag="dip_r", budget="dip_budget.json",
                   wallet="2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"),
       "ams": dict(name="Amsterdam", short="AMS", server="cyber-dock (84.32.104.202)", tag="dip_ams_r", budget="dip_budget_ams.json",
                   wallet="EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR")}
KIND = {"JitoLabs": "Jito", "AgaveBam": "BAM", "FireBAM": "BAM", "HarmonicAgave": "Harmonic", "HarmonicFiredancer": "Harmonic",
        "Firedancer": "Firedancer", "Frankendancer": "Firedancer", "Agave": "Agave", "Rakurai": "Rakurai"}
KNOWN = {"haqqiUUX": "haqq (dip bot)", "HkQ7hMjy": "HkQ7 (dip bot)", "DYXDDrZC": "DYXD (dip bot)", "CVPz447t": "CVPz447t (pre-placed)",
         "2KtcBCfh": "2KtcBC (pre-placed)", "3Xti8uhq": "3Xti8uhq (fast bot)", "9k78QZyw": "9k78QZyw (fast bot)", "3MHgGwdL": "3MHgGwdL",
         "omegoMAe": "omegoMAe (F9)", "7PedQZmc": "7PedQZmc (untipped fast)", "HLU8QbLd": "HLU8QbLd (41Pr family)",
         "E6JasdE8": "E6JasdE8 (speedlanding)", "6n2cCJrr": "6n2cCJrr", "BfvkhDip": "BfvkhDip", "8PgC4ngp": "8PgC4ngp",
         "GKd5EMzR": "GKd5EMzR (F9 scalper)", "ssssswdk": "ssssswdk (sss fleet)", "sssssDdM": "sssssDdM (sss fleet)",
         "9pQQc1xy": "9pQQc1xy (bait follower)", "bwamJzzt": "bwamJzzt (serial dev)"}
SMS = 212.0

def pkt(ns, fmt="%H:%M:%S"):
    return dt.datetime.fromtimestamp(ns / 1e9, dt.timezone(dt.timedelta(hours=5))).strftime(fmt)

def sol(x, d=4):
    return "–" if x is None else f"{x:+.{d}f}"

def med(v):
    v = [x for x in v if x is not None]
    return st.median(v) if v else None

def pct(v, q):
    v = sorted(x for x in v if x is not None)
    if not v: return None
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))]

def f1(x, nd=1, suf=""):
    return "–" if x is None else f"{x:.{nd}f}{suf}"

def short(u): return u[:8] if u else "?"

# ------------------------------------------------------------------ chain
class Chain:
    def __init__(self, enabled):
        self.enabled = enabled; self.url = None; self.cache = {}
        if os.path.exists(f"{DATA}/txcache.json"):
            try: self.cache = json.load(open(f"{DATA}/txcache.json"))
            except Exception: self.cache = {}
        if enabled:
            p = os.path.expanduser("~/.config/sniper/ck_rpc_url")
            if os.path.exists(p): self.url = open(p).read().strip()
            else: self.enabled = False
    def _rpc(self, m, p):
        last = None
        for i in range(5):
            try:
                req = urllib.request.Request(self.url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                             headers={"content-type": "application/json"})
                r = json.load(urllib.request.urlopen(req, timeout=30))
                if "error" in r: raise RuntimeError(str(r["error"])[:160])
                return r["result"]
            except Exception as e:
                last = e; time.sleep(0.6 * (i + 1))
        raise RuntimeError(f"rpc {m}: {last}")
    def tx(self, sig, wallet):
        key = f"{sig}|{wallet}"
        if key in self.cache: return self.cache[key]
        if not self.enabled or not sig: return None
        try:
            t = self._rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
        except Exception:
            return None
        if not t: return None
        keys = t["transaction"]["message"]["accountKeys"] + (t["meta"].get("loadedAddresses") or {}).get("writable", []) + \
            (t["meta"].get("loadedAddresses") or {}).get("readonly", [])
        i = keys.index(wallet) if wallet in keys else None
        d = (t["meta"]["postBalances"][i] - t["meta"]["preBalances"][i]) if i is not None else 0
        out = {"delta": d, "fee": t["meta"]["fee"], "err": t["meta"]["err"], "slot": t["slot"], "cu": t["meta"].get("computeUnitsConsumed")}
        self.cache[key] = out
        return out
    def prefetch(self, sigs, wallet):
        todo = [s for s in sigs if s and f"{s}|{wallet}" not in self.cache]
        if not todo or not self.enabled: return
        with ThreadPoolExecutor(6) as ex: list(ex.map(lambda s: self.tx(s, wallet), todo))
    def save(self):
        tmp = f"{DATA}/txcache.json.tmp"; json.dump(self.cache, open(tmp, "w")); os.replace(tmp, f"{DATA}/txcache.json")

# ------------------------------------------------------------------ parsing
def split_log(path):
    """engine starts in the log: each starts with the Alpenglow WARNING line (or, for very early logs, the payer line)"""
    sess, cur = [], None
    for line in open(path, errors="ignore"):
        if line.startswith("WARNING: date >=") or (line.startswith("snipe_engine: payer") and (cur is None or any(l.startswith("snipe_engine: payer") for l in cur))):
            if cur is not None: sess.append(cur)
            cur = [line.rstrip("\n")]
        else:
            if cur is None: cur = []
            cur.append(line.rstrip("\n"))
    if cur: sess.append(cur)
    return sess

def split_jsonl(path):
    sess, cur = [], None
    for line in open(path, errors="ignore"):
        try: o = json.loads(line)
        except Exception: continue
        if o.get("ev") == "run_start":
            if cur is not None: sess.append(cur)
            cur = [o]
        elif cur is not None: cur.append(o)
    if cur is not None: sess.append(cur)
    return sess

RX = {
    "rpc_lat": re.compile(r"RPC-LAT 60s (\S+) (\S+): n=(\d+) p50=([\d.]+)ms p90=([\d.]+)ms p99=([\d.]+)ms max=([\d.]+)ms timeouts/transport=(\d+)"),
    "runtime": re.compile(r"RUNTIME lag 60s .*?n=(\d+) p50=([\d.]+)ms p99=([\d.]+)ms max=([\d.]+)ms"),
    "fast_ack": re.compile(r"FAST-ACK tag=\S+ path=(\S+) ack_ms=([\d.]+) (?:status=Some\((\d+)\)|ok=(\w+)|answered=(\w+))"),
    "realized": re.compile(r"REALIZED mint=(\S+) pnl=([-+0-9.]+) SOL source=(\S+)"),
    "route": re.compile(r"ROUTE (\S+)\s+-> (.+)$"),
    # pre-send live probe (engine dip13+): each fill's chain P&L, and the failed attempts' fees (cumulative in every status line)
    "ps_realized": re.compile(r"PRESEND LIVE REALIZED (\S+) ([-+0-9.]+) SOL"),
    "ps_fees": re.compile(r"PRESEND LIVE.*?failed-attempt fees ([0-9.]+)"),
}

def parse_log(lines):
    L = dict(errors=[], refused=None, routes={}, sell_path=None, sell_fb=None, fire_path=None, fallback=None, n_paths=None,
             live_line=None, dev_line=None, near=None, nonce_on=None, nonce_selftest=None, rpc={}, runtime=[], acks=collections.Counter(),
             ack_bad=collections.Counter(), ack_429=collections.Counter(), ack_ms=collections.defaultdict(list), realized=[], signal=None, done=None,
             poll_err=0, unhealthy=[], sell_issues=[], kill=[], nonce_issues=collections.Counter(), telegram=None, panics=[], harmonic_auth=None,
             leaderbook=None, notes=[], payer=None, fast_verify=None, dip_status=None, mismatch=0,
             ps_live_line=None, ps_shadow=False, ps_end_check=None, ps_summary=None)
    for l in lines:
        s = l.strip()
        # pre-send live (1027): its config line, the shadow flag, the end-of-run check and summary
        if s.startswith("DIP PRESEND LIVE (") or s.startswith("DIP PRESEND LIVE DRY"): L["ps_live_line"] = s
        if s.startswith("DIP PRESEND SHADOW"): L["ps_shadow"] = True
        if s.startswith("PRESEND LIVE END CHECK") and "read at confirmed" in s: L["ps_end_check"] = s.replace("PRESEND LIVE END CHECK: ", "")
        if s.startswith("=== DIP PRESEND LIVE:"): L["ps_summary"] = s
        if s.startswith("snipe_engine: payer"): L["payer"] = s.split("=")[-1].strip()
        if s.startswith("Error:"): L["errors"].append(s); L["refused"] = L["refused"] or s
        m = RX["route"].search(s)
        if m and s.startswith("snipe_engine: ROUTE"): L["routes"][m.group(1)] = m.group(2).strip()
        if s.startswith("snipe_engine: SELL path"): L["sell_path"] = s.split("=", 1)[1].strip()
        if s.startswith("snipe_engine: SELL FALLBACK path"): L["sell_fb"] = s.split("=", 1)[1].split("(")[0].strip()
        if s.startswith("snipe_engine: fire path"): L["fire_path"] = s.split("=", 1)[1].strip()
        if s.startswith("RPC-FALLBACK:") and "genesis" in s: L["fallback"] = s.split()[1]
        if s.startswith("snipe_engine: building"): L["n_paths"] = s.split()[2]
        if s.startswith("DIP LIVE |"): L["live_line"] = s
        if s.startswith("DIP dev list"): L["dev_line"] = s
        if s.startswith("DIP near-leader gate"):
            m2 = re.search(r"(\d+) leaders", s); L["near"] = int(m2.group(1)) if m2 else s
        if s.startswith("NONCE-FANOUT ON"):
            m2 = re.search(r"ON: (\d+)", s); L["nonce_on"] = int(m2.group(1)) if m2 else True
        if s.startswith("NONCE-FANOUT OFF"): L["nonce_on"] = 0
        if s.startswith("NONCE self-test"): L["nonce_selftest"] = s
        if "LEADER-BOOK" in s: L["leaderbook"] = s
        if s.startswith("FAST: fast-verify"): L["fast_verify"] = s
        if "MISMATCH" in s and "0 MISMATCHED" not in s: L["mismatch"] += 1
        if "HARMONIC AUTH" in s: L["harmonic_auth"] = "OK" if "AUTH OK" in s else "FAILED (public sendBundle used)"
        m = RX["rpc_lat"].search(s)
        if m:
            k = (m.group(1), m.group(2)); r = L["rpc"].setdefault(k, dict(n=0, p99=0.0, mx=0.0, to=0, p50=[]))
            r["n"] += int(m.group(3)); r["p50"].append(float(m.group(4))); r["p99"] = max(r["p99"], float(m.group(6)))
            r["mx"] = max(r["mx"], float(m.group(7))); r["to"] += int(m.group(8))
        m = RX["runtime"].search(s)
        if m: L["runtime"].append((float(m.group(2)), float(m.group(3)), float(m.group(4))))
        m = RX["fast_ack"].search(s)
        if m:
            p = m.group(1); L["acks"][p] += 1; L["ack_ms"][p].append(float(m.group(2)))
            code = m.group(3)
            if (code and code != "200") or (m.group(4) == "false"): L["ack_bad"][p] += 1
            if code == "429" or "429" in s: L["ack_429"][p] += 1
        m = RX["realized"].search(s)
        if m: L["realized"].append((m.group(1), float(m.group(2)), m.group(3)))
        m = RX["ps_realized"].search(s)
        if m: L.setdefault("ps_realized", []).append((m.group(1), float(m.group(2))))
        m = RX["ps_fees"].search(s)
        if m: L["ps_fees"] = max(L.get("ps_fees", 0.0), float(m.group(1)))
        if s.startswith("SIGNAL"): L["signal"] = s
        if s.startswith("=== DIP DONE"): L["done"] = s
        if s.startswith("DIP status"): L["dip_status"] = s
        if "POLL-RPC-ERROR" in s: L["poll_err"] += 1
        if "SEND-PATH" in s and ("UNHEALTHY" in s or "RECOVERED" in s): L["unhealthy"].append(s[:200])
        if not s.startswith("DIP status") and re.search(r"SELL-(FAIL|GIVE|STUCK)|SELL #\d+ .*(fail|FAIL|err)|AccountNotInitialized|\b3012\b", s):
            L["sell_issues"].append(s[:220])   # (status lines skipped: their counters can read 3012)
        if re.search(r"DIP KILL-SWITCH|KILL-SWITCH BLIND|KILL-SWITCH \(realized|KILL-SWITCH pending", s): L["kill"].append(s[:200])
        for k in ("NONCE-FALLBACK", "NONCE-DEAD", "NONCE-REUSE", "NONCE-REFRESH read failed"):
            if k in s: L["nonce_issues"][k] += 1
        if s.startswith("TELEGRAM: raised"): L["telegram"] = s
        if "panicked" in s: L["panics"].append(s[:200])
    return L

# ------------------------------------------------------------------ one session -> trades
def build_trades(ev, wallet):
    fires = []; by_mint = collections.defaultdict(list); picks = {}; skips = collections.Counter(); dumps = 0; run_start = ev[0]; run_end = None
    # pre-send live records (engine dip13+), kept apart from the reactive bot's trades
    ps = dict(arm={}, fills=[], close=[], realized=[], ata=[], stop=[], end_check=[], held=[], sent=0, dry=0,
              res=collections.Counter(), fail_fee=0, att=collections.defaultdict(dict))
    for o in ev:
        e = o.get("ev")
        if e == "dump": dumps += 1; continue
        if e and e.startswith("presend_"):
            if e == "presend_attempt":
                if o.get("dry"): ps["dry"] += 1
                else: ps["sent"] += 1
                ps["att"][o.get("sig")] = dict(leader=o.get("leader"), client=o.get("client"))
            elif e == "presend_attempt_land":
                ps["res"][o.get("res") or "?"] += 1
                if o.get("res") != "ok": ps["fail_fee"] += o.get("fee") or 0
            elif e == "presend_live_arm": ps["arm"][o.get("w")] = o
            elif e == "presend_live_fill": ps["fills"].append(o)
            elif e == "presend_live_close": ps["close"].append(o)
            elif e == "presend_live_realized": ps["realized"].append(o)
            elif e == "presend_live_ata_close": ps["ata"].append(o)
            elif e == "presend_live_stop": ps["stop"].append(o)
            elif e == "presend_live_end_check": ps["end_check"].append(o)
            elif e == "presend_live_held": ps["held"].append(o)
            continue
        if e == "pick": picks[o.get("sig")] = o; continue
        if e == "pick_skip": skips[o.get("why", "?")] += 1; continue
        if e == "run_end": run_end = o; continue
        if e == "fire":
            tr = dict(fire=o, pick=picks.get(o.get("dump_sig"), {}), land=None, failed=None, poll=None, timing=None, exit=None, sells=[], close=None, tape=[])
            fires.append(tr); by_mint[o["mint"]].append(tr); continue
        m = o.get("mint")
        if not m or m not in by_mint: continue
        cands = by_mint[m]
        open_ = [t for t in cands if t["close"] is None]
        tr = open_[0] if open_ else cands[-1]
        if e == "buy_land": tr["land"] = tr["land"] or o
        elif e == "buy_failed": tr["failed"] = tr["failed"] or o
        elif e == "land_poll": tr["poll"] = tr["poll"] or o
        elif e == "timing":
            t2 = next((t for t in cands if t["timing"] is None), None)
            if t2: t2["timing"] = o
        elif e == "exit": tr["exit"] = tr["exit"] or o
        elif e == "sell_land": tr["sells"].append(o)
        elif e == "close": tr["close"] = o
        elif e == "tape": (tr if tr["close"] is None else cands[-1])["tape"].append(o)
    return dict(fires=fires, picks=picks, skips=skips, dumps=dumps, run_start=run_start, run_end=run_end, ps=ps)

# ------------------------------------------------------------------ pre-send live: one engine session -> its numbers
def ps_session(S):
    """pre-send live numbers of one engine session. P&L = the engine's PRESEND LIVE REALIZED records (chain txs of each buy + sell);
    rent back = token-account rent returned when the engine closed each pre-send account after the exit (dip19+; before dip19 the sell
    closed it and the refund sat inside realized); failed tries = fees of tries that landed and failed (6042 price, deadline, ...).
    Log lines are the fallback when the jsonl has no pre-send records."""
    P = S.get("ps") or {}; L = S["L"]
    out = dict(active=False, live_line=L.get("ps_live_line"), sent=P.get("sent", 0), res=P.get("res", collections.Counter()), fills=0,
               positions=[], realized=0.0, rent=0.0, fees=0.0, wins=0, unseen=0, stop=P.get("stop", []), end_check=L.get("ps_end_check"),
               end_actions=collections.Counter(o.get("action") for o in P.get("end_check", [])), held=P.get("held", []),
               after_exit=0, ata_fail=[], not_sold=[], t0=S["run_start"].get("t"), fail_lamports=5120)
    m = re.search(r"a failed attempt (\d+) lamports", L.get("ps_live_line") or "")
    if m: out["fail_lamports"] = int(m.group(1))
    fills = P.get("fills", []); closes = P.get("close", [])
    if fills or closes or P.get("sent") or P.get("stop"):
        out["active"] = True
        out["fills"] = len(fills)
        out["after_exit"] = sum(1 for f in fills if f.get("after_exit"))
        real = collections.defaultdict(list)
        for r in P.get("realized", []): real[(r.get("w"), r.get("mint"))].append(r)
        ata = collections.defaultdict(list)
        for a in P.get("ata", []):
            if a.get("ok", True): ata[a.get("mint")].append(a)
            else: out["ata_fail"].append(a)
        fill_by = collections.defaultdict(list)
        for f in fills: fill_by[(f.get("w"), f.get("mint"))].append(f)
        for c in closes:
            k = (c.get("w"), c.get("mint"))
            r = real[k].pop(0) if real.get(k) else None
            a = ata[c.get("mint")].pop(0) if ata.get(c.get("mint")) else None
            f = fill_by[k][0] if fill_by.get(k) else {}
            arm = (P.get("arm") or {}).get(c.get("w")) or {}
            trig = arm.get("trig") or {}
            att = (P.get("att") or {}).get(f.get("sig") or c.get("buy_sig")) or {}
            land = c.get("land") or []
            out["positions"].append(dict(
                t=f.get("t") or (land[2] if len(land) > 2 else None) or S["run_start"].get("t"), mint=c.get("mint", ""), w=c.get("w"),
                pnl=(r.get("pnl") / 1e9) if r and r.get("pnl") is not None else None, rent=(a.get("delta", 0) / 1e9) if a else 0.0,
                exit=c.get("exit_why"), held=c.get("held_s"), result=c.get("result"), merged=c.get("merged") or 0, late=c.get("late") or 0,
                client=c.get("client") or f.get("client") or "?", kind=KIND.get(c.get("client") or f.get("client") or "", c.get("client") or "?"),
                leader=att.get("leader") or "", buy_sigs=c.get("buy_sigs") or ([c["buy_sig"]] if c.get("buy_sig") else []),
                sell_sigs=[x[0] for x in (c.get("sell_sigs") or []) if isinstance(x, list) and x and x[0]],   # every sell tx sent (one may be unseen yet landed)
                trig_pct=trig.get("pct"), trig_sol=(trig.get("sol") or 0) / 1e9 if trig.get("sol") else None, trig_sig=trig.get("sig"),
                trig_wallet=trig.get("wallet") or "", after_trig=f.get("slots_after_trigger"), spend=(c.get("spend") or 0) / 1e9,
                curve=(c.get("curve_pnl") or 0) / 1e9))
            if c.get("result") not in ("sold", None): out["not_sold"].append(c)
        # realized records without a close (should not happen) still count
        for k, rr in real.items():
            for r in rr:
                out["positions"].append(dict(t=S["run_start"].get("t"), mint=r.get("mint", ""), w=r.get("w"), pnl=r.get("pnl", 0) / 1e9, rent=0.0,
                                             exit="?", held=None, result="?", merged=0, late=0, client="?", kind="?", leader="", buy_sigs=[],
                                             sell_sigs=[], trig_pct=None, trig_sol=None, trig_sig=None, trig_wallet="", after_trig=None, spend=0.0, curve=None))
        out["realized"] = sum(p["pnl"] or 0 for p in out["positions"])
        out["rent"] = sum(p["rent"] for p in out["positions"]) + sum(a.get("delta", 0) / 1e9 for rr in ata.values() for a in rr)
        out["wins"] = sum(1 for p in out["positions"] if (p["pnl"] or 0) > 0)
        out["fees"] = max(P.get("fail_fee", 0) / 1e9, L.get("ps_fees", 0.0), max([s.get("fees") or 0 for s in P.get("stop", [])] or [0]) / 1e9)
        out["unseen"] = out["res"].get("unseen", 0)
    elif L.get("ps_realized") or L.get("ps_fees"):
        out["active"] = True
        out["fills"] = len(L.get("ps_realized", []))
        for mnt, p in L.get("ps_realized", []):
            out["positions"].append(dict(t=S["run_start"].get("t"), mint=mnt, w=None, pnl=p, rent=0.0, exit="?", held=None, result="sold", merged=0, late=0,
                                         client="?", kind="?", leader="", buy_sigs=[], sell_sigs=[], trig_pct=None, trig_sol=None, trig_sig=None,
                                         trig_wallet="", after_trig=None, spend=0.0, curve=None))
        out["realized"] = sum(p for _, p in L.get("ps_realized", [])); out["fees"] = L.get("ps_fees", 0.0)
        out["wins"] = sum(1 for _, p in L.get("ps_realized", []) if p > 0)
    out["net"] = out["realized"] + out["rent"] - out["fees"]
    return out

def ps_cfg(L):
    """one-line pre-send live config from the engine's 'DIP PRESEND LIVE (REAL attempts)' line"""
    s = L.get("ps_live_line")
    if not s: return "off (shadow only)" if L.get("ps_shadow") else "off"
    g = lambda rx: (re.search(rx, s) or [None, "?"])[1]
    return (("DRY (builds + signs, never sends): " if s.startswith("DIP PRESEND LIVE DRY") else "LIVE: ") + f"whale >= {g(r'whale >= ([0-9.]+%)')}, {g(r'(\d+) attempts per slot')} tries/slot, {g(r'([0-9.]+) SOL, limit')} SOL, "
            f"limit x{g(r'price x ([0-9.]+)')}, route {g(r'routes default=([\w-]+)')}, caps {g(r'caps: (\d+) fills')} fills / "
            f"{g(r'fees ([0-9.]+) SOL')} SOL failed-try fees, exit {g(r'exit ([^|]+)$').strip()}")

def classify(tr):
    c = tr["close"] or {}
    res = c.get("result")
    if tr["land"] or res == "sold": return "filled"
    err = json.dumps(c.get("err") or (tr["poll"] or {}).get("err") or "")
    if res == "buy_failed" or tr["failed"]:
        return "guard" if "6042" in err else "failed"
    if res in ("not_landed", "dropped", "expired", None): return "not landed"
    return res or "?"

def known(u, coh):
    k = KNOWN.get(u[:8])
    if k: return k
    return u[:8] + ("*" if u in coh else "")

# ------------------------------------------------------------------ report
def load_notes():
    if os.path.exists(NOTES):
        try: return json.load(open(NOTES))
        except Exception as e: print(f"run_notes.json unreadable: {e}", file=sys.stderr)
    return {}

def config_of(rs, L, notes):
    c = {}
    c["engine build"] = notes.get("engine", "?")
    c["model / tier"] = f"{rs.get('model', '?')} {rs.get('tier', '?')} (score >= {rs.get('thr', 0):.4f})"
    c["size (normal)"] = f"{rs.get('spend', 0) / 1e9:.2f} SOL"
    if rs.get("devs"):
        c["dev list"] = f"{len(rs['devs'])} dev ({', '.join(d[:8] for d in rs['devs'])}): tier {rs.get('dev_tier')} (score >= {rs.get('thr_dev', rs.get('thr', 0)):.4f}), size {rs.get('dev_spend', 0) / 1e9:.2f} SOL"
    else: c["dev list"] = "off"
    tp = rs.get("tp"); sl = rs.get("sl"); hold = rs.get("hold_slots")
    c["exit"] = f"take-profit {'off' if (tp is None or tp >= 99) else f'+{tp * 100:.0f}%'} / stop-loss −{(sl or 0) * 100:.0f}% / time limit {hold} slots (~{(hold or 0) * 0.212:.1f} s)"
    c["price guard"] = f"+{(rs.get('guard', 1) - 1) * 100:.0f}% over the post-dump price (pump error 6042 if exceeded); slot deadline = dump slot + 1"
    c["buy fee (priority)"] = notes.get("priority", "5M µL/CU × 100k CU limit = 0.0005 SOL per landed buy tx")
    c["sell fee"] = notes.get("sell_priority", "5M µL/CU × 120k CU limit (0.0006 SOL per landed sell tx)")
    for k, v in sorted(L["routes"].items()): c[f"route: {k} leaders"] = v
    if not L["routes"]: c["routes"] = notes.get("routes", "?")
    c["sell path"] = f"{L['sell_path'] or '?'} (retry also via {L['sell_fb'] or '?'})"
    c["near-leader gate"] = f"{L['near']} leaders (buys only when the dump's leader is on the near list)" if L["near"] else "off (every leader)"
    c["pre-send"] = ps_cfg(L)
    c["durable-nonce fan-out"] = f"ON, {L['nonce_on']} nonce accounts (one copy per path, one tip each)" if L["nonce_on"] else "off (one tx to every path, every path's tip in it)"
    c["backup RPC"] = L["fallback"] or "?"
    c["holder-reward tokens"] = "allowed" if rs.get("allow_holder") else "skipped"
    c["limits"] = f"max {rs.get('max_buys')} fills, {rs.get('max_inflight')} open at a time, {rs.get('minutes')} min, loss cap {rs.get('loss_cap', 0) / 1e9:.3f} SOL"
    return c

def md_table(rows, head):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for r in rows: out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)

def analyse(region, run, chain, notes_all, coh):
    R = REG[region]; base = f"{DATA}/{region}/runs/{R['tag']}{run}"
    if not os.path.exists(base + ".jsonl"): return None
    wallet = R["wallet"]
    logs = split_log(base + ".log") if os.path.exists(base + ".log") else []
    js = split_jsonl(base + ".jsonl")
    parsed = [parse_log(s) for s in logs]
    real = [p for p in parsed if p["live_line"]]
    refused = [p for p in parsed if not p["live_line"]]
    sessions = []
    for i, ev in enumerate(js):
        L = real[i] if i < len(real) else parse_log([])
        S = build_trades(ev, wallet); S["L"] = L; sessions.append(S)
    # budget entries
    budget = []
    bp = f"{DATA}/{region}/{R['budget']}"
    if os.path.exists(bp):
        budget = [b for b in json.load(open(bp)).get("runs", []) if b.get("run") == run]
    notes = notes_all.get(f"{region}-{run}", {})
    # chain prefetch: landed buys, failed buys, sells
    sigs = []
    for S in sessions:
        for tr in S["fires"]:
            c = tr["close"] or {}
            if tr["land"] or tr["failed"] or (c.get("result") == "buy_failed"):
                sigs.append((tr["land"] or tr["failed"] or {}).get("sig") or c.get("buy_sig"))
            for x in (c.get("sell_sigs") or []):
                if isinstance(x, list) and len(x) > 1 and x[1]: sigs.append(x[0])
            for s_ in tr["sells"]: sigs.append(s_.get("sig"))
    chain.prefetch(list(dict.fromkeys(s for s in sigs if s)), wallet)
    return dict(region=region, run=run, R=R, sessions=sessions, refused=refused, budget=budget, notes=notes, wallet=wallet, base=base)

def trade_rows(A, chain, coh):
    """flatten every fire of every session into one dict per trade"""
    rows = []; wallet = A["wallet"]
    for si, S in enumerate(A["sessions"]):
        real = collections.defaultdict(list)
        for m, p, src in S["L"]["realized"]: real[m].append(p)
        for tr in S["fires"]:
            f = tr["fire"]; c = tr["close"] or {}; pk = tr["pick"]; feats = pk.get("feats") or []
            res = classify(tr)
            land_sig = (tr["land"] or tr["failed"] or {}).get("sig") or (c.get("buy_sig") if res in ("filled", "guard", "failed") else None)
            var = (tr["land"] or tr["failed"] or c).get("variant") or {}
            ch_b = chain.tx(land_sig, wallet) if land_sig and res != "not landed" else None
            sell_sigs = [x[0] for x in (c.get("sell_sigs") or []) if isinstance(x, list) and len(x) > 1 and x[1]] or [s_.get("sig") for s_ in tr["sells"] if s_.get("sig")]
            sell_tips = sum(x[2] for x in (c.get("sell_sigs") or []) if isinstance(x, list) and len(x) > 2 and x[1] and isinstance(x[2], int))
            ch_s = [chain.tx(s_, wallet) for s_ in dict.fromkeys(sell_sigs)]
            ch_s = [x for x in ch_s if x]
            realized = real[f["mint"]].pop(0) if (res == "filled" and real.get(f["mint"])) else None
            chain_pnl = None
            if res == "filled" and ch_b: chain_pnl = (ch_b["delta"] + sum(x["delta"] for x in ch_s)) / 1e9
            elif res in ("guard", "failed") and ch_b: chain_pnl = ch_b["delta"] / 1e9
            pnl = realized if realized is not None else chain_pnl
            if pnl is None and res in ("guard", "failed"): pnl = -0.000505
            spend = f.get("spend", 0) / 1e9
            sol_in = (c.get("sol_in_curve") or (tr["land"] or {}).get("sol") or 0) / 1e9
            sol_out = (c.get("sol_out_curve") or sum(s_.get("sol", 0) for s_ in tr["sells"])) / 1e9
            buy_fee = (ch_b or {}).get("fee", (tr["land"] or {}).get("fee")) if res != "not landed" else 0
            sell_fee = sum(x["fee"] for x in ch_s) if ch_s else sum(s_.get("fee", 0) for s_ in tr["sells"])
            buy_tip = (var.get("tip") if var else f.get("tips", 0)) if res == "filled" else 0
            pump_buy = (spend - sol_in) if res == "filled" and sol_in else 0.0
            curve = (c.get("curve_pnl") or 0) / 1e9 if res == "filled" else None
            pump_sell = None
            if res == "filled" and pnl is not None and curve is not None:
                pump_sell = curve - pnl - pump_buy - ((buy_fee or 0) + (sell_fee or 0)) / 1e9 - ((buy_tip or 0) + sell_tips) / 1e9
            # rivals
            ahead = []
            if tr["land"]:
                us = (tr["land"]["slot"], tr["land"].get("idx", 0)); dpos = (f["slot"], c.get("dump_idx", -1))
                ahead = [e for e in tr["tape"] if dpos < (e["slot"], e["idx"]) < us and e.get("user") != wallet]
            elif tr["failed"]:
                t1 = tr["failed"].get("t", 0)
                ahead = [e for e in tr["tape"] if f["t_dump_rx"] <= e.get("t", 0) <= t1 and e.get("user") != wallet]
            ab = [e for e in ahead if e.get("buy")]
            land_ms = (tr["land"] or {}).get("rx_ms_after_dump")
            if land_ms is None and tr["failed"] and tr["failed"].get("t"): land_ms = (tr["failed"]["t"] - f["t_dump_rx"]) / 1e6
            if tr["land"]: blk = tr["land"].get("slots_after_dump")
            elif tr["poll"] and tr["poll"].get("land_slot"): blk = tr["poll"]["land_slot"] - f["slot"]
            elif ch_b and ch_b.get("slot"): blk = ch_b["slot"] - f["slot"]
            else: blk = None
            tm = tr["timing"] or {}
            rows.append(dict(
                session=si, t=f["t_fire"], mint=f["mint"], spend=spend, dev=bool(f.get("dev")), score=pk.get("score", c.get("score")),
                age=pk.get("age", feats[0] if feats else None), dump_sol=feats[1] if len(feats) > 1 else None, drop=feats[2] if len(feats) > 2 else None,
                leader=f.get("leader", ""), client=f.get("client", "?"), kind=KIND.get(f.get("client", ""), f.get("client") or "?"), route=f.get("route", ""),
                paths=[w.get("path") for w in f.get("writes", []) if w.get("st") == "written"] or pk.get("paths") or [], res=res, land_sig=land_sig, dump_sig=f.get("dump_sig"),
                sell_sigs=list(dict.fromkeys(sell_sigs)), landed_path="+".join(var.get("paths", [])) if var else None,
                blk=blk, land_ms=land_ms, idx=(tr["land"] or {}).get("idx"), dump_idx=c.get("dump_idx"),
                exit=c.get("exit_why"), held=c.get("held_s"), exit_value=c.get("exit_value"), curve=curve, pnl=pnl, realized_src="engine (tx)" if realized is not None else ("chain" if chain_pnl is not None else "est."),
                buy_fee=buy_fee, sell_fee=sell_fee, buy_tip=buy_tip, sell_tip=sell_tips, pump_buy=pump_buy, pump_sell=pump_sell,
                n_sells=len(sell_sigs), cu_buy=(ch_b or {}).get("cu"), decision_us=f.get("decision_us"),
                reaction=tm.get("reaction_ms"), exec_lag=tm.get("exec_lag_ms"), seen=tm.get("fire_to_seen_ms"),
                ahead_buys=len(ab), ahead_sol=sum(e.get("sol", 0) for e in ab) / 1e9, ahead_who=[e.get("user", "") for e in ab],
                tips_sent=f.get("tips", 0), nonce=bool(f.get("nonce")), err=c.get("err"),
                result=c.get("result")))
    return rows

def render(A, rows, prevA, prev_rows, coh):
    R = A["R"]; N = A["notes"]; run = A["run"]; region = A["region"]
    S0 = A["sessions"][-1] if A["sessions"] else None
    # pick the session with trades for config (else the last)
    trade_sess = [S for S in A["sessions"] if S["fires"]]
    S = trade_sess[-1] if trade_sess else S0
    rs = S["run_start"] if S else {}
    L = S["L"] if S else parse_log([])
    cfg = config_of(rs, L, N)
    out = []
    W = out.append
    fills = [r for r in rows if r["res"] == "filled"]; guard = [r for r in rows if r["res"] == "guard"]
    other_fail = [r for r in rows if r["res"] == "failed"]; nl = [r for r in rows if r["res"] == "not landed"]
    total_reactive = sum(r["pnl"] or 0 for r in rows)
    fill_pnl = [r["pnl"] for r in fills if r["pnl"] is not None]
    wins = [x for x in fill_pnl if x > 0]
    # pre-send live: its fills' chain P&L + account rent back − its failed tries' fees (not in `rows`: those are the reactive bot's buys)
    PS = [ps_session(S_) for S_ in A["sessions"]]
    ps_on = any(p["active"] for p in PS)
    ps_pos = [x for p in PS for x in p["positions"]]
    ps_fills = sum(p["fills"] for p in PS); ps_wins = sum(p["wins"] for p in PS)
    ps_realized = sum(p["realized"] for p in PS); ps_rent = sum(p["rent"] for p in PS); ps_fees = sum(p["fees"] for p in PS)
    ps_net = ps_realized + ps_rent - ps_fees
    total = total_reactive + ps_net
    starts = [S_["run_start"]["t"] for S_ in A["sessions"]]
    ends = [(S_["run_end"] or {}).get("t") for S_ in A["sessions"]]
    t0 = min(starts) if starts else None; t1 = max([e for e in ends if e] or [0]) or None
    b_first = A["budget"][0] if A["budget"] else None; b_last = A["budget"][-1] if A["budget"] else None
    bal0 = b_first.get("start_balance") / 1e9 if b_first and b_first.get("start_balance") else None
    bal1 = b_last.get("end_balance") / 1e9 if b_last and b_last.get("end_balance") else None
    title = N.get("title", "")
    W(f"# {R['name']} run {run} — dip bot run report")
    W("")
    W(f"*{title}*" if title else "")
    W("")
    if N.get("verdict"): W(f"> **Verdict:** {N['verdict']}"); W("")
    # ---------------- 1 summary
    W("## 1. Summary")
    dur = None
    if t0 and t1: dur = (t1 - t0) / 1e9 / 60
    end_how = N.get("ended") or ("kill switch (run loss cap reached)" if L.get("kill") else
                                 (("stopped with Ctrl+C (SIGINT)" if "SIGINT" in (L.get("signal") or "") else "time limit / max trades") if L.get("done") else "?"))
    srows = [
        ("Result (chain, after every cost)", f"**{sol(total)} SOL**" + (f" (wallet {bal0:.4f} → {bal1:.4f}, Δ {bal1 - bal0:+.4f})" if bal0 is not None and bal1 is not None else "")),
        ("Started (PKT)", pkt(t0, "%Y-%m-%d %H:%M:%S") if t0 else "?"),
        ("Ended (PKT)", (pkt(t1, "%Y-%m-%d %H:%M:%S") if t1 else "?") + f" — {end_how}"),
        ("Ran for", (f"{int(dur // 60)} h {int(dur % 60):02d} min" if dur is not None else "?") + (f" of {rs.get('minutes')} min planned" if rs.get("minutes") else "")),
        ("First / last buy (PKT)", (f"{pkt(min(r['t'] for r in rows))} / {pkt(max(r['t'] for r in rows))}" if rows else "no buys")),
        ("Server / wallet", f"{R['server']} / `{A['wallet'][:8]}…`"),
        ("Buys sent", f"{len(rows)} → **{len(fills)} filled**, {len(guard)} failed on the +5% guard" + (f", {len(other_fail)} failed (other)" if other_fail else "") + (f", {len(nl)} never landed" if nl else "")),
        ("Fill rate", f1(100 * len(fills) / len(rows), 0, "%") if rows else "–"),
        ("Wins / losses (fills)", f"{len(wins)} / {len(fill_pnl) - len(wins)}" + (f" (win rate {100 * len(wins) / len(fill_pnl):.0f}%)" if fill_pnl else "")),
        ("Per filled buy", (f"avg {sol(sum(fill_pnl) / len(fill_pnl))}, median {sol(st.median(fill_pnl))} SOL" if fill_pnl else "–")),
        ("Fills only / failed buys only", f"{sol(sum(fill_pnl))} / {sol(sum(r['pnl'] or 0 for r in guard + other_fail))} SOL"),
        *([("Reactive bot / pre-send live", f"{sol(total_reactive)} / {sol(ps_net)} SOL (pre-send: {ps_fills} fills, realized {sol(ps_realized)}, "
                                            + (f"rent back {sol(ps_rent)}, " if ps_rent else "")
                                            + f"failed-attempt fees {sol(-ps_fees if ps_fees else 0.0)}, {ps_wins} wins; see section 4b)")] if ps_on else []),
    ]
    if fills:
        best = max(fills, key=lambda r: r["pnl"] or -9); worst = min(fills, key=lambda r: r["pnl"] or 9)
        srows.append(("Best / worst trade", f"{best['mint'][:6]} {sol(best['pnl'])} / {worst['mint'][:6]} {sol(worst['pnl'])}"))
        lm = [r["land_ms"] for r in fills]; same = sum(1 for r in fills if r["blk"] == 0)
        srows.append(("Fill landing", f"median {f1(med(lm), 0)} ms after the dump (seen on our feed); {same} of {len(fills)} in the dump's own block"))
    W(md_table(srows, ["", ""]))
    W("")
    if N.get("summary"): W(N["summary"]); W("")
    # ---------------- 2 setup
    W("## 2. Setup")
    W(md_table([(k, v) for k, v in cfg.items()], ["Setting", "This run"]))
    W("")
    if N.get("setup_notes"):
        for x in N["setup_notes"]: W(f"- {x}")
        W("")
    # ---------------- 3 what changed
    W("## 3. What changed from the previous run")
    if prevA:
        PSp = [S_ for S_ in prevA["sessions"] if S_["fires"]] or prevA["sessions"]
        prs = PSp[-1]["run_start"] if PSp else {}; pL = PSp[-1]["L"] if PSp else parse_log([])
        pcfg = config_of(prs, pL, prevA["notes"])
        diff = [(k, pcfg.get(k, "–"), v) for k, v in cfg.items() if pcfg.get(k) != v]
        W(f"Compared with **{prevA['R']['name']} run {prevA['run']}**:")
        W("")
        W(md_table(diff, ["Setting", f"{prevA['R']['short']} run {prevA['run']}", f"{R['short']} run {run}"]) if diff else "- no setting changed")
    else:
        W("- first run of this kind (nothing to compare)")
    W("")
    for x in N.get("changes", []): W(f"- {x}")
    if N.get("changes"): W("")
    # ---------------- 4 timeline
    W("## 4. Timeline (PKT)")
    tl = []
    short_b = [b for b in A["budget"] if b.get("t_end") and b["t_end"] - b["t_start"] < 60 and b.get("end_balance") == b.get("start_balance")]
    # a short start that is itself an engine session (restart within one log) is listed once, as that session
    eng_t = [S_["run_start"]["t"] / 1e9 for S_ in A["sessions"]]
    short_b = [b for b in short_b if not any(b["t_start"] <= t_ <= b["t_end"] for t_ in eng_t)]
    for i, p in enumerate(PS):
        for s_ in p["stop"]:
            if s_.get("why") not in ("run_end", "run_stopping") and s_.get("t"):
                tl.append((pkt(s_["t"]), f"pre-send live (session #{i + 1}) stopped: {s_.get('why')} — {s_.get('fills')} fills, failed-try fees "
                                         f"{(s_.get('fees') or 0) / 1e9:.4f} SOL; no new pre-send tries (the reactive bot kept running)"))
    if not N.get("events") or not any("refused" in x for _, x in N.get("events", [])):
        ref = [p for p in A["refused"] if p["errors"]]
        for i, p in enumerate(ref):
            t_ = pkt(short_b[i]["t_start"] * 1e9) if i < len(short_b) else "?"
            tl.append((t_, f"start refused: `{p['errors'][0][:150]}` (nothing sent)"))
        for b in short_b[len(ref):]:
            tl.append((pkt(b["t_start"] * 1e9), "start ended within seconds (no trades)"))
    for i, S_ in enumerate(A["sessions"]):
        rs_ = S_["run_start"]; re_ = S_["run_end"] or {}
        tl.append((pkt(rs_["t"]), f"engine start #{i + 1} (session with {len(S_['fires'])} buys)"))
        if re_: tl.append((pkt(re_["t"]), f"engine end #{i + 1}: {(S_['L'].get('signal') or 'run end').replace('SIGNAL ', '')[:90]}"))
    for r in rows:
        if r["res"] == "filled" and r["pnl"] is not None and abs(r["pnl"]) >= 0.05:
            tl.append((pkt(r["t"]), f"{'big win' if r['pnl'] > 0 else 'big loss'}: {r['mint'][:6]} {sol(r['pnl'])} SOL ({r['exit']})"))
    for t_, x in N.get("events", []): tl.append((t_, x))
    # sort by real time: "HH:MM[:SS]" strings are placed on the run's first day, or the next day when they fall before the start
    d0 = dt.datetime.fromtimestamp((t0 or 0) / 1e9, dt.timezone(dt.timedelta(hours=5))) if t0 else None
    def key(item):
        m = re.match(r"~?(\d{1,2}):(\d{2})(?::(\d{2}))?", item[0] or "")
        if not (m and d0): return dt.datetime.max.replace(tzinfo=dt.timezone.utc)
        x = d0.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=int(m.group(3) or 0), microsecond=0)
        if x < d0 - dt.timedelta(hours=1): x += dt.timedelta(days=1)
        return x
    tl.sort(key=key)
    for t_, x in tl: W(f"- **{t_}** {x}")
    W("")
    # ---------------- 4b pre-send live (its own path; sections 5–11 cover only the reactive bot)
    if ps_on:
        W("## 4b. Pre-send live (pre-placed buys) — separate from the reactive bot")
        W("Buys pre-sent after a big whale buy, before any dump. **Not included in sections 5–11**, which cover only the reactive dip bot. "
          "Realized = the engine's PRESEND LIVE REALIZED records (chain txs of each buy and sell; the buy pays the token-account rent). "
          "Rent back = that rent returned when the engine closed each pre-send account after the exit (dip19+; before dip19 the sell closed it and "
          "the refund sat inside realized). Failed tries = fees of tries that landed and failed (6042 price, deadline, …). Net = realized + rent back − failed tries.")
        W("")
        srows_ = []
        for i, p in enumerate(PS):
            if not (p["active"] or p["live_line"]): continue
            stop = ", ".join(f"{s_.get('why')}" + (f" {pkt(s_['t'], '%H:%M')}" if s_.get("t") and s_.get("why") not in ("run_end", "run_stopping") else "") for s_ in p["stop"]) or "–"
            cfg_ = re.search(r"([0-9.]+) SOL, limit", p["live_line"] or ""); cap_ = re.search(r"caps: (\d+) fills, fees ([0-9.]+)", p["live_line"] or "")
            srows_.append((f"#{i + 1}", pkt(p["t0"], "%m-%d %H:%M") if p["t0"] else "?",
                           (f"{float(cfg_.group(1)):.2f}" if cfg_ else "?") + (f" / {cap_.group(1)} / {float(cap_.group(2)):.2f}" if cap_ else ""),
                           f"{p['sent']:,}" + (f" (+{(A['sessions'][i].get('ps') or {}).get('dry', 0):,} dry)" if (A['sessions'][i].get('ps') or {}).get('dry') else ""),
                           p["fills"], p["wins"], sol(p["realized"]), sol(p["rent"]), sol(-p["fees"] if p["fees"] else 0.0), f"**{sol(p['net'])}**", stop))
        if len(srows_) > 1:
            srows_.append(("**all**", "", "", f"{sum(p['sent'] for p in PS):,}", ps_fills, ps_wins, sol(ps_realized), sol(ps_rent), sol(-ps_fees), f"**{sol(ps_net)}**", ""))
        W(md_table(srows_, ["Session", "Started", "Size / fill cap / fee cap", "Tries sent", "Fills", "Wins", "Realized", "Rent back", "Failed tries", "Net", "Stopped"]))
        W("")
        res_ = collections.Counter()
        for p in PS: res_.update(p["res"])
        if res_:
            W("**Try results (as seen on our feed):** " + ", ".join(f"{k} {v:,}" for k, v in res_.most_common()) + ".")
            W("")
        unseen = sum(p["unseen"] for p in PS)
        if unseen:
            lam = max([p["fail_lamports"] for p in PS] or [5120])
            W(f"Tries never seen on our feed: {unseen:,}. If they landed and failed they cost up to {unseen * lam / 1e9:.4f} SOL in fees that are **not** in "
              f"the failed-try total above ({lam:,} lamports each; inferred, the engine does not see them).")
            W("")
        if ps_pos:
            exs = collections.OrderedDict()
            for x in sorted(ps_pos, key=lambda x: x["exit"] or "?"): exs.setdefault(x["exit"] or "?", []).append(x)
            W("**By exit reason:**"); W("")
            W(md_table([(k, len(v), sum(1 for x in v if (x["pnl"] or 0) > 0), sol(sum(x["pnl"] or 0 for x in v)), sol(sum(x["pnl"] or 0 for x in v) / len(v)),
                         f1(med([x["held"] for x in v]), 1, " s")) for k, v in sorted(exs.items(), key=lambda kv: -len(kv[1]))],
                       ["Exit", "Fills", "Wins", "Realized SOL", "Per fill", "Median hold"]))
            W("")
            kd = collections.defaultdict(list)
            for x in ps_pos: kd[x["kind"]].append(x)
            W("**By leader type (the slot leader where the fill landed):**"); W("")
            W(md_table([(k, len(v), sum(1 for x in v if (x["pnl"] or 0) > 0), sol(sum(x["pnl"] or 0 for x in v)), sol(sum(x["pnl"] or 0 for x in v) / len(v)))
                        for k, v in sorted(kd.items(), key=lambda kv: -len(kv[1]))], ["Leader type", "Fills", "Wins", "Realized SOL", "Per fill"]))
            W("")
            hr = collections.defaultdict(list)
            for x in ps_pos: hr[pkt(x["t"], "%m-%d %H:00")].append(x)
            if len(hr) > 1:
                W("**By hour (PKT):**"); W("")
                W(md_table([(k, len(v), sum(1 for x in v if (x["pnl"] or 0) > 0), sol(sum(x["pnl"] or 0 for x in v)), sol(sum(x["pnl"] or 0 for x in v) / len(v)))
                            for k, v in sorted(hr.items())], ["Hour", "Fills", "Wins", "Realized SOL", "Per fill"]))
                W("")
            srt_ = sorted(ps_pos, key=lambda x: x["pnl"] or 0)
            W("**Best pre-send fills:** " + "; ".join(f"{x['mint'][:8]} {sol(x['pnl'])} ({x['kind']}, {x['exit']})" for x in srt_[::-1][:3]))
            W("")
            W("**Worst pre-send fills:** " + "; ".join(f"{x['mint'][:8]} {sol(x['pnl'])} ({x['kind']}, {x['exit']})" for x in srt_[:3]))
            W("")
        # end-of-run checks
        ck = []
        for i, p in enumerate(PS):
            if not p["active"]: continue
            if p["end_check"]: ck.append(f"session #{i + 1}: END CHECK {p['end_check']}" + (f" (per mint: {', '.join(f'{k} {v}' for k, v in p['end_actions'].items())})" if p["end_actions"] else ""))
            elif p["fills"]: ck.append(f"session #{i + 1}: no END CHECK line in the log (engine before dip19)")
            for h in p["held"]: ck.append(f"session #{i + 1}: end check skipped {h.get('mint', '')[:8]} ({h.get('skipped')}: the reactive bot had a position on that token, so its sell handled the account)")
            if p["after_exit"]: ck.append(f"session #{i + 1}: {p['after_exit']} fill(s) landed after the position's exit")
            pos_ = sum(1 for x in p["positions"] if x["exit"] != "?")
            if p["fills"] and pos_ and p["fills"] != pos_: ck.append(f"session #{i + 1}: {p['fills']} fills but {pos_} closed positions (a fill merged or left open — check the wallet)")
            for c in p["not_sold"]: ck.append(f"session #{i + 1}: {c.get('mint', '')[:8]} position {c.get('result')}")
            for a in p["ata_fail"]: ck.append(f"session #{i + 1}: account close failed for {a.get('mint', '')[:8]}")
            n_m = sum(x["merged"] for x in p["positions"]); n_l = sum(x["late"] for x in p["positions"])
            if n_m or n_l: ck.append(f"session #{i + 1}: merged fills {n_m}, late fills {n_l}")
        if ck:
            W("**End-of-run checks:**"); W("")
            for x in ck: W(f"- {x}")
            W("")
        if ps_pos and any(x["exit"] != "?" for x in ps_pos):
            W("**Every pre-send fill** (time = fill; whale = the trigger buy; P&L = realized, rent back not included):")
            W("")
            prow = []
            for i, x in enumerate(sorted(ps_pos, key=lambda x: x["t"] or 0), 1):
                links = [f"[buy](https://solscan.io/tx/{s_})" for s_ in x["buy_sigs"][:2]] + \
                        [f"[sell{j if len(x['sell_sigs']) > 1 else ''}](https://solscan.io/tx/{s_})" for j, s_ in enumerate(x["sell_sigs"], 1)] + \
                        ([f"[whale](https://solscan.io/tx/{x['trig_sig']})"] if x["trig_sig"] else [])
                whale = (f"{x['trig_pct']:.1f}% / {x['trig_sol']:.2f}" if x["trig_pct"] is not None and x["trig_sol"] is not None else "–")
                prow.append((i, pkt(x["t"]) if x["t"] else "?", f"[{x['mint'][:6]}](https://gmgn.ai/sol/token/{x['mint']})", whale,
                             "–" if x["after_trig"] is None else f"+{x['after_trig']}", f"{x['kind']} `{(x['leader'] or '')[:6]}`",
                             f"{x['exit'] or '–'}" + (f" {x['held']:.1f} s" if x["held"] is not None else ""),
                             f"**{sol(x['pnl'])}**", " ".join(links)))
            W(md_table(prow, ["#", "Time", "Token", "Whale % / SOL", "Slots after whale", "Leader", "Exit", "P&L SOL", "Links"]))
            W("")
    # ---------------- 5 funnel
    W("## 5. Funnel")
    d = sum((S_["run_end"] or {}).get("dumps", S_["dumps"]) for S_ in A["sessions"]); ie = sum((S_["run_end"] or {}).get("in_envelope", S_["dumps"]) for S_ in A["sessions"])
    pk_n = sum((S_["run_end"] or {}).get("picks", 0) for S_ in A["sessions"]) or sum(len(S_["picks"]) for S_ in A["sessions"])
    sk = collections.Counter()
    for S_ in A["sessions"]: sk.update(S_["skips"])
    sold = sum(1 for r in rows if r["result"] == "sold")
    W(md_table([
        ("Dumps the engine scored (≥2% sells it saw)", d), ("Inside the envelope (age / drop / since-buy / size)", ie or "–"),
        ("Picks (score above the threshold)", pk_n), ("Skipped", ", ".join(f"{k} {v}" for k, v in sk.most_common()) or "0"),
        ("Buys sent", len(rows)), ("Filled", len(fills)), ("Failed on the +5% guard", len(guard)),
        ("Failed (other)", len(other_fail)), ("Never landed", len(nl)), ("Sold (positions closed)", f"{sold} of {len(fills)}"),
    ], ["Step", "Count"]))
    W("")
    # ---------------- 6 every trade
    W("## 6. Every buy")
    W("Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.")
    W("")
    t1rows = []
    for i, r in enumerate(rows, 1):
        tok = f"[{r['mint'][:6]}](https://gmgn.ai/sol/token/{r['mint']})"
        res = {"filled": "filled", "guard": "guard fail", "failed": "failed", "not landed": "not landed"}.get(r["res"], r["res"])
        t1rows.append((i, pkt(r["t"]), tok, f"{r['spend']:.2f}{' dev' if r['dev'] else ''}", f1(r["score"], 2),
                       f"{f1(r['dump_sol'], 2)} / −{f1(r['drop'], 0)}%", f1(r["age"], 1, " s"), f"{r['kind']} `{r['leader'][:6]}`",
                       res, f"**{sol(r['pnl'])}**" if r["res"] == "filled" else sol(r["pnl"])))
    W(md_table(t1rows, ["#", "Time", "Token", "SOL", "Score", "Dump SOL / drop", "Age", "Leader", "Result", "P&L SOL"]))
    W("")
    W("How each buy landed and was sold:")
    W("")
    t2rows = []
    for i, r in enumerate(rows, 1):
        links = []
        if r["land_sig"]: links.append(f"[buy](https://solscan.io/tx/{r['land_sig']})")
        for j, s_ in enumerate(r["sell_sigs"], 1): links.append(f"[sell{j if len(r['sell_sigs']) > 1 else ''}](https://solscan.io/tx/{s_})")
        if r["dump_sig"]: links.append(f"[dump](https://solscan.io/tx/{r['dump_sig']})")
        blk = "–" if r["blk"] is None else ("same" if r["blk"] == 0 else f"+{r['blk']}")
        path = (f"**{r['landed_path']}** of " if r["landed_path"] else "") + "+".join(dict.fromkeys(p for p in (r["paths"] or []) if p))
        ex = f"{r['exit'] or '–'}" + (f" {r['held']:.1f} s" if r["held"] else "")
        t2rows.append((i, f1(r["land_ms"], 0), blk, r["ahead_buys"], path or "–", ex, f"{r['n_sells']}" if r["n_sells"] else "–", " ".join(links)))
    W(md_table(t2rows, ["#", "ms after dump (feed)", "Block", "Buys ahead", "Paths sent (landed copy)", "Exit", "Sell txs", "Links"]))
    W("")
    # ---------------- 7 breakdowns
    W("## 7. Breakdowns")
    def grp(key, label):
        g = collections.OrderedDict()
        for r in rows: g.setdefault(key(r), []).append(r)
        tb = []
        # hours in time order (an overnight run's 21:00 comes before its 00:00)
        for k, rr in sorted(g.items(), key=(lambda kv: min(r["t"] for r in kv[1])) if label.startswith("hour") else (lambda kv: -len(kv[1]))):
            fl = [r for r in rr if r["res"] == "filled"]; pp = [r["pnl"] for r in fl if r["pnl"] is not None]
            tb.append((k, len(rr), len(fl), f1(100 * len(fl) / len(rr), 0, "%"), sol(sum(r["pnl"] or 0 for r in rr)), sol(sum(pp) / len(pp)) if pp else "–",
                       f"{sum(1 for x in pp if x > 0)}/{len(pp)}"))
        W(f"**By {label}:**"); W("")
        W(md_table(tb, [label.capitalize(), "Buys", "Fills", "Fill rate", "P&L SOL", "Per fill", "Wins"])); W("")
    if rows:
        grp(lambda r: r["kind"], "leader type")
        grp(lambda r: "dev list" if r["dev"] else "normal", "size tier")
        grp(lambda r: ("same block" if r["blk"] == 0 else ("next block" if r["blk"] == 1 else ("2+ blocks" if r["blk"] else "not landed"))), "landing block")
        grp(lambda r: pkt(r["t"], "%H:00"), "hour (PKT)")
        ex = collections.OrderedDict()
        for r in fills: ex.setdefault(r["exit"] or "?", []).append(r)
        W("**By exit reason (fills):**"); W("")
        W(md_table([(k, len(v), sol(sum(r["pnl"] or 0 for r in v)), sol(sum(r["pnl"] or 0 for r in v) / len(v)), f1(med([r['held'] for r in v]), 1, " s"))
                    for k, v in ex.items()], ["Exit", "Fills", "P&L SOL", "Per fill", "Median hold"]))
        W("")
    # ---------------- 8 pnl leaders
    W("## 8. P&L leaders")
    if fills:
        srt = sorted(fills, key=lambda r: r["pnl"] or 0)
        W("**Best trades:** " + "; ".join(f"{r['mint'][:6]} {sol(r['pnl'])} ({r['kind']}, {r['exit']}, score {f1(r['score'], 2)})" for r in srt[::-1][:3]))
        W("")
        W("**Worst trades:** " + "; ".join(f"{r['mint'][:6]} {sol(r['pnl'])} ({r['kind']}, {r['exit']}, score {f1(r['score'], 2)})" for r in srt[:3]))
        W("")
    g = collections.defaultdict(list)
    for r in rows: g[(r["leader"], r["client"])].append(r)
    tb = []
    for (ld, cl), rr in sorted(g.items(), key=lambda kv: -sum(r["pnl"] or 0 for r in kv[1])):
        fl = [r for r in rr if r["res"] == "filled"]
        tb.append((f"`{ld[:8]}`", cl, len(rr), len(fl), sol(sum(r["pnl"] or 0 for r in rr))))
    W("**By slot leader (validator), best to worst:**"); W("")
    W(md_table(tb[:12] + ([("…", "", "", "", "")] if len(tb) > 24 else []) + (tb[-12:] if len(tb) > 24 else tb[12:24]),
               ["Leader", "Client", "Buys", "Fills", "P&L SOL"]) if tb else "- no buys")
    W("")
    # ---------------- 9 speed
    W("## 9. Speed and landing")
    def stat(v, nd=1): return f"{f1(med(v), nd)} (p25 {f1(pct(v, 0.25), nd)}, p75 {f1(pct(v, 0.75), nd)}, n {len([x for x in v if x is not None])})"
    W(md_table([
        ("Decision (dump seen → buy sent), µs", stat([r["decision_us"] for r in rows], 0)),
        ("Executed-feed lag behind first sighting, ms", stat([r["exec_lag"] for r in rows], 1)),
        ("Buy sent → our tx seen on the feed, ms", stat([r["seen"] for r in rows], 1)),
        ("Fills: our buy seen on the feed after the dump, ms", stat([r["land_ms"] for r in fills], 0)),
        ("Guard fails: our failed buy seen after the dump, ms", stat([r["land_ms"] for r in guard], 0)),
        ("Fills in the dump's own block", f"{sum(1 for r in fills if r['blk'] == 0)} of {len(fills)}"),
        ("Guard fails in the dump's own block", f"{sum(1 for r in guard if r['blk'] == 0)} of {len(guard)}"),
    ], ["Measure", "Median (p25, p75, n)"]))
    W("")
    if any(r["landed_path"] for r in rows):
        lp = collections.Counter(r["landed_path"] for r in rows if r["landed_path"] and r["res"] in ("filled", "guard", "failed"))
        W("**Which copy landed (nonce fan-out):** " + ", ".join(f"{k} {v}" for k, v in lp.most_common()))
        W("")
    acks = L["acks"]
    if acks:
        W("**Send-path answers (FAST-ACK lines):** " + ", ".join(f"{p} {n} (median ack {f1(med(L['ack_ms'][p]), 1)} ms" + (f", {L['ack_bad'][p]} errors" if L['ack_bad'][p] else "") + (f", {L['ack_429'][p]}×429" if L['ack_429'][p] else "") + ")" for p, n in acks.most_common()))
        W("")
    # ---------------- 10 competition
    W("## 10. Who got in ahead of us")
    W("Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). "
      "`*` = a wallet in the 462-wallet winner cohort.")
    W("")
    W(md_table([
        ("Fills: rival buys ahead (median)", f1(med([r["ahead_buys"] for r in fills]), 0)),
        ("Guard fails: rival buys ahead (median)", f1(med([r["ahead_buys"] for r in guard]), 0)),
        ("Guard fails: rival SOL ahead (median)", f1(med([r["ahead_sol"] for r in guard]), 2)),
    ], ["", ""]))
    W("")
    cnt = collections.Counter(); cnt_fail = collections.Counter()
    for r in rows:
        for u in set(r["ahead_who"]):
            cnt[u] += 1
            if r["res"] == "guard": cnt_fail[u] += 1
    if cnt:
        W(md_table([(known(u, coh), n, cnt_fail[u]) for u, n in cnt.most_common(12)], ["Wallet", "Ahead of us (buys)", "…of which on our guard fails"]))
        W("")
    # ---------------- 11 costs
    W("## 11. Costs")
    if fills:
        n = len(fills)
        bf = sum((r["buy_fee"] or 0) for r in fills) / 1e9; sf = sum((r["sell_fee"] or 0) for r in fills) / 1e9
        bt = sum((r["buy_tip"] or 0) for r in fills) / 1e9; stp = sum((r["sell_tip"] or 0) for r in fills) / 1e9
        pb = sum(r["pump_buy"] or 0 for r in fills); ps = sum(r["pump_sell"] or 0 for r in fills if r["pump_sell"] is not None)
        gf = -sum(r["pnl"] or 0 for r in guard + other_fail)
        cur = sum(r["curve"] or 0 for r in fills)
        W(md_table([
            ("Curve P&L of the fills (before any cost)", sol(cur)),
            ("Pump fee on buys", f"{pb:.4f} ({pb / n:.4f} per fill)"), ("Pump fee on sells (residual)", f"{ps:.4f} ({ps / n:.4f} per fill)"),
            ("Buy tx fees (base + priority)", f"{bf:.4f} ({bf / n:.5f} per fill)"), ("Buy tips", f"{bt:.4f} ({bt / n:.4f} per fill)"),
            ("Sell tx fees", f"{sf:.4f} ({sf / n:.5f} per fill)"), ("Sell tips", f"{stp:.4f} ({stp / n:.4f} per fill)"),
            ("Failed buys (tx fees)", f"{gf:.4f} ({len(guard + other_fail)} buys)"),
            ("**Result**", f"**{sol(total)}**"),
        ], ["Item", "SOL"]))
        W("")
        cu = [r["cu_buy"] for r in fills if r["cu_buy"]]
        if cu: W(f"Buy compute used (fills): median {med(cu):,.0f} CU, max {max(cu):,} CU (limit 100k)."); W("")
    else:
        W(f"No fills. Failed buys cost {-sum(r['pnl'] or 0 for r in rows):.4f} SOL in tx fees."); W("")
    # ---------------- 12 health / red flags
    W("## 12. Health checks and red flags")
    flags = []
    def F(level, text): flags.append((level, text))
    for p in A["refused"]:
        if p["errors"]: F("⚠️", f"start refused: {p['errors'][0][:160]}")
    for S_ in A["sessions"]:
        L_ = S_["L"]
        if L_["panics"]: F("🔴", f"engine panic: {L_['panics'][0]}")
        if L_["kill"]: F("🔴", f"kill switch: {L_['kill'][0]}")
        if L_["sell_issues"]: F("⚠️", f"{len(L_['sell_issues'])} sell issue line(s), e.g. `{L_['sell_issues'][0][:150]}`")
        if L_["poll_err"]: F("⚠️", f"{L_['poll_err']} POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)")
        for (nm, meth), r in sorted(L_["rpc"].items()):
            if r["to"]: F("⚠️", f"RPC {nm} {meth}: {r['to']} timeouts/transport errors (worst p99 {r['p99']:.0f} ms)")
            elif r["p99"] > 300: F("ℹ️", f"RPC {nm} {meth}: slow minutes (worst p99 {r['p99']:.0f} ms, max {r['mx']:.0f} ms)")
        if L_["runtime"]:
            w99 = max(x[1] for x in L_["runtime"]); wmx = max(x[2] for x in L_["runtime"])
            if w99 > 10 or wmx > 100: F("⚠️", f"engine stalls: runtime lag worst p99 {w99:.1f} ms, max {wmx:.1f} ms")
        for p, n in L_["ack_429"].items(): F("ℹ️", f"send path {p}: {n} × HTTP 429 (rate limited) on buys")
        for p, n in L_["ack_bad"].items():
            if n - L_["ack_429"].get(p, 0) > 0: F("ℹ️", f"send path {p}: {n - L_['ack_429'].get(p, 0)} non-200 answers")
        if L_["unhealthy"]: F("ℹ️", f"{len(L_['unhealthy'])} send-path health events (self-heal), e.g. `{L_['unhealthy'][0][:120]}`")
        for k, n in L_["nonce_issues"].items():
            if k != "NONCE-REUSE": F("⚠️", f"{k}: {n}")
            else: F("ℹ️", f"NONCE-REUSE (no copy landed, nonce kept): {n}")
        if L_["mismatch"]: F("🔴", f"{L_['mismatch']} FAST-VERIFY / nonce MISMATCH lines")
        if L_["harmonic_auth"] and "FAILED" in L_["harmonic_auth"]: F("ℹ️", f"Harmonic bundle auth {L_['harmonic_auth']}")
        if L_["telegram"]:
            m = re.search(r"dropped (\d+) failed (\d+)", L_["telegram"])
            if m and (int(m.group(1)) or int(m.group(2))): F("ℹ️", f"Telegram: {L_['telegram'][:120]}")
    for r in rows:
        if r["res"] == "filled" and r["result"] not in ("sold", None): F("🔴", f"{r['mint'][:6]}: position {r['result']} — check the wallet")
        if r["res"] == "filled" and r["pnl"] is not None and r["pnl"] <= -0.05: F("⚠️", f"big loss {r['mint'][:6]} {sol(r['pnl'])} ({r['exit']}, {r['kind']})")
        if r["res"] == "filled" and r["exit"] == "stop-loss" and r["curve"] is not None and r["spend"]:
            lossp = -r["curve"] / r["spend"] * 100
            slp = (rs.get("sl") or 0) * 100
            if lossp > slp + 5: F("⚠️", f"stop-loss slipped: {r['mint'][:6]} stop at −{slp:.0f}% but the curve loss was −{lossp:.0f}% (one big sell went through before ours)")
        if r["n_sells"] > 1: F("ℹ️", f"{r['mint'][:6]}: {r['n_sells']} sell txs landed (duplicate sell)")
        if r["blk"] is not None and r["blk"] >= 2: F("⚠️", f"{r['mint'][:6]}: landed {r['blk']} blocks after the dump")
        if r["res"] == "not landed": F("ℹ️", f"{r['mint'][:6]}: buy never landed (dropped by every path)")
    for i, p in enumerate(PS):
        if not p["active"]: continue
        m_ = re.search(r"(\d+) sold now, (\d+) empty account\(s\) closed, (\d+) held / (\d+) unreadable", p["end_check"] or "")
        if m_ and any(int(g) for g in m_.groups()): F("⚠️", f"pre-send END CHECK (session #{i + 1}) found work to do: {p['end_check']}")
        if p["not_sold"]: F("🔴", f"pre-send (session #{i + 1}): {len(p['not_sold'])} position(s) not sold — check the wallet")
        if p["ata_fail"]: F("⚠️", f"pre-send (session #{i + 1}): {len(p['ata_fail'])} token-account close(s) failed (rent not back)")
        if p["after_exit"]: F("⚠️", f"pre-send (session #{i + 1}): {p['after_exit']} fill(s) landed after the exit")
        pos_ = sum(1 for x in p["positions"] if x["exit"] != "?")
        if p["fills"] and pos_ and p["fills"] != pos_: F("⚠️", f"pre-send (session #{i + 1}): {p['fills']} fills but {pos_} closed positions")
    for x in ps_pos:
        if x["pnl"] is not None and x["pnl"] <= -0.1: F("⚠️", f"big pre-send loss {x['mint'][:6]} {sol(x['pnl'])} ({x['exit']}, {x['kind']})")
    bal_note = None
    if bal0 is not None and bal1 is not None:
        gap = (bal1 - bal0) - total
        unseen = sum(p["unseen"] for p in PS)
        bound = unseen * max([p["fail_lamports"] for p in PS] or [5120]) / 1e9
        if abs(gap) > 0.003 or (ps_on and abs(gap) > 0.0002):
            if unseen and gap < 0 and -gap <= bound + 0.0005:   # small and the right size: the unseen tries' fees
                bal_note = f"wallet change {bal1 - bal0:+.4f} vs trades {total:+.4f}: gap {gap:+.4f} SOL — about the fees of the {unseen:,} pre-send tries " \
                           f"never seen on our feed (up to {bound:.4f} SOL if they all landed and failed; inferred)"
            else:
                bal_note = f"wallet change {bal1 - bal0:+.4f} vs trades {total:+.4f}: gap {gap:+.4f} SOL (transfers / rent / unsold — see notes)" + \
                           (f"; pre-send tries never seen on our feed: {unseen:,} (up to {bound:.4f} SOL)" if unseen else "")
        if bal_note: F("ℹ️", bal_note)
    for x in N.get("red_flags", []): F(x[0] if isinstance(x, list) else "⚠️", x[1] if isinstance(x, list) else x)
    if not flags: W("- ✅ nothing flagged")
    seen = collections.OrderedDict()
    for lv, tx in flags: seen[(lv, tx)] = seen.get((lv, tx), 0) + 1
    for (lv, tx), k in seen.items(): W(f"- {lv} {tx}" + (f" (×{k})" if k > 1 else ""))
    W("")
    ok = []
    if rows and not any(r["res"] == "filled" and r["result"] not in ("sold", None) for r in rows):
        ok.append("every reactive fill was sold" if ps_on else "every filled position was sold")
    if ps_on and ps_pos and all(not p["not_sold"] and not p["after_exit"] and (not p["fills"] or p["fills"] == sum(1 for x in p["positions"] if x["exit"] != "?"))
                                for p in PS):
        ok.append("every pre-send fill was closed by a sell")
    if L.get("fast_verify"): ok.append(L["fast_verify"].replace("FAST: ", ""))
    if L.get("nonce_selftest"): ok.append("nonce self-test passed")
    if ok: W("Checks passed: " + "; ".join(ok) + "."); W("")
    # ---------------- 13 fixes
    W("## 13. Fixes and follow-ups")
    if N.get("fixes_after"):
        W("**Done after this run:**"); W("")
        for x in N["fixes_after"]: W(f"- {x}")
        W("")
    if N.get("next"):
        W("**Recommended / open:**"); W("")
        for x in ([N["next"]] if isinstance(N["next"], str) else N["next"]): W(f"- {x}")
        W("")
    if not N.get("fixes_after") and not N.get("next"): W("- none recorded"); W("")
    # ---------------- 14 data
    W("## 14. Data and how this report was made")
    W(f"- Engine records: `/root/prod/runs/{A['R']['tag']}{run}.jsonl`, log `.log` on {R['server']} (local copy `{A['base']}.*`).")
    W(f"- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; "
      "costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).")
    if ps_on:
        W("- Pre-send (section 4b): the jsonl presend_live_* records (fills, closes, REALIZED, account closes, stops, end checks) and "
          "presend_attempt_land (try results, failed-try fees); the log's PRESEND LIVE lines when a run has no such records.")
    W(f"- Engine sessions in this run: {len(A['sessions'])}" + (" (restarts appended to the same log, each with its own START BALANCE; every section sums them)"
                                                                if len(A["sessions"]) > 1 else "") + f"; refused starts: {sum(1 for p in A['refused'] if p['errors'])}.")
    W(f"- Generated by `ops/dip/report/make_run_report.py` at {dt.datetime.now(dt.timezone(dt.timedelta(hours=5))).strftime('%m-%d %H:%M')} PKT.")
    W("")
    return "\n".join(out), dict(region=region, run=run, total=total, fires=len(rows), fills=len(fills) + ps_fills, guard=len(guard),
                                wins=len(wins) + ps_wins,
                                t0=t0, t1=t1, bal0=bal0, bal1=bal1, title=title, verdict=N.get("verdict", ""))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region"); ap.add_argument("--run", type=int); ap.add_argument("--all", action="store_true")
    ap.add_argument("--no-chain", action="store_true"); ap.add_argument("--max-run", type=int, default=999)
    a = ap.parse_args()
    chain = Chain(not a.no_chain); notes = load_notes(); coh = set(json.load(open(COHORT))) if os.path.exists(COHORT) else set()
    os.makedirs(OUT, exist_ok=True)
    todo = []
    if a.all:
        for region in ("fra", "ams"):
            for n in range(1, a.max_run + 1):
                if os.path.exists(f"{DATA}/{region}/runs/{REG[region]['tag']}{n}.jsonl"): todo.append((region, n))
    else: todo = [(a.region, a.run)]
    index = []; cacheA = {}
    def getA(region, n):
        if (region, n) not in cacheA: cacheA[(region, n)] = analyse(region, n, chain, notes, coh)
        return cacheA[(region, n)]
    for region, n in todo:
        A = getA(region, n)
        if not A: continue
        rows = trade_rows(A, chain, coh)
        # previous run: same region, the closest lower run number with trades
        prevA = None; prev_rows = None
        pn = notes.get(f"{region}-{n}", {}).get("previous")
        cand = [tuple(pn)] if pn else [(region, k) for k in range(n - 1, 0, -1)]
        for reg2, k in cand:
            P = getA(reg2, k)
            if P and any(S["fires"] for S in P["sessions"]): prevA = P; break
        text, summ = render(A, rows, prevA, prev_rows, coh)
        fn = f"{OUT}/{REG[region]['short']}_run{n:02d}.md"
        open(fn, "w").write(text)
        index.append(summ); print(f"wrote {fn}: {summ['fires']} buys, {summ['fills']} fills, {summ['total']:+.4f} SOL", flush=True)
    chain.save()
    if a.all and index:
        lines = ["# Dip bot runs — index", "", "Each run has its own standard report (link). P&L = chain, after every cost, incl. the pre-send live probe (fills + account rent back − failed-attempt fees). Fills / Wins include pre-send fills. Times PKT.", "",
                 "| Region | Run | Started (PKT) | Ended (PKT) | Ran for | Buys | Fills | Wins | P&L SOL | What it tested |", "|---|---|---|---|---|---|---|---|---|---|"]
        for s in sorted(index, key=lambda s: (s["t0"] or 0)):
            st_ = pkt(s["t0"], "%m-%d %H:%M") if s["t0"] else "?"; en_ = pkt(s["t1"], "%m-%d %H:%M") if s["t1"] else "?"
            mins = (s["t1"] - s["t0"]) / 6e10 if s["t0"] and s["t1"] else None
            ran = f"{int(mins // 60)} h {int(mins % 60):02d} m" if mins is not None else "?"
            lines.append(f"| {REG[s['region']]['name']} | [{s['run']}]({REG[s['region']]['short']}_run{s['run']:02d}.md) | {st_} | {en_} | {ran} | {s['fires']} | {s['fills']} | {s['wins']} | **{s['total']:+.4f}** | {s['title']} |")
        tot = sum(s["total"] for s in index)
        lines += ["", f"**All runs: {tot:+.4f} SOL** over {sum(s['fills'] for s in index)} fills and {sum(s['fires'] for s in index)} buys sent."]
        open(f"{OUT}/INDEX.md", "w").write("\n".join(lines) + "\n")
        print(f"wrote {OUT}/INDEX.md")

if __name__ == "__main__":
    main()
