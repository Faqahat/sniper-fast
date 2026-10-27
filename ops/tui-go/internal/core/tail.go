package core

import (
	"bytes"
	"io"
	"os"
	"syscall"
)

// Tail is an incremental reader of a growing file: it keeps its offset and a partial last line, and notices a
// truncation or a replacement (new inode), which sets Reset (the caller then re-reads everything).
type Tail struct {
	Path   string
	Off    int64
	Buf    []byte
	ino    uint64
	hasIno bool
	Size   int64
	MTime  float64 // seconds; 0 = never stat'ed
	Reset  bool
	Exists bool
	Err    string
}

// NewTail starts at offset 0.
func NewTail(path string) *Tail { return &Tail{Path: path} }

// Stat refreshes size / mtime / inode; false when the file cannot be stat'ed.
func (t *Tail) Stat() bool {
	fi, err := os.Stat(t.Path)
	if err != nil {
		t.Exists = false
		t.Err = err.Error()
		return false
	}
	t.Exists = true
	t.Err = ""
	var ino uint64
	if st, ok := fi.Sys().(*syscall.Stat_t); ok {
		ino = st.Ino
	}
	if t.hasIno && (ino != t.ino || fi.Size() < t.Off) {
		t.Off = 0
		t.Buf = nil
		t.Reset = true
	}
	t.ino, t.hasIno = ino, true
	t.Size = fi.Size()
	t.MTime = float64(fi.ModTime().UnixNano()) / 1e9
	return true
}

// Pending is the number of bytes not read yet.
func (t *Tail) Pending() int64 {
	if t.Size > t.Off {
		return t.Size - t.Off
	}
	return 0
}

// Read returns the complete new lines (without their newline) from at most maxBytes of new data. The lines are
// fresh slices the caller may keep.
func (t *Tail) Read(maxBytes int64) [][]byte {
	if !t.Stat() || t.Size <= t.Off {
		return nil
	}
	f, err := os.Open(t.Path)
	if err != nil {
		t.Err = err.Error()
		return nil
	}
	defer f.Close()
	n := t.Size - t.Off
	if n > maxBytes {
		n = maxBytes
	}
	data := make([]byte, len(t.Buf), int64(len(t.Buf))+n)
	copy(data, t.Buf)
	got, err := f.ReadAt(data[len(t.Buf):len(t.Buf)+int(n)], t.Off)
	if err != nil && err != io.EOF {
		t.Err = err.Error()
	}
	if got <= 0 {
		return nil
	}
	t.Off += int64(got)
	data = data[:len(t.Buf)+got]
	lines := bytes.Split(data, []byte{'\n'})
	last := lines[len(lines)-1]
	lines = lines[:len(lines)-1]
	if len(last) > 8_000_000 { // a runaway line without a newline: drop it (never grow without bound)
		t.Buf = nil
	} else {
		t.Buf = append([]byte(nil), last...)
	}
	return lines
}

// FlushPartialJSON returns a complete JSON object sitting without its newline (a writer that paused between the
// record and the newline), and clears it from the buffer.
func (t *Tail) FlushPartialJSON() []byte {
	b := bytes.TrimSpace(t.Buf)
	if len(b) >= 2 && b[0] == '{' && b[len(b)-1] == '}' {
		if _, _, ok := DecodeObj(b); !ok {
			return nil
		}
		t.Buf = nil
		return append([]byte(nil), b...)
	}
	return nil
}
