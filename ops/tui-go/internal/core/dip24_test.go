package core

import (
	"strings"
	"testing"
)

// The dip24 lines: real lines of AMS r36 (10-29), and the pause / resume / lock-fire lines in the engine's own format
// (src/bin/snipe_engine/pslive.rs, dipmode.rs).
var r36Start = []string{
	`DIP LIVE | model IMIT1 tier wider (score >= 0.2109) | exit TP off / SL -50% / 5 slots | guard x1.05 | spend 0.696 SOL | max buys 0 | max open 1 | loss cap 0.500 SOL | 0 min`,
	`DIP LIMITS: time no time limit | regular buys unlimited | per-buy cap 0.731 SOL | kill switch -0.5000 SOL from the start balance | profit lock give back max(0.650 SOL, 30% of the peak profit) | pre-send fills unlimited | pre-send fee budget 1.0000 SOL per rolling 24 h (pauses, never stops)`,
	`DIP REGULAR PAPER: decided as live, NEVER sent; paper landing 60 ms; regular_paper_* records`,
	`DIP OBSERVATORY (LOG ONLY, own thread, never sends): rearm, hold, watch, migration, blink, backrun, select, feedrace, inslot -> /root/prod/runs/dip_ams_r36.obs.jsonl`,
	`START BALANCE 8.172076 SOL; kill switch below 7.672076 SOL`,
	`PROFIT LOCK ON: give back max(0.6500 SOL, 30% of the peak profit); floor now -0.5000 SOL from the start (never below the kill switch's -0.5000)`,
	`DIP PRESEND LIVE (REAL attempts) | T2 whale >= 6% -> window 10 slots from +50 ms (create-slot triggers skipped) | 8 attempts per slot (27 ms apart), 0.696 SOL, limit = latest price x 0.88, deadline slot + 1 | CU 120000 x 1000 uL (a failed attempt 5120 lamports) | routes default=helius-ps(fast) | caps: unlimited fills, fees 1.0000 SOL per rolling 24 h (pause), 40 attempts/s (40 per path) | one position on | exit 2 slots or 200 ms after the fill (dip22, first) / TP +20% / SL -20%`,
}

const r36Status = `  DIP status: tokens 1069 dumps 6291 in-envelope 2891 picks 74 fired 0 closed 0 open 0 slot 462675083 skipped {"far_leader": 55} | PRESEND LIVE: triggers 359 armed 151 (now 0) skips {"quiet": 34} | fills 47/0 (late 3 unexpected 0) exits 47 closed 47 unsold 0 | failed-attempt fees 0.036531/1.000000 SOL, fill fees 0.000241, tips 0.009400 | QUIET: skips 34 (would-skip in the warm-up 0) stops 17 | arm rule on | signals 359 (6.1/40.5 us p50/p99) | fees 24 h 0.0365/1.0000 SOL | REGULAR PAPER: picks 6, fills 0 (no-fill 6), exits 0, paper P&L +0.0000 SOL gross / -0.0030 net, open 0 | lock: peak +0.4677, floor -0.1823 (0.6500 give-back), run PnL +0.3479 | OBS: sent 6223589 dropped 0 queued 0 done 6223589 | rearm windows 107 fills 88 | hold 47 | watch 4092 | mig 110 | blink 1453 | backrun 6304 | select 3132 | race 85859 | inslot 6321 | 107929 records 41.0 MB in 1 part(s), p99 29.1 us/msg, ~17 MB`

func feedStrs(M *Model, ls ...string) {
	b := make([][]byte, len(ls))
	for i, s := range ls {
		b[i] = []byte(s)
	}
	M.FeedLog(b)
}

func d24View(M *Model, running bool) *View {
	ctx := &Ctx{Src: &Source{Model: M, TJ: NewTail("/nonexistent"), TL: NewTail("/nonexistent")}, Price: NewPrice(100, false), AssumeRunning: running}
	return BuildView(ctx, -1)
}

