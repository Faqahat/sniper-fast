package ui

import (
	"compress/gzip"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

// r40f: AMS run 40 trimmed to the Filters table's records (internal/core/testdata/filters); its end, 10-31 01:30 PKT
const r40fNow = 1793392200.0

var r40fSeed = filepath.Join("..", "core", "testdata", "filters", "gcr_seed.json")

func r40fCtx(t testing.TB, seed string) *core.Ctx {
	f, err := os.Open(filepath.Join("..", "core", "testdata", "filters", "dip_ams_r40f.jsonl.gz"))
	if err != nil {
		t.Skip("no fixture")
	}
	defer f.Close()
	zr, err := gzip.NewReader(f)
	if err != nil {
		t.Fatal(err)
	}
	p := filepath.Join(t.TempDir(), "dip_ams_r40f.jsonl")
	out, _ := os.Create(p)
	if _, err := io.Copy(out, zr); err != nil {
		t.Fatal(err)
	}
	out.Close()
	ctx := loadCtx(t, p, r40fNow)
	ctx.GcrSeed = seed
	return ctx
}

// TestGoldenFilters: the Filters tab on r40f at 4 sizes (testdata/golden/r40f_*; -update rewrites them).
func TestGoldenFilters(t *testing.T) {
	ctx := r40fCtx(t, r40fSeed)
	o := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1}
	for _, sz := range [][2]int{{200, 45}, {120, 40}, {80, 30}, {50, 30}} {
		name := fmt.Sprintf("r40f_%dx%d_12-filters.txt", sz[0], sz[1])
		got := RenderScreen(ctx, o, sz[0], sz[1], 7, "", false)
		lines := strings.Split(strings.TrimSuffix(got, "\n"), "\n")
		if len(lines) != sz[1] {
			t.Errorf("%s: %d lines", name, len(lines))
		}
		for i, l := range lines {
			if w := ansi.StringWidth(l); w > sz[0] {
				t.Errorf("%s line %d: %d cells", name, i+1, w)
			}
		}
		if !strings.Contains(got, "FILTERS") || !strings.Contains(got, "SKIPPED / BLOCKED") || !strings.Contains(got, "+2.196") || (sz[0] >= 80 && !strings.Contains(got, "+1.277")) { // the calibrated net; the raw paper net where it fits
			t.Errorf("%s: the table is missing:\n%s", name, got)
		}
		fp := filepath.Join("testdata", "golden", name)
		if *update {
			os.WriteFile(fp, []byte(got), 0o644)
			continue
		}
		want, err := os.ReadFile(fp)
		if err != nil {
			t.Errorf("%s: no golden file (run with -update)", name)
			continue
		}
		if string(want) != got {
			t.Errorf("%s differs from the golden screen:\n%s", name, firstDiff(string(want), got))
		}
	}
}

