package core

import (
	"bytes"
	"strconv"
	"strings"
	"time"
)

const (
	LAM          = 1_000_000_000
	FailedBuyFee = 505_000 // 5,000 base + 100,000 CU x 5,000,000 uL/CU (run script: --cu-limit 100000 --cu-price-micro 5000000)
	PSFailFee    = 5_120   // 5,000 base + 120,000 CU x 1,000 uL/CU
	minuteNS     = 60_000_000_000
)

// KIND maps a leader client to its family.
var KIND = map[string]string{"JitoLabs": "Jito", "AgaveBam": "BAM", "FireBAM": "BAM", "HarmonicAgave": "Harmonic",
	"HarmonicFiredancer": "Harmonic", "Firedancer": "Firedancer", "Frankendancer": "Firedancer", "Agave": "Agave",
	"Rakurai": "Rakurai", "Raiku": "Raiku"}

// KindOf is the client family ("?" for none).
func KindOf(client string) string {
	if k, ok := KIND[client]; ok {
		return k
	}
	if client == "" {
		return "?"
	}
	return client
}

// EXIT_SHORT: exit reasons in short form.
var exitShort = map[string]string{"take-profit": "TP", "stop-loss": "SL", "time-limit": "time", "time": "time"}

// ExitShort is EXIT_SHORT.get(why, fallback).
func ExitShort(why string, fallback string) string {
	if s, ok := exitShort[why]; ok {
		return s
	}
	return fallback
}

// WKey is a pre-send window id (None when !Ok).
type WKey struct {
	W  int64
	Ok bool
}

type psKey struct {
	W    WKey
	Mint string
}

// Land / Failed / RegExit / SellRec / RegClose / PSClose / Timing: the regular bot's records of one buy.
type Land struct {
	T, Slot, Ms, Blk, Fee, Sol Num
	Sig                        string
	HasSig                     bool
	Via                        string
}

type Failed struct {
	T, Slot Num
	Sig     string
	HasSig  bool
	Via     string
}

type RegExit struct {
	Why    string
	HasWhy bool
	Slots  Num
	T      Num
}

type SellRec struct {
	Sig    string
	HasSig bool
	T      Num
	Sol    Num
	Fee    Num
}

type RegClose struct {
	Result    string
	HasResult bool
	Why       string
	HasWhy    bool
	HeldS     Num
	Err       string
	SellSigs  []string
	T         int64
	SolOut    Num
	ExitSlot  Num
	LandSlot  Num
	Curve     Num
	Spend     Num
	Score     Num
}

type PSClose struct {
	T      int64
	Curve  Num
	Merged Num
	Late   Num
}

type Timing struct {
	Reaction, ExecLag, FireToSeen Num
	DumpToSeen                    Num // buy_first_rx - dump_first_rx (ms): our buy seen after the dump (display only)
	Blk                           Num // clock2 buy_slot - dump_slot (display only)
}

// Trade is one regular buy (Kind "REG") or one pre-send fill / position (Kind "PS").
type Trade struct {
	ID    int
	Kind  string
	S     int
	T     int64
	Mint  string
	Spend Num

	// regular
	Dev        bool
	Client     string
	Leader     string
	Route      string
	BuySig     string
	HasBuySig  bool
	DumpSig    string
	HasDumpSig bool
	DecUs      Num
	TDump      Num
	Slot       Num
	Paths      []string
	Land       *Land
	Failed     *Failed
	PollErr    string
	HasPollErr bool
	Timing     *Timing
	Exit       *RegExit
	Sells      []SellRec
	Close      *RegClose

	// both
	Pnl    int64
	HasPnl bool
	Src    string // "" = None
	Res    string
	Booked int64
	Bm     int64
	HasBm  bool

	// pre-send
	W        WKey
	SolIn    Num
	Path     string
	Ms       Num
	After    Num
	NFills   int
	BuySigs  []string
	SellSigs []string
	PExit    string
	HasPExit bool
	Slots    Num
	HeldS    Num
	Value    Num
	PClose   *PSClose
	Rent     int64
	HasRent  bool
	TrigPct  Num
	TrigSol  Num
	Fee      Num
	Tip      Num
	Late     bool
	Lat      *PSLat // the filling try's latency (v3, display only)
}

// Closed: a PS trade with a close record or a P&L (the Python `close is not None or pnl is not None`).
func (t *Trade) PSOpen() bool { return t.PClose == nil && !t.HasPnl }

// RunStart is the subset of the run_start record dipmon uses.
type RunStart struct {
	Minutes, LossCap, Spend, DevSpend              Num
	DevTier, Tier, Model, Wallet                   string
	HasDevTier, HasTier, HasModel, HasWallet       bool
	TP, SL, HoldSlots, Guard, MaxBuys, MaxInflight Num
	Thr                                            Num
	SkipClients                                    any
	HasSkipClients                                 bool
	Devs, Nonce                                    int
	M2                                             *M2Cfg
	Presend                                        bool
	PSL                                            map[string]any // presend_live subset (every key present, None when missing)
	Quiet                                          *QuietStart
	present                                        bool
}

type M2Cfg struct {
	Mode, Model       string
	HasMode, HasModel bool
	Min               Num
}

type QuietStart struct {
	Stop       string
	HasStop    bool
	Skip       any
	WarmupMin  Num
	Preload    bool
	HistH, Fol Num
}

// LiveCfg: the "DIP LIVE | ..." line.
type LiveCfg struct {
	Model, Tier string
	HasModel    bool
	TP          string
	HasTP       bool
	SL          float64
	HasSL       bool
	Hold        int64
	HasHold     bool
	Guard       float64
	HasGuard    bool
	Spend       int64
	HasSpend    bool
	MaxBuys     int64
	HasMaxBuys  bool
	LossCap     int64
	HasLossCap  bool
	Minutes     int64
	HasMinutes  bool
}

// QuietLog: "DIP PRESEND LIVE QUIET:" (+ preload / status updates).
type QuietLog struct {
	Line      bool
	Stop      string
	HasStop   bool
	Skip      int8 // -1 None, 0 false, 1 true
	OnHHMM    [2]int
	HasOnHHMM bool
	WarmupMin float64
	HasWarmup bool
	Preload   string
	PreloadH  Num
	RuleState string
}

// LogCfg: other start lines (routes, nonce, sell fan-out, near gate, M2, shadow, dev list, skip clients).
type LogCfg struct {
	Shadow         bool
	M2             string
	Dev            *DevList // nil = absent
	DevTrue        bool     // "dev": True (the line without numbers)
	Near           int64
	NearSet        bool
	NearTrue       bool
	SkipClients    string
	HasSkipClients bool
	Nonce          int64
	NonceSet       bool
	NonceTrue      bool
	Routes         map[string][]string
	SellFan        string
	SellFanTrue    bool
}

