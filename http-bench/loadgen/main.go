// A closed-loop HTTP/1.1 load generator: each of -c connections sends a request, reads the whole response, and sends
// the next, for -d. Raw sockets rather than net/http's client, so that the client's own costs stay small and alike
// for every server. Prints requests per second and latency percentiles.
package main

import (
	"bufio"
	"flag"
	"fmt"
	"io"
	"net"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

func main() {
	addr := flag.String("addr", "127.0.0.1:8090", "the server")
	path := flag.String("path", "/hello", "the request's path")
	conns := flag.Int("c", 64, "connections")
	duration := flag.Duration("d", 10*time.Second, "how long to measure")
	warmup := flag.Duration("w", 2*time.Second, "how long to send first, unmeasured")
	flag.Parse()

	request := []byte("GET " + *path + " HTTP/1.1\r\nHost: bench\r\n\r\n")
	var wg sync.WaitGroup
	start := time.Now().Add(*warmup)
	end := start.Add(*duration)
	samples := make([][]time.Duration, *conns)
	errors := make([]int, *conns)
	for i := 0; i < *conns; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			conn, err := net.Dial("tcp", *addr)
			if err != nil {
				errors[i]++
				return
			}
			defer conn.Close()
			r := bufio.NewReaderSize(conn, 16384)
			local := make([]time.Duration, 0, 1<<16)
			for {
				t0 := time.Now()
				if t0.After(end) {
					break
				}
				if _, err := conn.Write(request); err != nil {
					errors[i]++
					return
				}
				if err := readResponse(r); err != nil {
					errors[i]++
					return
				}
				if t0.After(start) {
					local = append(local, time.Since(t0))
				}
			}
			samples[i] = local
		}(i)
	}
	wg.Wait()
	var all []time.Duration
	for _, s := range samples {
		all = append(all, s...)
	}
	failed := 0
	for _, e := range errors {
		failed += e
	}
	if len(all) == 0 {
		fmt.Fprintln(os.Stderr, "no responses")
		os.Exit(1)
	}
	sort.Slice(all, func(a, b int) bool { return all[a] < all[b] })
	pct := func(p float64) float64 { return float64(all[int(p*float64(len(all)-1))].Microseconds()) }
	fmt.Printf("http: rps %.0f p50 %.0f p99 %.0f p999 %.0f us errors %d\n",
		float64(len(all))/duration.Seconds(), pct(0.50), pct(0.99), pct(0.999), failed)
}

// readResponse reads one response, framed by Content-Length (the servers compared send no chunked bodies here).
func readResponse(r *bufio.Reader) error {
	length := -1
	status, err := r.ReadString('\n')
	if err != nil {
		return err
	}
	if !strings.HasPrefix(status, "HTTP/1.1 200") {
		return fmt.Errorf("status %q", status)
	}
	for {
		line, err := r.ReadString('\n')
		if err != nil {
			return err
		}
		if line == "\r\n" {
			break
		}
		if colon := strings.IndexByte(line, ':'); colon > 0 && strings.EqualFold(line[:colon], "Content-Length") {
			length, _ = strconv.Atoi(strings.TrimSpace(line[colon+1:]))
		}
	}
	if length < 0 {
		return fmt.Errorf("no Content-Length")
	}
	_, err = io.CopyN(io.Discard, r, int64(length))
	return err
}
