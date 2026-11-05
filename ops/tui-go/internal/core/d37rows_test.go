package core

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestFiltersD37AllRows (dip37): a dip37 run (run_start with the ledger flags) shows EVERY filter row from the start, at 0 blocks too; each
// row counts its own records: LIVE rows on the shadow paper (re-arm skips counted, unscored), LOG rows on the real fills; the control
// file's mode on the ledger rows; the no-bot row's stale-hold count.
func TestFiltersD37AllRows(t *testing.T) {
	sh := func(w, sig string, net string) []string {
		return []string{`{"ev":"presend_arm","sig":"` + sig + `","w":` + w + `}`, `{"ev":"presend_fill","row":"c","w":` + w + `,"entry":{"sol_in":500000000}}`,
			`{"ev":"presend_exit","row":"c","w":` + w + `,"net_cheap":` + net + `}`}
	}
	skip := func(why, sig, mint string) string {
		return `{"ev":"presend_live_skip","why":"` + why + `","trig":{"sig":"` + sig + `","mint":"` + mint + `","t":1000}}`
	}
	raskip := func(why, mint string) string {
		return `{"ev":"presend_live_skip","kind":"rearm","why":"` + why + `","mint":"` + mint + `","dump":{"sig":"d` + mint + `","t":2000}}`
	}
	recs := []string{`{"ev":"run_start","t":1,"presend_live":{"spend":500000000,"wh_loss":"2:0.05 sum","holder_loss":"2:0.1:0.05","ledger_control":"/x"}}`}
	recs = append(recs, sh("1", "s1", "0.04")...)
	recs = append(recs, sh("2", "s2", "-0.03")...)
	recs = append(recs, sh("3", "s3", "-0.02")...)
	recs = append(recs, sh("4", "s4", "0.01")...)
	recs = append(recs, sh("5", "s5", "-0.05")...)
	recs = append(recs, sh("6", "s6", "0.02")...)
	recs = append(recs,
		skip("wh_loss", "s1", "MA"), raskip("rearm_wh_loss", "MB"),
		skip("holder_loss", "s2", "MC"), raskip("rearm_holder_loss", "MD"),
		skip("blocklist", "s3", "ME"), skip("cr_loss", "s4", "MF"), skip("quiet", "s5", "MG"), skip("m2_unseen", "s6", "MH"),
		`{"ev":"presend_live_fpnb_withheld","w":20,"mint":"MI","slot":5,"kind":"T2","stale":true,"age":1}`,
		`{"ev":"presend_live_fpnb_withheld","w":20,"mint":"MI","slot":6,"kind":"T2"}`,
		`{"ev":"presend_live_ledger_mode","ok":true,"whale":"log","holder":"live"}`,
		// a real fill armed with: the whale's other rule (mean) hit, the whale log-mode would-skip, the holder log-mode would-skip, HYBRID-2 no
		`{"ev":"presend_live_arm","w":30,"mint":"MJ","trig":{"sig":"x30","mint":"MJ","t":3000},"wh_n":2,"wh_sum":-0.06,"wh_sum_hit":true,"wh_mean_hit":true,"wh_would":true,`+
			`"hl_wallet":"H","hl_would":true,"nd":0,"m2max":-1,"h2_keep":false,"h2_size":0.5}`,
		`{"ev":"presend_live_fill","w":30,"mint":"MJ","t":3100}`,
		`{"ev":"presend_live_realized","w":30,"mint":"MJ","pnl":-40000000}`,
		// and a clean one
		`{"ev":"presend_live_arm","w":31,"mint":"MK","trig":{"sig":"x31","mint":"MK","t":4000},"wh_n":0,"wh_sum":0,"wh_sum_hit":false,"wh_mean_hit":false,"nd":2,"m2max":0.1,"h2_keep":true,"h2_size":1.0}`,
		`{"ev":"presend_live_fill","w":31,"mint":"MK","t":4100}`,
		`{"ev":"presend_live_realized","w":31,"mint":"MK","pnl":25000000}`,
	)
	p := filepath.Join(t.TempDir(), "dip_ams_r94.jsonl")
	if err := os.WriteFile(p, []byte(strings.Join(recs, "\n")+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	R := filtView(t, p, "none").Filt
	type want struct {
		key, typ         string
		blk, winN, loseN int
		note             string
	}
	for _, w := range []want{
		{"wh_loss", "LIVE", 1, 1, 0, "mode LOG"}, {"rearm_wh_loss", "LIVE", 1, 0, 0, "no shadow window"}, {"holder_loss", "LIVE", 2, 0, 1, "mode live"},
		{"blocklist", "LIVE", 1, 0, 1, ""}, {"cr_loss", "LIVE", 1, 1, 0, ""}, {"quiet", "LIVE", 1, 0, 1, ""}, {"m2_unseen", "LIVE", 1, 1, 0, ""},
		{"breaker", "LIVE", 0, 0, 0, ""}, {"cr_unfollowed", "LIVE", 0, 0, 0, ""}, {"quiet3_a", "LIVE", 0, 0, 0, ""}, {"create_slot", "LIVE", 0, 0, 0, ""},
		{"fpnb_live", "LIVE", 0, 0, 0, "stale-hold withheld 1"},
		{"fpnb", "LOG", 0, 0, 0, ""}, {"skip2", "LOG", 0, 0, 0, ""}, {"wh_other", "LOG", 1, 0, 1, "mean"}, {"wh_logmode", "LOG", 1, 0, 1, ""},
		{"hl_logmode", "LOG", 1, 0, 1, ""}, {"h2", "LOG", 1, 0, 1, ""},
	} {
		r, ok := R.Row(w.key)
		if !ok {
			t.Errorf("%s: no row (every dip37 row shows from the start)", w.key)
			continue
		}
		if r.Type != w.typ || r.Blocked != w.blk || r.WinN != w.winN || r.LoseN != w.loseN || !strings.Contains(r.Note, w.note) {
			t.Errorf("%s: %+v", w.key, r)
		}
	}
	if r, _ := R.Row("wh_loss"); r.Name != "whale loss (T2) [log]" {
		t.Errorf("the control file's mode in the name: %q", r.Name)
	}
	if r, _ := R.Row("holder_loss"); r.Name != "holder loss (T2 / re-arm) [live]" {
		t.Errorf("%q", r.Name)
	}
	if r, _ := R.Row("wh_loss"); r.Net() != -0.04 {
		t.Errorf("whale loss net (paper, live size = row c size): %v", r.Net())
	}
	// a pre-dip37 run: none of the dip37 rows, the optional ones hidden at 0 as before
	R = filtView(t, moveFixture(t, false), "none").Filt
	for _, k := range []string{"wh_loss", "rearm_wh_loss", "holder_loss", "m2_unseen", "wh_other", "h2", "breaker"} {
		if _, ok := R.Row(k); ok {
			t.Errorf("%s: shown on an older run", k)
		}
	}
}
