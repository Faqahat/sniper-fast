package ui

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

var update = flag.Bool("update", false, "rewrite the golden screens")

var dataDir = func() string {
	if d := os.Getenv("DIPMON_DATA"); d != "" {
		return d
	}
	return "/home/moiz/sniper-data/runs"
}()

var r27 = filepath.Join(dataDir, "ams/runs/dip_ams_r27.jsonl")

// r27 ended at 5:36:57 PM PKT; the screens are rendered at that instant
const r27End = 1793104617.217364241

func loadCtx(t testing.TB, path string, now float64) *core.Ctx {
	if _, err := os.Stat(path); err != nil {
		t.Skip("no local data: " + path)
	}
	src := core.NewSource(path, "", 0, 3000)
	src.LoadAll(core.LoadChunk, 0, nil)
	return &core.Ctx{Src: src, Engine: core.NewEngine(path, false), Price: core.NewPrice(187.42, false), Sys: core.NewSysInfo("/", 2),
		FixedNow: now}
}

var sizes = [][2]int{{200, 35}, {160, 50}, {120, 40}, {80, 24}, {50, 30}}

var pages = []struct {
	name string
	tab  int
	page string
}{{"01-overview", 0, ""}, {"02-presend", 1, ""}, {"03-regular", 2, ""}, {"04-trades", 3, ""}, {"05-health", 4, ""}, {"06-log", 5, ""},
	{"07-config", 6, ""}, {"08-help", 0, "help"}, {"09-detail", 3, "detail"}, {"10-splash", 0, "splash"}, {"11-today", 0, "today"}}

var r28 = filepath.Join(func() string {
	if d := os.Getenv("DIPMON_TUI_DATA"); d != "" {
		return d
	}
	return "/home/moiz/sniper-data/tui/runs"
}(), "ams/runs/dip_ams_r28.jsonl")

// r28 ended at 10:03:02 PM PKT
const r28End = 1793120582.446567003

// TestGoldenLatency: r28 (the run with the latency the owner measured): the Pre-send tab (its LATENCY), the Trades
// tab (d→land / s→seen / blk) and a fill's details at the 5 sizes, compared with testdata/golden/r28_*.
func TestGoldenLatency(t *testing.T) {
	ctx := loadCtx(t, r28, r28End)
	o := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1}
	dir := filepath.Join("testdata", "golden")
	for _, sz := range sizes {
		for _, p := range []struct {
			name string
			tab  int
			page string
		}{{"02-presend", 1, ""}, {"04-trades", 3, ""}, {"09-detail", 3, "detail"}} {
			name := fmt.Sprintf("r28_%dx%d_%s.txt", sz[0], sz[1], p.name)
			got := RenderScreen(ctx, o, sz[0], sz[1], p.tab, p.page, false)
			lines := strings.Split(strings.TrimSuffix(got, "\n"), "\n")
			if len(lines) != sz[1] {
				t.Errorf("%s: %d lines, want %d", name, len(lines), sz[1])
			}
			for i, l := range lines {
				if w := ansi.StringWidth(l); w > sz[0] {
					t.Errorf("%s line %d: %d cells > %d", name, i+1, w, sz[0])
				}
			}
			fp := filepath.Join(dir, name)
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
	// the measured medians on the Pre-send tab
	got := RenderScreen(ctx, o, 200, 35, 1, "", false)
	if !strings.Contains(got, "fills      dump→land p10 <1 · p50 34") || !strings.Contains(got, "bounced    dump→land p10 85 · p50 307") {
		t.Errorf("r28 Pre-send: the fills' 34 ms / the bounced tries' 307 ms after the dump are not shown")
	}
}

// TestASCIIAndNoColor: with --ascii every page at every size is plain ASCII (the line chart in '*', the frames in
// + - |), and with --no-color no escape sets a color (bold / faint / reverse only).
func TestASCIIAndNoColor(t *testing.T) {
	ctx := loadCtx(t, r27, r27End)
	asc := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1, ASCII: true}
	mono := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1, NoColor: true}
	core.SetASCII(true)
	defer core.SetASCII(false)
	for _, sz := range sizes {
		for _, p := range pages {
			got := RenderScreen(ctx, asc, sz[0], sz[1], p.tab, p.page, false)
			for i, l := range strings.Split(got, "\n") {
				for _, r := range l {
					if r >= 0x80 {
						t.Errorf("--ascii %dx%d %s line %d: %q", sz[0], sz[1], p.name, i+1, l)
						break
					}
				}
			}
		}
	}
	core.SetASCII(false)
	for _, p := range pages {
		got := RenderScreen(ctx, mono, 120, 40, p.tab, p.page, true)
		if strings.Contains(got, "38;2;") || strings.Contains(got, "48;2;") || strings.Contains(got, "38;5;") {
			t.Errorf("--no-color %s: a color escape", p.name)
		}
	}
}