type DevList struct {
	N    int64
	Size float64
}

// Done: "=== DIP DONE".
type Done struct {
	Fired, Closed, Landed int64
	Realized              int64
	Parsed                bool
}

// RunEnd: the run_end record subset.
type RunEnd struct {
	T                                   Num
	Fired, Closed, LandedBuys, Realized Num
	Dumps, Picks                        Num
	Skipped                             any
	Quiet                               *Obj
}

// StopRec: presend_live_stop.
type StopRec struct {
	Why    string
	HasWhy bool
	T      Num
	Fees   Num
	Fills  Num
}

// Preload: presend_live_quiet_preload.
type Preload struct {
	Ok       any
	Secs     Num
	CoveredH Num
	OnAt     Num
	T        Num
}

// Status: the latest "DIP status" line's pieces.
type Status struct {
	HasReg                 bool
	Fired, Closed, Open    int64
	Skipped                *OCounter
	HasPS                  bool
	PSDry                  bool
	PSStopped              string
	PSTriggers, PSArmed    int64
	PSNow                  int64
	HasFills               bool
	PSFills, PSCap         int64
	HasFee                 bool
	PSFee, PSBudget        float64
	HasQ                   bool
	QSkips, QWould, QStops int64
	QRule                  string
	Min                    int
}

// Sess is one engine session (one run_start; a restart into the same log is the next session).
type Sess struct {
	Idx   int
	HasRS bool
	RS    RunStart
	T0    int64 // run_start t (0 = None)
	RE    *RunEnd
	CurT  int64

	Live           LiveCfg
	HasLive        bool
	StartBal       int64
	HasStartBal    bool
	KillLevel      int64
	HasKillLevel   bool
	PSL            map[string]any
	Quiet          QuietLog
	Cfg            LogCfg
	Done           *Done
	Signal         string
	HasSignal      bool
	Kill           float64
	KillSet        bool
	KillIsFloat    bool
	PSStopped      *PSStoppedLine
	EndCheck       *[5]int64
	Status         Status
	EngineRealized int64
	HasEngineReal  bool
	Paper          *Paper
	LogPSFees      int64
	LogPSReal      []int64
	Errors         []string

	Reg    []*Trade
	ByMint map[string][]*Trade
	RealQ  map[string][]int64
	Dumps  int64
	Picks  int64

	PSRec      bool
	PSFills    int64
	PSWins     int64
	PSNReal    int64
	PSRealized int64
	PSRent     int64
	PSFeeCnt   int64
	PSFeeN     int64
	PSFeeEach  *OCounter
	PSSent     int64
	PSDry      int64
	PSRes      *OCounter
	PSArmed    int64
	PSOpenSet  map[WKey]bool
	PSSkips    *OCounter
	PSDisarms  *OCounter
	PSPos      map[psKey]*Trade
	PSByKey    map[psKey][]*Trade
	PSList     []*Trade
	PSStop     []StopRec
	PSEndChk   *OCounter
	PSHeld     int64
	PSATAFail  int64
	PSLandMs   []float64
	PSAfter    []Num
	QSkips     int64
	QStops     int64
	QWould     int64
	QRuleOn    int8 // -1 None
	QPreload   *Preload
	Buckets    map[int64]int64 // unix minute -> P&L change (lamports)

	// v3 (not in the Python v1): the trading-card figures and their minutes (the Today scope)
	FeeBuckets map[int64]int64 // unix minute -> failed pre-send tries' fees
	RentFree   map[int64]int64 // unix minute -> rent back not matched to a fill
	Tx         TxTally         // landed buys / sells (counts + SOL), all and per minute
	RealRecs   []MinAmt        // every presend_live_realized P&L with its booking minute
	RentRecs   []MinAmt        // every ok presend_live_ata_close delta with its booking minute

	// v3 latency (display only)
	Lat      LatAgg             // the pre-send tries' latency
	LatKind  map[string]*LatAgg // by the leader's client family
	WinTries map[int64]int64    // sent tries per window
}

// MinAmt is an amount booked in a unix minute.
type MinAmt struct{ Amt, Min int64 }

// PSStoppedLine: "PRESEND LIVE STOPPED (why) ... fills a/b".
type PSStoppedLine struct {
	Why        string
	Fills, Cap int64
	HasFills   bool
}

// Paper: shadow row c (fills, gross SOL, net SOL).
type Paper struct {
	Fills      int64
	Gross, Net float64
}

func newSess(idx int) *Sess {
	return &Sess{Idx: idx, PSL: map[string]any{}, Quiet: QuietLog{Skip: -1}, ByMint: map[string][]*Trade{},
		RealQ: map[string][]int64{}, PSFeeEach: NewOCounter(), PSRes: NewOCounter(), PSOpenSet: map[WKey]bool{},
		PSSkips: NewOCounter(), PSDisarms: NewOCounter(), PSPos: map[psKey]*Trade{}, PSByKey: map[psKey][]*Trade{},
		PSEndChk: NewOCounter(), QRuleOn: -1, Buckets: map[int64]int64{}, FeeBuckets: map[int64]int64{},
		RentFree: map[int64]int64{}, Tx: newTxTally()}
}

// PSFees is the larger of the counted failed-try fees, the log's counter and presend_live_stop.fees.
func (S *Sess) PSFees() int64 {
	stop := int64(0)
	for _, s := range S.PSStop {
		if f := s.Fees.Int(); s.Fees.Truthy() && f > stop {
			stop = f
		}
	}
	return max(S.PSFeeCnt, S.LogPSFees, stop)
}

func (S *Sess) stopFeesMax() int64 {
	stop := int64(0)
	for _, s := range S.PSStop {
		if f := s.Fees.Int(); s.Fees.Truthy() && f > stop {
			stop = f
		}
	}
	return stop
}

// PSActive: any pre-send record or line.
func (S *Sess) PSActive() bool {
	return S.PSRec || len(S.PSL) > 0 || len(S.LogPSReal) > 0 || S.LogPSFees != 0
}

// PSNet: realized + rent back - failed-try fees (old runs: the log's PRESEND LIVE REALIZED lines).
func (S *Sess) PSNet() int64 {
	if S.PSRec {
		return S.PSRealized + S.PSRent - S.PSFees()
	}
	sum := int64(0)
	for _, x := range S.LogPSReal {
		sum += x
	}
	return sum - S.LogPSFees
}

