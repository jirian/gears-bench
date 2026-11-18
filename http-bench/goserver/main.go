// The Go net/http server the gears HTTP server is compared with: the same two routes, as Go's standard library
// serves them with its defaults.
package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"
	"strconv"
)

func main() {
	addr := flag.String("addr", "127.0.0.1:8090", "where to listen")
	flag.Parse()
	mux := http.NewServeMux()
	mux.HandleFunc("GET /hello", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		w.Write([]byte("Hello, world"))
	})
	mux.HandleFunc("GET /items/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
		if err != nil {
			http.Error(w, "bad id", http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"id":%d,"name":"item %d"}`, id, id)
	})
	log.Fatal(http.ListenAndServe(*addr, mux))
}
