package core

import (
	"bufio"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"sort"
	"testing"
)

// tuiDataDir holds run copies kept for these tests (r28: the first run with the latency the owner measured).
var tuiDataDir = func() string {
	if d := os.Getenv("DIPMON_TUI_DATA"); d != "" {
		return d
	}
	return "/home/moiz/sniper-data/tui/runs"
}()

func latRuns(t *testing.T) []string {
	var out []string
	for _, p := range []string{filepath.Join(dataDir, "ams/runs/dip_ams_r27.jsonl"), filepath.Join(tuiDataDir, "ams/runs/dip_ams_r28.jsonl")} {
		if _, err := os.Stat(p); err == nil {
			out = append(out, p)
		}
	}
	if len(out) == 0 {
		t.Skip("no r27 / r28")
	}
	return out
}

// the linear-interpolation quantile of raw values (the Hist definition, numpy's default)
func rawQ(xs []float64, p float64) float64 {
	s := append([]float64(nil), xs...)
	sort.Float64s(s)
	pos := p * float64(len(s)-1)
	lo := int(math.Floor(pos))
	hi := min(lo+1, len(s)-1)
	return s[lo] + (s[hi]-s[lo])*(pos-float64(lo))
}

func histClose(t *testing.T, name string, h *Hist, raw []float64) {
	t.Helper()
	if h.N != int64(len(raw)) {
		t.Errorf("%s: %d values, want %d", name, h.N, len(raw))
		return
	}
	if len(raw) == 0 {
		return
	}
	for _, p := range []float64{0.1, 0.5, 0.9} {
		got, _ := h.Quantile(p)
		want := rawQ(raw, p)
		tol := 0.05
		if want >= 10000 {
			tol = 5
		} else if want >= 1000 {
			tol = 0.5
		}
		if math.Abs(got-want) > tol+1e-9 {
			t.Errorf("%s p%.0f: %.1f, want %.3f (+-%.1f)", name, p*100, got, want, tol)
		}
	}
}

type latRaw struct {
	s2r, fillDL, bounce []float64
	blk                 [4]int64
	fills               int64
}