// TestFiltersKeys: the tab's keys (f cycles all / LIVE / LOG / each filter, n the no-fill rows, o / O sort, enter a LOG
// item's trade, c copy) at many sizes: no panic, the frame fills the terminal, the list follows the choices.
func TestFiltersKeys(t *testing.T) {
	ctx := r40fCtx(t, "none")
	o := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1, Strict: true}
	m := New(ctx, o)
	m.Init()
	drive(m, tea.WindowSizeMsg{Width: 120, Height: 40})
	drive(m, keyMsg("8"))
	if m.tab != 7 {
		t.Fatalf("8 -> tab %d", m.tab)
	}
	drive(m, keyMsg("v")) // the shadow-window rows are hidden by default
	n0 := len(m.fltRows)
	drive(m, keyMsg("n"))
	if len(m.fltRows) <= n0 {
		t.Errorf("n: %d rows, before %d", len(m.fltRows), n0)
	}
	drive(m, keyMsg("n"))
	drive(m, keyMsg("f")) // LIVE
	for _, it := range m.fltRows {
		if !it.Live {
			t.Fatal("f LIVE shows a LOG item")
		}
	}
	drive(m, keyMsg("f")) // LOG
	if len(m.fltRows) == 0 || m.fltRows[0].Live {
		t.Fatal("f LOG")
	}
	drive(m, keyMsg("enter"))
	if m.detail == nil || m.detail.Mint != m.fltRows[0].Mint {
		t.Fatal("enter on a LOG item: no trade details")
	}
	drive(m, keyMsg("esc"))
	if m.tab != 7 || m.detail != nil {
		t.Fatal("esc: back to Filters")
	}
	for i := 0; i < len(fltSortKeys); i++ { // every sort column, both orders
		drive(m, keyMsg("o"))
		drive(m, keyMsg("O"))
		drive(m, keyMsg("O"))
	}
	if m.fltSort != 0 {
		t.Errorf("o cycle: sort %d", m.fltSort)
	}
	for i := 0; i < 20; i++ {
		drive(m, keyMsg("f"))
	}
	keys := []string{"8", "f", "n", "down", "down", "end", "home", "pgdown", "o", "O", "c", "enter", "esc", "f", "n", "up", "o", "o", "o"}
	for _, sz := range [][2]int{{200, 45}, {36, 10}, {50, 30}, {63, 20}, {64, 20}, {80, 24}, {99, 30}, {100, 30}, {160, 50}, {10, 5}} {
		out := drive(m, tea.WindowSizeMsg{Width: sz[0], Height: sz[1]})
		for _, k := range keys {
			out = drive(m, keyMsg(k))
			if sz[0] >= 36 && sz[1] >= 10 {
				if n := strings.Count(out, "\n") + 1; n != sz[1] {
					t.Fatalf("%dx%d after %q: %d lines", sz[0], sz[1], k, n)
				}
				for i, l := range strings.Split(out, "\n") {
					if w := ansi.StringWidth(l); w > sz[0] {
						t.Fatalf("%dx%d after %q line %d: %d cells", sz[0], sz[1], k, i+1, w)
					}
				}
			}
		}
		drive(m, tea.MouseWheelMsg(tea.Mouse{X: 3, Y: 20, Button: tea.MouseWheelDown}))
		drive(m, tea.MouseClickMsg(tea.Mouse{X: 5, Y: m.fltRowY + 1, Button: tea.MouseLeft}))
	}
	if m.uiErrs != 0 {
		t.Fatalf("UI errors: %s", m.uiErr)
	}
}

