package core

import (
	"math"
	"testing"
)

func near(a, b float64) bool { return math.Abs(a-b) < 1e-9 }

// TestCalibEmbedded: the shipped table parses and is the gatecheck 11-11 export (7 buckets, T2 + rearm).
func TestCalibEmbedded(t *testing.T) {
	c := DefaultCalib
	if c == nil {
		t.Fatal("the embedded calib.json does not parse")
	}
	if len(c.Bins) != 8 || len(c.Cal["T2"]) != 7 || len(c.Cal["rearm"]) != 7 {
		t.Fatalf("shape: bins %d T2 %d rearm %d", len(c.Bins), len(c.Cal["T2"]), len(c.Cal["rearm"]))
	}
	if !near(c.Cal["T2"][0], -0.08096) || !near(c.Cal["T2"][6], 0.050939) {
		t.Errorf("T2 ends: %v", c.Cal["T2"])
	}
	if x, err := LoadCalib("none"); x != nil || err != nil {
		t.Errorf("none: %v %v", x, err)
	}
	if _, err := ParseCalib([]byte(`{"bins":[0,1],"cal":{"T2":[1,2]}}`)); err == nil {
		t.Error("a table with the wrong bucket count parsed")
	}
}

// TestCalibApply: the buckets are (lo, hi] like pandas.cut, the ends catch everything, the size scales in and out.
func TestCalibApply(t *testing.T) {
	c := DefaultCalib
	for _, x := range []struct {
		paper, size float64
		kind        string
		want        float64
	}{
		{-20, 1, "T2", -0.08096},         // below the first edge
		{-0.15, 1, "T2", -0.08096},       // the edge belongs to the bucket below it (closed right)
		{-0.149, 1, "T2", -0.03542},      //
		{0.0, 1, "T2", -0.012003},        // a flat paper trade loses live
		{0.02, 1, "T2", -0.012003},       //
		{0.05, 1, "T2", -0.001826},       // a small paper win is ~0 live
		{0.1, 1, "T2", 0.020005},         //
		{3.0, 1, "T2", 0.050939},         // a big paper win
		{50, 1, "T2", 0.050939},          // above the last edge
		{0.1, 0.5, "T2", 0.050939 * 0.5}, // at 0.5 SOL: +0.1 = +0.2 at 1 SOL -> (0.15, 9], scaled back x 0.5
		{0.1, 0.8, "RA", 0.021479},       // re-arm at its reference 0.8 SOL
		{0.1, 0, "rearm", 0.021479},      // size 0 = the reference spend
	} {
		got, ok := c.Apply(x.paper, x.kind, x.size)
		if !ok || !near(got, x.want) {
			t.Errorf("Apply(%v, %s, %v) = %v %v, want %v", x.paper, x.kind, x.size, got, ok, x.want)
		}
	}
	if _, ok := c.Apply(1, "REG", 1); ok {
		t.Error("a kind without a table was calibrated")
	}
	var nilc *Calib
	if _, ok := nilc.Apply(1, "T2", 1); ok {
		t.Error("a nil table calibrated")
	}
}

// TestCalibRow: a synthetic LIVE row (5 skips: 4 paper-scored T2, 1 shadow never filled, 1 re-arm with no shadow) and a
// LOG row through calibrate: the LIVE row's cal W / L / net, the paper kept, the LOG row untouched, the unique totals.
func TestCalibRow(t *testing.T) {
	R := &FiltReport{Rows: []FiltRow{
		{Key: "create_slot", Type: "LIVE", Blocked: 6, WinN: 3, LoseN: 1, WinSol: 0.30 + 0.04 + 0.5, LoseSol: -0.2},
		{Key: "grp", Type: "LOG", Blocked: 1, LoseN: 1, LoseSol: -0.1},
	}}
	add := func(sig string, sol float64, scored bool, kind string) {
		R.Items = append(R.Items, FiltItem{Live: true, Filter: "create_slot", Kind: kind, Sig: sig, Scored: scored, Sol: sol})
	}
	add("a", 0.30, true, "T2") // (0.15, 9] -> +0.050939
	add("b", 0.04, true, "T2") // (0.02, 0.06] -> -0.001826 (a paper win, a live loss)
	add("c", 0.5, true, "T2")  // +0.050939
	add("d", -0.2, true, "T2") // (-9, -0.15] -> -0.08096
	add("e", 0, false, "T2")   // shadow never filled: no value
	add("f", 0, false, "RA")   // re-arm: no shadow
	add("a", 0.30, true, "T2") // the same trigger again (a second row in real life): once in the unique total
	R.Items = append(R.Items, FiltItem{Filter: "grp", Kind: "T2", Scored: true, Sol: -0.1})
	R.LiveU = FiltTotal{Blocked: 6}
	R.LogU = FiltTotal{Blocked: 1, LoseN: 1, LoseSol: -0.1, Net: 0.1}
	R.calibrate(DefaultCalib, 1.0)
	r := R.Rows[0]
	if !r.Cal || r.CalWinN != 3 || r.CalLoseN != 2 { // the repeated "a" item belongs to the row too (rows count per item)
		t.Fatalf("cal row: %+v", r)
	}
	wantNet := -(3*0.050939 - 0.001826 - 0.08096)
	if !near(r.CalNet(), wantNet) || !near(r.ShownNet(), wantNet) {
		t.Errorf("cal net %v want %v", r.CalNet(), wantNet)
	}
	if !near(r.Net(), -(0.84 - 0.2)) {
		t.Errorf("the paper net changed: %v", r.Net())
	}
	if lg := R.Rows[1]; lg.Cal || lg.ShownNet() != lg.Net() {
		t.Errorf("the LOG row was calibrated: %+v", lg)
	}
	for _, it := range R.Items {
		if it.Cal != (it.Live && it.Scored) {
			t.Errorf("item %+v: cal %v", it, it.Cal)
		}
	}
	u := R.LiveUCal // a, b, c, d once each
	if u.WinN != 2 || u.LoseN != 2 || !near(u.Net, -(2*0.050939-0.001826-0.08096)) || u.Blocked != 6 {
		t.Errorf("unique cal total: %+v", u)
	}
	if !near(R.AllCal.Net, u.Net+0.1) || R.AllCal.LoseN != 3 {
		t.Errorf("ALL cal: %+v", R.AllCal)
	}
}