// RegTotal: every regular trade's P&L.
func (S *Sess) RegTotal() int64 {
	sum := int64(0)
	for _, t := range S.Reg {
		if t.HasPnl {
			sum += t.Pnl
		}
	}
	return sum
}

// Total: pre-send net + regular.
func (S *Sess) Total() int64 { return S.PSNet() + S.RegTotal() }

// Ended: DIP DONE or run_end seen.
func (S *Sess) Ended() bool { return S.Done != nil || S.RE != nil }

// TEnd: run_end's t (0 = None).
func (S *Sess) TEnd() int64 {
	if S.RE != nil && S.RE.T.Truthy() {
		return S.RE.T.Int()
	}
	return 0
}

// Minutes: run_start minutes or the DIP LIVE line's.
func (S *Sess) Minutes() Num {
	if S.RS.Minutes.Truthy() {
		return S.RS.Minutes
	}
	if S.Live.HasMinutes {
		return IntNum(S.Live.Minutes)
	}
	return Num{}
}

// LossCap: run_start loss_cap or the DIP LIVE line's.
func (S *Sess) LossCap() Num {
	if S.RS.LossCap.Ok() {
		return S.RS.LossCap
	}
	if S.Live.HasLossCap {
		return IntNum(S.Live.LossCap)
	}
	return Num{}
}

// LogItem is one kept log line: cleaned text, its session, its minute in the session, its arrival time when
// read live (0 in the initial load).
type LogItem struct {
	Text  string
	Sess  int
	SMin  int
	TLive float64
}

// RPCStat: the newest RPC-LAT minute for a (name, method).
type RPCStat struct {
	N            int64
	P50, P99, Mx float64
	Min          int
	TO, TOLast   int64
}

// Event: a trade whose P&L became final (the app's bell / highlight) and when (wall time).
type Event struct {
	Seq   int64
	At    time.Time
	Trade *Trade
	Pnl   int64
}

// Model is the parsed run: every session, the trades, the log's health figures.
type Model struct {
	Sessions      []*Sess
	jsess, lsess  int
	lpend         LogCfg
	lpendRoutes   bool
	Version       int
	CurT          int64
	Bad           int64
	JLines        int64
	LLines        int64
	LogMin        int
	LogKeep       int
	LogRing       *Ring
	LogImp        *Ring
	RPC           map[[2]string]*RPCStat
	RPCOrder      [][2]string
	Runtime       [3]float64
	HasRuntime    bool
	RuntimeWorst  float64
	PollErr       map[int]int64
	PollErrTotal  int64
	PathErr       map[string]map[int]int64
	PathKind      map[string]string
	PathTotal     map[string]int64
	EngineStarts  int
	SegLive       bool
	Refused       []string
	Panics        []string
	FailBuyFee    int64
	FailBuyFeeSrc string
	armInfo       map[[2]int64]armRec
	armOrder      [][2]int64
	Trades        []*Trade
	EvCount       map[string]int
	Events        []Event // bounded: the newest 1000
	EventSeq      int64   // events ever pushed
	TradeVer      int64   // bumped whenever a trade is added or changes (UI caches)
	LiveLog       bool
	LogSMin       int
	recentStart   bool
	segLines      int
	tLive         float64
	nextID        int
	// v3 latency: fills by sig, landings that came before their fill, the recent tries' leaders (bounded)
	psSigTrade map[string]*Trade
	psLandPend map[string]*PSLat
	tryLeader  map[string]string
	tryOrder   []string
}

type armRec struct {
	key     [2]int64
	pct, sl Num
}

// NewModel: failBuyFee > 0 = from the engine's command line.
func NewModel(failBuyFee int64, logKeep int) *Model {
	if logKeep <= 0 {
		logKeep = 3000
	}
	M := &Model{jsess: -1, lsess: -1, LogKeep: logKeep, LogRing: NewRing(logKeep), LogImp: NewRing(max(200, logKeep/2)),
		RPC: map[[2]string]*RPCStat{}, PollErr: map[int]int64{}, PathErr: map[string]map[int]int64{},
		PathKind: map[string]string{}, PathTotal: map[string]int64{}, armInfo: map[[2]int64]armRec{},
		EvCount: map[string]int{}}
	M.lpend = LogCfg{}
	if failBuyFee > 0 {
		M.FailBuyFee, M.FailBuyFeeSrc = failBuyFee, "cmdline"
	} else {
		M.FailBuyFee, M.FailBuyFeeSrc = FailedBuyFee, "default"
	}
	return M
}

// Sess returns session i (created as needed; i < 0 -> 0).
func (M *Model) Sess(i int) *Sess {
	if i < 0 {
		i = 0
	}
	for len(M.Sessions) <= i {
		M.Sessions = append(M.Sessions, newSess(len(M.Sessions)))
	}
	return M.Sessions[i]
}

func (M *Model) jcur() *Sess { return M.Sess(M.jsess) }
func (M *Model) lcur() *Sess { return M.Sess(M.lsess) }

func (M *Model) setTime(S *Sess, t int64) {
	if !TimeOKi(t) {
		return
	}
	if t > S.CurT {
		S.CurT = t
		if t > M.CurT {
			M.CurT = t
		}
	}
}

func (M *Model) pushEvent(tr *Trade) {
	M.EventSeq++
	M.Events = append(M.Events, Event{Seq: M.EventSeq, At: time.Now(), Trade: tr, Pnl: tr.Pnl})
	if len(M.Events) > 1000 {
		M.Events = append([]Event(nil), M.Events[len(M.Events)-1000:]...)
	}
}

// --------------------------------------------------------------------------------------------------------- jsonl

var ignoredEvents = map[string]bool{"tape": true, "presend_live_tape": true, "presend_arm": true, "presend_disarm": true,
	"presend_skip": true, "presend_fill": true, "presend_exit": true, "presend_live_parity": true, "presend_live_ata": true,
	"shred_dump": true, "shred_parity": true, "feed_lag": true, "probe_land": true}

var jsonEvents = map[string]bool{"run_start": true, "run_end": true, "fire": true, "buy_land": true, "buy_failed": true,
	"land_poll": true, "timing": true, "exit": true, "sell_land": true, "close": true, "presend_live_arm": true,
	"presend_live_disarm": true, "presend_live_skip": true, "presend_live_fill": true, "presend_live_exit": true,
	"presend_live_close": true, "presend_live_realized": true, "presend_live_ata_close": true, "presend_live_stop": true,
	"presend_live_end_check": true, "presend_live_held": true, "presend_live_quiet_preload": true,
	"presend_live_quiet_state": true}

var evKey = []byte(`"ev":"`)

