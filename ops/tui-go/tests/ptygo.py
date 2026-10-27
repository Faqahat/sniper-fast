#!/usr/bin/env python3
"""Run the Go dipmon in a real pseudo-terminal (a given size): send keys, collect the output, rebuild the screen
(tests/vt.py), count bells, sample CPU / RSS. The Python tests' ptyrun.py, for the Go binary."""
import fcntl
import os
import pty
import select
import signal
import struct
import termios
import time

from vt import Screen

KEYS = {"up": b"\x1b[A", "down": b"\x1b[B", "pgup": b"\x1b[5~", "pgdn": b"\x1b[6~", "home": b"\x1b[H", "end": b"\x1b[F",
        "enter": b"\r", "esc": b"\x1b", "tab": b"\t", "btab": b"\x1b[Z", "wheelup": b"\x1b[<64;10;10M", "wheeldown": b"\x1b[<65;10;10M"}


def set_size(fd, rows, cols):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


class Pty:
    def __init__(self, binary, args, rows=24, cols=80, env=None):
        self.rows, self.cols = rows, cols
        self.screen = Screen(rows, cols)
        self.total = 0
        self.raw_tail = bytearray()
        e = dict(os.environ)
        e.update(env or {})
        pid, fd = pty.fork()
        if pid == 0:
            try:
                set_size(0, rows, cols)
            except OSError:
                pass
            os.execvpe(binary, [binary] + list(args), e)
        self.pid, self.fd = pid, fd
        set_size(fd, rows, cols)
        self.status = None

    def pump(self, secs=0.0):
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
                    self.screen.feed(data)
                    self.raw_tail += data
                    if len(self.raw_tail) > 200_000:
                        del self.raw_tail[:len(self.raw_tail) - 200_000]
            if time.time() >= end:
                return

    def send(self, k, wait=0.25):
        os.write(self.fd, KEYS.get(k, k.encode() if isinstance(k, str) else k))
        self.pump(wait)

    def click(self, x, y, wait=0.3):
        os.write(self.fd, f"\x1b[<0;{x + 1};{y + 1}M\x1b[<0;{x + 1};{y + 1}m".encode())
        self.pump(wait)

    def resize(self, rows, cols, wait=0.5):
        self.rows, self.cols = rows, cols
        set_size(self.fd, rows, cols)
        self.screen.resize(rows, cols)
        os.kill(self.pid, signal.SIGWINCH)
        self.pump(wait)

    def poll(self):
        if self.status is None:
            try:
                p, st = os.waitpid(self.pid, os.WNOHANG)
            except ChildProcessError:
                return -1
            if p:
                self.status = os.waitstatus_to_exitcode(st)
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
        return self.screen.text()

    @property
    def bells(self):
        return self.screen.bells
