package core

import "testing"

// TestFeeAB (dip37): the fee A/B block per arm x leader group: fills and positions from the fill records' fee_arm / fee_grp, their
// realized P&L and rent back, the failed tries' fees by THEIR arm x group (presend_attempt_land res != ok); a run without the fields
// has no block.
func TestFeeAB(t *testing.T) {
	M := NewModel(0, 100)
	feedJ := func(ls ...string) {
		b := make([][]byte, len(ls))
		for i, s := range ls {
			b[i] = []byte(s)
		}
		M.FeedJSONL(b)
	}
	// a pre-dip37 run: no fee fields, no block
	feedJ(`{"ev":"presend_live_fill","w":1,"mint":"M0","t":1000,"sol_in":400000000,"client":"AgaveBam"}`,
		`{"ev":"presend_live_realized","w":1,"mint":"M0","pnl":5000000}`,
		`{"ev":"presend_attempt_land","w":1,"mint":"M0","res":"6042","fee":5120,"t_send":1000}`)
	if s := FeeABOf(M.Sessions); s.On || len(s.Rows) != 0 {
		t.Fatalf("no fee fields: no block: %+v", s)
	}
	M = NewModel(0, 100)
	feedJ(
		// B on a fee leader: two positions (one win), one with rent back
		`{"ev":"presend_live_fill","w":11,"mint":"M1","t":2000,"sol_in":400000000,"client":"AgaveBam","fee_arm":"B","fee_grp":"fee","fee_b":true,"cu_price":20000,"cu_limit":120000,"tip":100000}`,
		`{"ev":"presend_live_realized","w":11,"mint":"M1","pnl":12000000,"fee_arm":"B","fee_grp":"fee"}`,
		`{"ev":"presend_live_ata_close","mint":"M1","ok":true,"delta":2000000}`,
		`{"ev":"presend_live_fill","w":13,"mint":"M3","t":3000,"sol_in":400000000,"client":"HarmonicAgave","fee_arm":"B","fee_grp":"fee"}`,
		`{"ev":"presend_live_realized","w":13,"mint":"M3","pnl":-4000000,"fee_arm":"B","fee_grp":"fee"}`,
		// B on a Jito leader (A's values): one position, not realized yet
		`{"ev":"presend_live_fill","w":15,"mint":"M5","t":4000,"sol_in":400000000,"client":"JitoLabs","fee_arm":"B","fee_grp":"jito","fee_b":false}`,
		// A on a fee leader: one loss
		`{"ev":"presend_live_fill","w":12,"mint":"M2","t":5000,"sol_in":400000000,"client":"AgaveBam","fee_arm":"A","fee_grp":"fee"}`,
		`{"ev":"presend_live_realized","w":12,"mint":"M2","pnl":-1000000,"fee_arm":"A","fee_grp":"fee"}`,
		// failed tries: by their own arm x group; ok / unseen / fee-less ones never
		`{"ev":"presend_attempt_land","w":11,"mint":"M1","res":"6042","fee":6800,"fee_arm":"B","fee_grp":"fee","t_send":1000}`,
		`{"ev":"presend_attempt_land","w":11,"mint":"M1","res":"deadline","fee":6800,"fee_arm":"B","fee_grp":"fee","t_send":1000}`,
		`{"ev":"presend_attempt_land","w":15,"mint":"M5","res":"6042","fee":5120,"fee_arm":"B","fee_grp":"jito","t_send":1000}`,
		`{"ev":"presend_attempt_land","w":12,"mint":"M2","res":"6042","fee":5120,"fee_arm":"A","fee_grp":"fee","t_send":1000}`,
		`{"ev":"presend_attempt_land","w":12,"mint":"M2","res":"6042","fee":5120,"fee_arm":"A","fee_grp":"other","t_send":1000}`,
		`{"ev":"presend_attempt_land","w":12,"mint":"M2","res":"ok","fee":5000,"fee_arm":"A","fee_grp":"fee","t_send":1000}`,
		`{"ev":"presend_attempt_land","w":12,"mint":"M2","res":"unseen","fee":0,"fee_arm":"A","fee_grp":"fee","t_send":1000}`,
	)
	if M.Bad != 0 {
		t.Fatalf("bad lines %d", M.Bad)
	}
	s := FeeABOf(M.Sessions)
	if !s.On {
		t.Fatal("the fee fields turn the block on")
	}
	type k struct{ a, g string }
	got := map[k]FeeABRow{}
	var order []k
	for _, r := range s.Rows {
		got[k{r.Arm, r.Grp}] = r
		order = append(order, k{r.Arm, r.Grp})
	}
	want := []k{{"A", "fee"}, {"A", "other"}, {"A", ""}, {"B", "fee"}, {"B", "jito"}, {"B", ""}}
	if len(order) != len(want) {
		t.Fatalf("rows %v", order)
	}
	for i := range want {
		if order[i] != want[i] {
			t.Fatalf("row order %v", order)
		}
	}
	bf := got[k{"B", "fee"}]
	if bf.Fills != 2 || bf.Pos != 2 || bf.Wins != 1 || bf.Pnl != 8_000_000 || bf.Rent != 2_000_000 || bf.FailN != 2 || bf.FailFees != 13_600 {
		t.Errorf("B fee: %+v", bf)
	}
	if bf.Net() != 8_000_000+2_000_000-13_600 {
		t.Errorf("B fee net %d", bf.Net())
	}
	if pf, ok := bf.PerFill(); !ok || pf != 5_000_000 {
		t.Errorf("B fee per fill %v %v", pf, ok)
	}
	if w, ok := bf.WinPct(); !ok || w != 50 {
		t.Errorf("B fee win %v", w)
	}
	bj := got[k{"B", "jito"}]
	if bj.Fills != 1 || bj.Pos != 0 || bj.FailN != 1 || bj.FailFees != 5_120 || bj.Net() != -5_120 {
		t.Errorf("B jito: %+v", bj)
	}
	if _, ok := bj.PerFill(); ok {
		t.Error("no realized position: no per-fill figure")
	}
	ao := got[k{"A", "other"}]
	if ao.Fills != 0 || ao.FailN != 1 || ao.FailFees != 5_120 {
		t.Errorf("A other (failed tries only): %+v", ao)
	}
	at, bt := got[k{"A", ""}], got[k{"B", ""}]
	if at.Fills != 1 || at.Pnl != -1_000_000 || at.FailN != 2 || at.FailFees != 10_240 || at.Net() != -1_010_240 {
		t.Errorf("A total: %+v", at)
	}
	if bt.Fills != 3 || bt.Pos != 2 || bt.FailN != 3 || bt.FailFees != 18_720 || bt.Net() != 8_000_000+2_000_000-18_720 {
		t.Errorf("B total: %+v", bt)
	}
	// the view carries it (the Engine tab's FEE A/B section)
	if v := viewAt(M, 6e12, false); !v.FAB.On || len(v.FAB.Rows) != 6 {
		t.Errorf("view: %+v", v.FAB)
	}
}
