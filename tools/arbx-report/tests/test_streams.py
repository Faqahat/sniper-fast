"""Readers: zstd frames (complete, truncated, multi-frame, skippable), headers and schema versions, rotation series,
idx_update merging, text logs, and the binary formats (accounts with XOR deltas and gaps, journal)."""
import io
import json
import os
import shutil
import struct
import subprocess
import unittest

from helpers import TmpDir, gen, write_jsonl

from arbx_report import solana, streams, zstd


class ZstdFrames(unittest.TestCase):
    def test_raw_roundtrip_and_multiframe(self):
        a, b = b"hello\n" * 1000, b"world\n" * 70000  # b spans several 128 KiB raw blocks
        data = zstd.compress_raw(a) + zstd.compress_raw(b) + zstd.compress_raw(b"")
        sc = zstd.scan(io.BytesIO(data), len(data))
        self.assertEqual(len(sc.frames), 3)
        self.assertTrue(sc.only_raw)
        self.assertEqual(sc.truncated_tail_bytes, 0)
        self.assertEqual(zstd.decode_raw(data), a + b)

    def test_truncated_trailing_frame_is_ignored(self):
        a, b = b"line one\n" * 50, b"line two\n" * 50
        full = zstd.compress_raw(a) + zstd.compress_raw(b)
        cut = full[:-17]  # a writer in the middle of its second frame
        sc = zstd.scan(io.BytesIO(cut), len(cut))
        self.assertEqual([f.complete for f in sc.frames], [True, False])
        self.assertEqual(sc.complete_end, len(zstd.compress_raw(a)))
        with TmpDir() as d:
            p = os.path.join(d, "x.jsonl.zst")
            with open(p, "wb") as f:
                f.write(cut)
            f, trunc = streams.open_bytes(p)
            self.assertEqual(f.read(), a)
            f.close()
            self.assertEqual(trunc, len(cut) - len(zstd.compress_raw(a)))

    def test_skippable_frame(self):
        skip = struct.pack("<II", 0x184D2A50, 4) + b"meta"
        data = skip + zstd.compress_raw(b"abc")
        self.assertEqual(zstd.decode_raw(data), b"abc")

    @unittest.skipUnless(shutil.which("node") or shutil.which("zstd"), "no external zstd decoder")
    def test_external_backend_multiframe(self):
        """Compressed (not raw) frames go to the external backend; several frames must all decode."""
        if not shutil.which("node"):
            self.skipTest("frames are produced with node here")
        js = ("const z=require('zlib');const a=z.zstdCompressSync(Buffer.from('alpha\\n'.repeat(500)));"
              "const b=z.zstdCompressSync(Buffer.from('beta\\n'.repeat(500)));process.stdout.write(Buffer.concat([a,b]));")
        p = subprocess.run(["node", "-e", js], capture_output=True)
        if p.returncode != 0:
            self.skipTest("node without zstd compression")
        with TmpDir() as d:
            path = os.path.join(d, "y.log.zst")
            with open(path, "wb") as f:
                f.write(p.stdout)
            f, _ = streams.open_bytes(path)
            out = f.read()
            f.close()
        self.assertEqual(out, b"alpha\n" * 500 + b"beta\n" * 500)


class JsonLines(unittest.TestCase):
    def test_header_skipped_and_versions_checked(self):
        with TmpDir() as d:
            hdr = {"schema": "arbx.attempts/2.3", "run": "x", "file_seq": 0, "started_ns": 1, "producer": "p"}
            write_jsonl(os.path.join(d, "attempts.jsonl"), [{"attempt": 0}, {"attempt": 1}], hdr)
            files = streams.discover(d)["attempts"]
            rows = streams.read_jsonl(files, "attempts")
            self.assertEqual([r["attempt"] for r in rows], [0, 1])
            self.assertEqual((files[0].major, files[0].minor), (2, 3))  # minor versions may add fields

    def test_unknown_major_is_refused(self):
        with TmpDir() as d:
            hdr = {"schema": "arbx.attempts/3.0", "run": "x", "file_seq": 0, "started_ns": 1, "producer": "p"}
            write_jsonl(os.path.join(d, "attempts.jsonl"), [{"attempt": 0}], hdr)
            with self.assertRaises(streams.SchemaError):
                streams.read_jsonl(streams.discover(d)["attempts"], "attempts")

    def test_v1_file_without_header_is_legacy(self):
        with TmpDir() as d:
            write_jsonl(os.path.join(d, "outcomes.jsonl"), [{"attempt": 0, "landed": None}])
            fi = streams.discover(d)["outcomes"]
            self.assertEqual(len(streams.read_jsonl(fi)), 1)
            self.assertTrue(fi[0].legacy)

    def test_partial_last_line_is_skipped(self):
        with TmpDir() as d:
            p = os.path.join(d, "bundles.jsonl")
            with open(p, "w") as f:
                f.write('{"bundle":"a"}\n{"bundle":"b"}\n{"bund')
            fi = streams.discover(d)["bundles"]
            self.assertEqual([r["bundle"] for r in streams.read_jsonl(fi)], ["a", "b"])
            self.assertTrue(fi[0].partial_tail)

    def test_rotation_order_and_legacy_names(self):
        with TmpDir() as d:
            for seq in (2, 0, 1):
                with open(os.path.join(d, f"decisions.{seq:03d}.jsonl.zst"), "wb") as f:
                    hdr = {"schema": "arbx.decisions/1.0", "run": "x", "file_seq": seq, "started_ns": 1, "producer": "p"}
                    f.write(zstd.compress_raw((json.dumps(hdr) + "\n" + json.dumps({"decision": seq}) + "\n").encode()))
            open(os.path.join(d, "slots.log"), "w").close()
            found = streams.discover(d)
            self.assertEqual([r["decision"] for r in streams.read_jsonl(found["decisions"])], [0, 1, 2])
            self.assertIn("slots-feed", found)  # arb-lab's slots.log is the slots-feed stream

    def test_idx_update_merged_into_first_line(self):
        with TmpDir() as d:
            seg = gen.generate(os.path.join(d, "s"))
            rows = {r["sig"]: r for r in streams.iter_exec(streams.discover(seg)["exec"])}
            y3 = rows[gen.S["Y3"]]
            self.assertEqual(y3["idx"], 4)
            self.assertEqual(y3["idx_src"], "slotidx")
            self.assertFalse(any("idx_update" in r for r in rows.values()))


