package ui

// dip26 (10-30): the re-arm's own section and the send-path A/B on the Engine tab, the "via" code of the trades.
// Shown only when the run has them (older runs render exactly as before).

import (
	"fmt"
	"strings"
	"time"

	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

// abSummary: the A/B of the sessions in scope: rebuilt when a trade or the scope changes, else at most every 5 s while
// the records move (its percentiles sort thousands of buckets; the figures are aggregates of thousands of tries).
func (m *Model) abSummary() *core.ABSummary {
	M := m.ctx.Src.Model
	v := m.view
	key := fmt.Sprintf("%d|%d|%d", m.scope, M.TradeVer, int64(v.NowNS()/60e9))
	if m.abSum != nil && key == m.abKey && (M.Version == m.abVer || m.now().Sub(m.abAt) < 5*time.Second) {
		return m.abSum
	}
	sel := v.Sessions
	if v.Scope >= 0 {
		sel = []*core.Sess{v.S}
	}
	s := core.ABOf(sel, v.Trades, M, v.NowNS())
	m.abKey, m.abSum, m.abVer, m.abAt = key, &s, M.Version, m.now()
	return m.abSum
}

// rearmTitle: the re-arm's setting for a section's title ("● 0.65 SOL · gap 20 · QUIET 6:2 · R5 off").
func (m *Model) rearmTitle(short bool) string {
	t := m.th
	v := m.view
	c := v.RA.Cfg
	st := "on"
	if !c.On {
		st = "part"
	}
	sep := m.g(" · ", " | ")
	if short {
		return t.StateDot(st, m.ascii) + t.Lbl.Render(" "+core.RearmShort(c))
	}
	x := core.F(float64(c.Spend)/core.LAM, 2) + " SOL" + sep + "gap " + core.Itoa(c.Gap)
	if c.Quiet != "" {
		x += sep + "QUIET " + c.Quiet
	}
	if c.HasR5 {
		x += sep + "R5 " + map[bool]string{true: "on", false: "off"}[c.R5]
	}
	return t.StateDot(st, m.ascii) + t.Lbl.Render(" "+x)
}

// wrapKV: a label and a long plain value wrapped under it.
func (m *Model) wrapKV(label string, lw int, text string, inner int, st lipgloss.Style) []string {
	var out []string
	for i, l := range core.WrapText(text, max(10, inner-lw), 0) {
		lab := ""
		if i == 0 {
			lab = label
		}
		out = append(out, m.kv(lab, lw, st.Render(l)))
	}
	return out
}

// itemLines: "label  a 3 · b 2 · ..." packed into lines of at most inner cells, whole items only (a continuation line
// never starts with the separator).
func (m *Model) itemLines(label string, lw int, items []string, inner int, st lipgloss.Style) []string {
	t := m.th
	sep := " " + m.g("·", "|") + " "
	if len(items) == 0 {
		return []string{m.kv(label, lw, st.Render(core.G.Dash))}
	}
	var lines [][]string
	var cur []string
	width := 0
	for _, it := range items {
		w := ansi.StringWidth(it)
		if len(cur) > 0 && lw+width+ansi.StringWidth(sep)+w > inner {
			lines = append(lines, cur)
			cur, width = nil, 0
		}
		if len(cur) > 0 {
			width += ansi.StringWidth(sep)
		}
		cur = append(cur, it)
		width += w
	}
	lines = append(lines, cur)
	out := make([]string, len(lines))
	for i, l := range lines {
		lab := ""
		if i == 0 {
			lab = label
		}
		parts := make([]string, len(l))
		for j, it := range l {
			parts[j] = st.Render(it)
		}
		out[i] = m.kv(lab, lw, strings.Join(parts, t.Dim.Render(sep)))
	}
	return out
}

func kvItems(c *core.OCounter, name func(string) string) []string {
	if c == nil {
		return nil
	}
	var out []string
	for _, kv := range c.MostCommon() {
		k := kv.K
		if name != nil {
			k = name(k)
		}
		out = append(out, k+" "+core.IC(kv.N))
	}
	return out
}

// rearmLines: the RE-ARM section (its own money, windows, skips / ends by reason, exits, the engine's counters, the
// observatory's paper re-arm) and its title's right side.
func (m *Model) rearmLines(w int) ([]string, string) {
	t := m.th
	v := m.view
	ra := v.RA
	inner := w
	if w >= 70 {
		inner = w - 4
	}
	sep := t.Dim.Render(" " + m.g("·", "|") + " ")
	fit := func(cands ...string) string {
		for _, c := range cands {
			if ansi.StringWidth(c) <= inner {
				return c
			}
		}
		return cands[len(cands)-1]
	}
	var out []string
	out = append(out, m.kv("net", 11, m.money(ra.Net, true, 4)))
	fs := t.Val
	if ra.Fees != 0 {
		fs = t.Neg
	}
	real := t.Money(ra.Real, true, false).Render(core.SolS(ra.Real))
	rent := t.Lbl.Render("rent back ") + t.Money(ra.Rent, true, false).Render(core.SolS(ra.Rent))
	failed := t.Lbl.Render("failed ") + fs.Render(core.SolS(-ra.Fees)) + t.Lbl.Render(" "+core.IC(ra.FeeN)+" tries")
	if one := m.kv("realized", 11, real+t.Lbl.Render("   ")+rent+t.Lbl.Render("   ")+failed); ansi.StringWidth(one) <= inner {
		out = append(out, one)
	} else {
		out = append(out, m.kv("realized", 11, real+t.Lbl.Render("   ")+rent), m.kv("failed", 11, fs.Render(core.SolS(-ra.Fees))+t.Lbl.Render("   "+core.IC(ra.FeeN)+" tries x "+core.IC(v.PSFailEach))))
	}
	nl := ra.NReal - ra.Wins
	wl := t.Val.Render(fmt.Sprintf("%d fills", ra.Fills)) + sep + t.Val.Render(fmt.Sprintf("%d W / %d L", ra.Wins, nl))
	if ra.NReal > 0 {
		wl += t.Lbl.Render(fmt.Sprintf(" (%.0f%%)", float64(ra.Wins)/float64(ra.NReal)*100))
	}
	avgS := ""
	if ra.Fills > 0 {
		avg := int64(float64(ra.Real) / float64(ra.Fills))
		avgS = sep + t.Lbl.Render("avg/fill ") + t.Money(avg, true, false).Render(core.SolS(avg))
	}
	out = append(out, fit(m.kv("wins", 11, wl+avgS), m.kv("wins", 11, wl)))
	now := t.Val.Render(fmt.Sprint(ra.OpenNow))
	if ra.OpenNow > 0 && v.Running {
		now = t.B.Render(fmt.Sprint(ra.OpenNow))
	}
	wa := t.Val.Render(core.IC(ra.Arms)) + t.Lbl.Render(" armed")
	nowS := now + t.Lbl.Render(" now")
	aw := t.Lbl.Render(core.IC(ra.ArmedWait) + " after waiting")
	df := t.Lbl.Render(core.IC(ra.Defers) + " deferred")
	tr := t.Lbl.Render(core.IC(ra.Sent) + " tries")
	out = append(out, fit(m.kv("windows", 11, wa+sep+nowS+sep+aw+sep+df+sep+tr), m.kv("windows", 11, wa+sep+nowS+sep+df+sep+tr), m.kv("windows", 11, wa+sep+nowS+sep+tr)))
	out = append(out, m.itemLines("skipped", 11, kvItems(ra.Skips, core.SkipName), inner, t.Val)...)
	out = append(out, m.itemLines("ended", 11, kvItems(ra.Ends, nil), inner, t.Val)...)
	if ra.Exits != nil && len(ra.Exits.Keys) > 0 {
		var parts []string
		for _, k := range ra.Exits.Sorted() {
			e := ra.Exits.M[k]
			parts = append(parts, t.Val.Render(k+" "+core.IC(e.N))+" "+t.Money(e.Pnl, true, false).Render(core.SolS(e.Pnl)))
		}
		line := ""
		for _, p := range parts {
			if line != "" && ansi.StringWidth(m.kv("exits", 11, line+sep+p)) > inner {
				out = append(out, m.kv("exits", 11, line))
				line = ""
			}
			if line != "" {
				line += sep
			}
			line += p
		}
		if line != "" {
			out = append(out, m.kv("exits", 11, line))
		}
	}
	if ra.OpenPos > 0 {
		out = append(out, m.kv("open now", 11, t.Warn.Render(fmt.Sprint(ra.OpenPos))))
	}
	if ra.Best != nil {
		for _, bw := range []struct {
			l  string
			tr *core.Trade
		}{{"best", ra.Best}, {"worst", ra.Worst}} {
			x := bw.tr
			why := core.ExitShort(x.PExit, x.PExit)
			if why == "" {
				why = "?"
			}
			out = append(out, cut(m.kv(bw.l, 11, m.mintLink(x.Mint, core.Short(x.Mint, 6), t.Val)+" "+t.Money(x.Pnl, true, false).Render(core.SolS(x.Pnl))+
				t.Lbl.Render("  "+why+" "+core.KindOf(x.Client)+" "+core.PathCode(x.Path)+"  "+core.T12(float64(x.T), false))), inner))
		}
	}
	if e := ra.Eng; e.Has {
		x := t.Lbl.Render("candidates ") + t.Val.Render(core.IC(e.Cands)) + sep + t.Lbl.Render("checks ") + t.Val.Render(core.IC(e.Checks)) + sep +
			t.Lbl.Render("pending ") + t.Val.Render(core.IC(e.Pending))
		six := sep + t.Lbl.Render("sells "+m.g("≥", ">=")+" 6% ") + t.Val.Render(core.IC(e.Sells6))
		out = append(out, fit(m.kv("engine", 11, x+six+t.Dim.Render("  (60 s status)")), m.kv("engine", 11, x+six), m.kv("engine", 11, x)))
	}
	if ra.HasPaper {
		p := t.Val.Render(core.IC(ra.Paper.N)) + t.Lbl.Render(" windows")
		if ra.Paper.HasFills {
			p += t.Lbl.Render(" / ") + t.Val.Render(core.IC(ra.Paper.Fills)) + t.Lbl.Render(" fills")
		}
		out = append(out, fit(m.kv("paper", 11, t.Lbl.Render("observatory ")+p+t.Dim.Render("  (log only)")), m.kv("paper", 11, p)))
	}
	right := m.rearmTitle(false)
	if ansi.StringWidth(right)+12 > w {
		right = m.rearmTitle(true)
	}
	return out, right
}

// abLines: the SEND PATHS A/B section (per path: tries, refused, landed, same slot, send -> land, acks, fills and their
// P&L; by leader client; the engine's not-sent; health) and its title's right side.
func (m *Model) abLines(w int) ([]string, string) {
	t := m.th
	s := m.abSummary()
	inner := w
	if w >= 70 {
		inner = w - 4
	}
	sep := t.Dim.Render(" " + m.g("·", "|") + " ")
	ne := m.g("≠", "!=")
	var out []string
	if len(s.Rows) == 0 {
		return []string{t.Lbl.Render("no tries yet")}, ""
	}
	pct := func(n, d int64) string {
		if d == 0 {
			return core.G.Dash
		}
		return core.F(float64(n)/float64(d)*100, 0) + "%"
	}
	ref := func(r core.ABRow, long bool) string {
		if !s.Rule {
			return "?"
		}
		sh, ok := r.RefusedShare()
		if !ok {
			return core.G.Dash
		}
		if long {
			return core.IC(r.Refused) + " " + core.F(sh*100, 1) + "%"
		}
		return core.F(sh*100, 1) + "%"
	}
	q := func(r core.ABRow, both bool) string {
		if !r.HasQ {
			return core.G.Dash
		}
		if both {
			return core.F(r.P50, 0) + "/" + core.F(r.P90, 0)
		}
		return core.F(r.P50, 0)
	}
	mode := 0 // 0 full, 1 medium, 2 narrow
	switch {
	case inner < 60:
		mode = 2
	case inner < 80:
		mode = 1
	}
	var hdr []string
	var rows [][]string
	var styles [][]lipgloss.Style
	for _, r := range s.Rows {
		pnl := core.SolS(r.Pnl)
		ps := t.Money(r.Pnl, true, false)
		as := t.Val
		if r.AckFail() > 0 {
			as = t.Warn
		}
		rs := t.Val
		if sh, ok := r.RefusedShare(); ok && sh > 0.01 {
			rs = t.Warn
		}
		switch mode {
		case 0:
			hdr = []string{"path", "tries", "refused", "landed", "same", "p50/p90", "ack" + ne + "200", "fills", "P&L SOL"}
			rows = append(rows, []string{core.RuneSlice(r.Path, 14), core.IC(r.Sent), ref(r, true), pct(r.Landed, r.Land), pct(r.Same, r.Seen), q(r, true),
				core.IC(r.AckFail()), core.IC(r.Fills), pnl})
			styles = append(styles, []lipgloss.Style{t.Val, t.Val, rs, t.Val, t.Val, t.Val, as, t.Val, ps})
		case 1:
			hdr = []string{"path", "tries", "refused", "same", "p50", "fills", "P&L SOL"}
			rows = append(rows, []string{core.RuneSlice(r.Path, 13), core.IC(r.Sent), ref(r, false), pct(r.Same, r.Seen), q(r, false), core.IC(r.Fills), pnl})
			styles = append(styles, []lipgloss.Style{t.Val, t.Val, rs, t.Val, t.Val, t.Val, ps})
		default:
			hdr = []string{"", "tries", "ref", "same", "p50", "P&L"}
			rows = append(rows, []string{core.PathCode(r.Path), core.IC(r.Sent), ref(r, false), pct(r.Same, r.Seen), q(r, false), core.Sol(r.Pnl, true, 3, true)})
			styles = append(styles, []lipgloss.Style{t.Acc, t.Val, rs, t.Val, t.Val, ps})
		}
	}
	right := map[int]bool{}
	for i := 1; i < len(hdr); i++ {
		right[i] = true
	}
	out = append(out, strings.Split(m.kvTable(hdr, rows, right, func(r, c int) lipgloss.Style { return styles[r][c] }), "\n")...)
	if mode == 2 {
		var leg []string
		for _, r := range s.Rows {
			leg = append(leg, core.PathCode(r.Path)+" "+r.Path)
		}
		out = append(out, m.wrapKV("", 0, strings.Join(leg, " "+core.G.Sep+" "), inner, t.Dim)...)
	}
	// what the columns mean, and what the engine counted for every path together
	var note []string
	if s.Rule {
		note = append(note, "refused = a path's own try skipped between sent ones (inferred)")
	}
	if mode == 0 {
		note = append(note, "landed = not unseen; same = in the send slot; p50/p90 = send"+m.g("→", "->")+"land ms")
	} else {
		note = append(note, "same = in the send slot; p50 = send"+m.g("→", "->")+"land ms")
	}
	out = append(out, m.wrapKV("", 0, strings.Join(note, "; "), inner, t.Dim)...)
	ns := kvItems(s.NotSent, nil)
	if len(ns) == 0 {
		ns = []string{"none"}
	}
	ns[len(ns)-1] += " (engine, all paths)"
	out = append(out, m.itemLines("not sent", 11, ns, inner, t.Val)...)
	// ack failures: their codes
	for _, r := range s.Rows {
		if r.AckFail() == 0 {
			continue
		}
		var parts []string
		for _, kv := range r.Codes.MostCommon() {
			code := kv.K
			if code == "0" {
				code = "no answer"
			}
			parts = append(parts, code+" "+core.G.X+core.IC(kv.N))
		}
		if r.AckNone > 0 {
			parts = append(parts, "none "+core.G.X+core.IC(r.AckNone))
		}
		out = append(out, m.wrapKV("acks", 11, r.Path+": "+strings.Join(parts, ", ")+" of "+core.IC(r.Land), inner, t.Warn)...)
	}
	// the health edges of the A/B's paths (SEND-PATH UNHEALTHY / RECOVERED)
	var hp []string
	anyEdge := false
	for _, r := range s.Rows {
		st := t.Good.Render("ok")
		if e := r.Edge; e != nil && (e.Downs > 0 || e.Ups > 0) {
			anyEdge = true
			if e.Down {
				st = t.Bad.Render("UNHEALTHY")
			}
			st += t.Lbl.Render(fmt.Sprintf(" (%d%s %d%s)", e.Downs, m.g("↓", "v"), e.Ups, m.g("↑", "^")))
		}
		hp = append(hp, t.Val.Render(r.Path+" ")+st)
	}
	if anyEdge {
		out = append(out, cut(m.kv("health", 11, strings.Join(hp, sep)), inner))
	}
	// by leader client: each path's tries seen, same slot, p50 (the families that matter)
	if inner >= 52 && len(s.Rows) >= 2 && len(s.Rows) <= 3 && len(s.Kinds) > 0 {
		hdr := []string{"client"}
		for _, r := range s.Rows {
			c := core.PathCode(r.Path)
			hdr = append(hdr, c+" n", "same", "p50")
		}
		var krows [][]string
		var kcells [][]float64
		for _, k := range s.Kinds {
			row := []string{core.RuneSlice(k, 10)}
			cells := []float64{-1}
			for _, r := range s.Rows {
				kr := r.Kinds[k]
				if kr == nil {
					row = append(row, "0", core.G.Dash, core.G.Dash)
					cells = append(cells, -1, -1, -1)
					continue
				}
				p50 := core.G.Dash
				pv := -1.0
				if kr.HasQ {
					p50, pv = core.F(kr.P50, 0), kr.P50
				}
				row = append(row, core.IC(kr.Seen), pct(kr.Same, kr.Seen), p50)
				cells = append(cells, -1, -1, pv)
			}
			krows = append(krows, row)
			kcells = append(kcells, cells)
		}
		rt := map[int]bool{}
		for i := 1; i < len(hdr); i++ {
			rt[i] = true
		}
		out = append(out, strings.Split(m.kvTable(hdr, krows, rt, func(r, c int) lipgloss.Style {
			if c == 0 {
				return t.Val
			}
			if x := kcells[r][c]; x >= 0 {
				return m.latStyle(x)
			}
			return t.Lbl
		}), "\n")...)
		out = append(out, t.Dim.Render("by leader client: n = tries seen, same slot, p50 send"+m.g("→", "->")+"land ms"))
	}
	rgt := ""
	if s.MaxPerSec > 0 {
		rgt = t.Lbl.Render(fmt.Sprintf("caps %d/s %s %d/s a path", s.MaxPerSec, m.g("·", "|"), s.PathMaxPerSec))
	}
	return out, rgt
}

// viaOn: the trades table's "via" column (the run's pre-send tries go over two or more paths).
func (m *Model) viaOn() bool { return m.view != nil && m.view.AB.On }

// scrPresend26: the Engine tab (2) of a dip26 run: the caps, the T2 windows' RESULT, the RE-ARM, then the A/B (first on
// the right: what the owner watches), the latency of every try (T2 + re-arm), QUIET, exits, paper, windows.
func (m *Model) scrPresend26(w, cw int, title, right string, C, A, E, Wn, Q, P, Ss []string, latR string, all core.AggPS) string {
	v := m.view
	rw := m.lastW(w, cw)
	resT, exT := "RESULT", "EXITS"
	if v.RA.On {
		resT, exT = "RESULT "+m.g("·", "|")+" T2", "EXITS "+m.g("·", "|")+" T2"
	}
	sec := func(width int) (ra []string, rr string, ab []string, ar string) {
		if v.RA.On {
			ra, rr = m.rearmLines(width)
		}
		if v.AB.On {
			ab, ar = m.abLines(width)
		}
		return
	}
	if w < 120 {
		ra, rr, ab, ar := sec(w)
		secs := []string{m.section(title, right, C, w), m.section(resT, "", A, w)}
		if v.RA.On {
			secs = append(secs, m.section("RE-ARM", rr, ra, w))
		}
		if v.AB.On {
			secs = append(secs, m.section("SEND PATHS A/B", ar, ab, w))
		}
		if v.FAB.On { // dip37
			secs = append(secs, m.section("FEE A/B", "", m.fabLines(w), w))
		}
		secs = append(secs, m.section("LATENCY", latR, m.latencyLines(w, all), w), m.section("QUIET", "", Q, w), m.section(exT, "", E, w),
			m.section("PAPER vs LIVE", "", P, w), m.section("WINDOWS", "", Wn, w))
		if len(Ss) > 0 {
			secs = append(secs, m.section("SESSIONS", "", Ss, w))
		}
		return strings.Join(secs, "\n")
	}
	ra, rr, _, _ := sec(cw)
	_, _, ab, ar := sec(rw)
	left := []string{m.section(title, right, C, cw), m.section(resT, "", A, cw)}
	if v.RA.On {
		left = append(left, m.section("RE-ARM", rr, ra, cw))
	}
	left = append(left, m.section(exT, "", E, cw), m.section("WINDOWS", "", Wn, cw))
	var rightCol []string
	if v.AB.On {
		rightCol = append(rightCol, m.section("SEND PATHS A/B", ar, ab, rw))
	}
	if v.FAB.On { // dip37
		rightCol = append(rightCol, m.section("FEE A/B", "", m.fabLines(rw), rw))
	}
	rightCol = append(rightCol, m.section("LATENCY", latR, m.latencyLines(rw, all), rw), m.section("QUIET", "", Q, rw), m.section("PAPER vs LIVE", "", P, rw))
	if len(Ss) > 0 {
		rightCol = append(rightCol, m.section("SESSIONS", "", Ss, rw))
	}
	return hcat(1, strings.Join(left, "\n"), strings.Join(rightCol, "\n"))
}

// raLive (dip26): LIVE's re-arm line: fills, wins, its net, the windows armed now (a spinner) and in all.
func (m *Model) raLive(cw int, sep string, frames []string) string {
	t := m.th
	v := m.view
	ra := v.RA
	now := t.Val.Render(fmt.Sprint(ra.OpenNow))
	if ra.OpenNow > 0 && v.Running {
		sp := frames[m.armFrame%len(frames)]
		if m.ascii {
			sp = []string{"|", "/", "-", "\\"}[m.armFrame%4]
		}
		now = t.Acc.Render(sp) + " " + t.B.Render(fmt.Sprint(ra.OpenNow))
	}
	fl := t.Val.Render(fmt.Sprintf("%d fills", ra.Fills)) + sep + t.Val.Render(fmt.Sprintf("%d W", ra.Wins))
	if ra.NReal > 0 {
		fl += t.Lbl.Render(fmt.Sprintf(" %.0f%%", float64(ra.Wins)/float64(ra.NReal)*100))
	}
	net := t.Money(ra.Net, true, false).Render(core.SolS(ra.Net))
	win := now + t.Lbl.Render(" now") + sep + t.Lbl.Render(core.IC(ra.Arms)+" win.")
	for _, c := range []string{fl + sep + net + sep + win, fl + sep + net + sep + now + t.Lbl.Render(" now"), fl + sep + net} {
		if x := m.kv("re-arm", 10, c); ansi.StringWidth(x) <= cw {
			return x
		}
	}
	return cut(m.kv("re-arm", 10, fl), cw)
}

// raCompact (dip26): the one-line LIVE of the medium layout: T2 and the re-arm, the windows armed now.
func (m *Model) raCompact(w int, sep string) string {
	t := m.th
	v := m.view
	t2, ra := v.T2, v.RA
	a := t.Lbl.Render("T2 ") + t.Val.Render(fmt.Sprintf("%d fills", t2.Fills)) + sep + t.Val.Render(fmt.Sprintf("%d W", t2.Wins))
	b := t.Lbl.Render("re-arm ") + t.Val.Render(fmt.Sprintf("%d fills", ra.Fills)) + sep + t.Val.Render(fmt.Sprintf("%d W", ra.Wins)) + t.Lbl.Render(" ") +
		t.Money(ra.Net, true, false).Render(core.SolS(ra.Net))
	now := v.PSOpenNow + ra.OpenNow
	arm := t.Val.Render(fmt.Sprint(now))
	if now > 0 && v.Running {
		frames := []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}
		sp := frames[m.armFrame%len(frames)]
		if m.ascii {
			sp = []string{"|", "/", "-", "\\"}[m.armFrame%4]
		}
		arm = t.Acc.Render(sp) + " " + t.B.Render(fmt.Sprint(now))
	}
	win := t.Dim.Render("   ") + t.Lbl.Render("windows ") + arm + t.Lbl.Render(" now")
	for _, c := range []string{a + t.Dim.Render("   ") + b + win, a + t.Dim.Render("   ") + b} {
		if ansi.StringWidth(c) <= w {
			return c
		}
	}
	return cut(a+t.Dim.Render("  ")+b, w)
}

// helpNotes26: the help's notes on the re-arm and the A/B (dip26 runs only).
func helpNotes26(ra, ab bool) [][2]string {
	var out [][2]string
	if ra {
		out = append(out, [2]string{"re-arm", "live re-arm windows (records \"kind\":\"rearm\"; RA in the trades): their own money, windows, skips and ends; T2 = the other pre-send windows; T2 + re-arm + regular = RUN P&L"})
	}
	if ab {
		out = append(out, [2]string{"A/B", "the pre-send tries alternate between two send paths (via HL / AS in the trades); refused = a path's own try skipped between sent ones (inferred); alert when a path refuses > 1% or its acks fail > 1% in 10 min"})
	}
	return out
}
