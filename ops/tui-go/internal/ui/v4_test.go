package ui

import (
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

// v4 (10-28): the Trades sort, the running total, size / total in the primary unit, the config blocks, links / copy /
// mouse, dipview.

func tradesModel(t *testing.T, path string, now float64, w, h int) *Model {
	ctx := loadCtx(t, path, now)
	o := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1, Strict: true}
	m := screenModel(ctx, o, w, h)
	m.tab = 3
	m.render(w, h)
	return m
}

// TestTradeSort: every sort key in both orders: the Trades tab's rows are ordered by the key's value (missing values
// last, ties newest first); the default is newest first (= the old order); o cycles, O flips, the header shows it.
func TestTradeSort(t *testing.T) {
	m := tradesModel(t, r27, r27End, 200, 35)
	def := core.SortedTrades(m.view.Trades, "all")
	got := m.filteredTrades()
	for i := range def {
		if def[i] != got[i] {
			t.Fatalf("default order differs at %d", i)
		}
	}
	for ki, key := range sortKeys {
		for _, asc := range []bool{false, true} {
			m.sortCol, m.sortAsc = ki, asc
			tl := m.filteredTrades()
			if len(tl) != len(def) {
				t.Fatalf("%s: %d rows, want %d", key, len(tl), len(def))
			}
			seenMissing := false
			for i := range tl {
				f, s, ok := m.sortVal(tl[i], key)
				if !ok {
					seenMissing = true
					continue
				}
				if seenMissing {
					t.Fatalf("%s asc=%v: a value after a missing one at row %d", key, asc, i)
				}
				if i == 0 {
					continue
				}
				pf, ps, pok := m.sortVal(tl[i-1], key)
				if !pok {
					continue
				}
				bad := false
				if s != "" || ps != "" {
					bad = (asc && ps > s) || (!asc && ps < s)
				} else {
					bad = (asc && pf > f) || (!asc && pf < f)
				}
				if bad {
					t.Fatalf("%s asc=%v: rows %d/%d out of order (%v %q / %v %q)", key, asc, i-1, i, pf, ps, f, s)
				}
			}
		}
	}
	// the keys: o cycles (each column starts descending), O flips; the header and the title show it
	m.sortCol, m.sortAsc = 0, false
	drive(m, tea.WindowSizeMsg{Width: 200, Height: 35})
	drive(m, keyMsg("4"))
	for i := 0; i < 4; i++ { // time -> type -> mint -> size -> P&L
		drive(m, keyMsg("o"))
	}
	out := ansi.Strip(drive(m, keyMsg("O")))
	if sortKeys[m.sortCol] != "P&L" || !m.sortAsc {
		t.Fatalf("o x4 + O: sort %s asc=%v", sortKeys[m.sortCol], m.sortAsc)
	}
	if !strings.Contains(out, "sort P&L ▲") || !strings.Contains(out, "▲P&L SOL") {
		t.Errorf("the sort is not shown:\n%s", out)
	}
	first := m.tradeRows[0]
	for _, tr := range m.tradeRows {
		if tr.HasPnl && tr.Pnl < first.Pnl {
			t.Fatalf("P&L ascending: the first row is not the worst trade")
		}
	}
	// a click on a header sorts by it (with the mouse on)
	m.mouseOn = true
	for _, h := range m.hdrX {
		if h.key == "whale" {
			drive(m, tea.MouseClickMsg(tea.Mouse{X: h.x0 + 1, Y: m.tradeRowY - 1, Button: tea.MouseLeft}))
		}
	}
	if sortKeys[m.sortCol] != "whale" || m.sortAsc {
		t.Errorf("header click: sort %s asc=%v, want whale desc", sortKeys[m.sortCol], m.sortAsc)
	}
}