func TestDip24Lines(t *testing.T) {
	M := NewModel(0, 100)
	feedStrs(M, append(append([]string{}, r36Start...), r36Status)...)
	if M.Bad != 0 {
		t.Fatalf("bad lines %d", M.Bad)
	}
	S := M.Sessions[0]
	d := S.D24
	if !d.Limits || !d.NoTime || !d.RegUnl || !d.PSFillsUnl {
		t.Fatalf("limits: %+v", d)
	}
	if !d.HasLock || d.LockM != 650_000_000 || d.LockF != 0.30 {
		t.Fatalf("lock setting: %d %v", d.LockM, d.LockF)
	}
	if !d.HasLockSt || d.LockPeak != 467_700_000 || d.LockFloor != -182_300_000 || d.LockPnL != 347_900_000 {
		t.Fatalf("lock state: %+v", d)
	}
	if !d.HasFee24 || d.Fee24 != 36_500_000 || d.Bud24 != 1_000_000_000 || d.FeePaused {
		t.Fatalf("fee 24 h: %d/%d paused %v", d.Fee24, d.Bud24, d.FeePaused)
	}
	if d.RegMode != "paper" || !d.HasRegP || d.RegP.Picks != 6 || d.RegP.NoFill != 6 || d.RegP.Net != -0.003 {
		t.Fatalf("regular: %q %+v", d.RegMode, d.RegP)
	}
	o := d.Obs
	if !o.On || len(o.Names) != 9 || o.Out != "/root/prod/runs/dip_ams_r36.obs.jsonl" || !o.HasLine || o.Sent != 6223589 || !o.HasRec || o.Records != 107929 {
		t.Fatalf("obs: %+v", o)
	}
	if len(o.Counts) != 9 || o.Counts[0].K != "rearm" || o.Counts[0].N != 107 || o.Counts[0].Fills != 88 || o.Counts[8].K != "inslot" || o.Counts[8].N != 6321 {
		t.Fatalf("obs counts: %+v", o.Counts)
	}
	v := d24View(M, true)
	if !v.NoTimeLimit || v.Build != "dip24" {
		t.Fatalf("no time limit %v build %s", v.NoTimeLimit, v.Build)
	}
	if L := v.Lock; !L.On || !L.Engine || L.Floor != -182_300_000 || L.Dist != 347_900_000+182_300_000 {
		t.Fatalf("lock view: %+v", L)
	}
	for _, a := range v.Alerts { // nothing near: no lock / fee / max-fills alert
		if strings.Contains(a.Text, "lock") || strings.Contains(a.Text, "fills") || strings.Contains(a.Text, "fees") {
			t.Fatalf("alert %q", a.Text)
		}
	}
	txt := SnapshotText(v, &Ctx{Src: &Source{Model: M, TJ: NewTail("/x"), TL: NewTail("/x")}}, 200)
	for _, want := range []string{"(no time limit)", "limits    time no limit, regular buys no limit, pre-send fills no limit, fee budget 24 h 0.0365/1.0000 SOL",
		"lock      give back max(0.650 SOL, 30% of the peak); peak +0.4677, stops below -0.1823, run P&L +0.3479 (0.530 SOL away)",
		"reg mode  paper: picks 6", "re-arm 107 windows / 88 fills", "INSLOT 6,321", "time no limit", "+ lock 0.65/30%", "~ REG paper"} {
		if !strings.Contains(txt, want) {
			t.Errorf("snapshot lacks %q:\n%s", want, txt)
		}
	}
	if v.PSCfg["fills_unlimited"] != true {
		t.Fatal("PS caps: unlimited fills not parsed")
	}
	if _, ok := v.PSCfg["max_fills"]; ok {
		t.Fatal("unlimited fills must not set max_fills")
	}
	if fb, ok := v.PSCfg["fee_budget"].(Num); !ok || fb.Int() != 1_000_000_000 {
		t.Fatalf("PS fee budget %v", v.PSCfg["fee_budget"])
	}

	// the fee budget pauses, then resumes (pslive.rs format); the status part's PAUSED flag too
	feedStrs(M, `  PRESEND LIVE PAUSED (fee budget): failed-attempt fees of the last 24 h 1.000120 SOL >= 1.000000 SOL: NO NEW ATTEMPTS until they roll back under (pause #1; the run goes on)`)
	d = M.Sessions[0].D24
	if !d.FeePaused || d.Fee24 != 1_000_120_000 || d.FeePauses != 1 {
		t.Fatalf("pause: %+v", d)
	}
	v = d24View(M, true)
	if !hasAlert(v, "pre-send PAUSED") || !strings.Contains(SnapshotText(v, &Ctx{Src: &Source{Model: M, TJ: NewTail("/x"), TL: NewTail("/x")}}, 200), "PAUSED") {
		t.Fatal("PAUSED not shown")
	}
	feedStrs(M, `  PRESEND LIVE RESUMED (fee budget): failed-attempt fees of the last 24 h 0.990000 SOL < 1.000000 SOL`)
	if d = M.Sessions[0].D24; d.FeePaused || d.Fee24 != 990_000_000 {
		t.Fatalf("resume: %+v", d)
	}
	feedStrs(M, strings.Replace(r36Status, "fees 24 h 0.0365/1.0000 SOL", "fees 24 h 1.0001/1.0000 SOL PAUSED (pauses 2)", 1))
	if d = M.Sessions[0].D24; !d.FeePaused || d.FeePauses != 2 {
		t.Fatalf("status PAUSED: %+v", d)
	}

	// the profit lock fires (dipmode.rs format): STOPPING, how it ended, the alert
	feedStrs(M, `  PROFIT LOCK pending confirmation: run PnL -0.190000 below the floor -0.182300 (peak +0.467700; re-check next poll)`,
		`  PROFIT LOCK: peak +0.467700, floor -0.182300, balance 7.982076 (run PnL -0.190000) -> stopping: no new buys of any kind; open positions finish their exit`)
	d = M.Sessions[0].D24
	if !d.LockFired || d.LockPending != 1 || d.LockFire != [4]int64{467_700_000, -182_300_000, 7_982_076_000, -190_000_000} {
		t.Fatalf("lock fire: %+v", d)
	}
	v = d24View(M, true)
	if v.Status != "STOPPING" || v.HowEnded != "profit lock" || !hasAlert(v, "PROFIT LOCK stopped") {
		t.Fatalf("lock fired: %s %q %+v", v.Status, v.HowEnded, v.Alerts)
	}
	if !strings.Contains(SnapshotText(v, &Ctx{Src: &Source{Model: M, TJ: NewTail("/x"), TL: NewTail("/x")}}, 200), "STOPPED by profit lock") {
		t.Fatal("snapshot: stopped by profit lock")
	}
	j := SnapshotJSON(v, &Ctx{Src: &Source{Model: M, TJ: NewTail("/x"), TL: NewTail("/x")}}, nil)
	if !strings.Contains(j, `"dip24": {`) || !strings.Contains(j, `"fired": true`) || !strings.Contains(j, `"regular_mode": "paper"`) {
		t.Fatalf("json: %s", j[strings.Index(j, `"dip24"`):])
	}
}

