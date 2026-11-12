package ui

// The Filters tab (8): what each pre-send filter blocked and what those blocks would have made (core/filters.go, the
// filters_report.py accounting). On top the table, one row per filter tagged LIVE (it changed what the engine did;
// scored on the shadow's paper = an estimate) or LOG (log only, would-have; scored on the real fills), with its net
// saved (green: saved us money, red: cost us); under it the skip list: every blocked item, sortable (o / O), filtered
// by filter (f), the unscored ones (no shadow fill) shown with n, c copies the mint, enter opens a LOG item's trade.

import (
	"fmt"
	"math"
	"sort"
	"strings"

	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

// fltSortKeys: the skip list's sort columns (o cycles, O flips; time = newest first by default).
var fltSortKeys = []string{"time", "filter", "kind", "mint", "result", "SOL"}

func lamOf(sol float64) int64 { return int64(math.Round(sol * 1e9)) }

// fltShort: a filter's name in at most 12 cells (phones).
func fltShort(key, name string) string {
	switch key {
	case "quiet":
		return "QUIET"
	case "create_slot":
		return "create-slot"
	case "young_age":
		return "age-1 skip"
	case "lone_whale":
		return "10-sec skip"
	case "deeper":
		return "deeper limit"
	case "botdepth_live":
		return "bot depth"
	case "gcr":
		if strings.Contains(name, "run only") {
			return "bad creator*"
		}
		return "bad creator"
	case "st":
		return "safe timer"
	case "ctx85":
		return "ctx85"
	case "grp":
		return "group risk"
	case "hc":
		return "holder clock"
	case "guard":
		return "landing guard"
	case "breaker":
		return "breaker"
	case "cr_loss":
		return "creator loss"
	case "cr_unfollowed":
		return "cr unfollowed"
	case "quiet3_a":
		return "QUIET3-A live"
	case "q3a":
		return "QUIET3-A"
	case "fresh":
		return "fresh holders"
	case "crlog":
		return "creator loss (log)"
	case "eqgrp":
		return "equal group"
	case "fam":
		return "fam"
	case "fpnb":
		return "no-bot (log)"
	case "skip2":
		return "skip2 (log)"
	case "fpnb_live":
		return "no-bot (live)"
	case "blocklist":
		return "blocklist"
	case "wh_loss":
		return map[bool]string{true: "whale T2 log", false: "whale T2"}[strings.HasSuffix(name, "[log]")]
	case "rearm_wh_loss":
		return map[bool]string{true: "whale RA log", false: "whale RA"}[strings.HasSuffix(name, "[log]")]
	case "holder_loss":
		return map[bool]string{true: "holder log", false: "holder loss"}[strings.HasSuffix(name, "[log]")]
	case "wh_other":
		return "whale other rule"
	case "skip2_live":
		return "skip2 live"
	case "wh_logmode":
		return "whale (log mode)"
	case "hl_logmode":
		return "holder (log mode)"
	case "m2_unseen":
		return "M2 unseen"
	case "mint_ledger":
		return "mint ledger live"
	case "fanout_live":
		return "fan-out live"
	case "h2":
		return "HYBRID-2 (log)"
	}
	return name
}

// fltCode: a LOG rule in 2 cells (a phone's skip list, several rules on one fill: "ST+GR+HC").
func fltCode(key string) string {
	switch key {
	case "gcr":
		return "BC"
	case "st":
		return "ST"
	case "ctx85":
		return "85"
	case "grp":
		return "GR"
	case "hc":
		return "HC"
	case "guard":
		return "LG"
	case "q3a":
		return "Q3"
	case "fresh":
		return "FH"
	case "crlog":
		return "CL"
	case "eqgrp":
		return "EQ"
	case "fam":
		return "FM"
	case "fpnb":
		return "NB"
	case "skip2":
		return "S2"
	case "fpnb_live":
		return "NL"
	case "h2":
		return "H2"
	case "skip2_live":
		return "SL"
	case "wh_other":
		return "WO"
	case "wh_logmode":
		return "WL"
	case "hl_logmode":
		return "HL"
	}
	if x := core.LogRuleOf(key); x != nil && x.Code != "" {
		return x.Code
	}
	return key
}

// fltChoices: the f cycle: all, LIVE, LOG, then each filter with something blocked.
func (m *Model) fltChoices() []string {
	out := []string{"all", "LIVE", "LOG"}
	if R := m.view.Filt; R != nil {
		for _, r := range R.Rows {
			if r.Blocked > 0 {
				out = append(out, r.Key)
			}
		}
	}
	return out
}

func (m *Model) fltChoiceName(c string) string {
	if R := m.view.Filt; R != nil {
		if r, ok := R.Row(c); ok {
			return r.Name
		}
	}
	return c
}

// fltItems: the skip list (filter, the unscored ones with n, sort).
func (m *Model) fltItems() ([]core.FiltItem, int) {
	items, hidden, _ := m.fltItems2()
	return items, hidden
}

// fltItems2: also the number of shadow-window rows hidden (v). A LIVE filter picked with f reveals its rows.
func (m *Model) fltItems2() ([]core.FiltItem, int, int) {
	R := m.view.Filt
	if R == nil {
		return nil, 0, 0
	}
	ch := m.fltChoices()
	c := ch[min(m.fltFilter, len(ch)-1)]
	var out []core.FiltItem
	hidden, shadow := 0, 0
	for _, it := range R.Items {
		if it.Live && !m.fltShadow && c == "all" { // the shadow-window rows: hidden by default (v); picking a LIVE filter with f reveals them
			shadow++
			continue
		}
		switch c {
		case "all":
		case "LIVE":
			if !it.Live {
				continue
			}
		case "LOG":
			if it.Live {
				continue
			}
		default: // one filter: a LOG fill shows under every rule that caught it
			if !it.Has(c) {
				continue
			}
		}
		if !it.Scored && !m.fltAll {
			hidden++
			continue
		}
		out = append(out, it)
	}
	key := fltSortKeys[m.fltSort]
	val := func(it core.FiltItem) (float64, string, bool) {
		switch key {
		case "filter":
			return 0, it.Name, true
		case "kind":
			return 0, it.Kind, true
		case "mint":
			return 0, strings.ToLower(it.Mint), it.Mint != ""
		case "result":
			if !it.Scored { // a LIVE skip whose shadow window never filled: no dip, between WIN and LOSE
				return 0, "", it.Live
			}
			if it.Sol > 0 {
				return 1, "", true
			}
			return -1, "", true
		case "SOL":
			return it.Sol, "", it.Scored || it.Live // no dip = 0.000 (Sol is 0)
		}
		return float64(it.T), "", it.T != 0
	}
	sort.SliceStable(out, func(i, j int) bool {
		a, as, aok := val(out[i])
		b, bs, bok := val(out[j])
		if aok != bok {
			return aok // no value: last
		}
		if as != bs {
			if m.fltAsc {
				return as < bs
			}
			return as > bs
		}
		if a != b {
			if m.fltAsc {
				return a < b
			}
			return a > b
		}
		return false
	})
	return out, hidden, shadow
}

// tagLive / tagLog: the LIVE / LOG badges.
func (m *Model) fltTag(live bool, short bool) string {
	t := m.th
	if live { // v5.2 (owner 11-12): a green circle = LIVE (it blocks trades), a violet one = LOG (it only marks what it would block)
		return t.Good.Render(m.g("\u25cf", "*"))
	}
	if t.Mono {
		return m.g("\u25cb", "o")
	}
	return lipgloss.NewStyle().Foreground(t.Violet).Render(m.g("\u25cf", "o"))
}

// fltClean: a row's name without the mode / build suffixes the circle already says ("(log)", "[live]", "(new)", "(dip48)", "would").
func fltClean(name string) string {
	for _, x := range []string{" (log)", " (live)", " (new)", " (dip48)", " (approx)", " would"} {
		name = strings.ReplaceAll(name, x, "")
	}
	if i := strings.Index(name, " ["); i > 0 { // the mode history tags: " [live]", " [log]", " [live→log]"
		name = name[:i]
	}
	return strings.TrimSpace(name)
}

// fltWhats: what each filter does, in plain words (the table's last column).
var fltWhats = map[string]string{
	"create_slot": "whale bought in the token's first slot", "quiet": "quiet token: no bot follow-up on the whale's past dumps",
	"young_age": "token only 1 slot old", "lone_whale": "lone whale, token older than 10 s", "breaker": "pause after 2 losses in 30 min",
	"cr_loss": "creator cost us twice before", "cr_unfollowed": "creator's tokens get no followers", "quiet3_a": "dead token + new whale",
	"fpnb_live": "no follower bot expected (model)", "fpnb": "no follower bot expected (model)", "blocklist": "a listed attacker wallet holds",
	"wh_loss": "this whale cost us before", "rearm_wh_loss": "this dumper cost us before", "holder_loss": "a holder who cost us before is in",
	"skip2_live": "per-try loss model", "skip2": "per-try loss model", "m2_unseen": "no scored dump before the trigger",
	"grp_t2": "fast-selling holders in at arm", "grp": "fast-selling holders in at our landing", "mint_ledger": "we already lost on this token",
	"fanout_live": "whale spread over many wallets", "fresh_holders": "too many brand-new holders", "fresh": "too many brand-new holders",
	"rgate_live": "no rivals bidding / young dev wallet", "rearm_cap": "re-arm fills per token capped", "pause_window": "night pause window",
	"rfleet_live": "re-arm: wait for the bot fleet", "botdepth_live": "fewer than 3 known bots traded it", "deeper": "deeper limit while a 6% holder stays",
	"q3a": "dead token + new whale", "eqgrp": "several equal-size holders", "fam": "launch bundle family holds", "h2": "HYBRID-2 arm rule",
	"st": "safe sell timer", "hc": "holder clock", "guard": "landing guard", "ctx85": "context score", "gcr": "bad creator (run only)",
	"crlog": "creator ledger would-skip", "ga": "2+ top holders left before we landed", "gd": "a top-5 guard holder left before we landed",
	"mintled": "we already lost on this token", "fanout": "whale spread over many wallets", "fpstrict": "stricter no-follower-bot model",
	"grpsign": "fast-selling holders in when the try was signed", "rfleet": "re-arm: wait for the bot fleet", "fresh48": "too many brand-new holders",
	"rgate": "no rivals bidding / young dev wallet", "farm": "farm floor", "grx": "fast rivals got in ahead of us (early-exit flag)", "wh_other": "whale ledger, other rule", "wh_logmode": "whale ledger in log mode", "hl_logmode": "holder ledger in log mode",
}

func fltWhat(key, fallback string) string {
	if w, ok := fltWhats[key]; ok {
		return w
	}
	return fallback
}

// solCell: a SOL amount in green / red (3 decimals, signed).
func (m *Model) solCell(x float64, n int, bold bool) string {
	return m.th.Money(lamOf(x), n > 0 || x != 0, bold).Render(core.FS(x, 3))
}

// invCell: what blocked trades would have made, colored from the FILTER's side (owner 11-03: "green good, red bad"): a blocked
// winner (+) cost us (red), a blocked loser (-) saved us (green). The number itself keeps its sign.
func (m *Model) invCell(x float64, n int, bold bool) string {
	return m.th.Money(lamOf(-x), n > 0 || x != 0, bold).Render(core.FS(x, 3))
}

// fltVerdict: a filter's verdict from the FILTERS-3 study (11-03 PKT: ops/strategies/presend/filters3/tune/tune.json
// "verdicts" and build/DIP32.md). group orders the table (LIVE, then LOG, then DISMISSED, folded into one line).
type fltVerdict struct {
	group      int    // vgLive / vgLog / vgDism
	label, why string // the verdict (<= 10 cells) and a 3-6 word reason
}

const (
	vgLive = iota
	vgLog
	vgDism
)

// fltVerdicts: the one place to edit the verdicts (key = the row's Key, core/filters.go).
var fltVerdicts = map[string]fltVerdict{
	"create_slot":   {vgLive, "KEEP", "strongest, + always"},
	"quiet":         {vgLive, "KEEP", "small + everywhere"},
	"young_age":     {vgLive, "KEEP", "no value either way"},
	"lone_whale":    {vgLive, "KEEP", "tiny + everywhere"},
	"breaker":       {vgLive, "LIVE new", "fires on attacks"},
	"cr_loss":       {vgLive, "LIVE new", "+ in every period"},
	"quiet3_a":      {vgLive, "LIVE new", "dead token + new whale; attack"},
	"cr_unfollowed": {vgLog, "LOG", "unproven vs ledger"},
	"gcr":           {vgLive, "LIVE dip32", "now creator loss"},
	"grp":           {vgLog, "LOG", "weak, keep logging"},
	"q3a":           {vgLog, "LOG", "weak on holdout"},
	"fresh":         {vgLog, "LOG", "attack guard (G3)"},
	"crlog":         {vgLog, "LOG", "ledger off: would-skips"},
	"eqgrp":         {vgDism, "DISMISSED", "mixed r51/r53"},
	"fam":           {vgLog, "LOG new", "bundle rug (dip35)"},
	"fpnb":          {vgLog, "LOG new", "no follower bot (dip36)"},
	"skip2":         {vgLog, "LOG new", "per-send logit (dip36)"},
	"fpnb_live":     {vgLive, "LIVE new", "no-bot gate (dip36)"},
	"blocklist":     {vgLive, "LIVE new", "listed wallets (dip36)"},
	"wh_loss":       {vgLive, "LIVE new", "whale ledger T2 (dip37)"},
	"rearm_wh_loss": {vgLive, "LIVE new", "dumper ledger (dip37)"},
	"holder_loss":   {vgLive, "LIVE new", "holder ledger (dip37)"},
	"wh_other":      {vgLog, "LOG new", "whale ledger other rule"},
	"skip2_live":    {vgLive, "LIVE new", "per-send logit gate (dip37b)"},
	"wh_logmode":    {vgLog, "LOG", "whale ledger in log mode"},
	"hl_logmode":    {vgLog, "LOG", "holder ledger in log mode"},
	"m2_unseen":     {vgLive, "LIVE new", "no M2 dump before (dip37)"},
	"h2":            {vgDism, "DISMISSED", "HYBRID-2 arm rule (dip37)"},
	"st":            {vgDism, "DISMISSED", "within group risk"},
	"hc":            {vgDism, "DISMISSED", "dup of group risk"},
	"guard":         {vgDism, "DISMISSED", "flagged did better"},
	"ctx85":         {vgDism, "DISMISSED", "attack-only gain"},
	"grp_t2":        {vgLive, "LIVE new", "group at signing (dip47)"},
	"mint_ledger":   {vgLive, "LIVE new", "mint ledger live (dip43)"},
	"fanout_live":   {vgLive, "LIVE new", "fan-out live (dip43)"},
	"fresh_holders": {vgLive, "LIVE new", "fresh holders (dip48)"},
	"rgate_live":    {vgLive, "LIVE new", "rival gate T2 (dip49)"},
	"rearm_cap":     {vgLive, "LIVE new", "re-arm fills per mint (dip47)"},
	"pause_window":  {vgLive, "LIVE new", "PKT pause window (dip47)"},
	"rfleet_live":   {vgLive, "LIVE new", "re-arm fleet rule (dip47)"},
}

// fltVerdictOf: the row's verdict; a filter the study did not judge (the deeper limit) keeps its type's group, "—".
func fltVerdictOf(r core.FiltRow) fltVerdict {
	if v, ok := fltVerdicts[r.Key]; ok {
		return v
	}
	if x := core.LogRuleOf(r.Key); x != nil { // v4: the LOG rule registry (dip43+)
		return fltVerdict{vgLog, x.Verdict, x.Why}
	}
	if r.Type == "LIVE" {
		return fltVerdict{vgLive, core.G.Dash, "no 11-03 verdict"}
	}
	return fltVerdict{vgLog, core.G.Dash, "no 11-03 verdict"}
}

// fltVerdictShort: the verdict in 4 cells (phones).
func fltVerdictShort(label string) string {
	switch label {
	case "LIVE new":
		return "NEW"
	case "LIVE dip32":
		return "LV32"
	case "DISMISSED":
		return "DISM"
	}
	return label
}

func (m *Model) verdictStyle(v fltVerdict) lipgloss.Style {
	t := m.th
	switch {
	case v.label == core.G.Dash:
		return t.Dim
	case v.group == vgLive:
		return t.Good
	case v.group == vgLog:
		return t.Warn
	}
	return t.Dim
}

// fltPrec: the precision of a row: the losers among the marked items that have a value (%), ok = any.
func fltPrec(winN, loseN int) (float64, bool) {
	if winN+loseN == 0 {
		return 0, false
	}
	return float64(loseN) / float64(winN+loseN) * 100, true
}

// precCell: the precision in n cells, green >= 60%, yellow >= 50% (a coin flip), red below.
func (m *Model) precCell(winN, loseN, n int) string {
	t := m.th
	p, ok := fltPrec(winN, loseN)
	if !ok {
		return t.Dim.Render(padLeft(core.G.Dash, n))
	}
	st := t.Neg
	switch {
	case p >= 60:
		st = t.Pos
	case p >= 50:
		st = t.Warn
	}
	return st.Render(padLeft(fmt.Sprintf("%.0f%%", p), n))
}

// fltSortedRows: the table's rows by verdict group (LIVE, LOG, DISMISSED), within a group by net saved (largest first;
// a rule this run does not log last), the table's own order on ties.
func fltSortedRows(rows []core.FiltRow) []core.FiltRow {
	out := append([]core.FiltRow(nil), rows...)
	sort.SliceStable(out, func(i, j int) bool {
		a, b := out[i], out[j]
		ga, gb := fltVerdictOf(a).group, fltVerdictOf(b).group
		if ga != gb {
			return ga < gb
		}
		if a.NA != b.NA {
			return !a.NA
		}
		return lamOf(a.ShownNet()) > lamOf(b.ShownNet())
	})
	return out
}

// fltTableLines: the overview table, fitted to w: tag, filter, verdict, NET SAVED, precision, then blocked and the
// would-win / would-lose (wide), the reason; the DISMISSED filters folded into one line (d expands), the unique totals.
func (m *Model) fltTableLines(w int) []string {
	t := m.th
	R := m.view.Filt
	bar := " " + m.g("│", "|") + " "
	sep := t.Dim.Render(bar)
	// three layouts: wide (the would-win / would-lose sums, the reason), medium (counts only), phones (4-cell verdicts)
	mode := 2
	switch {
	case w >= 100:
		mode = 0
	case w >= 76:
		mode = 1
	}
	// v4 (11-11) CALIBRATED: with a calibration the LIVE paper-scored rows lead with the calibrated numbers (net, prec, W / L), a
	// src marker after the net (cal / real / paper; phones: one cell, c = cal) and the raw paper net in a dim column of its own
	calOn := R.Calib != nil
	srcW, papW := 0, 0 // the marker's and the paper column's cells (0 = not shown)
	if calOn {
		switch mode {
		case 0:
			srcW, papW = 5, 12 // " " + 4; " | " + 9
		case 1:
			srcW, papW = 5, 9 // " " + 4; " " + 8
		default:
			srcW = 1
		}
	}
	var nameW, tagW, vdW, netW, precW int
	_ = vdW
	showBlk, showWL := true, true
	switch mode {
	case 0:
		papW = 0
		tagW, vdW, netW, precW = 3, 0, 9, 0
		nameW = max(8, min(26, w-55-srcW))
	case 1:
		papW = 0
		tagW, vdW, netW, precW = 3, 0, 9, 0
		nameW = max(8, min(26, w-33-srcW))
	default:
		papW = 0
		tagW, vdW, netW, precW = 2, 0, 8, 0
		nameW = 16
		fixed := tagW + nameW + 1 + netW + srcW
		if fixed+6+8 > w {
			showWL = false
		}
		if fixed+6 > w {
			showBlk = false
		}
		if fixed > w {
			nameW = max(4, nameW-(fixed-w))
		}
	}
	whyW := 0
	if mode == 0 {
		whyW = w - (55 + srcW + nameW) - 3
		if whyW < 24 { // too narrow to say what the filter does: drop the column
			whyW = 0
		}
	}
	srcCell := func(src string) string { // "cal" / "real" / "pap" ("" = blank)
		if srcW == 0 {
			return ""
		}
		if srcW == 1 {
			if src == "cal" {
				return t.Acc.Render("c")
			}
			return " "
		}
		st := t.Dim
		if src == "cal" {
			st = t.Acc
		}
		return " " + st.Render(padRight(src, 4))
	}
	papCell := func(p string) string { // the raw paper net, dim ("" = blank)
		if papW == 0 {
			return ""
		}
		if mode == 0 {
			return sep + t.Dim.Render(padLeft(p, 9))
		}
		return " " + t.Dim.Render(padLeft(p, papW-1))
	}
	// the numbers after the name + verdict (net, prec, blocked, W / L), shared by the rows, the totals and the folded line
	nums := func(net, src string, winN, loseN, blocked int, winSol, loseSol float64, paper string, bold bool) string {
		s := " " + padLeft(net, netW) + srcCell(src)
		if precW > 0 {
			s += " " + m.precCell(winN, loseN, precW)
		}
		blk := core.IC(int64(blocked))
		st := t.Val
		if bold {
			st = t.B
		}
		switch mode {
		case 0:
			s += sep + st.Render(padLeft(blk, 7)) + sep + t.Neg.Render(padLeft(fmt.Sprint(winN), 4)) + " " + padLeft(m.invCell(winSol, winN, false), 8) + sep +
				t.Pos.Render(padLeft(fmt.Sprint(loseN), 4)) + " " + padLeft(m.invCell(loseSol, loseN, false), 8)
		case 1:
			s += sep + st.Render(padLeft(blk, 7)) + " " + t.Neg.Render(padLeft(fmt.Sprint(winN), 4)) + " " + t.Pos.Render(padLeft(fmt.Sprint(loseN), 4))
		default:
			if showBlk {
				s += " " + st.Render(padLeft(blk, 5))
			}
			if showWL {
				s += " " + t.Neg.Render(padLeft(fmt.Sprint(winN), 3)) + " " + t.Pos.Render(padLeft(fmt.Sprint(loseN), 3))
			}
		}
		return s + papCell(paper)
	}
	hdr := func() string {
		srcH, papH := "", ""
		if srcW > 1 {
			srcH = " " + padRight("src", 4)
		} else if srcW == 1 {
			srcH = " "
		}
		if papW > 0 {
			if mode == 0 {
				papH = bar + padLeft("paper net", 9)
			} else {
				papH = " " + padLeft("paper", papW-1)
			}
		}
		s := padRight("", tagW) + padRight("filter", nameW) + " " + padLeft("saved", netW) + srcH
		switch mode {
		case 0:
			s += bar + padLeft("blocked", 7) + bar + padLeft("would win", 13) + bar + padLeft("would lose", 13) + papH
			if whyW > 0 {
				s += "   what"
			}
		case 1:
			s += bar + padLeft("blocked", 7) + " " + padLeft("W", 4) + " " + padLeft("L", 4) + papH
		default:
			s = padRight("", tagW) + padRight("filter", nameW) + " " + padLeft("saved", netW) + srcH
			if showBlk {
				s += " " + padLeft("blkd", 5)
			}
			if showWL {
				s += " " + padLeft("W", 3) + " " + padLeft("L", 3)
			}
			s += papH
		}
		return t.Lbl.Render(s)
	}
	rowSel := false // the row being rendered is the selected one
	row := func(r core.FiltRow) string {
		name := fltClean(r.Name)
		if ansi.StringWidth(name) > nameW {
			name = fltShort(r.Key, name)
		}
		name = cut(name, nameW)
		vd := fltVerdictOf(r)
		tag := m.fltTag(r.Type == "LIVE", mode == 2)
		lbl := vd.label
		if mode == 2 {
			lbl = fltVerdictShort(lbl)
		}
		_ = lbl
		pad, nst := strings.Repeat(" ", max(0, tagW-ansi.StringWidth(tag))), t.Val
		if rowSel && len(pad) > 0 { // the cursor: a marker after the circle, the name highlighted
			pad = pad[:len(pad)-1] + t.Acc.Render(m.g("\u25b8", ">"))
			if len(pad) > 1 && tagW == 3 {
				pad = " " + t.Acc.Render(m.g("\u25b8", ">"))
			}
			nst = t.B.Background(t.SelBg)
			if t.Mono {
				nst = t.B.Reverse(true)
			}
		}
		s := tag + pad + nst.Render(padRight(name, nameW))
		if r.NA { // a rule this run does not log (the landing guard before dip30)
			if mode == 2 {
				return s + " " + t.Dim.Render(padLeft("n/a", netW)+" dip30+")
			}
			return s + " " + t.Dim.Render(padLeft("n/a", netW)) + "  " + t.Dim.Render("(dip30+: not logged by this run)")
		}
		switch {
		case r.Cal: // calibrated: the cal numbers lead, the raw paper net in its dim column
			s += nums(m.solCell(r.CalNet(), r.CalWinN+r.CalLoseN, true), "cal", r.CalWinN, r.CalLoseN, r.Blocked, r.CalWinSol, r.CalLoseSol, core.FS(r.Net(), 3), false)
		case r.Type == "LIVE":
			cell := m.solCell(r.Net(), r.WinN+r.LoseN, true)
			if r.WinN+r.LoseN == 0 && r.Blocked > 0 { // v5.1: a zero is either "no dip" (nothing would have filled) or "n/a" (no way to price it)
				if nd, unk := m.fltDip(r.Key); nd+unk > 0 {
					txt := "no dip"
					switch {
					case nd == 0:
						txt = "n/a"
					case unk > 0:
						txt = "no dip*"
					}
					cell = t.Dim.Render(txt)
					s += nums(cell, "", r.WinN, r.LoseN, r.Blocked, r.WinSol, r.LoseSol, core.FS(r.Net(), 3), false)
					break
				}
			}
			s += nums(cell, "pap", r.WinN, r.LoseN, r.Blocked, r.WinSol, r.LoseSol, core.FS(r.Net(), 3), false)
		default:
			s += nums(m.solCell(r.Net(), r.WinN+r.LoseN, true), "real", r.WinN, r.LoseN, r.Blocked, r.WinSol, r.LoseSol, "", false)
		}
		if whyW > 0 {
			why := fltWhat(r.Key, vd.why)
			if r.Key == "gcr" && R.Seed == "" {
				why = "no seed: this run only; " + why
			}
			s += "   " + t.Dim.Render(cut(why, whyW))
		}
		return s
	}
	lead := tagW + nameW // the label span of a total / the folded line
	total := func(label, src string, x core.FiltTotal, paper string) string {
		return t.Lbl.Render(padRight(cut(label, lead), lead)) + nums(m.solCell(x.Net, 1, true), src, x.WinN, x.LoseN, x.Blocked, x.WinSol, x.LoseSol, paper, true)
	}
	deepLine := func() string { // the deeper limit's deep fills (bought >= 15% down): their real P&L vs the shadow's, the NET
		ind := strings.Repeat(" ", tagW)
		if calOn { // v4 (11-11): against the calibrated paper (the row's cal blocks + real - cal(paper))
			d := t.Dim.Render(ind+m.g("└ ", "` ")) + t.Lbl.Render(fmt.Sprintf("%d deep fills: real ", R.DeepRealN)) + m.solCell(R.DeepReal, 1, false) +
				t.Lbl.Render(" vs cal paper ") + m.solCell(R.DeepReal-R.DeepGainCal, 1, false) + t.Lbl.Render(" = gain ") + m.solCell(R.DeepGainCal, 1, false) + t.Lbl.Render("  NET ") + m.solCell(R.DeepNetCal, 1, true) + t.Acc.Render(" cal") +
				t.Dim.Render("  (paper gain "+core.FS(R.DeepGain, 3)+", NET "+core.FS(R.DeepNet, 3)+")")
			if w < 84 {
				d = t.Dim.Render(ind+m.g("└ ", "` ")) + t.Lbl.Render(fmt.Sprintf("%d deep fills gain ", R.DeepRealN)) + m.solCell(R.DeepGainCal, 1, false) +
					t.Lbl.Render("  NET ") + m.solCell(R.DeepNetCal, 1, true) + t.Acc.Render(" c")
			}
			return cut(d, w)
		}
		d := t.Dim.Render(ind+m.g("└ ", "` ")) + t.Lbl.Render(fmt.Sprintf("%d deep fills: real ", R.DeepRealN)) + m.solCell(R.DeepReal, 1, false) +
			t.Lbl.Render(" vs 0.88x paper ") + m.solCell(R.DeepPaper, 1, false) + t.Lbl.Render(" = gain ") + m.solCell(R.DeepGain, 1, false) +
			t.Lbl.Render("  NET ") + m.solCell(R.DeepNet, 1, true)
		if w < 84 { // phones: the gain and the NET only
			d = t.Dim.Render(ind+m.g("└ ", "` ")) + t.Lbl.Render(fmt.Sprintf("%d deep fills gain ", R.DeepRealN)) + m.solCell(R.DeepGain, 1, false) +
				t.Lbl.Render("  NET ") + m.solCell(R.DeepNet, 1, true)
		}
		if R.DeepRAN > 0 && w >= 120 {
			d += t.Dim.Render(fmt.Sprintf("  (+%d re-arm deep fills ", R.DeepRAN)) + m.solCell(R.DeepRAReal, 1, false) + t.Dim.Render(", no shadow)")
		}
		return d
	}
	out := []string{hdr()}
	m.fltTblKeys, m.fltTblLine = m.fltTblKeys[:0], m.fltTblLine[:0]
	sel := func(r core.FiltRow) string { // v5.3: the table's rows are selectable (enter opens the filter's page)
		i := len(m.fltTblKeys)
		m.fltTblKeys, m.fltTblLine = append(m.fltTblKeys, r.Key), append(m.fltTblLine, len(out))
		rowSel = m.fltTblFocus && i == m.fltCur && m.fltOpen == ""
		l := row(r)
		rowSel = false
		return l
	}
	var dism []core.FiltRow
	var idle []string // dipmon 3.3: the rows with no blocks yet, folded into one line by name
	for _, r := range fltSortedRows(R.Rows) {
		if fltVerdictOf(r).group == vgDism {
			dism = append(dism, r)
			continue
		}
		if r.Blocked == 0 && !r.NA {
			idle = append(idle, fltClean(r.Name))
			continue
		}
		out = append(out, sel(r))
		if r.Key == "deeper" && R.Deep {
			out = append(out, deepLine())
		}
	}
	if len(idle) > 0 {
		out = append(out, t.Dim.Render(cut(fmt.Sprintf("%d with no blocks yet: %s", len(idle), strings.Join(idle, ", ")), w)))
	}
	if len(dism) > 0 { // the DISMISSED filters: one line (count, the rows' net summed), d expands them under it
		var net, pnet float64
		var names []string
		var winN, loseN, blocked int
		var winSol, loseSol float64
		anyCal, anyLive := false, false
		for _, r := range dism {
			names = append(names, fltClean(fltShort(r.Key, r.Name)))
			if !r.NA {
				net += r.ShownNet()
				pnet += r.Net()
				blocked += r.Blocked
				if r.Cal {
					anyCal = true
					winN, loseN = winN+r.CalWinN, loseN+r.CalLoseN
					winSol, loseSol = winSol+r.CalWinSol, loseSol+r.CalLoseSol
				} else {
					winN, loseN = winN+r.WinN, loseN+r.LoseN
					winSol, loseSol = winSol+r.WinSol, loseSol+r.LoseSol
				}
				anyLive = anyLive || r.Type == "LIVE"
			}
		}
		dsrc, dpap := "real", ""
		if anyCal {
			dsrc = "cal"
		}
		if anyLive {
			dpap = core.FS(pnet, 3)
		}
		arrow, act := m.g("▸", ">"), "show"
		if m.fltDism {
			arrow, act = m.g("▾", "v"), "hide"
		}
		label := fmt.Sprintf("%s %d DISMISSED  d %s", arrow, len(dism), act)
		if mode == 2 {
			label = fmt.Sprintf("%s %d dismissed (d)", arrow, len(dism))
		}
		l := t.Dim.Render(padRight(cut(label, lead), lead)) + nums(m.solCell(net, winN+loseN, true), dsrc, winN, loseN, blocked, winSol, loseSol, dpap, false)
		if whyW > 0 {
			l += "   " + t.Dim.Render(cut(strings.Join(names, ", "), whyW))
		}
		out = append(out, l)
		if m.fltDism {
			for _, r := range dism {
				out = append(out, sel(r))
			}
		}
	}
	lvLabel, lgLabel, allLabel := "LIVE total (unique triggers)", "LOG total (unique fills)", "ALL total"
	if ansi.StringWidth(lvLabel) > lead {
		lvLabel, lgLabel = "LIVE unique", "LOG unique"
	}
	lv := total(lvLabel, "pap", R.LiveU, core.FS(R.LiveU.Net, 3))
	if calOn {
		lv = total(lvLabel, "cal", R.LiveUCal, core.FS(R.LiveU.Net, 3))
	}
	tail := func(s string) string { // a total's dim note in the reason column (wide only)
		if whyW > 0 {
			return "   " + t.Dim.Render(cut(s, whyW))
		}
		return ""
	}
	addIf := func(line, x string) string { // x only when the line keeps within w
		if ansi.StringWidth(line)+ansi.StringWidth(x) <= w {
			return line + x
		}
		return line
	}
	if R.Deep && whyW > 0 { // the deeper limit's deep fills earned apart from its blocks
		inc := R.LiveU.Net + R.DeepGain
		if calOn {
			inc = R.LiveUCal.Net + R.DeepGainCal
		}
		lv = addIf(lv, t.Dim.Render("   incl. deep ")+m.solCell(inc, 1, true))
	} else if R.LiveDup > 0 {
		lv += tail(fmt.Sprintf("%d triggers in 2+ rows", R.LiveDup))
	}
	out = append(out, lv)
	out = append(out, total(lgLabel, "real", R.LogU, "")+tail(fmt.Sprintf("%d fills in 2+ rules", R.LogMulti)))
	if calOn {
		out = append(out, total(allLabel, "cal", R.AllCal, core.FS(R.All.Net, 3))+tail("LIVE cal+LOG real"))
	} else {
		out = append(out, total(allLabel, "pap", R.All, core.FS(R.All.Net, 3))+tail("LIVE paper+LOG real"))
	}
	for _, l := range m.view.Added { // dip41 / dip42: the log-only windows' rows (the snapshot's ADDED WINDOWS lines)
		out = append(out, t.Val.Render(cut(l, w)))
	}
	return out
}

// scrFilters: the table, then the skip list (scrolls with its selection, like Trades).
func (m *Model) scrFilters(w, bh int) string {
	t := m.th
	R := m.view.Filt
	if R == nil || !R.Any {
		m.fltRows = nil
		m.fltRowY = 0
		return m.rule("FILTERS", "", w) + "\n" + t.Lbl.Render("no filter records in this run (pre-send skips, deeper-limit tries, annotations)")
	}
	if m.fltOpen != "" {
		return m.scrFilterPage(w, bh)
	}
	sep := t.Dim.Render(" " + m.g("·", "|") + " ")
	var out []string
	livePap := " live: blocks trades (paper)"
	if R.Calib != nil {
		livePap = " live: blocks trades (cal)"
	}
	right := m.fltTag(true, false) + t.Lbl.Render(livePap) + sep + m.fltTag(false, false) + t.Lbl.Render(" log only, would-have (real fills)")
	if w < 100 {
		right = m.fltTag(true, false) + t.Lbl.Render(" live") + sep + m.fltTag(false, false) + t.Lbl.Render(" log only")
	}
	out = append(out, m.rule("FILTERS", right, w))
	if R.Calib != nil { // v4 (11-11): the one-line warning: decide on the calibrated numbers
		note := t.Dim.Render("saved = what its blocks would have lost · cal = expected live value · real = real fills · no dip = nothing would have filled · n/a = cannot be priced")
		if m.ascii {
			note = t.Dim.Render("saved = what its blocks would have lost | cal = expected live value | real = real fills | no dip = nothing would have filled | n/a = cannot be priced")
		}
		out = append(out, cut(note, w))
	}
	m.fltTblY = m.bodyY + len(out)
	out = append(out, m.fltTableLines(w)...)
	m.fltCur = max(0, min(m.fltCur, len(m.fltTblKeys)-1))
	// the legend: what net saved / prec / verdict mean (one line), then (wide) how LIVE and LOG rows are scored
	foot := t.Pos.Render("green") + t.Dim.Render(" = the filter saved money, ") + t.Neg.Render("red") + t.Dim.Render(" = it cost money") + sep + t.Dim.Render("blocked = triggers / windows it stopped; would win / lose = the ones that would have filled")
	out = append(out, cut(foot, w))
	if w >= 120 {
		if R.RearmSkips > 0 { // v5.2: one short line only when it says something
			out = append(out, t.Dim.Render(cut(fmt.Sprintf("re-arm skips %s have no value yet (no shadow window or probes for re-arm)", core.IC(R.RearmSkips)), w)))
		}
	}
	// the skip list
	items, hidden, shadowHid := m.fltItems2()
	m.fltRows = items
	n := len(items)
	if n == 0 {
		m.fltSel = 0
	} else {
		m.fltSel = max(0, min(m.fltSel, n-1))
	}
	ch := m.fltChoices()
	m.fltFilter = min(m.fltFilter, len(ch)-1)
	var wins, loses int
	var sum float64
	for _, it := range items {
		if it.Scored {
			sum += it.Sol
			if it.Sol > 0 {
				wins++
			} else {
				loses++
			}
		}
	}
	left := t.Acc.Render(m.fltChoiceName(ch[m.fltFilter])) + t.Lbl.Render(fmt.Sprintf("  (%s)", core.IC(int64(n))))
	if !(fltSortKeys[m.fltSort] == "time" && !m.fltAsc) {
		arrow := m.g("▼", "v")
		if m.fltAsc {
			arrow = m.g("▲", "^")
		}
		left += t.Lbl.Render("  sort ") + t.Acc.Render(fltSortKeys[m.fltSort]+" "+arrow)
	}
	if hidden > 0 {
		left += t.Dim.Render(fmt.Sprintf("  +%s no dip (n)", core.IC(int64(hidden))))
	} else if m.fltAll {
		left += t.Dim.Render("  with no-dip (n)")
	}
	if shadowHid > 0 {
		left += t.Dim.Render(fmt.Sprintf("  +%s shadow (v)", core.IC(int64(shadowHid))))
	} else if m.fltShadow {
		left += t.Dim.Render("  with shadow (v)")
	}
	rt := t.Neg.Render(fmt.Sprintf("%dW", wins)) + t.Lbl.Render(" ") + t.Pos.Render(fmt.Sprintf("%dL", loses)) + t.Lbl.Render("  ") + m.invCell(sum, 1, false)
	if w >= 110 {
		rt += t.Dim.Render("   f filter  n no-dip  v shadow  o sort  O order  c copy")
	}
	if w >= 100 && !m.fltTblFocus {
		left += t.Dim.Render("   " + m.g("\u2191", "up") + " from the first row: back to the filters")
	}
	out = append(out, m.rule("SKIPPED / BLOCKED", "", w))
	out = append(out, lr(left, rt, w))
	rowsAvail := bh - len(out)
	if rowsAvail < 3 { // a short terminal: the list keeps 3 rows, the table gives way
		drop := 3 - rowsAvail
		head := out[:len(out)-2]
		if drop < len(head) {
			head = head[:len(head)-drop]
		} else {
			head = head[:1]
		}
		out = append(append([]string(nil), head...), out[len(out)-2:]...)
		rowsAvail = max(1, bh-len(out))
	}
	rowsAvail-- // the header
	if rowsAvail < 1 {
		rowsAvail = 1
	}
	if m.fltSel < m.fltTop {
		m.fltTop = m.fltSel
	}
	if m.fltSel >= m.fltTop+rowsAvail {
		m.fltTop = m.fltSel - rowsAvail + 1
	}
	m.fltTop = max(0, min(m.fltTop, max(0, n-rowsAvail)))
	if n == 0 {
		out = append(out, t.Lbl.Render("nothing blocked here"+map[bool]string{true: " that would have filled (n shows the rest)", false: ""}[hidden > 0]))
		m.fltRowY = 0
		return strings.Join(out, "\n")
	}
	m.fltRowY = m.bodyY + len(out) + 1
	vis := items[m.fltTop:min(n, m.fltTop+rowsAvail)]
	lsel := m.fltSel - m.fltTop
	if m.fltTblFocus { // the cursor is in the table: no marker in the list
		lsel = -1
	}
	out = append(out, m.fltList(w, vis, lsel))
	if n > rowsAvail {
		m.moreHint = fmt.Sprintf("%d/%d", m.fltSel+1, n)
	}
	return strings.Join(out, "\n")
}

// fltMove: a LIVE row's shadow-window price move, max / min vs the trigger's post price, rounded ("+35/-8%", "+4/0%"); "–" when the
// record has no "move" (runs before 11-03), "0 trades" when nothing traded in the window.
func fltMove(mv *core.FMove) string {
	if mv == nil {
		return core.G.Dash
	}
	if mv.N == 0 {
		return "0 trades"
	}
	r := func(x float64) string { // rounded, signed; 0 unsigned
		if v := int(math.Round(x)); v != 0 {
			return fmt.Sprintf("%+d", v)
		}
		return "0"
	}
	return r(mv.Max) + "/" + r(mv.Min) + "%"
}

// fltList: the skip list's rows (a header, the selection, zebra rows like Trades). The move column (a LIVE row's
// shadow-window price move) when the list has a LIVE row and the width allows (>= 76 cells).
func (m *Model) fltList(w int, rows []core.FiltItem, sel int) string {
	t := m.th
	type col struct {
		title string
		w     int
		right bool
	}
	mintW := 8
	if w >= 150 {
		mintW = 44
	}
	showMove := false
	for _, it := range m.fltRows {
		if it.Live {
			showMove = true
			break
		}
	}
	moveW := 0
	if showMove {
		moveW = 10 // 9 cells + the gap
	}
	var cols []col
	switch {
	case w >= 90: // the filter column: up to 42 cells (a LOG fill's every rule), the note keeps >= 12
		fw := max(22, min(42, w-(1+11+4+4+mintW+6+8+9+moveW)-12))
		cols = []col{{"", 1, false}, {"time", 11, true}, {"type", 4, false}, {"filter", fw, false}, {"kind", 4, false}, {"mint", mintW, false}, {"result", 6, false}, {"SOL", 8, true}}
		if showMove {
			cols = append(cols, col{"move", 9, true})
		}
		cols = append(cols, col{"", 0, false})
	case w >= 66:
		cols = []col{{"", 1, false}, {"time", 11, true}, {"type", 4, false}, {"filter", 16, false}, {"kind", 4, false}, {"mint", 8, false}, {"result", 6, false}, {"SOL", 8, true}}
		if showMove && w >= 76 {
			cols = append(cols, col{"move", 9, true})
		}
	default:
		cols = []col{{"", 1, false}, {"time", 11, true}, {"ty", 2, false}, {"filter", 10, false}, {"mint", 6, false}, {"res", 4, false}, {"SOL", 7, true}}
	}
	fixed := 0
	for _, c := range cols {
		fixed += c.w + 1
	}
	if last := &cols[len(cols)-1]; last.w == 0 {
		last.w = max(1, w-fixed)
	}
	cell := func(s string, c col) string {
		s = ansi.Truncate(s, c.w, "…")
		if c.right {
			return padLeft(s, c.w)
		}
		return padRight(s, c.w)
	}
	var b strings.Builder
	for i, c := range cols {
		h := c.title
		if sortKeyFlt(c.title) == fltSortKeys[m.fltSort] && h != "" {
			arrow := m.g("▼", "v")
			if m.fltAsc {
				arrow = m.g("▲", "^")
			}
			h = arrow + h
		}
		st := t.Lbl
		if sortKeyFlt(c.title) == fltSortKeys[m.fltSort] && h != "" {
			st = t.Acc.Bold(true)
		}
		b.WriteString(st.Render(cell(h, c)))
		if i < len(cols)-1 {
			b.WriteString(" ")
		}
	}
	lines := []string{b.String()}
	for i, it := range rows {
		var parts []string
		for _, c := range cols {
			var s string
			st := t.Val
			switch c.title {
			case "":
				if c.w == 1 && i == sel {
					s = m.g("▸", ">")
				}
				if c.w != 1 {
					st = t.Dim
					if !it.Live {
						s = "real fill"
						if it.Has("guard") {
							s = fmt.Sprintf("real fill; guard set %.1f%% at landing", it.GuardPct)
						}
					} else if it.Filter == "deeper" {
						s = "shadow window of the trigger"
					} else {
						s = "shadow window"
					}
				}
			case "time":
				st = t.Lbl
				if it.T != 0 {
					s = core.T12(float64(it.T), true)
				}
			case "type", "ty":
				tag := "LIVE"
				if !it.Live {
					tag = "LOG"
				}
				if c.w == 2 {
					tag = map[bool]string{true: "LV", false: "LG"}[it.Live]
				}
				s = tag
				st = t.Warn
				if it.Live {
					st = t.AccB
				}
				// v5.2: the same circles as the table (green = live, violet = log)
				s, st = m.g("\u25cf", "*"), t.Good
				if !it.Live {
					s, st = m.g("\u25cf", "o"), lipgloss.NewStyle().Foreground(t.Violet)
				}
			case "filter": // a LOG fill: every rule that would have blocked it
				s = fltClean(it.Name)
				if ansi.StringWidth(s) > c.w {
					sh := make([]string, len(it.Rules))
					for j, r := range it.Rules {
						sh[j] = fltShort(r, it.Names[j])
					}
					s = strings.Join(sh, ", ")
				}
				if ansi.StringWidth(s) > c.w && len(it.Rules) > 1 { // narrow: the first rule + how many more, else the codes
					s = fmt.Sprintf("%s +%d", fltShort(it.Rules[0], it.Names[0]), len(it.Rules)-1)
					if ansi.StringWidth(s) > c.w {
						cs := make([]string, len(it.Rules))
						for j, r := range it.Rules {
							cs[j] = fltCode(r)
						}
						s = strings.Join(cs, "+")
					}
				}
			case "kind":
				s, st = it.Kind, t.Lbl
				if it.Kind == "RA" {
					st = t.Acc
				}
			case "mint":
				s = core.Short(it.Mint, c.w)
			case "result", "res":
				switch {
				case !it.Scored: // a LIVE skip whose shadow window never filled: the trade would not have happened
					s, st = "no dip", t.Dim
					if c.w == 4 {
						s = core.G.Dash
					}
				case it.Sol > 0: // a blocked winner: the filter cost us (red); a blocked loser: it saved us (green)
					s, st = "WIN", t.Neg
				default:
					s, st = "LOSE", t.Pos
				}
			case "SOL":
				if it.Scored {
					s, st = core.FS(it.Sol, 4), t.Money(lamOf(-it.Sol), true, false)
					if c.w < 8 {
						s = core.FS(it.Sol, 3)
					}
				} else if it.Live { // no dip: nothing saved or lost
					s, st = "0.000", t.Dim
				} else {
					s, st = core.G.Dash, t.Dim
				}
			case "move": // LIVE rows only: the shadow window's price move
				if it.Live {
					s, st = fltMove(it.Move), t.Lbl
					if it.Move == nil || it.Move.N == 0 {
						st = t.Dim
					}
				}
			}
			txt := cell(s, c)
			if c.title == "mint" && m.linksOn() && it.Mint != "" { // OSC 8: the mint opens GMGN
				st = st.Hyperlink(gmgnURL(it.Mint))
			}
			if !t.Mono && i%2 == 1 {
				st = st.Background(t.Zebra)
			}
			if i == sel {
				st = st.Background(t.SelBg).Bold(true)
				if t.Mono {
					st = st.Reverse(true)
				}
			}
			parts = append(parts, st.Render(txt))
		}
		sp := lipgloss.NewStyle()
		if !t.Mono && i%2 == 1 {
			sp = sp.Background(t.Zebra)
		}
		if i == sel {
			sp = sp.Background(t.SelBg)
		}
		lines = append(lines, strings.Join(parts, sp.Render(" ")))
	}
	return strings.Join(lines, "\n")
}

func sortKeyFlt(title string) string {
	switch title {
	case "ty", "type":
		return "" // LIVE / LOG: the filter sort groups them
	case "res", "result":
		return "result"
	}
	return title
}

// fltTrade: the LOG item's position in the trades (enter opens its details); nil for a LIVE item.
func (m *Model) fltTrade(it core.FiltItem) *core.Trade {
	if it.Live {
		return nil
	}
	for _, tr := range m.view.Trades {
		if tr.Kind == "PS" && tr.Mint == it.Mint && tr.W.Ok && tr.W.W == it.W {
			return tr
		}
	}
	return nil
}

// fltDip: for a LIVE row with no scored skip: how many of its skips are "no dip" (probes / the shadow window say the price never
// reached our limit) and how many cannot be priced (re-arm windows without probes). From the Trades tab's skip rows (skips.go).
func (m *Model) fltDip(key string) (nodip, unknown int) {
	if m.view == nil {
		return 0, 0
	}
	for i := range m.view.Skips {
		r := &m.view.Skips[i]
		if r.Why != key && strings.TrimPrefix(r.Why, "rearm_") != key {
			continue
		}
		switch {
		case r.NoDip():
			nodip++
		case !r.HasPaper && !r.HasProbePnl:
			unknown++
		}
	}
	return nodip, unknown
}

// ------------------------------------------------------------------------------------------------- a filter's page (v5.3)

// fltPageRows: everything the filter blocked, as Trades-table rows: a LIVE filter's skipped triggers / withheld windows (the
// Trades tab's skip rows), a LOG rule's real fills it would have blocked (the real trades), newest first.
func (m *Model) fltPageRows(key string) []*core.Trade {
	var out []*core.Trade
	if m.view == nil || m.view.Filt == nil {
		return nil
	}
	for _, tr := range m.view.SkipTrades {
		if r := tr.Skip; r.Why == key || strings.TrimPrefix(r.Why, "rearm_") == key {
			out = append(out, tr)
		}
	}
	seen := map[*core.Trade]bool{}
	for _, it := range m.view.Filt.Items {
		if it.Live {
			continue
		}
		hit := false
		for _, r := range it.Rules {
			if r == key {
				hit = true
			}
		}
		if !hit {
			continue
		}
		if tr := m.fltTrade(it); tr != nil && !seen[tr] {
			seen[tr] = true
			out = append(out, tr)
		}
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].T > out[j].T })
	return out
}

