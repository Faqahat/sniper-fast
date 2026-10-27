package core

import (
	"bytes"
	"math"
	"sort"
	"strconv"
	"unsafe"
)

// Latency (v3, display only: no money figure depends on it). Pre-send: every seen try's send -> seen and its block
// (presend_attempt_land: ms_send_to_rx, slots_after_send); the dump -> land of the fills and of the tries that failed
// 6042 after a dump that met the drop rule (the price had bounced back); per leader client family; each fill's own
// figures from its filling try. Regular: buy_land / timing (see TradeLatency).

// Hist is a sparse histogram of milliseconds (bounded memory): 0.1 ms buckets below 1 s, 1 ms buckets to 10 s, 10 ms
// above.
type Hist struct {
	B map[int32]int64
	N int64
}

func histKey(ms float64) int32 {
	switch {
	case ms < 1000:
		return int32(math.Floor(ms * 10))
	case ms < 10000:
		return 10000 + int32(math.Floor(ms-1000))
	}
	return 19000 + int32(math.Min(math.Floor((ms-10000)/10), 1e8))
}

func histVal(k int32) float64 {
	switch {
	case k < 10000:
		return (float64(k) + 0.5) / 10
	case k < 19000:
		return 1000 + float64(k-10000) + 0.5
	}
	return 10000 + float64(k-19000)*10 + 5
}

// Add one value.
func (h *Hist) Add(ms float64) {
	if math.IsNaN(ms) || math.IsInf(ms, 0) {
		return
	}
	if h.B == nil {
		h.B = map[int32]int64{}
	}
	h.B[histKey(ms)]++
	h.N++
}

// Merge adds o's counts.
func (h *Hist) Merge(o *Hist) {
	if o == nil || o.N == 0 {
		return
	}
	if h.B == nil {
		h.B = map[int32]int64{}
	}
	for k, n := range o.B {
		h.B[k] += n
	}
	h.N += o.N
}

// Quantile is the linear-interpolation quantile (numpy's default; p 0.5 = the median of an even count = the mean of
// the two middle values) of the values at their bucket middles; ok false when empty.
func (h *Hist) Quantile(p float64) (float64, bool) {
	q, ok := h.Quantiles(p)
	if !ok {
		return 0, false
	}
	return q[0], true
}

// Quantiles is Quantile for several p (one sort).
func (h *Hist) Quantiles(ps ...float64) ([]float64, bool) {
	if h == nil || h.N == 0 {
		return nil, false
	}
	keys := make([]int32, 0, len(h.B))
	for k := range h.B {
		keys = append(keys, k)
	}
	sort.Slice(keys, func(i, j int) bool { return keys[i] < keys[j] })
	// the value at a 0-based rank
	at := func(r int64) float64 {
		var cum int64
		for _, k := range keys {
			cum += h.B[k]
			if cum > r {
				return histVal(k)
			}
		}
		return histVal(keys[len(keys)-1])
	}
	out := make([]float64, len(ps))
	for i, p := range ps {
		pos := math.Max(0, math.Min(1, p)) * float64(h.N-1)
		lo := int64(math.Floor(pos))
		hi := min(lo+1, h.N-1)
		vlo, vhi := at(lo), at(hi)
		out[i] = vlo + (vhi-vlo)*(pos-float64(lo))
	}
	return out, true
}

// LatAgg: one session's (or one leader client family's) pre-send latency.
type LatAgg struct {
	S2R    Hist     // send -> seen of every seen try (ms_send_to_rx)
	Blk    [4]int64 // the seen tries by slots after the send: 0 (the send block), 1, 2, 3+
	Fills  int64    // fills (res ok)
	FillDL Hist     // dump -> land of the fills after a dump that met the drop rule
	Bounce Hist     // dump -> land of the tries that failed 6042 after such a dump (the price had bounced back)
}

// Seen is the number of seen tries (those with a send -> seen).
func (a *LatAgg) Seen() int64 { return a.Blk[0] + a.Blk[1] + a.Blk[2] + a.Blk[3] }