// TestRunningTotal: on every local run the total column adds each trade's P&L + rent in time order, minus the failed
// tries' fees up to its minute; the last trade's total + the fees booked after its minute = the run P&L (the hero).
func TestRunningTotal(t *testing.T) {
	var files []string
	for _, d := range []string{"ams/runs", "fra/runs"} {
		fs, _ := filepath.Glob(filepath.Join(dataDir, d, "dip_*r*.jsonl"))
		files = append(files, fs...)
	}
	if len(files) == 0 {
		t.Skip("no local runs")
	}
	n := 0
	for _, f := range files {
		ctx := loadCtx(t, f, 0)
		m := screenModel(ctx, Options{Sound: "all", Version: "test", Golden: true}, 200, 35)
		v := m.view
		tot := m.runTotals()
		tl := append([]*core.Trade(nil), v.Trades...)
		sort.SliceStable(tl, func(i, j int) bool {
			if tl[i].T != tl[j].T {
				return tl[i].T < tl[j].T
			}
			return tl[i].ID < tl[j].ID
		})
		var last *core.Trade
		for _, tr := range tl {
			if tr.HasPnl || tr.HasRent {
				last = tr
			}
		}
		if last == nil {
			continue
		}
		// fees booked after the last trade's minute
		var after int64
		lm := floorMin(last.T)
		for _, S := range ctx.Src.Model.Sessions {
			if S.PSRec {
				for mn, fee := range S.FeeBuckets {
					if mn > lm {
						after += fee
					}
				}
				if adj := S.PSFees() - S.PSFeeCnt; adj != 0 {
					te := S.TEnd()
					if te == 0 {
						te = S.CurT
					}
					if floorMin(te) > lm {
						after += adj
					}
				}
			} else if S.LogPSFees != 0 && floorMin(S.T0) > lm {
				after += S.LogPSFees
			}
		}
		if got := tot[last.ID] - after; got != v.Total {
			t.Errorf("%s: last total %d - later fees %d = %d, run P&L %d", filepath.Base(f), tot[last.ID], after, got, v.Total)
		}
		n++
	}
	t.Logf("running total = run P&L on %d runs", n)
}

func floorMin(t int64) int64 {
	q := t / 60e9
	if t%int64(60e9) < 0 {
		q--
	}
	return q
}

// TestUnitSwitch: u switches size and total to USD (the header says $), and back.
func TestUnitSwitch(t *testing.T) {
	m := tradesModel(t, r27, r27End, 200, 35)
	drive(m, tea.WindowSizeMsg{Width: 200, Height: 35})
	drive(m, keyMsg("4"))
	sol := ansi.Strip(drive(m, keyMsg("down")))
	usd := ansi.Strip(drive(m, keyMsg("u")))
	back := ansi.Strip(drive(m, keyMsg("u")))
	if sol != back {
		t.Errorf("u twice does not come back to the same screen:\n%s", firstDiff(sol, back))
	}
	if !strings.Contains(usd, "size $") || !strings.Contains(usd, "total $") || strings.Contains(sol, "size $") {
		t.Errorf("headers: SOL %v / USD %v", strings.Contains(sol, "size $"), strings.Contains(usd, "size $"))
	}
	// r27's first row: 0.35 SOL at $187.42 = $65.60, the total +0.5879 SOL = +$110.19
	row := func(s string) string {
		for _, l := range strings.Split(s, "\n") {
			if strings.Contains(l, "CKTeAGpo") {
				return l
			}
		}
		return ""
	}
	if r := row(usd); !strings.Contains(r, "$65.60") || !strings.Contains(r, "+$110.19") {
		t.Errorf("USD row: %q", r)
	}
	if r := row(sol); !strings.Contains(r, " 0.35 ") || !strings.Contains(r, "+0.5879") {
		t.Errorf("SOL row: %q", r)
	}
	// the overview's last trades follow too
	m.tab = 0
	m.usdFirst = true
	m.bodyK = ""
	if !strings.Contains(ansi.Strip(m.render(200, 35)), "total $") {
		t.Errorf("overview: the total column does not follow u")
	}
}

