package ui

import (
	"regexp"
	"strings"

	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
)

// fitLine truncates (with an ellipsis) or pads a styled line to exactly w cells.
func fitLine(s string, w int) string {
	if w <= 0 {
		return ""
	}
	sw := ansi.StringWidth(s)
	if sw > w {
		return ansi.Truncate(s, w, "…")
	}
	if sw < w {
		return s + strings.Repeat(" ", w-sw)
	}
	return s
}

// cut truncates without padding.
func cut(s string, w int) string {
	if w <= 0 {
		return ""
	}
	if ansi.StringWidth(s) > w {
		return ansi.Truncate(s, w, "…")
	}
	return s
}

// block normalizes s to exactly h lines (h <= 0: as many as it has) of exactly w cells.
func block(s string, w, h int) string {
	lines := strings.Split(s, "\n")
	if h > 0 {
		if len(lines) > h {
			lines = lines[:h]
		}
		for len(lines) < h {
			lines = append(lines, "")
		}
	}
	for i, l := range lines {
		lines[i] = fitLine(l, w)
	}
	return strings.Join(lines, "\n")
}

// lr puts left and right on one line of width w (right-aligned); the left side is cut first.
func lr(left, right string, w int) string {
	lw, rw := ansi.StringWidth(left), ansi.StringWidth(right)
	if lw+rw+1 > w {
		if rw+1 >= w {
			return fitLine(left, w)
		}
		left = cut(left, w-rw-1)
		lw = ansi.StringWidth(left)
	}
	return left + strings.Repeat(" ", max(1, w-lw-rw)) + right
}

func (m *Model) border() lipgloss.Border {
	if m.ascii {
		return lipgloss.ASCIIBorder()
	}
	return lipgloss.RoundedBorder()
}

// panel draws a box of outer width w (and outer height h when h > 0) with the title set in its top border and an
// optional right-hand note, the Lip Gloss rounded border runes in the theme's border color, one cell of padding.
func (m *Model) panel(title, right, body string, w, h int) string {
	if w < 6 {
		return block(body, w, h)
	}
	t := m.th
	b := m.border()
	bs := lipgloss.NewStyle().Foreground(t.Border)
	inner := w - 4
	lines := strings.Split(body, "\n")
	if h > 0 {
		ch := max(0, h-2)
		if len(lines) > ch {
			lines = lines[:ch]
		}
		for len(lines) < ch {
			lines = append(lines, "")
		}
	}
	// top border with the title
	tt := ""
	if title != "" {
		tt = " " + t.PanelTitle.Render(title) + " "
	}
	rt := ""
	if right != "" {
		rt = " " + right + " "
	}
	avail := w - 2 - 2 // corners + one dash on each side
	if ansi.StringWidth(tt)+ansi.StringWidth(rt) > avail {
		rt = ""
		if ansi.StringWidth(tt) > avail {
			tt = cut(tt, avail)
		}
	}
	fill := avail - ansi.StringWidth(tt) - ansi.StringWidth(rt)
	var sb strings.Builder
	sb.WriteString(bs.Render(b.TopLeft + b.Top))
	sb.WriteString(tt)
	sb.WriteString(bs.Render(strings.Repeat(b.Top, max(0, fill))))
	sb.WriteString(rt)
	sb.WriteString(bs.Render(b.Top + b.TopRight))
	side := bs.Render(b.Left)
	sideR := bs.Render(b.Right)
	for _, l := range lines {
		sb.WriteString("\n")
		sb.WriteString(side + " " + fitLine(l, inner) + " " + sideR)
	}
	sb.WriteString("\n")
	sb.WriteString(bs.Render(b.BottomLeft + strings.Repeat(b.Bottom, w-2) + b.BottomRight))
	return sb.String()
}

// rule is a section line: "TITLE ─────── right".
func (m *Model) rule(title, right string, w int) string {
	t := m.th
	hr := "─"
	if m.ascii {
		hr = "-"
	}
	l := t.PanelTitle.Render(title)
	r := ""
	if right != "" {
		r = " " + right
	}
	n := w - ansi.StringWidth(l) - ansi.StringWidth(r) - 2
	if n < 1 {
		return fitLine(l+r, w)
	}
	return l + " " + t.Rule.Render(strings.Repeat(hr, n)) + r + " "
}

