#!/bin/bash
exec "$(dirname "$0")/../http-bench/goserver.bin" -addr 127.0.0.1:$1
