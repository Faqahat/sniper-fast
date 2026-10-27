package core

import (
	"math"
	"math/big"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

// ------------------------------------------------------------------------------------------------- number text

// Sol is Python's sol(lam, d, sign): "+0.1234" ("–" for None).
func Sol(lam int64, ok bool, d int, sign bool) string {
	if !ok {
		return G.Dash
	}
	v := float64(lam) / LAM
	if sign {
		return FS(v, d)
	}
	return F(v, d)
}

// SolAuto is a signed SOL amount with 3 decimals, more when it would round to zero (a drawdown of a few fees must
// not read "-0.000").
func SolAuto(lam int64) string {
	a := lam
	if a < 0 {
		a = -a
	}
	switch {
	case lam == 0 || a >= 500_000:
		return Sol(lam, true, 3, true)
	case a >= 50_000:
		return Sol(lam, true, 4, true)
	}
	return Sol(lam, true, 6, true)
}

// SolS is Sol with the defaults (4 decimals, signed).
func SolS(lam int64) string { return Sol(lam, true, 4, true) }

// Usd is Python's usd(lam, price, sign, d): "+$12.34" / "$12.34" / "USD n/a".
func Usd(lam int64, ok bool, price float64, sign bool, d int) string {
	if !ok || price == 0 {
		return "USD n/a"
	}
	v := float64(lam) / LAM * price
	if sign {
		s := "+"
		if v < 0 {
			s = "-"
		}
		return s + "$" + FC(math.Abs(v), d)
	}
	return "$" + FC(v, d)
}

// UsdAmt is a USD amount without a sign: $555.6 / $55.62 / $1.9K.
func UsdAmt(lam int64, ok bool, price float64, k bool) string {
	if !ok || price == 0 {
		return "USD n/a"
	}
	x := math.Abs(float64(lam) / LAM * price)
	if k && x >= 1000 {
		return "$" + F(x/1000, 1) + "K"
	}
	if x >= 100 {
		return "$" + FC(x, 1)
	}
	return "$" + FC(x, 2)
}

// PctS is pct_s(x, d, sign).
func PctS(x float64, ok bool, d int, sign bool) string {
	if !ok {
		return G.Dash
	}
	if sign {
		return FS(x*100, d) + "%"
	}
	return F(x*100, d) + "%"
}

// Med is the median (None when empty).
func Med(v []float64) (float64, bool) {
	if len(v) == 0 {
		return 0, false
	}
	s := append([]float64(nil), v...)
	sort.Float64s(s)
	n := len(s)
	if n%2 == 1 {
		return s[n/2], true
	}
	return (s[n/2-1] + s[n/2]) / 2, true
}

// Short is (m or "?")[:n].
func Short(m string, n int) string {
	if m == "" {
		m = "?"
	}
	return RuneSlice(m, n)
}

// sol2 is _sol2(lam): "0.35" / "?".
func sol2(n Num) string {
	if !n.Ok() {
		return "?"
	}
	return F(n.Float()/LAM, 2)
}

// fmtAny is f"{x}" for a config value.
func fmtAny(v any) string {
	switch x := v.(type) {
	case nil:
		return "None"
	case Num:
		return x.Repr()
	case string:
		return x
	case bool:
		if x {
			return "True"
		}
		return "False"
	}
	return PyStr(v)
}

func truthyAny(v any) bool {
	switch x := v.(type) {
	case nil:
		return false
	case Num:
		return x.Truthy()
	case string:
		return x != ""
	case bool:
		return x
	}
	return Truthy(v)
}

// ------------------------------------------------------------------------------------------------- aggregates

// ExitAgg: (n, wins, pnl) for one exit reason.
type ExitAgg struct{ N, Wins, Pnl int64 }

// OExits is an insertion-ordered map of exit reason -> ExitAgg.
type OExits struct {
	Keys []string
	M    map[string]*ExitAgg
}

func newOExits() *OExits { return &OExits{M: map[string]*ExitAgg{}} }

func (o *OExits) get(k string) *ExitAgg {
	e := o.M[k]
	if e == nil {
		e = &ExitAgg{}
		o.M[k] = e
		o.Keys = append(o.Keys, k)
	}
	return e
}

// Sorted is the exits by count, descending (ties in first-seen order).
func (o *OExits) Sorted() []string {
	ks := append([]string(nil), o.Keys...)
	sort.SliceStable(ks, func(i, j int) bool { return o.M[ks[i]].N > o.M[ks[j]].N })
	return ks
}

// AggPS: the pre-send figures over the selected sessions.
type AggPS struct {
	Active                                  bool
	Fills, Wins, NReal                      int64
	Real, Rent, Fees, FeesCnt, FeesEng, Net int64
	FeeN, Sent, Dry, Armed                  int64
	Res, Skips, Disarms, EndChk, FeeEach    *OCounter
	Exits                                   *OExits
	LandMs                                  []float64
	After                                   []Num
	Best, Worst                             *Trade
	QSkips, QStops, QWould                  int64
	Paper                                   bool
	PaperFills                              int64
	PaperGross, PaperNet                    float64
	Held, ATAFail, NotSold, OpenPos, Closed int64
	StopFees                                int64
	AllStopped                              bool
	hasAllStopped                           bool
}

func aggPS(sessions []*Sess) AggPS {
	A := AggPS{Res: NewOCounter(), Skips: NewOCounter(), Disarms: NewOCounter(), EndChk: NewOCounter(), FeeEach: NewOCounter(),
		Exits: newOExits()}
	for _, S := range sessions {
		if S.Paper != nil {
			A.Paper = true
			A.PaperFills += S.Paper.Fills
			A.PaperGross += S.Paper.Gross
			A.PaperNet += S.Paper.Net
		}
		if !S.PSActive() {
			continue
		}
		A.Active = true
		A.Fills += S.PSFills
		A.Wins += S.PSWins
		A.NReal += S.PSNReal
		A.Real += S.PSRealized
		A.Rent += S.PSRent
		A.FeesCnt += S.PSFeeCnt
		A.FeeN += S.PSFeeN
		A.Sent += S.PSSent
		A.Dry += S.PSDry
		A.Armed += S.PSArmed
		A.QSkips += S.QSkips
		A.QStops += S.QStops
		A.QWould += S.QWould
		A.Held += S.PSHeld
		A.ATAFail += S.PSATAFail
		if !S.PSRec { // an old run: only the log's PRESEND LIVE lines
			A.Fills += int64(len(S.LogPSReal))
			for _, x := range S.LogPSReal {
				A.Real += x
				if x > 0 {
					A.Wins++
				}
			}
			A.NReal += int64(len(S.LogPSReal))
		}
		if S.PSRec {
			A.Fees += S.PSFees()
		} else {
			A.Fees += S.LogPSFees
		}
		stop := S.stopFeesMax()
		A.FeesEng += max(S.LogPSFees, stop)
		A.StopFees += stop
		if !A.hasAllStopped {
			A.AllStopped, A.hasAllStopped = true, true
		}
		A.AllStopped = A.AllStopped && len(S.PSStop) > 0
		A.Net += S.PSNet()
		A.Res.Update(S.PSRes)
		A.Skips.Update(S.PSSkips)
		A.Disarms.Update(S.PSDisarms)
		A.EndChk.Update(S.PSEndChk)
		A.FeeEach.Update(S.PSFeeEach)
		A.LandMs = append(A.LandMs, S.PSLandMs...)
		A.After = append(A.After, S.PSAfter...)
		for _, tr := range S.PSList {
			if tr.PClose == nil && !tr.HasPnl {
				A.OpenPos++
				continue
			}
			A.Closed++
			if tr.Res != "sold" && tr.Res != "?" && tr.Res != "" && tr.PClose != nil {
				A.NotSold++
			}
			why := "?"
			if tr.HasPExit && tr.PExit != "" {
				why = tr.PExit
			}
			e := A.Exits.get(why)
			e.N++
			if tr.HasPnl && tr.Pnl > 0 {
				e.Wins++
			}
			if tr.HasPnl {
				e.Pnl += tr.Pnl
			}
			if tr.HasPnl {
				if A.Best == nil || tr.Pnl > A.Best.Pnl {
					A.Best = tr
				}
				if A.Worst == nil || tr.Pnl < A.Worst.Pnl {
					A.Worst = tr
				}
			}
		}
	}
	return A
}

// KindAgg: (buys, fills, wins, pnl) for one leader-client family.
type KindAgg struct{ Buys, Fills, Wins, Pnl int64 }

// AggReg: the regular bot's figures over the selected sessions.
type AggReg struct {
	Fires, Fills, Wins, Guard, Lighthouse, Failed, NotL, Open int64
	FillPnl, FailPnl, Total                                   int64
	Est                                                       int64
	Exits                                                     *OExits
	KindKeys                                                  []string
	Kinds                                                     map[string]*KindAgg
	LandMs                                                    []float64
	Same                                                      int64
	OpenList                                                  []*Trade
	Skipped                                                   *OCounter
	Picks, Dumps                                              int64
	Best, Worst                                               *Trade
	FailMs                                                    []float64
}

func aggReg(sessions []*Sess) AggReg {
	R := AggReg{Exits: newOExits(), Kinds: map[string]*KindAgg{}, Skipped: NewOCounter()}
	for _, S := range sessions {
		R.Dumps += S.Dumps
		R.Picks += S.Picks
		var sk *OCounter
		if S.RE != nil && Truthy(S.RE.Skipped) {
			if m, ok := S.RE.Skipped.(map[string]any); ok {
				sk = NewOCounter()
				keys := make([]string, 0, len(m))
				for k := range m {
					keys = append(keys, k)
				}
				sort.Strings(keys) // the engine writes sorted keys
				for _, k := range keys {
					if b, isB := m[k].(bool); isB {
						if b {
							sk.Add(k, 1)
						} else {
							sk.Add(k, 0)
						}
					} else if n := toNum(m[k]); n.K == NumInt {
						sk.Add(k, n.I)
					}
				}
			} else {
				sk = nil
			}
		} else if S.Status.Skipped != nil && S.Status.Skipped.Len() > 0 {
			sk = S.Status.Skipped
		}
		R.Skipped.Update(sk)
		for _, tr := range S.Reg {
			R.Fires++
			res := tr.Res
			p, hp := tr.Pnl, tr.HasPnl
			if hp {
				R.Total += p
			}
			kn := KindOf(tr.Client)
			k := R.Kinds[kn]
			if k == nil {
				k = &KindAgg{}
				R.Kinds[kn] = k
				R.KindKeys = append(R.KindKeys, kn)
			}
			k.Buys++
			if hp {
				k.Pnl += p
			}
			switch {
			case res == "filled":
				R.Fills++
				k.Fills++
				if hp {
					R.FillPnl += p
				}
				if hp && p > 0 {
					R.Wins++
					k.Wins++
				}
				if tr.Src != "tx" {
					R.Est++
				}
				if tr.Land != nil {
					if tr.Land.Ms.Ok() {
						R.LandMs = append(R.LandMs, tr.Land.Ms.Float())
					}
					if tr.Land.Blk.Ok() && tr.Land.Blk.Float() == 0 {
						R.Same++
					}
				}
				if tr.Close == nil {
					R.Open++
					R.OpenList = append(R.OpenList, tr)
				} else {
					why := "?"
					if tr.Close.HasWhy && tr.Close.Why != "" {
						why = tr.Close.Why
					} else if tr.Exit != nil && tr.Exit.HasWhy && tr.Exit.Why != "" {
						why = tr.Exit.Why
					}
					e := R.Exits.get(why)
					e.N++
					if hp && p > 0 {
						e.Wins++
					}
					if hp {
						e.Pnl += p
					}
				}
				if hp {
					if R.Best == nil || p > R.Best.Pnl {
						R.Best = tr
					}
					if R.Worst == nil || p < R.Worst.Pnl {
						R.Worst = tr
					}
				}
			case res == "guard" || res == "lighthouse" || res == "failed":
				switch res {
				case "guard":
					R.Guard++
				case "lighthouse":
					R.Lighthouse++
				default:
					R.Failed++
				}
				if hp {
					R.FailPnl += p
				}
				if tr.Failed != nil && tr.Failed.T.Truthy() && tr.TDump.Truthy() {
					R.FailMs = append(R.FailMs, float64(tr.Failed.T.Int()-tr.TDump.Int())/1e6)
				}
			case res == "open":
				R.Open++
				R.OpenList = append(R.OpenList, tr)
			default:
				R.NotL++
			}
		}
	}
	return R
}

// ------------------------------------------------------------------------------------------------- the view

// Ctx is what a view needs besides the model.
type Ctx struct {
	Src           *Source
	Engine        *Engine
	Price         *Price
	Sys           *SysInfo
	BudgetPath    string
	budget        *Budget
	budgetT       time.Time
	FixedNow      float64
	AssumeRunning bool
}

// Now is the wall clock (seconds), or --now.
func (c *Ctx) Now() float64 {
	if c.FixedNow != 0 {
		return c.FixedNow
	}
	return float64(time.Now().UnixNano()) / 1e9
}

func (c *Ctx) readBudget() {
	if c.BudgetPath != "" && time.Since(c.budgetT) > 60*time.Second {
		c.budgetT = time.Now()
		c.budget = ReadBudget(c.BudgetPath)
	}
}

// CfgItem is one config badge: key, label, state on|off|part|na, short and full text.
type CfgItem struct {
	Key, Label, SLabel, State, Short, Full string
}

// Alert is (level bad|warn|end|info, text).
type Alert struct{ Level, Text string }

// QuietState is quiet_state(): present, stop, skip, state, on_at, preload, preload_h.
type QuietState struct {
	Present  bool
	Stop     string
	HasStop  bool
	Skip     bool
	HasSkip  bool
	State    string
	OnAt     int64
	HasOnAt  bool
	Preload  string
	PreloadH Num
}

// View is build_view(): everything the screens and the snapshot show.
type View struct {
	Now                        float64
	NSess                      int
	Scope                      int // -1 = all sessions
	S, Cur                     *Sess
	Region                     string
	Run                        int
	HasRun                     bool
	Build                      string
	BuildLive                  bool
	Price                      float64
	PriceAge                   float64
	PriceAgeOK                 bool
	PriceSrc                   string
	LastWrite                  float64
	WriteAge, LogAge, JSONLAge float64
	HasWrite, HasLogA, HasJA   bool
	TFirst                     int64
	Status                     string
	Running                    bool
	TEnd                       int64
	NowNSInt                   int64
	NowNSIsInt                 bool
	NowNSF                     float64
	ST0                        int64
	Elapsed, SElapsed          float64
	HasElapsed, HasSElapsed    bool
	Planned                    Num
	EndsAt                     float64
	HasEndsAt                  bool
	STEnd                      int64
	HowEnded                   string
	PS                         AggPS
	Reg                        AggReg
	Total                      int64
	PerHour                    float64
	HasPerHour                 bool
	PSCfg                      map[string]any
	PSFailEach                 int64
	PSStopped                  string
	PSOpenNow                  int64
	StartBal                   int64
	HasStartBal                bool
	RunStartBal                int64
	HasRunStartBal             bool
	STotal                     int64
	EstNow                     int64
	HasEstNow                  bool
	KillLevel                  int64
	HasKillLevel               bool
	LossCapN                   Num
	KillDist                   int64
	HasKillDist                bool
	LossUsed                   float64
	HasLossUsed                bool
	BudgetLeft, BudgetMax      int64
	HasBudget                  bool
	Series                     []int64
	SeriesM0                   int64
	Best, Worst                [2]float64 // (value, time ns)
	HasBest                    bool
	Trades                     []*Trade
	Sessions                   []*Sess
	Quiet                      QuietState
	CfgItems                   []CfgItem
	Alerts                     []Alert
	Model                      *Model
}

// NowNS is now_ns as a float.
func (v *View) NowNS() float64 {
	if v.NowNSIsInt {
		return float64(v.NowNSInt)
	}
	return v.NowNSF
}

// subNS is (now_ns - t) / 1e9 with Python's int / float semantics.
func (v *View) subNS(t int64) float64 {
	if v.NowNSIsInt {
		return float64(v.NowNSInt-t) / 1e9
	}
	return (v.NowNSF - float64(t)) / 1e9
}

// ItemByKey returns a config item.
func (v *View) ItemByKey(k string) *CfgItem {
	for i := range v.CfgItems {
		if v.CfgItems[i].Key == k {
			return &v.CfgItems[i]
		}
	}
	return nil
}

// InferBuild: the engine's build (dip20 ...) from its process, else inferred from the records.
func InferBuild(S *Sess, eng *Engine) (string, bool) {
	if eng != nil {
		e := eng.Snapshot()
		if e.PID != 0 && e.Build != "" {
			return e.Build, true
		}
	}
	if S.Quiet.Line || S.RS.Quiet != nil {
		return "dip20", false
	}
	if S.PSEndChk.Len() > 0 || S.PSRent != 0 || S.EndCheck != nil {
		return "dip19", false
	}
	if S.PSRec {
		return "dip13+", false
	}
	return "?", false
}

func (S *Sess) killTruthy() bool   { return S.KillSet && (!S.KillIsFloat || S.Kill != 0) }
func (S *Sess) signalTruthy() bool { return S.HasSignal && S.Signal != "" }

// pyGE is Python's exact `float >= int`.
func pyGE(f float64, i int64) bool {
	if math.IsNaN(f) {
		return false
	}
	if math.IsInf(f, 0) {
		return f > 0
	}
	return new(big.Float).SetFloat64(f).Cmp(new(big.Float).SetInt64(i)) >= 0
}

// BuildView is build_view(ctx, scope): scope -1 = all sessions.
func BuildView(ctx *Ctx, scope int) *View {
	M := ctx.Src.Model
	now := ctx.Now()
	v := &View{Now: now, Model: M}
	sessions := M.Sessions
	if len(sessions) == 0 {
		sessions = []*Sess{newSess(0)}
	}
	v.NSess = len(sessions)
	v.Scope = -1
	if scope >= 0 && scope < len(sessions) {
		v.Scope = scope
	}
	sel := sessions
	S := sessions[len(sessions)-1]
	if v.Scope >= 0 {
		sel = []*Sess{sessions[v.Scope]}
		S = sessions[v.Scope]
	}
	v.S = S
	v.Cur = sessions[len(sessions)-1]
	v.Region = ctx.Src.Region
	if v.Region == "" {
		v.Region = "?"
	}
	v.Run, v.HasRun = ctx.Src.Run, ctx.Src.HasRun
	eng := ctx.Engine
	v.Build, v.BuildLive = InferBuild(v.Cur, eng)
	if ctx.Price != nil {
		v.Price, v.PriceSrc, v.PriceAge, v.PriceAgeOK, _, _ = ctx.Price.Get()
	}
	// ---- status
	cur := v.Cur
	alive := eng.Alive() || ctx.AssumeRunning
	jm, lm := ctx.Src.TJ.MTime, ctx.Src.TL.MTime
	v.LastWrite = math.Max(jm, lm)
	if v.LastWrite != 0 {
		v.WriteAge, v.HasWrite = now-v.LastWrite, true
	}
	if lm != 0 {
		v.LogAge, v.HasLogA = now-lm, true
	}
	if jm != 0 {
		v.JSONLAge, v.HasJA = now-jm, true
	}
	tf := int64(0)
	for _, x := range sessions {
		if x.T0 != 0 && (tf == 0 || x.T0 < tf) {
			tf = x.T0
		}
	}
	if tf == 0 {
		tf = M.CurT
	}
	v.TFirst = tf
	engSeen := eng != nil && eng.Snapshot().Seen
	switch {
	case len(M.Sessions) == 0 || (cur.T0 == 0 && !cur.HasLive && M.JLines == 0):
		v.Status = "WAITING"
	case cur.Ended():
		v.Status = "ENDED"
	case alive:
		plannedEnd, hasPE := 0.0, false
		if cur.T0 != 0 && cur.Minutes().Truthy() {
			plannedEnd, hasPE = float64(cur.T0)+cur.Minutes().Float()*60e9, true
		}
		if cur.signalTruthy() || cur.killTruthy() || (hasPE && plannedEnd != 0 && now*1e9 > plannedEnd) {
			v.Status = "STOPPING"
		} else {
			v.Status = "RUNNING"
		}
	case engSeen || (v.HasWrite && v.WriteAge < 600):
		v.Status = "ENGINE GONE"
	default:
		v.Status = "NO END RECORD"
	}
	v.Running = v.Status == "RUNNING" || v.Status == "STOPPING"
	tEnd := cur.TEnd()
	if tEnd == 0 && cur.Ended() {
		tEnd = cur.CurT
	}
	v.TEnd = tEnd
	if v.Running || v.Status == "WAITING" {
		v.NowNSF = now * 1e9
	} else if tEnd != 0 {
		v.NowNSInt, v.NowNSIsInt = tEnd, true
	} else if M.CurT != 0 {
		v.NowNSInt, v.NowNSIsInt = M.CurT, true
	} else {
		v.NowNSF = now * 1e9
	}
	if v.Status == "ENGINE GONE" || v.Status == "NO END RECORD" {
		if M.CurT != 0 {
			v.NowNSInt, v.NowNSIsInt = M.CurT, true
		}
	}
	sT0 := S.T0
	if sT0 == 0 {
		sT0 = v.TFirst
	}
	v.ST0 = sT0
	if v.TFirst != 0 && sT0 != 0 {
		base := v.TFirst
		if v.Scope >= 0 {
			base = sT0
		}
		v.Elapsed, v.HasElapsed = v.subNS(base), true
	}
	if sT0 != 0 {
		v.SElapsed, v.HasSElapsed = v.subNS(sT0), true
	}
	v.Planned = S.Minutes()
	if sT0 != 0 && v.Planned.Truthy() {
		v.EndsAt, v.HasEndsAt = float64(sT0)+v.Planned.Float()*60e9, true
	}
	if S.Ended() && S.TEnd() != 0 {
		v.STEnd = S.TEnd()
	}
	if cur.Ended() || v.Status == "STOPPING" {
		switch {
		case cur.killTruthy():
			v.HowEnded = "kill switch"
		case cur.signalTruthy():
			if cur.Signal == "SIGINT" {
				v.HowEnded = "Ctrl+C"
			} else {
				v.HowEnded = cur.Signal
			}
		case cur.Ended():
			v.HowEnded = "time limit / max trades"
		}
	}
	// ---- money
	v.PS = aggPS(sel)
	v.Reg = aggReg(sel)
	v.Total = v.PS.Net + v.Reg.Total
	if v.HasElapsed && v.Elapsed != 0 && v.Elapsed > 60 {
		v.PerHour, v.HasPerHour = float64(v.Total)/(v.Elapsed/3600), true
	}
	v.PSCfg = map[string]any{}
	for k, x := range S.RS.PSL {
		v.PSCfg[k] = x
	}
	for k, x := range S.PSL {
		if _, ok := v.PSCfg[k]; !ok {
			v.PSCfg[k] = x
		}
	}
	if r, ok := v.PSCfg["routes"]; ok && truthyAny(r) {
		v.PSCfg["routes"] = rxParen.ReplaceAllString(fmtAny(r), "")
	}
	if v.PS.FeeEach.Len() > 0 {
		v.PSFailEach, _ = strconv.ParseInt(v.PS.FeeEach.MostCommon()[0].K, 10, 64)
	} else if ff, ok := v.PSCfg["fail_fee"].(Num); ok && ff.Truthy() {
		v.PSFailEach = ff.Int()
	} else {
		v.PSFailEach = PSFailFee
	}
	normal := func(x string) bool { return x == "run_end" || x == "run_stopping" }
	cands := []string{}
	if S.PSStopped != nil {
		cands = append(cands, S.PSStopped.Why)
	} else {
		cands = append(cands, "")
	}
	stopWhy := ""
	for _, x := range S.PSStop {
		w := x.Why
		if !x.HasWhy {
			w = ""
		}
		if !normal(w) || !x.HasWhy {
			if !x.HasWhy {
				stopWhy = ""
				break
			}
			stopWhy = w
			break
		}
	}
	cands = append(cands, stopWhy, S.Status.PSStopped)
	for _, x := range cands {
		if x != "" && !normal(x) {
			v.PSStopped = x
			break
		}
	}
	if v.Running {
		v.PSOpenNow = int64(len(S.PSOpenSet))
		if S.Status.HasPS && !S.PSRec {
			v.PSOpenNow = S.Status.PSNow
		}
	}
	// ---- wallet (the session's START BALANCE + its P&L; the kill switch is per session)
	v.StartBal, v.HasStartBal = S.StartBal, S.HasStartBal
	if v.Scope < 0 {
		v.RunStartBal, v.HasRunStartBal = sessions[0].StartBal, sessions[0].HasStartBal
	} else {
		v.RunStartBal, v.HasRunStartBal = S.StartBal, S.HasStartBal
	}
	v.STotal = S.Total()
	if S.HasStartBal {
		v.EstNow, v.HasEstNow = S.StartBal+v.STotal, true
	}
	v.KillLevel, v.HasKillLevel = S.KillLevel, S.HasKillLevel
	v.LossCapN = S.LossCap()
	if !v.HasKillLevel && S.HasStartBal && v.LossCapN.Truthy() {
		v.KillLevel, v.HasKillLevel = S.StartBal-v.LossCapN.Int(), true
	}
	if v.HasEstNow && v.HasKillLevel {
		v.KillDist, v.HasKillDist = v.EstNow-v.KillLevel, true
	}
	if v.HasStartBal && v.HasEstNow && v.LossCapN.Truthy() {
		v.LossUsed, v.HasLossUsed = math.Max(0.0, float64(v.StartBal-v.EstNow)/v.LossCapN.Float()), true
	}
	ctx.readBudget()
	if b := ctx.budget; b != nil && b.FirstStart.Truthy() && b.MaxTotalLoss.Truthy() && v.HasEstNow {
		v.BudgetLeft = b.MaxTotalLoss.Int() - max(0, b.FirstStart.Int()-v.EstNow)
		v.BudgetMax, v.HasBudget = b.MaxTotalLoss.Int(), true
	}
	// ---- series: cumulative P&L a minute
	buckets := map[int64]int64{}
	for _, x := range sel {
		for k, d := range x.Buckets {
			buckets[k] += d
		}
	}
	var bmin, bmax int64
	first := true
	for k := range buckets {
		if first || k < bmin {
			bmin = k
		}
		if first || k > bmax {
			bmax = k
		}
		first = false
	}
	base := v.TFirst
	if v.Scope >= 0 {
		base = sT0
	}
	var m0 int64
	if v.TFirst != 0 || sT0 != 0 {
		m0 = floorDiv(base, minuteNS)
	} else if len(buckets) > 0 {
		m0 = bmin
	}
	if len(buckets) > 0 {
		if m0 != 0 {
			m0 = min(m0, bmin)
		} else {
			m0 = bmin
		}
	}
	var m1 int64
	if v.NowNSIsInt {
		m1 = floorDiv(v.NowNSInt, minuteNS)
	} else {
		m1 = floorDiv(int64(v.NowNSF), minuteNS)
	}
	if len(buckets) > 0 {
		m1 = max(m1, bmax)
	}
	if m0 != 0 && m1 >= m0 && m1-m0 < 7*1440 {
		acc := int64(0)
		v.Series = make([]int64, 0, m1-m0+1)
		for mm := m0; mm <= m1; mm++ {
			acc += buckets[mm]
			v.Series = append(v.Series, acc)
		}
	}
	v.SeriesM0 = m0
	if len(v.Series) > 0 {
		hi, lo := 0, 0
		for i, x := range v.Series {
			if x > v.Series[hi] {
				hi = i
			}
			if x < v.Series[lo] {
				lo = i
			}
		}
		v.Best = [2]float64{float64(v.Series[hi]), float64(m0+int64(hi)) * 60e9}
		v.Worst = [2]float64{float64(v.Series[lo]), float64(m0+int64(lo)) * 60e9}
		v.HasBest = true
	}
	// ---- trades
	for _, t := range M.Trades {
		if v.Scope < 0 || t.S == v.Scope {
			v.Trades = append(v.Trades, t)
		}
	}
	v.Sessions = sessions
	v.Quiet = quietState(S, M, v)
	v.CfgItems = configItems(v, S, eng)
	v.Alerts = makeAlerts(v, ctx, M)
	return v
}

// BestVal / WorstVal: the series' high / low as lamports.
func (v *View) BestVal() int64  { return int64(v.Best[0]) }
func (v *View) WorstVal() int64 { return int64(v.Worst[0]) }

func resolveOnAt(S *Sess, M *Model) (int64, bool) {
	if S.QPreload != nil && S.QPreload.OnAt.Truthy() {
		return S.QPreload.OnAt.Int(), true
	}
	q := S.Quiet
	if q.HasOnHHMM {
		base := S.T0
		if base == 0 {
			base = M.CurT
		}
		return HHMMns(base, q.OnHHMM[0], q.OnHHMM[1])
	}
	if rq := S.RS.Quiet; rq != nil && Truthy(rawToJSON(rq.Skip)) && S.T0 != 0 && rq.WarmupMin.Ok() {
		return int64(float64(S.T0) + rq.WarmupMin.Float()*60e9), true
	}
	return 0, false
}

// rawToJSON undoes rawAny's Num wrapping for truthiness checks.
func rawToJSON(v any) any {
	if n, ok := v.(Num); ok {
		if n.Truthy() {
			return true
		}
		return false
	}
	return v
}

func quietState(S *Sess, M *Model, v *View) QuietState {
	rq := S.RS.Quiet
	q := S.Quiet
	out := QuietState{Present: rq != nil || q.Line, Preload: q.Preload, PreloadH: q.PreloadH}
	if !out.Present {
		return out
	}
	switch {
	case q.HasStop && q.Stop != "":
		out.Stop, out.HasStop = q.Stop, true
	case rq != nil && rq.HasStop:
		out.Stop, out.HasStop = rq.Stop, true
	}
	var sk bool
	if q.Skip >= 0 {
		sk = q.Skip == 1
	} else if rq != nil {
		sk = Truthy(rawToJSON(rq.Skip))
	}
	out.Skip, out.HasSkip = sk, true
	if out.Preload == "" && rq != nil && rq.Preload {
		out.Preload = "running"
	}
	if S.QPreload != nil {
		if Truthy(rawToJSON(S.QPreload.Ok)) {
			out.Preload = "done"
		} else {
			out.Preload = "failed"
		}
		if S.QPreload.CoveredH.Ok() {
			out.PreloadH = S.QPreload.CoveredH
		}
	}
	out.OnAt, out.HasOnAt = resolveOnAt(S, M)
	nowSec := v.NowNS() / 1e9 // quiet_state(S, M, now_ns / 1e9) compares now * 1e9 with on_at
	switch {
	case !out.Skip:
		out.State = "off"
	case q.RuleState == "on" || S.QRuleOn == 1:
		out.State = "on"
	case out.HasOnAt && out.OnAt != 0 && pyGE(nowSec*1e9, out.OnAt):
		out.State = "on"
	default:
		out.State = "warm-up"
	}
	return out
}

// ------------------------------------------------------------------------------------------------- config

var presetMaps = map[string]map[string][]string{}
var presetOrder = []string{"v13", "v12", "v11", "v10", "v9", "v8"}

// ROUTE_PRESETS of ops/prod/run_dip_prod.sh (--routes vN): the engine gets the expanded string; matched back.
var routePresets = map[string]string{
	"v13": "bam=nozomi+helius-swqos+bolt+falcon+falcon-udp+soyas+solami+0slot;jito=solami+soyas+glaive+falcon+falcon-udp+helius-swqos+0slot;harmonic=nozomi+landx-fra3+falcon+falcon-udp+glaive+soyas+solami+0slot;fd=0slot+nozomi+landx-fra3+staked-rpc+soyas+solami;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
	"v12": "bam=nozomi+helius-swqos+bolt+falcon+falcon-udp+soyas+solami;jito=solami+soyas+glaive+falcon+falcon-udp+helius-swqos;harmonic=nozomi+landx-fra3+falcon+falcon-udp+glaive+soyas+solami;fd=nozomi+landx-fra3+staked-rpc+soyas+solami;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
	"v11": "bam=nozomi+helius-swqos+bolt+falcon+falcon-udp;jito=falcon+falcon-udp+helius-swqos+helius;harmonic=nozomi+falcon+falcon-udp+landx-fra3;fd=nozomi+landx-fra3+staked-rpc;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
	"v10": "bam=nozomi+helius-swqos+bolt+falcon;jito=falcon+helius-swqos+helius;harmonic=nozomi+falcon+landx-fra3;fd=nozomi+landx-fra3+staked-rpc;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
	"v9":  "bam=nozomi+helius-swqos+bolt;jito=helius+helius-swqos+staked-rpc;harmonic=nozomi+landx-fra3;fd=nozomi+landx-fra3+staked-rpc;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
	"v8":  "bam=nozomi+helius-swqos+bolt+staked-rpc;jito=helius+nozomi+jito-bundle+staked-rpc;harmonic=nozomi+helius-swqos+landx-fra3+staked-rpc;fd=nozomi+landx-fra3+staked-rpc;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
}

func init() {
	for k, s := range routePresets {
		presetMaps[k] = RouteMap(s)
	}
}

// RouteMap parses "kind=a+b;kind2=c" into {kind: [paths]}.
func RouteMap(spec string) map[string][]string {
	out := map[string][]string{}
	for _, part := range strings.Split(spec, ";") {
		k, v, ok := strings.Cut(part, "=")
		if !ok {
			continue
		}
		var ps []string
		for _, x := range strings.Split(strings.ReplaceAll(v, " ", ""), "+") {
			if x = PyStrip(x); x != "" {
				ps = append(ps, x)
			}
		}
		out[PyStrip(k)] = ps
	}
	return out
}

func eqStrs(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

// RoutePreset: a {kind: paths} map -> its preset name (v8..v13) or "custom" ("" for none).
func RoutePreset(routes map[string][]string) string {
	if len(routes) == 0 {
		return ""
	}
	// Python iterates its dict in insertion order: v13 first
	for _, name := range presetOrder {
		m := presetMaps[name]
		all := true
		for k, v := range routes {
			mv, ok := m[k]
			if !ok || !eqStrs(mv, v) {
				all = false
				break
			}
		}
		if all && len(routes) >= 5 {
			return name
		}
	}
	return "custom"
}

var rxDipN = regexp.MustCompile(`^dip(\d+)`)

func configItems(v *View, S *Sess, eng *Engine) []CfgItem {
	var items []CfgItem
	fl := map[string]string{}
	var es EngineInfo
	if eng != nil {
		es = eng.Snapshot()
		if es.PID != 0 {
			fl = es.Flags
		}
	}
	SL := map[string]string{"ps": "Pre-send", "qstop": "QUIET stop", "qskip": "QUIET skip", "quiet": "QUIET", "paper": "Paper",
		"m2": "M2 gate", "dev": "Dev list", "reg": "Regular", "guard": "Guard", "routes": "Routes", "sellfan": "Sell fan",
		"nonce": "Nonce", "near": "Near gate", "skipcl": "Skip cl.", "kill": "Kill sw.", "planned": "Planned", "build": "Engine"}
	add := func(key, label, state, short, full string) {
		sl, ok := SL[key]
		if !ok {
			sl = RuneSlice(label, 10)
		}
		if full == "" {
			full = short
		}
		items = append(items, CfgItem{Key: key, Label: label, SLabel: sl, State: state, Short: short, Full: full})
	}
	pc := v.PSCfg
	ps := v.PS
	sep := G.Sep
	pget := func(k string) any { return pc[k] }
	if len(pc) > 0 || ps.Active {
		capV, budget := pget("max_fills"), pget("fee_budget")
		dry := truthyAny(pget("dry"))
		st := "on"
		if dry || v.PSStopped != "" {
			st = "part"
		}
		tag := ""
		if dry {
			tag = " DRY"
		} else if v.PSStopped != "" {
			tag = " (" + v.PSStopped + ")"
		}
		var sf, sfee int64
		if S.PSRec {
			sf, sfee = S.PSFills, S.PSFees()
		} else {
			sf, sfee = int64(len(S.LogPSReal)), S.LogPSFees
		}
		kTxt := "?"
		if x, ok := pc["k"]; ok {
			kTxt = fmtAny(x)
		}
		capTxt := "?"
		if truthyAny(capV) {
			capTxt = fmtAny(capV)
		}
		bud := 0.0
		if bn, ok := budget.(Num); ok && bn.Truthy() {
			bud = bn.Float()
		}
		spendN, _ := pget("spend").(Num)
		short := "PS " + sol2(spendN) + " k" + kTxt + " " + Itoa(sf) + "/" + capTxt + " fee " + F(float64(sfee)/LAM, 2) + "/" + F(bud/LAM, 2) + tag
		full := sol2(spendN) + " SOL " + sep + " " + kTxt + " tries/slot"
		if dn, ok := pget("drop").(Num); ok && dn.Truthy() {
			full += " " + sep + " limit " + G.X + F(1-dn.Float(), 2)
		} else if ln, ok := pget("limit").(Num); ok && ln.Truthy() {
			full += " " + sep + " limit " + G.X + F(ln.Float(), 2)
		}
		if dl := pget("deadline_slots"); truthyAny(dl) {
			full += " " + sep + " deadline +" + fmtAny(dl)
		}
		rt := "?"
		if r := pget("routes"); truthyAny(r) {
			rt = fmtAny(r)
		}
		full += " " + sep + " route " + rt
		if es := pget("exit_slots"); truthyAny(es) {
			full += " " + sep + " exit " + fmtAny(es) + " slots"
		}
		if tp, ok := pget("tp").(Num); ok && tp.Truthy() {
			x := tp.Float()
			if x < 1 {
				x *= 100
			}
			full += " / TP +" + F(x, 0) + "%"
		}
		if sl, ok := pget("sl").(Num); ok && sl.Truthy() {
			x := sl.Float()
			if x < 1 {
				x *= 100
			}
			full += " / SL " + F(x, 0) + "%"
		}
		full += tag
		add("ps", "Pre-send live", st, short, full)
	} else {
		add("ps", "Pre-send live", "off", "PS off", "off")
	}
	// QUIET
	q := v.Quiet
	if q.Present {
		stopOn := q.HasStop && q.Stop != "" && q.Stop != "off"
		stopTxt := "off"
		if q.HasStop && q.Stop != "" {
			stopTxt = q.Stop
		}
		full := "off"
		if q.HasStop && q.Stop != "" && strings.Contains(q.Stop, ":") {
			p := strings.Split(q.Stop, ":")
			full = "at trigger + " + p[0] + " slots with < " + p[1] + " other trades: no more attempts"
		}
		st := "off"
		if stopOn {
			st = "on"
		}
		add("qstop", "QUIET stop rule", st, "stop "+stopTxt, full)
		pre := ""
		if q.Preload != "" {
			pre = " " + sep + " preload " + q.Preload
			if q.PreloadH.Truthy() && q.Preload == "done" {
				pre += " " + F(q.PreloadH.Float(), 1) + " h"
			}
		}
		switch q.State {
		case "on":
			add("qskip", "QUIET skip rule", "on", "skip on", "on (all 4 quiet signals skip a trigger)"+pre)
		case "warm-up":
			when := "?"
			if q.HasOnAt && q.OnAt != 0 {
				when = Clock(float64(q.OnAt), "%H:%M")
			}
			cd := ""
			if q.HasOnAt && q.OnAt != 0 {
				left := float64(q.OnAt)/1e9 - v.Now
				if left > 0 {
					cd = " (in " + HMS(left, true, false) + ")"
				}
			}
			add("qskip", "QUIET skip rule", "part", "skip on "+when, "warming up: on at "+when+" PKT"+cd+pre)
		default:
			add("qskip", "QUIET skip rule", "off", "skip off", "off"+pre)
		}
	} else {
		why := "off"
		if m := rxDipN.FindStringSubmatch(v.Build); m != nil {
			if n, err := strconv.Atoi(m[1]); err == nil && n < 20 {
				why = "not in this engine"
			}
		}
		add("quiet", "QUIET", "off", "QUIET off", why)
	}
	// shadow, M2, dev list
	sh := S.Cfg.Shadow || S.RS.Presend
	if sh {
		add("paper", "Paper (shadow)", "on", "paper", "on (rows a/b/c = +0/+5/+10 ms)")
	} else {
		add("paper", "Paper (shadow)", "off", "paper", "off")
	}
	m2 := ""
	if S.RS.M2 != nil && S.RS.M2.HasMode && S.RS.M2.Mode != "" {
		m2 = S.RS.M2.Mode
	} else if S.Cfg.M2 != "" {
		m2 = S.Cfg.M2
	} else if fl["--dip-m2"] != "" {
		m2 = fl["--dip-m2-mode"]
	}
	if m2 != "" {
		st := "part"
		if m2 == "gate" {
			st = "on"
		}
		full := m2
		if S.RS.M2 != nil {
			if S.RS.M2.HasModel && S.RS.M2.Model != "" {
				full += " " + sep + " model " + S.RS.M2.Model
			}
			if S.RS.M2.Min.Truthy() {
				full += " " + sep + " score " + G.Ge + " " + F(S.RS.M2.Min.Float(), 4)
			}
		}
		add("m2", "M2 gate", st, "M2 "+m2, full)
	} else {
		add("m2", "M2 gate", "off", "M2 off", "off (IMIT1 gate)")
	}
	devn := S.RS.Devs
	dev := S.Cfg.Dev
	if devn != 0 || dev != nil || S.Cfg.DevTrue {
		size := S.RS.DevSpend
		if !size.Ok() && dev != nil {
			size = IntNum(int64(dev.Size * LAM))
		}
		n := "?"
		if devn != 0 {
			n = strconv.Itoa(devn)
		} else if dev != nil {
			n = Itoa(dev.N)
		}
		full := n + " dev wallet(s) " + sep + " " + sol2(size) + " SOL"
		if S.RS.HasDevTier && S.RS.DevTier != "" {
			full += " " + sep + " tier " + S.RS.DevTier
		}
		add("dev", "Dev list", "on", "dev "+sol2(size), full)
	} else {
		add("dev", "Dev list", "off", "dev off", "off")
	}
	// regular buy + exit
	spend := S.RS.Spend // `rs.spend or live.spend`
	if !spend.Truthy() {
		spend = Num{}
		if S.Live.HasSpend {
			spend = IntNum(S.Live.Spend)
		}
	}
	var tpS string
	if S.RS.TP.Ok() {
		if S.RS.TP.Float() >= 99 {
			tpS = "off"
		} else {
			tpS = "+" + F(S.RS.TP.Float()*100, 0) + "%"
		}
	} else if S.Live.HasTP && S.Live.TP != "" {
		tpS = S.Live.TP
	} else {
		tpS = "?"
	}
	var slS string
	if S.RS.SL.Ok() {
		slS = F(S.RS.SL.Float()*100, 0) + "%"
	} else if S.Live.HasSL {
		slS = F(S.Live.SL, 0) + "%"
	} else {
		slS = "?"
	}
	hold := S.RS.HoldSlots
	if !hold.Truthy() && S.Live.HasHold {
		hold = IntNum(S.Live.Hold)
	}
	holdTxt := "?"
	if hold.Truthy() {
		holdTxt = hold.Repr()
	}
	model := "?"
	if S.RS.HasModel && S.RS.Model != "" {
		model = S.RS.Model
	} else if S.Live.HasModel && S.Live.Model != "" {
		model = S.Live.Model
	}
	tier := ""
	if S.RS.HasTier && S.RS.Tier != "" {
		tier = S.RS.Tier
	} else if S.Live.HasModel && S.Live.Tier != "" {
		tier = S.Live.Tier
	}
	add("reg", "Regular buy", "na", sol2(spend)+" TP "+tpS+" SL "+slS+" "+holdTxt+"sl",
		sol2(spend)+" SOL "+sep+" model "+model+" "+tier+" "+sep+" exit TP "+tpS+" / SL "+slS+" / "+holdTxt+" slots (~"+F(hold.Float()*0.212, 1)+" s)")
	guard := S.RS.Guard
	if !guard.Truthy() && S.Live.HasGuard {
		guard = FloatNum(S.Live.Guard)
	}
	if guard.Truthy() {
		add("guard", "Price guard", "na", G.X+F(guard.Float(), 2), G.X+F(guard.Float(), 2)+" over the post-dump price (pump error 6042 above it)")
	} else {
		add("guard", "Price guard", "na", "guard ?", "?")
	}
	routes := S.Cfg.Routes
	if len(routes) == 0 && fl["--route-by-client"] != "" {
		routes = RouteMap(fl["--route-by-client"])
	}
	preName := RoutePreset(routes)
	rshort := preName
	if rshort == "" {
		rshort = "routes ?"
	}
	rfull := preName
	if rfull == "" {
		rfull = "?"
	}
	if len(routes) > 0 {
		ks := make([]string, 0, len(routes))
		for k := range routes {
			ks = append(ks, k)
		}
		sort.Strings(ks)
		parts := make([]string, len(ks))
		for i, k := range ks {
			parts[i] = k + ": " + strings.Join(routes[k], "+")
		}
		rfull += " " + strings.Join(parts, "; ")
	}
	add("routes", "Routes", "na", rshort, rfull)
	sfStr, sfOn := "", false
	if S.Cfg.SellFan != "" {
		sfStr, sfOn = S.Cfg.SellFan, true
	} else if S.Cfg.SellFanTrue {
		sfOn = true
	} else if f := fl["--sell-fanout"]; f != "" {
		sfStr, sfOn = f, true
	}
	if sfOn {
		x := "on"
		if sfStr != "" {
			x = sfStr
		}
		add("sellfan", "Sell fan-out", "on", "sell-fan", "staked-rpc + "+x)
	} else {
		add("sellfan", "Sell fan-out", "off", "sell-fan off", "off")
	}
	nonceTxt, nonceOn := "", false
	switch {
	case S.Cfg.NonceSet:
		if S.Cfg.NonceTrue {
			nonceTxt, nonceOn = "True", true
		} else {
			nonceTxt, nonceOn = Itoa(S.Cfg.Nonce), S.Cfg.Nonce != 0
		}
	case S.RS.present && S.RS.Nonce != 0:
		nonceTxt, nonceOn = strconv.Itoa(S.RS.Nonce), true
	case fl["--nonce-fanout"] != "":
		nonceTxt, nonceOn = "8", true
	}
	if nonceOn {
		add("nonce", "Nonce fan-out", "on", "nonce "+nonceTxt, nonceTxt+" durable-nonce accounts (one tip per landed buy)")
	} else {
		add("nonce", "Nonce fan-out", "off", "nonce off", "off")
	}
	nearTxt, nearOn := "", false
	switch {
	case S.Cfg.NearSet && S.Cfg.NearTrue:
		nearTxt, nearOn = "True", true
	case S.Cfg.NearSet && S.Cfg.Near != 0:
		nearTxt, nearOn = Itoa(S.Cfg.Near), true
	case fl["--dip-near-leaders"] != "":
		nearTxt, nearOn = "True", true
	}
	if nearOn {
		add("near", "Near-leader gate", "on", "near "+nearTxt, nearTxt+" leaders")
	} else {
		add("near", "Near-leader gate", "off", "near off", "off (every leader)")
	}
	var skc string
	hasSkc := false
	if S.RS.HasSkipClients && Truthy(S.RS.SkipClients) {
		if l, ok := S.RS.SkipClients.([]any); ok {
			parts := make([]string, len(l))
			for i, x := range l {
				parts[i] = PyStr(x)
			}
			skc, hasSkc = strings.Join(parts, ","), true
			add("skipcl", "Skip clients", "na", "skip "+skc, strings.Join(parts, ", "))
		} else {
			skc, hasSkc = PyStr(S.RS.SkipClients), true
			add("skipcl", "Skip clients", "na", "skip "+skc, skc)
		}
	} else if S.Cfg.HasSkipClients && S.Cfg.SkipClients != "" {
		skc, hasSkc = S.Cfg.SkipClients, true
		add("skipcl", "Skip clients", "na", "skip "+skc, skc)
	}
	_ = hasSkc
	if v.HasKillLevel {
		full := "below " + F(float64(v.KillLevel)/LAM, 4) + " SOL"
		if v.LossCapN.Truthy() {
			full += " (loss cap " + F(v.LossCapN.Float()/LAM, 3) + ")"
		}
		add("kill", "Kill switch", "na", "kill "+F(float64(v.KillLevel)/LAM, 3), full)
	}
	if v.Planned.Truthy() {
		full := v.Planned.Repr() + " min"
		if v.HasEndsAt {
			full += " (ends " + Clock(v.EndsAt, "%H:%M") + " PKT)"
		}
		add("planned", "Planned", "na", v.Planned.Repr()+"m", full)
	}
	b := v.Build
	if b == "" {
		b = "?"
	}
	full := b
	if !v.BuildLive {
		full += " (inferred from the records)"
	}
	if es.PID != 0 {
		full += " " + sep + " pid " + strconv.Itoa(es.PID)
	}
	add("build", "Engine", "na", b, full)
	return items
}

// ------------------------------------------------------------------------------------------------- alerts

func makeAlerts(v *View, ctx *Ctx, M *Model) []Alert {
	var A []Alert
	S := v.Cur
	if v.Status == "ENGINE GONE" {
		A = append(A, Alert{"bad", "engine gone without DIP DONE"})
	}
	if len(M.Panics) > 0 {
		A = append(A, Alert{"bad", "engine panic: " + RuneSlice(M.Panics[len(M.Panics)-1], 60)})
	}
	if len(M.Refused) > 0 && !M.SegLive {
		r := M.Refused[len(M.Refused)-1]
		rs := []rune(r)
		seg := ""
		if len(rs) > 7 {
			seg = string(rs[7:min(len(rs), 70)])
		}
		A = append(A, Alert{"bad", "start refused: " + seg})
	}
	if S.killTruthy() {
		if S.KillIsFloat {
			A = append(A, Alert{"bad", "KILL SWITCH fired (run P&L " + FS(S.Kill, 4) + ")"})
		} else {
			A = append(A, Alert{"bad", "KILL SWITCH fired"})
		}
	} else if v.Running && v.HasKillDist && float64(v.KillDist) < 0.15*LAM {
		A = append(A, Alert{"bad", "kill switch " + F(float64(v.KillDist)/LAM, 3) + " SOL away"})
	}
	if v.Running && v.HasWrite && v.WriteAge > 30 {
		A = append(A, Alert{"bad", "log stalled " + AgeS(v.WriteAge, true)})
	}
	ps := v.PS
	pc := v.PSCfg
	if v.Running && ps.Active {
		if fb, ok := pc["fee_budget"].(Num); ok && fb.Truthy() && float64(ps.Fees) > 0.8*fb.Float() {
			A = append(A, Alert{"warn", "pre-send fees " + F(float64(ps.Fees)/fb.Float()*100, 0) + "% of budget"})
		}
		if mf, ok := pc["max_fills"].(Num); ok && mf.Truthy() && float64(ps.Fills) > 0.9*mf.Float() {
			A = append(A, Alert{"warn", "pre-send fills " + Itoa(ps.Fills) + "/" + mf.Repr()})
		}
	}
	if v.PSStopped != "" && !S.Ended() {
		A = append(A, Alert{"warn", "pre-send stopped (" + v.PSStopped + ")"})
	}
	if v.Status == "STOPPING" && S.signalTruthy() {
		A = append(A, Alert{"warn", "stopping (" + S.Signal + "): open positions finish"})
	}
	lo := M.LogMin - 9
	paths := make([]string, 0, len(M.PathErr))
	for p := range M.PathErr {
		paths = append(paths, p)
	}
	sort.Strings(paths)
	for _, path := range paths {
		n := int64(0)
		for k, x := range M.PathErr[path] {
			if k >= lo {
				n += x
			}
		}
		if n >= 3 {
			kind, ok := M.PathKind[path]
			if !ok {
				kind = "error"
			}
			A = append(A, Alert{"warn", path + " " + kind + " " + Itoa(n) + "/10m"})
		}
	}
	pe := M.PollErr[M.LogMin] + M.PollErr[M.LogMin-1]
	if v.Running && pe >= 20 {
		A = append(A, Alert{"warn", "POLL-RPC-ERROR " + Itoa(pe) + "/2m"})
	}
	if v.Running && M.HasRuntime && M.Runtime[1] > 10 {
		A = append(A, Alert{"warn", "runtime lag p99 " + F(M.Runtime[1], 1) + " ms"})
	}
	if ec := S.EndCheck; ec != nil && (ec[1] != 0 || ec[2] != 0 || ec[3] != 0 || ec[4] != 0) {
		A = append(A, Alert{"warn", "END CHECK found work: " + Itoa(ec[1]) + " sold, " + Itoa(ec[2]) + " closed, " + Itoa(ec[3]) + " held, " + Itoa(ec[4]) + " unreadable"})
	}
	if ps.NotSold != 0 || ps.ATAFail != 0 {
		A = append(A, Alert{"warn", "pre-send: " + Itoa(ps.NotSold) + " unsold, " + Itoa(ps.ATAFail) + " account closes failed"})
	}
	if v.Reg.Est != 0 && !v.Running {
		A = append(A, Alert{"warn", Itoa(v.Reg.Est) + " regular fill(s) without the REALIZED line (feed estimate)"})
	}
	if v.Status == "ENDED" {
		ecs := ""
		if ec := S.EndCheck; ec != nil {
			ecs = "END CHECK " + Itoa(ec[0]) + " read: " + Itoa(ec[1]) + " sold, " + Itoa(ec[2]) + " closed, " + Itoa(ec[3]) + " held"
			if ec[1] == 0 && ec[2] == 0 && ec[3] == 0 && ec[4] == 0 {
				ecs += " " + G.Ok
			}
		} else if S.PSActive() {
			ecs = "no END CHECK line"
		}
		how := v.HowEnded
		if how == "" {
			how = "?"
		}
		t := "RUN ENDED " + Clock(float64(v.TEnd), "%H:%M") + " (" + how + ") " + SolS(v.Total) + " SOL"
		if ecs != "" {
			t += " " + G.Sep + " " + ecs
		}
		A = append(A, Alert{"end", t})
	}
	if v.Status == "NO END RECORD" {
		A = append(A, Alert{"warn", "no DIP DONE / run_end in the files (incomplete copy?)"})
	}
	order := map[string]int{"bad": 0, "warn": 1, "end": 2, "info": 3}
	sort.SliceStable(A, func(i, j int) bool { return order[A[i].Level] < order[A[j].Level] })
	return A
}

// ------------------------------------------------------------------------------------------------- trades

// SortedTrades: newest first, filtered (all | pre-send | regular | wins | losses | open).
func SortedTrades(trades []*Trade, flt string) []*Trade {
	out := make([]*Trade, 0, len(trades))
	for _, t := range trades {
		switch flt {
		case "pre-send":
			if t.Kind != "PS" {
				continue
			}
		case "regular":
			if t.Kind != "REG" {
				continue
			}
		case "wins":
			if !(t.HasPnl && t.Pnl > 0) {
				continue
			}
		case "losses":
			if !(t.HasPnl && t.Pnl < 0) {
				continue
			}
		case "open":
			if !(t.Res == "open" || (t.Kind == "PS" && t.PClose == nil && !t.HasPnl) || (t.Kind == "REG" && t.Res == "filled" && t.Close == nil)) {
				continue
			}
		}
		out = append(out, t)
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].T > out[j].T })
	return out
}