// TestDip24Variants: a capped dip24 run (60 min, 200 fills, lock none, regular off / live) and the lock computed from our
// own P&L before the engine's first status line.
func TestDip24Variants(t *testing.T) {
	M := NewModel(0, 100)
	feedStrs(M, `DIP LIVE | model IMIT1 tier wider | exit TP off / SL -50% / 5 slots | guard x1.05 | spend 0.696 SOL | max buys 5 | loss cap 0.500 SOL | 60 min`,
		`DIP LIMITS: time 60 min | regular buys 5 | per-buy cap 0.731 SOL | kill switch -0.5000 SOL from the start balance | profit lock none | pre-send fills 200 | pre-send fee budget 0.4000 SOL per rolling 24 h (pauses, never stops)`,
		`DIP REGULAR OFF: no regular buys (dumps still logged; would-be picks as pick_skip regular_off)`)
	d := M.Sessions[0].D24
	if d.NoTime || d.RegUnl || d.PSFillsUnl || d.HasLock || !d.LockOff || d.RegMode != "off" || d.Bud24 != 400_000_000 {
		t.Fatalf("capped: %+v", d)
	}
	v := d24View(M, true)
	if v.NoTimeLimit || v.Lock.On || v.ItemByKey("lock").State != "off" || v.ItemByKey("regmode").Short != "REG off" {
		t.Fatalf("capped view: %v %+v", v.NoTimeLimit, v.Lock)
	}
	if it := v.ItemByKey("limits"); it == nil || it.Full != "regular buys 5 · pre-send fills 200" && it.Full != "regular buys 5 | pre-send fills 200" {
		t.Fatalf("limits item %+v", it)
	}
	M2 := NewModel(0, 100)
	feedStrs(M2, `DIP LIVE | spend 0.696 SOL | max buys 0 | loss cap 0.500 SOL | 0 min`, `DIP REGULAR LIVE (as before)`,
		`START BALANCE 8.0 SOL; kill switch below 7.5 SOL`, `PROFIT LOCK ON: give back max(0.1000 SOL, 50% of the peak profit); floor now -0.1000 SOL from the start (never below the kill switch's -0.5000)`)
	v = d24View(M2, true)
	if !v.Lock.On || v.Lock.Engine || v.Lock.Floor != -100_000_000 || v.RegModeOf() != "live" {
		t.Fatalf("lock before a status line: %+v", v.Lock)
	}
	if LockFloor(1_000_000_000, 100_000_000, 0.5, 500_000_000, true) != 500_000_000 || LockFloor(0, 650_000_000, 0.3, 500_000_000, true) != -500_000_000 {
		t.Fatal("LockFloor")
	}
}

// TestNoDip24OnOldLines: a dip20 log gets none of it (older runs render as before).
func TestNoDip24OnOldLines(t *testing.T) {
	M := NewModel(0, 100)
	feedStrs(M, `DIP LIVE | model IMIT1 tier wider | exit TP off / SL -50% / 5 slots | guard x1.05 | spend 0.35 SOL | max buys 1000 | loss cap 0.500 SOL | 130 min`,
		`START BALANCE 8.0 SOL; kill switch below 7.5 SOL`)
	v := d24View(M, true)
	if M.Sessions[0].D24.Any() || v.NoTimeLimit || v.Lock.On || v.D24.Any() {
		t.Fatal("dip24 state on an old log")
	}
	for _, k := range []string{"lock", "fee24", "regmode", "limits", "obs"} {
		if v.ItemByKey(k) != nil {
			t.Fatalf("item %s on an old log", k)
		}
	}
	if strings.Contains(SnapshotJSON(v, &Ctx{Src: &Source{Model: M, TJ: NewTail("/x"), TL: NewTail("/x")}}, nil), "dip24") {
		t.Fatal("dip24 JSON on an old log")
	}
}

func hasAlert(v *View, s string) bool {
	for _, a := range v.Alerts {
		if strings.Contains(a.Text, s) {
			return true
		}
	}
	return false
}