// TestLatency (r27, r28): every pre-send latency figure against an independent encoding/json scan of the records:
// the tries' send -> seen and block, the fills' and the bounced tries' dump -> land (the drop rule from run_start), all
// and per leader client family, each fill's own figures from its filling try, the window try counts; each regular
// buy's dump -> land / send -> seen / block from buy_land and timing. r28 also against the owner's measurement
// (fills 34 ms after the dump, the bounced 6042 tries 307 ms).
func TestLatency(t *testing.T) {
	for _, p := range latRuns(t) {
		name := filepath.Base(p)
		src := NewSource(p, "", 0, 50)
		src.LoadAll(LoadChunk, 0, nil)
		M := src.Model
		f, err := os.Open(p)
		if err != nil {
			t.Fatal(err)
		}
		drop := 0.12
		all := &latRaw{}
		kinds := map[string]*latRaw{}
		okRec := map[string]map[string]any{}
		leader := map[string]string{}
		winTries := map[float64]int64{}
		buyLand := map[string][]map[string]any{}
		timing := map[string][]map[string]any{}
		sc := bufio.NewScanner(f)
		sc.Buffer(make([]byte, 1<<20), 64<<20)
		for sc.Scan() {
			var o map[string]any
			if json.Unmarshal(sc.Bytes(), &o) != nil {
				continue
			}
			switch o["ev"] {
			case "run_start":
				if pl, ok := o["presend_live"].(map[string]any); ok {
					if d, ok := pl["drop"].(float64); ok && d != 0 {
						drop = d
					}
				}
			case "presend_attempt":
				if o["dry"] == true {
					continue
				}
				winTries[o["w"].(float64)]++
				if s, ok := o["sig"].(string); ok {
					l, _ := o["leader"].(string)
					leader[s] = l
				}
			case "presend_attempt_land":
				c, _ := o["client"].(string)
				k := KindOf(c)
				if kinds[k] == nil {
					kinds[k] = &latRaw{}
				}
				res, _ := o["res"].(string)
				for _, r := range []*latRaw{all, kinds[k]} {
					if ss, ok := o["ms_send_to_rx"].(float64); ok {
						r.s2r = append(r.s2r, ss)
						b, okb := o["slots_after_send"].(float64)
						i := 3
						if okb && b >= 0 && b < 3 {
							i = int(b)
						}
						r.blk[i]++
					}
					if res == "ok" {
						r.fills++
					}
					dl, okd := o["ms_after_d_a"].(float64)
					if !okd {
						dl, okd = o["ms_after_x_a"].(float64)
					}
					d, _ := o["d"].(map[string]any)
					prel, okp := d["p_rel"].(float64)
					if okd && okp && prel <= 1-drop+1e-9 {
						if res == "ok" {
							r.fillDL = append(r.fillDL, dl)
						} else if res == "6042" {
							r.bounce = append(r.bounce, dl)
						}
					}
				}
				if res == "ok" {
					okRec[o["sig"].(string)] = o
				}
			case "buy_land":
				m := o["mint"].(string)
				buyLand[m] = append(buyLand[m], o)
			case "timing":
				m := o["mint"].(string)
				timing[m] = append(timing[m], o)
			}
		}
		f.Close()
		got := LatOf(M.Sessions)
		check := func(label string, a *LatAgg, r *latRaw) {
			histClose(t, name+" "+label+" send->seen", &a.S2R, r.s2r)
			histClose(t, name+" "+label+" fills dump->land", &a.FillDL, r.fillDL)
			histClose(t, name+" "+label+" bounced dump->land", &a.Bounce, r.bounce)
			if a.Blk != r.blk || a.Fills != r.fills {
				t.Errorf("%s %s: blocks %v fills %d, want %v %d", name, label, a.Blk, a.Fills, r.blk, r.fills)
			}
		}
		check("all", &got.All, all)
		for k, r := range kinds {
			a := got.Kind[k]
			if a == nil {
				t.Errorf("%s: no %s", name, k)
				continue
			}
			check(k, a, r)
		}
		if len(got.Kind) != len(kinds) {
			t.Errorf("%s: %d client families, want %d", name, len(got.Kind), len(kinds))
		}
		// each fill's own figures
		nf := 0
		for _, tr := range M.Trades {
			if tr.Kind != "PS" || len(tr.BuySigs) == 0 {
				continue
			}
			o := okRec[tr.BuySigs[0]]
			if o == nil {
				continue
			}
			nf++
			l := tr.Lat
			if l == nil {
				t.Errorf("%s: fill %s has no latency", name, tr.BuySigs[0][:8])
				continue
			}
			wantDL, ok := o["ms_after_d_a"].(float64)
			if !ok {
				wantDL, _ = o["ms_after_x_a"].(float64)
			}
			c, _ := o["client"].(string)
			pth, _ := o["path"].(string)
			if l.DL.Float() != wantDL || l.SendSeen.Float() != o["ms_send_to_rx"].(float64) || l.Blk.Float() != o["slots_after_send"].(float64) ||
				l.NBetween.Float() != o["n_between"].(float64) || l.N.Float() != o["n"].(float64) || l.Client != c || l.Path != pth ||
				l.Leader != leader[tr.BuySigs[0]] {
				t.Errorf("%s: fill %s latency %+v != its try's record", name, tr.BuySigs[0][:8], *l)
			}
			S := M.Sessions[tr.S]
			if S.WinTries[tr.W.W] != winTries[float64(tr.W.W)] {
				t.Errorf("%s: window %d tries %d, want %d", name, tr.W.W, S.WinTries[tr.W.W], winTries[float64(tr.W.W)])
			}
		}
		if nf == 0 || nf != len(okRec) {
			t.Errorf("%s: %d fills matched to %d filling tries", name, nf, len(okRec))
		}
		// regular buys
		seen := map[string]int{}
		for _, tr := range M.Trades {
			if tr.Kind != "REG" {
				continue
			}
			i := seen[tr.Mint]
			seen[tr.Mint]++
			dl, ss, blk := TradeLatency(tr)
			var tm map[string]any
			if i < len(timing[tr.Mint]) {
				tm = timing[tr.Mint][i]
			}
			if tm != nil {
				if want, ok := tm["fire_to_seen_ms"].(float64); ok && ss.Float() != want {
					t.Errorf("%s: %s send->seen %v, want %v", name, tr.Mint[:8], ss, want)
				}
			}
			if tr.Land != nil {
				var bl map[string]any
				for _, x := range buyLand[tr.Mint] {
					if s, _ := x["sig"].(string); tr.Land.HasSig && s == tr.Land.Sig {
						bl = x
					}
				}
				if bl != nil && (dl.Float() != bl["rx_ms_after_dump"].(float64) || blk.Float() != bl["slots_after_dump"].(float64)) {
					t.Errorf("%s: %s landed dump->land %v blk %v != buy_land", name, tr.Mint[:8], dl, blk)
				}
			} else if tm != nil {
				b, okb := tm["buy_first_rx"].(float64)
				d, okd := tm["dump_first_rx"].(float64)
				if okb && okd && b != 0 && d != 0 && math.Abs(dl.Float()-(b-d)/1e6) > 0.001 {
					t.Errorf("%s: %s failed buy dump->seen %v, want %.3f", name, tr.Mint[:8], dl, (b-d)/1e6)
				}
			}
		}
		if filepath.Base(p) == "dip_ams_r28.jsonl" {
			f50, _ := got.All.FillDL.Quantile(0.5)
			b50, _ := got.All.Bounce.Quantile(0.5)
			if math.Abs(f50-34) > 1.5 || math.Abs(b50-307) > 1.5 {
				t.Errorf("r28: fills %.1f ms / bounced %.1f ms after the dump, measured 34 / 307", f50, b50)
			}
			t.Logf("r28: fills p50 %.1f ms (%d), bounced 6042 p50 %.1f ms (%d), send->seen p50 %.1f, same block %d/%d",
				f50, got.All.FillDL.N, b50, got.All.Bounce.N, func() float64 { x, _ := got.All.S2R.Quantile(0.5); return x }(),
				got.All.Blk[0], got.All.Seen())
		}
	}
}

// TestHistQuantiles: the sparse histogram's quantiles equal the raw values' to its bucket width.
func TestHistQuantiles(t *testing.T) {
	var h Hist
	var raw []float64
	for i := 0; i < 5000; i++ {
		x := math.Mod(float64(i)*37.37, 25000) - 3
		h.Add(x)
		raw = append(raw, x)
	}
	histClose(t, "synthetic", &h, raw)
	var e Hist
	if _, ok := e.Quantile(0.5); ok {
		t.Error("an empty histogram has a quantile")
	}
}

// BenchmarkLoadR28: the whole r28 (42 MB of records + 1.6 MB of log), as the initial load reads it.
func BenchmarkLoadR28(b *testing.B) {
	p := filepath.Join(tuiDataDir, "ams/runs/dip_ams_r28.jsonl")
	if _, err := os.Stat(p); err != nil {
		b.Skip("no r28")
	}
	for i := 0; i < b.N; i++ {
		src := NewSource(p, "", 0, 50)
		src.LoadAll(LoadChunk, 0, nil)
	}
}