// FeedJSONL parses record lines (the cheap ones by substring, the rest as JSON).
func (M *Model) FeedJSONL(lines [][]byte) {
	for _, line := range lines {
		M.JLines++
		i := bytes.Index(line, evKey)
		if i < 0 {
			if len(bytes.TrimSpace(line)) > 0 {
				M.Bad++
			}
			continue
		}
		rest := line[i+6:]
		j := bytes.IndexByte(rest, '"')
		var ev []byte
		if j < 0 {
			if len(line) > i+6 {
				ev = line[i+6 : len(line)-1] // Python line[i+6:-1]
			}
		} else {
			ev = rest[:j]
		}
		M.feedOne(line, ev)
	}
	M.Version++
}

func (M *Model) feedOne(line, ev []byte) {
	defer func() {
		if r := recover(); r != nil {
			M.Bad++
		}
	}()
	switch string(ev) {
	case "presend_live_sell_land": // v3 only: a landed pre-send sell (ignored by the Python v1)
		M.jPSSellLand(line)
		return
	}
	if ignoredEvents[string(ev)] {
		return
	}
	switch string(ev) {
	case "dump":
		S := M.jcur()
		S.Dumps++
		M.setTime(S, tOf(line))
		return
	case "presend_attempt":
		S := M.jcur()
		S.PSRec = true
		dry := bytes.Contains(line, []byte(`"dry":true`))
		if dry {
			S.PSDry++
		} else {
			S.PSSent++
		}
		M.latAttempt(S, line, dry)
		return
	case "presend_attempt_land":
		M.jAttemptLand(line)
		return
	case "pick":
		M.jcur().Picks++
		return
	case "pick_skip":
		return
	}
	if jsonEvents[string(ev)] {
		o, isObj, ok := DecodeObj(line)
		if !ok {
			M.Bad++
			return
		}
		if !isObj {
			M.Bad++
			return
		}
		M.jJSON(o)
		return
	}
	M.EvCount[string(ev)]++
	if len(M.EvCount) > 200 {
		M.EvCount = map[string]int{}
	}
}

// numAfter is the integer right after key (the first occurrence; an optional '-').
func numAfter(line []byte, key string) (int64, bool) {
	i := bytes.Index(line, []byte(key))
	if i < 0 {
		return 0, false
	}
	i += len(key)
	j := i
	if j < len(line) && line[j] == '-' {
		j++
	}
	for j < len(line) && line[j] >= '0' && line[j] <= '9' {
		j++
	}
	v, err := strconv.ParseInt(string(line[i:j]), 10, 64)
	if err != nil {
		return 0, false
	}
	return v, true
}

// tOf is the record's top-level time: its last "t": (sorted keys put nested trades' "t" first), else "t_send":.
func tOf(line []byte) int64 {
	i := bytes.LastIndex(line, []byte(`"t":`))
	k := 4
	if i < 0 {
		i = bytes.LastIndex(line, []byte(`"t_send":`))
		k = 9
		if i < 0 {
			return 0
		}
	}
	i += k
	j := i
	for j < len(line) && line[j] >= '0' && line[j] <= '9' {
		j++
	}
	v, err := strconv.ParseInt(string(line[i:j]), 10, 64)
	if err != nil {
		return 0
	}
	return v
}

func (M *Model) jAttemptLand(line []byte) {
	S := M.jcur()
	S.PSRec = true
	res := "?"
	if i := bytes.Index(line, []byte(`"res":"`)); i >= 0 {
		rest := line[i+7:]
		if j := bytes.IndexByte(rest, '"'); j >= 0 {
			res = string(rest[:j])
		} else if len(line) > i+7 {
			res = string(line[i+7 : len(line)-1])
		} else {
			res = ""
		}
		res = strings.ToValidUTF8(res, "�")
	}
	S.PSRes.Add(res, 1)
	M.latLand(S, line, res)
	t := tOf(line)
	M.setTime(S, t)
	if res != "ok" {
		fee, ok := numAfter(line, `"fee":`)
		if ok && fee != 0 {
			S.PSFeeCnt += fee
			S.PSFeeN++
			S.PSFeeEach.Add(strconv.FormatInt(fee, 10), 1)
			base := t
			if !TimeOKi(t) {
				base = S.CurT
				if base == 0 {
					base = M.CurT
				}
			}
			mm := floorDiv(base, minuteNS)
			S.Buckets[mm] -= fee
			S.FeeBuckets[mm] += fee
		}
	}
}

func floorDiv(a, b int64) int64 {
	q := a / b
	if (a%b != 0) && ((a < 0) != (b < 0)) {
		q--
	}
	return q
}

// jPSSellLand: a landed pre-send sell (v3 card: sells + SOL out). The Python v1 ignores these records, so this
// never creates a session or moves a clock.
func (M *Model) jPSSellLand(line []byte) {
	if len(M.Sessions) == 0 {
		return
	}
	S := M.jcur()
	sol, _ := numAfter(line, `"sol":`)
	S.Tx.add(false, sol, tOf(line))
}

func (M *Model) jJSON(o Obj) {
	e, _ := StrKey(o, "ev")
	if e == "run_start" {
		if M.jsess < 0 && !M.Sess(0).HasRS {
			M.jsess = 0
		} else {
			M.jsess++
		}
		S := M.jcur()
		S.HasRS = true
		t0 := NumKey(o, "t")
		S.T0 = 0
		if t0.Ok() {
			S.T0 = t0.Int()
		}
		M.setTime(S, S.T0)
		S.RS = parseRunStart(o)
		return
	}
	S := M.jcur()
	if t := NumKey(o, "t"); t.Truthy() {
		M.setTime(S, t.Int())
	}
	if strings.HasPrefix(e, "presend_live_") {
		S.PSRec = true
		M.ps(S, e, o)
	} else if e == "run_end" {
		re := &RunEnd{T: NumKey(o, "t"), Fired: NumKey(o, "fired"), Closed: NumKey(o, "closed"),
			LandedBuys: NumKey(o, "landed_buys"), Realized: NumKey(o, "realized"), Dumps: NumKey(o, "dumps"),
			Picks: NumKey(o, "picks")}
		re.Skipped = o["skipped"]
		S.RE = re
		if pl, ok := o["presend_live"]; ok && pl != nil {
			plm, isMap := pl.(map[string]any)
			if !isMap {
				if Truthy(pl) {
					M.Bad++ // Python: AttributeError on .get
				}
				return
			}
			if q, ok := plm["quiet"].(map[string]any); ok {
				qo := Obj{}
				for _, k := range []string{"skips", "stops", "warm_would", "arm_rule_on_at"} {
					qo[k] = q[k]
				}
				re.Quiet = &qo
			}
		}
	} else {
		M.reg(S, e, o)
	}
}