// Merge adds o.
func (a *LatAgg) Merge(o *LatAgg) {
	if o == nil {
		return
	}
	a.S2R.Merge(&o.S2R)
	for i := range a.Blk {
		a.Blk[i] += o.Blk[i]
	}
	a.Fills += o.Fills
	a.FillDL.Merge(&o.FillDL)
	a.Bounce.Merge(&o.Bounce)
}

// PSLat is a pre-send fill's latency, from its filling try (the presend_attempt_land record of the fill's sig).
type PSLat struct {
	DL       Num    // ms after the dump: ms_after_d_a, else ms_after_x_a
	DLSrc    string // "d" / "x"
	SendSeen Num    // ms_send_to_rx
	Blk      Num    // slots_after_send (0 = landed in the send block)
	NBetween Num    // traders between the dump and us
	Client   string // the client of the leader that landed it
	Path     string
	N        Num    // the try's number in its window
	DropPct  Num    // the dump's drop
	PRel     Num    // the price after the dump relative to the window's (<= 1 - drop: the drop rule met)
	Leader   string // the leader the try was sent to (from its presend_attempt, when still in the recent-try ring)
}

// floatAfter is the JSON number right after key (the first occurrence); false for null / missing.
func floatAfter(line []byte, key string) (float64, bool) {
	i := bytes.Index(line, []byte(key))
	if i < 0 {
		return 0, false
	}
	i += len(key)
	j := i
	for j < len(line) && (line[j] == '-' || line[j] == '+' || line[j] == '.' || line[j] == 'e' || line[j] == 'E' || (line[j] >= '0' && line[j] <= '9')) {
		j++
	}
	if j == i {
		return 0, false
	}
	// no copy: the number's bytes as a string for ParseFloat only (not kept)
	v, err := strconv.ParseFloat(unsafe.String(&line[i], j-i), 64)
	if err != nil {
		return 0, false
	}
	return v, true
}

// strAfter is the JSON string right after key (key ends with the opening quote), raw (no unescaping).
func strAfter(line []byte, key string) (string, bool) {
	i := bytes.Index(line, []byte(key))
	if i < 0 {
		return "", false
	}
	rest := line[i+len(key):]
	j := bytes.IndexByte(rest, '"')
	if j < 0 {
		return "", false
	}
	return string(rest[:j]), true
}

// objAfter is the flat JSON object right after key (`"d":{`), up to its first '}'.
func objAfter(line []byte, key string) []byte {
	i := bytes.Index(line, []byte(key))
	if i < 0 {
		return nil
	}
	rest := line[i+len(key):]
	j := bytes.IndexByte(rest, '}')
	if j < 0 {
		return nil
	}
	return rest[:j]
}

// latKind is the session's aggregate for a leader client family.
func (S *Sess) latKind(kind string) *LatAgg {
	if S.LatKind == nil {
		S.LatKind = map[string]*LatAgg{}
	}
	a := S.LatKind[kind]
	if a == nil {
		a = &LatAgg{}
		S.LatKind[kind] = a
	}
	return a
}

// dropFrac is the pre-send drop rule (run_start presend_live.drop; 0.12 when unknown).
func (S *Sess) dropFrac() float64 {
	if S.RS.PSL != nil {
		if n, ok := S.RS.PSL["drop"].(Num); ok && n.Truthy() {
			return n.Float()
		}
	}
	return 0.12
}

// the recent tries' leaders, by the first 24 characters of their sig (a fill follows its try within a few records)
const (
	tryRingN = 1024
	sigKeyN  = 24
)

func sigKey(sig string) string {
	if len(sig) > sigKeyN {
		return sig[:sigKeyN]
	}
	return sig
}

