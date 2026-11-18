#!/usr/bin/env python3
"""Runs bench builds alternately, pinned to the same CPUs, and reports each scenario's median and quartiles.

    bench_runner.py --runs 10 --cpus 2,3 --save out.json \
        uring='/path/iouringdemos bench' ce='/path/cebench bench' -- --scenarios pingpong,concurrent

Each label=command is run --runs times, the builds taking turns in every round, so that drift in the machine's load
falls on all of them alike; each run is pinned with taskset to --cpus. Arguments after -- go to every command. A
command prints `bench: <scenario> <ops> <seconds> <ops/s> <us/op>` lines (gearsbench and cebench both do); the table
gives the median µs/op and the quartiles, which on this machine matter more than the median (unpinned spread ~50%).
"""
import json
import os
import shlex
import statistics
import subprocess
import sys
import time


def quartiles(xs):
    xs = sorted(xs)
    if len(xs) < 4:
        return xs[0], statistics.median(xs), xs[-1]
    q = statistics.quantiles(xs, n=4, method="inclusive")
    return q[0], q[1], q[2]


def main(argv):
    runs, cpus, save, timeout = 10, "2,3", None, 900
    builds, extra = [], []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--":
            extra = argv[i + 1:]
            break
        if a == "--runs":
            runs = int(argv[i + 1]); i += 2; continue
        if a == "--cpus":
            cpus = argv[i + 1]; i += 2; continue
        if a == "--save":
            save = argv[i + 1]; i += 2; continue
        if a == "--timeout":
            timeout = int(argv[i + 1]); i += 2; continue
        label, _, command = a.partition("=")
        builds.append((label, shlex.split(command)))
        i += 1
    results = {label: {} for label, _ in builds}
    failures = []
    load_before = open("/proc/loadavg").read().split()[:3]
    for r in range(runs):
        for label, command in builds:
            full = ["taskset", "-c", cpus] + command + extra
            try:
                out = subprocess.run(full, capture_output=True, text=True, timeout=timeout).stdout
            except subprocess.TimeoutExpired:
                failures.append(f"{label} run {r}: timed out")
                continue
            found = 0
            for line in out.splitlines():
                parts = line.split()
                if len(parts) == 6 and parts[0] == "bench:" and parts[1] != "scenario":
                    results[label].setdefault(parts[1], []).append(float(parts[5]))
                    found += 1
            if found == 0:
                failures.append(f"{label} run {r}: no results")
            print(f"round {r + 1}/{runs} {label}: {found} scenarios", file=sys.stderr)
    scenarios = []
    for label, _ in builds:
        for s in results[label]:
            if s not in scenarios:
                scenarios.append(s)
    header = f"{'scenario':20}" + "".join(f"{label:>28}" for label, _ in builds)
    print(header)
    for s in scenarios:
        row = f"{s:20}"
        for label, _ in builds:
            xs = results[label].get(s)
            if xs:
                q1, m, q3 = quartiles(xs)
                row += f"{m:>12.2f} [{q1:>6.2f}-{q3:>6.2f}]"[:28].rjust(28)
            else:
                row += f"{'-':>28}"
        print(row)
    for f in failures:
        print("FAILED", f)
    if save:
        # Commands are saved relative to the harness, and to ~ outside it, so results name no home directory.
        here = os.path.dirname(os.path.abspath(__file__)) + os.sep
        home = os.path.expanduser("~")

        def portable(arg):
            return arg.replace(here, "").replace(home, "~")

        with open(save, "w") as f:
            json.dump({
                "date": time.strftime("%Y-%m-%d %H:%M"),
                "runs": runs, "cpus": cpus, "args": extra,
                "builds": {label: [portable(a) for a in command] for label, command in builds},
                "load_before": load_before, "load_after": open("/proc/loadavg").read().split()[:3],
                "results": results, "failures": failures,
            }, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