func parseRunStart(o Obj) RunStart {
	rs := RunStart{present: true}
	rs.Minutes = NumKey(o, "minutes")
	rs.LossCap = NumKey(o, "loss_cap")
	rs.Spend = NumKey(o, "spend")
	rs.DevSpend = NumKey(o, "dev_spend")
	rs.DevTier, rs.HasDevTier = StrKey(o, "dev_tier")
	rs.Tier, rs.HasTier = StrKey(o, "tier")
	rs.Model, rs.HasModel = StrKey(o, "model")
	rs.Wallet, rs.HasWallet = StrKey(o, "wallet")
	rs.TP = NumKey(o, "tp")
	rs.SL = NumKey(o, "sl")
	rs.HoldSlots = NumKey(o, "hold_slots")
	rs.Guard = NumKey(o, "guard")
	rs.MaxBuys = NumKey(o, "max_buys")
	rs.MaxInflight = NumKey(o, "max_inflight")
	rs.Thr = NumKey(o, "thr")
	if v, ok := o["skip_clients"]; ok {
		rs.SkipClients, rs.HasSkipClients = v, true
	}
	if l, ok := ListKey(o, "devs"); ok {
		rs.Devs = len(l)
	}
	if l, ok := ListKey(o, "nonce_accounts"); ok {
		rs.Nonce = len(l)
	}
	if m2, ok := SubObj(o, "m2"); ok {
		c := &M2Cfg{Min: NumKey(m2, "min")}
		c.Mode, c.HasMode = StrKey(m2, "mode")
		c.Model, c.HasModel = StrKey(m2, "model")
		rs.M2 = c
	}
	if _, ok := SubObj(o, "presend"); ok {
		rs.Presend = true
	}
	if pl, ok := SubObj(o, "presend_live"); ok {
		p := map[string]any{}
		p["dry"] = rawAny(pl, "dry")
		p["spend"] = NumKey(pl, "spend")
		p["k"] = NumKey(pl, "k")
		p["drop"] = NumKey(pl, "drop")
		p["deadline_slots"] = NumKey(pl, "deadline_slots")
		if s, ok := StrKey(pl, "routes"); ok {
			p["routes"] = s
		} else {
			p["routes"] = nil
		}
		p["max_fills"] = NumKey(pl, "max_fills")
		p["fee_budget"] = NumKey(pl, "fee_budget")
		p["fail_fee"] = NumKey(pl, "fail_fee")
		p["tp"] = NumKey(pl, "tp")
		p["sl"] = NumKey(pl, "sl")
		p["exit_slots"] = NumKey(pl, "exit_slots")
		p["create_slot"] = rawAny(pl, "create_slot")
		p["one_position"] = rawAny(pl, "one_position")
		rs.PSL = p
		if q, ok := SubObj(pl, "quiet"); ok {
			qs := &QuietStart{WarmupMin: NumKey(q, "warmup_min"), HistH: NumKey(q, "hist_h"), Fol: NumKey(q, "fol")}
			qs.Stop, qs.HasStop = StrKey(q, "stop")
			qs.Skip = rawAny(q, "skip")
			qs.Preload = Truthy(q["preload"])
			rs.Quiet = qs
		}
	}
	return rs
}

// rawAny is o.get(k) for a key _san leaves alone (Num for numbers, else the decoded value).
func rawAny(o Obj, k string) any {
	v, ok := o[k]
	if !ok || v == nil {
		return nil
	}
	if n := toNum(v); n.Ok() {
		return n
	}
	return v
}

// ------------------------------------------------------------------------------------- the regular (reactive) bot

func (M *Model) newTrade(kind string, S *Sess) *Trade {
	M.nextID++
	return &Trade{ID: M.nextID, Kind: kind, S: S.Idx}
}

