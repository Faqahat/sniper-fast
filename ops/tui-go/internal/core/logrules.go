package core

import (
	"encoding/json"
	"fmt"
)

// The LOG rule registry (dipmon v4, 11-11): log-only verdicts the engine writes on its fill records (dip43+), each shown as
// a LOG row of the Filters table (would-have, scored on the real fills) and in the LOG item of every fill it flags (the
// Trades dot, the Filters list). A new shadow is one entry here: its key, names, the records it reads (if any beyond the
// fill) and its verdict on a fill. The row shows once a fill of the run carries the rule's field (Present).
//
// The coming dip44 farm-floor shadow (presend_live_farm records) goes in as one more entry, e.g.
//
//	{Key: "farm", Name: "farm floor (log)", Short: "farm floor", Note: "real fills; ...", Verdict: "LOG new", Why: "farm floor (dip44)",
//	 Records: []string{"presend_live_farm"}, Feed: func(st *RuleState, ev string, o map[string]any) { ... st.Set("farm", w) ... },
//	 Present: func(st *RuleState, f map[string]any) bool { return st.Any("farm") },
//	 Flag: func(st *RuleState, f map[string]any) (bool, string) { ... }}
type LogRule struct {
	Key, Name, Short, Note string // the row's key, its table name, its short name in the list, its note
	Code                   string // 2 cells (a phone's skip list)
	Verdict, Why           string // the Filters tab's verdict label and reason (FILTERS-3 style)
	ModeKey                string // v5: the filter's live / log control key (the row's name follows the run's modes; "" = log only)
	Records                []string
	Feed                   func(st *RuleState, ev string, o map[string]any)
	Present                func(st *RuleState, fill map[string]any) bool
	Flag                   func(st *RuleState, fill map[string]any) (bool, string)
}

// RuleState: what the rules' own records left (window sets by name).
type RuleState struct {
	sets map[string]map[int64]bool
	n    map[string]int
}

func newRuleState() *RuleState {
	return &RuleState{sets: map[string]map[int64]bool{}, n: map[string]int{}}
}

// Set marks window w in the named set; Has / Any read it; N counts the records.
func (s *RuleState) Set(name string, w int64) {
	if s.sets[name] == nil {
		s.sets[name] = map[int64]bool{}
	}
	s.sets[name][w] = true
	s.n[name]++
}
func (s *RuleState) Has(name string, w int64) bool { return s.sets[name][w] }
func (s *RuleState) Any(name string) bool          { return s.n[name] > 0 }
func (s *RuleState) N(name string) int             { return s.n[name] }

// object helpers on decoded records
func mObj(o map[string]any, k string) map[string]any {
	if x, ok := o[k].(map[string]any); ok {
		return x
	}
	return nil
}
func mBool(o map[string]any, k string) bool {
	b, _ := o[k].(bool)
	return b
}
func mNum(o map[string]any, k string) (float64, bool) {
	switch x := o[k].(type) {
	case float64:
		return x, true
	case json.Number:
		f, err := x.Float64()
		return f, err == nil
	}
	return 0, false
}
func mStr(o map[string]any, k string) string {
	s, _ := o[k].(string)
	return s
}
func mW(o map[string]any) int64 {
	if x, ok := mNum(o, "w"); ok {
		return int64(x)
	}
	return noW
}

