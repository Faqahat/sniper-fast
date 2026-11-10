package ui

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/charmbracelet/x/ansi"
)

// TestGoldenDip43: AMS r80 (dip43d: the snipe-guard A/B, the CURVE band, the dip43 shadows; ended by the kill switch): the
// Engine tab (the dip43 panels on top), Trades (the arm column), a fill's details (its dip43 line), Filters (the registry's
// LOG rows) and Config (the dip43 start banners) at 3 sizes, against testdata/golden/r80_* (-update rewrites).
func TestGoldenDip43(t *testing.T) {
	r80 := filepath.Join(dataDir, "ams_r80/dip_ams_r80.jsonl")
	ctx := loadCtx(t, r80, 1794346253.6+600)
	o := Options{Sound: "all", Version: "test", Golden: true, Interval: 1, LoadDuty: 1}
	dir := filepath.Join("testdata", "golden")
	for _, sz := range [][2]int{{200, 60}, {120, 40}, {80, 30}} {
		for _, p := range []struct {
			name string
			tab  int
			page string
		}{{"02-presend", 1, ""}, {"04-trades", 3, ""}, {"09-detail", 3, "detail"}, {"07-config", 6, ""}, {"12-filters", 7, ""}} {
			name := fmt.Sprintf("r80_%dx%d_%s.txt", sz[0], sz[1], p.name)
			got := RenderScreen(ctx, o, sz[0], sz[1], p.tab, p.page, false)
			lines := strings.Split(strings.TrimSuffix(got, "\n"), "\n")
			if len(lines) != sz[1] {
				t.Errorf("%s: %d lines, want %d", name, len(lines), sz[1])
			}
			for i, l := range lines {
				if w := ansi.StringWidth(l); w > sz[0] {
					t.Errorf("%s line %d: %d cells", name, i+1, w)
				}
			}
			fp := filepath.Join(dir, name)
			if *update {
				os.MkdirAll(dir, 0o755)
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
	// the dip43 figures on them
	eng := RenderScreen(ctx, o, 200, 60, 1, "", false)
	for _, w := range []string{"GUARD (snipe-guard A/B)", "CURVE BAND (dip43d)", "TRUE BALANCES", "G snipe-guard   tries", "curve_deep aborts"} {
		if !strings.Contains(eng, w) {
			t.Errorf("Engine tab lacks %q", w)
		}
	}
	tr := RenderScreen(ctx, o, 200, 60, 3, "", false)
	if !strings.Contains(tr, " arm ") {
		t.Errorf("Trades: no arm column")
	}
	fl := RenderScreen(ctx, o, 200, 60, 7, "", false)
	if !strings.Contains(fl, "G-A holder floors (log)") {
		t.Errorf("Filters: no G-A row")
	}
}
