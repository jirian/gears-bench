#!/bin/bash
# profile.sh <tag> <server command...>: a server pinned to cpus 0,1, serving /hello to 64 connections from loadgen on
# cpus 4-7, then: its CPU split over 5 s from /proc, and a user-space perf profile with the last calls before each sample (-j any_call; LBR call graphs are refused at paranoid 2 since Linux 7.3) over 6 s.
# Results in results/perf-<tag>; the server gets its port as its last argument.
V=$(cd "$(dirname "$0")/.." && pwd)
TAG=$1; shift; PORT=18556; OUT=$V/results/perf-$TAG; C=${CONNS:-64}; mkdir -p $OUT
# perf starts the server, as attaching to it needs ptrace rights; it records from 9 s in, after the split's window.
perf record -D 9000 -F 2999 -e cycles:u -j any_call,u -o $OUT/perf.data -- taskset -c 0,1 "$@" $PORT \
  >/dev/null 2> $OUT/record.log &
PP=$!; sleep 1
SP=$(pgrep -P $(pgrep -P $PP) 2>/dev/null || pgrep -P $PP)
GOMAXPROCS=4 taskset -c 4,5,6,7 $V/http-bench/loadgen.bin -addr 127.0.0.1:$PORT -path /hello -c $C -d 24s -w 2s > $OUT/load.txt &
LP=$!; sleep 4
read -r u1 s1 < <(awk '{print $14, $15}' /proc/$SP/stat)
sleep 5
read -r u2 s2 < <(awk '{print $14, $15}' /proc/$SP/stat)
echo "user_ticks $((u2-u1)) sys_ticks $((s2-s1)) (5 s)" > $OUT/split.txt
sleep 6
kill -INT $PP; wait $PP 2>/dev/null; kill $SP 2>/dev/null; wait $LP
perf script -i $OUT/perf.data -F sym,brstacksym 2>/dev/null > $OUT/script.txt
grep http: $OUT/load.txt; cat $OUT/split.txt
