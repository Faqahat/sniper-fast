package core

import (
	"compress/gzip"
	"encoding/json"
	"io"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

// The Filters table against filters_report.py (the reference) on AMS run 40. testdata/filters:
//   dip_ams_r40f.jsonl.gz  r40 (the live copy of 10-30 20:29 UTC) trimmed by make_fixture.py to the records the table
//                          reads (one deep T2 try per window); the script gives the same rows on it as on the full file
//   ref_seed.json          ref_rows.py (filters_report.py, unchanged, its rows at full precision) with gcr_seed.json
//   ref_noseed.json        the same without a seed (the bad creator from this run's own fills)
// DIPMON_R40=path/to/r40.jsonl also checks a full run file against the script run on it (TestFiltersFullR40).

type refRow struct {
	Name    string  `json:"name"`
	Type    string  `json:"type"`
	Blocked int     `json:"blocked"`
	WinN    int     `json:"win_n"`
	WinSol  float64 `json:"win_sol"`
	LoseN   int     `json:"lose_n"`
	LoseSol float64 `json:"lose_sol"`
	Net     float64 `json:"net"`
	Note    string  `json:"note"`
}

type refRep struct {
	Positions int      `json:"positions"`
	Realized  float64  `json:"realized"`
	Rows      []refRow `json:"rows"`
	Text      string   `json:"text"`
	Unique    map[string]struct {
		Blocked int     `json:"blocked"`
		WinN    int     `json:"win_n"`
		WinSol  float64 `json:"win_sol"`
		LoseN   int     `json:"lose_n"`
		LoseSol float64 `json:"lose_sol"`
		Net     float64 `json:"net"`
	} `json:"unique"`
}

func fixtureR40(t testing.TB) string {
	src := filepath.Join("testdata", "filters", "dip_ams_r40f.jsonl.gz")
	f, err := os.Open(src)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	zr, err := gzip.NewReader(f)
	if err != nil {
		t.Fatal(err)
	}
	dst := filepath.Join(t.TempDir(), "dip_ams_r40f.jsonl")
	out, err := os.Create(dst)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := io.Copy(out, zr); err != nil {
		t.Fatal(err)
	}
	out.Close()
	return dst
}

func loadRef(t testing.TB, name string) refRep {
	b, err := os.ReadFile(filepath.Join("testdata", "filters", name))
	if err != nil {
		t.Fatal(err)
	}
	var r refRep
	if err := json.Unmarshal(b, &r); err != nil {
		t.Fatal(err)
	}
	return r
}

// filtView loads a run file (step by step, computing the report between steps: the live update path) and builds the view.
func filtView(t testing.TB, path, seed string) *View {
	src := NewSource(path, "", 0, 3000)
	for {
		n := src.Step(LoadChunk)
		_ = src.Model.Filt.Report(ResolveGcrSeed(seed)) // the report between steps (cached, recomputed as records come)
		if n == 0 && !src.Pending() {
			break
		}
	}
	src.Loaded = true
	ctx := &Ctx{Src: src, Engine: NewEngine(path, false), Price: NewPrice(100, false), Sys: NewSysInfo("/", 2), GcrSeed: seed}
	return BuildView(ctx, -1)
}

func checkFilt(t *testing.T, R *FiltReport, ref refRep) {
	t.Helper()
	const eps = 1e-9
	if R.NReal != ref.Positions || math.Abs(R.RealSum-ref.Realized) > eps {
		t.Errorf("positions %d %.9f, want %d %.9f", R.NReal, R.RealSum, ref.Positions, ref.Realized)
	}
	// the landing guard (dip30+, not in filters_report.py yet): n/a on a run that does not log it, kept apart
	var rows []FiltRow
	for _, r := range R.Rows {
		if r.Key == "guard" {
			if r.NA != !R.HasGuard || (r.NA && (r.Blocked != 0 || r.Net() != 0 || r.Note != "n/a (dip30+)")) {
				t.Errorf("guard row %+v (logged %v)", r, R.HasGuard)
			}
			continue
		}
		rows = append(rows, r)
	}
	if len(rows) != len(ref.Rows) {
		t.Fatalf("%d rows, want %d", len(rows), len(ref.Rows))
	}
	for i, w := range ref.Rows {
		g := rows[i]
		name := w.Name
		if name == "bad creator" && g.Name == "bad creator (run only)" { // no seed: labelled so
			name = g.Name
		}
		if g.Name != name || g.Type != w.Type || g.Blocked != w.Blocked || g.WinN != w.WinN || g.LoseN != w.LoseN {
			t.Errorf("row %d: %s %s %d %d %d, want %s %s %d %d %d", i, g.Name, g.Type, g.Blocked, g.WinN, g.LoseN, w.Name, w.Type, w.Blocked, w.WinN, w.LoseN)
		}
		if math.Abs(g.WinSol-w.WinSol) > eps || math.Abs(g.LoseSol-w.LoseSol) > eps || math.Abs(g.Net()-w.Net) > eps {
			t.Errorf("row %s: win %.12f lose %.12f net %.12f, want %.12f %.12f %.12f", g.Name, g.WinSol, g.LoseSol, g.Net(), w.WinSol, w.LoseSol, w.Net)
		}
		if g.Type == "LIVE" || name == w.Name {
			if g.Note != w.Note && !(strings.HasPrefix(g.Note, "real fills; no ledger seed")) {
				t.Errorf("row %s note %q, want %q", g.Name, g.Note, w.Note)
			}
		}
	}
	// the script's own text lines (header + rows) = TableLines, character for character (with a seed: same names)
	pl := strings.Split(strings.TrimRight(ref.Text, "\n"), "\n")[1:]
	for i, l := range pl { // the script's unique-total lines (10-31) follow the rows
		if strings.HasPrefix(l, "LIVE total (unique") {
			pl = pl[:i]
			break
		}
	}
	var gl []string
	for _, l := range R.TableLines() {
		if !strings.HasPrefix(l, "landing guard") {
			gl = append(gl, l)
		}
	}
	if R.Seed != "" {
		if strings.Join(pl, "\n") != strings.Join(gl, "\n") {
			t.Errorf("table text differs:\npy:\n%s\ngo:\n%s", strings.Join(pl, "\n"), strings.Join(gl, "\n"))
		}
	}
	// the items: one per blocked thing (a LOG fill once, with every rule that caught it), W/L as in the rows
	nb := map[string][3]int{}
	seen := map[[2]any]bool{}
	for _, it := range R.Items {
		if !it.Live {
			k := [2]any{it.W, it.Mint}
			if seen[k] {
				t.Errorf("LOG fill %v listed twice", k)
			}
			seen[k] = true
			if it.Name != strings.Join(it.Names, ", ") || len(it.Names) != len(it.Rules) || it.Filter != it.Rules[0] {
				t.Errorf("LOG item %+v", it)
			}
		}
		for _, r := range it.Rules {
			x := nb[r]
			x[0]++
			if it.Scored && it.Sol > 0 {
				x[1]++
			} else if it.Scored {
				x[2]++
			}
			nb[r] = x
		}
	}
	for _, r := range R.Rows {
		if x := nb[r.Key]; x[0] != r.Blocked || x[1] != r.WinN || x[2] != r.LoseN {
			t.Errorf("items of %s: %v, want %d/%d/%d", r.Key, x, r.Blocked, r.WinN, r.LoseN)
		}
	}
}

func TestFiltersR40(t *testing.T) {
	path := fixtureR40(t)
	seed := filepath.Join("testdata", "filters", "gcr_seed.json")
	v := filtView(t, path, seed)
	checkFilt(t, v.Filt, loadRef(t, "ref_seed.json"))
	if v.Filt.Seed != seed || v.Filt.SeedN == 0 {
		t.Errorf("seed %q %d", v.Filt.Seed, v.Filt.SeedN)
	}
	R := v.Filt
	// the deeper limit's extra lines: the deep fills' real P&L vs the shadow, its NET = blocks + gain
	if !R.Deep || R.DeepFills != 146 || R.DeepRealN+R.DeepRAN > R.DeepFills {
		t.Errorf("deep: %+v", R)
	}
	dr, _ := R.Row("deeper")
	if math.Abs(R.DeepNet-(dr.Net()+R.DeepGain)) > 1e-12 || math.Abs(R.DeepGain-(R.DeepReal-R.DeepPaper)) > 1e-9 {
		t.Errorf("deep net %.9f gain %.9f", R.DeepNet, R.DeepGain)
	}
	if math.Abs(R.DeepReal+R.DeepRAReal-1.938) > 0.0005 {
		t.Errorf("deep fills real %.6f (+ re-arm %.6f), the script says +1.938", R.DeepReal, R.DeepRAReal)
	}
	// totals = the rows of each type
	var lv, lg float64
	for _, r := range R.Rows {
		if r.Type == "LIVE" {
			lv += r.Net()
		} else {
			lg += r.Net()
		}
	}
	if math.Abs(R.Live.Net-lv) > 1e-12 || math.Abs(R.Log.Net-lg) > 1e-12 {
		t.Errorf("totals %v %v", R.Live, R.Log)
	}
	// the snapshot sections
	ctx := &Ctx{Src: &Source{JSONL: path, TJ: NewTail(path), TL: NewTail(path)}}
	txt := strings.Join(filtersText(v, ctx), "\n")
	if !strings.Contains(txt, "filters   dip_ams_r40f.jsonl: 335 positions realized +5.495 SOL") || !strings.Contains(txt, "LIVE total (unique triggers):") || !strings.Contains(txt, "ALL total:") {
		t.Errorf("text section:\n%s", txt)
	}
	d := &JObj{}
	filtersJSON(v, d)
	js := JSONDumps(d)
	var back map[string]any
	if err := json.Unmarshal([]byte(js), &back); err != nil {
		t.Fatal(err)
	}
	fo, _ := back["filters"].(map[string]any)
	if fo == nil || len(fo["rows"].([]any)) != len(R.Rows) || len(fo["items"].([]any)) == 0 || fo["guard_logged"] != false {
		t.Fatalf("json: %s", js)
	}
}

func TestFiltersR40NoSeed(t *testing.T) {
	path := fixtureR40(t)
	v := filtView(t, path, "none")
	checkFilt(t, v.Filt, loadRef(t, "ref_noseed.json"))
	if r, _ := v.Filt.Row("gcr"); r.Name != "bad creator (run only)" {
		t.Errorf("no-seed label %q", r.Name)
	}
}

// TestFiltersLive: the table follows the file as it grows (the cache never hands back a stale report).
func TestFiltersLive(t *testing.T) {
	path := fixtureR40(t)
	b, _ := os.ReadFile(path)
	lines := strings.SplitAfter(string(b), "\n")
	cut := len(lines) / 2
	part := filepath.Join(t.TempDir(), "dip_ams_r40f.jsonl")
	os.WriteFile(part, []byte(strings.Join(lines[:cut], "")), 0o644)
	src := NewSource(part, "", 0, 3000)
	src.LoadAll(LoadChunk, 0, nil)
	seed := ResolveGcrSeed(filepath.Join("testdata", "filters", "gcr_seed.json"))
	r1 := src.Model.Filt.Report(seed)
	n1 := 0
	for _, r := range r1.Rows {
		n1 += r.Blocked
	}
	f, _ := os.OpenFile(part, os.O_APPEND|os.O_WRONLY, 0o644)
	f.WriteString(strings.Join(lines[cut:], ""))
	f.Close()
	for src.Step(LoadChunk) > 0 || src.Pending() {
	}
	r2 := src.Model.Filt.Report(seed)
	if r2 == r1 {
		t.Fatal("stale report after the file grew")
	}
	ref := loadRef(t, "ref_seed.json")
	n2, nref := 0, 0
	for _, r := range r2.Rows {
		n2 += r.Blocked
	}
	for _, r := range ref.Rows {
		nref += r.Blocked
	}
	if n2 != nref || n1 >= n2 {
		t.Errorf("blocked %d -> %d, want -> %d", n1, n2, nref)
	}
	if r3 := src.Model.Filt.Report(seed); r3 != r2 {
		t.Error("no records came: the cached report should be reused")
	}
}

// TestFiltersFullR40: filters_report.py itself (python3 -I) against dipmon: on the fixture always (when python3 and the
// script are here), and on a full run file when DIPMON_R40 points at one (a live copy may grow: it is copied first, then
// both read the copy). Its rows at full precision come from testdata/filters/ref_rows.py.
func TestFiltersFullR40(t *testing.T) {
	script := "/home/moiz/sniper/ops/strategies/presend/prevent/forward/filters_report.py"
	py, err := exec.LookPath("python3")
	if _, e2 := os.Stat(script); err != nil || e2 != nil {
		t.Skip("no python3 / filters_report.py here")
	}
	seed, _ := filepath.Abs(filepath.Join("testdata", "filters", "gcr_seed.json"))
	refRows, _ := filepath.Abs(filepath.Join("testdata", "filters", "ref_rows.py"))
	files := []string{fixtureR40(t)}
	if p := os.Getenv("DIPMON_R40"); p != "" {
		dst := filepath.Join(t.TempDir(), "dip_ams_r40.jsonl")
		in, err := os.Open(p)
		if err != nil {
			t.Fatal(err)
		}
		out, _ := os.Create(dst)
		if _, err := io.Copy(out, in); err != nil {
			t.Fatal(err)
		}
		in.Close()
		out.Close()
		files = append(files, dst)
	}
	for _, path := range files {
		b, err := exec.Command(py, "-I", refRows, path, "--seed", seed).Output()
		if err != nil {
			t.Fatal(err)
		}
		var ref refRep
		if err := json.Unmarshal(b, &ref); err != nil {
			t.Fatal(err)
		}
		v := filtView(t, path, seed)
		checkFilt(t, v.Filt, ref)
		checkUnique(t, v.Filt, ref)
		t.Logf("%s: %d rows equal to filters_report.py (%d positions)", filepath.Base(path), len(ref.Rows), ref.Positions)
	}
}

// TestFiltersF36: the owner's example (r40 w1538 F36E6Xcs, a -0.121 SOL loss): one LOG row with every rule that would
// have blocked it ("safe sell timer, group risk, holder clock"), and it appears as soon as its records come (the file
// cut just before its realized record, then grown).
func TestFiltersF36(t *testing.T) {
	path := fixtureR40(t)
	b, _ := os.ReadFile(path)
	lines := strings.SplitAfter(string(b), "\n")
	cut := -1
	for i, l := range lines {
		if strings.Contains(l, `"ev":"presend_live_realized"`) && strings.Contains(l, "F36E6Xcs") {
			cut = i
		}
	}
	if cut < 0 {
		t.Fatal("no F36E6Xcs realized record in the fixture")
	}
	part := filepath.Join(t.TempDir(), "dip_ams_r40f.jsonl")
	os.WriteFile(part, []byte(strings.Join(lines[:cut], "")), 0o644)
	src := NewSource(part, "", 0, 3000)
	src.LoadAll(LoadChunk, 0, nil)
	seed := filepath.Join("testdata", "filters", "gcr_seed.json")
	find := func(R *FiltReport) *FiltItem {
		for i := range R.Items {
			if !R.Items[i].Live && strings.HasPrefix(R.Items[i].Mint, "F36E6Xcs") {
				return &R.Items[i]
			}
		}
		return nil
	}
	if it := find(src.Model.Filt.Report(seed)); it != nil {
		t.Fatalf("F36E6Xcs listed before it was realized: %+v", it)
	}
	f, _ := os.OpenFile(part, os.O_APPEND|os.O_WRONLY, 0o644)
	f.WriteString(strings.Join(lines[cut:], ""))
	f.Close()
	for src.Step(LoadChunk) > 0 || src.Pending() {
	}
	R := src.Model.Filt.Report(seed)
	it := find(R)
	if it == nil {
		t.Fatal("F36E6Xcs not listed after its realized record")
	}
	if it.Name != "safe sell timer, group risk, holder clock" || strings.Join(it.Rules, ",") != "st,grp,hc" || it.Kind != "T2" ||
		math.Abs(it.Sol-(-0.120771)) > 0.0005 || !it.Has("hc") || it.Has("gcr") {
		t.Errorf("F36E6Xcs: %+v", *it)
	}
	if R.Items[0].Mint != it.Mint { // the newest item: on top of the list
		t.Errorf("newest item %s, want F36E6Xcs", R.Items[0].Mint)
	}
}

// TestFiltersLandingGuard: dip30's landing guard (ann.guard.block) as a LOG rule on the real fills; n/a on runs without it.
func TestFiltersLandingGuard(t *testing.T) {
	recs := []string{
		`{"ev":"presend_live_arm","w":1,"mint":"MintA","trig":{"sig":"s1","mint":"MintA","t":1000},"spend":500000000,"ann":{"creator":"C1","cr_pct":1}}`,
		`{"ev":"presend_live_fill","w":1,"mint":"MintA","t":2000,"ann":{"st_block":true,"grp_block":false,"holders":[],"guard":{"block":true,"pct":7.25,"set":[{"w":"X","sign_pct":8.0,"land_pct":7.25}]}}}`,
		`{"ev":"presend_live_realized","w":1,"mint":"MintA","pnl":-50000000}`,
		`{"ev":"presend_live_arm","w":2,"mint":"MintB","trig":{"sig":"s2","mint":"MintB","t":3000},"spend":500000000,"ann":{"creator":"C2","cr_pct":1}}`,
		`{"ev":"presend_live_fill","w":2,"mint":"MintB","t":4000,"ann":{"st_block":false,"grp_block":true,"holders":[],"guard":{"block":true,"pct":6.5,"set":[]}}}`,
		`{"ev":"presend_live_realized","w":2,"mint":"MintB","pnl":20000000}`,
		`{"ev":"presend_live_arm","w":3,"mint":"MintC","trig":{"sig":"s3","mint":"MintC","t":5000},"spend":500000000,"ann":{"creator":"C3","cr_pct":1}}`,
		`{"ev":"presend_live_fill","w":3,"mint":"MintC","t":6000,"ann":{"st_block":false,"holders":[],"guard":{"block":false,"pct":1.0,"set":[]}}}`,
		`{"ev":"presend_live_realized","w":3,"mint":"MintC","pnl":-10000000}`,
	}
	run := func(ls []string) *FiltReport {
		p := filepath.Join(t.TempDir(), "dip_ams_r99.jsonl")
		os.WriteFile(p, []byte(strings.Join(ls, "\n")+"\n"), 0o644)
		src := NewSource(p, "", 0, 3000)
		src.LoadAll(LoadChunk, 0, nil)
		return src.Model.Filt.Report("")
	}
	R := run(recs)
	g, ok := R.Row("guard")
	if !ok || g.NA || !R.HasGuard || g.Blocked != 2 || g.WinN != 1 || g.LoseN != 1 || math.Abs(g.Net()-0.03) > 1e-12 {
		t.Fatalf("guard row %+v", g)
	}
	if R.Rows[len(R.Rows)-1].Key != "guard" {
		t.Error("the guard row is not last")
	}
	var a, b *FiltItem
	for i := range R.Items {
		switch R.Items[i].Mint {
		case "MintA":
			a = &R.Items[i]
		case "MintB":
			b = &R.Items[i]
		case "MintC":
			t.Error("MintC (guard not blocking) listed")
		}
	}
	if a == nil || a.Name != "safe sell timer, landing guard" || a.GuardPct != 7.25 || b == nil || b.Name != "group risk, landing guard" {
		t.Errorf("items %+v %+v", a, b)
	}
	if R.Log.Net != func() float64 {
		s := 0.0
		for _, r := range R.Rows {
			if r.Type == "LOG" {
				s += r.Net()
			}
		}
		return s
	}() {
		t.Error("LOG total")
	}
	if !strings.Contains(strings.Join(R.TableLines(), "\n"), "landing guard (new)") {
		t.Error("table lines lack the guard")
	}
	// a run before dip30: the same records without "guard" -> n/a, nothing counted
	var old []string
	for _, l := range recs {
		if i := strings.Index(l, `,"guard":`); i >= 0 {
			l = l[:i] + "}}"
		}
		old = append(old, l)
	}
	R = run(old)
	g, _ = R.Row("guard")
	if !g.NA || R.HasGuard || g.Blocked != 0 || g.Note != "n/a (dip30+)" {
		t.Errorf("no guard field: %+v", g)
	}
	if !strings.Contains(strings.Join(R.TableLines(), "\n"), "n/a   (dip30+: not logged by this run)") {
		t.Error("table lines: n/a")
	}
}

// BenchmarkFiltersReport: one recompute of the table + list on r40 (it runs at most once a refresh, only after a
// filter record came).
func BenchmarkFiltersReport(b *testing.B) {
	path := fixtureR40(b)
	src := NewSource(path, "", 0, 3000)
	src.LoadAll(LoadChunk, 0, nil)
	seed := filepath.Join("testdata", "filters", "gcr_seed.json")
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		src.Model.Filt.compute(seed)
	}
}