// latAttempt: a sent try (presend_attempt): its window's try count, and its leader kept a while by sig.
func (M *Model) latAttempt(S *Sess, line []byte, dry bool) {
	if dry {
		return
	}
	// sorted keys: leader, then sig, then w
	tail := line
	leader := ""
	if i := bytes.Index(line, []byte(`leader":"`)); i >= 0 {
		tail = line[i:]
		leader, _ = strAfter(tail, `leader":"`)
	}
	w, okw := numAfter(tail, `"w":`)
	if !okw && len(tail) != len(line) {
		w, okw = numAfter(line, `"w":`)
	}
	if okw {
		if S.WinTries == nil {
			S.WinTries = map[int64]int64{}
		}
		S.WinTries[w]++
	}
	sig, ok := strAfter(tail, `"sig":"`)
	if !ok && len(tail) != len(line) {
		sig, ok = strAfter(line, `"sig":"`)
	}
	if !ok || sig == "" {
		return
	}
	if M.tryLeader == nil {
		M.tryLeader = map[string]string{}
	}
	k := sigKey(sig)
	if _, seen := M.tryLeader[k]; !seen {
		M.tryOrder = append(M.tryOrder, k)
		if len(M.tryOrder) > tryRingN {
			delete(M.tryLeader, M.tryOrder[0])
			M.tryOrder = M.tryOrder[1:]
		}
	}
	M.tryLeader[k] = leader
}

// latLand: a try's landing (presend_attempt_land), read by substring (the high-volume record, never decoded). The
// engine writes sorted keys, so everything wanted sits after "client" (behind the long trade lists): the searches
// start there, and look at the whole line only when a key is not found there.
func (M *Model) latLand(S *Sess, line []byte, res string) {
	tail := line
	client := ""
	if i := bytes.Index(line, []byte(`client":"`)); i >= 0 { // patterns start past their quote: '"' is everywhere
		tail = line[i:]
		client, _ = strAfter(tail, `client":"`)
	}
	fnum := func(key string) (float64, bool) {
		if v, ok := floatAfter(tail, key); ok || len(tail) == len(line) {
			return v, ok
		}
		return floatAfter(line, key)
	}
	fstr := func(key string) string {
		if v, ok := strAfter(tail, key); ok || len(tail) == len(line) {
			return v
		}
		v, _ := strAfter(line, key)
		return v
	}
	K := S.latKind(KindOf(client))
	ss, okss := fnum(`ms_send_to_rx":`)
	blk, okb := fnum(`slots_after_send":`)
	if okss {
		S.Lat.S2R.Add(ss)
		K.S2R.Add(ss)
		i := 3
		if okb && blk >= 0 && blk < 3 {
			i = int(blk)
		}
		S.Lat.Blk[i]++
		K.Blk[i]++
	}
	dl, okd := fnum(`ms_after_d_a":`)
	src := "d"
	if !okd {
		dl, okd = fnum(`ms_after_x_a":`)
		src = "x"
	}
	if res == "ok" {
		S.Lat.Fills++
		K.Fills++
	}
	if !okd || (res != "ok" && res != "6042") {
		return
	}
	dobj := objAfter(tail, `"d":{`)
	if dobj == nil && len(tail) != len(line) {
		dobj = objAfter(line, `"d":{`)
	}
	prel, okp := floatAfter(dobj, `p_rel":`)
	if okp && prel <= 1-S.dropFrac()+1e-9 {
		if res == "ok" {
			S.Lat.FillDL.Add(dl)
			K.FillDL.Add(dl)
		} else {
			S.Lat.Bounce.Add(dl)
			K.Bounce.Add(dl)
		}
	}
	if res != "ok" {
		return
	}
	// the filling try: the fill's own figures
	num := func(v float64, ok bool) Num {
		if !ok {
			return Num{}
		}
		return FloatNum(v)
	}
	inum := func(v float64, ok bool) Num { // a count / slot number: an int when it is one
		if ok && v == math.Trunc(v) && math.Abs(v) < 1e15 {
			return IntNum(int64(v))
		}
		return num(v, ok)
	}
	l := &PSLat{DL: FloatNum(dl), DLSrc: src, SendSeen: num(ss, okss), Blk: inum(blk, okb), Client: client, Path: fstr(`path":"`)}
	l.NBetween = inum(fnum(`n_between":`))
	l.N = inum(fnum(`"n":`))
	l.DropPct = num(floatAfter(dobj, `drop_pct":`))
	l.PRel = num(prel, okp)
	sig := fstr(`"sig":"`)
	l.Leader = M.tryLeader[sigKey(sig)]
	if tr := M.psSigTrade[sig]; tr != nil {
		if tr.Lat == nil {
			tr.Lat = l
			M.TradeVer++
		}
		return
	}
	if M.psLandPend == nil {
		M.psLandPend = map[string]*PSLat{}
	}
	if len(M.psLandPend) < 2000 {
		M.psLandPend[sig] = l
	}
}

