package ui

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

// screenModel prepares a model for one off-screen render (the data is already loaded).
func screenModel(ctx *core.Ctx, o Options, w, h int) *Model {
	o.NoAnim = true
	if o.Golden {
		ctx.Sys = &core.SysInfo{Path: "/", Disk: 42, HasDisk: true, Load: [3]float64{0.5, 0.4, 0.3}, HasLoad: true,
			MemUsed: 1 << 30, MemTotal: 2 << 30, NCPU: 2, OwnCPU: 0.1, HasOwn: true, OwnRSS: 30 << 20, Frozen: true}
	}
	m := New(ctx, o)
	m.screenMode = true
	m.w, m.h = w, h
	m.helpM.SetWidth(w)
	if ctx.Src.Loaded {
		m.afterLoad()
	}
	return m
}

func plain(s string, keepANSI bool) string {
	if !keepANSI {
		s = ansi.Strip(s)
	}
	ls := strings.Split(s, "\n")
	for i, l := range ls {
		ls[i] = strings.TrimRight(l, " ")
	}
	return strings.Join(ls, "\n") + "\n"
}

// RenderScreen renders the UI once at w x h (tab 0-6, or page help | detail | splash | today) as text.
func RenderScreen(ctx *core.Ctx, o Options, w, h, tab int, page string, keepANSI bool) string {
	m := screenModel(ctx, o, w, h)
	m.tab = max(0, min(6, tab))
	switch page {
	case "help":
		m.showHelp = true
	case "detail":
		m.detail = pickDetail(m)
		m.tab = 3
	case "splash":
		m.loading = true
		m.loadTotal = max(1, ctx.Src.DoneBytes()*100/43)
	case "today":
		m.todayOn = true
		m.today = screenToday(ctx, m.view.NowNS())
		m.refreshToday()
	}
	return plain(m.render(w, h), keepANSI)
}

// screenToday: the day's other runs, loaded once per run file and day for every screen rendered from it.
var (
	screenTodayMu sync.Mutex
	screenTodays  = map[string]*core.Today{}
)

func screenToday(ctx *core.Ctx, nowNS float64) *core.Today {
	d0, _, _ := core.DayRange(nowNS)
	key := fmt.Sprintf("%s|%d", ctx.Src.JSONL, d0)
	screenTodayMu.Lock()
	defer screenTodayMu.Unlock()
	if td := screenTodays[key]; td != nil {
		return td
	}
	td := core.NewToday(ctx.Src)
	td.Start(nowNS)
	for td.Step(core.LoadChunk) {
	}
	screenTodays[key] = td
	return td
}

func pickDetail(m *Model) *core.Trade {
	tl := core.SortedTrades(m.view.Trades, "all")
	for _, t := range tl {
		if t.Kind == "PS" && t.HasPnl {
			return t
		}
	}
	if len(tl) > 0 {
		return tl[0]
	}
	return nil
}

// DumpScreens writes every tab (+ help, a trade's details, the splash, the today card) at each size.
func DumpScreens(ctx *core.Ctx, o Options, dir string, sizes [][2]int, tag string, keepANSI bool) ([]string, error) {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, err
	}
	var written []string
	type pg struct {
		key  string
		tab  int
		page string
	}
	pages := []pg{{"01-overview", 0, ""}, {"02-presend", 1, ""}, {"03-regular", 2, ""}, {"04-trades", 3, ""}, {"05-health", 4, ""},
		{"06-log", 5, ""}, {"07-config", 6, ""}, {"08-help", 0, "help"}, {"09-detail", 3, "detail"}, {"10-splash", 0, "splash"},
		{"11-today", 0, "today"}}
	ext := ".txt"
	if keepANSI {
		ext = ".ans"
	}
	for _, sz := range sizes {
		for _, p := range pages {
			name := fmt.Sprintf("%dx%d_%s", sz[0], sz[1], p.key)
			if tag != "" {
				name += "-" + tag
			}
			fn := filepath.Join(dir, name+ext)
			out := RenderScreen(ctx, o, sz[0], sz[1], p.tab, p.page, keepANSI)
			if err := os.WriteFile(fn, []byte(out), 0o644); err != nil {
				return written, err
			}
			written = append(written, fn)
		}
	}
	return written, nil
}

func cardJSON(c core.Card) *core.JObj {
	o := &core.JObj{}
	o.Set("profit", c.Profit)
	o.Set("loss", c.Loss)
	o.Set("wins", c.Wins)
	o.Set("losses", c.Losses)
	o.Set("rent", c.Rent)
	o.Set("fees", c.Fees)
	o.Set("net", c.Net)
	o.Set("buys", c.Buys)
	o.Set("sells", c.Sells)
	o.Set("buy_sol", c.BuySol)
	o.Set("sell_sol", c.SellSol)
	if wr, ok := c.WinRate(); ok {
		o.Set("win_rate", wr)
	} else {
		o.Set("win_rate", nil)
	}
	if a, ok := c.AvgWin(); ok {
		o.Set("avg_win", a)
	} else {
		o.Set("avg_win", nil)
	}
	if a, ok := c.AvgLoss(); ok {
		o.Set("avg_loss", a)
	} else {
		o.Set("avg_loss", nil)
	}
	if pf, ok := c.PF(); ok {
		o.Set("pf", pf)
	} else {
		o.Set("pf", nil)
	}
	return o
}

// ExtraJSON: the v3 figures for --snapshot --json --extra: the trading card of the run and of the PKT day.
func ExtraJSON(ctx *core.Ctx, v *core.View) *core.JObj {
	o := &core.JObj{}
	o.Set("card", cardJSON(core.CardOf(v.Sessions, nil)))
	td := core.NewToday(ctx.Src)
	td.Start(v.NowNS())
	for td.Step(core.LoadChunk) {
	}
	c := td.Total(ctx.Src.Model)
	tj := cardJSON(c)
	tj.Set("day", c.Label)
	runs := make([]any, len(c.Runs))
	for i, r := range c.Runs {
		runs[i] = int64(r)
	}
	tj.Set("runs", runs)
	core.ATHJSON(tj, td.Series(ctx.Src.Model, v.NowNS(), c.Net)) // the day's ATH / low (the chart's with s)
	o.Set("today", tj)
	return o
}
