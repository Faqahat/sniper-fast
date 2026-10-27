#!/usr/bin/env python3
"""Render a dipmon --screens-ansi frame (.ans: truecolor SGR text) to a PNG, as a dark terminal would show it, so the
screenshots can be looked at on a phone.   ans2png.py IN.ans OUT.png [--bg #101117] [--size 15]
Cells are drawn on a fixed grid: block elements (▀▄█▌▐) and the light / heavy box lines as rectangles (no gaps between
rows), everything else with DejaVu Sans Mono."""
import argparse
import re
import sys

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
FONT_FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"  # glyphs the mono font lacks
SGR = re.compile(r"\x1b\[([0-9;:]*)m")
OTHER = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[A-Za-z]")


def hexrgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def parse(text, fg0, bg0):
    rows = []
    for line in text.split("\n"):
        fg, bg, bold, faint, rev = None, None, False, False, False
        cells = []
        i = 0
        while i < len(line):
            if line[i] == "\x1b":
                m = SGR.match(line, i)
                if m:
                    ps = [p for p in re.split(r"[;:]", m.group(1))] if m.group(1) else ["0"]
                    j = 0
                    while j < len(ps):
                        p = int(ps[j] or 0)
                        if p == 0:
                            fg, bg, bold, faint, rev = None, None, False, False, False
                        elif p == 1:
                            bold = True
                        elif p == 2:
                            faint = True
                        elif p == 22:
                            bold = faint = False
                        elif p == 7:
                            rev = True
                        elif p == 27:
                            rev = False
                        elif p in (38, 48) and j + 1 < len(ps) and ps[j + 1] == "2":
                            c = tuple(int(x) for x in ps[j + 2:j + 5])
                            if p == 38:
                                fg = c
                            else:
                                bg = c
                            j += 4
                        elif p in (38, 48) and j + 1 < len(ps) and ps[j + 1] == "5":
                            j += 2
                        elif p == 39:
                            fg = None
                        elif p == 49:
                            bg = None
                        j += 1
                    i = m.end()
                    continue
                m = OTHER.match(line, i)
                if m:
                    i = m.end()
                    continue
                i += 1
                continue
            f, b = fg or fg0, bg or bg0
            if faint:
                f = tuple((a + c) // 2 for a, c in zip(f, bg0))
            if rev:
                f, b = b, f
            cells.append((line[i], f, b, bold))
            i += 1
        rows.append(cells)
    if text.endswith("\n") and rows and not rows[-1]:
        rows.pop()  # the final newline, not a row: the frame keeps its full height
    return rows


def draw_cell(d, ch, x, y, cw, chh, f, font):
    o = ord(ch)
    half_w, half_h = cw // 2, chh // 2
    rects = {
        0x2580: (0, 0, cw, half_h), 0x2584: (0, half_h, cw, chh), 0x2588: (0, 0, cw, chh),
        0x258C: (0, 0, half_w, chh), 0x2590: (half_w, 0, cw, chh),
    }
    if o in rects:
        a, b, c, e = rects[o]
        d.rectangle([x + a, y + b, x + c - 1, y + e - 1], fill=f)
        return
    lw = max(1, cw // 8)
    mid_x, mid_y = x + cw // 2, y + chh // 2
    # light / heavy box lines and rounded corners: drawn so neighbouring cells connect
    h = {"─": 1, "━": 2, "┤": 1, "┼": 1, "├": 1, "┬": 1, "┴": 1}
    if ch in ("─", "━"):
        t = lw * h[ch]
        d.rectangle([x, mid_y - t // 2, x + cw - 1, mid_y - t // 2 + t - 1], fill=f)
        return
    if ch == "│":
        d.rectangle([mid_x - lw // 2, y, mid_x - lw // 2 + lw - 1, y + chh - 1], fill=f)
        return
    if ch in "╭╮╰╯":
        r = min(cw, chh) // 2
        # the straight parts
        if ch in "╭╮":
            d.rectangle([mid_x - lw // 2, mid_y + r // 2, mid_x - lw // 2 + lw - 1, y + chh - 1], fill=f)
        else:
            d.rectangle([mid_x - lw // 2, y, mid_x - lw // 2 + lw - 1, mid_y - r // 2], fill=f)
        if ch in "╭╰":
            d.rectangle([mid_x + r // 2, mid_y - lw // 2, x + cw - 1, mid_y - lw // 2 + lw - 1], fill=f)
        else:
            d.rectangle([x, mid_y - lw // 2, mid_x - r // 2, mid_y - lw // 2 + lw - 1], fill=f)
        box = {"╭": (mid_x, mid_y, 180, 270), "╮": (mid_x - r, mid_y, 270, 360), "╰": (mid_x, mid_y - r, 90, 180),
               "╯": (mid_x - r, mid_y - r, 0, 90)}[ch]
        bx, by, a0, a1 = box
        d.arc([bx, by, bx + r, by + r], a0, a1, fill=f, width=lw)
        return
    if ch in "┤┼├┬┴":
        if ch in "┤┼├":
            d.rectangle([mid_x - lw // 2, y, mid_x - lw // 2 + lw - 1, y + chh - 1], fill=f)
        if ch in "┤┼┬┴":
            d.rectangle([x, mid_y - lw // 2, mid_x, mid_y - lw // 2 + lw - 1], fill=f)
        if ch in "┼├┬┴":
            d.rectangle([mid_x, mid_y - lw // 2, x + cw - 1, mid_y - lw // 2 + lw - 1], fill=f)
        if ch == "┬":
            d.rectangle([mid_x - lw // 2, mid_y, mid_x - lw // 2 + lw - 1, y + chh - 1], fill=f)
        if ch == "┴":
            d.rectangle([mid_x - lw // 2, y, mid_x - lw // 2 + lw - 1, mid_y], fill=f)
        return
    if ch == "╱":
        d.line([x, y + chh - 1, x + cw - 1, y], fill=f, width=lw)
        return
    if 0x2800 <= o <= 0x28FF:  # braille: 2 x 4 dots
        bits = o - 0x2800
        pos = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 3), (1, 3)]
        r = max(1, cw // 7)
        for k, (cx, cy) in enumerate(pos):
            if bits & (1 << k):
                px = x + cw * (1 + 2 * cx) // 4
                py = y + chh * (1 + 2 * cy) // 8
                d.ellipse([px - r, py - r, px + r, py + r], fill=f)
        return
    if missing(font, ch):
        font = fallback(font.size)
    d.text((x, y + (chh - font.size) // 2 - 1), ch, font=font, fill=f)


_missing, _fb = {}, {}


def missing(font, ch):
    k = (font.path, ch)
    if k not in _missing:
        ref = font.getmask("\ue000")
        m = font.getmask(ch)
        _missing[k] = m.size == ref.size and bytes(m) == bytes(ref)
    return _missing[k]


def fallback(size):
    if size not in _fb:
        _fb[size] = ImageFont.truetype(FONT_FB, size)
    return _fb[size]


def render(path, out, bg="#101117", fg="#d8d8e0", size=15):
    bg0, fg0 = hexrgb(bg), hexrgb(fg)
    rows = parse(open(path, encoding="utf-8").read(), fg0, bg0)
    font, fontb = ImageFont.truetype(FONT, size), ImageFont.truetype(FONT_B, size)
    cw = round(font.getlength("M"))
    chh = round(size * 1.3)
    w = max((len(r) for r in rows), default=1)
    pad = 12
    img = Image.new("RGB", (w * cw + 2 * pad, len(rows) * chh + 2 * pad), bg0)
    d = ImageDraw.Draw(img)
    for ry, r in enumerate(rows):
        for cx, (ch, f, b, bold) in enumerate(r):
            x, y = pad + cx * cw, pad + ry * chh
            if b != bg0:
                d.rectangle([x, y, x + cw - 1, y + chh - 1], fill=b)
            if ch != " ":
                draw_cell(d, ch, x, y, cw, chh, f, fontb if bold else font)
    img.save(out, optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--bg", default="#101117")
    ap.add_argument("--size", type=int, default=15)
    a = ap.parse_args()
    render(a.src, a.out, a.bg, size=a.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
