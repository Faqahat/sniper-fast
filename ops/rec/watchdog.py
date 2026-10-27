#!/usr/bin/env python3
# sniper-rec WATCHDOG: one pass per minute (systemd timer sniper-rec-watch.timer). Checks the host recorder and alerts.
# Checks: recorder process / service alive; status + newest chunk age; lag vs the chain tip (one getSlot per minute on
# the public Solana RPC, never Constant-K / SHYFT); gap holes (consecutive failed slots > 30 s, slot jumps, run.json
# holes); failed / skipped slots per hour; disk %; archive failures + backlog; day rotation + finalization.
# Alerts: logs/alerts.log + state/watch.json (read by the session) + Telegram (same bot + chat as the engines; token
# from the root-only env, never printed). De-duplicated: sent when an alert starts, repeated every REC_ALERT_REPEAT_H
# hours while it stays, and a RECOVERED message when it clears. A HOLD file written by an operator (by=agent/owner)
# silences the recorder checks; a HOLD written by the recorder itself (limit trip) or the overlap guard is an alert.
#   watchdog.py              one pass       watchdog.py --test-alert     send ONE test message (once; --force to repeat)
import os, sys, json, time, glob, shutil, subprocess, urllib.request, urllib.error, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reclib as R

WS = os.path.join(R.STATE, "watch.json"); ALOG = "alerts"
SLOT_S = 0.4 if False else 0.213
DOWN_S = float(os.environ.get("REC_ALERT_DOWN_S", "120")); LAG_S = float(os.environ.get("REC_ALERT_LAG_S", "300"))
HOLE_S = float(os.environ.get("REC_ALERT_HOLE_S", "30")); DISK = float(os.environ.get("REC_ALERT_DISK_PCT", "85"))
REPEAT_H = float(os.environ.get("REC_ALERT_REPEAT_H", "6")); EXPECT = os.environ.get("REC_EXPECT_RUNNING", "0") == "1"
TIP_URLS = [u for u in os.environ.get("REC_TIP_URLS", "https://api.mainnet-beta.solana.com").split(",") if u]

def tg(text):
    if os.environ.get("REC_TG", "on") != "on": return "disabled"
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat: return "no token in env"
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request("https://api.telegram.org/bot" + tok + "/sendMessage", data=data), timeout=20)
        return "sent" if json.loads(r.read()).get("ok") else "telegram said not ok"
    except urllib.error.HTTPError as e: return f"telegram HTTP {e.code}"
    except Exception as e: return f"telegram error {type(e).__name__}"          # never str(e): it can contain the URL

def hm(ts=None): return time.strftime("%H:%M", time.gmtime((ts or time.time()) + R.PKT)) + " PKT"

def tip_slot():
    for u in TIP_URLS:
        try:
            d = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getSlot", "params": [{"commitment": "confirmed"}]}).encode()
            r = json.loads(urllib.request.urlopen(urllib.request.Request(u, data=d, headers={"content-type": "application/json", "user-agent": "sniper-rec-watchdog/1"}), timeout=10).read())
            if isinstance(r.get("result"), int): return r["result"], urllib.parse.urlparse(u).hostname
        except Exception: continue
    return None, None

def tail_slots(path, offset):
    """new slots.tsv lines since offset -> (lines, new offset)"""
    if not os.path.exists(path): return [], 0
    size = os.path.getsize(path)
    if offset > size: offset = 0
    with open(path) as f:
        f.seek(offset); data = f.read()
    cut = data.rfind("\n") + 1
    return [l.split("\t") for l in data[:cut].splitlines()], offset + len(data[:cut].encode())

