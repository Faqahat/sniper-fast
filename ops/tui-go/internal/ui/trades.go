package ui

import (
	"fmt"
	"image/color"
	"strings"

	"charm.land/lipgloss/v2"
	"charm.land/lipgloss/v2/table"
	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

type tcol struct {
	title string
	w     int
	right bool
}

// tradeCols: the columns that fit w. Latency (ms): d→land = dump to landing, s→seen = send to seen, blk = the block
// it landed in (pre-send: slots after the send; regular: after the dump); total = the run's P&L after this trade (the
// running total, in the primary unit); phones keep the money (Enter: details). usd: size and total in USD (u). via
// (dip26, a run whose pre-send tries go over two or more paths): the filling try's path in two letters (HL / AS)
// before the client, where there is room (80 columns and up).
func tradeCols(w int, usd, via bool, arm ...bool) []tcol {
	cols := tradeCols0(w, usd)
	if !via || w < 80 {
		return cols
	}
	add := []tcol{{"via", 3, false}}
	if len(arm) > 0 && arm[0] && w >= 110 { // v4 (dip43 snipe-guard A/B): the filling try's arm, G snipe-guard / L Lighthouse
		add = append(add, tcol{"arm", 3, false})
	}
	for i, c := range cols {
		if c.title == "client" {
			return append(cols[:i:i], append(add, cols[i:]...)...)
		}
	}
	return cols
}

// armOn: the run's tries carry the snipe-guard A/B (dip43): the Trades table gets the arm column.
func (m *Model) armOn() bool {
	R := m.view.D43
	if R == nil {
		return false
	}
	for _, f := range R.Fills {
		if f.Arm != "" {
			return true
		}
	}
	return false
}

// d43Of: a trade's dip43 view (nil = none).
func (m *Model) d43Of(tr *core.Trade) *core.D43Fill {
	if tr == nil || tr.Kind != "PS" || !tr.W.Ok || m.view == nil {
		return nil
	}
	return m.view.D43.Fill(tr.W.W, tr.Mint)
}

func tradeCols0(w int, usd bool) []tcol {
	sz, tot := 5, 10
	if usd {
		sz = 6
	}
	switch {
	case w >= 150:
		return []tcol{{"time", 11, true}, {"type", 4, false}, {"mint", 8, false}, {"size", sz, true}, {"P&L SOL", 10, true},
			{"USD", 9, true}, {"%", 7, true}, {"total", tot, true}, {"exit", 5, false}, {"held", 5, true}, {"d→land", 6, true},
			{"s→seen", 6, true}, {"blk", 3, true}, {"after", 5, true}, {"whale", 6, true}, {"client", 10, false}, {"path", 0, false}}
	case w >= 125:
		return []tcol{{"time", 11, true}, {"type", 4, false}, {"mint", 8, false}, {"size", sz, true}, {"P&L SOL", 10, true},
			{"USD", 9, true}, {"%", 7, true}, {"total", tot, true}, {"exit", 5, false}, {"held", 5, true}, {"d→land", 6, true},
			{"s→seen", 6, true}, {"blk", 3, true}, {"client", 10, false}, {"path", 0, false}}
	case w >= 110:
		return []tcol{{"time", 11, true}, {"type", 4, false}, {"mint", 8, false}, {"size", sz, true}, {"P&L SOL", 10, true},
			{"USD", 9, true}, {"%", 7, true}, {"total", tot, true}, {"exit", 5, false}, {"d→land", 6, true}, {"blk", 3, true},
			{"client", 10, false}, {"path", 0, false}}
	case w >= 90:
		return []tcol{{"time", 11, true}, {"typ", 3, false}, {"mint", 6, false}, {"P&L SOL", 10, true}, {"USD", 8, true},
			{"%", 7, true}, {"total", 9, true}, {"exit", 5, false}, {"d→land", 6, true}, {"blk", 3, true}, {"client", 0, false}}
	case w >= 70:
		return []tcol{{"time", 11, true}, {"typ", 3, false}, {"mint", 6, false}, {"P&L SOL", 10, true}, {"USD", 8, true},
			{"total", 9, true}, {"exit", 5, false}, {"d→land", 6, true}, {"client", 0, false}}
	}
	return []tcol{{"time", 11, true}, {"ty", 2, false}, {"mint", 6, false}, {"P&L SOL", 10, true}, {"USD", 7, true}, {"exit", 4, false}}
}

// latMs is a latency for a narrow column: "34", "307", "1.2s"; "" when unknown.
func latMs(n core.Num) string {
	if !n.Ok() {
		return ""
	}
	x := n.Float()
	switch {
	case x >= 999.5:
		return core.F(x/1000, 1) + "s"
	case x >= 0 && x < 0.5:
		return "<1"
	}
	return core.F(x, 0)
}

// latStyle: green under 40 ms, yellow to 120, red above (not bold: calm).
func (m *Model) latStyle(ms float64) lipgloss.Style {
	switch {
	case ms < 40:
		return m.th.Good
	case ms <= 120:
		return m.th.Warn
	}
	return m.th.Neg
}

// blkStyle: green for the send block (0), quiet otherwise.
func (m *Model) blkStyle(n core.Num) lipgloss.Style {
	if n.Ok() && n.Float() == 0 {
		return m.th.Good
	}
	return m.th.Lbl
}

// tradeCells: one trade's cells (plain text) and their styles.
func (m *Model) tradeCells(tr *core.Trade, cols []tcol) ([]string, []lipgloss.Style) {
	if tr.Skip != nil {
		return m.skipCells(tr.Skip, cols)
	}
	t := m.th
	v := m.view
	p, hp := tr.Pnl, tr.HasPnl
	spend := tr.Spend.Int()
	ps := t.Money(p, hp, false)
	est := " "
	if hp && tr.Src == "est" {
		est = "~"
	}
	pS := core.G.Dash
	if hp {
		pS = core.Sol(p, true, 4, true) + est
	}
	uS := ""
	if hp && v.Price != 0 {
		uS = core.Usd(p, true, v.Price, true, 2)
	}
	pct := ""
	if hp && spend != 0 {
		pct = core.PctS(float64(p)/float64(spend), true, 1, true)
	}
	ex := core.TradeExit(tr)
	exS := t.Val
	switch ex {
	case "time", "open", "hold":
		exS = t.Lbl
	case "6042", "6001", "fail", "drop", "SL":
		exS = t.Warn
	}
	typ := "REG"
	tyS := t.Val
	if tr.Kind == "PS" {
		typ, tyS = "T2", t.Acc
		if tr.Rearm {
			typ = "RA"
		}
	}
	var cells []string
	var sts []lipgloss.Style
	for _, c := range cols {
		var s string
		st := t.Val
		switch c.title {
		case "time":
			s, st = core.T12(float64(tr.T), true), t.Lbl
		case "type", "typ":
			s, st = typ, tyS
		case "ty":
			s, st = map[string]string{"T2": "T2", "RA": "RA", "REG": "RG"}[typ], tyS
		case "mint":
			s = core.Short(tr.Mint, c.w)
		case "size":
			s, st = core.F(float64(spend)/core.LAM, 2), t.Lbl
			if m.usdFirst && v.Price != 0 {
				s = core.UsdAmt(spend, true, v.Price, true)
			}
		case "total": // the run's P&L after this trade (trades in time order), in the primary unit
			if x, ok := m.runTotals()[tr.ID]; ok {
				st = t.Money(x, true, false)
				s = core.Sol(x, true, 4, true)
				if m.usdFirst && v.Price != 0 {
					s = core.Usd(x, true, v.Price, true, 2)
				}
			}
		case "P&L SOL":
			s, st = pS, ps
		case "USD":
			s, st = uS, ps
		case "%":
			s, st = pct, ps
		case "exit":
			s, st = ex, exS
			if c.w == 4 {
				s = core.RuneSlice(ex, 4)
			}
		case "held":
			s, st = core.TradeHeld(tr), t.Lbl
		case "d→land":
			dl, _, _ := core.TradeLatency(tr)
			s, st = latMs(dl), m.latStyle(dl.Float())
		case "s→seen":
			_, ss, _ := core.TradeLatency(tr)
			s, st = latMs(ss), m.latStyle(ss.Float())
		case "blk":
			_, _, b := core.TradeLatency(tr)
			if b.Ok() {
				s = b.Repr()
			}
			st = m.blkStyle(b)
		case "after": // a pre-send fill: N slots after the trigger (a regular buy's block is in blk)
			st = t.Lbl
			if tr.Kind == "PS" && tr.After.Ok() {
				s = "+" + tr.After.Repr()
			}
		case "whale": // the dump that armed the pre-send window, % of the curve
			st = t.Lbl
			if tr.Kind == "PS" && tr.TrigPct.Ok() {
				s = core.F(tr.TrigPct.Float(), 1) + "%"
			}
		case "client":
			s = core.RuneSlice(core.KindOf(tr.Client), 10)
		case "path":
			s, st = core.RuneSlice(core.TradePath(tr), 28), t.Lbl
		case "via": // dip26: the filling try's path (HL helius-ps, AS astralane-ps, ...)
			s, st = core.PathCode(core.TradePath(tr)), t.Acc
		case "arm": // dip43: the filling try's guard arm
			if f := m.d43Of(tr); f != nil {
				s, st = f.Arm, t.Acc
			}
		case "b+1": // v5 (dip48)
			if f := m.v5Of(tr); f != nil {
				s, st = f.FlowCell(), t.Lbl
			}
		case "riv": // v5 (dip49)
			if f := m.v5Of(tr); f != nil {
				s, st = f.RivalCell(), t.Lbl
				if f.Rival != nil && f.Rival.Blocked {
					st = t.Warn
				}
			}
		case "fv": // v5 (dip47)
			if f := m.v5Of(tr); f != nil {
				s, st = f.FvCell(), t.Lbl
				if strings.HasSuffix(s, "*") {
					st = t.Warn
				}
			}
		case "":
			s, st = " ", t.Acc
		case "flag":
			s, st = " ", t.Warn
			if m.flagged(tr) {
				s = m.dot()
			}
		}
		cells = append(cells, s)
		sts = append(sts, st)
	}
	return cells, sts
}

// hlBg is a row's highlight background while its P&L is fresh (fading over ~2 s), nil when none.
func (m *Model) hlBg(tr *core.Trade) (color.Color, float64) {
	if !m.anim || m.th.Mono {
		return nil, 0
	}
	h, ok := m.hl[tr.ID]
	if !ok {
		return nil, 0
	}
	age := m.now().Sub(h.at)
	if age >= animSpan {
		return nil, 0
	}
	soft := m.th.GreenSoft
	if h.pnl < 0 {
		soft = m.th.RedSoft
	}
	k := float64(age) / float64(animSpan)
	steps := lipgloss.Blend1D(16, soft, m.th.Zebra)
	return steps[min(15, int(k*16))], k
}

// tradeTable renders rows with the Lip Gloss table: header, zebra rows, the selection, the fresh-trade highlight.
func (m *Model) tradeTable(w int, rows []*core.Trade, sel int) string {
	t := m.th
	cols := tradeCols(w, m.usdFirst && m.view.Price != 0, m.viaOn(), m.armOn())
	var add5 []tcol
	if m.fvOn() && w >= 110 { // v5 (dip47): the filter state's version at the window's arm ("*": it moved before the fill)
		add5 = append(add5, tcol{"fv", 4, true})
	}
	if R := m.view.V5; R != nil && w >= 110 {
		if R.FlowOn { // v5 (dip48): outside buy SOL through fill+1
			add5 = append(add5, tcol{"b+1", 5, true})
		}
		if R.RivalOn { // v5 (dip49): rivals / dev age at the filling try
			add5 = append(add5, tcol{"riv", 7, true})
		}
	}
	if len(add5) > 0 {
		for i, c := range cols {
			if c.title == "client" {
				cols = append(cols[:i:i], append(add5, cols[i:]...)...)
				break
			}
		}
	}
	if sel >= 0 {
		cols = append([]tcol{{"", 1, false}}, cols...)
	}
	fixed := 0
	for _, c := range cols {
		fixed += c.w + 1
	}
	// the yellow dot of a trade some LOG rule would have blocked: its own 1-cell column after the marker (Trades) or first
	// (the overview's last trades, no marker) when the table has room, else inside the type column (the narrowest one)
	dotInType := false
	if m.view.Filt.NFlagged() > 0 {
		at := 0
		if sel >= 0 {
			at = 1
		}
		if fixed+2 <= w-4 {
			cols = append(cols[:at:at], append([]tcol{{"flag", 1, false}}, cols[at:]...)...)
			fixed += 2
		} else {
			dotInType = true
		}
	}
	if last := &cols[len(cols)-1]; last.w == 0 {
		last.w = max(4, w-fixed)
	}
	data := make([][]string, len(rows))
	styles := make([][]lipgloss.Style, len(rows))
	for i, tr := range rows {
		cells, sts := m.tradeCells(tr, cols)
		if dotInType && m.flagged(tr) {
			for j, c := range cols {
				if (c.title == "type" || c.title == "typ" || c.title == "ty") && c.w > 0 {
					r := []rune(cells[j])
					if len(r) >= c.w {
						r = r[:c.w-1]
					}
					cells[j] = string(r) + m.dot()
					sts[j] = m.th.Warn
				}
			}
		}
		if sel >= 0 && i == sel {
			cells[0] = m.g("▸", ">")
		}
		for j := range cells {
			cells[j] = ansi.Truncate(cells[j], cols[j].w, "…")
		}
		data[i], styles[i] = cells, sts
	}
	if sel >= 0 { // the header cells' x ranges (a click on a header sorts by it)
		m.hdrX = m.hdrX[:0]
		x := 0
		for _, c := range cols {
			cw := c.w + 1
			if c.title == "" {
				cw = 1
			}
			m.hdrX = append(m.hdrX, hdrCell{x, x + cw, sortKeyOf(c.title)})
			x += cw
		}
	}
	headers := make([]string, len(cols))
	sortCol := -1
	for j, c := range cols {
		headers[j] = m.headerText(c, sel >= 0)
		if sel >= 0 && sortKeyOf(c.title) == sortKeys[m.sortCol] && c.title != "" {
			sortCol = j
		}
	}
	tb := table.New().
		Border(lipgloss.NormalBorder()).
		BorderTop(false).BorderBottom(false).BorderLeft(false).BorderRight(false).BorderColumn(false).
		BorderHeader(false).
		BorderStyle(t.Rule).
		Headers(headers...).
		Rows(data...).
		StyleFunc(func(row, col int) lipgloss.Style {
			c := cols[col]
			base := lipgloss.NewStyle().Width(c.w + 1).PaddingRight(1)
			if c.title == "" {
				base = lipgloss.NewStyle().Width(1)
			}
			if c.right {
				base = base.Align(lipgloss.Right)
			}
			if row == table.HeaderRow {
				if col == sortCol {
					return base.Inherit(t.Acc).Bold(true)
				}
				return base.Inherit(t.Lbl).Bold(false)
			}
			st := styles[row][col]
			s := base.Inherit(st)
			if c.title == "mint" && m.linksOn() { // OSC 8: the mint opens GMGN (Ctrl / Cmd-click in Ghostty, iTerm2, kitty, WezTerm)
				s = s.Hyperlink(gmgnURL(rows[row].Mint))
			}
			if !t.Mono && row%2 == 1 {
				s = s.Background(t.Zebra)
			}
			if bg, k := m.hlBg(rows[row]); bg != nil {
				s = s.Background(bg)
				if k < 0.2 {
					s = s.Bold(true)
				}
			}
			if row == sel {
				s = s.Background(t.SelBg).Bold(true)
				if t.Mono {
					s = s.Reverse(true)
				}
			}
			return s
		})
	return tb.Render()
}

// tradesPanel: the overview's last trades, filling h lines (a titled panel; cached while nothing changes).
func (m *Model) tradesPanel(w, h int) string {
	key := m.tradesKey("panel", w, h)
	if key != "" && key == m.trKey {
		return m.trOut
	}
	out := m.tradesPanelRaw(w, h)
	m.trKey, m.trOut = key, out
	return out
}

// tradesKey: the cache key of the last-trades block ("" while a highlight is fading: no caching).
func (m *Model) tradesKey(kind string, w, h int) string {
	for _, x := range m.hl {
		if m.anim && m.now().Sub(x.at) < animSpan {
			return ""
		}
	}
	return fmt.Sprintf("%s|%d|%d|%d|%d|%v|%v|%v|%d|%g|%d", kind, w, h, m.ctx.Src.Model.TradeVer, len(m.view.Trades), m.dark, m.ascii,
		m.usdFirst, m.view.Scope, m.view.Price, m.view.Filt.NFlagged()) // the dots: a fill can be flagged after its trade closed
}

func (m *Model) tradesPanelRaw(w, h int) string {
	v := m.view
	tl := core.SortedTrades(v.Trades, "all")
	n := max(0, h-3)
	rows := tl[:min(len(tl), n)]
	var nps, nreg int
	for _, x := range v.Trades {
		if x.Kind == "PS" {
			nps++
		} else {
			nreg++
		}
	}
	right := m.th.Lbl.Render(fmt.Sprintf("%d pre-send %s %d regular", nps, m.g("·", "|"), nreg))
	var body string
	if len(rows) == 0 {
		body = m.th.Lbl.Render("no trades yet")
	} else {
		body = m.tradeTable(w-4, rows, -1)
	}
	return m.panel("LAST TRADES", right, body, w, h)
}

// tradesBlock: the last trades under a rule (no box; cached while nothing changes).
func (m *Model) tradesBlock(w, h int) string {
	key := m.tradesKey("block", w, h)
	if key != "" && key == m.trKey {
		return m.trOut
	}
	out := m.tradesBlockRaw(w, h)
	m.trKey, m.trOut = key, out
	return out
}

func (m *Model) tradesBlockRaw(w, h int) string {
	v := m.view
	tl := core.SortedTrades(v.Trades, "all")
	n := max(0, h-2)
	rows := tl[:min(len(tl), n)]
	head := m.rule("LAST TRADES", "", w)
	if len(rows) == 0 {
		return head + "\n" + m.th.Lbl.Render("no trades yet")
	}
	return head + "\n" + m.tradeTable(w, rows, -1)
}

// filteredTrades: the Trades tab's list (filter + mint search).
func (m *Model) filteredTrades() []*core.Trade {
	tl := core.SortedTrades(m.view.Trades, filters[m.tfilter])
	if sk := m.skipRows(); len(sk) > 0 { // v5.1: the skipped tokens (t), merged newest first with the trades
		all := make([]*core.Trade, 0, len(tl)+len(sk))
		i, j := 0, 0
		for i < len(tl) || j < len(sk) {
			if j >= len(sk) || (i < len(tl) && tl[i].T >= sk[j].T) {
				all = append(all, tl[i])
				i++
			} else {
				all = append(all, sk[j])
				j++
			}
		}
		tl = all
	}
	if q := mintQuery(m.query); q != "" { // the mint search: %part% anywhere in the mint (the % signs optional), trades and skips
		var out []*core.Trade
		for _, tr := range tl {
			if strings.Contains(strings.ToLower(tr.Mint), q) {
				out = append(out, tr)
			}
		}
		tl = out
	}
	return m.sortTrades(tl)
}

// mintQuery: the search text as a lower-case substring ("%abc%", "abc%" and "abc" all mean "contains abc").
func mintQuery(q string) string {
	return strings.ToLower(strings.Trim(strings.TrimSpace(q), "%*"))
}

// skipRows: the skip rows the switch shows (nil when off), newest first; the trade filter's kind (T2 / RA) applies to them too.
func (m *Model) skipRows() []*core.Trade {
	if m.skipsMode == 0 || m.view == nil {
		return nil
	}
	flt := filters[m.tfilter]
	var out []*core.Trade
	for _, tr := range m.view.SkipTrades {
		r := tr.Skip
		if m.skipsMode == 1 && r.Cat != "filter" {
			continue
		}
		switch flt {
		case "pre-send", "all":
		case "T2", "t2":
			if r.Kind != "T2" {
				continue
			}
		case "re-arm", "RA", "rearm":
			if r.Kind != "RA" {
				continue
			}
		default: // a trade-only filter (wins, losses, regular, ...): no skips
			continue
		}
		out = append(out, tr)
	}
	return out
}

// scrTrades: every trade, newest first, a scrollable table with the selection; f filters, / searches a mint.
func (m *Model) scrTrades(w, bh int) string {
	t := m.th
	tl := m.filteredTrades()
	m.tradeRows = tl
	n := len(tl)
	if n == 0 {
		m.tradeSel = 0
	} else {
		m.tradeSel = max(0, min(m.tradeSel, n-1))
	}
	var wins int
	var tot int64
	for _, x := range tl {
		if x.HasPnl {
			tot += x.Pnl
			if x.Pnl > 0 {
				wins++
			}
		}
	}
	flt := filters[m.tfilter]
	nsk := 0
	var skr []core.SkipRow
	for _, x := range tl {
		if x.Skip != nil {
			nsk++
			skr = append(skr, *x.Skip)
		}
	}
	left := t.AccB.Render("TRADES ") + t.Acc.Render(flt) + t.Lbl.Render(fmt.Sprintf("  (%d)", n-nsk))
	if m.skipsMode > 0 { // v5.1: the switch's state, how many skips and what their paper would have made
		st := core.SumSkips(skr)
		lbl := map[int]string{1: "filter skips", 2: "all skips"}[m.skipsMode]
		left += t.Warn.Render("  + "+lbl) + t.Lbl.Render(fmt.Sprintf(" %d", nsk))
		if st.NoFill > 0 {
			left += t.Lbl.Render(fmt.Sprintf("  no dip %d", st.NoFill))
		}
		if st.Scored > 0 {
			left += t.Lbl.Render(fmt.Sprintf("  paper %dW/%dL ", st.WinN, st.LoseN)) + t.Money(int64(st.Paper*core.LAM), true, false).Render(core.FS(st.Paper, 3))
			if st.CalN > 0 {
				left += t.Lbl.Render(" cal ") + t.Money(int64(st.Cal*core.LAM), true, false).Render(core.FS(st.Cal, 3))
			}
		}
		if st.ProbeN > 0 {
			left += t.Lbl.Render(fmt.Sprintf("  probes %d ", st.ProbeN)) + t.Money(int64(st.Probe*core.LAM), true, false).Render(core.FS(st.Probe, 3))
		}
	}
	if m.query != "" && !m.searching {
		left += t.Lbl.Render("  mint ") + t.Val.Render(m.query+"…") + t.Dim.Render("  esc clears")
	}
	if !(sortKeys[m.sortCol] == "time" && !m.sortAsc) {
		left += t.Lbl.Render("  sort ") + t.Acc.Render(m.sortLabel())
	}
	right := t.Lbl.Render(fmt.Sprintf("%dW  ", wins)) + t.Money(tot, true, false).Render(core.SolS(tot))
	if m.usdFirst && m.view.Price != 0 {
		right = t.Lbl.Render(fmt.Sprintf("%dW  ", wins)) + t.Money(tot, true, false).Render(core.Usd(tot, true, m.view.Price, true, 2))
	}
	if w >= 100 {
		right += t.Dim.Render("   o sort  O order  f filter  t skips  / find  c copy  enter details")
	} else if w >= 70 {
		right += t.Dim.Render("   o sort  f filter  t skips  / find")
	}
	out := []string{lr(left, right, w)}
	if m.searching {
		m.search.SetWidth(max(10, w-4))
		out = append(out, m.search.View())
	}
	var why []string                                   // x: which filters would have blocked the selected trade
	if n > 0 && tl[min(m.tradeSel, n-1)].Skip != nil { // v5.1: a skip row always shows its panel
		why = m.skipLines(tl[min(m.tradeSel, n-1)].Skip, w)
	} else if m.tradeInfo && n > 0 {
		why = append([]string{m.rule("BLOCKED BY", "", w)}, m.whyLines(tl[min(m.tradeSel, n-1)], w)...)
	}
	rowsAvail := bh - len(out) - 1 - len(why)
	if rowsAvail < 1 {
		rowsAvail = 1
	}
	if m.tradeSel < m.tradeTop {
		m.tradeTop = m.tradeSel
	}
	if m.tradeSel >= m.tradeTop+rowsAvail {
		m.tradeTop = m.tradeSel - rowsAvail + 1
	}
	m.tradeTop = max(0, min(m.tradeTop, max(0, n-rowsAvail)))
	if n == 0 {
		msg := "no trades"
		if flt != "all" || m.query != "" {
			msg += " for this filter"
		}
		out = append(out, t.Lbl.Render(msg))
		m.tradeRowY = 0
		return strings.Join(out, "\n")
	}
	vis := tl[m.tradeTop:min(n, m.tradeTop+rowsAvail)]
	m.tradeRowY = m.bodyY + len(out) + 1
	out = append(out, m.tradeTable(w, vis, m.tradeSel-m.tradeTop))
	out = append(out, why...)
	if n > rowsAvail {
		m.moreHint = fmt.Sprintf("%d/%d", m.tradeSel+1, n)
	}
	return strings.Join(out, "\n")
}

// dot: the yellow flag mark ("*" in --ascii).
func (m *Model) dot() string { return m.g("\u25cf", "*") }

// flag: the filters that would have blocked this trade (the Filters tab's own LOG item: one source of truth).
func (m *Model) flag(tr *core.Trade) (core.FiltItem, bool) {
	if tr == nil || tr.Kind != "PS" || !tr.W.Ok || m.view == nil {
		return core.FiltItem{}, false
	}
	return m.view.Filt.Flag(tr.W.W, tr.Mint)
}

func (m *Model) flagged(tr *core.Trade) bool {
	_, ok := m.flag(tr)
	return ok
}

// whyLines: the x panel / the details' "blocked by" text for one trade, wrapped to w (at most 4 lines).
func (m *Model) whyLines(tr *core.Trade, w int) []string {
	t := m.th
	it, ok := m.flag(tr)
	if !ok {
		ls := []string{t.Lbl.Render("no filter would have blocked this trade")}
		if f := m.d43Of(tr); f != nil {
			for _, l := range core.WrapText("dip43: "+f.Brief(), max(10, w-2), 0) {
				ls = append(ls, t.Lbl.Render(l))
			}
		}
		return ls
	}
	txt := "would have been blocked by: " + it.Info()
	if f := m.d43Of(tr); f != nil { // v4: the fill's dip43 brief (arm, floors, band, landing depth, CASCADE G-A)
		txt += " · dip43: " + f.Brief()
	}
	ls := core.WrapText(txt, max(10, w-2), 0)
	if len(ls) > 4 {
		ls = ls[:4]
		ls[3] = ansi.Truncate(ls[3], max(1, w-4), "") + m.g("\u2026", "~")
	}
	out := make([]string, len(ls))
	for i, l := range ls {
		pre := "  "
		if i == 0 {
			pre = t.Warn.Render(m.dot()) + " "
		}
		out[i] = pre + t.Val.Render(l)
	}
	return out
}

// skipCells: a skipped token's row in the Trades table: type "SK·T2" / "SK·RA", the paper P&L (the trigger's shadow window at the
// live size; "~" = calibrated shown when there is one) in the P&L columns, the filter in the exit column, the price move in held.
func (m *Model) skipCells(r *core.SkipRow, cols []tcol) ([]string, []lipgloss.Style) {
	t := m.th
	v := m.view
	val, has := r.Paper, r.HasPaper
	mark := " "
	if r.HasCal {
		val, has, mark = r.Cal, true, "~"
	}
	if !has && r.HasProbePnl { // no shadow paper: the would-fill probe priced on the later probes' curve samples ("p")
		val, has, mark = r.ProbePnl, true, "p"
	}
	lam := int64(val * core.LAM)
	ps := t.Dim
	if has {
		ps = t.Money(lam, true, false).Faint(true)
	}
	wide := false // a table with a path column carries the filter there; a narrow one in the exit column
	for _, c := range cols {
		wide = wide || c.title == "path"
	}
	var cells []string
	var sts []lipgloss.Style
	for _, c := range cols {
		s, st := "", t.Dim
		switch c.title {
		case "time":
			if r.T != 0 {
				s = core.T12(float64(r.T), true)
			}
		case "type", "typ":
			s, st = "S"+m.g("\u00b7", ".")+r.Kind, t.Warn
			if c.w < 4 {
				s = "S" + r.Kind
			}
		case "ty":
			s, st = "S"+r.Kind[:1], t.Warn
		case "mint":
			s, st = core.Short(r.Mint, c.w), t.Lbl
		case "P&L SOL":
			s = core.G.Dash
			switch {
			case has:
				s, st = core.Sol(lam, true, 4, true)+mark, ps
			case r.ProbeWould > 0: // a probe would have filled but no later sample prices it
				s, st = "fill?", t.Warn
			case r.NoDip(): // the price never reached our limit (probes / the shadow window): the trade would not have happened
				s = "no dip"
			}
		case "USD":
			if has && v.Price != 0 {
				s, st = core.Usd(lam, true, v.Price, true, 2), ps
			}
		case "%":
			if has && v.Filt != nil && v.Filt.LiveSize > 0 {
				s, st = core.PctS(val/v.Filt.LiveSize, true, 1, true), ps
			}
		case "exit":
			s, st = "skip", t.Warn
			if r.Withheld {
				s = "held"
			}
			if r.Cat != "filter" {
				s, st = map[string]string{"busy": "busy", "not a setup": "n/a"}[r.Cat], t.Dim
			}
			if !wide {
				s = r.Name
			}
			s = core.RuneSlice(s, c.w)
		case "path", "client": // the wide columns: the filter that blocked it, then the shadow window's price move
			if c.title == "client" {
				break
			}
			s, st = r.Name, t.Warn
			if r.Cat != "filter" {
				st = t.Dim
			}
			if r.Move != nil && r.Move.N > 0 {
				s += fmt.Sprintf(" %+.0f/%+.0f%%", r.Move.Max, r.Move.Min)
			}
			s = core.RuneSlice(s, c.w)
		case "":
			s, st = " ", t.Acc
		}
		cells = append(cells, s)
		sts = append(sts, st)
	}
	return cells, sts
}

// skipLines: the selected skip row's panel under the table: the filter, the numbers, the paper / calibrated value, the move.
func (m *Model) skipLines(r *core.SkipRow, w int) []string {
	t := m.th
	head := fmt.Sprintf("%s %s skipped by %s", r.Kind, core.Short(r.Mint, 12), r.Name)
	if r.Withheld {
		head = fmt.Sprintf("%s %s: window armed, every try withheld by %s", r.Kind, core.Short(r.Mint, 12), r.Name)
	}
	val := "no paper (no shadow window"
	switch {
	case r.Kind == "RA" && !r.Shadow:
		val += ": re-arm windows have none)"
	case r.Shadow:
		val = "no dip: the shadow window never filled (the price never reached our limit; nothing saved or lost)"
	default:
		val += " for this trigger)"
	}
	if r.ProbeN > 0 {
		pv := fmt.Sprintf("probes: %d landed, %d would have filled", r.ProbeN, r.ProbeWould)
		if r.ProbeWould == 0 {
			pv += " = no dip: no trade would have happened (nothing saved or lost)"
		} else if r.HasProbePnl {
			pv += " → priced on the later probes' curve samples: " + core.FS(r.ProbePnl, 4) + "◎ (approx)"
		}
		val += " · " + pv
	}
	if r.HasPaper {
		val = "paper " + core.FS(r.Paper, 4) + "◎"
		if r.HasCal {
			val += ", calibrated " + core.FS(r.Cal, 4) + "◎"
		}
		if r.Move != nil && r.Move.N > 0 {
			val += fmt.Sprintf(", move %+.1f%% / %+.1f%% (%d trades)", r.Move.Max, r.Move.Min, r.Move.N)
		}
	}
	txt := head + " · " + val
	if r.Detail != "" {
		txt += " · " + r.Detail
	}
	ls := core.WrapText(txt, max(10, w-2), 0)
	if len(ls) > 4 {
		ls = ls[:4]
	}
	out := []string{m.rule("SKIP", "", w)}
	for _, l := range ls {
		out = append(out, "  "+t.Val.Render(l))
	}
	return out
}
