#!/usr/bin/env python3
"""A minimal VT screen for tests: replays a terminal byte stream (what Bubble Tea writes) onto a rows x cols grid
and returns the final text. Handles what the renderer emits: CUP / CHA / VPA, cursor moves, ECH / EL / ED, REP,
IL / DL, scrolling regions, SGR (ignored for text), private modes, OSC (dropped), UTF-8 text; BEL is counted."""
import re

CSI = re.compile(rb"\x1b\[([0-9;?<>=:]*)([ -/]*)([@-~])")


class Screen:
    def __init__(self, rows, cols):
        self.rows, self.cols = rows, cols
        self.alt = [[" "] * cols for _ in range(rows)]
        self.main = [[" "] * cols for _ in range(rows)]
        self.g = self.main
        self.y = self.x = 0
        self.top, self.bot = 0, rows - 1
        self.bells = 0
        self.saved = (0, 0)
        self.last = " "
        self.wrap_pending = False
        self.pend = b""

    def resize(self, rows, cols):
        def fit(g):
            g = [r[:cols] + [" "] * max(0, cols - len(r)) for r in g[:rows]]
            while len(g) < rows:
                g.append([" "] * cols)
            return g
        self.alt, self.main = fit(self.alt), fit(self.main)
        self.g = self.alt if self.g is not self.main else self.main
        self.rows, self.cols = rows, cols
        self.top, self.bot = 0, rows - 1
        self.y, self.x = min(self.y, rows - 1), min(self.x, cols - 1)

    def text(self):
        return "\n".join("".join(r).rstrip() for r in self.g)

    def _scroll_up(self, n=1):
        for _ in range(n):
            del self.g[self.top]
            self.g.insert(self.bot, [" "] * self.cols)

    def _put(self, ch):
        if self.wrap_pending:
            self.wrap_pending = False
            self.x = 0
            self._lf()
        if 0 <= self.y < self.rows and 0 <= self.x < self.cols:
            self.g[self.y][self.x] = ch
        self.last = ch
        if self.x >= self.cols - 1:
            self.wrap_pending = True
        else:
            self.x += 1

    def _lf(self):
        if self.y == self.bot:
            self._scroll_up()
        elif self.y < self.rows - 1:
            self.y += 1

    def feed(self, data):
        data = self.pend + data
        self.pend = b""
        i, n = 0, len(data)
        while i < n:
            b = data[i]
            if b == 0x1b:
                # an escape sequence cut by the read: keep it for the next feed
                tail = data[i:]
                if len(tail) < 64 and (tail == b"\x1b" or (tail[1:2] == b"[" and not CSI.match(data, i)) or
                                       (tail[1:2] in (b"]", b"P", b"_", b"^", b"X") and b"\x07" not in tail and b"\x1b\\" not in tail[1:])):
                    self.pend = tail
                    return
                m = CSI.match(data, i)
                if m:
                    self._csi(m.group(1).decode(), m.group(2).decode(), m.group(3).decode())
                    i = m.end()
                    continue
                if i + 1 < n and data[i + 1] == 0x5D:  # OSC: drop until BEL or ST
                    j = i + 2
                    while j < n and data[j] != 0x07 and not (data[j] == 0x1b and j + 1 < n and data[j + 1] == 0x5C):
                        j += 1
                    i = j + (1 if j < n and data[j] == 0x07 else 2)
                    continue
                if i + 1 < n and data[i + 1] in b"PX^_":  # DCS / SOS / PM / APC: drop until ST
                    j = data.find(b"\x1b\\", i + 2)
                    i = n if j < 0 else j + 2
                    continue
                if i + 1 < n and data[i + 1] == ord("7"):
                    self.saved = (self.y, self.x)
                elif i + 1 < n and data[i + 1] == ord("8"):
                    self.y, self.x = self.saved
                elif i + 1 < n and data[i + 1] in b"()":
                    i += 3
                    continue
                elif i + 1 < n and data[i + 1] == ord("M"):  # reverse index
                    if self.y == self.top:
                        del self.g[self.bot]
                        self.g.insert(self.top, [" "] * self.cols)
                    else:
                        self.y = max(0, self.y - 1)
                i += 2
                continue
            if b == 0x07:
                self.bells += 1
                i += 1
                continue
            if b == 0x0d:
                self.x = 0
                self.wrap_pending = False
                i += 1
                continue
            if b == 0x0a:
                self.wrap_pending = False
                self._lf()
                i += 1
                continue
            if b == 0x08:
                self.x = max(0, self.x - 1)
                self.wrap_pending = False
                i += 1
                continue
            if b == 0x09:
                self.x = min(self.cols - 1, (self.x // 8 + 1) * 8)
                i += 1
                continue
            if b < 0x20:
                i += 1
                continue
            # UTF-8 text
            ln = 1 if b < 0x80 else (2 if b >> 5 == 6 else (3 if b >> 4 == 14 else 4))
            if i + ln > n:
                self.pend = data[i:]
                return
            ch = data[i:i + ln].decode("utf-8", "replace")
            self._put(ch)
            i += ln

    def _csi(self, params, inter, final):
        priv = params[:1] if params[:1] in "?<>=" else ""
        ps = params[1:] if priv else params
        args = [int(x) if x.isdigit() else 0 for x in ps.replace(":", ";").split(";")] if ps else []

        def a(k, d=1):
            return args[k] if len(args) > k and args[k] else d
        self.wrap_pending = False
        if priv == "?":
            if final in "hl" and (1049 in args or 47 in args or 1047 in args):
                if final == "h":
                    self.g = self.alt
                else:
                    self.g = self.main
            return
        if priv or inter:
            return
        if final == "H" or final == "f":
            self.y, self.x = min(self.rows - 1, a(0) - 1), min(self.cols - 1, a(1) - 1)
        elif final == "G" or final == "`":
            self.x = min(self.cols - 1, a(0) - 1)
        elif final == "d":
            self.y = min(self.rows - 1, a(0) - 1)
        elif final == "A":
            self.y = max(0, self.y - a(0))
        elif final == "B" or final == "e":
            self.y = min(self.rows - 1, self.y + a(0))
        elif final == "C" or final == "a":
            self.x = min(self.cols - 1, self.x + a(0))
        elif final == "D":
            self.x = max(0, self.x - a(0))
        elif final == "E":
            self.y, self.x = min(self.rows - 1, self.y + a(0)), 0
        elif final == "F":
            self.y, self.x = max(0, self.y - a(0)), 0
        elif final == "X":
            for k in range(a(0)):
                if self.x + k < self.cols:
                    self.g[self.y][self.x + k] = " "
        elif final == "K":
            m = args[0] if args else 0
            row = self.g[self.y]
            rng = range(self.x, self.cols) if m == 0 else (range(0, self.x + 1) if m == 1 else range(self.cols))
            for k in rng:
                row[k] = " "
        elif final == "J":
            m = args[0] if args else 0
            if m in (2, 3):
                for r in range(self.rows):
                    self.g[r] = [" "] * self.cols
            elif m == 0:
                self.g[self.y][self.x:] = [" "] * (self.cols - self.x)
                for r in range(self.y + 1, self.rows):
                    self.g[r] = [" "] * self.cols
            elif m == 1:
                for r in range(0, self.y):
                    self.g[r] = [" "] * self.cols
                for k in range(0, self.x + 1):
                    self.g[self.y][k] = " "
        elif final == "b":
            for _ in range(a(0)):
                self._put(self.last)
        elif final == "L":
            for _ in range(a(0)):
                del self.g[self.bot]
                self.g.insert(self.y, [" "] * self.cols)
        elif final == "M":
            for _ in range(a(0)):
                del self.g[self.y]
                self.g.insert(self.bot, [" "] * self.cols)
        elif final == "P":
            row = self.g[self.y]
            k = a(0)
            del row[self.x:self.x + k]
            row.extend([" "] * k)
        elif final == "@":
            row = self.g[self.y]
            for _ in range(a(0)):
                row.insert(self.x, " ")
                row.pop()
        elif final == "S":
            self._scroll_up(a(0))
        elif final == "T":
            for _ in range(a(0)):
                del self.g[self.bot]
                self.g.insert(self.top, [" "] * self.cols)
        elif final == "r":
            self.top = a(0) - 1
            self.bot = (args[1] if len(args) > 1 and args[1] else self.rows) - 1
            self.y = self.x = 0