// TestGoldenScreens: every tab (+ help, a trade's details, the splash, the today card) at the 5 sizes, r27, compared
// with testdata/golden (go test -run Golden -update rewrites them).
func TestGoldenScreens(t *testing.T) {
	ctx := loadCtx(t, r27, r27End)
	o := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1}
	dir := filepath.Join("testdata", "golden")
	if *update {
		os.MkdirAll(dir, 0o755)
	}
	for _, sz := range sizes {
		for _, p := range pages {
			name := fmt.Sprintf("%dx%d_%s.txt", sz[0], sz[1], p.name)
			got := RenderScreen(ctx, o, sz[0], sz[1], p.tab, p.page, false)
			lines := strings.Split(strings.TrimSuffix(got, "\n"), "\n")
			if len(lines) != sz[1] {
				t.Errorf("%s: %d lines, want %d", name, len(lines), sz[1])
			}
			for i, l := range lines {
				if w := ansi.StringWidth(l); w > sz[0] {
					t.Errorf("%s line %d: %d cells > %d", name, i+1, w, sz[0])
				}
			}
			fp := filepath.Join(dir, name)
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
}

func firstDiff(a, b string) string {
	la, lb := strings.Split(a, "\n"), strings.Split(b, "\n")
	for i := 0; i < max(len(la), len(lb)); i++ {
		var x, y string
		if i < len(la) {
			x = la[i]
		}
		if i < len(lb) {
			y = lb[i]
		}
		if x != y {
			return fmt.Sprintf("line %d\n  want: %s\n  got:  %s", i+1, x, y)
		}
	}
	return ""
}

// drive sends a message through Update and renders a frame (what the program does).
func drive(m *Model, msg tea.Msg) string {
	m.Update(msg)
	return m.View().Content
}

// TestResizeAndKeys: the live model through many sizes (down to 1x1) and every key: no panic, the frame always
// exactly fills the terminal.
func TestResizeAndKeys(t *testing.T) {
	ctx := loadCtx(t, r27, r27End)
	o := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1, Strict: true}
	m := New(ctx, o)
	m.Init()
	keys := []string{"1", "2", "3", "4", "5", "6", "7", "tab", "shift+tab", "u", "u", "s", "s", "S", "a", "a", "m", "m", "p", "p",
		"?", "x", "4", "down", "down", "enter", "esc", "f", "f", "/", "3", "N", "enter", "esc", "6", "f", "w", "end", "home", "up",
		"pgdown", "pgup", "+", "-", "r", "7", "G", "g", "4", "o", "o", "O", "c", "M", "M", "enter", "c", "esc", "o", "o", "o", "o", "o", "o", "o",
		"o", "o", "o", "o", "o", "o", "o", "u", "u"}
	szs := [][2]int{{200, 35}, {1, 1}, {10, 5}, {35, 9}, {36, 10}, {50, 30}, {80, 24}, {120, 40}, {160, 50}, {300, 100}, {61, 29},
		{69, 30}, {70, 40}, {99, 40}, {100, 40}, {119, 41}, {179, 35}, {181, 39}}
	for _, sz := range szs {
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
		// the mouse: tab clicks, wheel, a trade row
		for x := 0; x < sz[0]; x += 7 {
			drive(m, tea.MouseClickMsg(tea.Mouse{X: x, Y: m.tabY, Button: tea.MouseLeft}))
		}
		drive(m, tea.MouseWheelMsg(tea.Mouse{X: 3, Y: 8, Button: tea.MouseWheelDown}))
		drive(m, tea.MouseWheelMsg(tea.Mouse{X: 3, Y: 8, Button: tea.MouseWheelUp}))
		drive(m, keyMsg("4"))
		drive(m, tea.MouseClickMsg(tea.Mouse{X: 5, Y: m.tradeRowY + 1, Button: tea.MouseLeft}))
		drive(m, tea.MouseClickMsg(tea.Mouse{X: 5, Y: m.tradeRowY + 1, Button: tea.MouseLeft}))
		drive(m, keyMsg("esc"))
	}
	if m.uiErrs != 0 {
		t.Fatalf("UI errors: %s", m.uiErr)
	}
}