// LogRules: the registry (in the table's order, after the built-in LOG rows).
var LogRules = []LogRule{
	{Key: "ga", Code: "GA", Name: "G-A holder floors (log)", Short: "G-A floors", Verdict: "LOG new", Why: "CASCADE G-A (dip43)",
		Note:    "real fills; CASCADE G-A: >= 2 of the top-6 holders (>= 1%) below 90% of their signing balance just before our buy (the snipe-guard's floors would have aborted it)",
		Present: func(_ *RuleState, f map[string]any) bool { return mObj(mObj(f, "cascade"), "ga") != nil },
		Flag: func(_ *RuleState, f map[string]any) (bool, string) {
			ga := mObj(mObj(f, "cascade"), "ga")
			if ga == nil || !mBool(ga, "abort") {
				return false, ""
			}
			b, _ := mNum(ga, "below")
			n, _ := mNum(ga, "n")
			return true, fmt.Sprintf("G-A %.0f of the top %.0f below 90%%", b, n)
		}},
	{Key: "gd", Code: "GD", Name: "guards top-5 (log)", Short: "guards top-5", Verdict: "LOG new", Why: "CASCADE guards (dip43)",
		Note:    "real fills; CASCADE guards: >= 2 of the top-5 non-trigger holders (>= 0.5%) below 90% just before our buy",
		Present: func(_ *RuleState, f map[string]any) bool { return mObj(mObj(f, "cascade"), "gd") != nil },
		Flag: func(_ *RuleState, f map[string]any) (bool, string) {
			gd := mObj(mObj(f, "cascade"), "gd")
			if gd == nil || !mBool(gd, "abort") {
				return false, ""
			}
			b, _ := mNum(gd, "below")
			n, _ := mNum(gd, "n")
			return true, fmt.Sprintf("guards %.0f of %.0f below 90%%", b, n)
		}},
	{Key: "mintled", Code: "ML", Name: "mint ledger (log)", Short: "mint ledger", ModeKey: "mint_ledger", Verdict: "LOG new", Why: "MINT-LEDGER (dip43 A6)",
		Note:    "real fills; MINT-LEDGER: an earlier landing on the mint at or below the ledger's loss (would have skipped the trigger)",
		Present: func(_ *RuleState, f map[string]any) bool { return mObj(f, "mint_ledger") != nil },
		Flag: func(_ *RuleState, f map[string]any) (bool, string) {
			ml := mObj(f, "mint_ledger")
			if ml == nil || !mBool(ml, "would_block") {
				return false, ""
			}
			n, _ := mNum(ml, "n")
			wst, _ := mNum(ml, "worst")
			return true, fmt.Sprintf("mint ledger %.0f landings, worst %s", n, fmtSigned(wst/1e9, 3))
		}},
	{Key: "fanout", Code: "FO", Name: "fan-out (log)", Short: "fan-out", ModeKey: "fanout", Verdict: "LOG new", Why: "FANOUT (dip43 A4)",
		Note:    "real fills; FANOUT: the arm's fam read found >= N plain-transfer recipients (would have disarmed)",
		Present: func(_ *RuleState, f map[string]any) bool { return mObj(f, "fanout") != nil },
		Flag: func(_ *RuleState, f map[string]any) (bool, string) {
			fo := mObj(f, "fanout")
			if fo == nil || !mBool(fo, "flag") {
				return false, ""
			}
			n, _ := mNum(fo, "n")
			return true, fmt.Sprintf("fan-out %.0f recipients", n)
		}},
	{Key: "fpstrict", Code: "FS", Name: "FP strict (log)", Short: "FP strict", ModeKey: "fpnb_strict", Verdict: "LOG new", Why: "FP-NOBOT strict (dip43 A10)",
		Note:    "real fills; FP-NOBOT strict: the window had a T2 slot the strict threshold blocked (the frozen one passed)",
		Records: []string{"presend_live_fpnb_strict"},
		Feed:    func(st *RuleState, _ string, o map[string]any) { st.Set("fpstrict", mW(o)) },
		Present: func(st *RuleState, _ map[string]any) bool { return st.Any("fpstrict") },
		Flag: func(st *RuleState, f map[string]any) (bool, string) {
			if mStr(f, "kind") == "rearm" || !st.Has("fpstrict", mW(f)) {
				return false, ""
			}
			return true, "FP strict blocked a slot of the window"
		}},
}

