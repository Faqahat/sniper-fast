"""Re-pricing a route at a recorded state version through `arbx quote` (WP-09).

R4 (attribution), the all-swap part of R8 and X3 need it. Until WP-09 lands, `ArbxQuote.available()` is False and
those sections are marked incomplete (MEASUREMENT §6.1: never approximated).

A pricer is any object with `net_after(seg, attempt, versions, size, after_sig) -> int | None`, where `versions` maps
each route account to the `aseq` of its version (accounts.bin) and `after_sig` names the last transaction applied
(None = the decision's own state). Tests use a table-driven pricer.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess


class Unavailable(Exception):
    pass


class ArbxQuote:
    """`arbx quote --run <seg> --route <json> --version <json> --size <lamports>` printing JSON {net, gross, ...}.
    The exact CLI is WP-09's; this adapter is the one place to align with it."""

    def __init__(self, binary: str | None = None):
        self.binary = binary or os.environ.get("ARBX_BIN") or shutil.which("arbx")
        self._ok: bool | None = None

    def available(self) -> bool:
        if self._ok is None:
            self._ok = False
            if self.binary and os.path.exists(self.binary):
                try:
                    p = subprocess.run([self.binary, "quote", "--help"], capture_output=True, timeout=20)
                    self._ok = p.returncode == 0
                except Exception:
                    self._ok = False
        return self._ok

    def reason(self) -> str:
        return "needs `arbx quote` (WP-09): no arbx binary with a quote command found (set --arbx-bin or ARBX_BIN)"

    def net_after(self, seg, attempt: dict, versions: dict, size: int, after_sig=None):
        if not self.available():
            raise Unavailable(self.reason())
        route = attempt.get("route") or {}
        cmd = [self.binary, "quote", "--run", seg.dir, "--route", json.dumps(route, sort_keys=True),
               "--version", json.dumps(versions, sort_keys=True), "--size", str(size)]
        p = subprocess.run(cmd, capture_output=True, timeout=60)
        if p.returncode != 0:
            return None
        try:
            return json.loads(p.stdout).get("net")
        except ValueError:
            return None


class TablePricer:
    """For tests and offline studies: net looked up by (attempt, last tx applied) -> lamports."""

    def __init__(self, table: dict, start: dict | None = None):
        self.table = table
        self.start = start or {}

    def available(self) -> bool:
        return True

    def reason(self) -> str:
        return ""

    def net_after(self, seg, attempt: dict, versions: dict, size: int, after_sig=None):
        return self.table.get((attempt["attempt"], after_sig))