func keyMsg(k string) tea.KeyPressMsg {
	switch k {
	case "tab":
		return tea.KeyPressMsg{Code: tea.KeyTab}
	case "shift+tab":
		return tea.KeyPressMsg{Code: tea.KeyTab, Mod: tea.ModShift}
	case "enter":
		return tea.KeyPressMsg{Code: tea.KeyEnter}
	case "esc":
		return tea.KeyPressMsg{Code: tea.KeyEscape}
	case "down":
		return tea.KeyPressMsg{Code: tea.KeyDown}
	case "up":
		return tea.KeyPressMsg{Code: tea.KeyUp}
	case "pgdown":
		return tea.KeyPressMsg{Code: tea.KeyPgDown}
	case "pgup":
		return tea.KeyPressMsg{Code: tea.KeyPgUp}
	case "home":
		return tea.KeyPressMsg{Code: tea.KeyHome}
	case "end":
		return tea.KeyPressMsg{Code: tea.KeyEnd}
	}
	r := []rune(k)[0]
	return tea.KeyPressMsg{Code: r, Text: k}
}

// copyLines writes the first n lines of src to dst (n < 0: all), returning the rest.
func splitFile(t *testing.T, src string, frac float64) ([]string, []string) {
	f, err := os.Open(src)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	var all []string
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 16<<20)
	for sc.Scan() {
		all = append(all, sc.Text())
	}
	k := int(float64(len(all)) * frac)
	return all[:k], all[k:]
}

