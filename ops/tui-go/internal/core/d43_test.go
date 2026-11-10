package core

import (
	"encoding/json"
	"flag"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

var update43 = flag.Bool("update43", false, "rewrite the dip43 golden snapshots (testdata/golden43)")

// d43Recs: a small dip43d run: two windows (w 1 odd = G snipe-guard, w 2 even = L Lighthouse + the CURVE band), the tries,
// their landings (a floors abort, a curve_deep abort, a deadline), two fills with CASCADE, their exits (cheap timer A/B)
// and realized P&L, a true-balance snapshot, a fam read, the send accounting and a hot switch of the band to log.
var d43Recs = []string{
	`{"ev":"run_start","presend_live":{"spend":1000000000}}`,
	`{"ev":"presend_live_dip43","cfg":{"cascade":true,"tbal":true},"t":1794344688513941694}`,
	`{"ev":"presend_live_arm","w":1,"mint":"MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","trig":{"sig":"trigA","mint":"MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","t":1794344700000000000},"spend":1000000000,"mint_ledger":{"n":0,"worst":0,"would_block":false}}`,
	`{"ev":"presend_attempt","w":1,"n":1,"sig":"sA1","cu_price":50000,"guard":{"age_ms":45,"arm":"G","curve_hi":985359472259926,"mode":"holders","n_floors":6},"tier":{"client":true,"cu_price":50000,"i":1,"n":1,"on":true},"mint":"MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","dry":false}`,
	`{"ev":"presend_attempt","w":1,"n":2,"sig":"sA2","cu_price":50000,"guard":{"age_ms":50,"arm":"G","curve_hi":985359472259926,"mode":"holders","n_floors":6},"tier":{"client":true,"cu_price":50000,"i":2,"n":1,"on":true},"mint":"MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","dry":false}`,
	`{"ev":"presend_attempt","w":1,"n":3,"sig":"sA3","cu_price":1000,"guard":{"arm":"G","mode":"holders","n_floors":0,"reason":"no_snapshot","curve_hi":985359472259926},"tier":{"client":false,"on":false},"mint":"MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","dry":false}`,
	`{"ev":"presend_attempt_land","w":1,"sig":"sA1","mint":"MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","res":"guard_abort","fee":10500,"guard_abort":{"kind":"floors","cnt":2,"gap_bucket":0}}`,
	`{"ev":"presend_attempt_land","w":1,"sig":"sA3","mint":"MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","res":"deadline","fee":5100,"guard_abort":{"kind":"deadline","cnt":0,"gap_bucket":1}}`,
	`{"ev":"presend_attempt_land","w":1,"sig":"sA2","mint":"MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","res":"ok","fee":10500}`,
	`{"ev":"presend_live_fill","w":1,"mint":"MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","sig":"sA2","p_sign":0.0001,"p_entry_pre":0.000088,"cascade":{"ga":{"abort":true,"below":2,"n":6},"gd":{"abort":false,"below":1,"n":5}},"mint_ledger":{"n":0,"worst":0,"would_block":false},"fanout":{"flag":false,"n":3,"read":true},"t":1794344701000000000}`,
	`{"ev":"presend_live_exit","w":1,"mint":"MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","pid":1,"why":"time-limit","timer_sell":{"arm":"cheap","cu_price":500000,"ab":true}}`,
	`{"ev":"presend_live_realized","w":1,"mint":"MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","pnl":-20000000}`,
	`{"ev":"presend_live_arm","w":2,"kind":"rearm","mint":"MintBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB","spend":800000000,"fanout":{"flag":true,"n":12,"read":true}}`,
	`{"ev":"presend_attempt","w":2,"n":1,"sig":"sB1","kind":"rearm","cu_price":50000,"guard":{"arm":"L","curve_hi":7.5e14,"mode":"deadline","n_floors":0},"mint":"MintBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB","dry":false}`,
	`{"ev":"presend_attempt","w":2,"n":2,"sig":"sB2","kind":"rearm","cu_price":50000,"guard":{"arm":"L","curve_hi":7.5e14,"mode":"deadline","n_floors":0},"mint":"MintBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB","dry":false}`,
	`{"ev":"presend_attempt_land","w":2,"sig":"sB1","mint":"MintBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB","res":"guard_abort","fee":10500,"guard_abort":{"kind":"curve_deep","cnt":0,"gap_bucket":5}}`,
	`{"ev":"presend_attempt_land","w":2,"sig":"sB2","mint":"MintBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB","res":"ok","fee":10500}`,
	`{"ev":"presend_live_fill","w":2,"kind":"rearm","mint":"MintBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB","sig":"sB2","p_sign":0.0001,"p_entry_pre":0.00007,"cascade":{"ga":{"abort":false,"below":0,"n":6}},"fanout":{"flag":true,"n":12,"read":true},"t":1794344702000000000}`,
	`{"ev":"presend_live_exit","w":2,"mint":"MintBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB","pid":2,"why":"time-limit","timer_sell":{"arm":"base","cu_price":null,"ab":true}}`,
	`{"ev":"presend_live_realized","w":2,"mint":"MintBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB","pnl":30000000}`,
	`{"ev":"presend_live_tbal_snap","mint":"MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","ms":5.1,"n":6,"slot":10,"w":1}`,
	`{"ev":"presend_live_fam","mint":"MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","w":1,"err":null,"lag_ms":80,"read_slot":8,"arm_slot":10,"fanout":{"act":"none","flag":false,"n":3,"thr":10}}`,
	`{"ev":"presend_live_disarm","w":1,"why":"filled","not_sent":{"due":10,"sent":3,"rate_global":4,"rate_path":0,"other":3}}`,
	`{"ev":"presend_live_unseen_fee","w":1,"unseen":1,"fee_est":5110,"total_unseen":1,"total_fee_est":5110}`,
	`{"ev":"presend_live_ledger_mode","ok":true,"dip43":{"curve_deep":"log"},"was":{"dip43":{"curve_deep":"live"}},"t":1794344800000000000}`,
	`{"ev":"presend_live_fpnb_strict","w":1,"mint":"MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","score":0.4,"thr":0.3}`,
}

const d43Guard = "GUARD (dip43 snipe-guard) holders 6:0.9:1:1 (abort when more than 1 of the top 6 below 90%), max snapshot age 5000 ms; program X; " +
	"A/B by window parity (odd: snipe-guard, even: Lighthouse); CURVE BAND LIVE (control key curve_deep): a try aborts when the price is >= 42% under its signing price, on EVERY window"

func d43Model(t *testing.T) *Model {
	M := NewModel(0, 100)
	M.FeedLog([][]byte{[]byte(d43Guard), []byte("DIP43-B B2 FEE TIER: ON: every 1th try of a window-slot at CU price 50000 uL"),
		[]byte("DIP43-B B4 CHEAP TIMER SELLS: ON: time-limit / time-ms sells at 500000 uL")})
	var ls [][]byte
	for _, r := range d43Recs {
		ls = append(ls, []byte(r))
	}
	M.FeedJSONL(ls)
	if M.Bad != 0 {
		t.Fatalf("bad %d", M.Bad)
	}
	return M
}

func TestD43Report(t *testing.T) {
	M := d43Model(t)
	R := M.D43.Report()
	if R == nil {
		t.Fatal("no dip43 report")
	}
	D := R.A
	if D.guardMode != "holders" || D.guardSpec != "6:0.9:1:1" || !D.guardAB || !D.bandOn || !D.bandLive || D.bandD != 42 {
		t.Fatalf("banner: mode %q spec %q ab %v band %v %v %v", D.guardMode, D.guardSpec, D.guardAB, D.bandOn, D.bandLive, D.bandD)
	}
	G, L := D.arms["G"], D.arms["L"]
	if G == nil || L == nil || G.Tries != 3 || G.Fills != 1 || G.Real != -20000000 || G.Res["guard_abort"] != 1 || G.Res["deadline"] != 1 || G.FeeFailed != 15600 ||
		L.Tries != 2 || L.Fills != 1 || L.Real != 30000000 || L.Wins != 1 {
		t.Fatalf("arms G %+v L %+v", G, L)
	}
	if D.aborts["floors"].N != 1 || D.aborts["curve_deep"].N != 1 || D.aborts["deadline"].N != 1 || len(D.deepW) != 1 || D.floors[6] != 2 || D.reasons["no_snapshot"] != 1 {
		t.Fatalf("aborts / floors %v %v %v", D.aborts, D.floors, D.reasons)
	}
	if D.bandTry != 5 || len(D.bandChanges) != 1 || D.bandChanges[0].now != "log" {
		t.Fatalf("band tries %d changes %v", D.bandTry, D.bandChanges)
	}
	if D.cuTries[50000] != 4 || D.cuTries[1000] != 1 || D.cuFee[1000] != 5100 || D.tierOn != 2 || D.notSent["due"] != 10 || D.unseenFee != 5110 {
		t.Fatalf("send: cu %v fee %v tier %d ns %v unseen %d", D.cuTries, D.cuFee, D.tierOn, D.notSent, D.unseenFee)
	}
	if x := D.exitArms["timer_sell"]; x["cheap"].N != 1 || x["cheap"].Pnl != -20000000 || x["base"].Pnl != 30000000 {
		t.Fatalf("exit arms %+v %+v", x["cheap"], x["base"])
	}
	fa, fb := R.Fill(1, "MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"), R.Fill(2, "MintBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB")
	if fa == nil || fb == nil || fa.Arm != "G" || fa.Floors != 6 || fa.GA != "abort" || !fa.HasDepth || fa.DepthPct < 11.99 || fa.DepthPct > 12.01 || fa.TimerArm != "cheap" ||
		fb.Arm != "L" || fb.GA != "pass" || !fb.Fanout || fb.Kind != "RA" {
		t.Fatalf("fills %+v %+v", fa, fb)
	}
	if b := fa.Brief(); !strings.Contains(b, "arm G floors 6 band on depth 12.0% G-A abort (2/6 below)") || !strings.Contains(b, "timer cheap") {
		t.Fatalf("brief %q", b)
	}
	// the sections and the snapshot
	var keys []string
	for _, s := range R.Sections {
		keys = append(keys, s.Key)
	}
	if strings.Join(keys, ",") != "guard,band,tbal,send,exits,shadows" {
		t.Fatalf("sections %v", keys)
	}
	v := &View{D43: R}
	txt := strings.Join(d43Text(v), "\n")
	for _, w := range []string{"G snipe-guard   tries 3, fills 1 (333.3 / 1k tries), realized -0.0200", "band      LOG now (start LIVE)", "curve_deep aborts 1 in 1 windows, 1 mints",
		"CASCADE G-A on 2 fills: would abort 1 (realized -0.0200), pass 1 (realized +0.0300)", "cheap timer sells (B4)   base 1 exits, realized +0.0300 (1, 1 W) | cheap 1 exits",
		"unseen tries 1, their fees est. -0.000005", "FP strict would-blocks 1 in 1 windows"} {
		if !strings.Contains(txt, w) {
			t.Errorf("snapshot lacks %q:\n%s", w, txt)
		}
	}
	d := &JObj{}
	d43JSON(v, d)
	var back map[string]any
	if err := json.Unmarshal([]byte(JSONDumps(d)), &back); err != nil {
		t.Fatal(err)
	}
	o := back["dip43"].(map[string]any)
	if g := o["guard"].(map[string]any)["arms"].(map[string]any)["G"].(map[string]any); g["tries"].(float64) != 3 || g["realized"].(float64) != -20000000 {
		t.Fatalf("json guard %v", g)
	}
	if len(o["fills"].([]any)) != 2 {
		t.Fatalf("json fills %v", o["fills"])
	}
}

// TestD43Registry: the LOG rule registry's rows on the fills (G-A, fan-out, FP strict), each fill once with every rule.
func TestD43Registry(t *testing.T) {
	M := d43Model(t)
	R := M.Filt.Report("")
	want := map[string][3]int{"ga": {1, 0, 1}, "gd": {0, 0, 0}, "fanout": {1, 1, 0}, "fpstrict": {1, 0, 1}, "mintled": {0, 0, 0}}
	for k, w := range want {
		r, ok := R.Row(k)
		if !ok || r.Type != "LOG" || r.Blocked != w[0] || r.WinN != w[1] || r.LoseN != w[2] {
			t.Errorf("row %s %+v (ok %v), want blocked/W/L %v", k, r, ok, w)
		}
	}
	it, ok := R.Flag(1, "MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
	if !ok || !it.Has("ga") || !it.Has("fpstrict") || it.Has("fanout") || !strings.Contains(it.Info(), "G-A floors (G-A 2 of the top 6 below 90%)") {
		t.Fatalf("item %+v %q", it, it.Info())
	}
	// v3 mode: no registry rows, no dip43 report
	NoV4 = true
	defer func() { NoV4 = false }()
	M2 := d43Model(t)
	if _, ok := M2.Filt.Report("").Row("ga"); ok || M2.D43.Report() != nil {
		t.Fatal("DIPMON_V3: registry rows / dip43 report still there")
	}
}

// TestD43Golden: the text snapshot and the JSON of AMS r76-r80 (the dip43 .. dip43d runs) against testdata/golden43 (local
// copies in DIPMON_DATA/ams_rNN; skipped without them; -update43 rewrites).
func TestD43Golden(t *testing.T) {
	dir := filepath.Join("testdata", "golden43")
	n := 0
	for _, r := range []string{"r76", "r77", "r78", "r79", "r80"} {
		p := filepath.Join(dataDir, "ams_"+r, "dip_ams_"+r+".jsonl")
		if _, err := os.Stat(p); err != nil {
			continue
		}
		n++
		src := NewSource(p, "", 0, 3000)
		src.LoadAll(LoadChunk, 0, nil)
		ctx := &Ctx{Src: src, Price: NewPrice(150, false), FixedNow: float64(src.Model.CurT)/1e9 + 600, GcrSeed: "none"}
		v := BuildView(ctx, -1)
		for _, g := range []struct{ name, got string }{{r + "_snapshot.txt", SnapshotText(v, ctx, 110)}, {r + "_snapshot.json", SnapshotJSON(v, ctx, nil)}} {
			got := g.got
			if strings.HasSuffix(g.name, ".txt") { // the files line names this machine's path
				got = stripFilesLine(got)
			} else {
				got = strings.ReplaceAll(got, dataDir, "DATA")
			}
			fp := filepath.Join(dir, g.name)
			if *update43 {
				os.MkdirAll(dir, 0o755)
				if err := os.WriteFile(fp, []byte(got), 0o644); err != nil {
					t.Fatal(err)
				}
				continue
			}
			want, err := os.ReadFile(fp)
			if err != nil {
				t.Errorf("%s: no golden (run with -update43)", g.name)
				continue
			}
			if string(want) != got {
				t.Errorf("%s differs from the golden:\n%s", g.name, firstDiffLine(string(want), got))
			}
		}
		if !strings.Contains(SnapshotText(v, ctx, 110), "dip43     ") {
			t.Errorf("%s: no dip43 section", r)
		}
	}
	if n == 0 {
		t.Skip("no local r76-r80 copies under " + dataDir)
	}
}

func stripFilesLine(s string) string {
	var out []string
	for _, l := range strings.Split(s, "\n") {
		if strings.HasPrefix(l, "files     ") {
			continue
		}
		out = append(out, l)
	}
	return strings.Join(out, "\n")
}

func firstDiffLine(a, b string) string {
	al, bl := strings.Split(a, "\n"), strings.Split(b, "\n")
	for i := 0; i < max(len(al), len(bl)); i++ {
		var x, y string
		if i < len(al) {
			x = al[i]
		}
		if i < len(bl) {
			y = bl[i]
		}
		if x != y {
			return "line " + itoa(i+1) + "\n  want: " + x + "\n  got:  " + y
		}
	}
	return ""
}
