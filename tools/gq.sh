#!/bin/sh
# Run a KoboQuery batch against the headless kobo Ghidra project.
# Usage: tools/gq.sh <queryfile> <outfile> [program]   (program defaults to libnickel.so.1.0.0)
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
GHIDRA="${GHIDRA:-/Users/vdmkenny/starlancer-decomp/tools/ghidra_12.1.3_PUBLIC}"
PROG="${3:-libnickel.so.1.0.0}"
GHIDRA_HEADLESS_MAXMEM="${GHIDRA_HEADLESS_MAXMEM:-6G}" "$GHIDRA/support/analyzeHeadless" \
	"$ROOT/ghidra" kobo -process "$PROG" -readOnly -noanalysis \
	-scriptPath "$HERE/ghidra_scripts" -postScript KoboQuery.java "$(cd "$(dirname "$1")" && pwd)/$(basename "$1")" "$2" \
	> "$ROOT/ghidra/query.log" 2>&1 || { tail -20 "$ROOT/ghidra/query.log"; exit 1; }