// fixtureSmall: a hand-made run (the same shape as core's smallFixture): 4 skipped triggers (one twice), 3 real fills:
// M1 flagged by safe sell timer + group risk + holder clock, M2 by the landing guard, M3 by nothing.
func fixtureSmall(t testing.TB) string {
	recs := []string{
		`{"ev":"presend_arm","sig":"s1","w":1}`, `{"ev":"presend_arm","sig":"s2","w":2}`,
		`{"ev":"presend_fill","row":"c","w":1,"entry":{"sol_in":1000000000}}`, `{"ev":"presend_fill","row":"c","w":2,"entry":{"sol_in":1000000000}}`,
		`{"ev":"presend_exit","row":"c","w":1,"net_cheap":0.5}`, `{"ev":"presend_exit","row":"c","w":2,"net_cheap":-0.2}`,
		`{"ev":"presend_live_skip","why":"quiet","trig":{"sig":"s1","mint":"MA","t":1000}}`,
		`{"ev":"presend_live_skip","why":"create_slot","trig":{"sig":"s1","mint":"MA","t":1000}}`,
		`{"ev":"presend_live_skip","why":"young_age","trig":{"sig":"s2","mint":"MB","t":2000}}`,
	}
	h := `{"w":"AAAAAAAAbbbb","pct":7.5,"n":6,"h3":0.9,"risk":6,"hz3":0.91},{"w":"CCCCCCCCdddd","pct":3.6,"n":6,"h3":0.1,"risk":6,"hz3":0.5}`
	anns := []string{
		`{"st_block":true,"grp_block":true,"grp_pct":11.1,"holders":[` + h + `],"guard":{"block":false,"pct":0,"set":[]}}`,
		`{"st_block":false,"grp_block":false,"holders":[],"guard":{"block":true,"pct":15.5,"set":[{"w":"EEEEEEEEffff","sign_pct":15.5,"land_pct":15.5}]}}`,
		`{"st_block":false,"grp_block":false,"holders":[],"guard":{"block":false,"pct":0,"set":[]}}`,
	}
	pnl := []string{"-300000000", "100000000", "200000000"}
	for i := 0; i < 3; i++ {
		w, m := fmt.Sprint(10+i), []string{"M1", "M2", "M3"}[i]
		recs = append(recs,
			`{"ev":"presend_live_arm","w":`+w+`,"mint":"`+m+`","kind":"t2","spend":500000000,"trig":{"sig":"x`+w+`","mint":"`+m+`","t":1`+w+`}}`,
			`{"ev":"presend_live_fill","w":`+w+`,"mint":"`+m+`","t":`+fmt.Sprint(20000+i)+`,"ann":`+anns[i]+`}`,
			`{"ev":"presend_live_realized","w":`+w+`,"mint":"`+m+`","pnl":`+pnl[i]+`}`)
	}
	p := filepath.Join(t.TempDir(), "dip_ams_r99.jsonl")
	if err := os.WriteFile(p, []byte(strings.Join(recs, "\n")+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

// TestTradesFlagDot: a trade flagged by 3 rules gets the dot and x lists all 3 with their numbers; an unflagged one has
// neither; the details say it too; --ascii uses "*".
func TestTradesFlagDot(t *testing.T) {
	ctx := loadCtx(t, fixtureSmall(t), 1793392200.0)
	ctx.GcrSeed = "none"
	for _, ascii := range []bool{false, true} {
		o := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1, Strict: true, ASCII: ascii}
		m := New(ctx, o)
		m.Init()
		drive(m, tea.WindowSizeMsg{Width: 160, Height: 40})
		out := drive(m, keyMsg("4"))
		dot := map[bool]string{false: "\u25cf", true: "*"}[ascii]
		lines := strings.Split(ansi.Strip(out), "\n")
		got := map[string]bool{}
		for _, l := range lines {
			for _, mt := range []string{"M1", "M2", "M3"} {
				if strings.Contains(l, mt) && !strings.Contains(l, "mint") {
					got[mt] = strings.Contains(l, dot)
				}
			}
		}
		if len(got) != 3 || !got["M1"] || !got["M2"] || got["M3"] {
			t.Fatalf("ascii=%v dots %v (want M1 M2 yes, M3 no):\n%s", ascii, got, out)
		}
		// select M1 (newest first: sort by mint is not needed: find it) and press x
		sel := -1
		for i, tr := range m.tradeRows {
			if tr.Mint == "M1" {
				sel = i
			}
		}
		if sel < 0 {
			t.Fatal("no M1 trade")
		}
		for i := 0; i < sel; i++ {
			drive(m, keyMsg("down"))
		}
		out = drive(m, keyMsg("x"))
		for _, w := range []string{"safe sell timer (holder AAAAAAAA 7.5%, hz3 0.91)", "group risk (11.1% = AAAAAAAA 7.5% + CCCCCCCC 3.6%)", "holder clock (holder AAAAAAAA 7.5%, h3 0.90)"} {
			if !strings.Contains(strings.Join(strings.Fields(ansi.Strip(out)), " "), w) {
				t.Errorf("ascii=%v x panel misses %q:\n%s", ascii, w, out)
			}
		}
		for i, l := range strings.Split(out, "\n") {
			if w := ansi.StringWidth(l); w > 160 {
				t.Errorf("line %d: %d cells", i+1, w)
			}
		}
		// an unflagged trade
		for i, tr := range m.tradeRows {
			if tr.Mint == "M3" {
				for m.tradeSel != i {
					drive(m, keyMsg(map[bool]string{true: "down", false: "up"}[m.tradeSel < i]))
				}
			}
		}
		out = drive(m, keyMsg("x"))
		out = drive(m, keyMsg("x"))
		if !strings.Contains(out, "no filter would have blocked this trade") {
			t.Errorf("M3 x panel:\n%s", out)
		}
		for _, sz := range [][2]int{{36, 12}, {50, 30}, {64, 20}, {70, 20}, {80, 24}, {100, 30}, {200, 45}} { // phones: no overflow
			out := drive(m, tea.WindowSizeMsg{Width: sz[0], Height: sz[1]})
			for _, k := range []string{"x", "down", "x", "up"} {
				out = drive(m, keyMsg(k))
				for i, l := range strings.Split(out, "\n") {
					if w := ansi.StringWidth(l); w > sz[0] {
						t.Fatalf("%dx%d after %q line %d: %d cells", sz[0], sz[1], k, i+1, w)
					}
				}
			}
		}
	}
}

// TestFiltersShadowToggle: the shadow-window rows are hidden by default (v shows them, with the count of hidden rows in
// the header), a LIVE filter picked with f reveals its rows, and the overview table is the same either way.
func TestFiltersShadowToggle(t *testing.T) {
	ctx := loadCtx(t, fixtureSmall(t), 1793392200.0)
	ctx.GcrSeed = "none"
	o := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1, Strict: true}
	m := New(ctx, o)
	m.Init()
	drive(m, tea.WindowSizeMsg{Width: 160, Height: 50})
	out := drive(m, keyMsg("8"))
	table := func(s string) string { // the lines of the overview table (up to the skip list)
		return strings.Split(s, "SKIPPED / BLOCKED")[0]
	}
	t0 := table(out)
	if len(m.fltRows) != 3 { // default: only the 3 LOG items... (2 flagged fills + none else) -> M1, M2 only
		for _, it := range m.fltRows {
			if it.Live {
				t.Fatalf("default view shows a shadow row: %+v", it)
			}
		}
	}
	for _, it := range m.fltRows {
		if it.Live {
			t.Fatal("default shows shadow rows")
		}
	}
	nLog := len(m.fltRows)
	if !strings.Contains(out, "+3 shadow (v)") { // 3 skip entries (s1 twice)
		t.Errorf("no hidden-count hint:\n%s", out)
	}
	out = drive(m, keyMsg("v"))
	if len(m.fltRows) <= nLog || !strings.Contains(out, "with shadow (v)") {
		t.Errorf("v: %d rows, before %d", len(m.fltRows), nLog)
	}
	if table(out) != t0 {
		t.Errorf("the overview table changed with the toggle:\n%s\nvs\n%s", t0, table(out))
	}
	drive(m, keyMsg("v"))
	if len(m.fltRows) != nLog {
		t.Errorf("v off: %d rows, want %d", len(m.fltRows), nLog)
	}
	out = drive(m, keyMsg("f")) // LIVE: reveals the shadow rows without the toggle
	live := 0
	for _, it := range m.fltRows {
		if it.Live {
			live++
		}
	}
	if live != 3 || m.fltShadow {
		t.Errorf("f LIVE: %d live rows (toggle %v)", live, m.fltShadow)
	}
	if table(out) != t0 {
		t.Error("the overview table changed with f")
	}
}

// TestFiltersVerdicts: the table leads with the FILTERS-3 verdicts: LIVE-group rows (KEEP / LIVE new / LIVE dip32) before
// LOG ones, by net saved within a group; the DISMISSED filters folded into one line that d expands (no overflow either
// way); every verdict key is a filter the engine reports.
func TestFiltersVerdicts(t *testing.T) {
	ctx := r40fCtx(t, r40fSeed)
	o := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1, Strict: true}
	m := New(ctx, o)
	m.Init()
	drive(m, tea.WindowSizeMsg{Width: 200, Height: 45})
	out := ansi.Strip(drive(m, keyMsg("8")))
	table := strings.Split(out, "SKIPPED / BLOCKED")[0]
	pos := func(s string) int {
		i := strings.Index(table, s)
		if i < 0 {
			t.Fatalf("no %q in:\n%s", s, table)
		}
		return i
	}
	if !(pos("create-slot skip") < pos("age-1 skip") && pos("age-1 skip") < pos("QUIET") && pos("QUIET") < pos("bad creator") &&
		pos("bad creator") < pos("group risk") && pos("group risk") < pos("3 DISMISSED")) {
		t.Errorf("row order:\n%s", table)
	}
	for _, s := range []string{"safe sell timer", "holder clock (approx)", "landing guard"} {
		if strings.Contains(table, s+" ") && !strings.Contains(table, "DISMISSED  d show") {
			t.Errorf("%s shown while folded", s)
		}
	}
	if strings.Contains(table, "LOG  safe sell timer") {
		t.Errorf("dismissed rows shown by default:\n%s", table)
	}
	out = ansi.Strip(drive(m, keyMsg("d")))
	table = strings.Split(out, "SKIPPED / BLOCKED")[0]
	if !strings.Contains(table, "LOG  safe sell timer") || !strings.Contains(table, "DISMISSED  d hide") || !strings.Contains(table, "within group risk") {
		t.Errorf("d: the dismissed rows are not shown:\n%s", table)
	}
	for _, sz := range [][2]int{{200, 45}, {120, 40}, {100, 30}, {99, 30}, {80, 30}, {76, 24}, {75, 24}, {50, 30}, {49, 20}, {40, 20}, {36, 12}} {
		for _, k := range []string{"d", "d"} {
			drive(m, tea.WindowSizeMsg{Width: sz[0], Height: sz[1]})
			out := drive(m, keyMsg(k))
			for i, l := range strings.Split(out, "\n") {
				if w := ansi.StringWidth(l); w > sz[0] {
					t.Fatalf("%dx%d (dismissed %v) line %d: %d cells", sz[0], sz[1], m.fltDism, i+1, w)
				}
			}
		}
	}
	known := map[string]bool{"quiet": true, "create_slot": true, "young_age": true, "lone_whale": true, "breaker": true, "cr_loss": true,
		"cr_unfollowed": true, "gcr": true, "st": true, "ctx85": true, "grp": true, "hc": true, "guard": true, "q3a": true, "fresh": true, "quiet3_a": true, "crlog": true, "eqgrp": true, "fam": true, "fpnb": true, "blocklist": true, "skip2": true, "fpnb_live": true,
		// dip37
		"wh_loss": true, "rearm_wh_loss": true, "holder_loss": true, "m2_unseen": true, "wh_other": true, "wh_logmode": true, "hl_logmode": true, "h2": true, "skip2_live": true}
	for k, v := range fltVerdicts {
		if !known[k] || v.label == "" || v.why == "" || len(v.label) > 10 {
			t.Errorf("verdict %q: %+v", k, v)
		}
	}
	if m.uiErrs != 0 {
		t.Fatalf("UI errors: %s", m.uiErr)
	}
}