func (M *Model) reg(S *Sess, e string, o Obj) {
	M.TradeVer++
	if e == "fire" {
		var paths []string
		seen := map[string]bool{}
		if ws, ok := ListKey(o, "writes"); ok {
			for _, w := range ws {
				wm, ok := w.(map[string]any)
				if !ok {
					continue
				}
				if st, _ := wm["st"].(string); st != "written" {
					continue
				}
				p := wm["path"]
				ps, isStr := p.(string)
				if !isStr {
					if p != nil && !Truthy(p) {
						continue
					}
					if p != nil {
						ps = PyStr(p)
					}
				}
				if ps == "" || seen[ps] {
					continue
				}
				seen[ps] = true
				paths = append(paths, ps)
			}
		}
		tr := M.newTrade("REG", S)
		tf := NumKey(o, "t_fire")
		switch {
		case tf.Truthy():
			tr.T = tf.Int()
		case NumKey(o, "t").Truthy():
			tr.T = NumKey(o, "t").Int()
		default:
			tr.T = S.CurT
		}
		tr.Mint = StrOr(o, "mint", "")
		tr.Spend = NumKey(o, "spend")
		tr.Dev = Truthy(o["dev"])
		tr.Client = StrOr(o, "client", "?")
		tr.Leader = StrOr(o, "leader", "")
		tr.Route = StrOr(o, "route", "")
		tr.BuySig, tr.HasBuySig = StrKey(o, "buy_sig")
		tr.DumpSig, tr.HasDumpSig = StrKey(o, "dump_sig")
		tr.DecUs = NumKey(o, "decision_us")
		tr.TDump = NumKey(o, "t_dump_rx")
		tr.Slot = NumKey(o, "slot")
		tr.Paths = paths
		tr.Res = "open"
		S.Reg = append(S.Reg, tr)
		S.ByMint[tr.Mint] = append(S.ByMint[tr.Mint], tr)
		M.Trades = append(M.Trades, tr)
		return
	}
	// the card's landed buys / sells (v3), counted per record like the engine's own records
	switch e {
	case "buy_land":
		S.Tx.add(true, NumKey(o, "sol").Int(), NumKey(o, "t").Int())
	case "sell_land":
		S.Tx.add(false, NumKey(o, "sol").Int(), NumKey(o, "t").Int())
	}
	mint, hasMint := StrKey(o, "mint")
	if !hasMint {
		return
	}
	cands := S.ByMint[mint]
	if len(cands) == 0 {
		return
	}
	var tr *Trade
	for _, x := range cands {
		if x.Close == nil {
			tr = x
			break
		}
	}
	if tr == nil {
		tr = cands[len(cands)-1]
	}
	switch e {
	case "buy_land":
		if tr.Land == nil {
			ld := &Land{T: NumKey(o, "t"), Slot: NumKey(o, "slot"), Ms: NumKey(o, "rx_ms_after_dump"),
				Blk: NumKey(o, "slots_after_dump"), Fee: NumKey(o, "fee"), Sol: NumKey(o, "sol")}
			ld.Sig, ld.HasSig = StrKey(o, "sig")
			ld.Via = variantPaths(o)
			tr.Land = ld
			if fee := NumKey(o, "fee"); fee.Truthy() && M.FailBuyFeeSrc != "cmdline" {
				M.FailBuyFeeSrc = "landed buy fee"
				if fee.Int() != M.FailBuyFee {
					M.FailBuyFee = fee.Int()
					for _, S2 := range M.Sessions {
						for _, t2 := range S2.Reg {
							if t2.Res == "guard" || t2.Res == "lighthouse" || t2.Res == "failed" {
								M.regUpdate(S2, t2)
							}
						}
					}
				}
			}
		}
	case "buy_failed":
		if tr.Failed == nil {
			f := &Failed{T: NumKey(o, "t"), Slot: NumKey(o, "slot")}
			f.Sig, f.HasSig = StrKey(o, "sig")
			f.Via = variantPaths(o)
			tr.Failed = f
		}
	case "land_poll":
		if !tr.HasPollErr && Truthy(o["err"]) {
			tr.PollErr, tr.HasPollErr = JSONCompact(o["err"]), true
		}
	case "timing":
		for _, x := range cands {
			if x.Timing == nil {
				x.Timing = &Timing{Reaction: NumKey(o, "reaction_ms"), ExecLag: NumKey(o, "exec_lag_ms"),
					FireToSeen: NumKey(o, "fire_to_seen_ms")}
				if b, d := NumKey(o, "buy_first_rx"), NumKey(o, "dump_first_rx"); b.Truthy() && d.Truthy() {
					x.Timing.DumpToSeen = Num{K: NumFloat, F: float64(b.Int()-d.Int()) / 1e6}
				}
				if c2, ok := SubObj(o, "clock2"); ok {
					if bs, ds := NumKey(c2, "buy_slot"), NumKey(c2, "dump_slot"); bs.Truthy() && ds.Truthy() {
						x.Timing.Blk = Num{K: NumInt, I: bs.Int() - ds.Int()}
					}
				}
				break
			}
		}
	case "exit":
		if tr.Exit == nil {
			ex := &RegExit{Slots: NumKey(o, "slots_held"), T: NumKey(o, "t")}
			ex.Why, ex.HasWhy = StrKey(o, "why")
			tr.Exit = ex
		}
	case "sell_land":
		sr := SellRec{T: NumKey(o, "t"), Sol: NumKey(o, "sol"), Fee: NumKey(o, "fee")}
		sr.Sig, sr.HasSig = StrKey(o, "sig")
		tr.Sells = append(tr.Sells, sr)
	case "close":
		sl := SanList(o, "sell_land")
		land := SanList(o, "land")
		c := &RegClose{HeldS: NumKey(o, "held_s"), ExitSlot: NumKey(o, "exit_slot"), Curve: NumKey(o, "curve_pnl"),
			Spend: NumKey(o, "spend"), Score: NumKey(o, "score")}
		c.Result, c.HasResult = StrKey(o, "result")
		c.Why, c.HasWhy = StrKey(o, "exit_why")
		if Truthy(o["err"]) {
			c.Err = JSONCompact(o["err"])
		}
		if ss, ok := ListKey(o, "sell_sigs"); ok {
			for _, x := range ss {
				xl, ok := x.([]any)
				if ok && len(xl) > 1 && Truthy(xl[1]) {
					if s, ok := xl[0].(string); ok {
						c.SellSigs = append(c.SellSigs, s)
					} else {
						c.SellSigs = append(c.SellSigs, PyStr(xl[0]))
					}
				}
			}
		}
		switch {
		case len(sl) > 2 && sl[2].Truthy():
			c.T = sl[2].Int()
		case len(land) > 2 && land[2].Truthy():
			c.T = land[2].Int()
		default:
			c.T = S.CurT
		}
		if len(sl) > 3 {
			c.SolOut = sl[3]
		}
		if len(land) > 0 {
			c.LandSlot = land[0]
		}
		tr.Close = c
	}
	M.regUpdate(S, tr)
	M.reconcile(S, mint)
}

// variantPaths: "+".join(variant.paths) when variant is a dict.
func variantPaths(o Obj) string {
	v, ok := SubObj(o, "variant")
	if !ok {
		return ""
	}
	pl, ok := v["paths"].([]any)
	if !ok {
		return ""
	}
	parts := make([]string, 0, len(pl))
	for _, p := range pl {
		s, ok := p.(string)
		if !ok {
			panic("non-string path") // Python: TypeError in join -> the record counts as bad
		}
		parts = append(parts, s)
	}
	return strings.Join(parts, "+")
}

func (M *Model) classify(tr *Trade) string {
	res, hasRes := "", false
	if tr.Close != nil {
		res, hasRes = tr.Close.Result, tr.Close.HasResult
	}
	if tr.Land != nil || (hasRes && res == "sold") {
		return "filled"
	}
	err := ""
	if tr.Close != nil && tr.Close.Err != "" {
		err = tr.Close.Err
	} else if tr.HasPollErr {
		err = tr.PollErr
	}
	if (hasRes && res == "buy_failed") || tr.Failed != nil {
		if strings.Contains(err, "6042") {
			return "guard"
		}
		if strings.Contains(err, "6001") {
			return "lighthouse"
		}
		return "failed"
	}
	if !hasRes {
		return "open"
	}
	switch res {
	case "not_landed", "buy_not_landed", "dropped", "expired":
		return "not landed"
	}
	return res
}

// book puts a trade's P&L change into its session's minute buckets (the cumulative P&L line).
func (M *Model) book(S *Sess, tr *Trade, amount int64, t int64) {
	if !tr.HasBm {
		base := t
		if !TimeOKi(t) {
			base = S.CurT
			if base == 0 {
				base = M.CurT
			}
		}
		tr.Bm, tr.HasBm = floorDiv(base, minuteNS), true
	}
	d := amount - tr.Booked
	if d != 0 {
		S.Buckets[tr.Bm] += d
		tr.Booked = amount
	}
}

