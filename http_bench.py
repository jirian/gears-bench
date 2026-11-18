#!/usr/bin/env python3
"""Compares HTTP servers under the same closed-loop load: Go's net/http and gears-io-http on its backends.

    http_bench.py --rounds 5 --save results/http.json

Every round starts each server afresh, pinned to --server-cpus, warms it up, and measures it with http-bench's
loadgen pinned to --load-cpus, for each path and connection count; the servers take turns within a round, so that
drift in the machine's load falls on all of them alike. Reports the median and quartiles of requests per second and
of p50/p99 latency across rounds.
"""
import json
import os
import socket
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BUILDS = os.path.join(HERE, "bench-builds")
LOADGEN = os.path.join(HERE, "http-bench", "loadgen.bin")

SERVERS = {
    "go": lambda port: [os.path.join(HERE, "http-bench", "goserver.bin"), "-addr", f"127.0.0.1:{port}"],
    "gears-uring": lambda port: [os.path.join(BUILDS, "httpbench-native"), str(port)],
    "gears-uring-runtime": lambda port: [os.path.join(BUILDS, "httpbench-native-runtime"), str(port)],
    "gears-uring-runtime-nightly": lambda port: [os.path.join(BUILDS, "httpbench-native-runtime-nightly"), str(port)],
    "gears-uring-stackless": lambda port: [os.path.join(BUILDS, "httpbench-native-stackless-nightly"), str(port)],
    "gears-uring-before": lambda port: [os.path.join(BUILDS, "httpbench-native.before-split"), str(port)],
    "gears-nio-caller": lambda port: [os.path.join(BUILDS, "http-jvm.sh"), str(port), "caller"],
    "gears-nio-reactors": lambda port: [os.path.join(BUILDS, "http-jvm.sh"), str(port), "reactors"],
    "gears-nio-reference": lambda port: [os.path.join(BUILDS, "http-jvm-reference.sh"), str(port)],
    "gears-nio-linked": lambda port: [os.path.join(BUILDS, "http-jvm-linked.sh"), str(port)],
    "gears-uring-main": lambda port: [os.path.join(BUILDS, "httpbench-native-main"), str(port)],
    "gears-uring-spin": lambda port: [os.path.join(BUILDS, "httpbench-native-spin"), str(port)],
    "gears-uring-spin-commix": lambda port: [os.path.join(BUILDS, "httpbench-native-spin-commix"), str(port)],
    "gears-uring-text": lambda port: [os.path.join(BUILDS, "httpbench-native-text"), str(port)],
    "gears-uring-text2": lambda port: [os.path.join(BUILDS, "httpbench-native-text2"), str(port)],
    "gears-uring-text3": lambda port: [os.path.join(BUILDS, "httpbench-native-text3"), str(port)],
    "gears-uring-text4": lambda port: [os.path.join(BUILDS, "httpbench-native-text4"), str(port)],
    "gears-uring-timer": lambda port: [os.path.join(BUILDS, "httpbench-native-timer"), str(port)],
    "gears-uring-duewatch": lambda port: [os.path.join(BUILDS, "httpbench-native-duewatch"), str(port)],
    "gears-uring-tick": lambda port: [os.path.join(BUILDS, "httpbench-native-tick"), str(port)],
    "gears-uring-nowatcher": lambda port: [os.path.join(BUILDS, "httpbench-native-nowatcher"), str(port)],
    "gears-uring-conngroup": lambda port: [os.path.join(BUILDS, "httpbench-native-conngroup"), str(port)],
    "gears-uring-nolimits": lambda port: [os.path.join(BUILDS, "httpbench-native-nolimits"), str(port)],
    "gears-uring-noabandon": lambda port: [os.path.join(BUILDS, "httpbench-native-noabandon"), str(port)],
    "gears-reference-main": lambda port: [os.path.join(BUILDS, "http-jvm-main.sh"), str(port)],
    "gears-reference-now": lambda port: [os.path.join(BUILDS, "http-jvm-now.sh"), str(port)],
}
JVM = {"gears-nio-caller", "gears-nio-reactors", "gears-nio-reference", "gears-nio-linked", "gears-reference-main", "gears-reference-now"}


