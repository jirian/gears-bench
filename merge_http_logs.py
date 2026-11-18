#!/usr/bin/env python3
"""merge_http_logs.py <out.json> <log>...: http_bench.py's per-round lines from several runs (only complete rounds,
those in which every server measured every case) as one table: median and quartiles of req/s, median p50 and p99."""
import ast, collections, json, re, statistics, sys

def quart(xs):
    xs = sorted(xs)
    if len(xs) < 4: return xs[0], statistics.median(xs), xs[-1]
    q = statistics.quantiles(xs, n=4, method="inclusive"); return q[0], q[1], q[2]

rows = collections.defaultdict(list)  # (server, key) -> [m]
for log in sys.argv[2:]:
    per_round = collections.defaultdict(dict)
    for line in open(log):
        m = re.match(r"round (\d+)/\d+ (\S+) (/\S+ c=\d+): (\{.*\})", line.strip())
        if m: per_round[int(m.group(1))][(m.group(2), m.group(3))] = ast.literal_eval(m.group(4))
    full = max(len(v) for v in per_round.values())
    for r, cases in sorted(per_round.items()):
        if len(cases) == full:
            for k, v in cases.items(): rows[k].append(v)
        else: print(f"{log}: round {r} incomplete ({len(cases)}/{full}), dropped", file=sys.stderr)
servers = list(dict.fromkeys(s for s, _ in rows)); keys = list(dict.fromkeys(k for _, k in rows))
out = {}
for key in keys:
    print(f"\n{key}\n{'server':28s}  rounds  req/s median [q1-q3]       p50 us  p99 us  errors")
    for s in servers:
        ms = rows.get((s, key))
        if not ms: continue
        q1, med, q3 = quart([m["rps"] for m in ms])
        p50 = statistics.median(m["p50"] for m in ms); p99 = statistics.median(m["p99"] for m in ms)
        err = sum(m["errors"] for m in ms)
        out.setdefault(key, {})[s] = {"rounds": len(ms), "rps": [q1, med, q3], "p50": p50, "p99": p99, "errors": err}
        print(f"{s:28s}  {len(ms):5d}  {med:8.0f} [{q1:7.0f}-{q3:7.0f}]  {p50:7.0f} {p99:7.0f} {err:6d}")
json.dump(out, open(sys.argv[1], "w"), indent=1)