// TestConfigBlocks: the overview's CONFIG and the Config tab in blocks at 80 / 120 / 200 columns: every block,
// every field the old grid showed, nothing wider than the terminal.
func TestConfigBlocks(t *testing.T) {
	ctx := loadCtx(t, r27, r27End)
	o := Options{Sound: "all", Version: "test", Golden: true}
	fields := [][]string{ // each: the long or the short form
		{"4 tries/slot", "4/slot"}, {"SL −20%"}, {"49/1000"}, {"0.02/0.40"}, {"guard +5%", "+5%"}, {"SL −50%"},
		{"M2 gate", "M2"}, {"Dev list", "Dev"}, {"v13"}, {"near leaders 120", "near 120"}, {"fan"}, {"nonce"}, {"Rakurai"},
		{"kill switch 4.432", "kill 4.432"}, {"2:10"}, {"dip20"}, {"stop"}, {"skip"}, {"paper"},
	}
	for _, sz := range [][2]int{{200, 35}, {120, 40}, {80, 24}} {
		ov := RenderScreen(ctx, o, sz[0], sz[1], 0, "", false)
		cfg := RenderScreen(ctx, o, sz[0], 200, 6, "", false)
		for _, s := range []string{ov, cfg} {
			for i, l := range strings.Split(strings.TrimSuffix(s, "\n"), "\n") {
				if w := ansi.StringWidth(l); w > sz[0] {
					t.Errorf("%dx%d line %d: %d cells", sz[0], sz[1], i+1, w)
				}
			}
		}
		for _, b := range cfgBlockTitles {
			if !strings.Contains(cfg, b) {
				t.Errorf("%d cols: the Config tab has no %s block", sz[0], b)
			}
		}
		if sz[0] >= 120 {
			for i, b := range cfgBlockTitles {
				if !strings.Contains(ov, b) && !strings.Contains(ov, cfgBlockShort[i]) {
					t.Errorf("%d cols: the overview has no %s block", sz[0], b)
				}
			}
			for _, f := range fields {
				ok := false
				for _, x := range f {
					ok = ok || strings.Contains(ov, x)
				}
				if !ok {
					t.Errorf("%d cols: the overview's config lost %q", sz[0], f[0])
				}
			}
		}
	}
	// every config item is in the Config tab, under its block
	m := screenModel(ctx, o, 120, 40)
	for _, it := range m.view.CfgItems {
		found := false
		for bi := range cfgBlockKeys {
			for _, x := range blockItems(m.view.CfgItems, bi) {
				found = found || x.Key == it.Key
			}
		}
		if !found {
			t.Errorf("config item %s in no block", it.Key)
		}
	}
}

// TestLinksCopyMouse: mints link to GMGN (OSC 8) in the table and the details, signatures to Solscan; --no-links
// none; the mouse is off by default (M toggles); c copies the selected mint (OSC 52).
func TestLinksCopyMouse(t *testing.T) {
	m := tradesModel(t, r28, r28End, 200, 35)
	drive(m, tea.WindowSizeMsg{Width: 200, Height: 35})
	if m.View().MouseMode != tea.MouseModeNone {
		t.Errorf("mouse capture is on by default")
	}
	out := drive(m, keyMsg("4"))
	sel := m.tradeRows[0]
	if !strings.Contains(out, "\x1b]8;;https://gmgn.ai/sol/token/"+sel.Mint) {
		t.Errorf("Trades: the mint is not a GMGN link")
	}
	cmd := m.onKey(keyMsg("c"))
	if cmd == nil || !strings.HasPrefix(m.flash, "copied "+sel.Mint[:8]) {
		t.Errorf("c: no clipboard command / flash %q", m.flash)
	}
	det := drive(m, keyMsg("enter"))
	for _, u := range []string{"https://gmgn.ai/sol/token/" + sel.Mint, "https://solscan.io/token/" + sel.Mint} {
		if !strings.Contains(det, "\x1b]8;;"+u) {
			t.Errorf("details: no link to %s", u)
		}
	}
	for _, s := range sel.BuySigs {
		if !strings.Contains(det, "\x1b]8;;https://solscan.io/tx/"+s) {
			t.Errorf("details: the buy tx is not a link")
		}
	}
	if !strings.Contains(ansi.Strip(det), "gmgn       https://gmgn.ai/sol/token/") {
		t.Errorf("details: no gmgn line")
	}
	drive(m, keyMsg("M"))
	if m.View().MouseMode != tea.MouseModeCellMotion {
		t.Errorf("M: the mouse is not captured")
	}
	// --no-links
	ctx := loadCtx(t, r28, r28End)
	m2 := screenModel(ctx, Options{Sound: "all", Version: "test", Golden: true, NoLinks: true}, 200, 35)
	m2.tab = 3
	if s := m2.render(200, 35); strings.Contains(s, "\x1b]8;;http") {
		t.Errorf("--no-links: links in the Trades tab")
	}
}

