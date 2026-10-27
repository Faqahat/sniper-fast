#!/usr/bin/env python3
"""Run dipmon's curses UI in a real pseudo-terminal (a given size), send keys, collect the output, sample its CPU / RSS."""
import fcntl
import os
import pty
import select
import signal
import struct
import sys
import termios
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DIPMON = os.path.join(os.path.dirname(HERE), "dipmon.py")
KEYS = {"up": b"\x1b[A", "down": b"\x1b[B", "pgup": b"\x1b[5~", "pgdn": b"\x1b[6~", "home": b"\x1b[H", "end": b"\x1b[F",
        "enter": b"\r", "esc": b"\x1b", "tab": b"\t", "btab": b"\x1b[Z"}


def set_size(fd, rows, cols):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


class Pty:
    def __init__(self, args, rows=24, cols=80, env=None, keep=400_000):
        self.rows, self.cols = rows, cols
        self.keep = keep
        self.out = bytearray()
        self.total = 0
        e = dict(os.environ)
        e.update(env or {})
        for k, v in list(e.items()):
            if v is None:
                del e[k]
        pid, fd = pty.fork()
        if pid == 0:
            try:
                set_size(sys.stdout.fileno(), rows, cols)
            except OSError:
                pass
            os.execvpe(sys.executable, [sys.executable, DIPMON] + list(args), e)
        self.pid, self.fd = pid, fd
        set_size(fd, rows, cols)
        self.status = None
        self.t0 = time.time()

    def pump(self, secs=0.0):
        """read whatever the UI wrote, for up to secs"""
        end = time.time() + secs
        while True:
            left = end - time.time()
            r, _, _ = select.select([self.fd], [], [], max(0.0, min(0.05, left)))
            if r:
                try:
                    data = os.read(self.fd, 65536)
                except OSError:
                    data = b""
                if not data:
                    self.poll()
                    if self.status is not None:
                        return
                else:
                    self.total += len(data)
                    self.out += data
                    if len(self.out) > self.keep:
                        del self.out[: len(self.out) - self.keep]
            if time.time() >= end:
                return

    def send(self, k, wait=0.25):
        os.write(self.fd, KEYS.get(k, k.encode() if isinstance(k, str) else k))
        self.pump(wait)

    def resize(self, rows, cols, wait=0.4):
        self.rows, self.cols = rows, cols
        set_size(self.fd, rows, cols)
        os.kill(self.pid, signal.SIGWINCH)
        self.pump(wait)

    def poll(self):
        if self.status is None:
            try:
                p, st = os.waitpid(self.pid, os.WNOHANG)
            except ChildProcessError:
                return -1
            if p:
                self.status = os.waitstatus_to_exitcode(st) if hasattr(os, "waitstatus_to_exitcode") else (st >> 8)
        return self.status

    def wait(self, timeout=20.0):
        end = time.time() + timeout
        while time.time() < end:
            self.pump(0.1)
            if self.poll() is not None:
                return self.status
        os.kill(self.pid, signal.SIGKILL)
        self.pump(0.2)
        self.poll()
        return None

    def cpu_ticks(self):
        try:
            rest = open(f"/proc/{self.pid}/stat").read().rsplit(")", 1)[1].split()
            return int(rest[11]) + int(rest[12])
        except Exception:
            return None

    def rss(self):
        """(VmRSS, VmHWM) in bytes"""
        try:
            d = {}
            for l in open(f"/proc/{self.pid}/status"):
                if l.startswith(("VmRSS", "VmHWM")):
                    k, v = l.split(":")
                    d[k] = int(v.split()[0]) * 1024
            return d.get("VmRSS"), d.get("VmHWM")
        except Exception:
            return None, None

    def text(self):
        return self.out.decode("utf-8", "replace")