// psFillLat: a fill (presend_live_fill) with its sig: its latency when its try's landing came first; later lands find
// it by sig.
func (M *Model) psFillLat(tr *Trade, sig string) {
	if sig == "" {
		return
	}
	if M.psSigTrade == nil {
		M.psSigTrade = map[string]*Trade{}
	}
	M.psSigTrade[sig] = tr
	if l := M.psLandPend[sig]; l != nil {
		if tr.Lat == nil {
			tr.Lat = l
		}
		delete(M.psLandPend, sig)
	}
}

// TradeLatency: dump -> land (ms), send -> seen (ms) and the block (slots), each !Ok when unknown.
//   - pre-send: the filling try: ms_after_d_a (else ms_after_x_a), ms_send_to_rx, slots_after_send;
//   - regular: buy_land.rx_ms_after_dump (a failed buy: the timing's buy_first_rx - dump_first_rx, the same clock),
//     the timing's fire_to_seen_ms (t_fire -> buy seen), buy_land.slots_after_dump (a failed buy: the timing's
//     clock2 buy_slot - dump_slot).
func TradeLatency(tr *Trade) (dl, ss, blk Num) {
	if tr.Kind == "PS" {
		if tr.Lat != nil {
			return tr.Lat.DL, tr.Lat.SendSeen, tr.Lat.Blk
		}
		if tr.Ms.Ok() {
			return Num{}, tr.Ms, Num{}
		}
		return
	}
	if tr.Land != nil {
		dl, blk = tr.Land.Ms, tr.Land.Blk
	}
	if tr.Timing != nil {
		if !dl.Ok() {
			dl = tr.Timing.DumpToSeen
		}
		if !blk.Ok() {
			blk = tr.Timing.Blk
		}
		ss = tr.Timing.FireToSeen
	}
	return
}

// LatSummary is the pre-send latency of sessions: all, and by leader client family (most tries first).
type LatSummary struct {
	All   LatAgg
	Kinds []string
	Kind  map[string]*LatAgg
	Drop  float64
}

// LatOf sums the sessions' pre-send latency.
func LatOf(sessions []*Sess) LatSummary {
	out := LatSummary{Kind: map[string]*LatAgg{}, Drop: 0.12}
	for _, S := range sessions {
		out.All.Merge(&S.Lat)
		out.Drop = S.dropFrac()
		for k, a := range S.LatKind {
			x := out.Kind[k]
			if x == nil {
				x = &LatAgg{}
				out.Kind[k] = x
			}
			x.Merge(a)
		}
	}
	for k := range out.Kind {
		out.Kinds = append(out.Kinds, k)
	}
	order := map[string]int{"Harmonic": 0, "BAM": 1, "Jito": 2, "Firedancer": 3, "Agave": 4}
	sort.Slice(out.Kinds, func(i, j int) bool {
		a, b := out.Kinds[i], out.Kinds[j]
		oa, oka := order[a]
		ob, okb := order[b]
		if oka != okb {
			return oka
		}
		if oka {
			return oa < ob
		}
		if out.Kind[a].Seen() != out.Kind[b].Seen() {
			return out.Kind[a].Seen() > out.Kind[b].Seen()
		}
		return a < b
	})
	return out
}