def wait_listening(port, limit=30):
    deadline = time.time() + limit
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


def load(port, path, conns, seconds, warmup, cpus):
    out = subprocess.run(
        ["taskset", "-c", cpus, LOADGEN, "-addr", f"127.0.0.1:{port}", "-path", path, "-c", str(conns),
         "-d", f"{seconds}s", "-w", f"{warmup}s"],
        capture_output=True, text=True, timeout=seconds + warmup + 60,
        env={**os.environ, "GOMAXPROCS": str(len(cpus.split(",")))},
    ).stdout
    for line in out.splitlines():
        p = line.split()
        if p and p[0] == "http:":
            return {"rps": float(p[2]), "p50": float(p[4]), "p99": float(p[6]), "p999": float(p[8]),
                    "errors": int(p[11])}
    return None


def quart(xs):
    xs = sorted(xs)
    if len(xs) < 4:
        return xs[0], statistics.median(xs), xs[-1]
    q = statistics.quantiles(xs, n=4, method="inclusive")
    return q[0], q[1], q[2]


def main(argv):
    rounds, save, seconds = 5, None, 10
    server_cpus, load_cpus = "0,1", "4,5,6,7"
    conns_list, paths = [1, 64], ["/hello", "/items/42"]
    names = list(SERVERS)
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--rounds": rounds = int(argv[i + 1])
        elif a == "--save": save = argv[i + 1]
        elif a == "--seconds": seconds = int(argv[i + 1])
        elif a == "--servers": names = argv[i + 1].split(",")
        elif a == "--conns": conns_list = [int(c) for c in argv[i + 1].split(",")]
        else: raise SystemExit(f"unknown argument {a}")
        i += 2
    results = {}
    port = 18100
    for r in range(rounds):
        for name in names:
            port += 1
            server = subprocess.Popen(["taskset", "-c", server_cpus] + SERVERS[name](port),
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                if not wait_listening(port):
                    print(f"{name} did not listen", file=sys.stderr)
                    continue
                first = True
                for path in paths:
                    for conns in conns_list:
                        warmup = 10 if (name in JVM and first) else 2
                        first = False
                        m = load(port, path, conns, seconds, warmup, load_cpus)
                        key = f"{path} c={conns}"
                        results.setdefault(name, {}).setdefault(key, []).append(m)
                        print(f"round {r + 1}/{rounds} {name} {key}: {m}", file=sys.stderr)
            finally:
                server.terminate()
                try:
                    server.wait(15)
                except subprocess.TimeoutExpired:
                    server.kill()
                time.sleep(1)
    keys = [f"{p} c={c}" for p in paths for c in conns_list]
    for key in keys:
        print(f"\n{key}")
        print(f"{'server':20}{'req/s median [q1-q3]':>32}{'p50 us':>10}{'p99 us':>10}{'errors':>8}")
        for name in names:
            ms = [m for m in results.get(name, {}).get(key, []) if m]
            if not ms:
                print(f"{name:20}{'-':>32}")
                continue
            q1, med, q3 = quart([m["rps"] for m in ms])
            p50 = statistics.median(m["p50"] for m in ms)
            p99 = statistics.median(m["p99"] for m in ms)
            errs = sum(m["errors"] for m in ms)
            print(f"{name:20}{med:>14.0f} [{q1:>7.0f}-{q3:>7.0f}]{p50:>10.0f}{p99:>10.0f}{errs:>8}")
    if save:
        with open(save, "w") as f:
            json.dump({"date": time.strftime("%Y-%m-%d %H:%M"), "rounds": rounds, "seconds": seconds,
                       "server_cpus": server_cpus, "load_cpus": load_cpus, "results": results}, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
