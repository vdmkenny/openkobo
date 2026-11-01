#!/bin/sh
# Runs inside a linux/arm/v7 container with out/bench mounted at /b. Every
# workload runs twice: on the stock libraries, then on the new ones, both on
# the firmware's own glibc and loader.
cd /b
run() {
	set=$1; shift
	./rt/ld.so --library-path "$set:rt" ./bench "$@" 2>&1 | grep -v 'no version information available'
}
both() { for s in stock new; do printf '%-6s ' $s; run $s "$@"; done; }

[ -s data/cover.jpg ] || run new mkcover data/cover.jpg
for s in stock new; do printf '%-6s ' $s; run $s versions; done
both inflate data/chapter.z 20
both inflate data/georgia.z 40
both jpeg data/cover.jpg 1 3
both jpeg data/cover.jpg 4 8
both ft data/georgia.ttf data/page.txt 10 212 3
both ft data/OpenDyslexic-Regular.otf data/page.txt 10 212 3
both xml data/chapter.xhtml 4
