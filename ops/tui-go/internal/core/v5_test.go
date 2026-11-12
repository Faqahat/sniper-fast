package core

import (
	"os"
	"strings"
	"testing"
)

// v5: a synthetic dip46 + dip47 run (record shapes from sniper-dip46 docs/dip46_probe_ab.md and sniper-dip47 a85abd28
// psctl47 / psgrp47 / psrfleet47 / psfunder47 / psrearm).
var v5Recs = []string{
	`{"ev":"presend_live_dip46","ab_now":["young_age"],"cfg":{"filter_ab":["young_age"],"probe":{"kinds":"all","max_per_sec":5,"max_windows":8}},"probe_now":true,"t":1794423747684900770}`,
	`{"ev":"presend_live_filter_state","fv":0,"fh":"aaaa0000","src":"start","state":{"grp_t2":"log","grp_t2_pct":3.0,"grp_t2_whale":"out","rearm_fleet":"log","rearm_fleet_spec":"1:8","rearm_max_per_mint":2,"pause_window":"00:20-00:25","pause_now":"off","tp":0.2},"changed":{},"t":1794423747684900770}`,
	`{"ev":"presend_live_arm","w":1,"mint":"MintT2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","kind":"t2","fv":0,"fh":"aaaa0000","ab46":{"n":1,"arms":{"young_age":"bypass"},"would":["young_age"]},"trig":{"sig":"S1","mint":"MintT2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","t":1794423750000000000}}`,
	`{"ev":"presend_live_filter_state","fv":1,"fh":"bbbb1111","src":"control","state":{"grp_t2":"live","grp_t2_pct":3.0,"grp_t2_whale":"out","rearm_fleet":"log","rearm_fleet_spec":"1:8","rearm_max_per_mint":2,"pause_window":"00:20-00:25","pause_now":"off","tp":0.2},"changed":{"grp_t2":["log","live"]},"t":1794423760000000000}`,
	`{"ev":"presend_live_funder","w":1,"mint":"MintT2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","kind":"t2","at":"fill","slot":5,"n":19,"pct":60.0,"resolved":19,"pending":0,"c1":{"funder":"BufYjmzEQQQQ","n_wallets":17,"pct":44.0},"c2":null,"t":1794423760500000000}`,
	`{"ev":"presend_live_fill","w":1,"mint":"MintT2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","kind":"t2","spend":1000000000,"sol_in":990000000,"t":1794423761000000000,"fv":0,"fh":"aaaa0000","fv_fill":1,"grpsign":{"pct":5.0,"would_block_t2":true,"pct_x":4.0,"would_block_t2_x":true},"funder":{"pct":44.0,"n":17,"resolved":19},"filters":{"grp_t2_pct":3.0,"grp_t2_whale":"out"}}`,
	`{"ev":"presend_live_exit","w":1,"why":"stop-loss","t":1794423763000000000}`,
	`{"ev":"presend_live_realized","w":1,"mint":"MintT2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","kind":"t2","pnl":-300000000,"fv":0,"fh":"aaaa0000"}`,
	`{"ev":"presend_live_arm","w":2,"mint":"MintRAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","kind":"rearm","fv":1,"fh":"bbbb1111","dump":{"t":1794423770000000000}}`,
	`{"ev":"presend_live_grpsign","w":2,"mint":"MintRAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","kind":"rearm","at":"first_try","grp_pct":7.0,"grp_pct_x":7.0,"n":2,"would_block_t2":false,"would_block_t2_x":false,"would_block_6":true}`,
	`{"ev":"presend_live_grpsign","w":1,"mint":"MintT2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","kind":"t2","at":"first_try","grp_pct":5.0,"grp_pct_x":4.0,"n":2,"would_block_t2":true,"would_block_t2_x":true,"would_block_6":false}`,
	`{"ev":"presend_live_fill","w":2,"mint":"MintRAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","kind":"rearm","spend":800000000,"t":1794423771000000000,"fv":1,"fh":"bbbb1111","rearm_fleet":{"n":0,"min":1,"slots":8,"on":"log","would_withhold":true},"funder":{"pct":3.0,"n":2,"resolved":5}}`,
	`{"ev":"presend_live_realized","w":2,"mint":"MintRAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","kind":"rearm","pnl":200000000}`,
	`{"ev":"presend_live_rearm_fleet","w":2,"mint":"MintRAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","kind":"rearm","mode":"log","tries":10,"passed":6,"withheld":0,"would":4,"open":0,"n_min":0,"t":1794423772000000000}`,
	`{"ev":"presend_live_skip","kind":"rearm","why":"rearm_cap","mint":"MintRAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","rearm_fills":2,"cap":2,"dump":{"t":1794423780000000000}}`,
	`{"ev":"presend_live_skip","why":"grp_t2","trig":{"sig":"S9","mint":"MintZZ","t":1794423781000000000},"grp_t2":{"pct":4.5,"thr":3.0},"fv":1}`,
	`{"ev":"presend_live_ledger_mode","ok":true,"pause_window":"on","window":"00:20-00:25","tz":"PKT","t":1794424800000000000}`,
	`{"ev":"presend_live_ledger_mode","ok":true,"pause_window":"off","window":"00:20-00:25","tz":"PKT","skipped":7,"t":1794425100000000000}`,
	`{"ev":"presend_live_probe","w":1099511627777,"filter":"young_age","sig":"P1","tip":100000,"mint":"MintPPPP","t":1794423749941924100}`,
	`{"ev":"presend_live_probe_land","w":1099511627777,"filter":"young_age","mint":"MintPPPP","sig":"P1","res":"6042","fee":10500,"slot":100,"idx":5,"spend":1000000000,"would_min_out":1000,"would_fill":true,"pre":{"vtok":800000000000000},"would_tokens":30000000000000,"t":1794423750013566074}`,
	`{"ev":"presend_live_probe_land","w":1099511627777,"filter":"young_age","mint":"MintPPPP","sig":"P2","res":"unseen","fee":0,"t":1794423750113566074}`,
	`{"ev":"presend_attempt_land","ms_send_to_first_rx":30.0,"client":"FireBAM","path":"helius-ps"}`,
	`{"ev":"presend_attempt_land","ms_send_to_first_rx":90.0,"client":"JitoLabs","path":"helius-ps"}`,
}