func (M *Model) regUpdate(S *Sess, tr *Trade) {
	tr.Res = M.classify(tr)
	switch {
	case tr.Res == "guard" || tr.Res == "lighthouse" || tr.Res == "failed":
		tr.Pnl, tr.HasPnl = -M.FailBuyFee, true
		tr.Src = "fee"
		t := tr.T
		if tr.Failed != nil && tr.Failed.T.Truthy() {
			t = tr.Failed.T.Int()
		}
		M.book(S, tr, tr.Pnl, t)
	case tr.Res == "filled" && tr.Src != "tx":
		c := tr.Close
		if c != nil && c.HasResult && c.Result == "sold" {
			if c.SolOut.Ok() && tr.Spend.Truthy() {
				tr.Pnl, tr.HasPnl = c.SolOut.Int()-tr.Spend.Int(), true
				tr.Src = "est"
				M.book(S, tr, tr.Pnl, c.T)
			}
		}
	}
}

func (M *Model) reconcile(S *Sess, mint string) {
	M.TradeVer++
	q := S.RealQ[mint]
	if len(q) == 0 {
		return
	}
	for _, tr := range S.ByMint[mint] {
		if len(q) == 0 {
			break
		}
		if tr.Res == "filled" && tr.Src != "tx" {
			tr.Pnl, tr.HasPnl = q[0], true
			q = q[1:]
			tr.Src = "tx"
			t := tr.T
			if tr.Close != nil && tr.Close.T != 0 {
				t = tr.Close.T
			}
			M.book(S, tr, tr.Pnl, t)
			M.pushEvent(tr)
		}
	}
	if len(q) == 0 {
		delete(S.RealQ, mint)
	} else {
		S.RealQ[mint] = q
	}
}

// ------------------------------------------------------------------------------------------------- pre-send live

func wkeyOf(o Obj) WKey {
	w := NumKey(o, "w")
	if !w.Ok() {
		return WKey{}
	}
	return WKey{W: w.Int(), Ok: true}
}

func (M *Model) ps(S *Sess, e string, o Obj) {
	M.TradeVer++
	w := wkeyOf(o)
	mint := StrOr(o, "mint", "")
	key := psKey{w, mint}
	switch e {
	case "presend_live_arm":
		S.PSArmed++
		S.PSOpenSet[w] = true
		var pct, sol Num
		if trig, ok := SubObj(o, "trig"); ok {
			pct, sol = NumKey(trig, "pct"), NumKey(trig, "sol")
		}
		M.setArm(S.Idx, w, pct, sol)
		M.quietRec(S, o)
	case "presend_live_skip":
		why := StrOr(o, "why", "?")
		S.PSSkips.Add(why, 1)
		if why == "quiet" || Truthy(o["quiet_skip"]) {
			S.QSkips++
		}
		M.quietRec(S, o)
	case "presend_live_disarm":
		delete(S.PSOpenSet, w)
		why := StrOr(o, "why", "?")
		S.PSDisarms.Add(why, 1)
		if why == "quiet" {
			S.QStops++
		}
	case "presend_live_fill":
		S.PSFills++
		S.Tx.add(true, NumKey(o, "sol_in").Int(), NumKey(o, "t").Int())
		if tr := S.PSPos[key]; tr != nil && tr.PClose == nil {
			tr.NFills++ // a second attempt of the same window filled: merged into the position
			if sig, ok := StrKey(o, "sig"); ok && sig != "" {
				tr.BuySigs = append(tr.BuySigs, sig)
				M.psFillLat(tr, sig)
			}
			return
		}
		pct, wsol := M.getArm(S.Idx, w)
		tr := M.newTrade("PS", S)
		tr.W = w
		if t := NumKey(o, "t"); t.Truthy() {
			tr.T = t.Int()
		} else {
			tr.T = S.CurT
		}
		tr.Mint = mint
		tr.Spend = psSpend(S)
		tr.SolIn = NumKey(o, "sol_in")
		tr.Client = StrOr(o, "client", "?")
		tr.Path = StrOr(o, "path", "")
		tr.Ms = NumKey(o, "ms_send_to_rx")
		tr.After = NumKey(o, "slots_after_trigger")
		tr.NFills = 1
		if sig, ok := StrKey(o, "sig"); ok && sig != "" {
			tr.BuySigs = []string{sig}
			M.psFillLat(tr, sig)
		}
		tr.Res = "open"
		tr.TrigPct, tr.TrigSol = pct, wsol
		tr.Fee, tr.Tip = NumKey(o, "fee"), NumKey(o, "tip")
		tr.Late = Truthy(o["after_exit"])
		S.PSPos[key] = tr
		S.PSByKey[key] = append(S.PSByKey[key], tr)
		S.PSList = append(S.PSList, tr)
		M.Trades = append(M.Trades, tr)
		if tr.Ms.Ok() {
			S.PSLandMs = append(S.PSLandMs, tr.Ms.Float())
		}
		if tr.After.Ok() {
			S.PSAfter = append(S.PSAfter, tr.After)
		}
	case "presend_live_exit":
		if tr := S.PSPos[key]; tr != nil && !tr.HasPExit { // Python: `tr["exit"] is None`
			tr.PExit, tr.HasPExit = StrKey(o, "why")
			tr.Slots = NumKey(o, "slots_held")
			tr.Value = NumKey(o, "value")
		}
	case "presend_live_close":
		tr := S.PSPos[key]
		if tr == nil {
			tr = M.psBare(S, w, mint, NumKey(o, "spend"))
			S.PSPos[key] = tr
			S.PSByKey[key] = append(S.PSByKey[key], tr)
		}
		sl := SanList(o, "sell_land")
		land := SanList(o, "land")
		c := &PSClose{Curve: NumKey(o, "curve_pnl"), Merged: NumKey(o, "merged"), Late: NumKey(o, "late")}
		switch {
		case len(sl) > 2 && sl[2].Truthy():
			c.T = sl[2].Int()
		case len(land) > 2 && land[2].Truthy():
			c.T = land[2].Int()
		default:
			c.T = S.CurT
		}
		tr.PClose = c
		if ew, ok := StrKey(o, "exit_why"); ok && ew != "" {
			tr.PExit, tr.HasPExit = ew, true
		}
		tr.HeldS = NumKey(o, "held_s")
		tr.Res = StrOr(o, "result", "?")
		if bs, ok := ListKey(o, "buy_sigs"); ok && len(bs) > 0 {
			tr.BuySigs = nil
			for _, x := range bs {
				if s, ok := x.(string); ok {
					tr.BuySigs = append(tr.BuySigs, s)
				}
			}
		}
		tr.SellSigs = nil
		if ss, ok := ListKey(o, "sell_sigs"); ok {
			for _, x := range ss {
				xl, ok := x.([]any)
				if ok && len(xl) > 0 && Truthy(xl[0]) {
					if s, ok := xl[0].(string); ok {
						tr.SellSigs = append(tr.SellSigs, s)
					} else {
						tr.SellSigs = append(tr.SellSigs, PyStr(xl[0]))
					}
				}
			}
		}
		if cl, ok := StrKey(o, "client"); ok && cl != "" {
			tr.Client = cl
		}
		if p, ok := StrKey(o, "path"); ok && p != "" {
			tr.Path = p
		}
		if sp := NumKey(o, "spend"); sp.Truthy() {
			tr.Spend = sp
		}
		if !tr.Slots.Ok() {
			if xs := NumKey(o, "exit_slot"); xs.Truthy() && len(land) > 0 {
				if !land[0].Ok() {
					panic("land[0] is None") // Python: TypeError -> bad
				}
				if xs.K == NumFloat || land[0].K == NumFloat {
					tr.Slots = FloatNum(xs.Float() - land[0].Float())
				} else {
					tr.Slots = IntNum(xs.I - land[0].I)
				}
			}
		}
	case "presend_live_realized":
		var tr *Trade
		var first *Trade
		for _, x := range S.PSByKey[key] {
			if x.Src == "tx" {
				continue
			}
			if first == nil {
				first = x
			}
			if x.PClose != nil {
				tr = x
				break
			}
		}
		if tr == nil {
			tr = first
		}
		if tr == nil {
			tr = M.psBare(S, w, mint, Num{})
		}
		pnl := NumKey(o, "pnl")
		tr.HasPnl = pnl.Ok()
		tr.Pnl = pnl.Int()
		if src, ok := StrKey(o, "src"); ok && src != "tx" { // None (or a non-string, sanitized to None) and "tx" -> "tx"
			tr.Src = src
		} else {
			tr.Src = "tx"
		}
		S.PSNReal++
		if pnl.Ok() {
			M.pushEvent(tr)
			S.PSRealized += pnl.Int()
			if pnl.Int() > 0 {
				S.PSWins++
			}
			amt := pnl.Int()
			if tr.HasRent {
				amt += tr.Rent
			}
			t := tr.T
			if tr.PClose != nil && tr.PClose.T != 0 {
				t = tr.PClose.T
			}
			M.book(S, tr, amt, t)
			S.RealRecs = append(S.RealRecs, MinAmt{pnl.Int(), tr.Bm})
		}
	case "presend_live_ata_close":
		if IsFalse(o["ok"]) {
			S.PSATAFail++
			return
		}
		d := NumKey(o, "delta").Int()
		S.PSRent += d
		var tr *Trade
		for _, x := range S.PSList {
			if x.Mint == mint && !x.HasRent && x.PClose != nil {
				tr = x
				break
			}
		}
		if tr == nil {
			for i := len(S.PSList) - 1; i >= 0; i-- {
				x := S.PSList[i]
				if x.Mint == mint && !x.HasRent {
					tr = x
					break
				}
			}
		}
		if tr != nil {
			tr.Rent, tr.HasRent = d, true
			amt := d
			if tr.HasPnl {
				amt += tr.Pnl
			}
			t := tr.T
			if tr.PClose != nil && tr.PClose.T != 0 {
				t = tr.PClose.T
			}
			M.book(S, tr, amt, t)
			S.RentRecs = append(S.RentRecs, MinAmt{d, tr.Bm})
		} else {
			base := S.CurT
			if base == 0 {
				base = M.CurT
			}
			mm := floorDiv(base, minuteNS)
			S.Buckets[mm] += d
			S.RentFree[mm] += d
			S.RentRecs = append(S.RentRecs, MinAmt{d, mm})
		}
	case "presend_live_stop":
		r := StopRec{T: NumKey(o, "t"), Fees: NumKey(o, "fees"), Fills: NumKey(o, "fills")}
		r.Why, r.HasWhy = StrKey(o, "why")
		S.PSStop = append(S.PSStop, r)
	case "presend_live_end_check":
		S.PSEndChk.Add(StrOr(o, "action", "?"), 1)
	case "presend_live_held":
		S.PSHeld++
	case "presend_live_quiet_preload":
		S.QPreload = &Preload{Ok: rawAny(o, "ok"), Secs: NumKey(o, "secs"), CoveredH: NumKey(o, "covered_h"),
			OnAt: NumKey(o, "arm_rule_on_at"), T: NumKey(o, "t")}
	}
}

