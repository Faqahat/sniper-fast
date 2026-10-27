#!/usr/bin/env python3
# Unit tests (stdlib unittest) for the host recorder's pure pieces. Run: python3 -I tests/test_unit.py
import os, sys, json, gzip, time, shutil, tempfile, unittest, threading, array, calendar
HERE = os.path.dirname(os.path.abspath(__file__)); REC = os.path.dirname(HERE); sys.path.insert(0, REC)
TMP = tempfile.mkdtemp(prefix="rec_unit_", dir=os.environ.get("TEST_WORK", "/home/moiz/sniper-data/rec/test"))
for k in list(os.environ):
    if k.startswith(("REC_", "SHYFT", "RMR", "CONSTANTK", "TELEGRAM", "FTP_")): os.environ.pop(k)
os.environ.update(REC_ROOT=TMP, REC_MODE="overlap", FAKE_URL="http://127.0.0.1:9/", REC_BLOCK_EPS="FAKE_URL", REC_RPC_EP="FAKE_URL")
import reclib as R
import recorder as REC_
import slim

class DayMath(unittest.TestCase):
    def test_midnight(self):
        for day in ("2026-10-27", "2026-12-31", "2027-01-01", "2028-02-29", "2026-03-29"):
            t = R.day_start(day)
            self.assertEqual(R.pkt_day(t), day); self.assertNotEqual(R.pkt_day(t - 1), day)
            self.assertEqual(time.strftime("%H:%M", time.gmtime(t)), "19:00")          # 00:00 PKT = 19:00 UTC, no DST
        self.assertEqual(R.next_day("2026-12-31"), "2027-01-01"); self.assertEqual(R.next_day("2028-02-28"), "2028-02-29")
        self.assertEqual(REC_.pkt_day(R.day_start("2026-10-28") - 0.001), "2026-10-27")
    def test_parse_when(self):
        self.assertEqual(R.parse_when("462055180"), ("slot", 462055180))
        self.assertEqual(R.parse_when("2026-10-27 16:40")[1], R.day_start("2026-10-27") + 16 * 3600 + 40 * 60)
        self.assertEqual(R.parse_when("1793100000")[0], "time")

class SlotsFile(unittest.TestCase):
    def test_last_line_truncates_partial(self):
        p = os.path.join(TMP, "slots.tsv"); open(p, "w").write("100\tok\t1\t5\t1\t0\t1.0\n101\tskip\t\t\t0\t0\t1.1\n102\tok\t1")
        self.assertEqual(REC_.last_line_slot(p), 101); self.assertTrue(open(p).read().endswith("1.1\n"))
    def test_stats(self):
        import rec as CLI
        p = os.path.join(TMP, "s2.tsv"); open(p, "w").write("".join(f"{s}\t{'fail' if s in (5, 6, 7) else 'ok'}\t1\t1\t0\t0\t1\n" for s in [1, 2, 3, 4, 5, 6, 7, 9, 10, 10]))
        st = CLI.slots_stats(p)
        self.assertFalse(st["contiguous"]); self.assertEqual(st["holes"], [[8, 8]]); self.assertEqual(st["dup_or_backwards"], 1); self.assertEqual(st["max_fail_run"], 3)

class Chunks(unittest.TestCase):
    def mk(self, day, recs, truncate=0):
        d = os.path.join(TMP, "days", day, "txs"); os.makedirs(d, exist_ok=True); p = os.path.join(d, "txs_1700000000.jsonl.gz")
        with gzip.open(p, "wb") as g:
            for r in recs: g.write((json.dumps(r, separators=(",", ":")) + "\n").encode())
        if truncate: b = open(p, "rb").read(); open(p, "wb").write(b[:-truncate])
        return p
    def test_repair_truncated_and_beyond(self):
        recs = [dict(s=s, i=i, bt=1700000000 + s, sig=f"x{s}_{i}") for s in range(10, 30) for i in range(3)]
        p = self.mk("2026-01-05", recs, truncate=7)                                # crash: no gzip trailer
        e = R.index_chunk(p); self.assertFalse(e["ok"])
        REC_.repair_chunks("2026-01-05", 20)
        got = [json.loads(l) for l in gzip.open(p, "rt")]
        self.assertTrue(all(r["s"] <= 20 for r in got)); self.assertEqual(len(got), 11 * 3)
        self.assertTrue(R.index_chunk(p)["ok"])
        self.assertTrue(os.listdir(os.path.join(TMP, "repair", "2026-01-05")))      # the original is kept
    def test_index_chunk(self):
        recs = [dict(s=s, i=0, bt=1700000000 + s, sig=str(s)) for s in range(5, 9)]
        e = R.index_chunk(self.mk("2026-01-06", recs))
        self.assertEqual((e["n"], e["slot"], e["bt"], e["ok"]), (4, [5, 8], [1700000005, 1700000008], True))

class Pacing(unittest.TestCase):
    def test_spacing(self):
        p = REC_.Pace(20.0); ts = []; lk = threading.Lock()
        def w():
            for _ in range(10):
                p.wait()
                with lk: ts.append(time.time())
        th = [threading.Thread(target=w) for _ in range(4)]; [t.start() for t in th]; [t.join() for t in th]
        ts.sort(); gaps = [b - a for a, b in zip(ts, ts[1:])]
        self.assertGreaterEqual(min(gaps), 0.05 - 0.002)
        self.assertTrue(all(sum(1 for x in ts if a <= x < a + 1.0) <= 20 for a in ts))   # never more than the cap in any 1-s window
    def test_limit_detection(self):
        self.assertTrue(REC_.LIMIT_RE.search("max usage reached")); self.assertTrue(REC_.LIMIT_RE.search("Too Many Requests"))
        self.assertTrue(REC_.LIMIT_RE.search("credits exhausted")); self.assertFalse(REC_.LIMIT_RE.search("Slot 123 was skipped"))

class Slim(unittest.TestCase):
    def test_roundtrip(self):
        rows = [(100 + j // 3, j % 3, j % 2, 1700000000 + j // 3, j % 2, 10 ** 9 + j, 5 * 10 ** 12 - j, 30 * 10 ** 9, 10 ** 15, 5000, 0 if j % 4 else 10 ** 6, j % 2,
                 f"Mint{j % 7}pump", f"User{j % 11}") for j in range(1000)]
        rows[500] = (50,) + rows[500][1:]                                          # a backwards slot (two-source day)
        p = os.path.join(TMP, "t.slim"); W = slim.Writer(p, "lzma"); slim.BLOCK = 300
        cols = [array.array(slim.COLS[j][1], [r[j] for r in rows]).tobytes() for j in range(slim.NI)]
        W.add(cols, [r[12] for r in rows], [r[13] for r in rows]); W.close(dict(day="x"))
        h, d = slim.load(p)
        names = [c[0] for c in slim.COLS]
        self.assertEqual(h["rows"], 1000)
        self.assertEqual([tuple(d[n][j] for n in names) for j in range(1000)], rows)

if __name__ == "__main__":
    try: unittest.main(verbosity=2)
    finally: shutil.rmtree(TMP, ignore_errors=True)
