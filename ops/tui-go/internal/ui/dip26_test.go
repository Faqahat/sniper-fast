package ui

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

// r38 (AMS, 10-30): the first dip26 run (live re-arm, the helius-ps / astralane-ps A/B); a frozen read-only copy of its
// first 38 minutes (both files' mtime 1793309896), rendered as running at +10 s.
var r38 = filepath.Join(func() string {
	if d := os.Getenv("DIPMON_DIP26_DATA"); d != "" {
		return d
	}
	return "/home/moiz/sniper-data/tui/runs-dip26"
}(), "ams/runs/dip_ams_r38.jsonl")

const r38Now = 1793309906.0

// TestGoldenDip26: r38's overview / pre-send / trades / health / config / trade details at the 5 sizes
// (testdata/golden/r38_*), the dip26 figures on them, --ascii pure ASCII.
func TestGoldenDip26(t *testing.T) {
	ctx := loadCtx(t, r38, r38Now)
	ctx.AssumeRunning = true
	o := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1}
	dir := filepath.Join("testdata", "golden")
	for _, sz := range sizes {
		for _, p := range []struct {
			name string
			tab  int
			page string
		}{{"01-overview", 0, ""}, {"02-presend", 1, ""}, {"04-trades", 3, ""}, {"05-health", 4, ""}, {"07-config", 6, ""}, {"09-detail", 3, "detail"}} {
			name := fmt.Sprintf("r38_%dx%d_%s.txt", sz[0], sz[1], p.name)
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
	for _, c := range []struct {
		tab  int
		w, h int
		want []string
	}{
		{0, 200, 35, []string{"dip26", "split     T2 +0.3266  regular +0.0000", "re-arm    +0.2358  21 fills 10 W", "T2        23 fills · 13 W 57%",
			"re-arm    21 fills · 10 W 48% · +0.2358", "● A/B helius-ps / astralane-ps", "● re-arm 0.65 SOL · gap 20 · QUIET 6:2 · R5 off", " via ", " RA ",
			"astralane-ps refused 2.0% of its tries in 10 min (19 of 972)"}},
		{1, 200, 80, []string{"RESULT · T2", "RE-ARM", "SEND PATHS A/B", "caps 60/s · 40/s a path", "helius-ps     4,694    0 0.0%", "astralane-ps  4,399  296 6.3%",
			"rate_path_config 381 · paused_presend_position 156 (engine, all paths)", "no_holder 185 · age 90", "T2 tries 4,025 (+5,068 re-arm)",
			"paper      observatory 86 windows / 101 fills", "live T2      23 fills"}},
		{3, 200, 35, []string{"via", "AS ", "HL "}},
		{4, 200, 35, []string{"A/B paths  helius-ps ok · astralane-ps ok", "paper re-arm 86 windows / 101 fills"}},
		{6, 160, 90, []string{"Re-arm", "Send-path A/B", "QUIET stop 6:2", "live re-arm: after a single ≥ 6% sell"}},
	} {
		got := RenderScreen(ctx, o, c.w, c.h, c.tab, "", false)
		for _, w := range c.want {
			if !strings.Contains(got, w) {
				t.Errorf("r38 tab %d (%dx%d) lacks %q", c.tab+1, c.w, c.h, w)
			}
		}
	}
	// --ascii: pure ASCII with the dip26 lines
	core.SetASCII(true)
	defer core.SetASCII(false)
	asc := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1, ASCII: true}
	for _, sz := range sizes {
		for _, p := range []struct {
			tab  int
			page string
		}{{0, ""}, {1, ""}, {3, ""}, {4, ""}, {6, ""}, {0, "help"}} {
			for i, l := range strings.Split(RenderScreen(ctx, asc, sz[0], sz[1], p.tab, p.page, false), "\n") {
				for _, r := range l {
					if r >= 0x80 {
						t.Errorf("--ascii r38 %dx%d tab %d %s line %d: %q", sz[0], sz[1], p.tab+1, p.page, i+1, l)
						break
					}
				}
			}
		}
	}
}

// TestDip26ResizeKeysSort: r38 through many sizes, every tab and the sort keys (the via column sorts as the path; the
// type sorts PS / RA / REG apart): no panic, every frame exactly fills the terminal; the help has the dip26 notes.
func TestDip26ResizeKeysSort(t *testing.T) {
	ctx := loadCtx(t, r38, r38Now)
	ctx.AssumeRunning = true
	o := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1, Strict: true}
	m := New(ctx, o)
	m.Init()
	keys := []string{"1", "2", "end", "home", "3", "4", "o", "O", "o", "5", "6", "7", "?", "x", "4", "enter", "esc", "u", "u", "2", "pgdown", "pgdown"}
	for _, sz := range [][2]int{{200, 35}, {1, 1}, {36, 10}, {50, 30}, {70, 40}, {79, 30}, {80, 24}, {89, 30}, {90, 30}, {109, 40}, {110, 40}, {119, 41},
		{120, 40}, {124, 40}, {125, 40}, {149, 40}, {150, 40}, {160, 50}, {179, 35}, {181, 39}, {300, 100}} {
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
	}
	if m.uiErrs != 0 {
		t.Fatalf("UI errors: %s", m.uiErr)
	}
	// sorting: by type the re-arm rows sort apart; a click on "via" sorts by the path
	m2 := tradesModel(t, r38, r38Now, 200, 35)
	for ki, k := range sortKeys {
		if k == "type" {
			m2.sortCol, m2.sortAsc = ki, true
		}
	}
	tl := m2.filteredTrades()
	seen := map[string]bool{}
	last := ""
	for _, tr := range tl {
		tag := kindTag(tr)
		if tag != last && seen[tag] {
			t.Fatalf("type sort: %s rows not together", tag)
		}
		seen[tag], last = true, tag
	}
	if !seen["RA"] || !seen["PS"] {
		t.Fatalf("type sort: kinds %v", seen)
	}
	m2.sortCol, m2.sortAsc = 0, false
	m2.render(200, 35)
	for _, h := range m2.hdrX {
		if h.key == "path" {
			m2.clickHeader(h.x0)
			break
		}
	}
	if sortKeys[m2.sortCol] != "path" {
		t.Fatalf("a click on via / path sorts by %s", sortKeys[m2.sortCol])
	}
	m3 := screenModel(ctx, o, 120, 60)
	if h := m3.helpContent(92); !strings.Contains(h, "re-arm") || !strings.Contains(h, "A/B") {
		t.Fatal("help: no dip26 notes")
	}
}