class TextLogs(unittest.TestCase):
    def test_txarr_header_and_columns(self):
        with TmpDir() as d:
            seg = gen.generate(os.path.join(d, "s"))
            files = streams.discover(seg)["txarr"]
            rows = list(streams.iter_txarr(files))
            self.assertEqual(streams.txarr_feeds(files), ["feedA", "feedB"])
            o0 = [r for r in rows if r["sig8"] == solana.sig8(gen.S["O0"])][0]
            self.assertEqual(o0["d"], [None, 0])

    def test_v1_and_v2_poh_moves(self):
        with TmpDir() as d:
            with open(os.path.join(d, "poh.log"), "w") as f:
                f.write("f00b423f1ce58643 453055456 50.401\n")
            with open(os.path.join(d, "moves.log"), "w") as f:
                f.write("sigA 10 poolP 123\n")
            fs = streams.discover(d)
            p = list(streams.iter_poh(fs["poh"]))[0]
            self.assertEqual((p["slot"], p["ms"], p["feed"]), (453055456, 50.401, None))
            m = list(streams.iter_moves(fs["moves"]))[0]
            self.assertEqual((m["pool"], m["t_ns"], m["wv"]), ("poolP", 123, None))

    def test_sig8_matches_arb_lab(self):
        sig = "C17DdXVvy5krQukMj7piz9RZnr2GQmwTMtC5Pa1BztS5RicDexjRVkjfx6uZtxx6RB8BLcE42Dyv6eVfp7qXyXf"
        self.assertEqual(solana.sig8(sig), solana.b58decode(sig)[:8].hex())
        self.assertEqual(len(solana.sig8(sig)), 16)


class Binary(unittest.TestCase):
    def test_accounts_xor_reconstruction(self):
        with TmpDir() as d:
            seg = gen.generate(os.path.join(d, "s"))
            recs = list(streams.iter_accounts(streams.discover(seg)["accounts"]))
            self.assertEqual([r.aseq for r in recs], list(range(len(recs))))
            self.assertIn(streams.ACC_XOR, {r.kind for r in recs})
            for r in recs:  # the generator writes data = one repeated byte: XOR must give it back
                self.assertEqual(len(set(r.data)), 1)
            s1 = [r for r in recs if r.txn == gen.S["S1"]]
            self.assertEqual(sorted(r.acct for r in s1), sorted(gen.POOL_A))

    def test_accounts_gap_and_unmarked_hole(self):
        acct = gen.PA
        recs = [(0, acct, 10, 1, 1, None, b"\x01" * 4), (1, acct, 10, 2, 2, None, b"\x02" * 4),
                (5, acct, 11, 3, 3, None, b"\x03" * 4)]
        with TmpDir() as d:
            p = os.path.join(d, "accounts.000.bin.zst")
            with open(p, "wb") as f:  # the recorder dropped aseq 2..4 and said so
                f.write(zstd.compress_raw(gen.accounts_bin(recs, [acct], gaps={5: (2, 3)})))
            sc = streams.AccountsScan()
            got = [r.aseq for r in streams.iter_accounts(streams.discover(d)["accounts"], scan=sc)]
            self.assertEqual(got, [0, 1, 5])
            self.assertEqual(sc.gaps, [(2, 3)])
            self.assertEqual(sc.aseq_holes, [])
            with open(p, "wb") as f:  # the same hole without a GAP record is reported as unmarked
                f.write(zstd.compress_raw(gen.accounts_bin(recs, [acct])))
            sc = streams.AccountsScan()
            list(streams.iter_accounts(streams.discover(d)["accounts"], scan=sc))
            self.assertEqual(sc.aseq_holes, [(2, 4)])

    def test_journal_records(self):
        with TmpDir() as d:
            seg = gen.generate(os.path.join(d, "s"))
            js = streams.JournalScan()
            recs = list(streams.iter_journal(streams.discover(seg)["journal"], js))
            self.assertEqual([r["kind"] for r in recs], ["SLOT", "TX_FIRST", "ACCOUNT", "INPUT", "TIMER", "TICK"])
            self.assertEqual(recs[1]["sig"], solana.b58encode(bytes(64)))
            self.assertEqual(recs[3]["input"], "gate")
            self.assertEqual(js.seq_holes, [])


if __name__ == "__main__":
    unittest.main()