// checkUnique: the unique totals (LIVE per trigger, LOG per fill, ALL) against filters_report.py's new final lines
// (ref_rows.py hands them over at full precision). The script has no landing guard, so on a run that logs it the LOG
// numbers are only compared when the guard flags no extra fill.
func checkUnique(t *testing.T, R *FiltReport, ref refRep) {
	t.Helper()
	if ref.Unique == nil {
		t.Fatal("filters_report.py prints no unique totals")
	}
	const eps = 1e-9
	for name, g := range map[string]FiltTotal{"live": R.LiveU, "log": R.LogU, "all": R.All} {
		w := ref.Unique[name]
		if g.Blocked != w.Blocked || g.WinN != w.WinN || g.LoseN != w.LoseN || math.Abs(g.WinSol-w.WinSol) > eps || math.Abs(g.LoseSol-w.LoseSol) > eps || math.Abs(g.Net-w.Net) > eps {
			t.Errorf("unique %s: go %+v, script %+v", name, g, w)
		}
	}
}

// smallFixture: a hand-made run (SOL values by hand in the comments). Live size 0.5, shadow size 1.0 (paper x0.5).
//
//	LIVE skips: s1 quiet (+0.25), s1 create_slot (the SAME trigger, +0.25), s2 young_age (-0.10), s3 quiet (+0.05), s4 lone_whale (no shadow fill)
//	  rows: 5 blocked (3 W +0.55, 1 L -0.10); unique triggers: 4 blocked (2 W +0.30, 1 L -0.10), net saved -0.20
//	LOG fills: M1 -0.30 (safe sell timer + group risk + holder clock), M2 +0.10 (landing guard), M3 +0.20 (no rule)
//	  rows: 4 blocked; unique fills: 2 (1 W +0.10, 1 L -0.30), net saved +0.20
//	ALL: 6 blocked, 3 W +0.40, 2 L -0.40, net 0.00
func smallFixture(t testing.TB) string {
	recs := []string{
		`{"ev":"presend_arm","sig":"s1","w":1}`, `{"ev":"presend_arm","sig":"s2","w":2}`, `{"ev":"presend_arm","sig":"s3","w":3}`, `{"ev":"presend_arm","sig":"s4","w":4}`,
		`{"ev":"presend_fill","row":"c","w":1,"entry":{"sol_in":1000000000}}`, `{"ev":"presend_fill","row":"c","w":2,"entry":{"sol_in":1000000000}}`,
		`{"ev":"presend_fill","row":"c","w":3,"entry":{"sol_in":1000000000}}`,
		`{"ev":"presend_exit","row":"c","w":1,"net_cheap":0.5}`, `{"ev":"presend_exit","row":"c","w":2,"net_cheap":-0.2}`, `{"ev":"presend_exit","row":"c","w":3,"net_cheap":0.1}`,
		`{"ev":"presend_live_skip","why":"quiet","trig":{"sig":"s1","mint":"MA","t":1000}}`,
		`{"ev":"presend_live_skip","why":"create_slot","trig":{"sig":"s1","mint":"MA","t":1000}}`,
		`{"ev":"presend_live_skip","why":"young_age","trig":{"sig":"s2","mint":"MB","t":2000}}`,
		`{"ev":"presend_live_skip","why":"quiet","trig":{"sig":"s3","mint":"MC","t":3000}}`,
		`{"ev":"presend_live_skip","why":"lone_whale","trig":{"sig":"s4","mint":"MD","t":4000}}`,
	}
	h := `{"w":"AAAAAAAAbbbb","pct":7.5,"n":6,"h3":0.9,"risk":6,"hz3":0.91},{"w":"CCCCCCCCdddd","pct":3.6,"n":6,"h3":0.1,"risk":6,"hz3":0.5}`
	anns := []string{
		`{"st_block":true,"grp_block":true,"grp_pct":11.1,"holders":[` + h + `],"guard":{"block":false,"pct":0,"set":[]}}`,
		`{"st_block":false,"grp_block":false,"holders":[],"guard":{"block":true,"pct":15.5,"set":[{"w":"EEEEEEEEffff","sign_pct":15.5,"land_pct":15.5}]}}`,
		`{"st_block":false,"grp_block":false,"holders":[],"guard":{"block":false,"pct":0,"set":[]}}`,
	}
	pnl := []string{"-300000000", "100000000", "200000000"}
	for i := 0; i < 3; i++ {
		w, m := 10+i, []string{"M1", "M2", "M3"}[i]
		recs = append(recs,
			`{"ev":"presend_live_arm","w":`+itoa(w)+`,"mint":"`+m+`","kind":"t2","spend":500000000,"trig":{"sig":"x`+itoa(w)+`","mint":"`+m+`","t":`+itoa(10000+w)+`}}`,
			`{"ev":"presend_live_fill","w":`+itoa(w)+`,"mint":"`+m+`","t":`+itoa(20000+i)+`,"ann":`+anns[i]+`}`,
			`{"ev":"presend_live_realized","w":`+itoa(w)+`,"mint":"`+m+`","pnl":`+pnl[i]+`}`)
	}
	p := filepath.Join(t.TempDir(), "dip_ams_r99.jsonl")
	if err := os.WriteFile(p, []byte(strings.Join(recs, "\n")+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

func itoa(i int) string { return strconv.Itoa(i) }

func TestFiltersUniqueHand(t *testing.T) {
	v := filtView(t, smallFixture(t), "none")
	R := v.Filt
	near := func(a, b float64) bool { return math.Abs(a-b) < 1e-9 }
	chk := func(name string, g FiltTotal, n, wn int, ws float64, ln int, ls, net float64) {
		if g.Blocked != n || g.WinN != wn || g.LoseN != ln || !near(g.WinSol, ws) || !near(g.LoseSol, ls) || !near(g.Net, net) {
			t.Errorf("%s: %+v, want %d %d %.2f %d %.2f net %.2f", name, g, n, wn, ws, ln, ls, net)
		}
	}
	chk("LIVE rows", R.Live, 5, 3, 0.55, 1, -0.10, -0.45) // the plain row sums
	chk("LIVE unique", R.LiveU, 4, 2, 0.30, 1, -0.10, -0.20)
	chk("LOG unique", R.LogU, 2, 1, 0.10, 1, -0.30, 0.20)
	chk("ALL", R.All, 6, 3, 0.40, 2, -0.40, 0)
	if R.LiveDup != 1 || R.LogDup != 2 || R.LogMulti != 1 {
		t.Errorf("dups: live %d log %d multi %d", R.LiveDup, R.LogDup, R.LogMulti)
	}
	// the flags: M1 by three rules with their numbers, M2 by the guard, M3 none
	it, ok := R.Flag(10, "M1")
	if !ok || strings.Join(it.Rules, ",") != "st,grp,hc" {
		t.Fatalf("M1 flag %+v", it)
	}
	want := "safe sell timer (holder AAAAAAAA 7.5%, hz3 0.91) · group risk (11.1% = AAAAAAAA 7.5% + CCCCCCCC 3.6%) · holder clock (holder AAAAAAAA 7.5%, h3 0.90)"
	if it.Info() != want {
		t.Errorf("info:\n got %s\nwant %s", it.Info(), want)
	}
	if it, ok := R.Flag(11, "M2"); !ok || it.Info() != "landing guard (guard set 15.5% at landing)" {
		t.Errorf("M2 %+v %v", it, ok)
	}
	if _, ok := R.Flag(12, "M3"); ok {
		t.Error("M3 must not be flagged")
	}
	if R.NFlagged() != 2 {
		t.Errorf("flagged %d", R.NFlagged())
	}
}

// moveFixture: shadow windows w1 (filled, with a "move"), w2 (filled, no "move": a run before 11-03), w5 (never filled,
// with a "move"), w6 (never filled, no trades); one skipped trigger each; a real fill whose arm logged f3 with q3a false
// (the QUIET3-A log row then marks nothing). q3live adds a run_start whose presend_live has "quiet3a": true.
func moveFixture(t testing.TB, q3live bool) string {
	recs := []string{
		`{"ev":"presend_arm","sig":"s1","w":1}`, `{"ev":"presend_arm","sig":"s2","w":2}`, `{"ev":"presend_arm","sig":"s5","w":5}`, `{"ev":"presend_arm","sig":"s6","w":6}`,
		`{"ev":"presend_fill","row":"c","w":1,"entry":{"sol_in":1000000000}}`, `{"ev":"presend_fill","row":"c","w":2,"entry":{"sol_in":1000000000}}`,
		`{"ev":"presend_exit","row":"c","w":1,"net_cheap":0.5}`, `{"ev":"presend_exit","row":"c","w":2,"net_cheap":-0.2}`,
		`{"ev":"presend_disarm","w":1,"why":"expired","rows":{"c":{"filled":true}},"move":{"max_pct":35.4,"min_pct":-7.6,"n":12}}`,
		`{"ev":"presend_disarm","w":2,"why":"expired","rows":{"c":{"filled":true}}}`,
		`{"ev":"presend_disarm","w":5,"why":"expired","rows":{"c":{"filled":false}},"move":{"max_pct":4.2,"min_pct":-0.4,"n":3}}`,
		`{"ev":"presend_disarm","w":6,"why":"expired","rows":{"c":{"filled":false}},"move":{"max_pct":0,"min_pct":0,"n":0}}`,
		`{"ev":"presend_live_skip","why":"quiet","trig":{"sig":"s1","mint":"MA","t":1000}}`,
		`{"ev":"presend_live_skip","why":"young_age","trig":{"sig":"s2","mint":"MB","t":2000}}`,
		`{"ev":"presend_live_skip","why":"create_slot","trig":{"sig":"s5","mint":"ME","t":5000}}`,
		`{"ev":"presend_live_skip","why":"quiet","trig":{"sig":"s6","mint":"MF","t":6000}}`,
		`{"ev":"presend_live_arm","w":10,"mint":"M1","kind":"t2","spend":500000000,"f3":{"q3a":false,"n_120s":40,"wh_dumps":5,"fresh":10,"fresh_n":2},"trig":{"sig":"x10","mint":"M1","t":10010}}`,
		`{"ev":"presend_live_fill","w":10,"mint":"M1","t":20000,"ann":{"st_block":true,"holders":[]}}`,
		`{"ev":"presend_live_realized","w":10,"mint":"M1","pnl":-300000000}`,
	}
	if q3live {
		recs = append([]string{`{"ev":"run_start","t":1,"presend_live":{"spend":500000000,"quiet3a":true}}`}, recs...)
	}
	p := filepath.Join(t.TempDir(), "dip_ams_r98.jsonl")
	if err := os.WriteFile(p, []byte(strings.Join(recs, "\n")+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

// TestFiltersMove: each LIVE skip carries its shadow window's "move" (by trigger sig -> shadow w), nil without one; a skip
// whose window never filled is unscored (the UI's "no dip"); LOG items have no move.
func TestFiltersMove(t *testing.T) {
	R := filtView(t, moveFixture(t, false), "none").Filt
	by := map[string]FiltItem{}
	for _, it := range R.Items {
		by[it.Mint] = it
	}
	if m := by["MA"].Move; m == nil || m.Max != 35.4 || m.Min != -7.6 || m.N != 12 || !by["MA"].Scored {
		t.Errorf("MA (filled, move): %+v %+v", by["MA"], m)
	}
	if by["MB"].Move != nil || !by["MB"].Scored {
		t.Errorf("MB (filled, no move): %+v", by["MB"])
	}
	if m := by["ME"].Move; m == nil || m.N != 3 || by["ME"].Scored || by["ME"].Sol != 0 {
		t.Errorf("ME (no fill, move): %+v", by["ME"])
	}
	if m := by["MF"].Move; m == nil || m.N != 0 || by["MF"].Scored {
		t.Errorf("MF (no fill, no trades): %+v", by["MF"])
	}
	if it := by["M1"]; it.Live || it.Move != nil {
		t.Errorf("M1 (LOG): %+v", it)
	}
	if _, ok := R.Row("q3a"); !ok || R.Q3Live {
		t.Errorf("QUIET3-A not live: its log row must stay (q3live %v)", R.Q3Live)
	}
}

// TestFiltersQ3aLiveHidesLogRow: with QUIET3-A live (run_start presend_live.quiet3a, or a quiet3_a skip) the
// "QUIET3-A (log)" row is left out (it can never fire); the other f3 row (fresh holders) stays.
func TestFiltersQ3aLiveHidesLogRow(t *testing.T) {
	R := filtView(t, moveFixture(t, true), "none").Filt
	if _, ok := R.Row("q3a"); ok || !R.Q3Live {
		t.Errorf("QUIET3-A live: the log row is still there (q3live %v)", R.Q3Live)
	}
	if _, ok := R.Row("fresh"); !ok {
		t.Error("the fresh holders row went too")
	}
	// the same from a live quiet3_a skip alone (no run_start flag)
	p := moveFixture(t, false)
	b, _ := os.ReadFile(p)
	b = append(b, []byte(`{"ev":"presend_live_skip","why":"quiet3_a","trig":{"sig":"s9","mint":"MZ","t":9000}}`+"\n")...)
	os.WriteFile(p, b, 0o644)
	R = filtView(t, p, "none").Filt
	if _, ok := R.Row("q3a"); ok {
		t.Error("a quiet3_a skip: the log row is still there")
	}
	if r, ok := R.Row("quiet3_a"); !ok || r.Blocked != 1 {
		t.Errorf("QUIET3-A (live) row: %+v %v", r, ok)
	}
}

// TestFiltersFpnb (dip36): the "no-bot filter (log)" row counts the fills whose deciding send FP-NOBOT would have blocked (stage "fill",
// block true; the first fill of a position decides), with their realized P&L; arm / send stages and unblocked fills are not counted.
func TestFiltersFpnb(t *testing.T) {
	recs := []string{
		`{"ev":"presend_live_arm","w":10,"mint":"M1","kind":"t2","spend":500000000,"trig":{"sig":"x10","mint":"M1","t":10010}}`,
		`{"ev":"presend_live_fpnb","stage":"arm","w":10,"mint":"M1","kind":"T2","score":0.5,"thr":0.388,"block":true}`,
		`{"ev":"presend_live_fill","w":10,"mint":"M1","t":20000}`,
		`{"ev":"presend_live_fpnb","stage":"fill","w":10,"mint":"M1","kind":"T2","score":0.45,"thr":0.388,"block":true,"skip2":{"score":-0.5,"thr":-0.319,"skip":true}}`,
		`{"ev":"presend_live_fpnb","stage":"fill","w":10,"mint":"M1","kind":"T2","score":0.1,"thr":0.388,"block":false}`,
		`{"ev":"presend_live_realized","w":10,"mint":"M1","pnl":-20000000}`,
		`{"ev":"presend_live_arm","w":11,"mint":"M2","kind":"rearm","dump":{"sig":"x11","mint":"M2","t":10020}}`,
		`{"ev":"presend_live_fill","w":11,"mint":"M2","t":21000}`,
		`{"ev":"presend_live_fpnb","stage":"fill","w":11,"mint":"M2","kind":"rearm","score":0.6,"thr":0.5,"block":true}`,
		`{"ev":"presend_live_realized","w":11,"mint":"M2","pnl":50000000}`,
		`{"ev":"presend_live_arm","w":12,"mint":"M3","kind":"t2","trig":{"sig":"x12","mint":"M3","t":10030}}`,
		`{"ev":"presend_live_fill","w":12,"mint":"M3","t":22000}`,
		`{"ev":"presend_live_fpnb","stage":"fill","w":12,"mint":"M3","kind":"T2","score":0.2,"thr":0.388,"block":false}`,
		`{"ev":"presend_live_realized","w":12,"mint":"M3","pnl":-10000000}`,
	}
	p := filepath.Join(t.TempDir(), "dip_ams_r99.jsonl")
	if err := os.WriteFile(p, []byte(strings.Join(recs, "\n")+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	R := filtView(t, p, "none").Filt
	r, ok := R.Row("fpnb")
	if !ok || r.Blocked != 2 || r.Type != "LOG" || r.Name != "no-bot filter (log)" || r.WinN != 1 || r.LoseN != 1 {
		t.Fatalf("fpnb row: %+v %v", r, ok)
	}
	if d := r.Net() - (0.02 - 0.05); d > 1e-9 || d < -1e-9 {
		t.Errorf("net %v", r.Net())
	}
	it, ok := R.Flag(10, "M1")
	if !ok || !it.Has("fpnb") || len(it.Why) == 0 || !strings.Contains(it.Why[0], "no-bot score 0.450") {
		t.Errorf("M1 item: %+v", it)
	}
	if _, ok := R.Flag(12, "M3"); ok {
		t.Error("M3 not blocked")
	}
	// dip36 skip2 on the same fill record: its own LOG row (only M1 carries it)
	if s, ok := R.Row("skip2"); !ok || s.Blocked != 1 || s.LoseN != 1 || s.Name != "skip2 per-send (log)" {
		t.Errorf("skip2 row: %+v %v", s, ok)
	}
	if it2, _ := R.Flag(10, "M1"); !it2.Has("skip2") || !it2.Has("fpnb") {
		t.Errorf("M1 rules: %+v", it2.Rules)
	}
}

// TestFiltersBlocklist (dip36): the LIVE "blocklist" row counts T2 "blocklist" skips (scored on the shadow's paper like the other skips) and
// re-arm "rearm_blocklist" skips (counted, unscored); absent without one.
func TestFiltersBlocklist(t *testing.T) {
	recs := []string{
		`{"ev":"presend_arm","sig":"s1","w":1}`,
		`{"ev":"presend_fill","row":"c","w":1,"entry":{"sol_in":1000000000}}`,
		`{"ev":"presend_exit","row":"c","w":1,"net_cheap":-0.04}`,
		`{"ev":"presend_live_skip","why":"blocklist","trig":{"sig":"s1","mint":"MA","t":1000},"bl_wallet":"8ZN71XTd","bl_role":"whale","bl_pct":9.1}`,
		`{"ev":"presend_live_skip","kind":"rearm","why":"rearm_blocklist","mint":"MB","dump":{"sig":"d2","t":2000},"bl_role":"dumper"}`,
		`{"ev":"presend_live_skip","kind":"rearm","why":"rearm_cr_loss","mint":"MC","dump":{"sig":"d3","t":3000}}`,
	}
	p := filepath.Join(t.TempDir(), "dip_ams_r97.jsonl")
	if err := os.WriteFile(p, []byte(strings.Join(recs, "\n")+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	R := filtView(t, p, "none").Filt
	r, ok := R.Row("blocklist")
	if !ok || r.Type != "LIVE" || r.Blocked != 2 || r.LoseN != 1 || r.WinN != 0 {
		t.Fatalf("blocklist row: %+v %v", r, ok)
	}
	kinds := map[string]string{}
	for _, it := range R.Items {
		if it.Filter == "blocklist" {
			kinds[it.Mint] = it.Kind
		}
	}
	if kinds["MA"] != "T2" || kinds["MB"] != "RA" || len(kinds) != 2 {
		t.Errorf("items: %v", kinds)
	}
	R = filtView(t, moveFixture(t, false), "none").Filt
	if _, ok := R.Row("blocklist"); ok {
		t.Error("no blocklist skip: no row")
	}
}

// TestFiltersFpnbLive (dip36): the LIVE "no-bot filter" row: windows with withheld sends that never filled are blocked; the ones that filled
// later are in the note with their real P&L; the withheld sends counted.
func TestFiltersFpnbLive(t *testing.T) {
	recs := []string{
		`{"ev":"presend_live_arm","w":20,"mint":"N1","kind":"t2","trig":{"sig":"y20","mint":"N1","t":10010}}`,
		`{"ev":"presend_live_fpnb_withheld","w":20,"mint":"N1","slot":5,"kind":"T2"}`,
		`{"ev":"presend_live_fpnb_withheld","w":20,"mint":"N1","slot":6,"kind":"T2"}`,
		`{"ev":"presend_live_fpnb_window","w":20,"mint":"N1","kind":"T2","withheld":2,"filled":false,"why":"expired"}`,
		`{"ev":"presend_live_arm","w":21,"mint":"N2","kind":"rearm","dump":{"sig":"y21","t":10020}}`,
		`{"ev":"presend_live_fpnb_withheld","w":21,"mint":"N2","slot":9,"kind":"rearm"}`,
		`{"ev":"presend_live_fill","w":21,"mint":"N2","t":21000}`,
		`{"ev":"presend_live_fpnb_window","w":21,"mint":"N2","kind":"rearm","withheld":1,"filled":true,"why":"filled"}`,
		`{"ev":"presend_live_realized","w":21,"mint":"N2","pnl":-15000000}`,
		`{"ev":"presend_live_fpnb_window","w":22,"mint":"N3","kind":"T2","withheld":0,"filled":true}`,
	}
	p := filepath.Join(t.TempDir(), "dip_ams_r96.jsonl")
	if err := os.WriteFile(p, []byte(strings.Join(recs, "\n")+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	R := filtView(t, p, "none").Filt
	r, ok := R.Row("fpnb_live")
	if !ok || r.Type != "LIVE" || r.Blocked != 1 || !strings.Contains(r.Note, "3 sends withheld") || !strings.Contains(r.Note, "1 filled later") {
		t.Fatalf("fpnb_live row: %+v %v", r, ok)
	}
	n := 0
	for _, it := range R.Items {
		if it.Filter == "fpnb_live" {
			n++
			if it.Mint != "N1" || it.Kind != "T2" {
				t.Errorf("item %+v", it)
			}
		}
	}
	if n != 1 {
		t.Errorf("items %d", n)
	}
	R = filtView(t, moveFixture(t, false), "none").Filt
	if _, ok := R.Row("fpnb_live"); ok {
		t.Error("no gate records: no row")
	}
}