// TestLiveEventsAnimationsAndBell: a run followed live: trades closing after the load highlight their rows, roll the
// hero, pulse the chart and ring the bell at most once per 2 s (a burst merged); trades read in the load never ring.
func TestLiveEventsAnimationsAndBell(t *testing.T) {
	if _, err := os.Stat(r27); err != nil {
		t.Skip("no data")
	}
	d := t.TempDir()
	jl, jr := splitFile(t, r27, 0.5)
	ll, lr := splitFile(t, strings.TrimSuffix(r27, ".jsonl")+".log", 0.5)
	jp, lp := filepath.Join(d, "dip_ams_r27.jsonl"), filepath.Join(d, "dip_ams_r27.log")
	os.WriteFile(jp, []byte(strings.Join(jl, "\n")+"\n"), 0o644)
	os.WriteFile(lp, []byte(strings.Join(ll, "\n")+"\n"), 0o644)
	src := core.NewSource(jp, "", 0, 3000)
	ctx := &core.Ctx{Src: src, Engine: core.NewEngine(jp, false), Price: core.NewPrice(187.42, false), Sys: core.NewSysInfo("/", 2), AssumeRunning: true}
	bl := filepath.Join(d, "bells.log")
	m := New(ctx, Options{Sound: "all", Version: "test", Interval: 1, LoadDuty: 0, BellLog: bl})
	clock := time.Unix(1793100000, 0)
	m.nowFn = func() time.Time { return clock }
	m.Init()
	m.w, m.h = 200, 35
	for i := 0; i < 1000 && m.loading; i++ {
		m.Update(loadMsg{})
	}
	if m.loading {
		t.Fatal("load did not finish")
	}
	loadedEvents := src.Model.EventSeq
	if m.bells != 0 {
		t.Fatal("rang during the load")
	}
	// append the rest in 20 pieces, one data tick each, 0.5 s apart
	const pieces = 20
	for p := 0; p < pieces; p++ {
		a, b := len(jr)*p/pieces, len(jr)*(p+1)/pieces
		c, e := len(lr)*p/pieces, len(lr)*(p+1)/pieces
		appendLines(t, jp, jr[a:b])
		appendLines(t, lp, lr[c:e])
		clock = clock.Add(500 * time.Millisecond)
		m.Update(dataMsg{gen: m.dataGen})
		for i := 0; i < 5; i++ { // frames
			clock = clock.Add(time.Second / animFPS)
			m.Update(frameMsg{})
			_ = m.render(200, 35)
		}
		if p%3 == 0 {
			clock = clock.Add(2100 * time.Millisecond)
			m.Update(bellMsg{})
		}
	}
	clock = clock.Add(3 * time.Second)
	m.Update(bellMsg{})
	newEvents := src.Model.EventSeq - loadedEvents
	if newEvents == 0 {
		t.Fatal("no trade closed after the load")
	}
	m.bellLog.Close()
	raw, _ := os.ReadFile(bl)
	var covered int64
	var last float64
	i := 0
	for _, l := range strings.Split(strings.TrimSpace(string(raw)), "\n") {
		if strings.HasPrefix(l, "#") {
			continue
		}
		i++
		var ts float64
		var n int64
		fmt.Sscanf(l, "%f %d", &ts, &n)
		if i > 1 && ts-last < 1.999 {
			t.Errorf("bells %.3f s apart", ts-last)
		}
		last = ts
		covered += n
	}
	if covered != newEvents {
		t.Errorf("bells covered %d closed trades, %d closed after the load", covered, newEvents)
	}
	t.Logf("closed after the load %d, bells %d covering %d, highlights %d, followed total %d", newEvents, m.bells, covered, len(m.hl), m.view.Total)
	if m.bells == 0 || int64(m.bells) > newEvents {
		t.Errorf("%d bells for %d trades", m.bells, newEvents)
	}
	if m.toastAt.IsZero() || m.pulseAt.IsZero() || len(m.hl) == 0 && m.anim {
		t.Errorf("no animation started (toast %v pulse %v highlights %d)", m.toastAt, m.pulseAt, len(m.hl))
	}
	// the final numbers equal the finished file's
	full := loadCtx(t, r27, 0)
	vf := core.BuildView(full, -1)
	if m.view.Total != vf.Total || m.view.PS.Fills != vf.PS.Fills || m.view.Reg.Fires != vf.Reg.Fires {
		t.Errorf("followed total %d (fills %d, fires %d) != file %d (%d, %d)", m.view.Total, m.view.PS.Fills, m.view.Reg.Fires,
			vf.Total, vf.PS.Fills, vf.Reg.Fires)
	}
}

func appendLines(t *testing.T, p string, ls []string) {
	if len(ls) == 0 {
		return
	}
	f, err := os.OpenFile(p, os.O_APPEND|os.O_WRONLY, 0)
	if err != nil {
		t.Fatal(err)
	}
	f.WriteString(strings.Join(ls, "\n") + "\n")
	f.Close()
}