func psSpend(S *Sess) Num {
	if S.RS.PSL != nil {
		if n, ok := S.RS.PSL["spend"].(Num); ok && n.Truthy() {
			return n
		}
	}
	if n, ok := S.PSL["spend"].(Num); ok {
		return n
	}
	return Num{}
}

func (M *Model) psBare(S *Sess, w WKey, mint string, spend Num) *Trade {
	tr := M.newTrade("PS", S)
	tr.W = w
	tr.T = S.CurT
	tr.Mint = mint
	if spend.Truthy() {
		tr.Spend = spend
	} else if S.RS.PSL != nil {
		if n, ok := S.RS.PSL["spend"].(Num); ok {
			tr.Spend = n
		}
	}
	tr.Client = "?"
	tr.Res = "?"
	S.PSList = append(S.PSList, tr)
	M.Trades = append(M.Trades, tr)
	return tr
}

func (M *Model) setArm(sidx int, w WKey, pct, sol Num) {
	k := [2]int64{int64(sidx), w.W}
	if !w.Ok {
		k[1] = -1 << 62
	}
	if _, ok := M.armInfo[k]; !ok {
		M.armOrder = append(M.armOrder, k)
	}
	M.armInfo[k] = armRec{key: k, pct: pct, sl: sol}
	if len(M.armInfo) > 3000 {
		old := M.armOrder[0]
		M.armOrder = M.armOrder[1:]
		delete(M.armInfo, old)
	}
}

func (M *Model) getArm(sidx int, w WKey) (Num, Num) {
	k := [2]int64{int64(sidx), w.W}
	if !w.Ok {
		k[1] = -1 << 62
	}
	if r, ok := M.armInfo[k]; ok {
		return r.pct, r.sl
	}
	return Num{}, Num{}
}

func (M *Model) quietRec(S *Sess, o Obj) {
	q, ok := SubObj(o, "quiet")
	if !ok {
		return
	}
	if Truthy(q["would_skip"]) {
		S.QWould++
	}
	if v, ok := q["rule_on"]; ok {
		if Truthy(v) {
			S.QRuleOn = 1
		} else {
			S.QRuleOn = 0
		}
	}
}

// Reset clears the model (the files were truncated / replaced).
func (M *Model) Reset() *Model {
	fee := int64(0)
	if M.FailBuyFeeSrc == "cmdline" {
		fee = M.FailBuyFee
	}
	return NewModel(fee, M.LogKeep)
}
