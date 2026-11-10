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
	{Key: "mintled", Code: "ML", Name: "mint ledger (log)", Short: "mint ledger", Verdict: "LOG new", Why: "MINT-LEDGER (dip43 A6)",
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
	{Key: "fanout", Code: "FO", Name: "fan-out (log)", Short: "fan-out", Verdict: "LOG new", Why: "FANOUT (dip43 A4)",
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
	{Key: "fpstrict", Code: "FS", Name: "FP strict (log)", Short: "FP strict", Verdict: "LOG new", Why: "FP-NOBOT strict (dip43 A10)",
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