def one_pass():
    now = time.time(); W = R.jload(WS) or {}; alerts = W.setdefault("alerts", {}); found = {}; info = {}
    W.setdefault("slots", {})
    def alert(key, msg): found[key] = msg
    hold = R.jload(os.path.join(R.ROOT, "HOLD"))
    svc = subprocess.run(["systemctl", "is-active", "sniper-rec.service"], capture_output=True, text=True).stdout.strip()
    s = R.jload(os.path.join(R.STATE, "recorder.json")) or {}
    alive = False
    try: os.kill(int(s.get("pid")), 0); alive = s.get("pid") is not None
    except Exception: pass
    info.update(service=svc, alive=alive, hold=(hold or {}).get("reason"), mode=s.get("mode"), day=s.get("day"))
    watch_rec = EXPECT and not (hold and hold.get("by") in ("agent", "owner", "maintenance"))
    if hold and hold.get("by") in ("recorder", "guard"):
        alert("hold", f"recorder STOPPED itself: {hold.get('reason')}")
    if watch_rec and not hold:
        if not alive or svc != "active":
            W.setdefault("down_since", now)
            if now - W["down_since"] > DOWN_S: alert("down", f"recorder DOWN since {hm(W['down_since'])} (service {svc})")
        else: W.pop("down_since", None)
        st_age = now - (s.get("now") or 0)
        cur = os.path.join(R.DAYS, s.get("day") or R.today(), "txs")
        newest = max((os.path.getmtime(p) for p in glob.glob(os.path.join(cur, "*.jsonl.gz"))), default=0)
        info.update(status_age_s=round(st_age), chunk_age_s=round(now - newest) if newest else None)
        if alive and st_age > 180: alert("stalled", f"recorder STALLED: status not updated for {st_age / 60:.0f} min")
        elif alive and newest and now - newest > 300: alert("stalled", f"recorder STALLED: newest chunk {(now - newest) / 60:.0f} min old")
        lbt = s.get("last_block_time"); lag = now - lbt if lbt else None
        tip, tip_host = tip_slot()
        tip_lag = (tip - s["last_slot"]) * SLOT_S if tip and s.get("last_slot") else None
        info.update(lag_s=round(lag) if lag else None, tip_lag_s=round(tip_lag) if tip_lag is not None else None, tip_from=tip_host)
        L = max(x for x in (lag, tip_lag) if x is not None) if (lag is not None or tip_lag is not None) else None
        if alive and L is not None and L > LAG_S: alert("lag", f"recorder LAG {L / 60:.1f} min behind the chain")
        # gaps: consecutive failed slots, slot jumps
        day = s.get("day")
        if day:
            p = os.path.join(R.DAYS, day, "slots.tsv"); key = day
            st = W["slots"].get(key) or {}; lines, off = tail_slots(p, st.get("off", 0))
            run_fail = st.get("run_fail", 0); prev = st.get("prev"); hist = st.get("hist", [])
            for x in lines:
                try: sl = int(x[0])
                except ValueError: continue
                if prev is not None and sl != prev + 1: alert("hole", f"slot JUMP {prev} -> {sl} ({(sl - prev - 1) * SLOT_S:.0f} s not recorded)")
                prev = sl
                if x[1] == "fail": run_fail += 1
                else: run_fail = 0
                if run_fail * SLOT_S > HOLE_S: alert("hole", f"GAP: {run_fail} consecutive failed slots (> {HOLE_S:.0f} s) up to slot {sl}")
                if x[1] in ("fail", "skip"): hist.append([now, x[1]])
            hist = [h for h in hist if now - h[0] < 3600]
            W["slots"] = {key: dict(off=off, run_fail=run_fail, prev=prev, hist=hist)}
            info.update(fails_1h=sum(1 for h in hist if h[1] == "fail"), skips_1h=sum(1 for h in hist if h[1] == "skip"))
            run = R.jload(os.path.join(R.DAYS, day, "run.json")) or {}
            if run.get("holes"): info["holes"] = run["holes"][-3:]
        # rotation / finalization
        t_pkt = time.gmtime(now + R.PKT); today = R.today()
        if t_pkt.tm_hour * 60 + t_pkt.tm_min >= 15 and alive and s.get("day") and s["day"] < today and (s.get("last_block_time") or 0) > R.day_start(today) + 60:
            alert("rotation", f"day ROTATION failed: still writing {s['day']} after 00:00 PKT")
        yday = R.pkt_day(R.day_start(today) - 3600); yrun = R.jload(os.path.join(R.DAYS, yday, "run.json"))
        if yrun and t_pkt.tm_hour >= 3:
            # the final pass is paced at Constant-K's heavy limit (1.8/s): ~50k mints take ~8 h, so it may run to ~09:00
            yst = R.jload(os.path.join(R.DAYS, yday, "status.json")) or {}; ph = str(yst.get("phase"))
            if ph != "DONE" and (t_pkt.tm_hour >= 14 or not ph.startswith("final")):
                alert("finalize", f"day {yday} not finalized (phase {ph}; expected: final pass started by 03:00, DONE by 14:00 PKT)")
            elif ph.startswith("final") and now - (yst.get("now") or now) > 3600:
                alert("finalize", f"day {yday} final pass stuck at {ph} for {(now - yst['now']) / 60:.0f} min")
    # disk
    du = shutil.disk_usage("/home/moiz"); pct = du.used / du.total * 100; info.update(disk_pct=round(pct, 1), disk_free_gb=round(du.free / 1e9))
    if pct >= DISK: alert("disk", f"DISK {pct:.0f}% used ({du.free / 1e9:.0f} GB free)")
    # archive
    arch = R.jload(os.path.join(R.STATE, "archive.json")) or {}
    if arch and arch.get("ok") is False: alert("archive", f"ARCHIVE failed: {'; '.join(arch.get('failures') or [])[:300]}")
    remote_ok = bool(os.environ.get("FTP_HOST")) or os.environ.get("REC_REMOTE", "ftp") != "ftp"
    c = R.cat_load(); cut = R.day_start(R.today()) - (R.HOST_KEEP_DAYS + 2) * 86400
    backlog = [d for d, e in c["days"].items() if e.get("kind") == "rec" and "host" in (e.get("where") or []) and not e.get("sample_every") and R.day_start(d) < cut]
    info.update(archive_backlog=len(backlog), remote_configured=remote_ok)
    if remote_ok and backlog: alert("backlog", f"ARCHIVE backlog: {len(backlog)} day(s) older than {R.HOST_KEEP_DAYS + 2} days still on the host")
    # de-dup + send
    sent = []
    for k, msg in found.items():
        a = alerts.get(k) or {}
        if not a.get("active"):
            alerts[k] = dict(active=True, since=now, last_sent=now, msg=msg); r = tg(f"🛰 rec: {msg} ({hm(now)})"); sent.append((k, r))
            R.log(ALOG, f"ALERT {k}: {msg} | telegram: {r}")
        else:
            a["msg"] = msg
            if now - a.get("last_sent", 0) > REPEAT_H * 3600:
                a["last_sent"] = now; r = tg(f"🛰 rec: still: {msg} (since {hm(a['since'])})"); sent.append((k, r)); R.log(ALOG, f"REPEAT {k}: {msg} | telegram: {r}")
    for k, a in alerts.items():
        if a.get("active") and k not in found:
            a.update(active=False, cleared=now); r = tg(f"🛰 rec: RECOVERED: {k} ({hm(now)}; was: {a.get('msg')})"); sent.append((k + " recovered", r))
            R.log(ALOG, f"RECOVERED {k} | telegram: {r}")
    W.update(t=now, pkt=R.pkt_str(now), info=info, active=sorted(k for k, a in alerts.items() if a.get("active")))
    R.jdump(WS, W)
    return W, sent

if __name__ == "__main__":
    if "--test-alert" in sys.argv:
        flag = os.path.join(R.STATE, "test_alert_sent")
        if os.path.exists(flag) and "--force" not in sys.argv:
            print("a test alert was already sent at", open(flag).read().strip(), "(use --force to send another)"); sys.exit(1)
        r = tg("🛰 rec: test alert from the host recorder (ignore)")
        print("test alert:", r); R.log(ALOG, f"TEST alert: {r}")
        if r == "sent": open(flag, "w").write(R.pkt_str(time.time()))
        sys.exit(0 if r == "sent" else 1)
    with R.lock("watchdog", wait=False):
        W, sent = one_pass()
    if "-v" in sys.argv: print(json.dumps(dict(info=W["info"], active=W["active"], sent=sent), indent=1))