// TestOverviewFlagDot: the overview's last trades carry the same yellow dot as the Trades tab (M1, M2 flagged, M3 not).
func TestOverviewFlagDot(t *testing.T) {
	ctx := loadCtx(t, fixtureSmall(t), 1793392200.0)
	ctx.GcrSeed = "none"
	for _, sz := range [][2]int{{200, 45}, {160, 50}, {120, 40}, {80, 30}} {
		o := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1, Strict: true}
		m := New(ctx, o)
		m.Init()
		out := drive(m, tea.WindowSizeMsg{Width: sz[0], Height: sz[1]})
		out = drive(m, keyMsg("1"))
		got := map[string]bool{}
		for _, l := range strings.Split(ansi.Strip(out), "\n") {
			for _, mt := range []string{"M1", "M2", "M3"} {
				if strings.Contains(l, " "+mt+" ") || strings.HasSuffix(strings.TrimRight(l, " │|"), " "+mt) {
					got[mt] = strings.Contains(l, "●")
				}
			}
		}
		if len(got) != 3 || !got["M1"] || !got["M2"] || got["M3"] {
			t.Errorf("%dx%d overview dots %v (want M1 M2 yes, M3 no):\n%s", sz[0], sz[1], got, out)
		}
	}
}

// fixtureMove: four skipped triggers on shadow windows (core's moveFixture): MA filled with a "move" (+35/-8%), MB filled
// without one (a run before 11-03: "–"), ME never filled with a "move" (no dip, +4/0%), MF never filled, no trades;
// one real fill M1 (LOG, safe sell timer). q3live: the run_start says QUIET3-A runs live.
func fixtureMove(t testing.TB, q3live bool) string {
	recs := []string{
		`{"ev":"presend_arm","sig":"s1","w":1}`, `{"ev":"presend_arm","sig":"s2","w":2}`, `{"ev":"presend_arm","sig":"s5","w":5}`, `{"ev":"presend_arm","sig":"s6","w":6}`,
		`{"ev":"presend_fill","row":"c","w":1,"entry":{"sol_in":1000000000}}`, `{"ev":"presend_fill","row":"c","w":2,"entry":{"sol_in":1000000000}}`,
		`{"ev":"presend_exit","row":"c","w":1,"net_cheap":0.5}`, `{"ev":"presend_exit","row":"c","w":2,"net_cheap":-0.2}`,
		`{"ev":"presend_disarm","w":1,"why":"expired","move":{"max_pct":35.4,"min_pct":-7.6,"n":12}}`,
		`{"ev":"presend_disarm","w":2,"why":"expired"}`,
		`{"ev":"presend_disarm","w":5,"why":"expired","move":{"max_pct":4.2,"min_pct":-0.4,"n":3}}`,
		`{"ev":"presend_disarm","w":6,"why":"expired","move":{"max_pct":0,"min_pct":0,"n":0}}`,
		`{"ev":"presend_live_skip","why":"quiet","trig":{"sig":"s1","mint":"MA","t":1793390000000000000}}`,
		`{"ev":"presend_live_skip","why":"young_age","trig":{"sig":"s2","mint":"MB","t":1793390100000000000}}`,
		`{"ev":"presend_live_skip","why":"create_slot","trig":{"sig":"s5","mint":"ME","t":1793390200000000000}}`,
		`{"ev":"presend_live_skip","why":"quiet","trig":{"sig":"s6","mint":"MF","t":1793390300000000000}}`,
		`{"ev":"presend_live_arm","w":10,"mint":"M1","kind":"t2","spend":500000000,"f3":{"q3a":false,"n_120s":40,"wh_dumps":5,"fresh":10,"fresh_n":2},"trig":{"sig":"x10","mint":"M1","t":1793390400000000000}}`,
		`{"ev":"presend_live_fill","w":10,"mint":"M1","t":1793390400000000000,"ann":{"st_block":true,"holders":[]}}`,
		`{"ev":"presend_live_realized","w":10,"mint":"M1","pnl":-300000000}`,
	}
	if q3live {
		recs = append([]string{`{"ev":"run_start","t":1793389000000000000,"presend_live":{"spend":500000000,"quiet3a":true}}`}, recs...)
	}
	p := filepath.Join(t.TempDir(), "dip_ams_r98.jsonl")
	if err := os.WriteFile(p, []byte(strings.Join(recs, "\n")+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

// TestFiltersNoDipMove: a LIVE skip whose shadow window never filled shows result "no dip" and SOL 0.000 (hidden until
// n, like before); the LIVE rows' move column ("+35/-8%", "–" without a "move"), blank on LOG rows, dropped on narrow
// screens and when the list has no LIVE row; QUIET3-A live hides the "QUIET3-A (log)" table row.
func TestFiltersNoDipMove(t *testing.T) {
	ctx := loadCtx(t, fixtureMove(t, false), 1793392200.0)
	ctx.GcrSeed = "none"
	o := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1, Strict: true}
	m := New(ctx, o)
	m.Init()
	drive(m, tea.WindowSizeMsg{Width: 160, Height: 50})
	out := ansi.Strip(drive(m, keyMsg("8")))
	list := func(s string) string { return strings.Split(s, "SKIPPED / BLOCKED")[1] }
	if strings.Contains(list(out), " move") { // LOG rows only: no move column
		t.Errorf("move column without LIVE rows:\n%s", list(out))
	}
	if !strings.Contains(out, "QUIET3-A (log)") {
		t.Errorf("QUIET3-A not live: the log row is missing:\n%s", out)
	}
	out = ansi.Strip(drive(m, keyMsg("v")))
	if !strings.Contains(out, "+2 no dip (n)") || strings.Contains(list(out), "ME ") {
		t.Errorf("v: the no-dip rows are not hidden behind n:\n%s", list(out))
	}
	out = ansi.Strip(drive(m, keyMsg("n")))
	line := func(mint string) string {
		for _, l := range strings.Split(list(out), "\n") {
			if strings.Contains(l, " "+mint+" ") {
				return strings.Join(strings.Fields(l), " ")
			}
		}
		t.Fatalf("no %s row:\n%s", mint, list(out))
		return ""
	}
	if !strings.Contains(list(out), "move") {
		t.Errorf("no move column:\n%s", list(out))
	}
	for mint, want := range map[string]string{"MA": "WIN +0.2500 +35/-8%", "MB": "LOSE -0.1000 " + core.G.Dash, "ME": "no dip 0.000 +4/0%",
		"MF": "no dip 0.000 0 trades", "M1": "LOSE -0.3000 real fill"} {
		if l := line(mint); !strings.Contains(l, want) {
			t.Errorf("%s: %q, want %q", mint, l, want)
		}
	}
	if strings.Contains(list(out), "no fi") {
		t.Errorf("still says no fill:\n%s", list(out))
	}
	for _, sz := range [][2]int{{200, 45}, {120, 40}, {90, 30}, {89, 30}, {80, 30}, {76, 24}, {75, 24}, {66, 24}, {50, 30}, {36, 12}} {
		out := drive(m, tea.WindowSizeMsg{Width: sz[0], Height: sz[1]})
		for i, l := range strings.Split(out, "\n") {
			if w := ansi.StringWidth(l); w > sz[0] {
				t.Fatalf("%dx%d line %d: %d cells", sz[0], sz[1], i+1, w)
			}
		}
		has := strings.Contains(list(ansi.Strip(out)), " move")
		if want := sz[0] >= 76; has != want && sz[1] > 12 {
			t.Errorf("%dx%d: move shown %v, want %v:\n%s", sz[0], sz[1], has, want, ansi.Strip(out))
		}
	}
	// QUIET3-A live: the log row is gone
	ctx = loadCtx(t, fixtureMove(t, true), 1793392200.0)
	ctx.GcrSeed = "none"
	m = New(ctx, o)
	m.Init()
	drive(m, tea.WindowSizeMsg{Width: 160, Height: 50})
	out = ansi.Strip(drive(m, keyMsg("8")))
	if strings.Contains(out, "QUIET3-A (log)") || !strings.Contains(out, "fresh holders") {
		t.Errorf("QUIET3-A live: the log row is still shown:\n%s", out)
	}
	if m.uiErrs != 0 {
		t.Fatalf("UI errors: %s", m.uiErr)
	}
}
