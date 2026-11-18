#!/usr/bin/env python3
"""callers.py <script.txt> [regex...]: from `perf script -F sym,brstacksym` of a `-j any_call` profile, the hottest
symbols, or for each regex, the share of samples in a matching symbol and the callers that last called into it."""
import collections, re, sys
def clean(s):
    return re.sub(r'(L[0-9]+[a-zA-Z.$_]+)+', '', re.sub(r'_SM[0-9]+', '', s))[:110]
samples = []
for line in open(sys.argv[1]):
    line = line.strip()
    if not line: continue
    parts = line.split()
    sym = parts[0]
    edges = []  # newest first: from/to/flags... as "from+off/to+off/P/-/-/0"
    for e in parts[1:]:
        f = e.split('/')
        if len(f) >= 2: edges.append((re.sub(r'\+0x[0-9a-f]+$', '', f[0]), re.sub(r'\+0x[0-9a-f]+$', '', f[1])))
    samples.append((sym, edges))
T = len(samples)
if len(sys.argv) == 2:
    c = collections.Counter(clean(s) for s, _ in samples)
    for k, v in c.most_common(40): print(f"{100*v/T:5.2f}  {k}")
for target in sys.argv[2:]:
    c = collections.Counter(); n = 0
    for sym, edges in samples:
        if re.search(target, sym):
            n += 1
            caller = next((f for f, t in edges if t == sym), '?')
            c[clean(caller)] += 1
    print(f"=== {target}: {100*n/T:.2f}% of {T}")
    for k, v in c.most_common(10): print(f"  {100*v/T:5.2f}%  {k}")