// scrFilterPage: one filter: what it is, its numbers, then every trigger / fill it blocked in the Trades table (enter on a real
// trade opens its details, c copies the mint, esc goes back).
func (m *Model) scrFilterPage(w, bh int) string {
	t := m.th
	R := m.view.Filt
	row, ok := R.Row(m.fltOpen)
	if !ok {
		m.fltOpen = ""
		return m.scrFilters(w, bh)
	}
	live := row.Type == "LIVE"
	mode := "log: it only marks what it would block"
	if live {
		mode = "live: it blocks trades"
	}
	out := []string{m.rule("FILTER", t.Dim.Render("esc back   enter trade details   c copy mint"), w)}
	out = append(out, m.fltTag(live, false)+" "+t.B.Render(fltClean(row.Name))+t.Lbl.Render("   "+mode))
	if what := fltWhat(row.Key, fltVerdictOf(row).why); what != "" {
		out = append(out, t.Lbl.Render("  what    ")+t.Val.Render(cut(what, max(10, w-10))))
	}
	rows := m.fltPageRows(m.fltOpen)
	m.fltOpenRows = rows
	var sk []core.SkipRow
	nReal, realW := 0, 0
	var realSum int64
	for _, x := range rows {
		if x.Skip != nil {
			sk = append(sk, *x.Skip)
		} else if x.HasPnl {
			nReal++
			realSum += x.Pnl
			if x.Pnl > 0 {
				realW++
			}
		}
	}
	saved, src := row.ShownNet(), "paper"
	if row.Cal {
		src = "calibrated"
	} else if !live {
		src = "real fills"
	}
	num := t.Lbl.Render("  saved   ") + m.solCell(saved, row.WinN+row.LoseN+row.CalWinN+row.CalLoseN, true) + t.Lbl.Render(" ("+src+")   blocked ") + t.Val.Render(core.IC(int64(row.Blocked)))
	wn, ln, ws, ls := row.WinN, row.LoseN, row.WinSol, row.LoseSol
	if row.Cal {
		wn, ln, ws, ls = row.CalWinN, row.CalLoseN, row.CalWinSol, row.CalLoseSol
	}
	num += t.Lbl.Render("   would win ") + t.Neg.Render(fmt.Sprint(wn)) + " " + m.invCell(ws, wn, false) + t.Lbl.Render("   would lose ") + t.Pos.Render(fmt.Sprint(ln)) + " " + m.invCell(ls, ln, false)
	out = append(out, cut(num, w))
	if len(sk) > 0 {
		st := core.SumSkips(sk)
		l := t.Lbl.Render(fmt.Sprintf("  skips   %d", st.N)) + t.Dim.Render(fmt.Sprintf("   no dip %d   paper %dW/%dL %s", st.NoFill, st.WinN, st.LoseN, core.FS(st.Paper, 3)))
		if st.CalN > 0 {
			l += t.Dim.Render("   cal " + core.FS(st.Cal, 3))
		}
		if st.ProbeN > 0 {
			l += t.Dim.Render(fmt.Sprintf("   probes %d %s", st.ProbeN, core.FS(st.Probe, 3)))
		}
		if un := st.N - st.NoFill - st.Scored - st.ProbeN; un > 0 {
			l += t.Dim.Render(fmt.Sprintf("   n/a %d", un))
		}
		out = append(out, cut(l, w))
	}
	if nReal > 0 {
		out = append(out, t.Lbl.Render(fmt.Sprintf("  fills   %d real fills it would have blocked: %dW/%dL ", nReal, realW, nReal-realW))+t.Money(realSum, true, false).Render(core.SolS(realSum)))
	}
	n := len(rows)
	if n == 0 {
		out = append(out, "", t.Lbl.Render("nothing blocked yet in this run"))
		m.fltOpenSel, m.fltOpenTop = 0, 0
		return strings.Join(out, "\n")
	}
	m.fltOpenSel = max(0, min(m.fltOpenSel, n-1))
	var why []string
	if cur := rows[m.fltOpenSel]; cur.Skip != nil {
		why = m.skipLines(cur.Skip, w)
	}
	rowsAvail := max(1, bh-len(out)-1-len(why))
	if m.fltOpenSel < m.fltOpenTop {
		m.fltOpenTop = m.fltOpenSel
	}
	if m.fltOpenSel >= m.fltOpenTop+rowsAvail {
		m.fltOpenTop = m.fltOpenSel - rowsAvail + 1
	}
	m.fltOpenTop = max(0, min(m.fltOpenTop, max(0, n-rowsAvail)))
	vis := rows[m.fltOpenTop:min(n, m.fltOpenTop+rowsAvail)]
	out = append(out, m.tradeTable(w, vis, m.fltOpenSel-m.fltOpenTop))
	out = append(out, why...)
	if n > rowsAvail {
		m.moreHint = fmt.Sprintf("%d/%d", m.fltOpenSel+1, n)
	}
	return strings.Join(out, "\n")
}
