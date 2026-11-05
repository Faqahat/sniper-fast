package core

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestFiltersWhLoss (dip37): the LIVE "wh_loss" row ("whale loss") counts T2 "wh_loss" skips (scored on the shadow's paper like the other
// skips) and re-arm "rearm_wh_loss" skips (counted, unscored); absent without one.
func TestFiltersWhLoss(t *testing.T) {
	recs := []string{
		`{"ev":"presend_arm","sig":"s1","w":1}`,
		`{"ev":"presend_fill","row":"c","w":1,"entry":{"sol_in":1000000000}}`,
		`{"ev":"presend_exit","row":"c","w":1,"net_cheap":0.03}`,
		`{"ev":"presend_live_skip","why":"wh_loss","trig":{"sig":"s1","mint":"MA","t":1000,"wallet":"BujUx1wz"},"wh_wallet":"BujUx1wz","wh_n":13,"wh_sum":-0.91,"wh_sum_hit":true,"wh_mean_hit":true}`,
		`{"ev":"presend_live_skip","kind":"rearm","why":"rearm_wh_loss","mint":"MB","dump":{"sig":"d2","t":2000,"seller":"X"},"wh_wallet":"X","wh_n":2,"wh_sum":-0.2}`,
		`{"ev":"presend_live_skip","kind":"rearm","why":"rearm_cr_loss","mint":"MC","dump":{"sig":"d3","t":3000}}`,
	}
	p := filepath.Join(t.TempDir(), "dip_ams_r96.jsonl")
	if err := os.WriteFile(p, []byte(strings.Join(recs, "\n")+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	R := filtView(t, p, "none").Filt
	r, ok := R.Row("wh_loss")
	if !ok || r.Type != "LIVE" || r.Name != "whale loss (T2)" || r.Blocked != 1 || r.WinN != 1 || r.LoseN != 0 {
		t.Fatalf("wh_loss row: %+v %v", r, ok)
	}
	ra, ok := R.Row("rearm_wh_loss")
	if !ok || ra.Blocked != 1 || ra.WinN+ra.LoseN != 0 || ra.Name != "whale loss (re-arm)" {
		t.Fatalf("rearm_wh_loss row: %+v %v", ra, ok)
	}
	kinds := map[string]string{}
	for _, it := range R.Items {
		if it.Filter == "wh_loss" || it.Filter == "rearm_wh_loss" {
			kinds[it.Mint] = it.Kind
		}
	}
	if kinds["MA"] != "T2" || kinds["MB"] != "RA" || len(kinds) != 2 {
		t.Errorf("items: %v", kinds)
	}
	if _, ok := R.Row("blocklist"); ok {
		t.Error("no blocklist skip: no blocklist row")
	}
	R = filtView(t, moveFixture(t, false), "none").Filt
	if _, ok := R.Row("wh_loss"); ok {
		t.Error("no whale-loss skip: no row")
	}
}

// TestFiltersH2 (dip37): the LOG row "HYBRID-2 gate (log)" counts the real fills whose arm had h2_keep false (won / lost on their realized
// P&L); the LIVE "m2_unseen" row counts the gate's skips (re-arm ones unscored)
func TestFiltersH2(t *testing.T) {
	recs := []string{
		`{"ev":"presend_live_arm","w":1,"mint":"M1","trig":{"sig":"x1","mint":"M1","t":1000},"nd":0,"m2max":-1,"h2_keep":false,"h2_size":0.4}`,
		`{"ev":"presend_live_fill","w":1,"mint":"M1","t":2000}`,
		`{"ev":"presend_live_realized","w":1,"mint":"M1","pnl":-20000000}`,
		`{"ev":"presend_live_arm","w":2,"mint":"M2","trig":{"sig":"x2","mint":"M2","t":3000},"nd":2,"m2max":0.01,"h2_keep":true,"h2_size":1.0}`,
		`{"ev":"presend_live_fill","w":2,"mint":"M2","t":4000}`,
		`{"ev":"presend_live_realized","w":2,"mint":"M2","pnl":30000000}`,
		`{"ev":"presend_live_skip","kind":"rearm","why":"rearm_m2_unseen","mint":"M3","dump":{"sig":"d3","t":5000},"nd":0}`,
	}
	p := filepath.Join(t.TempDir(), "dip_ams_r95.jsonl")
	if err := os.WriteFile(p, []byte(strings.Join(recs, "\n")+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	R := filtView(t, p, "none").Filt
	r, ok := R.Row("h2")
	if !ok || r.Type != "LOG" || r.Blocked != 1 || r.LoseN != 1 || r.WinN != 0 {
		t.Fatalf("h2 row: %+v %v", r, ok)
	}
	m, ok := R.Row("m2_unseen")
	if !ok || m.Type != "LIVE" || m.Blocked != 1 || m.Name != "M2 unseen" {
		t.Fatalf("m2_unseen row: %+v %v", m, ok)
	}
}
