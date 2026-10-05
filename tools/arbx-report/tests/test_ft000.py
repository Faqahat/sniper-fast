"""FT-000 fixes (docs/field-tests/FT-000-early-shadow.md): block positions ordered by one kind per slot (S1-2), R9
leaving exec.jsonl's sampled records out (S1-5), the journal's ALT eviction record (S1-4)."""
import struct
import unittest

from arbx_report import blockctx, solana, streams
from arbx_report.reports import r9_rivals


def tx(sig, bi):
    return {"sig": sig, "idx": None, "_bi": bi}


class SlotOrder(unittest.TestCase):
    def test_exec_block_indexes_when_every_transaction_has_one(self):
        txs = {"a": tx("a", 30), "b": tx("b", 77)}
        self.assertEqual(blockctx.order_slot(txs, {"a": 5, "b": 20}, "nonvote_rank"), "block_index")
        self.assertEqual((txs["a"]["idx"], txs["b"]["idx"]), (30, 77))

    def test_slot_index_ranks_when_one_lacks_a_block_index(self):
        # FT-000: a = the stream's (block index 77), b = a backfilled record without one; Shyft listed them at ranks 20, 5
        # (votes left out). Mixed, they would put a (77) after b... and b's rank 5 before a's rank 20: one kind only
        txs = {"a": tx("a", 77), "b": tx("b", None)}
        self.assertEqual(blockctx.order_slot(txs, {"a": 20, "b": 5}, "nonvote_rank"), "nonvote_rank")
        self.assertEqual((txs["a"]["idx"], txs["b"]["idx"]), (20, 5))

    def test_a_block_index_line_merges_with_exec_indexes(self):
        txs = {"a": tx("a", 31), "b": tx("b", None)}
        self.assertEqual(blockctx.order_slot(txs, {"a": 31, "b": 12}, "block_index"), "block_index")
        self.assertEqual((txs["a"]["idx"], txs["b"]["idx"]), (31, 12))

    def test_mixed_when_neither_kind_covers_the_slot(self):
        txs = {"a": tx("a", 31), "b": tx("b", None), "c": tx("c", 40)}
        self.assertEqual(blockctx.order_slot(txs, {"b": 12}, "nonvote_rank"), "mixed")
        self.assertEqual([txs[s]["idx"] for s in "abc"], [31, None, 40], "the larger kind, the others without a position")

    def test_line_kinds_and_merged_ranks(self):
        self.assertEqual(blockctx.slot_pos_kind({"status": "ok", "pos_kind": "nonvote_rank"}), "nonvote_rank")
        self.assertEqual(blockctx.slot_pos_kind({"status": "ok"}), "unverified", "a line written before slotidx 1.1")
        self.assertIsNone(blockctx.slot_pos_kind({"status": "skipped"}))
        # an idx merged from a rank's idx_update (FT-000's recordings) is not a block index
        self.assertIsNone(blockctx.exec_block_index({"idx": 5, "idx_src": "slotidx"}, "unverified"))
        self.assertEqual(blockctx.exec_block_index({"idx": 5, "idx_src": "slotidx"}, "block_index"), 5)
        self.assertEqual(blockctx.exec_block_index({"idx": 77}, "nonvote_rank"), 77)


class Positions(unittest.TestCase):
    def test_exec_indexes_only_where_the_slot_line_is_block_index(self):
        class Seg:
            slotidx = {100: {"slot": 100, "status": "ok", "pos_kind": "nonvote_rank", "tracked": [["t", 3]]},
                       101: {"slot": 101, "status": "ok", "pos_kind": "block_index", "tracked": [["u", 9]]}}
        rows = [{"sig": "x", "slot": 100, "idx": 70}, {"sig": "y", "slot": 101, "idx": 12}, {"sig": "z", "slot": 102, "idx": 4},
                {"sig": "w", "slot": 101, "idx": 13, "idx_src": "slotidx"}]
        pos = blockctx.positions(Seg(), rows)
        self.assertEqual(pos, {"t": (100, 3), "u": (101, 9), "y": (101, 12), "z": (102, 4), "w": (101, 13)},
                         "x's block index would not compare with slot 100's ranks")


class R9Sampled(unittest.TestCase):
    def test_sampled_records_are_left_out(self):
        win = {"sig": "s1", "slot": 1, "idx": 3, "ok": True, "signer": "A", "signer_sol": 5_000, "signer_tok": {}, "arb_like": {"is": True},
               "pools": [], "sample": None}
        sampled = dict(win, sig="s2", signer="B", sample={"one_in": 20, "kept": 1, "seen": 7})

        class Seg:
            legacy = False
            wallet = "OURS"
            pools = []
            slotidx = {}
            def has(self, s):
                return False
            def iter_exec(self):
                return iter([win, sampled])
        sec = r9_rivals.run(Seg(), {})
        d = sec["data"]
        self.assertEqual((d["arb_like_txs"], d["sampled_unwatched_rows_left_out"], d["signers"]), (1, 1, 1))
        self.assertEqual(d["top_by_clean_wins"][0]["signer"], "A")


class JournalEviction(unittest.TestCase):
    def test_alt_found_4_reads_as_an_eviction(self):
        t1, t2 = bytes([1] * 32), bytes([2] * 32)
        body = bytes(32) + bytes([4]) + struct.pack("<H", 2) + t1 + t2 + struct.pack("<QQ", 17, 0xABC)
        d = streams._parse_journal_body(streams.J_ALT, body)
        self.assertEqual(d, {"evicted": [solana.b58encode(t1), solana.b58encode(t2)], "evicted_total": 17, "evict_hash": 0xABC})
        # an answer still reads as before
        a = streams._parse_journal_body(streams.J_ALT, t1 + bytes([1]) + struct.pack("<H", 1) + t2)
        self.assertEqual((a["found"], a["addrs"]), (True, [solana.b58encode(t2)]))


if __name__ == "__main__":
    unittest.main()
