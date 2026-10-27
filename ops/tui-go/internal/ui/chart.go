package ui

import (
	"fmt"
	"math"
	"strings"
	"time"

	"charm.land/lipgloss/v2"
	"github.com/NimbleMarkets/ntcharts/v2/canvas"
	"github.com/NimbleMarkets/ntcharts/v2/canvas/graph"
	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

const yLabelW = 7

func chartNum(x int64) string {
	if math.Abs(float64(x)) >= 0.1*core.LAM {
		return core.FS(float64(x)/core.LAM, 2)
	}
	return core.FS(float64(x)/core.LAM, 3)
}

// chartNow is the scope's P&L now: the run P&L (the hero), or the day card's net.
func (m *Model) chartNow() int64 {
	if s := m.pnl(); s.Ok() {
		return s.Now
	}
	if m.todayOn {
		return m.todayCard.Net
	}
	return m.view.Total
}

// chartTitle: "Run P&L over time (SOL)", or the day's with s.
func (m *Model) chartTitle(short bool) string {
	switch {
	case m.todayOn && short:
		return "Today P&L (SOL)"
	case m.todayOn:
		return "Today's P&L over time (SOL)"
	case short:
		return "P&L (SOL)"
	}
	return "Run P&L over time (SOL)"
}

// chartTitleRight: "▲ ATH +0.606 4:21 PM · ▼ low −0.004 2:58 PM · now +0.588 (−0.018 from the ATH)".
func (m *Model) chartTitleRight(w int) string {
	t := m.th
	nv := m.chartNow()
	now := t.Lbl.Render("now ") + t.Money(nv, true, false).Render(core.Sol(nv, true, 3, true))
	s := m.pnl()
	if !s.Ok() || w < 90 {
		return now
	}
	a, at := s.ATH()
	l, lt := s.Low()
	var parts []string
	if a > 0 {
		parts = append(parts, t.Lbl.Render(m.g("▲", "^")+" ATH ")+t.Pos.Render(core.SolAuto(a))+t.Lbl.Render(" "+core.T12(at, false)))
	}
	if l < 0 {
		parts = append(parts, t.Lbl.Render(m.g("▼", "v")+" low ")+t.Neg.Render(core.SolAuto(l))+t.Lbl.Render(" "+core.T12(lt, false)))
	}
	if f := s.FromATH(); a > 0 && f < 0 && w >= 120 {
		now += t.Lbl.Render(" (") + t.Neg.Render(core.SolAuto(f)) + t.Lbl.Render(" from the ATH)")
	}
	parts = append(parts, now)
	return strings.Join(parts, t.Dim.Render("  "+m.g("·", "|")+"  "))
}

// chartPanel: the chart in a titled panel of outer size w x h.
func (m *Model) chartPanel(w, h int) string {
	body := m.chartBody(w-4, h-2)
	return m.panel(m.chartTitle(false), m.chartTitleRight(w-30), body, w, h)
}

// chartBlock: the chart under a rule title (no box), h lines in all.
func (m *Model) chartBlock(w, h int, title bool) string {
	if !title {
		return m.chartBody(w, h)
	}
	r := m.rule(m.chartTitle(false), m.chartTitleRight(w-30), w)
	if w < 60 {
		nv := m.chartNow()
		r = m.rule(m.chartTitle(true), m.th.Money(nv, true, false).Render(core.Sol(nv, true, 3, true)), w)
	}
	return r + "\n" + m.chartBody(w, h-1)
}

// chartBody draws the plot in w x h cells: y labels, the braille line, the zero line, the high / low markers, the
// time axis (cached until the series, the size or the pulse changes).
func (m *Model) chartBody(w, h int) string {
	pulse := -1
	if m.anim && !m.pulseAt.IsZero() {
		if age := m.now().Sub(m.pulseAt); age < 1200*time.Millisecond {
			pulse = int(age / (100 * time.Millisecond))
		}
	}
	s := m.pnl()
	var vals []int64
	var m0 int64
	if s.Ok() {
		vals, m0 = s.Vals, s.M0
	}
	key := fmt.Sprintf("%d|%d|%d|%d|%d|%v|%v|%d|%d|%v", w, h, len(vals), m0, m.chartNow(), m.dark, m.ascii, pulse, lastOr(vals), m.todayOn)
	if key == m.chartKey {
		return m.chartOut
	}
	out := m.drawChart(w, h, pulse)
	m.chartKey, m.chartOut = key, out
	return out
}

// asciiLine draws the line for --ascii: '*' at each cell column's last value, '|' up / down to its range and to the
// previous column (green above zero, red below).
func (m *Model) asciiLine(c *canvas.Model, series []int64, xOf func(int) int, pt func(int, int64) canvas.Point, ph int) {
	t := m.th
	type cell struct {
		first, mn, mx, last int
		ok                  bool
	}
	pw := c.Width()
	cols := make([]cell, pw)
	vals := make([]int64, pw)
	for i, x := range series {
		cx := min(pw-1, xOf(i)/2)
		r := max(0, min(ph-1, pt(xOf(i), x).Y/4))
		cc := &cols[cx]
		if !cc.ok {
			*cc = cell{r, r, r, r, true}
		} else {
			cc.mn, cc.mx, cc.last = min(cc.mn, r), max(cc.mx, r), r
		}
		vals[cx] = x
	}
	zr := pt(0, 0).Y / 4 // the zero line's row: green above it, red below
	put := func(x, y int, r rune, v int64) {
		st := t.Pos
		if y > zr || (y == zr && v < 0) {
			st = t.Neg
		}
		p := canvas.Point{X: x, Y: y}
		if c.Cell(p).Rune == 0 || r == '*' {
			c.SetCell(p, canvas.NewCellWithStyle(r, st))
		}
	}
	prev, px := -1, -1
	for x, cc := range cols {
		if !cc.ok {
			continue
		}
		// the columns without a point of their own: on the straight line from the previous one
		for k := px + 1; px >= 0 && k < x; k++ {
			r := prev + int(math.Round(float64(cc.first-prev)*float64(k-px)/float64(x-px)))
			put(k, r, '*', vals[x])
		}
		lo, hi := cc.mn, cc.mx
		if prev >= 0 && x == px+1 {
			lo, hi = min(lo, prev), max(hi, prev)
		}
		for y := lo; y <= hi; y++ {
			put(x, y, '|', vals[x])
		}
		put(x, cc.last, '*', vals[x])
		prev, px = cc.last, x
	}
}

func lastOr(s []int64) int64 {
	if len(s) == 0 {
		return 0
	}
	return s[len(s)-1]
}

func (m *Model) drawChart(w, h, pulse int) string {
	t := m.th
	ser := m.pnl()
	if h < 3 || w < yLabelW+10 {
		return block("", w, h)
	}
	if !ser.Ok() {
		return block(strings.Repeat(" ", yLabelW+1)+t.Lbl.Render("no P&L yet"), w, h)
	}
	series, m0 := ser.Vals, ser.M0
	n := len(series)
	ihi, ilo := ser.Hi, ser.Lo // the ATH and the low (the card's)
	vmax := max(0, series[ihi])
	vmin := min(0, series[ilo])
	// rows: [high marker] plot... [low marker] [axis] labels
	axisRows := 1
	if h >= 8 {
		axisRows = 2
	}
	topPad := 0
	if vmax > 0 && h >= 10 {
		topPad = 1
	}
	botPad := 0
	if vmin < 0 && h >= 11 {
		botPad = 1
	}
	ph := h - axisRows - topPad - botPad
	if ph < 1 {
		ph, topPad, botPad = max(1, h-axisRows), 0, 0
	}
	pw := w - yLabelW - 1
	span := float64(vmax - vmin)
	if span == 0 {
		span = 1
	}
	lo, hi := float64(vmin), float64(vmin)+span
	if vmax == 0 && vmin == 0 {
		lo, hi = -1, 1
	}
	c := canvas.New(pw, ph)
	gw := pw * 2
	gridOf := func() *graph.BrailleGrid { return graph.NewBrailleGrid(pw, ph, 0, float64(gw-1), lo, hi) }
	gPos, gNeg := gridOf(), gridOf()
	// the series reduced to one (first, min, max, last) per braille column
	type col struct {
		first, mn, mx, last int64
		ok                  bool
	}
	cols := make([]col, gw)
	xOf := func(i int) int {
		if n == 1 {
			return gw - 1
		}
		return int(math.Round(float64(i) * float64(gw-1) / float64(n-1)))
	}
	for i, x := range series {
		k := xOf(i)
		cc := &cols[k]
		if !cc.ok {
			*cc = col{x, x, x, x, true}
		} else {
			cc.mn, cc.mx, cc.last = min(cc.mn, x), max(cc.mx, x), x
		}
	}
	pt := func(x int, y int64) canvas.Point {
		return gPos.GridPoint(canvas.Float64Point{X: float64(x), Y: float64(y)})
	}
	setSeg := func(x1 int, y1 int64, x2 int, y2 int64) {
		// split at the zero crossing: green above, red below
		if (y1 > 0 && y2 < 0) || (y1 < 0 && y2 > 0) {
			f := float64(y1) / float64(y1-y2)
			xm := float64(x1) + f*float64(x2-x1)
			zp := gPos.GridPoint(canvas.Float64Point{X: xm, Y: 0})
			a, b := pt(x1, y1), pt(x2, y2)
			g1, g2 := gPos, gNeg
			if y1 < 0 {
				g1, g2 = gNeg, gPos
			}
			for _, p := range graph.GetLinePoints(a, zp) {
				g1.Set(p)
			}
			for _, p := range graph.GetLinePoints(zp, b) {
				g2.Set(p)
			}
			return
		}
		g := gPos
		if y1 < 0 || y2 < 0 {
			g = gNeg
		}
		for _, p := range graph.GetLinePoints(pt(x1, y1), pt(x2, y2)) {
			g.Set(p)
		}
	}
	px, py := -1, int64(0)
	lastX := 0
	for k, cc := range cols {
		if !cc.ok {
			continue
		}
		if px >= 0 {
			setSeg(px, py, k, cc.first)
		}
		if cc.mn != cc.mx {
			setSeg(k, cc.mn, k, cc.mx)
		} else {
			setSeg(k, cc.first, k, cc.first)
		}
		px, py, lastX = k, cc.last, k
	}
	posS, negS := t.Pos, t.Neg
	if m.ascii {
		m.asciiLine(&c, series, xOf, pt, ph)
	} else {
		graph.DrawBraillePatterns(&c, canvas.Point{X: 0, Y: 0}, gPos.BraillePatterns(), posS)
		graph.DrawBraillePatterns(&c, canvas.Point{X: 0, Y: 0}, gNeg.BraillePatterns(), negS)
	}
	// the zero line
	zrow := gPos.GridPoint(canvas.Float64Point{X: 0, Y: 0}).Y / 4
	zrow = max(0, min(ph-1, zrow))
	zr := '┈'
	if m.ascii {
		zr = '-'
	}
	zs := t.Dim
	for x := 0; x < pw; x++ {
		p := canvas.Point{X: x, Y: zrow}
		if c.Cell(p).Rune == 0 {
			c.SetCell(p, canvas.NewCellWithStyle(zr, zs))
		}
	}
	// the newest point pulses once (a bright dot fading back into the line)
	if pulse >= 0 && !t.Mono {
		last := series[n-1]
		p := pt(lastX, last)
		cell := canvas.Point{X: min(pw-1, p.X/2), Y: min(ph-1, p.Y/4)}
		base := t.Green
		if last < 0 {
			base = t.Red
		}
		k := float64(pulse) / 12
		col := lipgloss.Blend1D(12, lipgloss.Lighten(base, 0.5), base)[min(11, int(k*12))]
		r := '●'
		if m.ascii {
			r = '*'
		}
		c.SetCell(cell, canvas.NewCellWithStyle(r, lipgloss.NewStyle().Foreground(col).Bold(true)))
	}
	plot := strings.Split(c.View(), "\n")
	// y labels: max / 0 / min
	ylab := map[int]string{}
	if vmax > 0 && zrow > 0 {
		ylab[0] = chartNum(vmax)
	}
	ylab[zrow] = "0"
	if vmin < 0 && zrow < ph-1 {
		ylab[ph-1] = chartNum(vmin)
	}
	axV, axT, axZ := "│", "┤", "┼"
	if m.ascii {
		axV, axT, axZ = "|", "+", "+"
	}
	var out []string
	cellX := func(i int) int { return min(pw-1, xOf(i)/2) }
	marker := func(i int, sym string, val int64, tns float64, st lipgloss.Style) string {
		lab := sym + " " + core.Sol(val, true, 3, true) + " " + core.T12(tns, false)
		x := cellX(i)
		row := []rune(strings.Repeat(" ", pw))
		start := x
		if x+ansi.StringWidth(lab) > pw {
			start = max(0, x-ansi.StringWidth(lab)+1)
		}
		s := string(row[:start]) + st.Render(lab)
		return strings.Repeat(" ", yLabelW+1) + s
	}
	if topPad == 1 {
		out = append(out, marker(ihi, m.g("▲", "^"), series[ihi], float64(m0+int64(ihi))*60e9, t.PosB))
	}
	for r := 0; r < ph; r++ {
		lab, ok := ylab[r]
		ax := axV
		if ok {
			ax = axT
			if r == zrow {
				ax = axZ
			}
		}
		line := t.Lbl.Render(padLeft(lab, yLabelW)) + t.Rule.Render(ax)
		if r < len(plot) {
			line += plot[r]
		}
		out = append(out, line)
	}
	if botPad == 1 {
		out = append(out, marker(ilo, m.g("▼", "v"), series[ilo], float64(m0+int64(ilo))*60e9, t.NegB))
	}
	// the time axis: 3-5 labels, 12-hour PKT
	nl := 3
	if pw >= 90 {
		nl = 5
	} else if pw >= 60 {
		nl = 4
	}
	labRow := []rune(strings.Repeat(" ", pw))
	axisRow := []rune(strings.Repeat(m.g("─", "-"), pw))
	for j := 0; j < nl; j++ {
		p := int(math.Round(float64(j) * float64(pw-1) / float64(nl-1)))
		axisRow[p] = []rune(m.g("┴", "+"))[0]
		mi := int(math.Round(float64(p) / float64(max(1, pw-1)) * float64(n-1)))
		txt := []rune(core.T12(float64(m0+int64(mi))*60e9, false))
		st := p - len(txt)/2
		if j == 0 {
			st = p
		} else if j == nl-1 {
			st = p - len(txt) + 1
		}
		st = max(0, min(pw-len(txt), st))
		free := true
		for k := max(0, st-1); k < min(pw, st+len(txt)+1); k++ {
			if labRow[k] != ' ' {
				free = false
			}
		}
		if free {
			copy(labRow[st:], txt)
		}
	}
	if axisRows == 2 {
		corner := m.g("└", "+")
		out = append(out, strings.Repeat(" ", yLabelW)+t.Rule.Render(corner+string(axisRow)))
	}
	out = append(out, strings.Repeat(" ", yLabelW+1)+t.Lbl.Render(string(labRow)))
	return block(strings.Join(out, "\n"), w, h)
}