// hcat joins blocks side by side (top-aligned) with a gap.
func hcat(gap int, blocks ...string) string {
	if len(blocks) == 0 {
		return ""
	}
	parts := make([]string, 0, 2*len(blocks))
	sp := strings.Repeat(" ", gap)
	for i, b := range blocks {
		if i > 0 && gap > 0 {
			h := strings.Count(b, "\n") + 1
			parts = append(parts, strings.TrimSuffix(strings.Repeat(sp+"\n", h), "\n"))
		}
		parts = append(parts, b)
	}
	return lipgloss.JoinHorizontal(lipgloss.Top, parts...)
}

// kv is a label (dim, padded to lw) and its value.
func (m *Model) kv(label string, lw int, value string) string {
	return m.th.Lbl.Render(padRight(label, lw)) + value
}

var numUnit = regexp.MustCompile(`(\d) (s|ms|us|SOL|slots?|slot\(s\)|blocks?|block\(s\))\b`)

// asciiFold maps what is left of Unicode in an --ascii frame to one ASCII character each (the cell widths stay):
// lines, corners, arrows, dots, blocks, braille; '?' for anything else.
func asciiFold(s string) string {
	return strings.Map(func(r rune) rune {
		if r < 0x80 {
			return r
		}
		if r >= 0x2800 && r <= 0x28FF {
			if r == 0x2800 {
				return ' '
			}
			return '*'
		}
		switch r {
		case '─', '┈', '┄', '╌':
			return '-'
		case '━', '═':
			return '='
		case '│', '┃':
			return '|'
		case '┤', '┼', '├', '┬', '┴', '└', '┘', '┌', '┐', '╭', '╮', '╰', '╯':
			return '+'
		case '↑', '▲':
			return '^'
		case '↓', '▼':
			return 'v'
		case '→', '▸', '►':
			return '>'
		case '←':
			return '<'
		case '…':
			return '~'
		case '·', '•':
			return '|'
		case '−', '–', '—':
			return '-'
		case '≥':
			return '>'
		case '≤':
			return '<'
		case '×':
			return 'x'
		case '✓', '✔':
			return 'v'
		case '✗', '✘':
			return 'x'
		case '●', '◆', '♦':
			return '*'
		case '○', '◷':
			return 'o'
		case '╱':
			return '/'
		case '♪':
			return '~'
		case '█', '▀', '▄', '▌', '▐', '▁', '▂', '▃', '▅', '▆', '▇':
			return '#'
		}
		return '?'
	}, s)
}

// wrapLines wraps every line wider than w (its styles kept) after its first ind columns (a kv label), indenting the
// continuation lines by ind.
func wrapLines(ls []string, w, ind int) []string {
	var out []string
	for _, l := range ls {
		if ansi.StringWidth(l) <= w || w-ind < 10 {
			out = append(out, l)
			continue
		}
		// a number and its unit stay together (a no-break space while wrapping)
		val := numUnit.ReplaceAllString(ansi.TruncateLeft(l, ind, ""), "$1\u00a0$2")
		parts := strings.Split(ansi.Wrap(val, w-ind, " "), "\n")
		for i, p := range parts {
			p = strings.ReplaceAll(p, "\u00a0", " ")
			if i == 0 {
				out = append(out, ansi.Truncate(l, ind, "")+p)
			} else {
				out = append(out, strings.Repeat(" ", ind)+p)
			}
		}
	}
	return out
}

func padRight(s string, n int) string {
	w := ansi.StringWidth(s)
	if w >= n {
		return s
	}
	return s + strings.Repeat(" ", n-w)
}

func padLeft(s string, n int) string {
	w := ansi.StringWidth(s)
	if w >= n {
		return s
	}
	return strings.Repeat(" ", n-w) + s
}

// lines counts the lines of a block.
func lines(s string) int { return strings.Count(s, "\n") + 1 }