// TestDipview: the run list of a directory of real run files (copied read-only; DIPVIEW_DATA), both regions and a
// log-only run: names, order, the numbers equal dipmon's own (core.BuildView) for every run; the screens fit.
func TestDipview(t *testing.T) {
	dir := os.Getenv("DIPVIEW_DATA")
	if dir == "" {
		dir = filepath.Join(dataDir, "ams/runs")
	}
	if _, err := os.Stat(dir); err != nil {
		t.Skip("no " + dir)
	}
	e := NewExplorer(dir, Options{Version: "test"}, core.NewPrice(187.42, false))
	e.Duty = 0
	e.Scan()
	e.ComputeAll()
	runs, sums := e.Runs()
	ents, _ := os.ReadDir(dir)
	tags := map[string]bool{}
	for _, x := range ents {
		if mm := runFileRX.FindStringSubmatch(x.Name()); mm != nil {
			tags[strings.TrimSuffix(strings.TrimSuffix(x.Name(), ".jsonl"), ".log")] = true
		}
	}
	if len(runs) != len(tags) {
		t.Fatalf("%d runs listed, %d in the directory", len(runs), len(tags))
	}
	for i, r := range runs {
		if !tags[r.Tag] {
			t.Errorf("unknown run %s", r.Tag)
		}
		if (r.Region == "AMS") != strings.HasPrefix(r.Tag, "dip_ams_") {
			t.Errorf("%s: region %s", r.Tag, r.Region)
		}
		if i > 0 && !runs[i-1].Running && !r.Running {
			a, b := runs[i-1].T0, r.T0
			if a == 0 {
				a = runs[i-1].MTime.UnixNano()
			}
			if b == 0 {
				b = r.MTime.UnixNano()
			}
			if a < b {
				t.Errorf("order: %s before %s", runs[i-1].Tag, r.Tag)
			}
		}
		s := sums[r.Tag]
		if !r.HasJ {
			if s != nil {
				t.Errorf("%s: log-only run has numbers", r.Tag)
			}
			continue
		}
		if s == nil {
			t.Fatalf("%s: no numbers", r.Tag)
		}
		ctx := loadCtx(t, r.JSONL, 0)
		v := core.BuildView(ctx, -1)
		if s.Total != v.Total || s.PSFills != v.PS.Fills || s.PSWins != v.PS.Wins || s.RegFires != v.Reg.Fires || s.Build != v.Build || s.TFirst != v.TFirst {
			t.Errorf("%s: explorer %+v != dipmon total %d fills %d", r.Tag, s, v.Total, v.PS.Fills)
		}
		if r.T0 != 0 && s.TFirst != 0 && r.T0 != s.TFirst {
			t.Logf("%s: first record t %d, first session %d", r.Tag, r.T0, s.TFirst)
		}
	}
	txt := e.ListText()
	if strings.Count(txt, "\n") != len(runs) {
		t.Errorf("--list: %d lines for %d runs", strings.Count(txt, "\n"), len(runs))
	}
	for _, sz := range [][2]int{{200, 35}, {120, 40}, {80, 24}, {50, 30}} {
		for _, keep := range []bool{false, true} {
			s := ExplorerScreen(e, sz[0], sz[1], keep)
			ls := strings.Split(strings.TrimSuffix(s, "\n"), "\n")
			if len(ls) != sz[1] {
				t.Errorf("%dx%d: %d lines", sz[0], sz[1], len(ls))
			}
			for i, l := range ls {
				if w := ansi.StringWidth(l); w > sz[0] {
					t.Errorf("%dx%d line %d: %d cells", sz[0], sz[1], i+1, w)
				}
			}
		}
	}
	// keys: down / enter picks a run with records
	x := newExModel(e)
	x.w, x.h = 120, 40
	x.Update(tea.KeyPressMsg{Code: tea.KeyDown})
	_, cmd := x.Update(tea.KeyPressMsg{Code: tea.KeyEnter})
	_, _, i := x.runs()
	if runs[i].HasJ && (cmd == nil || x.open != runs[i].JSONL) {
		t.Errorf("enter: open %q", x.open)
	}
	t.Logf("%d runs in %s\n%s", len(runs), dir, txt)
}
