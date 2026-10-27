package core

import "sort"

// OCounter is Python's collections.Counter with its insertion order (most_common ties keep that order).
type OCounter struct {
	keys []string
	m    map[string]int64
}

func NewOCounter() *OCounter { return &OCounter{m: map[string]int64{}} }

// Add adds n to key k (a new key goes to the end of the order).
func (c *OCounter) Add(k string, n int64) {
	if _, ok := c.m[k]; !ok {
		c.keys = append(c.keys, k)
	}
	c.m[k] += n
}

// Update is Counter.update(other).
func (c *OCounter) Update(o *OCounter) {
	if o == nil {
		return
	}
	for _, k := range o.keys {
		c.Add(k, o.m[k])
	}
}

func (c *OCounter) Get(k string) int64 { return c.m[k] }
func (c *OCounter) Len() int           { return len(c.keys) }
func (c *OCounter) Keys() []string     { return c.keys }

// KV is one counter entry.
type KV struct {
	K string
	N int64
}

// Items in insertion order.
func (c *OCounter) Items() []KV {
	out := make([]KV, len(c.keys))
	for i, k := range c.keys {
		out[i] = KV{k, c.m[k]}
	}
	return out
}

// MostCommon is Counter.most_common(): by count, descending; ties in insertion order.
func (c *OCounter) MostCommon() []KV {
	out := c.Items()
	sort.SliceStable(out, func(i, j int) bool { return out[i].N > out[j].N })
	return out
}

// JSON is dict(counter) as an ordered JSON object.
func (c *OCounter) JSON() *JObj {
	o := &JObj{}
	for _, k := range c.keys {
		o.Set(k, c.m[k])
	}
	return o
}

// Ring is a bounded FIFO (Python deque(maxlen=n)).
type Ring struct {
	buf   []LogItem
	start int
	n     int
}

func NewRing(n int) *Ring { return &Ring{buf: make([]LogItem, n)} }

// Push appends, dropping the oldest when full.
func (r *Ring) Push(x LogItem) {
	if len(r.buf) == 0 {
		return
	}
	if r.n < len(r.buf) {
		r.buf[(r.start+r.n)%len(r.buf)] = x
		r.n++
		return
	}
	r.buf[r.start] = x
	r.start = (r.start + 1) % len(r.buf)
}

func (r *Ring) Len() int { return r.n }

// At is the i-th oldest item.
func (r *Ring) At(i int) LogItem { return r.buf[(r.start+i)%len(r.buf)] }

// TxTally counts landed buys / sells and their SOL (into / out of the curve), in total and per unix minute.
type TxTally struct {
	Buys, Sells     int64
	BuySol, SellSol int64
	ByMin           map[int64]*TxMin
}

// TxMin is one minute's landed buys / sells.
type TxMin struct{ Buys, Sells, BuySol, SellSol int64 }

func newTxTally() TxTally { return TxTally{ByMin: map[int64]*TxMin{}} }

func (x *TxTally) add(buy bool, sol int64, t int64) {
	var mm int64 = -1
	if TimeOKi(t) {
		mm = floorDiv(t, minuteNS)
	}
	b := x.ByMin[mm]
	if b == nil {
		b = &TxMin{}
		x.ByMin[mm] = b
	}
	if buy {
		x.Buys++
		x.BuySol += sol
		b.Buys++
		b.BuySol += sol
	} else {
		x.Sells++
		x.SellSol += sol
		b.Sells++
		b.SellSol += sol
	}
}
