package ui

import (
	"sort"
	"strconv"
	"strings"

	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

// sortKeys: the Trades tab's sort columns, in the order o cycles them (O flips the order). time = newest first by default.
var sortKeys = []string{"time", "type", "mint", "size", "P&L", "%", "total", "exit", "held", "d→land", "s→seen", "blk", "after",
	"whale", "client", "path"}

// sortKeyOf maps a table column title to its sort key ("" = not sortable).
func sortKeyOf(title string) string {
	switch title {
	case "type", "typ", "ty":
		return "type"
	case "P&L SOL", "USD":
		return "P&L"
	case "":
		return ""
	}
	return title
}

// headerText: a column's header: the unit for size / total in USD mode, the sort arrow on the sorted column (Trades tab).
func (m *Model) headerText(c tcol, sortable bool) string {
	h := c.title
	usd := m.usdFirst && m.view != nil && m.view.Price != 0
	if usd && (h == "size" || h == "total") {
		h += " $"
	}
	if sortable && h != "" && sortKeyOf(c.title) == sortKeys[m.sortCol] {
		arrow := m.g("▼", "v")
		if m.sortAsc {
			arrow = m.g("▲", "^")
		}
		if ansi.StringWidth(h)+1 <= c.w || c.w == 0 {
			h = arrow + h
		} else {
			h = arrow + ansi.Truncate(h, max(0, c.w-1), "")
		}
	}
	if c.w > 0 {
		h = ansi.Truncate(h, c.w, "")
	}
	return h
}

// sortLabel: "P&L ▼" for the Trades title line.
func (m *Model) sortLabel() string {
	arrow := m.g("▼", "v")
	if m.sortAsc {
		arrow = m.g("▲", "^")
	}
	return sortKeys[m.sortCol] + " " + arrow
}

// heldNum: a trade's hold as a number (slots; a hold in seconds counts 2.5 slots a second) for sorting.
func heldNum(tr *core.Trade) (float64, bool) {
	h := core.TradeHeld(tr)
	switch {
	case strings.HasSuffix(h, "sl"):
		x, err := strconv.ParseFloat(strings.TrimSuffix(h, "sl"), 64)
		return x, err == nil
	case strings.HasSuffix(h, "s"):
		x, err := strconv.ParseFloat(strings.TrimSuffix(h, "s"), 64)
		return x * 2.5, err == nil
	}
	return 0, false
}

// sortVal: the trade's value for a sort key: a number or a string; ok false = no value (always sorted last).
func (m *Model) sortVal(tr *core.Trade, key string) (float64, string, bool) {
	switch key {
	case "time":
		return float64(tr.T), "", true
	case "type":
		return 0, tr.Kind, true
	case "mint":
		return 0, strings.ToLower(tr.Mint), tr.Mint != ""
	case "size":
		return float64(tr.Spend.Int()), "", tr.Spend.Ok()
	case "P&L":
		return float64(tr.Pnl), "", tr.HasPnl
	case "%":
		sp := tr.Spend.Int()
		if !tr.HasPnl || sp == 0 {
			return 0, "", false
		}
		return float64(tr.Pnl) / float64(sp), "", true
	case "total":
		x, ok := m.runTotals()[tr.ID]
		return float64(x), "", ok
	case "exit":
		return 0, core.TradeExit(tr), true
	case "held":
		x, ok := heldNum(tr)
		return x, "", ok
	case "d→land":
		d, _, _ := core.TradeLatency(tr)
		return d.Float(), "", d.Ok()
	case "s→seen":
		_, s, _ := core.TradeLatency(tr)
		return s.Float(), "", s.Ok()
	case "blk":
		_, _, b := core.TradeLatency(tr)
		return b.Float(), "", b.Ok()
	case "after":
		ok := tr.Kind == "PS" && tr.After.Ok()
		return tr.After.Float(), "", ok
	case "whale":
		ok := tr.Kind == "PS" && tr.TrigPct.Ok()
		return tr.TrigPct.Float(), "", ok
	case "client":
		c := core.KindOf(tr.Client)
		return 0, c, tr.Client != ""
	case "path":
		p := core.TradePath(tr)
		return 0, p, p != ""
	}
	return 0, "", false
}

// sortTrades orders tl (newest first already) by the Trades tab's sort: missing values last, ties newest first.
func (m *Model) sortTrades(tl []*core.Trade) []*core.Trade {
	key := sortKeys[m.sortCol]
	if key == "time" && !m.sortAsc {
		return tl
	}
	type kv struct {
		tr  *core.Trade
		f   float64
		s   string
		ok  bool
		idx int
	}
	xs := make([]kv, len(tl))
	for i, tr := range tl {
		f, s, ok := m.sortVal(tr, key)
		xs[i] = kv{tr, f, s, ok, i}
	}
	asc := m.sortAsc
	sort.SliceStable(xs, func(i, j int) bool {
		a, b := xs[i], xs[j]
		if a.ok != b.ok {
			return a.ok
		}
		if !a.ok {
			return a.idx < b.idx
		}
		if a.s != b.s {
			if asc {
				return a.s < b.s
			}
			return a.s > b.s
		}
		if a.f != b.f {
			if asc {
				return a.f < b.f
			}
			return a.f > b.f
		}
		return a.idx < b.idx
	})
	out := make([]*core.Trade, len(xs))
	for i, x := range xs {
		out[i] = x.tr
	}
	return out
}

// runTotals: the run's P&L after each trade: every trade's P&L (+ a pre-send fill's rent back) summed in time order,
// minus the failed pre-send tries' fees booked up to that trade's minute (they are not trades; the engine's extra fee
// count at its session's end, an old run's log fees at its start), so the last row is the run P&L when no try failed
// after the last trade. Cached per data version / scope.
func (m *Model) runTotals() map[int]int64 {
	v := m.view
	if v == nil {
		return nil
	}
	M := m.ctx.Src.Model
	key := strconv.FormatInt(M.TradeVer, 10) + "|" + strconv.Itoa(len(v.Trades)) + "|" + strconv.Itoa(v.Scope) + "|" +
		strconv.Itoa(M.Version)
	if key == m.totKey && m.totals != nil {
		return m.totals
	}
	const minNS = int64(60e9)
	fmin := func(t int64) int64 {
		q := t / minNS
		if t%minNS < 0 {
			q--
		}
		return q
	}
	// the failed tries' fees by minute
	var fees []core.MinAmt
	for i, S := range M.Sessions {
		if v.Scope >= 0 && i != v.Scope {
			continue
		}
		if S.PSRec {
			for mn, f := range S.FeeBuckets {
				fees = append(fees, core.MinAmt{Amt: f, Min: mn})
			}
			if adj := S.PSFees() - S.PSFeeCnt; adj != 0 {
				te := S.TEnd()
				if te == 0 {
					te = S.CurT
				}
				fees = append(fees, core.MinAmt{Amt: adj, Min: fmin(te)})
			}
		} else if S.LogPSFees != 0 {
			fees = append(fees, core.MinAmt{Amt: S.LogPSFees, Min: fmin(S.T0)})
		}
	}
	sort.Slice(fees, func(i, j int) bool { return fees[i].Min < fees[j].Min })
	tl := make([]*core.Trade, len(v.Trades))
	copy(tl, v.Trades)
	sort.SliceStable(tl, func(i, j int) bool {
		if tl[i].T != tl[j].T {
			return tl[i].T < tl[j].T
		}
		return tl[i].ID < tl[j].ID
	})
	out := make(map[int]int64, len(tl))
	var run int64
	fi := 0
	for _, tr := range tl {
		if !tr.HasPnl && !tr.HasRent {
			continue
		}
		for tm := fmin(tr.T); fi < len(fees) && fees[fi].Min <= tm; fi++ {
			run -= fees[fi].Amt
		}
		if tr.HasPnl {
			run += tr.Pnl
		}
		if tr.HasRent {
			run += tr.Rent
		}
		out[tr.ID] = run
	}
	m.totKey, m.totals = key, out
	return out
}

// gmgnURL: the token's GMGN page.
func gmgnURL(mint string) string { return "https://gmgn.ai/sol/token/" + mint }

// linksOn: OSC 8 hyperlinks (off with --no-links, --ascii, --no-color; terminals without OSC 8 ignore them).
func (m *Model) linksOn() bool { return !m.opt.NoLinks && !m.ascii && !m.th.Mono }

// hdrCell: a Trades header cell's x range and its sort key.
type hdrCell struct {
	x0, x1 int
	key    string
}

// clickHeader sorts by the clicked column (a second click on the sorted column flips the order).
func (m *Model) clickHeader(x int) {
	for _, h := range m.hdrX {
		if x < h.x0 || x >= h.x1 || h.key == "" {
			continue
		}
		for i, k := range sortKeys {
			if k == h.key {
				if i == m.sortCol {
					m.sortAsc = !m.sortAsc
				} else {
					m.sortCol, m.sortAsc = i, false
				}
				m.tradeSel, m.tradeTop = 0, 0
				return
			}
		}
	}
}
