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
// running total, in the primary unit); phones keep the money (Enter: details). usd: size and total in USD (u).
func tradeCols(w int, usd bool) []tcol {
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
		typ, tyS = "PS", t.Acc
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
			s, st = map[string]string{"PS": "PS", "REG": "RG"}[typ], tyS
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
		case "":
			s, st = " ", t.Acc
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
	cols := tradeCols(w, m.usdFirst && m.view.Price != 0)
	if sel >= 0 {
		cols = append([]tcol{{"", 1, false}}, cols...)
	}
	fixed := 0
	for _, c := range cols {
		fixed += c.w + 1
	}
	if last := &cols[len(cols)-1]; last.w == 0 {
		last.w = max(4, w-fixed)
	}
	data := make([][]string, len(rows))
	styles := make([][]lipgloss.Style, len(rows))
	for i, tr := range rows {
		cells, sts := m.tradeCells(tr, cols)
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
	return fmt.Sprintf("%s|%d|%d|%d|%d|%v|%v|%v|%d|%g", kind, w, h, m.ctx.Src.Model.TradeVer, len(m.view.Trades), m.dark, m.ascii,
		m.usdFirst, m.view.Scope, m.view.Price)
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
	if q := strings.TrimSpace(m.query); q != "" {
		var out []*core.Trade
		lq := strings.ToLower(q)
		for _, tr := range tl {
			if strings.HasPrefix(strings.ToLower(tr.Mint), lq) || strings.Contains(strings.ToLower(tr.Mint), lq) {
				out = append(out, tr)
			}
		}
		tl = out
	}
	return m.sortTrades(tl)
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
	left := t.AccB.Render("TRADES ") + t.Acc.Render(flt) + t.Lbl.Render(fmt.Sprintf("  (%d)", n))
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
		right += t.Dim.Render("   o sort  O order  f filter  / find  c copy  enter details")
	} else if w >= 70 {
		right += t.Dim.Render("   o sort  f filter  / find  c copy")
	}
	out := []string{lr(left, right, w)}
	if m.searching {
		m.search.SetWidth(max(10, w-4))
		out = append(out, m.search.View())
	}
	rowsAvail := bh - len(out) - 1
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
	if n > rowsAvail {
		m.moreHint = fmt.Sprintf("%d/%d", m.tradeSel+1, n)
	}
	return strings.Join(out, "\n")
}