// v5 (dip47): GRPSIGN and the re-arm fleet rule on the fill records; "measured" = scored on the real fills
var _ = func() bool {
	LogRules = append(LogRules,
		LogRule{Key: "grpsign", Code: "GS", Name: "group at signing (log)", Short: "grp at signing", ModeKey: "grp_t2", Verdict: "LOG new", Why: "GRPSIGN T2 (dip47)",
			Note:    "measured (real fills); GRPSIGN: the T2 window's group at the filling try's signing >= grp_t2_pct (trigger whale per grp_t2_whale; the fill's state)",
			Present: func(_ *RuleState, f map[string]any) bool { return mObj(f, "grpsign") != nil },
			Flag: func(_ *RuleState, f map[string]any) (bool, string) {
				g := mObj(f, "grpsign")
				if g == nil || mStr(f, "kind") == "rearm" || mBool(g, "miss") {
					return false, ""
				}
				thr, whale := 3.0, "out"
				if st := mObj(f, "filters"); st != nil {
					if x, ok := mNum(st, "grp_t2_pct"); ok && x > 0 {
						thr = x
					}
					if w := mStr(st, "grp_t2_whale"); w != "" {
						whale = w
					}
				}
				p, ok := mNum(g, "pct_x")
				if whale == "in" {
					p, ok = mNum(g, "pct")
				}
				if !ok || p < thr {
					return false, ""
				}
				return true, fmt.Sprintf("group %.1f%% at signing (whale %s) >= %.1f%%", p, whale, thr)
			}},
		LogRule{Key: "rfleet", Code: "RF", Name: "re-arm fleet (log)", Short: "re-arm fleet", ModeKey: "rearm_fleet", Verdict: "LOG new", Why: "REARM FLEET (dip47)",
			Note:    "measured (real fills); RE-ARM FLEET: the filling re-arm try saw fewer fleet tries than the rule's N (it would have been withheld; fail-open tries not counted)",
			Present: func(_ *RuleState, f map[string]any) bool { return mObj(f, "rearm_fleet") != nil },
			Flag: func(_ *RuleState, f map[string]any) (bool, string) {
				r := mObj(f, "rearm_fleet")
				if r == nil || !mBool(r, "would_withhold") || mStr(r, "open") != "" {
					return false, ""
				}
				n, _ := mNum(r, "n")
				mn, _ := mNum(r, "min")
				sl, _ := mNum(r, "slots")
				return true, fmt.Sprintf("fleet %.0f < %.0f in %.0f slots", n, mn, sl)
			}})
	LogRules = append(LogRules,
		LogRule{Key: "fresh48", Code: "FR", Name: "fresh holders (log)", Short: "fresh holders", ModeKey: "fresh_skip", Verdict: "LOG new", Why: "FRESH-HOLDERS skip (dip48)",
			Note:    "measured (real fills); the fresh-holders share at the arm >= its lane's threshold (fresh_skip.would_skip on the fill)",
			Present: func(_ *RuleState, f map[string]any) bool { return mObj(f, "fresh_skip") != nil },
			Flag: func(_ *RuleState, f map[string]any) (bool, string) {
				x := mObj(f, "fresh_skip")
				if x == nil || !mBool(x, "would_skip") {
					return false, ""
				}
				p, _ := mNum(x, "pct")
				th, _ := mNum(x, "thr")
				return true, fmt.Sprintf("fresh %.1f%% >= %.0f%%", p, th)
			}},
		// dip50 GRX: fast-selling holders who bought after the trigger were in at our landing (the early-exit flag). The row shows the
		// flagged fills' real P&L: while GRX is in log mode that is what the early exit has to beat; live, what it still left.
		LogRule{Key: "grx", Code: "GX", Name: "rival ahead (log)", Short: "rival ahead", ModeKey: "grx", Verdict: "LOG new", Why: "GRX early exit (dip50)",
			Note:    "measured (real fills); T2 fills with entrant risk >= the threshold at landing (grx.would_exit)",
			Present: func(_ *RuleState, f map[string]any) bool { return mObj(f, "grx") != nil },
			Flag: func(_ *RuleState, f map[string]any) (bool, string) {
				x := mObj(f, "grx")
				if x == nil || !mBool(x, "would_exit") {
					return false, ""
				}
				p, _ := mNum(x, "ent_pct")
				n, _ := mNum(x, "ent_n")
				return true, fmt.Sprintf("rivals ahead %.1f%% (%.0f)", p, n)
			}},
		LogRule{Key: "rgate", Code: "RG", Name: "rival gate (log)", Short: "rival gate", ModeKey: "rival_gate", Verdict: "LOG new", Why: "RIVAL GATE T2 (dip49)",
			Note:    "measured (real fills); the filling T2 try had rivals <= R0, or <= R2 with a young dev (rival_gate.blocked; fail-open not counted)",
			Present: func(_ *RuleState, f map[string]any) bool { return mObj(f, "rival_gate") != nil },
			Flag: func(_ *RuleState, f map[string]any) (bool, string) {
				x := mObj(f, "rival_gate")
				if x == nil || !mBool(x, "blocked") || mStr(x, "open") != "" {
					return false, ""
				}
				r, _ := mNum(x, "rivals")
				a, ok := mNum(x, "dev_age_h")
				age := "?"
				if ok {
					age = fmt.Sprintf("%.1f h", a)
				}
				return true, fmt.Sprintf("rivals %.0f, dev age %s", r, age)
			}})
	return true
}()

var ruleEvs = func() map[string][]int {
	m := map[string][]int{}
	for i, r := range LogRules {
		for _, e := range r.Records {
			m[e] = append(m[e], i)
		}
	}
	return m
}()

// LogRuleOf: the registry entry of a row key (nil = a built-in rule).
func LogRuleOf(key string) *LogRule {
	for i := range LogRules {
		if LogRules[i].Key == key {
			return &LogRules[i]
		}
	}
	return nil
}