// TradeExit: TP / SL / time, 6042 / 6001 / fail for failed buys, open / hold.
func TradeExit(tr *Trade) string {
	if tr.Kind == "PS" {
		if tr.PClose == nil && !tr.HasPnl {
			return "open"
		}
		e := tr.PExit
		if !tr.HasPExit {
			e = ""
		}
		fb := "?"
		if e != "" {
			fb = RuneSlice(e, 5)
		}
		return ExitShort(e, fb)
	}
	switch tr.Res {
	case "filled":
		if tr.Close == nil {
			return "hold"
		}
		w := ""
		if tr.Close.HasWhy {
			w = tr.Close.Why
		}
		fb := "?"
		if w != "" {
			fb = RuneSlice(w, 5)
		}
		return ExitShort(w, fb)
	case "guard":
		return "6042"
	case "lighthouse":
		return "6001"
	case "failed":
		return "fail"
	case "open":
		return "open"
	case "not landed":
		return "drop"
	}
	return RuneSlice(tr.Res, 5)
}

// TradeHeld: "2sl" / "1.3s" / "".
func TradeHeld(tr *Trade) string {
	if tr.Kind == "PS" {
		if tr.Slots.Ok() {
			return tr.Slots.Repr() + "sl"
		}
		if tr.HeldS.Truthy() {
			return F(tr.HeldS.Float(), 1) + "s"
		}
		return ""
	}
	if tr.Exit != nil && tr.Exit.Slots.Ok() {
		return tr.Exit.Slots.Repr() + "sl"
	}
	if tr.Close != nil && tr.Close.ExitSlot.Truthy() && tr.Close.LandSlot.Truthy() {
		if tr.Close.ExitSlot.K == NumFloat || tr.Close.LandSlot.K == NumFloat {
			return PyRepr(tr.Close.ExitSlot.Float()-tr.Close.LandSlot.Float()) + "sl"
		}
		return Itoa(tr.Close.ExitSlot.I-tr.Close.LandSlot.I) + "sl"
	}
	return ""
}

// TradePath: the send path that landed it.
func TradePath(tr *Trade) string {
	if tr.Kind == "PS" {
		return tr.Path
	}
	if tr.Land != nil {
		return tr.Land.Via
	}
	if tr.Failed != nil {
		return tr.Failed.Via
	}
	return ""
}

// ExeName is the engine binary name from a command line (tests / screens).
func ExeName() string { return filepath0(os.Args[0]) }

func filepath0(p string) string {
	if i := strings.LastIndexByte(p, '/'); i >= 0 {
		return p[i+1:]
	}
	return p
}
