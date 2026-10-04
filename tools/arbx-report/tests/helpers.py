import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(TOOL, "..", ".."))
sys.path.insert(0, TOOL)

from arbx_report import model, quote  # noqa: E402

import gen  # noqa: E402

LEGACY_RAW = os.path.join(REPO, "testdata", "legacy", "raw")
WALLET_FIXTURE = os.path.join(HERE, "fixtures", "legacy", "wallet-w5h-p1-p10.jsonl.xz")


class TmpDir:
    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="arbx-report-test-")
        return self.d

    def __exit__(self, *a):
        shutil.rmtree(self.d, ignore_errors=True)


def synth_segment(root: str, name: str = "synth-p1") -> model.Segment:
    d = gen.generate(os.path.join(root, name))
    return model.Segment(d)


def synth_ctx(**kw) -> dict:
    ctx = {"offline": True, "quick": False, "fill_gaps": False, "pricer": quote.TablePricer(gen.TABLE)}
    ctx.update(kw)
    return ctx


def write_jsonl(path: str, rows: list, header: dict | None = None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        if header is not None:
            f.write(json.dumps(header) + "\n")
        for r in rows:
            f.write(json.dumps(r) + "\n")
