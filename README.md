# gears-bench

The benchmark harness behind the measurements of [Gears](https://github.com/lampepfl/gears)' async I/O on io_uring:
the scripts that run the builds, the Go server and load generator the HTTP server is compared with, the profiling
scripts, and the results. The Scala side, the gears bench (`bench/io-bench`) and the HTTP bench's server
(`bench/http-bench`), lives with the code it measures, in [jirian/gears](https://github.com/jirian/gears), branch
`feature/uring-on-main`.

Linux only: the runs are pinned to cores with `taskset`, and the native builds run on io_uring.

## Layout

| Path | What it is |
| --- | --- |
| `bench_runner.py` | Runs bench builds in turns, pinned to the same cores, and reports each scenario's median µs/op and quartiles. |
| `http_bench.py` | Starts each HTTP server afresh every round, warms it up, and measures it with `loadgen` per path and connection count. |
| `merge_http_logs.py` | Merges the per-round lines of several `http_bench.py` runs into one table, keeping only complete rounds. |
| `http-bench/goserver` | Go's `net/http` serving the same two routes as the gears HTTP bench, with the standard library's defaults. |
| `http-bench/loadgen` | A closed-loop HTTP/1.1 load generator over raw sockets: requests per second and latency percentiles. |
| `perf/` | `profile.sh` profiles a server under load (user-space `perf`, last calls via `-j any_call`); `callers.py` summarises it. |
| `results/` | Every run: the table (`.txt`), its data (`.json`) and the log of its rounds (`.log`), named by date. |

## Running

Build the Go programs into the names the scripts expect:

```sh
(cd http-bench/goserver && go build -o ../goserver.bin .)
(cd http-bench/loadgen && go build -o ../loadgen.bin .)
```

The gears builds go into `bench-builds/`, which is not tracked: each is a binary, or for the JVM a wrapper script
running the bench's classpath. In the gears repository, with the Scala Native nightly its `project/plugins.sbt` names:

```sh
sbt --client shutdown
SCALA_NATIVE_NIGHTLY=1 sbt --client 'ioHttpBenchNative/nativeLinkReleaseFast'   # the HTTP bench's server
SCALA_NATIVE_NIGHTLY=1 sbt --client 'ioUringDemos/nativeLinkReleaseFast'        # the gears bench, as `<binary> bench`
sbt --client shutdown
```

and copy the linked binary to `bench-builds/<name>`. `http_bench.py`'s `SERVERS` maps each server's name to its
build; `bench_runner.py` takes `label='command'` pairs:

```sh
./http_bench.py --rounds 5 --servers go,gears-uring-spin --save results/<date>-http.json 2> results/<date>-http.log \
  > results/<date>-http.txt
./bench_runner.py --runs 10 --cpus 2,3 --save results/<date>-backends.json \
  uring='bench-builds/iouringdemos-spin bench' -- --scenarios pingpong,pipelined
```

By default the HTTP servers run on cores 0 and 1 and the load generator on cores 4 to 7.

## Results

The report's tables come from `results/2026-11-16-backends.{txt,json}` (the backend, gears commit `0b6ac649`, and
the commit before it for *no spin*) and `results/2026-11-18-http.{txt,json}` (the HTTP server, gears commit
`7f50fe77`, and the builds it was measured against). The HTTP run was cut off after 3 of its 5 rounds, so rounds 4 and
5 were run separately (`2026-11-18-http-b.log`) and both logs were merged by `merge_http_logs.py`. Earlier runs are
kept beside them. Which gears commit each of the other builds came from was not recorded.

Absolute paths in the recorded commands and logs were rewritten relative to this directory before publishing; nothing
else in the results was changed.

## Licence

Apache License 2.0, as Gears itself; see `LICENSE`.
