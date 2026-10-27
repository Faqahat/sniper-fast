package ui

import (
	"image/color"
	"strings"

	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
)

// The REWIND wordmark, in the style of Charm's Crush header: blocky half-block letters with a pink -> violet ->
// indigo gradient, diagonal hatching to the edges and a small label above the start of the word.

// full letterforms: 3 rows, a 5-pixel face with the baseline in the upper half of the last row
var logoFull = [][3]string{
	{"█▀▀▀▄", "█▀▀▀▄", "▀   ▀"}, // R
	{"█▀▀▀▀", "█▀▀▀ ", "▀▀▀▀▀"}, // E
	{"█   █", "█ ▄ █", " ▀ ▀ "}, // W
	{"▀█▀", " █ ", "▀▀▀"},       // I
	{"█▄  █", "█ ▀▄█", "▀   ▀"}, // N
	{"█▀▀▀▄", "█   █", "▀▀▀▀ "}, // D
}

// compact letterforms: 2 rows
var logoCompact = [][2]string{
	{"█▀█", "█▀▄"},     // R
	{"█▀▀", "██▄"},     // E
	{"█ █ █", "▀▄▀▄▀"}, // W
	{"█", "█"},         // I
	{"█▄ █", "█ ▀█"},   // N
	{"█▀▄", "█▄▀"},     // D
}

const hatchRune = "╱"

// stretchRow doubles every column (the splash's large logo).
func stretchRow(s string) string {
	var b strings.Builder
	for _, r := range s {
		b.WriteRune(r)
		b.WriteRune(r)
	}
	return b.String()
}

func logoRows(rows int, stretch bool) []string {
	out := make([]string, rows)
	if rows == 3 {
		for i, l := range logoFull {
			for r := 0; r < 3; r++ {
				if i > 0 {
					out[r] += " "
				}
				seg := l[r]
				if stretch {
					seg = stretchRow(seg)
				}
				out[r] += seg
			}
		}
		return out
	}
	for i, l := range logoCompact {
		for r := 0; r < 2; r++ {
			if i > 0 {
				out[r] += " "
			}
			out[r] += l[r]
		}
	}
	return out
}

// gradientRows colors each column of the rows with a horizontal blend of the stops.
func gradientRows(rows []string, stops []color.Color, bold bool) []string {
	w := 0
	rr := make([][]rune, len(rows))
	for i, r := range rows {
		rr[i] = []rune(r)
		w = max(w, len(rr[i]))
	}
	if w == 0 {
		return rows
	}
	var cols []color.Color
	if len(stops) > 1 {
		cols = lipgloss.Blend1D(w, stops...)
	}
	out := make([]string, len(rows))
	for i, r := range rr {
		var b strings.Builder
		run := []rune{}
		cur := -1
		flush := func() {
			if len(run) == 0 {
				return
			}
			st := lipgloss.NewStyle().Bold(bold)
			if cols != nil && cur >= 0 {
				st = st.Foreground(cols[cur])
			} else if len(stops) == 1 {
				st = st.Foreground(stops[0])
			}
			b.WriteString(st.Render(string(run)))
			run = run[:0]
		}
		for x, ch := range r {
			if ch == ' ' {
				flush()
				b.WriteRune(' ')
				cur = -1
				continue
			}
			// one style per column keeps the blend smooth; adjacent cells of similar color are cheap enough
			flush()
			cur = x
			run = append(run, ch)
		}
		flush()
		out[i] = b.String()
	}
	return out
}

// GradientText colors a word with the brand blend (one color per character).
func (m *Model) GradientText(s string, bold bool) string {
	if m.ascii || m.th.Mono {
		return lipgloss.NewStyle().Bold(bold).Render(s)
	}
	return gradientRows([]string{s}, m.th.Brand, bold)[0]
}

// logoBlock renders the wordmark at width w: label row + letter rows, hatching on both sides to the edges.
// size: 3 = full, 2 = compact. right: text for the label row's right side (status, clock, price).
func (m *Model) logoBlock(w, size int, stretch bool, label, right string, center bool) string {
	t := m.th
	rows := logoRows(size, stretch)
	lw := ansi.StringWidth(rows[0])
	var colored []string
	if t.Mono {
		colored = rows
	} else {
		colored = gradientRows(rows, t.Brand, true)
	}
	hatch := lipgloss.NewStyle().Foreground(t.Hatch)
	left := 3
	if center {
		left = max(3, (w-lw-2)/2)
	}
	rightN := max(0, w-left-lw-2)
	var b strings.Builder
	// the small label above the start of the word
	lab := lipgloss.NewStyle().Foreground(t.Pink).Render(label)
	labRow := strings.Repeat(" ", left+1) + lab
	if right != "" {
		gap := w - ansi.StringWidth(labRow) - ansi.StringWidth(right)
		if gap >= 2 {
			labRow += strings.Repeat(" ", gap) + right
		}
	}
	b.WriteString(ansi.Truncate(labRow, w, ""))
	for _, r := range colored {
		b.WriteString("\n")
		b.WriteString(hatch.Render(strings.Repeat(hatchRune, left)))
		b.WriteString(" ")
		b.WriteString(r)
		b.WriteString(" ")
		b.WriteString(hatch.Render(strings.Repeat(hatchRune, rightN)))
	}
	return b.String()
}

// logoLine is the one-line header (phones and short terminals): a short hatch, REWIND in the gradient, a hatch.
func (m *Model) logoLine(hatchN int) string {
	if m.ascii || m.th.Mono {
		return lipgloss.NewStyle().Bold(true).Render("REWIND")
	}
	h := lipgloss.NewStyle().Foreground(m.th.Hatch)
	s := h.Render(strings.Repeat(hatchRune, 2)) + " " + m.GradientText("REWIND", true)
	if hatchN > 0 {
		s += " " + h.Render(strings.Repeat(hatchRune, hatchN))
	}
	return s
}