func v5Model(t *testing.T) *Model {
	M := NewModel(0, 100)
	var ls [][]byte
	for _, r := range v5Recs {
		ls = append(ls, []byte(r))
	}
	M.FeedJSONL(ls)
	if M.Bad != 0 {
		t.Fatalf("bad %d", M.Bad)
	}
	return M
}

func v5Sec(R *V5Report, key string) *D43Section {
	for _, s := range append(append([]*D43Section(nil), R.Rule...), R.Stats...) {
		if s.Key == key {
			return s
		}
	}
	return nil
}

func jget(o *JObj, k string) any { v, _ := o.Get(k); return v }

func TestV5Report(t *testing.T) {
	M := v5Model(t)
	R := M.V5.Report(1794423790000000000, nil, nil)
	for _, k := range []string{"probes", "ab46", "fstate", "pause", "rearm_cap", "rearm_fleet", "grpsign", "funder", "hours", "big", "landing"} {
		if v5Sec(R, k) == nil {
			t.Fatalf("no %s section", k)
		}
	}
	f1 := R.Fill(1, "MintT2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
	if f1 == nil || f1.FvCell() != "0*" || f1.Fund.Funder != "BufYjmzEQQQQ" || f1.Exit != "stop-loss" || f1.Pnl != -300000000 {
		t.Fatalf("fill 1 %+v", f1)
	}
	if c := R.Fill(2, "MintRAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA").FvCell(); c != "1" {
		t.Fatalf("fill 2 fv %q", c)
	}
	fs := v5Sec(R, "fstate").JSON
	if jget(fs, "fv") != int64(1) || len(jget(fs, "changes").([]any)) != 1 {
		t.Fatalf("fstate %v", fs)
	}
	fl := v5Sec(R, "rearm_fleet").JSON
	if jget(fl, "windows_would") != int64(1) || jget(fl, "fills_without") != int64(1) || jget(fl, "would_save") != int64(-200000000) {
		t.Fatalf("fleet %v", fl.Keys)
	}
	g := v5Sec(R, "grpsign").JSON
	if jget(g, "would_skip") != int64(1) || jget(g, "skipped") != 1 || jget(g, "pnl_would") != int64(-300000000) {
		t.Fatalf("grp %v", g.Vals)
	}
	fu := v5Sec(R, "funder").JSON
	if len(jget(fu, "flagged").([]any)) != 1 || jget(fu, "flagged_pnl") != int64(-300000000) {
		t.Fatalf("funder %v", fu.Vals)
	}
	p := v5Sec(R, "pause").JSON
	if jget(p, "active") != false || jget(p, "skips_total") != int64(0) || len(jget(p, "periods").([]any)) != 1 {
		t.Fatalf("pause %v", p.Vals)
	}
	if R.Pause.NextStart == 0 || !strings.Contains(strings.Join(v5Sec(R, "pause").Lines, "\n"), "7 skipped") {
		t.Fatalf("pause lines %v", v5Sec(R, "pause").Lines)
	}
	M.FeedJSONL([][]byte{[]byte(`{"ev":"presend_live_ledger_mode","ok":true,"pause_window":"on","window":"00:20-00:25","tz":"PKT","t":1794511200000000000}`)})
	if P := M.V5.Report(1794511260000000000, nil, nil).Pause; !P.Active || P.NextEnd == 0 || T12(float64(P.NextEnd), false) != "12:25 AM" {
		t.Fatalf("active pause %+v", P)
	}
	R = M.V5.Report(1794423790000000000, nil, nil)
	if jget(v5Sec(R, "rearm_cap").JSON, "blocks") != 1 {
		t.Fatal("rearm cap")
	}
	ab := v5Sec(R, "ab46").JSON
	if rows := jget(ab, "rows").([]any); len(rows) != 1 {
		t.Fatalf("ab rows %v", rows)
	}
	pr := R.ProbeRows
	if len(pr) != 1 || pr[0].Probes != 2 || pr[0].Windows != 1 || pr[0].Would != 1 || pr[0].Priced {
		t.Fatalf("probes %+v", pr)
	}
	H := R.Hours
	var n, w int64
	for _, r := range H.Rows {
		n += r.Fills
		w += r.Wins
	}
	if n != 2 || w != 1 || H.Rows[0].BigL != 1 || H.Rows[0].BigW != 1 { // 00:xx PKT: -30% and +25%
		t.Fatalf("hours %d %d %+v", n, w, H.Rows[0])
	}
	if b := v5Sec(R, "big").JSON; jget(b, "n") != 2 {
		t.Fatalf("big %v", b.Vals)
	}
	if l := M.V5.land["client FireBAM"]; l == nil || l.n != 1 || l.le[0] != 1 || M.V5.land["ALL"].le[1] != 1 {
		t.Fatal("landing")
	}
	// Filters: the dip47 LIVE rows and the measured LOG rows
	FR := M.Filt.Report("", nil)
	for _, k := range []string{"grp_t2", "rearm_cap", "pause_window", "grpsign", "rfleet"} {
		r, ok := FR.Row(k)
		if !ok || r.Blocked == 0 {
			t.Fatalf("filters row %s %+v", k, r)
		}
	}
}

// TestV5Old: a run without dip46 / dip47 records has no rule sections (the snapshot / JSON as v4).
func TestV5Old(t *testing.T) {
	M := NewModel(0, 100)
	M.FeedJSONL([][]byte{[]byte(`{"ev":"presend_attempt_land","ms_send_to_first_rx":30.0,"client":"FireBAM","path":"helius-ps"}`)})
	R := M.V5.Report(0, nil, nil)
	if len(R.Rule) != 0 || R.FvOn || R.Pause != nil {
		t.Fatalf("rule sections on an old run: %d", len(R.Rule))
	}
}

// TestV5ProbeR83: r83's probes priced on the exported chain tape = probe_check.py (DIPMON_DATA + the tape file).
func TestV5ProbeR83(t *testing.T) {
	run := os.Getenv("DIPMON_DATA") + "/ams_r83/dip_ams_r83.jsonl"
	tp := "/home/it/sniper-data/dipmon5/r83_probe_tape.jsonl"
	if _, err := os.Stat(run); err != nil {
		t.Skip("no r83")
	}
	if _, err := os.Stat(tp); err != nil {
		t.Skip("no r83 tape")
	}
	tape, err := LoadProbeTape(tp)
	if err != nil {
		t.Fatal(err)
	}
	M := NewModel(0, 100)
	if err := eachLine(run, func(l []byte) { M.FeedJSONL([][]byte{l}) }); err != nil {
		t.Fatal(err)
	}
	R := M.V5.Report(0, tape, nil)
	// probe_check.py r83 (sniper-dip46 ops/probe46): filter probes windows would win lose net
	want := map[string][6]float64{"botdepth_withheld": {306, 54, 6, 2, 4, -0.3399}, "create_slot": {901, 113, 13, 3, 10, -0.7417},
		"mint_ledger": {20, 3, 1, 0, 1, -0.0444}, "young_age": {22, 4, 1, 1, 0, 0.0398}, "lone_whale": {88, 10, 0, 0, 0, 0}}
	got := 0
	for _, r := range R.ProbeRows {
		x, ok := want[r.Filter]
		if !ok {
			continue
		}
		got++
		if float64(r.Probes) != x[0] || float64(r.Windows) != x[1] || float64(r.Would) != x[2] || float64(r.Win) != x[3] || float64(r.Lose) != x[4] || F(r.Net, 4) != F(x[5], 4) {
			t.Errorf("%s: %+v want %v", r.Filter, r, x)
		}
	}
	if got != len(want) {
		t.Fatalf("rows %d", got)
	}
}

// TestFilterModes (r84 fix): the Filters rows follow each filter's live / log mode (start flags, dip43 / dip47 control keys,
// the filter state); a record without a whale / holder key leaves those modes alone.
func TestFilterModes(t *testing.T) {
	M := NewModel(0, 100)
	feed := func(r string) { M.FeedJSONL([][]byte{[]byte(r)}) }
	feed(`{"ev":"run_start","presend_live":{"wh_loss":"2:0.3","ledger_control":"/x","dip43":{"mint_ledger":0.1,"mint_ledger_live":true,"fanout":10,"fanout_live":false}}}`)
	feed(`{"ev":"presend_live_ledger_mode","ok":true,"whale":"log","holder":"live"}`)
	feed(`{"ev":"presend_live_ledger_mode","ok":true,"dip46":{"probe46":true}}`)
	feed(`{"ev":"presend_live_skip","why":"mint_ledger","trig":{"sig":"S1","mint":"M1","t":1}}`)
	feed(`{"ev":"presend_live_fill","w":5,"mint":"M5","kind":"rearm","t":2,"mint_ledger":{"n":2,"worst":-103846188,"would_block":true}}`)
	feed(`{"ev":"presend_live_realized","w":5,"mint":"M5","kind":"rearm","pnl":-50000000}`)
	R := M.Filt.Report("", nil)
	name := func(k string) string {
		r, ok := R.Row(k)
		if !ok {
			return ""
		}
		return r.Name
	}
	if n := name("mint_ledger"); n != "mint ledger [live]" {
		t.Fatalf("live row %q", n)
	}
	if n := name("mintled"); n != "mint ledger would [live]" {
		t.Fatalf("log row %q", n)
	}
	if n := name("fanout"); n != "fan-out (log)" && n != "" {
		t.Fatalf("fan-out %q", n)
	}
	if !M.Filt.modeSeen("whale", "log") || M.Filt.modeWh || name("wh_logmode") == "" {
		t.Fatalf("whale mode %v (a dip46 record must not flip it to live)", M.Filt.modes["whale"])
	}
	feed(`{"ev":"presend_live_ledger_mode","ok":true,"dip43":{"mint_ledger":"log","create_slot":"log"},"was":{"dip43":{"mint_ledger":"live","create_slot":"live"}}}`)
	feed(`{"ev":"presend_live_filter_state","fv":1,"fh":"x","src":"control","state":{"mint_ledger":"log","create_slot":"live"},"changed":{}}`)
	R = M.Filt.Report("", nil)
	if n := name("mint_ledger"); n != "mint ledger [live→log]" {
		t.Fatalf("switched %q", n)
	}
	if n := name("create_slot"); n != "create-slot skip [log→live]" {
		t.Fatalf("A9 %q", n)
	}
	// a run where the ledger was log only: the v4 name
	M2 := NewModel(0, 100)
	M2.FeedJSONL([][]byte{[]byte(`{"ev":"run_start","presend_live":{"dip43":{"mint_ledger":0.1,"mint_ledger_live":false}}}`),
		[]byte(`{"ev":"presend_live_fill","w":5,"mint":"M5","kind":"t2","t":2,"mint_ledger":{"n":2,"worst":-1,"would_block":true}}`)})
	if r, ok := M2.Filt.Report("", nil).Row("mintled"); !ok || r.Name != "mint ledger (log)" {
		t.Fatalf("log-only %+v", r)
	}
	if _, ok := M2.Filt.Report("", nil).Row("mint_ledger"); ok {
		t.Fatal("a LIVE row on a log-only run")
	}
}

// TestTradingState (r85): the breaker's pause shows until its end, ends early on the control key's switch to log, then IDLE.
func TestTradingState(t *testing.T) {
	M := NewModel(0, 100)
	feed := func(r string) { M.FeedJSONL([][]byte{[]byte(r)}) }
	feed(`{"ev":"run_start","t":1794441900000000000,"presend_live":{"breaker":"2:0.1:30:60"}}`)
	feed(`{"ev":"dump","t":1794441940000000000}`)
	feed(`{"ev":"presend_live_arm","w":1,"kind":"t2","trig":{"sig":"S","mint":"M","t":1794443700000000000}}`)
	feed(`{"ev":"dump","t":1794443747000000000}`)
	feed(`{"ev":"presend_live_breaker","last_mint":"4h9QNMRirGeXMScgBPY9DaQy5BqseWrhU4aVPHgepump","last_pnl":-137557522,"losses":2,"pause_min":60,"trips":1}`)
	S := M.Sess(0)
	v := &View{Running: true, Status: "RUNNING", Cur: S, D43: &D43Report{}}
	st, sev, bl := TradingState(v, M, S, 1794444000000000000) // 5:40 AM
	if st != "PAUSED: breaker until 6:35 AM" || sev != "bad" || len(bl) != 1 || !strings.Contains(bl[0].Text, "56 min left") {
		t.Fatalf("paused: %q %q %+v", st, sev, bl)
	}
	feed(`{"ev":"presend_live_ledger_mode","ok":true,"dip43":{"breaker":"log"},"was":{"dip43":{"breaker":"live"}},"t":1794446617996460147}`)
	st, _, bl = TradingState(v, M, S, 1794446640000000000) // 6:24 AM
	if !strings.HasPrefix(st, "IDLE") || !strings.Contains(TradingLine(bl), "breaker → log at 6:23 AM") {
		t.Fatalf("after log: %q %v", st, TradingLine(bl))
	}
	if st, _, _ := TradingState(&View{Running: false, Cur: S}, M, S, 1794444000000000000); st != "" {
		t.Fatal("an ended run has no trading state")
	}
}

// TestD48D49: the fresh-holders skip, the follower flow and the rival gate (record shapes from sniper-dip49 84807f7a; r86 / r87).
func TestD48D49(t *testing.T) {
	M := NewModel(0, 100)
	for _, r := range []string{
		`{"ev":"presend_live_filter_state","fv":0,"fh":"a","src":"start","state":{"fresh_skip":"live","fresh_skip_spec":"35:20","fresh_skip_ra_def":"f3","rival_gate":"live","rival_gate_spec":"0:2:1","flow_log":true},"changed":{}}`,
		`{"ev":"presend_live_skip","why":"fresh_holders","fresh":45.07,"fresh_n":5,"thr":35.0,"trig":{"sig":"S1","mint":"MintA","t":1794450000000000000}}`,
		`{"ev":"presend_live_skip","kind":"rearm","why":"fresh_holders","fresh":44.98,"fresh_n":5,"thr":20.0,"mint":"MintB","dump":{"t":1794450405101217459}}`,
		`{"ev":"presend_live_rival_gate","w":13,"mint":"MintC","kind":"t2","mode":"live","tries":187,"passed":163,"withheld":24,"would":0,"open":0,"rivals_min":0,"dev_age_h":null,"dev_age_src":"error","t":1794455422198179699}`,
		`{"ev":"presend_live_fill","w":1,"mint":"MintD","kind":"t2","spend":1000000000,"t":1794455000000000000,"rival_gate":{"rivals":2,"dev_age_h":0.5,"young":true,"dev_age_src":"rpc","on":"log","blocked":true},"fresh_skip":{"n":5,"pct":40.0,"thr":35.0,"would_skip":true}}`,
		`{"ev":"presend_live_flow","w":1,"mint":"MintD","kind":"t2","closed":"exit","per_slot":[{"dslot":0,"buy_sol":{"bots":0.7,"fleet":0,"retail":0,"rivals":0,"dumper":0,"us":0},"sell_sol":{"bots":0,"fleet":0,"retail":0,"rivals":0,"dumper":5.6,"us":0}},{"dslot":2,"buy_sol":{"bots":0,"fleet":1.0,"retail":0,"rivals":0,"dumper":0,"us":0},"sell_sol":{}}],"tot1":{"buy":0.7,"sell":5.6},"tot2":{"buy":1.7,"sell":5.6}}`,
		`{"ev":"presend_live_realized","w":1,"mint":"MintD","kind":"t2","pnl":-100000000}`,
	} {
		M.FeedJSONL([][]byte{[]byte(r)})
	}
	if M.Bad != 0 {
		t.Fatalf("bad %d", M.Bad)
	}
	R := M.V5.Report(0, nil, nil)
	f := R.Fill(1, "MintD")
	if f == nil || f.FlowCell() != "0.70" || f.RivalCell() != "2/0.5h" || f.Flow.Buy2["fleet"] != 1.0 || !f.Fresh.Would {
		t.Fatalf("fill %+v", f)
	}
	if j := v5Sec(R, "fresh_skip").JSON; jget(j, "skips_t2") != 1 || jget(j, "skips_ra") != 1 || jget(j, "pnl_would") != int64(-100000000) {
		t.Fatalf("fresh %v", j.Vals)
	}
	if j := v5Sec(R, "rival_gate").JSON; jget(j, "windows_withheld") != int64(1) || jget(j, "tries_withheld") != int64(24) || jget(j, "fills_block") != int64(1) {
		t.Fatalf("rival %v", j.Vals)
	}
	if v5Sec(R, "flow") == nil {
		t.Fatal("flow")
	}
	FR := M.Filt.Report("", nil)
	for _, k := range []string{"fresh_holders", "rgate_live"} {
		if r, ok := FR.Row(k); !ok || r.Blocked == 0 {
			t.Fatalf("row %s %+v", k, r)
		}
	}
}
