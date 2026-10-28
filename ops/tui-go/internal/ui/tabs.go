package ui

import (
	"fmt"
	"os"
	"sort"
	"strings"
	"time"

	"charm.land/bubbles/v2/key"
	"charm.land/lipgloss/v2"
	"charm.land/lipgloss/v2/table"
	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

// section is a titled panel whose height fits its lines (under 70 columns: a titled rule, no box, so phones keep
// every column for the content).
func (m *Model) section(title, right string, ls []string, w int) string {
	if w < 70 {
		return m.rule(title, right, w) + "\n" + strings.Join(ls, "\n")
	}
	return m.panel(title, right, strings.Join(ls, "\n"), w, len(ls)+2)
}

// twoCols places left and right section stacks side by side (wide) or one under the other.
func (m *Model) twoCols(w int, left, right []string) string {
	if w >= 120 {
		cw := (w - 1) / 2
		// each column is fitted to its width, so the right one always starts at the same column
		return hcat(1, block(strings.Join(left, "\n"), cw, 0), block(strings.Join(right, "\n"), w-cw-1, 0))
	}
	return strings.Join(append(left, right...), "\n")
}

func (m *Model) colW(w int) int {
	if w >= 120 {
		return (w - 1) / 2
	}
	return w
}

// kvTable renders rows of cells with the Lip Gloss table (no borders, a rule under the header).
func (m *Model) kvTable(headers []string, rows [][]string, right map[int]bool, cellStyle func(r, c int) lipgloss.Style) string {
	t := m.th
	tb := table.New().
		Border(lipgloss.NormalBorder()).
		BorderTop(false).BorderBottom(false).BorderLeft(false).BorderRight(false).BorderColumn(false).
		BorderHeader(len(headers) > 0).
		BorderStyle(t.Rule).
		Rows(rows...).
		StyleFunc(func(row, col int) lipgloss.Style {
			s := lipgloss.NewStyle().PaddingRight(2)
			if right[col] {
				s = s.Align(lipgloss.Right)
			}
			if row == table.HeaderRow {
				return s.Inherit(t.Lbl)
			}
			if cellStyle != nil {
				return s.Inherit(cellStyle(row, col))
			}
			return s.Inherit(t.Val)
		})
	if len(headers) > 0 {
		tb = tb.Headers(headers...)
	}
	return tb.Render()
}

// ------------------------------------------------------------------------------------------------- 2 pre-send

func (m *Model) scrPresend(w, bh int) string {
	t := m.th
	v := m.view
	ps, pc, S := v.PS, v.PSCfg, v.S
	cw := m.colW(w)
	it := v.ItemByKey("ps")
	if !ps.Active && len(pc) == 0 {
		ls := []string{t.Lbl.Render("off in this run")}
		if ps.Paper {
			ls = append(ls, "", m.kv("paper (c)", 12, t.Val.Render(fmt.Sprintf("%d fills  gross %s  net %s SOL", ps.PaperFills, core.FS(ps.PaperGross, 3), core.FS(ps.PaperNet, 3)))))
		}
		return m.section("PRE-SEND LIVE", "", ls, w)
	}
	sep := t.Dim.Render(" " + m.g("·", "|") + " ")
	// caps (per session)
	var C []string
	capN, _ := pc["max_fills"].(core.Num)
	budN, _ := pc["fee_budget"].(core.Num)
	var sf, sfee int64
	if S.PSRec {
		sf, sfee = S.PSFills, S.PSFees()
	} else {
		sf, sfee = int64(len(S.LogPSReal)), S.LogPSFees
	}
	gw := max(8, min(40, cw-11-12-10)) // label 11, value 12, " 100% used"
	capS := "?"
	fr := -1.0
	if capN.Truthy() {
		capS = capN.Repr()
		fr = float64(sf) / capN.Float()
	}
	fl := m.kv("fills", 11, t.Val.Render(padRight(fmt.Sprintf("%d / %s", sf, capS), 12)))
	if fr >= 0 {
		fl += m.bar(fr, gw) + t.Lbl.Render(fmt.Sprintf(" %.0f%%", fr*100))
	}
	C = append(C, fl)
	bud := budN.Float()
	fb := m.kv("fee budget", 11, t.Val.Render(padRight(core.F(float64(sfee)/core.LAM, 3)+"/"+core.F(bud/core.LAM, 2), 12)))
	if budN.Truthy() {
		f := float64(sfee) / bud
		fb += m.usageBar(f, gw) + t.Lbl.Render(fmt.Sprintf(" %.0f%% used", f*100))
	}
	C = append(C, fb)
	arm := t.Val.Render(fmt.Sprint(v.PSOpenNow))
	if v.PSOpenNow > 0 {
		arm = t.B.Render(fmt.Sprint(v.PSOpenNow))
	}
	tries := t.Lbl.Render("tries " + core.IC(ps.Sent))
	if ps.Dry > 0 {
		tries += t.Lbl.Render(" (+" + core.IC(ps.Dry) + " dry)")
	}
	C = append(C, m.kv("armed now", 11, arm+t.Lbl.Render(" window(s)")+sep+t.Lbl.Render("armed "+core.IC(ps.Armed))+sep+tries))
	if v.PSStopped != "" {
		C = append(C, m.kv("stopped", 11, t.Warn.Render(v.PSStopped)+t.Lbl.Render("  no new attempts this session")))
	}
	title := "PRE-SEND LIVE"
	if v.NSess > 1 {
		title += fmt.Sprintf(" · session %d", S.Idx+1)
	}
	right := ""
	if it != nil {
		right = t.StateDot(it.State, m.ascii) + t.Lbl.Render(" "+strings.TrimPrefix(it.Short, "PS "))
	}
	// result
	var A []string
	A = append(A, m.kv("net", 11, m.money(ps.Net, true, 4)))
	A = append(A, m.kv("realized", 11, t.Money(ps.Real, true, false).Render(core.SolS(ps.Real))+t.Lbl.Render("   rent back ")+t.Money(ps.Rent, true, false).Render(core.SolS(ps.Rent))))
	fs := t.Val
	if ps.Fees != 0 {
		fs = t.Neg
	}
	A = append(A, m.kv("failed", 11, fs.Render(core.SolS(-ps.Fees))+t.Lbl.Render("   "+core.IC(ps.FeeN)+" tries x "+core.IC(v.PSFailEach))))
	if ps.AllStopped && ps.FeesEng != 0 {
		d := ps.FeesEng - ps.FeesCnt
		ok := d < v.PSFailEach && -d < v.PSFailEach
		mark := t.Good.Render(m.g("✓ match", "ok match"))
		if !ok {
			mark = t.Warn.Render("differs " + core.FS(float64(d)/core.LAM, 6))
		}
		fc := m.kv("fee check", 11, t.Lbl.Render("counted "+core.F(float64(ps.FeesCnt)/core.LAM, 6)+"  engine "+core.F(float64(ps.FeesEng)/core.LAM, 6)+"  ")+mark)
		if ok && ansi.StringWidth(fc) > m.colW(w) {
			fc = m.kv("fee check", 11, t.Lbl.Render(core.F(float64(ps.FeesCnt)/core.LAM, 6)+" = engine ")+t.Good.Render(m.g("✓", "ok")))
		}
		A = append(A, fc)
	} else if ps.FeesEng != 0 {
		A = append(A, m.kv("engine", 11, t.Lbl.Render(core.F(float64(ps.FeesEng)/core.LAM, 6)+" at its last status line (60 s)")))
	}
	nl := ps.NReal - ps.Wins
	wl := t.Val.Render(fmt.Sprintf("%d W / %d L", ps.Wins, nl))
	if ps.NReal > 0 {
		wl += t.Lbl.Render(fmt.Sprintf("  (%.0f%%)", float64(ps.Wins)/float64(ps.NReal)*100))
	}
	if ps.Fills > 0 {
		avg := int64(float64(ps.Real) / float64(ps.Fills))
		wl += t.Lbl.Render("   avg/fill ") + t.Money(avg, true, false).Render(core.SolS(avg))
	}
	A = append(A, m.kv("wins", 11, wl))
	if ps.Best != nil {
		for _, bw := range []struct {
			l  string
			tr *core.Trade
		}{{"best", ps.Best}, {"worst", ps.Worst}} {
			x := bw.tr
			why := core.ExitShort(x.PExit, x.PExit)
			if why == "" {
				why = "?"
			}
			A = append(A, m.kv(bw.l, 11, m.mintLink(x.Mint, core.Short(x.Mint, 6), t.Val)+" "+t.Money(x.Pnl, true, false).Render(core.SolS(x.Pnl))+t.Lbl.Render("  "+why+" "+core.KindOf(x.Client)+"  "+core.T12(float64(x.T), false))))
		}
	}
	// exits
	var E []string
	if len(ps.Exits.Keys) == 0 {
		E = append(E, t.Lbl.Render("no closed fills yet"))
	} else {
		var rows [][]string
		for _, why := range ps.Exits.Sorted() {
			e := ps.Exits.M[why]
			per := ""
			if e.N > 0 {
				per = core.SolS(int64(float64(e.Pnl) / float64(e.N)))
			}
			rows = append(rows, []string{why, fmt.Sprint(e.N), fmt.Sprint(e.Wins), core.SolS(e.Pnl), per})
		}
		keys := ps.Exits.Sorted()
		E = append(E, strings.Split(m.kvTable([]string{"exit", "n", "W", "P&L SOL", "per fill"}, rows, map[int]bool{1: true, 2: true, 3: true, 4: true},
			func(r, c int) lipgloss.Style {
				if c >= 3 {
					e := ps.Exits.M[keys[r]]
					return t.Money(e.Pnl, true, false)
				}
				if c == 0 {
					return t.Lbl
				}
				return t.Val
			}), "\n")...)
	}
	if ps.OpenPos > 0 {
		E = append(E, m.kv("open now", 11, t.Warn.Render(fmt.Sprint(ps.OpenPos))))
	}
	// latency (the tries' landings: send -> seen of every seen try, dump -> land of the fills and of the bounced tries)
	L := m.latencyLines(cw, ps)
	// QUIET
	q := v.Quiet
	var Q []string
	if !q.Present {
		qi := v.ItemByKey("quiet")
		txt := "off"
		if qi != nil {
			txt = qi.Full
		}
		Q = append(Q, m.kv("QUIET", 11, t.StateDot("off", m.ascii)+t.Lbl.Render(" "+txt)))
	} else {
		si, ki := v.ItemByKey("qstop"), v.ItemByKey("qskip")
		stop := "off"
		if q.HasStop && q.Stop != "" {
			stop = q.Stop
		}
		sst := "off"
		if si != nil {
			sst = si.State
		}
		Q = append(Q, m.kv("stop rule", 11, t.StateDot(sst, m.ascii)+t.Val.Render(" "+stop)+t.Lbl.Render(fmt.Sprintf("   stops %d", ps.QStops))))
		kt := ""
		kst := "off"
		if ki != nil {
			kt, kst = to12(ki.Full), ki.State
		}
		wl := core.WrapText(kt, max(10, cw-18), 0)
		Q = append(Q, m.kv("skip rule", 11, t.StateDot(kst, m.ascii)+t.Val.Render(" "+wl[0])))
		for _, l := range wl[1:] {
			Q = append(Q, m.kv("", 11, t.Val.Render("  "+l)))
		}
		if q.State == "warm-up" && q.HasOnAt {
			left := float64(q.OnAt)/1e9 - m.nowSec()
			if left > 0 {
				Q = append(Q, m.kv("", 11, t.Warn.Render("on in "+core.Dur(left, true))+t.Lbl.Render(" at "+core.T12(float64(q.OnAt), false))))
			}
		}
		Q = append(Q, m.kv("", 11, t.Lbl.Render(fmt.Sprintf("skips %d   would-skip in the warm-up %d", ps.QSkips, ps.QWould))))
	}
	// paper vs live
	var P []string
	if ps.Paper {
		P = append(P, m.kv("paper (c)", 11, t.Val.Render(fmt.Sprintf("%4d fills", ps.PaperFills))+t.Lbl.Render("  gross "+core.FS(ps.PaperGross, 3)+"  net ")+
			t.Money(int64(ps.PaperNet*core.LAM), true, false).Render(core.FS(ps.PaperNet, 3))))
	} else {
		P = append(P, m.kv("paper (c)", 11, t.Lbl.Render("no shadow numbers yet")))
	}
	P = append(P, m.kv("live", 11, t.Val.Render(fmt.Sprintf("%4d fills", ps.Fills))+t.Lbl.Render("  net ")+t.Money(ps.Net, true, false).Render(core.Sol(ps.Net, true, 3, true))))
	// windows
	var Wn []string
	for _, x := range []struct {
		l string
		c *core.OCounter
	}{{"skipped", ps.Skips}, {"disarmed", ps.Disarms}, {"results", ps.Res}} {
		var parts []string
		for _, kv := range x.c.MostCommon() {
			parts = append(parts, kv.K+" "+core.IC(kv.N))
		}
		txt := strings.Join(parts, " "+core.G.Sep+" ")
		if txt == "" {
			txt = core.G.Dash
		}
		for i, l := range core.WrapText(txt, max(10, cw-17), 0) {
			lab := ""
			if i == 0 {
				lab = x.l
			}
			Wn = append(Wn, m.kv(lab, 11, t.Val.Render(l)))
		}
	}
	// sessions
	var Ss []string
	if v.NSess > 1 && v.Scope < 0 {
		var rows [][]string
		var nets []int64
		for _, X := range v.Sessions {
			a := core.CardOf([]*core.Sess{X}, nil)
			stop := ""
			for _, s := range X.PSStop {
				if s.Why != "run_end" {
					stop = s.Why
					break
				}
			}
			if stop == "" && len(X.PSStop) > 0 {
				stop = X.PSStop[len(X.PSStop)-1].Why
			}
			_ = a
			nets = append(nets, X.PSNet())
			rows = append(rows, []string{fmt.Sprint(X.Idx + 1), core.T12(float64(X.T0), false), fmt.Sprint(X.PSFills), fmt.Sprint(X.PSWins),
				core.SolS(X.PSRealized), core.SolS(X.PSRent), core.SolS(-X.PSFees()), core.SolS(X.PSNet()), stop})
		}
		Ss = strings.Split(m.kvTable([]string{"#", "start", "fills", "wins", "realized", "rent", "fees", "net", "stop"}, rows,
			map[int]bool{2: true, 3: true, 4: true, 5: true, 6: true, 7: true}, func(r, c int) lipgloss.Style {
				if c == 7 {
					return t.Money(nets[r], true, false)
				}
				if c == 8 || c == 1 {
					return t.Lbl
				}
				return t.Val
			}), "\n")
	}
	latR := t.Lbl.Render("ms")
	left := []string{m.section(title, right, C, cw), m.section("RESULT", "", A, cw), m.section("EXITS", "", E, cw), m.section("WINDOWS", "", Wn, cw)}
	rightCol := []string{m.section("LATENCY", latR, m.latencyLines(m.lastW(w, cw), ps), m.lastW(w, cw)), m.section("QUIET", "", Q, m.lastW(w, cw)),
		m.section("PAPER vs LIVE", "", P, m.lastW(w, cw))}
	if len(Ss) > 0 {
		rightCol = append(rightCol, m.section("SESSIONS", "", Ss, m.lastW(w, cw)))
	}
	if w < 120 {
		left = []string{m.section(title, right, C, w), m.section("RESULT", "", A, w), m.section("LATENCY", latR, L, w), m.section("QUIET", "", Q, w),
			m.section("EXITS", "", E, w), m.section("PAPER vs LIVE", "", P, w), m.section("WINDOWS", "", Wn, w)}
		if len(Ss) > 0 {
			left = append(left, m.section("SESSIONS", "", Ss, w))
		}
		return strings.Join(left, "\n")
	}
	return hcat(1, strings.Join(left, "\n"), strings.Join(rightCol, "\n"))
}

func (m *Model) lastW(w, cw int) int {
	if w >= 120 {
		return w - cw - 1
	}
	return w
}

// to12 rewrites "16:26 PKT" times in a text to 12-hour form.
func to12(text string) string {
	if !strings.Contains(text, "PKT") {
		return text
	}
	var b strings.Builder
	rs := []rune(text)
	for i := 0; i < len(rs); i++ {
		// match H:MM PKT or HH:MM PKT at a word start
		j := i
		for j < len(rs) && j-i < 2 && rs[j] >= '0' && rs[j] <= '9' {
			j++
		}
		if j > i && j+7 <= len(rs) && rs[j] == ':' && isD(rs[j+1]) && isD(rs[j+2]) && string(rs[j+3:j+7]) == " PKT" && (i == 0 || !isD(rs[i-1])) {
			hh := 0
			for _, c := range rs[i:j] {
				hh = hh*10 + int(c-'0')
			}
			mm := string(rs[j+1 : j+3])
			if hh < 24 {
				h12 := hh % 12
				if h12 == 0 {
					h12 = 12
				}
				ap := "AM"
				if hh >= 12 {
					ap = "PM"
				}
				b.WriteString(fmt.Sprintf("%d:%s %s PKT", h12, mm, ap))
				i = j + 6
				continue
			}
		}
		b.WriteRune(rs[i])
	}
	return b.String()
}

func isD(r rune) bool { return r >= '0' && r <= '9' }

// ------------------------------------------------------------------------------------------------- 3 regular

func (m *Model) scrRegular(w, bh int) string {
	t := m.th
	v := m.view
	g := v.Reg
	cw := m.colW(w)
	sep := t.Dim.Render(" " + m.g("·", "|") + " ")
	ri, mi := v.ItemByKey("reg"), v.ItemByKey("m2")
	var A []string
	if ri != nil {
		A = append(A, m.kv("setup", 9, t.Val.Render(ri.Short)))
	}
	A = append(A, m.kv("P&L", 9, m.money(g.Total, true, 4)))
	A = append(A, m.kv("", 9, t.Lbl.Render("fills ")+t.Money(g.FillPnl, true, false).Render(core.SolS(g.FillPnl))+t.Lbl.Render("   failed buys ")+t.Money(g.FailPnl, true, false).Render(core.SolS(g.FailPnl))))
	b := t.Val.Render(fmt.Sprintf("%d fired", g.Fires)) + t.Lbl.Render(" "+m.g("→", "->")+" ") + t.B.Render(fmt.Sprintf("%d filled", g.Fills))
	if g.Fires > 0 {
		b += t.Lbl.Render(fmt.Sprintf(" (%.0f%%)", float64(g.Fills)/float64(g.Fires)*100))
	}
	b += sep + t.Val.Render(fmt.Sprintf("%d failed", g.Guard+g.Lighthouse+g.Failed))
	if g.Open > 0 {
		b += sep + t.Warn.Render(fmt.Sprintf("%d open", g.Open))
	}
	A = append(A, m.kv("buys", 9, b))
	wl := t.Val.Render(fmt.Sprintf("%d W / %d L", g.Wins, g.Fills-g.Wins))
	if g.Fills > 0 {
		avg := int64(float64(g.FillPnl) / float64(g.Fills))
		wl += t.Lbl.Render("   avg/fill ") + t.Money(avg, true, false).Render(core.SolS(avg))
	}
	A = append(A, m.kv("wins", 9, wl))
	if g.Est > 0 {
		A = append(A, m.kv("", 9, t.Warn.Render(fmt.Sprintf("%d fill(s) on the feed estimate (~) until the engine's REALIZED line", g.Est))))
	}
	if g.Best != nil {
		A = append(A, m.kv("best", 9, t.Val.Render(core.Short(g.Best.Mint, 6)+" ")+t.Money(g.Best.Pnl, true, false).Render(core.SolS(g.Best.Pnl))+
			t.Lbl.Render("   worst ")+t.Val.Render(core.Short(g.Worst.Mint, 6)+" ")+t.Money(g.Worst.Pnl, true, false).Render(core.SolS(g.Worst.Pnl))))
	}
	right := ""
	if mi != nil {
		right = t.StateDot(mi.State, m.ascii) + t.Lbl.Render(" "+mi.Short)
	}
	fee := m.ctx.Src.Model.FailBuyFee
	var F []string
	var frows [][]string
	var fn []int64
	for _, x := range []struct {
		l string
		n int64
	}{{"price 6042", g.Guard}, {"lighthouse 6001", g.Lighthouse}, {"other", g.Failed}} {
		frows = append(frows, []string{x.l, fmt.Sprint(x.n), core.SolS(-x.n * fee)})
		fn = append(fn, x.n)
	}
	F = append(F, strings.Split(m.kvTable(nil, frows, map[int]bool{1: true, 2: true}, func(r, c int) lipgloss.Style {
		if c == 0 {
			return t.Lbl
		}
		if fn[r] == 0 {
			return t.Dim
		}
		if c == 2 {
			return t.Neg
		}
		return t.Val
	}), "\n")...)
	F = append(F, t.Dim.Render(fmt.Sprintf("each costs its tx fee %s SOL; tips revert", core.F(float64(fee)/core.LAM, 6))))
	var E []string
	if len(g.Exits.Keys) == 0 {
		E = append(E, t.Lbl.Render("no sold fills yet"))
	} else {
		var rows [][]string
		keys := g.Exits.Sorted()
		for _, why := range keys {
			e := g.Exits.M[why]
			rows = append(rows, []string{why, fmt.Sprint(e.N), fmt.Sprint(e.Wins), core.SolS(e.Pnl)})
		}
		E = append(E, strings.Split(m.kvTable([]string{"exit", "n", "W", "P&L SOL"}, rows, map[int]bool{1: true, 2: true, 3: true}, func(r, c int) lipgloss.Style {
			if c == 3 {
				return t.Money(g.Exits.M[keys[r]].Pnl, true, false)
			}
			if c == 0 {
				return t.Lbl
			}
			return t.Val
		}), "\n")...)
	}
	var B []string
	if len(g.KindKeys) == 0 {
		B = append(B, t.Lbl.Render("no buys yet"))
	} else {
		keys := append([]string(nil), g.KindKeys...)
		sort.SliceStable(keys, func(i, j int) bool { return g.Kinds[keys[i]].Buys > g.Kinds[keys[j]].Buys })
		var rows [][]string
		for _, k := range keys {
			x := g.Kinds[k]
			rows = append(rows, []string{core.RuneSlice(k, 12), fmt.Sprint(x.Buys), fmt.Sprint(x.Fills), fmt.Sprint(x.Wins), core.SolS(x.Pnl)})
		}
		B = append(B, strings.Split(m.kvTable([]string{"client", "buys", "fills", "W", "P&L SOL"}, rows, map[int]bool{1: true, 2: true, 3: true, 4: true}, func(r, c int) lipgloss.Style {
			if c == 4 {
				return t.Money(g.Kinds[keys[r]].Pnl, true, false)
			}
			return t.Val
		}), "\n")...)
	}
	var L []string
	lm, ok := core.Med(g.LandMs)
	lt := core.G.Dash
	if ok {
		lt = "median " + core.F(lm, 0) + " ms after the dump"
	}
	L = append(L, m.kv("fills", 9, t.Val.Render(lt)))
	L = append(L, m.kv("", 9, t.Lbl.Render(fmt.Sprintf("%d of %d in the dump's own block", g.Same, g.Fills))))
	if fm, ok := core.Med(g.FailMs); ok {
		L = append(L, m.kv("fails", 9, t.Lbl.Render("median "+core.F(fm, 0)+" ms after the dump (seen)")))
	}
	var O []string
	if len(g.OpenList) == 0 {
		O = append(O, t.Lbl.Render("no open position"))
	} else {
		for _, tr := range g.OpenList[max(0, len(g.OpenList)-5):] {
			st := "in flight"
			if tr.Res == "filled" {
				st = "holding"
			}
			O = append(O, t.Lbl.Render(core.T12(float64(tr.T), true)+" ")+t.Val.Render(core.Short(tr.Mint, 8)+" "+core.F(float64(tr.Spend.Int())/core.LAM, 2)+" SOL")+t.Warn.Render("  "+st)+t.Lbl.Render("  "+core.KindOf(tr.Client)))
		}
	}
	var Fn []string
	Fn = append(Fn, m.kv("dumps", 9, t.Val.Render(core.IC(g.Dumps))+t.Lbl.Render("   picks "+core.IC(g.Picks))))
	var parts []string
	for _, kv := range g.Skipped.MostCommon() {
		parts = append(parts, kv.K+" "+core.IC(kv.N))
	}
	txt := strings.Join(parts, " "+core.G.Sep+" ")
	if txt == "" {
		txt = core.G.Dash
	}
	for i, l := range core.WrapText(txt, max(10, m.lastW(w, cw)-15), 0) {
		lab := ""
		if i == 0 {
			lab = "skipped"
		}
		Fn = append(Fn, m.kv(lab, 9, t.Val.Render(l)))
	}
	if w < 120 {
		return strings.Join([]string{m.section("REGULAR BUYS", right, A, w), m.section("FAILED BUYS", "", F, w), m.section("EXITS", "", E, w),
			m.section("BY LEADER CLIENT", "", B, w), m.section("LANDING", "", L, w), m.section("OPEN NOW", "", O, w), m.section("FUNNEL", "", Fn, w)}, "\n")
	}
	rw := m.lastW(w, cw)
	l := strings.Join([]string{m.section("REGULAR BUYS", right, A, cw), m.section("FAILED BUYS", "", F, cw), m.section("EXITS", "", E, cw)}, "\n")
	r := strings.Join([]string{m.section("BY LEADER CLIENT", "", B, rw), m.section("LANDING", "", L, rw), m.section("OPEN NOW", "", O, rw), m.section("FUNNEL", "", Fn, rw)}, "\n")
	return hcat(1, l, r)
}

// ------------------------------------------------------------------------------------------------- 5 health

func (m *Model) scrHealth(w, bh int) string {
	t := m.th
	v := m.view
	M := m.ctx.Src.Model
	src := m.ctx.Src
	es := m.ctx.Engine.Snapshot()
	sy := m.ctx.Sys
	sep := t.Dim.Render(" " + m.g("·", "|") + " ")
	var E []string
	if es.PID != 0 {
		up := v.SElapsed
		if es.Start != 0 {
			up = m.nowSec() - es.Start
		}
		cpu := core.G.Dash
		if es.HasCPU {
			cpu = core.F(es.CPU, 0) + "%"
		}
		l := t.Val.Render(fmt.Sprintf("pid %d", es.PID)) + sep + t.Lbl.Render(es.Build) + sep + t.Lbl.Render("cpu ") + t.Val.Render(cpu) + sep +
			t.Lbl.Render("rss ") + t.Val.Render(core.FC(float64(es.RSS)/1e6, 0)+" MB") + sep + t.Lbl.Render("up ") + t.Val.Render(core.HMS(up, true, false))
		if es.Threads > 0 {
			l += t.Lbl.Render(fmt.Sprintf("  %d thr", es.Threads))
		}
		E = append(E, m.kv("process", 10, l))
	} else {
		st := t.Lbl
		if v.Status == "ENGINE GONE" {
			st = t.Bad
		}
		why := "no engine process with this --dip-log"
		if es.Seen {
			why += " (it was running)"
		}
		E = append(E, m.kv("process", 10, st.Render(why)))
	}
	stall := v.Running && v.HasWrite && v.WriteAge > 30
	ageS := func(a float64, ok bool) string {
		st := t.Val
		if stall {
			st = t.Bad
		}
		if !ok {
			return st.Render("never")
		}
		return st.Render(core.AgeS(a, true) + " ago")
	}
	E = append(E, m.kv("log", 10, t.Val.Render(core.FC(float64(src.TL.Size)/1e6, 1)+" MB")+t.Lbl.Render("  written ")+ageS(v.LogAge, v.HasLogA)+t.Lbl.Render("  "+core.IC(M.LLines)+" lines")))
	bad := t.Lbl
	if M.Bad > 0 {
		bad = t.Warn
	}
	rec := m.kv("records", 10, t.Val.Render(core.FC(float64(src.TJ.Size)/1e6, 1)+" MB")+t.Lbl.Render("  written ")+ageS(v.JSONLAge, v.HasJA)+t.Lbl.Render("  "+core.IC(M.JLines)+" lines"))
	if M.Bad > 0 || w >= 70 {
		rec += bad.Render(fmt.Sprintf("  bad %d", M.Bad))
	}
	E = append(E, rec)
	if M.HasRuntime {
		p99s := t.Val
		if M.Runtime[1] > 10 {
			p99s = t.Warn
		}
		rt := m.kv("runtime", 10, t.Lbl.Render("lag p50 ")+t.Val.Render(core.F(M.Runtime[0], 2))+t.Lbl.Render("  p99 ")+p99s.Render(core.F(M.Runtime[1], 2))+
			t.Lbl.Render("  max ")+t.Val.Render(core.F(M.Runtime[2], 1)+" ms"))
		if worst := t.Lbl.Render("  worst p99 " + core.F(M.RuntimeWorst, 1)); ansi.StringWidth(rt+worst) <= m.colW(w) {
			rt += worst
		}
		E = append(E, rt)
	}
	// errors
	var R []string
	pe1 := M.PollErr[M.LogMin]
	var pe10 int64
	for k, x := range M.PollErr {
		if k >= M.LogMin-9 {
			pe10 += x
		}
	}
	p1s := t.Val
	if pe1 >= 10 {
		p1s = t.Warn
	}
	R = append(R, m.kv("poll errs", 11, p1s.Render(fmt.Sprint(pe1))+t.Lbl.Render(" this min")+sep+t.Val.Render(fmt.Sprint(pe10))+t.Lbl.Render(" in 10 min")+sep+t.Lbl.Render(fmt.Sprintf("%d total", M.PollErrTotal))))
	paths := make([]string, 0, len(M.PathErr))
	for p := range M.PathErr {
		paths = append(paths, p)
	}
	sort.SliceStable(paths, func(i, j int) bool { return M.PathTotal[paths[i]] > M.PathTotal[paths[j]] })
	if len(paths) == 0 {
		R = append(R, m.kv("send paths", 11, t.Lbl.Render("no keep-alive / connection errors")))
	} else {
		var rows [][]string
		var hot []bool
		for _, p := range paths {
			var n10 int64
			for k, x := range M.PathErr[p] {
				if k >= M.LogMin-9 {
					n10 += x
				}
			}
			kind := M.PathKind[p]
			if kind == "" {
				kind = "error"
			}
			rows = append(rows, []string{core.RuneSlice(p, 14), kind, fmt.Sprint(n10), fmt.Sprint(M.PathTotal[p])})
			hot = append(hot, n10 >= 3)
		}
		R = append(R, strings.Split(m.kvTable([]string{"send path", "kind", "10 min", "total"}, rows, map[int]bool{2: true, 3: true}, func(r, c int) lipgloss.Style {
			if hot[r] && (c == 1 || c == 2) {
				return t.Warn
			}
			if c == 3 {
				return t.Lbl
			}
			return t.Val
		}), "\n")...)
	}
	if len(M.Panics) > 0 {
		R = append(R, m.kv("panics", 11, t.Bad.Render(core.RuneSlice(M.Panics[len(M.Panics)-1], w-20))))
	}
	if len(M.Refused) > 0 {
		R = append(R, m.kv("refused", 11, t.Warn.Render(core.RuneSlice(M.Refused[len(M.Refused)-1], w-20))))
	}
	// system
	var Y []string
	if sy != nil {
		disk := core.G.Dash
		ds := t.Val
		if sy.HasDisk {
			disk = core.F(sy.Disk, 0) + "%"
			if sy.Disk > 85 {
				ds = t.Warn
			}
		}
		load := core.G.Dash
		if sy.HasLoad {
			load = core.F(sy.Load[0], 2) + " " + core.F(sy.Load[1], 2) + " " + core.F(sy.Load[2], 2)
		}
		Y = append(Y, m.kv("disk", 10, ds.Render(disk)+t.Lbl.Render("  load ")+t.Val.Render(load)+t.Lbl.Render(fmt.Sprintf(" (%d cpu)", sy.NCPU))))
		if sy.MemTotal > 0 {
			Y = append(Y, m.kv("memory", 10, t.Val.Render(core.F(float64(sy.MemUsed)/1e9, 2)+" / "+core.F(float64(sy.MemTotal)/1e9, 2)+" GB")+
				t.Lbl.Render(fmt.Sprintf("  (%.0f%% used)", float64(sy.MemUsed)/float64(sy.MemTotal)*100))))
		}
		own := "cpu " + core.G.Dash
		if sy.HasOwn {
			own = "cpu " + core.F(sy.OwnCPU, 1) + "%"
		}
		pid := os.Getpid()
		if m.opt.Golden {
			pid = 4242
		}
		Y = append(Y, m.kv("dipmon", 10, t.Val.Render(own)+t.Lbl.Render("  rss ")+t.Val.Render(core.F(float64(sy.OwnRSS)/1e6, 0)+" MB")+t.Lbl.Render(fmt.Sprintf("  pid %d", pid))))
	}
	if pr := m.ctx.Price; pr != nil {
		u, src, age, ageOK, perr, fetching := pr.Get()
		x := t.Val.Render("n/a")
		if u != 0 {
			x = t.Val.Render("$" + core.FC(u, 2))
		}
		x += t.Lbl.Render("  " + src)
		if ageOK {
			x += t.Lbl.Render(", " + core.AgeS(age, true) + " ago")
		}
		if fetching || m.priceSpin {
			x += " " + m.spin.View()
		}
		if perr != "" && u == 0 {
			x += t.Warn.Render("  " + perr)
		}
		Y = append(Y, m.kv("SOL/USD", 10, x))
	}
	// RPC latency
	var P []string
	if len(M.RPC) == 0 {
		P = append(P, t.Lbl.Render("no RPC-LAT lines yet"))
	} else {
		keys := append([][2]string(nil), M.RPCOrder...)
		sort.SliceStable(keys, func(i, j int) bool {
			a, b := M.RPC[keys[i]], M.RPC[keys[j]]
			if a.Min != b.Min {
				return a.Min > b.Min
			}
			if keys[i][0] != keys[j][0] {
				return keys[i][0] < keys[j][0]
			}
			return keys[i][1] < keys[j][1]
		})
		var rows [][]string
		var warn [][2]bool
		for _, k := range keys {
			x := M.RPC[k]
			if M.LogMin-x.Min > 30 {
				continue
			}
			if w < 70 { // phones: name, method, p50, p99
				rows = append(rows, []string{core.RuneSlice(k[0], 13), core.RuneSlice(k[1], 18), core.F(x.P50, 1), core.F(x.P99, 1)})
			} else {
				rows = append(rows, []string{core.RuneSlice(k[0], 14), core.RuneSlice(k[1], 22), core.F(x.P50, 1), core.F(x.P99, 1), fmt.Sprint(x.N), fmt.Sprint(x.TO)})
			}
			warn = append(warn, [2]bool{x.P99 > 300, x.TO > 0})
		}
		hdr := []string{"name", "method", "p50", "p99", "n", "to"}
		if w < 70 {
			hdr = hdr[:4]
		}
		P = append(P, strings.Split(m.kvTable(hdr, rows, map[int]bool{2: true, 3: true, 4: true, 5: true}, func(r, c int) lipgloss.Style {
			if c == 3 && warn[r][0] {
				return t.Warn
			}
			if c == 5 && warn[r][1] {
				return t.Warn
			}
			if c >= 4 {
				return t.Lbl
			}
			return t.Val
		}), "\n")...)
	}
	cw := m.colW(w)
	if w < 120 {
		return strings.Join([]string{m.section("ENGINE", "", E, w), m.section("ERRORS", "", R, w), m.section("SYSTEM", "", Y, w),
			m.section("RPC LATENCY", t.Lbl.Render("latest minute, ms"), P, w)}, "\n")
	}
	rw := m.lastW(w, cw)
	l := strings.Join([]string{m.section("ENGINE", "", E, cw), m.section("SYSTEM", "", Y, cw)}, "\n")
	r := strings.Join([]string{m.section("ERRORS", "", R, rw), m.section("RPC LATENCY", t.Lbl.Render("latest minute, ms"), P, rw)}, "\n")
	return hcat(1, l, r)
}

// ------------------------------------------------------------------------------------------------- 7 config

// explain: a one-line plain-English explanation of a config item.
func (m *Model) explain(it core.CfgItem) string {
	v := m.view
	pc := v.PSCfg
	n := func(k string) (core.Num, bool) {
		x, ok := pc[k].(core.Num)
		return x, ok && x.Ok()
	}
	switch it.Key {
	case "ps":
		k := "N"
		if x, ok := n("k"); ok {
			k = x.Repr()
		}
		drop := ""
		if x, ok := n("drop"); ok && x.Truthy() {
			drop = " " + m.g("≥", ">=") + " " + core.F(x.Float()*100, 0) + "%"
		}
		ex := ""
		if x, ok := n("exit_slots"); ok {
			ex = "; it is sold at TP / SL or after " + x.Repr() + " slots"
		}
		return k + " tries/slot = " + k + " conditional buys sent every slot (~0.2 s) while a window is open; each fills only on a sudden" + drop + " drop" + ex
	case "qstop":
		if v.Quiet.HasStop && strings.Contains(v.Quiet.Stop, ":") {
			p := strings.SplitN(v.Quiet.Stop, ":", 2)
			return "a window stops sending tries when fewer than " + p[1] + " other trades happen within " + p[0] + " slots of the trigger"
		}
		return "a window keeps sending tries until it closes"
	case "qskip":
		return "skips a trigger when all 4 quiet signals agree the token is quiet; off during the warm-up after a start"
	case "quiet":
		return "the QUIET filter (stop + skip rules) is not active in this run"
	case "paper":
		return "a paper copy of pre-send at +0 / +5 / +10 ms landing, to compare with live; it never trades"
	case "m2":
		return "the regular bot buys only when the M2 model's score reaches the threshold (gate); shadow = scored, not enforced"
	case "dev":
		return "buys new tokens of the listed developer wallets at this size"
	case "reg":
		return "after a big dump the regular bot buys this size and sells at TP / SL or after the hold slots"
	case "guard":
		return "the buy fails on chain (pump error 6042, costs only the tx fee) when the price is above this multiple of the post-dump price"
	case "routes":
		return "which send paths each leader client gets (a preset of the run script)"
	case "sellfan":
		return "each sell goes out through staked RPC and a second path, for speed"
	case "nonce":
		return "one buy goes out as several durable-nonce copies; only one can land, so one tip is paid"
	case "near":
		return "the regular bot fires only when one of these nearest leaders makes the next blocks"
	case "skipcl":
		return "no regular buys while the leader runs these clients"
	case "kill":
		return "the engine stops itself when the wallet falls below this (START BALANCE − loss cap)"
	case "planned":
		return "the run stops by itself after this long"
	case "build":
		return "the engine binary running this run"
	}
	return ""
}

func (m *Model) scrConfig(w, bh int) string {
	t := m.th
	v := m.view
	S := v.S
	lw := 19
	if w < 70 {
		lw = 11
	}
	inner := w // the text width: a panel's inside, or the full width under a rule
	if w >= 70 {
		inner = w - 4
	}
	tw := max(10, inner-lw-3)
	var out []string
	for bi, title := range cfgBlockTitles { // the items grouped: pre-send, regular, routes & sending, limits, QUIET & paper
		n0 := len(out)
		for _, it := range blockItems(v.CfgItems, bi) {
			if len(out) == n0 {
				if n0 > 0 {
					out = append(out, "")
				}
				out = append(out, m.subRule(title, inner))
			}
			lab := it.Label
			if w < 70 {
				lab = it.SLabel
			}
			dot := t.StateDot(it.State, m.ascii)
			if it.State == "na" {
				dot = " "
			}
			text := to12(it.Full)
			if it.Key == "routes" && w < 90 {
				text = strings.SplitN(text, " ", 2)[0]
			}
			wl := core.WrapText(text, tw, 0)
			out = append(out, dot+" "+t.Lbl.Render(padRight(core.RuneSlice(lab, lw), lw))+" "+t.Val.Render(wl[0]))
			for _, l := range wl[1:] {
				out = append(out, strings.Repeat(" ", lw+3)+t.Val.Render(l))
			}
			if ex := m.explain(it); ex != "" {
				for _, l := range core.WrapText(ex, tw, 0) {
					out = append(out, strings.Repeat(" ", lw+3)+t.Dim.Render(l))
				}
			}
		}
	}
	var W []string
	if v.HasStartBal {
		W = append(W, m.kv("start", 18, t.Val.Render(core.F(float64(v.StartBal)/core.LAM, 6)+" SOL")+t.Lbl.Render("  START BALANCE of this session  ")+t.Dim.Render(core.UsdAmt(v.StartBal, true, v.Price, false))))
		W = append(W, m.kv("now (est.)", 18, t.Val.Render(core.F(float64(v.EstNow)/core.LAM, 6)+" SOL")+t.Lbl.Render("  start + this session's P&L  ")+t.Dim.Render(core.UsdAmt(v.EstNow, true, v.Price, false))))
	}
	if v.HasBudget {
		W = append(W, m.kv("dip budget left", 18, t.Val.Render(core.F(float64(v.BudgetLeft)/core.LAM, 4)+" of "+core.F(float64(v.BudgetMax)/core.LAM, 3)+" SOL")))
	}
	if S.RS.HasWallet && S.RS.Wallet != "" {
		wal := S.RS.Wallet
		W = append(W, m.kv("address", 18, t.Val.Render(core.RuneSlice(wal, 8)+core.G.Ell+string([]rune(wal)[max(0, len([]rune(wal))-4):]))+t.Lbl.Render("  (public)")))
	}
	right := ""
	if v.NSess > 1 {
		right = t.Lbl.Render(fmt.Sprintf("session %d/%d", S.Idx+1, v.NSess))
	}
	legend := t.StateDot("on", m.ascii) + t.Lbl.Render(" on   ") + t.StateDot("part", m.ascii) + t.Lbl.Render(" warming up / partial / stopped   ") + t.StateDot("off", m.ascii) + t.Lbl.Render(" off")
	parts := []string{m.section("CONFIG", right, out, w)}
	if len(W) > 0 {
		parts = append(parts, m.section("WALLET", "", W, w))
	}
	parts = append(parts, " "+legend)
	return strings.Join(parts, "\n")
}

// ------------------------------------------------------------------------------------------------- detail

func (m *Model) link(url string) string { return m.linkText(url, url, m.th.Acc) }

// linkText renders text in st as an OSC 8 hyperlink to url (plain text when links are off: --no-links, --ascii,
// --no-color). Terminals without OSC 8 show the text alone.
func (m *Model) linkText(url, text string, st lipgloss.Style) string {
	if m.linksOn() && url != "" {
		st = st.Hyperlink(url)
	}
	return st.Render(text)
}

// mintLink: (part of) a mint, linked to its GMGN page.
func (m *Model) mintLink(mint, text string, st lipgloss.Style) string {
	if mint == "" || mint == "?" {
		return st.Render(text)
	}
	return m.linkText(gmgnURL(mint), text, st)
}

// acctLink: an account (a leader's identity), linked to Solscan when it looks like a public key.
func (m *Model) acctLink(acct, text string, st lipgloss.Style) string {
	if n := len(acct); n < 32 || n > 44 || strings.ContainsAny(acct, "0OIl+/=_- ") {
		return st.Render(text)
	}
	return m.linkText("https://solscan.io/account/"+acct, text, st)
}

func (m *Model) scrDetail(w, bh int, tr *core.Trade) string {
	t := m.th
	v := m.view
	lw := 11
	var out []string
	// every URL / address is an OSC 8 hyperlink (each wrapped piece links the whole URL)
	full := func(label, u string) {
		for i, l := range core.WrapText(u, max(10, w-lw-4), 0) {
			lab := ""
			if i == 0 {
				lab = label
			}
			out = append(out, m.kv(lab, lw, m.linkText(u, l, t.Acc)))
		}
	}
	url := func(label, kind, sig string) {
		if sig == "" {
			return
		}
		full(label, "https://solscan.io/"+kind+"/"+sig)
	}
	ps := tr.Kind == "PS"
	for i, l := range core.WrapText(tr.Mint, max(10, w-lw-4), 0) {
		lab := ""
		if i == 0 {
			lab = "mint"
		}
		out = append(out, m.kv(lab, lw, m.mintLink(tr.Mint, l, t.B)))
	}
	if tr.Mint != "" {
		full("gmgn", gmgnURL(tr.Mint))
	}
	url("solscan", "token", tr.Mint)
	spend := tr.Spend.Int()
	sz := t.Val.Render(core.F(float64(spend)/core.LAM, 4) + " SOL")
	if m.usdFirst && v.Price != 0 {
		sz = t.Val.Render(core.UsdAmt(spend, true, v.Price, false)) + t.Lbl.Render("  ("+core.F(float64(spend)/core.LAM, 4)+" SOL)")
	}
	if ps && tr.SolIn.Truthy() {
		sz += t.Lbl.Render("  (into the curve " + core.F(tr.SolIn.Float()/core.LAM, 4) + ")")
	}
	out = append(out, m.kv("size", lw, sz))
	if tr.HasPnl {
		p := m.money(tr.Pnl, true, 4)
		if spend != 0 {
			p += t.Money(tr.Pnl, true, false).Render("  " + core.PctS(float64(tr.Pnl)/float64(spend), true, 1, true))
		}
		if tr.Src == "est" {
			p += t.Warn.Render("  feed estimate")
		}
		out = append(out, m.kv("P&L", lw, p))
	} else {
		out = append(out, m.kv("P&L", lw, t.Lbl.Render("not realized yet")))
	}
	if ps {
		if tr.HasRent {
			out = append(out, m.kv("rent back", lw, t.Pos.Render(core.SolS(tr.Rent))+t.Lbl.Render("  account closed; not in the P&L above")))
		}
		ex := tr.PExit
		if !tr.HasPExit || ex == "" {
			ex = "open"
		}
		e := t.Val.Render(ex)
		if tr.Slots.Ok() {
			e += t.Lbl.Render("  after " + tr.Slots.Repr() + " slot(s)")
		}
		if tr.HeldS.Truthy() {
			e += t.Lbl.Render("  held " + core.F(tr.HeldS.Float(), 2) + " s")
		}
		if tr.Value.Truthy() {
			e += t.Lbl.Render("  value x" + core.F(tr.Value.Float(), 3))
		}
		out = append(out, m.kv("exit", lw, e))
		sep := t.Lbl.Render(" " + core.G.Sep + " ")
		// latency: the filling try (its presend_attempt_land record)
		out = append(out, m.kv("latency", lw, m.latLine(tr, "send→seen")))
		l := tr.Lat
		client := tr.Client
		path := tr.Path
		if l != nil && l.Client != "" {
			client = l.Client
		}
		if l != nil && l.Path != "" {
			path = l.Path
		}
		cl := t.Val.Render(core.KindOf(client))
		if core.KindOf(client) != client {
			cl += t.Lbl.Render(" (" + client + ")")
		}
		if l != nil && l.Leader != "" {
			cl += sep + t.Lbl.Render("leader ") + m.acctLink(l.Leader, l.Leader, t.Val)
		}
		out = append(out, m.kv("landed", lw, cl+sep+t.Lbl.Render("path ")+t.Val.Render(path)))
		var win []string
		if l != nil && l.N.Ok() {
			x := t.Lbl.Render("try ") + t.Val.Render(l.N.Repr())
			if S := m.sessOf(tr); S != nil && S.WinTries[tr.W.W] > 0 {
				x += t.Lbl.Render(" of ") + t.Val.Render(core.IC(S.WinTries[tr.W.W]))
			}
			win = append(win, x)
		} else if S := m.sessOf(tr); S != nil && tr.W.Ok && S.WinTries[tr.W.W] > 0 {
			win = append(win, t.Val.Render(core.IC(S.WinTries[tr.W.W]))+t.Lbl.Render(" tries"))
		}
		if l != nil && l.NBetween.Ok() {
			nb := l.NBetween.Repr()
			win = append(win, t.Val.Render(nb)+t.Lbl.Render(map[bool]string{true: " trader", false: " traders"}[nb == "1"]+" between the dump and us"))
		}
		if l != nil && l.DropPct.Ok() {
			d := t.Lbl.Render("the dump ") + t.Val.Render("-"+core.F(l.DropPct.Float(), 1)+"%")
			if l.PRel.Ok() {
				d += t.Lbl.Render(", price x" + core.F(l.PRel.Float(), 3))
			}
			win = append(win, d)
		}
		if len(win) > 0 {
			out = append(out, m.kv("window", lw, strings.Join(win, sep)))
		}
		var bits []string
		if tr.TrigPct.Ok() {
			b := "whale " + core.F(tr.TrigPct.Float(), 1) + "%"
			if tr.TrigSol.Truthy() {
				b += " (" + core.F(tr.TrigSol.Float()/core.LAM, 2) + " SOL)"
			}
			bits = append(bits, b)
		}
		if tr.After.Ok() {
			bits = append(bits, "+"+tr.After.Repr()+" slots after the trigger")
		}
		if tr.NFills > 1 {
			bits = append(bits, fmt.Sprintf("%d fills merged", tr.NFills))
		}
		if len(bits) > 0 {
			out = append(out, m.kv("trigger", lw, t.Val.Render(strings.Join(bits, " "+core.G.Sep+" ")))) // wrapped below
		}
		for i, s := range tr.BuySigs {
			lab := ""
			if i == 0 {
				lab = "buy"
			}
			url(lab, "tx", s)
		}
		for i, s := range tr.SellSigs {
			lab := ""
			if i == 0 {
				lab = "sell"
			}
			url(lab, "tx", s)
		}
	} else {
		resd := map[string]string{"filled": "filled", "guard": "failed: price guard 6042", "lighthouse": "failed: Lighthouse slot guard 6001",
			"failed": "failed on chain", "open": "in flight", "not landed": "never landed"}[tr.Res]
		if resd == "" {
			resd = tr.Res
		}
		rs := t.Val
		if tr.Res == "guard" || tr.Res == "lighthouse" || tr.Res == "failed" {
			rs = t.Warn
		}
		r := rs.Render(resd)
		if tr.Dev {
			r += t.Acc.Render("  dev list")
		}
		out = append(out, m.kv("result", lw, r))
		if tr.Res == "filled" {
			why := "holding"
			if tr.Close != nil && tr.Close.HasWhy && tr.Close.Why != "" {
				why = tr.Close.Why
			} else if tr.Exit != nil && tr.Exit.HasWhy && tr.Exit.Why != "" {
				why = tr.Exit.Why
			}
			e := t.Val.Render(why)
			if h := core.TradeHeld(tr); h != "" {
				e += t.Lbl.Render("  after " + h)
			}
			if tr.Close != nil && tr.Close.HeldS.Truthy() {
				e += t.Lbl.Render("  held " + core.F(tr.Close.HeldS.Float(), 2) + " s")
			}
			out = append(out, m.kv("exit", lw, e))
		}
		sep := t.Lbl.Render(" " + core.G.Sep + " ")
		// latency: buy_land (a failed buy: its timing record)
		out = append(out, m.kv("latency", lw, m.latLine(tr, "fire→seen")))
		cl := t.Val.Render(core.KindOf(tr.Client))
		if core.KindOf(tr.Client) != tr.Client {
			cl += t.Lbl.Render(" (" + tr.Client + ")")
		}
		if tr.Leader != "" {
			cl += sep + t.Lbl.Render("leader ") + m.acctLink(tr.Leader, core.RuneSlice(tr.Leader, 8), t.Val)
		}
		if r := strings.ReplaceAll(tr.Route, "route:", ""); r != "" {
			cl += sep + t.Lbl.Render("route ") + t.Val.Render(r)
		}
		var via string
		if tr.Land != nil && tr.Land.Via != "" {
			via = "path " + tr.Land.Via
		} else if tr.Failed != nil && tr.Failed.Via != "" {
			via = "failed copy via " + tr.Failed.Via
		} else if len(tr.Paths) > 0 {
			via = "sent via " + strings.Join(tr.Paths, ", ")
		}
		if via != "" {
			cl += sep + t.Lbl.Render(via)
		}
		out = append(out, m.kv("landed", lw, cl))
		var bits []string
		if tr.DecUs.Ok() {
			bits = append(bits, "decision "+core.F(tr.DecUs.Float(), 0)+" us")
		}
		if tm := tr.Timing; tm != nil {
			if tm.Reaction.Ok() {
				bits = append(bits, "reaction "+core.F(tm.Reaction.Float(), 2)+" ms")
			}
			if tm.ExecLag.Ok() {
				bits = append(bits, "exec lag "+core.F(tm.ExecLag.Float(), 2)+" ms")
			}
		}
		bt := strings.Join(bits, " "+core.G.Sep+" ")
		if bt == "" {
			bt = core.G.Dash
		}
		out = append(out, m.kv("timing", lw, t.Val.Render(bt))) // wrapped below, a number kept with its unit
		if tr.HasDumpSig {
			url("dump", "tx", tr.DumpSig)
		}
		bsig := tr.BuySig
		if tr.Land != nil && tr.Land.HasSig && tr.Land.Sig != "" {
			bsig = tr.Land.Sig
		} else if tr.Failed != nil && tr.Failed.HasSig && tr.Failed.Sig != "" {
			bsig = tr.Failed.Sig
		}
		url("buy", "tx", bsig)
		var sells []string
		if tr.Close != nil && len(tr.Close.SellSigs) > 0 {
			sells = tr.Close.SellSigs
		} else {
			for _, s := range tr.Sells {
				if s.HasSig && s.Sig != "" {
					sells = append(sells, s.Sig)
				}
			}
		}
		seen := map[string]bool{}
		i := 0
		for _, s := range sells {
			if seen[s] {
				continue
			}
			seen[s] = true
			lab := ""
			if i == 0 {
				lab = "sell"
			}
			url(lab, "tx", s)
			i++
		}
	}
	title := "REGULAR BUY"
	if ps {
		title = "PRE-SEND FILL"
	}
	title += "  " + core.T12Date(float64(tr.T), true) + " PKT"
	right := t.Lbl.Render(fmt.Sprintf("session %d", tr.S+1))
	_ = v
	inner := w
	if w >= 70 {
		inner = w - 4
	}
	return m.section(title, right, append(wrapLines(out, inner, lw), "", t.Dim.Render("esc back")), w)
}

// latencyLines: the Pre-send tab's latency: send -> seen of every seen try (p10 / p50 / p90) and how many landed in
// their send block; dump -> land of the fills and of the tries that failed 6042 after a dump that met the drop rule
// (the price had bounced back); the fills' send -> seen; how many slots after the trigger they filled; by leader
// client family when it fits.
func (m *Model) latencyLines(w int, ps core.AggPS) []string {
	t := m.th
	inner := w
	if w >= 70 {
		inner = w - 4
	}
	lat := m.latSummary()
	A := &lat.All
	sep := t.Lbl.Render(" " + core.G.Sep + " ")
	ms := func(x float64) string { return m.latStyle(x).Render(latMs(core.FloatNum(x))) }
	var out []string
	if A.Seen() == 0 {
		out = append(out, t.Lbl.Render("no try landings with timings in the records yet"))
	} else {
		q, _ := A.S2R.Quantiles(0.1, 0.5, 0.9)
		sb := float64(A.Blk[0]) / float64(A.Seen())
		x := t.Lbl.Render("p10 ") + ms(q[0]) + sep + t.Lbl.Render("p50 ") + ms(q[1]) + sep + t.Lbl.Render("p90 ") + ms(q[2])
		y := t.Lbl.Render("same block ") + t.Val.Render(core.F(sb*100, 0)+"%") + t.Lbl.Render(" of "+core.IC(A.Seen())+" tries")
		if ansi.StringWidth(m.kv("send→seen", 11, x+"   "+y)) <= inner {
			out = append(out, m.kv("send→seen", 11, x+"   "+y))
		} else {
			out = append(out, m.kv("send→seen", 11, x), m.kv("", 11, y))
		}
		dropS := core.F(lat.Drop*100, 0)
		// p10 / p50 / p90 (n), shorter when the width is short
		dist := func(label string, h *core.Hist) string {
			q, ok := h.Quantiles(0.1, 0.5, 0.9)
			if !ok {
				return m.kv(label, 11, t.Lbl.Render("dump→land "+core.G.Dash))
			}
			n := t.Lbl.Render(fmt.Sprintf("  (%d)", h.N))
			forms := []string{
				t.Lbl.Render("dump→land p10 ") + ms(q[0]) + sep + t.Lbl.Render("p50 ") + ms(q[1]) + sep + t.Lbl.Render("p90 ") + ms(q[2]) + n,
				t.Lbl.Render("dump→land p50 ") + ms(q[1]) + sep + t.Lbl.Render("p90 ") + ms(q[2]) + n,
				t.Lbl.Render("dump→land p50 ") + ms(q[1]) + n,
			}
			for _, f := range forms {
				if x := m.kv(label, 11, f); ansi.StringWidth(x) <= inner {
					return x
				}
			}
			return m.kv(label, 11, forms[len(forms)-1])
		}
		out = append(out, dist("fills", &A.FillDL), dist("bounced", &A.Bounce))
		note := "after a dump of >= " + dropS + "%; bounced = failed 6042, the price was back"
		if !m.ascii {
			note = "after a dump of ≥ " + dropS + "%; bounced = failed 6042, the price was back"
		}
		for _, l := range core.WrapText(note, max(10, inner-11), 0) {
			out = append(out, m.kv("", 11, t.Dim.Render(l)))
		}
	}
	// the fills: send -> seen (the engine's fill records) and how far into the window
	if lm, okl := core.Med(ps.LandMs); okl {
		out = append(out, m.kv("fills", 11, t.Lbl.Render("send→seen median ")+ms(lm)+t.Lbl.Render(fmt.Sprintf("  (%d)", len(ps.LandMs)))))
	}
	if len(ps.After) > 0 {
		var fs []float64
		cnt := map[int64]int{}
		for _, a := range ps.After {
			fs = append(fs, a.Float())
			k := min(a.Int(), 5)
			cnt[k]++
		}
		md, _ := core.Med(fs)
		var ks []int64
		for k := range cnt {
			ks = append(ks, k)
		}
		sort.Slice(ks, func(i, j int) bool { return ks[i] < ks[j] })
		var parts []string
		for _, k := range ks {
			p := fmt.Sprintf("+%d", k)
			if k == 5 {
				p += "+"
			}
			parts = append(parts, fmt.Sprintf("%s:%d", p, cnt[k]))
		}
		x := t.Lbl.Render("after the trigger median ") + t.Val.Render("+"+core.F(md, 0)) + t.Lbl.Render(" slots   "+strings.Join(parts, " "))
		if ansi.StringWidth(m.kv("", 11, x)) > inner {
			x = t.Lbl.Render("after the trigger median ") + t.Val.Render("+"+core.F(md, 0)) + t.Lbl.Render(" slots")
		}
		out = append(out, m.kv("", 11, x))
	}
	// by leader client family: the five that matter, the rest as "other"
	main := map[string]bool{"Harmonic": true, "BAM": true, "Jito": true, "Firedancer": true, "Agave": true}
	var kinds []string
	kind := map[string]*core.LatAgg{}
	for _, k := range lat.Kinds {
		if main[k] {
			kinds = append(kinds, k)
			kind[k] = lat.Kind[k]
			continue
		}
		if kind["other"] == nil {
			kind["other"] = &core.LatAgg{}
		}
		kind["other"].Merge(lat.Kind[k])
	}
	if kind["other"] != nil {
		kinds = append(kinds, "other")
	}
	if len(kinds) > 0 && A.Seen() > 0 {
		hdr := []string{"client", "tries", "same blk", "send→seen", "fills", "d→land", "bounced", "d→land"}
		if inner < 66 {
			hdr = []string{"client", "tries", "s→seen", "d→land", "bnc d→l"}
		}
		var rows [][]string
		var cells [][]float64 // the ms cells (for their colors), -1 none
		for _, k := range kinds {
			a := kind[k]
			q50 := func(h *core.Hist) (string, float64) {
				if x, ok := h.Quantile(0.5); ok {
					return latMs(core.FloatNum(x)), x
				}
				return core.G.Dash, -1
			}
			s2, s2v := q50(&a.S2R)
			fd, fdv := q50(&a.FillDL)
			bd, bdv := q50(&a.Bounce)
			sbs := core.G.Dash
			if a.Seen() > 0 {
				sbs = core.F(float64(a.Blk[0])/float64(a.Seen())*100, 0) + "%"
			}
			if inner < 66 {
				rows = append(rows, []string{core.RuneSlice(k, 10), core.IC(a.Seen()), s2, fd, bd})
				cells = append(cells, []float64{-1, -1, s2v, fdv, bdv})
			} else {
				rows = append(rows, []string{core.RuneSlice(k, 12), core.IC(a.Seen()), sbs, s2, fmt.Sprint(a.FillDL.N), fd, fmt.Sprint(a.Bounce.N), bd})
				cells = append(cells, []float64{-1, -1, -1, s2v, -1, fdv, -1, bdv})
			}
		}
		right := map[int]bool{1: true, 2: true, 3: true, 4: true, 5: true, 6: true, 7: true}
		out = append(out, strings.Split(m.kvTable(hdr, rows, right, func(r, c int) lipgloss.Style {
			if c == 0 {
				return t.Val
			}
			if v := cells[r][c]; v >= 0 {
				return m.latStyle(v)
			}
			return t.Lbl
		}), "\n")...)
		if inner >= 66 {
			out = append(out, t.Dim.Render("medians; fills / bounced after the drop rule; same blk = landed in the send block"))
		} else {
			out = append(out, t.Dim.Render("medians; bnc = bounced 6042"))
		}
	}
	return out
}

// latSummary is the pre-send latency of the sessions in scope (cached until the records move).
func (m *Model) latSummary() *core.LatSummary {
	M := m.ctx.Src.Model
	key := fmt.Sprintf("%d|%d", M.Version, m.scope)
	if key == m.latKey && m.latSum != nil {
		return m.latSum
	}
	v := m.view
	sel := v.Sessions
	if v.Scope >= 0 {
		sel = []*core.Sess{v.S}
	}
	s := core.LatOf(sel)
	m.latKey, m.latSum = key, &s
	return m.latSum
}

// latLine: "dump→land 34 ms · send→seen 70 ms · block +0 (the send block)", colored by speed.
func (m *Model) latLine(tr *core.Trade, ssName string) string {
	t := m.th
	dl, ss, blk := core.TradeLatency(tr)
	sep := t.Lbl.Render(" " + core.G.Sep + " ")
	ms := func(n core.Num) string {
		x := n.Float()
		if x < 10 {
			return m.latStyle(x).Render(core.F(x, 1) + " ms")
		}
		return m.latStyle(x).Render(core.F(x, 0) + " ms")
	}
	var parts []string
	if dl.Ok() {
		name := "dump→land "
		if tr.Kind != "PS" && tr.Land == nil {
			name = "dump→seen " // a failed buy: when it was seen (it landed failed)
		}
		parts = append(parts, t.Lbl.Render(name)+ms(dl))
	}
	if ss.Ok() {
		parts = append(parts, t.Lbl.Render(ssName+" ")+ms(ss))
	}
	if blk.Ok() {
		what := " (the send block)"
		if tr.Kind != "PS" {
			what = " (the dump's block)"
		}
		b := blk.Repr()
		if blk.Float() != 0 {
			unit := " slots"
			if b == "1" {
				unit = " slot"
			}
			what = unit + map[bool]string{true: " after the send", false: " after the dump"}[tr.Kind == "PS"]
		}
		parts = append(parts, t.Lbl.Render("block ")+m.blkStyle(blk).Render("+"+b)+t.Lbl.Render(what))
	}
	if len(parts) == 0 {
		return t.Lbl.Render(core.G.Dash + " (not in this run's records)")
	}
	return strings.Join(parts, sep)
}

// sessOf is the engine session of a trade.
func (m *Model) sessOf(tr *core.Trade) *core.Sess {
	ss := m.ctx.Src.Model.Sessions
	if tr.S >= 0 && tr.S < len(ss) {
		return ss[tr.S]
	}
	return nil
}

// ------------------------------------------------------------------------------------------------- help

var helpNotes = [][2]string{
	{"RUN P&L", "pre-send net + regular, after every fee; the same accounting as the run reports"},
	{"pre-send net", "realized (chain txs of each buy + sell) + token-account rent back − failed-attempt fees"},
	{"regular", "the engine's REALIZED P&L of each fill + each failed buy at its tx fee (~ = feed estimate until REALIZED)"},
	{"card", "profit (winning trades) − loss (losing trades) + rent − fees = the P&L; s switches this run / today"},
	{"ATH / Low", "the highest / lowest P&L of the chart's line (the run's, or today's with s); from ATH = now − the ATH"},
	{"latency", "d→land = ms from the dump to our landing, s→seen = from our send to seen, blk = slots after the send (regular: after the dump); green < 40 ms, yellow ≤ 120, red above"},
	{"total", "Trades: the run's P&L after each trade (the trades' P&L + rent back in time order, minus the failed tries' fees up to that minute); SOL or USD with u, like size"},
	{"sort", "Trades: o picks the column (time, type, mint, size, P&L, %, total, exit, held, d→land, s→seen, blk, after, whale, client, path), O flips the order; the header marks it"},
	{"links", "mints open GMGN, signatures / accounts Solscan (OSC 8: Ctrl / Cmd-click); c copies the mint (OSC 52; tmux: set -g set-clipboard on)"},
	{"wallet est.", "the session's START BALANCE + its P&L (no RPC: an estimate; unseen tries' fees are not in it)"},
	{"kill sw.", "how far the wallet is above the engine's kill switch (START BALANCE − loss cap)"},
	{"dots", "green = on, yellow = warming up / partial / stopped, red = off"},
	{"sound", "one terminal bell per closed trade (at most one per 2 s); --sound all|wins|big|off, m mutes"},
}

func (m *Model) helpContent(w int) string {
	t := m.th
	hm := m.helpM
	hm.SetWidth(w)
	var out []string
	groups := m.keys.FullHelp()
	if w < 66 { // phones: one column
		var one []key.Binding
		for _, g := range groups {
			one = append(one, g...)
		}
		groups = [][]key.Binding{one}
	}
	dim := func(s string) {
		for _, l := range core.WrapText(s, max(10, w), 0) {
			out = append(out, t.Dim.Render(l))
		}
	}
	out = append(out, strings.Split(hm.FullHelpView(groups), "\n")...)
	out = append(out, "")
	dim("mouse capture is off by default: select text and Ctrl / Cmd-click links (mints open GMGN) with the terminal itself; M turns it on (click a tab, wheel scrolls, click a trade, twice: details)")
	out = append(out, "")
	for _, n := range helpNotes {
		wl := core.WrapText(n[1], max(10, w-15), 0)
		out = append(out, t.AccB.Render(padRight(n[0], 14))+t.Val.Render(wl[0]))
		for _, l := range wl[1:] {
			out = append(out, strings.Repeat(" ", 14)+t.Val.Render(l))
		}
	}
	out = append(out, "")
	dim("read-only: the run files, the budget file and /proc; no RPC; SOL/USD from Binance / CoinGecko")
	dim("all times PKT (UTC+5)")
	_ = time.Second
	return strings.Join(out, "\n")
}
